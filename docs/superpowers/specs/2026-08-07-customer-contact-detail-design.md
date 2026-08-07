# Thông tin liên lạc khách hàng — `get_customer_detail` + chủ động gợi ý

**Ngày:** 2026-08-07
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`backend/src/erp_query/purchase.py:137` đã có `get_supplier_detail(name)` —
đọc `res.partner`, trả về **email, phone, VAT, địa chỉ, tài khoản ngân hàng,
điều khoản thanh toán**, và đã được đăng ký làm tool cho agent
(`erp_query/tools.py:147-151`). Phía khách hàng chỉ có
`find_customer(name)` (`sales.py:20-21`) — gọi thẳng `resolve_entity`, chỉ
trả `id`/`name`, **không có email/phone**. Không có hàm tương đương
`get_customer_detail`.

Hệ quả: agent hiện có thể tra cứu và chủ động nêu thông tin liên lạc
**nhà cung cấp** khi cần, nhưng **không thể làm điều tương tự với khách
hàng** — một bất đối xứng có thật, không phải suy đoán, đo trực tiếp trên
Odoo (2026-08-07): `res.partner` "Acme Corporation" có đủ `email`, `phone`,
`vat`, `street`, `city`, `property_payment_term_id` — dữ liệu đã sẵn có,
chỉ thiếu đường đọc.

## 2. Phạm vi

**Có trong phạm vi:**
- Hàm đọc mới `get_customer_detail(name, *, gw=None)` trong
  `backend/src/erp_query/sales.py`, mirror `get_supplier_detail`.
- Đăng ký thành `@tool` trong `erp_query/tools.py`.
- Một rule mới trong `GATHER_ERP_PROMPT` để agent **chủ động** gọi
  `get_customer_detail`/`get_supplier_detail` và nêu email/SĐT trong câu
  trả lời khi phù hợp (không chỉ khi được hỏi thẳng).

**Cố ý KHÔNG làm** (gác lại cho spec kế tiếp — mục "gửi mail" của ý ban đầu):
- Không xây khả năng **gửi email thật**. Instance Odoo hiện **chưa có
  `ir.mail_server`** nào cấu hình — đo thật 2026-08-07, `search_read` trên
  `ir.mail_server` trả rỗng. Dù có build cơ chế gửi, mail sẽ chỉ nằm ở hàng
  đợi `mail.mail(state='outgoing')`, không rời khỏi hệ thống.
- Không đụng `bank_ids` cho khách hàng: không có giá trị nghiệp vụ tương
  đương bản NCC (mình không cần biết tài khoản ngân hàng của khách để làm
  gì) — khác `get_supplier_detail`, nơi biết TK ngân hàng NCC phục vụ việc
  mình trả tiền cho họ.
- Không sửa `find_customer`/`resolve_entity`: hai hàm này dùng chung cho
  nhiều model khác (`crm.py`, `create_order.py`...), đổi shape output sẽ
  lan ra ngoài phạm vi và rủi ro phá vỡ chỗ khác đang dùng.

## 3. Kiến trúc

### 3.1. `get_customer_detail` — `backend/src/erp_query/sales.py`

Mirror nguyên khuôn `get_supplier_detail` (`purchase.py:137-166`), đổi
field ngân hàng/điều khoản mua thành field đối xứng phía bán, và đổi
`po_count` (đơn mua) thành `so_count` (đơn bán):

```python
def get_customer_detail(name, *, gw=None):
    gw = gw or default_gateway()
    cus, msg = _resolve_single("res.partner", name, gw)
    if msg:
        return err(msg)
    try:
        rows = gw.search_read("res.partner", [["id", "=", cus["id"]]],
                              ["name", "email", "phone", "vat", "street", "city",
                               "property_payment_term_id"], limit=1)
        p = rows[0]
        sos = gw.search_read("sale.order", [["partner_id", "=", cus["id"]]],
                             ["id"], limit=200)
    except Exception as e:
        return err(f"Lỗi tra cứu hồ sơ khách hàng: {e}")
    term = p.get("property_payment_term_id")
    display = (f"Khách hàng: {p['name']}\n"
              f"  Email: {p['email'] or '—'} | Điện thoại: {p['phone'] or '—'}\n"
              f"  Mã số thuế: {p['vat'] or '—'}\n"
              f"  Địa chỉ: {p['street'] or '—'}, {p['city'] or '—'}\n"
              f"  Điều khoản thanh toán: {term[1] if term else '—'}\n"
              f"  Số đơn bán đã có: {len(sos)}")
    return ok({"partner": p, "so_count": len(sos)}, display)
```

