from src.agents.disambiguation import parse_selection

OPTS = [{"id": 41, "name": "Azur Interior"}, {"id": 52, "name": "Azur Furniture"}]


def test_integer_index_one_based():
    assert parse_selection("1", OPTS) == 41
    assert parse_selection(" 2 ", OPTS) == 52


def test_integer_out_of_range_is_none():
    assert parse_selection("3", OPTS) is None
    assert parse_selection("0", OPTS) is None


def test_exact_name_match_case_insensitive():
    assert parse_selection("azur furniture", OPTS) == 52


def test_unique_substring_match():
    assert parse_selection("furniture", OPTS) == 52


def test_ambiguous_substring_is_none():
    assert parse_selection("azur", OPTS) is None


def test_garbage_is_none():
    assert parse_selection("", OPTS) is None
    assert parse_selection("xyz", OPTS) is None


# ── Cách người dùng THẬT trả lời (mục 3, đo sống 2026-08-23) ────────────────
#
# Đo qua cổng vào production: trợ lý đưa danh sách đánh số, người dùng gõ
# "cái thứ 2" ⇒ parse_selection trả None ⇒ nút hỏi LẠI y nguyên danh sách
# trong 0,2s. Trông như bị treo, và người dùng không có cách nào biết mình
# phải gõ gì. Danh sách đánh số là thứ CHÍNH TRỢ LÝ đưa ra, nên đây là ngõ cụt
# nó tự tạo cho mình.

def test_so_thu_tu_nam_trong_mot_cau():
    for cau in ("cái thứ 2", "số 2", "chọn 2", "lấy cái 2", "2 nhé",
                "cho mình cái số 2", "mục 2"):
        assert parse_selection(cau, OPTS) == 52, cau


def test_chu_so_thu_tu_tieng_viet():
    assert parse_selection("cái đầu tiên", OPTS) == 41
    assert parse_selection("thứ nhất", OPTS) == 41
    assert parse_selection("cái thứ hai", OPTS) == 52
    assert parse_selection("cái cuối", OPTS) == 52
    assert parse_selection("cuối cùng", OPTS) == 52


def test_ngoai_pham_vi_van_la_none():
    """Số nằm trong câu nhưng ngoài danh sách ⇒ None, KHÔNG bịa."""
    assert parse_selection("cái thứ 9", OPTS) is None
    assert parse_selection("mục 0", OPTS) is None


def test_TEN_uu_tien_hon_so_thu_tu():
    """Đây là ca đánh đổi, quyết định 2026-08-23.

    "2 cái bàn học sinh" vừa có số 2 vừa có tên. Người dùng gần như chắc chắn
    đang nêu TÊN kèm số lượng, không phải chọn mục 2. Nên khớp tên chạy TRƯỚC,
    số thứ tự chỉ dùng khi không tên nào khớp.
    """
    opts = [{"id": 69, "name": "Bàn học sinh gỗ MDF"},
            {"id": 70, "name": "Bàn làm việc chân sắt"}]
    assert parse_selection("2 cái bàn học sinh", opts) == 69
    # Không tên nào khớp ⇒ mới đọc số.
    assert parse_selection("2 cái", opts) == 70


def test_nhieu_so_trong_cau_thi_KHONG_doan():
    """"1 hoặc 2" là người dùng còn phân vân — hỏi lại đúng hơn là chọn bừa."""
    assert parse_selection("1 hoặc 2", OPTS) is None
    assert parse_selection("2 và 3", OPTS) is None
