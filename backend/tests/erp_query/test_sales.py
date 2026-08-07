from src.erp_query.gateway import Gateway
from src.erp_query import sales


class FakeTransport:
    def __init__(self, ret): self.ret = ret; self.calls = []
    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs)); return self.ret


def _gw(rows): return Gateway(FakeTransport(rows))


def test_find_customer_delegates_to_resolve():
    out = sales.find_customer("Azur", gw=_gw([(41, "Azur Interior")]))
    assert out["data"]["matches"][0]["id"] == 41


def test_list_sale_orders_builds_domain_and_envelope():
    rows = [{"name": "S00042", "partner_id": [41, "Azur"], "date_order": "2026-06-01",
             "state": "sale", "amount_total": 320000.0, "delivery_status": "pending"}]
    gw = _gw(rows)
    out = sales.list_sale_orders(state="sale", customer="Azur", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["count"] == 1
    assert out["data"]["rows"][0]["name"] == "S00042"
    assert "S00042" in out["display"]


def test_get_product_price_reads_list_price():
    # Odoo 19 has no context-computed `price` field on product.product, and the
    # read-only gateway can't call a pricelist method → list_price is the price.
    gw = _gw([{"id": 552, "name": "Tủ", "list_price": 320000.0}])
    out = sales.get_product_price(552, partner_id=41, qty=2, gw=gw)
    assert out["data"]["price"] == 320000.0
    assert out["data"]["product_id"] == 552
    fields = gw._t.calls[-1][3]["fields"]
    assert "list_price" in fields


def test_sales_summary_uses_read_group():
    gw = _gw([{"amount_total": 1000.0, "partner_id": [41, "Azur"]}])
    out = sales.sales_summary(period="month", gw=gw)
    assert out["status"] == "success"
    assert gw._t.calls[-1][1] == "read_group"


def test_get_sale_order_detail_includes_state():
    order_rows = [{"id": 7, "name": "S00007", "partner_id": [41, "Azur"],
                   "amount_total": 320000.0, "state": "draft"}]
    line_rows = [{"id": 101, "product_id": [552, "Tủ"], "product_uom_qty": 2.0,
                  "price_unit": 160000.0, "price_subtotal": 320000.0}]

    class TwoCallTransport:
        def __init__(self): self.calls = []
        def call(self, model, method, args, kwargs):
            self.calls.append((model, method, args, kwargs))
            return order_rows if model == "sale.order" else line_rows

    gw = Gateway(TwoCallTransport())
    out = sales.get_sale_order_detail("S00007", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["order"]["state"] == "draft"
    assert out["data"]["lines"][0]["id"] == 101
    order_call = next(c for c in gw._t.calls if c[0] == "sale.order")
    assert "state" in order_call[3]["fields"]
    line_call = next(c for c in gw._t.calls if c[0] == "sale.order.line")
    assert "id" in line_call[3]["fields"]


def test_get_sale_order_detail_includes_dates():
    order_rows = [{"id": 7, "name": "S00007", "partner_id": [41, "Azur"],
                   "amount_total": 320000.0, "state": "draft",
                   "date_order": "2026-07-18 16:55:50",
                   "delivery_status": "pending"}]
    line_rows = []

    class TwoCallTransport:
        def __init__(self): self.calls = []
        def call(self, model, method, args, kwargs):
            self.calls.append((model, method, args, kwargs))
            return order_rows if model == "sale.order" else line_rows

    gw = Gateway(TwoCallTransport())
    out = sales.get_sale_order_detail("S00007", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["order"]["date_order"] == "2026-07-18 16:55:50"
    assert out["data"]["order"]["delivery_status"] == "pending"
    order_call = next(c for c in gw._t.calls if c[0] == "sale.order")
    assert "date_order" in order_call[3]["fields"]
    assert "delivery_status" in order_call[3]["fields"]


def test_get_sale_order_detail_includes_effective_dates():
    order_rows = [{"id": 7, "name": "S00007", "partner_id": [41, "Azur"],
                   "amount_total": 320000.0, "state": "done",
                   "date_order": "2026-07-18 16:55:50",
                   "delivery_status": "full",
                   "commitment_date": False,
                   "effective_date": "2026-07-20 09:12:00"}]
    line_rows = []

    class TwoCallTransport:
        def __init__(self): self.calls = []
        def call(self, model, method, args, kwargs):
            self.calls.append((model, method, args, kwargs))
            return order_rows if model == "sale.order" else line_rows

    gw = Gateway(TwoCallTransport())
    out = sales.get_sale_order_detail("S00007", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["order"]["effective_date"] == "2026-07-20 09:12:00"
    assert out["data"]["order"]["commitment_date"] is False
    order_call = next(c for c in gw._t.calls if c[0] == "sale.order")
    assert "commitment_date" in order_call[3]["fields"]
    assert "effective_date" in order_call[3]["fields"]


class MultiModelTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        return self.responses.get((model, method), [])


def test_get_customer_detail_happy_path():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(41, "Azure Interior")],
        ("res.partner", "search_read"): [{
            "id": 41, "name": "Azure Interior", "email": "contact@azure.example",
            "phone": "0900000000", "vat": "VN123456", "street": "12 Le Loi",
            "city": "HCMC", "property_payment_term_id": [3, "15 Days"]}],
        ("sale.order", "search_read"): [{"id": 1}, {"id": 2}, {"id": 3}],
    })
    out = sales.get_customer_detail("Azure", gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["so_count"] == 3
    assert out["data"]["partner"]["email"] == "contact@azure.example"
    assert "contact@azure.example" in out["display"]
    assert "0900000000" in out["display"]
    assert "bank_ids" not in out["data"]["partner"]
    partner_call = next(c for c in t.calls if c[0] == "res.partner" and c[1] == "search_read")
    assert "bank_ids" not in partner_call[3]["fields"]


def test_get_customer_detail_ambiguous():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(1, "Công ty A Miền Bắc"), (2, "Công ty A Miền Nam")],
    })
    out = sales.get_customer_detail("Công ty A", gw=Gateway(t))
    assert out["status"] == "error"
    assert "nhiều" in out["display"].lower()


def test_get_customer_detail_not_found():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({("res.partner", "name_search"): []})
    out = sales.get_customer_detail("Không tồn tại", gw=Gateway(t))
    assert out["status"] == "error"


def test_get_customer_detail_missing_fields_render_dash():
    from src.erp_query.gateway import Gateway
    t = MultiModelTransport({
        ("res.partner", "name_search"): [(9, "Acme Corporation")],
        ("res.partner", "search_read"): [{
            "id": 9, "name": "Acme Corporation", "email": False, "phone": False,
            "vat": False, "street": False, "city": False,
            "property_payment_term_id": False}],
        ("sale.order", "search_read"): [],
    })
    out = sales.get_customer_detail("Acme", gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["so_count"] == 0
    assert "—" in out["display"]
