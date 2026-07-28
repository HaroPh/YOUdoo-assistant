# SP-1A — LLM Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng `backend/src/llm/` — tầng duy nhất biết đến nhà cung cấp LLM: chọn model theo vai trò dựa trên ngân sách hạn mức free-tier thật, tự tụt sang provider khác khi cạn hoặc lỗi, và chuẩn hoá đầu ra.

**Architecture:** Ba nhà cung cấp (Google AI Studio, Groq, OpenRouter) đều nói OpenAI-compatible nên `providers.py` chỉ là ba `ChatOpenAI` khác `base_url`. Trí tuệ nằm ở `catalog.py` (bảng model + hạn mức + miền lỗi thật) và `budget.py` (kế toán cửa sổ trượt trên Postgres, sau một interface để test không cần DB). `router.py` ghép hai thứ đó thành quyết định định tuyến, và bọc trong một `Runnable` của LangChain để code `agents/` port sau này không phải sửa chỗ gọi.

**Tech Stack:** Python 3.11+, `langchain-openai`, `langchain-core`, `psycopg` 3, `tiktoken`, `pytest`, `pytest-asyncio`.

**Spec:** [2026-07-28-sp1-foundation-design.md](../specs/2026-07-28-sp1-foundation-design.md) §1, §2, §7. Kế hoạch này KHÔNG bao gồm §3 (port), §4 (chat path), §5 (Langfuse), §8 (eval) — chúng thuộc kế hoạch B và C.

## Global Constraints

- **Python 3.11+**. Dùng `X | None` chứ không `Optional[X]`.
- **Không khoá API nào trong code.** Mọi khoá đọc từ biến môi trường: `GOOGLE_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`.
- **`src/llm/` không được import bất cứ thứ gì từ `src/agents/`, `src/erp_query/`, `src/rag/`.** Phụ thuộc một chiều (spec §1). Có test ép điều này.
- **Unit test không chạm mạng và không cần Postgres.** Test cần mạng phải đánh dấu `@pytest.mark.live`; test cần Postgres đánh dấu `@pytest.mark.integration`.
- **Bình luận trong code viết bằng tiếng Việt**, khớp lối viết của repo nguồn `D:\Project`. Tên định danh (biến, hàm, lớp) bằng tiếng Anh.
- **`total_tokens` là con số có thẩm quyền cho mọi phép kiểm token.** Không bao giờ dùng `prompt_tokens + completion_tokens` (spec §2 — Gemma đếm thiếu 7×).
- **Mọi giá trị hạn mức trong `catalog.py` phải khớp `docs/provider-quotas.md`.** Sửa một nơi thì sửa cả hai.
- **Năm quyết định phải có bình luận tại đúng điểm code** (spec Phụ lục B) — thiếu bình luận là plan chưa xong, không phải chuyện thẩm mỹ:

  | Quyết định | File |
  |---|---|
  | `google/*:free` bị loại vì `upstream=google` | `catalog.py` (Task 2) |
  | Budget fail-open, ngược `write_gate` fail-closed | `budget.py` (Task 5) |
  | Cửa sổ trượt 24h thay vì ngày lịch | `budget.py` (Task 5) |
  | `total_tokens` là con số có thẩm quyền, không cộng `p+c` | `budget.py` (Task 5), `migrations/001` (Task 6), `router._usage` (Task 9) |
  | Scrub `<thought>` vì Gemma không tắt được thinking | `providers.py` (Task 7) |

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/llm/catalog.py` | `ModelSpec`, `CATALOG`, `CHAINS`, các tập vai. Dữ liệu thuần, không hành vi |
| `backend/src/llm/store.py` | `UsageStore` protocol + `InMemoryUsageStore` + `PostgresUsageStore`. Chỉ lưu trữ, không chính sách |
| `backend/src/llm/budget.py` | `BudgetLedger` — chính sách hạn mức trên `UsageStore`. Không biết Postgres |
| `backend/src/llm/tokens.py` | `estimate_base_tokens()` — ước lượng token trung tính với provider |
| `backend/src/llm/providers.py` | `client_for()`, `strip_thought()`. Chỗ duy nhất biết `base_url` và tên biến môi trường |
| `backend/src/llm/router.py` | `Router.resolve()` / `.invoke()`, `RouteDecision`, `RoutedChatModel`, `make_llms()` |
| `backend/tests/llm/conftest.py` | Đồng hồ giả, kho giả, client giả |

Cùng khuôn `transport.py` / `gateway.py` của repo nguồn: **lưu trữ tách khỏi chính sách**, để chính sách test được mà không cần hạ tầng.

### Sai lệch có chủ đích so với spec

Spec §2 liệt `weight: str` trong `ModelSpec`. Kế hoạch này **bỏ trường đó**. Lý do: nó chỉ tồn tại để phục vụ bất biến "vai nặng cần tpm ≥ 12K", mà bất biến ấy diễn đạt trực tiếp bằng `HEAVY_ROLES` + `spec.tpm` thì gọn hơn và không đẻ ra khả năng gán sai (một model 120B mà phải gắn nhãn `"light"` vì vai dùng nó không nặng — vô nghĩa). Ràng buộc thuộc về **vai**, không thuộc về model.

Bù lại, thêm hai trường spec §2 (bản cập nhật) đã yêu cầu: `supports_tools` và `emits_thought_tags`.

---

## Interfaces — bảng tra nhanh

Mọi task đều tham chiếu bảng này. Người triển khai một task chỉ nhìn thấy task của mình, nên đây là chỗ họ học tên và kiểu của các task lân cận.

```python
# catalog.py
@dataclass(frozen=True)
class ModelSpec:
    alias: str; provider: str; model_id: str; upstream: str
    quota_scope: str            # "model" | "account"
    rpm: int | None; tpm: int | None; rpd: int | None
    token_multiplier: float
    max_output_tokens: int | None; timeout_s: int
    supports_tools: bool; emits_thought_tags: bool

CATALOG: dict[str, ModelSpec]
CHAINS: dict[str, tuple[str, ...]]
ROLES: frozenset[str]
HEAVY_ROLES: frozenset[str]     # {"read", "fusion", "synthesis"}
TOOL_ROLES: frozenset[str]      # {"read", "planner", "fusion", "synthesis"}
HEAVY_TPM_FLOOR: int            # 12_000
def spec_for(alias: str) -> ModelSpec
def chain_for(role: str) -> tuple[ModelSpec, ...]

# store.py
@dataclass(frozen=True)
class Usage:
    requests: int
    total_tokens: int

class UsageStore(Protocol):
    def record(self, ts, alias, provider, upstream,
               prompt_tokens, completion_tokens, total_tokens) -> None: ...
    def usage_since(self, *, since, alias=None, provider=None) -> Usage: ...

class InMemoryUsageStore: ...
class PostgresUsageStore: ...

# tokens.py
def estimate_base_tokens(messages: list, tools: list | None = None) -> int

# budget.py
class Verdict(str, Enum):
    OK = "ok"; RPM = "rpm_exhausted"; TPM = "tpm_exhausted"
    RPD = "rpd_exhausted"; COOLDOWN = "cooldown"

class BudgetLedger:
    def __init__(self, store: UsageStore, clock=None) -> None
    def can_afford(self, spec: ModelSpec, base_tokens: int) -> Verdict
    def record(self, spec: ModelSpec, prompt_tokens: int,
               completion_tokens: int, total_tokens: int) -> None
    def cooldown(self, spec: ModelSpec, seconds: float) -> None

# providers.py
def strip_thought(content: str | None) -> str
def client_for(spec: ModelSpec) -> ChatOpenAI | "ChatGoogleGenerativeAI"
# google → ChatGoogleGenerativeAI (spike Task 1: ChatOpenAI làm mất
# thought_signature, Google từ chối cứng lượt 2 với 400). groq/openrouter →
# ChatOpenAI. Cả hai lớp phơi ra .invoke()/.bind_tools() giống nhau nên
# router.py (Task 8-10) không cần biết sự khác biệt này.

# router.py
@dataclass(frozen=True)
class SkippedLink:
    alias: str
    verdict: Verdict

@dataclass(frozen=True)
class RouteDecision:
    role: str; spec: ModelSpec; fallback_depth: int
    skipped: tuple[SkippedLink, ...]; base_tokens: int

class ChainExhausted(RuntimeError): ...

class Router:
    def __init__(self, ledger: BudgetLedger, client_factory=client_for) -> None
    def resolve(self, role: str, base_tokens: int, pin: str | None = None) -> RouteDecision

class RoutedChatModel(Runnable):
    def __init__(self, router, role, tools=None, pin=None) -> None
    def bind_tools(self, tools, **kwargs) -> "RoutedChatModel"   # bản MỚI
    last_decision: RouteDecision | None

def build_router(store=None, clock=None) -> Router
def make_llms(router: Router,
              pins: dict[str, str] | None = None) -> dict[str, RoutedChatModel]
```

**Điểm dễ sai — thứ tự nhân hệ số token:** `estimate_base_tokens()` trả về con số **trung tính với provider**. Hệ số `token_multiplier` được nhân **bên trong `can_afford()`**, vì trước khi chọn được `spec` thì chưa biết nhân hệ số nào. Đừng nhân ở chỗ ước lượng.

---

### Task 1: Spike `thought_signature` + dựng khung backend

Spec §12 xếp đây là rủi ro **Cao** và bắt nó đứng đầu kế hoạch. Gemini 3 trả
`extra_content.google.thought_signature` **bên trong** `tool_calls`; nếu
`ChatOpenAI` vứt trường đó đi thì vòng lặp tool nhiều lượt của agent ERP có thể
hỏng. Phải biết câu trả lời **trước khi** xây `providers.py`, vì đường lui là
đổi client Google sang `langchain-google-genai` native.

Đây là task **spike**, không theo nhịp TDD: sản phẩm là một phát hiện được ghi
lại và một quyết định, không phải mã sản xuất.

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/src/__init__.py`, `backend/src/llm/__init__.py`
- Create: `backend/tests/__init__.py`, `backend/tests/llm/__init__.py`
- Create: `backend/spikes/spike_thought_signature.py`
- Create: `docs/spikes/2026-07-28-thought-signature.md`
- Create: `.env.example`
- Create (không commit): `.env`

**Interfaces:**
- Consumes: không có (task đầu tiên)
- Produces: khung thư mục Python; **quyết định** ghi trong
  `docs/spikes/2026-07-28-thought-signature.md` về việc `providers.py` (Task 7)
  dùng `ChatOpenAI` cho Google hay `ChatGoogleGenerativeAI`

- [ ] **Bước 1: Dựng khung thư mục và dependency**

`backend/requirements.txt`:

```
langchain-core==1.4.8
langchain-openai==1.3.3
langchain==1.2.18
psycopg[binary]==3.3.4
tiktoken==0.13.0
python-dotenv==1.2.2
pytest==9.1.1
pytest-asyncio==1.4.0
```

Pin đúng phiên bản repo nguồn `D:\Project/requirements.txt` đang dùng cho các
gói dùng chung — kế hoạch B sẽ port code chạy trên chính các phiên bản này, nên
lệch phiên bản ở đây là tự tạo việc cho mình.

`backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
markers =
    live: cần mạng và API key thật (không chạy trong CI thường)
    integration: cần Postgres đang chạy
```

Tạo các file `__init__.py` rỗng ở `src/`, `src/llm/`, `tests/`, `tests/llm/`.

- [ ] **Bước 2: Tạo `.env.example` và `.env`**

`.env.example` (commit file này):

```bash
# ─── LLM providers (SP-1) ────────────────────────────────────────────────────
GOOGLE_API_KEY=thay_bang_key_that
GROQ_API_KEY=thay_bang_key_that
OPENROUTER_API_KEY=thay_bang_key_that

# ─── Postgres (sổ ngân sách + checkpointer LangGraph) ────────────────────────
DATABASE_URL=postgresql://admin:thay_bang_mat_khau@localhost:5433/ai_assistant

# ─── Langfuse (kế hoạch C) ───────────────────────────────────────────────────
LANGFUSE_HOST=http://localhost:3001
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```

Rồi tạo `.env` (đã có trong `.gitignore`) với giá trị thật lấy từ `models.csv`
ở gốc repo. Cột `key` của `models.csv`: dòng `Gemini` → `GOOGLE_API_KEY`, dòng
`Groqcloud` → `GROQ_API_KEY`, dòng `openrouter` → `OPENROUTER_API_KEY`.

- [ ] **Bước 3: Viết script spike**

`backend/spikes/spike_thought_signature.py`:

```python
"""Spike: ChatOpenAI có giữ được thought_signature của Gemini 3 qua vòng lặp
tool 2 lượt không?

Bối cảnh: gọi thô bằng curl ngày 2026-07-28 cho thấy Google trả
extra_content.google.thought_signature BÊN TRONG tool_calls. Trường này không
thuộc schema OpenAI, nên ChatOpenAI có thể vứt nó đi. Agent ERP sống bằng vòng
lặp tool nhiều lượt (spec §12).

Chạy:  python -m spikes.spike_thought_signature
"""
import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


@tool
def get_stock(product: str) -> str:
    """Tra tồn kho theo tên sản phẩm."""
    return json.dumps({"product": product, "on_hand": 42, "uom": "cái"},
                      ensure_ascii=False)


@tool
def get_price(product: str) -> str:
    """Tra đơn giá bán theo tên sản phẩm."""
    return json.dumps({"product": product, "price": 1500000, "currency": "VND"},
                      ensure_ascii=False)


def main() -> None:
    llm = ChatOpenAI(model="gemini-3.5-flash-lite", base_url=GOOGLE_BASE,
                     api_key=os.environ["GOOGLE_API_KEY"], temperature=0,
                     timeout=60)
    bound = llm.bind_tools([get_stock, get_price])
    tools = {"get_stock": get_stock, "get_price": get_price}

    messages = [HumanMessage(
        "Sản phẩm ABC còn bao nhiêu hàng, và đơn giá bao nhiêu?")]

    for turn in range(1, 4):
        ai = bound.invoke(messages)
        messages.append(ai)
        print(f"\n─── Lượt {turn} ───")
        print("  tool_calls        :", [tc["name"] for tc in ai.tool_calls])
        print("  additional_kwargs :", json.dumps(
            ai.additional_kwargs, ensure_ascii=False, default=str)[:400])
        print("  response_metadata :", json.dumps(
            ai.response_metadata, ensure_ascii=False, default=str)[:400])
        blob = json.dumps({"ak": ai.additional_kwargs,
                           "rm": ai.response_metadata,
                           "tc": ai.tool_calls}, default=str)
        print("  CÓ thought_signature:", "thought_signature" in blob)

        if not ai.tool_calls:
            print("\n─── Câu trả lời cuối ───")
            print(ai.content)
            return
        for tc in ai.tool_calls:
            out = tools[tc["name"]].invoke(tc["args"])
            messages.append(ToolMessage(content=out, tool_call_id=tc["id"]))

    print("\nKHÔNG hội tụ sau 3 lượt — vòng lặp tool có vấn đề.")


if __name__ == "__main__":
    main()
```

- [ ] **Bước 4: Chạy spike**

```bash
cd backend && python -m spikes.spike_thought_signature
```

Kết quả cần quan sát, ghi lại cả ba:
1. Vòng lặp **có hội tụ** không (đến lượt có `tool_calls` rỗng và có câu trả
   lời tiếng Việt nhắc cả tồn kho lẫn giá)?
2. `thought_signature` **có xuất hiện** ở đâu đó trong `additional_kwargs` /
   `response_metadata` / `tool_calls` không?
3. Có lỗi `400` nào từ Google than phiền về lượt thiếu chữ ký không?

- [ ] **Bước 5: Ghi phát hiện và quyết định**

Tạo `docs/spikes/2026-07-28-thought-signature.md` với đúng bốn mục: **Câu hỏi**,
**Cách đo** (lệnh chạy), **Kết quả quan sát được** (dán output thật, không diễn
giải), **Quyết định**.

Quyết định theo đúng luật này:

| Quan sát | Quyết định cho Task 7 |
|---|---|
| Vòng lặp hội tụ, câu trả lời cuối đúng | Dùng `ChatOpenAI` cho cả 3 provider. Ghi rằng `thought_signature` bị mất **không** gây hỏng trong phạm vi đã đo |
| Vòng lặp không hội tụ, HOẶC Google trả lỗi liên quan chữ ký | Google đổi sang `langchain-google-genai` / `ChatGoogleGenerativeAI`; thêm `langchain-google-genai` vào `requirements.txt`. Task 7 phải xử `client_for()` phân nhánh theo `spec.provider` |

