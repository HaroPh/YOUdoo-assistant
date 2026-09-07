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
    from src.ocr import table as m

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
