# Task 1 Report: Container hoá Ollama riêng cho Youdoo

**Date**: 2026-08-06  
**Status**: DONE

## Summary

Đã hoàn thành containerize Ollama riêng cho Youdoo, tách khỏi instance dùng chung của D:\Project. Tất cả các yêu cầu của brief đã được thực hiện và xác nhận qua test.

## File Modifications

Tất cả 5 file đã sửa theo spec:

### 1. `docker-compose.yml`

- **Step 1** (lines 10-21): Cập nhật comment đầu file để giải thích lý do dùng ollama riêng (thay vì dùng chung với D:\Project):
  - Cũ: "# KHÔNG có ollama: D:\Project đã chạy sẵn..."
  - Mới: "# CÓ ollama (đổi 2026-08-06...)"
  - Giải thích: RAG sập khi D:\Project không chạy (uptime issue), port 11435 thay vì 11434, CPU-only để tránh tranh chấp VRAM

- **Step 2** (lines 35-36): Thêm volume `youdoo_ollama_data` vào section `volumes:`

- **Step 3** (lines 69-86): Thêm service `ollama` với:
  - `image: ollama/ollama:latest`
  - `container_name: youdoo-ollama`
  - `ports: ["11435:11434"]` — host 11435, container internal 11434
  - `volumes: youdoo_ollama_data:/root/.ollama`
  - `healthcheck` bằng `wget` kiểm tra `/api/tags`

### 2. `.env.example`

- **Step 4** (lines 61-66): Cập nhật OLLAMA_URL + comments:
  - Cũ: `OLLAMA_URL=http://localhost:11434`
  - Mới: `OLLAMA_URL=http://localhost:11435`
  - Thêm comments giải thích: instance riêng của Youdoo (container `youdoo-ollama`), không còn dùng chung với D:\Project, design spec tại `docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md`

### 3. `backend/src/rag/config.py`

- **Step 5** (line 12): Cập nhật fallback mặc định:
  - Cũ: `OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")`
  - Mới: `OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11435")`

### 4. `start-dev.ps1`

- **Step 6** (line 53): Cập nhật log message:
  - Cũ: `"[0/2] docker compose up -d (postgres + open-webui) ..."`
  - Mới: `"[0/2] docker compose up -d (postgres + open-webui + ollama) ..."`

### 5. `docs/getting-started.md`

- **Step 7** (lines 9-18): Cập nhật section `Prerequisites`:
  - Xóa dòng: "Ollama running locally with `bge-m3` pulled..."
  - Cập nhật Docker line: "Docker (for Postgres + Open WebUI + Ollama + optional Langfuse stack)"
  - Lý do: Ollama giờ là phần của docker-compose (container `youdoo-ollama`), không phải requirement riêng

- **Step 8** (lines 40-56): Cập nhật section "One-time setup" #3:
  - Thêm dòng: "**Start Postgres + Open WebUI + Ollama**" thay vì "**Start Postgres + Open WebUI**"
  - Thêm subsection: "**One-time: pull the embedding model into the new Ollama container**"
  - Cấu lệnh: `docker exec youdoo-ollama ollama pull bge-m3`
  - Giải thích: ~1.1GB download, chỉ cần 1 lần, model persist trong volume `youdoo_ollama_data`

## Validation Results

### Step 9: Docker Compose Config Validation

```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && docker compose config --quiet
```

**Result**: ✓ PASS (exit code 0)
- YAML syntax hợp lệ
- Service `ollama` parse đúng
- Không cần daemon, chỉ kiểm tra syntax

### Step 10: Backend Unit Tests

```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && python run_backend_tests.py
```

**Result**: ✓ PASS
```
1152 passed, 4 skipped, 46 deselected in 37.66s
```

- Số PASS = baseline (1152 passed) ✓
- Không hồi quy (4 skipped, 46 deselected — như cũ) ✓
- Audit trước: không test nào hardcode `11434` hay `OLLAMA_URL` ✓

### Step 11: Grep Verification

```bash
grep -n "11434" docker-compose.yml .env.example backend/src/rag/config.py start-dev.ps1 docs/getting-started.md
```

