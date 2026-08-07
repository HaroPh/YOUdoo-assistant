# Gửi mail xác nhận đơn hàng thật — cơ chế gửi mail lõi + 1 điểm nối

**Ngày:** 2026-08-07
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

Ý ban đầu của người dùng: agent nên có thể **gửi mail thật** (yêu cầu báo
giá, xác nhận đơn, bản nháp...) cho khách hàng/nhà cung cấp, tận dụng
`mail.template` sẵn có của Odoo thay vì tự soạn nội dung. Hiện hệ thống
**hoàn toàn chưa có** khả năng gửi mail — không có tool nào trong
`mcp-servers/odoo/tools/`, không có method liên quan mail nào trong
whitelist bảo mật (`security.py`).

Toàn bộ tính năng "gửi mail" thực ra là **nhiều điểm nối độc lập** (RFQ→NCC,
báo giá nháp→KH, xác nhận đơn→KH, hóa đơn→KH...), mỗi điểm dùng một
`mail.template` khác nhau nhưng chạy qua **cùng một cơ chế lõi**. Spec này
**cố ý thu hẹp** phạm vi xuống: xây cơ chế lõi + đúng **một** điểm nối
(`confirm_sale_order` → mail xác nhận đơn cho khách), để chứng minh cơ chế
hoạt động đầu-cuối thật trước khi nhân rộng sang các điểm còn lại ở plan
sau (đúng cách dự án này vẫn làm — mọi plan trước giờ đều nhỏ, một mục
tiêu).

### 1.1. Hai giới hạn hạ tầng đã đo thật và đã xử lý trong phiên viết spec này

- **SMTP:** `ir.mail_server` rỗng (đo qua XML-RPC 2026-08-07) — Odoo chưa
  có server gửi mail thật nào. Người dùng sẽ tự cấu hình **trước khi
  live-verify**; không chặn thiết kế/xây dựng.
- **wkhtmltopdf:** template `sale.order`/`purchase.order` đều gắn sẵn báo
  cáo PDF (`report_template_ids`), cần wkhtmltopdf để tạo PDF đính kèm —
  ban đầu thiếu, đã cài + thêm vào **PATH hệ thống (Machine, không phải
  User)** + restart Windows Service `odoo-server-19.0` (chạy dưới account
  `LocalSystem`, chỉ đọc Machine PATH). Đã xác nhận hoạt động thật: gọi
  `mail.template.send_mail(17, 166, force_send=False)` tạo thành công
  `mail.mail` id=59 kèm `attachment_ids: [1026]` (PDF thật), đã dọn bản
  test này.

## 2. Phạm vi

**Có trong phạm vi:**
- 2 method mới trong whitelist bảo mật (`security.py`):
  `send_mail` → `"create"`, `send` (trên `mail.mail`) → `"write"`.
- 2 tool MCP **dùng chung** cho mọi điểm nối tương lai (không riêng theo
  domain — xem §3.1 lý do): `preview_template_email`,
  `send_prepared_email`.
- 1 coordinator agent cho **đúng một** điểm nối: `confirm_sale_order` →
  mail xác nhận đơn (`mail.template` "Sales: Order Confirmation").
- Đăng ký vào `WRITE_COORDINATORS` + `CONFIRM_IN_CHAIN` (frozenset có sẵn
  từ `2026-08-06-invoice-confirm-summary`). **Không** đăng ký vào
  `NEXT_STEPS` — xem §3.4 lý do (xung đột thật với bước "Giao hàng" có
  sẵn của `confirm_sale_order`).

**Cố ý KHÔNG làm** (để dành plan sau, tái dùng cơ chế lõi vừa xây):
- Các điểm nối khác (`create_rfq`→NCC, `create_quotation`→KH,
  `post_invoice`→KH...).
- Cấu hình SMTP thật (việc của người dùng, ngoài phạm vi code).
- Không thêm cờ môi trường bật/tắt hành vi mới.

## 3. Kiến trúc

### 3.1. Tại sao 2 tool MCP dùng chung, không riêng theo domain

