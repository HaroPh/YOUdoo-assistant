"""Cấu hình vai và chính sách quyền — spec 2026-08-09-role-based-access.

BỐN TRẠNG THÁI, không phải hai. Phỏng vấn nhân viên kho thật (2026-08-09,
docs/role-permission-interview.md) cho 13 câu Đ, 11 câu X, 0 câu K: ở doanh
nghiệp nhỏ gần như không có gì bị cấm tuyệt đối. Nhưng hai chữ X không cùng
nghĩa — "việc của tôi, cần sếp ký" khác hẳn "việc phòng khác, xin thì được":
cái đầu cần LUỒNG DUYỆT, cái sau cần BÀN GIAO. Gộp chúng làm một là lý do
bản thiết kế đầu tiên khiến vai kho và vai kế toán trông giống nhau.

QUYỀN TRÊN TÀI KHOẢN ODOO = own ∪ needs_sign_off. other_dept và denied KHÔNG
có quyền — đó là chỗ Odoo cưỡng chế thật. Hệ quả: sức mạnh lớp cưỡng chế tỉ
lệ thuận với số nghiệp vụ tổ chức xếp ra ngoài tập đó, nên hồ sơ
'small-business' (gần như không có) cưỡng chế yếu — đúng chính sách của nó,
không phải khuyết điểm kiến trúc.

FAIL-CLOSED: tool không khai báo = denied. Thêm tool mới vào hệ thống mà quên
khai báo sẽ khiến nó bị CẤM, không phải được cấp cho mọi vai."""
import os
from dataclasses import dataclass, field

OWN = "own"
NEEDS_SIGN_OFF = "needs_sign_off"
OTHER_DEPT = "other_dept"
DENIED = "denied"

# Bộ phận phụ trách từng nghiệp vụ — NGUỒN SỰ THẬT DUY NHẤT cho "tool X thuộc
# bộ phận nào", dùng cho câu từ chối tất định (nodes.py) và cho hint trong
# prompt của planner (prompts.py).
#
# Chuyển từ prompts.py sang đây (spec 2026-08-12 §3.1): đây là dữ liệu phân
# quyền chứ không phải dữ liệu prompt, và other_dept được SUY RA từ chính bảng
# này nên nó phải sống cùng module với RoleCfg.
#
# Bảng CÓ những nghiệp vụ chưa vai AI nào sở hữu (Bán hàng, Mua hàng). Đó là
# thông tin mà suy diễn từ own/needs_sign_off KHÔNG tạo ra được, và là lý do
# bảng phải tồn tại thay vì bỏ hẳn.
#
# Ba mục cuối được bổ sung 2026-08-12: chúng vào roles.py ở các đợt sau mà
# không ai cập nhật bảng, gây 5 khoảng trống trên 2 profile. tests/agents/
# test_dept_of.py giờ khoá lại: sở hữu tool nào thì phải khai bộ phận tool đó.
DEPT_OF = {
    "post_invoice": "Kế toán", "register_payment": "Kế toán",
    "create_credit_memo": "Kế toán", "create_invoice_from_order": "Kế toán",
    "create_bill_from_po": "Kế toán",
    "create_quotation": "Bán hàng", "confirm_sale_order": "Bán hàng",
    "create_rfq": "Mua hàng", "confirm_purchase_order": "Mua hàng",
    "deliver_order": "Kho", "receive_order": "Kho", "validate_picking": "Kho",
    "internal_transfer": "Kho", "inventory_adjustment": "Kho",
    "scrap_product": "Kho", "return_order": "Kho",
    # bổ sung 2026-08-12 — xem comment trên
    "send_delivery_email": "Kho",
    "send_invoice_email": "Kế toán",
    "flag_order_for_review": "Kho",
}


@dataclass(frozen=True)
class RoleCfg:
    name: str
    label: str
    mcp_url: str
    own: frozenset = field(default_factory=frozenset)
    needs_sign_off: frozenset = field(default_factory=frozenset)
    other_dept: frozenset = field(default_factory=frozenset)
    unrestricted: bool = False        # chỉ vai admin

    def state_of(self, tool: str) -> str:
        if self.unrestricted:
            return OWN
        if tool in self.own:
            return OWN
        if tool in self.needs_sign_off:
            return NEEDS_SIGN_OFF
        if tool in self.other_dept:
            return OTHER_DEPT
        return DENIED                 # fail-closed — xem docstring module

    def allowed_tools(self):
        """Tập tool được phép gọi. None = không lọc (vai admin)."""
        if self.unrestricted:
            return None
        return self.own | self.needs_sign_off


