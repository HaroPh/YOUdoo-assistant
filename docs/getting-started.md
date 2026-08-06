# Getting Started — Running Youdoo Locally to Test in the UI

Every step below was run and verified against a real backend + real Odoo
instance while writing this doc (2026-08-06) — including two real startup
bugs found and fixed along the way (see Troubleshooting). If a step here
stops matching reality, trust the error message over this doc and update
it.

## Prerequisites

- Docker (for Postgres + Open WebUI + optional Langfuse stack)
- Python 3.11, with `backend/.venv` already set up (`pip install -r
  backend/requirements.txt` if not)
- Ollama running locally with `bge-m3` pulled (`ollama pull bge-m3`) — used
  for RAG embeddings regardless of which LLM provider is active
- A real Odoo instance reachable at the URL in your `.env` (`ODOO_URL`)
- API keys for at least one LLM provider (`GOOGLE_API_KEY` / `GROQ_API_KEY`
  / `OPENROUTER_API_KEY`) in `.env`

## One-time setup

1. **Copy `.env.example` to `.env`** at the repo root and fill in real
   values (Odoo credentials, at least one LLM API key, Postgres password).
   `docker-compose.yml`, `backend/run.py`, and
   `mcp-servers/odoo/server.py` all read from process environment
   variables — none of them auto-load `.env`, so it must be loaded into
   the shell before starting anything (see "Every time you start" below).

2. **Give `mcp-servers/odoo` its own virtualenv** (it needs
   `psycopg2-binary`, which isn't in `backend/`'s venv — `backend` uses
   `psycopg` v3 instead):

   ```powershell
   cd mcp-servers\odoo
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   cd ..\..
   ```

3. **Start Postgres + Open WebUI** (default `docker compose up` does NOT
   include Langfuse — that's behind the `observability` profile, optional
   for UI testing):

   ```powershell
   docker compose up -d
   # optional, only if you want real traces:
   # docker compose --profile observability up -d
   ```

4. **Index the RAG corpus into Postgres — required once, the table starts
   empty.** Without this, every RAG/mixed scenario below will silently
   return "no info" instead of a real answer (confirmed while writing this
   doc — `rag_chunks` had 0 rows on a fresh checkout). From `backend/`,
   with `.env` loaded (see step below):

   ```powershell
   python -m src.rag.ingest src/rag/seed
   ```

   Takes about 4 minutes (measured: 3m55s for the full 17-document, ~3,300
   -chunk seed corpus via Ollama). One-time — `ingest_path` skips files
   whose content hash hasn't changed, so re-running later is fast and safe.

## Every time you start

Three things need to be running: Postgres+Open WebUI (docker, see above),
`mcp-odoo`, and the `backend` itself. Each of the latter two needs `.env`
loaded into its shell process first — open two separate terminals.

**Terminal 1 — mcp-odoo:**

```powershell
. .\scripts\load-env.ps1
cd mcp-servers\odoo
.\.venv\Scripts\python.exe server.py
```

Expect `Uvicorn running on http://0.0.0.0:8003`.

**Terminal 2 — backend:**

```powershell
. .\scripts\load-env.ps1
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

`Ctrl+C` in each of the two Python terminals, then `docker compose down`
(add `--profile observability` if you started that too).

## Troubleshooting

- **`KeyError: 'ODOO_URL'` (or similar) on startup** — `.env` wasn't
  loaded into that shell's process before running `python server.py` /
  `python run.py`. Re-run `. .\scripts\load-env.ps1` in that same
  terminal, then start the service again (the dot at the start of the
  command is required — it loads variables into the *current* session,
  not a throwaway child process).
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
- **A scenario needs a write action and gets refused outright** — the
  write kill-switch (`erp_ai.write_actions_enabled` in Odoo → Settings →
  Technical → System Parameters) defaults to **off**. That refusal is the
  correct behavior, not a bug — see `manual-test-scenarios.md` scenario 7
  before turning it on.
