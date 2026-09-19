# ifadhf/odoo-rust-mcp — architecture, flow and logic

> Method: repo cloned read-only to
> `C:\Users\ADMIN\AppData\Local\Temp\claude\d--Youdoo\b419e890-6b02-466c-a1db-dc484e24662f\scratchpad\repos\ifadhf-odoo-rust-mcp`
> at HEAD `7cf70b9` (2026-02-12). All paths below are repo-relative. Nothing was built or run.
> GitHub metadata pulled from the REST API on 2026-09-19.
>
> **Provenance caveat, read this first:** `ifadhf/odoo-rust-mcp` is a **fork** (`fork: true`,
> `parent: rachmataditiya/odoo-rust-mcp`) created **2026-09-14**, with **0 stars, 0 forks, 0 releases,
> 0 issues** — [GitHub API](https://api.github.com/repos/ifadhf/odoo-rust-mcp). The real project is
> **`rachmataditiya/odoo-rust-mcp`** (created 2026-01-21, **14 stars**, 5 forks, 16 open issues/PRs,
> releases up to `v0.3.31` on 2026-02-12, last commit `818c0b2` on **2026-09-14**) —
> [GitHub API](https://api.github.com/repos/rachmataditiya/odoo-rust-mcp). The fork is **one commit
> behind** upstream and is missing upstream's watcher fix (see §12). Maintainer per `rust-mcp/Cargo.toml`
> `[package.metadata.deb]`: "Rachmat Aditiya <radit@arkana.co.id>". Treat "activity signals" for the
> *fork* as ~zero and read upstream's numbers as the project's real signal.

---

## 1. Repo facts

### Takeaway
Rust 2024-edition single crate (`rust-mcp` v0.3.31, ~11.5k LOC src) + a React/TS config UI (~5.4k LOC),
AGPL-3.0-only, **not** built on `rmcp` — it uses the thin abandoned `mcp_rust_sdk 0.1.1` for transport
primitives and hand-rolls all MCP method dispatch. Tests and CI are real and reasonably broad (18 test
files, ~154 test fns, 7-job CI incl. clippy `-D warnings`, tarpaulin coverage, cargo-audit).

### Cited Findings
- Language/edition/version/license — `rust-mcp/Cargo.toml`: `name = "rust-mcp"`, `version = "0.3.31"`,
  `edition = "2024"`, `license = "AGPL-3.0-only"`; `LICENSE` is the full AGPLv3 text.
- MCP framework: **`mcp_rust_sdk = "0.1.1"`** (`rust-mcp/Cargo.toml`), *not* `rmcp`. What it supplies is
  only `Transport`/`Message`/`Request`/`Response`/`ServerHandler`/`ErrorCode` and a WebSocket transport
  (`use mcp_rust_sdk::transport::websocket::WebSocketTransport;` — `rust-mcp/src/main.rs:7`). Everything
  protocol-level is hand-written: the dispatcher is a literal `match method` over `"tools/list"`,
  `"tools/call"`, `"prompts/list"`, `"resources/read"`, … in `rust-mcp/src/mcp/mod.rs:79-163`, and even
  `initialize` is re-implemented in `rust-mcp/src/mcp/runtime.rs:58-133`. A comment concedes the SDK's
  type is unusable: *"mcp_rust_sdk ServerCapabilities is currently "custom" only, so we advertise
  tools/prompts/resources in custom."* (`rust-mcp/src/mcp/mod.rs:61`).
- Other key deps (`rust-mcp/Cargo.toml`): `axum 0.8.8` (HTTP/SSE), `reqwest 0.12` (rustls, `json`,
  `cookies`), `tokio`, `notify 8` (config hot-reload), `clap 4`, `tower-http` (cors + `ServeDir`),
  `tracing`. Dev-deps: `wiremock 0.6`, `axum-test 18`, `mockall 0.14`, `tempfile`.
- LOC (`wc -l`): Rust src **11,500** total (largest: `mcp/tools.rs` 1405, `mcp/http.rs` 1223,
  `config_manager/server.rs` 852, `odoo/legacy_client.rs` 770, `main.rs` 751, `odoo/client.rs` 682,
  `cleanup/deep.rs` 655, `cleanup/database.rs` 637, `odoo/unified_client.rs` 620, `mcp/registry.rs` 599).
  Integration tests **3,877** LOC. `config-ui/src` TypeScript **5,383** LOC. Declarative
  `config/tools.json` is **606** lines.
- Activity: 271 commits in the fork's history, most recent 2026-02-12; tags run `v0.3.3 … v0.3.31`.
  Upstream published `v0.3.31` on 2026-02-12 and pushed one further commit 2026-09-14.
- Tests: `rust-mcp/tests/` has 18 files — `odoo_client_modern.rs` (21 tests), `odoo_client_legacy.rs`
  (16), `http_transport.rs` (13), `config_manager.rs` (13), `odoo_errors.rs` (11), `cleanup_database.rs`
  (11), `mcp_resources.rs` (10), plus `mcp_registry.rs`, `mcp_cache.rs`, `cursor_schema.rs`,
  `config_watcher.rs`, `mcp_smoke.rs`. `config-ui/src/__tests__/` has 8 vitest files.
- CI (`.github/workflows/ci.yml`): jobs `Build React UI`, `Cargo Check`, `UI Tests (TypeScript)`,
  `Rustfmt --check`, `Clippy … -- -D warnings`, `Test (${{ matrix.os }})` (OS matrix),
  `Code Coverage` (cargo-tarpaulin + Codecov), `Security Audit` (cargo-audit). Dependabot is live
  (`.github/dependabot.yml`; commits `d13a185`, `c634e61`, `80ff435` are dependabot bumps).
- Packaging is unusually heavy for the size: Debian `[package.metadata.deb]` + `debian/rust-mcp.service`,
  a Homebrew formula (`homebrew/Formula/rust-mcp.rb`), an apt repo (`apt-repo/`), Helm chart
  (`helm/odoo-rust-mcp/`), raw k8s manifests (`k8s/`), `docker-compose.yml`, `Cross.toml`,
  `scripts/install.sh` + `install.ps1`.

### Inferences
- Choosing `mcp_rust_sdk 0.1.1` over `rmcp` costs them the whole protocol layer: session handling,
  capability negotiation, Streamable-HTTP semantics and schema generation are all re-implemented by
  hand in this repo. That is the single biggest source of its bulk (`mcp/http.rs` alone is 1223 lines).
- The packaging surface (deb/brew/helm/k8s/apt) is larger than the security surface (§6). This is
  a distribution-first project.

### Gaps
- No `CHANGELOG.md`; rationale has to be read out of commit messages and README prose.

---

## 2. Architecture

### Takeaway
Four modules under one crate with a clean one-way dependency: `main` → `mcp` → `odoo` (+ `cleanup`,
`config_manager` as siblings). Tools are **100% declarative**: `config/tools.json` supplies name,
description, `inputSchema` and an `op` block; the binary never generates a schema from Rust types — it
passes the author's hand-written JSON schema straight through to `tools/list`, and maps arguments to a
fixed set of 22 built-in primitives via JSON Pointer.

### Cited Findings
- Module roots: `rust-mcp/src/lib.rs:5-8` = `pub mod cleanup; pub mod config_manager; pub mod mcp; pub mod odoo;`
  - `odoo/` — transport to Odoo. `client.rs` (JSON-2 modern), `legacy_client.rs` (JSON-RPC),
    `unified_client.rs` (enum + trait facade), `config.rs` (instances/env), `types.rs` (`OdooError`).
  - `mcp/` — protocol + tool machinery. `mod.rs` (method dispatch), `runtime.rs` (`initialize`/framing
    over any `Transport`), `registry.rs` (tools.json/prompts.json/server.json load + watch),
    `tools.rs` (op primitives + `OdooClientPool`), `resources.rs` (`odoo://`), `prompts.rs`,
    `cache.rs` (metadata TTL cache), `http.rs` (axum Streamable-HTTP + legacy SSE),
    `cursor_stdio.rs` (stdio transport tailored to Cursor).
  - `cleanup/` — `database.rs` + `deep.rs`, destructive maintenance routines.
  - `config_manager/` — `server.rs` (axum admin API on :3008), `manager.rs` (read/write config files),
    `watcher.rs`.
- Entry point `rust-mcp/src/main.rs:569-649`: parse CLI → init tracing (stderr-only for stdio, because
  *"stdout is reserved for JSON-RPC messages"*, `main.rs:574-583`) → `setup_user_config()` →
  `OdooClientPool::from_env()` → `Registry::from_env()` → `registry.initial_load()` →
  `registry.start_watchers()` → build `McpOdooHandler` → **spawn the config server unconditionally** →
  `match cli.transport { Stdio | Ws | Http }`.
- Dependency direction is strictly downward: `mcp/tools.rs` imports `crate::odoo::unified_client::OdooClient`
  (`tools.rs:13`); nothing in `odoo/` imports `mcp/`. `cleanup/` takes an `&OdooClient` argument
  (`tools.rs:535`), so it also sits below `mcp`.
- **Schema generation: there is none.** `Registry::list_tools()` emits the JSON verbatim:
  ```rust
  serde_json::json!({ "name": t.name, "description": t.description, "inputSchema": t.input_schema })
  ```
  (`rust-mcp/src/mcp/registry.rs:212-216`). `schemars` is in `Cargo.toml` but is not used to build tool
  schemas.
- The only schema *processing* is a Cursor-compatibility validator run at load time
  (`registry.rs:357-387`): it walks the schema and **rejects** `anyOf` / `oneOf` / `allOf` / `$ref` /
  `definitions` and union `type` arrays — *"Cursor can be picky about JSON Schema features. Reject
  schemas that likely break Cursor parsing."* A violation fails the whole reload
  (`registry.rs:254-256`).
- `op.type` → primitive mapping is a hard-coded `match` of **22 arms** in
  `rust-mcp/src/mcp/tools.rs:77-103`: `search, search_read, read, create, write, unlink, search_count,
  workflow_action, execute, generate_report, get_model_metadata, database_cleanup, deep_cleanup,
  read_group, name_search, name_get, default_get, copy, onchange, list_models, check_access,
  create_batch`; anything else → `Unknown op.type: {other}`.
- Argument binding is JSON Pointer: `op.map` maps a primitive's parameter name to a pointer into the
  call arguments —
  ```rust
  fn ptr<'a>(args: &'a Value, op: &'a OpSpec, key: &str) -> Option<&'a Value> {
      op.map.get(key).and_then(|p| args.pointer(p))
  }
  ```
  (`tools.rs:106-108`), with typed accessors `req_str/opt_i64/opt_vec_i64/req_value/...`
  (`tools.rs:110-217`). A typical map is `"model": "/model", "ids": "/ids", "values": "/values"`
  (`config/tools.json`, `odoo_update`).
- Hot-reload: `Registry::start_watchers()` (`registry.rs:127-186`) spawns a `notify` recommended watcher
  on the **parent directories** of tools/prompts/server JSON (`RecursiveMode::NonRecursive`), pushing
  into an unbounded channel; the consumer debounces with `sleep(200ms)` then drains
  (`registry.rs:140-151`). Reload is atomic-on-success and **fails safe**:
  `warn!(error = %e, "config reload failed; keeping last good")` (`registry.rs:148`). State swap happens
  under one `RwLock` write (`registry.rs:277-283`). Duplicate tool names abort the reload
  (`registry.rs:257-262`).
- Seeding: `config-defaults/{tools,prompts,server}.json` are `include_str!`-embedded in the binary
  (`registry.rs:14-16`) and written to disk if the target file is missing (`ensure_file_exists_with_seed`,
  `registry.rs:322-333`). Paths come from `MCP_TOOLS_JSON` / `MCP_PROMPTS_JSON` / `MCP_SERVER_JSON`, else
  `config/tools.json` etc. (`registry.rs:101-116`).
- `config/tools.json`, `rust-mcp/config/tools.json` and `rust-mcp/config-defaults/tools.json` are
  **byte-identical** (same md5 `9d48aba4…`) — three copies of the same file in the tree.

### Inferences
- "Declarative" here means *declarative dispatch*, not *declarative capability*: you can rename, re-word,
  re-schema and re-map any tool at runtime, but you cannot create a behaviour the 22-arm `match` does not
  already implement (see §9).
- Because `list_tools` emits the author's schema unmodified, the schema and the actual argument
  extraction can drift silently — `op.map` pointers are never checked against `inputSchema`.

### Gaps
- Nothing in the code emits `notifications/tools/list_changed` after a hot reload (the handler only
  *swallows* that notification, `mcp/mod.rs:160`), even though `initialize` advertises
  `"tools": { "listChanged": true }` (`runtime.rs:88`). Clients therefore may not notice a reload; I found
  no code path that pushes the notification.

---

## 3. Odoo connection layer (KEY ITEM)

### Takeaway
Two fully separate client structs (`OdooHttpClient` = JSON-2, `OdooLegacyClient` = JSON-RPC) unified by a
**Rust enum with per-method `match` delegation** (`OdooClient::Modern | Legacy`), with an
`OdooClientTrait` existing only for mockability. Version is **never detected at runtime** — it is
declared in config, and the *authentication material you supply* is what actually picks the client. The
two impls are not behaviourally equivalent: the legacy path silently discards `context` on every call.

### Cited Findings

**Abstraction shape — enum, not dyn-trait polymorphism**
- `rust-mcp/src/odoo/unified_client.rs:137-143`:
  ```rust
  #[derive(Clone)]
  pub enum OdooClient {
      /// Odoo 19+ with JSON-2 API and API key authentication
      Modern(OdooHttpClient),
      /// Odoo < 19 with JSON-RPC and username/password authentication
      Legacy(OdooLegacyClient),
  }
  ```
  Every one of ~17 methods is a two-arm `match` that forwards identical arguments
  (`unified_client.rs:166-406`). `OdooClientTrait` (`unified_client.rs:9-133`) is declared *"for Odoo
  client operations, enabling mockability for testing"* and then implemented for `OdooClient` by
  calling the inherent methods (`unified_client.rs:408-575`) — a trait wrapper over an enum wrapper over
  two structs. ~600 lines of pure delegation.

**Version detection — there is none**
- `OdooInstanceConfig::auth_mode()` (`odoo/config.rs:44-64`) is the whole "detection": if `version`
  parses and `major < 19` → `Password`; else if `apiKey` empty/absent and username+password present →
  `Password`; else → `ApiKey` (the `#[default]`, `config.rs:11-12`).
- `OdooClient::new` picks on that alone (`unified_client.rs:148-159`). A grep for `version_info`,
  `webclient/version`, `detect_version` across `rust-mcp/src` and `README.md` returns **nothing** — no
  handshake, no probe. The README/description claim "Supports Odoo 14-19+" but the code treats
  everything `< 19` as one undifferentiated legacy path; there is no 14-vs-18 branching anywhere.

**What a JSON-2 call actually looks like (the reader's migration question)**
- URL: `POST {origin}/json/2/{model}/{method}` —
  ```rust
  fn endpoint(&self, model: &str, method: &str) -> anyhow::Result<Url> {
      let mut url = self.base_url.clone();
      url.set_path(&format!("/json/2/{model}/{method}"));
      Ok(url)
  }
  ```
  (`odoo/client.rs:74-78`). `base_url` is normalised to origin at construction — path, query and fragment
  are stripped (`client.rs:23-26`), so a configured URL with a path silently loses it.
- Headers (`client.rs:50-72`):
  ```rust
  headers.insert(AUTHORIZATION, HeaderValue::from_str(&format!("bearer {}", self.api_key))?);
  headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json; charset=utf-8"));
  headers.insert(USER_AGENT, HeaderValue::from_static("odoo-mcp-rust/0.1"));
  // and, when db is non-empty:
  headers.insert("X-Odoo-Database", HeaderValue::from_str(db)?);
  ```
  Note lowercase `bearer` and the **`X-Odoo-Database` header** carrying the db rather than a body field.
- Body: **a flat JSON object of kwargs, one per method — no envelope, no `jsonrpc`, no `id`, no `params`
  wrapper.** Examples straight from the code:
  - `search`: `{"domain":…, "limit":…, "offset":…, "order":…, "context":…}` — keys only added when
    `Some` (`client.rs:221-238`).
  - `read`: `{"ids":[…], "fields":[…], "context":…}` (`client.rs:284-292`).
  - `create`: `{"vals_list":[{…}], "context":…}` with a convenience wrap —
    *"Odoo signature is create(vals_list) … we accept a single object for convenience"*
    (`client.rs:301-312`).
  - `write`: `{"ids":[…], "vals":{…}, "context":…}` (`client.rs:345`).
  - `unlink`: `{"ids":[…]}` (`client.rs:360`).
  - `copy`: `{"ids":[id], "default":…}` (`client.rs:518-524`).
  - arbitrary method (`call_named`): the caller's params map **is** the body, with `context` and `ids`
    injected as top-level keys (`client.rs:405-412`).
- Response: **the bare return value, not wrapped.** `search` deserialises the body directly into
  `Vec<i64>` (`client.rs:238-242`); `search_count` directly into `i64` (`client.rs:382-385`); `write`
  and `unlink` directly into `bool` (`client.rs:350, 365`). `create` handles both shapes with a comment
  recording the observed reality: *"Odoo v19 /json/2/ create returns an array of IDs, e.g. [42]"*
  (`client.rs:314-334`).
- Errors: **HTTP status is the error channel** — a success status means the body *is* the result; a
  non-2xx body is parsed as `OdooErrorBody { name, message, arguments, context, debug }`
  (`odoo/types.rs:4-13`) and lifted into `OdooError::Api { status, message, body }`
  (`client.rs:112-121`). If the body doesn't parse, the raw text becomes the message. Compare JSON-RPC,
  where a **200 OK can still carry `{"error": …}`** and must be unwrapped explicitly
  (`legacy_client.rs:123-137`).
- Retry policy is identical in both clients: `for attempt in 0..=max_retries` (default 3,
  `client.rs:34`), retry **only** on 5xx / 429 / transport errors, never on 4xx
  (*"Retry on 5xx and 429; do not retry auth/4xx."*, `client.rs:123-128`), exponential backoff
  `250ms · 2^attempt` (`client.rs:136-140`). Timeout default 30s (`client.rs:33`).
- Report PDF (modern) bypasses JSON-2 entirely: `GET {origin}/report/pdf/{report_name}/{csv ids}` with
  the same bearer headers, returning raw bytes (`client.rs:148-210`).
- Test evidence for the wire shape: `rust-mcp/tests/common/mod.rs:77-95` mounts wiremock on
  `path_regex(r"/json/2/{model}/search")` and responds with a **bare** `[1,2,3]`;
  `rust-mcp/tests/odoo_client_modern.rs` asserts against that.

**Legacy JSON-RPC shape, for contrast**
- Single endpoint `POST {origin}/jsonrpc` (`legacy_client.rs:73-77`) with the classic envelope
  ```json
  {"jsonrpc":"2.0","method":"call","params":{"service":…,"method":…,"args":…},"id":1}
  ```
  (`legacy_client.rs:80-91`).
- Auth: `common.authenticate([db, username, password, {}])`, uid cached in
  `Arc<RwLock<Option<i64>>>` (`legacy_client.rs:183-223`); `uid == 0` is mapped to a synthetic
  `status: 401` error (`legacy_client.rs:205-214`).
- Every call then goes through `execute_kw` with **the password re-sent on every request**:
  ```rust
  let call_args = vec![json!(self.db), json!(uid), json!(self.password),
                       json!(model), json!(method), args, kwargs.unwrap_or_else(|| json!({}))];
  ```
  (`legacy_client.rs:226-249`).
- Legacy report download needs a **session cookie**: it POSTs `/web/session/authenticate` first
  (relying on reqwest's `cookie_store(true)`), then GETs `/report/pdf/…` — with the honest comment
  *"This is a simplified approach - in production you might need session cookies"*
  (`legacy_client.rs:407-460`).
- Error mapping differs: a JSON-RPC error is flattened to a fabricated `status: 400` with the message
  taken from `error.data.message` (falling back to `error.message`) — `legacy_client.rs:123-137`.

**Divergence the enum hides**
- **The legacy client throws away `context` on every single method.** Fifteen signatures take
  `_context: Option<Value>` and never use it (`legacy_client.rs` lines 258, 289, 315, 330, 345, 358, 369,
  380, 391, 509, 542, 562, 572, 584, 600). So `{"context":{"lang":"vi_VN","company_id":3}}` is honoured on
  Odoo 19 and silently dropped on Odoo 18, through the same MCP tool with the same arguments.
- `fields_get` also differs: legacy requests a fixed attribute subset
  `["string","type","help","required","readonly","relation","selection"]`
  (`legacy_client.rs:380-383`), modern sends no `attributes` at all (`client.rs:388-395`) and gets
  everything.
- `name_search` legacy applies defaults (`operator="ilike"`, `limit=100`) that modern does not
  (`legacy_client.rs:535-555` vs `client.rs:454-480`).

**Metadata caching**
- `MetadataCache` = `Arc<RwLock<HashMap<String, (Value, Instant)>>>`-style store keyed by instance+model
  (`rust-mcp/src/mcp/cache.rs:16-55`), TTL read per call from `ODOO_METADATA_CACHE_TTL_SECS`
  (**default 300s, `0` disables**) — `mcp/tools.rs:467-478`.
- What's cached: only the `odoo_get_model_metadata` payload, i.e. `fields_get` + the `ir.model` name
  lookup merged into `{"model":{"name","description","fields"}}` (`tools.rs:484-520`).
- **Invalidation: time-only.** `clear_all()` / `clear_expired()` exist (`cache.rs:57-68`) but a grep of
  the whole `src/` tree shows **no caller outside `cache.rs`** — no write path, no reload, no
  `ir.model.fields` change ever evicts an entry. A schema change is invisible for up to the TTL.
- The cache is **not** consulted by `odoo://{instance}/metadata/{model}` (`mcp/resources.rs:177-221`
  calls the client directly), so the same data is cached on one path and not the other.

**Multi-instance isolation**
- `instances.example.json` is a flat map `{ "<name>": {url, db, apiKey | username+password, version,
  timeout_ms, max_retries} }`; loaded by `load_odoo_env()` in priority order: `ODOO_INSTANCES_JSON`
  (file path) → `ODOO_INSTANCES` (inline JSON, or a path if it doesn't start with `{`/`[`) → single-
  instance `ODOO_URL`/`ODOO_DB`/`ODOO_API_KEY`/`ODOO_USERNAME`/`ODOO_PASSWORD`/`ODOO_VERSION` collapsed
  into an instance literally named `"default"` (`odoo/config.rs:72-177`).
- Per-instance gaps are back-filled from global env vars, and a missing credential is a **hard startup
  failure**: `anyhow::bail!("Missing apiKey for instance '{name}' …")` (`config.rs:202-258`).
- Isolation at runtime is **one `OdooClient` per instance name, lazily built and memoised** in
  `OdooClientPool { clients: Arc<Mutex<HashMap<String, OdooClient>>> }` (`mcp/tools.rs:17-57`). Each
  client owns its own `reqwest::Client` (so its own connection pool and **its own cookie jar**,
  `client.rs:36-39`) and its own credentials; the legacy client's cached `uid` is per-client too. The
  metadata cache is shared but keyed by instance (`cache.rs`).
- `instance` is a **required argument on every single tool** (`config/tools.json`: all 22 tools list
  `"instance"` in `required`), resolved by `pool.get(&instance)` at the top of each op
  (`tools.rs:229-234` and equivalents). An unknown name errors with the available list
  (`tools.rs:42-51`).

### Inferences
- The JSON-2 migration is mostly *smaller*, not bigger, than XML-RPC: no envelope to build, no
  `common.authenticate` round-trip, no uid/password threading, and errors arrive as HTTP status codes.
  The real work is (a) the `create` return-shape change (array of ids), (b) `write` taking `vals` while
  `create` takes `vals_list`, (c) db moving to a header.
- The "one trait, two impls" story is the README's framing; the code is an enum with a mock-only trait.
  The practical effect is that every new Odoo method must be written **five times** (modern impl, legacy
  impl, trait decl, enum inherent, trait forward) — which is exactly the kind of friction that produced
  the silent `_context` drop.

### Gaps
- No evidence in the repo of testing against a **real** Odoo 19 server: `tests/odoo_client_modern.rs`
  uses wiremock with hand-written response fixtures, so the JSON-2 request/response shape is asserted
  against the authors' *belief* about Odoo 19, not against Odoo 19. (The `create` comment at
  `client.rs:314` reads like it was corrected after a real observation, but I can't verify that.)
- No documented behaviour for Odoo 19 instances that still want password auth, or for `/json/2/`
  disabled.

---

## 4. Tool design

### Takeaway
**22 generic-CRUD/meta tools, zero domain tools** — the entire surface is a thin, faithful projection of
Odoo's ORM API (`search`, `read`, `write`, `unlink`, `read_group`, `onchange`, `execute` …) plus an
`odoo_execute` escape hatch that makes the other 21 largely redundant. Output is uniformly a
pretty-printed JSON blob inside a single MCP text content block.

### Cited Findings
Enumerated from `rust-mcp/config/tools.json` (name — op type — one-line purpose; `W` = gated by
`ODOO_ENABLE_WRITE_TOOLS`, `C` = gated by `ODOO_ENABLE_CLEANUP_TOOLS`):

| Tool | op.type | What it does |
|---|---|---|
| `odoo_search` | `search` | Return matching ids (`{ids, count}`) |
| `odoo_search_read` | `search_read` | Search + read in one call (`{records, count}`) |
| `odoo_read` | `read` | Read named fields of given ids |
| `odoo_create` **W** | `create` | Create one record, returns `{id, success}` |
| `odoo_update` **W** | `write` | Write `values` to `ids`, returns `{success, updated_count}` |
| `odoo_delete` **W** | `unlink` | Unlink `ids`, returns `{success, deleted_count}` |
| `odoo_execute` **W** | `execute` | **Call any method on any model** with free-form args/kwargs |
| `odoo_count` | `search_count` | Count matching records |
| `odoo_workflow_action` **W** | `workflow_action` | Call a button/workflow method (e.g. `action_confirm`) on ids |
| `odoo_generate_report` | `generate_report` | Render a QWeb report to PDF, base64 |
| `odoo_get_model_metadata` | `get_model_metadata` | `fields_get` + model description, TTL-cached |
| `odoo_database_cleanup` **C** | `database_cleanup` | Bulk hygiene: drop test data / drafts / inactive, archive, optimize |
| `odoo_deep_cleanup` **C** | `deep_cleanup` | Deeper destructive cleanup pass |
| `odoo_read_group` | `read_group` | GROUP BY aggregation |
| `odoo_name_search` | `name_search` | Autocomplete-style lookup by display name |
| `odoo_name_get` | `name_get` | Display names for ids |
| `odoo_default_get` | `default_get` | Default values for a new record |
| `odoo_copy` **W** | `copy` | Duplicate a record |
| `odoo_onchange` | `onchange` | Simulate form onchange |
| `odoo_list_models` | `list_models` | `ir.model` listing, default domain `[["transient","=",false]]` (`tools.rs:702`) |
| `odoo_check_access` | `check_access` | Query model- and record-level access (see §6) |
| `odoo_create_batch` **W** | `create_batch` | Create up to 100 records |

- Generic vs domain-specific: **entirely generic**. No `sale.order`-aware or `stock.picking`-aware tool
  exists; the model name is always a caller-supplied string (`req_str(&args, op, "model")`).
- Input schema style: flat, all-primitive, `"additionalProperties": false`, small `required` lists, no
  enums or formats, no per-field descriptions. Example (`odoo_search_read`): `instance, model, domain
  (array), fields (array<string>), limit, offset, order, context (object)` with
  `"required": ["instance","model"]`. Descriptions are one sentence, e.g. *"Update existing Odoo records.
  Returns true on success."* — there are no usage examples, no domain-syntax hints, no field guidance.
- Output formatting is a single helper, used by every op:
  ```rust
  fn ok_text(payload: Value) -> Value {
      json!({"content":[{"type":"text","text": serde_json::to_string_pretty(&payload).unwrap_or_else(|_| "{}".to_string())}]})
  }
  ```
  (`tools.rs:219-226`). No `structuredContent`, no `outputSchema`, no pagination hints, no token-budget
  truncation — `odoo_search_read` with no `limit` will happily serialise the entire table into the model's
  context.
- Errors are returned as MCP tool errors, not protocol errors: `{"content":[{…json with "error"…}],
  "isError": true}` (`mcp/mod.rs:112-123`), including for unknown/guard-disabled tools
  (`mcp/mod.rs:98-109`).
- `odoo_create_batch` limit: hard-coded, not configurable —
  ```rust
  // Limit batch size to 100 to prevent abuse
  if values_list.len() > 100 { return Err(OdooError::InvalidResponse("Batch size limited to 100 records".to_string())); }
  ```
  (`tools.rs:802-807`). It then **loops one `create` call per record** (`tools.rs:814-820`), i.e. up to
  100 sequential HTTP round-trips, **non-atomic**: a failure at item 57 returns an error and leaves 56
  records committed, with the created ids lost.
- `odoo_generate_report` = `download_report_pdf` then base64 into the text block:
  `{"pdf_base64", "report_name", "record_ids"}` (`tools.rs:436-456`). No size cap — a large PDF becomes a
  multi-MB base64 string in the conversation.
- `odoo_workflow_action` = `call_named(model, action, Some(ids), {}, context)` with **no allow-list of
  action names** (`tools.rs:354-374`); returns `{"result", "executed_on"}`.
- `odoo_execute` argument marshalling is heuristic: a single-element array whose inner element is an
  all-integer array is reinterpreted as `ids`, an object is splatted into params, anything else is
  stuffed under `"arg"`; `kwargs` objects are merged into the same flat param map
  (`tools.rs:392-428`). That flattening means a kwarg literally named `ids` or `context` collides with
  the injected ones.

### Inferences
- Measured against MCP tool-design guidance (few, purposeful, workflow-shaped tools with rich
  descriptions), this is the opposite pole: it is an ORM driver exposed as tools. It maximises coverage
  and minimises model guidance — the LLM must already know Odoo's model names, field names and domain
  syntax. `odoo_get_model_metadata` + `odoo_list_models` are the concession to discovery.
- `odoo_execute` makes every other write guard advisory at best: if `ODOO_ENABLE_WRITE_TOOLS=true`,
  `odoo_execute` can call `unlink` on any model regardless of whether `odoo_delete` was removed from
  `tools.json`.

### Gaps
- No token/response-size limits anywhere; I found no truncation logic in `tools.rs`.

---

## 5. Write-path flow, traced

### Takeaway
The write path is startlingly short: **guard check → JSON-Pointer extraction → type coercion → HTTP call
to Odoo.** There is no approval step, no `fields_get` validation, no model or method allow-list, no
dry-run, no rate limit, no audit record. "Read-only mode" is not an enforced mode at all — it is the
absence of write tools from the published list.

### Cited Findings
Full trace for `odoo_update` over HTTP transport:
1. `POST /mcp` → `validate_origin` (only if `MCP_ALLOWED_ORIGINS` is set — off by default,
   `http.rs:463-466`) → `validate_auth_async` (only if `MCP_AUTH_ENABLED=true` — **default false**,
   `http.rs:180-183, 525-528`) → `validate_protocol_version` (`http.rs:576+`).
2. `McpOdooHandler::handle_method("tools/call")` → `self.registry.get_tool(name)`
   (`mcp/mod.rs:87-98`).
3. **Guard check, the only gate:** `get_tool` returns `Some` only if `guards_allow(...)`:
   ```rust
   fn guards_allow(guards: Option<&ToolGuards>) -> bool {
       let Some(g) = guards else { return true };
       if let Some(var) = &g.requires_env_true { return env_truthy(var); }
       true
   }
   fn env_truthy(var: &str) -> bool {  // "1" | "true" | "yes" | "y" | "on"
   ```
   (`registry.rs:298-314`). Same predicate filters `list_tools` (`registry.rs:210`). Guards are read
   **live from the process environment on every call** — not snapshotted at boot.
   `requiresEnvTrue` is the **only** guard kind the struct supports (`registry.rs:56-61`).
4. Blocked → `{"error":"Unknown or disabled tool","tool":…, "isError": true}` (`mcp/mod.rs:99-108`).
   Note the enforcement is real at call time, not merely a listing filter — a client that remembers a
   tool name from an earlier, permissive run still gets refused.
5. `call_tool` → `execute_op` → `op_write` (`tools.rs:69, 82, 303`).
6. `op_write` extracts `instance`, `model`, `ids`, `values`, `context` via `op.map` pointers, coercing
   types (`tools.rs:304-308`). **This is the entire validation.** No check that `model` exists, that the
   field names in `values` exist or are writable, that `ids` are non-empty, that the caller is allowed
   this model, no size cap on `ids`.
7. `pool.get(&instance)` → `client.write(model, ids, values, context)` → `POST /json/2/{model}/write`
   (modern) or `execute_kw` (legacy) (`tools.rs:310-314`).
8. Response `{"success": ok, "updated_count": ids.len()}` (`tools.rs:315-317`). Note
   `updated_count` is **the requested id count, not what Odoo reports as updated** — Odoo's `write`
   returns a bare `true`.

Per-op specifics:
- `odoo_create` (`tools.rs:289-301`): same shape; returns `{id, success:true}` where `success` is
  hard-coded `true` (it can only be reached if the call succeeded, but it is not Odoo's answer).
- `odoo_delete` (`op_unlink`, `tools.rs:320-334`): `ids` required, **no minimum/maximum, no confirmation,
  no soft-delete preference**. `odoo_delete` on `[1,2,…,10000]` is one call.
- `odoo_execute` (`tools.rs:376-434`): `method` is a free string; **no method whitelist anywhere in the
  repo** (contrast with the reader's server). Guarded only by `ODOO_ENABLE_WRITE_TOOLS`.
- `odoo_workflow_action` (`tools.rs:354-374`): `action` is a free string, likewise unfiltered.
- `odoo_create_batch` (`tools.rs:787-826`): only the ≤100 check, then a non-atomic loop (§4).
- Cleanup tools: gated by `"requiresEnvTrue": "ODOO_ENABLE_CLEANUP_TOOLS"` in `tools.json` (lines 298,
  331) — enforced by the **same** `guards_allow` path, nothing special. `main.rs` keeps a
  `--enable-cleanup-tools` clap flag but the comment states it is inert:
  *"Cleanup tool gating is handled via tool guards (e.g. requiresEnvTrue=ODOO_ENABLE_CLEANUP_TOOLS). We
  keep the CLI flag for compatibility, but it only affects the env var via clap env binding."*
  (`main.rs:611-612`). `op_database_cleanup` does expose a `dryRun` option passed through to
  `cleanup::database::CleanupOptions` (`tools.rs:535-545`).
- **Read-only mode**: `ODOO_ENABLE_WRITE_TOOLS` appears **only in `tools.json`** — a grep over
  `rust-mcp/src` finds zero references. There is no server-side "is this op a write?" test; nothing stops
  an author from writing `{"name":"odoo_read","op":{"type":"unlink"}}`. README §"Disabling Tools"
  recommends deleting entries from `tools.json` as "Option 1 (recommended)" and guards as "Option 2"
  (README lines ~210-270), and its read-only example is a hand-pruned `tools.json`. So read-only is a
  *configuration convention*, and the credential the server holds is unchanged — the Odoo account can
  still write.

### Inferences
- The security model delegates **everything** to Odoo's own ACLs plus the single on/off env flag. If the
  configured Odoo account can write, the only thing between an LLM and a mass `unlink` is
  `ODOO_ENABLE_WRITE_TOOLS` and Odoo's `ir.model.access`.
- Because guards are read from the live environment per call, they can be flipped without restart — but
  also, the *process environment* is the security boundary, and the config UI can write the `.env`
  (§6), which makes the UI a privilege-escalation surface.

### Gaps
- No approval/confirmation primitive of any kind (no MCP `elicitation`, no pending-op store). The reader's
  agent-layer LangGraph interrupt has no counterpart here.

---

## 6. Permission / security model

### Takeaway
One shared Odoo credential per instance, no per-caller identity, **HTTP transport unauthenticated by
default**, permissive CORS on every route, and an admin Web UI that binds `0.0.0.0:3008`
**unconditionally** with default credentials `admin/changeme` and plaintext comparison. `odoo_check_access`
reports `has_access: true` unconditionally.

### Cited Findings

**Identity / credentials**
- One account per instance, shared by all MCP callers; no propagation of end-user identity. Credentials
  live in `instances.json` / env in **plaintext** (`odoo/config.rs`, `instances.example.json`,
  `dotenv.example` lines 17/36-37). The legacy client re-sends the password in every `execute_kw`
  (`legacy_client.rs:240`).
- `dotenv.example:44-45`: `CONFIG_UI_USERNAME=admin`, `CONFIG_UI_PASSWORD=changeme`.

**`odoo_check_access`** (`tools.rs:727-785`)
- It calls **`check_access_rights`** (model level, with `{"operation": …}`) and, when `ids` are supplied,
  **`check_access_rule`** (record level). It does *not* read `ir.model.access` rows. The code comment
  explains the choice:
  > *"Note: check_access() in Odoo 19+ is a private method and cannot be called remotely. We must use
  > check_access_rights() and check_access_rule() for all Odoo versions, even though they are deprecated
  > in Odoo 19+. They are still callable remotely."* (`tools.rs:743-745`)
- **Bug:** the record-level call's failure is swallowed with `.await.ok()` (`tools.rs:771`) and the
  response hard-codes `"has_access": true` (`tools.rs:777`) regardless of either result. A denial surfaces
  only if the *model-level* call errors out of the whole op. An LLM reading `has_access` is being told
  "yes" by a constant.

**MCP transport security** (`rust-mcp/src/mcp/http.rs`)
- Bearer auth exists but is **opt-in and off by default**: `MCP_AUTH_ENABLED` must be truthy and
  `MCP_AUTH_TOKEN` set (`http.rs:176-192`); if enabled without a token, it fails **closed** with a 500
  (`http.rs:530-539`) — good. Token comparison is `token == expected_token` (`http.rs:546`), a plain
  non-constant-time `==`. README confirms the default: *"If `MCP_AUTH_ENABLED=false` or `MCP_AUTH_TOKEN`
  is not set, authentication is disabled (not recommended for production)"* (README ~line 850).
- Auth config supports hot-reload (`AuthConfig::reload_from_env`, `http.rs:246-264`), driven from the
  config UI.
- Routes (`http.rs:389-400`): `/mcp` (POST/GET/DELETE, Streamable HTTP), `/sse` + `/messages` (legacy SSE
  for Cursor), `/health` and `/openapi.json` — the latter two **explicitly unauthenticated**
  (*"Health check endpoint (no auth required for monitoring)"*, `http.rs:395-398`). `/health` performs a
  live `search_count("ir.model")` per instance (`http.rs:312-342`), so an unauthenticated caller can both
  enumerate instance names and induce an Odoo query per request.
- **`.layer(CorsLayer::permissive())`** is applied to the whole router (`http.rs:399`).
- Origin validation (DNS-rebinding defence) exists but is **disabled unless `MCP_ALLOWED_ORIGINS` is
  set** (`SecurityConfig::from_env`, `http.rs:142-164`; `validate_origin`, `http.rs:459-508`), and even
  when enabled it always allows anything whose Origin string merely *contains* `"localhost"`,
  `"127.0.0.1"` or `"[::1]"` (`http.rs:473-475, 490`) — so `https://localhost.evil.com` passes.
  A request with **no** Origin header is always allowed (`http.rs:502-506`).
- Default bind for ws/http is `127.0.0.1:8787` (`main.rs:542`), which is the one sane default.
- Session/resumability: `Mcp-Session-Id` header (`http.rs:40`), a per-session event store with
  `next_event_id` and `get_events_after(last_event_id)` for SSE resume via `Last-Event-ID`
  (`http.rs:101-130`). Session ids are UUIDs; I found no binding of a session to an auth principal —
  when auth is off, any client can guess/replay a session id.

**Web UI on :3008** (`rust-mcp/src/config_manager/server.rs`)
- Started **unconditionally** on every server start, for every transport, in a `tokio::spawn`
  (`main.rs:618-635`) — including stdio mode under Claude Desktop. Port default 3008
  (`main.rs:549-551`, comment: *"inspired by Peugeot 3008"*).
- Binds **all interfaces**: `TcpListener::bind(format!("0.0.0.0:{}", port))` (`server.rs:234`).
- Auth is **disabled by default**: `enabled = !username.is_empty() && !password.is_empty()` from
  `CONFIG_UI_USERNAME` / `CONFIG_UI_PASSWORD` (`server.rs:40-42`), with
  `warn!("Config UI authentication disabled (CONFIG_UI_USERNAME/PASSWORD not set)")` (`server.rs:47`).
  The middleware short-circuits: *"If auth is disabled, allow all requests"* (`server.rs:135-138`).
- When enabled, verification is plaintext `self.username == username && self.password == password`
  (`server.rs:57-58`), then a random session token with an expiry (`server.rs:106-110, 141-148`).
- `CorsLayer::permissive()` again (`server.rs:231`).
- Protected endpoints write the server's own configuration and secrets: `POST /api/config/instances`
  (**Odoo credentials**), `/api/config/tools` (**the tool definitions, i.e. arbitrary op wiring**),
  `/api/config/prompts`, `/api/config/server`, `/api/auth/change-password`,
  `/api/auth/generate-mcp-token`, `/api/auth/mcp-auth-enabled` (`server.rs:195-215`). `GET
  /api/config/instances` returns the stored config **unmasked** — `load_instances()` straight into
  `Json(config)` (`server.rs:642-644`), no redaction of `apiKey`/`password`.
- Public: `/health`, `/api/auth/status`, `/api/auth/login`, `/api/auth/logout` (`server.rs:219-224`).
- README does tell the user to change the password immediately (README ~line 423) and offers to enable
  MCP auth from the Security tab — mitigation by documentation, not by default.

### Inferences
- **Answer to the key question "Is HTTP transport authenticated at all?": only if you turn it on.**
  Out of the box, `--transport http` yields an unauthenticated, permissively-CORS'd MCP endpoint that can
  create, write and unlink in Odoo whenever `ODOO_ENABLE_WRITE_TOOLS=true`.
- The `0.0.0.0:3008` admin plane is the more serious exposure than the MCP port: by default it is
  reachable from the LAN, unauthenticated, hands out Odoo credentials in cleartext, and lets a caller
  rewrite `tools.json` — which is remote *behaviour* injection into the MCP server (define a tool whose
  `op.type` is `unlink` or `execute`).
- Per-role isolation in the reader's sense (separate processes, separate Odoo accounts) is *possible*
  here via separate instances, but is undermined by the fact that a single MCP client picks the
  `instance` argument freely on every call: the multi-instance feature is a routing convenience, not an
  isolation boundary.

### Gaps
- `.github/SECURITY.md` exists; I did not read its content in depth. No CVE/advisory history found.

---

## 7. Audit / logging / observability

### Takeaway
Structured `tracing` for lifecycle events only. **There is no per-tool-call audit trail** — no record of
who called what, on which model, with which arguments, nor of writes.

### Cited Findings
- A grep for `info!|warn!|debug!|trace!` in `rust-mcp/src/mcp/tools.rs` and `rust-mcp/src/odoo/client.rs`
  returns **zero hits**. The tool-execution path and the Odoo HTTP path emit no logs at all.
- Logging that does exist: config load/reload (`registry.rs:284-286`, `registry.rs:148`), watcher setup
  (`registry.rs:181`), auth state (`http.rs:214-220, 255-261`), origin policy (`http.rs:153-161`), config
  server events (`config_manager/server.rs:45-47, 646`).
- Tracing init distinguishes transports: stderr-only, no ANSI for stdio (`main.rs:576-591`).
- Health/observability endpoints: MCP `/health` with per-instance reachability and `status ∈
  {ok, degraded, unhealthy}` (`http.rs:312-359`), MCP `ping` → `{}` (`mcp/mod.rs:154`), config server
  `/health`, and a static `/openapi.json` served from `rust-mcp/openapi/openapi.json` (`http.rs:362-367`).
- No metrics endpoint, no request ids in logs, no hash-chain, no tamper-evidence, no argument
  fingerprinting.

### Inferences
- For a server that can `unlink` production records, the absence of any write log is the largest
  operational gap. The only forensic trail after an incident is Odoo's own `ir.logging`/mail-thread and
  the shared account's footprint — and since all callers share one account, attribution is impossible.

---

## 8. Testing strategy

### Takeaway
Mock-based integration tests with wiremock at the HTTP boundary, axum-test for the transport, and
unit tests inline; ~154 test functions over 18 files, wired into an 8-job CI with clippy-as-error and
coverage. No tests against a real Odoo, and no test asserts the actual *request body* shape sent to
Odoo — only the URL path.

### Cited Findings
- Layers: (a) inline `#[cfg(test)] mod tests` in nearly every source file (e.g. `client.rs:578-682`
  covering URL normalisation, endpoint format, retry defaults; `registry.rs` covering the Cursor schema
  validator; `tools.rs:828+` covering the JSON-Pointer helpers); (b) `rust-mcp/tests/*.rs` integration
  tests; (c) `config-ui/src/__tests__/*` vitest suites.
- Odoo is mocked with **wiremock**: `rust-mcp/tests/common/mod.rs:77-95` mounts
  `method("POST") + path_regex(r"/json/2/res\.partner/search")` returning a canned body. The matcher
  constrains **only the path** — `.and(body_json(...))` is not used, so a regression in the request body
  (e.g. sending `vals` where Odoo wants `vals_list`) would not be caught.
- `header(...)` is imported in `odoo_client_modern.rs:10`, so at least some tests assert the
  `Authorization` header.
- Transport tested with `axum-test` via the public `create_app(handler, auth)` factory, deliberately
  exposed for that purpose: *"This is public to enable integration testing with axum-test"*
  (`http.rs:369-371`); `tests/http_transport.rs` has 13 tests. `tests/mcp_smoke.rs` and
  `tests/cursor_schema.rs` are single-test guards. There is also a manual WS client binary
  `rust-mcp/src/bin/ws_smoke_client.rs` (232 LOC).
- `mockall` is a dev-dependency (the stated reason `OdooClientTrait` exists, `unified_client.rs:9-10`).
- CI (`.github/workflows/ci.yml`): `cargo check --all-features`, `cargo fmt --check`,
  `cargo clippy -- -D warnings`, `cargo test --all-features` on an **OS matrix**, tarpaulin coverage →
  Codecov, `cargo-audit`, plus the React build and `npm test`. Commit `8d51ba5` (2026-01-28) adds
  *"comprehensive service integration tests"*; `64ed857` records *"Remove problematic TS test files -
  need different coverage strategy"*.

### Inferences
- The test suite proves the code is internally consistent, not that it speaks Odoo correctly. Given that
  JSON-2 is new and sparsely documented, this is where the highest residual risk sits — and it is exactly
  the same trap the reader's own memory records repeatedly ("test không đo gì").

---

## 9. Extensibility

### Takeaway
Adding a tool without recompiling is genuinely easy — edit `tools.json`, save, the watcher reloads in
~200 ms — but you can only recombine the 22 existing primitives. **The escape hatch is `op.type:
"execute"`**, which lets a declarative tool call any Odoo method; there is no hook for per-tool
business validation in Rust short of a recompile.

### Cited Findings
Concrete steps (all verified against code):
1. Open the active `tools.json` (path from `MCP_TOOLS_JSON`, else `config/tools.json`;
   `registry.rs:102-107`), or use the UI's Tools tab (`config-ui/src/components/tabs/ToolsTab.tsx`,
   `POST /api/config/tools`, `server.rs:201`).
2. Append an object with `name`, `description`, `inputSchema`, `op`, optional `guards`
   (`ToolDef`, `registry.rs:37-46`).
3. `inputSchema` must survive `validate_cursor_schema` — **no `anyOf`/`oneOf`/`allOf`/`$ref`/
   `definitions`, no union `type` arrays** (`registry.rs:357-387`), or the whole reload is rejected and
   the previous config stays live (`registry.rs:254-256`, `registry.rs:148`).
4. `op.type` must be one of the 22 (`tools.rs:77-103`); `op.map` gives a JSON Pointer per primitive
   parameter (`"model": "/model"`, or something nested like `"/filters/model"` — `ptr` uses
   `Value::pointer`, so any pointer works).
5. Save. The `notify` watcher fires, debounces 200 ms, and swaps state atomically
   (`registry.rs:140-151, 277-283`). No restart. Name collisions abort the reload
   (`registry.rs:257-262`).

What declarative tools **cannot** express:
- **Any new behaviour.** `op.type` outside the 22 → `Unknown op.type` at call time (`tools.rs:100-102`).
- **Any conditional logic**: no branching, no chaining two Odoo calls, no computed defaults, no
  post-processing of results, no templating of values. `op.map` only *relocates* arguments.
- **Any validation beyond types**: no enums, no ranges, no cross-field rules, no
  "`model` must be in this list", no "reject `unlink` on `account.move`". `guards` has exactly one
  variant, `requiresEnvTrue` (`registry.rs:56-61`), and it is per-tool boolean, not per-argument.
- **Any output shaping**: `ok_text` is fixed (`tools.rs:219-226`); you cannot declare a summary form or
  field projection.
- **Anything bound to a caller**: no identity, no role, no per-tool instance pinning (`instance` is always
  a caller-supplied argument).

**The escape hatch, and its double edge:** you *can* fake a domain-specific tool by fixing a model in the
pointer map — e.g. an `odoo_confirm_sale_order` tool whose `op` is `workflow_action` — but the `model` and
`action` still have to arrive from the caller's arguments, because `op.map` can only point *into the
arguments*, never supply a constant. There is no `"const"`/`"default"` facility in `OpSpec`
(`registry.rs:48-54`: just `type` + `map`). So even pinning a tool to `sale.order` is impossible
declaratively — you would have to rely on the `inputSchema` (which is never enforced by the server; §12).
Real per-tool validation requires adding an arm to `execute_op` in Rust and recompiling.

### Inferences
- **Answer to the key question:** the declarative approach does *not* make per-tool business validation
  impossible in principle — but the only escape hatch (`op.type: "execute"`) escapes in the wrong
  direction: it widens power rather than constraining it. To *narrow* behaviour you must write Rust.
- The reader's own design (35 hand-written domain tools) sits at the opposite end: every tool is a
  validation point, at the cost of a recompile/redeploy per tool. The declarative model buys iteration
  speed and pays in expressiveness and safety.

---

## 10. MCP Resources (`odoo://`)

### Takeaway
Three read-only URI forms parsed by a hand-written string splitter, served through the same client pool;
no templates, no subscriptions, and the metadata resource bypasses the TTL cache the equivalent tool uses.

### Cited Findings
- Documented in code (`rust-mcp/src/mcp/resources.rs:11-14`):
  ```
  odoo://instances                      - List all configured instances
  odoo://{instance}/models              - List models for an instance
  odoo://{instance}/metadata/{model}    - Get model metadata
  ```
- `ResourceUri::parse` strips the 7-char `odoo://` prefix and splits the remainder, rejecting anything
  else with explicit messages (`resources.rs:24-70`); `to_uri()` is the inverse (`resources.rs:74-82`).
- `resources/list` enumerates `odoo://instances` plus one `odoo://{name}/models` per configured instance
  (`resources.rs:86-110`) — metadata URIs are **not** listed (they are unbounded), and there is **no
  `resourceTemplates` support**, so a client cannot discover the metadata form programmatically.
- `resources/read` dispatches to `read_instances` / `read_models` / `read_metadata`
  (`resources.rs:113-122`). `read_models` and `read_metadata` hit the Odoo client directly
  (`resources.rs:146-221`) — `read_metadata` does **not** consult `pool.metadata_cache`, unlike
  `op_get_model_metadata` (`tools.rs:474-478`).
- Wired into the dispatcher at `mcp/mod.rs:143-151`; capabilities advertise `"resources": {}` — i.e. no
  `subscribe`, no `listChanged` (`runtime.rs:90`). Covered by 10 tests in `tests/mcp_resources.rs`.

---

## 11. Notable design decisions and stated rationale

### Takeaway
Rationale is recorded in code comments rather than docs/ADRs, and the recurring theme is
**client-compatibility pragmatism** (Cursor, Claude Desktop) plus **API-reality corrections** (Odoo 19
return shapes, deprecated-but-callable access methods).

### Cited Findings
- *Cursor-driven schema restriction*: "Cursor can be picky about JSON Schema features. Reject schemas that
  likely break Cursor parsing." (`registry.rs:357-358`) — a whole validator, plus a dedicated
  `CursorStdioTransport` (259 LOC, `mcp/cursor_stdio.rs`) and a legacy SSE pair `/sse` + `/messages`
  *"(Cursor supports `SSE` transport option)"* (`http.rs:392-394`).
- *Tolerating clients that skip `initialized`*: "Allow tools/list and prompts/list without initialized
  notification. Some clients (like Cursor) may not send initialized before listing"
  (`runtime.rs:115-120`).
- *Fully declarative by intent*: "Fully declarative: tools are served from tools.json (registry). Note:
  cleanup gating is handled by tool guards (e.g. requiresEnvTrue)." (`mcp/mod.rs:82-83`), reinforced by
  `main.rs:611-612` explicitly demoting the `--enable-cleanup-tools` CLI flag to a compatibility shim.
- *Deprecated-but-callable access API*: `tools.rs:743-745` (quoted in §6) — a deliberate, documented
  trade-off rather than an oversight.
- *Odoo 19 `create` returns an array*: "Odoo v19 /json/2/ create returns an array of IDs, e.g. [42]. We
  handle both array and single integer for compatibility" (`client.rs:314-316`) — defensive coding
  against an API the authors expect to move.
- *Retry policy rationale*: "Retry on 5xx and 429; do not retry auth/4xx." (`client.rs:123`).
- *Batch cap rationale*: "Limit batch size to 100 to prevent abuse" (`tools.rs:802`).
- *Fail-safe reload*: "config reload failed; keeping last good" (`registry.rs:148`).
- *Honest TODO-in-prose*: legacy report auth is "a simplified approach - in production you might need
  session cookies" (`legacy_client.rs:420-421`).
- *Whimsy*: port 3008 is "(inspired by Peugeot 3008)" (`main.rs:549`, `main.rs:638`).
- AI-assisted development is explicit: `.github/copilot-instructions.md` and
  `.github/instructions/instructions.md`, added in `ff82379` ("Add comprehensive AI coding agent
  instructions") and `78d29cf`.

### Gaps
- No `docs/` directory, no ADRs. The upstream repo shows 16 open issues/PRs but the API returned none in
  the plain issue list (they appear to be PRs), so I could not mine issue discussion for rationale.

---

## 12. Weaknesses / risks spotted in the code

### Takeaway
Two genuine correctness bugs, one stale-fork exposure, and a cluster of insecure-by-default choices.

### Cited Findings
1. **`odoo_check_access` always answers "yes".** `"has_access": true` is a literal (`tools.rs:777`) and the
   record-level result is discarded on error via `.ok()` (`tools.rs:771`). An agent using this tool to
   decide whether to attempt a write is being misled. *(Correctness bug.)*
2. **Legacy path silently drops `context` on all 15 methods** (`legacy_client.rs`, the `_context`
   parameters listed in §3). Same MCP tool, same arguments, different semantics depending on the Odoo
   version — and no warning is logged. `lang`, `company_id`, `active_test`, `tz` all vanish on Odoo <19.
   *(Correctness bug, silent.)*
3. **The fork is missing upstream's watcher fix.** Upstream commit `818c0b2` (2026-09-14), *"Fix config
   watcher reload loops on file reads (#61) — Ignore access events in both config watchers to prevent
   self-triggered reloads"*, touches `config_manager/watcher.rs` (+3/−1) and `mcp/registry.rs` (+100/−15)
   — [GitHub API](https://api.github.com/repos/rachmataditiya/odoo-rust-mcp/commits/818c0b2). The code at
   the cloned HEAD therefore has the reload-loop defect: `notify` access events re-trigger `reload()`,
   which re-reads the files, which emits more access events.
4. **Config server on `0.0.0.0:3008`, unauthenticated by default, unconditionally started** — including
   in stdio mode (`main.rs:618-635`, `server.rs:234`, `server.rs:40-47, 135-138`). It serves Odoo
   credentials unmasked (`server.rs:642-644`) and accepts a full `tools.json` rewrite
   (`server.rs:201`), which is remote behaviour injection into the MCP server.
5. **MCP HTTP unauthenticated by default** (`MCP_AUTH_ENABLED` default false, `http.rs:180-183`) with
   `CorsLayer::permissive()` on all routes (`http.rs:399`) and Origin checking off unless
   `MCP_ALLOWED_ORIGINS` is set (`http.rs:144-151`).
6. **Origin allow-list is bypassable by substring**: `origin_str.contains("localhost")` matches
   `https://localhost.attacker.example` (`http.rs:473-475`).
7. **Non-constant-time secret comparison** in both auth paths (`http.rs:546`, `server.rs:57-58`), and
   plaintext UI password in env.
8. **`inputSchema` is published but never enforced.** The server validates only that the *shape* is
   Cursor-safe (`registry.rs:254`); at call time only `op.map` pointers are read (`tools.rs:106`).
   `"additionalProperties": false` and `required` are advisory — a client sending garbage gets whatever
   the pointers happen to find, or a generic "Missing required argument … (map)" that names the *op*
   parameter, not the schema field.
9. **`odoo_create_batch` is non-atomic** and loses the ids of already-created records on partial failure
   (`tools.rs:814-820`).
10. **Unbounded result sizes**: `odoo_search_read` without `limit`, and `odoo_generate_report`'s base64
    PDF, both go into a single text block with no truncation (`tools.rs:271, 450`).
11. **`updated_count` / `deleted_count` report the requested id count, not Odoo's result**
    (`tools.rs:316, 332`) — misleading when ids don't exist or are filtered by record rules.
12. **Base URL path is silently stripped** (`client.rs:23-26`, `legacy_client.rs:30-32`): an Odoo behind a
    reverse-proxy sub-path (`https://host/odoo`) is misconfigured with no error, hitting
    `https://host/json/2/…`.
13. **No rate limiting anywhere** — no token bucket, no concurrency cap, no per-instance throttle. One
    `odoo_search_read` loop can hammer Odoo.
14. **Metadata cache is never invalidated by writes** (§3), so a field added or a model changed stays
    invisible for up to 300 s; and the resource path doesn't share the cache at all.
15. **`odoo_execute`'s argument heuristic is lossy** (`tools.rs:392-428`): kwargs named `ids`, `context`
    or `args` collide with injected keys, and a one-element array of integers is *always* reinterpreted as
    record ids even when the method expects a list argument.
16. ~600 lines of mechanical delegation in `unified_client.rs` — five edits per new Odoo method — is the
    structural cause of drift like #2.

---

## 13. Transferable to the reader's server (Python / FastMCP / XML-RPC / Odoo 19)

### Takeaway
The one high-value import is the **JSON-2 client design**, which is simpler than XML-RPC and maps cleanly
onto a single choke-point function. The guard-by-env-var idea is worth one narrow borrowing. Almost
everything else — enum-over-two-clients, the declarative tool registry, the config UI, the transport
layer — is either already better in the reader's server or actively worse.

### Worth taking

**A. The JSON-2 call contract, concretely (highest value; the reader's instance already exposes `/json/2/`)**
A Python `odoo_json2()` that mirrors `odoo()` would be, per `rust-mcp/src/odoo/client.rs`:
- **URL**: `POST {origin}/json/2/{model}/{method}` — origin only, path/query stripped (`client.rs:74-78`).
  *One endpoint per (model, method)*, versus XML-RPC's single `/xmlrpc/2/object` with `execute_kw`.
  Consequence for the reader: the method whitelist becomes *URL construction*, i.e. the whitelist is
  enforced by which endpoints the code can even build — structurally stronger than a string check.
- **Headers**: `Authorization: bearer <api_key>`, `Content-Type: application/json; charset=utf-8`,
  `X-Odoo-Database: <db>` (`client.rs:50-72`). The **db moves from a positional argument to a header**,
  and **uid/password disappear entirely** — the API key *is* the identity. Per-role isolation via
  dedicated Odoo accounts survives unchanged: one API key per role process, same as today's
  username/password pairs.
- **Body**: flat kwargs, no envelope. Key shape differences from `execute_kw`:
  | operation | XML-RPC `execute_kw` | JSON-2 body |
  |---|---|---|
  | search | `(db,uid,pw,model,'search',[domain],{limit,offset,order})` | `{"domain":…,"limit":…,"offset":…,"order":…}` |
  | read | `…,'read',[ids],{'fields':[…]}` | `{"ids":[…],"fields":[…]}` |
  | create | `…,'create',[vals]` → `int` | `{"vals_list":[vals]}` → **`[id]` (array!)** |
  | write | `…,'write',[ids, vals]` → `True` | `{"ids":[…],"vals":{…}}` → `true` |
  | unlink | `…,'unlink',[ids]` | `{"ids":[…]}` |
  | any method | `…,method,args,kwargs` | kwargs object **is** the body, with `ids`/`context` as top-level keys |
  (`client.rs:221-238, 284-292, 301-312, 345, 360, 405-412`.) **Take the `create` return-shape lesson
  seriously** — the code comment records it as an observed correction (`client.rs:314`), and a Python port
  that assumes `int` will break.
- **Errors**: non-2xx carries `{name, message, arguments, context, debug}` (`odoo/types.rs:4-13`) — that's
  Odoo's exception rendered as JSON, so `name` gives you `odoo.exceptions.AccessDenied` /
  `ValidationError` / `UserError` as a *machine-readable* discriminator. Compare `xmlrpc.client.Fault`,
  where you regex `faultString`. This is a direct upgrade for the reader's error hygiene work: map
  `body.name` → an error class and surface `message` to the agent while logging `debug`.
- **None-marshalling — the specific migration hazard the reader asked about.** XML-RPC has no null by
  default (`allow_none=False` raises on `None`; with `allow_none=True` it emits `<nil/>`), which is why
  Python Odoo clients conventionally send `False` for "empty" and receive `False` for empty
  many2one/char. JSON-2 is plain JSON: `null` is legal on the wire in both directions. This code's
  handling is *not* a model to copy blindly — it sidesteps the question by **omitting keys entirely**
  rather than sending null (`if let Some(v) = limit { body["limit"] = json!(v) }`, `client.rs:228-236`)
  and by treating a received `null` as absent (`opt_value(...).filter(|v| !v.is_null())`,
  `tools.rs:152-154`). The transferable rules are: (1) **omit optional keys instead of sending `null`**;
  (2) on writes, keep sending Odoo's own `False` for "clear this field" — do **not** translate Python
  `None` to JSON `null` and assume Odoo reads it as false-y; (3) on reads, expect `false` (not `null`)
  for empty relational fields, exactly as with XML-RPC, since that is Odoo's ORM convention, not a
  transport artefact. Verify (2) and (3) empirically against the reader's Odoo 19 before relying on them
  — **this repo does not prove them**, because its only evidence is wiremock fixtures the authors wrote
  themselves (§8).
- **Retry policy worth copying verbatim**: retry on 5xx/429/transport only, never 4xx; exponential
  backoff `250ms · 2^attempt`, max 3 (`client.rs:123-140`). The reader's memory already records an
  incident where an SDK's hidden `max_retries=6` burned quota — an explicit, visible, 4xx-excluding
  policy at the choke point is the right shape.
- **Report PDFs are not JSON-2**: `GET /report/pdf/{report}/{ids_csv}` with the same bearer header
  (`client.rs:148-155`). Useful to know before assuming `/json/2/` covers everything.
- **Migration strategy transferable from the enum**: keep `odoo()` as the choke point and add a
  transport switch *inside* it (XML-RPC | JSON-2) selected by config, so the 35 tools are untouched. But
  **learn from their mistake**: their enum lets the two paths diverge silently (`_context` dropped on one
  side). Enforce parity with a shared contract test that runs the *same* call through both transports
  against the same Odoo and diffs the results — the reader's existing GATHER_CASES contract-test pattern
  is exactly the right instrument.

**B. `requiresEnvTrue`-style per-tool guards, as a complement to the global toggle (small, bounded)**
`guards_allow` is checked both when listing and when calling (`registry.rs:210, 224`; `mcp/mod.rs:98`),
and reads the variable **live per call**, so flipping it takes effect without restart. The transferable
idea for the reader is *granularity*: today the reader has one global write toggle from
`ir.config_parameter`; a per-tool (or per-model) key in the same `ir.config_parameter`, read through the
same fail-closed helper, would let a role's `unlink` be disabled while its `create` stays on — with the
reader's existing fail-closed semantics preserved. **Do not** copy the env-var carrier: `ir.config_parameter`
is strictly better (auditable, centrally changeable, already fail-closed) than a process env var that
the local admin UI can rewrite.

**C. `fields_get` attribute projection (tiny, immediately useful)**
The legacy client asks for exactly
`["string","type","help","required","readonly","relation","selection"]` (`legacy_client.rs:380-383`).
For the reader's planned runtime `fields_get` validation of write payloads, that is a good minimal
projection — it gives you existence, writability (`readonly`), `required`, type and `selection` values,
without dragging the full field dictionary into memory or context. Pair it with a TTL cache, but —
unlike this repo — **invalidate it** (their cache is never invalidated by anything, §3).

**D. What their `check_access` teaches, by failing**
Copy the *method choice*, not the implementation: `check_access_rights` (model level) +
`check_access_rule` (record level, needs ids), with the documented reason that Odoo 19's `check_access`
is private and non-RPC-callable (`tools.rs:743-745`). Then do what they didn't: **return the real
answer** instead of a hard-coded `true`, and don't swallow the record-level error. This is a cheap,
concrete addition to the reader's pre-write path — a permission probe before attempting a write,
answering honestly.

**E. Health/observability detail**
`search_count("ir.model", [])` as the cheap liveness probe (`client.rs:568-575`) and a tri-state
`ok/degraded/unhealthy` rollup across instances (`http.rs:344-350`) are both small and sensible for the
reader's 3-4 role processes.

### Not worth copying, and why
- **Language/packaging (Rust, deb/brew/helm/apt, `mcp_rust_sdk`).** Irrelevant to a FastMCP/Python stack,
  and the SDK choice is actively bad — it forced ~1,200 lines of hand-rolled HTTP-transport code that
  FastMCP gives the reader for free.
- **The declarative `tools.json` registry.** It would *delete* the reader's main safety asset. The 35
  domain-specific tools are where validation, defaults and role semantics live; a generic
  `op.type`-driven registry cannot express any of that (§9), and its only escape hatch is
  `odoo_execute`, which is precisely what a method whitelist exists to prevent. The reader's per-tool
  recompile cost is the price of enforceability.
- **Generic CRUD tools (`odoo_execute`, `odoo_workflow_action` with a free-string method).** Directly
  hostile to the reader's method-whitelist design.
- **The multi-instance-by-argument pattern.** `instance` as a caller-supplied argument is routing, not
  isolation. The reader's 3-4 separate processes, each with one dedicated Odoo account and no way to
  address another role's connection, is a strictly stronger boundary. Keep it.
- **The config UI on `0.0.0.0:3008`.** Unauthenticated by default, credentials unmasked, rewrites tool
  definitions remotely (§6). For a server bound to `127.0.0.1` by design, this is a large step backwards.
- **Their auth defaults.** `MCP_AUTH_ENABLED=false` + `CorsLayer::permissive()` + substring-matched
  origins. The reader's `127.0.0.1` binding is a better default than all three combined.
- **Their audit posture.** Zero per-call logging (§7). The reader's event log with argument fingerprint
  and hash-chained audit log with a verifier is far ahead; nothing here improves on it.
- **`odoo_create_batch`'s loop.** Non-atomic, loses ids on partial failure (§12 #9). If the reader wants
  batch create on JSON-2, send the whole `vals_list` in **one** call — the JSON-2 `create` signature
  already takes a list (`client.rs:301-308`), so the batching this repo does in a loop is unnecessary.

### Gaps
- The `None`/`False` marshalling rules above are inferred from how this code *avoids* the question plus
  Odoo ORM convention; I found **no** authoritative statement in this repo about how Odoo 19's `/json/2/`
  treats JSON `null` in write payloads. The reader must probe this against their own Odoo 19 before
  migrating — the existing empirical-probe habit (the masked OR-tuple case) is the right method.
- I could not verify whether Odoo 19's `/json/2/` requires the `X-Odoo-Database` header when only one
  database exists, or whether it accepts `db` some other way; this code only ever sends the header, and
  only when `db` is non-empty (`client.rs:62-70`).
