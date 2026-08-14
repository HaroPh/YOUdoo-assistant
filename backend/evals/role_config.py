"""Dựng prompt theo VAI cho bộ đo eval — bằng chính hàm production dùng.

Vì sao cần: production lọc cả tập skill lẫn tập tool theo vai (graph.py,
planner_prompt_for), còn bộ đo trước đây luôn dựng từ tập ĐẦY ĐỦ. Đo
2026-08-14: vai kế toán chạy worker block RỖNG (0/3 skill) trong khi bộ đo đo
3/3 — nên mọi kết luận "cấu hình còn khoẻ" chỉ đúng cho vai admin.

skill_role_gap cần ĐỐI TƯỢNG tool, mà bộ đo không có kết nối MCP. Giải: import
module server của mcp-servers/odoo (đã kiểm: cho ra đủ 35 tool, không cần MCP
sống, không chạm Odoo — get_uid() là lười) rồi dựng tool giả mang đúng TÊN và
đúng CHỮ KÝ của tool thật. Chỉ thân hàm là giả, nên registry này dựng được cả
build_graph() thật — đó là điều kiện để lưới đỡ trong
tests/jobs/test_eval_role_config.py so được prompt bộ đo với prompt production
thật sự dựng, thay vì so với một bản chép tay.
"""
import functools
import inspect
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
def _mcp_tool_fns() -> tuple[tuple[str, object], ...]:
    """(tên, hàm) của mọi tool MCP đã đăng ký, lấy từ chính module server.

    Lấy cả HÀM chứ không chỉ tên vì tool giả phải mang đúng CHỮ KÝ thật: bộ
    lọc theo vai chỉ cần tên, nhưng build_skill_tools (skill_loader) đối chiếu
    các trường nội suy trong `confirm` với tham số thật của tool, nên tool giả
    mang chữ ký sai làm build_graph() ném SkillManifestError.

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
        return tuple((name, t.fn) for name, t
                     in sorted(server.mcp._tool_manager._tools.items()))
    except Exception as e:  # noqa: BLE001 — gói MỌI nguyên nhân vào một lỗi nói rõ
        # Nguyên nhân hay gặp nhất KHÔNG phải thiếu thư mục (đã chặn ở trên) mà
        # là thiếu biến môi trường: mcp-servers/odoo/config.py dùng
        # os.environ[...] nên bật ra KeyError('ODOO_URL') trần, không nói gì về
        # việc bộ đo đang cần gì. `.env` bị gitignore nên worktree/CI sạch là
        # đúng trường hợp đó.
        raise RuntimeError(
            f"không nạp được registry tool MCP từ {_MCP_DIR} ({type(e).__name__}: "
            f"{e}) — bộ đo cần ODOO_URL/ODOO_DB/ODOO_USERNAME/ODOO_PASSWORD "
            f"trong môi trường để import được, dù nó KHÔNG gọi Odoo") from e
    finally:
        sys.path.remove(str(_MCP_DIR))


@functools.lru_cache(maxsize=1)
def _fake_registry():
    """Tool giả mang ĐÚNG tên VÀ ĐÚNG chữ ký của tool MCP thật.

    Chỉ thân hàm là giả — nó ném nếu bị gọi, vì bộ đo không có kết nối MCP.
    Chữ ký chép từ hàm thật (`__signature__`) nên args_schema langchain suy ra
    trùng khít tool thật, đủ để dựng được build_graph() thật. Trước đây stub là
    `def _stub(**kwargs)` nên mọi tool chỉ có tham số 'kwargs', và bất kỳ ai
    dựng graph thật với registry này đều ăn SkillManifestError.
    """
    out = []
    for name, real_fn in _mcp_tool_fns():
        def _stub(*args, **kwargs):
            """tool giả — chỉ mang tên và chữ ký, không bao giờ được gọi"""
            raise AssertionError("tool giả của bộ đo không được phép chạy")
        _stub.__signature__ = inspect.signature(real_fn)
        _stub.__annotations__ = dict(getattr(real_fn, "__annotations__", {}))
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
    specs = load_skill_specs()
    # Vai không lọc (admin) TRẢ SỚM, KHÔNG đụng registry MCP: skill_role_gap
    # trả None vô điều kiện khi allowed_tools() is None, nên registry hoàn toàn
    # không được dùng ở đường này. Dựng nó vẫn kéo theo `import server`, tức
    # đường admin — đường đang chạy tốt và có 6 baseline — sẽ CHẾT nếu tiến
    # trình eval thiếu ODOO_* trong môi trường hoặc thiếu cây mcp-servers/.
    # Trước đợt này eval_intent không có phụ thuộc nào như vậy; đừng thêm nó
    # cho một đường không cần tới.
    if cfg.allowed_tools() is None:
        return list(specs)
    raw = list(_fake_registry())
    return specs_for_role(specs, _filter_tools_for_role(raw, cfg), raw, cfg)


def intent_prompt(role_name: str) -> str:
    """Prompt router mà vai này thật sự chạy. Vai giữ 0 skill ⇒ khối worker
    rỗng ⇒ render_intent_router_prompt trả prompt gốc."""
    return render_intent_router_prompt(render_worker_block(_specs(role_name)))


def planner_prompt(role_name: str) -> str:
    return planner_prompt_for(role_cfg(role_name))


def valid_sops(role_name: str) -> frozenset:
    return frozenset(s.name for s in _specs(role_name))
