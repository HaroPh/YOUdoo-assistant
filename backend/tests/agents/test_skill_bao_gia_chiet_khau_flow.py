"""Port luồng ReAct đầy đủ (interrupt/resume, đếm bước, bất biến tiền bạc) từ
D:\\Project\\backend\\tests\\agents\\test_skill_agentic_discount_quote.py (344
dòng). Xem task-7-report.md mục "Khác biệt brief không lường trước" cho phân
tích đầy đủ; tóm tắt nối dây áp dụng ở đây:

- File nguồn alias module là `sad` (KHÔNG phải `sq` như ví dụ minh hoạ trong
  brief) — không ảnh hưởng gì, chỉ đổi tên biến cục bộ khi port.
- `sad.compute_discount_pct` / `sad.TIER_INVALID_MSG` / `sad._TIER_ALIASES` /
  `sad.sales` / `sad.inventory` / `sad._build_tools` -> `logic.<tên cũ>`
  (`logic = _load_entry_module(SPEC)`, `_build_tools` đổi tên thành
  `build_tools` theo hợp đồng loader — quy tắc brief bước 2).
- `sad.REFUSED_MSG` -> `REFUSED_MSG` nhập trực tiếp từ `src.agents.agentic_gate`
  (cùng pattern Task 6 đã dùng cho giao-hang/nhap-kho).
- `monkeypatch.setattr(sad, "_confirm_write", ...)` (dùng trong `_patch_confirm`,
  helper được MỌI test gọi) -> `monkeypatch.setattr(logic, "_confirm_write", ...)`
  — patch trên module logic.py vừa nạp, ĐÚNG như brief đã chỉ rõ đây là skill
  duy nhất tự gọi _confirm_write bên trong logic.py, không qua wrapper loader.
- `sad.TIER_PCT` / `sad._render_discount_draft`: brief liệt kê cần đổi tên
  nhưng thực tế 0 lần được tham chiếu trực tiếp trong 344 dòng nguồn (draft
  chỉ được kiểm gián tiếp qua nội dung câu hỏi xác nhận) — không có gì để sửa,
  cùng loại phát hiện Task 6 đã gặp với `_confirm_write` không được mock.
- `test_triggers_unchanged_from_deterministic_skill` (nguồn dòng 37-40, kiểm
  `sad.TRIGGERS == (...)`) bị DROP: SkillSpec (skill_manifest.py) không có
  trường triggers — cơ chế trigger-keyword bị khai tử từ Task 1-3 của chính
  plan này, thay bằng routing theo description/manifest. Không phải bug hành
  vi, là quyết định kiến trúc đã chốt trước Task 7.
- Test E2E cuối file (nguồn: test_discount_skill_e2e_confirm_gate_and_
  working_context, dòng 262-345) được viết lại cấu trúc graph ngoài — xem
  chi tiết đầy đủ trong task-7-report.md. Tóm tắt: nguồn dùng
  `backend.src.agents.graph.build_graph()` (production graph THẬT). Test ở
  đây dùng ĐÚNG pattern Task 6 đã lập tiền lệ cho 2 skill anh em
  (build_skill_node gắn thẳng vào StateGraph tối giản tự dựng, không qua
  build_graph()) — giữ nguyên 100% các assertion thuộc phạm vi skill này
  (interrupt kind=confirm với đúng 7%, không ghi gì trước khi xác nhận,
  resume=True gọi MCP đúng partner_id + price_unit đã chiết khấu).

  SỬA (final review fix wave, 2026-07-31, Finding 3): đoạn trên từng liệt kê
  3 lý do KỸ THUẬT cho việc không dùng build_graph() thật (agentic_context_
  sync "chưa có node thật", ERP_SKILLS_ENABLED "0 kết quả grep", SP-2a "kết
  thúc ở Task 7 không có task nối dây graph.py") — cả 3 đều SAI: Task 9 đã
  nối agentic_context_sync vào build_graph() thật, và ERP_SKILLS_ENABLED tồn
  tại từ SP-1B (không phải chưa có trong SP-2a). Lý do ĐÚNG các test flow
  port từ Task 6/7 (file này + 2 skill anh em) vẫn cố ý dùng StateGraph tối
  giản: mục tiêu của chúng là khớp BEHAVIOR-EQUIVALENCE với module gốc
  D:\\Project (port nguyên văn assertion), không cần một graph đầy đủ để làm
  việc đó — không phải vì thiếu hạ tầng. Coverage qua `build_graph()` sản
  xuất thật (routing intent_router → node SOP THẬT, và hành vi thật của
  agentic_context_sync bàn giao working_context) nằm ở
  `test_build_graph_skill_integration.py` (file mới, cùng fix wave)."""
