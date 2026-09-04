# B3 — Word suy phân cấp từ chữ — kế hoạch thực thi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tài liệu Word không dùng style Heading vẫn suy được phân cấp từ mẫu chữ, và không tài liệu nào còn nhúng đường dẫn tệp vào vector embedding.

**Architecture:** Một hàm mới `docx_heading_levels(texts) -> list[int|None]` nhận CẢ tài liệu và trả cả mảng cấp — vì quy tắc "đánh số trần phải tự chứng minh" cần bằng chứng ở phạm vi tài liệu. Nó dùng lại các regex có sẵn của `heading_level()` (đường PDF luật KHÔNG đổi một bit) nhưng xếp thứ tự kiểm khác và thêm bốn mẫu hành chính. `parse_docx` thành hai lượt để gọi được nó. Kèm một bản sửa một dòng ở `chunking.py` cho lỗi chung mọi định dạng.

**Tech Stack:** Python 3.11, `python-docx`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-b3-word-phan-cap-design.md` — đọc trước khi bắt đầu, đặc biệt mục 4 (thang cấp), mục 5 (quy tắc bằng chứng) và mục 10 (cổng nghiệm thu).

## Global Constraints

- **Định danh trong MÃ SẢN PHẨM đặt tên tiếng Anh.** Chú thích, docstring, thông điệp lỗi viết tiếng Việt. *(Tên hàm test tiếng Việt là quy ước sẵn có của dự án.)*
- **Lệnh test luôn kèm** `-m "not integration and not live"` **và** `PYTHONIOENCODING=utf-8`.
- **Worktree KHÔNG có `.venv` riêng.** Dùng interpreter cây chính với cwd trong worktree: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest ...`. Chạy mọi lệnh từ `d:/Youdoo/.claude/worktrees/tang-nap-tai-lieu-1/backend`.
- **Không hằng số rút từ không khí.** Thang cấp ở Task 1 là ĐỀ XUẤT; Task 4 hiệu chỉnh trên 12 tệp thật và chốt kèm bảng đo.
- **Kiểm bằng sản phẩm, không kiểm bằng mã thoát.** Mỗi cơ chế mới phải có phép thử phá chứng minh cổng đỏ được.
- **Đường PDF không được đổi một bit** — `heading_level()` và `parse_pdf` không được sửa. Bằng chứng là suite hiện có giữ nguyên số.
- Suite hiện tại: **2283 passed, 1 skipped, 74 deselected**.

---

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/src/rag/parse.py` | **Sửa.** Thêm thang cấp docx, 4 mẫu mới, `docx_heading_levels()`; `parse_docx` thành hai lượt. Đặt cạnh `heading_level()` — chưa đáng tách module riêng (spec mục 6). |
| `backend/src/rag/chunking.py` | **Sửa.** Một dòng: `doc_title` không lùi về `source_file`. |
| `backend/tests/rag/test_docx_heading.py` | **Tạo mới.** Bộ dò, thuần dữ liệu `list[str]`, không cần tệp `.docx`. |
| `backend/tests/rag/test_parse_docx_phan_cap.py` | **Tạo mới.** `parse_docx` hai lượt + ánh xạ style, fixture tự dựng. |
| `backend/tests/rag/test_chunking_khong_duong_dan.py` | **Tạo mới.** Chân đối chứng cho bản sửa `chunking.py`. |
| `backend/tests/rag/test_docx_kho_that.py` | **Tạo mới.** Nghiệm thu `live` trên 12 tệp thật. |

---

### Task 1: Bộ dò phân cấp từ chữ cho docx

**Files:**
- Modify: `backend/src/rag/parse.py` (thêm sau `heading_level()`, khoảng dòng 84)
- Create: `backend/tests/rag/test_docx_heading.py`

**Interfaces:**
- Consumes: `_CHUONG_RE`, `_MUC_RE`, `_DIEU_RE`, `heading_level()` — đã có sẵn cùng module.
- Produces:
  - `parse.DOCX_LEVEL: dict[str, int]` — thang cấp docx.
  - `parse.STYLE_SCALE: int = 10` — hệ số ánh xạ cấp style Word sang thang docx.
  - `parse.docx_heading_levels(texts: list[str]) -> list[int | None]`

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_docx_heading.py`:

