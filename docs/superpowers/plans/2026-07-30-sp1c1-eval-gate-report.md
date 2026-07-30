# SP-1C1 Task 7 — Báo cáo chạy cổng M3 thật

**Ngày chạy:** 2026-07-30, 14:15:41 (giờ bắt đầu job, `logs/jobs/eval-gate-20260730T141541.json`).
**Lệnh:** `cd backend && python -m jobs run eval-gate --set all` (159 ca, model ghim theo `chain_for(role)[0]`, nhịp `(60/rpm)*1.2`).

## Kết quả tổng: **FAIL** (exit code 1)

Đây là **kết quả hợp lệ của cổng**, không phải lỗi hạ tầng và không phải khiếm
khuyết của kế hoạch SP-1C1 (spec §4: *"Gate đỏ nghĩa là gì: C2 không được bắt
đầu. Điều tra, sửa model/prompt, chạy lại."*). **C2 KHÔNG được mở khoá** — xem
phần "Bước tiếp theo" bên dưới.

## Bảng trước/sau — 7 bộ (159 ca)

| Bộ | Model ghim | Số đo | Baseline (qwen3:8b) | Gate |
|---|---|---|---|---|
| intent | `gemma-4-26b` | acc = **0.944** (51/54) | acc = 0.870 | ✅ PASS |
| confirm | `groq-gpt-oss-20b` | acc = **0.708** (17/24) | acc = 0.625 | ✅ PASS |
| chitchat | `gemma-4-31b` | violations = **0** (tuyệt đối, không baseline) | — | ✅ PASS |
| planner | `gemini-3.5-flash-lite` | tool_acc = **1.000**, dangerous_misroute = 0 | tool_acc = 1.000 | ✅ PASS |
| read | `gemini-3.5-flash-lite` | tool_acc = **1.000**, fabricated_param = 0 | tool_acc = 1.000 | ✅ PASS |
| synthesis | `gemini-3.1-flash-lite` | grounded_acc = **0.917** (11/12), false_answer = 0 | grounded_acc = 1.000 | ❌ **FAIL** |
| multi_source | `gemini-3.1-flash-lite` | citation_validity = 1.0, both_source_coverage = 0.75, **fabricated_number = 1** | both_source_coverage = 0.75, fabricated_number = 1 | ❌ **FAIL** |

Nguồn số liệu: `logs/jobs/eval-gate-20260730T141541.json` (JSON đầy đủ, gitignored,
không commit — số liệu được chép nguyên vào bảng trên từ trường `detail` của
file này, không ước lượng).

**Chú thích cột Baseline của `multi_source`:** khác với các bộ khác (baseline
là ngưỡng "≥"), `fabricated_number` trong `_gate()` là điều kiện TUYỆT ĐỐI
`== 0` áp lên kết quả đang đo, không so sánh với baseline (xem
`jobs/eval_gate.py` dòng ~61-67). Cột Baseline ở đây chỉ để đối chiếu: baseline
qwen3:8b cũng có `fabricated_number = 1` (cùng 1 ca, cùng lý do — xem chi tiết
dưới), nên đây KHÔNG phải hồi quy so với baseline, dù bản thân `_gate()` vẫn đỏ
cơ học vì không có ngoại lệ cho giới hạn đã biết.

## Chi tiết 2 bộ FAIL

### `synthesis` — 1/12 ca không khớp gate

Ca duy nhất fail:

- Câu hỏi: "Hàng giảm giá có được hoàn trả không?"
- Kỳ vọng (khớp substring, đã chuẩn hoá): `"không được hoàn trả"`
- Model trả lời: *"Rất tiếc, các sản phẩm hàng giảm giá không được áp dụng
  chính sách hoàn trả. NGUỒN_DÙNG: 4"*

`false_answer = False`, `false_insufficient = False` — model **không bịa,
không né tránh**, nội dung đúng nghĩa (hàng giảm giá không được hoàn trả).
Nhưng `eval_synthesis()` chấm bằng substring khớp nguyên văn
(`_norm(expect) in _norm(body)`), và cụm "không được áp dụng chính sách hoàn
trả" không chứa nguyên văn "không được hoàn trả" (model diễn giải lại bằng từ
khác thay vì lặp đúng cụm kỳ vọng). Đây là **giới hạn của scanner** (quá cứng
với diễn giải hợp lệ), không phải model bịa hay né — nhưng **đây là phát hiện
MỚI**, khác với case đã biết ở `multi_source` (xem dưới): scanner
`eval_synthesis()` **chưa được điều tra hay duyệt sửa** trong SP-1C1 — cần
người quyết định hướng xử lý (nới lỏng cách so khớp, hay coi đây là giới hạn
chấp nhận được của phép đo).

