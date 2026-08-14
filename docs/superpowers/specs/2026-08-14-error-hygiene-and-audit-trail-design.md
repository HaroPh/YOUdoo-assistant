# Vệ sinh thông báo lỗi + khôi phục vệt kiểm toán — thiết kế

**Ngày:** 2026-08-14
**Trạng thái:** đã duyệt thiết kế, chưa lập plan
**Nguồn:** nợ "21/33 tool MCP rò nguyên văn lỗi Odoo" mang từ đợt
role-based-access; khảo sát đợt này lật ra hai vấn đề lớn hơn hẳn nợ gốc.

---

## 0. Tóm tắt

Ba việc, có quan hệ nhân quả nên đi cùng một đợt:

1. **Vệt kiểm toán MCP chưa từng ghi được dòng nào.** Bảng `mcp_call_log`
   không tồn tại trong database. Dựng bảng, và làm cho "bảng có thật" trở
   thành thứ kiểm được.
2. **89 chỗ trên 4 tầng nội suy nguyên văn exception vào câu trả lời người
   dùng, 0 chỗ được ghi log.** Bịt cả 89, chuyển dấu vết vào log.
3. **Quyền đọc `mail.activity` không được bất kỳ lưới nào canh.** Đưa vào
   bảng kiểm quyền, và bịt lỗ cấu trúc khiến tool chỉ-đọc lọt qua.

Việc 1 là **tiền đề** của việc 2, không phải phình phạm vi: lý lẽ duy nhất
biện minh cho việc giấu lỗi khỏi người dùng là "vẫn còn dấu vết ở nơi khác"
— mà lý lẽ đó hiện sai.

---

## 1. Các phép đo làm nền cho thiết kế

Mọi con số dưới đây đo ngày 2026-08-14 trên hệ thống đang chạy, không suy
từ code.

### 1.1 ⚠️ `mcp_call_log` chưa từng tồn tại

Truy vấn `pg_tables` trên database mà `DATABASE_URL` trỏ tới:

```
checkpoint_blobs, checkpoint_migrations, checkpoint_writes, checkpoints,
erp_entity_index, llm_usage, rag_chunks, rag_documents, rag_embedding_marker
```

Không có `mcp_call_log`. `event_log.log_mcp_event` nuốt **mọi** lỗi ghi
("KHÔNG được làm hỏng tool" — đúng về nguyên tắc), nên `UndefinedTable` bị
nuốt im lặng ở từng lượt gọi, từ ngày port đến nay.

Đã loại trừ khả năng nhìn nhầm database: `config.py` đọc `DATABASE_URL` từ
môi trường; `.env` và `.env.example:7` đều trỏ `localhost:5434/ai_assistant`
— đúng database đã truy vấn. `DATABASE_URL` trong `docker-compose.yml` là DB
riêng của Langfuse, dịch vụ khác.

Trong repo **không có** `CREATE TABLE mcp_call_log` ở bất kỳ đâu: không
migration, không `.sql`, không docs. `backend/migrations/` chỉ có
`001_llm_usage.sql`. Cũng không có test nào cho `event_log.py` hay
`audit_chain.py`.

**Mất mát rộng hơn thông báo lỗi.** Cùng hàm đó ghi `permission_denied`
(`odoo_call.py:51,56`), `rate_limit`, `write_gate_error`, và `model_access`
cho **mọi** lệnh đọc/ghi Odoo. Toàn bộ vệt kiểm toán — kèm hash-chain chống
sửa mà một spec riêng từng được viết ra để thiết kế — chưa từng ghi được gì.

**Và phép kiểm cũng không kiểm được gì.** `verify_audit_chain.py` trên bảng
rỗng in `OK — 0 dòng, chuỗi nguyên vẹn` rồi thoát 0.

### 1.2 Không có cơ chế migration nào cả

`backend/migrations/001_llm_usage.sql` là một file SQL nằm đó: không runner,
không được nhắc trong `getting-started.md`, ai đó chạy tay một lần (bảng
`llm_usage` có thật). `mcp_call_log` không bao giờ có file để mà chạy.

⇒ Chỉ thêm `002_mcp_call_log.sql` rồi thôi sẽ **tái tạo đúng lỗi này**.

