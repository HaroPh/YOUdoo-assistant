"""Dò hàng tiêu đề của một bảng Excel — spec 2026-08-29 mục 5.2.

Module LÁ: chỉ nhận lưới giá trị ô, không biết openpyxl, không biết DB.

Vì sao cần: `parse_xlsx` từng lấy hàng ĐẦU TIÊN có chữ làm nhãn cột. Trên sổ
kế toán thật (81 sheet có dữ liệu) điều đó cho 0/81 sheet đúng — nhãn cột hoá
ra là tên công ty, tên tài liệu, số phiếu, câu hướng dẫn, và một lần là chuỗi
công thức `$B$7:$M$100`.
"""
import re
from dataclasses import dataclass

# HIỆU CHỈNH BẰNG ĐO — trên 23 sheet có đáp án của sổ kế toán thật.
#
# ĐÁP ÁN (sửa ở vòng 2): hàng tiêu đề đúng là vùng hàng LIÊN TIẾP chứa ô "STT"
# (so sau `strip().upper()`). Ô "STT" của các biểu mẫu này thường bị GỘP DỌC
# qua 2-3 hàng, nên sau khi trải ô gộp thì MỌI hàng trong vùng đều mang "STT" —
# vòng 1 dùng quy tắc "hàng ĐẦU TIÊN chứa STT" nên chấm oan 4 ca mà bộ dò
# thực ra chọn đúng hơn cả đáp án. Mọi số dưới đây đo bằng đáp án ĐÃ SỬA.
#
# SCAN_LIMIT=15 GIỮ NGUYÊN từ hai vòng trước. Đo lại với công thức mới cho
# thấy dải `sai==0` trải rộng từ scan 7 đến 18, và trong dải đó `đúng` tăng
# đều theo độ sâu: 10-12 → 16, 13-17 → 17, 18 → 18. Nhưng 18 là một MŨI NHỌN
# ĐÚNG MỘT ĐIỂM (19 và 20 lại sinh ca sai), và nó chỉ vớt thêm đúng một sheet
# `TỜ KHAI THUẾ GTGT` có hàng tiêu đề nằm ở chỉ số 17 — chọn 18 là hiệu chỉnh
# vừa khít MỘT sheet ngay cạnh vách đá. 15 nằm giữa cao nguyên phẳng 13-17.
#
# MIN_SCORE=0.92, HẠ từ 0.99 của vòng 1. Sau khi bốn cơ chế bên dưới loại
# được các hàng "trông như nhãn nhưng không phải tiêu đề", điểm không còn phải
# gánh việc phân biệt đó nữa, nên ngưỡng hạ được để vớt các hàng tiêu đề THẬT
# bị điểm thấp. Biên trên 23 sheet có đáp án: hàng tiêu đề đúng thấp nhất đạt
# 0.9250 (`PL 43-2022-QH15`), hàng cao nhất mà bộ dò PHẢI từ chối đạt 0.9135
# (`Data` hàng 0). Khe hở rộng 0.0115.
#
# CÁI GIÁ ĐÃ BIẾT của việc hạ ngưỡng, đo bằng phép so TỪNG SHEET base↔head
# trên CẢ 81 sheet (phép đo vòng sửa 2 đã THIẾU, review độc lập chỉ ra): hai
# sheet chuyển từ `None` (an toàn) sang một câu trả lời TỰ TIN SAI —
#   `BHBB`  hàng 13 (0.9500) — một dòng gạch đầu dòng VĂN XUÔI trong văn bản
#           quy định bảo hiểm; sheet này không có bảng nào cả.
#   `Data2` hàng 0  (0.9375) — dòng chú thích của một sheet phụ trợ.
# Cả hai đều không có ô `STT` nên nằm NGOÀI 23 sheet có đáp án.
#
# VÌ SAO KHÔNG NÂNG NGƯỠNG ĐỂ LOẠI CHÚNG — đã thử 0.96 và ĐO, rồi RÚT LẠI:
# ở đúng mức 0.9500000000 có CẢ hàng SAI của `BHBB` LẪN hai hàng tiêu đề
# ĐÚNG (`SỔ CT VT-HH` hàng 5, `PB CPMH` hàng 3 — cùng dạng header hai tầng,
# đã soi tay). Chúng BẰNG ĐIỂM NHAU tuyệt đối, nên KHÔNG ngưỡng nào tách nổi:
# nâng lên 0.96 loại được 2 ca sai nhưng giết luôn 3 ca đúng (`SỔ CT VT-HH`,
# `PB CPMH`, và `PL 43-2022-QH15` ở 0.9250). Đổi 3 lấy 2 là lỗ.
#
# Muốn đóng `BHBB` phải có CƠ CHẾ nhận ra VĂN XUÔI (câu có dấu chấm cuối,
# nhiều từ) chứ không phải một con số ngưỡng — và cơ chế đó lại chỉ hiệu chỉnh
# được trên đúng một sheet, nên để lại làm việc tương lai có đo đàng hoàng.
#
# KẾT QUẢ trên 23 sheet có đáp án: đúng=17 sai=0 None=6
# (baseline trước vòng sửa 2: đúng=10 sai=7 None=6).
SCAN_LIMIT = 15
MIN_SCORE = 0.92

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


