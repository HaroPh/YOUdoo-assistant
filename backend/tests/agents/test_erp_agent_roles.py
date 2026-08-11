import pytest
from src.agents import roles


def test_loc_tool_theo_vai_bo_tool_ngoai_quyen():
    """Bộ lọc backend là lớp UX/chính xác (lớp cưỡng chế thật là Odoo).
    Vai kho không được thấy post_invoice trong danh sách tool."""
    from src.agents.erp_agent import _filter_tools_for_role

    class T:
        def __init__(self, name): self.name = name

    tools = [T("deliver_order"), T("post_invoice"), T("validate_picking")]
    cfg = roles.PROFILES["small-business"]["warehouse"]
    kept = [t.name for t in _filter_tools_for_role(tools, cfg)]
    assert "deliver_order" in kept
    assert "validate_picking" in kept
    assert "post_invoice" not in kept


def test_vai_admin_giu_nguyen_moi_tool():
    from src.agents.erp_agent import _filter_tools_for_role

    class T:
        def __init__(self, name): self.name = name

    tools = [T("deliver_order"), T("post_invoice")]
    cfg = roles.PROFILES["small-business"]["admin"]
    assert len(_filter_tools_for_role(tools, cfg)) == 2
