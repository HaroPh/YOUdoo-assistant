# Tách tầng định tuyến thành đơn vị có tên — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gom lớp đề xuất (LLM) và lớp veto (tất định) của tầng định tuyến —
hiện rải ở 4 file — vào một module `backend/src/agents/routing.py` có tên,
đặt lại tên theo vai từng lớp, **không đổi một hành vi nào**.

**Architecture:** Thuần di chuyển + đổi tên. `routing.py` giữ 6 symbol
(`VALID_INTENTS`, `RouteProposal`, `parse_proposal`, `make_intent_router_node`,
`_QUESTION_MARKERS`/`looks_like_question`, `decide_route`) cùng một docstring
đầu file mô tả trọn hợp đồng 2 lớp và bằng chứng đằng sau. Text prompt ở
nguyên `prompts.py`; `intent_targets` + `add_conditional_edges` ở nguyên
`graph.py` (đó là sơ đồ, không phải logic). Không có shim re-export.

**Tech Stack:** Python 3.12, LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-08-04-routing-layer-extraction-design.md`

## Global Constraints

- **KHÔNG đổi tên node graph `"intent_router"`.** Ràng buộc cứng: checkpoint
  Postgres của các hội thoại đang park ở `interrupt()` chứa tên node — đổi
  tên làm hỏng resume. Cũng bị `test_skill_nodes_reachable_only_from_intent_router`
  (`tests/agents/test_graph_build.py:327`) assert trực tiếp.
- **KHÔNG sửa GIÁ TRỊ KỲ VỌNG của test cũ.** Được phép — và bắt buộc — đổi
  *tên symbol* trong dòng `import` và trong lời gọi hàm (`_parse_router_output(`
  → `parse_proposal(`, `_route_by_intent(` → `decide_route(`,
  `_looks_like_question(` → `looks_like_question(`), kể cả khi lời gọi nằm bên
  trong một dòng `assert`. KHÔNG được đổi vế phải của phép so sánh, chuỗi
  input, hay bất kỳ giá trị kỳ vọng nào. Nếu một giá trị kỳ vọng phải sửa mới
  xanh → đã đổi hành vi → **DỪNG, báo cáo, không tự sửa cho khớp**.
- **KHÔNG để lại shim re-export** ở `nodes.py` hay `graph.py`. Import cũ phải
  chết hẳn để không chỗ nào lặng lẽ dùng đường cũ.
- **KHÔNG sửa file trong `docs/superpowers/specs/`** — đó là hồ sơ lịch sử
  ghi quyết định tại thời điểm đó, không phải tài liệu mô tả mã hôm nay.
- **KHÔNG đổi text prompt, không đụng đường ghi, không đụng fan-out.**
- Comment/docstring trong repo này viết tiếng Việt — giữ đúng văn phong.
- Chạy test: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
- Suite unit-only: thêm `-m "not integration and not live"`.
- Repo **không có linter** (không ruff/flake8/pylint) — import thừa sẽ không
  bị bắt tự động, phải tự kiểm bằng mắt theo đúng danh sách plan đã liệt kê.
- `main` đang nhận merge từ nhánh song song khác. **Không cite số test
  baseline từ plan cũ** — tự chụp ở Task 1 Step 1.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/agents/routing.py` (mới) | Toàn bộ tầng định tuyến 2 lớp + docstring giải thích hợp đồng |
| `backend/src/agents/nodes.py` | Bỏ `VALID_INTENTS`, `_parse_router_output`, `make_intent_router_node` + 2 import prompt thành thừa |
| `backend/src/agents/graph.py` | Bỏ `_QUESTION_MARKERS`, `_looks_like_question`, `_route_by_intent` + 2 import `skill_gate` thành thừa; đổi nguồn import |
| `backend/evals/run_eval.py` | Đổi nguồn import + 2 chỗ gọi tên mới |
| `backend/tests/agents/test_intent_router.py` | Đổi nguồn import; thêm 1 test mới cho `RouteProposal` |
| `backend/tests/agents/test_graph_build.py` | Đổi nguồn import (9 chỗ) + sửa comment lỗi thời |
| `backend/tests/agents/test_fanout_graph.py` | Đổi nguồn import + đổi tên test + docstring |
| `backend/src/agents/{prompts,skill_manifest,state,fanout}.py`, `backend/evals/cases.py`, `backend/tests/agents/test_build_graph_skill_integration.py` | Chỉ sửa comment trỏ tên cũ |
| `docs/superpowers/plans/2026-08-04-routing-layer-extraction-report.md` (mới) | Số đo + xác nhận |

---

### Task 1: Chuyển LỚP 1 (đề xuất) sang `routing.py`

**Files:**
- Create: `backend/src/agents/routing.py`
- Modify: `backend/src/agents/nodes.py:9-28` (import + `VALID_INTENTS`), xoá `nodes.py:31-84`
- Modify: `backend/src/agents/graph.py:6-13` (nguồn import `make_intent_router_node`)
- Modify: `backend/evals/run_eval.py:38`, `:447`
- Test: `backend/tests/agents/test_intent_router.py` (đổi import + thêm 1 test)

**Interfaces:**
- Produces:
  - `VALID_INTENTS: set[str]` = `{"erp_read", "erp_write", "rag", "mixed", "unknown"}`
  - `class RouteProposal(NamedTuple)` với field `intent: str`, `sop: str | None`
  - `parse_proposal(text: str, valid_sops) -> RouteProposal`
  - `make_intent_router_node(llm, worker_block: str = "", valid_sops=frozenset())` → async node trả `dict` `{"intent": str, "sop": str | None}`
- Consumes: `render_intent_router_prompt` từ `.prompts`, `ERPAgentState` từ `.state`

- [ ] **Step 1: Chụp baseline TRƯỚC khi sửa gì**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`

Ghi lại nguyên văn dòng tổng kết (vd `1120 passed, 4 skipped, 43 deselected`).
Con số này là mốc đối chiếu cho Task 1, 2, 3 — **không dùng số từ plan cũ**.

Run thêm: `cd D:/Youdoo && git rev-parse --short HEAD` — ghi lại SHA baseline.

- [ ] **Step 2: Tạo `routing.py` với lớp 1**

Create `backend/src/agents/routing.py`:

```python
# backend/src/agents/routing.py
"""Tầng định tuyến — LỚP 1: đề xuất (xác suất).

Lớp 2 (phủ quyết tất định) chuyển vào file này ở task kế tiếp; docstring đầy
đủ về hợp đồng 2 lớp được viết khi cả hai lớp đã có mặt, để không có commit
nào mô tả thứ chưa tồn tại.
"""
from typing import NamedTuple

from langchain_core.messages import SystemMessage, HumanMessage

from .state import ERPAgentState
from .prompts import render_intent_router_prompt

VALID_INTENTS = {"erp_read", "erp_write", "rag", "mixed", "unknown"}


class RouteProposal(NamedTuple):
    """Đầu ra của LỚP 1 — ĐỀ CỬ, chưa phải quyết định định tuyến.

    PHẢI là NamedTuple, KHÔNG được đổi sang dataclass: eval_sop_select
    (evals/run_eval.py) unpack kiểu tuple (`intent, sop = parse_proposal(...)`).
    NamedTuple vẫn LÀ tuple nên chỗ đó không gãy. Đây là ràng buộc có test
    canh (test_route_proposal_unpacks_as_tuple), không phải sở thích.
    """
    intent: str          # luôn thuộc VALID_INTENTS; "unknown" khi không parse được
    sop: str | None      # ĐỀ CỬ — lớp 2 (decide_route) có quyền bỏ


def parse_proposal(text: str, valid_sops) -> RouteProposal:
    """Parse hợp đồng 2 dòng của router. FAIL AN TOÀN ở mọi hướng:

    - intent không nhận ra → "unknown" (hành vi cũ);
    - sop không nằm trong valid_sops → None. Tên worker model bịa ra KHÔNG BAO
      GIỜ được trả ra: nó sẽ thành node đích không tồn tại và làm LangGraph ném
      lỗi định tuyến giữa một lượt chat thật;
    - không thấy dòng "intent:" nào → thử đọc cả chuỗi như MỘT TỪ intent (hợp
      đồng CŨ). Model nhỏ hay bỏ qua format; rơi về đúng hành vi hôm nay tốt
      hơn là rơi về "unknown"."""
    intent: str | None = None
    sop: str | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("intent:"):
            value = low[len("intent:"):].strip()
            if value in VALID_INTENTS:
                intent = value
        elif low.startswith("sop:"):
            value = stripped[len("sop:"):].strip()
            if value in valid_sops:
                sop = value
    if intent is None:
        bare = (text or "").strip().lower()
        intent = bare if bare in VALID_INTENTS else "unknown"
    return RouteProposal(intent, sop)


def make_intent_router_node(llm, worker_block: str = "", valid_sops=frozenset()):
    """LỚP 1 của tầng định tuyến — node LLM đề xuất `intent` + `sop` trong
    CÙNG MỘT lượt gọi (không tốn call thêm; quan trọng khi OpenRouter chỉ
    ~50 req/ngày).

    worker_block + valid_sops được TIÊM VÀO (graph.py lấy từ skill_loader) —
    routing.py cố ý không import skill_loader: node này phải test được với bất
    kỳ danh sách worker nào, kể cả rỗng.

    TÊN NODE TRONG GRAPH PHẢI GIỮ NGUYÊN "intent_router" (graph.py). Không
    phải vì thẩm mỹ: checkpoint Postgres của các hội thoại đang park ở
    interrupt() chứa tên node, đổi tên làm hỏng resume của chúng; và
    test_skill_nodes_reachable_only_from_intent_router assert thẳng tên này
    như một bất biến bảo mật."""
    prompt = render_intent_router_prompt(worker_block)
    valid_sops = frozenset(valid_sops)

    async def intent_router(state: ERPAgentState) -> dict:
        last_human = next(
            (m for m in reversed(state["messages"]) if m.type == "human"),
            None,
        )
        if not last_human:
            return {"intent": "unknown", "sop": None}

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=last_human.content),
        ])
        intent, sop = parse_proposal(response.content, valid_sops)
        # LUÔN ghi khoá "sop" (kể cả None): nó TRANSIENT, đề cử của lượt trước
        # không được sống sót sang lượt sau.
        return {"intent": intent, "sop": sop}

    return intent_router
```

- [ ] **Step 3: Xoá lớp 1 khỏi `nodes.py`**

Trong `backend/src/agents/nodes.py`:

1. Xoá **nguyên khối dòng 28 tới 84** (từ `VALID_INTENTS = {...}` tới hết
   `return intent_router`, gồm cả `_parse_router_output` và
   `make_intent_router_node`).
2. Sửa khối import prompts (dòng 14-16) — bỏ `INTENT_ROUTER_PROMPT` (vốn
   ĐÃ thừa từ trước, chỉ có ở dòng import) và `render_intent_router_prompt`
   (chỉ dùng bởi hàm vừa xoá):

Từ:
```python
from .prompts import (INTENT_ROUTER_PROMPT, SYSTEM_PROMPT, WRITE_PLANNER_PROMPT,
                      WRITE_CONFIRM_PREFIX, CHITCHAT_PROMPT, render_working_context,
                      render_intent_router_prompt)
```
Thành:
```python
from .prompts import (SYSTEM_PROMPT, WRITE_PLANNER_PROMPT,
                      WRITE_CONFIRM_PREFIX, CHITCHAT_PROMPT, render_working_context)
```

**GIỮ NGUYÊN** các import khác của `nodes.py` — đã kiểm: `SystemMessage`
còn dùng ở dòng 151/233, `HumanMessage` còn dùng ở dòng 245, `ERPAgentState`
còn dùng ở 5 node khác. Không đụng.

- [ ] **Step 4: Đổi nguồn import ở `graph.py`**

Trong `backend/src/agents/graph.py`, bỏ `make_intent_router_node` khỏi khối
`from .nodes import (...)` (dòng 6-13), rồi thêm dòng import mới ngay sau khối đó:

Từ:
```python
from .nodes import (
    make_intent_router_node,
    make_erp_read_node,
    make_erp_write_planner_node,
    make_erp_write_executor_node,
    make_rag_node,
    make_respond_unknown_node,
)
```
Thành:
```python
from .nodes import (
    make_erp_read_node,
    make_erp_write_planner_node,
    make_erp_write_executor_node,
    make_rag_node,
    make_respond_unknown_node,
)
from .routing import make_intent_router_node
```

- [ ] **Step 5: Đổi nguồn import ở `evals/run_eval.py`**

Dòng 38, từ:
```python
from src.agents.nodes import _parse_plan_tiered, _parse_router_output
```
Thành:
```python
from src.agents.nodes import _parse_plan_tiered
from src.agents.routing import parse_proposal
```

Dòng 447, từ:
```python
        intent, sop = _parse_router_output(resp.content, valid_sops)
```
Thành:
```python
        intent, sop = parse_proposal(resp.content, valid_sops)
```

- [ ] **Step 6: Đổi import ở `test_intent_router.py` — CHỈ dòng import**

Dòng 6, từ:
```python
from src.agents.nodes import _parse_router_output, make_intent_router_node
```
Thành:
```python
from src.agents.routing import parse_proposal, make_intent_router_node
```

File này còn **7 chỗ import lặp trong thân test** (`from src.agents.nodes import
make_intent_router_node` ở dòng 24, 32, 40, 48, 57, 66, 75) — đổi cả 7 thành
`from src.agents.routing import make_intent_router_node`.

Và **10 chỗ gọi** `_parse_router_output(` (dòng 82, 87, 88, 94, 99, 105, 106,
110, 111, 115) — đổi tên hàm thành `parse_proposal(`.

**Chỉ đổi TÊN HÀM được gọi; KHÔNG đổi giá trị kỳ vọng.** `parse_proposal` trả
`RouteProposal` là NamedTuple nên vế phải `== ("erp_write", "giao-hang")` vẫn
đúng nguyên văn — đó chính là điều Step 7 kiểm.

- [ ] **Step 7: Viết test MỚI cho ràng buộc NamedTuple**

Thêm vào cuối `backend/tests/agents/test_intent_router.py`:

```python
def test_route_proposal_unpacks_as_tuple():
    """RouteProposal PHẢI unpack được kiểu tuple: eval_sop_select
    (evals/run_eval.py:447) làm `intent, sop = parse_proposal(...)`. Đổi sang
    dataclass sẽ làm eval gãy — test này đỏ TRƯỚC khi điều đó xảy ra."""
    from src.agents.routing import RouteProposal
    proposal = parse_proposal("intent: mixed\nsop: giao-hang", SOPS)
    intent, sop = proposal                      # phải unpack được
    assert (intent, sop) == ("mixed", "giao-hang")
    assert isinstance(proposal, tuple)
    assert proposal.intent == "mixed"           # và vẫn truy cập theo tên được
    assert proposal.sop == "giao-hang"
    assert RouteProposal("rag", None) == ("rag", None)
```

- [ ] **Step 8: Chạy test của lớp 1**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_intent_router.py -q`
Expected: **20 passed** (19 cũ + 1 mới ở Step 7).

Nếu một test cũ đỏ: **KHÔNG sửa giá trị kỳ vọng cho khớp.** Xem lại Step 2/3 đã chép đúng
từng dòng chưa, rồi báo cáo nếu vẫn đỏ.

- [ ] **Step 9: Chạy suite unit-only, đối chiếu baseline Step 1**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: số `passed` = baseline Step 1 **+ 1** (test mới), số `failed` = 0.

- [ ] **Step 10: Kiểm không còn ai import đường cũ**

Run:
```bash
cd D:/Youdoo/backend && grep -rn "_parse_router_output\|from src.agents.nodes import make_intent_router_node\|from .nodes import make_intent_router_node" --include="*.py" src/ evals/ tests/
```
Expected: **không có dòng nào**. Nếu còn, sửa nốt rồi chạy lại Step 9.

- [ ] **Step 11: Commit**

```bash
cd D:/Youdoo && git add backend/src/agents/routing.py backend/src/agents/nodes.py backend/src/agents/graph.py backend/evals/run_eval.py backend/tests/agents/test_intent_router.py
git commit -m "refactor(routing): chuyển lớp đề xuất sang routing.py, parse_proposal trả RouteProposal"
```

---

### Task 2: Chuyển LỚP 2 (veto) + viết docstring hợp đồng đầy đủ

**Files:**
- Modify: `backend/src/agents/routing.py` (thêm lớp 2 + thay docstring đầu file)
- Modify: `backend/src/agents/graph.py:19-20` (bỏ import `skill_gate`/`_fold`), xoá `graph.py:25-65`, `:131`
- Modify: `backend/evals/run_eval.py:39`, `:448`
- Test: `backend/tests/agents/test_graph_build.py` (9 dòng import), `backend/tests/agents/test_fanout_graph.py:53-58`

**Interfaces:**
- Consumes: `RouteProposal`, `VALID_INTENTS` (Task 1) — không dùng trực tiếp,
  nhưng cùng file
- Produces:
  - `looks_like_question(folded: str) -> bool`
  - `decide_route(state: ERPAgentState) -> str` — trả **chuỗi trần** (tên
    intent hoặc tên SOP), đúng hợp đồng mà `SOP_SELECT_CASES` đang đo

- [ ] **Step 1: Thêm lớp 2 vào cuối `routing.py`**

Thêm vào cuối `backend/src/agents/routing.py` (chép nguyên logic từ
`graph.py:25-65`, chỉ đổi tên hàm):

```python
# ── LỚP 2: phủ quyết tất định ────────────────────────────────────────────────

_QUESTION_MARKERS = (
    "?", "la gi", "nghia la", "nhu the nao", "the nao", "tai sao",
    "giai thich", "huong dan", "kiem tra", "tinh trang", "trang thai",
    "duoc khong",
)


def looks_like_question(folded: str) -> bool:
    return any(m in folded for m in _QUESTION_MARKERS)


def decide_route(state: ERPAgentState) -> str:
    """Quyết định cuối là TẤT ĐỊNH. Đề cử SOP (state["sop"]) chỉ là một trong
    hai điều kiện; điều kiện kia — câu KHÔNG mang dấu hiệu câu hỏi — là lớp
    phủ quyết không phụ thuộc phân loại LLM.

    Vì sao lớp phủ quyết này CỐ Ý tất định và KHÔNG được tháo ra: bản đầu (chỉ
    AND với intent=="erp_write") đóng đúng ca hijack gốc ("quy trình nhập kho
    là gì?" → skill thay vì RAG) nhưng live-verify 2026-07-16 lộ ra chiều lỗi
    ngược — router phân loại "mixed"/"erp_read" cho chính 2 câu lệnh dùng
    nguyên văn ngôn ngữ quy trình ("quy trình nhập kho cho đơn mua P00021",
    "nhập kho theo quy trình cho đơn mua P00021"), khiến lệnh thật bị lỡ route
    3/3 LẦN THỬ — vì router chưa từng được tune để phân biệt "hỏi VỀ SOP" khỏi
    "thực thi SOP cho 1 đơn cụ thể" (đọc rất giống định nghĩa "mixed" trong
    prompts.py dù ý người dùng là hành động). Chuyển gate sang tất định (đánh
    dấu câu hỏi) giữ nguyên bất biến an toàn (câu hỏi không hijack) mà không
    phụ thuộc phân loại LLM cho quyết định này. Model to hơn CÓ THỂ đủ — nhưng
    "có thể" không phải cơ sở để tháo một lớp phòng thủ đã chứng minh giá trị,
    khi giữ nó tốn 10 dòng.

    Lưới đỡ cuối không phải lớp này: router sai chiều nào thì confirm-gate tại
    tool boundary vẫn chặn mọi write chưa được duyệt."""
    intent = state.get("intent") or "unknown"
    sop = state.get("sop")
    if sop and skill_gate.skills_enabled():
        last_human = next((m.content for m in reversed(state["messages"])
                           if m.type == "human"), "")
        folded = _fold(last_human)
        if intent == "erp_write" or not looks_like_question(folded):
            return sop            # SOP nhận trọn lượt
    return intent                 # phủ quyết: rớt sop, dùng intent
```

Và thêm 2 import vào đầu `routing.py`, ngay sau `from .prompts import ...`:

```python
from . import skill_gate
from .skill_gate import _fold
```

- [ ] **Step 2: Thay docstring đầu `routing.py` bằng hợp đồng đầy đủ**

Thay khối docstring tạm ở đầu file (viết ở Task 1 Step 2) bằng:

```python
"""Tầng định tuyến của trợ lý — hợp đồng HAI LỚP, lai xác suất + tất định.

Đây là chỗ DUY NHẤT trong repo mô tả trọn cơ chế này. Trước 2026-08-04 nó nằm
rải ở 4 file (prompts.py, nodes.py, graph.py, skill_gate.py) và không file nào
tự nhận mình là tầng định tuyến.

    message ──► [node "intent_router"] ──state──► [decide_route] ──► node đích
                 LỚP 1: LLM đề xuất               LỚP 2: tất định
                 RouteProposal(intent, sop)       veto thắng → trả 1 chuỗi

LỚP 1 — XÁC SUẤT (make_intent_router_node → parse_proposal):
    Một lượt gọi LLM duy nhất đề xuất CẢ `intent` lẫn `sop` (không tốn call
    thêm — đáng kể khi OpenRouter chỉ ~50 req/ngày). Đầu ra là ĐỀ CỬ, tên kiểu
    RouteProposal nói đúng điều đó. Parse fail-an-toàn mọi hướng; tên worker
    model bịa ra không bao giờ lọt ra ngoài.

LỚP 2 — TẤT ĐỊNH, VÀ NÓ THẮNG (decide_route):
    Điều kiện phủ quyết (`looks_like_question`) KHÔNG phụ thuộc phân loại của
    LLM. Đề cử SOP chỉ được nhận trọn lượt khi câu người dùng không mang dấu
    hiệu câu hỏi, HOẶC router tự tin nói erp_write.

VÌ SAO LỚP 2 PHẢI TẤT ĐỊNH — ba bằng chứng độc lập:
    1. Live-verify 2026-07-16: router LLM lỡ route lệnh thật 3/3 LẦN THỬ trên
       chính ngôn ngữ quy trình ("quy trình nhập kho cho đơn mua P00021").
    2. Thí nghiệm model 2026-07-31 (chạy thật trên cổng sop_select):
       gemini-3.1-flash-lite HOÀ đúng ca đang fail với gemma-4-26b; còn
       groq-gpt-oss-120b TỆ HƠN — đẻ thêm một ca hijack mới. Model to hơn
       không cứu được.
    3. Nguồn ngoài dự án (research 2026-08-04): đây là inverse/U-shaped
       scaling đã công bố — McKenzie et al., "Inverse Scaling: When Bigger
       Isn't Better", TMLR 2023. Mô hình lớn hơn bám prior lúc pretrain nhiều
       hơn, bám prompt ít hơn. Pattern chuẩn ngành cho đúng tình huống này là
       hybrid "lớp đề xuất + veto tất định" — chính là thiết kế ở đây.

ĐIỀU KIỆN ĐỂ ĐƯỢC THÁO VETO: hiện tại KHÔNG CÓ. Muốn tháo phải có số đo mới
bác bỏ được cả ba bằng chứng trên. Một supervisor LLM (nếu đời sau làm) chỉ
được đứng TRƯỚC lớp 2, không được thay nó — xem
docs/superpowers/specs/2026-08-04-routing-layer-extraction-design.md §0 để
biết vì sao giai đoạn "supervisor nuốt intent_router" đã bị huỷ.

LƯỚI ĐỠ CUỐI KHÔNG PHẢI TẦNG NÀY: router sai chiều nào thì confirm-gate tại
tool boundary vẫn chặn mọi write chưa được duyệt.

VÌ SAO HAI LỚP KHÔNG GỘP THÀNH MỘT HÀM: LangGraph persist state giữa node và
conditional-edge, nên lớp 1 buộc là node còn lớp 2 buộc là hàm trên cạnh. Đơn
vị làm rõ ở đây là FILE, không phải hàm — đó là thiết kế, không phải thiếu sót.

Ở NGUYÊN CHỖ KHÁC, CÓ CHỦ ĐÍCH: text prompt sống ở prompts.py (quy ước: mọi
prompt ở đó); `intent_targets` + `add_conditional_edges` sống ở graph.py (đó
là sơ đồ, không phải logic định tuyến).
"""
```

- [ ] **Step 3: Xoá lớp 2 khỏi `graph.py`**

Trong `backend/src/agents/graph.py`:

1. Xoá **nguyên khối dòng 25 tới 65** (`_QUESTION_MARKERS`,
   `_looks_like_question`, `_route_by_intent`).
2. Xoá 2 dòng import nay đã thừa (dòng 19-20) — đã kiểm: `skill_gate` và
   `_fold` **chỉ** được dùng bên trong `_route_by_intent`:
```python
from . import skill_gate
from .skill_gate import _fold
```
3. Sửa dòng import `.routing` (đã thêm ở Task 1 Step 4) thành:
```python
from .routing import make_intent_router_node, decide_route
```
4. Sửa chỗ đăng ký cạnh có điều kiện (dòng ~131):

Từ:
```python
    g.add_conditional_edges("intent_router", _route_by_intent, intent_targets)
```
Thành:
```python
    g.add_conditional_edges("intent_router", decide_route, intent_targets)
```

**GIỮ NGUYÊN** `from .state import ERPAgentState` — còn dùng ở
`_route_after_write_planner` và `StateGraph(ERPAgentState)`.
**GIỮ NGUYÊN** chuỗi `"intent_router"` làm tên node.

- [ ] **Step 4: Đổi nguồn import ở `evals/run_eval.py`**

Dòng 39, xoá:
```python
from src.agents.graph import _route_by_intent
```
Và gộp vào dòng import `.routing` đã có từ Task 1 Step 5:
```python
from src.agents.routing import parse_proposal, decide_route
```

Dòng 448, từ:
```python
        got = _route_by_intent({"messages": [HumanMessage(content=text)],
                                "intent": intent, "sop": sop})
```
Thành:
```python
        got = decide_route({"messages": [HumanMessage(content=text)],
                            "intent": intent, "sop": sop})
```

- [ ] **Step 5: Đổi import ở `test_graph_build.py` — CHỈ dòng import**

9 chỗ import trong thân test, đổi nguồn `src.agents.graph` → `src.agents.routing`
và đổi tên symbol:

| Dòng | Từ | Thành |
|---|---|---|
| 217 | `from src.agents.graph import _looks_like_question` | `from src.agents.routing import looks_like_question` |
| 235 | `from src.agents.graph import _looks_like_question` | `from src.agents.routing import looks_like_question` |
| 261, 271, 278, 287, 294, 301 | `from src.agents.graph import _route_by_intent` | `from src.agents.routing import decide_route` |

Và đổi tên ở chỗ **gọi**: `_looks_like_question(` → `looks_like_question(`
(dòng 231, 245); `_route_by_intent(` → `decide_route(` (dòng 264, 266, 273,
280, 282, 288, 289, 290, 296, 304).

**Chỉ đổi tên symbol; KHÔNG đổi giá trị kỳ vọng của assert.**

- [ ] **Step 6: Sửa `test_fanout_graph.py` — import + tên test + docstring**

Dòng 53-58, từ:
```python
def test_route_by_intent_still_returns_plain_mixed_string():
    """Hợp đồng đầu ra mà SOP_SELECT_CASES đo — không được đổi ở SP-2b."""
    from src.agents.graph import _route_by_intent
    state = {"intent": "mixed", "sop": None,
             "messages": [HumanMessage(content="theo chính sách, đơn X hoàn được không?")]}
    assert _route_by_intent(state) == "mixed"
```
Thành:
```python
def test_decide_route_still_returns_plain_mixed_string():
    """Hợp đồng đầu ra mà SOP_SELECT_CASES đo — không được đổi ở SP-2b, và
    không đổi khi hàm chuyển nhà sang routing.py (2026-08-04)."""
    from src.agents.routing import decide_route
    state = {"intent": "mixed", "sop": None,
             "messages": [HumanMessage(content="theo chính sách, đơn X hoàn được không?")]}
    assert decide_route(state) == "mixed"
```

- [ ] **Step 7: Chạy test của lớp 2 + bất biến cấu trúc**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_graph_build.py tests/agents/test_fanout_graph.py -q`
Expected: toàn bộ PASS, gồm `test_skill_nodes_reachable_only_from_intent_router`
(bất biến bảo mật — nó assert tên node `"intent_router"`, tức cũng là canh gác
cho ràng buộc "không đổi tên node").

- [ ] **Step 8: Chạy suite unit-only**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: `passed` = baseline Task 1 Step 1 **+ 1**, `failed` = 0.

- [ ] **Step 9: Kiểm không còn ai import đường cũ**

Run:
```bash
cd D:/Youdoo/backend && grep -rn "_route_by_intent\|_looks_like_question" --include="*.py" src/ evals/ tests/
```
Expected: chỉ còn các dòng **comment/docstring** (Task 3 xử lý), **không còn
dòng `import` hay dòng gọi hàm nào**. Nếu còn import/gọi → sửa rồi chạy lại
Step 8.

- [ ] **Step 10: Commit**

```bash
cd D:/Youdoo && git add backend/src/agents/routing.py backend/src/agents/graph.py backend/evals/run_eval.py backend/tests/agents/test_graph_build.py backend/tests/agents/test_fanout_graph.py
git commit -m "refactor(routing): chuyển lớp veto sang routing.py, docstring hợp đồng 2 lớp"
```

---

### Task 3: Vệ sinh cross-reference + kiểm chứng + report

**Files:**
- Modify: `backend/src/agents/prompts.py:23`, `skill_manifest.py:14`, `state.py:14`, `fanout.py:61,63,65`
- Modify: `backend/evals/cases.py:568`
- Modify: `backend/tests/agents/test_build_graph_skill_integration.py:145-146`, `test_graph_build.py:206,211-212,249`
- Create: `docs/superpowers/plans/2026-08-04-routing-layer-extraction-report.md`

**Interfaces:** Không có API mới. Chỉ sửa comment và viết report.

- [ ] **Step 1: Grep lại danh sách cross-reference (main có thể đã đổi)**

Run:
```bash
cd D:/Youdoo/backend && grep -rn "graph\._route_by_intent\|nodes\._parse_router_output\|_route_by_intent\|_looks_like_question\|_parse_router_output" --include="*.py" src/ evals/ tests/
```

Ghi lại danh sách thật. Bảng dưới là danh sách đã grep tại HEAD `4c2fd49`;
nếu nhánh song song thêm chỗ mới thì sửa cả chỗ đó.

- [ ] **Step 2: Sửa 4 comment trong `src/agents/`**

`prompts.py:23` — từ `graph._route_by_intent` thành `routing.decide_route`:
```python
# định cuối vẫn tất định ở routing.decide_route. Đổi hợp đồng này là đổi
```

`skill_manifest.py:14` — từ `(graph._route_by_intent)` thành `(routing.decide_route)`:
```python
và lớp phủ quyết tất định (routing.decide_route) cùng confirm-gate vẫn chặn
```

`state.py:14` — từ `graph._route_by_intent` thành `routing.decide_route`:
```python
                                  # định cuối vẫn do routing.decide_route
```

`fanout.py:61,63,65` — 3 chỗ trong cùng một docstring:
```python
    chủ đích: nhờ vậy `decide_route` KHÔNG ĐỔI MỘT KÝ TỰ, mà hàm đó chính
```
```python
    decide_route() TRẢ VỀ" — cases.py). Cho hàm đó trả về list
```
```python
    ra mà bộ eval đang đo, và kéo theo cả lớp phủ quyết looks_like_question
```

- [ ] **Step 3: Sửa comment trong `evals/cases.py:568`**

Từ:
```python
# Đích là giá trị _route_by_intent() TRẢ VỀ: tên skill SOP ("giao-hang",
```
Thành:
```python
# Đích là giá trị decide_route() TRẢ VỀ: tên skill SOP ("giao-hang",
```

- [ ] **Step 4: Sửa comment trong 2 file test**

`test_build_graph_skill_integration.py:145-146`, từ:
```python
    # Router thật đã đề cử ĐÚNG SOP và lớp phủ quyết tất định (graph.
    # _route_by_intent) đã cho SOP nhận trọn lượt (không bị veto).
```
Thành:
```python
    # Router thật đã đề cử ĐÚNG SOP và lớp phủ quyết tất định
    # (routing.decide_route) đã cho SOP nhận trọn lượt (không bị veto).
```

`test_graph_build.py:206` và `:211-212`, từ:
```python
# _looks_like_question). These tests reproduce the exact 3 failing repro
```
```python
# NOT ported in this plan (deferred to SP-2 — spec §3). _route_by_intent now
# just returns state["intent"], so only the two _looks_like_question unit
```
Thành:
```python
# looks_like_question). These tests reproduce the exact 3 failing repro
```
```python
# NOT ported in this plan (deferred to SP-2 — spec §3). decide_route now
# just returns state["intent"], so only the two looks_like_question unit
```

`test_graph_build.py:249`, từ:
```python
# Tầng 1 (description → đề cử `sop`) là XÁC SUẤT. Tầng 2 (_looks_like_question
```
Thành:
```python
# Tầng 1 (description → đề cử `sop`) là XÁC SUẤT. Tầng 2 (looks_like_question
```

- [ ] **Step 5: Chứng minh không còn tên cũ ở đâu trong mã**

Run:
```bash
cd D:/Youdoo/backend && grep -rn "_route_by_intent\|_looks_like_question\|_parse_router_output" --include="*.py" src/ evals/ tests/
```
Expected: **không có kết quả nào.**

Run (chứng minh spec cũ KHÔNG bị đụng — chúng phải vẫn giữ tên cũ):
```bash
cd D:/Youdoo && git status --short docs/superpowers/specs/
```
Expected: **rỗng** — không file spec nào bị sửa.

- [ ] **Step 6: Chạy lại suite unit-only lần cuối**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: `passed` = baseline Task 1 Step 1 **+ 1**, `failed` = 0.

Chạy thêm tầng tích hợp (cần Postgres `youdoo` cổng 5434 đang chạy):

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m integration`
Expected: không tăng số fail so với trước. Nếu Postgres không chạy, ghi rõ
"bỏ qua, Postgres không sẵn sàng" vào report thay vì đoán kết quả.

- [ ] **Step 7: Đo xác nhận `--set sop_select`**

Cần Postgres `youdoo` + Odoo (`localhost:8069`) đang chạy. Chạy (bash):

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set sop_select
```

Expected: `hijack = 0`, `acc ≥ 16/17` (bar chuẩn SP-2b §8.4; gate tuyệt đối
của set này biết trước là **không xanh** — ca hồi quy 2026-07-16 — nên
`FAIL` ở dòng gate là bình thường, đọc `acc`/`hijack` chứ không đọc verdict).

**Giới hạn phải ghi vào report:** prompt byte-identical và logic parse/veto
byte-identical, nên lệch nếu có là do **sampling của model**, KHÔNG kết luận
được gì về refactor. Bằng chứng thật là Step 6. Nếu `hijack > 0` hoặc
`acc < 16/17`: **không tự suy diễn nguyên nhân** — chạy lại đúng 1 lần nữa để
phân biệt sampling với hồi quy thật, rồi báo cáo cả hai lượt kèm đường dẫn
`logs/jobs/eval-gate-*.json`.

- [ ] **Step 8: Viết report**

Tạo `docs/superpowers/plans/2026-08-04-routing-layer-extraction-report.md` gồm:

1. SHA baseline (Task 1 Step 1) và SHA cuối.
2. Số suite unit-only trước/sau, kèm khẳng định **không assert nào bị sửa nội dung**.
3. Kết quả `-m integration` (hoặc lý do bỏ qua).
4. Số `acc`/`hijack` của `--set sop_select` + đường dẫn file log JSON + đoạn
   ghi giới hạn ở Step 7 (chép nguyên ý: đây là xác nhận, không phải bằng chứng).
5. Kết quả 2 lệnh grep ở Step 5 (đều rỗng).
6. Đối chiếu §7 "Xong nghĩa là" của spec — 7 mục, đánh dấu từng mục.

- [ ] **Step 9: Commit**

```bash
cd D:/Youdoo && git add backend/src/agents/prompts.py backend/src/agents/skill_manifest.py backend/src/agents/state.py backend/src/agents/fanout.py backend/evals/cases.py backend/tests/agents/test_build_graph_skill_integration.py backend/tests/agents/test_graph_build.py docs/superpowers/plans/2026-08-04-routing-layer-extraction-report.md
git commit -m "docs(routing): sửa 8 file comment trỏ tên cũ + report đo thật"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §2.1 `routing.py` giữ 6 symbol, đúng cái ở nguyên chỗ cũ | T1 Step 2-4, T2 Step 1, 3 |
| §2.2 docstring đầu file, 5 nội dung bắt buộc | T2 Step 2 |
| §2.3 không đổi tên node `"intent_router"` | Global Constraints; T1 Step 2 (comment tại chỗ), T2 Step 3.4; canh bởi test ở T2 Step 7 |
| §2.4 `RouteProposal` là NamedTuple vì eval unpack tuple | T1 Step 2, test ở T1 Step 7 |
| §2.5 luồng không đổi; file là đơn vị làm rõ | T2 Step 2 (ghi trong docstring) |
| §3.1 5 import site, không shim | T1 Step 3-6, T2 Step 3-6; chứng minh ở T1 Step 10, T2 Step 9 |
| §3.2 8 file comment lỗi thời | T3 Step 2-4; chứng minh ở T3 Step 5 |
| §3.3 không sửa spec cũ | T3 Step 5 (git status rỗng) |
| §4 error handling không đổi | T1 Step 2 chép nguyên `parse_proposal` |
| §5.1 bằng chứng chính: giá trị kỳ vọng không đổi (chỉ đổi tên symbol) | Global Constraints; T1 Step 8-9, T2 Step 7-8, T3 Step 6 |
| §5.2 bất biến cấu trúc vẫn xanh | T2 Step 7 |
| §5.3 test mới cho `RouteProposal` | T1 Step 7 |
| §5.4 `sop_select` là xác nhận, kèm ghi giới hạn | T3 Step 7-8 |
| §7 "xong nghĩa là" 7 mục | T3 Step 8 mục 6 |
| Phụ lục A: comment tại chỗ cho 5 quyết định | T1 Step 2 (tên node, NamedTuple), T2 Step 2 (hợp đồng 2 lớp, file-là-đơn-vị, con trỏ tới spec §0) |

**Placeholder scan:** không có "TBD"/"TODO"/"tương tự Task N". Mọi bước sửa
mã đều có code block đầy đủ hoặc bảng dòng-đổi-dòng cụ thể. Bước duy nhất
không có code cứng là T3 Step 1 (grep lại) — cố ý, vì `main` đang nhận merge
từ nhánh song song và danh sách có thể dài thêm; bảng ở §3.2 spec vẫn là mốc
đối chiếu.

**Type consistency:** `parse_proposal(text, valid_sops) -> RouteProposal` dùng
nhất quán ở T1 Step 2 (định nghĩa), Step 5 (`run_eval.py`), Step 6-7 (test).
`decide_route(state) -> str` dùng nhất quán ở T2 Step 1 (định nghĩa), Step 3
(`graph.py`), Step 4 (`run_eval.py`), Step 5-6 (test).
`looks_like_question(folded) -> bool` dùng nhất quán ở T2 Step 1 và Step 5.
`RouteProposal.intent` / `.sop` khớp giữa định nghĩa (T1 Step 2) và test
(T1 Step 7). Tên node graph là chuỗi `"intent_router"` ở mọi chỗ, không đổi.