def _cell_text(v) -> str:
    return str(v).strip() if v is not None else ""


def _filled_columns(row: list) -> set[int]:
    """Chỉ số các cột CÓ giá trị của một hàng."""
    return {j for j, c in enumerate(row) if _cell_text(c) != ""}


def _filled_count(row: list) -> int:
    return sum(1 for c in row if _cell_text(c) != "")


def _distinct_groups(row: list) -> int:
    """Số NHÓM giá trị liền kề phân biệt của một hàng.

    Dấu vết còn lại của ô gộp NGANG sau khi trải: "Quý II" lấp B:C rồi "Lũy
    kế" lấp D:E cho hai nhóm; một dòng tiêu đề tài liệu (một ô gộp DUY NHẤT
    phủ hết bề rộng) chỉ cho MỘT nhóm."""
    groups, prev = 0, None
    for c in row:
        v = _cell_text(c) or None
        if v is not None and v != prev:
            groups += 1
        prev = v
    return groups


# Vòng sửa 1 (2026-08-31) — nhận diện HÀNG ĐÁNH SỐ CỘT của biểu mẫu hành chính
# Việt Nam: số trần ("1", "2"), số trong ngoặc đơn/vuông ("(1)", "[2]"), một
# chữ cái đơn ("A".."D"), hay biểu thức tham chiếu kiểu "(3)=(1)/(2)". Cả năm
# dạng đều PASS `_looks_like_label` (ngắn, không phải số kiểu, không phải công
# thức $-range) nên trước vòng sửa đó chúng cạnh tranh ngang hàng tiêu đề THẬT.
# CHỈ 1-2 chữ số: chặn để năm "2026"/"2025" của header hai tầng không bị coi
# là đánh số cột — cả 3 ví dụ của spec ("1", "2", "10") đều <=2 chữ số.
_BARE_NUM_RE = re.compile(r"^\d{1,2}(\.\d+)?$")
_PAREN_NUM_RE = re.compile(r"^\(\d+\)$")
_BRACKET_NUM_RE = re.compile(r"^\[\d+\]$")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-z]$")
# Biểu thức tham chiếu: bất kỳ chuỗi nào CHỈ gồm chữ số/ngoặc/toán tử/dấu
# chấm-phẩy/khoảng trắng, có ÍT NHẤT một trong `()[]=`. RỘNG HƠN mẫu ban đầu
# `^\(\d+\)=\(\d+\)op\(\d+\)$` — sổ TT200 có công thức lồng ngoặc VUÔNG lẫn
# ngoặc TRÒN, ví dụ "(3)=(1)/[(2)*12/1000]" (khấu hao TSCĐ theo tháng). Không
# có CHỮ CÁI nào trong tập ký tự cho phép nên không thể khớp nhầm nhãn thật.
_REF_EXPR_RE = re.compile(r"^(?=.*[()\[\]=])[\d()\[\]=+\-*/.,\s]+$")

# Bằng chứng dương khi hàng ĐÁNH SỐ CỘT nằm NGAY DƯỚI ứng viên: quy ước rất
# mạnh trong biểu mẫu hành chính VN (tên cột / (1)(2)(3) / dữ liệu), đáng tin
# hơn `data_ratio`. Cộng thêm điểm, giới hạn trần ở 1.0.
_COLUMN_INDEX_BONUS = 0.15

