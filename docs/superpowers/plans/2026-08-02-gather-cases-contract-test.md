# Contract test cho GATHER_CASES Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm một test đối chiếu fixture của `GATHER_CASES` với field THẬT
mà tool được gán có thể trả về — chặn lớp lỗi "fixture khẳng định khả năng
tool không có thật" đã tái diễn 2 lần liên tiếp (`gather-erp-tool-fix`,
`sale-order-detail-dates`).

**Architecture:** Một transport ghi nhận DÙNG CHUNG gọi thẳng hàm business-
layer thật qua `Gateway`, ghi lại field `search_read` thật sự yêu cầu. Một
từ điển nhỏ ánh xạ nhãn tiếng Việt đã từng gây lỗi → field thật tương ứng.
Test quét mọi fixture, cảnh báo khi nhãn xuất hiện nhưng tool không có field
đó thật — trừ 2 vi phạm đã biết, nằm trong danh sách ngoại lệ tường minh.

**Tech Stack:** Python 3.12, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-08-02-gather-cases-contract-test-design.md`

## Global Constraints

- **Không sửa `backend/evals/cases.py` hay bất kỳ code sản xuất nào** — chỉ
  thêm code vào `backend/tests/jobs/test_eval_gather.py`.
- **Chỉ áp dụng cho `GATHER_CASES`** — không đụng `MULTI_SOURCE_CASES` hay
  bộ case khác.
- Chạy Python bằng `backend/.venv/Scripts/python.exe`.
- "Full suite" = `pytest -m "not integration and not live"` (unit-only) +
  `pytest -m integration`.

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Sửa | `backend/tests/jobs/test_eval_gather.py` | Thêm hạ tầng đối chiếu field thật + 1 test mới |

---

## Task 1: Contract test đối chiếu fixture với field thật của tool

**Files:**
- Modify: `backend/tests/jobs/test_eval_gather.py` (thêm vào cuối file, sau
  dòng 252)

**Interfaces:**
- Consumes: `evals.cases.GATHER_CASES` (đã có sẵn — shape tuple 5 phần tử
  `(topic, question, required_tools, required_facts, tool_fixtures)`),
  `src.erp_query.gateway.Gateway`, `src.erp_query.sales`,
  `src.erp_query.accounting` (đã có sẵn).
- Produces: không có consumer nào khác trong plan này — đây là task duy
  nhất, tự đóng gói hoàn chỉnh.

- [ ] **Step 1: Đọc đúng vị trí chèn code**

Mở `backend/tests/jobs/test_eval_gather.py`, xác nhận hàm CUỐI CÙNG của
file (dòng 246-252, đúng đoạn kết thúc file) khớp CHÍNH XÁC:

```python
def test_set_choices_includes_gather():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "gather"])
    assert args.set == "gather"
```

Nếu KHÔNG khớp (file đã đổi từ lúc viết plan), DỪNG LẠI, báo cáo
NEEDS_CONTEXT kèm nội dung thật đang có.

- [ ] **Step 2: Thêm toàn bộ hạ tầng + test vào cuối file**

Nối vào CUỐI file (sau dòng 252, cách 2 dòng trống với nội dung hiện có):

```python
# ── Contract test: fixture GATHER_CASES đối chiếu field THẬT của tool ──────
# Lớp lỗi "fixture khẳng định khả năng tool không có thật" đã tái diễn 2
# lần liên tiếp (gather-erp-tool-fix 2026-08-01, sale-order-detail-dates
# 2026-08-02) — 5 test tự-nhất-quán phía trên chỉ kiểm fixture KHÔNG tự
# mâu thuẫn, không kiểm fixture có khớp thực tế tool hay không. Xem
# docs/superpowers/specs/2026-08-02-gather-cases-contract-test-design.md.

_REPRESENTATIVE_ROWS = {
    "sale.order": {"id": 1, "name": "S00001", "partner_id": [1, "Khách mẫu"],
                   "amount_total": 100.0, "state": "sale",
                   "date_order": "2026-01-01 00:00:00",
                   "delivery_status": "pending"},
    "sale.order.line": {"id": 1, "product_id": [1, "Sản phẩm mẫu"],
                        "product_uom_qty": 1.0, "price_unit": 100.0,
                        "price_subtotal": 100.0},
    "account.move": {"id": 1, "name": "INV/0001", "partner_id": [1, "Khách mẫu"],
                     "invoice_date": "2026-01-01", "invoice_date_due": "2026-01-31",
                     "amount_total": 100.0, "amount_residual": 100.0,
                     "payment_state": "not_paid"},
    "product.product": {"id": 1, "name": "Sản phẩm mẫu", "list_price": 100.0},
}


class _RecordingTransport:
    """Transport giả DÙNG CHUNG cho mọi tool — chỉ ghi lại (model, fields)
    của mỗi lệnh gọi rồi trả về dòng mẫu tương ứng, đủ để hàm business-layer
    không bị chặn giữa chừng bởi guard 'not found'."""

    def __init__(self):
        self.calls = []  # list[tuple[str, list[str] | None]]

    def call(self, model, method, args, kwargs):
        self.calls.append((model, kwargs.get("fields")))
        row = _REPRESENTATIVE_ROWS.get(model, {"id": 1})
        return [row]


