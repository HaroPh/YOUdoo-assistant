"""Cong so hoc cho dap an bang tai chinh — TAT DINH, khong LLM, khong nguon ngoai.

Y tuong: mot bao cao tai chinh TU MANG dap an. Dong tong phai bang tong (co dau)
cac dong thanh phan. Neu ai do — Claude doc anh, Tesseract, hay thuat toan dung
bang cua bac 2 — doc/dung SAI mot o, chuoi rang buoc se gay o dau do.

Day la phien ban manh nhat cua "cong tu nuoi" ap vao bang: no kiem CAU TRUC chu
khong chi kiem CHU, vi muon cong duoc thi phai biet o nao thuoc cot nao va hang
nao thuoc muc nao.

Chay:  python kiem_so_hoc.py <tep_dap_an.json> [...]
Thoat khac 0 neu co rang buoc nao khong thoa.
"""
import json
import sys

# Cot khong mang gia tri so — moi cot con lai trong `cot` la cot gia tri.
COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")


def cot_gia_tri(d: dict) -> list[str]:
    """Ten cot gia tri khac nhau giua cac bang ("nam_nay"/"nam_truoc" o luu
    chuyen tien te, "so_cuoi_ky"/"so_dau_nam" o bang can doi), nen SUY tu khai
    bao `cot` cua chinh tep thay vi gan chet — gan chet thi them mot bang moi
    la no."""
    return [c for c in d["cot"] if c not in COT_NHAN]


def gia_tri(o, ma: str, cot: str) -> tuple[int | None, str | None]:
    """O -> (so de cong, loi neu co).

    Quy uoc o:
      so    -> gia tri that
      "-"   -> CO o, KHONG co so: cong bang 0
      null  -> KHONG AP DUNG (hang tieu de). Mot rang buoc tro toi o null la LOI
               DU LIEU, khong duoc lang le coi la 0 — do dung la cach mot dong bi
               doc sot ma cong van xanh.
    """
    if o == "-":
        return 0, None
    if isinstance(o, int):
        return o, None
    if o is None:
        return None, f"ma so {ma} [{cot}]: rang buoc tro toi o null (khong ap dung)"
    return None, f"ma so {ma} [{cot}]: kieu o khong hieu duoc: {o!r}"


def tach_thanh_phan(x) -> tuple[str, int]:
    """Mot thanh phan cua rang buoc: "111" hoac ["111", -1].

    He so am la BAT BUOC cho bao cao ket qua kinh doanh (20 = 10 - 11). Khong
    the lach bang cach luu chi phi thanh so am trong dap an: dap an phai trung
    thanh voi thu IN TREN GIAY, con dau la ngu nghia ke toan cua rang buoc.
    """
    if isinstance(x, str):
        return x, 1
    ma, he_so = x
    return ma, int(he_so)


def tra_cuu(ma: str, nhom_minh: str | None, toan_cuc: dict) -> tuple[dict | None, str]:
    """Giai mot tham chieu ma so. Dang "nhom:ma" tro sang bao cao KHAC (vi du
    ket qua kinh doanh tro toi bang can doi); dang "ma" tro trong nhom cua minh.

    Can qualifier vi ma so KHONG duy nhat toan cuc: luu chuyen tien te va ket
    qua kinh doanh deu co ma "01" nhung la hai chi tieu khac han.
    """
    if ":" in ma:
        nhom, ma_that = ma.split(":", 1)
    else:
        nhom, ma_that = nhom_minh, ma
    return toan_cuc.get((nhom, ma_that)), ma


def kiem(duong: str, toan_cuc: dict) -> list[str]:
    d = json.load(open(duong, encoding="utf-8"))
    nhom = d.get("nhom")
    loi = []
    cots = cot_gia_tri(d)
    if not cots:
        return [f"{duong}: khong tim thay cot gia tri nao trong {d['cot']}"]

    for rb in d["rang_buoc_so_hoc"]:
        hang_tong, _ = tra_cuu(rb["tong"], nhom, toan_cuc)
        if hang_tong is None:
            loi.append(f"{duong}: rang buoc tro toi ma so {rb['tong']} khong tim thay")
            continue
        for cot in cots:
            phan, loi_o = 0, []
            for tp in rb["cong"]:
                ma, he_so = tach_thanh_phan(tp)
                hang, nhan = tra_cuu(ma, nhom, toan_cuc)
                if hang is None:
                    loi_o.append(f"ma so {nhan} khong tim thay")
                    continue
                if cot not in hang:
                    loi_o.append(f"ma so {nhan} khong co cot [{cot}]")
                    continue
                v, e = gia_tri(hang[cot], nhan, cot)
                if e:
                    loi_o.append(e)
                else:
                    phan += he_so * v
            if loi_o:
                loi += [f"{duong}: {e}" for e in loi_o]
                continue
            if cot not in hang_tong:
                loi.append(f"{duong}: ma so {rb['tong']} khong co cot [{cot}]")
                continue
            tong_ghi, e = gia_tri(hang_tong[cot], rb["tong"], cot)
            if e:
                loi.append(f"{duong}: {e}")
            elif phan != tong_ghi:
                cong_thuc = " ".join(
                    ("-" if h < 0 else "+") + m for m, h in map(tach_thanh_phan, rb["cong"]))
                loi.append(f"{duong}: [{cot}] ma so {rb['tong']}: ghi {tong_ghi:,} "
                           f"nhung {cong_thuc.lstrip('+')} = {phan:,} "
                           f"(lech {tong_ghi - phan:,})")
    return loi


