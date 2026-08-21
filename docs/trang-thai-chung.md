# Trạng thái chung — hai phiên làm việc song song

Cập nhật lần cuối: **2026-08-21**.

## Cách dùng tệp này

Hai phiên Claude Code cùng làm trên repo này (một giữ **RAG/truy xuất**, một giữ
**ký ức người dùng**). Tệp này là chỗ **duy nhất** để biết trạng thái chung mà
không phải đọc lại hội thoại của nhau.

Quy ước:

- **Đóng một mục thì tự xoá nó khỏi đây**, kèm commit đã đóng nó. Đừng để mục
  chết nằm lại — một danh sách không ai dọn sẽ thành danh sách không ai đọc.
- **Không chép nội dung spec vào đây.** Chỉ ghi *cái gì đang treo* và *ai giữ*,
  rồi trỏ tới spec. Tệp này phải đọc hết trong một phút.
- **Không dùng tệp này thay cho test.** Ràng buộc giữa hai vùng phải cưỡng chế
  bằng test, không bằng dòng chữ ở đây. Bằng chứng: ràng buộc
  `render_memory_block` được `tests/evals/test_memory_presets.py` gác, nên không
  cần ai nhắn ai.
- **Trước khi sửa file thuộc vùng người khác**, xem mục "Ai giữ vùng nào". Đụng
  file phiên kia đang mở là cách đã từng gây sự cố.

## Đang chờ chủ dự án quyết

| # | mục | vùng | ghi chú |
|---|---|---|---|

## Việc đang treo

| # | mục | ai giữ | chặn bởi |
|---|---|---|---|
| 3 | Tham chiếu thứ tự trong câu nối tiếp ("loại đầu tiên", "cái sau") | chưa ai | bài toán mới, chưa mở phạm vi |
| 6 | `gemma-4-26b` (rpd 14 400) — model DUY NHẤT đủ gánh cả hệ một mình, chưa đo nên chưa cho chọn | chưa ai | **căn cứ sau 2026-08-21**: mục 8 cho thấy chuỗi dự phòng có thể cạn SẠCH trên đường ERP thật (`ChainExhausted`). Không trích số `llm_usage` làm căn cứ hạn mức — xem mục 9 |
| 7 | **Không có dự phòng theo KHOÁ API** — `providers.ENV_KEYS` chỉ một biến mỗi upstream, nên cạn hạn mức ngày của Google là cạn cho cả hệ | chưa ai | chờ chủ dự án quyết hướng |
| 8 | ⚠️ **Chọn 3.5 cho chuỗi NGẮN HƠN chọn 3.1** — `prefer` chỉ chèn lên đầu, nên model vốn đã đứng đầu thì không thêm mắt xích nào. Gặp thật: hỏi tồn kho khi chọn 3.5 → `ChainExhausted` dù 3.1 còn hạn mức | chưa ai | phạm vi mới, chờ quyết (spec `2026-08-21-model-picker.md` §8.5) |
| 9 | ⚠️ **Bộ test tích hợp XOÁ SỔ NGÂN SÁCH `llm_usage`** — `tests/llm/test_store_postgres.py::test_thieu_migration_thi_nem_RuntimeError_ro_rang` chạy `DROP TABLE` trên chính `DATABASE_URL` thật rồi tạo lại bảng RỖNG | chưa ai | phạm vi mới. Hệ quả: sau mỗi lượt `pytest -m integration`, ledger tưởng chưa dùng gì và mọi chẩn đoán hạn mức đọc sau đó đều sai |
| 10 | ⚠️ **`or-nemotron` CHẾT** — 16 lần gọi, **0 lần thành công**, luôn 404 "Provider returned error / Nvidia". Nó là mắt xích CUỐI của `read`/`planner`/`synthesis` ⇒ ba chuỗi đó ngắn hơn vẻ ngoài một mắt xích | chưa ai | phạm vi mới; thành phần chết im lặng thứ BA của dự án (sau chân sparse và reranker) |
| 11 | `e2e-skill-warehouse` còn **2/5 kịch bản chưa nghiệm thu** (`no_po_tool_leak`, `refusal`) và `e2e-skill-delivery` còn 1 (`refusal`) | chưa ai | **cạn hạn mức NGÀY** (429 `PerDayPerProjectPerModel`). Chạy lại khi hạn mức reset — bản vá chẩn đoán đã sẵn, lượt sau sẽ in nguyên văn câu trả lời |

## Ai giữ vùng nào

| vùng | tệp chính |
|---|---|
| **RAG / truy xuất** | `src/rag/**`, `src/agents/synthesis.py`, `src/agents/history.py`, `evals/{retrieval,synthesis_live,multiturn,memory_presets}*` |
| **Ký ức người dùng** | `src/agents/user_memory.py`, `migrations/004_user_memory.sql`, `evals/cases.py`, phần `eval_memory` của `run_eval.py` |
| **Chung — hỏi trước khi sửa** | `src/agents/nodes.py`, `src/agents/fanout.py`, `src/agents/prompts.py`, `evals/run_eval.py` |

