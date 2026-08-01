# SP-2c: Bộ đo cho bước thu thập ERP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bộ đo THẬT cho bước thu thập ERP của `gather_erp` (SP-2b) —
điều mà bộ eval `multi_source` hiện tại không đo được vì nó đóng băng
`erp_block` viết tay — để biết trước khi sửa: `gather_erp` có lấy đủ dữ kiện
một chính sách đòi hỏi hay không, và tuần tự hoá fan-out (SP-2d) có đáng làm
không.

**Architecture:** Bộ ca `GATHER_CASES` tái dùng đúng fixture chính sách của
`MULTI_SOURCE_CASES`. `eval_gather(llm, pace, checkpoint_path, branch)` gọi
node `make_gather_erp_node` THẬT (nhánh `base`, được gate gác) với 25 tool
đọc thật bị bọc bằng stub fixture (giữ nguyên `name`/`description`/
`args_schema`, chỉ thay thân hàm) — hoặc, cho nhánh `policy` (không gate, chỉ
ghi nhận), chạy một biến thể có ghép chính sách vào prompt. Đo hai trục tách
bạch: `tool_recall` (chọn đủ tool chưa) và `fact_coverage` (dữ kiện có nổi
lên trong `erp_facts` chưa).

**Tech Stack:** Python 3.12, LangGraph 1.1.10, LangChain 1.2.18, pytest
9.1.1 (`asyncio_mode = auto`).

**Spec:** `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md`

## Global Constraints

- **0 dòng thay đổi trong `backend/src/agents/graph.py`, `fanout.py`,
  `state.py`, `prompts.py`.** SP-2c CHỈ dựng bộ đo. Không sửa `gather_erp`,
  không sửa `_route_by_intent`/`intent_targets`.
- **Stub tool phải bọc ĐỦ 25 tool** từ `build_erp_query_tools()` — không rút
  gọn tập lựa chọn. Rút gọn làm bài dễ đi, số đo vô nghĩa.
- **`eval_gather` là MỘT hàm, tham số `branch: str = "base"`** — không hai
  hàm riêng cho `base`/`policy`. Tránh hai bản logic đo trôi khỏi nhau.
- **Nhánh `base` PHẢI gọi `make_gather_erp_node` thật** (import từ
  `src.agents.fanout`), không dựng lại logic thu thập.
- **Nhánh `policy` KHÔNG gọi `make_gather_erp_node`** — production chưa có
  nhánh này, không có "hành vi thật" để mirror. Đây là thí nghiệm có kiểm
  soát, không phải hợp đồng chống trôi.
- **`required_facts`/`required_tools` phải khớp NGUYÊN VĂN với dữ liệu trong
  `tool_fixtures` của chính case đó** — tự-mâu-thuẫn (đòi model nói điều
  fixture không hề chứa) là lỗi phải test bắt được, theo đúng kỷ luật đã áp
  cho `MULTI_SOURCE_CASES` (`_grounded_match`, không heuristic mờ).
- **`--set gather` đăng ký nhưng loại khỏi `--set all` ngay từ đầu** — không
  đợi phát hiện vấn đề rồi mới loại (bài học `sop_select` ở SP-2a).
- **Không có `BASELINES["gather"]`** — không có baseline model cũ (node
  `gather_erp` không tồn tại trước SP-2b). Gate của set này trả `True` vô
  điều kiện ở lượt đo đầu — quan sát, không phải ngưỡng tuyệt đối.
- Chạy Python bằng `backend/.venv/Scripts/python.exe`. Đặt
  `PYTHONIOENCODING=utf-8` trước lệnh in tiếng Việt.
- "Full suite" trong repo này = `pytest -m "not integration and not live"`
  (`pytest.ini` không tự loại `live`/`integration`).

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Sửa | `backend/evals/cases.py` | thêm `GATHER_CASES` |
| Sửa | `backend/evals/run_eval.py` | thêm `_stub_erp_tools`, `_score_gather`, `_run_gather_with_prompt`, `eval_gather` |
| Sửa | `backend/jobs/eval_gate.py` | đăng ký `--set gather`, loại khỏi `--set all` |
| Tạo | `backend/tests/jobs/test_eval_gather.py` | test cho toàn bộ file này |
| Tạo | `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md` | báo cáo số đo — sản phẩm chính |

---

## Task 1: `GATHER_CASES` — dữ liệu ca đo

**Files:**
- Modify: `backend/evals/cases.py` (thêm vào cuối file)
- Test: `backend/tests/jobs/test_eval_gather.py` (tạo mới)

