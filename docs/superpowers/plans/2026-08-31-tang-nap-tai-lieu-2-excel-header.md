# Tầng nạp tài liệu — Kế hoạch 2: Excel dò hàng tiêu đề

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nhãn cột của mọi bảng Excel phải là hàng tiêu đề THẬT, không phải dòng đầu tiên có chữ.

**Architecture:** `parse_xlsx` đang lấy `rows[0]` làm tiêu đề. Thay bằng một bộ dò chấm điểm các hàng đầu, mở `read_only=False` để nạp được ô gộp, ghép header hai tầng thành `cha · con`, và **báo ra** sheet nào dò với độ tin cậy thấp thay vì nuốt. Kênh cảnh báo mức sheet — hoãn ở kế hoạch 1 vì chưa có nguồn sinh — nay có nguồn sinh đầu tiên nên dựng ở đây.

**Tech Stack:** Python 3.11, `openpyxl`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-tang-nap-tai-lieu.md` — mục 4 (kênh cảnh báo) và 5.2. Đọc cả hai trước khi bắt đầu.

## Global Constraints

- **Biến và hàm trong MÃ SẢN PHẨM đặt tên tiếng Anh.** Chú thích, docstring, thông điệp lỗi viết tiếng Việt. *(Tên hàm test tiếng Việt là quy ước sẵn có — 184 hàm test hiện dùng kiểu đó.)*
- **Lệnh test luôn kèm** `-m "not integration and not live"`.
- Thư mục làm việc `backend/`; interpreter `d:/Youdoo/backend/.venv/Scripts/python.exe`; mọi lệnh test kèm `PYTHONIOENCODING=utf-8`.
- **Không hằng số rút từ không khí.** Mọi ngưỡng phải hiệu chỉnh trên 23 sheet đã có đáp án và chốt kèm số đo.
- **Kiểm bằng sản phẩm, không kiểm bằng mã thoát.** Mỗi bản sửa phải có phép thử phá chứng minh cổng đỏ được.
- Suite hiện tại: **2257 passed, 1 skipped**.

---

## 1. Đề bài, đo được

`parse_xlsx` lấy `rows[0]` (hàng đầu **có chữ**) làm nhãn cột. Trên sổ kế toán thật `Sổ-Sách-Kế-Toán-Trên-Excel-TT 200 (1).xls.xlsm` (84 sheet, 81 có dữ liệu):

- **0/81 sheet** lấy đúng hàng tiêu đề
- **23 sheet** chứng minh được là sai: hàng chứa `STT` nằm lẫn trong `rows` thay vì ở `columns`
- 58 sheet còn lại không có cột `STT` nên không kết luận bằng máy được, nhưng soi mắt 12 sheet đầu thì nhãn cột hoá ra là: tên công ty, tên tài liệu, số phiếu `PC002`, chữ hướng dẫn `"Chọn tháng cần in ở đây -->"`, và một sheet lấy nhầm **chuỗi công thức Excel** `$B$7:$M$100`

Thiệt hại đi thẳng vào chunk vì `chunk_xlsx_sheets` ghép `f"{col}: {val}"`. Chunk thật hôm nay:

```
[schema] [DM KH] Bảng có các cột: Công ty TNHH Thương mại Dịch vụ Thiên Ưng, , , , , , , , ...
[row 1]  [DM KH] Công ty TNHH Thương mại Dịch vụ Thiên Ưng: Số 19 Đường Nguyễn Trãi, Khương Trung...
[row 4]  [DM KH] Công ty TNHH Thương mại Dịch vụ Thiên Ưng: STT | : Mã | : Tên Khách hàng | ...
```

Hàng tiêu đề thật tụt xuống thành dòng dữ liệu, nhãn của nó là tên công ty. Sheet `DM KH` có bố cục:

```
r1  Công ty TNHH Thương mại...     ← tên công ty
r2  Số 19 Đường Nguyễn Trãi...     ← địa chỉ
r3           DANH SÁCH KHÁCH...    ← tiêu đề tài liệu, ở cột D
r4                    Thông tin ngân hàng   ← header tầng 1 (ô gộp)
r5  STT | Mã | Tên Khách hàng | Mã số thuế | Địa chỉ | Số Tài Khoản | Tên Ngân Hàng
```

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/src/rag/xlsx_header.py` | **Tạo mới.** Dò hàng tiêu đề + ghép header hai tầng. Module lá: chỉ nhận dữ liệu ô, không biết openpyxl, không biết DB. |
| `backend/src/rag/ingest_report.py` | **Sửa.** Thêm `Warning` và danh sách cảnh báo mức sheet/bảng. |
| `backend/src/rag/parse.py` | **Sửa.** `parse_xlsx` mở `read_only=False`, trải ô gộp, gọi bộ dò, trả kèm cảnh báo. |
| `backend/src/rag/ingest.py` | **Sửa.** Gom cảnh báo từ parse vào `IngestReport`. |
| `backend/tests/rag/test_xlsx_header.py` | **Tạo mới.** Bộ dò, thuần dữ liệu, không cần tệp. |
| `backend/tests/rag/test_parse_xlsx_merged.py` | **Tạo mới.** Ô gộp + header hai tầng, fixture tự dựng. |
| `backend/tests/rag/test_canh_bao_sheet.py` | **Tạo mới.** Kênh cảnh báo. |
| `backend/tests/rag/test_xlsx_kho_that.py` | **Tạo mới.** Nghiệm thu `live` trên 81 sheet thật. |

