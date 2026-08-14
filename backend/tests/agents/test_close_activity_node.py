"""Coordinator đóng việc — hai nhánh vào (có chứng từ / không), hỏi lại khi
trùng, cổng xác nhận.

Toàn bộ tool đều là tool GIẢ: coordinator không được chạm Odoo thật. Vòng
trước có một test gọi Odoo thật vì thiếu điểm tiêm, và nghiệm thu sống tạo
đúng bản ghi đó khiến 3 test đỏ như một hồi quy bí ẩn."""
import json

import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.crm_write as cw
from src.agents import write_gate

ROW_A = {"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
         "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
         "date_deadline": "2026-08-20"}
ROW_B = {"id": 56, "summary": "Kho đề nghị: ghi nhận thanh toán",
         "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
         "date_deadline": "2026-08-21"}


def _content_blocks(payload: dict) -> list[dict]:
    """Shape THẬT mà langchain-mcp-adapters 0.3.0 trả về cho tool MCP dựng với
    response_format="content_and_artifact": MỘT DANH SÁCH content-block, không
    phải chuỗi. C1: _my_open_activities từng json.loads(raw) thẳng vào shape
    này và luôn ném TypeError → tính năng chết 100% trong production dù mọi
    test trước đó xanh, vì fake khi ấy trả chuỗi thuần — shape production
    không bao giờ tạo ra. Đa số fixture ở đây dùng shape THẬT này để phép thử
    phá C1 (hoàn nguyên code về json.loads(raw)) có đường để bắt được."""
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]


def _finder(rows, recorder):
    t = MagicMock()
    t.name = "find_my_activities"

    async def ainvoke(args):
        recorder.setdefault("find", []).append(args)
        return _content_blocks({"ok": True, "rows": list(rows)})

    t.ainvoke = ainvoke
    return t


def _broken_finder():
    """Cố ý giữ shape CHUỖI THUẦN (khác _finder) — kiểm cả hai shape mà
    _tool_result_text phải xử lý được: content-block-list (thật, _finder) và
    chuỗi thuần (fallback cũ, vẫn hợp lệ theo tool_result._tool_result_text).
    Không phải quán tính — cố ý dùng để phủ nhánh isinstance(result, str)."""
    t = MagicMock()
    t.name = "find_my_activities"

    async def ainvoke(args):
        return json.dumps({"ok": False, "rows": []})

    t.ainvoke = ainvoke
    return t


def _closer(recorder):
    t = MagicMock()
    t.name = "close_activity"

    async def ainvoke(args):
        recorder["close"] = args
        return json.dumps({"ok": True, "ref": "S00012", "model": "mail.activity",
                           "res_id": args["activity_id"], "state": "done",
                           "display": "Đã đóng việc."}, ensure_ascii=False)

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
            "pending_action": {"tool": "close_activity", "args": args,
                               "summary": "đóng việc"}}


def _node(rows, recorder):
    return cw.make_close_activity_node([_finder(rows, recorder), _closer(recorder)])


@pytest.fixture(autouse=True)
def _write_on(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)


@pytest.fixture(autouse=True)
def _no_real_odoo(monkeypatch):
    """_resolve_doc đi qua _search_by_name; chặn cứng để không test nào lỡ ra
    Odoo thật."""
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda model, domain, fields, **kw: [{"id": 12, "name": "S00012"}])


@pytest.mark.asyncio
async def test_mot_viec_tren_chung_tu_thi_hoi_xac_nhan_roi_dong():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca1"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012", "note": "xong"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"
    question = res["__interrupt__"][0].value["question"]
    assert "S00012" in question and "phát hành hóa đơn" in question
    assert "2026-08-20" in question

    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"] == {"activity_id": 55, "note": "xong"}
    assert rec["find"][0]["res_model"] == "sale.order"
    assert rec["find"][0]["res_id"] == 12


