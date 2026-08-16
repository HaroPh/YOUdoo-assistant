"""Tương đương hành vi: wrapper deliver_order do skill_loader SINH TỰ ĐỘNG phải
quan sát được y hệt wrapper viết tay cũ ở
D:\\Project\\backend\\src\\agents\\skill_agentic_delivery.py:53-60 —
cùng câu xác nhận đã nội suy, cùng REFUSED_MSG, cùng payload ainvoke.

Module gốc KHÔNG tồn tại trong D:\\Youdoo (cố ý không port ở SP-1B), nên không
import để so sánh trực tiếp được; chuỗi kỳ vọng dưới đây chép từ mã nguồn đó."""
import json
from unittest.mock import patch

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import SKILLS_DIR, build_skill_tools
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "giao-hang" / "SKILL.md")


def _mcp():
    calls = []

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """Xác nhận giao hàng vào Odoo cho một đơn bán ĐÃ XÁC NHẬN."""
        calls.append({"order_ref": order_ref})
        return json.dumps({"ok": True, "ref": order_ref, "model": "sale.order",
                           "display": f"Đã giao hàng cho đơn {order_ref} (1 phiếu)."},
                          ensure_ascii=False)

    return [deliver_order], calls


def test_manifest_matches_source_module():
    assert SPEC.read_tools == ("get_sale_order_detail",)
    assert [w.name for w in SPEC.write_tools] == ["deliver_order"]
    assert SPEC.max_steps == 15
    # Prose LÀ system prompt — phải là nguyên văn SOP_PROMPT cũ, không cắt xén.
    assert SPEC.prose.startswith(
        "Bạn là trợ lý kho, thực hiện quy trình giao hàng cho đơn bán.")
    assert SPEC.prose.rstrip().endswith(
        "dừng lại ở đó, chờ yêu cầu mới từ người dùng.")


def test_description_has_both_clauses():
    assert "Chọn worker này khi" in SPEC.description
    assert "KHÔNG chọn khi" in SPEC.description


@pytest.mark.asyncio
async def test_confirm_question_is_verbatim_and_write_happens_once():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []

    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert asked == ["Xác nhận GIAO HÀNG cho đơn bán S00012?"]
    assert calls == [{"order_ref": "S00012"}]
    assert "Đã giao hàng cho đơn S00012" in out


@pytest.mark.asyncio
async def test_refusal_returns_refused_msg_and_writes_nothing():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})
    assert out == REFUSED_MSG
    assert calls == []


def test_model_never_sees_raw_write_tool():
    """Bất biến: mọi tool ghi bind vào node SOP đều là wrapper đã gate — cùng
    TÊN với tool MCP nhưng KHÁC ĐỐI TƯỢNG."""
    mcp, _ = _mcp()
    raw = {t.name: t for t in mcp}
    for t in build_skill_tools(SPEC, mcp):
        if t.name in raw:
            assert t is not raw[t.name], f"{t.name} bind THẲNG tool MCP, không qua gate"
