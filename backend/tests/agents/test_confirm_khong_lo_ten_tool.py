# backend/tests/agents/test_confirm_khong_lo_ten_tool.py
"""Cổng xác nhận ghi tầng 1: hiện REF THẬT, KHÔNG hiện tên tool MCP.

Đây là chỗ HAI BẤT BIẾN CỐ Ý của repo từng va nhau, và cả hai đều không có
test nào gác khuôn câu hỏi:

  - `agents/tool_leak_guard.py`: tên tool MCP thô KHÔNG được lọt ra người dùng.
  - `nodes.py` "Invariant C tầng 3": cổng xác nhận phải hiện dữ liệu TẤT ĐỊNH
    để user thấy ref thật trước khi bấm "có", kể cả khi `summary` của LLM mơ hồ.

Trước 2026-08-22 câu hỏi in `(deliver_order: order_ref=S00012)` — thoả bất biến
sau, VI PHẠM bất biến trước. Mâu thuẫn có từ lâu ở cả `D:\\Project`; nghiệm thu
e2e 2026-08-21 mới phơi ra (kịch bản `draft_order_refused` đỏ vì *"lộ tool name:
['deliver_order']"*).

Bản sửa bỏ TÊN TOOL và giữ ARGS, vì mục đích của Invariant C là **ref**, không
phải định danh nội bộ. Tệp này khoá cả hai chiều lại: thiếu ref là mất Invariant
C, có tên tool là mất chống-lộ. Không có nó, lần sau ai đó "khôi phục cho dễ
debug" sẽ không gặp phản đối nào.
"""
import json

import pytest
from langchain_core.messages import HumanMessage

import src.agents.nodes as nodes_mod
from src.agents import write_gate
from src.agents.nodes import make_erp_write_planner_node
from src.agents.state import ERPAgentState
from src.agents.tool_leak_guard import has_tool_leak
from tests.conftest import make_mock_llm


def _hoi(monkeypatch, tool, args, summary="Thực hiện thao tác"):
    """Chạy planner thật, trả về nguyên văn câu hỏi của cổng xác nhận."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    bat = {}
    monkeypatch.setattr(nodes_mod, "_interrupt",
                        lambda p: bat.update(p) or True)
    llm = make_mock_llm(json.dumps(
        {"tool": tool, "args": args, "summary": summary}, ensure_ascii=False))
    return bat, llm


@pytest.mark.asyncio
async def test_cau_hoi_xac_nhan_KHONG_chua_ten_tool(monkeypatch):
    """`deliver_order` nằm trong TOOL_NAME_LEAK_MARKERS — đây đúng ca đã đỏ
    trên stack thật ngày 2026-08-21."""
    bat, llm = _hoi(monkeypatch, "deliver_order", {"order_ref": "S00012"},
                    summary="Giao hàng cho đơn bán S00012")
    await make_erp_write_planner_node(llm)(ERPAgentState(
        messages=[HumanMessage(content="giao hàng cho đơn bán S00012")],
        intent="erp_write", pending_action=None, confirmed=None))

    q = bat["question"]
    assert has_tool_leak(q) == [], f"lộ tên tool trong cổng xác nhận: {q!r}"
    assert "deliver_order" not in q


@pytest.mark.asyncio
async def test_cau_hoi_xac_nhan_VAN_chua_ref_that(monkeypatch):
    """Nửa còn lại của cặp. Bỏ tên tool mà bỏ luôn args là đánh mất Invariant C:
    user bấm "có" cho một `summary` do LLM viết, không thấy mã đơn thật."""
    bat, llm = _hoi(monkeypatch, "deliver_order", {"order_ref": "S00012"},
                    summary="Giao hàng")
    await make_erp_write_planner_node(llm)(ERPAgentState(
        messages=[HumanMessage(content="giao hàng cho đơn bán S00012")],
        intent="erp_write", pending_action=None, confirmed=None))

    assert "S00012" in bat["question"], "mất ref thật = mất Invariant C tầng 3"
    assert "order_ref=S00012" in bat["question"]


@pytest.mark.asyncio
async def test_khong_co_args_thi_KHONG_in_ngoac_rong(monkeypatch):
    """"()" trơ trọi vừa xấu vừa không mang thông tin nào."""
    bat, llm = _hoi(monkeypatch, "deliver_order", {}, summary="Thao tác")
    await make_erp_write_planner_node(llm)(ERPAgentState(
        messages=[HumanMessage(content="làm gì đó")],
        intent="erp_write", pending_action=None, confirmed=None))
    assert "()" not in bat["question"]


@pytest.mark.asyncio
async def test_moi_marker_lo_tool_deu_duoc_kiem_chu_khong_rieng_mot_cai(monkeypatch):
    """Kiểm TỪNG marker chứ không chỉ `deliver_order`.

    Một test chỉ dùng một tool sẽ xanh kể cả khi bản sửa vô tình chỉ lọc đúng
    tên đó. Danh sách lấy từ chính TOOL_NAME_LEAK_MARKERS nên thêm marker mới
    là tự động được phủ — không phải danh sách viết tay.
    """
    from src.agents.tool_leak_guard import TOOL_NAME_LEAK_MARKERS

    for marker in TOOL_NAME_LEAK_MARKERS:
        tool = marker.rstrip("(")          # "ask_human(" -> "ask_human"
        bat, llm = _hoi(monkeypatch, tool, {"order_ref": "P00021"})
        await make_erp_write_planner_node(llm)(ERPAgentState(
            messages=[HumanMessage(content="làm gì đó")],
            intent="erp_write", pending_action=None, confirmed=None))
        q = bat.get("question", "")
        assert tool not in q, f"cổng xác nhận lộ {tool!r}: {q!r}"
