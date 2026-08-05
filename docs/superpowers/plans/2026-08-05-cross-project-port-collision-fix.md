# Đổi port backend + mcp-odoo — tránh trùng mặc định với D:\Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đổi port mặc định backend FastAPI (8000→8002) và mcp-odoo SSE
server (8001→8003, đồng thời chuyển từ hardcode sang đọc env var
`MCP_ODOO_PORT`) — đóng lỗ hổng khiến backend Youdoo từng vô tình nhận
nhầm request test của `D:\Project` do trùng port mặc định.

**Architecture:** Task 1 sửa TOÀN BỘ file mã nguồn/config đã track trong
git (8 file, 9 điểm) trong worktree cô lập, không đụng gì tới tiến trình
đang chạy thật. **Việc cập nhật file `.env` thật (không track git) và
restart tiến trình backend/mcp-odoo đang chạy KHÔNG nằm trong task nào của
subagent** — controller (không phải subagent) tự làm sau khi Task 1 merge,
theo đúng bài học từ sự cố vượt quyền ở plan
`2026-08-05-chitchat-brand-identity-fix` (subagent không nên được giao
quyền quản lý tiến trình sống/dùng chung ngoài phạm vi worktree của nó).

**Tech Stack:** Python 3.12, pytest, FastMCP, FastAPI, docker-compose.

**Spec:** `docs/superpowers/specs/2026-08-05-cross-project-port-collision-fix-design.md`

## Global Constraints

- `D:\Project` là repo nguồn READ-ONLY — KHÔNG được sửa bất kỳ file nào
  trong đó, dù cùng mắc lỗi trùng port.
- KHÔNG sửa `ODOO_URL` (port 8069) — dùng chung Odoo thật có chủ đích với
  `D:\Project`, khác lớp với 2 port đang sửa.
- KHÔNG sửa các doc lịch sử (`docs/superpowers/plans|specs/*.md` đã merge
  trước plan này) dù chúng nhắc "8000"/"8001" — giữ nguyên làm biên bản.
- Port mới: backend `8002`, mcp-odoo `8003` (tiếp nối pattern +2 đã dùng
  cho UI 3000→3002).
- `MCP_ODOO_PORT` là biến môi trường MỚI — `mcp-servers/odoo/server.py`
  hiện hardcode `port=8001` cứng, không đọc biến nào; phải đổi sang đọc
  `os.environ.get("MCP_ODOO_PORT", "8003")`.
- **KHÔNG có bước nào trong Task 1 được khởi động lại, dừng, hay quản lý
  tiến trình backend/mcp-odoo thật đang chạy** — chỉ sửa file trong
  worktree. Việc đó thuộc phần "Sau khi merge" ở cuối plan, controller tự
  làm.
- Chạy test: `cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
  (thay đúng path worktree được cấp — KHÔNG phải `D:/Youdoo/backend`).
- Comment/docstring trong repo này viết tiếng Việt.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `.env.example` | Template: `BACKEND_PORT=8002`, `MCP_ODOO_URL` port 8003, thêm `MCP_ODOO_PORT=8003` |
| `backend/run.py` | fallback `BACKEND_PORT` |
| `backend/src/agents/erp_agent.py` | fallback `MCP_ODOO_URL` |
| `backend/tests/live_verify_common.py` | `BASE_URL` đọc từ `BACKEND_PORT` |
| `docker-compose.yml` | fallback `BACKEND_PORT` trong service `open-webui` |
| `backend/src/main.py`, `backend/jobs/__main__.py`, `backend/tests/jobs/test_cli.py` | Sửa comment/docstring nhắc port cũ |
| `mcp-servers/odoo/server.py` | Đổi hardcode `port=8001` sang đọc `MCP_ODOO_PORT` |
| `docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md` (mới) | Report Task 1 (test) — KHÔNG có phần đo thật live process, phần đó ở report riêng do controller viết sau merge |

---

### Task 1: Sửa toàn bộ 9 điểm tham chiếu port cũ trong file đã track git

**Files:**
- Modify: `.env.example`, `backend/run.py`, `backend/src/agents/erp_agent.py`,
  `backend/tests/live_verify_common.py`, `docker-compose.yml`,
  `backend/src/main.py`, `backend/jobs/__main__.py`,
  `backend/tests/jobs/test_cli.py`, `mcp-servers/odoo/server.py`
- Test: `backend/tests/` (chạy lại toàn bộ, không file test mới bắt buộc —
  các thay đổi là config/comment/fallback, không phải logic mới cần TDD)
- Create: `docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md`

**Interfaces:** Không có API mới. `BACKEND_PORT`, `MCP_ODOO_URL` giữ
nguyên TÊN biến môi trường (chỉ đổi giá trị mặc định). `MCP_ODOO_PORT` là
biến MỚI, chỉ `mcp-servers/odoo/server.py` đọc.

- [ ] **Step 1: Sửa `.env.example`**

Tìm khối:
```
# ─── Backend HTTP server (kế hoạch C2) ──────────────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```
Đổi `BACKEND_PORT=8000` thành `BACKEND_PORT=8002`.

