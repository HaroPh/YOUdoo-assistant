# Phân quyền theo vai — tài khoản AI riêng + cưỡng chế ở tầng Odoo

**Ngày:** 2026-08-09
**Trạng thái:** design đã duyệt, chờ plan
**Bối cảnh:** `docs/ADR-012-agent-capability-and-permissions.md`,
`docs/role-permission-interview.md` (đã phỏng vấn thật, đã điền)

## 1. Mục tiêu

Hiện agent kết nối Odoo bằng **tài khoản cá nhân của chủ dự án**
(`phamhao14170@gmail.com`), có `Administrator` trên **mọi** module, dùng chung
cho cả đường đọc lẫn đường ghi. Hai hệ quả:

1. Mọi người dùng chat thao tác với quyền quản trị toàn hệ thống.
2. Trong nhật ký Odoo (`create_uid`/`write_uid`), **hành động của AI hiện ra
   như do chính chủ dự án làm** — không phân biệt được người với máy.

Spec này làm hai nhịp, gộp một lần triển khai:

- **1a** — Tài khoản AI riêng cho vai `admin`. Chức năng KHÔNG đổi (đã đo,
  §2.3), nhưng nhật ký phân biệt được người/máy và bán kính thiệt hại bị giới
  hạn.
- **1b** — Cơ chế phân vai đầy đủ: 3 vai, credential riêng, cưỡng chế ở tầng
  Odoo, mô hình 4 trạng thái quyền.

**NGOÀI phạm vi (vòng 2):** luồng duyệt bất đồng bộ và bàn giao chéo bộ phận
thật — xem §9.

## 2. Cơ sở đo lường

Mọi con số dưới đây **đo trực tiếp trên Odoo đang chạy**, ngày 2026-08-09.

### 2.1 Phương pháp đã tự kiểm chứng

Ma trận quyền tính từ `ir.model.access` **cộng bao đóng kế thừa nhóm**
(`res.groups.implied_ids` — bỏ sót bước này là nguồn sai của lần đo đầu).
Đối chiếu kết quả tính toán với `has_access(ids, operation)` thật của tài khoản
admin hiện tại: **0 lệch / 57 phép đo**.

`has_access` cho phép đo quyền **không cần thực thi lệnh ghi nào** — không tạo
dữ liệu rác trong lúc khảo sát.

### 2.2 Bề mặt model

- **Đường ghi** (33 tool MCP): 28 model. Trích từ mã nguồn `mcp-servers/odoo/`,
  áp `ODOO_METHOD_OPERATION_MAP` của `security.py` để quy method → operation.
- **Đường đọc** (27 tool `erp_query`): 18 model —
  `account.move`, `account.move.line`, `crm.lead`, `mrp.bom`, `mrp.bom.line`,
  `mrp.production`, `product.product`, `product.supplierinfo`, `purchase.order`,
  `purchase.order.line`, `res.partner`, **`res.partner.bank`**, `sale.order`,
  `sale.order.line`, `stock.lot`, `stock.quant`, `stock.picking`,
  `stock.warehouse.orderpoint`.

`res.partner.bank` (số tài khoản ngân hàng đối tác) là dữ liệu nhạy cảm — ghi
ra đây để quyết định có cấp cho vai `warehouse` hay không (§5.3).

### 2.3 Vai `admin` đủ quyền — đã xác minh

6 nhóm ứng dụng Administrator + `Role / Administrator` → **0/57 phép đo bị
thiếu**. So với tài khoản cá nhân hiện tại, chỉ kém 3 nhóm — `Multi Companies`,
`Dashboard / Admin`, `Maintenance / Equipment Manager` — **không tool nào hiện
có chạm tới cả ba**. Nên `ai-admin` tương đương chức năng tài khoản hiện tại.

### 2.4 Phát hiện chặn: nhóm mặc định của Odoo KHÔNG đủ

```
mail.mail            | chỉ Role / Administrator cấp | read,write,create,unlink
ir.config_parameter  | chỉ Role / Administrator cấp | read,write,create,unlink
```

Không nhóm nào khác cấp hai model này. Hệ quả nếu chỉ dùng nhóm có sẵn:

- Mọi vai gửi mail (cả 3 vai đều gửi — §7) sẽ phải nhận `Role / Administrator`,
  tức **toàn quyền cấu hình hệ thống** ⇒ phân tách vai trở thành hình thức.
- `ai-readonly` cũng cần `ir.config_parameter` (write-gate đọc mỗi request).

Thêm nữa, Odoo **không có nhóm "chỉ đọc"**: các nhóm `*/User` cấp đọc **và**
ghi cùng lúc. Đó là lý do cấu hình chỉ-`Internal User` chỉ đạt 7/28.

⇒ Thiết kế **bắt buộc** phải tạo nhóm quyền tuỳ chỉnh (§4).

## 3. Kiến trúc — 3 tầng danh tính, không tầng nào tự khai

```
Nhân viên đăng nhập Open WebUI (:3002)      ← xác thực thật, có mật khẩu
            │  x-openwebui-user-id (header)
   backend tra bảng ánh xạ user_id → role   ← phía server, người dùng không sửa được
            │
   chọn graph + tiến trình MCP + credential Odoo
            │
   Odoo cưỡng chế theo nhóm quyền           ← lớp cuối, không tin code phía trên
```

Hai phương án đã **bị loại**, ghi lại để không ai đề xuất lại:

- **3 model trong dropdown Open WebUI** — cho phép người dùng tự chọn vai, tức
  tự khai. Không phải cưỡng chế.
- **Truyền `role` như tham số tool** — tham số tool do LLM điền, mà LLM là
  thành phần kém tin cậy nhất trong stack. Bảo mật giả.

**Cô lập theo tiến trình, không phải một tiến trình giữ 3 credential:** tiến
trình `warehouse` không hề nắm credential admin, nên một bug định tuyến vai chỉ
dẫn tới "sai bộ tool" chứ không phải "leo thang đặc quyền".

`MCP_ODOO_PORT`, `ODOO_USERNAME`, `ODOO_PASSWORD` **đều đã lấy từ env** ⇒ chạy 3
tiến trình MCP **không cần sửa dòng nào** trong `mcp-servers/odoo/`.

### 3.1 Điều kiện tiên quyết

`docker-compose.yml` hiện **không** đặt `ENABLE_FORWARD_USER_INFO_HEADERS`, nên
header nhận dạng **chưa bao giờ được gửi**. `main.py` đã có code đọc
`x-openwebui-user-id` nhưng thực tế luôn rỗng (`thread_id` đang rơi về phương án
băm câu hỏi đầu). Phải bật.

