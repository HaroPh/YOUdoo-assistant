# backend/tests/agents/test_prompt_per_role.py
from src.agents import roles
from src.agents.prompts import planner_prompt_for, WRITE_PLANNER_PROMPT


def test_prompt_vai_kho_khong_liet_ke_tool_ngoai_quyen():
    cfg = roles.PROFILES["small-business"]["warehouse"]
    p = planner_prompt_for(cfg)
    assert "deliver_order" in p
    assert "post_invoice(" not in p


def test_prompt_vai_admin_giu_nguyen_ban_goc():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert planner_prompt_for(cfg) == WRITE_PLANNER_PROMPT


def test_prompt_neu_ra_bo_phan_phu_trach_cho_viec_ngoai_quyen():
    """Vai kho bị từ chối post_invoice thì phải biết chỉ sang đâu — nếu không,
    người dùng chỉ nhận 'không làm được' mà không biết làm gì tiếp."""
    cfg = roles.PROFILES["small-business"]["warehouse"]
    p = planner_prompt_for(cfg)
    assert "post_invoice" in p           # vẫn nhắc tên, nhưng để TỪ CHỐI
    assert "Kế toán" in p