def kiem_lien_bao_cao(duong: str, toan_cuc: dict) -> tuple[int, list[str]]:
    """Rang buoc noi HAI BAO CAO khac nhau, khai bao CO T TUONG MINH ca hai ben.

    Vi sao phai khai bao cot chu khong suy ra: hai bao cao dat ten cot khac nhau
    ("nam_nay" vs "so_cuoi_ky") VA anh xa khac nhau tuy tung rang buoc — ma 70
    (tien cuoi ky) ung voi so_cuoi_ky, con ma 60 (tien dau nam) ung voi
    so_dau_nam cua CUNG mot dong 110. Doan mo se sai.

    Bai hoc da tra gia: rang buoc 61 = 420b ban dau viet duoi dang ma so thuan
    va DUNG o cot nay nhung SAI o cot kia (so_dau_nam cua 420b la so du dau ky,
    khong phai loi nhuan nam truoc). Hai o bang nhau o mot cot khong co nghia
    hai DONG tuong duong nhau.
    """
    d = json.load(open(duong, encoding="utf-8"))
    ds = d.get("rang_buoc_lien_bao_cao", [])
    loi = []
    for rb in ds:
        ben = {}
        for phia in ("trai", "phai"):
            t = rb[phia]
            hang = toan_cuc.get((t["nhom"], t["ma_so"]))
            if hang is None:
                loi.append(f"{duong}: [{phia}] {t['nhom']}:{t['ma_so']} khong tim thay "
                           f"(co truyen tep chua no vao khong?)")
                break
            if t["cot"] not in hang:
                loi.append(f"{duong}: [{phia}] {t['nhom']}:{t['ma_so']} khong co cot "
                           f"[{t['cot']}]")
                break
            v, e = gia_tri(hang[t["cot"]], t["ma_so"], t["cot"])
            if e:
                loi.append(f"{duong}: [{phia}] {e}")
                break
            ben[phia] = v
        else:
            if ben["trai"] != ben["phai"]:
                a, b = rb["trai"], rb["phai"]
                loi.append(f"{duong}: {a['nhom']}:{a['ma_so']}[{a['cot']}] = "
                           f"{ben['trai']:,} NHUNG {b['nhom']}:{b['ma_so']}[{b['cot']}] = "
                           f"{ben['phai']:,} (lech {ben['trai'] - ben['phai']:,})")
    return len(ds), loi


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("dung: kiem_so_hoc.py <tep_dap_an.json> [...]")
        return 2

    # Gom ma so cua MOI tep truoc, khoa theo (nhom, ma so), de rang buoc bac qua
    # trang va bac qua bao cao giai duoc du thu tu tham so the nao.
    toan_cuc: dict[tuple[str | None, str], dict] = {}
    for duong in argv[1:]:
        d = json.load(open(duong, encoding="utf-8"))
        for h in d["hang"]:
            if h.get("ma_so"):
                toan_cuc[(d.get("nhom"), h["ma_so"])] = h

    tong_loi = []
    for duong in argv[1:]:
        d = json.load(open(duong, encoding="utf-8"))
        loi = kiem(duong, toan_cuc)
        n = len(d["rang_buoc_so_hoc"]) * len(cot_gia_tri(d))
        n_lbc, loi_lbc = kiem_lien_bao_cao(duong, toan_cuc)
        n += n_lbc
        loi += loi_lbc
        print(f"{duong}: {n - len(loi)}/{n} rang buoc THOA"
              f"{f' (trong do {n_lbc} lien bao cao)' if n_lbc else ''}"
              f"   [{d.get('trang_thai', '?')}]")
        tong_loi += loi
    for e in tong_loi:
        print("  LECH:", e)
    return 1 if tong_loi else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
