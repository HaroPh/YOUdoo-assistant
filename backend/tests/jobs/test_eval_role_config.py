"""Lưới đỡ đóng vĩnh viễn hạng lỗi "bộ đo dựng prompt khác production".

KHÔNG gọi LLM. Đây là phần quan trọng nhất của đợt: hai vế còn lại chỉ sửa
hiện trạng, vế này ngăn tái diễn. Ba bản sửa trước cùng hạng lỗi đều thiếu nó.
"""
import pathlib
from unittest.mock import MagicMock

import pytest

from evals import role_config
from src.agents import prompts as prompts_mod
from src.agents import roles
from src.agents import routing as routing_mod
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.graph import build_graph
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


def test_ten_va_chu_ky_tool_gia_khop_registry_mcp_that():
    """Nếu tool giả lệch khỏi registry thật, mọi phép lọc phía sau đo sai — và
    sai IM LẶNG. Đo cả TÊN lẫn THAM SỐ:

    - tên: quyết định phép lọc theo vai (_filter_tools_for_role);
    - tham số: quyết định build_skill_tools dựng được hay ném
      SkillManifestError, tức quyết định lưới đỡ build_graph bên dưới có chạy
      được không.

    Phép thử phá cho bản sửa chữ ký (chạy 2026-08-14): đưa stub về
    `def _stub(**kwargs)` ⇒ test này ĐỎ, phủ cả 35 tool. Lưới đỡ build_graph
    bên dưới cũng đỏ nhưng chỉ ở các cấu hình còn giữ skill (4/6) — nó chỉ
    chạm 4 tool mà skill thật khai báo, nên không thay được test này."""
    import inspect
    import sys
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        that = {name: set(inspect.signature(t.fn).parameters)
                for name, t in server.mcp._tool_manager._tools.items()}
    finally:
        sys.path.remove(str(MCP_DIR))

    gia = {t.name: set(t.args_schema.model_fields)
           for t in role_config._fake_registry()}
    assert gia == that


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_intent_prompt_khop_cach_production_dung(role, profile, monkeypatch):
    """Vế kỳ vọng ở đây là một bản CHÉP TAY của chính thân role_config._specs,
    nên test này chỉ bắt được chiều "bộ đo trôi". Bất biến thật nằm ở
    test_prompt_bo_do_khop_prompt_build_graph_dung ngay dưới; giữ test này lại
    vì nó chẩn đoán tốt hơn — hai test cùng đỏ ⇒ phía eval hỏng, chỉ test dưới
    đỏ ⇒ production đã trôi."""
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
    """Cùng giới hạn với test intent ngay trên: so với hàm production nhưng gọi
    TRỰC TIẾP, không qua đường graph.py thật sự đi."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    assert role_config.planner_prompt(role) == planner_prompt_for(cfg)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_prompt_bo_do_khop_prompt_build_graph_dung(role, profile, monkeypatch):
    """BẤT BIẾN TRUNG TÂM, chiều mà ba bản sửa trước cùng hạng lỗi đều thiếu:
    so prompt bộ đo với chuỗi production THẬT SỰ dựng, bắt tại đúng chỗ nó
    dựng, qua build_graph() thật.

    Không gọi LLM: make_intent_router_node dựng prompt ngay lúc KHỞI TẠO
    (routing.py), và graph.py truyền prompt planner vào node lúc khởi tạo —
    nên chỉ cần dựng graph, không cần chạy nó.

    Cả hai điểm chặn đều bọc hàm THẬT rồi trả nguyên giá trị của nó, nên
    production không bị đổi hành vi; role_config import hai hàm này vào
    namespace riêng của nó nên vế bộ đo không bị chặn lây.

    Ba phép thử phá đã chạy tay 2026-08-14, mỗi cái sửa MỘT dây trong graph.py
    rồi hoàn nguyên. Trước bản sửa này, cả ba đều KHÔNG làm test nào đỏ:

    1. skill_specs = load_skill_specs() (bỏ specs_for_role) ⇒ đỏ 4/6, hai vai
       bị lọc × hai hồ sơ; admin không lọc nên không đổi.
    2. render_worker_block(load_skill_specs()) nhưng skill_specs vẫn lọc ⇒ đỏ
       đúng 4 cấu hình đó, và lần này đỏ bằng SO SÁNH CHUỖI chứ không phải
       SkillManifestError — tức test bắt lệch prompt thật, không chỉ bắt sập.
    3. planner_prompt_for(None) thay vì planner_prompt_for(role_cfg) ⇒ đỏ 6/6,
       kể cả admin: prompt planner của admin cũng suy từ vai, không phải hằng.

    Ở cả ba, test_intent_prompt_khop_cach_production_dung vẫn XANH — đúng chỗ
    lỗ hổng I2 nằm."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    raw = list(role_config._fake_registry())
    tools = _filter_tools_for_role(raw, cfg)

    ghi = {}
    intent_that = routing_mod.render_intent_router_prompt
    planner_that = prompts_mod.planner_prompt_for

    def _bat_intent(worker_block):
        ghi["intent"] = intent_that(worker_block)
        return ghi["intent"]

    def _bat_planner(role_cfg):
        ghi["planner"] = planner_that(role_cfg)
        return ghi["planner"]

    monkeypatch.setattr(routing_mod, "render_intent_router_prompt", _bat_intent)
    monkeypatch.setattr(prompts_mod, "planner_prompt_for", _bat_planner)

    build_graph(MagicMock(), tools, checkpointer=None, role_cfg=cfg,
                mcp_all_tools=raw)

    assert ghi["intent"] == role_config.intent_prompt(role)
    assert ghi["planner"] == role_config.planner_prompt(role)


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
