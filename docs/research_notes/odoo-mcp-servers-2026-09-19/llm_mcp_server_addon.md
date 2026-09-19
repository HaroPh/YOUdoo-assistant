# `llm_mcp_server` (Apexive `odoo-llm` suite) — MCP server running INSIDE Odoo

> Research date: 2026-09-19. All code read from a read-only clone of
> `https://github.com/apexive/odoo-llm` at
> `C:\Users\ADMIN\AppData\Local\Temp\claude\d--Youdoo\b419e890-6b02-466c-a1db-dc484e24662f\scratchpad\repos\llm-mcp-server`.
> Branch `18.0` @ `609ec6dd` (2026-05-26, head of the default branch); branch `19.0` @ merge of PR #252 (2026-05-09) also inspected.
> Odoo core excerpts read from `raw.githubusercontent.com/odoo/odoo/18.0/...`.
> All paths below are **repo-relative to the `apexive/odoo-llm` root** unless stated otherwise.

---

## Key questions — direct answers up front

**Q1. Which `auth=` mode does `/mcp` use, and how does it turn a Bearer key into a user environment?**
The POST route is `auth="public"` — *not* `auth="bearer"`. Authentication is applied **per JSON-RPC method**, inside the handler, by a local decorator that first blanks the env and then calls Odoo's built-in bearer auth:

```python
# llm_mcp_server/controllers/mcp_controller.py:37-48
def requires_bearer_auth(handler_func):
    def wrapper(self, *args, **kwargs):
        # Clean up the public uid and use built-in _auth_method_bearer
        request.update_env(user=False)
        request.env["ir.http"]._auth_method_bearer()
        return handler_func(self, *args, **kwargs)
    return wrapper

# llm_mcp_server/controllers/mcp_controller.py:60-62
@http.route("/mcp", type="mcp_json", auth="public", methods=["POST"], csrf=False, cors="*")
```

Only `tools/list` (line 191) and `tools/call` (line 196) carry `@requires_bearer_auth`. `initialize`, `ping`, `notifications/initialized` and `GET/POST /mcp/health` are reachable **unauthenticated**. Odoo's `_auth_method_bearer` (`odoo/addons/base/models/ir_http.py`) parses `Authorization: Bearer <k>`, calls `res.users.apikeys._check_credentials(scope='rpc', key=token)`, and on success does `request.update_env(user=uid)` then `_auth_method_user()`. From then on `request.env` is that user's environment and every `self.env[model]` in a tool body goes through normal ORM ACL + `ir.rule`.

**Q2. Is there any tool-level permission layer, or is Odoo's ACL the only gate?**
Depends on the branch, and this is a real divergence:
- **18.0 (= the Apps Store build): Odoo's ACL is the only gate.** There is no `ir.rule` on `llm.tool` anywhere in the 18.0 tree, every internal user has read on `llm.tool` (`llm_tool/security/ir.model.access.csv:2`), and `tools/list` is explicitly `sudo()`-ed (`llm_mcp_server/models/llm_tool.py:17`), so *every authenticated internal user sees and can invoke every active tool*.
- **19.0 (branch only, not on the store): a real per-tool layer exists.** `llm_tool/security/llm_tool_rules.xml` defines record rules keyed on a new `category` Selection field (`llm_tool/models/llm_tool.py:110-120`, values `general`/`technical`), and `tools/list` there is *not* sudo-ed. Ordinary internal users see only `category='general'`; `base.group_system` and `llm.group_llm_manager` see all. In the shipped data, `odoo_model_method_executor` is `technical`, the other five are `general`.
There is **no per-key scoping** on either branch (no read-only key, no model allowlist), and `requires_user_consent` is **not enforced on the MCP path at all** (see item 5).

**Q3. Does it write an audit record per tool call?**
**No.** There is no audit model, no `message_post`, no `mail.message` write anywhere in `llm_mcp_server` (`grep -rn "message_post\|_message_log" llm_mcp_server` → zero hits). The only per-call trace is `_logger.info(...)` lines inside individual tool implementations, e.g. `llm_tool/models/llm_tool_record_updater.py:33-35`, plus `_logger.exception` on failure (`llm_mcp_server/models/llm_tool.py:56`). Everything else is Odoo's ordinary `create_uid` / `write_uid` / `mail.thread` tracking on the *business* records. **The module README's claim "Audit trail: All tool calls logged in Odoo" (`llm_mcp_server/README.md`, Security section) and the identical claim on the Apps Store page are not supported by the code** — see item 10 for the full list of doc/code contradictions.

---

## 1. Repo facts

| Fact | Value | Evidence |
|---|---|---|
| Source repo | **https://github.com/apexive/odoo-llm** (public) | `llm_mcp_server/__manifest__.py` `"website"` field |
| Author | Apexive Solutions LLC | `__manifest__.py` |
| License | LGPL-3 (per-module manifest). GitHub API reports repo-level `license: null` — there is no root LICENSE file detected by GitHub | `__manifest__.py`; `api.github.com/repos/apexive/odoo-llm` |
| Stars / forks / open issues / watchers | 219 / 159 / 47 / 17 | GitHub API, fetched 2026-09-19 |
| Created / last push | 2023-12-10 / **2026-05-26T13:23:30Z** | GitHub API |
| Default branch | `18.0` | GitHub API |
| Branches with the module | `16.0`, `18.0`, `19.0` (+ ~25 WIP/feature branches). No `17.0` release branch, only `17.0-backport-migration` | `git branch -r` |
| Apps Store listing | versions 18.0 and 16.0 only; **628 downloads**, "Third Party" | https://apps.odoo.com/apps/modules/18.0/llm_mcp_server |
| Module version | `18.0.1.3.2` (18.0) / `19.0.1.0.0` (19.0 branch) | manifests |
| Module size | **1,128 Python LOC**; 2,057 LOC counting XML/CSV/shell | `wc -l` over `llm_mcp_server/**` |
| Module dependency | `["base", "llm", "llm_tool", "web_json_editor"]` on 18.0; `["base", "llm", "llm_tool"]` on 19.0 | manifests |
| External Python dep | `mcp` (the official Anthropic MCP SDK) — imported *into the Odoo process*; `llm_tool` additionally needs `pydantic>=2.0.0` | `__manifest__.py` `external_dependencies` |
| CI | **None in the repo** — no `.github/` directory at all on 18.0 | `ls -a .github` → not found |
| Tests | No Python unit tests for `llm_mcp_server`; two curl shell scripts (`tests/test_stateful.sh`, `tests/test_stateless.sh`). `llm_tool` has 36 Odoo unit tests across 3 files | `find`, `grep -n "def test_"` |
| Module commit activity (shallow clone, depth 50) | 2025-12 ×1, 2026-01 ×1, 2026-02 ×4, 2026-05 ×3 | `git log -- llm_mcp_server` |
| First release | 18.0.1.0.0 on **2025-10-23** | `llm_mcp_server/changelog.rst` |

**Suite composition.** The 18.0 branch ships 32 addons. The MCP-relevant spine is three layers:

- `llm` — core: providers, models, security groups (`llm.group_llm_manager`, `llm.group_llm_user`).
- `llm_tool` — **the registry**: the `llm.tool` model, the `@llm_tool` decorator, schema generation, and the 6 generic tools. 2,961 Python LOC incl. tests.
- `llm_mcp_server` — the HTTP/MCP transport. Depends on the two above; **nothing depends on it**. Dependency direction is strictly one-way (transport → registry → core), so the same registry also feeds the in-Odoo chat UI (`llm_thread`, `llm_assistant`) and the Letta bridge (`llm_letta`).

Domain tool packs (each is a plain addon that `_inherit = "llm.tool"` or decorates business models), counted by `grep -c "@llm_tool"`:

| Addon | `@llm_tool` methods |
|---|---|
| `llm_tool_mis_builder` | 44 |
| `llm_tool_website` | 31 |
| `llm_tool_account` | 18 |
| `llm_tool_demo` | 11 |
| `llm_tool_ocr_mistral` | 1 |
| `llm_tool_knowledge` | 0 decorated — uses the `_get_available_implementations` pattern instead (`llm_tool_knowledge/models/llm_tool_knowledge_retriever.py`) |

Note: the 16.0 branch additionally contains `llm_mcp` — an MCP **client** (Odoo consuming external MCP servers). That module does **not** exist on 18.0 or 19.0. Don't confuse `llm_mcp` with `llm_mcp_server`.

---

## 2. Architecture: how an MCP server is embedded in Odoo

**Three moving parts and no socket of its own.** There is no separate process, no asyncio loop, no `FastMCP` server object. The module registers a *new Odoo routing type* and a controller, and the MCP protocol is spoken over Odoo's ordinary werkzeug request path.

**(a) A custom dispatcher registers the routing type.** `llm_mcp_server/__init__.py:1` imports the dispatcher module *before* controllers, purely for its registration side effect:

```python
# llm_mcp_server/mcp_json_dispatcher.py:74-80
class MCPJsonRPCDispatcher(JsonRPCDispatcher):
    routing_type = "mcp_json"
```

Odoo's `http.Dispatcher` metaclass picks up `routing_type` and makes `type="mcp_json"` usable in `@http.route`. So MCP requests reuse Odoo's own JSON-RPC 2.0 parsing, `id` handling, error envelope and `make_json_response`, and the subclass only adds MCP-specific behaviour.

**(b) Routes.** Three, all in `llm_mcp_server/controllers/mcp_controller.py`:

| Route | Type | auth | Notes |
|---|---|---|---|
| `POST /mcp` (line 60) | `mcp_json` | `public` | `csrf=False`, `cors="*"`. The whole protocol surface. |
| `DELETE /mcp` (line 98) | `http` | `bearer` | session termination; `csrf=False` |
| `GET\|POST /mcp/health` (line 228) | `http` | `public` | returns `{"status","server","version"}` |

**(c) Request lifecycle for `POST /mcp`:**
1. Odoo routing matches the rule; because `auth="public"`, `request.env` is the **public user** at entry.
2. `MCPJsonRPCDispatcher.dispatch` (line 82) *peeks* at the body before the endpoint runs: `self.request.get_json_data()`, extracts `method` and the `Mcp-Session-Id` header, then runs `_validate_session_requirements` (line 182) and `_validate_protocol_version` (line 216). Both read `llm.mcp.server.config` with `.sudo()` because the caller is still the public user. Parse failures are swallowed (`except (ValueError, AttributeError): pass`) so the parent can emit a proper JSON-RPC parse error.
3. `super().dispatch(endpoint, args)` — Odoo's stock `JsonRPCDispatcher` — parses the envelope and calls the endpoint with `params` as kwargs.
4. `mcp_endpoint` re-reads the method off `request.dispatcher.jsonrequest` and does **string-to-handler name mangling**, not a dict table:
   ```python
   # mcp_controller.py:210-213
   def _is_callable(self, method_name):
       handler_name = f"_mcp_{method_name.replace('/', '_').replace('-', '_')}"
       return hasattr(self, handler_name) and callable(getattr(self, handler_name))
   ```
   so `tools/call` → `_mcp_tools_call`, `notifications/initialized` → `_mcp_notifications_initialized`. Unknown → `MCPMethodNotFoundError`.
5. The handler runs (authenticating first if decorated), returns a pydantic object, and `mcp_endpoint` serialises it: `result.model_dump(exclude_none=True)` (line 94).
6. `_response` (dispatcher line 169) attaches `Mcp-Session-Id` to the outgoing headers if the handler stashed one on `request`.
7. Odoo's normal request teardown commits the cursor.

**`initialize` / `tools/list` / `tools/call`:**
- `initialize` (line 126) reads the singleton config, negotiates the protocol version from the `Mcp-Protocol-Version` header *or* `params.protocolVersion`, builds an `InitializeResult` from the real MCP SDK types (`Implementation`, `ServerCapabilities`, `ToolsCapability(listChanged=False)`; `llm_mcp_server/models/llm_mcp_server_config.py:145-158`), and in `stateful` mode creates an `llm.mcp.session` DB row and returns its `session_id` in the response header.
- `tools/list` (line 191) → `request.env["llm.tool"].get_mcp_tools_list()`.
- `tools/call` (line 196) → `request.env["llm.tool"].execute_mcp_tool(params)`.
- `notifications/initialized` (line 163) commits the state transition and then **aborts out of the JSON-RPC envelope entirely** to return a bare `202 Accepted`, with a code comment citing Odoo's own pattern: `werkzeug.exceptions.abort(http.Response("", ..., status=HTTPStatus.ACCEPTED))`.

**Streaming: there is none.** The README says "Transport: `streamable-http`" and "Response streamed back via HTTP streaming", but no `text/event-stream`, no generator response and no SSE code exists anywhere in the module (`grep -rni "event-stream|sse|stream" llm_mcp_server/*.py` matches only the literal `"MCP_TRANSPORT": "streamable-http"` string inside the *client config template*). The module's own test README is honest about it: *"Standard HTTP/JSON (no SSE streaming)"* (`llm_mcp_server/tests/README.md`, "Test Architecture"). The generated client config routes Claude Desktop through `npx mcp-remote`, which speaks streamable-HTTP to the client side and plain request/response to Odoo.

---

## 3. Odoo access layer

Because it runs in-process there is **no XML-RPC, no JSON-RPC client, no connection pool** — it is direct ORM access on the live request cursor.

- **No `with_user()` anywhere.** `grep -rn "with_user" llm_mcp_server llm_tool llm` → zero hits. The user switch is done once, at the request level, by `request.update_env(user=uid)` inside Odoo's `_auth_method_bearer`. Everything downstream just uses `self.env` / `request.env`.
- Tool bodies use the plain env: `model_obj = self.env[model]` then `search_read` / `create` / `write` / `unlink` (`llm_tool/models/llm_tool_record_retriever.py:37`, `..._creator.py:42`, `..._updater.py:37`, `..._unlinker.py:35`). All ACL, record rules, field groups, `@api.constrains` and computed-field logic apply exactly as they would for that user clicking in the web UI.
- **API key → user.** `res.users.apikeys._check_credentials` (Odoo 18 `odoo/addons/base/models/res_users.py:2394-2411`):
  ```sql
  SELECT user_id, key FROM res_users_apikeys INNER JOIN res_users u ON (u.id = user_id)
  WHERE u.active and index = %s
    AND (scope IS NULL OR scope = %s)
    AND (expiration_date IS NULL OR expiration_date >= now() at time zone 'utc')
  ```
  followed by `KEY_CRYPT_CONTEXT.verify(key, current_key)`. Note the Odoo core comment at `ir_http.py`: *"'rpc' scope does not really exist, we basically require a global key (scope NULL)"*.
