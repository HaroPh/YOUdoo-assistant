# Tóm tắt hóa đơn trước cổng xác nhận ghi (post_invoice / register_payment)

**Ngày:** 2026-08-06
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

Hai thao tác đụng tiền — `post_invoice` (phát hành hóa đơn nháp) và
`register_payment` (ghi nhận thanh toán) — hiện **không** có node điều phối
riêng, nên rơi vào nhánh fallback chung của `erp_write_planner`
(`backend/src/agents/nodes.py:259-266`). Người dùng chỉ thấy:

```
**Phát hành hóa đơn**
(post_invoice: partner_name=Acme Corporation)
```

rồi phải trả lời có/không. Họ **không biết hóa đơn nào và bao nhiêu tiền**.

### 1.1. Đây là lỗ hổng an toàn, không phải vấn đề thẩm mỹ — đo trên Odoo thật

Truy vấn Odoo thật ngày 2026-08-06 qua `erp_query.gateway`:

- Có **5 hóa đơn nháp**, **tất cả** thuộc cùng một đối tác
  "Acme Corporation"; **4 trong số đó trùng y hệt số tiền `140.0`**.
- Hóa đơn nháp có `name = False` — **chưa có số** (Odoo chỉ cấp số lúc phát
  hành). Điều này khớp docstring của chính tool
  (`mcp-servers/odoo/tools/accounting.py:19`).

Hệ quả: `post_invoice(partner_name="Acme")` **không thể** xác định được hóa
đơn nào chỉ từ những gì người dùng nhìn thấy — và kể cả tham số phân biệt
`amount=140` cũng không tách được 4 bản nháp trùng nhau. Logic
`resolve_unique` trong tool (`mcp-servers/odoo/tools/accounting.py:70-77`)
sẽ báo lỗi mơ hồ — **nhưng chỉ SAU khi người dùng đã bấm xác nhận**. Trường
hợp ngược lại còn tệ hơn: khi khớp đúng một bản nháp, hệ thống phát hành
luôn mà người dùng chưa từng thấy số tiền.

### 1.2. Bất đối xứng giữa hai tool — đã đo, không suy đoán

Hai tool tuy đều "đụng tiền" nhưng khác bản chất, và spec này xử lý khác
nhau:

| | `post_invoice` | `register_payment` |
|---|---|---|
| Tác động lên | hóa đơn **nháp** (`state=draft`) | hóa đơn **đã phát hành** (`state=posted`) |
| Đối tượng có số? | **Không** (`name=False`) | **Có** (đo thật: `INV/2026/00028`) |
| Độ mơ hồ khi resolve | **Cao** — chỉ tìm được theo tên đối tác | Thấp *nếu* có `invoice_ref`; **cao y hệt** nếu chỉ có `partner_name` (tool nhận cả hai) |
| Con số quyết định | `amount_total` | **`amount_residual`** |

`amount_residual` là con số đúng cho `register_payment` vì tool **luôn thanh
toán đủ số dư còn lại**, không thanh toán một phần — docstring nói rõ điều
này (`mcp-servers/odoo/tools/accounting.py:148-150`). Hiển thị
`amount_total` ở đây sẽ **sai** với hóa đơn đã trả một phần
(`payment_state = partial`).

## 2. Phạm vi

**Có trong phạm vi:** `post_invoice`, `register_payment` — cả hai đường vào:
gọi trực tiếp, và bước trong chuỗi tự động (`auto_chain`).

**Cố ý KHÔNG làm:** `create_invoice_from_order`, `create_bill_from_po`.
Ba lý do:

1. Chúng **tạo** bản nháp — tại thời điểm hỏi xác nhận, hóa đơn *chưa tồn
   tại*, không có gì để đọc dòng hàng. Muốn preview phải đọc từ đơn nguồn —
   đường đọc khác hẳn, thuộc phạm vi khác.
