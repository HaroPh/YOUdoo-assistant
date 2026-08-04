# Sửa fixture `get_overdue_invoices` trong `GATHER_CASES` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa fixture `get_overdue_invoices` trong `GATHER_CASES`
(`backend/evals/cases.py`) cho khớp format thật của tool — xoá cụm "quá hạn
N ngày" (field không tồn tại trên `accounting.get_overdue_invoices`) — và
xác nhận bằng đo thật rằng số đo của set `gather` không đổi.

**Architecture:** Đổi ĐÚNG MỘT biến (text fixture của 1 tool trong 1 case),
giữ nguyên `required_facts`/`required_tools`/`question`. Không thêm cơ chế
test mới — dọn 2 comment cảnh báo đã hết hiệu lực và xác nhận bằng 1 lượt
đo `--set gather` thật, so với baseline đã biết (SP-2c:
`tool_recall=1.0, fact_coverage=1.0`).

**Tech Stack:** Python 3.12, pytest, `evals/run_eval.py`, `jobs/eval_gate.py`.

**Spec:** `docs/superpowers/specs/2026-08-04-gather-cases-overdue-invoices-fix-design.md`

## Global Constraints

- Fixture chỉ được dùng field tool THẬT SỰ đọc — `accounting.get_overdue_invoices`
  (`backend/src/erp_query/accounting.py:35-51`) chỉ đọc/trả `_FIELDS`
  (`accounting.py:7-8`): `name`, `partner_id`, `invoice_date`,
  `invoice_date_due`, `amount_total`, `amount_residual`, `payment_state`.
  KHÔNG có field số-ngày-quá-hạn nào.
- `required_facts` của ca này là `("INV/2026/00030",)` — KHÔNG được đổi;
  đây là điều kiện để phép đo trước/sau so sánh được trên đúng một biến
  (spec §4, §5).
- KHÔNG thêm cơ chế test/guard mới cho lớp lỗi này — quyết định đã chốt ở
  spec §3 (nhất quán với cách dự án xử lý giới hạn scanner số học
  `MULTI_SOURCE_DERIVED_DIGITS`: ghi nhận/sửa thủ công từng trường hợp cụ
  thể, không xây bộ xác minh tổng quát).
- Chạy test: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
- Chạy eval thật cần env: `set -a && source ../.env && set +a` trước khi gọi
  `-m jobs run eval-gate` (bash), và Postgres `youdoo` + Odoo phải đang chạy.
- Comment/docstring trong repo này viết tiếng Việt — giữ đúng văn phong file
  đang sửa.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/evals/cases.py` | Sửa fixture text `get_overdue_invoices` trong `GATHER_CASES`; dọn comment cảnh báo tại chỗ + cross-reference trong `MULTI_SOURCE_GATHER_CASES` |
| `docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md` (mới) | Số đo `--set gather` thật sau khi sửa, so với baseline SP-2c |

---

### Task 1: Sửa fixture + dọn comment + đo thật

**Files:**
- Modify: `backend/evals/cases.py:518-528` (comment cross-reference trong
  `MULTI_SOURCE_GATHER_CASES`)
- Modify: `backend/evals/cases.py:665-695` (fixture + comment trong
  `GATHER_CASES`)
- Test: `backend/tests/jobs/test_eval_gather.py` (không sửa, chỉ chạy lại)
- Create: `docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md`

**Interfaces:** Không có API mới. `GATHER_CASES` giữ nguyên hình dạng
`(topic, question, required_tools, required_facts, tool_fixtures)`.

- [ ] **Step 1: Chạy baseline test TRƯỚC khi sửa**

Đây không phải thay đổi hành vi code (chỉ đổi text fixture), nên không có
test mới cần viết trước — bước "TDD" ở đây là chụp lại trạng thái PASS
hiện tại để đối chiếu sau khi sửa không có gì vỡ.

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py tests/jobs/test_eval_multi_source_gather.py -q`
Expected: toàn bộ PASS (ghi lại số lượng test PASS để đối chiếu ở Step 4).

- [ ] **Step 2: Sửa fixture + comment trong `GATHER_CASES`**

Trong `backend/evals/cases.py`, tìm khối sau (hiện ở dòng ~665-695):

