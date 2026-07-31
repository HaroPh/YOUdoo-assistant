# SP-2b: Fan-out đường đọc — khai tử node `fusion` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay node `mixed` (một ReAct agent bịa riêng, `fusion.py`) bằng fan-out
hai chân thu thập + một node tổng hợp, dựng nên nguyên thuỷ join mà SP-2c dùng
lại — mà không đụng một ký tự nào vào lớp định tuyến SP-2a.

**Architecture:** `intent_router --"mixed"--> mixed` (điểm fan-out, xoá key
join, nhả 2 cạnh) `--> gather_docs ‖ gather_erp --> fuse_answer --> END`. Hai
chân chạy cùng superstep LangGraph, ghi hai key state khác nhau, không chân nào
ghi `messages`. `fuse_answer` gọi một lượt LLM rồi dùng lại nguyên
`cite_and_verify` + `verify_erp_grounding`.

**Tech Stack:** Python 3.12, LangGraph 1.1.10, LangChain 1.2.18, pytest 9.1.1
(`asyncio_mode = auto`), Postgres (checkpointer + pgvector).

**Spec:** `docs/superpowers/specs/2026-08-01-sp2b-read-fanout-design.md`

## Global Constraints

- **`_route_by_intent` và `intent_targets` trong `graph.py` KHÔNG ĐƯỢC ĐỔI một
  ký tự.** Bộ eval `SOP_SELECT_CASES` đo trực tiếp giá trị `_route_by_intent()`
  trả về. Node `mixed` giữ nguyên tên và giữ nguyên chỗ trong `intent_targets`.
- **State chỉ chứa JSON thuần.** `Chunk` là `@dataclass(frozen=True)` — phải
  `asdict()` khi ghi và dựng lại `Chunk(**d)` khi đọc. Không bao giờ đặt
  dataclass/pydantic object vào `ERPAgentState`.
- **Không chân `gather_*` nào được để exception thoát ra.** LangGraph để lỗi
  một nhánh giết CẢ superstep. Mỗi chân tự `try/except`, ghi giá trị rỗng
  (`[]` / `""`).
- **Không chân `gather_*` nào được ghi key `messages`.** Chỉ `fuse_answer` ghi.
- **Vai model `fusion` trong `catalog.py` GIỮ NGUYÊN.** Node chết, vai sống.
  `CHAINS["fusion"] = ("gemini-3.1-flash-lite", "groq-llama-3.3-70b")` không đổi;
  `ROLE_FOR_SET["multi_source"] = "fusion"` trong `eval_gate.py` không đổi.
- **`gather_erp` và `fuse_answer` đều dùng `llms["fusion"]`** — đúng model node
  `mixed` đang dùng. QĐ M3 (ADR-009) cấm đổi model/prompt khi chưa qua eval
  gate; đổi topology *và* vai model cùng lượt thì không quy được trách nhiệm.
- **Cả hai prompt mới kết thúc bằng `/no_think`** (lệ đang áp trong `prompts.py`).
- **`FUSE_PROMPT` phải giữ nguyên văn hai mệnh đề** mà `test_prompts.py` chốt:
  `"KHÔNG nêu số thứ tự Điều/Mục/Khoản"` và `"HAY số thứ tự đoạn tài liệu"`.
- **`FUSE_PROMPT` phải giữ hợp đồng đuôi `NGUỒN_DÙNG: <số>`** — đó là thứ
  `extract_used_citations()` parse, không phải trang trí.
- **Không bê deny-list `WRITE_TOOL_NAMES`** từ `fusion.py` sang. Lớp thật là
  allow-list `build_erp_query_tools()` + test chốt.
- Chạy Python bằng `backend/.venv/Scripts/python.exe` (alias `python` trên máy
  này trỏ vào Microsoft Store shim, hỏng). Đặt `PYTHONIOENCODING=utf-8` trước
  mọi lệnh in tiếng Việt ra file/pipe.
- Sau khi chạy bất kỳ test nào chạm `tests/rag/`, `git checkout --` lại
  `backend/tests/rag/fixtures/bang_gia.xlsx` và `policy.docx` (suite
  re-serialize chúng không tất định).

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Tạo | `backend/src/agents/fanout.py` | 4 node factory + `render_fuse_input()` + 2 helper Chunk↔dict |
| Xoá | `backend/src/agents/fusion.py` | — |
| Sửa | `backend/src/agents/state.py` | thêm `doc_context`, `erp_facts` + comment vòng đời |
| Sửa | `backend/src/agents/prompts.py` | thêm `GATHER_ERP_PROMPT`, `FUSE_PROMPT`; xoá `FUSION_PROMPT` |
| Sửa | `backend/src/agents/graph.py` | đấu lại `mixed` thành 4 node |
| Sửa | `backend/evals/run_eval.py` | `eval_multi_source` dùng `FUSE_PROMPT` + `render_fuse_input()` |
| Sửa | `backend/src/llm/catalog.py` | comment "vai sống, node chết" |
| Sửa | `backend/src/main.py` | comment cũ nhắc `fusion_node` |
| Tạo | `backend/tests/agents/test_fanout.py` | test đơn vị 4 node |
| Tạo | `backend/tests/agents/test_fanout_graph.py` | test tích hợp trên `build_graph()` THẬT |
| Xoá | `backend/tests/agents/test_fusion.py` | — |
| Sửa | `backend/tests/agents/test_graph_build.py` | bỏ test spy `make_fusion_node` |
| Sửa | `backend/tests/agents/test_prompts.py` | đổi `FUSION_PROMPT` → `FUSE_PROMPT` |
| Tạo | `docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md` | số đo TRƯỚC/SAU + live verify |

Module tên `fanout.py` chứ không phải `mixed.py`: tên phải nói lên **nguyên
thuỷ**, vì SP-2c dùng lại nguyên thuỷ chứ không dùng lại intent `mixed`.

---

## Task 1: Đo TRƯỚC trên `main` sạch

**Không sửa một dòng mã nào.** Đây là số tham chiếu cho phép so hồi quy ở
Task 9. Chạy TRƯỚC mọi thay đổi, nếu không thì mất vĩnh viễn.

**Files:**
- Create: `docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md`

**Interfaces:**
- Consumes: không có.
- Produces: file report có mục `## Số đo TRƯỚC` chứa 3 khối JSON kết quả và
  đường dẫn tới file log gốc trong `logs/jobs/`. Task 9 đọc file này.

- [ ] **Step 1: Xác nhận cây làm việc sạch và ở đúng base**

```bash
git status --short          # kỳ vọng: rỗng
git log --oneline -1        # kỳ vọng: commit spec SP-2b
```

- [ ] **Step 2: Chạy gate `multi_source`**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Ghi lại: `both_source_coverage`, `citation_validity`, `fabricated_number`,
`lat_p50`, `lat_p95`, verdict, và đường dẫn file JSON mà job in ra
(`logs/jobs/eval-gate-<timestamp>.json`).

Job gọi LLM thật. Nếu trả `INFRA_ERROR` (lỗi mạng/quota chứ không phải lỗi
chất lượng), chạy lại — đừng ghi INFRA_ERROR làm số tham chiếu.

- [ ] **Step 3: Chạy gate `intent`**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set intent
```

Ghi lại `acc`, verdict, đường dẫn JSON.

- [ ] **Step 4: Chạy gate `sop_select`**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set sop_select
```

Ghi lại `acc`, `hijack`, verdict, đường dẫn JSON. **Kỳ vọng FAIL** — đây là gate
tuyệt đối (`acc == 1.0 and hijack == 0`) đang FAIL biết trước 16/17 từ SP-2a,
đã được chủ dự án chấp nhận. Ghi đúng con số, đừng coi FAIL là sự cố.

- [ ] **Step 5: Viết file report**

```markdown
# SP-2b — báo cáo số đo và xác minh sống

Plan: `docs/superpowers/plans/2026-08-01-sp2b-read-fanout.md`
Spec: `docs/superpowers/specs/2026-08-01-sp2b-read-fanout-design.md`

## Số đo TRƯỚC

Chạy trên `main` sạch tại commit `<sha>`, trước khi sửa dòng đầu tiên.
Model: đầu chuỗi catalog của vai tương ứng (không truyền `--model`).

### multi_source (vai `fusion`)
- verdict: `<PASS|FAIL>`
- `both_source_coverage`: `<số>`
- `citation_validity`: `<số>`
- `fabricated_number`: `<số>`
- `lat_p50` / `lat_p95`: `<số>` / `<số>` ms
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`

### intent (vai `router`)
- verdict: `<PASS|FAIL>`
- `acc`: `<số>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`

### sop_select (vai `router`)
- verdict: `FAIL` (biết trước — gate tuyệt đối, 16/17 tồn dư từ SP-2a)
- `acc`: `<số>`
- `hijack`: `<số>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`
```

Thay mọi `<...>` bằng giá trị thật. Không để lại dấu ngoặc nhọn nào.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md
git commit -m "docs(sp2b): số đo TRƯỚC trên main sạch (multi_source/intent/sop_select)"
```

