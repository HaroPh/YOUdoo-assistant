# SP-1B — Port tầng nghiệp vụ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mang `rag/`, `erp_query/`, security gates và graph lõi `agents/` từ repo nguồn `D:\Project` sang Youdoo, nối vào tầng `llm/` của kế hoạch A, chẻ MCP server Odoo theo domain — để graph trả lời được câu hỏi thật qua model cloud, chạy bằng pytest.

**Architecture:** Đồ thị phụ thuộc nông và sạch (`rag/` là lá → `erp_query/` chỉ import rag → `agents/` import cả hai), nên port từ dưới lên. `agents/models.py` co lại thành mặt tiền mỏng gọi `llm/router.make_llms()` — hai bên gọi duy nhất (`erp_agent.py`, `graph.py`) không phải sửa. MCP server là tiến trình riêng qua SSE, chẻ độc lập.

**Tech Stack:** Python 3.11+, LangGraph 1.1.10, `langchain-mcp-adapters`, `psycopg` 3 + `pgvector`, Ollama (bge-m3), `pytest`, `pytest-asyncio`.

**Spec:** [2026-07-29-sp1b-port-business-layer-design.md](../specs/2026-07-29-sp1b-port-business-layer-design.md). Spec gốc SP-1: [2026-07-28-sp1-foundation-design.md](../specs/2026-07-28-sp1-foundation-design.md) §3.

**Repo nguồn:** `D:\Project` — chỉ ĐỌC, không bao giờ sửa. Mọi lệnh `git` chạy trong `D:\Youdoo`.

## Global Constraints

- **Python 3.11+.** Dùng `X | None` chứ không `Optional[X]`.
- **Không khoá API nào trong code.** Mọi khoá đọc từ biến môi trường.
- **`src/llm/` không được import bất cứ thứ gì từ `src/agents/`, `src/erp_query/`, `src/rag/`.** Phụ thuộc một chiều. `backend/tests/llm/test_boundaries.py` (kế hoạch A) đã ép điều này — nó sẽ đỏ nếu ai vi phạm.
- **Chiều ngược lại thì được:** `agents/` import `llm/`, `erp_query/`, `rag/` là hợp lệ.
- **Bình luận trong code viết bằng tiếng Việt**, khớp lối viết repo nguồn. Tên định danh bằng tiếng Anh.
- **Test đơn vị không chạm mạng và không cần Postgres.** Test cần mạng đánh dấu `@pytest.mark.live`; test cần Postgres đánh dấu `@pytest.mark.integration`.
- **QUY TẮC PORT TEST — quan trọng nhất của kế hoạch này.** Test port sang mà đỏ:
  - vì **hạ tầng đổi** (LiteLLM → `llm/router`, qwen → catalog, đường import) → sửa phần nối dây.
  - vì **hành vi thật sự đổi** → **DỪNG LẠI, BÁO CÁO.** Không sửa test cho xanh. Một test bị sửa cho xanh là một hồi quy được ký giấy thông hành.
