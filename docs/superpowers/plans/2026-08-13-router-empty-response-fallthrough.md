# Phản hồi rỗng phải là lượt gọi hỏng — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một phản hồi LLM không có nội dung dùng được phải được tính là lượt gọi hỏng, để chuỗi fallback của vai được kích hoạt — thay vì được trả về như câu trả lời hợp lệ.

**Architecture:** Sửa đúng một chỗ — `Router.invoke` / `Router.ainvoke` trong `backend/src/llm/router.py` — nên áp cho mọi vai. Nhận diện bằng luật **cấu trúc** (`content` rỗng VÀ không có `tool_calls`), không so chuỗi `finish_reason`. Mắt xích đã trả rỗng bị loại khỏi vòng chọn **trong phạm vi một lượt gọi**, không dùng cooldown.

**Tech Stack:** Python 3.11, langchain-core, pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-router-empty-response-fallthrough-design.md`

## Global Constraints

- **Định danh trong `backend/src` viết bằng TIẾNG ANH.** Chú thích và chuỗi hiển thị cho người dùng viết tiếng Việt. Đây là quy ước repo, đã bị vi phạm sáu đợt liên tiếp — không lặp lại.
- **`backend/tests` KHÁC**: thư mục này có quy ước tên hàm test phiên âm tiếng Việt không dấu, dùng nhất quán ở 19+ file. Test mới **phải theo quy ước đó** (`test_phan_hoi_rong_thi_tut_mat_xich`), không đổi sang tiếng Anh.
- **Đường có `pin` KHÔNG được đổi hành vi.** `_max_attempts` trả 1 khi có pin; gọi đúng một lần, rỗng thì trả rỗng, không tụt. Toàn bộ eval dựa vào điều này.
- **Lượt gọi bị bỏ VẪN phải vào sổ ngân sách.** Token đã tiêu thật. Bỏ qua việc ghi sổ sẽ làm sổ đếm thiếu và hỏng chính cơ chế chọn model.
- **KHÔNG đặt cooldown cho phản hồi rỗng.** Đây không phải 429 và model không ốm.
- **Phải sửa CẢ `invoke` lẫn `ainvoke`.** Hai thân hàm riêng biệt; sửa một quên một là lỗi rất dễ xảy ra ở file này.
- **Không ném exception khi cạn chuỗi vì rỗng.** Trả kết quả cuối cùng. Không caller nào bắt `ChainExhausted`; ném lỗi biến câu trả lời kém thành lỗi 500.
- **LỆNH CHẠY TEST BẮT BUỘC** — luôn kèm bộ lọc marker:

  ```
  .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
  ```

  `pytest.ini` khai marker `live`/`integration` nhưng **KHÔNG** có `addopts`
  loại trừ chúng, còn `tests/conftest.py` tự `load_dotenv()` một `.env` thật.
  Chạy `pytest` trần sẽ **gọi API LLM thật và chạm Postgres**. Sự cố đã xảy ra
  thật ở Task 1 đợt này, do chính lệnh trong plan bản đầu thiếu bộ lọc.

---

## File Structure

| file | việc |
|---|---|
| `backend/src/llm/budget.py` | thêm một giá trị `Verdict` |
| `backend/src/llm/router.py` | `_usable()`, `resolve(skip=...)`, vòng lặp `invoke`/`ainvoke`, log |
| `backend/tests/llm/conftest.py` | thêm đồ giả cho phản hồi rỗng và phản hồi gọi tool |
| `backend/tests/llm/test_router.py` | test cho `resolve(skip=...)` |
| `backend/tests/llm/test_router_invoke.py` | test hành vi tụt mắt xích |

---

## Task 1: Nền — `Verdict.EMPTY`, `resolve(skip=...)`, `_usable()`

**Files:**
- Modify: `backend/src/llm/budget.py:16-21`
- Modify: `backend/src/llm/router.py` (thêm hàm `_usable`, sửa `resolve`)
- Test: `backend/tests/llm/test_router.py`

**Interfaces:**
- Consumes: không có (task đầu)
- Produces:
  - `Verdict.EMPTY` — giá trị chuỗi `"empty_response"`
  - `_usable(message) -> bool` (module-level trong `router.py`)
  - `Router.resolve(role, base_tokens, pin=None, skip=frozenset()) -> RouteDecision`
  - `EMPTY_RESPONSE_REASON: str` — hằng module-level trong `router.py`

### Vì sao cần `skip`

`resolve()` luôn trả **mắt xích đầu tiên** còn ngân sách và không bị cooldown. Đường exception hiện tại tụt được là nhờ `_cooldown_for()` làm mắt xích hỏng biến mất khỏi vòng chọn. Phản hồi rỗng **không** đặt cooldown (Global Constraints), nên nếu không có `skip`, `resolve()` sẽ trả lại đúng mắt xích vừa rỗng và vòng lặp gọi nó ba lần rồi trả rỗng — bản sửa vô hiệu hoàn toàn.

`skip` là **cục bộ trong một lượt gọi**: không có tác dụng phụ sang request sau, khác với cooldown.

- [ ] **Bước 1: Viết test cho `resolve(skip=...)` — phải đỏ trước**

Thêm vào cuối `backend/tests/llm/test_router.py`. File này ĐÃ có sẵn
`import pytest`, `BudgetLedger`, `Verdict`, `Router`, `InMemoryUsageStore` ở
đầu file và helper `_router(clock)` — dùng lại, **không** import lại trong thân
hàm:

```python
def test_resolve_bo_qua_mat_xich_trong_skip(clock):
    """skip là cục bộ trong MỘT lượt gọi — không phải cooldown, không có tác
    dụng phụ sang request sau."""
    got = _router(clock).resolve("router", base_tokens=100,
                                 skip=frozenset({"gemma-4-26b"}))

    assert got.spec.alias == "groq-gpt-oss-20b"
    assert got.fallback_depth == 1
    assert [(s.alias, s.verdict) for s in got.skipped] == [
        ("gemma-4-26b", Verdict.EMPTY)]


