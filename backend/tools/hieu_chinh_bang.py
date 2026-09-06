"""Hiệu chỉnh tham số bậc 2 trên MỌI trang bảng vector của corpus.

Đáp án TỰ SINH: trang bảng vector rasterise ra ảnh, đọc lại bằng OCR, dựng
lưới, rồi so với lưới `pdfplumber` bóc từ CHÍNH trang đó. Không gõ tay ô nào,
và phủ nhiều định dạng — đúng chỗ yếu của việc hiệu chỉnh trên một tài liệu.

LỆCH so với brief gốc: `THU_MUC` trỏ tuyệt đối vào corpus của repo chính
(`D:\\Youdoo\\tmp-docs`), không phải `../tmp-docs` tương đối. Script này chạy
từ một git worktree (`.claude/worktrees/ocr-bac-2/backend`) — `tmp-docs` là
thư mục KHÔNG theo dõi bởi git (không nằm trong bất cứ worktree nào), nó chỉ
tồn tại một bản duy nhất ở gốc repo chính. Đường dẫn tương đối `../tmp-docs`
sẽ trỏ vào `.claude/worktrees/ocr-bac-2/tmp-docs`, không tồn tại.

Chạy:  python -m tools.hieu_chinh_bang [so_trang_toi_da]
"""
import glob
import itertools
import os
import sys

import pdfplumber

from src.ocr import bang, engine
from src.ocr.document import _anh_cua_trang

THU_MUC = ["src/rag/seed/law", r"D:\Youdoo\tmp-docs"]
DPI = 200

# FIX ROUND 2: cặp tham số nào cũng có nguy cơ bị chấm QUÁ CAO nếu thước chỉ
# đo một vế. THU_PHA là một cấu hình suy biến CỐ Ý (boi_khe cực lớn -> không
# khe nào đủ lớn để thành ranh giới -> MỌI bảng suy biến về MỘT cột) — chạy
# kèm để tự kiểm: nếu thước không phạt được cấu hình này, thước không đo gì.
THU_PHA = (1000.0, 0.3)


def _tu_trong_bbox(words, bbox, ty_le):
    """Chỉ giữ từ nằm trong khung bảng. `bbox` theo ĐIỂM (pdfplumber), toạ độ
    từ theo PIXEL ảnh — nhân `ty_le` = DPI/72 để về cùng hệ."""
    x0, top, x1, bot = (v * ty_le for v in bbox)
    return [w for w in words
            if x0 <= w.left and w.left + w.width <= x1
            and top <= w.top and w.top + w.height <= bot]


def _tk(o) -> list[str]:
    """Token đủ dài để tìm trong text phẳng mà không khớp bừa."""
    return [t for t in (o or "").split() if len(t) >= 3]


def _diem(dap_an: list[list], luoi: list[list[str]], tho: str):
    """(giu, giu_mau_so, tach, tach_mau_so, bo_doc_hong).

    FIX ROUND 2 (2026-09-06): thước round 1 chỉ đo MỘT vế — "mọi token của ô
    đáp án nằm trong CÙNG MỘT ô lưới" — và bị lưới suy biến MỘT CỘT ăn gian
    miễn phí: cả hàng là một ô nên vế đó luôn đúng. Đo được: `boi_khe=1000`
    (không khe nào đủ lớn để thành ranh giới) vẫn đạt 0,9706 trên
    `luat-thuexuatnhapkhau.pdf` tr.14 — cao ngang cặp "tốt nhất" của round 1.
    Thước không phân biệt được "dựng đúng cột" với "không dựng cột nào cả".

    ĐỐI XỨNG, và đó là điểm mấu chốt:
      vế 1 KHÔNG TÁCH NHẦM — mọi token của MỘT ô đáp án nằm trong CÙNG MỘT ô
                             lưới (thước round 1, giữ nguyên).
      vế 2 KHÔNG GỘP NHẦM  — HAI ô KHÁC NHAU trong cùng một hàng đáp án KHÔNG
                             được rơi chung một ô lưới.

    Chỉ có vế 1 thì một lưới MỘT CỘT đạt điểm tuyệt đối miễn phí. Chỉ có vế 2
    thì tách vụn từng từ thành một cột riêng lại thắng tuyệt đối. Điểm cuối
    (tính ở `main`) lấy MIN của hai vế nên cả hai hướng suy biến đều bị phạt.

    Ô nào tầng đọc không đọc được thì loại khỏi CẢ HAI mẫu số và đếm riêng —
    chấm nó là chấm chất lượng OCR, không phải việc của bậc 2 (spec §2.4).
    """
    ph = tho.replace("\n", " ")
    giu = giu_ms = tach = tach_ms = bo = 0
    for hang in dap_an:
        doc_duoc = []
        for o in hang:
            t = _tk(o)
            if not t:
                continue
            if not all(x in ph for x in t):
                bo += 1
                continue
            doc_duoc.append(t)
        for t in doc_duoc:
            giu_ms += 1
            if any(all(x in c for x in t) for h in luoi for c in h):
                giu += 1
        for i in range(len(doc_duoc)):
            for j in range(i + 1, len(doc_duoc)):
                tach_ms += 1
                chung = any(all(x in c for x in doc_duoc[i])
                            and all(y in c for y in doc_duoc[j])
                            for h in luoi for c in h)
                if not chung:
                    tach += 1
    return giu, giu_ms, tach, tach_ms, bo


