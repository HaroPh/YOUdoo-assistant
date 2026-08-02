# Contract test cho GATHER_CASES — Design

## Bối cảnh

Lớp lỗi "fixture khẳng định khả năng tool không có thật" đã gặp 2 lần liên
tiếp, cả hai lần trong `GATHER_CASES` (`backend/evals/cases.py`):

1. Plan `gather-erp-tool-selection-fix` (2026-08-01): fixture gán field
   ngày cho `get_sale_order_detail`, một khả năng tool đó không có thật lúc
   đó — khiến bộ đo `gather` báo 4/4 PASS trong khi bug thật vẫn còn.
2. Plan `sale-order-detail-dates` (2026-08-02): sau khi sửa
   `get_sale_order_detail` để có `date_order`/`delivery_status`, 2 fixture
   VẪN đòi hỏi "ngày giao dự kiến"/"ngày giao thực tế" — hai khái niệm khác
   `date_order` (ngày xác nhận đơn) — mà không tool nào `gather_erp` gọi
   được thật sự cung cấp. Final review (Opus) phát hiện, không phải task
   review nào bắt được — vì không có cơ chế nào đối chiếu fixture với khả
   năng THẬT của tool, chỉ có test đối chiếu fixture với CHÍNH NÓ (tự-nhất-
   quán, không phải đúng-với-thực-tế).

5 test tự-nhất-quán hiện có trong `backend/tests/jobs/test_eval_gather.py`
(`test_gather_cases_shape_and_topics_exist`,
`test_gather_cases_required_tools_have_fixtures`,
`test_gather_cases_required_facts_exist_in_fixtures`,
`test_gather_cases_facts_not_leaked_by_the_question`,
`test_gather_cases_required_tools_are_real_erp_tool_names`) đều kiểm case
KHÔNG tự mâu thuẫn — không có test nào kiểm fixture có khớp field THẬT của
tool hay không. Đây là khoảng trống cụ thể plan này lấp.

## Phạm vi

- Chỉ `GATHER_CASES` — không đụng `MULTI_SOURCE_CASES` hay bộ case khác.
- Chỉ áp dụng cho 5 tool hiện có trong `GATHER_CASES`:
  `get_sale_order_detail`, `get_overdue_invoices`, `get_product_price`
  (dùng `search_read`), `find_customer`, `find_product` (dùng
  `name_search`, không có khái niệm field).
- Từ điển nhãn (`_DATE_STATUS_LABELS`) CHỈ chứa nhãn tiếng Việt đã thực sự
  xuất hiện trong fixture hiện tại + 1 nhãn phòng ngừa liên quan trực tiếp
  (`delivery_status`) — không cố tổng quát hoá thành hệ thống kiểm mọi loại
  fact.
- Không sửa `backend/evals/cases.py` hay bất kỳ code sản xuất nào — thuần
  hạ tầng test mới trong `backend/tests/jobs/test_eval_gather.py`.
- 2 vi phạm đã biết (xem Bối cảnh, mục 2) được ghi vào danh sách ngoại lệ có
  theo dõi — KHÔNG chặn plan này, KHÔNG tự ý sửa `GATHER_CASES`/tool ngay
  (quyết định đó vẫn treo, chờ phase riêng).

## Kiến trúc

### 1. `_REPRESENTATIVE_ROWS: dict[str, dict]`

Một dòng dữ liệu mẫu, đầy đủ kiểu dữ liệu, cho mỗi Odoo model mà các tool
trong phạm vi truy vấn qua `search_read`:

```python
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
```

Mục đích DUY NHẤT: đủ dữ liệu, đủ kiểu (số thật cho field số, tuple
`[id, name]` cho field quan hệ) để hàm business-layer KHÔNG bị chặn giữa
chừng bởi guard "not found" hay lỗi định dạng trong bước xử lý SAU lệnh gọi
— việc ghi nhận `fields` đã yêu cầu xảy ra TRƯỚC đó, tại thời điểm gọi, nên
không phụ thuộc bước xử lý sau có thành công hay không. Đây là lý do
`get_sale_order_detail` (2 lệnh gọi tuần tự: `sale.order` rồi
`sale.order.line`) cần dòng mẫu `sale.order` không rỗng — để nó đi tiếp tới
lệnh gọi thứ hai thay vì dừng ở `if not orders: return err(...)`.

### 2. `_RecordingTransport`

Một transport giả DÙNG CHUNG cho mọi tool (không viết riêng theo từng tool
như test cũ):

