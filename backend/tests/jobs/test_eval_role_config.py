"""Lưới đỡ đóng vĩnh viễn hạng lỗi "bộ đo dựng prompt khác production".

KHÔNG gọi LLM. Đây là phần quan trọng nhất của đợt: hai vế còn lại chỉ sửa
hiện trạng, vế này ngăn tái diễn. Ba bản sửa trước cùng hạng lỗi đều thiếu nó.
"""
import pathlib

import pytest

from evals import role_config
from src.agents import roles
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.prompts import (INTENT_ROUTER_PROMPT, planner_prompt_for,
                                render_intent_router_prompt)
from src.agents.skill_loader import (load_skill_specs, render_worker_block,
                                     specs_for_role)

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"
PROFILES = ["small-business", "enterprise"]
ROLES = ["admin", "warehouse", "accounting"]


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


def test_ten_tool_gia_khop_registry_mcp_that():
    """Nếu danh sách tên lệch khỏi registry thật, mọi phép lọc phía sau đo sai
    — và sai IM LẶNG. Đây là giả định duy nhất của cách tiếp cận, nên nó phải
    được đo chứ không được tin."""
    import sys
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        that = set(server.mcp._tool_manager._tools)
    finally:
        sys.path.remove(str(MCP_DIR))

    gia = {t.name for t in role_config._fake_registry()}
    assert gia == that


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_intent_prompt_khop_cach_production_dung(role, profile, monkeypatch):
    """Bất biến trung tâm: prompt bộ đo dựng == prompt production dựng."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    raw = role_config._fake_registry()
    mong_doi = render_intent_router_prompt(render_worker_block(
        specs_for_role(load_skill_specs(), _filter_tools_for_role(raw, cfg),
                       raw, cfg)))
    assert role_config.intent_prompt(role) == mong_doi


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_planner_prompt_khop_ham_production(role, profile, monkeypatch):
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    assert role_config.planner_prompt(role) == planner_prompt_for(cfg)


def test_vai_admin_giu_nguyen_cach_dung_cu(monkeypatch):
    """Điều kiện để 5 baseline hiện có còn dùng được: vai admin phải dựng ra
    ĐÚNG chuỗi mà bộ đo dựng TRƯỚC đợt này (tập skill đầy đủ, prompt gốc)."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "small-business")
    cu_intent = render_intent_router_prompt(render_worker_block(load_skill_specs()))
    from src.agents.prompts import WRITE_PLANNER_PROMPT
    assert role_config.intent_prompt("admin") == cu_intent
    assert role_config.planner_prompt("admin") == WRITE_PLANNER_PROMPT


@pytest.mark.parametrize("profile", PROFILES)
def test_vai_ke_toan_co_worker_block_RONG(profile, monkeypatch):
    """Đo 2026-08-14: kế toán giữ 0/3 skill trên CẢ HAI hồ sơ, nên
    render_intent_router_prompt("") trả về prompt TRẦN. Với vai này, prompt
    trần CHÍNH LÀ production — và đó là cấu hình con bọ 'router phân loại lệnh
    ghi thành unknown 3/3' đã sống trong đó."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    assert role_config.intent_prompt("accounting") == INTENT_ROUTER_PROMPT
    assert role_config.valid_sops("accounting") == frozenset()


def test_vai_kho_hep_hon_admin_nhung_khong_rong(monkeypatch):
    """Đối chứng: nếu phép lọc hỏng theo hướng 'lọc sạch mọi thứ', test kế toán
    ở trên vẫn xanh giả. Vai kho phải giữ MỘT PHẦN."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "small-business")
    sops = role_config.valid_sops("warehouse")
    assert sops == {"giao-hang", "nhap-kho"}


def test_ba_bo_nhay_vai_duoc_ghim():
    """Bộ thứ tư trở thành nhạy-vai mà quên khai ⇒ nó sẽ âm thầm đo cấu hình
    admin. Ghim danh sách lại."""
    assert role_config.ROLE_SENSITIVE_SETS == frozenset(
        {"intent", "sop_select", "planner"})


def test_vai_khong_ton_tai_thi_tu_choi():
    """Fail-closed: rơi âm thầm về admin chính là con bọ đợt này đi đóng."""
    with pytest.raises(KeyError):
        role_config.role_cfg("bia-ra")


def test_vai_admin_khong_can_registry_mcp(monkeypatch):
    """Đường admin KHÔNG được phụ thuộc vào việc import được module server.

    `skill_role_gap` trả None vô điều kiện khi `allowed_tools() is None`, nên
    registry hoàn toàn không được dùng ở đường này. Nếu `_specs` vẫn dựng nó,
    đường admin — đường đang chạy tốt và có 6 baseline — sẽ CHẾT khi tiến trình
    eval thiếu ODOO_* hoặc thiếu cây mcp-servers/ (`.env` bị gitignore, nên
    worktree/CI sạch là đúng trường hợp đó). Trước đợt này `eval_intent` không
    có phụ thuộc nào như vậy (final review I3).

    Phép thử phá cho chính bản sửa: gỡ nhánh trả sớm ⇒ test này ĐỎ."""
    def no_registry():
        raise RuntimeError("registry MCP không nạp được")

    monkeypatch.setattr(role_config, "_fake_registry", no_registry)
    assert role_config.intent_prompt("admin")          # không được ném
    assert role_config.valid_sops("admin") == {
        "bao-gia-chiet-khau", "giao-hang", "nhap-kho"}

    # Đối chứng: vai CÓ lọc thì vẫn cần registry — nếu không, bản sửa đã lặng
    # lẽ tắt phép lọc cho mọi vai.
    with pytest.raises(RuntimeError):
        role_config.intent_prompt("accounting")
