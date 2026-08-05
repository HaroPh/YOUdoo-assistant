# Đổi port backend + mcp-odoo — tránh trùng mặc định với D:\Project

**Ngày:** 2026-08-05
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`D:\Youdoo` được port từ `D:\Project` (cùng gốc codebase), nên nhiều
default port giống hệt nhau. Port UI (3000) đã xử lý trước đó (Youdoo đổi
sang 3002, xem
`docs/superpowers/specs/2026-08-04-fuse-prompt-obligation-penalty-fix-design.md`
và commit `f864082`). Nhưng còn 2 port khác vẫn trùng mặc định:

- **Backend FastAPI**: cả 2 project mặc định `BACKEND_PORT=8000`
  (`backend/run.py:23` cả hai bên: `os.environ.get("BACKEND_PORT", "8000")`).
- **MCP server Odoo (SSE)**: cả 2 project hardcode cứng `port=8001`
  ngay trong code (`mcp-servers/odoo/server.py:16`,
  `FastMCP("odoo-mcp", host="0.0.0.0", port=8001)`) — xác nhận bằng cách
  đọc trực tiếp file tương ứng trong `D:\Project`, không suy đoán.

**Sự cố thật đã xảy ra** (theo báo cáo người dùng): backend `D:\Project`
crash và khởi động lại; backend Youdoo (đang chạy `run.py`) chiếm port
8000 trước. Mọi request test của `D:\Project` trong lúc đó vô tình bị gửi
sang Youdoo mà không ai nhận ra ngay — cả 2 API gần giống hệt nhau
(OpenAI-compatible `/v1`), response vẫn "hợp lệ" về hình thức nên không
có lỗi rõ ràng nào báo hiệu.

`D:\Project` là repo nguồn tham chiếu, READ-ONLY (không được sửa — xem
`reference_youdoo_repo_layout` trong bộ nhớ dự án). Trách nhiệm tách biệt
port hoàn toàn thuộc về Youdoo (bên fork).

## 2. Audit đầy đủ — không chỉ 2 điểm người dùng nêu

Grep toàn repo (loại trừ `docs/superpowers/plans|specs/*.md` lịch sử —
biên bản cũ, không sửa) tìm được **9 điểm** trên 8 file tham chiếu port
cũ, bao gồm 2 hardcode nguy hiểm người dùng chưa nêu tới:

- `backend/tests/live_verify_common.py:15` — `BASE_URL =
  "http://localhost:8000"` — hardcode CỨNG, không qua env var nào, dùng
  bởi 3 script live-verify skill agentic.
- `mcp-servers/odoo/server.py:16` — `port=8001` hardcode ngay trong
  `FastMCP(...)`, không đọc từ bất kỳ env var nào — gốc rễ sâu hơn
  `BACKEND_PORT` (backend ít nhất còn có biến môi trường để ghi đè).

So sánh port mapping trong `docker-compose.yml` của cả 2 project (đọc
trực tiếp cả hai file) xác nhận: mọi port ĐÃ khai báo trong
`docker-compose.yml` của Youdoo (postgres 5434, open-webui 3002, langfuse
3001/3030, clickhouse 8123/9000, minio 9090/9091, redis 6379) đều KHÔNG
trùng với `D:\Project` (postgres 5433, ollama 11434 — dùng CHUNG có chủ
đích không phải trùng lỗi, litellm 4000, open-webui 3000). Ollama
(11434) không phải lỗi — Youdoo cố ý KHÔNG chạy container Ollama riêng,
dùng chung instance của `D:\Project` (đã ghi ở đầu `docker-compose.yml`,
không nằm trong phạm vi sửa). **2 điểm trùng còn lại (backend 8000,
mcp-odoo 8001) đều là tiến trình chạy TRỰC TIẾP trên host (`python
run.py`, `python server.py`), không khai báo trong `docker-compose.yml`
của bên nào** — đây chính xác là lý do chúng lọt qua đợt sửa UI port
trước đó (chỉ rà theo `docker-compose.yml`).

## 3. Quyết định

- **Backend**: `BACKEND_PORT` 8000 → **8002** (tiếp nối pattern +2 đã
  dùng cho UI: 3000→3002).
