# Phiếu phỏng vấn phân quyền theo vai

**Mục đích:** kiểm chứng ranh giới quyền hạn với người làm thật, trước khi
chốt thiết kế phân vai cho agent (xem `ADR-012`).

**Cách dùng:** Phần A hỏi trực tiếp nhân viên — không có thuật ngữ kỹ thuật.
Phần B là bản đồ nghiệp vụ → model/tool, dành cho người thiết kế, **không đưa
cho người được phỏng vấn**.

Đánh dấu mỗi dòng: **Đ** = được làm · **K** = không được · **X** = được nhưng
phải xin duyệt · **?** = không rõ / không liên quan

---

# PHẦN A — Phiếu hỏi

## A1. Nhân viên KHO

### A1.1 Việc hằng ngày — xuất/nhập hàng

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 1 | Anh/chị có tự xác nhận **đã giao hàng xong** cho một đơn không? | |
| 2 | Có tự xác nhận **đã nhận hàng** từ nhà cung cấp không? | |
| 3 | Có tự tạo **phiếu chuyển hàng nội bộ** giữa các kho/khu vực không? | |
| 4 | Có được **sửa số lượng thực giao** khác với số trên đơn không (giao thiếu/thừa)? | |
| 5 | Khi hàng nhận về **thiếu hoặc hỏng**, anh/chị tự xử lý hay phải báo ai? | |

### A1.2 Kiểm kê và hàng hỏng

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 6 | Có được **tự điều chỉnh số lượng tồn kho** sau khi kiểm kê không? | |
| 7 | Nếu được, có **giới hạn giá trị** không (vd trên X triệu phải xin duyệt)? | |
| 8 | Có được **khai báo hàng hỏng/huỷ** (scrap) không? | |
| 9 | Có được **tạo phiếu trả hàng** cho nhà cung cấp không? | |

### A1.3 Thông tin được XEM — *phần quan trọng nhất, hỏi kỹ*

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 10 | Có xem được **giá bán** của sản phẩm không? | |
| 11 | Có xem được **giá mua / giá vốn** không? | |
| 12 | Có xem được **công nợ của khách hàng** (khách còn nợ bao nhiêu) không? | |
| 13 | Có xem được **hoá đơn** (đã phát hành, đã thanh toán chưa) không? | |
| 14 | Trước khi xuất hàng, có cần biết **đơn đó khách đã thanh toán chưa** không? | |
| 15 | Có xem được **thông tin liên hệ** của khách/nhà cung cấp không? | |
| 16 | Có xem được **doanh thu, báo cáo bán hàng** không? | |

### A1.4 Liên lạc ra ngoài

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 17 | Có được **gửi email cho khách** báo đã xuất hàng / đang giao không? | |
| 18 | Nếu có, email đó **gửi thẳng** hay phải qua ai duyệt? | |
| 19 | Có được **liên hệ trực tiếp nhà cung cấp** (gọi/mail) khi hàng về thiếu không? | |

### A1.5 Ngoài phạm vi kho

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 20 | Có được **tạo đơn bán / báo giá** cho khách không? | |
| 21 | Có được **tạo đơn mua** đặt hàng nhà cung cấp không? | |
| 22 | Có được **phát hành hoá đơn** không? | |
| 23 | Có được **xác nhận đơn bán** (chốt đơn) không? | |
| 24 | Khi gặp việc thuộc bộ phận khác, quy trình hiện tại là gì? *(báo miệng / phần mềm / email / giấy)* | |

### A1.6 Câu hỏi mở — *đừng bỏ qua, thường lộ ra thứ không ai nghĩ tới*

| # | Câu hỏi |
|---|---|
| 25 | Việc gì anh/chị **thường phải chờ người khác** làm hộ, mà thấy mất thời gian nhất? |
| 26 | Có việc gì hệ thống **cho phép làm nhưng thực tế bị cấm** (quy định nội bộ) không? |
| 27 | Đầu ca làm việc, anh/chị **nhìn vào đâu** để biết hôm nay phải làm gì? |
| 28 | Có bao giờ làm nhầm vì **không thấy được thông tin** của bộ phận khác không? |

---

## A2. Nhân viên KẾ TOÁN *(hỏi sau, nếu có dịp)*

| # | Câu hỏi | Đ/K/X |
|---|---|---|
| 1 | Có tự **phát hành hoá đơn** (post) không, hay cần kế toán trưởng duyệt? | |
| 2 | Có tự **ghi nhận thanh toán** không? Có giới hạn số tiền? | |
| 3 | Có được **tạo credit memo / hoàn tiền** không? | |
| 4 | Có được **gửi hoá đơn qua email** cho khách không? | |
| 5 | Có xem được **tồn kho** không? Có cần không? | |
| 6 | Có được **sửa/huỷ** hoá đơn đã phát hành không? | |
| 7 | Có được xem **giá vốn** không? | |
| 8 | Ai là người **đối chiếu đơn mua với hoá đơn NCC** (3-way matching)? | |

---

# PHẦN B — Bản đồ kỹ thuật *(không đưa cho người phỏng vấn)*

