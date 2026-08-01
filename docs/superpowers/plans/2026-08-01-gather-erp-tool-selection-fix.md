# Sửa hướng dẫn chọn tool của `gather_erp` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa nguyên nhân thật (đã điều tra trực tiếp, có bằng chứng Odoo
thật) của 2 ca `multi_source` còn FAIL từ trước SP-2b: `gather_erp` luôn
chọn `get_sale_order_detail` (không có field ngày) thay vì `list_sale_orders`
(có `date_order`/`delivery_status`) khi câu hỏi cần ngày/trạng thái giao của
một đơn cụ thể.

**Architecture:** Thêm một quy tắc vào `GATHER_ERP_PROMPT` chỉ rõ dùng
`list_sale_orders` cho câu hỏi cần ngày/trạng thái giao. Sửa 2 case
`GATHER_CASES` hiện có (không phải case mới) — chúng đang gán field ngày
vào fixture của `get_sale_order_detail`, một khả năng tool đó không có
thật, khiến bộ đo `gather` không phát hiện được bug này. Trình tự xác minh
NGƯỢC thường lệ: sửa fixture trước, đo THẬT để xác nhận nó FAIL (chứng
minh case tái hiện đúng bug) — nếu không FAIL thì dừng lại, không sửa
prompt. Sửa prompt sau, đo lại để xác nhận PASS. Đo `multi_source` thật lần
cuối để xác nhận nguyên nhân gốc đã hết.

**Tech Stack:** Python 3.12, LangChain 1.2.18, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-08-01-gather-erp-tool-selection-design.md`

## Global Constraints

- **0 dòng thay đổi trong `backend/src/agents/graph.py`, `fanout.py`,
  `state.py`.** Đây là sửa prompt + dữ liệu eval, không phải kiến trúc.
- **Không sửa mô tả tool dùng chung** (`get_sale_order_detail`/
  `list_sale_orders` trong `backend/src/erp_query/tools.py`) — chỉ sửa
  `GATHER_ERP_PROMPT`, prompt riêng của `gather_erp`.
- **Chỉ sửa 2 case `GATHER_CASES` đã có** (`sla_giao_hang`,
  `chinh_sach_hoan_hang`) — KHÔNG thêm case mới, KHÔNG đụng 2 case còn lại
  (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`).
- **Trình tự bắt buộc, không được đảo**: sửa fixture (Task 1) → đo THẬT xác
  nhận FAIL → sửa prompt (Task 2) → đo THẬT xác nhận PASS → đo `multi_source`
  (Task 3). Nếu Task 1's đo THẬT KHÔNG cho ra FAIL, DỪNG LẠI — báo cáo
  BLOCKED, không tự ý sửa prompt trước rồi đo sau (đảo trình tự làm mất khả
  năng chứng minh case tái hiện đúng bug thật).
- Chạy Python bằng `backend/.venv/Scripts/python.exe`. Đặt
  `PYTHONIOENCODING=utf-8` trước lệnh in tiếng Việt hoặc chạy job có gọi
  LLM/Odoo thật.
- "Full suite" = `pytest -m "not integration and not live"` (unit-only);
  `pytest -m integration`; `pytest -m live` — cả ba chế độ, không có chế độ
  "mặc định" nào tự loại `live`/`integration`.

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Sửa | `backend/evals/cases.py` | 2 case `GATHER_CASES` — dữ liệu ngày chuyển sang `list_sale_orders` |
| Sửa | `backend/src/agents/prompts.py` | `GATHER_ERP_PROMPT` — thêm quy tắc chọn tool |
| Tạo | `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md` | báo cáo số đo TRƯỚC/SAU — sản phẩm chính của Task 1-3 |

---

## Task 1: Sửa 2 case `GATHER_CASES` — đo THẬT xác nhận tái hiện đúng bug (phải FAIL)

**KHÔNG sửa `GATHER_ERP_PROMPT` trong task này.** Nếu đo ở Step 4 không ra
FAIL, DỪNG LẠI — báo cáo BLOCKED, không sang Task 2.

**Files:**
- Modify: `backend/evals/cases.py:515-529` (2 case `sla_giao_hang`,
  `chinh_sach_hoan_hang` trong `GATHER_CASES`)
