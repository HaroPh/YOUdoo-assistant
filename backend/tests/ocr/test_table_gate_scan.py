"""Cong B cua bac 2 -- SCAN THAT.

Cong A (`test_table_gate_vector.py`) chay tren anh rasterise tu PDF SO --
sach hon scan doi thuc. Cong nay chay tren ban scan that DUY NHAT dang co
(BCTC hop nhat ban nien SCID, 150 DPI, 0 ky tu lop text), doi chieu voi dap
an DA DUYET trong `backend/tests/fixtures/ocr_bang_that/`.

KHONG dat ten cot. Voi moi hang dap an, chi hoi: cac gia tri cua no co roi
vao CUNG MOT hang cua luoi bac 2 khong, VA moi gia tri co o mot O KHAC NHAU
trong hang do khong. Ve thu hai la thuoc do viec TACH COT -- thieu no thi
cong khong do gi: mot thuoc chi hoi ve thu nhat cho 0,969 o CA GAP_FACTOR=3.0
lan GAP_FACTOR=1000 (do 2026-09-07), vi noi ca hang thanh mot chuoi thi luoi
1 cot va luoi 5 cot giong het nhau.

HAI LOAI DO, phai phan biet duoc (spec Sec 2.4):
  (a) bac 2 dung sai cot   -> loi that cua cong nay
  (b) tang doc doc sai chu -> KHONG phai loi bac 2 (do duoc: Tesseract sai
      3/14 cot Ma so hai chu so tren trang 17). Khong phan biet thi cong do
      oan vai lan roi bi tat, ma cong bi tat thi bang khong.
Cach phan biet: chi tinh hang ma MOI gia tri cua no xuat hien dau do trong
`PageRead.text` (text phang ca trang). Hang nao tang doc doc hong thi loai
khoi mau so va DEM RA, khong am tham bo qua.

Chi xet hang co >=2 gia tri sau khi gop `ma_so` (mot gia tri thi khong noi
duoc gi ve viec "cung hang").
"""
import glob
import json
import os

import pytest

from src.ocr import table
from src.ocr.document import read_page
from src.ocr.engine import OcrWord, tesseract_path

PDF_PATH = ("D:/downloads/SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat"
            "_SoatXet_2026_signed_05092026111802.pdf")
ANSWERS_DIR = "tests/fixtures/ocr_bang_that"

# NGUONG DO THAT 2026-09-07 (chay `-s` tren venv, SAME_ROW_THRESHOLD=0.0 tam
# thoi, 7 trang SCID tr12..18 -- KHONG nhan so nguoi giao viec bao truoc, tu
# do lai het):
#   SCID_2026H1_tr12.json: intact=15/17=0.8824 unreadable=2
#   SCID_2026H1_tr13.json: intact=18/21=0.8571 unreadable=1
#   SCID_2026H1_tr14.json: intact=12/12=1.0000 unreadable=2
#   SCID_2026H1_tr15.json: intact=5/6=0.8333   unreadable=2
#   SCID_2026H1_tr16.json: intact=16/20=0.8000 unreadable=0
#   SCID_2026H1_tr17.json: intact=13/17=0.7647 unreadable=2
#   SCID_2026H1_tr18.json: intact=4/5=0.8000   unreadable=0
# Ca 7 ty le KHOP CHINH XAC voi 7 con so nguoi giao viec da neu truoc
# (15/17, 18/21, 12/12, 5/6, 16/20, 13/17, 4/5) -- khong lech con nao. Tong
# hang bi loai vi tang doc doc hong (dem rieng, KHONG tinh vao mau so):
# 2+1+2+2+0+2+0 = 9/107 hang du dieu kien.
# Thap nhat = 13/17 = 0.7647 (tr17). SAME_ROW_THRESHOLD = lam tron xuong 2
# chu so cua (0.7647 - 0.05) = lam tron xuong cua 0.7147 = 0.71.
SAME_ROW_THRESHOLD = 0.71


def _vn(n: int) -> str:
    """So nguyen -> chuoi kieu Viet: -2428531621 -> '(2.428.531.621)'."""
    s = f"{abs(n):,}".replace(",", ".")
    return f"({s})" if n < 0 else s


def _row_is_intact(values: list[str], grid: list[list[str]]) -> bool:
    """Moi gia tri cung MOT hang luoi VA moi gia tri o mot O KHAC NHAU.

    Ve thu hai la thu do viec TACH COT. Thieu no thi cong khong do gi: mot
    thuoc chi hoi "cac gia tri co cung hang khong" cho 0,969 o CA
    GAP_FACTOR=3.0 lan GAP_FACTOR=1000 (do 2026-09-07), vi noi ca hang thanh
    mot chuoi thi luoi 1 cot va luoi 5 cot giong het nhau.
    """
    for row in grid:
        cell_of = {}
        for v in values:
            hits = [i for i, c in enumerate(row) if v in c]
            if len(hits) != 1:
                break
            cell_of[v] = hits[0]
        else:
            if len(set(cell_of.values())) == len(values):
                return True
    return False


def _answer_files() -> list[str]:
    return sorted(glob.glob(os.path.join(ANSWERS_DIR, "SCID_2026H1_tr*.json")))


