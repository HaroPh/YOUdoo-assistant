"""Suy phân cấp từ chữ cho .docx — spec 2026-09-04 mục 4, 5, 6.

Hàm nhận CẢ TÀI LIỆU (`list[str]`) chứ không chấm từng dòng độc lập, vì quy
tắc "đánh số trần phải tự chứng minh" cần bằng chứng ở phạm vi tài liệu.
Không test nào ở đây cần một tệp .docx thật — module là lá thuần.
"""
from src.rag.parse import DOCX_LEVEL, docx_heading_levels


def test_tu_khoa_PHAN_nhan_thang_khong_can_bang_chung():
    """`PHẦN`/`Chương`/`Mục` là TỪ KHOÁ, gần như không bao giờ là văn xuôi,
    nên không cần bằng chứng như nhóm đánh số trần."""
    out = docx_heading_levels(["PHẦN I - QUY ĐỊNH CHUNG", "Nội dung nào đó."])
    assert out[0] == DOCX_LEVEL["phan"]
    assert out[1] is None


def test_mot_muc_La_Ma_dung_mot_minh_KHONG_phai_tieu_de():
    """Bằng chứng thiếu: chỉ có `I.`, không có `II.`. Một chữ cái lạc giữa
    văn xuôi không được thành tiêu đề."""
    out = docx_heading_levels(["I. Đặc điểm hoạt động", "Công ty cổ phần."])
    assert out[0] is None


def test_hai_muc_La_Ma_ke_tiep_trong_day_thi_ca_hai_la_tieu_de():
    out = docx_heading_levels(["I. Đặc điểm hoạt động",
                               "Công ty cổ phần.",
                               "II. Kỳ kế toán"])
    assert out[0] == DOCX_LEVEL["roman"]
    assert out[2] == DOCX_LEVEL["roman"]
    assert out[1] is None


def test_bang_chung_khong_doi_hoi_hai_dong_LIEN_NHAU():
    """"Kế tiếp trong DÃY", không phải "kề nhau trên trang" — `I.` và `II.`
    cách nhau 3 dòng vẫn là bằng chứng hợp lệ. Hiểu nhầm chỗ này thì quy tắc
    gần như không bao giờ kích hoạt."""
    out = docx_heading_levels(["I. Mục một", "a", "b", "c", "II. Mục hai"])
    assert out[0] == DOCX_LEVEL["roman"]
    assert out[4] == DOCX_LEVEL["roman"]


def test_ho_chu_cai_cung_can_bang_chung_va_co_cap_rieng():
    """Mẫu thứ tư của spec. `A.` một mình không đủ; `A.` rồi `B.` thì đủ.
    Và họ chữ cái phải THẤP HƠN họ La Mã trong cây (35 < 38)."""
    thieu = docx_heading_levels(["A. Một mục lẻ", "Nội dung."])
    assert thieu[0] is None

    du = docx_heading_levels(["A. Tài sản ngắn hạn",
                              "Nội dung.",
                              "B. Tài sản dài hạn"])
    assert du[0] == DOCX_LEVEL["letter"]
    assert du[2] == DOCX_LEVEL["letter"]
    assert DOCX_LEVEL["roman"] < DOCX_LEVEL["letter"]


def test_so_tran_co_con_mang_cung_tien_to_thi_la_tieu_de():
    """`12.` là tiêu đề VÌ `12.1` tồn tại — bằng chứng nằm trong chính tài
    liệu. Đây là ca thật của `b09-dn.docx`: trước bản sửa, CON là tiêu đề mà
    CHA thì không, bất nhất còn tệ hơn cả hai thái cực."""
    out = docx_heading_levels(["12. Tài sản sinh học",
                               "12.1. Tài sản sinh học khác",
                               "12.2. Súc vật cho sản phẩm"])
    assert out[0] == DOCX_LEVEL["arabic"]


def test_cha_dung_cap_CAO_HON_con():
    out = docx_heading_levels(["12. Tài sản sinh học",
                               "12.1. Tài sản sinh học khác"])
    assert out[0] < out[1], "cấp nhỏ hơn = cao hơn trong cây"


def test_so_tran_khong_co_bang_chung_nao_thi_KHONG_phai_tieu_de():
    out = docx_heading_levels(["7. Một khoản lẻ nằm giữa văn xuôi.",
                               "Câu tiếp theo không đánh số."])
    assert out[0] is None


def test_dong_IN_HOA_van_duoc_giu_nhu_truoc():
    out = docx_heading_levels(["BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH", "Nội dung."])
    assert out[0] == DOCX_LEVEL["upper"]
    assert out[1] is None


def test_muc_La_Ma_IN_HOA_CUNG_CAP_voi_muc_La_Ma_thuong():
    """Cùng một họ phải cùng cấp bất kể viết hoa. Nếu nhánh IN HOA được kiểm
    TRƯỚC nhánh đánh số thì `II. CÁ NHÂN CƯ TRÚ` ra cấp khác `I. Đặc điểm`,
    và stack breadcrumb lồng sai."""
    out = docx_heading_levels(["I. Đặc điểm hoạt động", "II. CÁ NHÂN CƯ TRÚ"])
    assert out[0] == out[1] == DOCX_LEVEL["roman"]


def test_khong_nham_tien_te_thanh_muc_danh_so():
    out = docx_heading_levels(["Tổng cộng 5.000.000 đồng.",
                               "1. Mục thật", "2. Mục thật nữa"])
    assert out[0] is None


def test_tu_khoa_luat_van_giu_dung_thu_bac_cu():
    out = docx_heading_levels(["Chương I", "Mục 1", "Điều 5. Định mức chi"])
    assert out[0] == DOCX_LEVEL["chuong"]
    assert out[1] == DOCX_LEVEL["muc"]
    assert out[2] == DOCX_LEVEL["dieu"]
    assert out[0] < out[1] < out[2]