---

### Task 1: Kênh cảnh báo mức sheet

**Files:**
- Modify: `backend/src/rag/ingest_report.py`
- Modify: `backend/tests/rag/test_ingest_report.py`

**Interfaces:**
- Consumes: `IngestReport`, `Rejection` (đã có).
- Produces:
  - `Warning(path: str, where: str, reason: str)` — dataclass frozen. `where` là tên sheet hoặc mô tả vị trí trong tệp.
  - `IngestReport.warnings: list[Warning]` — `field(default_factory=list)`.
  - `merge()` cộng dồn `warnings`.
  - `ok` **KHÔNG** bị ảnh hưởng bởi warnings.
  - `render()` in một khối cảnh báo riêng, gọi tên từng chỗ.

**Vì sao warnings không làm `ok` thành False:** ba trạng thái ở spec mục 4 nói về **tệp**; một sheet dò tiêu đề kém vẫn là một tệp đã nạp. Nếu cảnh báo làm hỏng lượt nạp thì người dùng sẽ tắt cảnh báo, và ta mất luôn tín hiệu.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/rag/test_ingest_report.py`:

```python
from src.rag.ingest_report import IngestReport, Rejection, Warning


def test_canh_bao_khong_lam_bao_cao_that_bai():
    """Cảnh báo mức sheet KHÁC từ chối mức tệp: tệp vẫn nạp được."""
    r = IngestReport(ingested=1, warnings=[Warning("a.xlsx", "DM KH", "tiêu đề độ tin cậy thấp")])
    assert r.ok is True


def test_merge_cong_don_ca_canh_bao():
    a = IngestReport(ingested=1)
    b = IngestReport(warnings=[Warning("b.xlsx", "Sheet2", "lý do")])
    a.merge(b)
    assert [w.where for w in a.warnings] == ["Sheet2"]


def test_hai_bao_cao_rong_khong_dung_chung_danh_sach_canh_bao():
    a, b = IngestReport(), IngestReport()
    a.merge(IngestReport(warnings=[Warning("x", "y", "z")]))
    assert b.warnings == []


def test_render_goi_TEN_tung_cho_bi_canh_bao():
    r = IngestReport(ingested=2, warnings=[
        Warning("so_ke_toan.xlsm", "BK NHẬP - XUẤT", "nhãn cột trông như công thức"),
    ])
    out = r.render()
    assert "so_ke_toan.xlsm" in out
    assert "BK NHẬP - XUẤT" in out
    assert "nhãn cột trông như công thức" in out
```

- [ ] **Step 2: Chạy để thấy ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_report.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'Warning'`

- [ ] **Step 3: Sửa `ingest_report.py`**

```python
@dataclass(frozen=True)
class Warning:
    """Mối lo ở mức SHEET/BẢNG, không phải mức tệp.

    Tệp vẫn được nạp; chỗ đáng ngờ phải được GỌI TÊN chứ không nuốt. Nuốt
    cảnh báo chính là lỗi mà cả spec 2026-08-29 đi đóng.

    Cố ý KHÔNG làm `ok` thành False: ba trạng thái ở spec mục 4 nói về TỆP.
    Nếu cảnh báo làm hỏng lượt nạp, người dùng sẽ tắt nó, và ta mất tín hiệu.
    """
    path: str
    where: str
    reason: str
```

Thêm `warnings: list[Warning] = field(default_factory=list)` vào `IngestReport`, cộng dồn trong `merge()`, và nối vào `render()`:

```python
        for w in self.warnings:
            lines.append(f"  CẢNH BÁO  {w.path} [{w.where}]  —  {w.reason}")
```

Dòng tóm tắt thêm `· cảnh báo {len(self.warnings)}`.

- [ ] **Step 4: Chạy thấy XANH**

Run: lệnh ở Step 2. Expected: PASS.

- [ ] **Step 5: Phép thử phá**