Tìm khối:
```
# ─── MCP server Odoo (tiến trình riêng, SSE) ─────────────────────────────────
MCP_ODOO_URL=http://localhost:8001/sse
```
Đổi thành:
```
# ─── MCP server Odoo (tiến trình riêng, SSE) ─────────────────────────────────
MCP_ODOO_URL=http://localhost:8003/sse
# Port mcp-servers/odoo/server.py TỰ lắng nghe — phải khớp port trong
# MCP_ODOO_URL ở trên. 8003, không phải 8001 mặc định của D:\Project (cùng
# gốc codebase, trùng port từng gây backend Youdoo nhận nhầm request test
# của D:\Project — xem plan 2026-08-05-cross-project-port-collision-fix).
MCP_ODOO_PORT=8003
```

- [ ] **Step 2: Sửa `backend/run.py`**

Tìm dòng:
```python
        port=int(os.environ.get("BACKEND_PORT", "8000")),
```
Đổi thành:
```python
        port=int(os.environ.get("BACKEND_PORT", "8002")),
```

- [ ] **Step 3: Sửa `backend/src/agents/erp_agent.py`**

Tìm dòng:
```python
MCP_ODOO_URL = os.environ.get("MCP_ODOO_URL", "http://localhost:8001/sse")
```
Đổi thành:
```python
MCP_ODOO_URL = os.environ.get("MCP_ODOO_URL", "http://localhost:8003/sse")
```

- [ ] **Step 4: Sửa `backend/tests/live_verify_common.py`**

`import os` đã có sẵn ở dòng 7 — KHÔNG thêm dòng import mới, chỉ đổi
`BASE_URL`.

Tìm dòng:
```python
BASE_URL = "http://localhost:8000"
```
Đổi thành:
```python
BASE_URL = f"http://localhost:{os.environ.get('BACKEND_PORT', '8002')}"
```

- [ ] **Step 5: Sửa `docker-compose.yml`**

Tìm dòng trong service `open-webui`:
```yaml
      OPENAI_API_BASE_URL: http://host.docker.internal:${BACKEND_PORT:-8000}/v1
```
Đổi thành:
```yaml
      OPENAI_API_BASE_URL: http://host.docker.internal:${BACKEND_PORT:-8002}/v1
```

- [ ] **Step 6: Sửa comment/docstring nhắc port cũ**

`backend/src/main.py`, tìm:
```
Chạy (host, cần mcp-odoo SSE :8001 đang chạy):
```
Đổi thành:
```
Chạy (host, cần mcp-odoo SSE :8003 đang chạy):
```

`backend/jobs/__main__.py`, tìm:
```
# 4 job e2e_* (D:\Project) cần backend :8000 sống (kế hoạch C2, chưa tồn tại
```
Đổi thành:
```
# 4 job e2e_* (D:\Project) cần backend :8002 sống (kế hoạch C2, chưa tồn tại
```

`backend/tests/jobs/test_cli.py`, tìm:
```
                          "ngoài phạm vi, cần backend :8000 sống — kế hoạch "
```
Đổi thành:
```
                          "ngoài phạm vi, cần backend :8002 sống — kế hoạch "
```

- [ ] **Step 7: Sửa `mcp-servers/odoo/server.py`**

Tìm khối docstring:
```
Transport: HTTP/SSE tại port 8001
Connect:   http://mcp-odoo:8001/sse  (từ backend container)
```
Đổi thành:
```
Transport: HTTP/SSE tại port MCP_ODOO_PORT (mặc định 8003 — KHÔNG phải
8001 mặc định của D:\Project, cùng gốc codebase, tránh trùng port từng
gây backend Youdoo nhận nhầm request test của D:\Project).
Connect:   http://mcp-odoo:${MCP_ODOO_PORT:-8003}/sse  (từ backend container)
```

File hiện KHÔNG có `import os` — khối import hiện tại (dòng 10-14) là:
```python
import sys

from mcp.server.fastmcp import FastMCP

from security import forbid_extra_kwargs
```
Đổi thành (thêm `import os` cạnh `import sys`):
```python
import os
import sys

from mcp.server.fastmcp import FastMCP

from security import forbid_extra_kwargs
```

Tìm dòng:
```python
mcp = FastMCP("odoo-mcp", host="0.0.0.0", port=8001)
```
Đổi thành:
```python
mcp = FastMCP("odoo-mcp", host="0.0.0.0",
             port=int(os.environ.get("MCP_ODOO_PORT", "8003")))
```

- [ ] **Step 8: Chạy toàn bộ test — phải PASS**