```python
class _RecordingTransport:
    def __init__(self):
        self.calls = []  # list[tuple[model, fields|None]]

    def call(self, model, method, args, kwargs):
        self.calls.append((model, kwargs.get("fields")))
        row = _REPRESENTATIVE_ROWS.get(model, {"id": 1})
        return [row]
```

### 3. `_real_fields_for_tool(tool_name: str) -> set[str]`

Bảng ánh xạ tường minh, nhỏ — gọi ĐÚNG hàm business-layer thật (không phải
qua `@tool` wrapper) với transport ghi nhận ở trên, hợp tất cả field đã ghi
được qua mọi lệnh gọi trong quá trình thực thi:

```python
def _real_fields_for_tool(tool_name: str) -> set[str]:
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
            f"_real_fields_for_tool: chưa biết cách gọi tool {tool_name!r} — "
            f"thêm nhánh xử lý trước khi dùng tool này trong GATHER_CASES")
    return {f for _model, fields in gw._t.calls if fields for f in fields}
```

Ghi chú thiết kế: hợp field của MỌI lệnh gọi trong 1 tool (vd
`get_sale_order_detail` gộp field của cả `sale.order` lẫn
`sale.order.line`) thay vì tách theo từng model riêng. Với 5 tool hiện có,
không có field nào trùng tên mang nghĩa khác nhau giữa 2 model của cùng 1
tool, nên gộp là an toàn và đơn giản hơn. Nếu sau này một tool nối nhiều
model có field trùng tên khác nghĩa, cần tách lại theo model — chưa cần
làm bây giờ (YAGNI).

### 4. `_DATE_STATUS_LABELS: dict[str, tuple[str, ...]]`

```python
_DATE_STATUS_LABELS = {
    "ngày xác nhận": ("date_order",),
    "ngày giao dự kiến": ("commitment_date", "effective_date"),
    "ngày giao thực tế": ("effective_date", "date_done"),
    "trạng thái giao": ("delivery_status",),
}
```

Nhãn → tuple field thật (bất kỳ field nào trong tuple xuất hiện là ĐẠT —
dùng tuple vì đôi khi nhiều tên field khác nhau có thể thoả cùng một khái
niệm, tuỳ tool/model). 3 nhãn đầu đã dùng thật trong fixture hiện tại; nhãn
thứ 4 (`delivery_status`) chưa case nào dùng — thêm sẵn để chặn tái diễn ở
đúng field vừa sửa tại Task 1 của plan trước.

### 5. `_KNOWN_GAPS`

```python
_KNOWN_GAPS = {
    # (topic, tool, nhãn) — xem docs/superpowers/plans/
    # 2026-08-02-sale-order-detail-dates-report.md (Task 2 Bước 10):
    # get_sale_order_detail không có field "ngày giao dự kiến"/"ngày giao
    # thực tế" thật — chưa tool nào gather_erp gọi được cung cấp field đó.
    # Quyết định lộ tool/đọc field mới vẫn TREO, chưa làm. Xoá 2 dòng này
    # khỏi danh sách khi field đó có thật, KHÔNG xoá để né test.
    ("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến"),
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}
```

### 6. Test

```python
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

## Testing

Đây TỰ NÓ là một test — không cần "test cho test". Xác minh đúng qua 2
cách:

1. **Chạy trên `GATHER_CASES` hiện tại**: phải PASS (2 vi phạm đã biết nằm
   trong `_KNOWN_GAPS`, các case còn lại không dùng nhãn nào cần kiểm).
2. **Kiểm tra ngược (thủ công, ghi vào report, không phải test tự động)**:
   tạm thời xoá 1 dòng khỏi `_KNOWN_GAPS`, chạy lại, xác nhận test FAIL
   đúng thông báo mong đợi — chứng minh test THẬT SỰ bắt được lỗi đã biết,
   không phải bắt được false positive nào khác. Khôi phục `_KNOWN_GAPS` sau
   khi xác nhận, không commit trạng thái đã xoá.

## Xong nghĩa là

1. `test_gather_cases_fixture_labels_match_real_tool_fields` tồn tại trong
   `backend/tests/jobs/test_eval_gather.py`, PASS trên `GATHER_CASES` hiện
   tại.
2. Đã xác nhận (thủ công, ghi vào report) rằng xoá 1 dòng khỏi `_KNOWN_GAPS`
   khiến test FAIL đúng như mong đợi — chứng minh test có tác dụng thật.
3. Không sửa `backend/evals/cases.py` hay bất kỳ code sản xuất nào.
4. Toàn bộ test 2 chế độ (unit-only, integration) xanh.
5. `_KNOWN_GAPS` có đúng 2 mục, mỗi mục có comment trỏ tới report đã ghi
   nhận lỗ hổng.