---

## Task 2: Key state + hai prompt mới

**Files:**
- Modify: `backend/src/agents/state.py`
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_fanout.py` (tạo mới ở task này)

**Interfaces:**
- Consumes: không có.
- Produces:
  - `ERPAgentState` có thêm 2 key: `doc_context: list[dict] | None`,
    `erp_facts: str | None`.
  - `prompts.GATHER_ERP_PROMPT: str`, `prompts.FUSE_PROMPT: str`.
  - `FUSION_PROMPT` **vẫn còn** sau task này (Task 8 mới xoá) — `fusion.py` và
    `run_eval.py` còn đang import nó.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_fanout.py`:

```python
# backend/tests/agents/test_fanout.py
"""Test fan-out đường đọc (SP-2b) — 4 node thay node `fusion` cũ."""


def test_state_has_fanout_keys():
    from src.agents.state import ERPAgentState
    ann = ERPAgentState.__annotations__
    assert "doc_context" in ann
    assert "erp_facts" in ann


def test_gather_erp_prompt_forbids_concluding():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG kết luận" in GATHER_ERP_PROMPT
    assert GATHER_ERP_PROMPT.rstrip().endswith("/no_think")


def test_gather_erp_prompt_forbids_citing_documents():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG viện dẫn" in GATHER_ERP_PROMPT


def test_fuse_prompt_keeps_citation_trailer_contract():
    from src.agents.prompts import FUSE_PROMPT
    from src.agents.synthesis import USED_MARKER
    # extract_used_citations() parse đúng dòng này — không phải trang trí.
    assert USED_MARKER in FUSE_PROMPT
    assert FUSE_PROMPT.rstrip().endswith("/no_think")


def test_fuse_prompt_forbids_inline_section_numbers():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in FUSE_PROMPT
    assert "HAY số thứ tự đoạn tài liệu" in FUSE_PROMPT


def test_fuse_prompt_mentions_no_write():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG thực hiện thao tác ghi" in FUSE_PROMPT
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'GATHER_ERP_PROMPT'` và
`assert "doc_context" in ann` sai.

- [ ] **Step 3: Thêm 2 key vào `state.py`**

Thêm vào cuối `class ERPAgentState` (sau `auto_chain`):

```python
    doc_context: list[dict] | None  # chân TÀI LIỆU của fan-out `mixed`:
                                  # [dataclasses.asdict(chunk), ...]. JSON
                                  # THUẦN — Chunk là @dataclass(frozen=True),
                                  # nhét thẳng vào state là loại lỗi CHỈ hỏng
                                  # khi checkpointer Postgres thật chạy (bài
                                  # học SP-1C2). TRANSIENT, dọn ở HAI chỗ với
                                  # HAI lý do: node `mixed` xoá lúc VÀO là lớp
                                  # chịu lực chống dữ liệu ôi qua lượt (channel
                                  # semantics của LangGraph giữ giá trị khi node
                                  # bỏ qua key); `fuse_answer` xoá lúc RA là vệ
                                  # sinh (lượt erp_read sau không vác theo cả
                                  # đống chunk trong checkpoint và trace).
    erp_facts: str | None         # chân ERP của fan-out `mixed`: dữ kiện thô
                                  # dạng văn bản (KHÔNG phải câu trả lời), hoặc
                                  # "". Cùng vòng đời với doc_context.
```

- [ ] **Step 4: Thêm 2 prompt vào `prompts.py`**

Thêm ngay sau `FUSION_PROMPT` (chưa xoá `FUSION_PROMPT` ở task này):

```python
GATHER_ERP_PROMPT = """Bạn là bộ phận THU THẬP DỮ KIỆN ERP. Nhiệm vụ duy nhất: dùng các tool đọc Odoo để lấy ra những dữ kiện liên quan đến câu hỏi của người dùng.

Quy tắc:
- Chỉ NÊU DỮ KIỆN, dạng gạch đầu dòng ngắn (mã đơn, ngày, số lượng, trạng thái, tên khách, tên sản phẩm...).
- TUYỆT ĐỐI KHÔNG kết luận, không phán quyết câu hỏi của người dùng. Một bộ phận khác sẽ làm việc đó.
- KHÔNG viện dẫn chính sách/quy định/tài liệu nội bộ — bạn không có tài liệu trong tay, và một bộ phận khác đang lo phần đó.
- CHỈ dùng dữ kiện do tool trả về. Tuyệt đối không bịa số liệu.
- Nếu không lấy được dữ kiện nào liên quan, trả lời đúng một câu: Không tìm được dữ kiện ERP liên quan.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""

FUSE_PROMPT = """Bạn là trợ lý ERP nội bộ, trả lời bằng tiếng Việt. Bạn nhận sẵn HAI nguồn đã được thu thập: các đoạn TÀI LIỆU nội bộ và DỮ LIỆU ERP. Nhiệm vụ của bạn là suy luận kết hợp hai nguồn để trả lời CÂU HỎI.

Quy tắc:
- CHỈ dùng dữ kiện có trong hai nguồn được cung cấp. Tuyệt đối không bịa điều khoản hay số liệu.
- Nếu phần TÀI LIỆU trống hoặc không liên quan, hoặc phần DỮ LIỆU ERP thiếu thứ cần thiết, hãy nói rõ là không đủ căn cứ — không suy đoán.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận.
- KHÔNG tự viết mục "Nguồn"/trích dẫn — phần trích dẫn sẽ được thêm tự động.
- KHÔNG nêu số thứ tự Điều/Mục/Khoản HAY số thứ tự đoạn tài liệu (ví dụ "Điều 3", "Mục 2", "[2]", "đoạn 2") trong câu trả lời — hãy diễn giải trực tiếp nội dung bằng lời tự nhiên, không chỉ đến nguồn theo số.
- Trả lời tự nhiên, thân thiện, ngắn gọn bằng tiếng Việt.

Sau khi trả lời xong, LUÔN thêm một dòng CUỐI CÙNG theo đúng định dạng: NGUỒN_DÙNG: <số thứ tự các đoạn TÀI LIỆU bạn đã dùng để trả lời, cách nhau bởi dấu phẩy>. Ví dụ: NGUỒN_DÙNG: 2,5. Nếu không dùng đoạn tài liệu nào (câu hỏi chỉ cần dữ liệu ERP), bỏ qua dòng này. /no_think"""
```

- [ ] **Step 5: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: 6 passed.

- [ ] **Step 6: Chạy toàn bộ test đơn vị để xác nhận không vỡ gì**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Kỳ vọng: xanh như trước (thêm 6 test mới).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/state.py backend/src/agents/prompts.py backend/tests/agents/test_fanout.py
git commit -m "feat(sp2b): key state doc_context/erp_facts + GATHER_ERP_PROMPT/FUSE_PROMPT"
```

---

## Task 3: `gather_docs` + helper Chunk↔dict

**Files:**
- Create: `backend/src/agents/fanout.py`
- Test: `backend/tests/agents/test_fanout.py` (thêm vào)

**Interfaces:**
- Consumes: `prompts.GATHER_ERP_PROMPT`, `prompts.FUSE_PROMPT` (Task 2);
  `synthesis.passes_floor(result) -> bool` (nhận `RetrievalResult`, KHÔNG phải
  list chunk); `rag.retrieve.retrieve(query, k=..., conn=None, aux_queries=())`
  (đồng bộ, psycopg); `rag.types.Chunk` (`@dataclass(frozen=True)`, 14 field,
  `rerank_score` có default).
- Produces:
  - `fanout.chunk_to_dict(c: Chunk) -> dict`
  - `fanout.chunks_from_dicts(ds: list[dict] | None) -> list[Chunk]`
  - `fanout._last_human(state) -> str`
  - `fanout.make_gather_docs_node() -> async node(state) -> {"doc_context": list[dict]}`

- [ ] **Step 1: Viết test thất bại**

Thêm vào đầu `backend/tests/agents/test_fanout.py` (sau docstring):

```python
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.rag.types import Chunk, RetrievalResult


def _chunk(**kw) -> Chunk:
    d = dict(chunk_id=1, doc_id="d", source_file="C:/docs/policy.docx",
             doc_title="P", section_path="Chính sách hoàn hàng › Điều 4",
             page=1, sheet=None, row_range=None,
             text="Hoàn hàng trong 30 ngày.", dense_score=0.7,
             sparse_score=None, rrf_score=0.02, rank=0)
    d.update(kw)
    return Chunk(**d)


def _result(chunks) -> RetrievalResult:
    return RetrievalResult(query="q", query_used="q", chunks=chunks,
                           top_score=(chunks[0].rrf_score if chunks else 0.0),
                           total_candidates=len(chunks), method="hybrid-rrf")


