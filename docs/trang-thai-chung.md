# Trạng thái chung — hai phiên làm việc song song

Cập nhật lần cuối: **2026-08-23**.

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
| 15 | Guardrail fail-open: **nửa CHẨN ĐOÁN đã vá** (log + đánh dấu "chưa xác minh" ra người dùng). Nửa còn lại — **tách ví hạn mức** cho verifier — chưa làm | chưa ai | cần quyết: dùng model/ví riêng cho verifier, hay chấp nhận nó tắt khi cạn |
| 17b | ⚠️ **Đường ĐỌC không có vệt kiểm toán nào.** `erp_query/transport.py` gọi Odoo bằng `ServerProxy` riêng, không qua MCP ⇒ không qua `odoo()` ⇒ không `log_mcp_event`. Cả 35 tool MCP đều là tool GHI. Câu "ai đã đọc công nợ/bảng giá" hiện KHÔNG trả lời được | chưa ai | phát hiện khi đóng mục 17; là mục riêng, không phải phần mở rộng |
| 19 | RAG: **không có Query Transformation** | chưa ai | recall@20 = 1,0 ⇒ truy xuất không phải nút thắt |
| 19b | **RBAC tầng RAG — HOÃN CÓ ĐIỀU KIỆN.** Chỉ mở lại khi corpus có **nhiều tài liệu nội bộ**. Hôm nay: 8 tài liệu / 44 chunk nội bộ (98,6% corpus là PDF luật công khai) ⇒ chưa cần | hoãn 2026-08-22 | điều kiện mở lại, không phải "đã xong" — lỗ hổng vẫn còn, xem mục "đã đo" |
| 23 | ⚠️ **3 khoảng trống vai↔Odoo còn lại** (`update_quotation_lines` kho, `update_rfq_lines` kế toán, `find_my_activities`) — nên khai vào `KNOWN_ODOO_GAPS` kèm lý do đo được thay vì để script thoát mã 1 mãi. `create_vendor` ĐÃ ĐÓNG 2026-08-23 | chưa ai | spec `2026-08-23-canh-bao-rui-ro-va-chan-tao-ncc.md` §2 |

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
| Xác nhận quá hạn nay BÁO cho người dùng, đặt ở ĐẦU câu trả lời | `erp_agent.QUA_HAN_MSG`; TTL giữ 300s có lý do — xem docstring `_them_bao_qua_han` |
| `/v1/*` bắt buộc Bearer token, fail-closed khi thiếu biến; `YOUDOO_FALLBACK_ROLE` đã GỠ | spec `2026-08-22-muc-9-12-13.md` + commit `e285c94`; nghiệm thu sống qua Open WebUI thật |
| CI chạy bộ mặc định trên `windows-latest`, cài ĐÚNG requirements production | spec `2026-08-22-ci.md`; KHÔNG phủ integration/live/eval — xem §3 |
| `groq-gpt-oss-120b` đã đo trên BA vai: `confirm` 0,8333 · `intent` 0,9630 (bằng Gemini) · `chitchat` violations=0 | spec `2026-08-22-muc-9-12-13.md` |
| Cổng xác nhận ghi hiện **args, KHÔNG hiện tên tool** — hai bất biến nay cùng đúng | cùng spec; `tests/agents/test_confirm_khong_lo_ten_tool.py` khoá hai chiều |
| Chuỗi mọi vai có **ba** mắt xích, mắt xích 3 `or-nemotron` (upstream nvidia); bất biến #6 canh "mỗi vai bind tool phải có ≥1 mắt xích ngoài Google" | spec `2026-08-22-muc-16-du-phong-ngoai-google.md`; commit `0cb708e` |
| **FM-3 của bản kiểm toán ("hội thoại dài giết đoạn chat") KHÔNG tái hiện được**: payload production là 28 tool `erp_query` (~2 762 token Groq đếm), không phải 35 tool MCP; Groq cần ~134 lượt lịch sử mới chạm trần | cùng spec §3 — đo qua đúng cổng vào production |
| **RBAC tầng RAG: lỗ hổng CÓ THẬT, hoãn CÓ ĐIỀU KIỆN** (2026-08-22 — mở lại khi có nhiều tài liệu nội bộ để RAG). Đo sống: vai `warehouse` hỏi "chính sách chiết khấu" ⇒ nhận đủ bậc 5%/10%, cộng 2%, trần 15% | `POST /v1/chat/completions` với `x-openwebui-user-id` của vai kho |
| Bán kính lỗ hổng đó **nhỏ hơn bản kiểm toán mô tả**: corpus 3 151 chunk / 17 tài liệu, **98,6% là PDF luật công khai**; toàn bộ vấn đề nằm ở 44 chunk / 8 tài liệu nội bộ, trong đó 4 tài liệu thương mại (`discount_policy`, `bang_gia`, `payment_policy`, `sla`) | truy vấn thẳng `rag_chunks` + `rag_documents` |
| ⚠️ `rag_chunks.visibility` **tồn tại trong schema nhưng KHÔNG ai đọc, KHÔNG ai ghi** — 3151/3151 chunk đều `'all'`. Hạ tầng để lọc đã có sẵn, chỉ chưa bật | `src/rag/schema.sql:30`; `grep -rn visibility` chỉ khớp đúng dòng đó |
| Vệt kiểm toán nay ghi `http_user` (id người dùng Open WebUI) + `args_digest` + `args_keys`; cả ba **nằm trong chuỗi hash** — sửa `http_user` thì verify báo đứt | spec `2026-08-22-muc-17-vet-kiem-toan.md`; nghiệm thu sống qua MCP thật có ca đối chứng |
| `mcp_call_log` khởi động chuỗi mới từ migration 005; 2 671 dòng cũ nằm nguyên ở `mcp_call_log_archive` | cùng spec §4; dòng `chain_reset` id=2685 ghi lại chính việc dọn |
| ⚠️ **`localhost` tốn ~4,1 giây MỖI lời gọi Odoo trên Windows** (5,188s vs 1,073s qua `127.0.0.1`; Windows thử `::1` trước, container bind IPv4). Đã sửa `ODOO_URL` trong `.env` ⇒ lượt ERP 11,27s → 6,58s. Postgres KHÔNG dính | spec `2026-08-23-muc-21-bao-tien-trinh.md` §4.1 — 3 lượt mỗi bên |
| Độ trễ lượt ERP KHÔNG phải "4 lời gọi LLM nối tiếp" như từng ghi: chặng đắt nhất là **lời gọi tool** (6,45s trước khi sửa). Phép đo rời bỏ sót vì lời gọi thử của tôi hỏng ngay do sai tham số | cùng spec §4.1 |
| Lượt tài liệu **ấm** chỉ 4,9–5,2s (truy xuất ~1s); con số 15,8s là lượt NGUỘI sau restart (reranker nạp trọng số) | cùng spec §4.2 |
| `ai-admin` ĐỦ quyền demo: ghi được `sale.order`/`crm.lead`/`purchase.order`/`mrp.*`/`stock.*`/`account.*`; vai kho bị chặn đúng chỗ (cột đối chứng) | spec `2026-08-23-vai-sales.md` §2 |
| Vai Youdoo suy từ `YOUDOO_ROLE_MAP` theo **user-id** (header `x-openwebui-user-id`), KHÔNG từ trường role của Open WebUI. Ba tài khoản nghiệp vụ (Kho/KeToan/Sale) để role Open WebUI = `user`; `DEFAULT_USER_ROLE` mặc định là `pending` nên tài khoản mới phải được duyệt thủ công | spec `2026-08-23-vai-sales.md` §7 — đọc `webui.db` |
| **Mục 18 ĐÓNG, không làm** (quyết định chủ dự án 2026-08-23): cả 5 tài khoản AI dùng CHUNG một mật khẩu, nên cách ly theo vai chỉ là trên giấy ở tầng credential. Code đã sẵn sàng; mở lại chỉ là đặt 5 biến | spec `2026-08-23-canh-bao-rui-ro-va-chan-tao-ncc.md` §1 |
| Odoo có **BỐN tầng phân quyền**, cả bốn đều có mặt: groups (76) · ACL theo model (869) · record rule (220) · field-level. Khoảng trống vai↔Odoo là "chưa ai viết luật", KHÔNG phải "Odoo thiếu cơ chế" | cùng spec §2 |
| ⚠️ ir.rule chặn ghi PHẢI đặt `perm_read=False` — đặt read=True sẽ giấu mọi NCC khỏi vai kho và bẻ gãy `find_supplier`. Nghiệm thu 3 chiều: tạo khách ✅ · tạo NCC CHẶN · đọc NCC ✅ | cùng spec §3 |
| **Không làm Undo**: cảnh báo rủi ro TRƯỚC khi xác nhận (15 tool), gợi ý hành động BÙ TRỪ khi lỡ. Tool tạo mới CỐ Ý không cảnh báo — cảnh báo mọi thứ thì chẳng còn gì là cảnh báo | cùng spec §4 |
| Câu hỏi tài liệu ĐẦU TIÊN sau restart: **15,8s** (không ấm) → **10,9s** (chỉ ấm reranker) → **6,1s** (ấm cả reranker + embedder). Ấm một nửa là chưa đủ | spec `2026-08-23-danh-bong-demo.md` §3 |
| `parse_selection` nay nhận số trong câu, chữ chỉ thứ tự tiếng Việt, và tên gõ thiếu sau phần số lượng. TÊN ưu tiên hơn số thứ tự; nhiều số trong câu ⇒ hỏi lại chứ không đoán | cùng spec §1 |
| Nhãn trạng thái tra theo **(model, state)**: `done` = hoàn tất (sản xuất) / đã giao (phiếu kho) / đã khóa (đơn bán). Bảng phẳng là sai | cùng spec §2 |
| `ACTIVITY_MODELS_OF` đo thật: sales gắn được activity lên sale.order, account.move, stock.picking, mrp.production, crm.lead — KHÔNG có purchase.order | cùng spec §4 |
| ir.rule mail cưỡng chế THẬT theo vai: warehouse đọc 1 template, accounting 5, sales 4, admin 29 | cùng spec §4 — `search_read` trên `mail.template` từng tài khoản |
| `send_delivery_email`/`send_invoice_email`/`send_quotation_email`/`send_order_confirmation_email` là **coordinator tầng backend**, KHÔNG phải tool MCP. Đừng đối chiếu chúng với registry MCP rồi kết luận "tool không tồn tại" | cùng spec §5 — tôi đã mắc đúng lỗi đó |
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
