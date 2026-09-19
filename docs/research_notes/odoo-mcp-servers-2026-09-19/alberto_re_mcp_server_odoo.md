# alberto-re/mcp-server-odoo — architecture, flow, extensibility

**Repo:** https://github.com/alberto-re/mcp-server-odoo
**Investigated from:** full read-only clone at commit `c207554` (HEAD of `main`), 2026-09-19.
**Headline:** a ~560-LOC, read-only, single-author hobby server. Its one genuinely distinctive idea is a runtime external-tool loader driven by two env vars (`TOOLS_TO_REGISTER` + `EXT_DIRECTORIES`). That loader is, in its current form, **less safe than a static per-domain module split** — it `exec_module()`s an arbitrary `tools.py` and, with the documented default configuration, it scans the process's **current working directory**.

---

## 1. Repo facts

| Fact | Value | Evidence |
|---|---|---|
| Language | Python, `requires-python = ">=3.10"`, `.python-version` = 3.10 | `pyproject.toml:6`, `.python-version:1` |
| MCP framework | Official Python SDK's **FastMCP** — `from mcp.server.fastmcp import FastMCP` | `src/mcp_server_odoo/server.py:10` |
| SDK version | `mcp[cli]>=1.9.2`, locked at **1.9.2** (released 2025-05-29) | `pyproject.toml:19`; `uv.lock:175-176` |
| LOC | **559 lines** of Python across 9 files (`config.py` 120, `tools/common.py` 134, `server.py` 102, `odoo_client.py` 98, `tools/v16|v17|v18.py` 33 each, `__init__.py` 6, `tools/__init__.py` 0) | `wc -l` over `src/**/*.py` |
| License | MIT, © 2025 Alberto Re | `LICENSE:1-3`; `pyproject.toml:10` |
| Version | `0.1.0`, classifier `Development Status :: 4 - Beta` | `pyproject.toml:3,12` |
| Commits | **14 total**, first `0cd2e36` 2025-06-15 "Initial release", last `c207554` 2025-06-28 "Minor Odoo client refactoring" | `git rev-list --count HEAD`, `git log` |
| Release tags | **None** (`git tag -l` empty). No PyPI publish — install is `uv tool install --from git+https://…` | `README.md:39` |
| Activity | Repo created 2025-06-04; `pushed_at` **2025-06-28**. **~15 months dormant** as of 2026-09-19 | GitHub API `/repos/alberto-re/mcp-server-odoo` |
| Stars / forks / watchers | **2 stars, 0 forks, 0 subscribers** | GitHub API |
| Issues / PRs | **Zero**, open or closed (`/issues?state=all` returns `[]`) | GitHub API |
| Tests | **None.** No `tests/`, no `test_*.py`, no pytest dependency anywhere | full file listing; `pyproject.toml` dep groups |
| CI | `.github/workflows/ci.yml` — on push to `main` only; runs `uv sync --locked` then **`pre-commit run --all-files`** and nothing else | `.github/workflows/ci.yml:1-19` |
| Lint/type gate | pre-commit: `end-of-file-fixer`, `trailing-whitespace`, `check-docstring-first`, `ruff-check --fix`, `ruff-format`, `black`, `mypy`. Ruff rules `["E","F","I","C90"]` | `.pre-commit-config.yaml`; `pyproject.toml:34-35` |

> The project self-describes its maturity honestly: *"**Beware: the project is in very early development. Expect rough edges.**"* (`README.md:5`).

**No GitHub issues or PRs exist**, so item 10 of the rubric ("stated rationale from issues") can only be sourced from commit messages and code comments.

---

## 2. Architecture

Five modules, strictly layered, dependency arrows all pointing one way (no cycles):

```
__init__.py  (main() entry point)
     │
     ▼
server.py    OdooMCP  ── FastMCP instance, lifespan, tool registration loop
     │  ├──► config.py      (module-level singleton `config = Config()`)
     │  └──► odoo_client.py (OdooClient, XML-RPC)
     ▼
tools/vNN.py  ──► tools/common.py ──► (reaches back into OdooClient via ctx)
```

**Responsibilities**

- `src/mcp_server_odoo/__init__.py` (6 lines) — the console-script entry point declared as `mcp-server-odoo = "mcp_server_odoo:main"` (`pyproject.toml:28`):
  ```python
  def main():
      mcp = OdooMCP()
      mcp.run()
  ```
- `src/mcp_server_odoo/config.py` — all env-var reading in one class, with `load_dotenv(override=True)` at **import time** (`config.py:15`). Note `override=True`: a `.env` file on disk **beats real environment variables**, which is the opposite of the usual precedence and can silently override a Claude Desktop `env:` block.
- `src/mcp_server_odoo/server.py` — `OdooMCP` wraps `FastMCP`; owns the lifespan and `_register_capabilities()` (the extensibility mechanism, §9).
- `src/mcp_server_odoo/odoo_client.py` — the **only** place that talks to Odoo. Three methods: `login()`, `_search()`, `_read()`, all funnelling through one private `_execute_kw()`.
- `src/mcp_server_odoo/tools/common.py` — the four real tool implementations.
- `src/mcp_server_odoo/tools/v16.py`, `v17.py`, `v18.py` — thin per-version shims (§3).

**Entry point & wiring.** `Config()` is instantiated at **module import** (`server.py:18`), so a missing `ODOO_DATABASE` raises `ConfigError` during import, before `main()` runs. Logging is configured from that same module-level config (`server.py:20-21`).

**Connection lifecycle** is a FastMCP lifespan that yields a dataclass:
```python
@dataclass
class AppContext:
    client: OdooClient

@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    try:
        odoo_client = OdooClient(config.xmlrpc_url, config.odoo_username,
                                 config.odoo_password, config.odoo_database)
        odoo_client.login()
        logger.info(f"Connected successfully to Odoo at {config.xmlrpc_url}")
        yield AppContext(client=odoo_client)
    except Exception as ex:
        logger.error(f"Failed to connect to Odoo {ex}")
        raise
```
(`server.py:29-43`.) This was deliberately changed: commit `5f582b3` 2025-06-23 *"Move client login into context manager"* — at `0cd2e36` the client was constructed and `login()`ed at **module scope** (`git show 0cd2e36:src/mcp_server_odoo/server.py:23-26`), meaning a dead Odoo crashed the process on import. Now failure happens at server start and is logged first.