Tạm đổi `ok` thành `return not self.rejected and not self.warnings`.
Run: `... -m pytest tests/rag/test_ingest_report.py::test_canh_bao_khong_lam_bao_cao_that_bai -v -m "not integration and not live"`
Expected: **ĐỎ**. Hoàn tác.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/ingest_report.py backend/tests/rag/test_ingest_report.py
git commit -m "feat(rag): kenh canh bao muc sheet trong bao cao nap"
```

---

### Task 2: Bộ dò hàng tiêu đề — hiệu chỉnh trên dữ liệu thật

**Files:**
- Create: `backend/src/rag/xlsx_header.py`
- Create: `backend/tests/rag/test_xlsx_header.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `HeaderGuess(row_index: int, labels: list[str], score: float)` — dataclass frozen. `row_index` là chỉ số 0-based trong danh sách hàng đã truyền vào.
  - `find_header(rows: list[list], scan_limit: int = ...) -> HeaderGuess | None`
  - `SCAN_LIMIT: int` và `MIN_SCORE: float` — **hai hằng số này chốt bằng đo, xem Step 3**.

**Nguyên tắc chấm điểm** (bạn tự chọn công thức, miễn hiệu chỉnh được):
- ô của hàng ứng viên phần lớn là **chuỗi ngắn, không phải số**
- các ô **liền mạch** (không rải rác một ô rồi trống chục ô)
- các hàng **bên dưới** mang dáng dữ liệu: nhiều ô là số, hoặc kiểu dữ liệu đồng nhất theo cột
- hàng ứng viên **không** trông như công thức (`$B$7:$M$100`), không phải câu hướng dẫn dài

- [ ] **Step 1: Viết test đỏ — dữ liệu thuần, không cần tệp**

Tạo `backend/tests/rag/test_xlsx_header.py`:

```python
# backend/tests/rag/test_xlsx_header.py
"""Bộ dò hàng tiêu đề — spec 2026-08-29 mục 5.2.

Test ở đây thuần dữ liệu (list of list), không đọc tệp: bộ dò phải là module
lá, không biết openpyxl. Nghiệm thu trên sổ kế toán THẬT nằm ở Task 5.
"""
from src.rag.xlsx_header import find_header


def test_bo_qua_dong_tieu_de_tai_lieu_va_dong_trong():
    rows = [
        ["BÁO CÁO TÀI CHÍNH HỢP NHẤT QUÝ II/2026", None, None, None],
        [None, None, None, None],
        ["Chỉ tiêu", "Quý II", "Lũy kế", "Ghi chú"],
        ["Doanh thu thuần", 1250, 2400, None],
        ["Giá vốn hàng bán", 900, 1750, None],
        ["Lợi nhuận gộp", 350, 650, None],
    ]
    g = find_header(rows)
    assert g is not None
    assert g.row_index == 2
    assert g.labels[:2] == ["Chỉ tiêu", "Quý II"]


def test_tim_dung_hang_STT_du_nam_sau_bon_dong_rac():
    rows = [
        ["Công ty TNHH Thương mại Dịch vụ Thiên Ưng", None, None, None, None],
        ["Số 19 Đường Nguyễn Trãi, Thanh Xuân, Hà Nội", None, None, None, None],
        [None, None, None, "DANH SÁCH KHÁCH HÀNG - TK131", None],
        [None, None, None, None, " Thông tin ngân hàng"],
        ["STT", "Mã", "Tên Khách hàng", "Mã số thuế", "Số Tài Khoản"],
        [1, "KH001", "Công ty A", "0101234567", "1234567890"],
        [2, "KH002", "Công ty B", "0107654321", "9876543210"],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 4
    assert g.labels[0] == "STT"


def test_khong_lay_chuoi_cong_thuc_lam_tieu_de():
    """Sheet thật `BK NHẬP - XUẤT` lấy nhầm `$B$7:$M$100` làm nhãn cột."""
    rows = [
        ["$B$7:$M$100", None, None],
        ["Mã hàng", "Số lượng", "Đơn giá"],
        ["VT001", 10, 15000],
        ["VT002", 5, 22000],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1


def test_khong_lay_cau_huong_dan_lam_tieu_de():
    """Sheet thật `BẢNG TH N-X-T` lấy nhầm 'Chọn tháng cần in ở đây -->'."""
    rows = [
        ["  ", "Chọn tháng cần in ở đây -->", "Tháng 01 Năm 2022", "#N/A"],
        ["Mã hàng", "Tồn đầu", "Nhập", "Xuất"],
        ["VT001", 10, 5, 3],
        ["VT002", 0, 20, 15],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 1


def test_sheet_khong_co_tieu_de_nhan_dien_duoc_thi_tra_None():
    """Trả None là kết quả HỢP LỆ, không phải lỗi — nó là tín hiệu để tầng
    trên phát một cảnh báo CÓ TÊN thay vì đoán bừa một hàng."""
    rows = [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]
    assert find_header(rows) is None


def test_bang_bat_dau_ngay_hang_dau_van_dung():
    rows = [
        ["Sản phẩm", "Giá", "Tồn"],
        ["Bàn", 1200000, 30],
        ["Ghế", 450000, 120],
    ]
    g = find_header(rows)
    assert g is not None and g.row_index == 0
```