Nếu rơi vào hàng thứ hai, **cập nhật spec §2** (mục `providers.py`) rồi mới đi
tiếp — spec là bản ghi thiết kế, không được để nó nói sai.

- [ ] **Bước 6: Commit**

```bash
git add backend/requirements.txt backend/pytest.ini backend/src backend/tests \
        backend/spikes .env.example docs/spikes/
git commit -m "spike: xác định ChatOpenAI có giữ thought_signature của Gemini 3 không

Dựng khung backend + chạy vòng lặp tool 2 lượt qua endpoint OpenAI-compat của
Google. Phát hiện và quyết định ghi ở docs/spikes/2026-07-28-thought-signature.md;
quyết định này chi phối client Google trong Task 7."
```

---

### Task 2: `catalog.py` — bảng model và bốn bất biến

Bốn bất biến là phần đáng giá nhất của task này. Chúng biến các phát hiện đo
được ngày 2026-07-28 thành thứ **máy kiểm tra được**, thay vì lời dặn trong tài
liệu mà phiên sau sẽ đọc lướt qua.

**Files:**
- Create: `backend/src/llm/catalog.py`
- Test: `backend/tests/llm/test_catalog.py`

**Interfaces:**
- Consumes: khung thư mục từ Task 1
- Produces: `ModelSpec`, `CATALOG`, `CHAINS`, `ROLES`, `HEAVY_ROLES`,
  `TOOL_ROLES`, `HEAVY_TPM_FLOOR`, `spec_for(alias)`, `chain_for(role)` —
  mọi task sau đều dùng

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_catalog.py`:

```python
import pytest

from src.llm.catalog import (CATALOG, CHAINS, HEAVY_ROLES, HEAVY_TPM_FLOOR,
                             ROLES, TOOL_ROLES, chain_for, spec_for)


def test_moi_alias_trong_chain_deu_ton_tai_trong_catalog():
    """Bất biến #2 — chuỗi trỏ tới alias lạ là lỗi cấu hình, phải chết sớm."""
    for role, aliases in CHAINS.items():
        for alias in aliases:
            assert alias in CATALOG, f"chuỗi {role!r} trỏ tới alias lạ: {alias!r}"


def test_khong_hai_mat_xich_nao_trong_mot_chuoi_chung_upstream():
    """Bất biến #1 — fallback phải vượt qua ranh giới miền lỗi thật.

    Đo 2026-07-28: google/gemma-4-31b-it:free trên OpenRouter trả 429 kèm
    provider_name "Google AI Studio" — nó proxy ngược về chính Google. Rơi từ
    Gemini xuống đó là rơi vào lại chỗ vừa ngã.
    """
    for role, aliases in CHAINS.items():
        upstreams = [CATALOG[a].upstream for a in aliases]
        assert len(upstreams) == len(set(upstreams)), (
            f"chuỗi {role!r} có hai mắt xích chung upstream: {upstreams}")


def test_vai_nang_chi_dung_model_du_tpm():
    """Bất biến #3 — một lượt synthesis có RAG tốn ~3–4K token input."""
    for role in HEAVY_ROLES:
        for spec in chain_for(role):
            assert spec.tpm is None or spec.tpm >= HEAVY_TPM_FLOOR, (
                f"{spec.alias!r} có tpm={spec.tpm} < {HEAVY_TPM_FLOOR}, "
                f"không gánh nổi vai nặng {role!r}")


def test_vai_can_tool_chi_dung_model_ho_tro_tool():
    """Bất biến #4 — vai gọi tool mà trúng model không tool-call thì hỏng câm."""
    for role in TOOL_ROLES:
        for spec in chain_for(role):
            assert spec.supports_tools, (
                f"{spec.alias!r} không hỗ trợ tool nhưng nằm trong chuỗi "
                f"của vai {role!r}")


def test_moi_vai_deu_co_chuoi_va_khong_co_chuoi_thua():
    assert set(CHAINS) == set(ROLES)


def test_khong_co_model_openrouter_nao_co_upstream_google():
    """Chốt cứng phát hiện 2026-07-28 ở tầng dữ liệu, không chỉ ở chuỗi."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.upstream != "google", (
                f"{spec.alias!r} proxy về Google — không được vào catalog")


def test_quota_scope_chi_nhan_hai_gia_tri_hop_le():
    for spec in CATALOG.values():
        assert spec.quota_scope in ("model", "account")


def test_openrouter_dung_quota_scope_account():
    """Hạn mức free của OpenRouter tính theo TÀI KHOẢN, dùng chung mọi model."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.quota_scope == "account"


def test_alias_khop_voi_khoa_trong_catalog():
    for key, spec in CATALOG.items():
        assert spec.alias == key


def test_spec_for_nem_loi_voi_alias_la():
    with pytest.raises(KeyError):
        spec_for("model-khong-ton-tai")


def test_chain_for_nem_loi_voi_vai_la():
    with pytest.raises(KeyError):
        chain_for("vai-khong-ton-tai")


def test_chain_for_tra_ve_dung_thu_tu():
    specs = chain_for("read")
    assert [s.alias for s in specs] == list(CHAINS["read"])
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_catalog.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.catalog'`

- [ ] **Bước 3: Viết `catalog.py`**

`backend/src/llm/catalog.py`:

```python
"""Bảng model — nguồn sự thật duy nhất cho tầng LLM (spec SP-1 §2).

Mọi con số hạn mức ở đây phải khớp docs/provider-quotas.md. Sửa một nơi thì
sửa cả hai; test contract (Task 11) đối chiếu model_id với /models thật.

KHÔNG có khoá API nào trong file này.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str            # google | groq | openrouter
    model_id: str            # ID gốc phía provider
    upstream: str            # MIỀN LỖI THẬT — xem CHÚ THÍCH OPENROUTER bên dưới
    quota_scope: str         # "model" (Google, Groq) | "account" (OpenRouter)
    rpm: int | None
    tpm: int | None          # None = không có trần token công bố
    rpd: int | None
    token_multiplier: float  # hiệu chỉnh ước lượng token theo provider
    max_output_tokens: int | None
    timeout_s: int
    supports_tools: bool
    emits_thought_tags: bool  # họ Gemma nhả <thought> vào content


# Ngưỡng cho bất biến #3. Chọn theo số đo: một lượt synthesis có RAG tốn ~3–4K
# token input, và 12K là mức của llama-3.3-70b — mắt xích Groq duy nhất gánh
# nổi vai nặng. gpt-oss-* ở 8K bị loại khỏi vai nặng đúng bởi ngưỡng này.
HEAVY_TPM_FLOOR = 12_000

ROLES = frozenset({"router", "chitchat", "evaluator", "planner",
                   "read", "fusion", "synthesis"})
HEAVY_ROLES = frozenset({"read", "fusion", "synthesis"})
TOOL_ROLES = frozenset({"read", "planner", "fusion", "synthesis"})

# ─── CHÚ THÍCH OPENROUTER (quyết định 2026-07-28, KHÔNG lật lại) ─────────────
# google/gemma-4-31b-it:free CỐ Ý không có mặt trong catalog. Đo được: nó trả
# 429 kèm provider_name "Google AI Studio" — OpenRouter proxy ngược về chính
# Google, dùng chung hồ hạn mức. Xếp nó sau Gemini trong một chuỗi fallback là
# tự lừa mình. Chỉ model OpenRouter có upstream THẬT SỰ khác mới được vào:
# ling-3.0-flash → Novita, nemotron-3-super → Nvidia (cả hai đã xác nhận
# tool-call bình thường).
# ────────────────────────────────────────────────────────────────────────────

CATALOG: dict[str, ModelSpec] = {
    # ─── Google AI Studio ───────────────────────────────────────────────────
    "gemini-3.5-flash-lite": ModelSpec(
        alias="gemini-3.5-flash-lite", provider="google",
        model_id="gemini-3.5-flash-lite", upstream="google",
        quota_scope="model", rpm=15, tpm=250_000, rpd=500,
        token_multiplier=1.0, max_output_tokens=8192, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    "gemini-3.1-flash-lite": ModelSpec(
        alias="gemini-3.1-flash-lite", provider="google",
        model_id="gemini-3.1-flash-lite", upstream="google",
        quota_scope="model", rpm=15, tpm=250_000, rpd=500,
        token_multiplier=1.0, max_output_tokens=8192, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    # Gemma: RPD khổng lồ (14.4K) nhưng TPM thấp (16K) và KHÔNG tắt được
    # thinking (reasoning_effort → 400 "Thinking budget is not supported").
    # 26b và 31b có HAI ví hạn mức riêng biệt — vai router và chitchat cố ý
    # tách ra hai model để tiêu hai ví thay vì một.
    "gemma-4-26b": ModelSpec(
        alias="gemma-4-26b", provider="google",
        model_id="gemma-4-26b-a4b-it", upstream="google",
        quota_scope="model", rpm=30, tpm=16_000, rpd=14_400,
        token_multiplier=1.0, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=True),
    "gemma-4-31b": ModelSpec(
        alias="gemma-4-31b", provider="google",
        model_id="gemma-4-31b-it", upstream="google",
        quota_scope="model", rpm=30, tpm=16_000, rpd=14_400,
        token_multiplier=1.0, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=True),

    # ─── Groq ───────────────────────────────────────────────────────────────
    # token_multiplier=2.3: đo được Groq tính 133 prompt_tokens cho payload mà
    # Google tính 57. Với trần 8K TPM, ước lượng lệch 2.3× là gọi thẳng vào 429.
    "groq-gpt-oss-20b": ModelSpec(
        alias="groq-gpt-oss-20b", provider="groq",
        model_id="openai/gpt-oss-20b", upstream="groq",
        quota_scope="model", rpm=30, tpm=8_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=2048, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),
    "groq-gpt-oss-120b": ModelSpec(
        alias="groq-gpt-oss-120b", provider="groq",
        model_id="openai/gpt-oss-120b", upstream="groq",
        quota_scope="model", rpm=30, tpm=8_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=4096, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),
    "groq-llama-3.3-70b": ModelSpec(
        alias="groq-llama-3.3-70b", provider="groq",
        model_id="llama-3.3-70b-versatile", upstream="groq",
        quota_scope="model", rpm=30, tpm=12_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=4096, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),

    # ─── OpenRouter (khan hiếm — ~50 lượt/ngày CHUNG cho mọi model free) ────
    "or-ling": ModelSpec(
        alias="or-ling", provider="openrouter",
        model_id="inclusionai/ling-3.0-flash:free", upstream="novita",
        quota_scope="account", rpm=None, tpm=None, rpd=50,
        token_multiplier=1.5, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    "or-nemotron": ModelSpec(
        alias="or-nemotron", provider="openrouter",
        model_id="nvidia/nemotron-3-super-120b-a12b:free", upstream="nvidia",
        quota_scope="account", rpm=None, tpm=None, rpd=50,
        token_multiplier=1.5, max_output_tokens=4096, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
}

# Gán provider theo TRỌNG LƯỢNG TOKEN của vai, không theo chuỗi "primary →
# fallback" chung chung. Ràng buộc thật của Groq là TPM chứ không phải RPM:
# ở 8K TPM chỉ chạy được ~2 request/phút với ngữ cảnh RAG, trong khi RPM 30
# còn chưa dùng tới 1/15. Ai thiết kế theo RPM sẽ bị TPM đánh úp.
CHAINS: dict[str, tuple[str, ...]] = {
    "router":    ("gemma-4-26b", "groq-gpt-oss-20b", "or-ling"),
    "chitchat":  ("gemma-4-31b", "groq-gpt-oss-20b"),
    "evaluator": ("groq-gpt-oss-20b", "gemma-4-26b"),
    "planner":   ("gemini-3.5-flash-lite", "groq-gpt-oss-120b", "or-nemotron"),
    "read":      ("gemini-3.5-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
    "fusion":    ("gemini-3.1-flash-lite", "groq-llama-3.3-70b"),
    "synthesis": ("gemini-3.1-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
}


def spec_for(alias: str) -> ModelSpec:
    """Ném KeyError nếu alias lạ — cấu hình sai phải chết sớm, không đoán."""
    return CATALOG[alias]


def chain_for(role: str) -> tuple[ModelSpec, ...]:
    return tuple(CATALOG[a] for a in CHAINS[role])
```

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_catalog.py -v`
Kỳ vọng: 12 test PASS

Nếu bất biến nào đỏ thì **sửa `CHAINS`, đừng nới lỏng test** — mỗi bất biến đại
diện cho một cách hỏng đã quan sát được ngoài đời.

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/catalog.py backend/tests/llm/test_catalog.py
git commit -m "feat(llm): catalog model + 4 bất biến chuỗi fallback

Bảng model cho 3 provider với hạn mức đo được 2026-07-28. Bốn bất biến ép bằng
test trên chính CATALOG/CHAINS: không trùng upstream trong một chuỗi, alias tồn
tại, vai nặng đủ TPM, vai gọi tool chỉ dùng model tool-capable.

google/*:free của OpenRouter cố ý bị loại — đo được nó proxy ngược về Google."
```

---

### Task 3: `store.py` — `UsageStore` protocol + `InMemoryUsageStore`

Tách lưu trữ khỏi chính sách, đúng khuôn `transport.py` / `gateway.py` của repo
nguồn: `transport` mang dây nối, `gateway` mang chính sách. Ở đây `store` mang
dây nối tới Postgres còn `budget` (Task 5) mang chính sách hạn mức. Nhờ tách
vậy, toàn bộ logic ngân sách test được bằng kho trong bộ nhớ, không cần DB.

Postgres đến ở Task 6. Task này chỉ dựng hợp đồng và bản trong bộ nhớ.

**Files:**
- Create: `backend/src/llm/store.py`
- Test: `backend/tests/llm/test_store.py`

**Interfaces:**
- Consumes: không có (độc lập với `catalog.py`)
- Produces: `Usage`, `UsageStore` (Protocol), `InMemoryUsageStore` — Task 5
  dùng làm chỗ dựa cho `BudgetLedger`, Task 6 thêm bản Postgres

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_store.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from src.llm.store import InMemoryUsageStore, Usage

T0 = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def _record(store, ts, alias="a1", provider="p1", upstream="u1",
            prompt=10, completion=20, total=30):
    store.record(ts=ts, alias=alias, provider=provider, upstream=upstream,
                 prompt_tokens=prompt, completion_tokens=completion,
                 total_tokens=total)


def test_kho_rong_tra_ve_khong():
    store = InMemoryUsageStore()
    assert store.usage_since(since=T0, alias="a1") == Usage(requests=0,
                                                            total_tokens=0)


def test_dem_dung_so_luot_va_tong_token_theo_alias():
    store = InMemoryUsageStore()
    _record(store, T0, total=30)
    _record(store, T0 + timedelta(seconds=1), total=70)
    assert store.usage_since(since=T0 - timedelta(minutes=1), alias="a1") == \
        Usage(requests=2, total_tokens=100)


def test_loc_theo_alias_bo_qua_alias_khac():
    store = InMemoryUsageStore()
    _record(store, T0, alias="a1", total=30)
    _record(store, T0, alias="a2", total=500)
    got = store.usage_since(since=T0 - timedelta(minutes=1), alias="a1")
    assert got == Usage(requests=1, total_tokens=30)


def test_loc_theo_provider_gop_moi_alias_cua_provider_do():
    """OpenRouter dùng quota_scope="account" — mọi model free chung một ví."""
    store = InMemoryUsageStore()
    _record(store, T0, alias="or-ling", provider="openrouter", total=30)
    _record(store, T0, alias="or-nemotron", provider="openrouter", total=70)
    _record(store, T0, alias="gemma-4-26b", provider="google", total=999)
    got = store.usage_since(since=T0 - timedelta(minutes=1),
                            provider="openrouter")
    assert got == Usage(requests=2, total_tokens=100)


