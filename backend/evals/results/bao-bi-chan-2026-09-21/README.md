# Hai lượt đo của cổng ÂM/DƯƠNG bao-bi-chan-tang-rag

Hai JSON này là **đầu vào của cổng ÂM** — `evals/compare_visibility.py` so chúng
với nhau. Cổng này 19b đã dựng; nhánh `bao-bi-chan-tang-rag` chỉ MỞ RỘNG nó để
đọc thêm cờ `hidden` mỗi ca (tín hiệu `retrieve()` phát khi lớp bị giấu nằm trong
**top-`HIDDEN_TOP_K`** của một truy vấn bóng không lọc vai — xem spec
`2026-09-21-bao-bi-chan-tang-rag-design.md` §3/§6.3).

Cùng corpus, cùng migration như `19b-2026-09-20` (không ingest lại — chỉ mã đo
thay đổi, không phải dữ liệu): các số retrieval thuần (r@20/r@6/mrr) dưới đây
**trùng khít** với thư mục đó ở từng vai — bằng chứng độc lập rằng thêm tín hiệu
`hidden_classes` không đụng thứ hạng hay nội dung trả về, chỉ thêm một trường.

Chạy lại lần cuối từ `c345e33` (Task 10 — đã có `HIDDEN_TOP_K=3` từ Task 9 và
miễn `KNOWN_UNFLAGGED` cho ca `sla.docx`, tài liệu bị giấu đứng ngoài top-3 lúc
đo — xem SỬA CHỮ dưới cho hạng chính xác).

| tệp | `--role` | r@20 | r@6 | mrr | lat_p50 |
|---|---|---|---|---|---|
| `admin.json` | `admin` | 0,9771 | 0,9633 | 0,7996 | 523 ms |
| `warehouse.json` | `warehouse` | 0,8853 | 0,8716 | 0,7248 | 558 ms |

lat_p50 kho **+35 ms** so admin, đo trên corpus THẬT (~3 900 chunk). Đây là con số
**khác** với phép đo ở Task 5 trên **fixture 2 tài liệu** (+4,2 ms, ×2,50): con số
fixture chứng minh lượt bóng là cỡ mili-giây và không gọi LLM, nhưng KHÔNG nói được
chi phí tuyệt đối trên corpus thật, nơi chân dense đắt hơn. +35 ms là con số thật
của lượt bóng trên dữ liệu sản xuất — không nhân/chia hai con số này vào nhau.

Lệnh sinh (cwd = `backend/`, `.env` đã nạp):

```powershell
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role admin     > evals/results/bao-bi-chan-2026-09-21/admin.json
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role warehouse > evals/results/bao-bi-chan-2026-09-21/warehouse.json
.venv\Scripts\python.exe -m evals.compare_visibility evals/results/bao-bi-chan-2026-09-21/admin.json evals/results/bao-bi-chan-2026-09-21/warehouse.json
```

Kết quả cổng ÂM: `CỔNG ÂM PASS — thương mại 10 ca (lộ 0, không báo chặn 1 — trong
đó 1 ca đã biết được miễn, 0 ca mới), khác 99 ca (kém đi 0, từ chối oan 0)`, exit 0.

Cổng DƯƠNG admin (so `evals/baseline-bge-m3-retrieval.json`):
`GATE PASS — model=0,963 baseline=0,963`, exit 0 — đường admin không hồi quy vì
việc thêm lượt bóng.

**Ca "không báo chặn" duy nhất:** *"bên bán phải đóng gói hàng ra sao trước khi
chuyển đi?"* (mong đợi `sla.docx`) — tài liệu ẩn của nó đứng hạng > 5 trong bản
bóng, ngoài tầm mọi giá trị k đã đo (bảng k=1..5 ở spec §3/§10). Miễn qua
`KNOWN_UNFLAGGED` trong `compare_visibility.py`, có kiểm rữa staleness: cổng sẽ
FAIL, không im lặng giữ miễn, nếu ca này bắt đầu được phát hiện hoặc câu hỏi biến
mất khỏi bộ ca.

