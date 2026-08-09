# Live-verify — 3 điểm nối gửi mail mới (2026-08-09)

**Môi trường:** backend (:8002) + mcp-odoo (:8003) khởi động lại thủ công,
trỏ vào code worktree `mail-trigger-points` (commit `8e56702`, sau Task
1+2), KHÔNG phải `main`. Gọi qua `/v1/chat/completions` thật, resend toàn
bộ lịch sử mỗi lượt, KHÔNG dùng `session_id` — khớp shape client Open WebUI
thật.

## Tiêu chí 1 — `send_invoice_email` trên hóa đơn ĐÃ phát hành

`"Gửi mail hóa đơn INV/2026/00030 cho khách"`:

```
Mail hóa đơn INV/2026/00030:
  Tới: Acme Corporation <phamhao14170@gmail.com>
  Tiêu đề: My Company (San Francisco) Hóa đơn (Mã INV/2026/00030)
```

`mail.mail` id 68 → **`state: 'cancel'`** (cơ chế bản-nháp-trơ-tính hoạt
động đúng trên `account.move`, model CHƯA TỪNG được đo trước plan này).
Xác nhận `"có"` → `"Đã gửi mail."`, bản ghi biến mất (auto_delete sau gửi
thành công).

**ĐẠT** — nhưng phát hiện một thiếu sót thật, xem mục "Sự cố" bên dưới.

## Tiêu chí 2 — `send_rfq_email` gửi tới NHÀ CUNG CẤP

Đây là điểm rủi ro cao nhất của plan: vai trò người nhận khác hẳn 3 ca kia.
Cố ý chọn P00080 của **Gemini Furniture** — đối tác KHÁC hẳn Acme
Corporation (khách hàng ở 3 ca còn lại) — để phép đo có tính kết luận,
không thể trùng khớp ngẫu nhiên.

```
Mail yêu cầu báo giá P00080:
  Tới: Gemini Furniture <john.b@tech.info>
  Tiêu đề: My Company (San Francisco) Đơn hàng (Mã P00080)
```

Người nhận ĐÚNG là nhà cung cấp, không phải khách hàng. `mail.mail` id 69 →
**`state: 'cancel'`** (trơ tính đúng trên `purchase.order`, model thứ hai
chưa từng được đo). Trả lời `"không"` → `"Đã hủy gửi mail yêu cầu báo
giá."` (câu từ chối dựng đúng từ `label` mới), đọc lại id 69 → **rỗng**,
bản nháp đã bị xóa thật.

Ca này CỐ Ý chọn nhánh từ chối (đúng như plan quy định): địa chỉ nhà cung
cấp là dữ liệu demo Odoo trỏ ra domain ngoài (`tech.info`) không thuộc
quyền kiểm soát — không gửi thật ra ngoài.

**ĐẠT.**

## Tiêu chí 3 — `send_quotation_email` trên báo giá nháp

`"Gửi mail báo giá S00161 cho khách"`:

```
Mail báo giá S00161:
  Tới: Acme Corporation <phamhao14170@gmail.com>
  Tiêu đề: My Company (San Francisco) Báo giá (Ref S00161)
```

Tiêu đề là **"Báo giá"**, KHÁC hẳn **"Đơn hàng"** của
`send_order_confirmation_email` trên cùng model `sale.order` — bằng chứng
trực tiếp rằng `template_name` trong config thật sự quyết định template
được dùng, không phải cả 4 coordinator cùng gọi một template (đúng lớp lỗi
mà test `test_moi_cfg_mail_co_template_va_model_rieng_biet` khóa ở mức
unit, giờ được xác nhận ở mức thật).

`mail.mail` id 70 → **`state: 'cancel'`**. Xác nhận `"có"` → `"Đã gửi
mail."`, bản ghi biến mất.

**ĐẠT.**

## Tiêu chí 4 — `send_order_confirmation_email` KHÔNG hồi quy

Đường đã live-verify ở 2 plan trước, giờ chạy qua factory mới:

```
Mail xác nhận đơn S00171:
  Tới: Acme Corporation <phamhao14170@gmail.com>
  Tiêu đề: My Company (San Francisco) Đơn hàng (Mã S00171)
```