2. Tạo nháp **có thể hoàn tác**; phát hành và chuyển tiền thì không.
3. Chúng nhận `order_ref` tường minh (vd `"S00012"`) nên không có vấn đề mơ
   hồ mục 1.1.

**Cố ý KHÔNG làm:** cờ môi trường bật/tắt hành vi mới. Các kill-switch sẵn
có trong repo (`ERP_SKILLS_ENABLED`, `write_actions_enabled`) đều phục vụ
**an toàn**, không phải sở thích UX; thêm một trục cấu hình chỉ nhân đôi ma
trận test mà không đóng rủi ro nào.

## 3. Kiến trúc

Theo đúng khuôn `create_credit_memo` — coordinator gần nhất cũng đụng hóa
đơn (`backend/src/agents/returns_write.py:115-151`): backend resolve → render
→ `_interrupt` → gọi tool bằng **ID đã resolve**.

### 3.1. Năng lực đọc mới — `backend/src/erp_query/accounting.py`

Hiện **không hàm nào đọc được hóa đơn nháp**: cả bốn hàm đều hardcode
`state = "posted"` (`accounting.py:17`, `:37`, `:72-77`), và
`find_posted_invoice` còn chủ động báo lỗi nếu chưa phát hành
(`accounting.py:116-118`). Cũng không đường nào đọc dòng hàng — `_FIELDS`
(`accounting.py:7-8`) không có `invoice_line_ids`.

Thêm ba hàm:

**`get_invoice_detail(invoice_id)`** — đọc `account.move`
(`partner_id`, `invoice_date`, `amount_total`, `amount_residual`,
`move_type`, `state`, `name`) + dòng hàng từ `account.move.line`, lọc
**`display_type = 'product'`**.

> Bộ lọc `display_type` là **bắt buộc**, không phải tối ưu: đo thật trên
> Odoo cho thấy `search_read('account.move.line', [['move_id','=',105]])`
> trả về **cả dòng `payment_term`** (dòng đối ứng phải thu/phải trả, số
> tiền 0). Thiếu bộ lọc thì bảng tóm tắt có một dòng rác 0 đồng.

Trường dòng hàng: `product_id`, `quantity`, `price_subtotal`. Dùng
`product_id[1]` làm tên hiển thị — **không** dùng `line.name`, vì đo thật
thấy trường đó chứa mô tả nhiều dòng
(`'[FURN_0789] Individual Workplace\n[FURN_0...'`).

**`find_draft_invoices(partner_name, amount=None, invoice_date=None)`** —
cho đường gọi trực tiếp `post_invoice`. Trả **danh sách** (không phải một),
để coordinator tự xử mơ hồ bằng `_interrupt` kiểu `disambiguation` thay vì
để tool báo lỗi sau khi đã xác nhận. Domain khớp domain của tool
(`mcp-servers/odoo/tools/accounting.py:57-64`).

**`find_open_invoices(invoice_ref=None, partner_name=None, amount=None,
invoice_date=None)`** — cho đường gọi trực tiếp `register_payment`. Trả
**danh sách**, đối xứng với `find_draft_invoices`, vì tool nhận **cả**
`invoice_ref` **lẫn** `partner_name` (`mcp-servers/odoo/tools/accounting.py:144-146`)
— đường `partner_name` mơ hồ y hệt mục 1.1 nên phải xử lý cùng cách.

Domain: `state = "posted"` **và** `payment_state in ("not_paid", "partial")`
— hóa đơn đã trả hết thì không còn gì để thanh toán, đưa vào danh sách chọn
chỉ gây nhiễu.

`find_posted_invoice` hiện có **không dùng lại được**: nó lọc cứng
`move_type = "out_invoice"` (`accounting.py:106`) trong khi
`register_payment` phục vụ cả `in_invoice` (mình trả NCC), nó không đọc
`amount_residual`, và nó chỉ nhận số hóa đơn chính xác chứ không nhận tên
đối tác.