Chênh lệch 0,9771 − 0,8853 = 0,0918 ≈ 10/109 = 0,0917: phần sụt truy xuất của kho
đúng bằng 10 ca thương mại rơi về 0, không ca nào khác mất — giống hệt 19b, vì đây
là số đo TRUY XUẤT thuần, không đổi bởi tính năng câu từ chối (tính năng đó chỉ
chạm bước SAU truy xuất, ở `rag_node`/`fuse_answer`).

**SỬA CHỮ (review cuối nhánh, 2026-09-22, I1):** hạng chính xác của tài liệu bị
giấu ở ca "không báo chặn" trên là **HẠNG 6** trong bản bóng (35 ứng viên, đo gốc
bằng script rời; tái lập được bằng `measure_hidden_topk.py` sau khi nâng
`MAX_K=6`) — không phải "không k nào bắt được kể cả top-20" như một số chỗ khác
từng ghi (câu đó sai, do controller viết ra
rồi lan ra 4 chỗ trong repo, đã sửa — xem spec §10 mục Task 11). k=6 BẮT ĐƯỢC ca
này; lý do miễn qua `KNOWN_UNFLAGGED` là ĐÁNH ĐỔI k (k=5 đã sinh 1/99 từ chối oan),
không phải giới hạn của truy xuất.

## Hai script đo — đưa vào repo để bằng chứng tái lập được (sóng sửa cuối, 2026-09-22)

`measure_hidden_topk.py` và `measure_hidden_multiturn.py` trong thư mục này là hai
script CHỈ ĐỌC (không sửa mã production, không gọi LLM) dùng để đo hai quyết định
lớn của nhánh:

- **`measure_hidden_topk.py`** — bảng "bắt được / từ chối oan" theo từng giá trị
  k, bằng chứng cho quyết định `HIDDEN_TOP_K = 3` (Task 9). Tự chứng: hàng k=1
  phải khớp đúng 5/10 · 0/99 (số đo gốc bằng luật hạng-1, Task 8). `MAX_K` nâng
  5→6 ở sóng sửa doc trước merge (D3) để bảng đi tới hạng của ca `sla.docx`; số
  đo ở k=6 (bắt được / từ chối oan) chỉ đáng tin sau khi CHẠY LẠI script này —
  không được đoán trước trong tài liệu.
- **`measure_hidden_multiturn.py`** — đo C1 (sóng sửa cuối): so hai chế độ hợp
  nhất lượt bóng (`with_prev` — câu hiện tại + lượt trước, đúng mã TRƯỚC sửa;
  `current_only` — chỉ câu hiện tại, đúng mã SAU sửa) trên ba loại cặp câu hỏi
  (990 + 400 + 990 cặp, seed 20260922). Tự chứng: chế độ `current_only` phải khớp
  đúng số đo một-lượt của cổng ÂM (9/10 · 0/99).

Cả hai đã `py_compile` sạch nhưng **KHÔNG được chạy lại** khi đưa vào repo — số
liệu đã có đủ trong spec §10 (Task 11); chạy lại tốn Ollama + Postgres không cần
thiết cho việc ghi chép. Muốn tái lập, chạy như MỘT
SCRIPT (không phải `-m` — tên thư mục có dấu `-`, không phải identifier hợp lệ),
từ `backend/` với `DATABASE_URL`/`OLLAMA_URL` đã có trong môi trường:

```powershell
# .env đã nạp (hoặc set tay hai biến trên), cwd = backend/
.venv\Scripts\python.exe evals/results/bao-bi-chan-2026-09-21/measure_hidden_topk.py
.venv\Scripts\python.exe evals/results/bao-bi-chan-2026-09-21/measure_hidden_multiturn.py
```
