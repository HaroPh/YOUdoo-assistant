"""Cong A cua bac 2 -- TU NUOI, da dinh dang.

Co che: lay trang bang VECTOR (pdfplumber boc duoc) -> rasterise -> OCR ->
dung grid bang bac 2 -> so voi grid pdfplumber boc tu CHINH trang do. Dap an
tu sinh, khong go tay o nao.

Vi sao can cong nay ben canh cong scan that: cong kia chi co MOT tai lieu, mot
dinh dang. Cong nay phu phu luc luat, bieu thue, bieu mau BCTC, bieu mau SSC
va hoa don.

GIOI HAN noi thang, hai lop:
- Anh rasterise SACH HON scan doi thuc -- giong het gioi han cua cong tu nuoi
  bac 1. Cong nay chung minh "con song va dai khai dung tren nhieu dinh
  dang", KHONG chung minh "chiu duoc scan doi thuc".
- **Tap 6 trang nay KHONG PHU tai lieu tieng Anh THUAN.** Da tim khap kho
  (tmp-docs + src/rag/seed/law + D:/Documents +
  backend/tests/rag/fixtures/*.pdf): tai lieu tieng Anh THUAN duy nhat tim
  duoc, `USA_Employee_Handbook-Freely_Available.pdf`, co CA 34/34 trang ma
  pdfplumber `find_tables()` bao "co bang" deu la DUONG TINH GIA (van ban
  doan van hoac muc luc bi nham thanh bang -- da kiem tay noi dung tung
  trang; vi du tr.5: `[None, 'x.', None, 'Screen and interview candidates.',
  None, None, ...]`, 17 cot rong). `BOM.pdf` va SOP fixture trong
  `backend/tests/rag/fixtures/` khong co trang nao pdfplumber thay bang tren
  CA HAI tep (114 + 9 trang, quet het). Khong con ung vien nao khac. Dinh
  dang thu 6 trong PAGES vi vay dung BANG THU HAI (khoi tong hop VAT)
  tren CHINH trang hoa don da dung o dinh dang thu 5 -- van la NOI DUNG tieng
  Anh that (hoa don nay 100% tieng Anh), nhung cung MOT nguon tep voi dinh
  dang thu 5, khong phai mot tai lieu tieng Anh doc lap. NGUOI SAU MUON PHU
  tai lieu tieng Anh doc lap phai bo sung tep moi vao kho, khong the lay tu
  tap hien co (xem task-3-report.md, phan "Dinh dang thu 6").

THUOC DIEM: dung `src.ocr.table_score.score` -- MOT BAN DUY NHAT dung chung
voi `backend/tools/calibrate_table.py`. Truoc 2026-09-07 moi ben giu mot ban
chep tay va hai ban DA LECH nhau (ban o day xu ly o xuong dong, ban hieu chinh
thi khong), nghia la bang so do chot GAP_FACTOR/SUPPORT_RATIO duoc sinh boi
THUOC KHAC thuoc dang gac (phat hien I6 cua review toan nhanh). Dung chep lai
vao day.

KHONG dung ham `_match_ratio` (so tap tu theo dung chi so hang/cot) ma brief
goc de xuat. Ly do: `_match_ratio` chi do MOT ve -- "moi token cua mot o dap
an nam trong CUNG MOT o grid" -- va mot grid MOT COT (moi hang = mot o) an
diem tuyet doi MIEN PHI vi khong co "chi so cot" nao de sai. Da do duoc tren
`luat-thuexuatnhapkhau.pdf` tr.14: gap_factor=1000 (khong khe nao du lon de
thanh bounds gioi, MOI bang suy bien ve MOT COT) van dat 0,9706 tren thuoc do
dung chi so. `score` doi xung: ve 1 KHONG TACH NHAM + ve 2 KHONG GOP NHAM,
diem trang = min(hai ve) nen ca hai huong suy bien deu bi phat -- xem THU PHA
o cuoi tep.

O XUONG DONG: o dap an co `"\n"` bi loai khoi CA HAI ve va dem rieng thanh
`wrapped` (spec Sec 10 ghi ro no NGOAI PHAM VI bac 2). Loai khoi CA HAI, khong
chi ve `kept` -- xem docstring `table_score.score` va chu thich tren
MATCH_THRESHOLD cho so do cua lo hong cu (phat hien I1).
"""
import os

