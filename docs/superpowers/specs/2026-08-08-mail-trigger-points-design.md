# Mở rộng gửi mail sang 3 điểm nối mới — gom về 1 factory chung

**Ngày:** 2026-08-08
**Trạng thái:** design đã duyệt, chờ plan

## 1. Mục tiêu

Plan `2026-08-07-order-confirmation-email` (đã merge) dựng cơ chế gửi mail
thật, cố ý thu hẹp về ĐÚNG MỘT điểm nối (`send_order_confirmation_email`)
để chứng minh cơ chế trước. Plan `2026-08-08-inert-mail-draft` (đã merge)
làm bản nháp trơ tính với cron Odoo từ lúc tạo. Cơ chế giờ đã được chứng
minh trên Odoo thật ở cả 2 vòng, mở rộng sang 3 điểm nối còn lại:

| Coordinator mới | Template Odoo | Model | Người nhận |
|---|---|---|---|
| `send_invoice_email` | `Invoice: Sending` | `account.move` | khách hàng |
| `send_rfq_email` | `Purchase: Request For Quotation` | `purchase.order` | **nhà cung cấp** |
| `send_quotation_email` | `Sales: Send Quotation` | `sale.order` | khách hàng |

Cả 3 template đã tồn tại sẵn trong Odoo (kiểm chứng thật 2026-08-08), đều
có `auto_delete=True` — đúng hành vi mà `send_prepared_email` đã xử lý sẵn
(bản ghi tự biến mất sau khi gửi thành công là DẤU HIỆU THÀNH CÔNG, không
phải lỗi; xem plan `order-confirmation-email`).

## 2. Kiến trúc — 1 factory tham số hoá, 4 config

`backend/src/agents/mail_write.py` hiện hardcode `sale.order` +
`"Sales: Order Confirmation"` + arg `order_ref` trong Node 1. Node 2 (xác
nhận + gửi) ĐÃ generic 100% — không chứa gì riêng của sale.

Chuyển sang mẫu `OrderCfg`/`SALE_CFG`/`PURCHASE_CFG` có sẵn trong
`create_order.py` (không phát minh pattern mới):

```python
@dataclass(frozen=True)
class EmailCfg:
    template_name: str   # tên mail.template Odoo
    res_model: str       # model bản ghi nguồn
    ref_arg: str         # tên arg LLM truyền vào

ORDER_CONFIRMATION_CFG = EmailCfg("Sales: Order Confirmation", "sale.order", "order_ref")
QUOTATION_EMAIL_CFG    = EmailCfg("Sales: Send Quotation", "sale.order", "order_ref")
RFQ_EMAIL_CFG          = EmailCfg("Purchase: Request For Quotation", "purchase.order", "order_ref")
INVOICE_EMAIL_CFG      = EmailCfg("Invoice: Sending", "account.move", "invoice_ref")
```

- Node 1: `make_send_template_email_preview_node(tools, cfg)` — tham số hoá.
- Node 2: `make_send_template_email_node(tools)` — giữ NGUYÊN logic hiện có
  (write_gate re-check, `_interrupt`, discard best-effort, `_finish`), chỉ
  đổi tên; KHÔNG cần config.
- `route_after_mail_preview` generic hoá theo tên node đích tương ứng.

**CẢ 4 coordinator dùng chung 2 factory này**, kể cả
`send_order_confirmation_email` đã có — không để 2 pattern cùng giải một
vấn đề sống song song trong cùng file. Rủi ro thấp vì phần nhạy cảm nhất
(Node 2) chỉ là move nguyên văn; bằng chứng "không đổi hành vi" là toàn bộ
test hiện có của nó phải xanh KHÔNG sửa assertion nào (xem §5).

`graph.py` giữ nguyên kiểu hand-wiring 2 node đã có, nhân lên 4 cặp node
riêng biệt (KHÔNG share một node instance giữa nhiều lối vào) — không phát
minh topology mới. Bất biến "preview KHÔNG có unconditional edge thẳng
write_continuation" (test `test_graph_build.py`) mở rộng từ 1 lên 4 node.

## 3. Đăng ký

- 3 dòng mới trong `WRITE_COORDINATORS` (`write_registry.py`).
- 3 dòng mới trong `WRITE_PLANNER_PROMPT` (`prompts.py`) — **BẮT BUỘC**:
  vì không nằm trong `NEXT_STEPS` (xem dưới), đây là đường DUY NHẤT LLM
  biết các tool này tồn tại. Thiếu dòng này thì coordinator dù đúng hoàn
  toàn vẫn không bao giờ chạm tới được từ hội thoại thật — đúng lớp lỗi
  `write-confirmation-ux-fix` từng dính.
- **KHÔNG đăng ký vào `NEXT_STEPS`**: cả 3 khoá đều ĐÃ có bước kế chiếm
  chỗ (`create_quotation`→`confirm_sale_order`,
  `create_rfq`→`confirm_purchase_order`,
  `post_invoice`→`register_payment`). `NEXT_STEPS` là dict một entry mỗi
  khoá — thêm vào sẽ GHI ĐÈ im lặng, phá chuỗi có sẵn. Đây chính xác va
  chạm đã gặp và đã xử lý cùng cách ở plan `order-confirmation-email`.
- `CONFIRM_IN_CHAIN`: thêm cả 3, cho nhất quán với
  `send_order_confirmation_email` đã có. Thực chất inert (không có mặt
  trong `NEXT_STEPS` nên không bao giờ tới được như một bước chuỗi) —
  nhưng giữ quy tắc đồng nhất "mọi coordinator gửi mail đều thuộc tập
  này" rẻ hơn để 1/4 khác biệt gây khó hiểu về sau.

