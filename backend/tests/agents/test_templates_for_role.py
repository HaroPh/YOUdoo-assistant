"""Allowlist template phải được SUY RA từ roles.py × EmailCfg, không khai lại.

Khai lại là đẻ thêm đúng loại danh sách song song mà cả mạch phân quyền đang
đi sửa — và tiến trình MCP không import được backend nên không tự suy được."""
import src.agents.mail_write as mw
from src.agents import roles


def _vai(ten):
    return roles.load_profile()[ten]


def test_admin_khong_gioi_han():
    assert mw.templates_for_role(_vai("admin")) is None
    assert mw.mail_models_for_role(_vai("admin")) is None


def test_kho_chi_duoc_template_giao_hang():
    assert mw.templates_for_role(_vai("warehouse")) == frozenset(
        {mw.DELIVERY_EMAIL_CFG.template_name})
    assert mw.mail_models_for_role(_vai("warehouse")) == frozenset(
        {mw.DELIVERY_EMAIL_CFG.res_model})


def test_ke_toan_chi_duoc_template_hoa_don():
    assert mw.templates_for_role(_vai("accounting")) == frozenset(
        {mw.INVOICE_EMAIL_CFG.template_name})
    assert mw.mail_models_for_role(_vai("accounting")) == frozenset(
        {mw.INVOICE_EMAIL_CFG.res_model})


def test_suy_ra_chu_khong_hardcode():
    """Đối chứng cho tính 'suy ra': với MỘT RoleCfg tự chế được cấp đúng một
    coordinator mail khác, hàm phải trả template của coordinator ĐÓ — không
    phải một danh sách viết cứng."""
    cfg = roles.RoleCfg("thu", "Thử", "http://x", own=frozenset({"send_rfq_email"}))
    assert mw.templates_for_role(cfg) == frozenset({mw.RFQ_EMAIL_CFG.template_name})


def test_vai_khong_co_coordinator_mail_thi_rong():
    cfg = roles.RoleCfg("thu", "Thử", "http://x", own=frozenset({"deliver_order"}))
    assert mw.templates_for_role(cfg) == frozenset()


def test_moi_profile_deu_suy_duoc_khong_no():
    for ten_profile in roles.PROFILES:
        for cfg in roles.load_profile(ten_profile).values():
            mw.templates_for_role(cfg)
            mw.mail_models_for_role(cfg)
