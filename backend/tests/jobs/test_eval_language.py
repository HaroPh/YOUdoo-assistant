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
