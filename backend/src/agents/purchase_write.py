# backend/src/agents/purchase_write.py
"""Deterministic Purchasing coordinators (tier-1): create_vendor /
update_vendor_pricing / create_bulk_rfq. Resolve NCC/sản phẩm bằng
slot-filling + disambig interrupt (pattern create_order.py/returns_write.py).
create_vendor CÓ NEXT_STEPS → update_vendor_pricing (gợi ý mềm, round 7
pattern: vừa tạo NCC, gợi ý khai giá luôn). update_vendor_pricing và
create_bulk_rfq TERMINAL (không NEXT_STEPS) — không có 1 next-step tự nhiên
duy nhất sau khi khai giá (update_vendor_pricing), hoặc khi tạo N đơn cùng
lúc (create_bulk_rfq — N ref không gói vừa envelope 1-ref). Xem
docs/superpowers/specs/2026-07-23-vendor-pricing-bulk-rfq-design.md."""
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import (resolve_entity_for_order, _by_id, _ttl_expiry, _msg,
                           _disambig_q, WRITE_DISABLED_MSG)
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX
from ..erp_query import inventory, purchase


def _finish(tool_name: str, result) -> dict:
    display, env = parse_write_result(result)
    return {**_msg(display), "pending_action": None,
            "last_write": {"tool": tool_name, **env} if env else None}


def _resolve_vendor(ref: str):
    """Resolve 1 tên NCC → ('ok', {'id','name'}) | ('msg', <dict return ngay>)."""
    kind, val = resolve_entity_for_order(purchase.find_supplier(ref), ref)
    if kind == "error":
        return "msg", _msg(val)
    if kind == "none":
        return "msg", _msg(f"Không tìm thấy nhà cung cấp '{ref}'.")
    if kind == "ambiguous":
        chosen = _interrupt({"kind": "disambiguation",
                             "question": _disambig_q("nhà cung cấp", val),
                             "options": val, "expires_at": _ttl_expiry()})
        picked = _by_id(val, chosen)
        if picked is None:
            return "msg", _msg("Đã hủy.")
        return "ok", picked
    return "ok", val


def _resolve_product(ref: str):
    """Resolve 1 tên sản phẩm → ('ok', {'id','name'}) | ('msg', <dict>).
    Lặp pattern bom_write.py/returns_write.py's _resolve_product có chủ đích
    (không import chéo bounded context)."""
    kind, val = resolve_entity_for_order(inventory.find_product(ref), ref)
    if kind == "error":
        return "msg", _msg(val)
    if kind == "none":
        return "msg", _msg(f"Không tìm thấy sản phẩm '{ref}'.")
    if kind == "ambiguous":
        chosen = _interrupt({"kind": "disambiguation",
                             "question": _disambig_q(f"sản phẩm '{ref}'", val),
                             "options": val, "expires_at": _ttl_expiry()})
        picked = _by_id(val, chosen)
        if picked is None:
            return "msg", _msg("Đã hủy.")
        return "ok", picked
    return "ok", val