**Interfaces:**
- Consumes: `fixtures.available_topics()`, `fixtures.load_chunks(topic)` (đã có sẵn).
- Produces: `cases.GATHER_CASES: list[tuple[str, str, tuple[str,...], tuple[str,...], dict[str,str]]]`
  — mỗi phần tử là `(topic, question, required_tools, required_facts, tool_fixtures)`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/jobs/test_eval_gather.py`:

```python
# backend/tests/jobs/test_eval_gather.py
"""Set gather: đo bước THU THẬP của gather_erp — tách khỏi bước tổng hợp mà
multi_source đã đo. Không gate baseline-relative (không có baseline model cũ
— node gather_erp không tồn tại trước SP-2b)."""
from evals import cases, fixtures


def test_gather_cases_shape_and_topics_exist():
    assert len(cases.GATHER_CASES) >= 4
    topics = set(fixtures.available_topics())
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert question.strip()
        assert required_tools and all(t.strip() for t in required_tools)
        assert required_facts and all(f.strip() for f in required_facts)


def test_gather_cases_required_tools_have_fixtures():
    """Mọi tool trong required_tools PHẢI có mặt trong tool_fixtures của
    chính case đó — nếu không, case tự mâu thuẫn: đòi model gọi một tool mà
    không có dữ liệu nào để nó lấy được."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in tool_fixtures, (
                f"required_tools có {t!r} nhưng case {topic}/{question!r} "
                f"không có fixture cho tool đó")


def test_gather_cases_required_facts_exist_in_fixtures():
    """Nửa còn lại của kiểm tra tự-mâu-thuẫn: mỗi required_fact PHẢI xuất
    hiện nguyên văn (không phân biệt hoa/thường) trong ÍT NHẤT MỘT fixture
    của case đó — nếu không, case đòi model nói điều dữ liệu không hề chứa."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        corpus = " ".join(tool_fixtures.values()).casefold()
        for f in required_facts:
            assert f.casefold() in corpus, (
                f"required_fact {f!r} không có trong tool_fixtures của case "
                f"{topic}/{question!r}")


def test_gather_cases_required_tools_are_real_erp_tool_names():
    from src.erp_query.tools import build_erp_query_tools
    real_names = {t.name for t in build_erp_query_tools()}
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in real_names, (
                f"required_tools có {t!r} — không phải tên tool thật nào "
                f"trong build_erp_query_tools()")
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: FAIL — `AttributeError: module 'evals.cases' has no attribute 'GATHER_CASES'`.

- [ ] **Step 3: Thêm `GATHER_CASES` vào cuối `backend/evals/cases.py`**

```python
# ── GATHER_CASES ─────────────────────────────────────────────────────────────
# Đo bước THU THẬP của gather_erp (SP-2b/fanout.py) — TÁCH KHỎI bước tổng hợp
# mà MULTI_SOURCE_CASES đã đo trên erp_block viết tay. topic tái dùng ĐÚNG
# fixture chính sách của multi_source (fixtures.load_chunks) để hai bộ đo kể
# cùng một câu chuyện về cùng một chính sách.
#
# tool_fixtures: dữ liệu HAND-WRITTEN (không phải Odoo thật — fixture eval
# thật của multi_source cũng viết tay, cùng kỷ luật) cho MỖI tool trong
# required_tools; tool nào không có trong dict này thì stub trả "Không có dữ
# liệu liên quan." (xem run_eval._stub_erp_tools). required_facts PHẢI xuất
# hiện nguyên văn trong tool_fixtures của chính case (test chốt ở
# test_eval_gather.py) — tự-mâu-thuẫn là lỗi, không phải điều kiện khó.
GATHER_CASES = [
    # sla_giao_hang — hồi quy thật quan sát được ở Task 10 (SP-2b): model
    # đọc đúng chính sách 3-ngày-SLA nhưng nói "không cung cấp thông tin về
    # ngày xác nhận đơn hàng, ngày giao hàng thực tế" rồi từ chối kết luận
    # (logs/jobs/eval-gate-20260801T130223.json). Case này đo: nếu tool CÓ
    # đủ hai ngày đó, gather_erp có lấy và truyền đạt được không.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("get_sale_order_detail",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận) | "
      "ngày xác nhận: 18/07/2026 | ngày giao dự kiến: 20/07/2026 | "
      "loại đơn: thường"}),
    # chinh_sach_hoan_hang — cùng hình dạng: chính sách cần "ngày giao thực
    # tế" để tính hạn 30 ngày hoàn hàng.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("get_sale_order_detail",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao) | "
      "ngày giao thực tế: 15/07/2026"}),
    # chinh_sach_thanh_toan — câu hỏi giống hệt MULTI_SOURCE_CASES (S00050),
    # nhưng ở đây đo bước THU THẬP: "quá hạn 32 ngày" có nổi lên từ tool
    # get_overdue_invoices không, giữa nhiều dòng dữ liệu khác.
    ("chinh_sach_thanh_toan",
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     ("get_overdue_invoices",),
     ("32 ngày",),
     {"get_overdue_invoices":
      "3 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "quá hạn 32 ngày | còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "quá hạn 20 ngày | còn 1.000.000"}),
    # bang_gia_chiet_khau — ca 3 tool nối chuỗi (find_customer → find_product
    # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
    # một lượt gọi đơn.
    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
     ("find_customer", "find_product", "get_product_price"),
     ("12%",),
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price":
      "Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): "
      "2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"}),
]
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/cases.py backend/tests/jobs/test_eval_gather.py
git commit -m "feat(sp2c): GATHER_CASES — 4 ca đo bước thu thập ERP, tái dùng fixture multi_source"
```

