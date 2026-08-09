# backend/src/agents/write_registry.py
"""Single source of truth for coordinated write flows. Adding a coordinated write =
one row here; the planner branch, router, and graph registration all read it."""

from dataclasses import dataclass
from typing import Callable

from .create_order import make_order_node, SALE_CFG, PURCHASE_CFG
from .edit_order import make_edit_order_node, SALE_EDIT_CFG, PURCHASE_EDIT_CFG
from .inventory_write import make_inventory_node, make_internal_transfer_node, make_scrap_product_node
from .crm_write import make_create_lead_node, make_convert_lead_node, make_log_activity_node
from .mrp_write import make_create_mo_node
from .bom_write import make_create_bom_node, make_update_bom_node
from .returns_write import make_return_order_node, make_create_credit_memo_node
from .invoice_write import make_post_invoice_node, make_register_payment_node
from .mail_write import make_send_template_email_preview_node, ORDER_CONFIRMATION_CFG
from .purchase_write import (make_create_vendor_node, make_update_vendor_pricing_node,
                             make_create_bulk_rfq_node)


@dataclass(frozen=True)
class Spec:
    node: str                 # graph node name
    build: Callable           # (llm, tools) -> node


WRITE_COORDINATORS = {
    "create_quotation":     Spec("create_order",    lambda llm, tools: make_order_node(tools, SALE_CFG)),
    "create_rfq":           Spec("create_rfq",      lambda llm, tools: make_order_node(tools, PURCHASE_CFG)),
    "update_quotation_lines": Spec("edit_order", lambda llm, tools: make_edit_order_node(tools, SALE_EDIT_CFG)),
    "update_rfq_lines":       Spec("edit_rfq",   lambda llm, tools: make_edit_order_node(tools, PURCHASE_EDIT_CFG)),
    "inventory_adjustment": Spec("inventory_adjust", lambda llm, tools: make_inventory_node(tools)),
    "internal_transfer": Spec("internal_transfer", lambda llm, tools: make_internal_transfer_node(tools)),
    "scrap_product":     Spec("scrap_product",     lambda llm, tools: make_scrap_product_node(tools)),
    "create_lead":  Spec("crm_create_lead",  lambda llm, tools: make_create_lead_node(tools)),
    "convert_lead": Spec("crm_convert_lead", lambda llm, tools: make_convert_lead_node(tools)),
    "log_activity": Spec("crm_log_activity", lambda llm, tools: make_log_activity_node(tools)),
    "create_manufacturing_order": Spec("create_mo", lambda llm, tools: make_create_mo_node(tools)),
    "create_bom":       Spec("create_bom", lambda llm, tools: make_create_bom_node(tools)),
    "update_bom_lines": Spec("update_bom", lambda llm, tools: make_update_bom_node(tools)),
    "return_order":       Spec("return_order",       lambda llm, tools: make_return_order_node(tools)),
    "create_credit_memo": Spec("create_credit_memo", lambda llm, tools: make_create_credit_memo_node(tools)),
    "create_vendor":          Spec("create_vendor",         lambda llm, tools: make_create_vendor_node(tools)),
    "update_vendor_pricing":  Spec("update_vendor_pricing", lambda llm, tools: make_update_vendor_pricing_node(tools)),
    "create_bulk_rfq":        Spec("create_bulk_rfq",       lambda llm, tools: make_create_bulk_rfq_node(tools)),
    "post_invoice": Spec("post_invoice", lambda llm, tools: make_post_invoice_node(tools)),
    "register_payment": Spec("register_payment", lambda llm, tools: make_register_payment_node(tools)),
    # Spec.node PHẢI khớp cfg.preview_node — graph.py lặp trên
    # MAIL_COORDINATOR_CFGS để dựng node 2 + conditional edge, hai bên phải
    # gọi cùng một tên node thì đồ thị mới nối được.
    ORDER_CONFIRMATION_CFG.tool_name: Spec(
        ORDER_CONFIRMATION_CFG.preview_node,
        lambda llm, tools: make_send_template_email_preview_node(
            tools, ORDER_CONFIRMATION_CFG)),
}

COORDINATED_TOOLS = frozenset(WRITE_COORDINATORS)