Cơ chế gốc của Odoo (`mail.template.send_mail(template_id, res_id,
force_send=...)` + `mail.mail.send([mail_id])`) đã là **hàm chung**, hoạt
động y hệt bất kể model nguồn là `sale.order`, `purchase.order` hay
`account.move` — không có logic nghiệp vụ riêng theo domain (khác hẳn
`confirm_sale_order`, nơi có state-check + `action_confirm` là logic
riêng của sale). Tạo tool riêng từng domain sẽ trùng lặp không cần thiết.
LLM **không** tự chọn template — mỗi coordinator hardcode template của
chính nó (xem §3.3), tool chỉ là lớp thực thi.

### 3.2. Whitelist bảo mật — `mcp-servers/odoo/security.py`

Thêm vào `ODOO_METHOD_OPERATION_MAP`:

```python
"send_mail": "create",   # mail.template.send_mail — tạo bản mail.mail
"send": "write",         # mail.mail.send — gửi thật (hoặc set state=exception nếu SMTP lỗi)
```

> **Lưu ý bảo mật:** `"send"` là tên method khá chung — nếu sau này có
> model khác cũng có method `send` với ý nghĩa khác, whitelist này áp
> dụng cho MỌI model gọi `execute_kw(model, "send", ...)`, không chỉ
> `mail.mail`. Rủi ro thấp (đã kiểm tra: không MCP tool nào khác trong
> repo gọi method tên `send` trên model khác), nhưng cần biết khi review.

### 3.3. 2 tool MCP — `mcp-servers/odoo/tools/mail.py` (file mới)

```python
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
        return envelope(False, f"Không tìm thấy template '{template_name}' cho model '{res_model}'.")
    recs = odoo(res_model, "search_read", [[["name", "=", ref]]], {"fields": ["id"], "limit": 2})
    if not recs:
        return envelope(False, f"Không tìm thấy bản ghi '{ref}' trong {res_model}.")
    if len(recs) > 1:
        return envelope(False, f"Có nhiều bản ghi '{ref}'. Vui lòng nêu rõ hơn.")

    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False})
    rows = odoo("mail.mail", "read", [[mail_id]],
               {"fields": ["subject", "recipient_ids", "body_html"]})
    m = rows[0]
    return envelope(True, f"Đã soạn mail '{m['subject']}', chờ xác nhận gửi.",
                    mail_id=mail_id, subject=m["subject"],
                    recipient_ids=m["recipient_ids"], body_html=m["body_html"])


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
    rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["state", "failure_reason"]})
    m = rows[0]
    if m["state"] == "exception":
        return envelope(False, f"Gửi thất bại: {m['failure_reason'] or 'không rõ lý do'}.",
                        mail_id=mail_id, state=m["state"])
    return envelope(True, "Đã gửi mail.", mail_id=mail_id, state=m["state"])
```

Đăng ký cả hai vào `server.py` (theo đúng cách các tool khác đã đăng ký —
xem file để khớp pattern chính xác lúc viết plan).

### 3.4. Coordinator agent — `backend/src/agents/mail_write.py` (file mới)

Theo đúng khuôn các coordinator khác (`invoice_write.py`): resolve →
render → `_interrupt` → gọi tool. Khác biệt duy nhất: **"render" ở đây là
gọi `preview_template_email`** (một write thật, xem §1.1 rationale đã
duyệt), không phải một hàm đọc thuần.

```python
def make_send_order_confirmation_email_node(tools):
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_node(state):
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        order_ref = str(args.get("order_ref") or "").strip()
        if not order_ref:
            return _msg("Bạn cần cho biết mã đơn bán cần gửi mail xác nhận.")

        preview_tool = by_name.get("preview_template_email")
        result = await preview_tool.ainvoke({
            "template_name": "Sales: Order Confirmation",
            "res_model": "sale.order", "ref": order_ref})
        display, env = parse_write_result(result)
        if not env or env.get("status") != "success":
            return _msg(display)
        data = env.get("data") or {}
        mail_id = data.get("mail_id")

        preview_text = (f"Mail xác nhận đơn {order_ref}:\n"
                        f"  Tới: {len(data.get('recipient_ids') or [])} người nhận\n"
                        f"  Tiêu đề: {data.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy gửi mail xác nhận đơn.")

        send_tool = by_name.get("send_prepared_email")
        try:
            result = await send_tool.ainvoke({"mail_id": mail_id})
        except Exception as e:
            return _msg(f"Lỗi khi gửi mail: {e}")
        return _finish("send_order_confirmation_email", result)

    return send_order_confirmation_email_node
```

Đăng ký (`write_registry.py`):

