# Thông tin liên lạc khách hàng — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent có thể tra cứu và **chủ động** nêu email/SĐT của một khách
hàng cụ thể trong câu trả lời — năng lực đã có sẵn cho nhà cung cấp
(`get_supplier_detail`), nhưng chưa có cho khách hàng.

**Architecture:** Hàm đọc mới `get_customer_detail` trong `erp_query/sales.py`,
mirror `get_supplier_detail` (`purchase.py`), dùng lại helper resolve
`_resolve_single` — chuyển từ `purchase.py` (nơi nó đang là private helper)
sang `erp_query/resolve.py` (nhà chung, cạnh `resolve_entity` mà nó bọc
quanh) để hai module dùng chung không trùng lặp code. Đăng ký hàm mới làm
`@tool`. Thêm một rule mới vào `GATHER_ERP_PROMPT` để agent chủ động gọi
tool này (và `get_supplier_detail` sẵn có) khi câu trả lời xoay quanh đúng
một đối tác cụ thể có tính nghiệp vụ.

**Tech Stack:** Python 3.11, pytest, Odoo XML-RPC qua `erp_query.gateway`,
LangChain `@tool`.

**Spec:** `docs/superpowers/specs/2026-08-07-customer-contact-detail-design.md`

## Global Constraints

- Mọi hàm `erp_query` trả envelope `ok(data, display)` / `err(message)` từ
  `src/erp_query/envelope.py`, và nhận tham số `gw=None` để test tiêm
  gateway giả.
- `get_customer_detail` **không** đọc `bank_ids` — không có giá trị nghiệp
  vụ tương đương bản NCC (spec §2).
- Việc di chuyển `_resolve_single` sang `resolve.py` **không được đổi hành
  vi** — `get_supplier_detail` và `get_product_suppliers` (hai nơi đang
  dùng nó trong `purchase.py`) phải xanh nguyên không cần sửa test.
- Test assert rule prompt mới phải ghim **cả câu/mệnh đề hành động**, không
  chỉ từ khoá rời — quy ước đã có trong `test_prompts.py` (xem
  `test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai`): một sửa lệch
  đảo ngược nghĩa vẫn có thể giữ nguyên từ khoá rời.
- `/no_think` phải giữ nguyên là token cuối cùng của `GATHER_ERP_PROMPT`.
- Không thêm cờ môi trường bật/tắt hành vi mới.

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/src/erp_query/resolve.py` (sửa) | Thêm `_resolve_single` (chuyển từ purchase.py) | 1 |
| `backend/src/erp_query/purchase.py` (sửa) | Bỏ `_resolve_single`, import từ `.resolve` | 1 |
| `backend/src/erp_query/sales.py` (sửa) | Hàm mới `get_customer_detail` | 1 |
| `backend/tests/erp_query/test_sales.py` (sửa) | Test `get_customer_detail` | 1 |
| `backend/src/erp_query/tools.py` (sửa) | Đăng ký `get_customer_detail` làm `@tool` | 2 |
| `backend/tests/erp_query/test_tools.py` (sửa) | Test đăng ký tool | 2 |
| `backend/src/agents/prompts.py` (sửa) | Rule mới trong `GATHER_ERP_PROMPT` | 3 |
| `backend/tests/agents/test_prompts.py` (sửa) | Guard test cho rule mới | 3 |

---

### Task 1: Chuyển `_resolve_single` dùng chung + hàm `get_customer_detail`

**Files:**
- Modify: `backend/src/erp_query/resolve.py`
- Modify: `backend/src/erp_query/purchase.py`
- Modify: `backend/src/erp_query/sales.py`
- Test: `backend/tests/erp_query/test_sales.py`

**Interfaces:**
- Consumes: `ok`/`err` từ `.envelope`, `default_gateway` từ `.gateway`
  (đã import sẵn ở đầu `sales.py`); `resolve_entity` từ `.resolve` (đã
  import sẵn).
- Produces: `_resolve_single(model, query, gw) -> (row, None) | (None, error_msg)`
  export từ `erp_query/resolve.py`;
  `get_customer_detail(name, *, gw=None) -> envelope` với
  `data = {"partner": <dict>, "so_count": int}` trong
  `erp_query/sales.py`.

- [ ] **Step 1: Di chuyển `_resolve_single` sang `resolve.py`**

Trong `backend/src/erp_query/resolve.py`, thêm vào cuối file:

```python
def _resolve_single(model, query, gw):
    """resolve_entity envelope -> (row_with_id_and_name, None) | (None, error_msg).
    Dùng chung cho mọi bounded context cần resolve MỘT bản ghi res.partner/
    product.product... theo tên trước khi đọc chi tiết (get_supplier_detail,
    get_customer_detail, get_product_suppliers)."""
    env = resolve_entity(model, query, gw=gw)
    if env.get("status") != "success":
        return None, env.get("display") or "Lỗi tra cứu."
    data = env.get("data") or {}
    matches = data.get("matches") or []
    if not matches:
        return None, f"Không tìm thấy '{query}'."
    if data.get("needs_disambiguation"):
        names = "; ".join(f"{m['name']} (ID {m['id']})" for m in matches)
        return None, f"Có nhiều kết quả cho '{query}': {names}."
    exact = [m for m in matches if (m["name"] or "").strip().lower() == query.strip().lower()]
    chosen = exact[0] if exact else matches[0]
    return {"id": chosen["id"], "name": chosen["name"]}, None
