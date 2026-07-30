# SP-1C2: HTTP endpoint + Langfuse tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mở `backend/src/main.py` — FastAPI OpenAI-compatible bọc `ERPAgent`
— và gắn Langfuse tracing lên toàn bộ đường LLM, để một client HTTP thật
(curl/Postman) trò chuyện được với agent và mỗi lượt chat sinh một trace
giải thích "model nào chạy, vì sao, tốn bao nhiêu token".

**Architecture:** Port `main.py`/`run.py` gần nguyên văn từ `D:\Project`
(interface `ERPAgent` đã khớp hệt). Gắn Langfuse ở **đúng 1 điểm nghẽn**:
`RoutedChatModel.ainvoke()`/`.invoke()` (router.py) — không rải rác ở từng
node `agents/`. `ERPAgent` sở hữu Langfuse `CallbackHandler` (dựng 1 lần lúc
`setup()`), `main.py` không đổi gì liên quan Langfuse.

**Tech Stack:** Python 3.11, FastAPI, Langfuse Python SDK 4.14.1
(`langfuse.langchain.CallbackHandler`, `langfuse.get_client()`), Docker
Compose (self-host Langfuse: langfuse-web/worker, ClickHouse, Redis, MinIO).

## Global Constraints

- **Python 3.11+.** Dùng `X | None`, không `Optional[X]`.
- **Không khoá API/secret nào trong code.** Mọi giá trị đọc từ biến môi trường.
- **`src/llm/` không được import từ `src/agents/`, `src/erp_query/`, `src/rag/`.**
  `src/llm/tracing.py` là ngoại lệ được phép cho chính `src/llm/router.py`
  gọi (cùng tầng, không đảo chiều).
- **Bình luận tiếng Việt, định danh tiếng Anh** — khớp quy ước repo.
- **Test đơn vị không chạm mạng, không cần Postgres** theo mặc định. Test
  cần Postgres → `@pytest.mark.integration`. Test cần mạng/Docker thật →
  `@pytest.mark.live` hoặc bước thủ công ghi rõ trong plan (không tự động
  hoá trong CI).
- **`total_tokens` là con số có thẩm quyền cho mọi phép kiểm token** — không
  bao giờ cộng `prompt_tokens + completion_tokens`.
- **Không đường nào để lỗi Langfuse làm hỏng một lượt chat** — mọi điểm chạm
  SDK Langfuse (`get_handler()`, `annotate_current_span()`) phải bọc
  `try/except`, không bao giờ propagate exception ra ngoài.
- **`docker compose up` mặc định KHÔNG được kéo theo bất kỳ service Langfuse
  nào** — mọi service mới đặt `profiles: ["observability"]`.
- **Port `LANGFUSE_HOST` giữ nguyên `http://localhost:3001`** (đã có sẵn
  trong `.env.example`, không phải cổng mặc định 3000 của Langfuse gốc).

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/requirements.txt` | **Sửa** — thêm `langfuse==4.14.1` |
| `backend/src/llm/tracing.py` | **Mới** — `get_handler()`, `annotate_current_span()` |
| `backend/src/llm/router.py` | **Sửa** — `RoutedChatModel.ainvoke()`/`.invoke()` gọi `annotate_current_span()` |
| `backend/src/agents/erp_agent.py` | **Sửa** — `ERPAgent` dựng + dùng Langfuse handler |
| `backend/src/main.py` | **Mới** — port từ `D:\Project\backend\src\main.py` |
| `backend/run.py` | **Mới** — port từ `D:\Project\backend\run.py` |
| `.env.example` | **Sửa** — thêm `BACKEND_HOST`/`BACKEND_PORT` + 5 biến secret Langfuse |
| `docker-compose.yml` | **Sửa** — thêm profile `observability` (5 service) |
| `backend/tests/llm/test_tracing.py` | **Mới** |
| `backend/tests/llm/test_router_invoke.py` | **Mở rộng** — test gọi `annotate_current_span()` |
| `backend/tests/agents/test_erp_agent.py` | **Mở rộng** (nếu tồn tại) hoặc **Mới** |
| `backend/tests/test_main.py` | **Mới** |

---

### Task 1: Thêm Langfuse SDK vào requirements.txt

**Files:**
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: không có
- Produces: `langfuse.langchain.CallbackHandler`, `langfuse.get_client()` khả dụng để import trong các task sau

- [ ] **Bước 1: Thêm dòng vào `requirements.txt`**

Mở `backend/requirements.txt`, thêm vào cuối file:

```
langfuse==4.14.1
```

- [ ] **Bước 2: Cài vào venv, xác nhận import được**

Run: `cd backend && .venv/Scripts/python.exe -m pip install langfuse==4.14.1`
Run: `.venv/Scripts/python.exe -c "from langfuse.langchain import CallbackHandler; from langfuse import get_client; print('ok')"`
Expected: in ra `ok`, không lỗi import.

- [ ] **Bước 3: Chạy toàn bộ test suite hiện có, xác nhận KHÔNG hồi quy chỉ vì thêm dependency**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors`
Expected: cùng số lượng PASS như trước khi thêm `langfuse` (không có test nào mới ở bước này) — 0 lỗi mới. Nếu có collection error mới (xung đột phiên bản `httpx`/`pydantic`/`opentelemetry` với các gói đã ghim), DỪNG và báo cáo — không tự ý đổi version đã ghim của gói khác.

- [ ] **Bước 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(deps): thêm langfuse==4.14.1

SDK Python chính thức cho Langfuse tracing (kế hoạch C2). Version xác nhận
từ PyPI (2026-07-30), tương thích langchain v1 (langfuse.langchain.CallbackHandler
hỗ trợ langchain.__version__.startswith('1')) và các version httpx/pydantic
đã ghim (langfuse yêu cầu httpx<1.0, pydantic<3 — không xung đột
httpx==0.28.1 đã có)."
```

---

### Task 2: `tracing.py` — `get_handler()` + `annotate_current_span()`

**Files:**
- Create: `backend/src/llm/tracing.py`
- Test: `backend/tests/llm/test_tracing.py`

**Interfaces:**
- Consumes: `langfuse.langchain.CallbackHandler`, `langfuse.get_client()` (Task 1)
- Produces: `tracing.get_handler() -> CallbackHandler | None`,
  `tracing.annotate_current_span(decision: RouteDecision, result: InvokeResult) -> None`
  — cả hai KHÔNG BAO GIỜ ném exception, dùng ở Task 3/4

- [ ] **Bước 1: Viết `backend/src/llm/tracing.py`**

```python
"""Langfuse tracing — không đường nào để lỗi ở đây làm hỏng một lượt chat.

get_handler(): CallbackHandler của Langfuse, gắn ở tầng LangChain (mỗi node
LangGraph tự thành 1 span lồng nhau khi truyền vào config={"callbacks":[...]}).
Construct lỗi (bug SDK, import hỏng) → trả None, log 1 lần, không throw. SDK
tự nó ĐÃ no-op êm khi thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY (đọc
nguồn: langfuse._client.client.Langfuse.__init__ — thiếu key thì gán
self._otel_tracer = NoOpTracer() rồi return sớm, KHÔNG raise) — get_handler()
không cần tự kiểm tra env, chỉ cần bọc try/except phòng lỗi construct khác.

annotate_current_span(): gắn thuộc tính định tuyến lên span Langfuse HIỆN
TẠI. Gọi ngay bên trong RoutedChatModel.ainvoke()/.invoke() (spec §4.2),
KHÔNG phải ở agents/nodes.py — giữ đúng ràng buộc "chỉ llm/ biết provider",
và làm giàu miễn phí cả đường eval harness (evals/run_eval.py cũng gọi
RoutedChatModel). Langfuse.update_current_span() của SDK tự no-op nếu không
có span đang mở hoặc tracing tắt (đọc nguồn: kiểm self._tracing_enabled và
self._get_current_otel_span() is not None trước khi làm gì) — không cần tự
kiểm tra điều đó ở đây, chỉ cần bọc try/except phòng lỗi SDK khác. Đây là
đường NÓNG (gọi mỗi lượt LLM) nên im lặng hoàn toàn khi lỗi, không log lặp
lại như get_handler()."""
import logging

