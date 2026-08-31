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
# VÒNG SỬA 1 (2026-08-31): sau khi thêm `is_column_index_row` + đổi cách
# `data_ratio` xử lý biểu mẫu trống (xem hai hàm bên dưới), đo LẠI toàn bộ
# lưới trên cùng 23 sheet. Bảng đo đầy đủ nằm trong task-3-report.md, mục
# "Vòng sửa 1".
#
# SCAN_LIMIT=15 GIỮ NGUYÊN: quét sâu hơn (20/25/30...) vẫn không giúp gì ở
# vòng đo lại — hàng tiêu đề thật của phần lớn sheet nằm trong 15 hàng đầu, và
# sheet "DV" (hàng tiêu đề thật ở hàng 30, nhiều bảng minh hoạ nhỏ xếp chồng
# TRƯỚC bảng chính) vẫn sai ở MỌI scan_limit đã thử — quét sâu hơn chỉ đổi
# NÓ SAI THEO CÁCH KHÁC, không bao giờ tự sửa đúng.
#
# MIN_SCORE=0.99, NÂNG từ 0.95 (giá trị chốt vòng đầu): đo lại cho thấy dải
# phẳng tốt nhất bây giờ là [0.99, 1.0] (đúng=6 sai=11 None=6), thay vì dải
# [0.95, 0.964] trước đó — vì hai fix của vòng sửa 1 đã loại một phần lỗi
# "dò sai" (từ 19/23 giảm còn 17/23 ở MIN_SCORE=0.5 thấp; xem báo cáo), nên
# NGƯỠNG PHẢI ĐẨY LÊN THEO để tận dụng phần cải thiện đó — các hàng tiêu đề
# thật CÒN LẠI (6 ca đúng) đều đạt đúng 1.0. Chọn 0.99 (không phải 1.0) để có
# biên an toàn trước sai số dấu phẩy động của phép `min(1.0, score+bonus)`.
#
# KẾT QUẢ SAU VÒNG SỬA 1 VẪN CHƯA ĐẠT 20/23 chủ dự án kỳ vọng (đúng=6 sai=11
# None=6). 11 ca sai còn lại là những dạng KHÁC với hai lỗi vòng 1 đã sửa —
# liệt kê đầy đủ kèm bằng chứng trong task-3-report.md mục "Vòng sửa 1 — 11
# ca còn sai". Theo đúng chỉ đạo, KHÔNG tinh chỉnh thêm ở đây; báo cáo và chờ
# quyết định.
SCAN_LIMIT = 15
MIN_SCORE = 0.99

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


# Vòng sửa 1 (2026-08-31, phản hồi trên task-3-report.md) — nhận diện HÀNG
# ĐÁNH SỐ CỘT của biểu mẫu hành chính Việt Nam: số trần ("1", "2"), số trong
# ngoặc đơn/vuông ("(1)", "[2]"), một chữ cái đơn ("A".."D"), hay biểu thức
# tham chiếu kiểu "(3)=(1)/(2)". Cả năm dạng đều PASS `_looks_like_label`
# (ngắn, không phải số kiểu, không phải công thức $-range) nên trước vòng sửa
# này chúng cạnh tranh ngang hàng tiêu đề THẬT — đo trên 23 sheet cho thấy đây
# là nguyên nhân của phần lớn ca "dò sai" (vd `PB CPTT - TK 242`, `Bảng Kê Mua
# Vào`: hàng `(1)(2)(3)...` ăn điểm bằng hoặc hơn hàng `STT`/tên cột thật).
# CHỈ 1-2 chữ số: chặn để năm "2026"/"2025" của header hai tầng (fixture
# BCTC) không bị coi là đánh số cột — cả 3 ví dụ của chính spec vòng sửa 1
# ("1", "2", "10") đều <=2 chữ số, chưa từng thấy chỉ số cột 3+ chữ số.
_BARE_NUM_RE = re.compile(r"^\d{1,2}(\.\d+)?$")
_PAREN_NUM_RE = re.compile(r"^\(\d+\)$")
_BRACKET_NUM_RE = re.compile(r"^\[\d+\]$")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-z]$")
# Biểu thức tham chiếu: bất kỳ chuỗi nào CHỈ gồm chữ số/ngoặc/toán tử/dấu
# chấm-phẩy/khoảng trắng, có ÍT NHẤT một chữ số. RỘNG HƠN mẫu ban đầu
# `^\(\d+\)=\(\d+\)op\(\d+\)$` — sổ TT200 có công thức lồng ngoặc VUÔNG lẫn
# ngoặc TRÒN, ví dụ "(3)=(1)/[(2)*12/1000]" (khấu hao TSCĐ theo tháng), không
# khớp mẫu chỉ-ngoặc-tròn ban đầu nên từng lọt lưới và thắng hàng tiêu đề thật
# (sheet `KH TSCĐ - TK 214`, vòng sửa 1 lần đo lại). Không có CHỮ CÁI nào
# trong tập ký tự cho phép nên không thể khớp nhầm một nhãn cột thật.
_REF_EXPR_RE = re.compile(r"^(?=.*[()\[\]=])[\d()\[\]=+\-*/.,\s]+$")

