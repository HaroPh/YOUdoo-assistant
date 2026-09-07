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

Chạy:  python -m tools.calibrate_table [so_trang_toi_da]
"""
import glob
import itertools
import os
import sys

import pdfplumber

from src.ocr import table, engine, table_score
from src.ocr.document import _anh_cua_trang

THU_MUC = ["src/rag/seed/law", r"D:\Youdoo\tmp-docs"]
DPI = 200

# FIX ROUND 2: cặp tham số nào cũng có nguy cơ bị chấm QUÁ CAO nếu thước chỉ
# đo một vế. THU_PHA là một cấu hình suy biến CỐ Ý (gap_factor cực lớn -> không
# khe nào đủ lớn để thành bounds giới -> MỌI bảng suy biến về MỘT cột) — chạy
# kèm để tự kiểm: nếu thước không phạt được cấu hình này, thước không đo gì.
THU_PHA = (1000.0, 0.3)


# THƯỚC DÙNG CHUNG: `words_in_bbox` / `tokens` / `score` nay nằm ở
# `src/ocr/table_score.py`, cổng A (`tests/ocr/test_table_gate_vector.py`)
# import CÙNG một bản. Trước 2026-09-07 mỗi bên giữ một bản chép tay và hai
# bản ĐÃ LỆCH (bản cổng A xử lý ô xuống dòng, bản ở đây thì không) — nghĩa là
# bảng số đo chốt tham số được sinh bởi thước KHÁC thước đang gác (phát hiện
# I6 của review toàn nhánh). Đừng chép lại vào đây.


def main(argv):
    gioi_han = int(argv[1]) if len(argv) > 1 else 10**9
    tep = sorted(itertools.chain.from_iterable(
        glob.glob(os.path.join(t, "*.pdf")) for t in THU_MUC))

    # FIX ROUND 3: thêm nấc ty_le=0.75 vì round 2 chốt ĐÚNG RÌA lưới (0.6 là
    # giá trị lớn nhất từng thử, điểm vẫn tăng đơn điệu tới đó) — không biết
    # đỉnh thật nằm ở đâu nếu không thử thêm.
    luoi_tham_so = [(ds, tl) for ds in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
                    for tl in (0.15, 0.3, 0.45, 0.6, 0.75)]
    tat_ca_tham_so = luoi_tham_so + [THU_PHA]
    # [kept, keep_total, tach, split_total, bo, tong_cot, so_bang, trang_suy_bien]
    diem = {k: [0, 0, 0, 0, 0, 0, 0, 0] for k in tat_ca_tham_so}
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
                        answer = b.extract()
                    except Exception:
                        continue
                    ws = table_score.words_in_bbox(kq.words, b.bbox, DPI / 72)
                    if not ws:
                        continue
                    n_cot_dap_an = max((len(h) for h in answer), default=0)
                    for ds, tl in tat_ca_tham_so:
                        grid = table.build_grid(ws, gap_factor=ds,
                                              support_ratio=tl)
                        kept, keep_total, tach, split_total, bo, _wrapped = (
                            table_score.score(answer, grid, kq.text))
                        n_cot_luoi = max((len(h) for h in grid), default=0)
                        so_cot = n_cot_luoi if n_cot_luoi else 1
                        d = diem[(ds, tl)]
                        d[0] += kept
                        d[1] += keep_total
                        d[2] += tach
                        d[3] += split_total
                        d[4] += bo
                        d[5] += so_cot
                        d[6] += 1
                        if n_cot_dap_an >= 2 and n_cot_luoi <= 1:
                            d[7] += 1
                        if keep_total:
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
        kept, keep_total, tach, split_total, bo, tong_cot, so_bang, collapsed = v
        ty_giu = kept / keep_total if keep_total else 0.0
        ty_tach = tach / split_total if split_total else 0.0
        m = min(ty_giu, ty_tach)
        cot_tb = tong_cot / so_bang if so_bang else 0.0
        return (ds, tl, ty_giu, ty_tach, m, bo, cot_tb, collapsed)

    thuong = [_hang(ds, tl, diem[(ds, tl)]) for ds, tl in luoi_tham_so]
    thuong_theo_ban = {(r[0], r[1]): r for r in thuong}

    print(f"\n{'gap_factor':>10}{'ty_le':>8}{'kept':>9}{'tach':>9}{'min':>9}"
          f"{'unreadable':>13}{'cot_tb':>9}{'trang_suy_bien':>16}")
    thuong_in = sorted(thuong, key=lambda r: -r[4])
    for ds, tl, ty_giu, ty_tach, m, bo, cot_tb, collapsed in thuong_in:
        print(f"{ds:>10}{tl:>8}{ty_giu:>9.4f}{ty_tach:>9.4f}"
              f"{m:>9.4f}{bo:>13}{cot_tb:>9.2f}{collapsed:>16}")

    ds, tl = THU_PHA
    r = _hang(ds, tl, diem[THU_PHA])
    print(f"\n(THỬ PHÁ — suy biến một cột, gap_factor={ds}, ty_le={tl})")
    print(f"{ds:>10}{tl:>8}{r[2]:>9.4f}{r[3]:>9.4f}"
          f"{r[4]:>9.4f}{r[5]:>13}{r[6]:>9.2f}{r[7]:>16}")

    # FIX ROUND 3: tiêu chí chốt KHÔNG còn là "điểm cao nhất" đơn thuần. Với
    # mỗi gap_factor, sắp ty_le tăng dần: một cấu hình bị LOẠI nếu trang_suy_bien
    # của nó CAO HƠN cấu hình ty_le thấp hơn liền kề CÙNG gap_factor — nghĩa là
    # tăng ty_le đó đã đổi lấy thêm trang sập về một cột, dù điểm tổng có thể
    # vẫn nhích lên (trung bình che mất thảm hoạ cục bộ vì đa số trang chỉ
    # đóng góp vài ô). Cấu hình ty_le nhỏ nhất của mỗi gap_factor luôn ĐỦ ĐIỀU
    # KIỆN (không có cấu hình thấp hơn để so).
    boi_khe_ds = sorted({ds for ds, _ in luoi_tham_so})
    ty_le_ds = sorted({tl for _, tl in luoi_tham_so})
    du_dieu_kien = []
    bi_loai = []
    for ds in boi_khe_ds:
        suy_bien_truoc = None
        for tl in ty_le_ds:
            r = thuong_theo_ban[(ds, tl)]
            suy_bien_hien_tai = r[7]
            if suy_bien_truoc is None or suy_bien_hien_tai <= suy_bien_truoc:
                du_dieu_kien.append(r)
            else:
                bi_loai.append(r)
            suy_bien_truoc = suy_bien_hien_tai

    print(f"\n(Cấu hình BỊ LOẠI vì tăng trang_suy_bien so với ty_le thấp hơn"
          f" liền kề cùng gap_factor: {len(bi_loai)}/{len(luoi_tham_so)})")
    for ds, tl, ty_giu, ty_tach, m, bo, cot_tb, collapsed in bi_loai:
        print(f"  LOẠI  gap_factor={ds} ty_le={tl}  min={m:.4f}"
              f"  trang_suy_bien={collapsed}")

    if not bi_loai:
        print("\nKHÔNG cấu hình nào bị loại — không phát hiện vách đá trong"
              " toàn lưới đã quét. Chốt theo điểm min cao nhất như thường lệ.")

    chot = max(du_dieu_kien, key=lambda r: r[4])
    print(f"\n(CHỐT — min cao nhất trong số ĐỦ ĐIỀU KIỆN) gap_factor={chot[0]}"
          f" ty_le={chot[1]}  min={chot[4]:.4f}  trang_suy_bien={chot[7]}")


if __name__ == "__main__":
    main(sys.argv)