**How built-in tools get registered.** There is **no decorator and no self-registration on import**. Nothing uses `@mcp.tool()`. Instead, `OdooMCP.__init__` calls `_register_capabilities()`, which loops over the comma-split `TOOLS_TO_REGISTER` string and does `getattr(module, tool)` → `self._mcp.add_tool(...)` (`server.py:60-98`). **A tool that exists in the codebase but is not named in `TOOLS_TO_REGISTER` is simply never exposed.** This is a pull model (config names what it wants) rather than the push model (module registers itself on import) used by the reader's server.

The dedicated docstring states the intent:
> *"Register capabilities (tools, resources, prompts, ...) available at runtime. At the moment only tools are supported… Tools to expose must be configured from the user by setting the TOOLS_TO_REGISTER environment variable."* — `server.py:52-59`

**No MCP resources and no MCP prompts are implemented** — only tools.

---

## 3. Odoo connection layer

- **Protocol: 100% XML-RPC**, via Python's stdlib `xmlrpc.client`. Two proxies built in the constructor (`odoo_client.py:22-23`):
  ```python
  self._common = xmlrpc.client.ServerProxy(f"{self._url}/2/common")
  self._models = xmlrpc.client.ServerProxy(f"{self._url}/2/object")
  ```
  with `self._xmlrpc_url = f"{self._odoo_base_url}/xmlrpc"` (`config.py:70`) → the standard `http://host:8069/xmlrpc/2/object`. No JSON-RPC, no ORM, no direct SQL.
- **Auth: username + password/API-key**, indistinguishable at the code level. `README.md:26` documents `ODOO_PASSWORD` as *"Password or API Key for authentication"* — which is accurate, because Odoo's `authenticate()` accepts either in the same slot. The code has **no separate API-key path and no way to prefer one**.
- **uid caching:** `login()` calls `common.authenticate(db, user, pw, {})` once and caches the result in `self._uid` (`odoo_client.py:32-38`). `login()` is called exactly once, from the lifespan. `_execute_kw` then re-sends `self._db, self._uid, self._password` on **every** call (`odoo_client.py:44-52`) — i.e. the password is transmitted with every single RPC, which is how Odoo's XML-RPC API works, but it means the credential is on the wire N times per session.
- **Connection reuse:** the two `ServerProxy` objects live for the whole process. `xmlrpc.client` opens a new HTTP connection per call unless a custom transport is supplied; none is. **No connection pooling, no keep-alive tuning.**
- **Retry: none.** No re-login on an expired session, no backoff, no circuit breaker. If `authenticate` succeeds at boot and the Odoo session later dies, every subsequent tool call fails.
- **Timeouts: none.** `ServerProxy` is constructed with no `transport=` argument, so there is **no socket timeout** — a hung Odoo hangs the MCP tool call indefinitely.
- **Error mapping: essentially none.** The only mapped error is auth:
  ```python
  if not uid:
      raise ConnectionError("Authentication failed. Are ODOO_DATABASE, ODOO_USERNAME and "
                            "ODOO_PASSWORD set correctly?")
  ```
  (`odoo_client.py:33-37`, improved by commit `8ae297f` "Better error message"). Commit `00f1118` *"Remove unnecessary try/except block"* explicitly **removed** a `try/except ... raise ex` wrapper. Everything else — `xmlrpc.client.Fault` for an access-rights error, a bad field name, an invalid model — propagates raw out of the tool coroutine and is turned into a generic MCP tool error by FastMCP, with the **raw Odoo traceback text reaching the LLM**.

### What `ODOO_VERSION` actually changes — **nothing** (answer to key question 3)

`ODOO_VERSION` is validated to 16–18 and then used only to pick a module name:
```python
if not 16 <= int(self._odoo_version) <= 18:
    raise NotImplementedError(f"The specified version of Odoo ('{self._odoo_version}') is not supported")
```
(`config.py:48-52`)
```python
module_path = f"mcp_server_odoo.tools.v{config.odoo_version}"
module = importlib.import_module(module_path)
```
(`server.py:85-86`)

**But `v16.py`, `v17.py` and `v18.py` are byte-identical** — `diff` between each pair returns exit code 0 with no output. All three contain the same four functions, each a one-line `return await common.X(...)` plus a `X.__doc__ = common.X.__doc__` assignment. Example (`tools/v18.py:6-12`):
```python
async def search_partners(ctx: Context, name: str = "", email: str = "", limit: int = 100) -> str:
    return await common.search_partners(ctx, name, email, limit)

search_partners.__doc__ = common.search_partners.__doc__
```

