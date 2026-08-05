# Báo cáo hoàn thành Task 1: Fix xung đột port giữa hai project

**Ngày:** 2026-08-05
**Trạng thái:** DONE
**Test:** 1123 passed, 4 skipped (khớp baseline)

## Tóm tắt

Đã cập nhật xong 12 điểm thay đổi qua 10 file để xử lý xung đột port giữa backend Youdoo và backend D:\Project (cùng gốc codebase):
- Backend FastAPI: 8000 → 8002
- MCP-Odoo SSE server: 8001 → 8003
- MCP_ODOO_PORT: thêm biến môi trường mới (đọc bởi `mcp-servers/odoo/server.py`)

## 9 thay đổi cốt lõi (bảng gốc)

| # | File | Thay đổi | Dòng |
|---|------|--------|------|
| 1 | `.env.example` | `BACKEND_PORT=8000` → `BACKEND_PORT=8002` | 28 |
| 2 | `.env.example` | Thêm `MCP_ODOO_URL=http://localhost:8003/sse` | 37 |
| 3 | `.env.example` | Thêm `MCP_ODOO_PORT=8003` (biến mới) | 42 |
| 4 | `backend/run.py` | Fallback `BACKEND_PORT` `"8000"` → `"8002"` | 23 |
| 5 | `backend/src/agents/erp_agent.py` | Default `MCP_ODOO_URL` `"http://localhost:8001/sse"` → `"http://localhost:8003/sse"` | 21 |
| 6 | `backend/tests/live_verify_common.py` | `BASE_URL` đổi sang đọc biến môi trường `BACKEND_PORT`, fallback `"8002"` | 34 |
| 7 | `docker-compose.yml` | Fallback `OPENAI_API_BASE_URL` `${BACKEND_PORT:-8000}` → `${BACKEND_PORT:-8002}` | 74 |
| 8 | `backend/src/main.py` | Comment: `:8001 đang chạy` → `:8003 đang chạy` | 5 |
| 9 | `backend/jobs/__main__.py` | Comment: `backend :8000 sống` → `backend :8002 sống` | 24 |

