"""Cong A cua bac 2 -- TU NUOI, da dinh dang.

Co che: lay trang bang VECTOR (pdfplumber boc duoc) -> rasterise -> OCR ->
dung luoi bang bac 2 -> so voi luoi pdfplumber boc tu CHINH trang do. Dap an
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
  dang thu 6 trong TAP_TRANG vi vay dung BANG THU HAI (khoi tong hop VAT)
  tren CHINH trang hoa don da dung o dinh dang thu 5 -- van la NOI DUNG tieng
  Anh that (hoa don nay 100% tieng Anh), nhung cung MOT nguon tep voi dinh
  dang thu 5, khong phai mot tai lieu tieng Anh doc lap. NGUOI SAU MUON PHU
  tai lieu tieng Anh doc lap phai bo sung tep moi vao kho, khong the lay tu
  tap hien co (xem task-3-report.md, phan "Dinh dang thu 6").

THUOC DIEM: dung dung ham `_diem` chep tu `backend/tools/hieu_chinh_bang.py`
(giu nguyen ngu nghia CHINH, co MOT sua bo sung -- xem doan "SUA O XUONG
DONG" duoi day), KHONG dung ham `_ty_le_khop` (so tap tu theo dung chi so
hang/cot) ma brief goc de xuat. Ly do: `_ty_le_khop` chi do MOT ve -- "moi
token cua mot o dap an nam trong CUNG MOT o luoi" -- va mot luoi MOT COT (moi
hang = mot o) an diem tuyet doi MIEN PHI vi khong co "chi so cot" nao de sai.
Da do duoc tren `luat-thuexuatnhapkhau.pdf` tr.14: boi_khe=1000 (khong khe
nao du lon de thanh ranh gioi, MOI bang suy bien ve MOT COT) van dat 0,9706
tren thuoc do dung chi so -- thuoc khong phan biet duoc "dung cot" voi
"khong dung cot nao ca". `_diem` doi xung: ve 1 KHONG TACH NHAM (giu nguyen
tinh than tren) + ve 2 KHONG GOP NHAM (hai o KHAC NHAU trong cung mot hang dap
an khong duoc roi chung mot o luoi). Diem trang = min(giu/giu_ms, tach/tach_ms)
nen ca hai huong suy bien deu bi phat -- xem THU PHA o cuoi tep va trong
task-3-report.md.

SUA O XUONG DONG (them so voi `hieu_chinh_bang.py` goc): o dap an co `"\\n"`
(vat qua nhieu dong vat ly) bi LOAI khoi ve "giu" va dem rieng thanh
`xuong_dong` -- xem docstring `_diem` de biet ly do day du (spec Sec 10 ghi
ro o xuong dong NGOAI PHAM VI bac 2). Do duoc: `ssc_bieumau.pdf` tr.4 di tu
0,3750 len 0,8333 khi ap dung sua nay, trong khi ba dinh dang KHONG co o
xuong dong (`bieumau_bctc_hopnhat` tr.3, `luat-dautu` tr.42,
`luat-thuexuatnhapkhau` tr.17) KHONG DOI mot chut nao -- xac nhan day la sua
mot gioi han da tuyen bo ngoai pham vi, khong phai noi long thuoc do chung
chung de "cong xanh". Chi tiet lich su (diem CU 0,3750 la loi thuoc do khi
chua co sua nay, khong phai loi chon trang) xem task-3-report.md.
"""
import os

import pdfplumber
import pytest

from src.ocr import bang
from src.ocr.document import _anh_cua_trang
from src.ocr.engine import ocr_image, tesseract_path

DPI = 200