- [ ] **Step 2: Chạy để thấy ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_xlsx_header.py -v -m "not integration and not live"`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rag.xlsx_header'`

- [ ] **Step 3: Viết bộ dò, rồi HIỆU CHỈNH bằng đo — đây là bước quan trọng nhất**

Bản khởi điểm dưới đây **cố ý để hai hằng số ở giá trị tạm**; Step 3b thay chúng bằng số đo. Bạn được phép sửa công thức chấm điểm nếu đo ra kết quả tốt hơn — miễn là kèm bảng đo.

```python
"""Dò hàng tiêu đề của một bảng Excel — spec 2026-08-29 mục 5.2.

Module LÁ: chỉ nhận lưới giá trị ô, không biết openpyxl, không biết DB.

Vì sao cần: `parse_xlsx` từng lấy hàng ĐẦU TIÊN có chữ làm nhãn cột. Trên sổ
kế toán thật (81 sheet có dữ liệu) điều đó cho 0/81 sheet đúng — nhãn cột hoá
ra là tên công ty, tên tài liệu, số phiếu, câu hướng dẫn, và một lần là chuỗi
công thức `$B$7:$M$100`.
"""
import re
from dataclasses import dataclass

# GIÁ TRỊ TẠM — Step 3b thay bằng số đo trên 23 sheet đã có đáp án.
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
```

> **Hiệu chỉnh KHÔNG làm ở Task này.** Phép đo cần dữ liệu đã **trải ô gộp**, mà việc trải nằm ở Task 3. Chạy hiệu chỉnh trên lưới chưa trải sẽ đo trên dữ liệu sai hình dạng: hàng header cha trông thưa hơn thực tế và làm lệch điểm `contiguity`. Task 2 ship với hai giá trị tạm; **Task 3 Step 5 chốt chúng bằng số**.

- [ ] **Step 4: Chạy thấy XANH**

Run: lệnh ở Step 2. Expected: PASS 6/6.

- [ ] **Step 5: Phép thử phá**

Đổi `find_header` thành `return HeaderGuess(0, [str(c) for c in rows[0]], 1.0)` (tức hành vi cũ).
Run: lệnh ở Step 2.
Expected: **ít nhất 4 test ĐỎ**. Hoàn tác.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/xlsx_header.py backend/tests/rag/test_xlsx_header.py
git commit -m "feat(rag): bo do hang tieu de xlsx, nguong hieu chinh tren du lieu that"
```

---

### Task 3: Ô gộp và header hai tầng

**Files:**
- Modify: `backend/src/rag/parse.py` (`parse_xlsx`)
- Modify: `backend/src/rag/xlsx_header.py` (thêm hàm ghép hai tầng)
- Create: `backend/tests/rag/test_parse_xlsx_merged.py`

**Interfaces:**
- Consumes: `find_header`, `HeaderGuess` từ Task 2.
- Produces:
  - `xlsx_header.compose_two_tier(parent_row: list, child_row: list) -> list[str]` — ghép `"cha · con"` khi ô cha không rỗng và khác ô con; trả ô con khi cha rỗng.
  - `parse_xlsx(path) -> tuple[list[dict], list[tuple[str, str]]]` — **đổi chữ ký**: trả thêm danh sách `(sheet, reason)` cho các sheet đáng ngờ.

**Sự thật kỹ thuật bắt buộc tôn trọng:** `openpyxl.load_workbook(read_only=True)` **không nạp `ws.merged_cells`**. Phải bỏ `read_only=True`. Đã thử với chính tệp 12,5 MB của chủ dự án: mở được, thời gian chấp nhận được. Ô gộp phải được **trải giá trị** ra toàn vùng trước khi dò tiêu đề, nếu không nhãn cha chỉ nằm ở ô trên-trái.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_parse_xlsx_merged.py`:

```python
# backend/tests/rag/test_parse_xlsx_merged.py
"""Ô gộp và header hai tầng — spec 2026-08-29 mục 5.2.

Fixture tự dựng, đáp án chắc 100% (spec mục 6.1 tầng 1).
"""
import openpyxl
import pytest

from src.rag.parse import parse_xlsx


def _make_bctc(path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "BCTC"
    ws["A1"] = "BÁO CÁO TÀI CHÍNH HỢP NHẤT QUÝ II/2026"
    ws.merge_cells("A1:E1")
    ws["A3"] = "Chỉ tiêu"; ws["B3"] = "Quý II"; ws["D3"] = "Lũy kế"
    ws.merge_cells("B3:C3"); ws.merge_cells("D3:E3"); ws.merge_cells("A3:A4")
    ws["B4"] = "2026"; ws["C4"] = "2025"; ws["D4"] = "2026"; ws["E4"] = "2025"
    for i, row in enumerate([("Doanh thu thuần", 1250, 1100, 2400, 2050),
                             ("Giá vốn hàng bán", 900, 820, 1750, 1560),
                             ("Lợi nhuận gộp", 350, 280, 650, 490)], start=5):
        for j, v in enumerate(row):
            ws.cell(row=i, column=j + 1, value=v)
    wb.save(path)


def test_nhan_cot_khong_con_la_tieu_de_tai_lieu(tmp_path):
    p = str(tmp_path / "bctc.xlsx"); _make_bctc(p)
    sheets, _ = parse_xlsx(p)
    cols = sheets[0]["columns"]
    assert "BÁO CÁO TÀI CHÍNH" not in " ".join(cols)
    assert cols[0] == "Chỉ tiêu"


def test_header_hai_tang_ghep_cha_con(tmp_path):
    """Bốn con số 1250/1100/2400/2050 chỉ phân biệt được nhờ nhãn ghép."""
    p = str(tmp_path / "bctc.xlsx"); _make_bctc(p)
    sheets, _ = parse_xlsx(p)
    cols = sheets[0]["columns"]
    assert "Quý II · 2026" in cols
    assert "Quý II · 2025" in cols
    assert "Lũy kế · 2026" in cols
    assert "Lũy kế · 2025" in cols


def test_o_gop_duoc_trai_gia_tri_khong_con_None(tmp_path):
    p = str(tmp_path / "bctc.xlsx"); _make_bctc(p)
    sheets, _ = parse_xlsx(p)
    assert all(c for c in sheets[0]["columns"][:5])


def test_hang_du_lieu_khong_lan_hang_tieu_de(tmp_path):
    p = str(tmp_path / "bctc.xlsx"); _make_bctc(p)
    sheets, _ = parse_xlsx(p)
    first = sheets[0]["rows"][0]
    assert first[0] == "Doanh thu thuần"


def test_sheet_khong_do_duoc_tieu_de_thi_sinh_canh_bao(tmp_path):
    p = str(tmp_path / "soden.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SoLieu"
    for i, row in enumerate([[1, 2, 3], [4, 5, 6], [7, 8, 9]], start=1):
        for j, v in enumerate(row):
            ws.cell(row=i, column=j + 1, value=v)
    wb.save(p)
    _, canh_bao = parse_xlsx(p)
    assert any(sheet == "SoLieu" for sheet, _ in canh_bao)
```