### `multi_source` — đúng như dự đoán từ Task 6: gặp lại giới hạn số học ngày-tháng

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
xứng, không ưu ái bên nào"* — dự đoán này **đã xảy ra đúng như vậy** ở lượt
chạy thật này, xác nhận quyết định chấp nhận ở Task 6 là hợp lý và nhất quán.

`both_source_coverage = 0.75` khớp chính xác baseline (0.75) — 2/8 ca model
chọn trả lời "cần thêm thông tin" thay vì kết hợp cả ERP+RAG, giống hệt hành
vi của baseline qwen3:8b trên cùng 2 ca đó.

## Ghi chú vận hành

- Lượt chạy `--set all` đầu tiên (trong một phiên trước) bị hạ tầng bên ngoài
  (hết hạn mức phiên agent) giết giữa chừng ở ca 10/16 của `chitchat` — không
  liên quan tới code hay hạ tầng SP-1C1. Chạy lại từ đầu (theo đúng thiết kế
  `jobs/resilience.py`: checkpoint là bằng chứng crash, không phải cơ chế
  resume) cho kết quả trên.
- Ứng dụng thật (`python -m jobs run eval-gate`) **không tự nạp `.env`** —
  khác với 2 lệnh kiểm tra thủ công ở Bước 1-2 (dùng `load_dotenv()` riêng).
  Phải `export` biến môi trường vào shell trước khi chạy CLI thật
  (`set -a && source ../.env && set +a`). Đáng ghi chú cho lần chạy sau.
- Thấy 2 dòng cảnh báo thoáng qua "`Event loop is closed` — nghỉ 15s" cho
  `gemini-3.5-flash-lite`/`gemini-3.1-flash-lite` ngay đầu log, trước khi các
  bộ dùng đúng 2 model này (`planner`/`read`/`synthesis`) chạy và cho kết quả
  bình thường sau đó — không thấy ảnh hưởng tới số đo cuối (cơ chế cooldown
  của router tự phục hồi). Không điều tra sâu hơn vì không có bằng chứng nó
  làm sai lệch kết quả đã ghi.

## Test suite — 3 chế độ, không hồi quy

- Mode 1 (mặc định, không mạng/Postgres): `pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors` → **851 passed, 4 skipped, 0 failed**.
- Mode 2 (`-m integration`): `pytest tests/ -q -m integration` → **27 passed, 0 failed** (khớp đúng số dự kiến trong plan).
- Mode 3 (`-m live`): không chạy riêng — chính lượt gate `--set all` ở trên LÀ phép đo `live` thật.
- 2 fixture nhị phân `tests/rag/fixtures/{bang_gia.xlsx,policy.docx}` bị re-serialize (tác dụng phụ đã biết) — đã `git checkout --` khôi phục trước khi commit.

## Bước tiếp theo

Theo spec §4/§6: **gate đỏ → C2 (main.py + Langfuse) KHÔNG được bắt đầu.**
Cần người quyết định hướng xử lý cho 2 phát hiện trên trước khi chạy lại:

1. `multi_source`: giới hạn đã biết, đối xứng, đã chấp nhận từ Task 6 — có
   thể không cần hành động thêm (bảng số liệu này chính là bằng chứng cho
   quyết định đó), nhưng **_gate() vẫn đỏ cơ học** vì công thức giữ nguyên văn
   không có ngoại lệ cho giới hạn đã biết.
2. `synthesis`: phát hiện MỚI — cách so khớp bằng substring nguyên văn quá
   cứng với diễn giải hợp lệ. Cần quyết định: nới lỏng cách so khớp
   (`eval_synthesis()`), hay chấp nhận như một giới hạn khác của phép đo,
   tương tự cách Task 6 đã xử lý `multi_source`.
