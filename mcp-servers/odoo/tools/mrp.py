"""Tool MCP domain MRP (mrp.production / mrp.bom) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo(). Các tool ở đây nhận ID ĐÃ resolve
(coordinator lo resolve tên → ID trước khi gọi) nên không cần đến các helper
resolve dùng chung ở helpers.py.
"""
from server import mcp
from odoo_call import odoo
from helpers import envelope, fail


@mcp.tool()
def create_manufacturing_order(product_id: int, qty: float, bom_id: int = 0) -> str:
    """Tạo lệnh sản xuất (mrp.production, nháp) cho một sản phẩm có định mức
    BoM. Nhận ID ĐÃ resolve (product_id bắt buộc; bom_id chỉ cần khi sản phẩm
    có nhiều BoM — vắng thì tự tìm BoM 'normal' duy nhất, không rõ thì DỪNG).
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        product_id: ID sản phẩm (product.product) cần sản xuất.
        qty: Số lượng thành phẩm.
        bom_id: ID định mức (mrp.bom) — 0 = tự tìm.
    """
    try:
        if qty is None or qty <= 0:
            return envelope(False, "Số lượng sản xuất phải lớn hơn 0.")
        prows = odoo("product.product", "search_read",
                     [[["id", "=", product_id]]],
                     {"fields": ["id", "name", "product_tmpl_id"], "limit": 1})
        if not prows:
            return envelope(False, f"Không tìm thấy sản phẩm ID {product_id}.")
        product = prows[0]
        # mrp.bom link theo TEMPLATE id — KHÔNG dùng variant id ở domain BoM
        # (trên instance thật template 39 = Table Top ≠ variant 39 = Drawer).
        tmpl_id = product["product_tmpl_id"][0]

        if bom_id:
            brows = odoo("mrp.bom", "search_read", [[["id", "=", bom_id]]],
                         {"fields": ["id", "type", "product_tmpl_id", "active"],
                          "limit": 1})
            if not brows or not brows[0]["active"]:
                return envelope(False, f"Không tìm thấy BoM {bom_id}.")
            bom = brows[0]
            if bom["type"] != "normal":
                return envelope(False,
                                "BoM này là Kit — không sản xuất trực tiếp được.")
            if bom["product_tmpl_id"][0] != tmpl_id:
                return envelope(False, f"BoM {bom_id} không thuộc sản phẩm này.")
        else:
            brows = odoo("mrp.bom", "search_read",
                         [[["product_tmpl_id", "=", tmpl_id],
                           ["type", "=", "normal"], ["active", "=", True]]],
                         {"fields": ["id", "code"], "limit": 10})
            if not brows:
                return envelope(False, "Sản phẩm chưa có định mức (BoM) — cần "
                                       "tạo BoM trong Odoo trước.")
            if len(brows) > 1:
                listing = "\n".join(
                    f"  • BoM {b['id']}: {b.get('code') or '(không mã)'}"
                    for b in brows)
                return envelope(False, f"Sản phẩm có nhiều BoM:\n{listing}\n"
                                       f"Vui lòng chỉ rõ BoM.")
            bom = brows[0]

        # Vals tối thiểu (probe #1): Odoo tự default uom/picking/locations/
        # date/company/consumption + tự sinh raw moves, finished move, workorders.
        mo_id = odoo("mrp.production", "create",
                     [{"product_id": product_id, "product_qty": float(qty),
                       "bom_id": bom["id"], "origin": "AI Agent"}])
        mo = odoo("mrp.production", "search_read", [[["id", "=", mo_id]]],
                  {"fields": ["id", "name", "state"], "limit": 1})[0]
        return envelope(True,
                        f"Đã tạo lệnh sản xuất {mo['name']} (nháp): "
                        f"{product['name']} × {qty:g}.",
                        ref=mo["name"], model="mrp.production", res_id=mo_id,
                        state="draft")
    except Exception as e:  # noqa: BLE001
        return fail("create_manufacturing_order",
                    f"Lỗi khi tạo lệnh sản xuất — thao tác có thể chưa "
                    f"hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def confirm_manufacturing_order(order_ref: str) -> str:
    """Xác nhận lệnh sản xuất (mrp.production) đang ở trạng thái nháp.
    draft → confirmed. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã lệnh sản xuất, ví dụ "WH/MO/00007".
    """
    try:
        rows = odoo("mrp.production", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy lệnh sản xuất '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False, f"Có nhiều lệnh sản xuất tên '{order_ref}'. "
                                   f"Vui lòng nêu rõ hơn.")
        mo = rows[0]
        name, state = mo["name"], mo["state"]
        if state == "done":
            return envelope(False, f"Lệnh sản xuất {name} đã hoàn tất rồi.")
        if state == "cancel":
            return envelope(False,
                            f"Lệnh sản xuất {name} đã bị hủy, không thể xác nhận.")
        if state != "draft":
            return envelope(False, f"Lệnh sản xuất {name} đã được xác nhận rồi.")
        odoo("mrp.production", "action_confirm", [[mo["id"]]])
        return envelope(True, f"Đã xác nhận lệnh sản xuất {name}.",
                        ref=name, model="mrp.production", res_id=mo["id"],
                        state="confirmed")
    except Exception as e:  # noqa: BLE001
        return fail("confirm_manufacturing_order",
                    f"Lỗi khi xác nhận lệnh sản xuất — thao tác có thể "
                    f"chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def complete_manufacturing_order(order_ref: str) -> str:
    """Hoàn tất lệnh sản xuất ĐÃ XÁC NHẬN: kiểm tra đủ nguyên liệu (từ chối
    rõ ràng nếu thiếu), rồi mark done — tiêu hao nguyên liệu, nhập kho thành
    phẩm. Work order con (nếu có) được Odoo tự hoàn tất. YÊU CẦU XÁC NHẬN từ
    người dùng trước khi gọi.

    Args:
        order_ref: Mã lệnh sản xuất, ví dụ "WH/MO/00007".
    """
    try:
        rows = odoo("mrp.production", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state", "product_id",
                                "product_qty", "move_raw_ids"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy lệnh sản xuất '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False, f"Có nhiều lệnh sản xuất tên '{order_ref}'. "
                                   f"Vui lòng nêu rõ hơn.")
        mo = rows[0]
        name = mo["name"]
        if mo["state"] == "draft":
            return envelope(False, f"Lệnh sản xuất {name} chưa xác nhận. "
                                   f"Hãy xác nhận trước khi hoàn tất.")
        if mo["state"] == "done":
            return envelope(False, f"Lệnh sản xuất {name} đã hoàn tất rồi.")
        if mo["state"] == "cancel":
            return envelope(False, f"Lệnh sản xuất {name} đã bị hủy.")

        def _raw_moves():
            if not mo["move_raw_ids"]:
                return []
            return odoo("stock.move", "search_read",
                        [[["id", "in", mo["move_raw_ids"]]]],
                        {"fields": ["product_id", "product_uom_qty",
                                    "quantity", "state"], "limit": 100})

        # Pre-check tất định (probe #5): thiếu nguyên liệu mà mark done sẽ lộ
        # Fault "Lot/Serial Number" khó hiểu của Odoo — chặn trước, thử reserve
        # đúng 1 lần rồi từ chối với liệt kê rõ ràng.
        moves = _raw_moves()
        short = [m for m in moves if m["state"] not in ("assigned", "done")]
        if short:
            odoo("mrp.production", "action_assign", [[mo["id"]]])
            moves = _raw_moves()
            short = [m for m in moves if m["state"] not in ("assigned", "done")]
        if short:
            listing = "\n".join(
                f"  - {m['product_id'][1]}: cần {m['product_uom_qty']:g}, "
                f"sẵn sàng {m['quantity']:g}" for m in short)
            return envelope(False,
                            f"Chưa đủ nguyên liệu cho {name}:\n{listing}\n"
                            f"Cần nhập thêm nguyên liệu (có thể tạo đơn mua) "
                            f"trước khi hoàn tất.")

        # Probe #3/#4: đủ nguyên liệu → mark done tự set qty_producing, tự
        # hoàn tất workorder. Re-read xác minh (safety net — không claim bừa).
        odoo("mrp.production", "button_mark_done", [[mo["id"]]])
        after = odoo("mrp.production", "search_read", [[["id", "=", mo["id"]]]],
                     {"fields": ["id", "state"], "limit": 1})[0]
        if after["state"] != "done":
            return envelope(False, f"Lệnh sản xuất {name} chưa hoàn tất được "
                                   f"(trạng thái hiện tại: {after['state']}).")
        return envelope(True,
                        f"Đã hoàn tất lệnh sản xuất {name}: nhập kho "
                        f"{mo['product_qty']:g} {mo['product_id'][1]}.",
                        ref=name, model="mrp.production", res_id=mo["id"],
                        state="done")
    except Exception as e:  # noqa: BLE001
        return fail("complete_manufacturing_order",
                    f"Lỗi khi hoàn tất lệnh sản xuất — thao tác có thể "
                    f"chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def create_bom(product_id: int, components: list, batch_qty: float = 1.0,
               code: str = "", is_kit: bool = False) -> str:
    """Tạo định mức nguyên liệu (mrp.bom) MỚI cho một sản phẩm — 'normal'
    (sản xuất trực tiếp) hoặc 'phantom'/Kit (tự nổ thành nguyên liệu khi
    bán, không sản xuất riêng) tùy is_kit. Nhận ID ĐÃ resolve (coordinator
    lo resolve tên). YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        product_id: ID sản phẩm thành phẩm (product.product).
        components: [{"product_id": <id nguyên liệu>, "qty": <số>}, ...].
        batch_qty: Số thành phẩm mỗi mẻ (mặc định 1).
        code: Mã tham chiếu BoM (tùy chọn).
        is_kit: True = tạo BoM Kit (type 'phantom'); False = BoM thường
            (type 'normal', mặc định).
    """
    try:
        components = components or []
        if not components:
            return envelope(False, "Vui lòng cho biết nguyên liệu và số lượng.")
        if batch_qty is None or batch_qty <= 0:
            return envelope(False, "Số lượng mỗi mẻ phải lớn hơn 0.")
        for c in components:
            if not c.get("product_id") or (c.get("qty") or 0) <= 0:
                return envelope(False, "Mỗi nguyên liệu cần ID và số lượng > 0.")
            if c["product_id"] == product_id:
                return envelope(False, "Nguyên liệu không thể là chính thành phẩm.")
        prows = odoo("product.product", "search_read",
                     [[["id", "=", product_id]]],
                     {"fields": ["id", "name", "product_tmpl_id"], "limit": 1})
        if not prows:
            return envelope(False, f"Không tìm thấy sản phẩm ID {product_id}.")
        product = prows[0]
        # mrp.bom link theo TEMPLATE id (bẫy id-space round 4).
        tmpl_id = product["product_tmpl_id"][0]
        vals = {"product_tmpl_id": tmpl_id, "product_qty": float(batch_qty),
                "bom_line_ids": [(0, 0, {"product_id": c["product_id"],
                                         "product_qty": float(c["qty"])})
                                 for c in components]}
        if code:
            vals["code"] = code
        if is_kit:
            vals["type"] = "phantom"
        bom_id = odoo("mrp.bom", "create", [vals])
        bom = odoo("mrp.bom", "search_read", [[["id", "=", bom_id]]],
                   {"fields": ["id", "code"], "limit": 1})[0]
        label = bom.get("code") or f"BoM #{bom_id}"
        return envelope(True,
                        f"Đã tạo BoM {label} cho {product['name']}: "
                        f"{len(components)} nguyên liệu (mẻ {batch_qty:g}).",
                        ref=label, model="mrp.bom", res_id=bom_id, state="active")
    except Exception as e:  # noqa: BLE001
        return fail("create_bom",
                    f"Lỗi khi tạo BoM — thao tác có thể chưa hoàn tất. "
                    f"Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def update_bom_lines(bom_id: int, changes: list) -> str:
    """Sửa danh sách nguyên liệu của một BoM ĐÃ CÓ (normal hoặc Kit). Mỗi change:
    {"action": "add"|"remove"|"set_qty", "product_id": <id>, "qty": <số|None>}.
    Validate toàn bộ trước khi ghi (all-or-nothing). YÊU CẦU XÁC NHẬN trước.

    Args:
        bom_id: ID định mức (mrp.bom).
        changes: Danh sách thay đổi nguyên liệu.
    """
    try:
        changes = changes or []
        if not changes:
            return envelope(False, "Vui lòng cho biết thay đổi cần áp dụng.")
        brows = odoo("mrp.bom", "search_read", [[["id", "=", bom_id]]],
                     {"fields": ["id", "code", "type", "active"], "limit": 1})
        if not brows or not brows[0]["active"]:
            return envelope(False, f"Không tìm thấy BoM {bom_id}.")
        bom = brows[0]
        label = bom.get("code") or f"BoM #{bom_id}"
        lines = odoo("mrp.bom.line", "search_read", [[["bom_id", "=", bom_id]]],
                     {"fields": ["id", "product_id", "product_qty"], "limit": 100})
        by_pid = {l["product_id"][0]: l for l in lines}
        remaining = set(by_pid)          # theo dõi xóa hết
        added_this_call = set()          # bắt add trùng trong CÙNG 1 request
        ops = []
        for ch in changes:
            action = ch.get("action")
            pid = ch.get("product_id")
            qty = ch.get("qty")
            if action == "add":
                if pid in by_pid or pid in added_this_call:
                    return envelope(False, f"Nguyên liệu ID {pid} đã có trong "
                                           f"BoM (hoặc đã được thêm ở một thay "
                                           f"đổi khác trong cùng yêu cầu này) — "
                                           f"dùng set_qty để đổi số lượng.")
                if (qty or 0) <= 0:
                    return envelope(False, "Số lượng thêm phải lớn hơn 0.")
                ops.append((0, 0, {"product_id": pid, "product_qty": float(qty)}))
                added_this_call.add(pid)
            elif action == "set_qty":
                if pid not in by_pid:
                    return envelope(False, f"Nguyên liệu ID {pid} chưa có trong "
                                           f"BoM. Nguyên liệu hiện có: "
                                           f"{sorted(by_pid)}.")
                if (qty or 0) <= 0:
                    return envelope(False, "Số lượng phải lớn hơn 0.")
                ops.append((1, by_pid[pid]["id"], {"product_qty": float(qty)}))
            elif action == "remove":
                if pid not in by_pid:
                    return envelope(False, f"Nguyên liệu ID {pid} chưa có trong "
                                           f"BoM. Nguyên liệu hiện có: "
                                           f"{sorted(by_pid)}.")
                ops.append((2, by_pid[pid]["id"], 0))
                remaining.discard(pid)
            else:
                return envelope(False, f"Thao tác '{action}' không hợp lệ.")
        if not remaining and not any(o[0] == 0 for o in ops):
            return envelope(False, "BoM phải còn ít nhất 1 nguyên liệu.")
        odoo("mrp.bom", "write", [[bom_id], {"bom_line_ids": ops}])
        after = odoo("mrp.bom.line", "search_read", [[["bom_id", "=", bom_id]]],
                     {"fields": ["id"], "limit": 100})
        return envelope(True, f"Đã cập nhật BoM {label}: {len(after)} nguyên liệu.",
                        ref=label, model="mrp.bom", res_id=bom_id, state="active")
    except Exception as e:  # noqa: BLE001
        return fail("update_bom_lines",
                    f"Lỗi khi sửa BoM — thao tác có thể chưa hoàn tất. "
                    f"Nếu lặp lại, báo quản trị viên.", e)
