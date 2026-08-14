# backend/src/agents/handoff.py
"""Dựng một BÀN GIAO từ một thao tác ghi bị guard vai từ chối.

Thuần, KHÔNG I/O: chỉ quyết định "có dựng được không" và dựng plan. Việc tra
chứng từ thật trong Odoo, kiểm loại activity, tra người nhận và cổng xác nhận
đều do coordinator `log_activity` (agents/crm_write.py) lo — vì log_activity
NẰM TRONG WRITE_COORDINATORS, planner trả sớm và coordinator chạy tiếp.

SÀN (spec §3.3): trả None ở MỌI trường hợp không chắc. Caller rơi về đúng câu
từ chối như trước. Bàn giao là nâng cấp ở nơi làm được, không bao giờ làm lời
từ chối tệ đi.
"""
from .roles import DEPT_OF, load_profile

# tool → (tên tham số mang mã chứng từ, res_model của chứng từ đó)
#
# Suy từ chữ ký thật trong WRITE_PLANNER_PROMPT (prompts.py) — CHỈ những tool
# planner thật sự nêu được tên. Tool không có trong prompt đó thì guard vai
# (soi plan["tool"]) không bao giờ thấy, nên không thuộc bảng này.
#
# Bảng khai tay sẽ trôi — test_handoff.py canh BA chiều: mọi khoá thuộc
# DEPT_OF, mọi tool trong DEPT_OF đều được xếp loại, và NO_DOCUMENT_TOOLS
# không có mục chết. LƯU Ý ba chiều đó KHÔNG canh được ánh xạ có ĐÚNG hay
# không (tên tham số, res_model) — chỗ đó cần mắt người đọc chéo.
HANDOFF_DOC_OF: dict[str, tuple[str, str]] = {
    "confirm_sale_order":        ("order_ref",   "sale.order"),
    "deliver_order":             ("order_ref",   "sale.order"),
    "create_invoice_from_order": ("order_ref",   "sale.order"),
    "return_order":              ("order_ref",   "sale.order"),
    "confirm_purchase_order":    ("order_ref",   "purchase.order"),
    "receive_order":             ("order_ref",   "purchase.order"),
    "create_bill_from_po":       ("order_ref",   "purchase.order"),
    "create_credit_memo":        ("invoice_ref", "account.move"),
    "send_invoice_email":        ("invoice_ref", "account.move"),
    # register_payment: invoice_ref là TUỲ CHỌN (tool cũng nhận partner_name).
    # Xếp vào đây có chủ đích: có invoice_ref thì bàn giao được, không có thì
    # build_handoff trả None vì ref rỗng ⇒ rơi về sàn. Không cần nhánh riêng.
    "register_payment":          ("invoice_ref", "account.move"),
    "validate_picking":          ("picking_ref", "stock.picking"),
    "send_delivery_email":       ("picking_ref", "stock.picking"),
}

# Tool KHÔNG trỏ vào một bản ghi có sẵn: chúng TẠO MỚI hoặc thao tác trên
# vật/kho. Không có chứng từ để gắn activity ⇒ rơi về sàn.
#
# log_activity nằm đây vì lý do KHÁC: nó chính LÀ kênh bàn giao, nên không bao
# giờ là đích của một cuộc bàn giao. Xếp vào đây để lưới đỡ chiều 2 không đỏ.
NO_DOCUMENT_TOOLS: frozenset[str] = frozenset({
    "post_invoice", "create_quotation", "create_rfq",
    "inventory_adjustment", "internal_transfer", "scrap_product",
    "log_activity",
    # flag_order_for_review nằm đây vì HAI lý do, cả hai đều loại nó khỏi bảng
    # trên (review Task 1 bắt được — bản plan đầu ép cứng "purchase.order"):
    #   1. Nó KHÔNG có trong WRITE_PLANNER_PROMPT, nên planner không bao giờ
    #      nêu được tên nó ⇒ guard vai (soi plan["tool"]) không bao giờ thấy.
    #      Chỉ edit_order.py gọi nội bộ.
    #   2. Model của nó LƯỠNG TÍNH: edit_order.py truyền model=cfg.model, mà
    #      cfg là SALE_EDIT_CFG ("sale.order") HOẶC PURCHASE_EDIT_CFG
    #      ("purchase.order"). Một tuple tĩnh không biểu diễn nổi.
    "flag_order_for_review",
})

