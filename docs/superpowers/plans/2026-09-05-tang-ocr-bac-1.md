# Tầng OCR bậc 1 (chân Tesseract) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng chân đọc-bằng-ảnh chạy local (Tesseract) thành một tầng dùng chung có ranh giới riêng, tự động kích hoạt cho trang PDF không có lớp text, kèm cờ xuất xứ trong DB và một cổng tự nuôi chứng minh đường này còn sống ở mỗi lượt chạy test.

**Architecture:** Ba tầng theo spec §3 — tầng 0 `ocr/engine.py` (một ảnh → từ + toạ độ + độ tin cậy, không biết PDF), tầng 1 `ocr/document.py` (PDF → rasterise từng trang → vùng có kiểu → đệm trên đĩa), tầng 2 là consumer `rag/parse.py` (trang rỗng → gọi tầng 1). Cả hai module OCR là **module lá**: import được từ bất cứ đâu mà không kéo theo DB hay cấu hình runtime, đúng nghĩa dự án đã dùng cho `xlsx_header.py` và `pdf_table.py`.

**Tech Stack:** Python 3.11, `pytesseract` 0.3.13 + binary Tesseract 5.4.0 (đã cài, cần KHAI vào `requirements.txt`), `pypdfium2` + `Pillow` (đã có sẵn theo `pdfplumber`, không thêm phụ thuộc), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-04-tang-ocr-dung-chung-design.md` (spec rộng hơn: `docs/superpowers/specs/2026-08-29-tang-nap-tai-lieu.md` §5.5 — phần **kiến trúc** của nó đã bị spec trên thay thế, phần **số đo** vẫn còn giá trị)

## Global Constraints

- **Phạm vi là BẬC 1 (spec §14)**: chân Tesseract đầy đủ + cổng tự nuôi + artifact vùng-có-kiểu **chỉ sinh kiểu `text`**. Bậc 2 (dựng bảng từ toạ độ) và bậc 3 (chân VLM cho `figure`) **NGOÀI phạm vi** — chờ có tài liệu scan thật. Hợp đồng artifact (§6) và cột DB (§8) vẫn dựng NGAY từ bậc 1 để bậc 2/3 không phải thiết kế lại.
- **Tham số đã hiệu chỉnh bằng đo, không được đổi tuỳ tiện (spec §4.1)**: `PSM = 6` (recall TB 0,865 so với 0,569 của PSM 3 mặc định, và PSM 3 hỏng KHÔNG ĐỀU giữa các trang), `DPI = 200` (2,5 s/trang, chất lượng ngang 400 DPI nhưng nhanh 2,4 lần), `lang = "vie+eng"`.
- **"Rỗng" nghĩa là KHÔNG CÒN DÒNG NÀO** sau bước strip hiện có (`text_toan_trang == []`), KHÔNG phải "ít chữ". Cấm đặt ngưỡng "dưới N ký tự thì coi là rỗng": chưa có tài liệu scan thật để hiệu chỉnh N, và hằng số rút từ không khí là thứ dự án này cấm (spec §11).
- **KHÔNG BAO GIỜ để LLM viết lại text đã trích** (spec §9 ràng buộc 1) — bậc 1 không có LLM nào trong đường đi, giữ nguyên như vậy.
- **Khoá đệm phải gồm dấu vân tay cấu hình**, không chỉ `content_hash` (spec §7): đổi PSM/DPI/lang/phiên bản tesseract là ra kết quả khác. `convert.py` đang có đúng lỗ hổng này — tầng này không lặp lại.
- **Ghi tạm rồi đổi tên nguyên tử** (spec §7): tệp cụt do timeout ở lại thì bẩn vĩnh viễn vì khoá đệm không tự lành.
- **Quy tắc gộp xuất xứ là BI QUAN** (spec §8): chunk lấy bậc thấp-tin-cậy-nhất trong các block thành phần, `ocr_conf` lấy **min**.
- **Trang ĐÃ CÓ lớp text không được đụng tới**: output `parse_pdf` cho tài liệu hiện có phải byte-identical với trước đợt này (corpus thật hôm nay 0 tài liệu cần OCR).
- **CỐ Ý KHÔNG nối `source_kind` vào truy xuất và prompt tổng hợp trong đợt này.** Spec §9 mô tả đích đến ("prompt biết đoạn này từ OCR, đừng trích số như thể chính xác"), nhưng corpus hôm nay sinh **0 chunk OCR**, nên nối ngay sẽ tạo một nhánh code KHÔNG BAO GIỜ CHẠY — đúng cách reranker (chết 6 tuần), chân sparse (chết từ ngày đầu) và sổ ngân sách đã chết, và đúng lý do migration `003_effective_date.sql` từ chối viết bộ lọc hiệu lực ngay lúc thu thập. Cột được dựng từ bậc 1 để dữ liệu không mất; việc ĐỌC cột mở khi có tài liệu scan thật. Đã kiểm: `retrieve.py:13-15` liệt kê cột tường minh (`_COLS`), không dùng `SELECT *`, nên thêm cột là thay đổi CỘNG THÊM, không xê dịch vị trí gì của đường đọc hiện có.
- Chạy test: `pytest -m "not integration and not live"` cho vòng nhanh. Test cần binary tesseract dùng `@pytest.mark.skipif(tesseract_path() is None, ...)`; test cần kho tài liệu thật dùng `skipif` trên đường dẫn kho — cùng khuôn `test_pdf_kho_that.py` của B4.
- Baseline đầu đợt (đo 2026-09-05): `pytest --collect-only -q -m "not integration and not live"` → **2337 passed, 1 skipped, 83 deselected**.

---

## Task 1: `ocr/engine.py` — máy đọc chữ (tầng 0)

**Files:**
- Create: `backend/src/ocr/__init__.py`
- Create: `backend/src/ocr/engine.py`
- Modify: `backend/requirements.txt` (khai `pytesseract==0.3.13`)
- Test: `backend/tests/ocr/__init__.py`, `backend/tests/ocr/test_engine.py`

**Interfaces:**
- Consumes: không có gì từ task trước (đây là task đầu).
- Produces (dùng ở Task 2):
  - `tesseract_path() -> str | None`
  - `tessdata_prefix() -> str | None`
  - `tesseract_version() -> str`
  - `TesseractMissing(RuntimeError)`
  - `OcrWord` dataclass: `text: str`, `conf: float`, `left/top/width/height: int`, `line_id: tuple[int,int,int]`
  - `OcrResult` dataclass: `words: list[OcrWord]`, `text: str`, `mean_conf: float`
  - `parse_tsv(tsv: str) -> list[OcrWord]`
  - `words_to_lines(words: list[OcrWord]) -> list[str]`
  - `ocr_image(img, *, lang: str = OCR_LANG, psm: int = OCR_PSM) -> OcrResult`
  - Hằng: `OCR_PSM = 6`, `OCR_DPI = 200`, `OCR_LANG = "vie+eng"`

- [ ] **Step 1: Khai `pytesseract` vào `requirements.txt`**

Đã cài sẵn trong `.venv` (0.3.13) nhưng CHƯA khai — đúng lớp nợ mà B4 vừa vá cho `pdfplumber`. Mở `backend/requirements.txt`, thêm ngay dưới dòng `pdfplumber==0.11.10`:

```
pytesseract==0.3.13
```

- [ ] **Step 2: Xác nhận không đổi phiên bản gì**

Run: `cd backend && pip install -r requirements.txt`
Expected: `Requirement already satisfied: pytesseract==0.3.13` — không tải lại gì.

- [ ] **Step 3: Viết test cho `parse_tsv` (thuần, không cần binary)**

```python
# backend/tests/ocr/test_engine.py
from src.ocr.engine import OcrWord, parse_tsv, words_to_lines

# TSV THẬT của tesseract 5.4.0, chép từ phép đo 2026-09-05 trên
# luat-thuexuatnhapkhau.pdf trang 6 (rút gọn còn 5 hàng đầu + 1 từ nữa).
# Cột: level page_num block_num par_num line_num word_num left top width height conf text
_TSV = "\n".join([
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "1\t1\t0\t0\t0\t0\t0\t0\t2200\t1700\t-1\t",
    "2\t1\t1\t0\t0\t0\t67\t47\t2065\t1607\t-1\t",
    "3\t1\t1\t1\t0\t0\t67\t47\t2065\t1607\t-1\t",
    "4\t1\t1\t1\t1\t0\t67\t47\t1199\t16\t-1\t",
    "5\t1\t1\t1\t1\t1\t67\t47\t51\t16\t95.924789\t22:41",
    "5\t1\t1\t1\t1\t2\t130\t47\t80\t16\t92.5\tngày",
    "5\t1\t1\t1\t2\t1\t67\t70\t60\t16\t88.25\tĐiều",
])


