import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.mail_write as mw
from src.agents import write_gate


def _fake_tool(name, recorder, response):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        recorder["args"] = args
        return json.dumps(response, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(node):
    g = StateGraph(ERPAgentState)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def _state(args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": "send_order_confirmation_email",
                               "args": args, "summary": "x"}}


_PREVIEW_OK = {"ok": True, "display": "Đã soạn mail 'Order Confirmation', chờ xác nhận gửi.",
              "mail_id": 60, "subject": "Order Confirmation (Ref S00166)",
              "recipient_count": 1}
_SEND_OK = {"ok": True, "display": "Đã gửi mail.", "ref": "Order Confirmation (Ref S00166)",
           "model": "mail.mail", "res_id": 60, "state": "sent"}


@pytest.mark.asyncio
async def test_co_order_ref_thi_hien_preview_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m1"}}
    res = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "S00166" in itr["question"]
    assert "1 người nhận" in itr["question"]
    assert preview_rec["args"] == {"template_name": "Sales: Order Confirmation",
                                   "res_model": "sale.order", "ref": "S00166"}
    assert "args" not in send_rec           # chưa gửi trước khi xác nhận


@pytest.mark.asyncio
async def test_xac_nhan_thi_goi_send_bang_dung_mail_id(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m2"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert send_rec["args"] == {"mail_id": 60}
    assert res["last_write"]["tool"] == "send_order_confirmation_email"
    assert res["last_write"]["state"] == "sent"


@pytest.mark.asyncio
async def test_tu_choi_thi_khong_goi_send(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m3"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "args" not in send_rec
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_tim_thay_don_thi_bao_loi_khong_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec,
                              {"ok": False, "display": "Không tìm thấy bản ghi 'S99999' trong sale.order."})
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({"order_ref": "S99999"}),
                              {"configurable": {"thread_id": "m4"}})
    assert "__interrupt__" not in res
    assert "args" not in send_rec


@pytest.mark.asyncio
async def test_preview_loi_thi_bao_loi_khong_crash(monkeypatch):
    """Task 2 review finding (plan-mandated, 2 tool MCP không try/except) —
    ruling: xử lý ở tầng coordinator thay vì tool. preview_tool.ainvoke ném
    exception (vd Odoo mạng lỗi) không được để lộ traceback ra ngoài node —
    phải trả về _msg lỗi rõ ràng, giống hệt cách send_tool đã xử lý."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    send_rec = {}

    def _raise(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    preview_tool = MagicMock()
    preview_tool.name = "preview_template_email"
    preview_tool.ainvoke = _raise
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m4b"}})
    assert "__interrupt__" not in res
    assert "args" not in send_rec
    assert "lỗi" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_thieu_order_ref_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({}), {"configurable": {"thread_id": "m5"}})
    assert "__interrupt__" not in res
    assert "args" not in preview_rec
    assert "args" not in send_rec


@pytest.mark.asyncio
async def test_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m6"}})
    assert "__interrupt__" not in res
    assert "args" not in preview_rec
