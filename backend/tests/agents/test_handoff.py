import pytest

from src.agents.handoff import (HANDOFF_DOC_OF, NO_DOCUMENT_TOOLS,
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
