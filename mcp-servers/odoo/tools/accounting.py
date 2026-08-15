"""Tool MCP domain Accounting (account.move / product.supplierinfo /
res.partner) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo(); helper resolve dùng chung nhiều
domain (_resolve_partner, _resolve_product) nằm ở helpers.py — xem docstring
ở đó để biết vì sao chúng không nằm trong module domain nào.
"""
from server import mcp
from odoo_call import odoo
from helpers import envelope, fail, resolve_unique, _resolve_partner, _resolve_product


@mcp.tool()
def post_invoice(partner_name: str = "", amount: float | None = None,
                 invoice_date: str | None = None, invoice_id: int = 0) -> str:
    """Phát hành hóa đơn/credit memo nháp (account.move draft → posted) của
    một khách hàng — áp dụng cho cả hóa đơn (out_invoice/in_invoice) VÀ
    credit memo (out_refund/in_refund).
    Hóa đơn nháp CHƯA có số (số được cấp khi phát hành), nên tra theo tên khách.
    Nếu khách có nhiều hóa đơn nháp, truyền thêm amount hoặc invoice_date để chọn đúng cái.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        partner_name: Tên khách hàng/nhà cung cấp của hóa đơn nháp (tìm gần đúng).
        amount: Tổng tiền hóa đơn — dùng để phân biệt khi có nhiều nháp.
        invoice_date: Ngày hóa đơn (YYYY-MM-DD) — dùng để phân biệt.
        invoice_id: ID hóa đơn đã biết (ưu tiên hơn partner_name — đường nội bộ).
    """
    if invoice_id:
        rows = odoo("account.move", "search_read",
                    [[["id", "=", invoice_id],
                      ["move_type", "in", ["out_invoice", "in_invoice",
                                           "out_refund", "in_refund"]]]],
                    {"fields": ["id", "name", "state", "partner_id"], "limit": 1})
        if not rows:
            return envelope(False, f"Không tìm thấy hóa đơn ID {invoice_id}.")
        mv = rows[0]
        if mv["state"] == "posted":
            return envelope(False, f"Hóa đơn {mv['name']} đã phát hành rồi.")
        if mv["state"] != "draft":
            return envelope(False,
                            f"Hóa đơn ID {invoice_id} không ở trạng thái nháp.")
        odoo("account.move", "action_post", [[invoice_id]])
        posted = odoo("account.move", "read", [[invoice_id]],
                      {"fields": ["name", "partner_id"]})
        name = posted[0]["name"] if posted else "?"
        partner = (posted[0]["partner_id"][1]
                   if posted and posted[0].get("partner_id") else "?")
        return envelope(True, f"Đã phát hành hóa đơn {name} cho {partner}.",
                        ref=name, model="account.move", res_id=invoice_id,
                        state="posted")

    if not partner_name:
        return envelope(False,
                        "Vui lòng cho biết khách hàng (hoặc ID) của hóa đơn nháp.")

    domain = [["move_type", "in", ["out_invoice", "in_invoice",
                                   "out_refund", "in_refund"]],
              ["state", "=", "draft"],
              ["partner_id.name", "ilike", partner_name]]
    if amount is not None:
        domain.append(["amount_total", "=", amount])
    if invoice_date:
        domain.append(["invoice_date", "=", invoice_date])

    rows = odoo("account.move", "search_read", [domain],
                {"fields": ["id", "partner_id", "amount_total", "invoice_date",
                            "move_type"], "limit": 6})

    row, msg = resolve_unique(
        rows, "hóa đơn nháp",
        describe=lambda r: (f"{r['partner_id'][1] if r['partner_id'] else '?'} "
                            f"— {(r.get('amount_total') or 0):,.0f}đ "
                            f"— {r.get('invoice_date') or '—'}"),
        hint="Vui lòng nêu rõ số tiền hoặc ngày.")
    if msg:
        return envelope(False, msg)

    partner = row["partner_id"][1] if row["partner_id"] else partner_name
    odoo("account.move", "action_post", [[row["id"]]])
    posted = odoo("account.move", "read", [[row["id"]]], {"fields": ["name"]})
    name = posted[0]["name"] if posted else "?"
    return envelope(True, f"Đã phát hành hóa đơn {name} cho {partner}.",
                    ref=name, model="account.move", res_id=row["id"],
                    state="posted")


