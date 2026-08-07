"""Tool MCP domain Mail (mail.template / mail.mail) — spec 2026-08-07.

3 tool DÙNG CHUNG cho MỌI điểm nối gửi mail tương lai (không riêng theo
domain — cơ chế gốc Odoo mail.template.send_mail/mail.mail.send đã là hàm
chung, không có logic nghiệp vụ riêng theo domain, khác hẳn
confirm_sale_order nơi state-check là logic riêng của sale). LLM KHÔNG tự
chọn template — mỗi coordinator ở tầng agent hardcode template_name của
chính nó; 3 tool này chỉ là lớp thực thi.

preview_template_email TẠO một bản mail.mail nháp thật (Odoo không cho
render template mà không tạo bản ghi qua XML-RPC — các method render nội
bộ như _render_template bị chặn gọi từ xa, đã kiểm chứng thật 2026-08-07).
Đây KHÔNG phải thao tác đọc thuần.

Bản nháp bị từ chối gửi PHẢI được dọn qua discard_prepared_email (đảo
ngược quyết định §4.1 gốc của spec — quyết định đó được duyệt TRƯỚC KHI
biết Odoo có cron "Mail: Email Queue Manager" đang bật, tự động gửi MỌI
mail.mail ở trạng thái 'outgoing' mỗi giờ, kể cả bản bị từ chối nếu không
chủ động hủy; đã xác nhận thật trên Odoo 2026-08-07). Việc gọi tool này ở
nhánh từ chối là trách nhiệm của coordinator (xem backend/src/agents/
mail_write.py), không phải của 2 tool soạn/gửi ở trên."""
import json

from server import mcp
from odoo_call import odoo
from helpers import envelope


@mcp.tool()
def preview_template_email(template_name: str, res_model: str, ref: str) -> str:
    """
    Soạn (nhưng CHƯA gửi) một mail từ template Odoo có sẵn cho MỘT bản ghi
    cụ thể. LƯU Ý: bước này TẠO một bản ghi mail.mail nháp thật trong Odoo
    (Odoo không cho render template mà không tạo bản ghi qua XML-RPC) —
    KHÔNG phải thao tác đọc thuần. YÊU CẦU XÁC NHẬN từ người dùng trước
    khi gọi send_prepared_email với mail_id trả về.

    Args:
        template_name: Tên chính xác của mail.template, vd "Sales: Order Confirmation".
        res_model: Model của bản ghi nguồn, vd "sale.order".
        ref: Mã bản ghi (field 'name'), vd "S00166".
    """
    tpls = odoo("mail.template", "search_read",
               [[["name", "=", template_name], ["model", "=", res_model]]],
               {"fields": ["id"], "limit": 2})
    if not tpls:
        return json.dumps({"ok": False,
                           "display": f"Không tìm thấy template '{template_name}' cho model '{res_model}'."},
                          ensure_ascii=False)

    recs = odoo(res_model, "search_read", [[["name", "=", ref]]], {"fields": ["id"], "limit": 2})
    if not recs:
        return json.dumps({"ok": False, "display": f"Không tìm thấy bản ghi '{ref}' trong {res_model}."},
                          ensure_ascii=False)
    if len(recs) > 1:
        return json.dumps({"ok": False, "display": f"Có nhiều bản ghi '{ref}'. Vui lòng nêu rõ hơn."},
                          ensure_ascii=False)

    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False})
    rows = odoo("mail.mail", "read", [[mail_id]],
               {"fields": ["subject", "recipient_ids", "email_to"]})
    m = rows[0]

    # Finding 4 (final review 2026-08-07): trả DANH SÁCH người nhận thật, không
    # phải mỗi số lượng — người dùng phải nhìn thấy AI gửi cho ai để cổng xác
    # nhận còn bắt được sai người nhận. recipient_ids là many2many res.partner
    # (cần "read" thêm để lấy name/email — "read" đã whitelist toàn cục theo
    # method, không theo model, nên không cần thêm gì vào security whitelist);
    # email_to là field địa chỉ thô song song, template có thể populate CÁI
    # NÀY thay vì recipient_ids — bỏ sót nó thì đếm ra 0 dù mail VẪN sẽ gửi.
    recipients = []
    partner_ids = m["recipient_ids"] or []
    if partner_ids:
        partners = odoo("res.partner", "read", [partner_ids], {"fields": ["name", "email"]})
        recipients.extend(f"{p['name']} <{p['email'] or '?'}>" for p in partners)
    if m.get("email_to"):
        recipients.append(m["email_to"])

    return json.dumps({"ok": True, "display": f"Đã soạn mail '{m['subject']}', chờ xác nhận gửi.",
                       "mail_id": mail_id, "subject": m["subject"],
                       "recipients": recipients},
                      ensure_ascii=False)


@mcp.tool()
def send_prepared_email(mail_id: int) -> str:
    """
    Gửi thật một mail đã soạn sẵn qua preview_template_email (dùng ĐÚNG
    mail_id đã trả về, không tạo lại). YÊU CẦU XÁC NHẬN từ người dùng
    trước khi gọi.

    Args:
        mail_id: ID bản ghi mail.mail đã soạn (từ preview_template_email).
    """
    odoo("mail.mail", "send", [[mail_id]], {})
    rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["state", "failure_reason", "subject"]})
    m = rows[0]
    if m["state"] == "exception":
        return envelope(False, f"Gửi thất bại: {m['failure_reason'] or 'không rõ lý do'}.",
                        ref=m["subject"], model="mail.mail", res_id=mail_id, state=m["state"])
    return envelope(True, "Đã gửi mail.", ref=m["subject"], model="mail.mail",
                    res_id=mail_id, state=m["state"])


@mcp.tool()
def discard_prepared_email(mail_id: int) -> str:
    """
    Hủy một mail đã soạn qua preview_template_email nhưng người dùng từ
    chối gửi — xóa bản mail.mail nháp. BẮT BUỘC gọi khi từ chối: bản nháp
    nằm ở trạng thái 'outgoing' (hàng đợi gửi), KHÔNG phải trạng thái thụ
    động — Odoo có cron "Mail: Email Queue Manager" chạy định kỳ, tự động
    gửi MỌI bản ghi ở trạng thái này, kể cả bản bị người dùng từ chối nếu
    không chủ động hủy (đã xác nhận thật trên Odoo 2026-08-07: cron đang
    bật, chạy mỗi giờ).

    Args:
        mail_id: ID bản ghi mail.mail cần hủy (từ preview_template_email).
    """
    odoo("mail.mail", "unlink", [[mail_id]], {})
    return envelope(True, "Đã hủy mail nháp.", ref=str(mail_id), model="mail.mail",
                    res_id=mail_id, state="cancelled")