ACTIVITY_TYPE = "To-Do"

# Đánh dấu một activity LÀ bàn giao (không phải activity thường có sẵn trên
# chứng từ). existing_handoff() dùng để lọc — thiếu điều kiện này, MỌI
# activity mở trên đúng bản ghi (kể cả activity không liên quan gì tới bàn
# giao) đều bị tính là "đã chuyển rồi", báo sai sự thật (final-review I5).
HANDOFF_MARKER = "đề nghị:"


def role_name_for_label(label: str) -> str | None:
    """Nhãn bộ phận ("Kế toán") → tên vai ("accounting"), hoặc None.

    DEPT_OF trả NHÃN, còn login Odoo suy từ TÊN VAI, nên phải tra ngược. Trả
    None cho "Bán hàng"/"Mua hàng" (có trong DEPT_OF nhưng không vai nào nhận)
    và cho "khác" (dept_of trả khi tên tool không có trong bảng)."""
    for name, cfg in load_profile().items():
        if cfg.label == label:
            return name
    return None


def build_handoff(role_cfg, tool: str, args: dict,
                  summary: str | None) -> dict | None:
    """Plan `log_activity` đã điền sẵn, hoặc None nếu không dựng được.

    Trả None khi: tool không có chứng từ trong bảng; args không phải dict
    hoặc thiếu giá trị; bộ phận đích không có vai; hoặc đích trùng chính vai
    đang gọi."""
    target = HANDOFF_DOC_OF.get(tool)
    if target is None:
        return None
    arg_name, res_model = target

    # SÀN (spec §3.3): planner có thể trả args không phải dict (vd list) khi
    # LLM bịa hình dạng — .get() trên đó ném AttributeError không ai bắt, vỡ
    # cả lượt chat (final-review M1). Mọi trường hợp không chắc ⇒ None.
    if not isinstance(args, dict):
        return None

    ref = str(args.get(arg_name) or "").strip()
    if not ref:
        return None

    role_name = role_name_for_label(DEPT_OF.get(tool, ""))
    if role_name is None or role_name == role_cfg.name:
        return None

    what = (summary or "").strip() or tool
    return {
        "tool": "log_activity",
        "args": {
            "res_model": res_model,
            "ref": ref,
            "activity_type": ACTIVITY_TYPE,
            # Nguồn gốc nằm ngay trong summary: bên nhận đọc activity phải
            # biết AI đề nghị và vì sao, không phải đi hỏi lại.
            "summary": f"{role_cfg.label} {HANDOFF_MARKER} {what}",
            "assignee": f"ai-{role_name}",
        },
        "summary": f"Chuyển việc cho bộ phận {DEPT_OF[tool]}: {what}",
    }


def existing_handoff(rows, res_model: str, ref: str) -> dict | None:
    """Activity đang mở trên ĐÚNG bản ghi này VÀ LÀ một bàn giao, hoặc None.

    Khớp theo CẢ res_model lẫn res_name: mã đơn có thể trùng nhau giữa các
    model, khớp mỗi mã sẽ báo trùng nhầm.

    Khớp thêm HANDOFF_MARKER trong summary (final-review I5): thiếu điều
    kiện này, một activity BẤT KỲ đang mở trên đúng chứng từ — không liên
    quan gì tới bàn giao (dữ liệu demo có sẵn hàng chục cái) — cũng bị tính
    là "đã chuyển rồi", báo sai sự thật cho người dùng."""
    for r in rows or []:
        if (r.get("res_model") == res_model
                and str(r.get("res_name") or "") == str(ref)
                and HANDOFF_MARKER in str(r.get("summary") or "")):
            return r
    return None
