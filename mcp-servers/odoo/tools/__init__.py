"""Gói tool MCP Odoo, chia theo domain (spec SP-1B §3c task 7).

Mỗi module con (sales/purchase/inventory/mrp/crm/accounting) tự đăng ký các
tool MCP của mình khi được import — server.py import cả 6 module này để
kích hoạt đăng ký, không tool nào định nghĩa ở đây."""
