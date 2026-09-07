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
# TUYET DOI theo `__file__`, va danh sach dap an duoc KHANG DINH khac rong o
# `_answer_files()`. Truoc 2026-09-07 day la duong dan TUONG DOI va duoc glob
# LUC COLLECT: chay pytest tu thu muc khac -> 0 test, khong skip, khong do,
# cong bien mat trong im lang (phat hien I7 cua review toan nhanh).
ANSWERS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "fixtures", "ocr_bang_that"))

# Ky tu cat o HAI DAU token truoc khi so bang. Chi dau cau NOI DUOI cua
# tesseract ('123.' thay vi '123'), KHONG cat ngoac -- ngoac la NGU NGHIA
# trong bao cao tai chinh Viet Nam (so am viet la '(2.774.400)').
TOKEN_TRIM = ".,;:"

# NGUONG DO LAI 2026-09-07 SAU KHI SUA THUOC (phat hien C2 cua review toan
# nhanh -- nguong cu 0.71 phai coi la KHONG CO CAN CU vi 13/15 lan do truot
# sinh ra no la AO). Chay voi SAME_ROW_THRESHOLD=0.0 tam thoi, 7 trang SCID
# tr12..18:
#   SCID_2026H1_tr12.json: intact=17/17=1.0000 unreadable=2
#   SCID_2026H1_tr13.json: intact=21/21=1.0000 unreadable=1
#   SCID_2026H1_tr14.json: intact=11/11=1.0000 unreadable=3
#   SCID_2026H1_tr15.json: intact=5/6=0.8333   unreadable=2
#   SCID_2026H1_tr16.json: intact=19/19=1.0000 unreadable=1
#   SCID_2026H1_tr17.json: intact=15/15=1.0000 unreadable=4
#   SCID_2026H1_tr18.json: intact=5/5=1.0000   unreadable=0
# Tong: 93/94 = 0.9894, 13/107 hang du dieu kien bi loai vi tang doc doc hong.
# Thap nhat = 5/6 = 0.8333 (tr15). SAME_ROW_THRESHOLD = lam tron xuong 2 chu
# so cua (0.8333 - 0.05) = lam tron xuong cua 0.7833 = 0.78.
#
# LAN TRUOT DUY NHAT CON LAI (tr15 ma_so=411) KHONG phai loi bac 2: luoi ra
#   ['1.', '', 'Von gop cua chu so huu', '411', 'V2I 1.000.000.000.000',
#    '1,000.000.000.000 . \\']
# -- hai cot tien DA o hai o KHAC NHAU, nhung tang doc doc o thu hai thanh
# '1,000.000.000.000' (dau PHAY). Bo loc "doc hong" khong bat duoc vi no hoi
# ca TRANG chu khong hoi rieng hang do, ma dung chuoi '1.000.000.000.000' co
# that o hang 411a ngay duoi. Do la GIOI HAN CON LAI cua bo loc, ghi ra chu
# khong che.
SAME_ROW_THRESHOLD = 0.78


def _vn(n: int) -> str:
    """So nguyen -> chuoi kieu Viet: -2428531621 -> '(2.428.531.621)'."""
    s = f"{abs(n):,}".replace(",", ".")
    return f"({s})" if n < 0 else s


def _tokens(text: str) -> list[str]:
    """Chuoi -> token so BANG duoc.

    SO BANG, KHONG so chuoi con -- day la phat hien C2 cua review toan nhanh
    va la ly do 13/15 lan cong nay bao do truoc 2026-09-07 la AO: `'160' in
    '15.618.160.768'` va `'05' in '(38.320.042.505)'` deu DUNG, nen mot hang
    bi cham truot du luoi hoan toan chinh xac.
    """
    return [t.strip(TOKEN_TRIM) for t in text.split() if t.strip(TOKEN_TRIM)]


