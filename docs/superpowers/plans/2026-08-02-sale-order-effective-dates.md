# Thêm ngày giao thật vào `get_sale_order_detail` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `get_sale_order_detail` đọc thêm `commitment_date`/`effective_date`
(cả hai đã xác nhận tồn tại thật trên Odoo qua chẩn đoán trực tiếp) — đóng
2 lỗ hổng còn lại trong `_KNOWN_GAPS` của contract test. Trước đó, sửa một
lỗ hổng thật vừa phát hiện trong chính contract test: nó chỉ bắt được 1
trong 2 kịch bản "cấu hình chết" mà nó tự nhận đã bắt cả hai.

**Architecture:** 3 task tuần tự — sửa logic contract test trước (để nó có
khả năng phát hiện đúng), rồi mới thêm field (để phép thử "tự báo lỗi" có
ý nghĩa thật), rồi đo thật qua Odoo (không dùng S00042 — đơn đó đang
`draft`, không có ngày giao thật) để xác nhận toàn bộ chuỗi.

**Tech Stack:** Python 3.12, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-08-02-sale-order-effective-dates-design.md`

## Global Constraints

- **Không lộ tool mới, không sửa `GATHER_ERP_PROMPT`, không sửa
  `backend/evals/cases.py` (`GATHER_CASES`).**
- **Trình tự bắt buộc, không được đảo**: sửa logic contract test (Task 1)
  → thêm field vào `get_sale_order_detail` (Task 2) → đo thật + dọn
  `_KNOWN_GAPS` (Task 3).
- Chạy Python bằng `backend/.venv/Scripts/python.exe`. Đặt
  `PYTHONIOENCODING=utf-8` trước lệnh in tiếng Việt hoặc chạy script gọi
  Odoo thật.
- "Full suite" = `pytest -m "not integration and not live"` (unit-only) +
  `pytest -m integration`.
- **Không hard-code số đơn cụ thể cho bước đo Odoo thật (Task 3)** — dữ
  liệu demo đã chứng minh trôi theo thời gian (S00042 hiện `draft`, không
  giống giả định các plan trước). Tra động một đơn có `effective_date`
  thật tại thời điểm chạy.

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Sửa | `backend/tests/jobs/test_eval_gather.py` | Sửa logic `_KNOWN_GAPS` (Task 1); dọn 2 dòng ngoại lệ (Task 3) |
| Sửa | `backend/src/erp_query/sales.py` | `get_sale_order_detail` đọc thêm `commitment_date`/`effective_date` |
| Sửa | `backend/src/erp_query/tools.py` | Docstring tool cập nhật |
| Sửa | `backend/tests/erp_query/test_sales.py`, `test_tools.py` | Test mới |
| Tạo | `docs/superpowers/plans/2026-08-02-sale-order-effective-dates-report.md` | Báo cáo |

---

## Task 1: Sửa lỗ hổng cấu hình chết trong contract test

**Files:**
- Modify: `backend/tests/jobs/test_eval_gather.py:344-373`
  (`test_gather_cases_fixture_labels_match_real_tool_fields`)

**Interfaces:**
- Consumes: `_DATE_STATUS_LABELS`, `_KNOWN_GAPS`, `_real_fields_for_tool`
  (đã có sẵn, không đổi chữ ký).
- Produces: logic mới trong test — Task 2/3 dựa vào việc test này BÁO LỖI
  đúng khi field thật đã có cho một mục trong `_KNOWN_GAPS`.

- [ ] **Step 1: Đọc đúng vị trí cần sửa**

Mở `backend/tests/jobs/test_eval_gather.py`, xác nhận hàm
`test_gather_cases_fixture_labels_match_real_tool_fields` (dòng 344-373)
khớp CHÍNH XÁC:

```python
def test_gather_cases_fixture_labels_match_real_tool_fields():
    """Đối chiếu fixture với field THẬT tool trả về — chặn lớp lỗi "fixture
    khẳng định khả năng tool không có" (gặp 2 lần: gather-erp-tool-fix,
    sale-order-detail-dates). 2 vi phạm đã biết nằm trong _KNOWN_GAPS,
    không bị chặn ở đây — xem comment tại đó. `used` đảm bảo mỗi mục trong
    _KNOWN_GAPS thật sự còn cần thiết — nếu gap đã được sửa (field thật đã
    có) hoặc fixture đã đổi chữ (nhãn không còn khớp), mục thừa sẽ bị bắt
    ngay, không nằm lại như cấu hình chết mãi mãi (final review 2026-08-02,
    finding Important #1 — chính _KNOWN_GAPS là một khẳng định viết tay về
    thực tế, không có gì kiểm tra nó còn đúng, tái diễn đúng lớp lỗi nhánh
    này chặn)."""
    used = set()
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for tool_name, fixture_text in tool_fixtures.items():
            real_fields = _real_fields_for_tool(tool_name)
            low = fixture_text.casefold()
            for label, field_names in _DATE_STATUS_LABELS.items():
                if label not in low:
                    continue
                if (topic, tool_name, label) in _KNOWN_GAPS:
                    used.add((topic, tool_name, label))
                    continue
                assert set(field_names) & real_fields, (
                    f"case {topic}: fixture của tool {tool_name!r} dùng nhãn "
                    f"{label!r} nhưng tool không có field thật nào trong "
                    f"{field_names} (field thật: {sorted(real_fields)})")
    assert used == _KNOWN_GAPS, (
        f"_KNOWN_GAPS có mục không còn ứng với vi phạm thật (gap đã lấp "
        f"hoặc fixture đã đổi chữ): {sorted(_KNOWN_GAPS - used)} — xoá mục "
        f"đó khỏi _KNOWN_GAPS, đừng để nó nằm lại như cấu hình chết.")
