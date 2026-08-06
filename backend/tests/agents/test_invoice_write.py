import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.invoice_write as iw
from src.agents import write_gate


def _fake_tool(name, recorder, ref="INV/2026/00030", res_id=105):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        recorder["args"] = args
        return json.dumps({"ok": True, "ref": ref, "model": "account.move",
                           "res_id": res_id, "state": "posted",
                           "display": "Đã phát hành."}, ensure_ascii=False)

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
            "pending_action": {"tool": tool, "args": args, "summary": "x"}}


_DRAFT = {"id": 105, "name": False, "partner_id": [41, "Acme Corporation"],
          "invoice_date": "2026-08-06", "amount_total": 17520.0,
          "amount_residual": 17520.0, "move_type": "in_invoice", "state": "draft"}
_LINE = {"product_id": [7, "[FURN_0789] Individual Workplace"],
         "quantity": 20.0, "price_subtotal": 17520.0}


def _detail(monkeypatch, inv=None, lines=None):
    monkeypatch.setattr(iw.accounting, "get_invoice_detail", lambda *a, **k: {
        "status": "success",
        "data": {"invoice": inv or _DRAFT, "lines": lines or [_LINE]},
        "display": "x"})


def _drafts(monkeypatch, rows):
    monkeypatch.setattr(iw.accounting, "find_draft_invoices", lambda *a, **k: {
        "status": "success", "data": {"rows": rows, "count": len(rows)},
        "display": "x"})


# ── render ──────────────────────────────────────────────────────────────────

def test_render_dung_ten_san_pham_khong_dung_line_name():
    """Đo thật: line['name'] chứa mô tả NHIỀU DÒNG
    ('[FURN_0789] Individual Workplace\\n[FURN_0...') — hiển thị nó sẽ vỡ
    bảng. Tên đúng nằm ở product_id[1]."""
    out = iw.render_invoice_summary("Đầu:", [_LINE], ["  Tổng: 17.520"])
    assert "[FURN_0789] Individual Workplace × 20 = 17.520" in out
    assert "\n[FURN_0" not in out


def test_render_luon_ket_bang_hang_so_xac_nhan():
    from src.agents.prompts import WRITE_CONFIRM_SUFFIX
    out = iw.render_invoice_summary("Đầu:", [_LINE], ["  Tổng: 1"])
    assert out.endswith(WRITE_CONFIRM_SUFFIX)


# ── post_invoice: đường chuỗi (đã có invoice_id) ────────────────────────────

@pytest.mark.asyncio
async def test_post_invoice_co_id_thi_hien_bang_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p1"}}
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "Acme Corporation" in itr["question"]
    assert "Individual Workplace × 20" in itr["question"]
    assert "17.520" in itr["question"]
    assert "args" not in rec           # chưa gọi tool trước khi xác nhận


@pytest.mark.asyncio
async def test_post_invoice_xac_nhan_thi_goi_tool_bang_invoice_id(monkeypatch):
    """Bất biến §5.1: LUÔN truyền invoice_id — nhánh đó của tool bỏ qua hoàn
    toàn phần resolve của chính nó, nên chỉ có ĐÚNG MỘT phép resolve."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p2"}}
    await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 105}
    assert res["last_write"]["tool"] == "post_invoice"


@pytest.mark.asyncio
async def test_post_invoice_tu_choi_thi_khong_goi_tool(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p3"}}
    await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "args" not in rec
    assert "hủy" in res["messages"][-1].content.lower()


# ── post_invoice: đường gọi trực tiếp (phải resolve) ────────────────────────

@pytest.mark.asyncio
async def test_post_invoice_nhieu_nhap_thi_hoi_chon_truoc(monkeypatch):
    """Ca thật: 5 bản nháp cùng 'Acme', 4 trùng số tiền. Phải hỏi chọn
    TRƯỚC cổng xác nhận, không để tool báo lỗi SAU khi đã xác nhận."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _drafts(monkeypatch, [_DRAFT, {**_DRAFT, "id": 99, "amount_total": 140.0}])
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p4"}}
    res = await graph.ainvoke(_state("post_invoice", {"partner_name": "Acme"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "disambiguation"
    assert len(itr["options"]) == 2
    res = await graph.ainvoke(Command(resume=99), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_post_invoice_mot_nhap_thi_di_thang_toi_xac_nhan(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _drafts(monkeypatch, [_DRAFT])
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p5"}}
    res = await graph.ainvoke(_state("post_invoice", {"partner_name": "Acme"}), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_post_invoice_thieu_ca_id_lan_ten_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {}),
                              {"configurable": {"thread_id": "p6"}})
    assert "__interrupt__" not in res
    assert "args" not in rec


@pytest.mark.asyncio
async def test_post_invoice_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}),
                              {"configurable": {"thread_id": "p7"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
