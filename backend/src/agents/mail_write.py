# backend/src/agents/mail_write.py
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07.

TÁCH 2 NODE LangGraph — KHÁC MỌI coordinator khác trong package này (chỉ
có 1 node). Lý do: preview_template_email TỰ NÓ là một write thật (tạo
mail.mail nháp) — Odoo không cho render template mà không tạo bản ghi qua
XML-RPC. Nếu gọi nó TRƯỚC _interrupt() trong CÙNG một node (khuôn mọi
coordinator khác dùng, vì bước "render" của họ là READ thuần, idempotent),
LangGraph sẽ REPLAY TOÀN BỘ node khi resume sau interrupt — đo thật bằng
probe (review Task 3, 2026-08-07): preview bị gọi LẦN THỨ HAI, tạo bản
mail.mail thứ hai, và mail thật sự gửi đi KHÔNG PHẢI bản người dùng đã
duyệt. Tách node giải quyết triệt để: mỗi node hoàn tất là một ranh giới
checkpoint LangGraph — node đã return xong không bị replay khi node SAU
nó (nơi có interrupt) resume.

  Node 1 (send_order_confirmation_email_preview): gọi preview_template_email
    MỘT LẦN DUY NHẤT, lưu mail_id/subject/recipient_count vào
    pending_action.args (persist qua state, không phải biến cục bộ), rồi
    (qua conditional edge ở graph.py, KHÔNG unconditional) chuyển sang Node 2
    nếu thành công, hoặc thẳng write_continuation nếu lỗi/thiếu input.
  Node 2 (send_order_confirmation_email): đọc dữ liệu đã lưu từ Node 1
    (KHÔNG gọi lại preview), _interrupt xác nhận, rồi gọi send_prepared_email.

TỪ CHỐI GỬI PHẢI CHỦ ĐỘNG HỦY BẢN NHÁP (đảo ngược quyết định §4.1 gốc của
spec — quyết định đó được duyệt TRƯỚC KHI biết Odoo có cron "Mail: Email
Queue Manager" đang bật, tự động gửi MỌI mail.mail ở trạng thái 'outgoing',
kể cả bản bị từ chối, nếu không chủ động hủy). Gọi discard_prepared_email
ở nhánh từ chối — best-effort (lỗi hủy không chặn thông báo "đã hủy" cho
người dùng, vì từ góc nhìn agent, hành động ĐÃ bị hủy; dọn dẹp mail.mail là
lớp phòng vệ thêm, không phải hợp đồng chính).

KHÔNG đăng ký vào NEXT_STEPS: confirm_sale_order đã có bước kế tiếp
"deliver_order" — thêm bước này vào sẽ ghi đè, phá chuỗi giao hàng có sẵn.
Gửi mail xác nhận là hành động người dùng tự yêu cầu riêng — PHẢI được
liệt kê trong WRITE_PLANNER_PROMPT (prompts.py) để planner có thể chọn nó,
khác các coordinator chỉ tới được qua NEXT_STEPS."""
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import _ttl_expiry, _msg, WRITE_DISABLED_MSG
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX


def _finish(tool_name: str, result) -> dict:
    display, env = parse_write_result(result)
    return {**_msg(display), "pending_action": None,
            "last_write": {"tool": tool_name, **env} if env else None}


def make_send_order_confirmation_email_preview_node(tools):
    """Node 1: soạn mail (1 write thật), lưu kết quả vào state. KHÔNG
    interrupt ở đây — xem docstring module."""
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_preview_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        action = state.get("pending_action") or {}
        args = action.get("args") or {}
        order_ref = str(args.get("order_ref") or "").strip()
        if not order_ref:
            return _msg("Bạn cần cho biết mã đơn bán cần gửi mail xác nhận.")

        preview_tool = by_name.get("preview_template_email")
        if preview_tool is None:
            return _msg("Công cụ soạn mail không khả dụng.")
        try:
            result = await preview_tool.ainvoke({
                "template_name": "Sales: Order Confirmation",
                "res_model": "sale.order", "ref": order_ref})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi soạn mail: {e}")
        # preview_template_email trả JSON phẳng {ok, display, mail_id, subject,
        # recipient_count} — parse_write_result chỉ cần key "ok"+"display" để
        # coi là envelope hợp lệ, KHÔNG lồng dưới "data" (đó là shape khác của
        # erp_query/envelope.py). env ở đây CHÍNH LÀ dict đã json.loads.
        display, env = parse_write_result(result)
        if env is None:
            return _msg(display)

        # Lưu vào pending_action.args — Node 2 đọc từ ĐÂY, không gọi lại
        # preview_template_email. Đây là ranh giới persist thật (node này
        # return xong mới tới Node 2), không phải biến cục bộ sẽ mất khi
        # LangGraph replay.
        return {"pending_action": {**action,
                                   "args": {**args, "mail_id": env.get("mail_id"),
                                            "subject": env.get("subject"),
                                            "recipient_count": env.get("recipient_count")}}}

    return send_order_confirmation_email_preview_node


def make_send_order_confirmation_email_node(tools):
    """Node 2: đọc mail_id/subject/recipient_count đã lưu (Node 1), xác
    nhận, gửi. Từ chối → hủy bản nháp (best-effort) — xem docstring module."""
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_node(state: ERPAgentState) -> dict:
        args = (state.get("pending_action") or {}).get("args") or {}
        order_ref = str(args.get("order_ref") or "")
        mail_id = args.get("mail_id")

        preview_text = (f"Mail xác nhận đơn {order_ref}:\n"
                        f"  Tới: {args.get('recipient_count', 0)} người nhận\n"
                        f"  Tiêu đề: {args.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            discard_tool = by_name.get("discard_prepared_email")
            if discard_tool is not None:
                try:
                    await discard_tool.ainvoke({"mail_id": mail_id})
                except Exception:  # noqa: BLE001 — best-effort, không chặn thông báo hủy
                    pass
            return _msg("Đã hủy gửi mail xác nhận đơn.")

        send_tool = by_name.get("send_prepared_email")
        if send_tool is None:
            return _msg("Công cụ gửi mail không khả dụng.")
        try:
            result = await send_tool.ainvoke({"mail_id": mail_id})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi gửi mail: {e}")
        return _finish("send_order_confirmation_email", result)

    return send_order_confirmation_email_node


def route_after_mail_preview(state: ERPAgentState) -> str:
    """Node 1 → Node 2 (thành công, có mail_id) hoặc thẳng write_continuation
    (lỗi/thiếu input — Node 1 đã tự trả _msg lỗi, Node 2 không cần chạy)."""
    args = (state.get("pending_action") or {}).get("args") or {}
    if args.get("mail_id"):
        return "send_order_confirmation_email"
    return "write_continuation"