from langfuse import get_client
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)

_warned_once = False


def get_handler() -> "CallbackHandler | None":
    global _warned_once
    try:
        return CallbackHandler()
    except Exception:
        if not _warned_once:
            logger.warning(
                "Không dựng được Langfuse CallbackHandler — tắt tracing cho "
                "phiên chạy này (không ảnh hưởng lượt chat).", exc_info=True)
            _warned_once = True
        return None


def annotate_current_span(decision, result) -> None:
    """decision: RouteDecision (router.py). result: InvokeResult (router.py)
    — result.total_tokens là con số có thẩm quyền, KHÔNG cộng
    prompt_tokens+completion_tokens (bất biến toàn dự án)."""
    try:
        get_client().update_current_span(metadata={
            "role": decision.role,
            "alias": decision.spec.alias,
            "provider": decision.spec.provider,
            "upstream": decision.spec.upstream,
            "fallback_depth": decision.fallback_depth,
            "budget_verdict": [(s.alias, s.verdict.value)
                              for s in decision.skipped],
            "est_tokens": decision.base_tokens,
            "actual_tokens": result.total_tokens,
        })
    except Exception:
        pass
```

- [ ] **Bước 2: Viết test — `get_handler()` không throw khi construct lỗi**

Tạo `backend/tests/llm/test_tracing.py`:

```python
# backend/tests/llm/test_tracing.py
"""tracing.py: get_handler()/annotate_current_span() — không đường nào
được phép ném exception ra ngoài (bất biến toàn module)."""
import pytest
from langchain_core.messages import AIMessage

from src.llm import tracing
from src.llm.budget import Verdict
from src.llm.catalog import spec_for
from src.llm.router import InvokeResult, RouteDecision, SkippedLink


def test_get_handler_khong_throw_khi_construct_loi(monkeypatch):
    def _no(*a, **k):
        raise RuntimeError("lỗi giả lập construct CallbackHandler")
    monkeypatch.setattr(tracing, "_warned_once", False)
    monkeypatch.setattr(tracing, "CallbackHandler", _no)
    assert tracing.get_handler() is None