- **`sudo()` inventory in `llm_mcp_server` (9 call sites, all deliberate):**

  | Site | Purpose |
  |---|---|
  | `controllers/mcp_controller.py:128,144,170,231` | pre-auth reads/writes of `llm.mcp.server.config` and `llm.mcp.session` while still the public user |
  | `mcp_json_dispatcher.py:194,205` | same, from the pre-dispatch validation |
  | `models/llm_tool.py:17` | **`tools/list` lists ALL active tools regardless of the caller** (18.0 only) |
  | `models/llm_mcp_server_config.py:140` | read `web.base.url` from `ir.config_parameter` |
  | `wizards/mcp_key_wizard.py:21` | unlink the transient description record |

  Crucially, **no `sudo()` is on the tool-execution path** on 18.0 — `execute_mcp_tool` uses `self.search(...)` and the tool body uses `self.env[...]`. The permission-inheritance claim is genuinely realised.
- Six `sudo()` calls do exist *inside tool packs*: `llm_tool_website/models/website_visitor.py:47,57,122,165,171` (website visitor/track data) and `llm_tool_knowledge/models/llm_tool_knowledge_retriever.py:24` (knowledge collections). These are deliberate ACL bypasses in the tool bodies — if you install those packs, "the AI only sees what the user sees" stops being true for those specific datasets.

---

## 4. Tool design — the `llm.tool` registry

**Tools are Odoo *records*, not Python objects.** `llm.tool` (`llm_tool/models/llm_tool.py:13`) is a real model with `name`, `description`, `implementation`, `input_schema`, `active`, and the four MCP annotation booleans. Two registration mechanisms coexist:

**(a) Selection-based implementations** (the original pattern). A module inherits `llm.tool`, extends the `implementation` selection, and provides a `{implementation}_execute` method:
```python
# llm_tool/models/llm_tool_record_retriever.py:13-16
@api.model
def _get_available_implementations(self):
    return super()._get_available_implementations() + [("odoo_record_retriever", "Odoo Record Retriever")]
```
Dispatch is by convention at `llm_tool/models/llm_tool.py:226-233`: `impl_method_name = f"{self.implementation}_execute"`. The record itself is declared in XML (`llm_tool/data/llm_tool_data.xml`).

**(b) `@llm_tool` decorator + auto-discovery** (the newer pattern, `llm_tool/decorators.py`). Decorating any model method stamps `_is_llm_tool`, `_llm_tool_name`, `_llm_tool_description`, `_llm_tool_metadata`, `_llm_tool_xml_managed` onto the function. **Type hints on every parameter and on the return are mandatory** unless an explicit `schema=` is supplied (`decorators.py:149-181` raises `ValueError` otherwise) — a nice forcing function for schema quality.

Discovery runs at registry load, not at request time:
```python
# llm_tool/models/llm_tool.py:268-273
@api.model
def _register_hook(self):
    super()._register_hook()
    self._scan_tool_decorators()
    self._sync_tools_to_db()
```
`_scan_tool_decorators` (line 275) walks **every model in `self.env.registry`** and every public attribute of each model class looking for `_is_llm_tool`. `_sync_tools_to_db` (line 318) then reconciles the in-memory registry against the `llm_tool` table with **raw SQL**, guarded by a Postgres advisory lock:
```python
lock_key = hash(cr.dbname) & 0x7FFFFFFF
cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
```
The docstring explains why raw SQL: *"Raw SQL bypasses the ORM cache, which avoids the SerializationFailure that occurs when load_modules calls flush_all() with dirty ORM state from concurrent workers."* Tools absent from the registry get `active = false` (unless XML-managed). There is also a manual "Sync Tools" button (`action_sync_tools`, line 443).

**Built-in tools shipped by `llm_tool` (all six are generic, model-agnostic CRUD):**

| Tool | One line | consent flag |
|---|---|---|
| `odoo_record_retriever` | `search_read` on any model with domain/fields/limit (default 100) | no |
| `odoo_record_creator` | `create()` one record (`fields`) or many (`records`) on any model | yes |
| `odoo_record_updater` | `search(domain, limit=1)` then `write(values)` on any model | yes |
| `odoo_record_unlinker` | `search(domain, limit=1)` then `unlink()` on any model | yes |
| `odoo_model_method_executor` | **Call an arbitrary method** on any model or recordset with arbitrary args; `allow_private=True` even reaches `_`-prefixed methods | yes |
| `odoo_model_inspector` | Introspect a model: fields, types, relations, method signatures, docstrings, decorators | no (`read_only_hint=True`) |

The XML description for the method executor is candid: *"**VERY HIGH RISK TOOL** … It bypasses standard UI workflows. **IMPORTANT:** The LLM using this tool MUST explicitly ask the user for confirmation before EVERY execution"* (`llm_tool/data/llm_tool_data.xml`). That "MUST" is addressed to the model, not to any code.

The domain packs are the opposite style — narrow, named, business-level, e.g. `account_get_balances`, `account_get_ledger`, `account_create_move`, `account_post_moves`, `account_reverse_move`, `account_register_payment`, `account_check_period`, `account_set_lock_date`, `account_get_unreconciled`, `account_reconcile`, `account_suggest_matches`, `account_get_profit_and_loss`, `account_get_cash_position`, `account_get_tax_balances` (`llm_tool_account/models/*.py`); `website_create_page`, `website_publish_page`, `website_delete_redirect`, `website_seo_audit`, … (`llm_tool_website/models/*.py`).

**Input schema generation** (`llm_tool/models/llm_tool.py:171-194`) has two tiers: use `input_schema` from the DB if set (manual override or decorator-stored), otherwise generate from the signature using the MCP SDK's own helper:
```python
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
func_meta = func_metadata(method_func)
schema = func_meta.arg_model.model_json_schema(by_alias=True)
```
So the wire schema is produced by the *same* library the clients use. `get_tool_definition` (line 492) builds a real `mcp.types.Tool` with `ToolAnnotations(readOnlyHint, idempotentHint, destructiveHint, openWorldHint)` and returns `model_dump(exclude_none=True)`. There is a whole doc, `llm_tool/OPENAI_SCHEMA_COMPATIBILITY.md`, about keeping schemas OpenAI-function-calling-compatible, which is why the method executor's args are typed as primitives-or-JSON-strings and re-parsed by `_parse_json_value` (`llm_tool_model_method_executor.py:21-37`).

**Output formatting is weak.** `execute_mcp_tool` collapses any return value to a single text block using Python's `str()`:
```python
# llm_mcp_server/models/llm_tool.py:51-54
content = [TextContent(type="text", text=str(result) if result is not None else "")]
return CallToolResult(content=content, isError=False)
```
A dict therefore reaches the model as Python repr (single quotes, `True`/`None`), not JSON. No `structuredContent`, no pagination, no truncation.

---

## 5. Write-path flow, `tools/call` → ORM commit

