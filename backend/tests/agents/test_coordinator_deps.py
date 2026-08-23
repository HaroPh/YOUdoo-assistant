"""Coordinator có phụ thuộc nội bộ (tool MCP tên KHÁC tên coordinator) phải
khai tường minh, và graph phải resolve chúng từ registry MCP đầy đủ.

Lỗi thật đã xảy ra (đo sống 2026-08-12): bộ lọc theo vai cắt mất
preview_template_email, nên send_delivery_email của chính vai kho trả
"Công cụ soạn mail không khả dụng." — trong khi 1254 test vẫn xanh, vì
test mail không biết đến vai và test vai không biết đến mail."""
import json
import pathlib
import re

import pytest
from unittest.mock import MagicMock

import src.agents.mail_write as mw
from src.agents.write_registry import WRITE_COORDINATORS, tools_for_coordinator

GRAPH_PY = (pathlib.Path(__file__).resolve().parents[3]
            / "backend" / "src" / "agents" / "graph.py")


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


def test_erp_write_executor_va_skill_node_khong_di_qua_tools_for_coordinator():
    """Bất biến bảo mật (spec §3.2/§7.2), tầng NGOÀI test trên: chỉ node
    coordinator (WRITE_COORDINATORS, dep khai tường minh) mới được gọi
    tools_for_coordinator để lồng thêm deps mail. `erp_write_executor` và
    node SOP/skill phải nhận đúng `tools` — danh sách đã lọc theo vai gốc,
    KHÔNG lồng thêm deps — nếu không, LLM planner ở đó gọi thẳng được
    preview_template_email/send_prepared_email/... với template/model bất
    kỳ, vượt khỏi bộ lọc theo vai (đúng lỗ hổng "dep lọt vào danh sách
    planner-visible" mà hai test phía trên bịt, nhưng chỉ bịt được ở tầng
    tools_for_coordinator — nếu graph.py lỡ bọc tools_for_coordinator(...)
    quanh erp_write_executor hoặc build_skill_node, không test nào ở trên
    bắt được).

    Test đọc NGUỒN graph.py (không import/dựng graph thật — dựng graph cần
    role_cfg/mcp_all_tools đầy đủ, không cần thiết để pin bất biến CẤU TRÚC
    này), theo đúng kỹ thuật ở test_odoo_setup_mail_groups.py."""
    src = GRAPH_PY.read_text(encoding="utf-8")

    m = re.search(
        r'g\.add_node\("erp_write_executor",\s*'
        r'make_erp_write_executor_node\((.*?)\)\)', src)
    assert m, ("không tìm thấy dòng "
               "add_node('erp_write_executor', make_erp_write_executor_node("
               "...)) trong graph.py — file đã đổi cấu trúc?")
    assert m.group(1).strip() == "tools", (
        f"erp_write_executor phải nhận đúng biến `tools` (đã lọc theo vai), "
        f"không phải {m.group(1)!r} — nếu đây là tools_for_coordinator(...), "
        f"deps mail đã lọt vào planner/erp_write_executor")

    # re.S: lời gọi trải HAI DÒNG từ 2026-08-23 (thêm role_cfg), regex một
    # dòng không bắt được và test đỏ với thông điệp sai hẳn bản chất
    # ("không tìm thấy build_skill_node" trong khi nó vẫn ở đó).
    m2 = re.search(r'build_skill_node\((.*?)\)', src, re.S)
    assert m2, "không tìm thấy build_skill_node(...) trong graph.py"
    args = [a.strip() for a in m2.group(1).split(",")]
    # Ghim theo VỊ TRÍ THAM SỐ mcp_tools (thứ ba), không phải "tham số cuối".
    # Bản cũ ghim `args[-1]` và đỏ ngày 2026-08-23 khi `role_cfg` được thêm
    # vào SAU nó cho vệt kiểm toán đường đọc — bất biến thật (mcp_tools phải
    # là `tools`, không phải tools_for_coordinator(...)) không hề đổi, chỉ vị
    # trí đổi. Ghim vị trí cuối là ghim một thứ không phải bất biến.
    assert len(args) >= 3, f"build_skill_node(...) thiếu tham số: {args}"
    assert args[2] == "tools", (
        f"build_skill_node phải nhận đúng `tools` làm mcp_tools (tham số thứ "
        f"ba), không phải {args[2]!r} — nếu đây là tools_for_coordinator(...), "
        f"deps mail đã lọt vào node SOP/skill")