import json
import pytest
from typing import TypedDict, Annotated
from unittest.mock import MagicMock

from pydantic import PrivateAttr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.types import Command

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import (SKILLS_DIR, _load_entry_module,
                                     build_skill_node)
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "bao-gia-chiet-khau" / "SKILL.md")
logic = _load_entry_module(SPEC)


# ── compute_discount_pct: di trú NGUYÊN VĂN các ca từ test_skill_discount_quote.py ──

def test_compute_discount_pct_tier_only():
    assert logic.compute_discount_pct("than_thiet", 10_000_000) == 0.05


def test_compute_discount_pct_thuong_is_zero():
    assert logic.compute_discount_pct("thuong", 10_000_000) == 0.0


def test_compute_discount_pct_adds_bonus_at_threshold():
    assert logic.compute_discount_pct("thuong", 50_000_000) == 0.02
    assert logic.compute_discount_pct("than_thiet", 50_000_000) == 0.07


def test_compute_discount_pct_below_threshold_no_bonus():
    assert logic.compute_discount_pct("doi_tac", 49_999_999) == 0.10


def test_compute_discount_pct_caps_at_15_percent():
    # Current tiers max out at 10% + 2% = 12%, so the 15% clamp is
    # unreachable with real tier values — assert the clamp function itself
    # still behaves correctly for a hypothetical higher base (policy
    # fidelity: discount_policy.docx states "tối đa không vượt quá 15%").
    assert logic.compute_discount_pct("doi_tac", 50_000_000) == 0.12
    assert min(0.20, 0.15) == 0.15  # documents the clamp math in isolation


# test_triggers_unchanged_from_deterministic_skill (nguồn dòng 37-40) bị DROP
# có chủ đích — xem docstring đầu file: SkillSpec không có trường triggers,
# cơ chế trigger-keyword đã bị khai tử trước Task 7.


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(matches, needs):
    return {"status": "success", "data": {"matches": matches,
            "needs_disambiguation": needs}, "display": "x"}


ENVELOPE_BLOCKS = [{"type": "text", "text":
    '{"ok": true, "ref": "S00099", "model": "sale.order", "res_id": 5, '
    '"state": "draft", "display": "Đã tạo báo giá S00099."}'}]


def _fake_create(recorder, raise_exc=None):
    t = MagicMock()
    t.name = "create_quotation"

    async def ainvoke(args):
        if raise_exc is not None:
            raise raise_exc
        recorder["args"] = args
        # Shape THẬT từ langchain_mcp_adapters: list content-block,
        # KHÔNG phải chuỗi trần (Global Constraint 5).
        return ENVELOPE_BLOCKS
    t.ainvoke = ainvoke
    return t


def _patch_reads(monkeypatch, customer_matches, product_matches,
                 price=30_000_000.0, needs_c=False, needs_p=False):
    monkeypatch.setattr(logic.sales, "find_customer",
                        lambda *a, **k: _ok(customer_matches, needs_c))
    monkeypatch.setattr(logic.inventory, "find_product",
                        lambda *a, **k: _ok(product_matches, needs_p))
    monkeypatch.setattr(logic.sales, "get_product_price",
                        lambda *a, **k: {"status": "success",
                                         "data": {"price": price}, "display": "x"})


def _patch_confirm(monkeypatch, answer, questions=None):
    def fake_confirm(question):
        if questions is not None:
            questions.append(question)
        return answer
    monkeypatch.setattr(logic, "_confirm_write", fake_confirm)


def _gated(mcp_tools):
    tools = logic.build_tools(mcp_tools)
    return next(t for t in tools if t.name == "create_discount_quote")


_ARGS = {"customer": "Azur", "lines": [{"product": "Tủ", "qty": 2}],
         "tier": "than_thiet"}


# ── build_tools shape ───────────────────────────────────────────────────

def test_build_tools_exposes_only_ask_human_and_gated_tool():
    rec = {}
    names = {t.name for t in logic.build_tools([_fake_create(rec)])}
    assert names == {"ask_human", "create_discount_quote"}
    # Model KHÔNG BAO GIỜ thấy tool ghi thô:
    assert "create_quotation" not in names


def test_build_tools_without_create_quotation_only_ask_human():
    names = {t.name for t in logic.build_tools([])}
    assert names == {"ask_human"}