```python
    # chinh_sach_thanh_toan — câu hỏi giống hệt MULTI_SOURCE_CASES (S00050).
    # required_fact là mã hoá đơn INV/2026/00030 (KHÔNG phải "32 ngày" —
    # sửa sau review toàn nhánh: "32 ngày" đã có sẵn NGUYÊN VĂN trong câu
    # hỏi, model chép lại câu hỏi là đủ đậu, không đo được gì thật). Mã hoá
    # đơn CHỈ xuất hiện trong dữ liệu tool, đòi model phải đọc và đối chiếu
    # đúng dòng giữa nhiều dòng dữ liệu khác.
    #
    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
    # 2026-08-04-multi-source-gather-eval-design.md §7): fixture dưới đây
    # khẳng định "quá hạn 32 ngày" / "quá hạn 20 ngày" (số ngày quá hạn),
    # nhưng accounting.get_overdue_invoices (accounting.py:35-51) chỉ
    # đọc/trả về _FIELDS (accounting.py:7-8) — name, partner_id,
    # invoice_date, invoice_date_due, amount_total, amount_residual,
    # payment_state — KHÔNG có field số-ngày-quá-hạn nào. Đúng "hạng lỗi thứ
    # ba" (fixture khẳng định năng lực tool không có); defect y hệt đã được
    # SỬA ở fixture tương ứng của MULTI_SOURCE_GATHER_CASES (xem comment ở
    # cases.py:518-528). CỐ Ý chưa sửa ở đây: required_facts của ca này là
    # ("INV/2026/00030",) — không chạm field "quá hạn N ngày" — sửa sẽ đổi
    # số đo của set `gather` và cần một lượt đo riêng để quy trách nhiệm,
    # cùng lý do với ca get_product_price/"12%" bên dưới.
    ("chinh_sach_thanh_toan",
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     ("get_overdue_invoices",),
     ("INV/2026/00030",),
     {"get_overdue_invoices":
      "2 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "quá hạn 32 ngày | còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "quá hạn 20 ngày | còn 1.000.000"}),
```

Thay TOÀN BỘ khối trên bằng:

```python
    # chinh_sach_thanh_toan — câu hỏi giống hệt MULTI_SOURCE_CASES (S00050).
    # required_fact là mã hoá đơn INV/2026/00030 (KHÔNG phải "32 ngày" —
    # sửa sau review toàn nhánh: "32 ngày" đã có sẵn NGUYÊN VĂN trong câu
    # hỏi, model chép lại câu hỏi là đủ đậu, không đo được gì thật). Mã hoá
    # đơn CHỈ xuất hiện trong dữ liệu tool, đòi model phải đọc và đối chiếu
    # đúng dòng giữa nhiều dòng dữ liệu khác.
    #
    # Fixture dưới đây đã được sửa khớp format thật của
    # accounting.get_overdue_invoices (accounting.py:35-51, chỉ trả _FIELDS
    # — accounting.py:7-8 — không có field số-ngày-quá-hạn nào). Trước đó
    # fixture khẳng định "quá hạn N ngày" (hạng lỗi thứ ba, phát hiện ở
    # spec 2026-08-04-multi-source-gather-eval-design.md §7) — đã sửa ở
    # plan 2026-08-04-gather-cases-overdue-invoices-fix, đo thật xác nhận
    # tool_recall/fact_coverage không đổi (required_facts của ca này chưa
    # từng chạm field đó).
    ("chinh_sach_thanh_toan",
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     ("get_overdue_invoices",),
     ("INV/2026/00030",),
     {"get_overdue_invoices":
      "2 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "còn 1.000.000"}),
```

(Chỉ khác biệt so với bản gốc: 2 đoạn `"quá hạn 32 ngày | "` và `"quá hạn
20 ngày | "` bị xoá khỏi fixture text; comment "CẢNH BÁO CHƯA SỬA" thay
bằng comment xác nhận đã sửa.)

- [ ] **Step 3: Sửa comment cross-reference trong `MULTI_SOURCE_GATHER_CASES`**

Trong `backend/evals/cases.py`, tìm khối comment sau (hiện ở dòng
~518-528, ngay trước ca `chinh_sach_thanh_toan`/`get_overdue_invoices` thứ
hai trong `MULTI_SOURCE_GATHER_CASES`):

```python
    # Fixture ĐIỀU CHỈNH từ GATHER_CASES (cùng câu hỏi, cùng tool), KHÔNG
    # chép nguyên văn: bản ở GATHER_CASES khẳng định "quá hạn N ngày", nhưng
    # get_overdue_invoices (accounting.py:35-51) chỉ đọc/trả về _FIELDS —
    # name, partner_id, invoice_date, invoice_date_due, amount_total,
    # amount_residual, payment_state — KHÔNG có field số-ngày-quá-hạn nào;
    # display thật là "{name} | {partner} | đến hạn {invoice_date_due} |
    # còn {amount_residual}". Đây đúng "hạng lỗi thứ ba" đã nêu ở đầu file
    # (fixture khẳng định năng lực tool không có). Lỗi tương tự VẪN CÒN
    # nguyên trong GATHER_CASES — CỐ Ý chưa sửa ở đó, cùng lý do với ca
    # get_product_price/"12%" đã ghi chú ở cuối GATHER_CASES: sửa sẽ đổi số
    # đo của set `gather` và cần một lượt đo riêng để quy trách nhiệm.
```