Chuỗi `"Mail xác nhận đơn S00171:"` **giống hệt từng ký tự** bản trước
refactor — xác nhận ở môi trường THẬT rằng phép dẫn xuất
`cfg.label.capitalize()` (Task 1) bảo toàn nguyên văn chuỗi hardcode cũ,
không chỉ đúng trên lý thuyết đọc code. `mail.mail` id 76 →
`state: 'cancel'`, 1 đính kèm PDF. Xác nhận `"có"` → `"Đã gửi mail."`.

**ĐẠT.**

## Sự cố phát hiện trong lúc live-verify: mail hóa đơn KHÔNG có PDF đính kèm

Người dùng tự kiểm tra hộp thư sau Tiêu chí 1 và báo: mail hóa đơn
`INV/2026/00030` nhận được **không đính kèm file nào**. Điều tra:

**KHÔNG phải lỗi code.** Đo đối chứng — cùng một đường code, gọi
`send_mail` trực tiếp qua XML-RPC cho cả 4 template, đọc `attachment_ids`
của bản `mail.mail` tạo ra:

| Template | Đính kèm |
|---|---|
| `Invoice: Sending` | **0** |
| `Sales: Order Confirmation` | 1 — `Đơn hàng - S00171.pdf` |
| `Sales: Send Quotation` | 1 — `Báo giá - S00161.pdf` |
| `Purchase: Request For Quotation` | 1 — `Yêu cầu Báo giá - P00080.pdf` |

Nguyên nhân gốc: template `Invoice: Sending` có `report_template_ids` **rỗng**,
trong khi 3 template kia đều có report gắn sẵn (313 cho sale, 475 cho
purchase). Từ Odoo 17+, việc đính PDF hóa đơn chuyển vào wizard riêng
`account.move.send` (wizard tự sinh PDF và lưu vào
`invoice_pdf_report_id`), nên bản thân template chỉ còn cung cấp phần
NỘI DUNG. Gọi thẳng `mail.template.send_mail` — như code này làm — vì vậy
nhận đúng những gì template khai báo: có body, không PDF.

**Rủi ro đính kèm trùng đã được loại trừ bằng bằng chứng, không phải phỏng
đoán:** đọc mã nguồn Odoo (`account/models/account_move_send.py:266-272`),
wizard gốc CHỦ ĐỘNG trừ report hóa đơn ra khỏi danh sách của template —
`extra_mail_templates = mail_template.report_template_ids - invoice_template`
với `invoice_template = pdf_report | self.env.ref('account.account_invoices')`
— kèm comment nói rõ mục đích là "to avoid duplicated placeholders". Và
`account.account_invoices` giải ra đúng report **229**, cũng chính là mặc
định của `_get_default_pdf_report_id`. Nghĩa là gắn report 229 vào template
là cấu hình Odoo đã lường trước và tự khử trùng lặp.

**Xử lý (người dùng chọn):** gắn report 229 `Invoice PDF`
(`account.report_invoice_with_payments`, có thông tin thanh toán — đúng mặc
định của Odoo) vào `report_template_ids` của template `Invoice: Sending`.
Đây là thay đổi CẤU HÌNH ODOO, không phải thay đổi code trong repo này.

**Đo lại sau khi sửa** (`INV/2026/00029`, qua agent thật):
`state: 'cancel'` (cơ chế trơ tính KHÔNG bị ảnh hưởng) và
**`attachment_ids` = 1 → `INV/2026/00029.pdf`, `application/pdf`, 31.515
bytes**. Gửi thật thành công.

**Ghi nhận cho tương lai:** nếu Odoo được cài lại/khôi phục từ bản sao lưu
cũ, cấu hình này sẽ mất và mail hóa đơn lại thiếu PDF trong im lặng —
không có test tự động nào phát hiện được (đây là dữ liệu Odoo, không phải
code repo). Chỉ có kiểm tra hộp thư thật mới bắt được, đúng như lần này.

## Kết luận cổng đánh giá

**Cả 4 tiêu chí ĐẠT, đo TRƯỚC khi merge, trên code worktree thật.** Ngoài
ra bắt được một thiếu sót thật (mail hóa đơn không PDF) mà không một unit
test nào có thể phát hiện — nhờ người dùng kiểm tra hộp thư thật — và đã
sửa + đo lại xác nhận.

Cơ chế bản-nháp-trơ-tính (`state='cancel'` từ lúc tạo) được xác nhận hoạt
động đúng trên CẢ HAI model mới `account.move` và `purchase.order`, không
chỉ `sale.order` như các plan trước đã đo.