### 1.3 ⚠️ Lỗi Odoo liệt kê nguyên bản đồ phân quyền

Đo bằng cách xác thực `ai-warehouse` (uid 9) rồi `search_read` trên
`account.move`. Nguyên văn `faultString`:

```
Xin lỗi, bạn không được phép truy cập vào dữ liệu 'Journal Entry' (account.move).

Thao tác này được phép cho các nhóm sau:
	- Accounting/Administrator
	- Accounting/Invoicing
	- Purchase/User
	- Sales/User: Own Documents Only
	- Youdoo AI / Read Only
	- Role / Portal
	- Show Accounting Features - Readonly

Liên hệ với quản trị viên của bạn để yêu cầu quyền truy cập nếu cần.
```

Đây là lộ thông tin thật, không phải chuyện thẩm mỹ: người dùng đọc được
chính xác cần nhóm nào để có thêm quyền, kể cả tên nhóm tự tạo của dự án
(`Youdoo AI / Read Only`).

**Phát hiện phụ, ngoài phạm vi đợt này:** cùng phép đo cho thấy
`ai-warehouse` **đọc được** `ir.config_parameter` và `res.groups`. Cái đầu ở
Odoo thường chứa khoá/token cấu hình. Xem §6.

### 1.4 ⚠️ 89 chỗ rò, trên 4 tầng — và tầng nguy hiểm nhất KHÔNG phải MCP

| Tầng | Số chỗ | Nội dung rò |
|---|---|---|
| `mcp-servers/odoo/tools/` | 21 | lỗi Odoo, đã qua `odoo()` |
| **`backend/src/erp_query/` (đường ĐỌC)** | **44** | **nguyên văn Fault Odoo** |
| `backend/src/agents/` (điều phối GHI) | 23 | lỗi transport/Python |
| `backend/skills/` | 1 | — |
| **Tổng** | **89** | |

Đếm riêng ở `backend/src` + `backend/skills`: **68 chỗ đi ra người dùng, 0
chỗ vào logger.** Ba chỗ còn nội suy exception mà KHÔNG ra người dùng đều là
`raise` nội bộ (`skill_manifest.py` ×2, `rag/embed.py`) — fail-loud lúc nạp
cấu hình, giữ nguyên.

**Đường ĐỌC nặng nhất.** `erp_query/gateway.py:32-36` gọi thẳng Odoo và
**không bọc gì**:

```python
def _call(self, model, method, args, kwargs):
    if method not in READ_METHODS:
        raise GatewayError(f"Method '{method}' không được phép (chỉ đọc).")
    self._check_model(model)
    return self._t.call(model, method, args, kwargs)
```

Fault bay nguyên vẹn lên `erp_query/*.py` rồi vào `err(f"...: {e}")`. Nghĩa
là đường được dùng nhiều nhất trong toàn trợ lý rò **đúng nguyên văn** đoạn
văn ở §1.3 — trong khi tầng MCP chỉ rò gián tiếp.

⚠️ Nợ gốc ghi "21/33 tool MCP". Con số 21 đúng, 33 sai (35 tool), và quan
trọng hơn: **nó chưa bao giờ được hỏi liệu tầng khác có cùng khuôn không.**
Một lưới chống tái diễn chỉ quét `mcp-servers/odoo/tools/` sẽ báo **xanh**
trong khi 68 chỗ vẫn rò — đúng hạng lỗi "test đo không gì" dự án đã vấp
nhiều lần. Vì vậy §2.5 là ràng buộc, không phải tuỳ chọn.

### 1.5 Quyền đọc `mail.activity` hiện CÓ — nên đây thuần là chuyện lưới

Xác thực từng tài khoản AI rồi `search_read` `mail.activity`:

```
ai-warehouse    uid= 9  READ OK, 0 dòng của mình
ai-accounting   uid=10  READ OK, 0 dòng của mình
```

Không có lỗi sống cần sửa. Nhưng **không lưới nào canh**:

- `TOOL_ACCESS_MAP` khai `close_activity: [("mail.activity","write")]` — tool
  đó `search_read` TRƯỚC khi ghi, cặp `read` không được khai.
