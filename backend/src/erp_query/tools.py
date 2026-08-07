"""LangChain tool wrappers around the Business Query API. Each tool returns the
envelope as JSON text (the agent reads it; orchestration in C parses `data`)."""
import json
import re

from langchain_core.tools import tool
from pydantic import model_validator

from . import sales, inventory, purchase, accounting, crm, mrp


def _json(envelope) -> str:
    return json.dumps(envelope, ensure_ascii=False)


_REF_SHAPE_RE = re.compile(
    r"^(S\d{4,6}|P\d{4,6}|WH/(IN|OUT|INT)/\d+|INV/\d{4}/\d+)$"
)
_PARTNER_NAME_FIELDS = ("customer", "vendor", "partner", "name")


def _reject_ref_shaped_partner_names(t) -> None:
    """Chặn tất định: nếu tham số tên khách/NCC (customer/vendor/partner/
    name) nhận giá trị trông giống mã đơn/phiếu/hoá đơn thật — dấu hiệu
    model gán nhầm mã tham chiếu vào tham số tên (spec Finding #1), đúng
    tool nên dùng là get_*_detail(ref=...). Subclass args_schema (KHÔNG
    wrap t.func) — chỉ ValidationError mới đi qua đúng đường graceful của
    LangGraph ToolNode (spec Finding #6); vô hại với tool không có field
    nào trong _PARTNER_NAME_FIELDS."""
    fields = [f for f in _PARTNER_NAME_FIELDS if f in t.args_schema.model_fields]
    if not fields:
        return
    base = t.args_schema

    class _Guarded(base):
        @model_validator(mode="before")
        @classmethod
        def _check(cls, data):
            if isinstance(data, dict):
                for f in fields:
                    v = data.get(f)
                    if isinstance(v, str) and _REF_SHAPE_RE.match(v):
                        raise ValueError(
                            f"{v!r} trông giống mã đơn/phiếu/hoá đơn, không "
                            f"phải tên — dùng tool chi tiết (get_*_detail) "
                            f"với đúng mã này thay vì truyền vào '{f}'.")
            return data

    t.args_schema = _Guarded


def _forbid_extra_kwargs(t) -> None:
    """Ép Pydantic reject tham số lạ trong tool call thay vì âm thầm bỏ
    qua (mặc định extra='ignore') — biến 'tool chạy sai với default rỗng'
    thành lỗi LLM nhìn thấy được. LangGraph's ToolNode đã tự bắt
    ValidationError và trả 'Error: ... Please fix your mistakes.' cho LLM,
    không cần code thêm ở tầng agent. Vô hại (không có tác dụng) với tool
    0 tham số — xem test riêng ghi nhận giới hạn này."""
    t.args_schema.model_config['extra'] = 'forbid'
    t.args_schema.model_rebuild(force=True)


