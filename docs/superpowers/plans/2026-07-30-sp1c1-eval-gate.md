# SP-1C1: Vá blocker hạ tầng + eval harness + chạy cổng M3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vá 3 blocker hạ tầng, port + thích nghi eval harness từ `D:\Project`, sửa bug scanner `multi_source`, và chạy cổng ADR-009 QĐ M3 thật — sinh bảng trước/sau chứng minh model cloud không làm chất lượng thụt lùi so với qwen3:8b.

**Architecture:** Vá 2 điểm trong `backend/src/llm/` (không đổi hợp đồng `BudgetLedger`/`UsageStore`). Port `backend/evals/` + `backend/jobs/` từ repo nguồn, thay thế 3 phụ thuộc đã bị SP-1 xoá (LiteLLM, `model_for()`, `is_qwen()`) bằng `RoutedChatModel(pin=...)` + `llm/catalog.py`. Hai package mới này là **hàng xóm của `src/`**, không phải bên trong nó — chạy bằng `cd backend && python -m evals.run_eval` / `python -m jobs run eval-gate`, cùng quy ước "`backend/` không có `__init__.py`" mà SP-1B Task 4 đã chốt cho `src/`.

**Tech Stack:** Python 3.11, pytest, psycopg_pool, tiktoken, langchain-core.

## Global Constraints

- **Python 3.11+.** Dùng `X | None`, không `Optional[X]`.
- **Không khoá API nào trong code.** Mọi khoá đọc từ biến môi trường.
- **`src/llm/` không được import từ `src/agents/`, `src/erp_query/`, `src/rag/`.** `backend/evals/` và `backend/jobs/` là ngoại lệ được phép (chúng đo `agents/`, không phải một phần của `llm/`) — nhưng `src/llm/` tự nó vẫn không được đảo chiều.
- **Bình luận tiếng Việt, định danh tiếng Anh** — khớp quy ước repo nguồn và SP-1B.
- **Test đơn vị không chạm mạng, không cần Postgres** theo mặc định. Test cần Postgres → `@pytest.mark.integration`. Test cần mạng/API key thật → `@pytest.mark.live`.
- **QUY TẮC PORT TEST — quan trọng nhất.** Test port sang mà đỏ:
  - vì **hạ tầng đổi** (đường import, `backend.X` → `X`, `sys.path.insert`) → sửa nối dây.
  - vì **hành vi thật sự đổi** → sửa test cho khớp thiết kế MỚI đã duyệt trong spec, và **ghi rõ trong commit đây là thay đổi hành vi, không phải nối dây** — không được lặng lẽ sửa như một fix cơ học. Hai test cụ thể rơi vào diện này đã xác định sẵn ở Task 5 (§ Bước 5).
- **`total_tokens` là con số có thẩm quyền cho mọi phép kiểm token** — không bao giờ cộng `prompt_tokens + completion_tokens`.
- **Công thức `_gate()` trong `eval_gate.py` giữ NGUYÊN VĂN** — nó mã hoá ADR-009 QĐ M3. Không "tối ưu" hay "làm gọn" nó.
- **Quy ước gói mới:** `backend/evals/` và `backend/jobs/` là package cấp cao **ngang hàng** với `backend/src/` (không nằm trong `src/`). Import nội bộ giữa chúng: `from evals.X import Y`, `from jobs.X import Y`; import sang tầng nghiệp vụ: `from src.agents.X import Y`. Không bao giờ `from backend.X import Y`, không `sys.path.insert`. Cả hai đều có `__init__.py` rỗng (là package thường) — nhưng **không** tạo `backend/__init__.py` (sẽ phá quy ước sys.path hiện có của toàn bộ `backend/tests/`).
- **`backend/tests/jobs/conftest.py`** cô lập `registry.JOBS`/`registry.LOGS_DIR` giữa các test — bắt buộc `autouse=True`, nếu không job đăng ký thật ở import-time (`eval_gate.py`) sẽ rò giữa các file test.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/llm/store.py` | **Sửa** — `PostgresUsageStore.__init__` thêm timeout ngắn |
| `backend/src/llm/router.py` | **Sửa** — `Router.ainvoke()` bọc `to_thread` quanh `resolve()`/`_finish()` |
| `backend/src/llm/tokens.py` | **Sửa** — `estimate_base_tokens()` tụt về ước lượng thô khi `tiktoken` không nạp được |
| `backend/evals/fixtures/__init__.py`, `chunks.json` | Port nguyên — chunk RAG đóng băng cho `multi_source`/`synthesis` |
| `backend/evals/cases.py` | Port nguyên — dữ liệu case thuần, không import gì |
| `backend/evals/run_eval.py` | Port + **thích nghi** — 7 hàm `eval_*`, `_llm()` viết lại dùng `RoutedChatModel` |
| `backend/jobs/registry.py` | Port nguyên — Job/JobResult/exit-contract |
| `backend/jobs/resilience.py` | Port nguyên — `run_resilient` (retry + checkpoint + circuit-breaker) |
| `backend/jobs/eval_gate.py` | Port + **thích nghi** — bỏ `model_for`/`is_qwen`, thay bằng `chain_for`/công thức nhịp mới |
| `backend/jobs/__main__.py` | Port + **thích nghi** — bỏ 4 import job `e2e_*` (ngoài phạm vi) |
| `backend/evals/rescore_multi_source.py` | **Mới** — script chấm lại baseline sau khi sửa scanner |
| `backend/tests/jobs/`, `backend/tests/llm/` (mở rộng) | Port + thích nghi bộ test tương ứng |

---

### Task 1: Vá blocker #1 + #2 — pool timeout ngắn + `Router.ainvoke()` không chặn event loop

**Files:**
- Modify: `backend/src/llm/store.py:88-89`
- Modify: `backend/src/llm/router.py:266-284` (phương thức `ainvoke`)
- Test: `backend/tests/llm/test_store.py`
- Test: `backend/tests/llm/test_router_invoke.py`

**Interfaces:**
- Consumes: `psycopg_pool.ConnectionPool` (đã cài), `BudgetLedger`/`UsageStore` hiện có (không đổi chữ ký)
- Produces: Không đổi API công khai nào — `PostgresUsageStore.__init__(dsn=None, *, pool=None)` và `Router.ainvoke(role, messages, ...)` giữ nguyên chữ ký, chỉ đổi hành vi bên trong

- [ ] **Bước 1: Sửa `store.py` — timeout ngắn cho `ConnectionPool`**

Mở `backend/src/llm/store.py`, tìm đoạn (dòng 88-89):

```python
        self._pool = ConnectionPool(dsn or os.environ["DATABASE_URL"],
                                    min_size=1, max_size=4, open=True)
```

Thay bằng:

```python
        # timeout ngắn (mặc định ConnectionPool là 30s cho pool.connection(),
        # cộng bản thân TCP connect không giới hạn nếu thiếu connect_timeout —
        # quan sát thực tế ~90s trước khi BudgetLedger fail-open). Sổ ngân
        # sách là TƯ VẤN, đã fail-open sẵn (budget.py can_afford/record) — chặn
        # lượt của người dùng vài giây chỉ để tra một cuốn sổ tư vấn là đánh
        # đổi sai. Thà mất một dòng kế toán.
        self._pool = ConnectionPool(dsn or os.environ["DATABASE_URL"],
                                    min_size=1, max_size=4, open=True,
                                    timeout=2.0,
                                    kwargs={"connect_timeout": 2})
```

- [ ] **Bước 2: Test — `ConnectionPool` được dựng với timeout ngắn**

Thêm vào `backend/tests/llm/test_store.py`:

```python
def test_postgres_store_dung_pool_voi_timeout_ngan(monkeypatch):
    """Blocker #1: pool không có timeout → chặn ~90s trước khi fail-open.
    Xác nhận cấu hình timeout ngắn thật sự được truyền xuống ConnectionPool,
    không chỉ "đã sửa" trong lời commit."""
    calls = []

    class FakePool:
        def __init__(self, dsn, **kwargs):
            calls.append(kwargs)
            self._dsn = dsn

        def connection(self):
            import contextlib

            class _Conn:
                def execute(self, *a, **k):
                    return None
            @contextlib.contextmanager
            def _cm():
                yield _Conn()
            return _cm()

    monkeypatch.setattr("psycopg_pool.ConnectionPool", FakePool)
    from src.llm.store import PostgresUsageStore
    PostgresUsageStore(dsn="postgresql://fake/db")
    assert len(calls) == 1
    assert calls[0]["timeout"] <= 3.0
    assert calls[0]["kwargs"]["connect_timeout"] <= 3
