"""Coordinator có phụ thuộc nội bộ (tool MCP tên KHÁC tên coordinator) phải
khai tường minh, và graph phải resolve chúng từ registry MCP đầy đủ.

Lỗi thật đã xảy ra (đo sống 2026-08-12): bộ lọc theo vai cắt mất
preview_template_email, nên send_delivery_email của chính vai kho trả
"Công cụ soạn mail không khả dụng." — trong khi 1254 test vẫn xanh, vì
test mail không biết đến vai và test vai không biết đến mail."""
import json
import pytest
from unittest.mock import MagicMock

import src.agents.mail_write as mw
from src.agents.write_registry import WRITE_COORDINATORS, tools_for_coordinator


def _fake_tool(name):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        return json.dumps({"ok": True, "display": "x", "mail_id": 1,
                           "subject": "s", "recipients": []}, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def test_khong_deps_thi_tra_nguyen_danh_sach():
    spec = WRITE_COORDINATORS["post_invoice"]
    tools = [_fake_tool("post_invoice")]
    assert tools_for_coordinator(spec, tools, [_fake_tool("bat_ky")]) is tools


def test_mcp_all_tools_None_thi_tra_nguyen_danh_sach():
    """Hàng trăm test hiện có dựng graph không truyền mcp_all_tools — nhánh
    này giữ chúng nguyên vẹn."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    assert tools_for_coordinator(spec, tools, None) is tools


def test_resolve_dep_thieu_tu_registry_day_du():
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    full = tools + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    ket_qua = tools_for_coordinator(spec, tools, full)
    ten = {t.name for t in ket_qua}
    assert mw.MAIL_DEPS <= ten
    assert "send_delivery_email" in ten


def test_dep_khong_ton_tai_o_dau_ca_thi_raise():
    """Phân biệt hai loại lỗi: tool không có trong registry MCP là lỗi CẤU
    HÌNH (raise), khác hẳn tool có nhưng vai không được cấp (bỏ qua).

    Chỉ để thiếu ĐÚNG MỘT dep (preview_template_email) trong registry đầy
    đủ — sorted(thieu) duyệt theo alphabet nên nếu để thiếu cả 3, dep bị
    raise đầu tiên là "discard_prepared_email" (d < p < s), không phải
    preview_template_email; match ở đây cần xác định, không phụ thuộc thứ
    tự alphabet của tập thiếu."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    mcp_thieu_preview = tools + [_fake_tool("discard_prepared_email"),
                                 _fake_tool("send_prepared_email")]
    with pytest.raises(ValueError, match="preview_template_email"):
        tools_for_coordinator(spec, tools, mcp_thieu_preview)


@pytest.mark.asyncio
async def test_node_preview_khong_con_bao_khong_kha_dung():
    """Hồi quy TRỰC TIẾP cho lỗi sống: dựng node preview bằng danh sách ĐÃ
    LỌC theo vai kho (chỉ có send_delivery_email) cộng deps resolve từ
    registry đầy đủ — node phải chạy được, không trả câu 'không khả dụng'."""
    cfg = mw.DELIVERY_EMAIL_CFG
    spec = WRITE_COORDINATORS[cfg.tool_name]
    da_loc = [_fake_tool(cfg.tool_name)]
    full = da_loc + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    node = mw.make_send_template_email_preview_node(
        tools_for_coordinator(spec, da_loc, full), cfg)
    state = {"messages": [], "intent": "erp_write", "confirmed": None,
             "pending_action": {"tool": cfg.tool_name,
                                "args": {cfg.ref_arg: "WH/OUT/00138"},
                                "summary": "x"}}
    ket_qua = await node(state)
    # Nhánh thành công của node 1 (mail_write.py) chỉ trả về pending_action
    # cập nhật, KHÔNG có key "messages" (đó là _msg(), chỉ dùng cho nhánh
    # lỗi) — nên phải phòng thủ key vắng mặt thay vì coi nó luôn tồn tại.
    # Nếu bug sống (preview_template_email không resolve được) vẫn còn,
    # node sẽ đi qua _msg("Công cụ soạn mail không khả dụng.") và trả về
    # "messages" có nội dung đó — assert dưới đây bắt được cả hai trường hợp.
    tin_nhan = ket_qua.get("messages", [])
    noi_dung = tin_nhan[-1].content if tin_nhan else ""
    assert "không khả dụng" not in noi_dung


def test_dep_khong_lot_vao_danh_sach_planner_visible():
    """Bất biến bảo mật (spec §3.2, §7.2): tools_for_coordinator KHÔNG được
    sửa danh sách gốc. Nếu nó mutate `tools` tại chỗ thay vì trả bản mới,
    dep sẽ lan sang planner/erp_write_executor — tức LLM gọi thẳng được
    preview_template_email với template bất kỳ, đúng lỗ hổng đang đi bịt."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    da_loc = [_fake_tool("send_delivery_email")]
    full = da_loc + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    tools_for_coordinator(spec, da_loc, full)
    assert [t.name for t in da_loc] == ["send_delivery_email"]
