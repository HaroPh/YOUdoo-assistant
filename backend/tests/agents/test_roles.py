import pytest
from src.agents import roles
from src.agents.prompts import WRITE_PLANNER_PROMPT


def _real_tool_names() -> set[str]:
    """Tên tool 'thật' theo đúng cách planner_prompt_for (prompts.py) trích
    xuất: mỗi dòng bắt đầu bằng '- ' và có '(', tên là phần trước dấu '(' đầu
    tiên. Dùng lại nguyên logic đó (không viết lại) để test và generator LUÔN
    đồng thuận về việc gì được tính là một tool thật."""
    names = set()
    for line in WRITE_PLANNER_PROMPT.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and "(" in stripped:
            names.add(stripped[2:].split("(", 1)[0].strip())
    return names


def test_moi_ten_tool_trong_role_cfg_la_tool_that():
    """Task 6's prompt generator (planner_prompt_for) phát ra tên tool từ
    needs_sign_off/other_dept THẲNG vào prompt mà KHÔNG kiểm tra tên đó có
    thật hay không. Đây chính xác là cách một tool ma lọt vào production:
    send_delivery_email từng nằm trong _WH_SIGN_OFF ở roles.py TRƯỚC KHI
    tool đó được xây (Task 7 mới xây nó). Một tên trong RoleCfg mà không
    phải tool thật sẽ khiến prompt sinh ra nhắc tới một năng lực mà planner
    không có schema, và executor sẽ từ chối khi LLM cố gọi nó — bài test này
    khoá bất biến đó lại cho MỌI profile/vai, để lần gõ nhầm tên tool tiếp
    theo bị bắt ngay ở test, không phải ở production."""
    real = _real_tool_names()
    assert real, "rỗng thì test này vô nghĩa"
    for profile_name, roles_by_name in roles.PROFILES.items():
        for role_name, cfg in roles_by_name.items():
            if cfg.unrestricted:
                continue
            declared = cfg.own | cfg.needs_sign_off | cfg.other_dept
            missing = declared - real
            assert not missing, (
                f"{profile_name}/{role_name} khai báo tool không tồn tại "
                f"trong WRITE_PLANNER_PROMPT: {sorted(missing)}")


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