- `find_my_activities` **không có trong bảng nào cả**: không ở `roles.py` nên
  `test_moi_tool_trong_roles_deu_duoc_bang_phu` không phủ; không ở
  `TOOL_ACCESS_MAP` cũng không ở `UNMAPPED_TOOLS`.

Và cả hai vai trả **0 dòng của chính mình**, nên nếu quyền đọc hỏng thì kết
quả trông y hệt "không có việc nào được giao". Suy từ kết quả rỗng không
phân biệt được hai trạng thái đó — phải canh tường minh.

---

## 2. Quyết định thiết kế

### 2.1 Dựng bảng trong chính đợt này

Không tách đợt riêng. §1.1 làm hỏng tiền đề của cả việc 2: bịt lỗi khỏi
người dùng chỉ chấp nhận được nếu dấu vết còn ở nơi khác.

### 2.2 MCP từ chối khởi động nếu thiếu bảng

Có `DATABASE_URL` mà thiếu `mcp_call_log` ⇒ server **không lên**, báo rõ
lệnh migration phải chạy. Không có `DATABASE_URL` ⇒ im lặng bỏ qua, vì
"không cấu hình = tắt log" vốn là thiết kế có chủ ý của `event_log.py`.

Cùng triết lý `assert_embedding_marker` đã có trong repo: thà không lên còn
hơn lên sai. Đây là lựa chọn có giá — ai kéo code về mà chưa chạy migration
sẽ thấy server không lên; §3.1 bắt buộc `getting-started.md` nói rõ.

Hai phương án đã cân nhắc và loại: `CREATE TABLE IF NOT EXISTS` tự động lúc
khởi động (schema do code sinh, sẽ lệch khỏi file migration lúc nào không
biết); file SQL + tài liệu + test `integration` (test đó không chạy trong
cổng mặc định nên vẫn trôi âm thầm — đúng cách vấn đề này đã xảy ra).

### 2.3 Một câu chung theo từng tool, không phân loại nguyên nhân

Người dùng thấy ví dụ: *"Không tạo được hóa đơn cho đơn SO123 — thao tác
chưa được thực hiện. Nếu lặp lại, báo quản trị viên."*

Không phân loại "thiếu quyền" / "sai trạng thái" / "lỗi hệ thống". Hai
phương án đã loại:

- **Phân loại theo vị trí trong code** (khuôn `close_activity`, bọc riêng
  lệnh Odoo đầu tiên): hữu ích hơn nhưng phải sửa **cấu trúc** 89 chỗ chứ
  không chỉ đổi chuỗi — rủi ro hồi quy trên đường ghi không tương xứng lợi
  ích, nhất là khi phân quyền đã được cưỡng chế ở tầng allowlist MCP nên lỗi
  quyền từ Odoo là đường backstop hiếm gặp.
- **Giữ câu đầu/cuối của Odoo, cắt danh sách nhóm**: phải cắt theo mẫu văn
  bản, mà mẫu đó đổi theo phiên bản và ngôn ngữ Odoo — cắt hụt là lộ lại.

### 2.4 Ghi log ở tầng bắt lỗi, dù `odoo()` đã ghi

`odoo()` chỉ ghi lỗi đi qua nó. `except Exception` ở tầng gọi bắt rộng hơn:
bug Python của chính tool/coordinator (`KeyError` trong helper resolve,
lỗi parse, lỗi transport MCP) — những thứ hiện **không** được ghi ở đâu.
Bịt chúng mà không thêm gì sẽ biến cả một hạng lỗi thành vô hình.

**Hai đích, theo tầng:**

| Tầng | Đích | Lý do |
|---|---|---|
| MCP | `logger` tiến trình **và** `log_mcp_event("tool_error", …)` | tiến trình MCP là biên bảo mật; bảng có hash-chain, truy vấn được |
| backend | `logger` (`logs/backend_err.log`) | backend không có bảng kiểm toán; dựng một cái nữa là ngoài phạm vi |

MCP ghi **cả hai**, không chỉ bảng: nếu chỉ ghi bảng thì môi trường không có
`DATABASE_URL` sẽ làm lỗi biến mất hoàn toàn — đúng lỗ hổng đợt này đi đóng.

### 2.5 Lưới quét phải phủ CẢ BỐN tầng ngay từ đầu

Ràng buộc, không tuỳ chọn — xem §1.4. Lưới phủ một tầng tạo ra tín hiệu sai
nguy hiểm hơn không có lưới.

