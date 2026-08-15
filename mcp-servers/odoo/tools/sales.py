"""Tool MCP domain Sales (sale.order) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo(); helper resolve/apply dùng chung
nhiều domain (_resolve_partner, _resolve_product, _apply_line_ops,
_validate_order_pickings) nằm ở helpers.py — xem docstring ở đó để biết vì
sao chúng không nằm trong module domain nào.

flag_order_for_review: tool nhận model tham số ("sale.order" | "purchase.order")
nên về bản chất dùng chung cả sales lẫn purchase — không có tool nào khác gọi
nó ở tầng code (chỉ tầng điều phối/LLM gợi ý dùng sau khi update_quotation_lines/
update_rfq_lines từ chối sửa đơn đã xác nhận), nên nó không hội đủ điều kiện để
chuyển vào helpers.py như 5 helper resolve/apply. Đây là quyết định thủ công do
không có tín hiệu domain nào mạnh hơn — đặt tại sales.py.
"""
from server import mcp
from odoo_call import odoo
from helpers import envelope, fail, _resolve_partner, _resolve_product, _apply_line_ops, \
    _validate_order_pickings


@mcp.tool()
def confirm_sale_order(order_ref: str) -> str:
    """
    Xác nhận một đơn bán hàng (sale.order) đang ở trạng thái nháp.
    draft/sent → sale. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn bán, ví dụ "S00012".
    """
    try:
        rows = odoo("sale.order", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False, f"Có nhiều đơn tên '{order_ref}'. Vui lòng nêu rõ hơn.")

        order = rows[0]
        name, state = order["name"], order["state"]
        if state in ("sale", "done"):
            return envelope(False, f"Đơn {name} đã được xác nhận rồi.")
        if state == "cancel":
            return envelope(False, f"Đơn {name} đã bị hủy, không thể xác nhận.")

        odoo("sale.order", "action_confirm", [[order["id"]]])
        return envelope(True, f"Đã xác nhận đơn {name}.",
                        ref=name, model="sale.order", res_id=order["id"], state="sale")
    except Exception as e:  # noqa: BLE001 — không exception nào xuyên qua MCP tool
        return fail("confirm_sale_order",
                    f"Lỗi khi xác nhận đơn {order_ref} — thao tác có thể "
                    f"chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def deliver_order(order_ref: str) -> str:
    """Giao hàng cho một đơn bán ĐÃ XÁC NHẬN: xác nhận mọi phiếu xuất kho
    (stock.picking) đã reserve đủ của đơn. Đơn không có phiếu cần giao
    (dịch vụ / đã giao đủ) được coi là hoàn tất — chuỗi đi tiếp bước
    tạo hóa đơn. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn bán, ví dụ "S00012".
    """
    try:
        rows = odoo("sale.order", "search_read",
                    [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state", "picking_ids"],
                     "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False,
                            f"Có nhiều đơn tên '{order_ref}'. Vui lòng nêu rõ hơn.")

        so = rows[0]
        name = so["name"]
        if so["state"] not in ("sale", "done"):
            return envelope(False, f"Đơn {name} chưa xác nhận (trạng thái nháp). "
                                   f"Hãy xác nhận đơn trước khi giao hàng.")

        status, val = _validate_order_pickings(so["picking_ids"], "outgoing")
        if status == "none":
            # Pass-through: dịch vụ / giao ngay / đã giao đủ — chuỗi vẫn mời
            # bước "Tạo hóa đơn" tiếp theo.
            return envelope(True, f"Đơn {name} không có phiếu cần giao "
                                  f"(dịch vụ hoặc đã giao đủ).",
                            ref=name, model="sale.order", res_id=so["id"],
                            state="sale")
        if status == "not_ready":
            return envelope(False,
                            f"Phiếu giao của đơn {name} chưa reserve đủ hàng "
                            f"(trạng thái: {val}). Kiểm tra tồn kho trước khi giao.")
        if status == "wizard":
            return envelope(False,
                            f"Phiếu {val} cần thao tác bổ sung trên Odoo "
                            f"(wizard không hỗ trợ qua API). Vui lòng xử lý trực tiếp.")
        return envelope(True, f"Đã giao hàng cho đơn {name} ({val} phiếu).",
                        ref=name, model="sale.order", res_id=so["id"], state="sale")
    except Exception as e:  # noqa: BLE001 — không exception nào xuyên qua MCP tool
        return fail("deliver_order",
                    f"Lỗi khi giao hàng cho đơn {order_ref} — thao tác có "
                    f"thể chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def create_quotation(partner_name: str = "", lines: list | None = None,
                     partner_id: int = 0) -> str:
    """Tạo báo giá nháp (sale.order) cho một khách hàng với các dòng sản phẩm.
    Ưu tiên ID đã resolve (partner_id, mỗi dòng product_id); nếu vắng ID thì
    resolve theo tên (partner_name, mỗi dòng product). Nếu có gì không rõ thì
    DỪNG, không tạo đơn dở. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        partner_name: Tên khách hàng (tìm gần đúng) — dùng khi không có partner_id.
        lines: Danh sách dòng hàng, mỗi dòng {"product": "<tên>", "qty": <số>} hoặc
               {"product_id": <id>, "qty": <số>}, có thể kèm "price_unit": <số>
               (giá đã xác nhận với người dùng — nếu vắng, Odoo tự tính theo
               bảng giá của khách, có thể LỆCH với giá đã hỏi xác nhận).
        partner_id: ID khách hàng đã resolve (ưu tiên hơn partner_name).
    """
    lines = lines or []
    try:
        if not lines:
            return envelope(False, "Vui lòng cho biết sản phẩm và số lượng cần báo giá.")

        if partner_id:
            prows = odoo("res.partner", "read", [[partner_id]], {"fields": ["id", "name"]})
            if not prows:
                return envelope(False, f"Không tìm thấy khách hàng ID {partner_id}.")
            partner = prows[0]
        else:
            partner, msg = _resolve_partner(partner_name, "khách hàng",
                                            "Vui lòng nêu rõ tên khách hàng.")
            if msg:
                return envelope(False, msg)

        order_line = []
        for line in lines:
            pid = line.get("product_id")
            price_unit = line.get("price_unit")
            if pid:
                vals = {"product_id": pid, "product_uom_qty": line["qty"]}
                if price_unit is not None:
                    vals["price_unit"] = price_unit
                order_line.append((0, 0, vals))
                continue
            prod, pmsg = _resolve_product(line["product"], "sale_ok")
            if pmsg:
                return envelope(False, pmsg)
            vals = {"product_id": prod["id"], "product_uom_qty": line["qty"]}
            if price_unit is not None:
                vals["price_unit"] = price_unit
            order_line.append((0, 0, vals))

        sid = odoo("sale.order", "create",
                   [{"partner_id": partner["id"], "order_line": order_line}])
        so = odoo("sale.order", "read", [[sid]], {"fields": ["name"]})
        name = so[0]["name"] if so else "?"
        return envelope(True,
                        f"Đã tạo báo giá {name} (nháp) cho {partner['name']} ({len(lines)} dòng).",
                        ref=name, model="sale.order", res_id=sid, state="draft")
    except Exception as e:  # noqa: BLE001 — không exception nào xuyên qua MCP tool
        return fail("create_quotation",
                    f"Lỗi khi tạo báo giá cho {partner_name} — thao tác có "
                    f"thể chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


@mcp.tool()
def update_quotation_lines(order_ref: str, ops: list | None = None) -> str:
    """Sửa dòng hàng của BÁO GIÁ (sale.order). Chỉ áp dụng được cho đơn nháp
    (draft/sent); nếu đơn đã xác nhận, tool trả về lỗi và tầng điều phối sẽ đề nghị
    ghi chú nội bộ. ops đã resolve theo ID; coordinator dựng ops, KHÔNG để LLM tự dựng.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        order_ref: Mã đơn bán, ví dụ "S00012".
        ops: [{"op":"add","product_id":int,"qty":float} |
              {"op":"remove","line_id":int} |
              {"op":"set_qty","line_id":int,"qty":float}]
    """
    try:
        return _apply_line_ops("sale.order", "product_uom_qty", order_ref, ops or [])
    except Exception as e:  # noqa: BLE001
        return fail("update_quotation_lines",
                    f"Lỗi khi sửa báo giá {order_ref} — thao tác có thể "
                    f"chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)


_FLAGGABLE_MODELS = ("sale.order", "purchase.order")


@mcp.tool()
def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
    """Ghi một ghi chú nội bộ (message_post) lên chatter của đơn để báo quản lý —
    dùng khi đơn ĐÃ xác nhận không sửa trực tiếp được. Chỉ áp dụng cho sale.order /
    purchase.order (Invariant #6).

    Args:
        model: "sale.order" | "purchase.order".
        order_ref: Mã đơn, ví dụ "S00012" / "P00003".
        note: Nội dung ghi chú (tiếng Việt).
    """
    try:
        if model not in _FLAGGABLE_MODELS:
            return envelope(False, "Model không được hỗ trợ.")
        rows = odoo(model, "search_read", [[["name", "=", order_ref]]],
                    {"fields": ["id", "name", "state"], "limit": 2})
        if not rows:
            return envelope(False, f"Không tìm thấy đơn '{order_ref}'.")
        if len(rows) > 1:
            return envelope(False, f"Có nhiều đơn tên '{order_ref}'. Vui lòng nêu rõ hơn.")
        order = rows[0]
        # message_post may return a recordset that XML-RPC can't marshal (gateway
        # then returns None post-commit). We don't use the return value.
        odoo(model, "message_post", [[order["id"]]], {"body": note})
        return envelope(True,
                        f"Đã ghi chú nội bộ trên đơn {order['name']} để báo quản lý.",
                        ref=order["name"], model=model, res_id=order["id"],
                        state=order["state"])
    except Exception as e:  # noqa: BLE001
        return fail("flag_order_for_review",
                    f"Lỗi khi ghi chú đơn {order_ref} — thao tác có thể "
                    f"chưa hoàn tất. Nếu lặp lại, báo quản trị viên.", e)
