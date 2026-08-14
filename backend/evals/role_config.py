"""Dựng prompt theo VAI cho bộ đo eval — bằng chính hàm production dùng.

Vì sao cần: production lọc cả tập skill lẫn tập tool theo vai (graph.py,
planner_prompt_for), còn bộ đo trước đây luôn dựng từ tập ĐẦY ĐỦ. Đo
2026-08-14: vai kế toán chạy worker block RỖNG (0/3 skill) trong khi bộ đo đo
3/3 — nên mọi kết luận "cấu hình còn khoẻ" chỉ đúng cho vai admin.

skill_role_gap cần ĐỐI TƯỢNG tool, mà bộ đo không có kết nối MCP. Giải: lấy
TÊN tool thật bằng cách import module server của mcp-servers/odoo (đã kiểm:
cho ra đủ 35 tên, không cần MCP sống, không chạm Odoo — get_uid() là lười),
rồi dựng tool giả mang đúng tên đó. Giả định duy nhất — bộ lọc chỉ quan tâm
TÊN — được khoá bằng test, không để là niềm tin.
"""
import functools
import pathlib
import sys

from langchain_core.tools import tool as lc_tool

from src.agents import roles
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.prompts import (planner_prompt_for, render_intent_router_prompt)
from src.agents.skill_loader import (load_skill_specs, render_worker_block,
                                     specs_for_role)

# Ba bộ mà prompt của chúng phụ thuộc vai. Bộ nào KHÔNG ở đây thì --role không
# đổi gì — và điều đó phải tường minh, vì một bộ thứ tư trở thành nhạy-vai mà
# quên khai sẽ âm thầm đo cấu hình admin.
ROLE_SENSITIVE_SETS = frozenset({"intent", "sop_select", "planner"})

_MCP_DIR = (pathlib.Path(__file__).resolve().parents[2]
            / "mcp-servers" / "odoo")


@functools.lru_cache(maxsize=1)
def _mcp_tool_names() -> tuple[str, ...]:
    """Tên mọi tool MCP đã đăng ký, lấy từ chính module server.

    Fail-closed: thiếu thư mục MCP thì BÁO LỖI, không rơi về một danh sách
    đoán — đo sai im lặng chính là con bọ module này đi đóng.
    """
    if not _MCP_DIR.exists():
        raise RuntimeError(
            f"không tìm thấy {_MCP_DIR} — bộ đo cần tên tool MCP thật để dựng "
            "đúng cấu hình theo vai")
    sys.path.insert(0, str(_MCP_DIR))
    try:
        import server
        return tuple(sorted(server.mcp._tool_manager._tools))
    finally:
        sys.path.remove(str(_MCP_DIR))


@functools.lru_cache(maxsize=1)
def _fake_registry():
    """Tool giả mang ĐÚNG tên tool MCP thật.

    Bộ lọc theo vai chỉ so tên (erp_agent._filter_tools_for_role) và
    skill_role_gap chỉ cần tên để quyết định, nên thân hàm không bao giờ chạy.
    """
    out = []
    for name in _mcp_tool_names():
        def _stub(**kwargs):
            """tool giả — chỉ mang tên, không bao giờ được gọi"""
            raise AssertionError("tool giả của bộ đo không được phép chạy")
        out.append(lc_tool(name)(_stub))
    return tuple(out)


def role_cfg(role_name: str):
    """RoleCfg của vai, theo hồ sơ đang bật (YOUDOO_POLICY_PROFILE) — cùng
    nguồn production dùng. Vai không tồn tại ⇒ KeyError (fail-closed)."""
    return roles.load_profile()[role_name]


def _specs(role_name: str):
    # KHÔNG cache: role_cfg đọc YOUDOO_POLICY_PROFILE lúc gọi, nên cache ở đây
    # sẽ ghim kết quả của hồ sơ đầu tiên cho mọi hồ sơ sau — đúng là hạng lỗi
    # test đổi hồ sơ (test_intent_prompt_khop_cach_production_dung) canh.
    cfg = role_cfg(role_name)
    raw = list(_fake_registry())
    return specs_for_role(load_skill_specs(),
                          _filter_tools_for_role(raw, cfg), raw, cfg)


def intent_prompt(role_name: str) -> str:
    """Prompt router mà vai này thật sự chạy. Vai giữ 0 skill ⇒ khối worker
    rỗng ⇒ render_intent_router_prompt trả prompt gốc."""
    return render_intent_router_prompt(render_worker_block(_specs(role_name)))


def planner_prompt(role_name: str) -> str:
    return planner_prompt_for(role_cfg(role_name))


def valid_sops(role_name: str) -> frozenset:
    return frozenset(s.name for s in _specs(role_name))