import pdfplumber
import pytest

from src.ocr import table, table_score
from src.ocr.document import _anh_cua_trang
from src.ocr.engine import ocr_image, tesseract_path

DPI = 200

# NGUONG DO LAI 2026-09-07 LAN THU HAI, sau khi loai o `wrapped` khoi CA HAI
# ve cua thuoc (phat hien I1 cua review toan nhanh -- xem docstring
# `table_score.score`). 6 diem MOI (thay tron bang truoc do):
#   phu luc luat     luat-dautu.pdf tr42            : kept=8/8=1.0000   tach=4/4=1.0000   min=1.0000 unread=28 wrapped=2
#   bieu thue        luat-thuexuatnhapkhau.pdf tr17  : kept=34/35=0.9714 tach=22/22=1.0000 min=0.9714 unread=16 wrapped=0
#   bieu mau BCTC    bieumau_bctc_hopnhat.pdf tr3    : kept=56/78=0.7179 tach=35/41=0.8537 min=0.7179 unread=6  wrapped=0
#   bieu mau SSC     ssc_bieumau.pdf tr4             : kept=6/7=0.8571  tach=2/3=0.6667   min=0.6667 unread=9  wrapped=9
#   hoa don (dong)   invoice_51109301.pdf tr1 idx0   : kept=26/26=1.0000 tach=69/72=0.9583 min=0.9583 unread=0  wrapped=2
#   hoa don (VAT)    invoice_51109301.pdf tr1 idx1   : kept=10/11=0.9091 tach=14/15=0.9333 min=0.9091 unread=0  wrapped=1
#
# min quan sat = 0,6667 (bieu mau SSC tr4). MATCH_THRESHOLD = lam tron xuong
# 2 chu so cua (0,6667 - 0,05) = lam tron xuong cua 0,6167 = 0,61.
#
# VI SAO SSC TUT 0,8571 -> 0,6667: 9 o cua trang do la o XUONG DONG. Ban truoc
# loai chung khoi ve `kept` nhung VAN cho chung tham gia ve `tach`, va o ve do
# chung an tin dung MIEN PHI -- mot o khong bao gio nam tron trong mot o luoi
# thi cung khong bao gio "roi chung mot o" voi o khac, nen MOI cap co no tinh
# la tach dung. Hau qua do duoc: ca SSC tr4 o cau hinh THU PHA `gap_factor=1000`
# (luoi MOT cot) van dat min=0,8333 -- tren nguong 0,66, tuc XANH MIEN PHI o
# dung cau hinh suy bien ma phep thu pha sinh ra de bat. Phep thu pha cu chi
# doi `min(diem_suy_bien) < min(diem_mac_dinh)` nen khong keu.
#
# 6 DIEM O CAU HINH THU PHA (gap_factor=1000, luoi MOT cot), sau khi sua --
# TUNG ca phai duoi nguong, va deu duoi:
#   phu luc luat 0,0000 | bieu thue 0,5000 | bieu mau BCTC 0,1463
#   bieu mau SSC 0,0000 | hoa don (dong) 0,0000 | hoa don (VAT) 0,0000
MATCH_THRESHOLD = 0.61

# Tap trang, moi dong la MOT DINH DANG khac nhau (tru dong cuoi -- xem "GIOI
# HAN noi thang" o dau tep ve ly do dinh dang thu 6 phai thay the bang mot
# bang khac tren CHINH tep hoa don, khong phu tai lieu tieng Anh doc lap).
# `bang_idx` chon bang thu may tren trang (pdfplumber co the thay nhieu
# bang/trang); mac dinh 0.
#
# Duong dan tmp-docs la TUYET DOI: `tmp-docs/` khong nam trong worktree nay
# (thu muc gitignore, chi ton tai o cay chinh D:\Youdoo) -- duong dan tuong
# doi se khong tim thay tep (xem canh bao trong task).
_TMP_DOCS = "D:/Youdoo/tmp-docs"

