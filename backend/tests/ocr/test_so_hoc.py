"""`src/ocr/so_hoc.py` — cổng số học cho bảng tài chính, dùng được trong production.

Spec: docs/superpowers/specs/2026-09-11-ocr-bac-3-vlm-kiem-so-hoc-design.md.

Vì sao tồn tại: VLM sẽ đọc cả SỐ trên trang Tesseract hỏng hẳn, và số đó chỉ được
lưu khi qua được số học của chính báo cáo. Module này là bộ đánh giá duy nhất —
CLI `tests/fixtures/ocr_bang_that/kiem_so_hoc.py` uỷ quyền lại cho nó, nên cổng
118/118 trên đáp án đã duyệt canh chính bộ đánh giá production.

Mọi công thức trong test là công thức THẬT in trên DVT_2022 tr7/8/9 (TT 107).
"""
import pytest

from src.ocr import so_hoc
from src.ocr.so_hoc import BAD, DASH, Constraint


# --- parse ô tiền ----------------------------------------------------------

@pytest.mark.parametrize("chuoi,mong", [
    ("19.078.257.265", 19078257265),
    ("(58.099.826.029)", -58099826029),
    ("750.005.854", 750005854),
    ("-", DASH),
    ("–", DASH),           # en dash — máy scan/VLM hay trả về thay gạch ngang
    ("  8.331.692.341 ", 8331692341),
    ("17.007", 17007),     # 2 nhóm cũng hợp lệ về hình dạng
])
def test_parse_money_reads_printed_forms(chuoi, mong):
    assert so_hoc.parse_money(chuoi) == mong


@pytest.mark.parametrize("chuoi", [
    "8.812.478.00O",       # chữ O thay số 0 — đúng lỗi VLM/OCR hay mắc
    "19078257365",         # không có dấu phân cách: KHÔNG chấp nhận, vì mất tự kiểm nhóm-3
    "1.500.00",            # nhóm cuối 2 chữ số
    "12.3456.789",
    "",
    "abc",
    "(19.078.257.265",     # ngoặc lệch
])
def test_parse_money_rejects_malformed_as_bad(chuoi):
    assert so_hoc.parse_money(chuoi) is BAD


def test_parse_money_accepts_int_passthrough_for_answer_keys():
    # Đáp án đã lưu số nguyên; đường đó không đi qua chuỗi.
    assert so_hoc.parse_money(69862687223) == 69862687223
    assert so_hoc.parse_money(-2920489798) == -2920489798


# --- (e1) công thức in sẵn trong nhãn --------------------------------------

@pytest.mark.parametrize("nhan,tong,thanh_phan", [
    ("TỔNG CỘNG TÀI SẢN (50=01+05+10+20+25+30+40+45)", "50",
     [("01", 1), ("05", 1), ("10", 1), ("20", 1), ("25", 1), ("30", 1), ("40", 1), ("45", 1)]),
    ("TỔNG CỘNG NGUỒN VỐN (80=60+70)", "80", [("60", 1), ("70", 1)]),
    ("Thặng dư / thâm hụt (09=01-05)", "09", [("01", 1), ("05", -1)]),
    ("Thặng dư/thâm hụt trong năm (50=09+12+22+32-40)", "50",
     [("09", 1), ("12", 1), ("22", 1), ("32", 1), ("40", -1)]),
    ("Doanh thu (01=02+03+04)", "01", [("02", 1), ("03", 1), ("04", 1)]),
    # Khoảng trắng quanh dấu bằng và dấu cộng — mẫu TT 99 in kiểu này
    ("TỔNG CỘNG TÀI SẢN (280 = 100 + 200)", "280", [("100", 1), ("200", 1)]),
    # Hậu tố chữ (411a, 411b) phải giữ nguyên
    ("Vốn góp (411=411a+411b)", "411", [("411a", 1), ("411b", 1)]),
])
def test_printed_formula_is_parsed_from_the_label(nhan, tong, thanh_phan):
    c = so_hoc.parse_printed_formula(nhan)
    assert c is not None
    assert c.total == tong
    assert list(c.terms) == thanh_phan
    assert c.source == "in_san"


@pytest.mark.parametrize("nhan", [
    "Các khoản phải thu",
    "Phải thu khách hàng",
    "TỔNG CỘNG TÀI SẢN",                 # không có công thức
    "Tiền (xem thuyết minh III.1)",     # ngoặc nhưng không phải công thức
    "(50)",                             # chỉ một số
    "(50=)",                            # vế phải rỗng
])
def test_labels_without_a_formula_yield_none(nhan):
    assert so_hoc.parse_printed_formula(nhan) is None


def test_formula_with_nested_parens_keeps_sign_through_the_group():
    # Mẫu TT 200 B01 dòng 30: "30 = 20 + (21-22) + 24 - (25+26)" — dấu trừ trước
    # ngoặc phải đổi dấu MỌI hạng tử bên trong.
    c = so_hoc.parse_printed_formula("Lợi nhuận (30 = 20 + (21-22) + 24 - (25+26))")
    assert c is not None
    assert c.total == "30"
    assert list(c.terms) == [("20", 1), ("21", 1), ("22", -1), ("24", 1), ("25", -1), ("26", -1)]


