# backend/tests/agents/test_auto_chain.py
"""Auto-chain multi-step planner: expand_chain, planner chain_until,
continuation queue, chain_note in coordinator confirms."""
import pytest

from src.agents.write_registry import expand_chain
from src.agents import write_gate
from src.agents.prompts import WRITE_CONFIRM_SUFFIX


# ── expand_chain (total function) ────────────────────────────────────────────

def test_expand_one_step_sale():
    assert expand_chain("create_quotation", "confirm_sale_order") == \
        [("confirm_sale_order", "Xác nhận báo giá")]


def test_expand_full_sale_chain_to_invoice():
    steps = expand_chain("create_quotation", "post_invoice")
    assert [t for t, _ in steps] == ["confirm_sale_order", "deliver_order",
                                     "create_invoice_from_order", "post_invoice"]


def test_expand_purchase_chain():
    steps = expand_chain("create_rfq", "receive_order")
    assert [t for t, _ in steps] == ["confirm_purchase_order", "receive_order"]


def test_expand_edit_chain():
    assert expand_chain("update_quotation_lines", "confirm_sale_order") == \
        [("confirm_sale_order", "Xác nhận báo giá")]


def test_expand_missing_or_same_returns_none():
    assert expand_chain("create_quotation", None) is None
    assert expand_chain("create_quotation", "") is None
    assert expand_chain("create_quotation", "create_quotation") is None


def test_expand_unknown_or_unreachable_returns_none():
    assert expand_chain("create_quotation", "frobnicate") is None
    assert expand_chain("inventory_adjustment", "confirm_sale_order") is None
    # backwards: deliver comes AFTER confirm, can't walk back
    assert expand_chain("deliver_order", "confirm_sale_order") is None
    # cross-chain: sale start can't reach purchase tool
    assert expand_chain("create_quotation", "receive_order") is None


def test_expand_total_on_garbage():
    for a, b in [(None, None), (123, "x"), ("create_quotation", 123),
                 ({}, []), (None, "confirm_sale_order"),
                 ({}, "confirm_sale_order"), ([1, 2], "confirm_sale_order"),
                 (123, "confirm_sale_order")]:
        assert expand_chain(a, b) is None


# ── planner: chain_until → auto_chain + chain_note ───────────────────────────
import json
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage

from src.agents.state import ERPAgentState
from tests.conftest import make_mock_llm
import src.agents.nodes as nodes_mod
from src.agents.nodes import make_erp_write_planner_node


def _pstate(text):
    return ERPAgentState(messages=[HumanMessage(content=text)],
                         intent="erp_write", pending_action=None, confirmed=None)


def _mk_llm(payload):
    return make_mock_llm(json.dumps(payload, ensure_ascii=False))