```

**Lỗ hổng thật**: dòng `if key in _KNOWN_GAPS: used.add(...); continue`
thoát NGAY, không bao giờ kiểm tra `set(field_names) & real_fields` cho
mục đó — nghĩa là nếu field thật ĐÃ CÓ (gap đã được sửa ở nơi khác), test
KHÔNG BAO GIỜ biết, mục cứ nằm lại trong `_KNOWN_GAPS` mãi mãi mà không bị
báo lỗi. Chỉ kịch bản "nhãn không còn khớp câu chữ fixture" mới bị
`assert used == _KNOWN_GAPS` bắt được.

Nếu nội dung KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT.

- [ ] **Step 2: Viết test thất bại trước — xác nhận lỗ hổng có thật**

Thêm hàm test mới NGAY TRƯỚC
`test_gather_cases_fixture_labels_match_real_tool_fields`:

```python
def test_known_gaps_catches_entry_when_real_field_now_exists(monkeypatch):
    """Xác nhận sửa lỗ hổng: nếu real_fields giờ khớp một mục trong
    _KNOWN_GAPS, test chính phải FAIL đòi xoá mục — không được im lặng
    pass. Bug thật tìm thấy khi viết plan sale-order-effective-dates: bản
    gốc (trước sửa ở Step 3 dưới) chỉ bắt được kịch bản "nhãn không còn
    khớp câu chữ", không bắt được kịch bản này — continue thoát trước khi
    kiểm tra field thật."""
    def _fake_real_fields(tool_name):
        if tool_name == "get_sale_order_detail":
            # Giả lập: field thật GIỜ ĐÃ CÓ commitment_date/effective_date
            # — đúng 2 field _KNOWN_GAPS hiện đang ngoại lệ.
            return {"id", "name", "partner_id", "amount_total", "state",
                    "date_order", "delivery_status",
                    "commitment_date", "effective_date"}
        return _real_fields_for_tool(tool_name)

    monkeypatch.setitem(globals(), "_real_fields_for_tool", _fake_real_fields)
    import pytest as _pytest
    with _pytest.raises(AssertionError, match="KHÔNG CÒN CẦN THIẾT"):
        test_gather_cases_fixture_labels_match_real_tool_fields()
```

- [ ] **Step 3: Chạy test mới, xác nhận FAIL (chứng minh lỗ hổng có thật)**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_known_gaps_catches_entry_when_real_field_now_exists -v
```

Expected: **FAIL** — `pytest.raises` không bắt được `AssertionError` nào
(vì hàm test bên trong ÂM THẦM PASS, không raise gì) → báo lỗi dạng
`DID NOT RAISE`. Đây LÀ kết quả đúng ở bước này — chứng minh lỗ hổng có
thật trước khi sửa. Nếu test PASS ngay ở bước này (không phải FAIL), DỪNG
LẠI, báo cáo NEEDS_CONTEXT — có gì đó không khớp giả định.