Run: `cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ, không giảm số PASS so với baseline đã biết trước
khi bắt đầu (ghi lại số PASS ở bước đầu phiên làm việc để đối chiếu).

- [ ] **Step 9: Kiểm tra `docker-compose.yml` vẫn hợp lệ**

Run: `cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && docker compose config --quiet`
Expected: không lỗi (exit 0).

- [ ] **Step 10: Grep xác nhận không còn "8000"/"8001" nào sót trong file đã sửa**

Run: `cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && grep -n "8000\|8001" .env.example backend/run.py backend/src/agents/erp_agent.py backend/tests/live_verify_common.py docker-compose.yml backend/src/main.py backend/jobs/__main__.py backend/tests/jobs/test_cli.py mcp-servers/odoo/server.py`
Expected: KHÔNG có kết quả nào (empty output) — nếu còn dòng nào khớp,
đó là điểm bị bỏ sót, phải sửa trước khi qua Step tiếp theo.

- [ ] **Step 11: Viết report**

Tạo `docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md`
gồm: xác nhận cả 9 điểm đã sửa (liệt kê file:dòng cụ thể), kết quả
`pytest` đầy đủ, kết quả `docker compose config`, kết quả grep Step 10.
**KHÔNG bao gồm phần đo thật restart tiến trình live** — phần đó
controller viết report riêng SAU KHI merge (xem "Sau khi merge" cuối
plan này).

- [ ] **Step 12: Commit**

```bash
git add .env.example backend/run.py backend/src/agents/erp_agent.py backend/tests/live_verify_common.py docker-compose.yml backend/src/main.py backend/jobs/__main__.py backend/tests/jobs/test_cli.py mcp-servers/odoo/server.py docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md
git commit -m "fix(infra): đổi port backend 8000→8002, mcp-odoo 8001→8003 — tránh trùng mặc định với D:\Project"
```

---

## Sau khi merge (KHÔNG phải việc của subagent/Task 1 — controller tự làm)

Sau khi nhánh này merge vào `main`, controller (không dispatch subagent)
tự thực hiện, TRỰC TIẾP trên `D:\Youdoo` (repo chính, không phải worktree):

1. Thêm/sửa vào file `.env` THẬT (không track git, hiện CHƯA có dòng
   `BACKEND_PORT` — chỉ dựa vào fallback cứng cũ trong `run.py`):
   ```
   BACKEND_PORT=8002
   ```
   và sửa `MCP_ODOO_URL=http://localhost:8001/sse` thành
   `MCP_ODOO_URL=http://localhost:8003/sse`, thêm dòng
   `MCP_ODOO_PORT=8003`.
2. Dừng tiến trình backend + mcp-odoo đang chạy (nếu có) — controller tự
   sở hữu các tiến trình này (đã start trong phiên làm việc trước đó),
   dùng cơ chế đã dùng trước (`Get-NetTCPConnection`/`Stop-Process` hợp
   pháp trên tiến trình CHÍNH MÌNH sở hữu).
3. Khởi động lại CẢ HAI từ `D:\Youdoo` (repo chính, code đã merge, không
   path injection): backend (`backend/run.py`) và mcp-odoo
   (`mcp-servers/odoo/server.py`).
4. Xác nhận bằng lệnh hệ thống thật (không suy đoán):
   - Backend lắng nghe ở **8002**, KHÔNG còn gì của Youdoo ở 8000.
   - mcp-odoo lắng nghe ở **8003**, KHÔNG còn gì của Youdoo ở 8001.
   - `curl http://localhost:8002/v1/models` trả về đúng.
5. Cập nhật `docker-compose.yml`'s `open-webui` service đang chạy (nếu
   container cũ trỏ port 8000 cũ đã cache) — `docker compose up -d
   open-webui` để áp lại config mới.
6. Ghi kết quả vào chính report Task 1 (thêm mục mới, không tạo file
   report thứ hai) — theo đúng khuôn đã dùng ở plan
   `2026-08-05-chitchat-brand-identity-fix` (report §8, đo lại hợp pháp
   sau merge).

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1-2 vấn đề + audit đầy đủ (đã làm khi viết spec) | — |
| §3 quyết định port mới + MCP_ODOO_PORT | Task 1 Step 1, 7 |
| §4 9 điểm sửa | Task 1 Step 1-7 |
| §5 kiểm chứng | Task 1 Step 8-10 (phần test/grep); "Sau khi merge" mục 4 (phần live process) |
| §6 tiêu chí hoàn thành | Task 1 Step 8-11; "Sau khi merge" |

**Type consistency:** `BACKEND_PORT`, `MCP_ODOO_URL` giữ nguyên tên biến
môi trường xuyên suốt plan. `MCP_ODOO_PORT` là biến mới duy nhất, chỉ
`mcp-servers/odoo/server.py` đọc — không có nơi nào khác cần biết tên biến
này.
