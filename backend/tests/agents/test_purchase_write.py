import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from src.agents.state import ERPAgentState
import src.agents.purchase_write as pw
from src.agents import write_gate


def _fake_tool(name, recorder, env):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        recorder["args"] = args
        return json.dumps(env, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(node):
    g = StateGraph(ERPAgentState)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def _state(tool, args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": tool, "args": args, "summary": "Purchasing"}}


def _ok_resolve(matches, needs):
    return {"status": "success", "data": {"matches": matches,
            "needs_disambiguation": needs}, "display": "x"}


def _no_dups(*a, **k):
    return {"status": "success", "data": {"rows": []}, "display": "Không trùng."}


# ── create_vendor coordinator ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_vendor_happy(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_vendor_duplicates", _no_dups)
    rec = {}
    env = {"ok": True, "ref": "NCC Mới", "model": "res.partner", "res_id": 77,
           "state": None, "display": "Đã tạo nhà cung cấp 'NCC Mới'."}
    graph = _graph(pw.make_create_vendor_node([_fake_tool("create_vendor", rec, env)]))
    cfg = {"configurable": {"thread_id": "v1"}}
    res = await graph.ainvoke(_state("create_vendor",
                                     {"name": "NCC Mới", "email": "a@b.com"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "NCC Mới" in itr["question"] and "a@b.com" in itr["question"]
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["name"] == "NCC Mới"
    assert res["last_write"]["tool"] == "create_vendor"
    assert res["last_write"]["res_id"] == 77


@pytest.mark.asyncio
async def test_create_vendor_missing_name_asks(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_create_vendor_node([_fake_tool("create_vendor", rec, {})]))
    cfg = {"configurable": {"thread_id": "v2"}}
    res = await graph.ainvoke(_state("create_vendor", {}), cfg)
    assert "tên nhà cung cấp" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_create_vendor_dup_warning_shown_not_blocking(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_vendor_duplicates",
                        lambda *a, **k: {"status": "success",
                                         "data": {"rows": [{"name": "NCC Cũ"}]},
                                         "display": "1 NCC trùng."})
    rec = {}
    env = {"ok": True, "ref": "NCC Mới", "model": "res.partner", "res_id": 77,
           "state": None, "display": "OK."}
    graph = _graph(pw.make_create_vendor_node([_fake_tool("create_vendor", rec, env)]))
    cfg = {"configurable": {"thread_id": "v3"}}
    res = await graph.ainvoke(_state("create_vendor", {"name": "NCC Mới"}), cfg)
    itr = res["__interrupt__"][0].value
    assert "⚠" in itr["question"] and "NCC Cũ" in itr["question"]
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["name"] == "NCC Mới"


@pytest.mark.asyncio
async def test_create_vendor_cancel(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_vendor_duplicates", _no_dups)
    rec = {}
    graph = _graph(pw.make_create_vendor_node([_fake_tool("create_vendor", rec, {})]))
    cfg = {"configurable": {"thread_id": "v4"}}
    await graph.ainvoke(_state("create_vendor", {"name": "X"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "hủy" in res["messages"][-1].content.lower()
    assert rec == {}


# ── update_vendor_pricing coordinator ────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_vendor_pricing_happy_with_id(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda *a, **k: _ok_resolve(
        [{"id": 10, "name": "NCC A", "score": 1}], False))
    monkeypatch.setattr(pw.inventory, "find_product", lambda *a, **k: _ok_resolve(
        [{"id": 60, "name": "Screw", "score": 1}], False))
    rec = {}
    env = {"ok": True, "ref": "NCC A", "model": "product.supplierinfo", "res_id": 501,
           "state": None, "display": "OK."}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, env)]))
    cfg = {"configurable": {"thread_id": "p1"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw",
                                      "price": 12000}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "Screw" in itr["question"] and "NCC A" in itr["question"]
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"partner_id": 10, "product_id": 60, "price": 12000.0}
    assert res["last_write"]["tool"] == "update_vendor_pricing"


@pytest.mark.asyncio
async def test_update_vendor_pricing_missing_price_asks(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, {})]))
    cfg = {"configurable": {"thread_id": "p2"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw"}), cfg)
    assert "đơn giá" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_update_vendor_pricing_invalid_min_qty_asks_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, {})]))
    cfg = {"configurable": {"thread_id": "p2b"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw",
                                      "price": 12000, "min_qty": "năm cái"}), cfg)
    assert "Số lượng tối thiểu không hợp lệ" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_update_vendor_pricing_invalid_delay_asks_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, {})]))
    cfg = {"configurable": {"thread_id": "p2c"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw",
                                      "price": 12000, "delay": "vài ngày"}), cfg)
    assert "Thời gian giao hàng không hợp lệ" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_update_vendor_pricing_includes_min_qty_delay_when_given(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda *a, **k: _ok_resolve(
        [{"id": 10, "name": "NCC A", "score": 1}], False))
    monkeypatch.setattr(pw.inventory, "find_product", lambda *a, **k: _ok_resolve(
        [{"id": 60, "name": "Screw", "score": 1}], False))
    rec = {}
    env = {"ok": True, "ref": "NCC A", "model": "product.supplierinfo", "res_id": 501,
           "state": None, "display": "OK."}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, env)]))
    cfg = {"configurable": {"thread_id": "p3"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw",
                                      "price": 12000, "min_qty": 5, "delay": 7}), cfg)
    itr = res["__interrupt__"][0].value
    assert "tối thiểu 5" in itr["question"] and "7 ngày" in itr["question"]
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"partner_id": 10, "product_id": 60, "price": 12000.0,
                           "min_qty": 5.0, "delay": 7}


