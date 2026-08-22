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
| 14 | 🔴 **`/v1` KHÔNG xác thực** — bind `0.0.0.0:8002`, quyền suy DUY NHẤT từ header `x-openwebui-user-id`. Ai trong LAN gửi header của admin là mở khoá 33 tool ghi Odoo | chưa ai | **chờ chủ dự án quyết cơ chế token**; đổi `BACKEND_HOST=127.0.0.1` phải kiểm trước vì Open WebUI chạy trong Docker |
| 15 | Guardrail fail-open: **nửa CHẨN ĐOÁN đã vá** (log + đánh dấu "chưa xác minh" ra người dùng). Nửa còn lại — **tách ví hạn mức** cho verifier — chưa làm | chưa ai | cần quyết: dùng model/ví riêng cho verifier, hay chấp nhận nó tắt khi cạn |
| 16 | 🔴 **Không quản lý cửa sổ ngữ cảnh** — `_filter_messages` chuyển nguyên lịch sử, không cắt/tóm tắt/đếm token. Hội thoại dài ⇒ mọi mắt xích cùng lỗi ⇒ đoạn chat chết vĩnh viễn | chưa ai | phạm vi mới |
| 17 | Vệt kiểm toán ghi `caller = mcp-odoo/<vai>` (tên tiến trình), **không có user HTTP, không có `args_digest`** ⇒ không truy vết được sau sự cố | chưa ai | đi cùng mục 14 |
| 18 | Xác nhận quá hạn (TTL 300s) **hủy trong im lặng**; `.env.example` để `ODOO_USERNAME=admin`; 4 tài khoản Odoo chung **một** mật khẩu | chưa ai | ba việc nhỏ, gom một đợt |
| 19 | RAG: **không có Query Transformation**; metadata thiếu `department`/`access_level` ⇒ **RBAC rách ở tầng RAG** (vai kho đọc được tài liệu kế toán) | chưa ai | phạm vi mới |
| 20 | **Không có CI** (`.github/` không tồn tại) — 2004 test + `eval_gate` đều phải gõ tay | chưa ai | |
| 21 | UX: **không có streaming** (màn hình trắng 5–20s), **không có Undo**, dữ liệu hiển thị thô (`sale`/`draft`), thiếu vai Bán hàng & Mua hàng trong `RoleCfg` | chưa ai | nhóm P1 của bản kiểm toán |

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
| `groq-gpt-oss-120b` đã đo trên BA vai: `confirm` 0,8333 · `intent` 0,9630 (bằng Gemini) · `chitchat` violations=0 | spec `2026-08-22-muc-9-12-13.md` |
| Cổng xác nhận ghi hiện **args, KHÔNG hiện tên tool** — hai bất biến nay cùng đúng | cùng spec; `tests/agents/test_confirm_khong_lo_ten_tool.py` khoá hai chiều |
| Nhịp eval suy từ **CẢ rpm LẪN tpm**, và theo model ĐANG GHIM | cùng spec; Gemini 4,8s (không đổi), Groq 2,4 → 9,0s |
| Catalog gom còn **4 model**, một hình dạng chuỗi cho mọi vai | spec `2026-08-21-catalog-consolidation.md` |
| `gemma-4-26b` THUA mọi ứng viên trên bộ `confirm` (0,7917 · 6062ms) — đã xoá | cùng spec §4; bảng 5 model đo cùng phiên |
| Cổng xác nhận ghi: `gemini-3.5-flash-lite` 0,9583 · `3.1` 0,9167 · `120b` 0,8333 — false_confirm = 0 ở CẢ NĂM | cùng spec §4 |
| Xoay khoá API: xoay BÊN TRONG một mắt xích, KHÔNG thành mắt xích mới — bất biến #1 vẫn nguyên | spec `2026-08-21-api-key-rotation.md` §2, nghiệm thu sống §4 |
| Chỉ xoay khoá khi **429**; lỗi khác (404/5xx) không xoay | cùng spec §2.1; `or-nemotron` 404 16/16 lượt là ca phản chứng |
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

- ⚠️ **Cạn hạn mức gây SUY GIẢM CHẤT LƯỢNG, không chỉ gây lỗi.** Lượt gọi tụt xuống
  mắt xích yếu hơn; model yếu vẫn trả lời trôi chảy nhưng bỏ chỉ dẫn trong SOP —
  KHÔNG phân biệt được với lỗi hành vi thật. Đo được 2026-08-21: `no_po_tool_leak`
  đỏ 2 lượt liền, đổi sang khoá còn hạn mức thì PASS ngay. **Mọi kết quả eval/nghiệm
  thu chạy lúc hạn mức suy giảm đều không đáng tin.** Job e2e nay ghi
  `RESULT_JSON["models"]` để phân biệt được hai thứ đó.
- **Hạn mức NGÀY của Google là cửa sổ TRƯỢT 24h**, không phải mốc nửa đêm: chỗ trống
  nhỏ giọt quay lại. Probe trực tiếp thấy `3.1-flash-lite` trả 200 trên chính khoá vừa
  báo `PerDayPerProjectPerModel` — đủ vài lượt, KHÔNG đủ một job 5 kịch bản.
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
