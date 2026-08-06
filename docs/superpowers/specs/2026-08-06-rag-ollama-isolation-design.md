# Tách Ollama (RAG embedding) thành hạ tầng riêng của Youdoo

**Ngày:** 2026-08-06
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`docker-compose.yml` hiện tại (đầu file, dòng 10-16) ghi rõ một quyết định
có chủ đích: Youdoo **không** chạy container Ollama riêng, dùng chung
instance của `D:\Project` (`localhost:11434`, đã pull sẵn `bge-m3`). Lý do
ghi lại lúc đó: Ollama chỉ là model server, không có dữ liệu cần cách ly
theo project, dựng thêm container thứ hai chỉ tốn thêm ~1.2GB disk/VRAM mà
không có lợi ích gì.

Một buổi live-test thật (2026-08-06, xem báo cáo kiểm thử agent cùng
ngày) cho thấy lý do đó bỏ sót một khía cạnh: **uptime**. Trong suốt phiên
test, `D:\Project`'s docker stack không chạy → Ollama không phản hồi
(`curl http://localhost:11434` timeout) → mọi câu hỏi RAG thuần đều lỗi
("tính năng tra cứu tài liệu tạm thời gặp sự cố"), và tệ hơn, ở luồng
`mixed` (ERP + tài liệu), cùng lỗi đó bị `fuse_answer` nuốt và trả lời như
một kết luận nghiệp vụ hợp lệ ("tài liệu nội bộ không cung cấp thông tin
về...") — không phân biệt được với trường hợp chính sách thật sự không
quy định. Dùng chung nghĩa là khả năng trả lời của Youdoo phụ thuộc vòng
đời một tiến trình nó không sở hữu và không kiểm soát.

Ollama phục vụ đúng 2 việc trong Youdoo, cả hai đều dùng `bge-m3` qua cùng
biến `OLLAMA_URL`:

- `backend/src/rag/embed.py` (`OllamaEmbedder`) — nhúng tài liệu chính
  sách/SOP cho RAG.
- `backend/src/erp_query/sync_index.py` — index ngữ nghĩa cho phân giải
  tên khách hàng/sản phẩm (hiện `ERP_SEMANTIC_RESOLVE=0`, tắt trong
  `.env`, nhưng dùng chung biến môi trường nên sẽ tự động theo instance
  mới nếu bật lại).

Reranker (`BAAI/bge-reranker-v2-m3`, CPU-only, `backend/src/rag/config.py`)
chạy in-process qua transformers, không qua Ollama — không nằm trong phạm
vi việc này.

## 2. Quyết định

- **Container hoá** `ollama/ollama:latest` trong `docker-compose.yml` của
  Youdoo — nhất quán với cách Postgres đã được tách trước đó (cùng lý do:
  vòng đời độc lập). Container tên `youdoo-ollama`, volume riêng
  `youdoo_ollama_data:/root/.ollama`.
- **Port host 11435** (không phải 11434 — đã bị `D:\Project` chiếm),
  container nội bộ vẫn 11434 mặc định của image.
- **Không cấp GPU** cho service này (không thêm block
  `deploy.resources.reservations.devices`). Máy dev có GPU đang phục vụ
  Ollama của `D:\Project` (chạy `qwen3:8b` + 1 model khác, xác nhận qua
  `curl :11434/api/tags` thật). Không khai báo GPU passthrough trong
  Compose khiến container tự chạy CPU-only theo mặc định của Docker —
  `bge-m3` (~1.1GB, xác nhận qua `api/tags` của instance dùng chung hiện
  tại) chạy CPU cho khối lượng nhúng từng câu hỏi/tài liệu của một demo là
  chấp nhận được, và tránh tranh chấp VRAM với instance của Project.
- **Không migrate dữ liệu đã ingest.** `rag_chunks` (~3.300 chunk, ingest
  một lần trước đó) và semantic index của `erp_query` được nhúng bằng
  đúng model weights `bge-m3` công khai trên Ollama library — pull lại
  đúng tag đó vào container mới cho vector giống hệt, không cần re-ingest.
  Sẽ xác minh bằng cách chạy lại câu hỏi RAG thật (§5), không chỉ giả
  định.
- **Healthcheck**: `wget -qO- http://localhost:11434/api/tags` (nội bộ
  container) — cùng kiểu `CMD-SHELL` + `wget` đã dùng cho `clickhouse`
  trong file này; Ollama không có endpoint `/ping` riêng, `/api/tags` trả
  200 khi server sẵn sàng nhận request.
- **Không đổi** cơ chế chọn nhà cung cấp embedding (`RAG_EMBED_PROVIDER`,
  `GeminiEmbedder`) — nằm ngoài phạm vi, đã có quyết định riêng (hoãn dùng
  Gemini vì giới hạn free-tier, xem spec embedding trước đó).
- **Không sửa bất kỳ file nào trong `D:\Project`** (repo nguồn, read-only)
  và không đụng tới các container không tiền tố `youdoo-` của nó (`ollama`,
  `postgres`, `litellm`, `open-webui`).
- **Không tự động hoá việc pull model** trong `start-dev.ps1` — giữ đúng
  quy ước thủ công một-lần đã có sẵn cho các service khác
  (`docs/getting-started.md` bước "One-time setup"); `restart:
  unless-stopped` + volume riêng nghĩa là chỉ cần pull một lần, các lần
  `docker compose up -d` sau tái sử dụng model đã có trong volume.

## 3. File bị chạm

| File | Thay đổi |
|---|---|
| `docker-compose.yml` | Viết lại comment đầu file (dòng 10-16, lý do dùng chung Ollama) thành lý do cách ly mới; thêm volume `youdoo_ollama_data`; thêm service `ollama` (port `11435:11434`, không GPU, volume riêng, healthcheck, `restart: unless-stopped`), đặt cạnh `postgres` |
| `.env` | `OLLAMA_URL=http://localhost:11434` → `http://localhost:11435` |
| `.env.example` | Same, cộng thêm comment ngắn ghi rõ đây là instance riêng của Youdoo, không còn dùng chung |
| `start-dev.ps1` | Sửa dòng log `"[0/2] docker compose up -d (postgres + open-webui) ..."` → thêm `+ ollama` cho khớp thực tế (bản thân lệnh `docker compose up -d` đã tự kéo theo service mới, không cần đổi logic) |
| `docs/getting-started.md` | Prerequisites: bỏ mục "Ollama running locally..." riêng, gộp vào dòng Docker; One-time setup bước 3: đổi tên bước + thêm lệnh `docker exec youdoo-ollama ollama pull bge-m3` (ghi chú ~1.1GB tải lần đầu) |

`README.md` **không cần sửa** — câu duy nhất nhắc Ollama (dòng 124, "dropped
from the chat path in favor of cloud APIs") vẫn đúng, không liên quan tới
hạ tầng embedding.

## 4. Rủi ro & xử lý lỗi

- Nếu `docker exec youdoo-ollama ollama pull bge-m3` thất bại (mạng...):
  RAG degrade đúng như hiện tại (thông báo lỗi tường minh ở node `rag`) —
  không tệ hơn trạng thái trước khi làm việc này.
- Nếu port 11435 đã bị chiếm bởi thứ khác trên máy: `docker compose up -d`
  sẽ báo lỗi rõ ràng ngay lúc đó, không âm thầm định tuyến nhầm như sự cố
  port 8000/8001 trước đây (đã kiểm tra: không service nào trong 2 repo
  dùng 11435).
- Backend đang chạy (tiến trình host, không tự đọc lại `.env`) sẽ không tự
  nhận `OLLAMA_URL` mới — phải dừng và khởi động lại qua `start-dev.ps1`.

## 5. Kiểm chứng

1. `docker compose config --quiet` xanh sau khi sửa `docker-compose.yml`.
2. `docker compose up -d` — xác nhận `youdoo-ollama` lên `healthy`, không
   đụng tới các container của `D:\Project`.
3. `docker exec youdoo-ollama ollama pull bge-m3`, xác nhận bằng
   `curl http://localhost:11435/api/tags` thấy `bge-m3`.
4. Dừng backend hiện tại, khởi động lại qua `start-dev.ps1` với `.env`
   mới.
5. Chạy lại đúng 2 câu hỏi đã lỗi trong báo cáo kiểm thử cùng ngày:
   - "Chính sách hoàn hàng quy định bao nhiêu ngày?" (luồng `rag` thuần) —
     kỳ vọng trả lời có nội dung thật, không còn thông báo lỗi hạ tầng.
   - "S00050 trễ hạn thanh toán 32 ngày, đơn mới của khách này có bị tạm
     dừng xử lý không?" (luồng `mixed`) — kỳ vọng câu trả lời (dù là
     "không đủ căn cứ" hay có nội dung chính sách) không còn khả năng bị
     nhầm với lỗi hạ tầng đã ngưng tồn tại.
6. Kiểm tra không hồi quy chất lượng truy hồi một cách tối thiểu: so một
   câu hỏi RAG đã có kết quả tốt trước đây, xác nhận vẫn trả về nội dung
   hợp lý qua instance mới.

## 6. Tiêu chí hoàn thành

1. `youdoo-ollama` chạy healthy trong `docker-compose.yml` của Youdoo,
   không cấp GPU, có `bge-m3` đã pull, dữ liệu bền qua volume riêng.
2. `OLLAMA_URL` trong `.env`/`.env.example` trỏ về `11435`.
3. Backend chạy lại thành công với cấu hình mới, cả 2 câu hỏi lỗi ở §5
   được xác nhận đã hết lỗi bằng cách gọi thật, không suy đoán.
4. `D:\Project` không bị sửa hay khởi động lại ở bất kỳ bước nào.
