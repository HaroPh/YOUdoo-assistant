"""(e2) bất biến cấu trúc, gộp ràng buộc, trạng thái hàng, và Q5 break-test.

Q5 của spec: mỗi bẫy README đã trả giá phải làm cổng ĐỎ ĐÚNG CHỖ — đúng hàng,
đúng lý do — chứ không chỉ "đỏ ở đâu đó". Dữ liệu là DVT tr7 (B01 TT 107) đọc
lại từ đáp án, số đổi sang chuỗi in trên giấy ("750.005.854", "(58.099.826.029)")
để đi đúng đường VLM sẽ đi: chuỗi nguyên văn -> parse_money -> đánh giá.

Điểm mù ghi thành test: đảo cột MỌI hàng thì số học vẫn QUA — kiểm x-toạ-độ
Tesseract (a) ở lát 2 là thứ duy nhất bắt được; test này tồn tại để ai sửa
bộ kiểm sau không tưởng số học bắt được nó.
"""
import copy
import glob
import json
import os

import pytest

from src.ocr import so_hoc
from src.ocr.so_hoc import Constraint, RowStatus, Verdict

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")


def _in(v):
    """Số nguyên -> chuỗi in trên giấy; "-"/None giữ nguyên."""
    if not isinstance(v, int):
        return v
    s = f"{abs(v):,}".replace(",", ".")
    return f"({s})" if v < 0 else s


def _load(name):
    d = json.load(open(os.path.join(_THU_MUC, name), encoding="utf-8"))
    cols = [c for c in d["cot"] if c not in _COT_NHAN]
    rows = [{**h, **{c: _in(h[c]) for c in cols}} for h in d["hang"]]
    return rows, cols, d


def _constraints(rows, *, hierarchy=True):
    e1 = [c for c in (so_hoc.parse_printed_formula(h.get("chi_tieu") or "") for h in rows) if c]
    b = so_hoc.derive_hierarchy(rows) if hierarchy else []
    cs, _ = so_hoc.merge_constraints(e1, b)
    return cs


def _tr7():
    rows, cols, _ = _load("DVT_2022_tr7.json")
    return rows, cols


def _by(rows, ma):
    return next(r for r in rows if r.get("ma_so") == ma)


def _status(rep, ma):
    return next(r for r in rep.rows if r.ma_so == ma)


# --- (e2) check_structure ------------------------------------------------------

class TestCheckStructure:
    def test_clean_page_has_no_issues(self):
        rows, cols = _tr7()
        assert so_hoc.check_structure(rows, cols) == []

    def test_garbage_money_cell_is_bad_money_on_that_row(self):
        rows, cols = _tr7()
        _by(rows, "11")["so_cuoi_nam"] = "8.812.478.00O"          # chữ O thay 0
        [i] = so_hoc.check_structure(rows, cols)
        assert (i.kind, i.ma_so) == ("bad_money", "11")

    def test_missing_value_column_is_width(self):
        rows, cols = _tr7()
        del _by(rows, "14")["so_dau_nam"]
        [i] = so_hoc.check_structure(rows, cols)
        assert (i.kind, i.ma_so) == ("width", "14")

    def test_duplicate_ma_so_flags_second_occurrence_only(self):
        rows, cols = _tr7()
        rows.insert(8, copy.deepcopy(_by(rows, "14")))            # lặp ngay sau hàng 14
        kinds = [(i.kind, i.ma_so, i.index) for i in so_hoc.check_structure(rows, cols)]
        assert ("dup_ma_so", "14", 8) in kinds

    def test_decreasing_ma_so_is_non_monotonic(self):
        rows, cols = _tr7()
        _by(rows, "14")["ma_so"] = "18"                            # 13 -> 18 kiểu đọc sai
        # 18 sau 13: tăng — KHÔNG bắt được ở đây (mù có tên); nhưng 20 sau 18 vẫn tăng.
        assert so_hoc.check_structure(rows, cols) == []
        _by(rows, "20")["ma_so"] = "09"                            # nhỏ hơn 18
        kinds = [(i.kind, i.ma_so) for i in so_hoc.check_structure(rows, cols)]
        assert ("non_monotonic", "09") in kinds

    def test_suffix_letters_sort_after_the_bare_code(self):
        assert so_hoc.ma_so_key("411") < so_hoc.ma_so_key("411a") < so_hoc.ma_so_key("411b") < so_hoc.ma_so_key("412")
        assert so_hoc.ma_so_key("abc") is None
        assert so_hoc.ma_so_key(None) is None

    def test_null_cells_on_header_rows_are_not_bad_money(self):
        rows = [{"muc": None, "chi_tieu": "TAI SAN", "ma_so": None, "a": None},
                {"muc": "I.", "chi_tieu": "Tien", "ma_so": "01", "a": "1.000"}]
        assert so_hoc.check_structure(rows, ["a"]) == []

    def test_every_approved_key_passes_structure_gate(self):
        for p in sorted(glob.glob(os.path.join(_THU_MUC, "*.json"))):
            rows, cols, _ = _load(os.path.basename(p))
            assert so_hoc.check_structure(rows, cols) == [], os.path.basename(p)


