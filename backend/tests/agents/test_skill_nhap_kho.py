"""Tương đương hành vi cho nhap-kho — chuỗi kỳ vọng chép từ
D:\\Project\\backend\\src\\agents\\skill_agentic_warehouse_receiving.py:79-100.
Điểm khác giao-hang: flag_order_for_review có fixed_args model="purchase.order"
(wrapper cũ ghim hằng đó trong payload ainvoke, dòng 98-99)."""
import json
from unittest.mock import patch

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import SKILLS_DIR, build_skill_tools
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "nhap-kho" / "SKILL.md")


def _mcp():
    calls = {"receive": [], "flag": []}

    @lc_tool("receive_order")
    async def receive_order(order_ref: str) -> str:
        """Xác nhận nhận hàng vào Odoo cho một đơn mua ĐÃ XÁC NHẬN."""
        calls["receive"].append({"order_ref": order_ref})
        return json.dumps({"ok": True, "display": f"Đã nhận hàng cho đơn {order_ref}."},
                          ensure_ascii=False)

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """Ghi chú nội bộ lên đơn."""
        calls["flag"].append({"model": model, "order_ref": order_ref, "note": note})
        return json.dumps({"ok": True, "display": "Đã ghi chú."}, ensure_ascii=False)

    return [receive_order, flag_order_for_review], calls


def test_manifest_matches_source_module():
    assert SPEC.read_tools == ("get_purchase_order_detail",)
    assert [w.name for w in SPEC.write_tools] == ["receive_order",
                                                  "flag_order_for_review"]
    assert SPEC.max_steps == 15
    assert SPEC.prose.startswith("Bạn là trợ lý kho, thực hiện quy trình nhập kho.")


def test_bridge_message_is_verbatim_in_prose():
    """NO_PO_BRIDGE_MSG (nhánh 'không có PO') sống trong prose và phải nguyên
    văn — model được dặn trả ĐÚNG chuỗi này để giảm biến thiên."""
    assert ("Quy trình nhập kho này yêu cầu có đơn mua (PO). Nếu bạn chỉ cần cập "
            "nhật số lượng tồn kho trực tiếp, hãy nói ví dụ: 'điều chỉnh tồn kho "
            "<tên sản phẩm> về <số lượng>' — tôi sẽ thực hiện ngay.") in SPEC.prose


@pytest.mark.asyncio
async def test_receive_order_confirm_verbatim():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await tools["receive_order"].ainvoke({"order_ref": "P00021"})
    assert asked == ["Xác nhận NHẬN HÀNG cho đơn mua P00021?"]
    assert calls["receive"] == [{"order_ref": "P00021"}]


@pytest.mark.asyncio
async def test_flag_confirm_verbatim_and_model_pinned_to_purchase_order():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await tools["flag_order_for_review"].ainvoke(
            {"order_ref": "P00021", "note": "thiếu 2 cái"})
    assert asked == ['Xác nhận GHI CHÚ lên đơn mua P00021: "thiếu 2 cái"?']
    assert calls["flag"] == [{"model": "purchase.order", "order_ref": "P00021",
                              "note": "thiếu 2 cái"}]


@pytest.mark.asyncio
async def test_both_write_tools_refuse_without_touching_mcp():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        assert await tools["receive_order"].ainvoke({"order_ref": "P00021"}) == REFUSED_MSG
        assert await tools["flag_order_for_review"].ainvoke(
            {"order_ref": "P00021", "note": "x"}) == REFUSED_MSG
    assert calls == {"receive": [], "flag": []}
