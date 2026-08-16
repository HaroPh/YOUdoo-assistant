# backend/src/agents/routing.py
"""Tầng định tuyến của trợ lý — hợp đồng HAI LỚP, lai xác suất + tất định.

Đây là chỗ DUY NHẤT trong repo mô tả trọn cơ chế này. Trước 2026-08-04 nó nằm
rải ở 4 file (prompts.py, nodes.py, graph.py, skill_gate.py) và không file nào
tự nhận mình là tầng định tuyến.

    message ──► [node "intent_router"] ──state──► [decide_route] ──► node đích
                 LỚP 1: LLM đề xuất               LỚP 2: tất định
                 RouteProposal(intent, sop)       veto thắng → trả 1 chuỗi

LỚP 1 — XÁC SUẤT (make_intent_router_node → parse_proposal):
    Một lượt gọi LLM duy nhất đề xuất CẢ `intent` lẫn `sop` (không tốn call
    thêm — đáng kể khi OpenRouter chỉ ~50 req/ngày). Đầu ra là ĐỀ CỬ, tên kiểu
    RouteProposal nói đúng điều đó. Parse fail-an-toàn mọi hướng; tên worker
    model bịa ra không bao giờ lọt ra ngoài.

LỚP 2 — TẤT ĐỊNH, VÀ NÓ THẮNG (decide_route):
    Điều kiện phủ quyết (`looks_like_question`) KHÔNG phụ thuộc phân loại của
    LLM. Đề cử SOP chỉ được nhận trọn lượt khi câu người dùng không mang dấu
    hiệu câu hỏi, HOẶC router tự tin nói erp_write.

VÌ SAO LỚP 2 PHẢI TẤT ĐỊNH — ba bằng chứng độc lập:
    1. Live-verify 2026-07-16: router LLM lỡ route lệnh thật 3/3 LẦN THỬ trên
       chính ngôn ngữ quy trình ("quy trình nhập kho cho đơn mua P00021").
    2. Thí nghiệm model 2026-07-31 (chạy thật trên cổng sop_select):
       gemini-3.1-flash-lite HOÀ đúng ca đang fail với gemma-4-26b; còn
       groq-gpt-oss-120b TỆ HƠN — đẻ thêm một ca hijack mới. Model to hơn
       không cứu được.
    3. Nguồn ngoài dự án (research 2026-08-04): đây là inverse/U-shaped
       scaling đã công bố — McKenzie et al., "Inverse Scaling: When Bigger
       Isn't Better", TMLR 2023. Mô hình lớn hơn bám prior lúc pretrain nhiều
       hơn, bám prompt ít hơn. Pattern chuẩn ngành cho đúng tình huống này là
       hybrid "lớp đề xuất + veto tất định" — chính là thiết kế ở đây.

ĐIỀU KIỆN ĐỂ ĐƯỢC THÁO VETO: hiện tại KHÔNG CÓ. Muốn tháo phải có số đo mới
bác bỏ được cả ba bằng chứng trên. Một supervisor LLM (nếu đời sau làm) chỉ
được đứng TRƯỚC lớp 2, không được thay nó — xem
docs/superpowers/specs/2026-08-04-routing-layer-extraction-design.md §0 để
biết vì sao giai đoạn "supervisor nuốt intent_router" đã bị huỷ.

LƯỚI ĐỠ CUỐI KHÔNG PHẢI TẦNG NÀY: router sai chiều nào thì confirm-gate tại
tool boundary vẫn chặn mọi write chưa được duyệt.

VÌ SAO HAI LỚP KHÔNG GỘP THÀNH MỘT HÀM: LangGraph persist state giữa node và
conditional-edge, nên lớp 1 buộc là node còn lớp 2 buộc là hàm trên cạnh. Đơn
vị làm rõ ở đây là FILE, không phải hàm — đó là thiết kế, không phải thiếu sót.

Ở NGUYÊN CHỖ KHÁC, CÓ CHỦ ĐÍCH: text prompt sống ở prompts.py (quy ước: mọi
prompt ở đó); `intent_targets` + `add_conditional_edges` sống ở graph.py (đó
là sơ đồ, không phải logic định tuyến).
"""
from typing import NamedTuple