@pytest.mark.asyncio
async def test_update_vendor_pricing_vendor_ambiguous_disambiguates(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda *a, **k: _ok_resolve(
        [{"id": 10, "name": "NCC A", "score": 1}, {"id": 11, "name": "NCC A2", "score": 1}],
        True))
    monkeypatch.setattr(pw.inventory, "find_product", lambda *a, **k: _ok_resolve(
        [{"id": 60, "name": "Screw", "score": 1}], False))
    rec = {}
    env = {"ok": True, "ref": "NCC A", "model": "product.supplierinfo", "res_id": 501,
           "state": None, "display": "OK."}
    graph = _graph(pw.make_update_vendor_pricing_node(
        [_fake_tool("update_vendor_pricing", rec, env)]))
    cfg = {"configurable": {"thread_id": "p4"}}
    res = await graph.ainvoke(_state("update_vendor_pricing",
                                     {"vendor_name": "NCC A", "product": "Screw",
                                      "price": 12000}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "disambiguation"
    res = await graph.ainvoke(Command(resume=11), cfg)
    itr2 = res["__interrupt__"][0].value
    assert itr2["kind"] == "confirm"
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["partner_id"] == 11


# ── create_bulk_rfq coordinator ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_bulk_rfq_happy(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda ref, **k: _ok_resolve(
        [{"id": 10 if ref == "NCC A" else 20, "name": ref, "score": 1}], False))
    monkeypatch.setattr(pw.inventory, "find_product", lambda *a, **k: _ok_resolve(
        [{"id": 60, "name": "Screw", "score": 1}], False))
    rec = {}
    env = {"ok": True, "ref": None, "model": "purchase.order", "res_id": None,
           "state": None, "display": "Đã tạo 2 RFQ nháp: P00010 (NCC A), P00011 (NCC B)."}
    graph = _graph(pw.make_create_bulk_rfq_node(
        [_fake_tool("create_bulk_rfq", rec, env)]))
    cfg = {"configurable": {"thread_id": "b1"}}
    res = await graph.ainvoke(_state("create_bulk_rfq",
                                     {"vendor_names": ["NCC A", "NCC B"],
                                      "lines": [{"product": "Screw", "qty": 3}]}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "NCC A" in itr["question"] and "NCC B" in itr["question"]
    assert "Screw" in itr["question"]
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["partner_ids"] == [10, 20]
    assert rec["args"]["lines"] == [{"product_id": 60, "qty": 3}]


@pytest.mark.asyncio
async def test_create_bulk_rfq_too_many_vendors_asks(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_create_bulk_rfq_node([_fake_tool("create_bulk_rfq", rec, {})]))
    cfg = {"configurable": {"thread_id": "b2"}}
    res = await graph.ainvoke(_state("create_bulk_rfq",
                                     {"vendor_names": [f"NCC {i}" for i in range(11)],
                                      "lines": [{"product": "Screw", "qty": 1}]}), cfg)
    assert "Tối đa 10" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_create_bulk_rfq_missing_lines_asks(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(pw.make_create_bulk_rfq_node([_fake_tool("create_bulk_rfq", rec, {})]))
    cfg = {"configurable": {"thread_id": "b3"}}
    res = await graph.ainvoke(_state("create_bulk_rfq",
                                     {"vendor_names": ["NCC A"], "lines": []}), cfg)
    assert "sản phẩm" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_create_bulk_rfq_vendor_not_found_stops(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda *a, **k: _ok_resolve([], False))
    rec = {}
    graph = _graph(pw.make_create_bulk_rfq_node([_fake_tool("create_bulk_rfq", rec, {})]))
    cfg = {"configurable": {"thread_id": "b4"}}
    res = await graph.ainvoke(_state("create_bulk_rfq",
                                     {"vendor_names": ["NCC lạ"],
                                      "lines": [{"product": "Screw", "qty": 1}]}), cfg)
    assert "Không tìm thấy nhà cung cấp" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_create_bulk_rfq_cancel(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(pw.purchase, "find_supplier", lambda *a, **k: _ok_resolve(
        [{"id": 10, "name": "NCC A", "score": 1}], False))
    monkeypatch.setattr(pw.inventory, "find_product", lambda *a, **k: _ok_resolve(
        [{"id": 60, "name": "Screw", "score": 1}], False))
    rec = {}
    graph = _graph(pw.make_create_bulk_rfq_node([_fake_tool("create_bulk_rfq", rec, {})]))
    cfg = {"configurable": {"thread_id": "b5"}}
    await graph.ainvoke(_state("create_bulk_rfq",
                               {"vendor_names": ["NCC A"],
                                "lines": [{"product": "Screw", "qty": 1}]}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "hủy" in res["messages"][-1].content.lower()
    assert rec == {}
