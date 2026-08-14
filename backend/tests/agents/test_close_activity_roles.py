"""close_activity được cấp cho cả hai vai non-admin, ở CẢ HAI hồ sơ.

Thêm một tool vào `own` nghĩa là scripts/odoo_setup_ai_accounts.py sinh ra bộ
nhóm quyền Odoo khác trước, nên thay đổi này phải được khoá bằng test chứ không
để nó âm thầm (cùng lý do test_log_activity_roles.py tồn tại)."""
import importlib.util
import pathlib
import sys

from src.agents import handoff, prompts, roles, write_registry

REPO = pathlib.Path(__file__).resolve().parents[3]
CHECK = REPO / "scripts" / "check_role_odoo_consistency.py"


def test_ca_hai_vai_deu_so_huu_close_activity():
    for profile_name, profile in roles.PROFILES.items():
        for role_name in ("warehouse", "accounting"):
            cfg = profile[role_name]
            assert cfg.state_of("close_activity") == roles.OWN, (
                f"{profile_name}/{role_name} không sở hữu close_activity")
            assert "close_activity" in cfg.allowed_tools()


def test_close_activity_co_trong_dept_of():
    assert "close_activity" in roles.DEPT_OF


def test_close_activity_khong_co_chung_tu_de_ban_giao():
    """Nó tác động lên MỘT activity, không lên một chứng từ — và cả hai vai đều
    sở hữu nên không bao giờ phát sinh bàn giao. Phải nằm ở NO_DOCUMENT_TOOLS,
    không phải HANDOFF_DOC_OF."""
    assert "close_activity" in handoff.NO_DOCUMENT_TOOLS
    assert "close_activity" not in handoff.HANDOFF_DOC_OF


def test_dang_ky_coordinator_kem_dep_tra_ung_vien():
    spec = write_registry.WRITE_COORDINATORS["close_activity"]
    assert spec.node == "crm_close_activity"
    assert "find_my_activities" in spec.deps, (
        "thiếu dep thì coordinator không có tool tra ứng viên — nhánh liệt kê "
        "im lặng chết trong production dù test dùng tool giả vẫn xanh")


def test_dep_tra_ung_vien_khong_lot_vao_danh_sach_planner():
    """deps CHỈ được thêm cho coordinator. Lọt vào danh sách planner-visible là
    mở đúng lỗ hổng mà cơ chế deps đi bịt: LLM gọi thẳng tool tra cứu, bỏ qua
    coordinator và cổng xác nhận."""
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            allowed = cfg.allowed_tools()
            if allowed is None:
                continue
            assert "find_my_activities" not in allowed


def test_planner_biet_ten_tool():
    assert "close_activity(" in prompts.WRITE_PLANNER_PROMPT


def test_bang_quyen_odoo_co_dong_cho_close_activity():
    spec = importlib.util.spec_from_file_location(
        "_check_role_for_close_test", CHECK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert "close_activity" in mod.TOOL_ACCESS_MAP
    assert ("mail.activity", "write") in mod.TOOL_ACCESS_MAP["close_activity"]