from langchain_core.messages import SystemMessage, HumanMessage

from .state import ERPAgentState
from .prompts import render_intent_router_prompt
from . import skill_gate
from .skill_gate import _fold
from .confirmation import CONFIRM, classify_keyword

VALID_INTENTS = {"erp_read", "erp_write", "rag", "mixed", "unknown"}
# Độ sâu — CÂU HỎI THỨ HAI, tách khỏi `sop`. Trước 2026-08-16 hai câu hỏi này
# gộp vào một trường: `sop` vừa phải nói việc thuộc miền nào, vừa phải đoán
# chạy sâu tới đâu. Đó là nguyên nhân ca "quy trình nhập kho cho đơn mua
# P00021" hỏng bền bỉ từ 2026-07-16 (cụm đó nằm ở CẢ vế Dùng-khi lẫn
# KHÔNG-dùng-khi của mô tả skill).
VALID_DEPTHS = {"full_sop", "one_step", "unsure", "none"}


class RouteProposal(NamedTuple):
    """Đầu ra của LỚP 1 — ĐỀ CỬ, chưa phải quyết định định tuyến.

    PHẢI là NamedTuple, KHÔNG được đổi sang dataclass: run_eval.py unpack
    kiểu tuple ở hai chỗ. NamedTuple vẫn LÀ tuple nên chỗ đó không gãy. Đây
    là ràng buộc có test canh (test_route_proposal_unpacks_as_tuple).
    """
    intent: str          # luôn thuộc VALID_INTENTS; "unknown" khi không parse được
    sop: str | None      # MIỀN nghiệp vụ — lớp 2 (decide_route) có quyền bỏ
    depth: str           # luôn thuộc VALID_DEPTHS; "none" khi sop is None


def parse_proposal(text: str, valid_sops) -> RouteProposal:
    """Parse hợp đồng 3 dòng của router. FAIL AN TOÀN ở mọi hướng:

    - intent không nhận ra → "unknown" (hành vi cũ);
    - sop không nằm trong valid_sops → None. Tên worker model bịa ra KHÔNG BAO
      GIỜ được trả ra: nó sẽ thành node đích không tồn tại và làm LangGraph ném
      lỗi định tuyến giữa một lượt chat thật;
    - không thấy dòng "intent:" nào → thử đọc cả chuỗi như MỘT TỪ intent (hợp
      đồng CŨ). Model nhỏ hay bỏ qua format; rơi về đúng hành vi hôm nay tốt
      hơn là rơi về "unknown";
    - sop rỗng → depth LUÔN "none", kể cả khi model điền bừa (đo được ở spike
      vòng 1: model điền depth vào cả lượt sop rỗng);
    - có sop nhưng depth không đọc được → "full_sop". FAIL AN TOÀN: chiều
      "one_step" là chiều BỎ QUA các bước kiểm tra của SOP, không bao giờ được
      là mặc định của một lỗi parse.
    """
    intent: str | None = None
    sop: str | None = None
    depth: str | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("intent:"):
            value = low[len("intent:"):].strip()
            if value in VALID_INTENTS:
                intent = value
        elif low.startswith("sop:"):
            value = stripped[len("sop:"):].strip()
            if value in valid_sops:
                sop = value
        elif low.startswith("depth:"):
            value = low[len("depth:"):].strip()
            if value in VALID_DEPTHS:
                depth = value
    if intent is None:
        bare = (text or "").strip().lower()
        intent = bare if bare in VALID_INTENTS else "unknown"
    if sop is None:
        depth = "none"
    elif depth in (None, "none"):
        depth = "full_sop"
    return RouteProposal(intent, sop, depth)


