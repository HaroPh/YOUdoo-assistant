"""Tool MCP domain Purchase (purchase.order) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo(); helper resolve/apply dùng chung
nhiều domain (_resolve_partner, _resolve_product, _apply_line_ops,
_validate_order_pickings) nằm ở helpers.py — xem docstring ở đó để biết vì
sao chúng không nằm trong module domain nào.
"""
from server import mcp
from odoo_call import odoo
from helpers import envelope, today_iso, _resolve_partner, _resolve_product, \
    _apply_line_ops, _validate_order_pickings


@mcp.tool()
def confirm_purchase_order(order_ref: str) -> str:
    """Xác nhận đơn mua hàng (purchase.order) đang ở trạng thái nháp.
    draft/sent → purchase. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn mua, ví dụ "P00003".
    """
    rows = odoo("purchase.order", "search_read",
                [[["name", "=", order_ref]]],
                {"fields": ["id", "name", "state"], "limit": 2})
    if not rows:
        return envelope(False, f"Không tìm thấy đơn mua '{order_ref}'.")
    if len(rows) > 1:
        return envelope(False,
                        f"Có nhiều đơn mua tên '{order_ref}'. Vui lòng nêu rõ hơn.")

    order = rows[0]
    name, state = order["name"], order["state"]
    if state in ("purchase", "done"):
        return envelope(False, f"Đơn mua {name} đã được xác nhận rồi.")
    if state == "cancel":
        return envelope(False, f"Đơn mua {name} đã bị hủy, không thể xác nhận.")

    odoo("purchase.order", "button_confirm", [[order["id"]]])
    return envelope(True, f"Đã xác nhận đơn mua {name}.",
                    ref=name, model="purchase.order", res_id=order["id"],
                    state="purchase")


@mcp.tool()
def receive_order(order_ref: str) -> str:
    """Nhận hàng cho một đơn mua ĐÃ XÁC NHẬN: xác nhận mọi phiếu nhập kho
    (stock.picking) đã sẵn sàng của đơn. Đơn không có phiếu cần nhận
    (dịch vụ / đã nhận đủ) được coi là hoàn tất — chuỗi đi tiếp bước
    lập hóa đơn NCC. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn mua, ví dụ "P00003".
    """
    try:
        rows = odoo("purchase.order", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state", "picking_ids"],
                     "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn mua '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False,
                            f"Có nhiều đơn mua tên '{order_ref}'. Vui lòng nêu rõ hơn.")

        po = rows[0]
        name = po["name"]
        if po["state"] not in ("purchase", "done"):
            return envelope(False, f"Đơn mua {name} chưa xác nhận. "
                                   f"Hãy xác nhận đơn trước khi nhận hàng.")

        status, val = _validate_order_pickings(po["picking_ids"], "incoming")
        if status == "none":
            return envelope(True, f"Đơn mua {name} không có phiếu cần nhận "
                                  f"(dịch vụ hoặc đã nhận đủ).",
                            ref=name, model="purchase.order", res_id=po["id"],
                            state="purchase")
        if status == "not_ready":
            return envelope(False,
                            f"Phiếu nhập của đơn mua {name} chưa sẵn sàng nhận "
                            f"(trạng thái: {val}).")
        if status == "wizard":
            return envelope(False,
                            f"Phiếu {val} cần thao tác bổ sung trên Odoo "
                            f"(wizard không hỗ trợ qua API). Vui lòng xử lý trực tiếp.")
        return envelope(True, f"Đã nhận hàng cho đơn mua {name} ({val} phiếu).",
                        ref=name, model="purchase.order", res_id=po["id"],
                        state="purchase")
    except Exception as e:  # noqa: BLE001 — không exception nào xuyên qua MCP tool
        return envelope(False, f"Lỗi khi nhận hàng cho đơn mua {order_ref}: {e}")


