# Live-verify — phân quyền theo vai (2026-08-09)

**Môi trường:** worktree `role-based-access`, chạy thật với 3 tiến trình MCP
(`:8003` ai-admin · `:8004` ai-warehouse · `:8005` ai-accounting) + backend
`:8002` đọc Odoo bằng `ai-readonly`. Thử qua **giao diện Open WebUI thật**
(người dùng thao tác) và qua API kèm header nhận dạng (controller đo).

## Kết quả: 6/6 ĐẠT

### Tiêu chí 1 — vai kho làm được việc kho

Vai `warehouse`, yêu cầu *"xác nhận phiếu kho WH/OUT/00138"* → chạy bình
thường qua cổng xác nhận:

```
(validate_picking: picking_ref=WH/OUT/00138)
Bạn xác nhận giúp mình nhé?
```

Đây là **đối chứng âm** quan trọng: guard chỉ chặn đúng thứ cần chặn, không
chặn nhầm việc thuộc quyền. **ĐẠT.**

### Tiêu chí 2 — vai kho bị từ chối việc kế toán, có chỉ đường

Vai `warehouse`, yêu cầu *"phát hành hóa đơn cho khách"*:

```
Việc này không thuộc quyền hạn của bộ phận Kho.
Vui lòng liên hệ bộ phận Kế toán để thực hiện.
```

Từ chối sạch, nêu đúng bộ phận, **không** kèm cổng xác nhận. **ĐẠT** (sau
một vòng sửa — xem §"Lỗi phát hiện").

### Tiêu chí 3 — vai kế toán làm được đúng việc đó

Vai `accounting`, cùng câu hỏi → vào đúng luồng, hỏi tiếp:

```
Bạn cần cho biết khách hàng (hoặc ID) của hóa đơn nháp.
```

Cùng một câu hỏi, hai vai, hai kết quả trái ngược — hai vai **thật sự khác
nhau**, không phải cùng quyền đội lốt. **ĐẠT.**

**Đo bổ sung, chiều ngược lại:** vai `accounting` yêu cầu *"xác nhận phiếu kho
WH/OUT/00138"* → *"không thuộc quyền hạn của bộ phận Kế toán. Vui lòng liên hệ
bộ phận Kho"*. Cả hai chiều đều chặn đúng.

### Tiêu chí 4 — cưỡng chế là THẬT, không chỉ lọc ở tầng agent

**Phép đo quyết định của cả plan.** Gọi thẳng Odoo bằng credential
`ai-warehouse`, bỏ qua toàn bộ backend và LLM:

```
has_access(account.move, write) = False
```

Odoo chặn **ngay ở bước đọc**, chưa kịp tới lệnh phát hành, và trả về Fault
liệt kê rõ những nhóm quyền cần có. **ĐẠT.**

Đo thêm để xác nhận hai credential tách đúng thiết kế:

| Credential | đọc `account.move` | ghi `account.move` |
|---|---|---|
| `ai-readonly` (đường đọc, backend) | ✅ | ❌ |
| `ai-warehouse` (đường ghi, MCP) | ❌ | ❌ |

Nhân viên kho **xem được** hoá đơn (phỏng vấn câu 13 = Đ) qua đường đọc, nhưng
không thao tác được qua đường ghi. Đường đọc là read-only **thật** — kể cả bị
chiếm quyền hoàn toàn cũng không ghi được, vì tài khoản không có quyền, không
phải vì code từ chối.

### Tiêu chí 5 — đổi vai không resume nhầm graph

**Nhận xét thiết kế trước khi đo:** kịch bản "người dùng tự đổi vai giữa chừng"
KHÔNG xảy ra được — vai suy từ tài khoản đăng nhập, nên đổi tài khoản là đổi
`user_id`, tức `thread_id` đã khác sẵn. Đường THẬT để cùng một `user_id` ra hai
vai khác nhau là: **quản trị viên đổi bảng ánh xạ trong lúc câu xác nhận đang
treo.** Đó mới là thứ tiền tố vai bảo vệ, nên đo đúng kịch bản đó.

