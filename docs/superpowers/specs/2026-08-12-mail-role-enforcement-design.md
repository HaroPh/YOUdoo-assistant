# Thiết kế — cưỡng chế vai cho tầng mail (2026-08-12)

**Trạng thái:** đã duyệt, chờ viết plan.
**Nối tiếp:** `docs/ADR-012`, `2026-08-09-role-based-access-design.md`, và đợt
sửa bảng map ngày 2026-08-12 (`2026-08-09-role-based-access-report.md`, mục
"Đính chính lần ba").

## 1. Vấn đề

### 1.1 Lỗi đang có: mọi tool mail đã chết với vai non-admin

Đo thật qua `/v1/chat/completions` ngày 2026-08-12:

| Vai | Yêu cầu | Kết quả |
|---|---|---|
| kho | *"gửi email báo giao hàng cho phiếu WH/OUT/00138"* | `Công cụ soạn mail không khả dụng.` |
| kế toán | *"gửi email hóa đơn INV/2026/00030 cho khách"* | `Công cụ soạn mail không khả dụng.` |
| admin | cùng câu của kho | chạy đúng — hiện người nhận, tiêu đề, cổng xác nhận |

`send_delivery_email` là tool `needs_sign_off` của **chính vai kho**;
`send_invoice_email` là tool `own` của **chính vai kế toán**. Cả hai không dùng
được kể từ khi nhánh phân quyền merge.

**Cơ chế.** `_filter_tools_for_role` (`erp_agent.py:129-139`) lọc danh sách tool
xuống `own ∪ needs_sign_off` của vai. `graph.py` truyền danh sách ĐÃ LỌC đó cho
mọi hàm dựng node coordinator (dòng 91 và 133). Coordinator mail
(`mail_write.py:170`) tra `by_name.get("preview_template_email")` — một tool MCP
**không nằm trong tập nào** của `roles.py` — nên với vai non-admin nó luôn là
`None`, và node trả câu "không khả dụng".

**Vì sao chỉ mail dính.** Mọi coordinator khác tra đúng tool TRÙNG TÊN chính nó
(`post_invoice` → `post_invoice`, `create_bom` → `create_bom`, …). Khi vai không
được cấp, tool bị lọc VÀ coordinator cũng là `denied`, nên guard tất định trong
`nodes.py` đã từ chối sạch trước khi tới node. Chỉ `mail_write.py` tra tool có
tên KHÁC tên coordinator — ba tool: `preview_template_email`,
`send_prepared_email`, `discard_prepared_email`.

**Vì sao 1254 test không bắt được.** `tests/agents/test_mail_write.py` không biết
đến vai; `test_roles.py` / `test_role_write_guard.py` / `test_skill_role_filtering.py`
không biết đến mail. Không có test nào ở giao điểm.

Đây là lần thứ **năm** của cùng một hạng lỗi trong mạch phân quyền: một danh
sách khai báo thiếu âm thầm (SOP skill thiếu tool ghi → sập startup;
`KNOWN_ODOO_GAPS` thiếu 5 dòng; `TOOL_ACCESS_MAP` sai 8 dòng; `_WH_OTHER` thiếu
2 tool; giờ là coordinator có phụ thuộc nội bộ mà không chỗ nào khai).

### 1.2 Khoảng trống: tầng mail không có backstop Odoo

Nhóm `Youdoo AI / Mail` cấp `mail.mail` (read/write/create/unlink) cho **cả ba**
vai, và `mail.template` thì mọi người dùng nội bộ đều đọc được — hiện có 2
`ir.rule` trên `mail.template` nhưng cả hai đều `perm_read=False`, tức chưa hề có
luật giới hạn đọc.

Hệ quả: ở tầng Odoo, `ai-warehouse` gửi được mail hoá đơn và `ai-accounting` gửi
được mail giao hàng. Bốn tool gửi mail là nhóm tool duy nhất gây hậu quả **không
thu hồi được** (mail đã rời hệ thống), và chúng chỉ được chặn ở tầng agent.

Bảng map cũ che mất điều này: nó khai `("mail.template","create")` — quyền không
vai nào có — nên báo "chặn đúng" ở cả hai vai.

### 1.3 Mô hình đe doạ

`mcp-servers/odoo/server.py:19` bind `0.0.0.0`, nên ba cổng 8003/8004/8005 lộ ra
mạng LAN chứ không chỉ localhost. Ai gọi thẳng `:8004` dùng được mọi tool MCP
với credential `ai-warehouse`, bỏ qua toàn bộ tầng agent.