---

## Task 2: `_stub_erp_tools` — bọc 25 tool đọc thật bằng fixture

**Files:**
- Modify: `backend/evals/run_eval.py`
- Test: `backend/tests/jobs/test_eval_gather.py` (thêm vào)

**Interfaces:**
- Consumes: `src.erp_query.tools.build_erp_query_tools() -> list`.
- Produces: `run_eval._stub_erp_tools(tool_fixtures: dict[str,str], called: list[str]) -> list`
  — trả về CHÍNH danh sách tool thật (đã bị mutate `.func`), giữ nguyên
  `name`/`description`/`args_schema`.

**Bẫy phải tránh — late-binding closure trong vòng lặp:** nếu viết
`def _stub(**kwargs): called.append(t.name); return fixture` NGAY TRONG vòng
`for t in tools:` mà không chốt `t`/`fixture` bằng default-argument, MỌI stub
sẽ dùng giá trị của LẦN LẶP CUỐI (Python đóng biến theo tham chiếu, không
theo giá trị tại thời điểm định nghĩa). Bài này có 25 tool — bug sẽ khiến
TẤT CẢ đều trả fixture của tool thứ 25, im lặng sai, không báo lỗi.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/jobs/test_eval_gather.py`:

```python
def test_stub_erp_tools_wraps_all_real_tools():
    from evals.run_eval import _stub_erp_tools
    from src.erp_query.tools import build_erp_query_tools
    called = []
    tools = _stub_erp_tools({}, called)
    real_names = {t.name for t in build_erp_query_tools()}
    stub_names = {t.name for t in tools}
    assert stub_names == real_names


def test_stub_erp_tools_returns_fixture_for_named_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({"get_stock": "Còn 10 Desk Pad."}, called)
    t = next(t for t in tools if t.name == "get_stock")
    out = t.func(product="Desk Pad")
    assert out == "Còn 10 Desk Pad."
    assert called == ["get_stock"]


def test_stub_erp_tools_default_no_data_for_unlisted_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({}, called)
    t = next(t for t in tools if t.name == "find_customer")
    out = t.func(name="anyone")
    assert out == "Không có dữ liệu liên quan."
    assert called == ["find_customer"]


def test_stub_erp_tools_no_late_binding_closure_bug():
    """Chốt đúng bẫy nêu trong docstring _stub_erp_tools — mỗi stub phải trả
    ĐÚNG fixture của TOOL CỦA NÓ, không phải fixture của tool cuối vòng lặp."""
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools(
        {"get_stock": "A", "find_customer": "B", "find_product": "C"}, called)
    a = next(t for t in tools if t.name == "get_stock").func()
    b = next(t for t in tools if t.name == "find_customer").func()
    c = next(t for t in tools if t.name == "find_product").func()
    assert (a, b, c) == ("A", "B", "C")
    assert called == ["get_stock", "find_customer", "find_product"]
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -k stub_erp_tools -v
```

Kỳ vọng: FAIL — `ImportError: cannot import name '_stub_erp_tools'`.

- [ ] **Step 3: Thêm import và `_stub_erp_tools` vào `backend/evals/run_eval.py`**

Thêm vào khối import ở đầu file (sau dòng `from src.agents.fanout import
render_fuse_input`):

```python
from src.agents.prompts import GATHER_ERP_PROMPT
from src.agents.fanout import make_gather_erp_node, _create_agent
from src.agents.erp_grounding import verify_erp_grounding
from src.erp_query.tools import build_erp_query_tools
```

Thêm hàm (đặt cạnh các helper `_norm`/`_grounded_match`, trước
`async def eval_multi_source`):

```python
def _stub_erp_tools(tool_fixtures: dict, called: list) -> list:
    """Bọc TOÀN BỘ tool đọc thật (build_erp_query_tools()) — giữ nguyên
    name/description/args_schema (allow-list y hệt production), chỉ thay
    THÂN hàm bằng tra cứu fixture. KHÔNG rút gọn tập lựa chọn: độ khó
    chọn-đúng-tool giữa 25 tool phải giữ nguyên như production (spec
    2026-08-01-sp2c §1.1) — rút gọn làm bài dễ đi, số đo vô nghĩa.

    BẪY late-binding closure: t/fixture PHẢI chốt bằng default-argument
    (_name=t.name, _fixture=fixture), không phải đọc trực tiếp t/fixture
    trong thân hàm lồng trong vòng lặp — nếu không MỌI stub sẽ trả fixture
    của tool CUỐI CÙNG trong vòng lặp, im lặng sai."""
    tools = build_erp_query_tools()
    for t in tools:
        fixture = tool_fixtures.get(t.name, "Không có dữ liệu liên quan.")

        def _stub(_name=t.name, _fixture=fixture, **kwargs):
            called.append(_name)
            return _fixture

        t.func = _stub
    return tools
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: tất cả PASS (4 từ Task 1 + 4 mới).

