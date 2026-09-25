# Trạng thái chung — hai phiên làm việc song song

Cập nhật lần cuối: **2026-09-25**.

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
| 37b | Có bật `RAG_RERANK_MODE=override` cho production không | RAG | Hai nguồn số **CÙNG CHIỀU**: cả hai đều cho `override` hơn `blend` về MRR. Chúng chỉ khác ở độ chắc chắn và ở 2 câu cụ thể. Bench ngoài (1.788 câu): MRR +0,038/+0,046, p<0,0001 trên cả hai bộ (số trước khi sửa khoá phá hoà; bản đo lại trên pool tất định ở `bench-ngoai-2026-09-24-tiebreak/`). Bộ nội bộ 109 ca (#31d): Δ+0,0507, cũng tốt hơn, nhưng p chính xác 0,01073 nhỉnh hơn ngưỡng 0,01, và mất 2 câu hợp đồng lao động mà blend giữ. Câu cần quyết: 2 câu bị rơi đó có đủ nặng để chặn một cải thiện cùng chiều trên cả ba bộ không |
| 29 | Có xoá **18 dòng rác `p=1200 c=300 t=1500`** trong `public.llm_usage` không | vận hành | Suite ghi vào sổ thật trước khi có rào `so_vlm_khong_cham_postgres` (#29 đã đóng ở `2e75d51` + `0c9a122`) |

## Việc đang treo

| # | mục | ai giữ | chặn bởi |
|---|---|---|---|
| 15 | Guardrail fail-open: **nửa CHẨN ĐOÁN đã vá** (log + đánh dấu "chưa xác minh" ra người dùng). Nửa còn lại — **tách ví hạn mức** cho verifier — chưa làm | chưa ai | cần quyết: dùng model/ví riêng cho verifier, hay chấp nhận nó tắt khi cạn |
| 19 | RAG: **không có Query Transformation** | chưa ai | recall@20 = 1,0 ⇒ truy xuất không phải nút thắt |
| 25 | **Cổng eval của Youdoo không có lịch nào gọi.** `eval-gate` khai `schedulable=True` nhưng máy chỉ có đúng một lịch (`ERP-AI-EvalGate`) và nó trỏ vào `D:\Project`. Youdoo không có script chạy định kỳ ⇒ cổng chỉ chạy khi có người gõ lệnh. Cổng `retrieval` đã vào `--set all` (#28, đóng 2026-09-24), chỉ còn thiếu lịch | chưa ai | cần quyết: chạy đêm thì tốn hạn mức API mỗi ngày |
| 26 | **Open WebUI: `top_k_reranker` còn = 3 trong khi `top_k` = 10.** Việc của chủ dự án, không sửa mã: Admin → Documents, đặt `top_k_reranker` ≥ `top_k`. Đo được 8/11 → 10/11 trên bộ 11 câu tệp đính kèm | chủ dự án | ghi chú thi hành `2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md`, mục hướng B bước 2 |
| 32 | **Lát 5 chạy trên corpus sản xuất** (`20d58d5` + fix `65420d9`, 2026-09-19): SID 117 verified / 104 unverified, 25 lượt VLM ~70k token/tài liệu. CÒN: bảng cột trùng tên (nhóm theo năm) chưa đỡ; `loai=hieu` model gắn nhầm `cong_don` — cần tầng kiểm phép trừ; VLM không tất định giữa lượt; nghiệm thu rộng 4 PDF scan còn lại | chưa ai | ghi chú thi hành |
| 31 | **So sánh 3 reranker — tín hiệu 4B ĐÃ QUA kiểm định trên bộ `hard` MỞ RỘNG (2026-09-18, 17 → 62 ca, 45 ca mới do agent mù viết từ mẫu tất định): XÁC NHẬN theo quy tắc đăng ký trước (spec mở rộng §8) — `qwen3-4b-override` so `bge-reranker-v2-m3` hoà 1:1 trên `hard mrr`, n=62, chênh +0,1290, CI95 [+0,060; +0,202], p=0,0007, 18 thắng/42 hoà/2 thua; trên 109 ca `recall@6` 0,9679 ≥ 0,9633 và 0 ca bị văng khỏi top-6 mà bge còn giữ. Production VẪN GIỮ `bge-reranker-v2-m3` + `blend`, chưa đổi gì.** Hai điều phải đọc kèm: (i) độ lớn co từ +0,25 (17 ca cũ — mẫu tự chọn, nghiêng về chỗ yếu của bge: `hard mrr` bge 0,5755 trên 17 cũ so 0,8010 trên 45 mới) xuống **+0,129**; (ii) riêng 45 câu MỚI (phần chưa ai nhìn trước): CI [+0,022; +0,149] không cắt 0 nhưng **p=0,0146 — KHÔNG dưới ngưỡng 0,01 spec tự đặt**; cùng chiều, yếu hơn số gộp; §8 quy định new-45 chỉ báo thêm nên kết luận giữ. Còn mở: (a) **cổng lượng tử hoá 4B chưa chạy** (`bitsandbytes` sm_120 hoặc GGUF/`llama.cpp`) — giờ là câu hỏi ĐỘ TRỄ + giữ `trap`/`mrr`, không còn là recall (109 ca: `r@20` = 0,9771 mọi chân = trần pool; p50 4B hiện là đường `device_map=auto` offload CPU 4568 ms, không phải số triển khai); (b) **`trap` vẫn n=16, kém lực** — chưa mở rộng, 0,8958 so 0,8875 chỉ nói "không tụt rõ"; (c) **bài học R12**: cổng đối chứng `old-64` (spec §7) chỉ soi các ca chạy TRƯỚC — lượt `qwen3-4b` hoà đầu tiên qua mọi kiểm tra cơ học + cổng §7 mà sụp trên 45 ca chạy SAU (`r@6` 0,6444 < tắt rerank 0,8667) vì máy cạn RAM giữa lượt (4B tràn ~5 GB sang CPU); đã loại và chạy lại, thêm cổng `r@6 new-45 ≥ no-rerank` — cổng này còn kiểm tay, chưa vào `run_eval` (**việc mở**: một cổng liên tục phải phủ cả các ca chạy CUỐI, đưa vào `run_eval` hoặc test hợp đồng; và lượt bị loại đã bị chạy lại ghi đè, không còn kiểm toán được — lần sau đổi tên `*.DISCARDED.json` thay vì ghi đè); (d) chân `bge`+`override` **ĐÃ ĐO 2026-09-19** (`evals/results/reranker-2026-09-18-mo-rong/bge-v2-m3-override.json`, 109/109, 0 lỗi): so *no-rerank* thắng áp đảo (Δ+0,2014, CI95 [+0,139;+0,265], p≈0) — kết luận 2026-08-20 "override trên bge THUA cả tắt rerank" **không còn đúng** vì hạ tầng đã đổi hẳn từ đó (corpus, `section_path`, chân bỏ dấu, vá breadcrumb); nhưng so *blend* (production hiện tại) **KHÔNG đạt ngưỡng**: Δ+0,0507 toàn 109 ca song p CHÍNH XÁC (DP) = **0,01073** — CLI in 0,0097 (Monte Carlo, 28 chênh ≠ 0 > `max_exact`), trên ngưỡng 0,01 chứ không dưới; riêng hard-62, p=0,0638; đổi này còn MẤT 2 câu hợp đồng lao động (chấm dứt/đơn phương dừng) mà blend giữ, chỉ ĐƯỢC lại 1 câu quy trình giao hàng — **không bật override cho bge sản xuất**, chưa đủ số. (e) 5 khoản vá nhỏ hoãn từ review Task 1–5 của spec 2026-09-17 chờ soát trước merge; (f) `0.6B override` **p chính xác = 0,0110** (CLI in 0,0101 là ước lượng Monte Carlo 20 000 lượt, SE ≈ 0,0007 — 24 chênh ≠ 0 vượt `max_exact = 22`), trên ngưỡng 0,01 khoảng 0,001, chưa kết luận — là ứng viên kế nếu 4B trượt cổng độ trễ, cần quy tắc đăng ký trước riêng; (g) ✅ **`retrieval_stats` in p Monte Carlo và p chính xác giống nhau — ĐÃ VÁ 2026-09-19.** Phép so quyết định gốc (20 chênh ≠ 0) tình cờ là chính xác, phép so 109 ca (29) và 0.6B override hard-62 (24) là MC; bằng chứng thứ hai đo thêm cùng ngày: `bge-override` vs `bge-blend` toàn 109 ca có 28 chênh ≠ 0, CLI cũ in p=0,0097 (MC) nhưng DP chính xác = 0,01073 — đổi phía so ngưỡng 0,01 (mục (d)). Vá: nhánh chính xác đổi từ liệt kê `itertools.product` sang DP theo tổng dấu (nhanh hơn ~n lần, không tính lại tổng mỗi tổ hợp dấu), CLI/`compare()` in kèm nhãn `(exact)`/`(MC n=20000)`, nâng `max_exact` 22→30 (đủ trùm cả hai ca vừa gặp: 24 và 28). **Tự bắt một lỗi thứ hai khi vá**: bản DP đầu làm tròn tổng tới 9 chữ số thập phân để gộp trạng thái rẻ hơn — kiểm chéo bằng liệt kê thẳng (brute-force, 2^24, ~26 giây) thì SAI trên đúng ca 0.6B-override hard-62 (làm tròn cho 0,01085, liệt kê thẳng cho 0,01099 — vài trạng thái gần biên bị gộp lộn phe hit/miss); bỏ làm tròn (dict khoá bằng float thô, DP và liệt kê thẳng cộng cùng thứ tự nên khớp bit-để-bit) thì khớp brute-force ở mọi ca đã kiểm. DP có trần trạng thái (`_DP_STATE_CAP=2 000 000`), vượt trần rơi về Monte Carlo — an toàn với dữ liệu không trùng giá trị (đã đo: 28 float ngẫu nhiên liên tục chiếm >8 GB, không xong sau 300 giây nếu không có trần). Test hợp đồng: `test_retrieval_stats.py` (khớp brute-force ở n=16; nhánh exact độc lập seed ở đúng mốc max_exact=30; DP trả `None` khi vượt trần; nhãn `(exact)`/`(MC n=…)` đúng nhánh) | chưa ai | spec `2026-09-18-mo-rong-hard-set-design.md` §10–§11 (kết luận Task 7); cổng lượng tử hoá 4B là plan riêng, chưa có |
| 37 | **Benchmark ngoài có qrels thật (2026-09-23)** — TVPL-Retrieval-VN (1.000 câu) + Zalo AI Legal Text Retrieval (788 câu, corpus 61k Điều), nạp qua đúng bộ cắt/biến đổi ingest vào schema riêng, mọi chân chung một pool; 0 lỗi, qua cổng R12. **(a) Qwen3-Reranker-0.6B THUA bge-reranker-v2-m3** cùng chế độ ở cả hai bộ (MRR −0,012…−0,060, p ≤ 0,03), chậm ~3,5× ⇒ đảo kết luận "0.6B-override hơn bge" của #31: phần lợi đó là của chế độ override, không của model. **(b) `override` > `blend` với bge**: MRR +0,038/+0,046, p < 0,0001 trên CẢ HAI bộ; recall@6 không tụt (+0,012 p=0,023 / +0,0025 ns) nhưng có câu văng (9/5) — **chờ chủ dự án quyết, xem bảng "Đang chờ chủ dự án quyết"**. (c) Mất lớn nhất nằm trước reranker: 7–8,5% đáp án không vào pool 20. **(d) Stress test vai (nhãn `commercial` GIẢ LẬP, mật độ 27–40% chunk):** 0 rò rỉ; accounting trùng admin từng câu; tín hiệu "bị chặn" bắt 96–98%; nhưng luật top-3 **từ chối oan 40,6% / 43,4%** câu mà kho ĐÃ tìm đúng đáp án — tỉ lệ oan tăng theo mật độ nội dung bị giấu, nên con số 0/990 của 19c sẽ không giữ khi 19b mở lại với nhiều tài liệu nội bộ. **(e) Thứ hạng không tất định**: chân FTS `ORDER BY score` thiếu khoá phá hoà (117/200 câu hoà `ts_rank`), `UPDATE` bảng đổi thứ tự top-6 ở 2,1% câu — ✅ **ĐÃ SỬA** `a2b07be` (khoá phá hoà `c.id` cho cả ba chân, merge `4a2146b`; đo lại bench ngoài sau sửa `8afa11f`: không hồi quy). (f) Ingest production ghi từng dòng 46 ms/dòng; `executemany` nhanh ~15× — CHƯA sửa. 4B chưa đo trên bộ ngoài | chủ dự án (b); chưa ai (d)(f) | `backend/evals/results/bench-ngoai-2026-09-23/README.md` |
| 19c-dư | **Phần còn mở của 19b/19c** (hai mục chính đã đóng: 19b `1191347`, 19c `a30ef9f`). (1) Trên tuyến mixed, model fusion TỰ VIẾT một đoạn lý do SAI ("ERP không có dữ liệu") đứng TRƯỚC câu từ chối tất định; máy không bắt được vì đoạn đó không chứa marker. Sửa cần A/B prompt fuse. (2) Tuyến thật của câu mixed trong probe sống chưa được soi qua Langfuse/log. (3) CHƯA ĐO: câu tỉnh lược cần ngữ cảnh lượt trước ("trong bao lâu?" sau câu về SLA). Sau bản sửa C1, lượt bóng chỉ thấy câu hiện tại. (4) Mở lại 19b khi corpus có nhiều tài liệu nội bộ; bảng chọn k cho ngày đó đã có sẵn (mục "Đã đo" đầu tiên). 5 giới hạn còn lại của 19b: spec §10 | chưa ai | spec `2026-09-21-bao-bi-chan-tang-rag-design.md` §10; `2026-09-20-rbac-tang-rag-design.md` §10 |

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
| **Luật "báo bị chặn" GIỮ NGUYÊN, `HIDDEN_TOP_K = 3` là đúng cho corpus hôm nay** (chủ dự án chốt 2026-09-24). Luật thay thế ("từ chối khi KHÔNG có thứ thấy được trong top-k") bị số đo BÁC BỎ: trên production nó bắt **1/10** ở k≥2 và **0/10** ở k=6 — gần như không bao giờ từ chối, tức làm chết tính năng 19c. Lý do: corpus 98,9% là PDF luật (`all`), nên lượt bóng gần như luôn có một chunk thấy được ở top-2 kể cả với câu hỏi mà đáp án nằm ở tài liệu thương mại. Tiền đề sai: **một chunk được XẾP HẠNG cao không có nghĩa nó TRẢ LỜI được câu hỏi** — cùng lớp lỗi đã khiến `passes_floor` bị loại khỏi vai trò này. Luật hiện tại trên nhãn THẬT: **9/10 bắt, 0/99 oan**. Con số 40–43% của bench là ở mật độ cao gấp **45–65 lần** production (24/3.901 = 0,6%) — stress test cơ chế, không phải dự báo. Đổi k về 1 sẽ kéo bắt đúng 9/10 → 5/10 ngay hôm nay để giảm một tỉ lệ oan đang bằng KHÔNG. **Ngày phải xem lại** = ngày mở lại 19b (corpus nhiều tài liệu nội bộ); bảng chọn k cho ngày đó đã có sẵn, không cần đo lại. | `backend/evals/results/luat-top3-2026-09-24/` — lưới 12 ô × 3 bộ (1.000 + 788 + 109 ca), có TỰ CHỨNG khớp hai mốc 19c (k=1→5/10, k=3→9/10), rò rỉ 0 mọi ô |
| **"Hồi quy" baseline `retrieval` nửa dấu/không dấu là SO LỆCH BỘ CA, không phải chất lượng tụt.** Hard-set mở rộng 17→62 ca ngày 2026-09-19 nhưng chỉ baseline dạng CÓ DẤU được chốt lại; hai baseline kia ở lại 64 ca. Đo lại trên CÙNG 64 ca: nửa dấu **0,8203 = 0,8203** (khớp tuyệt đối) và recall@20 còn **tốt hơn** (0,8672 vs 0,8359, 2 ca trước đây trượt pool nay lọt, 0 ca mới trượt); không dấu recall@20 **bằng đúng** 0,6042 với y nguyên 25 ca trượt pool, recall@6 lệch 1 ca — và lệch đó CÓ TRƯỚC hai bản sửa ngày 24/09 (mã cũ 0,5052, sau sửa 0,5104). Giả thuyết sót backfill `chunk_text_fold` đã BỊ BÁC: 0/3.901 chunk rỗng. Đã chốt lại cả hai baseline trên bộ 109 ca. | phiên 2026-09-24; `n` nay là điều kiện hợp lệ trong `_gate("retrieval")` và có test hợp đồng `test_moi_baseline_do_tren_DUNG_bo_ca_hien_tai` |
| **Open WebUI `RerankCompressor` LUÔN cắt xuống `top_n = k_reranker`**, kể cả khi không cấu hình reranking model (nó tự chấm lại bằng cosine rồi cắt) ⇒ `top_k=10` + `top_k_reranker=3` = lấy 10, giao 3, xếp thuần dense, BM25 hạng 4-10 bỏ sạch | `open_webui/retrieval/utils.py:1743` đọc trực tiếp trong container; `backend/tools/compare_attachment_retrieval.py` đo 8/11 → 10/11 khi bỏ trần |
| **Truy hồi của Open WebUI KHÔNG tệ hơn của ta** trên tệp đính kèm khi cấu hình đúng: HỌ 10/11 vs TA 9/11 (thước "đáp án có trong ngữ cảnh @k=10", 11 câu DVT/NTC) ⇒ hướng B bước 3 (lấy lại tầng truy hồi) mất lý do chất lượng, ĐÓNG 2026-09-17 | commit `532c78f`; giới hạn N=11 một miền ghi trong ghi chú thi hành |
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
| **Đường ĐỌC nay có vệt kiểm toán** (mục 17b): một dòng `erp_read` mỗi lời gọi tool, kèm vai + `http_user` + **giá trị tham số đầy đủ**. Ở đường đọc chính tham số mới là câu trả lời — ngược với quyết định digest ở mục 17, có chủ đích | spec `2026-08-23-muc-17b-vet-kiem-toan-duong-doc.md` |
| Ghi ở tầng TOOL chứ không ở `transport.call()`: gateway chỉ biết model+method, và một tool gọi gateway vài lượt. KHÔNG hash-chain — `compute_entry_hash` ở cây MCP, chain sẽ buộc chép công thức băm sang backend | cùng spec §2 |
| ⚠️ **Youdoo và `D:\Project` dùng HAI database TÁCH BIỆT** — container riêng (`youdoo-postgres` 5434 vs `postgres` 5433), volume riêng (`youdoo_youdoo_postgres_data` vs `project_postgres_data`), corpus riêng (3 151 vs 3 300 chunk). NHƯNG hai tệp nguồn từng mặc định về **5433** — cùng tên db `ai_assistant` — và thứ duy nhất chặn là mật khẩu sai. Đã sửa về 5434 + test gác | đo 2026-08-23; `tests/test_khong_tro_sang_du_an_anh_em.py` |
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

- Thứ hạng bên trong top-6 có đổi câu trả lời cuối không (docstring `rerank()`).

## Bẫy vận hành

- ⚠️ **`backend/.env` là cấu hình VÔ HÌNH và nó từng sai.** Tới 2026-09-24 dòng
  `OLLAMA_URL` ở đó trỏ `http://localhost:11434` — cổng CHẾT (Ollama của Youdoo bind
  `127.0.0.1:11435`, chỉ IPv4), lại còn dính án phạt IPv6 ~2s/lời gọi đã ghi trong
  `rag/config.py`. Repo `.env.example` ghi ĐÚNG; chỉ tệp cục bộ trôi. Mã Youdoo không
  tự nạp `.env` (`load_dotenv` duy nhất trong cây là của bộ dữ liệu bên thứ ba), nên
  nó chỉ cắn qua `load-env.ps1`/`start-dev.ps1` — tức đúng đường dev được ghi trong
  tài liệu. **Trước mọi lượt đo, kiểm `OLLAMA_URL` thật sự phân giải ra cái gì.**
- ⚠️ **So với tệp baseline KHÔNG phải phép đo đối chứng.** 2026-09-24: thấy `retrieval`
  nửa dấu 0,820 → 0,766 sau một thay đổi và suýt kết luận là mình gây hồi quy. Đo lại
  bằng cách `git stash` bản sửa rồi chạy code HEAD trên CÙNG corpus thì HEAD cũng ra
  0,766 — baseline đã cũ từ trước. **Muốn biết một thay đổi có gây hồi quy không thì
  phải so với HEAD chạy hôm nay, không phải với con số chốt 5 tuần trước.**

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
- **`llm_usage` là CẬN DƯỚI hễ API key được dùng ngoài backend Youdoo** (#30,
  đóng 2026-09-20). Khoảng 13→18/09 key dùng chung 3 nơi nên sổ im lặng dù
  đường ghi không hỏng. Từ 20/09 chủ dự án xác nhận không còn nơi nào khác
  dùng key. Trước khi tin số hạn mức, hỏi "key còn ai dùng không?".
- **DB RAG thật**: `postgresql://admin:thay_bang_mat_khau@localhost:5434/ai_assistant`
  (container `youdoo-postgres`).
- Đụng `chunking`/`parse` thì phải `DELETE FROM rag_documents` rồi ingest lại
  (~3,5 phút). Không xoá thì content-hash bỏ qua toàn bộ 17 tệp.

## Giới hạn đã chấp nhận — có đo, quyết không sửa

| giới hạn | số đo | vì sao không sửa |
|---|---|---|
| Footer nguồn chỉ nêu LỚP nguồn (`📄 Nguồn: kho tài liệu chung`), không phát hiện được tệp đính kèm (#34, đóng 2026-09-19) | Open WebUI pop cả `files` (middleware.py:2600) lẫn `metadata` (openai.py:1207) trước khi gọi; request có-tệp-0-nguồn và không-tệp giống nhau từng byte | Muốn hơn phải sửa phía Open WebUI (inlet filter), ngoài repo này |
| 3 cặp vai↔Odoo sửa được dòng đơn mà roles.py cấm: kho `update_quotation_lines`, kế toán `update_quotation_lines`/`update_rfq_lines` (#23, đóng 2026-09-25) | Vai kho sửa được số lượng dòng S00193 nhưng không thêm/xoá dòng (`c0 u0`) | Gốc là ACL MẶC ĐỊNH của Odoo (`w1` trên `*.order.line`); sửa có thể làm vỡ luồng kho/kế toán mà không có gì báo. Chỉ agent chặn. Đã khai trong `KNOWN_ODOO_GAPS`: script `check_role_odoo_consistency.py` thoát mã 0 (28/28 gap đã biết) |
| Hai key cho cùng một fact (`hien_thi_ma_don` + `always_show_order_code`) | 5 fact = 10% `SYSTEM_PROMPT`; cộng dồn không hỏng chỉ số nào (spec §13) | Sửa cần phân loại/gộp lúc ghi — cơ chế đã bị số đo bác hai lần. **Cách rẻ hơn: người dùng tự bảo trợ lý "quên `always_show_order_code`"** — nó là dữ liệu, không phải code. Nguy cơ thật là sửa một cái mà cái kia vẫn nói ngược; chưa xảy ra. |
| Không có trần số fact | ở 50 fact khối bằng 130% `CHITCHAT_PROMPT`, nhưng người dùng thật có 5 | Đặt trần bây giờ là dựng cơ chế cho một rủi ro chưa đo được. Đo lại khi có người vượt ~20 fact. |
| `proposed_rate = 0` trên `fuse_answer` | 0,75 → 0,00 tất định 3 lượt | Ba hướng khả dĩ: một đắt, một vô dụng, một nguy hiểm (spec §16). |
| Mặc định là **3.1** dù số nghiêng 3.5 | acc sau vá: 3.1 = 0,9630 · 0,9630; 3.5 = 0,9630 · 0,9815. Trễ trung vị 2000ms vs 951ms | **Chủ dự án chốt 2026-08-21: giữ 3.1.** Số chỉ cho thấy 3.5 *ngang*, không cho thấy nó *hơn*; đổi mặc định để lấy tốc độ là mua bằng rủi ro định tuyến im lặng (spec §4). Ai cần nhanh thì đổi ở dropdown — đúng việc tính năng này sinh ra để làm. Mở lại **chỉ khi** có số mới cho thấy 3.5 HƠN. |