# --- merge_constraints ---------------------------------------------------------

class TestMergeConstraints:
    def test_printed_formula_beats_hierarchy_for_same_total(self):
        e1 = [Constraint("50", [("01", 1), ("05", 1)], "in_san")]
        b = [Constraint("50", [("01", 1), ("40", 1)], "phan_cap")]
        cs, conflicts = so_hoc.merge_constraints(b, e1)                # thứ tự truyền không quan trọng
        assert [c.source for c in cs] == ["in_san"]
        assert conflicts == [(e1[0], b[0])]

    def test_same_terms_different_order_is_not_a_conflict(self):
        e1 = [Constraint("10", [("11", 1), ("14", 1)], "in_san")]
        b = [Constraint("10", [("14", 1), ("11", 1)], "phan_cap")]
        cs, conflicts = so_hoc.merge_constraints(e1, b)
        assert len(cs) == 1 and conflicts == []

    def test_distinct_totals_all_kept(self):
        cs, _ = so_hoc.merge_constraints(
            [Constraint("10", [("11", 1)], "in_san")],
            [Constraint("30", [("31", 1)], "phan_cap")])
        assert {c.total for c in cs} == {"10", "30"}


# --- classify_rows: đường xanh ---------------------------------------------------

class TestClassifyClean:
    def test_tr7_every_numeric_row_is_verified_and_none_rejected(self):
        rows, cols = _tr7()
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        assert rep.count(RowStatus.REJECTED) == 0
        assert not rep.capped_unverified
        num = [r for r in rep.rows if r.numeric]
        assert len(num) == 12
        assert all(r.status == RowStatus.VERIFIED for r in num)
        # Hàng "-" là unverified theo spec, hàng tiêu đề TAI SAN là label.
        assert _status(rep, "05").status == RowStatus.UNVERIFIED
        assert rep.rows[0].status == RowStatus.LABEL
        assert "xác minh 12/12 hàng có số" in rep.summary
        assert "toàn gạch ngang 7" in rep.summary

    def test_all_approved_keys_reject_nothing_and_fail_nothing(self):
        """Đáp án là chân lý: bộ phân loại không được loại một hàng đúng nào."""
        for p in sorted(glob.glob(os.path.join(_THU_MUC, "*.json"))):
            rows, cols, d = _load(os.path.basename(p))
            cs = _constraints(rows, hierarchy="can_doi" in d["nhom"])
            rep = so_hoc.classify_rows(rows, cs, cols, strict_absent=True)
            assert rep.count(RowStatus.REJECTED) == 0, os.path.basename(p)
            assert all(e.verdict != Verdict.FAIL for e in rep.evaluations), os.path.basename(p)

    def test_b01_keys_verify_every_numeric_row(self):
        """Độ phủ hàng trên B01 với (e1)+(b): 100% hàng có số. Sàn cứng — (c)
        vào không được làm giảm."""
        # Ngoại lệ có tên: tổng lớn tham chiếu hàng ở TRANG TRƯỚC. Đồng nhất
        # xuyên trang là lượt cấp tài liệu (lát 5), không phải lỗi bộ kiểm.
        xuyen_trang = {"SCID_2026H1_tr13.json": ["280"],      # 280 = 100 + 200, 100 ở tr12
                       "SCID_2026H1_tr15.json": ["440"]}      # 440 = 300 + 400, 300 ở tr14
        for p in sorted(glob.glob(os.path.join(_THU_MUC, "*.json"))):
            rows, cols, d = _load(os.path.basename(p))
            if "can_doi" not in d["nhom"]:
                continue
            rep = so_hoc.classify_rows(rows, _constraints(rows), cols, strict_absent=True)
            num = [r for r in rep.rows if r.numeric]
            chua = [r.ma_so for r in num if r.status != RowStatus.VERIFIED]
            assert chua == xuyen_trang.get(os.path.basename(p), []), f"{os.path.basename(p)}: {chua}"

    def test_no_constraints_means_everything_unverified_not_rejected(self):
        rows, cols = _tr7()
        rep = so_hoc.classify_rows(rows, [], cols)
        assert rep.count(RowStatus.VERIFIED) == 0
        assert rep.count(RowStatus.REJECTED) == 0
        assert "xác minh 0/12" in rep.summary


