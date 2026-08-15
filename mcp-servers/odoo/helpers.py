"""Generic response/formatting helpers dùng chung bởi các MCP tool (spec
2026-07-13-mcp-server-modularization).

Ngoài các helper thuần format (now_iso/today_iso/resolve_unique/envelope),
module này còn giữ 5 helper resolve/apply GỌI odoo() nhưng lại được DÙNG
CHUNG bởi tool ở nhiều domain khác nhau (spec SP-1B §3c task 7):
  - _resolve_partner    — sales, purchase, accounting
  - _resolve_product     — sales, purchase, inventory, accounting
  - _resolve_location    — inventory (nhiều tool)
  - _apply_line_ops      — sales (update_quotation_lines) + purchase (update_rfq_lines)
  - _validate_order_pickings — sales (deliver_order) + purchase (receive_order)
Nếu đặt bất kỳ cái nào trong 5 helper này vào MỘT file domain rồi để domain
khác import chéo, sẽ tạo tool-to-tool coupling giữa các module — đi ngược
mục đích chẻ theo domain (SP-2 cần cấp cho mỗi specialist agent một tập tool
hẹp, tự chứa). Nên cả 5 nằm ở đây, cạnh envelope/resolve_unique — hạ tầng
dùng chung, không thuộc riêng domain nào."""
import json
import logging
from datetime import datetime, timezone

from event_log import log_mcp_event
from odoo_call import odoo

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def resolve_unique(rows, kind_label, describe, hint=""):
    """Pick a single record from candidate rows, or describe the choices.

    Returns (row, None) when exactly one candidate matches; (None, message)
    when none match or several do. `describe(row)` returns a short
    distinguishing string used in the multi-candidate listing. Reusable by
    any resolution tool.
    """
    if not rows:
        return None, f"Không tìm thấy {kind_label} nào phù hợp."
    if len(rows) == 1:
        return rows[0], None
    listing = "\n".join(f"  • {describe(r)}" for r in rows)
    msg = f"Có nhiều {kind_label}:\n{listing}"
    if hint:
        msg += f"\n{hint}"
    return None, msg

def envelope(ok: bool, display: str, *, ref=None, model=None,
             res_id=None, state=None) -> str:
    """JSON-string result for the invoice-chain tools (create_quotation,
    confirm_sale_order, create_invoice_from_order, post_invoice). The backend
    parses this to drive the write-continuation menu; `display` is the
    user-facing Vietnamese sentence. Non-chain tools keep plain strings."""
    return json.dumps({"ok": ok, "ref": ref, "model": model, "res_id": res_id,
                       "state": state, "display": display}, ensure_ascii=False)


def fail(tool_name: str, display: str, exc: Exception) -> str:
    """Ghi nguyên văn lỗi vào log tiến trình VÀ vệt kiểm toán; trả người dùng
    câu KHÔNG lộ gì.

    Ghi cả hai đích có chủ ý: log_mcp_event im lặng không làm gì khi thiếu
    DATABASE_URL, nên nếu chỉ dựa vào nó thì môi trường không cấu hình DB sẽ
    làm lỗi biến mất hoàn toàn — đúng lỗ hổng đợt này đi đóng.

    Nguyên văn lỗi Odoo KHÔNG được vào `display`: đo 2026-08-14, lỗi phân
    quyền của Odoo liệt kê đầy đủ danh sách nhóm được phép, kể cả nhóm tự tạo
    của dự án.
    """
    detail = f"{type(exc).__name__}: {exc}"
    logger.exception("tool %s thất bại: %s", tool_name, detail)
    log_mcp_event("tool_error", tool_name=tool_name, error_code="E500",
                  error_message=detail)
    return envelope(False, display)


# ─── Helper resolve/apply dùng chung nhiều domain (xem docstring module) ─────

def _resolve_partner(name, kind_label, hint):
    """Resolve a partner name → unique row via the disambiguation pattern.
    Lenient (no rank filter); returns (row, None) or (None, listing/not-found msg)."""
    rows = odoo("res.partner", "search_read",
                [[["name", "ilike", name]]],
                {"fields": ["id", "name", "email"], "limit": 6})
    return resolve_unique(
        rows, kind_label,
        describe=lambda r: f"{r['name']} — {r.get('email') or '—'}",
        hint=hint)


def _resolve_product(term, ok_field):
    """Resolve a product name/code → unique row. `ok_field` ANDs a flag clause:
    'sale_ok' (SO), 'purchase_ok' (PO), or 'is_storable' (inventory)."""
    rows = odoo("product.product", "search_read",
                [["|", ["name", "ilike", term],
                      ["default_code", "ilike", term],
                  [ok_field, "=", True]]],
                {"fields": ["id", "name", "default_code", "list_price"],
                 "limit": 6})
    return resolve_unique(
        rows, f"sản phẩm '{term}'",
        describe=lambda r: (f"{r['name']} [{r.get('default_code') or '-'}] "
                            f"— {r['list_price']:,.0f}đ"),
        hint="Vui lòng nêu rõ tên sản phẩm.")