Gateway **không cần sửa**: nó dùng denylist chứ không phải allowlist, và
`account.move.line` không nằm trong `MODEL_DENYLIST` (`gateway.py:10-13`).

### 3.2. Node điều phối mới — `backend/src/agents/invoice_write.py`

Hai node, đăng ký vào `WRITE_COORDINATORS`
(`backend/src/agents/write_registry.py:25-44`). Việc đăng ký này khiến
**đường gọi trực tiếp chạy đúng mà không sửa một dòng routing nào**:
`erp_write_planner` đã có sẵn nhánh "tool thuộc `COORDINATED_TOOLS` thì
không interrupt tại chỗ, để coordinator tự lo" (`nodes.py:256-257`), và
`_route_after_write_planner` đã dispatch theo registry
(`graph.py:66-74`, `graph.py:89-91`).

**`make_post_invoice_node`**: lấy `invoice_id` từ args nếu có (đường chuỗi);
nếu không thì `find_draft_invoices(...)` → 0 kết quả: báo lỗi; >1: `_interrupt`
disambiguation liệt kê (đối tác — số tiền — ngày); 1: dùng luôn. Sau đó
`get_invoice_detail` → render → `_interrupt` xác nhận → `tool.ainvoke({"invoice_id": ...})`.

**`make_register_payment_node`**: cùng khuôn, nhưng resolve qua
`find_open_invoices(...)` (ưu tiên `invoice_ref` nếu có, không thì
`partner_name`), và **số tiền hiển thị là `amount_residual`** — số sẽ thực
sự chuyển (§1.2).

Định dạng bản tóm tắt (khớp `render_draft` của `create_order.py:43-53`).
`post_invoice` — hóa đơn nháp chưa có số nên phải định danh bằng đối tác +
ngày:

```
Hóa đơn nháp của Acme Corporation — ngày 2026-08-06:
  - [FURN_0789] Individual Workplace × 20 = 17.520
  Tổng: 17.520

Bạn có muốn thực hiện thao tác sau không? (có / không)
```

`register_payment` — hóa đơn đã phát hành nên có số; dòng cuối là **số dư
còn lại**, tức số tiền sẽ chuyển:

```
Thanh toán hóa đơn INV/2026/00028 — Acme Corporation:
  - [FURN_7777] Office Chair × 2 = 140
  Tổng hóa đơn: 350
  Số dư sẽ thanh toán: 350

Bạn có muốn thực hiện thao tác sau không? (có / không)
```

Câu xác nhận **bắt buộc** dùng `WRITE_CONFIRM_SUFFIX` (`prompts.py`), không
tự chế câu mới — bất biến C tầng 3 đã gom 19 chỗ về hằng số này.

### 3.3. Chuỗi tự động — `continuation.py` + `graph.py`

Hiện `write_continuation` set `confirmed: True` rồi bắn thẳng vào executor,
**bỏ qua interrupt** (`continuation.py:38-45`), và
`_route_after_continuation` chỉ có hai đích `erp_write_executor` / `END`
(`continuation.py:54-57`, target map ở `graph.py:95-96`).

Sửa: khi bước kế nằm trong một **tập tường minh** `CONFIRM_IN_CHAIN =
frozenset({"post_invoice", "register_payment"})`, **không** set `confirmed`,
và `_route_after_continuation` trả về node coordinator — dùng lại đúng quy
tắc dispatch mà `_route_after_write_planner` đã dùng. Target map ở
`graph.py:95-96` mở rộng bằng chính cách đã dựng `write_targets`
(`graph.py:89-90`).

