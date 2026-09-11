"""`grid_rows.rows_from_grid` (lưới Tesseract -> hàng) và `so_hoc.assess_page`
(chọn bảng bằng số học, gộp tầng, phân loại) + `tesseract_vouched`.

Lưới tổng hợp dựng từ đáp án DVT tr7 theo đúng hình dạng lưới bậc 2 đã quan
sát trên SCID tr12 (cột đánh dấu | nhãn tách 2 ô | mã số | thuyết minh | tiền |
ô trống | tiền), có letterhead phía trên và dấu "-" trôi sang cột kề — để không
phải chạy Tesseract trong CI. Số đo trên lưới Tesseract THẬT nằm ở
`tools/calibrate_vlm_trigger.py`, không ở đây.
"""
import glob
import json
import os

import pytest

from src.ocr import grid_rows, so_hoc
from src.ocr.so_hoc import RowStatus, Verdict

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")
_MAU = {"bang_can_doi": "B01-DN", "ket_qua_kd": "B02-DN", "luu_chuyen_tien": "B03-DN-GT"}


def _in(v):
    if not isinstance(v, int):
        return v
    s = f"{abs(v):,}".replace(",", ".")
    return f"({s})" if v < 0 else s


def _tr7_grid():
    d = json.load(open(os.path.join(_THU_MUC, "DVT_2022_tr7.json"), encoding="utf-8"))
    grid = [["", "TRUNG TÂM ĐÀO TẠO", "NGHIỆP VỤ", "", "", "", "", "Mẫu B01/BCTC"],
            ["", "Báo cáo tình hình tài chính", "", "", "", "(Ban hành theo", "TT số", "107/2017/TT-BTC"],
            ["", "", "", "", "", "", "", ""],
            ["STT", "Chỉ tiêu", "", "Mã số", "Thuyết minh", "Số cuối năm", "", "Số đầu năm"]]
    for i, h in enumerate(d["hang"]):
        nhan = h["chi_tieu"].split(" ", 1)
        v1, v2 = _in(h["so_cuoi_nam"]), _in(h["so_dau_nam"])
        # Dấu "-" trôi sang cột trống kề bên như trên SCID tr12 (cột 6 thay 5).
        row = [h["muc"] or "", nhan[0], nhan[1] if len(nhan) > 1 else "", h["ma_so"] or "",
               "", "" if v1 == "-" and i % 2 else (v1 or ""), v1 if v1 == "-" and i % 2 else "", v2 or ""]
        grid.append(row)
    grid.append(["", "Báo cáo này phải được đọc cùng", "Bản thuyết minh", "", "", "", "", "Trang 5"])
    return grid


class TestRowsFromGrid:
    def test_finds_ma_so_and_two_value_columns(self):
        gr = grid_rows.rows_from_grid(_tr7_grid())
        assert gr is not None
        assert gr.ma_so_col == 3 and gr.value_cols_idx == [5, 7]
        assert gr.coded_rows == 19
        assert gr.value_columns == ["c5", "c7"]

    def test_header_names_are_used_when_given(self):
        names = ["STT", "Chỉ tiêu", "", "Mã số", "Thuyết minh", "Số cuối năm", "", "Số đầu năm"]
        gr = grid_rows.rows_from_grid(_tr7_grid(), header_names=names)
        assert gr.value_columns == ["Số cuối năm", "Số đầu năm"]

    def test_rows_carry_verbatim_cells_and_drifted_dashes_land_in_nearest_column(self):
        gr = grid_rows.rows_from_grid(_tr7_grid())
        r10 = next(r for r in gr.rows if r["ma_so"] == "10")
        assert r10["chi_tieu"] == "Cac khoan phai thu" and r10["muc"] == "III."
        assert r10["c5"] == "19.078.257.265" and r10["c7"] == "8.331.692.341"
        r05 = next(r for r in gr.rows if r["ma_so"] == "05")
        assert r05["c5"] == "-" and r05["c7"] == "-"

    def test_letterhead_rows_have_no_ma_so_and_none_cells(self):
        gr = grid_rows.rows_from_grid(_tr7_grid())
        assert gr.rows[0]["ma_so"] is None and gr.rows[0]["c5"] is None

    def test_coded_row_without_money_cell_gets_empty_string_not_dash(self):
        g = _tr7_grid()
        row = next(r for r in g if r[3] == "14")
        row[5] = ""                                              # Tesseract mất số
        gr = grid_rows.rows_from_grid(g)
        r14 = next(r for r in gr.rows if r["ma_so"] == "14")
        assert r14["c5"] == "" and so_hoc.parse_money("") is so_hoc.BAD

    def test_page_without_a_code_column_returns_none(self):
        assert grid_rows.rows_from_grid([["Pap s", "", "25900585)"], ["F káananyee", "", "83316921)"]]) is None
        assert grid_rows.rows_from_grid([]) is None