def test_resolve_khong_truyen_skip_thi_khong_doi_gi(clock):
    assert _router(clock).resolve(
        "router", base_tokens=100).spec.alias == "gemma-4-26b"


def test_resolve_skip_het_chuoi_thi_nem_ChainExhausted(clock):
    with pytest.raises(ChainExhausted):
        _router(clock).resolve(
            "router", base_tokens=100,
            skip=frozenset({"gemma-4-26b", "groq-gpt-oss-20b", "or-ling"}))
```

- [ ] **Bước 2: Viết test cho `_usable()` — phải đỏ trước**

Thêm vào cùng file:

Thêm `AIMessage` và `_usable` vào khối import ở ĐẦU file:

```python
from langchain_core.messages import AIMessage
from src.llm.router import (ChainExhausted, RouteDecision, Router, SkippedLink,
                            _usable)
```

Rồi thêm vào cuối file:

```python
def test_usable_content_co_chu_thi_dung_duoc():
    assert _usable(AIMessage(content="intent: erp_write")) is True


def test_usable_content_rong_khong_tool_call_thi_khong_dung_duoc():
    assert _usable(AIMessage(content="")) is False
    assert _usable(AIMessage(content="   \n  ")) is False


def test_usable_tool_call_co_content_rong_VAN_dung_duoc():
    """Đo 2026-08-13: một lượt gọi tool THÀNH CÔNG cũng có content rỗng —
    cả gemini-3.5-flash-lite lẫn gemma-4-26b trả content='' + 1 tool_call cho
    câu hỏi tồn kho, finish_reason=STOP. Bỏ vế tool_calls sẽ làm hỏng
    erp_read, gather_erp, erp_write_planner và mọi node SOP."""
    msg = AIMessage(content="",
                    tool_calls=[{"name": "get_stock", "args": {}, "id": "c1"}])
    assert _usable(msg) is True
```

- [ ] **Bước 3: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router.py -m "not integration and not live" -q`
Expected: FAIL — `ImportError`/`AttributeError` cho `_usable`, `Verdict.EMPTY`, và `TypeError` cho tham số `skip`.

- [ ] **Bước 4: Thêm `Verdict.EMPTY`**

Trong `backend/src/llm/budget.py`, sửa enum:

```python
class Verdict(str, Enum):
    OK = "ok"
    RPM = "rpm_exhausted"
    TPM = "tpm_exhausted"
    RPD = "rpd_exhausted"
    COOLDOWN = "cooldown"
    # Mắt xích đã trả phản hồi rỗng TRONG CHÍNH lượt gọi này. Khác COOLDOWN ở
    # chỗ: không có tác dụng phụ sang request sau — model không ốm, nó chỉ
    # không trả lời nổi prompt này.
    EMPTY = "empty_response"
```

- [ ] **Bước 5: Thêm `_usable()` và hằng lý do vào `router.py`**

Đặt ngay sau hàm `_gop_content()` (tức trước `class Router`):