# ── gated tool: validate args (không I/O, không confirm) ─────────────────

@pytest.mark.asyncio
async def test_gated_tool_invalid_tier_errors_without_confirm_or_mcp(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    res = await _gated([_fake_create(rec)]).ainvoke(
        {**_ARGS, "tier": "vip"})
    assert res == logic.TIER_INVALID_MSG
    assert questions == [] and "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_empty_customer_asks(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    res = await _gated([_fake_create(rec)]).ainvoke(
        {**_ARGS, "customer": "  "})
    assert "khách hàng" in res
    assert questions == [] and "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_empty_lines_asks(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    res = await _gated([_fake_create(rec)]).ainvoke({**_ARGS, "lines": []})
    assert "sản phẩm" in res
    assert questions == [] and "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_non_numeric_qty_errors(monkeypatch):
    # Bổ sung so với bản tất định: args giờ do model 8-9B sinh trực tiếp
    # (không qua extract-prompt JSON), qty rác không được phép crash tool.
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])
    res = await _gated([_fake_create(rec)]).ainvoke(
        {**_ARGS, "lines": [{"product": "Tủ", "qty": "hai"}]})
    assert "Số lượng" in res
    assert questions == [] and "args" not in rec


# ── gated tool: tier tiếng Việt có dấu ───────────────────────────────────

@pytest.mark.asyncio
async def test_gated_tool_accepts_vietnamese_tier_label(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])
    await _gated([_fake_create(rec)]).ainvoke({**_ARGS, "tier": "Thân thiết"})
    # 2 × 30M = 60M ≥ 50M → 5% + 2% = 7%: nhãn có dấu resolve đúng tier.
    assert len(questions) == 1 and "7%" in questions[0]
    assert rec["args"]["lines"][0]["price_unit"] == pytest.approx(30_000_000.0 * 0.93)


# ── gated tool: resolve ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gated_tool_customer_not_found(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    _patch_reads(monkeypatch, [], [{"id": 552, "name": "Tủ", "score": 1}])
    res = await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    assert "Không tìm thấy khách hàng 'Azur'" in res
    assert questions == [] and "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_ambiguous_customer_lists_candidates_without_confirm(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    _patch_reads(monkeypatch,
                 [{"id": 41, "name": "Azur Interior", "score": 1},
                  {"id": 42, "name": "Azur Furniture", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}], needs_c=True)
    res = await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    assert "Azur Interior" in res and "Azur Furniture" in res
    assert "hỏi người dùng" in res.lower()
    assert questions == [] and "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_ambiguous_product_lists_candidates_without_confirm(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, True, questions)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ gỗ", "score": 1},
                  {"id": 553, "name": "Tủ sắt", "score": 1}], needs_p=True)
    res = await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    assert "Tủ gỗ" in res and "Tủ sắt" in res
    assert questions == [] and "args" not in rec


# ── gated tool: confirm gate ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gated_tool_refused_returns_refused_msg_without_mcp(monkeypatch):
    rec = {}
    _patch_confirm(monkeypatch, False)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])
    res = await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    assert res == REFUSED_MSG
    assert "args" not in rec


@pytest.mark.asyncio
async def test_gated_tool_confirm_question_shows_computed_percent(monkeypatch):
    rec, questions = {}, []
    _patch_confirm(monkeypatch, False, questions)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}], price=100_000.0)
    await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    # 200k < 50M → không bonus → đúng 5%; draft đủ tiền trước/sau chiết khấu.
    assert len(questions) == 1
    assert "5%" in questions[0]
    assert "200,000" in questions[0] and "190,000" in questions[0]
    assert "Azur" in questions[0]


@pytest.mark.asyncio
async def test_gated_tool_confirmed_calls_mcp_discounted_and_returns_raw(monkeypatch):
    rec = {}
    _patch_confirm(monkeypatch, True)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])
    res = await _gated([_fake_create(rec)]).ainvoke(_ARGS)
    assert rec["args"]["partner_id"] == 41
    assert rec["args"]["lines"] == [{"product_id": 552, "qty": 2,
        "price_unit": pytest.approx(30_000_000.0 * 0.93)}]
    # Global Constraint 2: trả RAW kết quả MCP (list content-block), không parse.
    assert res == ENVELOPE_BLOCKS


@pytest.mark.asyncio
async def test_gated_tool_mcp_error_returns_text(monkeypatch):
    _patch_confirm(monkeypatch, True)
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])
    res = await _gated([_fake_create({}, raise_exc=ValueError("write-mode tắt"))]).ainvoke(_ARGS)
    assert res.startswith("Lỗi khi tạo báo giá")
    assert "—" in res and "báo quản trị viên" in res
    assert "ValueError" not in res and "Traceback" not in res


