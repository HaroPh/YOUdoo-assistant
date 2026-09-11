"""Đo quy tắc KÍCH HOẠT VLM trên lưới Tesseract đệm sẵn — Q2, Q3, Q6, Q9 của spec
`2026-09-11-ocr-bac-3-vlm-kiem-so-hoc-design.md`. KHÔNG gọi API nào.

Câu hỏi thật của lát này: "số học có vouch được cho Tesseract trên trang TỐT
không?" — nếu không (≈0 ràng buộc đánh giá được vì mã số đọc sai 21%), bảo vệ
Q4 không có răng và ngưỡng dấu tiếng Việt phải gánh chính.

Mỗi trang ảnh của corpus scan (`tmp-docs/ocr-scan-that` + SCID, cùng danh sách
với `calibrate_table.py`) cho một dòng:

    tệp  trang  conf  dấu  |T|  coded  form  PASS FAIL NA  vouch  xoay  tiêu đề

- `dấu`  — tỉ lệ token chữ (≥ 3 ký tự) mang dấu tiếng Việt: tín hiệu lọc thô
           của spec. Đo cả trên ĐỐI CHỨNG biết-tốt: trang PDF vector rasterise
           rồi OCR (cùng đường tự-nuôi). Hai phân bố chồng nhau ở chỗ trang cờ
           nằm → thước không tách (Q9).
- `|T|`  — số token khớp `MONEY` trên lưới (Tesseract đọc được bao nhiêu số).
- `coded`— số hàng có ô mã số hợp dạng (`grid_rows`); "-" = không có cột mã số.
- `form` — bảng thông tư số học chọn (`so_hoc.select_form`), "-" = không bảng.
- `vouch`— `so_hoc.tesseract_vouched`: ≥ 1 PASS và 0 FAIL → KHÔNG gọi VLM.
- `xoay` — góc `read_page` đã xoay theo OSD (0 = không; tầng tài liệu đọc cả hai
           hướng, giữ hướng conf cao hơn). Q6: bao nhiêu trang là xoay.
- `tiêu đề` — tín hiệu TIÊU ĐỀ báo cáo chính ở 1/3 đầu trang (fold dấu): B01
           "bảng cân đối kế toán"/"báo cáo tình hình tài chính", B02 "kết quả
           hoạt động/kinh doanh", B03 "lưu chuyển tiền"; loại trang có "bản
           thuyết minh". Đo 2026-09-11 lần 1: 50/281 trang, đúng mọi trang báo
           cáo chính của 6 tài liệu; trang khớp ≥ 2 loại là văn xuôi (mục lục,
           ý kiến kiểm toán) → loại. Đây là ứng viên quy tắc kích hoạt: tiêu đề
           đúng MỘT loại VÀ không vouch → gọi VLM.

Q3 riêng: trên DVT tr7/8/9 (đáp án tay TT 107), bao nhiêu ô tiền của đáp án
xuất hiện NGUYÊN VĂN trong token Tesseract — chất lượng Tesseract làm oracle.

Chạy:  python -m tools.calibrate_vlm_trigger [so_trang_toi_da]
Kết quả ghi vào `tools/calibrate_vlm_trigger_result.txt`.
"""
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter

import pdfplumber

from src.ocr import engine, grid_rows, so_hoc, table
from src.ocr.document import _anh_cua_trang, read_page
from src.ocr.engine import OCR_DPI

THU_MUC_SCAN = r"D:\Youdoo\tmp-docs\ocr-scan-that"
SCAN_THEM = [r"D:\downloads\SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf"]
# Đối chứng biết-tốt: PDF vector của corpus luật, rasterise rồi OCR (đường tự-nuôi).
THU_MUC_DOI_CHUNG = "src/rag/seed/law"
SO_TRANG_DOI_CHUNG = 30
DAP_AN = "tests/fixtures/ocr_bang_that"
KET_QUA = os.path.join(os.path.dirname(__file__), "calibrate_vlm_trigger_result.txt")

_CHU = re.compile(r"^[^\W\d_]{3,}$")
TITLES = {"B01": r"bang can doi ke toan|bao cao tinh hinh tai chinh",
          "B02": r"ket qua hoat dong|ket qua kinh doanh",
          "B03": r"luu chuyen tien"}