def test_parse_tsv_chi_lay_hang_TU_that():
    words = parse_tsv(_TSV)
    # 4 hàng level 1-4 là KHUNG CẤU TRÚC (trang/khối/đoạn/dòng), conf=-1,
    # text rỗng — không phải từ. Chỉ 3 hàng level 5 mới là từ.
    assert [w.text for w in words] == ["22:41", "ngày", "Điều"]
    assert words[0].conf == 95.924789
    assert (words[0].left, words[0].top, words[0].width, words[0].height) == (67, 47, 51, 16)


def test_parse_tsv_giu_dinh_danh_dong_de_gom_lai_duoc():
    words = parse_tsv(_TSV)
    assert words[0].line_id == (1, 1, 1)
    assert words[2].line_id == (1, 1, 2)


def test_words_to_lines_gom_theo_dong_giu_thu_tu():
    words = parse_tsv(_TSV)
    assert words_to_lines(words) == ["22:41 ngày", "Điều"]


def test_words_to_lines_rong_thi_tra_rong():
    assert words_to_lines([]) == []
```

- [ ] **Step 4: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/ocr/test_engine.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'src.ocr'`

- [ ] **Step 5: Tạo package và viết `engine.py`**

Tạo `backend/src/ocr/__init__.py` RỖNG và `backend/tests/ocr/__init__.py` RỖNG (thư mục test khác đã có `__init__.py`; giữ đồng nhất).

```python
# backend/src/ocr/engine.py
"""Máy đọc chữ từ ảnh (Tesseract) — tầng 0 của spec 2026-09-04-tang-ocr §3.

Module LÁ: nhận một ảnh PIL, trả về TỪ kèm toạ độ và độ tin cậy. KHÔNG biết
PDF, trang, DB, chunk, hay ai đang gọi mình. Tầng 1 (`document.py`) lo việc
rasterise và đệm; tầng 2 (`rag/parse.py`) lo việc dùng chữ để làm gì.
"""
import os
import shutil
from dataclasses import dataclass

TESSERACT_ENV = "TESSERACT_PATH"
TESSDATA_ENV = "TESSDATA_PREFIX"

# HIỆU CHỈNH BẰNG ĐO (spec §4.1), không phải mặc định của thư viện:
#
# PSM 6 — recall theo TỪ trung bình 0,865 trên 3 trang bảng, so với 0,569 của
# PSM 3 (mặc định của tesseract). Điều đáng sợ không phải PSM 3 kém, mà là nó
# hỏng KHÔNG ĐỀU giữa các trang: 0,26 trang này, 0,81 trang kia, không báo gì.
# Dùng mặc định thì một phần corpus scan sẽ biến mất âm thầm.
#
# 200 DPI — 2,5 s/trang, recall 0,865; 400 DPI ngang chất lượng nhưng chậm
# 2,4 lần; 150 DPI nhanh hơn chút nhưng recall thấp hơn.
OCR_PSM = 6
OCR_DPI = 200
OCR_LANG = "vie+eng"

# KHÔNG viết cứng một đường dẫn duy nhất — cùng lý do `convert.soffice_path()`
# đã nêu: máy dev hiện tại cài qua winget vào Program Files, máy khác sẽ khác
# (spec §18 "nợ triển khai").
_FALLBACK_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)

# `vie.traineddata` KHÔNG nằm cạnh binary trên máy dev: ghi vào Program Files
# cần quyền admin nên lúc cài đã thất bại, gói ngôn ngữ để ở thư mục người
# dùng (spec §4.1). Không trỏ đúng chỗ này thì tesseract chạy nhưng KHÔNG có
# tiếng Việt — hỏng âm thầm đúng loại spec đi đóng.
_FALLBACK_TESSDATA = (
    r"C:\Users\ADMIN\.tessdata",
    r"C:\Program Files\Tesseract-OCR\tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tessdata",
)


class TesseractMissing(RuntimeError):
    """Không tìm thấy binary tesseract."""


@dataclass(frozen=True)
class OcrWord:
    """Một TỪ tesseract đọc được, kèm toạ độ và độ tin cậy 0-100.

    Giữ toạ độ vì nó MIỄN PHÍ (tesseract xuất sẵn trong TSV) và vì bậc 2 sẽ
    cần nó để dựng lại bảng. Nguyên tắc spec §6: không mất mát ở tầng dưới,
    diễn giải ở tầng trên — vứt thông tin ở tầng 0 là không đảo ngược được.
    """
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    line_id: tuple[int, int, int]   # (block_num, par_num, line_num)


@dataclass(frozen=True)
class OcrResult:
    words: list[OcrWord]
    text: str          # dòng nối bằng "\n", từ trong dòng nối bằng " "
    mean_conf: float   # trung bình conf các TỪ; 0.0 khi không đọc được từ nào


def tesseract_path() -> str | None:
    """Đường dẫn binary tesseract, hoặc None. Thứ tự: biến môi trường → PATH
    → vài vị trí quen thuộc — ĐÚNG KHUÔN `convert.soffice_path()`."""
    env = os.environ.get(TESSERACT_ENV)
    if env and os.path.isfile(env):
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _FALLBACK_TESSERACT:
        if os.path.isfile(p):
            return p
    return None


def tessdata_prefix() -> str | None:
    """Thư mục chứa `vie.traineddata`, hoặc None."""
    env = os.environ.get(TESSDATA_ENV)
    if env and os.path.isdir(env):
        return env
    for d in _FALLBACK_TESSDATA:
        if os.path.isdir(d):
            return d
    return None


def parse_tsv(tsv: str) -> list[OcrWord]:
    """Lọc TSV của `image_to_data` xuống các TỪ thật.

    Dạng thật (đo trên tesseract 5.4.0, 2026-09-05): cột là
    `level page_num block_num par_num line_num word_num left top width height
    conf text`, và CHỈ hàng `level == 5` là từ — mọi mức thấp hơn là khung cấu
    trúc (trang/khối/đoạn/dòng) với `conf = -1` và text rỗng.

    Lọc theo `level` chứ không theo `conf >= 0`: hôm nay hai tiêu chí trùng
    nhau, nhưng `level` là thứ tesseract ĐỊNH NGHĨA, còn conf chỉ là hệ quả.
    """
    out: list[OcrWord] = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        text = c[11].strip()
        if not text:
            continue
        out.append(OcrWord(
            text=text, conf=float(c[10]),
            left=int(c[6]), top=int(c[7]), width=int(c[8]), height=int(c[9]),
            line_id=(int(c[2]), int(c[3]), int(c[4]))))
    return out


def words_to_lines(words: list[OcrWord]) -> list[str]:
    """Gom từ thành dòng theo `line_id`, GIỮ NGUYÊN thứ tự tesseract trả.

    Không sắp xếp lại theo toạ độ: tesseract đã xếp theo thứ tự đọc của nó, và
    spec §13 ghi rõ bài học "thứ tự đọc khác pdfplumber" — sắp lại ở đây là
    thêm một phỏng đoán nữa vào tầng đáng lẽ không được phỏng đoán.
    """
    lines: list[str] = []
    cur_id: tuple[int, int, int] | None = None
    cur: list[str] = []
    for w in words:
        if w.line_id != cur_id:
            if cur:
                lines.append(" ".join(cur))
            cur_id, cur = w.line_id, []
        cur.append(w.text)
    if cur:
        lines.append(" ".join(cur))
    return lines


def tesseract_version() -> str:
    """Phiên bản binary, dạng chuỗi — đi vào dấu vân tay đệm của tầng 1."""
    import pytesseract
    _dam_bao_moi_truong()
    return str(pytesseract.get_tesseract_version())


def _dam_bao_moi_truong() -> None:
    """Trỏ pytesseract vào đúng binary và đúng thư mục tessdata.

    Chỉ ĐẶT khi chưa có: người triển khai đặt sẵn biến môi trường thì phải
    thắng phỏng đoán của ta."""
    import pytesseract
    path = tesseract_path()
    if path is None:
        raise TesseractMissing(
            "không tìm thấy binary tesseract — đặt biến môi trường "
            f"{TESSERACT_ENV}, hoặc cài tesseract vào PATH")
    pytesseract.pytesseract.tesseract_cmd = path
    if not os.environ.get(TESSDATA_ENV):
        prefix = tessdata_prefix()
        if prefix:
            os.environ[TESSDATA_ENV] = prefix


def ocr_image(img, *, lang: str = OCR_LANG, psm: int = OCR_PSM) -> OcrResult:
    """Đọc chữ trong MỘT ảnh PIL. Ném `TesseractMissing` khi thiếu binary."""
    import pytesseract
    _dam_bao_moi_truong()
    tsv = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}")
    words = parse_tsv(tsv)
    mean = sum(w.conf for w in words) / len(words) if words else 0.0
    return OcrResult(words=words, text="\n".join(words_to_lines(words)),
                     mean_conf=mean)
```

- [ ] **Step 6: Chạy lại test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/ocr/test_engine.py -v`
Expected: PASS (4 test)

- [ ] **Step 7: Viết test dò đường dẫn (thuần, monkeypatch — không cần binary)**

```python
# Nối vào backend/tests/ocr/test_engine.py
import os

import pytest

from src.ocr import engine