def _state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "intent": "mixed",
            "doc_context": None, "erp_facts": None}
```

Thêm vào cuối file:

```python
def test_chunk_dict_roundtrip_is_lossless():
    from src.agents.fanout import chunk_to_dict, chunks_from_dicts
    c = _chunk(rerank_score=0.9)
    back = chunks_from_dicts([chunk_to_dict(c)])
    assert back == [c]


def test_chunk_to_dict_is_plain_json_types():
    from src.agents.fanout import chunk_to_dict
    d = chunk_to_dict(_chunk())
    assert isinstance(d, dict)
    assert all(v is None or isinstance(v, (str, int, float)) for v in d.values())


def test_chunks_from_dicts_handles_none():
    from src.agents.fanout import chunks_from_dicts
    assert chunks_from_dicts(None) == []


async def test_gather_docs_writes_chunks_as_dicts(monkeypatch):
    import src.agents.fanout as fanout
    c = _chunk(dense_score=0.7)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([c]))
    out = await fanout.make_gather_docs_node()(_state("chính sách hoàn hàng?"))
    assert out == {"doc_context": [asdict(c)]}


async def test_gather_docs_retrieves_with_full_question(monkeypatch):
    """Khác `fusion` cũ (agent tự chọn query, hay truyền từ khoá trần) —
    fan-out LUÔN truy xuất bằng nguyên câu hỏi, nên aux_queries thành thừa."""
    import src.agents.fanout as fanout
    calls = []

    def fake_retrieve(q, *a, **kw):
        calls.append((q, kw.get("aux_queries")))
        return _result([])

    monkeypatch.setattr(fanout, "retrieve", fake_retrieve)
    await fanout.make_gather_docs_node()(_state("Đơn S00042 hoàn được không?"))
    assert calls == [("Đơn S00042 hoàn được không?", None)]


async def test_gather_docs_below_floor_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    c = _chunk(dense_score=0.2, sparse_score=None)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([c]))
    out = await fanout.make_gather_docs_node()(_state("câu ngoài corpus"))
    assert out == {"doc_context": []}


async def test_gather_docs_empty_result_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([]))
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert out == {"doc_context": []}


async def test_gather_docs_swallows_exception(monkeypatch):
    """Exception THOÁT RA sẽ giết CẢ superstep — tức chân ERP chạy song song
    cũng mất theo. Chân phải tự nuốt lỗi và ghi giá trị rỗng."""
    import src.agents.fanout as fanout

    def boom(q, *a, **kw):
        raise RuntimeError("pgvector down")

    monkeypatch.setattr(fanout, "retrieve", boom)
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert out == {"doc_context": []}


async def test_gather_docs_never_writes_messages(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([_chunk()]))
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert "messages" not in out


async def test_gather_docs_no_human_message_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    called = []
    monkeypatch.setattr(fanout, "retrieve",
                        lambda q, *a, **kw: called.append(q) or _result([]))
    out = await fanout.make_gather_docs_node()(
        {"messages": [AIMessage(content="xin chào")]})
    assert out == {"doc_context": []}
    assert called == []
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'src.agents.fanout'`.

- [ ] **Step 3: Tạo `fanout.py` với helper + `gather_docs`**

```python
# backend/src/agents/fanout.py
"""Fan-out đường đọc cho intent `mixed` (SP-2b) — thay node `fusion`.

    intent_router --"mixed"--> mixed ──┬──> gather_docs ──┐
                              (fan-out) │                  ├──> fuse_answer ──> END
                                        └──> gather_erp  ──┘

Hai chân chạy CÙNG một superstep LangGraph và ghi HAI key state khác nhau;
không chân nào ghi `messages`. Nhờ vậy không có xung đột reducer và người dùng
không thể nhận hai câu trả lời cho một lượt.

Vì sao fan-out của việc THU THẬP chứ không phải của việc TRẢ LỜI: cả 8 ca
MULTI_SOURCE_CASES đều cần một giá trị trong tài liệu (30 ngày, 3 ngày, 0,5%,
bảng chiết khấu) để DIỄN GIẢI một bản ghi ERP — suy luận là tuần tự, chỉ thu
thập mới song song được. Hai nhánh cùng tự trả lời rồi ghép hai câu trả lời sẽ
hỏng: mỗi nhánh chỉ thấy nửa dữ kiện nên đều nói "không đủ thông tin".
"""
import asyncio
import logging
from dataclasses import asdict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.agents import create_agent as _create_agent

from .state import ERPAgentState
from .prompts import FUSE_PROMPT, GATHER_ERP_PROMPT
from .synthesis import SAFE_MSG, _format_context, cite_and_verify, passes_floor
from .erp_grounding import verify_erp_grounding
from ..rag.retrieve import retrieve
from ..rag.types import Chunk

logger = logging.getLogger(__name__)


def _last_human(state) -> str:
    return next((m.content for m in reversed(state["messages"])
                 if m.type == "human"), "")


def chunk_to_dict(c: Chunk) -> dict:
    """Chunk → JSON thuần để đặt vào state.

    BẤT BIẾN: state chỉ chứa JSON thuần. Chunk là @dataclass(frozen=True);
    nhét thẳng dataclass vào state là loại lỗi CHỈ hỏng khi checkpointer
    Postgres thật chạy — unit test mock checkpointer sẽ bỏ lọt hoàn toàn (bài
    học SP-1C2, nơi một cơ chế dựa vào hạ tầng thật đi qua sạch mọi unit test
    rồi hỏng trên production). Ràng JSON thuần chọn cách không phải dựa vào đó.
    """
    return asdict(c)


def chunks_from_dicts(ds) -> list[Chunk]:
    """Dựng lại Chunk từ state để đưa vào cite_and_verify()."""
    return [Chunk(**d) for d in (ds or [])]


def make_gather_docs_node():
    """Chân TÀI LIỆU: retrieve() thuần, KHÔNG gọi LLM lần nào.

    Luôn truy xuất bằng NGUYÊN câu hỏi người dùng. `fusion` cũ phải mang cơ chế
    aux_queries vì agent tự chọn query và hay truyền từ khoá trần kiểu "SLA" —
    vốn không bao giờ kéo được sla.docx lên; fan-out dùng thẳng câu hỏi đầy đủ
    (chính là query mà docstring fusion nói là "reliably does"), nên cơ chế đó
    không còn cần trên đường này.
    """
    async def gather_docs(state: ERPAgentState) -> dict:
        query = _last_human(state)
        if not query:
            return {"doc_context": []}
        try:
            # retrieve() là psycopg ĐỒNG BỘ — to_thread giữ event loop rảnh
            # cho chân ERP chạy song song trong cùng superstep.
            result = await asyncio.to_thread(retrieve, query)
            chunks = ([] if result.is_empty() or not passes_floor(result)
                      else result.chunks)
        except Exception:
            # KHÔNG để exception thoát ra: LangGraph để lỗi một nhánh giết CẢ
            # superstep, tức chân ERP đang chạy song song cũng mất theo.
            logger.exception("gather_docs failed")
            chunks = []
        return {"doc_context": [chunk_to_dict(c) for c in chunks]}

    return gather_docs
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: tất cả PASS (6 test của Task 2 + 9 test mới).

`test_gather_docs_retrieves_with_full_question` kỳ vọng `aux_queries` là `None`
vì `gather_docs` gọi `retrieve(query)` không truyền kwarg đó.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/fanout.py backend/tests/agents/test_fanout.py
git commit -m "feat(sp2b): gather_docs — chân tài liệu 0 lượt LLM, state JSON thuần"
```

---

## Task 4: `gather_erp`

**Files:**
- Modify: `backend/src/agents/fanout.py`
- Test: `backend/tests/agents/test_fanout.py` (thêm vào)

**Interfaces:**
- Consumes: `fanout._last_human`, `prompts.GATHER_ERP_PROMPT`,
  `langchain.agents.create_agent` (import sẵn trong `fanout.py` với tên
  `_create_agent`), `erp_grounding.verify_erp_grounding(answer, tool_outputs, llm) -> str`.
- Produces: `fanout.make_gather_erp_node(llm, tools) -> async node(state) -> {"erp_facts": str}`

**Lưu ý cho người thực thi — vì sao có `verify_erp_grounding` ở đây:**
`fusion` cũ verify câu trả lời CUỐI so với tool output THÔ. Fan-out tách đôi,
nên nếu chỉ verify ở `fuse_answer` (so với `erp_facts`) thì dữ kiện do
`gather_erp` bịa ra sẽ không bao giờ bị bắt — tức SP-2b lặng lẽ làm YẾU một
bảo đảm an toàn đang có. Giữ nguyên bảo đảm đó bằng cách verify hai chặng:
`gather_erp` verify dữ kiện của mình so với tool output thô (đúng khuôn
`erp_read` đang dùng ở `nodes.py:103-106`), rồi `fuse_answer` verify câu trả
lời so với `erp_facts`. Bắc cầu là kín.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_fanout.py`:

```python
def _fake_agent(messages_out):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": messages_out})
    return agent


async def test_gather_erp_writes_last_ai_content(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="- Đơn S00042 giao 15/07/2026")]))
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert out == {"erp_facts": "- Đơn S00042 giao 15/07/2026"}


async def test_gather_erp_uses_gather_prompt(monkeypatch):
    import src.agents.fanout as fanout
    from src.agents.prompts import GATHER_ERP_PROMPT
    captured = {}

    def spy(llm, tools, system_prompt=None):
        captured["prompt"] = system_prompt
        return _fake_agent([AIMessage(content="ok")])

    monkeypatch.setattr(fanout, "_create_agent", spy)
    await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert captured["prompt"] == GATHER_ERP_PROMPT


async def test_gather_erp_passes_tools_through_unfiltered(monkeypatch):
    """KHÔNG bê deny-list WRITE_TOOL_NAMES của fusion.py sang: nó phủ 9/29 tool
    ghi nên thực tế là no-op, mà lại TRÔNG NHƯ một lớp phòng thủ. Lớp thật là
    allow-list build_erp_query_tools() do graph.py truyền vào — có test chốt
    riêng ở test_fanout_graph.py."""
    import src.agents.fanout as fanout
    captured = {}

    def spy(llm, tools, system_prompt=None):
        captured["names"] = [t.name for t in tools]
        return _fake_agent([AIMessage(content="ok")])

    monkeypatch.setattr(fanout, "_create_agent", spy)
    t = MagicMock(); t.name = "list_sale_orders"
    await fanout.make_gather_erp_node(MagicMock(), tools=[t])(_state("x?"))
    assert captured["names"] == ["list_sale_orders"]


async def test_gather_erp_swallows_exception(monkeypatch):
    import src.agents.fanout as fanout

    def boom(llm, tools, system_prompt=None):
        agent = MagicMock()

        async def explode(payload):
            raise RuntimeError("llm down")

        agent.ainvoke = explode
        return agent

    monkeypatch.setattr(fanout, "_create_agent", boom)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert out == {"erp_facts": ""}


async def test_gather_erp_never_writes_messages(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="ok")]))
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert "messages" not in out


async def test_gather_erp_verifies_grounding_against_raw_tool_output(monkeypatch):
    """fusion cũ verify câu trả lời CUỐI so với tool output THÔ. Fan-out tách
    đôi nên phải verify hai chặng, nếu không dữ kiện bịa ở chân này không bao
    giờ bị bắt."""
    import src.agents.fanout as fanout
    from langchain_core.messages import ToolMessage

    monkeypatch.setattr(
        fanout, "_create_agent",
        lambda llm, tools, system_prompt=None: _fake_agent([
            ToolMessage(content='{"count": 5}', name="list_sale_orders",
                        tool_call_id="1"),
            AIMessage(content="- Có 9 đơn trễ"),
        ]))
    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append((answer, tool_outputs))
        return "- Có 5 đơn trễ"

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert calls == [("- Có 9 đơn trễ", ['{"count": 5}'])]
    assert out == {"erp_facts": "- Có 5 đơn trễ"}


async def test_gather_erp_skips_grounding_when_no_tool_output(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="Không tìm được dữ kiện ERP liên quan.")]))
    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append(answer)
        return answer

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert calls == []
    assert out == {"erp_facts": "Không tìm được dữ kiện ERP liên quan."}
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -k gather_erp -v
```

Kỳ vọng: FAIL — `AttributeError: module 'src.agents.fanout' has no attribute 'make_gather_erp_node'`.

- [ ] **Step 3: Thêm `make_gather_erp_node` vào `fanout.py`**

Thêm sau `make_gather_docs_node`:

```python
def make_gather_erp_node(llm, tools):
    """Chân ERP: ReAct agent chế độ THU THẬP — nêu dữ kiện, không kết luận.

    Khác `erp_read` ở MỤC ĐÍCH chứ không phải trùng lặp. Hỏi "Đơn S00042 còn
    được hoàn hàng theo chính sách không?" thì `erp_read` với SYSTEM_PROMPT rất
    dễ trả lời "tôi không biết chính sách" thay vì đi lấy ngày giao của S00042 —
    đúng nửa dữ kiện mà `fuse_answer` cần.

    KHÔNG bê deny-list WRITE_TOOL_NAMES của fusion.py sang. Nó liệt kê 9 tên
    trong khi WRITE_PLANNER_PROMPT khai 29 tool ghi, nên thực tế là no-op — mà
    lại TRÔNG NHƯ một lớp phòng thủ. Lớp thật là allow-list
    build_erp_query_tools() do graph.py truyền vào, có test chốt containment
    (tests/agents/test_fanout_graph.py). Allow-list + test nói đúng sự thật;
    deny-list thiếu 20 tên thì không.

    verify_erp_grounding tại ĐÂY là cố ý: `fusion` cũ verify câu trả lời CUỐI
    so với tool output THÔ. Fan-out tách đôi, nên nếu chỉ verify ở fuse_answer
    (so với erp_facts) thì dữ kiện do chính chân này bịa ra sẽ không bao giờ bị
    bắt — SP-2b sẽ lặng lẽ làm YẾU một bảo đảm đang có. Hai chặng verify bắc
    cầu kín: dữ kiện ⊂ tool output thô, câu trả lời ⊂ dữ kiện.
    """
    async def gather_erp(state: ERPAgentState) -> dict:
        try:
            agent = _create_agent(llm, tools, system_prompt=GATHER_ERP_PROMPT)
            result = await agent.ainvoke({"messages": state["messages"]})
            msgs = result["messages"]
            facts = (msgs[-1].content or "").strip() if msgs else ""
            tool_outputs = [m.content for m in msgs if m.type == "tool"]
            if facts and tool_outputs:
                facts = await verify_erp_grounding(facts, tool_outputs, llm)
        except Exception:
            # Xem gather_docs: exception thoát ra giết CẢ superstep.
            logger.exception("gather_erp failed")
            facts = ""
        return {"erp_facts": facts}

    return gather_erp
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/fanout.py backend/tests/agents/test_fanout.py
git commit -m "feat(sp2b): gather_erp — chân ERP chế độ thu thập + verify grounding 2 chặng"
```

---

## Task 5: `render_fuse_input` + `fuse_answer`

**Files:**
- Modify: `backend/src/agents/fanout.py`
- Test: `backend/tests/agents/test_fanout.py` (thêm vào)

**Interfaces:**
- Consumes: `fanout.chunks_from_dicts`, `fanout._last_human`,
  `prompts.FUSE_PROMPT`, `synthesis._format_context(chunks, start=1) -> str`,
  `synthesis.cite_and_verify(body, chunks, llm) -> str`,
  `synthesis.SAFE_MSG`, `erp_grounding.verify_erp_grounding`.
- Produces:
  - `fanout.render_fuse_input(chunks: list[Chunk], erp_facts: str, question: str) -> str`
  - `fanout.make_fuse_answer_node(llm) -> async node(state) -> {"messages": [...], "doc_context": None, "erp_facts": None}`

**Hình dạng `render_fuse_input` phải khớp NGUYÊN VĂN chuỗi mà
`eval_multi_source` đang dựng tay hôm nay** (`run_eval.py:484-486`), vì Task 8
sẽ thay chuỗi tay đó bằng lời gọi hàm này:

```
TÀI LIỆU:
{_format_context(chunks)}

DỮ LIỆU ERP:
{erp_facts}

CÂU HỎI: {question}
```

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_fanout.py`:

```python
def test_render_fuse_input_shape():
    from src.agents.fanout import render_fuse_input
    from src.agents.synthesis import _format_context
    chunks = [_chunk()]
    out = render_fuse_input(chunks, "- Đơn S00042 giao 15/07/2026", "Hoàn được không?")
    assert out == (f"TÀI LIỆU:\n{_format_context(chunks)}\n\n"
                   f"DỮ LIỆU ERP:\n- Đơn S00042 giao 15/07/2026\n\n"
                   f"CÂU HỎI: Hoàn được không?")


def test_render_fuse_input_numbers_from_one():
    """fusion cũ phải tự quản start= tăng dần vì agent gọi search_documents
    nhiều lần. Fan-out truy xuất ĐÚNG MỘT LẦN nên sổ sách đó biến mất."""
    from src.agents.fanout import render_fuse_input
    out = render_fuse_input([_chunk(), _chunk(chunk_id=2)], "", "q?")
    assert "[1] " in out and "[2] " in out


def _fuse_state(doc_context, erp_facts, text="Đơn S00042 hoàn được không?"):
    return {"messages": [HumanMessage(content=text)], "intent": "mixed",
            "doc_context": doc_context, "erp_facts": erp_facts}