# ── Nghiệp vụ theo vai, suy trực tiếp từ phiếu phỏng vấn đã điền ────────────
# Kho: A1.1-A1.4 là địa hạt của họ (Đ hoặc X); A1.5 "Ngoài phạm vi kho" nên
# mọi X trong mục đó là OTHER_DEPT, không phải NEEDS_SIGN_OFF.
# flag_order_for_review: câu 5 phiếu phỏng vấn (docs/role-permission-interview.md)
# — "Khi hàng nhận về thiếu hoặc hỏng, anh/chị tự xử lý hay phải báo ai?" → Đ
# (tự xử lý). Ghi chú bất thường lên đơn mua LÀ hành động "tự xử lý" đó, nên
# thuộc own, không phải needs_sign_off/other_dept. Cả 2 profile dùng chung
# _WH_OWN nên một dòng này áp cho cả small-business lẫn enterprise.
_WH_OWN = frozenset({
    "deliver_order", "receive_order", "validate_picking", "internal_transfer",
    "inventory_adjustment", "scrap_product", "flag_order_for_review",
})
_WH_SIGN_OFF = frozenset({"return_order", "send_delivery_email"})
_WH_OTHER = frozenset({
    "create_quotation", "create_rfq", "post_invoice", "confirm_sale_order",
    "register_payment", "create_credit_memo", "confirm_purchase_order",
})

_ACC_OWN = frozenset({
    "create_credit_memo", "send_invoice_email", "create_invoice_from_order",
    "create_bill_from_po",
})
_ACC_SIGN_OFF = frozenset({"post_invoice", "register_payment"})
_ACC_OTHER = frozenset({
    "deliver_order", "receive_order", "validate_picking", "internal_transfer",
    "inventory_adjustment", "scrap_product", "return_order",
    "create_quotation", "create_rfq",
})

MCP_ADMIN = os.environ.get("MCP_ODOO_URL", "http://localhost:8003/sse")
MCP_WAREHOUSE = os.environ.get("MCP_ODOO_URL_WAREHOUSE", "http://localhost:8004/sse")
MCP_ACCOUNTING = os.environ.get("MCP_ODOO_URL_ACCOUNTING", "http://localhost:8005/sse")

PROFILES = {
    "small-business": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg("warehouse", "Kho", MCP_WAREHOUSE,
                             own=_WH_OWN, needs_sign_off=_WH_SIGN_OFF,
                             other_dept=_WH_OTHER),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF,
                              other_dept=_ACC_OTHER),
    },
    # Doanh nghiệp lớn chia nhỏ trách nhiệm: 3 nghiệp vụ RỜI tập own∪sign_off
    # của vai kho ⇒ quyền bị gỡ khỏi tài khoản Odoo (khác với việc chỉ đổi
    # other_dept↔denied, vốn không đổi gì ở tầng Odoo).
    "enterprise": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg(
            "warehouse", "Kho", MCP_WAREHOUSE,
            own=frozenset({"deliver_order", "receive_order", "validate_picking",
                           "internal_transfer"}),
            needs_sign_off=frozenset({"send_delivery_email"}),
            other_dept=_WH_OTHER | frozenset({"inventory_adjustment",
                                              "scrap_product", "return_order"})),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF,
                              other_dept=_ACC_OTHER),
    },
}


def load_profile(name: str | None = None) -> dict:
    return PROFILES[name or os.environ.get("YOUDOO_POLICY_PROFILE", "small-business")]


def role_for_user(user_id):
    """Ánh xạ user_id (chuỗi mờ từ header Open WebUI) → tên vai.

    Khoá theo user_id, KHÔNG theo email/tên — quyết định PII tại main.py.
    Trả None khi không xác định được: KHÔNG mặc định thành admin (fail-closed).

    Định dạng YOUDOO_ROLE_MAP: "id1:admin,id2:warehouse,id3:accounting"
    """
    if not user_id:
        return None
    raw = os.environ.get("YOUDOO_ROLE_MAP", "")
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        uid, _, role = pair.partition(":")
        if uid.strip() == str(user_id).strip():
            return role.strip() or None
    return None
