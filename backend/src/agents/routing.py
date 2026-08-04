# backend/src/agents/routing.py
"""Tầng định tuyến — LỚP 1: đề xuất (xác suất).

Lớp 2 (phủ quyết tất định) chuyển vào file này ở task kế tiếp; docstring đầy
đủ về hợp đồng 2 lớp được viết khi cả hai lớp đã có mặt, để không có commit
nào mô tả thứ chưa tồn tại.
"""
from typing import NamedTuple

from langchain_core.messages import SystemMessage, HumanMessage

from .state import ERPAgentState
from .prompts import render_intent_router_prompt

VALID_INTENTS = {"erp_read", "erp_write", "rag", "mixed", "unknown"}


class RouteProposal(NamedTuple):
    """Đầu ra của LỚP 1 — ĐỀ CỬ, chưa phải quyết định định tuyến.

    PHẢI là NamedTuple, KHÔNG được đổi sang dataclass: eval_sop_select
    (evals/run_eval.py) unpack kiểu tuple (`intent, sop = parse_proposal(...)`).
    NamedTuple vẫn LÀ tuple nên chỗ đó không gãy. Đây là ràng buộc có test
    canh (test_route_proposal_unpacks_as_tuple), không phải sở thích.
    """
    intent: str          # luôn thuộc VALID_INTENTS; "unknown" khi không parse được
    sop: str | None      # ĐỀ CỬ — lớp 2 (decide_route) có quyền bỏ


def parse_proposal(text: str, valid_sops) -> RouteProposal:
    """Parse hợp đồng 2 dòng của router. FAIL AN TOÀN ở mọi hướng:

    - intent không nhận ra → "unknown" (hành vi cũ);
    - sop không nằm trong valid_sops → None. Tên worker model bịa ra KHÔNG BAO
      GIỜ được trả ra: nó sẽ thành node đích không tồn tại và làm LangGraph ném
      lỗi định tuyến giữa một lượt chat thật;
    - không thấy dòng "intent:" nào → thử đọc cả chuỗi như MỘT TỪ intent (hợp
      đồng CŨ). Model nhỏ hay bỏ qua format; rơi về đúng hành vi hôm nay tốt
      hơn là rơi về "unknown"."""
    intent: str | None = None
    sop: str | None = None
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
    if intent is None:
        bare = (text or "").strip().lower()
        intent = bare if bare in VALID_INTENTS else "unknown"
    return RouteProposal(intent, sop)


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
            return {"intent": "unknown", "sop": None}

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=last_human.content),
        ])
        intent, sop = parse_proposal(response.content, valid_sops)
        # LUÔN ghi khoá "sop" (kể cả None): nó TRANSIENT, đề cử của lượt trước
        # không được sống sót sang lượt sau.
        return {"intent": intent, "sop": sop}

    return intent_router
