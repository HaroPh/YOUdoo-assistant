# Live-verify — cưỡng chế vai cho tầng mail (2026-08-12)

**Môi trường:** worktree `mail-role-enforcement` (nhánh `feat/mail-role-enforcement`),
đo **TRƯỚC merge**. Stack cũ (code `main`) đã bị dừng hẳn trước khi khởi động
stack của nhánh — `start-dev.ps1` thấy port đang mở sẽ "dùng lại" tiến trình cũ,
và toàn bộ nghiệm thu sẽ là giả. Kiểm lại: 4 cổng đóng sạch, rồi mới khởi động.

## Kết quả: 7/7 ĐẠT

| # | Kịch bản | Kết quả |
|---|---|---|
| 1 | kho gửi mail giao hàng | soạn được, đúng người nhận, có cổng xác nhận |
| 2 | kế toán gửi mail hóa đơn | soạn được, đúng người nhận, có cổng xác nhận |
| 3 | kho xin gửi mail hóa đơn | từ chối ở tầng agent, không cổng xác nhận |
| 4 | kế toán xin gửi mail giao hàng | không tới được tool (chi tiết ở §"Lỗi trải nghiệm") |
| 5 | **gọi thẳng `:8004`** `preview_template_email("Invoice: Sending", ...)` | `Template 'Invoice: Sending' không thuộc phạm vi của vai này.` |
| 6 | **gọi thẳng `:8004`** `send_prepared_email` trên bản nháp THẬT của kế toán | `Mail này không thuộc phạm vi của vai hiện tại.` |
| 7 | admin dùng cả hai template | không hồi quy |

Kịch bản 1 và 2 chính là hai thứ **đang chết hoàn toàn** trước nhánh này.

### Kịch bản 5 và 6 là phép đo quyết định

Chúng bỏ qua toàn bộ tầng agent, gọi thẳng cổng MCP bằng client SSE. Đây là
đường tấn công thật mà bộ lọc tool ở backend không với tới.

Kịch bản 6 được làm cho ĐÚNG sau một lần hỏng: lần đầu tôi truyền `mail_id`
không tồn tại, nên tool dừng ở "không tìm thấy" **trước** bước kiểm model —
một PASS giả. Làm lại cho đúng: dùng `:8005` (kế toán) tạo bản nháp thật trên
`account.move`, rồi gọi `send_prepared_email` trên `:8004` (kho) với chính
`mail_id` đó. Nếu guard hỏng, mail hóa đơn đã bị gửi thật.

### Kịch bản 5 đồng thời đóng một ⚠️ chưa ai đo được

Final review nêu: chưa ai chứng minh giá trị env **nhiều dòng** sống sót qua
`Start-Process` vào tiến trình MCP con, và không test tĩnh nào kiểm được. Kịch
bản 5 trả lời gián tiếp nhưng dứt khoát: nếu env không tới nơi, allowlist rỗng
= **không giới hạn**, và lời từ chối đã không xuất hiện.

## Đo tầng Odoo: bind và luật

`:8003/:8004/:8005` nay bind `127.0.0.1` (trước `0.0.0.0`). `:8002` vẫn
`0.0.0.0` — rủi ro đã ghi nhận, nhánh này không đụng tới.

`scripts/odoo_setup_ai_accounts.py` chạy thật **không crash ngay lần đầu** —
đáng nói vì chính script này từng "py_compile sạch" rồi vỡ ở lần chạy sống đầu
tiên. Chạy lần hai in "nhóm đã có" + "cập nhật luật": idempotent.

## HỒI QUY TÌM ĐƯỢC — và một kết quả thứ ba spec không dự trù

**Triệu chứng.** Với domain theo `name` (thiết kế ban đầu), đối chứng dương của
chính vai kho ĐỔ:

```
Fault 4: AI Warehouse (id=9) không có quyền truy cập 'đọc' vào:
- Mẫu email (mail.template)
```

Nghịch lý bề ngoài: phép đo trước đó cho thấy `ai-warehouse` **đọc được** đúng
template của mình (1/29). Nghĩa là `mail.template.send_mail` đọc thêm bản ghi
`mail.template` KHÁC ngoài chính template được gọi.

