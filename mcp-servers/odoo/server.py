"""MCP server Odoo — chỉ khởi tạo, đăng ký, chạy.

Toàn bộ tool nằm ở tools/ chia theo domain; mọi đường ra Odoo nằm ở
odoo_call.py. Đường cắt theo domain là đường biên SP-2 sẽ dùng để cấp cho mỗi
specialist agent một tập tool hẹp riêng.

Transport: HTTP/SSE tại port 8001
Connect:   http://mcp-odoo:8001/sse  (từ backend container)
"""
from mcp.server.fastmcp import FastMCP

from security import forbid_extra_kwargs

mcp = FastMCP("odoo-mcp", host="0.0.0.0", port=8001)

# Import 6 module tool theo domain — mỗi module tự đăng ký @mcp.tool() của nó
# khi import (side-effect import, không dùng trực tiếp tên module). Vòng import
# server <-> tools.* an toàn: lúc các module này chạy `from server import mcp`,
# tên `mcp` ở trên đã được gán xong trong module server đang khởi tạo dở.
from tools import sales, purchase, inventory, mrp, crm, accounting  # noqa: E402,F401

# Chặn tool-call kwarg lạ ở mọi write-tool đã đăng ký — chạy 1 lần lúc
# import, sau khi toàn bộ @mcp.tool() ở trên đã đăng ký xong. Tool đăng ký
# thêm sau dòng này sẽ KHÔNG được bọc — mọi @mcp.tool() phải nằm trước.
forbid_extra_kwargs(mcp._tool_manager)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse")
