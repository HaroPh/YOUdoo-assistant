# ADR-012: Khảo sát năng lực agent, phân quyền production, và bàn giao chéo bộ phận

**Ngày khảo sát:** 2026-08-09 (đo trực tiếp trên Odoo đang chạy, không suy đoán)
**Trạng thái:** khảo sát xong, kiến trúc đã phân tích, **3 quyết định còn mở**

File này ghi lại một phiên khảo sát trả lời câu hỏi *"nên thêm tính năng gì
cho agent?"*. Nó KHÔNG phải spec — chưa có thiết kế nào được duyệt để lên
plan. Giá trị lâu dài của nó nằm ở **số liệu thật đã đo** (để không phải đo
lại) và ở **ba luồng vấn đề hoá ra là một hệ thống**.

---

## 1. Số liệu thật đã đo (2026-08-09)

Odoo cài 10 application: `account`, `calendar`, `contacts`, `crm`, `mail`,
`maintenance`, `mrp`, `purchase`, `sale_management`, `stock`.

| Model | Số bản ghi | Ghi chú |
|---|---:|---|
| `stock.move.line` | 1.144 | Khối lượng lớn nhất hệ thống |
| `sale.report` | 252 | |
| `stock.picking` | 207 | **94 đang chờ xử lý** (assigned/confirmed/waiting) |
| `stock.quant` | 200 | Tất cả ở một vị trí `WH/Tồn kho` |
| `sale.order` | 171 | |
| `product.product` | 108 | |
| `account.move` | 105 | **38 chưa thanh toán xong, 27 quá hạn** |
| `purchase.order` | 81 | |
| `res.partner` | 61 | |
| `mrp.production` | 45 | |
| `crm.lead` | 43 | |
| `mail.activity` | 37 | **37/37 đều quá hạn** |
| `stock.lot` | 17 | |
| `maintenance.equipment` | 8 | Module đã cài, agent chưa đụng |
| `calendar.event` | 7 | Module đã cài, agent chưa đụng |
| `account.payment` | 7 | |
| `maintenance.request` | 5 | |

Công nợ quá hạn: **271.726** (22 hóa đơn khách nợ mình, 5 hóa đơn mình nợ NCC).

## 2. Phát hiện chính: agent giỏi **làm**, mù **việc gì cần làm**

Agent có **33 tool ghi** — phủ gần kín nghiệp vụ. Nhưng **mọi tool đọc đều là
tra cứu theo tên/mã**: người dùng phải biết trước cần hỏi về cái gì. Không
persona nào hỏi được câu quan trọng nhất mỗi sáng: *"hôm nay tôi cần xử lý gì?"*

Bằng chứng sắc nhất: `log_activity` **ghi** vào danh sách việc cần làm mà
**không tool nào đọc được**. Kết quả quan sát được: 37/37 activity đều quá hạn
— đúng triệu chứng của một danh sách việc không ai nhìn thấy.

Tương tự: có `validate_picking` để **hoàn tất** một phiếu kho, nhưng không có
gì để **xem hàng đợi** 94 phiếu đang chờ. Như có nút "Gửi" mà không có Inbox.

**Kết luận: nút thắt nằm ở đầu vào (đọc), không phải đầu ra (ghi). Không nên
thêm tool ghi.**

## 3. Số liệu đã BÁC BỎ giả thiết ban đầu

Đề xuất đầu tiên tên là *"Việc của tôi hôm nay"*. Đo xong thì chữ **"của tôi"**
sai với nửa kho:

- **91/94 phiếu kho chờ xử lý KHÔNG có người phụ trách** (`user_id` trống).
  Lọc theo "của tôi" sẽ cho nhân viên kho thấy **1 phiếu** thay vì 94 — tệ hơn
  hẳn không lọc.
- **93/94 phiếu đã quá hạn lịch hẹn.**

⇒ Trục hữu ích ở kho là **thời gian + loại phiếu**, không phải quyền sở hữu.
Ngược lại, activity **có** chủ thật (28 Mitchell Admin / 7 Marc Demo), nên
"của tôi" chỉ có nghĩa ở nửa văn phòng.

**Hệ quả thiết kế:** nửa kho KHÔNG phụ thuộc vào việc giải quyết danh tính —
có thể làm trước, độc lập.

## 4. Phân quyền: hiện trạng là "full quyền cho tất cả", do kiến trúc

