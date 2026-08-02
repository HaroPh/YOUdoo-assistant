# Thêm ngày giao thật vào `get_sale_order_detail` — Design

## Bối cảnh

Plan `sale-order-detail-dates` (2026-08-02) sửa `get_sale_order_detail` để
đọc `date_order`/`delivery_status`, nhưng để lại 2 lỗ hổng đã ghi nhận
trong `_KNOWN_GAPS` của `backend/tests/jobs/test_eval_gather.py` (contract
test vừa merge): `sla_giao_hang` cần "ngày giao dự kiến", `chinh_sach_hoan_hang`
cần "ngày giao thực tế" — cả hai đều KHÔNG map tới `date_order` (chỉ là
ngày xác nhận đơn).

Kiểm tra trực tiếp Odoo thật (`sale.order`, 10 đơn gần nhất + S00042) xác
nhận:

- **`effective_date`** — trường THẬT, CÓ dữ liệu (6/10 đơn gần nhất có giá
  trị thật, vd `2026-07-25 06:18:23`). Đây chính là "ngày giao thực tế" —
  Odoo tự tính khi phiếu giao đầu tiên hoàn tất, nằm ngay trên `sale.order`,
  không cần tra thêm `stock.picking`.
- **`commitment_date`** — trường THẬT tồn tại nhưng **KHÔNG có dữ liệu nào**
  trong toàn bộ 10 đơn gần nhất, kể cả S00042 (`False` toàn bộ). Đây là
  "ngày giao dự kiến" — có khả năng demo Odoo chưa từng dùng field này.
- **S00042 cụ thể đang ở trạng thái `draft`, chưa từng giao** — `effective_date`
  của chính nó cũng `False`. Nghĩa là dù sửa code đúng, case
  `chinh_sach_hoan_hang` (câu hỏi hard-code "Đơn S00042") vẫn KHÔNG thể đo
  PASS thật qua Odoo thật cho ĐÚNG đơn đó — không phải lỗi code, là dữ
  liệu demo trôi (cùng lớp phát hiện như plan trước).

