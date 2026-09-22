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
miễn `KNOWN_UNFLAGGED` cho ca không k nào bắt được).

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
