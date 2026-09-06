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


def gia_tri(o, ma: str, cot: str) -> tuple[int | None, str | None]:
    """O -> (so de cong, loi neu co).

    Quy uoc o (xem `quy_uoc_o` trong tep dap an):
      so    -> gia tri that
      "-"   -> CO o, KHONG co so: cong bang 0
      null  -> KHONG AP DUNG (hang tieu de). Mot rang buoc tro toi o null la
               LOI DU LIEU, khong duoc lang le coi la 0 — do dung la cach mot
               dong bi doc sot ma cong van xanh.
    """
    if o == "-":
        return 0, None
    if isinstance(o, int):
        return o, None
    if o is None:
        return None, f"ma so {ma} [{cot}]: rang buoc tro toi o null (khong ap dung)"
    return None, f"ma so {ma} [{cot}]: kieu o khong hieu duoc: {o!r}"


def kiem(duong: str, theo_ma_nhom: dict | None = None) -> list[str]:
    d = json.load(open(duong, encoding="utf-8"))
    # Ma so trong tep nay. Neu tep thuoc mot NHOM (nhieu trang cua cung mot
    # bang), tra cuu lui ve ban do chung cua ca nhom — bao cao tai chinh co
    # rang buoc BAC QUA TRANG, manh nhat la 280 = 100 + 200 (tong cong tai san
    # bang tai san ngan han o trang truoc cong tai san dai han o trang nay).
    theo_ma = dict(theo_ma_nhom or {})
    theo_ma.update({h["ma_so"]: h for h in d["hang"] if h.get("ma_so")})
    loi = []
    # Ten cot GIA TRI khac nhau giua cac bang ("nam_nay"/"nam_truoc" o luu chuyen
    # tien te, "so_cuoi_ky"/"so_dau_nam" o bang can doi), nen SUY tu khai bao
    # `cot` cua chinh tep thay vi gan chet — gan chet thi them mot bang moi la no.
    cot_gia_tri = [c for c in d["cot"] if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")]
    if not cot_gia_tri:
        return [f"{duong}: khong tim thay cot gia tri nao trong {d['cot']}"]
    for rb in d["rang_buoc_so_hoc"]:
        tong_ma = rb["tong"]
        if tong_ma not in theo_ma:
            loi.append(f"{duong}: rang buoc tro toi ma so {tong_ma} khong co trong bang")
            continue
        for cot in cot_gia_tri:
            thieu = [m for m in rb["cong"] if m not in theo_ma]
            if thieu:
                loi.append(f"{duong}: [{cot}] rang buoc {tong_ma} thieu ma so {thieu}")
                continue
            phan, loi_o = [], []
            for m in rb["cong"]:
                v, e = gia_tri(theo_ma[m][cot], m, cot)
                (phan if e is None else loi_o).append(v if e is None else e)
            if loi_o:
                loi += [f"{duong}: {e}" for e in loi_o]
                continue
            tong_tinh = sum(phan)
            tong_ghi, e = gia_tri(theo_ma[tong_ma][cot], tong_ma, cot)
            if e:
                loi.append(f"{duong}: {e}")
            elif tong_tinh != tong_ghi:
                loi.append(f"{duong}: [{cot}] ma so {tong_ma}: ghi {tong_ghi:,} "
                           f"nhung tong {'+'.join(rb['cong'])} = {tong_tinh:,} "
                           f"(lech {tong_ghi - tong_tinh:,})")
    return loi


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("dung: kiem_so_hoc.py <tep_dap_an.json> [...]")
        return 2
    # Gom ma so theo nhom TRUOC, de rang buoc bac qua trang giai duoc du thu tu
    # tham so the nao. Ma so trong cung mot nhom la duy nhat (bang can doi dung
    # 100-280, luu chuyen tien dung 01-30) nen gop khong dam nhau; KHAC nhom thi
    # KHONG gop, vi luu chuyen tien va ket qua kinh doanh deu co ma "01".
    theo_nhom: dict[str, dict] = {}
    for duong in argv[1:]:
        d = json.load(open(duong, encoding="utf-8"))
        nhom = d.get("nhom")
        if nhom:
            theo_nhom.setdefault(nhom, {}).update(
                {h["ma_so"]: h for h in d["hang"] if h.get("ma_so")})

    tong_loi = []
    for duong in argv[1:]:
        d = json.load(open(duong, encoding="utf-8"))
        loi = kiem(duong, theo_nhom.get(d.get("nhom")))
        n_cot = len([c for c in d["cot"]
                     if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")])
        n = len(d["rang_buoc_so_hoc"]) * n_cot
        print(f"{duong}: {n - len(loi)}/{n} rang buoc THOA"
              f"   [{d.get('trang_thai', '?')}]")
        tong_loi += loi
    for e in tong_loi:
        print("  LECH:", e)
    return 1 if tong_loi else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