# NGUONG DO LAI 2026-09-07 (chay `-s`, SAU KHI doi `tim_ranh_cot` sang mep-
# canh-khe VA doi tham so BOI_KHE=3.0/TY_LE_UNG_HO=0.3 -- xem `bang.py` cho ly
# do doi tham so, chu yeu la vi corpus scan that can ty_le=0.3 de khong sap ve
# mot cot). 6 diem MOI (thay tron 6 diem CU do voi BOI_KHE=2.0/TY_LE=0.6):
#   phu luc luat     luat-dautu.pdf tr42            : giu=8/8=1.0000   tach=7/7=1.0000   min=1.0000  xuong_dong=2
#   bieu thue        luat-thuexuatnhapkhau.pdf tr17  : giu=34/35=0.9714 tach=22/22=1.0000 min=0.9714  xuong_dong=0
#   bieu mau BCTC    bieumau_bctc_hopnhat.pdf tr3    : giu=56/78=0.7179 tach=35/41=0.8537 min=0.7179  xuong_dong=0
#   bieu mau SSC     ssc_bieumau.pdf tr4             : giu=6/7=0.8571  tach=17/18=0.9444 min=0.8571  xuong_dong=9
#   hoa don (dong)   invoice_51109301.pdf tr1 idx0   : giu=26/26=1.0000 tach=81/84=0.9643 min=0.9643 xuong_dong=2
#   hoa don (VAT)    invoice_51109301.pdf tr1 idx1   : giu=10/11=0.9091 tach=17/18=0.9444 min=0.9091 xuong_dong=1
#
# min quan sat = 0,7179 (bieu mau BCTC tr3 -- doi vi tri so voi ban do CU, noi
# min la luat-dautu tr42 o 0,7143; ban nay luat-dautu tr42 len han 1,0000 vi
# mep-canh-khe tach dung ca 7/7 cap o thay vi 5/7). Tat ca 6 diem deu > 0,5 ->
# KHONG DONE_WITH_CONCERNS. NGUONG_KHOP = lam tron xuong 2 chu so cua
# (0,7179 - 0,05) = lam tron xuong cua 0,6679 = 0,66 -- TRUNG SO CU (0,66) mot
# cach TINH CO, khong phai gia tri giu nguyen tu truoc: phai tinh lai tu 6
# diem moi, khong duoc gia dinh gia tri cu con dung.
NGUONG_KHOP = 0.66

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