PAGES = [
    ("src/rag/seed/law/luat-dautu.pdf", 42, 0,
     "phu luc luat (danh muc nganh nghe/hoa chat)"),
    ("src/rag/seed/law/luat-thuexuatnhapkhau.pdf", 17, 0,
     "bieu thue xuat nhap khau"),
    (f"{_TMP_DOCS}/bieumau_bctc_hopnhat.pdf", 3, 0,
     "bieu mau BCTC"),
    (f"{_TMP_DOCS}/ssc_bieumau.pdf", 4, 0,
     "bieu mau SSC"),
    (f"{_TMP_DOCS}/invoice_51109301.pdf", 1, 0,
     "hoa don (dong mat hang)"),
    (f"{_TMP_DOCS}/invoice_51109301.pdf", 1, 1,
     "hoa don (khoi tong hop VAT -- KHONG phu tai lieu tieng Anh doc lap, "
     "xem 'GIOI HAN noi thang' o dau tep)"),
]


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.parametrize("tep,trang,bang_idx,dinh_dang", PAGES)
def test_grid_from_image_matches_vector_grid(tep, trang, bang_idx, dinh_dang):
    if not os.path.isfile(tep):
        pytest.skip(f"khong co {tep}")
    with pdfplumber.open(tep) as pdf:
        bangs = pdf.pages[trang - 1].find_tables()
        assert bangs, f"{tep} tr{trang}: pdfplumber khong thay bang -> chon lai trang"
        assert len(bangs) > bang_idx, (
            f"{tep} tr{trang}: chi co {len(bangs)} bang, khong co idx {bang_idx}")
        answer = bangs[bang_idx].extract()
        bbox = bangs[bang_idx].bbox

    kq = ocr_image(_anh_cua_trang(tep, trang, DPI))
    ws = table_score.words_in_bbox(kq.words, bbox, DPI / 72)
    assert ws, "khong tu nao nam trong khung bang -> bbox hoac ty le sai"

    grid = table.build_grid(ws)
    kept, keep_total, tach, split_total, bo, wrapped = table_score.score(
        answer, grid, kq.text)
    if split_total == 0:
        pytest.skip(
            f"{dinh_dang}: khong co hang dap an nao >=2 o doc duoc -- "
            "khong noi duoc gi ve viec tach nham (xem quy uoc bo qua trong "
            "task-3-report.md)")
    ty_giu = kept / keep_total if keep_total else 0.0
    ty_tach = tach / split_total
    diem = min(ty_giu, ty_tach)
    # Dong in nay GIU NGUYEN vinh vien -- co ich moi lan cong do (xem cac
    # cong tu nuoi khac trong repo cung theo quy uoc nay). unreadable va
    # wrapped la HAI DU KIEN VE TAI LIEU (chat luong tang doc / mat do o
    # nhieu dong), khong phai rac -- in ca hai de nguoi doc thay ngay khi
    # mot dinh dang bi phat vi ly do gi.
    print(f"\n{dinh_dang} :: {os.path.basename(tep)} tr{trang} idx{bang_idx}: "
          f"kept={kept}/{keep_total}={ty_giu:.4f} tach={tach}/{split_total}={ty_tach:.4f} "
          f"min={diem:.4f} unreadable={bo} wrapped={wrapped}")
    assert MATCH_THRESHOLD is not None, (
        "MATCH_THRESHOLD chua duoc chot -- xem task-3-report.md truoc khi dat "
        "lai gia tri nay")
    assert diem >= MATCH_THRESHOLD, (
        f"{dinh_dang} :: {os.path.basename(tep)} tr{trang}: {diem:.4f} "
        f"< nguong {MATCH_THRESHOLD}")