```python
# backend/tests/rag/test_docx_heading.py
"""Suy phân cấp từ chữ cho .docx — spec 2026-09-04 mục 4, 5, 6.

Hàm nhận CẢ TÀI LIỆU (`list[str]`) chứ không chấm từng dòng độc lập, vì quy
tắc "đánh số trần phải tự chứng minh" cần bằng chứng ở phạm vi tài liệu.
Không test nào ở đây cần một tệp .docx thật — module là lá thuần.
"""
from src.rag.parse import DOCX_LEVEL, docx_heading_levels


def test_tu_khoa_PHAN_nhan_thang_khong_can_bang_chung():
    """`PHẦN`/`Chương`/`Mục` là TỪ KHOÁ, gần như không bao giờ là văn xuôi,
    nên không cần bằng chứng như nhóm đánh số trần."""
    out = docx_heading_levels(["PHẦN I - QUY ĐỊNH CHUNG", "Nội dung nào đó."])
    assert out[0] == DOCX_LEVEL["phan"]
    assert out[1] is None


def test_mot_muc_La_Ma_dung_mot_minh_KHONG_phai_tieu_de():
    """Bằng chứng thiếu: chỉ có `I.`, không có `II.`. Một chữ cái lạc giữa
    văn xuôi không được thành tiêu đề."""
    out = docx_heading_levels(["I. Đặc điểm hoạt động", "Công ty cổ phần."])
    assert out[0] is None


def test_hai_muc_La_Ma_ke_tiep_trong_day_thi_ca_hai_la_tieu_de():
    out = docx_heading_levels(["I. Đặc điểm hoạt động",
                               "Công ty cổ phần.",
                               "II. Kỳ kế toán"])
    assert out[0] == DOCX_LEVEL["roman"]
    assert out[2] == DOCX_LEVEL["roman"]
    assert out[1] is None


def test_bang_chung_khong_doi_hoi_hai_dong_LIEN_NHAU():
    """"Kế tiếp trong DÃY", không phải "kề nhau trên trang" — `I.` và `II.`
    cách nhau 3 dòng vẫn là bằng chứng hợp lệ. Hiểu nhầm chỗ này thì quy tắc
    gần như không bao giờ kích hoạt."""
    out = docx_heading_levels(["I. Mục một", "a", "b", "c", "II. Mục hai"])
    assert out[0] == DOCX_LEVEL["roman"]
    assert out[4] == DOCX_LEVEL["roman"]


def test_so_tran_co_con_mang_cung_tien_to_thi_la_tieu_de():
    """`12.` là tiêu đề VÌ `12.1` tồn tại — bằng chứng nằm trong chính tài
    liệu. Đây là ca thật của `b09-dn.docx`: trước bản sửa, CON là tiêu đề mà
    CHA thì không, bất nhất còn tệ hơn cả hai thái cực."""
    out = docx_heading_levels(["12. Tài sản sinh học",
                               "12.1. Tài sản sinh học khác",
                               "12.2. Súc vật cho sản phẩm"])
    assert out[0] == DOCX_LEVEL["arabic"]


def test_cha_dung_cap_CAO_HON_con():
    out = docx_heading_levels(["12. Tài sản sinh học",
                               "12.1. Tài sản sinh học khác"])
    assert out[0] < out[1], "cấp nhỏ hơn = cao hơn trong cây"


def test_so_tran_khong_co_bang_chung_nao_thi_KHONG_phai_tieu_de():
    out = docx_heading_levels(["7. Một khoản lẻ nằm giữa văn xuôi.",
                               "Câu tiếp theo không đánh số."])
    assert out[0] is None


def test_dong_IN_HOA_van_duoc_giu_nhu_truoc():
    out = docx_heading_levels(["BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH", "Nội dung."])
    assert out[0] == DOCX_LEVEL["upper"]
    assert out[1] is None


def test_muc_La_Ma_IN_HOA_CUNG_CAP_voi_muc_La_Ma_thuong():
    """Cùng một họ phải cùng cấp bất kể viết hoa. Nếu nhánh IN HOA được kiểm
    TRƯỚC nhánh đánh số thì `II. CÁ NHÂN CƯ TRÚ` ra cấp khác `I. Đặc điểm`,
    và stack breadcrumb lồng sai."""
    out = docx_heading_levels(["I. Đặc điểm hoạt động", "II. CÁ NHÂN CƯ TRÚ"])
    assert out[0] == out[1] == DOCX_LEVEL["roman"]


def test_khong_nham_tien_te_thanh_muc_danh_so():
    out = docx_heading_levels(["Tổng cộng 5.000.000 đồng.",
                               "1. Mục thật", "2. Mục thật nữa"])
    assert out[0] is None


def test_tu_khoa_luat_van_giu_dung_thu_bac_cu():
    out = docx_heading_levels(["Chương I", "Mục 1", "Điều 5. Định mức chi"])
    assert out[0] == DOCX_LEVEL["chuong"]
    assert out[1] == DOCX_LEVEL["muc"]
    assert out[2] == DOCX_LEVEL["dieu"]
    assert out[0] < out[1] < out[2]
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_docx_heading.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'DOCX_LEVEL'`

- [ ] **Step 3: Viết bản cài đặt**

Thêm vào `backend/src/rag/parse.py`, NGAY SAU hàm `heading_level()` (đừng sửa hàm đó):

