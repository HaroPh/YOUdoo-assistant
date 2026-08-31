"""Dò hàng tiêu đề của một bảng Excel — spec 2026-08-29 mục 5.2.

Module LÁ: chỉ nhận lưới giá trị ô, không biết openpyxl, không biết DB.

Vì sao cần: `parse_xlsx` từng lấy hàng ĐẦU TIÊN có chữ làm nhãn cột. Trên sổ
kế toán thật (81 sheet có dữ liệu) điều đó cho 0/81 sheet đúng — nhãn cột hoá
ra là tên công ty, tên tài liệu, số phiếu, câu hướng dẫn, và một lần là chuỗi
công thức `$B$7:$M$100`.
"""
import re
from dataclasses import dataclass

# GIÁ TRỊ TẠM — Task 3 Step 5 thay bằng số đo trên 23 sheet đã có đáp án
# (cần dữ liệu đã trải ô gộp, việc trải nằm ở Task 3). Không hiệu chỉnh ở
# Task 2 — xem ghi chú trong task-2-brief.md.
SCAN_LIMIT = 15
MIN_SCORE = 0.5

_FORMULA = re.compile(r"^\s*\$?[A-Z]{1,3}\$?\d+\s*:\s*\$?[A-Z]{1,3}\$?\d+\s*$")
_LABEL_MAX_LEN = 40


@dataclass(frozen=True)
class HeaderGuess:
    row_index: int
    labels: list[str]
    score: float


def _looks_like_label(v) -> bool:
    """Một nhãn cột: chuỗi ngắn, không phải số, không phải công thức, không
    phải một câu. `"Chọn tháng cần in ở đây -->"` là câu hướng dẫn, không
    phải nhãn — sheet `BẢNG TH N-X-T` từng lấy nó làm nhãn cột."""
    if v is None or isinstance(v, (int, float)):
        return False
    s = str(v).strip()
    if not s or len(s) > _LABEL_MAX_LEN:
        return False
    if _FORMULA.match(s) or s.startswith("$"):
        return False
    if s.startswith("#"):            # #N/A, #REF!
        return False
    return True


def _looks_like_data(v) -> bool:
    return isinstance(v, (int, float)) or (v is not None and str(v).strip() != "")


def _score_row(rows: list[list], i: int) -> float:
    """Điểm cao khi hàng i trông như nhãn VÀ các hàng dưới trông như dữ liệu."""
    row = rows[i]
    filled = [c for c in row if c is not None and str(c).strip() != ""]
    if len(filled) < 2:
        return 0.0
    label_ratio = sum(1 for c in filled if _looks_like_label(c)) / len(filled)
    if label_ratio == 0.0:
        # Không ô nào trông như nhãn (vd. toàn số) — chắc chắn không phải
        # hàng tiêu đề, dù liền mạch và hàng dưới trông như dữ liệu đến đâu.
        return 0.0

    # Liền mạch: các ô có giá trị nên nằm sát nhau, không rải rác.
    idx = [j for j, c in enumerate(row) if c is not None and str(c).strip() != ""]
    span = idx[-1] - idx[0] + 1
    contiguity = len(idx) / span if span else 0.0

    below = rows[i + 1: i + 4]
    if not below:
        return 0.0
    data_ratio = sum(
        1 for r in below
        if sum(1 for c in r if _looks_like_data(c)) >= max(2, len(filled) // 2)
    ) / len(below)

    return 0.45 * label_ratio + 0.25 * contiguity + 0.30 * data_ratio


def find_header(rows: list[list], scan_limit: int = SCAN_LIMIT) -> HeaderGuess | None:
    """Trả về hàng tiêu đề, hoặc None.

    None là kết quả HỢP LỆ: nó là tín hiệu để tầng trên phát một CẢNH BÁO CÓ
    TÊN. Đoán bừa một hàng còn tệ hơn — nhãn sai một cách tự tin thì không ai
    phát hiện, đúng lớp lỗi cả spec đi đóng."""
    best, best_score = None, 0.0
    for i in range(min(scan_limit, len(rows))):
        s = _score_row(rows, i)
        if s > best_score:
            best, best_score = i, s
    if best is None or best_score < MIN_SCORE:
        return None
    return HeaderGuess(best, [str(c).strip() if c is not None else ""
                              for c in rows[best]], best_score)