@pytest.mark.asyncio
async def test_planner_valid_chain_sets_auto_chain_and_note(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    llm = _mk_llm({"tool": "create_quotation",
                   "args": {"partner_name": "Azur",
                            "lines": [{"product": "Tủ", "qty": 2}]},
                   "summary": "Tạo báo giá và xác nhận",
                   "chain_until": "confirm_sale_order"})
    out = await make_erp_write_planner_node(llm)(
        _pstate("tạo báo giá cho Azur, 2 Tủ rồi xác nhận luôn"))
    assert out["auto_chain"] == ["confirm_sale_order"]
    assert out["pending_action"]["chain_note"] == \
        "\n\nSau đó tự động: Xác nhận báo giá"


@pytest.mark.asyncio
async def test_planner_bogus_chain_falls_back_single_step(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    llm = _mk_llm({"tool": "create_quotation",
                   "args": {"partner_name": "Azur", "lines": []},
                   "summary": "Tạo báo giá", "chain_until": "frobnicate"})
    out = await make_erp_write_planner_node(llm)(_pstate("tạo báo giá"))
    assert out["auto_chain"] is None
    assert "chain_note" not in out["pending_action"]


@pytest.mark.asyncio
async def test_planner_noncoordinated_chain_note_in_confirm(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    captured = {}
    monkeypatch.setattr(nodes_mod, "_interrupt",
                        lambda p: captured.update(p) or True)
    llm = _mk_llm({"tool": "confirm_sale_order", "args": {"order_ref": "S00012"},
                   "summary": "Xác nhận S00012", "chain_until": "deliver_order"})
    out = await make_erp_write_planner_node(llm)(
        _pstate("xác nhận S00012 rồi giao hàng luôn"))
    assert "Sau đó tự động: Giao hàng" in captured["question"]
    assert out["auto_chain"] == ["deliver_order"]
    assert out["confirmed"] is True


@pytest.mark.asyncio
async def test_planner_gate_return_has_auto_chain_key(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    out = await make_erp_write_planner_node(MagicMock())(_pstate("x"))
    assert "auto_chain" in out and out["auto_chain"] is None


@pytest.mark.asyncio
async def test_planner_non_json_return_has_auto_chain_key(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    out = await make_erp_write_planner_node(make_mock_llm("not json"))(_pstate("x"))
    assert "auto_chain" in out and out["auto_chain"] is None


# ── continuation: queue consumption ──────────────────────────────────────────
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from src.agents.continuation import make_write_continuation_node


def _cgraph():
    g = StateGraph(ERPAgentState)
    g.add_node("write_continuation", make_write_continuation_node())
    g.set_entry_point("write_continuation")
    g.add_edge("write_continuation", END)
    return g.compile(checkpointer=MemorySaver())


def _lw(tool="create_quotation", ok=True, ref="S00031", res_id=42):
    return {"tool": tool, "ok": ok, "ref": ref, "model": "sale.order",
            "res_id": res_id, "state": "draft",
            "display": "Đã tạo báo giá S00031 (nháp) cho Azure."}


def _cstate(lw, queue):
    return {"messages": [], "intent": "erp_write", "confirmed": True,
            "pending_action": {"tool": "x"}, "last_write": lw,
            "auto_chain": queue}


@pytest.mark.asyncio
async def test_auto_proceed_no_interrupt():
    res = await _cgraph().ainvoke(_cstate(_lw(), ["confirm_sale_order"]),
                                  {"configurable": {"thread_id": "a1"}})
    assert "__interrupt__" not in res
    assert res["pending_action"] == {"tool": "confirm_sale_order",
                                     "args": {"order_ref": "S00031"},
                                     "summary": "Xác nhận báo giá"}
    assert res["confirmed"] is True
    assert res["last_write"] is None
    assert res["auto_chain"] is None          # queue exhausted


@pytest.mark.asyncio
async def test_auto_proceed_keeps_rest_of_queue():
    res = await _cgraph().ainvoke(
        _cstate(_lw(), ["confirm_sale_order", "deliver_order"]),
        {"configurable": {"thread_id": "a2"}})
    assert "__interrupt__" not in res
    assert res["auto_chain"] == ["deliver_order"]


@pytest.mark.asyncio
async def test_head_mismatch_falls_back_to_suggestion():
    graph, cfg = _cgraph(), {"configurable": {"thread_id": "a3"}}
    res = await graph.ainvoke(_cstate(_lw(), ["deliver_order"]), cfg)
    assert "__interrupt__" not in res         # suggestion, NOT auto-run of wrong step
    assert res["auto_chain"] is None
    assert "Xác nhận báo giá" in res["messages"][-1].content


@pytest.mark.asyncio
async def test_failed_write_with_queue_warns_and_clears():
    res = await _cgraph().ainvoke(_cstate(_lw(ok=False), ["confirm_sale_order"]),
                                  {"configurable": {"thread_id": "a4"}})
    assert "__interrupt__" not in res
    content = res["messages"][-1].content
    assert "Đã tạo báo giá S00031" in content   # lw['display'] must survive
    assert "Chuỗi tự động dừng" in content
    assert res["auto_chain"] is None and res["last_write"] is None


@pytest.mark.asyncio
async def test_offchain_tool_with_queue_warns():
    # vd nhánh flag của edit: write chạy OK nhưng tool không có NEXT_STEPS entry
    lw = _lw(tool="flag_order_for_review", ok=True)
    res = await _cgraph().ainvoke(_cstate(lw, ["confirm_sale_order"]),
                                  {"configurable": {"thread_id": "a5"}})
    content = res["messages"][-1].content
    assert lw["display"] in content            # real flag-note result survives
    assert "Chuỗi tự động dừng" in content
    assert res["auto_chain"] is None


@pytest.mark.asyncio
async def test_cancel_with_queue_is_silent():
    # lw falsy = user đã hủy ở draft confirm — không write nào chạy → im lặng
    res = await _cgraph().ainvoke(_cstate(None, ["confirm_sale_order"]),
                                  {"configurable": {"thread_id": "a6"}})
    assert res["messages"] == []
    assert res["auto_chain"] is None


@pytest.mark.asyncio
async def test_every_branch_writes_auto_chain_key_direct_call():
    node = make_write_continuation_node()
    out = await node({"messages": [], "last_write": None, "auto_chain": None})
    assert "auto_chain" in out and out["auto_chain"] is None


# ── chain_note in coordinator confirms ───────────────────────────────────────
from unittest.mock import MagicMock
import src.agents.create_order as co
import src.agents.edit_order as eo
from src.agents.create_order import render_draft
from src.agents.edit_order import _render_diff

NOTE = "\n\nSau đó tự động: Xác nhận báo giá"


def test_render_draft_note_before_question():
    out = render_draft({"name": "Azur"},
                       [{"name": "Tủ", "qty": 2, "unit_price": 5.0, "subtotal": 10.0}],
                       10.0, note=NOTE)
    assert "Sau đó tự động: Xác nhận báo giá" in out
    assert out.index("Sau đó tự động") < out.index(WRITE_CONFIRM_SUFFIX)


def test_render_draft_purchase_variant_note():
    out = render_draft({"name": "ACME"}, [{"name": "Tủ", "qty": 2}], None,
                       head="Đơn mua từ", note=NOTE)
    assert out.index("Sau đó tự động") < out.index(WRITE_CONFIRM_SUFFIX)


def test_render_draft_no_note_unchanged():
    out = render_draft({"name": "Azur"},
                       [{"name": "Tủ", "qty": 2, "unit_price": 5.0, "subtotal": 10.0}],
                       10.0)
    assert "Sau đó tự động" not in out


def test_render_diff_note_before_question():
    out = _render_diff(eo.SALE_EDIT_CFG, "S00040", "Azur",
                       ["Tủ × 2 = 10"], [], [], NOTE)
    assert out.index("Sau đó tự động") < out.index(WRITE_CONFIRM_SUFFIX)


def _ok_env(matches, needs=False):
    return {"status": "success", "display": "x",
            "data": {"matches": matches, "needs_disambiguation": needs}}


@pytest.mark.asyncio
async def test_create_order_confirm_shows_chain_note(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(co.sales, "find_customer",
                        lambda *a, **k: _ok_env([{"id": 41, "name": "Azur", "score": 1}]))
    monkeypatch.setattr(co.inventory, "find_product",
                        lambda *a, **k: _ok_env([{"id": 552, "name": "Tủ", "score": 1}]))
    monkeypatch.setattr(co.sales, "get_product_price",
                        lambda *a, **k: {"status": "success",
                                         "data": {"price": 100000.0}, "display": "x"})
    g = StateGraph(ERPAgentState)
    g.add_node("create_order", co.make_create_order_node(MagicMock(), []))
    g.set_entry_point("create_order")
    g.add_edge("create_order", END)
    graph = g.compile(checkpointer=MemorySaver())
    state = {"messages": [], "intent": "erp_write", "confirmed": None,
             "pending_action": {"tool": "create_quotation",
                                "args": {"partner_name": "Azur",
                                         "lines": [{"product": "Tủ", "qty": 2}]},
                                "chain_note": NOTE}}
    res = await graph.ainvoke(state, {"configurable": {"thread_id": "n1"}})
    q = res["__interrupt__"][0].value["question"]
    assert "Sau đó tự động: Xác nhận báo giá" in q
    assert q.index("Sau đó tự động") < q.index(WRITE_CONFIRM_SUFFIX)


# ── integration: create → (auto) confirm qua graph write thật ────────────────
from src.agents.nodes import make_erp_write_executor_node
from src.agents.graph import (_route_after_write_planner,
                                      _route_after_continuation)
from src.agents.write_registry import WRITE_COORDINATORS, CONFIRM_IN_CHAIN
from src.agents.mail_write import (MAIL_COORDINATOR_CFGS, make_send_template_email_node,
                                    make_route_after_mail_preview)


def _env_tool(name, ref, state_val, display, rec):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        rec.append((name, args))
        return json.dumps({"ok": True, "ref": ref, "model": "sale.order",
                           "res_id": 99, "state": state_val, "display": display},
                          ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _write_graph(llm, tools):
    # Mirror graph.py's write_continuation wiring EXACTLY (same construction,
    # not just same result) — Task 4 fix round 1, Finding 2: this helper had
    # drifted to the old 2-target map while production moved to a
    # CONFIRM_IN_CHAIN-extended one, so any future test using this helper to
    # exercise a money-touching chain step would have silently tested nothing
    # real (or hit the same KeyError production would hit if graph.py regressed).
    #
    # Drifted AGAIN — review round 2, Finding 3 (2026-08-07, order-confirmation-
    # email task): send_order_confirmation_email became a 2-node coordinator
    # (preview → interrupt+send) and graph.py grew a hand-wired skip +
    # conditional edge for it (see build_graph in graph.py). This helper is
    # copy-mirrored by hand from graph.py, same as the rest of its wiring —
    # NOT factored into a shared function, to keep this fix low-risk/scoped;
    # if it drifts a third time, that's the signal to actually share the code.
    g = StateGraph(ERPAgentState)
    g.add_node("erp_write_planner", make_erp_write_planner_node(llm))
    g.add_node("erp_write_executor", make_erp_write_executor_node(tools))
    for spec in WRITE_COORDINATORS.values():
        g.add_node(spec.node, spec.build(llm, tools))
    g.add_node("write_continuation", make_write_continuation_node())
    g.set_entry_point("erp_write_planner")
    targets = {END: END, "erp_write_executor": "erp_write_executor"}
    targets.update({s.node: s.node for s in WRITE_COORDINATORS.values()})
    g.add_conditional_edges("erp_write_planner", _route_after_write_planner, targets)
    g.add_edge("erp_write_executor", "write_continuation")
    mail_preview_nodes = {cfg.preview_node for cfg in MAIL_COORDINATOR_CFGS}
    for s in WRITE_COORDINATORS.values():
        if s.node in mail_preview_nodes:
            continue  # coordinator 2 node, nối tay ngay dưới — mirror graph.py
        g.add_edge(s.node, "write_continuation")

    # Mỗi coordinator gửi mail là 2 node. Node 1 (preview) đã add ở vòng lặp
    # add_node phía trên. Node 2 (gửi) KHÔNG nằm trong WRITE_COORDINATORS —
    # add tay, khớp đúng graph.py.
    for cfg in MAIL_COORDINATOR_CFGS:
        g.add_node(cfg.send_node, make_send_template_email_node(tools, cfg))
        g.add_conditional_edges(
            cfg.preview_node, make_route_after_mail_preview(cfg),
            {cfg.send_node: cfg.send_node,
             "write_continuation": "write_continuation"})
        g.add_edge(cfg.send_node, "write_continuation")

    cont_targets = {"erp_write_executor": "erp_write_executor", END: END}
    cont_targets.update({WRITE_COORDINATORS[t].node: WRITE_COORDINATORS[t].node
                         for t in CONFIRM_IN_CHAIN})
    g.add_conditional_edges("write_continuation", _route_after_continuation,
                            cont_targets)
    return g.compile(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_two_step_chain_one_confirm_end_to_end(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(co.sales, "find_customer",
                        lambda *a, **k: _ok_env([{"id": 41, "name": "Azur", "score": 1}]))
    monkeypatch.setattr(co.inventory, "find_product",
                        lambda *a, **k: _ok_env([{"id": 552, "name": "Tủ", "score": 1}]))
    monkeypatch.setattr(co.sales, "get_product_price",
                        lambda *a, **k: {"status": "success",
                                         "data": {"price": 100000.0}, "display": "x"})
    rec = []
    tools = [
        _env_tool("create_quotation", "S00099", "draft",
                  "Đã tạo báo giá S00099 (nháp) cho Azur (1 dòng).", rec),
        _env_tool("confirm_sale_order", "S00099", "sale",
                  "Đã xác nhận đơn S00099.", rec),
    ]
    llm = _mk_llm({"tool": "create_quotation",
                   "args": {"partner_name": "Azur",
                            "lines": [{"product": "Tủ", "qty": 2}]},
                   "summary": "Tạo báo giá và xác nhận",
                   "chain_until": "confirm_sale_order"})
    graph = _write_graph(llm, tools)
    cfg = {"configurable": {"thread_id": "e2e-1"}}

    # Turn 1: draft confirm hiện chain_note — interrupt DUY NHẤT trước khi chạy
    res = await graph.ainvoke(
        {"messages": [HumanMessage(content="tạo báo giá cho Azur, 2 Tủ rồi xác nhận luôn")],
         "intent": "erp_write", "pending_action": None, "confirmed": None}, cfg)
    q = res["__interrupt__"][0].value["question"]
    assert "Sau đó tự động: Xác nhận báo giá" in q
    assert rec == []                                  # chưa write gì

    # Resume "có": create chạy → continuation auto-proceed (KHÔNG interrupt)
    # → executor confirm chạy → continuation: queue hết → suggestion bước kế (Giao hàng)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert [n for n, _ in rec] == ["create_quotation", "confirm_sale_order"]
    assert rec[1][1] == {"order_ref": "S00099"}       # args từ registry lambda
    assert "__interrupt__" not in res                 # no interrupt, suggestion instead
    assert "Giao hàng" in res["messages"][-1].content  # suggestion chỉ hiện SAU chuỗi
    assert res["auto_chain"] is None


def test_expand_full_sale_chain_to_register_payment():
    steps = expand_chain("create_quotation", "register_payment")
    assert [t for t, _ in steps] == ["confirm_sale_order", "deliver_order",
                                     "create_invoice_from_order", "post_invoice",
                                     "register_payment"]


def test_post_invoice_next_step_is_register_payment():
    from src.agents.write_registry import NEXT_STEPS
    step = NEXT_STEPS["post_invoice"]
    assert step.tool == "register_payment"
    assert step.args({"res_id": 64}) == {"invoice_id": 64}


def test_expand_create_lead_chain():
    steps = expand_chain("create_lead", "convert_lead")
    assert steps == [("convert_lead", "Chuyển thành cơ hội")]


def test_create_lead_next_step_args_lambda():
    from src.agents.write_registry import NEXT_STEPS
    step = NEXT_STEPS["create_lead"]
    assert step.tool == "convert_lead"
    assert step.args({"res_id": 45}) == {"lead_id": 45}


# ── CONFIRM_IN_CHAIN: money-touching chain steps must not auto-run ──────────
from src.agents.write_registry import CONFIRM_IN_CHAIN, WRITE_COORDINATORS
from src.agents.continuation import _route_after_continuation


def test_confirm_in_chain_la_tap_tuong_minh_chi_6_tool_dung_tien():
    """PHẢI tường minh, KHÔNG được viết thành `in COORDINATED_TOOLS`:
    convert_lead và update_vendor_pricing cũng vừa coordinated vừa là bước
    trong NEXT_STEPS — điều kiện rộng sẽ đổi luôn hành vi của chúng, ngoài
    phạm vi spec 2026-08-06 §3.3. send_order_confirmation_email thêm vào
    spec 2026-08-07 §3 (task 3): cũng là hành động "đụng" tới thực tế bên
    ngoài (gửi mail thật) nên phải dừng hỏi lại kèm bản tóm tắt, không
    auto-run trong chuỗi. Task 2 (2026-08-08) mở rộng thêm 3 coordinator gửi
    mail nữa: send_quotation_email, send_rfq_email, send_invoice_email."""
    assert CONFIRM_IN_CHAIN == frozenset({"post_invoice", "register_payment",
                                          "send_order_confirmation_email",
                                          "send_quotation_email", "send_rfq_email",
                                          "send_invoice_email"})


def test_moi_tool_trong_confirm_in_chain_deu_co_coordinator():
    """Nếu thiếu, _route_after_continuation sẽ trả về node không tồn tại và
    LangGraph ném lỗi định tuyến giữa một lượt chat thật."""
    for tool in CONFIRM_IN_CHAIN:
        assert tool in WRITE_COORDINATORS


@pytest.mark.asyncio
async def test_buoc_dung_tien_trong_chuoi_KHONG_auto_run():
    """Đảo hành vi có chủ đích (spec §4): lúc khai báo chuỗi, hóa đơn CHƯA
    tồn tại — user đồng ý với HÀNH ĐỘNG, không thể đồng ý với SỐ TIỀN."""
    lw = {"tool": "create_invoice_from_order", "ok": True, "ref": "INV/2026/00030",
          "model": "account.move", "res_id": 105, "state": "draft",
          "display": "Đã tạo hóa đơn nháp."}
    res = await _cgraph().ainvoke(_cstate(lw, ["post_invoice"]),
                                  {"configurable": {"thread_id": "c1"}})
    assert res["pending_action"]["tool"] == "post_invoice"
    assert res["confirmed"] is None          # coordinator sẽ tự interrupt
    assert res["auto_chain"] is None         # queue đã tiêu thụ bước này


def test_route_after_continuation_tro_vao_coordinator():
    state = {"pending_action": {"tool": "post_invoice"}, "confirmed": None}
    assert _route_after_continuation(state) == WRITE_COORDINATORS["post_invoice"].node


def test_route_after_continuation_giu_nguyen_duong_executor():
    """Chống hồi quy: bước KHÔNG đụng tiền vẫn đi thẳng executor như cũ."""
    state = {"pending_action": {"tool": "confirm_sale_order"}, "confirmed": True}
    assert _route_after_continuation(state) == "erp_write_executor"


# ── end-to-end: chuỗi đụng tiền qua ĐỒ THỊ THẬT (Task 4 fix round 1,
# Finding 3) ─────────────────────────────────────────────────────────────────
# test_buoc_dung_tien_trong_chuoi_KHONG_auto_run (trên) chỉ chạy qua _cgraph()
# — write_continuation -> END, KHÔNG có conditional edge nào cả — nên câu
# "coordinator sẽ tự interrupt" trong docstring của nó chưa từng được ai kiểm
# chứng. Test này lái NGUYÊN chuỗi create_invoice_from_order -> post_invoice
# qua _write_graph() (mirror graph.py thật, xem Finding 2) và xác nhận: (1)
# CHUỖI TỰ ĐỘNG dừng đúng chỗ — một interrupt THỨ HAI (money gate) nổi lên
# thay vì auto-run, mang theo bảng dòng hàng; (2) sau khi resume lần hai, tool
# post_invoice thật sự được gọi ĐÚNG MỘT LẦN với invoice_id đã resolve từ chuỗi
# (105, không phải giá trị nào khác) — không phải giả định suông.
import src.agents.invoice_write as iw


def _fake_invoice_tool(name, rec, ref, res_id, state_val, display):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        rec.append((name, args))
        return json.dumps({"ok": True, "ref": ref, "model": "account.move",
                           "res_id": res_id, "state": state_val, "display": display},
                          ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


@pytest.mark.asyncio
async def test_chuoi_dung_tien_dung_lai_hoi_lai_qua_do_thi_that(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(iw.accounting, "get_invoice_detail", lambda *a, **k: {
        "status": "success",
        "data": {"invoice": {"partner_id": [41, "Azur"],
                             "invoice_date": "2026-08-07",
                             "amount_total": 100000.0,
                             "state": "draft"},
                 "lines": [{"product_id": [552, "Tủ"], "quantity": 2.0,
                           "price_subtotal": 100000.0}]},
        "display": "x"})

    rec = []
    tools = [
        _fake_invoice_tool("create_invoice_from_order", rec, "INV/2026/00030",
                           105, "draft", "Đã tạo hóa đơn nháp cho Azur."),
        _fake_invoice_tool("post_invoice", rec, "INV/2026/00030",
                           105, "posted", "Đã phát hành hóa đơn."),
    ]
    llm = _mk_llm({"tool": "create_invoice_from_order",
                   "args": {"order_ref": "S00099"},
                   "summary": "Tạo hóa đơn và phát hành",
                   "chain_until": "post_invoice"})
    graph = _write_graph(llm, tools)
    cfg = {"configurable": {"thread_id": "money-1"}}

    # Turn 1: draft confirm (chain_note) — chưa write gì.
    res = await graph.ainvoke(
        {"messages": [HumanMessage(content="tạo hóa đơn cho đơn S00099 rồi phát hành luôn")],
         "intent": "erp_write", "pending_action": None, "confirmed": None}, cfg)
    assert "Sau đó tự động: Phát hành hóa đơn" in res["__interrupt__"][0].value["question"]
    assert rec == []

    # Resume "có": create_invoice_from_order chạy → write_continuation thấy
    # bước kế (post_invoice) thuộc CONFIRM_IN_CHAIN → KHÔNG auto-run, route
    # sang coordinator post_invoice → coordinator tự đọc hóa đơn, hiện bảng
    # dòng hàng, và tự interrupt LẦN HAI. Đây chính là hành vi cần chứng minh.
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert [n for n, _ in rec] == ["create_invoice_from_order"]   # post_invoice CHƯA chạy
    assert "__interrupt__" in res
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "Tủ × 2" in itr["question"]        # bảng dòng hàng thật, không phải "(post_invoice: ...)"
    assert "100,000" in itr["question"]

    # Resume lần hai (money gate): post_invoice thật sự chạy, ĐÚNG MỘT LẦN,
    # với invoice_id đã resolve từ chuỗi (105) — không phải args nào khác.
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert [n for n, _ in rec] == ["create_invoice_from_order", "post_invoice"]
    assert rec[1] == ("post_invoice", {"invoice_id": 105})
    assert "__interrupt__" not in res
    assert "Ghi nhận thanh toán" in res["messages"][-1].content  # suggestion sau chuỗi
    assert res["auto_chain"] is None