```python
EMPTY_RESPONSE_REASON = "phản hồi rỗng (không content, không tool_calls)"


def _usable(message) -> bool:
    """Phản hồi này có dùng được không.

    Luật CẤU TRÚC, cố ý KHÔNG so chuỗi `finish_reason`: Google trả
    "MAX_TOKENS", Groq trả "length", hoa/thường khác nhau — bắt theo chuỗi của
    nhà cung cấp là đúng lớp lỗi đã có tiền lệ trong repo (bài học đợt
    log_activity: phát hiện theo NƠI, không theo NỘI DUNG). "Rỗng và không gọi
    tool" là tính chất cấu trúc, không phụ thuộc nhà cung cấp.

    tool_calls PHẢI được tính là dùng được. Đo 2026-08-13: một lượt gọi tool
    THÀNH CÔNG cũng có content rỗng — cả gemini-3.5-flash-lite lẫn gemma-4-26b
    trả content='' + 1 tool_call, finish_reason=STOP. Bỏ vế này sẽ làm hỏng
    erp_read, gather_erp, erp_write_planner và mọi node SOP.

    Gọi hàm này TRÊN MESSAGE ĐÃ QUA _finish(): lúc đó content chắc chắn là str
    (đã qua _gop_content) và đã gỡ khối thought.
    """
    if getattr(message, "tool_calls", None):
        return True
    return bool((getattr(message, "content", "") or "").strip())
```

- [ ] **Bước 6: Thêm tham số `skip` cho `resolve()`**

Trong `backend/src/llm/router.py`, sửa `resolve()`. Chữ ký hiện tại:

```python
    def resolve(self, role: str, base_tokens: int,
                pin: str | None = None) -> RouteDecision:
```

Đổi thành (giữ NGUYÊN toàn bộ docstring cũ, chỉ nối thêm đoạn về `skip`):

```python
    def resolve(self, role: str, base_tokens: int,
                pin: str | None = None,
                skip: frozenset[str] = frozenset()) -> RouteDecision:
```

Nối vào cuối docstring cũ, TRƯỚC dấu `"""` đóng:

```
        skip: alias đã hỏng TRONG CHÍNH lượt gọi này (vd đã trả phản hồi
        rỗng). Cục bộ trong một lượt — khác cooldown, không có tác dụng phụ
        sang request sau. Không có nó, resolve() sẽ trả lại đúng mắt xích vừa
        rỗng và vòng lặp fallback thành vô nghĩa.
```

Trong thân hàm, sửa vòng `for`:

```python
        skipped: list[SkippedLink] = []
        for depth, spec in enumerate(chain_for(role)):
            if spec.alias in skip:
                skipped.append(SkippedLink(alias=spec.alias,
                                           verdict=Verdict.EMPTY))
                continue
            verdict = self._ledger.can_afford(spec, base_tokens)
            if verdict is Verdict.OK:
```

Phần còn lại của hàm giữ nguyên không sửa.

- [ ] **Bước 7: Chạy test, xác nhận XANH**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router.py -m "not integration and not live" -q`
Expected: PASS toàn bộ.

- [ ] **Bước 8: Chạy toàn bộ test tầng llm để bắt hồi quy**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm -m "not integration and not live" -q`
Expected: PASS. `resolve()` có tham số mới với giá trị mặc định nên mọi chỗ gọi cũ không đổi.

- [ ] **Bước 9: Commit**

```bash
git add backend/src/llm/budget.py backend/src/llm/router.py backend/tests/llm/test_router.py
git commit -m "feat(llm): resolve() bỏ qua được mắt xích đã hỏng trong lượt, thêm _usable()"
```

---

## Task 2: Vòng lặp `invoke`/`ainvoke` tụt mắt xích khi phản hồi rỗng

**Files:**
- Modify: `backend/src/llm/router.py` (`invoke`, `ainvoke`, thêm `_log_empty`)
- Modify: `backend/tests/llm/conftest.py` (thêm hai đồ giả)
- Test: `backend/tests/llm/test_router_invoke.py`

**Interfaces:**
- Consumes từ Task 1: `_usable(message) -> bool`, `EMPTY_RESPONSE_REASON`, `Router.resolve(..., skip=frozenset())`, `Verdict.EMPTY`
- Produces: không có (task cuối)

- [ ] **Bước 1: Thêm đồ giả vào `conftest.py`**

Thêm vào `backend/tests/llm/conftest.py`, ngay sau `fake_ai_google()`:

```python
def fake_ai_rong(*, prompt=361, completion=2045, total=2406,
                 finish_reason="MAX_TOKENS"):
    """Phản hồi RỖNG mà production thật sự nhận được.

    Số liệu chép từ phép đo sống 2026-08-13 với gemma-4-26b ở vai router:
    toàn bộ 2045 token đầu ra là reasoning, content rỗng, finish_reason
    MAX_TOKENS. Đây là hình dạng đã làm intent router phân loại nhầm thành
    'unknown'."""
    return AIMessage(
        content="",
        response_metadata={"finish_reason": finish_reason},
        usage_metadata={"input_tokens": prompt, "output_tokens": completion,
                        "total_tokens": total,
                        "output_token_details": {"reasoning": completion}})


def fake_ai_tool_call(name="get_stock", *, prompt=10, completion=20, total=30):
    """Lượt gọi tool THÀNH CÔNG — content RỖNG, có tool_calls.

    Đo 2026-08-13: cả gemini-3.5-flash-lite lẫn gemma-4-26b đều trả đúng hình
    dạng này (content='', 1 tool_call, finish_reason=STOP) cho câu hỏi tồn
    kho. Đây là ca dễ bị bản sửa phá nhất."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": "call_1"}],
        response_metadata={"token_usage": {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total}})
```

- [ ] **Bước 2: Viết test hành vi — phải đỏ trước**

Thêm vào `backend/tests/llm/test_router_invoke.py`. Sửa dòng import từ conftest để thêm hai đồ giả mới:

```python
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai, fake_ai_google, fake_ai_rong,
                                fake_ai_tool_call)
```

Rồi thêm vào cuối file:

```python
def test_phan_hoi_rong_thi_tut_mat_xich(clock):
    """Lỗi sống 2026-08-13: gemma-4-26b đốt hết 2045/2048 token vào suy luận
    nội bộ, phát ra 0 token hiển thị, HTTP 200. Trước bản sửa, chuỗi fallback
    không bao giờ chạy vì nó chỉ chạy khi có exception."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    got = r.invoke("router", MSGS)

    assert got.message.content == "intent: erp_write"
    assert got.decision.spec.alias == "groq-gpt-oss-20b"
    assert len(rong.calls) == 1        # gọi ĐÚNG một lần, không lặp lại
    assert len(tot.calls) == 1


def test_phan_hoi_rong_NHUNG_co_tool_call_thi_KHONG_tut(clock):
    """Ca dễ phá nhất: một lượt gọi tool THÀNH CÔNG cũng có content rỗng.
    Luật thiếu vế tool_calls sẽ làm hỏng erp_read, gather_erp,
    erp_write_planner và mọi node SOP."""
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI — không được gọi tới đây")])
    r = _router(clock, {"gemini-3.5-flash-lite": goi_tool,
                        "groq-llama-3.3-70b": khong_duoc_cham})

    got = r.invoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert got.message.tool_calls[0]["name"] == "get_stock"
    assert len(khong_duoc_cham.calls) == 0


def test_luot_bi_bo_van_duoc_ghi_so_ngan_sach(clock):
    """Token đã tiêu THẬT. Không ghi sổ thì sổ đếm thiếu và làm hỏng chính
    cơ chế chọn model."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = Router(ledger, client_factory=lambda spec: {
        "gemma-4-26b": rong, "groq-gpt-oss-20b": tot}[spec.alias])

    r.invoke("router", MSGS)

    assert store.usage_since(since=clock(),
                             alias="gemma-4-26b").total_tokens == 2406
    assert store.usage_since(since=clock(),
                             alias="groq-gpt-oss-20b").total_tokens == 800


def test_phan_hoi_rong_KHONG_dat_cooldown(clock):
    """Đây không phải 429 và model không ốm — nó chỉ không trả lời nổi prompt
    này. Lượt sau vẫn phải thử lại mắt xích 1."""
    rong = FakeChatClient([fake_ai_rong(), fake_ai("intent: erp_read")])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    r.invoke("router", MSGS)          # lượt 1: rỗng → tụt
    got = r.invoke("router", MSGS)    # lượt 2: mắt xích 1 PHẢI được thử lại

    assert len(rong.calls) == 2
    assert got.decision.spec.alias == "gemma-4-26b"
    assert got.message.content == "intent: erp_read"


def test_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem(clock):
    """Giữ hành vi hôm nay làm SÀN: bản sửa chỉ được cải thiện, không được đẻ
    ra đường crash mới. Không caller nào trong repo bắt ChainExhausted."""
    rong = FakeChatClient([fake_ai_rong()])
    r = _router(clock, {"gemini-3.1-flash-lite": rong,
                        "groq-llama-3.3-70b": rong})

    got = r.invoke("fusion", MSGS)    # chuỗi fusion chỉ có 2 mắt xích

    assert got.message.content == ""
    assert len(got.attempts) == 2
    assert all(a.error == EMPTY_RESPONSE_REASON for a in got.attempts)


def test_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan(clock):
    """Ghim là ghim. Toàn bộ eval dựa vào điều này — tụt lặng lẽ sẽ làm eval
    đo một model khác model được ghim."""
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: rong)

    got = r.invoke("router", MSGS, pin="gemma-4-26b")

    assert got.message.content == ""
    assert got.decision.spec.alias == "gemma-4-26b"
    assert len(rong.calls) == 1


async def test_ainvoke_cung_tut_khi_phan_hoi_rong(clock):
    """invoke và ainvoke là HAI thân hàm riêng — sửa một quên một là lỗi rất
    dễ xảy ra ở file này."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    got = await r.ainvoke("router", MSGS)

    assert got.decision.spec.alias == "groq-gpt-oss-20b"
    assert got.message.content == "intent: erp_write"


async def test_ainvoke_phan_hoi_rong_co_tool_call_thi_KHONG_tut(clock):
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI")])
    r = _router(clock, {"gemini-3.5-flash-lite": goi_tool,
                        "groq-llama-3.3-70b": khong_duoc_cham})

    got = await r.ainvoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert len(khong_duoc_cham.calls) == 0
```