# --- Q5 break-test: đỏ ĐÚNG CHỖ ------------------------------------------------

class TestBreak:
    def test_one_digit_changed_in_a_component_rejects_the_whole_cluster_naming_the_formula(self):
        rows, cols = _tr7()
        _by(rows, "11")["so_cuoi_nam"] = "8.812.478.001"          # +1 đồng
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        s11 = _status(rep, "11")
        assert s11.status == RowStatus.REJECTED
        assert "10 = 11 +12 +13 +14" in s11.reason and "lệch -1" in s11.reason and "so_cuoi_nam" in s11.reason
        # Cả cụm của 10 đi: 12, 13, 14 và tổng 10.
        for ma in ("10", "12", "13", "14"):
            assert _status(rep, ma).status == RowStatus.REJECTED, ma
        # Ô của 10 KHÔNG đổi nên 50 = 01 + 05 + 10 + ... vẫn PASS: cụm 50 đứng
        # yên. Chính xác hơn tôi kỳ vọng lúc viết test (đã ghi 01 bị loại — sai).
        assert _status(rep, "01").status == RowStatus.VERIFIED
        assert _status(rep, "50").status == RowStatus.VERIFIED
        assert _status(rep, "32").status == RowStatus.VERIFIED
        assert rep.count(RowStatus.REJECTED) == 5

    def test_total_changed_rejects_total_and_all_components(self):
        rows, cols = _tr7()
        _by(rows, "31")["so_dau_nam"] = "17.097.932.257"
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        for ma in ("31", "32", "33"):
            assert _status(rep, ma).status == RowStatus.REJECTED, ma
        # 31 là thành phần của 30 = 31 + 35 → 30 cũng lệch → 30, 35 đi theo.
        assert _status(rep, "30").status == RowStatus.REJECTED

    def test_dropping_a_nonzero_component_row_is_NA_naming_the_absent_code(self):
        """Lệch + có hàng vắng → NA, không FAIL: không phân biệt được "rơi hàng"
        với "hàng ở trang trước" (280 = 100 + 200 trên SCID tr13). Kết quả: 11/12/13
        mất phủ → unverified; 10 vẫn verified qua 50 = ... + 10 + ... vì ô của nó
        đúng. Không hàng nào bị xác minh sai."""
        rows, cols = _tr7()
        cs = _constraints(rows)                  # tham chiếu cố định, như (c)/(e1)
        rows = [r for r in rows if r.get("ma_so") != "14"]
        rep = so_hoc.classify_rows(rows, cs, cols, strict_absent=False)
        e = next(e for e in rep.evaluations if e.constraint.total == "10" and e.column == "so_cuoi_nam")
        assert e.verdict == Verdict.NA and e.absent == ("14",) and "vắng ['14']" in e.reason
        assert _status(rep, "11").status == RowStatus.UNVERIFIED
        assert _status(rep, "10").status == RowStatus.VERIFIED
        assert rep.count(RowStatus.REJECTED) == 0

    def test_cross_page_grand_total_stays_unverified_not_rejected(self):
        """SCID tr13: 280 = 100 + 200, 100 ở tr12. Bảng (c) TT 99 tham chiếu cố định
        → 100 vắng → NA. 280 unverified (có tag), 200 vẫn verified qua 200 = 210 + ..."""
        rows, cols, _ = _load("SCID_2026H1_tr13.json")
        ft = so_hoc.form_table("99/2025/TT-BTC", "B01-DN")
        rep = so_hoc.classify_rows(rows, ft.constraints, cols, strict_absent=False)
        assert rep.count(RowStatus.REJECTED) == 0
        assert _status(rep, "280").status == RowStatus.UNVERIFIED
        assert _status(rep, "200").status == RowStatus.VERIFIED

    def test_dropping_a_dash_row_still_passes_and_counts_it_absent(self):
        rows, cols = _tr7()
        cs = _constraints(rows)
        rows = [r for r in rows if r.get("ma_so") != "12"]
        rep = so_hoc.classify_rows(rows, cs, cols, strict_absent=False)
        e = next(e for e in rep.evaluations if e.constraint.total == "10" and e.column == "so_cuoi_nam")
        assert e.verdict == Verdict.PASS and e.absent == ("12",)
        assert _status(rep, "11").status == RowStatus.VERIFIED

    def test_hierarchy_derived_from_the_mutilated_page_is_blind_to_the_dropped_row(self):
        """Điểm mù có tên của (b): suy từ hàng CÓ MẶT, nên hàng 14 rơi thì ràng
        buộc thành 10 = 11 + 12 + 13 → FAIL vì tổng lệch, nhưng `absent` rỗng —
        không ai biết là THIẾU hàng. Cụm vẫn bị loại (an toàn), chỉ mất lời giải
        thích. Chỉ (e1)/(c) mới báo được `absent`."""
        rows, cols = _tr7()
        rows = [r for r in rows if r.get("ma_so") != "14"]
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols, strict_absent=False)
        e = next(e for e in rep.evaluations if e.constraint.total == "10" and e.column == "so_cuoi_nam")
        assert e.verdict == Verdict.FAIL and e.absent == ()
        assert [m for m, _ in e.constraint.terms] == ["11", "12", "13"]
        assert _status(rep, "11").status == RowStatus.REJECTED

    def test_promoting_a_numbered_row_to_roman_breaks_the_enclosing_constraint(self):
        """Chỉ (b) canh SCID tr12 (không công thức in). "1." -> "I." trên 111:
        110 còn một con (112) → không sinh ràng buộc nữa (luật >= 2 con); 111
        thành anh em của 110 dưới A-100 → 100 = 110 + 111 + 120 + ... lệch → cụm
        100 (gồm 110, 111) loại. 112 mồ côi → unverified, không phải loại."""
        rows, cols, _ = _load("SCID_2026H1_tr12.json")
        _by(rows, "111")["muc"] = "I."
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        assert _status(rep, "110").status == RowStatus.REJECTED
        assert _status(rep, "111").status == RowStatus.REJECTED
        assert _status(rep, "112").status == RowStatus.UNVERIFIED

    def test_swapping_columns_on_one_row_fails_both_columns(self):
        rows, cols = _tr7()
        r = _by(rows, "14")
        r["so_cuoi_nam"], r["so_dau_nam"] = r["so_dau_nam"], r["so_cuoi_nam"]
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        fails = {(e.constraint.total, e.column) for e in rep.evaluations if e.verdict == Verdict.FAIL}
        assert ("10", "so_cuoi_nam") in fails and ("10", "so_dau_nam") in fails
        assert _status(rep, "14").status == RowStatus.REJECTED

    def test_swapping_columns_on_every_row_PASSES_arithmetic_known_blind_spot(self):
        """Điểm mù có tên: số học không biết cột nào là "cuối năm". Lát 2 dùng
        x-toạ-độ token Tesseract để bắt; test này ghi rằng đây KHÔNG phải việc của
        số học, để không ai kỳ vọng nhầm."""
        rows, cols = _tr7()
        for r in rows:
            r["so_cuoi_nam"], r["so_dau_nam"] = r["so_dau_nam"], r["so_cuoi_nam"]
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        assert rep.count(RowStatus.REJECTED) == 0
        assert all(e.verdict == Verdict.PASS for e in rep.evaluations)

    def test_garbage_cell_rejects_row_and_makes_its_constraints_na_not_fail(self):
        rows, cols = _tr7()
        _by(rows, "11")["so_cuoi_nam"] = "8.812.478.00O"
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols, strict_absent=True)
        s11 = _status(rep, "11")
        assert s11.status == RowStatus.REJECTED and s11.reason.startswith("bad_money")
        # Hàng loại rời khỏi lookup → 10 = 11 + ... thiếu 11 → NA (strict), không FAIL:
        # không được kết luận sai về 12/13/14 từ một ô rác.
        e = next(e for e in rep.evaluations if e.constraint.total == "10" and e.column == "so_cuoi_nam")
        assert e.verdict == Verdict.NA
        assert _status(rep, "14").status == RowStatus.UNVERIFIED         # cột cuối năm mất phủ

    def test_duplicate_ma_so_rejects_the_duplicate_and_keeps_the_original(self):
        """Hàng lặp bị loại RIÊNG; hàng gốc vẫn verified và trang KHÔNG bị trần
        `non_monotonic` (14 sau 14 không phải "không đơn điệu", là lặp)."""
        rows, cols = _tr7()
        dup = copy.deepcopy(_by(rows, "14"))
        dup["so_cuoi_nam"] = "1"
        rows.insert(8, dup)
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        st = [r for r in rep.rows if r.ma_so == "14"]
        assert [r.status for r in st] == [RowStatus.VERIFIED, RowStatus.REJECTED]
        assert not rep.capped_unverified

    def test_non_monotonic_page_caps_everything_at_unverified(self):
        rows, cols = _tr7()
        _by(rows, "20")["ma_so"] = "09"          # số học vẫn qua (50 tham chiếu 20 → NA thôi)
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols)
        assert rep.capped_unverified
        assert rep.count(RowStatus.VERIFIED) == 0
        assert "KHÔNG đơn điệu" in rep.summary and rep.capped_reason
        assert _status(rep, "32").status == RowStatus.UNVERIFIED         # 31 = 32 + 33 PASS mà vẫn trần

    def test_missing_column_on_a_row_rejects_only_that_row(self):
        rows, cols = _tr7()
        del _by(rows, "45")["so_dau_nam"]
        rep = so_hoc.classify_rows(rows, _constraints(rows), cols, strict_absent=True)
        assert _status(rep, "45").status == RowStatus.REJECTED
        assert _status(rep, "45").reason.startswith("width")