# Chuỗi tối thiểu các ô LIỀN KỀ, PHÂN BIỆT, đều là ký hiệu cột thì đủ để kết
# luận cả hàng là hàng đánh số cột. Đo trên 23 sheet: dải `sai==0 & đúng=17`
# trải từ 2 đến 6, hỏng ở 7 (mất 1 ca đúng) và 8 (`PB CPTT - TK 242` sai lại).
# Chọn 3 — nằm giữa dải, và ba ký hiệu liền nhau đã đủ hiếm để không ngẫu nhiên.
_MIN_INDEX_RUN = 3

# Ngưỡng KHỚP CỘT tối thiểu giữa hàng ứng viên và thân bảng ngay dưới nó.
# Đo trên 23 sheet: hàng tiêu đề THẬT thấp nhất đạt 0.5833 (`TT THUẾ TNDN`
# hàng 5), còn hai hàng mà cổng này PHẢI chặn đạt 0.0330 (`BẢNG TÍNH THUẾ
# TNCN` hàng 8 — mục La Mã 2 ô) và 0.2361 (`TỜ KHAI THUẾ GTGT` hàng 4 — ô
# tick biểu mẫu). Chọn 0.40, gần đúng trung điểm khe hở [0.2361, 0.5833];
# dải giữ nguyên kết quả là [0.36, 0.58].
_MIN_ALIGNMENT = 0.40

# Cổng ĐA BẢNG: một bảng khác ở phía dưới, rộng gấp ngần này lần bảng vừa
# chọn và cũng đạt điểm tối đa, nghĩa là sheet chứa NHIỀU bảng và bộ dò không
# có cách nào biết bảng nào là bảng chính. Đo trên 23 sheet: cổng chỉ kích
# hoạt ở đúng sheet `DV` (bảng chính rộng 12 ô nằm dưới một bảng ví dụ 3 ô,
# tỉ lệ 4x), và kết quả không đổi với mọi hệ số trong [1.5, 3.0] — chọn 2.0
# giữa dải phẳng đó.
_RIVAL_WIDTH_FACTOR = 2.0
# Trần số hàng quét khi tìm bảng đối thủ: sheet `Data` có 1000 hàng, quét hết
# là lãng phí mà không đổi kết luận.
_RIVAL_SCAN_LIMIT = 200
_SCORE_EPS = 1e-9


def _looks_like_index_symbol(v) -> bool:
    """KÝ HIỆU cột theo nghĩa CHẶT: chuỗi hoá rồi mới so khớp, nên giới hạn
    "số trần 1-2 chữ số" áp cho CẢ ô số lẫn ô chuỗi.

    Khác `_looks_like_column_index` đúng một điểm: không có nhánh tắt "mọi
    `int`/`float` đều là ký hiệu cột". Nhánh tắt đó làm giới hạn 1-2 chữ số
    thành VÔ NGHĨA với ô số — mà openpyxl trả ô số dưới dạng `int`/`float`,
    tức gần như MỌI ô số thật đều đi qua nhánh tắt.

    Vì sao tách làm hai hàm thay vì sửa thẳng `_looks_like_column_index`:
    nhánh tắt đó có từ vòng sửa 1 và tiêu chí TỈ LỆ (>50%) cùng
    `_COLUMN_INDEX_BONUS` đã được hiệu chỉnh CÙNG nó. Bỏ nó trên toàn cục thì
    hai sheet thật `CĐTK` và `Thẻ giá thành DV` RỜI KHỎI hàng tiêu đề đúng
    (4 → 3, đo trên 81 sheet). Nên chỉ tiêu chí CHUỖI LIỀN KỀ — thứ vòng sửa
    2 mới thêm — dùng bản chặt này; phần còn lại giữ nguyên hành vi cũ.
    """
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    return bool(_BARE_NUM_RE.match(s) or _PAREN_NUM_RE.match(s)
                or _BRACKET_NUM_RE.match(s) or _SINGLE_LETTER_RE.match(s)
                or _REF_EXPR_RE.match(s))


def _looks_like_column_index(v) -> bool:
    """Một Ô đánh số cột: số trần, "(n)", "[n]", một chữ cái đơn, hoặc biểu
    thức tham chiếu kiểu "(3)=(1)/(2)" hay "(3)=(1)/[(2)*12/1000]".

    CẢNH BÁO — nhánh tắt `isinstance(v, (int, float))` coi MỌI ô số là ký
    hiệu cột, kể cả `24000000`. Đó là NỢ CÓ SẴN từ vòng sửa 1, được giữ vì
    tiêu chí tỉ lệ và `_COLUMN_INDEX_BONUS` đã hiệu chỉnh cùng nó (xem
    `_looks_like_index_symbol`). Hệ quả còn lại: một hàng dữ liệu toàn số
    PHÂN BIỆT (vd `1 | Chiết khấu | 5211 | 100 | 200 | 300`) vẫn bị tiêu chí
    tỉ lệ nhận nhầm là hàng đánh số cột. Không gây hại đo được (hàng như vậy
    có `label_ratio` rất thấp nên vốn đã không thể thắng), nhưng đừng đọc
    tên hàm rộng hơn thực tế nó làm.
    """
    if isinstance(v, (int, float)):
        return True
    return _looks_like_index_symbol(v)


