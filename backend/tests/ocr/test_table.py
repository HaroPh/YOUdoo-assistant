from src.ocr import table as m
from src.ocr.table import median_char_width, find_column_bounds, build_grid
from src.ocr.engine import OcrWord


def word(text: str, left: int, top: int, width: int, *, line: int = 0) -> OcrWord:
    """Tạo OcrWord cho test."""
    return OcrWord(
        text=text,
        conf=99.0,
        left=left,
        top=top,
        width=width,
        height=16,
        line_id=(line, 0, 0)
    )


def test_median_char_width_is_median_not_mean():
    """Ba từ: 20/2=10, 20/4=5, 30/3=10 mỗi ký tự.

    Trung vị các tỷ lệ TỪNG TỪ = 10,0.
    Trung bình gộp (tổng rộng / tổng ký tự) = 70/9 = 7,78 — SAI.
    """
    words = [word("ab", 0, 0, 20), word("abcd", 0, 0, 20), word("abc", 0, 0, 30)]
    assert median_char_width(words) == 10.0


def test_median_char_width_survives_empty_input():
    assert median_char_width([]) > 0


def _three_col_money_table():
    """Ba hàng: nhãn ở x=100, hai cột số căn PHẢI ở x=500 và x=800."""
    words = []
    for i, (nhan, a, b) in enumerate([("Tien", "1.000", "2.000"),
                                      ("Hang", "30.000", "40.000"),
                                      ("Khac", "500.000", "600.000")]):
        words.append(word(nhan, 100, 100 + i * 30, 40, line=i))
        words.append(word(a, 500 - len(a) * 10, 100 + i * 30, len(a) * 10, line=i))
        words.append(word(b, 800 - len(b) * 10, 100 + i * 30, len(b) * 10, line=i))
    return words


def test_finds_two_bounds_between_three_columns():
    """Dùng `<=` chứ không `<`: bounds giới nằm ĐÚNG mép chữ cạnh khe (thuật toán
    lấy mép, không lấy điểm giữa khe). Đó vẫn là bộ tách hợp lệ vì phép gán cột
    so TÂM của từ — một từ có mép phải đúng bằng bounds giới thì tâm nó vẫn nằm
    hẳn bên trái. Đổi assertion ở đây là theo một thay đổi THIẾT KẾ có chủ ý,
    không phải nới test cho khớp một lỗi.
    """
    bounds = find_column_bounds(_three_col_money_table(), gap_factor=2.0, support_ratio=0.6)
    assert len(bounds) == 2
    assert 140 <= bounds[0] < 450 and 500 <= bounds[1] < 730