def test_moc_since_loai_ban_ghi_cu_hon():
    store = InMemoryUsageStore()
    _record(store, T0 - timedelta(hours=25), total=999)   # ngoài cửa sổ 24h
    _record(store, T0 - timedelta(hours=1), total=50)     # trong cửa sổ
    got = store.usage_since(since=T0 - timedelta(hours=24), alias="a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_moc_since_la_bien_dong_ban_ghi_dung_bang_since_duoc_tinh():
    store = InMemoryUsageStore()
    _record(store, T0, total=50)
    got = store.usage_since(since=T0, alias="a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_tong_dung_total_tokens_khong_phai_prompt_cong_completion():
    """Gemma trả p=11, c=36 nhưng total=337 (~290 token thinking vô hình).
    Cộng p+c đếm thiếu 7 lần — sổ báo còn hạn mức trong khi ví đã cạn."""
    store = InMemoryUsageStore()
    _record(store, T0, prompt=11, completion=36, total=337)
    got = store.usage_since(since=T0 - timedelta(minutes=1), alias="a1")
    assert got.total_tokens == 337


def test_phai_dua_dung_mot_trong_hai_alias_hoac_provider():
    store = InMemoryUsageStore()
    with pytest.raises(ValueError):
        store.usage_since(since=T0)
    with pytest.raises(ValueError):
        store.usage_since(since=T0, alias="a1", provider="p1")
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_store.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.store'`

- [ ] **Bước 3: Viết `store.py`**

`backend/src/llm/store.py`:

```python
"""Lưu trữ lượt gọi LLM — chỉ dây nối, KHÔNG chính sách (spec SP-1 §2).

Cùng khuôn transport.py / gateway.py của repo nguồn: chính sách hạn mức nằm ở
budget.py và không được biết Postgres tồn tại. Nhờ vậy toàn bộ logic ngân sách
test được bằng InMemoryUsageStore, không cần DB.

Bản Postgres nằm ở cùng file này (Task 6) — giữ hai implementation cạnh nhau
để hợp đồng giữa chúng nhìn thấy được trong một màn hình.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Usage:
    requests: int
    total_tokens: int


def _check_exactly_one(alias: str | None, provider: str | None) -> None:
    """Gộp theo alias (quota_scope="model") HOẶC theo provider (="account").
    Đưa cả hai, hoặc không đưa gì, đều là lỗi gọi — không đoán ý."""
    if (alias is None) == (provider is None):
        raise ValueError("phải đưa đúng một trong hai: alias hoặc provider")


class UsageStore(Protocol):
    def record(self, *, ts: datetime, alias: str, provider: str, upstream: str,
               prompt_tokens: int, completion_tokens: int,
               total_tokens: int) -> None: ...

    def usage_since(self, *, since: datetime, alias: str | None = None,
                    provider: str | None = None) -> Usage: ...


class InMemoryUsageStore:
    """Bản cho unit test và cho chế độ degrade khi Postgres không có.

    Không tự dọn bản ghi cũ: vòng đời của nó là một tiến trình test hoặc một
    lần chạy ngắn, nên tăng trưởng bộ nhớ không phải vấn đề. PostgresUsageStore
    mới là chỗ cần nghĩ tới chuyện đó.
    """

    def __init__(self) -> None:
        self._rows: list[tuple] = []   # (ts, alias, provider, total_tokens)

    def record(self, *, ts: datetime, alias: str, provider: str, upstream: str,
               prompt_tokens: int, completion_tokens: int,
               total_tokens: int) -> None:
        # upstream/prompt/completion không dùng cho phép cộng nào ở đây; giữ
        # trong chữ ký để hợp đồng khớp bản Postgres, nơi chúng được lưu để
        # chẩn đoán (so est_tokens với actual, xem span Langfuse ở kế hoạch C).
        self._rows.append((ts, alias, provider, total_tokens))

    def usage_since(self, *, since: datetime, alias: str | None = None,
                    provider: str | None = None) -> Usage:
        _check_exactly_one(alias, provider)
        idx = 1 if alias is not None else 2
        want = alias if alias is not None else provider
        hits = [r for r in self._rows if r[0] >= since and r[idx] == want]
        return Usage(requests=len(hits),
                     total_tokens=sum(r[3] for r in hits))
```

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_store.py -v`
Kỳ vọng: 8 test PASS

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/store.py backend/tests/llm/test_store.py
git commit -m "feat(llm): UsageStore protocol + bản trong bộ nhớ

Tách lưu trữ khỏi chính sách hạn mức, đúng khuôn transport/gateway của repo
nguồn — budget.py sẽ không biết Postgres tồn tại, nên test được không cần DB.

usage_since() gộp theo alias (quota_scope=model) hoặc theo provider
(quota_scope=account, cho OpenRouter dùng chung ví)."
```

---

### Task 4: `tokens.py` — ước lượng token trung tính với provider

Bộ kế toán cần biết một lượt gọi **sắp** tốn bao nhiêu token, trước khi gọi.
`tiktoken` cho con số gần đúng; hệ số riêng từng provider được nhân **sau**,
bên trong `can_afford()` (Task 5), vì lúc ước lượng thì chưa chọn được model.

Nhớ tính cả JSON schema của tool: agent ERP bind hàng chục tool, và phần schema
đó thường **lớn hơn** cả câu hỏi người dùng. Bỏ qua nó là ước lượng thiếu ở
đúng chỗ đau nhất — vai `read` với 8K TPM của Groq.

**Files:**
- Create: `backend/src/llm/tokens.py`
- Test: `backend/tests/llm/test_tokens.py`

**Interfaces:**
- Consumes: không có
- Produces: `estimate_base_tokens(messages, tools=None) -> int` — Task 8 gọi
  trước khi `Router.resolve()`

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_tokens.py`:

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm.tokens import estimate_base_tokens


def test_khong_co_gi_thi_bang_khong():
    assert estimate_base_tokens([]) == 0


def test_tin_nhan_dai_hon_thi_uoc_luong_lon_hon():
    ngan = estimate_base_tokens([HumanMessage("Xin chào")])
    dai = estimate_base_tokens([HumanMessage("Xin chào " * 200)])
    assert dai > ngan > 0


def test_cong_don_qua_nhieu_tin_nhan():
    mot = estimate_base_tokens([HumanMessage("Tồn kho sản phẩm ABC?")])
    ba = estimate_base_tokens([
        SystemMessage("Bạn là trợ lý ERP."),
        HumanMessage("Tồn kho sản phẩm ABC?"),
        AIMessage("Sản phẩm ABC còn 42 cái."),
    ])
    assert ba > mot


def test_schema_tool_duoc_tinh_vao():
    """Agent ERP bind hàng chục tool — phần schema thường lớn hơn câu hỏi."""
    msgs = [HumanMessage("Tồn kho ABC?")]
    tools = [{
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Tra tồn kho theo tên sản phẩm trong hệ thống Odoo",
            "parameters": {
                "type": "object",
                "properties": {"product": {"type": "string"}},
                "required": ["product"],
            },
        },
    }]
    assert estimate_base_tokens(msgs, tools) > estimate_base_tokens(msgs)


def test_chap_nhan_dict_kieu_openai_lan_message_cua_langchain():
    """Đường eval dựng message dạng dict thô; graph dùng message LangChain."""
    dang_dict = estimate_base_tokens([{"role": "user", "content": "Tồn kho ABC?"}])
    dang_obj = estimate_base_tokens([HumanMessage("Tồn kho ABC?")])
    assert dang_dict > 0 and dang_obj > 0
    assert abs(dang_dict - dang_obj) <= 5


def test_noi_dung_rong_khong_lam_no_vo():
    assert estimate_base_tokens([HumanMessage("")]) >= 0
    assert estimate_base_tokens([{"role": "user", "content": None}]) >= 0


def test_ket_qua_la_so_nguyen_khong_am():
    got = estimate_base_tokens([HumanMessage("Tồn kho ABC?")])
    assert isinstance(got, int) and got >= 0
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_tokens.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.tokens'`

- [ ] **Bước 3: Viết `tokens.py`**

`backend/src/llm/tokens.py`:

```python
"""Ước lượng token TRUNG TÍNH với provider (spec SP-1 §2).

Đây là ước lượng, không phải phép đo. Ba nhà cung cấp tokenize khác nhau —
đo được 2026-07-28: cùng một payload, Groq tính 133 prompt_tokens còn Google
tính 57. Chênh lệch đó được bù bằng ModelSpec.token_multiplier, nhân BÊN TRONG
BudgetLedger.can_afford(), KHÔNG nhân ở đây: lúc ước lượng thì chưa chọn được
model nên chưa biết nhân hệ số nào.

cl100k_base chỉ là thước đo thay thế cho tokenizer thật của từng nhà. Sai số
được khép lại bằng cách BudgetLedger.record() ghi cả ước lượng lẫn số thật từ
trường usage của response (span Langfuse ở kế hoạch C hiển thị cả hai).
"""
import json

import tiktoken

_ENCODING = "cl100k_base"
_enc = None


def _encoder():
    # Nạp lười: tiktoken tải bảng mã ở lần dùng đầu, không nên trả giá đó lúc
    # import module.
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(_ENCODING)
    return _enc


def _text_of(message) -> str:
    """Rút phần chữ từ message LangChain HOẶC dict kiểu OpenAI."""
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # Nội dung nhiều phần (multimodal): chỉ cộng phần chữ. Phần ảnh không đo
    # được bằng tokenizer chữ, và SP-1 không có đường nào sinh ra chúng.
    parts = []
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
        elif isinstance(part, str):
            parts.append(part)
    return " ".join(parts)


def estimate_base_tokens(messages: list, tools: list | None = None) -> int:
    """Ước lượng token đầu vào cho một lượt gọi, chưa nhân hệ số provider."""
    if not messages and not tools:
        return 0
    enc = _encoder()
    total = sum(len(enc.encode(_text_of(m))) for m in messages)
    if tools:
        # Schema tool đi vào prompt dưới dạng JSON. Với agent ERP bind hàng
        # chục tool, phần này thường lớn hơn cả câu hỏi người dùng — bỏ qua nó
        # là ước lượng thiếu ở đúng chỗ đau nhất (Groq 8K TPM).
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(enc.encode(blob))
    return total
```

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_tokens.py -v`
Kỳ vọng: 7 test PASS

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/tokens.py backend/tests/llm/test_tokens.py
git commit -m "feat(llm): ước lượng token trung tính với provider

tiktoken/cl100k_base trên messages + JSON schema của tool. Hệ số riêng từng
nhà cung cấp KHÔNG nhân ở đây mà nhân trong can_afford(), vì lúc ước lượng
chưa chọn được model.

Tính cả schema tool: agent ERP bind hàng chục tool, phần đó thường lớn hơn
câu hỏi người dùng."
```

---

### Task 5: `budget.py` — `BudgetLedger`

Lõi của cả kế hoạch. Đây là lý do spec chọn Python thuần thay vì YAML của
LiteLLM: chính sách hạn mức phải test được, và hạn mức free-tier **theo ngày**
đúng là chỗ LiteLLM yếu nhất.

**Files:**
- Create: `backend/src/llm/budget.py`
- Create: `backend/tests/llm/conftest.py`
- Test: `backend/tests/llm/test_budget.py`

**Interfaces:**
- Consumes: `ModelSpec` (Task 2), `UsageStore` / `InMemoryUsageStore` / `Usage`
  (Task 3)
- Produces: `Verdict`, `BudgetLedger` — Task 8 (`Router.resolve`) và Task 9
  (`Router.invoke`) đều dựa vào

- [ ] **Bước 1: Viết `conftest.py` (đồng hồ giả dùng chung)**

`backend/tests/llm/conftest.py`:

```python
"""Đồ giả dùng chung cho test tầng llm. Không có gì ở đây chạm mạng hay DB."""
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    """Đồng hồ điều khiển được — cửa sổ trượt không test được bằng time thật."""

    def __init__(self, now: datetime = T0) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)


class ExplodingStore:
    """Kho luôn ném lỗi — dùng để kiểm tra hành vi fail-open của ngân sách."""

    def record(self, **kwargs) -> None:
        raise RuntimeError("Postgres sập")

    def usage_since(self, **kwargs):
        raise RuntimeError("Postgres sập")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
```

- [ ] **Bước 2: Viết test thất bại**

`backend/tests/llm/test_budget.py`:

```python
import pytest

from src.llm.budget import BudgetLedger, Verdict
from src.llm.catalog import spec_for
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import ExplodingStore, FakeClock

GEMMA = spec_for("gemma-4-26b")          # rpm 30, tpm 16_000, rpd 14_400, x1.0
GROQ = spec_for("groq-gpt-oss-20b")      # rpm 30, tpm  8_000, rpd  1_000, x2.3
OR_LING = spec_for("or-ling")            # rpd 50, quota_scope="account"
OR_NEMO = spec_for("or-nemotron")        # rpd 50, quota_scope="account"


def _ledger(clock, store=None):
    return BudgetLedger(store or InMemoryUsageStore(), clock=clock)


def _fill(ledger, spec, n, total_tokens=1):
    for _ in range(n):
        ledger.record(spec, prompt_tokens=1, completion_tokens=1,
                      total_tokens=total_tokens)


def test_so_sach_trong_thi_cho_goi(clock):
    assert _ledger(clock).can_afford(GEMMA, 100) is Verdict.OK


def test_cham_tran_rpm_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    assert led.can_afford(GEMMA, 100) is Verdict.RPM


def test_qua_mot_phut_thi_rpm_hoi_lai(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    clock.advance(seconds=61)
    assert led.can_afford(GEMMA, 100) is Verdict.OK


def test_cham_tran_tpm_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 1, total_tokens=15_900)
    assert led.can_afford(GEMMA, 200) is Verdict.TPM


def test_he_so_token_cua_provider_duoc_ap_dung(clock):
    """Groq đếm nặng 2.3×. 3_000 token thô → ~6_900 ước lượng, vẫn lọt 8K.
    Nhưng 3_500 thô → ~8_050, vượt trần. Không nhân hệ số thì cả hai đều lọt."""
    led = _ledger(clock)
    assert led.can_afford(GROQ, 3_000) is Verdict.OK
    assert led.can_afford(GROQ, 3_500) is Verdict.TPM


def test_cham_tran_rpd_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GROQ, 1_000)
    clock.advance(hours=2)          # RPM/TPM đã hồi, RPD thì chưa
    assert led.can_afford(GROQ, 10) is Verdict.RPD


def test_cua_so_truot_24h_chu_khong_phai_ngay_lich(clock):
    led = _ledger(clock)
    _fill(led, GROQ, 1_000)
    clock.advance(hours=23)
    assert led.can_afford(GROQ, 10) is Verdict.RPD
    clock.advance(hours=2)          # tổng 25h — bản ghi cũ rơi khỏi cửa sổ
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_rpd_duoc_bao_truoc_tpm(clock):
    """Cạn ngân sách ngày mà báo "tpm_exhausted" là gợi ý sai — nó khiến người
    đọc tưởng chờ một phút là xong."""
    led = _ledger(clock)
    _fill(led, GROQ, 1_000, total_tokens=7_999)
    assert led.can_afford(GROQ, 10_000) is Verdict.RPD


def test_quota_scope_account_gop_chung_moi_model_openrouter(clock):
    """OR_LING và OR_NEMO là hai model khác nhau nhưng chung một ví 50/ngày."""
    led = _ledger(clock)
    _fill(led, OR_LING, 50)
    assert led.can_afford(OR_NEMO, 10) is Verdict.RPD


def test_quota_scope_model_khong_gop_chung(clock):
    """Ngược lại: gemma-4-26b cạn không kéo theo groq-gpt-oss-20b."""
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_cooldown_chan_roi_tu_het_han(clock):
    led = _ledger(clock)
    led.cooldown(GEMMA, seconds=30)
    assert led.can_afford(GEMMA, 10) is Verdict.COOLDOWN
    clock.advance(seconds=31)
    assert led.can_afford(GEMMA, 10) is Verdict.OK


def test_cooldown_chi_anh_huong_dung_alias_do(clock):
    led = _ledger(clock)
    led.cooldown(GEMMA, seconds=30)
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_kho_sap_thi_FAIL_OPEN_cho_goi(clock):
    """NGƯỢC với write_gate.py (fail-closed) và cố ý như vậy: write_gate chặn
    thao tác ghi ERP không hoàn tác được; ngân sách chỉ chắn một cái 429 tự
    lành mà chuỗi fallback đã xử lý. Fail-closed ở đây là đánh sập cả hệ thống
    để bảo vệ một hạn mức miễn phí."""
    led = _ledger(clock, store=ExplodingStore())
    assert led.can_afford(GEMMA, 100) is Verdict.OK


def test_kho_sap_luc_ghi_khong_lam_vo_luot_goi(clock):
    led = _ledger(clock, store=ExplodingStore())
    led.record(GEMMA, prompt_tokens=1, completion_tokens=1, total_tokens=2)


def test_han_muc_None_thi_khong_kiem(clock):
    """OpenRouter không công bố rpm/tpm — None nghĩa là không áp trần đó."""
    led = _ledger(clock)
    assert OR_LING.rpm is None and OR_LING.tpm is None
    assert led.can_afford(OR_LING, 10_000_000) is Verdict.OK


def test_record_dung_total_tokens_khong_phai_prompt_cong_completion(clock):
    """Gemma: p=11, c=36, total=337. Cộng p+c đếm thiếu 7 lần."""
    store = InMemoryUsageStore()
    led = _ledger(clock, store=store)
    led.record(GEMMA, prompt_tokens=11, completion_tokens=36, total_tokens=337)
    got = store.usage_since(since=clock() , alias="gemma-4-26b")
    assert got.total_tokens == 337
```

- [ ] **Bước 3: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_budget.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.budget'`

- [ ] **Bước 4: Viết `budget.py`**

`backend/src/llm/budget.py`:

```python
"""Kế toán hạn mức free-tier (spec SP-1 §2).

Chính sách thuần — KHÔNG biết Postgres tồn tại. Mọi thứ đi qua UsageStore, nên
toàn bộ file này test được bằng kho trong bộ nhớ và một đồng hồ giả.
"""
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum

from .catalog import ModelSpec
from .store import UsageStore

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    OK = "ok"
    RPM = "rpm_exhausted"
    TPM = "tpm_exhausted"
    RPD = "rpd_exhausted"
    COOLDOWN = "cooldown"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BudgetLedger:
    def __init__(self, store: UsageStore, clock=None) -> None:
        self._store = store
        self._clock = clock or _utcnow
        # Cooldown chỉ nằm trong bộ nhớ có chủ đích: nó ngắn (giây tới phút),
        # nên mất khi khởi động lại là vô hại — cùng lắm thử lại một provider
        # đang ốm và ăn thêm một cái 429, mà 429 thì chuỗi fallback đã xử lý.
        self._cooldowns: dict[str, datetime] = {}

    # ── Khoá gộp ────────────────────────────────────────────────────────────
    def _scope_kwargs(self, spec: ModelSpec) -> dict:
        """quota_scope="model" (Google, Groq) → gộp theo alias.
        quota_scope="account" (OpenRouter) → gộp theo provider: mọi model free
        của OpenRouter chia chung một ví ~50 lượt/ngày."""
        if spec.quota_scope == "account":
            return {"provider": spec.provider}
        return {"alias": spec.alias}

    # ── Đọc ─────────────────────────────────────────────────────────────────
    def can_afford(self, spec: ModelSpec, base_tokens: int) -> Verdict:
        now = self._clock()

        until = self._cooldowns.get(spec.alias)
        if until is not None and now < until:
            return Verdict.COOLDOWN

        # Hệ số provider nhân Ở ĐÂY, không nhân lúc ước lượng: trước khi chọn
        # được spec thì chưa biết nhân hệ số nào (xem tokens.py).
        est = int(base_tokens * spec.token_multiplier)
        scope = self._scope_kwargs(spec)

        try:
            minute = self._store.usage_since(
                since=now - timedelta(seconds=60), **scope)
            # Cửa sổ TRƯỢT 24h, không phải "ngày lịch": Google reset hạn mức
            # lúc nửa đêm giờ Thái Bình Dương, Groq và OpenRouter reset ở múi
            # giờ khác — ba múi giờ là ba con bug đang chờ. Cửa sổ trượt chỉ
            # có một cách hiện thực và luôn THẬN TRỌNG HƠN mức thật; giá phải
            # trả là hơi bi quan ngay sau một đợt dùng dồn — chấp nhận được.
            day = self._store.usage_since(
                since=now - timedelta(hours=24), **scope)
        except Exception:
            # FAIL-OPEN, ngược với write_gate.py (fail-closed) và cố ý như vậy:
            # write_gate chặn thao tác ghi ERP KHÔNG HOÀN TÁC ĐƯỢC nên mơ hồ
            # thì phải khoá; sổ ngân sách chỉ chắn một cái 429 TỰ LÀNH mà chuỗi
            # fallback đã xử lý sẵn. Fail-closed ở đây là đánh sập cả hệ thống
            # để bảo vệ một hạn mức miễn phí — sai tỉ lệ.
            logger.warning("không đọc được sổ ngân sách, cho gọi (fail-open)",
                           exc_info=True)
            return Verdict.OK

        # Thứ tự kiểm theo chân trời hồi phục GIẢM DẦN, để phán quyết trả về là
        # cái cung cấp nhiều thông tin nhất. Cạn ngân sách ngày mà báo
        # "tpm_exhausted" sẽ khiến người đọc tưởng chờ một phút là xong.
        if spec.rpd is not None and day.requests >= spec.rpd:
            return Verdict.RPD
        if spec.rpm is not None and minute.requests >= spec.rpm:
            return Verdict.RPM
        if spec.tpm is not None and minute.total_tokens + est > spec.tpm:
            return Verdict.TPM
        return Verdict.OK

    # ── Ghi ─────────────────────────────────────────────────────────────────
    def record(self, spec: ModelSpec, prompt_tokens: int,
               completion_tokens: int, total_tokens: int) -> None:
        """total_tokens là con số CÓ THẨM QUYỀN cho mọi phép kiểm token.

        Đo 2026-07-28: gemma-4-26b-a4b-it trả prompt=11, completion=36 nhưng
        total=337 — có ~290 token "thinking" không nằm trong completion_tokens
        mà vẫn bị tính vào tổng. Cộng hai thành phần đếm thiếu 7 lần, tức sổ
        báo còn hạn mức trong khi ví đã cạn. prompt/completion vẫn lưu để chẩn
        đoán, nhưng không dùng cho phép kiểm nào.
        """
        try:
            self._store.record(
                ts=self._clock(), alias=spec.alias, provider=spec.provider,
                upstream=spec.upstream, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, total_tokens=total_tokens)
        except Exception:
            # Cùng lý do fail-open: không ghi được sổ thì mất một dòng kế toán,
            # KHÔNG được làm vỡ lượt gọi đã thành công.
            logger.warning("không ghi được sổ ngân sách", exc_info=True)

    def cooldown(self, spec: ModelSpec, seconds: float) -> None:
        self._cooldowns[spec.alias] = self._clock() + timedelta(seconds=seconds)
```

- [ ] **Bước 5: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_budget.py -v`
Kỳ vọng: 16 test PASS

- [ ] **Bước 6: Commit**

```bash
git add backend/src/llm/budget.py backend/src/llm/store.py \
        backend/tests/llm/conftest.py backend/tests/llm/test_budget.py
git commit -m "feat(llm): BudgetLedger — kế toán RPM/TPM/RPD cửa sổ trượt

Ba quyết định có bình luận tại điểm code:
- cửa sổ trượt 24h thay vì ngày lịch (3 provider reset ở 3 múi giờ khác nhau)
- fail-open khi kho sập, NGƯỢC write_gate fail-closed và cố ý: ngân sách chỉ
  chắn một cái 429 tự lành, không phải thao tác ghi ERP không hoàn tác được
- total_tokens là con số có thẩm quyền, không cộng prompt+completion

Hệ số token theo provider nhân trong can_afford(), không nhân lúc ước lượng."
```

---

### Task 6: `PostgresUsageStore` + migration

Sổ ngân sách phải sống qua lần khởi động lại: RPD trải dài 24 giờ, mà bản trong
bộ nhớ thì mất sạch mỗi lần restart backend — đúng lúc đó hệ thống sẽ tưởng ví
còn nguyên và bắn thẳng vào 429.

Cooldown thì **không** cần bền, và đã cố ý để trong bộ nhớ ở Task 5.

**Files:**
- Create: `backend/migrations/001_llm_usage.sql`
- Modify: `backend/src/llm/store.py` (thêm `PostgresUsageStore` vào cuối)
- Modify: `backend/requirements.txt` (thêm `psycopg-pool`)
- Test: `backend/tests/llm/test_store_postgres.py`

**Interfaces:**
- Consumes: `Usage`, `UsageStore` (Task 3)
- Produces: `PostgresUsageStore(dsn: str | None = None)` — Task 10
  (`make_llms`) dựng nó cho đường chạy thật

- [ ] **Bước 1: Thêm dependency**

Thêm vào `backend/requirements.txt`:

```
psycopg-pool==3.3.1
```

Khớp phiên bản repo nguồn `D:\Project`. Dùng pool chứ không mở kết nối mỗi lần
gọi: `can_afford()` bắn 2 truy vấn, và nó nằm trên đường nóng của mỗi lượt chat
nhân với độ dài chuỗi fallback.

- [ ] **Bước 2: Viết migration**

`backend/migrations/001_llm_usage.sql`:

```sql
-- Sổ ngân sách LLM (spec SP-1 §2).
--
-- MỘT bảng cho cả ba cửa sổ (phút / phút / 24 giờ). Không cache, không sổ kép:
-- ở lưu lượng vài nghìn lượt/ngày Postgres làm việc này không tốn gì, mà một
-- cơ chế thì không bao giờ lệch với chính nó.
--
-- prompt_tokens và completion_tokens lưu để CHẨN ĐOÁN, không dùng cho phép
-- kiểm hạn mức nào. Con số có thẩm quyền là total_tokens — đo 2026-07-28,
-- gemma-4-26b-a4b-it trả p=11, c=36 nhưng total=337 (~290 token "thinking"
-- vô hình). Cộng p+c đếm thiếu 7 lần.

CREATE TABLE IF NOT EXISTS llm_usage (
    id                bigserial PRIMARY KEY,
    ts                timestamptz NOT NULL,
    alias             text        NOT NULL,
    provider          text        NOT NULL,
    upstream          text        NOT NULL,
    prompt_tokens     integer     NOT NULL,
    completion_tokens integer     NOT NULL,
    total_tokens      integer     NOT NULL
);

-- Gộp theo alias khi quota_scope="model" (Google, Groq).
CREATE INDEX IF NOT EXISTS llm_usage_alias_ts_idx
    ON llm_usage (alias, ts DESC);

-- Gộp theo provider khi quota_scope="account" (OpenRouter dùng chung một ví).
-- Cột provider PHẢI có thật, không suy ra từ alias lúc truy vấn.
CREATE INDEX IF NOT EXISTS llm_usage_provider_ts_idx
    ON llm_usage (provider, ts DESC);

-- Dọn bản ghi cũ: mọi truy vấn chỉ nhìn lại tối đa 24 giờ, nên phần cũ hơn chỉ
-- còn giá trị chẩn đoán. SP-1 KHÔNG tự dọn (lưu lượng quá nhỏ để đáng bận tâm).
-- Khi cần:  DELETE FROM llm_usage WHERE ts < now() - interval '30 days';
```

- [ ] **Bước 3: Viết test thất bại**

`backend/tests/llm/test_store_postgres.py`:

```python
"""Test tích hợp — cần Postgres đang chạy.

Chạy:  pytest tests/llm/test_store_postgres.py -m integration -v
Bỏ:    pytest -m "not integration"
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.llm.store import PostgresUsageStore, Usage

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")


@pytest.fixture
def store():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    s = PostgresUsageStore(DSN)
    with s._pool.connection() as conn:          # dọn sạch trước mỗi test
        conn.execute("DELETE FROM llm_usage WHERE alias LIKE 'test-%'")
    yield s
    s.close()


def _rec(store, ts, alias="test-a1", provider="test-p1", total=30):
    store.record(ts=ts, alias=alias, provider=provider, upstream="test-u1",
                 prompt_tokens=10, completion_tokens=20, total_tokens=total)


def test_ghi_roi_doc_lai_dung_so(store):
    now = datetime.now(timezone.utc)
    _rec(store, now, total=30)
    _rec(store, now, total=70)
    got = store.usage_since(since=now - timedelta(minutes=1), alias="test-a1")
    assert got == Usage(requests=2, total_tokens=100)


def test_khong_co_gi_thi_tra_ve_khong_chu_khong_phai_None(store):
    now = datetime.now(timezone.utc)
    got = store.usage_since(since=now, alias="test-khong-ton-tai")
    assert got == Usage(requests=0, total_tokens=0)


def test_loc_theo_provider_gop_moi_alias(store):
    now = datetime.now(timezone.utc)
    _rec(store, now, alias="test-a1", provider="test-or", total=30)
    _rec(store, now, alias="test-a2", provider="test-or", total=70)
    got = store.usage_since(since=now - timedelta(minutes=1),
                            provider="test-or")
    assert got == Usage(requests=2, total_tokens=100)


def test_moc_since_loai_ban_ghi_ngoai_cua_so(store):
    now = datetime.now(timezone.utc)
    _rec(store, now - timedelta(hours=25), total=999)
    _rec(store, now - timedelta(hours=1), total=50)
    got = store.usage_since(since=now - timedelta(hours=24), alias="test-a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_phai_dua_dung_mot_trong_hai_alias_hoac_provider(store):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        store.usage_since(since=now)
    with pytest.raises(ValueError):
        store.usage_since(since=now, alias="a", provider="p")
```

- [ ] **Bước 4: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_store_postgres.py -m integration -v`
Kỳ vọng: FAIL với `ImportError: cannot import name 'PostgresUsageStore'`

- [ ] **Bước 5: Viết `PostgresUsageStore`**

Thêm vào **cuối** `backend/src/llm/store.py`:

```python
class PostgresUsageStore:
    """Bản bền của UsageStore.

    Sổ phải sống qua lần khởi động lại: RPD trải dài 24 giờ, mà bản trong bộ
    nhớ mất sạch mỗi lần restart — đúng lúc đó hệ thống sẽ tưởng ví còn nguyên
    và bắn thẳng vào 429. (Cooldown thì ngược lại, cố ý để trong bộ nhớ ở
    budget.py.)

    KHÔNG bắt exception ở đây: BudgetLedger là chỗ quyết định fail-open, và nó
    chỉ quyết được nếu lỗi nổi lên tới nó. Nuốt lỗi ở tầng này sẽ biến "Postgres
    sập" thành "ví rỗng", tức mở toang mọi hạn mức mà không ai biết.
    """

    def __init__(self, dsn: str | None = None, *, pool=None) -> None:
        if pool is not None:
            self._pool = pool
            self._owns_pool = False
            return
        import os

        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(dsn or os.environ["DATABASE_URL"],
                                    min_size=1, max_size=4, open=True)
        self._owns_pool = True

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    def record(self, *, ts: datetime, alias: str, provider: str, upstream: str,
               prompt_tokens: int, completion_tokens: int,
               total_tokens: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO llm_usage (ts, alias, provider, upstream, "
                "prompt_tokens, completion_tokens, total_tokens) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (ts, alias, provider, upstream, prompt_tokens,
                 completion_tokens, total_tokens))

    def usage_since(self, *, since: datetime, alias: str | None = None,
                    provider: str | None = None) -> Usage:
        _check_exactly_one(alias, provider)
        column = "alias" if alias is not None else "provider"
        value = alias if alias is not None else provider
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT count(*), coalesce(sum(total_tokens), 0) "
                f"FROM llm_usage WHERE {column} = %s AND ts >= %s",
                (value, since)).fetchone()
        # coalesce ở trên đảm bảo sum không trả NULL khi không có dòng nào —
        # nếu không, Usage(total_tokens=None) sẽ làm phép cộng ở can_afford() vỡ.
        return Usage(requests=row[0], total_tokens=row[1])
```

`column` được nội suy vào chuỗi SQL, nhưng nó **không** đến từ đầu vào người
dùng: `_check_exactly_one()` đã chốt nó chỉ có thể là đúng một trong hai literal
`"alias"` / `"provider"` do chính code này viết ra. Giá trị so sánh vẫn đi qua
tham số hoá.

- [ ] **Bước 6: Áp migration và chạy test**

```bash
psql "$DATABASE_URL" -f backend/migrations/001_llm_usage.sql
cd backend && python -m pytest tests/llm/test_store_postgres.py -m integration -v
```

Kỳ vọng: 5 test PASS

Rồi chạy lại toàn bộ test không cần hạ tầng, để chắc chắn không hỏng gì:

```bash
python -m pytest -m "not integration and not live" -v
```

Kỳ vọng: toàn bộ test của Task 2–5 vẫn PASS

- [ ] **Bước 7: Commit**

```bash
git add backend/migrations/001_llm_usage.sql backend/src/llm/store.py \
        backend/requirements.txt backend/tests/llm/test_store_postgres.py
git commit -m "feat(llm): PostgresUsageStore + migration llm_usage

Sổ ngân sách phải bền: RPD trải 24 giờ, bản trong bộ nhớ mất mỗi lần restart —
đúng lúc đó hệ thống tưởng ví còn nguyên và bắn vào 429.

Một bảng cho cả ba cửa sổ, index theo (alias, ts) và (provider, ts) — cột
provider phải có thật vì OpenRouter gộp hạn mức theo tài khoản.

Store KHÔNG bắt exception: BudgetLedger mới là chỗ quyết định fail-open, và nó
chỉ quyết được nếu lỗi nổi lên tới nó."
```

---

### Task 7: `providers.py` — ba client + gỡ `<thought>`

Chỗ **duy nhất** biết `base_url` và tên biến môi trường của từng nhà cung cấp.

Phần thú vị không phải ba client (chúng gần như giống hệt nhau) mà là
`strip_thought()`. Đo 2026-07-28: `gemma-4-26b-a4b-it` và `gemma-4-31b-it` nhả
nguyên khối `<thought>…</thought>` vào **trường `content`** qua endpoint
OpenAI-compat, câu trả lời thật nằm ngay sau thẻ đóng. Vai `chitchat` và
`router` chạy Gemma, nên không gỡ là người dùng nhìn thấy phần suy nghĩ thô.

Và **không tắt được**: `reasoning_effort=none` → `400 "Thinking budget is not
supported for this model"`. Nên gỡ tất định là bắt buộc, không phải tuỳ chọn.

**Kết quả spike Task 1 (2026-07-28, đã xảy ra thật — không còn là "nếu"):**
vòng lặp tool 2 lượt qua `ChatOpenAI` → Google **không hội tụ**, Google từ
chối cứng ở lượt 2 với `400 INVALID_ARGUMENT: "Function call is missing a
thought_signature in functionCall parts"`. Chi tiết:
`docs/spikes/2026-07-28-thought-signature.md`.

**Do đó `client_for()` KHÔNG còn trả về một loại client duy nhất.** Google
dùng `ChatGoogleGenerativeAI` (gói `langchain-google-genai`, đã thêm vào
`requirements.txt` ở Task 1, bản `4.2.0` — đã xác nhận qua metadata PyPI:
đòi `langchain-core<2.0.0,>=1.2.5`, khớp bản `1.4.8` đã pin, không ép nâng
cấp). Groq và OpenRouter tiếp tục `ChatOpenAI` vì cả hai vẫn hội tụ bình
thường qua endpoint OpenAI-compat (đã đo). Bước 3 dưới đây viết đúng theo
phân nhánh này — không phải giả định "cả ba client giống hệt nhau" của bản
kế hoạch gốc.

Ba khác biệt về tên trường giữa hai lớp client mà bạn PHẢI biết trước khi
viết `client_for()` (xác nhận từ mã nguồn `langchain_google_genai._common`,
không phải suy đoán):
- `ChatGoogleGenerativeAI` nhận khoá qua `api_key` (alias của trường
  `google_api_key`) — **không phải** `api_key=...` kiểu `ChatOpenAI` dùng
  `base_url`; không có tham số `base_url` nào cả, SDK tự quản endpoint.
- Giới hạn token ra: `max_tokens` là **alias** của `max_output_tokens` — dùng
  được tên nào cũng ra cùng trường, plan này dùng `max_output_tokens=` cho
  rõ nghĩa.
- Timeout: `timeout` là tên chính (alias `request_timeout`) — giống
  `ChatOpenAI`, không cần đổi tên khi gọi.

**Files:**
- Create: `backend/src/llm/providers.py`
- Test: `backend/tests/llm/test_providers.py`

**Interfaces:**
- Consumes: `ModelSpec`, `spec_for` (Task 2)
- Produces: `strip_thought(content)`, `client_for(spec)`, `BASE_URLS`,
  `ENV_KEYS` — Task 9 (`Router.invoke`) dùng cả hai

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_providers.py`:

```python
import pytest

from src.llm.catalog import spec_for
from src.llm.providers import BASE_URLS, ENV_KEYS, client_for, strip_thought

GEMMA = spec_for("gemma-4-26b")            # emits_thought_tags=True
GEMINI = spec_for("gemini-3.5-flash-lite")  # emits_thought_tags=False
GROQ = spec_for("groq-gpt-oss-20b")
OR_LING = spec_for("or-ling")


# ─── strip_thought ──────────────────────────────────────────────────────────

def test_go_khoi_thought_va_giu_lai_cau_tra_loi():
    raw = "<thought>Người dùng chào hỏi.</thought>Chào bạn! Mình khỏe."
    assert strip_thought(raw) == "Chào bạn! Mình khỏe."


def test_khong_co_the_thi_giu_nguyen():
    assert strip_thought("Chào bạn!") == "Chào bạn!"


def test_thought_nhieu_dong():
    raw = "<thought>dòng 1\ndòng 2\ndòng 3</thought>\n\nCâu trả lời."
    assert strip_thought(raw) == "Câu trả lời."


def test_thieu_the_dong_thi_tra_ve_RONG():
    """Bị cắt giữa chừng. Trả nửa khối suy nghĩ cho người dùng còn tệ hơn trả
    rỗng — rỗng thì node gọi degrade về SAFE_MSG, đúng đường đã có."""
    assert strip_thought("<thought>đang nghĩ dở thì bị cắt") == ""


def test_None_va_chuoi_rong_khong_lam_no_vo():
    assert strip_thought(None) == ""
    assert strip_thought("") == ""


def test_chi_toan_thought_thi_tra_ve_rong():
    assert strip_thought("<thought>nghĩ xong nhưng quên trả lời</thought>") == ""


def test_the_dong_o_giua_thi_chi_go_phan_dau():
    """Chỉ khối MỞ ĐẦU là suy nghĩ. Chuỗi giống thẻ nằm trong câu trả lời thật
    (ví dụ người dùng hỏi về chính cú pháp đó) không được đụng tới."""
    raw = "<thought>nghĩ</thought>Thẻ <thought> dùng để đánh dấu suy nghĩ."
    assert strip_thought(raw) == "Thẻ <thought> dùng để đánh dấu suy nghĩ."


def test_khoang_trang_dau_truoc_the_van_xu_ly_duoc():
    assert strip_thought("\n  <thought>nghĩ</thought>Xong.") == "Xong."


# ─── client_for ─────────────────────────────────────────────────────────────
# Google → ChatGoogleGenerativeAI (spike Task 1); Groq/OpenRouter → ChatOpenAI.
# Hai lớp có TÊN TRƯỜNG khác nhau cho cùng khái niệm (đã xác nhận từ mã nguồn
# langchain_google_genai._common, không suy đoán): ChatOpenAI dùng
# `model_name`/`openai_api_base`/`request_timeout`/`max_tokens`;
# ChatGoogleGenerativeAI dùng `model`/(không có base_url)/`timeout`/
# `max_output_tokens`. Test dưới đây test ĐÚNG trường của ĐÚNG lớp — không
# giả định hai lớp đối xứng.

def test_google_dung_ChatGoogleGenerativeAI_groq_openrouter_dung_ChatOpenAI(monkeypatch):
    """Đây là hành vi CHÍNH mà quyết định spike Task 1 đòi hỏi — nếu test này
    xanh mà client_for() vẫn trả ChatOpenAI cho Google, coi như chưa làm."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert isinstance(client_for(GEMINI), ChatGoogleGenerativeAI)
    assert isinstance(client_for(GEMMA), ChatGoogleGenerativeAI)
    assert isinstance(client_for(GROQ), ChatOpenAI)
    assert isinstance(client_for(OR_LING), ChatOpenAI)


def test_moi_provider_co_ten_bien_moi_truong_rieng():
    from src.llm.catalog import CATALOG
    for spec in CATALOG.values():
        assert spec.provider in ENV_KEYS


def test_groq_va_openrouter_co_base_url_google_thi_khong():
    """Google không có base_url — ChatGoogleGenerativeAI tự quản endpoint."""
    assert "groq" in BASE_URLS and "openrouter" in BASE_URLS
    assert "google" not in BASE_URLS


def test_client_google_dung_model_id_goc_qua_truong_model(monkeypatch):
    """ChatGoogleGenerativeAI dùng trường `model`, KHÔNG phải `model_name`."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    client = client_for(GEMMA)
    assert client.model == "gemma-4-26b-a4b-it"   # KHÔNG phải "gemma-4-26b"


def test_client_groq_dung_model_id_goc_qua_truong_model_name(monkeypatch):
    """ChatOpenAI dùng trường `model_name` (alias `model` lúc khởi tạo)."""
    monkeypatch.setenv("GROQ_API_KEY", "k")
    client = client_for(GROQ)
    assert client.model_name == "openai/gpt-oss-20b"


def test_client_groq_openrouter_lay_dung_base_url_theo_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert "groq.com" in str(client_for(GROQ).openai_api_base)
    assert "openrouter.ai" in str(client_for(OR_LING).openai_api_base)


def test_client_groq_lay_timeout_va_max_tokens_tu_catalog(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    client = client_for(GROQ)
    assert client.request_timeout == GROQ.timeout_s
    assert client.max_tokens == GROQ.max_output_tokens


def test_client_google_lay_timeout_va_max_output_tokens_tu_catalog(monkeypatch):
    """Field khác tên (max_output_tokens, không phải max_tokens) nhưng PHẢI
    nhận đúng giá trị từ catalog — đây chính là chỗ dễ gõ nhầm tên field."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    client = client_for(GEMINI)
    assert client.timeout == GEMINI.timeout_s
    assert client.max_output_tokens == GEMINI.max_output_tokens


def test_thieu_bien_moi_truong_thi_chet_ngay_voi_thong_bao_ro(monkeypatch):
    """Lỗi cấu hình lệch lạc phải chết ngay và ồn ào (spec §6). Kiểm cả hai
    nhánh client — RuntimeError phải ném TRƯỚC khi chạm tới constructor nào."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client_for(GROQ)

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        client_for(GEMINI)


def test_temperature_luon_bang_khong_ca_hai_loai_client(monkeypatch):
    """Khớp repo nguồn: mọi vai đều temperature=0 để đầu ra tái lập được.
    ChatGoogleGenerativeAI cũng có trường `temperature` (khác mặc định 0.7 của
    thư viện) nên phải truyền tường minh, không dựa vào default."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert client_for(GEMINI).temperature == 0
    assert client_for(GROQ).temperature == 0
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_providers.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.providers'`

- [ ] **Bước 3: Viết `providers.py`**

`backend/src/llm/providers.py`:

```python
"""Client cho từng nhà cung cấp + chuẩn hoá đầu ra (spec SP-1 §2).

Chỗ DUY NHẤT biết base_url, tên biến môi trường, và loại client của từng nhà.
Không tầng nào khác được nhắc tới Google/Groq/OpenRouter.

Google dùng ChatGoogleGenerativeAI, KHÔNG dùng ChatOpenAI: spike Task 1
(docs/spikes/2026-07-28-thought-signature.md, 2026-07-28) đo hội thoại tool
2 lượt thật qua endpoint OpenAI-compat của Google và thấy vòng lặp KHÔNG hội
tụ — ChatOpenAI không mang thought_signature đi qua request kế tiếp, và
Google từ chối cứng ở lượt 2 với 400 INVALID_ARGUMENT. Groq và OpenRouter vẫn
ChatOpenAI: cả hai vẫn OpenAI-compatible và giữ tool-calling tiếng Việt bình
thường (đã đo — spec Phụ lục A). Đây vẫn là lý do SP-1 bỏ LiteLLM cho hai nhà
này: giá trị "hợp nhất giao thức" của nó đã bốc hơi.
"""
import os
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from .catalog import ModelSpec

# Chỉ Groq/OpenRouter dùng — Google không có base_url (SDK tự quản endpoint).
BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

ENV_KEYS = {
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Khối suy nghĩ MỞ ĐẦU. Neo vào đầu chuỗi (\A) có chủ đích: chỉ khối đầu tiên
# là suy nghĩ của model; chuỗi trông giống thẻ nằm giữa câu trả lời thật (người
# dùng hỏi về chính cú pháp đó) không được đụng tới.
_THOUGHT_RE = re.compile(r"\A\s*<thought>.*?</thought>\s*", re.DOTALL)
_THOUGHT_OPEN_RE = re.compile(r"\A\s*<thought>", re.DOTALL)


def strip_thought(content: str | None) -> str:
    """Gỡ khối <thought>…</thought> mở đầu — TẤT ĐỊNH, không nhờ prompt.

    Đo 2026-07-28: endpoint OpenAI-compat của Google KHÔNG tách phần suy nghĩ
    ra khỏi content cho họ Gemma; nó nối thẳng vào, câu trả lời thật nằm sau
    thẻ đóng. Và thinking không tắt được — reasoning_effort trả 400 "Thinking
    budget is not supported for this model".

    Cùng hình dạng với tool_leak_guard.py của repo nguồn: một cú scrub tất định
    tại ranh giới, vì định dạng model trả về chỉ tuân theo prompt một cách xác
    suất.

    Thiếu thẻ đóng (bị cắt giữa chừng) → trả RỖNG, để node gọi degrade về
    SAFE_MSG. Trả nửa khối suy nghĩ cho người dùng còn tệ hơn trả rỗng.
    """



def client_for(spec: ModelSpec):
    """Dựng client cho một model. Thiếu khoá → chết ngay, không đợi lúc gọi.

    Google → ChatGoogleGenerativeAI; Groq/OpenRouter → ChatOpenAI (quyết định
    spike Task 1). Đọc khoá và kiểm rỗng CHUNG cho cả hai nhánh trước khi rẽ,
    để thông báo lỗi thiếu biến môi trường nhất quán bất kể provider nào.
    """
    env_name = ENV_KEYS[spec.provider]
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(
            f"thiếu biến môi trường {env_name} — cần cho provider "
            f"{spec.provider!r} (model {spec.alias!r}). Xem .env.example.")

    if spec.provider == "google":
        # KHÔNG có base_url — SDK tự quản endpoint. Field tên `model` (không
        # phải `model_name`), `max_output_tokens` (không phải `max_tokens`,
        # dù đó là alias hợp lệ — dùng tên chính cho rõ nghĩa), `timeout`.
        return ChatGoogleGenerativeAI(
            model=spec.model_id,      # ID GỐC của nhà cung cấp, không phải alias
            api_key=api_key,
            temperature=0,
            timeout=spec.timeout_s,
            max_output_tokens=spec.max_output_tokens,
        )
    return ChatOpenAI(
        model=spec.model_id,          # ID GỐC của nhà cung cấp, không phải alias
        base_url=BASE_URLS[spec.provider],
        api_key=api_key,
        temperature=0,
        timeout=spec.timeout_s,
        max_tokens=spec.max_output_tokens,
    )
```

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_providers.py -v`
Kỳ vọng: 18 test PASS

Nếu tên thuộc tính (`model_name`/`openai_api_base`/`request_timeout` của
`ChatOpenAI`, hay `model`/`timeout`/`max_output_tokens` của
`ChatGoogleGenerativeAI`) không khớp phiên bản thư viện đang cài, hãy
`print(client.__fields__.keys())` một lần rồi **sửa test cho khớp thuộc tính
thật** — các assertion đó chỉ nhằm chứng minh cấu hình đã truyền xuống, không
nhằm khoá tên thuộc tính của thư viện. Tên trường đã dùng ở đây được xác nhận
từ mã nguồn `langchain_google_genai._common` ngày 2026-07-28, nhưng thư viện
có thể đổi giữa các bản.

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/providers.py backend/tests/llm/test_providers.py
git commit -m "feat(llm): client theo provider (Google native) + gỡ <thought> tất định

Chỗ duy nhất biết base_url, tên biến môi trường, và loại client của từng nhà.

Google dùng ChatGoogleGenerativeAI, KHÔNG ChatOpenAI: spike Task 1 đo vòng
lặp tool 2 lượt qua ChatOpenAI → Google KHÔNG hội tụ, Google từ chối cứng ở
lượt 2 (400, thiếu thought_signature). Groq/OpenRouter vẫn ChatOpenAI. Tên
trường khác nhau giữa hai lớp (model/model_name, timeout/request_timeout,
max_output_tokens/max_tokens) đã đối chiếu với mã nguồn thư viện, không đoán.

strip_thought(): họ Gemma nhả nguyên <thought>...</thought> vào trường content
qua endpoint OpenAI-compat, và thinking KHÔNG tắt được (reasoning_effort trả
400). Vai chitchat/router chạy Gemma nên không gỡ là lộ suy nghĩ thô ra người
dùng. Neo \\A: chỉ khối mở đầu bị gỡ, chuỗi giống thẻ trong câu trả lời thật
không bị đụng. Thiếu thẻ đóng → trả rỗng để node degrade về SAFE_MSG.

Thiếu biến môi trường → RuntimeError ngay lúc dựng client, không đợi lúc gọi
(cả hai nhánh)."
```

---

### Task 8: `router.py` — `resolve()`, `RouteDecision`, chế độ ghim

Ghép catalog với sổ ngân sách thành một quyết định. Task này **chỉ chọn**,
chưa gọi — gọi thật ở Task 9. Tách vậy để phần chọn test được hoàn toàn bằng
sổ giả, không cần client nào.

`RouteDecision` không chỉ mang model được chọn mà mang cả **những mắt xích bị
bỏ qua và lý do**. Đó chính là bộ thuộc tính span mà kế hoạch C đổ vào Langfuse
để một trace tự trả lời được câu *"vì sao lượt này chạy Groq chứ không phải
Gemini?"*. Không ghi lại lúc quyết định thì sau đó không dựng lại được.

**Files:**
- Create: `backend/src/llm/router.py`
- Test: `backend/tests/llm/test_router.py`

**Interfaces:**
- Consumes: `chain_for`, `spec_for`, `ModelSpec` (Task 2); `BudgetLedger`,
  `Verdict` (Task 5)
- Produces: `SkippedLink`, `RouteDecision`, `ChainExhausted`, `Router.resolve`
  — Task 9 thêm `.invoke()` vào cùng lớp `Router`

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_router.py`:

```python
import pytest

from src.llm.budget import BudgetLedger, Verdict
from src.llm.catalog import spec_for
from src.llm.router import ChainExhausted, RouteDecision, Router, SkippedLink
from src.llm.store import InMemoryUsageStore


def _router(clock, store=None):
    return Router(BudgetLedger(store or InMemoryUsageStore(), clock=clock))


def _fill(router, alias, n, total_tokens=1):
    spec = spec_for(alias)
    for _ in range(n):
        router._ledger.record(spec, prompt_tokens=1, completion_tokens=1,
                              total_tokens=total_tokens)


def test_so_sach_trong_thi_chon_mat_xich_dau_tien(clock):
    got = _router(clock).resolve("read", base_tokens=100)
    assert got.spec.alias == "gemini-3.5-flash-lite"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_mat_xich_dau_can_thi_tut_xuong_cai_ke(clock):
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)      # rpd = 500
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-llama-3.3-70b"
    assert got.fallback_depth == 1
    assert got.skipped == (
        SkippedLink(alias="gemini-3.5-flash-lite", verdict=Verdict.RPD),)


def test_tut_qua_hai_mat_xich(clock):
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)
    _fill(r, "groq-llama-3.3-70b", 1_000)
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "or-nemotron"
    assert got.fallback_depth == 2
    assert [s.alias for s in got.skipped] == [
        "gemini-3.5-flash-lite", "groq-llama-3.3-70b"]


