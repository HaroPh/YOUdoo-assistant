import pytest

from src.agents.handoff import (ACTIVITY_MODELS_OF, HANDOFF_DOC_OF,
                                NO_DOCUMENT_TOOLS,
                                build_handoff, existing_handoff,
                                role_name_for_label)
from src.agents.roles import DEPT_OF, load_profile


def test_moi_khoa_trong_bang_deu_co_trong_DEPT_OF():
    """Chiều 1 của lưới đỡ trôi."""
    la = set(HANDOFF_DOC_OF) - set(DEPT_OF)
    assert not la, f"bảng có tool không thuộc DEPT_OF: {sorted(la)}"


def test_moi_tool_trong_DEPT_OF_deu_duoc_xep_loai():
    """Chiều 2: thêm tool vào DEPT_OF mà quên xếp loại ở đây thì ĐỎ."""
    chua_xep = set(DEPT_OF) - set(HANDOFF_DOC_OF) - set(NO_DOCUMENT_TOOLS)
    assert not chua_xep, (
        f"tool trong DEPT_OF chưa xếp loại: {sorted(chua_xep)} — thêm vào "
        "HANDOFF_DOC_OF (có chứng từ) hoặc NO_DOCUMENT_TOOLS (không có)")


def test_danh_sach_ngoai_le_khong_co_muc_chet():
    """Chiều 3 — bài học GATHER_CASES: lần đó lưới đỡ được dựng nhưng chính
    danh sách ngoại lệ lại không ai canh, và lỗi tái xuất cao hơn một tầng."""
    chet = set(NO_DOCUMENT_TOOLS) - set(DEPT_OF)
    assert not chet, f"NO_DOCUMENT_TOOLS có mục không còn trong DEPT_OF: {sorted(chet)}"


def test_hai_tap_khong_giao_nhau():
    trung = set(HANDOFF_DOC_OF) & set(NO_DOCUMENT_TOOLS)
    assert not trung, f"tool vừa có vừa không có chứng từ: {sorted(trung)}"


def test_tra_nhan_bo_phan_ve_ten_vai():
    assert role_name_for_label("Kế toán") == "accounting"
    assert role_name_for_label("Kho") == "warehouse"


def test_bo_phan_khong_co_vai_thi_tra_None():
    """Bán hàng / Mua hàng có trong DEPT_OF nhưng KHÔNG có vai nào — 4/20
    tool luôn rơi về sàn. Hành vi đúng, không phải thiếu sót."""
    assert role_name_for_label("Bán hàng") is None
    assert role_name_for_label("Mua hàng") is None
    assert role_name_for_label("khác") is None


def _vai(ten):
    return load_profile("small-business")[ten]


def test_dung_duoc_ban_giao_cho_tool_co_chung_tu():
    got = build_handoff(_vai("warehouse"), "create_invoice_from_order",
                        {"order_ref": "S00012"}, "Phát hành hóa đơn cho đơn S00012")

    assert got["tool"] == "log_activity"
    assert got["args"]["res_model"] == "sale.order"
    assert got["args"]["ref"] == "S00012"
    assert got["args"]["assignee"] == "ai-accounting"
    assert got["args"]["activity_type"] == "To-Do"
    # Nguồn gốc phải nằm trong summary — bên nhận cần biết AI đề nghị.
    assert "Kho" in got["args"]["summary"]
    assert "Phát hành hóa đơn" in got["args"]["summary"]


def test_khong_dung_duoc_khi_tool_khong_co_chung_tu():
    assert build_handoff(_vai("warehouse"), "post_invoice",
                         {"partner_name": "Acme"}, "Phát hành hóa đơn") is None


def test_khong_dung_duoc_khi_thieu_gia_tri_tham_so():
    """Tool CÓ trong bảng nhưng args rỗng — vẫn phải rơi về sàn."""
    assert build_handoff(_vai("warehouse"), "create_invoice_from_order",
                         {}, "x") is None


def test_khong_dung_duoc_khi_bo_phan_khong_co_vai():
    """create_quotation thuộc 'Bán hàng' — không vai nào nhận."""
    assert build_handoff(_vai("accounting"), "create_quotation",
                         {"partner_name": "Acme"}, "Tạo báo giá") is None


def test_khong_dung_duoc_voi_ten_tool_bia():
    """LLM bịa tên tool ('other') → dept_of trả 'khác' → sàn."""
    assert build_handoff(_vai("warehouse"), "other", {}, "x") is None


def test_khong_bao_gio_ban_giao_chinh_log_activity():
    """log_activity LÀ kênh bàn giao, không bao giờ là đích của nó."""
    assert build_handoff(_vai("warehouse"), "log_activity",
                         {"ref": "S00012"}, "x") is None


def test_args_khong_phai_dict_thi_tra_None():
    """final-review M1: planner có thể trả args không phải dict (vd list)
    khi LLM bịa hình dạng — .get() trên đó từng ném AttributeError không ai
    bắt, vỡ cả lượt chat. SÀN: mọi trường hợp không chắc ⇒ None."""
    assert build_handoff(_vai("warehouse"), "create_invoice_from_order",
                         ["S00012"], "x") is None


