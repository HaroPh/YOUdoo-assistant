"""Doi chieu dap an (Claude doc anh) voi Tesseract — sinh HANG DOI BAT DONG.

Cho nao ca hai khop VA cong so hoc thoa  -> tu nhan, khong lam phien nguoi.
Cho nao lech                             -> day sang nguoi duyet.

Muc dich KHONG phai cham diem Tesseract, ma la thu HEP viec nguoi phai soi:
tu "doc lai 200 con so" xuong con "xem may cho hai may doc khong dong y".
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath("backend"))
from src.ocr.document import read_page                       # noqa: E402


def vn(n: int) -> str:
    """So nguyen -> chuoi kieu Viet: -2428531621 -> '(2.428.531.621)'."""
    s = f"{abs(n):,}".replace(",", ".")
    return f"({s})" if n < 0 else s


def chuan_hoa(s: str) -> str:
    """Bo moi dau phan cach de so sanh CHU SO thuan tuy."""
    return re.sub(r"[.,\s]", "", s)


def main(duong_key: str, duong_pdf: str) -> int:
    d = json.load(open(duong_key, encoding="utf-8"))
    tho = read_page(duong_pdf, d["trang_pdf"]).text
    tho_phang = chuan_hoa(tho)

    khop, lech_dau_phan_cach, vang = [], [], []
    for h in d["hang"]:
        for cot in ("nam_nay", "nam_truoc"):
            v = h.get(cot)
            if not v:                       # bo qua None va 0 (o gach ngang)
                continue
            muc = vn(v)
            if muc in tho:
                khop.append((h["ma_so"], cot, muc))
            elif chuan_hoa(muc) in tho_phang:
                lech_dau_phan_cach.append((h["ma_so"], cot, muc))
            else:
                vang.append((h["ma_so"], cot, muc))

    tong = len(khop) + len(lech_dau_phan_cach) + len(vang)
    print(f"=== {os.path.basename(duong_key)} — trang {d['trang_pdf']} ===")
    print(f"o co gia tri: {tong}")
    print(f"  khop nguyen van        : {len(khop)}")
    print(f"  dung chu so, LECH DAU  : {len(lech_dau_phan_cach)}   <- Tesseract sai phan cach")
    print(f"  KHONG TIM THAY         : {len(vang)}   <- CAN NGUOI DUYET")
    for ma, cot, muc in lech_dau_phan_cach:
        print(f"    [dau  ] ma so {ma} {cot}: dap an {muc}")
    for ma, cot, muc in vang:
        print(f"    [VANG ] ma so {ma} {cot}: dap an {muc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