`_resolve_single` (đã kiểm tra: định nghĩa tại `purchase.py:72-89`, wrapper
mỏng quanh `resolve_entity` — ưu tiên khớp chính xác, không thì lấy match
đầu) hiện là helper **riêng** của `purchase.py`, không phải chỗ dùng chung.
`sales.py` cần đúng hành vi này để resolve `res.partner`. Thay vì import
chéo `sales.py → purchase.py` (lệch domain) hoặc chép lại y nguyên 15 dòng
(trùng lặp không cần thiết), **chuyển `_resolve_single` sang
`erp_query/resolve.py`** — đúng nhà của nó, cạnh `resolve_entity` mà nó bọc
quanh — rồi `purchase.py` và `sales.py` cùng import từ đó. `purchase.py`
đổi 1 dòng import, không đổi hành vi `get_supplier_detail`.

Envelope chuẩn `ok`/`err`, tham số `gw=None` để test tiêm gateway giả —
đúng quy ước toàn bộ `erp_query`.

### 3.2. Đăng ký tool — `backend/src/erp_query/tools.py`

Thêm `@tool get_customer_detail(name: str) -> str` ngay cạnh
`get_supplier_detail` hiện có, cùng khuôn `_json(sales.get_customer_detail(name))`.
Thêm vào danh sách `tools = [...]`.

### 3.3. Prompt rule chủ động gợi ý — `GATHER_ERP_PROMPT`

Rule hiện có (`prompts.py:174`) chỉ kích hoạt khi **thiếu thông tin bắt
buộc để thực hiện một thao tác ghi** — không phủ ca "câu trả lời thuần đọc,
nhưng nêu contact sẽ hữu ích". Thêm rule mới, ngưỡng kích hoạt **hẹp có chủ
đích** để tránh nhiễu (không phải mọi câu nhắc tên khách/NCC đều cần contact
— vd danh sách 22 hóa đơn quá hạn từ 4 khách không cần kèm 4 bộ contact):

> Nếu câu trả lời xoay quanh **đúng một** khách hàng/nhà cung cấp cụ thể làm
> trọng tâm (không phải danh sách nhiều đối tác), và câu hỏi có tính chất
> nghiệp vụ có thể cần liên hệ tiếp theo (đặt hàng, hỏi thêm, xác nhận, báo
> giá) — hãy chủ động gọi `get_customer_detail`/`get_supplier_detail` và nêu
> email/SĐT nếu có, không cần người dùng hỏi thẳng.

Ngưỡng "đúng một, không phải danh sách" tái dùng đúng tinh thần rule đã có ở
`FUSE_PROMPT:186` ("Khi dữ kiện cho thấy chỉ có ĐÚNG một lựa chọn khả dĩ...").

## 4. Rủi ro và cách xử lý

### 4.1. Rule mới có thể làm agent gọi tool thừa, tăng độ trễ/chi phí

Ngưỡng "đúng một đối tác + có tính chất nghiệp vụ cần liên hệ" đã thu hẹp
có chủ đích (§3.3). Cổng nghiệm thu §5 verify bằng ca thật KHÔNG nên kích
hoạt (câu hỏi liệt kê nhiều đối tác) để chứng minh không nhiễu.

### 4.2. Di chuyển `_resolve_single` — rủi ro hồi quy `get_supplier_detail`/`get_product_suppliers`

`_resolve_single` đang được `purchase.py` dùng ở **hai** chỗ
(`get_product_suppliers:94`, `get_supplier_detail:139`), không chỉ một.
Di chuyển sang `resolve.py` phải giữ **hành vi y hệt** (test hồi quy của cả
hai hàm đó phải xanh nguyên, không chỉ test mới của `get_customer_detail`).

### 4.3. Eval/regression hiện có (GATHER_CASES, multi_source_gather...) có thể đổi hành vi

Rule mới có thể khiến một số câu hỏi hiện có trong eval set gọi thêm tool —
cần chạy lại eval suite liên quan sau khi implement để bắt hồi quy điểm số,
không chỉ dựa vào unit test dựng state tay.

## 5. Cổng nghiệm thu

Unit test (dựng gateway giả) cho `get_customer_detail` là cần nhưng không
đủ để verify rule prompt mới — rule đó chỉ thật sự chạy qua LLM thật. Live-
verify qua backend thật (đúng phương pháp resend toàn bộ lịch sử, không
`session_id`, đã dùng ở các plan trước):

1. **Câu hỏi đơn khách hàng cụ thể, có tính nghiệp vụ.** "Khách Acme
   Corporation có đơn hàng nào đang chờ giao không?" → câu trả lời **kèm**
   email/SĐT thật của Acme (không cần hỏi thẳng).
2. **Câu hỏi liệt kê nhiều đối tác — KHÔNG kích hoạt.** "Hóa đơn nào quá hạn
   thanh toán?" (trả về nhiều khách khác nhau) → **không** tự động kèm
   contact cho từng khách — chứng minh ngưỡng "đúng một" hoạt động đúng,
   không nhiễu.
3. **Nhà cung cấp — chống hồi quy.** Một câu hỏi đơn NCC cụ thể (vd "nhà
   cung cấp Acme cho Individual Workplace là ai, thông tin liên lạc thế
   nào?") → vẫn ra đúng email/SĐT NCC như trước (rule mới không phá nhánh
   `get_supplier_detail` đã hoạt động).
