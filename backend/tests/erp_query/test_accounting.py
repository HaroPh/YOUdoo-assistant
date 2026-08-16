from src.erp_query.gateway import Gateway
from src.erp_query import accounting


class FakeTransport:
    def __init__(self, ret): self.ret = ret; self.calls = []
    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs)); return self.ret


def _gw(rows): return Gateway(FakeTransport(rows))


def test_list_invoices_builds_move_type_domain():
    rows = [{"name": "INV/2026/0042", "partner_id": [41, "Azur"], "invoice_date": "2026-06-01",
             "amount_total": 320000.0, "amount_residual": 0.0, "payment_state": "paid"}]
    gw = _gw(rows)
    out = accounting.list_invoices("out_invoice", payment_state="paid", gw=gw)
    assert out["data"]["count"] == 1
    assert ["move_type", "=", "out_invoice"] in gw._t.calls[0][2][0]
    assert ["state", "=", "posted"] in gw._t.calls[0][2][0]


def test_get_overdue_invoices_domain():
    gw = _gw([])
    out = accounting.get_overdue_invoices(gw=gw)
    assert out["data"]["count"] == 0
    dom = gw._t.calls[0][2][0]
    assert ["payment_state", "in", ["not_paid", "partial"]] in dom


def test_get_overdue_invoices_capped_false_below_limit():
    rows = [{"name": "INV/2026/0001", "partner_id": [1, "Acme"],
             "invoice_date_due": "2026-08-01", "amount_residual": 100.0}]
    out = accounting.get_overdue_invoices(limit=50, gw=_gw(rows))
    assert out["data"]["capped"] is False
    assert "có thể còn nhiều hơn" not in out["display"]


def test_get_overdue_invoices_capped_true_at_limit():
    rows = [{"name": f"INV/2026/{i:04d}", "partner_id": [1, "Acme"],
             "invoice_date_due": "2026-08-01", "amount_residual": 100.0}
            for i in range(5)]
    out = accounting.get_overdue_invoices(limit=5, gw=_gw(rows))
    assert out["data"]["capped"] is True
    assert "có thể còn nhiều hơn — đã đạt giới hạn 5 dòng" in out["display"]


class PartnerBalanceTransport:
    """Đường-2 call cùng model account.move (AR rồi AP) — phân biệt bằng
    domain (move_type), không phải thứ tự gọi."""
    def __init__(self, partner_rows, ar_rows, ap_rows):
        self.partner_rows = partner_rows
        self.ar_rows = ar_rows
        self.ap_rows = ap_rows
        self.calls = []

    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        if model == "res.partner":
            return self.partner_rows
        domain = args[0]
        if ["move_type", "=", "out_invoice"] in domain:
            return self.ar_rows
        return self.ap_rows


def test_get_partner_balance_not_found():
    gw = Gateway(PartnerBalanceTransport([], [], []))
    out = accounting.get_partner_balance("Nobody", gw=gw)
    assert "Không tìm thấy" in out["display"]