def test_break_check_huge_gap_factor_turns_gate_red():
    """THU PHA bat buoc (spec quy trinh cong tu nuoi): ep GAP_FACTOR=1000.0 --
    khong khe nao du lon de thanh bounds gioi cot, MOI bang suy bien ve MOT
    COT. Neu cong van XANH o cau hinh nay thi thuoc khong do gi -- xem
    task-3-report.md phan "THU PHA" cho output day du cua ca hai luot.

    SIET 2026-09-07 (phat hien I1): truoc do test nay chi doi
    `min(diem_suy_bien) < min(diem_mac_dinh)` -- mot phep so TONG THE, nen mot
    ca van co the XANH o cau hinh suy bien mien la mot ca KHAC do hon no. Do
    duoc: `ssc_bieumau.pdf` tr4 dat min=0,8333 >= nguong 0,66 voi
    `gap_factor=1000` (luoi MOT cot) va cong khong keu. Nay khang dinh TUNG ca
    phai DUOI nguong o cau hinh suy bien -- 6/6 do.
    """
    if tesseract_path() is None:
        pytest.skip("chua cai tesseract")
    boi_khe_goc = table.GAP_FACTOR
    try:
        diem_mac_dinh = []
        diem_suy_bien = []
        ten_ca = []
        for tep, trang, bang_idx, dinh_dang in PAGES:
            if not os.path.isfile(tep):
                continue
            with pdfplumber.open(tep) as pdf:
                bangs = pdf.pages[trang - 1].find_tables()
                if not bangs or len(bangs) <= bang_idx:
                    continue
                answer = bangs[bang_idx].extract()
                bbox = bangs[bang_idx].bbox
            kq = ocr_image(_anh_cua_trang(tep, trang, DPI))
            ws = table_score.words_in_bbox(kq.words, bbox, DPI / 72)
            if not ws:
                continue

            table.GAP_FACTOR = boi_khe_goc
            luoi_mac_dinh = table.build_grid(ws)
            g, gm, t, tm, _, _ = table_score.score(answer, luoi_mac_dinh, kq.text)
            if tm == 0:
                continue
            diem_mac_dinh.append(min(g / gm if gm else 0.0, t / tm))
            ten_ca.append(dinh_dang[:24])

            table.GAP_FACTOR = 1000.0
            luoi_suy_bien = table.build_grid(ws)
            g2, gm2, t2, tm2, _, _ = table_score.score(answer, luoi_suy_bien, kq.text)
            if tm2 == 0:
                # Suy bien mot cot -> khong con hang nao co 2 o KHAC NHAU
                # cung roi mot o grid de dem tach (moi hang gio la 1 o) --
                # day CHINH LA dau hieu suy bien, dem la 0/0 (roi vao nhanh
                # nay) thay vi mot diem so.
                diem_suy_bien.append(0.0)
            else:
                diem_suy_bien.append(min(g2 / gm2 if gm2 else 0.0, t2 / tm2))
        print(f"\n(THU PHA) diem mac dinh (gap_factor={boi_khe_goc}): "
              f"{[round(d, 4) for d in diem_mac_dinh]}")
        print(f"(THU PHA) diem suy bien (gap_factor=1000.0): "
              f"{[round(d, 4) for d in diem_suy_bien]}")
        assert diem_mac_dinh, "khong co trang nao du dieu kien de thu pha"
        assert min(diem_suy_bien) < min(diem_mac_dinh), (
            "cong khong phan biet duoc cau hinh suy bien voi cau hinh mac "
            "dinh -- thuoc khong do gi, DUNG LAI va bao cao")
        do_ac = [(t, d) for t, d in zip(ten_ca, diem_suy_bien)
                 if d >= MATCH_THRESHOLD]
        assert not do_ac, (
            f"cau hinh SUY BIEN van tren nguong {MATCH_THRESHOLD} o cac ca: "
            f"{do_ac} -- nhung ca do dang XANH MIEN PHI, thuoc khong do gi o "
            "do, DUNG LAI va bao cao")
    finally:
        table.GAP_FACTOR = boi_khe_goc