Thêm `EMPTY_RESPONSE_REASON` vào dòng import từ `src.llm.router` ở đầu file:

```python
from src.llm.router import (COOLDOWN_RATE_LIMIT_S, EMPTY_RESPONSE_REASON,
                            ChainExhausted, RoutedChatModel, Router)
```

- [ ] **Bước 3: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router_invoke.py -m "not integration and not live" -q`
Expected: FAIL. Các test tụt mắt xích đỏ vì hiện `invoke` trả thẳng phản hồi rỗng của mắt xích 1.

- [ ] **Bước 4: Thêm `_log_empty()` vào `Router`**

Đặt ngay sau `_cooldown_for()` trong `backend/src/llm/router.py`:

```python
    def _log_empty(self, decision: RouteDecision, response) -> None:
        """Ghi lại một lượt bị bỏ vì rỗng.

        finish_reason CHỈ dùng để ghi log, KHÔNG dùng để quyết định (xem
        _usable). Đây là cách duy nhất để về sau biết tần suất thật trên lưu
        lượng thật, thay vì suy từ 36 lượt đo lúc chẩn đoán."""
        meta = getattr(response, "response_metadata", None) or {}
        logger.warning(
            "vai %s: %s trả phản hồi rỗng (finish_reason=%s) — bỏ lượt, "
            "thử mắt xích sau", decision.role, decision.spec.alias,
            meta.get("finish_reason"))
```

- [ ] **Bước 5: Sửa `invoke()`**

Thay TOÀN BỘ thân hàm `invoke()` (giữ nguyên chữ ký) bằng:

```python
    def invoke(self, role: str, messages: list, tools: list | None = None,
               pin: str | None = None, config=None,
               tool_kwargs: dict | None = None, **kwargs) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        empty_aliases: set[str] = set()
        last_empty: InvokeResult | None = None
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin,
                                    skip=frozenset(empty_aliases))
            try:
                response = self._client(decision.spec, tools, tool_kwargs).invoke(
                    messages, config=config, **kwargs)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            # _finish ghi sổ ngân sách — phải chạy KỂ CẢ khi lượt này bị bỏ,
            # vì token đã tiêu thật.
            result = self._finish(decision, response, attempts)
            if _usable(result.message):
                return result
            self._log_empty(decision, response)
            attempts.append(AttemptError(decision.spec.alias,
                                         EMPTY_RESPONSE_REASON))
            empty_aliases.add(decision.spec.alias)
            last_empty = result
        if last_empty is not None:
            # Cạn chuỗi vì rỗng → trả kết quả cuối, KHÔNG ném. Giữ hành vi
            # trước bản sửa làm sàn: không caller nào bắt ChainExhausted, nên
            # ném ở đây sẽ biến câu trả lời kém thành lỗi 500.
            return dataclasses.replace(last_empty, attempts=tuple(attempts))
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

Thêm `import dataclasses` vào khối import ở đầu file (sau `import asyncio`).

