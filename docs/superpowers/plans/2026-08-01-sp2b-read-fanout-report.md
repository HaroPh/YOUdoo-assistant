# SP-2b — báo cáo số đo và xác minh sống

Plan: `docs/superpowers/plans/2026-08-01-sp2b-read-fanout.md`
Spec: `docs/superpowers/specs/2026-08-01-sp2b-read-fanout-design.md`

## Số đo TRƯỚC

Chạy trên `main` sạch tại commit `e9117d8 docs(plan): SP-2b — 10 task, fan-out đường đọc`, trước khi sửa dòng đầu tiên.
Model: đầu chuỗi catalog của vai tương ứng (không truyền `--model`).

### multi_source (vai `fusion`)
- verdict: `PASS`
- `both_source_coverage`: `0.75`
- `citation_validity`: `1.0`
- `fabricated_number`: `0`
- `lat_p50` / `lat_p95`: `1061` / `1484` ms
- log gốc: `logs/jobs/eval-gate-20260801T104522.json`

### intent (vai `router`)
- verdict: `PASS`
- `acc`: `0.9444444444444444`
- log gốc: `logs/jobs/eval-gate-20260801T105408.json`

### sop_select (vai `router`)
- verdict: `FAIL` (biết trước — gate tuyệt đối, 16/17 tồn dư từ SP-2a)
- `acc`: `0.9411764705882353`
- `hijack`: `0`
- log gốc: `logs/jobs/eval-gate-20260801T105851.json`

## Số đo SAU

Chạy trên nhánh SP-2b tại commit `a3fd5d1` (docs(sp2b): comment tại chỗ — vai
`fusion` sống dù node chết — commit cuối trước khi Task 10 tự commit report
này), cùng model đầu chuỗi catalog của vai tương ứng (không truyền `--model`)
và cùng công thức `--pace` mặc định (suy từ RPM catalog) như lượt TRƯỚC.

### multi_source (vai `fusion`)
- verdict: `FAIL`
- `both_source_coverage`: `0.625` (TRƯỚC: `0.75`)
- `citation_validity`: `1.0` (TRƯỚC: `1.0`)
- `fabricated_number`: `0` (TRƯỚC: `0`)
- `lat_p50` / `lat_p95`: `1149` / `1444` ms (TRƯỚC: `1061` / `1484`)
- log gốc: `logs/jobs/eval-gate-20260801T121135.json`
- Chạy lặp lại một lần nữa để loại trừ khả năng nhiễu lấy mẫu (không phải một
  bước bắt buộc của giao thức đo, làm thêm vì kết quả FAIL cần được xác nhận
  trước khi ghi vào báo cáo): lần 2 ra ĐÚNG `both_source_coverage=0.625`, ĐÚNG
  3 ca fail giống hệt lần 1 (`sla_giao_hang`, `chinh_sach_hoan_hang`,
  `chinh_sach_thanh_toan`) — log `logs/jobs/eval-gate-20260801T121335.json`.
  Kết quả tất định trên input này (mô hình trả lời giống hệt hai lần), không
  phải nhiễu ngẫu nhiên của lấy mẫu LLM.

### intent (vai `router`)
- verdict: `PASS` — `acc`: `0.9444444444444444` (TRƯỚC: `0.9444444444444444`)
- log gốc: `logs/jobs/eval-gate-20260801T122814.json`

### sop_select (vai `router`)
- verdict: `FAIL` (biết trước) — `acc`: `0.9411764705882353` (TRƯỚC:
  `0.9411764705882353`), `hijack`: `0` (TRƯỚC: `0`)
- log gốc: `logs/jobs/eval-gate-20260801T123213.json`

## Xác minh sống