@pytest.mark.asyncio
async def test_huy_o_cong_xac_nhan_thi_khong_goi_tool():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca2"}}
    await graph.ainvoke(_state({"res_model": "sale.order", "ref": "S00012"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)

    assert "close" not in rec
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_co_viec_nao_tren_chung_tu_thi_noi_ro():
    rec = {}
    graph = _graph(_node([], rec))
    cfg = {"configurable": {"thread_id": "ca3"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert "__interrupt__" not in res
    assert "S00012" in res["messages"][-1].content
    assert "close" not in rec


@pytest.mark.asyncio
async def test_nhieu_viec_thi_hoi_chon_truoc_khi_xac_nhan():
    rec = {}
    graph = _graph(_node([ROW_A, ROW_B], rec))
    cfg = {"configurable": {"thread_id": "ca4"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    res = await graph.ainvoke(Command(resume=56), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"
    assert "ghi nhận thanh toán" in res["__interrupt__"][0].value["question"]

    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"]["activity_id"] == 56


@pytest.mark.asyncio
async def test_huy_o_cong_hoi_chon_thi_khong_goi_tool():
    """I1: nhánh act is None (chosen không khớp id nào trong rows) có đường
    tới THẬT — không chỉ lý thuyết. Resume cổng hỏi-chọn bằng một id KHÔNG có
    trong rows phải fail-closed thành "Đã hủy.", không gọi tool đóng."""
    rec = {}
    graph = _graph(_node([ROW_A, ROW_B], rec))
    cfg = {"configurable": {"thread_id": "ca4b"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    res = await graph.ainvoke(Command(resume=999), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_neu_chung_tu_thi_liet_ke_chu_khong_doi_ma():
    """Đây là đường lui chủ dự án chốt: câu "xong việc rồi" ngay sau khi vừa
    xem danh sách là cách nói tự nhiên nhất, không được chặn lại để đòi mã."""
    rec = {}
    graph = _graph(_node([ROW_A, ROW_B], rec))
    cfg = {"configurable": {"thread_id": "ca5"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    assert rec["find"][0]["res_model"] == ""
    assert rec["find"][0]["res_id"] == 0


@pytest.mark.asyncio
async def test_khong_neu_chung_tu_va_chi_co_mot_viec_thi_di_thang_toi_xac_nhan():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca6"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_khong_co_viec_nao_ca_thi_noi_ro():
    rec = {}
    graph = _graph(_node([], rec))
    cfg = {"configurable": {"thread_id": "ca7"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert "__interrupt__" not in res
    assert "không có việc" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_tra_ung_vien_hong_thi_khong_dong_bua():
    """ok=False từ tool tra cứu KHÔNG được hiểu thành "không có việc nào" —
    hai chuyện đó khác nhau, và nhầm chúng sẽ báo sai sự thật cho người dùng."""
    rec = {}
    node = cw.make_close_activity_node([_broken_finder(), _closer(rec)])
    graph = _graph(node)
    cfg = {"configurable": {"thread_id": "ca8"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec
    assert "không tra được" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_chung_tu_khong_giai_duoc_thi_dung_lai(monkeypatch):
    rec = {}
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda model, domain, fields, **kw: [])
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca9"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S99999"}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec
    assert "find" not in rec


@pytest.mark.asyncio
async def test_write_gate_tat_thi_khong_lam_gi(monkeypatch):
    """monkeypatch ở đây ĐÈ LÊN fixture _write_on (fixture chạy trước), và vẫn
    được gỡ đúng cách sau test — khác hẳn việc gán thẳng vào module."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca10"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec and "find" not in rec


@pytest.mark.asyncio
async def test_dong_duoc_ca_viec_khong_phai_ban_giao():
    """Spec §2.4: KHÔNG lọc theo HANDOFF_MARKER. Một việc do chính vai tự đặt
    (log_activity không có assignee) cũng là việc của vai đó và cũng phải đóng
    được. Giới hạn vào riêng việc bàn giao là ranh giới nhân tạo."""
    rec = {}
    tu_dat = {"id": 57, "summary": "Kiểm lại tồn kho cuối tháng",
              "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
              "date_deadline": "2026-08-22"}
    graph = _graph(_node([tu_dat], rec))
    cfg = {"configurable": {"thread_id": "ca11"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"]["activity_id"] == 57