Phép đo:
1. Vai `warehouse` tạo câu xác nhận treo cho `WH/OUT/00007` (state `assigned`)
2. Đổi ánh xạ user đó sang `accounting`, khởi động lại backend
3. Gửi đúng chữ `"có"` — cùng `user_id`, cùng `chat-id`

Kết quả: `"có"` được xử lý như **lượt mới** (agent chào lại), KHÔNG resume. Đọc
lại Odoo: `WH/OUT/00007` vẫn `state='assigned'`, **không** thành `done`.

Một hành động ghi đã duyệt ở vai cũ **không** bị hoàn tất dưới vai mới. **ĐẠT.**

### Tiêu chí 6 — người không có vai bị từ chối

Chứng minh ngoài ý muốn, và vì thế đáng tin hơn một bài test dàn dựng: lúc
`YOUDOO_ROLE_MAP` còn rỗng, chính tài khoản admin của chủ dự án bị từ chối:

```
Không xác định được quyền truy cập của bạn. Vui lòng đăng nhập bằng
tài khoản đã được cấp vai, hoặc liên hệ quản trị viên.
```

Hệ thống không nhận ra ai, và nó chọn **từ chối** thay vì đoán. **ĐẠT.**

## Hai lỗi thật chỉ live-verify mới bắt được

Cả hai xảy ra khi **1.248+ unit test đều xanh**. Chúng thoát lưới vì test dựng
graph bằng danh sách tool giả và không đi qua planner thật.

### 1. Backend không khởi động nổi (nghiêm trọng)

```
skill 'nhap-kho': tool ghi 'flag_order_for_review' không có trong registry MCP
Application startup failed. Exiting.
```

Ba SOP skill khai báo tool ghi riêng; bộ lọc theo vai cắt mất chúng ⇒ **mọi vai
non-admin đều làm sập startup**. Khoảng trống thiết kế plan không lường: SOP
skill vốn không biết đến vai, nhưng manifest được validate khi dựng graph cho
mọi vai.

**Sửa:** nạp skill theo vai — vừa đúng kỹ thuật vừa đúng nghiệp vụ (kho không
nên được mời SOP báo giá). Quan trọng: **không nới lỏng** `SkillManifestError`
— nó vẫn nổ khi skill khai một tool không tồn tại ở bất kỳ đâu (lỗi cấu hình
thật); chỉ bỏ qua khi tool có thật nhưng vai không được cấp. Hai trường hợp
được phân biệt rõ ràng, không bắt gộp exception.

Kèm theo: thêm `flag_order_for_review` cho vai kho, căn cứ phỏng vấn câu 5
(hàng về thiếu/hỏng thì tự xử lý = Đ).

Kết quả sau sửa: `admin` nạp cả 3 skill · `warehouse` nạp `giao-hang` +
`nhap-kho`, bỏ `bao-gia-chiet-khau` · `accounting` bỏ cả 3.

### 2. Cổng xác nhận hỏi người dùng duyệt một lời từ chối

```
Mình sẽ thực hiện thao tác sau giúp bạn:
Từ chối phát hành hóa đơn do không thuộc quyền hạn của bộ phận Kho.
(other: )
Bạn xác nhận giúp mình nhé?
```

Gốc rễ là **lỗi thiết kế của controller**: việc chặn được đặt vào *prompt*, tức
giao ranh giới cho LLM giữ — trái đúng nguyên tắc chính spec này viết ra (§3:
không để tầng LLM là thứ duy nhất đứng giữa người dùng và hành động đặc quyền).
LLM không có cách nào diễn đạt "chỉ trả lời, không hành động" trong định dạng
JSON bắt buộc nêu tên tool, nên nó bịa ra tool `other`.

**Bảo mật không thủng** — tool `other` không tồn tại nên executor từ chối, và
`ai-warehouse` cũng bị Odoo chặn. Ba lớp vẫn giữ. Đây là lỗi **trải nghiệm**,
nhưng nó cho thấy đúng lý do phải có lớp cưỡng chế dưới cùng.

**Sửa:** chặn tất định trong code — sau khi planner ra kế hoạch, nếu tool thuộc
`other_dept`/`denied` của vai (hoặc không tồn tại), trả thẳng câu từ chối nêu
bộ phận, `pending_action=None`, không cổng xác nhận. Prompt giữ nguyên nhưng từ
nay chỉ là gợi ý.

