# Cảnh báo rủi ro trước khi ghi (mục 21) + chặn tạo NCC ở tầng Odoo (mục 23)

**Ngày**: 2026-08-23. **Nhánh**: `main`.

## 1. Mục 18 — ĐÓNG, không làm

Chủ dự án quyết định bỏ: *"tôi hay quên mật khẩu, và cũng chỉ mình tôi xem
được"*. Ghi lại nguyên trạng để lần sau không ai mở lại mà không biết đã cân
nhắc: **cả 5 tài khoản AI dùng CHUNG một mật khẩu** (`AI_ACCOUNT_PASSWORD`),
nên ở tầng credential, năm tiến trình MCP cô lập theo vai **chỉ cô lập trên
giấy**. Code đã sẵn sàng (`ODOO_PASSWORD_<VAI>`); mở lại chỉ là đặt 5 biến.

## 2. Mục 23 — Odoo phân quyền tới đâu? (nghiên cứu theo yêu cầu)

**Bốn tầng, cả bốn đều có mặt trong instance này:**

| tầng | bảng | số bản ghi |
|---|---|---|
| Nhóm quyền | `res.groups` | 76 |
| **ACL theo model** (read/write/create/unlink riêng) | `ir.model.access` | 869 |
| **Luật theo bản ghi** (domain lọc dòng) | `ir.rule` | 220 |
| Theo trường | `ir.model.fields` | 10 105 |

Nên câu trả lời KHÔNG phải "Odoo thiếu cơ chế" mà là **"chưa ai viết luật"** —
dự án đã dùng tầng 3 cho `mail.template` rồi.

Nhưng đo tiếp thì không phải cặp nào cũng đóng được sạch:

| khoảng trống | kết luận |
|---|---|
| `create_vendor` | ✅ đóng được sạch — **đã làm, xem §3** |
| 3 tool mail thô | ✅ đã đóng ở tầng bản ghi; script chỉ kiểm tầng model nên báo nhầm |
| `find_my_activities` | ⚠️ không đáng — chỉ-đọc việc của chính mình |
| `update_quotation_lines` (kho) | ❌ vướng: **đo thật, vai kho sửa được dòng báo giá S00193**, vì `Inventory / User` có `w1` trên `sale.order.line` — ACL **mặc định của Odoo**, gỡ đi có thể vỡ luồng kho |
| `update_rfq_lines` (kế toán) | ❌ cùng hình dạng, `Accounting / Invoicing` có `w1` trên `purchase.order.line` |

Sắc thái đáng ghi: vai kho **sửa được số lượng** dòng có sẵn nhưng **không
thêm/xoá được** (`c0 u0`) — thiệt hại tối đa nhỏ hơn tên gọi gợi ý.

**Khuôn an toàn:** tạo nhóm riêng của dự án + ir.rule, **đừng sửa ACL mặc định
của Odoo** — sửa là giẫm lên luồng nghiệp vụ của chính nó, và không có gì báo
khi vỡ.

## 3. Mục 23 — luật chặn tạo nhà cung cấp (đã làm)

`res.partner.supplier_rank` (integer) phân biệt được khách với NCC. Nhóm mới
`Youdoo AI / Partner No Vendor` + ir.rule domain `[('supplier_rank','=',0)]`,
gắn cho **cả ba vai non-admin**.

⚠️ **`perm_read=False` CÓ CHỦ ĐÍCH — đây là cái bẫy chính.** `ensure_rule` cũ
ghi cứng `perm_read=True`; dùng nguyên nó sẽ **giấu mọi NCC** khỏi vai kho và
làm hỏng `find_supplier`/`get_supplier_detail` — một luật "an ninh" bẻ gãy
nghiệp vụ đọc. Đã nới `ensure_rule` nhận tham số `perms`, mặc định giữ nguyên
hành vi cũ để 2 luật mail không đổi.

**Nghiệm thu, ba chiều:**

| tài khoản | tạo KHÁCH | tạo NCC | đọc NCC |
|---|---|---|---|
| `ai-warehouse` | ✅ | **CHẶN** | ✅ (10) |
| `ai-accounting` | ✅ | **CHẶN** | ✅ (10) |
| `ai-sales` | ✅ | **CHẶN** | ✅ (10) |
| `ai-admin` | ✅ | ✅ | ✅ (11) |

