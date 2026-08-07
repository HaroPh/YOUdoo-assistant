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
    out = iw.render_invoice_summary("Đầu:", [_LINE], ["  Tổng: 17,520"])
    assert "[FURN_0789] Individual Workplace × 20 = 17,520" in out
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
    assert "17,520" in itr["question"]
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
async def test_post_invoice_tu_choi_hoa_don_da_phat_hanh(monkeypatch):
    """§Finding 1: nhánh invoice_id-only KHÔNG check state trước khi render
    tóm tắt — hóa đơn đã posted (vd chain-supplied) sẽ hiện như thể còn
    nháp, người dùng xác nhận rồi tool mới báo lỗi. Phải chặn TRƯỚC khi
    hiện bảng/hỏi xác nhận."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    posted = {**_DRAFT, "state": "posted", "name": "INV/2026/00099"}
    _detail(monkeypatch, inv=posted)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}),
                              {"configurable": {"thread_id": "p8"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
    assert "đã phát hành rồi" in res["messages"][-1].content


@pytest.mark.asyncio
async def test_post_invoice_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}),
                              {"configurable": {"thread_id": "p7"}})
    assert "__interrupt__" not in res
    assert "args" not in rec


# ── register_payment ────────────────────────────────────────────────────────

_POSTED = {"id": 100, "name": "INV/2026/00028",
           "partner_id": [41, "Acme Corporation"], "invoice_date": "2026-08-01",
           "amount_total": 350.0, "amount_residual": 350.0,
           "move_type": "out_invoice", "state": "posted"}
_CHAIR = {"product_id": [9, "[FURN_7777] Office Chair"],
          "quantity": 2.0, "price_subtotal": 140.0}


def _opens(monkeypatch, rows):
    monkeypatch.setattr(iw.accounting, "find_open_invoices", lambda *a, **k: {
        "status": "success", "data": {"rows": rows, "count": len(rows)},
        "display": "x"})


@pytest.mark.asyncio
async def test_register_payment_hien_so_du_khong_phai_tong(monkeypatch):
    """Tool LUÔN thanh toán đủ số dư còn lại, không trả một phần — nên số
    quyết định là amount_residual. Hiển thị amount_total sẽ SAI với hóa đơn
    đã trả một phần (payment_state='partial')."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    partial = {**_POSTED, "amount_total": 350.0, "amount_residual": 210.0}
    _detail(monkeypatch, inv=partial, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(_state("register_payment", {"invoice_id": 100}),
                              {"configurable": {"thread_id": "r1"}})
    q = res["__interrupt__"][0].value["question"]
    assert "INV/2026/00028" in q
    assert "Số dư sẽ thanh toán: 210" in q
    assert "Tổng hóa đơn: 350" in q


@pytest.mark.asyncio
async def test_register_payment_xac_nhan_thi_goi_bang_invoice_id(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r2"}}
    await graph.ainvoke(_state("register_payment", {"invoice_id": 100}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 100}
    assert res["last_write"]["tool"] == "register_payment"


@pytest.mark.asyncio
async def test_register_payment_giu_journal_neu_co(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r3"}}
    await graph.ainvoke(
        _state("register_payment", {"invoice_id": 100, "journal": "bank"}), cfg)
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 100, "journal": "bank"}


@pytest.mark.asyncio
async def test_register_payment_partner_name_mo_ho_thi_hoi_chon(monkeypatch):
    """register_payment nhận CẢ invoice_ref LẪN partner_name — đường
    partner_name mơ hồ y hệt post_invoice nên phải xử lý cùng cách."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _opens(monkeypatch, [_POSTED, {**_POSTED, "id": 96,
                                   "name": "INV/2026/00026"}])
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r4"}}
    res = await graph.ainvoke(
        _state("register_payment", {"partner_name": "Acme"}), cfg)
    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    assert "args" not in rec


@pytest.mark.asyncio
async def test_register_payment_tu_choi_hoan_tien(monkeypatch):
    """§Finding 1: register_payment (tool) chỉ chấp nhận
    move_type in (out_invoice, in_invoice) — kể cả ở nhánh invoice_id-only.
    Một credit memo posted/chưa đối soát (out_refund/in_refund) vẫn lọt
    qua find_open_invoices và sẽ render tóm tắt như thể thanh toán được,
    người dùng xác nhận rồi tool mới báo lỗi. Phải chặn TRƯỚC khi hiện
    bảng/hỏi xác nhận."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    refund = {**_POSTED, "id": 102, "name": "RINV/2026/00003",
              "move_type": "out_refund"}
    _detail(monkeypatch, inv=refund, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(_state("register_payment", {"invoice_id": 102}),
                              {"configurable": {"thread_id": "r6"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
    assert "credit memo" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_register_payment_nhan_disambig_hien_so_du_khong_phai_tong(monkeypatch):
    """§Finding 2: hai hóa đơn thanh toán một phần, CÙNG amount_total nhưng
    KHÁC amount_residual — nhãn disambig của register_payment phải phân
    biệt được bằng số dư (số tiền thực sự sẽ trả), không phải tổng hóa đơn
    (số không liên quan tới quyết định chọn)."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    row_a = {**_POSTED, "id": 100, "name": "INV/2026/00028",
             "amount_total": 500.0, "amount_residual": 210.0}
    row_b = {**_POSTED, "id": 101, "name": "INV/2026/00029",
             "amount_total": 500.0, "amount_residual": 90.0}
    _opens(monkeypatch, [row_a, row_b])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(
        _state("register_payment", {"partner_name": "Acme"}),
        {"configurable": {"thread_id": "r7"}})
    itr = res["__interrupt__"][0].value
    labels = [o["name"] for o in itr["options"]]
    assert labels[0] != labels[1]
    assert "210" in labels[0] and "90" in labels[1]
    assert "500" not in labels[0] and "500" not in labels[1]


@pytest.mark.asyncio
async def test_register_payment_thieu_moi_thu_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(_state("register_payment", {}),
                              {"configurable": {"thread_id": "r5"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