def test_tesseract_path_uu_tien_bien_moi_truong(monkeypatch, tmp_path):
    gia = tmp_path / "tesseract.exe"
    gia.write_text("")
    monkeypatch.setenv(engine.TESSERACT_ENV, str(gia))
    assert engine.tesseract_path() == str(gia)


def test_tesseract_path_bo_qua_bien_tro_vao_cho_khong_ton_tai(monkeypatch, tmp_path):
    # Biến môi trường SAI không được che mất đường dò tiếp theo — nếu không,
    # một biến cũ còn sót lại trong shell sẽ làm cả tầng OCR chết câm.
    monkeypatch.setenv(engine.TESSERACT_ENV, str(tmp_path / "khong-co-that.exe"))
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/tesseract-gia")
    assert engine.tesseract_path() == "/usr/bin/tesseract-gia"


def test_dam_bao_moi_truong_nem_khi_thieu_binary(monkeypatch):
    monkeypatch.setattr(engine, "tesseract_path", lambda: None)
    with pytest.raises(engine.TesseractMissing):
        engine._dam_bao_moi_truong()


def test_dam_bao_moi_truong_KHONG_de_len_tessdata_nguoi_dung_da_dat(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "tesseract_path", lambda: str(tmp_path / "t.exe"))
    monkeypatch.setenv(engine.TESSDATA_ENV, "/cua-nguoi-trien-khai")
    monkeypatch.setattr(engine, "tessdata_prefix", lambda: "/phong-doan-cua-ta")
    engine._dam_bao_moi_truong()
    assert os.environ[engine.TESSDATA_ENV] == "/cua-nguoi-trien-khai"
```

- [ ] **Step 8: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/ocr/test_engine.py -v`
Expected: PASS (8 test)

- [ ] **Step 9: Viết test đọc ảnh THẬT (cần binary, có `skipif`)**

```python
# Nối vào backend/tests/ocr/test_engine.py
from PIL import Image, ImageDraw


@pytest.mark.skipif(engine.tesseract_path() is None, reason="chưa cài tesseract")
def test_ocr_image_doc_duoc_chu_tren_anh_tu_dung():
    img = Image.new("RGB", (900, 220), "white")
    ImageDraw.Draw(img).text((20, 60), "TONG CONG TAI SAN 280",
                             fill="black", font_size=64)
    kq = engine.ocr_image(img)
    assert "280" in kq.text
    assert kq.words, "phải đọc được ít nhất một từ"
    assert 0 < kq.mean_conf <= 100
    # Toạ độ phải THẬT, không phải 0 mặc định — bậc 2 dựng bảng dựa vào đây.
    assert any(w.left > 0 and w.width > 0 for w in kq.words)


@pytest.mark.skipif(engine.tesseract_path() is None, reason="chưa cài tesseract")
def test_ocr_image_anh_trang_tra_ve_rong_chu_khong_no():
    kq = engine.ocr_image(Image.new("RGB", (400, 200), "white"))
    assert kq.words == []
    assert kq.text == ""
    assert kq.mean_conf == 0.0
```

- [ ] **Step 10: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/ocr/test_engine.py -v`
Expected: PASS (10 test). `font_size` cần Pillow ≥ 10 — máy này có Pillow 12.3.0. Nếu bản Pillow khác không nhận tham số đó, dùng `ImageDraw.text` mặc định rồi phóng to ảnh (`img.resize((1800, 440))`) trước khi OCR, và ghi lại sai lệch trong báo cáo.

- [ ] **Step 11: Chạy suite nhanh, xác nhận không hồi quy**

Run: `cd backend && python -m pytest -m "not integration and not live" -q`
Expected: PASS, tổng test TĂNG so với baseline 2337.

- [ ] **Step 12: Commit**

```bash
git add backend/src/ocr backend/tests/ocr backend/requirements.txt
git commit -m "feat(ocr): tang 0 - may doc chu Tesseract, toa do + do tin cay tung tu"
```

---

## Task 2: `ocr/document.py` — tầng tài liệu: rasterise + đệm

**Files:**
- Create: `backend/src/ocr/document.py`
- Test: `backend/tests/ocr/test_document.py`

**Interfaces:**
- Consumes (Task 1): `ocr_image`, `OcrResult`, `OcrWord`, `tesseract_version`, `OCR_DPI`, `OCR_PSM`, `OCR_LANG`, `TesseractMissing` từ `src.ocr.engine`.
- Produces (dùng ở Task 4):
  - `Region` dataclass: `kind: str`, `text: str`, `mean_conf: float`, `bbox: tuple[int,int,int,int]`, `words: list[dict]`
  - `PageRead` dataclass: `page: int`, `regions: list[Region]`, `mean_conf: float`, `tu_dem: bool`
  - `read_page(path: str, pageno: int, *, dpi: int = OCR_DPI) -> PageRead` (pageno đếm từ **1**)
  - `PageRead.text` property → chữ của mọi vùng nối bằng `"\n"`
  - `cache_dir() -> str`, `config_fingerprint() -> str`, `ARTIFACT_VERSION = 1`
  - Biến môi trường `OCR_CACHE_ENV = "YOUDOO_OCR_CACHE"`

- [ ] **Step 1: Viết test cho dấu vân tay cấu hình (thuần, monkeypatch)**

```python
# backend/tests/ocr/test_document.py
from src.ocr import document


def test_van_tay_doi_khi_DPI_doi(monkeypatch):
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint(dpi=200)
    b = document.config_fingerprint(dpi=300)
    assert a != b


def test_van_tay_doi_khi_PHIEN_BAN_TESSERACT_doi(monkeypatch):
    # Đây là nửa mà `convert.py` đang THIẾU: nó khoá đệm chỉ theo hash tệp, nên
    # đổi tham số công cụ sẽ dùng lại bản cũ mà không ai biết (spec §7).
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint()
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.5.0")
    b = document.config_fingerprint()
    assert a != b


def test_van_tay_on_dinh_khi_khong_doi_gi(monkeypatch):
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    assert document.config_fingerprint() == document.config_fingerprint()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/ocr/test_document.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'src.ocr.document'`

- [ ] **Step 3: Viết khung `document.py` (vân tay + thư mục đệm)**

```python
# backend/src/ocr/document.py
"""Tầng tài liệu của tầng OCR — spec 2026-09-04-tang-ocr §3 (tầng 1).

PDF → ảnh từng trang → vùng CÓ KIỂU, có đệm trên đĩa. KHÔNG biết DB, chunk,
hay ai đang gọi mình.

BẬC 1 chỉ sinh vùng kiểu `text` (spec §14). Kiểu `table` (dựng từ toạ độ) và
`figure` (mô tả bằng VLM) là bậc 2/3, chờ có tài liệu scan thật — nhưng HỢP
ĐỒNG artifact dựng sẵn từ bây giờ để hai bậc sau không phải đổi kho đệm.
"""
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field

from . import engine

OCR_CACHE_ENV = "YOUDOO_OCR_CACHE"

# Tăng khi ĐỔI HÌNH DẠNG artifact (thêm/bớt trường, đổi nghĩa). Nó nằm trong
# dấu vân tay nên bản đệm cũ tự động thành lạc khoá, không cần xoá tay.
ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class Region:
    kind: str          # bậc 1: luôn "text"
    text: str
    mean_conf: float
    bbox: tuple[int, int, int, int]     # (left, top, right, bottom) theo pixel ảnh
    words: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PageRead:
    page: int
    regions: list[Region]
    mean_conf: float
    tu_dem: bool

    @property
    def text(self) -> str:
        return "\n".join(r.text for r in self.regions if r.text)


def cache_dir() -> str:
    d = os.environ.get(OCR_CACHE_ENV) or os.path.join(
        tempfile.gettempdir(), "youdoo_ocr")
    os.makedirs(d, exist_ok=True)
    return d


def config_fingerprint(*, dpi: int = engine.OCR_DPI, psm: int = engine.OCR_PSM,
                       lang: str = engine.OCR_LANG) -> str:
    """Dấu vân tay của MỌI thứ ảnh hưởng tới kết quả đọc.

    Khoá đệm = hash(nội dung tệp) + vân tay này. Thiếu nửa sau thì đổi PSM/DPI
    /model xong vẫn dùng lại bản cũ mà không ai biết — đúng lỗ hổng `convert.py`
    đang có, spec §7 yêu cầu không lặp lại."""
    raw = f"{ARTIFACT_VERSION}|{dpi}|{psm}|{lang}|{engine.tesseract_version()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/ocr/test_document.py -v`
Expected: PASS (3 test)

- [ ] **Step 5: Viết test cho đệm (đọc/ghi/lạc khoá), dùng OCR giả**