- **`total_tokens` là con số có thẩm quyền cho mọi phép kiểm token** (kế hoạch A). Không bao giờ cộng `prompt_tokens + completion_tokens`.
- **Ba quyết định phải có bình luận tại đúng điểm code** (spec Phụ lục B — thiếu bình luận là task chưa xong):

  | Quyết định | File |
  |---|---|
  | QĐ M2 của ADR-009 bị thay thế CÓ CHỦ ĐÍCH | `agents/models.py` (Task 8) |
  | Marker `embedding_model`/`dim` lệch → fail lớn tiếng | `rag/embed.py` (Task 5) |
  | Mọi đường ra Odoo phải qua `odoo_call.odoo()` | `mcp-servers/odoo/odoo_call.py` (Task 7) |

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/llm/router.py` | **Sửa** — chuẩn hoá `.content`, `last_decision` an toàn đa luồng, chuyển tiếp `config` |
| `backend/src/rag/` | 10 file: `config`, `types`, `db`, `chunking`, `parse`, `ingest`, `retrieve`, `reranker`, `embed`, `__init__` |
| `backend/src/erp_query/` | 15 file: `gateway` (4 guard), `transport`, 6 module domain, `tools`, `resolve`, `semantic`, `envelope`, `sync_index`, `eval_resolve`, `schema.sql` |
| `backend/src/agents/` | Graph lõi + gates + write node. `models.py` là mặt tiền mỏng |
| `mcp-servers/odoo/odoo_call.py` | Hàm `odoo()` — 5 cổng bảo mật, cửa DUY NHẤT ra Odoo |
| `mcp-servers/odoo/tools/*.py` | 6 module theo domain — đường biên SP-2 sẽ dùng |
| `docker-compose.yml` | postgres+pgvector, ollama. KHÔNG có litellm/open-webui |

**Ánh xạ đường dẫn:** `D:\Project\backend\src\X` → `D:\Youdoo\backend\src\X`; `D:\Project\backend\tests\X` → `D:\Youdoo\backend\tests\X`; `D:\Project\mcp-servers\odoo` → `D:\Youdoo\mcp-servers\odoo`. Cấu trúc giống hệt, chỉ đổi gốc.

---

## Interfaces — bảng tra nhanh

Người triển khai một task chỉ nhìn thấy task của mình. Đây là chỗ họ học tên và kiểu của các task lân cận.

```python
# llm/router.py — ĐÃ CÓ từ kế hoạch A, Task 2 sửa
class Router:
    def __init__(self, ledger: BudgetLedger, client_factory=client_for) -> None
    def resolve(self, role: str, base_tokens: int, pin: str | None = None) -> RouteDecision
    def invoke(self, role, messages, tools=None, pin=None,
               config=None, tool_kwargs=None, **kwargs) -> InvokeResult   # chữ ký MỚI sau Task 2
    async def ainvoke(self, role, messages, tools=None, pin=None,
                      config=None, tool_kwargs=None, **kwargs) -> InvokeResult

class RoutedChatModel(Runnable):
    def __init__(self, router, role, tools=None, pin=None, tool_kwargs=None) -> None
    def bind_tools(self, tools: list, **kwargs) -> "RoutedChatModel"
    last_decision: RouteDecision | None      # sau Task 2 là @property đọc ContextVar

def build_router(store=None, clock=None) -> Router
def make_llms(router: Router, pins: dict[str, str] | None = None) -> dict[str, RoutedChatModel]

# agents/models.py — SAU Task 8 chỉ còn hai thứ
def make_llms() -> dict[str, RoutedChatModel]      # KHÔNG tham số, khác make_llms của router
def llms_from_single(llm) -> dict                  # back-compat test

# rag/embed.py — SAU Task 5
class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dim(self) -> int: ...

class OllamaEmbedder:  ...      # bge-m3, 1024-dim, BẬT mặc định
class GeminiEmbedder:  ...      # viết sẵn, TẮT
def get_embedder() -> Embedder
def assert_embedding_marker(conn) -> None    # lệch → RuntimeError lúc khởi động
```

**Điểm dễ sai:** `agents.models.make_llms()` gọi **không tham số** (giữ hợp đồng cũ của `erp_agent.py`), còn `llm.router.make_llms(router, pins=None)` cần router. Hai hàm khác nhau, cùng tên, khác module.

---

### Task 1: Spike — đo cái gì vỡ khi đổi qwen3:8b → cloud

Task này **vứt đi**. Đầu ra là HIỂU BIẾT ghi vào một file docs, không phải code chạy được.

Lý do đứng trước mọi thứ: toàn bộ prompt, ngưỡng, và cách xử lý đầu ra của `agents/` được hiệu chỉnh cho qwen3:8b local. Kế hoạch A đã tìm ra một chỗ vỡ chắc chắn bằng cách ĐỌC MÃ NGUỒN THƯ VIỆN, không phải bằng cách chạy: `langchain_google_genai` có nhánh `_is_gemini_3_or_later()` khớp tiền tố `"gemini-3"` — đúng với cả `gemini-3.5-flash-lite` lẫn `gemini-3.1-flash-lite` — và trên nhánh đó `.content` là **list** các khối `{"type": "text", ...}` chứ không phải string. Hai model này đứng đầu 4/7 chuỗi vai. Còn bao nhiêu chỗ cùng loại thì chưa ai biết.

**Files:**
- Create: `docs/spikes/2026-07-29-port-cloud-model.md`
- Scratch (KHÔNG commit): `backend/spikes/spike_port_smoke.py`

**Interfaces:**
- Consumes: `llm/router.py` (kế hoạch A), mã nguồn chỉ-đọc ở `D:\Project`
- Produces: quyết định chi phối Task 2 và Task 9–13

- [ ] **Bước 1: Dựng script spike**

`backend/spikes/spike_port_smoke.py`. Script này KHÔNG import từ `D:\Project` (khác repo, khác venv) — nó **chép prompt thật** ra rồi bắn qua `llm/router.py` của Youdoo, để xem model cloud trả về hình dạng gì.

Script **tự rút prompt thật** từ `D:\Project\backend\src\agents\prompts.py` bằng AST — không chép tay, không viết lại theo trí nhớ. Ba prompt cần đã kiểm chứng là hằng chuỗi thường (không phải f-string) nên `ast.Constant` lấy được:

| Hằng | Vai | Kích thước | Hình dạng đầu ra |
|---|---|---|---|
| `INTENT_ROUTER_PROMPT` | `router` | 935 ký tự | nhãn phân loại một từ |
| `WRITE_PLANNER_PROMPT` | `planner` | 7426 ký tự | JSON — vai có `max_tokens=4096` hardcode |
| `RAG_SYNTHESIS_PROMPT` | `synthesis` | 1168 ký tự | văn xuôi có trích dẫn |

Dùng AST chứ không `import` vì `prompts.py` có `from .working_context import ORDER_MODELS` — import nó ngoài package sẽ vỡ, mà AST thì không chạy code nào.

```python
"""Spike Task 1 — đo hình dạng đầu ra model cloud với prompt hiệu chỉnh cho qwen3:8b.

VỨT ĐI sau khi ghi kết quả vào docs/spikes/2026-07-29-port-cloud-model.md.
KHÔNG commit file này.

Chạy:  cd backend && python spikes/spike_port_smoke.py
Cần:   GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY trong môi trường
"""
import ast
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm.budget import BudgetLedger
from src.llm.router import Router
from src.llm.store import InMemoryUsageStore

PROMPTS_NGUON = pathlib.Path(r"D:\Project\backend\src\agents\prompts.py")


def rut_prompt() -> dict[str, str]:
    """Rút hằng prompt bằng AST — KHÔNG chép tay, KHÔNG import.

    Không import được vì prompts.py có `from .working_context import
    ORDER_MODELS`, mà import tương đối ngoài package thì vỡ. AST không chạy code
    nào nên tránh luôn cả việc phải dựng giả module.

    Chỉ lấy hằng chuỗi thường; SYSTEM_PROMPT là f-string nên không lấy được và
    cũng không cần.
    """
    cay = ast.parse(PROMPTS_NGUON.read_text(encoding="utf-8"))
    ra = {}
    for node in cay.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for dich in node.targets:
                if isinstance(dich, ast.Name) and isinstance(node.value.value, str):
                    ra[dich.id] = node.value.value
    return ra


CAU_HOI = "Tồn kho sản phẩm ABC còn bao nhiêu?"


def _mo_ta(x) -> str:
    """Mô tả CHÍNH XÁC kiểu dữ liệu — đây là thứ spike cần biết."""
    if isinstance(x, list):
        return f"list[{len(x)}] các phần tử kiểu {[type(i).__name__ for i in x]}"
    return f"{type(x).__name__} dài {len(x) if hasattr(x, '__len__') else '?'}"


async def do_mot_vai(router: Router, vai: str, prompt: str) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [SystemMessage(prompt), HumanMessage(CAU_HOI)]
    ket_qua = await router.ainvoke(vai, messages)
    msg = ket_qua.message
    return {
        "vai": vai,
        "alias": ket_qua.decision.spec.alias,
        "provider": ket_qua.decision.spec.provider,
        "kieu_content": _mo_ta(msg.content),
        "content_la_list": isinstance(msg.content, list),
        "content_50_ky_tu_dau": str(msg.content)[:50],
        "co_tool_calls": bool(getattr(msg, "tool_calls", None)),
        "response_metadata_keys": sorted((getattr(msg, "response_metadata", None) or {}).keys()),
        "co_usage_metadata": getattr(msg, "usage_metadata", None) is not None,
        "total_tokens": ket_qua.total_tokens,
        "finish_reason": (getattr(msg, "response_metadata", None) or {}).get("finish_reason"),
    }


async def main() -> None:
    prompts = rut_prompt()
    can = {"router": "INTENT_ROUTER_PROMPT",
           "planner": "WRITE_PLANNER_PROMPT",
           "synthesis": "RAG_SYNTHESIS_PROMPT"}
    thieu = [k for k in can.values() if k not in prompts]
    if thieu:
        raise SystemExit(f"không rút được prompt: {thieu} — prompts.py đã đổi?")
    for vai, ten in can.items():
        print(f"# {vai:10} ← {ten} ({len(prompts[ten])} ký tự)", file=sys.stderr)

    router = Router(BudgetLedger(InMemoryUsageStore()))
    ket_qua = []
    for vai, ten in can.items():
        try:
            ket_qua.append(await do_mot_vai(router, vai, prompts[ten]))
        except Exception as exc:
            ket_qua.append({"vai": vai, "LOI": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(ket_qua, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Bước 2: Chạy spike**

```bash
cd backend && python spikes/spike_port_smoke.py
```

Cần khoá thật trong môi trường. Nếu thiếu khoá → **BÁO CÁO BLOCKED**, đừng giả lập: spike mà không gọi thật thì không đo được gì, và cả lý do tồn tại của task này là đo thật.

- [ ] **Bước 3: Kiểm chứng giả thuyết `.content` list-shape**

Trong kết quả JSON, tìm vai `planner` và `synthesis` (cả hai chạy `gemini-3.5-flash-lite` / `gemini-3.1-flash-lite` khi sổ ngân sách trống). Khẳng định `content_la_list` là `true` cho ít nhất một vai chạy model Google.

Nếu `content_la_list` là `false` ở mọi vai: đọc lại `backend/.venv/Lib/site-packages/langchain_google_genai/chat_models.py`, tìm `_is_gemini_3_or_later` và `_append_to_content`, xác định vì sao nhánh đó không kích hoạt. Ghi phát hiện vào docs — có thể thư viện đã đổi, và khi đó Task 2 phần chuẩn hoá `.content` cần xem lại (vẫn làm, vì nó vô hại, nhưng lý do phải ghi đúng).

- [ ] **Bước 4: Đối chiếu prompt qwen3 với đầu ra cloud**

Với vai `planner`: đầu ra có phải JSON hợp lệ không? Chạy `json.loads()` lên phần content đã gộp về string. Prompt planner của repo nguồn hiệu chỉnh cho qwen3:8b, và `_parse_plan_tiered` bên đó **không sửa ngoặc** — nên JSON hỏng là lỗi thật, không cứu được.

Với vai `synthesis`: đầu ra có kèm chuỗi giống thẻ `<thought>` không (nếu chạy trúng Gemma)? Có xuống dòng/định dạng lạ không?

- [ ] **Bước 5: Ghi kết quả**

`docs/spikes/2026-07-29-port-cloud-model.md`. Cấu trúc — mỗi mục phải có **số đo thật**, không phỏng đoán:

```markdown
# Spike: hình dạng đầu ra model cloud với prompt hiệu chỉnh cho qwen3:8b

> Chạy ngày 2026-07-29 (điền ngày thật). Kết quả THẬT, không phải giả lập.

## Câu hỏi cần trả lời
1. `.content` có phải list với model gemini-3.x không?
2. Prompt planner (hiệu chỉnh qwen3) còn sinh JSON hợp lệ không?
3. `finish_reason` / `response_metadata` có hình dạng gì theo từng provider?
4. Còn chỗ nào khác vỡ?

## Kết quả đo
<dán nguyên JSON script in ra>

## Kết luận chi phối task sau
| Phát hiện | Ảnh hưởng task nào | Phải làm gì |
|---|---|---|
| ... | ... | ... |
```

Bảng cuối là phần quan trọng nhất — nó là thứ Task 2 và Task 9–13 đọc.

- [ ] **Bước 6: Xoá script spike, commit docs**

```bash
rm backend/spikes/spike_port_smoke.py
git add docs/spikes/2026-07-29-port-cloud-model.md
git commit -m "spike: đo hình dạng đầu ra model cloud với prompt qwen3

Chạy 3 vai (router/planner/synthesis) qua llm/router.py thật với prompt chép
nguyên văn từ repo nguồn. Đo kiểu dữ liệu .content, finish_reason, hình dạng
response_metadata theo từng provider.

Script vứt đi theo đúng thiết kế — chỉ giữ kết quả và bảng kết luận."
```

---

### Task 2: Làm cứng `RoutedChatModel` — ba phát hiện kế hoạch A

Ba vấn đề review toàn nhánh kế hoạch A tìm ra và ghi là *điều kiện đầu vào* của kế hoạch B. Vá **trước** khi port, vì cả ba nằm ở tầng dưới cái sắp port — vá trước thì khi port, lỗi nào hiện ra là lỗi port thật; vá sau thì mỗi lỗi phải điều tra hai khả năng.

Nếu Task 1 phát hiện thêm hình dạng đầu ra nào khác, xử lý luôn ở đây.

**Files:**
- Modify: `backend/src/llm/router.py`
- Modify: `backend/tests/llm/conftest.py` (FakeChatClient nhận thêm kwargs)
- Test: `backend/tests/llm/test_routed_chat_model.py` (thêm test), `backend/tests/llm/test_router_invoke.py` (thêm test)

**Interfaces:**
- Consumes: `Router`, `RoutedChatModel`, `RouteDecision`, `strip_thought` (kế hoạch A)
- Produces: chữ ký mới của `Router.invoke`/`.ainvoke`/`._client` và `RoutedChatModel.__init__`/`.bind_tools` — Task 8 (`models.py`) và Task 13 (`erp_agent`) dựa vào

- [ ] **Bước 1: Viết test thất bại**

Thêm vào cuối `backend/tests/llm/test_routed_chat_model.py`:

```python
def test_content_dang_list_duoc_gop_ve_string(clock):
    """langchain_google_genai nhánh _is_gemini_3_or_later() phát ra content dạng
    list khối {"type": "text"}, khớp CẢ gemini-3.5-flash-lite lẫn
    gemini-3.1-flash-lite — hai model đứng đầu 4/7 chuỗi vai. Mọi code agents/
    port sang đều gọi .content.strip(), nên không gộp ở đây là vỡ rải rác."""
    from langchain_core.messages import AIMessage
    khoi = AIMessage(content=[{"type": "text", "text": "Còn 42 "},
                              {"type": "text", "text": "cái."}],
                     response_metadata={"token_usage": {
                         "prompt_tokens": 5, "completion_tokens": 5,
                         "total_tokens": 10}})
    llm = RoutedChatModel(_router(clock, FakeChatClient([khoi])), "read")
    assert llm.invoke(MSGS).content == "Còn 42 cái."


def test_content_None_thanh_chuoi_rong(clock):
    from langchain_core.messages import AIMessage
    rong = AIMessage(content=[], response_metadata={"token_usage": {
        "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    llm = RoutedChatModel(_router(clock, FakeChatClient([rong])), "read")
    assert llm.invoke(MSGS).content == ""


def test_last_decision_khong_ro_ri_giua_hai_vai(clock):
    """make_llms() dựng mỗi vai một RoutedChatModel MỘT LẦN và ERPAgent là
    singleton dùng chung mọi request — nên last_decision phải tách theo vai,
    không được là một ô nhớ dùng chung."""
    client = FakeChatClient([fake_ai("a"), fake_ai("b")])
    router = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                    client_factory=lambda spec: client)
    doc = RoutedChatModel(router, "read")
    tan_gau = RoutedChatModel(router, "chitchat")
    doc.invoke(MSGS)
    tan_gau.invoke(MSGS)
    assert doc.last_decision.spec.alias == "gemini-3.5-flash-lite"
    assert tan_gau.last_decision.spec.alias == "gemma-4-31b"


def test_last_decision_khong_ro_ri_giua_hai_request_dong_thoi(clock):
    """Hai request đồng thời CÙNG VAI không được đọc nhầm quyết định của nhau.

    Đọc last_decision TRONG cùng task đã gọi ainvoke — đúng như graph làm ở
    đường chạy thật (FastAPI cấp mỗi request một task riêng, node đọc quyết định
    ngay trong request đó). ContextVar tách theo ngữ cảnh nên hai task thấy hai
    giá trị khác nhau dù dùng chung một khoá vai.
    """
    import asyncio

    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    by_alias = {"gemini-3.5-flash-lite": hong, "groq-llama-3.3-70b": tot}
    r_tut = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                   client_factory=lambda spec: by_alias[spec.alias])
    r_thang = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                     client_factory=lambda spec: FakeChatClient([fake_ai("ok")]))
    llm_tut = RoutedChatModel(r_tut, "read")
    llm_thang = RoutedChatModel(r_thang, "read")

    async def mot_request(llm):
        await llm.ainvoke(MSGS)
        return llm.last_decision          # đọc TRONG task, như graph thật

    async def hai_request_song_song():
        return await asyncio.gather(mot_request(llm_tut),
                                    mot_request(llm_thang))

    qd_tut, qd_thang = asyncio.run(hai_request_song_song())
    assert qd_tut.spec.alias == "groq-llama-3.3-70b"    # đã tụt vì 429
    assert qd_thang.spec.alias == "gemini-3.5-flash-lite"
    assert qd_tut is not qd_thang


def test_config_duoc_chuyen_tiep_xuong_client(clock):
    """config là đường LangChain lan callback/tag/metadata xuống runnable con —
    đúng đường handler Langfuse của kế hoạch C sẽ dùng. Nuốt nó là làm hỏng
    tracing một cách âm thầm."""
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    cau_hinh = {"tags": ["thu-nghiem"], "metadata": {"phien": "abc"}}
    llm.invoke(MSGS, config=cau_hinh)
    assert client.configs[-1] == cau_hinh


def test_bind_tools_giu_lai_kwargs_phu(clock):
    """bind_tools(tools, tool_choice=...) nhận rồi bỏ im lặng là đổi hành vi
    âm thầm tại chỗ gọi đã port."""
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    llm.bind_tools(tools, tool_choice="auto").invoke(MSGS)
    assert client.bound_tool_kwargs == {"tool_choice": "auto"}
```

- [ ] **Bước 2: Cập nhật `FakeChatClient` để ghi lại `config` và kwargs**

Sửa `FakeChatClient` trong `backend/tests/llm/conftest.py` — thay `bind_tools` và hai phương thức invoke:

```python
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[list] = []
        self.configs: list = []             # MỚI: config từng lượt
        self.bound_tools = None
        self.bound_tool_kwargs: dict = {}   # MỚI: kwargs của bind_tools

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        self.bound_tool_kwargs = dict(kwargs)
        return self

    def _next(self, messages, config=None):
        self.calls.append(messages)
        self.configs.append(config)
        item = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def invoke(self, messages, config=None, **kwargs):
        return self._next(messages, config)

    async def ainvoke(self, messages, config=None, **kwargs):
        return self._next(messages, config)
```

- [ ] **Bước 3: Chạy test để chắc chắn nó thất bại**

Run: `cd backend && python -m pytest tests/llm/test_routed_chat_model.py -v`
Expected: 6 test mới FAIL. `test_content_dang_list_duoc_gop_ve_string` FAIL vì `.content` vẫn là list; `test_config_duoc_chuyen_tiep_xuong_client` FAIL với `AssertionError` vì `configs[-1]` là `None`.

- [ ] **Bước 4: Chuẩn hoá `.content`**

Thêm vào `backend/src/llm/router.py`, ngay TRƯỚC `class Router`:

```python
def _gop_content(content) -> str:
    """Gộp content về string — có thể là list khối với model Gemini 3.x.

    langchain_google_genai có nhánh _is_gemini_3_or_later() khớp tiền tố
    "gemini-3", tức CẢ gemini-3.5-flash-lite LẪN gemini-3.1-flash-lite; trên
    nhánh đó nó phát ra content là list các khối {"type": "text", "text": ...}
    thay vì string. Hai model này đứng đầu 4 trong 7 chuỗi vai (read, planner,
    fusion, synthesis), và toàn bộ code agents/ port từ repo nguồn sang đều gọi
    .content.strip() — không gộp ở ĐÂY thì phải vá rải rác khắp mọi node, và
    chỗ nào quên thì vỡ lúc chạy chứ không phải lúc test.

    Gộp ở tầng này còn khiến strip_thought() luôn nhận string, đúng chữ ký của nó.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        phan = []
        for khoi in content:
            if isinstance(khoi, str):
                phan.append(khoi)
            elif isinstance(khoi, dict) and khoi.get("type") == "text":
                phan.append(khoi.get("text") or "")
        return "".join(phan)
    return str(content)
```

Rồi sửa `Router._finish()` — thêm ĐÚNG MỘT dòng đầu thân hàm, trước khối `emits_thought_tags`:

```python
    def _finish(self, decision: RouteDecision, response,
                attempts: list[AttemptError]) -> InvokeResult:
        response.content = _gop_content(response.content)      # DÒNG MỚI
        if decision.spec.emits_thought_tags:
            response.content = strip_thought(response.content)
```

Đặt ở `_finish()` chứ không ở `RoutedChatModel` là cố ý: `Router.invoke()` cũng có bên gọi trực tiếp (không qua mặt tiền), và cả hai đường đều phải nhận string.

- [ ] **Bước 5: `last_decision` an toàn đa luồng**

Thêm `from contextvars import ContextVar` vào khối import đầu `router.py`. Rồi thêm ngay trước `class RoutedChatModel`:

```python
# Quyết định của lượt gọi vừa rồi, tách theo NGỮ CẢNH chứ không theo instance.
#
# make_llms() dựng mỗi vai một RoutedChatModel đúng MỘT LẦN, và ERPAgent là
# singleton dựng trong lifespan của FastAPI — tức mọi request dùng chung đúng
# những object ấy. Để last_decision làm biến instance thì hai request cùng vai
# đua nhau, bên thua đọc được quyết định của bên kia. Kế hoạch C chỉ định đúng
# last_decision làm móc đổ thuộc tính span Langfuse, nên đọc nhầm ở đây là ghi
# sai trace, loại lỗi không ai phát hiện bằng mắt.
#
# Một ContextVar duy nhất giữ dict {khoá vai: quyết định}, KHÔNG tạo ContextVar
# theo từng instance: bind_tools() sinh instance mới mỗi lượt gọi, mà ContextVar
# tạo động thì không bao giờ được thu hồi.
#
# GIỚI HẠN phải biết: giá trị set() bên trong một asyncio.Task KHÔNG lan ngược
# về task cha (đã kiểm chứng: gather xong rồi đọc ở cha thì thấy dict rỗng).
# Nên last_decision phải được đọc TRONG cùng ngữ cảnh đã gọi invoke — đúng như
# graph làm (FastAPI cấp mỗi request một task, node đọc quyết định ngay trong
# request đó). Đây chính là tính chất tạo ra sự cô lập: hai request đồng thời
# cùng vai thấy hai giá trị khác nhau thay vì ghi đè lên nhau.
_QUYET_DINH: ContextVar[dict] = ContextVar("routed_chat_quyet_dinh", default={})
```

Rồi sửa `RoutedChatModel` — `__init__` nhận thêm `tool_kwargs`, `last_decision` thành property:

```python
    def __init__(self, router: "Router", role: str, tools: list | None = None,
                 pin: str | None = None,
                 tool_kwargs: dict | None = None) -> None:
        self._router = router
        self._role = role
        self._tools = tools
        self._pin = pin
        self._tool_kwargs = dict(tool_kwargs or {})
        # Khoá theo vai+ghim: bind_tools() trả instance mới nhưng cùng vai, và
        # đó vẫn là cùng một lượt gọi logic nên phải cùng khoá.
        self._khoa = f"{role}\x00{pin or ''}"

    @property
    def last_decision(self) -> RouteDecision | None:
        return _QUYET_DINH.get().get(self._khoa)

    def _ghi_quyet_dinh(self, decision: RouteDecision) -> None:
        # Gán dict MỚI chứ không sửa tại chỗ: dict mặc định của ContextVar dùng
        # chung mọi ngữ cảnh, sửa tại chỗ là rò rỉ đúng thứ đang đi tránh.
        _QUYET_DINH.set({**_QUYET_DINH.get(), self._khoa: decision})
```

- [ ] **Bước 6: Chuyển tiếp `config` và `tool_kwargs`**

Sửa `RoutedChatModel.bind_tools`, `.invoke`, `.ainvoke`:

```python
    def bind_tools(self, tools: list, **kwargs) -> "RoutedChatModel":
        # Trả bản MỚI, không sửa bản gốc — khớp ngữ nghĩa bind_tools của
        # LangChain. Bản mới dùng chung router nên dùng chung sổ ngân sách.
        # kwargs (tool_choice, parallel_tool_calls…) đi theo xuống client:
        # nhận rồi bỏ im lặng là đổi hành vi âm thầm tại chỗ gọi đã port.
        return RoutedChatModel(self._router, self._role, tools, self._pin,
                               tool_kwargs={**self._tool_kwargs, **kwargs})

    def invoke(self, input, config=None, **kwargs):
        result = self._router.invoke(self._role, input, tools=self._tools,
                                     pin=self._pin, config=config,
                                     tool_kwargs=self._tool_kwargs, **kwargs)
        self._ghi_quyet_dinh(result.decision)
        return result.message

    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._router.ainvoke(self._role, input,
                                            tools=self._tools, pin=self._pin,
                                            config=config,
                                            tool_kwargs=self._tool_kwargs,
                                            **kwargs)
        self._ghi_quyet_dinh(result.decision)
        return result.message
```

Rồi sửa `Router._client`, `.invoke`, `.ainvoke` để nhận và truyền xuống. `_client`:

```python
    def _client(self, spec: ModelSpec, tools, tool_kwargs=None):
        # Cache theo alias: dựng lại client mỗi lượt là lãng phí (dù là
        # ChatOpenAI hay ChatGoogleGenerativeAI — client_for() trả loại nào
        # tuỳ provider, xem Task 7), mà tools thì
        # đổi theo lượt nên bind_tools() gọi lại mỗi lần (nó trả về bản bọc
        # mới, không sửa client gốc).
        if spec.alias not in self._clients:
            self._clients[spec.alias] = self._client_factory(spec)
        client = self._clients[spec.alias]
        if not tools:
            return client
        return client.bind_tools(tools, **(tool_kwargs or {}))
```

`invoke` — đổi chữ ký và đúng một dòng gọi client:

```python
    def invoke(self, role: str, messages: list, tools: list | None = None,
               pin: str | None = None, config=None,
               tool_kwargs: dict | None = None, **kwargs) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = self._client(decision.spec, tools, tool_kwargs).invoke(
                    messages, config=config, **kwargs)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))
```

`ainvoke` — y hệt, đổi đúng dòng gọi client:

```python
                response = await self._client(
                    decision.spec, tools, tool_kwargs).ainvoke(
                        messages, config=config, **kwargs)
```

Hai vòng lặp giống nhau tới 90% và **cố ý không gộp** (quyết định kế hoạch A): gộp lại sẽ phải chạy nhánh đồng bộ qua executor hoặc dựng một lớp trừu tượng async/sync, cả hai đều đắt hơn nhiều so với việc đọc song song hai vòng lặp mười dòng.

- [ ] **Bước 7: Chạy test để chắc chắn nó xanh**

Run: `cd backend && python -m pytest tests/llm/ -v`
Expected: toàn bộ PASS — 98 test cũ + 6 test mới = 104, 16 deselected.

Nếu test cũ nào đỏ: `test_go_thought_cho_model_gemma` và `test_khong_go_gi_voi_model_khong_nha_thought` chạy qua `_finish()` nên chịu ảnh hưởng của `_gop_content` — chúng phải VẪN xanh vì content của chúng là string và `_gop_content` trả nguyên string. Đỏ ở đó nghĩa là `_gop_content` sai, không phải test sai.

- [ ] **Bước 8: Commit**

```bash
git add backend/src/llm/router.py backend/tests/llm/conftest.py \
        backend/tests/llm/test_routed_chat_model.py
git commit -m "fix(llm): làm cứng RoutedChatModel trước khi port tầng nghiệp vụ

Ba phát hiện review toàn nhánh kế hoạch A ghi là điều kiện đầu vào của B.
Vá TRƯỚC khi port: cả ba nằm ở tầng dưới cái sắp port, vá trước thì lỗi hiện
ra lúc port là lỗi port thật, vá sau thì mỗi lỗi phải điều tra hai khả năng.

1. .content trả list với model gemini-3.x (nhánh _is_gemini_3_or_later khớp cả
   3.5-flash-lite lẫn 3.1-flash-lite — hai model đứng đầu 4/7 chuỗi vai). Gộp
   ở Router._finish() nên cả đường qua mặt tiền lẫn đường gọi Router trực tiếp
   đều nhận string, và strip_thought() luôn đúng chữ ký.

2. last_decision đua nhau: make_llms() dựng mỗi vai một object MỘT LẦN, ERPAgent
   là singleton dùng chung mọi request. Chuyển sang ContextVar giữ dict theo vai
   — một ContextVar duy nhất, không tạo động theo instance vì bind_tools() sinh
   instance mới mỗi lượt.

3. invoke()/bind_tools() nuốt config và kwargs. config là đường LangChain lan
   callback xuống runnable con — đúng đường Langfuse của kế hoạch C."
```

---

### Task 3: Hạ tầng — compose, biến môi trường, phụ thuộc

Youdoo chưa có `docker-compose.yml` nào. Kế hoạch B verify bằng hạ tầng thật, nên định nghĩa hạ tầng phải tồn tại trong repo này — không mượn file của `D:\Project`.

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: không
- Produces: hạ tầng chạy được cho Task 4–13; `DATABASE_URL`, `OLLAMA_URL`, `ODOO_*`, `MCP_ODOO_URL`

- [ ] **Bước 1: Viết `docker-compose.yml`**

Chép từ `D:\Project\docker-compose.yml`, giữ đúng hai service và **bỏ hai service**:

| Service | Giữ? | Lý do |
|---|---|---|
| `postgres` (`pgvector/pgvector:pg16`) | Giữ | RAG cần pgvector; sổ ngân sách kế hoạch A cũng dùng Postgres, dùng chung một DB |
| `ollama` | Giữ | `OllamaEmbedder` (bge-m3) bật mặc định ở Task 5 |
| `litellm` | **BỎ** | SP-1 đã bỏ LiteLLM (ADR-011 mục 2) — cả 3 nhà đã OpenAI-compatible nên giá trị hợp nhất giao thức bốc hơi |
| `open-webui` | **BỎ** | Giao diện chat, chỉ có nghĩa khi có `/v1` — kế hoạch C |

Mở đầu file bằng khối bình luận:

```yaml
# Hạ tầng SP-1B. KHÔNG có litellm (ADR-011 mục 2 — cả 3 nhà đã
# OpenAI-compatible nên LiteLLM hết lý do tồn tại) và KHÔNG có open-webui
# (giao diện chat chỉ có nghĩa khi có /v1, tức kế hoạch C).
#
# Odoo nằm NGOÀI compose này — trỏ qua ODOO_URL. Repo nguồn dùng
# host.docker.internal:8069.
```

Cổng Postgres giữ `5433` cho khớp `DATABASE_URL` mặc định của kế hoạch A và của `rag/config.py`.

- [ ] **Bước 2: Bổ sung `.env.example`**

Thêm vào cuối `.env.example` hiện có (giữ nguyên phần LLM/Postgres/Langfuse đã có):

```
# ─── Odoo (kế hoạch B) ───────────────────────────────────────────────────────
ODOO_URL=http://host.docker.internal:8069
ODOO_DB=odoo
ODOO_USERNAME=admin
ODOO_PASSWORD=thay_bang_mat_khau

# ─── MCP server Odoo (tiến trình riêng, SSE) ─────────────────────────────────
MCP_ODOO_URL=http://localhost:8001/sse

# ─── RAG ─────────────────────────────────────────────────────────────────────
# RAG_DB_DSN mặc định lấy DATABASE_URL ở trên — dùng chung DB với sổ ngân sách.
OLLAMA_URL=http://localhost:11434
RAG_SCHEMA=public
# Reranker nạp lười, fail-open. Đặt 0 để bỏ hẳn (không tải model 2.3GB).
RAG_RERANK_ENABLED=1
# Test luôn tắt cờ này qua fixture autouse — đây là mặc định cho chạy thật.
ERP_SEMANTIC_RESOLVE=0
```

**Không đặt khoá thật vào file này.**

- [ ] **Bước 3: Bổ sung `backend/requirements.txt`**

Danh sách dưới đây lấy từ việc **quét import thật** của `rag/`, `erp_query/`, `agents/` trong repo nguồn — không chép cả `requirements.txt` của nó (file đó có torch/opencv/ultralytics cho phần thị giác máy tính không liên quan). Thêm vào cuối file:

```
langgraph==1.1.10
langgraph-checkpoint==4.1.0
langgraph-checkpoint-postgres==3.1.0
langgraph-prebuilt==1.0.13
langchain-mcp-adapters==0.3.0
pgvector==0.4.1
pypdf==5.1.0
python-docx==1.1.2
openpyxl==3.1.5
pyvi==0.1.1
```

`transformers` và `torch` CỐ Ý không thêm: `rag/reranker.py` import chúng **lười** bên trong `_load()` và fail-open tuyệt đối (mọi sự cố → `None`, retrieval quay về hybrid-rrf). Test không bao giờ chạm tới (fixture autouse tắt sẵn). Ai cần reranker thật thì cài riêng và bật `RAG_RERANK_ENABLED=1`; kế hoạch C sẽ quyết khi chạy eval gate đối chiếu baseline, vì baseline qwen3:8b đo CÓ reranker.

- [ ] **Bước 4: Dựng venv rồi cài**

`backend/.venv` **chưa tồn tại** ở `main`: nó từng nằm trong worktree của kế hoạch A, và worktree đó đã bị xoá sau khi merge. Dựng mới:

```bash
cd backend
py -3.11 -m venv .venv          # hoặc python3.11 -m venv .venv tuỳ máy
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -c "import langgraph, langchain_mcp_adapters, pgvector, pypdf, docx, openpyxl, pyvi; print('OK')"
```
Expected: in `OK`, không lỗi import.

Kiểm cả phần kế hoạch A vẫn nhập được:
```bash
.venv/Scripts/python.exe -c "import langchain_google_genai, langchain_openai, psycopg, psycopg_pool, tiktoken; print('OK ke hoach A')"
```
Expected: in `OK ke hoach A`.

`.gitignore` đã có `.venv/` (dòng 15) nên `backend/.venv/` được loại sẵn — đã kiểm chứng. Xác nhận lại bằng **dấu `/` ở cuối**, vì thiếu nó thì `check-ignore` trả rỗng với đường dẫn chưa tồn tại và dễ hiểu nhầm là chưa ignore:

```bash
git check-ignore -v "backend/.venv/"
```
Expected: in `.gitignore:15:.venv/	backend/.venv/`. Không cần sửa `.gitignore`.

- [ ] **Bước 5: Dựng hạ tầng và kiểm**

```bash
docker compose up -d postgres
docker compose ps
# (Superseded, Task 3 thực tế: dùng chung Ollama đã có sẵn ở cổng 11434, không tạo service ollama trong compose này — xem ledger Task 3.)
```
Expected: cả hai service `running`; `ollama pull` tải xong bge-m3.

Kiểm Postgres có extension vector:
```bash
docker compose exec postgres psql -U admin -d ai_assistant -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
```
Expected: in ra một số phiên bản.

- [ ] **Bước 6: Chạy lại toàn bộ test cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -v`
Expected: 104 passed (98 của kế hoạch A + 6 của Task 2), không hồi quy.

- [ ] **Bước 7: Commit**

```bash
git add docker-compose.yml .env.example backend/requirements.txt
git commit -m "chore: hạ tầng cho kế hoạch B — compose, biến môi trường, phụ thuộc

Youdoo chưa có docker-compose nào; kế hoạch B verify bằng hạ tầng thật nên
định nghĩa hạ tầng phải nằm trong repo này.

Bỏ litellm (ADR-011 mục 2) và open-webui (kế hoạch C) khỏi compose nguồn.
Postgres giữ cổng 5433 để dùng chung DATABASE_URL với sổ ngân sách kế hoạch A.

Phụ thuộc thêm lấy từ quét import THẬT của rag/erp_query/agents, không chép cả
requirements.txt nguồn (nó có torch/opencv/ultralytics cho phần thị giác máy
tính không liên quan). transformers/torch cố ý không thêm: reranker import lười
và fail-open, test không chạm tới."
```

---

### Task 4: Port `rag/` (trừ `embed.py`)

Lá của đồ thị phụ thuộc — `rag/` không import gì nội bộ, nên port được trước mọi thứ.

**Files:**
- Create: `backend/src/rag/__init__.py`, `config.py`, `types.py`, `db.py`, `chunking.py`, `parse.py`, `ingest.py`, `retrieve.py`, `reranker.py`, `schema.sql`
- Create: `backend/src/rag/seed/` (chép nguyên thư mục)
- Test: `backend/tests/rag/` — 9 file (mọi `test_*.py` TRỪ `test_embed.py`)

**Interfaces:**
- Consumes: không (lá)
- Produces: `retrieve.search()`, `ingest`, `chunking`, `types` — Task 6 (`erp_query/semantic.py`) và Task 11 (`synthesis.py`) dùng

- [ ] **Bước 1: Chép mã nguồn**

```bash
mkdir -p backend/src/rag
cp "/d/Project/backend/src/rag/__init__.py" backend/src/rag/
cp "/d/Project/backend/src/rag/config.py" backend/src/rag/
cp "/d/Project/backend/src/rag/types.py" backend/src/rag/
cp "/d/Project/backend/src/rag/db.py" backend/src/rag/
cp "/d/Project/backend/src/rag/chunking.py" backend/src/rag/
cp "/d/Project/backend/src/rag/parse.py" backend/src/rag/
cp "/d/Project/backend/src/rag/ingest.py" backend/src/rag/
cp "/d/Project/backend/src/rag/retrieve.py" backend/src/rag/
cp "/d/Project/backend/src/rag/reranker.py" backend/src/rag/
cp "/d/Project/backend/src/rag/schema.sql" backend/src/rag/
cp -r "/d/Project/backend/src/rag/seed" backend/src/rag/
```

**KHÔNG chép `embed.py`** — Task 5 viết lại nó. `retrieve.py` và `ingest.py` sẽ đỏ vì thiếu import; đó là đúng, Task 5 vá.

**KHÔNG chép `__pycache__` hay `eval/`** (`rag/eval/` thuộc harness eval, hoãn sang kế hoạch C).

- [ ] **Bước 2: Chép test**

```bash
mkdir -p backend/tests/rag
cp "/d/Project/backend/tests/rag/"__init__.py backend/tests/rag/ 2>/dev/null || touch backend/tests/rag/__init__.py
for f in test_chunking_text test_chunking_xlsx test_db test_ingest test_parse_pdf \
         test_reranker test_retrieve test_types test_eval; do
  cp "/d/Project/backend/tests/rag/$f.py" backend/tests/rag/
done
cp -r "/d/Project/backend/tests/rag/fixtures" backend/tests/rag/ 2>/dev/null || true
```

`test_embed.py` KHÔNG chép — Task 5 viết mới.

Nếu `test_eval.py` import từ `rag/eval/` (chưa chép) thì bỏ luôn file đó và ghi vào báo cáo — nó thuộc harness eval của kế hoạch C.

- [ ] **Bước 3: Chép conftest gốc**

`backend/tests/conftest.py` của repo nguồn có các fixture `autouse` mà mọi test dựa vào (`friction_log_path` chuyển log sang tmp, `semantic_resolve_off` tắt đường semantic để test không cần PG/Ollama). Youdoo chưa có file này.

```bash
cp "/d/Project/backend/tests/conftest.py" backend/tests/conftest.py
```

Đọc file vừa chép. Nếu nó import bất cứ thứ gì từ `src.agents` (chưa port tới Task 9+), tạm bỏ đúng phần đó ra và ghi lại trong báo cáo để Task 10 khôi phục.

- [ ] **Bước 4: Chạy test, xem cái gì đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/ -v`
Expected: một số FAIL với `ImportError` về `embed` (đúng — Task 5 vá), phần còn lại PASS hoặc SKIP.

Ghi lại CHÍNH XÁC test nào đỏ và vì sao. Áp dụng **quy tắc port test** ở Global Constraints: đỏ vì đường import/hạ tầng thì sửa nối dây; đỏ vì hành vi đổi thì DỪNG và báo cáo.

- [ ] **Bước 5: Sửa nối dây**

Chỉ sửa những gì thuộc loại "hạ tầng đổi". Dự kiến chỉ có đường import (`from src.rag...` vẫn đúng vì cấu trúc giống hệt). Nếu không có gì phải sửa, ghi rõ "không cần sửa" trong báo cáo — đó là kết quả tốt.

- [ ] **Bước 6: Chạy lại**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/ -v -m "not integration and not live"`
Expected: mọi test PASS, TRỪ những test cần `embed` (Task 5 sẽ làm xanh).

Rồi chạy toàn bộ để chắc không hỏng kế hoạch A:
Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -v`
Expected: 104 test của llm/ vẫn PASS.

- [ ] **Bước 7: Commit**

```bash
git add backend/src/rag backend/tests/rag backend/tests/conftest.py
git commit -m "feat(rag): port tầng rag từ repo nguồn (trừ embed.py)

Lá của đồ thị phụ thuộc — rag/ không import gì nội bộ nên port được trước.
embed.py để Task 5 viết lại (interface + 2 implementation + marker chống lệch).

Kèm backend/tests/conftest.py: các fixture autouse mà mọi test dựa vào —
friction_log_path (không làm bẩn telemetry thật) và semantic_resolve_off
(test không cần PG/Ollama).

reranker.py port nguyên: nó import transformers LƯỜI bên trong _load() và
fail-open tuyệt đối, nên không cần torch trong requirements."
```

---

### Task 5: Viết lại `rag/embed.py` — interface + hai implementation + marker chống lệch

Đây là một trong bốn điểm thiết kế thật của kế hoạch B.

`OllamaEmbedder` (bge-m3, 1024-dim) **bật mặc định**; `GeminiEmbedder` viết sẵn nhưng **tắt**. Corpus nhỏ (17 tài liệu, 8.2MB) nên re-index qua Gemini chỉ tốn 30–60 phút — chi phí không phải rào cản. **Rào cản là đo đạc:** đổi embedding cùng lúc đổi LLM là đổi hai biến; `read` và `multi_source` lệch đi thì không quy được cho biến nào.

**Files:**
- Create: `backend/src/rag/embed.py`
- Test: `backend/tests/rag/test_embed.py`
- Reference: `D:\Project\backend\src\rag\embed.py` (29 dòng — bản gốc chỉ có Ollama)

**Interfaces:**
- Consumes: `rag/config.py` (`EMBED_MODEL`, `EMBED_DIM`, `OLLAMA_URL`)
- Produces: `Embedder` protocol, `OllamaEmbedder`, `GeminiEmbedder`, `get_embedder()`, `assert_embedding_marker(conn)` — `retrieve.py`/`ingest.py` dùng

- [ ] **Bước 1: Đọc bản gốc**

Đọc `D:\Project\backend\src\rag\embed.py`. Nó đã tách sẵn `embed_texts()` / `embed_query()` — **đúng hình dạng cần có**, vì embedding Gemini bất đối xứng (`task_type` phân biệt `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) trong khi bge-m3 đối xứng. Giữ nguyên chữ ký và hành vi HTTP của `OllamaEmbedder`, chỉ bọc lại thành lớp.

- [ ] **Bước 2: Viết test thất bại**

`backend/tests/rag/test_embed.py`:

```python
"""Test embed.py — hai implementation + marker chống lệch.

Không chạm mạng: OllamaEmbedder được test qua httpx mock, GeminiEmbedder chỉ
test phần cấu hình (nó TẮT mặc định nên không có đường chạy thật ở SP-1).
"""
import pytest

from src.rag.embed import (Embedder, GeminiEmbedder, OllamaEmbedder,
                           assert_embedding_marker, get_embedder)


def test_ollama_la_mac_dinh():
    """Nguyên tắc một-biến: SP-1 đổi LLM, KHÔNG đổi embedding cùng lúc."""
    assert isinstance(get_embedder(), OllamaEmbedder)


def test_ollama_khai_bao_dung_model_va_chieu():
    e = OllamaEmbedder()
    assert e.model_name == "bge-m3"
    assert e.dim == 1024


def test_gemini_khai_bao_dung_model_va_chieu():
    e = GeminiEmbedder()
    assert e.model_name == "gemini-embedding-001"
    assert e.dim == 3072


def test_ca_hai_deu_thoa_protocol():
    assert isinstance(OllamaEmbedder(), Embedder)
    assert isinstance(GeminiEmbedder(), Embedder)


def test_marker_khop_thi_khong_nem(fake_conn_khop):
    assert_embedding_marker(fake_conn_khop)      # không raise là đạt


def test_marker_lech_model_thi_nem_RuntimeError(fake_conn_lech_model):
    with pytest.raises(RuntimeError, match="embedding"):
        assert_embedding_marker(fake_conn_lech_model)


def test_marker_lech_chieu_thi_nem_RuntimeError(fake_conn_lech_dim):
    with pytest.raises(RuntimeError, match="1024|dim"):
        assert_embedding_marker(fake_conn_lech_dim)


def test_marker_chua_co_ban_ghi_thi_khong_nem(fake_conn_rong):
    """DB trống (chưa index gì) không phải lệch — chỉ là chưa có gì để lệch."""
    assert_embedding_marker(fake_conn_rong)


class _FakeConn:
    """Kết nối giả trả sẵn một hàng marker."""

    def __init__(self, row) -> None:
        self._row = row

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return self._row


@pytest.fixture
def fake_conn_khop():
    return _FakeConn(("bge-m3", 1024))


@pytest.fixture
def fake_conn_lech_model():
    return _FakeConn(("gemini-embedding-001", 1024))


@pytest.fixture
def fake_conn_lech_dim():
    return _FakeConn(("bge-m3", 3072))


@pytest.fixture
def fake_conn_rong():
    return _FakeConn(None)
```

- [ ] **Bước 3: Chạy test để chắc chắn nó thất bại**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_embed.py -v`
Expected: FAIL với `ImportError: cannot import name 'Embedder' from 'src.rag.embed'`

- [ ] **Bước 4: Viết `embed.py`**

```python
"""Embedding — hai implementation sau một interface (spec SP-1B §3b).

OllamaEmbedder (bge-m3, 1024 chiều) BẬT mặc định; GeminiEmbedder viết sẵn
nhưng TẮT.

VÌ SAO KHÔNG BẬT GEMINI NGAY: corpus nhỏ (17 tài liệu, 8.2MB) nên re-index chỉ
tốn 30–60 phút — chi phí không phải rào cản. Rào cản là ĐO ĐẠC: SP-1 đã đổi LLM
từ qwen3:8b local sang cloud; đổi luôn embedding là đổi HAI biến cùng lúc, và
khi read/multi_source lệch đi thì không quy được cho biến nào. Sau khi eval-gate
của cú flip LLM đi qua (kế hoạch C), lật embedding là thí nghiệm THỨ HAI, đo
riêng.

Hai bên bất đối xứng khác nhau: bge-m3 đối xứng (câu hỏi và tài liệu nhúng như
nhau), Gemini bất đối xứng (task_type phân biệt RETRIEVAL_DOCUMENT với
RETRIEVAL_QUERY). Đó là lý do interface tách embed_texts() khỏi embed_query()
thay vì một hàm embed() dùng chung.
"""
import os
from typing import Protocol, runtime_checkable

import httpx

from .config import EMBED_DIM, EMBED_MODEL, OLLAMA_URL

GEMINI_EMBED_MODEL = "gemini-embedding-001"
GEMINI_EMBED_DIM = 3072


@runtime_checkable
class Embedder(Protocol):
    """Hợp đồng chung. Ai thêm provider mới chỉ cần thoả bốn thứ này."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dim(self) -> int: ...


class OllamaEmbedder:
    """bge-m3 qua Ollama — ĐỐI XỨNG, câu hỏi và tài liệu nhúng như nhau."""

    def __init__(self, url: str | None = None) -> None:
        self._url = (url or OLLAMA_URL).rstrip("/")

    @property
    def model_name(self) -> str:
        return EMBED_MODEL

    @property
    def dim(self) -> int:
        return EMBED_DIM

    def _goi(self, text: str) -> list[float]:
        r = httpx.post(f"{self._url}/api/embeddings",
                       json={"model": EMBED_MODEL, "prompt": text},
                       timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._goi(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._goi(text)


class GeminiEmbedder:
    """gemini-embedding-001 — BẤT ĐỐI XỨNG, task_type phân biệt tài liệu/câu hỏi.

    TẮT ở SP-1 (xem docstring module). Viết sẵn để cú lật sau này là đổi một
    biến môi trường chứ không phải viết code mới dưới áp lực.

    Model ID đã xác nhận tồn tại qua GET /v1beta/models ngày 2026-07-28:
    gemini-embedding-001, gemini-embedding-2-preview, gemini-embedding-2.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    @property
    def model_name(self) -> str:
        return GEMINI_EMBED_MODEL

    @property
    def dim(self) -> int:
        return GEMINI_EMBED_DIM

    def _goi(self, text: str, task_type: str) -> list[float]:
        if not self._api_key:
            raise RuntimeError(
                "thiếu GOOGLE_API_KEY — cần cho GeminiEmbedder. Xem .env.example.")
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_EMBED_MODEL}:embedContent",
            params={"key": self._api_key},
            json={"content": {"parts": [{"text": text}]}, "taskType": task_type},
            timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]["values"]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._goi(t, "RETRIEVAL_DOCUMENT") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._goi(text, "RETRIEVAL_QUERY")


def get_embedder() -> Embedder:
    """Provider đang bật. Mặc định Ollama — xem docstring module về một-biến."""
    ten = os.environ.get("RAG_EMBED_PROVIDER", "ollama").lower()
    if ten == "gemini":
        return GeminiEmbedder()
    return OllamaEmbedder()


def assert_embedding_marker(conn) -> None:
    """Provider đang bật lệch với marker trong DB → CHẾT LỚN TIẾNG lúc khởi động.

    Vector nhúng bằng bge-m3 (1024 chiều, đối xứng) và bằng gemini-embedding-001
    (3072 chiều, bất đối xứng) nằm trong hai không gian KHÁC NHAU. Truy vấn
    không gian này bằng vector của không gian kia không báo lỗi — nó chỉ trả về
    kết quả rác, xếp hạng theo một độ tương đồng vô nghĩa. Retrieval rác một
    cách IM LẶNG tệ hơn nhiều so với app không lên: cái thứ hai ai cũng thấy
    ngay, cái thứ nhất đi thẳng vào câu trả lời cho người dùng.

    Cùng triết lý fail-loud với PostgresUsageStore kiểm bảng llm_usage lúc dựng
    (kế hoạch A) — cấu hình lệch phải chết sớm, không đợi tới lúc dùng.

    DB trống (chưa index gì) KHÔNG phải lệch: chưa có gì để lệch.
    """
    row = conn.execute(
        "SELECT embedding_model, dim FROM rag_embedding_marker LIMIT 1").fetchone()
    if row is None:
        return
    trong_db, dim_db = row[0], row[1]
    dang_bat = get_embedder()
    if trong_db != dang_bat.model_name or dim_db != dang_bat.dim:
        raise RuntimeError(
            f"lệch embedding: DB đã index bằng {trong_db!r} ({dim_db} chiều) "
            f"nhưng provider đang bật là {dang_bat.model_name!r} "
            f"({dang_bat.dim} chiều). Vector hai bên nằm ở hai không gian khác "
            f"nhau — truy vấn chéo trả kết quả rác mà KHÔNG báo lỗi. "
            f"Hoặc đổi RAG_EMBED_PROVIDER về đúng, hoặc re-index toàn bộ.")
```

- [ ] **Bước 5: Thêm bảng marker vào `schema.sql`**

Thêm vào cuối `backend/src/rag/schema.sql`:

```sql
-- Marker chống lệch embedding (spec SP-1B §3b). Một hàng duy nhất, ghi lúc
-- index. Provider đang bật lệch với hàng này → app không lên (embed.py
-- assert_embedding_marker). Vector bge-m3 và vector Gemini nằm ở hai không gian
-- khác nhau; truy vấn chéo trả rác mà không báo lỗi.
CREATE TABLE IF NOT EXISTS rag_embedding_marker (
    embedding_model text    NOT NULL,
    dim             integer NOT NULL
);
```

- [ ] **Bước 6: Nối `ingest.py` ghi marker**

Đọc `backend/src/rag/ingest.py`. Tìm chỗ nó bắt đầu index (hàm chính). Thêm ngay sau khi kết nối DB:

```python
    # Ghi marker nếu chưa có — để lần khởi động sau assert_embedding_marker()
    # bắt được cú đổi provider mà không re-index.
    e = get_embedder()
    conn.execute(
        "INSERT INTO rag_embedding_marker (embedding_model, dim) "
        "SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM rag_embedding_marker)",
        (e.model_name, e.dim))
```

Sửa import đầu `ingest.py` và `retrieve.py`: bản gốc import hàm rời từ `embed`, giờ đổi sang `from .embed import get_embedder` rồi gọi `get_embedder().embed_texts(...)` / `.embed_query(...)`. Đọc mã hai file để biết chính xác tên hàm cũ chúng gọi.

- [ ] **Bước 7: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/ -v -m "not integration and not live"`
Expected: toàn bộ `tests/rag/` PASS, kể cả những test Task 4 để lại đỏ vì thiếu `embed`.

- [ ] **Bước 8: Commit**

```bash
git add backend/src/rag/embed.py backend/src/rag/schema.sql \
        backend/src/rag/ingest.py backend/src/rag/retrieve.py \
        backend/tests/rag/test_embed.py
git commit -m "feat(rag): embed.py — interface + Ollama (bật) + Gemini (tắt) + marker

Nguyên tắc một-biến: SP-1 đã đổi LLM từ qwen3:8b local sang cloud. Đổi luôn
embedding là đổi HAI biến, và khi read/multi_source lệch thì không quy được cho
biến nào. Gemini viết sẵn nhưng TẮT — lật sau, đo riêng, sau eval-gate kế hoạch C.

Interface tách embed_texts/embed_query vì hai bên bất đối xứng khác nhau: bge-m3
đối xứng, Gemini phân biệt RETRIEVAL_DOCUMENT với RETRIEVAL_QUERY.

Marker chống lệch: provider đang bật lệch với DB → RuntimeError lúc khởi động.
Vector hai provider nằm hai không gian khác nhau; truy vấn chéo trả rác mà KHÔNG
báo lỗi — im lặng sai tệ hơn app không lên. Cùng triết lý fail-loud với
PostgresUsageStore kiểm bảng llm_usage ở kế hoạch A."
```

---

### Task 6: Port `erp_query/` — 15 file

Chỉ import `..rag` (đã có sau Task 4–5). Không đụng gì tới `llm/`.

**Files:**
- Create: `backend/src/erp_query/` — `__init__.py`, `gateway.py`, `transport.py`, `sales.py`, `purchase.py`, `inventory.py`, `mrp.py`, `crm.py`, `accounting.py`, `tools.py`, `resolve.py`, `semantic.py`, `envelope.py`, `sync_index.py`, `eval_resolve.py`, `eval_resolve_cases.json`, `schema.sql`
- Test: `backend/tests/erp_query/` — 13 file

**Interfaces:**
- Consumes: `rag/` (Task 4–5)
- Produces: `erp_query.tools` (32 tool ERP) — Task 10 (`nodes.py`) và Task 13 (`erp_agent.py`) dùng

- [ ] **Bước 1: Chép mã nguồn**

```bash
mkdir -p backend/src/erp_query
cp "/d/Project/backend/src/erp_query/"*.py backend/src/erp_query/
cp "/d/Project/backend/src/erp_query/"*.json backend/src/erp_query/
cp "/d/Project/backend/src/erp_query/"*.sql backend/src/erp_query/
rm -rf backend/src/erp_query/__pycache__
```

- [ ] **Bước 2: Chép test**

```bash
mkdir -p backend/tests/erp_query
cp "/d/Project/backend/tests/erp_query/"*.py backend/tests/erp_query/
rm -rf backend/tests/erp_query/__pycache__
```

- [ ] **Bước 3: Chạy test, ghi lại cái gì đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/erp_query/ -v`

Ghi CHÍNH XÁC test nào đỏ, thông báo lỗi gì. Phân loại từng cái theo **quy tắc port test**:
- Đỏ vì đường import, biến môi trường thiếu, đường dẫn file → **hạ tầng**, sửa nối dây.
- Đỏ vì kết quả tính toán khác, khẳng định nghiệp vụ sai → **hành vi**, DỪNG và báo cáo. KHÔNG sửa test.

`gateway.py` có 4 guard bảo mật; `transport.py` là cửa ra Odoo qua `xmlrpc`. Test của chúng dùng mock nên không cần Odoo thật.

- [ ] **Bước 4: Sửa nối dây**

Chỉ loại "hạ tầng". Dự kiến đường import `from ..rag import ...` vẫn đúng vì cấu trúc giống hệt. Nếu có test cần biến môi trường Odoo, chúng đã có mặc định trong `.env.example` (Task 3).

- [ ] **Bước 5: Chạy lại**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/erp_query/ tests/rag/ -v -m "not integration and not live"`
Expected: toàn bộ PASS.

Rồi toàn bộ: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -v`
Expected: 104 test llm/ + test rag/ + test erp_query/ đều PASS.

- [ ] **Bước 6: Commit**

```bash
git add backend/src/erp_query backend/tests/erp_query
git commit -m "feat(erp_query): port tầng truy vấn ERP — 15 file

Chỉ import ..rag, không đụng llm/. gateway.py giữ nguyên 4 guard bảo mật,
transport.py giữ nguyên cửa ra Odoo qua xmlrpc.

13 test port nguyên văn. Test đỏ vì đường import/biến môi trường thì sửa nối
dây; đỏ vì hành vi đổi thì dừng điều tra — quy tắc port test của kế hoạch."
```

---

### Task 7: Chẻ MCP server Odoo theo domain

`mcp-servers/odoo/server.py` hiện 1865 dòng. Các helper (`security.py`, `rate_limit.py`, `audit_chain.py`, `event_log.py`, `helpers.py`, `config.py`) đã là file riêng sẵn.

**Không phải refactor lạc đề:** SP-2 cần cấp cho mỗi specialist agent một tập tool hẹp riêng — đường cắt theo domain chính là đường biên SP-2 sẽ dùng.

**Files:**
- Create: `mcp-servers/odoo/` — `server.py`, `odoo_call.py`, `security.py`, `rate_limit.py`, `audit_chain.py`, `event_log.py`, `helpers.py`, `config.py`, `verify_audit_chain.py`, `Dockerfile`
- Create: `mcp-servers/odoo/tools/` — `__init__.py`, `sales.py`, `purchase.py`, `inventory.py`, `mrp.py`, `crm.py`, `accounting.py`
- Create: `mcp-servers/odoo/requirements.txt`
- Test: `backend/tests/mcp/test_odoo_tool_boundary.py`

**Interfaces:**
- Consumes: không (tiến trình riêng, không import gì từ `backend/src/`)
- Produces: 32 MCP tool qua SSE `:8001` — Task 13 (`erp_agent.py`) nối qua `MultiServerMCPClient`

- [ ] **Bước 1: Chép nguyên trạng trước, chẻ sau**

```bash
mkdir -p mcp-servers/odoo
cp "/d/Project/mcp-servers/odoo/"*.py mcp-servers/odoo/
cp "/d/Project/mcp-servers/odoo/Dockerfile" mcp-servers/odoo/
rm -rf mcp-servers/odoo/__pycache__
```

Chẻ một file 1865 dòng mà chưa có gì chạy được để so sánh là mù. Chép trước, xác nhận nó khởi động được, rồi mới chẻ.

- [ ] **Bước 2: Viết `requirements.txt` cho MCP server**

`mcp-servers/odoo/requirements.txt` — server này là tiến trình riêng, venv riêng, và dùng `psycopg2` (KHÁC `psycopg` 3 của backend):

```
mcp==1.28.0
psycopg2-binary==2.9.12
```

- [ ] **Bước 3: Đếm tool trước khi chẻ**

```bash
cd mcp-servers/odoo && grep -c "@mcp.tool" server.py
```
Ghi lại con số. Sau khi chẻ, tổng số `@mcp.tool` trên toàn bộ `tools/*.py` phải **bằng đúng** con số này. Đây là lưới an toàn rẻ nhất chống đánh rơi tool lúc chẻ.

- [ ] **Bước 4: Viết test bất biến TRƯỚC khi chẻ**

`backend/tests/mcp/test_odoo_tool_boundary.py`:

```python
"""Bất biến bảo vệ cú chẻ MCP server theo domain (spec SP-1B §3c).

Chẻ file là lúc dễ đánh rơi một guard bảo mật nhất: một tool được chuyển sang
module mới mà quên đi qua odoo_call.odoo() sẽ vòng qua CẢ NĂM cổng bảo mật
(xác thực, rate limit, denylist, audit chain, event log) mà không ai thấy —
nó vẫn chạy đúng, chỉ là không được kiểm.

Test này duyệt registry FastMCP thật, lấy mã nguồn từng tool đã đăng ký, và
khẳng định không tool nào nói chuyện thẳng với Odoo.
"""
import inspect
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"

# Hai cái tên này là đường ra Odoo trực tiếp. Chỉ odoo_call.py được nhắc tới.
CAM = ("ServerProxy", "execute_kw")


@pytest.fixture(scope="module")
def cac_tool():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
    except ImportError as exc:
        pytest.skip(f"không import được server.py: {exc}")
    finally:
        sys.path.remove(str(MCP_DIR))
    reg = getattr(server.mcp, "_tool_manager", None)
    tools = getattr(reg, "_tools", None) if reg else None
    if not tools:
        pytest.skip("không đọc được registry FastMCP — cấu trúc nội bộ đã đổi")
    return tools


def test_khong_tool_nao_goi_thang_odoo(cac_tool):
    vi_pham = []
    for ten, tool in cac_tool.items():
        fn = getattr(tool, "fn", None) or getattr(tool, "func", None)
        if fn is None:
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        for cam in CAM:
            if cam in src:
                vi_pham.append(f"{ten} nhắc {cam!r} trực tiếp")
    assert not vi_pham, (
        "mọi đường ra Odoo phải qua odoo_call.odoo():\n" + "\n".join(vi_pham))


def test_chi_odoo_call_duoc_nhac_ServerProxy():
    """Quét file, không quét registry — bắt được cả tool chưa đăng ký."""
    vi_pham = []
    for path in sorted((MCP_DIR / "tools").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for cam in CAM:
            if cam in text:
                vi_pham.append(f"{path.name} nhắc {cam!r}")
    assert not vi_pham, "\n".join(vi_pham)
```

- [ ] **Bước 5: Chạy test — nó phải ĐỎ hoặc SKIP lúc này**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/mcp/ -v`
Expected: `test_chi_odoo_call_duoc_nhac_ServerProxy` FAIL (chưa có `tools/`) hoặc test đầu SKIP. Ghi lại kết quả thật.

- [ ] **Bước 6: Tách `odoo_call.py`**

Đọc `mcp-servers/odoo/server.py`, tìm hàm gọi Odoo (chỗ dùng `ServerProxy`/`execute_kw`) cùng năm cổng bảo mật quanh nó. Chuyển nguyên vào `mcp-servers/odoo/odoo_call.py`, mở đầu bằng:

```python
"""Cửa DUY NHẤT ra Odoo — mọi tool phải đi qua đây (spec SP-1B §3c).

Năm cổng bảo mật nằm ở hàm odoo() bên dưới: xác thực, rate limit, denylist,
audit chain, event log. Một tool gọi thẳng ServerProxy/execute_kw sẽ vòng qua
CẢ NĂM mà vẫn chạy đúng — nên sai sót loại này không lộ ra bằng test chức năng,
chỉ lộ khi có sự cố và không ai truy được dấu vết.

backend/tests/mcp/test_odoo_tool_boundary.py ép bất biến này: nó lấy
inspect.getsource() của từng tool đã đăng ký và khẳng định không tool nào nhắc
ServerProxy hay execute_kw.
"""
```

- [ ] **Bước 7: Chẻ tool theo domain**

Tạo `mcp-servers/odoo/tools/__init__.py` và sáu module. Chuyển từng nhóm `@mcp.tool` sang đúng module theo domain: `sales.py`, `purchase.py`, `inventory.py`, `mrp.py`, `crm.py`, `accounting.py`.

Đối chiếu tên tool với 6 module domain của `backend/src/erp_query/` (Task 6) để biết tool nào thuộc nhóm nào — hai bên dùng chung cách chia domain.

`server.py` còn lại **chỉ ba việc**: khởi tạo FastMCP, import 6 module tool để chúng tự đăng ký, và chạy. Mở đầu:

```python
"""MCP server Odoo — chỉ khởi tạo, đăng ký, chạy.

Toàn bộ tool nằm ở tools/ chia theo domain; mọi đường ra Odoo nằm ở
odoo_call.py. Đường cắt theo domain là đường biên SP-2 sẽ dùng để cấp cho mỗi
specialist agent một tập tool hẹp riêng.
"""
```

- [ ] **Bước 8: Đếm lại tool**

```bash
cd mcp-servers/odoo && grep -c "@mcp.tool" tools/*.py | awk -F: '{s+=$2} END {print s}'
```
Expected: bằng ĐÚNG con số ghi ở Bước 3. Lệch một cái là rơi một tool — dừng lại tìm.

- [ ] **Bước 9: Chạy test bất biến**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/mcp/ -v`
Expected: cả hai test PASS.

- [ ] **Bước 10: Kiểm server khởi động được**

```bash
cd mcp-servers/odoo && python -c "import server; print(f'tool đã đăng ký: {len(server.mcp._tool_manager._tools)}')"
```
Expected: in ra đúng số tool ở Bước 3. Nếu `_tool_manager` không tồn tại (cấu trúc FastMCP đổi), tìm thuộc tính tương đương và ghi lại trong báo cáo — test ở Bước 4 cũng cần cập nhật cho khớp.

- [ ] **Bước 11: Commit**

```bash
git add mcp-servers backend/tests/mcp
git commit -m "refactor(mcp): chẻ server Odoo 1865 dòng theo domain

Không phải refactor lạc đề: SP-2 cần cấp cho mỗi specialist agent một tập tool
hẹp riêng, và đường cắt theo domain chính là đường biên SP-2 sẽ dùng.

odoo_call.py là cửa DUY NHẤT ra Odoo, giữ cả 5 cổng bảo mật. tools/ chia 6 module
theo domain, khớp cách chia của backend/src/erp_query/. server.py còn đúng ba
việc: khởi tạo FastMCP, import để đăng ký, chạy.

Test bất biến duyệt registry FastMCP, lấy inspect.getsource() từng tool và khẳng
định không tool nào nhắc ServerProxy/execute_kw — chẻ file là lúc dễ đánh rơi
một guard nhất, mà rơi guard thì tool vẫn chạy đúng nên test chức năng không bắt
được."
```

---

### Task 8: `agents/models.py` → mặt tiền mỏng

Một trong bốn điểm thiết kế thật. File gốc xuất mười thứ nhưng **chỉ hai thứ thực sự được import** (đã quét cả cây nguồn).

**Files:**
- Create: `backend/src/agents/__init__.py`, `backend/src/agents/models.py`
- Test: `backend/tests/agents/__init__.py`, `backend/tests/agents/test_models.py`
- Reference: `D:\Project\backend\src\agents\models.py` (83 dòng)

**Interfaces:**
- Consumes: `llm.router.build_router`, `llm.router.make_llms` (kế hoạch A + Task 2)
- Produces: `agents.models.make_llms()` (KHÔNG tham số), `agents.models.llms_from_single(llm)` — Task 10 (`graph.py`) và Task 13 (`erp_agent.py`) dùng

- [ ] **Bước 1: Viết test thất bại**

`backend/tests/agents/test_models.py`:

```python
"""models.py sau khi thành mặt tiền — chỉ còn hai thứ.

Test không chạm mạng: build_router() bị thay bằng router dùng sổ trong bộ nhớ.
"""
import pytest

from src.agents import models
from src.llm.budget import BudgetLedger
from src.llm.catalog import ROLES
from src.llm.router import Router, RoutedChatModel
from src.llm.store import InMemoryUsageStore


@pytest.fixture
def router_gia(monkeypatch):
    """Thay build_router() để không cần Postgres."""
    r = Router(BudgetLedger(InMemoryUsageStore()))
    monkeypatch.setattr(models, "build_router", lambda: r)
    return r


def test_make_llms_khong_tham_so_va_du_moi_vai(router_gia):
    """Hợp đồng CŨ của erp_agent.py: make_llms() gọi không tham số."""
    llms = models.make_llms()
    assert set(llms) == set(ROLES)
    assert all(isinstance(v, RoutedChatModel) for v in llms.values())


def test_llms_from_single_van_con_cho_test_cu():
    """graph.py chuẩn hoá về mapping qua hàm này — hợp đồng cũ phải giữ."""
    mock = object()
    got = models.llms_from_single(mock)
    assert set(got) == set(ROLES)
    assert all(v is mock for v in got.values())


@pytest.mark.parametrize("da_bo", [
    "CLOUD_ALLOWED", "LITELLM_URL", "LITELLM_KEY", "default_model",
    "is_qwen", "model_for", "make_llm",
])
def test_moi_thu_gan_voi_litellm_va_qwen_da_bi_xoa(da_bo):
    """Bảy thứ này thuộc kiến trúc cũ. Còn sót lại là còn đường quay về nó."""
    assert not hasattr(models, da_bo), f"{da_bo} lẽ ra đã bị xoá"


def test_co_khoi_binh_luan_supersession_QD_M2():
    """Spec Phụ lục B: quyết định nào phiên sau không được lật lại thì phải có
    bình luận trong file tracked, ngay tại điểm code nó chi phối."""
    import pathlib
    src = pathlib.Path(models.__file__).read_text(encoding="utf-8")
    assert "M2" in src, "thiếu tham chiếu QĐ M2"
    assert "ADR-009" in src, "thiếu tham chiếu ADR-009"
    assert "ADR-011" in src, "thiếu trỏ tới ADR-011 (lý do đầy đủ)"
```

- [ ] **Bước 2: Chạy test để chắc chắn nó thất bại**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_models.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'src.agents'`

- [ ] **Bước 3: Viết `models.py`**

```python
"""Mặt tiền LLM cho tầng agents — mỏng, chỉ chuyển tiếp sang llm/router.py.

Toàn bộ trí tuệ chọn model nằm ở src/llm/ (kế hoạch A): catalog hạn mức thật,
sổ ngân sách cửa sổ trượt, tụt mắt xích khi cạn hoặc lỗi. File này chỉ giữ đúng
hai cái tên mà agents/ đã gọi từ trước, để port sang không phải sửa chỗ gọi nào.

─── QĐ M2 CỦA ADR-009 BỊ THAY THẾ CÓ CHỦ ĐÍCH, KHÔNG PHẢI BỊ QUÊN ─────────────

Bản cũ của file này có CLOUD_ALLOWED = frozenset({"router", "evaluator",
"chitchat"}) và ép nó ở ngay tầng thực thi: bốn vai mang dữ liệu nghiệp vụ
(read, planner, fusion, synthesis — tên khách, đơn hàng, tồn kho, tài liệu nội
bộ) LUÔN chạy model local, env override cho chúng bị bỏ qua có chủ đích.

SP-1 bỏ Ollama khỏi đường chat, nên bốn vai đó không còn chỗ nào ngoài cloud.
Đây là thay thế một quyết định đã khoá, và nó được chấp nhận vì: dữ liệu Odoo
trong hệ này là dữ liệu demo, và project là demo/portfolio (chủ dự án xác nhận
2026-07-28).

Dữ kiện đi kèm, để phiên sau không phải đoán lại: tier TRẢ PHÍ của
Anthropic/OpenAI mặc định không dùng dữ liệu API để huấn luyện, còn free tier
của Google AI Studio thì CÓ. Nên ranh giới đúng không phải "cloud hay local" mà
là "free demo bây giờ / trả phí thật về sau" — và khi hệ này mang dữ liệu thật,
đường đi là chuyển sang tier trả phí, không phải quay lại local.

Lý do đầy đủ: docs/ADR-011-sp1-foundation.md mục 1.

─── HAI HẰNG SỐ HIỆU CHỈNH CHO qwen3:8b ĐÃ THÀNH DỮ LIỆU CATALOG ─────────────

Bản cũ có max_tokens=4096 cho vai planner — circuit breaker cho vòng sinh không
dừng đã xác nhận của qwen3:8b (quan sát 7000+ token), hiệu chỉnh riêng cho model
đó: ~3.3 lần nhu cầu hợp lệ cao nhất đo được (1250 token), ở tốc độ ~65
token/giây. Và timeout = 120 if is_qwen(name) else 30.

Cả hai giả định — token "thinking" vô hình và tốc độ sinh — đều không còn đúng
với Gemini hay Groq. Chúng vẫn là lưới an toàn THẬT, nên không bỏ đi: chúng
thành spec.max_output_tokens và spec.timeout_s trong llm/catalog.py, tức ngưỡng
theo từng model thay vì một hằng số ghim cho một model đã rời hệ thống.
"""
from ..llm.catalog import ROLES
from ..llm.router import RoutedChatModel, build_router
from ..llm.router import make_llms as _make_llms_router


def make_llms() -> dict[str, RoutedChatModel]:
    """dict vai → model. KHÔNG tham số — giữ đúng hợp đồng cũ của erp_agent.py.

    Khác với llm.router.make_llms(router, pins=None) vốn cần router: hàm này tự
    dựng router cho đường chạy thật (sổ ngân sách Postgres).
    """
    return _make_llms_router(build_router())


def llms_from_single(llm) -> dict:
    """Back-compat cho test/caller cũ: mọi vai dùng chung 1 llm.

    graph.py chuẩn hoá tham số llm qua hàm này (nhận dict thì dùng luôn, nhận
    một object thì trải ra mọi vai), nên nó phải sống sót qua cú port.
    """
    return {role: llm for role in ROLES}
```

- [ ] **Bước 4: Tạo `__init__.py`**

```bash
touch backend/src/agents/__init__.py backend/tests/agents/__init__.py
```

- [ ] **Bước 5: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_models.py -v`
Expected: 11 test PASS (2 + 7 parametrize + 2).

- [ ] **Bước 6: Kiểm ranh giới tầng vẫn nguyên**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/llm/test_boundaries.py -v`
Expected: PASS. `agents/` import `llm/` là hợp lệ (một chiều đúng hướng); test này chỉ chặn chiều ngược lại.

- [ ] **Bước 7: Commit**

```bash
git add backend/src/agents backend/tests/agents
git commit -m "feat(agents): models.py thành mặt tiền mỏng trên llm/router.py

File gốc xuất mười thứ nhưng chỉ hai thứ thực sự được import (đã quét cả cây
nguồn): erp_agent.py gọi make_llms(), graph.py gọi llms_from_single(). Nên mặt
tiền đúng nghĩa mỏng — bảy thứ còn lại (CLOUD_ALLOWED, LITELLM_*, default_model,
is_qwen, model_for, make_llm) xoá hẳn, có test khẳng định chúng đã biến mất.

Giữ khối bình luận ghi QĐ M2 của ADR-009 bị thay thế CÓ CHỦ ĐÍCH: bỏ Ollama nên
4 vai mang dữ liệu không còn chỗ nào ngoài cloud; chấp nhận vì dữ liệu demo và
project là portfolio. Kèm dữ kiện tier trả phí không huấn luyện trên dữ liệu API
còn free tier Google AI Studio thì có — nên ranh giới đúng là 'free demo giờ /
trả phí thật sau', không phải 'cloud hay local'.

max_tokens=4096 và timeout=120-nếu-qwen thành spec.max_output_tokens và
spec.timeout_s: vẫn là lưới an toàn thật, chỉ là theo model thay vì hằng số ghim
cho model đã rời hệ thống."
```

---

### Task 9: Port security gates

Năm file nhỏ nhưng là thứ chặn thao tác ghi ERP không hoàn tác được. Port trước các node vì node import chúng.

**Files:**
- Create: `backend/src/agents/write_gate.py` (55 dòng), `agentic_gate.py` (38), `write_registry.py` (126), `skill_gate.py` (26), `tool_leak_guard.py` (29)
- Test: `backend/tests/agents/test_write_gate.py`, `test_skill_gate.py`, `test_tool_leak_guard.py`, `test_write_planner_keys.py`, `test_write_state_hygiene.py`

**Interfaces:**
- Consumes: `erp_query/` (Task 6)
- Produces: `write_gate`, `agentic_gate`, `write_registry`, `skill_gate`, `tool_leak_guard` — Task 11–12 dùng

- [ ] **Bước 1: Chép**

```bash
for f in write_gate agentic_gate write_registry skill_gate tool_leak_guard; do
  cp "/d/Project/backend/src/agents/$f.py" backend/src/agents/
done
for f in test_write_gate test_skill_gate test_tool_leak_guard \
         test_write_planner_keys test_write_state_hygiene; do
  cp "/d/Project/backend/tests/agents/$f.py" backend/tests/agents/
done
```

`skill_gate.py` và `tool_leak_guard.py` port **nhưng nằm im tới SP-2** — chúng bé, và mất chúng đắt hơn giữ. Test của chúng vẫn port.

- [ ] **Bước 2: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/ -v`
Expected: một số FAIL vì import module chưa port (`state`, `nodes`…). Ghi lại chính xác.

- [ ] **Bước 3: Sửa nối dây, hoặc hoãn**

Test nào đỏ chỉ vì import module Task 10–12 sẽ port: **để nguyên, ghi vào báo cáo**, không sửa. Chúng sẽ tự xanh khi module tới.

Test nào đỏ vì hành vi: DỪNG, báo cáo.

- [ ] **Bước 4: Chạy phần chạy được**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_write_gate.py tests/agents/test_skill_gate.py tests/agents/test_tool_leak_guard.py -v`
Expected: PASS (ba file này ít phụ thuộc nhất).

- [ ] **Bước 5: Commit**

```bash
git add backend/src/agents backend/tests/agents
git commit -m "feat(agents): port 5 security gate

write_gate và agentic_gate chặn thao tác ghi ERP không hoàn tác được —
fail-closed, ngược với budget fail-open của kế hoạch A, và cố ý như vậy.

skill_gate và tool_leak_guard port nhưng nằm im tới SP-2: chúng bé, và mất
chúng đắt hơn giữ.

Test nào còn đỏ vì import module Task 10-12 chưa port thì để nguyên — sẽ tự
xanh khi module tới, không sửa test để che."
```

---

### Task 10: Port graph lõi — `state`, `prompts`, `nodes`, `graph`

Trái tim điều phối. `nodes.py` (323 dòng) là file lớn nhất của `agents/`.

**Files:**
- Create: `backend/src/agents/state.py` (25), `prompts.py` (163), `nodes.py` (323), `graph.py` (130)
- Test: `backend/tests/agents/test_graph_build.py`, `test_intent_router.py`, `test_prompts.py`, `test_simple_nodes.py`, `test_planner_context.py`, `test_planner_json_retry.py`, `test_context_flow.py`

**Interfaces:**
- Consumes: `models.make_llms`/`llms_from_single` (Task 8), gates (Task 9), `erp_query/` (Task 6), `rag/` (Task 4–5)
- Produces: `graph.build_graph()`, `state.AgentState` — Task 13 (`erp_agent.py`) dùng

- [ ] **Bước 1: Chép bốn file + test**

```bash
for f in state prompts nodes graph; do
  cp "/d/Project/backend/src/agents/$f.py" backend/src/agents/
done
for f in test_graph_build test_intent_router test_prompts test_simple_nodes \
         test_planner_context test_planner_json_retry test_context_flow; do
  cp "/d/Project/backend/tests/agents/$f.py" backend/tests/agents/
done
```

- [ ] **Bước 2: Đọc `graph.py` dòng 79–80**

Bản gốc:
```python
    # role→llm (production, từ make_llms()). Normalize về mapping.
    llms = llm if isinstance(llm, dict) else llms_from_single(llm)
```
Đoạn này **không đổi** — `make_llms()` của Task 8 vẫn trả dict vai → model, và `llms_from_single` vẫn còn. Xác nhận nó nguyên vẹn sau khi chép.

- [ ] **Bước 3: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/ -v`
Expected: nhiều test PASS hơn Task 9; số còn đỏ là do node Task 11–12 chưa port. Ghi CHÍNH XÁC danh sách đỏ và lý do từng cái.

- [ ] **Bước 4: Đối chiếu với kết quả spike Task 1**

Mở `docs/spikes/2026-07-29-port-cloud-model.md`, bảng "Kết luận chi phối task sau". Với mỗi dòng ảnh hưởng tới `nodes.py`/`prompts.py`, kiểm xem nó đã được xử lý chưa:
- `.content` list-shape → đã gộp ở `Router._finish()` (Task 2), node không phải biết.
- Prompt planner sinh JSON hỏng → nếu spike thấy hỏng, đây là chỗ sửa prompt. **Nếu phải sửa prompt, ghi rõ sửa gì và vì sao trong commit** — đổi prompt là đổi biến, và kế hoạch C sẽ đo nó.
- `finish_reason` khác hình dạng → tìm chỗ `nodes.py` đọc `finish_reason`, sửa cho khớp.

- [ ] **Bước 5: Chạy lại**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_graph_build.py tests/agents/test_intent_router.py tests/agents/test_prompts.py -v`
Expected: PASS.

- [ ] **Bước 6: Commit**

```bash
git add backend/src/agents backend/tests/agents
git commit -m "feat(agents): port graph lõi — state, prompts, nodes, graph

graph.py dòng 80 (llms = llm if isinstance(llm, dict) else llms_from_single(llm))
không phải sửa: make_llms() của mặt tiền vẫn trả dict vai → model, đúng hợp đồng
cũ. Đây là lý do mặt tiền tồn tại.

Đối chiếu với bảng kết luận của spike Task 1: .content list-shape đã xử lý ở
Router._finish() nên node không phải biết."
```

---

### Task 11: Port node hỗ trợ

Chín node quanh trục chính: đàm thoại, xác nhận, chống bịa, tổng hợp.

**Files:**
- Create: `backend/src/agents/` — `confirmation.py` (98), `continuation.py` (57), `disambiguation.py` (23), `friction.py` (39), `erp_grounding.py` (44), `synthesis.py` (141), `fusion.py` (100), `tool_result.py` (37), `working_context.py` (56)
- Test: `test_confirmation.py`, `test_confirmation_gate.py`, `test_continuation.py`, `test_disambiguation.py`, `test_friction.py`, `test_erp_grounding.py`, `test_synthesis.py`, `test_fusion.py`, `test_tool_result.py`, `test_working_context.py`, `test_parse_write_result.py`, `test_resume_decision.py`, `test_chat_resume.py`, `test_fresh_reset.py`, `test_auto_chain.py`

**Interfaces:**
- Consumes: `state`, `nodes` (Task 10), gates (Task 9), `rag/` (Task 4–5)
- Produces: 9 node — `nodes.py`/`graph.py` gọi

- [ ] **Bước 1: Chép**

```bash
for f in confirmation continuation disambiguation friction erp_grounding \
         synthesis fusion tool_result working_context; do
  cp "/d/Project/backend/src/agents/$f.py" backend/src/agents/
done
for f in test_confirmation test_confirmation_gate test_continuation \
         test_disambiguation test_friction test_erp_grounding test_synthesis \
         test_fusion test_tool_result test_working_context \
         test_parse_write_result test_resume_decision test_chat_resume \
         test_fresh_reset test_auto_chain; do
  cp "/d/Project/backend/tests/agents/$f.py" backend/tests/agents/
done
```

- [ ] **Bước 2: Xác nhận `fusion.py` được giữ nguyên**

`fusion` là nhánh intent `mixed` — ReAct agent bind sẵn cả tool đọc ERP lẫn `search_documents`. Nó **sẽ** biến mất ở SP-2 (đã ghi sẵn trong `evals/cases.py:325` từ SP-0), nhưng **không phải ở SP-1**, vì lý do một-biến: `multi_source` có số "trước" đo trên qwen3:8b *với topology fusion*. Đổi topology cùng lúc đổi model là đổi hai biến.

Không sửa gì trong `fusion.py`. Nếu thấy nó "thừa", đó là hiểu nhầm — đọc lại đoạn này.

- [ ] **Bước 3: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/ -v`
Expected: đa số PASS. Còn đỏ là các test cần write node (Task 12) và `erp_agent` (Task 13).

- [ ] **Bước 4: Phân loại từng test đỏ**

Áp dụng quy tắc port test. `synthesis.py` chứa `cite_and_verify` (footer trích dẫn tất định), `verify_erp_grounding` (kiểm chống bịa đối chiếu tool output), `passes_floor` (lọc retrieval lạc đề), bộ lọc `WRITE_TOOL_NAMES` — bốn thứ này là máy móc chống bịa, test của chúng đỏ vì hành vi là chuyện nghiêm trọng. DỪNG và báo cáo.

- [ ] **Bước 5: Chạy lại nhóm chạy được**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_synthesis.py tests/agents/test_fusion.py tests/agents/test_erp_grounding.py tests/agents/test_confirmation.py -v`
Expected: PASS.

- [ ] **Bước 6: Commit**

```bash
git add backend/src/agents backend/tests/agents
git commit -m "feat(agents): port 9 node hỗ trợ

fusion.py giữ NGUYÊN dù SP-2 sẽ bỏ nó: multi_source có số 'trước' đo trên
qwen3:8b VỚI topology fusion, nên đổi topology cùng lúc đổi model là đổi hai
biến và không quy được kết quả cho biến nào.

synthesis.py mang bốn thứ chống bịa dùng chung (cite_and_verify,
verify_erp_grounding, passes_floor, lọc WRITE_TOOL_NAMES) — đó cũng là lý do bỏ
fusion ở SP-2 sẽ là DỜI đám máy móc này chứ không phải bỏ."
```

---

### Task 12: Port write node

Tám file, ~1650 dòng — nhóm lớn nhất. Đây là đường ghi vào ERP: không hoàn tác được, nên `write_gate` fail-closed bảo vệ chúng.

**Files:**
- Create: `backend/src/agents/` — `create_order.py` (204), `edit_order.py` (225), `bom_write.py` (291), `crm_write.py` (227), `inventory_write.py` (186), `mrp_write.py` (136), `purchase_write.py` (239), `returns_write.py` (150)
- Test: `test_create_order_helpers.py`, `test_create_order_node.py`, `test_edit_order_node.py`, `test_create_rfq_flow.py`, `test_bom_write.py`, `test_crm_write.py`, `test_inventory_write.py`, `test_mrp_write.py`, `test_purchase_write.py`, `test_returns_write.py`

**Interfaces:**
- Consumes: `write_gate`, `write_registry` (Task 9), `erp_query/` (Task 6), `state` (Task 10)
- Produces: 8 write node — `graph.py` nối vào

- [ ] **Bước 1: Chép**

```bash
for f in create_order edit_order bom_write crm_write inventory_write \
         mrp_write purchase_write returns_write; do
  cp "/d/Project/backend/src/agents/$f.py" backend/src/agents/
done
for f in test_create_order_helpers test_create_order_node test_edit_order_node \
         test_create_rfq_flow test_bom_write test_crm_write \
         test_inventory_write test_mrp_write test_purchase_write \
         test_returns_write; do
  cp "/d/Project/backend/tests/agents/$f.py" backend/tests/agents/
done
```

- [ ] **Bước 2: Chạy test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/ -v`
Expected: gần như toàn bộ PASS. Chỉ còn test cần `erp_agent` (Task 13) là đỏ.

- [ ] **Bước 3: Kiểm `write_gate` vẫn chặn**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_write_gate.py tests/agents/test_write_state_hygiene.py tests/agents/test_write_planner_keys.py -v`
Expected: PASS. Ba file này ép bất biến "không thao tác ghi nào lọt qua mà chưa xác nhận" — đỏ ở đây là lỗi nghiêm trọng nhất kế hoạch này có thể tạo ra.

- [ ] **Bước 4: Commit**

```bash
git add backend/src/agents backend/tests/agents
git commit -m "feat(agents): port 8 write node

Đường ghi vào ERP — không hoàn tác được, nên write_gate fail-closed bảo vệ
chúng (ngược với budget fail-open của kế hoạch A, và cố ý như vậy: budget chỉ
chắn một cái 429 tự lành, còn đây là thao tác không rút lại được).

test_write_gate / test_write_state_hygiene / test_write_planner_keys ép bất biến
'không thao tác ghi nào lọt qua mà chưa xác nhận' — đỏ ở đó là lỗi nghiêm trọng
nhất cú port này có thể tạo ra."
```

---

### Task 13: Port `erp_agent.py` + xác minh đầu-cuối

Đỉnh của cây. `ERPAgent` là singleton dựng một lần, nối MCP client và giữ `make_llms()`.

**Files:**
- Create: `backend/src/agents/erp_agent.py` (256 dòng)
- Test: `backend/tests/agents/test_erp_agent_resume.py`, `test_models.py` (đã có), `backend/tests/test_thread_id.py`, `backend/tests/test_live_verify_common.py`
- Test mới: `backend/tests/agents/test_dau_cuoi.py`

**Interfaces:**
- Consumes: tất cả Task 4–12
- Produces: `ERPAgent` — kế hoạch C bọc HTTP quanh nó

- [ ] **Bước 1: Chép**

```bash
cp "/d/Project/backend/src/agents/erp_agent.py" backend/src/agents/
cp "/d/Project/backend/tests/agents/test_erp_agent_resume.py" backend/tests/agents/
cp "/d/Project/backend/tests/test_thread_id.py" backend/tests/
cp "/d/Project/backend/tests/test_live_verify_common.py" backend/tests/
cp "/d/Project/backend/tests/live_verify_common.py" backend/tests/ 2>/dev/null || true
```

- [ ] **Bước 2: Xác nhận `erp_agent.py` dòng 18 và 136 không phải sửa**

Bản gốc:
```python
from .models import make_llms      # dòng 18
...
        self._llms = make_llms()   # dòng 136
```
Cả hai **không đổi** — mặt tiền Task 8 giữ đúng tên và chữ ký. Đây là toàn bộ lý do mặt tiền tồn tại. Xác nhận sau khi chép.

Dòng 233–237 có docstring nhắc `CLOUD_ALLOWED` và `model_for()` (đã xoá ở Task 8). Sửa docstring đó cho khớp thực tế: vai `chitchat` giờ chạy model cloud như mọi vai khác, không còn khái niệm "cloud-eligible". Ghi rõ trong commit rằng đây là sửa **docstring**, không phải sửa hành vi.

- [ ] **Bước 3: Chạy toàn bộ test agents**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v -m "not integration and not live"`
Expected: **toàn bộ PASS.** Đây là lần đầu cả 62 test port + test mới cùng xanh.

Nếu còn đỏ: phân loại theo quy tắc port test. Đỏ vì hành vi → DỪNG, báo cáo, không sửa test.

- [ ] **Bước 4: Viết test đầu-cuối**

`backend/tests/agents/test_dau_cuoi.py`:

```python
"""Xác minh đầu-cuối kế hoạch B: câu hỏi thật → Odoo thật + RAG thật → model
cloud thật → câu trả lời.

Cần MỌI THỨ: Odoo chạy, Postgres+pgvector chạy, Ollama chạy, MCP server chạy,
và khoá API thật. Đánh dấu live vì nó gọi model thật tiêu hạn mức.

Chạy:  pytest tests/agents/test_dau_cuoi.py -m live -v
"""
import os

import pytest

pytestmark = pytest.mark.live

CAN_CO = ("GOOGLE_API_KEY", "ODOO_URL", "DATABASE_URL", "MCP_ODOO_URL")


@pytest.fixture(scope="module")
def agent():
    thieu = [k for k in CAN_CO if not os.environ.get(k)]
    if thieu:
        pytest.skip(f"thiếu biến môi trường: {thieu}")
    import asyncio

    from src.agents.erp_agent import ERPAgent

    a = ERPAgent()
    asyncio.run(a.setup())
    yield a
    asyncio.run(a.aclose())


def test_agent_dung_duoc_va_co_tool(agent):
    """Nối được MCP server và thấy tool — cú chẻ Task 7 không đánh rơi gì."""
    assert agent.tool_names, "không thấy tool nào từ MCP server"


def test_cau_hoi_that_tra_ve_cau_tra_loi_that(agent):
    """Lượt chạy đầy đủ: định tuyến intent → gọi tool → tổng hợp.

    Không khẳng định NỘI DUNG câu trả lời (dữ liệu Odoo đổi theo môi trường) —
    chỉ khẳng định đường đi thông: có trả lời, là string, không rỗng, không phải
    thông báo lỗi degrade.
    """
    import asyncio

    tra_loi = asyncio.run(agent.chat("Xin chào, bạn giúp được gì?",
                                     thread_id="test-dau-cuoi-1"))
    assert isinstance(tra_loi, str), f"trả về {type(tra_loi).__name__}, không phải str"
    assert tra_loi.strip(), "câu trả lời rỗng"
    assert "đã có lỗi xảy ra" not in tra_loi.lower(), (
        f"rơi vào nhánh degrade lỗi: {tra_loi[:200]}")


def test_cau_hoi_ERP_di_qua_tool(agent):
    """Câu hỏi cần dữ liệu ERP phải chạm tool, không phải model tự bịa."""
    import asyncio

    tra_loi = asyncio.run(agent.chat("Có bao nhiêu đơn bán hàng?",
                                     thread_id="test-dau-cuoi-2"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
```

Đọc `erp_agent.py` để lấy ĐÚNG tên phương thức (`chat`, `setup`, `aclose`, `tool_names`) và chữ ký thật — nếu khác, sửa test cho khớp mã nguồn thật, đừng sửa mã nguồn cho khớp test.

- [ ] **Bước 5: Dựng hạ tầng đầy đủ và chạy đầu-cuối**

```bash
docker compose up -d postgres
# MCP server (tiến trình riêng, cửa sổ khác):
cd mcp-servers/odoo && python server.py
# Rồi, ở cửa sổ chính:
cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_dau_cuoi.py -m live -v
```
Ollama giả định đã chạy sẵn ở nơi khác (cổng 11434) — quyết định Task 3, xem ledger. docker-compose.yml của repo này KHÔNG có service ollama.

Expected: 3 test PASS.

Nếu thiếu khoá hoặc thiếu Odoo → SKIP, và **báo cáo trung thực là SKIP, không phải PASS**. Một task mà phần xác minh cốt lõi chưa từng chạy thì chưa xong — nếu không dựng nổi hạ tầng, báo BLOCKED.

- [ ] **Bước 6: Chạy toàn bộ ba chế độ**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -v
.venv/Scripts/python.exe -m pytest -m integration -v
.venv/Scripts/python.exe -m pytest -m live -v
```
Expected: chế độ 1 toàn bộ PASS; chế độ 2 PASS (cần Postgres); chế độ 3 PASS (cần mạng + khoá + Odoo).

- [ ] **Bước 7: Commit**

```bash
git add backend/src/agents/erp_agent.py backend/tests
git commit -m "feat(agents): port erp_agent + xác minh đầu-cuối kế hoạch B

erp_agent.py dòng 18 (from .models import make_llms) và dòng 136
(self._llms = make_llms()) KHÔNG phải sửa — mặt tiền Task 8 giữ đúng tên và chữ
ký. Đó là toàn bộ lý do mặt tiền tồn tại.

Sửa docstring dòng 233-237: nó nhắc CLOUD_ALLOWED và model_for() đã xoá ở Task 8.
Sửa DOCSTRING cho khớp thực tế, không sửa hành vi — vai chitchat giờ chạy cloud
như mọi vai khác.

test_dau_cuoi.py: câu hỏi thật → Odoo thật + RAG thật → model cloud thật → câu
trả lời. Không khẳng định nội dung (dữ liệu Odoo đổi theo môi trường), chỉ khẳng
định đường đi thông và không rơi vào nhánh degrade lỗi."
```

---

## "Kế hoạch B xong" nghĩa là

1. Ba phát hiện kế hoạch A đã vá, có test (Task 2).
2. `docker-compose.yml` + `.env.example` đủ dựng hạ tầng từ repo Youdoo (Task 3).
3. `rag/`, `erp_query/`, security gates, graph `agents/` đã port; 62 test cũ xanh; 2 test viết lại xanh.
4. `agents/models.py` là mặt tiền mỏng, không còn `CLOUD_ALLOWED`/LiteLLM/`is_qwen`, có khối bình luận supersession QĐ M2.
5. `rag/embed.py` có 2 implementation (Ollama bật, Gemini tắt) + marker chống lệch fail lớn tiếng.
6. MCP server đã chẻ theo domain; test bất biến registry xanh; số tool sau khi chẻ bằng đúng số trước khi chẻ.
7. Đầu-cuối: một câu hỏi thật đi qua Odoo thật + RAG thật + model cloud thật và trả về câu trả lời — chạy từ pytest, không cần server.
8. Toàn bộ test xanh ở cả ba chế độ: `-m "not integration and not live"`, `-m integration`, `-m live`.
   (Ngoại lệ đã ghi nhận: 2 test trong test_live_providers.py đỏ vì trôi API Google thượng nguồn kể từ 2026-07-29 — không phải hồi quy từ kế hoạch này, xem ledger Task 13. Đường sản xuất thật không bị ảnh hưởng.)

**Chưa làm được sau kế hoạch B:** chưa có HTTP endpoint, chưa có trace, chưa có số eval. Đó là việc của C.

## Sau kế hoạch B

| Kế hoạch | Nội dung | Phụ thuộc |
|---|---|---|
| **C** | `main.py` FastAPI `/v1` bọc `ERPAgent` + Langfuse `tracing.py` (đổ `RouteDecision` vào span) + eval harness (13 file `tests/jobs/`) + gate 7 bộ đối chiếu baseline qwen3:8b + `multi_source` lượt hai | B |

Năm điều kiện đầu vào của kế hoạch C, ghi lại để không rơi:

- **Pool Postgres không có timeout tường minh** (`llm/store.py`) — DB không truy cập được thì mỗi lượt gọi chặn ~90 giây trước khi fail-open.
- **`Router.ainvoke()` gọi Postgres đồng bộ** — chặn event loop dưới FastAPI/LangGraph async.
- **`tiktoken` cần mạng lần dùng đầu nếu không có cache** — chạy trên đường test MẶC ĐỊNH vốn phải không chạm mạng. Máy dev đã có cache nên không lộ; **sẽ vỡ trên CI lạnh.**
- **Eval gate phải chạy TRƯỚC khi mở `/v1`** — ADR-009 QĐ M3. Kế hoạch B cố ý không tuyên bố "không hồi quy", chỉ tuyên bố "port đúng".
- **`rag/embed.py`'s `assert_embedding_marker()` không có người gọi thật** — cơ chế fail lớn tiếng khi lệch `embedding_model`/`dim` tồn tại (Task 5, có test riêng) nhưng `ERPAgent.setup()` (Task 13, đường khởi động thật của kế hoạch B) chưa gọi nó. Kế hoạch C bọc `main.py` FastAPI quanh `ERPAgent` — gọi nó ở đó, trước khi phục vụ request đầu tiên, mới đúng tinh thần "app không lên nếu lệch" của spec §3b.