Bảng ánh xạ khoá theo **`user_id` (chuỗi mờ)**, KHÔNG theo email — tôn trọng
quyết định PII ở `main.py:114-118` ("name/email/role là PII, không bao giờ được
đọc hoặc ghi log").

### 3.2 Rủi ro còn lại đã biết (final-review Fix 6b, chưa sửa — chỉ ghi nhận)

§3 viết "phía server, người dùng không sửa được" cho bước tra bảng ánh xạ
user_id → role. Đúng cho **chặng Open WebUI → backend**: header
`x-openwebui-user-id` do container `open-webui` tự gắn phía server, người
dùng cuối không chỉnh được nó qua giao diện chat.

Nhưng **`/v1/chat/completions` của chính backend không có xác thực**, và
`run.py` mặc định `BACKEND_HOST=0.0.0.0` (nghe mọi interface, không chỉ
`127.0.0.1`) — xem `.env.example`. Bất kỳ ai gọi thẳng tới cổng `8002` (bỏ
qua Open WebUI hoàn toàn) đều có thể tự đặt `x-openwebui-user-id` thành BẤT
KỲ giá trị nào, kể cả id của tài khoản admin thật. Tầng Odoo **không bắt
được** trường hợp này — không phải vì nó bị vượt qua, mà vì request khi đó
**hợp lệ đúng nghĩa admin** (role tra ra đúng là `admin` theo bảng ánh xạ),
nên Odoo cưỡng chế đúng như thiết kế, chỉ là đang cưỡng chế cho một danh
tính bị mạo nhận ở tầng phía trên nó.

Nói cách khác: "người dùng không sửa được" đúng cho người dùng **đi qua Open
WebUI**; không đúng cho bất kỳ ai gọi thẳng backend. Thiết kế này CHƯA đóng
rủi ro đó — ghi nhận để không claim nhiều hơn những gì đã triển khai. Hai
hướng giảm thiểu khả thi, chưa làm: (a) ràng `BACKEND_HOST` về `127.0.0.1`
(chỉ nhận kết nối cục bộ, đúng mô hình "backend + open-webui cùng một máy/
mạng tin cậy"), hoặc (b) một shared secret giữa container `open-webui` và
backend (header/token riêng mà backend đòi hỏi, open-webui tự đính kèm) để
phân biệt "request thật từ open-webui" khỏi "ai đó tự gọi thẳng cổng 8002".

## 4. Bốn credential và nhóm quyền

| Tài khoản | Dùng ở | Nhóm quyền |
|---|---|---|
| `ai-readonly` | backend: đường ĐỌC + write-gate | `Youdoo AI / Read Only` (tuỳ chỉnh) |
| `ai-admin` | MCP :8003 | 6 nhóm Administrator + `Role / Administrator` |
| `ai-warehouse` | MCP :8004 | `Inventory / User` + `Contact / Creation` + `Youdoo AI / Mail` |
| `ai-accounting` | MCP :8005 | `Accounting / Invoicing` + `Contact / Creation` + `Youdoo AI / Mail` |

Đường ĐỌC **không đi qua MCP** — nó chạy thẳng từ backend
(`erp_query/gateway.py:67-69`), nên cần credential riêng.

### 4.1 Hai nhóm quyền tuỳ chỉnh phải tạo

**`Youdoo AI / Mail`** — thay cho việc ném `Role / Administrator` cho vai gửi mail:

| Model | read | write | create | unlink |
|---|:-:|:-:|:-:|:-:|
| `mail.mail` | ✓ | ✓ | ✓ | ✓ |
| `ir.config_parameter` | ✓ | | | |

**`Youdoo AI / Read Only`** — quyền đọc rộng, **không một quyền ghi nào**, trên
18 model đường đọc (§2.2) cộng `ir.config_parameter`. Mọi dòng
`ir.model.access` chỉ bật `perm_read`.

Cả hai tạo bằng bản ghi `res.groups` + `ir.model.access` — công việc **cấu hình
Odoo**, không phải code Python.

### 4.2 Đánh đổi có chủ ý: một credential đọc dùng chung

Mọi vai đọc được mọi dữ liệu ở tầng credential. Đúng với nghiệp vụ đã phỏng vấn
(câu 14: kho **cần** biết đơn đã thanh toán chưa trước khi xuất). Hạn chế theo
vai ở đường đọc được thực hiện bằng **lọc tool** (§6), tức lớp UX/chính sách,
không phải cưỡng chế.

Nếu sau cần siết thật: mọi hàm `erp_query` đều nhận `gw=None` ⇒ tiêm gateway
theo vai được, không phải viết lại.

## 5. Mô hình 4 trạng thái quyền

Phỏng vấn nhân viên kho thật cho kết quả quyết định thiết kế: **13 câu Đ, 11 câu
X, 0 câu K**. Ở doanh nghiệp nhỏ gần như không có gì bị cấm tuyệt đối — chỉ có
"làm được" và "làm được nhưng phải xin phép".

Nhưng hai chữ X **không cùng nghĩa**:

| | Kho, `post_invoice` | Kế toán, `post_invoice` |
|---|---|---|
| Nghĩa | *"Không phải việc của tôi, cần gấp thì xin được"* | *"Đúng việc của tôi, kế toán trưởng phải ký"* |
| Người duyệt | Phòng kế toán | Cấp trên cùng phòng |
| Hành động đúng | **Bàn giao** sang phòng kế toán | **Xin duyệt** rồi chính mình làm |

⇒ Bốn trạng thái, không phải ba:

```
Đ  own            việc của mình                → cổng xác nhận như hiện nay
X  needs_sign_off việc của mình, cần cấp trên  → vòng 2: luồng duyệt
E  other_dept     việc phòng khác, xin thì được→ vòng 2: bàn giao (activity)
K  denied         không thể                    → từ chối, nêu rõ thuộc bộ phận nào
```

### 5.1 Ánh xạ trạng thái → quyền Odoo

| Trạng thái | Quyền trên tài khoản Odoo của vai | Lý do |
|---|---|---|
| Đ, X | **có** | Vòng 2, sau khi được duyệt, chính vai đó thực thi |
| E, K | **không** | Cưỡng chế thật ở tầng Odoo |

Chỉ **E và K** được cưỡng chế bởi Odoo. Đây là lý do sức mạnh lớp cưỡng chế
**tỉ lệ thuận với số E/K mà tổ chức khai báo** — không phải khuyết điểm kiến
trúc mà là phản ánh trung thực chính sách.

### 5.2 Hành vi vòng 1 (chưa có luồng duyệt)

| Trạng thái | Vòng 1 |
|---|---|
| Đ | cổng xác nhận hiện có |
| X | **như Đ**, kèm ghi chú *"thực tế cần cấp trên duyệt"* |
| E | **từ chối**, nêu rõ thuộc bộ phận nào và nên liên hệ ai |
| K | từ chối |

X xử lý như Đ ở vòng 1 để **không làm mất năng lực hiện có** — nếu từ chối X thì
kế toán sẽ không phát hành được hoá đơn (câu A2.1 = X), kém hơn hiện tại.

### 5.3 Hai hồ sơ chính sách

Cùng một cơ chế, hai cấu hình — chứng minh **cơ chế ≠ chính sách**:

- **`small-business`** — đúng bảng phỏng vấn. Nhiều X/E, không K.
- **`enterprise`** — minh hoạ doanh nghiệp lớn, chia nhỏ trách nhiệm hơn.

**Lưu ý quan trọng khi chọn ví dụ minh hoạ:** ở tầng Odoo, **E và K giống hệt
nhau** — cả hai đều là "tài khoản không có quyền". Khác biệt của chúng nằm ở
tầng agent (vòng 2: E tạo yêu cầu bàn giao, K từ chối thẳng). Vì vậy một ví dụ
kiểu *"`create_rfq` chuyển từ E sang K"* **không** chứng minh được lớp cưỡng chế
Odoo — nó vốn đã bị chặn ở cả hai hồ sơ.

Ví dụ đúng phải là nghiệp vụ **rời khỏi tập Đ/X**, vì đó mới là lúc quyền bị gỡ
khỏi tài khoản Odoo:

| Nghiệp vụ | `small-business` | `enterprise` | Tài khoản `ai-warehouse` |
|---|---|---|---|
| `inventory_adjustment` | **Đ** (câu 6) | **E** — chỉ thủ kho trưởng | mất quyền ghi `stock.quant` |
| `scrap_product` | **Đ** (câu 8) | **E** — cần bộ phận chất lượng | mất quyền ghi `stock.scrap` |
| `return_order` | **X** (câu 9) | **E** — thuộc phòng thu mua | mất quyền `stock.return.picking` |

Ba dòng này khiến hồ sơ `enterprise` cần một **tài khoản Odoo khác hẳn** (nhóm
quyền hẹp hơn `Inventory / User`), và đó mới là bằng chứng cho thấy chính sách
thật sự đổi được lớp cưỡng chế — chứ không chỉ đổi câu chữ agent trả lời.

## 6. Thay đổi phía backend

```python
@dataclass(frozen=True)
class RoleCfg:
    name: str                        # "admin" | "warehouse" | "accounting"
    mcp_url: str                     # cổng MCP riêng của vai
    tool_states: dict[str, str]      # tool → "own"|"needs_sign_off"|"other_dept"|"denied"
    label: str                       # "Kho" — dùng trong thông báo cho người dùng
```

`ERPAgent.setup()` lặp qua 3 `RoleCfg`, mỗi vai một `MultiServerMCPClient` + một
graph; `llms`, connection pool và checkpointer **dùng chung** ⇒ 3 graph gần như
không tốn thêm bộ nhớ.

**Hai lớp, không lớp nào được tin một mình:**

- Backend **lọc** tool xuống tập `own`+`needs_sign_off` trước khi dựng graph →
  LLM chỉ thấy tool liên quan (chọn đúng hơn, prompt gọn hơn — dự án đang đo
  `tool_acc`/`dangerous_misroute`)
- Odoo **cưỡng chế** → bộ lọc có bug thì vẫn bị chặn

**Prompt sinh động từ `tool_states`**, không viết tay 3 prompt cứng — nếu không
chúng sẽ trôi lệch, đúng lớp lỗi đã bắt được ở `mail-trigger-points`
(`WRITE_TOOL_NAMES` thiếu 4 tool mail khiến chỉ số "misroute nguy hiểm" mù với
đúng những tool gửi mail ra ngoài).

### 6.1 Cạm bẫy: `thread_id` phải mang vai

`thread_id` hiện suy từ người dùng + cuộc chat, **không có vai**. Kịch bản hỏng:
đang chờ xác nhận một lệnh ghi ở vai `warehouse` → đổi vai → trả lời "có" →
LangGraph resume interrupt trong graph **không có node đó**. Bắt buộc đưa vai
vào `thread_id`.

## 7. Tool mới

Khảo sát template Odoo lộ ra `Shipping: Send by Email` trên `stock.picking` —
báo khách hàng đã xuất hàng. Đây là nhu cầu nghiệp vụ thật (phỏng vấn câu 17 =
Đ) và là thứ khiến vai `warehouse` có "đầu ra" thay vì chỉ bấm nút validate.

**`send_delivery_email`** — thêm bằng đúng factory `EmailCfg` đã có
(`2026-08-08-mail-trigger-points`), tốn 1 config + 1 dòng registry + 1 dòng
prompt. Trạng thái: **X** với `warehouse` (câu 18 = cần duyệt).

Các điểm nối mail khác đã khảo sát nhưng **ngoài phạm vi vòng này**:
`Payment: Payment Receipt` (`account.payment`), `Purchase: Vendor Reminder`,
`Purchase: Purchase Order`, `Sales: Payment Done`.

## 8. Cổng nghiệm thu

Live-verify **TRƯỚC merge**, trên worktree của nhánh.

**Nhịp 1a — không hồi quy:**

1. Đổi `.env` sang `ai-admin`, chạy lại các luồng chính đã có (tạo báo giá →
   xác nhận → giao hàng → hoá đơn → thanh toán; gửi 1 mail). ĐẠT khi kết quả
   giống hệt trước.
2. Đọc `create_uid` của một bản ghi vừa tạo. ĐẠT khi = **AI Admin**, không phải
   tài khoản cá nhân — đây là bằng chứng vấn đề nhật ký đã đóng.

**Nhịp 1b — phân vai:**

3. Đăng nhập Open WebUI bằng tài khoản vai `warehouse`. ĐẠT khi: làm được việc
   kho (validate phiếu), và **bị từ chối** khi yêu cầu `post_invoice`, kèm thông
   báo nêu đúng bộ phận phụ trách.
4. Cùng yêu cầu `post_invoice` đó, đăng nhập bằng vai `accounting` → ĐẠT khi
   thực hiện được. Đây là phép đo chứng minh vai thật sự khác nhau, không phải
   cùng một quyền đội lốt.
5. **Cưỡng chế Odoo là thật, không chỉ lọc ở agent:** gọi thẳng MCP :8004
   (`ai-warehouse`) yêu cầu `post_invoice`, bỏ qua tầng backend. ĐẠT khi **Odoo
   từ chối** — chứng minh bảo vệ không nằm ở LLM.
6. Đổi vai giữa lúc một câu xác nhận đang treo → ĐẠT khi không resume nhầm
   graph (bẫy §6.1).

Tiêu chí 5 là quan trọng nhất: nó phân biệt "kiến trúc production-ready" với
"tách vai trên giao diện".

## 9. Ngoài phạm vi — vòng 2

- **Luồng duyệt (X)** — bất đồng bộ, xuyên người dùng: hàng đợi duyệt, hết hạn,
  người duyệt thấy đủ ngữ cảnh. Cơ chế hoàn toàn mới, không phải mở rộng cổng
  xác nhận hiện có (cổng đó hỏi **chính** người đang chat).
- **Bàn giao (E)** — cần tổng quát hoá `log_activity` (hiện chỉ chạy trên
  `crm.lead`, không có tham số người nhận).
- **Ngưỡng giá trị cho `inventory_adjustment`** (phỏng vấn câu 7 = X "trên X
  triệu phải duyệt") — hiện **không có ngưỡng nào** trong code.
- Hàng đợi "việc hôm nay" (ADR-012 §2) — 94 phiếu kho đang chờ, chưa tool nào
  liệt kê được.