---

## 3. Kiến trúc

Quy ước định danh: mã nguồn (`backend/src`, `mcp-servers`) dùng **định danh
tiếng Anh**, chú thích và chuỗi hiển thị tiếng Việt. Mã test trong
`backend/tests` theo quy ước phiên âm tiếng Việt đã có ở đó.

### 3.1 Migration + kiểm khởi động

**`backend/migrations/002_mcp_call_log.sql`** — đúng 12 cột mà
`event_log.py` ghi và `verify_audit_chain.py:9-11` đọc:

```sql
CREATE TABLE IF NOT EXISTS mcp_call_log (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL,
    event_type    text        NOT NULL,
    caller        text,
    tool_name     text,
    model_name    text,
    operation     text,
    duration_ms   integer,
    error_code    text,
    error_message text,
    entry_hash    text,
    prev_hash     text
);
```

`entry_hash`/`prev_hash` để NULL được: `fetch_rows` lọc
`WHERE entry_hash IS NOT NULL`, tức schema đã lường trước dòng chưa
hash-chain. Không đặt ràng buộc `CHECK` trên `event_type` — thêm loại sự
kiện mới (đợt này thêm `tool_error`) không được đòi migration.

**`event_log.assert_log_table_ready()`** — hàm mới, gọi từ `server.py`
trước khi đăng ký tool. Không có `DATABASE_URL` ⇒ trả về ngay. Có mà thiếu
bảng ⇒ `raise RuntimeError` nêu tên file migration.

**`verify_audit_chain.py`** — tách "bảng rỗng" khỏi "chuỗi nguyên vẹn". Bảng
rỗng không phải bằng chứng toàn vẹn; nó là "chưa có gì để kiểm" và phải nói
đúng như vậy.

**`docs/getting-started.md`** — thêm mục chạy migration, liệt kê **cả
`001_llm_usage.sql`** (hiện không được nhắc ở đâu).

### 3.2 Helper tầng MCP — `mcp-servers/odoo/helpers.py`

```python
def fail(tool_name: str, display: str, exc: Exception) -> str:
    """Ghi nguyên văn lỗi vào log + vệt kiểm toán; trả câu KHÔNG lộ.

    Ghi CẢ HAI đích: thiếu DATABASE_URL thì log_mcp_event im lặng không làm
    gì, nên nếu chỉ dựa vào nó thì lỗi biến mất hoàn toàn."""
    detail = f"{type(exc).__name__}: {exc}"
    logger.exception("tool %s thất bại: %s", tool_name, detail)
    log_mcp_event("tool_error", tool_name=tool_name, error_code="E500",
                  error_message=detail)
    return envelope(False, display)
```

21 điểm gọi đổi từ `return envelope(False, f"…: {e}")` sang
`return fail("<tên tool>", "<câu chung>", e)`.

**Hai điều kiện phải dựng cùng, không được coi là có sẵn:**

- `helpers.py` hiện **không có logger** (chỉ `import json`, `datetime`,
  `odoo_call`). Phải thêm `logging` + `logger = logging.getLogger(__name__)`
  và `from event_log import log_mcp_event`. Không có vòng import: `event_log`
  chỉ phụ thuộc `audit_chain` và `config`.
- `server.py` **không cấu hình `logging`**. stderr mỗi tiến trình MCP đã được
  `start-dev.ps1:128-129` chuyển vào `logs/mcp-odoo-<vai>_err.log`, nên
  `logger.exception` hiện tới đích **chỉ nhờ handler `lastResort` mặc định
  của Python** — đúng ngẫu nhiên, và im lặng mất nếu ai đó thêm cấu hình
  logging khác. Dựng `basicConfig` tường minh ở `server.py`, và test phải
  khẳng định dòng log thật sự phát ra chứ không chỉ khẳng định hàm được gọi.

### 3.3 Helper tầng backend

Hai hình dạng trả về khác nhau nên hai helper, cùng một khuôn:

- **`backend/src/erp_query/envelope.py`** — thêm `fail_read(where, display,
  exc)` trả `err(display)` sau khi `logger.exception`. 44 điểm gọi.
