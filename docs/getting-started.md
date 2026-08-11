# Getting Started — Running Youdoo Locally to Test in the UI

Every step below was run and verified against a real backend + real Odoo
instance while writing this doc (2026-08-06) — including two real startup
bugs found and fixed along the way (see Troubleshooting). If a step here
stops matching reality, trust the error message over this doc and update
it.

## Prerequisites

- Docker (for Postgres + Open WebUI + Ollama + optional Langfuse stack)
- Python 3.11, with `backend/.venv` already set up (`pip install -r
  backend/requirements.txt` if not)
- A real Odoo instance reachable at the URL in your `.env` (`ODOO_URL`), with
  the 4 AI accounts + custom groups created via
  `backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py`
  (needs `ODOO_URL`/`ODOO_DB`/`ODOO_USERNAME`/`ODOO_PASSWORD` for a real
  Odoo *admin* account, plus `AI_ACCOUNT_PASSWORD` — the password the 4 new
  AI accounts will share)
- API keys for at least one LLM provider (`GOOGLE_API_KEY` / `GROQ_API_KEY`
  / `OPENROUTER_API_KEY`) in `.env`

### Role-based access — what a fresh checkout needs (2026-08-09)

This repo enforces role-based access (`admin` / `warehouse` / `accounting`)
end to end: the identity comes from the authenticated Open WebUI login, the
agent filters tools and refuses out-of-department writes deterministically
in code, and the Odoo account for each role backs that up with its own
permissions. A fresh checkout with only the old single-MCP `.env.example`
gets an assistant that refuses everyone — correctly, but with no documented
way out. What's needed beyond the single-role setup:

- **`AI_ACCOUNT_PASSWORD`** — shared password for the 4 AI Odoo accounts
  (`ai-readonly`, `ai-admin`, `ai-warehouse`, `ai-accounting`), created by
  `scripts/odoo_setup_ai_accounts.py`. Pick your own value; never commit it.
- **Three MCP processes, not one**: `MCP_ODOO_URL` (admin, :8003),
  `MCP_ODOO_URL_WAREHOUSE` (:8004), `MCP_ODOO_URL_ACCOUNTING` (:8005).
  `start-dev.ps1` starts all three automatically, each logged into Odoo as
  its own AI account — see "Every time you start" below.
- **`YOUDOO_POLICY_PROFILE`** — which role policy to use
  (`backend/src/agents/roles.py` `PROFILES`); leave unset for the default
  `small-business` profile.
- **`YOUDOO_ROLE_MAP`** — maps an Open WebUI user id to a role
  (`id1:admin,id2:warehouse,id3:accounting`). **An unmapped user is refused
  by design** (fail-closed) — this is not a bug, and it's exactly what a
  fresh checkout with this left blank will show for every account,
  including yours. See "Find a user's id" below to fill it in.