> **Vì sao là tập tường minh, KHÔNG phải điều kiện `in COORDINATED_TOOLS`:**
> kiểm chứng bằng script đối chiếu registry cho thấy `convert_lead` và
> `update_vendor_pricing` **vừa** là coordinated tool **vừa** xuất hiện như
> bước trong `NEXT_STEPS`. Dùng điều kiện rộng sẽ đổi luôn hành vi của hai
> tool đó — vượt phạm vi §2 và không có tiêu chí nghiệm thu nào phủ.
>
> Điều này phơi ra một điểm không nhất quán **có sẵn từ trước**, nằm ngoài
> phạm vi spec này: hôm nay khi chuỗi chạy tới `convert_lead`, nó set
> `confirmed=True` rồi vào thẳng `erp_write_executor` — tức **bỏ qua node
> coordinator của chính nó**, kể cả phần resolve và cổng xác nhận riêng mà
> node đó có. Ghi nhận lại đây để lần sau có người xét; **không** sửa trong
> spec này.

Ba điều kiện khiến thay đổi này an toàn, **đã kiểm chứng trên code**:

1. Mọi coordinator đã có sẵn cạnh về `write_continuation`
   (`graph.py:93-94`) — chuỗi chạy tiếp được sau khi coordinator xong.
2. `auto_chain` **sống sót** qua coordinator: `_finish`
   (`returns_write.py:20-23`) không ghi vào channel đó, mà channel LangGraph
   không được ghi thì giữ nguyên giá trị.
3. Nhánh **người dùng từ chối giữa chuỗi** dừng sạch: lúc đó `last_write`
   đã là `None` (write_continuation trả `last_write=None` ở **mọi** nhánh),
   nên rơi đúng nhánh terminal im lặng — đúng như comment sẵn có mô tả
   ("*Cancel (lw falsy): im lặng — 'Đã hủy.' của coordinator đã đủ*").

## 4. Thay đổi hành vi có chủ đích

Chuỗi khai-báo-một-lần sẽ **dừng hỏi lại ở bước đụng tiền**, khác thiết kế
hiện tại. Đây là đảo một quyết định được ghi chú tường minh trong
`continuation.py:8-11`.

