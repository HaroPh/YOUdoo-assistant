# backend/src/agents/continuation.py
"""Write-continuation: after any write, append a non-blocking, deterministic
suggestion for the next linear step from NEXT_STEPS to the reply — never an
interrupt. If the user follows up on it in a later message, that message
goes through the normal write-planner confirm gate like any other request
(no shortcut). Cross-cutting node, not a per-flow coordinator; deterministic
(no LLM). Sole consumer of last_write: returns last_write=None on EVERY
branch, so a stale handle can never re-offer an old record's next step. Khi
auto_chain còn bước khớp NEXT_STEPS, bước kế tự chạy không interrupt — user
đã tự khai báo cả chuỗi trong 1 câu, mức đồng ý mạnh hơn 1 gợi ý bình
thường. NGOẠI LỆ: bước thuộc CONFIRM_IN_CHAIN vẫn dừng hỏi lại. Lý lẽ trên
có một biên: lúc khai báo chuỗi, hóa đơn CHƯA tồn tại, nên user đồng ý với
HÀNH ĐỘNG chứ không thể đồng ý với SỐ TIỀN. Những bước đó được chuyển vào
coordinator riêng để hiện bảng dòng hàng trước cổng xác nhận (spec
2026-08-06)."""

from langchain_core.messages import AIMessage
from langgraph.graph import END

from .state import ERPAgentState
from .write_registry import NEXT_STEPS, CONFIRM_IN_CHAIN, WRITE_COORDINATORS


def make_write_continuation_node():
    async def write_continuation(state: ERPAgentState) -> dict:
        lw = state.get("last_write")
        queue = state.get("auto_chain") or []
        step = NEXT_STEPS.get((lw or {}).get("tool"))
        if not lw or not lw.get("ok") or step is None:
            # terminal / failed write / non-chain tool → end, no extra message
            # (the executor's display is already the final answer).
            upd = {"pending_action": None, "confirmed": None, "last_write": None,
                   "auto_chain": None}
            if queue and lw:
                # một write ĐÃ chạy (lỗi, hoặc rẽ khỏi chuỗi như nhánh flag) mà
                # chuỗi khai báo còn bước → báo tất định. Cancel (lw falsy):
                # im lặng — "Đã hủy." của coordinator đã đủ.
                upd["messages"] = [AIMessage(
                    content=f"{lw['display']}\n\n⚠️ Chuỗi tự động dừng: bước tiếp theo không chạy.")]
            return upd

        if queue and queue[0] == step.tool:
            base = {"pending_action": {"tool": step.tool, "args": step.args(lw),
                                       "summary": step.label},
                    "last_write": None, "auto_chain": queue[1:] or None}
            if step.tool in CONFIRM_IN_CHAIN:
                # Bước đụng tiền: KHÔNG auto-run. Giao cho coordinator để nó tự
                # đọc hóa đơn, hiện bảng dòng hàng + số tiền, rồi mới interrupt.
                return {**base, "confirmed": None}
            # Bước kế đã được user duyệt trước ở confirm đầu chuỗi (chain_note)
            # → tự chạy, KHÔNG interrupt.
            return {**base, "confirmed": True}

        suggestion = f"{lw['display']}\n\n(Bạn có thể yêu cầu \"{step.label}\" bất cứ lúc nào.)"
        return {"pending_action": None, "confirmed": None, "last_write": None,
                "auto_chain": None, "messages": [AIMessage(content=suggestion)]}

    return write_continuation


def _route_after_continuation(state: ERPAgentState) -> str:
    action = state.get("pending_action") or {}
    tool = action.get("tool")
    if tool in CONFIRM_IN_CHAIN:
        # Coordinator tự lo cổng xác nhận của nó (giống _route_after_write_planner).
        return WRITE_COORDINATORS[tool].node
    if action and state.get("confirmed"):
        return "erp_write_executor"
    return END
