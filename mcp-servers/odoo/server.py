"""MCP server Odoo — chỉ khởi tạo, đăng ký, chạy.

Toàn bộ tool nằm ở tools/ chia theo domain; mọi đường ra Odoo nằm ở
odoo_call.py. Đường cắt theo domain là đường biên SP-2 sẽ dùng để cấp cho mỗi
specialist agent một tập tool hẹp riêng.

Transport: HTTP/SSE tại port 8001
Connect:   http://mcp-odoo:8001/sse  (từ backend container)
"""
import sys

from mcp.server.fastmcp import FastMCP

from security import forbid_extra_kwargs

mcp = FastMCP("odoo-mcp", host="0.0.0.0", port=8001)

# Bí danh module hiện tại thành "server" trong sys.modules TRƯỚC khi import
# tools/* — bắt buộc khi tiến trình được khởi động bằng `python server.py`
# (script chạy trực tiếp nằm ở sys.modules["__main__"], KHÔNG nằm ở
# sys.modules["server"]). Thiếu dòng này, `from server import mcp` bên trong
# mỗi module tools/*.py không tìm thấy "server" trong sys.modules nên import
# lại TOÀN BỘ file này như một module thứ hai, độc lập, với một FastMCP() —
# và vì tools.sales (module TRIGGER ra vòng import lại này) đã nằm dở dang
# trong sys.modules ngay khi việc import nó bắt đầu, nhánh nhập lại đó bỏ qua
# sales nhưng vẫn nhập purchase/inventory/mrp/crm/accounting đầy đủ — kết quả
# quan sát thực nghiệm (Task 13, 2026-07-29): HAI đối tượng FastMCP tồn tại
# trong cùng tiến trình, cái phục vụ request thật (id khác cái mcp ở trên)
# thiếu tool của sales.py và ngẫu nhiên theo thứ tự import mà có thể trống
# gần hết — client MCP thấy 0 tool dù tool_manager của module NÀY có đủ.
# Chuỗi nhân quả xác nhận bằng in id(mcp)/đếm tool ở cả hai điểm nhập.
# setdefault (không phải gán thẳng) để không phá vỡ trường hợp file này được
# import bình thường qua `import server` (khi đó Python đã tự đặt đúng khoá
# "server" rồi, vòng import tools/* vốn đã an toàn như comment cũ mô tả).
sys.modules.setdefault("server", sys.modules[__name__])

# Import 6 module tool theo domain — mỗi module tự đăng ký @mcp.tool() của nó
# khi import (side-effect import, không dùng trực tiếp tên module). Vòng import
# server <-> tools.* an toàn: lúc các module này chạy `from server import mcp`,
# tên `mcp` ở trên đã được gán xong trong module server đang khởi tạo dở (VÀ,
# từ dòng sys.modules.setdefault ở trên, "server" đã có mặt trong sys.modules
# dưới đúng tên mà tools/*.py tìm — kể cả khi tiến trình này tự nó là
# __main__).
from tools import sales, purchase, inventory, mrp, crm, accounting  # noqa: E402,F401

# Chặn tool-call kwarg lạ ở mọi write-tool đã đăng ký — chạy 1 lần lúc
# import, sau khi toàn bộ @mcp.tool() ở trên đã đăng ký xong. Tool đăng ký
# thêm sau dòng này sẽ KHÔNG được bọc — mọi @mcp.tool() phải nằm trước.
forbid_extra_kwargs(mcp._tool_manager)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse")
