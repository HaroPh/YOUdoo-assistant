import pytest
from src.agents import roles


def test_tool_khong_khai_bao_thi_mac_dinh_bi_tu_choi():
    """Fail-closed: quên khai báo một tool = tool đó bị CẤM, không phải được
    phép. Nếu mặc định là 'own', thêm tool mới vào hệ thống sẽ âm thầm cấp nó
    cho mọi vai — đúng lớp lỗi mà toàn bộ thiết kế này sinh ra để ngăn."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset(),
                        other_dept=frozenset())
    assert cfg.state_of("a") == roles.OWN
    assert cfg.state_of("tool_chua_ton_tai") == roles.DENIED


def test_allowed_tools_gom_own_va_needs_sign_off_khong_gom_other_dept():
    """Quyền trên tài khoản Odoo = own ∪ needs_sign_off. other_dept KHÔNG nằm
    trong đó — đó chính là chỗ Odoo cưỡng chế."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset({"b"}),
                        other_dept=frozenset({"c"}))
    assert cfg.allowed_tools() == frozenset({"a", "b"})
    assert cfg.state_of("c") == roles.OTHER_DEPT


def test_vai_admin_khong_bi_gioi_han():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert cfg.unrestricted is True
    assert cfg.state_of("bat_ky_tool_nao") == roles.OWN
    assert cfg.allowed_tools() is None   # None = không lọc


def test_warehouse_khong_duoc_phat_hanh_hoa_don():
    """Từ phỏng vấn thật (câu 22): post_invoice với kho là 'việc phòng khác'."""
    cfg = roles.PROFILES["small-business"]["warehouse"]
    assert cfg.state_of("post_invoice") == roles.OTHER_DEPT
    assert "post_invoice" not in cfg.allowed_tools()


def test_accounting_duoc_phat_hanh_hoa_don_nhung_can_duyet():
    """Phỏng vấn A2 câu 1 = X: việc của mình, nhưng kế toán trưởng ký.
    Khác hẳn kho — cùng một tool, hai trạng thái khác nhau. Đây là phép đo
    chứng minh 2 vai thật sự khác nhau."""
    cfg = roles.PROFILES["small-business"]["accounting"]
    assert cfg.state_of("post_invoice") == roles.NEEDS_SIGN_OFF
    assert "post_invoice" in cfg.allowed_tools()


def test_ho_so_enterprise_go_quyen_khoi_vai_kho():
    """Hồ sơ enterprise phải khiến nghiệp vụ RỜI tập own∪needs_sign_off —
    chỉ khi đó quyền mới bị gỡ khỏi tài khoản Odoo. Chuyển other_dept→denied
    KHÔNG đổi gì ở tầng Odoo (cả hai đều là 'không có quyền')."""
    small = roles.PROFILES["small-business"]["warehouse"]
    ent = roles.PROFILES["enterprise"]["warehouse"]
    assert "inventory_adjustment" in small.allowed_tools()
    assert "inventory_adjustment" not in ent.allowed_tools()


def test_user_khong_co_trong_bang_anh_xa_thi_khong_co_vai(monkeypatch):
    """Fail-closed: người lạ KHÔNG được mặc định thành admin."""
    monkeypatch.setenv("YOUDOO_ROLE_MAP", "abc:admin")
    assert roles.role_for_user("abc") == "admin"
    assert roles.role_for_user("nguoi_la") is None
    assert roles.role_for_user(None) is None


def test_bang_anh_xa_rong_thi_khong_ai_co_vai(monkeypatch):
    monkeypatch.delenv("YOUDOO_ROLE_MAP", raising=False)
    assert roles.role_for_user("bat_ky") is None
