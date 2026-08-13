# backend/tests/agents/test_role_write_guard.py
"""Task 8 fix — live defect 2026-08-09: vai `warehouse` hỏi "phát hành hóa
đơn cho khách" (post_invoice, thuộc bộ phận Kế toán) khiến planner cũ tạo
pending_action cho tool bịa "other" (không tồn tại) và hỏi người dùng "xác
nhận" MỘT SỰ TỪ CHỐI — vô lý. Nguyên nhân gốc: ranh giới vai chỉ nằm ở PROMPT
(planner_prompt_for dặn LLM "TỪ CHỐI, KHÔNG cố gọi tool") trong khi hợp đồng
JSON của planner BẮT BUỘC nêu một tool — LLM không có cách nào biểu đạt "chỉ
trả lời, không hành động".

Các test dưới đây khoá lại cổng TẤT ĐỊNH mới trong erp_write_planner
(nodes.py): sau khi biết tên tool, nếu role_cfg.state_of(tool) là
OTHER_DEPT/DENIED → trả lời thẳng, KHÔNG tạo pending_action, KHÔNG gọi
_interrupt — bất kể tool đó có coordinated (post_invoice — đi thẳng, không
qua interrupt()) hay không (deliver_order — đi qua interrupt()).
"""
import json
import pytest

from langchain_core.messages import HumanMessage

from src.agents import roles, write_gate
from src.agents.nodes import make_erp_write_planner_node
from tests.conftest import make_mock_llm

WAREHOUSE = roles.PROFILES["small-business"]["warehouse"]
ACCOUNTING = roles.PROFILES["small-business"]["accounting"]
ADMIN = roles.PROFILES["small-business"]["admin"]


def _write_state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)],
            "intent": "erp_write", "pending_action": None, "confirmed": None}


def _plan_json(tool: str, args: dict | None = None) -> str:
    return json.dumps({"tool": tool, "args": args or {},
                        "summary": "Thực hiện thao tác"})


class _FakeInterrupt(Exception):
    pass


def _interrupt_must_not_fire(monkeypatch):
    """Nếu cổng vai KHÔNG chặn được, node sẽ đi tới _interrupt() cho tool
    không-coordinated — bắt lỗi đó tường minh thay vì để nó lặng lẽ pause."""
    import src.agents.nodes as nodes_mod

    def boom(payload):
        raise AssertionError(
            f"_interrupt() bị gọi dù role_cfg cấm tool này: {payload}")

    monkeypatch.setattr(nodes_mod, "_interrupt", boom)


# ── (1) Đúng ca defect live: post_invoice là COORDINATED TOOL — nhánh cũ trả
#     thẳng {"pending_action": plan, "auto_chain": auto_chain} mà KHÔNG hề
#     đụng tới _interrupt(). Đây là assertion "no pending_action" mà lệnh
#     deliberate-break ở dưới phải chọc thủng đúng chỗ này. ─────────────────