```python
# Nối vào backend/tests/ocr/test_document.py
import pytest

from src.ocr.engine import OcrResult, OcrWord


def _kq_gia(text="XIN CHAO", conf=91.5):
    w = OcrWord(text=text, conf=conf, left=10, top=20, width=100, height=30,
                line_id=(1, 1, 1))
    return OcrResult(words=[w], text=text, mean_conf=conf)


@pytest.fixture
def kho_tam(monkeypatch, tmp_path):
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    return tmp_path


def test_lan_dau_doc_that_lan_sau_lay_tu_dem(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    dem_goi = {"n": 0}

    def _fake_ocr(img, **kw):
        dem_goi["n"] += 1
        return _kq_gia()

    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", _fake_ocr)

    a = document.read_page(str(pdf), 1)
    b = document.read_page(str(pdf), 1)

    assert dem_goi["n"] == 1, "lượt hai phải lấy từ đệm, không đọc lại"
    assert a.tu_dem is False and b.tu_dem is True
    assert a.text == b.text == "XIN CHAO"
    assert b.regions[0].kind == "text"
    assert b.regions[0].words[0]["t"] == "XIN CHAO"


def test_doi_van_tay_cau_hinh_thi_KHONG_dung_lai_ban_cu(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", lambda img, **kw: _kq_gia())
    document.read_page(str(pdf), 1)

    # Đổi phiên bản tesseract = đổi vân tay = phải đọc lại, KHÔNG dùng bản cũ.
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.9.9")
    lai = document.read_page(str(pdf), 1)
    assert lai.tu_dem is False


def test_doi_noi_dung_tep_thi_KHONG_dung_lai_ban_cu(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-mot")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", lambda img, **kw: _kq_gia())
    document.read_page(str(pdf), 1)
    pdf.write_bytes(b"%PDF-HAI-khac-han")
    assert document.read_page(str(pdf), 1).tu_dem is False


def test_dem_hong_giua_chung_KHONG_lam_no_ca_luot_nap(kho_tam, monkeypatch, tmp_path):
    # Tệp đệm cụt (ghi dở, đĩa đầy, tiến trình bị giết) không được làm hỏng
    # việc nạp — đọc lại là đủ. Nếu ném ở đây thì một tệp rác vĩnh viễn sẽ
    # chặn đúng tài liệu đó mãi mãi, vì khoá đệm không bao giờ tự lành.
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", lambda img, **kw: _kq_gia())
    document.read_page(str(pdf), 1)
    for f in os.listdir(kho_tam):
        (kho_tam / f).write_text("{ khong phai json hop le")
    lai = document.read_page(str(pdf), 1)
    assert lai.tu_dem is False and lai.text == "XIN CHAO"
```

- [ ] **Step 6: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/ocr/test_document.py -v`
Expected: FAIL — `AttributeError: module 'src.ocr.document' has no attribute 'read_page'`

- [ ] **Step 7: Viết `read_page` + đệm**

```python
# Nối vào backend/src/ocr/document.py