Agent kết nối Odoo bằng **một tài khoản cố định** (`Mitchell Admin`, uid 2,
`ODOO_USERNAME` trong `.env`). Tài khoản đó có **Administrator trên MỌI
module**: Accounting, Inventory, Manufacturing, Purchase, Sales, Maintenance,
cộng `Role / Administrator`.

⇒ Mọi người dùng chat — kể cả nhân viên kho — đang thao tác với tư cách quản
trị viên toàn hệ thống. Đây không phải một lựa chọn đã cân nhắc; nó là hệ quả
mặc định.

### Giới hạn nên nằm ở tầng nào

| Tầng | Hiện trạng | Bản chất |
|---|---|---|
| **Odoo** (user riêng + nhóm quyền) | ❌ chưa có | Cưỡng chế ở tầng ORM, chặn cả đường code không lường trước |
| **Agent** (chức vụ → tập tool) | ❌ chưa có | Trải nghiệm + độ chính xác chọn tool |
| **MCP** (`ODOO_METHOD_OPERATION_MAP` + `write_actions_enabled()`) | ✅ có, nhưng **toàn cục** | Thô, không phân biệt người dùng |

**Nguyên tắc:** không bao giờ để tầng LLM là thứ duy nhất đứng giữa người dùng
và một hành động đặc quyền. LLM là thành phần kém tất định nhất trong stack.
Dự án này đã có sẹo đúng chỗ đó — cơ chế xác nhận ghi từng bị phát hiện **hoàn
toàn không hoạt động trong production** dù đã qua 6 vòng review (xem
`write-confirmation-ux-fix`).

### Lộ trình đề xuất, rẻ trước

1. **Bỏ tài khoản Administrator cho agent.** Tạo user Odoo riêng, cấp đúng
   quyền 33 tool cần. Chỉ sửa `.env`, không đụng code, nhưng giới hạn bán kính
   thiệt hại của mọi bug tương lai — kể cả bug chưa tồn tại. **Làm trước khi
   production.**
2. **Chức vụ → tập tool ở tầng agent.** Không chỉ là thuế bảo mật: nhồi 33 tool
   vào một prompt làm hỏng khả năng chọn tool, mà dự án đang đo chính chỉ số đó
   (`tool_acc`, `dangerous_misroute` trong `backend/evals/`). Ít tool liên quan
   ⇒ chọn đúng hơn.
3. **Mỗi nhân viên một credential Odoo**, agent thao tác *với tư cách* họ. Đây
   mới là cưỡng chế thật + audit trail đúng người. Là refactor thật:
   `mcp-servers/odoo/odoo_call.py` đang cache một `_uid` toàn cục và dùng một
   `ODOO_PASSWORD` duy nhất.

### Bẫy cần tránh

Đừng cắt quyền theo trực giác sơ đồ tổ chức. Tool đọc của agent **cắt ngang
domain một cách hợp lệ**: `create_quotation` cần đọc tồn kho, `check_po_matching`
cần đọc cả mua lẫn kế toán. Khoá nhân viên bán hàng khỏi quyền đọc kho là làm
hỏng luồng báo giá. Giới hạn phải bám **phụ thuộc tool thực tế**, không theo
chức danh.

Ngoài ra `write_actions_enabled()` hiện là công tắc **toàn cục** — thế giới có
chức vụ nhiều khả năng cần nó theo từng vai.

## 5. Bàn giao chéo bộ phận

Câu hỏi: nhân viên kho đụng việc thuộc quyền kế toán thì agent nên làm gì?

### Phải tách đôi trước

- **(A) Đọc chéo domain** — kho hỏi *"đơn này khách thanh toán chưa?"*: KHÔNG
  phải vi phạm phân quyền về bản chất, mà là thông tin cần để làm đúng việc
  mình (có nên xuất hàng không). Chặn là vừa khó chịu vừa sai nghiệp vụ.
- **(B) Ghi chéo domain** — kho muốn *phát hành hóa đơn*: đây mới là ranh giới
  thật, nguyên tắc **phân tách nhiệm vụ**. Kế toán độc quyền phát hành không
  phải để giấu, mà để kiểm soát.

Gộp hai cái làm một là lỗi kinh điển. Khi làm bước 3 ở §4: cấp nhóm quyền
**đọc rộng tay**, siết nhóm quyền **ghi**. Odoo phân tách read/write đủ mịn.