def _passthrough_cite():
    """Thay cite_and_verify: giữ nguyên thân, đính footer khi có chunk."""
    async def _cite(body, chunks, llm):
        return body + ("\n\n📄 Nguồn: policy.docx, tr.1" if chunks else "")
    return _cite


async def test_fuse_answer_happy_path_appends_citation_footer(monkeypatch):
    import src.agents.fanout as fanout
    c = _chunk(dense_score=0.7, section_path="Chính sách hoàn hàng › Điều 4",
               source_file="C:/docs/policy.docx", page=1)
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(
        content="Đơn đã quá 30 ngày nên không hoàn được."))
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    out = await fanout.make_fuse_answer_node(llm)(
        _fuse_state([asdict(c)], "- Đơn S00042 giao 15/07/2026"))
    content = out["messages"][0].content
    assert "Đơn đã quá 30 ngày nên không hoàn được." in content
    assert "📄 Nguồn: policy.docx, tr.1" in content


async def test_fuse_answer_both_empty_returns_safe_msg():
    import src.agents.fanout as fanout
    from src.agents.synthesis import SAFE_MSG
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=AssertionError("không được gọi LLM"))
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([], ""))
    assert out["messages"][0].content == SAFE_MSG


async def test_fuse_answer_clears_keys_on_happy_path(monkeypatch):
    import src.agents.fanout as fanout
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="xong"))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([asdict(_chunk())], "dữ kiện"))
    assert out["doc_context"] is None
    assert out["erp_facts"] is None


async def test_fuse_answer_clears_keys_on_safe_msg_path():
    import src.agents.fanout as fanout
    llm = MagicMock()
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([], ""))
    assert out["doc_context"] is None
    assert out["erp_facts"] is None


async def test_fuse_answer_clears_keys_on_exception():
    import src.agents.fanout as fanout
    from src.agents.synthesis import SAFE_MSG
    llm = MagicMock()

    async def boom(msgs):
        raise RuntimeError("llm down")

    llm.ainvoke = boom
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([asdict(_chunk())], "x"))
    assert out["messages"][0].content == SAFE_MSG
    assert out["doc_context"] is None
    assert out["erp_facts"] is None


async def test_fuse_answer_empty_llm_answer_returns_safe_msg():
    import src.agents.fanout as fanout
    from src.agents.synthesis import SAFE_MSG
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="   "))
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([asdict(_chunk())], "x"))
    assert out["messages"][0].content == SAFE_MSG


async def test_fuse_answer_uses_fuse_prompt_and_render(monkeypatch):
    import src.agents.fanout as fanout
    from src.agents.prompts import FUSE_PROMPT
    captured = {}

    async def spy_ainvoke(msgs):
        captured["system"] = msgs[0].content
        captured["human"] = msgs[1].content
        return AIMessage(content="xong")

    llm = MagicMock()
    llm.ainvoke = spy_ainvoke
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))
    c = _chunk()
    await fanout.make_fuse_answer_node(llm)(
        _fuse_state([asdict(c)], "- dữ kiện", text="Hoàn được không?"))
    assert captured["system"] == FUSE_PROMPT
    assert captured["human"] == fanout.render_fuse_input([c], "- dữ kiện",
                                                         "Hoàn được không?")


async def test_fuse_answer_verifies_grounding_against_erp_facts(monkeypatch):
    import src.agents.fanout as fanout
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Có 9 đơn trễ."))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    calls = []

    async def fake_verify(answer, tool_outputs, llm_):
        calls.append((answer, tool_outputs))
        return answer

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    await fanout.make_fuse_answer_node(llm)(_fuse_state([], "- Có 5 đơn trễ"))
    assert calls == [("Có 9 đơn trễ.", ["- Có 5 đơn trễ"])]


async def test_fuse_answer_skips_grounding_when_no_erp_facts(monkeypatch):
    import src.agents.fanout as fanout
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Theo tài liệu, 30 ngày."))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    calls = []

    async def fake_verify(answer, tool_outputs, llm_):
        calls.append(answer)
        return answer

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    await fanout.make_fuse_answer_node(llm)(_fuse_state([asdict(_chunk())], ""))
    assert calls == []
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -k "fuse or render" -v
```

Kỳ vọng: FAIL — `AttributeError: module 'src.agents.fanout' has no attribute 'render_fuse_input'`.

- [ ] **Step 3: Thêm `render_fuse_input` + `make_fuse_answer_node` vào `fanout.py`**

Thêm sau `make_gather_erp_node`:

```python
def render_fuse_input(chunks, erp_facts: str, question: str) -> str:
    """NGUỒN SỰ THẬT DUY NHẤT cho hình dạng input của fuse_answer.

    Dùng bởi CẢ node thật LẪN evals.run_eval.eval_multi_source — bắt buộc, không
    phải tiện tay. Bài học SP-2a: eval_intent() mirror hợp đồng đầu ra của router
    ở một module khác; Task 8 đổi hợp đồng, eval không đổi theo, acc rơi
    0.870 → 0.148 với MỌI ca parse thành "unknown", và không ai nghi ngờ vì lỗi
    trông y hệt lỗi chất lượng model. Dùng chung một hàm thì mirror KHÔNG THỂ
    trôi khỏi node thật.

    fusion cũ phải tự quản `start=` tăng dần vì agent gọi search_documents nhiều
    lần; fan-out truy xuất ĐÚNG MỘT LẦN nên _format_context chạy start=1 và sổ
    sách đó biến mất.
    """
    return (f"TÀI LIỆU:\n{_format_context(chunks)}\n\n"
            f"DỮ LIỆU ERP:\n{erp_facts}\n\n"
            f"CÂU HỎI: {question}")


def make_fuse_answer_node(llm):
    """Node JOIN: một lượt LLM trên cả hai nguồn, rồi trích dẫn + verify.

    Xoá hai key join lúc RA là VỆ SINH (một lượt erp_read sau đó không vác theo
    cả đống chunk trong checkpoint và trace Langfuse) — KHÁC với việc node
    `mixed` xoá lúc VÀO, vốn là lớp chịu lực cho TÍNH ĐÚNG. Hai chỗ, hai lý do,
    không phải hai lớp cho cùng một việc.
    """
    async def fuse_answer(state: ERPAgentState) -> dict:
        clear = {"doc_context": None, "erp_facts": None}
        chunks = chunks_from_dicts(state.get("doc_context"))
        erp_facts = state.get("erp_facts") or ""
        if not chunks and not erp_facts:
            # Hai chân cùng rỗng → không có gì để suy luận. Kiểm tra TẤT ĐỊNH,
            # không giao cho model tự nhận ra.
            return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
        try:
            resp = await llm.ainvoke([
                SystemMessage(content=FUSE_PROMPT),
                HumanMessage(content=render_fuse_input(
                    chunks, erp_facts, _last_human(state))),
            ])
            answer = (resp.content or "").strip()
            if not answer:
                return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
            answer = await cite_and_verify(answer, chunks, llm)
            if erp_facts:
                answer = await verify_erp_grounding(answer, [erp_facts], llm)
        except Exception:
            logger.exception("fuse_answer failed")
            answer = SAFE_MSG
        return {"messages": [AIMessage(content=answer)], **clear}

    return fuse_answer
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/fanout.py backend/tests/agents/test_fanout.py
git commit -m "feat(sp2b): fuse_answer + render_fuse_input (nguồn sự thật chung với eval)"
```

---

## Task 6: Node `mixed` (điểm fan-out)

**Files:**
- Modify: `backend/src/agents/fanout.py`
- Test: `backend/tests/agents/test_fanout.py` (thêm vào)

**Interfaces:**
- Consumes: không có (node không LLM, không I/O).
- Produces: `fanout.make_mixed_node() -> async node(state) -> {"doc_context": None, "erp_facts": None}`

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_fanout.py`:

```python
async def test_mixed_node_clears_both_join_keys():
    """LangGraph GIỮ giá trị channel khi node bỏ qua key. Nếu lượt sau
    gather_docs ngã và không ghi gì, fuse_answer sẽ trích dẫn chunk của lượt
    TRƯỚC — sai kiểu không ai thấy. Xoá tất định tại một chỗ khiến tính đúng
    không phụ thuộc vào việc mọi đường lỗi đều nhớ ghi key."""
    import src.agents.fanout as fanout
    stale = {"messages": [HumanMessage(content="câu mới")], "intent": "mixed",
             "doc_context": [asdict(_chunk())], "erp_facts": "dữ kiện lượt trước"}
    out = await fanout.make_mixed_node()(stale)
    assert out == {"doc_context": None, "erp_facts": None}


async def test_mixed_node_never_writes_messages():
    import src.agents.fanout as fanout
    out = await fanout.make_mixed_node()(_state("x?"))
    assert "messages" not in out
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -k mixed_node -v
```

Kỳ vọng: FAIL — `AttributeError: ... has no attribute 'make_mixed_node'`.

