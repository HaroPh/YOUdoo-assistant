# Sửa ca `bang_gia_chiet_khau` trong `GATHER_CASES` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa ca `bang_gia_chiet_khau` trong `GATHER_CASES`
(`backend/evals/cases.py`) — đổi từ hỏi % chiết khấu (không tool ERP nào
trả về được) sang hỏi giá niêm yết (tool thật trả về được), đóng nốt defect
"hạng lỗi thứ ba" cuối cùng còn lại trong `GATHER_CASES`.

**Architecture:** Đổi 3 thứ CÙNG LÚC trong đúng 1 case-tuple: câu hỏi,
`required_facts`, và fixture text của `get_product_price` — khác các plan
fixture-fix trước (chỉ đổi fixture text), vì `required_facts` cũ
(`"12%"`) chính là giá trị bịa, không thể giữ nguyên. `required_tools`
giữ nguyên nguyên vẹn.

**Tech Stack:** Python 3.12, pytest, `evals/run_eval.py`, `jobs/eval_gate.py`.

**Spec:** `docs/superpowers/specs/2026-08-04-gather-cases-product-price-fix-design.md`

## Global Constraints

- Fixture chỉ được dùng field tool THẬT SỰ đọc —
  `sales.get_product_price` (`backend/src/erp_query/sales.py:73-90`) chỉ
  đọc `list_price`, trả đúng format `f"Giá {name}: {price:,.0f} (SL
  {qty:g})."` — KHÔNG có chiết khấu.
- `required_tools` PHẢI giữ nguyên `("find_customer", "find_product",
  "get_product_price")` — mục đích gốc của ca này là đo tool_recall trên
  chuỗi 3 tool, không đổi.
- Fixture text của `get_product_price` PHẢI dùng đúng nguyên văn
  `"Giá Large Cabinet: 2.400.000 (SL 50)."` — đã được kiểm chứng ở ca song
  sinh trong `MULTI_SOURCE_GATHER_CASES`, không viết lại.
- KHÔNG đổi tên topic `bang_gia_chiet_khau` — dùng chung ở các set khác
  qua `fixtures.load_chunks()`.
- KHÔNG sửa các doc/report lịch sử đã trích dẫn defect cũ
  (`2026-08-01-sp2c-gather-eval.md`,
  `2026-08-04-multi-source-gather-eval*.md`,
  `2026-08-04-gather-cases-overdue-invoices-fix*.md`) — giữ nguyên làm
  biên bản lịch sử.
- Chạy test: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
- Chạy eval thật cần env: `set -a && source ../.env && set +a` trước khi
  gọi `-m jobs run eval-gate` (bash), và Postgres `youdoo` + Odoo phải
  đang chạy.
- Comment/docstring trong repo này viết tiếng Việt — giữ đúng văn phong
  file đang sửa.