@mcp.tool()
def create_bill_from_po(order_ref: str) -> str:
    """Tạo hóa đơn nhà cung cấp (account.move nháp) từ một đơn mua ĐÃ XÁC NHẬN
    và ĐÃ NHẬN HÀNG. Chỉ tạo nháp — phát hành là bước riêng (post_invoice).
    Bill Date được đặt = hôm nay (Odoo bắt buộc trước khi phát hành).
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn mua, ví dụ "P00003".
    """
    try:
        rows = odoo("purchase.order", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state", "invoice_status",
                                "invoice_ids"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn mua '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False,
                            f"Có nhiều đơn mua tên '{order_ref}'. Vui lòng nêu rõ hơn.")

        po = rows[0]
        name = po["name"]
        if po["state"] not in ("purchase", "done"):
            return envelope(False, f"Đơn mua {name} chưa xác nhận. "
                                   f"Hãy xác nhận đơn trước khi lập hóa đơn.")
        if po["invoice_status"] != "to invoice":
            return envelope(False,
                            f"Chưa có gì để lập hóa đơn NCC cho đơn mua {name} "
                            f"(chưa nhận hàng, hoặc đã lập đủ).")

        before = set(po["invoice_ids"] or [])
        # action_create_invoice trả action dict — không tin return value; verify
        # bằng đọc lại invoice_ids (verified-live 2026-07-03 trên P00015).
        odoo("purchase.order", "action_create_invoice", [[po["id"]]])
        after = odoo("purchase.order", "read", [[po["id"]]],
                     {"fields": ["invoice_ids"]})
        new_ids = [i for i in (after[0]["invoice_ids"] if after else [])
                   if i not in before]
        if not new_ids:
            return envelope(False, f"Không tạo được hóa đơn cho đơn mua {name} — "
                                   f"vui lòng kiểm tra trên Odoo.")
        # Bill Date bắt buộc trước khi post (verified-live: "The Bill/Refund
        # date is required to validate this document.")
        odoo("account.move", "write", [new_ids, {"invoice_date": today_iso()}])
        return envelope(True, f"Đã tạo hóa đơn NCC (nháp) cho đơn mua {name}.",
                        ref=None, model="account.move", res_id=max(new_ids),
                        state="draft")
    except Exception as e:  # noqa: BLE001 — không exception nào xuyên qua MCP tool
        return envelope(False, f"Lỗi khi tạo hóa đơn cho đơn mua {order_ref}: {e}")


@mcp.tool()
def create_rfq(supplier_name: str = "", lines: list | None = None,
               partner_id: int = 0) -> str:
    """Tạo RFQ — đơn mua nháp (purchase.order) cho một nhà cung cấp với các dòng
    sản phẩm. Ưu tiên ID đã resolve (partner_id, mỗi dòng product_id); nếu vắng ID
    thì resolve theo tên. Nếu có gì không rõ thì DỪNG, không tạo đơn dở. YÊU CẦU
    XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        supplier_name: Tên nhà cung cấp (tìm gần đúng) — dùng khi không có partner_id.
        lines: Danh sách dòng hàng, mỗi dòng {"product": "<tên>", "qty": <số>} hoặc
               {"product_id": <id>, "qty": <số>}.
        partner_id: ID nhà cung cấp đã resolve (ưu tiên hơn supplier_name).
    """
    lines = lines or []
    if not lines:
        return envelope(False, "Vui lòng cho biết sản phẩm và số lượng cần đặt mua.")

    if partner_id:
        vrows = odoo("res.partner", "read", [[partner_id]], {"fields": ["id", "name"]})
        if not vrows:
            return envelope(False, f"Không tìm thấy nhà cung cấp ID {partner_id}.")
        vendor = vrows[0]
    else:
        vendor, msg = _resolve_partner(supplier_name, "nhà cung cấp",
                                       "Vui lòng nêu rõ tên nhà cung cấp.")
        if msg:
            return envelope(False, msg)

    order_line = []
    for line in lines:
        pid = line.get("product_id")
        if pid:
            order_line.append((0, 0, {"product_id": pid,
                                      "product_qty": line["qty"]}))
            continue
        prod, pmsg = _resolve_product(line["product"], "purchase_ok")
        if pmsg:
            return envelope(False, pmsg)
        order_line.append((0, 0, {"product_id": prod["id"],
                                  "product_qty": line["qty"]}))

    pid_ = odoo("purchase.order", "create",
                [{"partner_id": vendor["id"], "order_line": order_line}])
    po = odoo("purchase.order", "read", [[pid_]], {"fields": ["name"]})
    name = po[0]["name"] if po else "?"
    return envelope(True,
                    f"Đã tạo RFQ {name} (nháp) cho {vendor['name']} ({len(lines)} dòng).",
                    ref=name, model="purchase.order", res_id=pid_, state="draft")


