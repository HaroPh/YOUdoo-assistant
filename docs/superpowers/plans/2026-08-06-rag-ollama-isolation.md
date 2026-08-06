# Tách Ollama (RAG embedding) thành hạ tầng riêng Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Container hoá một instance Ollama riêng cho Youdoo (`youdoo-ollama`,
port host 11435, CPU-only, volume riêng) thay vì dùng chung instance của
`D:\Project` (`localhost:11434`) — đóng lỗ hổng khiến RAG của Youdoo phụ
thuộc vòng đời một tiến trình nó không sở hữu.

**Architecture:** Task 1 sửa TOÀN BỘ file mã nguồn/config đã track trong git
(5 file) trong worktree cô lập, không đụng gì tới tiến trình/container đang
chạy thật. **Việc cập nhật file `.env` thật (không track git), chạy `docker
compose up -d`, pull model, restart backend, và live-verify KHÔNG nằm trong
Task 1 của subagent** — controller (không phải subagent) tự làm sau khi
Task 1 merge, đúng bài học từ sự cố vượt quyền ở plan
`2026-08-05-chitchat-brand-identity-fix` (subagent không nên được giao
quyền quản lý tiến trình sống/dùng chung ngoài phạm vi worktree của nó) và
đúng khuôn đã dùng ở plan `2026-08-05-cross-project-port-collision-fix`.

