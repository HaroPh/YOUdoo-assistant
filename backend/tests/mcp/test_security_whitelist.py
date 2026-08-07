"""Whitelist bảo mật cho 2 method mail mới (spec 2026-08-07 §3.2) —
security.py là module Python thuần, import trực tiếp được (khác
test_odoo_tool_boundary.py cần sys.path.insert để import cả gói `server`
qua FastMCP)."""
import importlib.util
import pathlib

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def security():
    path = MCP_DIR / "security.py"
    if not path.exists():
        pytest.skip("chưa có mcp-servers/odoo/security.py")
    spec = importlib.util.spec_from_file_location("security_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_send_mail_duoc_phep_va_phan_loai_create(security):
    assert security.classify_operation("send_mail") == "create"


def test_send_duoc_phep_va_phan_loai_write(security):
    assert security.classify_operation("send") == "write"


def test_send_khong_phan_biet_hoa_thuong(security):
    """classify_operation lowercase method trước khi tra map (security.py
    hiện có, hành vi có sẵn) — khoá test này lại cho 2 method mới."""
    assert security.classify_operation("SEND") == "write"
    assert security.classify_operation("Send_Mail") == "create"
