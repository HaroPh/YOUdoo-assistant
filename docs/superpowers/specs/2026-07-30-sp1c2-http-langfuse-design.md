# SP-1C2: HTTP endpoint + Langfuse tracing — Thiết kế

**Goal:** Mở `backend/src/main.py` — một FastAPI app OpenAI-compatible bọc
`ERPAgent`, đủ để một client HTTP thật (curl, Postman, hay sau này Open
WebUI) trò chuyện được với agent — và gắn Langfuse tracing lên toàn bộ
đường LLM, để mỗi lượt chat sinh ra một trace giải thích được "model nào đã
chạy, vì sao, và tốn bao nhiêu token".

**Vì sao bây giờ:** ADR-009 QĐ M3 buộc eval-gate phải xanh trước khi `/v1`
mở — SP-1C1 đã chạy gate thật và đạt **7/7 PASS** (cổng xanh thật, không
qua ký duyệt). Điều kiện tiên quyết đã thoả.

**Phạm vi đã chốt (brainstorm 2026-07-30):**
- **Chỉ backend `/v1`** — test bằng curl/httpx, KHÔNG dựng Open WebUI lần
  này (dù `requirements.txt` có ghi chú Open WebUI "hoãn sang kế hoạch C" —
  đó là việc khác, làm sau nếu cần).
- Mức kiểm chứng Langfuse: **unit test cho logic** (không cần Langfuse thật)
  **+ một lượt chạy sống thật**, xem UI Langfuse bằng mắt xác nhận trace
  đúng — KHÔNG cần dựng kịch bản chặn mạng Google thật (chỉ cần xác nhận cơ
  chế đúng, không cần tái hiện đúng bài nghiệm thu gốc của SP-1 foundation).
- SSE streaming giữ nguyên như bản tham chiếu: trả nguyên câu rồi emit 1
  content-chunk, KHÔNG phải streaming token-thật (đổi sang streaming thật
  cần đổi `graph.ainvoke` → `graph.astream`, ngoài phạm vi).

---

## §1. Bối cảnh đã có sẵn — không phải thiết kế lại từ đầu

Phần lớn thiết kế cho C2 đã được viết ở
`docs/superpowers/specs/2026-07-28-sp1-foundation-design.md` §1/§5 (lúc đó
gọi chung là "Plan C", trước khi C tách đôi thành C1/C2 ở SP-1C1). Spec này
**kế thừa và cập nhật** phần đó cho khớp kiến trúc thật hiện tại (Router/
RoutedChatModel/catalog.py ra đời ở SP-1A, sau khi spec gốc viết).

**Sẵn có, không cần làm lại:**
- `D:\Project\backend\src\main.py` + `run.py` — bản tham chiếu ĐẦY ĐỦ: FastAPI
  OpenAI-compatible `/v1/chat/completions`, `/v1/models`, `/health`; xử lý
  Open WebUI session headers, "task prompt" phân biệt (R7 hotfix); catch-all
  lỗi trả `ERROR_MSG` lịch sự; `run.py` tự tạo `asyncio.SelectorEventLoop`
  trên Windows (psycopg3 async không tương thích `ProactorEventLoop` mặc
  định của uvicorn 0.46 — đã xác nhận thật ở repo nguồn).
- `backend/src/agents/erp_agent.py`'s `ERPAgent` (đã port ở SP-1B) có
  interface **khớp hệt** những gì `main.py` gốc cần:
  `setup()`/`chat(messages, thread_id, reset_if_fresh)`/
  `answer_stateless(content)`/`aclose()`/`tool_names` — port `main.py` gần
  như nguyên văn.
- `backend/src/llm/router.py`'s `RoutedChatModel.last_decision` (property,
  dòng ~349) — đã có sẵn, comment ghi rõ mục đích:
  *"kế hoạch C đổ nó vào span Langfuse"*. Mang đúng
  `RouteDecision(role, spec: ModelSpec, fallback_depth, skipped: tuple[SkippedLink,...], base_tokens)`.
- `.env.example` đã có `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`.
- ADR-011 mục 3 đã chốt: Langfuse **self-host**, không dùng Cloud (rủi ro dữ
  liệu khác API call thoáng qua; SP-3 fan-out sẽ chạm trần observation của
  bản Cloud).