- [ ] **Bước 6: Sửa `ainvoke()`**

Thay TOÀN BỘ thân hàm `ainvoke()` (giữ nguyên chữ ký VÀ giữ nguyên khối chú thích dài về Blocker #2 ở đầu thân hàm) bằng:

```python
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        empty_aliases: set[str] = set()
        last_empty: InvokeResult | None = None
        for _ in range(self._max_attempts(role, pin)):
            decision = await asyncio.to_thread(
                self.resolve, role, base, pin=pin,
                skip=frozenset(empty_aliases))
            try:
                response = await self._client(
                    decision.spec, tools, tool_kwargs).ainvoke(
                        messages, config=config, **kwargs)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            result = await asyncio.to_thread(self._finish, decision, response,
                                             attempts)
            if _usable(result.message):
                return result
            self._log_empty(decision, response)
            attempts.append(AttemptError(decision.spec.alias,
                                         EMPTY_RESPONSE_REASON))
            empty_aliases.add(decision.spec.alias)
            last_empty = result
        if last_empty is not None:
            return dataclasses.replace(last_empty, attempts=tuple(attempts))
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

`asyncio.to_thread` truyền `skip` bằng keyword — `to_thread(func, /, *args, **kwargs)` chuyển tiếp kwargs bình thường.

- [ ] **Bước 7: Chạy test, xác nhận XANH**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_router_invoke.py -m "not integration and not live" -q`
Expected: PASS toàn bộ.

- [ ] **Bước 8: Chứng minh guard THẬT SỰ canh — phá có chủ đích**

Một test xanh là một tuyên bố, không phải bằng chứng. Làm hai phép thử phá, ghi kết quả vào report:

1. Trong `_usable`, xoá tạm hai dòng `if getattr(message, "tool_calls", ...)`.
   Chạy `pytest tests/llm/test_router_invoke.py -q`.
   **Phải ĐỎ** ở `test_phan_hoi_rong_NHUNG_co_tool_call_thi_KHONG_tut` và bản `ainvoke` của nó. Khôi phục.
2. Trong `invoke`, xoá tạm `skip=frozenset(empty_aliases)` khỏi lời gọi `resolve`.
   Chạy lại. **Phải ĐỎ** ở `test_phan_hoi_rong_thi_tut_mat_xich`. Khôi phục.

Nếu phép thử nào KHÔNG đỏ, test đó không đo cái nó tự nhận là đo — báo lại, đừng đi tiếp.

- [ ] **Bước 9: Chạy toàn bộ bộ test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS. Mốc hiện tại trên `main`: 1326 passed, 4 skipped, 46 deselected. Số passed sẽ tăng đúng bằng số test mới.

- [ ] **Bước 10: Commit**

```bash
git add backend/src/llm/router.py backend/tests/llm/conftest.py backend/tests/llm/test_router_invoke.py
git commit -m "fix(llm): phản hồi rỗng là lượt gọi hỏng, tụt xuống mắt xích sau"
```

---

## Nghiệm thu sống — controller làm, KHÔNG giao subagent

Subagent **không được** khởi động/dừng tiến trình, container, hay chạm Odoo. Phần này controller tự làm sau khi Task 2 xanh, **TRƯỚC khi merge**, trên worktree của nhánh, stack cũ dừng hẳn trước.

**Kịch bản chính** — vai **kế toán**, qua cổng HTTP thật:

| # | câu | kỳ vọng |
|---|---|---|
| 1 | `gửi email báo giao hàng cho phiếu WH/OUT/00138` | từ chối, nêu đúng **"bộ phận Kho"** |
| 2 | `nhờ gửi mail thông báo giao hàng cho khách của đơn S00119` | như trên |

Trước bản sửa cả hai rơi vào `respond_unknown` và trả lời hội thoại lan man.

**Đối chứng âm bắt buộc** — thiếu nó thì "chặn được nhiều hơn" không phân biệt được với "chặn hỏng":

| # | câu | kỳ vọng |
|---|---|---|
| 3 | kế toán: `gửi hóa đơn INV/... cho khách qua email` | vẫn soạn được, vẫn có cổng xác nhận |
| 4 | bất kỳ vai: `tồn kho sản phẩm ... còn bao nhiêu` | vẫn chạy — chứng minh đường gọi tool không hồi quy |

Kiểm log backend để xác nhận dòng `trả phản hồi rỗng ... bỏ lượt` có xuất hiện ở kịch bản 1–2 và **không** xuất hiện ở kịch bản 3–4.
