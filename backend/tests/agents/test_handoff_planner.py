import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import make_erp_write_planner_node
from src.agents.roles import load_profile


def _vai(ten):
    return load_profile("small-business")[ten]


class FakeLLM:
    """Trả đúng một plan JSON — planner chỉ parse, không cần LLM thật."""

    def __init__(self, payload):
        self._payload = payload

    async def ainvoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage
        return AIMessage(content=self._payload)


def _state(text="phát hành hóa đơn cho đơn S00012"):
    return {"messages": [HumanMessage(content=text)]}


@pytest.mark.asyncio
async def test_dung_duoc_ban_giao_thi_thay_plan(monkeypatch):
    """Vai kho xin phát hành hoá đơn (thuộc Kế toán) VÀ có mã đơn ⇒ plan bị
    thay bằng log_activity, đi tiếp qua cổng xác nhận sẵn có."""
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "create_invoice_from_order", '
                '"args": {"order_ref": "S00012"}, '
                '"summary": "Phát hành hóa đơn cho đơn S00012"}'),
        role_cfg=_vai("warehouse"))

    out = await node(_state())

    plan = out["pending_action"]
    assert plan is not None, "phải có pending_action, không phải từ chối trơn"
    assert plan["tool"] == "log_activity"
    assert plan["args"]["assignee"] == "ai-accounting"
    assert plan["args"]["ref"] == "S00012"
    assert out.get("auto_chain") is None


@pytest.mark.asyncio
async def test_khong_dung_duoc_thi_giu_nguyen_loi_tu_choi(monkeypatch):
    """SÀN: tool không có chứng từ ⇒ đúng câu từ chối cũ, pending_action None."""
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "post_invoice", "args": {"partner_name": "Acme"}, '
                '"summary": "Phát hành hóa đơn"}'),
        role_cfg=_vai("warehouse"))

    out = await node(_state("phát hành hóa đơn cho khách Acme"))

    assert out["pending_action"] is None
    noi_dung = out["messages"][0].content
    assert "không thuộc quyền hạn của bộ phận Kho" in noi_dung
    assert "Kế toán" in noi_dung


@pytest.mark.asyncio
async def test_vai_admin_khong_doi_gi(monkeypatch):
    """role_cfg=None ⇒ guard vai không chạy, hành vi y như trước.

    create_invoice_from_order KHÔNG nằm trong COORDINATED_TOOLS, nên nhánh
    role_cfg=None đi tiếp tới _interrupt() thật (langgraph.types.interrupt),
    đòi hỏi một runnable context mà lệnh gọi node() trực tiếp trong test
    không có (RuntimeError: "Called get_config outside of a runnable
    context") — đây là hành vi CÓ SẴN từ trước Task 2, không liên quan tới
    thay đổi của Task này. Theo đúng mẫu monkeypatch nodes_mod._interrupt đã
    dùng ở test_confirmation_gate.py / test_planner_context.py: thay bằng
    một hàm trả None để lấy được kết quả cuối mà không cần graph context
    thật.
    """
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_interrupt", lambda payload: None)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "create_invoice_from_order", '
                '"args": {"order_ref": "S00012"}, "summary": "x"}'),
        role_cfg=None)

    out = await node(_state())

    assert out["pending_action"]["tool"] == "create_invoice_from_order"
