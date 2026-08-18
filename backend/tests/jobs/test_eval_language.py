"""Bộ dò ngôn ngữ đầu ra phải phân biệt NHÃN với DANH TỪ RIÊNG.

Spike 2026-08-18 báo động giả vì đếm tên tài liệu tiếng Việt ở phần trích dẫn
nguồn là lỗi. Tên riêng giữ nguyên mới đúng — dịch chúng thì mất khả năng tra
ngược tài liệu/sản phẩm.
"""
from evals.cases import LANGUAGE_CASES
from evals.run_eval import looks_vietnamese


def test_cau_tieng_anh_thuan_thi_khong_bi_bao_dong():
    assert looks_vietnamese("Order P00003 from Azure Interior. Status: Draft.") is False


def test_cau_tieng_anh_kem_TEN_RIENG_tieng_viet_thi_khong_bi_bao_dong():
    """Đây đúng ca spike đếm nhầm."""
    assert looks_vietnamese(
        "The receipt procedure has 4 steps.\n\nSources:\n"
        "- Quy trình nhập kho › Bước 1 (sop.docx)") is False


def test_cau_tieng_viet_that_thi_bi_bao_dong():
    assert looks_vietnamese(
        "Chi tiết đơn mua P00003 từ nhà cung cấp Azure Interior.") is True


def test_moi_prompt_deu_co_ca_hai_ngon_ngu():
    for ten in ("CHITCHAT_PROMPT", "RAG_SYNTHESIS_PROMPT", "FUSE_PROMPT"):
        langs = {lang for p, _q, lang in LANGUAGE_CASES if p == ten}
        assert langs == {"vi", "en"}, ten


def test_khong_bi_bao_dong_sai_cho_anh_va_cho_viet():
    """Hồi quy: "cho" trong tiếng Anh (echo, school, anchor, chose, psychology)
    không còn dọng báo động sai bằng ranh giới từ \b."""
    assert looks_vietnamese("I need to echo this value back") is False
    assert looks_vietnamese("Go to school tomorrow") is False
    assert looks_vietnamese("Drop the anchor into the water") is False
    assert looks_vietnamese("I chose this option") is False
    assert looks_vietnamese("Psychology is the study of behavior") is False


def test_tieng_viet_that_van_dung_sau_ranh_gioi():
    """Hồi quy: tiếng Việt thật với "cho" vẫn được nhận diện đúng sau khi
    thêm ranh giới từ."""
    assert looks_vietnamese("Cho tôi xin lỗi vì đã làm việc này") is True
    assert looks_vietnamese("Vui lòng xác nhận đơn hàng này") is True