Traced for `odoo_record_updater` with `{"model":"sale.order","domain":[["id","=",7]],"values":{"note":"x"}}`:

1. **Dispatcher pre-validation** — `MCPJsonRPCDispatcher.dispatch:82`. Peeks the body. `_validate_session_requirements` (line 182): if mode is `stateful` and the method is not `initialize`/`ping`/`notifications/initialized`, require `Mcp-Session-Id` (400 if missing), require the session to exist (404), require `session.is_method_allowed(method)`. `_validate_protocol_version` (line 216): 400 if a supplied `Mcp-Protocol-Version` is not in the configured list. **Note both run as the public user; neither is an authorization check.**
2. **Route + envelope** — `auth="public"` so no credential is needed yet; Odoo's `JsonRPCDispatcher` parses the envelope and calls `mcp_endpoint`.
3. **Method mangling** — `_is_callable` / `_dispatch` resolve `_mcp_tools_call`.
4. **Authentication** — `@requires_bearer_auth`: `request.update_env(user=False)` then `ir.http._auth_method_bearer()` → key lookup → `request.update_env(user=uid)` → `_auth_method_user()` rejects public/None. Failure raises `werkzeug Unauthorized`, which `handle_error` (dispatcher line 104) converts into a JSON-RPC error carrying the **real HTTP status** (401).
5. **Session stamping** — `mcp_controller.py:202-206`: if a session exists and `session.user_id` is empty, set it to the authenticated user. Set once, **never verified afterwards**.
6. **Tool lookup** — `llm_mcp_server/models/llm_tool.py:42`: `self.search([("name","=",tool_name),("active","=",True)], limit=1)` in the *user's* env. On 19.0 this is where the `category` record rule bites; on 18.0 every internal user matches.
7. **Argument validation** — `llm_tool/models/llm_tool.py:196-206`: builds a pydantic model from the Python signature via `get_pydantic_model_from_signature` and does `model(**parameters)`. Type errors raise here, before any ORM call. This is the only input validation.
8. **Execution** — `records = self.env[model].search(domain, limit=limit)` then `records.write(values)`. Odoo enforces `ir.model.access`, `ir.rule`, field-level `groups=`, `@api.constrains`, SQL constraints, and fires computes/`mail.thread` tracking.
9. **Result** — wrapped as `CallToolResult(content=[TextContent(str(result))], isError=False)` → `model_dump(exclude_none=True)` → JSON-RPC result → HTTP 200.

**Checks that do NOT exist on this path:** no confirmation/interrupt, no dry-run, no model allowlist or denylist, no method whitelist, no read-only mode, no global write kill-switch, no rate limit, no argument fingerprint, no size cap on returned rows beyond each tool's own `limit` default.

**`requires_user_consent` is dead code on the MCP path.** The field exists (`llm_tool/models/llm_tool.py:87-90`) and four of the six built-in tools set it, but its only consumer is `llm_tool/models/llm_provider.py:56-60`, which injects a *system-message sentence* into prompts for the **in-Odoo chat** flow (`llm.tool.consent.config.system_message_template`: *"you MUST … ask for their explicit permission"*). `execute_mcp_tool` never reads the flag. An external MCP client never even sees it — it is not mapped to any MCP annotation. So for an MCP caller, "requires user consent" is a string in the database and nothing more.

**Transaction / rollback behaviour is the weakest link.** `execute_mcp_tool` wraps execution in a blanket catch:
```python
# llm_mcp_server/models/llm_tool.py:55-60
except Exception as e:
    _logger.exception(f"Error executing tool {tool_name}")
    error_content = [TextContent(type="text", text=f"Tool execution failed: {str(e)}")]
    return CallToolResult(content=error_content, isError=True)
```
No `savepoint`, no `cr.rollback()`. Because the exception is swallowed and a normal 200 response is produced, Odoo's standard request teardown **commits the cursor**. A tool that creates three records and then raises on the fourth leaves the first three persisted while the client is told the call failed. (Inferred from Odoo's ordinary request lifecycle — Odoo commits when the endpoint returns without raising — combined with the verified absence of any savepoint/rollback in this module. I did not execute the code.) Separately, `_mcp_notifications_initialized` performs an explicit mid-request `session._cr.commit()` (line 175), with the comment *"Force immediate commit so concurrent requests see the updated state"*.

---

## 6. Permission / security model — KEY ITEM

**How "inherits the user's Odoo permissions" is actually realised.** The chain is short and genuinely sound:

```
Authorization: Bearer <k>
  → res.users.apikeys._check_credentials(scope='rpc', key=k)   [hash verify, active user, not expired]
  → uid
  → request.update_env(user=uid)                                [new Environment bound to that uid]
  → request.env["llm.tool"].execute_mcp_tool(...)
  → tool body: self.env[model].search/create/write/unlink
  → Odoo ORM: ir.model.access → ir.rule → field groups → constraints
```
There is no shadow permission model and no service account in the middle. The AI's effective rights are *exactly* the user's rights, recomputed by the same code that serves the web client. That is the design's central strength and the code supports the claim.

**Yes — an admin API key gives the AI full admin.** Nothing narrows it. Combined with `odoo_record_updater` on `ir.config_parameter` / `res.users` / `ir.model.access`, or `odoo_model_method_executor` with `allow_private=True`, an admin-keyed MCP client can do anything an admin can do through a shell, including editing the ACL tables that are supposed to constrain it.

**No per-key scope narrowing of any kind.** Odoo's API keys carry a `scope` column, and `_generate(scope, ...)` could in principle mint a narrow key — but the MCP wizard explicitly passes `None`:
```python
# llm_mcp_server/wizards/mcp_key_wizard.py:22-24
k = self.env["res.users.apikeys"]._generate(None, description.name, self.expiration_date)
```
and `_check_credentials` matches `scope IS NULL OR scope = %s`. **Therefore a "New MCP Key" is a fully general Odoo RPC credential**: the same string works against `/xmlrpc/2/object`, `/jsonrpc` and `/web/session/authenticate` for that user, with no MCP involved. There is no read-only key, no per-model allowlist, no per-tool key binding, no IP binding.

**Who can mint one.** Odoo core gates key creation at `res_users.py:2542`: `check_access_make_key()` raises unless `self.env.user._is_internal()`. Non-system users must also set an expiration date (`_check_expiration_date`). The module's wizard calls `check_access_make_key()` before generating (`mcp_key_wizard.py:20`) and is `@check_identity`-decorated (password re-prompt). Keys are shown once and stored as a hash + 8-char index.

**Unauthenticated surface.** `initialize`, `ping`, `notifications/initialized` and `/mcp/health` need no credential. Consequences:
- Anyone who can reach the host can create `llm.mcp.session` rows at will (one row per `initialize`), with attacker-controlled `client_info` / `client_capabilities` JSON stored. There is **no `ir.cron` for session GC anywhere in the suite** (`grep -rln "ir.cron" llm_mcp_server llm_tool llm` → nothing) and no expiry field. Unbounded table growth / trivial DoS vector.
- `/mcp/health` discloses the configured server name and version to anyone.
- Tool *enumeration* used to be unauthenticated too; that was fixed on 2026-05-26 (see item 10).