def _has_distinct_cells(candidates: list[list[int]]) -> bool:
    """Ton tai HE DAI DIEN PHAN BIET: moi gia tri mot o KHAC NHAU (Kuhn).

    Khong dung `len(set(...)) == len(values)` tren mot dict khoa boi GIA TRI:
    bang can doi thuong xuyen co hai cot tien BANG NHAU (vd ma_so=136 tr12,
    '(15.635.803.061)' o ca so cuoi ky lan so dau nam). Dict lam hai lan xuat
    hien do gop thanh MOT khoa nen dieu kien khong bao gio thoa, va hang do
    bi cham truot du luoi TACH DUNG hai o -- artefact thu hai cua thuoc cu,
    tim ra khi tai lap C2. He dai dien phan biet xu ly dung ca truong hop
    trung gia tri.
    """
    assign: dict[int, int] = {}

    def _augment(i: int, seen: set[int]) -> bool:
        for cell in candidates[i]:
            if cell in seen:
                continue
            seen.add(cell)
            if cell not in assign or _augment(assign[cell], seen):
                assign[cell] = i
                return True
        return False

    for i in range(len(candidates)):
        if not _augment(i, set()):
            return False
    return True


def _row_is_intact(values: list[str], grid: list[list[str]],
                   ma_so: str | None) -> bool:
    """Moi gia tri cung MOT hang luoi VA moi gia tri o mot O KHAC NHAU.

    Ve thu hai la thu do viec TACH COT. Thieu no thi cong khong do gi: mot
    thuoc chi hoi "cac gia tri co cung hang khong" cho 0,969 o CA
    GAP_FACTOR=3.0 lan GAP_FACTOR=1000 (do 2026-09-07), vi noi ca hang thanh
    mot chuoi thi luoi 1 cot va luoi 5 cot giong het nhau.

    RANG BUOC THU BA (them 2026-09-07 theo review toan nhanh): o chua `ma_so`
    khong duoc chua GI KHAC ngoai chinh `ma_so`. Truoc do cong chi doi ba gia
    tri o ba o KHAC NHAU, nen cot `Ma so` gop TRAI vao o `Chi tieu` van "dat".
    Do duoc: rang buoc nay hien KHONG loai them hang nao (93/93 hang dat cung
    dat rang buoc moi) -- no chua co rang, nhung deterministic va chi co the
    lam diem GIAM, nen giu de lan sau cot gop trai thi cong keu.
    """
    for row in grid:
        cells = [_tokens(c) for c in row]
        candidates = [[i for i, c in enumerate(cells) if v in c] for v in values]
        if not all(candidates) or not _has_distinct_cells(candidates):
            continue
        if ma_so is not None:
            # `values[0]` la `ma_so` (xem `_row_values`). O nao cung duoc,
            # mien la co MOT o chi chua dung no.
            if not any(cells[i] == [ma_so] for i in candidates[0]):
                continue
        return True
    return False


def _answer_files() -> list[str]:
    files = sorted(glob.glob(os.path.join(ANSWERS_DIR, "SCID_2026H1_tr*.json")))
    assert files, (
        f"khong dap an nao trong {ANSWERS_DIR} -- cong nay se sinh ZERO test "
        "ma khong keu; DUNG LAI thay vi de no bien mat trong im lang")
    return files


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
        values.append(ma_so.strip(TOKEN_TRIM))
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
    # SO BANG token, khong `in` chuoi phang: bo loc "doc hong" cu hong CUNG
    # LY DO voi `_row_is_intact` cu -- `'01'` la chuoi con cua vo so so dai
    # khac tren trang, nen mot hang tang doc doc HONG van duoc coi la doc
    # duoc va di thang vao mau so (phat hien C2).
    flat_tokens = set(_tokens(page_read.text))
    grid = table.build_grid(_words_from_page(page_read))

    intact = total = unreadable = 0
    for row in d["hang"]:
        values = _row_values(row, value_cols)
        if len(values) < 2:
            continue
        if any(v not in flat_tokens for v in values):
            unreadable += 1
            continue
        total += 1
        ma_so = row.get("ma_so")
        ma_so = ma_so.strip(TOKEN_TRIM) if isinstance(ma_so, str) and ma_so else None
        if _row_is_intact(values, grid, ma_so):
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