- **`backend/src/agents/create_order.py`** — `_msg()` định nghĩa **một chỗ
  duy nhất** ở `create_order.py:67`, 8 coordinator còn lại import lại từ đó.
  Helper mới đặt ngay cạnh nó, cùng đường import sẵn có, trả `_msg(display)`
  sau khi `logger.exception`. 23 điểm gọi.
- **`backend/skills/bao-gia-chiet-khau/logic.py:135`** — 1 điểm gọi, nằm
  ngoài cây `src/` nên không import được helper trên; xử lý tại chỗ theo cùng
  khuôn (log rồi trả câu chung).

### 3.4 Lưới chống tái diễn

Một test quét **cả bốn** cây nguồn, bắt mọi chuỗi đi ra người dùng có nội
suy biến exception. Ba điểm bắt buộc:

1. **Quét theo LOẠI TRỪ, không theo liệt kê.** Lưới duyệt mọi `*.py` từ gốc
   repo, trừ một danh sách nhỏ và ổn định (`.venv`, `__pycache__`,
   `.worktrees`, `.claude`, `backend/tests`, `backend/spikes`, `docs`). Liệt
   kê 4 thư mục nguồn thì thêm cây nguồn thứ 5 sẽ hụt im lặng — đúng cơ chế
   đã làm nợ gốc chỉ đếm 21/89. Loại trừ thì cây mới **tự động được phủ**,
   tức hụt về phía an toàn.
2. Ba chỗ `raise` nội bộ ở §1.4 nằm trong danh sách miễn trừ **kèm lý do**,
   không im lặng bỏ qua.
3. **Phép thử phá bắt buộc**: thêm lại một chỗ rò vào MỖI tầng trong bốn
   tầng ⇒ lưới phải đỏ ở cả bốn. Đây chính xác là loại test dễ viết thành đo
   -không-gì; không có phép thử phá thì không nghiệm thu.

### 3.5 Canh quyền đọc `mail.activity`

- `TOOL_ACCESS_MAP`: thêm `("mail.activity","read")` vào dòng
  `close_activity`; thêm dòng mới cho `find_my_activities`.
- **Lỗ cấu trúc**: `_declared_tools()` chỉ lấy tool **ghi** khai trong
  `roles.py`, nên mọi tool **chỉ-đọc** lọt qua cả hai lưới. Mở nguồn phủ để
  tool đọc cũng buộc phải khai, hoặc nằm trong `UNMAPPED_TOOLS` kèm lý do.
- `backend/src/erp_query/crm.py:88` đọc `mail.activity` ở tầng khác hẳn
  (gateway backend, không phải tool MCP) — **ngoài phạm vi** bảng này, ghi
  lý do vào §6 thay vì im lặng bỏ.

---

## 4. Rủi ro đã biết

**4.1 Đổi văn bản người dùng nhìn thấy.** Hai test đang khớp chuỗi sẽ phải
đổi: `test_create_order_node.py:312` (`"Lỗi khi tạo đơn"`) và
`test_skill_bao_gia_chiet_khau_flow.py:320` (`"Lỗi khi tạo báo giá:"`). Plan
phải **đo lại** danh sách này ngay trước khi sửa, không dùng lại con số ở
đây — 89 điểm gọi là bề mặt lớn, và chính đợt này đã một lần đếm thiếu.

**4.2 MCP không lên nếu chưa chạy migration.** Là chủ đích (§2.2), nhưng
nghĩa là nghiệm thu sống phải khởi động lại **cả bốn** tiến trình MCP sau khi
chạy migration, không chỉ một.

**4.3 Bề mặt sửa lớn, cơ học, lặp lại.** 89 điểm gọi trên 4 tầng là đúng
loại việc mà người thực thi dễ sửa 85 chỗ rồi báo xong. §3.4 phép thử phá
theo từng tầng là lưới bắt chuyện đó, không phải phần trang trí.

**4.4 `log_mcp_event` nuốt mọi lỗi.** Sau đợt này bảng đã tồn tại, nhưng
hành vi nuốt vẫn giữ (đúng: log không được làm hỏng tool). Nghĩa là một lỗi
ghi log mới sẽ lại im lặng. `assert_log_table_ready` chỉ chặn được đúng
nguyên nhân đã biết là thiếu bảng — không phải mọi nguyên nhân.

