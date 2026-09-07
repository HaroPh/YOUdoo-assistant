"""Cổng B của bậc 2 -- SCAN THẬT.

Cổng A chứng minh bậc 2 chạy trên nhiều định dạng, nhưng trên ảnh rasterise
SẠCH. Cổng này chạy trên bản scan đời thật duy nhất đang có (BCTC hợp nhất bán
niên SCID, 150 DPI, 0 ký tự lớp text), đối chiếu với đáp án ĐÃ DUYỆT.

KHÔNG cần đặt tên cột. Với mỗi hàng trong đáp án, chỉ hỏi: các giá trị của nó
có rơi vào CÙNG MỘT hàng đầu ra không. Dựng sai cột là gãy ngay, mà không phải
suy diễn cột nào là cột nào -- tránh được một tầng suy diễn có thể tự nó sai.

HAI LOẠI ĐỎ, phải phân biệt được:
  (a) bậc 2 dựng sai cột      -> LỖI CỦA TASK NÀY
  (b) tầng đọc đọc sai chữ    -> KHÔNG phải lỗi bậc 2 (spec §2.4: Tesseract sai
      3/14 cột Mã số hai chữ số). Nếu không phân biệt, cổng sẽ đỏ oan vài lần
      rồi có người tắt nó -- mà cổng bị tắt thì bằng không.
Cách phân biệt: chỉ tính những giá trị mà tầng đọc ĐỌC ĐƯỢC (xuất hiện đâu đó
trong text phẳng của trang). Giá trị tầng đọc đã đọc hỏng thì bỏ khỏi mẫu số và
ĐẾM RA, không âm thầm bỏ qua.
"""
import glob
import json
import os

import pytest

from src.ocr import bang
from src.ocr.document import read_page
from src.ocr.engine import OcrWord, tesseract_path

PDF = ("D:/downloads/SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat"
       "_SoatXet_2026_signed_05092026111802.pdf")
DAP_AN = "tests/fixtures/ocr_bang_that"

# NGƯỠNG ĐO ĐƯỢC -- chạy `-s` với NGUONG_CUNG_HANG=0.0 tạm thời, 7 dong in ra
# (mot tep dap an mot dong, thu tu tr12..tr18, cache OCR da co san tu cac
# task truoc nen luot nay chi mat 12,54s cho ca 7 trang):
#   SCID_2026H1_tr12.json: 19/19 = 1.0000  (0 hang bo qua)
#   SCID_2026H1_tr13.json: 22/22 = 1.0000  (0 hang bo qua)
#   SCID_2026H1_tr14.json: 12/12 = 1.0000  (2 hang bo qua vi TANG DOC doc hong)
#   SCID_2026H1_tr15.json: 7/7   = 1.0000  (0 hang bo qua)
#   SCID_2026H1_tr16.json: 20/20 = 1.0000  (0 hang bo qua)
#   SCID_2026H1_tr17.json: 16/16 = 1.0000  (2 hang bo qua vi TANG DOC doc hong)
#   SCID_2026H1_tr18.json: 5/5   = 1.0000  (0 hang bo qua)
# min = 1,0000 -- moi hang du dieu kien (>=2 gia tri so, ca hai gia tri deu
# xuat hien trong text phang) van GIU NGUYEN cung mot hang sau khi bac 2
# dung lai luoi, tren ca 7 trang. Cac hang tang doc doc hong (4 hang tren
# tr14+tr17) da bi LOAI KHOI mau so va DEM RA (xem dong in), khong lam dep
# diem. min > 0,5 -> KHONG DONE_WITH_CONCERNS. NGUONG_CUNG_HANG = lam tron
# xuong 2 chu so cua (1,0000 - 0,05) = lam tron xuong cua 0,9500 = 0,95.
NGUONG_CUNG_HANG = 0.95


def _vn(n: int) -> str:
    s = f"{abs(n):,}".replace(",", ".")
    return f"({s})" if n < 0 else s


def _cac_tep_dap_an():
    return sorted(glob.glob(os.path.join(DAP_AN, "SCID_2026H1_tr*.json")))


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.skipif(not os.path.isfile(PDF), reason="khong co ban scan that")
@pytest.mark.parametrize("duong", _cac_tep_dap_an())
def test_gia_tri_cung_hang_van_cung_hang_sau_khi_dung_lai(duong):
    d = json.load(open(duong, encoding="utf-8"))
    assert d["trang_thai"] == "DA_DUYET", f"{duong} chua duoc duyet"
    cots = [c for c in d["cot"]
            if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")]

    kq = read_page(PDF, d["trang_pdf"])
    tho = kq.text
    luoi = bang.dung_luoi([
        OcrWord(text=w["t"], conf=w["c"], left=w["l"], top=w["y"],
                width=w["w"], height=w["h"], line_id=tuple(w["g"]))
        for r in kq.regions for w in r.words])

    cung_hang = tong = bo_qua = 0
    for h in d["hang"]:
        muc = [_vn(h[c]) for c in cots if isinstance(h.get(c), int)]
        if len(muc) < 2:
            continue                      # can >=2 gia tri moi noi duoc "cung hang"
        if any(m not in tho for m in muc):
            bo_qua += 1                   # tang doc doc hong -> KHONG tinh vao mau so
            continue
        tong += 1
        if any(all(m in " ".join(hang) for m in muc) for hang in luoi):
            cung_hang += 1

    print(f"\n{os.path.basename(duong)}: {cung_hang}/{tong} hang giu nguyen "
          f"({bo_qua} hang bo qua vi TANG DOC doc hong, khong phai loi bac 2)")
    assert tong > 0, "khong hang nao du dieu kien -> phep do nay khong do gi"
    assert cung_hang / tong >= NGUONG_CUNG_HANG