**Chưa có, C2 phải làm:**
- `backend/src/main.py`, `backend/run.py` — chưa tồn tại ở Youdoo.
- `backend/src/llm/tracing.py` — chưa tồn tại.
- `docker-compose.yml` — chưa có profile `observability`.
- `requirements.txt` — chưa có Langfuse SDK.

---

## §2. Bố cục file

```
backend/
├── src/
│   ├── main.py                 MỚI — port nguyên văn D:\Project\backend\src\main.py
│   ├── agents/
│   │   └── erp_agent.py        SỬA — ERPAgent.setup() dựng self._handler;
│   │                            chat()/_invoke_fresh()/answer_stateless()
│   │                            merge callbacks vào config khi gọi LLM/graph
│   └── llm/
│       ├── router.py           SỬA — RoutedChatModel.ainvoke()/.invoke() gọi
│       │                        tracing.annotate_current_span() (2 chỗ)
│       └── tracing.py          MỚI — get_handler() + annotate_current_span()
├── run.py                      MỚI — port nguyên văn D:\Project\backend\run.py
├── requirements.txt             THÊM: langfuse
└── tests/
    ├── llm/test_tracing.py     MỚI
    ├── llm/test_router.py       THÊM test cho annotate_current_span() call site
    └── test_main.py             MỚI
docker-compose.yml                THÊM: profile `observability`
```

---

## §3. `main.py` + `run.py` — port gần nguyên văn

`main.py` port từ `D:\Project\backend\src\main.py`, đổi đúng 1 chỗ:
`from src.agents.erp_agent import ERPAgent` — đường import ĐÃ khớp quy ước
Youdoo (`from src.X` không `from backend.src.X`), không cần sửa. Toàn bộ
logic (`lifespan`, `_filter_messages`, `_explicit_session`,
`_is_owui_task_prompt`, `_derive_thread_id`, `chat_completions`, SSE
`sse()`) port nguyên văn — không có gì trong đó phụ thuộc LiteLLM/model
local đã bị SP-1 xoá.

`run.py` port nguyên văn — constraint Windows/psycopg3/ProactorEventLoop áp
dụng y hệt cho Youdoo (cùng OS, cùng psycopg3 async qua
`AsyncPostgresSaver`/`AsyncConnectionPool` trong `ERPAgent.setup()`).

`MODEL_ID = "erp-assistant"` giữ nguyên (không phải thuộc tính kỹ thuật,
đổi tuỳ ý sau nếu cần, không phải quyết định phải chốt bây giờ).

`BACKEND_HOST`/`BACKEND_PORT` đọc từ env (mặc định `0.0.0.0`/`8000`,
`run.py` gốc đã làm vậy) — thêm 2 dòng vào `.env.example` nếu chưa có.

---

## §4. Langfuse — `tracing.py`

### 4.1 `get_handler()`

```python
def get_handler() -> "CallbackHandler | None":
    """Trả CallbackHandler của Langfuse, hoặc None nếu thiếu env hoặc không
    kết nối được. Không có đường nào để lỗi ở đây làm hỏng một lượt chat —
    caller luôn nhận None hoặc handler hợp lệ, không bao giờ nhận exception."""
```

Đọc `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`; thiếu bất
kỳ biến nào → trả `None` ngay, log warning một lần (không log mỗi request).
Dựng `CallbackHandler` trong `try/except` — lỗi kết nối/khởi tạo → `None` +
log, không throw.

**`ERPAgent` sở hữu handler, `main.py` KHÔNG đổi gì liên quan Langfuse.**
`ERPAgent.setup()` gọi `tracing.get_handler()` **một lần** lúc khởi động
(cùng chỗ dựng `self._llms`/`self._pool`/`self.graph`), lưu vào
`self._handler`.

**`chat()` — gắn callback MỘT LẦN lúc dựng `config`, không rải rác nhiều
điểm gọi.** `chat()` hiện có 4 điểm dùng biến `config` sau khi dựng nó
(`aget_state`, 2 nhánh `ainvoke` resume/discard, và truyền xuống
`_invoke_fresh`) — thay vì sửa cả 4 chỗ, sửa đúng 1 chỗ dựng:

```python
config = {"configurable": {"thread_id": tid}}
if self._handler:
    config["callbacks"] = [self._handler]
```

