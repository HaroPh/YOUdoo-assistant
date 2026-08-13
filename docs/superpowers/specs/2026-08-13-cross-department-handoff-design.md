# Bàn giao chéo bộ phận — thiết kế

**Ngày:** 2026-08-13
**Trạng thái:** thiết kế đã duyệt, chờ plan
**Nguồn:** `docs/ADR-012-agent-capability-and-permissions.md` §5

## 0. Tóm tắt

Hôm nay, vai kho yêu cầu một thao tác ghi thuộc kế toán thì nhận đúng một câu:

```
Việc này không thuộc quyền hạn của bộ phận Kho.
Vui lòng liên hệ bộ phận Kế toán để thực hiện.
```

Việc đó **bốc hơi**. Không ai được giao, không gì được ghi nhận, người dùng phải
tự đi thuật lại bối cảnh. ADR-012 §5 xếp đây là phương án **yếu nhất**.

Đợt này biến lời từ chối thành một **bàn giao có ghi nhận**: một activity gắn
trên đúng chứng từ, giao cho bộ phận có thẩm quyền, kèm bối cảnh — và một đường
để bên nhận **đọc được** việc đó.

## 1. Vì sao làm được bây giờ

ADR-012 §5 nêu hai điều kiện tiên quyết. Cả hai nay đã đóng:

| điều kiện (nguyên văn ADR-012) | trạng thái |
|---|---|
| *"vô nghĩa cho tới khi agent ngừng chạy bằng tài khoản admin"* | ĐÓNG — 4 tài khoản Odoo riêng, 3 tiến trình MCP cô lập |
| *"`log_activity` hiện quá hẹp để làm kênh bàn giao"* — chỉ `crm.lead`, chỉ Call/Meeting, không có người nhận | ĐÓNG — 6 model, loại suy từ Odoo, có `assignee` |

Và một điều kiện thứ ba mà ADR-012 không biết là mình cần: **lời từ chối phải
thật sự xảy ra**. Trước bản sửa `router-empty-response` (cùng ngày), với một số
cách diễn đạt, router phân loại nhầm thành `unknown` nên planner không bao giờ
chạy — không có gì để mà bàn giao.

## 2. Phát hiện quyết định: không ai đọc được activity

**Không tool nào trong repo đọc `mail.activity`.** Chỉ `log_activity` ghi vào.
Đường đọc (`erp_query`) không có gì; `SYSTEM_PROMPT` không liệt kê.

Đây đúng là điều ADR-012 §2 phê phán — *"agent giỏi **làm**, mù **việc gì cần
làm**"* — và khảo sát năng lực đã đo: 37/37 activity quá hạn, một danh sách
việc không ai đọc được.

**Hệ quả cho phạm vi:** làm nửa ghi mà không làm nửa đọc là rơi vào đúng cái hố
ADR-012 chỉ ra. Tính năng này **bắt buộc có hai nửa**.

## 3. Quyết định thiết kế

### 3.1 Người nhận = tài khoản AI của bộ phận

Activity giao cho `ai-accounting` / `ai-warehouse`, không phải một người thật.

**Lý do:** người dùng làm việc qua **Open WebUI, không phải Odoo UI**. Tiến
trình MCP của vai kế toán xác thực vào Odoo bằng `ai-accounting`, nên việc giao
cho tài khoản đó chính là việc nằm trong tầm nhìn của **trợ lý bộ phận kế
toán** — đúng nơi người đó sẽ hỏi.

Phương án "một người thật cấu hình theo bộ phận" đúng tinh thần ADR-012 hơn
(*"có người chịu trách nhiệm"*), nhưng nó giải bài toán **Odoo UI** mà ở đây
không ai dùng, và đẻ ra một bảng ánh xạ mới phải nuôi.

**Đánh đổi, nói rõ:** ai muốn xem trực tiếp trong Odoo UI phải đăng nhập bằng
chính tài khoản AI đó. Chấp nhận được với quy mô demo vài vai đặc trưng (quyết
định của chủ dự án), và đổi được sau bằng cách thêm bảng ánh xạ mà không phá
thiết kế.

**Suy ra, không khai tay:** login Odoo = `f"ai-{role_name}"` — đúng quy ước đã
dùng ở `scripts/odoo_setup_ai_accounts.py` và `start-dev.ps1`.

Nhưng `DEPT_OF` trả **nhãn** (`"Kế toán"`), không phải tên vai (`accounting`).
Phải tra ngược qua `PROFILES[...]` theo `RoleCfg.label`. Và phép tra đó **trượt
với 4/20 tool**: `"Bán hàng"` (2 tool) và `"Mua hàng"` (2 tool) không có vai nào
trong hệ — bốn tool đó rơi về sàn §3.3, xem §6.

