# backend/src/agents/fanout.py
"""Fan-out đường đọc cho intent `mixed` (SP-2b) — thay node `fusion`.

    intent_router --"mixed"--> mixed ──┬──> gather_docs ──┐
                              (fan-out) │                  ├──> fuse_answer ──> END
                                        └──> gather_erp  ──┘

Hai chân chạy CÙNG một superstep LangGraph và ghi HAI key state khác nhau;
không chân nào ghi `messages`. Nhờ vậy không có xung đột reducer và người dùng
không thể nhận hai câu trả lời cho một lượt.

Vì sao fan-out của việc THU THẬP chứ không phải của việc TRẢ LỜI: cả 8 ca
MULTI_SOURCE_CASES đều cần một giá trị trong tài liệu (30 ngày, 3 ngày, 0,5%,
bảng chiết khấu) để DIỄN GIẢI một bản ghi ERP — suy luận là tuần tự, chỉ thu
thập mới song song được. Hai nhánh cùng tự trả lời rồi ghép hai câu trả lời sẽ
hỏng: mỗi nhánh chỉ thấy nửa dữ kiện nên đều nói "không đủ thông tin".
"""
import asyncio
import logging
from dataclasses import asdict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.agents import create_agent as _create_agent

from .state import ERPAgentState
from .prompts import FUSE_PROMPT, GATHER_ERP_PROMPT
from .synthesis import SAFE_MSG, _format_context, cite_and_verify, passes_floor
from .erp_grounding import verify_erp_grounding
from ..rag.retrieve import retrieve
from ..rag.types import Chunk

logger = logging.getLogger(__name__)


def _last_human(state) -> str:
    return next((m.content for m in reversed(state["messages"])
                 if m.type == "human"), "")


def chunk_to_dict(c: Chunk) -> dict:
    """Chunk → JSON thuần để đặt vào state.

    BẤT BIẾN: state chỉ chứa JSON thuần. Chunk là @dataclass(frozen=True);
    nhét thẳng dataclass vào state là loại lỗi CHỈ hỏng khi checkpointer
    Postgres thật chạy — unit test mock checkpointer sẽ bỏ lọt hoàn toàn (bài
    học SP-1C2, nơi một cơ chế dựa vào hạ tầng thật đi qua sạch mọi unit test
    rồi hỏng trên production). Ràng JSON thuần chọn cách không phải dựa vào đó.
    """
    return asdict(c)


def chunks_from_dicts(ds) -> list[Chunk]:
    """Dựng lại Chunk từ state để đưa vào cite_and_verify()."""
    return [Chunk(**d) for d in (ds or [])]


def make_mixed_node():
    """Điểm FAN-OUT. Không LLM, không I/O.

    Giữ nguyên TÊN `mixed` và nguyên chỗ trong intent_targets là quyết định có
    chủ đích: nhờ vậy `_route_by_intent` KHÔNG ĐỔI MỘT KÝ TỰ, mà hàm đó chính
    là thứ bộ eval SOP_SELECT_CASES đo trực tiếp ("Đích là giá trị
    _route_by_intent() TRẢ VỀ" — cases.py). Cho hàm đó trả về list
    ["gather_docs","gather_erp"] trông gọn hơn một dòng nhưng phá hợp đồng đầu
    ra mà bộ eval đang đo, và kéo theo cả lớp phủ quyết _looks_like_question
    của SP-2a phải chứng minh lại. Đổi 1 dòng lấy 1 bộ eval là lỗ.

    Node KHÔNG rỗng: xoá hai key join lúc VÀO là lớp CHỊU LỰC chống dữ liệu ôi
    qua lượt. LangGraph giữ giá trị channel khi node bỏ qua key, nên nếu ở lượt
    sau gather_docs ngã và không ghi gì, fuse_answer sẽ lặng lẽ trích dẫn chunk
    của lượt TRƯỚC. Xoá tất định tại đúng một chỗ khiến tính đúng KHÔNG phụ
    thuộc vào việc mọi đường lỗi của mọi chân đều nhớ ghi key.
    """
    async def mixed(state: ERPAgentState) -> dict:
        return {"doc_context": None, "erp_facts": None}

    return mixed


