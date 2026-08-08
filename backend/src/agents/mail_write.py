# backend/src/agents/mail_write.py
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07, cập nhật
spec 2026-08-08 (bản nháp trơ tính — xem mcp-servers/odoo/tools/mail.py).

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
    MỘT LẦN DUY NHẤT, lưu mail_id/subject/recipients vào pending_action.args
    (persist qua state, không phải biến cục bộ), rồi (qua conditional edge ở
    graph.py, KHÔNG unconditional) chuyển sang Node 2 nếu thành công, hoặc
    thẳng write_continuation nếu lỗi/thiếu input.
  Node 2 (send_order_confirmation_email): đọc dữ liệu đã lưu từ Node 1
    (KHÔNG gọi lại preview), tự re-check write_gate (xem Finding 1 dưới),
    _interrupt xác nhận, rồi gọi send_prepared_email.

"recipients" LÀ DANH SÁCH NGƯỜI NHẬN THẬT, KHÔNG PHẢI SỐ LƯỢNG (final review
2026-08-07, Finding 4 — Important): bản trước lưu "recipient_count" và hiện
"Tới: N người nhận" ở cổng xác nhận — người dùng không thể biết AI định gửi
mail cho AI, nên cổng xác nhận (thứ được dựng ra CHÍNH để bắt sai người nhận)
mất tác dụng. preview_template_email (mcp-servers/odoo/tools/mail.py) giờ đọc
cả recipient_ids (many2many res.partner, resolve tên/email qua "read") lẫn
email_to (field địa chỉ thô song song — bỏ sót nó thì đếm/liệt kê ra rỗng dù
mail VẪN sẽ gửi tới địa chỉ đó) và trả về "recipients": [chuỗi người đọc
được, ...].

