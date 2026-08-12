"""server.py phải bind 127.0.0.1 theo mặc định, không phải 0.0.0.0.

0.0.0.0 khiến ba cổng MCP (8003/8004/8005) lộ ra mạng LAN. Mỗi tiến trình
nắm credential ghi của một vai, và cổng không có xác thực — nên bind rộng là
đường tấn công trực tiếp mà toàn bộ Task 4 đang đi bịt.

Quét NGUỒN chứ không khởi động server: test không được chạm hạ tầng sống."""
import pathlib
import re

SERVER_PY = (pathlib.Path(__file__).resolve().parents[3]
             / "mcp-servers" / "odoo" / "server.py")


def test_khong_hardcode_0_0_0_0():
    src = SERVER_PY.read_text(encoding="utf-8")
    dong_code = [d for d in src.splitlines()
                 if '"0.0.0.0"' in d or "'0.0.0.0'" in d]
    assert not dong_code, (
        "server.py không được hardcode 0.0.0.0 — dùng "
        'os.environ.get("MCP_ODOO_HOST", "127.0.0.1"):\n' + "\n".join(dong_code))


def test_mac_dinh_la_localhost():
    src = SERVER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"""MCP_ODOO_HOST["']\s*,\s*["']127\.0\.0\.1["']""", src), (
        "phải có mặc định 127.0.0.1 cho MCP_ODOO_HOST")