def main(argv):
    gioi_han = int(argv[1]) if len(argv) > 1 else 10**9
    tep = sorted(itertools.chain.from_iterable(
        glob.glob(os.path.join(t, "*.pdf")) for t in THU_MUC))

    luoi_tham_so = [(ds, tl) for ds in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
                    for tl in (0.15, 0.3, 0.45, 0.6)]
    tat_ca_tham_so = luoi_tham_so + [THU_PHA]
    # [giu, giu_ms, tach, tach_ms, bo, tong_cot, so_bang]
    diem = {k: [0, 0, 0, 0, 0, 0, 0] for k in tat_ca_tham_so}
    da_lam = 0
    so_tep_co_bang = set()

    for p in tep:
        if da_lam >= gioi_han:
            break
        with pdfplumber.open(p) as pdf:
            for pageno, pg in enumerate(pdf.pages, 1):
                if da_lam >= gioi_han:
                    break
                bangs = pg.find_tables()
                if not bangs:
                    continue
                img = _anh_cua_trang(p, pageno, DPI)
                kq = engine.ocr_image(img)
                trang_co_o = False
                for b in bangs:
                    try:
                        dap_an = b.extract()
                    except Exception:
                        continue
                    ws = _tu_trong_bbox(kq.words, b.bbox, DPI / 72)
                    if not ws:
                        continue
                    for ds, tl in tat_ca_tham_so:
                        luoi = bang.dung_luoi(ws, boi_khe=ds,
                                              ty_le_ung_ho=tl)
                        giu, giu_ms, tach, tach_ms, bo = _diem(
                            dap_an, luoi, kq.text)
                        so_cot = len(luoi[0]) if luoi and luoi[0] else 1
                        d = diem[(ds, tl)]
                        d[0] += giu
                        d[1] += giu_ms
                        d[2] += tach
                        d[3] += tach_ms
                        d[4] += bo
                        d[5] += so_cot
                        d[6] += 1
                        if giu_ms:
                            trang_co_o = True
                if trang_co_o:
                    so_tep_co_bang.add(p)
                da_lam += 1
                print(f"  {os.path.basename(p)[:34]:36s} tr{pageno:>3}"
                      f"  ({da_lam} trang)", flush=True)

    tong_giu_ms = max((v[1] for v in diem.values()), default=0)
    tong_bo = max((v[4] for v in diem.values()), default=0)
    print(f"\n(tổng kết) {len(so_tep_co_bang)} tệp có ô, {da_lam} trang quét,"
          f" tối đa {tong_giu_ms} ô chấm được (+{tong_bo} ô BỎ vì tầng đọc"
          f" hỏng) trong 1 cấu hình tham số")

    def _hang(ds, tl, v):
        giu, giu_ms, tach, tach_ms, bo, tong_cot, so_bang = v
        ty_giu = giu / giu_ms if giu_ms else 0.0
        ty_tach = tach / tach_ms if tach_ms else 0.0
        m = min(ty_giu, ty_tach)
        cot_tb = tong_cot / so_bang if so_bang else 0.0
        return (ds, tl, ty_giu, ty_tach, m, bo, cot_tb)

    thuong = [_hang(ds, tl, diem[(ds, tl)]) for ds, tl in luoi_tham_so]
    thuong.sort(key=lambda r: -r[4])

    print(f"\n{'boi_khe':>10}{'ty_le':>8}{'giu':>9}{'tach':>9}"
          f"{'min':>9}{'bo_doc_hong':>13}{'cot_tb':>9}")
    for ds, tl, ty_giu, ty_tach, m, bo, cot_tb in thuong:
        print(f"{ds:>10}{tl:>8}{ty_giu:>9.4f}{ty_tach:>9.4f}"
              f"{m:>9.4f}{bo:>13}{cot_tb:>9.2f}")

    ds, tl = THU_PHA
    r = _hang(ds, tl, diem[THU_PHA])
    print(f"\n(THỬ PHÁ — suy biến một cột, boi_khe={ds}, ty_le={tl})")
    print(f"{ds:>10}{tl:>8}{r[2]:>9.4f}{r[3]:>9.4f}"
          f"{r[4]:>9.4f}{r[5]:>13}{r[6]:>9.2f}")


if __name__ == "__main__":
    main(sys.argv)
