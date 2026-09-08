from src.rag.pdf_table import (bat_dong_so_cot, checksum_gap, column_names,
                               hang_khong_gia_tri, merge_table_rows, row_to_text,
                               so_cot_dai_dien, split_header_body)


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


# Bảng biểu mẫu THƯA thật (bieumau_bctc_hopnhat.pdf) — mọi hàng thân chỉ có
# nhãn + mã số điền (2/5 ô), ba cột số tiền để TRỐNG (form chưa điền). Đây
# đúng ca đo được ~79/1106 hàng bị lẫn cột do split_header_body nuốt hàng
# thân vào header (bug tìm ra khi nghiệm thu Task 5, xem ghi chú thực thi).
_BANG_THUA = [
    ["", "Thuyết", "Số cuối", "kỳ", "Số đầu kỳ"],
    ["TÀI SẢN", None, None, None, None],
    ["1", "2", "3", "4", "5"],                       # hàng đánh số cột
    ["I. Tiền", "100", None, None, None],            # hàng thân THƯA (2/5 ô)
    ["1. Tiền mặt", "111", None, None, None],        # hàng thân THƯA (2/5 ô)
]


def test_split_header_body_bang_thua_hang_than_nhieu_o_rong_van_vao_than():
    # Bug thật (đo 2026-09-04): nhánh "đa số ô rỗng → header" kiểm TRƯỚC
    # nhánh "có ô số liệu thuần → thân" nuốt MỌI hàng thân thật của bảng
    # biểu mẫu thưa vào header, vì các hàng đó có >50% ô rỗng. Ưu tiên tín
    # hiệu số liệu thuần TRƯỚC mới phân đúng — hàng có mã số ('100', '111')
    # phải vào THÂN dù đa số ô khác rỗng.
    header, body, dung_mac_dinh = split_header_body(_BANG_THUA)
    assert header == _BANG_THUA[:3]
    assert body == _BANG_THUA[3:]
    assert dung_mac_dinh is False


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


# ── Fix wave sau review toàn nhánh (2026-09-04) ──────────────────────────────
# Critical #1: hai chế độ trích xuất BẤT ĐỒNG SỐ CỘT thì gộp làm MẤT CẢ CỘT.
# Số liệu thật: luat-thuexuatnhapkhau.pdf trang 12-25, số dòng mang mức thuế
# suất ("0-10", "15-25") 247 (pypdf thô) → 14 (B4 trước fix) → 240 (sau fix).


def test_so_cot_dai_dien_bo_qua_hang_dau_toan_rong():
    # Hàng đầu toàn None là dòng đệm của lưới pdfplumber — số ô của nó không
    # phản ánh cấu trúc thật, phải lấy hàng đầu tiên CÓ nội dung.
    assert so_cot_dai_dien([[None, None], ["1", "A", "B", "0-10"]]) == 4
    assert so_cot_dai_dien([]) == 0
    assert so_cot_dai_dien([["", None], [" ", ""]]) == 0


def test_bat_dong_so_cot_phat_hien_lech_4_vs_2():
    default_rows = [["1", "03.03", "Cá, đông lạnh", "0-10"]]
    text_rows = [["03.03", "Cá, đông lạnh"]]
    assert bat_dong_so_cot(default_rows, text_rows) == (4, 2)


def test_bat_dong_so_cot_im_lang_khi_khop_hoac_luoi_rong():
    khop = [["1", "A"], ["2", "B"]]
    assert bat_dong_so_cot(khop, [["3", "C"]]) is None
    # Một lưới rỗng: không có gì để đối chiếu — KHÔNG được báo bất đồng, nếu
    # không mọi bảng chỉ dò được ở một chế độ đều sinh cảnh báo rác.
    assert bat_dong_so_cot(khop, []) is None
    assert bat_dong_so_cot([], khop) is None


def test_lech_so_cot_thi_ket_qua_chi_dung_che_do_mac_dinh():
    """Khi bất đồng số cột, đường xử lý bỏ hẳn `text_rows` — kết quả gộp phải
    GIỮ NGUYÊN lưới 4 cột. Ca đối chứng ngay dưới cho thấy vì sao: gộp thẳng
    hai lưới lệch cột làm cột thứ 4 ("Khung thuế suất") biến mất."""
    default_rows = [["STT", "Nhóm hàng", "Mô tả", "Khung thuế suất"],
                    ["1", "03.03", "Cá, đông lạnh", "0-10"],
                    ["2", "03.04", "Phi-lê cá", "15-25"]]
    text_rows = [["03.03", "Cá, đông lạnh"], ["03.04", "Phi-lê cá"],
                 ["03.05", "Cá khô"]]
    assert bat_dong_so_cot(default_rows, text_rows) == (4, 2)
    gop = merge_table_rows(default_rows, [])
    assert [r for r, _ in gop] == default_rows
    assert all(len(r) == 4 for r, _ in gop)