- [ ] **Step 4: Sửa logic — đảo lại kiểm tra cho mục trong `_KNOWN_GAPS`**

Thay TOÀN BỘ thân hàm `test_gather_cases_fixture_labels_match_real_tool_fields`
(giữ nguyên docstring, chỉ đổi phần code bên dưới) bằng:

```python
def test_gather_cases_fixture_labels_match_real_tool_fields():
    """Đối chiếu fixture với field THẬT tool trả về — chặn lớp lỗi "fixture
    khẳng định khả năng tool không có" (gặp 2 lần: gather-erp-tool-fix,
    sale-order-detail-dates). 2 vi phạm đã biết nằm trong _KNOWN_GAPS —
    nhưng khác bản gốc, mục trong _KNOWN_GAPS VẪN được kiểm field thật:
    nếu field thật ĐÃ CÓ (gap đã sửa), đó là lỗi đòi xoá mục, không phải
    được bỏ qua âm thầm (sửa 2026-08-02: bản gốc chỉ bắt được kịch bản
    "nhãn không còn khớp câu chữ", không bắt được kịch bản "gap đã sửa" —
    continue thoát trước khi kiểm tra field thật)."""
    used = set()
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for tool_name, fixture_text in tool_fixtures.items():
            real_fields = _real_fields_for_tool(tool_name)
            low = fixture_text.casefold()
            for label, field_names in _DATE_STATUS_LABELS.items():
                if label not in low:
                    continue
                key = (topic, tool_name, label)
                ok = bool(set(field_names) & real_fields)
                if key in _KNOWN_GAPS:
                    used.add(key)
                    assert not ok, (
                        f"_KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: case "
                        f"{topic}, tool {tool_name!r}, nhãn {label!r} — "
                        f"field thật đã có "
                        f"({sorted(set(field_names) & real_fields)}), xoá "
                        f"mục này khỏi _KNOWN_GAPS.")
                    continue
                assert ok, (
                    f"case {topic}: fixture của tool {tool_name!r} dùng nhãn "
                    f"{label!r} nhưng tool không có field thật nào trong "
                    f"{field_names} (field thật: {sorted(real_fields)})")
    assert used == _KNOWN_GAPS, (
        f"_KNOWN_GAPS có mục không còn ứng với vi phạm thật (gap đã lấp "
        f"hoặc fixture đã đổi chữ): {sorted(_KNOWN_GAPS - used)} — xoá mục "
        f"đó khỏi _KNOWN_GAPS, đừng để nó nằm lại như cấu hình chết.")
```