@mcp.tool()
def update_rfq_lines(order_ref: str, ops: list | None = None) -> str:
    """Sửa dòng hàng của ĐƠN MUA (purchase.order). Chỉ áp dụng được cho đơn nháp
    (draft/sent); nếu đơn đã xác nhận, tool trả về lỗi và tầng điều phối sẽ đề nghị
    ghi chú nội bộ. ops đã resolve theo ID. YÊU CẦU XÁC NHẬN trước khi gọi.

    Args:
        order_ref: Mã đơn mua, ví dụ "P00003".
        ops: cùng schema với update_quotation_lines.
    """
    try:
        return _apply_line_ops("purchase.order", "product_qty", order_ref, ops or [])
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi sửa đơn mua {order_ref}: {e}")


@mcp.tool()
def create_bulk_rfq(vendor_names: list | None = None, partner_ids: list | None = None,
                    lines: list | None = None) -> str:
    """Tạo RFQ nháp (purchase.order) CÙNG LÚC cho NHIỀU nhà cung cấp, với
    CÙNG danh sách sản phẩm/số lượng — dùng để so sánh báo giá. Tối đa 10
    NCC/lần gọi. Ưu tiên partner_ids đã resolve; vendor_names dùng khi chưa
    resolve. Resolve TẤT CẢ NCC + TẤT CẢ sản phẩm TRƯỚC khi tạo bất kỳ đơn
    nào — nếu có gì không rõ thì DỪNG, không tạo đơn dở. YÊU CẦU XÁC NHẬN
    từ người dùng trước khi gọi.

    Args:
        vendor_names: Danh sách tên nhà cung cấp (dùng khi không có partner_ids).
        partner_ids: Danh sách ID nhà cung cấp đã resolve (ưu tiên hơn vendor_names).
        lines: Danh sách dòng hàng dùng chung cho mọi NCC, mỗi dòng
               {"product": "<tên>", "qty": <số>} hoặc {"product_id": <id>, "qty": <số>}.
    """
    lines = lines or []
    vendor_names = vendor_names or []
    partner_ids = partner_ids or []
    try:
        if not lines:
            return envelope(False, "Vui lòng cho biết sản phẩm và số lượng cần đặt mua.")

        if partner_ids:
            if len(partner_ids) > 10:
                return envelope(False, "Tối đa 10 nhà cung cấp mỗi lần — "
                                       "vui lòng chia nhỏ.")
            vendors = []
            for pid in partner_ids:
                vrows = odoo("res.partner", "read", [[pid]], {"fields": ["id", "name"]})
                if not vrows:
                    return envelope(False, f"Không tìm thấy nhà cung cấp ID {pid}.")
                vendors.append(vrows[0])
        elif vendor_names:
            if len(vendor_names) > 10:
                return envelope(False, "Tối đa 10 nhà cung cấp mỗi lần — "
                                       "vui lòng chia nhỏ.")
            vendors = []
            for vname in vendor_names:
                vendor, msg = _resolve_partner(vname, "nhà cung cấp",
                                               "Vui lòng nêu rõ tên nhà cung cấp.")
                if msg:
                    return envelope(False, msg)
                vendors.append(vendor)
        else:
            return envelope(False, "Vui lòng cho biết (các) nhà cung cấp cần gửi RFQ.")

        order_line = []
        for line in lines:
            pid = line.get("product_id")
            if pid:
                order_line.append((0, 0, {"product_id": pid,
                                          "product_qty": line["qty"]}))
                continue
            prod, pmsg = _resolve_product(line["product"], "purchase_ok")
            if pmsg:
                return envelope(False, pmsg)
            order_line.append((0, 0, {"product_id": prod["id"],
                                      "product_qty": line["qty"]}))

        names = []
        for vendor in vendors:
            po_id = odoo("purchase.order", "create",
                        [{"partner_id": vendor["id"], "order_line": order_line}])
            po = odoo("purchase.order", "read", [[po_id]], {"fields": ["name"]})
            names.append(po[0]["name"] if po else "?")

        listing = ", ".join(f"{n} ({v['name']})" for n, v in zip(names, vendors))
        return envelope(True, f"Đã tạo {len(names)} RFQ nháp: {listing}.",
                        model="purchase.order")
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi tạo RFQ hàng loạt: {e}")
