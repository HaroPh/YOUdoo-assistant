"""Thuật toán bảng PDF — module LÁ, chỉ nhận lưới `list[list]`, không biết
`pdfplumber`. Tách khỏi `parse.py` vì `parse.py` phải giữ nguyên logic
`heading_level()`/furniture cho trang không bảng — trộn hai việc vào một
hàm sẽ khó chứng minh "trang không bảng không đổi gì" (spec §3.1)."""
import re

from .xlsx_header import is_column_index_row


def _to_text(v) -> str:
    return str(v).strip() if v is not None else ""


def _anchor(row: list) -> str:
    """Nội dung ô KHÔNG RỖNG đầu tiên của hàng — dùng làm điểm neo đối chiếu
    hai chế độ trích xuất. Không dùng chỉ số vị trí thuần: chế độ mặc định
    có thể thiếu hàng ở GIỮA danh sách, làm lệch chỉ số của mọi hàng sau đó
    (spec §3.3)."""
    for c in row:
        t = _to_text(c)
        if t:
            return t
    return ""


def merge_table_rows(default_rows: list[list], text_rows: list[list]
                     ) -> list[tuple[list, bool]]:
    """Gộp hai chế độ trích xuất `pdfplumber` của MỘT bảng.

    Neo bằng `_anchor()`. Nhìn trước 1 bước để phân biệt "text có hàng thừa"
    (mặc định làm mất hàng vắt trang — spec đo 194/210) với ca đối xứng hiếm
    "mặc định có hàng thừa". Khi neo trống ở CẢ HAI (ô đầu rỗng cả hai chế
    độ) coi là khớp theo vị trí — chấp nhận rủi ro lệch hiếm, ghi nhận là
    giới hạn đã biết."""
    i, j = 0, 0
    out: list[tuple[list, bool]] = []
    while i < len(default_rows) or j < len(text_rows):
        if i >= len(default_rows):
            out.append((text_rows[j], True))
            j += 1
            continue
        if j >= len(text_rows):
            out.append((default_rows[i], False))
            i += 1
            continue
        if _anchor(default_rows[i]) == _anchor(text_rows[j]):
            out.append((default_rows[i], False))
            i += 1
            j += 1
            continue
        # Nhìn trước: text có hàng thừa ở j (mặc định làm mất) hay mặc định
        # có hàng thừa ở i (đối xứng, hiếm)?
        if (j + 1 < len(text_rows)
                and _anchor(default_rows[i]) == _anchor(text_rows[j + 1])):
            out.append((text_rows[j], True))
            j += 1
            continue
        if (i + 1 < len(default_rows)
                and _anchor(default_rows[i + 1]) == _anchor(text_rows[j])):
            out.append((default_rows[i], False))
            i += 1
            continue
        # Không tìm được điểm neo trước — không đoán thêm, ưu tiên chế độ
        # mặc định (ô đầy đủ hơn) và tiến cả hai con trỏ.
        out.append((default_rows[i], False))
        i += 1
        j += 1
    return out


_SO_LIEU_THUAN_RE = re.compile(r"^\d[\d.,]*\d$|^\d$")


def _la_so_lieu_thuan(v) -> bool:
    return bool(_SO_LIEU_THUAN_RE.match(_to_text(v)))


