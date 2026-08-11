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
