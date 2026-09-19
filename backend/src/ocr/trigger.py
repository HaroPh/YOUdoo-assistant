"""Quy tắc KÍCH HOẠT VLM cho một trang đọc-từ-ảnh — tất định, đo được, không
ngưỡng rút từ không khí.

Đo 2026-09-11 trên 281 trang ảnh của 6 báo cáo tài chính scan
(`tools/calibrate_vlm_trigger_result.txt`):

- Tín hiệu **dấu tiếng Việt** (spec đề xuất) KHÔNG tách được trang tốt/xấu:
  vouched p50 = 0,78, không vouched p50 = 0,77, đối chứng vector 0,84. Bác.
- Tín hiệu **tiêu đề báo cáo chính** ở 1/3 đầu trang — Tesseract đọc ĐÚNG dòng
  tiêu đề ngay cả khi thân trang là rác (DVT tr7: "Báo cáo tình hình tài
  chính" đọc đúng, thân 1/8 số đúng) — bắt 50/281 trang, gồm MỌI trang báo cáo
  chính của cả 6 tài liệu. Trang khớp ≥ 2 loại tiêu đề là văn xuôi (mục lục,
  ý kiến kiểm toán nhắc tên cả ba báo cáo) → không kích hoạt. Trang có "bản
  thuyết minh" là trang thuyết minh → không kích hoạt (tầng tổng-ma-trận cho
  chúng là việc sau, spec lát 5).
- **Số học vouch cho Tesseract** (`so_hoc.tesseract_vouched`: ≥ 1 PASS, 0 FAIL
  trên hàng dựng từ lưới Tesseract): 21/52 trang có cột mã số. Trang vouched
  giữ hàng Tesseract, KHÔNG gọi VLM — số học đã bảo lãnh cho số, nhãn vẫn của
  Tesseract, cảnh báo trang nói rõ.

Quy tắc: gọi VLM ⇔ tiêu đề đúng MỘT loại báo cáo chính VÀ số học không vouch
được cho Tesseract. Trên corpus đo: 50 trang tiêu đề − 8 trang ≥ 2 loại − 19
vouched ≈ 23 lượt VLM / 6 tài liệu (~4 mỗi báo cáo), gồm DVT tr7/8/9 — đúng
ba trang bài toán này sinh ra để giải.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import grid_rows, so_hoc, table

# Tiêu đề in trên trang của ba báo cáo chính, theo cả TT 200/99 (doanh nghiệp)
# lẫn TT 107 (hành chính sự nghiệp). So trên chuỗi bỏ dấu, chữ thường.
STATEMENT_TITLES = {
    "B01": r"bang can doi ke toan|bao cao tinh hinh tai chinh",
    "B02": r"ket qua hoat dong|ket qua kinh doanh",
    "B03": r"luu chuyen tien",
}
_NOTES_MARKERS = ("ban thuyet minh", "thuyet minh bao cao")
# Tiêu đề nằm ở phần đầu trang; lấy 1/3 số dòng nhưng không dưới 10 dòng để
# trang ít dòng (bảng ngắn) vẫn đủ letterhead.
_TOP_MIN_LINES = 10


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def title_kinds(text: str) -> list[str]:
    """Loại báo cáo chính mà phần đầu trang gọi tên. [] nếu không có hoặc là
    trang thuyết minh. ≥ 2 phần tử = văn xuôi nhắc tên nhiều báo cáo."""
    lines = text.split("\n")
    top = fold(" ".join(lines[: max(_TOP_MIN_LINES, len(lines) // 3)]))
    if any(k in top for k in _NOTES_MARKERS):
        return []
    return [k for k, rx in STATEMENT_TITLES.items() if re.search(rx, top)]


def statement_kind(text: str) -> str | None:
    kinds = title_kinds(text)
    return kinds[0] if len(kinds) == 1 else None


# Trang báo cáo chính mà Tesseract KHÔNG đọc ra tiêu đề (PGI tr9, SCID tr56, DVT
# tr15) vẫn nhận ra được bằng số hàng có mã số. Đo 2026-09-11 trên 281 trang
# (`tools/calibrate_vlm_trigger_result.txt`): trang không tiêu đề có coded ∈
# {0, 2, 3, 4} — số mục thuyết minh "29.", "30." — trừ đúng ba trang trên
# (9, 12, 19); trang có tiêu đề: 0 hoặc ≥ 9. Khe 4 < x < 9 sạch trên cả corpus;
# 6 nằm giữa khe.
STATEMENT_MIN_CODED_ROWS = 6


def is_statement_page(text: str, grid: list[list[str]]) -> bool:
    """Trang là báo cáo chính (bảng chỉ tiêu có cột mã số) — khác trang thuyết
    minh/văn xuôi. Tiêu đề đúng một loại, HOẶC cột mã số đủ dày. Dùng cho hai
    quyết định: có gọi VLM không (ở đây) và có xé hàng có chữ số thành cột
    không (`parse._khoi_tu_luoi_anh(strict_numeric=…)`)."""
    if statement_kind(text) is not None:
        return True
    gr = grid_rows.rows_from_grid(grid) if grid else None
    return gr is not None and gr.coded_rows >= STATEMENT_MIN_CODED_ROWS


@dataclass(frozen=True)
class Decision:
    kind: str | None                 # B01/B02/B03 hoặc None
    call_vlm: bool
    reason: str
    tesseract: so_hoc.PageAssessment | None = None
    grid_rows: grid_rows.GridRows | None = None
    # Hợp đồng VLM nào dùng cho trang này. `bang_chi_tieu` = prompt gốc (bảng
    # có cột mã số); `thuyet_minh` = prompt tm-v1 (bảng con + cấp + loại tổng).
    # None khi không gọi VLM.
    che_do: str | None = None


# Nhãn hàng tổng của bảng con — cùng tập với `so_hoc.rang_buoc_tu_bang_con`.
def _la_nhan_tong(o: str) -> bool:
    f = " ".join(fold(o).split())
    return f.startswith("tong cong") or f in ("cong", "tong") or f.startswith("cong:")


def co_bang_con_tu_kiem(grid: list[list[str]]) -> bool:
    """Trang có ít nhất một token tiền VÀ một nhãn hàng tổng.

    Đây là điều kiện CẦN để cổng `rang_buoc_tu_bang_con` dựng được ràng buộc —
    không có phép cộng thì VLM đọc xong cũng không kiểm được, và số chưa kiểm
    thì đã có đường `UNVERIFIED_PREFIX` rồi, không đáng một lượt gọi.

    Đo 2026-09-19 trên 309 trang scan (5 PDF + SID): 198 trang có tiền, 203
    trang có nhãn tổng, **152 trang (49,2%) có cả hai**. Đó là trần trên của
    tầng này — nửa còn lại nằm ngoài tầm với của mọi cổng số học.
    """
    co_tien = co_tong = False
    for row in grid or ():
        for o in row:
            o = str(o)
            if not co_tien and table.MONEY_TOKEN.search(o):
                co_tien = True
            if not co_tong and _la_nhan_tong(o):
                co_tong = True
            if co_tien and co_tong:
                return True
    return False


def decide(text: str, grid: list[list[str]]) -> Decision:
    """Một trang đọc-từ-ảnh có nên đi VLM không. Không có tác dụng phụ."""
    kind = statement_kind(text)
    if kind is None:
        # Trang KHÔNG phải báo cáo chính. Trước 2026-09-19 dừng ở đây, nên
        # 256/309 trang scan (thuyết minh) không bao giờ đi VLM. Nay: nếu trang
        # có bảng con TỰ KIỂM ĐƯỢC (tiền + nhãn tổng) thì gọi, ở chế độ tm.
        if co_bang_con_tu_kiem(grid):
            return Decision(kind=None, call_vlm=True, che_do="thuyet_minh",
                            reason="trang thuyết minh có bảng con tự kiểm được "
                                   "(có token tiền và nhãn tổng)")
        n = len(title_kinds(text))
        ly_do = "không có tiêu đề báo cáo chính" if n == 0 else f"tiêu đề {n} loại — văn xuôi"
        if grid:
            ly_do += "; không có bảng con tự kiểm được"
        return Decision(kind=None, call_vlm=False, reason=ly_do)
    gr = grid_rows.rows_from_grid(grid) if grid else None
    if gr is None:
        return Decision(kind=kind, call_vlm=True, che_do="bang_chi_tieu",
                        reason=f"tiêu đề {kind}, Tesseract không dựng được cột mã số")
    a = so_hoc.assess_page(gr.rows, gr.value_columns, strict_absent=False)
    if so_hoc.tesseract_vouched(a.report):
        return Decision(kind=kind, call_vlm=False, che_do="bang_chi_tieu", tesseract=a, grid_rows=gr,
                        reason=f"tiêu đề {kind}, số học vouch cho Tesseract "
                               f"(bảng {a.form.mau if a.form else '-'})")
    vs = [e.verdict for e in a.report.evaluations]
    return Decision(kind=kind, call_vlm=True, che_do="bang_chi_tieu", tesseract=a, grid_rows=gr,
                    reason=f"tiêu đề {kind}, số học KHÔNG vouch cho Tesseract "
                           f"(PASS {vs.count('PASS')}, FAIL {vs.count('FAIL')}, NA {vs.count('NA')})")