def _real_fields_for_tool(tool_name: str) -> set[str]:
    """Gọi ĐÚNG hàm business-layer thật (không qua @tool wrapper) với
    transport ghi nhận, hợp tất cả field đã ghi được qua mọi lệnh gọi
    search_read trong quá trình thực thi."""
    from src.erp_query.gateway import Gateway
    from src.erp_query import sales, accounting

    gw = Gateway(_RecordingTransport())
    if tool_name == "get_sale_order_detail":
        sales.get_sale_order_detail("S00001", gw=gw)
    elif tool_name == "get_overdue_invoices":
        accounting.get_overdue_invoices(gw=gw)
    elif tool_name == "get_product_price":
        sales.get_product_price(1, gw=gw)
    elif tool_name in ("find_customer", "find_product"):
        # resolve_entity() dùng gw.name_search(), KHÔNG có tham số "fields"
        # — tool loại này KHÔNG THỂ trả field ngày/trạng thái nào, tập rỗng
        # là đúng ngữ nghĩa, không phải giới hạn tạm thời.
        return set()
    else:
        raise KeyError(
            f"_real_fields_for_tool: chưa biết cách gọi tool {tool_name!r} "
            f"— thêm nhánh xử lý trước khi dùng tool này trong GATHER_CASES")
    return {f for _model, fields in gw._t.calls if fields for f in fields}


_DATE_STATUS_LABELS = {
    "ngày xác nhận": ("date_order",),
    "ngày giao dự kiến": ("commitment_date", "effective_date"),
    "ngày giao thực tế": ("effective_date", "date_done"),
    "trạng thái giao": ("delivery_status",),
}

_KNOWN_GAPS = {
    # (topic, tool, nhãn) — xem docs/superpowers/plans/
    # 2026-08-02-sale-order-detail-dates-report.md (Task 2 Bước 10):
    # get_sale_order_detail không có field "ngày giao dự kiến"/"ngày giao
    # thực tế" thật — chưa tool nào gather_erp gọi được cung cấp field đó.
    # Quyết định lộ tool/đọc field mới vẫn TREO, chưa làm. Xoá dòng khỏi
    # danh sách khi field đó có thật, KHÔNG xoá để né test.
    ("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến"),
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}