So **`ODOO_VERSION` is today purely structural scaffolding — informational in effect.** It is an *architectural affordance* for future per-version field/domain divergence (which is real: e.g. `res.partner.mobile` and `sale.order` state semantics do drift between majors), but no divergence has been written yet. Two consequences:
- Setting `ODOO_VERSION=19` (the reader's version) **hard-fails at startup** with `NotImplementedError` even though nothing version-specific exists.
- Non-numeric `ODOO_VERSION` raises a bare `ValueError` from `int()`, not the project's `ConfigError` — inconsistent error handling (`config.py:48`).

The `__doc__` re-assignment trick exists because FastMCP derives the tool description from `fn.__doc__`; without it the shim would register a tool with an **empty description** (see `Tool.from_function`: `func_doc = description or fn.__doc__ or ""`). It's a working but fragile pattern — the docstrings are also duplicated in `common.py` only, so `check-docstring-first` in pre-commit doesn't protect the shims.

---

## 4. Tool design

**Exactly four built-in tools**, all in `tools/common.py`, all read-only searches, all returning `json.dumps(records, indent=2)`.

| Tool | Odoo model | Hard-coded domain | Returned fields | Args |
|---|---|---|---|---|
| `search_partners` | `res.partner` | built from args (see below) | `name, phone, mobile, email, website` | `name=""`, `email=""`, `limit=100` |
| `search_sales_orders` | `sale.order` | `[["state","in",["sale"]]]` | `name, date_order, payment_term_id, partner_id` | `limit=100` |
| `search_quotations` | `sale.order` | `[["state","in",["draft","draft_sent"]]]` | `name, state, date_order, payment_term_id, partner_id` | `limit=100` |
| `search_customer_invoices` | `account.move` | `[["move_type","=","out_invoice"],["state","=","posted"]]` | `name, partner_id, invoice_date, invoice_date_due, currency_id, amount_untaxed, amount_tax, amount_total` | `limit=100` |

`search_customer_invoices` was added later (commit `9d7f5cb`, 2025-06-18) — and is **still missing from the `DEFAULT_TOOLS_TO_REGISTER` constant** (`config.py:11` lists only three), though `.env.example:9` and the README examples list all four. So a user who omits `TOOLS_TO_REGISTER` silently gets three tools.

**Domain construction.** Only `search_partners` builds a domain from arguments, and it does so by naive append — which produces an **implicit AND**, never an OR:
```python
domain = []
if name:
    domain.append(["name", "ilike", name])
if email:
    domain.append(["email", "ilike", email])
```
(`common.py:43-47`.) The docstring says *"filtered by name **or** email"* (`common.py:10`) — the code implements AND. **Docs contradict code.** The other three tools accept no filter arguments at all: no date range, no partner filter, no state override, no text search. To answer "invoices for Acme in Q3" the LLM must pull up to 100 invoices and filter them itself.

**The domain is double-wrapped**, `[domain]`, because `execute_kw`'s positional `args` for `search` must be `[domain]`:
```python
ids = ctx.request_context.lifespan_context.client._search(model, [domain], limit)
partners = ctx.request_context.lifespan_context.client._read(model, ids, fields)
```
(`common.py:49-50`.) Note the tools reach through **three levels of attribute access into the lifespan context and then call two underscore-private methods** of `OdooClient`. There is no service/repository facade; the "private" naming is decorative.

**Two RPCs per tool call** — `search` then `read` — deliberately, per commit `bee38e2` *"Split odoo_client.search_records method. Method has been splitted into search() and read() to make logic more easily reusable."* Odoo's `search_read` would do it in one round trip; the author traded a round trip for reusability. Worth noting given the reader's measured ~2 s/4.1 s per-Odoo-call latency penalties.

**Output formatting for the LLM.** Raw `json.dumps(records, indent=2)` of Odoo's `read()` output. That means:
- `indent=2` inflates token count for no model benefit.
- Many2one fields come back as Odoo's `[id, "Display Name"]` tuples — e.g. `partner_id: [7, "Acme Corp"]` — which is passed through **unexplained**. The docstrings never tell the model what that pair means.
- `id` is **not** in any field list, but Odoo's `read()` always returns `id` anyway, so the model gets an id it was never told about.
- Odoo returns `False` (not `null`) for empty char fields; the docstring example shows `"mobile": null` (`common.py:36`), which is what `json.dumps` produces for `None` — Odoo actually yields `false`. **Example output in the docstring does not match real Odoo output.**
- No truncation, no field-level redaction, no token budgeting.

**Pagination: none.** There is only `limit` (default 100). No `offset`, no cursor, no total count, no "more results exist" signal. The LLM cannot page past the first 100 records and is **not told that results were truncated** — a silent-wrong-answer hazard on any tenant with >100 quotations.

Docstring quality is otherwise the strongest part of the repo: each tool has a full Args/Returns block and `search_partners` has an "Example Output" section — genuinely good LLM-facing documentation, of the kind the `mcp-builder` criteria ask for. Two of the four docstrings, however, are **copy-paste damaged**: `search_sales_orders` and `search_customer_invoices` both say *"filtered by name or email"* (`common.py:56`, `common.py:102`) when neither accepts any filter argument. That is misinformation fed directly to the model.

---

## 5. Write path — **there is none**

**There are zero write tools.** Verified exhaustively:
- The only Odoo methods reachable are `authenticate`, `search` and `read`. `_execute_kw` takes `method` as a parameter, but its only two callers pass the literals `"search"` (`odoo_client.py:64`) and `"read"` (`odoo_client.py:86`).
- No `create`, `write`, `unlink`, `action_confirm`, `button_*`, `message_post` anywhere in `src/`.
- No confirmation flow, no dry-run, no idempotency key, no `ToolAnnotations` (FastMCP 1.9.2 supports `annotations=ToolAnnotations(readOnlyHint=True)` on `add_tool`; this repo never passes it, so clients get **no machine-readable read-only hint** either).

**What that implies.** Read-only-by-construction is the strongest possible write safety story, and it removes the entire class of problems the reader has solved with a global toggle, a method whitelist and a hash-chained audit log. But it is *not* a designed safety control — it is an absence of features in a 14-commit project, and the architecture has **no seam to add writes safely**: `_execute_kw` is an unguarded passthrough that accepts any `method` string, so the first write tool added (or the first external `tools.py` — see §9) can call any model method with no gate whatsoever. The read-only property is a property of *what has been written so far*, not an enforced invariant.

---

## 6. Permission / security model

- **Odoo auth:** one set of credentials from env, one `uid`, for the whole process. **No per-role separation, no per-user impersonation.** Whatever the configured Odoo user can do, every MCP client can do. (Contrast the reader's 3–4 isolated processes with dedicated accounts.)
- **Allow/deny lists: none.** No model allowlist, no method whitelist, no field denylist, no record-count cap beyond `limit`. The only reason arbitrary models aren't reachable is that no tool exposes a `model` parameter — a convention, not a control.
- **Input sanitization: none, and none needed for the built-ins.** `name` and `email` go into a `["name","ilike",value]` triple; XML-RPC marshals them as strings and Odoo parameterizes the SQL, so there is no injection vector through the built-in tools. `limit` is typed `int` and validated by FastMCP's pydantic schema, but is **unbounded** — an LLM can pass `limit=10_000_000` and the server will happily `read()` the whole table into memory and then into the model's context. No max.
- **Credential filtering on read results: none.** Whatever fields the tool lists are returned verbatim. (Same known gap as the reader's server; here the hard-coded field lists happen to be benign.)
- **Transport security — the weak point.** `TRANSPORT_PROTOCOL` accepts `stdio | sse | streamable-http` (`config.py:60-64`, enforced by commit `22e9041`). Default is `stdio` (changed by `cd8c5d6` *"Default transport protocol to stdio"*), default `HOST` is `127.0.0.1` (`config.py:12`) — both safe defaults. **But for `sse`/`streamable-http` there is no client authentication of any kind**: no bearer token, no API key, no OAuth, no TLS, no origin check. FastMCP 1.9.2's `sse_app()` is mounted as-is. And the README actively instructs users to widen it:
  > *"When running inside a container remember to use an HTTP based transport protocol … and to make the server listen to all interfaces (i.e. set `HOST` to `0.0.0.0`)."* — `README.md:66-67`

  Following the README therefore yields **an unauthenticated HTTP endpoint on all interfaces that proxies a privileged Odoo account** (the `.env.example` and every README example use `ODOO_USERNAME=admin`). The `docker run -p 8000:8000` command in `README.md:63` publishes it to the host.
- **Shared lifespan under HTTP.** The lifespan runs **once per process**, so every concurrent HTTP client shares the same `OdooClient` and the same `uid`. There is no per-session context and no way to attribute a call to a caller.
- **Container hardening:** `Dockerfile` is 6 lines, `ADD . /mcp`, runs as **root**, no healthcheck, no non-root user. `.dockerignore` excludes `.*` so `.env` is not baked into the image (good, probably incidental).

---

## 7. Audit / logging / observability

Everything is stdlib `logging`, configured once from `LOG_LEVEL`/`LOG_FORMAT` (`config.py:8-9`, `server.py:20`).

What is logged:
- Registration decisions, at INFO: `f"registering tool '{tool}' (from {file_path})"` / `(from {module_path})` (`server.py:77,89`) — **this is the only visibility into which code a tool actually came from**, and it is INFO-level, off by default in many setups but on by default here.
- A warning when a requested tool can't be found (`server.py:95-98`).
- Connect success/failure (`server.py:39,42`).
- Per-RPC: `"Executing '%s' method on model '%s'"` — method + model only (`odoo_client.py:65-69`, `87-91`).

What is **not** logged, and matters:
- **The domain and the limit were deliberately removed from the log.** Commit `bee38e2` changed `"Executing method %s with model=%s, domain=%s, limit=%s"` → `"Executing '%s' method on model '%s'"`, dropping the `domain` and `limit` arguments. So there is **no record of what was actually queried** — no argument fingerprint, nothing equivalent to the reader's event log.
- No record count, no latency, no caller identity, no request id, no correlation between an MCP tool call and the resulting RPCs.
- **No audit log, no tamper evidence, no verifier.** (Moot for reads, but there is no scaffolding for writes either.)
- No metrics, no tracing, no health endpoint.

---

## 8. Testing strategy

**There is no testing strategy.** Zero test files, zero test framework in dependencies, and CI runs only `pre-commit` (format + ruff + mypy). The quality gate is entirely static.

The one testing-adjacent artifact is `dev/docker-compose.yml`, added by commit `97c49a4` *"Include Docker Compose file for development"*, which spins up odoo16/17/18 + postgres:14 — clear evidence the author intended to verify against all three supported versions manually. **It is broken as written:** Odoo listens on 8069 inside the container, but the compose file maps `"8070:8070"` for odoo17 and `"8071:8071"` for odoo18 (`dev/docker-compose.yml:12-13,18-19`) instead of `8070:8069` / `8071:8069`, so only the odoo16 service is reachable. Nothing in CI would ever catch that, because nothing runs it.

Given the reader's repeated hard-won lesson that **green tests routinely miss defects that only live verification catches**, the relevant observation here is the inverse: this repo has neither, so every behavioral claim in it (including `ODOO_VERSION` support for 16 and 17) is **unverified**.

---

## 9. Extensibility — `TOOLS_TO_REGISTER` + `EXT_DIRECTORIES` (the key item)

### The whole mechanism, in one function

`OdooMCP._register_capabilities()` (`server.py:51-98`) is the entire extensibility system. Full trace:

```python
for tool in config.tools_to_register.split(","):          # (1)
    tool_registered = False
    for ext_dir in config.ext_directories.split(","):     # (2)
        file_path = Path(ext_dir) / "tools.py"            # (3)  <-- fixed filename
        if not file_path.is_file():
            continue
        module_name = f"{file_path.stem}_{hash(file_path)}"   # (4)
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Invalid source file at '%s'", file_path)   # (5) bug
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module                 # (6)
        spec.loader.exec_module(module)                   # (7)  <-- ARBITRARY CODE RUNS
        try:
            self._mcp.add_tool(getattr(module, tool))     # (8)
            logger.info(f"registering tool '{tool}' (from {file_path})")
            tool_registered = True
        except AttributeError:
            pass

    if tool_registered:
        continue                                          # (9) ext wins over built-in

    module_path = f"mcp_server_odoo.tools.v{config.odoo_version}"   # (10) fallback
    module = importlib.import_module(module_path)
    try:
        self._mcp.add_tool(getattr(module, tool))
        tool_registered = True
    except AttributeError:
        pass

    if not tool_registered:
        logger.warning(f"Tool '{tool}' not found. Check spelling and "
                       f"EXT_DIRECTORIES ({config.ext_directories})")
```

Step by step:

1. **`TOOLS_TO_REGISTER`** is a bare comma-split string — the *outer* loop. It is a name allowlist: only names appearing here are ever registered. There is **no `.strip()`**, so `"search_partners, search_quotations"` (with the space a human naturally types) makes the second lookup `getattr(module, " search_quotations")`, which fails and logs only a warning — verified: `'a, b'.split(',')` → `['a', ' b']`. **Silent partial failure on a formatting nit.**
2. **`EXT_DIRECTORIES`** is the *inner* loop, also a bare comma-split.
3. Each directory is probed for **exactly one hard-coded filename, `tools.py`**. No recursion, no globbing, no package support, no `__init__.py`, no manifest, no version/compat declaration.
4. Module name is `tools_<hash(Path)>`. `Path.__hash__` derives from the string hash, which under Python's default hash randomization **differs between processes** — harmless here (the name is only a `sys.modules` key within one run) but it means the same file gets a different module identity on every restart, and it defeats any caching or debugging by module name.
5. **Bug:** `RuntimeError("Invalid source file at '%s'", file_path)` uses `%`-style args on an exception constructor, which does not interpolate; the exception carries a 2-tuple, so the message reads `("Invalid source file at '%s'", WindowsPath(...))`.
6. The module is inserted into `sys.modules` **before** execution — the correct importlib idiom (it lets the module import itself / handle circular refs), but it also means the external module is permanently resident and reachable.
7. **`spec.loader.exec_module(module)` executes the entire file at import time.** Any top-level statement in an external `tools.py` runs with the full privileges of the MCP server process. This is plain arbitrary code execution by design.
8. `getattr(module, tool)` then `add_tool`. **No validation whatsoever**: not checked to be callable, not checked to be async, not checked to take a `Context`, not checked to be a function at all. If the attribute is a non-callable, `Tool.from_function` raises somewhere other than `AttributeError` and the server **crashes at startup** rather than warning.
9. The `tool_registered` flag makes **external definitions shadow built-ins**: if any ext dir supplies `search_partners`, the built-in is never consulted. So `EXT_DIRECTORIES` is an **override mechanism, not just an addition mechanism** — an external file can silently replace a shipped tool of the same name with different behavior, and the only trace is one INFO line.
10. Fallback to `mcp_server_odoo.tools.v{ODOO_VERSION}` via ordinary `importlib.import_module`. Note the **redundant re-import inside the loop** for every tool name (cheap — `sys.modules` cached — but sloppy).

### The minimal contract for an external tool file (answer to key question 2)

The repo ships **no example** — `.dockerignore:2` excludes a directory named `ext_dir_example` that **has never existed in any commit** (`git log --all -- 'ext_dir_example*'` is empty; the string appears only in that one added line). So the contract must be reverse-engineered from `add_tool` + the built-ins. It is:

1. The file must be named exactly **`tools.py`**, directly inside a directory listed in `EXT_DIRECTORIES`.
2. It must define a **module-level attribute whose name exactly matches an entry in `TOOLS_TO_REGISTER`**. The attribute lookup key is that string.
3. The registered **MCP tool name comes from `fn.__name__`, not from the `TOOLS_TO_REGISTER` string** — `Tool.from_function` does `func_name = name or fn.__name__`, and `server.py:76` passes no `name=`. So `my_tool = some_other_function` registers under `some_other_function`'s name, and the config entry silently doesn't match what the client sees.
4. The **description is `fn.__doc__`** (`func_doc = description or fn.__doc__ or ""`) — a docstring-less external tool is exposed to the LLM with an **empty description**.
5. Parameters must be type-annotated (FastMCP builds the JSON schema from the signature via pydantic). A parameter annotated `Context` is auto-detected and **excluded from the schema** (`skip_names=[context_kwarg]`), and is how the tool reaches Odoo.
6. Sync or async both work in FastMCP 1.9.2, but every built-in is `async`.

A minimal conforming file, reconstructed from `tools/common.py`:

```python
# /your/custom/path/tools.py
import json
from mcp.server.fastmcp import Context

async def search_leads(ctx: Context, limit: int = 50) -> str:
    """Retrieve Odoo CRM leads (crm.lead).

    Args:
        limit (int): Maximum number of results.
    Returns:
        JSON list of {name, partner_id, expected_revenue}.
    """
    client = ctx.request_context.lifespan_context.client
    ids = client._search("crm.lead", [[["type", "=", "lead"]]], limit)
    return json.dumps(client._read("crm.lead", ids, ["name", "partner_id", "expected_revenue"]), indent=2)
```
…with `TOOLS_TO_REGISTER=search_leads` and `EXT_DIRECTORIES=/your/custom/path`. **Note what this contract forces:** the external author must reach into `ctx.request_context.lifespan_context.client` and call the **private** `_search`/`_read`. The extension API *is* the private API — there is no stable public surface, so any refactor of `OdooClient` (and there has already been one, `bee38e2`) silently breaks every external tool.

### Name collisions

Two collision cases, handled differently and neither well:

- **External vs built-in:** external wins, by the `tool_registered` / `continue` flag (`server.py:82-83`). Intentional, undocumented.
- **External vs external (two ext dirs both defining the tool):** `add_tool` is called twice. Per the SDK, the **first one wins**:
  ```python
  existing = self._tools.get(tool.name)
  if existing:
      if self.warn_on_duplicate_tools:
          logger.warning(f"Tool already exists: {tool.name}")
      return existing
  ```
  (`mcp/server/fastmcp/tools/tool_manager.py`, v1.9.2.) Crucially, the repo's own code sets `tool_registered = True` and logs `"registering tool 'X' (from <second path>)"` **for the shadowed second file too**, because `add_tool` returns normally rather than raising. So **the INFO log actively lies about which file the live tool came from** when two ext dirs collide. Worse: even when a collision occurs, *all* colliding `tools.py` files have already been `exec_module`'d — their side effects run regardless of who wins the name.

### Validation, sandboxing, path normalization — **none of any kind** (answer to key question 1)

`importlib` is used (`spec_from_file_location` + `exec_module`), not `exec()` on a string — that is the better of the two loose options, but every safety property one would want around it is absent:

| Control | Present? |
|---|---|
| Path normalization (`resolve()`, `realpath`) | **No** — the raw string goes to `Path()` and to `spec_from_file_location` |
| Allowlist / root-containment check (`is_relative_to`) | **No** |
| Symlink check | **No** — a symlinked `tools.py` is followed silently (`Path.is_file()` follows symlinks) |
| Absolute-path requirement | **No** — relative paths are accepted and resolved against CWD |
| File permission / ownership check | **No** |
| Signature, checksum or manifest | **No** |
| Sandbox, subprocess, restricted globals | **No** — runs in the server process with full privileges |
| Post-load validation of the object | **No** — not even `callable()` |

**Could a malicious or mistaken path load unintended code? Yes — and the default configuration already does something surprising.**

The severe finding is the **empty-string default**. `EXT_DIRECTORIES` defaults to `""` (`config.py:69`), and `.env.example:10` ships it empty. Then:
```
''.split(',')            -> ['']
Path('') / 'tools.py'    -> Path('tools.py')        # verified
Path('tools.py').resolve() -> <process CWD>/tools.py  # verified
```
So **with no external directories configured at all, the server probes the current working directory for `tools.py` and, if one exists, executes it** — on every startup, before any tool call. The intended "off" state is not off. Whoever controls the CWD (a shared work directory, a repo the user `cd`'d into, a Docker `WORKDIR` — note the Dockerfile sets `WORKDIR /mcp` and `ADD . /mcp`, so a `tools.py` committed anywhere at the repo root would be executed) controls code in the MCP server process. This is a **classic CWD code-injection hole**, structurally the same class of bug as the path-traversal the reader already had to fix in their folder-based skill loader — but with a worse default, because it triggers without the operator opting in.

Two mitigating facts, stated plainly so the comparison is fair: (a) `EXT_DIRECTORIES` and `TOOLS_TO_REGISTER` are **operator-controlled env vars, not MCP-client-controlled inputs** — a remote LLM client cannot choose a path, so this is not remotely triggerable traversal; (b) the blast radius is "the operator's own machine, with the operator's own Odoo credentials." The realistic threat model is therefore *accidental* execution (a stray `tools.py` in the CWD, a symlinked shared directory, a `tools.py` from a cloned third-party "extension pack" that the user never read) rather than a remote attacker. But the reader's incident history — a subagent serving unmerged code via `sys.path` injection — is exactly the accidental case.

### Comparison: runtime loader vs a static per-domain module split

| Dimension | `EXT_DIRECTORIES` runtime loader | Static per-domain modules that self-register on import (reader's design) |
|---|---|---|
| Who can add a tool | Anyone who can set an env var and drop a file — **no code change, no redeploy, no review** | Only someone who can commit to the repo — passes code review, CI, tests |
| Auditability of the live tool set | Requires reading INFO logs at runtime; the log can be wrong on collision | `git log` on the module is the complete record |
| Attack surface | Arbitrary code execution at startup from a filesystem path, with a CWD-scanning default | Code executed is the code in the repo; import graph is static and greppable |
| Override / shadowing | External silently shadows built-in; no diff, no warning | Impossible — a duplicate name is a merge conflict or an import error |
| Granularity of exposure | Per-tool-name via `TOOLS_TO_REGISTER` — genuinely useful; one deployment can expose 2 tools, another 20 | Usually per-module; per-tool gating needs extra machinery |
| Per-role deployments | One process, one env var set, different tool subsets — **cheap** | Needs either conditional registration or separate processes (reader uses separate processes) |
| Stability of the extension API | **None** — extensions call private `_search`/`_read` | Internal, refactorable at will |
| Testability | External tools are outside the repo, outside CI, untested by construction | Tools live in the test suite |

**Verdict: the runtime loading mechanism as implemented is riskier than the reader's static per-domain split, and its one real benefit is separable from its risk.** The valuable half is `TOOLS_TO_REGISTER` — declarative, per-deployment, per-tool exposure control over code that already lives in the repo. That half carries essentially zero new risk. The risky half is `EXT_DIRECTORIES` — loading unreviewed code from the filesystem — and it buys "no redeploy needed," which for a server that already requires an env-var change and a restart is a very small prize.

---

## 10. Notable design decisions and stated rationale

Rationale sources are limited to commit messages and two docstrings (no issues, no PRs, no ADRs, no design doc).

- **Config-driven tool exposure instead of decorators.** Stated: *"Tools to expose must be configured from the user by setting the TOOLS_TO_REGISTER environment variable"* (`server.py:57-59`). The implicit rationale is context economy and least privilege — don't flood the model with tools a given deployment doesn't need. This aligns with the `mcp-builder` guidance that tool count and tool-description tokens are a first-order design cost.
- **"Extensible" is the project's stated headline feature** — it is the first word of the GitHub description and of `README.md:3`. The architecture is arranged around it: the version shims exist so that an external file can sit alongside per-version built-ins in the same lookup order.
- **Version shim layer with identical bodies.** No stated rationale; the structure (delegate + copy `__doc__`) only makes sense as a pre-built seam for future divergence.
- **`search`/`read` split over `search_read`.** Stated: *"to make logic more easily reusable"* (`bee38e2`). Cost: 2 RPCs per tool call.
- **Login moved into the lifespan** (`5f582b3`) — so connection failure is a server-start event, logged, instead of an import-time crash.
- **`stdio` made the default transport** (`cd8c5d6`) and `HOST` defaults to `127.0.0.1` — safe-by-default local posture, then contradicted by the README's `0.0.0.0` container instructions.
- **Transport values validated** (`22e9041`) with a `Literal` cast — a small, deliberate fail-fast-on-config improvement. Notably this is the *only* place the author added validation, and it does not extend to `EXT_DIRECTORIES`.
- **Error handling deliberately thinned** (`00f1118` "Remove unnecessary try/except block") — an explicit choice to let exceptions propagate.
- **Docstrings as the LLM contract** — long, structured Args/Returns/Example docstrings are clearly written for the model, not for developers. Best practice, executed unevenly (two are wrong).

### README claims contradicted by the code

| README says | Code says |
|---|---|
| `ODOO_VERSION` — **Required: Yes** (`README.md:27`) | Optional, `DEFAULT_ODOO_VERSION = "18"` (`config.py:6,47`) |
| `TRANSPORT_PROTOCOL` — **Required: Yes** (`README.md:29`) | Optional, defaults to `stdio` (`config.py:10,57`) |
| `TOOLS_TO_REGISTER` — **Required: Yes** (`README.md:31`) | Optional, defaults to 3 of the 4 tools (`config.py:11`) |
| `EXT_DIRECTORIES` — "No" / optional, with the implication that unset means no external loading (`README.md:32`) | Unset (`""`) still probes **`./tools.py` in the CWD** and executes it — verified |
| `search_partners` filters "by name **or** email" (`common.py:10`) | AND — both conditions appended to the same domain (`common.py:43-47`) |
| `search_sales_orders` / `search_customer_invoices` "filtered by name or email" (`common.py:56,102`) | Accept no filter arguments at all |
| `ODOO_VERSION` implies per-version behavior | `v16.py`, `v17.py`, `v18.py` are byte-identical |

---

## 11. Weaknesses and risks found in the code

Ordered roughly by severity.

1. **CWD code execution with the default config** — `EXT_DIRECTORIES=""` → `Path('')/'tools.py'` → `./tools.py` is imported and `exec_module`'d at startup (`config.py:69`, `server.py:62-74`; verified empirically). The off switch is not off.
2. **No path normalization, containment, or symlink handling on `EXT_DIRECTORIES`** (§9) — any path, absolute or relative, symlinked or not, is executed as-is.
3. **Unauthenticated HTTP transports, with the README telling users to bind `0.0.0.0`** (`README.md:66-67`) — an open proxy to a (per every example) **admin** Odoo account.
4. **`search_quotations` returns wrong results.** Domain is `[["state","in",["draft","draft_sent"]]]` (`common.py:93`), but Odoo 18's `SALE_ORDER_STATE` is `[('draft',…),('sent',…),('sale',…),('cancel',…)]` — verified against `odoo/odoo` 18.0 `addons/sale/models/sale_order.py`. **`draft_sent` is not a valid state**, so every quotation that has actually been *sent to the customer* is silently omitted. The LLM is given an incomplete list with no indication it is incomplete. Same bug in v16/v17 paths (identical code).
5. **Silent truncation at `limit`** with no total count and no "truncated" flag — the LLM will confidently answer "there are 100 open quotations."
6. **Unbounded `limit`** — no server-side cap; an LLM-chosen `limit=1000000` becomes an unbounded `read()`.
7. **No timeouts on XML-RPC** (`ServerProxy` built with no transport) — a hung Odoo hangs the tool call forever.
8. **No retry / no re-login** — a session that dies after boot never recovers without a restart.
9. **Raw exception leakage to the LLM** — Odoo `Fault` tracebacks (which can include model names, field names, and internal messages) propagate unmapped.
10. **Whitespace in `TOOLS_TO_REGISTER` silently drops tools** — no `.strip()` (`server.py:60`); verified `'a, b'.split(',')` → `['a', ' b']`.
11. **Tool-provenance log can be wrong** — on an ext-vs-ext name collision the code logs "registering … (from <path>)" for the file that was actually discarded by `add_tool` (§9).
12. **Non-callable / malformed external attribute crashes the server at startup** — only `AttributeError` is caught (`server.py:79`).
13. **`load_dotenv(override=True)`** (`config.py:15`) — a stray `.env` beats the real environment, so a Claude Desktop `env:` block can be silently overridden by a file the user forgot about.
14. **`RuntimeError("…'%s'", file_path)`** — broken message formatting (`server.py:71`).
15. **Tools depend on private methods through a 3-deep attribute chain** (`ctx.request_context.lifespan_context.client._search`) — no facade; the extension contract is the private API.
16. **`ODOO_VERSION` non-numeric → bare `ValueError`**, bypassing `ConfigError` (`config.py:48`).
17. **`DEFAULT_TOOLS_TO_REGISTER` is stale** — omits `search_customer_invoices` added three days after the default was written (`config.py:11` vs commit `9d7f5cb`).
18. **`dev/docker-compose.yml` port mappings are wrong** (`8070:8070`, `8071:8071` for containers listening on 8069) — the stated multi-version dev environment cannot actually work for 17/18.
19. **Zero tests, no runtime CI** — everything above is unverified by the project itself.
20. **Dormant**: last commit 2025-06-28, 2 stars, 0 forks, 0 issues. Treat as **a reference design, not a dependency.**

---

## 12. Transferable to the reader's server

### Worth taking (bounded, with reasoning)

1. **`TOOLS_TO_REGISTER`-style declarative per-tool exposure — but sourced from Odoo, not env.**
   The reader has 35 tools across 7 self-registering domain modules and 3–4 role-isolated processes. The idea worth stealing is *decoupling "the tool exists in the codebase" from "this deployment exposes it"* at **per-tool** granularity, not per-module. The reader already has the right storage for it: the same Odoo `ir.config_parameter` mechanism used for the global write toggle, read fail-closed. That gives per-role tool sets that a warehouse role's process and a sales role's process can differ on **without a code change or a new process**, and it directly cuts LLM context (the reader has measured context and latency costs before). Keep the reader's self-registration on import as the *definition* mechanism; add an exposure filter as the *publication* mechanism. Log every registration decision, the way `server.py:77` does — that INFO line is the single most useful thing in this repo.
   *Bound:* fail-closed on an unreadable parameter (expose nothing, or expose a hard-coded read-only core), never fail-open.

2. **`ToolAnnotations(readOnlyHint=True)` on read tools.** This repo doesn't do it, and that is a miss worth learning from in the negative: FastMCP's `add_tool`/`@tool` accepts `annotations=`, which gives MCP clients a machine-readable read/write distinction. With 35 tools and a global write toggle, the reader can annotate every read tool `readOnlyHint=True` and every write tool `destructiveHint`/`idempotentHint` — near-zero cost, improves client-side confirmation UX, and makes the reader's existing write/read split legible to the client instead of only to the server.

3. **Docstrings as the LLM contract, with a "Returns: exact field list" block and a worked Example Output.** `common.py:9-41` is the good pattern. But the reader should take the *lesson from its failures*: three of four docstrings here are wrong (two say "filtered by name or email" for tools with no filters; the example shows `null` where Odoo returns `false`). The reader already has a GATHER_CASES contract test that checks fixtures against real tool fields — **extend that pattern to assert that each tool's docstring "Returns:" field list equals the field list the code actually requests.** That is a deterministic, LLM-free check, and it closes a class of "test không đo gì" defect: docstring drift that only the model ever sees.

4. **Explicit Many2one shape documentation.** This server passes Odoo's `[id, "Name"]` tuples to the LLM with no explanation anywhere. If the reader's 35 tools do the same, one sentence in each docstring ("`partner_id` is `[id, display_name]`") is a cheap accuracy win — and relates to the reader's known masked-OR-tuple class of bug.

5. **A truncation signal.** Neither server should return exactly `limit` records and stay silent. Return `{"records": [...], "returned": N, "limit": L, "truncated": true}`. This repo's silent 100-cap is a concrete demonstration of the failure mode.

6. **Fail-fast config validation with a typed `Literal` cast** (`config.py:60-64,100-104`) — small and clean, and mypy-checked. Cheap to mirror for any of the reader's enum-ish settings.

### Explicitly **not** worth copying

1. **`EXT_DIRECTORIES` / runtime filesystem tool loading — do not copy.**
   The reader has already paid for this lesson once (folder-based dynamic skill loader → path-traversal fix). This implementation is **strictly weaker** than what the reader ended up with: no `resolve()`, no containment check, no symlink handling, no allowlist, no callable validation, and a default that scans the CWD. Against the reader's static per-domain modules it loses on every axis that matters here — auditability (`git log` vs runtime INFO logs), reviewability (CI + tests vs none), and blast radius (repo code vs any file on disk). The one advantage — "add a tool without a redeploy" — is worth very little to a server that already restarts to pick up an env change, and it is entirely obtainable via item 1 above without executing unreviewed code.
   *If it were ever wanted anyway*, the minimum bar the reader's own history implies: `Path(d).resolve()`, reject unless `is_relative_to(ALLOWED_ROOT)`, reject symlinks (`Path.is_symlink()` on every component), require absolute paths, reject empty strings **before** the `Path('')` → CWD collapse, validate the loaded object with `inspect.iscoroutinefunction` + a `Context` parameter check, and refuse silent shadowing of a built-in name.

2. **The `vNN` version-shim layer — do not copy.** Three byte-identical files is pure duplication paying for a divergence that hasn't happened. It also means `ODOO_VERSION` is a *lie the config validates* — and it would reject the reader's Odoo 19 outright. If the reader ever needs version-conditional fields, a single data table `{version: {model: [fields]}}` beats three parallel modules, and a runtime `fields_get` probe (one of the reader's known gaps) beats both.

3. **The private-method extension contract.** `ctx.request_context.lifespan_context.client._search` is the anti-pattern: the extension surface is the private surface. The reader's single choke-point `odoo()` function is a better design *precisely because* it is one named, guarded entry — keep it, and if per-domain modules ever get a public helper, make it public and versioned.

4. **Two RPCs per tool call (`search` + `read`).** Odoo's `search_read` halves the round trips. Given the reader's measured per-call Odoo latency (~2 s localhost IPv6 penalty; 4.1 s observed per Odoo call in the progress-bar work), this repo's "reusability" rationale is not a trade the reader should accept.

5. **Everything about its security posture.** No client auth on HTTP, no allow/deny lists, no rate limit, no audit trail, no argument logging (deliberately *removed*), single shared admin credential across all clients. The reader's server is ahead of this repo on every one of these. **This repo is not a source of security ideas; it is a source of one architectural idea (`TOOLS_TO_REGISTER`) and a catalogue of what happens without those controls.**

### Direct answers to the three key questions

- **Q: `importlib` on a normalized, allowlisted path, or something looser?** — `importlib.util.spec_from_file_location` + `exec_module`, i.e. the *right API*, with **zero** normalization, **zero** allowlisting, **zero** symlink or containment checking, and a default (`EXT_DIRECTORIES=""`) that silently targets `./tools.py` in the process CWD. Looser than it looks.
- **Q: minimal contract for an external tool file?** — a file literally named `tools.py` in a listed directory, defining a module-level attribute whose name matches a `TOOLS_TO_REGISTER` entry; the exposed tool name comes from `fn.__name__` and the description from `fn.__doc__`; a `Context`-annotated parameter is injected and stripped from the schema; the body must call the **private** `client._search` / `client._read`. No decorator, no registry, no base class, no manifest, no example in the repo (the `.dockerignore` reference to `ext_dir_example` points at a directory that never existed in any commit). A working example is reconstructed in §9.
- **Q: does `ODOO_VERSION` gate behavior?** — **No. Informational only in effect.** It is validated to 16–18 and used to build the module path `mcp_server_odoo.tools.v{N}`, but the three target modules are byte-identical (`diff` returns no differences). Its only real behavioral effect is the startup `NotImplementedError` for anything outside 16–18 — which would reject the reader's Odoo 19.

---

## Gaps

- **No GitHub issues, PRs, discussions, or release notes exist** (`/issues?state=all` → `[]`, `git tag -l` empty), so the author's rationale for the `EXT_DIRECTORIES` design is inferable only from the `server.py:52-59` docstring and the README's "extensible" framing — there is **no stated threat model** to evaluate against.
- **No `ext_dir_example` was ever committed**, so the external-tool contract in §9 is reverse-engineered from `add_tool` + the built-ins, not from author-supplied documentation. The reconstructed example is not executed.
- **Nothing in this repo has been run.** Per the read-only constraint, I did not start the server, the Docker image, or an Odoo instance. Behavioral claims are derived from code reading plus two empirical checks done in the scratchpad against pure-stdlib behavior (`Path('')/'tools.py'` resolution; `str.split` whitespace) and two cross-checks against upstream source (`mcp` v1.9.2 `tool_manager.py` / `base.py`; `odoo/odoo` 18.0 `sale_order.py`).
- **Odoo 16 and 17 compatibility is unverified by anyone** — the version shims are identical, there are no tests, and `dev/docker-compose.yml` is misconfigured, so the README's "16–18 supported" claim rests on nothing observable.
- **`res.partner.mobile`** is requested by `search_partners` (`common.py:48`). I did not verify whether that field survives into Odoo 19 (the reader's version); if it was merged into `phone`, copying that field list verbatim would raise. Flagged as unchecked.