- **`ENABLE_FORWARD_USER_INFO_HEADERS=true`** on the `open-webui` container
  (already set in `docker-compose.yml`'s `open-webui.environment` block) —
  without it, the backend can't see which Open WebUI account sent the
  request at all, and every user is refused regardless of `YOUDOO_ROLE_MAP`.

**Find a user's id:** log into the target Open WebUI account
(http://localhost:3002 by default), send it one message, then check
`logs/backend.log` for the `x-openwebui-user-id` header value on that
request (the header this backend actually keys off). Do this once per role
account you want to test, then fill in `YOUDOO_ROLE_MAP` and restart the
backend.

## One-time setup

1. **Copy `.env.example` to `.env`** at the repo root and fill in real
   values (Odoo credentials, at least one LLM API key, Postgres password,
   `AI_ACCOUNT_PASSWORD` — see "Role-based access" above).
   `docker-compose.yml`, `backend/run.py`, and
   `mcp-servers/odoo/server.py` all read from process environment
   variables — none of them auto-load `.env`, so it must be loaded into
   the shell before starting anything (see "Every time you start" below).

   Then create the 4 AI Odoo accounts + custom groups (idempotent, safe to
   re-run):

   ```powershell
   .\scripts\load-env.ps1
   backend\.venv\Scripts\python.exe scripts\odoo_setup_ai_accounts.py
   ```

   Optional but recommended after any Odoo group/permission change: verify
   the Odoo-side permissions still line up with `backend/src/agents/roles.py`
   (`backend\.venv\Scripts\python.exe
   scripts\check_role_odoo_consistency.py`) — it prints a PASS/GAP table per
   role/tool and documents 4 known gaps where Odoo's own group granularity
   can't fully back the agent-side refusal (see the script's docstring).

2. **Give `mcp-servers/odoo` its own virtualenv** (it needs
   `psycopg2-binary`, which isn't in `backend/`'s venv — `backend` uses
   `psycopg` v3 instead):

   ```powershell
   cd mcp-servers\odoo
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   cd ..\..
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

4. **Index the RAG corpus into Postgres — required once, the table starts
   empty.** Without this, every RAG/mixed scenario below will silently
   return "no info" instead of a real answer (confirmed while writing this
   doc — `rag_chunks` had 0 rows on a fresh checkout). From `backend/`,
   with `.env` loaded (see step below):

   ```powershell
   python -m src.rag.ingest src/rag/seed
   ```

   Timing depends heavily on which Ollama instance is embedding: the
   3m55s figure below was measured on a GPU-backed Ollama. The
   `youdoo-ollama` container this repo now runs (see
   `docs/superpowers/specs/2026-08-06-rag-ollama-isolation-design.md`) is
   deliberately CPU-only, so expect this step to take substantially
   longer on a fresh setup — plan for tens of minutes, not 4. One-time —
   `ingest_path` skips files whose content hash hasn't changed, so
   re-running later is fast and safe.

   (Historical measurement, GPU-backed Ollama: 3m55s for the full
   17-document, ~3,300-chunk seed corpus.)

## Every time you start

Three things need to be running: Postgres+Open WebUI+Ollama (docker), the
`backend` itself, and **mcp-odoo — as THREE separate processes**, one per
role (admin :8003, warehouse :8004, accounting :8005), each logged into
Odoo as its own AI account (`ai-admin` / `ai-warehouse` / `ai-accounting`).
This is what backs the agent-side role filtering with real, separate Odoo
credentials per role — a single shared MCP process would defeat that.

**Fast path — one command, one terminal:**

```powershell
.\start-dev.ps1
```

Brings up docker (idempotent — fine if already running), then all three
`mcp-odoo` role processes and `backend`, waiting for each to actually be
ready (`/health` returning `agent_ready: true`) before declaring success.
If a port is already occupied by a healthy process from a previous run, it
detects that and skips starting a duplicate rather than erroring — this
exact collision happened while writing this doc (started `python run.py`
by hand in a terminal while an earlier background instance still held
:8002) and is what motivated adding the port check. `Ctrl+C` stops only
what it started this run (docker keeps running). Logs land in `logs/`
(`mcp-odoo-admin.log`, `mcp-odoo-warehouse.log`, `mcp-odoo-accounting.log`,
`backend.log`).

**Manual path — same steps, useful for understanding what's happening or
when the script doesn't fit (e.g. you want each service in its own visible
terminal window). Needs THREE mcp-odoo terminals, one per role:**

**Terminal 1 — mcp-odoo (admin):**

```powershell
.\scripts\load-env.ps1
$env:MCP_ODOO_PORT = "8003"; $env:ODOO_USERNAME = "ai-admin"; $env:ODOO_PASSWORD = $env:AI_ACCOUNT_PASSWORD
cd mcp-servers\odoo
.\.venv\Scripts\python.exe server.py
```

Expect `Uvicorn running on http://0.0.0.0:8003`. Repeat in two more
terminals with `MCP_ODOO_PORT=8004`/`ODOO_USERNAME=ai-warehouse` and
`MCP_ODOO_PORT=8005`/`ODOO_USERNAME=ai-accounting` for the other two roles.

**Terminal 4 — backend:**

```powershell
.\scripts\load-env.ps1
cd backend
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe run.py
```

Expect `✓ ERP agent ready — tools: [...]` after `Uvicorn running on
http://0.0.0.0:8002`. `PYTHONUTF8=1` matters: without it, Windows can pick
a non-UTF-8 console encoding for the process and startup crashes on the
`✓` character in that print statement (`UnicodeEncodeError`) — hit and
confirmed while writing this doc, especially likely if you redirect output
to a log file rather than a live terminal.

## Test in the UI

Open **http://localhost:3002**, pick model **"Youdoo ERP Assistant"**
(`erp-assistant`), and start chatting. See
[`manual-test-scenarios.md`](manual-test-scenarios.md) for ready-to-paste
scenarios with known-good real data.

Quick sanity check before running full scenarios — ask "Bạn là ai?"
(who are you); expect "Tôi là Youdoo" in the reply.

## Stopping everything

`Ctrl+C` in each of the four Python terminals (three `mcp-odoo` role
processes + `backend`), then `docker compose down` (add `--profile
observability` if you started that too).

## Troubleshooting

- **`KeyError: 'ODOO_URL'` (or similar) on startup** — `.env` wasn't
  loaded into that shell's process before running `python server.py` /
  `python run.py`. Re-run `.\scripts\load-env.ps1` in that same terminal,
  then start the service again.
- **A port is already in use / bind error** — `.\start-dev.ps1` detects
  this and skips (see above); the manual path doesn't. Check who's
  listening and stop it if it's stale: `Get-NetTCPConnection -LocalPort
  8002 -State Listen` (or 8003), then `Stop-Process -Id <pid> -Force`.
- **`psycopg.OperationalError: ... password authentication failed ...
  port 5433`** — same root cause as above (env not loaded), but the
  symptom looks different: without `DATABASE_URL` from `.env`, code falls
  back to a default that happens to match a *different* project's Postgres
  container (`D:\Project` also runs on this machine, port 5433 vs.
  Youdoo's 5434) — a real cross-project collision documented in
  `docs/superpowers/plans/2026-08-05-cross-project-port-collision-fix.md`.
- **`UnicodeEncodeError` on the `✓ ERP agent ready` line** — see
  `PYTHONUTF8=1` above.
- **RAG/mixed-query scenarios return "no info" / can't find anything** —
  the corpus was never ingested (or Postgres was reset). Re-run the
  one-time ingest step above.
- Also check: is `youdoo-ollama` running and healthy, and was `bge-m3`
  pulled into it (`docker exec youdoo-ollama ollama list`)? RAG needs
  Ollama for embeddings — if it's down or the model was never pulled,
  the symptom looks identical to an empty corpus. See
  `curl http://localhost:11435/api/tags`.
- **A scenario needs a write action and gets refused outright** — the
  write kill-switch (`erp_ai.write_actions_enabled` in Odoo → Settings →
  Technical → System Parameters) defaults to **off**. That refusal is the
  correct behavior, not a bug — see `manual-test-scenarios.md` scenario 7
  before turning it on.
- **"Không xác định được quyền truy cập của bạn" (every message, every
  account)** — expected on a fresh checkout: `YOUDOO_ROLE_MAP` is empty, so
  every user id is unmapped and refused by design (fail-closed), including
  your own admin account. Follow "Find a user's id" above to fill it in.
  If it persists after that, check `ENABLE_FORWARD_USER_INFO_HEADERS=true`
  actually reached the running `open-webui` container (`docker compose up
  -d open-webui` to reload after editing `docker-compose.yml`).
