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
        except Exception:
            # KHÔNG để exception thoát ra: LangGraph để lỗi một nhánh giết CẢ
            # superstep, tức chân ERP đang chạy song song cũng mất theo.
            logger.exception("gather_docs failed")
            chunks = []
        return {"doc_context": [chunk_to_dict(c) for c in chunks]}

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
