# SP-1C1 Task 7 — Báo cáo chạy cổng M3 thật

Tài liệu này có 2 lượt chạy: **Lượt 1** (verdict FAIL, 5/7 PASS) phát hiện ra
phát hiện mới ở `synthesis`; sau khi sửa scanner (xem "Fix đi kèm" bên dưới)
và merge, **Lượt 2** (verdict FAIL, 6/7 PASS) xác nhận fix hoạt động đúng.
Giữ lại cả hai để có đầy đủ bằng chứng xuất xứ.

## Lượt 2 (2026-07-30, sau khi sửa scanner synthesis) — KẾT QUẢ HIỆN HÀNH

**Ngày chạy:** 2026-07-30, `started_at` ~16:16:33, ghi kết quả tại
`logs/jobs/eval-gate-20260730T163507.json` (gitignored, không commit).
**Lệnh:** `cd backend && set -a && source ../.env && set +a && python -m jobs run eval-gate --set all`.

### Kết quả tổng: **FAIL** (exit code 1) — nhưng 6/7 bộ PASS, tăng từ 5/7

| Bộ | Model ghim | Số đo | Baseline (qwen3:8b) | Gate |
|---|---|---|---|---|
| intent | `gemma-4-26b` | acc = **0.944** (51/54) | acc = 0.870 | ✅ PASS |
| confirm | `groq-gpt-oss-20b` | acc = **0.708** (17/24) | acc = 0.625 | ✅ PASS |
| chitchat | `gemma-4-31b` | violations = **0** (tuyệt đối, không baseline) | — | ✅ PASS |
| planner | `gemini-3.5-flash-lite` | tool_acc = **1.000**, dangerous_misroute = 0 | tool_acc = 1.000 | ✅ PASS |
| read | `gemini-3.5-flash-lite` | tool_acc = **1.000**, fabricated_param = 0 | tool_acc = 1.000 | ✅ PASS |
| synthesis | `gemini-3.1-flash-lite` | grounded_acc = **1.000** (12/12), false_answer = 0 | grounded_acc = 1.000 | ✅ **PASS** (đã sửa) |
| multi_source | `gemini-3.1-flash-lite` | citation_validity = 1.0, both_source_coverage = 0.75, **fabricated_number = 1** | both_source_coverage = 0.75, fabricated_number = 1 | ❌ FAIL |