- [ ] **Step 5: Chạy lại 2 test, xác nhận cả hai PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_known_gaps_catches_entry_when_real_field_now_exists tests/jobs/test_eval_gather.py::test_gather_cases_fixture_labels_match_real_tool_fields -v
```

Expected: CẢ HAI PASS.
- `test_known_gaps_catches_entry_when_real_field_now_exists`: PASS — giờ
  `pytest.raises` BẮT ĐƯỢC `AssertionError` đúng thông báo "KHÔNG CÒN CẦN
  THIẾT" như mong đợi (chứng minh logic mới hoạt động).
- `test_gather_cases_fixture_labels_match_real_tool_fields`: PASS — với
  code THẬT (`_real_fields_for_tool` không bị monkeypatch), `sales.py`
  CHƯA sửa (Task 2 chưa chạy), nên `ok=False` cho cả 2 mục
  `_KNOWN_GAPS` → `assert not False` → qua, không hồi quy so với trước.

- [ ] **Step 6: Chạy toàn bộ `test_eval_gather.py`, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Expected: TẤT CẢ pass (25 test — 24 cũ + 1 mới).

- [ ] **Step 7: Commit**

```bash
git add backend/tests/jobs/test_eval_gather.py
git commit -m "fix(gather-cases-contract-test): _KNOWN_GAPS phải kiểm field thật ngay cả khi mục đã có ngoại lệ — bản gốc chỉ bắt 1/2 kịch bản cấu hình chết"
```

---

## Task 2: `get_sale_order_detail` đọc thêm `commitment_date`/`effective_date`

**Chỉ thực hiện task này SAU khi Task 1 hoàn tất và review sạch.**

**Files:**
- Modify: `backend/src/erp_query/sales.py:49-69` (`get_sale_order_detail`)
- Modify: `backend/src/erp_query/tools.py:88-90` (docstring tool)
- Test: `backend/tests/erp_query/test_sales.py`
- Test: `backend/tests/erp_query/test_tools.py`

**Interfaces:**
- Consumes: không phụ thuộc Task 1 về mặt code (Task 1 chỉ đụng file test
  khác) — nhưng Task 3 CẦN cả 2 task đã xong để chạy đúng trình tự xác
  minh.
- Produces: `sales.get_sale_order_detail(ref, *, gw=None)` trả về thêm
  `out["data"]["order"]["commitment_date"]`,
  `out["data"]["order"]["effective_date"]`.

- [ ] **Step 1: Đọc đúng vị trí cần sửa**

Mở `backend/src/erp_query/sales.py`, xác nhận `get_sale_order_detail`
(dòng 49-69) khớp CHÍNH XÁC:

```python
def get_sale_order_detail(ref, *, gw=None):
    gw = gw or default_gateway()
    try:
        orders = gw.search_read("sale.order", [["name", "=", ref]],
                                ["id", "name", "partner_id", "amount_total", "state",
                                 "date_order", "delivery_status"], limit=2)
        if not orders:
            return err(f"Không tìm thấy đơn '{ref}'.")
        if len(orders) > 1:
            return err(f"Có nhiều đơn tên '{ref}'.")
        o = orders[0]
        lines = gw.search_read("sale.order.line", [["order_id", "=", o["id"]]],
                               ["id", "product_id", "product_uom_qty", "price_unit", "price_subtotal"],
                               order="id asc", limit=100)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu chi tiết đơn: {e}")
    body = "\n".join(f"  {(l['product_id'] or [0, 'N/A'])[1]} | SL {l['product_uom_qty']:.1f} "
                     f"| {l['price_unit']:,.0f} | {l['price_subtotal']:,.0f}" for l in lines)
    return ok({"order": o, "lines": lines},
              f"Đơn {o['name']} | {(o['partner_id'] or [0, 'N/A'])[1]} "
              f"| Tổng {o['amount_total']:,.0f}\n{body}")