### 3.2 Từ chối kèm đề xuất, KHÔNG tự động ghi

Tạo activity **là một thao tác ghi vào Odoo**. Dự án có cổng xác nhận ghi tất
định ở ranh giới tool; tự động tạo là **đi vòng qua đúng cái cổng đó**.

Nên: lời từ chối mang theo một `pending_action` `log_activity` **đã điền sẵn**.
Người dùng thấy chính xác sẽ ghi gì cho ai rồi mới đồng ý. Không đục thêm đường
ghi nào — tái dùng nguyên cơ chế đang có.

Thêm một lý do: ADR-012 cảnh báo *"mỗi lần bị chặn đều tạo activity ⇒ kế toán
ngập"*. Bắt xác nhận đã chặn phần lớn spam ngay từ đầu.

### 3.3 Sàn: dựng không được thì rơi về lời từ chối hôm nay

Bàn giao là **nâng cấp ở nơi làm được**, không bao giờ làm lời từ chối tệ đi.
Cùng nguyên tắc đã dùng ở `router-empty-response` §3.5 và nó đã cứu đợt đó một
lần (xem C1 trong final review đợt ấy).

### 3.4 Tool đọc TỔNG QUÁT, không phải kênh riêng cho bàn giao

*"Activity đang mở giao cho tôi, sắp theo hạn"* — không lọc riêng activity do
bàn giao sinh ra.

**Lý do:** một kênh chuyên dụng chỉ trả lời được câu hỏi của chính nó, trong khi
tool tổng quát đóng luôn khoảng trống ADR-012 §2 nêu (agent mù việc gì cần làm).
YAGNI theo chiều ngược lại: đừng dựng đường riêng khi đường chung đã đủ.

### 3.5 Chống spam dùng chính nửa đọc

Trước khi **đề xuất**, kiểm đã có activity đang mở trên cùng bản ghi cho cùng
người nhận chưa. Có rồi thì nói *"đã có việc đang mở, hạn 15/8"* thay vì đề xuất
trùng. Hai nửa dùng chung một đường truy vấn.

## 4. Phương án đã cân nhắc và LOẠI: mail nội bộ

Chủ dự án đề xuất dùng mail thay activity, và tự nêu lo ngại quyền riêng tư.
Lo ngại đó đúng, và là lý do mạnh nhất trong bốn lý do:

1. **Quyền riêng tư:** đọc mail nghĩa là đọc **toàn bộ** hộp thư, không có cách
   nào cấp quyền "chỉ đọc mail bàn giao". Dự án có ràng buộc PII rất chặt (chỉ
   `x-openwebui-user-id`, không bao giờ đọc tên/email/vai).
2. **Mail rời khỏi hệ thống.** `send_mail` ở đây gửi thật qua SMTP tới địa chỉ
   thật; một việc **nội bộ** sẽ thành email đi ra ngoài. Bán kính ảnh hưởng có
   thật và không thu hồi được — đã có một lượt gửi ngoài ý muốn cùng ngày.
3. **Mail không có trạng thái.** Bàn giao cần "xong / chưa xong". Dùng mail là
   phải dựng lại một hệ quản việc trên nền hộp thư.
4. **Mail không gắn vào chứng từ**, buộc người ta chép mã đơn qua lại.

ADR-012 §5 đã chốt quy tắc: **mail = ra ngoài (khách, NCC). Activity = vào trong
(đồng nghiệp).**

**Chỗ ý này thật sự mạnh, ghi lại vì nó có thể đúng về sau:** mail là nơi người
ta thật sự nhìn vào. Nếu người nhận không mở Open WebUI hay Odoo hằng ngày thì
activity vô hình với họ. Hôm nay không áp dụng vì bên nhận là tài khoản AI và
người dùng làm việc qua Open WebUI. Nếu về sau cần đánh động, cách đúng là **một
thông báo trỏ về activity**, không phải biến mail thành nơi lưu việc.

## 5. Kiến trúc

```
Kho: "phát hành hoá đơn cho S00012"
  └─ erp_write_planner → guard vai bắt: create_invoice_from_order thuộc Kế toán
       ├─ dựng được bàn giao?  ─ KHÔNG → câu từ chối như hôm nay (SÀN)
       └─ CÓ → kiểm trùng → pending_action log_activity → CỔNG XÁC NHẬN
                                                            └─ ghi activity

Kế toán: "có việc gì chuyển cho tôi không?"
  └─ erp_read → list_my_activities → activity đang mở giao cho ai-accounting
```

### 5.1 Bảng tool → chứng từ, kèm lưới đỡ ba chiều

Activity phải gắn vào một bản ghi, nhưng tham số các tool ghi không đồng nhất.
`DEPT_OF` có **20** tool, phân bố: Kho 10, Kế toán 6, Bán hàng 2, Mua hàng 2.