Cột "tạo KHÁCH" và "đọc NCC" là hai ca đối chứng: chúng chứng minh luật chặn
đúng thứ cần chặn chứ không chặn bừa. Đã xoá 5 partner test.

## 4. Mục 21 — cảnh báo rủi ro thay cho Undo

Thiết kế của chủ dự án: **không làm Undo thật**; thay vào đó nói trước khi còn
kịp huỷ, và khi người dùng muốn sửa thì gợi ý **hành động bù trừ** chứ không
hứa hoàn tác.

Lý do đứng vững khi đối chiếu Odoo: "hoàn tác" mang nghĩa khác nhau ở từng thao
tác và **có cái không tồn tại** — thư đã gửi không thu hồi được, hoá đơn đã phát
hành phải bù bằng credit memo (chứng từ MỚI), hàng đã xuất phải làm phiếu ngược.

`RUI_RO_CUA_TOOL` phủ **15 tool**, chia ba nhóm: không thu hồi (5 mail), không
hoàn tác (`post_invoice`, `register_payment`), đụng hàng thật (7 tool kho/sản
xuất).

⚠️ **Cố ý BỎ TRỐNG các tool tạo mới** (`create_quotation`, `create_rfq`,
`create_lead`, `create_bom`…). Cảnh báo mọi thứ thì chẳng còn gì là cảnh báo —
người dùng sẽ học cách lướt qua cả những dòng thật sự quan trọng. Có một test
riêng canh chiều này.

**Nghiệm thu sống, 3 ca (ca cuối là ĐỐI CHỨNG):**

    Gửi mail báo giá S00193
      ⚠️ Thư đã gửi KHÔNG thu hồi được. Nếu cần sửa, chỉ có thể gửi thư mới…

    Điều chỉnh tồn kho … về 50
      ⚠️ Số tồn sẽ bị GHI ĐÈ, không cộng dồn. Muốn sửa phải điều chỉnh lại…

    Lập báo giá cho Azure Interior
      (KHÔNG có cảnh báo)

## 5. Khó khăn / hướng đã chọn / giới hạn còn lại

**Khó khăn — 22 chỗ dựng câu xác nhận / 11 tệp, và chỗ gọi không phải lúc nào
cũng biết tên tool.** *Hướng đã chọn*: cổng planner (`nodes.py`) có
`plan["tool"]` nên phủ mọi tool KHÔNG có coordinator cùng lúc; 5 tệp coordinator
chứa tool rủi ro thì nối tay, mỗi chỗ một hằng. `render_invoice_summary` dùng
chung cho `post_invoice` và `register_payment` nên phải thêm tham số `tool`.
*Giới hạn*: 5 tệp coordinator không rủi ro (`create_order`, `crm_write`,
`bom_write`, `purchase_write`, `edit_order`) không nối — đúng thiết kế, nhưng
nếu sau này một tool rủi ro chuyển vào đó thì phải nhớ nối.

**Rào chống trôi cho đúng chỗ đó:** `test_moi_tool_rui_ro_deu_TOI_DUOC_mot_cong_xac_nhan`
— tool có coordinator ⇒ phải có một tệp `*_write.py` vừa gọi `canh_bao_rui_ro`
vừa nhắc tới nó; tool không coordinator ⇒ cổng planner phải gọi hàm đó. Đã thử
phá: gỡ lời gọi khỏi `mail_write.py` ⇒ đỏ đúng 5 tool mail.

**Test của tôi từng quá cứng:** ca "cảnh báo phải nói hậu quả" liệt kê
`"KHÔNG"`/`"không"` mà quên dạng `"Không"` (K hoa) ⇒ đỏ oan một tool. Sửa thành
so không phân biệt hoa thường — test cứng, không phải cảnh báo sai.

**Chưa làm:** 3 khoảng trống vai↔Odoo còn lại (§2) nên khai vào
`KNOWN_ODOO_GAPS` kèm lý do đo được, thay vì để script thoát mã 1 mãi. Mục 17b
chủ dự án đang cân nhắc.