def test_doi_chung_gop_thang_hai_luoi_lech_cot_lam_mat_cot_cuoi():
    """Ca ĐỐI CHỨNG ghi lại chính lỗi đã đo — không phải hành vi mong muốn.
    Nếu ai đó gỡ cổng `bat_dong_so_cot` ở `_khoi_bang`, đây là thứ sẽ xảy ra:
    các hàng lấy từ chế độ `text` chỉ còn 2 ô, mọi mức thuế suất ở ô thứ 4
    biến mất khỏi output."""
    default_rows = [["1", "03.03", "Cá, đông lạnh", "0-10"]]
    text_rows = [["03.04", "Phi-lê cá"], ["03.03", "Cá, đông lạnh"]]
    gop = [r for r, _ in merge_table_rows(default_rows, text_rows)]
    assert any(len(r) == 2 for r in gop), (
        "ca đối chứng không còn tái hiện được lỗi — nếu merge_table_rows đã "
        "tự xử lý lệch cột thì xem lại có còn cần cổng bat_dong_so_cot không")


# ── Important #3: hàng KHÔNG mang giá trị nào ────────────────────────────────
# Số liệu thật: bieumau_bctc_hopnhat.pdf 951/1625 chunk atomic (59%) chỉ là
# khung "Cột X: | Cột Y:" không giá trị.


def test_hang_khong_gia_tri_nhan_dien_dung():
    assert hang_khong_gia_tri([None, "", "   ", None])
    assert hang_khong_gia_tri([])
    assert not hang_khong_gia_tri([None, "", "280", None])
    assert not hang_khong_gia_tri(["Tài sản ngắn hạn", "", ""])


# --- `compact=True`: bo o RONG va nhan `Cot N` -------------------------------
# Do tren corpus san xuat sau khi nap ban scan that dau tien: 37,7% so o trong
# chunk bang OCR la o rong mang nhan `Cot N`, chiem 20,6% do dai chunk, va
# chung di THANG vao vector nhung -- truy van "tai san ngan han cuoi ky" khong
# lay duoc hang ma 100 du o k=50.

def test_row_to_text_compact_drops_empty_cells():
    row = ["A-", "", "TÀI SẢN NGẮN HẠN", "", "100", "", "566.695.646.268"]
    cols = ["Cột 1", "Cột 2", "Cột 3", "CHỈ TIÊU", "Mã số", "Thuyết minh",
            "Số cuối kỳ"]
    assert row_to_text(row, cols, compact=True) == (
        "A- | TÀI SẢN NGẮN HẠN | Mã số: 100 | Số cuối kỳ: 566.695.646.268")


def test_row_to_text_compact_keeps_value_but_drops_generic_name():
    # `Cot 3` khong noi len dieu gi; gia tri thi co.
    assert row_to_text(["x"], ["Cột 3"], compact=True) == "x"
    assert row_to_text(["x"], ["Mã số"], compact=True) == "Mã số: x"


def test_row_to_text_compact_keeps_a_real_name_even_when_it_looks_numbered():
    # Chi dung mau `Cot <so>` moi la nhan vo nghia; dung an nham ten that.
    assert row_to_text(["x"], ["Cột mốc"], compact=True) == "Cột mốc: x"
    assert row_to_text(["x"], ["Quý 3"], compact=True) == "Quý 3: x"


def test_row_to_text_default_is_byte_identical_to_before_compact_existed():
    # BAT BIEN: duong bang vector va .docx goi ham nay va output cua chung
    # KHONG duoc doi mot byte. Mac dinh phai giu nguyen ca o rong lan nhan.
    row = ["A-", "", "TÀI SẢN NGẮN HẠN"]
    cols = ["Cột 1", "Cột 2", "Cột 3"]
    assert row_to_text(row, cols) == (
        "Cột 1: A- | Cột 2:  | Cột 3: TÀI SẢN NGẮN HẠN")


def test_row_to_text_compact_on_an_all_empty_row_gives_empty_string():
    assert row_to_text(["", "", ""], ["Cột 1", "Cột 2", "Cột 3"],
                       compact=True) == ""
