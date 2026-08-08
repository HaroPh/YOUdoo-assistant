# Bản nháp mail "trơ tính" từ lúc tạo — đóng 2 rủi ro còn lại

**Ngày:** 2026-08-08
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

Plan `2026-08-07-order-confirmation-email` (đã merge) để lại 2 rủi ro đã
biết, ghi rõ trong `mail_write.py`'s docstring nhưng KHÔNG sửa triệt để:

1. **Hội thoại bị bỏ dở** (người dùng không xác nhận cũng không từ chối,
   không gửi thêm tin nhắn nào) → bản `mail.mail` nháp nằm ở trạng thái
   `outgoing` (hàng đợi gửi) → cron "Mail: Email Queue Manager" của Odoo
   (chạy mỗi giờ) tự động gửi nó, bất kể người dùng chưa từng xác nhận —
   "im lặng = gửi", sai default cho hành động không thể thu hồi.
2. **Hủy khi tắt kill-switch giữa lúc chờ xác nhận gần như chắc chắn thất
   bại**: `discard_prepared_email` gọi `unlink`, bị chặn bởi CHÍNH cái
   gate vừa tắt (mọi write non-"read" đều cần `write_actions_enabled()`).
   Plan trước chỉ sửa THÔNG BÁO cho trung thực, không sửa được vấn đề gốc.

## 2. Xác minh kỹ thuật (đọc trực tiếp mã nguồn Odoo, không suy đoán)

`D:\Odoo\server\odoo\addons\mail\models\mail_mail.py`:

- **Cron chỉ xử lý `state = 'outgoing'`** (`process_email_queue`, dòng
  206-212: domain cứng `('state', '=', 'outgoing')`). Bản ghi ở state
  khác **hoàn toàn vô hình** với cron.
- **`_send()` tự bỏ qua bản ghi không phải `'outgoing'`** (dòng 784:
  `if mail.state != 'outgoing': continue`) — **không gửi, không báo lỗi**,
  chỉ lặng lẽ skip.
- **`'cancel'`** là giá trị hợp lệ thật trong `state` Selection field
  (dòng 74: `('cancel', 'Cancelled')`) — không phải hack.

**Kết luận:** nếu bản nháp được chuyển sang `state='cancel'` ngay sau khi
tạo, nó trơ tính hoàn toàn với cron VÀ với mọi lệnh gọi `send()` tình cờ —
cho tới khi có ai đó chủ động lật lại `'outgoing'`. Đây không phải giảm
thiểu rủi ro, mà **đóng triệt để cả 2 vấn đề trên cùng lúc**.

## 3. Thiết kế

Sửa 2 hàm trong `mcp-servers/odoo/tools/mail.py`:

**`preview_template_email`** — ngay sau khi `send_mail(force_send=False)`
tạo bản nháp (mặc định ở `state='outgoing'`), thêm một lệnh `write()` đổi
`state` thành `'cancel'`.

**`send_prepared_email`** — TRƯỚC khi gọi `mail.mail.send(...)`, thêm một
lệnh `write()` đổi `state` từ `'cancel'` lại thành `'outgoing'` (bắt buộc —
thiếu bước này thì `send()` sẽ lặng lẽ không làm gì, theo đúng dòng 784 đã
trích ở trên).

Không cần whitelist bảo mật mới — `write` đã có sẵn trong
`ODOO_METHOD_OPERATION_MAP` từ trước plan `order-confirmation-email`.

**`discard_prepared_email` giữ nguyên** (vẫn hữu ích để dọn rác — bản nháp
bị từ chối tích lũy theo thời gian nếu không dọn), nhưng **không còn là cơ
chế an toàn** — thất bại của nó giờ vô hại. Bỏ đoạn cảnh báo "⚠️ có thể
vẫn bị gửi..." đã thêm ở `mail_write.py` (plan trước, fix wave cuối) vì
không còn đúng: bản nháp không bao giờ ở trạng thái cron nhìn thấy trừ
đúng khoảnh khắc đang gửi thật.

### Cửa sổ rủi ro còn lại (chấp nhận, không phải bug)

Giữa lúc `send_prepared_email` lật `state` sang `'outgoing'` và lúc
`send()` thực sự hoàn tất, bản ghi có tồn tại ở trạng thái cron-nhìn-thấy
— nhưng đây là một lệnh gọi đồng bộ, gần như tức thời, VÀ chỉ xảy ra SAU
khi người dùng đã xác nhận (không phải trong lúc chờ). Cửa sổ này nhỏ hơn
hàng nghìn lần so với "chờ người dùng trả lời" (có thể vô hạn) — chấp
nhận được, không cần xử lý thêm.

## 4. Cổng nghiệm thu

Không cần unit test mới cho `mcp-servers/odoo/tools/mail.py` (đúng quy
ước đã có — xem plan `order-confirmation-email` Task 2, verify qua
live-verify). Live-verify TRƯỚC merge (đúng quy trình mới):

1. Soạn mail xem trước (`preview_template_email`) qua 1 đơn thật → đọc
   trực tiếp `mail.mail.state` qua Odoo thật, ĐẠT khi = `'cancel'` (không
   phải `'outgoing'`).
2. Trong lúc bản nháp đang ở `'cancel'`, gọi thẳng
   `process_email_queue` (hoặc đợi/mô phỏng cron) — ĐẠT khi bản nháp
   KHÔNG bị gửi (chứng minh trực tiếp bằng đọc `state` không đổi).
3. Xác nhận gửi thật → đọc `mail.mail.state` (hoặc xác nhận record đã bị
   xóa nếu `auto_delete=True`, như hành vi đã biết) → ĐẠT khi gửi thành
   công y hệt plan trước (không hồi quy).