def _words_from_page(page_read) -> list[OcrWord]:
    return [OcrWord(text=w["t"], conf=w["c"], left=w["l"], top=w["y"],
                     width=w["w"], height=w["h"], line_id=tuple(w["g"]))
            for region in page_read.regions for w in region.words]


def _row_values(row: dict, value_cols: list[str]) -> list[str]:
    """`ma_so` (neu co) cong cac gia tri SO cua hang, doi sang chuoi kieu Viet.

    Cot gia tri SUY TU `d["cot"]`, khong gan chet ten: bang can doi dung
    `so_cuoi_ky`/`so_dau_nam`, luu chuyen tien te dung `nam_nay`/`nam_truoc`.
    """
    values = []
    ma_so = row.get("ma_so")
    if isinstance(ma_so, str) and ma_so:
        values.append(ma_so)
    values += [_vn(row[c]) for c in value_cols if isinstance(row.get(c), int)]
    return values


def _score_page(answer_path: str) -> tuple[int, int, int]:
    """Tra ve (intact, total, unreadable) cho MOT trang dap an, o GAP_FACTOR
    va SUPPORT_RATIO HIEN HANH cua `table` (de test THU PHA doi duoc tham so
    truoc khi goi ham nay)."""
    d = json.load(open(answer_path, encoding="utf-8"))
    assert d["trang_thai"] == "DA_DUYET", f"{answer_path} chua duoc duyet"
    value_cols = [c for c in d["cot"]
                  if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")]

    page_read = read_page(PDF_PATH, d["trang_pdf"])
    flat_text = page_read.text
    grid = table.build_grid(_words_from_page(page_read))

    intact = total = unreadable = 0
    for row in d["hang"]:
        values = _row_values(row, value_cols)
        if len(values) < 2:
            continue
        if any(v not in flat_text for v in values):
            unreadable += 1
            continue
        total += 1
        if _row_is_intact(values, grid):
            intact += 1
    return intact, total, unreadable


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.skipif(not os.path.isfile(PDF_PATH), reason="khong co ban scan that")
@pytest.mark.parametrize("answer_path", _answer_files())
def test_grid_from_scan_keeps_answer_rows_intact(answer_path):
    intact, total, unreadable = _score_page(answer_path)
    assert total > 0, (
        f"{answer_path}: khong hang nao du dieu kien -> phep do nay khong do gi")
    ratio = intact / total
    # Dong in nay GIU NGUYEN vinh vien -- co ich moi lan cong do (dung quy
    # uoc voi cong A). `unreadable` la du kien VE TAI LIEU (tang doc doc
    # hong), khong phai rac -- in ra de nguoi doc thay ngay khi mot trang bi
    # phat vi ly do gi.
    print(f"\n{os.path.basename(answer_path)}: intact={intact}/{total}={ratio:.4f} "
          f"unreadable={unreadable}")
    assert SAME_ROW_THRESHOLD is not None, (
        "SAME_ROW_THRESHOLD chua duoc chot -- do lai truoc khi dat gia tri nay")
    assert ratio >= SAME_ROW_THRESHOLD, (
        f"{os.path.basename(answer_path)}: {ratio:.4f} < nguong {SAME_ROW_THRESHOLD}")


def test_break_check_huge_gap_factor_collapses_score_below_threshold():
    """THU PHA bat buoc (spec quy trinh cong tu nuoi): ep GAP_FACTOR=1000.0 --
    khong khe nao du lon de thanh bounds gioi cot, MOI bang suy bien ve MOT
    COT. Neu diem van o tren nguong o cau hinh nay thi thuoc khong do gi.
    """
    if tesseract_path() is None:
        pytest.skip("chua cai tesseract")
    if not os.path.isfile(PDF_PATH):
        pytest.skip("khong co ban scan that")
    original_gap_factor = table.GAP_FACTOR
    try:
        table.GAP_FACTOR = original_gap_factor
        default_intact = default_total = 0
        for answer_path in _answer_files():
            intact, total, _ = _score_page(answer_path)
            default_intact += intact
            default_total += total
        default_ratio = default_intact / default_total if default_total else 0.0

        table.GAP_FACTOR = 1000.0
        collapsed_intact = collapsed_total = 0
        for answer_path in _answer_files():
            intact, total, _ = _score_page(answer_path)
            collapsed_intact += intact
            collapsed_total += total
        collapsed_ratio = collapsed_intact / collapsed_total if collapsed_total else 0.0

        print(f"\n(THU PHA) diem mac dinh (GAP_FACTOR={original_gap_factor}): "
              f"{default_intact}/{default_total}={default_ratio:.4f}")
        print(f"(THU PHA) diem suy bien (GAP_FACTOR=1000.0): "
              f"{collapsed_intact}/{collapsed_total}={collapsed_ratio:.4f}")
        assert default_total > 0, "khong hang nao du dieu kien de thu pha"
        assert collapsed_ratio < SAME_ROW_THRESHOLD, (
            "cong khong phan biet duoc cau hinh suy bien voi cau hinh mac "
            "dinh -- thuoc khong do gi, DUNG LAI va bao cao")
    finally:
        table.GAP_FACTOR = original_gap_factor
