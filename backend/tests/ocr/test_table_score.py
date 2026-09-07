"""Thước KHÔNG CẦN ĐÁP ÁN cho chân scan — `table_score.score_unlabelled`.

Thước này quyết định hằng số bậc 2 trên corpus scan thật, nên bản thân nó phải
bị thử phá theo CẢ HAI chiều. Nhánh này đã bốn lần chốt tham số bằng một cái
thước chỉ đo một vế; các test dưới đây là cái chốt cửa đó.
"""
from src.ocr import table_score as ts


def test_two_money_values_in_different_cells_count_as_separated():
    grid = [["Tiền mặt", "111", "15.618.160.768", "12.004.331.512"]]
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert (sep, rows) == (1, 1)


def test_two_money_values_in_one_cell_count_as_merged():
    # Đúng ca hỏng thật: cột không tách nên hai số dồn vào một ô.
    grid = [["Tiền mặt", "111", "15.618.160.768 12.004.331.512"]]
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert (sep, rows) == (0, 1)


def test_degenerate_single_column_grid_scores_zero():
    # THỬ PHÁ vế GỘP: lưới một cột (mọi khe bị bỏ) phải về 0, không được
    # ăn điểm miễn phí.
    grid = [["Tiền mặt 111 15.618.160.768 12.004.331.512"],
            ["Phải thu 131 8.200.000.000 7.100.000.000"]]
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert rows == 2 and sep == 0


def test_shredded_grid_still_scores_full_on_separation_but_density_collapses():
    # THỬ PHÁ vế TÁCH VỤN, và đây là lý do hàm trả về BỐN số chứ không phải
    # một tỉ lệ: chia nhỏ thành nhiều cột rỗng KHÔNG bị vế `separated` phạt —
    # chỉ mật độ ô bắt được.
    lanh = [["Tiền mặt", "15.618.160.768", "12.004.331.512"]]
    vun = [["Tiền", "mặt", "", "15.618.160.768", "", "", "12.004.331.512", ""]]
    s1, r1, f1, t1 = ts.score_unlabelled(lanh)
    s2, r2, f2, t2 = ts.score_unlabelled(vun)
    assert (s1, r1) == (s2, r2) == (1, 1)          # vế tách: KHÔNG phân biệt nổi
    assert f2 / t2 < f1 / t1                        # vế mật độ: bắt được


def test_substring_money_values_are_matched_as_exact_tokens():
    # `160.768` là chuỗi con của `15.618.160.768`. So bằng `in` trên chuỗi sẽ
    # cho rằng nó nằm ở CẢ HAI ô rồi bỏ qua hàng (phát hiện C2). So theo token
    # thì đây là hai giá trị phân biệt nằm hai ô -> tách đúng.
    grid = [["Chỉ tiêu", "15.618.160.768", "160.768"]]
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert (sep, rows) == (1, 1)


def test_rows_with_fewer_than_two_money_values_are_not_counted():
    grid = [["Chỉ tiêu", "111", "Thuyết minh"],       # không có tiền
            ["Tiền mặt", "15.618.160.768"],           # chỉ một
            ["Mã số", "01", "02"]]                    # mã số KHÔNG phải tiền
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert (sep, rows) == (0, 0)


def test_duplicate_money_value_makes_the_row_inconclusive():
    # Cùng một chuỗi ở hai ô: không biết ô nào là ô nào -> bỏ hàng, không
    # được đoán bừa theo hướng có lợi.
    grid = [["Chỉ tiêu", "1.000.000", "1.000.000", "2.000.000"]]
    sep, rows, _, _ = ts.score_unlabelled(grid)
    assert (sep, rows) == (0, 0)