def make_intent_router_node(llm, worker_block: str = "", valid_sops=frozenset()):
    """LỚP 1 của tầng định tuyến — node LLM đề xuất `intent` + `sop` trong
    CÙNG MỘT lượt gọi (không tốn call thêm; quan trọng khi OpenRouter chỉ
    ~50 req/ngày).

    worker_block + valid_sops được TIÊM VÀO (graph.py lấy từ skill_loader) —
    routing.py cố ý không import skill_loader: node này phải test được với bất
    kỳ danh sách worker nào, kể cả rỗng.

    TÊN NODE TRONG GRAPH PHẢI GIỮ NGUYÊN "intent_router" (graph.py). Không
    phải vì thẩm mỹ: checkpoint Postgres của các hội thoại đang park ở
    interrupt() chứa tên node, đổi tên làm hỏng resume của chúng; và
    test_skill_nodes_reachable_only_from_intent_router assert thẳng tên này
    như một bất biến bảo mật."""
    prompt = render_intent_router_prompt(worker_block)
    valid_sops = frozenset(valid_sops)

    async def intent_router(state: ERPAgentState) -> dict:
        last_human = next(
            (m for m in reversed(state["messages"]) if m.type == "human"),
            None,
        )
        if not last_human:
            return {"intent": "unknown", "sop": None, "depth": "none"}

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=last_human.content),
        ])
        intent, sop, depth = parse_proposal(response.content, valid_sops)
        # LUÔN ghi cả ba khoá (kể cả None/"none"): chúng TRANSIENT, đề cử của
        # lượt trước không được sống sót sang lượt sau.
        return {"intent": intent, "sop": sop, "depth": depth}

    return intent_router


# ── LỚP 2: phủ quyết tất định ────────────────────────────────────────────────

_QUESTION_MARKERS = (
    "?", "la gi", "nghia la", "nhu the nao", "the nao", "tai sao",
    "giai thich", "huong dan", "kiem tra", "tinh trang", "trang thai",
    "duoc khong",
)


def looks_like_question(folded: str) -> bool:
    return any(m in folded for m in _QUESTION_MARKERS)


def replying_to_write_suggestion(state: ERPAgentState) -> bool:
    """Lượt này có phải người dùng ĐỒNG Ý với một ĐỀ XUẤT GHI ở lượt trước?

    Đúng khi CẢ HAI vế cùng đúng: (a) câu trả lời đường ĐỌC ở lượt ngay trước
    (fuse_answer / erp_read) thật sự có đề xuất một hành động ghi — cờ
    `state["suggested_write"]`, do synthesis.extract_write_suggestion tách ra
    từ marker ĐỀ_XUẤT_GHI; và (b) lượt người dùng mới này là một câu ĐỒNG Ý
    gọn ("ok", "có", "làm đi") theo classify_keyword.

    VÌ SAO KHÔNG DÒ VĂN BẢN: câu gây bug thật ("...từ nhà cung cấp Acme
    Corporation không?") không có khuôn "(có / không)" nào để bắt; mà nới ra
    bắt mọi câu kết thúc "...không?" thì MỌI câu hỏi chitchat/RAG thường ngày
    ("Bạn có muốn tôi giải thích thêm không?") theo sau bởi "ok" đều bị ép sai
    sang đường ghi. Một cờ tường minh tránh hẳn thế lưỡng nan đó.

    VÌ SAO ĐỌC STATE KEY RIÊNG, KHÔNG PHẢI AIMessage.additional_kwargs: bản
    đầu gắn cờ lên chính AIMessage và ĐÃ ĐƯỢC ĐO LÀ HỎNG TRONG PRODUCTION.
    `erp_agent._invoke_fresh` chạy trên MỌI lượt không parked (kể cả đúng lượt
    "okay" mà cơ chế này nhắm tới) và dựng LẠI TOÀN BỘ kênh "messages" từ
    payload client gửi lên — mà main.py._filter_messages đã lược mỗi message
    còn {"role", "content"}, nên additional_kwargs không sống sót một lượt
    nào. Cờ nằm trên message vì thế KHÔNG BAO GIỜ tới được hàm này ngoài đời
    thật. State key riêng là một CHANNEL KHÁC của LangGraph: update
    {"messages": reset} của _invoke_fresh không đụng tới nó, nên nó sống sót.

    VÌ SAO CẦN NEO ĐỘ DÀI (suggested_write_at): channel LangGraph là "last
    write wins" — channel không được ghi thì GIỮ NGUYÊN giá trị checkpoint cũ
    mãi mãi. Không có neo, một cờ đặt từ nhiều lượt trước vẫn còn True và sẽ
    bắn phủ quyết nhầm vào một câu "ok" ngắn hoàn toàn không liên quan ở lượt
    xa sau đó. Neo làm cờ TỰ HẾT HẠN: chỉ tin khi len(messages) đúng bằng
    suggested_write_at + 1 — tức đúng MỘT message mới (chính câu trả lời của
    người dùng) được thêm kể từ lúc đặt cờ, không có gì xen giữa. Nhờ vậy
    KHÔNG node nào phải chủ động dọn cờ (không phải sửa respond_unknown,
    rag_node, erp_write_planner, write_continuation và 9 module ghi phối hợp).

    suggested_write_at đếm theo cái NGƯỜI DÙNG THẤY (xem state.py), nên đúng
    cho cả fuse_answer (luôn 1 message) lẫn erp_read (ReAct, phụ thêm cả
    tool-call/tool-result nhưng client chỉ nhận lại 1 câu trả lời).

    Đây CHỈ là quyết định định tuyến. Không hành động ghi nào chạy nếu chưa
    qua _interrupt() thật của erp_write_planner.
    """
    if not state.get("suggested_write"):
        return False
    messages = state.get("messages") or []
    at = state.get("suggested_write_at")
    if at is None or len(messages) != at + 1:
        return False
    last_human = next((m for m in reversed(messages) if m.type == "human"), None)
    if last_human is None:
        return False
    return classify_keyword(last_human.content or "") == CONFIRM


