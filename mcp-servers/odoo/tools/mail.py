"""Tool MCP domain Mail (mail.template / mail.mail) — spec 2026-08-07,
cập nhật spec 2026-08-08 (bản nháp trơ tính).

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

BẢN NHÁP TRƠ TÍNH TỪ LÚC TẠO (spec 2026-08-08, xác minh qua mã nguồn Odoo
thật D:\\Odoo\\server\\odoo\\addons\\mail\\models\\mail_mail.py): send_mail()
mặc định tạo bản ghi ở state='outgoing' — cron "Mail: Email Queue Manager"
của Odoo (chạy mỗi giờ) VÀ mail.mail._send() nội bộ đều chỉ xử lý bản ghi ở
state này (cron lọc cứng theo domain, _send() có
"if mail.state != 'outgoing': continue" — bỏ qua lặng lẽ, không lỗi).
preview_template_email tạo bản ghi TRỰC TIẾP ở state='cancel' qua
email_values parameter của send_mail (giá trị Selection hợp lệ thật, không
phải hack) — bản nháp chưa xác nhận không bao giờ ở trạng thái cron/send()
nhìn thấy. send_prepared_email PHẢI lật lại 'outgoing' NGAY TRƯỚC khi gọi
send() thật (thiếu bước này thì send() sẽ lặng lẽ không làm gì, đúng dòng
nói trên).

discard_prepared_email giờ chỉ còn là DỌN DẸP (xóa bản nháp bị từ chối cho
gọn CSDL), KHÔNG còn là cơ chế an toàn — bản nháp đã trơ tính sẵn kể từ lúc
tạo nên thất bại của discard không còn kéo theo rủi ro gửi ngoài ý muốn."""
import json
import os

from server import mcp
from odoo_call import odoo
from helpers import envelope
import role_scope