```

- [ ] **Bước 3: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_store.py -v -k timeout_ngan`
Expected: PASS.

- [ ] **Bước 4: Sửa `router.py` — `to_thread` quanh `resolve()`/`_finish()` trong `ainvoke`**

Mở `backend/src/llm/router.py`, tìm phương thức `ainvoke` (dòng 266-284):

```python
    async def ainvoke(self, role: str, messages: list,
                      tools: list | None = None,
                      pin: str | None = None, config=None,
                      tool_kwargs: dict | None = None, **kwargs) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = await self._client(
                    decision.spec, tools, tool_kwargs).ainvoke(
                        messages, config=config, **kwargs)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

Thay bằng:

```python
    async def ainvoke(self, role: str, messages: list,
                      tools: list | None = None,
                      pin: str | None = None, config=None,
                      tool_kwargs: dict | None = None, **kwargs) -> InvokeResult:
        # Blocker #2: resolve()/_finish() chạm Postgres ĐỒNG BỘ (qua
        # BudgetLedger.can_afford/record) — chặn event loop dưới FastAPI/
        # LangGraph async nếu gọi trực tiếp trong coroutine. to_thread đẩy
        # đúng hai điểm đó ra khỏi event loop. BudgetLedger/UsageStore KHÔNG
        # đổi một dòng — giữ nguyên tuyên bố thiết kế "chính sách thuần,
        # KHÔNG biết Postgres tồn tại" (budget.py), nên toàn bộ test SP-1A
        # của chúng còn nguyên giá trị. Đường invoke() đồng bộ không đổi.
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = await asyncio.to_thread(self.resolve, role, base, pin=pin)
            try:
                response = await self._client(
                    decision.spec, tools, tool_kwargs).ainvoke(
                        messages, config=config, **kwargs)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return await asyncio.to_thread(self._finish, decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

Thêm `import asyncio` vào đầu file (`backend/src/llm/router.py`, cạnh `import logging` dòng 6).

- [ ] **Bước 5: Test — event loop không bị chặn khi store chậm**

Thêm vào `backend/tests/llm/test_router_invoke.py`:

```python
async def test_ainvoke_khong_chan_event_loop_khi_store_cham(clock):
    """Blocker #2: to_thread phải thực sự nhường event loop, không chỉ gọi
    hàm đồng bộ trong 1 thread khác mà vẫn await liền — task khác PHẢI
    tiến được trong lúc resolve()/_finish() đang chạy trên thread."""
    import asyncio
    import time

    class SlowStore:
        def usage_since(self, **kwargs):
            time.sleep(0.3)          # mô phỏng round-trip Postgres đồng bộ
            from src.llm.store import Usage
            return Usage(requests=0, total_tokens=0)

        def record(self, **kwargs):
            time.sleep(0.3)

    ledger = BudgetLedger(SlowStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))

    progressed = []

    async def dem_nhip():
        for i in range(6):
            await asyncio.sleep(0.05)
            progressed.append(i)

    task = asyncio.create_task(dem_nhip())
    await router.ainvoke("router", [HumanMessage("hi")])
    await task

    assert len(progressed) >= 4, (
        f"chỉ tiến {len(progressed)}/6 nhịp — event loop có vẻ bị chặn "
        "trong lúc ainvoke chạy resolve()/_finish() đồng bộ")
```

File `test_router_invoke.py` đã có sẵn `from langchain_core.messages import HumanMessage` và `from tests.llm.conftest import (FakeChatClient, ..., fake_ai, ...)` ở đầu file (dòng 1-9) — không cần thêm import nào.

- [ ] **Bước 6: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router_invoke.py -v -k khong_chan_event_loop`
Expected: PASS.

- [ ] **Bước 7: Chạy toàn bộ test tầng llm, xác nhận không hồi quy**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/ -v -m "not integration and not live"`
Expected: toàn bộ PASS (baseline cũ + 2 test mới).

- [ ] **Bước 8: Commit**

```bash
git add backend/src/llm/store.py backend/src/llm/router.py backend/tests/llm/test_store.py backend/tests/llm/test_router_invoke.py
git commit -m "fix(llm): vá 2 blocker hạ tầng — pool timeout ngắn + ainvoke không chặn event loop

Blocker #1 (store.py): ConnectionPool thiếu timeout → DB không tới được thì
chặn ~90s trước khi BudgetLedger fail-open. Thêm timeout=2.0 +
connect_timeout=2 — cố ý NGẮN vì sổ ngân sách là tư vấn, đã fail-open sẵn.

Blocker #2 (router.py): Router.ainvoke() gọi BudgetLedger.can_afford()/
record() ĐỒNG BỘ bên trong async def — chặn event loop dưới FastAPI/
LangGraph async. Vá bằng asyncio.to_thread tại đúng 2 điểm (resolve, _finish).
BudgetLedger/UsageStore KHÔNG đổi — giữ nguyên tuyên bố 'chính sách thuần,
KHÔNG biết Postgres tồn tại', test SP-1A còn nguyên giá trị.

Test mới chứng minh, không chỉ khẳng định: cấu hình timeout thật sự truyền
xuống ConnectionPool; và một task khác THỰC SỰ tiến được trong lúc ainvoke
đang chạy resolve/finish trên thread nền (store giả cố tình chậm 0.3s)."
```

---

### Task 2: Vá blocker #3 — `tiktoken` không chạm mạng trên đường mặc định

**Files:**
- Modify: `backend/src/llm/tokens.py`
- Test: `backend/tests/llm/test_tokens.py`

**Interfaces:**
- Consumes: Không đổi
- Produces: `estimate_base_tokens(messages, tools=None) -> int` — chữ ký giữ nguyên, thêm nhánh fallback khi `tiktoken.get_encoding()` ném lỗi

- [ ] **Bước 1: Sửa `tokens.py` — bắt lỗi nạp encoder, tụt về ước lượng thô**

Mở `backend/src/llm/tokens.py`. Thay toàn bộ `_encoder()` (dòng 21-27) và `estimate_base_tokens()` (dòng 51-63) bằng:

```python
import logging

logger = logging.getLogger(__name__)

_enc = None
_enc_failed = False


def _encoder():
    # Nạp lười: tiktoken tải bảng mã ở lần dùng đầu, không nên trả giá đó lúc
    # import module. Blocker #3: lần nạp đầu tiên CẦN MẠNG — nằm trên đường
    # test mặc định vốn phải không chạm mạng. Máy dev có cache nên không lộ;
    # CI lạnh sẽ vỡ. Nạp lỗi thì đánh dấu và không thử lại mỗi lượt gọi (thử
    # lại mỗi lần sẽ làm MỌI request đều trả giá network timeout).
    global _enc, _enc_failed
    if _enc is None and not _enc_failed:
        try:
            _enc = tiktoken.get_encoding(_ENCODING)
        except Exception:
            _enc_failed = True
            logger.warning(
                "không nạp được tiktoken (%s) — tụt về ước lượng thô "
                "ký tự/4. Không ảnh hưởng kế toán: total_tokens từ response "
                "mới là con số có thẩm quyền, đây chỉ dùng để ước lượng "
                "TRƯỚC khi gọi.", _ENCODING, exc_info=True)
    return _enc


def _estimate_thô(messages: list, tools: list | None) -> int:
    total = sum(len(_text_of(m)) for m in messages)
    if tools:
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(blob)
    return total // 4


def estimate_base_tokens(messages: list, tools: list | None = None) -> int:
    """Ước lượng token đầu vào cho một lượt gọi, chưa nhân hệ số provider."""
    if not messages and not tools:
        return 0
    enc = _encoder()
    if enc is None:
        return _estimate_thô(messages, tools)
    total = sum(len(enc.encode(_text_of(m))) for m in messages)
    if tools:
        # Schema tool đi vào prompt dưới dạng JSON. Với agent ERP bind hàng
        # chục tool, phần này thường lớn hơn cả câu hỏi người dùng — bỏ qua nó
        # là ước lượng thiếu ở đúng chỗ đau nhất (Groq 8K TPM).
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(enc.encode(blob))
    return total
```

- [ ] **Bước 2: Test — nạp lỗi thì tụt về ước lượng thô, không chạm mạng**

Thêm vào `backend/tests/llm/test_tokens.py`:

```python
def test_tiktoken_khong_nap_duoc_thi_tut_ve_uoc_luong_tho(monkeypatch):
    """Blocker #3: đường mặc định không được chạm mạng. Mô phỏng lỗi nạp
    (giống lần đầu chạy không có cache, CI lạnh) — hàm vẫn phải trả số dùng
    được, không ném lỗi, không thử nạp lại lần thứ hai trong cùng test."""
    import src.llm.tokens as tokens_mod

    tokens_mod._enc = None
    tokens_mod._enc_failed = False

    def _no_mang(*a, **k):
        raise OSError("network is unreachable (mô phỏng)")

    monkeypatch.setattr(tokens_mod.tiktoken, "get_encoding", _no_mang)

    from langchain_core.messages import HumanMessage
    n = tokens_mod.estimate_base_tokens([HumanMessage("một hai ba bốn")])
    assert n > 0
    assert tokens_mod._enc_failed is True

    # Gọi lại lần 2 KHÔNG được thử nạp lại (đã đánh dấu thất bại)
    calls_before = 0
    def _dem(*a, **k):
        nonlocal calls_before
        calls_before += 1
        raise OSError("vẫn không có mạng")
    monkeypatch.setattr(tokens_mod.tiktoken, "get_encoding", _dem)
    tokens_mod.estimate_base_tokens([HumanMessage("lượt hai")])
    assert calls_before == 0

    # dọn lại trạng thái module-level cho test khác trong tiến trình
    tokens_mod._enc = None
    tokens_mod._enc_failed = False
```

- [ ] **Bước 3: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_tokens.py -v`
Expected: PASS — toàn bộ file, bao gồm test cũ và test mới.

- [ ] **Bước 4: Xác nhận đường mặc định thật sự không chạm mạng**

Không có cách chặn mạng trực tiếp trong test đơn giản, nhưng test ở Bước 2 đã chứng minh gián tiếp: khi `tiktoken.get_encoding` bị mock để ném lỗi (đại diện cho "không có mạng"), hàm không crash và không thử gọi lại — đó chính là hành vi cần có trên CI lạnh không cache.

- [ ] **Bước 5: Chạy toàn bộ test tầng llm**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/ -v -m "not integration and not live"`
Expected: toàn bộ PASS.

- [ ] **Bước 6: Commit**

```bash
git add backend/src/llm/tokens.py backend/tests/llm/test_tokens.py
git commit -m "fix(llm): tiktoken tụt về ước lượng thô khi không nạp được bảng mã

Blocker #3: lần dùng đầu tiên tiktoken.get_encoding() tải bảng mã QUA MẠNG —
nằm trên đường test MẶC ĐỊNH vốn phải không chạm mạng. Máy dev có cache nên
không lộ; CI lạnh sẽ vỡ.

Vá: bắt lỗi nạp, đánh dấu _enc_failed để không thử lại mỗi lượt gọi, tụt về
ước lượng ký tự/4. Chấp nhận được vì con số này chỉ dùng để kiểm TPM TRƯỚC
khi gọi — total_tokens từ response mới là con số có thẩm quyền để ghi sổ
(budget.py record())."
```

---

### Task 3: Dựng cấu trúc gói `evals/`/`jobs/` — port hạ tầng thuần (fixtures, cases, registry, resilience)

**Files:**
- Create: `backend/evals/__init__.py`, `backend/evals/fixtures/__init__.py`, `backend/evals/fixtures/chunks.json`, `backend/evals/cases.py`
- Create: `backend/jobs/__init__.py`, `backend/jobs/registry.py`, `backend/jobs/resilience.py`
- Test: `backend/tests/jobs/__init__.py`, `backend/tests/jobs/conftest.py`, `backend/tests/jobs/test_registry.py`, `backend/tests/jobs/test_resilience.py`

**Interfaces:**
- Consumes: `src.rag.types.Chunk` (đã có, Task 4 SP-1B)
- Produces: `evals.fixtures.load_chunks(topic) -> list[Chunk]`, `evals.fixtures.available_topics() -> list[str]`, `evals.cases.{INTENT,CONFIRM,CHITCHAT,PLANNER,READ,SYNTHESIS,MULTI_SOURCE}_CASES`, `evals.cases.WRITE_TOOL_NAMES`, `evals.cases.HALLUCINATION_MARKERS`, `jobs.registry.{PASS,GATE_FAIL,INFRA_ERROR,Job,JobResult,JOBS,LOGS_DIR,register,write_result}`, `jobs.resilience.{CircuitBreakerOpen,run_resilient}` — tất cả file này KHÔNG import gì từ tầng nghiệp vụ ngoại trừ `fixtures/__init__.py` cần `Chunk`

Bốn file này **không cần thích nghi logic** — chỉ đổi đường import (`backend.src.X` → `src.X`, `backend.evals.X`/`backend.jobs.X` → `evals.X`/`jobs.X`, bỏ `sys.path.insert`).

- [ ] **Bước 1: Tạo cấu trúc gói + chép file thuần**

```bash
mkdir -p backend/evals/fixtures backend/jobs
touch backend/evals/__init__.py backend/jobs/__init__.py
cp "/d/Project/backend/evals/fixtures/chunks.json" backend/evals/fixtures/
cp "/d/Project/backend/evals/cases.py" backend/evals/
cp "/d/Project/backend/jobs/registry.py" backend/jobs/
cp "/d/Project/backend/jobs/resilience.py" backend/jobs/
```

`cases.py` và `resilience.py` và `registry.py` không có occurrence nào của `backend.src`/`backend.evals`/`backend.jobs` (đã kiểm — `cases.py` không import gì, `registry.py`/`resilience.py` chỉ dùng thư viện chuẩn). **Không cần sửa gì trong 3 file này.**

- [ ] **Bước 2: Chép + sửa `fixtures/__init__.py`**

```bash
cp "/d/Project/backend/evals/fixtures/__init__.py" backend/evals/fixtures/
```

Sửa dòng 16 trong `backend/evals/fixtures/__init__.py`:

```python
from backend.src.rag.types import Chunk
```

thành:

```python
from src.rag.types import Chunk
```

- [ ] **Bước 3: Xác nhận `Chunk` nạp đúng**

Run: `cd backend && .venv/Scripts/python.exe -c "from evals.fixtures import load_chunks, available_topics; print(available_topics())"`
Expected: in ra danh sách topic (vd `['chinh_sach_hoan_hang', 'chinh_sach_thanh_toan', 'sla_giao_hang', ...]`), không lỗi import.

- [ ] **Bước 4: Chép + sửa test `registry`/`resilience`**

```bash
mkdir -p backend/tests/jobs
touch backend/tests/jobs/__init__.py
cp "/d/Project/backend/tests/jobs/conftest.py" backend/tests/jobs/
cp "/d/Project/backend/tests/jobs/test_registry.py" backend/tests/jobs/
cp "/d/Project/backend/tests/jobs/test_resilience.py" backend/tests/jobs/
```

Trong cả 3 file, xoá 2 dòng đầu kiểu:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
```

(giữ `import os`/`import sys` KHÁC nếu file còn dùng cho việc khác — `test_registry.py`/`conftest.py` không dùng `os`/`sys` cho gì khác nên xoá cả 2 dòng import; kiểm bằng grep trước khi xoá).

Rồi thay mọi `from backend.jobs.X import Y` / `from backend.jobs import X` thành `from jobs.X import Y` / `from jobs import X`.

- [ ] **Bước 5: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/ -v`
Expected: `test_registry.py` (3 test) + `test_resilience.py` toàn bộ PASS.

- [ ] **Bước 6: Xác nhận grep sạch quy ước cũ trong 6 file vừa tạo/sửa**

Run: `grep -rn "backend\.src\|backend\.evals\|backend\.jobs\|sys\.path\.insert" backend/evals/ backend/jobs/ backend/tests/jobs/`
Expected: không có kết quả nào (rỗng).

- [ ] **Bước 7: Commit**

```bash
git add backend/evals backend/jobs backend/tests/jobs
git commit -m "feat(evals): dựng cấu trúc gói evals/jobs — port hạ tầng thuần

fixtures/, cases.py, registry.py, resilience.py — không cần thích nghi logic,
chỉ đổi đường import (backend.X -> X, bỏ sys.path.insert), y hệt quy ước đã
áp dụng 6 lần xuyên suốt SP-1B.

evals/ và jobs/ là package NGANG HÀNG với src/ dưới backend/, không nằm
trong src/ — chạy bằng cd backend && python -m evals.X / python -m jobs,
cùng quy ước 'backend/ không có __init__.py' mà Task 4 SP-1B đã chốt."
```

---

### Task 4: Port + thích nghi `evals/run_eval.py` — 7 hàm đo, `_llm()` dùng `RoutedChatModel`

**Files:**
- Create: `backend/evals/run_eval.py`
- Test: `backend/tests/jobs/test_eval_chitchat.py`, `test_eval_multi_source.py`, `test_eval_planner.py`, `test_eval_read.py`, `test_eval_synthesis.py`, `test_eval_latency.py`, `test_pacing.py`, `test_run_eval_errors.py`

**Interfaces:**
- Consumes: `evals.cases.*`, `evals.fixtures.*`, `jobs.resilience.run_resilient`, `src.agents.prompts.{INTENT_ROUTER_PROMPT,CHITCHAT_PROMPT,WRITE_PLANNER_PROMPT,SYSTEM_PROMPT,RAG_SYNTHESIS_PROMPT,FUSION_PROMPT}`, `src.agents.confirmation._LLM_PROMPT`, `src.agents.synthesis.{SENTINEL,_format_context,_MARKER_RE}`, `src.agents.nodes._parse_plan_tiered`, `src.erp_query.tools.build_erp_query_tools`, `src.llm.router.{Router,RoutedChatModel,build_router}`
- Produces: `run_eval._llm(alias, role) -> RoutedChatModel`, `run_eval.eval_{intent,confirm,chitchat,planner,read,synthesis,multi_source}(llm, pace=0.0, checkpoint_path=None) -> dict` (chữ ký giữ nguyên bản gốc — Task 5 gọi các hàm này), `run_eval._percentiles`, `run_eval._cited_indices`, `run_eval._digits`, `run_eval.main(argv=None)` (CLI độc lập)

- [ ] **Bước 1: Chép file gốc**

```bash
cp "/d/Project/backend/evals/run_eval.py" backend/evals/
```

- [ ] **Bước 2: Sửa khối import (dòng 15-31)**

Thay:

```python
import argparse, asyncio, json, math, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.evals.cases import (CHITCHAT_CASES, CONFIRM_CASES,
                                 HALLUCINATION_MARKERS, INTENT_CASES,
                                 MULTI_SOURCE_CASES, PLANNER_CASES,
                                 READ_CASES, SYNTHESIS_CASES,
                                 WRITE_TOOL_NAMES)
from backend.evals import fixtures
from backend.src.agents.prompts import INTENT_ROUTER_PROMPT, CHITCHAT_PROMPT
from backend.src.agents.confirmation import _LLM_PROMPT
from backend.src.agents.prompts import WRITE_PLANNER_PROMPT
from backend.src.agents.prompts import SYSTEM_PROMPT
from backend.src.agents.prompts import RAG_SYNTHESIS_PROMPT
from backend.src.agents.prompts import FUSION_PROMPT
from backend.src.agents.synthesis import SENTINEL, _format_context, _MARKER_RE
from backend.src.agents.nodes import _parse_plan_tiered
from backend.src.erp_query.tools import build_erp_query_tools
from backend.jobs.resilience import run_resilient
```

bằng:

```python
import argparse, asyncio, json, math, os, re, sys, time

from langchain_core.messages import HumanMessage, SystemMessage

from evals.cases import (CHITCHAT_CASES, CONFIRM_CASES,
                         HALLUCINATION_MARKERS, INTENT_CASES,
                         MULTI_SOURCE_CASES, PLANNER_CASES,
                         READ_CASES, SYNTHESIS_CASES,
                         WRITE_TOOL_NAMES)
from evals import fixtures
from src.agents.prompts import INTENT_ROUTER_PROMPT, CHITCHAT_PROMPT
from src.agents.confirmation import _LLM_PROMPT
from src.agents.prompts import WRITE_PLANNER_PROMPT
from src.agents.prompts import SYSTEM_PROMPT
from src.agents.prompts import RAG_SYNTHESIS_PROMPT
from src.agents.prompts import FUSION_PROMPT
from src.agents.synthesis import SENTINEL, _format_context, _MARKER_RE
from src.agents.nodes import _parse_plan_tiered
from src.erp_query.tools import build_erp_query_tools
from jobs.resilience import run_resilient
```

(`ChatOpenAI`/`langchain_openai` bị xoá — không còn dùng, thay bằng `RoutedChatModel` ở Bước 3.)

- [ ] **Bước 3: Viết lại `_llm()` — dùng `RoutedChatModel` với `pin`, router dựng lười dùng chung**

Thay toàn bộ hàm `_llm` (dòng 41-45):

```python
def _llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(model=model,
                      base_url=os.environ.get("LITELLM_URL", "http://localhost:4000/v1"),
                      api_key=os.environ.get("LITELLM_MASTER_KEY", ""),
                      temperature=0, timeout=60)
```

bằng:

```python
# Router dựng LƯỜI, dùng CHUNG cho mọi lượt gọi eval trong một tiến trình —
# không phải một router mới mỗi case. build_router() mở PostgresUsageStore
# (fail-loud nếu bảng llm_usage chưa migrate), nên dựng đúng một lần.
_router: "Router | None" = None


def _get_router() -> "Router":
    global _router
    if _router is None:
        from src.llm.router import build_router
        _router = build_router()
    return _router


def _llm(alias: str, role: str) -> "RoutedChatModel":
    """RoutedChatModel ghim vào ĐÚNG một model (spec §2.1): resolve() với pin
    bỏ qua toàn bộ chuỗi VÀ không đọc sổ ngân sách (router.py resolve()) —
    trạng thái ngân sách không ảnh hưởng phép đo. _finish() vẫn GHI lượng
    tiêu thụ thật vào sổ — eval tiêu hạn mức thật thì sổ phải biết cả hai
    chiều. role chỉ dùng để gắn nhãn/ContextVar cô lập, KHÔNG ảnh hưởng model
    được chọn khi đã ghim (xem router.py resolve(), nhánh pin is not None
    trả sớm trước khi đụng tới role)."""
    from src.llm.router import RoutedChatModel
    return RoutedChatModel(_get_router(), role, pin=alias)
```

- [ ] **Bước 4: Sửa lời gọi `_llm` trong `main()` (CLI độc lập, cuối file)**

Tìm dòng:

```python
        result = await _FN[args.set](_llm(args.model), pace=args.pace)
```

Thay bằng:

```python
        result = await _FN[args.set](_llm(args.model, role=args.set), pace=args.pace)
```

- [ ] **Bước 5: Sửa import cục bộ trong `main()` (chống circular import)**

Tìm đoạn cuối `main()`:

```python
        from backend.jobs.eval_gate import _gate
```

Thay bằng:

```python
        from jobs.eval_gate import _gate
```

- [ ] **Bước 6: Xác nhận không còn dấu vết cũ**

Run: `grep -n "backend\.\|ChatOpenAI\|LITELLM\|sys\.path\.insert" backend/evals/run_eval.py`
Expected: **rỗng** (không match).

- [ ] **Bước 7: Chép + sửa 8 file test đi kèm**

```bash
for f in test_eval_chitchat test_eval_multi_source test_eval_planner \
         test_eval_read test_eval_synthesis test_eval_latency test_pacing \
         test_run_eval_errors; do
  cp "/d/Project/backend/tests/jobs/$f.py" backend/tests/jobs/
done
```

Trong cả 8 file: xoá khối `sys.path.insert` (2-3 dòng đầu, giữ `import os`/`import sys` nếu file còn dùng chỗ khác — kiểm bằng grep trước khi xoá dòng import), rồi thay:
- `from backend.evals import X` → `from evals import X`
- `from backend.evals.X import Y` → `from evals.X import Y`
- `from backend.jobs...` → `from jobs...` (nếu có)

Không file nào trong 8 file này gọi `run_eval._llm` trực tiếp — chúng tự tạo LLM giả (`_FakeLLM`, `_ScriptedLLM`) và gọi thẳng `run_eval.eval_intent(llm, ...)` v.v. **Không cần sửa gì khác ngoài đường import.**

- [ ] **Bước 8: Sửa riêng 1 test trong `test_run_eval_errors.py` — chữ ký `_llm` đổi**

Trong `test_run_eval_errors.py`, hàm `test_main_exits_2_on_errors_and_never_saves_baseline` có dòng:

```python
    monkeypatch.setattr(run_eval, "_llm", lambda m: object())
```

Sửa thành:

```python
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
```

(Đây là sửa nối dây thuần — `_llm` giờ nhận 2 tham số, monkeypatch phải khớp arity mới. Không phải thay đổi hành vi được kiểm.)

- [ ] **Bước 9: Chạy toàn bộ 8 file test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_chitchat.py tests/jobs/test_eval_multi_source.py tests/jobs/test_eval_planner.py tests/jobs/test_eval_read.py tests/jobs/test_eval_synthesis.py tests/jobs/test_eval_latency.py tests/jobs/test_pacing.py tests/jobs/test_run_eval_errors.py -v`
Expected: toàn bộ PASS. Nếu có test đỏ vì lý do KHÁC import/arity `_llm` (tức hành vi của `eval_*` thật sự khác) → DỪNG, báo cáo, không tự sửa test.

- [ ] **Bước 10: Xác nhận grep sạch cho cả 8 file test**

Run: `grep -rln "backend\.\|sys\.path\.insert" backend/tests/jobs/test_eval_chitchat.py backend/tests/jobs/test_eval_multi_source.py backend/tests/jobs/test_eval_planner.py backend/tests/jobs/test_eval_read.py backend/tests/jobs/test_eval_synthesis.py backend/tests/jobs/test_eval_latency.py backend/tests/jobs/test_pacing.py backend/tests/jobs/test_run_eval_errors.py`
Expected: rỗng.

- [ ] **Bước 11: Commit**

```bash
git add backend/evals/run_eval.py backend/tests/jobs/test_eval_chitchat.py backend/tests/jobs/test_eval_multi_source.py backend/tests/jobs/test_eval_planner.py backend/tests/jobs/test_eval_read.py backend/tests/jobs/test_eval_synthesis.py backend/tests/jobs/test_eval_latency.py backend/tests/jobs/test_pacing.py backend/tests/jobs/test_run_eval_errors.py
git commit -m "feat(evals): port run_eval.py — 7 hàm đo + _llm() dùng RoutedChatModel

Không phải port nguyên văn: _llm() cũ dựng ChatOpenAI trỏ LiteLLM (đã gỡ bỏ
hoàn toàn ở SP-1) — thay bằng RoutedChatModel(router, role, pin=alias).
resolve() với pin bỏ qua chuỗi VÀ không đọc sổ ngân sách (đã đúng sẵn ở
router.py, không phải sửa gì), nhưng _finish() vẫn ghi tiêu thụ thật — đo
qua Router là đo đúng đường sản xuất (_gop_content, strip_thought) thay vì
model trần.

7 hàm eval_* + toàn bộ test đi kèm (8 file) port nguyên logic, chỉ đổi đường
import — không file test nào gọi _llm trực tiếp ngoại trừ 1 chỗ trong
test_run_eval_errors.py (chỉnh arity monkeypatch cho khớp chữ ký mới)."
```

---

### Task 5: Port + thích nghi `jobs/eval_gate.py` + `jobs/__main__.py`

**Files:**
- Create: `backend/jobs/eval_gate.py`
- Create: `backend/jobs/__main__.py`
- Test: `backend/tests/jobs/test_eval_gate.py`, `test_cli.py`

**Interfaces:**
- Consumes: `evals.run_eval`, `jobs.registry.*`, `src.llm.catalog.{chain_for,ROLES}`
- Produces: `eval_gate.run(args) -> JobResult`, `eval_gate.EVAL_FN`, `eval_gate.BASELINES`, `eval_gate.ROLE_FOR_SET`, `eval_gate._gate(set_name, result, base) -> bool` (Task 4's `run_eval.main()` import cục bộ hàm này — đã trỏ đúng `jobs.eval_gate`)

- [ ] **Bước 1: Chép file gốc**

```bash
cp "/d/Project/backend/jobs/eval_gate.py" backend/jobs/
```

- [ ] **Bước 2: Sửa khối import (dòng 13-21)**

Thay:

```python
import asyncio
import json
from pathlib import Path

from backend.evals import run_eval
from backend.jobs import registry
from backend.jobs.registry import (GATE_FAIL, INFRA_ERROR, PASS, Job, JobResult,
                                   register)
from backend.src.agents.models import is_qwen, model_for
```

bằng:

```python
import asyncio
import json
from pathlib import Path

from evals import run_eval
from jobs import registry
from jobs.registry import (GATE_FAIL, INFRA_ERROR, PASS, Job, JobResult,
                           register)
from src.llm.catalog import chain_for
```

- [ ] **Bước 3: Xoá `_auto_pace`, thay bằng công thức suy từ catalog**

Tìm:

```python
def _auto_pace(model: str) -> float:
    return 0.0 if is_qwen(model) else CLOUD_PACE_S
```

Xoá hàm này hoàn toàn (không còn khái niệm local/qwen — SP-1 bỏ Ollama khỏi đường chat hoàn toàn). Xoá luôn hằng `CLOUD_PACE_S = 5.0` (dòng 24) — không còn dùng ở đâu sau bước này.

- [ ] **Bước 4: Sửa `run()` — model mặc định từ `chain_for`, nhịp suy từ `rpm`**

Tìm đoạn trong `run()`:

```python
    for set_name in sets:
        model = args.model if args.model is not None else model_for(ROLE_FOR_SET[set_name])
        pace = args.pace if args.pace is not None else _auto_pace(model)
```

Thay bằng:

```python
    for set_name in sets:
        role = ROLE_FOR_SET[set_name]
        spec = chain_for(role)[0]
        model = args.model if args.model is not None else spec.alias
        # (60/rpm)*1.2: chậm hơn mức RPM cho phép 20% để có biên — suy trực
        # tiếp từ catalog, không còn khái niệm "local thì 0s" (không còn
        # model local nào trong catalog kể từ SP-1).
        pace = args.pace if args.pace is not None else (60.0 / spec.rpm) * 1.2
```

- [ ] **Bước 5: Sửa lời gọi `run_eval._llm` bên trong `run()`**

Tìm dòng (trong khối `try` gọi eval thật):

```python
            result = asyncio.run(EVAL_FN[set_name](
                run_eval._llm(model), pace=pace, checkpoint_path=checkpoint))
```

Thay bằng:

```python
            result = asyncio.run(EVAL_FN[set_name](
                run_eval._llm(model, role=role), pace=pace, checkpoint_path=checkpoint))
```

- [ ] **Bước 6: Xác nhận `_gate()` KHÔNG đổi**

Đọc lại toàn bộ hàm `_gate()` (dòng 51-76 bản gốc) — copy y nguyên, không sửa một ký tự. Nó mã hoá ADR-009 QĐ M3.

- [ ] **Bước 7: Xác nhận grep sạch**

Run: `grep -n "backend\.\|is_qwen\|model_for\|CLOUD_PACE_S\|sys\.path\.insert" backend/jobs/eval_gate.py`
Expected: rỗng.

- [ ] **Bước 8: Chép + sửa `jobs/__main__.py` — bỏ 4 import job ngoài phạm vi**

```bash
cp "/d/Project/backend/jobs/__main__.py" backend/jobs/
```

Sửa khối import job (dòng 23-28):

```python
# ── job modules đăng ký tại import (Task 3/4 thêm dòng ở đây) ────────────────
from backend.jobs import eval_gate  # noqa: F401  (đăng ký side-effect)
from backend.jobs import e2e_smoke  # noqa: F401  (đăng ký side-effect)
from backend.jobs import e2e_skill_discount  # noqa: F401  (đăng ký side-effect)
from backend.jobs import e2e_skill_warehouse  # noqa: F401  (đăng ký side-effect)
from backend.jobs import e2e_skill_delivery  # noqa: F401  (đăng ký side-effect)

from backend.jobs.registry import (INFRA_ERROR, JOBS, JobResult, write_result)
```

thành:

```python
# ── job modules đăng ký tại import ───────────────────────────────────────────
# 4 job e2e_* (D:\Project) cần backend :8000 sống (kế hoạch C2, chưa tồn tại
# ở đây) — NGOÀI PHẠM VI SP-1C1, cố ý không port. Thêm lại khi C2 xong.
from jobs import eval_gate  # noqa: F401  (đăng ký side-effect)

from jobs.registry import (INFRA_ERROR, JOBS, JobResult, write_result)
```

- [ ] **Bước 9: Chạy job runner tay, xác nhận đăng ký đúng**

Run: `cd backend && .venv/Scripts/python.exe -m jobs list`
Expected: in ra đúng 1 dòng `eval-gate [schedulable    ] M3 gate: ...`, không lỗi import (không đòi hỏi `e2e_smoke` v.v.).

- [ ] **Bước 10: Chép + sửa test**

```bash
cp "/d/Project/backend/tests/jobs/test_eval_gate.py" backend/tests/jobs/
cp "/d/Project/backend/tests/jobs/test_cli.py" backend/tests/jobs/
```

Trong cả 2 file: xoá khối `sys.path.insert`, thay `from backend.evals import X`/`from backend.jobs...` → `from evals import X`/`from jobs...`.

Trong `test_eval_gate.py`, hàm `_patch()` (định nghĩa gần đầu file) có dòng:

```python
    monkeypatch.setattr(run_eval, "_llm", lambda m: object())
```

Sửa thành:

```python
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
```

4 chỗ khác trong file cũng gọi `monkeypatch.setattr(run_eval, "_llm", lambda m: object())` độc lập (không qua `_patch()`) — trong các hàm `test_eval_exception_exit_two`, `test_chitchat_zero_violations_passes`, `test_chitchat_nonzero_violations_fails`, `test_chitchat_never_reads_a_baseline_file`. Sửa **cả 4 chỗ** giống hệt cách trên (`lambda m, role=None: object()`).

- [ ] **Bước 11: Xoá/viết lại 2 test kiểm tra hành vi ĐÃ ĐỔI THẬT (không phải nối dây)**

Đây là chỗ **hành vi thay đổi thật** — model mặc định giờ đến từ `chain_for()[0].alias` (catalog tĩnh), không còn đọc biến môi trường `MODEL_ROUTER`/`MODEL_EVALUATOR`/`AGENT_MODEL`, và không còn khái niệm "local qwen thì pace=0". Hai test sau **không port nguyên được** — thay bằng bản kiểm đúng thiết kế mới, đã duyệt ở spec §2:

Tìm và **xoá hoàn toàn** hàm `test_default_measures_live_config`:

```python
def test_default_measures_live_config(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setenv("MODEL_ROUTER", "gemini-flash-lite")
    monkeypatch.delenv("MODEL_EVALUATOR", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)   # tránh flaky theo env máy dev
    result = eval_gate.run(_args())
    assert result.detail["intent"]["model"] == "gemini-flash-lite"
    assert result.detail["confirm"]["model"] == "qwen3:8b"   # default local
```

Thay bằng:

```python
def test_khong_truyen_model_thi_dung_dau_chuoi_catalog(monkeypatch):
    """Thay test_default_measures_live_config (bản cũ đọc MODEL_ROUTER/
    MODEL_EVALUATOR/AGENT_MODEL — cơ chế đó đã bị xoá ở SP-1B Task 8). Hành vi
    MỚI: không truyền --model thì mỗi bộ dùng đúng chain_for(role)[0].alias
    từ catalog tĩnh — không đọc biến môi trường nào."""
    _patch(monkeypatch)
    result = eval_gate.run(_args())
    assert result.detail["intent"]["model"] == "gemma-4-26b"
    assert result.detail["confirm"]["model"] == "groq-gpt-oss-20b"
```

Tìm và **xoá hoàn toàn** hàm `test_pace_auto_cloud_5s_local_0`:

```python
def test_pace_auto_cloud_5s_local_0(monkeypatch):
    fi, fc = _patch(monkeypatch)
    monkeypatch.setenv("MODEL_ROUTER", "gemini-flash-lite")   # cloud
    monkeypatch.delenv("MODEL_EVALUATOR", raising=False)      # local qwen
    monkeypatch.delenv("AGENT_MODEL", raising=False)          # tránh flaky theo env
    eval_gate.run(_args())
    assert fi.calls[0]["pace"] == eval_gate.CLOUD_PACE_S       # 5.0
    assert fc.calls[0]["pace"] == 0.0
```

Thay bằng:

```python
def test_nhip_tu_dong_suy_tu_rpm_catalog(monkeypatch):
    """Thay test_pace_auto_cloud_5s_local_0 (bản cũ giả định có model 'local'
    pace=0 — không còn model local nào trong catalog kể từ SP-1). Hành vi
    MỚI: pace luôn = (60/rpm)*1.2, không có nhánh đặc biệt nào."""
    fi, fc = _patch(monkeypatch)
    eval_gate.run(_args())
    # gemma-4-26b (router, dòng đầu) rpm=30 -> (60/30)*1.2 = 2.4
    assert fi.calls[0]["pace"] == pytest.approx(2.4)
    # groq-gpt-oss-20b (evaluator, dòng đầu) rpm=30 -> cùng 2.4
    assert fc.calls[0]["pace"] == pytest.approx(2.4)
```

Kiểm đầu file `test_eval_gate.py` đã `import pytest` — nếu chưa, thêm dòng đó.

Tìm hàm `test_model_override_applies_to_all_sets` — **giữ nguyên không đổi**, nó chỉ kiểm `--model` override áp cho mọi bộ, không phụ thuộc cơ chế mặc định cũ.

- [ ] **Bước 12: Chạy 2 file test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gate.py tests/jobs/test_cli.py -v`
Expected: toàn bộ PASS, bao gồm 2 test viết lại.

- [ ] **Bước 13: Xác nhận grep sạch**

Run: `grep -rn "backend\.\|sys\.path\.insert\|MODEL_ROUTER\|MODEL_EVALUATOR\|AGENT_MODEL\|CLOUD_PACE_S" backend/jobs/eval_gate.py backend/jobs/__main__.py backend/tests/jobs/test_eval_gate.py backend/tests/jobs/test_cli.py`
Expected: rỗng.

- [ ] **Bước 14: Chạy toàn bộ `tests/jobs/`**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/ -v -m "not integration and not live"`
Expected: toàn bộ PASS (12 file, không tính `test_e2e_smoke.py` — chưa port, ngoài phạm vi).

- [ ] **Bước 15: Commit**

```bash
git add backend/jobs/eval_gate.py backend/jobs/__main__.py backend/tests/jobs/test_eval_gate.py backend/tests/jobs/test_cli.py
git commit -m "feat(jobs): port eval_gate.py + __main__.py — bỏ model_for/is_qwen, dùng catalog

model_for()/is_qwen() xoá ở SP-1B Task 8. Thay: model mặc định mỗi bộ =
chain_for(ROLE_FOR_SET[set])[0].alias; nhịp = (60/rpm)*1.2, cả hai suy trực
tiếp từ llm/catalog.py — không còn đọc biến môi trường MODEL_ROUTER/
MODEL_EVALUATOR/AGENT_MODEL, không còn khái niệm 'local thì pace=0' (không
còn model local nào trong catalog kể từ SP-1). Công thức _gate() giữ NGUYÊN
VĂN — nó mã hoá ADR-009 QĐ M3.

__main__.py bỏ 4 import job e2e_* (cần backend :8000 sống — kế hoạch C2,
ngoài phạm vi C1).

2 test (test_default_measures_live_config, test_pace_auto_cloud_5s_local_0)
KHÔNG port nguyên được — chúng kiểm hành vi của cơ chế env-var đã bị xoá.
Viết lại thành test_khong_truyen_model_thi_dung_dau_chuoi_catalog /
test_nhip_tu_dong_suy_tu_rpm_catalog, kiểm đúng thiết kế catalog-based mới.
Đây là thay đổi HÀNH VI có chủ đích (spec §2), không phải sửa nối dây."
```

---

### Task 6: Sửa bug scanner `fabricated_number` + chấm lại baseline `multi_source`

**Files:**
- Modify: `backend/evals/run_eval.py` (hàm `eval_multi_source`)
- Create: `backend/evals/rescore_multi_source.py`
- Modify: `backend/evals/fixtures/baseline-qwen3-8b-multi_source.json` *(chép từ nguồn trước, ở Bước 1)*
- Test: `backend/tests/jobs/test_eval_multi_source.py` (thêm 1 test)

**Interfaces:**
- Consumes: `evals.fixtures.load_chunks`, `src.agents.synthesis._format_context`
- Produces: Không đổi API — chỉ đổi kết quả `fabricated_number` của `eval_multi_source()`

- [ ] **Bước 1: Chép baseline gốc (chưa chấm lại) vào đúng chỗ**

```bash
mkdir -p backend/evals
cp "/d/Project/backend/evals/baseline-qwen3-8b-intent.json" backend/evals/
cp "/d/Project/backend/evals/baseline-qwen3-8b-confirm.json" backend/evals/
cp "/d/Project/backend/evals/baseline-qwen3-8b-planner.json" backend/evals/
cp "/d/Project/backend/evals/baseline-qwen3-8b-read.json" backend/evals/
cp "/d/Project/backend/evals/baseline-qwen3-8b-synthesis.json" backend/evals/
cp "/d/Project/backend/evals/baseline-qwen3-8b-multi_source.json" backend/evals/
```

(5 baseline không phải `multi_source` không cần chấm lại — bug chỉ nằm ở scanner của `eval_multi_source`.)

- [ ] **Bước 2: Sửa bug trong `eval_multi_source()`**

Mở `backend/evals/run_eval.py`, tìm trong hàm `eval_multi_source`:

```python
        allowed = _digits(erp_block) | _digits(" ".join(c.text for c in chunks))
```

Thay bằng:

```python
        # BUG (đã sửa, spec §3): model nhìn thấy _format_context(chunks)
        # (bao gồm chỉ số [i] và nhãn mục), nhưng allowed cũ chỉ dựng từ
        # c.text trần — số nằm trong nhãn mục bị quy oan là "bịa". allowed
        # PHẢI khớp đúng thứ model thấy.
        # Mất mát đã biết: [1]..[len(chunks)] từ nay luôn hợp lệ ở mọi vị trí
        # (xem rescore_multi_source.py — bước chấm lại là trọng tài, không
        # phải chủ quan: nếu baseline hiệu chỉnh không tự đạt fabricated=0
        # thì bản sửa này SAI, phải xem lại).
        allowed = _digits(erp_block) | _digits(_format_context(chunks))
```

- [ ] **Bước 3: Test — chunk có nhãn mục chứa số không còn bị quy là bịa**

Thêm vào `backend/tests/jobs/test_eval_multi_source.py`:

```python
@pytest.mark.asyncio
async def test_so_trong_nhan_muc_khong_bi_quy_la_bia(monkeypatch):
    """Tái hiện đúng bug đã sửa: _format_context() gắn chỉ số [i] + nhãn mục
    (section_path/sheet/basename) vào MỖI chunk. Trước fix, allowed chỉ dựng
    từ c.text trần nên số trong nhãn mục (vd chunk thứ [3], hay nhãn
    "(Điều 3.2)") bị quy oan là bịa dù model chỉ đang trích dẫn đúng."""
    topic = _one_case(monkeypatch)
    from evals import fixtures
    chunks = fixtures.load_chunks(topic)
    # _format_context số hoá chunk từ 1 — chunk đầu chắc chắn mang nhãn "[1]"
    llm = _ScriptedLLM([
        "Theo mục [1], đơn S00042 đạt yêu cầu trong 3 ngày.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fabricated_number"] == 0, (
        f"chỉ số [1] trong _format_context() bị quy nhầm là số bịa: "
        f"{r['fails']}")
```

- [ ] **Bước 4: Chạy test, xác nhận PASS**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source.py -v`
Expected: toàn bộ PASS bao gồm test mới. `test_fabricated_number_detected` (test cũ, dùng số "9.999.999" không có trong chunk/erp_block) vẫn PASS không đổi — số đó không liên quan `[i]`/nhãn mục.

- [ ] **Bước 5: Viết script chấm lại baseline đã lưu**

Tạo `backend/evals/rescore_multi_source.py`:

```python
"""Chấm lại baseline-qwen3-8b-multi_source.json sau khi sửa bug scanner
fabricated_number (spec §3, run_eval.py eval_multi_source()).

KHÔNG chạy lại qwen3:8b — dùng đúng `fabricated` đã lưu trong `fails` của
baseline gốc (tính trên VĂN BẢN ĐẦY ĐỦ khi baseline được chụp), rồi lọc lại
theo allowed_new bằng đại số tập hợp:

    fabricated_new = fabricated_old \\ allowed_new

Đúng vì allowed_new ⊇ allowed_old (_format_context chứa nguyên c.text cộng
thêm [i] và nhãn mục — chỉ TO RA, không bao giờ nhỏ đi). KHÔNG dùng trường
"response" trong bản ghi — nó bị CẮT CỤT ở 300 ký tự (run_eval.py dòng
"response": body[:300]), quét lại đoạn cắt sẽ đếm thiếu và sai lặng lẽ.

Chạy: cd backend && .venv/Scripts/python.exe -m evals.rescore_multi_source
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from evals import fixtures
from evals.cases import MULTI_SOURCE_CASES
from evals.run_eval import _digits
from src.agents.synthesis import _format_context

_PATH = Path(__file__).resolve().parent / "baseline-qwen3-8b-multi_source.json"


def _allowed_new(topic: str, erp_block: str) -> set[str]:
    chunks = fixtures.load_chunks(topic)
    return _digits(erp_block) | _digits(_format_context(chunks))


def rescore() -> dict:
    data = json.loads(_PATH.read_text(encoding="utf-8"))
    original = data["fabricated_number"]

    # Map topic -> erp_block từ chính MULTI_SOURCE_CASES (bản ghi baseline
    # không lưu erp_block, chỉ lưu topic/question/response).
    by_topic_question = {(t, q): erp for t, erp, q, _doc, _erp_fact
                         in MULTI_SOURCE_CASES}

    new_fails = []
    for f in data["fails"]:
        erp_block = by_topic_question.get((f["topic"], f["question"]))
        if erp_block is None:
            raise KeyError(
                f"không khớp lại được case gốc cho {f['topic']!r}/"
                f"{f['question']!r} — MULTI_SOURCE_CASES đã đổi so với lúc "
                "chụp baseline, không chấm lại an toàn được")
        allowed_new = _allowed_new(f["topic"], erp_block)
        fabricated_new = sorted(set(f["fabricated"]) - allowed_new)
        f2 = dict(f, fabricated=fabricated_new)
        new_fails.append(f2)

    fabricated_number_new = sum(1 for f in new_fails if f["fabricated"])

    data["fails"] = new_fails
    data["fabricated_number"] = fabricated_number_new
    data["original_fabricated_number"] = original
    data["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return data


if __name__ == "__main__":
    result = rescore()
    print(f"fabricated_number: {result['original_fabricated_number']} -> "
         f"{result['fabricated_number']}")
    if result["fabricated_number"] != 0:
        print("CẢNH BÁO: baseline hiệu chỉnh KHÔNG tự đạt gate của chính nó "
             "(fabricated_number != 0) — bản sửa scanner có thể chưa đủ, "
             "hoặc qwen3:8b bịa thật. DỪNG, điều tra trước khi chạy gate "
             "thật (Task 7).")
```

- [ ] **Bước 6: Chạy script, kiểm kết quả**

Run: `cd backend && .venv/Scripts/python.exe -m evals.rescore_multi_source`
Expected: in ra `fabricated_number: 4 -> 0`. **Nếu ra khác 0 → DỪNG, không đi tiếp Task 7 — báo cáo con số thật (là 1, 2, hay 3) và các case còn `fabricated` khác rỗng trong file JSON để điều tra.**

- [ ] **Bước 7: Xác nhận idempotent**

Run lại: `cd backend && .venv/Scripts/python.exe -m evals.rescore_multi_source`
Expected: vẫn in `fabricated_number: 0 -> 0` (chạy trên baseline ĐÃ chấm lại, `original_fabricated_number` trong file lúc này là 0 từ lần chạy trước — số này KHÔNG tự sinh sai vì hàm đọc lại đúng field `fabricated_number` hiện có của file làm "trước" mỗi lần chạy).

- [ ] **Bước 8: Kiểm `git diff` của baseline — bằng chứng xuất xứ**

Run: `git diff --stat backend/evals/baseline-qwen3-8b-multi_source.json`
Expected: file đổi, có 2 field mới (`rescored_at`, `original_fabricated_number`) và `fabricated_number: 4` → `0`, `fails[*].fabricated` các phần tử liên quan rỗng đi.

- [ ] **Bước 9: Chạy toàn bộ `tests/jobs/`, xác nhận không hồi quy**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/ -v -m "not integration and not live"`
Expected: toàn bộ PASS.

- [ ] **Bước 10: Commit**

```bash
git add backend/evals/run_eval.py backend/evals/rescore_multi_source.py backend/evals/baseline-qwen3-8b-*.json backend/tests/jobs/test_eval_multi_source.py
git commit -m "fix(evals): sửa bug scanner fabricated_number + chấm lại baseline multi_source

Bug: allowed dựng từ c.text trần, nhưng model nhìn thấy _format_context(chunks)
(có [i] + nhãn mục) — số trong nhãn mục bị quy oan là bịa. Baseline qwen3:8b
vì vậy fabricated_number=4, tự nó KHÔNG đạt gate của chính nó (ADR-010 đã ghi
nhận, để lại 'fix để lại cho round sau').

Sửa: allowed = _digits(erp_block) | _digits(_format_context(chunks)) — đúng
basis model thật sự thấy.

Chấm lại KHÔNG dựng lại qwen3:8b: _format_context chứa nguyên c.text cộng
thêm [i]+nhãn nên allowed_new ⊇ allowed_old (tính đơn điệu) — suy chính xác
fabricated_new = fabricated_old \\ allowed_new từ đúng trường 'fabricated'
đã lưu (tính trên văn bản ĐẦY ĐỦ lúc chụp baseline). KHÔNG dùng trường
'response' — nó bị cắt cụt 300 ký tự trong baseline, quét lại sẽ đếm thiếu.

Kết quả: fabricated_number 4 -> 0 — baseline hiệu chỉnh giờ tự đạt gate của
chính nó. Mất mát đã biết và chấp nhận: số 1..len(chunks) từ nay luôn hợp lệ
ở mọi vị trí (do chính chỉ số [i] lọt vào allowed)."
```

---

### Task 7: Chạy cổng M3 thật — 7 bộ, model ghim, bảng trước/sau

**Files:**
- Create: `docs/superpowers/plans/2026-07-30-sp1c1-eval-gate-report.md` *(báo cáo kết quả — KHÔNG phải code)*

**Interfaces:**
- Consumes: `jobs.eval_gate.run`, mọi thứ dựng ở Task 1-6
- Produces: Báo cáo bảng trước/sau — điều kiện đầu vào của C2

- [ ] **Bước 1: Xác nhận `DATABASE_URL` trỏ đúng Postgres đang chạy**

Run: `cd backend && .venv/Scripts/python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('../.env'); print(os.environ.get('DATABASE_URL'))"`
Expected: in ra chuỗi kết nối tới `youdoo-postgres` cổng 5434 (đã dựng từ SP-1B Task 3).

- [ ] **Bước 2: Xác nhận 3 khoá API thật có trong `.env`**

Run: `cd backend && .venv/Scripts/python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('../.env'); print(all(os.environ.get(k) for k in ('GOOGLE_API_KEY','GROQ_API_KEY','OPENROUTER_API_KEY')))"`
Expected: `True`.

- [ ] **Bước 3: Chạy thử 1 bộ nhỏ trước (không đốt cả 159 ca nếu có lỗi cấu hình)**

Run: `cd backend && .venv/Scripts/python.exe -m jobs run eval-gate --set chitchat`
Expected: exit 0 hoặc 1 (PASS/FAIL đều được — mục tiêu bước này là xác nhận CHẠY ĐƯỢC, không văng lỗi hạ tầng). Đọc output, xác nhận dòng `[chitchat] model=gemma-4-31b ... violations=... -> PASS/FAIL`.

Nếu văng lỗi hạ tầng (import, kết nối Postgres, key thiếu) → dừng, sửa trước khi chạy tiếp.

- [ ] **Bước 4: Chạy cả 7 bộ**

Run: `cd backend && .venv/Scripts/python.exe -m jobs run eval-gate --set all`
Expected: chạy ~10-15 phút (159 ca, nhịp theo RPM từng model). In ra 7 dòng, mỗi dòng một bộ, kèm alias model đã ghim, số đo, số baseline, PASS/FAIL. Kết quả JSON ghi ở `logs/jobs/eval-gate-<timestamp>.json` (đường dẫn `jobs.registry.LOGS_DIR`).

- [ ] **Bước 5: Đọc kết quả JSON, dựng bảng trước/sau**

Run: `cd backend && .venv/Scripts/python.exe -c "
import json, glob
p = sorted(glob.glob('../logs/jobs/eval-gate-*.json'))[-1]
d = json.load(open(p, encoding='utf-8'))
print(f'verdict tổng: {d[\"verdict\"]}')
for k, v in d['detail'].items():
    print(k, '->', v)
"`

- [ ] **Bước 6: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-07-30-sp1c1-eval-gate-report.md` với bảng 7 dòng (bộ, model ghim, số đo, baseline, PASS/FAIL) lấy trực tiếp từ JSON ở Bước 5 — không viết tay ước lượng, chép nguyên số thật.

**Nếu verdict tổng = PASS:** ghi rõ "cổng M3 xanh — C2 (main.py + Langfuse) được mở khoá", trỏ tới file spec `docs/superpowers/specs/2026-07-29-sp1c1-eval-gate-design.md` §6 làm bằng chứng đối chiếu Definition of Done.

**Nếu verdict tổng = FAIL:** ghi rõ bộ nào FAIL, số đo vs baseline, và dừng — không tiếp tục sang C2. Đây không phải một tình huống lỗi của plan này; nó là kết quả hợp lệ của cổng, và là phát hiện cần báo cáo cho người dùng quyết định bước tiếp theo (sửa model/prompt rồi chạy lại, hay chấp nhận sai lệch có lý do).

- [ ] **Bước 7: Chạy lại toàn bộ 3 chế độ test của TOÀN backend, xác nhận không hồi quy bất cứ đâu**

Run:
```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors
.venv/Scripts/python.exe -m pytest tests/ -q -m integration
```
Expected: cả hai lệnh 0 lỗi mới so với baseline trước Task 1 (731 passed / 3 skipped / 0 failed cho mode 1; 27 passed cho mode 2 — cộng thêm số test mới của các Task 1-6 trong plan này).

- [ ] **Bước 8: Kiểm fixture RAG không bị chạm bởi tác dụng phụ chạy test**

Run: `git status --short backend/tests/rag/fixtures/`
Nếu có thay đổi (tác dụng phụ đã biết xuyên suốt SP-1B): `git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`

- [ ] **Bước 9: Commit báo cáo**

```bash
git add docs/superpowers/plans/2026-07-30-sp1c1-eval-gate-report.md
git commit -m "docs: báo cáo chạy cổng M3 thật — 7 bộ, model ghim, bảng trước/sau

Kết quả thật từ jobs.eval_gate.run --set all, ghi lại nguyên số đo/baseline/
verdict mỗi bộ. Đây là điều kiện đầu vào của kế hoạch C2 (ADR-009 QĐ M3:
eval gate phải chạy TRƯỚC khi mở /v1)."
```

---

## "SP-1C1 xong" nghĩa là

Đối chiếu trực tiếp với spec §6:

1. ✅ Task 1-2: ba blocker vá xong, mỗi cái có test chứng minh (không phải "đã sửa" — "đã chứng minh không còn").
2. ✅ Task 3-5: `backend/evals/` + `backend/jobs/` chạy được trong Youdoo; grep sạch `backend.src`/`model_for`/`is_qwen`/`LITELLM`/`sys.path.insert`.
3. ✅ Task 6: scanner sửa; baseline chấm lại; baseline hiệu chỉnh **tự đạt gate của chính nó**.
4. ✅ Task 7: 7 bộ chạy thật với model ghim → bảng trước/sau đầy đủ, có alias model, ghi trong báo cáo.
5. ⚠️ Gate xanh → C2 mở khoá. Gate đỏ → dừng, báo cáo — không phải lỗi của plan này, là kết quả hợp lệ cần quyết định tiếp.
6. ✅ Task 7 Bước 7: toàn bộ test xanh ở cả hai chế độ không-mạng.

**Chưa làm được sau SP-1C1:** chưa có HTTP endpoint, chưa có Langfuse trace. Đó là C2 — chỉ bắt đầu được nếu Bước 6 của Task 7 xác nhận gate xanh.