```python
# ---------------------------------------------------------------------------
# Suy phân cấp cho .docx — spec 2026-09-04
#
# Vì sao KHÔNG nới `heading_level()` ở trên: nó đang phục vụ corpus LUẬT và đã
# hiệu chỉnh kỹ (nhánh `Điều` từng bị siết vì sinh 15 mục là mảnh câu). Nới nó
# ra là rủi ro hồi quy trên đường đang chạy tốt, để chữa một đường khác. Ở đây
# dùng LẠI các regex của nó nhưng xếp thứ tự kiểm khác và thêm mẫu hành chính.
#
# Thang RỘNG HƠN thang 1-5 của `heading_level()` để chèn được các tầng hành
# chính vào giữa. `chunk_text_blocks` chỉ so cấp bằng `>=` nên thang không cần
# liền mạch. Số ở đây là ĐỀ XUẤT, hiệu chỉnh ở Task 4.
DOCX_LEVEL = {
    "phan": 5,
    "chuong": 10,
    "upper": 20,
    "muc": 30,
    "roman": 35,
    "letter": 38,
    "dieu": 40,
    "arabic": 45,
    "multi": 50,
}

# Cấp của style Word (`Heading 1..9`) nhân với hệ số này để về CÙNG thang.
# Dùng thô là sai: `Heading 2` sẽ thành cấp 2, cao hơn cả `phan` (5) lẫn
# `chuong` (10), và hất sạch mọi thứ phía trên nó.
STYLE_SCALE = 10

_PHAN_RE = re.compile(r"^\s*PHẦN\s+\S", re.IGNORECASE)

# Một dòng mở đầu bằng ký hiệu đánh số TRẦN: "I.", "A.", "12.", "3)".
# `\s+\S` bắt buộc có khoảng trắng rồi mới tới nội dung — nhờ đó
# "5.000.000 đồng" không khớp (sau dấu chấm là chữ số, không phải khoảng trắng).
_ENUM_RE = re.compile(r"^\s*([A-ZĐ]+|\d{1,2})\s*[.)]\s+\S")

# Mục đánh số ĐA CẤP: "12.1", "3.2.1". Dùng để lấy TIỀN TỐ làm bằng chứng cho
# mục cha ("12." là tiêu đề vì "12.1" tồn tại).
_MULTI_RE = re.compile(r"^\s*(\d{1,2})\.\d{1,2}")

_ROMAN_VALUE = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(token: str) -> int | None:
    """Giá trị của một số La Mã, hoặc None nếu không phải số La Mã."""
    if not token or any(c not in _ROMAN_VALUE for c in token):
        return None
    total = 0
    highest = 0
    for char in reversed(token):
        value = _ROMAN_VALUE[char]
        total = total - value if value < highest else total + value
        highest = max(highest, value)
    return total or None


def _has_consecutive(numbers: set[int]) -> bool:
    """Tập có chứa hai số KẾ TIẾP NHAU không (n và n+1).

    Đây là "bằng chứng" của một họ đánh số: một tài liệu có `I.` rồi `II.` thì
    họ La Mã là thật; một `I.` đứng một mình có thể chỉ là chữ cái lạc.
    Nói về THỨ TỰ ĐÁNH SỐ, không phải khoảng cách dòng."""
    return any(n + 1 in numbers for n in numbers)


def _collect_evidence(texts: list[str]) -> tuple[bool, bool, bool, set[int]]:
    """Bằng chứng đánh số mà CHÍNH tài liệu đưa ra.

    Trả `(roman_ok, letter_ok, arabic_ok, multi_parents)`.

    Một token một ký tự như "I" được tính vào CẢ họ La Mã lẫn họ chữ cái; việc
    nó thuộc họ nào do bằng chứng quyết định sau, không đoán trước.
    """
    romans: set[int] = set()
    letters: set[int] = set()
    arabics: set[int] = set()
    parents: set[int] = set()

    for text in texts:
        multi = _MULTI_RE.match(text)
        if multi:
            parents.add(int(multi.group(1)))
            continue
        found = _ENUM_RE.match(text)
        if not found:
            continue
        token = found.group(1)
        if token.isdigit():
            arabics.add(int(token))
            continue
        value = _roman_to_int(token)
        if value is not None:
            romans.add(value)
        if len(token) == 1:
            letters.add(ord(token))

    return (_has_consecutive(romans), _has_consecutive(letters),
            _has_consecutive(arabics), parents)


def _docx_level(text: str, roman_ok: bool, letter_ok: bool,
                arabic_ok: bool, parents: set[int]) -> int | None:
    """Cấp của MỘT dòng, với bằng chứng của cả tài liệu đã tính sẵn.

    THỨ TỰ KIỂM quan trọng: nhánh đánh số phải đứng TRƯỚC nhánh dòng IN HOA
    của `heading_level()`. Nếu không, "II. CÁ NHÂN CƯ TRÚ" (in hoa) ra cấp
    khác "I. Đặc điểm hoạt động" (thường) dù cùng một họ, và stack breadcrumb
    lồng sai.
    """
    found = _ENUM_RE.match(text)
    if found:
        token = found.group(1)
        if token.isdigit():
            number = int(token)
            if number in parents or arabic_ok:
                return DOCX_LEVEL["arabic"]
            return None
        if roman_ok and _roman_to_int(token) is not None:
            return DOCX_LEVEL["roman"]
        if letter_ok and len(token) == 1:
            return DOCX_LEVEL["letter"]
        # Có đánh số nhưng tài liệu không đưa ra bằng chứng nào — rơi xuống
        # các nhánh dưới thay vì đoán bừa.

    if _PHAN_RE.match(text):
        return DOCX_LEVEL["phan"]

    shared = heading_level(text)
    if shared is None:
        return None
    return {1: DOCX_LEVEL["chuong"], 2: DOCX_LEVEL["upper"],
            3: DOCX_LEVEL["muc"], 4: DOCX_LEVEL["dieu"],
            5: DOCX_LEVEL["multi"]}[shared]


def docx_heading_levels(texts: list[str]) -> list[int | None]:
    """Cấp tiêu đề cho từng dòng của MỘT tài liệu .docx, hoặc None.

    Nhận cả tài liệu chứ không chấm từng dòng độc lập, vì quy tắc "đánh số
    trần phải tự chứng minh" (spec mục 5) cần bằng chứng ở phạm vi tài liệu.
    Nhận `list[str]` chứ KHÔNG nhận đối tượng docx — module giữ nguyên tính
    lá thuần, và test không cần tệp thật.
    """
    roman_ok, letter_ok, arabic_ok, parents = _collect_evidence(texts)
    return [_docx_level(t, roman_ok, letter_ok, arabic_ok, parents)
            for t in texts]
```

- [ ] **Step 4: Chạy để thấy XANH**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_docx_heading.py -v -m "not integration and not live"`
Expected: PASS 11/11

- [ ] **Step 5: Phép thử phá — quy tắc bằng chứng**

Tạm đổi `_has_consecutive` thành `return True` (tức mọi họ đều được coi là có bằng chứng).
Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_docx_heading.py -v -m "not integration and not live"`
Expected: `test_mot_muc_La_Ma_dung_mot_minh_KHONG_phai_tieu_de` **ĐỎ**. Hoàn tác.