- **MCP-odoo**: đổi từ hardcode cứng sang đọc biến môi trường
  `MCP_ODOO_PORT`, mặc định **8003** (tiếp nối pattern +2: 8001→8003).
  Không chỉ đổi số — sửa luôn gốc rễ (không cấu hình được) để nếu có lần
  fork tiếp theo, chỉ cần đổi `.env`, không phải sửa code. Cùng lý do,
  `live_verify_common.py`'s `BASE_URL` đổi từ hardcode sang đọc
  `BACKEND_PORT` (biến đã có sẵn) thay vì chỉ đổi số hardcode.
- **KHÔNG đổi** `ODOO_URL` (8069) — dùng chung Odoo thật có chủ đích với
  `D:\Project`, không phải lỗi cùng lớp.
- **KHÔNG sửa** bất kỳ file nào trong `D:\Project` (read-only, ngoài
  phạm vi Youdoo).
- **KHÔNG sửa** các doc lịch sử (`docs/superpowers/plans|specs/*.md` đã
  merge trước đây) dù chúng nhắc "8000"/"8001" — giữ nguyên làm biên bản,
  đúng quy ước dự án.

## 4. File bị chạm (9 điểm, 8 file)

| File | Thay đổi |
|---|---|
| `.env` (thật, không commit) | Thêm `BACKEND_PORT=8002` (hiện chưa có dòng này — code đang chạy nhờ fallback cứng trong `run.py`, không phải từ `.env`); đổi `MCP_ODOO_URL` sang port 8003; thêm `MCP_ODOO_PORT=8003` |
| `.env.example` | `BACKEND_PORT=8000→8002`; `MCP_ODOO_URL` port `8001→8003`; thêm dòng `MCP_ODOO_PORT=8003` |
| `backend/run.py` | fallback `"8000"→"8002"` |
| `backend/src/agents/erp_agent.py` | fallback URL trong `MCP_ODOO_URL` default: port `8001→8003` |
| `backend/tests/live_verify_common.py` | `BASE_URL` hardcode → đọc `BACKEND_PORT` từ env (mặc định 8002) |
| `docker-compose.yml` | `open-webui` service: `${BACKEND_PORT:-8000}` → `${BACKEND_PORT:-8002}` |
| `backend/src/main.py` | Sửa docstring "cần mcp-odoo SSE :8001" → ":8003" |
| `backend/jobs/__main__.py` | Sửa comment "cần backend :8000" → ":8002" |
| `backend/tests/jobs/test_cli.py` | Sửa comment "cần backend :8000" → ":8002" |
| `mcp-servers/odoo/server.py` | `port=8001` hardcode → đọc `os.environ.get("MCP_ODOO_PORT", "8003")`; sửa 2 dòng docstring nhắc "8001" → "8003" |

## 5. Kiểm chứng

1. `pytest` unit-only xanh toàn bộ — không test nào hard-code port cũ
   theo cách sẽ gãy (đã audit `test_cli.py`, chỉ là comment trong lý do
   skip, không phải assertion).
2. Sau khi sửa: khởi động lại backend Youdoo, xác nhận (bằng
   `Get-NetTCPConnection`/`netstat` thật, không suy đoán):
   - Backend lắng nghe ở port **8002**, KHÔNG còn ở 8000.
   - mcp-odoo lắng nghe ở port **8003**, KHÔNG còn ở 8001.
   - Không còn tiến trình Youdoo nào lắng nghe ở 8000 hay 8001.
3. Gọi `curl http://localhost:8002/v1/models` thật — xác nhận backend
   mới vẫn trả lời đúng, không phải chỉ đổi số suông làm hỏng kết nối.
4. `docker compose config --quiet` xanh (docker-compose.yml vẫn hợp lệ
   sau khi sửa biến môi trường tham chiếu).

## 6. Tiêu chí hoàn thành

1. Cả 9 điểm ở §4 đã sửa đúng.
2. `pytest` unit-only xanh toàn bộ, không hồi quy.
3. Backend + mcp-odoo khởi động lại thành công ở port mới (8002/8003),
   xác nhận bằng lệnh hệ thống thật — không còn gì của Youdoo lắng nghe
   ở 8000/8001.
4. `curl` thật xác nhận backend mới hoạt động đúng ở port 8002.
