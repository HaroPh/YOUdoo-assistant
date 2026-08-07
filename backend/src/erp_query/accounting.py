"""Accounting bounded context — customer/vendor invoices."""
from datetime import datetime, timezone

from .envelope import ok, err
from .gateway import default_gateway

_FIELDS = ["name", "partner_id", "invoice_date", "invoice_date_due",
           "amount_total", "amount_residual", "payment_state"]
_DETAIL_FIELDS = ["id", "name", "partner_id", "invoice_date", "amount_total",
                  "amount_residual", "move_type", "state"]
_LINE_FIELDS = ["product_id", "quantity", "price_subtotal"]
_INVOICE_TYPES = ["out_invoice", "in_invoice", "out_refund", "in_refund"]


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def list_invoices(move_type, partner=None, payment_state=None, limit=50, *, gw=None):
    gw = gw or default_gateway()
    domain = [["move_type", "=", move_type], ["state", "=", "posted"]]
    if partner:
        domain.append(["partner_id.name", "ilike", partner])
    if payment_state:
        domain.append(["payment_state", "=", payment_state])
    try:
        rows = gw.search_read("account.move", domain, _FIELDS,
                              order="invoice_date desc", limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn: {e}")
    if not rows:
        return ok({"rows": [], "count": 0}, "Không có hóa đơn nào phù hợp.")
    body = "\n".join(f"  {r['name']} | {(r['partner_id'] or [0, 'N/A'])[1]} "
                     f"| {r['amount_total']:,.0f} | còn {r['amount_residual']:,.0f} "
                     f"| {r['payment_state']}" for r in rows)
    return ok({"rows": rows, "count": len(rows)}, f"{len(rows)} hóa đơn:\n{body}")


def get_overdue_invoices(limit=50, *, gw=None):
    gw = gw or default_gateway()
    domain = [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
              ["payment_state", "in", ["not_paid", "partial"]],
              ["invoice_date_due", "<", _today()]]
    try:
        rows = gw.search_read("account.move", domain, _FIELDS,
                              order="invoice_date_due asc", limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn quá hạn: {e}")
    if not rows:
        return ok({"rows": [], "count": 0}, "Không có hóa đơn nào quá hạn.")
    body = "\n".join(f"  {r['name']} | {(r['partner_id'] or [0, 'N/A'])[1]} "
                     f"| đến hạn {r.get('invoice_date_due') or 'N/A'} "
                     f"| còn {r['amount_residual']:,.0f}" for r in rows)
    return ok({"rows": rows, "count": len(rows)},
              f"{len(rows)} hóa đơn quá hạn:\n{body}")


def get_partner_balance(name, *, gw=None):
    """Công nợ 1 đối tác cụ thể — CẢ hai chiều nếu có: phải thu (khách nợ
    mình, out_invoice) và phải trả (mình nợ NCC, in_invoice). KHÔNG cộng
    ròng — 2 loại sổ khác bản chất."""
    gw = gw or default_gateway()
    try:
        partners = gw.search_read("res.partner", [["name", "ilike", name]],
                                  ["id", "name"], limit=5)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu đối tác: {e}")
    if not partners:
        return err(f"Không tìm thấy đối tác '{name}'.")
    if len(partners) > 1:
        names = "; ".join(f"{p['name']} (ID {p['id']})" for p in partners)
        return err(f"Có nhiều đối tác khớp '{name}': {names}.")
    partner = partners[0]
    try:
        ar = gw.read_group("account.move",
                           [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
                            ["payment_state", "in", ["not_paid", "partial"]],
                            ["partner_id", "=", partner["id"]]],
                           ["amount_residual:sum"], ["partner_id"])
        ap = gw.read_group("account.move",
                           [["move_type", "=", "in_invoice"], ["state", "=", "posted"],
                            ["payment_state", "in", ["not_paid", "partial"]],
                            ["partner_id", "=", partner["id"]]],
                           ["amount_residual:sum"], ["partner_id"])
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra công nợ: {e}")
    ar_amt = ar[0]["amount_residual"] if ar else 0.0
    ap_amt = ap[0]["amount_residual"] if ap else 0.0
    if not ar_amt and not ap_amt:
        return ok({"partner": partner, "receivable": 0.0, "payable": 0.0},
                  f"{partner['name']}: không còn công nợ nào.")
    parts = [f"{partner['name']}:"]
    if ar_amt:
        parts.append(f"  Khách nợ mình (phải thu): {ar_amt:,.0f}")
    if ap_amt:
        parts.append(f"  Mình nợ NCC (phải trả): {ap_amt:,.0f}")
    return ok({"partner": partner, "receivable": ar_amt, "payable": ap_amt},
              "\n".join(parts))


def find_posted_invoice(invoice_ref, *, gw=None):
    """NỘI BỘ (coordinator create_credit_memo) — resolve 1 hóa đơn khách
    theo SỐ CHÍNH XÁC, lọc move_type='out_invoice' + state='posted'. Phân
    biệt rõ 'không tồn tại' vs 'chưa phát hành' để báo lỗi đúng nguyên
    nhân."""
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("account.move",
                              [["name", "=", invoice_ref],
                               ["move_type", "=", "out_invoice"]],
                              ["id", "name", "state", "partner_id",
                               "amount_total"], limit=2)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu hóa đơn: {e}")
    if not rows:
        return err(f"Không tìm thấy hóa đơn khách '{invoice_ref}'.")
    if len(rows) > 1:
        return err(f"Có nhiều hóa đơn tên '{invoice_ref}'.")
    inv = rows[0]
    if inv["state"] != "posted":
        return err(f"Hóa đơn {inv['name']} chưa phát hành "
                   f"(trạng thái: {inv['state']}).")
    return ok({"invoice": inv},
              f"Hóa đơn {inv['name']} | "
              f"{(inv['partner_id'] or [0, 'N/A'])[1]} | "
              f"{inv['amount_total']:,.0f}.")


def get_invoice_detail(invoice_id, *, gw=None):
    """Chi tiết 1 hóa đơn + dòng hàng, cho coordinator render bản tóm tắt
    trước cổng xác nhận ghi (spec 2026-08-06 §3.1).

    Lọc display_type='product' là BẮT BUỘC, không phải tối ưu: đo thật trên
    Odoo 2026-08-06 cho thấy account.move.line của một hóa đơn còn chứa dòng
    'payment_term' (dòng đối ứng phải thu/phải trả, số tiền 0) — không lọc
    thì bảng tóm tắt có một dòng rác 0 đồng."""
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("account.move", [["id", "=", invoice_id]],
                              _DETAIL_FIELDS, limit=1)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn: {e}")
    if not rows:
        return err(f"Không tìm thấy hóa đơn ID {invoice_id}.")
    try:
        lines = gw.search_read("account.move.line",
                               [["move_id", "=", invoice_id],
                                ["display_type", "=", "product"]],
                               _LINE_FIELDS, limit=100)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra dòng hóa đơn: {e}")
    return ok({"invoice": rows[0], "lines": lines},
              f"Hóa đơn ID {invoice_id}: {len(lines)} dòng.")


def find_draft_invoices(partner_name, amount=None, invoice_date=None, *, gw=None):
    """Danh sách hóa đơn NHÁP khớp tên đối tác — cho coordinator post_invoice.

    Trả DANH SÁCH (không phải một) có chủ đích: hóa đơn nháp chưa có số
    (name=False, đo thật 2026-08-06 — 5 bản nháp cùng 'Acme Corporation',
    4 trùng y hệt số tiền), nên coordinator phải để người dùng chọn TRƯỚC
    cổng xác nhận, thay vì để tool báo lỗi mơ hồ SAU khi đã xác nhận.
    Domain khớp domain của mcp-servers/odoo/tools/accounting.py:57-64."""
    gw = gw or default_gateway()
    domain = [["move_type", "in", _INVOICE_TYPES],
              ["state", "=", "draft"],
              ["partner_id.name", "ilike", partner_name]]
    if amount is not None:
        domain.append(["amount_total", "=", amount])
    if invoice_date:
        domain.append(["invoice_date", "=", invoice_date])
    try:
        rows = gw.search_read("account.move", domain, _DETAIL_FIELDS,
                              order="invoice_date desc", limit=10)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn nháp: {e}")
    if not rows:
        return err(f"Không tìm thấy hóa đơn nháp nào của '{partner_name}'.")
    return ok({"rows": rows, "count": len(rows)},
              f"{len(rows)} hóa đơn nháp.")


def find_open_invoices(invoice_ref=None, partner_name=None, amount=None,
                       invoice_date=None, *, gw=None):
    """Hóa đơn ĐÃ PHÁT HÀNH còn nợ — cho coordinator register_payment.

    KHÔNG dùng lại find_posted_invoice được: hàm đó lọc cứng
    move_type='out_invoice' (chỉ hóa đơn bán) trong khi register_payment
    phục vụ cả in_invoice (mình trả NCC), nó không đọc amount_residual, và
    chỉ nhận số hóa đơn chính xác chứ không nhận tên đối tác.

    payment_state lọc not_paid/partial: hóa đơn đã trả hết không còn gì để
    thanh toán, đưa vào danh sách chọn chỉ gây nhiễu."""
    gw = gw or default_gateway()
    domain = [["move_type", "in", _INVOICE_TYPES],
              ["state", "=", "posted"],
              ["payment_state", "in", ["not_paid", "partial"]]]
    if invoice_ref:
        domain.append(["name", "=", invoice_ref])
    if partner_name:
        domain.append(["partner_id.name", "ilike", partner_name])
    if amount is not None:
        # amount_residual, KHÔNG amount_total: khớp domain resolve của
        # chính nhánh partner_name-only trong mcp-servers/odoo/tools/
        # accounting.py::register_payment. register_payment luôn thanh
        # toán ĐỦ số dư còn lại (không trả một phần), nên "amount" ở đây
        # nghĩa là số tiền SẼ TRẢ dùng để phân biệt hóa đơn — với hóa đơn
        # thanh toán một phần, amount_total của hai bản ghi có thể trùng
        # trong khi amount_residual thì không.
        domain.append(["amount_residual", "=", amount])
    if invoice_date:
        domain.append(["invoice_date", "=", invoice_date])
    try:
        rows = gw.search_read("account.move", domain, _DETAIL_FIELDS,
                              order="invoice_date desc", limit=10)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn: {e}")
    if not rows:
        return err("Không tìm thấy hóa đơn đã phát hành còn nợ phù hợp.")
    return ok({"rows": rows, "count": len(rows)}, f"{len(rows)} hóa đơn.")