- **có mã chứng từ**: `create_invoice_from_order`/`create_bill_from_po`/
  `confirm_sale_order`/`confirm_purchase_order`/`deliver_order`/`receive_order`/
  `return_order` (`order_ref`), `validate_picking`/`send_delivery_email`
  (`picking_ref`), `create_credit_memo`/`send_invoice_email` (`invoice_ref`).
- **không có**: `post_invoice(partner_name, amount)`,
  `create_quotation(partner_name, lines)`, `create_rfq`,
  `inventory_adjustment(product_name, new_qty)`, `internal_transfer`,
  `scrap_product` — chúng **tạo mới** hoặc thao tác trên vật/kho.
- **hai ca riêng**, plan phải quyết tường minh chứ không được lặng lẽ xếp nhóm:
  `register_payment` có `invoice_ref` **tuỳ chọn** (có thì dùng, không thì rơi
  về sàn); `log_activity` chính LÀ tool bàn giao nên không bao giờ là đích của
  một cuộc bàn giao.

Bảng chính xác phải **suy từ chữ ký thật** lúc làm plan, không chép từ đây.

Bảng khai tay sẽ trôi — đây là lớp lỗi đã tái phát **sáu lần** trong dự án. Nên
kèm test canh trôi đủ **ba** chiều:

1. mọi khoá trong bảng đều có trong `DEPT_OF`;
2. mọi tool trong `DEPT_OF` **hoặc** có trong bảng, **hoặc** nằm trong danh sách
   ngoại lệ "không có chứng từ";
3. **danh sách ngoại lệ cũng không được có mục chết** — mọi mục phải còn trong
   `DEPT_OF`.

Chiều 3 là bài học trực tiếp từ đợt `GATHER_CASES`: lần đó lưới đỡ được dựng
nhưng chính danh sách ngoại lệ lại không ai canh, và lỗi tái xuất cao hơn một
tầng.

### 5.2 Nửa ghi

`_role_refusal_message` (`agents/nodes.py`) hiện trả một chuỗi và có **hai** chỗ
gọi — tool đơn (`nodes.py:~275`) và từng bước trong chuỗi (`~297`). Đổi thành
trả **cả câu lẫn `pending_action` khi dựng được**; hai chỗ gọi dùng chung nên
chỉ sửa một nơi.

Nội dung activity phải mang bối cảnh, không chỉ tên tool: người yêu cầu thuộc bộ
phận nào, họ muốn gì. Ví dụ *"Kho đề nghị: phát hành hoá đơn cho đơn S00012"*.

### 5.3 Nửa đọc — và vấn đề HAI TÀI KHOẢN

**Đường đọc và đường ghi chạy bằng hai tài khoản Odoo khác nhau.** Backend gọi
`build_erp_query_tools()` trong tiến trình của chính nó với `ODOO_USERNAME=
ai-readonly`; các tool ghi đi qua tiến trình MCP riêng của vai
(`ai-warehouse`/`ai-accounting`).

Nên câu "việc của tôi" hỏi qua đường đọc sẽ trả về việc của **`ai-readonly`** —
sai người — nếu tool lọc theo "người dùng hiện tại".

**Cách xử lý:** truyền `role_cfg` vào `build_erp_query_tools()` và lọc **tường
minh** theo user của vai (`ai-<role_name>`), vẫn truy vấn bằng tài khoản đọc.
`build_graph` đã nhận `role_cfg` sẵn, chỉ chưa chuyển xuống đường đọc.

> **ĐÃ ĐO (2026-08-13), giả định XÁC NHẬN — plan KHÔNG cần task cấp quyền.**
>
> `ai-readonly` đọc được `mail.activity`: `search_count` = 31, thấy cả bản ghi
> giao cho tài khoản khác (Mitchell Admin, Marc Demo), và lọc
> `user_id = <uid ai-accounting>` chạy đúng (trả 0 vì chưa có bàn giao nào).
> uid: `ai-readonly`=7, `ai-warehouse`=9, `ai-accounting`=10, `ai-admin`=8.
>
> Ghi chú Odoo đã biết: Odoo lọc **hiển thị** activity theo quyền đọc **chứng từ
> đính kèm**, không theo quyền trên `mail.activity`.

### 5.4 Phát hiện phụ: `ai-readonly` KHÔNG chỉ đọc

Đo cùng lúc, `check_access_rights` của `ai-readonly` trên 14 model:

| model | write / create / unlink |
|---|---|
| `account.move`, `account.payment`, `sale.order`, `purchase.order`, `stock.picking`, `stock.quant`, `mrp.production`, `res.partner`, `product.template`, `crm.lead`, `mail.mail`, `ir.config_parameter` | False |
| **`mail.activity`** | **True** |
| **`mail.template`** | **True** |

