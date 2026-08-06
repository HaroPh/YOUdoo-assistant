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

**Result**: Tìm thấy "11434" trong docker-compose.yml tại các dòng sau:

```
docker-compose.yml:12: # localhost:11434 — context lịch sử (old shared instance)
docker-compose.yml:16: # (11434 đã D:\Project chiếm) — context lịch sử
docker-compose.yml:72: # không phải 11434 mặc định — comment giải thích
docker-compose.yml:77: ports: ["11435:11434"] — ĐÚNG: Docker port mapping (host → container)
docker-compose.yml:81: http://localhost:11434 — ĐÚNG: healthcheck internal container port
docker-compose.yml:107: # localhost:11434 — context lịch sử (old shared instance)
```

**Analysis**: 
- Các comment (dòng 12, 16, 72, 107) là context lịch sử, giải thích LÝ DO dùng 11435 — không phải lỗi sót
- Dòng 77 (`ports: ["11435:11434"]`): **CẦN CÓ** — Docker port mapping host 11435 → container 11434
- Dòng 81 (`http://localhost:11434`): **CẦN CÓ** — Healthcheck INSIDE container, dùng internal port

**Các file khác**:
- `.env.example`: KHÔNG có "11434" ✓
- `backend/src/rag/config.py`: KHÔNG có "11434" ✓
- `start-dev.ps1`: KHÔNG có "11434" ✓
- `docs/getting-started.md`: KHÔNG có "11434" ✓

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