Thay bằng:

```python
    # Fixture ĐIỀU CHỈNH từ GATHER_CASES (cùng câu hỏi, cùng tool), KHÔNG
    # chép nguyên văn: get_overdue_invoices (accounting.py:35-51) chỉ
    # đọc/trả về _FIELDS — name, partner_id, invoice_date, invoice_date_due,
    # amount_total, amount_residual, payment_state — KHÔNG có field
    # số-ngày-quá-hạn nào; display thật là "{name} | {partner} | đến hạn
    # {invoice_date_due} | còn {amount_residual}". Đây đúng "hạng lỗi thứ
    # ba" đã nêu ở đầu file (fixture khẳng định năng lực tool không có).
    # Lỗi tương tự trong GATHER_CASES (từng CỐ Ý chưa sửa) đã được sửa ở
    # plan 2026-08-04-gather-cases-overdue-invoices-fix — cả hai fixture
    # nay khớp nhau và khớp format thật.
```

(Chỉ đổi 3 câu cuối từ thì "hiện tại còn tồn tại lỗi" sang thì "đã sửa";
giữ nguyên phần giải thích field/display ở đầu đoạn.)

- [ ] **Step 4: Chạy lại test — phải PASS, cùng số lượng như Step 1**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py tests/jobs/test_eval_multi_source_gather.py -q`
Expected: PASS, đúng số lượng test đã ghi ở Step 1 (không tăng không
giảm — xác nhận sửa fixture text không làm gãy assertion nào có sẵn).

Chạy thêm toàn bộ suite unit-only để chắc chắn không có test nào khác ở
xa phụ thuộc vào chuỗi "quá hạn" đã xoá:

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ (baseline đã biết từ plan trước: 1120 passed, 4
skipped, 43 deselected — nếu số liệu gốc trên máy bạn khác, đối chiếu
không tăng số fail, không phải khớp tuyệt đối con số này).

- [ ] **Step 5: Đo thật `--set gather`**

Cần Postgres `youdoo` + Odoo đang chạy. Chạy (bash):

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Expected: `tool_recall=1.000 fact_coverage=1.000` (khớp baseline SP-2c đã
biết, 4 case, xem `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md`
nếu cần đối chiếu) — **KHÔNG đổi** so với trước khi sửa, đúng như spec §2/§5
đã lập luận trước (`required_facts` của ca vừa sửa chưa từng chạm chuỗi bị
xoá). Nếu số đo LỆCH so với 1.000/1.000, DỪNG lại, không tự suy diễn
nguyên nhân — báo cáo nguyên văn kết quả và đường dẫn file log JSON
(`logs/jobs/eval-gate-*.json`) để controller điều tra.

- [ ] **Step 6: Viết report**

Tạo `docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md`
gồm: số đo `--set gather` (kèm đường dẫn file log JSON), so sánh với
baseline SP-2c (1.000/1.000), xác nhận không hồi quy; xác nhận không còn
comment `CẢNH BÁO CHƯA SỬA` nào trỏ tới defect này trong repo (grep
`"CẢNH BÁO CHƯA SỬA"` trong `backend/evals/cases.py` — kết quả phải CHỈ
còn đúng 1 chỗ, cho fixture `get_product_price`/"12%" — đây là defect
KHÁC, cố ý vẫn chưa sửa, ngoài phạm vi plan này).

- [ ] **Step 7: Commit**

```bash
git add backend/evals/cases.py docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md
git commit -m "fix(gather-cases): sửa fixture get_overdue_invoices khớp format thật — xoá 'quá hạn N ngày' không tồn tại"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1 vấn đề — fixture khẳng định field không tồn tại | Task 1 Step 2 |
| §2 vì sao an toàn để sửa — required_facts không đổi | Task 1 Step 2 (giữ nguyên), Step 5 (đo xác nhận) |
| §3 sửa tối thiểu, không xây guard mới | Task 1 (không có step nào thêm test machinery mới) |
| §4 nội dung sửa (fixture text + 2 comment) | Task 1 Step 2, Step 3 |
| §5 đo thật, so baseline SP-2c | Task 1 Step 5 |
| §7 tiêu chí hoàn thành (test xanh, đo khớp baseline, không còn comment cảnh báo) | Task 1 Step 4, Step 5, Step 6 |

**Type consistency:** `GATHER_CASES` giữ nguyên hình dạng 5-tuple
`(topic, question, required_tools, required_facts, tool_fixtures)` trong
suốt plan — không đổi. Không có hàm/API mới nào được định nghĩa.
