"""Bất biến bảo vệ cú chẻ MCP server theo domain (spec SP-1B §3c).

Chẻ file là lúc dễ đánh rơi một guard bảo mật nhất: một tool được chuyển sang
module mới mà quên đi qua odoo_call.odoo() sẽ vòng qua CẢ NĂM cổng bảo mật
(xác thực, rate limit, denylist, audit chain, event log) mà không ai thấy —
nó vẫn chạy đúng, chỉ là không được kiểm.

Test này duyệt registry FastMCP thật, lấy mã nguồn từng tool đã đăng ký, và
khẳng định không tool nào nói chuyện thẳng với Odoo.
"""
import inspect
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"

# Hai cái tên này là đường ra Odoo trực tiếp. Chỉ odoo_call.py được nhắc tới.
CAM = ("ServerProxy", "execute_kw")


@pytest.fixture(scope="module")
def cac_tool():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
    except ImportError as exc:
        pytest.skip(f"không import được server.py: {exc}")
    finally:
        sys.path.remove(str(MCP_DIR))
    reg = getattr(server.mcp, "_tool_manager", None)
    tools = getattr(reg, "_tools", None) if reg else None
    if not tools:
        pytest.skip("không đọc được registry FastMCP — cấu trúc nội bộ đã đổi")
    return tools


def test_khong_tool_nao_goi_thang_odoo(cac_tool):
    vi_pham = []
    for ten, tool in cac_tool.items():
        fn = getattr(tool, "fn", None) or getattr(tool, "func", None)
        if fn is None:
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        for cam in CAM:
            if cam in src:
                vi_pham.append(f"{ten} nhắc {cam!r} trực tiếp")
    assert not vi_pham, (
        "mọi đường ra Odoo phải qua odoo_call.odoo():\n" + "\n".join(vi_pham))


def test_chi_odoo_call_duoc_nhac_ServerProxy():
    """Quét file, không quét registry — bắt được cả tool chưa đăng ký."""
    vi_pham = []
    for path in sorted((MCP_DIR / "tools").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for cam in CAM:
            if cam in text:
                vi_pham.append(f"{path.name} nhắc {cam!r}")
    assert not vi_pham, "\n".join(vi_pham)