**CSRF / CORS.** `POST /mcp` is `csrf=False, cors="*"`. `pre_dispatch` (dispatcher line 150) additionally advertises `Access-Control-Allow-Headers: … Authorization, Mcp-Session-Id, Mcp-Protocol-Version` on preflight. This looks alarming but the decorator neutralises the browser-cookie attack: `request.update_env(user=False)` before `_auth_method_bearer()` forces Odoo into the `elif not request.env.uid:` branch whenever no `Authorization` header is present, raising `Unauthorized` instead of falling back to the session cookie (`ir_http.py`, `_auth_method_bearer`). So a malicious page cannot ride a logged-in Odoo session into `tools/call`. It *can* still hit the unauthenticated methods cross-origin. The `DELETE /mcp` route (`auth="bearer"`, no decorator) does keep Odoo's cookie fallback, but that path is guarded by core's `check_sec_headers()` (`Sec-Fetch-Dest: document` + `navigate` + `same-origin` + `Sec-Fetch-User: ?1`), which a cross-origin `fetch()` cannot forge.

**Rate limiting: none.** No counter, no throttle, no concurrency cap anywhere in the module.

**What a leaked API key exposes.** Everything that user can see and do in Odoo — read, write, delete, and arbitrary method invocation — reachable over plain HTTP from anywhere the Odoo host is reachable, with no second factor (Odoo API keys bypass 2FA by design), no IP restriction, and no rate limit. Because the key is scope-NULL, the attacker does not even need the MCP protocol. Mitigations that do exist: keys are revocable from the user's preferences, can carry an expiration date, and are rejected the moment the user is deactivated (`u.active` in the SQL).

**Session objects are not an authorization boundary** — and that is fine, because every request re-authenticates. `llm.mcp.session.get_session` matches on `session_id` only; the `user_id` field is stamped on first authenticated use and never compared again (`mcp_controller.py:202-206`). A guessed/stolen session id lets someone drive the *state machine*, not the tools. But it does mean `session.user_id` is unreliable as an audit signal: two different bearer tokens can share one session row and only the first is recorded.

**ACL rows worth noting.** `llm_mcp_server/security/ir.model.access.csv:6` grants **every internal user create/write/read on `llm.mcp.session`**, and the 18.0 changelog records the rationale: *"[FIX] Fixed session deletion permission - all authenticated users can now delete sessions; [IMP] Simplified permission model for MCP session management"*.

---

## 7. Audit / logging / observability

- **No per-call audit record.** Confirmed by grep: no `message_post`, no `_message_log`, no custom log model in `llm_mcp_server`. `llm.mcp.server.config` inherits `mail.thread` but that only tracks *configuration* field changes (`tracking=True` on `name`, `version`, `mode`, `active`, `external_url`, `client_name`).
- **What you do get:** Python logger lines from individual tool implementations at INFO (`f"Executing Odoo Record Updater with: model={model}, domain={domain}, values={values}, limit={limit}"` — `llm_tool_record_updater.py:33`), `_logger.exception` on any tool failure, `_logger.error` for every dispatcher error with `exc_info=True` (`mcp_json_dispatcher.py:109`), and Odoo core's own `_logger.info("%s generated: scope: <%s> for '%s' (#%s) from %s", ...)` on API-key creation and removal (`res_users.py:2448`, `:2388`). These go to the Odoo log file, correlated only by timestamp and PID.
- **What Odoo gives for free:** `create_uid`/`create_date`/`write_uid`/`write_date` on every touched record, and `mail.thread` field-tracking messages on models that define `tracking=True`. This is **per-human-user attribution at the record level** and it is real — you can answer "who changed this order" — but you cannot answer "which tool call did it, with what arguments, from which MCP client, in which session".
- **`llm.mcp.session` as a partial trace:** stores `client_info` (e.g. `{"name":"claude-ai","version":"0.1.0"}`), `client_capabilities`, `protocol_version`, `state`, `user_id`. Never pruned. There is a list/form view for it (`views/llm_mcp_session_views.xml`).
- The TECHNICAL_GUIDE calls this out as a deliberate tuning choice: *"Minimal Logging: Production mode logs only warnings and authentication events"* (`llm_mcp_server/docs/TECHNICAL_GUIDE.md`, Performance Optimizations).

---

## 8. Testing strategy

- **No automated tests for the MCP module.** `llm_mcp_server/tests/` contains only `test_stateful.sh` (238 lines) and `test_stateless.sh` (194 lines) — bash + curl smoke scripts that prompt for an API key (`MCP_API_KEY`) and hit a running server at `MCP_BASE_URL` (default `http://localhost:8069/mcp`). They check health, initialize, session-id extraction from headers, `notifications/initialized` → 202, `tools/list`, `ping`, `tools/call`, and error paths. They are not runnable in CI (they need a live Odoo and a human-supplied key).
- **No CI at all** on the 18.0 branch — there is no `.github/` directory. Repo-level quality tooling is limited to `.pre-commit-config.yaml`, `.ruff.toml`, `.eslintrc.yml`.
- **`llm_tool` is the tested layer**: 36 tests in `llm_tool/tests/` — `test_llm_tool_core.py` (decorator resolution, tool definitions, uniqueness constraints), `test_llm_tool_schema.py` (stored vs generated schema, reset, onchange), `test_llm_tool_concurrency.py` (the raw-SQL sync: create/update/no-op/deactivate/xml-managed/auto_update=False, plus the registry extraction helpers).
- `run_tests.sh` at the repo root is a developer convenience wrapper around `odoo-bin --test-enable --test-tags=<module> --stop-after-init` with hard-coded paths (`$ODOO_PATH/.venv310/bin/activate`, db `odoo_llm_test`, port 8071).
- **Nothing tests the security posture**: no test asserts that a non-admin cannot reach an admin-only model, that `tools/list` is authenticated, or that a failed write rolls back.

---

## 9. Extensibility — adding a tool

The decorator path is genuinely three steps and this is the suite's best feature (documented in `llm_tool/DECORATOR.md`):

1. In any addon that depends on `llm_tool`, inherit the business model and decorate a method — **with full type hints on every parameter and the return**:
   ```python
   from odoo.addons.llm_tool.decorators import llm_tool

   class SaleOrder(models.Model):
       _inherit = "sale.order"

       @llm_tool(read_only_hint=True, destructive_hint=False)
       def list_open_quotes(self, partner_id: int, limit: int = 20) -> dict:
           """Return the customer's open quotations."""
           ...
   ```
2. Restart Odoo (or upgrade the module). `_register_hook` scans the registry, `_sync_tools_to_db` INSERTs the `llm_tool` row with name, description (from the docstring), the four annotation hints and the generated JSON schema. A "Sync Tools" button on the tool list view does the same without a restart, *provided* the registry was already populated.
3. It appears in `tools/list` immediately — no MCP-side registration, no restart of any client, no schema file to maintain.

Variants: `@llm_tool(schema={...})` for legacy methods without type hints; `@llm_tool(xml_managed=True)` to take full control via an XML `llm.tool` record (auto-sync then skips the tool entirely, including deactivation); `auto_update=False` on the record to freeze admin-edited metadata. For a non-method-backed tool, inherit `llm.tool`, extend `_get_available_implementations`, and add `{implementation}_execute`.

On 19.0 you would also set `category` (and extend the Selection via `selection_add`) plus add an `ir.rule` if the tool should be group-restricted.

