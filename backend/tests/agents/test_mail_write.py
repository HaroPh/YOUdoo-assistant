import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.mail_write as mw
from src.agents import write_gate


def _fake_tool(name, calls_list, response_fn):
    """response_fn(call_number) -> dict cho lần gọi thứ N (1-indexed) —
    cho phép trả mail_id KHÁC NHAU mỗi lần gọi, để bắt được bug preview bị
    gọi lại (replay) thay vì chỉ chạy đúng 1 lần."""
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        calls_list.append(args)
        return json.dumps(response_fn(len(calls_list)), ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(preview_node, send_node):
    g = StateGraph(ERPAgentState)
    g.add_node("send_order_confirmation_email_preview", preview_node)
    g.add_node("send_order_confirmation_email", send_node)
    g.add_conditional_edges(
        "send_order_confirmation_email_preview", mw.route_after_mail_preview,
        {"send_order_confirmation_email": "send_order_confirmation_email",
         "write_continuation": END})
    g.add_edge("send_order_confirmation_email", END)
    g.set_entry_point("send_order_confirmation_email_preview")
    return g.compile(checkpointer=MemorySaver())


def _state(args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": "send_order_confirmation_email",
                               "args": args, "summary": "x"}}


def _preview_response(call_number):
    """mail_id ĐỔI theo call_number (58+n) — để test phát hiện được nếu
    preview bị gọi hơn 1 lần (mail_id sẽ khác giữa các lần gọi)."""
    return {"ok": True, "display": "Đã soạn mail 'Order Confirmation', chờ xác nhận gửi.",
           "mail_id": 58 + call_number, "subject": "Order Confirmation (Ref S00166)",
           "recipient_count": 1}


_SEND_OK = {"ok": True, "display": "Đã gửi mail.", "ref": "Order Confirmation (Ref S00166)",
           "model": "mail.mail", "res_id": 59, "state": "sent"}
_DISCARD_OK = {"ok": True, "display": "Đã hủy mail nháp.", "ref": "59",
              "model": "mail.mail", "res_id": 59, "state": "cancelled"}


def _tools(preview_calls, send_calls, discard_calls):
    preview_tool = _fake_tool("preview_template_email", preview_calls, _preview_response)
    send_tool = _fake_tool("send_prepared_email", send_calls, lambda n: _SEND_OK)
    discard_tool = _fake_tool("discard_prepared_email", discard_calls, lambda n: _DISCARD_OK)
    return preview_tool, send_tool, discard_tool


@pytest.mark.asyncio
async def test_co_order_ref_thi_hien_preview_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m1"}}
    res = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "S00166" in itr["question"]
    assert "1 người nhận" in itr["question"]
    assert "Order Confirmation (Ref S00166)" in itr["question"]
    assert preview_calls == [{"template_name": "Sales: Order Confirmation",
                              "res_model": "sale.order", "ref": "S00166"}]
    assert send_calls == []           # chưa gửi trước khi xác nhận


@pytest.mark.asyncio
async def test_xac_nhan_thi_goi_send_bang_dung_mail_id_va_preview_chi_goi_1_lan(monkeypatch):
    """Chốt chặn bug Critical đã đo thật ở review Task 3 (2026-08-07):
    LangGraph replay TOÀN BỘ node khi resume sau _interrupt — nếu preview
    nằm cùng node với interrupt (thiết kế cũ), nó bị gọi LẦN THỨ HAI, tạo
    mail.mail thứ hai, và send() nhận mail_id của bản KHÔNG được duyệt.
    mail_id đổi theo lần gọi (_preview_response) nên nếu bug tái diễn,
    assert send_calls dưới đây sẽ fail vì mail_id không khớp lần gọi đầu."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m2"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert len(preview_calls) == 1                    # KHÔNG bị replay
    assert send_calls == [{"mail_id": 59}]             # 58 + 1 (lần gọi duy nhất)
    assert res["last_write"]["tool"] == "send_order_confirmation_email"
    assert res["last_write"]["state"] == "sent"
    assert discard_calls == []


@pytest.mark.asyncio
async def test_tu_choi_thi_goi_discard_va_khong_goi_send(monkeypatch):
    """Đảo ngược quyết định §4.1 gốc: Odoo có cron 'Mail: Email Queue
    Manager' đang bật (đo thật 2026-08-07), tự gửi MỌI mail.mail ở trạng
    thái 'outgoing' — kể cả bản bị từ chối nếu không chủ động hủy."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    assert discard_calls == [{"mail_id": 59}]
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_discard_loi_khong_chan_thong_bao_huy(monkeypatch):
    """discard_prepared_email lỗi (vd Odoo mạng lỗi) không được chặn thông
    báo 'đã hủy' cho người dùng — best-effort, không phải hợp đồng chính."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3b"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_tim_thay_don_thi_bao_loi_khong_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool = _fake_tool("preview_template_email", preview_calls,
                              lambda n: {"ok": False,
                                        "display": "Không tìm thấy bản ghi 'S99999' trong sale.order."})
    _, send_tool, discard_tool = _tools([], send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S99999"}),
                              {"configurable": {"thread_id": "m4"}})
    assert "__interrupt__" not in res
    assert send_calls == []


@pytest.mark.asyncio
async def test_preview_loi_thi_bao_loi_khong_crash(monkeypatch):
    """Task 2 review finding (plan-mandated, 2 tool MCP không try/except) —
    ruling: xử lý ở tầng coordinator thay vì tool."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    send_calls, discard_calls = [], []

    preview_tool = MagicMock()
    preview_tool.name = "preview_template_email"

    async def _raise(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    preview_tool.ainvoke = _raise
    _, send_tool, discard_tool = _tools([], send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m4b"}})
    assert "__interrupt__" not in res
    assert send_calls == []
    assert "lỗi" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_thieu_order_ref_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({}), {"configurable": {"thread_id": "m5"}})
    assert "__interrupt__" not in res
    assert preview_calls == []
    assert send_calls == []


@pytest.mark.asyncio
async def test_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m6"}})
    assert "__interrupt__" not in res
    assert preview_calls == []
