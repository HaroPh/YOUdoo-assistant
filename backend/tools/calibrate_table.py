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

HAI CHÂN, và đó là điểm sửa ngày 2026-09-07:
- chân VECTOR (cũ): đáp án thật từ pdfplumber, thước đối xứng nên phạt được
  CẢ tách vụn lẫn gộp nhầm — nhưng chỉ trên ảnh rasterise SẠCH;
- chân SCAN (mới): 6 báo cáo tài chính ảnh thuần, không có đáp án, dùng
  `table_score.score_unlabelled` — bắt gộp nhầm trên ảnh thoái hoá thật,
  nhưng MÙ với tách vụn.
Điểm gộp = min(hai chân). Vế tách vụn do chân vector gác, vế gộp nhầm do chân
scan gác; không cần hệ số cân bằng bịa ra. Trước ngày này chỉ có chân vector,
và hằng số chốt ra từ đó sập 12 trang bảng trên corpus scan thật.

Chạy:  python -m tools.calibrate_table [so_trang_toi_da]
"""
import glob
import itertools
import os
import sys

import pdfplumber

from src.ocr import table, engine, table_score
from src.ocr.document import _anh_cua_trang, read_page
from src.ocr.engine import OcrWord

THU_MUC = ["src/rag/seed/law", r"D:\Youdoo\tmp-docs"]
DPI = 200

# Corpus scan thật (ảnh thuần, không có lớp text) — xem README trong thư
# mục đó. Nằm ngoài worktree nên đường dẫn phải TUYỆT ĐỐI, cùng lý do như
# THU_MUC.
THU_MUC_SCAN = r"D:\Youdoo\tmp-docs\ocr-scan-that"
SCAN_THEM = [r"D:\downloads\SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf"]
# Dưới ngưỡng này trang không đủ hàng bảng để nói lên điều gì.
MIN_MONEY_ROWS = 5

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
    # 2026-09-07: NỚI LƯỚI XUỐNG DƯỚI. Vòng trước chỉ thử tới ty_le=0.15 và
    # đó là giá trị THẤP NHẤT từng chạy — lại chốt đúng rìa lưới, cùng bệnh mà
    # FIX ROUND 3 đã bắt ở đầu kia. Đo trên corpus scan thật cho thấy vùng lành
    # nằm ở 0.12–0.15, tức NGOÀI lưới cũ hoàn toàn.
    luoi_tham_so = [(ds, tl) for ds in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
                    for tl in (0.05, 0.08, 0.10, 0.12, 0.15, 0.3, 0.45, 0.6, 0.75)]
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

    # ---- CHÂN SCAN ----------------------------------------------------
    # Ảnh thuần, không có đáp án. Dùng `read_page` (KHÔNG phải `ocr_image`) để
    # ăn đệm OCR: đệm khoá theo vân tay cấu hình, mà vòng quét này truyền tham
    # số THẲNG vào `build_grid` chứ không đụng hằng số module, nên vân tay đứng
    # yên và mọi trang chỉ đọc bằng Tesseract đúng một lần.
    # [separated, money_rows, filled, total, trang_sap, cot_max]
    diem_scan = {k: [0, 0, 0, 0, 0, 0] for k in tat_ca_tham_so}
    tep_scan = sorted(glob.glob(os.path.join(THU_MUC_SCAN, "*.pdf"))) + [
        p for p in SCAN_THEM if os.path.isfile(p)]
    so_trang_scan = 0
    for p in tep_scan:
        with pdfplumber.open(p) as pdf:
            trangs = [i + 1 for i, pg in enumerate(pdf.pages)
                      if not (pg.extract_text() or "").strip()]
        for pageno in trangs:
            ws = [OcrWord(text=w["t"], conf=w["c"], left=w["l"], top=w["y"],
                          width=w["w"], height=w["h"], line_id=tuple(w["g"]))
                  for r in read_page(p, pageno).regions for w in r.words]
            if not ws:
                continue
            so_trang_scan += 1
            for ds, tl in tat_ca_tham_so:
                grid = table.build_grid(ws, gap_factor=ds, support_ratio=tl)
                sep, rows, filled, total = table_score.score_unlabelled(grid)
                if rows < MIN_MONEY_ROWS:
                    continue
                n_cot = max((len(h) for h in grid), default=0)
                d = diem_scan[(ds, tl)]
                d[0] += sep
                d[1] += rows
                d[2] += filled
                d[3] += total
                if n_cot <= 1:
                    d[4] += 1
                d[5] = max(d[5], n_cot)
        print(f"  [scan] {os.path.basename(p)[:34]:36s}"
              f" {len(trangs)} trang ảnh", flush=True)
    print(f"{chr(10)}(chân scan) {len(tep_scan)} tệp, {so_trang_scan} trang ảnh")

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

    def _scan(ds, tl):
        sep, rows, filled, total, sap, cot_max = diem_scan[(ds, tl)]
        return (sep / rows if rows else 0.0,
                filled / total if total else 0.0, sap, cot_max)

    print(f"{chr(10)}{'gap':>5}{'ty_le':>7}"
          f"{'| VECTOR kept':>14}{'tach':>8}{'min':>8}{'suybien':>9}"
          f"{'| SCAN tach':>12}{'matdo':>8}{'sap':>6}{'cotmax':>8}"
          f"{'| GOP':>8}")
    bang = []
    for ds, tl in luoi_tham_so:
        v = thuong_theo_ban[(ds, tl)]
        s_tach, s_mat, s_sap, s_cot = _scan(ds, tl)
        gop = min(v[4], s_tach)
        bang.append((ds, tl, v, (s_tach, s_mat, s_sap, s_cot), gop))
    for ds, tl, v, sc, gop in sorted(bang, key=lambda r: -r[4]):
        print(f"{ds:>5}{tl:>7}{v[2]:>14.4f}{v[3]:>8.4f}{v[4]:>8.4f}{v[7]:>9}"
              f"{sc[0]:>12.4f}{sc[1]:>8.3f}{sc[2]:>6}{sc[3]:>8}{gop:>8.4f}")

    ds, tl = THU_PHA
    r = _hang(ds, tl, diem[THU_PHA])
    sc = _scan(ds, tl)
    print(f"{chr(10)}(THỬ PHÁ — suy biến một cột, gap={ds}, ty_le={tl}) "
          f"vector min={r[4]:.4f}  scan tach={sc[0]:.4f}  "
          f"GỘP={min(r[4], sc[0]):.4f}")
    print("  Nếu dòng THỬ PHÁ này KHÔNG thấp hơn hẳn mọi dòng trên, thước"
          " không đo gì — đừng chốt tham số từ bảng này.")

    # TIÊU CHÍ CHỐT, 2026-09-07. Bỏ luật loại-theo-trang_suy_bien của FIX
    # ROUND 3: nó suy ra từ MỘT chân (vector) và chính nó đã chốt ra cấu hình
    # sập 12 trang scan. Nay chốt theo ĐIỂM GỘP = min(vector_min, scan_tach):
    # tách vụn do chân vector phạt (nó có đáp án thật nên biết ô nào bị xé),
    # gộp nhầm do chân scan phạt (nó chạy trên ảnh thoái hoá thật). Không hệ
    # số cân bằng nào được bịa ra — min là min.
    chot = max(bang, key=lambda r: r[4])
    ds, tl, v, sc, gop = chot
    print(f"{chr(10)}(CHỐT theo ĐIỂM GỘP) gap_factor={ds} support_ratio={tl}"
          f"  gộp={gop:.4f}  [vector min={v[4]:.4f}, scan tách={sc[0]:.4f},"
          f" scan sập={sc[2]}, cột tối đa={sc[3]}]")
    print(f"  Hằng số ĐANG SHIP: gap_factor={table.GAP_FACTOR}"
          f" support_ratio={table.SUPPORT_RATIO}")
    if (table.GAP_FACTOR, table.SUPPORT_RATIO) != (ds, tl):
        print("  !! LỆCH — bảng này chốt khác hằng số trong src/ocr/table.py."
              " Sửa hằng số hoặc giải thích vì sao không sửa, ĐỪNG để lệch.")
    else:
        print("  Khớp hằng số đang ship.")


if __name__ == "__main__":
    main(sys.argv)