### Với ranh giới ghi: dùng activity, không dùng mail

| | Activity | Mail nội bộ |
|---|---|---|
| Gắn vào đúng bản ghi | ✅ | ❌ phải chép mã qua |
| Có trạng thái / đóng được | ✅ | ❌ gửi rồi là xong |
| Có hạn + người chịu trách nhiệm | ✅ | ❌ |
| Hiện trong Odoo UI của người nhận | ✅ | ❌ |
| Dấu vết kiểm toán | ✅ | ❌ |

> **Quy tắc: mail = ra ngoài (khách, NCC). Activity = vào trong (đồng nghiệp).**

*"Gợi ý liên hệ bộ phận kế toán"* là phương án yếu nhất — đẩy gánh nặng thuật
lại bối cảnh về cho con người, không gì được ghi nhận. Chỉ nên là đường lui khi
không xác định được người nhận.

### Điều kiện tiên quyết

Thiết kế bàn giao **vô nghĩa cho tới khi agent ngừng chạy bằng tài khoản
admin**. Hôm nay kho yêu cầu phát hành hóa đơn thì agent **cứ thế làm** —
không có bức tường nào để mà bàn giao. Thứ tự bắt buộc: chặn được trước, rồi
mới tới bàn giao đẹp.

### Cảnh báo thực tế

- **Chống spam:** mỗi lần bị chặn đều tạo activity ⇒ kế toán ngập. Cần kiểm tra
  đã có activity đang mở trên cùng bản ghi chưa.
- **`log_activity` hiện quá hẹp để làm kênh bàn giao:** chỉ chạy trên
  `crm.lead` (hardcode), chỉ nhận Call/Meeting, và **không có tham số người
  nhận** — luôn gán về chính tài khoản agent. Cần tổng quát hoá: mọi model +
  thêm người nhận. Hình dạng giống hệt việc đã làm với `EmailCfg`
  (`2026-08-08-mail-trigger-points`) — factory tham số hoá thay bản hardcode.

## 6. Điểm hội tụ — đây là MỘT hệ thống, không phải ba dự án

Ba luồng trên chia sẻ đúng một nền móng:

```
        ánh xạ danh tính (user chat → user Odoo)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   "việc của tôi"   phân quyền      bàn giao chéo
   (hàng đợi)       theo chức vụ    bộ phận
        │                               │
        └────────── activity ───────────┘
              (vừa là hộp thư đến,
               vừa là kênh bàn giao)
```

- Ánh xạ danh tính là nền của cả ba.
- Activity vừa là hộp thư đến của hàng đợi, vừa là kênh bàn giao.
- Phân quyền là thứ **tạo ra** nhu cầu bàn giao ngay từ đầu.

Backend đã nhận sẵn header `x-openwebui-user-id` (`backend/src/main.py:117`)
nhưng mới chỉ dùng để tách luồng hội thoại — chưa bao giờ ánh xạ sang user
Odoo. Đó là nửa hạ tầng đã có cho bước ánh xạ.

## 7. Quyết định còn mở

1. **Danh tính cho phần activity**: hiện tất cả kèm tên chủ mỗi dòng (không cần
   cấu hình) / ánh xạ user Open WebUI → user Odoo / agent hỏi "bạn là ai".
   *Lưu ý: nếu đằng nào cũng đi tới §4 bước 3 thì ánh xạ chính là bước một, và
   hai câu hỏi này là một.*
2. **Có làm nửa kho trước không** (không phụ thuộc quyết định 1).
3. **Thời điểm siết phân quyền** — trước hay sau khi thêm tính năng đọc.

## 8. Mảng đã phủ tốt, không cần làm lại

Chuỗi bán/mua, hóa đơn + thanh toán, BOM/lệnh sản xuất, CRM lead, tồn kho theo
sản phẩm, lot/serial, đối chiếu PO, công nợ đối tác, hóa đơn quá hạn, và 4 điểm
nối gửi mail (`2026-08-08-mail-trigger-points`).

Hai module **đã cài nhưng agent chưa đụng**: `maintenance` (8 thiết bị, 5 yêu
cầu) và `calendar` (7 sự kiện). Nghe hấp dẫn vì "mới", nhưng số liệu nói là ít
dùng — **ưu tiên thấp**, ghi lại ở đây để khỏi bị cám dỗ.