TAP_TRANG = [
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


def _tu_trong_bbox(words, bbox, ty_le):
    """Chi giu tu nam trong khung bang. `bbox` theo DIEM (pdfplumber), toa do
    tu theo PIXEL anh -- nhan `ty_le` = DPI/72 de ve cung he."""
    x0, top, x1, bot = (v * ty_le for v in bbox)
    return [w for w in words
            if x0 <= w.left and w.left + w.width <= x1
            and top <= w.top and w.top + w.height <= bot]


def _tk(o) -> list[str]:
    """Token du dai de tim trong text phang ma khong khop bua."""
    return [t for t in (o or "").split() if len(t) >= 3]


def _diem(dap_an, luoi, tho):
    """(giu, giu_mau_so, tach, tach_mau_so, bo_doc_hong, xuong_dong).

    DOI XUNG, va do la diem mau chot:
      ve 1 KHONG TACH NHAM -- moi token cua mot o dap an nam trong CUNG MOT o
      luoi;
      ve 2 KHONG GOP NHAM  -- hai o KHAC NHAU trong cung mot hang dap an
      KHONG duoc roi chung mot o luoi.

    Chi co ve 1 thi mot luoi MOT COT dat diem tuyet doi MIEN PHI -- do duoc:
    boi_khe=1000 van cho 0,9706. Chi co ve 2 thi tach vun tung tu lai thang.
    Diem cuoi lay min(ve 1, ve 2) nen ca hai huong suy bien deu bi phat.

    O nao tang doc khong doc duoc thi loai khoi CA HAI mau so va dem rieng --
    cham no la cham chat luong OCR, khong phai viec cua bac 2 (spec Sec 2.4).

    O XUONG DONG: spec Sec 10 ghi ro no NGOAI PHAM VI bac 2 -- bac 2 gom
    hang theo `line_id` nen token cua mot o vat qua nhieu dong vat ly nam o
    cac HANG luoi khac nhau, khong bao gio thoa "cung mot o", ke ca khi cot
    tach hoan toan dung. Cham no la cham thu bac 2 khong nhan lam. Vi vay o
    XUONG DONG bi LOAI KHOI ve "giu" (khong tinh vao giu_ms) va dem RIENG
    thanh `xuong_dong` -- dem rieng chu khong im lang bo, dung tinh than voi
    `bo_doc_hong`. O nay VAN THAM GIA binh thuong o ve "tach": viec tach cot
    cua no van kiem duoc du no khong tham gia duoc ve "giu".
    Do duoc: `ssc_bieumau.pdf` tr.4 di tu 0,3750 len 0,8333 khi loai lop o
    nay, trong khi ba dinh dang khong co o xuong dong (`bieumau_bctc_hopnhat`
    tr.3, `luat-dautu` tr.42, `luat-thuexuatnhapkhau` tr.17) KHONG DOI mot
    chut nao -- xac nhan day la sua mot gioi han da tuyen bo ngoai pham vi,
    khong phai noi long thuoc do chung chung.
    """
    ph = tho.replace("\n", " ")
    giu = giu_ms = tach = tach_ms = bo = xuong_dong = 0
    for hang in dap_an:
        doc_duoc = []
        for o in hang:
            t = _tk(o)
            if not t:
                continue
            if not all(x in ph for x in t):
                bo += 1
                continue
            doc_duoc.append((o, t))
        for o, t in doc_duoc:
            if "\n" in (o or ""):
                xuong_dong += 1
                continue
            giu_ms += 1
            if any(all(x in c for x in t) for h in luoi for c in h):
                giu += 1
        for i in range(len(doc_duoc)):
            for j in range(i + 1, len(doc_duoc)):
                tach_ms += 1
                chung = any(all(x in c for x in doc_duoc[i][1])
                            and all(y in c for y in doc_duoc[j][1])
                            for h in luoi for c in h)
                if not chung:
                    tach += 1
    return giu, giu_ms, tach, tach_ms, bo, xuong_dong


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.parametrize("tep,trang,bang_idx,dinh_dang", TAP_TRANG)
def test_dung_lai_bang_tu_anh_khop_luoi_vector(tep, trang, bang_idx, dinh_dang):
    if not os.path.isfile(tep):
        pytest.skip(f"khong co {tep}")
    with pdfplumber.open(tep) as pdf:
        bangs = pdf.pages[trang - 1].find_tables()
        assert bangs, f"{tep} tr{trang}: pdfplumber khong thay bang -> chon lai trang"
        assert len(bangs) > bang_idx, (
            f"{tep} tr{trang}: chi co {len(bangs)} bang, khong co idx {bang_idx}")
        dap_an = bangs[bang_idx].extract()
        bbox = bangs[bang_idx].bbox

    kq = ocr_image(_anh_cua_trang(tep, trang, DPI))
    ws = _tu_trong_bbox(kq.words, bbox, DPI / 72)
    assert ws, "khong tu nao nam trong khung bang -> bbox hoac ty le sai"

    luoi = bang.dung_luoi(ws)
    giu, giu_ms, tach, tach_ms, bo, xuong_dong = _diem(dap_an, luoi, kq.text)
    if tach_ms == 0:
        pytest.skip(
            f"{dinh_dang}: khong co hang dap an nao >=2 o doc duoc -- "
            "khong noi duoc gi ve viec tach nham (xem quy uoc bo qua trong "
            "task-3-report.md)")
    ty_giu = giu / giu_ms if giu_ms else 0.0
    ty_tach = tach / tach_ms
    diem = min(ty_giu, ty_tach)
    # Dong in nay GIU NGUYEN vinh vien -- co ich moi lan cong do (xem cac
    # cong tu nuoi khac trong repo cung theo quy uoc nay). bo_doc_hong va
    # xuong_dong la HAI DU KIEN VE TAI LIEU (chat luong tang doc / mat do o
    # nhieu dong), khong phai rac -- in ca hai de nguoi doc thay ngay khi
    # mot dinh dang bi phat vi ly do gi.
    print(f"\n{dinh_dang} :: {os.path.basename(tep)} tr{trang} idx{bang_idx}: "
          f"giu={giu}/{giu_ms}={ty_giu:.4f} tach={tach}/{tach_ms}={ty_tach:.4f} "
          f"min={diem:.4f} bo_doc_hong={bo} xuong_dong={xuong_dong}")
    assert NGUONG_KHOP is not None, (
        "NGUONG_KHOP chua duoc chot -- xem task-3-report.md truoc khi dat "
        "lai gia tri nay")
    assert diem >= NGUONG_KHOP, (
        f"{dinh_dang} :: {os.path.basename(tep)} tr{trang}: {diem:.4f} "
        f"< nguong {NGUONG_KHOP}")


def test_thu_pha_boi_khe_cuc_lon_lam_cong_do():
    """THU PHA bat buoc (spec quy trinh cong tu nuoi): ep BOI_KHE=1000.0 --
    khong khe nao du lon de thanh ranh gioi cot, MOI bang suy bien ve MOT
    COT. Neu cong van XANH o cau hinh nay thi thuoc khong do gi -- xem
    task-3-report.md phan "THU PHA" cho output day du cua ca hai luot.

    Test nay KHONG phu thuoc NGUONG_KHOP (van chay duoc du NGUONG_KHOP=None)
    vi no tu tinh nguong tam thoi = min cua cac diem đo duoc o cau hinh mac
    dinh (tu bang chu thich tren NGUONG_KHOP) tru 0,05 -- chi de chung minh
    diem SUY BIEN THAP HON diem mac dinh o CUNG trang, khong doi hoi biet
    nguong cuoi cung.
    """
    if tesseract_path() is None:
        pytest.skip("chua cai tesseract")
    boi_khe_goc = bang.BOI_KHE
    try:
        diem_mac_dinh = []
        diem_suy_bien = []
        for tep, trang, bang_idx, dinh_dang in TAP_TRANG:
            if not os.path.isfile(tep):
                continue
            with pdfplumber.open(tep) as pdf:
                bangs = pdf.pages[trang - 1].find_tables()
                if not bangs or len(bangs) <= bang_idx:
                    continue
                dap_an = bangs[bang_idx].extract()
                bbox = bangs[bang_idx].bbox
            kq = ocr_image(_anh_cua_trang(tep, trang, DPI))
            ws = _tu_trong_bbox(kq.words, bbox, DPI / 72)
            if not ws:
                continue

            bang.BOI_KHE = boi_khe_goc
            luoi_mac_dinh = bang.dung_luoi(ws)
            g, gm, t, tm, _, _ = _diem(dap_an, luoi_mac_dinh, kq.text)
            if tm == 0:
                continue
            diem_mac_dinh.append(min(g / gm if gm else 0.0, t / tm))

            bang.BOI_KHE = 1000.0
            luoi_suy_bien = bang.dung_luoi(ws)
            g2, gm2, t2, tm2, _, _ = _diem(dap_an, luoi_suy_bien, kq.text)
            if tm2 == 0:
                # Suy bien mot cot -> khong con hang nao co 2 o KHAC NHAU
                # cung roi mot o luoi de dem tach (moi hang gio la 1 o) --
                # day CHINH LA dau hieu suy bien, dem la 0/0 (roi vao nhanh
                # nay) thay vi mot diem so.
                diem_suy_bien.append(0.0)
            else:
                diem_suy_bien.append(min(g2 / gm2 if gm2 else 0.0, t2 / tm2))
        print(f"\n(THU PHA) diem mac dinh (boi_khe={boi_khe_goc}): "
              f"{[round(d, 4) for d in diem_mac_dinh]}")
        print(f"(THU PHA) diem suy bien (boi_khe=1000.0): "
              f"{[round(d, 4) for d in diem_suy_bien]}")
        assert diem_mac_dinh, "khong co trang nao du dieu kien de thu pha"
        assert min(diem_suy_bien) < min(diem_mac_dinh), (
            "cong khong phan biet duoc cau hinh suy bien voi cau hinh mac "
            "dinh -- thuoc khong do gi, DUNG LAI va bao cao")
    finally:
        bang.BOI_KHE = boi_khe_goc