- [ ] **Step 5: Commit**

```bash
git add backend/evals/run_eval.py backend/tests/jobs/test_eval_gather.py
git commit -m "feat(sp2c): _stub_erp_tools — bọc 25 tool đọc thật bằng fixture, giữ nguyên schema"
```

---

## Task 3: `_score_gather` + `_run_gather_with_prompt` + `eval_gather`

**Files:**
- Modify: `backend/evals/run_eval.py`
- Test: `backend/tests/jobs/test_eval_gather.py` (thêm vào)

**Interfaces:**
- Consumes: `_stub_erp_tools`, `make_gather_erp_node(llm, tools)` (từ
  `fanout.py`), `_create_agent`, `verify_erp_grounding`, `GATHER_ERP_PROMPT`,
  `_format_context`, `fixtures.load_chunks`, `_timed`, `_percentiles`,
  `_norm`, `run_resilient`, `cases.GATHER_CASES`.
- Produces:
  - `run_eval._score_gather(erp_facts: str, called: list[str], required_tools: tuple, required_facts: tuple) -> tuple[bool, bool]`
  - `run_eval._run_gather_with_prompt(llm, tools, system_prompt: str, messages: list) -> dict`
  - `run_eval.eval_gather(llm, pace: float = 0.0, checkpoint_path=None, branch: str = "base") -> dict`

**Vì sao `_score_gather` là hàm riêng, không viết trực tiếp trong vòng lặp
async:** để test được KHÔNG CẦN mock LLM/agent — cùng kỷ luật project đã áp
cho `_grounded_match`/`_args_match`/`_digits` (mọi logic chấm điểm tách khỏi
lượt gọi mạng, test bằng input string thuần).

**Vì sao `eval_gather`'s wiring được test bằng đọc mã nguồn
(`inspect.getsource`), không phải mock cả vòng ReAct:** dự án này không có
tiền lệ mock một vòng LangChain ReAct đầy đủ cho test đơn vị của hàm
`eval_*` (xem `test_eval_multi_source.py` — chỉ test helper thuần
`_grounded_match`). Việc "gọi node thật đúng cách" được xác nhận bằng chạy
thật ở Task 5, không phải mock ở đây.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/jobs/test_eval_gather.py`:

```python
from evals import run_eval


def test_score_gather_both_ok():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026, giao dự kiến 20/07/2026",
        ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and fact_ok


def test_score_gather_tool_recall_fails_when_required_tool_not_called():
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026, 20/07/2026", ["find_customer"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert not tool_ok


def test_score_gather_fact_coverage_fails_when_fact_missing():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026", ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and not fact_ok


def test_score_gather_extra_tool_call_does_not_fail_recall():
    """required_tools là TẬP CON của called, không phải khớp tuyệt đối —
    model gọi thêm tool khác (dò tìm thêm) không bị tính là lỗi."""
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026", ["find_customer", "get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert tool_ok


def test_score_gather_fact_match_is_case_insensitive_normalized():
    tool_ok, fact_ok = run_eval._score_gather(
        "quá hạn 32 NGÀY", ["get_overdue_invoices"],
        ("get_overdue_invoices",), ("32 ngày",))
    assert tool_ok and fact_ok


def test_eval_gather_base_branch_calls_real_gather_erp_node():
    """Chống trôi: nhánh base PHẢI gọi make_gather_erp_node thật, không dựng
    lại logic thu thập (Global Constraint) — kiểm bằng đọc mã nguồn, cùng
    khuôn Task 8 SP-2b đã dùng cho eval_multi_source/render_fuse_input."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "make_gather_erp_node" in src
    assert "_stub_erp_tools" in src
    assert "_score_gather" in src


def test_eval_gather_policy_branch_does_not_call_real_node():
    """Nhánh policy KHÔNG gọi make_gather_erp_node — production chưa có
    nhánh này, gọi hàm thật sẽ chỉ chạy lại đúng prompt cũ, không đo được gì
    mới. Phải đi qua _run_gather_with_prompt riêng."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "_run_gather_with_prompt" in src