def test_get_partner_balance_duplicate_name():
    partners = [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Acme Corp"}]
    gw = Gateway(PartnerBalanceTransport(partners, [], []))
    out = accounting.get_partner_balance("Acme", gw=gw)
    assert "nhiều đối tác" in out["display"]


def test_get_partner_balance_ar_only():
    partners = [{"id": 15, "name": "Azure Interior"}]
    ar = [{"partner_id": [15, "Azure Interior"], "amount_residual": 66107.0}]
    gw = Gateway(PartnerBalanceTransport(partners, ar, []))
    out = accounting.get_partner_balance("Azure Interior", gw=gw)
    assert out["data"]["receivable"] == 66107.0
    assert out["data"]["payable"] == 0.0
    assert "phải thu" in out["display"]
    assert "phải trả" not in out["display"]


def test_get_partner_balance_ap_only():
    partners = [{"id": 10, "name": "Gemini Furniture"}]
    ap = [{"partner_id": [10, "Gemini Furniture"], "amount_residual": 1244.77}]
    gw = Gateway(PartnerBalanceTransport(partners, [], ap))
    out = accounting.get_partner_balance("Gemini Furniture", gw=gw)
    assert out["data"]["payable"] == 1244.77
    assert out["data"]["receivable"] == 0.0
    assert "phải trả" in out["display"]
    assert "phải thu" not in out["display"]


def test_get_partner_balance_both_sides_shown_not_netted():
    partners = [{"id": 20, "name": "Dual Corp"}]
    ar = [{"partner_id": [20, "Dual Corp"], "amount_residual": 500.0}]
    ap = [{"partner_id": [20, "Dual Corp"], "amount_residual": 200.0}]
    gw = Gateway(PartnerBalanceTransport(partners, ar, ap))
    out = accounting.get_partner_balance("Dual Corp", gw=gw)
    assert out["data"]["receivable"] == 500.0
    assert out["data"]["payable"] == 200.0
    assert "phải thu" in out["display"] and "phải trả" in out["display"]


def test_get_partner_balance_no_debt():
    partners = [{"id": 30, "name": "Clean Co"}]
    gw = Gateway(PartnerBalanceTransport(partners, [], []))
    out = accounting.get_partner_balance("Clean Co", gw=gw)
    assert "không còn công nợ" in out["display"]


def test_find_posted_invoice_not_found():
    gw = _gw([])
    out = accounting.find_posted_invoice("INV/2026/99999", gw=gw)
    assert out["status"] == "error"
    assert "Không tìm thấy" in out["display"]


def test_find_posted_invoice_not_yet_posted():
    gw = _gw([{"id": 68, "name": "INV/2026/00017", "state": "draft",
               "partner_id": [15, "Azure Interior"], "amount_total": 70.0}])
    out = accounting.find_posted_invoice("INV/2026/00017", gw=gw)
    assert out["status"] == "error"
    assert "chưa phát hành" in out["display"]


def test_find_posted_invoice_happy():
    gw = _gw([{"id": 68, "name": "INV/2026/00017", "state": "posted",
               "partner_id": [15, "Azure Interior"], "amount_total": 70.0}])
    out = accounting.find_posted_invoice("INV/2026/00017", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["invoice"]["id"] == 68


class TwoModelTransport:
    """account.move rồi account.move.line — phân biệt bằng tên model."""
    def __init__(self, move_rows, line_rows):
        self.move_rows = move_rows
        self.line_rows = line_rows
        self.calls = []

    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        return self.move_rows if model == "account.move" else self.line_rows


_DRAFT = {"id": 105, "name": False, "partner_id": [41, "Acme Corporation"],
          "invoice_date": "2026-08-06", "amount_total": 17520.0,
          "amount_residual": 17520.0, "move_type": "in_invoice", "state": "draft"}
_LINE = {"product_id": [7, "[FURN_0789] Individual Workplace"],
         "quantity": 20.0, "price_subtotal": 17520.0}


def test_get_invoice_detail_loc_dong_product():
    """Bẫy thật đo trên Odoo 2026-08-06: account.move.line của một hóa đơn
    trả về CẢ dòng 'payment_term' (đối ứng phải thu/phải trả, 0 đồng).
    Thiếu bộ lọc display_type thì bảng tóm tắt có một dòng rác 0 đồng."""
    t = TwoModelTransport([_DRAFT], [_LINE])
    out = accounting.get_invoice_detail(105, gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["invoice"]["id"] == 105
    assert out["data"]["lines"] == [_LINE]
    line_domain = t.calls[1][2][0]
    assert ["move_id", "=", 105] in line_domain
    assert ["display_type", "=", "product"] in line_domain


def test_get_invoice_detail_khong_thay_thi_bao_loi():
    out = accounting.get_invoice_detail(999, gw=_gw([]))
    assert out["status"] == "error"
    assert "999" in out["display"]


def test_find_draft_invoices_domain_va_tra_danh_sach():
    """Trả DANH SÁCH: hóa đơn nháp chưa có số nên nhiều bản cùng đối tác là
    chuyện thường (đo thật: 5 bản nháp cùng 'Acme', 4 trùng số tiền)."""
    t = TwoModelTransport([_DRAFT, {**_DRAFT, "id": 99}], [])
    out = accounting.find_draft_invoices("Acme", gw=Gateway(t))
    assert out["data"]["count"] == 2
    dom = t.calls[0][2][0]
    assert ["state", "=", "draft"] in dom
    assert ["partner_id.name", "ilike", "Acme"] in dom


def test_find_draft_invoices_loc_them_khi_co_amount_va_date():
    t = TwoModelTransport([_DRAFT], [])
    accounting.find_draft_invoices("Acme", amount=140.0,
                                   invoice_date="2026-08-06", gw=Gateway(t))
    dom = t.calls[0][2][0]
    assert ["amount_total", "=", 140.0] in dom
    assert ["invoice_date", "=", "2026-08-06"] in dom


def test_find_draft_invoices_rong_thi_bao_loi():
    out = accounting.find_draft_invoices("Không Tồn Tại", gw=_gw([]))
    assert out["status"] == "error"


def test_find_open_invoices_chi_lay_con_no():
    """Hóa đơn đã trả hết không còn gì để thanh toán — đưa vào danh sách
    chọn chỉ gây nhiễu."""
    posted = {**_DRAFT, "id": 100, "name": "INV/2026/00028",
              "state": "posted", "move_type": "out_invoice",
              "amount_total": 350.0, "amount_residual": 350.0}
    t = TwoModelTransport([posted], [])
    out = accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t))
    assert out["data"]["count"] == 1
    dom = t.calls[0][2][0]
    assert ["state", "=", "posted"] in dom
    assert ["payment_state", "in", ["not_paid", "partial"]] in dom


def test_find_open_invoices_nhan_ca_invoice_ref_lan_partner_name():
    """register_payment nhận CẢ HAI — đường partner_name mơ hồ y hệt
    post_invoice nên phải xử lý cùng cách."""
    t = TwoModelTransport([], [])
    accounting.find_open_invoices(invoice_ref="INV/2026/00028", gw=Gateway(t))
    assert ["name", "=", "INV/2026/00028"] in t.calls[0][2][0]
    t2 = TwoModelTransport([], [])
    accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t2))
    assert ["partner_id.name", "ilike", "Acme"] in t2.calls[0][2][0]


