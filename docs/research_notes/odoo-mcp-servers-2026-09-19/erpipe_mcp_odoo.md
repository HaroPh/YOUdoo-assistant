# erpipe-org/mcp-odoo

Source: full read-only clone of https://github.com/erpipe-org/mcp-odoo at commit
`76ec136e0c89c414811a12629eb2903d2dc27357` (2026-08-25, "docs(readme): state ERPipe identity
and hosted tool count"). All paths below are repo-relative to that clone. Evidence is the
actual code unless a `docs/` or `README.md` file is named.

---

## 1. Repo facts

| Fact | Value | Evidence |
| --- | --- | --- |
| Language | Python, `requires-python = ">=3.10"` | `pyproject.toml` |
| MCP framework | **Official MCP Python SDK v2** (`mcp>=2,<3`), class `MCPServer` from `mcp.server.mcpserver` — *not* the older `mcp.server.fastmcp` | `pyproject.toml` deps; `src/odoo_mcp/server_core.py:20` `from mcp.server.mcpserver import Context, MCPServer` |
| Runtime deps | only `mcp>=2,<3` and `requests>=2.31.0` (HTTP for OAuth uses `httpx2`, transitively from the SDK) | `pyproject.toml`; `src/odoo_mcp/auth.py:36` |
| LOC | **11,900** lines across 33 modules in `src/odoo_mcp/`; **13,812** lines of tests in `tests/` (more test code than source) | `wc -l src/odoo_mcp/*.py`, `wc -l tests/*.py` |
| Largest modules | `diagnostics.py` 1185, `agent_tools.py` 1099, `odoo_client.py` 1010, `tools_read.py` 845, `tools_write.py` 806, `server_core.py` 759, `tools_diagnostics.py` 727 | same |
| License | MIT, "Copyright (c) 2025 Lê Anh Tuấn" | `LICENSE` |
| Version / last release | `1.3.2`, tag `v1.3.2` dated 2026-08-19 | `pyproject.toml`, `git for-each-ref` |
| Release cadence | 20 tags from `0.0.4` through `v1.3.2`; v1.1.0 (2026-07-02) → v1.3.2 (2026-08-19) is 8 releases in 7 weeks | `git tag`, tag dates |
| Last commit | 2026-08-25 (docs only); last code fix 2026-08-14 ("reject invalid search domains instead of matching every record", #66) | `git log` |
| GitHub signals | **414 stars, 187 forks, 7 open issues**, not archived, last push 2026-08-25 | `gh api repos/erpipe-org/mcp-odoo` |
| Tests | 891 test functions across 39 test files; CHANGELOG 1.2.1 claims "909 tests" | `grep -c "^def test_"`, `CHANGELOG.md` |
| CI | GitHub Actions `.github/workflows/publish.yml` runs `python -m pytest` on py3.10/3.11/3.12 on every PR and push to main, plus version-consistency, docker, pages, MCP-registry workflows | `.github/workflows/` |
| Extra quality gates | `ruff`, `mypy` (`disallow_untyped_defs = true`), **`lint-imports` (import-linter) with two enforced layering contracts** | `pyproject.toml`, `.importlinter`, `docs/testing.md` |
| Distribution | PyPI `odoo-mcp` (`uvx odoo-mcp`), GHCR Docker image, MCP Registry (`io.github.erpipe-org/mcp-odoo`), Smithery, MCPB desktop extension (`mcpb/manifest.template.json`), `glama.json`, `smithery.yaml` | repo root |
| Commercial angle | Repo is the self-host arm of a hosted product "ERPipe" (`https://mcp.erpipe.com/mcp`, 43 tools + OAuth + HITL inbox). README comparison table markets local vs hosted. | `README.md:34,43-45`; `pyproject.toml` description |

---

## 2. Architecture

Explicitly layered, and the layering is **machine-enforced** — the single most unusual
structural property of this repo.

### Module map (from `docs/architecture.md`, verified against code)

**Entry point / bootstrap**
- `src/odoo_mcp/__main__.py` (366 LOC) — CLI (`odoo-mcp` console script → `odoo_mcp.__main__:main`), transport selection, HTTP bind safety, OAuth wiring, `--health` non-secret JSON, `--setup` wizard dispatch, secret masking in startup logs.
- `run_server.py` — thin repo-root launcher.
- `src/odoo_mcp/setup_wizard.py` — interactive `--setup`: prompt, test connection, write config, print client snippets.

**Surface (top layer)**
- `src/odoo_mcp/server.py` (431 LOC) — *pure re-export aggregator*. Importing it imports every `tools_*` module, which is what registers all tools/resources/prompts. Also the monkeypatch seam every test and tool module resolves through.
- `src/odoo_mcp/server_core.py` (759 LOC) — owns the `MCPServer` singleton `mcp`, `AppContext` + `app_lifespan`, instance resolution (`_resolve_odoo`), the schema cache wrapper, smart-field resolution, the **write-approval store**, `odoo://` resources, plugin loading, tool filtering, N+1 tracking, `runtime_security_report()`.
- `tools_read.py` (12 tools), `tools_write.py` (5), `tools_diagnostics.py` (11), `tools_knowledge.py` (3), `tools_accounting.py` (2), `tools_cross_instance.py` (3), `tools_async.py` (4), `tools_data_quality.py` (1) = **41 tools**; `prompts.py` + `prompts_workflows.py` = 11 prompts.
- `plugin_api.py` — the stable third-party plugin surface.

**Core (bottom layer, no MCP imports)**
- `odoo_client.py` — XML-RPC + JSON-2 transport, config loading, client factory.
- `agent_tools.py` — pure write-preview/validate/token builders, domain builder, AST addon scanner, business packs.
- `diagnostics.py` — method-safety classification, JSON-2 payload mapping, migration risk, error sanitization.
- `tool_helpers.py`, `field_ranking.py`, `schema_cache.py`, `access_helpers.py`, `knowledge_index.py`, `accounting_tools.py`, `data_quality.py`, `cross_instance.py`, `task_queue.py`, `rate_limit.py`, `write_policy.py`, `field_policy.py`, `audit.py`, `auth.py`, `schemas.py`.

### Dependency direction — enforced, not aspirational

`.importlinter` declares two contracts run as a CI/dev gate (`PYTHONPATH=src lint-imports`):

```ini
[importlinter:contract:core-no-surface]
type = forbidden
source_modules = odoo_mcp.tool_helpers, ... odoo_mcp.odoo_client, odoo_mcp.audit, ...
forbidden_modules = odoo_mcp.server, odoo_mcp.server_core, odoo_mcp.tools_read, ...

[importlinter:contract:surface-layering]
type = layers
layers =
    odoo_mcp.server
    odoo_mcp.tools_async
    odoo_mcp.plugin_api | odoo_mcp.tools_read | odoo_mcp.tools_write | ... | odoo_mcp.prompts
    odoo_mcp.server_core
```

19 core modules are *forbidden* from importing any surface module. The only ignored edges are
the deliberate late `from . import server` lookups (`_srv()`), which exist so
`monkeypatch.setattr(server, ...)` keeps working in tests — documented in
`server_core.py:44-47` and `docs/architecture.md` "Import contracts".

### How tools get registered

Decorator on the module-level singleton:

```python
# src/odoo_mcp/server_core.py:132
mcp = MCPServer("Odoo MCP Server", instructions=load_server_instructions(),
                dependencies=["requests"], lifespan=app_lifespan)
```

Each `tools_*.py` does `from .server_core import mcp` then `@mcp.tool(description=..., annotations=..., structured_output=True)`. Importing `server.py` pulls in all tool modules → registration is an import side effect. `server.py` then re-exports every public symbol so `from odoo_mcp.server import search_records` works.

Three shared `ToolAnnotations` constants classify every tool for the client
(`server_core.py:139-157`): `READ_ONLY_TOOL` (read_only/idempotent), `PREVIEW_TOOL`
(read_only, closed-world), `DESTRUCTIVE_TOOL` (`destructive_hint=True`).

Two post-registration hooks in `server_core.py`:
- `load_plugins()` (688) — entry-point group `odoo_mcp.tools`, only names in `ODOO_MCP_PLUGINS` load; a raising plugin is recorded, never fatal.
- `apply_tool_filter()` (725) — `ODOO_MCP_TOOLS_INCLUDE` / `_EXCLUDE` CSV fnmatch globs delete entries straight out of `mcp._tool_manager._tools`. Rationale in README:281 — "small agents drown in 41 tools".

---

## 3. Odoo connection layer

### Two protocols, one abstraction with a leak

`src/odoo_mcp/odoo_client.py` supports `SUPPORTED_TRANSPORTS = {"xmlrpc", "json2"}` (line 28),
selected per instance by `ODOO_TRANSPORT` / config `transport` key. XML-RPC is the default;
JSON-2 is opt-in for Odoo 19+.

The abstraction is a **single dispatch point** — `_execute_once` (line 248):

```python
def _execute_once(self, model, method, args, kwargs):
    if self.transport == "json2":
        payload = self._build_json2_payload(model, method, args, kwargs)
        return self._json2_call(model, method, payload)
    return self._models.execute_kw(
        self.db, self.uid, self.password, model, method, list(args), kwargs)
```

Every call in the whole server funnels through `execute_method` → `_execute` → `_execute_once`.
So it is **one abstraction, not two code paths** — *except* that the positional→named argument
translation JSON-2 needs is only defined for a fixed table
(`JSON2_POSITIONAL_ARG_MAP` in `diagnostics.py:13`). Anything outside it raises:

```python
# odoo_client.py:275
raise ValueError(f"JSON-2 transport requires keyword arguments for {model}.{method}; "
                 "positional arguments are only mapped for common ORM methods. ...")
```

That is the leak: an arbitrary `execute_method` call that works on XML-RPC can fail on JSON-2.
`docs/architecture.md` "Odoo transport model" states the recommendation matrix (16/17/18 →
XML-RPC, 19 → JSON-2 or XML-RPC).

### Authentication

- **XML-RPC** (`_connect_xmlrpc`, line 147): `ServerProxy(f"{url}/xmlrpc/2/common")` → `self.uid = self._common.authenticate(db, username, password, {})`; raises `ValueError("Authentication failed: Invalid username or password")` on falsy uid. The **password (or API key used as password) is re-sent on every single call** — that is how `execute_kw` works, not a defect of this code.
- **JSON-2** (`_connect_json2`, line 188): bearer token. `self.api_key = api_key or (password if self.transport == "json2" else None)` (line 113) — i.e. in JSON-2 mode the password field doubles as the API key. Auth is *validated* by a probe call `res.users.context_get`. Header: `Authorization: bearer {api_key}` (line 308, lowercase "bearer"), plus `X-Odoo-Database` when `json2_database_header` is on (line 312). Endpoint shape: `{url}/json/2/{model}/{method}` (line 305).

### Session/uid caching, connection reuse

- `self.uid` cached on the client instance after one `authenticate` call; `_common`/`_models` `ServerProxy` objects are held for the client's lifetime.
- Clients are cached **per instance name** on the lifespan `AppContext` under a `threading.Lock`, and created lazily — an instance is never contacted until a tool targets it (`server_core.py:78-86`).
- Custom `RedirectTransport(xmlrpc.client.Transport)` (line 648) adds timeout, SSL verification toggle, and HTTP-redirect following.
- JSON-2 uses plain `urllib.request` per call — **no connection pooling, no keep-alive** (`_json2_call`, line 300). This is a per-call TCP+TLS handshake.

### Retry

`_execute` (line 217) retries **only read-only methods**:

```python
extra_attempts = _retry_attempts() if method in READ_ONLY_METHODS else 0
```

with exponential backoff `_retry_backoff_seconds() * (2 ** (attempt - 1))`, defaults 2 attempts
/ 0.5 s, caught exception set `(ConnectionError, TimeoutError, socket.error, xmlrpc.client.ProtocolError)`.
`READ_ONLY_METHODS` (`diagnostics.py:36`) = search, search_count, search_read, read, fields_get,
name_get, name_search, context_get. Docstring is explicit: "Anything that may mutate data is
never retried." This is a clean, correct design — retry is keyed on *method identity*, not on
tool identity.

### Error mapping

- JSON-2 HTTP errors → `OdooJson2Error(ValueError)` carrying `status_code`, a **sanitized** `odoo_error` (`sanitize_odoo_error` in `diagnostics.py:165`) and the raw body; `URLError` → `ConnectionError`.
- Every tool wraps its body in `try/except Exception` and returns `{"success": False, "error": str(e)}` — **no exception ever crosses the MCP tool boundary**. `docs/adding-a-tool.md` states this as rule 2: "Never raise through the tool boundary."
- One genuinely sharp piece of Odoo knowledge (`tools_write.py:60-62, 789-803`): Odoo marshals XML-RPC with `allow_none=False`, so a method returning `None` **executes and commits** and *then* faults. `execute_method` detects the marker string `"cannot marshal None unless allow_none is enabled"` and returns `success: True` with a warning, rather than a "phantom failure that tempts a retry of a side-effect method."

---

## 4. Tool design

**41 tools, domain-mixed: a generic-CRUD core wrapped in safety, plus ~25 domain/diagnostic
specialists.** Not the "35 narrow business tools" shape; not a raw CRUD passthrough either.

### Read (`tools_read.py`, 12)
| Tool | One line |
| --- | --- |
| `get_odoo_profile` | Version, modules, user context, transport posture. |
| `schema_catalog` | Model/field discovery catalog. |
| `health_check` | Full non-secret runtime posture (see §7). |
| `list_instances` | Names/URLs/DBs/transports via explicit allowlist; credentials never serialized. |
| `list_models` | List installed models. |
| `get_model_fields` | `fields_get`, with ACL-restricted fields **marked** (not hidden) and optional relevance ranking. |
| `search_records` | Bounded `search_read` + smart fields + free-text `query` shortcut. |
| `read_record` | Single record by id; feeds the N+1 detector. |
| `read_attachment` | `ir.attachment` metadata + base64 content under a cap. |
| `aggregate_records` | Server-side `read_group`; ACL-checked. |
| `search_employee` | Curated HR identity projection. |
| `search_holidays` | Curated leave/calendar projection. |

### Write (`tools_write.py`, 5)
`preview_write`, `validate_write`, `execute_approved_write`, `chatter_post`, `execute_method`.

### Diagnostics/migration (`tools_diagnostics.py`, 11)
`diagnose_odoo_call`, `generate_json2_payload`, `inspect_model_relationships`, `diagnose_access`
(ACL + record-rule analysis using only the current credential, "no sudo or impersonation" —
`docs/architecture.md`), `upgrade_risk_report`, `analyze_upgrade_log`, `lookup_model_history`
(model-rename catalog from `data/odoo_renames.json`), `fit_gap_report`, `scan_addons_source`
(static AST scan, never imports addon code), `build_domain`, `business_pack_report`.

### Other
- Knowledge (3): `index_knowledge`, `search_knowledge`, `knowledge_stats` — a **local pure-Python BM25 index** (`knowledge_index.py`), bounded by `ODOO_MCP_KNOWLEDGE_MAX_DOCS`.
- Accounting (2): `receivable_payable_aging`, `accounting_health_summary` — read-only, pure bucket builders in `accounting_tools.py`.
- Cross-instance (3): `search_across_instances`, `aggregate_across_instances`, `accounting_health_across_instances`.
- Async (4): `submit_async_task`, `get_async_task`, `cancel_async_task`, `list_async_tasks` — bounded thread pool over an **allowlist** of long-running read operations (`task_queue.py`).
- Data quality (1): `data_quality_report`.

### Input schema style
Plain Python type hints on the tool function; the SDK derives the JSON Schema. The ~10
highest-traffic tools additionally use `Annotated[T, Field(description=...)]` per parameter
(CHANGELOG 1.2.1: "the 10 highest-traffic tools describe their parameters to MCP clients").
Every Odoo-touching tool takes an optional `instance: Optional[str] = None`.

### Output format
Uniform envelope `{"success": bool, ...}` / `{"success": False, "error": str}` — a documented
contract (`docs/adding-a-tool.md` rule 2). All tools declare `structured_output=True`;
`schemas.py` (259 LOC) holds Pydantic response models used as **`outputSchema` advertisements**
in `tools/list` while the functions still return plain dicts — a deliberate mismatch declared in
`pyproject.toml`:

> "Tool modules annotate protocol-level response models (typed MCP outputSchema) while the
> functions keep returning the plain-dict envelope MCPServer validates at the MCP layer; the
> runtime dict/model mismatch is deliberate."

### "Smart fields"
`field_ranking.py:153 select_smart_fields()` — when the caller omits `fields`, the server picks
at most `ODOO_MCP_MAX_SMART_FIELDS` (default **15**) fields by: dropping technical names
(`_TECHNICAL_FIELD_NAMES` / prefixes), dropping binary/computed/audit noise
(`_is_skip_metadata`), scoring the rest against a priority table (`_PRIORITY_FIELD_NAMES`:
name, code, state, partner_id, …), sorting by `(-score, name)`, always forcing `id`.
`resolve_read_fields` (`server_core.py:230`) gives the caller three modes: `None` → smart,
`["*"]` → all fields (returns `None`, i.e. no projection), explicit list → verbatim.
A second ranker, `rank_relevant_fields`, powers `get_model_fields(relevance="top")`.
A third, `build_text_query_domain` + `select_text_query_fields` (max 5 fields), turns
`query="acme"` into an OR-`ilike` domain so agents don't hand-craft fuzzy domains.

### Pagination / limits
`MAX_SEARCH_LIMIT = 100` hard ceiling via `clamp_limit()` (`tool_helpers.py:113`) — `limit<1`
raises, anything above 100 is silently clamped. `offset` supported on `search_records`.
Cross-instance: `DEFAULT_LIMIT_PER_INSTANCE = 50`, `MAX_LIMIT_PER_INSTANCE = 100`.
Attachment download cap 1 MiB default / 16 MiB hard cap; upload cap 10 MiB default / same hard
cap. Batch create capped at `MAX_WRITE_BATCH_SIZE = 100` (`agent_tools.py:117`).

---

## 5. Write-path flow, step by step

### Step 1 — `preview_write` (`tools_write.py:206`, logic in `agent_tools.py:120`)
Pure, no network, no Odoo client instantiated (`"metadata_used": {"client_instantiated": False}`).
Checks: operation ∈ {create, write, unlink}; create needs non-empty values; write/unlink need
`record_ids`; write needs values; `values_list` only for create, not both with `values`,
non-empty, ≤100 entries, each a non-empty dict. Builds the **canonical payload**:

```python
canonical_payload = {"model", "operation", "record_ids", "values", "context", "instance"}
# "values_list" key added ONLY for batches "so single-write tokens stay unchanged"
approval_token = build_approval_token(canonical_payload)
```

Returns `{success, approval: {**canonical_payload, token}, execute_method: {...}, issues, warnings}`.
Emits an audit event `event="preview"`.

### Step 2 — `validate_write` (`tools_write.py:250`)
1. `_resolve_binary_from_path_fields(values)` — any `<field>_from_path` key is replaced with a
   `sha256:<hex>:<len>` fingerprint; the real base64 is kept **server-side only** and never
   hashed into the token or echoed to the caller (`tools_write.py:94-123`).
2. `*_from_path` uploads are **refused** unless validating against live metadata.
3. Fetches live `fields_get` unless the caller passed `fields_metadata` or set
   `use_live_metadata=False`. Empty live metadata → hard refusal:
   `"live fields_get metadata was empty; refusing to approve writes"`.
4. `validate_write_report` (`agent_tools.py:331`) re-runs the preview and adds metadata checks:
   unknown field → **error**; `readonly` field → **error**; many2one / x2many → *hints*;
   create-path required-and-not-readonly-and-not-computed fields missing → *hint*.
5. **The authorization decision:**
   ```python
   trusted_live_metadata = (metadata_source == "server"
                            and isinstance(fields_metadata, dict) and bool(fields_metadata))
   if trusted_live_metadata: stored = register_write_approval(...)
   else: report["approval_status"] = {"stored": False, "reason":
         "execute_approved_write requires validation against trusted live Odoo fields_get metadata"}
   ```
   Client-supplied metadata can *explain* issues but can never *authorize*. Audit event
   `event="validate"`, outcome approved/rejected.

`register_write_approval` (`server_core.py:293`) stores
`{approval, payload, validated_at, expires_at}` (+ `resolved_binary_values`) in
`app_context.write_approvals[token]`, TTL `WRITE_APPROVAL_TTL_SECONDS = 10 * 60`, and first
sweeps expired records so abandoned base64 uploads don't linger in RAM (`_sweep_expired_write_approvals`, with an explicit memory-leak rationale in its docstring).

### Step 3 — `execute_approved_write` (`tools_write.py:364` async wrapper → `403` → `428` gated body)
Gates in order (`_execute_approved_write_gated`):

| # | Gate | Failure message |
| --- | --- | --- |
| 0 | **Human elicitation** (only if `ODOO_MCP_ELICIT_WRITES=1`) | "write declined by the human reviewer via elicitation" |
| 1 | `verify_write_approval(approval)` — recompute SHA-256 over the canonical payload, compare to token | "approval token does not match the canonical payload" |
| 2 | `require_validated_write_approval` — token must exist in `app_context.write_approvals` and not be past `expires_at` (evicts on access) | "…has not been validated in this server session or has expired" |
| 3 | `write_approval_payload(approval) != validation_record["payload"]` | "approval payload does not match the stored validation record" |
| 4 | `confirm is True` | "confirm=true is required for destructive execution" |
| 5 | `writes_enabled()` i.e. `ODOO_MCP_ENABLE_WRITES` truthy | "write execution disabled; set ODOO_MCP_ENABLE_WRITES=1 to enable" |
| 6 | `validate_model_name`, operation ∈ {create, write, unlink} | ValueError |

Then it swaps the real base64 back in for fingerprinted binary fields, picks the Odoo client
**from the approval record's `instance`, never from a tool argument**
(`tools_write.py:502-509`), calls `odoo.execute_method(model, operation, *args, **kwargs)`, and
**pops the token** — single use (`tools_write.py:512`). Audit event `event="execute"`.

### The approval token itself

```python
# agent_tools.py:105-114
def canonical_json(value): return json.dumps(_normalize_numbers(value), sort_keys=True,
                                             separators=(",", ":"), default=str)
def build_approval_token(payload):
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"odoo-write:{digest[:32]}"
```

**It is an unkeyed content hash — no secret, no nonce, no session id, no timestamp.** The token
is a *checksum of intent*, not a capability credential. Its real anti-replay property comes
entirely from gate 2 + 3 (the in-memory `write_approvals` record) and single-use pop at gate 7.
`_normalize_numbers` collapses integral floats to ints before hashing, so a payload that crosses
a JS/TS transport and back (`1` → `1.0`) still matches — a real bug fixed in 1.2.1.

**Instance binding:** `"instance"` is one of the six canonical payload keys, so a token computed
for instance A cannot verify against a payload claiming instance B, and execution reads the
instance from the approval only. This is the mechanism the README:328 claim rests on, and the
code backs it.

**Session binding: the README/troubleshooting claim is weaker than the code delivers.**
`README.md:87` says "a same-session token" and `docs/troubleshooting.md:60` says tokens "are
session-bound". The store lives on `AppContext`, created once in `app_lifespan`
(`server_core.py:89-95`) — i.e. **per server process, not per MCP session**. On stdio that
distinction is invisible (one client per process). On Streamable HTTP, where multiple client
sessions share one lifespan context, a token validated by session A is executable by session B.
Nothing in the approval record stores a session id. **This is a README-vs-code contradiction.**

### What the env gates cover
- `ODOO_MCP_ENABLE_WRITES` (`write_policy.py:16`): gates **only** `execute_approved_write`. It does **not** gate `chatter_post` and does **not** gate `execute_method` — both of those can mutate Odoo with writes "disabled", subject to their own allowlists. `runtime_security_report` reports it as `write_execution_enabled`.
- `ODOO_MCP_ELICIT_WRITES` (`ELICIT_WRITES_ENV`, `server_core.py:563`): opt-in human confirmation. Two code paths: the SDK's `Resolve(_resolve_write_confirmation)` dependency (MRTR on modern clients) and an `await ctx.elicit(...)` fallback for direct Python callers. Critically, **when the gate is off or the client can't elicit, it returns `WriteConfirmation(approve=True)`** (`tools_write.py:157, 165`) — fail-open by design, with the token flow as the stated fallback.

### `execute_method` allowlisting (`tools_write.py:709`)
1. `validate_model_name` / `validate_method_name` (regex, `tool_helpers.py:19-20`).
2. `method in DESTRUCTIVE_METHODS {create, write, unlink}` → **blocked outright**, pointed at the gated flow. No escape hatch.
3. `classify_method_safety(method)` (`diagnostics.py:73`) — name-based heuristic: destructive set; read-only set *or* `get_`/`_get_` prefix → read_only; `message_post` or `^action_`, `^button_`, `(^|_)send($|_)`, `(^|_)post($|_)`, `(^|_)validate($|_)` → side_effect; anything else → **unknown**.
4. `side_effect` **and** `unknown` are both blocked unless the exact `model.method` string is in the allowlist (`ODOO_MCP_ALLOWED_SIDE_EFFECT_METHODS` env ∪ the JSON policy file's `allowed_side_effect_methods`) or the broad escape hatch `ODOO_MCP_ALLOW_UNKNOWN_METHODS=1` is set. Blocking `unknown` by default is the strong choice here — a custom method with a neutral name is denied, not allowed.
5. The policy file is **re-read on every request** (`load_side_effect_policy()` → `Path(path).read_text()` with no cache) — no restart needed, but also one file read per call. Entries may be strings or objects carrying review metadata (`reviewed_by`, `date`, `reason`) — `odoo_mcp_policy.json.example`.
6. A broken policy file contributes **zero methods** (fail closed) and surfaces its error in `health_check` (`write_policy.py:36-61`).

### `chatter_post` (`tools_write.py:562`)
A *separate, weaker* two-call gate: first call returns `mode=preview` with a token built from a
canonical `message_post` payload; second call with the same args + `approval` + `confirm=true`
posts. Token equality is checked **against a freshly recomputed token in the same call**
(`provided_token != token`), so there is no server-side store, no TTL, no live-metadata
requirement, and no `ODOO_MCP_ENABLE_WRITES` check. `MCP_CHATTER_DIRECT=1` removes the gate
entirely.

---

## 6. Permission / security model

### Account model
**Single Odoo credential per configured instance** — there is no per-MCP-user impersonation and
no `sudo`. `docs/architecture.md`: `diagnose_access` "reads ACL, record-rule, current-user, and
optional count metadata using only the current Odoo credential; it does not use sudo or
impersonation." Isolation between tenants is achieved by **named instances inside one process**,
each with a self-contained credential.

Credential isolation is explicit and tested: `build_odoo_client` (`odoo_client.py:908`) comments
that `api_key` must not inherit another deployment's key; `docs/architecture.md` states
"Instance entries are self-contained: credentials and transport never fall back to env vars…
Non-credential knobs (`ODOO_TIMEOUT`, `ODOO_VERIFY_SSL`, `ODOO_LOCALE`) remain global fallbacks."
`list_instances` serializes through an explicit allowlist of non-secret keys.

### Field-level ACL (`field_policy.py`, 249 LOC + `docs/field-acl.md`)
Format — a `field_acl` key in the shared policy file (`ODOO_MCP_POLICY_FILE`, default
`./odoo_mcp_policy.json`) or a dedicated `ODOO_MCP_FIELD_POLICY_FILE`:

```json
{"field_acl": {"default": {"res.partner": {"deny": ["credit_limit","comment"]},
                           "hr.employee": {"allow": ["name","work_email"]},
                           "*":           {"deny": ["message_ids"]}}}}
```

Semantics: per-instance → per-model; **exactly one** of `deny` (blacklist) or `allow`
(exclusive whitelist), enforced at parse time; `*` is a per-instance model wildcard whose rules
merge with the specific model's — `deny` sets **union**, `allow` sets **intersect**
(`_effective`, line 66); `id` is in `ALWAYS_KEPT` and never redactable.

Fail-closed on malformed policy: `get_field_policy()` is called in `app_lifespan` **before
yielding** specifically so "a malformed policy fails closed (aborts) instead of silently running
unprotected at first read" (`server_core.py:92-94`). Policy is parsed once and cached
process-wide behind a lock.

**Is it one choke point? Mostly — the class is one choke point but the *call sites* are
scattered, and at least two paths miss it.** Enforcement calls (verified by grep):
`tools_read.py:353` (`get_model_fields` marks restricted), `:449` (`search_records`),
`:506` (`read_record`), `:669` (`aggregate_records` — blocks grouping/aggregating on a denied
field to prevent value inference); `tools_cross_instance.py:117, 160`; `tools_knowledge.py:54`;
`server_core.py:629, 654` (`odoo://record`, `odoo://search`); `data_quality.py:292`;
`plugin_api.py:52` (exposed to plugins as `redact_records`). Nine-plus independent call sites;
adding a tool means remembering to call it (`docs/adding-a-tool.md` rule 5 says so explicitly —
though it names a function `apply_field_policy` that **does not exist** in the code; the real
API is `get_field_policy().redact_records`).

Two gaps, both in the code, only one admitted in the docs:
- **`execute_method` bypasses field ACL entirely.** `tools_write.py` never imports `field_policy`. `classify_method_safety("search_read")` → `read_only` → allowed by default → the raw rows are returned with no redaction. So `execute_method("res.partner", "search_read", [[]], fields=["credit_limit"])` returns a field the policy denies to `search_records`. `docs/field-acl.md`'s "Limits (read this)" section lists curated tools, `read_attachment`, writes, and server-side-only — it **does not mention `execute_method`**, and no grep hit ties the two in any doc. This is the sharpest code-vs-doc gap I found.
- **`read_attachment` is not redacted** despite `docs/field-acl.md:78-80` saying "Field ACL applies to the metadata dict". The function (`tools_read.py:527-617`) reads a hardcoded field list and returns it with no `get_field_policy()` call. The hardcoded projection makes the practical risk low, but the doc claim is inaccurate.
- Curated `search_employee` / `search_holidays` being outside redaction *is* documented as intentional.

### Credential handling
- Never written by the server; never serialized into any tool output.
- Startup log masking: `SECRET_ENV_KEYS = {"ODOO_PASSWORD", "ODOO_API_KEY", "MCP_HTTP_AUTH_TOKEN"}` plus a suffix rule (`_SECRET`, …) in `is_secret_env_key` (`__main__.py:20, 146`). Note `MCP_HTTP_AUTH_TOKEN` is masked but **never read anywhere else in `src/`** — dead config surface.
- `sanitize_odoo_error` redacts JSON-2 debug detail by default (`diagnostics.py:165`; `OdooJson2Error` keeps the raw body but only in the structured field).

### Transport security (`__main__.py`)
- Default transport **stdio**. Streamable HTTP and SSE opt-in; SSE prints a deprecation warning.
- **Fail-closed non-local bind**: `if transport in {streamable-http, sse} and host not in {"127.0.0.1","localhost","::1"} and not allow_remote_http: raise ValueError(...)` — you must pass `--allow-remote-http` / `MCP_ALLOW_REMOTE_HTTP=1` (`__main__.py:226-235`).
- SDK `TransportSecuritySettings(allowed_hosts=…, allowed_origins=…)` with defaults `["127.0.0.1:*","localhost:*","[::1]:*"]`; `security.enable_dns_rebinding_protection` is reported in `--health`. `docs/architecture.md` and `SECURITY.md` both insist these are "hardening controls, not authentication."
- **OAuth 2.1 resource server** (`auth.py`, 252 LOC): opt-in via `ODOO_MCP_AUTH_*`; RFC 9728 protected-resource metadata; tokens validated by **RFC 7662 introspection** (`IntrospectionTokenVerifier`) with a bounded TTL cache (default 60 s, stated risk: "a revoked token stays accepted for at most this long"); optional `aud` (RFC 8707) and `iss` strictness flags. Prints a warning and no-ops on stdio.
  **`SECURITY.md:39` contradicts this**: "this server does not implement built-in HTTP authentication." The OAuth layer clearly does; SECURITY.md was not updated.

### Input sanitization
- `MODEL_NAME_RE = ^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$`, `METHOD_NAME_RE = ^[a-zA-Z_][a-zA-Z0-9_]*$` applied on every model/method-taking tool.
- `normalize_domain_input` (`tool_helpers.py:288`) accepts domain arrays, JSON strings, Python literals, or `{"conditions":[...]}` — and since **v1.3.1 rejects unparseable non-empty input instead of degrading to `[]`**. The CHANGELOG states the failure mode plainly: "A search filter that the server cannot understand is now rejected instead of matching every record." That is a real, shipped, agent-safety bug class.
- Path confinement, twice, with mirrored code: `restrict_addons_paths` (source scans must live under `ODOO_ADDONS_PATHS`) and `restrict_attachment_upload_path` (`*_from_path` uploads must live under `ODOO_MCP_ATTACHMENT_UPLOAD_ROOTS`, **required — no roots means refusal**). Rationale is in the docstring: "a prompt-injected agent could read and exfiltrate arbitrary local files (SSH keys, other clients' data, …) as an Odoo attachment."
- **TOCTOU-hardened file read** (`_read_attachment_source_file`, `tools_write.py:65-91`): single `os.open` with `O_NOFOLLOW`, `fstat` on that fd for both regular-file and size checks, hash derived from the bytes read through the same fd. The docstring reasons it out explicitly. This is unusually careful for an MCP server.

---

## 7. Audit / logging / observability

**JSONL audit trail** — `audit.py` (81 LOC), opt-in via `ODOO_MCP_AUDIT_LOG=<path>`.
One line per event, fields:

```python
{"ts": "%Y-%m-%dT%H:%M:%SZ", "event", "outcome", "model", "operation",
 "record_ids": [...], "instance", "token_sha256", "detail"}
```

- Events emitted: `preview`, `validate`, `execute`, `elicit` (on decline), `chatter_post`, `cross_instance_query`.
- Outcomes: success / rejected / approved / denied / declined / ok.
- **Tokens are stored as a truncated SHA-256 digest** (`hashlib.sha256(token)[:16]`), never clear text.
- Writes are serialized by a `threading.Lock`, appended with `open(path,"a")`.
- **Fail-open by design**: an `OSError` logs a warning and returns `False` without blocking the operation. The docstring says so and tells operators who need fail-closed to "alert on the warning log line."
- **No hash chaining, no tamper-evidence, no verifier.** Nothing in the repo links line N to line N−1. `grep` for chain/hmac in `audit.py` returns nothing. The `token_sha256` is a per-event digest of the approval token, not a chain link.

**Structured logging**: minimal. Most runtime chatter is `print(..., file=sys.stderr)` inside
`odoo_client.py` (connection, retry, JSON-2 request lines). Only `audit.py` and `auth.py` use
the `logging` module. `mcp.settings.log_level` is set from `--log-level`.

**Observability via `health_check`** (`runtime_security_report()`, `server_core.py:520`) — a
genuinely rich, secret-free posture endpoint, also available as `uvx odoo-mcp --health` without
starting a server. It reports: transport/host/port/path, `remote_http_allowed`,
`write_execution_enabled`, `unknown_execute_method_enabled` **with a `risk: "broad"|"off"` field
and a recommendation string**, `chatter_direct_enabled`, the resolved side-effect allowlist and
where it came from (file path, file/env method counts, parse error), `allowed_hosts`/`origins`,
instance counts, audit posture, oauth posture, field-ACL posture (active + rule count, never
contents), plugin posture, rate posture, `mcp_surface_counts` read live from the SDK managers,
and the **N+1 report**.

**N+1 detector** (`server_core.py:430-476`): `read_record` calls are timestamped per
`(instance, model)`; ≥10 in a 60 s sliding window surfaces a `hot_models` entry with the literal
remediation string *"Batch with search_records using an ["id","in",[...]] domain instead of
looping read_record."* — observability aimed at correcting the *agent*, not the operator.

**Rate limiting** (`rate_limit.py`): opt-in three-mode (`off`/`warn`/`block`) sliding window
keyed `instance:tool`, default 120 calls / 60 s, tracked key set bounded at 512 (evicts the
stalest wholesale). `warn` counts over-budget calls so counters reflect real volume; `block`
excludes refused calls "so they do not extend the blocked window" — a small but correct detail.
Applied per-tool via explicit `check_rate(...)` calls, not middleware.

---

## 8. Testing strategy

- **891 test functions / 13,812 LOC across 39 files** — more test code than source code (11,900).
- **Odoo is mocked, not live, in the unit suite.** No `pytest.ini`/markers, no integration marker, no network. Tests monkeypatch the `odoo_mcp.server` module's patchable symbols (`get_odoo_client`, `resolve_instance_name`, …), which is precisely why the `_srv()` late-binding seam exists throughout the codebase.
- **The conftest fixture is the most instructive part** (`tests/conftest.py:14-31`): an autouse fixture deletes `ODOO_URL/DB/USERNAME/PASSWORD` and points `ODOO_CONFIG_FILE` at a nonexistent path, because a developer machine carrying a real config silently changes instance resolution and "the suite starts depending on whatever the developer configured." That is a hermeticity bug they hit and fixed (CHANGELOG 1.2.1: "the suite is hermetic on developer machines that carry a real Odoo config").
- **Real-Odoo coverage is a separate Docker Compose smoke harness**, not pytest: `scripts/odoo_compose_smoke.py` spins disposable Odoo 16.0/17.0/18.0/19.0 stacks, mounts `tests/fixtures/odoo_addons` as `/mnt/extra-addons`, installs/updates a real fixture addon `mcp_smoke_access` with XML-defined record rules and a dedicated restricted credential, then exercises XML-RPC reads, JSON-2 (19.0), MCP stdio tool/resource/prompt listing, and record-rule diagnosis **through MCP as that restricted user without sudo** (`docs/testing.md`, `docs/architecture.md` "Smoke harness"). There is also `scripts/odoo_multi_instance_smoke.py`.
- Notable brittleness admitted in `docs/adding-a-tool.md`: "`scripts/odoo_compose_smoke.py` asserts the **exact tool count** and some response strings — adding a tool without updating it breaks the smoke run."
- CI (`publish.yml`) runs pytest on 3.10/3.11/3.12 for every PR and push to main. `ruff`, `mypy src`, and `lint-imports` are documented pre-PR gates in `docs/testing.md` / `docs/adding-a-tool.md`.
- A dedicated `tests/test_field_acl_enforcement.py` exists — but it contains **zero references to `execute_method`**, which is consistent with that bypass never having been considered.

---

## 9. Extensibility

### Adding a builtin tool — the documented ritual (`docs/adding-a-tool.md`)
1. Put pure logic in a **core** module; put the thin `@mcp.tool` wrapper in the matching `tools_*.py`. New module → add it to the right `.importlinter` contract.
2. Return the `{"success": ...}` envelope; never raise through the tool boundary.
3. Re-export the symbol in `server.py`'s import block **and** `__all__`.
4. Resolve test-patchable symbols through the module-local `_srv()` seam.
5. Any tool returning record data must pass through the field-policy choke point and clamp sizes (`clamp_limit`, `MAX_SEARCH_LIMIT`).
6. Write-capable behavior must route through preview→validate→execute: "PRs that bypass the gate are declined."
7. Update `scripts/odoo_compose_smoke.py`'s tool-count assertion and any doc tables stating counts.

### Plugin mechanism — real, opt-in, isolated
`plugin_api.py` (v1, `PLUGIN_API_VERSION = 1`) + `load_plugins()` (`server_core.py:688`) +
`examples/plugin-example/` + `docs/plugins.md`.

```toml
[project.entry-points."odoo_mcp.tools"]
my_plugin = "my_pkg.plugin:register"
```

- Discovery via `importlib.metadata.entry_points(group="odoo_mcp.tools")`.
- **Installation alone never activates code** — only names listed in `ODOO_MCP_PLUGINS` load.
- A raising plugin is caught per-plugin and recorded in `PLUGIN_STATE["failed"]`, surfaced in `health_check`; never fatal.
- The API hands plugins exactly four things: `api.tool` (the decorator), `api.resolve_odoo`, `api.redact_records` (so plugins can honor the field ACL), `api.error_envelope`, plus `clamp_limit`/`validate_model_name` and the annotation constants.
- Honest threat statement in the module docstring: "Plugins run in the server process with the server's credentials — install only plugins you trust, and route any data modification through the gated write workflow (direct writes in plugins are a contract violation)." Note this is a **contract, not an enforcement** — nothing stops a plugin calling `client.execute_method(..., "write", ...)`.

### Per-deployment surface trimming
`ODOO_MCP_TOOLS_INCLUDE` / `ODOO_MCP_TOOLS_EXCLUDE` CSV fnmatch globs delete tools from the
registry post-registration (`apply_tool_filter`). Also `ODOO_MCP_INSTRUCTIONS_FILE` appends
operator text (capped 16,000 chars) to the MCP server-level `instructions` field — "deployment-specific guidance without touching tool descriptions (idea: GH-19, thanks @oadiazp)".

---

## 10. Notable design decisions and stated rationale

Quoted or paraphrased from code comments, docs, and CHANGELOG:

1. **"A thin MCP server around a deliberately small Odoo client. … give agents high-signal Odoo context while keeping execution paths inspectable and bounded."** (`docs/architecture.md` opening) — the whole design thesis.
2. **Zero Odoo-side installation.** README:49: "using only your existing credentials. No App Store module, no permission setup, no admin access required." This is the explicit competitive position vs Odoo-module-based bridges, and it's what forces every control into the MCP process.
3. **Layering enforced by a linter, not convention** (`.importlinter`, `docs/architecture.md` "Import contracts"). The `_srv()` late-binding seam exists purely to keep tests patchable without violating the contract — an explicit trade of a little indirection for a machine-checkable boundary.
4. **Authorization requires *trusted live* metadata.** `docs/architecture.md`: "`validate_write` stores an executable approval only when validation used trusted, non-empty live Odoo `fields_get` metadata. Client-provided or shape-only metadata can explain issues, but it does not authorize execution." This is the key insight that stops an agent from validating against fabricated schema.
5. **Blocking `unknown` methods, not just `side_effect` ones.** The name heuristic is admitted to be low-confidence, so the default denies anything it cannot positively classify as read-only; the broad escape hatch is kept but **reported as `risk: "broad"`** in health output with a recommendation to prefer exact entries (`server_core.py:536-543`).
6. **Runtime state is deliberately ephemeral.** `docs/architecture.md` "Runtime state": approval tokens "are intended for one MCP server session, not durable queues or cross-process approvals… a restart clears them by design." Same for async task results and knowledge indexes.
7. **Audit fail-open, stated as a choice**, with the mitigation named ("alert on the warning log line") rather than silently accepted (`audit.py:8-10`).
8. **`_normalize_numbers` before hashing** — an int/float transport-drift bug found in the wild and fixed with a 10-line, well-commented normalizer rather than by loosening the token check (CHANGELOG 1.2.1, `agent_tools.py:84-102`).
9. **Reporting a committed write as success when XML-RPC can't marshal `None`** — "Report success, not a phantom failure that tempts a retry of a side-effect method" (`tools_write.py:792-794`). Retry-safety reasoning applied to error *reporting*, not just to retry logic.
10. **`redacted_fields` is returned deliberately**: `docs/field-acl.md:67` — "the agent is told *that* fields were withheld, so it does not hallucinate their absence or values." Same reasoning behind marking (not hiding) restricted fields in `get_model_fields`.
11. **Aggregate blocking as inference defense**: grouping/aggregating on a denied field is refused "to prevent inference" (`field_policy.py:146-156`).
12. **Fail-closed on malformed policy at startup, not at first read** (`server_core.py:92-94`) — the policy load is placed in the lifespan specifically so a typo aborts the server instead of silently serving unprotected data.
13. **v1.3.1's domain fix** is the clearest statement of their agent-safety philosophy: an unparseable filter must be rejected, because degrading to `[]` "silently searches the whole model."
14. **Batch `write` with per-record values is deliberately unsupported**: "they would need one RPC call per record without transactional atomicity" (`agent_tools.py:134-136`). Atomicity chosen over convenience.
15. **`MAX_INSTRUCTIONS_CHARS = 16_000` and a set-but-unreadable instructions path fails at startup** "rather than silently running without the operator's guidance."

---

## 11. Weaknesses / risks spotted in the code

Ordered by how much they'd matter to someone copying this design.

1. **"Session-bound" approvals are process-bound.** (§5) `write_approvals` lives on the single lifespan `AppContext`. Under Streamable HTTP with multiple concurrent client sessions, session B can execute session A's validated approval by replaying the token + payload. The token carries no session identity, and no gate checks one. README:87 and `docs/troubleshooting.md:60` both assert session binding. **Code contradicts docs.**
2. **The approval token is an unkeyed hash of public data.** Anyone who can see a `preview_write` response (or can reconstruct the exact canonical payload — model, op, ids, values, context, instance) can compute a valid token offline. Security rests entirely on the server-side store and the env gate, so the token is best described as an *integrity checksum of intent*, not an authorization credential. Calling it an "approval token" in docs overstates it.
3. **`execute_method` is a field-ACL bypass.** (§6) `search_read`/`read`/`fields_get` are classified read-only and allowed by default; results are returned raw with no redaction. A deployment that denies `res.partner.credit_limit` still leaks it through `execute_method`. Not mentioned in `docs/field-acl.md`'s "Limits" section, not covered in `tests/test_field_acl_enforcement.py`.
4. **`read_attachment` is undocumented-unredacted.** Doc says the metadata dict is ACL-filtered; the code makes no policy call. Low practical impact (hardcoded projection) but the doc is wrong.
5. **`chatter_post` is a second, much weaker write path.** No server-side approval store, no TTL, no live-metadata requirement, and — most importantly — **`ODOO_MCP_ENABLE_WRITES` does not gate it**. An operator who believes "writes are off" can still have an agent post to any `mail.thread` record in two calls, or in one with `MCP_CHATTER_DIRECT=1`. `message_post` can notify partners and create `mail.message` records; it is not a harmless operation.
6. **Elicitation fails open.** `_resolve_write_confirmation` returns `WriteConfirmation(approve=True)` when the client lacks form elicitation (`tools_write.py:164-165`). A client that simply doesn't advertise the capability gets the write approved without a human. Defensible given the token fallback, but it means `ODOO_MCP_ELICIT_WRITES=1` is not a guarantee.
7. **Method safety is name-based only.** `classify_method_safety` treats any `get_*` prefix as read-only with only `"confidence": "medium"` — a custom `get_and_reset_counters()` would be auto-allowed. There is no `fields_get`/introspection-backed verification of what a method actually does.
8. **No runtime coherence between the validated payload and the executed one beyond dict equality.** Gate 3 compares `write_approval_payload(approval)` to the stored payload, which is good — but the *stored* payload was itself derived from caller input at validate time. The live `fields_get` check happens at validate time only; if a field becomes readonly between validate and execute (up to 10 minutes), execution proceeds.
9. **Policy files are read from disk on every `execute_method` call** (`load_side_effect_policy` has no cache, unlike `get_field_policy`). Minor perf cost; more importantly, the file's contents can change mid-session with no audit of the change.
10. **`MCP_HTTP_AUTH_TOKEN` appears only in the secret-masking set** and is never consumed — a dangling config name an operator could reasonably assume enables HTTP auth.
11. **`SECURITY.md:39` is stale**: "this server does not implement built-in HTTP authentication" contradicts the OAuth 2.1 introspection resource server in `auth.py`.
12. **`docs/adding-a-tool.md` names a nonexistent function** (`apply_field_policy`) as the field-ACL entry point; the real call is `get_field_policy().redact_records(...)`. A contributor following the doc literally would fail to find it — and the doc is the only thing making a scattered choke point work.
13. **JSON-2 opens a fresh `urllib` connection per call** with no pooling — for a chatty agent on a TLS endpoint this is a real per-call latency tax that XML-RPC (which reuses `ServerProxy`) does not pay.
14. **`O_NOFOLLOW` is `getattr(os, "O_NOFOLLOW", 0)`** — on Windows the flag doesn't exist, so the TOCTOU/symlink hardening silently degrades to a plain open. Correct fallback behavior, but the protection is platform-conditional and not flagged as such.
15. **`apply_tool_filter` mutates `mcp._tool_manager._tools` directly** — reaching into SDK privates. It guards with an `isinstance` check and no-ops on an unexpected shape, but it will break silently (filters stop applying) on an SDK refactor. Same for `mcp_surface_counts`.
16. **`plugin_api` cannot enforce its own contract.** Plugins get a live Odoo client via `resolve_odoo` and can call `write` directly; "contract violation" is the only deterrent.
17. **Audit has no integrity protection** — plain appended JSONL, fail-open, no chaining, no verifier. An attacker with filesystem access edits history undetectably.

---

## 12. Transferable to the reader's server

Reader's server recap: FastMCP (`mcp.server.fastmcp`), HTTP/SSE on 127.0.0.1, Odoo 19 Community,
100% XML-RPC through one `odoo()` choke point, 35 domain tools, method whitelist, global write
toggle from `ir.config_parameter` (fail-closed), rate limit, event log with argument
fingerprint, hash-chained audit + verifier, per-role isolation via 3–4 processes each with its
own Odoo account, per-write human confirmation in the LangGraph agent layer.
Known gaps: (a) no per-write approval inside the server, (b) no runtime `fields_get` validation
of write payloads, (c) no credential-field filtering on read results.

### Worth copying — mapped to the gaps

**→ Gap (b), highest value: the `validate_write` trusted-metadata rule.**
Copy `validate_write_report`'s check set (`agent_tools.py:279-403`) and, crucially, the
authorization rule that only *server-fetched, non-empty* `fields_get` may authorize
(`tools_write.py:316-340`). Concretely for the reader: before any `create`/`write`, call
`fields_get` through `odoo()`, then reject unknown fields and `readonly: True` fields as errors,
and emit hints for many2one (must be an id) and x2many (must be an Odoo command list). Bounded:
one extra RPC, cacheable per `(model)` with a TTL — the reader already has the choke point to
hang it on. This turns a class of "agent invented a field name" failures from an opaque Odoo
fault into a pre-flight error the agent can fix, and it costs nothing in architecture.
The empty-metadata refusal (`"live fields_get metadata was empty; refusing to approve writes"`)
is the part most people would forget — an Odoo permission problem returns `{}`, and without that
check an empty schema validates everything.

**→ Gap (c): the field-ACL policy, but with one change.**
The `field_policy.py` design is directly liftable: per-instance→per-model, exactly-one-of
`deny`/`allow` validated at parse time, `*` wildcard with union-deny/intersect-allow, `id` never
redactable, parse-at-startup fail-closed, and **returning `redacted_fields` so the model knows
values were withheld rather than absent**. For the reader, the instance dimension maps naturally
onto **role** (sales / kho / accounting / admin), which is a better fit than erpipe's
instance keying and directly extends the reader's per-role process isolation into the field
dimension. Two things to copy verbatim: (i) blocking aggregation/grouping on a denied field to
prevent inference (`field_policy.py:146-156`), and (ii) *marking* denied fields `"access":
"restricted"` in schema output rather than hiding them, so the agent can explain the refusal.
**The change**: the reader has a genuine single choke point (`odoo()`) that erpipe lacks.
Enforce redaction **inside `odoo()` on the response of read methods**, keyed on the model
argument — one site instead of nine. That structurally fixes erpipe's own `execute_method`
bypass (risk #3) before it can exist in the reader's server. Erpipe's scattering is a direct
consequence of having no single RPC choke point; the reader should not copy the scattering.

**→ Gap (a): only partially, and deliberately.**
The reader's per-write confirmation lives in the LangGraph interrupt, which is a *stronger*
place for the human gate than erpipe's elicitation (which fails open — risk #6). What is
still worth adding inside the server is the narrow part erpipe gets right: a **canonical-payload
checksum plus a server-side single-use record**, so the write that executes is provably the
write that was shown to the human. Bounded implementation: hash `{model, operation, ids, values,
context}` with `sort_keys=True, separators=(",",":")` **after** collapsing integral floats
(`_normalize_numbers` — copy it; the reader's JSON boundary has the same `1` → `1.0` hazard),
store it with a TTL, require it at execute, pop on use. Two deltas from erpipe:
- **Key the hash with a per-process secret (HMAC), not a bare SHA-256**, so the token can't be computed offline from a visible preview (risk #2).
- **Bind it to the role/process identity** — the reader's 3–4 processes make this free and it closes erpipe's cross-session replay hole (risk #1) by construction.

**Independently worth copying, small and bounded:**
- **`ToolAnnotations` on all 35 tools** (`READ_ONLY_TOOL` / `DESTRUCTIVE_TOOL`, `server_core.py:139-157`). Pure metadata, zero risk, lets any MCP client show the right confirmation UI. Cheapest item on this list.
- **Retry keyed on method identity, not tool identity** (`odoo_client.py:217-246` + `READ_ONLY_METHODS`). The reader's single `odoo()` is the ideal place: retry connection errors only when the method name is in the read-only set, never otherwise. Given the reader's memory of an SDK auto-retry burning quota, the explicit "writes never retry" invariant is worth having stated in code.
- **The `allow_none` / `None`-marshal trap** (`tools_write.py:60-62, 789-803`). On Odoo XML-RPC a method returning `None` *commits* and then faults. If the reader's `odoo()` surfaces that as a failure, an agent retry double-executes. This is exactly the class of bug the reader already hit once (`order-confirmation-email`: "node-replay double-sent a write"). Detecting the marker string is ~6 lines at the choke point.
- **The N+1 detector** (`server_core.py:430-476`) with its agent-directed remediation string. A sliding window over single-record reads per `(role, model)`, surfaced in a health tool. ~40 lines, and it measures a real cost the reader has already paid attention to (the localhost-per-call findings).
- **A non-secret `--health` posture dump** (`runtime_security_report()`), printable **without starting the server**. Given how many of the reader's incidents were "the config was not what I thought" (Open WebUI invisible config, port collisions, dead models, silently-dead reranker, exhausted keys), a single command that prints write-gate state, allowlist contents and their source, ACL active/rule-count, audit path, and bind address is disproportionately valuable. Copy the `risk: "broad"` + `recommendation` pattern for the dangerous escape hatch specifically.
- **`.importlinter` layering contracts.** The reader's `routing.py` extraction and repeated "the plan's own code was the bug" findings suggest a machine-checked "core must not import surface" contract would pay for itself. It's a config file plus one CI line.
- **The hermetic-config conftest fixture** (`tests/conftest.py:14-31`): force-unset the real credentials env and point the config path at a nonexistent file, so tests can never silently bind to the developer's live instance. This is *precisely* the reader's `feedback_erp_query_live_measurement_account` lesson (a bare `.env` script used a personal account) turned into an autouse fixture. Ten lines.
- **Path confinement with the `O_NOFOLLOW` single-fd read** (`tools_write.py:65-91`) *if and when* the reader adds any local-file → Odoo attachment path. Not needed otherwise.

### Not worth copying, with reasons

- **The bare SHA-256 token.** Unkeyed and computable offline. If the reader adds tokens, HMAC them. Copying the hash *shape* without the key would import risk #2.
- **Calling process-scoped approvals "session-bound."** Copy the mechanism, reject the vocabulary — and write a test that actually asserts cross-session rejection, since erpipe's docs claim a property its code doesn't have.
- **`chatter_post`'s parallel weak gate.** The reader's mail tooling already routes through coordinators and a role-enforced path, with per-write confirmation in the agent. A second write path that skips the global write toggle is exactly the "whole mechanism was dead in prod / invisible to 6 reviews" failure mode the reader has already lived through twice. If chatter/mail writes exist, they must go through the same toggle and the same confirmation.
- **Elicitation-based confirmation as the primary human gate.** It fails open on clients that don't advertise the capability, and the reader's LangGraph interrupt is strictly better: it's in a layer the reader controls, it can't be disabled by a client's capability advertisement, and it already works.
- **Fail-open, unchained JSONL audit.** The reader's hash-chained log with a verifier is strictly stronger. Erpipe's only transferable audit idea is the **event vocabulary** (`preview`/`validate`/`execute`/`elicit`/`chatter_post` × `success`/`rejected`/`approved`/`denied`/`declined`) and storing the token as a digest rather than clear text — worth folding into the reader's existing chain, nothing else.
- **`ODOO_MCP_ALLOW_UNKNOWN_METHODS`-style broad escape hatch.** The reader's method whitelist is already tighter. Adding a global "allow anything" flag re-opens the hole the whitelist closes; erpipe keeps it only for backward compatibility and flags it as `risk: "broad"` in its own health output.
- **The generic `execute_method` tool at all.** It is the source of erpipe's ACL bypass and the reason its method classifier has to be a name heuristic. The reader's 35 domain-specific tools + whitelist is the safer architecture; adding a generic escape hatch would import both problems.
- **The env-var configuration surface (≈30 `ODOO_MCP_*` vars) as a model.** The reader's write toggle reads from Odoo `ir.config_parameter`, which is centrally auditable and changeable without a restart — better than an env var for the property that matters most. Erpipe's env sprawl also creates the `MCP_HTTP_AUTH_TOKEN` class of dead knobs (risk #10).
- **The plugin entry-point system.** Real and well-isolated, but it exists to serve an open-source distribution with third-party contributors. For a single-team internal server it adds an in-process code-loading path with the server's credentials and no enforcement, for no benefit.
- **The JSON-2 transport abstraction.** Interesting as prior art — note their stated timeline (`diagnostics.py`: `ODOO_RPC_REMOVAL = "Odoo 22 fall 2028"`, deprecation at 19, and a comment that Odoo **postponed removal from Odoo 20 to Odoo 22**). That is directly relevant to the reader's 100%-XML-RPC choice: the runway is longer than the Odoo-20 rumor suggested. But erpipe's mapping only covers a fixed table of ORM methods and falls over on anything else, so the abstraction itself is not a finished pattern worth lifting today.

### Answers to the four key questions

1. **Approval token construction / replay defense.** `f"odoo-write:{sha256(canonical_json(payload))[:32]}"` where payload = `{model, operation, record_ids, values, context, instance}` (+ `values_list` for batches), canonicalized with `sort_keys=True, separators=(",",":")` after collapsing integral floats. **No secret, no nonce, no session id.** Replay across *instances* is prevented because `instance` is inside the hashed payload and execution reads the instance from the approval record only. Replay across *sessions* is **not** prevented on HTTP transports — the store is per-process, not per-session, contradicting README:87 and `docs/troubleshooting.md:60`. Single-use is enforced by popping the token after a successful execute, and by a 10-minute TTL with eviction on access plus a sweep on every new registration.
2. **Field ACL: one choke point or scattered?** The *policy object* is one choke point (`field_policy.get_field_policy()`, parsed once, cached, fail-closed at startup). The *enforcement* is scattered across 9+ explicit call sites, and at least two record-returning paths miss it: `execute_method` (complete bypass, undocumented) and `read_attachment` (documented as covered; isn't). `docs/adding-a-tool.md` tries to close this with a convention — and names a function that doesn't exist.
3. **Odoo 19 External JSON-2 vs XML-RPC.** One abstraction layer, one dispatch point (`_execute_once`), selected per-instance by a `transport` setting. Not two parallel code paths. The abstraction leaks in exactly one place: JSON-2 needs named arguments, so positional calls are translated via a fixed `JSON2_POSITIONAL_ARG_MAP` table and anything outside it raises a hard error telling the caller to pass kwargs or use XML-RPC. XML-RPC carries the db per request; JSON-2 sends `X-Odoo-Database` when enabled. XML-RPC reuses `ServerProxy`; JSON-2 opens a new `urllib` connection per call.
4. **Multi-instance fan-out: shared or isolated state?** Mixed, and deliberately so. **Isolated per instance**: Odoo clients (lazily created, lock-guarded, cached by name); credentials and transport (never fall back to env); schema caches (keyed `{instance}:{model}`); approval tokens (instance in the hashed payload); rate-limit counters (keyed `instance:tool`); field-ACL rules (top-level key is the instance). **Shared across instances**: the single `AppContext` and its one `write_approvals` dict, the process-wide field-policy object, the process-wide rate tracker object (keys are partitioned, the object is not), the audit file, the N+1 event map (keys partitioned), and the `ThreadPoolExecutor` used for fan-out (`ODOO_MCP_CROSS_INSTANCE_WORKERS`). Fan-out itself is **read-only by design** ("no warehouse, no data sync", `cross_instance.py:9`), per-instance-failure-tolerant (each worker's exception is caught and reported per instance rather than failing the whole query), opt-out per instance via a `cross_instance` flag defaulting to `True`, and applies field ACL and rate limits **inside each worker**, per target instance.

### Gaps in this investigation

- **GitHub issues/PRs/Discussions were not read** (the GitHub MCP server failed to connect this session; only `gh api` repo metadata was available). Rationale beyond code comments, docs, and CHANGELOG — e.g. the discussion behind the session-binding wording, or whether the `execute_method` ACL bypass is a known issue — is unverified. 7 issues were open at the time of cloning.
- **Nothing was executed.** No test run, no smoke harness, no live Odoo. All claims are static reads of the source. The 891 test-function count is a grep of `def test_`, not a pytest collection.
- **`docs/comparison.md`, `docs/benchmarks.md`, and `docs/performance.md` were not read** — their marketing-comparison and performance claims are unverified here.
- **The hosted ERPipe product (43 tools, HITL inbox, workspace OAuth) is closed-source** and outside this repo; the README's comparison table is the only evidence of its behavior and could not be checked against code.