**Ghi chú hạ tầng (trước khi test live chạy được):** worktree này khởi động
với hai khoảng trống hạ tầng chặn test live — (1) MCP server Odoo
(`mcp-servers/odoo/server.py`, cổng 8001) chưa chạy, phải khởi động thủ công
bằng `backend/.venv` (cùng phiên bản gói `mcp==1.28.0` đã có sẵn) sau khi cài
thêm `psycopg2-binary==2.9.12` cho nhánh log audit tùy chọn của MCP server; (2)
Postgres RAG (`rag_documents`/`rag_chunks` trên `DATABASE_URL`, Youdoo Postgres
cổng 5434) hoàn toàn trống — 0 dòng cả hai bảng, vì đây là instance Postgres
mới riêng cho worktree này, chưa từng chạy `ingest`. Lượt live đầu tiên vì vậy
trả lời đúng nhưng không có trích dẫn ("phần tài liệu nội bộ... đang bị
trống"). Đã chạy `python -m src.rag.ingest src/rag/seed` để nạp kho tài liệu
seed sẵn có trong repo (gồm `policy.docx` — "Chính sách hoàn hàng") — kết quả
`{'ingested': 17, 'skipped': 0, 'chunks': 3300}` — sau đó test live PASS.

- Test đơn vị (`-m "not integration and not live"`): `1066 passed, 4 skipped, 42 deselected`
- Test integration (`-m integration`): `27 passed`
- Test live `test_dau_cuoi_fanout.py`: `PASS`
- Câu hỏi đã hỏi: "Theo chính sách hoàn hàng, đơn S00042 còn hoàn được không?"
- Trích nguyên văn câu trả lời nhận được:

```
Đơn hàng S00042 hiện đang ở trạng thái nháp (draft) và chưa được giao, do đó chính sách hoàn hàng chưa áp dụng cho đơn hàng này. Theo quy định, các yêu cầu thay đổi về sản phẩm hoặc số lượng đối với đơn hàng chưa giao cần được thực hiện thông qua quy trình xử lý thay đổi đơn hàng trước khi đơn được xuất đi.

📄 Nguồn:
• Quy trình bán hàng › Mục 5 — Xử lý thay đổi đơn hàng (sales_process.docx)
```

## Kết luận

Đối chiếu 7 điều kiện "SP-2b xong" của spec §8, mỗi điều một dòng:

1. `fusion.py` không còn trong repo, `FUSION_PROMPT` không còn trong
   `prompts.py` — **đạt**. `backend/src/agents/fusion.py` không tồn tại;
   `grep FUSION_PROMPT backend/src/agents/prompts.py` → 0 khớp.
2. `mixed` chạy hai chân song song, `fuse_answer` ra đúng một `AIMessage` —
   **đạt**. `graph.py` có `g.add_edge("mixed", "gather_docs")` và
   `g.add_edge("mixed", "gather_erp")` (hai cạnh thẳng ra cùng superstep),
   cả hai gộp vào `fuse_answer` → `END`. Khẳng định bằng test tích hợp thật
   `tests/agents/test_fanout_graph.py::test_real_graph_mixed_turn_produces_one_answer`
   (gọi `build_graph()` thật, PASS trong lượt suite Bước 1 — xác nhận lại độc
   lập: `5 passed` khi chạy riêng file này).
3. Cổng `multi_source` PASS **và** `both_source_coverage` SAU ≥ TRƯỚC,
   `fabricated_number`=0, `citation_validity`=1.0 — **KHÔNG đạt**. verdict SAU
   = `FAIL`; `both_source_coverage` 0.625 < TRƯỚC 0.75 (hồi quy thật, tái lập
   y hệt ở lần chạy thứ hai — cùng 3 ca fail, cùng điểm số). Hai vế còn lại
   của điều kiện (`fabricated_number`=0, `citation_validity`=1.0) VẪN đạt —
   không có bịa đặt hay trích dẫn sai — nhưng điều kiện spec đòi CẢ BA vế
   cùng đạt, nên tổng thể điều 3 không đạt.
4. Cổng `intent` PASS; `sop_select` hijack=0 và acc≥16/17 — **đạt**. `intent`
   acc=0.9444444444444444 → PASS, y hệt TRƯỚC. `sop_select`
   acc=0.9411764705882353=16/17 đúng ngưỡng, hijack=0 — FAIL biết trước như
   spec đã chấp nhận ở SP-2a, không tệ thêm so với TRƯỚC (cùng 1 ca fail,
   "quy trình nhập kho cho đơn mua P00021" → `rag` thay vì `nhap-kho`).
5. Toàn bộ test xanh ở cả ba chế độ, gồm test tích hợp gọi `build_graph()`
   thật — **đạt**. Unit-only: `1066 passed, 4 skipped, 42 deselected`.
   Integration (`-m integration`, 27 ca — chủ yếu Postgres/RAG storage):
   `27 passed`. Live (`-m live`): test mới `test_dau_cuoi_fanout.py`
   `1 passed`. (Lưu ý thuật ngữ: "test tích hợp gọi build_graph() thật" của
   mục này được thoả bởi `test_fanout_graph.py` — chạy trong bộ unit-only,
   KHÔNG mang marker `integration` của pytest; marker `integration` của repo
   này chỉ phủ Postgres/RAG storage, không phủ fanout graph. Cả hai bộ đều
   xanh nên không ảnh hưởng verdict, nhưng nêu rõ để tránh lẫn hai khái niệm
   "tích hợp".)
6. Một câu hỏi `mixed` thật chạy ra một câu trả lời có trích dẫn — **đạt, kèm
   một điểm cần nêu rõ**. Test live gọi thẳng `ERPAgent.chat()` — ĐÚNG
   phương thức mà route `POST /v1/chat/completions` trong `main.py` gọi (dòng
   ~146: `answer = await agent.chat(messages, thread_id=thread_id, ...)`,
   không có logic nghiệp vụ nào khác chen giữa route và `agent.chat`) — chứ
   KHÔNG phải một request HTTP thật gửi tới uvicorn đang chạy. Câu trả lời
   nhận được có khối `📄 Nguồn:` và không lộ marker nội bộ `NGUỒN_DÙNG`.
7. Vai model `fusion` trong `catalog.py` không đổi — **đạt**.
   `CHAINS["fusion"]` vẫn nguyên `("gemini-3.1-flash-lite",
   "groq-llama-3.3-70b")`, có comment tại chỗ giải thích (Task 9,
   `catalog.py` dòng ~127).

Latency là số **quan sát, không phải cổng** (spec §5.3): `multi_source`
lat_p50/p95 SAU 1149/1444ms so TRƯỚC 1061/1484ms — dao động nhỏ cùng cỡ độ
lớn; không dùng để kết luận đạt/không đạt bất kỳ điều nào ở trên.

**Tổng kết: 6/7 điều kiện đạt, điều 3 KHÔNG đạt.** `both_source_coverage` hồi
quy thật (0.75 → 0.625), tái lập được ở hai lần chạy độc lập — không phải
nhiễu lấy mẫu. Ba ca fail đều có dạng model từ chối khẳng định kết hợp hai
nguồn ("không đủ căn cứ", "chưa thể khẳng định") thay vì bịa số liệu —
`fabricated_number`=0 và `citation_validity`=1.0 xác nhận đây KHÔNG phải một
lỗ hổng an toàn (không bịa đặt), nhưng vẫn là hồi quy thật trên đúng chỉ số mà
spec §8 điều 3 yêu cầu không được tệ đi so với TRƯỚC. Nguyên nhân nhiều khả
năng nhất: `FUSE_PROMPT` mới (khung "bạn nhận sẵn hai nguồn đã thu thập",
thay cho `FUSION_PROMPT` cũ khung "bạn tự gọi tool để tìm hai nguồn") khiến
model có xu hướng nghiêng về từ chối/nêu thiếu căn cứ ở các ca biên nhiều hơn
trước — đây là suy luận có căn cứ từ nội dung 3 câu trả lời fail, không phải
điều tra nguyên nhân gốc đầy đủ (nằm ngoài phạm vi đo của Task 10).

SP-2b **CHƯA đủ điều kiện đóng** theo đúng định nghĩa của chính spec §8 —
6/7 điều đạt, nhưng điều 3 (một trong hai cổng eval bắt buộc PASS) không đạt
và là hồi quy thật, không phải false alarm. Cần một vòng xem xét/sửa (nhiều
khả năng ở `FUSE_PROMPT` hoặc ở chính 3 ca `MULTI_SOURCE_CASES` bị fail)
trước khi có thể coi SP-2b là xong.
