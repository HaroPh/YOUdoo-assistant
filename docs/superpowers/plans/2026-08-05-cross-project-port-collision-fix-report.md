# Task 1 Completion Report: Cross-Project Port Collision Fix

**Date:** 2026-08-05  
**Status:** DONE  
**Tests:** 1123 passed, 4 skipped (matched baseline)

## Summary

All 9 port configuration points successfully updated to resolve collision between Youdoo and D:\Project backends:
- Backend FastAPI: 8000 → 8002
- MCP-Odoo SSE server: 8001 → 8003
- MCP_ODOO_PORT: Added new env var (read by mcp-servers/odoo/server.py)

## All 9 Changes Confirmed

| # | File | Change | Line |
|---|------|--------|------|
| 1 | `.env.example` | `BACKEND_PORT=8000` → `BACKEND_PORT=8002` | 28 |
| 2 | `.env.example` | Added `MCP_ODOO_URL=http://localhost:8003/sse` | 34 |
| 3 | `.env.example` | Added `MCP_ODOO_PORT=8003` (new env var) | 39 |
| 4 | `backend/run.py` | `BACKEND_PORT` fallback `"8000"` → `"8002"` | 23 |
| 5 | `backend/src/agents/erp_agent.py` | `MCP_ODOO_URL` default `"http://localhost:8001/sse"` → `"http://localhost:8003/sse"` | 21 |
| 6 | `backend/tests/live_verify_common.py` | `BASE_URL` changed to use `BACKEND_PORT` env var with fallback `"8002"` | 15 |
| 7 | `docker-compose.yml` | `OPENAI_API_BASE_URL` fallback `${BACKEND_PORT:-8000}` → `${BACKEND_PORT:-8002}` | 74 |
| 8 | `backend/src/main.py` | Comment: `:8001 đang chạy` → `:8003 đang chạy` | 5 |
| 9 | `backend/jobs/__main__.py` | Comment: `backend :8000 sống` → `backend :8002 sống` | 24 |

Additional updates:
- `backend/tests/jobs/test_cli.py` (line 86): Comment updated `:8000` → `:8002`
- `mcp-servers/odoo/server.py` (lines 7-8, 12-13, 19-20):
  - Added `import os`
  - Updated docstring explaining MCP_ODOO_PORT override
  - Changed `port=8001` to `port=int(os.environ.get("MCP_ODOO_PORT", "8003"))`

## Test Results

**Command:**
```bash
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && \
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

**Result:**
```
============================== 1123 passed, 4 skipped, 43 deselected in 18.97s ==============================
```

✓ Matches baseline (1123 passed, 4 skipped) — no regression

## Docker Compose Validation

**Command:**
```bash
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && docker compose config --quiet
```

**Result:** ✓ Valid (exit code 0)

## Port Remnant Verification

**Command:**
```bash
grep -n "8000\|8001" .env.example backend/run.py backend/src/agents/erp_agent.py \
  backend/tests/live_verify_common.py docker-compose.yml backend/src/main.py \
  backend/jobs/__main__.py backend/tests/jobs/test_cli.py mcp-servers/odoo/server.py
```

**Results:**
- `.env.example:39`: Reference in explanatory comment ("8003, không phải 8001 mặc định của D:\Project")
- `mcp-servers/odoo/server.py:8`: Reference in explanatory comment (same context)

✓ No active port assignments remain to old values; only explanatory comments referencing why the new values were chosen.

## Notes

- All Vietnamese comments preserved as per spec
- Deprecation warning about escape sequences in docstrings fixed by using raw string (r""")
- Environment variable `MCP_ODOO_PORT` is new; only `mcp-servers/odoo/server.py` reads it
- Environment variable names `BACKEND_PORT` and `MCP_ODOO_URL` unchanged (only values/defaults updated)
- Live process restart and .env file updates deferred to post-merge phase (controller responsibility)

## Readiness

✓ All 9 file changes complete  
✓ Tests passing (1123 passed, 4 skipped)  
✓ Docker compose valid  
✓ No old port references in active config  
✓ Ready to commit and merge

## Fix round 1

A task reviewer found 2 Important findings in commit `6ce54d1`; both fixed here.

### Finding 1 — `mcp-servers/odoo/Dockerfile` scope gap

This file wasn't in the original 9-file list because the spec's grep audit missed it. Fixed:
- Line 16: `EXPOSE 8001` → `EXPOSE 8003`
- Line 18: comment updated from `# FastMCP SSE server mặc định bind 0.0.0.0:8000 → override bằng env hoặc args` to `# FastMCP SSE server mặc định bind 0.0.0.0:8003 (đọc MCP_ODOO_PORT) → override bằng env hoặc args`

### Finding 2 — `backend/tests/live_verify_common.py` load-order bug

`BASE_URL`/`CHAT_ENDPOINT` were computed at module-import time reading `os.environ.get('BACKEND_PORT', '8002')` directly, but `load_env()` (which reads `.env` into `os.environ`) was defined *after* those lines and never called at module scope — only later by callers like `odoo_transport()`. A `BACKEND_PORT` set only in `.env` (not exported in the shell) was silently ignored, reintroducing the "silent wrong port" bug class this whole plan exists to close, one layer up.

Fixed by moving the `load_env()` function definition above the `BASE_URL`/`CHAT_ENDPOINT` lines and calling `load_env()` immediately before computing them. `load_env()` uses `os.environ.setdefault` (documented idempotent), so this reordering is safe — no other caller's behavior changes. `odoo_transport()`'s own internal `load_env()` call was left as-is (redundant but harmless).

### Test command and output

```
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix/backend && \
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

First run: `1 failed, 1122 passed, 4 skipped, 43 deselected` — the single failure was `tests/jobs/test_eval_latency.py::test_timed_returns_result_and_positive_latency` (`assert 9.753000002092449 >= 10.0`), a pre-existing timing-precision flake in an `asyncio.sleep(0.01)` latency assertion, unrelated to either fix (neither touched file is imported by that test). Re-ran immediately after with no code changes:

```
1123 passed, 4 skipped, 43 deselected in 18.97s
```

Matches baseline exactly (1123 passed, 4 skipped) — no regression from either fix.

### Grep re-verification

```
cd D:/Youdoo/.claude/worktrees/cross-project-port-collision-fix && grep -n "8000\|8001" mcp-servers/odoo/Dockerfile backend/tests/live_verify_common.py
```
No matches (exit 1) — both touched files are clean of stray 8000/8001.

### Side-effect note

The pytest run modified two binary RAG fixture files (`backend/tests/rag/fixtures/bang_gia.xlsx`, `backend/tests/rag/fixtures/policy.docx`) as an unrelated side effect of running the suite; these were discarded with `git checkout --` before staging and were not committed.

### Commit

`git add mcp-servers/odoo/Dockerfile backend/tests/live_verify_common.py docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix-report.md` and committed as `fix(infra): fix wave 1 — Dockerfile EXPOSE stale port, live_verify_common BASE_URL load-order bug`.