# --- đánh giá ràng buộc -----------------------------------------------------

# Hàng thật của DVT tr7, cột "so_dau_nam" (đã cộng tay, 2026-09-11).
_TR7 = {
    "01": {"so_dau_nam": 40565652481},
    "05": {"so_dau_nam": "-"},
    "10": {"so_dau_nam": 8331692341},
    "11": {"so_dau_nam": 4773193000},
    "12": {"so_dau_nam": "-"},
    "13": {"so_dau_nam": "-"},
    "14": {"so_dau_nam": 3558499341},
    "20": {"so_dau_nam": 76383313},
    "25": {"so_dau_nam": "-"},
    "30": {"so_dau_nam": 17097932256},
    "40": {"so_dau_nam": 3555344000},
    "45": {"so_dau_nam": 235682832},
    "50": {"so_dau_nam": 69862687223},
    "TAI_SAN": {"so_dau_nam": None},      # hàng tiêu đề: ô null
}
_C50 = so_hoc.parse_printed_formula("TỔNG CỘNG TÀI SẢN (50=01+05+10+20+25+30+40+45)")
_C10 = Constraint("10", [("11", 1), ("12", 1), ("13", 1), ("14", 1)], "dap_an")


def test_real_page_7_total_passes_in_the_start_of_year_column():
    e = so_hoc.evaluate(_C50, _TR7.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.PASS
    assert e.total_value == 69862687223
    assert e.computed == 69862687223
    assert e.absent == ()


def test_one_wrong_digit_in_a_component_fails_with_the_delta():
    # 45 là thành phần TRỰC TIẾP của 50 (14 thì không — nó là con của 10; một
    # bản test đầu đã đột biến 14 và ngạc nhiên vì 50 vẫn PASS: bộ đánh giá đúng,
    # test sai. Ghi lại để không ai lặp).
    rows = dict(_TR7); rows["45"] = {"so_dau_nam": 235682833}   # +1
    e = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.FAIL
    assert e.delta == -1                       # ghi 69.862.687.223, tính ra ...224


def test_one_wrong_digit_in_the_total_fails():
    rows = dict(_TR7); rows["50"] = {"so_dau_nam": 69862687224}
    e = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.FAIL
    assert e.delta == 1


def test_dash_counts_as_zero_and_passes():
    # 10 = 11 + 12 + 13 + 14 với 12, 13 là "-"
    e = so_hoc.evaluate(_C10, _TR7.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.PASS


def test_a_null_cell_in_a_constraint_is_NA_not_zero():
    # Bẫy README ghi: hàng tiêu đề bị cộng thành 0 mà vẫn xanh. null -> NA, không -> 0.
    c = Constraint("50", [("TAI_SAN", 1), ("10", 1)], "dap_an")
    e = so_hoc.evaluate(c, _TR7.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.NA
    assert "null" in e.reason


def test_a_bad_cell_is_NA_not_zero():
    rows = dict(_TR7); rows["45"] = {"so_dau_nam": "235.682.83Z"}   # chữ Z
    e = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.NA
    assert "45" in e.reason


def test_absent_total_row_is_NA():
    rows = dict(_TR7); del rows["50"]
    e = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=False)
    assert e.verdict is so_hoc.Verdict.NA


def test_absent_component_is_NA_in_strict_mode_but_zero_and_COUNTED_in_lenient_mode():
    # Đáp án: mọi hàng phải có mặt -> vắng là lỗi.
    # Trang VLM: trang có thể bỏ hàng "-" -> vắng = 0 NHƯNG phải được đếm, không im lặng.
    rows = dict(_TR7); del rows["05"]; del rows["25"]        # hai hàng "-" bị bỏ
    strict = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=True)
    assert strict.verdict is so_hoc.Verdict.NA
    lenient = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=False)
    assert lenient.verdict is so_hoc.Verdict.PASS
    assert lenient.absent == ("05", "25")


def test_absent_NONZERO_component_fails_in_lenient_mode():
    # Bỏ một hàng có giá trị thật -> tổng không còn khớp -> FAIL, không phải PASS-với-vắng.
    rows = dict(_TR7); del rows["45"]                        # 235.682.832 bị rơi
    e = so_hoc.evaluate(_C50, rows.get, "so_dau_nam", strict_absent=False)
    assert e.verdict is so_hoc.Verdict.FAIL
    assert e.absent == ("45",)
    assert e.delta == 235682832


def test_signed_formula_evaluates_with_negative_coefficients():
    # DVT tr9: 50 = 09 + 12 + 22 + 32 - 40, cột nam_nay
    rows = {"09": {"v": "-"}, "12": {"v": 6619053565}, "22": {"v": 392605794},
            "32": {"v": -2853754923}, "40": {"v": 7078394234}, "50": {"v": -2920489798}}
    c = so_hoc.parse_printed_formula("Thặng dư/thâm hụt trong năm (50=09+12+22+32-40)")
    e = so_hoc.evaluate(c, rows.get, "v", strict_absent=True)
    assert e.verdict is so_hoc.Verdict.PASS