**`synthesis` giờ PASS** — xác nhận fix scanner (danh sách phương án khớp
nguyên văn, xem "Fix đi kèm" bên dưới) hoạt động đúng trên chính model/case
thật đã gây fail ở Lượt 1: model trả lời y hệt Lượt 1 ("...không được áp
dụng chính sách hoàn trả..."), và giờ khớp với phương án thứ hai đã ghi
nhận trong `SYNTHESIS_CASES`.

**`multi_source` vẫn FAIL — y hệt Lượt 1, không phải phát hiện mới.** Case
fail duy nhất (`chinh_sach_thanh_toan`/INV-2026-00020) có response **byte-
for-byte giống hệt Lượt 1**, cùng `fabricated: ["08", "31"]`,
`both_source_coverage=0.75` khớp đúng baseline. Đây chính xác là giới hạn số
học ngày-tháng đã ghi nhận và chấp nhận ở Task 6 (xem chi tiết ở phần Lượt 1
bên dưới) — không phải điều gì mới cần điều tra thêm.

### Test suite (chạy lại sau merge, trên `main`)

- Mode 1: `pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors` → **858 passed, 4 skipped, 0 failed**.
- Mode 2: `pytest tests/ -q -m integration` → **27 passed, 0 failed**.
- 2 fixture nhị phân `tests/rag/fixtures/{bang_gia.xlsx,policy.docx}` bị chạm — đã khôi phục trước khi tiếp tục.

### Fix đi kèm giữa Lượt 1 và Lượt 2

`backend/evals/run_eval.py::eval_synthesis()`'s cách so khớp `grounded_acc`
được sửa (nhánh riêng `sp1c1-synthesis-fix`, đã merge vào `main`). Qua
**3 vòng review độc lập**:

- Vòng 1 thử một heuristic chung "khớp theo thứ tự từ" — bị bác bỏ vì lọt
  2 loại câu trả lời sai (số liệu khác, đảo cực tính không giới hạn).
- Vòng 2 thêm rào (loại expect có số/ngắn, giới hạn khoảng chèn) — vẫn bị
  bác bỏ vì review tìm được 6 câu phản ví dụ mới lọt qua rào, cộng phát
  hiện `tạm dừng xử lý` là case thứ hai cũng "đủ điều kiện" bị lọt.
- Vòng 3: bỏ hẳn heuristic mờ, thay bằng **danh sách phương án khớp NGUYÊN
  VĂN** — `expect` trong `SYNTHESIS_CASES` có thể là tuple nhiều chuỗi,
  mỗi chuỗi là một diễn giải THẬT đã quan sát được, không suy luận ngữ
  nghĩa. Cả 9 phản ví dụ từ 2 vòng trước đều bị chặn đúng — xác nhận qua
  review độc lập lần 3, không có Critical nào còn lại.

Baseline `baseline-qwen3-8b-synthesis.json` (grounded_acc=1.0, fails=[])
KHÔNG cần chấm lại — phương án nguyên văn cũ vẫn là phần tử đầu của tuple,
nên baseline vẫn khớp y hệt trước.

### Bước tiếp theo — quyết định về `multi_source`

`_gate()`'s điều kiện `fabricated_number == 0` cho `multi_source` là **tuyệt
đối**, không có ngoại lệ cho giới hạn đã biết/chấp nhận — nên gate cơ học
vẫn đỏ dù bản chất rủi ro đã được hiểu rõ, đối xứng (không thiên vị model
nào), và không phải hồi quy so với baseline. Đây là điểm nghẽn DUY NHẤT còn
lại để mở khoá C2. Cần người quyết định hướng xử lý — vd:

1. Chấp nhận cổng đỏ vĩnh viễn cho case này, và mở C2 bằng quyết định thủ
   công có ghi chép (tương tự cách Task 6/7 đã ghi chép quyết định chấp
   nhận), thay vì đợi `_gate()` tự xanh — cần cân nhắc kỹ vì đây là thay
   đổi CHÍNH SÁCH (không sửa code `_gate()`).
2. Sửa `eval_multi_source`/`cases.py` để loại ĐÚNG case ngày-tháng này khỏi
   phép đo (vd đổi câu hỏi test sang dạng không đòi tính toán ngày), thay vì
   cố "sửa" scanner chấp nhận số học ngày tháng nói chung (rủi ro over-
   engineering, học từ 3 vòng review ở `synthesis`).
3. Giữ nguyên, không mở C2 — chờ quyết định khác.

---

## Lượt 1 (2026-07-30, trước khi sửa scanner synthesis) — LỊCH SỬ

**Ngày chạy:** `started_at: 2026-07-30T13:54:23` (14:15:41 trong tên file
`eval-gate-20260730T141541.json` là giờ GHI KẾT QUẢ, không phải giờ bắt
đầu — `registry.py`'s `write_result()` đóng dấu lúc job HOÀN TẤT).

### Kết quả tổng: FAIL (exit code 1), 5/7 PASS

| Bộ | Model ghim | Số đo | Baseline (qwen3:8b) | Gate |
|---|---|---|---|---|
| intent | `gemma-4-26b` | acc = **0.944** (51/54) | acc = 0.870 | ✅ PASS |
| confirm | `groq-gpt-oss-20b` | acc = **0.708** (17/24) | acc = 0.625 | ✅ PASS |
| chitchat | `gemma-4-31b` | violations = **0** (tuyệt đối, không baseline) | — | ✅ PASS |
| planner | `gemini-3.5-flash-lite` | tool_acc = **1.000**, dangerous_misroute = 0 | tool_acc = 1.000 | ✅ PASS |
| read | `gemini-3.5-flash-lite` | tool_acc = **1.000**, fabricated_param = 0 | tool_acc = 1.000 | ✅ PASS |
| synthesis | `gemini-3.1-flash-lite` | grounded_acc = **0.917** (11/12), false_answer = 0 | grounded_acc = 1.000 | ❌ FAIL (đã sửa ở Lượt 2) |
| multi_source | `gemini-3.1-flash-lite` | citation_validity = 1.0, both_source_coverage = 0.75, **fabricated_number = 1** | both_source_coverage = 0.75, fabricated_number = 1 | ❌ FAIL |

**Chú thích cột Baseline của `multi_source`:** khác với các bộ khác (baseline
là ngưỡng "≥"), `fabricated_number` trong `_gate()` là điều kiện TUYỆT ĐỐI
`== 0` áp lên kết quả đang đo, không so sánh với baseline. Cột Baseline ở
đây chỉ để đối chiếu: baseline qwen3:8b cũng có `fabricated_number = 1`
(cùng 1 ca, cùng lý do), nên đây KHÔNG phải hồi quy so với baseline.

### Chi tiết 2 bộ FAIL (Lượt 1)

#### `synthesis` — 1/12 ca không khớp gate (đã sửa, xem Lượt 2)

Ca duy nhất fail:

- Câu hỏi: "Hàng giảm giá có được hoàn trả không?"
- Kỳ vọng (khớp substring, đã chuẩn hoá): `"không được hoàn trả"`
- Model trả lời: *"Rất tiếc, các sản phẩm hàng giảm giá không được áp dụng
  chính sách hoàn trả. NGUỒN_DÙNG: 4"*

`false_answer = False`, `false_insufficient = False` — model **không bịa,
không né tránh**, nội dung đúng nghĩa. Nhưng `eval_synthesis()` chấm bằng
substring khớp nguyên văn, và cụm trả lời không chứa nguyên văn cụm kỳ
vọng (model diễn giải lại). Chạy lại riêng `--set synthesis` xác nhận ổn
định (cùng 1 case, response y hệt) — không phải nhiễu lấy mẫu. Đã sửa ở
fix đi kèm (xem Lượt 2).

#### `multi_source` — đúng như dự đoán từ Task 6: gặp lại giới hạn số học ngày-tháng

Ca duy nhất fail (trong 8 ca, 1 ca có `fabricated` khác rỗng):

- Chủ đề: `chinh_sach_thanh_toan`, hóa đơn INV/2026/00020
- Model trả lời: *"...thời hạn thanh toán mặc định là 30 ngày kể từ ngày xuất
  hóa đơn, hóa đơn này sẽ đến hạn thanh toán vào ngày 31/07/2026. Do đó, hóa
  đơn sẽ bắt đầu quá hạn từ ngày 01/08/2026."*
- `fabricated: ["08", "31"]`

Đây **chính xác là giới hạn đã ghi nhận và chấp nhận ở Task 6** (xem
`backend/evals/cases.py` dòng ~300-324, `original_fabricated_number: 4` →
`fabricated_number: 1` của baseline qwen3:8b): scanner không xác minh được số
học ngày tháng hợp lệ (01/07 + 30 ngày = 31/07; qua hạn từ 01/08), nên quy
oan là "bịa" dù model tính đúng từ dữ kiện có căn cứ trong tài liệu (Điều 3 —
30 ngày mặc định). Task 6 đã dự đoán rõ: *"nếu model cloud cũng gặp trường hợp
tương tự (tính ngày tháng), nó cũng có thể bị FAIL oan giống hệt — rủi ro đối
xứng, không ưu ái bên nào"* — dự đoán này **đã xảy ra đúng như vậy**, và lại
xảy ra LẦN NỮA giống hệt ở Lượt 2, càng xác nhận đây là giới hạn ổn định của
scanner, không phải nhiễu.

`both_source_coverage = 0.75` khớp chính xác baseline (0.75) — 2/8 ca model
chọn trả lời "cần thêm thông tin" thay vì kết hợp cả ERP+RAG, giống hệt hành
vi của baseline qwen3:8b trên cùng 2 ca đó.

### Ghi chú vận hành (Lượt 1)

- Lượt chạy `--set all` đầu tiên (trong một phiên trước) bị hạ tầng bên ngoài
  (hết hạn mức phiên agent) giết giữa chừng ở ca 10/16 của `chitchat` — không
  liên quan tới code hay hạ tầng SP-1C1. Chạy lại từ đầu (theo đúng thiết kế
  `jobs/resilience.py`: checkpoint là bằng chứng crash, không phải cơ chế
  resume) cho kết quả trên.
- Ứng dụng thật (`python -m jobs run eval-gate`) **không tự nạp `.env`** —
  khác với 2 lệnh kiểm tra thủ công ở Bước 1-2 (dùng `load_dotenv()` riêng).
  Phải `export` biến môi trường vào shell trước khi chạy CLI thật
  (`set -a && source ../.env && set +a`).
- Thấy 2 dòng cảnh báo thoáng qua "`Event loop is closed` — nghỉ 15s" ngay
  đầu log ở Lượt 1 — chẩn đoán đúng ở review toàn nhánh cuối cùng của SP-1C1:
  `Router`/client cache bị tái sử dụng qua nhiều `asyncio.run()` riêng biệt
  (mỗi bộ một event loop mới). Đã vá (reset `run_eval._router` giữa các bộ
  trong `jobs/eval_gate.py::run()`) — Lượt 2 không còn thấy cảnh báo này.

### Test suite (Lượt 1)

- Mode 1: **851 passed, 4 skipped, 0 failed**.
- Mode 2: **27 passed, 0 failed**.