# --- hợp đồng VLM -> hàng + cổng trang -------------------------------------------------

class TestRowsFromVision:
    _P = {"trang": {"mau": "B01/BCTC", "thong_tu": "107/2017/TT-BTC",
                    "cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
          "hang": [{"muc": None, "nhan": "TÀI SẢN", "ma_so": None, "thuyet_minh": None, "so_tien": []},
                   {"muc": "I.", "nhan": "Tiền", "ma_so": "01", "thuyet_minh": "III.1",
                    "so_tien": ["750.005.854", "40.565.652.481"]},
                   {"muc": "II.", "nhan": "Đầu tư tài chính ngắn hạn", "ma_so": "05",
                    "thuyet_minh": None, "so_tien": ["-", "-"]}]}

    def test_maps_so_tien_onto_declared_columns_verbatim(self):
        rows, cols, issues = so_hoc.rows_from_vision(copy.deepcopy(self._P))
        assert cols == ["Số cuối năm", "Số đầu năm"] and issues == []
        assert rows[1]["chi_tieu"] == "Tiền" and rows[1]["Số cuối năm"] == "750.005.854"
        assert rows[2]["Số đầu năm"] == "-"
        assert rows[0]["ma_so"] is None and "Số cuối năm" not in rows[0]

    def test_header_row_without_cells_is_label_not_width_rejected(self):
        rows, cols, issues = so_hoc.rows_from_vision(copy.deepcopy(self._P))
        rep = so_hoc.classify_rows(rows, [], cols, extra_issues=issues)
        assert rep.rows[0].status == RowStatus.LABEL
        assert rep.count(RowStatus.REJECTED) == 0

    def test_too_many_cells_is_a_width_issue_that_rejects_the_row(self):
        p = copy.deepcopy(self._P)
        p["hang"][1]["so_tien"].append("1")
        rows, cols, issues = so_hoc.rows_from_vision(p)
        assert [(i.kind, i.ma_so) for i in issues] == [("width", "01")]
        rep = so_hoc.classify_rows(rows, [], cols, extra_issues=issues)
        assert _status(rep, "01").status == RowStatus.REJECTED

    def test_missing_or_bad_columns_declaration_is_a_page_error(self):
        for bad in ({"trang": {}, "hang": []}, {"trang": {"cot_gia_tri": []}, "hang": []},
                    {"trang": {"cot_gia_tri": ["a", "a"]}, "hang": []},
                    {"trang": {"cot_gia_tri": ["a"]}, "hang": {}}):
            with pytest.raises(ValueError):
                so_hoc.rows_from_vision(bad)

    def test_fewer_than_two_coded_rows_caps_the_page(self):
        rows, cols, issues = so_hoc.rows_from_vision(copy.deepcopy(self._P))
        rows = rows[:2]                                          # chỉ còn 01
        rep = so_hoc.classify_rows(rows, [], cols, extra_issues=issues)
        assert rep.capped_unverified and "ít hơn 2" in rep.capped_reason
        assert _status(rep, "01").status == RowStatus.UNVERIFIED