## 2. Phạm vi

**Làm:**
1. Khai báo phụ thuộc cho coordinator + test chốt drift (§3)
2. Allowlist template theo vai, cưỡng chế trong tiến trình MCP (§4)
3. Đo `ir.rule` phía Odoo; giữ nếu không gây hồi quy (§5)
4. MCP bind `127.0.0.1` mặc định, cấu hình được qua env (§6)

**Không làm (ghi nhận, để đợt sau):**
- `_WH_OTHER` thiếu `create_invoice_from_order` và `create_bill_from_po` — lời
  từ chối với vai kho mất tên bộ phận. Không phải lỗ hổng (`denied` chặt hơn
  `other_dept`), là lỗi chỉ đường.
- Chốt drift cho `TOOL_ACCESS_MAP` trong `scripts/check_role_odoo_consistency.py`.
- Xác thực cho `/v1/chat/completions`.

## 3. Khai báo phụ thuộc của coordinator

### 3.1 Trường `deps`

`Spec` (`write_registry.py:22-26`) thêm một trường có mặc định, nên 20 dòng
coordinator hiện có không phải sửa:

```python
@dataclass(frozen=True)
class Spec:
    node: str
    build: Callable
    deps: frozenset[str] = frozenset()
```

Năm coordinator mail khai:

```python
MAIL_DEPS = frozenset({"preview_template_email", "send_prepared_email",
                       "discard_prepared_email"})
```

### 3.2 HAI danh sách tool, không phải một

Đây là điểm mấu chốt về bảo mật, và là lý do không chọn cách đơn giản hơn là
"nhét deps vào `allowed_tools()`":

| Danh sách | Ai nhận | Nội dung |
|---|---|---|
| `tools` | planner, `erp_write_executor`, node SOP | đã lọc theo vai — GIỮ NGUYÊN |
| `coordinator_tools` | chỉ hàm dựng node coordinator | đã lọc **+** deps lấy từ `mcp_all_tools` |

Gộp làm một thì `preview_template_email` lọt vào tầm với của executor: LLM có thể
gọi thẳng nó với `template_name` bất kỳ, tức mở đúng lỗ hổng §1.2 đang đi bịt.
Tách hai danh sách khiến deps chỉ đến được **qua** coordinator sở hữu nó, mà
coordinator thì đã bị guard vai gác ở cửa vào.

Helper thuần, dễ test riêng:

```python
def tools_for_coordinator(spec, tools, mcp_all_tools):
    """tools + deps đã resolve. mcp_all_tools=None (test/admin) → trả tools."""
```

Áp ở `graph.py` dòng 91 (node preview) và dòng 133 (node gửi). `mcp_all_tools`
đã được `build_graph` nhận sẵn từ `erp_agent.py:185` — hiện chỉ dùng cho
`skill_role_gap`.

**Deps thiếu trong `mcp_all_tools`** (tức tool không tồn tại ở đâu cả) là lỗi cấu
hình, không phải chuyện vai: `tools_for_coordinator` raise, giống cách
`SkillManifestError` phân biệt hai trường hợp ở `skill_loader.py`.

### 3.3 Test chốt drift

Một test quét mọi literal `by_name.get("...")` trong `backend/src/agents/*.py` và
khẳng định tập đó ⊆ (tên coordinator trong `WRITE_COORDINATORS` ∪ mọi `deps` đã
khai). Thêm helper mới mà quên khai deps là test đỏ ngay.

Không quy literal về từng coordinator (mail_write.py chứa 5 coordinator, quy
thuộc sẽ mong manh) — kiểm bao hàm trên toàn tập là đủ mạnh để bắt đúng loại lỗi
này và không giòn.

**Giới hạn đã biết, nêu thẳng thay vì để người sau tưởng nó phủ hết:** test chỉ
thấy được literal chuỗi. Bốn chỗ hiện tra bằng biến —
`nodes.py:349 by_name.get(name)` (tên động, đúng thiết kế),
`edit_order.py:130 by_name.get(FLAG_TOOL)` (hằng module),
`edit_order.py:211` và `create_order.py:178` (`cfg.tool_name`, trùng tên
coordinator nên vô hại) — nằm ngoài tầm của test. `FLAG_TOOL` hiện là
`flag_order_for_review`, có trong `_WH_OWN`, nên hôm nay không sao; nếu ai đó
đổi nó thành một tool ngoài `roles.py` thì test này KHÔNG bắt được.