**Tech Stack:** docker-compose, Ollama, Python 3.12/pytest, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md`

## Global Constraints

- `D:\Project` là repo nguồn READ-ONLY — KHÔNG sửa file nào trong đó, KHÔNG
  đụng tới container không tiền tố `youdoo-` của nó (`ollama`, `postgres`,
  `litellm`, `open-webui`) ở bất kỳ bước nào, kể cả phần "Sau khi merge".
- Port mới: **11435** (host) → 11434 (container, mặc định image, không đổi).
- **KHÔNG cấp GPU** cho service `ollama` mới — không thêm block
  `deploy.resources.reservations.devices` trong `docker-compose.yml`. Đây
  KHÔNG phải một bước tùy chọn, mà là toàn bộ cơ chế cách ly VRAM (không
  khai báo GPU passthrough → Docker tự chạy CPU-only).
- KHÔNG sửa các doc lịch sử đã merge trước plan này
  (`docs/superpowers/plans|specs/*.md`) dù chúng nhắc `11434`/"dùng chung
  Ollama" — giữ nguyên làm biên bản, đúng quy ước dự án.
- KHÔNG re-ingest RAG corpus, KHÔNG đổi `RAG_EMBED_PROVIDER` — nằm ngoài
  phạm vi (xem spec §2).
- **KHÔNG có bước nào trong Task 1 được khởi động lại, dừng, hay quản lý
  tiến trình/container thật đang chạy** — chỉ sửa file trong worktree. Việc
  đó thuộc "Sau khi merge", controller tự làm.
- Chạy test: `cd D:/Youdoo/.claude/worktrees/<worktree-name>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
  (thay đúng path worktree được cấp — KHÔNG phải `D:/Youdoo/backend`).
- Comment/docstring trong repo này viết tiếng Việt.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `docker-compose.yml` | Viết lại comment đầu file (lý do dùng chung Ollama → lý do cách ly); thêm volume `youdoo_ollama_data`; thêm service `ollama` |
| `.env.example` | `OLLAMA_URL` → `11435`, comment giải thích |
| `backend/src/rag/config.py` | Fallback mặc định của `OLLAMA_URL` (khi biến môi trường không được set) → `11435` — phát hiện khi audit file trong lúc viết plan này, spec không liệt kê riêng nhưng cùng lớp thay đổi (giữ đồng bộ với `.env.example`, đúng cách plan port-collision trước đó xử lý fallback trong code) |
| `start-dev.ps1` | Sửa dòng log cho khớp thực tế (bản thân logic không đổi — `docker compose up -d` đã tự kéo theo service mới) |
| `docs/getting-started.md` | Prerequisites + bước "One-time setup" #3: Ollama giờ là một phần của `docker compose up -d`, thêm bước pull `bge-m3` một lần |
| `docs/superpowers/plans/2026-08-06-rag-ollama-isolation-report.md` (mới) | Report Task 1 (phần worktree) — controller thêm phần live-verify sau merge |

---

### Task 1: Container hoá Ollama riêng cho Youdoo

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `backend/src/rag/config.py`,
  `start-dev.ps1`, `docs/getting-started.md`
- Test: `backend/tests/` (chạy lại toàn bộ unit — thay đổi là fallback
  config, không phải logic mới cần test riêng; đã audit trước: không test
  nào hardcode `11434`/`OLLAMA_URL`)
- Create: `docs/superpowers/plans/2026-08-06-rag-ollama-isolation-report.md`

**Interfaces:** Không có API/hàm mới. Tên biến môi trường `OLLAMA_URL` giữ
nguyên xuyên suốt — chỉ giá trị mặc định đổi từ `http://localhost:11434`
sang `http://localhost:11435`. Tên volume mới `youdoo_ollama_data`, tên
container mới `youdoo-ollama` — hai giá trị này Task "Sau khi merge" sẽ
dùng lại nguyên văn khi chạy `docker exec`/`curl`, phải khớp chính xác.

- [ ] **Step 1: Sửa comment đầu `docker-compose.yml`**

Tìm khối (dòng 10-17):
```
# KHÔNG có ollama: D:\Project đã chạy sẵn một instance ollama dùng chung
# (localhost:11434, đã pull sẵn bge-m3). Ollama chỉ là model server, không có
# dữ liệu cần cách ly theo project — dựng thêm một container thứ hai ở đây chỉ
# tốn thêm ~1.2GB+ disk/VRAM mà không mang lại lợi ích gì, nên dùng chung thay
# vì trùng lặp. .env.example: OLLAMA_URL đã trỏ thẳng vào instance dùng chung
# đó (khác với litellm/open-webui — hai cái đó bị bỏ vì hoãn sang kế hoạch
# khác, không phải vì dùng chung).
#
```
Đổi thành:
```
# CÓ ollama (đổi 2026-08-06 — xem
# docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md): trước
# đây dùng chung instance của D:\Project (localhost:11434) vì "không có dữ
# liệu cần cách ly". Live-test 2026-08-06 lộ ra lý do đó bỏ sót khía cạnh
# uptime — RAG sập khi D:\Project không chạy, và ở luồng mixed còn sập MỘT
# CÁCH IM LẶNG (fuse_answer nuốt lỗi, trả lời như thể chính sách không quy
# định thay vì báo lỗi hạ tầng). Container riêng, port host 11435 (11434 đã
# bị D:\Project chiếm), volume riêng youdoo_ollama_data, KHÔNG cấp GPU (máy
# dev dùng GPU cho Ollama của D:\Project chạy qwen3:8b — không khai báo GPU
# passthrough ở đây để tự chạy CPU-only, tránh tranh chấp VRAM). Chỉ cần
# pull bge-m3 (~1.1GB, nhỏ hơn nhiều qwen3:8b) — xem docs/getting-started.md.
#
```

- [ ] **Step 2: Thêm volume `youdoo_ollama_data`**

Tìm khối:
```yaml
volumes:
  youdoo_postgres_data:
    driver: local
  youdoo_open_webui_data:
    driver: local
```
Đổi thành:
```yaml
volumes:
  youdoo_postgres_data:
    driver: local
  youdoo_ollama_data:
    driver: local
  youdoo_open_webui_data:
    driver: local
```

- [ ] **Step 3: Thêm service `ollama`**

Tìm khối cuối service `postgres` (kết thúc bằng `restart: unless-stopped`
ngay trước dòng trống rồi tới `open-webui:`):
```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-admin}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  open-webui:
```
Đổi thành (thêm service `ollama` xen giữa, giữ nguyên phần còn lại):
```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-admin}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    container_name: youdoo-ollama
    # 11435 — không phải 11434 mặc định: D:\Project đã chạy instance riêng
    # của nó ở đó. KHÔNG khai báo GPU passthrough (không có block
    # deploy.resources.reservations.devices) — instance này chỉ cần embed
    # bge-m3 (~1.1GB), để CPU-only tránh tranh chấp VRAM với Ollama của
    # D:\Project (đang giữ GPU cho qwen3:8b).
    ports: ["11435:11434"]
    volumes:
      - youdoo_ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:11434/api/tags >/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  open-webui:
```

- [ ] **Step 4: Sửa `.env.example`**

Tìm khối:
```
# ─── RAG ─────────────────────────────────────────────────────────────────────
# RAG_DB_DSN mặc định lấy DATABASE_URL ở trên — dùng chung DB với sổ ngân sách.
OLLAMA_URL=http://localhost:11434
```
Đổi thành:
```
# ─── RAG ─────────────────────────────────────────────────────────────────────
# RAG_DB_DSN mặc định lấy DATABASE_URL ở trên — dùng chung DB với sổ ngân sách.
# OLLAMA_URL: instance RIÊNG của Youdoo (container youdoo-ollama trong
# docker-compose.yml), KHÔNG còn dùng chung với D:\Project (đổi 2026-08-06,
# xem docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md).
OLLAMA_URL=http://localhost:11435
```

- [ ] **Step 5: Sửa fallback trong `backend/src/rag/config.py`**

Tìm dòng:
```python
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
```
Đổi thành:
```python
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11435")
```

- [ ] **Step 6: Sửa dòng log trong `start-dev.ps1`**

Tìm dòng:
```powershell
Write-Host "[0/2] docker compose up -d (postgres + open-webui) ..." -ForegroundColor Green
```
Đổi thành:
```powershell
Write-Host "[0/2] docker compose up -d (postgres + open-webui + ollama) ..." -ForegroundColor Green
```

- [ ] **Step 7: Sửa `docs/getting-started.md` — Prerequisites**

Tìm khối:
```
## Prerequisites

- Docker (for Postgres + Open WebUI + optional Langfuse stack)
- Python 3.11, with `backend/.venv` already set up (`pip install -r
  backend/requirements.txt` if not)
- Ollama running locally with `bge-m3` pulled (`ollama pull bge-m3`) — used
  for RAG embeddings regardless of which LLM provider is active
- A real Odoo instance reachable at the URL in your `.env` (`ODOO_URL`)
- API keys for at least one LLM provider (`GOOGLE_API_KEY` / `GROQ_API_KEY`
  / `OPENROUTER_API_KEY`) in `.env`
```
Đổi thành:
```
## Prerequisites

- Docker (for Postgres + Open WebUI + Ollama + optional Langfuse stack)
- Python 3.11, with `backend/.venv` already set up (`pip install -r
  backend/requirements.txt` if not)
- A real Odoo instance reachable at the URL in your `.env` (`ODOO_URL`)
- API keys for at least one LLM provider (`GOOGLE_API_KEY` / `GROQ_API_KEY`
  / `OPENROUTER_API_KEY`) in `.env`
```

- [ ] **Step 8: Sửa `docs/getting-started.md` — bước "One-time setup" #3**

Tìm khối:
```
3. **Start Postgres + Open WebUI** (default `docker compose up` does NOT
   include Langfuse — that's behind the `observability` profile, optional
   for UI testing):

   ```powershell
   docker compose up -d
   # optional, only if you want real traces:
   # docker compose --profile observability up -d
   ```
```
Đổi thành:
```
3. **Start Postgres + Open WebUI + Ollama** (default `docker compose up`
   does NOT include Langfuse — that's behind the `observability` profile,
   optional for UI testing):

   ```powershell
   docker compose up -d
   # optional, only if you want real traces:
   # docker compose --profile observability up -d
   ```

   **One-time: pull the embedding model into the new Ollama container**
   (~1.1GB download, only needed once — the model persists in the
   `youdoo_ollama_data` volume across restarts):

   ```powershell
   docker exec youdoo-ollama ollama pull bge-m3
   ```
```

- [ ] **Step 9: `docker compose config` phải hợp lệ**

Run: `cd D:/Youdoo/.claude/worktrees/<worktree-name> && docker compose config --quiet`
Expected: không lỗi (exit 0) — xác nhận YAML hợp lệ và service `ollama`
parse đúng, không cần daemon tạo container thật.

- [ ] **Step 10: Chạy toàn bộ test unit — phải PASS, không hồi quy**

Run: `cd D:/Youdoo/.claude/worktrees/<worktree-name>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ, số PASS không thấp hơn baseline đo được ở đầu
phiên làm việc.

- [ ] **Step 11: Grep xác nhận không còn "11434" sót trong file vừa sửa**

Run: `cd D:/Youdoo/.claude/worktrees/<worktree-name> && grep -n "11434" docker-compose.yml .env.example backend/src/rag/config.py start-dev.ps1 docs/getting-started.md`
Expected: KHÔNG có kết quả nào (empty output). Lưu ý: KHÔNG chạy grep này
trên `docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-design.md`
hay `docs/superpowers/plans/2026-07-29-sp1b-port-business-layer.md` — hai
file lịch sử đó CỐ Ý giữ nguyên "11434", không phải lỗi sót.

- [ ] **Step 12: Viết report**

Tạo `docs/superpowers/plans/2026-08-06-rag-ollama-isolation-report.md` gồm:
xác nhận cả 5 file đã sửa (liệt kê file:dòng cụ thể), kết quả
`docker compose config` (Step 9), kết quả `pytest` đầy đủ (Step 10), kết
quả grep (Step 11). **KHÔNG bao gồm phần chạy `docker compose up`, pull
model, hay restart backend thật** — phần đó controller viết report riêng
SAU KHI merge (xem "Sau khi merge" cuối plan này).

- [ ] **Step 13: Commit**

```bash
git add docker-compose.yml .env.example backend/src/rag/config.py start-dev.ps1 docs/getting-started.md docs/superpowers/plans/2026-08-06-rag-ollama-isolation-report.md
git commit -m "feat(infra): container hoá Ollama riêng cho Youdoo, tách khỏi instance dùng chung với D:\Project"
```

---

## Sau khi merge (KHÔNG phải việc của subagent/Task 1 — controller tự làm)

Sau khi nhánh này merge vào `main`, controller (không dispatch subagent) tự
thực hiện, TRỰC TIẾP trên `D:\Youdoo` (repo chính, không phải worktree):

1. Sửa file `.env` THẬT (không track git):
   ```
   OLLAMA_URL=http://localhost:11435
   ```
2. `docker compose up -d` từ `D:\Youdoo` — xác nhận `youdoo-ollama` lên
   `healthy` bằng `docker ps`. Không đụng tới bất kỳ container nào không
   tiền tố `youdoo-` (kiểm tra `docker ps` trước/sau để đối chiếu uptime
   của container `ollama`/`postgres`/`litellm`/`open-webui` của
   `D:\Project` không đổi).
3. `docker exec youdoo-ollama ollama pull bge-m3`, xác nhận bằng
   `curl http://localhost:11435/api/tags` thấy `bge-m3` trong danh sách.
4. Dừng tiến trình backend đang chạy (controller tự sở hữu, đã start
   trong phiên làm việc trước đó qua cổng 8002) bằng
   `Stop-Process` hợp pháp trên PID controller tự biết.
5. Khởi động lại qua `.\start-dev.ps1` từ `D:\Youdoo` (nạp `.env` mới,
   forward `OLLAMA_URL=http://localhost:11435` vào tiến trình backend).
6. Xác nhận bằng lệnh/gọi API thật (không suy đoán):
   - `curl http://localhost:8002/health` → `agent_ready: true`.
   - Gọi lại đúng 2 câu hỏi đã lỗi trong báo cáo kiểm thử agent cùng ngày
     (dùng `scratchpad/call_agent.py` đã có sẵn từ phiên trước):
     - "Chính sách hoàn hàng quy định bao nhiêu ngày?" (luồng `rag` thuần)
       — kỳ vọng KHÔNG còn "tính năng tra cứu tài liệu tạm thời gặp sự
       cố", có nội dung chính sách thật.
     - "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này
       có bị tạm dừng xử lý không?" (luồng `mixed`) — xác nhận câu trả
       lời không còn khả năng lẫn với lỗi hạ tầng đã ngưng tồn tại (dù
       nội dung cuối cùng có thể vẫn là "không đủ căn cứ" nếu chính sách
       thật sự không quy định — đó là kết quả hợp lệ, khác với lỗi hạ
       tầng bị nuốt).
   - Một câu hỏi RAG đã có kết quả tốt ở báo cáo trước (ví dụ câu hỏi
     tương đương "SLA giao hàng") — xác nhận chất lượng câu trả lời không
     hồi quy qua instance Ollama mới.
7. Ghi kết quả các bước 1-6 vào chính report Task 1 (thêm mục mới, không
   tạo file report thứ hai) — đúng khuôn đã dùng ở plan
   `2026-08-05-cross-project-port-collision-fix`.

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1 vấn đề (Ollama phục vụ rag/embed.py + erp_query/sync_index.py) | Không cần task riêng — cả hai đọc chung `OLLAMA_URL`, Task 1 Step 4-5 đổi giá trị đó là đủ cho cả hai |
| §2 quyết định (container hoá, port 11435, không GPU, không migrate, không đổi provider, không sửa D:\Project) | Task 1 Step 1-8; Global Constraints |
| §3 file bị chạm | Task 1 Step 1, 4, 6, 7-8 khớp đúng danh sách spec; Step 5 (`config.py`) là bổ sung phát hiện khi audit lúc viết plan — cùng lớp thay đổi (fallback), không mở rộng phạm vi |
| §4 rủi ro & xử lý lỗi | Global Constraints (port cố định 11435, không service nào khác dùng); "Sau khi merge" mục 2-3 |
| §5 kiểm chứng | Task 1 Step 9-11 (phần worktree); "Sau khi merge" mục 2-6 (phần live) |
| §6 tiêu chí hoàn thành | Task 1 Step 9-12; "Sau khi merge" toàn bộ |

**Placeholder scan:** Không còn "TBD"/"TODO"/"tương tự Task N" — mọi bước
đều có nội dung Tìm khối/Đổi thành cụ thể hoặc lệnh chạy thật kèm kết quả
kỳ vọng.

**Type consistency:** `OLLAMA_URL` giữ nguyên tên biến môi trường xuyên
suốt (docker-compose không đọc biến này — service `ollama` không cần nó,
chỉ backend/erp_query đọc). `youdoo-ollama` (container name) và
`youdoo_ollama_data` (volume name) dùng nhất quán giữa Task 1 Step 3 và
phần "Sau khi merge" mục 2-3.