# Bước chuỗi PHẢI dừng hỏi lại kèm bản tóm tắt, KHÔNG auto-run (spec
# 2026-08-06 §3.3, §4).
#
# TẬP TƯỜNG MINH, KHÔNG PHẢI `in COORDINATED_TOOLS`: đối chiếu registry cho
# thấy convert_lead và update_vendor_pricing cũng VỪA là coordinated tool VỪA
# là bước trong NEXT_STEPS — dùng điều kiện rộng sẽ đổi luôn hành vi của hai
# tool đó, vượt phạm vi spec và không có tiêu chí nghiệm thu nào phủ.
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment",
                              "send_order_confirmation_email"})


@dataclass(frozen=True)
class NextStep:
    label: str                       # menu label, e.g. "Xác nhận báo giá"
    tool: str                        # next tool in the chain
    args: Callable[[dict], dict]     # last_write -> args for that tool


# Linear next step per chain tool; absence = terminal. Adding a purchase chain
# later = envelope-ize its tools + add rows here (no node changes).
NEXT_STEPS = {
    # ── chuỗi bán ──
    "create_quotation":          NextStep("Xác nhận báo giá", "confirm_sale_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    # sửa đơn nháp → gợi ý xác nhận (giống sau khi tạo mới)
    "update_quotation_lines":    NextStep("Xác nhận báo giá", "confirm_sale_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "confirm_sale_order":        NextStep("Giao hàng", "deliver_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "deliver_order":             NextStep("Tạo hóa đơn", "create_invoice_from_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "create_invoice_from_order": NextStep("Phát hành hóa đơn", "post_invoice",
                                          lambda lw: {"invoice_id": lw["res_id"]}),
    # ── chuỗi mua ──
    "create_rfq":                NextStep("Xác nhận đơn mua", "confirm_purchase_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "update_rfq_lines":          NextStep("Xác nhận đơn mua", "confirm_purchase_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "confirm_purchase_order":    NextStep("Nhận hàng", "receive_order",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "receive_order":             NextStep("Tạo hóa đơn NCC", "create_bill_from_po",
                                          lambda lw: {"order_ref": lw["ref"]}),
    "create_bill_from_po":       NextStep("Phát hành hóa đơn", "post_invoice",
                                          lambda lw: {"invoice_id": lw["res_id"]}),
    "post_invoice":               NextStep("Ghi nhận thanh toán", "register_payment",
                                          lambda lw: {"invoice_id": lw["res_id"]}),
    # ── chuỗi CRM ──
    "create_lead":               NextStep("Chuyển thành cơ hội", "convert_lead",
                                          lambda lw: {"lead_id": lw["res_id"]}),
    # ── chuỗi sản xuất ──
    "create_manufacturing_order":  NextStep("Xác nhận lệnh sản xuất",
                                            "confirm_manufacturing_order",
                                            lambda lw: {"order_ref": lw["ref"]}),
    "confirm_manufacturing_order": NextStep("Hoàn tất sản xuất",
                                            "complete_manufacturing_order",
                                            lambda lw: {"order_ref": lw["ref"]}),
    # ── chuỗi trả hàng / hoàn tiền ──
    "return_order":       NextStep("Xác nhận phiếu trả hàng", "validate_picking",
                                   lambda lw: {"picking_ref": lw["ref"]}),
    "create_credit_memo": NextStep("Phát hành hóa đơn", "post_invoice",
                                   lambda lw: {"invoice_id": lw["res_id"]}),
    # ── chuỗi NCC ──
    "create_vendor": NextStep("Khai giá sản phẩm", "update_vendor_pricing",
                              lambda lw: {"partner_id": lw["res_id"]}),
}


def expand_chain(first_tool, chain_until):
    """Các bước SAU first_tool tới chain_until (inclusive), walk theo NEXT_STEPS.

    Trả [(tool, label), ...] theo thứ tự chạy; None nếu chain_until vắng, trùng
    first_tool, không reachable, hoặc input rác. TOTAL function: không raise,
    không I/O; cycle-guard bằng max-depth len(NEXT_STEPS)."""
    try:
        if (not chain_until or not isinstance(first_tool, str)
                or not isinstance(chain_until, str) or chain_until == first_tool):
            return None
        steps, current = [], first_tool
        for _ in range(len(NEXT_STEPS)):
            nxt = NEXT_STEPS.get(current)
            if nxt is None:
                return None
            steps.append((nxt.tool, nxt.label))
            if nxt.tool == chain_until:
                return steps
            current = nxt.tool
        return None
    except Exception:  # noqa: BLE001 — total function
        return None