Bốn tệp "chung" là nơi cả hai lần merge vừa rồi đều xung đột. Sửa được, chỉ cần
báo trước.

## Đã đo — ĐỪNG bàn lại nếu không có số mới

| kết luận | chứng cứ |
|---|---|
| Ký ức **không** vào prompt tổng hợp RAG — cả ba loại fact đều không dương | spec `2026-08-20-memory-synthesis-eval.md` §3, §7 |
| Fact mâu thuẫn tài liệu **không** đè được luật | cùng spec §3, chân `conflict` |
| Khối ký ức **không** làm tịt marker `GHI_NHỚ:`/`QUÊN:` | cùng spec §8, 15/15 |
| Trần số chunk mỗi mục: **vô tác dụng** | tag `parked/rag-section-cap` |
| Ngữ cảnh hội thoại cho `synthesize()`: **không chữa được gì** | spec `2026-08-20-rag-roadmap-revision.md` |
| Cross-encoder là **lá phiếu**, không phải kẻ ghi đè | docstring `retrieve.rerank()` |
| Ký ức tắt việc chủ động đề nghị ghi trên `fuse_answer` — **ĐÃ CHẤP NHẬN**, không sửa | spec §13, §15 |
| Ký ức KHÔNG làm tăng bịa hành động trên `chitchat` (violations = 0 mọi chân) | spec §17 |
| Cộng dồn 5 fact KHÔNG hỏng chọn tool / trích dẫn / độ khớp marker | spec §13 |
| Lọc ký ức theo LOẠI fact: bị bác HAI lần, trên hai bộ chỉ số khác nhau | spec §12.1, §15 |

## CHƯA đo — danh sách "ta chưa biết"

- Khối ký ức trên `FUSE_PROMPT` (mục 1 ở trên).
- **Mọi phép đo ký ức tới nay đều dùng đúng MỘT fact.** Người dùng thật đang có
  5. Không có gì cho biết nó bắt đầu hại ở đâu.
- Thứ hạng bên trong top-6 có đổi câu trả lời cuối không (docstring `rerank()`).

## Bẫy vận hành

- **Hạn mức LLM**: tính đến tối 2026-08-20, **cả khoá chính lẫn khoá dự phòng
  đều cạn hạn mức NGÀY**.
- `--pace 4.5` **bắt buộc** cho mọi bộ eval gọi LLM (free tier 15 lượt/phút).
- Lỗi `cooldown` có **hai** nguyên nhân. Phân biệt bằng phép đo: chạy lại ở
  `--pace 9` (~6,7 lượt/phút) mà **vẫn** cooldown ⇒ cạn hạn mức ngày, đổi khoá;
  hết cooldown ⇒ chỉ là trần phút.
- **`llm_usage` KHÔNG dùng để chẩn đoán hạn mức** — nó chỉ ghi lượt *thành
  công*. Đã gặp: Google báo cạn 500 trong khi sổ ghi 22.
- **DB RAG thật**: `postgresql://admin:thay_bang_mat_khau@localhost:5434/ai_assistant`
  (container `youdoo-postgres`).
- Đụng `chunking`/`parse` thì phải `DELETE FROM rag_documents` rồi ingest lại
  (~3,5 phút). Không xoá thì content-hash bỏ qua toàn bộ 17 tệp.

## Giới hạn đã chấp nhận — có đo, quyết không sửa

| giới hạn | số đo | vì sao không sửa |
|---|---|---|
| Hai key cho cùng một fact (`hien_thi_ma_don` + `always_show_order_code`) | 5 fact = 10% `SYSTEM_PROMPT`; cộng dồn không hỏng chỉ số nào (spec §13) | Sửa cần phân loại/gộp lúc ghi — cơ chế đã bị số đo bác hai lần. **Cách rẻ hơn: người dùng tự bảo trợ lý "quên `always_show_order_code`"** — nó là dữ liệu, không phải code. Nguy cơ thật là sửa một cái mà cái kia vẫn nói ngược; chưa xảy ra. |
| Không có trần số fact | ở 50 fact khối bằng 130% `CHITCHAT_PROMPT`, nhưng người dùng thật có 5 | Đặt trần bây giờ là dựng cơ chế cho một rủi ro chưa đo được. Đo lại khi có người vượt ~20 fact. |
| `proposed_rate = 0` trên `fuse_answer` | 0,75 → 0,00 tất định 3 lượt | Ba hướng khả dĩ: một đắt, một vô dụng, một nguy hiểm (spec §16). |
| Mặc định là **3.1** dù số nghiêng 3.5 | acc sau vá: 3.1 = 0,9630 · 0,9630; 3.5 = 0,9630 · 0,9815. Trễ trung vị 2000ms vs 951ms | **Chủ dự án chốt 2026-08-21: giữ 3.1.** Số chỉ cho thấy 3.5 *ngang*, không cho thấy nó *hơn*; đổi mặc định để lấy tốc độ là mua bằng rủi ro định tuyến im lặng (spec §4). Ai cần nhanh thì đổi ở dropdown — đúng việc tính năng này sinh ra để làm. Mở lại **chỉ khi** có số mới cho thấy 3.5 HƠN. |
