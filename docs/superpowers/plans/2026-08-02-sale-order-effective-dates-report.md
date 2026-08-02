# 2026-08-02: Sale Order Effective Dates — Implementation Report

## Task 1: Fix _KNOWN_GAPS contract test bug

### Step 3 Result (Confirm bug exists)
**Status: FAIL as expected** — Test `test_known_gaps_catches_entry_when_real_field_now_exists` failed with `DID NOT RAISE AssertionError`, proving the original logic did not catch the scenario where a gap has been fixed (field now exists in reality) but `_KNOWN_GAPS` entry was not removed.

### Step 5 Result (Both tests PASS)
**Status: PASS** — Both tests pass:
- `test_known_gaps_catches_entry_when_real_field_now_exists`: PASS (newly added test now catches the gap closure scenario)
- `test_gather_cases_fixture_labels_match_real_tool_fields`: PASS (existing test still works without regression)

### Commit
```
7fea52f fix(gather-cases-contract-test): _KNOWN_GAPS phải kiểm field thật ngay cả khi mục đã có ngoại lệ — bản gốc chỉ bắt 1/2 kịch bản cấu hình chết
```

### Summary
Task 1 completed successfully. The contract test now properly validates that `_KNOWN_GAPS` entries must have both their labels still matching fixture text AND their fields still missing from real tools. This prevents dead configuration from accumulating.

### Round 1 fix (after review): Code brief recursion bug
**Note**: Code in brief Step 2, if copied verbatim, would cause `RecursionError` when `monkeypatch.setitem(globals(), "_real_fields_for_tool", _fake_real_fields)` redirects the name to the new function, and then `_fake_real_fields` calls `_real_fields_for_tool(tool_name)` for fallback on non-`get_sale_order_detail` tools — this lookup now finds the patched `_fake_real_fields` again, causing infinite recursion. **Fixed**: Captured the original reference BEFORE patching (`_original_real_fields_for_tool = _real_fields_for_tool`), so fallback calls use the real function. This is the correct solution; Step 3 result (FAIL with `DID NOT RAISE`) is as expected only because the fix was already applied before running tests.

---

**Full detail**: See `.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-1-report.md`

## Task 2: `get_sale_order_detail` reads `commitment_date` and `effective_date`

### Overview
Added two new fields (`commitment_date`, `effective_date`) to the `get_sale_order_detail` function in `backend/src/erp_query/sales.py`, along with corresponding docstring updates and test coverage.

### Step 3 Result (New Test FAIL as expected)
**Status: FAIL** — Test `test_get_sale_order_detail_includes_effective_dates` failed with `AssertionError: assert 'commitment_date' in [...]` as expected—fields not yet in the search_read call.

### Step 5 Result (All Sales Tests PASS)
**Status: PASS** — All 7 sales tests pass, including the new test:
- `test_find_customer_delegates_to_resolve`: PASS
- `test_list_sale_orders_builds_domain_and_envelope`: PASS
- `test_get_product_price_reads_list_price`: PASS
- `test_sales_summary_uses_read_group`: PASS
- `test_get_sale_order_detail_includes_state`: PASS
- `test_get_sale_order_detail_includes_dates`: PASS
- `test_get_sale_order_detail_includes_effective_dates`: PASS (NEW)

### Step 8 Result (Docstring Test PASS)
**Status: PASS** — Test `test_get_sale_order_detail_description_mentions_effective_dates` passes, confirming docstring contains both new field labels.

### Step 9 Result (Full erp_query Test Suite PASS)
**Status: PASS** — All 143 tests in `tests/erp_query/` pass, no regressions detected.

### Commit
```
4c38fb4 feat(erp_query): get_sale_order_detail đọc thêm commitment_date/effective_date
```

### Summary
Task 2 completed successfully. The `get_sale_order_detail` function now retrieves and returns `commitment_date` and `effective_date` fields, with full test coverage and updated docstring reflecting the new capabilities.

---

**Full detail**: See `.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-2-report.md`

## Task 3 — Xác nhận contract test tự báo lỗi, dọn `_KNOWN_GAPS`, đo Odoo thật

**Trạng thái: HOÀN TẤT.** Trong quá trình chạy đã phát hiện thêm một
regression thật (ngoài dự đoán của brief), controller phê duyệt mở rộng
phạm vi Task 3 (vẫn trong cùng file) để sửa cùng, sau đó tiếp tục đúng
trình tự Step 4-8. Chi tiết đầy đủ:
`.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-3-report.md`.

## Task 3 Bước 1 — contract test tự báo lỗi

**FAIL đúng như brief dự đoán.** Thông báo lỗi nguyên văn:

```
AssertionError: _KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: case sla_giao_hang, tool 'get_sale_order_detail', nhãn 'ngày giao dự kiến' — field thật đã có (['commitment_date', 'effective_date']), xoá mục này khỏi _KNOWN_GAPS.
```

Bằng chứng sống Task 1 + Task 2 hoạt động đúng cùng nhau: field thật
(`commitment_date`/`effective_date`, do Task 2 thêm) xuất hiện, contract
test (logic đã Task 1 sửa) lập tức đòi xoá mục ngoại lệ tương ứng thay vì
im lặng bỏ qua.

## Task 3 Bước 2 — xoá `_KNOWN_GAPS`

Đã áp dụng đúng thay thế brief chỉ định (`_KNOWN_GAPS` → `set()` rỗng,
kèm comment lịch sử). `git diff` xác nhận khớp 100% văn bản brief.

## Task 3 Bước 3 — chạy lại, phát hiện regression ở test guard, sửa (controller phê duyệt), PASS

Kỳ vọng brief ban đầu: 25/25 pass. **Lần chạy đầu: 24 passed, 1 failed** —
`test_known_gaps_catches_entry_when_real_field_now_exists` (test guard do
chính Task 1 thêm) báo `Failed: DID NOT RAISE AssertionError`.

**Nguyên nhân gốc** (đã chẩn đoán độc lập trước khi báo cáo, xác nhận lại
bởi controller): test guard này monkeypatch `_real_fields_for_tool` để
giả lập field thật đã có, nhưng KHÔNG monkeypatch `_KNOWN_GAPS` — nó dựa
vào nội dung SỐNG (module-level) của `_KNOWN_GAPS` để tự tạo tình huống
"gap đã đóng nhưng mục còn trong danh sách". Ở thời điểm Task 1 viết test
này, `_KNOWN_GAPS` sống có đúng mục khớp nên test hoạt động đúng. Sau khi
Task 3 Bước 2 làm rỗng `_KNOWN_GAPS` (đúng theo brief), không còn key nào
từ `GATHER_CASES` khớp `_KNOWN_GAPS` rỗng, nên nhánh raise "KHÔNG CÒN CẦN
THIẾT" không bao giờ được thực thi nữa — test guard mất khả năng tự kích
hoạt kịch bản nó kiểm tra, không phải vì logic contract test chính (Task
1 đã sửa) sai.

Đây KHÔNG phải lỗi thao tác: `git diff` bước đầu xác nhận sửa `_KNOWN_GAPS`
khớp 100% văn bản brief. Việc sửa test guard nằm ngoài phạm vi file brief
Task 3 khai báo ban đầu (chỉ `test_eval_gather.py:330-341`) nên đã dừng
lại và báo cáo BLOCKED trước, không tự sửa.

**Controller đã xác nhận chẩn đoán đúng và phê duyệt mở rộng phạm vi Task
3** (vẫn chỉ trong `backend/tests/jobs/test_eval_gather.py`, không phạm
Global Constraint nào của plan) để sửa
`test_known_gaps_catches_entry_when_real_field_now_exists`: monkeypatch
CẢ `_KNOWN_GAPS` (bằng một mục giả lập độc lập
`{("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến")}`),
không chỉ `_real_fields_for_tool` — để test guard không còn phụ thuộc
nội dung sống của `_KNOWN_GAPS` thật. Giữ nguyên thứ tự capture tham
chiếu gốc TRƯỚC khi patch `_real_fields_for_tool` (bài học từ round 1 của
Task 1 — tránh đệ quy vô hạn qua self-referential monkeypatch).

Chạy lại sau khi sửa:

```
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

**Kết quả: 25 passed** — bao gồm cả
`test_gather_cases_fixture_labels_match_real_tool_fields` (với
`_KNOWN_GAPS` thật giờ rỗng) và
`test_known_gaps_catches_entry_when_real_field_now_exists` (giờ độc lập
với nội dung sống `_KNOWN_GAPS`).

## Task 3 Bước 4 — chẩn đoán Odoo thật

- Đơn dùng để đo: `S00165` (tra động lúc chạy, không phải S00042)
- `effective_date` từ search_read độc lập: `'2026-07-25 06:18:23'`
- `effective_date` từ get_sale_order_detail: `'2026-07-25 06:18:23'`
- Kết quả: **KHỚP**

## Task 3 Bước 5 — `--set gather`

- `tool_recall`: `1.0`, `fact_coverage`: `1.0`, `fails`: `[]` (4/4 case
  PASS, không hồi quy)
- log gốc: `logs/jobs/eval-gate-20260802T171038.json`

## Xác minh test

- Unit-only (`-m "not integration and not live"`): **1101 passed, 4
  skipped** (TRƯỚC: 1098 — +3 test mới: 1 guard test Task 1 + 2 test Task
  2)
- Integration (`-m integration`): **27 passed** (TRƯỚC: 27 — không đổi)
- 2 file fixture nhị phân (`bang_gia.xlsx`, `policy.docx`) bị lượt chạy
  unit-only làm đổi (hiện tượng đã biết) — đã khôi phục bằng
  `git checkout --` trước khi chạy integration.

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec
(`docs/superpowers/specs/2026-08-02-sale-order-effective-dates-design.md`):

1. **Đạt.** Logic `_KNOWN_GAPS` sửa đúng bắt cả 2 kịch bản "cấu hình
   chết" — Task 1 Step 3 (FAIL trước sửa) + Step 5 (PASS sau sửa) xác
   nhận cả trạng thái TRƯỚC lẫn SAU.
2. **Đạt.** `get_sale_order_detail` đọc thêm `commitment_date`/
   `effective_date` — Task 2 Step 3 (FAIL trước) + Step 5 (PASS sau, 7/7
   sales test) xác nhận bằng unit test; Task 3 Step 4 xác nhận thêm bằng
   Odoo thật (đơn S00165, KHỚP).
3. **Đạt.** Contract test tự báo lỗi đòi xoá `_KNOWN_GAPS` — Task 3 Step 1
   quan sát trực tiếp thông báo lỗi nguyên văn cho case `sla_giao_hang`
   (pytest dừng ở assert đầu tiên trong 1 lần chạy, đúng như brief lưu
   ý). Đã xoá CẢ 2 dòng cùng lúc theo đúng thay thế brief chỉ định (không
   xoá từng dòng một, không chạy riêng để lấy thông báo lỗi thứ hai cho
   case `chinh_sach_hoan_hang`). Bằng chứng dòng thứ hai cũng thật sự
   không còn cần thiết nằm ở kết quả Step 3 sau cùng: `_KNOWN_GAPS = set()`
   rỗng khiến MỌI tuple (topic, tool, nhãn) — kể cả tuple của
   `chinh_sach_hoan_hang`/`get_sale_order_detail`/"ngày giao thực tế" —
   đều rơi vào nhánh `assert ok` (đòi field thật phải có); 25/25 pass
   xác nhận nhánh đó đúng cho toàn bộ `GATHER_CASES`, gồm cả case thứ
   hai, không chỉ case đầu.
4. **Đạt.** Chẩn đoán Odoo thật (đơn `S00165`, tra động, không phải
   S00042) xác nhận `effective_date` trả về đúng giá trị thật — KHỚP.
   Lưu ý: `commitment_date` là field thật, tool đọc đúng, nhưng chẩn đoán
   Odoo thật lúc viết spec xác nhận KHÔNG đơn nào trong demo hiện tại
   populate field này (10/10 đơn gần nhất đều `False`) — không phải lỗi
   code, chỉ là dữ liệu demo chưa dùng field đó; xem
   `docs/superpowers/specs/2026-08-02-sale-order-effective-dates-design.md`.
5. **Đạt.** `--set gather` đo lại: `tool_recall=1.0, fact_coverage=1.0,
   fails=[]` — vẫn 4/4 PASS, không hồi quy.
6. **Đạt.** Toàn bộ test 2 chế độ xanh: unit-only 1101 passed (+3 so với
   1098 trước plan), integration 27 passed (không đổi).
7. **Đạt.** Không lộ tool mới — `get_sale_order_detail` vẫn 1 tool, chỉ
   đổi docstring (`backend/src/erp_query/tools.py`) để liệt kê thêm 2
   field mới. Không sửa `GATHER_ERP_PROMPT` (`backend/src/agents` không
   đổi dòng nào trong toàn plan). Không sửa `GATHER_CASES`
   (`backend/evals/cases.py` không đổi — chỉ test file tham chiếu
   `cases.GATHER_CASES` để đọc, không ghi).

**Phát sinh ngoài dự đoán của brief (đã xử lý, có phê duyệt)**: guard
test `test_known_gaps_catches_entry_when_real_field_now_exists` (Task 1)
phụ thuộc ngầm vào nội dung sống của `_KNOWN_GAPS`, hỏng ngay khi
`_KNOWN_GAPS` rỗng (Task 3 Step 2). Controller xác nhận chẩn đoán đúng,
phê duyệt mở rộng phạm vi Task 3 (cùng file) để sửa test guard độc lập
với nội dung sống `_KNOWN_GAPS`. Xem toàn bộ diễn biến, chẩn đoán, và
lý do dừng-rồi-tiếp-tục trong
`.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-3-report.md`.

**Chi tiết vận hành đầy đủ**: xem
`.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-3-report.md`.