- **Lưu ý worktree:** mọi lệnh `cd` trong plan này giả định chạy trong
  worktree được cấp cho plan này (`<worktree-path>/backend`), KHÔNG phải
  `D:/Youdoo/backend` (repo chính) — xác nhận bằng
  `git rev-parse --show-toplevel` trước khi chạy lệnh nếu không chắc.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/evals/cases.py` | Sửa câu hỏi + `required_facts` + fixture text của ca `bang_gia_chiet_khau` trong `GATHER_CASES`; dọn comment cảnh báo |
| `docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix-report.md` (mới) | Số đo `--set gather` thật sau khi sửa |

---

### Task 1: Sửa case + đo thật

**Files:**
- Modify: `backend/evals/cases.py:706-728` (ca `bang_gia_chiet_khau` trong `GATHER_CASES`)
- Test: `backend/tests/jobs/test_eval_gather.py` (không sửa, chỉ chạy lại)
- Create: `docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix-report.md`

**Interfaces:** Không có API mới. `GATHER_CASES` giữ nguyên hình dạng
`(topic, question, required_tools, required_facts, tool_fixtures)`.

- [ ] **Step 1: Chạy baseline test TRƯỚC khi sửa**

Run: `cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -q`
Expected: toàn bộ PASS (ghi lại số lượng test PASS để đối chiếu ở Step 4).

- [ ] **Step 2: Sửa case trong `GATHER_CASES`**

Trong `backend/evals/cases.py`, tìm khối sau (hiện ở dòng ~706-728):

```python
    # bang_gia_chiet_khau — ca 3 tool nối chuỗi (find_customer → find_product
    # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
    # một lượt gọi đơn.
    #
    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
    # 2026-08-04-multi-source-gather-eval-design.md §7): fixture
    # get_product_price dưới đây khẳng định "đã áp chiết khấu số lượng 12%",
    # nhưng sales.get_product_price (sales.py:73-90) chỉ đọc list_price và
    # docstring nói rõ nó KHÔNG áp pricelist/chiết khấu — pricelist cần ORM
    # method mà gateway read-only không cho phép. Đây là đúng "hạng lỗi thứ
    # ba" (fixture khẳng định năng lực tool không có), ở một tool contract
    # test chưa phủ (nhãn hiện chỉ về ngày/trạng thái, không về giá).
    # CỐ Ý chưa sửa: required_facts của ca này là ("12%",), sửa sẽ đổi số đo
    # của set `gather` và cần một lượt đo riêng để quy trách nhiệm.
    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
     ("find_customer", "find_product", "get_product_price"),
     ("12%",),
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price":
      "Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): "
      "2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"}),
]
```

Thay TOÀN BỘ khối trên bằng:

```python
    # bang_gia_chiet_khau — ca 3 tool nối chuỗi (find_customer → find_product
    # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
    # một lượt gọi đơn.
    #
    # Câu hỏi đã sửa từ "được chiết khấu bao nhiêu?" sang tra giá niêm yết
    # (plan 2026-08-04-gather-cases-product-price-fix): sales.get_product_price
    # (sales.py:73-90) chỉ đọc list_price, KHÔNG áp pricelist/chiết khấu —
    # pricelist cần ORM method mà gateway read-only không cho phép. Không
    # tool ERP nào trong hệ thống trả về được % chiết khấu, nên câu hỏi cũ
    # đòi required_facts=("12%",) — một giá trị KHÔNG thể đến từ ERP thật,
    # không phải field bị bỏ sót (khác lớp "hạng lỗi thứ ba" đã sửa ở
    # get_overdue_invoices). Fixture get_product_price dưới đây nguyên văn
    # đã kiểm chứng ở ca song sinh trong MULTI_SOURCE_GATHER_CASES.
    #
    # Topic vẫn tên "bang_gia_chiet_khau" (dùng chung ở set khác qua
    # fixtures.load_chunks()) dù ca CỤ THỂ này trong GATHER_CASES giờ đo
    # tra giá, không phải tra chiết khấu — lệch tên/nội dung có chủ đích,
    # đổi tên topic ngoài phạm vi plan này.
    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet, giá niêm yết là bao nhiêu?",
     ("find_customer", "find_product", "get_product_price"),
     ("2.400.000",),
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price": "Giá Large Cabinet: 2.400.000 (SL 50)."}),
]
```

- [ ] **Step 3: Chạy lại test — phải PASS, cùng số lượng như Step 1**

Run: `cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -q`
Expected: PASS, đúng số lượng test đã ghi ở Step 1.

Chạy thêm toàn bộ suite unit-only:

Run: `cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ, không giảm số PASS so với baseline đã biết trước
khi bắt đầu (1121 passed, 4 skipped, 43 deselected — nếu khác trên máy
bạn, đối chiếu không CÓ fail mới, không cần khớp tuyệt đối con số này).

- [ ] **Step 4: Đo thật `--set gather`**

Cần Postgres `youdoo` + Odoo đang chạy. Chạy (bash):

```bash
cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Expected: `tool_recall=1.000 fact_coverage=1.000` — cả 4 ca PASS, bao gồm
ca `bang_gia_chiet_khau` vừa sửa (fact_coverage đạt vì "2.400.000" đúng là
giá trị thật `get_product_price` trả về, không phải giá trị bịa). Nếu ca
`bang_gia_chiet_khau` KHÔNG pass, DỪNG lại — kiểm tra xem model có tổng
hợp lại số "2.400.000" trong `erp_facts` hay không (không phải lỗi thiết
kế câu hỏi, có thể là vấn đề tổng hợp cần điều tra riêng, không tự sửa
thêm trong task này).

- [ ] **Step 5: Viết report**

Tạo `docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix-report.md`
gồm: số đo `--set gather` đầy đủ 4 ca (kèm đường dẫn file log JSON), xác
nhận ca `bang_gia_chiet_khau` PASS với câu hỏi/required_facts mới, xác
nhận 3 ca còn lại (`sla_giao_hang`, `chinh_sach_hoan_hang`,
`chinh_sach_thanh_toan`) không đổi so với lần đo trước (Task 1 Step 5 của
plan `gather-cases-overdue-invoices-fix`).

- [ ] **Step 6: Commit**

```bash
git add backend/evals/cases.py docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix-report.md
git commit -m "fix(gather-cases): đổi ca bang_gia_chiet_khau sang tra giá niêm yết — required_facts cũ (12%) là giá trị không tool ERP nào trả về được"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1-2 vấn đề + vì sao khó hơn ca trước | — (đã làm khi viết spec, không lặp lại) |
| §3 quyết định: đổi câu hỏi + required_facts + fixture, giữ required_tools | Task 1 Step 2 |
| §4 kiểm chứng đo thật | Task 1 Step 4 |
| §5 file bị chạm | Task 1 (cases.py, report) |
| §6 tiêu chí hoàn thành | Task 1 Step 3, Step 4 |

**Type consistency:** `GATHER_CASES` giữ nguyên hình dạng 5-tuple
`(topic, question, required_tools, required_facts, tool_fixtures)` trong
suốt plan — không đổi. Không có hàm/API mới nào được định nghĩa.
