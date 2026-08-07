r"""MCP server Odoo — chỉ khởi tạo, đăng ký, chạy.

Toàn bộ tool nằm ở tools/ chia theo domain; mọi đường ra Odoo nằm ở
odoo_call.py. Đường cắt theo domain là đường biên SP-2 sẽ dùng để cấp cho mỗi
specialist agent một tập tool hẹp riêng.

Transport: HTTP/SSE tại port MCP_ODOO_PORT (mặc định 8003 — KHÔNG phải
8001 mặc định của D:\Project, cùng gốc codebase, tránh trùng port từng
gây backend Youdoo nhận nhầm request test của D:\Project).
Connect:   http://mcp-odoo:${MCP_ODOO_PORT:-8003}/sse  (từ backend container)
"""
import os
import sys

from mcp.server.fastmcp import FastMCP

from security import forbid_extra_kwargs

mcp = FastMCP("odoo-mcp", host="0.0.0.0",
             port=int(os.environ.get("MCP_ODOO_PORT", "8003")))

# Bí danh module hiện tại thành "server" trong sys.modules TRƯỚC khi import
# tools/* — bắt buộc khi tiến trình được khởi động bằng `python server.py`
# (script chạy trực tiếp nằm ở sys.modules["__main__"], KHÔNG nằm ở
# sys.modules["server"]). Thiếu dòng này: `tools.sales` (module ĐẦU TIÊN
# trong danh sách import bên dưới) chạy `from server import mcp`, không thấy
# "server" trong sys.modules nên Python nhập lại TOÀN BỘ file này lần hai
# như module độc lập ("FastMCP #2") — nhánh nhập lại đó tự nó chạy tiếp
# `from tools import sales, purchase, ...`: sales đang dở dang (đã nằm trong
# sys.modules từ bước ngoài) nên bị bỏ qua, nhưng purchase/inventory/mrp/
# crm/accounting (25 tool) CHƯA đụng tới nên nhập mới hoàn toàn, đăng ký hết
# vào FastMCP #2. Nhập lồng xong, sales.py resolve nốt `from server import
# mcp` của chính nó — nhưng lúc này "server" đã trỏ vào FastMCP #2 (không
# phải #1!) nên 5 tool của sales cũng đăng ký vào #2 → FastMCP #2 đủ 30/30.
# FastMCP #1 — đối tượng biến `mcp` Ở TRÊN, cái mcp.run() cuối file thực sự
# phục vụ — không nhận thêm tool nào cả (mọi module tools/* giờ nằm sẵn
# trong sys.modules nên Python chỉ gán tên, không chạy lại thân file) →
# client MCP thấy ĐÚNG 0 tool. Kết quả xác nhận bằng instrumentation vào
# FastMCP.__init__/ToolManager.add_tool (Task 13, 2026-07-29, xem
# task-13-report.md phần "Bug: python server.py chạy trực tiếp"). setdefault
# (không phải gán thẳng) để không phá vỡ trường hợp file này được import
# bình thường qua `import server` (khi đó Python đã tự đặt đúng khoá
# "server" rồi, vòng import tools/* vốn đã an toàn như comment cũ mô tả).
sys.modules.setdefault("server", sys.modules[__name__])

# Import 6 module tool theo domain — mỗi module tự đăng ký @mcp.tool() của nó
# khi import (side-effect import, không dùng trực tiếp tên module). Vòng import
# server <-> tools.* an toàn: lúc các module này chạy `from server import mcp`,
# tên `mcp` ở trên đã được gán xong trong module server đang khởi tạo dở (VÀ,
# từ dòng sys.modules.setdefault ở trên, "server" đã có mặt trong sys.modules
# dưới đúng tên mà tools/*.py tìm — kể cả khi tiến trình này tự nó là
# __main__).
from tools import sales, purchase, inventory, mrp, crm, accounting, mail  # noqa: E402,F401

# Chặn tool-call kwarg lạ ở mọi write-tool đã đăng ký — chạy 1 lần lúc
# import, sau khi toàn bộ @mcp.tool() ở trên đã đăng ký xong. Tool đăng ký
# thêm sau dòng này sẽ KHÔNG được bọc — mọi @mcp.tool() phải nằm trước.
forbid_extra_kwargs(mcp._tool_manager)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse")