@mcp.tool()
def preview_template_email(template_name: str, res_model: str, ref: str) -> str:
    """
    Soạn (nhưng CHƯA gửi) một mail từ template Odoo có sẵn cho MỘT bản ghi
    cụ thể. LƯU Ý: bước này TẠO một bản ghi mail.mail nháp thật trong Odoo
    (Odoo không cho render template mà không tạo bản ghi qua XML-RPC) —
    KHÔNG phải thao tác đọc thuần. Bản ghi được tạo TRỰC TIẾP ở
    state='cancel' (trơ tính với cron gửi mail của Odoo — xem docstring
    module) cho tới khi send_prepared_email được gọi. YÊU CẦU XÁC NHẬN từ
    người dùng trước khi gọi send_prepared_email với mail_id trả về.

    Args:
        template_name: Tên chính xác của mail.template, vd "Sales: Order Confirmation".
        res_model: Model của bản ghi nguồn, vd "sale.order".
        ref: Mã bản ghi (field 'name'), vd "S00166".
    """
    # Cưỡng chế phạm vi vai TRONG tiến trình MCP — chặn cả đường gọi thẳng
    # cổng này, thứ mà bộ lọc tool ở backend không với tới (spec 2026-08-12
    # §4.2). KHÔNG nêu danh sách được phép trong câu từ chối: không rò cấu
    # hình vai cho người gọi trực tiếp.
    if not role_scope.allowed(template_name,
                              os.environ.get(role_scope.ALLOWED_TEMPLATES_ENV)):
        return json.dumps(
            {"ok": False,
             "display": f"Template '{template_name}' không thuộc phạm vi của vai này."},
            ensure_ascii=False)

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

    # Bản nháp trơ tính (spec 2026-08-08, sửa sau final review — tạo TRỰC
    # TIẾP ở state='cancel' qua email_values, KHÔNG phải create rồi write()
    # riêng): send_mail's email_values được merge thẳng vào create() values
    # của mail.mail (xác minh qua mã nguồn Odoo mail_template.py + probe
    # thật: gọi send_mail với email_values={"state": "cancel"} tạo ra bản
    # ghi đã ở state='cancel' ngay từ create, đọc lại xác nhận). Một lệnh
    # gọi Odoo DUY NHẤT, không còn khoảng hở giữa tạo và chuyển state — nếu
    # lệnh write() riêng (thiết kế cũ) thất bại giữa 2 bước, bản nháp sẽ mồ
    # côi ở state mặc định 'outgoing', đúng lỗi mà toàn bộ nhánh này tồn tại
    # để ngăn. 'cancel' là giá trị Selection hợp lệ thật trong Odoo (không
    # phải hack) — cron "Mail: Email Queue Manager" lọc cứng theo
    # state='outgoing', và mail.mail._send() nội bộ có
    # "if mail.state != 'outgoing': continue" — bỏ qua LẶNG LẼ mọi state
    # khác, không lỗi. Bản nháp chưa xác nhận vì vậy không bao giờ ở trạng
    # thái mà cron/send() nhìn thấy, cho tới khi send_prepared_email chủ
    # động lật lại 'outgoing'.
    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False, "email_values": {"state": "cancel"}})
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
    mail_id đã trả về, không tạo lại). Lật state từ 'cancel' (trơ tính)
    sang 'outgoing' ngay trước khi gọi send() — xem docstring module.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        mail_id: ID bản ghi mail.mail đã soạn (từ preview_template_email).
    """
    # Cửa sau của §4.2: tool này chỉ nhận mail_id, nên ai gọi thẳng cổng MCP
    # có thể lấy BẤT KỲ bản nháp mail.mail nào đang có và gửi đi. Đối chiếu
    # model nguồn của bản ghi với phạm vi vai (spec 2026-08-12 §4.3).
    #
    # GIỚI HẠN ĐÃ BIẾT: hai vai cùng res_model thì kiểm này không tách được.
    # Hiện không xảy ra (stock.picking chỉ của kho, account.move chỉ của kế
    # toán) — đừng tưởng nó mạnh hơn thực tế.
    pham_vi = os.environ.get(role_scope.ALLOWED_MAIL_MODELS_ENV)
    if role_scope.parse(pham_vi):
        rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["model"]})
        if not rows:
            return envelope(False, f"Không tìm thấy mail nháp id={mail_id}.")
        model_nguon = rows[0].get("model") or ""
        if not role_scope.allowed(model_nguon, pham_vi):
            return envelope(False, "Mail này không thuộc phạm vi của vai hiện tại.")

    # Bắt buộc lật lại 'outgoing' TRƯỚC send() — thiếu bước này, send() nội
    # bộ của Odoo sẽ lặng lẽ bỏ qua bản ghi (state đang là 'cancel' từ
    # preview_template_email), không gửi, không báo lỗi. Xem spec 2026-08-08.
    odoo("mail.mail", "write", [[mail_id], {"state": "outgoing"}], {})
    odoo("mail.mail", "send", [[mail_id]], {})
    rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["state", "failure_reason", "subject"]})
    if not rows:
        # Đo thật 2026-08-08 (live-verify trước merge): template "Sales:
        # Order Confirmation" có auto_delete=True — Odoo TỰ XÓA bản ghi
        # mail.mail ngay sau khi gửi THÀNH CÔNG (hành vi mặc định của Odoo
        # cho mail.mail.auto_delete, không phải lỗi). Không còn bản ghi để
        # đọc lại là DẤU HIỆU GỬI THÀNH CÔNG, không phải trường hợp lỗi —
        # gửi thất bại (SMTP lỗi) thì Odoo GIỮ LẠI bản ghi ở state='exception'
        # (đã kiểm chứng thật trước khi có SMTP: state='exception' vẫn đọc
        # được), auto_delete chỉ áp dụng cho nhánh thành công.
        return envelope(True, "Đã gửi mail.", ref=str(mail_id), model="mail.mail",
                        res_id=mail_id, state="sent")
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
    chối gửi — xóa bản mail.mail nháp. Bản nháp đã trơ tính với cron gửi
    mail của Odoo ngay từ lúc tạo (state='cancel' — xem docstring module),
    nên gọi tool này ở nhánh từ chối chỉ là DỌN DẸP (tránh tích lũy bản
    nháp rác trong Odoo theo thời gian) — không còn là cơ chế an toàn bắt
    buộc, thất bại của nó không còn kéo theo rủi ro gửi ngoài ý muốn.

    Args:
        mail_id: ID bản ghi mail.mail cần hủy (từ preview_template_email).
    """
    odoo("mail.mail", "unlink", [[mail_id]], {})
    return envelope(True, "Đã hủy mail nháp.", ref=str(mail_id), model="mail.mail",
                    res_id=mail_id, state="deleted")
