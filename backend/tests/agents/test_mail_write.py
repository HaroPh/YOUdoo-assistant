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


def _graph(cfg, preview_node, send_node):
    g = StateGraph(ERPAgentState)
    g.add_node(cfg.preview_node, preview_node)
    g.add_node(cfg.send_node, send_node)
    g.add_conditional_edges(
        cfg.preview_node, mw.make_route_after_mail_preview(cfg),
        {cfg.send_node: cfg.send_node, "write_continuation": END})
    g.add_edge(cfg.send_node, END)
    g.set_entry_point(cfg.preview_node)
    return g.compile(checkpointer=MemorySaver())


def _build(tools, cfg=mw.ORDER_CONFIRMATION_CFG):
    """Dựng graph 2-node cho MỘT EmailCfg — thay 2 factory hardcode cũ bằng
    factory tham số hoá (spec 2026-08-08 mail-trigger-points). Chỉ đổi CÁCH
    DỰNG; mọi assertion bên dưới giữ nguyên, đó chính là bằng chứng refactor
    không đổi hành vi."""
    return _graph(cfg,
                  mw.make_send_template_email_preview_node(tools, cfg),
                  mw.make_send_template_email_node(tools, cfg))


def _state(args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": "send_order_confirmation_email",
                               "args": args, "summary": "x"}}


