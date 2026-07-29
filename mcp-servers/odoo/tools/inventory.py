"""Tool MCP domain Inventory (stock.*) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo(); helper resolve dùng chung nhiều
domain (_resolve_product, _resolve_location) nằm ở helpers.py — xem docstring
ở đó để biết vì sao chúng không nằm trong module domain nào.
"""
from server import mcp
from odoo_call import odoo
from helpers import envelope, _resolve_product, _resolve_location


@mcp.tool()
def validate_picking(picking_ref: str) -> str:
    """Xác nhận phiếu giao/nhận hàng (stock.picking) đã được reserve đủ.
    Chỉ hoạt động khi state = 'assigned' — ở trạng thái này Odoo 19 đã tự set
    số lượng thực = số lượng reserve trên mọi dòng, nên button_validate chạy
    thẳng (không pop wizard). Nếu vẫn trả về dict (vd backorder một phần) thì
    báo an toàn để xử lý trực tiếp trên Odoo.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        picking_ref: Mã phiếu, ví dụ "WH/OUT/00001" hoặc "WH/IN/00005".
    """
    rows = odoo("stock.picking", "search_read",
                [[["name", "=", picking_ref]]],
                {"fields": ["id", "name", "state"], "limit": 2})
    if not rows:
        return f"Không tìm thấy phiếu '{picking_ref}'."
    if len(rows) > 1:
        return f"Có nhiều phiếu tên '{picking_ref}'. Vui lòng nêu rõ hơn."

    pick = rows[0]
    name, state = pick["name"], pick["state"]
    if state == "done":
        return f"Phiếu {name} đã được xác nhận rồi."
    if state == "cancel":
        return f"Phiếu {name} đã bị hủy."
    if state != "assigned":
        return (f"Phiếu {name} chưa sẵn sàng (trạng thái: {state}). "
                f"Cần reserve đủ hàng trước khi xác nhận.")

    # Odoo 19: an 'assigned' picking already has done-qty = reserved on every
    # move, so button_validate completes directly (no immediate-transfer wizard).
    result = odoo("stock.picking", "button_validate", [[pick["id"]]])
    if isinstance(result, dict):
        return (f"Phiếu {name} cần thao tác bổ sung trên Odoo "
                f"(wizard không hỗ trợ qua API). Vui lòng xử lý trực tiếp.")
    return f"Đã xác nhận phiếu {name}."


@mcp.tool()
def inventory_adjustment(new_qty: float, product_name: str = "",
                         location_name: str | None = None, product_id: int = 0) -> str:
    """Điều chỉnh tồn kho thực tế của một sản phẩm về một SỐ TUYỆT ĐỐI tại một
    vị trí kho (kiểm kê). new_qty là tồn kho KẾT QUẢ mong muốn, không phải lượng
    tăng/giảm. Nếu không nêu vị trí thì dùng kho chính. YÊU CẦU XÁC NHẬN từ người
    dùng trước khi gọi.

    Args:
        product_name: Tên sản phẩm lưu kho (tìm gần đúng).
        new_qty: Tồn kho kết quả mong muốn (>= 0).
        location_name: Tên vị trí kho (tùy chọn; bỏ trống = kho chính).
    """
    if new_qty < 0:
        return "Số lượng tồn kho không hợp lệ (không âm)."

    if product_id:
        prows = odoo("product.product", "read", [[product_id]], {"fields": ["id", "name"]})
        if not prows:
            return f"Không tìm thấy sản phẩm ID {product_id}."
        prod = prows[0]
    else:
        prod, msg = _resolve_product(product_name, "is_storable")
        if msg:
            return msg

    loc, lmsg = _resolve_location(location_name)
    if lmsg:
        return lmsg

    quants = odoo("stock.quant", "search_read",
                  [[["product_id", "=", prod["id"]],
                    ["location_id", "=", loc["id"]]]],
                  {"fields": ["id", "quantity"], "limit": 1})
    if quants:
        qid = quants[0]["id"]
        old = quants[0]["quantity"]
        odoo("stock.quant", "write", [[qid], {"inventory_quantity": new_qty}])
    else:
        old = 0.0
        qid = odoo("stock.quant", "create",
                   [{"product_id": prod["id"], "location_id": loc["id"],
                     "inventory_quantity": new_qty}])

    res = odoo("stock.quant", "action_apply_inventory", [[qid]])
    if isinstance(res, dict):
        return (f"Tồn kho {prod['name']} cần xử lý xung đột kiểm kê trên Odoo "
                f"(sản phẩm theo lô/sê-ri). Vui lòng xử lý trực tiếp.")

    q = odoo("stock.quant", "read", [[qid]], {"fields": ["quantity"]})
    now = q[0]["quantity"] if q else new_qty
    return (f"Đã điều chỉnh tồn kho {prod['name']} tại {loc['complete_name']}: "
            f"{old:g} → {now:g}.")