def _index_symbol_run(row: list) -> int:
    """Chuỗi DÀI NHẤT các ô liền kề vừa là ký hiệu cột vừa KHÁC NHAU.

    Hai ràng buộc, cả hai đều cần:

    LIỀN KỀ — vòng sửa 2, ca `PB CPTT - TK 242` / `KH TSCĐ - TK 214`: hàng
    `['A','C','B','D','(1)','(2)','(3)=(1)/(2)', 'SỐ PHÂN BỔ…', 'Tháng 1',
    …, 'Tháng 12']` rộng 24 ô, 7 ô đầu THUẦN ký hiệu cột nhưng 16 ô sau là
    nhãn tháng THẬT, nên tỉ lệ toàn hàng chỉ 1/3 — dưới ngưỡng "phần lớn" của
    `is_column_index_row`, lọt lưới và hoà điểm với hàng tiêu đề thật.

    PHÂN BIỆT — nếu không đòi, ba ô `0 | 0 | 0` của một hàng DỮ LIỆU kế toán
    (đầy số 0) cũng thành "chuỗi ký hiệu cột", và hàng dữ liệu bị chấm 0 điểm
    thì không sao, nhưng hàng NGAY TRÊN nó lại được cộng `_COLUMN_INDEX_BONUS`
    oan — đúng thứ đã đẩy `TT THUẾ TNDN` chọn hàng 10 thay vì hàng 5. Một
    hàng đánh số cột thật thì LIỆT KÊ các chỉ số khác nhau, không lặp lại một
    giá trị.

    Dùng `_looks_like_index_symbol` (bản CHẶT), KHÔNG dùng
    `_looks_like_column_index`. Bản đầu của hàm này dùng bản lỏng, và vì bản
    lỏng coi MỌI ô số là ký hiệu cột, ba ô số PHÂN BIỆT bất kỳ cũng thành một
    "chuỗi ký hiệu" — kể cả một hàng TIÊU ĐỀ THẬT mang nhãn năm dạng SỐ
    (`['Chỉ tiêu','Ghi chú',2020,2021,2022,…]`, hình dạng rất phổ biến trong
    báo cáo tài chính), khiến `_score_row` chấm nó 0 điểm DỨT KHOÁT. Đó là
    hồi quy do chính vòng sửa 2 gây ra, review độc lập bắt được.
    """
    best = run = 0
    seen: set[str] = set()
    for c in row:
        s = _cell_text(c)
        if s and _looks_like_index_symbol(c):
            if s in seen:
                run, seen = 1, {s}
            else:
                run += 1
                seen.add(s)
            best = max(best, run)
        else:
            run, seen = 0, set()
    return best


def is_column_index_row(row: list) -> bool:
    """Hàng ĐÁNH SỐ CỘT — KHÔNG BAO GIỜ là hàng tiêu đề THẬT, dù mọi ô đều
    "trông như nhãn" theo `_looks_like_label` (đúng NGỮ PHÁP — ngắn, không
    phải số kiểu, không phải công thức $-range — nhưng sai NGỮ NGHĨA: chúng
    đánh số CHÚ THÍCH cho hàng tiêu đề bên trên, không phải TÊN cột).

    Tiêu chí, MỘT TRONG HAI:
      1. PHẦN LỚN (>50%) ô có giá trị mang một GIÁ TRỊ ký hiệu cột PHÂN BIỆT.
         Đếm giá trị phân biệt chứ không đếm Ô (vòng sửa 2): hàng dữ liệu kế
         toán `1.0 | Chiết khấu thương mại | 5211.0 | 0 | 0 | 0` có 4/6 ô
         "trông như ký hiệu" nhưng chỉ 3 giá trị phân biệt (1.0, 5211.0, 0),
         tức 3/6 = 50%, không vượt ngưỡng — trong khi `(1)|(2)|(3)|(4)|(5)`
         có 5 giá trị phân biệt trên 5 ô. Hàng đánh số cột LIỆT KÊ, không lặp.
      2. Có >= `_MIN_INDEX_RUN` ô LIỀN KỀ, PHÂN BIỆT, đều là ký hiệu cột,
         BẤT KỂ tỉ lệ toàn hàng — xem `_index_symbol_run`.
    """
    filled = [c for c in row if _cell_text(c) != ""]
    if len(filled) < 2:
        return False
    distinct_index_like = {_cell_text(c) for c in filled
                           if _looks_like_column_index(c)}
    if len(distinct_index_like) / len(filled) > 0.5:
        return True
    return _index_symbol_run(row) >= _MIN_INDEX_RUN


