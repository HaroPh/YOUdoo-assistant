# backend/src/agents/invoice_write.py
"""Coordinator cho hai thao tác đụng tiền: post_invoice (phát hành hóa đơn
nháp) và register_payment (ghi nhận thanh toán).

VÌ SAO CẦN COORDINATOR RIÊNG (spec 2026-08-06 §1.1): nhánh fallback chung của
erp_write_planner chỉ hiện "(post_invoice: partner_name=Acme)" — người dùng
xác nhận mà KHÔNG biết hóa đơn nào, bao nhiêu tiền. Đo thật trên Odoo
2026-08-06: 5 hóa đơn nháp đều của cùng "Acme Corporation", 4 cái trùng y hệt
số tiền, và hóa đơn nháp chưa có số (name=False). Lỗi mơ hồ của tool chỉ hiện
ra SAU khi người dùng đã bấm xác nhận — với thao tác đụng tiền thì đó là lỗ
hổng an toàn, không phải vấn đề thẩm mỹ.

LUÔN gọi tool bằng invoice_id đã resolve: nhánh `if invoice_id:` của tool
(mcp-servers/odoo/tools/accounting.py:29-51) bỏ qua hoàn toàn phần resolve
của chính nó, nên lúc chạy chỉ có ĐÚNG MỘT phép resolve — logic trùng không
phải hai resolver chạy đua rồi lệch nhau (spec §5.1). Đây là đường tool đã
dành sẵn: docstring gọi invoice_id là "đường nội bộ", ưu tiên hơn partner_name.
"""
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import (_by_id, _ttl_expiry, _msg, _disambig_q,
                           WRITE_DISABLED_MSG)
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX
from ..erp_query import accounting


def _finish(tool_name: str, result) -> dict:
    display, env = parse_write_result(result)
    return {**_msg(display), "pending_action": None,
            "last_write": {"tool": tool_name, **env} if env else None}


def render_invoice_summary(head: str, lines: list, totals: list) -> str:
    """Bảng tóm tắt hóa đơn, khớp khuôn render_draft của create_order.py.

    Tên hiển thị lấy từ product_id[1], KHÔNG lấy line["name"]: đo thật thấy
    trường đó chứa mô tả nhiều dòng ('[FURN_0789] Individual Workplace\\n...'),
    hiển thị nguyên sẽ vỡ bảng."""
    body = [f"  - {(l.get('product_id') or [0, '?'])[1]}"
            f" × {(l.get('quantity') or 0):g}"
            f" = {(l.get('price_subtotal') or 0):,.0f}" for l in lines]
    return "\n".join([head, *body, *totals]) + "\n" + WRITE_CONFIRM_SUFFIX


def _invoice_label(r: dict) -> str:
    """Nhãn chọn trong disambig. PHẢI có số tiền + ngày: hóa đơn nháp không
    có số nên chỉ tên đối tác thì không phân biệt được."""
    partner = (r.get("partner_id") or [0, "?"])[1]
    return (f"{r.get('name') or 'chưa có số'} — {partner}"
            f" — {(r.get('amount_total') or 0):,.0f}"
            f" — {r.get('invoice_date') or 'chưa có ngày'}")


def _pick_invoice(env: dict, label: str):
    """envelope find_*_invoices → ('ok', <row>) | ('msg', <state update>).
    Nhiều kết quả → disambig interrupt (pattern _resolve_product của
    returns_write.py)."""
    if env.get("status") != "success":
        return "msg", _msg(env.get("display") or "Lỗi tra cứu hóa đơn.")
    rows = (env.get("data") or {}).get("rows") or []
    if not rows:
        return "msg", _msg("Không tìm thấy hóa đơn phù hợp.")
    if len(rows) == 1:
        return "ok", rows[0]
    options = [{"id": r["id"], "name": _invoice_label(r)} for r in rows]
    chosen = _interrupt({"kind": "disambiguation",
                         "question": _disambig_q(label, options),
                         "options": options, "expires_at": _ttl_expiry()})
    picked = _by_id(options, chosen)
    if picked is None:
        return "msg", _msg("Đã hủy.")
    return "ok", next(r for r in rows if r["id"] == picked["id"])


def _detail_or_msg(invoice_id: int):
    """→ ('ok', (inv, lines)) | ('msg', <state update>)."""
    env = accounting.get_invoice_detail(invoice_id)
    if env.get("status") != "success":
        return "msg", _msg(env.get("display") or "Lỗi tra chi tiết hóa đơn.")
    data = env.get("data") or {}
    return "ok", (data.get("invoice") or {}, data.get("lines") or [])


def make_post_invoice_node(tools):
    by_name = {t.name: t for t in tools}

    async def post_invoice_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        invoice_id = args.get("invoice_id") or 0

        if not invoice_id:
            partner_name = str(args.get("partner_name") or "").strip()
            if not partner_name:
                return _msg("Bạn cần cho biết khách hàng (hoặc ID) của hóa đơn nháp.")
            kind, val = _pick_invoice(
                accounting.find_draft_invoices(partner_name, args.get("amount"),
                                               args.get("invoice_date")),
                "hóa đơn nháp")
            if kind == "msg":
                return val
            invoice_id = val["id"]

        kind, val = _detail_or_msg(invoice_id)
        if kind == "msg":
            return val
        inv, lines = val

        partner = (inv.get("partner_id") or [0, "?"])[1]
        head = (f"Hóa đơn nháp của {partner} — ngày "
                f"{inv.get('invoice_date') or 'chưa có'}:")
        draft = render_invoice_summary(
            head, lines, [f"  Tổng: {(inv.get('amount_total') or 0):,.0f}"])
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy phát hành hóa đơn.")

        tool = by_name.get("post_invoice")
        if tool is None:
            return _msg("Công cụ phát hành hóa đơn không khả dụng.")
        try:
            result = await tool.ainvoke({"invoice_id": invoice_id})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi phát hành hóa đơn: {e}")
        return _finish("post_invoice", result)

    return post_invoice_node