def test_intra_cell_word_gap_is_not_a_column_bound():
    """Đây là chỗ cơ chế cụm-mép hỏng: khe giữa `Tai` và `san` là một bề rộng
    ký tự, khe sang cột số là 30 — phải phân biệt được hai loại khe đó."""
    words = []
    for i in range(3):
        words.append(word("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(word("san", 140, 100 + i * 30, 30, line=i))
        words.append(word("100", 470, 100 + i * 30, 30, line=i))
    bounds = find_column_bounds(words, gap_factor=2.0, support_ratio=0.6)
    assert len(bounds) == 1, "chi duoc mot bounds: giua nhan hai tu va cot so"
    assert 170 <= bounds[0] < 470


def test_unaligned_prose_yields_no_bounds():
    """Không có bộ dò bảng: trang văn xuôi tự nhiên suy biến về một cột."""
    words = [word(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    assert find_column_bounds(words, gap_factor=2.0, support_ratio=0.6) == []


def test_build_grid_returns_three_columns():
    grid = build_grid(_three_col_money_table(), gap_factor=2.0, support_ratio=0.6)
    assert grid == [["Tien", "1.000", "2.000"],
                    ["Hang", "30.000", "40.000"],
                    ["Khac", "500.000", "600.000"]]


def test_build_grid_joins_multi_word_cell():
    """Nhãn nhiều từ phải thành MỘT ô, không phải nhiều cột."""
    words = []
    for i in range(3):
        words.append(word("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(word("san", 140, 100 + i * 30, 30, line=i))
        words.append(word("100", 470, 100 + i * 30, 30, line=i))
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [["Tai san", "100"]] * 3


def test_prose_degrades_to_single_column():
    words = [word(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [[f"dong{i}"] for i in range(6)]


def test_defaults_resolve_at_call_time_not_definition_time():
    """Bẫy tham số mặc định đóng băng: Python tính giá trị mặc định MỘT LẦN lúc
    định nghĩa hàm. Nếu viết `def f(*, x=HANG_SO)` thì đổi HANG_SO lúc chạy sẽ
    KHÔNG có tác dụng — đã cắn tầng OCR bậc 1 một lần và suýt vô hiệu hoá chính
    phép thử phá của nó. Test này gác đúng chuyện đó."""

    words = _three_col_money_table()
    goc = m.GAP_FACTOR
    try:
        m.GAP_FACTOR = 1000.0          # không khe nào đủ lớn -> một cột
        it_cot = m.build_grid(words)
        m.GAP_FACTOR = 2.0             # bình thường -> ba cột
        nhieu_cot = m.build_grid(words)
    finally:
        m.GAP_FACTOR = goc
    assert len(it_cot[0]) < len(nhieu_cot[0]), (
        "đổi hằng số lúc chạy KHÔNG đổi kết quả -> mặc định đã bị đóng băng")


def test_rows_keep_input_order_not_y_order():
    """Bậc 1 đã ghi bài học: khác biệt thứ tự đọc từng bị nhầm thành OCR kém.

    Đầu vào ở đây CỐ Ý không theo thứ tự y (từ ở y=500 đứng trước từ ở y=100),
    mô phỏng một trang mà tesseract đọc theo thứ tự khác thứ tự hình học. Đầu
    ra phải theo ĐÚNG THỨ TỰ ĐẦU VÀO, chứng minh ta không tự sắp lại theo y.
    Đòi đầu ra theo `line_id` mới là sắp lại — đúng thứ bị cấm."""
    words = [word("duoc_doc_truoc", 100, 500, 40, line=1),
             word("duoc_doc_sau", 100, 100, 40, line=0)]
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [["duoc_doc_truoc"], ["duoc_doc_sau"]]


# ── DẢI HÀNG TRÔNG NHƯ BẢNG (C1) ──────────────────────────────────────────


def test_row_runs_skip_the_sparse_letterhead_block():
    """Hàng letterhead ít ô không rỗng KHÔNG được vào dải bảng.

    Đây là lõi của bản vá C1: lưới bậc 2 phủ CẢ TRANG (bậc 1 nhả đúng một
    vùng), nên nếu không cắt letterhead ra thì `column_names()` lấy nó làm
    TÊN CỘT — đo được 136 ký tự tên cột trên SCID tr12."""
    grid = [["CONG TY ABC", "", "", ""],
            ["Dia chi: 1 Nguyen Trai", "", "", ""],
            ["Chi tieu", "Ma so", "Cuoi ky", "Dau nam"],
            ["Tien mat", "111", "1.000", "900"],
            ["Tien gui", "112", "2.000", "1.800"]]
    assert m.table_row_runs(grid) == [(2, 5)]


def test_run_shorter_than_min_rows_is_not_a_table():
    # Khe HAI hàng (> MAX_RUN_GAP_ROWS=1) nên KHÔNG bắc cầu — dải một hàng ở
    # đầu đứng riêng và bị loại vì dưới MIN_TABLE_RUN_ROWS.
    grid = [["a", "b", "c", "d"],
            ["x", "", "", ""],
            ["y", "", "", ""],
            ["a", "b", "c", "d"],
            ["a", "b", "c", "d"]]
    assert m.table_row_runs(grid) == [(3, 5)]


def test_runs_separated_by_more_than_max_gap_stay_separate():
    # Bất biến PHẢI giữ khi thêm bắc cầu: hai bảng thật sự rời nhau không
    # được gộp, nếu không bảng sau mượn TÊN CỘT của bảng trước.
    grid = [["a", "b", "c", "d"],
            ["a", "b", "c", "d"],
            ["chu thich giua bang", "", "", ""],
            ["", "", "", ""],
            ["a", "b", "c", "d"],
            ["a", "b", "c", "d"]]
    assert m.table_row_runs(grid) == [(0, 2), (4, 6)]


def test_single_junk_row_inside_a_table_is_bridged():
    # CỐ Ý, và đây là cả lý do MAX_RUN_GAP_ROWS tồn tại: trên SCID tr12 một
    # hàng chứa ĐÚNG MỘT ký tự (vệt dấu mộc) nằm giữa hàng header thật và
    # thân bảng, cắt header thành dải dài 1 rồi vứt đi, nên `column_names`
    # trả rỗng và mọi cột thành "Cột N".
    grid = [["CHỈ TIÊU", "Mã số", "Số cuối kỳ", "Số đầu năm"],
            ["C", "", "", ""],
            ["Tiền", "111", "1.000", "2.000"],
            ["Nợ", "112", "3.000", "4.000"]]
    assert m.table_row_runs(grid) == [(0, 4)]


def test_run_does_not_extend_past_its_last_table_row():
    # Khe ở CUỐI không được kéo dài dải: hàng rác cuối trang phải rơi ra
    # ngoài để đi đường dòng-phẳng (qua heading_level + lọc furniture).
    grid = [["a", "b", "c", "d"],
            ["a", "b", "c", "d"],
            ["rac cuoi trang", "", "", ""]]
    assert m.table_row_runs(grid) == [(0, 2)]


def test_find_header_rows_picks_the_money_free_row_above_the_body():
    grid = [["CÔNG TY CP", "", "", ""],
            ["CHỈ TIÊU", "Mã số", "Số cuối kỳ", "Số đầu năm"],
            ["Tiền", "111", "1.000.000", "2.000.000"]]
    assert m.find_header_rows(grid, 2) == [grid[1]]


def test_find_header_rows_stops_at_a_row_containing_money():
    # Hàng có tiền = đã chạm thân bảng; không leo tiếp lên trên nữa, nếu
    # không sẽ vớ phải letterhead ở tít trên.
    grid = [["CHỈ TIÊU", "Mã số", "Số cuối kỳ", "Số đầu năm"],
            ["Tiền", "111", "1.000.000", "2.000.000"],
            ["Nợ", "112", "3.000.000", "4.000.000"]]
    assert m.find_header_rows(grid, 2) == []


def test_find_header_rows_returns_empty_when_nothing_qualifies():
    grid = [["chỉ một ô", "", "", ""],
            ["Tiền", "111", "1.000.000", "2.000.000"]]
    assert m.find_header_rows(grid, 1) == []


def test_find_header_rows_reads_constants_at_call_time():
    grid = [["a", "b", "", ""],
            ["Tiền", "111", "1.000.000", "2.000.000"]]
    assert m.find_header_rows(grid, 1) == []       # 2 ô < MIN_HEADER_CELLS=3
    goc = m.MIN_HEADER_CELLS
    try:
        m.MIN_HEADER_CELLS = 2
        assert m.find_header_rows(grid, 1) == [grid[0]]
    finally:
        m.MIN_HEADER_CELLS = goc


def test_row_runs_read_constants_at_call_time():
    """Cùng bẫy đã cắn bậc 1: hằng số dùng làm giá trị mặc định của tham số
    thì bị đóng băng lúc định nghĩa hàm."""
    grid = [["a", "b", "", ""], ["a", "b", "", ""]]
    assert m.table_row_runs(grid) == []          # 2 ô < MIN_TABLE_ROW_CELLS=4
    goc = m.MIN_TABLE_ROW_CELLS
    try:
        m.MIN_TABLE_ROW_CELLS = 2
        assert m.table_row_runs(grid) == [(0, 2)]
    finally:
        m.MIN_TABLE_ROW_CELLS = goc


def test_has_numeric_data_true_for_a_real_table_row():
    assert m.has_numeric_data(["Tiền", "111", "1.000.000", "2.000.000"])


def test_has_numeric_data_false_for_a_prose_row():
    # Ca that: dong tieu de muc trong bao cao luu chuyen tien te, bi xe lam
    # doi qua hai cot truoc khi co dinh tuyen nay.
    assert not m.has_numeric_data(
        ["a", "Il.", "Lưu chuyển tiền từ hoạt", "động đầu tư", ""])


def test_has_numeric_data_sees_a_digit_anywhere_in_any_cell():
    assert m.has_numeric_data(["", "", "Điều 5 khoản", ""])
    assert not m.has_numeric_data(["", "", "Điều năm khoản", ""])


# ─── trang thuyết minh: dữ liệu bảng = tiền/gạch, cột rác gáy (2026-09-11) ──────
def test_has_money_data_money_token_or_two_dashes():
    assert m.has_money_data(["", "Đến 1 năm", "4.941.448.061", "15.611.296.360"])
    assert m.has_money_data(["Cổ phiếu ưu đãi", "-", "-"])
    assert m.has_money_data(["Trên 5 năm", "-", "94.841.935.650"])
    # Một gạch lẻ là dấu nối trong khối chữ ký / letterhead, không phải ô bảng.
    assert not m.has_money_data(["KE TOAN TRUONG", "-", "Binh Dinh, ngay 11 thang 07"])
    assert not m.has_money_data(["r", "29.", "CAM KET", "THUÊ VA CHO THUÊ HOAT ĐỘNG"])
    assert not m.has_money_data(["Cho năm tài chính kết thúc", "31 tháng", "12 năm", "2022"])
    assert not m.has_money_data(["Số lượng cổ phần", "29200", "625000"])   # không nhóm 3 -> không phải tiền in


def test_margin_junk_columns_detects_binding_shadow_edge_only():
    grid = [["r", "29.", "CAM KET", "THUÊ"], ["c", "Công ty", "hiện đang", "thuê"],
            ["la", "các hợp", "đồng", ""], ["E", "ngày kết", "thúc", "kỳ"],
            ["r", "Đến 1 năm", "4.941.448.061", "15.611.296.360"], ["[", "30.", "SỰ KIỆN", ""]]
    assert m.margin_junk_columns(grid) == {0}
    # Cột mã số thật (chữ số) không phải rác dù ngắn.
    ma = [["100", "TÀI SẢN", "1", "2"], ["110", "Tiền", "1", "2"], ["111", "Tiền", "1", "2"],
          ["112", "Tương đương", "1", "2"], ["120", "Đầu tư", "1", "2"]]
    assert m.margin_junk_columns(ma) == set()
    # Dưới MARGIN_MIN_CELLS ô -> không kết luận.
    assert m.margin_junk_columns(grid[:4]) == set()
    # Cột giữa toàn ký tự rác KHÔNG bị xét (chỉ rìa).
    giua = [["Tiền", "|", "1.000", "2.000"]] * 6
    assert m.margin_junk_columns(giua) == set()
    assert m.margin_junk_columns([]) == set()