Mọi lời gọi sau đó dùng chung biến `config` này (kể cả bên trong
`_invoke_fresh(messages, config)`) tự động mang callback — không cần sửa gì
thêm ở các điểm gọi. `answer_stateless()` (không đi qua `chat()`, gọi thẳng
`self._llms["synthesis"].ainvoke(...)`) tự dựng `config` tương tự tại chỗ
gọi đó.

Nếu `self._handler is None` (Langfuse tắt/lỗi), `config` không có key
`callbacks` — graph/LLM chạy y hệt không có Langfuse, không nhánh rẽ nào
khác trong logic nghiệp vụ. `main.py`'s `lifespan()` giữ nguyên y hệt bản
tham chiếu (`agent = ERPAgent(); await agent.setup(); ...`) — nó không biết
và không cần biết Langfuse tồn tại, mọi việc đã nằm trong `ERPAgent`.

### 4.2 `annotate_current_span()` — điểm quyết định chính

**Quyết định (đã duyệt ở brainstorm):** gắn thuộc tính span NGAY BÊN TRONG
`RoutedChatModel.ainvoke()`/`.invoke()` (`router.py` dòng ~372/365), ngay
sau `self._ghi_quyet_dinh(result.decision)`, trước `return result.message`
— **không** sửa bất kỳ node nào trong `agents/nodes.py`.

```python
async def ainvoke(self, input, config=None, **kwargs):
    result = await self._router.ainvoke(self._role, input,
                                        tools=self._tools, pin=self._pin,
                                        config=config,
                                        tool_kwargs=self._tool_kwargs,
                                        **kwargs)
    self._ghi_quyet_dinh(result.decision)
    tracing.annotate_current_span(result.decision, result)  # MỚI
    return result.message
```

`tracing.annotate_current_span(decision: RouteDecision, result: InvokeResult) -> None`:
đọc span Langfuse **hiện tại** (SDK track bằng contextvar riêng của nó, độc
lập với `_QUYET_DINH` của Router — không xung đột) và gắn:

| Thuộc tính | Nguồn |
|---|---|
| `role` | `decision.role` |
| `alias` | `decision.spec.alias` |
| `provider` | `decision.spec.provider` |
| `upstream` | `decision.spec.upstream` |
| `fallback_depth` | `decision.fallback_depth` (0 = lựa chọn đầu) |
| `budget_verdict` mỗi mắt xích bị bỏ qua | `[(s.alias, s.verdict.value) for s in decision.skipped]` |
| `est_tokens` | `decision.base_tokens` |
| `actual_tokens` | `result.total_tokens` (KHÔNG cộng `prompt_tokens+completion_tokens` — bất biến toàn dự án) |

Không có span đang mở (Langfuse tắt, hoặc gọi ngoài context có callback —
vd `evals/run_eval.py` gọi `RoutedChatModel` trực tiếp không qua
`graph.ainvoke`) → no-op êm, `try/except` nuốt mọi lỗi từ SDK, không log
lặp lại mỗi lần (khác `get_handler()`'s log-once, ở đây im lặng hoàn toàn vì
đây là đường nóng, gọi mỗi lượt LLM).

**Hệ quả phụ có lợi:** vì enrichment nằm trong `RoutedChatModel` (điểm
nghẽn cổ chai duy nhất cho MỌI lời gọi LLM), **eval harness** (`evals/
run_eval.py`, `jobs/eval_gate.py`) cũng tự động được làm giàu nếu ai đó bật
Langfuse khi chạy eval — miễn phí, không cần code riêng.

### 4.3 Hạ tầng — `docker-compose.yml` profile `observability`

```yaml
services:
  langfuse-web: ...
  langfuse-worker: ...
  clickhouse: ...
  redis: ...
  minio: ...
```

Dùng chung Postgres instance `youdoo-postgres` (schema riêng, KHÔNG container
Postgres thứ hai). Tất cả service này đặt `profiles: ["observability"]` —
`docker compose up` mặc định KHÔNG kéo theo; phải
`docker compose --profile observability up` mới lên. Việc này giữ nguyên ý
định gốc trong bố cục §1 của spec SP-1 foundation.

### 4.4 `requirements.txt`