- [ ] **Step 6: Phép thử phá — thứ tự kiểm**

Tạm chuyển khối `found = _ENUM_RE.match(text)` xuống SAU lời gọi `heading_level(text)` trong `_docx_level`.
Run: lệnh ở Step 5.
Expected: `test_muc_La_Ma_IN_HOA_CUNG_CAP_voi_muc_La_Ma_thuong` **ĐỎ**. Hoàn tác.

- [ ] **Step 7: Chạy toàn suite, đối chiếu SỐ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2294 passed, 1 skipped` — đúng 2283 + 11 test mới. **Đối chiếu con số, đừng chỉ nhìn chữ "passed".**

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/parse.py backend/tests/rag/test_docx_heading.py
git commit -m "feat(rag): bo do phan cap tu chu cho docx, co quy tac tu chung minh"
```

---

### Task 2: Nối vào `parse_docx` — hai lượt

**Files:**
- Modify: `backend/src/rag/parse.py` (hàm `parse_docx`, khoảng dòng 194-234)
- Create: `backend/tests/rag/test_parse_docx_phan_cap.py`

**Interfaces:**
- Consumes: `docx_heading_levels()`, `DOCX_LEVEL`, `STYLE_SCALE` từ Task 1.
- Produces: `parse_docx` giữ nguyên chữ ký `(path: str) -> list[dict]`; block vẫn là `{"text", "heading_level", "page"}`, chỉ khác là `heading_level` nay có giá trị cho tài liệu không dùng style.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_parse_docx_phan_cap.py`:

```python
# backend/tests/rag/test_parse_docx_phan_cap.py
"""`parse_docx` hai lượt — spec 2026-09-04 mục 7.

Fixture tự dựng bằng python-docx, đáp án chắc 100% (tầng 1 của spec
2026-08-29 mục 6.1).
"""
from docx import Document

from src.rag.parse import DOCX_LEVEL, parse_docx


def _levels(path):
    return [b["heading_level"] for b in parse_docx(str(path))]


def test_tai_lieu_KHONG_style_van_suy_duoc_phan_cap(tmp_path):
    """Ca thật của 10 biểu mẫu BCTC: 0 đoạn nào dùng style Heading."""
    p = tmp_path / "khong_style.docx"
    d = Document()
    for line in ("BÁO CÁO THỬ NGHIỆM", "I. Phần thứ nhất",
                 "Nội dung của phần thứ nhất.", "II. Phần thứ hai",
                 "Nội dung của phần thứ hai."):
        d.add_paragraph(line)
    d.save(str(p))

    levels = _levels(p)
    assert levels[0] == DOCX_LEVEL["upper"]
    assert levels[1] == DOCX_LEVEL["roman"]
    assert levels[2] is None
    assert levels[3] == DOCX_LEVEL["roman"]
    assert levels[4] is None


def test_style_Heading_duoc_ANH_XA_sang_cung_thang(tmp_path):
    """`Heading N` → `N * STYLE_SCALE`. Dùng cấp style THÔ là sai: `Heading 2`
    thành cấp 2, cao hơn cả `phan` (5) lẫn `chuong` (10), hất sạch mọi thứ."""
    p = tmp_path / "co_style.docx"
    d = Document()
    d.add_paragraph("Tiêu đề lớn", style="Heading 1")
    d.add_paragraph("Tiêu đề nhỏ", style="Heading 3")
    d.save(str(p))

    levels = _levels(p)
    assert levels == [DOCX_LEVEL["chuong"], DOCX_LEVEL["muc"]]


def test_style_duoc_UU_TIEN_hon_mau_chu(tmp_path):
    """Word đã khai báo rồi thì không đoán lại — không đổi hành vi cũ."""
    p = tmp_path / "tron.docx"
    d = Document()
    d.add_paragraph("I. Dòng này có style", style="Heading 1")
    d.add_paragraph("II. Dòng này không có style")
    d.save(str(p))

    levels = _levels(p)
    assert levels[0] == DOCX_LEVEL["chuong"], "style thắng"
    assert levels[1] == DOCX_LEVEL["roman"], "mẫu chữ lo phần còn lại"


def test_bang_van_la_THAN_khong_bao_gio_la_tieu_de(tmp_path):
    p = tmp_path / "co_bang.docx"
    d = Document()
    d.add_paragraph("I. Mục một")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "1. Cột này trông như đánh số"
    table.cell(0, 1).text = "Giá"
    table.cell(1, 0).text = "2. Hàng nữa"
    table.cell(1, 1).text = "100"
    d.add_paragraph("II. Mục hai")
    d.save(str(p))

    blocks = parse_docx(str(p))
    table_blocks = [b for b in blocks if "|" in b["text"]]
    assert table_blocks, "phải có block bảng"
    assert all(b["heading_level"] is None for b in table_blocks)