def test_can_ca_chuoi_thi_nem_ChainExhausted_kem_ly_do_tung_mat_xich(clock):
    r = _router(clock)
    _fill(r, "gemini-3.1-flash-lite", 500)
    _fill(r, "groq-llama-3.3-70b", 1_000)
    with pytest.raises(ChainExhausted) as err:
        r.resolve("fusion", base_tokens=100)      # chuỗi fusion chỉ có 2 mắt
    assert [s.alias for s in err.value.skipped] == [
        "gemini-3.1-flash-lite", "groq-llama-3.3-70b"]
    assert all(s.verdict is Verdict.RPD for s in err.value.skipped)


def test_cooldown_cung_lam_tut_mat_xich(clock):
    r = _router(clock)
    r._ledger.cooldown(spec_for("gemini-3.5-flash-lite"), seconds=30)
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-llama-3.3-70b"
    assert got.skipped[0].verdict is Verdict.COOLDOWN


def test_ghim_bo_qua_toan_bo_chuoi(clock):
    """Eval phải đo MỘT MODEL, không đo một trạng thái ngân sách."""
    r = _router(clock)
    got = r.resolve("read", base_tokens=100, pin="or-nemotron")
    assert got.spec.alias == "or-nemotron"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_ghim_van_chon_dung_model_ke_ca_khi_no_da_can(clock):
    """Ghim là ghim. Ngân sách cạn thì để lượt gọi ăn 429 thật, chứ tụt sang
    model khác sẽ làm hỏng phép đo mà không báo gì."""
    r = _router(clock)
    _fill(r, "or-nemotron", 50)
    got = r.resolve("read", base_tokens=100, pin="or-nemotron")
    assert got.spec.alias == "or-nemotron"