@pytest.mark.asyncio
async def test_warehouse_refused_post_invoice_no_pending_action(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    llm = make_mock_llm(_plan_json("post_invoice", {"partner_name": "Khách A"}))
    node = make_erp_write_planner_node(llm, role_cfg=WAREHOUSE)

    result = await node(_write_state("phát hành hóa đơn cho khách"))

    assert result["pending_action"] is None
    assert result["auto_chain"] is None
    assert len(result["messages"]) == 1
    content = result["messages"][0].content
    assert "Kế toán" in content, "phải nêu đúng bộ phận phụ trách thật"


# ── (2) Cùng yêu cầu, nhánh KHÔNG coordinated (đi qua _interrupt() bình
#     thường nếu không bị chặn) — chứng minh cổng vai chặn CẢ HAI nhánh. ────

@pytest.mark.asyncio
async def test_accounting_xin_deliver_order_thi_duoc_ban_giao_cho_kho(monkeypatch):
    """deliver_order thuộc other_dept của vai Kế toán (nghiệp vụ Kho).

    ĐỔI TÊN 2026-08-13 (trước: ..._no_pending_action). Bàn giao chéo bộ phận
    làm `pending_action` KHÔNG còn None — nó là plan log_activity. Nhưng hai
    tính chất test này bảo vệ thì KHÔNG đổi, và vẫn được assert dưới đây:
      1. deliver_order KHÔNG được thực thi;
      2. người dùng VẪN được cho biết việc thuộc bộ phận nào.
    Tính chất (2) chính là thứ đã ĐỎ khi bản đầu của bàn giao thay plan rồi
    im lặng — test này bắt được, nên đừng nới nó."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _interrupt_must_not_fire(monkeypatch)
    llm = make_mock_llm(_plan_json("deliver_order", {"order_ref": "S00012"}))
    node = make_erp_write_planner_node(llm, role_cfg=ACCOUNTING)

    result = await node(_write_state("giao hàng cho đơn S00012"))

    assert result["pending_action"]["tool"] == "log_activity", \
        "deliver_order KHÔNG được thực thi — phải bị thay bằng bàn giao"
    assert result["pending_action"]["args"]["assignee"] == "ai-warehouse"
    assert result["auto_chain"] is None
    assert "Kho" in result["messages"][0].content


# ── (3) Guard KHÔNG được rò vào vai không giới hạn: role_cfg=None (mọi
#     caller/test cũ) và role_cfg=admin thật (unrestricted=True) đều phải
#     TIẾP TỤC tạo pending_action như trước — không đổi hành vi. ───────────

@pytest.mark.asyncio
async def test_role_cfg_none_still_creates_pending_action(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    llm = make_mock_llm(_plan_json("post_invoice", {"partner_name": "Khách A"}))
    node = make_erp_write_planner_node(llm)  # role_cfg=None mặc định

    result = await node(_write_state("phát hành hóa đơn cho khách"))

    assert result["pending_action"] is not None
    assert result["pending_action"]["tool"] == "post_invoice"


@pytest.mark.asyncio
async def test_admin_role_cfg_still_creates_pending_action(monkeypatch):
    """role_cfg=admin THẬT (unrestricted=True, khác None) — state_of() luôn
    trả OWN nên guard cũng không chặn. Phân biệt với test trên: đây kiểm
    tra nhánh `role_cfg is not None` bên trong guard, không phải nhánh
    role_cfg=None bỏ qua guard hoàn toàn."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    llm = make_mock_llm(_plan_json("post_invoice", {"partner_name": "Khách A"}))
    node = make_erp_write_planner_node(llm, role_cfg=ADMIN)

    result = await node(_write_state("phát hành hóa đơn cho khách"))

    assert result["pending_action"] is not None
    assert result["pending_action"]["tool"] == "post_invoice"


# ── (4) Tool tên bịa (đúng "other" quan sát live) — không tồn tại trong bất
#     kỳ vai nào. RoleCfg.state_of fail-closed nên rơi vào DENIED, bị guard
#     chặn giống hệt other_dept — không tạo confirm prompt cho hành động
#     không hề tồn tại. ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_tool_name_refused_not_confirmed(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _interrupt_must_not_fire(monkeypatch)
    llm = make_mock_llm(_plan_json("other"))
    node = make_erp_write_planner_node(llm, role_cfg=WAREHOUSE)

    result = await node(_write_state("phát hành hóa đơn cho khách"))

    assert result["pending_action"] is None
    assert result["auto_chain"] is None
    assert len(result["messages"]) == 1
    # Không có bộ phận cụ thể cho tool bịa ra — dept_of fallback 'khác'.
    assert "khác" in result["messages"][0].content


# ── (5) final-review Fix 1: auto_chain rò khỏi cổng vai. plan["tool"] (bước
#     ĐẦU, deliver_order) là own của vai kho nên qua được cổng ở dòng ~273 —
#     nhưng expand_chain() thêm bước THỨ HAI (create_invoice_from_order,
#     "xuất hóa đơn") mà cổng đầu không hề soi tới. Trước fix: node trả thẳng
#     {"pending_action": plan, "auto_chain": [...]} cho non-coordinated tool
#     → interrupt() sẽ CHẠY (hiện confirm quảng cáo bước cấm, và nếu người
#     dùng đồng ý, executor sẽ THỰC SỰ giao hàng trước khi bị chặn ở bước
#     hai) — đúng ca sống 2026-08-09 nêu trong report review. Sau fix: TOÀN
#     CHUỖI bị soi trước khi bất cứ gì chạy — no pending_action nghĩa là
#     _interrupt() không hề được gọi, nên deliver_order KHÔNG được thực thi
#     dù nó tự nó được phép. ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warehouse_chain_deliver_then_invoice_refused_whole_chain(monkeypatch):
    """'giao hàng đơn S00012 rồi xuất hóa đơn luôn' — deliver_order (own, vai
    kho) chain_until create_invoice_from_order (Kế toán). Phải từ chối CẢ
    CHUỖI trước khi chạy — không giao hàng rồi mới báo lỗi ở bước hai."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _interrupt_must_not_fire(monkeypatch)
    plan = {"tool": "deliver_order", "args": {"order_ref": "S00012"},
            "summary": "Giao hàng và xuất hóa đơn",
            "chain_until": "create_invoice_from_order"}
    llm = make_mock_llm(json.dumps(plan, ensure_ascii=False))
    node = make_erp_write_planner_node(llm, role_cfg=WAREHOUSE)

    result = await node(_write_state("giao hàng đơn S00012 rồi xuất hóa đơn luôn"))

    # Bàn giao (2026-08-13): pending_action nay là plan log_activity,
    # KHÔNG còn None. Tính chất AN TOÀN thì y nguyên và vẫn được assert:
    # deliver_order không chạy, cả chuỗi bị chặn trước khi bất cứ gì thực thi.
    assert result["pending_action"]["tool"] == "log_activity", \
        "giao hàng KHÔNG được thực thi — cả chuỗi phải bị chặn trước khi chạy"
    assert result["auto_chain"] is None
    assert len(result["messages"]) == 1
    content = result["messages"][0].content
    # Nêu đúng bước cấm ĐẦU TIÊN và bộ phận phụ trách thật (Kế toán), không
    # phải bộ phận của deliver_order (Kho) — deliver_order tự nó được phép.
    assert "Kế toán" in content