## 4. Allowlist template trong MCP

### 4.1 Nguồn sự thật

Thông tin hiện chẻ hai chỗ: `roles.py` biết vai → tool, `mail_write.py` biết tool
→ template. Allowlist là phép ghép hai cái đó, nên đặt ở `mail_write.py` (nó sở
hữu `EmailCfg`) và nhận `role_cfg` qua tham số — không tạo chiều import mới:

```python
def templates_for_role(role_cfg) -> frozenset[str] | None:
    """None = không giới hạn (admin, unrestricted=True)."""
```

`scripts/export_role_templates.py <role>` in ra CẢ HAI biến mà tiến trình MCP
cần — `MCP_ALLOWED_TEMPLATES` (§4.2) và `MCP_ALLOWED_MAIL_MODELS` (§4.3) — vì cả
hai suy từ cùng một phép ghép; `start-dev.ps1` gọi nó một lần cho mỗi vai.
Allowlist được **suy ra**, không khai lại — thêm coordinator mail mới là
allowlist tự đúng theo.

### 4.2 Cưỡng chế phía MCP

`preview_template_email` (`mcp-servers/odoo/tools/mail.py`) đọc
`MCP_ALLOWED_TEMPLATES` (phân tách bằng ký tự newline để tên template chứa dấu
phẩy không vỡ). Không đặt hoặc rỗng = không giới hạn — nên tiến trình admin và
mọi test hiện có không đổi hành vi.

Template không thuộc allowlist → trả envelope `ok=False` nêu rõ tên template bị
từ chối. KHÔNG nêu danh sách được phép (không rò thông tin cấu hình vai cho
đường gọi trực tiếp).

### 4.3 Cửa sau: `send_prepared_email`

`send_prepared_email(mail_id)` không nhận template — nó lật `state` rồi gửi. Ai
gọi thẳng `:8004` lấy được **bất kỳ** bản nháp `mail.mail` nào đang có và gửi đi;
allowlist template không chạm tới đường này.

Nên thêm kiểm thứ hai: đọc trường `model` của bản ghi `mail.mail` và đối chiếu
với tập `res_model` mà vai được phép (suy từ cùng `EmailCfg`, xuất qua
`MCP_ALLOWED_MAIL_MODELS`). Không có kiểm này thì §4.2 đóng cửa trước mà để mở
cửa sau.

**Giới hạn đã biết:** hai vai cùng res_model thì kiểm này không tách được
(hiện không xảy ra — `stock.picking` chỉ của kho, `account.move` chỉ của kế
toán). Ghi lại để lần sau thêm coordinator không tưởng nhầm nó mạnh hơn thực tế.

## 5. Đo `ir.rule` phía Odoo

### 5.1 Thay đổi

Hai nhóm mới trong `scripts/odoo_setup_ai_accounts.py`:
`Youdoo AI / Mail Warehouse`, `Youdoo AI / Mail Accounting`. Mỗi nhóm một
`ir.rule` trên `mail.template` với `perm_read=1`, `perm_write/create/unlink=0`,
domain giới hạn đúng template của vai (tra theo `name`, không hardcode id).

**Không** tạo nhóm hạn chế cho admin: `ir.rule` theo nhóm chỉ áp lên thành viên,
nên admin không thuộc nhóm nào là tự do đọc — không cần luật "cho phép tất cả".

Nhóm `Youdoo AI / Mail` hiện tại **giữ nguyên**: nó cấp `mail.mail` và
`ir.config_parameter` mà cả ba vai đều cần.

### 5.2 Vòng đo hồi quy — bắt buộc trước khi giữ

Rủi ro của A không phải chặn sai, mà chặn **thừa**: một thao tác khác của vai có
thể cần đọc template mà luật không cho (Odoo tự gửi mail khi validate phiếu
chẳng hạn). Chỉ đo mới biết.

Sau khi áp luật, chạy qua cổng vào thật toàn bộ tool `own` của hai vai:

- **kho:** `deliver_order`, `receive_order`, `validate_picking`,
  `internal_transfer`, `inventory_adjustment`, `scrap_product`, `return_order`
- **kế toán:** `post_invoice`, `register_payment`, `create_credit_memo`,
  `create_invoice_from_order`, `create_bill_from_po`