def _resolve_location(name: str | None):
    """Resolve a location name → unique {'id','complete_name'} row. Empty
    name → the default warehouse's main stock location. Returns (loc, None)
    on success, (None, error_message) otherwise."""
    if not name:
        wh = odoo("stock.warehouse", "search_read", [[]],
                  {"fields": ["lot_stock_id"], "limit": 1})
        if not wh:
            return None, "Không tìm thấy kho mặc định."
        return {"id": wh[0]["lot_stock_id"][0],
                "complete_name": wh[0]["lot_stock_id"][1]}, None
    # Odoo builds stock.location.complete_name from the warehouse's short
    # CODE ("WH/Stock"), not its human display name — so a user naming
    # their warehouse by its real name never matches on complete_name
    # alone. Also search stock.warehouse.name and fold in its internal
    # stock location as a candidate.
    wh_rows = odoo("stock.warehouse", "search_read",
                   [[["name", "ilike", name]]],
                   {"fields": ["id", "name", "lot_stock_id"], "limit": 6})
    lrows = odoo("stock.location", "search_read",
                 [[["usage", "=", "internal"],
                   ["complete_name", "ilike", name]]],
                 {"fields": ["id", "complete_name"], "limit": 6})
    candidates = {}
    for w in wh_rows:
        if w.get("lot_stock_id"):
            lid, lname = w["lot_stock_id"]
            candidates[lid] = {"id": lid, "complete_name": lname}
    for r in lrows:
        candidates.setdefault(r["id"], {"id": r["id"], "complete_name": r["complete_name"]})
    return resolve_unique(
        list(candidates.values()), "vị trí kho",
        describe=lambda r: r["complete_name"],
        hint="Vui lòng nêu rõ tên vị trí kho.")


_EDITABLE_STATES = ("draft", "sent")


def _apply_line_ops(model: str, qty_field: str, order_ref: str, ops: list) -> str:
    """Validate + apply o2m commands to a DRAFT order's lines. Shared body for
    update_quotation_lines / update_rfq_lines — each passes its own model +
    qty_field (Invariant #1). State-gate here is the real gate (Invariant #4)."""
    rows = odoo(model, "search_read", [[["name", "=", order_ref]]],
                {"fields": ["id", "name", "state"], "limit": 2})
    if not rows:
        return envelope(False, f"Không tìm thấy đơn '{order_ref}'.")
    if len(rows) > 1:
        return envelope(False, f"Có nhiều đơn tên '{order_ref}'. Vui lòng nêu rõ hơn.")
    order = rows[0]
    name, state = order["name"], order["state"]
    if state not in _EDITABLE_STATES:
        return envelope(False, f"Đơn {name} đã xác nhận, không thể sửa.")
    if not ops:
        return envelope(False, "Không có thay đổi nào để áp dụng.")

    cmds = []
    for op in ops:
        kind = op.get("op")
        if kind == "add":
            pid, qty = op.get("product_id"), op.get("qty")
            if not isinstance(pid, int) or not isinstance(qty, (int, float)) or qty <= 0:
                return envelope(False, "Lệnh thêm dòng không hợp lệ.")
            cmds.append((0, 0, {"product_id": pid, qty_field: qty}))
        elif kind == "remove":
            lid = op.get("line_id")
            if not isinstance(lid, int):
                return envelope(False, "Lệnh xóa dòng không hợp lệ.")
            cmds.append((2, lid, 0))
        elif kind == "set_qty":
            lid, qty = op.get("line_id"), op.get("qty")
            if not isinstance(lid, int) or not isinstance(qty, (int, float)) or qty <= 0:
                return envelope(False, "Lệnh đổi số lượng không hợp lệ.")
            cmds.append((1, lid, {qty_field: qty}))
        else:
            return envelope(False, f"Thao tác không hỗ trợ: {kind!r}.")

    odoo(model, "write", [[order["id"]], {"order_line": cmds}])
    label = "báo giá" if model == "sale.order" else "đơn mua"
    return envelope(True, f"Đã sửa {label} {name} ({len(cmds)} thay đổi).",
                    ref=name, model=model, res_id=order["id"], state=state)


def _validate_order_pickings(picking_ids, type_code):
    """Validate mọi phiếu `assigned` (đã sẵn sàng) của một đơn, lọc theo
    picking_type_code ("outgoing" = giao, "incoming" = nhận). Trả (status, val):
      ("none", None)            — không còn phiếu chờ → caller pass-through
      ("not_ready", states_str) — có phiếu chờ nhưng chưa phiếu nào assigned
      ("wizard", picking_name)  — button_validate trả dict → DỪNG ngay
      ("done", k)               — đã validate k phiếu
    Wording nằm ở call-site — helper không dựng thông điệp người dùng."""
    pickings = []
    if picking_ids:
        pickings = odoo("stock.picking", "search_read",
                        [[["id", "in", picking_ids],
                          ["picking_type_code", "=", type_code]]],
                        {"fields": ["id", "name", "state"]})
    pending = [p for p in pickings if p["state"] not in ("done", "cancel")]
    if not pending:
        return "none", None
    assigned = [p for p in pending if p["state"] == "assigned"]
    if not assigned:
        return "not_ready", ", ".join(sorted({p["state"] for p in pending}))
    for p in assigned:
        # Odoo 19: phiếu 'assigned' đã auto-set done-qty nên button_validate
        # chạy thẳng; dict trả về = wizard → dừng an toàn.
        result = odoo("stock.picking", "button_validate", [[p["id"]]])
        if isinstance(result, dict):
            return "wizard", p["name"]
    return "done", len(assigned)