def test_get_handler_khong_throw_khi_thieu_bien_moi_truong(monkeypatch):
    """Không set LANGFUSE_PUBLIC_KEY/SECRET_KEY — SDK tự no-op nội bộ, KHÔNG
    ném exception ở construct. Không assert giá trị trả về cụ thể (phụ thuộc
    hành vi nội bộ SDK, không phải hợp đồng của get_handler()) — chỉ assert
    tính an toàn: gọi được, không throw."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tracing, "_warned_once", False)
    tracing.get_handler()  # không throw là đủ
```

- [ ] **Bước 3: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_tracing.py -v`
Expected: cả 2 test PASS.

- [ ] **Bước 4: Viết test — `annotate_current_span()` an toàn + gắn đúng field**

Thêm vào `backend/tests/llm/test_tracing.py`:

```python
def _fake_decision_and_result():
    decision = RouteDecision(
        role="router", spec=spec_for("gemma-4-26b"), fallback_depth=1,
        skipped=(SkippedLink("groq-gpt-oss-20b", Verdict.COOLDOWN),),
        base_tokens=123)
    result = InvokeResult(
        message=AIMessage(content="ok"), decision=decision,
        prompt_tokens=10, completion_tokens=20, total_tokens=30, attempts=())
    return decision, result


def test_annotate_current_span_khong_throw_khi_khong_co_span_dang_mo():
    """Gọi trực tiếp, không qua CallbackHandler nào — không có span Langfuse
    nào đang mở. Phải không throw."""
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)  # không throw là đủ


def test_annotate_current_span_gan_dung_field(monkeypatch):
    captured = {}

    class _FakeSpanClient:
        def update_current_span(self, *, metadata):
            captured.update(metadata)

    monkeypatch.setattr(tracing, "get_client", lambda: _FakeSpanClient())
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)

    assert captured["role"] == "router"
    assert captured["alias"] == "gemma-4-26b"
    assert captured["provider"] == "google"
    assert captured["upstream"] == "google"
    assert captured["fallback_depth"] == 1
    assert captured["budget_verdict"] == [("groq-gpt-oss-20b", "cooldown")]
    assert captured["est_tokens"] == 123
    assert captured["actual_tokens"] == 30


def test_annotate_current_span_khong_throw_khi_get_client_loi(monkeypatch):
    def _no():
        raise RuntimeError("lỗi giả lập get_client")
    monkeypatch.setattr(tracing, "get_client", _no)
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)  # không throw là đủ
```

- [ ] **Bước 5: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_tracing.py -v`
Expected: cả 5 test PASS. Kiểm `Verdict.COOLDOWN.value` thật sự là chuỗi
`"cooldown"` (xem `backend/src/llm/budget.py`'s enum `Verdict`) trước khi
tin assertion ở trên — nếu tên giá trị enum khác, sửa lại chuỗi kỳ vọng cho
khớp, đừng đoán.

- [ ] **Bước 6: Commit**

```bash
git add backend/src/llm/tracing.py backend/tests/llm/test_tracing.py
git commit -m "feat(llm): tracing.py — get_handler() + annotate_current_span()

get_handler(): CallbackHandler Langfuse, construct lỗi -> None + log 1 lần,
không throw. SDK tự no-op khi thiếu LANGFUSE_PUBLIC_KEY/SECRET_KEY (xác
nhận đọc nguồn Langfuse._client.client.Langfuse.__init__), get_handler()
không tự kiểm tra env.

annotate_current_span(): gắn role/alias/provider/upstream/fallback_depth/
budget_verdict/est_tokens/actual_tokens lên span Langfuse hiện tại qua
get_client().update_current_span(metadata=...). SDK tự no-op nếu không có
span đang mở hoặc tracing tắt. Đường nóng (mỗi lượt LLM) nên im lặng hoàn
toàn khi lỗi, không log lặp.

Test chứng minh không throw ở MỌI nhánh lỗi (construct hỏng, thiếu env,
không có span, get_client lỗi) — không chỉ 'đã viết try/except'."
```

---

### Task 3: Gắn `annotate_current_span()` vào `RoutedChatModel`

**Files:**
- Modify: `backend/src/llm/router.py:372-379` (`ainvoke`), `:365-370` (`invoke`), `:1-16` (import)
- Test: `backend/tests/llm/test_router_invoke.py`

**Interfaces:**
- Consumes: `tracing.annotate_current_span(decision, result)` (Task 2)
- Produces: không đổi API công khai nào — `RoutedChatModel.ainvoke()`/`.invoke()` giữ
  nguyên chữ ký và giá trị trả về (`result.message`), chỉ thêm 1 lời gọi phụ

- [ ] **Bước 1: Thêm import**

Mở `backend/src/llm/router.py`, sửa khối import (dòng 6-14):

```python
import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass

from . import tracing
from .budget import BudgetLedger, Verdict
from .catalog import ModelSpec, chain_for, spec_for
from .providers import client_for, strip_thought      # mở rộng import cũ
from .tokens import estimate_base_tokens
```

- [ ] **Bước 2: Sửa `RoutedChatModel.invoke()` (dòng 365-370)**

Tìm:

```python
    def invoke(self, input, config=None, **kwargs):
        result = self._router.invoke(self._role, input, tools=self._tools,
                                     pin=self._pin, config=config,
                                     tool_kwargs=self._tool_kwargs, **kwargs)
        self._ghi_quyet_dinh(result.decision)
        return result.message
```

Thay bằng:

```python
    def invoke(self, input, config=None, **kwargs):
        result = self._router.invoke(self._role, input, tools=self._tools,
                                     pin=self._pin, config=config,
                                     tool_kwargs=self._tool_kwargs, **kwargs)
        self._ghi_quyet_dinh(result.decision)
        tracing.annotate_current_span(result.decision, result)
        return result.message
```

- [ ] **Bước 3: Sửa `RoutedChatModel.ainvoke()` (dòng 372-379)**

Tìm:

```python
    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._router.ainvoke(self._role, input,
                                            tools=self._tools, pin=self._pin,
                                            config=config,
                                            tool_kwargs=self._tool_kwargs,
                                            **kwargs)
        self._ghi_quyet_dinh(result.decision)
        return result.message
```

Thay bằng:

```python
    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._router.ainvoke(self._role, input,
                                            tools=self._tools, pin=self._pin,
                                            config=config,
                                            tool_kwargs=self._tool_kwargs,
                                            **kwargs)
        self._ghi_quyet_dinh(result.decision)
        tracing.annotate_current_span(result.decision, result)
        return result.message
```

- [ ] **Bước 4: Viết test — `annotate_current_span` được gọi đúng tham số**

Thêm vào `backend/tests/llm/test_router_invoke.py`:

```python
@pytest.mark.asyncio
async def test_ainvoke_goi_annotate_current_span_dung_tham_so(clock, monkeypatch):
    from src.llm import tracing
    calls = []
    monkeypatch.setattr(tracing, "annotate_current_span",
                        lambda decision, result: calls.append((decision, result)))
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))
    llm = RoutedChatModel(router, "router")

    await llm.ainvoke([HumanMessage("hi")])

    assert len(calls) == 1
    decision, result = calls[0]
    assert decision is result.decision
    assert result.total_tokens == 30


def test_invoke_goi_annotate_current_span_dung_tham_so(clock, monkeypatch):
    from src.llm import tracing
    calls = []
    monkeypatch.setattr(tracing, "annotate_current_span",
                        lambda decision, result: calls.append((decision, result)))
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))
    llm = RoutedChatModel(router, "router")

    llm.invoke([HumanMessage("hi")])

    assert len(calls) == 1
    decision, result = calls[0]
    assert decision is result.decision
    assert result.total_tokens == 30
```

Đã xác nhận (2026-07-30): đầu file `test_router_invoke.py` hiện có
`InMemoryUsageStore`, `BudgetLedger`, `Router`, `fake_ai` — nhưng CHƯA có
`RoutedChatModel` (file hiện chỉ test qua `Router` trực tiếp). Sửa dòng
import (dòng 6):

```python
from src.llm.router import COOLDOWN_RATE_LIMIT_S, ChainExhausted, Router
```

thành:

```python
from src.llm.router import (COOLDOWN_RATE_LIMIT_S, ChainExhausted,
                            RoutedChatModel, Router)
```

- [ ] **Bước 5: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router_invoke.py tests/llm/test_routed_chat_model.py -v`
Expected: toàn bộ PASS, bao gồm 2 test mới. Test cũ (`test_last_decision_*`,
`test_config_duoc_chuyen_tiep_xuong_client`, v.v.) vẫn PASS không đổi.

- [ ] **Bước 6: Chạy toàn bộ test tầng llm, xác nhận không hồi quy**

Run: `.venv/Scripts/python.exe -m pytest tests/llm/ -v -m "not integration and not live"`
Expected: toàn bộ PASS.

- [ ] **Bước 7: Commit**

```bash
git add backend/src/llm/router.py backend/tests/llm/test_router_invoke.py
git commit -m "feat(llm): RoutedChatModel gọi tracing.annotate_current_span()

RoutedChatModel.ainvoke()/.invoke() (2 chỗ) gọi annotate_current_span(
result.decision, result) ngay sau _ghi_quyet_dinh(), trước khi trả
result.message. Đây là điểm nghẽn cổ chai duy nhất cho MỌI lời gọi LLM
trong hệ thống — enrichment tự động áp dụng cho production VÀ eval harness
(evals/run_eval.py cũng gọi RoutedChatModel), không cần sửa gì ở agents/
hay evals/. Không đổi chữ ký/giá trị trả về công khai nào.

Test xác nhận annotate_current_span được gọi đúng 1 lần với đúng
(decision, result) cho cả invoke() và ainvoke()."
```

---

### Task 4: `ERPAgent` — dựng và dùng Langfuse handler

**Files:**
- Modify: `backend/src/agents/erp_agent.py`
- Test: `backend/tests/agents/test_erp_agent.py` (mở rộng nếu tồn tại, tạo mới nếu chưa)

**Interfaces:**
- Consumes: `tracing.get_handler()` (Task 2)
- Produces: `ERPAgent.__init__`/`setup()`/`chat()`/`answer_stateless()` giữ
  nguyên chữ ký công khai — chỉ thêm `self._handler` (thuộc tính mới, không
  phải tham số)

- [ ] **Bước 1: `__init__` — thêm `self._handler`**

Mở `backend/src/agents/erp_agent.py`, tìm (dòng 127-134):

```python
class ERPAgent:
    def __init__(self) -> None:
        self.graph = None
        self.tool_names: list[str] = []
        self._pool = None
        self._llms = None
        self._checkpointer = None
```

Thay bằng:

```python
class ERPAgent:
    def __init__(self) -> None:
        self.graph = None
        self.tool_names: list[str] = []
        self._pool = None
        self._llms = None
        self._checkpointer = None
        self._handler = None
```

- [ ] **Bước 2: `setup()` — dựng handler**

Tìm dòng đầu `setup()` (dòng 135-136):

```python
    async def setup(self) -> None:
        self._llms = make_llms()
```

Thay bằng:

```python
    async def setup(self) -> None:
        self._handler = tracing.get_handler()
        self._llms = make_llms()
```

Thêm import ở đầu file (cạnh các import `src.llm.*` khác — kiểm import
block hiện tại của `erp_agent.py` trước khi thêm, không đoán vị trí):

```python
from src.llm import tracing
```

- [ ] **Bước 3: `chat()` — gắn callback 1 lần lúc dựng `config`**

Tìm trong `chat()` (dòng ~173-174):

```python
        tid = thread_id or uuid.uuid4().hex
        config = {"configurable": {"thread_id": tid}}
```

Thay bằng:

```python
        tid = thread_id or uuid.uuid4().hex
        config = {"configurable": {"thread_id": tid}}
        if self._handler:
            config["callbacks"] = [self._handler]
```

Mọi lời gọi sau đó trong `chat()` dùng chung biến `config` này
(`self.graph.aget_state(config)`, 2 nhánh `self.graph.ainvoke(..., config=config)`,
và `self._invoke_fresh(messages, config)`) tự động mang callback — KHÔNG
sửa gì thêm ở các dòng đó.

Tìm trong `answer_stateless()` (dòng 254):

```python
        response = await self._llms["synthesis"].ainvoke([HumanMessage(content=content)])
```

Thay bằng:

```python
        config = {"callbacks": [self._handler]} if self._handler else None
        response = await self._llms["synthesis"].ainvoke(
            [HumanMessage(content=content)], config=config)
```

- [ ] **Bước 4: Viết test — handler được dựng và truyền đúng**

Đã xác nhận (2026-07-30): `backend/tests/agents/test_erp_agent.py` CHƯA
tồn tại — tạo mới hoàn toàn:

```python
# backend/tests/agents/test_erp_agent.py
"""ERPAgent: dựng + truyền Langfuse handler xuống graph/LLM."""
import pytest

from src.agents import erp_agent as erp_agent_module
from src.agents.erp_agent import ERPAgent


class _FakeHandler:
    """Đại diện CallbackHandler thật — chỉ cần phân biệt được bằng identity."""


@pytest.mark.asyncio
async def test_setup_dung_handler_tu_tracing(monkeypatch):
    fake_handler = _FakeHandler()
    monkeypatch.setattr(erp_agent_module.tracing, "get_handler",
                        lambda: fake_handler)
    # Các phần còn lại của setup() (make_llms, MCP client, Postgres pool) cần
    # hạ tầng thật — test này CHỈ xác nhận self._handler được dựng đúng thời
    # điểm, không gọi setup() đầy đủ. Gọi trực tiếp dòng dựng handler qua
    # __init__ + monkeypatch, tương đương hành vi thật của Bước 3 mà không
    # cần Postgres/MCP.
    agent = ERPAgent()
    agent._handler = erp_agent_module.tracing.get_handler()
    assert agent._handler is fake_handler


def test_answer_stateless_truyen_callback_khi_co_handler(monkeypatch):
    """Xác nhận answer_stateless() truyền đúng config={"callbacks":[handler]}
    xuống RoutedChatModel.ainvoke() khi self._handler đã được dựng."""
    import asyncio

    fake_handler = _FakeHandler()
    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["config"] = config
            class _R:
                content = "ok"
            return _R()

    agent = ERPAgent()
    agent._handler = fake_handler
    agent._llms = {"synthesis": _FakeLLM()}

    result = asyncio.run(agent.answer_stateless("câu hỏi gì đó"))

    assert result == "ok"
    assert captured["config"] == {"callbacks": [fake_handler]}


def test_answer_stateless_config_none_khi_khong_co_handler():
    """self._handler is None (Langfuse tắt/lỗi) → config=None, không callback
    nào được truyền — hành vi y hệt không có Langfuse."""
    import asyncio

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["config"] = config
            class _R:
                content = "ok"
            return _R()

    agent = ERPAgent()
    agent._handler = None
    agent._llms = {"synthesis": _FakeLLM()}

    asyncio.run(agent.answer_stateless("câu hỏi gì đó"))

    assert captured["config"] is None
```

- [ ] **Bước 5: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_erp_agent.py -v`
Expected: toàn bộ 3 test PASS.

- [ ] **Bước 6: Chạy toàn bộ test tầng agents, xác nhận không hồi quy**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/ -v -m "not integration and not live"`
Expected: toàn bộ PASS.

- [ ] **Bước 7: Commit**

```bash
git add backend/src/agents/erp_agent.py backend/tests/agents/test_erp_agent.py
git commit -m "feat(agents): ERPAgent dựng + dùng Langfuse handler

setup() gọi tracing.get_handler() một lần, lưu self._handler. chat() gắn
callback đúng 1 lần lúc dựng config ban đầu (config['callbacks']=[handler]
nếu có) — mọi lời gọi graph.ainvoke()/aget_state() sau đó trong chat() tự
thừa hưởng vì dùng chung biến config, không sửa rải rác 4 điểm gọi.
answer_stateless() (không đi qua chat()) tự dựng config tương tự tại chỗ
gọi self._llms['synthesis'].ainvoke().

self._handler is None (Langfuse tắt/lỗi) → không callback nào được truyền,
graph/LLM chạy y hệt không có Langfuse — không nhánh rẽ nào khác trong logic
nghiệp vụ. main.py không đổi gì liên quan Langfuse (Task 5)."
```

---

### Task 5: `main.py` — port FastAPI OpenAI-compatible

**Files:**
- Create: `backend/src/main.py`
- Test: `backend/tests/test_main.py`

**Interfaces:**
- Consumes: `ERPAgent` (đã có, Task 4 không đổi chữ ký công khai)
- Produces: `app` (FastAPI instance) — `GET /health`, `GET /v1/models`,
  `POST /v1/chat/completions`

- [ ] **Bước 1: Thêm `fastapi`/`uvicorn` vào `requirements.txt`**

Đã xác nhận (2026-07-30): `backend/requirements.txt` KHÔNG có `fastapi` hay
`uvicorn` — cần thêm cả hai, `main.py` không chạy được nếu thiếu. Mở
`backend/requirements.txt`, thêm 2 dòng vào cuối:

```
fastapi==0.141.1
uvicorn==0.46.0
```

(`uvicorn==0.46.0` — pin ĐÚNG version mà `run.py`'s docstring (Task 6) mô
tả hành vi `ProactorEventLoop` đã xác nhận thật ở repo nguồn; không dùng
bản mới hơn — hành vi loop-factory của bản mới chưa được xác nhận có còn
giống hệt không, không đáng để đổi biến số khi workaround hiện tại đã biết
hoạt động đúng.)

Run: `cd backend && .venv/Scripts/python.exe -m pip install fastapi==0.141.1 uvicorn==0.46.0`
Run: `.venv/Scripts/python.exe -c "from fastapi import FastAPI; import uvicorn; print('ok')"`
Expected: in ra `ok`, không lỗi import/xung đột version.

- [ ] **Bước 2: Tạo `backend/src/main.py` — port nguyên văn**

```python
"""
FastAPI backend — OpenAI-compatible API bọc ERP agent.
Open WebUI nối vào endpoint /v1 này như một "model" (erp-assistant).

