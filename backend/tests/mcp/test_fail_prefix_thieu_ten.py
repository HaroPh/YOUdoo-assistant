# backend/tests/mcp/test_fail_prefix_thieu_ten.py
"""Ghim hành vi tiền tố fail() khi tham số TÊN rỗng (Fix round 1, finding
Minor sau review 2026-08-15-tool-try-coverage).

Bối cảnh: post_invoice đã có nhánh rẽ khi partner_name rỗng (dùng ID nếu
có, câu trơn nếu không) từ đợt sửa 12-tool-không-try. Review chỉ ra CÙNG
tình huống (tham số tên optional + tham số ID thay thế) tồn tại ở 5 tool
khác — inventory_adjustment, internal_transfer, scrap_product, create_rfq,
create_quotation — và không được xử lý cùng cách: khi caller chỉ truyền ID,
tên rỗng lọt thẳng vào f-string, để lại HAI dấu cách liền nhau và KHÔNG có
gì định danh chứng từ trong câu báo lỗi.

Test này gọi thẳng hàm đã đăng ký trong registry FastMCP với odoo()
monkeypatch để raise ngay ở lần gọi đầu — cùng khuôn
tests/mcp/test_close_activity_tool.py — rồi khẳng định CẢ HAI đường xuống
cấp: chỉ có ID (phải thấy ID trong display) và không có gì cả (phải là câu
trơn, không placeholder rỗng). Không kiểm 'name present' — nhánh đó vốn đã
đúng từ đầu."""
import json
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def server_mod():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server  # noqa: F401 — đăng ký mọi tool
    finally:
        sys.path.remove(str(MCP_DIR))
    return sys.modules["server"]


def _tool_fn(server_mod, ten):
    return server_mod.mcp._tool_manager._tools[ten].fn


def _hong_ngay(*a, **k):
    raise Exception("odoo hỏng — chi tiết không được lộ ra display")


def _vo_hieu_hoa_odoo(monkeypatch, *ten_module: str) -> None:
    """Patch `odoo` ở TỪNG module được liệt kê, không chỉ module tool.

    `from odoo_call import odoo` tạo một binding RIÊNG trong namespace của
    mỗi module import nó — patch tools.inventory.odoo không hề chạm
    helpers.odoo (5 helper resolve dùng chung — _resolve_partner,
    _resolve_product — sống ở helpers.py và giữ binding odoo() CỦA RIÊNG
    NÓ). Nhánh 'không tên không ID' của cả 5 tool ở file này đi qua đúng
    những helper đó, nên bỏ sót helpers ở đây sẽ khiến test gọi THẬT ra Odoo
    thay vì hỏng như ý — đã tự bắt được lỗi này khi chạy lần đầu (kết quả
    trả về là dữ liệu khách/sản phẩm CÓ THẬT, không phải exception giả)."""
    for ten in ten_module:
        monkeypatch.setattr(sys.modules[ten], "odoo", _hong_ngay)


def _khong_co_loi_hinh_thuc(display: str) -> None:
    """Hai bất biến bắt buộc trên MỌI nhánh: không dấu cách đôi (dấu vết của
    một placeholder rỗng còn sót lại), không chữ 'None' (dấu vết của tham số
    thiếu bị nội suy thẳng vào chuỗi)."""
    assert "  " not in display, f"dấu cách đôi trong display: {display!r}"
    assert "None" not in display, f"chữ 'None' lọt vào display: {display!r}"


# ─── inventory_adjustment (tools.inventory) ──────────────────────────────

def test_inventory_adjustment_chi_co_id_thi_neu_id(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "inventory_adjustment")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(new_qty=5.0, product_name="", product_id=42))
    assert out["ok"] is False
    assert "42" in out["display"]
    _khong_co_loi_hinh_thuc(out["display"])


def test_inventory_adjustment_khong_ten_khong_id_thi_cau_tron(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "inventory_adjustment")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(new_qty=5.0, product_name="", product_id=0))
    assert out["ok"] is False
    assert out["display"].startswith("Lỗi khi điều chỉnh tồn kho —")
    _khong_co_loi_hinh_thuc(out["display"])


# ─── internal_transfer (tools.inventory) ─────────────────────────────────

def test_internal_transfer_chi_co_id_thi_neu_id(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "internal_transfer")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(product_name="", qty=1.0, from_location="A",
                        to_location="B", product_id=7))
    assert out["ok"] is False
    assert "7" in out["display"]
    _khong_co_loi_hinh_thuc(out["display"])


def test_internal_transfer_khong_ten_khong_id_thi_cau_tron(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "internal_transfer")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(product_name="", qty=1.0, from_location="A",
                        to_location="B", product_id=0))
    assert out["ok"] is False
    assert out["display"].startswith("Lỗi khi chuyển kho —")
    _khong_co_loi_hinh_thuc(out["display"])


# ─── scrap_product (tools.inventory) ─────────────────────────────────────

def test_scrap_product_chi_co_id_thi_neu_id(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "scrap_product")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(product_name="", qty=1.0, product_id=9))
    assert out["ok"] is False
    assert "9" in out["display"]
    _khong_co_loi_hinh_thuc(out["display"])


def test_scrap_product_khong_ten_khong_id_thi_cau_tron(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "scrap_product")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.inventory", "helpers")
    out = json.loads(fn(product_name="", qty=1.0, product_id=0))
    assert out["ok"] is False
    assert out["display"].startswith("Lỗi khi ghi nhận phế liệu —")
    _khong_co_loi_hinh_thuc(out["display"])


# ─── create_rfq (tools.purchase) ─────────────────────────────────────────

def test_create_rfq_chi_co_id_thi_neu_id(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "create_rfq")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.purchase", "helpers")
    out = json.loads(fn(supplier_name="", lines=[{"product_id": 1, "qty": 1}],
                        partner_id=13))
    assert out["ok"] is False
    assert "13" in out["display"]
    _khong_co_loi_hinh_thuc(out["display"])


def test_create_rfq_khong_ten_khong_id_thi_cau_tron(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "create_rfq")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.purchase", "helpers")
    out = json.loads(fn(supplier_name="", lines=[{"product_id": 1, "qty": 1}],
                        partner_id=0))
    assert out["ok"] is False
    assert out["display"].startswith("Lỗi khi tạo RFQ —")
    _khong_co_loi_hinh_thuc(out["display"])


# ─── create_quotation (tools.sales) ──────────────────────────────────────

def test_create_quotation_chi_co_id_thi_neu_id(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "create_quotation")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.sales", "helpers")
    out = json.loads(fn(partner_name="", lines=[{"product_id": 1, "qty": 1}],
                        partner_id=21))
    assert out["ok"] is False
    assert "21" in out["display"]
    _khong_co_loi_hinh_thuc(out["display"])


def test_create_quotation_khong_ten_khong_id_thi_cau_tron(server_mod, monkeypatch):
    fn = _tool_fn(server_mod, "create_quotation")
    _vo_hieu_hoa_odoo(monkeypatch, "tools.sales", "helpers")
    out = json.loads(fn(partner_name="", lines=[{"product_id": 1, "qty": 1}],
                        partner_id=0))
    assert out["ok"] is False
    assert out["display"].startswith("Lỗi khi tạo báo giá —")
    _khong_co_loi_hinh_thuc(out["display"])