- [ ] **Step 3: Thêm `make_mixed_node` vào `fanout.py`**

Thêm ngay sau `chunks_from_dicts` (trước `make_gather_docs_node`):

```python
def make_mixed_node():
    """Điểm FAN-OUT. Không LLM, không I/O.

    Giữ nguyên TÊN `mixed` và nguyên chỗ trong intent_targets là quyết định có
    chủ đích: nhờ vậy `_route_by_intent` KHÔNG ĐỔI MỘT KÝ TỰ, mà hàm đó chính
    là thứ bộ eval SOP_SELECT_CASES đo trực tiếp ("Đích là giá trị
    _route_by_intent() TRẢ VỀ" — cases.py). Cho hàm đó trả về list
    ["gather_docs","gather_erp"] trông gọn hơn một dòng nhưng phá hợp đồng đầu
    ra mà bộ eval đang đo, và kéo theo cả lớp phủ quyết _looks_like_question
    của SP-2a phải chứng minh lại. Đổi 1 dòng lấy 1 bộ eval là lỗ.

    Node KHÔNG rỗng: xoá hai key join lúc VÀO là lớp CHỊU LỰC chống dữ liệu ôi
    qua lượt. LangGraph giữ giá trị channel khi node bỏ qua key, nên nếu ở lượt
    sau gather_docs ngã và không ghi gì, fuse_answer sẽ lặng lẽ trích dẫn chunk
    của lượt TRƯỚC. Xoá tất định tại đúng một chỗ khiến tính đúng KHÔNG phụ
    thuộc vào việc mọi đường lỗi của mọi chân đều nhớ ghi key.
    """
    async def mixed(state: ERPAgentState) -> dict:
        return {"doc_context": None, "erp_facts": None}

    return mixed
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/fanout.py backend/tests/agents/test_fanout.py
git commit -m "feat(sp2b): node mixed — điểm fan-out kiêm chỗ dọn key join"
```

---

## Task 7: Đấu dây graph, xoá `fusion.py`, test tích hợp trên `build_graph()` thật

**Files:**
- Modify: `backend/src/agents/graph.py`
- Delete: `backend/src/agents/fusion.py`
- Delete: `backend/tests/agents/test_fusion.py`
- Modify: `backend/tests/agents/test_graph_build.py:29-47`
- Create: `backend/tests/agents/test_fanout_graph.py`

**Interfaces:**
- Consumes: `fanout.make_mixed_node()`, `fanout.make_gather_docs_node()`,
  `fanout.make_gather_erp_node(llm, tools)`, `fanout.make_fuse_answer_node(llm)`;
  `erp_query.tools.build_erp_query_tools() -> list`.
- Produces: graph biên dịch có 4 node `mixed`/`gather_docs`/`gather_erp`/`fuse_answer`.

**KHÔNG ĐƯỢC ĐỔI:** `_route_by_intent`, `_QUESTION_MARKERS`,
`_looks_like_question`, dict `intent_targets`.

- [ ] **Step 1: Viết test tích hợp thất bại**

Tạo `backend/tests/agents/test_fanout_graph.py`:

```python
# backend/tests/agents/test_fanout_graph.py
"""Test wiring fan-out trên build_graph() THẬT.

Bài học SP-2a (review toàn nhánh): toàn bộ test node skill dựng StateGraph
bằng tay nên KHÔNG chứng minh được wiring thật; test đầu tiên gọi build_graph()
thật phải thêm vào ở đợt vá cuối. SP-2b làm ngay từ đầu.
"""
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.graph import build_graph


def _graph():
    return build_graph(MagicMock(), tools=[], checkpointer=None)


def test_build_graph_has_all_four_fanout_nodes():
    nodes = _graph().get_graph().nodes
    for name in ("mixed", "gather_docs", "gather_erp", "fuse_answer"):
        assert name in nodes


def test_build_graph_has_no_fusion_module():
    import importlib
    try:
        importlib.import_module("src.agents.fusion")
    except ModuleNotFoundError:
        return
    raise AssertionError("src.agents.fusion phải bị xoá ở SP-2b")


def test_gather_erp_tools_subset_of_read_tools(monkeypatch):
    """Lớp phòng thủ THẬT thay cho deny-list WRITE_TOOL_NAMES đã bỏ: node chỉ
    bao giờ nhận allow-list build_erp_query_tools()."""
    import src.agents.graph as graph_mod
    from src.erp_query.tools import build_erp_query_tools
    captured = {}
    real = graph_mod.make_gather_erp_node

    def spy(llm, tools):
        captured["names"] = {t.name for t in tools}
        return real(llm, tools)

    monkeypatch.setattr(graph_mod, "make_gather_erp_node", spy)
    graph_mod.build_graph(MagicMock(), tools=[], checkpointer=None)
    read_names = {t.name for t in build_erp_query_tools()}
    assert captured["names"] <= read_names
    assert {"list_sale_orders", "get_stock", "get_overdue_invoices"} <= captured["names"]


def test_route_by_intent_still_returns_plain_mixed_string():
    """Hợp đồng đầu ra mà SOP_SELECT_CASES đo — không được đổi ở SP-2b."""
    from src.agents.graph import _route_by_intent
    state = {"intent": "mixed", "sop": None,
             "messages": [HumanMessage(content="theo chính sách, đơn X hoàn được không?")]}
    assert _route_by_intent(state) == "mixed"


async def test_real_graph_mixed_turn_produces_one_answer(monkeypatch):
    """Một lượt `mixed` đầu-cuối qua build_graph() THẬT: cả hai chân chạy, ra
    ĐÚNG MỘT AIMessage, cả hai key join về None ở state cuối."""
    import src.agents.fanout as fanout
    import src.agents.nodes as nodes_mod
    from src.rag.types import Chunk, RetrievalResult

    c = Chunk(chunk_id=1, doc_id="d", source_file="C:/docs/policy.docx",
              doc_title="P", section_path="Chính sách hoàn hàng › Điều 4",
              page=1, sheet=None, row_range=None,
              text="Hoàn hàng trong 30 ngày.", dense_score=0.7,
              sparse_score=None, rrf_score=0.02, rank=0)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: RetrievalResult(
        query=q, query_used=q, chunks=[c], top_score=0.02, total_candidates=1))

    ran = set()

    def fake_agent(llm, tools, system_prompt=None):
        agent = MagicMock()

        async def ainvoke(payload):
            ran.add("gather_erp")
            return {"messages": [AIMessage(content="- Đơn S00042 giao 15/07/2026")]}

        agent.ainvoke = ainvoke
        return agent

    monkeypatch.setattr(fanout, "_create_agent", fake_agent)
    monkeypatch.setattr(fanout, "cite_and_verify",
                        AsyncMock(side_effect=lambda b, ch, l: b + "\n\n📄 Nguồn: policy.docx, tr.1"))
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))

    router_llm = MagicMock()
    router_llm.ainvoke = AsyncMock(return_value=AIMessage(content="intent: mixed\nsop:"))
    fuse_llm = MagicMock()
    fuse_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Đơn đã quá 30 ngày."))

    class _LLMs(dict):
        def __missing__(self, k):
            return MagicMock()

    llms = _LLMs(router=router_llm, fusion=fuse_llm)
    graph = build_graph(llms, tools=[], checkpointer=None)
    final = await graph.ainvoke(
        {"messages": [HumanMessage(content="Đơn S00042 hoàn được không theo chính sách?")]})

    assert "gather_erp" in ran                       # chân ERP đã chạy
    answers = [m for m in final["messages"] if m.type == "ai"]
    assert len(answers) == 1
    assert "Đơn đã quá 30 ngày." in answers[0].content
    assert "📄 Nguồn:" in answers[0].content          # chân tài liệu đã chạy
    assert final["doc_context"] is None
    assert final["erp_facts"] is None
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout_graph.py -v
```

Kỳ vọng: FAIL — `gather_docs` không có trong node; `src.agents.fusion` vẫn
import được.

- [ ] **Step 3: Sửa import trong `graph.py`**

Đổi dòng 14 từ:

```python
from .fusion import make_fusion_node
```

thành:

```python
from .fanout import (make_fuse_answer_node, make_gather_docs_node,
                     make_gather_erp_node, make_mixed_node)
```

- [ ] **Step 4: Đấu 4 node trong `build_graph`**

Thay dòng 97 (`g.add_node("mixed", make_fusion_node(...))`) bằng:

```python
    # Fan-out đường đọc (SP-2b): `mixed` giữ TÊN và giữ chỗ trong intent_targets
    # để _route_by_intent không phải đổi — hàm đó là thứ SOP_SELECT_CASES đo
    # trực tiếp. Hai chân chạy cùng superstep (hai cạnh thẳng ra), fuse_answer
    # có hai cạnh vào nên chỉ chạy sau khi CẢ HAI xong.
    g.add_node("mixed", make_mixed_node())
    g.add_node("gather_docs", make_gather_docs_node())
    g.add_node("gather_erp", make_gather_erp_node(
        llms["fusion"], build_erp_query_tools()))
    g.add_node("fuse_answer", make_fuse_answer_node(llms["fusion"]))
```