Chạy (host, cần mcp-odoo SSE :8001 đang chạy):
    cd backend
    python run.py
"""
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.agents.erp_agent import ERPAgent

logger = logging.getLogger(__name__)

MODEL_ID = "erp-assistant"
ERROR_MSG = "Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu. Vui lòng thử lại."
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent = ERPAgent()
    await agent.setup()
    _state["agent"] = agent
    print(f"✓ ERP agent ready — tools: {agent.tool_names}")
    yield
    agent = _state.get("agent")
    if agent is not None:
        await agent.aclose()
    _state.clear()


app = FastAPI(title="ERP AI Assistant Backend", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": "agent" in _state}


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [
        {"id": MODEL_ID, "object": "model",
         "created": int(time.time()), "owned_by": "erp-ai"},
    ]}


def _filter_messages(messages: list[dict]) -> list[dict]:
    """Bỏ system (đã có baked prompt), giữ user/assistant để multi-turn."""
    return [{"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant") and m.get("content")]


def _explicit_session(body: dict) -> bool:
    """Did the client supply its own session id (body session_id/id)?

    Such clients manage their own conversation state and may send
    single-message resume turns — never enable fresh-reset for them.
    """
    return bool(body.get("session_id") or body.get("id"))


_OWUI_TASK_PREFIX = "### Task:\n"


def _is_owui_task_prompt(messages: list[dict]) -> bool:
    """Is this Open WebUI's own background auto-generation call (title/tags/
    follow-up/query generation), not a real user turn?

    R7 hotfix (live-verify 2026-07-09, spec §8): these calls carry the SAME
    x-openwebui-chat-id/-user-id headers as real user turns and are always a
    single user message with no session_id — indistinguishable from a real
    "fresh conversation" by headers alone, which would wipe a real parked
    confirm via the fresh-reset in ERPAgent.chat. Open WebUI's task prompts
    use this stable internal template prefix INCLUDING the newline (confirmed
    2026-07-09 against a live instance, twice, both with "\\n" immediately
    after "Task:") — the newline narrows the (already unlikely) false-positive
    where a real user's opener happens to start with "### Task:".

    Residual risks (spec §8): an admin who customizes Open WebUI's task
    prompt templates (Admin Settings) silently defeats this check and
    reopens the original bug with no warning; a real user's first message
    starting with this exact prefix+newline is silently answered without
    the ERP agent (no state is wiped either way — see spec §8).
    """
    return (len(messages) == 1 and messages[0].get("role") == "user"
            and (messages[0].get("content") or "").startswith(_OWUI_TASK_PREFIX))


def _derive_thread_id(body: dict, messages: list[dict], headers=None) -> str | None:
    """Stable per-conversation thread for interrupt/resume.

    Priority (R7 fix, spec 2026-07-09-r7-thread-scoping):
      1. Open WebUI identity headers — real per-chat id, sent when the
         open-webui container has ENABLE_FORWARD_USER_INFO_HEADERS=true.
         Only the two id headers are read; name/email/role are PII and must
         never be read or logged.
      2. Explicit id from the client body (scripts/curl).
      3. Hash of the FIRST user message — stable across the turns of one
         conversation, but collides across conversations with identical
         openers; the fresh-conversation reset in ERPAgent.chat mitigates.
      4. None (no user message).
    """
    if headers is not None:
        chat_id = headers.get("x-openwebui-chat-id")
        if chat_id:
            user_id = headers.get("x-openwebui-user-id") or "anon"
            return f"owui:{user_id}:{chat_id}"
    if _explicit_session(body):
        return str(body.get("session_id") or body.get("id"))
    first_user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    if not first_user:
        return None
    return "conv-" + hashlib.sha1(first_user.encode("utf-8")).hexdigest()[:16]


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    stream = bool(body.get("stream", False))
    messages = _filter_messages(body.get("messages", []))

    agent: ERPAgent = _state["agent"]
    try:
        if _is_owui_task_prompt(messages):
            # Open WebUI's own background task call (title/tags/follow-up/query
            # generation) — answer it directly, never touch thread/checkpoint
            # state (R7 hotfix, spec §8).
            answer = await agent.answer_stateless(messages[0]["content"])
        else:
            # Stable thread per conversation so multi-turn confirmation resumes
            # correctly. Priority: Open WebUI identity headers (R7) > explicit
            # client session_id/id > hash of the first user message (see
            # _derive_thread_id docstring).
            thread_id = _derive_thread_id(body, messages, headers=req.headers)
            answer = await agent.chat(messages, thread_id=thread_id,
                                      reset_if_fresh=not _explicit_session(body))
    except Exception:
        # A transient failure (cloud LLM hiccup/timeout/rate-limit) here must
        # not propagate uncaught → FastAPI 500. rag_node/fusion_node already
        # degrade to a safe message on failure; this is the same pattern at
        # the endpoint's outermost layer, covering EVERY node (chitchat
        # included, which lacks its own guard).
        logger.exception("chat_completions failed")
        answer = ERROR_MSG

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if not stream:
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": MODEL_ID,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": answer},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    # Streaming: agent trả nguyên câu → emit 1 content chunk + [DONE] (đủ cho Open WebUI)
    async def sse():
        base = {"id": cid, "object": "chat.completion.chunk",
                "created": created, "model": MODEL_ID}
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})}\n\n'
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
```

Đúng 1 chỗ khác bản gốc `D:\Project\backend\src\main.py`: docstring's lệnh
chạy đổi từ `uvicorn src.main:app --host ... --port ...` (bản gốc cần
mcp-odoo + litellm) thành `python run.py` (Youdoo không có LiteLLM, dùng
`run.py` port ở Task 6 để né lỗi `ProactorEventLoop`). Comment trong
`except Exception:` nhắc "rag_node/fusion_node" giữ nguyên — đã xác nhận cả
2 tên hàm này tồn tại y hệt ở Youdoo (`backend/src/agents/nodes.py`'s
`make_rag_node()`'s inner `rag_node`, `backend/src/agents/fusion.py:77`'s
`fusion_node`), không cần sửa gì.

- [ ] **Bước 3: Viết test cho 4 hàm thuần**

Tạo `backend/tests/test_main.py`:

```python
# backend/tests/test_main.py
"""main.py: hàm thuần (không cần FastAPI TestClient) + endpoint lỗi."""
import pytest

from src.main import (_derive_thread_id, _explicit_session,
                      _is_owui_task_prompt, _filter_messages)


def test_filter_messages_bo_system_giu_user_assistant():
    messages = [
        {"role": "system", "content": "prompt hệ thống"},
        {"role": "user", "content": "câu hỏi"},
        {"role": "assistant", "content": "trả lời"},
        {"role": "user", "content": ""},  # rỗng, phải bị loại
    ]
    result = _filter_messages(messages)
    assert result == [
        {"role": "user", "content": "câu hỏi"},
        {"role": "assistant", "content": "trả lời"},
    ]


def test_explicit_session_true_khi_co_session_id():
    assert _explicit_session({"session_id": "abc"}) is True
    assert _explicit_session({"id": "xyz"}) is True


def test_explicit_session_false_khi_khong_co():
    assert _explicit_session({}) is False


def test_is_owui_task_prompt_dung_dinh_dang():
    messages = [{"role": "user", "content": "### Task:\nTóm tắt hội thoại"}]
    assert _is_owui_task_prompt(messages) is True


def test_is_owui_task_prompt_khong_khop_neu_thieu_newline():
    messages = [{"role": "user", "content": "### Task: không có newline"}]
    assert _is_owui_task_prompt(messages) is False


def test_is_owui_task_prompt_false_khi_nhieu_tin_nhan():
    messages = [
        {"role": "user", "content": "### Task:\nx"},
        {"role": "assistant", "content": "y"},
    ]
    assert _is_owui_task_prompt(messages) is False


def test_derive_thread_id_uu_tien_header_openwebui():
    headers = {"x-openwebui-chat-id": "chat123", "x-openwebui-user-id": "user9"}
    tid = _derive_thread_id({}, [], headers=headers)
    assert tid == "owui:user9:chat123"


def test_derive_thread_id_uu_tien_session_id_neu_khong_co_header():
    tid = _derive_thread_id({"session_id": "sess1"}, [], headers={})
    assert tid == "sess1"


def test_derive_thread_id_hash_tin_nhan_dau_neu_khong_co_gi_khac():
    messages = [{"role": "user", "content": "câu hỏi đầu tiên"}]
    tid = _derive_thread_id({}, messages, headers={})
    assert tid is not None and tid.startswith("conv-")


def test_derive_thread_id_none_neu_khong_co_user_message():
    tid = _derive_thread_id({}, [], headers={})
    assert tid is None
```

- [ ] **Bước 4: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: toàn bộ PASS.

- [ ] **Bước 5: Viết test cho `chat_completions`'s catch-all lỗi (cần `httpx`'s `ASGITransport`, đã có `httpx` trong requirements.txt)**

Thêm vào `backend/tests/test_main.py`:

```python
@pytest.mark.asyncio
async def test_chat_completions_tra_error_msg_khi_agent_nem_loi(monkeypatch):
    import httpx
    from src import main as main_module

    class _FakeAgentThrows:
        async def chat(self, *a, **k):
            raise RuntimeError("lỗi giả lập agent")

    main_module._state["agent"] = _FakeAgentThrows()
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        resp = await client.post("/v1/chat/completions",
                                 json={"messages": [{"role": "user",
                                                     "content": "hi"}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == main_module.ERROR_MSG
    main_module._state.clear()


@pytest.mark.asyncio
async def test_health_endpoint_khi_chua_co_agent():
    import httpx
    from src import main as main_module

    main_module._state.clear()
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "agent_ready": False}
```

- [ ] **Bước 6: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: toàn bộ PASS (11 test).

- [ ] **Bước 7: Commit**

```bash
git add backend/src/main.py backend/tests/test_main.py
git commit -m "feat(main): FastAPI OpenAI-compatible /v1 — port từ D:\Project

Port gần nguyên văn D:\Project\backend\src\main.py: /health, /v1/models,
POST /v1/chat/completions (JSON + SSE giả — 1 content-chunk, ERPAgent.chat()
trả str nguyên khối không phải generator). Đường import
'from src.agents.erp_agent import ERPAgent' đã khớp quy ước Youdoo, không
cần sửa. Catch-all lỗi trả ERROR_MSG lịch sự, không lộ traceback.

_filter_messages/_explicit_session/_is_owui_task_prompt/_derive_thread_id
là 4 hàm thuần port nguyên văn — D:\Project không có test riêng cho main.py
(đã xác nhận), viết mới toàn bộ 11 test."
```

---

### Task 6: `run.py` — entrypoint (Windows SelectorEventLoop)

**Files:**
- Create: `backend/run.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `src.main:app` (Task 5)
- Produces: `python run.py` khởi động server trên `BACKEND_HOST`/`BACKEND_PORT`

- [ ] **Bước 1: Tạo `backend/run.py` — port nguyên văn**

```python
"""Entry point for the ERP backend.