---

## 10. Notable design decisions and stated rationale

- **"Ultra-thin controller"** is the explicit north star: *"Ultra-thin HTTP controller that routes requests to appropriate Odoo models following proper separation of concerns"* (`mcp_controller.py:1-6`). Protocol lives in the dispatcher, state in `llm.mcp.session`, capabilities in `llm.mcp.server.config`, tools in `llm.tool`. It holds up — the controller is 238 lines and contains no business logic.
- **Reuse Odoo's JSON-RPC machinery rather than embed an MCP server.** Subclassing `JsonRPCDispatcher` with a new `routing_type` means Odoo does the parsing, id echoing, error envelope and response building. The subclass only adds session validation, protocol-version negotiation, custom HTTP status codes, and the `Mcp-Session-Id` response header.
- **Use the real MCP SDK's pydantic types on the wire** (`mcp.types.Tool`, `InitializeResult`, `CallToolResult`, `ToolAnnotations`) and the SDK's `func_metadata` for schema generation, so the server can't drift from the spec by hand-rolling dicts.
- **`update_env(user=False)` before bearer auth** (`mcp_controller.py:42`) — a small, deliberate and correct move: it removes the public uid so Odoo's session-cookie fallback cannot fire, forcing a real token.
- **`initializing` state allows every method** — an acknowledged hack with a `TODO` naming the cause: *"temporarily allow, because claude desktop is sending both notifications/initialize and tools/list at the similar time and causing race condition"* (`llm_mcp_session.py:100-102`). Paired with the explicit `session._cr.commit()` at `mcp_controller.py:175`.
- **Raw SQL + advisory lock for tool sync** — the docstring at `llm_tool.py:320-330` is unusually explicit about the failure it avoids (`SerializationFailure` from `load_modules` calling `flush_all()` with dirty ORM state across concurrent workers).
- **Ready-to-paste client configs** (Jinja2 templates at `llm_mcp_server/models/llm_mcp_server_config.py:18-47`) rendered *with the real key* the moment it is minted, for Claude Desktop, Claude Code and Codex, plus a `_slugify_mcp_url` that names the server `odoo-<host>-<db>`. Changelog 18.0.1.3.0 frames this as onboarding UX.
- **The one security-motivated commit in the module's recent history** (`d5869580`, 2026-05-26, contributor Matteo Mircoli, refs issue #255) is worth quoting because it is the clearest security reasoning in the repo:
  > *"Additionally, `_mcp_tools_list` now requires `@requires_bearer_auth`. `sudo()`ing it would let any anonymous caller enumerate the registered MCP tools (information disclosure)."*

  Before that commit, tool enumeration was unauthenticated. The companion commit `2a2a96b9` did the same for the dispatcher. Note the ordering: `e9622245` (2026-05-18) had tightened `ir.model.access.csv` from "no group" (= everyone, incl. public) to `base.group_user` to silence an Odoo 18 startup warning, which *broke* the public-user reads and forced the `sudo()` additions a week later. The 19.0 branch never took that csv change and therefore never needed the sudos.

- **Branch divergence worth knowing.** Comparing `origin/19.0` (2026-05-09) with `origin/18.0` (2026-05-26) for the same module, the **19.0 port is architecturally better on the security question and worse on freshness**:

  | | 18.0 (Apps Store) | 19.0 (branch only) |
  |---|---|---|
  | `tools/list` | `self.sudo().search(...)` — every tool to every user | `self.search(...)` — record-rule filtered, docstring: *"Returns only tools that the current user has permission to access. Filtering is handled by Odoo's native Record Rules based on 'category' field."* |
  | Per-tool permission layer | none | `llm_tool/security/llm_tool_rules.xml` + `category` Selection (`general` / `technical`, `selection_add`-extensible) |
  | `odoo_model_method_executor` reachable by | any internal user | only `base.group_system` / `llm.group_llm_manager` (category `technical`) |
  | Pre-auth `sudo()` fixes | present | **absent** (relies on the permissive ACL csv instead) |
  | `web_json_editor` dependency | yes | dropped |
  | Suite size | 32 addons | 3 addons (`llm`, `llm_tool`, `llm_mcp_server`) — a minimal port |

**Store/doc claims contradicted by the code** (all three are in both `llm_mcp_server/README.md` and the Apps Store page):
1. *"Audit trail: All tool calls logged in Odoo"* — **false**. No audit record exists; only Python logger lines.
2. *"For `tools/list`: Returns all active tools user can access"* / *"Users only see and modify data they're authorized to access"* — **false for tools/list on 18.0**, which is `sudo()`-ed. True on 19.0. (The "modify data" half is true on both.)
3. *"Response streamed back via HTTP streaming"* — **false**; plain request/response. The module's own `tests/README.md` says *"Standard HTTP/JSON (no SSE streaming)"*.

---

## 11. Weaknesses and risks in the code

**Security / correctness**
1. **`odoo_model_method_executor` with `allow_private`** is remote arbitrary-method execution scoped only by ACL. Odoo's own external API refuses `_`-prefixed methods; this tool re-enables them on request. On 18.0 every internal user can call it.
2. **No rollback on tool failure** (item 5) — partial writes commit while the client is told the call failed.
3. **`requires_user_consent` is unenforced** on the MCP path; the guarantee is a sentence in a prompt, and only for the *in-Odoo* chat, not for MCP at all.
4. **Unauthenticated `initialize` writes DB rows**, with no GC cron and no expiry ⇒ unbounded `llm_mcp_session` growth.
5. **"MCP key" is a scope-NULL Odoo RPC key** — the MCP branding implies a narrowing that does not exist.
6. **`tools/list` sudo leak on 18.0** — tool names and full descriptions (which frequently embed model names, field names and business process detail) are visible to every internal user.
7. **Blanket `except Exception` returns `isError=True` with `str(e)`** — Odoo exception messages can carry record names, model names and SQL fragments; these are handed to a third-party LLM client verbatim.
8. `_is_callable` uses `hasattr(self, "_mcp_" + mangled)`. The mangling only strips `/` and `-`, so a method name containing e.g. `.` or other characters simply won't resolve — but it is worth noting the handler namespace is the controller's attribute namespace. Nothing currently exploitable (`_mcp_` prefix + the controller has no dangerous `_mcp_*` attributes), but it is a name-based dispatch into `getattr`, not an explicit table.
9. `hash(cr.dbname)` as the advisory-lock key (`llm_tool.py:335`): CPython randomises `str` hashing per process (`PYTHONHASHSEED`). Odoo's prefork workers are forked from one master and inherit the seed, so this works in the classic single-host deployment — but **across separate processes/containers/hosts sharing one database (a very common Odoo deployment), the lock keys differ and the lock does not serialise anything**, reintroducing the race the code was written to prevent. Conversely, the key is a 31-bit hash of only the db name, so two *different* databases on the same cluster can collide and needlessly block each other.