def test_tim_thay_viec_dang_mo_tren_cung_ban_ghi():
    rows = [{"res_model": "sale.order", "res_name": "S00012",
             "summary": "Kho đề nghị: phát hành hóa đơn",
             "date_deadline": "2026-08-15"}]
    got = existing_handoff(rows, "sale.order", "S00012")
    assert got is not None
    assert got["date_deadline"] == "2026-08-15"


def test_khac_ban_ghi_thi_khong_tinh_la_trung():
    rows = [{"res_model": "sale.order", "res_name": "S00099", "summary": "x"}]
    assert existing_handoff(rows, "sale.order", "S00012") is None


def test_khac_model_thi_khong_tinh_la_trung():
    """Cùng mã nhưng khác model — vd S00012 không phải picking."""
    rows = [{"res_model": "stock.picking", "res_name": "S00012", "summary": "x"}]
    assert existing_handoff(rows, "sale.order", "S00012") is None


def test_danh_sach_rong_thi_khong_trung():
    assert existing_handoff([], "sale.order", "S00012") is None


def test_activity_khong_phai_ban_giao_thi_khong_tinh_la_trung():
    """final-review I5: activity mở sẵn trên ĐÚNG chứng từ nhưng KHÔNG phải
    một bàn giao (summary không có HANDOFF_MARKER — vd dữ liệu demo có sẵn)
    không được tính là "đã chuyển rồi". Thiếu điều kiện này, hệ báo sai sự
    thật và yêu cầu thật bốc hơi."""
    rows = [{"res_model": "sale.order", "res_name": "S00012",
             "summary": "Gọi khách xác nhận địa chỉ giao hàng"}]
    assert existing_handoff(rows, "sale.order", "S00012") is None


def test_khu_hoi_build_handoff_roi_existing_handoff_phai_nhan_ra():
    """Chống trôi giữa build_handoff và existing_handoff: nếu ai đổi cách
    build_handoff đánh dấu summary (HANDOFF_MARKER) mà quên đổi existing_
    handoff cho khớp — hoặc ngược lại — test này phải ĐỎ."""
    handoff = build_handoff(_vai("warehouse"), "create_invoice_from_order",
                            {"order_ref": "S00012"}, "Phát hành hóa đơn")
    row = {"res_model": handoff["args"]["res_model"],
           "res_name": handoff["args"]["ref"],
           "summary": handoff["args"]["summary"]}
    got = existing_handoff([row], handoff["args"]["res_model"],
                           handoff["args"]["ref"])
    assert got is row


# ── I3: vai nguồn phải gắn NỔI activity lên model đích ──────────────────────

def test_kho_khong_ban_giao_duoc_len_account_move():
    """ĐO THẬT 2026-08-14: ai-warehouse KHÔNG tạo nổi mail.activity trên
    account.move — Odoo chặn ở tầng bảo mật, không phải ở phép đọc của tool.

    Nghiệm thu sống bắt được: kho xin credit memo ⇒ bàn giao dựng được, cổng
    xác nhận hiện ra, user bấm đồng ý, RỒI mới nhận "Không đọc được dữ liệu
    'account.move'". Đề xuất một việc chắc chắn hỏng còn tệ hơn từ chối thẳng."""
    assert build_handoff(_vai("warehouse"), "create_credit_memo",
                         {"invoice_ref": "INV/2026/00030"}, "x") is None


def test_kho_khong_ban_giao_duoc_len_purchase_order():
    assert build_handoff(_vai("warehouse"), "create_bill_from_po",
                         {"order_ref": "P00068"}, "x") is None


def test_kho_VAN_ban_giao_duoc_len_sale_order():
    """Đối chứng dương: chặn phải HẸP, không được nuốt cả hướng đang chạy."""
    got = build_handoff(_vai("warehouse"), "create_invoice_from_order",
                        {"order_ref": "S00012"}, "x")
    assert got is not None and got["args"]["res_model"] == "sale.order"


def test_ke_toan_ban_giao_duoc_len_stock_picking():
    """Đối chứng dương hướng ngược: kế toán → kho, đã chạy thật ở nghiệm thu."""
    got = build_handoff(_vai("accounting"), "validate_picking",
                        {"picking_ref": "WH/OUT/00138"}, "x")
    assert got is not None and got["args"]["assignee"] == "ai-warehouse"


def test_moi_model_dich_trong_bang_deu_duoc_khai_o_it_nhat_mot_vai():
    """Lưới đỡ trôi: thêm một model đích mới vào HANDOFF_DOC_OF mà quên khai
    vai nào gắn nổi activity lên đó ⇒ mọi bàn giao tới model ấy im lặng rơi về
    sàn, không ai biết. Test này đỏ trước khi điều đó xảy ra."""
    dich = {res_model for _, res_model in HANDOFF_DOC_OF.values()}
    khai = set().union(*ACTIVITY_MODELS_OF.values())
    thieu = dich - khai
    assert not thieu, (
        f"model đích chưa vai nào khai gắn nổi activity: {sorted(thieu)} — "
        "đo thật rồi thêm vào ACTIVITY_MODELS_OF")