def _column_alignment(row: list, below: list) -> float | None:
    """Hàng ứng viên PHỦ được bao nhiêu phần các cột của thân bảng dưới nó.

    Trung bình, trên từng hàng thân, của `|cột(ứng viên) ∩ cột(thân)| /
    |cột(thân)|`. Trả None khi không có hàng thân nào có giá trị để đối chiếu.

    Đây là tín hiệu KẾT CẤU mà `label_ratio`/`contiguity` không có: một hàng
    tiêu đề THẬT phải đặt nhãn ĐÚNG TRÊN các cột mà dữ liệu chiếm. Vòng sửa 2
    thêm nó vì hai lớp hàng giả mạo đều đạt điểm tuyệt đối theo công thức cũ
    mà lại lệch hẳn cột với thân bảng: mục La Mã 2 ô (`I | CÁ NHÂN CƯ TRÚ`
    của `BẢNG TÍNH THUẾ TNCN`, phủ 3,3% cột thân) và ô tick biểu mẫu
    (`[02] Lần đầu: | X | [03] Bổ sung lần thứ:` của `TỜ KHAI THUẾ GTGT`,
    23,6%). Cả hai "trông như nhãn" hoàn hảo; chỉ vị trí cột tố cáo chúng.
    """
    cols = _filled_columns(row)
    ratios = []
    for r in below:
        body_cols = _filled_columns(r)
        if body_cols:
            ratios.append(len(cols & body_cols) / len(body_cols))
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


def _score_row(rows: list[list], i: int) -> float:
    """Điểm cao khi hàng i trông như nhãn VÀ các hàng dưới trông như dữ liệu."""
    row = rows[i]
    filled = [c for c in row if _cell_text(c) != ""]
    if len(filled) < 2:
        return 0.0
    if is_column_index_row(row):
        # Dứt khoát 0 điểm, KHÔNG phụ thuộc MIN_SCORE — hàng đánh số cột
        # không bao giờ được chọn làm tiêu đề (vòng sửa 1, mục 2a).
        return 0.0
    if _distinct_groups(row) < 2:
        # MỘT nhóm duy nhất sau khi trải ô gộp = một ô gộp phủ hết bề rộng
        # hàng, tức DÒNG TIÊU ĐỀ / CHÚ THÍCH của tài liệu, không phải hàng
        # nhãn cột. `is_parent_header` đã dùng đúng phép đếm này từ Task 3;
        # vòng sửa 2 áp nó cho CẢ `_score_row`, vì thiếu nó thì "Kỳ tính
        # thuế: Quý I năm 2022" (trải 9 ô) và "1. Hàng hoá, dịch vụ mua vào…"
        # của `Bảng Kê Mua Vào` cùng đạt 1.0 rồi thắng hàng tiêu đề thật.
        return 0.0
    label_ratio = sum(1 for c in filled if _looks_like_label(c)) / len(filled)
    if label_ratio == 0.0:
        # Không ô nào trông như nhãn (vd. toàn số) — chắc chắn không phải
        # hàng tiêu đề, dù liền mạch và hàng dưới trông như dữ liệu đến đâu.
        return 0.0

    # Liền mạch: các ô có giá trị nên nằm sát nhau, không rải rác.
    idx = sorted(_filled_columns(row))
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
    if any(below_looks_like_data):
        # CÓ thân bảng thật để đối chiếu vị trí cột — mới áp cổng khớp cột.
        # Biểu mẫu trống không có gì để đối chiếu nên phải miễn, nếu không
        # `DM KH`/`DM NCC`/`DMHH` mất luôn hàng tiêu đề hoàn hảo của chúng.
        alignment = _column_alignment(row, below)
        if alignment is not None and alignment < _MIN_ALIGNMENT:
            return 0.0
        data_ratio = sum(below_looks_like_data) / len(below)
        score = 0.45 * label_ratio + 0.25 * contiguity + 0.30 * data_ratio
    else:
        # Biểu mẫu TRỐNG (chưa điền số liệu, vd `DM KH`/`DM NCC`/`DMHH`) vẫn
        # có hàng tiêu đề THẬT — không được trừng phạt bằng data_ratio=0. Bỏ
        # hẳn thành phần này và CHUẨN HOÁ LẠI trọng số hai thành phần còn lại
        # (0.45+0.25=0.70 → chia lại cho 0.70) thay vì nhân với 0 (vòng sửa 1,
        # mục 2c).
        score = (0.45 * label_ratio + 0.25 * contiguity) / 0.70

    if i + 1 < len(rows) and is_column_index_row(rows[i + 1]):
        # Bằng chứng dương: hàng đánh số cột NGAY DƯỚI (vòng sửa 1, mục 2b).
        score = min(1.0, score + _COLUMN_INDEX_BONUS)

    return score