def build_erp_query_tools() -> list:
    @tool
    def find_customer(name: str) -> str:
        """Tìm khách hàng theo tên/email/điện thoại; trả về các ứng viên + ID."""
        return _json(sales.find_customer(name))

    @tool
    def find_supplier(name: str) -> str:
        """Tìm nhà cung cấp theo tên/email/điện thoại; trả về ứng viên + ID."""
        return _json(purchase.find_supplier(name))

    @tool
    def find_product(name_or_code: str) -> str:
        """Tìm sản phẩm theo tên hoặc mã (SKU/barcode); trả về ứng viên + ID."""
        return _json(inventory.find_product(name_or_code))

    @tool
    def list_sale_orders(state: str = "", customer: str = "",
                         date_from: str = "", date_to: str = "") -> str:
        """Liệt kê đơn bán; lọc theo state/tên khách (chuỗi con, KHÔNG dùng ID
        đã resolve từ find_customer)/khoảng ngày (YYYY-MM-DD), bỏ trống = bỏ lọc."""
        return _json(sales.list_sale_orders(state or None, customer or None,
                                            date_from or None, date_to or None))

    # Lưu ý: commitment_date là field thật, đọc đúng, nhưng KHÔNG đơn nào
    # trong demo Odoo hiện tại populate field này (xác nhận bằng chẩn đoán
    # Odoo thật khi viết spec sale-order-effective-dates, 2026-08-02).
    @tool
    def get_sale_order_detail(ref: str) -> str:
        """Chi tiết đơn bán theo mã (vd S00042): dòng sản phẩm, ngày xác nhận (date_order), trạng thái giao (delivery_status), ngày giao dự kiến (commitment_date), ngày giao thực tế (effective_date)."""
        return _json(sales.get_sale_order_detail(ref))

    @tool
    def get_product_price(product_id: int, partner_id: int = 0, qty: float = 1.0) -> str:
        """Giá bán hiệu lực của 1 sản phẩm (theo bảng giá), tùy chọn cho 1 khách + số lượng."""
        return _json(sales.get_product_price(product_id, partner_id or None, qty))

    @tool
    def sales_summary(period: str = "month") -> str:
        """Tổng hợp doanh thu theo kỳ: month|quarter|year."""
        return _json(sales.sales_summary(period))

    @tool
    def top_products(by: str = "quantity", period: str = "") -> str:
        """Top sản phẩm bán chạy theo 'quantity' hoặc 'revenue', kỳ tùy chọn."""
        return _json(sales.top_products(by, period or None))

    @tool
    def get_stock(product: str = "") -> str:
        """Tồn kho nội bộ; lọc theo tên sản phẩm (chuỗi con, KHÔNG dùng ID đã
        resolve từ find_product; bỏ trống = tất cả)."""
        return _json(inventory.get_stock(product or None))

    @tool
    def get_lots(product: str = "") -> str:
        """Lô/sê-ri và tồn theo lô; lọc theo tên sản phẩm (chuỗi con, KHÔNG
        dùng ID đã resolve từ find_product)."""
        return _json(inventory.get_lots(product or None))

    @tool
    def list_purchase_orders(state: str = "", vendor: str = "",
                             date_from: str = "", date_to: str = "") -> str:
        """Liệt kê đơn mua; lọc theo state/tên nhà cung cấp (chuỗi con, KHÔNG
        dùng ID đã resolve từ find_supplier)/khoảng ngày."""
        return _json(purchase.list_purchase_orders(state or None, vendor or None,
                                                   date_from or None, date_to or None))

    @tool
    def get_purchase_order_detail(ref: str) -> str:
        """Chi tiết dòng sản phẩm của một đơn mua theo mã (vd P00003)."""
        return _json(purchase.get_purchase_order_detail(ref))

    @tool
    def list_suppliers() -> str:
        """Liệt kê nhà cung cấp hiện có. Dùng khi hỏi 'có các vendor nào' mà
        KHÔNG nêu tên cụ thể."""
        return _json(purchase.list_suppliers())

    @tool
    def get_product_suppliers(product: str) -> str:
        """Nhà cung cấp của MỘT SẢN PHẨM (khai báo bảng giá + đã nhập thật
        theo đơn mua). Nhận tên hoặc mã sản phẩm."""
        return _json(purchase.get_product_suppliers(product))

    @tool
    def get_supplier_detail(name: str) -> str:
        """Hồ sơ chi tiết MỘT nhà cung cấp: liên hệ, thuế, ngân hàng, số đơn
        mua."""
        return _json(purchase.get_supplier_detail(name))

    @tool
    def get_customer_detail(name: str) -> str:
        """Hồ sơ chi tiết MỘT khách hàng: liên hệ, thuế, điều khoản thanh
        toán, số đơn bán."""
        return _json(sales.get_customer_detail(name))

    @tool
    def list_crm_leads(kind: str = "", stage: str = "") -> str:
        """Liệt kê lead/cơ hội CRM. kind = 'lead' | 'opportunity', bỏ trống =
        cả hai; stage lọc theo tên giai đoạn (New/Qualified/...)."""
        return _json(crm.list_crm_leads(kind or None, stage or None))

    @tool
    def list_invoices(move_type: str, partner: str = "", payment_state: str = "") -> str:
        """Hóa đơn đã phát hành; move_type = out_invoice (bán) | in_invoice (mua);
        partner lọc theo tên (chuỗi con, KHÔNG dùng ID)."""
        return _json(accounting.list_invoices(move_type, partner or None, payment_state or None))

    @tool
    def get_overdue_invoices() -> str:
        """Hóa đơn khách hàng quá hạn (chưa trả hết, đến hạn đã qua)."""
        return _json(accounting.get_overdue_invoices())

    @tool
    def list_reorder_needed() -> str:
        """Sản phẩm đang dưới mức tồn kho tối thiểu (Reordering Rules) kèm số
        lượng gợi ý mua thêm. Dùng khi hỏi 'sản phẩm nào cần bổ sung/tái đặt
        hàng' hoặc 'có gì tồn kho thấp không'."""
        return _json(inventory.list_reorder_needed())

    @tool
    def get_bom_detail(product: str) -> str:
        """Định mức nguyên vật liệu (BoM) của MỘT sản phẩm: các bản BoM,
        nguyên liệu + số lượng cho mỗi batch, kèm tồn kho từng nguyên liệu.
        Nhận tên hoặc mã sản phẩm."""
        return _json(mrp.get_bom_detail(product))

    @tool
    def list_manufacturing_orders(state: str = "", product: str = "") -> str:
        """Liệt kê lệnh sản xuất (Manufacturing Order); state = draft (nháp) |
        confirmed | progress | to_close | done | cancel, bỏ trống = tất cả;
        product lọc theo tên sản phẩm (chuỗi con)."""
        return _json(mrp.list_manufacturing_orders(state or None, product or None))

    @tool
    def list_late_deliveries(direction: str = "") -> str:
        """Phiếu giao/nhận đang trễ hạn. direction = 'outgoing' (giao khách) |
        'incoming' (nhận từ NCC), bỏ trống = cả hai."""
        return _json(inventory.list_late_deliveries(direction or None))

    @tool
    def check_po_matching(ref: str) -> str:
        """Đối soát 1 đơn mua (PO) theo mã: dòng nào đã xuất hóa đơn NHIỀU HƠN
        thực nhận (kiểm tra trước khi xác nhận hóa đơn NCC)."""
        return _json(purchase.check_po_matching(ref))

    @tool
    def list_po_mismatches() -> str:
        """Mọi đơn mua đang có dòng hóa đơn vượt thực nhận (cần rà soát trước
        khi thanh toán thêm)."""
        return _json(purchase.list_po_mismatches())

    @tool
    def get_partner_balance(name: str) -> str:
        """Công nợ của MỘT đối tác cụ thể (theo tên) — cả phải thu (nếu là
        khách) và phải trả (nếu là NCC)."""
        return _json(accounting.get_partner_balance(name))

    tools = [find_customer, find_supplier, find_product, list_sale_orders,
             get_sale_order_detail, get_product_price, sales_summary, top_products,
             get_stock, get_lots, list_purchase_orders, get_purchase_order_detail,
             list_suppliers, get_product_suppliers, get_supplier_detail,
             get_customer_detail, list_crm_leads, list_invoices, get_overdue_invoices,
             list_reorder_needed, get_bom_detail, list_manufacturing_orders,
             list_late_deliveries, check_po_matching, list_po_mismatches,
             get_partner_balance]
    for t in tools:
        _forbid_extra_kwargs(t)
        _reject_ref_shaped_partner_names(t)
    return tools