def test_run_gather_with_prompt_returns_erp_facts_key():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from langchain_core.messages import AIMessage, HumanMessage

    async def _run():
        agent = MagicMock()
        agent.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="18/07/2026")]})
        import src.agents.fanout as fanout_mod
        import unittest.mock
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: agent):
            out = await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])
        return out

    out = asyncio.run(_run())
    assert out == {"erp_facts": "18/07/2026"}


def test_run_gather_with_prompt_degrades_to_empty_on_exception():
    import asyncio
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    import unittest.mock

    async def _run():
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: (_ for _ in ()).throw(
                    RuntimeError("llm down"))):
            return await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])

    out = asyncio.run(_run())
    assert out == {"erp_facts": ""}
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -k "score_gather or eval_gather or run_gather_with_prompt" -v
```

Kỳ vọng: FAIL — `AttributeError: module 'evals.run_eval' has no attribute '_score_gather'`.

- [ ] **Step 3: Thêm `_score_gather`, `_run_gather_with_prompt`, `eval_gather` vào `backend/evals/run_eval.py`**

Thêm ngay sau `_stub_erp_tools` (Task 2):

```python
def _score_gather(erp_facts: str, called: list,
                  required_tools: tuple, required_facts: tuple) -> tuple[bool, bool]:
    """Tách riêng khỏi vòng lặp async để test được KHÔNG cần mock LLM/agent
    — cùng kỷ luật _grounded_match/_args_match/_digits. required_tools là
    TẬP CON của called (model gọi thêm tool khác không bị tính lỗi)."""
    tool_recall_ok = set(required_tools) <= set(called)
    low = _norm(erp_facts)
    fact_coverage_ok = all(_norm(f) in low for f in required_facts)
    return tool_recall_ok, fact_coverage_ok


async def _run_gather_with_prompt(llm, tools, system_prompt: str, messages: list) -> dict:
    """CHỈ dùng cho branch="policy" của eval_gather — production CHƯA CÓ
    nhánh này (spec 2026-08-01-sp2c §1.3), không có node thật để gọi. Cố ý
    mirror thân make_gather_erp_node (fanout.py) NHƯNG với system_prompt
    khác — một thí nghiệm có kiểm soát, KHÔNG phải hợp đồng phải chống trôi
    như branch="base" (không gate, không được coi là "khớp production")."""
    try:
        agent = _create_agent(llm, tools, system_prompt=system_prompt)
        result = await agent.ainvoke({"messages": messages})
        msgs = result["messages"]
        facts = (msgs[-1].content or "").strip() if msgs else ""
        tool_outputs = [m.content for m in msgs if m.type == "tool"]
        if facts and tool_outputs:
            facts = await verify_erp_grounding(facts, tool_outputs, llm)
    except Exception:
        facts = ""
    return {"erp_facts": facts}


