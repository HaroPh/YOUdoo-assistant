"""close_activity được cấp cho cả hai vai non-admin, ở CẢ HAI hồ sơ.

Thêm một tool vào `own` nghĩa là scripts/odoo_setup_ai_accounts.py sinh ra bộ
nhóm quyền Odoo khác trước, nên thay đổi này phải được khoá bằng test chứ không
để nó âm thầm (cùng lý do test_log_activity_roles.py tồn tại)."""
import importlib.util
import pathlib
import sys

import pytest

from src.agents import handoff, prompts, roles, write_registry

REPO = pathlib.Path(__file__).resolve().parents[3]
CHECK = REPO / "scripts" / "check_role_odoo_consistency.py"


@pytest.fixture(scope="module")
def check_mod():
    """Nạp scripts/check_role_odoo_consistency.py MỘT LẦN cho cả module.
    scripts/ không phải package con của backend/ (không có __init__.py) nên
    phải nạp qua đường dẫn file bằng importlib, không import thẳng tên —
    cùng mẫu với test_tool_access_map_drift.py:47-59, viết lại riêng ở đây
    (không import chéo file test) để file này tự đứng độc lập."""
    spec = importlib.util.spec_from_file_location(
        "_check_role_for_close_test", CHECK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


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


def test_moi_tool_trong_prompt_planner_deu_co_trong_bang_eval():
    """Bất biến suy ra, thay cho phép kiểm chuỗi con cũ.

    Bản cũ chỉ khẳng định `"close_activity("` xuất hiện trong
    WRITE_PLANNER_PROMPT — vẫn xanh nếu danh sách tham số sai hoàn toàn, và
    không nói gì về 34 tool còn lại.

    `evals/cases.py::WRITE_TOOL_NAMES` tự khai là đồng bộ với prompt. Lệch ⇒
    run_eval xếp một misroute sang tool thiếu vào rổ AN TOÀN thay vì rổ nguy
    hiểm, tức chỉ số dangerous_misroute MÙ với đúng tool đó.

    Đã lệch HAI lần: mail-trigger-points (thiếu 4 tool mail) và close-activity
    (thiếu send_delivery_email). Bất biến này chặn lần thứ ba."""
    import re

    from evals.cases import WRITE_TOOL_NAMES

    trong_prompt = set(re.findall(r"^- (\w+)\(", prompts.WRITE_PLANNER_PROMPT, re.M))
    assert trong_prompt, "regex không bắt được dòng tool nào — sửa regex, đừng nới test"
    thieu = sorted(trong_prompt - set(WRITE_TOOL_NAMES))
    assert not thieu, (
        f"tool có trong WRITE_PLANNER_PROMPT nhưng thiếu ở WRITE_TOOL_NAMES: "
        f"{thieu} — chỉ số dangerous_misroute sẽ mù với chúng")


def test_close_activity_co_trong_ca_prompt_lan_bang():
    """Giữ phần đối chứng cụ thể của test cũ: nêu thẳng tên để nếu ai đó gỡ
    close_activity ra thì đỏ vì đúng lý do, không phải vì một khẳng định
    chung chung."""
    from evals.cases import WRITE_TOOL_NAMES

    assert "close_activity(" in prompts.WRITE_PLANNER_PROMPT
    assert "close_activity" in WRITE_TOOL_NAMES


def test_bang_quyen_odoo_co_dong_cho_close_activity(check_mod):
    assert "close_activity" in check_mod.TOOL_ACCESS_MAP
    assert ("mail.activity", "write") in check_mod.TOOL_ACCESS_MAP["close_activity"]


def test_close_activity_khai_ca_quyen_doc(check_mod):
    """close_activity search_read mail.activity TRƯỚC khi action_feedback
    (crm.py:272) — bộ lọc chủ sở hữu là lớp cưỡng chế duy nhất, vì Odoo
    KHÔNG chặn một tài khoản đóng việc của người khác. Thiếu quyền đọc thì
    lớp đó sập, nên cặp read phải được khai."""
    assert ("mail.activity", "read") in check_mod.TOOL_ACCESS_MAP["close_activity"]


def test_find_my_activities_co_trong_bang(check_mod):
    """Tool CHỈ-ĐỌC nên nó lọt qua cả hai lưới: không ở roles.py (nên
    test_moi_tool_trong_roles_deu_duoc_bang_phu không phủ), không ở
    TOOL_ACCESS_MAP, không ở UNMAPPED_TOOLS."""
    assert ("mail.activity", "read") in check_mod.TOOL_ACCESS_MAP["find_my_activities"]
