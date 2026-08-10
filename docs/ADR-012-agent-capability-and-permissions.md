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

## 7. Quyết định đã chốt (cập nhật 2026-08-09, sau khảo sát vòng 2)

Chủ dự án chọn **hướng kiến trúc production-ready**, không phải trình diễn
tính năng. Ba vai, đặt tên tiếng Anh: **`admin`, `warehouse`, `accounting`**.

### 7.1 Ba tầng danh tính, không tầng nào tự khai

```
Nhân viên đăng nhập Open WebUI (:3002)      ← xác thực thật, có mật khẩu
            │  x-openwebui-user-id (header)
   backend tra bảng ánh xạ user_id → role   ← phía server, người dùng không sửa được
            │
   chọn graph + tiến trình MCP + credential Odoo
            │
   Odoo cưỡng chế theo nhóm quyền           ← lớp cuối, không tin code phía trên
```

**Phương án "3 model trong dropdown" đã bị LOẠI.** Nó cho phép người dùng tự
chọn vai — tức tự khai, không xác thực. Vai phải suy từ tài khoản đăng nhập.

Hai điều kiện kèm theo:

- `docker-compose.yml` hiện **không** đặt `ENABLE_FORWARD_USER_INFO_HEADERS`,
  nên header nhận dạng **chưa bao giờ được gửi sang**. `main.py` đã có code
  đọc `x-openwebui-user-id` nhưng thực tế luôn rỗng, và `thread_id` đang rơi
  về phương án dự phòng (băm câu hỏi đầu tiên). Phải bật.
- Bảng ánh xạ khoá theo **`user_id` (chuỗi mờ)**, KHÔNG theo email — tôn trọng
  quyết định PII đã ghi ở `main.py:114-118` ("name/email/role là PII, không bao
  giờ được đọc hoặc ghi log").

⇒ Quyết định mở số 1 của bản cũ (**danh tính cho activity**) **đã được giải
quyết** bởi chính chuỗi này: có ánh xạ rồi thì "việc của tôi" lọc đúng người
miễn phí.

### 7.2 Bốn credential, không phải ba — đường ĐỌC không đi qua MCP

Phát hiện khi khảo sát: có **ba** đường ra Odoo, không phải một.

| Đường | Chạy ở | Credential |
|---|---|---|
| Ghi (33 tool) | tiến trình MCP | env của MCP |
| **Đọc (27 tool `erp_query`)** | **thẳng từ backend** (`gateway.py:67-69`) | `ODOO_USERNAME` của backend |
| Kiểm tra write-gate | backend (`write_gate.py:31`) | như trên |

Nên kiến trúc "3 tiến trình MCP" chỉ phủ phần GHI. Phân bổ đúng:

| Tài khoản | Dùng ở | Quyền |
|---|---|---|
| `ai-readonly` | backend (đọc + write-gate) | Đọc rộng mọi module, **không một quyền ghi nào** |
| `ai-admin` | MCP :8003 | Ghi đầy đủ |
| `ai-warehouse` | MCP :8004 | Ghi kho |
| `ai-accounting` | MCP :8005 | Ghi kế toán |

Điều này làm thiết kế **gọn hơn**, vì khớp đúng nguyên tắc "đọc rộng tay, siết
ghi" ở §5: đọc chéo domain không gãy, backend không cần sửa cho phần đọc, và
đường đọc trở thành read-only **thật** (kể cả bị chiếm quyền hoàn toàn cũng
không ghi được — vì tài khoản không có quyền, không phải vì code từ chối).

**Đánh đổi có chủ ý:** một credential đọc dùng chung ⇒ mọi vai đọc được mọi dữ
liệu. Đúng với nghiệp vụ (kho cần biết đơn đã thanh toán chưa trước khi xuất).
Nếu sau cần siết: mọi hàm `erp_query` đều nhận `gw=None`, tức gateway tiêm được
theo từng lời gọi — chuyển sang gateway theo vai là việc làm được, không phải
viết lại.

### 7.3 Cô lập theo tiến trình, không phải 1 tiến trình giữ 3 credential

`MCP_ODOO_PORT`, `ODOO_USERNAME`, `ODOO_PASSWORD` **đều đã lấy từ env** — nên
chạy 3 tiến trình MCP với 3 credential **không cần sửa dòng nào** trong
`mcp-servers/odoo/`.

Lý do chọn cô lập tiến trình: tiến trình `warehouse` **không hề nắm** credential
admin. Một bug định tuyến vai khi đó chỉ dẫn tới "sai bộ tool", chứ không phải
"leo thang đặc quyền" — bảo đảm khác hẳn về chất so với "code chọn đúng
credential", thứ chỉ đúng chừng nào code không có bug.

**Phương án truyền `role` như tham số tool đã bị LOẠI**: tham số tool do LLM
điền, mà LLM là thành phần ta tin cậy ít nhất. Đó là bảo mật giả.

### 7.4 Hai lớp: lọc ở backend, cưỡng chế ở Odoo

Mỗi tiến trình MCP vẫn lộ đủ 33 tool (cùng code). Backend **lọc xuống tập cho
phép** trước khi dựng graph:

- LLM chỉ thấy tool liên quan → chọn đúng hơn, prompt gọn hơn (lợi ích **chất
  lượng**, không chỉ bảo mật — dự án đang đo `tool_acc`/`dangerous_misroute`)
- Nếu bộ lọc có bug → Odoo vẫn chặn

Phần liệt kê tool trong prompt phải **sinh động từ `allowed_tools`**, không viết
tay 3 prompt cứng — nếu không chúng sẽ trôi lệch, đúng lớp lỗi đã bắt được ở
`mail-trigger-points` (`WRITE_TOOL_NAMES` thiếu 4 tool mail khiến chỉ số
"misroute nguy hiểm" mù với đúng những tool gửi mail ra ngoài).

### 7.5 Cạm bẫy: `thread_id` chưa mang vai

`thread_id` suy từ người dùng + cuộc chat, **không có vai**. Kịch bản hỏng: đang
ở vai warehouse, agent hỏi xác nhận một lệnh ghi → đổi vai → trả lời "có" →
LangGraph resume interrupt trong graph **không có node đó**. Cách chặn: đưa vai
vào `thread_id`.

### 7.6 Phạm vi vòng đầu

Khi một vai chạm việc ngoài quyền: vòng này chỉ làm **thông báo rõ ràng**.
Phần **bàn giao bằng activity** để vòng sau — cần tổng quát hoá `log_activity`
(§5), đủ lớn để đứng riêng.

### Còn mở

- Nhóm quyền Odoo cụ thể cho từng vai → **đang đo** (§9).
- Có làm hàng đợi kho (§2, §3) trong cùng vòng hay tách.

## 8. Mảng đã phủ tốt, không cần làm lại

Chuỗi bán/mua, hóa đơn + thanh toán, BOM/lệnh sản xuất, CRM lead, tồn kho theo
sản phẩm, lot/serial, đối chiếu PO, công nợ đối tác, hóa đơn quá hạn, và 4 điểm
nối gửi mail (`2026-08-08-mail-trigger-points`).

Hai module **đã cài nhưng agent chưa đụng**: `maintenance` (8 thiết bị, 5 yêu
cầu) và `calendar` (7 sự kiện). Nghe hấp dẫn vì "mới", nhưng số liệu nói là ít
dùng — **ưu tiên thấp**, ghi lại ở đây để khỏi bị cám dỗ.
