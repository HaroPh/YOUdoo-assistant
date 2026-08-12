# Live-verify — tổng quát hoá `log_activity` (2026-08-12)

**Môi trường:** worktree `log-activity-general` (nhánh
`feat/log-activity-generalisation`), đo **TRƯỚC merge**. Stack cũ dừng hẳn
trước khi khởi động stack của nhánh.

## Kết quả: 7/7 kịch bản đúng thiết kế

| # | Kịch bản | Kết quả |
|---|---|---|
| 1 | admin → `sale.order` S00119, giao Marc Demo | tạo được |
| 2 | **kho → `stock.picking`, giao `ai-accounting`** | **tạo được — phép đo QUYẾT ĐỊNH** |
| 3 | `Maintenance Request` trên `sale.order` | từ chối: *"chỉ dùng được cho maintenance.request"* |
| 4 | `assignee` gõ sai tên | từ chối, nêu tên đã gõ |
| 5 | loại không tồn tại (`"goi dien"`) | từ chối **kèm danh sách hợp lệ**: Call, Document, Email, Meeting, To-Do |
| I3a | **kho → `crm.lead`** | từ chối, nhưng bằng fault Odoo thô — xem §3 |
| I3b | **kho → `account.move`** | từ chối, cùng vấn đề |

Kịch bản 5 chứng minh F3 của fix wave: trước đó lời từ chối cụt lủn và xuất
hiện **sau** cổng xác nhận; nay nó nêu đúng các loại dùng được cho model đó,
truy từ Odoo chứ không từ danh sách viết tay. Danh sách trả về **loại trừ**
`Maintenance Request` — đúng, vì loại đó gắn cứng `maintenance.request`.

## 1. Nhóm quyền mới hoạt động

`scripts/odoo_setup_ai_accounts.py` chạy lần đầu **tạo** `Youdoo AI / Activity`,
lần hai in "nhóm đã có" — idempotent. Đo trước/sau:

| tài khoản | `ir.model` read trước | sau |
|---|---|---|
| `ai-admin` | True | True |
| `ai-warehouse` | **False** | **True** |
| `ai-accounting` | **False** | **True** |
| `ai-readonly` | False | **False** (đúng — tài khoản đọc không tạo activity) |

Kịch bản 2 là phép đo quyết định vì nó đi qua đúng lệnh `odoo("ir.model",
"search", ...)` mà hai vai non-admin trước đây không có quyền gọi.

## 2. Đường coordinator — đo qua đúng cổng vào thật

Toàn bộ 7 kịch bản trên gọi **thẳng** cổng MCP, nên chúng không chạm tầng
coordinator (Task 2). Đo riêng qua `POST :8002/v1/chat/completions`:

Yêu cầu: *"tạo việc cần làm cho đơn hàng S00119: gọi lại khách xác nhận giao
hàng, giao cho Marc Demo"*

```
Lên lịch Call cho 'S00119': gọi lại khách xác nhận giao hàng
— hạn 2026-08-12 — giao Marc Demo.
Bạn xác nhận giúp mình nhé?
```

Xác nhận, rồi đọc lại Odoo:

```
{'summary': 'gọi lại khách xác nhận giao hàng',
 'user_id': [5, 'Marc Demo'], 'activity_type_id': [2, 'Call'],
 'date_deadline': '2026-08-12', 'res_name': 'S00119'}
```

Chuỗi đầu-cuối được chứng minh: planner sinh `res_model`/`ref`/`assignee` →
coordinator giải `S00119` trên `sale.order` → tool giải `"Marc Demo"` thành
`user_id` 5 → Odoo. Người nhận cũng hiện đúng trong câu xác nhận, tức
`assignee_note` của Task 2 hoạt động.

## 3. Phát hiện: fault Odoo thô lộ ra người dùng (I3)

Final review dự đoán và phép đo xác nhận. Vai kho gắn activity vào `crm.lead`
hoặc `account.move`:

```
Lỗi khi lên lịch hoạt động: <Fault 4: "Xin lỗi, bạn không được phép truy cập
vào dữ liệu 'Lead' (crm.lead).\n\nThao tác này được phép cho các nhóm sau ...
```

**Chặn được** — không có bản ghi nào được tạo. Nhưng thông điệp là chuỗi fault
thô của Odoo, liệt kê cả tên nhóm quyền. Ba điểm đáng ghi:

1. Đây là **bề mặt mới do chính nhánh này tạo ra**: trước đó tool chỉ nhận
   `crm.lead`, nên không có cách nào yêu cầu một model mà vai không đọc được.
2. `prompts.py` quảng cáo **cả sáu model cho cả hai vai không điều kiện**,
   trong khi vai kho không có nhóm CRM nào và vai kế toán cũng vậy.
3. Nguyên nhân sâu là thứ spec §10 đã đo: Odoo gác `mail.activity` theo quyền
   đọc **tài liệu đính kèm**, không theo quyền trên `mail.activity`.

### ĐÃ SỬA (commit `ef3c5ba`) và đo lại sống

Chọn hướng bắt lỗi và trả câu sạch. Cách phát hiện **không** dựa vào chuỗi
fault: thông điệp kia là tiếng Việt chỉ vì ngôn ngữ của tài khoản Odoo này, ở
cài đặt khác nó là tiếng Anh và phép kiểm sẽ âm thầm ngừng hoạt động. Thay vào
đó bọc riêng **lệnh `search_read` đầu tiên trên model đích** — lỗi ở đúng chỗ
đó chỉ có một nghĩa cần nói với người dùng, và điều đó biết được từ **nơi** ném
lỗi chứ không từ **nội dung** lỗi.

Đo lại sau khi khởi động lại MCP:

```
I3a KHO -> crm.lead      -> ok=False
    Không đọc được dữ liệu 'crm.lead' — model này có thể không tồn tại
    hoặc tài khoản hiện tại không có quyền truy cập.
I3b KHO -> account.move  -> ok=False   (cùng dạng)
KB2 KHO -> stock.picking -> ok=True    (không chặn nhầm)
```

Câu chữ cố ý **không** khẳng định chắc chắn là lỗi quyền: cùng lệnh đó cũng
hỏng khi model không tồn tại, nên nói "có thể không tồn tại hoặc không có
quyền" là đúng mức thông tin thực có.

**Chưa làm, còn trong backlog:** lọc danh sách model theo vai ngay trong prompt.
Đó mới là gốc — `prompts.py` vẫn quảng cáo cả sáu model cho cả hai vai. Bản sửa
này đóng phần lộ thông tin và làm thông điệp dùng được, không đóng phần quảng
cáo thừa.

## 4. Script nhất quán quyền

```
warehouse   log_activity   has  has  OK
accounting  log_activity   has  has  OK
Không có sai khác ngoài dự kiến — đúng 9/9 gap đã biết
```

exit 0, và số gap **không đổi** — thêm một tool vào `own` không mở thêm khoảng
trống nào.

Dòng mới có răng thật: trước khi áp nhóm, `ir.model` read là `False` với hai
vai, nên cặp `("ir.model", "read")` mà fix wave thêm vào sẽ báo `BLOCKED`. Nếu
chỉ khai `("mail.activity", "create")` như bản đầu, dòng này sẽ báo OK dù nhóm
có được áp hay không — đúng lỗ hổng final review chỉ ra.

## 5. Dọn dẹp

Bốn `mail.activity` sinh ra khi đo (id 40, 41, 42 và một bản trung gian) đều đã
xoá; đọc lại `sale.order` 119 và `stock.picking` 208 không còn activity nào.

## 6. Còn lại, chưa sửa

- ~~R1~~ và ~~I3~~ — đã sửa trong `ef3c5ba`, xem §3.
- **Lọc model theo vai trong prompt** — gốc thật của I3, chưa làm.
- M1 (nhánh `if not model_ids` không chạm tới) và M2 (nhánh ghi chú hoá đơn
  nháp chưa có test tầng coordinator) — đã hoãn có ghi nhận.