Thêm `langfuse` (Python SDK, bản mới nhất tương thích `langchain-core==1.4.8`
đã ghim — kiểm tương thích lúc cài, không ghim version cụ thể trước khi xác
nhận không xung đột).

---

## §5. Testing

**Unit (mặc định, không mạng, không Postgres):**
- `get_handler()` trả `None` khi thiếu 1/3 biến env (test cả 3 trường hợp
  thiếu riêng lẻ).
- `get_handler()` trả `None` (không throw) khi `CallbackHandler(...)` ném
  lỗi giả lập (monkeypatch).
- `annotate_current_span()` không throw khi không có span nào đang mở
  (gọi trực tiếp, không qua callback nào).
- `annotate_current_span()` gắn đúng field từ một `RouteDecision`/
  `InvokeResult` giả — dùng Langfuse SDK's test double/mock nếu có, hoặc
  monkeypatch điểm SDK gọi ra để bắt lại đúng dict thuộc tính đã gửi.
- `main.py`: `D:\Project\backend\tests\` KHÔNG có test riêng cho
  `main.py` (đã xác nhận — không có file `test_main.py` nào ở repo nguồn) —
  viết MỚI hoàn toàn cho `_filter_messages`/`_is_owui_task_prompt`/
  `_derive_thread_id` (3 hàm thuần, dễ test độc lập không cần FastAPI
  TestClient).
- `chat_completions` trả `ERROR_MSG` khi `agent.chat()` ném lỗi (mock agent).

**Live (chạy tay, đánh dấu `@pytest.mark.live` cho phần tự động hoá được,
phần còn lại là bước thủ công ghi trong báo cáo):**
1. `docker compose --profile observability up -d` (+ `youdoo-postgres` như
   thường lệ).
2. `cd backend && python run.py`.
3. `curl -X POST http://localhost:8000/v1/chat/completions -d '{"messages":[{"role":"user","content":"..."}]}'`
   — xác nhận trả lời hợp lệ.
4. Mở Langfuse UI (`http://localhost:3001` theo `.env.example`'s
   `LANGFUSE_HOST`), xác nhận bằng mắt: trace xuất hiện, span lồng nhau
   đúng cây LangGraph, thuộc tính `role`/`alias`/`provider`/`fallback_depth`
   hiện đúng trên span LLM tương ứng.

---

## §6. Ngoài phạm vi (ghi rõ để không ai ngạc nhiên)

- Open WebUI — hoãn, không phải việc của C2 này.
- Streaming token-thật — `ERPAgent.chat()` trả `str` nguyên khối, giữ SSE
  giả (1 content-chunk) như bản tham chiếu.
- Bài nghiệm thu chặn-Google-giữa-chừng của spec SP-1 foundation gốc — không
  tái hiện thật (tốn thời gian dựng chặn mạng); `fallback_depth`/
  `budget_verdict` được xác nhận đúng qua unit test với `RouteDecision` giả
  thay vì qua kịch bản mạng thật.
- Sampling rate Langfuse — 100% (spec gốc: "SP-3 mới là lúc bàn sampling").

---

## §7. "SP-1C2 xong" nghĩa là

1. `backend/src/main.py` + `run.py` chạy được, `/health`/`/v1/models`/
   `/v1/chat/completions` trả lời đúng qua curl.
2. `tracing.py` có test chứng minh no-op an toàn ở mọi nhánh lỗi (không
   phải "đã viết try/except", mà "đã chứng minh không throw").
3. `RoutedChatModel.ainvoke()`/`.invoke()` gọi `annotate_current_span()` —
   test xác nhận đúng field được gắn từ `RouteDecision`/`InvokeResult` giả.
4. Lượt chạy sống thật: Langfuse UI hiện trace + span đúng cây, thuộc tính
   đúng — xác nhận bằng mắt, ghi lại bằng ảnh chụp màn hình hoặc mô tả
   trong báo cáo cuối.
5. `docker-compose.yml`'s profile `observability` không ảnh hưởng
   `docker compose up` mặc định (test: chạy `up` không kèm profile, xác
   nhận không có container langfuse/clickhouse/redis/minio nào được tạo).
6. Toàn bộ test 2 chế độ (mặc định + `-m integration`) vẫn xanh, không hồi
   quy bất cứ đâu trong `evals/`/`jobs/`/`agents/`/`llm/` đã có.