def test_ghim_alias_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("read", base_tokens=100, pin="model-ma")


def test_vai_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("vai-khong-co", base_tokens=100)


def test_RouteDecision_mang_du_thuoc_tinh_cho_span_langfuse(clock):
    """Kế hoạch C đổ đúng các trường này vào span Langfuse."""
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)
    got = r.resolve("read", base_tokens=250)
    assert isinstance(got, RouteDecision)
    assert got.role == "read"
    assert got.base_tokens == 250
    assert got.spec.provider == "groq"
    assert got.spec.upstream == "groq"
    assert got.fallback_depth == 1
    assert got.skipped[0].verdict.value == "rpd_exhausted"


def test_moi_vai_deu_giai_quyet_duoc_khi_so_sach_trong(clock):
    from src.llm.catalog import ROLES
    r = _router(clock)
    for role in ROLES:
        assert r.resolve(role, base_tokens=10).fallback_depth == 0
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_router.py -v`
Kỳ vọng: FAIL với `ModuleNotFoundError: No module named 'src.llm.router'`

- [ ] **Bước 3: Viết phần `resolve` của `router.py`**

`backend/src/llm/router.py`:

```python
"""Định tuyến vai trò → model (spec SP-1 §2).

resolve() CHỈ chọn, không gọi — gọi thật nằm ở Router.invoke() (Task 9). Tách
vậy để toàn bộ logic chọn test được bằng sổ ngân sách giả, không cần client.
"""
import logging
from dataclasses import dataclass