**Operational**
10. **MCP calls consume Odoo HTTP workers.** Every `tools/call` occupies a worker for its full duration, competing directly with human web traffic. An agent doing 20 tool calls in a loop is 20 serialized worker-seconds. There is no separate pool, queue, or priority.
11. **Long-running tools hit Odoo's watchdogs.** `limit_time_real` / `limit_time_cpu` will kill a slow tool call mid-transaction; `limit_request` recycles workers. Nothing in the module is aware of these.
12. **No streaming means no progress and no partial results** for long calls, and the client-side `mcp-remote` shim adds a Node process per client.
13. **Upgrade coupling is total.** The controller depends on internals: `JsonRPCDispatcher`, `routing_type`, `request.dispatcher.jsonrequest`, `request.dispatcher.request_id`, `request.update_env`, `ir.http._auth_method_bearer` (which only exists from Odoo 17/18), and `werkzeug.exceptions.abort` with a comment citing *"Odoo's pattern from http.py line 2185"*. An Odoo minor upgrade that reshuffles `http.py` can break the MCP endpoint. The 19.0 port already had to change `_sql_constraints` → `models.Constraint`.
14. **The MCP SDK is imported into the Odoo process.** `mcp` + `pydantic>=2` now live in Odoo's dependency graph; an SDK bump for one addon is a bump for the whole ERP.
15. **Reverse proxy concerns**: `cors="*"` on `/mcp` means the endpoint answers cross-origin preflights from anywhere; if Odoo is behind a proxy that also serves the web client, `/mcp` inherits whatever TLS/timeouts/body limits that proxy imposes, and long tool calls can trip proxy read timeouts with no server-side keep-alive (no streaming).
16. **No tests, no CI** for the transport layer, so all of the above is unguarded against regression. The tool-enumeration hole went unnoticed from the 2025-10-23 initial release to 2026-05-26.

---

## 12. Comparison of approaches — in-Odoo addon vs external multi-process/multi-account

*(Reader's design as given: external Python FastMCP process, HTTP/SSE on 127.0.0.1, XML-RPC to Odoo 19.0 CE through a single `odoo()` choke point, 35 domain tools, method whitelist, global write toggle from `ir.config_parameter` fail-closed, rate limit, event log with argument fingerprint, hash-chained audit log + verifier, 3-4 processes each with its own dedicated Odoo account per role, per-write human confirmation in the LangGraph layer.)*

### Where the in-Odoo design is genuinely better

**a) Identity fidelity and per-*user* attribution — its single biggest win.** Every write lands with `create_uid`/`write_uid` = the actual human, and Odoo's `mail.thread` chatter on the business record says "Nguyễn A changed Delivery Date". The reader's design cannot produce that: every write by the `sales` process is `create_uid = ai-sales`, and the human identity survives only in the reader's own external audit log. If anyone ever asks "who approved this invoice" inside Odoo, the addon answers natively and the multi-account design answers "a robot did, go read another system's log".

**b) Permission correctness is free and always current.** The addon cannot drift from Odoo's ACL because it *is* Odoo's ACL, evaluated by the same code path as the web client, including `ir.rule` record-level filters, field-level `groups=`, multi-company rules and `@api.constrains`. The reader's per-role accounts also get ORM enforcement (XML-RPC goes through the same `execute_kw` → ORM path), so this is a smaller gap than it first looks — but the reader additionally maintains a method whitelist and 35 tool definitions that *can* drift from what the role account is actually allowed to do. The addon has nothing to keep in sync.

**c) N users scale without N processes.** 50 employees = 50 API keys and zero new infrastructure. The reader's model needs a process (and an Odoo account, and a port, and a supervisor entry) per role; it does not extend to per-person granularity at all.

**d) Zero deployment surface.** No second service to run, monitor, restart, or firewall. `odoo-bin -i llm_mcp_server` and it is live. The reader runs 3-4 long-lived processes with their own lifecycle, config and failure modes.

**e) Tool authoring is dramatically cheaper.** `@llm_tool` on a method of the model you are already editing, with the schema derived from type hints, versus writing a tool in the external server *and* an XML-RPC call *and* keeping the schema in sync by hand. For a team already writing Odoo modules, this is a real productivity difference.

**f) Extension points are first-class.** Want a gate? `_inherit = "llm.tool"` and override `execute_mcp_tool` in your own module. Odoo's inheritance makes adding behaviour to someone else's addon easy — which is *not* true of most external servers.

### Where the external multi-account design is genuinely better

**a) Server-side gates that Odoo structurally cannot express.** A global write on/off toggle, a rate limit, an argument fingerprint, and a hash-chained tamper-evident audit log are all things Odoo has no concept of. You *can* add them in an Odoo module (point (f) above) — but you cannot put them **out of the caller's reach**. That is the decisive asymmetry: on the addon, a sufficiently privileged key reaches the gate itself. An MCP client with an admin key can `odoo_record_updater` on `ir.config_parameter` to flip a toggle, `odoo_record_unlinker` the audit rows, or `odoo_model_method_executor` straight past everything. The reader's toggle is read *by the external process* from `ir.config_parameter`, and the account that reads it need not be an account that can write it — so the gate lives outside the blast radius of the credential the agent holds. Fail-closed evaluation outside the controlled system is a categorically stronger property than any in-system check.

**b) Blast radius of a leaked credential.** Addon: the leaked "MCP key" is a scope-NULL Odoo RPC credential for a *human* user, usable against `/xmlrpc/2/object` from anywhere, bypassing 2FA, with no rate limit — and if that human is an admin, it is game over. Reader: the leaked credential belongs to a purpose-built service account whose Odoo rights were cut to one role's needs; the MCP endpoint itself is on 127.0.0.1 and not reachable from the network at all; and even with the credential, the write toggle and rate limit still apply to traffic through the server. Two independent things must fail.

**c) Per-role separation is structural, not conventional.** Four processes with four accounts cannot accidentally act as each other — the isolation is enforced by the OS and by Odoo's own user model. In the addon, "which role is this" is just which key the client happened to send; one leaked admin key collapses every role at once. And the reader gets per-role *resource* isolation for free: a runaway agent burns its own process, not the ERP's HTTP workers.

**d) Operational isolation.** The addon's tool calls contend with human web traffic for Odoo workers and are subject to `limit_time_real`. The reader's server can be slow, restarted, profiled, rate-limited or killed without touching Odoo availability. For a demo-facing or latency-sensitive system this matters.

**e) Deployment / upgrade coupling.** The addon pins to Odoo internals (`JsonRPCDispatcher`, `request.dispatcher`, `_auth_method_bearer`, `http.py` line numbers in comments). Odoo major upgrades break it until someone ports it — and there is exactly one maintainer doing those ports, with the 19.0 port living on an unreleased branch. The reader's server talks XML-RPC, the most stable interface Odoo has, unchanged for a decade. **Concretely for this reader: on Odoo 19.0 Community the addon is not an Apps Store option at all** — only the `origin/19.0` branch has a 19.0.1.0.0 manifest, last touched 2026-05-09, with a 3-addon subset and none of the May security fixes from 18.0.

**f) Security review.** Reviewing the reader's server means reading one `odoo()` function, one whitelist, one toggle, 35 tool bodies — a closed, enumerable surface. Reviewing the addon means reasoning about the Odoo ACL matrix of every model any tool can touch, plus `ir.rule` interactions, plus multi-company, plus which tool packs are installed, plus the six `sudo()` calls hiding inside `llm_tool_website` / `llm_tool_knowledge`. The addon's `odoo_record_*` + `odoo_model_method_executor` family makes the reachable surface *the entire ORM*, which means the answer to "what can the AI do?" is "everything this user can do" — true, honest, and unbounded. The external design answers with a list of 35 items. For a security review, an enumerable surface beats a correct-but-unbounded one.

