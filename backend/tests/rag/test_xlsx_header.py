# backend/tests/rag/test_xlsx_header.py
"""Bộ dò hàng tiêu đề — spec 2026-08-29 mục 5.2.

Test ở đây thuần dữ liệu (list of list), không đọc tệp: bộ dò phải là module
lá, không biết openpyxl. Nghiệm thu trên sổ kế toán THẬT nằm ở Task 5.
"""
from src.rag.xlsx_header import find_header


def test_bo_qua_dong_tieu_de_tai_lieu_va_dong_trong():
    rows = [
        ["BÁO CÁO TÀI CHÍNH HỢP NHẤT QUÝ II/2026", None, None, None],
        [None, None, None, None],
        ["Chỉ tiêu", "Quý II", "Lũy kế", "Ghi chú"],
        ["Doanh thu thuần", 1250, 2400, None],
        ["Giá vốn hàng bán", 900, 1750, None],
        ["Lợi nhuận gộp", 350, 650, None],
    ]
    g = find_header(rows)
    assert g is not None
    assert g.row_index == 2
    assert g.labels[:2] == ["Chỉ tiêu", "Quý II"]


def test_tim_dung_hang_STT_du_nam_sau_bon_dong_rac():
    rows = [
        ["Công ty TNHH Thương mại Dịch vụ Thiên Ưng", None, None, None, None],
        ["Số 19 Đường Nguyễn Trãi, Thanh Xuân, Hà Nội", None, None, None, None],
        [None, None, None, "DANH SÁCH KHÁCH HÀNG - TK131", None],
        [None, None, None, None, " Thông tin ngân hàng"],
        ["STT", "Mã", "Tên Khách hàng", "Mã số thuế", "Số Tài Khoản"],
        [1, "KH001", "Công ty A", "0101234567", "1234567890"],
        [2, "KH002", "Công ty B", "0107654321", "9876543210"],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 4
    assert g.labels[0] == "STT"


def test_khong_lay_chuoi_cong_thuc_lam_tieu_de():
    """Sheet thật `BK NHẬP - XUẤT` lấy nhầm `$B$7:$M$100` làm nhãn cột."""
    rows = [
        ["$B$7:$M$100", None, None],
        ["Mã hàng", "Số lượng", "Đơn giá"],
        ["VT001", 10, 15000],
        ["VT002", 5, 22000],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1


def test_khong_lay_cau_huong_dan_lam_tieu_de():
    """Sheet thật `BẢNG TH N-X-T` lấy nhầm 'Chọn tháng cần in ở đây -->'."""
    rows = [
        ["  ", "Chọn tháng cần in ở đây -->", "Tháng 01 Năm 2022", "#N/A"],
        ["Mã hàng", "Tồn đầu", "Nhập", "Xuất"],
        ["VT001", 10, 5, 3],
        ["VT002", 0, 20, 15],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1


def test_sheet_khong_co_tieu_de_nhan_dien_duoc_thi_tra_None():
    """Trả None là kết quả HỢP LỆ, không phải lỗi — nó là tín hiệu để tầng
    trên phát một cảnh báo CÓ TÊN thay vì đoán bừa một hàng."""
    rows = [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]
    assert find_header(rows) is None


def test_bang_bat_dau_ngay_hang_dau_van_dung():
    rows = [
        ["Sản phẩm", "Giá", "Tồn"],
        ["Bàn", 1200000, 30],
        ["Ghế", 450000, 120],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0


def test_hang_danh_so_cot_khong_duoc_chon_lam_tieu_de():
    """Vòng sửa 1: sheet thật `PB CPTT - TK 242`/`BC KQKD` có hàng "(1)(2)(3)..."
    NGAY DƯỚI hàng tiêu đề thật; trước vòng sửa hàng đó ăn điểm cao hơn hoặc
    bằng chính hàng tiêu đề. Hàng đánh số cột không bao giờ được chọn."""
    rows = [
        ["STT", "Chỉ tiêu", "Mã", "Số năm nay", "Số năm trước"],
        ["(1)", "(2)", "(3)", "(4)", "(5)"],
        [1, "Doanh thu bán hàng", 1, 1000, 900],
        [2, "Giá vốn hàng bán", 11, 700, 650],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0
    assert g.labels[0] == "STT"


def test_bieu_mau_trong_van_do_duoc_tieu_de():
    """Vòng sửa 1: sheet thật `DM KH`/`DM NCC`/`DMHH` có hàng tiêu đề HOÀN HẢO
    nhưng chưa điền dữ liệu — trước vòng sửa, data_ratio=0 kéo điểm hàng tiêu
    đề xuống dưới ngưỡng, trả về None dù hàng tiêu đề thật hoàn toàn rõ ràng."""
    rows = [
        ["Công ty TNHH Thương mại Dịch vụ Thiên Ưng", None, None, None, None],
        ["STT", "Mã", "Tên Khách hàng", "Mã số thuế", "Số Tài Khoản"],
        [None, None, None, None, None],
        [None, None, None, None, None],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1
    assert g.labels[0] == "STT"