def decide_route(state: ERPAgentState) -> str:
    """Quyết định cuối là TẤT ĐỊNH. Đề cử SOP (state["sop"]) chỉ là một trong
    hai điều kiện; điều kiện kia — câu KHÔNG mang dấu hiệu câu hỏi — là lớp
    phủ quyết không phụ thuộc phân loại LLM.

    Vì sao lớp phủ quyết này CỐ Ý tất định và KHÔNG được tháo ra: bản đầu (chỉ
    AND với intent=="erp_write") đóng đúng ca hijack gốc ("quy trình nhập kho
    là gì?" → skill thay vì RAG) nhưng live-verify 2026-07-16 lộ ra chiều lỗi
    ngược — router phân loại "mixed"/"erp_read" cho chính 2 câu lệnh dùng
    nguyên văn ngôn ngữ quy trình ("quy trình nhập kho cho đơn mua P00021",
    "nhập kho theo quy trình cho đơn mua P00021"), khiến lệnh thật bị lỡ route
    3/3 LẦN THỬ — vì router chưa từng được tune để phân biệt "hỏi VỀ SOP" khỏi
    "thực thi SOP cho 1 đơn cụ thể" (đọc rất giống định nghĩa "mixed" trong
    prompts.py dù ý người dùng là hành động). Chuyển gate sang tất định (đánh
    dấu câu hỏi) giữ nguyên bất biến an toàn (câu hỏi không hijack) mà không
    phụ thuộc phân loại LLM cho quyết định này. Model to hơn CÓ THỂ đủ — nhưng
    "có thể" không phải cơ sở để tháo một lớp phòng thủ đã chứng minh giá trị,
    khi giữ nó tốn 10 dòng.

    Lưới đỡ cuối không phải lớp này: router sai chiều nào thì confirm-gate tại
    tool boundary vẫn chặn mọi write chưa được duyệt."""
    # Phủ quyết SỚM NHẤT: người dùng vừa đồng ý với một đề xuất ghi ở lượt
    # trước. Đặt trước cả nhánh SOP vì đây là ý định tường minh nhất có thể
    # có — mọi đề cử của lớp 1 đều thua nó.
    if replying_to_write_suggestion(state):
        return "erp_write"

    intent = state.get("intent") or "unknown"
    sop = state.get("sop")
    if sop and skill_gate.skills_enabled():
        last_human = next((m.content for m in reversed(state["messages"])
                           if m.type == "human"), "")
        folded = _fold(last_human)
        if intent == "erp_write" or not looks_like_question(folded):
            return sop            # SOP nhận trọn lượt
    return intent                 # phủ quyết: rớt sop, dùng intent