## B1. Nghiệp vụ → tool → model

### Kho — ghi

| Câu A1 | Nghiệp vụ | Tool | Model |
|---|---|---|---|
| 1 | Xác nhận giao hàng | `deliver_order`, `validate_picking` | `stock.picking` |
| 2 | Xác nhận nhận hàng | `receive_order`, `validate_picking` | `stock.picking` |
| 3 | Chuyển kho nội bộ | `internal_transfer` | `stock.picking` |
| 4 | Sửa số lượng thực giao | *(chưa có tool riêng)* | `stock.move` |
| 6-7 | Điều chỉnh tồn kho | `inventory_adjustment` | `stock.quant` |
| 8 | Khai báo hàng hỏng | `scrap_product` | `stock.scrap` |
| 9 | Trả hàng NCC | `return_order` | `stock.return.picking` |
| 17 | Mail báo đã xuất hàng | **`send_delivery_email` (ĐỀ XUẤT MỚI)** | `stock.picking` + template `Shipping: Send by Email` |

### Kho — đọc

| Câu A1 | Nghiệp vụ | Tool | Model |
|---|---|---|---|
| 10 | Xem giá bán | `get_product_price` | `product.product` |
| 11 | Xem giá mua/NCC | `get_product_suppliers` | `product.supplierinfo` |
| 12 | Xem công nợ khách | `get_partner_balance` | `account.move` |
| 13 | Xem hoá đơn | `list_invoices`, `get_overdue_invoices` | `account.move` |
| 15 | Liên hệ khách/NCC | `get_customer_detail`, `get_supplier_detail` | `res.partner` |
| 16 | Báo cáo bán hàng | `sales_summary`, `top_products` | `sale.report` |
| 27 | **Hàng đợi việc hôm nay** | *(CHƯA CÓ — xem ADR-012 §2)* | `stock.picking` (94 phiếu chờ) |

### Ngoài phạm vi kho

| Câu A1 | Nghiệp vụ | Tool |
|---|---|---|
| 20 | Tạo báo giá | `create_quotation` |
| 21 | Tạo đơn mua | `create_rfq` |
| 22 | Phát hành hoá đơn | `post_invoice` |
| 23 | Xác nhận đơn bán | `confirm_sale_order` |

### Kế toán

| Câu A2 | Nghiệp vụ | Tool | Model |
|---|---|---|---|
| 1 | Phát hành hoá đơn | `post_invoice` | `account.move` |
| 2 | Ghi nhận thanh toán | `register_payment` | `account.payment.register` |
| 3 | Credit memo | `create_credit_memo` | `account.move.reversal` |
| 4 | Mail hoá đơn | `send_invoice_email` | `account.move` |
| 8 | Đối chiếu PO | `check_po_matching`, `list_po_mismatches` | `purchase.order`+`account.move` |

## B2. Câu trả lời sẽ quyết định điều gì

| Nhóm câu | Quyết định thiết kế bị ảnh hưởng |
|---|---|
| **A1.3 (10-16)** | **Giả định "đọc rộng tay" của ADR-012 §7.2.** Nếu kho KHÔNG được xem công nợ/giá vốn, thì một credential đọc dùng chung là SAI, và phải tách gateway đọc theo vai (hạ tầng đã sẵn: mọi hàm `erp_query` nhận `gw=None`). |
| A1.4 (17-19) | Vai kho có cần nhóm quyền mail không → có thêm `send_delivery_email` không |
| A1.2 (6-7) | Có cần ngưỡng giá trị cho `inventory_adjustment` không — hiện **không có** ngưỡng nào |
| A1.5 (24) | Thiết kế bàn giao chéo bộ phận (ADR-012 §5): activity hay kênh khác |
| A1.6 (27) | Xác nhận nhu cầu "hàng đợi việc hôm nay" — nếu họ đang nhìn giấy/Excel thì đó là khoảng trống rõ ràng |
| A1.6 (26) | Quy định nội bộ chặt hơn phần mềm ⇒ agent phải chặn theo quy định, không theo khả năng kỹ thuật |
| A2 (1-2) | Có cần cấp duyệt nhiều tầng không — hiện chỉ có 1 cổng xác nhận phẳng |

## B3. Điều cần nghe được, không chỉ điền form

Ba thứ đáng giá hơn cả bảng Đ/K/X:

1. **Câu 27** — nếu họ trả lời "nhìn tờ giấy in sẵn" hoặc "hỏi tổ trưởng", đó là
   xác nhận trực tiếp cho khoảng trống ADR-012 §2 (agent giỏi *làm*, mù *việc gì
   cần làm*).
2. **Câu 26** — quy định nội bộ thường chặt hơn phân quyền phần mềm. Agent nên
   theo quy định thật, không theo cái Odoo cho phép.
3. **Câu 28** — mỗi lần làm nhầm vì thiếu thông tin chéo bộ phận là một lập luận
   cho "đọc rộng tay"; mỗi lần lo ngại lộ thông tin là lập luận ngược lại. Cần
   nghe cả hai phía trước khi chốt.