```

Trong `backend/src/erp_query/purchase.py`:
1. Xoá định nghĩa `_resolve_single` (dòng 72-89 hiện tại — toàn bộ hàm vừa
   copy ở trên, nguyên văn).
2. Sửa dòng import đầu file từ:
   ```python
   from .resolve import resolve_entity
   ```
   thành:
   ```python
   from .resolve import resolve_entity, _resolve_single
   ```

Không đổi gì khác trong `purchase.py` — mọi lời gọi `_resolve_single(...)`
hiện có (`get_product_suppliers`, `get_supplier_detail`) giữ nguyên, giờ
resolve qua import thay vì định nghĩa cục bộ.

- [ ] **Step 2: Chạy test hồi quy để chắc chắn di chuyển không đổi hành vi**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_purchase.py -v`
Expected: PASS toàn bộ, **không sửa file test** — đặc biệt
`test_get_supplier_detail_happy_path`, `test_get_supplier_detail_ambiguous`,
`test_get_supplier_detail_not_found`, `test_get_product_suppliers_declared_and_history`.

- [ ] **Step 3: Viết test thất bại cho `get_customer_detail`**

Thêm vào cuối `backend/tests/erp_query/test_sales.py`:

```python
class MultiModelTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        return self.responses.get((model, method), [])


def test_get_customer_detail_happy_path():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(41, "Azure Interior")],
        ("res.partner", "search_read"): [{
            "id": 41, "name": "Azure Interior", "email": "contact@azure.example",
            "phone": "0900000000", "vat": "VN123456", "street": "12 Le Loi",
            "city": "HCMC", "property_payment_term_id": [3, "15 Days"]}],
        ("sale.order", "search_read"): [{"id": 1}, {"id": 2}, {"id": 3}],
    })
    out = sales.get_customer_detail("Azure", gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["so_count"] == 3
    assert out["data"]["partner"]["email"] == "contact@azure.example"
    assert "contact@azure.example" in out["display"]
    assert "0900000000" in out["display"]
    assert "bank_ids" not in out["data"]["partner"]
    partner_call = next(c for c in t.calls if c[0] == "res.partner" and c[1] == "search_read")
    assert "bank_ids" not in partner_call[3]["fields"]


def test_get_customer_detail_ambiguous():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(1, "Công ty A Miền Bắc"), (2, "Công ty A Miền Nam")],
    })
    out = sales.get_customer_detail("Công ty A", gw=Gateway(t))
    assert out["status"] == "error"
    assert "nhiều" in out["display"].lower()


def test_get_customer_detail_not_found():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({("res.partner", "name_search"): []})
    out = sales.get_customer_detail("Không tồn tại", gw=Gateway(t))
    assert out["status"] == "error"


def test_get_customer_detail_missing_fields_render_dash():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(9, "Acme Corporation")],
        ("res.partner", "search_read"): [{
            "id": 9, "name": "Acme Corporation", "email": False, "phone": False,
            "vat": False, "street": False, "city": False,
            "property_payment_term_id": False}],
        ("sale.order", "search_read"): [],
    })
    out = sales.get_customer_detail("Acme", gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["so_count"] == 0
    assert "—" in out["display"]
```

