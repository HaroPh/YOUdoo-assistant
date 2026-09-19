# altinkaya-opensource/odoo-mcp

Repo: https://github.com/altinkaya-opensource/odoo-mcp
Investigated at commit `f831d0d1c1712bf2e54d639ddeb34c50005ac3d3` (2026-09-17, branch `16.0` = default). Clone read-only; all paths below are repo-relative.

> **Headline correction up front.** The brief describes this repo as "MCP for Odoo without any external dependencies". That string is the GitHub **About** blurb ("Model Context Protocol (MCP) for Odoo without any external dependencies" — https://github.com/altinkaya-opensource/odoo-mcp). It is **false as a Python statement** and the code contradicts it: `pyproject.toml:11-14` declares `fastmcp>=3.0.0rc1` and `python-dotenv>=1.0`, and `uv.lock` resolves to **76 packages** (fastmcp 3.0.0rc2, mcp 1.26.0, pydantic 2.12.5, httpx, authlib, cryptography, …). **There is no hand-rolled MCP protocol here at all.** The only defensible reading of the tagline is the Odoo-side one the README actually makes: *"No Odoo module installation required. Just point it at any Odoo 12+ instance."* (`README.md:6`) — i.e. no external **Odoo addon**, unlike ivnvxd/mcp-server-odoo which ships a companion Odoo module. Rubric item 2's question "is the MCP protocol implemented by hand?" therefore answers **no** — see §2.

---

## 1. Repo facts

| Fact | Value | Evidence |
|---|---|---|
| Language | Python, `requires-python = ">=3.10"` | `pyproject.toml:6` |
| MCP framework | **FastMCP 3.x** (`from fastmcp import FastMCP`), not the raw SDK, not hand-rolled | `pyproject.toml:12`; `mcp_server_odoo/server.py:5`; `mcp_server_odoo/tools.py:8-9` |
| LOC | **1,627 lines** of Python total across 7 files: `tools.py` 968, `utils.py` 324, `connection.py` 200, `server.py` 76, `config.py` 53, `__main__.py` 5, `__init__.py` 1 | `wc -l mcp_server_odoo/*.py` |
| License | **AGPL-3.0-or-later** | `pyproject.toml:7`; `LICENSE` |
| Version | `1.0.0` (declared), **no git tags, no GitHub Releases** | `pyproject.toml:3`; `git tag --list` empty |
| Last commit | 2026-09-17 `ci: replace OCR with native PR-Agent [skip ci]` | `git log -1` |
| History size | **21 commits total**, first real commit 2026-02-11 `[INIT] project initialized with first commit` | `git rev-list --count HEAD` |
| Stars / forks / watchers | **4 / 5 / 0** | GitHub repo page |
| Open issues / PRs | **0 / 0**; one merged PR (#1, `save_binary_field`, external contributor Ahmet Altinisik, 2026-02-14) | GitHub; `git log` |
| Tests | **None.** No `tests/`, no `conftest.py`, no `[tool.pytest]`, no test deps | `find` + `grep pyproject.toml` |
| CI | **One workflow only** — `.github/workflows/pr-agent.yml`, an LLM PR reviewer running on a self-hosted runner. **No lint job, no test job, no build job.** | `.github/workflows/pr-agent.yml` |
| Local quality gates | `.pre-commit-config.yaml`: ruff + ruff-format, prettier, whitespace/EOF/debug-statement hooks. Not enforced in CI. | `.pre-commit-config.yaml:37-42` |
| Provenance | Substantially AI-authored: commits carry `Co-Authored-By: Claude Opus 4.6` (e.g. `ccd0857`, `f39229e`) | `git show ccd0857 --format=%b` |
| Lineage | `.pre-commit-config.yaml:3-4` excludes `^analysis-mcp-server-odoo/` with the comment `# Ignore the analysis directory (third-party reference code)`. The package name `mcp-server-odoo` and directory `mcp_server_odoo/` **collide with the pre-existing PyPI package** ivnvxd/mcp-server-odoo (https://pypi.org/project/mcp-server-odoo/). Strong evidence this is a deliberate lighter re-implementation of that server after studying it. | `.pre-commit-config.yaml:1-8`; `pyproject.toml:2` |

Activity read: **low-maturity, low-adoption, actively maintained by one company.** Substantive feature work happened in a ~10-week burst (Feb–Apr 2026); everything since 2026-09-15 is CI plumbing for their own PR-review bot. Branch is named `16.0` (Odoo version-branch convention) though README claims Odoo 12+ support.

---

## 2. Architecture

### Module map (dependency direction is strictly one-way, no cycles)

```
__main__.py ──┐                    (python -m mcp_server_odoo)
              ├─> server.py ──> config.py      (env + logging)
[project.scripts]                └─> connection.py ──> config.py
mcp-server-odoo ─┘               └─> tools.py ──> config.py, connection.py, utils.py
                                                   utils.py  (leaf: stdlib only)
```

- **`config.py` (53 LOC)** — `OdooConfig` reads 8 env vars, `_require()` raises `ConfigError` for the 4 mandatory ones. `setup_logging()` deliberately sends logs to **stderr or a file, never stdout**: `"""Configure logging. Logs go to file or stderr (never stdout, reserved for MCP)."""` (`config.py:39`) — correct stdio-transport hygiene.
- **`connection.py` (200 LOC)** — the sole Odoo choke point. `OdooConnection` owns two `xmlrpc.client.ServerProxy` objects and one `execute_kw` wrapper; everything else is a thin typed helper.
- **`utils.py` (324 LOC)** — pure functions, **zero third-party imports** (`ast`, `json`, `datetime`, `typing` only). Domain validation, domain/list parsing, datetime normalization, smart-field scoring. This is the one module that *is* dependency-free.
- **`tools.py` (968 LOC)** — all 12 tool definitions, all MCP-facing error mapping, all safety gates.
- **`server.py` (76 LOC)** — assembly + a 37-line `SERVER_INSTRUCTIONS` prompt.

### Entry point and lifecycle

`pyproject.toml:17` → `mcp-server-odoo = "mcp_server_odoo.server:main"`. `main()` is two lines:

```python
def main() -> None:
    """Console-script entry point: build the server and run it."""
    create_server().run()          # server.py:74-76
```

`create_server()` (`server.py:52-71`) does, in order: build `OdooConfig` → `setup_logging` → construct `FastMCP("odoo-mcp", instructions=SERVER_INSTRUCTIONS)` → `OdooConnection(config)` → **`conn.connect()` synchronously at startup** → log mode → `register_tools(app, conn, config)`.

Two consequences of eager `connect()`: (a) bad credentials or a down Odoo kill the process **before** the MCP handshake, so the client sees a dead server rather than a tool error — arguably good fail-fast, bad diagnosability; (b) `connect()` is a blocking XML-RPC call executed outside the event loop, acceptable only because it runs pre-`run()`.

`run()` is called with **no transport argument** → FastMCP's default **stdio**. There is no HTTP/SSE option, no bind address, no auth layer. README confirms: `│ MCP (stdio)` (`README.md:10`).

### How tools get registered

Decorator-based, via closures over `conn`/`config` — no registry dict, no plugin discovery, no dynamic generation:

```python
def register_tools(app, conn, config) -> None:
    _register_search_tools(app, conn, config)
    _register_read_group_tools(app, conn)
    _register_model_tools(app, conn, config)
    _register_write_tools(app, conn, config)
    _register_copy_tools(app, conn, config)      # tools.py:147-157
```

Each sub-function defines `async def` tools decorated with `@app.tool(annotations={...}, timeout=...)`. FastMCP derives the JSON Schema from the Python signature (`Annotated[T, Field(description=...)]`) and the tool description from the docstring. The grouping into five `_register_*` functions is cosmetic — the split is arbitrary (`read_group` alone; `copy_record` alone) and does not follow the read/write boundary.

### "Zero external dependencies": what is actually hand-rolled

**Nothing MCP-related.** No JSON-RPC framing, no `initialize`/`tools/list`/`tools/call` handshake, no stdio reader loop appears anywhere in the source — `grep` over all 7 files finds no `jsonrpc`, no protocol constants. Spec compliance is entirely inherited from `fastmcp 3.0.0rc2` → `mcp 1.26.0`. Note `fastmcp>=3.0.0rc1` pins a **release candidate** as a floor, which is itself a supply-chain/stability choice worth flagging.

What *is* hand-rolled and dependency-free is the **Odoo side**: `xmlrpc.client` from the stdlib (`connection.py:5`), no `odoorpc`, no `requests`, and — the README's actual claim — **no Odoo addon to install**.

---

## 3. Odoo connection layer

**Protocol.** XML-RPC over the stdlib, two proxies built in `connect()` (`connection.py:31-36`):

```python
self._common = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/common", allow_none=True)
self._object = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/object", allow_none=True)
```

No `timeout=`, no custom `Transport`, no TLS `context=`, no proxy support, no `User-Agent` — verified by grep; `ServerProxy` appears only at these two lines. **A hung Odoo blocks until the OS TCP timeout**; the per-tool `timeout=` in the `@app.tool` decorator is FastMCP's tool-level timeout, which cancels the awaiting task but cannot interrupt the blocked thread in `asyncio.to_thread`.

**Auth.** Username/password (or API key in the password slot) via `common.authenticate(db, user, password, {"interactive": False})` (`connection.py:39-44`). The `{"interactive": False}` flag was added in `f39229e` specifically so "the RPC auth flow never triggers interactive prompts". Failure handling distinguishes exception from falsy uid:

```python
if not uid:
    raise OdooConnectionError("Authentication failed: invalid credentials")   # :47-48
```

**uid caching.** `self._uid` cached for process lifetime (`connection.py:49`). **But the password is re-sent on every single RPC call** — `_rpc_call` passes `self.config.password` as the third `execute_kw` argument (`connection.py:67-75`). That is how Odoo's XML-RPC API works (it is stateless), so it is correct, not a bug — worth naming because it means no session/cookie reuse and no session expiry to handle.

**Connection reuse.** `ServerProxy` objects live for the process lifetime; the underlying `http.client` connection is re-established per call by `xmlrpc.client`'s default transport (no keep-alive). So "reuse" is of the *proxy object*, not the TCP connection.

**Retry.** Exactly one retry, and only for transport-class errors — the classification is the interesting part (`connection.py:88-109`):

```python
try:
    return self._rpc_call(model, method, args, kw)
except xmlrpc.client.Fault as exc:
    # Application error from Odoo — no point reconnecting
    raise OdooConnectionError(f"RPC fault on {model}.{method}: {exc.faultString}") from exc
except Exception:
    # Transport error — try reconnecting once
    pass
try:
    logger.warning("Connection lost, reconnecting to Odoo...")
    self.connect()
    return self._rpc_call(model, method, args, kw)
```

This is a sound distinction (Odoo `Fault` = business/validation error, never retry; anything else = socket/HTTP, reconnect once). **But it is not write-safe:** a write that reaches Odoo and commits, then fails on the *response* leg (socket reset, read timeout), will be classified as a transport error and **replayed** — duplicate `create`, duplicate `action_confirm`. There is no idempotency key and no distinction between "failed to send" and "failed to receive". This is the same node-replay double-write hazard already hit in Youdoo's `order-confirmation-email` work.

**Async.** Every call funnels through `asyncio.to_thread` (`connection.py:111-121`), added in `ccd0857`:

```python
async def execute_kw(self, model, method, args, kwargs=None) -> Any:
    """Call execute_kw without blocking the event loop."""
    return await asyncio.to_thread(self._execute_kw_sync, model, method, args, kwargs)
```

**Error mapping.** Two layers. `connection.py` wraps everything into `OdooConnectionError` with a `f"RPC fault on {model}.{method}: {exc.faultString}"` message. `tools.py:74-79` re-maps to FastMCP's `ToolError`:

```python
def _handle_odoo_error(exc: OdooConnectionError, context: str) -> ToolError:
    msg = str(exc)
    if "Access" in msg or "security" in msg.lower():
        return ToolError(f"Access denied while {context}: {msg}")
    return ToolError(f"Odoo error while {context}: {msg}")
```

Substring sniffing on an English fault string — brittle (fails under a non-English Odoo locale, and `"Access"` is case-sensitive while `"security"` is not). Note it **passes the raw Odoo `faultString` straight through to the LLM**, which can include SQL fragments, table names, and record values from constraint violations.

---

## 4. Tool design

**12 tools**, all **generic CRUD over arbitrary models** — the polar opposite of the reader's 35 domain-specific tools. `server.py:69` logs `"MCP server ready with 12 tools"` (a hardcoded literal, not a count — it will lie the moment a tool is added).

| # | Tool | Kind | `readOnlyHint` | `timeout` | Source |
|---|---|---|---|---|---|
| 1 | `search_records` | read | `True` | 60s | `tools.py:170-250` |
| 2 | `read_record` | read | `True` | 30s | `tools.py:255-297` |
| 3 | `read_group` | read (aggregation) | `True` | 60s | `tools.py:309-451` |
| 4 | `list_models` | read (discovery) | `True` | 30s | `tools.py:464-532` |
| 5 | `get_record_count` | read | `True` | 30s | `tools.py:537-560` |
| 6 | `get_model_fields` | read (introspection) | `True` | 30s | `tools.py:565-594` |
| 7 | `save_binary_field` | read Odoo → **write local FS** | `False` | 30s | `tools.py:599-688` |
| 8 | `create_record` | write | `False`, `destructiveHint: False` | 30s | `tools.py:701-738` |
| 9 | `update_record` | write | `False`, `idempotentHint: True` | 30s | `tools.py:743-796` |
| 10 | `delete_record` | write | `False`, **`destructiveHint: True`** | 30s | `tools.py:801-832` |
| 11 | `execute_method` | write (arbitrary) | `False`, `destructiveHint: **False**` | 120s | `tools.py:837-913` |
| 12 | `copy_record` | write | `False` | 30s | `tools.py:926-968` |

Good practice worth noting: **every tool carries MCP `annotations`** and an explicit `timeout`. Bad: `execute_method` — the tool that can post invoices and delete records — is annotated `destructiveHint: False`, which is the one annotation a client would use to gate confirmation. That is an actively misleading hint.

**Input schema style.** Pydantic `Annotated[T, Field(description=..., ge=, le=, min_length=)]`. Constraints are real and enforced by FastMCP: `limit` is `ge=1, le=500` (`tools.py:192`), `record_id` is `ge=1`, `record_ids` is `min_length=1`. Descriptions are unusually long and LLM-targeted — the shared `DOMAIN_DESCRIPTION` constant (`tools.py:26-40`) is a 15-line mini-tutorial with worked examples, reused across four tools, and `server.py:13-49` puts a full Odoo-domain grammar (including Polish-notation rules and a common-models list) into `instructions`. This is the strongest part of the design: **the prompt engineering is treated as a first-class artifact.**

**Flexible domain parsing — is it safe?** Yes. `utils.py:161-183`:

```python
def parse_domain(domain: str | list | None) -> list:
    if domain is None: return []
    if isinstance(domain, list): return validate_domain(domain)
    try:
        result = json.loads(domain)
        if isinstance(result, list): return validate_domain(result)
    except (json.JSONDecodeError, TypeError): pass
    try:
        result = ast.literal_eval(domain)          # <-- literal_eval, NOT eval
        if isinstance(result, list): return validate_domain(result)
    except (ValueError, SyntaxError): pass
    raise ValueError(f"Invalid domain: expected JSON or Python list, got: {domain[:120]}")
```

**`ast.literal_eval`, never `eval`/`exec`** — grep confirms `eval(` appears nowhere except inside `literal_eval`. JSON is tried first, Python-repr second. Same pattern in `parse_list_param` (`utils.py:186-204`). Two residual nits, neither a code-execution risk: `ast.literal_eval` on adversarial input can still be a **CPU/memory DoS** (deeply nested literals, `"9"*10**7` style int parsing — mitigated in CPython ≥3.11 by the int-digit limit but not the nesting cost), and it catches only `(ValueError, SyntaxError)` while `literal_eval` can also raise `MemoryError`/`RecursionError`, which would escape as an unhandled exception.

**Domain validation** (`utils.py:43-155`) is genuinely thorough and better than most: leaf arity == 3, operator against a 17-member `VALID_OPERATORS` frozenset, non-empty string field names, `in`/`not in` require list values, and a **Polish-notation operand counter** (`_validate_polish_notation`, `utils.py:123-155`) that rejects `['|', [A]]`. Every error message is written *for the LLM* — the class docstring says so: `"The message is designed to be helpful to an LLM, explaining what went wrong and how to fix it."` (`utils.py:36-40`). Example (`utils.py:62-68`): a bare string element produces *"If you meant this as a condition, wrap it in a leaf: ['name', '=', value]."*

Note the validator is **structural only** — it does not touch field names, so `country_id.code` dot-traversal works, and it deliberately does not validate against `fields_get`. It also permits `=?` in `VALID_OPERATORS` (`utils.py:28`) which the LLM-facing docs never mention.

**ISO-8601 normalization** (`utils.py:210-244`). `format_datetime` matches the exact Odoo shape (`len == 19` and contains a space), parses with `strptime`, re-emits with a **hardcoded `+00:00` suffix**:

```python
return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")     # utils.py:218
```

That is factually correct for Odoo (`datetime` columns are stored UTC-naive) but it is an *assertion*, not a conversion. `process_record_dates` decides which keys to touch by a hint set of 11 names plus the suffix heuristic `key.endswith("_date") or key.endswith("_datetime")` (`utils.py:239-243`) — so `date_deadline`, `invoice_date_due`, `effective_date` are covered by neither list-membership nor suffix in some Odoo models, and Odoo `date` (not datetime) fields are left alone correctly since they are length 10.

**Smart field selection** (`utils.py:250-324`). When `fields is None`, the server calls `fields_get` and scores:
- Always included, score 1000: `{"id", "name", "display_name", "active"}` (`ESSENTIAL_FIELDS`).
- **Excluded by prefix**: `("_", "message_", "activity_", "website_message_")` — kills mail-thread noise.
- **Excluded by name**: `write_date, create_date, write_uid, create_uid, __last_update, access_token, access_warning, access_url`. The `access_*` three are a small **credential-ish filter** — the only one in the codebase.
- **Excluded by type** (`HEAVY_TYPES`): `binary, image, html, one2many, many2many` — so smart mode never returns order lines or base64 blobs.
- **Excluded**: non-stored computed fields (`info.get("compute") and not info.get("store", True)`) — avoids expensive per-record computation.
- Scoring: `+500` required, type table (`char` 200 → `text` 80), `+80` stored, `+60` if the name contains any of 13 business patterns (`state, status, stage, priority, amount, total, date, user, partner, email, phone, code, ref`). Capped at **`MAX_SMART_FIELDS = 40`**.
- Escape hatch: `fields=["__all__"]` → passes `None` to Odoo = every field (`tools.py:229-230`, `287-288`).

**Output formatting.** Plain dicts returned from the tool function; FastMCP serializes. Deliberate envelope design: reads return `{"records": [...], "total": N, "limit", "offset", "model"}` — **`total` is a separate `search_count` call** so the LLM knows it is paginating (`tools.py:220`, `244-250`). Writes return `{"success": True, "id": N, "record": {...}, "url": ...}` where `url` is a deep link into the Odoo web UI:

```python
url = f"{config.url}/web#id={record_id}&model={model}&view_type=form"     # tools.py:737
```

(Odoo 17+/19 uses `/odoo/<model>/<id>`; this `/web#...` form is the Odoo ≤16 style — consistent with the `16.0` branch name, and it will produce stale-looking but still-redirecting links on newer Odoo.)

Every write reads the record back through `_read_back_record` (`tools.py:131-141`) with smart fields, so the LLM immediately sees the post-write state — including server-computed fields. Nice touch, and its `try/except` around `fields_get` (falling back to `read_fields = None`) was an explicit bug fix: commit `48f8d29` "*prevent read-back crash on models without name field*".

`_safe_serialize` (`tools.py:82-90`) recursively coerces anything non-JSON to `str()` — used on `read_group` output and on `execute_method`'s return, where Odoo commonly returns action dicts containing non-serializable values.

---

## 5. Write-path flow, step by step

### The gate

One helper, **five call sites** — not a single choke point (`tools.py:51-57`):

```python
def _check_write(config: OdooConfig) -> None:
    """Raise ToolError if readonly mode is on."""
    if config.readonly:
        raise ToolError("Write operations are disabled (READONLY_MODE is enabled). "
                        "This server is configured for read-only access.")
```

Called at `tools.py:724` (`create_record`), `774` (`update_record`), `817` (`delete_record`), `894` (`execute_method`), `959` (`copy_record`). **It is a per-tool gate, enforced in the tool layer, not in `connection.py`.** `OdooConnection.create/write/unlink/copy` are entirely ungated — any future tool that forgets `_check_write` writes freely. `config.readonly` itself is read **once at startup** from the process env (`config.py:25`) and never re-read.

**Gap:** `save_binary_field` (tool 7) has **no `_check_write`** — verified by grep over `tools.py:599-688`. It is annotated `readOnlyHint: False` because it writes to the local filesystem, and `READONLY_MODE=true` does **not** stop it. The README's blanket claim *"🚫 Write tools are disabled when `READONLY_MODE=true`"* (`README.md:96`) is therefore **contradicted by the code** for the one tool that writes outside Odoo.

### `create_record` (`tools.py:705-738`)
1. `_check_write(config)`.
2. `if not values: raise ToolError(...)` — empty-dict guard only. **No `fields_get` validation of the payload**, no required-field check, no type check, no unknown-field check. The docstring pushes that onto the model: *"Use get_model_fields first to discover required fields."* (`tools.py:714`).
3. `await conn.create(model, values)` → `execute_kw(model, "create", [values])`.
4. `await _read_back_record(...)` → `fields_get` + smart fields + `read`.
5. Return `{"success", "id", "record", "url"}`.
Cost: **3 round trips** per create (create + fields_get + read).

### `update_record` (`tools.py:751-796`)
1. `_check_write`. 2. empty-`values` guard. 3. **existence pre-check**: `await conn.read(model, [record_id], ["id"])`, raise `ToolError(f"Record not found: ...")` if empty (`tools.py:782-787`). 4. `await conn.write(model, [record_id], values)`. 5. read-back. 6. return with `url`.
Cost: **4 round trips**. The pre-check is a courtesy for a better LLM-facing error (Odoo's own `write` on a missing id raises a `MissingError` fault anyway) and is a TOCTOU window, though a harmless one.

### `delete_record` (`tools.py:805-832`)
`_check_write` → existence pre-check → `unlink` → `{"success": True, "deleted_id": id}`. **One record at a time** (`record_id: int`, not a list) — a deliberate blast-radius limit. No archive-instead-of-delete, no confirmation, no soft-delete; docstring says *"This action cannot be undone."*

### `copy_record` (`tools.py:930-968`)
`_check_write` → `conn.copy(model, id, default)` → read-back → return. `default` is passed straight through to Odoo's ORM `copy` with **no validation at all** — it is an unvalidated write payload by another name.

### `execute_method` (`tools.py:841-913`) — the important one
```python
_check_write(config)
if config.readonly and method in BLOCKED_METHODS_READONLY:      # tools.py:895
    raise ToolError(f"Method '{method}' is blocked in readonly mode ...")

call_args = [record_ids] + (args or [])
result = await conn.execute_kw(model, method, call_args, kwargs)   # tools.py:902-903
```

**Can it call arbitrary methods? Yes — completely.** `method` is a free-form string with no allowlist, no denylist, no regex, no prefix rule. `execute_method("res.users", "unlink", [2])`, `execute_method("ir.config_parameter", "set_param", [], args=[...])`, `execute_method("res.partner", "write", [1], args=[{...}])` all reach Odoo. The tool's `timeout=120.0` is the only thing distinguishing it.

**And the one denylist in the repo is dead code.** `BLOCKED_METHODS_READONLY = frozenset({"create","write","unlink","copy","action_archive","action_unarchive","toggle_active"})` (`tools.py:61-71`). Line 894 calls `_check_write(config)`, which **already raises whenever `config.readonly` is true**. Therefore line 895's `if config.readonly and ...` is **unreachable on every path** — if readonly, we never get there; if not readonly, the condition is false. The frozenset is never consulted in production. Commit `ccd0857`'s message advertises this as a feature: *"Block ORM write methods (create/write/unlink/copy) in execute_method when READONLY_MODE is enabled."* The intent was almost certainly the inverse — a denylist that applies **in full-access mode** — and the two checks were stacked in the wrong order. Net effect of the bug is *fail-safe* (readonly blocks everything, including read-only methods like `name_get`/`fields_get` via `execute_method`) but the advertised safety mechanism does not exist.

**Residual protection is Odoo-side only:** Odoo's `execute_kw` dispatcher refuses method names starting with `_`, and enforces `ir.model.access` + `ir.rule` for the authenticated uid. This server adds nothing on top.

---

## 6. Permission / security model

- **One account, from env.** `ODOO_URL/ODOO_DB/ODOO_USER/ODOO_PASSWORD`, all four mandatory (`config.py:20-23`). No API-key-specific variable (unlike ivnvxd's `ODOO_API_KEY`); an Odoo API key simply goes in the password slot. **No per-role isolation, no multi-account support, no uid switching.** Whatever that account can do, the LLM can do.
- **Allow/deny lists: essentially none.** No model allowlist (any model, including `res.users`, `ir.model.data`, `ir.config_parameter`, `ir.cron`). No field allowlist. No method list (§5). The only lists in the whole codebase are `VALID_OPERATORS` (a *syntax* check, not a security control), `EXCLUDE_FIELDS`/`EXCLUDE_PREFIXES` (a *noise* filter, trivially bypassed by `fields=["__all__"]` or by naming the field explicitly), and the dead `BLOCKED_METHODS_READONLY`.
- **The entire authorization model is delegated to Odoo's own ACLs** for the configured user. With `ODOO_USER=admin` — which is what the README, the quick-start command and `.env.example` all show (`README.md:28`, `.env.example:4-5`) — there is effectively no authorization at all.
- **Input sanitization.** Domain structure validated (§4); numeric bounds enforced by pydantic; `values`/`default`/`kwargs`/`args` **not validated at all**. No injection surface in the SQL sense (XML-RPC + ORM domains, not string SQL), and no code-execution surface (`literal_eval`).
- **Filesystem.** `_validate_output_path` (`tools.py:107-120`) resolves `realpath(expanduser(path))` then rejects a **POSIX-only prefix list**: `/etc /bin /sbin /usr/bin /usr/sbin /boot /proc /sys /dev /var/run`. On **Windows this list matches nothing** — `C:\Windows\System32\...` passes. Even on Linux it misses `~/.ssh/authorized_keys`, `~/.bashrc`, `~/.config`, `/usr/lib`, `/var/spool/cron`, and any relative path resolving into a project's source tree. Combined with the missing `_check_write`, `save_binary_field` is an **arbitrary-file-write primitive** whose content is attacker-influenceable (anyone who can store a binary field in Odoo) and whose path is LLM-chosen. It also `os.makedirs(parent_dir, exist_ok=True)` (`tools.py:665-667`), creating directories as a side effect.
- **Transport security.** stdio only — the process is a child of the MCP client on the same machine, so there is no network listener and no auth needed; that is the right choice for this threat model. But the **Odoo leg** has no TLS enforcement: `ODOO_URL=http://...` is the documented default everywhere, `ServerProxy` gets no SSL context, and there is no certificate verification setting. Credentials transit in cleartext on every RPC if the URL is `http://`.
- **Secrets handling.** Password lives in `OdooConfig.password` in plaintext, re-sent per call, and is never redacted from logs — though in practice nothing logs it. `.env` is gitignored.

---

## 7. Audit / logging / observability

Effectively **absent**. The entire codebase contains **5 logger calls**:

| Line | Level | Message |
|---|---|---|
| `connection.py:50` | INFO | `"Connected to Odoo as uid=%d on %s"` |
| `connection.py:99` | WARNING | `"Connection lost, reconnecting to Odoo..."` |
| `server.py:66` | INFO | `"MCP server mode: %s"` (READONLY / FULL ACCESS) |
| `server.py:69` | INFO | `"MCP server ready with 12 tools"` |
| `tools.py:672` | INFO | `"Saved %s.%s (ID %d) to %s (%d bytes)"` |

So: **no tool-invocation log, no write log, no argument capture, no result log, no timing, no error log** (errors are raised as `ToolError` and never logged), no request/correlation id, no metrics, no tracing, no hash chain, no tamper-evidence. A `create_record` that deletes nothing and a `execute_method("account.move","button_draft",[...])` that un-posts an invoice leave **zero trace** in the server. The only forensic record is Odoo's own `write_uid`/`write_date` and `mail.tracking.value` — and since all traffic uses one shared account, every action attributes to that one user with no way to distinguish agent from human or one session from another.

Ironically, the one tool that does log is the local-filesystem one. Configurability exists (`ODOO_MCP_LOG_LEVEL`, `ODOO_MCP_LOG_FILE`) but there is nothing to configure.

---

## 8. Testing strategy

**There is none.** No test files, no `conftest.py`, no `pytest`/`hypothesis`/`respx` dependency, no `[tool.pytest.ini_options]`, no coverage config, no CI test job, no mock Odoo, no fixtures. Verified by `find` across the tree and `grep pyproject.toml`.

Quality control is (a) `pre-commit` with ruff — **local only, not enforced in CI**; (b) `.github/workflows/pr-agent.yml`, an LLM reviewer on a self-hosted runner that posts review comments. That is the *entire* verification apparatus.

The consequences are visible in the code. Commit `f39229e` (2026-04-16) exists precisely because five write tools shipped for two months calling `conn.create/read/write/unlink/copy` **without `await`**, silently producing un-awaited coroutines — its message: *"The write tools ... were calling conn methods without `await`, leaving them as unresolved coroutines. Adds `await` to all five call sites."* That fix enumerated the *write* tools and **missed a sixth site** — see §11, finding A. A single smoke test per tool would have caught all six.

---

## 9. Extensibility — adding a new tool

Concretely, 4 steps, ~30 lines, no registry to touch:

1. *(optional)* Add a helper to `OdooConnection` if `execute_kw` needs a typed wrapper (`connection.py:125-200` pattern) — but you can also call `conn.execute_kw(model, method, args, kwargs)` directly from the tool.
2. In `tools.py`, add an `async def` inside one of the five `_register_*` closures (or write a sixth `_register_*` and call it from `register_tools`, `tools.py:147-157`).
3. Decorate with `@app.tool(annotations={"readOnlyHint": ..., "destructiveHint": ...}, timeout=...)`, type the params as `Annotated[T, Field(description="...")]`, and write a docstring containing a `Returns:` shape — FastMCP turns all of this into the schema and tool description automatically.
4. If it mutates anything, **remember `_check_write(config)` as the first statement**, and wrap Odoo calls in `try/except OdooConnectionError` → `raise _handle_odoo_error(exc, "context") from exc`.
5. Update the hardcoded `"MCP server ready with 12 tools"` string in `server.py:69` and the README table.

Friction is genuinely low — this is the main upside of the design. The hazards are that steps 4 and 5 are convention, not enforcement: nothing in the framework stops a new write tool from omitting the gate (as `save_binary_field` already does), and the tool count is a literal.

---

## 10. Notable design decisions and stated rationale

1. **"No Odoo module installation required"** (`README.md:6`) — the differentiator vs ivnvxd/mcp-server-odoo (which ships an Odoo addon). Implemented by using only stock `/xmlrpc/2/*` endpoints. This is what the "no external dependencies" tagline actually means.
2. **Zero-clone install** — `uvx --from git+https://github.com/... mcp-server-odoo` is the only documented install path (`README.md:20-31`), and commit `[FIX] server: run server in script entry point so uvx works` exists to support it. Deliberate: nothing to publish, nothing to package, always HEAD. Also means **no version pinning for users** and no release integrity.
3. **Generic CRUD over domain tools**, explicitly bet on the LLM knowing Odoo. Backed by investment in prompt surface: the 37-line `SERVER_INSTRUCTIONS` domain grammar (`server.py:13-49`), the reusable 15-line `DOMAIN_DESCRIPTION`, and validator errors written as LLM instructions (`utils.py:36-40`).
4. **Smart field selection** exists because generic tools would otherwise dump entire records. Rationale in `README.md:100-107`: *"It scores fields based on type, importance patterns ... and excludes noisy fields like `message_ids`, binary blobs, and computed non-stored fields."*
5. **Fault vs transport error split** for retry (`connection.py:90-97`), with the reasoning inline: *"Application error from Odoo — no point reconnecting"*.
6. **Logs never to stdout** (`config.py:39`) — correct stdio-MCP discipline, stated in the docstring.
7. **Read-back after every write** — chosen over returning bare ids, so the LLM sees computed/defaulted values. Hardened by `48f8d29` (models without a `name` field).
8. **`save_binary_field` instead of returning base64** — docstring rationale (`tools.py:629-633`): *"This avoids returning the large base64 data in the response - it writes the file to disk and returns only the file path and metadata."* A genuinely good context-window decision, badly executed on the security side.
9. **MCP annotations on every tool** — a spec feature most servers skip.
10. **AI-assisted development is the stated workflow** (Claude co-author trailers on the substantive commits; the only CI job is an LLM PR reviewer). Explains both the polished docstrings and the class of bugs in §11.

No GitHub issues (0 open, 0 closed visible) and one merged PR, so commit messages are the only rationale record.

---

## 11. Weaknesses / risks found in the code

**A. `get_model_fields` is broken on HEAD — missing `await` (`tools.py:590`).**
```python
fields_info = conn.fields_get(model, attributes)      # no await
...
return {"model": model, "fields": fields_info, "count": len(fields_info)}   # :594
```
`conn.fields_get` is `async` (`connection.py:192`). This is the **only one of 20 `conn.*` call sites in `tools.py` lacking `await`** (verified by grep). It returns a coroutine, `len(coroutine)` raises `TypeError: object of type 'coroutine' has no len()`, plus a "coroutine was never awaited" warning. So the tool the README recommends using before every create/update (*"Use get_model_fields first to discover required fields"*, `tools.py:714`) **fails 100% of the time**. It survived the dedicated await-fix commit `f39229e` because that commit only swept the *write* tools. Direct consequence of §8.

**B. The only denylist is unreachable dead code** (`tools.py:894-899`) — see §5. `_check_write` fires first, so `BLOCKED_METHODS_READONLY` is never consulted. Advertised in `ccd0857`'s commit message as a shipped security control.

**C. `save_binary_field` = ungated arbitrary local file write.** No `_check_write` (so `READONLY_MODE=true` does not stop it, contradicting `README.md:96`); `BLOCKED_PATH_PREFIXES` is POSIX-only and **inert on Windows**; misses `~/.ssh`, `~/.bashrc`, `/usr/lib`, cron dirs; `os.makedirs` creates directories; content comes from an Odoo binary field that any Odoo user could have planted. Also `startswith` prefix matching gives false positives (`/etcetera` blocked) and false negatives (`/var/run` blocked but `/var/tmp/../run` is caught by realpath, fine — while `/home/u/.ssh` is not blocked at all).

**D. Retry can duplicate writes** (`connection.py:95-101`) — any non-`Fault` exception after the request was sent triggers a full re-execution, including `create` and `action_confirm`. No idempotency guard.

**E. No timeout on `ServerProxy`** — a hung Odoo pins a thread pool worker indefinitely; the FastMCP tool `timeout` cannot reclaim it. Repeated occurrences exhaust the default `asyncio.to_thread` executor (32 threads) and wedge the server.

**F. `destructiveHint: False` on `execute_method`** (`tools.py:838`) while `delete_record` correctly gets `True` — the one tool that can `unlink`, `action_post` and `button_validate` tells the client it is non-destructive.

**G. No credential/PII filtering on reads.** `EXCLUDE_FIELDS` drops only `access_token/access_warning/access_url`, and only in smart mode. `read_record("ir.mail_server", 1, fields=["smtp_pass"])` or `search_records("ir.config_parameter", [], fields=["__all__"])` is fully reachable — gated solely by Odoo ACLs, which for the documented `admin` account are wide open.

**H. Raw `faultString` forwarded to the LLM** (`connection.py:93`, `tools.py:79`) — leaks constraint names, table/column names and record values into the model's context.

**I. `config.readonly` read once at import-time env** (`config.py:25`); no runtime toggle, no re-read, no remote kill switch. Changing mode requires restarting the MCP client.

**J. `"MCP server ready with 12 tools"` is a hardcoded literal** (`server.py:69`) — will silently lie after the next tool is added.

**K. Odoo-version drift.** Branch `16.0`, `/web#id=...` URL format (`tools.py:737`), and `read_group` with `lazy=` — all Odoo ≤16 shapes. `read_group` is deprecated in Odoo 17+ in favour of `formatted_read_group`/`_read_group`; it still works in 19.0 but is on the way out. README claims "Odoo 12+" with no upper bound and no version detection anywhere in the code.

**L. Floor-pinned on a release candidate** (`fastmcp>=3.0.0rc1`) combined with git-URL installation = every user resolves a different dependency tree at install time, with no lockfile applied (`uv.lock` is not used by `uvx --from git+...`).

**M. No pagination ceiling on `read_group`** (`limit: int | None = None`, `tools.py:345-354`) — a group-by on a high-cardinality field returns everything into the LLM context, unlike `search_records` which is capped at `le=500`.

---

## 12. Transferable to the reader's server

### Worth taking (bounded, mapped to your stated gaps)

1. **Fix your "no runtime `fields_get` validation of write payloads" gap by copying the *idea* they document but never implement.** They punt entirely (docstring: *"Use get_model_fields first"*) and their `get_model_fields` is broken (§11-A). The transferable insight is negative-evidence: a generic server **cannot** validate payloads cheaply, but your 35 domain-specific tools can — you already know the model per tool, so a per-tool cached `fields_get` at first use, validating `values.keys()` ⊆ known fields and required-fields-present, costs one RPC per model per process and closes the gap with far less machinery than a generic server would need. Their `_read_back_record` caching pattern (`tools.py:131-141`) is the shape to copy; their lack of caching (a `fields_get` on *every* create/update/copy — 3-4 round trips per write) is what to avoid.

2. **Read-back-after-write with smart field selection** (`tools.py:131-141`, `_read_back_record`). Directly useful for your `invoice-confirm-summary` / `order-confirmation-email` family: returning the post-write record (not just the id) lets the agent verify server-computed state without a second tool call, and the `try/except` around `fields_get` falling back to `None` (from commit `48f8d29`) is the exact robustness detail you'd otherwise discover in live-verify.

3. **MCP `annotations` on every tool** (`readOnlyHint`, `destructiveHint`, `idempotentHint`) plus per-tool `timeout=`. Cheap, spec-correct, and your LangGraph interrupt layer could *read* `destructiveHint` to decide whether a write needs human confirmation instead of hardcoding the tool list — turning your per-write approval from a maintained list into a property of the tool. **Learn from their mistake:** they set `destructiveHint: False` on `execute_method` (§11-F), which would silently disable confirmation for the most dangerous tool. If you do this, make the annotation the *source* your confirmation layer reads and assert in a test that every write tool declares one.

4. **The LLM-targeted error message discipline** (`utils.py:36-40`, `62-68`). Every validation failure states what was wrong *and* shows a corrected example. This is prompt engineering living in the exception layer, and it is the single cleanest idea in the repo. Your `router-empty-response` and `gather_erp` history suggests the same payoff: errors that teach the model to self-correct on retry beat errors that just say "invalid".

5. **`save_binary_field`'s core decision — return a path, not base64** (`tools.py:629-633`). Your attachment/OCR work already moves binary out of band; if any of your 35 tools can return an Odoo binary field, this is the pattern. **Do not copy their implementation** — copy the decision and implement the path check properly (allowlist a single output directory, reject anything not under it after `realpath`, and put it behind your write gate).

6. **Fault-vs-transport retry classification** (`connection.py:90-97`) as a named concept for your `odoo()` choke point — Odoo `Fault` means "business rejected it, never retry"; anything else is a socket problem. **But invert their conclusion for writes:** their retry replays writes (§11-D). At your choke point you already know whether a method is a write (you have a method whitelist); gate the reconnect-and-retry on *read* methods only, and surface transport failures on writes as "unknown outcome" for the agent to reconcile. This is the same node-replay double-write class you already paid for once in `order-confirmation-email`.

7. **The 40-field smart selection cap + heavy-type exclusion** (`utils.py:250-324`). Even with domain-specific tools, `one2many`/`html`/`binary` fields are the main accidental context burner. The concrete list `HEAVY_TYPES = {"binary","image","html","one2many","many2many"}` and the non-stored-computed exclusion (`info.get("compute") and not info.get("store", True)`) are directly liftable as a default field filter — and the computed-field exclusion also avoids triggering expensive Odoo recomputation on read.

8. **`EXCLUDE_FIELDS` as the *seed* of your missing credential filter** — but only as a seed. Theirs is 3 `access_*` entries and is bypassed by `fields=["__all__"]`. For your gap, the right shape is the opposite: a **deny-by-default check applied at the `odoo()` choke point on the result**, keyed on field name patterns (`*password*`, `*_pass`, `*token*`, `*secret*`, `*api_key*`) plus a model denylist (`ir.config_parameter`, `ir.mail_server`, `fetchmail.server`, `res.users.password`), enforced where it cannot be bypassed by a tool argument. Their design demonstrates precisely why a filter in the *field-selection helper* rather than the *result path* is worthless.

### Explicitly NOT worth copying

- **The whole permission model.** One admin account, no allowlists, `execute_method` with an unbounded method string. Your 3-4 isolated MCP processes with dedicated per-role Odoo accounts + method whitelist is strictly stronger; this repo is the "what if we didn't" control group. Note the direct comparison: their `execute_method` alone re-introduces everything your whitelist excludes.
- **`READONLY_MODE` as a per-tool env-read flag.** Five call sites, one missing (§5), read once at startup, no remote control. Your `ir.config_parameter` fail-closed global toggle at a single choke point is better on all three axes (central, runtime-changeable, fail-closed). Their bug (`save_binary_field` ungated) is the direct empirical cost of per-tool gating — cite it if anyone proposes moving your gate into the tools.
- **Their `BLOCKED_METHODS_READONLY` denylist.** Not because denylists are wrong, but because **it is dead code that a commit message advertises as a shipped control** (§5, §11-B). The lesson is yours already ("test không đo gì"): a safety mechanism with no test is a comment. If you add any new gate to your server, add the test that proves the *blocked* path actually blocks.
- **Generic CRUD tool surface.** Contradicts your 35-domain-tool architecture deliberately. Their bet (LLM knows Odoo + a good domain-syntax prompt) trades auditability and least-privilege for coverage. Your `gather_erp`/`GATHER_CASES` history shows the domain-specific bet paying off in measurability — a generic `search_records` cannot be contract-tested against real tool fields the way your fixtures are.
- **Zero-dependency / zero-clone install via `uvx --from git+...`.** No pinning, no lockfile, RC-floor dependency. You need reproducible deploys.
- **Their observability level.** Five log lines, no tool-call log. Your event log with argument fingerprint + hash-chained audit log with verifier is several orders more mature; there is nothing here to import.
- **Their testing strategy** (none). Note for the cross-repo comparison: this repo is the clearest available evidence for your own durable preference — the `f39229e` missing-`await` incident shipped a *completely non-functional* write path for two months, and its fix still left `get_model_fields` broken today, in a 1,627-line codebase with an LLM PR reviewer and zero tests.

---

## Key Questions

### Q1: Is the hand-rolled MCP transport a liability (spec drift) or a strength (simplicity)?

#### Takeaway
The premise does not hold: **there is no hand-rolled MCP transport.** The server is a thin FastMCP 3.0.0rc2 application; protocol compliance is entirely inherited from `fastmcp` → `mcp` 1.26.0. The "without any external dependencies" tagline refers to needing no Odoo-side addon, not to Python dependencies.

#### Cited Findings
- `pyproject.toml:11-14` declares `dependencies = ["fastmcp>=3.0.0rc1", "python-dotenv>=1.0"]` — [repo](https://github.com/altinkaya-opensource/odoo-mcp/blob/16.0/pyproject.toml)
- `uv.lock` resolves **76 packages**, including `fastmcp 3.0.0rc2`, `mcp 1.26.0`, `pydantic 2.12.5`, `httpx`, `authlib`, `cryptography`.
- `server.py:5` `from fastmcp import FastMCP`; `tools.py:8-9` `from fastmcp import FastMCP` / `from fastmcp.exceptions import ToolError`; `tools.py:10` `from pydantic import Field`.
- No JSON-RPC framing, no `initialize`/`tools/list`/`tools/call` handler, no stdio loop exists in any of the 7 source files (grep).
- GitHub About text, verbatim: *"Model Context Protocol (MCP) for Odoo without any external dependencies"* — [repo page](https://github.com/altinkaya-opensource/odoo-mcp)
- `README.md:6`: *"No Odoo module installation required. Just point it at any Odoo 12+ instance."*

#### Inferences
- The only genuinely dependency-free part is the **Odoo leg**: stdlib `xmlrpc.client` (`connection.py:5`), no `odoorpc`/`requests`, and no Odoo addon — which is the real differentiator against ivnvxd/mcp-server-odoo (whose companion `mcp_server` module is on the Odoo Apps Store).
- Using FastMCP is the right call and removes spec-drift risk from the protocol layer; the actual liability sits one level up, in the **`>=3.0.0rc1` release-candidate floor combined with git-URL installation**, which means every user resolves an unpinned, pre-release dependency tree with `uv.lock` unused.
- `utils.py` (324 LOC) is the one module with zero third-party imports — it is plausible the tagline was written about the intent of that module's design ethos and never revisited.

#### Gaps
- No issue, PR or commit message explains the About tagline; there are 0 open and 0 visible closed issues, so authorial intent is inferred from the README, not confirmed.

---

### Q2: How does `execute_method` decide what is allowed — is there any denylist at all?

#### Takeaway
**No effective denylist exists.** `method` is an unconstrained string passed straight to `execute_kw`. The one denylist in the codebase, `BLOCKED_METHODS_READONLY`, is **unreachable dead code** because the `_check_write` call immediately above it already raises whenever readonly is on.

#### Cited Findings
- `tools.py:894-903`:
  ```python
  _check_write(config)
  if config.readonly and method in BLOCKED_METHODS_READONLY:
      raise ToolError(f"Method '{method}' is blocked in readonly mode ...")
  call_args = [record_ids] + (args or [])
  result = await conn.execute_kw(model, method, call_args, kwargs)
  ```
- `tools.py:51-57`: `_check_write` raises `ToolError` iff `config.readonly` — so line 895's condition is false on every path that reaches it.
- `tools.py:61-71`: `BLOCKED_METHODS_READONLY = frozenset({"create","write","unlink","copy","action_archive","action_unarchive","toggle_active"})`; grep shows exactly one reference, at line 895.
- Commit `ccd0857` message claims the control ships: *"Block ORM write methods (create/write/unlink/copy) in execute_method when READONLY_MODE is enabled."*
- No allowlist, prefix rule or regex on `method` anywhere; `model` is likewise unconstrained (`MODEL_DESCRIPTION` is documentation only, `tools.py:42-48`).
- `execute_method` is annotated `destructiveHint: False` (`tools.py:838`) while `delete_record` is annotated `True` (`tools.py:802`).

#### Inferences
- The intended design was almost certainly a denylist active in **full-access** mode; the two checks were composed in the wrong order, making the feature a no-op. The failure mode is fail-safe (readonly blocks *everything* through `execute_method`, including harmless reads like `name_get`) but the advertised protection does not exist.
- In full-access mode, `execute_method` is a **general-purpose ORM remote shell** bounded only by Odoo's own dispatcher rules (private `_`-prefixed methods refused) and the configured account's `ir.model.access`/`ir.rule` — which is nothing when the documented account is `admin`.
- Because `execute_method` can reach `create`/`write`/`unlink`, all the narrower tools' guards (empty-values checks, existence pre-checks, single-record delete) are bypassable through it. The blast-radius limits in `delete_record` are decorative while `execute_method` exists unrestricted.

#### Gaps
- Whether the author is aware of the ordering bug: no issue, no TODO comment, no follow-up commit. The LLM PR-reviewer workflow did not catch it (it was introduced in the same commit series it reviews).

---

### Q3: Is the Python-repr domain parsing an injection risk?

#### Takeaway
**No code-execution risk.** Parsing uses `ast.literal_eval`, never `eval`/`exec`, after a JSON attempt, and the result is then structurally validated. The residual exposure is resource-exhaustion and unhandled-exception classes, not injection.

#### Cited Findings
- `utils.py:161-183` (`parse_domain`): tries `json.loads` first, then `ast.literal_eval`, each guarded by `isinstance(result, list)`, then `validate_domain(result)`; otherwise raises `ValueError`.
- `utils.py:186-204` (`parse_list_param`): identical two-stage pattern for `fields`/`groupby`.
- `utils.py:3` imports `ast`; grep over all source finds no bare `eval(`, no `exec(`, no `compile(`.
- `utils.py:43-155` (`validate_domain` + `_validate_polish_notation`): leaf arity 3, operator ∈ 17-member `VALID_OPERATORS`, non-empty string field names, list values for `in`/`not in`, Polish-notation operand counter.
- Odoo domains are consumed by the ORM, not string-concatenated into SQL, so there is no second-order SQL-injection path through a well-formed domain.
- The except clauses catch only `(ValueError, SyntaxError)` (`utils.py:179`, `:202`).

#### Inferences
- `ast.literal_eval` still *parses* attacker-supplied text: deeply nested literals can blow the recursion limit (`RecursionError`) and huge literals can consume memory — neither is caught by the `(ValueError, SyntaxError)` handlers, so they escape as unhandled exceptions rather than `ToolError`. In stdio/single-tenant deployment the practical impact is a noisy crash, not a breach.
- The real risk in the domain path is not injection but **authorization**: `validate_domain` checks *structure only* and deliberately allows unlimited dot-traversal (`partner_id.country_id.code`), so a domain can filter and therefore infer data across relations the tool author never anticipated. With one shared admin account and no model allowlist, the domain language is an information-disclosure surface even though it is not an execution surface.
- Conversely, the unvalidated surfaces are `values` (`create_record`), `default` (`copy_record`), and `args`/`kwargs` (`execute_method`) — all passed verbatim to the ORM with no checks at all. The careful domain validator sits next to four completely open payload channels, which is the more consequential asymmetry.

#### Gaps
- No stated rationale for choosing `literal_eval` (no comment beyond `# Try Python literal (handles single quotes, True/False)`, `utils.py:174`), so it is unclear whether it was a security decision or an ergonomics one.

---

### Additional gaps across the whole investigation
- **No runtime verification was performed** — per the read-only constraint, nothing was installed or executed. The `get_model_fields` missing-`await` defect (§11-A) is established by static reading plus the async signature at `connection.py:192`, not by running the tool.
- **No issue tracker signal at all** (0 open, 0 closed visible; 1 merged PR), so all "rationale" is reconstructed from commit messages, docstrings and the README.
- **No user-facing adoption data** (4 stars, no PyPI release, no download stats), so nothing can be said about whether these design choices survive real workloads.
- **FastMCP 3.x's exact default transport for `run()`** was not independently verified against FastMCP docs; the stdio conclusion rests on `README.md:10` (`│ MCP (stdio)`) and the absence of any transport argument at `server.py:76`.
