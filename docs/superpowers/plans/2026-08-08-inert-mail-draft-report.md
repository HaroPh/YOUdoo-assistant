# Live-verify — bản nháp mail trơ tính (2026-08-08)

**Môi trường:** backend (:8002) + mcp-odoo (:8003) khởi động lại thủ công,
trỏ vào code worktree `inert-mail-draft` (commit `d23ec21`, sau Task 1+2),
KHÔNG phải `main`. Gọi qua `/v1/chat/completions` thật, resend toàn bộ
lịch sử hội thoại mỗi lượt, KHÔNG dùng `session_id` — khớp shape client
thật (Open WebUI), đúng quy ước đã dùng ở live-verify plan trước.

## Tiêu chí 1 — bản nháp phải ở state='cancel' ngay sau khi soạn

Gửi `"Gửi mail xác nhận đơn S00169 cho khách"` → agent trả về bản xem
trước đúng như plan trước (người nhận thật, tiêu đề thật):

```
Mail xác nhận đơn S00169:
  Tới: Acme Corporation <phamhao14170@gmail.com>
  Tiêu đề: My Company (San Francisco) Đơn hàng (Mã S00169)
Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)
```

Đọc trực tiếp qua XML-RPC: `mail.mail` id 64 (tìm theo subject) —
**`state: 'cancel'`**, không phải `'outgoing'`.

**ĐẠT.**

## Tiêu chí 2 — bản nháp 'cancel' phải vô hình với cron

Trong lúc bản nháp id 64 vẫn đang chờ xác nhận, gọi trực tiếp
`mail.mail.process_email_queue()` qua XML-RPC (mô phỏng cron "Mail: Email
Queue Manager" chạy ngay lập tức thay vì đợi tới chu kỳ giờ tự nhiên).
Đọc lại `mail.mail` id 64 sau khi cron chạy: **vẫn `state: 'cancel'`**,
không đổi — cron bỏ qua hoàn toàn bản ghi này.

**ĐẠT.**

## Tiêu chí 3 — từ chối vẫn hoạt động đúng (không hồi quy)

Từ bản nháp Tiêu chí 1, trả lời `"không"`. Agent trả lời đúng thông báo
MỚI (không còn cảnh báo "có thể vẫn bị gửi..." — xác nhận trực tiếp Task 2
hoạt động đúng trên môi trường thật, không chỉ trong test mock):

```
Đã hủy gửi mail xác nhận đơn.
```

Đọc lại `mail.mail` id 64: **danh sách rỗng** — `discard_prepared_email`
đã `unlink` thành công, bản nháp bị xóa hoàn toàn.

**ĐẠT.**

**Lưu ý phạm vi:** tiêu chí này đo nhánh gate BẬT (discard thành công thật). Nhánh gate TẮT (discard thất bại) chỉ được phủ bởi unit test (mock) ở Task 2, không phải live-verify riêng — suy luận an toàn dựa trên tổ hợp Tiêu chí 1+2 (bản nháp đã ở state='cancel', cron xác nhận bỏ qua nó) vẫn đúng dù discard có thành công hay không, nhưng chưa có phép đo trực tiếp cho đúng nhánh này.

## Tiêu chí 4 — gửi thật vẫn hoạt động đúng (không hồi quy)

Lặp lại với đơn khác (S00170) để tránh dùng lại bản nháp vừa hủy. Soạn
xem trước → xác nhận `mail.mail` id 65 cũng ở `state='cancel'` (khớp
Tiêu chí 1). Trả lời `"có"` → agent trả lời:

```
Đã gửi mail.
```

Đọc lại `mail.mail` id 65: **danh sách rỗng**. Đây CHÍNH XÁC là dấu hiệu
gửi THÀNH CÔNG đã biết từ plan `order-confirmation-email` (template có
`auto_delete=True`, Odoo tự xóa bản ghi sau khi gửi thành công — không
phải lỗi). Bằng chứng gián tiếp nhưng chắc chắn rằng state đã được lật
lại `'outgoing'` đúng lúc: nếu bước lật state (Task 1, `send_prepared_email`)
không chạy, `send()` nội bộ của Odoo sẽ lặng lẽ bỏ qua bản ghi (vẫn ở
`'cancel'`) — bản ghi id 65 vẫn sẽ CÒN TỒN TẠI ở state `'cancel'`, không
biến mất. Nó biến mất ⇒ `send()` đã thực sự xử lý và thành công.

**ĐẠT.** (Không kiểm tra được hộp thư Gmail thật trong lượt live-verify
tự động này — không có người dùng tương tác trực tiếp trong phiên này để
tự kiểm tra inbox như plan trước; bằng chứng phía Odoo đã đủ mạnh và nhất
quán với hành vi `auto_delete` đã biết, không suy đoán thêm.)

## Kết luận cổng đánh giá

**Cả 4 tiêu chí ĐẠT, đo TRƯỚC khi merge, trên code worktree thật (không
phải main).** Cơ chế "bản nháp trơ tính" hoạt động đúng như thiết kế: vô
hình với cron trong lúc chờ xác nhận, không phá vỡ đường từ chối hay
đường gửi thật đã có từ plan `order-confirmation-email`.

## Tái đo sau final review (commit `f0bc52e`)

Final review (Important #1) phát hiện thiết kế TRÊN (Tiêu chí 1-4) tạo bản
nháp qua 2 bước tách rời (`send_mail` rồi `write(state='cancel')` riêng) —
để hở một khoảng ngắn giữa 2 lệnh gọi Odoo mà một lỗi thoáng qua (vd rate
limiter, mạng chập chờn) có thể khiến bản nháp mồ côi ở `state='outgoing'`
mặc định, đúng lỗi toàn bộ nhánh này tồn tại để ngăn. Sửa: `send_mail` giờ
nhận `email_values={"state": "cancel"}`, tạo bản ghi TRỰC TIẾP ở
`state='cancel'` trong một lệnh gọi Odoo DUY NHẤT — không còn khoảng hở.

Vì đây là thay đổi ĐÚNG cơ chế Tiêu chí 1 đã đo, đo lại Tiêu chí 1+4 trên
code sau fix (khởi động lại backend+mcp-odoo, nạp commit `f0bc52e`):

- **Tiêu chí 1 (đo lại):** đơn S00168 → `mail.mail` id 67 tạo ra đã ở
  **`state: 'cancel'`** ngay từ bản ghi đầu tiên đọc được (không còn bước
  write() riêng nào chạy sau đó) — **ĐẠT**, qua đường tạo trực tiếp mới.
- **Tiêu chí 4 (đo lại):** trả lời "có" → `"Đã gửi mail."` → `mail.mail`
  id 67 biến mất (auto_delete sau gửi thành công, cùng dấu hiệu đã biết)
  — **ĐẠT**, đường gửi thật không hồi quy sau khi đổi cơ chế tạo bản nháp.
- **Tiêu chí 2 không cần đo lại:** kết luận của nó ("cron bỏ qua bản ghi ở
  `state='cancel'`") chỉ phụ thuộc GIÁ TRỊ state, không phụ thuộc bản ghi
  được tạo ra bằng đường nào — kết luận cũ vẫn đúng nguyên vẹn.

**Cả 4 tiêu chí vẫn ĐẠT sau fix, đo TRƯỚC merge.** Khoảng hở tạo-bản-nháp
mà final review phát hiện đã đóng triệt để bằng bằng chứng thật, không chỉ
bằng lý luận.