- [ ] **Step 4: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py -k get_customer_detail -v`
Expected: FAIL — `AttributeError: module 'src.erp_query.sales' has no attribute 'get_customer_detail'`

- [ ] **Step 5: Cài đặt `get_customer_detail`**

Sửa dòng import đầu `backend/src/erp_query/sales.py` từ:
```python
from .resolve import resolve_entity
```
thành:
```python
from .resolve import resolve_entity, _resolve_single
```

Thêm hàm vào cuối file:

```python
def get_customer_detail(name, *, gw=None):
    """Hồ sơ chi tiết MỘT khách hàng: liên hệ, thuế, điều khoản thanh toán,
    số đơn bán. Mirror get_supplier_detail (purchase.py), KHÔNG đọc bank_ids
    — không có giá trị nghiệp vụ tương đương bản NCC (spec 2026-08-07 §2)."""
    gw = gw or default_gateway()
    cus, msg = _resolve_single("res.partner", name, gw)
    if msg:
        return err(msg)
    try:
        rows = gw.search_read("res.partner", [["id", "=", cus["id"]]],
                              ["name", "email", "phone", "vat", "street", "city",
                               "property_payment_term_id"], limit=1)
        p = rows[0]
        sos = gw.search_read("sale.order", [["partner_id", "=", cus["id"]]],
                             ["id"], limit=200)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu hồ sơ khách hàng: {e}")
    term = p.get("property_payment_term_id")
    display = (f"Khách hàng: {p['name']}\n"
              f"  Email: {p['email'] or '—'} | Điện thoại: {p['phone'] or '—'}\n"
              f"  Mã số thuế: {p['vat'] or '—'}\n"
              f"  Địa chỉ: {p['street'] or '—'}, {p['city'] or '—'}\n"
              f"  Điều khoản thanh toán: {term[1] if term else '—'}\n"
              f"  Số đơn bán đã có: {len(sos)}")
    return ok({"partner": p, "so_count": len(sos)}, display)
```

- [ ] **Step 6: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py -v`
Expected: PASS toàn bộ file (test cũ vẫn xanh).

- [ ] **Step 7: Chạy lại test_purchase.py lần nữa (đảm bảo import mới không phá gì)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_purchase.py tests/erp_query/test_resolve.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 8: Commit**

```bash
git add backend/src/erp_query/resolve.py backend/src/erp_query/purchase.py backend/src/erp_query/sales.py backend/tests/erp_query/test_sales.py
git commit -m "feat(erp_query): get_customer_detail — mirror get_supplier_detail, dùng chung _resolve_single"
```

---

### Task 2: Đăng ký `get_customer_detail` làm tool cho agent

**Files:**
- Modify: `backend/src/erp_query/tools.py`
- Test: `backend/tests/erp_query/test_tools.py`

**Interfaces:**
- Consumes: `sales.get_customer_detail` (Task 1), `_json` helper đã có
  trong `tools.py`.
- Produces: tool tên `get_customer_detail` trong danh sách trả về của
  `build_erp_query_tools()`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/erp_query/test_tools.py`:

```python
def test_build_tools_exposes_get_customer_detail():
    names = {t.name for t in build_erp_query_tools()}
    assert "get_customer_detail" in names


def test_get_customer_detail_tool_returns_envelope_json(monkeypatch):
    import src.erp_query.tools as tmod
    monkeypatch.setattr(tmod.sales, "get_customer_detail",
                        lambda *a, **kw: {"status": "success",
                                          "data": {"so_count": 0}, "display": "ok"})
    tool = next(t for t in build_erp_query_tools() if t.name == "get_customer_detail")
    out = json.loads(tool.invoke({"name": "Acme"}))
    assert out["status"] == "success" and out["display"] == "ok"


