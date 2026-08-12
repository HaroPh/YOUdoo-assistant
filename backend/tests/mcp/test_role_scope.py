"""Giới hạn phạm vi mail theo vai, cưỡng chế TRONG tiến trình MCP.

Đây là lớp dưới tầng agent: nó chặn cả đường gọi thẳng vào cổng MCP (:8004 /
:8005), thứ mà bộ lọc tool ở backend không với tới. role_scope.py cố tình
không import server/odoo_call để test được như hàm thuần."""
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def rs():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import role_scope
    finally:
        sys.path.remove(str(MCP_DIR))
    return role_scope


def test_env_rong_thi_khong_gioi_han(rs):
    """Hợp đồng cho tiến trình admin và cho mọi test MCP hiện có."""
    assert rs.allowed("bat ky", "") is True
    assert rs.allowed("bat ky", None) is True


def test_gia_tri_trong_danh_sach_thi_cho_qua(rs):
    raw = "Shipping: Send by Email"
    assert rs.allowed("Shipping: Send by Email", raw) is True


def test_gia_tri_ngoai_danh_sach_thi_chan(rs):
    raw = "Shipping: Send by Email"
    assert rs.allowed("Invoice: Sending", raw) is False


def test_nhieu_gia_tri_ngan_cach_bang_newline(rs):
    raw = "Shipping: Send by Email\nInvoice: Sending"
    assert rs.allowed("Invoice: Sending", raw) is True
    assert rs.allowed("Sales: Send Quotation", raw) is False


def test_ten_chua_dau_phay_khong_bi_che_doi(rs):
    """Lý do chọn newline làm ký tự ngăn cách thay vì dấu phẩy."""
    raw = "Invoice: Sending, Reminder"
    assert rs.allowed("Invoice: Sending, Reminder", raw) is True
    assert rs.allowed("Invoice: Sending", raw) is False


def test_bo_qua_khoang_trang_thua_va_dong_rong(rs):
    raw = "\n  Shipping: Send by Email  \n\n"
    assert rs.allowed("Shipping: Send by Email", raw) is True