`start-dev.ps1` tuyên bố: *"kể cả bị chiếm quyền hoàn toàn cũng không ghi được
gì, vì tài khoản không có quyền"*. Tuyên bố đó **đúng 12/14, sai 2**.

KHÔNG phải lỗi cấu hình của dự án: Odoo cấp hai model này cho `base.group_user`
(mọi tài khoản nội bộ), không gỡ được mà không phá tài khoản. Việc đúng là
**sửa lời tuyên bố cho khớp sự thật**, không phải cố vá Odoo. `mail.template`
đáng chú ý hơn `mail.activity` — template là thứ gửi ra cho khách thật.

**Ngoài phạm vi đợt này** (chỉ sửa một dòng chú thích), nhưng ghi lại vì nó là
một tuyên bố an ninh trong tài liệu của chính dự án đang nói quá.

## 6. Ca lỗi và sàn

| tình huống | hành vi |
|---|---|
| tool không có chứng từ trong args | câu từ chối như hôm nay |
| bộ phận đích không có vai/tài khoản (`"Bán hàng"`, `"Mua hàng"` trong `DEPT_OF`) | câu từ chối như hôm nay |
| `dept_of` trả `"khác"` (LLM bịa tên tool) | câu từ chối như hôm nay |
| đã có activity đang mở trùng bản ghi + người nhận | nói đã có, kèm hạn; KHÔNG đề xuất trùng |
| tra chứng từ trong Odoo hỏng | câu từ chối như hôm nay, không vỡ lượt chat |

**Bất biến:** không nhánh nào trong bảng này được làm lời từ chối biến mất hoặc
xấu đi so với hôm nay.

## 7. Nghiệm thu

### 7.1 Test

- dựng được bàn giao → `pending_action` đúng tool `log_activity`, đúng
  `res_model`/`ref`/`assignee` suy từ vai đích
- **không** dựng được (mỗi dòng trong §6) → đúng câu từ chối hôm nay, và
  `pending_action` là `None`
- guard chuỗi (`nodes.py:~297`) cũng dựng được bàn giao, không chỉ tool đơn
- lưới đỡ trôi bảng: cả **ba** chiều ở §5.1, mỗi chiều một test
- tool đọc lọc đúng theo vai, KHÔNG theo tài khoản đọc
- kiểm trùng: có activity đang mở thì không đề xuất nữa

Mỗi guard phải kèm **phép thử phá**: xoá vế cần canh đi thì test tương ứng phải
đỏ. Một test xanh là một tuyên bố, không phải bằng chứng — lớp lỗi này đã xuất
hiện **ba lần trong một đợt** cùng ngày.

### 7.2 Nghiệm thu sống, TRƯỚC merge

Trên worktree của nhánh, stack cũ dừng hẳn trước.

| # | vai | câu | kỳ vọng |
|---|---|---|---|
| 1 | kho | *"phát hành hoá đơn cho đơn S00012"* | từ chối + đề xuất chuyển cho Kế toán, có cổng xác nhận |
| 2 | kho | xác nhận đề xuất ở #1 | activity tạo trên `sale.order` S00012, giao `ai-accounting` |
| 3 | kế toán | *"có việc gì chuyển cho tôi không?"* | **thấy đúng việc ở #2** |
| 4 | kho | lặp lại #1 | báo đã có việc đang mở, KHÔNG tạo trùng |
| 5 | kho | *"điều chỉnh tồn kho Bàn gỗ về 50"* (thuộc quyền) | chạy bình thường — đối chứng âm |
| 6 | kế toán | *"tạo báo giá cho khách X"* (chéo bộ phận, KHÔNG có chứng từ) | rơi về câu từ chối hôm nay |

#3 là phép đo **quyết định**: nó là thứ duy nhất chứng minh bàn giao không phải
một danh sách việc không ai đọc được.

### 7.3 Không được thụt

Bộ test đầy đủ xanh (mốc hiện tại: 1349 passed, 4 skipped, 46 deselected).

## 8. Ngoài phạm vi

1. **Thêm vai Bán hàng / Mua hàng** — `DEPT_OF` có hai bộ phận này nhưng hệ
   không có tài khoản nào cho chúng. Đóng khoảng trống đó cần thêm tài khoản
   Odoo, tiến trình MCP, nhóm quyền: một đợt riêng.
2. **Đóng activity từ phía trợ lý** ("việc này xong rồi") — vòng sau; vòng này
   chỉ tạo và đọc.
3. **Thông báo đẩy cho người nhận** — xem §4, chỉ làm khi có nhu cầu thật.
4. **Ánh xạ bộ phận → người thật** — xem §3.1, đổi được sau mà không phá thiết
   kế.