def test_ref_shaped_get_customer_detail_name_rejected(monkeypatch):
    """name khớp hình dạng mã đơn (vd S00059) phải bị chặn — cùng cơ chế
    _reject_ref_shaped_partner_names đã áp cho list_sale_orders/customer."""
    import src.erp_query.tools as tmod
    monkeypatch.setattr(tmod.sales, "get_customer_detail",
                        lambda *a, **kw: {"status": "success", "data": {}, "display": "ok"})
    tool = next(t for t in build_erp_query_tools() if t.name == "get_customer_detail")
    with pytest.raises(ValidationError):
        tool.invoke({"name": "S00059"})
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_tools.py -k get_customer_detail -v`
Expected: FAIL — `StopIteration` (không có tool tên `get_customer_detail`).

- [ ] **Step 3: Đăng ký tool**

Trong `backend/src/erp_query/tools.py`, thêm ngay sau định nghĩa
`get_supplier_detail` (trước `list_crm_leads`):

```python
    @tool
    def get_customer_detail(name: str) -> str:
        """Hồ sơ chi tiết MỘT khách hàng: liên hệ, thuế, điều khoản thanh
        toán, số đơn bán."""
        return _json(sales.get_customer_detail(name))
```

Thêm `get_customer_detail` vào danh sách `tools = [...]` (ngay sau
`get_supplier_detail` trong danh sách).

- [ ] **Step 4: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_tools.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/src/erp_query/tools.py backend/tests/erp_query/test_tools.py
git commit -m "feat(erp_query): đăng ký get_customer_detail làm tool cho agent"
```

---

### Task 3: Rule chủ động gợi ý thông tin liên lạc trong `GATHER_ERP_PROMPT`

**Files:**
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_prompts.py`

**Interfaces:**
- Consumes: `GATHER_ERP_PROMPT` string hiện có (`prompts.py:166-175`).
- Produces: không export mới — chỉ sửa nội dung hằng số string đã có.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_prompts.py`:

```python
def test_gather_erp_prompt_chu_dong_neu_lien_lac_khi_dung_mot_doi_tac():
    """Rule mới (spec 2026-08-07): khi câu trả lời xoay quanh ĐÚNG MỘT đối
    tác cụ thể có tính nghiệp vụ, agent phải chủ động nêu contact — không
    chờ người dùng hỏi thẳng. Assert CẢ mệnh đề hành động (không chỉ từ
    khoá rời) — cùng lý do với test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai
    trong file này: một sửa lệch đảo ngược nghĩa vẫn có thể giữ từ khoá rời."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert ("hãy chủ động gọi get_customer_detail/get_supplier_detail và nêu "
            "email/SĐT nếu có, không cần người dùng hỏi thẳng"
            in GATHER_ERP_PROMPT)


def test_gather_erp_prompt_no_think_van_la_token_cuoi():
    """Chống hồi quy: thêm rule mới không được đẩy /no_think ra khỏi vị trí
    cuối cùng (bất biến của toàn bộ prompts.py, xem CHITCHAT_PROMPT/FUSE_PROMPT)."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert GATHER_ERP_PROMPT.rstrip().endswith("/no_think")
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py -k chu_dong_neu_lien_lac -v`
Expected: FAIL — chuỗi chưa xuất hiện trong `GATHER_ERP_PROMPT`.

- [ ] **Step 3: Sửa `GATHER_ERP_PROMPT`**

Trong `backend/src/agents/prompts.py`, `GATHER_ERP_PROMPT` hiện kết thúc:

```python
- Nếu câu hỏi ngụ ý người dùng muốn thực hiện một thao tác nhưng còn THIẾU một thông tin bắt buộc (nhà cung cấp, khách hàng, kho...), và bạn CÓ tool tra cứu được thông tin đó — hãy GỌI TOOL tra cứu trước, đừng hỏi lại người dùng khi tự tra được.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

Chèn một dòng rule mới **giữa** hai dòng trên (giữ nguyên `/no_think` ở vị
trí cuối):

```python
- Nếu câu hỏi ngụ ý người dùng muốn thực hiện một thao tác nhưng còn THIẾU một thông tin bắt buộc (nhà cung cấp, khách hàng, kho...), và bạn CÓ tool tra cứu được thông tin đó — hãy GỌI TOOL tra cứu trước, đừng hỏi lại người dùng khi tự tra được.
- Nếu câu trả lời xoay quanh ĐÚNG MỘT khách hàng/nhà cung cấp cụ thể làm trọng tâm (không phải danh sách nhiều đối tác), và câu hỏi có tính chất nghiệp vụ có thể cần liên hệ tiếp theo (đặt hàng, hỏi thêm, xác nhận, báo giá) — hãy chủ động gọi get_customer_detail/get_supplier_detail và nêu email/SĐT nếu có, không cần người dùng hỏi thẳng.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