**Lý lẽ cũ không sai — nó có một biên mà tác giả cũ chưa nhìn tới.** Lý lẽ
cũ ("người dùng tự khai cả chuỗi trong 1 câu, mức đồng ý mạnh hơn một gợi ý
bình thường") đúng với hành động mà **nội dung biết được ngay lúc khai
báo**. Nhưng khi người dùng nói *"giao hàng rồi xuất hóa đơn và ghi nhận
thanh toán luôn"*, hóa đơn **chưa tồn tại** tại thời điểm đó — họ đồng ý với
**hành động**, và không thể nào đồng ý với **số tiền**. Spec này thu hẹp
quy tắc cũ lại đúng chỗ biên đó, không bãi bỏ nó.

Phạm vi nổ được thu hẹp có chủ đích: **chỉ** `post_invoice` và
`register_payment` dừng lại; `confirm_sale_order`, `deliver_order`,
`receive_order`, `convert_lead`… vẫn auto-run y như cũ.

Comment ở `continuation.py:8-11` phải được cập nhật để phát biểu quy tắc
mới kèm lý do trên — không để lại một phát biểu tuyệt đối đã hết đúng.

## 5. Rủi ro và cách xử lý

### 5.1. Trùng logic resolve giữa backend và MCP tool — **triệt tiêu bằng thiết kế**

Coordinator **luôn** gọi tool kèm `invoice_id` đã resolve. Nhánh
`if invoice_id:` của tool (`mcp-servers/odoo/tools/accounting.py:29-51`)
**bỏ qua hoàn toàn** phần resolve của chính nó. Nên lúc chạy thật chỉ có
**đúng một** phép resolve. Đoạn code trùng không phải hai resolver chạy đua
rồi lệch nhau, mà là một resolver sống + một nhánh chết trên đường này. Đây
cũng chính là đường mà tool đã dành sẵn: docstring gọi `invoice_id` là
*"đường nội bộ"*, ưu tiên hơn `partner_name`
(`mcp-servers/odoo/tools/accounting.py:27`, `:154`), và `create_credit_memo`
đã dùng đúng cách đó (`returns_write.py:146`).

Rủi ro còn lại thu hẹp về "ai đó gọi tool trực tiếp không kèm `invoice_id`".
Chốt chặn: một test `@pytest.mark.live` gọi cả hai đường với cùng
`partner_name` và assert chúng chọn ra **cùng một** `invoice_id` — bắt được
drift nếu ai đó sửa domain một bên.

### 5.2. Đảo hành vi chuỗi

Đã xử lý ở §4 (thu hẹp phạm vi + diễn đạt lại lý lẽ + cập nhật comment).
Thêm một dữ kiện quan trọng: **không test nào hiện ghim hành vi auto-run cho
hai tool đụng tiền**. Các test auto-chain hiện có dùng đúng
`confirm_sale_order`/`deliver_order`
(`backend/tests/agents/test_auto_chain.py:160-178`) — tức chúng vẫn xanh
**và vẫn còn ý nghĩa** sau thay đổi này.

**Nhưng bộ test xanh KHÔNG phải bằng chứng.** Chúng xanh *chính vì* chưa bao
giờ chạm ca bị đổi — đúng hình dạng lỗi của
`2026-08-05-write-confirmation-ux-fix` (6 vòng review sạch trên một cơ chế
thực tế không chạy được trong production, vì mọi test đều dựng state bằng
tay thay vì đi qua entry point thật). Vì vậy §6 bắt buộc live-verify.

### 5.3. Interrupt **giữa chuỗi** — tình huống chưa từng tồn tại

Trước nay coordinator chỉ tới được từ `erp_write_planner`, tức **đầu**
chuỗi. Với thay đổi này, graph sẽ park ở interrupt **giữa** chuỗi, rồi
resume từ checkpoint và phải khôi phục `auto_chain` đúng để chạy nốt phần
còn lại.

Về lý thuyết là ổn (`auto_chain` nằm trong state, checkpointer Postgres
persist nó, `_finish` không ghi đè). Nhưng đây đúng loại giả định mà dự án
này đã bị phạt vì tin lời suy luận, nên nó là **hạng mục phải live-verify
qua entry point thật**, không phải test dựng state bằng tay — xem §6 tiêu
chí 3.

## 6. Cổng nghiệm thu

Unit test (dựng state) là **cần nhưng không đủ**. Ba tiêu chí live-verify
dưới đây chạy qua backend thật + Odoo thật, gửi request đúng hình dạng
client thật (resend toàn bộ lịch sử hội thoại, không `session_id` — xem
phương pháp đã ghi trong `2026-08-05-write-confirmation-ux-fix`):

1. **Gọi trực tiếp, có mơ hồ thật.** "Phát hành hóa đơn nháp của Acme" →
   phải hiện danh sách nhiều bản nháp để chọn (dữ liệu thật hiện có 5 bản),
   **không** phát hành gì trước khi chọn; sau khi chọn, hiện bảng dòng hàng
   + tổng tiền rồi mới hỏi xác nhận.
2. **Chuỗi có bước đụng tiền phải DỪNG.** Khai báo chuỗi tới
   `post_invoice` → phải park ở interrupt kèm bảng tóm tắt, không tự chạy.
3. **Resume giữa chuỗi phải chạy nốt.** Từ tiêu chí 2, trả lời "có" →
   `post_invoice` chạy, rồi `register_payment` phải tiếp tục đúng theo
   `auto_chain` còn lại (và cũng dừng hỏi lại, kèm `amount_residual`).
4. **Chống hồi quy chaining nói chung.** Chuỗi **không** có bước đụng tiền
   (`create_quotation → confirm_sale_order`) phải **vẫn auto-run, không
   interrupt** — y hệt trước thay đổi.

Tiêu chí 4 là chốt chặn quan trọng nhất: nó chứng minh ta thu hẹp đúng chỗ
biên chứ không phá cơ chế chuỗi.
