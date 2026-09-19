# ivnvxd/mcp-server-odoo — architecture, flow, safety logic

> Evidence base: repo cloned read-only at commit `4c28709` (2026-08-26, tag `v0.8.0`) into
> `C:\Users\ADMIN\AppData\Local\Temp\claude\d--Youdoo\b419e890-.../scratchpad/repos/ivnvxd-mcp-server-odoo`.
> All paths below are repo-relative to that clone. Line numbers are from that commit.
> Current as of 2026-09-19.

## 1. Repo facts / activity signals

### Takeaway
Python 3.10+, official MCP SDK's `FastMCP` (`mcp.server.fastmcp`), ~11.2k LOC of source vs ~26k LOC of tests (1195 test functions), MPL-2.0, actively maintained through 2026-08-26 with 20 release tags. The **companion Odoo addon `mcp_server` is NOT in this repo and is NOT open source** — it is a proprietary (OPL-1) paid app by "much. Consulting", sourced in CI from the private repo `much-GmbH/much-mcp-server@19.0`.

### Cited Findings
- Language/framework: `from mcp.server import FastMCP` — [mcp_server_odoo/server.py:11](mcp_server_odoo/server.py). Dependency floor `"mcp>=1.27.0,<2"` with an inline rationale comment — [pyproject.toml].
- LOC (src): `tools.py 2909`, `resources.py 1651`, `odoo_connection.py 1342`, `access_control.py 688`, `error_sanitizer.py 628`, `formatters.py 616`, `performance.py 551`, `server.py 552`, `uri_schema.py 376`, `config.py 358`, `logging_config.py 341`, `schemas.py 324`, `error_handling.py 303`, `user_context.py 202`, `field_security.py 171`, `__main__.py 147`, `__init__.py 23` = **11,182 total**.
- Tests: 26,018 LOC across 40 test files, **1195 `def test_` functions**; `tests/helpers/` has a real MCP test client, a flaky proxy, and a model-discovery helper.
- License: `license = { text = "MPL-2.0" }`, `Development Status :: 3 - Alpha` — [pyproject.toml]. Version `0.8.0`.
- Activity: last commit `2026-08-26 19:32`, 20 tags, cadence v0.1.0 (2025-06-08) → v0.8.0 (2026-08-26); tag dates 2026-08-26 (0.8.0), 2026-06-12, 2026-06-11, 2026-05-02, 2026-04-30, 2026-04-23.
- GitHub: **388 stars, 179 forks, 10 watchers, 6 open issues**, 231 commits — [GitHub repo page](https://github.com/ivnvxd/mcp-server-odoo).
- CI: `.github/workflows/{ci.yml,docker.yml,publish.yml}`. `ci.yml` has 4 jobs: `lint` (ruff format+lint, `ty` type-check), `test` (unit matrix), `yolo-integration-test` (real `odoo:19`, vanilla XML-RPC), `mcp-integration-test` (real Odoo 19 **plus the private module**).
- Companion addon is proprietary: CI checks out `repository: much-GmbH/much-mcp-server`, `ref: '19.0'`, `token: ${{ secrets.MCP_MODULE_PAT }}` — [.github/workflows/ci.yml:240-246]. CHANGELOG notes the switch: *"the MCP job now sources the module from `much-GmbH/much-mcp-server@19.0` (was `ivnvxd/odoo-apps@18.0`)"* — [CHANGELOG.md:75]. Both GitHub repos return "Repository not found" to an anonymous clone (verified).
- Addon store listing: author "much. Consulting", **license OPL-1** ("The Software may only be used if you have purchased a valid license"), technical name `mcp_server`, version 19.0.2.1.0, supports Odoo 16.0–19.0, 6627 LOC, Python deps `authlib>=1.6.12,<1.7.0` / `defusedxml` / `packaging` — [apps.odoo.com/apps/modules/19.0/mcp_server](https://apps.odoo.com/apps/modules/19.0/mcp_server).

### Inferences
- The test-to-source ratio (2.3:1) and the density of *rationale comments* (nearly every non-obvious branch carries a paragraph explaining the failure it prevents, often citing an issue number) put this repo well above typical MCP-server quality.
- The external server is the **open-source client of a commercial product**. Any "security model" claim that depends on the addon cannot be audited from open source.

### Gaps
- The addon's source code could not be read (private repo + paid OPL-1). All addon claims below come from the client's consumption of its HTTP contract, the CI setup script, and the store listing.

---

## 2. Architecture: modules, entry point, registration, dependency direction

### Takeaway
A flat 4-layer package: **entry (`__main__`) → config → server orchestrator → {connection, access_control} → {tools, resources}**, with `formatters`/`field_security`/`error_sanitizer`/`schemas` as leaf utilities shared by both handler surfaces. Tools and resources are registered *after* the Odoo connection authenticates, inside the FastMCP lifespan, via `register_tools(app, connection, access_controller, config)` closures.

### Cited Findings
- Stated pipeline: `__main__.py → OdooConfig → OdooMCPServer → OdooConnection → FastMCP` plus a per-module responsibility table — [CONTRIBUTING.md:136-155].
- Entry point: `mcp-server-odoo = "mcp_server_odoo.__main__:main"` (pyproject `[project.scripts]`); `main()` parses `--transport/--host/--port`, writes them back into `os.environ`, calls `load_config()`, builds `OdooMCPServer(config)`, then `asyncio.run(server.run_stdio())` or `run_http()` — [mcp_server_odoo/__main__.py:99-123].
- Deliberate CLI/env layering: *"CLI flags default to None sentinels: load_config() resolves the actual values from the environment AND the .env file. Eagerly baking env values into argparse defaults ... would mask .env settings, because load_dotenv() never overrides variables already present"* — [__main__.py:74-78].
- Registration happens inside the FastMCP lifespan, after connect+auth: `_odoo_lifespan` → `await asyncio.to_thread(self._ensure_connection)` → `self._register_resources()` → `self._register_tools()` — [server.py:159-169].
- Registration is **idempotent by handler-instance sentinel** because streamable-http re-enters the lifespan per session: `if self.resource_handler is not None: ... return` — [server.py:281-308].
- Tools are plain async closures over `self`, declared with `@self.app.tool(title=..., annotations=ToolAnnotations(...))` inside `OdooToolHandler._register_tools()` — [tools.py:884-1370]. Resources use `@self.app.resource("odoo://{model}/record/{record_id}", ...)` — [resources.py:233-345].
- Dependency direction is strictly downward: `tools.py` imports from `access_control`, `config`, `error_handling`, `error_sanitizer`, `field_security`, `formatters`, `logging_config`, `odoo_connection`, `schemas`, `uri_schema`, `user_context` — [tools.py:20-66] — and nothing imports `tools`/`resources` except `server.py`.
- Odoo I/O is synchronous XML-RPC; every call from an async handler is offloaded: `await asyncio.to_thread(self.connection.search, ...)` — [tools.py:1441]. Same for the permission check: `await asyncio.to_thread(self.access_controller.validate_model_access, model, "read")` — [tools.py:1381].

### Inferences
- The "handler object holds the connection reference" design forces the in-place reconnect hack in `_ensure_connection` (*"Reconnect the existing object IN PLACE: registered tool and resource handlers hold references to this connection, so it must never be replaced"* — [server.py:188-190]). A registry/provider indirection would have avoided it.

---

## 3. Odoo connection layer

### Takeaway
100% XML-RPC for data, plus **plain HTTP/JSON to the addon's REST endpoints** for auth-validation and permissions. The single most important architectural fact: in **standard mode the object proxy points at the addon's own route `/mcp/xmlrpc/object`**, not Odoo's `/xmlrpc/2/object` — so the addon is in the data path, not merely consulted.

### Cited Findings
- Endpoint switch by mode:
  ```python
  if self.is_yolo_enabled:
      return {"db": "/xmlrpc/db", "common": "/xmlrpc/2/common", "object": "/xmlrpc/2/object"}
  else:
      return {"db": "/xmlrpc/db", "common": "/mcp/xmlrpc/common", "object": "/mcp/xmlrpc/object"}
  ```
  — [config.py:155-174]. The DB endpoint stays server-wide *"so that database listing works even when multiple databases exist (MCP addon routes require a DB context that isn't available yet)"*.
- Auth strategies — [odoo_connection.py:674-900]:
  - **Standard mode + API key** → HTTP GET `/mcp/auth/validate` with `X-API-Key` header; uid comes from `data.data.user_id` ([:735-750]).
  - **YOLO + API key** → `common.authenticate(db, username, api_key, {})` — the key is used *as the password* ([:686-690]); this is why `ODOO_USER` is required in YOLO even with a key.
  - **Password** → `common.authenticate(db, username, password, {})` ([:812-815]).
  - Fallback chain: API key first, then username/password, with a warning that *"permission checks will use session authentication for this run"* ([:872-877]).
- uid/session caching: `self._uid`, `self._database`, `self._auth_method`, `self._authenticated` are instance state; `AccessController` keeps a separate Odoo **web session cookie** obtained from `/web/session/authenticate` when no API key is usable ([access_control.py:172-215]), single-flighted under `self._session_lock` and retried once on 401 ([:296-305]).
- Connection reuse: `ConnectionPool` is *"Despite the name this is a factory, not a pool: proxies are created..."* — [performance.py:343-353]; three long-lived `xmlrpc.client.ServerProxy` objects (db/common/object), each guarded by its own `threading.Lock` because *"ServerProxy/Transport are not thread-safe, and tool handlers offload calls to worker threads via asyncio.to_thread"* — [odoo_connection.py:214-218].
- Retry: a custom `Transport.request` replacement, `_retry_once_request`, adds recovery from **half-open keepalive sockets** (issue #68). Crucially it is gated on write-safety: *"only read-only methods may be re-sent — a timed-out write could already be committing server-side and re-sending it would double-execute it"*; `execute_kw` sets `transport.timeout_retry_safe = method in _TIMEOUT_RETRY_SAFE_METHODS` under the same lock as the request — [performance.py:239-292], [odoo_connection.py:1012-1017].
- Fault → MCP error mapping, code-first:
  ```python
  #   2 = RPC_FAULT_CODE_WARNING          -> UserError / ValidationError
  #   4 = RPC_FAULT_CODE_ACCESS_ERROR     -> AccessError (record rules / ACLs)
  _ODOO_BUSINESS_FAULT_CODES = frozenset({2, 4})
  ```
  business faults become `OdooValidationFault` (surfaced verbatim), everything else becomes `OdooConnectionError("Operation failed: ...")` — [odoo_connection.py:113-155].
- **Self-documented gap**: *"Standard mode goes through the MCP module's own proxy, which re-wraps every exception as faultCode 500 with an 'Internal Server Error in MCPObjectController: <message>' envelope ... business errors keep reading as connection failures in standard mode until the module preserves Odoo's own fault codes."* — [odoo_connection.py:124-131]. So the nicest error handling in the repo only works in YOLO mode.
- Locale injection: `kwargs["context"].setdefault("lang", self.config.locale)` on every `execute_kw`, with a self-healing retry that drops an invalid lang and (only if it was the *configured* one) disables it process-wide — [odoo_connection.py:997-1046].
- Odoo returning void faults on `allow_none=False` is swallowed on purpose: `if "cannot marshal None unless allow_none" in e.faultString: return None` — *"the method already ran"* — [odoo_connection.py:1050-1053].

### Inferences
- Because the standard-mode object proxy is an addon route, an attacker who controls the MCP client cannot bypass the addon's model allowlist by crafting XML-RPC: the addon re-checks. That is the decisive difference from a design that only *reads* a config. (See §6.)

---

## 4. Tool design

### Takeaway
**Generic CRUD, not domain-specific**: 11 tools always registered + 1 behind a two-key opt-in. Input schemas are derived from Python type hints by FastMCP; outputs are **Pydantic structured results** (`schemas.py`) for tools and **hierarchical plain text** (`formatters.py`) for resources. Smart field selection is a hand-tuned additive scoring function capped at 15 fields.

### Cited Findings — tool inventory (all in tools.py:884-1370)
| Tool | One line |
|---|---|
| `search_records` | Domain search on any model; smart/explicit/`__all__` fields, limit/offset/order. |
| `get_record` | One record by id, with field-selection metadata and `related_summaries`. |
| `get_fields` | `fields_get` wrapper with a **curated** attribute set by default. |
| `get_current_context` | Connected user, timezone, active + allowed companies, UTC guidance. |
| `list_models` | Models enabled for MCP access with allowed operations. |
| `list_resource_templates` | Enumerate the `odoo://` URI templates (templates don't show in `resources/list`). |
| `create_record` | `create` on any enabled model. |
| `update_record` | `write` on one record id. |
| `delete_record` | `unlink` on one record id. |
| `post_message` | `message_post` to a record's chatter (note/comment, HTML, partners, attachments). |
| `aggregate_records` | Server-side `formatted_read_group` (19+) / `read_group` (older), normalized. |
| `call_model_method` | **Opt-in only**: raw `execute_kw` escape hatch for business methods. |

- Tool annotations are set honestly per tool: reads carry `readOnlyHint=True, idempotentHint=True`; `delete_record` and `call_model_method` carry `destructiveHint=True` — [tools.py:887-894, 1146-1153, 1313-1320].
- Input-schema style: plain typed parameters, but deliberately permissive for LLM sloppiness — `domain: Optional[Any]` and `fields: Optional[Any]` accept a list, a JSON string, or a Python-literal string, with `json.loads` → `ast.literal_eval` fallback — [tools.py:1405-1428]. `[]` is normalized to "smart defaults" because *"Odoo would interpret [] as ALL fields"* — [tools.py:1463-1466].
- Output for tools: Pydantic models (`SearchResult`, `RecordResult`, `CreateResult`, …) declared in `schemas.py` and returned directly, so clients get `structuredContent`.
- Output for resources ("hierarchical text formatting"): `RecordFormatter.format_record` emits
  ```
  ==================================================
  Record: res.partner/42
  Name: Acme Corp
  ==================================================
  Fields:
    email: ...
  Relationships:
    child_ids: ...
  ```
  with `OMIT_FIELDS` dropping `write_date/create_uid/message_*`, per-field truncation at `MAX_FIELD_DISPLAY_LENGTH = 2000`, and x2many previews capped at `MAX_RELATED_ITEMS = 5` — [formatters.py:28-160].

### Cited Findings — smart field scoring (`_score_field_importance`, tools.py:454-570)
Additive score, top-N by `ODOO_MCP_MAX_SMART_FIELDS` (default 15), with essentials force-appended afterwards:
- **Tier 1 / always**: `{"id","name","display_name","active"}` → `return 1000`.
- **Hard zero (excluded)**: prefixes `("_","message_","activity_","website_message_")`; exact names `{write_date, create_date, write_uid, create_uid, __last_update, access_token, access_warning, access_url}`; **anything `is_sensitive_field_name()` matches**; field types `binary`/`image`/`html`; and **all `one2many`/`many2many`**.
- **Bonuses**: `required` +500; type score (`char` 200, `boolean` 180, `selection` 170, `integer/float` 160, `date/datetime` 150, `monetary` 140, `many2one` 120, `text` 80, default 50); `store` +80; `searchable` +40; business-name pattern match (`state, status, stage, priority, company, currency, amount, total, date, user, partner, email, phone, address, street, city, country, code, ref, number`) +60.
- **Deprioritized, not excluded**: non-stored fields are capped at 30 — *"reading them triggers per-row compute. Note fields_get() never returns a `compute` key, so gate on `store`"*; **related fields are exempt** from the cap (*"they resolve via cheap joins — incl. `_inherits` delegation, e.g. most business fields on product.product ... Deliberate divergence from the reference in-process implementation"*) — [tools.py:552-563]. The CHANGELOG records that the earlier version gated on a `compute` key that never exists — a real bug fixed in 0.8.0.

### Cited Findings — credential-field withholding
- The detector lives in a dedicated 171-line module whose docstring states the scope precisely: *"Best-effort, name-only defense-in-depth for the **bulk** read paths ... Explicitly-named fields are always honored — Odoo field-level `groups=` is the real ACL, not this heuristic."* — [field_security.py:1-7].
- Matching rule (not a simple suffix list): split on `_`; return False if last segment is `id`/`ids` or first is `is`/`has`/`can`; pop trailing all-digit and empty segments; pop one representation suffix from `("hash","value","digest")`; then match the final segment against `SENSITIVE_FIELD_MARKERS` = `password, passwd, pass, secret, apikey, privatekey, secretkey, accesskey, token, rtoken, passkey, salt, otp, pin, hashkey, hashiv`, **or** match the trailing 2-segment compounds `SENSITIVE_MARKER_SEQUENCES` = `(api|private|secret|access|hmac|signature|transaction|hash|encryption|signing) + key` — [field_security.py:36-138].
- The comments record **empirical validation**: the extra markers were *"Scanned against 2475 distinct field names on a stock Odoo 19 database: `pin` was the only match and it is a real credential"*; and `hashkey/hashiv` came from *"scanning every `x = fields.Y(` definition in Odoo 19 core + enterprise (14708 distinct names)"*. A known false positive is documented and accepted: `purchase.report.delay_pass` ("Days to Receive").
- **Where enforced — three call sites, all bulk-only:**
  1. `search_records`: only inside `if fields_to_fetch is None:` (i.e. `__all__` or smart-selection failure) — [tools.py:1497-1510].
  2. `get_record`: same guard, `if fields_to_fetch is None: withheld_fields = strip_sensitive_fields(record)` — [tools.py:1619-1624].
  3. Resources: `_get_safe_fields()` removes them from the field list *before* the read (`field_name not in withheld_set`), returning `(safe_fields, withheld)` — [resources.py:1209-1261].
- Withholding is **advertised, not silent**: `withheld_note()` produces *"Credential-like field(s) withheld: X, Y — request explicitly by name to include"*, merged into `SearchResult.note` / `RecordResult.metadata.note` — [field_security.py:141-155], [tools.py:226-233, 1670-1687].
- The same detector also redacts write-payload logging: `_is_sensitive_log_key` / `_redact_values` in [odoo_connection.py:38-75], used by the DEBUG log line in `execute_kw` (*"write payloads can carry passwords/PII that must not land in log files"*).
- Pagination: `limit` defaults to `ODOO_MCP_DEFAULT_LIMIT` (10) and is clamped to `ODOO_MCP_MAX_LIMIT` (100); `_validate_offset` refuses negatives and caps depth at `max_offset_for(limit)` (1000 pages, floor 10 000) because *"Postgres walks (and discards) every skipped row, so an unbounded offset is query-cost amplification even with a capped limit"* — [tools.py:305-320]. `search_records` **always** issues a separate `search_count` rather than inferring totals, with a measured justification (mail.message post-filters in Python after the SQL limit: *"a limit=10 search returns 5 rows while 85 match ... verified: 86 == len(unlimited search)"*) — [tools.py:1449-1460].

### Inferences
- The tool surface is a thin, honest ORM projection. It therefore needs zero per-domain maintenance, but it also gives the LLM no business semantics — every question becomes "pick a model, write a domain".
- The credential denylist is explicitly a *context-hygiene* measure, not an access control: it stops accidental leakage into LLM context on wide reads and does nothing against a deliberate request.

---

## 5. Write-path flow, step by step

### Takeaway
Every write runs the **same 5-gate pre-flight** and then delegates to `execute_kw`. There is **no human-in-the-loop confirmation, no dry-run, no `fields_get` validation of the payload, and no diff/preview** anywhere in the server.

### Cited Findings — `create_record` trace ([tools.py:2120-2196])
1. `perf_logger.track_operation("tool_create_record", model=model)` opens the timing span.
2. `await asyncio.to_thread(self.access_controller.validate_model_access, model, "create")` — the permission gate (HTTP to `/mcp/models/{model}/access`, or a YOLO short-circuit).
3. `self._ctx_info(ctx, f"Creating record in {model}...")` — MCP log notification to the client.
4. `if not self.connection.is_authenticated: raise ValidationError`.
5. `if not values: raise ValidationError("No values provided")`.
6. `_check_xmlrpc_int_bounds(values, "values")` — recursive walk rejecting ints outside signed-32-bit *"incl. nested x2many command tuples ... fail cleanly before any RPC"*.
7. **Attachment gate**: `if model == "ir.attachment": await self._gate_attachment_target(values.get("res_model"), "attachment would be attached to")` — *"Planting a document on a model left out of the allowlist is the write-side of the same sidestep the read gate closes."*
8. `record_id = await asyncio.to_thread(self.connection.create, model, values)` → `execute_kw(model, "create", [values], {})` → commit.
9. Read-back of `["id","display_name"]` only, then `build_record_url`, returning `{success, record, url, message}`.

- `update_record` adds `_validate_record_id(record_id)` first, uses `"write"`, gates **both** the current attachment owner and any new `res_model` (*"Gating the CURRENT owner stops the escalation: repoint an excluded model's attachment at an allowed one and the read gate would then wave it through"* — [tools.py:2240-2249]), does an existence probe (`read [record_id] ["id"]`), then `write`, then read-back — [tools.py:2198-2285].
- `delete_record` uses `"unlink"`, gates `ir.attachment` rows, reads `["id","display_name"]` first so the confirmation message can name the record, then `unlink` — [tools.py:2290-2350].
- `post_message` is a write too and goes through the same `validate_model_access` + attachment gating for `attachment_ids`.
- **Error funnel** (identical on all four): `ValidationError` passthrough → `MCPPermissionError` → `AccessControlUnavailableError` ("Could not verify access (connection error)" = retryable) → `AccessControlError` (`access_denied_message`) → `OdooValidationFault` (verbatim business message) → `OdooConnectionError` → generic `Exception` sanitized via `ErrorSanitizer.sanitize_message`.

### Cited Findings — YOLO semantics
- Three-valued, validated at config load: `ODOO_YOLO ∈ {off, read, true}` — [config.py:73-78]. `is_yolo_enabled = yolo_mode != "off"`, `is_write_allowed = yolo_mode == "true"` — [config.py:145-153].
- In `AccessController.__init__`, YOLO **returns before any API-key validation**, logging `"🚨 YOLO mode (...): Access control bypassed! All models accessible, MCP security disabled."` — [access_control.py:151-159].
- `get_enabled_models()` returns `[]` in YOLO, and `[]` is the sentinel meaning *all models allowed* — [access_control.py:370-373]; callers must know this ([server.py:544-548] falls back to querying `ir.model` directly, capped at 200 for autocomplete).
- `check_operation_allowed` in YOLO: an explicit read-op set `{read, search, search_read, fields_get, count, search_count}` is always allowed; anything else is allowed only when `yolo_mode == "true"`, else refused with *"Write operation '...' not allowed in read-only YOLO mode"* — [access_control.py:471-500].
- `call_model_method` is a **two-key opt-in and is not even registered** otherwise: `if self.config.is_write_allowed and self.config.enable_method_calls:` — [tools.py:1311-1313]; a mismatched config logs a warning so the silent non-registration is debuggable — [config.py:127-133].

### Cited Findings — what `call_model_method` blocks outright ([tools.py:72-145, 247-278])
- Method name must match `^[A-Za-z][A-Za-z0-9_]*$` (`fullmatch`) — no dotted, dashed, whitespace, non-ASCII or `_`-prefixed names.
- **Model prefixes**: `ir.actions*`, `ir.cron` — *"ir.actions.server.run() executes server-action code as superuser and ir.cron.method_direct_trigger runs a cron job as its (often privileged) owner"*. Deliberately narrow: *"Scoped to these prefixes on purpose — other ir.* models (ir.attachment, ...) stay callable; no blanket ir.% block."*
- **Method family**: anything starting `web_`.
- **ORM primitives** (`_BLOCKED_METHOD_CALLS`, 30+ names): `create, write, unlink, read, search*, fetch, read_group, formatted_read_group, name_search, copy, browse, _write, sudo, with_user, with_env, with_context, fields_get, default_get, exists, load, export_data, name_create` plus the alias set added in 0.8.0 — `copy_data, copy_multi, update, get_view, get_views` (with a comment explaining each alias: *"update is write (15-18; @api.private only on 19)"*).
- **Universal privileged names** (`_BLOCKED_PRIVILEGED_METHOD_NAMES = {"run", "method_direct_trigger"}`) blocked on *every* model as defense-in-depth: *"other models commonly proxy or delegate to them ... Refusing a legitimately named run() on an unrelated model is an accepted cost."*
- Result truncation at `MAX_METHOD_RESULT_ITEMS = 100`.
- Audit line logs **what, not values**: `"call_model_method invoked: model=%s method=%s args_len=%d kwargs_keys=%s"` — *"Audit only what was called, not the values — kwargs may carry PII."*
- The denylist is honestly labelled a remote approximation: *"In-process introspection (mapped-operation gating, a hasattr(BaseModel, ...) check) cannot be replicated over XML-RPC, so this denylist is the remote approximation."*

### Inferences
- The write path's entire safety budget is spent on (a) the addon's per-model permission bits and (b) Odoo's own ACLs/record rules as the authenticated user. There is no server-side notion of "this write is unusual / large / needs review".
- `call_model_method` being gated on full YOLO means **the escape hatch is unavailable in exactly the deployment (standard mode) where the permission model is strongest** — a strange coupling: the flag is `enable_method_calls`, but its precondition is `yolo_mode == "true"`, i.e. "no access control at all".

---

## 6. Permission/security model — the key question

### Takeaway
**Both.** The external process reads the addon's config over REST *and* enforces it locally — but in standard mode the actual data RPC also travels through the addon's own controller `/mcp/xmlrpc/object`, so a modified client that skipped the local check would still be refused **server-side by the addon**. The local check is a fast, cacheable, better-error-message front line; it is not the only line. In YOLO mode there is no addon at all and the local check is the *only* line — and it is trivially removable since it lives in the client process.

### Cited Findings
- **Local enforcement**: `AccessController.validate_model_access(model, op)` → `check_operation_allowed` → `get_model_permissions(model)` → HTTP GET `/mcp/models/{model}/access`, parsing `data.operations.{read,write,create,unlink}` into a `ModelPermissions` dataclass — [access_control.py:411-470]. Results cached in-process with `CACHE_TTL = 300` seconds behind a `threading.Lock` — [access_control.py:114-116, 337-353].
- **Server-side enforcement**: standard mode's object proxy is `/mcp/xmlrpc/object` — [config.py:170-173] — and the client's own comments confirm the addon re-checks: *"the read goes through the MCP module's XML-RPC proxy, which refuses any model the administrator has not enabled"* — [user_context.py:28-31]; the module's refusal text `"Model 'x' is not enabled for MCP access."` is surfaced verbatim from a 403 body — [access_control.py:56-73, 305-310].
- **Addon store listing corroborates** server-side enforcement: `/mcp/xmlrpc/object` is described as "model operations **with MCP access control**", "Every call runs as a real Odoo user" with native ACLs and record rules, requires membership in the `MCP User`/`MCP Administrator` groups, and removing the group "cuts off the user's outstanding API keys and OAuth tokens immediately" — [apps.odoo.com listing](https://apps.odoo.com/apps/modules/19.0/mcp_server).
- **What the addon stores** (from the CI configuration script and the listing): `ir.config_parameter` keys `mcp_server.enabled`, `mcp_server.use_api_keys`, `mcp_server.enable_rate_limiting`; and a model `mcp.enabled.model` with `model_id` + booleans `allow_read / allow_create / allow_write / allow_unlink` — [.github/workflows/ci.yml:320-350]. The listing adds OAuth 2.1 clients/tokens, per-user API keys ("MCP only" vs all-APIs scope), custom server-action-backed tools, **rate limiting (~300 req/min default)**, and **audit logs with 30-day default retention**.
- **Fail-closed on infrastructure failure**: a dedicated exception exists for exactly this distinction — *"Permission could not be EVALUATED (infrastructure failure) ... Callers should surface these as connection errors (retryable), never as access denials. Still fails closed — operations do not proceed."* — [access_control.py:29-38]. Every handler catches `AccessControlUnavailableError` *before* its base class and rewrites it to "Could not verify access (connection error)".
- **Without the addon**: standard mode simply cannot work — `/mcp/auth/validate` 404s → auth fails → startup raises; the user must switch to YOLO. `check_health` and the README point at `https://your-odoo.com/mcp/health` as the installation probe.
- **Per-user API keys**: the key is an Odoo user API key; `/mcp/auth/validate` returns the `user_id` and everything then runs as that user. The README: *"Each API key is linked to a specific user with their permissions"*. There is **no per-key scoping inside the external server** — one process = one identity.
- **"No client auth on streamable-http"** is acknowledged in code, not just docs: `_warn_if_exposed()` logs *"HTTP transport binding to '<host>' — this transport has NO built-in authentication. Anyone who can reach this port gets Odoo access with the server's stored credentials..."*, and appends *"YOLO FULL-ACCESS MODE IS ENABLED: unauthenticated clients could read, write and delete ANY record"* + "and call arbitrary model methods" when those flags are on — [server.py:475-505]. The README repeats it twice with ⚠️.
- **DNS-rebinding protection has a sharp edge, documented**: `_build_transport_security` returns `None` when `ODOO_MCP_ALLOWED_HOSTS` is unset, and *"the SDK auto-enables protection ONLY when the bind host is loopback ... for any other bind — notably `0.0.0.0`, the usual Docker setting — it leaves protection DISABLED and no Host/Origin validation runs at all"* — [server.py:424-443]. The IPv6/port-less parsing bugs in that allowlist were fixed in 0.8.0.
- **Input sanitization** (defense in depth, all pre-RPC):
  - Domain **balance** check — `check_domain_balance` rejects `["|", ("id",">",0)]` because *"the trailing '|' would otherwise take the appended scope as its second operand, ORing the allowlist away instead of ANDing it in"* — [access_control.py:575-608]. This exists specifically to protect the attachment-scope concatenation.
  - Nesting-depth cap `_MAX_PARAM_NESTING = 32`, counted **quote-aware** by hand rather than by letting the parser fail: *"CPython 3.12 raised the JSON scanner's recursion ceiling ... made the same request an 'invalid parameter' on one interpreter and a stack-exhausting success on another"* — [tools.py:162-212].
  - JSON payload cap `_MAX_JSON_PARAM_BYTES = 1_000_000`.
  - 32-bit int range checks on record ids, domains, `values`, and `call_model_method` args.
  - **Prompt-injection hardening of the instructions block**: user-editable Odoo values (display name, login, company name) are passed through `_one_line()`, which maps CR/LF **and** U+0085/U+2028/U+2029/VT/FF/FS/GS/RS to spaces — *"stops a crafted value from forging extra context lines (prompt injection into the caller's own session)"* — [user_context.py:92-113].
  - The `ir.attachment` allowlist domain (`attachment_scope_domain`, [access_control.py:611-688]) scopes attachment rows to `res_model`s the caller may **read** (not merely "enabled"), because a row carries `url` and `index_content` (extracted document text); fails closed to `[("res_model","=",False)]`.

### Inferences
- **Answer to the key question**: in standard mode, enforcement is genuinely server-side (the addon owns the RPC endpoint); the external process's check is an optimization plus a better error surface. A modified client can bypass *the client-side check* but not the addon. In YOLO mode there is no server-side enforcement whatsoever — YOLO's honesty is that it says so loudly in every log line and in the README.
- The strongest parts of this security model are **not portable without buying the addon**. What *is* portable is the exception taxonomy (`Unavailable` ≠ `Denied`, both fail closed) and the "gate metadata, not just payloads" attachment reasoning.

---

## 7. Audit / logging / observability

### Takeaway
Structured logging with request ids, a slow-operation threshold, and an aggressive error sanitizer — but **no audit trail of its own**: the server logs, the addon audits.

### Cited Findings
- `logging_config.py`: `StructuredFormatter` (JSON via `ODOO_MCP_LOG_JSON`), `RequestLoggingAdapter` (generated request ids), `PerformanceLogger.track_operation` which warns when `duration_ms > slow_operation_threshold_ms` (`ODOO_MCP_SLOW_OPERATION_THRESHOLD_MS`, default 1000), rotating file handler via `ODOO_MCP_LOG_FILE` (10 MB × 5).
- Every tool handler opens `with perf_logger.track_operation("tool_<name>", model=model)`.
- `error_sanitizer.py` (628 lines) strips: tracebacks and `File "...", line N` frames, absolute `.py` paths, `odoo.<module>:` and `mcp_server_odoo.<module>:` prefixes, `<class '...'>`, memory addresses, `psycopg2.*`, Postgres `DETAIL: Key (...)=(...)` / `Failing row contains` / constraint and index names, and — added in 0.8.0 — **deployment topology**: any `scheme://...` → `<url>`, `IPv4:port` → `<host>`, `host.tld:port` → `<host>`, bracketed IPv6 authorities. Rationale: *"a connection/DNS failure quotes the endpoint it tried, so internal hostnames, private IPs and non-default ports ride out to the client."*
- A 0.8.0 fix runs the other way — over-sanitizing was also a bug: *"the sanitizer rewrote any message merely containing 'access denied' to a bare 'Permission denied for this operation', so the module's actionable wording ... never reached the caller; only a bare refusal maps to the generic text now"* — [CHANGELOG.md:65].
- MCP-level observability: handlers emit `ctx.info()` / `ctx.warning()` progress lines ("Searching res.partner…", "Found 86 records"); a `/health` custom Starlette route returns `{status, version, connection.connected}` — [server.py:123-127, 521-535]; a `@self.app.completion()` handler autocompletes the `model` argument from the enabled-model list — [server.py:129-141].
- Audit proper is the addon's: "Audit logs — all calls, denials, authentication attempts with configurable retention (default 30 days)" — [apps.odoo.com listing]. Nothing in this repo writes an audit record, and there is no hash chain or tamper-evidence anywhere in the source.

---

## 8. Testing strategy

### Takeaway
Three layers: pure-unit with mocks (runs offline), `@pytest.mark.yolo` against a **real vanilla Odoo 19**, and `@pytest.mark.mcp` against a **real Odoo 19 with the proprietary module installed**. Service probes are lazy and memoized so unit runs never touch the network.

### Cited Findings
- Markers declared in `pyproject.toml`: `yolo: needs running Odoo instance (vanilla XML-RPC, no MCP module)`, `mcp: needs running Odoo with MCP module installed`; `asyncio_mode = "auto"`.
- `tests/conftest.py`: *"Probes are LAZY and memoized: unit-only runs must not touch the network. They are triggered from pytest_collection_modifyitems only when yolo/mcp tests were actually collected (and survive the -m filter)"* — [conftest.py:56-60]. `mcp_module_available()` probes `GET /mcp/health` with an `X-Odoo-Database` header (multi-DB instances can't route it otherwise) and skips with a readable reason instead of failing.
- CI `yolo-integration-test` boots `odoo:19` + `postgres:17` and generates a real API key; `mcp-integration-test` additionally builds a custom image installing the module's `external_dependencies` (`authlib`, `defusedxml`, `packaging`) because *"Odoo refuses to install the module if any are missing, and the stock odoo image ships none of them"*, then initializes `--init base,mcp_server`.
- The CI permission fixture is itself a **test matrix by design**: `res.partner` read+write+unlink but `create=False`, `res.company` full CRUD, `res.country` read-only, and `res.users` **deliberately not enabled** — "matching auth-test-matrix.md ... (res.users intentionally NOT enabled)" — [ci.yml:340-352]. Rate limiting is disabled in CI with an explicit note that *"the suite hits the addon's ~300/min ceiling because all tests run under the single admin API key ... production deployments leave it on (default True)"*.
- Unit-level Odoo mocking is via `unittest.mock` on `OdooConnection`; there are also purpose-built helpers: `tests/helpers/mcp_test_client.py`, `transport_client.py`, `flaky_proxy.py` (for the keepalive-recovery test), `tests/docker/test-lb/{compose.yml,nginx.conf}` (a load balancer to reproduce issue #68), and `tests/mcp_client_validation.sh`.
- Coverage is uploaded per job (`coverage-unit`, `coverage-yolo`) with a codecov badge.

### Inferences
- The `test_e2e_yolo.py` / `test_keepalive_recovery_e2e.py` / nginx-LB fixtures show a project that reproduces infrastructure failures rather than asserting around them — the half-open-socket retry would be untestable otherwise.

---

## 9. Extensibility: adding a new tool

### Takeaway
Four concrete edits, no plugin system, no registry — tools are hand-written closures in one 2909-line file.

### Steps (derived from the existing pattern)
1. **Add a Pydantic result model** in `mcp_server_odoo/schemas.py` (e.g. `class MyResult(BaseModel)`), mirroring `CreateResult`/`SearchResult`.
2. **Add the closure** inside `OdooToolHandler._register_tools()` in `tools.py`, decorated with `@self.app.tool(title=..., annotations=ToolAnnotations(readOnlyHint=..., destructiveHint=..., idempotentHint=..., openWorldHint=...))`; parameter types become the JSON schema, the docstring becomes the description (FastMCP convention, used consistently at [tools.py:887-1310]).
3. **Add the private handler** `async def _handle_my_tool(...)` that: opens `perf_logger.track_operation`, calls `await asyncio.to_thread(self.access_controller.validate_model_access, model, "<read|write|create|unlink>")`, checks `self.connection.is_authenticated`, validates inputs (`_validate_record_id`, `_check_xmlrpc_int_bounds`, `_validate_offset`), offloads Odoo I/O with `asyncio.to_thread`, and closes with the 7-clause `except` funnel (`ValidationError → MCPPermissionError → AccessControlUnavailableError → AccessControlError → OdooValidationFault → OdooConnectionError → Exception+sanitize`).
4. **Gate it if it is dangerous**: wrap registration in an `if self.config.<flag>:` like `call_model_method` at [tools.py:1311], and add the flag to `OdooConfig` + `load_config()` + the `__main__.py` epilog + README table.
5. **Tests**: a unit file in `tests/`, plus `@pytest.mark.yolo` / `@pytest.mark.mcp` integration cases if it touches a real server.

### Inferences
- The cost of a new tool is low, but `tools.py` at 2909 lines is at the limit of what one file should hold; nothing prevents a `tools/` package, it just hasn't been split.

---

## 10. MCP Resources (`odoo://…`)

### Takeaway
Six URI shapes registered as FastMCP **templates**, with a low-level `read_resource` override installed solely to serve **per-read dynamic mimeTypes** for binaries. Resources exist to do what tools structurally cannot: return raw bytes with a correct content type, and give the client a stable, quotable handle to a record.

### Cited Findings
- Templates — [resources.py:233-345]:
  - `odoo://{model}/record/{id}` (formatted hierarchical text)
  - `odoo://{model}/search` (first 10, summary fields only)
  - `odoo://{model}/count`
  - `odoo://{model}/fields`
  - `odoo://{model}/record/{id}/{field}` (binary/image field, `mime_type="application/octet-stream"` as the advertised fallback)
  - `odoo://attachment/{id}`
- Each carries MCP `Annotations(audience=["assistant"], priority=…)` — 0.5 for record/search, 0.4 for fields, 0.3 for count/binary.
- Parsing/validation is a separate module: `URI_PATTERN = ^odoo://([^/]+)/([^/?]+)(?:/(\d+))?(?:\?(.*))?$`, plus dedicated `BINARY_FIELD_URI_PATTERN` and `ATTACHMENT_URI_PATTERN = ^odoo://attachment/(\d+)$`, and a field-name whitelist `^[a-zA-Z][a-zA-Z0-9_]*$` — [uri_schema.py:84-99, 257].
- The dynamic-mimeType override: *"This template is advertised via resources/templates/list; actual reads are served by the low-level override below (dynamic mimeType). The function body is the fallback path (static octet-stream mimeType) for callers that bypass the override (e.g. ctx.read_resource)"* — [resources.py:311-345], `_install_binary_read_override` at [:359-416] patches `app._mcp_server.read_resource()` (private attr, no chaining).
- **Tools never return base64**: reads pass `{"bin_size": True}` and populated binary values are swapped for `odoo://` URIs via `_replace_binary_values` — [tools.py:1517-1521, 1629-1631]; README: *"Binary content is served exclusively via MCP resources: tool results carry URIs, never inline base64, so your MCP client must support `resources/read` to fetch it."*
- Size ceiling enforced **before** fetching: `ODOO_MCP_MAX_BINARY_SIZE` (50 MB) checked via a `bin_size` probe / the attachment's stored `file_size`, because *"the read decodes the payload and the MCP layer re-encodes it to base64, so peak memory runs ~2.3x the stored size — one oversized attachment can take the process down"* — [config.py:57-62], `_enforce_binary_limit` [resources.py:536-551].
- Attachment reads are double-gated: `_assert_attachment_model_allowed` / `_gate_attachment_row` check the attached-to `res_model`, not just `ir.attachment` — [resources.py:552-603].
- Documented limitation: *"No browse resource: FastMCP URI templates cannot carry query parameters — use the search resource or search_records tool."* — [resources.py:270-271]; README repeats it.
- Resources apply the same credential withholding as tools via `_get_safe_fields` (§4), so the surfaces cannot disagree.

### Inferences
- The resource layer is the *only* way this server moves bytes. The tool layer deliberately degraded (URIs instead of data) to protect the context window — a trade that only works if the client implements `resources/read`.

---

## 11. Notable design decisions and their stated rationale

### Cited Findings
- **Two modes, loudly separated.** YOLO exists so the server works against any stock Odoo ("Works with any Odoo instance!"), at the price of all access control; `_warn_if_exposed`, the `AccessController.__init__` banner, and the `OdooConnection.__init__` banner all shout it. CHANGELOG 0.4.0: *"YOLO Mode: Development mode for testing without MCP module installation."*
- **Fail-closed but distinguish "denied" from "could not verify".** [access_control.py:29-38] — a whole exception class exists for this, and `attachment_scope_domain` repeats the principle: *"Swallowing the error would silently disable the scope on every surface at once, which is the one outcome a security control must not have."*
- **Lifespan re-entry under streamable-http was a real bug (#70)** and the fix is documented in place: *"The low-level MCP server enters this context PER SESSION ... tearing down the authenticated Odoo connection there broke every call after the first (#70). The connection must persist across HTTP sessions; the OS reclaims it at process exit."* — [server.py:145-158].
- **Bind host and transport-security decision must not be separable** — `run_http()` dropped its host/port parameters in 0.8.0 because *"it reassigned `app.settings.host` after FastMCP had already chosen transport security from `config.host`, so an embedder could bind loopback with DNS-rebinding protection left off"* — [CHANGELOG.md:29], [server.py:365-376].
- **Session context injected at `initialize`, not per call.** *"Must run BEFORE the transport starts: the SDK freezes instructions when the transport calls `create_initialization_options()`, which happens before the lifespan ... is entered — hence the eager connect here"* — [server.py:310-338]. It rebuilds from a pristine `_static_instructions` captured in `__init__` so repeated calls don't compound the block, and assigns the private `app._mcp_server.instructions` because FastMCP exposes `instructions` read-only. `get_current_context` exists as the tool-shaped duplicate for clients that ignore `initialize.instructions`.
- **Context-unavailability explains itself.** When `res.users` isn't MCP-enabled (the common standard-mode case), the fallback text names the real server-side reason when one was given, and only guesses otherwise; "uninformative" reasons are matched by **equality, not containment**, so *"MCP access denied: user is not a member of the MCP User group"* still reaches the user — [user_context.py:32-89].
- **Always count, never infer.** See §4 (`mail.message` post-filtering measurement).
- **Odoo-version dispatch instead of a version floor**: `aggregate_records` uses `formatted_read_group` on 19+ and normalizes `read_group` below, refusing the specific pre-19 footguns (`id:` aggregates on 15/16, duplicate aggregates, groupby/aggregate collisions) rather than silently returning corrupted groups — [CHANGELOG.md 0.8.0 Fixed].
- **Empirically-derived heuristics.** The credential markers and the non-stored-field cap both cite measurements against a real Odoo 19 database (2475 field names; `sale.order.tax_totals` making a 10-row read 3.3× slower; six computed `res.partner` avatars 2.2×).
- Alpha status and a stated limitation: *"No Prompts: Guided workflows not available"*, *"Alpha Status: API may change before 1.0.0"* — [CHANGELOG.md:305-309].

---

## 12. Weaknesses / risks visible in the code

### Cited Findings
1. **Standard mode loses business-error fidelity.** Self-documented: the addon re-wraps everything as faultCode 500 / `MCPObjectController:` envelope, so *"business errors keep reading as connection failures in standard mode"* — [odoo_connection.py:124-131]. Users of the *recommended production* mode get the worse error experience.
2. **`0.0.0.0` bind = no Host/Origin validation at all** unless `ODOO_MCP_ALLOWED_HOSTS` is set — and `0.0.0.0` is exactly what the README's own Docker HTTP example passes (`--transport streamable-http --host 0.0.0.0`) without mentioning `ODOO_MCP_ALLOWED_HOSTS` in that snippet. The warning is a log line only; nothing refuses to start.
3. **No client authentication on streamable-http, period.** Acknowledged, mitigated only by documentation and a log warning. Combined with (2) and `ODOO_YOLO=true`, a single misconfiguration yields unauthenticated full CRUD on an ERP.
4. **The credential denylist is name-based and bypassable by design.** `fields=["my_password"]` returns the value. That is *intentional* ([field_security.py:1-7]) but a reader who trusts the README's "🔐 Secure access" framing could over-rely on it. False negatives are structural: a field named `credentials`, `bearer`, `client_id_secret_material`, or any non-English name is not caught; plurals are deliberately excluded.
5. **Permission cache TTL of 300 s** means a permission revoked in Odoo can remain effective in a long-lived MCP process for up to 5 minutes ([access_control.py:114]). There is no invalidation hook and `clear_cache()` is never called automatically.
6. **`is_model_enabled()` swallows errors into `False`** (`except AccessControlError: ... return False`) while `check_operation_allowed` carefully re-raises `AccessControlUnavailableError` — the two functions have inconsistent failure semantics; `filter_enabled_models` similarly returns `[]` on error — [access_control.py:401-410, 539-551].
7. **A rejected API key silently downgrades to password auth**, and permission checks then switch to Odoo *web session* auth via `/web/session/authenticate` — a different credential path with different rate-limit/2FA behaviour, chosen automatically at runtime — [odoo_connection.py:868-877], [access_control.py:172-215].
8. **`call_model_method`'s denylist is an enumeration**, explicitly admitted to be "the remote approximation" of in-process introspection. Custom modules' `action_*` methods, `toggle_active`, `button_draft` etc. remain callable; the README warns but nothing blocks.
9. **`_cleanup_connection()` clears `self.connection` but FastMCP has no deregistration**, so already-registered handler closures hold a dead reference; the code documents this as unsupported-but-benign rather than fixing it — [server.py:266-279].
10. **Private-API coupling to the SDK** in three places: `app._mcp_server.instructions`, `app._session_manager` pre-seeding (`_preseed_session_manager`, with a "Remove once FastMCP plumbs session_idle_timeout through" TODO), and the low-level `read_resource` override. Each is a version-fragility point; the `mcp>=1.27.0` floor already exists for one of them.
11. **Everything runs as one Odoo user.** There is no per-caller identity on the MCP side; if the HTTP transport is shared, all callers collapse into the single configured account.
12. **No write payload validation against `fields_get`** — an unknown or read-only field reaches Odoo and comes back as a fault; no dry-run, no diff, no confirmation.

---

## 13. Transferable to the reader's server (Python/FastMCP/XML-RPC/35 domain tools)

### Worth copying — mapped to the stated gaps

**Gap: no runtime `fields_get` validation of write payloads.**
- Copy `_check_xmlrpc_int_bounds` wholesale ([tools.py:280-303]): a recursive walk of `values` (including nested x2many command tuples) rejecting ints outside signed-32-bit **before** any RPC. It is 20 lines, has no dependencies, and converts an `OverflowError` mid-marshal into a clean validation error. This is not `fields_get` validation, but it is the cheapest slice of it and it is the one that currently produces the worst error.
- Copy the **read-back-after-write** pattern: after `create`/`write`, re-read `["id","display_name"]` and return it plus a record URL ([tools.py:2155-2178]). Cheap (one extra RPC on `display_name` only), and it turns "did it work?" into evidence — which pairs directly with an audit log.
- Copy `check_domain_balance` ([access_control.py:575-608]) if any of the 35 tools appends a scope/tenant condition to a caller-supplied domain. A trailing `"|"` in the caller's domain silently ORs your scope away. This is a real, quiet privilege escalation that only shows up when you concatenate.

**Gap: no credential-field filtering on read results.**
- Port `field_security.py` almost verbatim (171 lines, zero dependencies). Its value over a naive suffix list is the segment algebra: `_id`/`_ids` and `is_`/`has_`/`can_` exclusions, digit- and empty-segment popping (`password_`, `api_key_2`), the representation-suffix pop (`password_hash`), and the `(api|secret|hmac|signature|…)+key` compounds. The markers were validated against a real Odoo 19 field census — you would otherwise have to redo that work.
- Copy the **three-part contract**, not just the filter: (a) apply on bulk paths only, (b) honour explicitly-named fields, (c) **say what you withheld** in the response (`withheld_note`). A silent filter makes an LLM retry blindly; the note converts it into a one-step recovery.
- Also copy `_is_sensitive_log_key`/`_redact_values` ([odoo_connection.py:38-75]) into the choke-point `odoo()` function: your event log already fingerprints arguments — use the same detector so a `smtp_pass` never lands in it.

**Gap: no per-write approval inside the server.**
- The honest finding is that **this repo does not solve it either** — there is no confirmation, dry-run or diff anywhere. Your LangGraph-interrupt design is strictly ahead. What *is* transferable is the **shape of the pre-flight**: a fixed, identical 5-gate sequence (`validate_model_access → is_authenticated → non-empty payload → payload range/shape checks → domain-specific gate`) run in the same order by every write handler, then one funnelled `except` ladder. With 35 tools, extracting that into a decorator is higher-value for you than for them.
- Copy the **`Unavailable` ≠ `Denied` distinction** ([access_control.py:29-38]) into your global write toggle. Your toggle reads `ir.config_parameter` and fails closed — good — but if the read *fails*, a caller currently cannot tell "writes are off" from "I could not check". Their rule: both fail closed, but the second is reported as retryable and never as a denial. That difference matters when an agent decides whether to retry or to give up and tell the user.
- Copy the **write-unsafe retry gate** ([performance.py:239-292]): their transport retries a timed-out request only on a reused keepalive socket **and** only when the method is read-only, because *"a timed-out write could already be committing server-side"*. If your `odoo()` choke point has any retry at all, it needs this gate; if it doesn't, note that Python's stdlib `xmlrpc` transport already retries on `RemoteDisconnected` — silently, for writes.

**Also worth copying (not tied to a stated gap):**
- **The `ir.attachment` reasoning, not just the code.** Their finding generalizes: gating the *payload* is not enough when the *metadata row* carries `url` and `index_content` (extracted document text) — and an ungated `update_record` can repoint an excluded model's attachment at an allowed one, then read it back ([CHANGELOG.md 0.8.0 Security]). With a RAG corpus and `muc19_rbac_rag` still open, check whether any of your 35 tools exposes `ir.attachment` rows, `index_content`, or `mail.message` bodies without gating the *attached-to* model.
- **Prompt-injection hardening of injected context** (`_one_line`, [user_context.py:92-113]). You inject role declarations and session context into prompts; a partner name containing U+2028 can forge a line in that block. One `str.translate` call with the full line-break set.
- **`bin_size=True` + resource URIs instead of inline base64** ([tools.py:1517-1521]). If any of your 35 tools can return a binary field, this pattern (placeholder read, URI in the result, bytes only on explicit fetch, size ceiling checked *before* fetching) prevents a single attachment from blowing the context window or the process's memory.
- **Always `search_count`, never infer totals from a short page** ([tools.py:1449-1460]) — their measurement on `mail.message` (10 requested, 5 returned, 86 matching) is exactly the class of bug your eval harness would score as a wrong answer, not as a pagination bug.
- **Offset depth cap** ([tools.py:305-320]) — cheap DoS protection your rate limiter does not cover.
- **`ToolAnnotations` on every tool.** With 35 tools, honest `readOnlyHint` / `destructiveHint` lets your agent layer decide *automatically* which calls need the LangGraph interrupt instead of maintaining a parallel list.
- **Their test-layering discipline**: lazy, memoized service probes so unit runs never touch the network, plus a CI permission fixture built as a *matrix* (one model create-denied, one read-only, one model deliberately not enabled). Your memory notes repeatedly record "tests green, live-verify found the bug" — this is the structural fix for that pattern: a CI fixture whose permissions are *deliberately asymmetric*.

### NOT worth copying
- **YOLO mode.** Its purpose is demoability on a stranger's Odoo. You control both ends and already have per-role isolated processes with dedicated accounts; a global "bypass all access control" switch is pure downside and directly contradicts your fail-closed toggle.
- **The generic-CRUD tool surface** (`search_records`/`create_record` over arbitrary models). Your 35 domain-specific tools with a method whitelist are a strictly smaller attack surface and give the LLM business semantics. Adopting generic CRUD would hand every model on the database to the model as a writable target.
- **`call_model_method`.** Its own denylist is admitted to be an approximation, and it is gated on full YOLO — i.e. it only exists where nothing else is checked. If you ever need a workflow-method escape hatch, make it a *named, per-method allowlist* (the inverse of their design), which is what your method whitelist already is.
- **Streamable-http without client auth.** You bind 127.0.0.1 — keep it. Their `_warn_if_exposed` text is worth stealing as a startup assertion, but their transport posture is not a model.
- **Private-SDK-attribute patching** (`app._mcp_server.instructions`, `app._session_manager`, low-level `read_resource` override). Three separate version-fragility points; you have no need matching any of them.
- **The 300-second permission cache.** Your permission model is process-level (one role per process, one dedicated Odoo account) and does not need a per-model cache — adding one would only create a window where a revoked right still works.
- **The `AccessController` web-session fallback** (`/web/session/authenticate` when the API key is rejected). Silent runtime credential-path switching is exactly the class of invisible-dependency problem your memory records (`feedback_erp_query_live_measurement_account`). Fail loudly instead.

### Gaps in this analysis
- The addon's actual enforcement code is unreadable (private + OPL-1 paid), so "the addon re-checks server-side" rests on the client's comments, the 403 messages it forwards, the CI setup, and the vendor's store listing — not on read source.
- No GitHub issue/PR discussion was read beyond what the CHANGELOG and in-code issue references (#68, #70) preserve; rationale attributed above is from code comments and the changelog, both first-party.