def _hash_tep(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _duong_dem(path: str, pageno: int, van_tay: str) -> str:
    return os.path.join(cache_dir(), f"{_hash_tep(path)}-{van_tay}-p{pageno}.json")


def _anh_cua_trang(path: str, pageno: int, dpi: int):
    """Rasterise MỘT trang (đếm từ 1) thành ảnh PIL.

    `pypdfium2` đã có sẵn theo `pdfplumber` — không thêm phụ thuộc (spec §3)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return pdf[pageno - 1].render(scale=dpi / 72).to_pil()
    finally:
        pdf.close()


def _tu_json(data: dict) -> PageRead:
    regions = [Region(kind=r["kind"], text=r["text"], mean_conf=r["mean_conf"],
                      bbox=tuple(r["bbox"]), words=r["words"])
               for r in data["regions"]]
    return PageRead(page=data["page"], regions=regions,
                    mean_conf=data["mean_conf"], tu_dem=True)


def _ghi_nguyen_tu(duong: str, data: dict) -> None:
    """Ghi tạm rồi đổi tên — bài học đã trả giá ở `convert.py`: tệp cụt do
    timeout ở lại thì bẩn VĨNH VIỄN, vì khoá đệm không bao giờ tự lành."""
    tam = f"{duong}.tmp"
    with open(tam, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tam, duong)


def read_page(path: str, pageno: int, *, dpi: int = engine.OCR_DPI) -> PageRead:
    """Đọc MỘT trang PDF bằng ảnh (đếm từ 1). Ném `TesseractMissing` khi thiếu
    binary — người gọi quyết định biến nó thành cảnh báo hay từ chối."""
    van_tay = config_fingerprint(dpi=dpi)
    duong = _duong_dem(path, pageno, van_tay)
    if os.path.isfile(duong):
        try:
            with open(duong, encoding="utf-8") as f:
                return _tu_json(json.load(f))
        except (ValueError, KeyError, OSError):
            pass          # đệm hỏng → đọc lại, xem test `dem_hong_giua_chung`

    img = _anh_cua_trang(path, pageno, dpi)
    kq = engine.ocr_image(img)
    rong, cao = getattr(img, "size", (0, 0))
    # BẬC 1: đúng MỘT vùng kiểu `text` phủ cả trang. Phân vùng hình học (vùng
    # rộng không có hộp chữ = vùng hình) là bộ định tuyến của bậc 3 — chưa có
    # tài liệu scan có hình để hiệu chỉnh, nên chưa dựng (spec §14).
    region = Region(kind="text", text=kq.text, mean_conf=kq.mean_conf,
                    bbox=(0, 0, rong, cao),
                    words=[{"t": w.text, "c": w.conf, "l": w.left, "y": w.top,
                            "w": w.width, "h": w.height} for w in kq.words])
    data = {"artifact_version": ARTIFACT_VERSION, "page": pageno,
            "config": {"dpi": dpi, "psm": engine.OCR_PSM,
                       "lang": engine.OCR_LANG,
                       "tesseract": engine.tesseract_version()},
            "mean_conf": kq.mean_conf,
            "regions": [{"kind": region.kind, "text": region.text,
                         "mean_conf": region.mean_conf,
                         "bbox": list(region.bbox), "words": region.words}]}
    _ghi_nguyen_tu(duong, data)
    return PageRead(page=pageno, regions=[region], mean_conf=kq.mean_conf,
                    tu_dem=False)
```

- [ ] **Step 8: Chạy lại test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/ocr/test_document.py -v`
Expected: PASS (7 test)

- [ ] **Step 9: Viết test đọc PDF THẬT một trang (cần binary + kho)**

```python
# Nối vào backend/tests/ocr/test_document.py
from src.ocr.engine import tesseract_path

KHO_LUAT = "D:/Documents"


@pytest.mark.skipif(tesseract_path() is None or
                    not os.path.isfile(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf")),
                    reason="chưa có tesseract hoặc kho luật")
def test_read_page_tren_pdf_that(tmp_path, monkeypatch):
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    kq = document.read_page(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf"), 1)
    assert kq.page == 1 and kq.tu_dem is False
    assert len(kq.text) > 200, "trang luật thật phải ra vài trăm ký tự"
    assert kq.mean_conf > 50, f"độ tin cậy quá thấp: {kq.mean_conf}"
    assert kq.regions[0].kind == "text"
    # Đệm phải ghi ra tệp THẬT, không chỉ nằm trong bộ nhớ.
    assert len(os.listdir(tmp_path)) == 1
    assert document.read_page(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf"), 1).tu_dem
```

- [ ] **Step 10: Chạy test, ghi số thật**

Run: `cd backend && python -m pytest tests/ocr/test_document.py -v`
Expected: PASS (8 test). Ghi lại `mean_conf` thật quan sát được vào báo cáo — Task 5 cần nó khi chốt ngưỡng.

- [ ] **Step 11: Chạy suite nhanh**

Run: `cd backend && python -m pytest -m "not integration and not live" -q`
Expected: PASS, không hồi quy.

- [ ] **Step 12: Commit**

```bash
git add backend/src/ocr/document.py backend/tests/ocr/test_document.py
git commit -m "feat(ocr): tang 1 - rasterise tung trang + dem khoa theo hash & van tay cau hinh"
```

---

## Task 3: Cờ xuất xứ trong DB + quy tắc gộp BI QUAN

**Files:**
- Create: `backend/migrations/007_ocr_xuat_xu.sql`
- Modify: `backend/src/rag/schema.sql:18-34` (thêm 2 cột vào `CREATE TABLE rag_chunks`)
- Modify: `backend/src/rag/chunking.py` (hàm `chunk_text_blocks`)
- Modify: `backend/src/rag/ingest.py:183-190` (câu `INSERT INTO rag_chunks`)
- Modify: `docs/getting-started.md` (danh sách migration chạy tay)
- Test: `backend/tests/rag/test_chunking_xuat_xu.py`

**Interfaces:**
- Consumes: không phụ thuộc code Task 1/2 (chỉ dùng chung khái niệm bậc xuất xứ).
- Produces (dùng ở Task 4): `chunk_text_blocks` đọc hai khoá TUỲ CHỌN trên block dict — `source_kind: str` (vắng ⇒ `"text"`) và `ocr_conf: float | None` — rồi phát ra cùng tên khoá trên chunk dict. Hằng `_XUAT_XU_RANK` (`text` 0 < `ocr` 1 < `vision_description` 2) đặt trong `chunking.py`.

- [ ] **Step 1: Viết migration**

```sql
-- backend/migrations/007_ocr_xuat_xu.sql — cờ xuất xứ cho chunk sinh từ ảnh.
--
-- VÌ SAO NẰM TRONG DB, không nằm trong kho đệm OCR: đây là chiều "có đáng tin
-- không" mà retrieval và việc chống injection gián tiếp sẽ cần đọc được, và
-- nó phải sống sót qua mọi lần re-chunk (spec 2026-09-04-tang-ocr §8).
--
-- Ba bậc, tin cậy giảm dần: 'text' (đọc thẳng lớp text của tệp) > 'ocr' (đọc
-- bằng ảnh qua Tesseract) > 'vision_description' (mô tả hình bằng VLM — bậc 3,
-- chưa dùng). Mặc định 'text' vì toàn bộ corpus hiện tại đọc được lớp text.
--
-- ocr_conf NULL là HỢP LỆ và là trạng thái thường gặp: chỉ chunk có nguồn từ
-- ảnh mới có độ tin cậy để ghi.
--
-- Idempotent, an toàn khi chạy lại.
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS source_kind text NOT NULL DEFAULT 'text';
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS ocr_conf real;
```

- [ ] **Step 2: Thêm 2 cột vào `schema.sql` cho bản cài mới**

Trong `backend/src/rag/schema.sql`, khối `CREATE TABLE IF NOT EXISTS {schema}.rag_chunks (...)`, thêm hai dòng ngay TRƯỚC dòng `chunk_text    text NOT NULL,`:

```sql
    source_kind   text NOT NULL DEFAULT 'text',
    ocr_conf      real,
```

- [ ] **Step 3: Ghi migration mới vào tài liệu cài đặt**

Trong `docs/getting-started.md`, phần liệt kê các lệnh `docker cp backend\migrations\...`, thêm một dòng cùng khuôn cho `007_ocr_xuat_xu.sql` (giữ nguyên văn phong và thứ tự số của các dòng đang có). Nếu tài liệu có câu tổng kết đếm số migration, cập nhật con số đó.

- [ ] **Step 4: Viết test cho quy tắc gộp BI QUAN**

```python
# backend/tests/rag/test_chunking_xuat_xu.py
from src.rag.chunking import chunk_text_blocks


def test_block_khong_khai_gi_thi_chunk_la_text_conf_None():
    blocks = [{"text": "Câu thường.", "heading_level": None, "page": 1}]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["source_kind"] == "text"
    assert out[0]["ocr_conf"] is None


def test_mot_block_ocr_lam_ca_chunk_thanh_ocr():
    # BI QUAN: trộn text sạch với text đọc từ ảnh thì cả chunk chỉ đáng tin
    # bằng phần yếu nhất của nó — không được làm tròn lên (spec §8).
    blocks = [
        {"text": "Câu sạch.", "heading_level": None, "page": 1},
        {"text": "Câu từ ảnh.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 88.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert len(out) == 1
    assert out[0]["source_kind"] == "ocr"
    assert out[0]["ocr_conf"] == 88.0


def test_nhieu_block_ocr_thi_conf_lay_NHO_NHAT():
    blocks = [
        {"text": "A.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 95.0},
        {"text": "B.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 61.5},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["ocr_conf"] == 61.5


def test_bac_thap_nhat_thang_ke_ca_khi_dung_sau():
    blocks = [
        {"text": "A.", "heading_level": None, "page": 1,
         "source_kind": "vision_description"},
        {"text": "B.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 90.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["source_kind"] == "vision_description"


def test_block_atomic_giu_xuat_xu_cua_RIENG_no():
    # Hàng bảng là chunk riêng (B4) — nó không được "lây" xuất xứ của văn xuôi
    # đứng cạnh, và văn xuôi cũng không được lây của nó.
    blocks = [
        {"text": "Văn xuôi sạch.", "heading_level": None, "page": 1},
        {"text": "Cột 1: X | Cột 2: Y", "heading_level": None, "page": 1,
         "atomic": True, "source_kind": "ocr", "ocr_conf": 70.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    theo_text = {c["chunk_text"]: c for c in out}
    assert theo_text["Văn xuôi sạch."]["source_kind"] == "text"
    assert theo_text["Cột 1: X | Cột 2: Y"]["source_kind"] == "ocr"
    assert theo_text["Cột 1: X | Cột 2: Y"]["ocr_conf"] == 70.0
```

- [ ] **Step 5: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/rag/test_chunking_xuat_xu.py -v`
Expected: FAIL với `KeyError: 'source_kind'`

- [ ] **Step 6: Sửa `chunk_text_blocks`**

Hàm hiện tại gom thân mục vào `cur_body: list[tuple[str, bool]]` — `(text, atomic)`. Mở rộng thành bộ 4 để mang theo xuất xứ, rồi gộp bi quan khi phát chunk. Thay phần thân hàm (giữ nguyên chữ ký, giữ nguyên `doc_title`/`path_stack`/`_flush` và toàn bộ logic heading):

```python
# Thêm gần đầu backend/src/rag/chunking.py, cạnh các hằng khác
_XUAT_XU_RANK = {"text": 0, "ocr": 1, "vision_description": 2}


def _gop_bi_quan(items: list[tuple[str, str, float | None]]) -> tuple[str, float | None]:
    """Bậc xuất xứ THẤP TIN CẬY NHẤT + `ocr_conf` NHỎ NHẤT trong nhóm.

    Ghi thành hàm riêng vì đây đúng loại quyết định hay bị quyết ngầm và quyết
    sai: trộn một câu đọc-từ-ảnh vào một chunk văn bản sạch thì cả chunk chỉ
    đáng tin bằng phần yếu nhất (spec 2026-09-04-tang-ocr §8)."""
    kind = "text"
    for _text, k, _conf in items:
        if _XUAT_XU_RANK.get(k, 0) > _XUAT_XU_RANK[kind]:
            kind = k
    confs = [c for _text, _k, c in items if c is not None]
    return kind, (min(confs) if confs else None)
```

Trong `chunk_text_blocks`: đổi khai báo `cur_body`/`sections` sang bộ 4, hai chỗ `cur_body.append(...)` mang thêm xuất xứ, và vòng phát chunk gom xuất xứ theo từng piece:

```python
    sections: list[tuple[str, int | None, list[tuple[str, bool, str, float | None]]]] = []
    cur_body: list[tuple[str, bool, str, float | None]] = []
    ...
    for b in blocks:
        atomic = bool(b.get("atomic"))
        xuat_xu = b.get("source_kind", "text")
        conf = b.get("ocr_conf")
        ...
                cur_body.append((b["text"], atomic, xuat_xu, conf))   # nhánh heading bị đè
                continue
        ...
            cur_body.append((b["text"], atomic, xuat_xu, conf))       # nhánh thân
    _flush()

    out: list[dict] = []
    idx = 0
    for section_path, page, body in sections:
        # (text, source_kind, ocr_conf) cho từng mảnh sắp phát ra
        pieces: list[tuple[str, str, float | None]] = []
        run: list[tuple[str, str, float | None]] = []

        def _xa_run():
            if not run:
                return
            joined = " ".join(t for t, _k, _c in run).strip()
            if joined:
                kind, conf = _gop_bi_quan(run)
                manh = ([joined] if count_tokens(joined) <= MIN_CHUNK_TOKENS
                        else _split_section_text(joined))
                # Mọi mảnh cắt ra từ cùng một run thừa hưởng cùng xuất xứ: run
                # là MỘT khối văn bản liền, cắt nó không làm phần nào sạch hơn.
                pieces.extend((m, kind, conf) for m in manh)
            run.clear()

        for text, atomic, xuat_xu, conf in body:
            if atomic:
                _xa_run()
                pieces.append((text, xuat_xu, conf))
            else:
                run.append((text, xuat_xu, conf))
        _xa_run()

        for piece, kind, conf in pieces:
            out.append({
                "doc_id": doc_id, "source_file": source_file, "doc_title": doc_title,
                "section_path": section_path, "page": page,
                "sheet": None, "row_range": None, "columns": None,
                "chunk_index": idx, "token_count": count_tokens(piece),
                "chunk_text": piece,
                "source_kind": kind, "ocr_conf": conf,
            })
            idx += 1
    return out
```

- [ ] **Step 7: Chạy test mới + toàn bộ test chunking cũ**

Run: `cd backend && python -m pytest tests/rag/test_chunking_xuat_xu.py tests/rag/test_chunking_atomic.py tests/rag/test_chunking_text.py tests/rag/test_chunking_khong_duong_dan.py -v`
Expected: PASS toàn bộ — test cũ KHÔNG được đổi kết quả (bằng chứng trực tiếp rằng thêm hai khoá không đụng hành vi `.docx`/`.pptx`/PDF hiện có).

- [ ] **Step 8: Viết test cho câu INSERT (không cần DB thật)**

```python
# Nối vào backend/tests/rag/test_chunking_xuat_xu.py
from src.rag import ingest


def test_INSERT_co_hai_cot_moi_va_chiu_duoc_chunk_thieu_khoa():
    # Đường `.xlsx` (`chunk_xlsx_sheets`) KHÔNG đặt hai khoá này — INSERT phải
    # tự lùi về mặc định thay vì ném KeyError, đúng khuôn khoá tuỳ chọn
    # `atomic` của B4.
    import inspect
    src = inspect.getsource(ingest._ingest_known)
    assert "source_kind" in src and "ocr_conf" in src
    assert 'c.get("source_kind"' in src, "phải dùng .get() để đường xlsx không vỡ"
```

- [ ] **Step 9: Chạy test, xác nhận FAIL, rồi sửa `INSERT`**

Run: `cd backend && python -m pytest tests/rag/test_chunking_xuat_xu.py -v`
Expected: FAIL (chưa có cột trong câu INSERT)

Sửa `backend/src/rag/ingest.py`, câu `INSERT INTO rag_chunks`:

```python
            conn.execute(
                "INSERT INTO rag_chunks (doc_id, source_file, doc_title, section_path, page, "
                "sheet, row_range, columns, chunk_index, token_count, chunk_text, "
                "source_kind, ocr_conf, embedding, "
                "ts_vector) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, "
                "to_tsvector('simple', %s))",
                (c["doc_id"], c["source_file"], c["doc_title"], c["section_path"], c["page"],
                 c["sheet"], c["row_range"], c["columns"], c["chunk_index"], c["token_count"],
                 c["chunk_text"],
                 # `.get()` chứ không phải `[...]`: `chunk_xlsx_sheets` không
                 # đặt hai khoá này và không có lý do gì phải đặt.
                 c.get("source_kind", "text"), c.get("ocr_conf"),
                 vec,
                 segment_vi(index_text(c["section_path"], c["chunk_text"]))),
            )
```

- [ ] **Step 10: Chạy lại test + toàn bộ test ingest**

Run: `cd backend && python -m pytest tests/rag/test_chunking_xuat_xu.py tests/rag/test_ingest*.py -m "not integration and not live" -v`
Expected: PASS toàn bộ.

- [ ] **Step 11: Chạy suite nhanh**

Run: `cd backend && python -m pytest -m "not integration and not live" -q`
Expected: PASS, không hồi quy.

- [ ] **Step 12: Commit**

```bash
git add backend/migrations/007_ocr_xuat_xu.sql backend/src/rag/schema.sql \
        backend/src/rag/chunking.py backend/src/rag/ingest.py \
        backend/tests/rag/test_chunking_xuat_xu.py docs/getting-started.md
git commit -m "feat(rag): co xuat xu source_kind/ocr_conf + quy tac gop BI QUAN"
```

---

## Task 4: Nối vào `parse_pdf` — trang rỗng thì đọc bằng ảnh

**Files:**
- Modify: `backend/src/rag/parse.py` (import + hàm `parse_pdf`, thêm hàm phụ `_doc_trang_bang_anh`)
- Test: `backend/tests/rag/test_parse_pdf_ocr.py`

**Interfaces:**
- Consumes (Task 2): `from src.ocr.document import read_page`, `PageRead.text`, `PageRead.mean_conf`; (Task 1): `TesseractMissing`.
- Consumes (Task 3): khoá tuỳ chọn `source_kind`/`ocr_conf` trên block dict.
- Produces: `parse_pdf` giữ NGUYÊN chữ ký `(path) -> tuple[list[dict], list[tuple[str, str]]]`; block sinh từ trang đọc-bằng-ảnh mang thêm `source_kind="ocr"` và `ocr_conf=<mean_conf>`.

- [ ] **Step 1: Viết test wiring (OCR giả, không cần binary)**

```python
# backend/tests/rag/test_parse_pdf_ocr.py
"""Trang KHÔNG có lớp text đi qua tầng OCR — spec 2026-09-04-tang-ocr §11."""
import pytest

from src.ocr.document import PageRead, Region


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, pages_text):
        self.pages = [_FakePage(t) for t in pages_text]


class _FakePlumberPage:
    def find_tables(self, table_settings=None):
        return []


class _FakePlumberPDF:
    def __init__(self, n):
        self.pages = [_FakePlumberPage() for _ in range(n)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _doc_gia(text, conf=90.0):
    r = Region(kind="text", text=text, mean_conf=conf, bbox=(0, 0, 100, 100))
    return PageRead(page=1, regions=[r], mean_conf=conf, tu_dem=False)


def _dung_canh(monkeypatch, pypdf_pages, ocr_text="Điều 1. Chữ đọc từ ảnh.",
               conf=90.0):
    import pypdf
    import pdfplumber
    from src.rag import parse
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: _FakeReader(pypdf_pages))
    monkeypatch.setattr(pdfplumber, "open",
                        lambda path: _FakePlumberPDF(len(pypdf_pages)))
    monkeypatch.setattr(parse, "read_page",
                        lambda path, pageno, **kw: _doc_gia(ocr_text, conf))
    return parse


def test_trang_RONG_thi_doc_bang_anh_va_gan_co_xuat_xu(monkeypatch):
    parse = _dung_canh(monkeypatch, [""])
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert [b["text"] for b in blocks] == ["Điều 1. Chữ đọc từ ảnh."]
    assert blocks[0]["source_kind"] == "ocr"
    assert blocks[0]["ocr_conf"] == 90.0
    assert warnings == []


def test_trang_CO_chu_thi_KHONG_goi_OCR(monkeypatch):
    # Bất biến quan trọng nhất của đợt này: tài liệu hiện có (100% đọc được
    # lớp text) không được đổi một bit nào.
    import pypdf
    import pdfplumber
    from src.rag import parse
    monkeypatch.setattr(pypdf, "PdfReader",
                        lambda path: _FakeReader(["Điều 1. Chữ có sẵn."]))
    monkeypatch.setattr(pdfplumber, "open", lambda path: _FakePlumberPDF(1))

    def _no(*a, **kw):
        raise AssertionError("KHÔNG được gọi OCR cho trang đã có lớp text")

    monkeypatch.setattr(parse, "read_page", _no)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert [b["text"] for b in blocks] == ["Điều 1. Chữ có sẵn."]
    assert "source_kind" not in blocks[0], "khoá chỉ đặt khi thật sự đọc từ ảnh"


def test_chi_trang_RONG_di_qua_OCR_trong_tai_lieu_HON_HOP(monkeypatch):
    parse = _dung_canh(monkeypatch, ["Điều 1. Có chữ.", "", "Điều 3. Có chữ."])
    blocks, _ = parse.parse_pdf("x.pdf")
    theo_trang = {b["page"]: b for b in blocks}
    assert theo_trang[1].get("source_kind") is None
    assert theo_trang[2]["source_kind"] == "ocr"
    assert theo_trang[3].get("source_kind") is None


def test_OCR_ra_gan_RONG_thi_canh_bao_CO_TEN_chu_khong_im_lang(monkeypatch):
    parse = _dung_canh(monkeypatch, [""], ocr_text="   ")
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert blocks == []
    assert len(warnings) == 1
    where, reason = warnings[0]
    assert "trang 1" in where
    assert "rỗng" in reason.lower()


def test_THIEU_BINARY_thi_bao_co_ten_chu_khong_lam_vo_ca_luot_nap(monkeypatch):
    from src.ocr.engine import TesseractMissing
    parse = _dung_canh(monkeypatch, [""])

    def _thieu(path, pageno, **kw):
        raise TesseractMissing("không tìm thấy binary tesseract")

    monkeypatch.setattr(parse, "read_page", _thieu)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert blocks == []
    assert len(warnings) == 1 and "tesseract" in warnings[0][1].lower()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/rag/test_parse_pdf_ocr.py -v`
Expected: FAIL — `AttributeError: module 'src.rag.parse' has no attribute 'read_page'`

- [ ] **Step 3: Thêm import vào `parse.py`**

Ngay dưới khối import hiện có ở đầu `backend/src/rag/parse.py` (sau `from .pdf_table import ...`), thêm — dùng dạng import TUYỆT ĐỐI vì `ocr` là package ANH EM của `rag`, đúng tiền lệ `from src.cli_console import use_utf8_streams` trong `ingest.py`:

```python
from src.ocr.document import read_page
from src.ocr.engine import TesseractMissing
```

Import ở CẤP MODULE (không phải trong hàm) để test monkeypatch được `parse.read_page` — và vì nó không kéo theo phụ thuộc nặng: `document.py` chỉ import `pypdfium2`/`pytesseract` khi thật sự đọc.

- [ ] **Step 4: Viết hàm phụ `_doc_trang_bang_anh`**

Đặt ngay TRƯỚC `def parse_pdf` trong `backend/src/rag/parse.py`:

```python
def _doc_trang_bang_anh(path: str, pageno: int
                        ) -> tuple[list[str], float | None, tuple[str, str] | None]:
    """Đọc MỘT trang không có lớp text bằng ảnh.

    Trả `(dòng, mean_conf, cảnh_báo)`. Hỏng thì to tiếng NHƯNG không làm vỡ cả
    lượt nạp: cảnh báo mang tên trang đi tiếp qua `IngestReport`, và nếu cuối
    cùng cả tệp không sinh được block nào thì `_ingest_known` đã sẵn ném
    `IngestError` — tệp bị TỪ CHỐI CÓ TÊN, đúng hạ tầng Kế hoạch 1 dựng
    (spec 2026-09-04-tang-ocr §12). Không phát minh cơ chế mới.
    """
    try:
        kq = read_page(path, pageno)
    except TesseractMissing as e:
        return [], None, (f"trang {pageno}",
                          f"trang không có lớp text và không đọc được bằng ảnh: {e}")
    except Exception as e:                      # noqa: BLE001
        # Một trang hỏng (PDF vỡ, ảnh không rasterise được) không được kéo
        # theo cả tài liệu — nhưng phải GỌI TÊN, không nuốt.
        return [], None, (f"trang {pageno}",
                          f"đọc trang bằng ảnh thất bại: {type(e).__name__}: {e}")
    lines = _lines_tu_text(kq.text)
    if not lines:
        return [], None, (f"trang {pageno}",
                          "đọc bằng ảnh ra text RỖNG — trang có thể là ảnh trắng "
                          "hoặc bản scan hỏng; KHÔNG nạp gì cho trang này")
    return lines, kq.mean_conf, None
```

- [ ] **Step 5: Cắm điểm gọi vào `parse_pdf`**

Trong vòng lặp lượt 1 của `parse_pdf`, ngay SAU dòng `text_toan_trang = _lines_tu_text(page.extract_text() or "")` và TRƯỚC `pages_cho_furniture.append(text_toan_trang)`, chèn:

```python
            # "Rỗng" nghĩa là KHÔNG CÒN DÒNG NÀO sau bước strip — không phải
            # "ít chữ". Máy scan đời mới thường nhúng sẵn một lớp OCR kém nên
            # trang scan có thể trả về vài ký tự rác thay vì rỗng hẳn; KHÔNG
            # đặt ngưỡng "dưới N ký tự" ở đây vì chưa có tài liệu scan thật để
            # hiệu chỉnh N, và hằng số rút từ không khí là thứ dự án này cấm
            # (spec 2026-09-04-tang-ocr §11).
            if not text_toan_trang:
                text_toan_trang, conf, canh_bao = _doc_trang_bang_anh(path, pageno)
                if canh_bao:
                    all_warnings.append(canh_bao)
                if text_toan_trang:
                    ocr_pages[pageno] = conf
```

Khai `ocr_pages: dict[int, float | None] = {}` cùng chỗ với `pages`/`pages_cho_furniture`.

Trong vòng lặp lượt 2, thay chỗ dựng block văn xuôi:

```python
            for text in lines:
                if _normalize_digits(text) in furniture:
                    continue
                blk = {"text": text, "heading_level": heading_level(text),
                       "page": pageno}
                if pageno in ocr_pages:
                    blk["source_kind"] = "ocr"
                    blk["ocr_conf"] = ocr_pages[pageno]
                blocks.append(blk)
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/rag/test_parse_pdf_ocr.py -v`
Expected: PASS (5 test)

- [ ] **Step 7: Chạy toàn bộ test PDF/chunking cũ — bất biến "không đụng trang có chữ"**

Run: `cd backend && python -m pytest tests/rag/test_parse_pdf.py tests/rag/test_pdf_table.py tests/rag/test_chunking_atomic.py -v`
Expected: PASS toàn bộ, không test nào đổi kết quả.

- [ ] **Step 8: Nghiệm thu đầu-cuối bằng một PDF THẬT KHÔNG có lớp text**

Corpus hiện tại không có tệp scan nào, nên tự dựng một tệp: `Pillow` lưu ảnh thành PDF được, cho ra một PDF chỉ có ảnh — đúng thứ cần.

```python
# Nối vào backend/tests/rag/test_parse_pdf_ocr.py
import os

from PIL import Image, ImageDraw

from src.ocr.engine import tesseract_path


@pytest.mark.skipif(tesseract_path() is None, reason="chưa cài tesseract")
def test_dau_cuoi_PDF_chi_co_anh_van_ra_chunk_mang_co_ocr(tmp_path, monkeypatch):
    from src.ocr import document
    from src.rag.chunking import chunk_text_blocks
    from src.rag.parse import parse_pdf
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path / "dem"))

    img = Image.new("RGB", (1700, 600), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 60), "Dieu 1. Pham vi dieu chinh", fill="black", font_size=70)
    d.text((40, 220), "Tong cong tai san 280", fill="black", font_size=70)
    pdf_path = tmp_path / "scan-gia.pdf"
    img.save(pdf_path, "PDF", resolution=200.0)

    blocks, warnings = parse_pdf(str(pdf_path))
    assert blocks, f"PDF chỉ có ảnh phải ra block, warnings={warnings}"
    assert all(b["source_kind"] == "ocr" for b in blocks)
    assert any("280" in b["text"] for b in blocks)

    chunks = chunk_text_blocks(blocks, doc_id="scan", source_file=str(pdf_path))
    assert chunks and all(c["source_kind"] == "ocr" for c in chunks)
    assert all(c["ocr_conf"] is not None and c["ocr_conf"] > 0 for c in chunks)
```

- [ ] **Step 9: Chạy test đầu-cuối, ghi số thật**

Run: `cd backend && python -m pytest tests/rag/test_parse_pdf_ocr.py -v`
Expected: PASS (6 test). Ghi lại `ocr_conf` quan sát được vào báo cáo.

- [ ] **Step 10: Chạy suite nhanh**

Run: `cd backend && python -m pytest -m "not integration and not live" -q`
Expected: PASS, không hồi quy.

- [ ] **Step 11: Commit**

```bash
git add backend/src/rag/parse.py backend/tests/rag/test_parse_pdf_ocr.py
git commit -m "feat(rag): trang PDF khong co lop text tu dong doc bang anh (OCR bac 1)"
```

---

## Task 5: Cổng tự nuôi + nghiệm thu corpus thật + ghi chú thực thi

**Files:**
- Create: `backend/tests/ocr/test_cong_tu_nuoi.py`
- Modify: `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md` (nối phần "Tầng OCR bậc 1")

**Interfaces:**
- Consumes: toàn bộ Task 1-4.
- Produces: không có API mới — đây là task NGHIỆM THU.

- [ ] **Step 1: ĐO ngưỡng trước khi viết cổng — KHÔNG kế thừa số cũ**

Spec §4.1 ghi recall TB `0,865`, nhưng đó đo trên **3 trang bảng** của một tài liệu. Controller đo lại 2026-09-05 trên `luat-thuexuatnhapkhau.pdf` (PSM 6, 200 DPI) được `0,989 / 0,991 / 0,947` (TB `0,976`) — **cao hơn hẳn**, vì tập trang khác. Hai con số không mâu thuẫn; chúng đo hai thứ khác nhau. Vì vậy phải tự đo trên ĐÚNG tập trang mà cổng sẽ chạy.

Viết script đo tạm (không commit) tính recall theo TỪ cho **ít nhất 6 trang trải trên ít nhất 2 tài liệu, BẮT BUỘC có trang bảng** (ca khó — đường kẻ bảng bị đọc thành ký tự, thứ tự cột khác). Gợi ý tập trang: `D:/Documents/luat-thuegtgt.pdf` trang 1, 5; `D:/Documents/luat-thuexuatnhapkhau.pdf` trang 3, 6, 13, 20.

```python
import os, re
os.environ.setdefault("TESSDATA_PREFIX", r"C:/Users/ADMIN/.tessdata")
import pypdf
from src.ocr.document import read_page

def _tu(s):
    return [w for w in re.findall(r"\w+", s.lower(), re.UNICODE) if w]

def recall(tep, trang):
    goc = _tu(pypdf.PdfReader(tep).pages[trang - 1].extract_text() or "")
    doc = set(_tu(read_page(tep, trang).text))
    return sum(1 for w in goc if w in doc) / max(len(goc), 1)
```

Ghi TỪNG số vào báo cáo. **Quy tắc chốt ngưỡng**: `NGUONG = làm tròn xuống 2 chữ số của (min quan sát được − 0,05)`. Ví dụ min `0,947` → `0,89`. Biên `0,05` là chỗ cho biến động giữa các máy/phiên bản tesseract, KHÔNG phải chỗ cho hồi quy thật.

**Nếu có trang nào recall dưới 0,80**: dừng lại, ghi rõ trang nào và số bao nhiêu, báo `NEEDS_CONTEXT` — đừng hạ ngưỡng xuống dưới 0,80 để "cho xanh"; một cổng đặt dưới mức đó không còn phân biệt được "OCR hoạt động" với "OCR hỏng".

- [ ] **Step 2: Viết cổng tự nuôi với ngưỡng vừa đo**

```python
# backend/tests/ocr/test_cong_tu_nuoi.py
"""Cổng TỰ NUÔI — spec 2026-09-04-tang-ocr §13.

Corpus hôm nay có 0 tài liệu cần đọc bằng ảnh. Một thành phần không ai chạy
qua thì CHẾT ÂM THẦM — dự án đã trả giá ba lần (reranker chết 6 tuần; chân
sparse chết từ ngày đầu, 0/64 câu; riêng Kế hoạch 1 đếm được TÁM lần "cổng
trông như đang gác nhưng không đo gì").

Cơ chế: lấy trang ĐÃ CÓ lớp text → rasterise → vứt lớp text → đọc lại bằng
ảnh → so ngược. Corpus tự sinh đáp án, không gán tay ô nào.

Thước là RECALL THEO TỪ, không phải độ giống chuỗi: `SequenceMatcher` từng cho
0,46 và suýt dẫn tới kết luận "OCR tiếng Việt kém" — thật ra chữ nhận gần đúng
hết, điểm thấp do THỨ TỰ ĐỌC khác và đường kẻ bảng bị đọc thành ký tự.

GIỚI HẠN nói thẳng: ảnh rasterise SẠCH HƠN scan đời thật. Cổng này chứng minh
"còn sống và đại khái đúng", KHÔNG chứng minh "chịu được scan đời thật".
"""
import os
import re

import pypdf
import pytest

from src.ocr.document import read_page
from src.ocr.engine import tesseract_path

KHO_LUAT = "D:/Documents"

# NGƯỠNG ĐO ĐƯỢC 2026-09-05, KHÔNG phải số kế thừa từ spec (spec ghi 0,865
# nhưng đo trên tập trang khác — 3 trang bảng của một tài liệu).
# Số thật từng trang ghi trong ghi chú thực thi mục "Tầng OCR bậc 1".
NGUONG_RECALL = 0.89        # <-- thay bằng số Step 1 tính ra

TAP_TRANG = [
    ("luat-thuegtgt.pdf", 1),
    ("luat-thuegtgt.pdf", 5),
    ("luat-thuexuatnhapkhau.pdf", 3),
    ("luat-thuexuatnhapkhau.pdf", 6),
    ("luat-thuexuatnhapkhau.pdf", 13),     # trang BẢNG — ca khó, cố ý giữ
    ("luat-thuexuatnhapkhau.pdf", 20),
]


def _tu(s: str) -> list[str]:
    return [w for w in re.findall(r"\w+", s.lower(), re.UNICODE) if w]


def _recall_tu(goc: str, doc: str) -> float:
    g, o = _tu(goc), set(_tu(doc))
    return sum(1 for w in g if w in o) / max(len(g), 1)


def _co_kho() -> bool:
    return all(os.path.isfile(os.path.join(KHO_LUAT, t)) for t, _ in TAP_TRANG)


@pytest.mark.skipif(tesseract_path() is None or not _co_kho(),
                    reason="chưa có tesseract hoặc kho luật")
@pytest.mark.parametrize("tep,trang", TAP_TRANG)
def test_cong_tu_nuoi_duong_doc_bang_anh_con_song(tep, trang, tmp_path, monkeypatch):
    from src.ocr import document
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    duong = os.path.join(KHO_LUAT, tep)
    goc = pypdf.PdfReader(duong).pages[trang - 1].extract_text() or ""
    assert _tu(goc), f"{tep} tr.{trang} không có lớp text — chọn sai trang mẫu"
    r = _recall_tu(goc, read_page(duong, trang).text)
    assert r >= NGUONG_RECALL, f"{tep} tr.{trang}: recall {r:.3f} < {NGUONG_RECALL}"
```

- [ ] **Step 3: Chạy cổng, xác nhận XANH trên cả 6 trang**

Run: `cd backend && python -m pytest tests/ocr/test_cong_tu_nuoi.py -v`
Expected: 6 PASSED. Ghi từng con số recall vào báo cáo.

- [ ] **Step 4: PHÉP THỬ PHÁ — cổng phải biết ĐỎ**

Một cổng chưa từng thấy đỏ là cổng không đo gì. Đột biến có căn cứ: spec §4.1 đo PSM 3 (mặc định của tesseract) cho recall TB `0,569`, có trang xuống `0,256`. Chạy TẠM (không commit) với `psm=3` bằng cách sửa `engine.OCR_PSM` trong một phiên python, đo lại đúng 6 trang trên:

```python
from src.ocr import engine, document
engine.OCR_PSM = 3          # đột biến
# ... đo lại recall 6 trang như Step 1, in ra
```

Expected: recall tụt rõ rệt, ít nhất một trang xuống DƯỚI `NGUONG_RECALL` → cổng sẽ đỏ. Ghi số thật vào báo cáo, rồi khôi phục.

**Nếu PSM 3 KHÔNG làm trang nào xuống dưới ngưỡng**: đó là tín hiệu ngưỡng quá lỏng — báo cáo rõ, đề xuất ngưỡng chặt hơn dựa trên số vừa đo, và ĐỪNG lặng lẽ bỏ qua bước này.

- [ ] **Step 5: Nghiệm thu KHÔNG hồi quy trên corpus PDF thật**

Corpus hiện tại 100% có lớp text ⇒ tầng OCR không được kích hoạt lần nào, và output phải y hệt trước đợt này.

```bash
cd backend && python -c "
import glob
from src.rag.parse import parse_pdf
tong = 0
for f in glob.glob('d:/Youdoo/tmp-docs/*.pdf') + glob.glob('d:/Documents/luat-*.pdf'):
    blocks, warnings = parse_pdf(f)
    n_ocr = sum(1 for b in blocks if b.get('source_kind') == 'ocr')
    tong += n_ocr
    if n_ocr or warnings:
        print(f, len(blocks), 'blocks,', n_ocr, 'ocr,', len(warnings), 'warnings')
print('TONG block OCR tren toan corpus =', tong, '(ky vong 0)')
"
```

Expected: `TONG block OCR = 0`. Nếu KHÁC 0, dừng lại điều tra: hoặc có tệp thật sự thiếu lớp text (phát hiện đáng giá, ghi lại), hoặc điều kiện "rỗng" bắt nhầm (bug, phải sửa).

- [ ] **Step 6: Đối chiếu byte-identical với bản trước đợt OCR**

```bash
cd backend && git show 8085815:backend/src/rag/parse.py > /tmp/parse_truoc_ocr.py 2>/dev/null || \
  git show 8085815:backend/src/rag/parse.py > "$TEMP/parse_truoc_ocr.py"
```

Rồi so từng block của vài tệp đại diện (ít nhất `bieumau_bctc_hopnhat.pdf`, `ssc_bieumau.pdf`, `luat-thuexuatnhapkhau.pdf`) giữa hàm cũ và hàm mới — cùng cách B4 đã làm: nạp bản cũ vào một module tạm, chạy song song, so `text`/`heading_level`/`page` từng block. Xoá tệp tạm ngay sau khi đo (`git status` phải sạch). Ghi kết quả vào báo cáo.

Expected: khớp 100%.

- [ ] **Step 7: Nối phần "Tầng OCR bậc 1" vào ghi chú thực thi**

Mở `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md`, đọc phần "B4" ở cuối để bắt đúng văn phong/mức chi tiết, rồi nối mục mới ở CUỐI file theo cùng khuôn (Kết quả / Khó khăn đã gặp / Giả thuyết bị số đo bác bỏ / Hướng đã chọn / Giới hạn còn lại), gồm:

- recall THẬT từng trang (Step 1/3) và ngưỡng đã chốt + lý do chọn biên 0,05
- kết quả phép thử phá PSM 3 (Step 4)
- `TONG block OCR = 0` trên corpus thật + kết quả byte-identical (Step 5/6)
- `mean_conf` quan sát được trên PDF thật (Task 2 Step 10) và trên PDF ảnh tự dựng (Task 4 Step 9)
- giới hạn CÒN NGUYÊN, nói thẳng: chưa đo trên scan đời thật (nhiễu/nghiêng/dấu mộc); ngưỡng confidence để TỪ CHỐI trang vẫn CHƯA CHỐT (bậc 1 chỉ từ chối khi text RỖNG hẳn — mọi ngưỡng conf khác cần tài liệu scan thật để hiệu chỉnh); bậc 2 (bảng) và bậc 3 (VLM) chưa làm; `TESSDATA_PREFIX`/đường dẫn binary vẫn là đường dẫn máy cá nhân có fallback.

- [ ] **Step 8: Chạy suite nhanh lần cuối + ghi số**

Run: `cd backend && python -m pytest -m "not integration and not live" -q`
Expected: PASS. Ghi số cuối so với baseline 2337.

- [ ] **Step 9: Commit**

```bash
git add backend/tests/ocr/test_cong_tu_nuoi.py \
        docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md
git commit -m "test(ocr): cong tu nuoi + nghiem thu bac 1 tren corpus that"
```
