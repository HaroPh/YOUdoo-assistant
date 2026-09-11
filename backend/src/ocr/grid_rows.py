"""Lưới Tesseract bậc 2 (`Region.grid`, list[list[str]]) -> hàng dạng dict cho
bộ kiểm số học (`so_hoc.classify_rows`).

Vì sao cần: spec VLM bậc 3 nói kích hoạt thật là "số học KHÔNG vouch được cho
Tesseract" — trước khi gọi VLM, dựng hàng từ lưới Tesseract, chạy CÙNG bộ kiểm;
≥ 1 PASS và 0 FAIL thì không gọi. Việc này cần một ánh xạ lưới → hàng có cột
`ma_so` và cột tiền. Lưới bậc 2 KHÔNG biết cột nào là gì; nó chỉ có toạ độ.

Cách nhận cột, tất định, không hằng số rút từ không khí ngoài "đa số":
- cột mã số = cột có nhiều ô khớp `^\\d{2,3}[a-z]?\\.?$` nhất (dấu chấm đuôi là
  lỗi OCR hay gặp: `123.`, `140.`);
- cột tiền = các cột BÊN PHẢI cột mã số có ô khớp `MONEY`; giữ cột nào có số ô
  tiền ≥ 1/3 cột tiền nhất — trên SCID tr12 cho đúng 2 cột, dấu "-" hay trôi
  sang cột kề thì gán về cột tiền GẦN NHẤT;
- nhãn = nối các ô giữa cột đánh dấu (cột 0) và cột mã số.

Trả None khi không có cột mã số đủ (dưới `so_hoc.MIN_CODED_ROWS` ô khớp) —
trang không phải bảng chỉ tiêu, không có gì để kiểm.

Không sửa một ký tự nào của Tesseract: `12I` ở lại `12I` (→ `bad_ma_so`),
`25900585)` ở lại (→ `BAD`). Sửa là việc của tầng có bằng chứng; đây chỉ xếp ô.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import so_hoc, table

_MA_SO_CELL_RE = re.compile(r"^(\d{2,3}[a-z]?)\.?$")
_MARKER_CELL_RE = re.compile(r"^([A-Z]\s*-|[IVXL]+\.?|\d{1,2}[.;:]?|[a-z][).]|-)$")
# Cột tiền phải có ít nhất tỉ lệ này số ô tiền so với cột tiền đông nhất, để
# một ô tiền lạc (số trang, ngày tháng) không thành cột.
_VALUE_COL_MIN_SHARE = 1 / 3


@dataclass(frozen=True)
class GridRows:
    rows: list[dict]
    value_columns: list[str]        # tên cột giá trị theo header nếu tìm được, không thì "c<idx>"
    ma_so_col: int
    value_cols_idx: list[int]
    coded_rows: int                 # số hàng có ô mã số hợp dạng — thước "trang có bảng chỉ tiêu"


def _col_count(grid: list[list[str]], pred) -> list[int]:
    n = max((len(r) for r in grid), default=0)
    out = [0] * n
    for r in grid:
        for j, c in enumerate(r):
            if c and pred(c.strip()):
                out[j] += 1
    return out


def rows_from_grid(grid: list[list[str]], *, header_names: list[str] | None = None) -> GridRows | None:
    if not grid:
        return None
    ma_counts = _col_count(grid, lambda c: bool(_MA_SO_CELL_RE.match(c)))
    if not ma_counts or max(ma_counts) < so_hoc.MIN_CODED_ROWS:
        return None
    ma_col = max(range(len(ma_counts)), key=lambda j: (ma_counts[j], -j))

    money_counts = _col_count(grid, lambda c: bool(table.MONEY.match(c)))
    right = [j for j in range(ma_col + 1, len(money_counts)) if money_counts[j] > 0]
    if not right:
        return None
    nguong = max(money_counts[j] for j in right) * _VALUE_COL_MIN_SHARE
    value_idx = [j for j in right if money_counts[j] >= nguong]

    names = []
    for k, j in enumerate(value_idx):
        ten = header_names[j].strip() if header_names and j < len(header_names) else ""
        names.append(ten if ten and not re.match(r"^Cột \d+$", ten) else f"c{j}")
    if len(set(names)) != len(names):
        names = [f"c{j}" for j in value_idx]

    rows: list[dict] = []
    coded = 0
    for r in grid:
        cells = [c.strip() for c in r] + [""] * (len(money_counts) - len(r))
        m = _MA_SO_CELL_RE.match(cells[ma_col]) if ma_col < len(cells) else None
        ma_so = m.group(1) if m else None
        if ma_so:
            coded += 1
        muc = cells[0] if cells and _MARKER_CELL_RE.match(cells[0]) else None
        nhan_cells = cells[(1 if muc is not None else 0):ma_col]
        nhan = " ".join(c for c in nhan_cells if c)
        row: dict = {"muc": muc, "chi_tieu": nhan, "ma_so": ma_so, "thuyet_minh": None}
        # Ô tiền / gạch bên phải mã số gán về cột giá trị gần nhất.
        gan: dict[int, list[str]] = {j: [] for j in value_idx}
        for j in range(ma_col + 1, len(cells)):
            c = cells[j]
            if not c:
                continue
            if table.MONEY.match(c) or c in ("-", "–", "—"):
                gan[min(value_idx, key=lambda v: abs(v - j))].append(c)
        for name, j in zip(names, value_idx):
            xs = gan[j]
            if not xs:
                # Không có ô: hàng nhãn thuần hay Tesseract mất số. Để None
                # cho hàng không mã số (label); hàng có mã số thì để "" -> BAD
                # (không đọc được) — KHÔNG được coi là "-".
                row[name] = None if ma_so is None else ""
            elif len(xs) == 1:
                row[name] = xs[0]
            else:
                row[name] = " ".join(xs)              # hai ô cùng cột -> BAD ở parse_money
        rows.append(row)
    return GridRows(rows=rows, value_columns=names, ma_so_col=ma_col,
                    value_cols_idx=value_idx, coded_rows=coded)