def test_gather_cases_fixture_labels_match_real_tool_fields():
    """Đối chiếu fixture với field THẬT tool trả về — chặn lớp lỗi "fixture
    khẳng định khả năng tool không có" (gặp 2 lần: gather-erp-tool-fix,
    sale-order-detail-dates). 2 vi phạm đã biết nằm trong _KNOWN_GAPS,
    không bị chặn ở đây — xem comment tại đó."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for tool_name, fixture_text in tool_fixtures.items():
            real_fields = _real_fields_for_tool(tool_name)
            low = fixture_text.casefold()
            for label, field_names in _DATE_STATUS_LABELS.items():
                if label not in low:
                    continue
                if (topic, tool_name, label) in _KNOWN_GAPS:
                    continue
                assert set(field_names) & real_fields, (
                    f"case {topic}: fixture của tool {tool_name!r} dùng nhãn "
                    f"{label!r} nhưng tool không có field thật nào trong "
                    f"{field_names} (field thật: {sorted(real_fields)})")
```

- [ ] **Step 3: Chạy test mới, xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_gather_cases_fixture_labels_match_real_tool_fields -v
```

Expected: PASS. 2 vi phạm đã biết (`sla_giao_hang`/`ngày giao dự kiến`,
`chinh_sach_hoan_hang`/`ngày giao thực tế`) được `_KNOWN_GAPS` che, không
gây fail. Các case/nhãn còn lại (`ngày xác nhận` của cả 2 case đó) khớp
field thật (`date_order`), nên qua bình thường không cần ngoại lệ.

- [ ] **Step 4: Xác minh test THẬT SỰ bắt được lỗi — xoá tạm 1 dòng `_KNOWN_GAPS`**

Đây là bước xác minh bắt buộc theo spec (mục Testing) — chứng minh test có
tác dụng thật, không phải PASS giả vì logic sai đâu đó.

Sửa tạm `_KNOWN_GAPS` (XOÁ đúng 1 dòng, dòng còn lại giữ nguyên):

```python
_KNOWN_GAPS = {
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}
```

Chạy lại:

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_gather_cases_fixture_labels_match_real_tool_fields -v
```

**Kỳ vọng: FAIL**, thông báo lỗi chứa đúng
`case sla_giao_hang: fixture của tool 'get_sale_order_detail' dùng nhãn
'ngày giao dự kiến' nhưng tool không có field thật nào trong
('commitment_date', 'effective_date')`.

Nếu FAIL đúng như trên: xác nhận test có tác dụng thật, ghi lại thông báo
lỗi đầy đủ vào báo cáo (Step 6). Nếu KHÔNG fail, hoặc fail với thông báo
khác: DỪNG LẠI, báo cáo BLOCKED — logic đối chiếu có vấn đề, không tự ý
đoán sửa.

- [ ] **Step 5: Khôi phục `_KNOWN_GAPS` về đầy đủ 2 dòng**

Sửa lại `_KNOWN_GAPS` về ĐÚNG bản gốc ở Step 2 (2 dòng, cả
`sla_giao_hang` lẫn `chinh_sach_hoan_hang`):

```python
_KNOWN_GAPS = {
    ("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến"),
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}
```

Chạy lại xác nhận PASS:

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py::test_gather_cases_fixture_labels_match_real_tool_fields -v
```

Expected: PASS (giống Step 3).

- [ ] **Step 6: Chạy toàn bộ `test_eval_gather.py`, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Expected: TẤT CẢ pass, bao gồm 5 test tự-nhất-quán cũ và test mới.

- [ ] **Step 7: Chạy full suite 2 chế độ, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
.venv/Scripts/python.exe -m pytest -m integration -q
```

Expected: xanh cả 2 chế độ, không giảm số lượng test so với TRƯỚC (chỉ
tăng đúng 1 test mới). Nếu 2 file fixture nhị phân
(`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`) bị đổi, khôi
phục: `git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`.

- [ ] **Step 8: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-08-02-gather-cases-contract-test-report.md`:

```markdown
# Báo cáo — contract test cho GATHER_CASES

Plan: `docs/superpowers/plans/2026-08-02-gather-cases-contract-test.md`
Spec: `docs/superpowers/specs/2026-08-02-gather-cases-contract-test-design.md`

## Xác minh test có tác dụng thật (Step 4)

Xoá tạm dòng `("sla_giao_hang", "get_sale_order_detail", "ngày giao dự
kiến")` khỏi `_KNOWN_GAPS`, chạy lại — kết quả:

<dán nguyên văn thông báo lỗi pytest ở đây>

Kết luận: `<khớp đúng kỳ vọng — test bắt được lỗi thật | không khớp, nêu
chi tiết>`. Đã khôi phục `_KNOWN_GAPS` về đầy đủ 2 dòng trước khi commit.

## Xác minh test

- `test_eval_gather.py` riêng: `<N passed>`
- Unit-only: `<N passed>` (TRƯỚC: 1097)
- Integration: `<N passed>` (TRƯỚC: 27)

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec:

1. `test_gather_cases_fixture_labels_match_real_tool_fields` tồn tại, PASS
   trên `GATHER_CASES` hiện tại: `<ĐẠT>`
2. Xoá 1 dòng `_KNOWN_GAPS` khiến test FAIL đúng kỳ vọng (Step 4): `<ĐẠT>`
3. Không sửa `cases.py` hay code sản xuất nào: `<ĐẠT, xác nhận qua git diff
   --stat>`
4. Toàn bộ test 2 chế độ xanh: `<ĐẠT>`
5. `_KNOWN_GAPS` có đúng 2 mục, có comment trỏ report: `<ĐẠT>`
```

Thay mọi `<...>` bằng nội dung thật.

- [ ] **Step 9: Commit**

```bash
git add backend/tests/jobs/test_eval_gather.py \
        docs/superpowers/plans/2026-08-02-gather-cases-contract-test-report.md
git commit -m "test(gather): contract test đối chiếu fixture GATHER_CASES với field thật của tool"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| Kiến trúc mục 1-6 (`_REPRESENTATIVE_ROWS`, `_RecordingTransport`, `_real_fields_for_tool`, `_DATE_STATUS_LABELS`, `_KNOWN_GAPS`, test) | 1 (Step 2) |
| Testing mục 1 (chạy trên GATHER_CASES hiện tại, PASS) | 1 (Step 3) |
| Testing mục 2 (kiểm tra ngược — xoá 1 dòng, xác nhận FAIL, khôi phục) | 1 (Step 4-5) |
| "Xong nghĩa là" điều 1-5 | 1 (Step 8, đối chiếu trực tiếp) |
| Phạm vi (không sửa `cases.py`/code sản xuất) | Global Constraints, không có step nào sửa file đó |

**Placeholder scan:** không có `TBD`/`TODO` — mọi `<...>` nằm trong template
report cho implementer điền số liệu thật, không phải placeholder chưa
quyết định trong chính plan.

**Type/interface consistency:** `_real_fields_for_tool(tool_name: str) ->
set[str]` dùng nhất quán trong test function; `_KNOWN_GAPS` là tập hợp
tuple 3 phần tử `(topic, tool, label)` xuyên suốt Step 2, 4, 5; shape tuple
5 phần tử của `GATHER_CASES` khớp đúng cách unpack đã dùng trong 5 test cũ
của file (đã đọc trực tiếp file thật để xác nhận, không suy đoán).

**Điểm khác biệt so với các plan trước trong dự án này:** chỉ 1 task duy
nhất (không tách nhiều task) — spec đủ nhỏ, các thành phần (dòng mẫu,
transport, hàm ánh xạ, từ điển nhãn, ngoại lệ, test) chỉ có ý nghĩa khi
đứng cùng nhau, tách nhỏ sẽ tạo review-gate giả không phản ánh ranh giới
thật của công việc.
