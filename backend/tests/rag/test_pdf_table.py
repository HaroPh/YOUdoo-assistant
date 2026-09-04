from src.rag.pdf_table import merge_table_rows, split_header_body, column_names, row_to_text, checksum_gap


def test_merge_ca_hai_che_do_khop_hoan_toan():
    default_rows = [["1", "Mã A", "10%"], ["2", "Mã B", "5%"]]
    text_rows = [["1", "Mã A", "10%"], ["2", "Mã B", "5%"]]
    merged = merge_table_rows(default_rows, text_rows)
    assert merged == [(["1", "Mã A", "10%"], False), (["2", "Mã B", "5%"], False)]


def test_merge_text_co_hang_thua_vi_mac_dinh_mat_hang_vat_trang():
    default_rows = [["1", "Mã A", "10%"], ["3", "Mã C", "7%"]]
    text_rows = [["1", "Mã A", "10%"], ["2", "Mã B", ""], ["3", "Mã C", "7%"]]
    merged = merge_table_rows(default_rows, text_rows)
    assert merged == [
        (["1", "Mã A", "10%"], False),
        (["2", "Mã B", ""], True),
        (["3", "Mã C", "7%"], False),
    ]


def test_merge_mac_dinh_co_hang_thua_doi_xung():
    default_rows = [["1", "Mã A", "10%"], ["2", "Mã B", "5%"], ["3", "Mã C", "7%"]]
    text_rows = [["1", "Mã A", "10%"], ["3", "Mã C", "7%"]]
    merged = merge_table_rows(default_rows, text_rows)
    assert merged == [
        (["1", "Mã A", "10%"], False),
        (["2", "Mã B", "5%"], False),
        (["3", "Mã C", "7%"], False),
    ]


# Bảng thật bieumau_bctc_hopnhat.pdf trang 1, rút gọn còn 3 cột để dễ đọc.
_BANG_BCTC = [
    ["", "Thuyết", "Số cuối"],
    ["TÀI SẢN", None, None],
    [None, "minh", "năm (3)"],
    ["", None, None],
    ["1", "2", "3"],                          # hàng đánh số cột
    ["I. Tiền", "100", "1.234.567"],          # hàng dữ liệu đầu tiên
    ["1. Tiền mặt", "111", "234.567"],
]


def test_split_header_body_nhieu_dong_va_hang_danh_so_cot():
    header, body, dung_mac_dinh = split_header_body(_BANG_BCTC)
    assert header == _BANG_BCTC[:5]
    assert body == _BANG_BCTC[5:]
    assert dung_mac_dinh is False


def test_split_header_body_hang_danh_so_cot_khong_bi_hieu_nham_du_lieu():
    # Tự nó: chỉ đưa đúng 1 hàng đánh số cột — không có hàng dữ liệu thật nào
    # theo sau, nên chốt an toàn phải kích hoạt (không được coi hàng đánh số
    # cột LÀ dữ liệu).
    rows = [["1", "2", "3"]]
    header, body, dung_mac_dinh = split_header_body(rows)
    assert dung_mac_dinh is True
    assert body == rows          # chốt an toàn: hàng DUY NHẤT thành thân


def test_split_header_body_bang_toan_chu_khong_tin_hieu_so_kich_chot_an_toan():
    rows = [["TT", "Biểu mẫu", "Tên báo cáo"], ["Ghi chú", "chung", "cho form"]]
    header, body, dung_mac_dinh = split_header_body(rows)
    assert dung_mac_dinh is True
    assert header == rows[:1]
    assert body == rows[1:]


def test_split_header_body_mot_hang_duy_nhat_khong_tin_hieu_so_van_thanh_than():
    # Bảng vỡ trang: pdfplumber trả 1 hàng duy nhất, không có gì trước nó để
    # làm header. Header rỗng còn hơn nuốt mất hàng đó vào "header" và không
    # bao giờ phát ra như dữ liệu (spec §3.4 chốt an toàn).
    rows = [["Cộng", "...", "..."]]
    header, body, dung_mac_dinh = split_header_body(rows)
    assert header == []
    assert body == rows
    assert dung_mac_dinh is True


def test_column_names_ghep_nhieu_dong_bo_qua_hang_danh_so_cot():
    # header trả về từ split_header_body của _BANG_BCTC ở Step 6 — GỒM CẢ
    # hàng đánh số cột ['1','2','3'] (nó thuộc header, không thuộc thân).
    header = _BANG_BCTC[:5]
    names = column_names(header)
    assert names == ["TÀI SẢN", "Thuyết minh", "Số cuối năm (3)"]


def test_column_names_cot_rong_dung_ten_vi_tri():
    header = [["", None], [None, "Giá trị"]]
    assert column_names(header) == ["Cột 1", "Giá trị"]


def test_column_names_header_rong_tra_danh_sach_rong():
    assert column_names([]) == []


def test_row_to_text_tu_du_nghia():
    row = ["I. Tiền", "100", "1.234.567"]
    columns = ["TÀI SẢN", "Mã số", "Số cuối năm"]
    assert row_to_text(row, columns) == (
        "TÀI SẢN: I. Tiền | Mã số: 100 | Số cuối năm: 1.234.567")


def test_row_to_text_thieu_ten_cot_dung_vi_tri():
    assert row_to_text(["x", "y"], ["Tên"]) == "Tên: x | Cột 2: y"


def test_checksum_gap_lien_mach_tra_none():
    body = [["1", "a"], ["2", "b"], ["3", "c"]]
    assert checksum_gap(body) is None


def test_checksum_gap_dut_doan_bao_ro_vi_tri():
    body = [["1", "a"], ["2", "b"], ["4", "d"]]
    assert checksum_gap(body) == "cột đếm đứt đoạn tại: 2→4"


def test_checksum_gap_khong_phai_cot_dem_im_lang_dung():
    body = [["Mã A", "x"], ["Mã B", "y"]]
    assert checksum_gap(body) is None


def test_checksum_gap_bang_rong_tra_none():
    assert checksum_gap([]) is None