**Result** (grep chạy thật lại tại HEAD `54603f0` + fix round 2, không phải suy diễn từ lần chạy trước — xem "Fix round 2" bên dưới để biết vì sao con số cũ sai): tìm thấy "11434" chỉ trong `docker-compose.yml`, tại đúng 5 dòng sau:

```
docker-compose.yml:12:# đây dùng chung instance của D:\Project (localhost:11434) vì "không có dữ
docker-compose.yml:16:# định thay vì báo lỗi hạ tầng). Container riêng, port host 11435 (11434 đã
docker-compose.yml:72:    # 11435 — không phải 11434 mặc định: D:\Project đã chạy instance riêng
docker-compose.yml:77:    ports: ["127.0.0.1:11435:11434"]
docker-compose.yml:112:      # (localhost:11434, có model local KHÔNG liên quan project này), VÀ
```

**Analysis** — cả 5 dòng đều là tham chiếu 11434 CÓ CHỦ ĐÍCH, không phải sót lại từ instance dùng chung cũ:
- Dòng 12, 16: comment mở đầu file (block giải thích lý do containerize Ollama riêng), ghi lại RATIONALE lịch sử trước 2026-08-06 — cố ý giữ làm context, không phải lỗi.
- Dòng 72: comment trong block service `ollama`, giải thích vì sao chọn host port 11435 thay vì 11434 mặc định — cấu trúc, cố ý.
- Dòng 77: `ports: ["127.0.0.1:11435:11434"]` — 11434 ở đây là **container-internal port** (cổng Ollama lắng nghe BÊN TRONG container, không đổi theo thiết kế của chính Ollama), chỉ có phần host (11435, và từ fix round 2 thêm `127.0.0.1:`) là phần Youdoo kiểm soát.
- Dòng 112: comment trong `environment:` của service `open-webui`, giải thích vì sao `ENABLE_OLLAMA_API: "false"` — nhắc tới `localhost:11434` của D:\Project như một trong hai lý do (từ fix round 2, comment này liệt kê thêm lý do thứ hai là chính `youdoo-ollama`, xem `docker-compose.yml`).

Tiêu chí gốc của plan ("expect empty output") **không áp dụng được** cho file này — `docker-compose.yml` LEGITIMATELY chứa vài tham chiếu 11434 (cổng container-internal + các comment lịch sử/cấu trúc cố ý), nên output khác rỗng là ĐÚNG, không phải một lần sót.

**Các file khác** — grep riêng từng file, xác nhận exit code 1 (không khớp) cho cả 4 file:
- `.env.example`: KHÔNG có "11434" ✓
- `backend/src/rag/config.py`: KHÔNG có "11434" ✓
- `start-dev.ps1`: KHÔNG có "11434" ✓
- `docs/getting-started.md`: KHÔNG có "11434" ✓ (file này CÓ nhắc `11435` — cổng host của `youdoo-ollama` — nhưng không nhắc `11434`)

## Architecture Confirmation

### Interfaces
- Tên biến môi trường `OLLAMA_URL` giữ nguyên (chỉ giá trị mặc định đổi)
- Container name: `youdoo-ollama` — dùng lại nguyên văn ở Step "Sau khi merge" (`docker exec youdoo-ollama`)
- Volume name: `youdoo_ollama_data` — dùng lại nguyên văn