# Bằng chứng dương khi hàng ĐÁNH SỐ CỘT nằm NGAY DƯỚI ứng viên: quy ước rất
# mạnh trong biểu mẫu hành chính VN (tên cột / (1)(2)(3) / dữ liệu), đáng tin
# hơn `data_ratio`. Cộng thêm điểm, giới hạn trần ở 1.0.
_COLUMN_INDEX_BONUS = 0.15


def _looks_like_column_index(v) -> bool:
    """Một Ô đánh số cột: số trần, "(n)", "[n]", một chữ cái đơn, hoặc biểu
    thức tham chiếu kiểu "(3)=(1)/(2)" hay "(3)=(1)/[(2)*12/1000]"."""
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).strip()
    if not s:
        return False
    return bool(_BARE_NUM_RE.match(s) or _PAREN_NUM_RE.match(s)
                or _BRACKET_NUM_RE.match(s) or _SINGLE_LETTER_RE.match(s)
                or _REF_EXPR_RE.match(s))


def is_column_index_row(row: list) -> bool:
    """Hàng ĐÁNH SỐ CỘT — KHÔNG BAO GIỜ là hàng tiêu đề THẬT, dù mọi ô đều
    "trông như nhãn" theo `_looks_like_label` (đúng NGỮ PHÁP — ngắn, không
    phải số kiểu, không phải công thức $-range — nhưng sai NGỮ NGHĨA: chúng
    đánh số CHÚ THÍCH cho hàng tiêu đề bên trên, không phải TÊN cột).

    Tiêu chí: PHẦN LỚN (>50%) ô có giá trị khớp một trong các dạng đánh số
    cột. Dùng "phần lớn" chứ không phải "mọi ô", vì một số biểu mẫu chừa vài
    ô trống hoặc lẫn một ô chú thích ngắn giữa các ô đánh số."""
    filled = [c for c in row if c is not None and str(c).strip() != ""]
    if len(filled) < 2:
        return False
    idx_like = sum(1 for c in filled if _looks_like_column_index(c))
    return idx_like / len(filled) > 0.5


def _score_row(rows: list[list], i: int) -> float:
    """Điểm cao khi hàng i trông như nhãn VÀ các hàng dưới trông như dữ liệu."""
    row = rows[i]
    filled = [c for c in row if c is not None and str(c).strip() != ""]
    if len(filled) < 2:
        return 0.0
    if is_column_index_row(row):
        # Dứt khoát 0 điểm, KHÔNG phụ thuộc MIN_SCORE — hàng đánh số cột
        # không bao giờ được chọn làm tiêu đề (vòng sửa 1, mục 2a).
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
    # Mỗi hàng dưới có "trông như dữ liệu" hay không, dùng CÙNG một ngưỡng
    # (>= một nửa số ô đã lấp của hàng ứng viên) cho cả hai việc: đếm data_ratio
    # VÀ quyết định "biểu mẫu có trống hay không". Không dùng "còn ô nào khác
    # None" làm tiêu chí trống (bản đầu vòng sửa 1 từng vậy) — sheet `DM KH`
    # có một cột danh sách thả xuống ẩn ("Tính chất" = "KH") lặp lại ở MỌI
    # hàng "trống", khiến kiểm tra thô đó luôn thấy "có dữ liệu" dù 8/9 cột
    # thật của khách hàng đều rỗng. Ngưỡng CÙNG PHE với `data_ratio` mới đúng:
    # một ô lạc duy nhất không bao giờ vượt ngưỡng "một nửa số ô", nên hàng đó
    # vẫn bị coi là "không đóng góp dữ liệu thật".
    data_bar = max(2, len(filled) // 2)
    below_looks_like_data = [
        sum(1 for c in r if _looks_like_data(c)) >= data_bar for r in below
    ]
    if not below or not any(below_looks_like_data):
        # Biểu mẫu TRỐNG (chưa điền số liệu, vd `DM KH`/`DM NCC`/`DMHH`) vẫn
        # có hàng tiêu đề THẬT — không được trừng phạt bằng data_ratio=0. Bỏ
        # hẳn thành phần này và CHUẨN HOÁ LẠI trọng số hai thành phần còn lại
        # (0.45+0.25=0.70 → chia lại cho 0.70) thay vì nhân với 0 (vòng sửa 1,
        # mục 2c).
        score = (0.45 * label_ratio + 0.25 * contiguity) / 0.70
    else:
        data_ratio = sum(below_looks_like_data) / len(below)
        score = 0.45 * label_ratio + 0.25 * contiguity + 0.30 * data_ratio

    if i + 1 < len(rows) and is_column_index_row(rows[i + 1]):
        # Bằng chứng dương: hàng đánh số cột NGAY DƯỚI (vòng sửa 1, mục 2b).
        score = min(1.0, score + _COLUMN_INDEX_BONUS)

    return score


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
