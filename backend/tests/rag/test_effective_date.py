# backend/tests/rag/test_effective_date.py
"""Trích ngày hiệu lực của văn bản luật — unit thuần, không cần DB/PDF.

VÌ SAO. Corpus 98,7% là PDF luật. Sẽ có lúc bản cũ và bản mới của cùng một
luật cùng nằm trong corpus (chủ dự án xác nhận 2026-08-20), và khi đó model
trộn hai bản là rủi ro TÍNH ĐÚNG — đúng loại hỏng đã đo được với cặp Điều
418/301, chỉ nghiêm trọng hơn vì nó là hiệu lực pháp lý.

Đợt này CHỈ thu thập và hiển thị, CHƯA lọc: hôm nay chưa có bản nào bị thay
thế, nên viết bộ lọc ngay sẽ tạo một nhánh code không bao giờ chạy — đúng cách
reranker, chân sparse và sổ ngân sách đã chết.
"""
import datetime as dt

from src.rag.parse import extract_effective_date


def test_bat_duoc_dang_chuan():
    t = "Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025, trừ trường hợp..."
    assert extract_effective_date(t) == dt.date(2025, 7, 1)


def test_bat_duoc_khi_thang_co_so_0_dau():
    t = "có hiệu lực thi hành từ ngày 01 tháng 01 năm 2017."
    assert extract_effective_date(t) == dt.date(2017, 1, 1)


def test_khong_co_ngay_tra_ve_None():
    # luat-doanhnghiep.pdf KHÔNG có mục "Hiệu lực thi hành" — None là kết quả
    # hợp lệ, không phải lỗi.
    assert extract_effective_date("Điều 218. Quy định chi tiết thi hành.") is None


def test_chuoi_rong_tra_ve_None():
    assert extract_effective_date("") is None
    assert extract_effective_date(None) is None


def test_bo_qua_hieu_luc_CUA_HOP_DONG_khong_phai_cua_luat():
    # Bẫy thật: cụm "có hiệu lực" xuất hiện dày đặc trong NỘI DUNG điều luật
    # (hiệu lực của hợp đồng, của giao dịch). Chỉ mẫu "hiệu lực THI HÀNH từ
    # ngày ..." mới là ngày của chính văn bản.
    t = ("Hợp đồng có hiệu lực từ ngày 15 tháng 3 năm 2020 theo thỏa thuận "
         "của các bên.")
    assert extract_effective_date(t) is None


def test_lay_lan_khop_DAU_TIEN_cua_mau_dung():
    t = ("Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025. "
         "Luật cũ hết hiệu lực thi hành từ ngày 01 tháng 1 năm 2026.")
    assert extract_effective_date(t) == dt.date(2025, 7, 1)


def test_ngay_khong_hop_le_tra_ve_None_thay_vi_ne_m_loi():
    # Trích sai không được làm vỡ ingest cả tài liệu.
    t = "có hiệu lực thi hành từ ngày 45 tháng 13 năm 2025"
    assert extract_effective_date(t) is None