## 4. Quyết định đã cân nhắc và BÁC BỎ: `extra_domain`

Đã đề xuất thêm một bộ lọc domain phụ vào `preview_template_email` (vd
`move_type = "out_invoice"`, `state = "sale"`) để chặn gửi nhầm loại
chứng từ / nhầm vai trò người nhận. **Bác bỏ sau khi đo dữ liệu thật:**

1. Mỗi loại chứng từ `account.move` đã có tiền tố mã RIÊNG BIỆT (đo thật
   2026-08-08: `INV/2026/…` khách, `HÓA Đ/2026/…` NCC, `RINV/…` credit
   note khách, `RHÓA Đ/…` credit note NCC) — không thể tra nhầm bằng mã.
   Bộ lọc `move_type` canh một rủi ro mà chính hệ thống đánh số đã loại.
2. Mỗi giá trị `extra_domain` là một PHỎNG ĐOÁN quy tắc nghiệp vụ, và khi
   sai nó tạo chế độ lỗi TỆ HƠN thứ nó phòng: bản ghi có thật nhưng bị lọc
   ra sẽ báo "Không tìm thấy đơn S00171" — sai sự thật, người dùng không
   lần ra được vì sao. Cụ thể: `sale.order` có cả state `sale` lẫn `done`,
   lọc `state="sale"` sẽ chặn gửi lại mail cho đơn đã hoàn tất; lọc
   `move_type="out_invoice"` chặn luôn gửi credit note cho khách (nhu cầu
   hợp lệ).
3. Rủi ro gửi nhầm người ĐÃ có lớp chắn được chứng minh: cổng xác nhận
   hiển thị tên + email người nhận thật và tiêu đề mail trước khi gửi —
   chính là thứ final review plan `order-confirmation-email` bắt phải sửa
   (thay `recipient_count` bằng danh sách người nhận thật) đúng vì lý do
   này. `extra_domain` sẽ là lớp thứ hai, yếu hơn, dễ sai hơn, chồng lên
   một lớp đã hoạt động.

Kết luận: giữ `preview_template_email` NGUYÊN như hiện tại, không thêm
tham số. Guard `len(recs) > 1` sẵn có ("Có nhiều bản ghi… vui lòng nêu rõ
hơn") đã gánh việc thật — đo thật thấy `RINV/2026/00004` xuất hiện HAI
LẦN trong dữ liệu, nên đây không phải phòng xa lý thuyết.

## 5. Ràng buộc dữ liệu đã kiểm chứng

**Hóa đơn nháp có `name = False`** (không phải `"/"`) — đo thật
2026-08-08. Nghĩa là `send_invoice_email` về bản chất chỉ áp dụng cho hóa
đơn ĐÃ phát hành (đúng ý đồ: `post_invoice` → gửi mail), và tra theo mã sẽ
tự nhiên trả "Không tìm thấy bản ghi… trong account.move" cho hóa đơn
nháp — thông báo trung thực, KHÔNG cần chặn riêng. RFQ nháp
(`P00078`) và báo giá nháp (`S00161`) đều CÓ mã thật, tra cứu bình thường.

`send_quotation_email` gửi báo giá CHƯA xác nhận (khác
`send_order_confirmation_email` — đơn ĐÃ xác nhận). Cùng cổng xem-trước-
rồi-hỏi-xác-nhận đã có là đủ để người dùng tự bắt nếu gửi quá sớm; không
thêm validate trạng thái riêng (xem §4).

## 6. Cổng nghiệm thu

**Unit test** (`backend/tests/agents/test_mail_write.py`, mở rộng file có sẵn):

- Test factory tham số hoá: dựng coordinator từ một `EmailCfg` giả, khẳng
  định Node 1 gọi `preview_template_email` đúng `template_name`/
  `res_model`/giá trị `ref` lấy từ đúng tên arg trong config.
- **Toàn bộ test hiện có của `send_order_confirmation_email` phải xanh mà
  KHÔNG sửa một assertion nào** sau khi nó chuyển sang factory — đây là
  bằng chứng "gom về factory không đổi hành vi", mạnh hơn mọi lập luận.
- 1 test registry/prompt cho cả 3 tool mới theo mẫu
  `test_send_order_confirmation_email_registered_in_registry_and_prompts`:
  có trong `WRITE_PLANNER_PROMPT`, **vắng mặt** trong `NEXT_STEPS`, `.node`
  đúng.
- `test_graph_build.py`: mở rộng assertion "không có unconditional edge
  preview→write_continuation" từ 1 node thành cả 4.

**Live-verify TRƯỚC merge** (trên worktree của nhánh, không phải main —
xem tiền lệ `order-confirmation-email`), mỗi điểm nối một lần gửi thật +
một lần từ chối, đọc `mail.mail.state` trực tiếp qua XML-RPC ở mỗi bước:

1. `send_invoice_email` trên hóa đơn ĐÃ phát hành thật → mail tới đúng khách.
2. `send_rfq_email` trên RFQ thật → mail tới đúng **nhà cung cấp**. Đây là
   điểm rủi ro cao nhất (vai trò người nhận khác 3 cái kia), phải nhìn tận
   mắt, không suy ra từ 3 ca còn lại.
3. `send_quotation_email` trên báo giá nháp thật.
4. **Không hồi quy:** chạy lại `send_order_confirmation_email` sau khi nó
   chuyển sang factory — cùng kết quả như live-verify plan trước.

Cả 4 phải xác nhận bản nháp ở `state='cancel'` ngay sau khi soạn — chứng
minh cơ chế trơ tính vẫn đúng trên các model MỚI (`account.move`,
`purchase.order`), không chỉ `sale.order` đã đo.