Có một hàm nội bộ `find_done_deliveries_for_order(order_ref, *, gw=None)`
(`backend/src/erp_query/inventory.py:143-171`, dùng bởi
`returns_write.py`'s `return_order` coordinator) tra đúng theo mã đơn, đọc
`stock.picking.date_done` — cũng cho "ngày giao thực tế" nhưng qua đường
khác (bảng phiếu giao, không phải `sale.order` trực tiếp). Xét cả 2
hướng (thêm field vs lộ tool này thành tool mới) — xem Quyết định phạm vi.

## Quyết định phạm vi

**Chỉ thêm field vào `get_sale_order_detail` — KHÔNG lộ
`find_done_deliveries_for_order` thành tool mới cho `gather_erp`.**

Lý do: `effective_date` đã cho cùng thông tin ("ngày giao thực tế") đơn
giản hơn — không cần lệnh gọi thứ hai, không cần tra `stock.picking`. Lộ
thêm một tool mới sẽ lại cần một quy tắc trong `GATHER_ERP_PROMPT` để dẫn
dắt khi nào dùng tool nào — đúng cơ chế đã gây hồi quy 2 lần trong plan
trước (`gather-erp-tool-selection-fix`: quy tắc dẫn dắt → hồi quy case
không liên quan; đã bỏ hẳn quy tắc đó trong `sale-order-detail-dates`).
Không lặp lại rủi ro đã học được.

## Kiến trúc

1. `backend/src/erp_query/sales.py::get_sale_order_detail` — thêm
   `"commitment_date"`, `"effective_date"` vào danh sách field đọc từ
   `sale.order` (dòng 53-54 hiện tại, nối tiếp `date_order`,
   `delivery_status`). Không sửa `body`/prose — model đọc đủ qua JSON toàn
   vẹn của `_json()` (đã xác nhận ở plan trước, `list_sale_orders` cũng
   không đưa các field ngày vào prose).

2. `backend/src/erp_query/tools.py` — cập nhật docstring tool
   `get_sale_order_detail`, thêm "ngày giao dự kiến (commitment_date),
   ngày giao thực tế (effective_date)".

3. `backend/tests/erp_query/test_sales.py` — test mới xác nhận 2 field
   mới đọc được, theo đúng mẫu `test_get_sale_order_detail_includes_dates`
   đã có (TwoCallTransport, gateway giả).

4. `backend/tests/erp_query/test_tools.py` — cập nhật/thêm assertion cho
   docstring mới (theo mẫu `test_get_sale_order_detail_description_mentions_dates`
   đã có).

## Sửa trước: lỗ hổng thật trong chính contract test vừa merge

**Đính chính (2026-08-02, phát hiện khi viết plan này):** đọc lại kỹ code
đã merge (`backend/tests/jobs/test_eval_gather.py`,
`test_gather_cases_fixture_labels_match_real_tool_fields`) cho thấy phần
"Hệ quả tự nhiên" ở bản spec gốc là SAI. Logic thật:

```python
if (topic, tool_name, label) in _KNOWN_GAPS:
    used.add((topic, tool_name, label))
    continue          # ← thoát NGAY, KHÔNG bao giờ chạy assert bên dưới
assert set(field_names) & real_fields, (...)
```

`continue` chặn TRƯỚC khi kiểm tra field thật — nghĩa là một khi mục nằm
trong `_KNOWN_GAPS`, test KHÔNG BAO GIỜ biết field thật đã có hay chưa.
Cơ chế `assert used == _KNOWN_GAPS` (finding Important #1, final review
của chính plan đó) chỉ bắt được MỘT trong HAI kịch bản "cấu hình chết" mà
nó tự nhận đã bắt cả hai:

- Kịch bản "fixture đổi chữ, nhãn không còn khớp" → BẮT ĐÚNG (`used` thiếu
  mục đó).
- Kịch bản "gap đã được sửa, field thật đã có" → **KHÔNG bắt được** —
  `continue` chặn trước khi biết field đã có hay chưa.

Đây CHÍNH LÀ kịch bản plan này sẽ tạo ra: sau khi thêm
`commitment_date`/`effective_date`, cả 2 dòng `_KNOWN_GAPS` sẽ ÂM THẦM
TIẾP TỤC PASS, không tự báo lỗi như bản spec gốc khẳng định.

**Sửa đúng** (Task đầu tiên của plan, TRƯỚC khi thêm field) — đảo logic:
nếu mục nằm trong `_KNOWN_GAPS` mà field thật GIỜ ĐÃ CÓ, đó chính là lỗi
đòi xoá mục, không phải im lặng bỏ qua:

```python
key = (topic, tool_name, label)
ok = bool(set(field_names) & real_fields)
if key in _KNOWN_GAPS:
    used.add(key)
    assert not ok, (
        f"_KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: case {topic}, "
        f"tool {tool_name!r}, nhãn {label!r} — field thật đã có "
        f"({sorted(set(field_names) & real_fields)}), xoá mục "
        f"này khỏi _KNOWN_GAPS.")
    continue
assert ok, (
    f"case {topic}: fixture của tool {tool_name!r} dùng nhãn "
    f"{label!r} nhưng tool không có field thật nào trong "
    f"{field_names} (field thật: {sorted(real_fields)})")
```

Đã trace tay qua trạng thái HIỆN TẠI (trước khi thêm field): `ok=False`
cho cả 2 mục → `assert not False` → qua, không hồi quy gì. Sau khi thêm
field ở task sau: `ok=True` cho cả 2 → `assert not True` → FAIL đúng như
kỳ vọng, chỉ đúng thông báo cần xoá mục nào.

## Hệ quả lên contract test (sau khi sửa đúng ở trên)

Sau khi sửa logic VÀ thêm 2 field, `get_sale_order_detail` sẽ có field
khớp cả 2 nhãn còn lại trong `_DATE_STATUS_LABELS` — nghĩa là cơ chế vừa
sửa sẽ TỰ BÁO LỖI đòi xoá cả 2 dòng ngoại lệ khỏi `_KNOWN_GAPS`. Đây là
bằng chứng sống rằng việc thêm field đã đóng đúng khoảng trống mà contract
test đo — nếu xoá cả 2 dòng mà test KHÔNG tự báo lỗi trước đó, nghĩa là có
gì sai, phải điều tra trước khi xoá.

Không đổi gì trong `backend/evals/cases.py` (`GATHER_CASES`) — fixture
viết tay ĐÃ khẳng định các nhãn này từ trước (không phải mới), và
`--set gather` dùng stub (không quan tâm khả năng thật của tool) nên
không bị ảnh hưởng, dự kiến vẫn 4/4 PASS như cũ.

## Xác minh qua Odoo thật — không dùng S00042

Vì S00042 đang `draft`, chưa từng giao, KHÔNG dùng được để đo "ngày giao
thực tế" dù code đã đúng. Không hard-code số đơn cụ thể trong plan (dữ
liệu demo đã chứng minh trôi theo thời gian) — thay vào đó, TRA ĐỘNG một
đơn có `effective_date` thật lúc thực thi:

```python
gw = default_gateway()
rows = gw.search_read("sale.order", [["effective_date", "!=", False]],
                      ["name", "effective_date"], limit=1)
```

Dùng `rows[0]["name"]` tìm được để chẩn đoán trực tiếp (bypass MCP, gọi
thẳng `sales.get_sale_order_detail` qua Gateway thật) — xác nhận
`effective_date` trả về đúng khớp giá trị `search_read` độc lập vừa tra.
Nếu KHÔNG còn đơn nào có `effective_date` thật (dữ liệu demo trôi tiếp),
DỪNG LẠI, báo cáo BLOCKED — không đoán, không tự viết giá trị giả.

## Testing

- Unit test mới cho `sales.py`/`tools.py` (TDD, gateway giả — không cần
  Odoo thật).
- Chẩn đoán Odoo thật (mục trên) — xác nhận field thật hoạt động cho MỘT
  đơn đã giao thật.
- `_KNOWN_GAPS` phải rỗng (2 dòng bị contract test tự đòi xoá) — xác nhận
  bằng cách chạy test, đọc thông báo lỗi, XOÁ đúng những gì lỗi chỉ ra
  (không đoán trước).
- Full suite 2 chế độ.

## Xong nghĩa là

1. Logic `_KNOWN_GAPS` trong contract test được sửa đúng — bắt được CẢ
   hai kịch bản "cấu hình chết" (fixture đổi chữ VÀ gap đã được sửa),
   xác nhận bằng cách trace tay/test cả trạng thái TRƯỚC (không hồi quy,
   2 mục vẫn hợp lệ) lẫn SAU khi thêm field (assert mới phải fail đúng).
2. `get_sale_order_detail` đọc thêm `commitment_date`/`effective_date`,
   xác nhận bằng unit test.
3. Contract test (đã sửa đúng ở điều 1) tự báo lỗi đòi xoá cả 2 dòng
   `_KNOWN_GAPS` — xoá đúng theo thông báo, `_KNOWN_GAPS` rỗng sau khi
   sửa.
4. Chẩn đoán Odoo thật (đơn tra động, không phải S00042) xác nhận
   `effective_date` trả về đúng giá trị thật.
5. `--set gather` đo lại, xác nhận vẫn 4/4 PASS (không hồi quy).
6. Toàn bộ test 2 chế độ xanh.
7. Không lộ tool mới, không sửa `GATHER_ERP_PROMPT`, không sửa
   `GATHER_CASES`.