*(Ghi chú: dòng của #2, #3, #6 là số dòng SAU khi đã áp cả fix round 1 và fix wave 2 bên dưới — không phải số dòng tại thời điểm commit gốc.)*

Các cập nhật bổ sung (không tính trong bảng 9 dòng trên):
- `backend/tests/jobs/test_cli.py` (dòng 86): comment cập nhật `:8000` → `:8002`
- `mcp-servers/odoo/server.py` (dòng 12, 7, 20):
  - Thêm `import os`
  - Cập nhật docstring giải thích cơ chế override qua `MCP_ODOO_PORT`
  - Đổi `port=8001` thành `port=int(os.environ.get("MCP_ODOO_PORT", "8003"))`

## Kết quả test

**Lệnh:**
```bash
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && \
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

**Kết quả:**
```
============================== 1123 passed, 4 skipped, 43 deselected in 18.97s ==============================
```

Khớp baseline (1123 passed, 4 skipped) — không có regression.

## Kiểm tra docker compose

**Lệnh:**
```bash
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && docker compose config --quiet
```

**Kết quả:** Hợp lệ (exit code 0)

## Kiểm tra dấu vết port cũ (grep)

**Lệnh:**
```bash
grep -n "8000\|8001" .env.example backend/run.py backend/src/agents/erp_agent.py \
  backend/tests/live_verify_common.py docker-compose.yml backend/src/main.py \
  backend/jobs/__main__.py backend/tests/jobs/test_cli.py mcp-servers/odoo/server.py
```

**Kết quả:**
- `.env.example:39` (số dòng tại thời điểm chạy grep gốc): comment giải thích ("8003, không phải 8001 mặc định của D:\Project")
- `mcp-servers/odoo/server.py:8`: comment giải thích (cùng ngữ cảnh)

Không còn giá trị port cũ nào đang được gán thật; chỉ còn comment giải thích lý do chọn giá trị mới.

## Ghi chú

- Toàn bộ comment tiếng Việt được giữ nguyên theo đúng spec
- Đã sửa warning deprecation về escape sequence trong docstring bằng cách dùng raw string (`r"""`)
- Biến môi trường `MCP_ODOO_PORT` là mới; hiện chỉ `mcp-servers/odoo/server.py` đọc nó
- Tên biến môi trường `BACKEND_PORT` và `MCP_ODOO_URL` không đổi (chỉ đổi giá trị/default)
- Việc restart tiến trình thật và cập nhật file `.env` thật được để lại cho giai đoạn hậu-merge (trách nhiệm của controller)

**Lưu ý quan trọng về giai đoạn hậu-merge:** `backend/run.py` và `mcp-servers/odoo/server.py` không tự đọc `.env` (không có `load_dotenv`/`dotenv` nào trong đường import của chúng) — chỉ `docker-compose.yml` (tự nạp `.env` gốc) và code test (`conftest.py`) có "biết" `.env`. Vì vậy bước hậu-merge phải EXPORT `BACKEND_PORT`/`MCP_ODOO_PORT` thật trong shell khởi động backend/mcp-odoo (không chỉ sửa `.env`) — nếu không, tiến trình vẫn chạy đúng port mới NHỜ fallback cứng trong code, không phải nhờ `.env`, và việc `.env` nói gì trở nên vô nghĩa với 2 tiến trình này. Nói cách khác: chỉ sửa `.env` rồi restart backend KHÔNG đảm bảo backend bind đúng port mong muốn nếu sau này ai đó chỉ sửa `.env` mà quên export — lúc đó backend âm thầm dùng fallback cứng trong code còn compose/test lại theo `.env`, đúng dạng lỗi "lệch port âm thầm" mà cả kế hoạch này tồn tại để đóng, chỉ là bị đảo chiều.

## Sẵn sàng merge

- Toàn bộ thay đổi cốt lõi hoàn tất
- Test pass (1123 passed, 4 skipped)
- Docker compose hợp lệ
- Không còn tham chiếu port cũ trong config đang dùng
- Sẵn sàng commit và merge

## Fix round 1

Một reviewer task tìm thấy 2 Important finding trong commit `6ce54d1`; cả hai đã được sửa ở đây.

### Finding 1 — `mcp-servers/odoo/Dockerfile` bị bỏ sót khỏi phạm vi

File này không nằm trong danh sách 9 file gốc vì grep audit của spec đã bỏ sót nó. Đã sửa:
- Dòng 16: `EXPOSE 8001` → `EXPOSE 8003`
- Dòng 18: comment cập nhật từ `# FastMCP SSE server mặc định bind 0.0.0.0:8000 → override bằng env hoặc args` thành `# FastMCP SSE server mặc định bind 0.0.0.0:8003 (đọc MCP_ODOO_PORT) → override bằng env hoặc args`

### Finding 2 — bug thứ tự load trong `backend/tests/live_verify_common.py`

`BASE_URL`/`CHAT_ENDPOINT` được tính tại thời điểm import module, đọc trực tiếp `os.environ.get('BACKEND_PORT', '8002')`, nhưng `load_env()` (hàm đọc `.env` vào `os.environ`) lại được định nghĩa SAU các dòng đó và không được gọi ở cấp module — chỉ được gọi sau này bởi caller như `odoo_transport()`. Một `BACKEND_PORT` chỉ đặt trong `.env` (không export trong shell) sẽ bị bỏ qua một cách âm thầm, tái tạo lại đúng dạng lỗi "sai port âm thầm" mà cả kế hoạch này tồn tại để đóng, chỉ là ở một lớp cao hơn.

Đã sửa bằng cách chuyển định nghĩa hàm `load_env()` lên trên các dòng `BASE_URL`/`CHAT_ENDPOINT` và gọi `load_env()` ngay trước khi tính hai giá trị đó. `load_env()` dùng `os.environ.setdefault` (đã có tài liệu là idempotent), nên việc đổi thứ tự này an toàn — không caller nào khác bị đổi hành vi. Lệnh gọi `load_env()` nội bộ của `odoo_transport()` được giữ nguyên (dư thừa nhưng vô hại).

### Lệnh test và kết quả

```
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && \
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

Lần chạy đầu: `1 failed, 1122 passed, 4 skipped, 43 deselected` — lỗi duy nhất là `tests/jobs/test_eval_latency.py::test_timed_returns_result_and_positive_latency` (`assert 9.753000002092449 >= 10.0`), một flake sẵn có về độ chính xác thời gian trong assertion `asyncio.sleep(0.01)`, không liên quan tới 1 trong 2 fix (không file nào bị sửa được import bởi test đó). Chạy lại ngay sau đó, không đổi code:

```
1123 passed, 4 skipped, 43 deselected in 18.97s
```

Khớp baseline chính xác (1123 passed, 4 skipped) — không có regression từ cả 2 fix.

### Grep xác nhận lại

```
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && grep -n "8000\|8001" mcp-servers/odoo/Dockerfile backend/tests/live_verify_common.py
```
Không có kết quả (exit 1) — cả 2 file đã sửa đều sạch dấu vết 8000/8001.

### Ghi chú tác dụng phụ

Việc chạy pytest làm đổi 2 file fixture nhị phân của RAG (`backend/tests/rag/fixtures/bang_gia.xlsx`, `backend/tests/rag/fixtures/policy.docx`) như một tác dụng phụ không liên quan; các file này đã bị discard bằng `git checkout --` trước khi stage, không nằm trong commit.

### Commit

`git add mcp-servers/odoo/Dockerfile backend/tests/live_verify_common.py docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md` và commit với message `fix(infra): fix wave 1 — Dockerfile EXPOSE stale port, live_verify_common BASE_URL load-order bug`.

## Fix wave (final review)

Whole-branch review cuối cùng (trên commit `ccd6517`) tìm thấy 2 Important finding + 3 Minor finding rẻ tiền; cả 5 đã được sửa trong 1 lượt.

### Finding 1 (Important) — `load_env()` fail cứng khi thiếu `.env`

Sau fix round 1, `load_env()` được gọi vô điều kiện ở cấp module với `open(path)` trần (không guard). Controller đã tái hiện thực nghiệm: đổi tên `.env` đi, `import live_verify_common` raise `FileNotFoundError`. Vì `.env` bị gitignore, một clone mới, một CI checkout, hay một git worktree mới (quy trình chuẩn per-plan của project này) sẽ không có `.env`, và `backend/tests/test_live_verify_common.py` (importer duy nhất của module này trong repo hiện tại) sẽ chuyển từ pass sang collection ERROR.

Đã sửa bằng cách bọc lệnh gọi để `.env` vắng mặt được dung thứ (giống cách `load_dotenv()` trong `conftest.py` đã no-op im lặng khi thiếu file):
```python
try:
    load_env()
except FileNotFoundError:      # .env không track git — vắng mặt là hợp lệ
    pass
```
Đặt ngay tại vị trí `load_env()` đang được gọi (ngay trước dòng `BASE_URL =`), không đổi gì khác trong thân `load_env()` hay lệnh gọi nội bộ của `odoo_transport()`.

**Xác minh thực nghiệm:** đổi tên `.env` ra `.env.tmp-hidden-for-test`, chạy `python -c "import sys; sys.path.insert(0,'backend/tests'); import live_verify_common"` từ venv — import thành công (`IMPORT_OK http://localhost:8002`), không còn raise `FileNotFoundError`. Sau đó đổi tên `.env` trả lại ngay, xác nhận bằng `ls -la .env` (3160 byte, đúng kích thước ban đầu) và `git status --short` (chỉ còn `live_verify_common.py` là M, không có dấu hiệu `.env` bị mất).

### Finding 2 (Important) — entrypoint production không đọc `.env`

Controller xác nhận: `backend/run.py` và `mcp-servers/odoo/server.py` (2 tiến trình mà kế hoạch này renumber) đọc `os.environ` trực tiếp, không có `dotenv`/`load_dotenv` nào trong đường import của chúng — chỉ code test (`backend/tests/conftest.py`) và docker-compose (tự nạp `.env` gốc) thực sự "biết" tới file `.env`. Đây là gap tài liệu, không phải bug code — không cần sửa source. Đã thêm ghi chú giải thích vào phần mô tả giai đoạn hậu-merge của báo cáo này (xem đoạn "Lưu ý quan trọng về giai đoạn hậu-merge" trong mục Ghi chú ở trên) — nội dung đã đồng bộ ở cả 2 nơi (file trong worktree và bản mirror ở `docs/`).

### Finding 3 (Minor) — số dòng lỗi thời trong bảng báo cáo

Bảng "9 thay đổi cốt lõi" trích `.env.example` `MCP_ODOO_URL` là dòng 34 (thực tế đã là dòng 37 sau các dòng thêm ở fix round 1), `MCP_ODOO_PORT` là dòng 39 (thực tế 42), và `live_verify_common.py` `BASE_URL` là dòng 15 (thực tế đã chuyển tới dòng 31 sau fix round 1, và tiếp tục dịch xuống dòng 34 sau fix cho Finding 1 ở trên). Đã cập nhật bảng với số dòng đúng SAU khi toàn bộ fix wave này áp dụng xong (xác nhận lại bằng Read trực tiếp file), và đổi tiêu đề từ "9 thay đổi" thành "12 điểm thay đổi qua 10 file" vì Dockerfile + các thay đổi fix round 1 là bổ sung so với 9 điểm gốc.

### Finding 4 (Minor) — báo cáo viết bằng tiếng Anh, phá vỡ quy ước repo

Mọi báo cáo khác dưới `docs/superpowers/plans/*-report.md` trong repo này đều viết bằng tiếng Việt; báo cáo này trước đó viết bằng tiếng Anh. Đã viết lại toàn bộ báo cáo (cả file trong worktree lẫn bản mirror ở `docs/`) sang tiếng Việt, giữ nguyên toàn bộ nội dung sự kiện (danh sách 12 điểm thay đổi, kết quả test, kiểm tra docker compose, kiểm tra grep, phần fix round 1, và ghi chú mới của Finding 2).

### Finding 5 (Minor) — comment ở `mcp-servers/odoo/Dockerfile:18` lẫn lộn 2 default khác nhau

Comment viết lại ở fix round 1 nói server "mặc định bind 0.0.0.0:8003" — nhưng đó là default CẤU HÌNH của app này, không phải default thật của thư viện FastMCP (thực ra là 8000). Ngoài ra Dockerfile không có `ENV MCP_ODOO_PORT=8003`, nên `EXPOSE 8003` sẽ âm thầm lệch nếu biến này bị override lúc chạy container (tác động thấp — hiện chưa có service compose nào build Dockerfile này). Đã sửa comment thành: `# Đọc MCP_ODOO_PORT (mặc định 8003 — xem server.py); EXPOSE dưới đây phải khớp giá trị mặc định đó`, giữ nguyên `EXPOSE 8003` (đúng với default đã tài liệu hoá).

### Lệnh test và kết quả (fix wave)

```
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && \
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

Kết quả: `1123 passed, 4 skipped` — khớp baseline, không regression.

### Commit

`fix(infra): fix wave 2 (final review) — .env missing tolerance, .env production-reader gap documented, report cleanup`

## 8. Đo lại hợp pháp sau merge (controller tự làm, không delegate)

Sau khi nhánh merge vào `main` (fast-forward `3933b8a..10013fd`, push lên
origin thành công), controller tự thực hiện toàn bộ bước hậu-merge TRỰC
TIẾP trên `D:\Youdoo` (repo chính, không phải worktree) — không dispatch
subagent cho bước này, đúng theo Global Constraints của plan (bài học từ
sự cố vượt quyền ở plan `2026-08-05-chitchat-brand-identity-fix`).

**1. Xác định 2 tiến trình cũ đang chiếm 8000/8001 là của Youdoo, không
phải D:\Project** — trước khi đụng vào bất kỳ tiến trình nào, đã xác minh
bằng lệnh hệ thống thật (`Get-CimInstance Win32_Process`, rồi soi loaded
modules của từng PID qua `Get-Process -Module`): cả PID trên port 8000 lẫn
PID trên port 8001 đều load package từ `D:\Youdoo\backend\.venv\...` — xác
nhận chắc chắn đây là tiến trình Youdoo tự sở hữu (khởi động từ trước
trong phiên làm việc này), không phải tiến trình của `D:\Project`. Chỉ sau
khi xác minh xong mới `Stop-Process -Force` cả hai.

**2. Cập nhật `.env` thật** — thêm `BACKEND_PORT=8002`, đổi `MCP_ODOO_URL`
sang port 8003, thêm `MCP_ODOO_PORT=8003`.

**3. Áp dụng đúng phát hiện Finding 2 (mục Fix wave ở trên) khi khởi động
lại** — vì `backend/run.py` và `mcp-servers/odoo/server.py` không tự đọc
`.env`, controller đã EXPORT toàn bộ biến trong `.env` vào environment của
chính shell khởi động 2 tiến trình (đọc từng dòng `.env`, set qua
`[System.Environment]::SetEnvironmentVariable`) trước khi gọi
`python server.py` / `python run.py` — không chỉ sửa `.env` rồi restart
suông.

**4. Xác nhận bằng lệnh hệ thống thật (`Get-NetTCPConnection`):**
- mcp-odoo: lắng nghe ở **8003**. ✓
- backend: lắng nghe ở **8002**. ✓
- Không còn gì của Youdoo lắng nghe ở **8000** hay **8001**. ✓ (`Get-NetTCPConnection` cho 4 port 8000-8003 chỉ trả về 8002 và 8003)

**5. `curl` thật xác nhận backend mới hoạt động đúng, không chỉ đổi số
suông:**
```
curl http://localhost:8002/v1/models
→ {"object":"list","data":[{"id":"erp-assistant",...}]}

curl -X POST http://localhost:8002/v1/chat/completions ... "Bạn là ai?"
→ "Chào bạn! Tôi là Youdoo, trợ lý ERP nội bộ của bạn. ..."
```
Request đi trọn đường (LLM router + agent graph) trên port mới, và tiện
thể xác nhận luôn brand identity fix (`CHITCHAT_PROMPT`) vẫn hoạt động
đúng trên hạ tầng mới.

**6. `docker-compose.yml`'s `open-webui` service** — container cũ đã tạo
từ trước khi port đổi, nên còn giữ `OPENAI_API_BASE_URL` trỏ port 8000 cũ.
Chạy `docker compose up -d open-webui` để recreate container với giá trị
mới; xác nhận bằng `docker exec youdoo-open-webui printenv
OPENAI_API_BASE_URL` → `http://host.docker.internal:8002/v1`. ✓

**Kết luận:** cả 4 tiêu chí hoàn thành ở spec §6 đều ĐẠT, với bằng chứng
đo thật (không phải suy đoán), toàn bộ đến từ hành động hợp pháp của
controller — không có tiến trình nào bị dừng ngoài phạm vi sở hữu, không
path injection, không delegate quản lý tiến trình sống cho subagent.