---

## 5. Nghiệm thu

### 5.1 Test

- **Đơn vị**: `assert_log_table_ready` — thiếu bảng ⇒ ném; thiếu
  `DATABASE_URL` ⇒ im lặng. Kèm phép thử phá: gỡ lời gọi trong `server.py` ⇒
  phải có test đỏ.
- **Tích hợp** (đánh dấu `integration`, nối DB thật): gọi `log_mcp_event`
  rồi **đọc lại dòng vừa ghi**, kiểm cả `entry_hash` khớp
  `audit_chain.compute_entry_hash`. Đây là test duy nhất chứng minh vòng ghi
  khép kín — thứ đã vắng mặt suốt và là lý do cả cơ chế chết mà không ai
  biết.
- **Lưới quét** §3.4 kèm phép thử phá bốn tầng.
- **`TOOL_ACCESS_MAP`** §3.5: thêm một tool chỉ-đọc giả không khai ⇒ test
  phủ phải đỏ.
- Lệnh chạy: `pytest -m "not integration and not live"` cho cổng thường;
  bộ `integration` chạy riêng, có DB.

### 5.2 Nghiệm thu sống, TRƯỚC merge

Trên worktree của nhánh, không phải trên `main`:

1. Chạy `002_mcp_call_log.sql`, khởi động lại 4 tiến trình MCP + backend.
2. Gây một lỗi quyền thật (vai kho hỏi dữ liệu kế toán) qua **UI thật** —
   kiểm câu trả lời **không** chứa tên nhóm Odoo nào.
3. Truy vấn `mcp_call_log` — dòng tương ứng phải có, `error_message` phải
   chứa nguyên văn lỗi.
4. Chạy `verify_audit_chain.py` — phải báo chuỗi nguyên vẹn trên dữ liệu
   thật, không phải trên bảng rỗng.

Bước 2 và 3 là một cặp: câu trả lời sạch **và** dấu vết còn. Thiếu một trong
hai thì đợt này thất bại theo đúng nghĩa nó đặt ra.

### 5.3 Không được thụt

Cổng eval hiện có (`intent` 0.870, `planner` 1.000, `sop_select` hijack=0)
không được thụt. Đợt này không đụng prompt, nên bất kỳ thay đổi nào ở đó đều
là tín hiệu có gì đó sai.

---

## 6. Ngoài phạm vi

**6.1 `ai-warehouse` đọc được `ir.config_parameter` và `res.groups`.** Đo ở
§1.3. `ir.config_parameter` ở Odoo thường chứa khoá/token cấu hình. Đây là
vấn đề **cấu hình quyền Odoo**, không phải vệ sinh thông báo lỗi, và cần một
phép rà riêng trên mọi model nhạy cảm — không nhét vào đợt này.

**6.2 Vệt kiểm toán cho tầng backend.** Backend ghi vào `logger`, không vào
bảng hash-chain. Dựng bảng kiểm toán thứ hai cho backend là một quyết định
kiến trúc riêng, chưa có nhu cầu chứng minh được.

**6.3 `erp_query/crm.py:88` đọc `mail.activity`.** Tầng gateway backend,
không phải tool MCP, nên nằm ngoài `TOOL_ACCESS_MAP` theo đúng thiết kế của
bảng đó (§3.5). Ghi lại để không ai tưởng đã phủ.

**6.4 Spec hash-chain gốc không tồn tại trong Youdoo.** Ba file
(`event_log.py`, `audit_chain.py`, `verify_audit_chain.py`) đều trỏ
`docs/superpowers/specs/2026-07-23-audit-trail-hash-chain-design.md`, không
có trong repo này. Đợt này dựng bảng theo đúng cột mà code hiện hành đọc và
ghi, không đi khôi phục spec gốc.

**6.5 Vai kho chưa vào cổng eval** — nợ có chủ ý từ đợt eval-role-fidelity.

**6.6 Phân loại nguyên nhân lỗi cho người dùng.** §2.3 loại có chủ ý. Nếu về
sau đo được rằng người dùng thật sự bí vì không biết lỗi thuộc loại nào,
khuôn `close_activity` (phân loại theo vị trí, không đọc nội dung lỗi) là
đường đi đã có tiền lệ.