- [ ] **Step 2: Chạy để thấy ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_parse_xlsx_merged.py -v -m "not integration and not live"`
Expected: FAIL — `parse_xlsx` trả một giá trị chứ không phải tuple.

- [ ] **Step 3: Sửa `parse_xlsx`**

Viết lại, giữ đúng khuôn trả về `{"sheet", "columns", "rows"}` cho mỗi sheet:

```python
def parse_xlsx(path: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Trả (sheets, warnings). `warnings` là các cặp (tên sheet, lý do).

    KHÔNG dùng `read_only=True`: chế độ đó không nạp `ws.merged_cells`, mà
    nhãn cột của báo cáo tài chính Việt Nam gần như luôn nằm trong ô gộp.
    Đã thử trên sổ kế toán thật 12,5 MB / 84 sheet: mở được, chấp nhận được.
    """
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    sheets: list[dict] = []
    warnings: list[tuple[str, str]] = []
    for ws in wb.worksheets:
        grid = _spread_merged(ws)          # trải giá trị ô gộp ra toàn vùng
        rows = [r for r in grid if any(c is not None for c in r)]
        if not rows:
            continue
        guess = find_header(rows)
        if guess is None:
            warnings.append((ws.title, "không dò được hàng tiêu đề — "
                                       "nhãn cột để trống thay vì đoán bừa"))
            columns = ["" for _ in rows[0]]
            body = rows
        else:
            parent = rows[guess.row_index - 1] if guess.row_index > 0 else None
            columns = (compose_two_tier(parent, guess.labels)
                       if parent is not None else guess.labels)
            body = rows[guess.row_index + 1:]
        sheets.append({"sheet": ws.title, "columns": columns, "rows": body})
    wb.close()
    return sheets, warnings
```

Hai hàm phụ, viết như sau.

Trong `parse.py`:

```python
def _spread_merged(ws) -> list[list]:
    """Lưới giá trị của sheet, với ô gộp được TRẢI ra toàn vùng.

    openpyxl chỉ đặt giá trị ở ô trên-trái của vùng gộp, các ô còn lại là
    None. Không trải thì nhãn cha ("Quý II" trải B:C) chỉ dính vào cột B, và
    cột C mất nhãn — đúng bốn con số 1250/1100/2400/2050 không phân biệt được.
    """
    grid = [list(r) for r in ws.iter_rows(values_only=True)]
    for rng in ws.merged_cells.ranges:
        r0, c0, r1, c1 = rng.min_row, rng.min_col, rng.max_row, rng.max_col
        if r0 - 1 >= len(grid) or c0 - 1 >= len(grid[r0 - 1]):
            continue
        value = grid[r0 - 1][c0 - 1]
        if value is None:
            continue
        for r in range(r0 - 1, min(r1, len(grid))):
            for c in range(c0 - 1, min(c1, len(grid[r]))):
                grid[r][c] = value
    return grid
```

Trong `xlsx_header.py`:

```python
def is_parent_header(row: list) -> bool:
    """Hàng trên hàng tiêu đề có phải MỘT TẦNG HEADER không?

    Tiêu chí: phần lớn ô rỗng, và các ô có giá trị đều trông như nhãn. Một
    tầng header cha ("Quý II" trải B:C, "Lũy kế" trải D:E) sau khi trải ô gộp
    sẽ lấp đầy đúng những cột nó bao, còn lại rỗng — khác hẳn một dòng dữ
    liệu ngẫu nhiên nằm trên, vốn lấp gần hết cột và có số.

    Ghép nhầm một dòng dữ liệu vào nhãn cột còn tệ hơn không ghép: nó tạo ra
    nhãn sai một cách tự tin.
    """
    filled = [c for c in row if c is not None and str(c).strip() != ""]
    if not filled or len(filled) == len(row):
        return False
    return all(_looks_like_label(c) for c in filled)


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
```

- [ ] **Step 4: Chạy thấy XANH**

Run: lệnh ở Step 2. Expected: PASS 5/5.

- [ ] **Step 5: Hiệu chỉnh `SCAN_LIMIT` và `MIN_SCORE` bằng đo — KHÔNG được bỏ qua**

Giờ mới làm được, vì `_spread_merged` đã tồn tại. Viết một script đo **dùng một lần** (thư mục tạm, **không commit**) chạy trên sổ kế toán thật:

```
d:/Youdoo/tmp-docs/Sổ-Sách-Kế-Toán-Trên-Excel-TT 200 (1).xls.xlsm
```

Script phải dùng **cùng `_spread_merged`** mà `parse_xlsx` dùng, để đo trên đúng hình dạng dữ liệu mà sản phẩm sẽ thấy.

Đáp án có sẵn cho **23 sheet**: hàng tiêu đề đúng là hàng **chứa ô có giá trị `STT`** (so sánh sau `strip().upper()`). Với mỗi cặp `SCAN_LIMIT` × `MIN_SCORE` trong một lưới hợp lý, đo ba con số:

| | ý nghĩa |
|---|---|
| dò **đúng** hàng | càng nhiều càng tốt |
| dò **sai** hàng | **nguy hiểm nhất** — gắn nhãn sai một cách tự tin, không ai phát hiện |
| trả `None` | an toàn — sinh cảnh báo có tên |

**Chốt theo thứ tự: tối thiểu hoá "dò sai" TRƯỚC, rồi mới tối đa hoá "dò đúng".** Dò sai tệ hơn trả `None`, vì `None` còn kêu.

Ghi bảng đo vào báo cáo, và ghi số chốt kèm lý do vào docstring của hằng số. **Không được chốt số mà không có bảng.** Nếu số chốt khác giá trị tạm, chạy lại `tests/rag/test_xlsx_header.py` để chắc 6 test đơn vị vẫn xanh.

- [ ] **Step 6: Phép thử phá**

Đổi `_spread_merged` thành trả thẳng `[list(r) for r in ws.iter_rows(values_only=True)]` (không trải ô gộp).
Run: lệnh ở Step 2.
Expected: `test_header_hai_tang_ghep_cha_con` và `test_o_gop_duoc_trai_gia_tri_khong_con_None` **ĐỎ**. Hoàn tác.

- [ ] **Step 7: Commit**

```bash
git add backend/src/rag/parse.py backend/src/rag/xlsx_header.py backend/tests/rag/test_parse_xlsx_merged.py
git commit -m "feat(rag): parse_xlsx nap o gop va ghep header hai tang"
```

---

### Task 4: Nối cảnh báo vào báo cáo nạp

**Files:**
- Modify: `backend/src/rag/ingest.py`
- Create: `backend/tests/rag/test_canh_bao_sheet.py`

**Interfaces:**
- Consumes: `parse_xlsx` trả tuple (Task 3), `Warning`/`IngestReport.warnings` (Task 1).
- Produces: không có tên mới; `_ingest_known` gắn `Warning` vào báo cáo cho mỗi cặp `(sheet, reason)`.

**Chú ý:** `_chunks_for` hiện gọi `parse_xlsx(path)` và truyền thẳng vào `chunk_xlsx_sheets`. Nay `parse_xlsx` trả tuple nên `_chunks_for` phải trả kèm cảnh báo lên `_ingest_known`. Đây là chỗ duy nhất trong repo gọi `parse_xlsx` — hãy `grep -rn "parse_xlsx" backend/` để tự xác nhận trước khi đổi.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_canh_bao_sheet.py`:

```python
# backend/tests/rag/test_canh_bao_sheet.py
"""Cảnh báo mức sheet đi được tới báo cáo nạp — spec mục 4.

Một sheet không dò được tiêu đề vẫn cho tệp nạp thành công, nhưng phải
được GỌI TÊN. Nuốt nó là dựng lại lỗi mà cả spec đi đóng.
"""
import contextlib

import openpyxl
import pytest

from src.rag import ingest as _ing


class _FakeConn:
    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None

    def transaction(self):
        return contextlib.nullcontext()


@pytest.fixture
def _no_embed(monkeypatch):
    monkeypatch.setattr(_ing, "embed_texts",
                        lambda texts: [[0.01] * 1024 for _ in texts])


def _make_sheet_khong_tieu_de(path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SoLieu"
    for i, row in enumerate([[1, 2, 3], [4, 5, 6], [7, 8, 9]], start=1):
        for j, v in enumerate(row):
            ws.cell(row=i, column=j + 1, value=v)
    wb.save(path)


def test_sheet_dang_ngo_duoc_goi_ten_trong_bao_cao(tmp_path, _no_embed):
    p = str(tmp_path / "so.xlsx"); _make_sheet_khong_tieu_de(p)
    rep = _ing._ingest_file(p, conn=_FakeConn())
    assert rep.ingested == 1, "tệp vẫn phải nạp được"
    assert rep.ok is True, "cảnh báo KHÔNG làm lượt nạp thất bại"
    assert any(w.where == "SoLieu" for w in rep.warnings)
    assert "so.xlsx" in rep.render()
    assert "SoLieu" in rep.render()


def test_sheet_binh_thuong_khong_sinh_canh_bao(tmp_path, _no_embed):
    """Chân đối chứng: nếu mọi sheet đều sinh cảnh báo thì cảnh báo vô nghĩa."""
    p = str(tmp_path / "sach.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "BangGia"
    ws.append(["Sản phẩm", "Giá", "Tồn"])
    ws.append(["Bàn", 1200000, 30])
    ws.append(["Ghế", 450000, 120])
    wb.save(p)
    rep = _ing._ingest_file(p, conn=_FakeConn())
    assert rep.ingested == 1
    assert rep.warnings == []
```

- [ ] **Step 2: Chạy để thấy ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_canh_bao_sheet.py -v -m "not integration and not live"`
Expected: FAIL — `rep.warnings` rỗng.

- [ ] **Step 3: Nối trong `ingest.py`**

Đổi `_chunks_for` trả `(chunks, sheet_warnings)`:

```python
def _chunks_for(read_path: str, kind: str, doc_id: str,
                source_file: str) -> tuple[list[dict], list[tuple[str, str]]]:
    if kind == "xlsx":
        sheets, sheet_warnings = parse_xlsx(read_path)
        return (chunk_xlsx_sheets(sheets, doc_id=doc_id, source_file=source_file),
                sheet_warnings)
    low = read_path.lower()
    if low.endswith(".pdf"):
        blocks = parse_pdf(read_path)
    elif low.endswith(".pptx"):
        blocks = parse_pptx(read_path)
    else:
        blocks = parse_docx(read_path)
    if not blocks:
        return [], []
    return (chunk_text_blocks(blocks, doc_id=doc_id, source_file=source_file), [])
```

Trong `_ingest_known`, chỗ gọi `_chunks_for` nhận hai giá trị, và dòng `return` cuối thành:

```python
    report = IngestReport(ingested=1, chunks=len(chunks))
    for sheet, reason in sheet_warnings:
        report.warnings.append(Warning(origin, sheet, reason))
    return report
```

Nhớ import `Warning` từ `.ingest_report`.

**Trước khi đổi, tự xác nhận phạm vi:** chạy `grep -rn "parse_xlsx\|_chunks_for" backend/ --include=*.py` để chắc không còn nơi nào khác gọi hai hàm này. Đổi chữ ký mà bỏ sót một lời gọi là hỏng im lặng ở chỗ khác.

- [ ] **Step 4: Chạy thấy XANH**

Run: lệnh ở Step 2. Expected: PASS 2/2.

- [ ] **Step 5: Chạy toàn suite, đối chiếu số**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS. Số trước là **2257**; số sau phải bằng 2257 cộng đúng số test mới. Đối chiếu con số, đừng chỉ nhìn chữ "passed" — một script sửa test từng lặng lẽ nuốt 3 test mà suite vẫn xanh.

- [ ] **Step 6: Chạy test integration**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_ingest.py -v -m integration`
Expected: PASS (Postgres cổng 5434). Đây là nơi duy nhất kiểm việc đổi chữ ký `parse_xlsx` không phá đường ghi thật.

- [ ] **Step 7: Phép thử phá**

Tạm bỏ vòng `for sheet, reason in sheet_warnings`.
Run: lệnh ở Step 2. Expected: `test_sheet_dang_ngo_duoc_goi_ten_trong_bao_cao` **ĐỎ**. Hoàn tác.

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/ingest.py backend/tests/rag/test_canh_bao_sheet.py
git commit -m "feat(rag): canh bao muc sheet di duoc toi bao cao nap"
```

---

### Task 5: Nghiệm thu trên sổ kế toán thật

**Files:**
- Create: `backend/tests/rag/test_xlsx_kho_that.py`

**Interfaces:**
- Consumes: `parse_xlsx` (Task 3).
- Produces: không có.

Đây là **tầng 2** của spec mục 6.1. Tệp thật ở ngoài repo nên test mang mốc `live` và phải `skip` sạch khi thiếu.

**Đáp án có sẵn:** với sheet nào có ô mang giá trị `STT` (sau `strip().upper()`), hàng chứa ô đó **chính là** hàng tiêu đề đúng. Trước bản sửa: **0/23** đúng.

- [ ] **Step 1: Viết test**

Tạo `backend/tests/rag/test_xlsx_kho_that.py`:

```python
# backend/tests/rag/test_xlsx_kho_that.py
"""Nghiệm thu tầng 2 — sổ kế toán THẬT, ngoài repo (spec mục 6.1, 7).

Đáp án lấy từ chính tài liệu: sheet nào có ô "STT" thì hàng chứa ô đó là
hàng tiêu đề. Trước bản sửa: 0/23 sheet đúng.
"""
import os
import pytest

from src.rag.parse import parse_xlsx

SO = "d:/Youdoo/tmp-docs/Sổ-Sách-Kế-Toán-Trên-Excel-TT 200 (1).xls.xlsm"
pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.path.isfile(SO), reason="chưa có sổ kế toán thật")
def test_moi_sheet_co_cot_STT_deu_lay_dung_hang_tieu_de():
    sheets, canh_bao = parse_xlsx(SO)
    assert len(sheets) >= 50, "đọc thiếu sheet, xem lại tệp"

    dung = sai = 0
    sai_ten = []
    for s in sheets:
        cols = [str(c).strip().upper() for c in s["columns"]]
        co_stt_o_body = any(
            any(str(c).strip().upper() == "STT" for c in row if c is not None)
            for row in s["rows"])
        if "STT" in cols:
            dung += 1
        elif co_stt_o_body:
            sai += 1
            if len(sai_ten) < 8:
                sai_ten.append(s["sheet"])

    print("\n  sheet lấy ĐÚNG hàng tiêu đề : %d" % dung)
    print("  sheet vẫn lấy SAI          : %d  %s" % (sai, sai_ten))
    print("  sheet sinh cảnh báo        : %d" % len(canh_bao))
    assert dung >= 20, f"chỉ {dung}/23 sheet đúng — trước bản sửa là 0"
    assert sai == 0, f"còn {sai} sheet lấy sai hàng tiêu đề: {sai_ten}"


@pytest.mark.skipif(not os.path.isfile(SO), reason="chưa có sổ kế toán thật")
def test_khong_sheet_nao_lay_chuoi_cong_thuc_lam_nhan_cot():
    """Sheet `BK NHẬP - XUẤT` từng lấy `$B$7:$M$100` làm nhãn cột."""
    sheets, _ = parse_xlsx(SO)
    xau = [s["sheet"] for s in sheets
           if any("$" in str(c) and ":" in str(c) for c in s["columns"])]
    assert xau == [], f"vẫn còn nhãn cột trông như công thức: {xau}"
```

- [ ] **Step 2: Chạy**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_xlsx_kho_that.py -v -m live -s`
Expected: PASS, và **dán bảng số in ra** vào báo cáo. Nếu `dung < 20` thì đó là phát hiện thật — báo rõ, **đừng nới ngưỡng cho xanh**.

- [ ] **Step 3: Chạy lại toàn suite mặc định**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS, số khớp Task 4 Step 5.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/rag/test_xlsx_kho_that.py
git commit -m "test(rag): nghiem thu do hang tieu de tren so ke toan that"
```

---

## Sau khi xong kế hoạch này

Ghi nối tiếp vào `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md` phần **khó khăn / hướng đã chọn / giới hạn còn lại** của đợt B2, gồm cả giả thuyết nào bị số đo bác bỏ và bảng hiệu chỉnh ngưỡng ở Task 2 Step 3.

Kế hoạch tiếp theo: **B3 — Word suy phân cấp từ chữ** (spec mục 5.3).