def test_find_open_invoices_amount_loc_theo_so_du():
    """amount lọc theo amount_residual, khớp domain resolve của chính nhánh
    partner_name-only của mcp-servers/odoo/tools/accounting.py::register_payment
    (dòng domain.append(["amount_residual", "=", amount])) — KHÔNG phải
    amount_total, vì register_payment luôn thanh toán ĐỦ số dư còn lại,
    amount chỉ dùng để phân biệt hóa đơn theo số tiền SẼ TRẢ."""
    t = TwoModelTransport([], [])
    accounting.find_open_invoices(partner_name="Acme", amount=210.0, gw=Gateway(t))
    dom = t.calls[0][2][0]
    assert ["amount_residual", "=", 210.0] in dom
    assert ["amount_total", "=", 210.0] not in dom


def test_find_open_invoices_bao_gom_ca_hoa_don_mua():
    """KHÔNG dùng lại find_posted_invoice được: hàm đó lọc cứng
    move_type='out_invoice', trong khi register_payment phục vụ cả
    in_invoice (mình trả NCC)."""
    t = TwoModelTransport([], [])
    accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t))
    dom = t.calls[0][2][0]
    move_type_cond = [c for c in dom if c[0] == "move_type"][0]
    assert "in_invoice" in move_type_cond[2]