### Số liệu ĐẦY ĐỦ sau khi chạy script (controller chạy thật, 2026-08-09)

Bản ghi ở trên nói "4 khoảng trống đã biết" — con số đó đến từ phần kiểm thủ
công của final review. Khi chạy `scripts/check_role_odoo_consistency.py` phủ
hết 18 tool × 2 vai, kết quả thật là **9 khoảng trống + 2 lỗi chức năng**:

| Vai | Kết quả |
|---|---|
| `warehouse` | 16/18 đúng. 2 gap: `confirm_sale_order`, `send_invoice_email` |
| `accounting` | 7 gap: `deliver_order`, `receive_order`, `validate_picking`, `internal_transfer`, `confirm_sale_order`, `confirm_purchase_order`, `send_delivery_email` |

> **ĐÍNH CHÍNH LẦN BA (2026-08-11, nhánh `fix/role-access-map-correction`).**
> Con số "2 lỗi chức năng" ngay dưới đây **SAI** — thực tế chỉ có **1**. Số 9
> khoảng trống thì đúng, nhưng đúng do trùng hợp: `TOOL_ACCESS_MAP` mà cả hai
> con số dựa vào có **8/18 dòng sai operation hoặc thiếu cặp**. Xem mục
> "Đính chính lần ba" ở cuối tài liệu để có số liệu đã kiểm chứng.

**Vai kho gần như sạch** — mọi tool `own` đều chạy được, mọi tool `other_dept`
đều bị Odoo chặn trừ 2. Đây là vai bị hạn chế nhiều nhất và cũng là vai được
cưỡng chế tốt nhất. Khoảng trống tập trung ở vai kế toán, vì `Accounting /
Invoicing` không tách được theo loại phiếu kho.

### HAI LỖI CHỨC NĂNG (khác hẳn khoảng trống — sẽ hỏng thật khi dùng)

```
accounting  create_invoice_from_order    expect=has  actual=lacks  BLOCKED
accounting  create_bill_from_po          expect=has  actual=lacks  BLOCKED
```

`roles.py` khai hai tool này thuộc `own` của kế toán, nhưng tài khoản
`ai-accounting` KHÔNG có quyền — nên chúng sẽ báo lỗi Odoo khi kế toán dùng
thật. Nguyên nhân: cả hai gọi wizard `sale.advance.payment.inv`, tức cần quyền
Sales mà `Accounting / Invoicing` không cấp.

Đây KHÔNG phải lỗ hổng bảo mật (chặn chặt hơn khai báo, không lỏng hơn), nhưng
là năng lực được hứa mà không dùng được. Chưa sửa trong nhánh này — cần quyết
định chính sách: hoặc cấp thêm nhóm Sales cho `ai-accounting`, hoặc chuyển hai
tool này ra khỏi `own` của kế toán. Ghi lại ở đây để không rơi vào im lặng.

**Bài học lặp lại hai lần trong nhánh này:** "đã kiểm tra" không đồng nghĩa "đã
kiểm tra đúng thứ đang tuyên bố". Kết luận gốc nói 3 tầng đều được chứng minh —
thực ra đo 1 tool 1 chiều. Bản sửa nói 4 gap — thực ra 9, cộng 2 lỗi chức năng.
Chỉ khi có script phủ hết ma trận và CHẠY THẬT thì con số mới đúng.

## Kết luận

**6/6 tiêu chí ĐẠT, đo TRƯỚC merge, trên code worktree thật.** Ba tầng bảo vệ
đều CÓ và hoạt động đúng thiết kế ở những chỗ đã đo: lọc tool ở backend (trải
nghiệm — tiêu chí 1/2/3/6), chặn tất định trong code (đúng đắn — tiêu chí
2/3/5, cộng phần "Hai lỗi thật" ở trên), và cưỡng chế ở tầng Odoo (bảo mật —
tiêu chí 4).