from .budget import BudgetLedger, Verdict
from .catalog import ModelSpec, chain_for, spec_for
from .providers import client_for

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkippedLink:
    alias: str
    verdict: Verdict


@dataclass(frozen=True)
class RouteDecision:
    """Quyết định định tuyến của MỘT lượt gọi.

    Mang cả những mắt xích bị bỏ qua và lý do, không chỉ mang cái được chọn:
    đây đúng là bộ thuộc tính span mà kế hoạch C đổ vào Langfuse để một trace
    tự trả lời được "vì sao lượt này chạy Groq chứ không phải Gemini". Không
    ghi lại lúc quyết định thì sau đó không dựng lại được.
    """
    role: str
    spec: ModelSpec
    fallback_depth: int
    skipped: tuple[SkippedLink, ...]
    base_tokens: int


class ChainExhausted(RuntimeError):
    """Cạn cả chuỗi cho một vai. Node gọi bắt lỗi này và degrade về SAFE_MSG —
    người dùng không bao giờ thấy stack trace (spec §6)."""

    def __init__(self, role: str, skipped: tuple[SkippedLink, ...]) -> None:
        self.role = role
        self.skipped = skipped
        chi_tiet = ", ".join(f"{s.alias}={s.verdict.value}" for s in skipped)
        super().__init__(f"cạn chuỗi cho vai {role!r}: {chi_tiet}")


class Router:
    def __init__(self, ledger: BudgetLedger, client_factory=client_for) -> None:
        self._ledger = ledger
        # client_factory tiêm được để test bằng client giả. Task 9 dùng tới hai
        # trường dưới; khai đủ ngay từ đây để KHÔNG phải định nghĩa lại
        # __init__ ở task sau.
        self._client_factory = client_factory
        self._clients: dict[str, object] = {}

    def resolve(self, role: str, base_tokens: int,
                pin: str | None = None) -> RouteDecision:
        """Mắt xích đầu tiên còn đủ ngân sách và không bị cooldown.

        pin: bỏ qua toàn bộ chuỗi, ép đúng một model. Chế độ này TỒN TẠI VÌ
        EVAL (spec §2): thiết kế fallback khiến cùng một câu hỏi có thể được
        trả lời bởi 3 model khác nhau tuỳ trạng thái ngân sách lúc đó, nên eval
        phải đo MỘT MODEL chứ không phải một trạng thái ngân sách. Ghim là
        ghim — ngân sách cạn cũng không tụt, vì tụt lặng lẽ sẽ làm hỏng phép đo
        mà không báo gì.
        """
        if pin is not None:
            return RouteDecision(role=role, spec=spec_for(pin),
                                 fallback_depth=0, skipped=(),
                                 base_tokens=base_tokens)

        skipped: list[SkippedLink] = []
        for depth, spec in enumerate(chain_for(role)):
            verdict = self._ledger.can_afford(spec, base_tokens)
            if verdict is Verdict.OK:
                if skipped:
                    logger.info("vai %s tụt xuống %s (bỏ qua: %s)", role,
                                spec.alias,
                                [f"{s.alias}={s.verdict.value}" for s in skipped])
                return RouteDecision(role=role, spec=spec, fallback_depth=depth,
                                     skipped=tuple(skipped),
                                     base_tokens=base_tokens)
            skipped.append(SkippedLink(alias=spec.alias, verdict=verdict))

        raise ChainExhausted(role, tuple(skipped))
```

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_router.py -v`
Kỳ vọng: 11 test PASS

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/router.py backend/tests/llm/test_router.py
git commit -m "feat(llm): Router.resolve + RouteDecision + chế độ ghim

RouteDecision mang cả những mắt xích bị bỏ qua kèm lý do, không chỉ cái được
chọn — đây là bộ thuộc tính span Langfuse của kế hoạch C, để một trace tự trả
lời được 'vì sao lượt này chạy Groq'.

Chế độ ghim tồn tại vì eval: fallback khiến cùng một câu hỏi có thể do 3 model
khác nhau trả lời tuỳ trạng thái ngân sách, nên eval phải đo MỘT model. Ghim là
ghim — cạn ngân sách cũng không tụt, vì tụt lặng lẽ làm hỏng phép đo."
```

---

### Task 9: `Router.invoke()` / `.ainvoke()` — gọi thật, cooldown, tụt mắt xích

Task 8 chọn theo **ngân sách**; task này xử lý cái ngân sách không đoán được:
provider ốm, 429 bất ngờ, timeout. Cách tụt mắt xích ở đây gọn một cách dễ
chịu — đặt cooldown cho mắt xích vừa hỏng rồi gọi lại `resolve()`, và
`can_afford()` sẽ tự bỏ qua nó. Không cần tham số `exclude`.

Có một cái bẫy phải tránh bằng được, mô tả ở bước 3: **cách rút `total_tokens`
ra khỏi response**.

**Files:**
- Modify: `backend/src/llm/router.py` (thêm vào lớp `Router` đã có)
- Modify: `backend/tests/llm/conftest.py` (thêm client giả)
- Test: `backend/tests/llm/test_router_invoke.py`

**Interfaces:**
- Consumes: `Router.resolve`, `RouteDecision`, `ChainExhausted` (Task 8);
  `client_for`, `strip_thought` (Task 7); `estimate_base_tokens` (Task 4)
- Produces: `InvokeResult`, `AttemptError`, `Router.invoke`, `Router.ainvoke`,
  `COOLDOWN_RATE_LIMIT_S`, `COOLDOWN_ERROR_S` — Task 10 bọc chúng lại thành
  `Runnable`

- [ ] **Bước 1: Thêm client giả vào `conftest.py`**

Thêm vào cuối `backend/tests/llm/conftest.py`:

```python
from langchain_core.messages import AIMessage


class FakeChatClient:
    """Client giả — trả sẵn kịch bản, đếm số lần bị gọi.

    responses: danh sách phần tử, mỗi phần tử là AIMessage (thành công) HOẶC
    một Exception (ném ra). Dùng hết thì lặp lại phần tử cuối.
    """

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[list] = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def _next(self, messages):
        self.calls.append(messages)
        item = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def invoke(self, messages, **kwargs):
        return self._next(messages)

    async def ainvoke(self, messages, **kwargs):
        return self._next(messages)


def fake_ai(content="xong", *, prompt=10, completion=20, total=30):
    """AIMessage kèm usage ở ĐÚNG chỗ mà provider thật đặt nó."""
    return AIMessage(
        content=content,
        response_metadata={"token_usage": {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total}})


class FakeRateLimit(Exception):
    status_code = 429


class FakeServerError(Exception):
    status_code = 503
```

- [ ] **Bước 2: Viết test thất bại**

`backend/tests/llm/test_router_invoke.py`:

```python
import pytest
from langchain_core.messages import HumanMessage

from src.llm.budget import BudgetLedger
from src.llm.catalog import spec_for
from src.llm.router import COOLDOWN_RATE_LIMIT_S, ChainExhausted, Router
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai)

MSGS = [HumanMessage("Tồn kho ABC?")]


def _router(clock, by_alias):
    """by_alias: {alias: FakeChatClient} — router lấy client theo alias."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    return Router(ledger, client_factory=lambda spec: by_alias[spec.alias])


def test_goi_thanh_cong_tra_ve_message_va_quyet_dinh(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.5-flash-lite": client})
    got = r.invoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."
    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert got.decision.fallback_depth == 0
    assert len(client.calls) == 1


def test_ghi_so_ngan_sach_bang_total_tokens_khong_phai_p_cong_c(clock):
    """Gemma: p=11, c=36, total=337. Cộng p+c đếm thiếu 7 lần."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    client = FakeChatClient([fake_ai("ok", prompt=11, completion=36, total=337)])
    r = Router(ledger, client_factory=lambda spec: client)
    r.invoke("chitchat", MSGS)
    got = store.usage_since(since=clock(), alias="gemma-4-31b")
    assert got.total_tokens == 337