class TestAssessPage:
    def test_tt107_page_selects_no_form_and_falls_back_to_hierarchy(self):
        gr = grid_rows.rows_from_grid(_tr7_grid())
        a = so_hoc.assess_page(gr.rows, gr.value_columns, strict_absent=False)
        assert a.form is None
        assert a.layers == {"in_san": 1, "bang_tt": 0, "phan_cap": 4}
        assert so_hoc.tesseract_vouched(a.report)
        num = [r for r in a.report.rows if r.numeric]
        assert all(r.status == RowStatus.VERIFIED for r in num) and len(num) == 12

    @pytest.mark.parametrize("p", sorted(glob.glob(os.path.join(_THU_MUC, "SCID*.json"))))
    def test_scid_keys_select_their_own_form_by_arithmetic(self, p):
        d = json.load(open(p, encoding="utf-8"))
        cols = [c for c in d["cot"] if c not in _COT_NHAN]
        a = so_hoc.assess_page(d["hang"], cols, strict_absent=True)
        assert a.form is not None, os.path.basename(p)
        if d["nhom"] == "luu_chuyen_tien" and "tr18" in p:
            # Trang 2 của B03 (31..36, 40, 50, 60, 61, 70) GIỐNG NHAU ở hai phương
            # pháp; số học không phân biệt được và không cần — hoà PASS/FAIL,
            # bảng ít NA hơn thắng. Chỉ đòi đúng HỌ mẫu.
            assert a.form.mau.startswith("B03-DN")
        else:
            assert a.form.mau == _MAU[d["nhom"]], os.path.basename(p)
        assert a.layers["phan_cap"] == 0                       # có bảng -> không dùng (b)
        assert not any(e.verdict == Verdict.FAIL for e in a.report.evaluations)

    def test_hierarchy_is_not_used_when_a_form_is_selected(self):
        """Ruling: (b) trên hàng Tesseract sinh ràng buộc sai vì đánh dấu STT đọc
        sai ("L", "2;") — có (c) thì (b) chỉ thêm rủi ro. Đo trên SCID tr13 lưới
        thật: 238 = 240 + 241 + 242 FAIL giả."""
        d = json.load(open(os.path.join(_THU_MUC, "SCID_2026H1_tr13.json"), encoding="utf-8"))
        cols = [c for c in d["cot"] if c not in _COT_NHAN]
        rows = [dict(h) for h in d["hang"]]
        for h in rows:                                           # phá mọi đánh dấu
            h["muc"] = "L" if h["muc"] else None
        a = so_hoc.assess_page(rows, cols, strict_absent=True)
        assert a.form.mau == "B01-DN" and a.layers["phan_cap"] == 0
        assert a.report.count(RowStatus.REJECTED) == 0

    def test_vouched_requires_a_pass_and_forbids_any_fail(self):
        gr = grid_rows.rows_from_grid(_tr7_grid())
        rows = gr.rows
        a = so_hoc.assess_page(rows, gr.value_columns, strict_absent=False)
        assert so_hoc.tesseract_vouched(a.report)
        r11 = next(r for r in rows if r["ma_so"] == "11")
        r11["c5"] = "8.812.478.001"
        a = so_hoc.assess_page(rows, gr.value_columns, strict_absent=False)
        assert not so_hoc.tesseract_vouched(a.report)
        assert not so_hoc.tesseract_vouched(so_hoc.classify_rows(rows, [], gr.value_columns))

    def test_select_form_returns_none_when_nothing_passes(self):
        rows = [{"muc": None, "chi_tieu": "x", "ma_so": "01", "a": "1"},
                {"muc": None, "chi_tieu": "y", "ma_so": "02", "a": "2"}]
        assert so_hoc.select_form(rows, ["a"], strict_absent=False) == (None, 0)