**Sửa lại nhận định trước đây (final-review Fix 6a, việc kiểm tra toàn nhánh
2026-08-09):** câu kết luận gốc ở đây viết "Ba tầng bảo vệ đều được chứng
minh hoạt động độc lập" — quá rộng so với những gì đã đo. Tiêu chí 4, phép đo
QUYẾT ĐỊNH duy nhất cho tầng Odoo, chỉ đo **MỘT tool, MỘT chiều**:
`ai-warehouse` bị Odoo chặn ghi trên `account.move` (bảng so sánh 2 dòng ở
trên). Không có phép đo tương đương cho: chiều ngược lại (`ai-accounting` có
bị Odoo chặn ghi `stock.picking`/`sale.order` không?), hay bất kỳ tool nào
khác trong 16 khai báo `other_dept` của `roles.py`. Kết quả thật của việc đi
kiểm — xem ngay dưới — là tầng Odoo **không** đồng nhất: nó cưỡng chế được ở
một số cặp (role, tool) và không cưỡng chế được ở một số cặp khác, tùy độ
mịn của nhóm quyền Odoo chuẩn.

### Các khoảng trống tầng Odoo đã biết (final-review Fix 2, đo thật)

Kiểm bằng `scripts/check_role_odoo_consistency.py` (gọi `has_access()` trực
tiếp trên tài khoản Odoo của từng vai, bỏ qua hoàn toàn backend/LLM — cùng
kiểu phép đo tiêu chí 4, nhưng phủ hết các tool khai trong `roles.py` thay vì
một tool) tìm ra 4 khai báo `other_dept` **không có backstop ở tầng Odoo**:

| Vai (tài khoản Odoo) | Tool bị chặn ở agent | Nhưng Odoo thực ra CHO PHÉP |
|---|---|---|
| `accounting` (`ai-accounting`) | `deliver_order` | ghi `stock.picking` |
| `accounting` (`ai-accounting`) | `validate_picking` | ghi `stock.picking` |
| `accounting` (`ai-accounting`) | `internal_transfer` | tạo `stock.picking` |
| `warehouse` (`ai-warehouse`) | `confirm_sale_order` | ghi `sale.order` |

Đây **không phải lỗi code** — nhóm quyền chuẩn của Odoo ("Inventory / User",
"Sales / User"...) không tách nhỏ tới mức phân biệt "được giao hàng" khỏi
"được điều chỉnh tồn kho", nên cấp quyền qua nhóm kéo theo cấp luôn cả cụm.
Hồ sơ chính sách hiện dùng (`small-business`) chấp nhận cưỡng chế yếu ở
những nghiệp vụ này — đúng tinh thần "doanh nghiệp nhỏ gần như không có gì bị
cấm tuyệt đối" (`roles.py` docstring) — nhưng **4 tool này chỉ được chặn ở
tầng agent**: một cách nào đó bỏ qua được backend (không phải kịch bản tiêu
chí 4 đã đo, vốn giả định request đi qua MCP layer bình thường) sẽ không bị
Odoo chặn lại ở 4 chỗ này. `scripts/check_role_odoo_consistency.py` chạy
lại được, nên nếu granularity Odoo đổi (thêm/bớt nhóm quyền) mà không cập
nhật bảng này, GAP mới sẽ hiện ra tường minh thay vì nằm im.

---

## Đính chính lần ba (2026-08-11) — bảng map sai, không phải quyền Odoo sai

Việc parked "cần quyết định chính sách cho 2 tool kế toán" hoá ra chỉ đúng một
nửa. Đi kiểm bằng `has_access` trực tiếp thì thấy `ai-accounting` **đã có đủ**
mọi quyền `create_bill_from_po` cần. Nghi vấn: bảng map sai. Đọc lại code tool
thì đúng vậy — và không chỉ một dòng.

### 8/18 dòng `TOOL_ACCESS_MAP` sai hoặc thiếu

