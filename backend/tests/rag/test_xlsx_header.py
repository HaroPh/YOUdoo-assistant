# backend/tests/rag/test_xlsx_header.py
"""Bộ dò hàng tiêu đề — spec 2026-08-29 mục 5.2.

Test ở đây thuần dữ liệu (list of list), không đọc tệp: bộ dò phải là module
lá, không biết openpyxl. Nghiệm thu trên sổ kế toán THẬT nằm ở Task 5.
"""
from src.rag.xlsx_header import find_header, is_column_index_row


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


def test_hang_danh_so_cot_lan_nhan_thang_that_van_bi_loai():
    """Vòng sửa 2, nhóm 1: sheet thật `PB CPTT - TK 242` / `KH TSCĐ - TK 214`.

    Hàng đánh số cột của hai sheet này RỘNG 24 ô: bảy ô đầu thuần ký hiệu
    (`A B C D (1) (2) (3)=(1)/(2)`) nhưng phần còn lại là "Tháng 1".."Tháng
    12" — nhãn THẬT. Tỉ lệ ký hiệu trên toàn hàng chỉ còn ~1/3, dưới ngưỡng
    "phần lớn", nên tiêu chí tỉ lệ KHÔNG loại được; nó hoà điểm với hàng tiêu
    đề thật rồi thắng nhờ tie-break "ưu tiên hàng sau".
    """
    rows = [
        ["STT", "Tên tài sản", "Nguyên giá", "Số tháng PB", "Mức PB tháng",
         "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4", "Tháng 5",
         "Tháng 6", "Tháng 7", "Tháng 8", "Tháng 9"],
        ["A", "B", "C", "(1)", "(2)", "(3)=(1)/(2)",
         "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4", "Tháng 5",
         "Tháng 6", "Tháng 7", "Tháng 8"],
        ["CCDC001", "Máy tính", 24000000, 24, 1000000,
         1000000, 1000000, 1000000, 1000000, 1000000,
         1000000, 1000000, 1000000, 1000000],
        ["CCDC002", "Bàn ghế", 12000000, 12, 1000000,
         1000000, 1000000, 1000000, 1000000, 1000000,
         1000000, 1000000, 1000000, 1000000],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0
    assert g.labels[0] == "STT"


def test_hang_du_lieu_toan_so_khong_bi_coi_la_hang_danh_so_cot():
    """Vòng sửa 2, nhóm 2: sheet thật `TT THUẾ TNDN`.

    Hàng dữ liệu `1 | Chiết khấu thương mại | 5211 | 0 | 0 | 0` từng bị coi
    là hàng ĐÁNH SỐ CỘT (4/6 ô "trông như ký hiệu"), nên hàng MỤC ngay TRÊN
    nó được cộng oan `_COLUMN_INDEX_BONUS` và vọt lên 1.0, thắng hàng tiêu đề
    thật. Hàng đánh số cột thật thì LIỆT KÊ các chỉ số KHÁC NHAU; hàng dữ
    liệu lặp đi lặp lại số 0.
    """
    assert not is_column_index_row(
        [1, "Chiết khấu thương mại", 5211, 0, 0, 0])
    assert is_column_index_row(["(1)", "(2)", "(3)", "(4)", "(5)"])

    rows = [
        ["STT", "Chỉ tiêu", "TK SD", "PS Bên Nợ", "PS Bên Có", "Số tiền"],
        ["I", "DOANH THU", None, None, None, 0],
        [1, "Doanh thu bán hàng", 5111, 0, 0, 0],
        [2, "Doanh thu dịch vụ", 5113, 0, 0, 0],
        ["B", "Các khoản giảm trừ", None, None, None, 0],
        [1, "Chiết khấu thương mại", 5211, 0, 0, 0],
        [2, "Giảm giá hàng bán", 5213, 0, 0, 0],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0


def test_dong_chu_thich_trai_het_be_rong_khong_duoc_chon():
    """Vòng sửa 2, nhóm 3: sheet thật `Bảng Kê Mua Vào` / `Bảng Kê Bán Ra`.

    Sau khi trải ô gộp, dòng chú thích MỤC ("1. Hàng hoá, dịch vụ mua vào")
    lấp đủ mọi cột và mọi ô đều "trông như nhãn", nên nó đạt điểm tuyệt đối
    y hệt hàng tiêu đề thật rồi thắng vì nằm SAU. Nó chỉ tạo ĐÚNG MỘT nhóm
    giá trị liền kề — dấu hiệu của một ô gộp phủ hết bề rộng, không phải nhãn
    cột.
    """
    caption = ["Kỳ tính thuế: Quý I năm 2022"] * 6
    muc = ["1. Hàng hoá, dịch vụ mua vào"] * 6
    rows = [
        caption,
        ["STT", "Số hoá đơn", "Tên người bán", "Mã số thuế",
         "Giá trị mua vào", "Thuế GTGT"],
        ["[1]", "[2]", "[3]", "[4]", "[5]", "[6]"],
        muc,
        [1, 300, "Công ty TNHH Thiên Ưng", "0101145192", 260000000, 26000000],
        [2, 6, "Công ty CP Nguyên Châu", "0101315334", 4200000, 420000],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1
    assert g.labels[0] == "STT"


def test_hang_muc_hai_o_lech_cot_khong_duoc_chon_lam_tieu_de():
    """Vòng sửa 2, nhóm 2: sheet thật `BẢNG TÍNH THUẾ TNCN` / `TỜ KHAI THUẾ GTGT`.

    Hàng mục La Mã `I | CÁ NHÂN CƯ TRÚ` chỉ có 2 ô nên tự động đạt
    `label_ratio = contiguity = 1.0`, và vì nằm SAU hàng tiêu đề thật nó
    thắng tie-break. Không có tiêu chí nào trong công thức cũ nhìn ra rằng
    hai ô ấy nằm LỆCH HẲN so với các cột mà dữ liệu thật chiếm.
    """
    rows = [
        ["STT", "Họ và tên", "Chức vụ", "Lương chính", "Phụ cấp", "Thuế TNCN"],
        [1, "Hoàng Trung Thật", "GĐ", 6634615, 1769230, 331730],
        [2, "Lã Văn Nam", "P.GĐ", 6192307, 884615, 215384],
        [3, "Nguyễn Đức Việt", "KTT", 5500000, 423076, 190000],
        ["I", "CÁ NHÂN CƯ TRÚ", None, None, None, None],
        [4, "Trần Thị Hoa", "NV", 5000000, 300000, 150000],
        [5, "Phạm Văn Bình", "NV", 4800000, 250000, 140000],
        [6, "Lê Thị Mai", "NV", 4600000, 200000, 130000],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0
    assert g.labels[0] == "STT"


def test_sheet_nhieu_bang_thi_tra_None_thay_vi_chon_bang_vi_du():
    """Vòng sửa 2, nhóm 3: sheet thật `DV`.

    Sheet xếp CHỒNG nhiều bảng — một bảng ví dụ 3 cột ở đầu, bảng chính 12
    cột ở hàng 30. Bộ dò chỉ quét `SCAN_LIMIT` hàng đầu nên chỉ thấy bảng ví
    dụ và chọn nó, SAI một cách tự tin. Không dựng nổi khái niệm "nhiều bảng
    trong một sheet" trong phạm vi vòng sửa này, nhưng khi có bằng chứng rằng
    còn một bảng RỘNG HƠN HẲN ở dưới thì phải NHẬN KHÔNG BIẾT.
    """
    rows = [
        ["Khoản mục chi phí", "Thông tư 200", "Thông tư 133"],
        ["Chi phí nguyên vật liệu", 621, 154],
        ["Chi phí nhân công", 622, 154],
        ["Chi phí sản xuất chung", 627, 154],
    ]
    rows += [["Ví dụ minh hoạ số " + str(i)] for i in range(13)]
    rows += [
        ["STT", "Tên dịch vụ", "CP NVLTT", "CP NCTT", "CP SXC",
         "Giá thành", "Đơn giá", "Ghi chú"],
        [1, "Tour Đà Nẵng", 1500000, 0, 60000000, 66115384, 1000000, ""],
        [2, "Tour Cửa Lò", 0, 1200000, 22307692, 25007692, 900000, ""],
    ]
    assert find_header(rows) is None