def test_thu_tu_block_khong_doi(tmp_path):
    """Hai lượt không được xáo thứ tự — `chunk_text_blocks` dựng breadcrumb
    theo THỨ TỰ block, xáo là gắn nội dung vào mục sai."""
    p = tmp_path / "thu_tu.docx"
    d = Document()
    for line in ("I. Một", "thân một", "II. Hai", "thân hai"):
        d.add_paragraph(line)
    d.save(str(p))

    texts = [b["text"] for b in parse_docx(str(p))]
    assert texts == ["I. Một", "thân một", "II. Hai", "thân hai"]
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_parse_docx_phan_cap.py -v -m "not integration and not live"`
Expected: FAIL — `parse_docx` chưa suy cấp, `levels[1]` là `None` thay vì `DOCX_LEVEL["roman"]`.

- [ ] **Step 3: Viết lại `parse_docx` thành hai lượt**

Thay THÂN hàm `parse_docx` (giữ nguyên docstring hiện có, thêm đoạn giải thích hai lượt vào cuối docstring):

```python
    doc = Document(path)

    # Lượt 1: gom theo ĐÚNG thứ tự thân tài liệu, chưa quyết định cấp.
    items: list[tuple[str, str, int | None]] = []   # (kind, text, style_level)
    for child in doc.element.body.iterchildren():
        tag = etree.QName(child).localname if hasattr(child, "tag") else ""
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or "") if para.style else ""
            style_level = None
            if style.startswith("Heading"):
                try:
                    style_level = int(style.split()[-1]) * STYLE_SCALE
                except ValueError:
                    style_level = DOCX_LEVEL["chuong"]
            items.append(("p", text, style_level))
        elif tag == "tbl":
            text = _bang_thanh_text(Table(child, doc))
            if text:
                items.append(("tbl", text, None))

    # Lượt 2: suy cấp từ chữ, CHỈ trên đoạn văn. Không đưa text bảng vào: một
    # ô bảng chứa "1." sẽ làm nhiễu bằng chứng đánh số của cả tài liệu.
    para_levels = docx_heading_levels([t for kind, t, _ in items if kind == "p"])

    blocks: list[dict] = []
    para_index = 0
    for kind, text, style_level in items:
        if kind == "tbl":
            # heading_level=None: bảng là THÂN, không bao giờ là tiêu đề —
            # để nó thành heading sẽ phá breadcrumb của cả mục.
            blocks.append({"text": text, "heading_level": None, "page": None})
            continue
        # Style của Word thắng mẫu chữ: đã khai báo rồi thì không đoán lại.
        level = style_level if style_level is not None else para_levels[para_index]
        para_index += 1
        blocks.append({"text": text, "heading_level": level, "page": None})
    return blocks
```

- [ ] **Step 4: Chạy để thấy XANH**

Run: lệnh ở Step 2.
Expected: PASS 5/5

- [ ] **Step 5: Phép thử phá — ánh xạ style**

Tạm bỏ `* STYLE_SCALE` (dùng cấp style thô).
Run: lệnh ở Step 2.
Expected: `test_style_Heading_duoc_ANH_XA_sang_cung_thang` **ĐỎ**. Hoàn tác.

- [ ] **Step 6: Chạy toàn suite, đối chiếu SỐ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2299 passed, 1 skipped` — đúng 2294 + 5 test mới. Nếu có test CŨ chuyển sang đỏ, dừng và báo: đó là hồi quy thật, không được sửa test cho xanh.

- [ ] **Step 7: Commit**

```bash
git add backend/src/rag/parse.py backend/tests/rag/test_parse_docx_phan_cap.py
git commit -m "feat(rag): parse_docx hai luot, suy phan cap khi khong co style Heading"
```

---

### Task 3: `section_path` rỗng thay vì đường dẫn tệp

**Files:**
- Modify: `backend/src/rag/chunking.py:52`
- Create: `backend/tests/rag/test_chunking_khong_duong_dan.py`

**Interfaces:**
- Consumes: không có (độc lập với Task 1-2).
- Produces: không có tên mới; `chunk_text_blocks` đổi HÀNH VI khi không block nào có heading.

**Bối cảnh bắt buộc đọc:** đây là lỗi CHUNG cho mọi định dạng, không riêng docx. `b09-dn.docx` hôm nay có 74/74 chunk mang `section_path` bằng đường dẫn tệp; đường dẫn Windows đó bị `index_text()` nối vào text đem đi embed, giống hệt nhau ở mọi chunk — vừa vô nghĩa vừa làm GIẢM khả năng phân biệt giữa chính các chunk đó (spec 2026-08-29 mục 1.1).

**Kế hoạch 1 đã vá NỬA chuỗi lỗi này rồi** — đọc docstring `ingest._chunks_for` (`backend/src/rag/ingest.py:78-92`): nó tách `read_path` khỏi `source_file` để tệp `.doc/.xls/.ppt` không ghi ĐƯỜNG DẪN CACHE TẠM vào `source_file`. Nửa còn lại là chỗ này — cú lùi vẫn còn, chỉ là nay nó rò đường dẫn GỐC thay vì đường dẫn cache.

**⚠️ LỆCH SPEC CÓ CHỦ Ý, đã báo chủ dự án.** Spec mục 8 viết `doc_title` phải **rỗng**. Kiểm lại code thì thấy `doc_title` là **một cột riêng** (`schema.sql:22`), được `retrieve.py` SELECT ra và mang vào kiểu `Chunk` để hiển thị/trích dẫn, và **KHÔNG đi vào `index_text()` lẫn `ts_vector`** (ts_vector do `ingest` ghi từ `index_text`). Tức tác hại nằm TRỌN ở `crumb`, không ở `doc_title`. Nên bản sửa tách đôi: **`crumb` không lùi về gì cả** (đúng ý spec), còn **`doc_title` lùi về TÊN TỆP** thay vì rỗng — giữ một nhãn đọc được cho trích dẫn, bỏ phần đường dẫn vô nghĩa. Rỗng hoàn toàn thì an toàn nhưng mất trắng nhãn hiển thị mà không đổi lại được gì.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_chunking_khong_duong_dan.py`:

```python
# backend/tests/rag/test_chunking_khong_duong_dan.py
"""Không tài liệu nào được nhúng ĐƯỜNG DẪN TỆP vào vector — spec 2026-09-04 mục 8.

Trước bản sửa: tài liệu không có heading nào thì `doc_title` lùi về
`source_file`, `crumb` lùi về `doc_title`, và `index_text()` nối đường dẫn
Windows vào text đem đi embed ở MỌI chunk.
"""
from src.rag.chunking import chunk_text_blocks