| Tool | Map cũ | Code thật gọi | |
|---|---|---|---|
| `create_bill_from_po` | `purchase.order create` | `write` (action_create_invoice trên PO **có sẵn**) + `account.move create/write` | sai |
| `return_order` | `stock.return.picking write` | `create` wizard + `.line write` + `stock.picking create` | sai |
| `send_delivery_email` / `send_invoice_email` | `mail.template create` | `mail.template` **read** + `mail.mail create/write/unlink` | sai |
| `register_payment` | `account.move write` | thêm `account.payment.register create` | thiếu |
| `internal_transfer` | `stock.picking create` | thêm `write` (`button_validate`) | thiếu |
| `inventory_adjustment` | `stock.quant write` | thêm `create` (nhánh chưa có quant — quyền **riêng**, chú thích cũ nói dùng chung gate write là sai) | thiếu |
| `scrap_product` | `stock.scrap create` | thêm `write` (`action_validate`) | thiếu |
| `create_credit_memo` | `account.move.reversal create` | thêm `write` (`refund_moves`) | thiếu |

### Số liệu thật sau khi sửa map

**9 khoảng trống + 1 lỗi chức năng** (không phải 2). `create_bill_from_po`
chạy được bằng `ai-accounting` — **chứng minh bằng phép thử sống**, không phải
suy luận: gọi `action_create_invoice` trên `P00068`, sinh hoá đơn NCC nháp
`id=108` (`in_invoice`, 900.0), rồi xoá, `P00068` trở lại `to invoice`.

Số 9 giữ nguyên nhưng đó là **trùng hợp**, không phải xác nhận: bảng map đứng
sau cả hai con số đều sai ở 8 dòng. Thành phần 9 khoảng trống nay đã được
kiểm chứng từng dòng và ghi vào `KNOWN_ODOO_GAPS` (trước đó chỉ ghi 4/9 — 5
khoảng trống thật nằm ngoài danh sách "đã biết").

### Lỗi chức năng duy nhất — ĐÃ SỬA

`create_invoice_from_order` thiếu đúng **một** thứ: `sale.advance.payment.inv`.
Mọi quyền khác nó chạm (`sale.order` read/write, `account.move` create/write,
`account.move.line` create) `ai-accounting` **đã có**.

Nhóm chuẩn duy nhất của Odoo cấp wizard này là `Sales / User: Own Documents
Only` — đo ra **52 cặp (model, operation) trên 25 model**, gồm `mrp.production`
create/write, toàn bộ CRM, và `sale.order create` (thứ này biến
`create_quotation` từ **chặn đúng** thành khoảng trống thứ 10). Nên tạo nhóm
hẹp `Youdoo AI / Sale Invoicing` mở đúng 1 model.

Kiểm chứng sống sau khi sửa: `ai-accounting` gọi wizard trên `S00115`, sinh
hoá đơn nháp `id=109` (`out_invoice`, 70.0), xoá, đơn trở lại nguyên trạng.
`check_role_odoo_consistency.py` exit 0, 36/36 dòng khớp, 0 BLOCKED.

### Phát hiện mới chưa từng ghi: tầng mail không có backstop Odoo

`send_delivery_email` hở với kế toán và `send_invoice_email` hở với kho —
**cả hai chiều**. Nhóm `Youdoo AI / Mail` cấp `mail.mail` cho *mọi* vai, còn
`mail.template` thì ai cũng đọc được. Bốn tool gửi mail là nhóm tool duy nhất
gây hậu quả **không thu hồi được**, và chúng chỉ được chặn ở tầng agent. Map
cũ (`mail.template create`) che mất điều này: nó hỏi một quyền không vai nào
có, nên báo "chặn đúng" ở cả hai vai.

### Bài học (lần thứ ba cùng một hạng lỗi)

Hai lần trước là *kết luận* sai vì đo thiếu. Lần này là **công cụ đo** sai hợp
đồng — cùng hạng lỗi với `has_access(ids, operation)` từng gọi sai hai lần.
Một công cụ kiểm tra không tự kiểm được chính nó: `check_role_odoo_consistency.py`
chạy sạch, exit 0, và vẫn cho số sai suốt hai ngày. Thứ duy nhất bắt được là
**chạy tool thật trên tài khoản thật** rồi đối chiếu với thứ công cụ dự đoán.

`TOOL_ACCESS_MAP` vẫn chép tay từ code tool, nên vẫn lệch được lần nữa. Chốt
drift cho bảng này đã được nêu ra nhưng **để lại cho đợt sau** (ngoài phạm vi
đợt này theo quyết định của user).