_NOTES = ("ban thuyet minh", "thuyet minh bao cao")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def title_kinds(text: str) -> list[str]:
    """Loại báo cáo chính mà 1/3 đầu trang gọi tên; [] nếu là trang thuyết minh."""
    lines = text.split(chr(10))
    top = fold(" ".join(lines[: max(10, len(lines) // 3)]))
    if any(k in top for k in _NOTES):
        return []
    return [k for k, rx in TITLES.items() if re.search(rx, top)]


def _co_dau(tok: str) -> bool:
    for ch in tok:
        d = unicodedata.decomposition(ch)
        if d or ch in "đĐ":
            return True
    return False


def ti_le_dau(text: str) -> tuple[float, int]:
    toks = [t for t in re.split(r"\s+", text) if _CHU.match(t)]
    if not toks:
        return 0.0, 0
    return sum(_co_dau(t) for t in toks) / len(toks), len(toks)


def _words(kq):
    return [w for r in kq.regions for w in r.words]


def do_trang(path, pageno):
    kq = read_page(path, pageno)
    grid = next((r.grid for r in kq.regions if r.grid), [])
    dau, n_tok = ti_le_dau(kq.text)
    money = sum(1 for w in _words(kq) if table.MONEY.match(w["t"] if isinstance(w, dict) else w.text))
    gr = grid_rows.rows_from_grid(grid)
    row = {"tep": os.path.basename(path)[:8], "trang": pageno, "conf": kq.mean_conf,
           "dau": dau, "tok": n_tok, "T": money, "coded": gr.coded_rows if gr else 0,
           "form": "-", "PASS": 0, "FAIL": 0, "NA": 0, "vouch": False,
           "xoay": kq.rotation, "tieu_de": "+".join(title_kinds(kq.text)) or "-"}
    if gr:
        a = so_hoc.assess_page(gr.rows, gr.value_columns, strict_absent=False)
        vs = Counter(e.verdict for e in a.report.evaluations)
        row.update(form=a.form.mau if a.form else "-", PASS=vs["PASS"], FAIL=vs["FAIL"],
                   NA=vs["NA"], vouch=so_hoc.tesseract_vouched(a.report))
    return row


def q3_oracle():
    """Ô tiền đáp án DVT có mặt nguyên văn trong token Tesseract?"""
    out = []
    for p in sorted(glob.glob(os.path.join(DAP_AN, "DVT_*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        kq = read_page(d["duong_dan_goc"], d["trang_pdf"])
        toks = {(w["t"] if isinstance(w, dict) else w.text) for w in _words(kq)}
        cols = [c for c in d["cot"] if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")]
        so = [h[c] for h in d["hang"] for c in cols if isinstance(h[c], int)]
        in_ = [f"({abs(v):,})".replace(",", ".") if v < 0 else f"{v:,}".replace(",", ".") for v in so]
        khop = sum(s in toks for s in in_)
        ma = [h["ma_so"] for h in d["hang"] if h["ma_so"]]
        ma_khop = sum(m in toks for m in ma)
        out.append(f"  {os.path.basename(p):22} ô tiền có mặt {khop}/{len(in_)}  mã số có mặt {ma_khop}/{len(ma)}")
    return out


def main(argv):
    gioi_han = int(argv[1]) if len(argv) > 1 else 10**9
    tep_scan = sorted(glob.glob(os.path.join(THU_MUC_SCAN, "*.pdf"))) + [
        p for p in SCAN_THEM if os.path.isfile(p)]
    dong = []
    n = 0
    for p in tep_scan:
        with pdfplumber.open(p) as pdf:
            trangs = [i + 1 for i, pg in enumerate(pdf.pages) if not (pg.extract_text() or "").strip()]
        for pageno in trangs:
            if n >= gioi_han:
                break
            dong.append(do_trang(p, pageno))
            n += 1
            print(f"  {dong[-1]['tep']} p{pageno:3} vouch={dong[-1]['vouch']} coded={dong[-1]['coded']}", flush=True)

    # Đối chứng biết-tốt
    doi_chung = []
    for p in sorted(glob.glob(os.path.join(THU_MUC_DOI_CHUNG, "*.pdf"))):
        if len(doi_chung) >= SO_TRANG_DOI_CHUNG:
            break
        with pdfplumber.open(p) as pdf:
            for pageno in range(1, min(len(pdf.pages), 4) + 1):
                if len(doi_chung) >= SO_TRANG_DOI_CHUNG:
                    break
                kq = engine.ocr_image(_anh_cua_trang(p, pageno, OCR_DPI))
                dau, n_tok = ti_le_dau(kq.text)
                if n_tok >= 30:
                    doi_chung.append(dau)

    L = []
    L.append("Q2 — bộ kiểm trên lưới Tesseract đệm sẵn, từng trang ảnh")
    L.append(f"{'tệp':9}{'tr':>4}{'conf':>6}{'dấu':>6}{'tok':>5}{'|T|':>5}{'coded':>6}  {'form':10}{'PASS':>5}{'FAIL':>5}{'NA':>4}  vouch  xoay  tiêu đề")
    for r in dong:
        L.append(f"{r['tep']:9}{r['trang']:>4}{r['conf']:>6.1f}{r['dau']:>6.2f}{r['tok']:>5}{r['T']:>5}"
                 f"{r['coded'] or '-':>6}  {r['form']:10}{r['PASS']:>5}{r['FAIL']:>5}{r['NA']:>4}  "
                 f"{'CÓ' if r['vouch'] else '-':5}  {r['xoay'] or '-':>4}  {r['tieu_de']}")
    co_bang = [r for r in dong if r["coded"] >= so_hoc.MIN_CODED_ROWS]
    vouch = [r for r in dong if r["vouch"]]
    khong = [r for r in dong if not r["vouch"]]
    L.append("")
    L.append(f"TỔNG: {len(dong)} trang ảnh; có cột mã số: {len(co_bang)}; vouched: {len(vouch)}; "
             f"không vouched: {len(khong)}")
    L.append(f"  trong số trang có cột mã số: vouched {sum(r['vouch'] for r in co_bang)}/{len(co_bang)}; "
             f"có ≥1 FAIL: {sum(r['FAIL'] > 0 for r in co_bang)}; 0 ràng buộc đánh giá được (PASS+FAIL=0): "
             f"{sum(r['PASS'] + r['FAIL'] == 0 for r in co_bang)}")
    forms = Counter(r["form"] for r in co_bang)
    L.append(f"  bảng chọn: {dict(forms)}")
    L.append("")
    L.append("Q6 — xoay theo OSD (read_page đọc cả hai hướng, giữ hướng conf cao hơn)")
    xoay = Counter(r["xoay"] for r in dong)
    L.append(f"  góc đã xoay: {dict(xoay)}  (trang xoay có cột mã số: "
             f"{sum(1 for r in dong if r['xoay'] and r['coded'] >= so_hoc.MIN_CODED_ROWS)})")
    L.append("")
    L.append("Quy tắc kích hoạt ứng viên: tiêu đề đúng MỘT loại báo cáo chính, không vouch")
    mot = [r for r in dong if r["tieu_de"] != "-" and "+" not in r["tieu_de"]]
    nhieu = [r for r in dong if "+" in r["tieu_de"]]
    L.append(f"  tiêu đề một loại: {len(mot)} trang — vouched {sum(r['vouch'] for r in mot)}, "
             f"CẦN VLM {sum(not r['vouch'] for r in mot)}; tiêu đề ≥ 2 loại (loại): {len(nhieu)}")
    L.append(f"  vouched nhưng KHÔNG có tiêu đề (tiêu đề bỏ sót trang tốt): "
             f"{[(r['tep'], r['trang']) for r in vouch if r['tieu_de'] == '-']}")
    L.append(f"  cần VLM theo tệp: {dict(Counter(r['tep'] for r in mot if not r['vouch']))}")
    L.append("")
    L.append("Q9 — tỉ lệ dấu tiếng Việt: scan vs đối chứng vector rasterise")

    def _phan_bo(xs):
        xs = sorted(xs)
        if not xs:
            return "(rỗng)"
        q = lambda f: xs[min(len(xs) - 1, int(f * len(xs)))]
        return f"n={len(xs)} min={xs[0]:.2f} p10={q(.1):.2f} p50={q(.5):.2f} p90={q(.9):.2f} max={xs[-1]:.2f}"
    L.append(f"  đối chứng (vector→ảnh→OCR): {_phan_bo(doi_chung)}")
    L.append(f"  scan vouched:               {_phan_bo([r['dau'] for r in vouch if r['tok'] >= 30])}")
    L.append(f"  scan KHÔNG vouched:         {_phan_bo([r['dau'] for r in khong if r['tok'] >= 30])}")
    L.append(f"  scan không có cột mã số:    {_phan_bo([r['dau'] for r in dong if r['coded'] < so_hoc.MIN_CODED_ROWS and r['tok'] >= 30])}")
    L.append("")
    L.append("Q3 — Tesseract làm oracle trên DVT (đáp án tay TT 107)")
    L += q3_oracle()
    txt = "\n".join(L)
    print(txt)
    with open(KET_QUA, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main(sys.argv)