def make_create_vendor_node(tools):
    by_name = {t.name: t for t in tools}

    async def create_vendor_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        name = str(args.get("name") or "").strip()
        email = str(args.get("email") or "").strip()
        phone = str(args.get("phone") or "").strip()
        vat = str(args.get("vat") or "").strip()
        street = str(args.get("street") or "").strip()
        city = str(args.get("city") or "").strip()
        if not name:
            return _msg("Bạn cần cho biết tên nhà cung cấp để mình tạo hồ sơ.")

        denv = purchase.find_vendor_duplicates(name, email or None)
        rows = (denv.get("data") or {}).get("rows") or []
        dup_note = ""
        if rows:
            names = "; ".join(f"'{r['name']}'" for r in rows)
            dup_note = f"\n  ⚠ Đã có NCC tên gần giống: {names}"

        note = (state.get("pending_action") or {}).get("chain_note") or ""
        draft = (f"Tạo nhà cung cấp mới:\n"
                 f"  Tên: {name}\n"
                 f"  Email: {email or '—'} | SĐT: {phone or '—'}\n"
                 f"  MST: {vat or '—'} | Địa chỉ: {street or '—'}, {city or '—'}"
                 f"{dup_note}{note}\n" + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy tạo nhà cung cấp.")

        tool = by_name.get("create_vendor")
        if tool is None:
            return _msg("Công cụ tạo nhà cung cấp không khả dụng.")
        try:
            result = await tool.ainvoke({"name": name, "email": email, "phone": phone,
                                         "vat": vat, "street": street, "city": city})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi tạo nhà cung cấp: {e}")
        return _finish("create_vendor", result)

    return create_vendor_node


def make_update_vendor_pricing_node(tools):
    by_name = {t.name: t for t in tools}

    async def update_vendor_pricing_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        vendor_ref = str(args.get("vendor_name") or "").strip()
        product_ref = str(args.get("product") or "").strip()
        try:
            price = float(args.get("price"))
        except (TypeError, ValueError):
            price = None
        min_qty_raw = args.get("min_qty")
        delay_raw = args.get("delay")
        min_qty = None
        if min_qty_raw is not None:
            try:
                min_qty = float(min_qty_raw)
            except (TypeError, ValueError):
                return _msg("Số lượng tối thiểu không hợp lệ.")
        delay = None
        if delay_raw is not None:
            try:
                delay = int(delay_raw)
            except (TypeError, ValueError):
                return _msg("Thời gian giao hàng không hợp lệ.")
        if not vendor_ref:
            return _msg("Bạn cần cho biết nhà cung cấp để khai giá.")
        if not product_ref:
            return _msg("Bạn cần cho biết sản phẩm cần khai giá.")
        if price is None or price <= 0:
            return _msg("Bạn cần cho biết đơn giá (lớn hơn 0).")

        vkind, vendor = _resolve_vendor(vendor_ref)
        if vkind == "msg":
            return vendor
        pkind, product = _resolve_product(product_ref)
        if pkind == "msg":
            return product

        extra_txt = ""
        if min_qty is not None:
            extra_txt += f" | tối thiểu {float(min_qty):g}"
        if delay is not None:
            extra_txt += f" | giao trong {int(delay)} ngày"
        draft = (f"Khai giá {product['name']} từ {vendor['name']}: "
                 f"{price:,.0f}đ{extra_txt}.\n" + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy khai giá.")

        tool = by_name.get("update_vendor_pricing")
        if tool is None:
            return _msg("Công cụ khai giá nhà cung cấp không khả dụng.")
        try:
            call_args = {"partner_id": vendor["id"], "product_id": product["id"],
                        "price": price}
            if min_qty is not None:
                call_args["min_qty"] = float(min_qty)
            if delay is not None:
                call_args["delay"] = int(delay)
            result = await tool.ainvoke(call_args)
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi khai giá nhà cung cấp: {e}")
        return _finish("update_vendor_pricing", result)

    return update_vendor_pricing_node


def make_create_bulk_rfq_node(tools):
    by_name = {t.name: t for t in tools}

    async def create_bulk_rfq_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        raw_vendors = args.get("vendor_names") or []
        raw_lines = args.get("lines") or []
        if not raw_vendors:
            return _msg("Bạn cần cho biết (các) nhà cung cấp cần gửi RFQ.")
        if len(raw_vendors) > 10:
            return _msg("Tối đa 10 nhà cung cấp mỗi lần — vui lòng chia nhỏ yêu cầu.")
        if not raw_lines:
            return _msg("Bạn cần cho biết sản phẩm và số lượng cần đặt mua.")

        vendors = []
        for vref in raw_vendors:
            vkind, vendor = _resolve_vendor(str(vref).strip())
            if vkind == "msg":
                return vendor
            vendors.append(vendor)

        lines, lines_txt = [], []
        for line in raw_lines:
            ref = str(line.get("product") or "").strip()
            try:
                q = float(line.get("qty") or 0)
            except (TypeError, ValueError):
                q = 0.0
            if not ref or q <= 0:
                return _msg("Mỗi dòng hàng cần tên sản phẩm và số lượng lớn hơn 0.")
            pkind, product = _resolve_product(ref)
            if pkind == "msg":
                return product
            lines.append({"product_id": product["id"], "qty": q})
            lines_txt.append(f"  - {product['name']} × {q:g}")

        vendor_names = ", ".join(v["name"] for v in vendors)
        draft = (f"Tạo {len(vendors)} RFQ nháp cho: {vendor_names}\n"
                 + "\n".join(lines_txt) + "\n" + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy tạo RFQ hàng loạt.")

        tool = by_name.get("create_bulk_rfq")
        if tool is None:
            return _msg("Công cụ tạo RFQ hàng loạt không khả dụng.")
        try:
            result = await tool.ainvoke({
                "partner_ids": [v["id"] for v in vendors], "lines": lines})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi tạo RFQ hàng loạt: {e}")
        return _finish("create_bulk_rfq", result)

    return create_bulk_rfq_node