Thay dòng `g.add_edge("mixed", END)` bằng:

```python
    g.add_edge("mixed", "gather_docs")
    g.add_edge("mixed", "gather_erp")
    g.add_edge("gather_docs", "fuse_answer")
    g.add_edge("gather_erp", "fuse_answer")
    g.add_edge("fuse_answer", END)
```

- [ ] **Step 5: Xoá `fusion.py` và test cũ**

```bash
git rm backend/src/agents/fusion.py backend/tests/agents/test_fusion.py
```

- [ ] **Step 6: Sửa test spy đã chết trong `test_graph_build.py`**

Xoá nguyên hàm `test_mixed_node_built_with_erp_query_read_tools` (dòng 29-47) —
nó spy `make_fusion_node` đã không còn tồn tại. Việc nó bảo vệ ("không tool ghi
nào lọt vào nhánh mixed") nay do
`test_fanout_graph.py::test_gather_erp_tools_subset_of_read_tools` gánh, chặt
hơn (containment với allow-list thay vì kiểm 2 tên ghi cụ thể).

Giữ nguyên `test_build_graph_includes_mixed_node` — node `mixed` vẫn tồn tại.

- [ ] **Step 7: Chạy test tích hợp để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout_graph.py tests/agents/test_graph_build.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 8: Chạy toàn bộ test đơn vị**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Kỳ vọng: xanh. Nếu có ImportError từ module nào còn `from .fusion import ...`,
sửa module đó (chỉ `graph.py` được biết là có).

- [ ] **Step 9: Commit**

```bash
git add -A backend/src/agents backend/tests/agents
git commit -m "feat(sp2b): đấu fan-out vào graph, xoá fusion.py — _route_by_intent nguyên vẹn"
```

---

## Task 8: `eval_multi_source` đo đường mới; xoá `FUSION_PROMPT`

**Files:**
- Modify: `backend/evals/run_eval.py:30`, `:474-487`
- Modify: `backend/src/agents/prompts.py` (xoá `FUSION_PROMPT`)
- Modify: `backend/tests/agents/test_prompts.py:102`, `:112-121`
- Test: `backend/tests/agents/test_fanout.py` (thêm 1 test)

**Interfaces:**
- Consumes: `fanout.render_fuse_input(chunks, erp_facts, question) -> str`,
  `prompts.FUSE_PROMPT`.
- Produces: `run_eval.eval_multi_source` đo đúng hình dạng input của node thật.

**Vì sao đây là yêu cầu hạng nhất:** `eval_multi_source` KHÔNG gọi node thật —
nó mirror prompt bằng một lượt LLM tự dựng trên fixture đóng băng. Đúng cái bẫy
đã cắn SP-2a: Task 8 đổi hợp đồng đầu ra của router, `eval_intent()` ở module
khác vẫn parse hợp đồng cũ, acc rơi 0.870 → 0.148 và trông y hệt lỗi model.
Sửa bằng cách dùng chung `render_fuse_input()` — mirror khi đó KHÔNG THỂ trôi.

`erp_block` trong fixture đóng vai `erp_facts`: cả hai đều là văn bản dữ kiện
ERP thô, không phải câu trả lời. Hình dạng khớp.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_fanout.py`:

```python
def test_eval_multi_source_uses_shared_render_and_fuse_prompt():
    """Chống trôi giữa node thật và eval — bài học SP-2a (eval_intent mirror
    hợp đồng router cũ, acc 0.870 → 0.148)."""
    import inspect
    from evals import run_eval
    src = inspect.getsource(run_eval.eval_multi_source)
    assert "render_fuse_input" in src
    assert "FUSE_PROMPT" in src
    assert "FUSION_PROMPT" not in src
    # eval KHÔNG được dựng lại chuỗi input bằng tay
    assert "TÀI LIỆU:" not in src


def test_fusion_prompt_is_gone():
    from src.agents import prompts
    assert not hasattr(prompts, "FUSION_PROMPT")
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -k "eval_multi_source or fusion_prompt_is_gone" -v
```

Kỳ vọng: cả 2 FAIL.

- [ ] **Step 3: Sửa import trong `run_eval.py`**

Đổi dòng 30 từ:

```python
from src.agents.prompts import FUSION_PROMPT
```

thành:

```python
from src.agents.prompts import FUSE_PROMPT
from src.agents.fanout import render_fuse_input
```

- [ ] **Step 4: Sửa thân `eval_multi_source`**

Đổi docstring và lời gọi (dòng 474-487) thành:

```python
async def eval_multi_source(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo tổng hợp 2 nguồn trên fixture đóng băng — mirror node fuse_answer.

    Prompt VÀ hình dạng input đều lấy từ production (FUSE_PROMPT,
    render_fuse_input) — KHÔNG dựng lại bằng tay. Đây là điều kiện để mirror
    không trôi khỏi node thật: ở SP-2a, eval_intent() dựng lại cách parse đầu
    ra router ở module riêng, hợp đồng đổi mà eval không đổi theo, acc rơi
    0.870 → 0.148 và trông y hệt lỗi chất lượng model.

    erp_block của fixture đóng vai erp_facts — cả hai đều là văn bản dữ kiện
    ERP thô do chân gather_erp nộp lên, không phải câu trả lời.
    """
    lat: list[float] = []

    async def call(case):
        topic, erp_block, question, doc_fact, erp_fact = case
        chunks = fixtures.load_chunks(topic)
        resp, ms = await _timed(llm.ainvoke([
            SystemMessage(content=FUSE_PROMPT),
            HumanMessage(content=render_fuse_input(chunks, erp_block, question)),
        ]))
```

Phần còn lại của `call()` (từ `lat.append(ms)` trở đi) **giữ nguyên**, kể cả
`allowed = _digits(erp_block) | _digits(_format_context(chunks))` — cơ sở tính
`allowed` không đổi vì `render_fuse_input` dùng đúng `_format_context(chunks)`.

- [ ] **Step 5: Xoá `FUSION_PROMPT` khỏi `prompts.py`**

Xoá nguyên biến `FUSION_PROMPT = """..."""` (khối bắt đầu ở dòng 148 của bản
gốc). Không xoá `RAG_SYNTHESIS_PROMPT` hay `CITATION_VERIFY_PROMPT` ở cạnh.

- [ ] **Step 6: Sửa `test_prompts.py`**

Đổi dòng 102 từ:

```python
from src.agents.prompts import RAG_SYNTHESIS_PROMPT, FUSION_PROMPT
```

thành:

```python
from src.agents.prompts import RAG_SYNTHESIS_PROMPT, FUSE_PROMPT
```

Đổi hai hàm test (dòng 112-121) thành:

```python
def test_fuse_prompt_forbids_inline_section_numbers():
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in FUSE_PROMPT


def test_fuse_prompt_forbids_bracket_index_citation():
    assert "HAY số thứ tự đoạn tài liệu" in FUSE_PROMPT
```

Giữ nguyên phần thân/comment khác của hai hàm nếu có.

- [ ] **Step 7: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/agents/ -q
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 8: Chạy toàn bộ test đơn vị**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Kỳ vọng: xanh, 0 failed.

- [ ] **Step 9: Commit**

```bash
git add backend/evals/run_eval.py backend/src/agents/prompts.py backend/tests/agents/test_prompts.py backend/tests/agents/test_fanout.py
git commit -m "fix(sp2b): eval_multi_source dùng chung render_fuse_input — chống trôi mirror"
```

---

## Task 9: Comment tại chỗ (Phụ lục A của spec)

Quyết định nào đời sau không được bàn lại thì phải có comment trong file được
version-control, tại đúng điểm mã nó ảnh hưởng (standing rule ADR-010). Phần
lớn đã nằm trong docstring các node ở Task 3-6; task này bù hai chỗ nằm ngoài
`fanout.py`.

**Files:**
- Modify: `backend/src/llm/catalog.py:125`
- Modify: `backend/src/main.py:153`

**Interfaces:**
- Consumes: không có. Produces: không có (chỉ comment).

- [ ] **Step 1: Thêm comment "vai sống, node chết" vào `catalog.py`**

Ngay TRƯỚC dòng `"fusion":    ("gemini-3.1-flash-lite", "groq-llama-3.3-70b"),`
trong dict `CHAINS`, thêm:

```python
    # SP-2b (2026-08-01): node `fusion` trong graph đã bị XOÁ (thay bằng fan-out
    # mixed → gather_docs ‖ gather_erp → fuse_answer, xem agents/fanout.py).
    # VAI model tên "fusion" thì SỐNG NGUYÊN: gather_erp và fuse_answer đều dùng
    # nó. Đổi tên vai sẽ lan sang models.py, router.py, main.py và
    # eval_gate.py:ROLE_FOR_SET — và QĐ M3 (ADR-009) cấm đổi model/prompt khi
    # chưa qua eval gate. Tên set đo đã là "multi_source" (trung tính) chính vì
    # lường trước việc này.
```

- [ ] **Step 2: Sửa comment cũ nhắc `fusion_node` trong `main.py`**

Trong khối comment ở dòng ~153, đổi cụm `rag_node/fusion_node already degrade`
thành `rag_node/fuse_answer already degrade` — `fusion_node` không còn tồn tại
và comment cũ sẽ dẫn người đọc đi tìm một hàm đã chết.

- [ ] **Step 3: Xác nhận không còn tham chiếu chết nào tới node fusion**

```bash
cd backend
grep -rn "fusion_node\|make_fusion_node\|FUSION_PROMPT\|WRITE_TOOL_NAMES" src/ tests/ evals/ jobs/
```

Kỳ vọng: **không có kết quả nào**. (Các dòng chứa chữ `fusion` còn lại đều phải
là VAI model: `CHAINS["fusion"]`, `ROLES`, `HEAVY_ROLES`, `TOOL_ROLES`,
`ROLE_FOR_SET`, và comment mới thêm.)

- [ ] **Step 4: Chạy toàn bộ test đơn vị**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Kỳ vọng: xanh.

- [ ] **Step 5: Commit**

```bash
git add backend/src/llm/catalog.py backend/src/main.py
git commit -m "docs(sp2b): comment tại chỗ — vai fusion sống dù node chết"
```

---

## Task 10: Đo SAU, xác minh sống, viết báo cáo

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md`
- Create: `backend/tests/agents/test_dau_cuoi_fanout.py`

**Interfaces:**
- Consumes: mục `## Số đo TRƯỚC` của file report (Task 1).
- Produces: mục `## Số đo SAU`, `## Xác minh sống`, `## Kết luận`.

- [ ] **Step 1: Chạy đủ 3 chế độ pytest**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest -q -m integration
```

Kỳ vọng: cả hai xanh. Ghi lại số test passed của mỗi lượt.

Sau lượt chạy, khôi phục 2 fixture nhị phân bị suite `tests/rag/` re-serialize:

```bash
git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx
```

- [ ] **Step 2: Viết test live đầu-cuối**

Tạo `backend/tests/agents/test_dau_cuoi_fanout.py`:

```python
# backend/tests/agents/test_dau_cuoi_fanout.py
"""Xác minh sống fan-out `mixed` (SP-2b) — LLM thật, Postgres thật, RAG thật.

Chạy: pytest tests/agents/test_dau_cuoi_fanout.py -m live -v
"""
import pytest

pytestmark = pytest.mark.live


async def test_mixed_question_returns_one_grounded_answer_with_citations():
    from src.agents.erp_agent import ERPAgent
    agent = ERPAgent()
    await agent.setup()
    try:
        answer = await agent.chat(
            "Theo chính sách hoàn hàng, đơn S00042 còn hoàn được không?",
            thread_id="sp2b-live-fanout")
    finally:
        await agent.close()
    assert answer.strip()
    # fuse_answer phải đính khối trích dẫn tất định khi có chân tài liệu
    assert "📄 Nguồn:" in answer
    # KHÔNG được lộ marker nội bộ ra người dùng
    assert "NGUỒN_DÙNG" not in answer
```

**Trước khi chạy:** đọc `backend/src/agents/erp_agent.py` để lấy đúng tên
class/phương thức khởi tạo–đóng–gọi (`setup`/`chat`/`close` là tên kỳ vọng; nếu
khác, sửa test cho khớp mã thật, đừng sửa mã cho khớp test).

- [ ] **Step 3: Chạy test live**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/agents/test_dau_cuoi_fanout.py -m live -v
```

Kỳ vọng: PASS. Nếu FAIL, chép nguyên văn output vào report và điều tra — đây là
lượt duy nhất chạm hạ tầng thật, mọi thứ nó bắt được đều là lỗi thật.

- [ ] **Step 4: Chạy gate `multi_source` (SAU)**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Ghi lại đúng bộ chỉ số như Task 1 Step 2.

- [ ] **Step 5: Chạy gate `intent` và `sop_select` (SAU)**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set intent
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set sop_select
```

- [ ] **Step 6: Viết mục còn lại của report**

Nối vào `docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md`:

```markdown
## Số đo SAU

Chạy trên nhánh SP-2b tại commit `<sha>`, cùng model và cùng `--pace` như lượt TRƯỚC.

### multi_source (vai `fusion`)
- verdict: `<PASS|FAIL>`
- `both_source_coverage`: `<số>` (TRƯỚC: `<số>`)
- `citation_validity`: `<số>` (TRƯỚC: `<số>`)
- `fabricated_number`: `<số>` (TRƯỚC: `<số>`)
- `lat_p50` / `lat_p95`: `<số>` / `<số>` ms (TRƯỚC: `<số>` / `<số>`)
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`

### intent (vai `router`)
- verdict: `<PASS|FAIL>` — `acc`: `<số>` (TRƯỚC: `<số>`)

### sop_select (vai `router`)
- verdict: `FAIL` (biết trước) — `acc`: `<số>` (TRƯỚC: `<số>`), `hijack`: `<số>` (TRƯỚC: `<số>`)

## Xác minh sống

- Test đơn vị: `<N>` passed
- Test integration: `<N>` passed
- Test live `test_dau_cuoi_fanout.py`: `<PASS|FAIL>`
- Câu hỏi đã hỏi: "Theo chính sách hoàn hàng, đơn S00042 còn hoàn được không?"
- Trích nguyên văn câu trả lời nhận được:

```
<dán nguyên văn>
```

## Kết luận

Đối chiếu 7 điều kiện "SP-2b xong" của spec §8, mỗi điều một dòng đạt/không đạt
kèm bằng chứng. Nếu có điều kiện không đạt, nói thẳng là không đạt và vì sao —
không diễn giải lại thành đạt.

Latency là số **quan sát, không phải cổng** (spec §5.3): ghi lại, không dùng nó
để kết luận đạt/không đạt.
```

Thay mọi `<...>` bằng giá trị thật.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md backend/tests/agents/test_dau_cuoi_fanout.py
git commit -m "docs(sp2b): số đo SAU + xác minh sống đầu-cuối"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| §2.1 topology 4 node | 3, 4, 5, 6, 7 |
| §2.2 `_route_by_intent` không đổi | 6 (docstring), 7 (test chốt) |
| §2.3 `mixed` xoá key lúc vào | 6 |
| §2.4 vai `fusion` sống, node chết | 7 (xoá node), 9 (comment catalog) |
| §2.5 bốn node | 3, 4, 5, 6 |
| §2.6 file | toàn bộ |
| §3.1-3.2 key + JSON thuần | 2, 3 |
| §3.3 vòng đời hai chỗ | 5, 6 |
| §3.4 an toàn ghi song song | 3, 4, 5 (test `never_writes_messages`), 7 (test tích hợp) |
| §3.5 chân ngã | 3, 4, 5 |
| §3.6 bỏ deny-list | 4 (docstring), 7 (test containment) |
| §4.1-4.2 hai prompt + `render_fuse_input` | 2, 5 |
| §4.3 model không đổi vai | 7 (dùng `llms["fusion"]`) |
| §4.4 `/no_think` | 2 (test chốt) |
| §5.1 đo hai phần | 1, 10 |
| §5.2 `eval_multi_source` chống trôi | 8 |
| §5.3 bảng cổng | 1, 10 |
| §6 test | 3, 4, 5, 6, 7, 10 |
| §8 "xong nghĩa là" | 10 (mục Kết luận đối chiếu từng điều) |
| Phụ lục A comment tại chỗ | 3, 4, 5, 6, 9 |

**Một chỗ plan đi XA HƠN spec, cố ý:** Task 4 thêm `verify_erp_grounding` vào
`gather_erp`. Spec §2.5 chỉ nói `fuse_answer` verify. Lý do: `fusion` cũ verify
câu trả lời cuối so với tool output THÔ; tách đôi mà chỉ verify ở `fuse_answer`
thì dữ kiện bịa ở chân ERP không bao giờ bị bắt, tức SP-2b lặng lẽ làm YẾU một
bảo đảm đang có. Đây là giữ nguyên hiện trạng, không phải thêm tính năng —
nhưng người review nên soi kỹ chỗ này.

**Nhất quán kiểu:** `chunk_to_dict`/`chunks_from_dicts`/`render_fuse_input`/
`_last_human` dùng đúng một tên ở mọi task. Bốn factory đều theo khuôn
`make_<node>_node(...)` như `nodes.py`. Node factory không LLM (`mixed`,
`gather_docs`) không nhận tham số.