def _preview_response(call_number):
    """mail_id ĐỔI theo call_number (58+n) — để test phát hiện được nếu
    preview bị gọi hơn 1 lần (mail_id sẽ khác giữa các lần gọi).

    "recipients" (danh sách chuỗi người-nhận-thật), KHÔNG PHẢI
    "recipient_count" (final review 2026-08-07, Finding 4) — khớp shape mới
    của preview_template_email (mcp-servers/odoo/tools/mail.py)."""
    return {"ok": True, "display": "Đã soạn mail 'Order Confirmation', chờ xác nhận gửi.",
           "mail_id": 58 + call_number, "subject": "Order Confirmation (Ref S00166)",
           "recipients": ["Nguyễn Văn A <a@example.com>"]}


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
    graph = _build(tools)
    cfg = {"configurable": {"thread_id": "m1"}}
    res = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "S00166" in itr["question"]
    # Finding 4 (final review 2026-08-07): cổng xác nhận phải lộ ra NGƯỜI
    # NHẬN THẬT, không phải chỉ số lượng — mới đủ để người dùng bắt được sai
    # người nhận tại đúng điểm được dựng ra để bắt lỗi này.
    assert "Nguyễn Văn A <a@example.com>" in itr["question"]
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
    graph = _build(tools)
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
    graph = _build(tools)
    cfg = {"configurable": {"thread_id": "m3"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    assert discard_calls == [{"mail_id": 59}]
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_discard_loi_khong_chan_thong_bao_huy_khong_con_canh_bao_rui_ro(monkeypatch):
    """discard_prepared_email lỗi (vd Odoo mạng lỗi) không được chặn thông
    báo 'đã hủy' cho người dùng — best-effort, không phải hợp đồng chính.
    KHÁC bản trước spec 2026-08-08 (bản nháp trơ tính — xem
    mcp-servers/odoo/tools/mail.py): bản nháp đã ở state='cancel' từ lúc
    Node 1 tạo ra, cron/gửi thật không thể chạm tới nó dù discard thất
    bại, nên KHÔNG còn cần cảnh báo rủi ro cron 1 giờ như trước."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools)
    cfg = {"configurable": {"thread_id": "m3b"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    final = res["messages"][-1].content
    assert "hủy" in final.lower()
    assert "không hủy được bản nháp" not in final.lower()
    assert "1 giờ" not in final


@pytest.mark.asyncio
async def test_gate_tat_va_discard_loi_khong_con_canh_bao_rui_ro(monkeypatch):
    """Nhánh gate-tắt-giữa-chừng: discard_prepared_email tự nó gọi odoo()
    với method 'unlink', bị CHÍNH write_actions_enabled() gate (đã False ở
    nhánh này) chặn giống mọi write khác, nên gần như chắc chắn thất bại
    đúng lúc cần dọn nhất. KHÁC bản trước spec 2026-08-08: bản nháp đã trơ
    tính (state='cancel') từ lúc tạo, nên thất bại dọn dẹp ở đây chỉ để
    lại rác trong Odoo — KHÔNG còn kéo theo rủi ro gửi ngoài ý muốn, nên
    KHÔNG còn cần cảnh báo."""
    gate = {"on": True}
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: gate["on"])
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Thao tác 'unlink' bị chặn — write-mode đang tắt")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools)
    cfg = {"configurable": {"thread_id": "m3c"}}
    res1 = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    assert "__interrupt__" in res1

    gate["on"] = False
    res2 = await graph.ainvoke(Command(resume=True), cfg)
    assert send_calls == []
    final = res2["messages"][-1].content
    assert "không hủy được bản nháp" not in final.lower()
    assert "1 giờ" not in final


@pytest.mark.asyncio
async def test_khong_tim_thay_don_thi_bao_loi_khong_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool = _fake_tool("preview_template_email", preview_calls,
                              lambda n: {"ok": False,
                                        "display": "Không tìm thấy bản ghi 'S99999' trong sale.order."})
    _, send_tool, discard_tool = _tools([], send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools)
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
    graph = _build(tools)
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
    graph = _build(tools)
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
    graph = _build(tools)
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m6"}})
    assert "__interrupt__" not in res
    assert preview_calls == []


@pytest.mark.asyncio
async def test_gate_tat_giua_luc_cho_xac_nhan_thi_huy_ban_nhap_khong_gui(monkeypatch):
    """Review round 2, Finding 1 (Important): LangGraph replay lại TOÀN BỘ
    node khi resume — mọi coordinator 1-node khác nhờ vậy tự động re-check
    write_gate ở MỌI lần resume (gate check nằm ở đầu node, node bị replay).
    Tách 2 node đã VÔ TÌNH xóa mất bất biến an toàn đó: Node 1 chỉ check
    gate một lần trước khi interrupt tồn tại; Node 2 (nơi gọi
    send_prepared_email thật) trước đây KHÔNG check gate — nếu gate bị tắt
    ngay lúc câu hỏi xác nhận đang chờ, resume(confirm=True) vẫn gửi mail.
    Case tương đương ở post_invoice (1-node) đã từ chối đúng.

    Ở đây gate BẬT lúc Node 1 chạy (preview thành công, bản nháp mail.mail
    đã tồn tại thật trong Odoo) rồi TẮT trước khi Node 2 resume — bản nháp
    đó đang ở trạng thái 'outgoing', cron sẽ gửi nó nếu không chủ động hủy,
    nên nhánh gate-tắt ở Node 2 PHẢI gọi discard_prepared_email, không chỉ
    từ chối gửi."""
    gate = {"on": True}
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: gate["on"])
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools)
    cfg = {"configurable": {"thread_id": "m7"}}
    res1 = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    assert "__interrupt__" in res1                     # xác nhận đang chờ
    assert preview_calls == [{"template_name": "Sales: Order Confirmation",
                              "res_model": "sale.order", "ref": "S00166"}]

    gate["on"] = False                                  # tắt NGAY lúc chờ
    res2 = await graph.ainvoke(Command(resume=True), cfg)
    assert send_calls == []                             # KHÔNG được gửi
    assert discard_calls == [{"mail_id": 59}]            # phải chủ động hủy
    assert "__interrupt__" not in res2


def test_moi_coordinator_mail_deu_dang_ky_day_du():
    """Review round 2, Finding 2 (Important, 2026-08-07) + spec 2026-08-08
    mail-trigger-points: mọi coordinator gửi mail (nay 4, dựng từ
    MAIL_COORDINATOR_CFGS — không còn 1 tool hardcode + 3 tool copy-paste
    riêng) đều KHÔNG nằm trong NEXT_STEPS (cố ý — mỗi khoá liên quan đã có
    bước kế chiếm chỗ, thêm vào sẽ GHI ĐÈ im lặng, xem docstring
    mail_write.py). Vì vậy dòng tương ứng trong WRITE_PLANNER_PROMPT là
    ĐƯỜNG DUY NHẤT LLM biết một tool gửi mail tồn tại — đây là bất biến
    LOAD-BEARING của cả bài test này.

    Đây CHÍNH XÁC là lớp lỗi mà việc sửa write-confirmation-ux-fix từng
    dính: một coordinator được dựng đúng cấu trúc (đăng ký registry đúng,
    node đúng, mọi test gọi thẳng graph 2-node ở trên vẫn xanh) nhưng KHÔNG
    BAO GIỜ chạm tới được từ một lượt chat thật, vì con đường duy nhất tới
    nó (dòng prompt) bị thiếu — và không có gì khác trong cả bộ test này
    bắt được lỗ hổng đó. Trước bản test này, mỗi lần thêm 1 EmailCfg cũng
    phải nhớ thêm tay 1 dòng vào một tuple literal riêng ở đây — quên 1
    trong 2 chỗ vẫn để lọt cùng lỗ hổng đó (thêm cfg thứ 5 vào
    MAIL_COORDINATOR_CFGS nhưng quên dòng prompt của nó sẽ không bị bài
    test cũ, dựng trên tuple literal, phát hiện). Lặp thẳng trên
    MAIL_COORDINATOR_CFGS xoá điểm quên đó: thêm 1 cfg tự động được test
    này phủ, không cần sửa file test."""
    from src.agents.write_registry import (COORDINATED_TOOLS, WRITE_COORDINATORS,
                                            NEXT_STEPS, CONFIRM_IN_CHAIN)
    from src.agents.prompts import WRITE_PLANNER_PROMPT
    for cfg in mw.MAIL_COORDINATOR_CFGS:
        assert cfg.tool_name in COORDINATED_TOOLS, cfg.tool_name
        assert WRITE_COORDINATORS[cfg.tool_name].node == cfg.preview_node, cfg.tool_name
        assert cfg.tool_name not in NEXT_STEPS, cfg.tool_name
        assert cfg.tool_name in CONFIRM_IN_CHAIN, cfg.tool_name
        assert f"{cfg.tool_name}({cfg.ref_arg}" in WRITE_PLANNER_PROMPT, cfg.tool_name

        # Fix 3 — hợp đồng label CHỮ THƯỜNG (EmailCfg docstring): confirm
        # prompt render qua .capitalize(), câu từ chối dùng label thô. Một
        # label có hoa (vd "RFQ mail") khiến .capitalize() âm thầm hạ hết các
        # chữ hoa còn lại xuống thường ("Rfq mail") — không lỗi, không test
        # nào khác bắt được, chỉ lộ ra khi người dùng đọc câu xác nhận.
        assert cfg.label == cfg.label.lower(), (
            f"{cfg.tool_name}: label {cfg.label!r} phải toàn CHỮ THƯỜNG")
        # Chứng minh CẢ HAI chỗ render (tiền tố xác nhận .capitalize() + câu
        # từ chối dùng label thô) ra đúng: chỉ ký tự đầu đổi hoa, phần còn
        # lại giữ nguyên.
        capitalized = cfg.label.capitalize()
        assert capitalized[0].isupper(), cfg.tool_name
        assert capitalized == cfg.label[0].upper() + cfg.label[1:], cfg.tool_name


def test_moi_cfg_mail_co_template_va_model_rieng_biet():
    """Copy-paste một EmailCfg rồi quên đổi template_name/res_model sẽ khiến
    một coordinator âm thầm gửi SAI loại mail cho SAI đối tượng — lỗi chỉ lộ
    ra khi mail đã bay đi thật. Khoá lại: 5 config phải đôi một khác nhau ở
    cả tool_name lẫn cặp (template_name, res_model)."""
    cfgs = mw.MAIL_COORDINATOR_CFGS
    assert len(cfgs) == 5
    assert len({c.tool_name for c in cfgs}) == 5
    assert len({(c.template_name, c.res_model) for c in cfgs}) == 5
    assert len({c.preview_node for c in cfgs}) == 5
    assert len({c.send_node for c in cfgs}) == 5


@pytest.mark.asyncio
async def test_cfg_quyet_dinh_template_model_va_ten_arg_gui_xuong_tool(monkeypatch):
    """Node 1 phải chuyển ĐÚNG template_name/res_model của cfg xuống tool, và
    đọc ref từ ĐÚNG tên arg của cfg (invoice_ref cho hóa đơn, order_ref cho
    đơn) — nếu nó vẫn hardcode "order_ref" như bản trước refactor thì
    send_invoice_email sẽ luôn báo thiếu mã dù LLM truyền invoice_ref đúng."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    cfg = mw.INVOICE_EMAIL_CFG
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools, cfg)
    state = {"messages": [], "intent": "erp_write", "confirmed": None,
             "pending_action": {"tool": cfg.tool_name,
                                "args": {"invoice_ref": "INV/2026/00030"},
                                "summary": "x"}}
    res = await graph.ainvoke(state, {"configurable": {"thread_id": "mi1"}})
    assert preview_calls == [{"template_name": "Invoice: Sending",
                              "res_model": "account.move",
                              "ref": "INV/2026/00030"}]
    assert "INV/2026/00030" in res["__interrupt__"][0].value["question"]
    assert send_calls == []