def make_gather_docs_node():
    """Chân TÀI LIỆU: retrieve() thuần, KHÔNG gọi LLM lần nào.

    Luôn truy xuất bằng NGUYÊN câu hỏi người dùng. `fusion` cũ phải mang cơ chế
    aux_queries vì agent tự chọn query và hay truyền từ khoá trần kiểu "SLA" —
    vốn không bao giờ kéo được sla.docx lên; fan-out dùng thẳng câu hỏi đầy đủ
    (chính là query mà docstring fusion nói là "reliably does"), nên cơ chế đó
    không còn cần trên đường này.
    """
    async def gather_docs(state: ERPAgentState) -> dict:
        query = _last_human(state)
        if not query:
            return {"doc_context": []}
        try:
            # retrieve() là psycopg ĐỒNG BỘ — to_thread giữ event loop rảnh
            # cho chân ERP chạy song song trong cùng superstep.
            result = await asyncio.to_thread(retrieve, query)
            chunks = ([] if result.is_empty() or not passes_floor(result)
                      else result.chunks)
            doc_context = [chunk_to_dict(c) for c in chunks]
        except Exception:
            # KHÔNG để exception thoát ra: LangGraph để lỗi một nhánh giết CẢ
            # superstep, tức chân ERP đang chạy song song cũng mất theo.
            logger.exception("gather_docs failed")
            doc_context = []
        return {"doc_context": doc_context}

    return gather_docs


def make_gather_erp_node(llm, tools):
    """Chân ERP: ReAct agent chế độ THU THẬP — nêu dữ kiện, không kết luận.

    Khác `erp_read` ở MỤC ĐÍCH chứ không phải trùng lặp. Hỏi "Đơn S00042 còn
    được hoàn hàng theo chính sách không?" thì `erp_read` với SYSTEM_PROMPT rất
    dễ trả lời "tôi không biết chính sách" thay vì đi lấy ngày giao của S00042 —
    đúng nửa dữ kiện mà `fuse_answer` cần.

    KHÔNG bê deny-list WRITE_TOOL_NAMES của fusion.py sang. Nó liệt kê 9 tên
    trong khi WRITE_PLANNER_PROMPT khai 29 tool ghi, nên thực tế là no-op — mà
    lại TRÔNG NHƯ một lớp phòng thủ. Lớp thật là allow-list
    build_erp_query_tools() do graph.py truyền vào, có test chốt containment
    (tests/agents/test_fanout_graph.py). Allow-list + test nói đúng sự thật;
    deny-list thiếu 20 tên thì không.

    verify_erp_grounding tại ĐÂY là cố ý: `fusion` cũ verify câu trả lời CUỐI
    so với tool output THÔ. Fan-out tách đôi, nên nếu chỉ verify ở fuse_answer
    (so với erp_facts) thì dữ kiện do chính chân này bịa ra sẽ không bao giờ bị
    bắt — SP-2b sẽ lặng lẽ làm YẾU một bảo đảm đang có. Hai chặng verify bắc
    cầu kín: dữ kiện ⊂ tool output thô, câu trả lời ⊂ dữ kiện.
    """
    async def gather_erp(state: ERPAgentState) -> dict:
        try:
            agent = _create_agent(llm, tools, system_prompt=GATHER_ERP_PROMPT)
            result = await agent.ainvoke({"messages": state["messages"]})
            msgs = result["messages"]
            facts = (msgs[-1].content or "").strip() if msgs else ""
            tool_outputs = [m.content for m in msgs if m.type == "tool"]
            if facts and tool_outputs:
                facts = await verify_erp_grounding(facts, tool_outputs, llm)
        except Exception:
            # Xem gather_docs: exception thoát ra giết CẢ superstep.
            logger.exception("gather_erp failed")
            facts = ""
        return {"erp_facts": facts}

    return gather_erp