def split_header_body(rows: list[list]) -> tuple[list[list], list[list], bool]:
    """Tách khối HEADER (có thể nhiều dòng) khỏi THÂN bảng — spec §3.4.

    Bốn nhánh, THEO THỨ TỰ ưu tiên cho mỗi hàng CHƯA vào thân:
      1. `is_column_index_row` (TÁI DÙNG từ `xlsx_header.py`, không viết lại)
         → header. Kiểm TRƯỚC nhánh 2 vì một hàng đánh số cột cũng có ô số
         thuần nhưng KHÔNG BAO GIỜ là dữ liệu.
      2. Có ô không rỗng khớp mẫu SỐ LIỆU THUẦN (toàn chữ số + dấu phân
         cách, không lẫn chữ) → THÂN bắt đầu từ đây, mọi dòng sau (kể cả
         không khớp nhánh nào) đều là thân. Kiểm TRƯỚC nhánh "đa số ô rỗng"
         (BUG THẬT tìm ra 2026-09-04 khi nghiệm thu `bieumau_bctc_hopnhat.pdf`:
         trên bảng biểu mẫu THƯA — nhãn + mã số có giá trị, các cột số tiền
         để TRỐNG — MỌI hàng thân thật chỉ có 2/5 ô khác rỗng, tức <50%. Nếu
         kiểm "đa số ô rỗng" trước, mọi hàng thân thật đó rơi vào header và
         KHÔNG BAO GIỜ chạm nhánh số liệu thuần — `column_names()` sau đó
         nối nhãn của nhiều hàng dữ liệu không liên quan thành một tên cột
         rác, đắp vào các hàng thân thật phía sau. Ưu tiên tín hiệu số liệu
         thuần trước đóng đúng lỗ hổng này mà không đổi hành vi 16 ca gốc
         của Task 1 — không ca nào trong các fixture đó vừa có ô số liệu
         thuần vừa đa số ô rỗng cùng lúc).
      3. Đa số ô (>50%) rỗng/None → header (dòng đệm/nhãn phụ thưa, KHÔNG có
         ô số liệu thuần nào — nếu có đã rẽ vào nhánh 2 ở trên).
      4. Không khớp gì ở trên → VẪN header (mặc định — chỉ nhánh 2 mới
         chuyển sang thân, đừng đọc "không khớp" thành "vậy là thân").

    CHỐT AN TOÀN: nếu duyệt hết mà không hàng nào từng khớp nhánh 2 (0 hàng
    thân) — bảng toàn chữ, không có tín hiệu số nào — bảng không được biến
    mất. Còn >=2 hàng: dòng đầu làm header, phần còn lại làm thân. Đúng 1
    hàng: hàng đó tự nó thành thân, header rỗng (không có gì đứng trước nó
    để làm header)."""
    header: list[list] = []
    body: list[list] = []
    started = False
    for row in rows:
        if started:
            body.append(row)
            continue
        if is_column_index_row(row):
            header.append(row)
            continue
        if any(_la_so_lieu_thuan(c) for c in row):
            started = True
            body.append(row)
            continue
        filled = sum(1 for c in row if _to_text(c))
        if filled < len(row) / 2:
            header.append(row)
            continue
        header.append(row)
    if not body:
        if len(rows) <= 1:
            return [], rows[:], True
        return rows[:1], rows[1:], True
    return header, body, False


def column_names(header_rows: list[list]) -> list[str]:
    """Tên cột = nối các ô KHÔNG RỖNG theo cột, theo thứ tự dòng header.

    LOẠI các hàng ĐÁNH SỐ CỘT khỏi phép nối — '1'/'2'/'3' không phải mảnh
    tên cột, ghép chúng vào sẽ sinh tên rác kiểu "TÀI SẢN 1"."""
    label_rows = [r for r in header_rows if not is_column_index_row(r)]
    if not label_rows:
        return []
    n_cols = len(label_rows[0])
    names = []
    for c in range(n_cols):
        parts = [_to_text(row[c]) for row in label_rows
                 if c < len(row) and _to_text(row[c])]
        names.append(" ".join(parts) if parts else f"Cột {c + 1}")
    return names


def row_to_text(row: list, columns: list[str]) -> str:
    """'<Tên cột>: <giá trị> | ...' — mỗi hàng tự mang tên cột vì nó sẽ đứng
    RIÊNG một chunk (spec §3.4), khác `_bang_thanh_text` của .docx (cả bảng
    một block nên header đứng dòng đầu là đủ ngữ cảnh)."""
    parts = []
    for i, val in enumerate(row):
        name = columns[i] if i < len(columns) else f"Cột {i + 1}"
        parts.append(f"{name}: {_to_text(val)}")
    return " | ".join(parts)


def checksum_gap(body_rows: list[list]) -> str | None:
    """`None` nếu cột đầu KHÔNG phải số đếm liên tục (im lặng ĐÚNG — đa số
    bảng không có checksum, vd `bieumau_bctc_hopnhat.pdf`) hoặc liền mạch.
    Chuỗi mô tả nếu đứt đoạn — đi tiếp vào `Warning` qua cầu đã có ở KH2
    (spec §3.6)."""
    if not body_rows:
        return None
    col0 = [_to_text(row[0]) if row else "" for row in body_rows]
    if not all(re.fullmatch(r"\d+", v) for v in col0):
        return None
    nums = [int(v) for v in col0]
    gaps = [f"{nums[i]}→{nums[i + 1]}" for i in range(len(nums) - 1)
            if nums[i + 1] - nums[i] != 1]
    if not gaps:
        return None
    return f"cột đếm đứt đoạn tại: {', '.join(gaps)}"