_DUONG_DAN = r"D:\Youdoo\tmp-docs\bao_cao.docx"


def _blocks_khong_heading():
    return [{"text": "Câu văn thứ nhất trong tài liệu.", "heading_level": None,
             "page": None},
            {"text": "Câu văn thứ hai trong tài liệu.", "heading_level": None,
             "page": None}]


def test_khong_co_heading_thi_section_path_RONG():
    chunks = chunk_text_blocks(_blocks_khong_heading(),
                               doc_id="d1", source_file=_DUONG_DAN)
    assert chunks, "phải sinh chunk"
    assert all(not c["section_path"] for c in chunks)


def test_duong_dan_KHONG_di_vao_chuoi_dem_di_EMBED():
    """Chân đối chứng cứng, đo ĐÚNG chỗ gây hại: `index_text()` là thứ đi vào
    embedding và ts_vector."""
    from src.rag.chunking import index_text
    chunks = chunk_text_blocks(_blocks_khong_heading(),
                               doc_id="d1", source_file=_DUONG_DAN)
    for c in chunks:
        indexed = index_text(c["section_path"], c["chunk_text"])
        assert "tmp-docs" not in indexed
        assert "Youdoo" not in indexed


def test_doc_title_lui_ve_TEN_TEP_khong_phai_duong_dan():
    """`doc_title` là cột hiển thị/trích dẫn, KHÔNG vào embedding — nên giữ
    một nhãn đọc được thay vì rỗng, nhưng bỏ phần đường dẫn."""
    chunks = chunk_text_blocks(_blocks_khong_heading(),
                               doc_id="d1", source_file=_DUONG_DAN)
    assert all(c["doc_title"] == "bao_cao.docx" for c in chunks)


def test_co_heading_thi_breadcrumb_van_nhu_cu():
    """Chân đối chứng ngược: bản sửa không được làm mất breadcrumb THẬT."""
    blocks = [{"text": "Chương I", "heading_level": 10, "page": None},
              {"text": "Nội dung của chương.", "heading_level": None,
               "page": None}]
    chunks = chunk_text_blocks(blocks, doc_id="d1", source_file=_DUONG_DAN)
    assert chunks[0]["section_path"] == "Chương I"
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_chunking_khong_duong_dan.py -v -m "not integration and not live"`
Expected: FAIL — `section_path` đang bằng `D:\Youdoo\tmp-docs\bao_cao.docx`.

- [ ] **Step 3: Sửa `chunking.py` — hai chỗ, một dòng mỗi chỗ**

Thêm `import os` vào đầu tệp (hiện chỉ có `import re`).

Thay dòng 52:

```python
    doc_title = next((b["text"] for b in blocks if b["heading_level"]), source_file)
```

bằng:

```python
    # `doc_title` lùi về TÊN TỆP, không phải đường dẫn đầy đủ và cũng không
    # phải rỗng: nó là cột metadata cho hiển thị/trích dẫn (`schema.sql`,
    # `retrieve.py` SELECT ra), KHÔNG đi vào `index_text()` lẫn `ts_vector`.
    # Giữ một nhãn đọc được thì có ích; giữ nguyên đường dẫn thì không.
    doc_title = next((b["text"] for b in blocks if b["heading_level"]),
                     os.path.basename(source_file))
```

Thay dòng 61 (bỏ hẳn cú lùi):

```python
            crumb = " › ".join(t for _, t in path_stack) or doc_title
```

bằng:

```python
            # KHÔNG lùi về `doc_title`: `crumb` là thứ `index_text()` nối vào
            # chuỗi đem đi EMBED và vào `ts_vector`. Trước 2026-09-04 nó lùi
            # về `doc_title` (khi đó đang là `source_file`), nên đường dẫn
            # Windows bị nhúng vào vector của MỌI chunk trong tài liệu, giống
            # hệt nhau — vừa vô nghĩa vừa làm GIẢM khả năng phân biệt giữa
            # chính các chunk đó (spec 2026-08-29 mục 1.1). Không có phân cấp
            # thì breadcrumb phải RỖNG: "không biết" phải trông như không
            # biết. Lỗi này CHUNG cho mọi định dạng, không riêng .docx.
            crumb = " › ".join(t for _, t in path_stack)