BẢN NHÁP TRƠ TÍNH TỪ LÚC TẠO (spec 2026-08-08 — ĐÓNG rủi ro "hội thoại bị
bỏ dở" từng ghi ở đây là CHẤP NHẬN, không sửa): preview_template_email giờ
tự chuyển state của bản nháp sang 'cancel' ngay sau khi tạo (xác minh qua
chính mã nguồn Odoo: cron "Mail: Email Queue Manager" VÀ mail.mail._send()
nội bộ đều chỉ xử lý bản ghi ở state='outgoing', bỏ qua lặng lẽ mọi state
khác) — coordinator ở file này không cần biết/làm gì thêm, cơ chế nằm trọn
trong lớp MCP tool. Hệ quả: discard_prepared_email (dưới đây) không còn là
cơ chế an toàn bắt buộc nữa, chỉ còn là dọn dẹp best-effort.

NODE 2 PHẢI TỰ RE-CHECK write_gate (review round 2, Finding 1 — Important,
2026-08-07): tách 2 node vô tình xóa mất một bất biến an toàn mà mọi
coordinator 1-node khác có MIỄN PHÍ — LangGraph replay TOÀN BỘ node khi
resume sau interrupt, nên gate check ở đầu node của họ tự động chạy lại ở
MỌI lần resume. Node 1 ở đây chỉ chạy MỘT LẦN trước khi interrupt tồn tại,
nên nếu chỉ Node 1 check gate, gate bị tắt (từ Odoo UI) ngay lúc câu hỏi
xác nhận đang chờ sẽ không bao giờ được phát hiện — đo thật: thiếu check
này, resume(confirm=True) vẫn gửi mail thật dù gate đã tắt.

TỪ CHỐI GỬI VẪN GỌI discard_prepared_email — GIỜ CHỈ LÀ DỌN DẸP, KHÔNG PHẢI
AN TOÀN (đảo ngược nốt phần còn lại của quyết định §4.1 gốc của spec, sau
khi spec 2026-08-08 đóng triệt để rủi ro cron ở lớp MCP tool): bản nháp đã
trơ tính (state='cancel') ngay từ lúc Node 1 tạo ra nó, nên thất bại của
discard_prepared_email (vd bị chính write_actions_enabled() gate chặn ở
nhánh gate-tắt-giữa-chừng — unlink cũng là write) chỉ để lại một bản ghi
rác nằm im trong Odoo, KHÔNG kéo theo rủi ro gửi ngoài ý muốn nữa — không
còn cần cảnh báo người dùng về rủi ro đó (khác bản trước 2026-08-07).

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
        #
        # "recipients" (danh sách chuỗi người-nhận-thật), KHÔNG PHẢI
        # "recipient_count" (final review 2026-08-07, Finding 4) — số lượng
        # không cho người dùng biết AI định gửi mail cho AI, cổng xác nhận vô
        # nghĩa nếu không lộ ra được đối tượng thật.
        return {"pending_action": {**action,
                                   "args": {**args, "mail_id": env.get("mail_id"),
                                            "subject": env.get("subject"),
                                            "recipients": env.get("recipients")}}}

    return send_order_confirmation_email_preview_node


def make_send_order_confirmation_email_node(tools):
    """Node 2: đọc mail_id/subject/recipients đã lưu (Node 1), xác nhận, gửi.
    Từ chối → hủy bản nháp (best-effort, thất bại im lặng nuốt vì bản nháp
    đã trơ tính từ lúc tạo — xem docstring module).

    RE-CHECK write_gate Ở ĐÂY, KHÔNG chỉ ở Node 1 (review round 2, Finding
    1 — Important): mọi coordinator 1-node khác tự động re-check gate ở MỌI
    lần resume, vì LangGraph replay TOÀN BỘ node (gồm cả check ở đầu) khi
    resume sau _interrupt(). Tách 2 node đã vô tình xóa mất bất biến đó —
    Node 1 chỉ chạy 1 lần TRƯỚC KHI interrupt tồn tại, nên gate có thể bị
    tắt (từ Odoo UI, giữa lúc câu hỏi xác nhận đang chờ) mà Node 1 không
    bao giờ biết. Đo thật: gate tắt lúc đang chờ + resume(confirm=True) →
    node cũ (không check) vẫn gửi mail thật."""
    by_name = {t.name: t for t in tools}

    async def _discard_draft(mail_id) -> None:
        """Best-effort dọn dẹp bản nháp bị từ chối/gate-tắt. Bản nháp đã trơ
        tính (state='cancel' — mcp-servers/odoo/tools/mail.py, spec
        2026-08-08) ngay từ lúc Node 1 tạo ra nó, nên thất bại ở đây (vd
        unlink cũng bị chặn bởi write_actions_enabled() giống mọi write
        khác) chỉ để lại một bản ghi rác nằm im trong Odoo — KHÔNG còn kéo
        theo rủi ro gửi ngoài ý muốn (khác thiết kế cũ trước 2026-08-08)."""
        discard_tool = by_name.get("discard_prepared_email")
        if discard_tool is None:
            return
        try:
            await discard_tool.ainvoke({"mail_id": mail_id})
        except Exception:  # noqa: BLE001 — best-effort, không raise cho user
            pass

    async def send_order_confirmation_email_node(state: ERPAgentState) -> dict:
        args = (state.get("pending_action") or {}).get("args") or {}
        mail_id = args.get("mail_id")

        if not write_gate.write_actions_enabled():
            # Bản nháp (Node 1) đã tồn tại thật, nhưng đã trơ tính
            # (state='cancel', spec 2026-08-08) ngay từ lúc tạo — dọn ở đây
            # chỉ là best-effort, không còn ảnh hưởng tới an toàn (xem
            # docstring module + _discard_draft).
            await _discard_draft(mail_id)
            return _msg(WRITE_DISABLED_MSG)

        order_ref = str(args.get("order_ref") or "")
        recipients = args.get("recipients") or []
        preview_text = (f"Mail xác nhận đơn {order_ref}:\n"
                        f"  Tới: {', '.join(recipients) if recipients else 'không rõ người nhận'}\n"
                        f"  Tiêu đề: {args.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            await _discard_draft(mail_id)
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