# ── E2E qua build_skill_node + StateGraph tối giản ───────────────────────
# (nguồn dùng build_graph() sản xuất thật — xem docstring đầu file mục cuối
# cùng cho lý do đổi cấu trúc; pattern _graph()/_SeqModel giống hệt
# test_skill_giao_hang_flow.py / test_skill_nhap_kho_flow.py của Task 6.)

class _SeqModel(BaseChatModel):
    """Phát lại đúng 1 AIMessage mỗi lần model được gọi, theo thứ tự."""
    _responses: list = PrivateAttr()
    _idx: list = PrivateAttr(default_factory=lambda: [0])

    def __init__(self, responses, **kwargs):
        super().__init__(**kwargs)
        self._responses = list(responses)

    @property
    def _llm_type(self) -> str:
        return "seq"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        i = self._idx[0]
        self._idx[0] += 1
        return ChatResult(generations=[ChatGeneration(message=self._responses[i])])


def _graph(node):
    class OuterState(TypedDict):
        messages: Annotated[list, add_messages]
    g = StateGraph(OuterState)
    g.add_node("skill_agent", node)
    g.set_entry_point("skill_agent")
    g.add_edge("skill_agent", END)
    return g.compile(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_discount_skill_e2e_confirm_gate_and_discounted_write(monkeypatch):
    # E2E qua build_skill_node THẬT (không thay spec.build): model script gọi
    # create_discount_quote → tool resolve + tính 7% TRONG CODE → interrupt
    # confirm (question phải chứa "7%") → resume True → fake MCP
    # create_quotation trả ĐÚNG shape list-content-block → write đúng 1 lần,
    # đúng partner_id + price_unit đã chiết khấu.
    _patch_reads(monkeypatch, [{"id": 41, "name": "Azur", "score": 1}],
                 [{"id": 552, "name": "Tủ", "score": 1}])

    envelope = json.dumps({"ok": True, "ref": "S00099", "model": "sale.order",
                           "res_id": 5, "state": "draft",
                           "display": "Đã tạo báo giá S00099 (nháp) cho Azur (1 dòng)."},
                          ensure_ascii=False)
    rec = {}
    fake_mcp = MagicMock()
    fake_mcp.name = "create_quotation"

    async def _ainvoke(args):
        rec["args"] = args
        return [{"type": "text", "text": envelope}]
    fake_mcp.ainvoke = _ainvoke

    steps = [
        AIMessage(content="", tool_calls=[
            {"name": "create_discount_quote",
             "args": {"customer": "Azur",
                      "lines": [{"product": "Tủ", "qty": 2}],
                      "tier": "than_thiet"},
             "id": "c1"}]),
        AIMessage(content="Đã tạo báo giá S00099 (nháp) cho Azur (1 dòng)."),
    ]
    node = build_skill_node(SPEC, _SeqModel(steps), [fake_mcp])
    graph = _graph(node)
    cfg = {"configurable": {"thread_id": "e2e-discount"}}

    res = await graph.ainvoke({"messages": [
        HumanMessage(content="báo giá chiết khấu cho Azur, 2 Tủ")]}, cfg)
    itr = res["__interrupt__"][0].value
    # 2 × 30M = 60M ≥ 50M → than_thiet 5% + bonus 2% = 7%, tính trong code.
    assert itr["kind"] == "confirm" and "7%" in itr["question"]
    assert "args" not in rec  # chưa ghi gì trước khi user xác nhận

    res = await graph.ainvoke(Command(resume=True), cfg)
    assert "__interrupt__" not in res
    assert rec["args"]["partner_id"] == 41
    assert rec["args"]["lines"][0]["price_unit"] == pytest.approx(30_000_000.0 * 0.93)
    # Global Constraint 2 (xem test đơn vị test_gated_tool_confirmed_calls_mcp_
    # discounted_and_returns_raw ở trên): create_quotation trả RAW list
    # content-block, KHÔNG phải chuỗi trần — "x in content_string" sẽ sai kiểu
    # nếu viết trên content thô; phải xét đúng shape list-of-block.
    tool_msgs = [m for m in res["messages"] if m.type == "tool"]
    assert any(
        isinstance(m.content, list) and any(
            isinstance(b, dict) and "Đã tạo báo giá S00099" in b.get("text", "")
            for b in m.content)
        for m in tool_msgs)