```

- [ ] **Step 4: Chạy để thấy XANH**

Run: lệnh ở Step 2.
Expected: PASS 4/4

- [ ] **Step 5: Phép thử phá**

Hoàn tác tạm dòng 61 về `... or doc_title`.
Run: lệnh ở Step 2.
Expected: `test_duong_dan_KHONG_di_vao_chuoi_dem_di_EMBED` **ĐỎ**. Sửa lại.

- [ ] **Step 6: Sửa docstring đã lạc hậu ở `ingest.py`**

`backend/src/rag/ingest.py:78-92` mô tả chuỗi lỗi `chunking.py:52 → :61 → index_text()` như một chuyện ĐANG xảy ra. Sau Step 3 nó không còn đúng. Để nguyên là dựng lại đúng lỗi "chú thích khẳng định sai sự thật" mà review toàn nhánh của kế hoạch 1 đã bắt (PARK 2).

Sửa đoạn từ `Đường dẫn đó chảy tiếp:` tới hết docstring thành:

```python
    HAI THAM SỐ TÁCH RỜI, không phải một. Trước 2026-08-31 chỉ có một tham
    số và nó vừa dùng để đọc vừa dùng làm nhãn, nên tệp `.doc/.xls/.ppt` ghi
    ĐƯỜNG DẪN CACHE TẠM vào `source_file` — một chuỗi chứa content_hash, ĐỔI
    mỗi lần tài liệu đổi và KHÁC NHAU giữa các máy.

    Chuỗi đó từng chảy tiếp vào embedding qua `chunking.py` (doc_title lùi về
    source_file → crumb lùi về doc_title → `index_text()`). Nhánh đó đã bị
    CẮT 2026-09-04 (B3): `crumb` không còn lùi về `doc_title` nữa. Việc tách
    hai tham số ở đây vẫn cần — `source_file` là nhãn người dùng thấy, và nó
    phải là tệp GỐC dù đường rò kia đã đóng."""
```

- [ ] **Step 7: Chạy toàn suite, đối chiếu SỐ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2303 passed, 1 skipped` — đúng 2299 + 4. **Chú ý đặc biệt**: bản sửa này đổi hành vi cho MỌI định dạng, nên nếu có test cũ đỏ thì đó là thông tin thật — đọc kỹ trước khi làm gì, **đừng sửa test cho xanh**. Đặc biệt để ý `tests/rag/test_chunking_text.py` (có test khẳng định `doc_title`).

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/chunking.py backend/src/rag/ingest.py backend/tests/rag/test_chunking_khong_duong_dan.py
git commit -m "fix(rag): crumb khong con lui ve duong dan tep -- dong nua con lai cua chuoi lo ro"
```

---

### Task 4: Nghiệm thu trên 12 tệp thật + hiệu chỉnh thang cấp

**Files:**
- Create: `backend/tests/rag/test_docx_kho_that.py`
- Modify: `backend/src/rag/parse.py` (chỉ `DOCX_LEVEL` nếu số đo đòi)

**Interfaces:**
- Consumes: `parse_docx`, `chunk_text_blocks`, `DOCX_LEVEL`.
- Produces: không có.

Đây là **tầng 2** của spec 2026-08-29 mục 6.1: tệp thật ngoài repo, mốc `live`, skip sạch khi thiếu.

- [ ] **Step 1: Viết test nghiệm thu**

Tạo `backend/tests/rag/test_docx_kho_that.py`:

```python
# backend/tests/rag/test_docx_kho_that.py
"""Nghiệm thu tầng 2 — 12 tệp Word THẬT ngoài repo (spec 2026-09-04 mục 10).

Cổng CỨNG: không chunk nào mang đường dẫn tệp làm `section_path`. Cổng này
không cần gán tay đáp án nào — "breadcrumb là đường dẫn tệp" là thứ máy tự
kiểm được.