```

Nếu KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT.

- [ ] **Step 2: Viết test thất bại trước (TDD)**

Mở `backend/tests/erp_query/test_sales.py`. Thêm hàm test mới NGAY SAU
`test_get_sale_order_detail_includes_dates` (kết thúc ở dòng 91):

```python
def test_get_sale_order_detail_includes_effective_dates():
    order_rows = [{"id": 7, "name": "S00007", "partner_id": [41, "Azur"],
                   "amount_total": 320000.0, "state": "done",
                   "date_order": "2026-07-18 16:55:50",
                   "delivery_status": "full",
                   "commitment_date": False,
                   "effective_date": "2026-07-20 09:12:00"}]
    line_rows = []

    class TwoCallTransport:
        def __init__(self): self.calls = []
        def call(self, model, method, args, kwargs):
            self.calls.append((model, method, args, kwargs))
            return order_rows if model == "sale.order" else line_rows

    gw = Gateway(TwoCallTransport())
    out = sales.get_sale_order_detail("S00007", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["order"]["effective_date"] == "2026-07-20 09:12:00"
    assert out["data"]["order"]["commitment_date"] is False
    order_call = next(c for c in gw._t.calls if c[0] == "sale.order")
    assert "commitment_date" in order_call[3]["fields"]
    assert "effective_date" in order_call[3]["fields"]
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py::test_get_sale_order_detail_includes_effective_dates -v
```

Expected: FAIL — `KeyError: 'effective_date'` (field chưa được đọc).

- [ ] **Step 4: Sửa `get_sale_order_detail` — thêm 2 field**

Thay đúng dòng `search_read` đầu tiên trong hàm:

```python
        orders = gw.search_read("sale.order", [["name", "=", ref]],
                                ["id", "name", "partner_id", "amount_total", "state",
                                 "date_order", "delivery_status",
                                 "commitment_date", "effective_date"], limit=2)
```

Không sửa gì khác trong hàm (cùng lý do plan trước: model đọc đủ qua JSON
toàn vẹn của `_json()`, không qua prose).

- [ ] **Step 5: Chạy lại test, xác nhận PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py -v
```

Expected: TẤT CẢ pass.

- [ ] **Step 6: Sửa docstring tool trong `tools.py`**

Mở `backend/src/erp_query/tools.py`, xác nhận dòng 88-90 khớp CHÍNH XÁC:

```python
    @tool
    def get_sale_order_detail(ref: str) -> str:
        """Chi tiết đơn bán theo mã (vd S00042): dòng sản phẩm, ngày xác nhận (date_order), trạng thái giao (delivery_status)."""
        return _json(sales.get_sale_order_detail(ref))
```

Thay dòng docstring bằng:

```python
    @tool
    def get_sale_order_detail(ref: str) -> str:
        """Chi tiết đơn bán theo mã (vd S00042): dòng sản phẩm, ngày xác nhận (date_order), trạng thái giao (delivery_status), ngày giao dự kiến (commitment_date), ngày giao thực tế (effective_date)."""
        return _json(sales.get_sale_order_detail(ref))
```

- [ ] **Step 7: Thêm test guard cho docstring mới**

Mở `backend/tests/erp_query/test_tools.py`, xác nhận có sẵn (khoảng dòng
170-174):

```python
def test_get_sale_order_detail_description_mentions_dates():
    tool = next(t for t in build_erp_query_tools()
                if t.name == "get_sale_order_detail")
    assert "ngày xác nhận" in tool.description
    assert "trạng thái giao" in tool.description
```

Thêm hàm test mới NGAY SAU:

```python
def test_get_sale_order_detail_description_mentions_effective_dates():
    tool = next(t for t in build_erp_query_tools()
                if t.name == "get_sale_order_detail")
    assert "ngày giao dự kiến" in tool.description
    assert "ngày giao thực tế" in tool.description
```

- [ ] **Step 8: Chạy test mới, xác nhận PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/test_tools.py::test_get_sale_order_detail_description_mentions_effective_dates -v
```

Expected: PASS.

- [ ] **Step 9: Chạy toàn bộ test đơn vị của `erp_query`, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/ -v
```

Expected: TẤT CẢ pass.

- [ ] **Step 10: Commit**

```bash
git add backend/src/erp_query/sales.py backend/src/erp_query/tools.py \
        backend/tests/erp_query/test_sales.py backend/tests/erp_query/test_tools.py
git commit -m "feat(erp_query): get_sale_order_detail đọc thêm commitment_date/effective_date"
```

---

## Task 3: Xác nhận contract test tự báo lỗi, dọn `_KNOWN_GAPS`, đo Odoo thật, chốt báo cáo

**Chỉ thực hiện task này SAU khi Task 1 và Task 2 hoàn tất, review sạch.**

**Files:**
- Modify: `backend/tests/jobs/test_eval_gather.py:330-341` (`_KNOWN_GAPS`)
- Create: `docs/superpowers/plans/2026-08-02-sale-order-effective-dates-report.md`

**Interfaces:**
- Consumes: kết quả Task 1 (logic contract test đã sửa đúng), Task 2
  (field thật đã có trong `get_sale_order_detail`).
- Produces: `_KNOWN_GAPS` rỗng, báo cáo cuối cùng của plan.

- [ ] **Step 1: Chạy `test_eval_gather.py`, xác nhận NÓ TỰ BÁO LỖI đúng như dự đoán**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_gather_cases_fixture_labels_match_real_tool_fields -v
```

**Kỳ vọng: FAIL**, với 2 dòng thông báo (mỗi mục `_KNOWN_GAPS` một dòng)
dạng:

```
AssertionError: _KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: case sla_giao_hang, tool 'get_sale_order_detail', nhãn 'ngày giao dự kiến' — field thật đã có (['commitment_date']), xoá mục này khỏi _KNOWN_GAPS.
```

(pytest chỉ dừng ở assert đầu tiên gặp phải trong một lần chạy — chạy lại
sau khi xoá dòng đầu để thấy dòng thứ hai, hoặc đọc kỹ thứ tự lặp
`_DATE_STATUS_LABELS`/`GATHER_CASES` để biết mục nào sẽ báo trước.)

Nếu KHÔNG fail (test PASS ngay): DỪNG LẠI, báo cáo BLOCKED — Task 1 hoặc
Task 2 có vấn đề, không tự đoán, ghi lại chi tiết quan sát được.

- [ ] **Step 2: Xoá đúng 2 dòng `_KNOWN_GAPS` mà thông báo lỗi chỉ ra**

Mở `backend/tests/jobs/test_eval_gather.py`, xác nhận `_KNOWN_GAPS`
(dòng 330-341) khớp CHÍNH XÁC:

```python
_KNOWN_GAPS = {
    # (topic, tool, nhãn) — xem docs/superpowers/plans/
    # 2026-08-02-sale-order-detail-dates-report.md (Task 2 Bước 10):
    # get_sale_order_detail không có field "ngày giao dự kiến"/"ngày giao
    # thực tế" thật — chưa tool nào gather_erp gọi được cung cấp field đó
    # CHO MỘT ĐƠN CỤ THỂ (list_late_deliveries có khái niệm ngày giao nhưng
    # chỉ trả phiếu trễ hạn, không lọc theo mã đơn).
    # Quyết định lộ tool/đọc field mới vẫn TREO, chưa làm. Xoá dòng khỏi
    # danh sách khi field đó có thật, KHÔNG xoá để né test.
    ("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến"),
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}
```

Thay bằng (đúng comment mới, `_KNOWN_GAPS` rỗng — vẫn giữ tên biến, kiểu
`set()`, không xoá biến vì code khác còn tham chiếu tới):

```python
_KNOWN_GAPS: set[tuple[str, str, str]] = set()
# Lịch sử: 2 mục ("sla_giao_hang"/"ngày giao dự kiến",
# "chinh_sach_hoan_hang"/"ngày giao thực tế" của get_sale_order_detail)
# từng nằm ở đây (xem docs/superpowers/plans/
# 2026-08-01-gather-erp-tool-selection-fix-report.md và
# 2026-08-02-sale-order-detail-dates-report.md) — đã đóng ở plan
# sale-order-effective-dates (2026-08-02): get_sale_order_detail giờ đọc
# commitment_date/effective_date thật. Nếu contract test lại báo lỗi đòi
# THÊM mục mới trong tương lai, đó là tín hiệu thật — đừng thêm lại 2 mục
# cũ trừ khi field thật lại biến mất.
```

- [ ] **Step 3: Chạy lại, xác nhận PASS với `_KNOWN_GAPS` rỗng**

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Expected: TẤT CẢ pass (25 test).

- [ ] **Step 4: Chẩn đoán Odoo thật — tra động một đơn có `effective_date` thật**

Tạo file tạm `backend/_diag_effective_date.py` (KHÔNG commit, xoá sau khi
xong):

```python
from dotenv import load_dotenv
load_dotenv("../.env")

from src.erp_query.gateway import default_gateway
from src.erp_query import sales

gw = default_gateway()
rows = gw.search_read("sale.order", [["effective_date", "!=", False]],
                      ["name", "effective_date"], limit=1)
if not rows:
    print("BLOCKED: không còn đơn nào có effective_date thật trong Odoo.")
else:
    ref = rows[0]["name"]
    expected = rows[0]["effective_date"]
    out = sales.get_sale_order_detail(ref, gw=gw)
    actual = out["data"]["order"]["effective_date"]
    print(f"Đơn: {ref}")
    print(f"effective_date từ search_read độc lập: {expected!r}")
    print(f"effective_date từ get_sale_order_detail: {actual!r}")
    print("KHỚP" if actual == expected else "KHÔNG KHỚP")
```

Chạy:

```bash
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe _diag_effective_date.py
```

**Kỳ vọng**: in ra "KHỚP" — `get_sale_order_detail` trả đúng giá trị
`effective_date` thật, khớp với `search_read` độc lập tra cùng lúc.

Nếu in ra "BLOCKED..." (không còn đơn nào có `effective_date` — dữ liệu
demo trôi tiếp): DỪNG LẠI, ghi lại, báo cáo BLOCKED — không tự bịa dữ
liệu, không tự sửa gì thêm.

Nếu in ra "KHÔNG KHỚP": DỪNG LẠI, báo cáo BLOCKED — có vấn đề trong code,
cần điều tra trước khi tiếp tục.

Ghi lại đơn thật đã dùng + giá trị + kết quả vào report (Step 6). Xoá file
`_diag_effective_date.py` sau khi xong — KHÔNG commit.

- [ ] **Step 5: Chạy `--set gather` THẬT — xác nhận không hồi quy**

```bash
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

**Kỳ vọng**: vẫn `tool_recall=1.0, fact_coverage=1.0, "fails": []` — 4/4
case PASS như trước (fixture `GATHER_CASES` không đổi, stub không quan
tâm khả năng thật của tool nên không có lý do gì đổi kết quả). Nếu KHÁC,
ghi lại chi tiết, báo cáo DONE_WITH_CONCERNS — không tự đoán nguyên nhân.

- [ ] **Step 6: Chạy full suite 2 chế độ**

```bash
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
.venv/Scripts/python.exe -m pytest -m integration -q
```

Sau mỗi lượt, nếu 2 file fixture nhị phân
(`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`) bị đổi, khôi
phục: `git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`.

- [ ] **Step 7: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-08-02-sale-order-effective-dates-report.md`:

```markdown
# Báo cáo — thêm ngày giao thật vào get_sale_order_detail

Plan: `docs/superpowers/plans/2026-08-02-sale-order-effective-dates.md`
Spec: `docs/superpowers/specs/2026-08-02-sale-order-effective-dates-design.md`

## Task 1 — sửa lỗ hổng contract test

Xác nhận lỗ hổng có thật (Step 3): `<PASS/FAIL đúng như brief>`.
Sau khi sửa (Step 5): `<PASS/FAIL đúng như brief>`.

## Task 3 Bước 1 — contract test tự báo lỗi

Thông báo lỗi nguyên văn:

```
<dán nguyên văn>
```

## Task 3 Bước 4 — chẩn đoán Odoo thật

- Đơn dùng để đo: `<mã đơn thật, tra động lúc chạy>`
- `effective_date` từ search_read độc lập: `<giá trị>`
- `effective_date` từ get_sale_order_detail: `<giá trị>`
- Kết quả: `<KHỚP | KHÔNG KHỚP | BLOCKED>`

## Task 3 Bước 5 — `--set gather`

- `tool_recall`: `<số>`, `fact_coverage`: `<số>`, `fails`: `<danh sách>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`

## Xác minh test

- Unit-only: `<N passed>` (TRƯỚC: 1098)
- Integration: `<N passed>` (TRƯỚC: 27)

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec, từng điều một dòng đạt/không đạt kèm
bằng chứng.
```

Thay mọi `<...>` bằng nội dung thật.

- [ ] **Step 8: Commit**

```bash
git add backend/tests/jobs/test_eval_gather.py \
        docs/superpowers/plans/2026-08-02-sale-order-effective-dates-report.md
git commit -m "test(gather): dọn _KNOWN_GAPS — get_sale_order_detail giờ có ngày giao thật, đo Odoo thật xác nhận"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| "Sửa trước: lỗ hổng thật trong chính contract test" | 1 |
| Kiến trúc mục 1-4 (thêm field, docstring, test) | 2 |
| "Hệ quả lên contract test" (tự báo lỗi, dọn `_KNOWN_GAPS`) | 3 (Step 1-3) |
| "Xác minh qua Odoo thật — không dùng S00042" | 3 (Step 4) |
| Testing (`--set gather` không hồi quy, full suite) | 3 (Step 5-6) |
| "Xong nghĩa là" điều 1-7 | 3 (Step 7, đối chiếu trực tiếp) |
| Phạm vi (không lộ tool mới, không sửa prompt/cases.py) | Global Constraints, không task nào đụng các file đó |

**Placeholder scan:** không có `TBD`/`TODO` — mọi `<...>` nằm trong
template report cho implementer điền số liệu thật.

**Type/interface consistency:** `_real_fields_for_tool(tool_name: str) ->
set[str]` không đổi chữ ký qua cả 3 task. `_KNOWN_GAPS` giữ nguyên kiểu
`set[tuple[str, str, str]]` xuyên suốt (chỉ đổi nội dung: 2 phần tử →
rỗng). `sales.get_sale_order_detail(ref, *, gw=None)` giữ nguyên chữ ký.

**Điểm khác biệt so với các plan trước:** Task 1 là một plan-trong-plan
nhỏ — sửa MỘT lỗi thật vừa phát hiện trong artifact của plan TRƯỚC ngay
trước khi dùng artifact đó, thay vì mở plan riêng — vì lỗi này trực tiếp
làm Task 3 của CHÍNH plan này không thể xác minh đúng như spec đã duyệt
nếu không sửa trước. Task 1 tự có chu kỳ TDD đầy đủ (test chứng minh lỗ
hổng → sửa → test chứng minh đã sửa), độc lập, review được riêng.