**Kiểm nhân quả, không suy luận.** Tắt hai luật → `ok: true` (mail_id 82). Bật
lại → đổ. Nguyên nhân là luật, chắc chắn.

**Kết quả thứ ba.** Spec §5.2 chỉ dự trù nhị phân: sạch thì giữ, gãy thì gỡ.
Thử domain theo `model` thay vì `name`:

| | domain theo `name` | domain theo `model` |
|---|---|---|
| kho gửi mail giao hàng | ❌ đổ | ✅ chạy |
| kho đọc được | 1/29 | 1/29 — vẫn không thấy `Invoice: Sending` |
| kế toán đọc được | 1/29 | 5/29 — đều thuộc `account.move`, không có `Shipping` |
| admin | 29/29 | 29/29 |

Nên **GIỮ** tầng Odoo, đổi domain. Phân tầng thành:

- **Odoo** chặn liên **miền** — tài khoản kho không đọc nổi bất kỳ template
  `account.move` nào
- **MCP `role_scope`** chặn liên **template** trong cùng miền

Chặt hơn hẳn phương án gỡ bỏ, và là thứ chỉ phép đo mới tìm ra.

**Chứng minh code tái tạo được, không phải chỉ vá tay.** Tôi đã vá tay lên Odoo
để đo. Sau khi sửa code, tôi **xoá hẳn hai luật** rồi chạy lại script: nó dựng
lại đúng `[('model', 'in', ['stock.picking'])]` /
`[('model', 'in', ['account.move'])]`, `perm_read` only, và ba con số
1/29 · 5/29 · 29/29 lặp lại y hệt. Không đo lại chính bản vá của mình.

## Vòng đo hồi quy §5.2

| Bằng chứng | Kết quả |
|---|---|
| Không có module `base.automation`; mọi `ir.actions.server` trên `stock.picking`/`account.move` đều `state='code'` | không action nào gửi mail template khi ghi |
| kho: `inventory_adjustment` chạy trọn đường ghi (`5 → 5`, no-op nhưng ghi thật) | không lỗi quyền |
| kế toán: `create_invoice_from_order` → hóa đơn nháp → xoá | không lỗi quyền |
| kho: `preview_template_email` trong phạm vi | chạy |
| kế toán: `preview_template_email` trong phạm vi | chạy |

**Kết luận: GIỮ luật.**

## Lỗi trải nghiệm (không phải lỗ hổng) — kịch bản 4

Kế toán xin gửi mail giao hàng nhận được câu *"đã nhận được yêu cầu… bạn vui
lòng xác nhận lại"* thay vì lời từ chối. Gửi tiếp "có, gửi đi" thì agent hỏi
lại lan man và **không có mail nào được tạo hay gửi** (kiểm `mail.mail`: 0 bản
ghi `outgoing`).

Nguyên nhân: `send_delivery_email` không nằm trong `_ACC_OTHER` của `roles.py`
nên trạng thái là `denied`, không phải `other_dept`. Planner không thấy tool
(đã bị lọc) nên không sinh kế hoạch nào để guard tất định bắt — nó rơi vào
đường trả lời hội thoại.

**Ba tầng đều giữ**: agent không định tuyến tới, MCP chặn template, Odoo chặn
đọc template. Đây là **cùng một khoảng trống đã hoãn** với `_WH_OTHER` thiếu
`create_invoice_from_order`/`create_bill_from_po` — nay có thêm anh em:
`_ACC_OTHER` thiếu `send_delivery_email`. Một bản sửa đóng được cả ba.

## Dọn dẹp

Mọi bản nháp `mail.mail` sinh ra khi đo đều đã xoá; `state='outgoing'` = 0.
Hóa đơn nháp thử nghiệm (111, 112) đã xoá. **Không xác nhận gửi ở bất kỳ kịch
bản nào** — mail đã gửi là không thu hồi được.

## Rủi ro còn lại

Xem §8 của spec. Điểm mới đo được lần này: tầng Odoo có độ mịn **theo model**,
nên hai coordinator mail dùng chung một model trong cùng một vai là không phân
biệt được ở tầng Odoo — tầng MCP mới là thứ tách chúng.