Số tài liệu có phân cấp thật thì BÁO CÁO, không đặt ngưỡng cứng — cùng lý do
kế hoạch 2 đã bỏ `đúng >= 20`.
"""
import os

import pytest

from src.rag.chunking import chunk_text_blocks
from src.rag.parse import parse_docx

KHO = "d:/Youdoo/tmp-docs"
pytestmark = pytest.mark.live


def _tep_docx():
    if not os.path.isdir(KHO):
        return []
    return sorted(f for f in os.listdir(KHO) if f.lower().endswith(".docx"))


@pytest.mark.skipif(not _tep_docx(), reason="chưa có tmp-docs")
def test_KHONG_chunk_nao_mang_duong_dan_tep_lam_breadcrumb():
    ban = []
    for name in _tep_docx():
        path = os.path.join(KHO, name)
        chunks = chunk_text_blocks(parse_docx(path), doc_id=name,
                                   source_file=path)
        for c in chunks:
            crumb = c["section_path"] or ""
            if "tmp-docs" in crumb or crumb.endswith(".docx"):
                ban.append((name, crumb[:60]))
                break
    assert ban == [], f"vẫn còn breadcrumb là đường dẫn tệp: {ban}"


@pytest.mark.skipif(not _tep_docx(), reason="chưa có tmp-docs")
def test_bao_cao_do_phu_phan_cap():
    """Không phải cổng — in ra để người chạy NHÌN THẤY kho thật rơi vào đâu."""
    print()
    co_phan_cap = 0
    for name in _tep_docx():
        path = os.path.join(KHO, name)
        blocks = parse_docx(path)
        heads = [b for b in blocks if b["heading_level"]]
        chunks = chunk_text_blocks(blocks, doc_id=name, source_file=path)
        có = sum(1 for c in chunks if c["section_path"])
        co_phan_cap += 1 if heads else 0
        print(f"  {name:<28} block {len(blocks):>4}  tiêu đề {len(heads):>3}  "
              f"chunk {len(chunks):>3}  có breadcrumb {có:>3}")
    print(f"\n  tài liệu có phân cấp: {co_phan_cap}/{len(_tep_docx())}")
    assert _tep_docx(), "không đọc được tệp nào"
```

- [ ] **Step 2: Chạy nghiệm thu**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_docx_kho_that.py -v -m live -s`
Expected: PASS, và **dán bảng in ra vào báo cáo**.

Nếu cổng cứng ĐỎ: đó là phát hiện thật, báo rõ tệp nào — **đừng nới cổng cho xanh**.

- [ ] **Step 3: Hiệu chỉnh thang cấp bằng đo**

Viết một script đo dùng một lần (scratchpad, **KHÔNG commit** — đúng quy ước dự án) so `DOCX_LEVEL` hiện tại với ít nhất hai biến thể, trên cả 12 tệp:

```python
# scratchpad/calibrate_docx_levels.py
import os, sys
sys.path.insert(0, "d:/Youdoo/.claude/worktrees/tang-nap-tai-lieu-1/backend/src")
from rag import parse
from rag.chunking import chunk_text_blocks

KHO = "d:/Youdoo/tmp-docs"
BIEN_THE = {
    "de xuat":        dict(roman=35, letter=38),
    "roman duoi dieu": dict(roman=42, letter=43),
}

for ten, thay in BIEN_THE.items():
    goc = dict(parse.DOCX_LEVEL)
    parse.DOCX_LEVEL.update(thay)
    tong_chunk = sam = 0
    for f in sorted(os.listdir(KHO)):
        if not f.lower().endswith(".docx"):
            continue
        p = os.path.join(KHO, f)
        blocks = parse.parse_docx(p)
        chunks = chunk_text_blocks(blocks, doc_id=f, source_file=p)
        tong_chunk += len(chunks)
        sam += sum(1 for c in chunks if c["section_path"])
    print(f"{ten:<20} chunk {tong_chunk:>4}  co breadcrumb {sam:>4}")
    parse.DOCX_LEVEL.clear(); parse.DOCX_LEVEL.update(goc)
```

Chốt giá trị theo số đo. Nếu số đo KHÔNG phân biệt được các biến thể thì **giữ nguyên đề xuất** và ghi rõ "dải phẳng, giữ giá trị khởi điểm" — đúng cách kế hoạch 2 đã chốt `SCAN_LIMIT`.

- [ ] **Step 4: Đo phân bố chunk trước/sau (nghĩa vụ đo của mẫu số trần)**

**Không** dựng worktree tạm ở commit cũ: bản "trước" khác bản "sau" ở HAI thay đổi (suy phân cấp *và* bản sửa `chunking.py`), nên phép so đó không tách được tác động của riêng mẫu số trần. Thay vào đó ép bộ dò trả toàn `None` — đúng hành vi trước B3 — và giữ mọi thứ khác nguyên:

```python
# scratchpad/do_phan_bo_chunk.py
import os, statistics, sys
sys.path.insert(0, "d:/Youdoo/.claude/worktrees/tang-nap-tai-lieu-1/backend/src")
from rag import parse
from rag.chunking import chunk_text_blocks

KHO = "d:/Youdoo/tmp-docs"
TEP = sorted(f for f in os.listdir(KHO) if f.lower().endswith(".docx"))
that = parse.docx_heading_levels


def do(nhan):
    tong, kich_thuoc = 0, []
    for f in TEP:
        p = os.path.join(KHO, f)
        chunks = chunk_text_blocks(parse.parse_docx(p), doc_id=f, source_file=p)
        tong += len(chunks)
        kich_thuoc += [len(c["chunk_text"]) for c in chunks]
    tb = statistics.mean(kich_thuoc) if kich_thuoc else 0
    trung_vi = statistics.median(kich_thuoc) if kich_thuoc else 0
    print(f"{nhan:<28} chunk {tong:>4}  ky tu TB {tb:>7.0f}  trung vi {trung_vi:>7.0f}")


# TRUOC: khong suy phan cap nao (hanh vi truoc B3)
parse.docx_heading_levels = lambda texts: [None] * len(texts)
do("truoc (khong suy cap)")

# SAU: day du
parse.docx_heading_levels = that
do("sau (day du)")

# CHI bang chung cha-con: bo nhanh arabic_ok
goc = parse._collect_evidence
parse._collect_evidence = lambda t: (lambda r: (r[0], r[1], False, r[3]))(goc(t))
do("sau, bo nhanh arabic_ok")
parse._collect_evidence = goc
```

Ba dòng số này trả lời đúng câu hỏi spec mục 5 đặt ra. Nếu số chunk tăng vọt ở dòng thứ hai nhưng dòng thứ ba thì không, tức **mẫu số trần đang cắt vụn `Điều` thành từng khoản** — phương án lùi đã được spec lường trước là **bỏ nhánh `arabic_ok`, chỉ giữ bằng chứng cha-con (`n in parents`)**.

**Đừng tự đổi** — báo ba con số rồi chờ quyết định. Đây là đánh đổi có hệ quả tới retrieval, không phải một hằng số chỉnh cho đẹp.

- [ ] **Step 5: Chạy lại toàn suite lần cuối**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2303 passed, 1 skipped`, `deselected` tăng đúng 2 (hai test `live` mới).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/rag/test_docx_kho_that.py backend/src/rag/parse.py
git commit -m "test(rag): nghiem thu phan cap docx tren 12 tep that + chot thang cap"
```

---

## Sau khi xong kế hoạch này

Ghi nối tiếp vào `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md` phần **khó khăn / hướng đã chọn / giới hạn còn lại** của đợt B3, gồm cả giả thuyết nào bị số đo bác bỏ và bảng hiệu chỉnh thang cấp ở Task 4. Đây là yêu cầu thường trực của chủ dự án, không phải tuỳ chọn — và review toàn nhánh của kế hoạch 2 đã bắt đúng lỗi bỏ sót bước này.

Kế hoạch tiếp theo: **B4 — PDF bóc bảng** (spec 2026-08-29 mục 5.4).