@mcp.tool()
def internal_transfer(product_name: str = "", qty: float = 0.0,
                      from_location: str = "", to_location: str = "",
                      product_id: int = 0) -> str:
    """Chuyển tồn kho một sản phẩm giữa 2 vị trí nội bộ trong cùng kho (vd
    Shelf 1 → Shelf 2). Cả from_location và to_location đều BẮT BUỘC.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        product_name: Tên sản phẩm lưu kho (tìm gần đúng).
        qty: Số lượng cần chuyển (> 0).
        from_location: Tên vị trí nguồn.
        to_location: Tên vị trí đích.
    """
    if qty <= 0:
        return "Số lượng cần chuyển không hợp lệ (phải lớn hơn 0)."
    if not from_location or not to_location:
        return "Cần nêu rõ cả vị trí nguồn và vị trí đích."

    if product_id:
        prows = odoo("product.product", "read", [[product_id]], {"fields": ["id", "name"]})
        if not prows:
            return f"Không tìm thấy sản phẩm ID {product_id}."
        prod = prows[0]
    else:
        prod, msg = _resolve_product(product_name, "is_storable")
        if msg:
            return msg

    src, msg = _resolve_location(from_location)
    if msg:
        return msg
    dst, msg = _resolve_location(to_location)
    if msg:
        return msg
    if src["id"] == dst["id"]:
        return "Vị trí nguồn và đích không được trùng nhau."

    wh = odoo("stock.warehouse", "search_read", [[]],
             {"fields": ["int_type_id"], "limit": 1})
    if not wh or not wh[0].get("int_type_id"):
        return "Không tìm thấy loại phiếu chuyển kho nội bộ."
    picking_type_id = wh[0]["int_type_id"][0]

    picking_id = odoo("stock.picking", "create", [{
        "picking_type_id": picking_type_id,
        "location_id": src["id"],
        "location_dest_id": dst["id"],
        "move_ids": [(0, 0, {"product_id": prod["id"], "product_uom_qty": qty})],
    }])
    odoo("stock.picking", "action_confirm", [[picking_id]])
    odoo("stock.picking", "action_assign", [[picking_id]])
    rows = odoo("stock.picking", "read", [[picking_id]], {"fields": ["name", "state"]})
    pick = rows[0]
    if pick["state"] != "assigned":
        return (f"Phiếu {pick['name']} chưa sẵn sàng (trạng thái: {pick['state']}). "
                f"Có thể không đủ tồn kho tại {src['complete_name']}.")

    # Odoo 19: an 'assigned' picking already has done-qty = reserved on every
    # move, so button_validate completes directly (no immediate-transfer
    # wizard) — same behavior validate_picking already relies on.
    result = odoo("stock.picking", "button_validate", [[picking_id]])
    if isinstance(result, dict):
        return (f"Phiếu {pick['name']} cần thao tác bổ sung trên Odoo "
                f"(wizard không hỗ trợ qua API). Vui lòng xử lý trực tiếp.")
    return (f"Đã chuyển {qty:g} {prod['name']} từ {src['complete_name']} "
            f"sang {dst['complete_name']} (phiếu {pick['name']}).")


