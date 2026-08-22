"""Sales bounded context — business read functions. Domains live here, in Python."""
from datetime import datetime, timezone

from .envelope import ok, err, fail_read
from .gateway import default_gateway
from .resolve import resolve_entity, _resolve_single


def _period_from(period):
    t = datetime.now(timezone.utc)
    if period == "month":
        return t.replace(day=1).strftime("%Y-%m-%d")
    if period == "quarter":
        return t.replace(month=((t.month - 1) // 3) * 3 + 1, day=1).strftime("%Y-%m-%d")
    if period == "year":
        return t.replace(month=1, day=1).strftime("%Y-%m-%d")
    return None


def find_customer(name, *, gw=None):
    return resolve_entity("res.partner", name, gw=gw)


def list_sale_orders(state=None, customer=None, date_from=None, date_to=None, limit=50, *, gw=None):
    gw = gw or default_gateway()
    domain = []
    if state:
        domain.append(["state", "=", state])
    if customer:
        domain.append(["partner_id.name", "ilike", customer])
    if date_from:
        domain.append(["date_order", ">=", date_from + " 00:00:00"])
    if date_to:
        domain.append(["date_order", "<=", date_to + " 23:59:59"])
    try:
        rows = gw.search_read("sale.order", domain,
                              ["name", "partner_id", "date_order", "state", "amount_total",
                               "delivery_status"], order="date_order desc", limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("list_sale_orders",
                         f"Lỗi tra cứu đơn bán — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
    if not rows:
        return ok({"rows": [], "count": 0}, "Không tìm thấy đơn bán nào phù hợp.")
    lines = [f"{r['name']} | {(r['partner_id'] or [0, 'N/A'])[1]} | {r['state']} "
             f"| {r['amount_total']:,.0f}" for r in rows]
    return ok({"rows": rows, "count": len(rows)},
              f"{len(rows)} đơn bán:\n" + "\n".join(lines))


def get_sale_order_detail(ref, *, gw=None):
    gw = gw or default_gateway()
    try:
        orders = gw.search_read("sale.order", [["name", "=", ref]],
                                ["id", "name", "partner_id", "amount_total", "state",
                                 "date_order", "delivery_status",
                                 "commitment_date", "effective_date"], limit=2)
        if not orders:
            return err(f"Không tìm thấy đơn '{ref}'.")
        if len(orders) > 1:
            return err(f"Có nhiều đơn tên '{ref}'.")
        o = orders[0]
        lines = gw.search_read("sale.order.line", [["order_id", "=", o["id"]]],
                               ["id", "product_id", "product_uom_qty", "price_unit", "price_subtotal"],
                               order="id asc", limit=100)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("get_sale_order_detail",
                         f"Lỗi tra cứu chi tiết đơn — không lấy được dữ "
                         f"liệu. Nếu lặp lại, báo quản trị viên.", e)
    body = "\n".join(f"  {(l['product_id'] or [0, 'N/A'])[1]} | SL {l['product_uom_qty']:.1f} "
                     f"| {l['price_unit']:,.0f} | {l['price_subtotal']:,.0f}" for l in lines)
    return ok({"order": o, "lines": lines},
              f"Đơn {o['name']} | {(o['partner_id'] or [0, 'N/A'])[1]} "
              f"| Tổng {o['amount_total']:,.0f}\n{body}")


def get_product_price(product_id, partner_id=None, qty=1.0, *, gw=None):
    """Sell price = the product's `list_price` (giá niêm yết). Pricelist-applied
    pricing needs an ORM *method* (e.g. `_get_contextual_price`), which the
    read-only gateway does not permit, and Odoo 19 dropped the context-computed
    `price` field on product.product — so list_price is the gateway-readable
    sale price. `partner_id` is accepted for API stability but not used here."""
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("product.product", [["id", "=", product_id]],
                              ["name", "list_price"], limit=1)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("get_product_price",
                         f"Lỗi tra giá — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
    if not rows:
        return err(f"Không tìm thấy sản phẩm ID {product_id}.")
    price = rows[0].get("list_price") or 0.0
    return ok({"product_id": product_id, "name": rows[0].get("name"),
               "price": price, "qty": qty},
              f"Giá {rows[0].get('name')}: {price:,.0f} (SL {qty:g}).")


# Trần số nhóm khách trong BẢNG PHÂN RÃ. KHÔNG áp cho `total` — xem chú thích
# trong sales_summary.
TRAN_NHOM_KHACH = 100


def sales_summary(period="month", *, gw=None):
    gw = gw or default_gateway()
    domain = [["state", "in", ["sale", "done"]]]
    df = _period_from(period)
    if df:
        domain.append(["date_order", ">=", df + " 00:00:00"])
    # HAI lời gọi có chủ đích (sửa 2026-08-22).
    #
    # Bản trước tính TỔNG bằng cách cộng các nhóm partner đã bị cắt `limit=100`
    # và KHÔNG có `orderby`. Doanh nghiệp trên 100 khách vì thế bị báo THIẾU
    # doanh thu — im lặng, không cờ, không cảnh báo. Đây là kiểu sai nguy hiểm
    # nhất với một con số tài chính: nó trông hợp lý nên không ai kiểm lại.
    #
    # Lời gọi 1: KHÔNG groupby ⇒ Odoo trả đúng một hàng tổng, không cắt được.
    # Lời gọi 2: vẫn giới hạn nhưng THÊM `orderby` giảm dần, nên số nhóm giữ
    # lại là những khách LỚN NHẤT chứ không phải một tập tuỳ ý.
    try:
        tong_nhom = gw.read_group("sale.order", domain, ["amount_total:sum"], [])
        groups = gw.read_group("sale.order", domain, ["amount_total:sum"],
                               ["partner_id"], orderby="amount_total desc",
                               limit=TRAN_NHOM_KHACH)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("sales_summary",
                         f"Lỗi tổng hợp doanh thu — không lấy được dữ "
                         f"liệu. Nếu lặp lại, báo quản trị viên.", e)
    total = (tong_nhom[0].get("amount_total") or 0) if tong_nhom else 0
    rows = [{"partner": (g.get("partner_id") or [0, "N/A"])[1],
             "amount": g.get("amount_total") or 0} for g in groups]
    rows.sort(key=lambda r: r["amount"], reverse=True)
    # `capped`: bảng phân rã theo khách bị cắt, nhưng `total` thì KHÔNG. Nói
    # rõ ra thay vì để người đọc tự suy — cùng khuôn với get_product_price.
    capped = len(groups) >= TRAN_NHOM_KHACH
    top = "\n".join(f"  {r['partner']}: {r['amount']:,.0f}" for r in rows[:5])
    ghi_chu = (f"\n(Bảng theo khách chỉ liệt kê {TRAN_NHOM_KHACH} khách lớn "
               f"nhất; tổng ở trên vẫn là tổng ĐẦY ĐỦ.)") if capped else ""
    return ok({"period": period, "total": total, "by_partner": rows,
               "capped": capped},
              f"Doanh thu {period}: {total:,.0f}\nTop khách:\n{top}{ghi_chu}")


def top_products(by="quantity", period=None, limit=10, *, gw=None):
    gw = gw or default_gateway()
    domain = [["order_id.state", "in", ["sale", "done"]]]
    df = _period_from(period)
    if df:
        domain.append(["order_id.date_order", ">=", df + " 00:00:00"])
    orderby = "price_subtotal desc" if by == "revenue" else "product_uom_qty desc"
    try:
        groups = gw.read_group("sale.order.line", domain,
                               ["product_uom_qty:sum", "price_subtotal:sum"], ["product_id"],
                               orderby=orderby, limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("top_products",
                         f"Lỗi top sản phẩm — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
    rows = [{"product": (g.get("product_id") or [0, "N/A"])[1],
             "qty": g.get("product_uom_qty") or 0,
             "revenue": g.get("price_subtotal") or 0} for g in groups]
    body = "\n".join(f"  {i}. {r['product']} | SL {r['qty']:,.0f} | DT {r['revenue']:,.0f}"
                     for i, r in enumerate(rows, 1))
    return ok({"by": by, "rows": rows}, f"Top {len(rows)} sản phẩm:\n{body}")


def get_customer_detail(name, *, gw=None):
    """Hồ sơ chi tiết MỘT khách hàng: liên hệ, thuế, điều khoản thanh toán,
    số đơn bán. Mirror get_supplier_detail (purchase.py), KHÔNG đọc bank_ids
    — không có giá trị nghiệp vụ tương đương bản NCC (spec 2026-08-07 §2)."""
    gw = gw or default_gateway()
    cus, msg = _resolve_single("res.partner", name, gw)
    if msg:
        return err(msg)
    try:
        rows = gw.search_read("res.partner", [["id", "=", cus["id"]]],
                              ["name", "email", "phone", "vat", "street", "city",
                               "property_payment_term_id"], limit=1)
        p = rows[0]
        sos = gw.search_read("sale.order", [["partner_id", "=", cus["id"]]],
                             ["id"], limit=100)
    except Exception as e:                                  # noqa: BLE001
        return fail_read("get_customer_detail",
                         f"Lỗi tra cứu hồ sơ khách hàng — không lấy "
                         f"được dữ liệu. Nếu lặp lại, báo quản trị viên.", e)
    term = p.get("property_payment_term_id")
    display = (f"Khách hàng: {p['name']}\n"
              f"  Email: {p['email'] or '—'} | Điện thoại: {p['phone'] or '—'}\n"
              f"  Mã số thuế: {p['vat'] or '—'}\n"
              f"  Địa chỉ: {p['street'] or '—'}, {p['city'] or '—'}\n"
              f"  Điều khoản thanh toán: {term[1] if term else '—'}\n"
              f"  Số đơn bán đã có: {len(sos)}")
    return ok({"partner": p, "so_count": len(sos)}, display)
