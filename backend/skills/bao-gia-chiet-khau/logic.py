# backend/skills/bao-gia-chiet-khau/logic.py
"""Mã riêng của SOP bao-gia-chiet-khau — 🔒 KHÔNG dành cho người sửa SOP.

BẤT BIẾN TIỀN BẠC (quyết định KHÔNG được bàn lại): % chiết khấu và đơn giá
LUÔN tính trong code (compute_discount_pct + get_product_price) — model chỉ
gom tham số (khách, dòng hàng, cấp khách), KHÔNG BAO GIỜ tính hay truyền số
tiền. Đây chính là lý do skill này không khai báo thuần bằng SKILL.md được:
đẩy ~109 dòng dưới đây vào markdown nghĩa là giao việc tính tiền cho model.

Port nguyên văn từ D:\\Project\\backend\\src\\agents\\skill_agentic_discount_quote.py
(chỉ đổi import tương đối → tuyệt đối, và _build_tools → build_tools cho khớp
hợp đồng loader). Prose quy trình sống ở SKILL.md cạnh file này."""
import logging

from langchain_core.tools import tool

from src.agents.agentic_gate import REFUSED_MSG, _confirm_write, ask_human
from src.agents.create_order import resolve_entity_for_order
from src.agents.prompts import WRITE_CONFIRM_SUFFIX
from src.agents.skill_gate import _fold
from src.erp_query import sales, inventory

TIER_PCT = {"thuong": 0.0, "than_thiet": 0.05, "doi_tac": 0.10}

# Nhận cả id lẫn cách gõ tự nhiên (đã _fold): model 8-9B hay trả nhãn tiếng
# Việt thay vì id — map tất định, sai thì trả lỗi liệt kê, không đoán.
_TIER_ALIASES = {
    "thuong": "thuong", "khach thuong": "thuong", "binh thuong": "thuong",
    "than thiet": "than_thiet", "than_thiet": "than_thiet",
    "khach than thiet": "than_thiet",
    "doi tac": "doi_tac", "doi_tac": "doi_tac",
    "doi tac chien luoc": "doi_tac", "chien luoc": "doi_tac",
}

TIER_INVALID_MSG = ("Cấp khách không hợp lệ. Ba cấp hợp lệ: Thường / Thân thiết / "
                    "Đối tác chiến lược. Hãy hỏi lại người dùng bằng ask_human.")


def compute_discount_pct(tier_id: str, order_total: float) -> float:
    base = TIER_PCT[tier_id]
    bonus = 0.02 if order_total >= 50_000_000 else 0.0
    # round(): base+bonus in raw IEEE-754 float can land off-integer-percent
    # (e.g. 0.10 + 0.02 == 0.12000000000000001) — all tier/bonus values are
    # whole percentage points, so round to 2dp before the cap comparison.
    return min(round(base + bonus, 2), 0.15)


def _render_discount_draft(partner, lines, pct) -> str:
    body = "\n".join(f"  - {l['name']} × {l['qty']:g} = {l['subtotal']:,.0f}"
                     for l in lines)
    total_before = sum(l["subtotal"] for l in lines)
    total_after = total_before * (1 - pct)
    return (f"Báo giá cho {partner['name']}:\n{body}\n"
            f"Tổng trước chiết khấu: {total_before:,.0f}\n"
            f"Chiết khấu: {pct * 100:g}%\n"
            f"Tổng sau chiết khấu: {total_after:,.0f}\n"
            + WRITE_CONFIRM_SUFFIX)


def build_tools(mcp_tools):
    """Hợp đồng với skill_loader: trả list[BaseTool]. Loader đối chiếu tên tool
    trả về với declares_tools trong SKILL.md — trả tool KHÔNG khai thì từ chối
    nạp (app không lên)."""
    by_name = {t.name: t for t in mcp_tools}
    tools = [ask_human]

    create = by_name.get("create_quotation")
    if create is not None:
        @tool("create_discount_quote")
        async def create_discount_quote_gated(customer: str, lines: list[dict],
                                              tier: str) -> str:
            """Tạo báo giá có chiết khấu theo cấp khách vào Odoo. Hệ thống tự
            tính đơn giá + % chiết khấu trong code và tự hỏi người dùng xác
            nhận trước khi ghi.

            Args:
                customer: Tên khách hàng.
                lines: Danh sách dòng hàng, mỗi dòng {"product": "<tên>", "qty": <số>}.
                tier: Cấp khách — "thuong" | "than_thiet" | "doi_tac".
            """
            tier_id = _TIER_ALIASES.get(_fold(tier).strip())
            if tier_id is None:
                return TIER_INVALID_MSG
            if not str(customer or "").strip():
                return "Chưa có tên khách hàng. Hãy hỏi người dùng bằng ask_human."
            if not lines:
                return "Chưa có dòng hàng nào. Hãy hỏi người dùng sản phẩm + số lượng."

            kind, val = resolve_entity_for_order(sales.find_customer(customer), customer)
            if kind == "error":
                return val
            if kind == "none":
                return f"Không tìm thấy khách hàng '{customer}'."
            if kind == "ambiguous":
                names = "; ".join(str(o.get("name", "?")) for o in val)
                return (f"Có nhiều khách hàng trùng '{customer}': {names}. "
                        "Hãy hỏi người dùng chọn đúng tên rồi gọi lại.")
            partner = val

            quote_lines = []
            for line in lines:
                ref = str(line.get("product") or "")
                try:
                    qty = float(line.get("qty") or 0)
                except (TypeError, ValueError):
                    return (f"Số lượng không hợp lệ cho '{ref}'. Hãy hỏi lại "
                            "người dùng số lượng (một con số).")
                pkind, pval = resolve_entity_for_order(inventory.find_product(ref), ref)
                if pkind == "error":
                    return pval
                if pkind == "none":
                    return f"Không tìm thấy sản phẩm '{ref}'."
                if pkind == "ambiguous":
                    names = "; ".join(str(o.get("name", "?")) for o in pval)
                    return (f"Có nhiều sản phẩm trùng '{ref}': {names}. "
                            "Hãy hỏi người dùng chọn đúng tên rồi gọi lại.")
                product = pval
                penv = sales.get_product_price(product["id"], partner["id"], qty)
                price = (penv.get("data") or {}).get("price", 0.0) \
                    if penv.get("status") == "success" else 0.0
                quote_lines.append({"product_id": product["id"], "name": product["name"],
                                    "qty": qty, "unit_price": price,
                                    "subtotal": price * qty})

            order_total = sum(l["subtotal"] for l in quote_lines)
            pct = compute_discount_pct(tier_id, order_total)

            if not _confirm_write(_render_discount_draft(partner, quote_lines, pct)):
                return REFUSED_MSG
            try:
                tool_lines = [{"product_id": l["product_id"], "qty": l["qty"],
                               "price_unit": l["unit_price"] * (1 - pct)}
                              for l in quote_lines]
                return await create.ainvoke({"partner_id": partner["id"],
                                             "lines": tool_lines})
            except Exception as e:  # noqa: BLE001 — tool luôn trả text, không phá graph
                logging.getLogger(__name__).exception(
                    "tao_bao_gia thất bại: %s: %s", type(e).__name__, e)
                return ("Lỗi khi tạo báo giá — thao tác có thể chưa hoàn tất. "
                        "Nếu lặp lại, báo quản trị viên.")
        tools.append(create_discount_quote_gated)

    return tools