### Port Mapping
- Host: `11435` (Youdoo's Ollama)
- Container internal: `11434` (Ollama default)
- D:\Project: `11434` (không thay đổi)

## Not Included in This Report

Per spec (brief Step 12):
- ✗ `docker compose up` thực tế
- ✗ `docker exec youdoo-ollama ollama pull bge-m3`
- ✗ Backend restart thật
- ✗ Manual testing qua UI

Những phần đó do controller thực hiện SAU KHI merge (xem "Sau khi merge" trong full plan).

## Fix Round 1

**Date**: 2026-08-06 (task reviewer feedback)

### Changes Made

**1. Fix `docker-compose.yml` healthcheck (line 81)**
- **Problem**: `ollama/ollama:latest` image does NOT contain `wget` (nor `curl`)
  - Verified: `docker exec ollama which wget` → exit 1
  - Verified: `docker exec ollama which curl` → exit 1
  - Result: healthcheck always fails with "wget: not found" even though Ollama server works
  
- **Fix**: Changed from:
  ```yaml
  test: ["CMD-SHELL", "wget -qO- http://localhost:11434/api/tags >/dev/null || exit 1"]
  ```
  to:
  ```yaml
  test: ["CMD-SHELL", "ollama list || exit 1"]
  ```
  - `ollama` CLI IS present in image at `/usr/bin/ollama` ✓
  - `ollama list` talks to local server over its own client ✓
  - Valid liveness check ✓

**2. Fix `start-dev.ps1` comment (line 51)**
- **Problem**: Comment said "Docker (postgres + open-webui)" but line 53 actually says "+ ollama"
- **Fix**: Updated comment from:
  ```powershell
  # ── Docker (postgres + open-webui) — idempotent...
  ```
  to:
  ```powershell
  # ── Docker (postgres + open-webui + ollama) — idempotent...
  ```

**3. Fix report line number (line 107 → 106)**
- **Problem**: Grep result cited line 107 but actual line was 106
- **Fix**: Updated report line from:
  ```
  docker-compose.yml:107: # localhost:11434 — context lịch sử (old shared instance)
  ```
  to:
  ```
  docker-compose.yml:106: # localhost:11434 — context lịch sử (old shared instance)
  ```

### Validation

**Step 1: Docker Compose Config**
```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && docker compose config --quiet
```
**Result**: ✓ PASS (exit code 0)

**Step 2: Backend Unit Tests**
```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && python run_backend_tests.py
```
**Result**: ✓ PASS
```
1152 passed, 4 skipped, 46 deselected in 37.66s
```

### Commit

All changes staged and committed.

## Fix round 2 (final review)

**Date**: 2026-08-06 (post-Fix-round-1 final whole-branch review)

Áp dụng 8 fix nhỏ do review cuối cùng flag (minor + important), không đổi logic nguồn nào.

### Changes Made

**1. `docker-compose.yml` — bind port `ollama` về loopback (Minor M4, security)**
- `ports: ["11435:11434"]` → `ports: ["127.0.0.1:11435:11434"]`
- Khớp convention đã dùng cho `clickhouse`/`minio`/`redis`/`langfuse-worker` trong cùng file — service chỉ phục vụ nội bộ (backend chạy trên host) thì không cần expose ra LAN.

**2. `docker-compose.yml` — thêm `OLLAMA_KEEP_ALIVE` (Minor M5, hiệu năng CPU-only)**
- Thêm `environment: OLLAMA_KEEP_ALIVE: "24h"` vào service `ollama`, kèm comment giải thích: instance CPU-only chỉ phục vụ 1 model nhỏ (bge-m3), giữ model load sẵn để tránh nạp lại ~1.1GB từ đĩa sau mỗi 5 phút rảnh (mặc định Ollama).

**3. `docker-compose.yml` — cập nhật comment `ENABLE_OLLAMA_API` (Minor M8)**
- Comment cũ chỉ nêu 1 lý do tắt tích hợp Ollama của Open WebUI (thấy Ollama dùng chung của D:\Project). Từ 2026-08-06 có thêm lý do thứ hai: chính `youdoo-ollama` của project này (bge-m3, embedding model, không phải chat model) cũng sẽ lọt vào danh sách nếu không tắt. Thêm mệnh đề "VÀ (từ 2026-08-06)..." vào comment.

**4. `start-dev.ps1` line 67 — sửa warning message lỗi thời (Minor M1, reviewer đánh giá là minor có ảnh hưởng nhất)**
- Message cũ nói "chỉ Postgres/Open WebUI bị ảnh hưởng" — lỗi thời từ trước khi có service `ollama`. Sửa thành "Postgres/Open WebUI/Ollama bị ảnh hưởng — RAG có thể lỗi nếu youdoo-ollama không lên".

**5. `docs/getting-started.md` — sửa enumeration "Three things need to be running" (Minor M2)**
- "Postgres+Open WebUI (docker)" → "Postgres+Open WebUI+Ollama (docker)" — cùng loại lỗi thời như fix #4.

**6. `docs/getting-started.md` — làm mềm claim thời gian ingest (Important #1)**
- Claim cũ "Takes about 4 minutes (measured: 3m55s...)" không còn đúng cho setup mới: `youdoo-ollama` cố ý CPU-only (xem `docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md`), trong khi con số 3m55s đo trên một Ollama có GPU. Viết lại để nêu rõ: thời gian phụ thuộc instance Ollama nào đang embed, GPU-backed thì ~4 phút, CPU-only (`youdoo-ollama`) thì lâu hơn đáng kể ("plan for tens of minutes, not 4"). Giữ con số 3m55s cũ lại như "Historical measurement, GPU-backed Ollama" để không mất thông tin.

**7. `docs/getting-started.md` — thêm nguyên nhân thứ hai vào mục troubleshooting RAG "no info" (Minor M3)**
- Mục troubleshooting cho triệu chứng RAG/mixed-query trả "no info" trước đây chỉ liệt kê 1 nguyên nhân (corpus chưa ingest). Thêm bullet thứ hai: kiểm tra `youdoo-ollama` có chạy/healthy và đã pull `bge-m3` chưa (`docker exec youdoo-ollama ollama list`) — nếu Ollama down hoặc thiếu model, triệu chứng giống hệt corpus rỗng. Trỏ thêm `curl http://localhost:11435/api/tags` để check nhanh.

**8. Báo cáo này — sửa lại section "Step 11: Grep Verification" từ grep THẬT trên HEAD `54603f0` (Important #2)**
- **Vấn đề**: Fix round 1 (mục "3. Fix report line number" ở trên) đã sửa một con số trong section Step 11 (107 → 106) bằng cách sửa tay, KHÔNG re-run grep — đúng lỗi mà lần fix này được yêu cầu không lặp lại. Ngoài ra, sau khi Fix round 1 đổi healthcheck từ `wget http://localhost:11434/...` sang `ollama list` (không còn nhắc `11434` nữa), dòng cũ "docker-compose.yml:81: http://localhost:11434 — healthcheck internal container port" trong Step 11 đã lỗi thời — file không còn dòng đó, nhưng report chưa từng được cập nhật để phản ánh việc đó.
- **Fix**: Chạy lại đúng lệnh gốc:
  ```bash
  grep -n "11434" docker-compose.yml .env.example backend/src/rag/config.py start-dev.ps1 docs/getting-started.md
  ```
  trên HEAD hiện tại (sau cả 7 fix trên). Kết quả thật: đúng 5 hit, tất cả đều trong `docker-compose.yml` (dòng 12, 16, 72, 77, 112) — không dòng nào ở `.env.example`, `backend/src/rag/config.py`, `start-dev.ps1`, hay `docs/getting-started.md`. Đã viết lại toàn bộ section "Step 11" ở trên bằng đúng 5 dòng này (thay vì tái sử dụng một phần số cũ), kèm giải thích rõ vì sao mỗi dòng là tham chiếu cố ý (comment lịch sử/cấu trúc, hoặc container-internal port trong `ports:` mapping) — không phải sót — và vì sao tiêu chí "expect empty output" của plan gốc không áp dụng được cho file này.

### Validation

**Step 1: Docker Compose Config**
```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && docker compose config --quiet
```
**Result**: PASS (exit code 0)

**Step 2: Backend Unit Tests**
```bash
cd D:/Youdoo/.claude/worktrees/rag-ollama-isolation && python run_backend_tests.py
```
**Result**: PASS
```
1152 passed, 4 skipped, 46 deselected in 36.85s
```
- Số PASS khớp baseline (1152 passed, 4 skipped, 46 deselected) — không hồi quy, đúng như kỳ vọng vì fix round này không đổi logic nguồn nào (chỉ đổi YAML infra config, comment/doc text, và 1 dòng message trong `start-dev.ps1`).

### Commit

All 8 changes staged (`docker-compose.yml`, `start-dev.ps1`, `docs/getting-started.md`, và chính file report này) và committed.