**g) Human confirmation.** The reader's LangGraph interrupt is a real gate that blocks execution. The addon's `requires_user_consent` is a prompt sentence the model may ignore, and it is not even wired into the MCP path. These are not comparable mechanisms.

### Honest summary

The two designs optimise different variables and both choices are defensible. **The in-Odoo addon optimises for correctness-of-permissions and per-person attribution at near-zero operational cost; the external multi-account design optimises for containment, enumerability and out-of-band control.** If the population is many humans each driving their own AI client against data they already own, the addon is the better answer and the reader's design would be over-engineered. If the population is a handful of autonomous agents acting on behalf of the business, where the question is "what is the worst thing this can do and can I prove what it did", the external design is the better answer — and the reader's specific additions (fail-closed global write toggle, hash-chained audit, argument fingerprints) are precisely the things the in-Odoo design cannot place beyond the agent's own reach. **The reader's weakest point relative to the addon is attribution** (per-role, not per-person) and that is fixable without changing architecture.

---

## 13. Transferable to the reader's server

### Worth adopting (bounded, with reasoning)

1. **Emit MCP `ToolAnnotations` on all 35 tools** — `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` (`llm_tool/models/llm_tool.py:44-63`, serialised at `:508-535`). Cheap (a decorator kwarg per tool) and it turns "which calls need the LangGraph interrupt" from a hard-coded name list into metadata the tool itself carries. Adopt the addon's **`destructive_hint` default of `True`** (`:54-58`) so an unannotated new tool is treated as dangerous — same fail-closed instinct as the write toggle.
2. **Record the acting human in the audit log, not just the role.** This is the addon's genuine advantage reframed for the reader's architecture. The agent layer already knows who is asking; pass that identity into the MCP call (a tool argument or a request header consumed by the `odoo()` choke point) and write it into the hash-chained audit record alongside the role. The reader cannot make Odoo's `create_uid` say the human's name without abandoning the multi-account design — but the audit log can, and that closes most of the gap. Optionally also stamp it into the Odoo write itself where the model supports a free-text ref or chatter note.
3. **Generate input schemas from Python type hints via the MCP SDK's own `func_metadata`** (`llm_tool/models/llm_tool.py:186-194`) and make missing hints a hard error at registration (`llm_tool/decorators.py:149-181`). If any of the 35 tools still carry hand-maintained JSON schemas, this removes a whole class of silent drift. FastMCP already does most of this; the addon's contribution is the *enforcement* — refusing to register a tool whose signature is under-specified.
4. **Explicit protocol-version negotiation with a configured supported-version list and a 400 on mismatch** (`mcp_json_dispatcher.py:216-239`, plus the `latest_protocol_version` / `supported_protocol_versions` fields). Turns a future MCP spec bump from a silent behavioural change into a loud rejection. Small, and it pairs well with the reader's existing fail-closed style.
5. **A `/health` endpoint returning server name + version** (`mcp_controller.py:228-238`) — with a caveat: keep it on the 127.0.0.1 binding and do not include anything beyond a liveness signal and a build id.
6. **The "generate a ready-to-paste client config" idea** (`llm_mcp_server/models/llm_mcp_server_config.py:18-47`, `wizards/mcp_key_wizard.py:34-50`). Not the code, the pattern: one command that prints the exact client-side config for each role's endpoint. Eliminates a recurring class of setup error and is ~30 lines of Jinja.
7. **Read their failure as a checklist item**: the tool-enumeration hole (`tools/list` unauthenticated from 2025-10-23 to 2026-05-26) is a reminder to verify that *every* MCP method on the reader's server — including `initialize`, `ping`, `resources/*` and any future `prompts/*` — is behind the same authorization as `tools/call`, not just the obvious one. Worth a single explicit test.

### Not worth copying, and why

1. **The generic-CRUD tool family** (`odoo_record_retriever/creator/updater/unlinker`) and above all **`odoo_model_method_executor` with `allow_private`**. They are the direct negation of the reader's method whitelist and 35 domain tools. Adding even one of them would make the whitelist decorative. The reader's design is strictly safer here and should not be diluted "for flexibility".
2. **`requires_user_consent` / `llm.tool.consent.config`** — consent as a system-message sentence (`llm_tool/models/llm_tool_consent_config.py:23-28`). It is unenforced even inside the addon's own MCP path. The reader already has a real interrupt; replacing or supplementing it with a prompt instruction would be a downgrade dressed as a feature. If anything, this is the cautionary tale: a field named `requires_user_consent` that four tools set and nothing checks is worse than no field, because reviewers assume it does something.
3. **The `llm.mcp.session` state machine backed by DB rows.** It exists only because a stateless Odoo controller has no process memory; FastMCP already holds session state in-process. Copying it would add a table, an unauthenticated write path and a GC problem (which the addon has and has not solved — no cron) in exchange for nothing.
4. **The blanket `except Exception → isError=True, HTTP 200, no rollback`** (`llm_mcp_server/models/llm_tool.py:55-60`). The reader should keep failures loud and ensure a failed write path does not leave partial state; and should *not* forward raw exception text to the model, which can leak internal names.
5. **`str(result)` as tool output.** Return JSON. The addon hands the model Python reprs.
6. **`cors="*"` + `csrf=False` on the MCP endpoint.** Irrelevant and harmful for a 127.0.0.1-bound server; the reader's loopback binding is a stronger control than anything CORS provides.
7. **Migrating into Odoo.** Beyond the architectural argument in item 12, three concrete blockers for this reader: (i) Odoo 19.0 Community is served only by an unreleased branch, three weeks behind 18.0's security fixes; (ii) the global write toggle, rate limit and hash-chained audit would move *inside* the blast radius of the agent's own credential; (iii) MCP traffic would start competing with the demo's Odoo HTTP workers, which the reader's own measurements (localhost/IPv6 penalty, Odoo call latency) show is already a sensitive budget.

---

## Gaps and caveats

- The repository clone was **shallow (`--depth 50` on `18.0`)**, so the per-month commit histogram for `llm_mcp_server` (2025-12 → 2026-05) covers only the fetched window, not the module's entire history. The module's first release date (2025-10-23) comes from `changelog.rst`, not from git.
- I did **not run** Odoo or the module. The transaction-commit-on-swallowed-exception behaviour (item 5) is inferred from Odoo's standard request lifecycle plus the verified absence of any savepoint/rollback in the module; it was not observed empirically.
- The Apps Store page did not expose a last-updated date; the "628 downloads" figure and the security claims were read from the 18.0 store page on 2026-09-19.
- GitHub reports `license: null` at the repo level while every manifest declares LGPL-3. I did not find a root LICENSE file; treat the repo-level licensing as per-module.
- I did not audit the 44 `llm_tool_mis_builder` or 18 `llm_tool_account` tool bodies individually for `sudo()` beyond the grep (which found none in those two packs — the six hits were all in `llm_tool_website` and `llm_tool_knowledge`).
- Issue #255 (which motivated the May 2026 security fixes) was referenced in the commit message but I did not read the issue thread itself.