def _has_wider_rival_table(rows: list[list], best_index: int,
                           best_score: float) -> bool:
    """Phía dưới có một bảng KHÁC, rộng hơn hẳn, cũng đạt điểm tối đa không?

    Sheet `DV` xếp CHỒNG nhiều bảng: một bảng ví dụ 3 cột ở hàng 1-2, rồi
    bảng chính 12 cột ở hàng 30-31. Bộ dò chỉ quét `SCAN_LIMIT` hàng đầu nên
    nhìn thấy đúng bảng ví dụ, chấm nó 1.0 và chọn — SAI một cách tự tin, mà
    không `SCAN_LIMIT` nào sửa được (quét sâu hơn chỉ làm hỏng thêm sheet
    khác, đã đo ở cả ba vòng).

    Thuật toán hiện tại không có khái niệm "nhiều bảng trong một sheet", và
    dựng khái niệm đó là một thiết kế lớn hơn phạm vi vòng sửa này. Nhưng
    KHÔNG được để nguyên trạng thái tự tin sai: khi có bằng chứng rằng sheet
    còn một bảng lớn hơn hẳn mà bộ dò không nhìn tới, câu trả lời đúng là
    NHẬN KHÔNG BIẾT (trả None → cảnh báo có tên), đúng nguyên tắc spec
    2026-08-29 mục 4.

    Vì sao đòi RỘNG GẤP `_RIVAL_WIDTH_FACTOR` lần chứ không chỉ "cũng đạt
    điểm tối đa": rất nhiều sheet lặp lại đúng hàng tiêu đề của chính nó ở
    giữa thân (biểu mẫu in nhiều trang — `BẢNG TÍNH LƯƠNG` lặp ở hàng 6-7,
    24-25, 42-43), và có cả hàng chữ ký "(Ký, họ tên)" hay mục La Mã sâu
    trong sheet cũng đạt 1.0. Chặn theo "có đối thủ bất kỳ" biến 5 sheet
    ĐANG ĐÚNG thành None để đổi lấy đúng 1 ca — đo được, và là một cái giá
    tồi. Đòi thêm điều kiện BỀ RỘNG thì cổng chỉ kích hoạt ở đúng ca `DV`.
    """
    limit = min(_RIVAL_SCAN_LIMIT, len(rows))
    if best_index >= limit:
        return False
    scores = [_score_row(rows, j) for j in range(limit)]
    tie_lo = tie_hi = best_index
    while tie_lo - 1 >= 0 and scores[tie_lo - 1] >= best_score - _SCORE_EPS:
        tie_lo -= 1
    while tie_hi + 1 < limit and scores[tie_hi + 1] >= best_score - _SCORE_EPS:
        tie_hi += 1
    needed_width = _RIVAL_WIDTH_FACTOR * _filled_count(rows[best_index])
    return any(scores[j] >= best_score - _SCORE_EPS
               and _filled_count(rows[j]) >= needed_width
               for j in range(limit) if not tie_lo <= j <= tie_hi)


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
    if _has_wider_rival_table(rows, best, best_score):
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
    filled = [c for c in row if _cell_text(c) != ""]
    if not filled or not all(_looks_like_label(c) for c in filled):
        return False
    return _distinct_groups(row) >= 2


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
