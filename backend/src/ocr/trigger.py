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

from . import grid_rows, so_hoc

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


@dataclass(frozen=True)
class Decision:
    kind: str | None                 # B01/B02/B03 hoặc None
    call_vlm: bool
    reason: str
    tesseract: so_hoc.PageAssessment | None = None
    grid_rows: grid_rows.GridRows | None = None


def decide(text: str, grid: list[list[str]]) -> Decision:
    """Một trang đọc-từ-ảnh có nên đi VLM không. Không có tác dụng phụ."""
    kind = statement_kind(text)
    if kind is None:
        n = len(title_kinds(text))
        ly_do = "không có tiêu đề báo cáo chính" if n == 0 else f"tiêu đề {n} loại — văn xuôi"
        return Decision(kind=None, call_vlm=False, reason=ly_do)
    gr = grid_rows.rows_from_grid(grid) if grid else None
    if gr is None:
        return Decision(kind=kind, call_vlm=True,
                        reason=f"tiêu đề {kind}, Tesseract không dựng được cột mã số")
    a = so_hoc.assess_page(gr.rows, gr.value_columns, strict_absent=False)
    if so_hoc.tesseract_vouched(a.report):
        return Decision(kind=kind, call_vlm=False, tesseract=a, grid_rows=gr,
                        reason=f"tiêu đề {kind}, số học vouch cho Tesseract "
                               f"(bảng {a.form.mau if a.form else '-'})")
    vs = [e.verdict for e in a.report.evaluations]
    return Decision(kind=kind, call_vlm=True, tesseract=a, grid_rows=gr,
                    reason=f"tiêu đề {kind}, số học KHÔNG vouch cho Tesseract "
                           f"(PASS {vs.count('PASS')}, FAIL {vs.count('FAIL')}, NA {vs.count('NA')})")