async def eval_gather(llm, pace: float = 0.0, checkpoint_path=None, branch: str = "base"):
    """Đo bước THU THẬP của gather_erp — multi_source đo bước TỔNG HỢP trên
    erp_block viết tay, KHÔNG đo được liệu gather_erp thật có lấy đủ field
    hay không (spec 2026-08-01-sp2c). branch="base": gọi make_gather_erp_node
    THẬT — số này được gate GÁC (không có baseline model cũ, gate tuyệt đối
    trả True ở lượt đầu, xem eval_gate.py). branch="policy": ghép thêm
    _format_context(chunks) vào prompt trước khi hỏi — KHÔNG gọi node thật
    (production chưa có nhánh này), chỉ GHI NHẬN, không gate."""
    assert branch in ("base", "policy")
    lat: list[float] = []

    async def call(case):
        topic, question, required_tools, required_facts, tool_fixtures = case
        called: list = []
        tools = _stub_erp_tools(tool_fixtures, called)
        messages = [HumanMessage(content=question)]
        if branch == "base":
            node = make_gather_erp_node(llm, tools)
            out, ms = await _timed(node({"messages": messages}))
        else:
            chunks = fixtures.load_chunks(topic)
            policy_prompt = (GATHER_ERP_PROMPT
                            + "\n\nCHÍNH SÁCH LIÊN QUAN:\n"
                            + _format_context(chunks))
            out, ms = await _timed(_run_gather_with_prompt(
                llm, tools, policy_prompt, messages))
        lat.append(ms)
        erp_facts = out.get("erp_facts") or ""
        tool_recall_ok, fact_coverage_ok = _score_gather(
            erp_facts, called, required_tools, required_facts)
        if tool_recall_ok and fact_coverage_ok:
            return None
        return {"topic": topic, "question": question, "called": called,
                "required_tools": list(required_tools),
                "erp_facts": erp_facts[:300],
                "tool_recall_ok": tool_recall_ok,
                "fact_coverage_ok": fact_coverage_ok}
    fails, errors = await run_resilient(GATHER_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(GATHER_CASES)
    measured = n - len(errors)
    tool_recall_bad = sum(1 for f in fails if not f["tool_recall_ok"])
    fact_bad = sum(1 for f in fails if not f["fact_coverage_ok"])
    p50, p95 = _percentiles(lat)
    return {"set": "gather", "branch": branch, "n": n,
            "tool_recall": (measured - tool_recall_bad) / n if n else 0.0,
            "fact_coverage": (measured - fact_bad) / n if n else 0.0,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

Thêm import `GATHER_CASES` vào khối import `from evals.cases import (...)` ở
đầu file — chèn `GATHER_CASES,` vào đúng vị trí theo thứ tự alphabet hiện có
(giữa `CONFIRM_CASES` và `HALLUCINATION_MARKERS`).

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 5: Chạy toàn bộ test đơn vị**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Kỳ vọng: xanh, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/run_eval.py backend/tests/jobs/test_eval_gather.py
git commit -m "feat(sp2c): eval_gather — gọi gather_erp thật (base) + biến thể có chính sách (policy)"
```

---

## Task 4: Đăng ký `--set gather` trong `eval_gate.py`, loại khỏi `--set all`

**Files:**
- Modify: `backend/jobs/eval_gate.py`
- Test: `backend/tests/jobs/test_eval_gather.py` (thêm vào)

**Interfaces:**
- Consumes: `run_eval.eval_gather`.
- Produces: `--set gather` chạy được qua `python -m jobs run eval-gate --set gather`;
  `--set all` KHÔNG gồm `gather`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/jobs/test_eval_gather.py`:

```python
def test_gather_registered_in_eval_gate():
    from jobs import eval_gate
    assert "gather" in eval_gate.EVAL_FN
    assert eval_gate.EVAL_FN["gather"] is run_eval.eval_gather
    assert eval_gate.ROLE_FOR_SET["gather"] == "fusion"


def test_gather_excluded_from_baselines():
    """Không có baseline model cũ — node gather_erp không tồn tại trước
    SP-2b."""
    from jobs import eval_gate
    assert "gather" not in eval_gate.BASELINES


def test_gather_gate_returns_true_unconditionally():
    """Lượt đo đầu tiên: chưa có ngưỡng tuyệt đối, chỉ ghi nhận (spec §2)."""
    from jobs import eval_gate
    assert eval_gate._gate("gather", {"tool_recall": 0.0, "fact_coverage": 0.0}, None) is True
    assert eval_gate._gate("gather", {"tool_recall": 1.0, "fact_coverage": 1.0}, None) is True


def test_gather_excluded_from_set_all():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "all"])
    assert args.set == "all"
    assert "gather" in eval_gate.EVAL_FN  # đăng ký...
    # ...nhưng run() phải tự loại nó khi set == "all" — kiểm qua cùng công
    # thức run() dùng, không gọi run() thật (tốn API call thật).
    sets = [s for s in eval_gate.EVAL_FN if s not in ("sop_select", "gather")]
    assert "gather" not in sets
    assert "sop_select" not in sets
    assert "intent" in sets  # sanity: loại trừ không quá tay


def test_set_choices_includes_gather():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "gather"])
    assert args.set == "gather"
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -k "gather_registered or gather_excluded or gather_gate or set_choices" -v
```

Kỳ vọng: FAIL — `KeyError: 'gather'` hoặc `argparse` từ chối `--set gather`
(không có trong `choices`).

- [ ] **Step 3: Sửa `backend/jobs/eval_gate.py`**

Tìm khối `ROLE_FOR_SET` hiện tại (kết thúc bằng `"sop_select": "router"}` trên
một dòng) và đổi dòng cuối đó — chỉ dòng cuối, phần trên giữ nguyên — từ:

```python
                "multi_source": "fusion", "sop_select": "router"}
```

thành:

```python
                "multi_source": "fusion", "sop_select": "router",
                "gather": "fusion"}
```

(`gather` dùng CÙNG vai `fusion` mà `gather_erp` thật dùng trong `graph.py`,
không phải vai mới).

Tìm khối `EVAL_FN` hiện tại (kết thúc bằng `"sop_select": run_eval.eval_sop_select}`
trên một dòng) và đổi dòng cuối đó từ:

```python
           "sop_select": run_eval.eval_sop_select}
```

thành:

```python
           "sop_select": run_eval.eval_sop_select,
           "gather": run_eval.eval_gather}
```

**KHÔNG thêm `"gather"` vào `BASELINES`** — dict đó giữ nguyên, không có
entry cho `gather` (không có baseline model cũ).

Trong hàm `_gate()`, thêm nhánh MỚI ngay TRƯỚC dòng `if set_name == "intent":`:

```python
    if set_name == "gather":
        # Không có baseline model cũ (node gather_erp không tồn tại trước
        # SP-2b) — lần đo đầu chỉ ghi nhận, chưa có ngưỡng tuyệt đối. GÁC
        # NHẸ: mọi lần chạy đều PASS ở round này; số liệu vào báo cáo SP-2c
        # để người đọc tự đánh giá, không phải job tự đánh giá thay (spec
        # 2026-08-01-sp2c §2). Siết lại thành ngưỡng thật khi có đủ số đo.
        return True
```

Trong hàm `run()`, sửa dòng loại trừ `--set all` (tìm dòng
`sets = [s for s in EVAL_FN if s != "sop_select"]`), đổi thành:

```python
        sets = [s for s in EVAL_FN if s not in ("sop_select", "gather")]
```

Cập nhật comment ngay phía trên dòng đó (đang giải thích riêng `sop_select`)
để nhắc thêm `gather` — tìm khối comment bắt đầu `# sop_select CỐ Ý không
nằm trong "all"` và thêm ngay dưới nó:

```python
        # gather CŨNG cố ý không nằm trong "all" (spec 2026-08-01-sp2c §2):
        # chưa có baseline/ngưỡng tuyệt đối nào được xác nhận — để trong
        # "all" sẽ luôn PASS giả (gate trả True vô điều kiện) và làm loãng
        # tín hiệu của job hàng đêm mà không cảnh báo được gì thật. Theo dõi
        # riêng qua `--set gather` cho tới khi có đủ số đo để siết ngưỡng.
```

Trong hàm `add_args()`, sửa `choices=[...]` của `--set`, thêm `"gather"` vào
cuối danh sách:

```python
    p.add_argument("--set",
                   choices=["both", "all", "intent", "confirm", "chitchat",
                            "planner", "read", "synthesis", "multi_source",
                            "sop_select", "gather"],
                   default="both")
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Kỳ vọng: tất cả PASS.

- [ ] **Step 5: Chạy toàn bộ test đơn vị**

```bash
cd backend
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Kỳ vọng: xanh, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add backend/jobs/eval_gate.py backend/tests/jobs/test_eval_gather.py
git commit -m "feat(sp2c): đăng ký --set gather, loại khỏi --set all (chưa có ngưỡng tuyệt đối)"
```

---

## Task 5: Chạy thật cả hai nhánh, viết báo cáo

**Không sửa code.** Chạy `eval_gather` thật (model thật, node thật) trên cả
hai nhánh, ghi số liệu vào báo cáo — đây là SẢN PHẨM CHÍNH của SP-2c.

**Files:**
- Create: `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`

**Interfaces:**
- Consumes: `eval_gather` (Task 3), `--set gather` (Task 4).
- Produces: file báo cáo có số đo thật + khuyến nghị.

- [ ] **Step 1: Chạy nhánh `base` qua job CLI (được gate gác)**

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Ghi lại: verdict, `tool_recall`, `fact_coverage`, `lat_p50`/`lat_p95`, chi
tiết từng ca FAIL (`fails` trong log JSON — `topic`, `called`,
`required_tools`, `erp_facts`, `tool_recall_ok`, `fact_coverage_ok`), đường
dẫn log (`logs/jobs/eval-gate-<timestamp>.json`).

- [ ] **Step 2: Chạy nhánh `policy` trực tiếp (không qua job CLI — không gate)**

Viết một script chẩn đoán một lần, không commit vào repo (đặt trong thư mục
scratchpad hoặc chạy trực tiếp bằng `python -c`):

```python
import asyncio, json
from src.llm.catalog import chain_for
from evals import run_eval

async def main():
    spec = chain_for("fusion")[0]
    llm = run_eval._llm(spec.alias, role="fusion")
    pace = (60.0 / spec.rpm) * 1.2
    result = await run_eval.eval_gather(llm, pace=pace, branch="policy")
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(main())
```

Chạy:

```bash
cd backend
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "$(cat <<'EOF'
[nội dung script ở trên]
EOF
)"
```

(Hoặc lưu vào file tạm rồi chạy `python path/to/script.py` — miễn không
commit file này vào repo, nó chỉ phục vụ đo một lần.)

Ghi lại cùng bộ chỉ số như Step 1.

- [ ] **Step 3: So sánh, viết báo cáo**

Tạo `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`:

```markdown
# SP-2c — báo cáo số đo bước thu thập ERP

Plan: `docs/superpowers/plans/2026-08-01-sp2c-gather-eval.md`
Spec: `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md`

## Nhánh `base` (production hôm nay — được gate gác)

Chạy qua `jobs run eval-gate --set gather`, model: `<tên model thật>`.

- verdict: `<PASS — gate trả True vô điều kiện ở lượt đầu>`
- `tool_recall`: `<số>`
- `fact_coverage`: `<số>`
- `lat_p50` / `lat_p95`: `<số>` / `<số>` ms
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`
- Chi tiết ca FAIL (nếu có): `<liệt kê topic, tool đã gọi vs required_tools,
  erp_facts thực tế, thiếu field/tool nào>`

## Nhánh `policy` (có ghép chính sách vào prompt — chỉ ghi nhận, không gate)

Chạy trực tiếp `eval_gather(..., branch="policy")`, cùng model.

- `tool_recall`: `<số>` (hiệu số so `base`: `<+/-số>`)
- `fact_coverage`: `<số>` (hiệu số so `base`: `<+/-số>`)
- `lat_p50` / `lat_p95`: `<số>` / `<số>` ms
- Chi tiết ca còn FAIL (nếu có), so với `base`: `<...>`

## Kết luận

`<Một trong hai:>`

**Nếu `fact_coverage` nhánh `base` đã cao (gần 1.0):** giả thuyết "gather_erp
không thấy chính sách nên lấy thiếu field" SAI — 2 ca FAIL còn lại của
`multi_source` không phải do thiếu tuần tự hoá. Không đề xuất SP-2d theo
hướng tuần tự hoá fan-out. Nguyên nhân thật (nếu có) nằm ở chỗ khác, ngoài
phạm vi đo của SP-2c.

**Nếu `fact_coverage` nhánh `base` thấp VÀ nhánh `policy` cải thiện rõ rệt:**
giả thuyết ĐÚNG — tuần tự hoá fan-out (SP-2d) đáng làm, có số đo thật để
biện minh chi phí mất tính song song. Nêu rõ mức cải thiện cụ thể
(`fact_coverage` tăng bao nhiêu điểm phần trăm).

**Nếu cả hai nhánh đều thấp như nhau:** vấn đề không nằm ở việc THIẾU chính
sách trong prompt — có thể là giới hạn của chính 25 tool đọc (dữ liệu cần
thiết không tồn tại trong bất kỳ tool nào), hoặc vấn đề chọn tool
(`tool_recall` thấp) chứ không phải truyền đạt. Nêu rõ nhánh nào (tool_recall
hay fact_coverage) là điểm nghẽn thật, dẫn chứng bằng ca cụ thể.

Thay `<...>` bằng nội dung thật, dựa đúng vào số đo — không đoán trước kết
luận rồi đi tìm số ủng hộ.
```

Thay TOÀN BỘ `<...>` bằng số thật và diễn giải thật.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md
git commit -m "docs(sp2c): số đo thật 2 nhánh base/policy cho bước thu thập ERP"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| §1.1 node thật + stub 25 tool | 2, 3 |
| §1.2 hình dạng ca đo, tự-mâu-thuẫn phải test được | 1 |
| §1.3 hai nhánh, một hàm `branch` param | 3 |
| §1.4 hai trục tách bạch | 3 |
| §2 gate: không baseline, loại khỏi `--set all`, comment tại chỗ | 4 |
| §3 điều 1-3 (cases, eval_gather, đăng ký gate) | 1, 2, 3, 4 |
| §3 điều 4-5 (chạy thật, báo cáo) | 5 |
| §3 điều 6 (0 dòng production đổi) | Global Constraints, xác nhận: Task 1-5 chỉ đụng `cases.py`/`run_eval.py`/`eval_gate.py`/test/report — không file nào trong Global Constraints' danh sách cấm |
| §3 điều 7 (test xanh unit-only) | 3, 4 |
| Phụ lục A (3 quyết định cần comment tại chỗ) | 4 (loại khỏi all), 2 (bọc đủ 25 tool — docstring), 3 (một hàm branch — docstring) |

**Nhất quán kiểu:** `_score_gather`/`_stub_erp_tools`/`_run_gather_with_prompt`
dùng đúng một tên xuyên suốt Task 2-4. `eval_gather` theo đúng chữ ký chung
`(llm, pace=0.0, checkpoint_path=None)` của mọi hàm `eval_*` khác trong
`run_eval.py`, cộng đúng một tham số mới `branch="base"` có default — không
phá vỡ cách `eval_gate.py` gọi `EVAL_FN[set_name](llm, pace=pace,
checkpoint_path=checkpoint)` cho 8 set hiện có.

**Một quyết định đáng chú ý khi review:** Task 3 KHÔNG mock một vòng
LangChain ReAct đầy đủ để test `eval_gather`'s wiring — thay vào đó tách
logic chấm điểm (`_score_gather`) ra test thuần, và xác nhận wiring đúng
bằng đọc mã nguồn (`inspect.getsource`). Đây là chủ đích, khớp tiền lệ có
sẵn của `test_eval_multi_source.py` (chỉ test `_grounded_match`, không mock
`eval_multi_source` end-to-end) — không phải né việc test.