@mcp.tool()
def create_invoice_from_order(order_ref: str) -> str:
    """Tạo hóa đơn nháp (account.move) từ một đơn bán ĐÃ XÁC NHẬN.
    Chỉ tạo nháp — phát hành hóa đơn là bước riêng (post_invoice). Đơn chưa
    xác nhận sẽ bị từ chối kèm gợi ý xác nhận trước.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn bán, ví dụ "S00012".
    """
    try:
        rows = odoo("sale.order", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state", "invoice_status",
                                "invoice_ids"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False, f"Có nhiều đơn tên '{order_ref}'. Vui lòng nêu rõ hơn.")

        so = rows[0]
        name = so["name"]
        if so["state"] not in ("sale", "done"):
            return envelope(False, f"Đơn {name} chưa xác nhận (trạng thái nháp). "
                                   f"Hãy xác nhận đơn trước khi tạo hóa đơn.")
        if so["invoice_status"] != "to invoice":
            # Verified-live: after full invoicing Odoo 19 reports 'no' (not
            # 'invoiced'), so one guard covers both not-deliverable and done.
            return envelope(False, f"Không có gì để xuất hóa đơn cho đơn {name} "
                                   f"(chưa giao hàng, hoặc đã xuất đủ).")

        before = set(so["invoice_ids"] or [])
        ctx = {"active_model": "sale.order", "active_ids": [so["id"]],
               "active_id": so["id"]}
        wid = odoo("sale.advance.payment.inv", "create",
                   [{"advance_payment_method": "delivered"}], {"context": ctx})
        # create_invoices returns an action dict Odoo can't marshal over
        # XML-RPC; odoo() maps that benign Fault to None — success is verified
        # by re-reading invoice_ids below, never from this return value.
        odoo("sale.advance.payment.inv", "create_invoices", [[wid]],
             {"context": ctx})

        after = odoo("sale.order", "read", [[so["id"]]], {"fields": ["invoice_ids"]})
        new_ids = [i for i in (after[0]["invoice_ids"] if after else [])
                   if i not in before]
        if not new_ids:
            return envelope(False, f"Không tạo được hóa đơn cho đơn {name} — "
                                   f"vui lòng kiểm tra trên Odoo.")
        return envelope(True, f"Đã tạo hóa đơn nháp cho đơn {name} (chưa phát hành).",
                        ref=None, model="account.move", res_id=max(new_ids),
                        state="draft")
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return fail("create_invoice_from_order",
                    f"Lỗi khi tạo hóa đơn cho đơn {order_ref} — thao tác chưa "
                    f"được thực hiện. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def register_payment(invoice_id: int = 0, invoice_ref: str = "",
                     partner_name: str = "", amount: float | None = None,
                     invoice_date: str | None = None, journal: str = "") -> str:
    """Ghi nhận thanh toán cho một hóa đơn ĐÃ PHÁT HÀNH (khách trả tiền hóa đơn
    bán, hoặc mình trả tiền hóa đơn mua NCC). Luôn thanh toán ĐỦ số dư còn lại
    của hóa đơn — amount/invoice_date chỉ dùng để CHỌN đúng hóa đơn khi trùng,
    KHÔNG phải số tiền thanh toán một phần.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        invoice_id: ID hóa đơn đã biết (ưu tiên cao nhất — đường nội bộ/chain).
        invoice_ref: Số hóa đơn đã phát hành (vd "INV/2026/00016", "BILL/...").
        partner_name: Tên khách/NCC (tìm gần đúng) khi không biết số hóa đơn.
        amount: Tổng tiền hóa đơn — CHỈ để phân biệt khi có nhiều hóa đơn.
        invoice_date: Ngày hóa đơn (YYYY-MM-DD) — CHỈ để phân biệt.
        journal: "bank" | "cash" — sổ nhận/chi tiền. Bỏ trống = hệ thống tự chọn.
    """
    try:
        fields = ["id", "name", "state", "payment_state", "amount_residual",
                  "partner_id"]
        if invoice_id:
            rows = odoo("account.move", "search_read",
                       [[["id", "=", invoice_id],
                         ["move_type", "in", ["out_invoice", "in_invoice"]]]],
                       {"fields": fields, "limit": 1})
            if not rows:
                return envelope(False, f"Không tìm thấy hóa đơn ID {invoice_id}.")
            mv = rows[0]
        elif invoice_ref:
            rows = odoo("account.move", "search_read",
                       [[["name", "=", invoice_ref],
                         ["move_type", "in", ["out_invoice", "in_invoice"]]]],
                       {"fields": fields, "limit": 2})
            if not rows:
                return envelope(False, f"Không tìm thấy hóa đơn '{invoice_ref}'.")
            if len(rows) > 1:
                return envelope(False, f"Có nhiều hóa đơn tên '{invoice_ref}'.")
            mv = rows[0]
        elif partner_name:
            domain = [["move_type", "in", ["out_invoice", "in_invoice"]],
                     ["state", "=", "posted"],
                     ["payment_state", "in", ["not_paid", "partial"]],
                     ["partner_id.name", "ilike", partner_name]]
            if amount is not None:
                domain.append(["amount_residual", "=", amount])
            if invoice_date:
                domain.append(["invoice_date", "=", invoice_date])
            rows = odoo("account.move", "search_read", [domain],
                       {"fields": fields, "limit": 6})
            row, msg = resolve_unique(
                rows, "hóa đơn",
                describe=lambda r: (
                    f"{r['name']} — {r['partner_id'][1] if r['partner_id'] else '?'} "
                    f"— còn {r['amount_residual']:,.0f}đ"),
                hint="Vui lòng nêu rõ số hóa đơn, số tiền hoặc ngày.")
            if msg:
                return envelope(False, msg)
            mv = row
        else:
            return envelope(False,
                            "Vui lòng cho biết số hóa đơn hoặc tên khách/NCC.")

        if mv["state"] != "posted":
            return envelope(False, f"Hóa đơn {mv['name']} chưa phát hành. "
                                   f"Hãy phát hành hóa đơn trước.")
        if mv["payment_state"] == "paid":
            return envelope(False, f"Hóa đơn {mv['name']} đã thanh toán đủ rồi.")
        if mv["payment_state"] == "reversed":
            return envelope(False, f"Hóa đơn {mv['name']} đã bị đảo, "
                                   f"không thể ghi nhận thanh toán.")

        move_id = mv["id"]
        partner = mv["partner_id"][1] if mv["partner_id"] else "?"

        journal_vals = {}
        if journal:
            jtype = journal.strip().lower()
            if jtype not in ("bank", "cash"):
                return envelope(False, f"Loại sổ '{journal}' không hợp lệ. "
                                       f"Chỉ nhận 'bank' hoặc 'cash'.")
            jrows = odoo("account.journal", "search", [[["type", "=", jtype]]],
                        {"limit": 1, "order": "id asc"})
            if not jrows:
                return envelope(False, f"Không tìm thấy sổ loại '{jtype}'.")
            journal_vals["journal_id"] = jrows[0]

        # action_register_payment tự tính active_ids là các move-line receivable/
        # payable thật (KHÔNG phải move id) — dùng context này VERBATIM, đã verify
        # trên Odoo 19 thật (không tự dựng context tay).
        action = odoo("account.move", "action_register_payment", [[move_id]])
        ctx = action["context"]

        wiz_id = odoo("account.payment.register", "create", [journal_vals],
                      {"context": ctx})
        wiz = odoo("account.payment.register", "read", [[wiz_id]],
                  {"fields": ["amount", "journal_id"]})[0]

        odoo("account.payment.register", "action_create_payments", [[wiz_id]],
            {"context": ctx})

        after = odoo("account.move", "read", [[move_id]],
                    {"fields": ["name", "payment_state"]})[0]
        state_label = {"paid": "Đã thanh toán đủ.",
                      "in_payment": "Đã ghi nhận, chờ đối soát ngân hàng.",
                      "partial": "Đã thanh toán một phần."}.get(
            after["payment_state"], "")
        journal_name = wiz["journal_id"][1] if wiz["journal_id"] else "?"
        return envelope(True,
            f"Đã ghi nhận thanh toán {wiz['amount']:,.0f}đ cho hóa đơn "
            f"{after['name']} ({partner}) qua sổ {journal_name}. {state_label}",
            ref=after["name"], model="account.move", res_id=move_id,
            state=after["payment_state"])
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return fail("register_payment",
                    f"Lỗi khi ghi nhận thanh toán — thao tác chưa được thực "
                    f"hiện. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def create_credit_memo(invoice_id: int, reason: str = "") -> str:
    """Tạo biên lai tín dụng (credit memo, account.move type 'out_refund')
    hoàn TOÀN BỘ số tiền một hóa đơn khách hàng ĐÃ PHÁT HÀNH. Nhận ID ĐÃ
    resolve (coordinator lo resolve số hóa đơn). Chỉ tạo NHÁP — phát hành
    là bước riêng (post_invoice). YÊU CẦU XÁC NHẬN từ người dùng trước khi
    gọi.

    Args:
        invoice_id: ID hóa đơn khách hàng (account.move) ĐÃ posted.
        reason: Lý do hoàn (tùy chọn, hiển thị trên credit memo).
    """
    try:
        rows = odoo("account.move", "search_read",
                    [[["id", "=", invoice_id],
                      ["move_type", "=", "out_invoice"]]],
                    {"fields": ["id", "name", "state", "partner_id",
                                "journal_id"], "limit": 1})
        if not rows:
            return envelope(False, f"Không tìm thấy hóa đơn khách ID {invoice_id}.")
        inv = rows[0]
        if inv["state"] != "posted":
            return envelope(False, f"Hóa đơn {inv['name']} chưa phát hành, "
                                   f"không thể tạo credit memo.")

        vals = {"move_ids": [(6, 0, [invoice_id])],
                "journal_id": inv["journal_id"][0]}
        if reason:
            vals["reason"] = reason
        wiz_id = odoo("account.move.reversal", "create", [vals])
        odoo("account.move.reversal", "refund_moves", [[wiz_id]])
        wiz = odoo("account.move.reversal", "read", [[wiz_id]],
                   {"fields": ["new_move_ids"]})[0]
        new_ids = wiz["new_move_ids"]
        if not new_ids:
            return envelope(False, f"Không tạo được credit memo cho hóa đơn "
                                   f"{inv['name']} — vui lòng kiểm tra trên "
                                   f"Odoo.")
        new_id = new_ids[0]
        cn = odoo("account.move", "read", [[new_id]],
                  {"fields": ["state", "amount_total"]})[0]
        partner = inv["partner_id"][1] if inv["partner_id"] else "?"
        return envelope(True,
                        f"Đã tạo credit memo (nháp) cho hóa đơn {inv['name']} "
                        f"của {partner}: {cn['amount_total']:,.0f}.",
                        ref=None, model="account.move", res_id=new_id,
                        state=cn["state"])
    except Exception as e:  # noqa: BLE001
        return fail("create_credit_memo",
                    f"Lỗi khi tạo credit memo — thao tác chưa được thực hiện. "
                    f"Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def create_vendor(name: str, email: str = "", phone: str = "",
                  vat: str = "", street: str = "", city: str = "") -> str:
    """Tạo hồ sơ nhà cung cấp (NCC) mới (res.partner, supplier_rank=1).
    Coordinator đã dup-check tên/email trước khi gọi tool này — không lặp
    lại ở đây. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        name: Tên NCC (bắt buộc).
        email: Email liên hệ (tùy chọn).
        phone: Số điện thoại (tùy chọn).
        vat: Mã số thuế (tùy chọn).
        street: Địa chỉ (tùy chọn).
        city: Thành phố (tùy chọn).
    """
    try:
        if not str(name or "").strip():
            return envelope(False, "Thiếu tên nhà cung cấp.")
        vals = {"name": name, "supplier_rank": 1}
        for k, v in (("email", email), ("phone", phone), ("vat", vat),
                     ("street", street), ("city", city)):
            if str(v or "").strip():
                vals[k] = v
        partner_id = odoo("res.partner", "create", [vals])
        return envelope(True, f"Đã tạo nhà cung cấp '{name}'.",
                        ref=name, model="res.partner", res_id=partner_id)
    except Exception as e:  # noqa: BLE001
        return fail("create_vendor",
                    f"Lỗi khi tạo nhà cung cấp — thao tác chưa được thực hiện. "
                    f"Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def update_vendor_pricing(price: float, vendor_name: str = "", partner_id: int = 0,
                          product: str = "", product_id: int = 0,
                          min_qty: float | None = None,
                          delay: int | None = None) -> str:
    """Khai báo/cập nhật giá mua từ một NCC cho một sản phẩm
    (product.supplierinfo). Mỗi cặp (NCC, sản phẩm) chỉ giữ 1 giá hiện
    hành — gọi lại sẽ GHI ĐÈ giá cũ. min_qty/delay CHỈ ghi khi nêu rõ
    (không tự đặt lại về mặc định của giá trước đó). Ưu tiên ID đã resolve
    (partner_id, product_id). YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        price: Đơn giá mua (bắt buộc, lớn hơn 0).
        vendor_name: Tên NCC (dùng khi không có partner_id).
        partner_id: ID NCC đã resolve (ưu tiên hơn vendor_name).
        product: Tên/mã sản phẩm (dùng khi không có product_id).
        product_id: ID sản phẩm đã resolve (ưu tiên hơn product).
        min_qty: Số lượng tối thiểu để hưởng giá này (tùy chọn).
        delay: Thời gian giao hàng dự kiến, tính bằng ngày (tùy chọn).
    """
    try:
        if price <= 0:
            return envelope(False, "Đơn giá phải lớn hơn 0.")

        if partner_id:
            vrows = odoo("res.partner", "read", [[partner_id]],
                        {"fields": ["id", "name"]})
            if not vrows:
                return envelope(False, f"Không tìm thấy nhà cung cấp ID {partner_id}.")
            vendor = vrows[0]
        else:
            vendor, msg = _resolve_partner(vendor_name, "nhà cung cấp",
                                           "Vui lòng nêu rõ tên nhà cung cấp.")
            if msg:
                return envelope(False, msg)

        if product_id:
            prows = odoo("product.product", "read", [[product_id]],
                        {"fields": ["id", "name", "product_tmpl_id"]})
            if not prows:
                return envelope(False, f"Không tìm thấy sản phẩm ID {product_id}.")
            prod = prows[0]
        else:
            resolved, pmsg = _resolve_product(product, "purchase_ok")
            if pmsg:
                return envelope(False, pmsg)
            prows = odoo("product.product", "read", [[resolved["id"]]],
                        {"fields": ["id", "name", "product_tmpl_id"]})
            prod = prows[0]
        tmpl_id = prod["product_tmpl_id"][0]

        existing = odoo("product.supplierinfo", "search_read",
                        [[["partner_id", "=", vendor["id"]],
                          ["product_tmpl_id", "=", tmpl_id]]],
                        {"fields": ["id"], "limit": 1})
        extra = {}
        if min_qty is not None:
            extra["min_qty"] = min_qty
        if delay is not None:
            extra["delay"] = delay

        if existing:
            si_id = existing[0]["id"]
            odoo("product.supplierinfo", "write", [[si_id], {"price": price, **extra}])
        else:
            si_id = odoo("product.supplierinfo", "create",
                        [{"partner_id": vendor["id"], "product_id": prod["id"],
                          "price": price, **extra}])

        return envelope(True,
                        f"Đã cập nhật giá {prod['name']} từ {vendor['name']}: "
                        f"{price:,.0f}đ.",
                        ref=vendor["name"], model="product.supplierinfo",
                        res_id=si_id)
    except Exception as e:  # noqa: BLE001
        return fail("update_vendor_pricing",
                    f"Lỗi khi cập nhật giá nhà cung cấp — thao tác chưa được "
                    f"thực hiện. Nếu lặp lại, báo quản trị viên.", e)