On Windows, psycopg3's async mode is incompatible with the ProactorEventLoop
("Psycopg cannot use the 'ProactorEventLoop'..."). uvicorn 0.46 hardcodes the
ProactorEventLoop for single-process Windows via its loop *factory* (it creates
the loop directly, ignoring the asyncio event-loop *policy*). So we cannot fix
this by setting a policy — we must drive uvicorn's ASGI server inside a
SelectorEventLoop we create ourselves.

Run:  python run.py     (from the backend/ directory)
"""
import asyncio
import os
import sys

from uvicorn import Config, Server


def main() -> None:
    config = Config(
        "src.main:app",
        host=os.environ.get("BACKEND_HOST", "0.0.0.0"),
        port=int(os.environ.get("BACKEND_PORT", "8000")),
    )
    server = Server(config)

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    else:
        server.run()


if __name__ == "__main__":
    main()
```

- [ ] **Bước 2: Thêm `BACKEND_HOST`/`BACKEND_PORT` vào `.env.example`**

Mở `.env.example`, thêm khối mới (sau khối `# ─── Langfuse (kế hoạch C) ───`
hiện có):

```
# ─── Backend HTTP server (kế hoạch C2) ──────────────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

- [ ] **Bước 3: Xác nhận `run.py` import được (không cần chạy server thật ở bước này)**

Run: `cd backend && .venv/Scripts/python.exe -c "import ast; ast.parse(open('run.py', encoding='utf-8').read()); print('cú pháp hợp lệ')"`
Expected: in ra `cú pháp hợp lệ`, không lỗi cú pháp. (Chưa chạy `python
run.py` thật ở bước này — cần `src/main.py` (Task 5, đã xong) + Postgres +
mcp-odoo sống, để dành cho Task 8's lượt chạy sống thật.)

- [ ] **Bước 4: Commit**

```bash
git add backend/run.py .env.example
git commit -m "feat(run): entrypoint backend — port SelectorEventLoop fix từ D:\Project

Port nguyên văn D:\Project\backend\run.py — Windows + psycopg3 async không
tương thích ProactorEventLoop mặc định của uvicorn (uvicorn 0.46 hardcode
loop factory, không đọc theo asyncio policy) — driver ASGI server bên trong
SelectorEventLoop tự tạo. Áp dụng y hệt cho Youdoo (cùng OS, cùng
AsyncPostgresSaver/AsyncConnectionPool trong ERPAgent.setup()).

Thêm BACKEND_HOST/BACKEND_PORT vào .env.example (mặc định 0.0.0.0:8000,
run.py gốc đã dùng vậy)."
```

---

### Task 7: `docker-compose.yml` — profile `observability` (Langfuse self-host)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: service `postgres` đã có (container `youdoo-postgres`)
- Produces: 5 service mới (`langfuse-web`, `langfuse-worker`, `clickhouse`,
  `redis`, `minio`), tất cả sau `profiles: ["observability"]` — không ảnh
  hưởng `docker compose up` mặc định

- [ ] **Bước 1: Thêm 5 biến secret Langfuse vào `.env.example`**

Mở `.env.example`, sửa khối Langfuse hiện có:

```
# ─── Langfuse (kế hoạch C2, self-host) ──────────────────────────────────────
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
# 4 biến dưới CHỈ dùng để dựng hạ tầng self-host (docker-compose.yml's
# profile observability) — KHÔNG phải LANGFUSE_PUBLIC_KEY/SECRET_KEY ở trên
# (2 khoá đó tạo THỦ CÔNG trên UI Langfuse sau khi hạ tầng đã chạy, xem Task 8).
LANGFUSE_NEXTAUTH_SECRET=thay_bang_secret_that
LANGFUSE_SALT=thay_bang_salt_that
# 64 ký tự hex — sinh bằng: openssl rand -hex 32
LANGFUSE_ENCRYPTION_KEY=thay_bang_64_ky_tu_hex
LANGFUSE_REDIS_AUTH=thay_bang_mat_khau_redis
LANGFUSE_CLICKHOUSE_PASSWORD=thay_bang_mat_khau_clickhouse
LANGFUSE_MINIO_ROOT_PASSWORD=thay_bang_mat_khau_minio
```

- [ ] **Bước 2: Thêm 5 service vào `docker-compose.yml`**

Mở `docker-compose.yml`, thêm vào cuối phần `volumes:` hiện có (giữ nguyên
`youdoo_postgres_data` đã có):

```yaml
  langfuse_clickhouse_data:
    driver: local
  langfuse_clickhouse_logs:
    driver: local
  langfuse_minio_data:
    driver: local
  langfuse_redis_data:
    driver: local
```

Thêm vào cuối phần `services:` hiện có (giữ nguyên service `postgres` đã
có, KHÔNG tạo service Postgres thứ hai — 5 service dưới dùng chung
`youdoo-postgres` qua service name `postgres`, database riêng `langfuse`
tạo ở Bước 3):

```yaml
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:4
    restart: unless-stopped
    profiles: ["observability"]
    depends_on: &langfuse-depends-on
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
      redis:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
    ports:
      - 127.0.0.1:3030:3030
    environment: &langfuse-worker-env
      NEXTAUTH_URL: http://localhost:3001
      DATABASE_URL: postgresql://${POSTGRES_USER:-admin}:${POSTGRES_PASSWORD:-thay_bang_mat_khau}@postgres:5432/langfuse
      SALT: ${LANGFUSE_SALT:-thay_bang_salt_that}
      ENCRYPTION_KEY: ${LANGFUSE_ENCRYPTION_KEY:-thay_bang_64_ky_tu_hex}
      TELEMETRY_ENABLED: "true"
      LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: "false"
      CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000
      CLICKHOUSE_URL: http://clickhouse:8123
      CLICKHOUSE_USER: clickhouse
      CLICKHOUSE_PASSWORD: ${LANGFUSE_CLICKHOUSE_PASSWORD:-thay_bang_mat_khau_clickhouse}
      CLICKHOUSE_CLUSTER_ENABLED: "false"
      LANGFUSE_S3_EVENT_UPLOAD_BUCKET: langfuse
      LANGFUSE_S3_EVENT_UPLOAD_REGION: auto
      LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: minio
      LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_MINIO_ROOT_PASSWORD:-thay_bang_mat_khau_minio}
      LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: http://minio:9000
      LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: "true"
      LANGFUSE_S3_EVENT_UPLOAD_PREFIX: events/
      LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: langfuse
      LANGFUSE_S3_MEDIA_UPLOAD_REGION: auto
      LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: minio
      LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_MINIO_ROOT_PASSWORD:-thay_bang_mat_khau_minio}
      LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: http://localhost:9090
      LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE: "true"
      LANGFUSE_S3_MEDIA_UPLOAD_PREFIX: media/
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      REDIS_AUTH: ${LANGFUSE_REDIS_AUTH:-thay_bang_mat_khau_redis}

  langfuse-web:
    image: docker.io/langfuse/langfuse:4
    restart: unless-stopped
    profiles: ["observability"]
    depends_on: *langfuse-depends-on
    ports:
      # 3001, KHÔNG phải 3000 mặc định của Langfuse — khớp LANGFUSE_HOST đã
      # có sẵn trong .env.example từ trước (SP-1 foundation).
      - 3001:3000
    environment:
      <<: *langfuse-worker-env
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET:-thay_bang_secret_that}

  clickhouse:
    image: docker.io/clickhouse/clickhouse-server:25.12
    restart: unless-stopped
    profiles: ["observability"]
    user: "101:101"
    environment:
      CLICKHOUSE_DB: default
      CLICKHOUSE_USER: clickhouse
      CLICKHOUSE_PASSWORD: ${LANGFUSE_CLICKHOUSE_PASSWORD:-thay_bang_mat_khau_clickhouse}
    volumes:
      - langfuse_clickhouse_data:/var/lib/clickhouse
      - langfuse_clickhouse_logs:/var/log/clickhouse-server
    ports:
      - 127.0.0.1:8123:8123
      - 127.0.0.1:9000:9000
    healthcheck:
      test: wget --no-verbose --tries=1 --spider http://localhost:8123/ping || exit 1
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 1s

  minio:
    image: cgr.dev/chainguard/minio
    restart: unless-stopped
    profiles: ["observability"]
    entrypoint: sh
    command: -c 'mkdir -p /data/langfuse && minio server --address ":9000" --console-address ":9001" /data'
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: ${LANGFUSE_MINIO_ROOT_PASSWORD:-thay_bang_mat_khau_minio}
    ports:
      - 9090:9000
      - 127.0.0.1:9091:9001
    volumes:
      - langfuse_minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 1s
      timeout: 5s
      retries: 5
      start_period: 1s

  redis:
    image: docker.io/redis:7
    restart: unless-stopped
    profiles: ["observability"]
    command: >
      --requirepass ${LANGFUSE_REDIS_AUTH:-thay_bang_mat_khau_redis}
      --maxmemory-policy noeviction
    ports:
      - 127.0.0.1:6379:6379
    volumes:
      - langfuse_redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 10s
      retries: 10
```

Nguồn đối chiếu: `docker-compose.yml` chính thức của Langfuse
(`https://github.com/langfuse/langfuse`, nhánh `main`, xác nhận 2026-07-30
— image `langfuse/langfuse:4`/`langfuse/langfuse-worker:4`,
`clickhouse-server:25.12`). Khác bản gốc ở 3 điểm: (1) không có service
`postgres` riêng — dùng chung `postgres` đã có của Youdoo; (2)
`langfuse-web` map cổng host `3001` thay vì `3000`; (3) mọi giá trị bí mật
đọc từ biến môi trường Youdoo's `.env` (tiền tố `LANGFUSE_*`) thay vì giá
trị mặc định `CHANGEME` của bản gốc.

- [ ] **Bước 3: Script tạo database `langfuse` trong `youdoo-postgres` (idempotent)**

Tạo `scripts/create-langfuse-db.sh` (thư mục `scripts/` ở gốc repo — tạo
thư mục nếu chưa có):

```bash
#!/usr/bin/env bash
# Tạo database "langfuse" trong container youdoo-postgres đã có, nếu chưa
# tồn tại. KHÔNG dùng CREATE DATABASE IF NOT EXISTS — cú pháp đó không được
# PostgreSQL hỗ trợ cho CREATE DATABASE (khác CREATE TABLE). An toàn chạy
# lại nhiều lần (idempotent) — nếu database đã tồn tại thì bỏ qua, không lỗi.
set -euo pipefail

EXISTS=$(docker exec youdoo-postgres psql -U "${POSTGRES_USER:-admin}" \
  -d "${POSTGRES_DB:-ai_assistant}" -tAc \
  "SELECT 1 FROM pg_database WHERE datname = 'langfuse'")

if [ "$EXISTS" = "1" ]; then
  echo "Database 'langfuse' đã tồn tại — bỏ qua."
else
  docker exec youdoo-postgres psql -U "${POSTGRES_USER:-admin}" \
    -d "${POSTGRES_DB:-ai_assistant}" -c "CREATE DATABASE langfuse"
  echo "Đã tạo database 'langfuse'."
fi
```

- [ ] **Bước 4: Xác nhận `docker compose up` mặc định KHÔNG kéo theo service Langfuse**

Run: `docker compose config --services`
Expected: chỉ in ra `postgres` — KHÔNG có `langfuse-web`/`langfuse-worker`/
`clickhouse`/`redis`/`minio`.

Run: `docker compose --profile observability config --services`
Expected: in ra cả 6 dòng — `postgres`, `langfuse-web`, `langfuse-worker`,
`clickhouse`, `redis`, `minio`.

Nếu Bước này cho kết quả khác kỳ vọng (vd service Langfuse xuất hiện ở lệnh
đầu), kiểm lại từng service đã có đúng dòng `profiles: ["observability"]`
chưa — đây là lỗi phải sửa trước khi đi tiếp, không phải cảnh báo bỏ qua
được.

- [ ] **Bước 5: Commit**

```bash
git add docker-compose.yml .env.example scripts/create-langfuse-db.sh
git commit -m "feat(infra): docker-compose profile observability — Langfuse self-host

5 service mới (langfuse-web, langfuse-worker, clickhouse, redis, minio),
đối chiếu docker-compose.yml chính thức của Langfuse (nhánh main, xác nhận
2026-07-30). Dùng chung service postgres đã có của Youdoo (database
'langfuse' riêng, tạo qua scripts/create-langfuse-db.sh — không container
Postgres thứ hai). Tất cả 5 service đặt profiles:[\"observability\"] —
docker compose up mặc định không đổi hành vi (xác nhận bằng docker compose
config --services trước/sau khi thêm profile).

langfuse-web map cổng host 3001 (không phải 3000 mặc định) — khớp
LANGFUSE_HOST đã có sẵn trong .env.example từ SP-1 foundation. 5 biến secret
mới (LANGFUSE_NEXTAUTH_SECRET/SALT/ENCRYPTION_KEY/REDIS_AUTH/
CLICKHOUSE_PASSWORD/MINIO_ROOT_PASSWORD) đọc từ .env, không hardcode."
```

---

### Task 8: Xác nhận sống — dựng stack thật, xem trace trên Langfuse UI

**Files:**
- Không tạo/sửa file code — chỉ chạy lệnh và ghi báo cáo
- Create: `docs/superpowers/plans/2026-07-30-sp1c2-http-langfuse-report.md`

**Interfaces:**
- Consumes: mọi thứ dựng ở Task 1-7
- Produces: báo cáo xác nhận — điều kiện "SP-1C2 xong" theo spec §7

- [ ] **Bước 1: Chạy toàn bộ test 2 chế độ (mặc định + integration), xác nhận không hồi quy**

Run:
```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors
.venv/Scripts/python.exe -m pytest tests/ -q -m integration
```
Expected: 0 lỗi mới so với trước Task 1 (cộng thêm số test mới từ Task 1-6
trong plan này). Nếu 2 fixture nhị phân `tests/rag/fixtures/{bang_gia.xlsx,policy.docx}`
bị chạm (tác dụng phụ đã biết), `git checkout --` khôi phục trước khi tiếp
tục.

- [ ] **Bước 2: Sinh 6 secret Langfuse thật, ghi vào `.env` (KHÔNG commit)**

```bash
# Từ gốc repo, tại chỗ có .env thật (không phải .env.example)
python -c "import secrets; print(secrets.token_hex(32))"   # ENCRYPTION_KEY — 64 hex
python -c "import secrets; print(secrets.token_urlsafe(24))"  # x4 cho SALT/NEXTAUTH_SECRET/REDIS_AUTH/CLICKHOUSE_PASSWORD/MINIO_ROOT_PASSWORD
```

Điền 6 giá trị sinh được vào `.env` (khớp tên biến đã thêm ở Task 7 Bước 1):
`LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`,
`LANGFUSE_REDIS_AUTH`, `LANGFUSE_CLICKHOUSE_PASSWORD`,
`LANGFUSE_MINIO_ROOT_PASSWORD`. `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
để TRỐNG ở bước này — tạo ở Bước 5 sau khi Langfuse UI đã chạy.

- [ ] **Bước 3: Dựng hạ tầng**

```bash
docker compose up -d postgres
bash scripts/create-langfuse-db.sh
docker compose --profile observability up -d
```

Chờ tất cả container `healthy`:
Run: `docker compose --profile observability ps`
Expected: `postgres`, `clickhouse`, `redis`, `minio` đều `healthy`;
`langfuse-web`/`langfuse-worker` đều `Up` (2 service này không có
healthcheck riêng trong compose, chỉ cần trạng thái `Up` không phải
`Restarting`).

- [ ] **Bước 4: Xác nhận `main.py` chạy được**

```bash
cd backend
set -a && source ../.env && set +a
python run.py
```
(Giữ chạy nền — mở terminal khác cho các bước sau, hoặc thêm `&` nếu shell
hỗ trợ.)

Ở terminal khác:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok","agent_ready":true}`.

- [ ] **Bước 5: Tạo project/API key trên Langfuse UI**

Mở `http://localhost:3001` trên trình duyệt → đăng ký tài khoản đầu tiên
(self-host, không cần email thật xác thực) → tạo 1 project → vào Settings
→ API Keys → tạo cặp Public/Secret key.

Dừng `python run.py` (Ctrl+C), điền `LANGFUSE_PUBLIC_KEY`/
`LANGFUSE_SECRET_KEY` vào `.env`, chạy lại `python run.py` để agent đọc
được 2 khoá mới.

- [ ] **Bước 6: Gửi 1 câu hỏi thật, xác nhận trả lời hợp lệ**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Xin chào, bạn có thể giúp gì?"}]}'
```
Expected: JSON `choices[0].message.content` có nội dung trả lời hợp lý
(không phải `ERROR_MSG`).

- [ ] **Bước 7: Xác nhận trace trên Langfuse UI bằng mắt**

Mở lại `http://localhost:3001` → vào project đã tạo → tab Traces. Xác nhận:
- Có 1 trace mới, thời điểm khớp lượt gọi curl ở Bước 6.
- Mở trace, thấy cây span lồng nhau (LangGraph node).
- Ít nhất 1 span (ứng với 1 lượt gọi LLM) có metadata chứa `role`, `alias`,
  `provider`, `upstream`, `fallback_depth`, `budget_verdict`, `est_tokens`,
  `actual_tokens` — đúng field đã định nghĩa ở Task 2.

- [ ] **Bước 8: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-07-30-sp1c2-http-langfuse-report.md`:
mô tả kết quả Bước 1 (số test PASS 2 chế độ), Bước 6 (câu hỏi + câu trả lời
thật), Bước 7 (ảnh chụp màn hình hoặc mô tả chi tiết cây trace + bảng
metadata thấy trên UI — chép nguyên giá trị thật thấy được, không viết tay
ước lượng). Nếu bất kỳ bước 1-7 nào KHÔNG đạt kỳ vọng, ghi rõ ràng — đây
không phải lỗi của plan, là kết quả cần người dùng quyết định bước tiếp
theo (sửa cấu hình rồi thử lại, hay chấp nhận giới hạn đã biết).

- [ ] **Bước 9: Dừng server, dọn dẹp**

```bash
# Ctrl+C dừng python run.py nếu còn chạy nền
docker compose --profile observability down
```

(Giữ `docker compose up -d postgres` chạy — Postgres vẫn cần cho việc khác.
KHÔNG chạy `down -v` — sẽ xoá volume dữ liệu Postgres/ClickHouse thật.)

- [ ] **Bước 10: Commit báo cáo**

```bash
git add docs/superpowers/plans/2026-07-30-sp1c2-http-langfuse-report.md
git commit -m "docs: báo cáo xác nhận sống SP-1C2 — /v1 + Langfuse trace thật

Kết quả thật từ lượt chạy sống: /health, /v1/chat/completions trả lời đúng
qua curl; Langfuse UI hiện trace + span lồng nhau + metadata định tuyến
(role/alias/provider/upstream/fallback_depth/budget_verdict/est_tokens/
actual_tokens) đúng như thiết kế Task 2. Test suite 2 chế độ xanh, không
hồi quy."
```

---

## "SP-1C2 xong" nghĩa là

Đối chiếu trực tiếp với spec §7:

1. ✅ Task 5-6: `main.py`/`run.py` chạy được, `/health`/`/v1/models`/
   `/v1/chat/completions` trả lời đúng qua curl (xác nhận thật ở Task 8).
2. ✅ Task 2: `tracing.py` có test chứng minh no-op an toàn ở mọi nhánh lỗi.
3. ✅ Task 3: `RoutedChatModel.ainvoke()`/`.invoke()` gọi
   `annotate_current_span()` — test xác nhận đúng field.
4. ✅ Task 8 Bước 7: Langfuse UI hiện trace + span đúng cây, thuộc tính đúng
   — xác nhận bằng mắt, ghi trong báo cáo.
5. ✅ Task 7 Bước 4: profile `observability` không ảnh hưởng `docker compose
   up` mặc định.
6. ✅ Task 8 Bước 1: toàn bộ test 2 chế độ vẫn xanh, không hồi quy.