**Tiêu chí giữ:** không tool nào gãy vì lý do liên quan `mail.template`.
**Nếu gãy:** gỡ luật, giữ §4, ghi số đo và lý do vào báo cáo. Đây là kết quả
hợp lệ, không phải thất bại — §4 vẫn đóng đường tấn công thật.

## 6. MCP bind

`server.py:19` đổi `host="0.0.0.0"` thành
`host=os.environ.get("MCP_ODOO_HOST", "127.0.0.1")`. Backend gọi MCP qua
localhost nên không ảnh hưởng; nếu sau này chạy MCP trong container thì đặt lại
env. Cập nhật `docs/getting-started.md` nêu biến mới.

## 7. Nghiệm thu

### 7.1 Live, qua đúng cổng vào thật

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1 | kho gửi mail giao hàng | chạy được, có cổng xác nhận *(hiện đang chết)* |
| 2 | kế toán gửi mail hoá đơn | chạy được, có cổng xác nhận *(hiện đang chết)* |
| 3 | kho yêu cầu gửi mail hoá đơn | từ chối ở tầng agent, không cổng xác nhận |
| 4 | kế toán yêu cầu gửi mail giao hàng | từ chối ở tầng agent |
| 5 | **gọi thẳng `:8004`** `preview_template_email` với `"Invoice: Sending"` | MCP từ chối |
| 6 | **gọi thẳng `:8004`** `send_prepared_email` với mail_id của `account.move` | MCP từ chối |
| 7 | admin dùng được cả 5 coordinator mail | không hồi quy |

Kịch bản 5 và 6 là phép đo QUYẾT ĐỊNH của §4 — chúng bỏ qua toàn bộ tầng agent,
đúng vai trò mà tiêu chí 4 đã đóng trong đợt phân quyền. Không có hai phép đo
này thì §4 chỉ được chứng minh gián tiếp.

### 7.2 Test tự động

- `tools_for_coordinator`: trả đúng deps đã resolve; raise khi deps không tồn tại
  trong `mcp_all_tools`; trả nguyên `tools` khi `mcp_all_tools=None`
- Chốt drift `by_name` (§3.3)
- `templates_for_role`: khớp với `roles.py` × `MAIL_COORDINATOR_CFGS` cho cả hai
  profile; trả `None` cho admin
- Danh sách planner-visible **không** chứa deps — chốt trực tiếp cho §3.2
- MCP: allowlist cho qua template hợp lệ, từ chối template ngoài danh sách,
  không giới hạn khi env rỗng

### 7.3 Chuẩn không hồi quy

`1254 passed, 4 skipped, 46 deselected` với
`pytest -m "not live and not integration"`, cộng các test mới.

## 8. Rủi ro còn lại đã biết

- **`/v1/chat/completions` không có xác thực** và `run.py` mặc định
  `BACKEND_HOST=0.0.0.0`. Không đổi trong đợt này.
- **Kiểm `res_model` ở §4.3 không tách được hai vai cùng res_model** — hiện
  không xảy ra, nhưng sẽ âm thầm yếu đi nếu sau này thêm coordinator mail dùng
  chung model với vai khác.
- **Nếu §5 phải gỡ**, tầng Odoo vẫn không có backstop cho mail; cưỡng chế nằm ở
  agent + MCP. Hai lớp, không phải ba.
- **`discard_prepared_email` không có guard `role_scope`** — người gọi thẳng
  cổng MCP có thể `unlink` bất kỳ bản ghi `mail.mail` nào, kể cả bản nháp
  đang chờ gửi của vai khác. Phá hoại nhưng không phải một lần gửi không thể
  thu hồi, và người gọi kiểu này vốn đã cầm credential ghi đầy đủ của vai đó.
- **Backstop `ir.rule` phía Odoo (§5) chỉ phủ ĐỌC `mail.template`** — chống
  lưng cho `preview_template_email`, nhưng KHÔNG chống lưng cho đường
  `send_prepared_email` ở §4.3 (đụng `mail.mail`, không bao giờ đọc
  template). Người đọc §5 dễ hiểu nhầm rằng nó chống lưng cho toàn bộ mail.
- **Hợp đồng env không có cách biểu diễn "giới hạn về 0"** — một thay đổi
  chính sách hợp lệ (bỏ `send_delivery_email` khỏi `_WH_SIGN_OFF`) khiến
  `scripts/export_role_templates.py` exit khác 0 và làm sập cả launcher.
  Fail-loud có chủ đích, nhưng fix cuối cùng — một sentinel phân biệt "không
  giới hạn" với "không được gì" — cần được đặt tên.