- Create: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`

**Interfaces:**
- Consumes: `evals.run_eval.eval_gather`, `--set gather` (đã có sẵn, SP-2c).
- Produces: 2 case sửa, số đo TRƯỚC (kỳ vọng FAIL) ghi vào file report.

- [ ] **Step 1: Đọc đúng vị trí cần sửa**

Mở `backend/evals/cases.py`, tìm đoạn `GATHER_CASES` bắt đầu bằng comment
`# sla_giao_hang — hồi quy thật quan sát được ở Task 10 (SP-2b)`. Xác nhận
nội dung hiện tại khớp CHÍNH XÁC:

```python
    # sla_giao_hang — hồi quy thật quan sát được ở Task 10 (SP-2b): model
    # đọc đúng chính sách 3-ngày-SLA nhưng nói "không cung cấp thông tin về
    # ngày xác nhận đơn hàng, ngày giao hàng thực tế" rồi từ chối kết luận
    # (logs/jobs/eval-gate-20260801T130223.json). Case này đo: nếu tool CÓ
    # đủ hai ngày đó, gather_erp có lấy và truyền đạt được không.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("get_sale_order_detail",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận) | "
      "ngày xác nhận: 18/07/2026 | ngày giao dự kiến: 20/07/2026 | "
      "loại đơn: thường"}),
    # chinh_sach_hoan_hang — cùng hình dạng: chính sách cần "ngày giao thực
    # tế" để tính hạn 30 ngày hoàn hàng.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("get_sale_order_detail",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao) | "
      "ngày giao thực tế: 15/07/2026"}),
```

Nếu nội dung KHÔNG khớp (file đã đổi từ lúc viết plan), DỪNG LẠI, báo cáo
NEEDS_CONTEXT kèm nội dung thật đang có — không tự đoán cách chỉnh sửa.

- [ ] **Step 2: Sửa 2 case**

Thay đúng khối trên bằng:

```python
    # sla_giao_hang — SỬA sau điều tra 2026-08-01: dữ liệu ngày chuyển từ
    # get_sale_order_detail (KHÔNG có field ngày thật — sales.py:49-68) sang
    # list_sale_orders (CÓ date_order/delivery_status thật — sales.py:24-39,
    # xác nhận bằng gọi Odoo thật). get_sale_order_detail giữ fixture riêng
    # không có ngày, để nếu model lỡ gọi tool cũ thì case vẫn FAIL đúng.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("list_sale_orders",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận)",
      "list_sale_orders":
      "S00042 | Azure Interior | sale | ngày xác nhận: 18/07/2026 | "
      "ngày giao dự kiến: 20/07/2026"}),
    # chinh_sach_hoan_hang — cùng lý do sửa như sla_giao_hang ở trên.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("list_sale_orders",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao)",
      "list_sale_orders":
      "S00042 | Azure Interior | done | ngày giao thực tế: 15/07/2026"}),
```

