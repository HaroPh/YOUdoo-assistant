"""Dò hàng tiêu đề của một bảng Excel — spec 2026-08-29 mục 5.2.

Module LÁ: chỉ nhận lưới giá trị ô, không biết openpyxl, không biết DB.

Vì sao cần: `parse_xlsx` từng lấy hàng ĐẦU TIÊN có chữ làm nhãn cột. Trên sổ
kế toán thật (81 sheet có dữ liệu) điều đó cho 0/81 sheet đúng — nhãn cột hoá
ra là tên công ty, tên tài liệu, số phiếu, câu hướng dẫn, và một lần là chuỗi
công thức `$B$7:$M$100`.
"""
import re
from dataclasses import dataclass

# HIỆU CHỈNH BẰNG ĐO — Task 3 Step 5, trên 23 sheet có đáp án của sổ kế toán
# thật (ô có giá trị "STT" sau strip().upper() đánh dấu hàng tiêu đề đúng).
# Bảng đo đầy đủ nằm trong task-3-report.md.
#
# SCAN_LIMIT=15 GIỮ NGUYÊN giá trị tạm của Task 2: quét sâu hơn (20/25/30...)
# không giúp gì — hàng tiêu đề thật của phần lớn sheet nằm trong 15 hàng đầu,
# và với những sheet KHÔNG nằm trong đó (vd "DV" ở hàng 30), quét sâu hơn chỉ
# tìm thêm hàng NHÁI ở đầu sheet cạnh tranh, không bao giờ tự sửa nổi ca đó.
#
# MIN_SCORE=0.95, NÂNG từ giá trị tạm 0.5: đo cho thấy phần lớn "dò SAI" (19
# trên 23 sheet, ở MIN_SCORE=0.5) là hàng NHÁI được dò với điểm CAO — đặc biệt
# một dạng lặp lại nhiều lần trên sổ kế toán TT200: một hàng "đánh số cột" nằm
# NGAY DƯỚI hàng tiêu đề thật, gồm các ô ngắn kiểu "(1)/(2)/(3)", "[1]/[2]" hay
# chữ cái đơn "A/B/C/D" — những ô này ĐỀU trông như nhãn theo `_looks_like_label`
# nên hàng đó ăn điểm gần như tuyệt đối, ngang hàng tiêu đề thật. Không ngưỡng
# SCAN_LIMIT/MIN_SCORE nào tự phân biệt được HAI hàng đó khi cả hai đều lọt
# vào cửa sổ quét — đây là giới hạn thật của thuật toán chấm điểm hiện tại,
# không phải thứ Step 5 (hiệu chỉnh 2 hằng số) có thể sửa triệt để.
#
# Điều Step 5 LÀM ĐƯỢC: nâng MIN_SCORE lên 0.95 biến 8/19 ca "dò sai" thành
# "trả None" (an toàn, sinh cảnh báo) MÀ KHÔNG mất ca đúng nào trong 4 ca đang
# đúng (điểm hàng tiêu đề thật của cả 4 ca đó đều >= 0.964, và của mọi fixture
# đơn vị Task 2 đều = 1.0). 0.95 nằm giữa một dải phẳng đo được [0.95, 0.964]
# cho cùng kết quả (đúng=4 sai=11 None=8) — chọn đầu dải để có biên an toàn
# trước ngưỡng 0.965 nơi một ca đúng bắt đầu rơi theo.
SCAN_LIMIT = 15
MIN_SCORE = 0.95

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
    phát hiện, đúng lớp lỗi cả spec đi đóng.

    Hoà điểm dùng `>=` (ưu tiên hàng SAU cùng đạt điểm cao nhất), không phải
    `>`. Phát hiện khi nối Task 3: một báo cáo tài chính hai tầng header, sau
    khi trải ô gộp, có thể cho NHIỀU hàng liền nhau cùng đạt điểm tuyệt đối —
    dòng tiêu đề tài liệu (một ô gộp phủ hết bề rộng), hàng nhãn cha ("Quý
    II"/"Lũy kế"), và hàng nhãn con ("2026"/"2025") — vì `_score_row` không
    phân biệt được các hàng CHỈ TOÀN NHÃN xếp chồng nhau. Hàng tiêu đề THẬT
    luôn là hàng SÁT DỮ LIỆU nhất trong nhóm hoà điểm đó, tức hàng có chỉ số
    lớn nhất."""
    best, best_score = None, 0.0
    for i in range(min(scan_limit, len(rows))):
        s = _score_row(rows, i)
        if s >= best_score and s > 0.0:
            best, best_score = i, s
    if best is None or best_score < MIN_SCORE:
        return None
    return HeaderGuess(best, [str(c).strip() if c is not None else ""
                              for c in rows[best]], best_score)


def is_parent_header(row: list) -> bool:
    """Hàng trên hàng tiêu đề có phải MỘT TẦNG HEADER không?

    Tiêu chí: mọi ô có giá trị đều trông như nhãn, VÀ hàng mang từ HAI NHÓM
    giá trị liền kề phân biệt trở lên. "Nhóm liền kề" là dấu vết còn lại của
    một ô gộp NGANG đã được trải: "Quý II" lấp B:C rồi "Lũy kế" lấp D:E cho
    hai nhóm. Một dòng tiêu đề tài liệu (một ô gộp DUY NHẤT phủ hết bề rộng
    hàng, ví dụ "BÁO CÁO TÀI CHÍNH...") chỉ tạo ĐÚNG MỘT nhóm sau khi trải —
    tuy mọi ô đều trông như nhãn, nó không phải header cha.

    KHÔNG dùng "phần lớn ô rỗng" làm tiêu chí (bản đầu của hàm này từng vậy):
    một cột nhãn dọc bên trái ("Chỉ tiêu") thường được gộp DỌC qua cả hai
    tầng header (ví dụ Excel `A3:A4`), nên sau khi trải ô gộp, CỘT ĐÓ lấp đầy
    ở CẢ hàng cha lẫn hàng con — hàng cha không còn "phần lớn rỗng" nữa dù
    vẫn là header cha thật. Đếm NHÓM PHÂN BIỆT thay vì đếm Ô RỖNG mới sống
    sót qua trường hợp này (fixture BCTC hai tầng, cột A gộp dọc).

    Ghép nhầm một dòng dữ liệu vào nhãn cột còn tệ hơn không ghép: nó tạo ra
    nhãn sai một cách tự tin.
    """
    filled = [c for c in row if c is not None and str(c).strip() != ""]
    if not filled or not all(_looks_like_label(c) for c in filled):
        return False
    groups = 0
    prev = None
    for c in row:
        v = str(c).strip() if c is not None and str(c).strip() != "" else None
        if v is not None and v != prev:
            groups += 1
        prev = v
    return groups >= 2


def compose_two_tier(parent_row: list, child_labels: list[str]) -> list[str]:
    """Ghép `"cha · con"` khi có tầng cha; nếu không, trả nguyên nhãn con."""
    if not is_parent_header(parent_row):
        return list(child_labels)
    out: list[str] = []
    for i, child in enumerate(child_labels):
        parent = parent_row[i] if i < len(parent_row) else None
        p = str(parent).strip() if parent is not None else ""
        c = (child or "").strip()
        if p and c and p != c:
            out.append(f"{p} · {c}")
        else:
            out.append(c or p)
    return out