def test_429_thi_dat_cooldown_va_tut_xuong_mat_xich_ke(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == "groq-llama-3.3-70b"
    assert got.decision.fallback_depth == 1
    assert [a.alias for a in got.attempts] == ["gemini-3.5-flash-lite"]


def test_sau_429_mat_xich_do_bi_cooldown_o_luot_sau(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    r.invoke("read", MSGS)
    assert len(hong.calls) == 1
    r.invoke("read", MSGS)          # lượt 2: không được chạm vào cái đang ốm
    assert len(hong.calls) == 1
    assert len(tot.calls) == 2


def test_cooldown_cua_429_dai_hon_cooldown_cua_loi_khac(clock):
    from src.llm.router import COOLDOWN_ERROR_S
    assert COOLDOWN_RATE_LIMIT_S > COOLDOWN_ERROR_S


def test_loi_5xx_cung_lam_tut_mat_xich(clock):
    hong = FakeChatClient([FakeServerError("sập")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    assert r.invoke("read", MSGS).decision.spec.alias == "groq-llama-3.3-70b"


def test_moi_mat_xich_deu_hong_thi_nem_ChainExhausted(clock):
    hong = FakeChatClient([FakeServerError("sập")])
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-llama-3.3-70b": hong})
    with pytest.raises(ChainExhausted):
        r.invoke("fusion", MSGS)      # chuỗi fusion chỉ có 2 mắt xích


def test_go_thought_cho_model_gemma(clock):
    """chitchat chạy gemma-4-31b (emits_thought_tags=True)."""
    client = FakeChatClient([fake_ai("<thought>nghĩ ngợi</thought>Chào bạn!")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    assert r.invoke("chitchat", MSGS).message.content == "Chào bạn!"


def test_khong_go_gi_voi_model_khong_nha_thought(clock):
    """read chạy gemini (emits_thought_tags=False) — nội dung giữ nguyên."""
    client = FakeChatClient([fake_ai("Thẻ <thought> nghĩa là gì?")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    assert r.invoke("read", MSGS).message.content == "Thẻ <thought> nghĩa là gì?"


def test_tool_duoc_bind_vao_client(clock):
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    client = FakeChatClient([fake_ai("ok")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    r.invoke("read", MSGS, tools=tools)
    assert client.bound_tools == tools


def test_ghim_khong_tut_khi_loi_ma_nem_thang_ra(clock):
    """Ghim là ghim — kể cả khi hỏng. Tụt lặng lẽ làm hỏng phép đo eval."""
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: hong)
    with pytest.raises(ChainExhausted):
        r.invoke("read", MSGS, pin="or-nemotron")
    assert len(hong.calls) == 1


async def test_ainvoke_hoat_dong_giong_invoke(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    got = await r.ainvoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."


async def test_ainvoke_cung_tut_mat_xich_khi_429(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    got = await r.ainvoke("read", MSGS)
    assert got.decision.spec.alias == "groq-llama-3.3-70b"
```

- [ ] **Bước 3: Viết phần `invoke` của `router.py`**

Bổ sung `import` ở **đầu file** `backend/src/llm/router.py` (dòng
`from .providers import client_for` đã có từ Task 8 — mở rộng nó), rồi thêm
phần thân bên dưới. **Không định nghĩa lại `__init__`** — Task 8 đã khai đủ
`_client_factory` và `_clients`.

```python
from .providers import client_for, strip_thought      # mở rộng import cũ
from .tokens import estimate_base_tokens

# 429 nghỉ lâu hơn lỗi khác: hạn mức hồi theo phút/ngày, còn 5xx với timeout
# thường là sự cố thoáng qua vài giây.
COOLDOWN_RATE_LIMIT_S = 60.0
COOLDOWN_ERROR_S = 15.0


@dataclass(frozen=True)
class AttemptError:
    alias: str
    error: str


@dataclass(frozen=True)
class InvokeResult:
    message: object                 # AIMessage, content đã được scrub
    decision: RouteDecision
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    attempts: tuple[AttemptError, ...]   # các mắt xích đã thử và hỏng
```

Rồi thêm các phương thức sau vào lớp `Router` đã có:

```python
    def _client(self, spec: ModelSpec, tools):
        # Cache theo alias: dựng lại client mỗi lượt là lãng phí (dù là
        # ChatOpenAI hay ChatGoogleGenerativeAI — client_for() trả loại nào
        # tuỳ provider, xem Task 7), mà tools thì
        # đổi theo lượt nên bind_tools() gọi lại mỗi lần (nó trả về bản bọc
        # mới, không sửa client gốc).
        if spec.alias not in self._clients:
            self._clients[spec.alias] = self._client_factory(spec)
        client = self._clients[spec.alias]
        return client.bind_tools(tools) if tools else client

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 429 or "429" in str(exc)

    def _cooldown_for(self, spec: ModelSpec, exc: Exception) -> None:
        seconds = (COOLDOWN_RATE_LIMIT_S if self._is_rate_limit(exc)
                   else COOLDOWN_ERROR_S)
        self._ledger.cooldown(spec, seconds)
        logger.warning("%s hỏng (%s) — nghỉ %.0fs", spec.alias, exc, seconds)

    @staticmethod
    def _usage(response) -> tuple[int, int, int]:
        """Rút (prompt, completion, total) — LẤY total THÔ CỦA PROVIDER.

        BẪY: một số phiên bản LangChain tự tính lại total = input + output khi
        dựng usage_metadata. Với họ Gemma đó đúng là con số đếm thiếu 7 lần
        (đo 2026-07-28: p=11, c=36 nhưng provider báo total=337 — ~290 token
        "thinking" không nằm trong completion_tokens). Nên ưu tiên
        response_metadata["token_usage"], nơi giữ nguyên khối usage thô.
        """
        raw = (getattr(response, "response_metadata", None) or {}).get(
            "token_usage") or {}
        if raw:
            prompt = int(raw.get("prompt_tokens") or 0)
            completion = int(raw.get("completion_tokens") or 0)
            total = int(raw.get("total_tokens") or (prompt + completion))
            return prompt, completion, total
        meta = getattr(response, "usage_metadata", None) or {}
        prompt = int(meta.get("input_tokens") or 0)
        completion = int(meta.get("output_tokens") or 0)
        return prompt, completion, int(meta.get("total_tokens") or
                                       (prompt + completion))

    def _finish(self, decision: RouteDecision, response,
                attempts: list[AttemptError]) -> InvokeResult:
        if decision.spec.emits_thought_tags:
            response.content = strip_thought(response.content)
        prompt, completion, total = self._usage(response)
        self._ledger.record(decision.spec, prompt_tokens=prompt,
                            completion_tokens=completion, total_tokens=total)
        return InvokeResult(message=response, decision=decision,
                            prompt_tokens=prompt, completion_tokens=completion,
                            total_tokens=total, attempts=tuple(attempts))

    def _max_attempts(self, role: str, pin: str | None) -> int:
        # Ghim thì thử đúng một lần: ghim là ghim, kể cả khi hỏng. Tụt lặng lẽ
        # sẽ làm hỏng phép đo eval mà không báo gì (spec §2).
        return 1 if pin is not None else len(chain_for(role))

    def invoke(self, role: str, messages: list, tools: list | None = None,
               pin: str | None = None) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = self._client(decision.spec, tools).invoke(messages)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))

    async def ainvoke(self, role: str, messages: list,
                      tools: list | None = None,
                      pin: str | None = None) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = await self._client(
                    decision.spec, tools).ainvoke(messages)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

Vòng lặp `invoke` và `ainvoke` giống nhau tới 90%, và **cố ý không gộp**: gộp
lại sẽ phải chạy nhánh đồng bộ qua executor hoặc dựng một lớp trừu tượng
async/sync, cả hai đều đắt hơn nhiều so với việc đọc song song hai vòng lặp
mười dòng.

Lưu ý cách tụt mắt xích: **không có tham số `exclude`**. Mắt xích vừa hỏng bị
`_cooldown_for()` đặt nghỉ, nên vòng sau `resolve()` tự bỏ qua nó qua đúng
đường `Verdict.COOLDOWN` đã có. Một cơ chế, không phải hai.

- [ ] **Bước 4: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_router_invoke.py -v`
Kỳ vọng: 13 test PASS

Rồi chạy lại toàn bộ: `python -m pytest -m "not integration and not live" -v`

- [ ] **Bước 5: Commit**

```bash
git add backend/src/llm/router.py backend/tests/llm/conftest.py \
        backend/tests/llm/test_router_invoke.py
git commit -m "feat(llm): Router.invoke/ainvoke — cooldown + tụt mắt xích

Tụt mắt xích không cần tham số exclude: mắt xích hỏng bị đặt cooldown, nên
resolve() vòng sau tự bỏ qua nó qua đúng đường Verdict.COOLDOWN đã có.

_usage() lấy total THÔ từ response_metadata['token_usage'], KHÔNG lấy
usage_metadata: một số phiên bản LangChain tự tính lại total = input + output,
mà với họ Gemma đó đúng là con số đếm thiếu 7 lần.

429 nghỉ 60s, lỗi khác nghỉ 15s. Ghim thì thử đúng một lần rồi ném."
```

---

### Task 10: `RoutedChatModel` + `make_llms()` — mặt tiền tương thích

Đây là task làm cho kế hoạch B rẻ đi. Code `agents/` ở repo nguồn gọi
`self._llms["read"].invoke(...)` với object dựng sẵn **một lần**. Nhưng ngân
sách đổi theo từng lượt, nên không dựng sẵn được.

Giải: `RoutedChatModel` là một `Runnable` của LangChain, **giải quyết model tại
thời điểm invoke**. `make_llms()` trả dict vai → `RoutedChatModel`, đúng hình
dạng `make_llms()` cũ trả về. Nhờ vậy toàn bộ `agents/` port sang **không phải
sửa dòng nào** ở chỗ gọi LLM.

Quyết định ghi trong sổ vẫn treo ở lượt gọi được — mỗi lượt invoke thật vẫn đi
qua `Router.invoke()` nên vẫn được kế toán và vẫn tụt mắt xích.

**Files:**
- Modify: `backend/src/llm/router.py` (thêm vào cuối)
- Create: `backend/src/llm/__init__.py` (xuất API công khai)
- Test: `backend/tests/llm/test_routed_chat_model.py`

**Interfaces:**
- Consumes: `Router.invoke` / `.ainvoke`, `InvokeResult` (Task 9);
  `PostgresUsageStore` (Task 6); `BudgetLedger` (Task 5); `ROLES` (Task 2)
- Produces: `RoutedChatModel`, `make_llms()`, `build_router()` — kế hoạch B và
  C dùng làm điểm vào duy nhất của tầng LLM

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/llm/test_routed_chat_model.py`:

```python
import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable

from src.llm.budget import BudgetLedger
from src.llm.catalog import ROLES
from src.llm.router import Router, RoutedChatModel, make_llms
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import FakeChatClient, FakeRateLimit, fake_ai

MSGS = [HumanMessage("Tồn kho ABC?")]


def _router(clock, client):
    return Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                  client_factory=lambda spec: client)


def test_la_mot_Runnable_that(clock):
    """Graph LangGraph bind nó vào node, nên nó phải là Runnable thật."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read")
    assert isinstance(llm, Runnable)


def test_invoke_tra_ve_AIMessage_chu_khong_phai_InvokeResult(clock):
    """Chỗ gọi ở agents/ mong nhận AIMessage — hợp đồng cũ phải giữ nguyên."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai("Còn 42.")])),
                          "read")
    got = llm.invoke(MSGS)
    assert got.content == "Còn 42."
    assert hasattr(got, "type")


async def test_ainvoke_cung_tra_ve_AIMessage(clock):
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai("Còn 42.")])),
                          "read")
    got = await llm.ainvoke(MSGS)
    assert got.content == "Còn 42."


def test_bind_tools_giu_lai_tool_cho_luot_invoke(clock):
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    llm.bind_tools(tools).invoke(MSGS)
    assert client.bound_tools == tools


def test_bind_tools_tra_ve_ban_MOI_khong_sua_ban_goc(clock):
    """Khớp ngữ nghĩa bind_tools của LangChain — bản gốc phải sạch."""
    client = FakeChatClient([fake_ai("ok"), fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    llm.bind_tools([{"type": "function", "function": {"name": "get_stock"}}])
    llm.invoke(MSGS)                      # bản gốc: không bind tool nào
    assert client.bound_tools is None


def test_quyet_dinh_dinh_tuyen_cua_luot_cuoi_lay_lai_duoc(clock):
    """Kế hoạch C cần nó để đổ thuộc tính vào span Langfuse."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "gemini-3.5-flash-lite"
    assert llm.last_decision.fallback_depth == 0


def test_ghim_truyen_xuong_router(clock):
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read",
                          pin="or-nemotron")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "or-nemotron"


def test_van_tut_mat_xich_qua_lop_boc(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    by_alias = {"gemini-3.5-flash-lite": hong, "groq-llama-3.3-70b": tot}
    router = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                    client_factory=lambda spec: by_alias[spec.alias])
    llm = RoutedChatModel(router, "read")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "groq-llama-3.3-70b"


def test_make_llms_tra_ve_du_moi_vai(clock):
    llms = make_llms(_router(clock, FakeChatClient([fake_ai()])))
    assert set(llms) == set(ROLES)
    assert all(isinstance(v, RoutedChatModel) for v in llms.values())


def test_make_llms_nhan_ghim_theo_tung_vai(clock):
    """Đường eval ghim từng vai một để đo đúng một model."""
    llms = make_llms(_router(clock, FakeChatClient([fake_ai()])),
                     pins={"read": "or-nemotron"})
    llms["read"].invoke(MSGS)
    assert llms["read"].last_decision.spec.alias == "or-nemotron"
    llms["chitchat"].invoke(MSGS)
    assert llms["chitchat"].last_decision.spec.alias == "gemma-4-31b"
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Chạy: `cd backend && python -m pytest tests/llm/test_routed_chat_model.py -v`
Kỳ vọng: FAIL với `ImportError: cannot import name 'RoutedChatModel'`

- [ ] **Bước 3: Viết `RoutedChatModel` và `make_llms`**

Thêm vào **cuối** `backend/src/llm/router.py`:

```python
from langchain_core.runnables import Runnable

from .catalog import ROLES
from .store import PostgresUsageStore


class RoutedChatModel(Runnable):
    """Mặt tiền giữ nguyên hợp đồng cũ của agents/.

    Code agents/ ở repo nguồn gọi self._llms["read"].invoke(...) với object
    dựng sẵn MỘT LẦN. Ngân sách thì đổi theo từng lượt, nên không dựng sẵn
    được — lớp này giải quyết model TẠI THỜI ĐIỂM INVOKE, giấu chuyện đó đi.
    Nhờ vậy toàn bộ agents/ port sang không phải sửa dòng nào ở chỗ gọi LLM.

    Trả về AIMessage chứ không phải InvokeResult: hợp đồng cũ là AIMessage, và
    đổi nó sẽ lan ra khắp agents/. Quyết định định tuyến lấy lại qua
    .last_decision (kế hoạch C đổ nó vào span Langfuse).
    """

    def __init__(self, router: "Router", role: str, tools: list | None = None,
                 pin: str | None = None) -> None:
        self._router = router
        self._role = role
        self._tools = tools
        self._pin = pin
        self.last_decision: RouteDecision | None = None

    def bind_tools(self, tools: list, **kwargs) -> "RoutedChatModel":
        # Trả bản MỚI, không sửa bản gốc — khớp ngữ nghĩa bind_tools của
        # LangChain. Bản mới dùng chung router nên dùng chung sổ ngân sách.
        return RoutedChatModel(self._router, self._role, tools, self._pin)

    def invoke(self, input, config=None, **kwargs):
        result = self._router.invoke(self._role, input, tools=self._tools,
                                     pin=self._pin)
        self.last_decision = result.decision
        return result.message

    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._router.ainvoke(self._role, input,
                                            tools=self._tools, pin=self._pin)
        self.last_decision = result.decision
        return result.message


def build_router(store=None, clock=None) -> Router:
    """Router cho đường chạy thật. Mặc định dùng sổ Postgres."""
    return Router(BudgetLedger(store or PostgresUsageStore(), clock=clock))


def make_llms(router: Router,
              pins: dict[str, str] | None = None) -> dict[str, RoutedChatModel]:
    """dict vai → model, đúng hình dạng make_llms() cũ của repo nguồn.

    pins: ghim từng vai, dùng cho đường eval — eval phải đo MỘT MODEL chứ
    không phải một trạng thái ngân sách (spec §2).
    """
    pins = pins or {}
    return {role: RoutedChatModel(router, role, pin=pins.get(role))
            for role in ROLES}
```

- [ ] **Bước 4: Xuất API công khai**

`backend/src/llm/__init__.py`:

```python
"""Tầng LLM — điểm vào DUY NHẤT cho mọi thứ liên quan nhà cung cấp mô hình.

Không tầng nào khác (agents/, erp_query/, rag/) được import trực tiếp
providers.py hay catalog.py; chúng đi qua đây.
"""
from .budget import BudgetLedger, Verdict
from .catalog import CATALOG, CHAINS, ROLES, ModelSpec, chain_for, spec_for
from .router import (ChainExhausted, InvokeResult, RouteDecision,
                     RoutedChatModel, Router, SkippedLink, build_router,
                     make_llms)
from .store import InMemoryUsageStore, PostgresUsageStore, Usage

__all__ = [
    "BudgetLedger", "Verdict", "CATALOG", "CHAINS", "ROLES", "ModelSpec",
    "chain_for", "spec_for", "ChainExhausted", "InvokeResult", "RouteDecision",
    "RoutedChatModel", "Router", "SkippedLink", "build_router", "make_llms",
    "InMemoryUsageStore", "PostgresUsageStore", "Usage",
]
```

- [ ] **Bước 5: Chạy test để chắc chắn nó xanh**

Chạy: `cd backend && python -m pytest tests/llm/test_routed_chat_model.py -v`
Kỳ vọng: 10 test PASS

Rồi toàn bộ: `python -m pytest -m "not integration and not live" -v`

- [ ] **Bước 6: Commit**

```bash
git add backend/src/llm/router.py backend/src/llm/__init__.py \
        backend/tests/llm/test_routed_chat_model.py
git commit -m "feat(llm): RoutedChatModel + make_llms — mặt tiền tương thích

agents/ gọi llms['read'].invoke(...) với object dựng sẵn một lần, nhưng ngân
sách đổi theo từng lượt. RoutedChatModel là Runnable giải quyết model TẠI THỜI
ĐIỂM INVOKE, nên agents/ port sang không phải sửa chỗ gọi LLM nào.

Trả AIMessage chứ không phải InvokeResult (giữ hợp đồng cũ); quyết định định
tuyến lấy qua .last_decision cho span Langfuse ở kế hoạch C.

make_llms(pins=...) ghim từng vai cho đường eval."
```

---

### Task 11: Contract test có mạng + ranh giới tầng + `provider-quotas.md`

Ba việc khép lại kế hoạch A.

**Contract test** là thứ bắt được chuyện xảy ra ngoài tầm kiểm soát của repo:
nhà cung cấp khai tử một model free (thường là lặng lẽ), hoặc đổi hành vi trả
về. Chúng chính là các phép đo tay ngày 2026-07-28 được đóng gói lại để chạy
lại được.

**Test ranh giới** ép quy tắc phụ thuộc một chiều ở §1 — thứ mà chỉ có lời dặn
trong tài liệu thì sáu tháng nữa sẽ bị vi phạm.

**Files:**
- Create: `backend/tests/llm/test_live_providers.py`
- Create: `backend/tests/llm/test_boundaries.py`
- Create: `docs/provider-quotas.md`
- Modify: `backend/requirements.txt` (thêm `httpx`)

**Interfaces:**
- Consumes: toàn bộ `src/llm/` từ Task 2–10
- Produces: không có API mới — đây là task kiểm chứng và tài liệu

- [ ] **Bước 1: Viết test ranh giới tầng**

`backend/tests/llm/test_boundaries.py`:

```python
"""Ép quy tắc phụ thuộc một chiều của spec §1.

src/llm/ KHÔNG được biết gì về ERP, RAG, Odoo. Nhờ vậy nó test được bằng
provider giả mà không cần Odoo hay Postgres — và nhờ vậy nó dùng lại được
nguyên vẹn khi SP-2 dựng orchestrator.
"""
import pathlib

LLM_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "llm"

CAM = ("src.agents", "src.erp_query", "src.rag",
       "from ..agents", "from ..erp_query", "from ..rag")


def test_tang_llm_khong_import_tang_nghiep_vu():
    vi_pham = []
    for path in sorted(LLM_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for cam in CAM:
            if cam in text:
                vi_pham.append(f"{path.name} tham chiếu {cam!r}")
    assert not vi_pham, "\n".join(vi_pham)


def test_khong_co_khoa_api_nao_bi_hardcode():
    """Khoá chỉ đến từ biến môi trường (spec §9).

    Dò theo HÌNH DẠNG, cố ý không nhúng tiền tố khoá thật của bất kỳ ai: một
    chuỗi dài gán thẳng vào biến có tên nghe như khoá. Nhúng mảnh khoá thật vào
    test là tự tạo ra chính thứ mình đang đi tìm.
    """
    import re

    nghi_ngo = re.compile(
        r"""(?i)(api[_-]?key|secret|token)\s*=\s*["'][A-Za-z0-9_\-.]{20,}["']""")
    for path in sorted(LLM_DIR.glob("*.py")):
        m = nghi_ngo.search(path.read_text(encoding="utf-8"))
        assert not m, f"{path.name}: có vẻ hardcode khoá — {m.group(0)[:40]}"
```

- [ ] **Bước 2: Viết contract test có mạng**

Thêm `httpx` vào `backend/requirements.txt` (nó vốn đã đi kèm `openai`, khai
báo tường minh cho rõ phụ thuộc).

`backend/tests/llm/test_live_providers.py`:

```python
"""Contract test — CẦN MẠNG và API key thật.

Chạy:  pytest tests/llm/test_live_providers.py -m live -v
Bỏ:    pytest -m "not live"

Đây là các phép đo tay ngày 2026-07-28 được đóng gói để chạy lại được. Chúng
bắt thứ nằm ngoài tầm kiểm soát của repo: nhà cung cấp khai tử model free
(thường lặng lẽ), hoặc đổi hình dạng response.

TIÊU HAO HẠN MỨC: mỗi lần chạy tốn vài lượt gọi thật. Gemini Flash không-Lite
chỉ có 20 lượt/ngày, nên KHÔNG thêm test nào chạm vào nhóm đó.
"""
import json
import os

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.llm.catalog import CATALOG
from src.llm.providers import BASE_URLS, ENV_KEYS, client_for

pytestmark = pytest.mark.live


@tool
def get_stock(product: str) -> str:
    """Tra tồn kho theo tên sản phẩm."""
    return json.dumps({"product": product, "on_hand": 42}, ensure_ascii=False)


def _skip_neu_thieu_key(provider: str) -> None:
    if not os.environ.get(ENV_KEYS[provider]):
        pytest.skip(f"chưa đặt {ENV_KEYS[provider]}")


# ─── Tool-calling qua cả ba nhà ─────────────────────────────────────────────

@pytest.mark.parametrize("alias", [
    "gemini-3.5-flash-lite", "groq-gpt-oss-20b", "or-nemotron",
])
def test_tool_calling_hoat_dong_voi_tieng_viet(alias):
    spec = CATALOG[alias]
    _skip_neu_thieu_key(spec.provider)
    response = client_for(spec).bind_tools([get_stock]).invoke(
        [HumanMessage("Tồn kho sản phẩm ABC còn bao nhiêu?")])
    assert response.tool_calls, f"{alias} không gọi tool"
    assert response.tool_calls[0]["name"] == "get_stock"


# ─── Vòng lặp tool 2 lượt qua Google (canh gác thought_signature) ────────────

def test_vong_lap_tool_hai_luot_qua_google_van_hoi_tu():
    """Canh gác hồi quy cho rủi ro §12. Nếu test này đỏ, đọc lại
    docs/spikes/2026-07-28-thought-signature.md — có thể phải đổi client Google
    sang langchain-google-genai."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemini-3.5-flash-lite"]
    bound = client_for(spec).bind_tools([get_stock])
    messages = [HumanMessage("Tồn kho sản phẩm ABC còn bao nhiêu?")]

    ai = bound.invoke(messages)
    assert ai.tool_calls
    messages.append(ai)
    for tc in ai.tool_calls:
        messages.append(ToolMessage(content=get_stock.invoke(tc["args"]),
                                    tool_call_id=tc["id"]))

    cuoi = bound.invoke(messages)
    assert not cuoi.tool_calls, "không hội tụ — vẫn còn đòi gọi tool"
    assert "42" in (cuoi.content or ""), "không dùng kết quả tool trong câu trả lời"


# ─── Lý do tồn tại của strip_thought vẫn còn đúng ───────────────────────────

def test_gemma_van_nha_thought_vao_content():
    """Nếu Google sửa endpoint để tách thinking ra, test này đỏ — và đó là tin
    TỐT: lúc đó strip_thought() thành thừa và nên gỡ bỏ, chứ không phải để lại
    một cú scrub không ai hiểu vì sao còn ở đó."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    assert "<thought>" in (response.content or ""), (
        "Gemma không còn nhả <thought> — cân nhắc gỡ strip_thought() và cờ "
        "emits_thought_tags")


def test_gemma_van_dem_thieu_token_neu_cong_prompt_va_completion():
    """Lý do tồn tại của quy tắc 'total_tokens là con số có thẩm quyền'."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    usage = response.response_metadata["token_usage"]
    tong_phan = usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["total_tokens"] > tong_phan * 2, (
        f"total={usage['total_tokens']} không còn lớn hơn hẳn p+c={tong_phan} "
        "— cân nhắc xem lại quy tắc total_tokens trong budget.py")


# ─── Catalog không trôi khỏi thực tế ────────────────────────────────────────

def _ids_google() -> set[str]:
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  params={"key": os.environ["GOOGLE_API_KEY"], "pageSize": 300},
                  timeout=30)
    r.raise_for_status()
    return {m["name"].removeprefix("models/") for m in r.json()["models"]}


def _ids_openai_compat(provider: str) -> set[str]:
    r = httpx.get(f"{BASE_URLS[provider].rstrip('/')}/models",
                  headers={"Authorization":
                           f"Bearer {os.environ[ENV_KEYS[provider]]}"},
                  timeout=30)
    r.raise_for_status()
    return {m["id"] for m in r.json()["data"]}


@pytest.mark.parametrize("provider", ["google", "groq", "openrouter"])
def test_moi_model_id_trong_catalog_van_con_ton_tai(provider):
    """Bắt được lúc nhà cung cấp khai tử một model free — thường lặng lẽ."""
    _skip_neu_thieu_key(provider)
    thuc_te = (_ids_google() if provider == "google"
               else _ids_openai_compat(provider))
    thieu = [s.model_id for s in CATALOG.values()
             if s.provider == provider and s.model_id not in thuc_te]
    assert not thieu, (
        f"{provider} không còn các model sau: {thieu} — cập nhật catalog.py "
        f"VÀ docs/provider-quotas.md")
```

- [ ] **Bước 3a: Viết `docs/provider-quotas.md`**

Bảng hạn mức là **dữ kiện thiết kế** — `catalog.py` phải khớp với nó — nên nó
thuộc về file tracked (standing rule ADR-010). Chép nội dung từ Phụ lục A của
spec, **không kèm khoá nào**, và mở đầu bằng:

```markdown
# Hạn mức nhà cung cấp (free tier)

> Đo ngày 2026-07-28. Đây là DỮ KIỆN THIẾT KẾ, không phải ghi chú tham khảo:
> `backend/src/llm/catalog.py` phải khớp bảng này. Sửa một nơi thì sửa cả hai.
> Contract test `test_moi_model_id_trong_catalog_van_con_ton_tai` bắt được lúc
> model biến mất, nhưng KHÔNG bắt được lúc con số hạn mức đổi — chỗ đó vẫn cần
> mắt người.
>
> KHÔNG đặt API key vào file này. Khoá nằm ở `.env` (đã gitignore).
```

Rồi ba bảng: hạn mức từng model, hành vi `<thought>` + kế toán token, và danh
sách `model_id` đã xác nhận — chép nguyên từ spec Phụ lục A.

- [ ] **Bước 3b: Viết `docs/ADR-011-sp1-foundation.md`**

Spec Phụ lục B đòi file này, và nó là **thứ duy nhất trong kế hoạch A còn sống
sau khi spec và plan hết hạn dùng**. ADR ghi *đã quyết gì và vì sao*; spec/plan
ghi *làm thế nào*. Một phiên tương lai clone repo về phải đọc được cái thứ nhất
mà không cần cái thứ hai — đúng vai trò ADR-010 đã đóng cho phiên này.

Giữ ngắn. Mỗi mục **một đoạn**: quyết định, lý do, và trỏ tới điểm code hoặc
phép đo. Bảy mục:

1. **SP-1 thay thế QĐ M2 của ADR-009 có chủ đích** — bỏ Ollama khỏi đường chat
   nên 4 vai mang dữ liệu không còn chỗ nào ngoài cloud. Lý do chấp nhận: dữ
   liệu Odoo là dữ liệu demo, project là demo/portfolio (chủ dự án xác nhận
   2026-07-28). Kèm dữ kiện: tier trả phí của Anthropic/OpenAI mặc định không
   dùng dữ liệu API để huấn luyện, còn free tier Google AI Studio thì có — nên
   ranh giới "free demo giờ / trả phí thật sau" là ranh giới đúng.
2. **Bỏ LiteLLM** — cả 3 nhà đã OpenAI-compatible (đo 2026-07-28) nên giá trị
   hợp nhất giao thức bốc hơi; bài toán thật là kế toán hạn mức free-tier theo
   ngày, đúng chỗ LiteLLM yếu nhất.
3. **Langfuse self-host, không dùng Cloud** — trace là kho lưu trữ tập trung,
   tìm kiếm được, tồn tại lâu dài, khác loại rủi ro với lời gọi API thoáng qua;
   và hạn mức observation sẽ cắn đúng lúc SP-3 chạy tải fan-out.
4. **Loại NVIDIA NeMo Guardrails** — rail của nó chạy bằng cách gọi thêm LLM,
   tức nhân ba mức tiêu thụ tài nguyên hiếm nhất; và nó xác suất trong khi
   `agentic_gate` đã làm tool ghi *bất khả đạt*. Khoảng trống thật (prompt
   injection ở input và ở chunk RAG) giao cho SP-2 bằng
   `meta-llama/llama-prompt-guard-2-*` trên Groq.
5. **Guard nào co được, guard nào không** — guard bù cho sự kém cỏi thì co lại
   được (`max_tokens=4096` của planner, timeout theo `is_qwen`); guard ràng
   buộc thẩm quyền thì không (`write_gate`, `agentic_gate`, denylist gateway).
   Model mạnh hơn là model giỏi hơn trong việc tìm đường đi chưa lường tới.
6. **`fusion` giữ qua SP-1, bỏ ở SP-2** — nguyên tắc một-biến. SP-1 chạy
   `multi_source` hai lượt để SP-2 quyết định gộp nhánh bằng số liệu.
7. **Đính chính ADR-010** — ADR-010 viết "summarization cho meeting agent giao
   Groq (nhanh với văn bản dài)". Với trần 8K TPM, một transcript họp dài không
   lọt nổi một request. Việc của SP-4, nhưng ghi lại ngay để không đi theo giả
   định sai. Ghi kèm: Groq host sẵn `whisper-large-v3` — có thể bỏ luôn nhu cầu
   GPU cục bộ cho meeting agent.

- [ ] **Bước 4: Chạy test ranh giới (không cần mạng)**

Chạy: `cd backend && python -m pytest tests/llm/test_boundaries.py -v`
Kỳ vọng: 2 test PASS

- [ ] **Bước 5: Chạy contract test (cần mạng + key)**

```bash
cd backend && python -m pytest tests/llm/test_live_providers.py -m live -v
```

Kỳ vọng: 9 test PASS (3 tool-calling + vòng lặp 2 lượt + 2 hành vi Gemma +
3 kiểm catalog).

Nếu `test_vong_lap_tool_hai_luot_qua_google_van_hoi_tu` đỏ thì **dừng lại** —
đó chính là rủi ro §12 xảy ra thật, và đường lui đã ghi ở Task 1.

- [ ] **Bước 6: Chạy toàn bộ, xác nhận kế hoạch A xong**

```bash
cd backend && python -m pytest -m "not integration and not live" -v
python -m pytest -m integration -v      # cần Postgres
python -m pytest -m live -v             # cần mạng + key
```

Kỳ vọng: toàn bộ xanh. Tổng khoảng 90 test.

- [ ] **Bước 7: Commit**

```bash
git add backend/tests/llm/test_live_providers.py \
        backend/tests/llm/test_boundaries.py backend/requirements.txt \
        docs/provider-quotas.md docs/ADR-011-sp1-foundation.md
git commit -m "test(llm): contract test có mạng + ranh giới tầng + bảng hạn mức

Contract test đóng gói lại các phép đo tay ngày 2026-07-28 để chạy lại được:
tool-calling qua cả 3 nhà, vòng lặp tool 2 lượt qua Google (canh gác rủi ro
thought_signature), và đối chiếu mọi model_id trong catalog với /models thật —
cái bắt được lúc nhà cung cấp khai tử model free, thường là lặng lẽ.

Hai test canh gác LÝ DO TỒN TẠI của code: nếu Gemma thôi nhả <thought> hoặc
thôi đếm thiếu token, chúng đỏ — và đó là tin tốt, nghĩa là gỡ được
strip_thought() thay vì để lại một cú scrub không ai hiểu vì sao còn đó.

test_boundaries ép quy tắc phụ thuộc một chiều của §1."
```

---

## "Kế hoạch A xong" nghĩa là

1. 11 task đều commit, toàn bộ test xanh ở cả ba chế độ:
   `-m "not integration and not live"`, `-m integration`, `-m live`
2. `docs/spikes/2026-07-28-thought-signature.md` có kết quả thật và một quyết
   định — không phải "chưa chạy"
3. `docs/ADR-011-sp1-foundation.md` và `docs/provider-quotas.md` đã tracked
4. Năm quyết định trong Global Constraints đều có bình luận tại đúng điểm code
5. `git log` không chứa khoá nào; `test_khong_co_khoa_api_nao_bi_hardcode` xanh

Cái **chưa** làm được sau kế hoạch A: chưa có đường chat nào. Tầng LLM chạy
được và đo được, nhưng chưa ai gọi nó. Đó là việc của B và C.

## Sau kế hoạch A

| | Kế hoạch | Nội dung | Phụ thuộc |
|---|---|---|---|
| **B** | Port tầng nghiệp vụ | `erp_query/` + `rag/` + security gates + chẻ MCP server theo domain; `agents/models.py` thành mặt tiền mỏng trên `llm/router.py` kèm khối bình luận supersession QĐ M2 | A (cần `make_llms`) |
| **C** | Chat path + tracing + eval | Graph lõi + FastAPI `/v1` + Langfuse `tracing.py` (đổ `RouteDecision` vào span) + eval gate 7 bộ với model ghim + `multi_source` lượt hai | A và B |

Hai chỗ kế hoạch A cố ý để lại móc sẵn cho C:

- `RouteDecision.skipped` mang lý do từng mắt xích bị bỏ qua → thuộc tính span
  trả lời "vì sao lượt này chạy Groq"
- `RoutedChatModel.last_decision` → chỗ C đọc quyết định của lượt vừa rồi
- `make_llms(pins=...)` → đường eval ghim từng vai

`tracing.py` **không** thuộc kế hoạch A dù spec §1 xếp nó trong `src/llm/`:
handler Langfuse gắn ở tầng LangGraph lúc invoke graph, mà graph thì tới C mới
có. Đưa nó vào A sẽ là code không ai gọi và không test được cho ra hồn.