```python
"send_order_confirmation_email": Spec(
    "send_order_confirmation_email",
    lambda llm, tools: make_send_order_confirmation_email_node(tools)),
```

Thêm vào `CONFIRM_IN_CHAIN` (đã có sẵn từ plan trước):
```python
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment",
                              "send_order_confirmation_email"})
```

**KHÔNG đăng ký vào `NEXT_STEPS`.** `confirm_sale_order` **đã có** một
`NextStep` trỏ tới `"deliver_order"` (`write_registry.py` hiện tại) —
`NEXT_STEPS` là `dict`, mỗi tool chỉ có **một** bước kế tiếp tuyến tính.
Thêm một dòng cho `"send_order_confirmation_email"` sẽ **ghi đè** bước
"Giao hàng" hiện có, phá vỡ chuỗi bán hàng
(`create_quotation → confirm_sale_order → deliver_order → ...`) đang
hoạt động.

**Quyết định (người dùng, 2026-08-07):** gửi mail xác nhận **không** tự
động nối chuỗi sau `confirm_sale_order`. Người dùng tự yêu cầu riêng
("gửi mail xác nhận đơn S00166 cho khách") sau khi đơn đã xác nhận — vẫn
đăng ký đầy đủ vào `WRITE_COORDINATORS` + `CONFIRM_IN_CHAIN` (nên nếu
được gọi TRONG một chuỗi khai báo tường minh khác sau này, nó vẫn dừng
hỏi lại đúng cách), chỉ không có mặt trong `NEXT_STEPS` — không đụng chuỗi
giao hàng có sẵn.

## 4. Rủi ro và cách xử lý

### 4.1. "Xem trước" là một write thật (đã duyệt ở §1.1 flow, xem thêm)

Người dùng đã xác nhận: bản `mail.mail` nháp khi bị từ chối **không bị
dọn** — khớp cách các coordinator khác xử lý draft bị từ chối (đơn/hóa đơn
nháp bị từ chối cũng không bị xóa). Hệ quả chấp nhận: Odoo sẽ tích lũy các
bản `mail.mail` nháp không bao giờ gửi theo thời gian — không phải lỗi,
chỉ là rác vô hại (không đụng SMTP).

### 4.2. Mở whitelist bảo mật — bề mặt ghi mới, cần review kỹ

`send`/`send_mail` mới thêm vào `ODOO_METHOD_OPERATION_MAP`. Đây là file
core bảo mật, thay đổi cần review cẩn thận hơn các tool thường (xem lưu ý
tên method chung ở §3.2).

### 4.3. Xung đột `NEXT_STEPS["confirm_sale_order"]` — đã giải quyết (§3.4)

Quyết định: không đăng ký vào `NEXT_STEPS`, giữ nguyên chuỗi giao hàng có
sẵn. Gửi mail xác nhận là hành động người dùng tự yêu cầu riêng.

### 4.4. SMTP chưa cấu hình — chặn live-verify tiêu chí "gửi thành công", không chặn build

Live-verify §5 tiêu chí 1-2 chạy được ngay (không cần SMTP). Tiêu chí 3
(gửi thật) cần SMTP đã cấu hình — nếu tới lúc live-verify vẫn chưa có,
ghi rõ KHÔNG ĐẠT thay vì suy đoán, theo đúng nguyên tắc "không tô hồng"
của dự án.

## 5. Cổng nghiệm thu

1. **Soạn mail xem trước, gọi trực tiếp.** Xác nhận đơn bán thật (chuỗi
   `create_quotation → confirm_sale_order`), rồi **tự yêu cầu riêng**
   "gửi mail xác nhận đơn [mã] cho khách" → phải hiện bản xem trước (tiêu
   đề + số người nhận) trước khi hỏi xác nhận, **không** tự động gửi,
   **không** tự động chạy nối tiếp `deliver_order`.
2. **Từ chối không gửi.** Trả lời "không" ở bước trên → xác nhận qua Odoo
   thật: `mail.mail` vẫn ở trạng thái chưa gửi (không bị `send()`).
3. **Gửi thật (cần SMTP đã cấu hình).** Trả lời "có" → xác nhận qua Odoo
   thật: `mail.mail.state` chuyển sang trạng thái đã gửi (không phải
   `exception`), và (nếu có quyền truy cập hộp mail nhận) khách hàng thật
   sự nhận được mail.