@mcp.tool()
def scrap_product(product_name: str = "", qty: float = 0.0,
                  location_name: str | None = None, reason: str | None = None,
                  product_id: int = 0) -> str:
    """Ghi nhận phế liệu/hàng hỏng cho một sản phẩm — trừ khỏi tồn kho khả
    dụng, chuyển vào vị trí phế liệu ảo của công ty. Nếu không nêu vị trí
    thì dùng kho chính. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        product_name: Tên sản phẩm lưu kho (tìm gần đúng).
        qty: Số lượng phế liệu (> 0).
        location_name: Tên vị trí nguồn (tùy chọn; bỏ trống = kho chính).
        reason: Lý do phế liệu (tùy chọn, ghi vào Source Document).
    """
    if qty <= 0:
        return "Số lượng phế liệu không hợp lệ (phải lớn hơn 0)."

    if product_id:
        prows = odoo("product.product", "read", [[product_id]], {"fields": ["id", "name"]})
        if not prows:
            return f"Không tìm thấy sản phẩm ID {product_id}."
        prod = prows[0]
    else:
        prod, msg = _resolve_product(product_name, "is_storable")
        if msg:
            return msg

    loc, msg = _resolve_location(location_name)
    if msg:
        return msg

    vals = {"product_id": prod["id"], "scrap_qty": qty, "location_id": loc["id"]}
    if reason:
        vals["origin"] = reason
    scrap_id = odoo("stock.scrap", "create", [vals])

    result = odoo("stock.scrap", "action_validate", [[scrap_id]])
    if isinstance(result, dict):
        return (f"Không đủ tồn kho {prod['name']} tại {loc['complete_name']} để "
                f"ghi nhận phế liệu. Vui lòng xử lý trực tiếp trên Odoo.")
    return f"Đã ghi nhận phế liệu {qty:g} {prod['name']} tại {loc['complete_name']}."


@mcp.tool()
def return_order(picking_id: int, lines: list | None = None) -> str:
    """Tạo phiếu trả hàng (RMA) từ một phiếu giao (stock.picking) ĐÃ DONE.
    Nhận ID ĐÃ resolve (coordinator lo resolve đơn bán → phiếu giao, và
    tên sản phẩm → ID). lines tùy chọn: [{"product_id": <id>, "qty":
    <số>}, ...] — bỏ trống/rỗng = trả TOÀN BỘ số lượng đã giao trong
    phiếu. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        picking_id: ID phiếu giao (stock.picking) đã DONE cần trả hàng.
        lines: Danh sách sản phẩm+số lượng cần trả (tùy chọn; bỏ trống =
            trả toàn bộ).
    """
    try:
        lines = lines or []
        prows = odoo("stock.picking", "search_read",
                     [[["id", "=", picking_id]]],
                     {"fields": ["id", "name", "state"], "limit": 1})
        if not prows:
            return envelope(False, f"Không tìm thấy phiếu giao ID {picking_id}.")
        picking = prows[0]
        if picking["state"] != "done":
            return envelope(False, f"Phiếu {picking['name']} chưa hoàn tất, "
                                   f"không thể tạo phiếu trả hàng.")

        wiz_id = odoo("stock.return.picking", "create",
                      [{"picking_id": picking_id}])
        wiz = odoo("stock.return.picking", "read", [[wiz_id]],
                   {"fields": ["product_return_moves"]})[0]
        return_line_ids = wiz["product_return_moves"]
        return_lines = odoo("stock.return.picking.line", "read",
                            [return_line_ids],
                            {"fields": ["product_id", "move_quantity"]})
        by_pid = {rl["product_id"][0]: rl for rl in return_lines}

        if lines:
            for l in lines:
                pid = l.get("product_id")
                qty = l.get("qty") or 0
                if pid not in by_pid:
                    names = ", ".join(rl["product_id"][1] for rl in return_lines)
                    return envelope(False, f"Sản phẩm ID {pid} không có trong "
                                           f"phiếu {picking['name']}. Sản phẩm "
                                           f"đã giao: {names}.")
                if qty <= 0:
                    return envelope(False, "Số lượng trả phải lớn hơn 0.")
                odoo("stock.return.picking.line", "write",
                     [[by_pid[pid]["id"]], {"quantity": float(qty)}])
        else:
            for rl in return_lines:
                odoo("stock.return.picking.line", "write",
                     [[rl["id"]], {"quantity": rl["move_quantity"]}])

        action = odoo("stock.return.picking", "action_create_returns", [[wiz_id]])
        new_id = action.get("res_id") if isinstance(action, dict) else None
        if not new_id:
            return envelope(False, f"Không tạo được phiếu trả hàng cho "
                                   f"{picking['name']} — vui lòng kiểm tra "
                                   f"trên Odoo.")
        new_pick = odoo("stock.picking", "read", [[new_id]],
                        {"fields": ["name", "state"]})[0]
        return envelope(True,
                        f"Đã tạo phiếu trả hàng {new_pick['name']} từ "
                        f"{picking['name']}.",
                        ref=new_pick["name"], model="stock.picking",
                        res_id=new_id, state=new_pick["state"])
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi tạo phiếu trả hàng: {e}")