Không đổi 2 case còn lại (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`).

- [ ] **Step 3: Chạy lại toàn bộ test unit của `test_eval_gather.py` — xác nhận vẫn xanh**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: TẤT CẢ pass (không cần thêm test mới — các test tự-nhất-quán đã có
từ SP-2c, `test_gather_cases_required_facts_exist_in_fixtures`,
`test_gather_cases_facts_not_leaked_by_the_question`,
`test_gather_cases_required_tools_are_real_erp_tool_names`,
`test_gather_cases_required_tools_have_fixtures`, tự động kiểm case mới
sửa vì chúng lặp qua TOÀN BỘ `GATHER_CASES`). Nếu bất kỳ test nào FAIL, đọc
kỹ thông báo lỗi — khả năng cao là gõ sai một trong hai case ở Step 2, sửa
lại cho khớp CHÍNH XÁC nội dung ở Step 2 rồi chạy lại.

- [ ] **Step 4: Chạy `--set gather` THẬT — bước quyết định, đọc kỹ kỳ vọng**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Đọc log JSON job in ra đường dẫn (`logs/jobs/eval-gate-<timestamp>.json`).
Tìm 2 case `sla_giao_hang` và `chinh_sach_hoan_hang` trong mảng `fails`.

**Kỳ vọng: CẢ HAI case này PHẢI xuất hiện trong `fails`**, với
`tool_recall_ok: false` (vì `gather_erp` hiện tại — CHƯA sửa prompt — vẫn
gọi `get_sale_order_detail`, không thoả `required_tools = ("list_sale_orders",)`
mới).

**Nếu CẢ HAI đều xuất hiện trong `fails` với `tool_recall_ok: false`**: đúng
kỳ vọng, case đã tái hiện được bug thật. Ghi lại `tool_recall`,
`fact_coverage` tổng, và chi tiết 2 case FAIL (bao gồm `called` — danh sách
tool thật sự gọi) vào file report (Step 5), rồi sang Task 2.

**Nếu MỘT trong hai (hoặc cả hai) KHÔNG xuất hiện trong `fails`** (nghĩa là
PASS dù chưa sửa prompt): DỪNG LẠI. KHÔNG sang Task 2. Ghi lại toàn bộ chi
tiết case đó (bao gồm `called`, `erp_facts`) vào report, và báo cáo trạng
thái **BLOCKED** — giả thuyết gốc (model luôn gọi `get_sale_order_detail`)
có thể không còn đúng, hoặc case sửa chưa đúng, cần điều tra thêm trước khi
tiếp tục. Đừng đoán — nêu chính xác dữ liệu quan sát được.

- [ ] **Step 5: Viết phần đầu file report**

Tạo `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`:

```markdown
# Báo cáo — sửa hướng dẫn chọn tool của gather_erp

Plan: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix.md`
Spec: `docs/superpowers/specs/2026-08-01-gather-erp-tool-selection-design.md`

## Bước 1 — xác nhận case sửa tái hiện đúng bug (TRƯỚC khi sửa prompt)

Chạy `jobs run eval-gate --set gather`, model: `<tên model thật>`, TRƯỚC khi
sửa `GATHER_ERP_PROMPT`.

- verdict: `<PASS|FAIL>` (gate `gather` trả True vô điều kiện — verdict này
  không phản ánh việc 2 case có FAIL đúng kỳ vọng hay không, xem chi tiết
  case dưới đây)
- `tool_recall`: `<số>`
- `fact_coverage`: `<số>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`
- Case `sla_giao_hang`: `<FAIL đúng kỳ vọng | PASS ngoài dự kiến>` —
  `called`: `<danh sách tool thật sự gọi>`
- Case `chinh_sach_hoan_hang`: `<FAIL đúng kỳ vọng | PASS ngoài dự kiến>` —
  `called`: `<danh sách tool thật sự gọi>`

**Kết luận bước này:** `<cả hai case FAIL đúng kỳ vọng — tiếp tục Task 2 |
BLOCKED — nêu rõ case nào không FAIL và tại sao cần dừng>`
```

Thay mọi `<...>` bằng giá trị thật.

- [ ] **Step 6: Commit**

Nếu Step 4 ra đúng kỳ vọng (cả hai FAIL):

```bash
git add backend/evals/cases.py docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md
git commit -m "fix(evals): sửa fixture 2 case GATHER_CASES gán nhầm ngày cho get_sale_order_detail"
```

Nếu Step 4 BLOCKED: vẫn commit đúng những gì đã sửa + report ghi rõ BLOCKED
(không xoá công đã làm), rồi dừng, báo cáo cho controller — KHÔNG tự ý sang
Task 2.

---

## Task 2: Sửa `GATHER_ERP_PROMPT` — đo THẬT xác nhận đã sửa (phải PASS)

**Chỉ thực hiện task này nếu Task 1 kết luận "cả hai case FAIL đúng kỳ
vọng".** Nếu Task 1 BLOCKED, task này không được thực hiện.

**Files:**
- Modify: `backend/src/agents/prompts.py:148-156` (`GATHER_ERP_PROMPT`)
- Modify: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`
  (nối thêm)

**Interfaces:**
- Consumes: kết quả Task 1 (2 case đã sửa, đã xác nhận FAIL đúng kỳ vọng).
- Produces: `GATHER_ERP_PROMPT` có quy tắc chọn tool mới; số đo SAU (kỳ
  vọng PASS) ghi vào report.

- [ ] **Step 1: Đọc đúng vị trí cần sửa**

Mở `backend/src/agents/prompts.py`, tìm `GATHER_ERP_PROMPT`. Xác nhận nội
dung hiện tại khớp CHÍNH XÁC:

```python
GATHER_ERP_PROMPT = """Bạn là bộ phận THU THẬP DỮ KIỆN ERP. Nhiệm vụ duy nhất: dùng các tool đọc Odoo để lấy ra những dữ kiện liên quan đến câu hỏi của người dùng.

Quy tắc:
- Chỉ NÊU DỮ KIỆN, dạng gạch đầu dòng ngắn (mã đơn, ngày, số lượng, trạng thái, tên khách, tên sản phẩm...).
- TUYỆT ĐỐI KHÔNG kết luận, không phán quyết câu hỏi của người dùng. Một bộ phận khác sẽ làm việc đó.
- KHÔNG viện dẫn chính sách/quy định/tài liệu nội bộ — bạn không có tài liệu trong tay, và một bộ phận khác đang lo phần đó.
- CHỈ dùng dữ kiện do tool trả về. Tuyệt đối không bịa số liệu.
- Nếu không lấy được dữ kiện nào liên quan, trả lời đúng một câu: Không tìm được dữ kiện ERP liên quan.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

Nếu KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT.

- [ ] **Step 2: Thêm quy tắc chọn tool**

Thay TOÀN BỘ khối trên bằng (thêm đúng một gạch đầu dòng mới, ngay sau dòng
"Chỉ NÊU DỮ KIỆN..."; mọi dòng khác giữ nguyên y hệt):

```python
GATHER_ERP_PROMPT = """Bạn là bộ phận THU THẬP DỮ KIỆN ERP. Nhiệm vụ duy nhất: dùng các tool đọc Odoo để lấy ra những dữ kiện liên quan đến câu hỏi của người dùng.

Quy tắc:
- Chỉ NÊU DỮ KIỆN, dạng gạch đầu dòng ngắn (mã đơn, ngày, số lượng, trạng thái, tên khách, tên sản phẩm...).
- Câu hỏi cần NGÀY (xác nhận, đặt hàng, giao hàng) hoặc TRẠNG THÁI GIAO của MỘT đơn bán cụ thể: dùng `list_sale_orders` (lọc theo tên khách hoặc điều kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG có ngày hay trạng thái giao).
- TUYỆT ĐỐI KHÔNG kết luận, không phán quyết câu hỏi của người dùng. Một bộ phận khác sẽ làm việc đó.
- KHÔNG viện dẫn chính sách/quy định/tài liệu nội bộ — bạn không có tài liệu trong tay, và một bộ phận khác đang lo phần đó.
- CHỈ dùng dữ kiện do tool trả về. Tuyệt đối không bịa số liệu.
- Nếu không lấy được dữ kiện nào liên quan, trả lời đúng một câu: Không tìm được dữ kiện ERP liên quan.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

- [ ] **Step 3: Chạy full test đơn vị — xác nhận không hồi quy**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Kỳ vọng: xanh, cùng số lượng test như trước (không có test nào assert
NGUYÊN VĂN nội dung `GATHER_ERP_PROMPT` cũ — nếu có test nào FAIL vì lý do
này, đọc kỹ và sửa test đó để khớp nội dung mới, KHÔNG bỏ quy tắc mới đi để
né test).

Nếu chạy `tests/rag/` làm đổi 2 file fixture nhị phân
(`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`), khôi phục:
`git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`.

- [ ] **Step 4: Chạy lại `--set gather` THẬT — xác nhận đã sửa**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

**Kỳ vọng: CẢ HAI case `sla_giao_hang` và `chinh_sach_hoan_hang` PASS** (không
còn trong `fails`, hoặc nếu còn thì `tool_recall_ok: true` — nghĩa là
`gather_erp` đã gọi `list_sale_orders`).

Nếu MỘT trong hai vẫn FAIL: đọc chi tiết `called`/`erp_facts` của case đó.
Nếu `list_sale_orders` ĐÃ được gọi nhưng `fact_coverage_ok: false` (gọi
đúng tool nhưng không truyền đạt đủ ngày trong `erp_facts` cuối cùng — có
thể do `verify_erp_grounding` cắt nhầm, giống cơ chế SP-2c đã quan sát ở
nhánh `policy`), ghi nhận đây là một lớp vấn đề KHÁC (không phải chọn sai
tool nữa) và báo cáo DONE_WITH_CONCERNS thay vì tự ý sửa thêm — đây là phát
hiện mới ngoài phạm vi plan này, cần quyết định riêng.

- [ ] **Step 5: Nối phần Task 2 vào file report**

Nối vào `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`:

```markdown
## Bước 2 — xác nhận đã sửa (SAU khi sửa prompt)

Chạy `jobs run eval-gate --set gather`, cùng model, SAU khi sửa
`GATHER_ERP_PROMPT`.

- `tool_recall`: `<số>` (Bước 1: `<số>`)
- `fact_coverage`: `<số>` (Bước 1: `<số>`)
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`
- Case `sla_giao_hang`: `<PASS | vẫn FAIL, nêu chi tiết called/erp_facts>`
- Case `chinh_sach_hoan_hang`: `<PASS | vẫn FAIL, nêu chi tiết called/erp_facts>`
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md
git commit -m "fix(agents): GATHER_ERP_PROMPT — chỉ rõ dùng list_sale_orders cho câu hỏi cần ngày/trạng thái giao"
```

---

## Task 3: Đo `multi_source` thật, chạy full suite, chốt báo cáo

**Không sửa code thêm** (trừ khi Task 2 Step 4 phát hiện vấn đề tầng
`verify_erp_grounding` — nếu vậy, mục này chỉ ĐO và GHI NHẬN, không tự sửa).

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`
  (nối thêm, chốt kết luận cuối)

**Interfaces:**
- Consumes: kết quả Task 1, Task 2.
- Produces: số đo `multi_source` SAU, kết luận cuối cùng của cả plan.

- [ ] **Step 1: Chạy `--set multi_source` thật**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Ghi lại: verdict, `both_source_coverage`, `citation_validity`,
`fabricated_number`, `lat_p50`/`lat_p95`, chi tiết `fails` (nếu còn), log
gốc.

**So sánh với TRƯỚC đã biết** (SP-2b's report, `both_source_coverage = 0.75`,
2 ca fail: `sla_giao_hang`, `chinh_sach_hoan_hang` — đúng 2 câu hỏi plan này
nhắm tới). Không cần đo lại "TRƯỚC" — số đó đã có sẵn, ổn định, chưa có gì
đổi `multi_source`/`fuse_answer` kể từ SP-2b Task 11.

- [ ] **Step 2: Chạy full suite cả 3 chế độ**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
.venv/Scripts/python.exe -m pytest -m integration -q
```

Sau mỗi lượt, nếu 2 file fixture nhị phân bị đổi, khôi phục:
`git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`.

Ghi lại số test passed mỗi chế độ.

- [ ] **Step 3: Nối kết luận cuối vào report**

Nối vào file report:

```markdown
## Bước 3 — multi_source thật (thước đo cuối cùng)

- verdict: `<PASS|FAIL>`
- `both_source_coverage`: `<số>` (TRƯỚC, SP-2b report: `0.75`)
- `citation_validity`: `<số>`
- `fabricated_number`: `<số>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`
- 2 ca mục tiêu (`sla_giao_hang`/S00042, `chinh_sach_hoan_hang`/S00042):
  `<còn trong fails hay đã hết>`

## Xác minh test

- Unit-only: `<N passed>`
- Integration: `<N passed>`

## Kết luận

`<Đối chiếu §5 spec "Xong nghĩa là", từng điều một dòng đạt/không đạt kèm
bằng chứng. Nói thẳng nếu both_source_coverage KHÔNG lên 1.0 dù 2 ca mục
tiêu đã hết — 8 ca của multi_source có thể còn ca khác chưa từng xuất hiện
trong log trước đây; không suy diễn xa hơn số đo cho phép.>`
```

Thay `<...>` bằng nội dung thật.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md
git commit -m "docs: chốt báo cáo sửa gather_erp tool-selection — số đo multi_source SAU"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| §2 sửa GATHER_ERP_PROMPT | 2 |
| §3 sửa 2 case GATHER_CASES | 1 |
| §4 trình tự TRƯỚC-phải-FAIL, dừng nếu không FAIL | 1 (Step 4 quyết định BLOCKED hay tiếp tục), Task 2 chỉ chạy khi Task 1 không BLOCKED |
| §5 điều 1-6 "xong nghĩa là" | 1, 2, 3 (Task 3 Step 3 đối chiếu trực tiếp) |
| Ngoài phạm vi (không sửa graph.py/fanout.py/state.py/mô tả tool dùng chung) | Global Constraints, không task nào đụng các file đó |
| Phụ lục A (comment tại chỗ) | 1 (comment case), 2 (comment ngầm trong chính quy tắc prompt mới — tự giải thích lý do) |

**Điểm khác biệt cố ý so với mọi plan trước trong dự án này:** Task 1 có
NHÁNH RẼ tường minh (BLOCKED nếu không tái hiện được FAIL) thay vì chỉ có
đường DONE thẳng — vì bản chất bước này là kiểm tra giả thuyết trước khi
tiêu tiền sửa, không phải triển khai một tính năng đã biết chắc cần làm.