- [ ] **Step 4: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py -v`
Expected: PASS toàn bộ file.

- [ ] **Step 5: Chạy hồi quy toàn bộ agents + erp_query**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/ tests/erp_query/ -q -m "not live and not integration"`
Expected: không có fail MỚI so với baseline trước plan này.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompts.py
git commit -m "feat(prompts): chủ động gợi ý thông tin liên lạc khi câu trả lời xoay quanh một đối tác"
```

---

### Task 4: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi kết quả vào
`docs/superpowers/plans/2026-08-07-customer-contact-detail-report.md`.

**Bối cảnh bắt buộc đọc trước:** rule prompt ở Task 3 chỉ thật sự chạy qua
LLM thật — unit test chỉ ghim đúng nội dung chuỗi, không chứng minh LLM
tuân theo. Cách gửi request phải khớp client thật: **resend toàn bộ lịch
sử hội thoại mỗi lượt, KHÔNG dùng `session_id`** (đúng phương pháp đã dùng
ở các plan trước, xem `2026-08-05-write-confirmation-ux-fix-report.md` và
`2026-08-06-invoice-confirm-summary-report.md`).

**Về rủi ro hồi quy eval (spec §4.3):** `evals/run_eval.py --set read` đo
`SYSTEM_PROMPT` qua `bind_tools` mô phỏng, **không** đụng `GATHER_ERP_PROMPT`
— không phải chốt chặn đúng cho thay đổi này. Tiêu chí 2 dưới đây (câu hỏi
liệt kê nhiều đối tác, qua backend thật — đúng node `gather_erp` thật dùng
`GATHER_ERP_PROMPT`) đã là chốt chặn hồi quy trực tiếp và sát thực tế hơn
một lượt eval suite tự động cho một thay đổi 1 dòng prompt như thế này.

- [ ] **Step 1: Khởi động hệ thống thật**

```powershell
.\start-dev.ps1
```

(Script tự phát hiện nếu `mcp-odoo`/`backend` đã chạy sẵn từ phiên trước và
bỏ qua khởi động lại — không cần restart nếu chúng đang khỏe.)

- [ ] **Step 2: Tiêu chí 1 — câu hỏi đơn khách hàng cụ thể, có tính nghiệp vụ**

Gửi: `"Khách Acme Corporation có đơn hàng nào đang chờ giao không?"`

ĐẠT khi: câu trả lời **kèm** email/SĐT thật của Acme Corporation, không
cần hỏi thẳng riêng một câu khác.

- [ ] **Step 3: Tiêu chí 2 — câu hỏi liệt kê nhiều đối tác, KHÔNG kích hoạt**

Gửi: `"Hóa đơn nào quá hạn thanh toán?"` (câu hỏi này trả về nhiều khách
khác nhau theo dữ liệu thật)

ĐẠT khi: câu trả lời liệt kê hóa đơn quá hạn **không** tự động kèm bộ
contact cho từng khách trong danh sách — chứng minh ngưỡng "đúng một đối
tác" hoạt động đúng, không gây nhiễu/tốn tool call thừa.

- [ ] **Step 4: Tiêu chí 3 — nhà cung cấp, chống hồi quy**

Gửi: `"Nhà cung cấp Individual Workplace là ai, thông tin liên lạc thế
nào?"`

ĐẠT khi: vẫn ra đúng email/SĐT nhà cung cấp thật như trước khi có plan này
— rule mới không phá nhánh `get_supplier_detail` đã hoạt động.

- [ ] **Step 5: Viết report và commit**

Ghi rõ từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (nội dung phản hồi thật,
email/SĐT thật xuất hiện). **Nếu bất kỳ tiêu chí nào KHÔNG ĐẠT, ghi nguyên
trạng, không tô hồng.**

```bash
git add docs/superpowers/plans/2026-08-07-customer-contact-detail-report.md
git commit -m "docs(customer-contact-detail): kết quả live-verify 3 tiêu chí"
```