def render_fuse_input(chunks, erp_facts: str, question: str) -> str:
    """NGUỒN SỰ THẬT DUY NHẤT cho hình dạng input của fuse_answer.

    Dùng bởi CẢ node thật LẪN evals.run_eval.eval_multi_source — bắt buộc, không
    phải tiện tay. Bài học SP-2a: eval_intent() mirror hợp đồng đầu ra của router
    ở một module khác; Task 8 đổi hợp đồng, eval không đổi theo, acc rơi
    0.870 → 0.148 với MỌI ca parse thành "unknown", và không ai nghi ngờ vì lỗi
    trông y hệt lỗi chất lượng model. Dùng chung một hàm thì mirror KHÔNG THỂ
    trôi khỏi node thật.

    fusion cũ phải tự quản `start=` tăng dần vì agent gọi search_documents nhiều
    lần; fan-out truy xuất ĐÚNG MỘT LẦN nên _format_context chạy start=1 và sổ
    sách đó biến mất.
    """
    return (f"TÀI LIỆU:\n{_format_context(chunks)}\n\n"
            f"DỮ LIỆU ERP:\n{erp_facts}\n\n"
            f"CÂU HỎI: {question}")


def make_fuse_answer_node(llm):
    """Node JOIN: một lượt LLM trên cả hai nguồn, rồi trích dẫn + verify.

    Xoá hai key join lúc RA là VỆ SINH (một lượt erp_read sau đó không vác theo
    cả đống chunk trong checkpoint và trace Langfuse) — KHÁC với việc node
    `mixed` xoá lúc VÀO, vốn là lớp chịu lực cho TÍNH ĐÚNG. Hai chỗ, hai lý do,
    không phải hai lớp cho cùng một việc.
    """
    async def fuse_answer(state: ERPAgentState) -> dict:
        clear = {"doc_context": None, "erp_facts": None}
        erp_facts = state.get("erp_facts") or ""
        try:
            chunks = chunks_from_dicts(state.get("doc_context"))
            if not chunks and not erp_facts:
                # Hai chân cùng rỗng → không có gì để suy luận. Kiểm tra TẤT
                # ĐỊNH, không giao cho model tự nhận ra.
                return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
            resp = await llm.ainvoke([
                SystemMessage(content=FUSE_PROMPT),
                HumanMessage(content=render_fuse_input(
                    chunks, erp_facts, _last_human(state))),
            ])
            answer = (resp.content or "").strip()
            if not answer:
                return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
            # `chunks` ở đây LUÔN là TOÀN BỘ kết quả gather_docs của lượt này
            # — khác `fusion` cũ, nơi `collected` chỉ gồm chunk agent THẬT SỰ
            # gọi search_documents lấy về (gather_docs không phải agent, nó
            # truy xuất một lần, không chọn lọc theo yêu cầu model). Hệ quả:
            # nếu model bỏ dòng NGUỒN_DÙNG (trả lời chỉ dựa ERP), extract_
            # used_citations() (synthesis.py) fallback về TOÀN BỘ chunks, và
            # verify_citations() fail-open (lỗi LLM → giữ nguyên toàn bộ) —
            # nên về lý thuyết có thể đính "📄 Nguồn:" vào câu trả lời không
            # thực sự dùng tài liệu. Chấp nhận: câu hỏi mixed luôn có ý định
            # cần tài liệu, passes_floor lọc truy xuất lạc đề trước khi tới
            # đây, và chưa quan sát thấy xảy ra thật (final review SP-2b,
            # 2026-08-01) — nhưng đây là lý do nếu xảy ra.
            answer = await cite_and_verify(answer, chunks, llm)
            if erp_facts:
                answer = await verify_erp_grounding(answer, [erp_facts], llm)
        except Exception:
            logger.exception("fuse_answer failed")
            answer = SAFE_MSG
        return {"messages": [AIMessage(content=answer)], **clear}

    return fuse_answer
