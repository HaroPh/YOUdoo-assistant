"""Cong so hoc cho dap an bang tai chinh — TAT DINH, khong LLM, khong nguon ngoai.

Y tuong: mot bao cao tai chinh TU MANG dap an. Dong tong phai bang tong cac
dong thanh phan. Neu ai do (Claude, Tesseract, hay thuat toan dung bang cua
bac 2) doc/dung SAI mot o, tong se khong ra.

Day la phien ban manh nhat cua "cong tu nuoi" ap vao bang: no kiem CAU TRUC
chu khong chi kiem CHU, vi muon cong duoc thi phai biet o nao thuoc cot nao.

Chay:  python kiem_so_hoc.py <tep_dap_an.json> [...]
Thoat khac 0 neu co rang buoc nao khong thoa.
"""
import json
import sys


def kiem(duong: str) -> list[str]:
    d = json.load(open(duong, encoding="utf-8"))
    theo_ma = {h["ma_so"]: h for h in d["hang"] if h.get("ma_so")}
    loi = []
    for rb in d["rang_buoc_so_hoc"]:
        tong_ma = rb["tong"]
        if tong_ma not in theo_ma:
            loi.append(f"{duong}: rang buoc tro toi ma so {tong_ma} khong co trong bang")
            continue
        for cot in ("nam_nay", "nam_truoc"):
            thieu = [m for m in rb["cong"] if m not in theo_ma]
            if thieu:
                loi.append(f"{duong}: [{cot}] rang buoc {tong_ma} thieu ma so {thieu}")
                continue
            tong_tinh = sum(theo_ma[m][cot] or 0 for m in rb["cong"])
            tong_ghi = theo_ma[tong_ma][cot]
            if tong_ghi is None:
                loi.append(f"{duong}: [{cot}] ma so {tong_ma} khong co gia tri de doi chieu")
            elif tong_tinh != tong_ghi:
                loi.append(f"{duong}: [{cot}] ma so {tong_ma}: ghi {tong_ghi:,} "
                           f"nhung tong {'+'.join(rb['cong'])} = {tong_tinh:,} "
                           f"(lech {tong_ghi - tong_tinh:,})")
    return loi


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("dung: kiem_so_hoc.py <tep_dap_an.json> [...]")
        return 2
    tong_loi = []
    for duong in argv[1:]:
        d = json.load(open(duong, encoding="utf-8"))
        loi = kiem(duong)
        n = len(d["rang_buoc_so_hoc"]) * 2          # moi rang buoc x 2 cot
        print(f"{duong}: {n - len(loi)}/{n} rang buoc THOA"
              f"   [{d.get('trang_thai', '?')}]")
        tong_loi += loi
    for e in tong_loi:
        print("  LECH:", e)
    return 1 if tong_loi else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
