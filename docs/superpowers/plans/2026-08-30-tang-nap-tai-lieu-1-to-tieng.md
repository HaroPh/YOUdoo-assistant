# Tầng nạp tài liệu — Kế hoạch 1: To tiếng + phủ định dạng

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Không tệp tài liệu nào biến mất khỏi corpus mà không có ai được báo, và mở đường nạp cho `.xlsm`, `.pptx`, cùng các định dạng cũ `.doc`/`.xls`/`.ppt`.

**Architecture:** `_ingest_file` đang trả một `dict` ba số đếm; đuôi lạ trả toàn 0 nên không phân biệt được "không có gì để làm" với "đã nuốt một tài liệu". Thay bằng kiểu kết quả có tên mang **ba trạng thái tệp** (`ingested` / `unchanged` / `rejected`), tách **danh sách đuôi được coi là tài liệu** khỏi **danh sách đuôi nạp được**, và cho `main()` thoát khác 0 khi có tệp bị từ chối. Định dạng cũ đi qua một cầu chuyển đổi LibreOffice tách rời; không có LibreOffice thì thành `rejected` chứ không im lặng.

**Tech Stack:** Python 3.11, `python-pptx` (mới), LibreOffice 26.8.0 headless (đã cài), `openpyxl`, `python-docx`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-tang-nap-tai-lieu.md` — mục 4 (Tầng A) và 5.1 (phủ định dạng). Đọc cả hai trước khi bắt đầu.

## Global Constraints

- **Định danh trong code viết bằng tiếng Anh.** Chú thích và thông điệp lỗi viết tiếng Việt. Không đặt tên biến/hàm tiếng Việt.
- **Lệnh test mặc định luôn kèm cờ loại trừ**: `pytest -m "not integration and not live"`. Lệnh trần gọi API thật và từng gây sự cố.
- **Không viết cứng đường dẫn máy cá nhân.** `soffice.exe` và `TESSDATA_PREFIX` phải đọc từ biến môi trường, có mặc định dò tìm.
- **Kiểm bằng sản phẩm, không kiểm bằng mã thoát.** Trong đợt cài phụ thuộc 2026-08-30 đã có **ba** mã thoát nói dối (spec mục 5.1.1). Test phải khẳng định trên dữ liệu/tệp thật sinh ra, không trên việc lệnh chạy xong.
- Chạy mọi lệnh từ thư mục `backend/`, dùng `./.venv/Scripts/python.exe`.
- Đường dẫn LibreOffice trên máy dev hiện tại: `C:\Users\ADMIN\scoop\apps\libreoffice\current\LibreOffice\program\soffice.exe`

---

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/src/rag/ingest_report.py` | **Tạo mới.** Kiểu kết quả nạp: `Rejection`, `IngestReport`. Module lá, không import gì trong `src.rag`. |
| `backend/src/rag/convert.py` | **Tạo mới.** Cầu chuyển đổi LibreOffice. Không biết gì về DB hay chunk. |
| `backend/src/rag/parse.py` | **Sửa.** Thêm `parse_pptx()`. |
| `backend/src/rag/ingest.py` | **Sửa.** Bảng đuôi tệp, ba trạng thái, `main()` thoát khác 0. |
| `backend/tests/rag/test_ingest_report.py` | **Tạo mới.** Kiểu kết quả. |
| `backend/tests/rag/test_ingest_guard.py` | **Sửa.** Viết lại test khoá hành vi cũ + thêm test anh em. |
| `backend/tests/rag/test_convert.py` | **Tạo mới.** Cầu chuyển đổi. |
| `backend/tests/rag/test_parse_pptx.py` | **Tạo mới.** Parser slide. |
| `backend/tests/rag/test_ingest.py` | **Sửa.** 2 dòng khẳng định đổi `skipped` → `unchanged`. |

**Ghi chú phạm vi:** Spec mục 4 có nhắc một **danh sách cảnh báo mức sheet/bảng**. Kế hoạch này **không** dựng nó, vì chưa có nguồn sinh cảnh báo nào — dựng bây giờ là hạ tầng không ai chạy qua, đúng lớp lỗi cả spec đi đóng. Nó thuộc kế hoạch 2 (B2), nơi bộ dò hàng tiêu đề là nguồn sinh cảnh báo đầu tiên.

---

### Task 1: Kiểu kết quả nạp với ba trạng thái

**Files:**
- Create: `backend/src/rag/ingest_report.py`
- Create: `backend/tests/rag/test_ingest_report.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `Rejection(path: str, reason: str)` — dataclass frozen.
  - `IngestReport(ingested: int = 0, unchanged: int = 0, chunks: int = 0, rejected: list[Rejection] = [])`
  - `IngestReport.merge(other: IngestReport) -> None` — cộng dồn tại chỗ.
  - `IngestReport.ok -> bool` — property, `True` khi `rejected` rỗng.
  - `IngestReport.render() -> str` — dòng tóm tắt + một dòng cho mỗi tệp bị từ chối.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_ingest_report.py`:

```python
# backend/tests/rag/test_ingest_report.py
"""Kiểu kết quả nạp — spec 2026-08-29 mục 4.

Vì sao có tệp này: `_ingest_file` từng trả dict ba số đếm, nên tệp đuôi lạ
trả toàn 0 và KHÔNG phân biệt được với "thư mục không có gì để làm". Ba
trạng thái phải là ba thứ đọc được, không phải ba con số.
"""
from src.rag.ingest_report import IngestReport, Rejection


def test_bao_cao_rong_la_ok():
    r = IngestReport()
    assert r.ok is True
    assert r.ingested == 0 and r.unchanged == 0 and r.chunks == 0


def test_co_tep_bi_tu_choi_thi_khong_ok():
    r = IngestReport(rejected=[Rejection("a.doc", "chưa hỗ trợ")])
    assert r.ok is False


def test_merge_cong_don_ca_so_dem_lan_danh_sach_tu_choi():
    a = IngestReport(ingested=1, chunks=5)
    b = IngestReport(unchanged=2, chunks=0,
                     rejected=[Rejection("x.ppt", "không có bộ chuyển đổi")])
    a.merge(b)
    assert (a.ingested, a.unchanged, a.chunks) == (1, 2, 5)
    assert [x.path for x in a.rejected] == ["x.ppt"]
    assert a.ok is False


def test_merge_khong_dung_chung_danh_sach_giua_hai_bao_cao():
    """Bẫy mutable default: hai IngestReport() rỗng phải có list RIÊNG.
    Nếu dùng `rejected: list = []` làm default thì mọi báo cáo dùng chung
    một list và một lượt nạp hỏng sẽ nhiễm sang lượt sau."""
    a, b = IngestReport(), IngestReport()
    a.merge(IngestReport(rejected=[Rejection("p.doc", "lý do")]))
    assert a.rejected != []
    assert b.rejected == []


def test_render_goi_TEN_tung_tep_bi_tu_choi():
    """Báo cáo phải gọi TÊN tệp. Một con số tổng không cho người dùng biết
    tài liệu nào của họ vắng mặt khỏi corpus."""
    r = IngestReport(ingested=3, unchanged=1, chunks=40,
                     rejected=[Rejection("quy_che.doc", "không có LibreOffice"),
                               Rejection("slide.pptx", "parse ra rỗng")])
    out = r.render()
    assert "quy_che.doc" in out and "không có LibreOffice" in out
    assert "slide.pptx" in out and "parse ra rỗng" in out
    assert "3" in out and "1" in out
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_report.py -v -m "not integration and not live"`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rag.ingest_report'`

- [ ] **Step 3: Viết bản cài đặt tối thiểu**

Tạo `backend/src/rag/ingest_report.py`:

```python
"""Kết quả một lượt nạp tài liệu — spec 2026-08-29 mục 4.

Ba trạng thái TỆP, không phải ba số đếm:
    ingested  — đã sinh chunk và ghi DB
    unchanged — content_hash trùng, bỏ qua CÓ CHỦ Ý
    rejected  — không nạp được, KÈM LÝ DO, được gọi tên

Không có trạng thái thứ tư. Trước 2026-08-30 hàm nạp trả dict ba số đếm và
tệp `.doc`/`.xlsm`/`.pptx` rơi vào khoảng trắng giữa chúng: cả ba số đều 0,
không lời nào, tài liệu biến mất khỏi corpus.

Chữ `skipped` cũ bị bỏ có chủ ý: nó mang HAI nghĩa ("không đổi nên bỏ qua"
và "không hiểu nên bỏ qua") và chính sự mơ hồ đó là chỗ lỗi nấp được.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rejection:
    path: str
    reason: str


@dataclass
class IngestReport:
    ingested: int = 0
    unchanged: int = 0
    chunks: int = 0
    rejected: list[Rejection] = field(default_factory=list)

    def merge(self, other: "IngestReport") -> None:
        self.ingested += other.ingested
        self.unchanged += other.unchanged
        self.chunks += other.chunks
        self.rejected.extend(other.rejected)

    @property
    def ok(self) -> bool:
        return not self.rejected

    def render(self) -> str:
        lines = [f"đã nạp {self.ingested} · không đổi {self.unchanged} · "
                 f"chunk {self.chunks} · từ chối {len(self.rejected)}"]
        for r in self.rejected:
            lines.append(f"  TỪ CHỐI  {r.path}  —  {r.reason}")
        return "\n".join(lines)
```

- [ ] **Step 4: Chạy để thấy XANH**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_report.py -v -m "not integration and not live"`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/ingest_report.py backend/tests/rag/test_ingest_report.py
git commit -m "feat(rag): kieu ket qua nap voi ba trang thai tep"
```

---

### Task 2: Tách đuôi "là tài liệu" khỏi đuôi "nạp được"

**Files:**
- Modify: `backend/src/rag/ingest.py` (dòng 15 `_EXT`, hàm `_ingest_file` dòng 56, `ingest_path` dòng 109, `main` dòng 133)
- Modify: `backend/tests/rag/test_ingest_guard.py` (viết lại `test_tep_duoi_la_khong_nem_va_khong_dem_la_skipped`)
- Modify: `backend/tests/rag/test_ingest.py` (dòng 31: `s2["skipped"]` → `s2.unchanged`)

**Interfaces:**
- Consumes: `IngestReport`, `Rejection` từ Task 1.
- Produces:
  - `ingest.DOCUMENT_EXT: frozenset[str]` — mọi đuôi được COI LÀ tài liệu (gồm cả loại chưa nạp được).
  - `ingest._EXT: dict[str, str]` — đuôi → loại parser (`"text"` / `"xlsx"`), tức đuôi nạp được TRỰC TIẾP.
  - `_ingest_file(path: str, conn) -> IngestReport`
  - `ingest_path(path: str, conn=None) -> IngestReport`

**Bối cảnh bắt buộc đọc:** test `test_tep_duoi_la_khong_nem_va_khong_dem_la_skipped` (2026-08-19) đang khoá hành vi cũ kèm lý lẽ *"tệp đuôi lạ chưa bao giờ là tài liệu để mà bỏ"*. Lý lẽ đó **ĐÚNG cho `.txt`** và phải được giữ. Việc ở đây không phải "sửa test cho xanh" mà là **tách một khái niệm đang bị gộp**: `.gitkeep` và `.doc` hôm nay nằm cùng một rọ.

- [ ] **Step 1: Viết test đỏ**

Thay thế hàm `test_tep_duoi_la_khong_nem_va_khong_dem_la_skipped` trong `backend/tests/rag/test_ingest_guard.py` bằng hai hàm dưới đây (giữ nguyên phần đầu tệp và test `test_tep_duoc_nhan_nhung_ra_rong_thi_nem_loi`):

```python
def test_duoi_KHONG_PHAI_tai_lieu_van_bo_qua_im_lang(tmp_path):
    """Giữ nguyên lý lẽ của bản 2026-08-19: `.txt` chưa bao giờ là tài liệu
    để mà bỏ, nên nó KHÔNG phải `rejected`. Nếu tính nó là từ chối thì một
    tệp `.gitkeep` trong thư mục sẽ làm tiến trình thoát khác 0."""
    f = tmp_path / "ghi_chu.txt"
    f.write_text("khong phai tai lieu", encoding="utf-8")
    rep = _ing._ingest_file(str(f), conn=None)
    assert rep.ingested == 0 and rep.unchanged == 0
    assert rep.rejected == []
    assert rep.ok is True


def test_duoi_LA_TAI_LIEU_nhung_chua_nap_duoc_thi_bi_TU_CHOI(tmp_path, monkeypatch):
    """Đây là lỗi cả spec đi đóng: `.doc` là tài liệu thật, người dùng nghĩ
    đã nạp, nhưng hệ trả toàn 0 và không nói gì.

    Giả lập KHÔNG có LibreOffice để test không phụ thuộc máy chạy."""
    from src.rag import convert as _conv
    monkeypatch.setattr(_conv, "soffice_path", lambda: None)
    f = tmp_path / "quy_che.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0 fake OLE")
    rep = _ing._ingest_file(str(f), conn=None)
    assert rep.ok is False
    assert len(rep.rejected) == 1
    assert rep.rejected[0].path.endswith("quy_che.doc")
    assert "LibreOffice" in rep.rejected[0].reason


def test_moi_duoi_nap_duoc_deu_nam_trong_danh_sach_tai_lieu():
    """Chống trôi hai chiều: không thể thêm một đuôi vào `_EXT` mà quên khai
    nó là tài liệu. Danh sách gõ tay trôi khỏi sự thật là lớp lỗi đã tái phát
    nhiều lần trong dự án này."""
    assert set(_ing._EXT) <= _ing.DOCUMENT_EXT


def test_dinh_dang_cu_pho_bien_deu_duoc_coi_la_tai_lieu():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".pptx", ".xlsm"):
        assert ext in _ing.DOCUMENT_EXT, ext
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_guard.py -v -m "not integration and not live"`
Expected: FAIL — `AttributeError: module 'src.rag.ingest' has no attribute 'DOCUMENT_EXT'`

- [ ] **Step 3: Sửa `ingest.py`**

Thay dòng 15 (`_EXT = {...}`) bằng:

```python
# Đuôi nạp được TRỰC TIẾP → loại parser.
_EXT = {
    ".pdf": "text",
    ".docx": "text",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",     # sổ kế toán Việt Nam gần như luôn là .xlsm (có macro)
    ".xltx": "xlsx",
}

# Đuôi ĐƯỢC COI LÀ TÀI LIỆU — rộng hơn `_EXT`. Tệp mang đuôi ở đây mà không
# nạp được thì phải bị TỪ CHỐI CÓ TÊN, không được im lặng.
#
# Vì sao cần hai danh sách: trước 2026-08-30 chỉ có `_EXT`, nên `.doc` và
# `.gitkeep` rơi vào cùng một nhánh "đuôi lạ, bỏ qua". Một cái là rác trong
# thư mục, cái kia là quy chế công ty biến mất khỏi corpus.
DOCUMENT_EXT = frozenset(_EXT) | {
    ".doc", ".xls", ".ppt",          # định dạng cũ, cần LibreOffice
    ".rtf", ".odt", ".ods", ".odp",  # định dạng khác LibreOffice đọc được
    ".pptx",                          # có parser riêng, xem Task 4
}
```

Thay thân `_ingest_file` (dòng 56 trở đi) — giữ nguyên phần từ `doc_id, content_hash = ...` xuống dưới, chỉ đổi phần đầu và kiểu trả về:

```python
def _ingest_file(path: str, conn) -> IngestReport:
    ext = os.path.splitext(path)[1].lower()
    kind = _EXT.get(ext)
    if kind is None:
        if ext not in DOCUMENT_EXT:
            return IngestReport()          # không phải tài liệu — im lặng ĐÚNG
        return _ingest_convertible(path, ext, conn)
    return _ingest_known(path, kind, conn)
```

Thêm `_ingest_known` chứa nguyên logic cũ (từ `doc_id, content_hash = ...` tới hết), trả `IngestReport` thay cho dict:

```python
def _ingest_known(path: str, kind: str, conn) -> IngestReport:
    doc_id, content_hash = _doc_id(path), _hash(path)
    existing = conn.execute(
        "SELECT content_hash FROM rag_documents WHERE doc_id = %s", (doc_id,)
    ).fetchone()
    if existing and existing[0] == content_hash:
        return IngestReport(unchanged=1)

    chunks = _chunks_for(path, kind, doc_id)
    if not chunks:
        raise IngestError(
            f"{path}: tệp được nhận ({kind}) nhưng không sinh được chunk nào. "
            f"Với PDF, nguyên nhân thường gặp là bản scan không có lớp text — "
            f"cần OCR trước khi ingest. KHÔNG bỏ qua âm thầm: tài liệu sẽ vắng "
            f"mặt khỏi corpus mà không ai biết.")
    # GIỮ NGUYÊN nguyên khối `ingest.py` dòng 80–105 của bản trước khi sửa:
    #   - đoạn chú thích "Embed BEFORE any DB write..."
    #   - `vectors = embed_texts([...])`
    #   - `try/except EmbeddingError`
    #   - DELETE + INSERT vào `rag_documents`, vòng INSERT `rag_chunks`
    # Chỉ đổi DÒNG CUỐI của hàm, từ `return {"ingested": 1, ...}` thành:
    return IngestReport(ingested=1, chunks=len(chunks))
```

**Cảnh báo cho người thực thi:** đừng gõ lại khối embed/INSERT từ trí nhớ. Mở
`git show HEAD:backend/src/rag/ingest.py` và chép nguyên. Khối đó có một chú
thích giải thích vì sao embed phải chạy TRƯỚC mọi lệnh ghi DB (tránh dòng mồ
côi khi Ollama chết) — mất chú thích đó là mất lý do.

Thêm nhánh chuyển đổi (bản tạm cho Task 2 — Task 3 sẽ hoàn thiện):

```python
def _ingest_convertible(path: str, ext: str, conn) -> IngestReport:
    from . import convert
    if convert.soffice_path() is None:
        return IngestReport(rejected=[Rejection(
            path, f"định dạng {ext} cần LibreOffice để chuyển đổi, "
                  f"nhưng không tìm thấy soffice (đặt biến {convert.SOFFICE_ENV})")])
    return IngestReport(rejected=[Rejection(path, f"định dạng {ext} chưa nạp được")])
```

Thêm import ở đầu tệp:

```python
from .ingest_report import IngestReport, Rejection
```

Sửa `ingest_path` (dòng 109): đổi `totals = {...}` và vòng lặp thành:

```python
        report = IngestReport()
        files = ([path] if os.path.isfile(path)
                 else [os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs])
        for f in files:
            report.merge(_ingest_file(f, conn))
        return report
```

Sửa `main()` (dòng 133):

```python
def main() -> None:
    use_utf8_streams()
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOCUMENTS_PATH", ".")
    report = ingest_path(target)
    print(report.render())
    # Thoát khác 0 khi có tài liệu bị từ chối: một lượt nạp bỏ sót tài liệu
    # KHÔNG phải là một lượt nạp thành công, và người gọi (script, CI) phải
    # biết được điều đó mà không cần đọc chữ.
    if not report.ok:
        sys.exit(1)
```

- [ ] **Step 4: Tạo `convert.py` tối thiểu để import không vỡ**

Tạo `backend/src/rag/convert.py`:

```python
"""Cầu chuyển đổi định dạng cũ qua LibreOffice — spec 2026-08-29 mục 5.1.

Task 3 hoàn thiện; Task 2 chỉ cần `soffice_path()` để nhánh từ chối chạy được.
"""
import os
import shutil

SOFFICE_ENV = "SOFFICE_PATH"

_FALLBACK_PATHS = (
    r"C:\Users\ADMIN\scoop\apps\libreoffice\current\LibreOffice\program\soffice.exe",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
)


def soffice_path() -> str | None:
    """Đường dẫn soffice, hoặc None nếu không tìm thấy.

    Thứ tự: biến môi trường → PATH → vài vị trí quen thuộc. KHÔNG viết cứng
    một đường dẫn duy nhất: máy dev hiện tại cài qua scoop vào thư mục người
    dùng, máy khác sẽ khác (spec mục 5.1.1, "nợ triển khai")."""
    env = os.environ.get(SOFFICE_ENV)
    if env and os.path.isfile(env):
        return env
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for p in _FALLBACK_PATHS:
        if os.path.isfile(p):
            return p
    return None
```

- [ ] **Step 5: Sửa test integration dùng tên mới**

Trong `backend/tests/rag/test_ingest.py`, dòng 26-32, đổi truy cập dict sang thuộc tính:

```python
    s1 = ingest_path(p, conn=clean_tables)
    assert s1.ingested == 1 and s1.chunks >= 1
    n = clean_tables.execute("SELECT count(*) FROM rag_chunks").fetchone()[0]
    assert n == s1.chunks

    s2 = ingest_path(p, conn=clean_tables)         # unchanged → skip
    assert s2.ingested == 0 and s2.unchanged == 1
    assert clean_tables.execute("SELECT count(*) FROM rag_chunks").fetchone()[0] == n
```

Rà nốt phần còn lại của tệp: mọi chỗ khác dùng `["ingested"]`, `["skipped"]`, `["chunks"]` phải đổi sang thuộc tính tương ứng (`skipped` → `unchanged`).

- [ ] **Step 6: Chạy test mặc định**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/ -v -m "not integration and not live"`
Expected: PASS toàn bộ, gồm 4 test mới ở Step 1.

- [ ] **Step 7: Chạy test integration (cần Postgres cổng 5434)**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest.py -v -m integration`
Expected: PASS. Nếu Postgres không chạy, khởi động container `youdoo-postgres` trước; **không** bỏ qua bước này — đây là nơi duy nhất kiểm việc đổi tên `skipped` → `unchanged` không phá đường ghi thật.

- [ ] **Step 8: Phép thử phá**

Tạm sửa `_ingest_file`: đổi `if ext not in DOCUMENT_EXT` thành `if True` (tức mọi đuôi lạ đều im lặng như trước).
Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_guard.py -v -m "not integration and not live"`
Expected: `test_duoi_LA_TAI_LIEU_nhung_chua_nap_duoc_thi_bi_TU_CHOI` **ĐỎ**.
Hoàn tác thay đổi tạm. Cổng không biết đỏ là cổng không đo gì.

- [ ] **Step 9: Commit**

```bash
git add backend/src/rag/ingest.py backend/src/rag/convert.py backend/tests/rag/test_ingest_guard.py backend/tests/rag/test_ingest.py
git commit -m "feat(rag): tach duoi tai lieu khoi duoi nap duoc, tu choi co ten"
```

---

### Task 3: Cầu chuyển đổi LibreOffice

**Files:**
- Modify: `backend/src/rag/convert.py`
- Create: `backend/tests/rag/test_convert.py`
- Modify: `backend/src/rag/ingest.py` (hàm `_ingest_convertible`)

**Interfaces:**
- Consumes: `soffice_path()` từ Task 2.
- Produces:
  - `convert.CONVERT_CACHE_ENV = "YOUDOO_CONVERT_CACHE"`
  - `convert.TARGET_EXT: dict[str, str]` — `{".doc": "docx", ".rtf": "docx", ".odt": "docx", ".xls": "xlsx", ".ods": "xlsx", ".ppt": "pptx", ".odp": "pptx"}`
  - `convert.ConverterMissing(RuntimeError)`
  - `convert.ConvertFailed(RuntimeError)`
  - `convert.convert_file(path: str, content_hash: str) -> str` — trả đường dẫn tệp đã chuyển; ném `ConverterMissing` / `ConvertFailed`.
  - `convert.cache_dir() -> str`

**Số đo bắt buộc tôn trọng (spec mục 5.1.2):** lần chuyển đầu tốn **17,5 giây** vì dựng profile LibreOffice, các lần sau **5,2 giây**. Vì vậy `convert_file` **phải** truyền `-env:UserInstallation` trỏ vào một profile cố định trong `cache_dir()`, và **phải** dùng lại tệp đã chuyển khi `content_hash` trùng.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_convert.py`:

```python
# backend/tests/rag/test_convert.py
"""Cầu chuyển đổi định dạng cũ — spec 2026-08-29 mục 5.1.

Test ở tệp này KHÔNG cần LibreOffice trừ hai test đánh dấu `live`. Lý do:
một cầu chuyển đổi chỉ chạy được trên máy có LibreOffice thì trên CI sẽ
không ai kiểm, và nó sẽ chết âm thầm — đúng lớp lỗi dự án đang đóng.
"""
import os
import pytest

from src.rag import convert


def test_moi_duoi_can_chuyen_deu_co_dich_den():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".ods", ".odp"):
        assert ext in convert.TARGET_EXT, ext


def test_dich_den_deu_la_duoi_ma_ingest_nap_duoc():
    """Chống trôi: chuyển `.doc` sang một đuôi mà `_EXT` không nhận thì
    tài liệu vẫn biến mất, chỉ là chậm hơn một bước."""
    from src.rag.ingest import _EXT, DOCUMENT_EXT
    for src_ext, target in convert.TARGET_EXT.items():
        assert "." + target in _EXT or "." + target in DOCUMENT_EXT, src_ext


def test_khong_co_soffice_thi_nem_ConverterMissing(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "soffice_path", lambda: None)
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake")
    with pytest.raises(convert.ConverterMissing) as e:
        convert.convert_file(str(f), "hash123")
    assert convert.SOFFICE_ENV in str(e.value)


def test_cache_dir_doc_duoc_tu_bien_moi_truong(monkeypatch, tmp_path):
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    assert convert.cache_dir() == str(tmp_path / "kho")
    assert os.path.isdir(convert.cache_dir())


def test_dung_lai_ban_da_chuyen_khi_hash_trung(monkeypatch, tmp_path):
    """Không gọi lại LibreOffice cho tệp không đổi: mỗi lượt gọi tốn ~5 giây."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")

    goi = []
    def _fake_run(soffice, path, target, outdir):
        goi.append(path)
        out = os.path.join(outdir, "a.docx")
        with open(out, "wb") as fh:
            fh.write(b"converted")
        return out
    monkeypatch.setattr(convert, "_run_soffice", _fake_run)

    p1 = convert.convert_file(str(src), "hash-abc")
    p2 = convert.convert_file(str(src), "hash-abc")
    assert p1 == p2
    assert len(goi) == 1, "lượt thứ hai phải dùng cache, không gọi lại soffice"


def test_soffice_chay_xong_ma_khong_co_tep_thi_nem_ConvertFailed(monkeypatch, tmp_path):
    """Bài học 2026-08-30: trong một đợt cài có BA mã thoát nói dối. Cầu
    chuyển đổi phải kiểm TỆP ĐẦU RA, không kiểm mã thoát."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    monkeypatch.setattr(convert, "_run_soffice",
                        lambda soffice, path, target, outdir: None)
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")
    with pytest.raises(convert.ConvertFailed):
        convert.convert_file(str(src), "hash-xyz")


@pytest.mark.live
def test_chuyen_that_mot_tep_doc(tmp_path):
    """Cần LibreOffice thật. Dùng tệp mẫu trong tmp-docs nếu có."""
    src = "d:/Youdoo/tmp-docs/quyche_taichinh.doc"
    if convert.soffice_path() is None or not os.path.isfile(src):
        pytest.skip("cần LibreOffice và tmp-docs/quyche_taichinh.doc")
    os.environ[convert.CONVERT_CACHE_ENV] = str(tmp_path / "kho")
    out = convert.convert_file(src, "live-hash")
    assert out.endswith(".docx") and os.path.getsize(out) > 5000
    from src.rag.parse import parse_docx
    blocks = parse_docx(out)
    assert len(blocks) > 20
    assert any("CHƯƠNG" in b["text"] for b in blocks)
```

- [ ] **Step 2: Chạy để chắc chắn nó ĐỎ**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_convert.py -v -m "not integration and not live"`
Expected: FAIL — `AttributeError: module 'src.rag.convert' has no attribute 'TARGET_EXT'`

- [ ] **Step 3: Hoàn thiện `convert.py`**

Thêm vào `backend/src/rag/convert.py`:

```python
import subprocess
import tempfile

CONVERT_CACHE_ENV = "YOUDOO_CONVERT_CACHE"

# Đuôi cũ → đuôi đích (không có dấu chấm, đúng dạng soffice --convert-to nhận)
TARGET_EXT = {
    ".doc": "docx", ".rtf": "docx", ".odt": "docx",
    ".xls": "xlsx", ".ods": "xlsx",
    ".ppt": "pptx", ".odp": "pptx",
}

CONVERT_TIMEOUT_S = 180


class ConverterMissing(RuntimeError):
    """Không tìm thấy LibreOffice."""


class ConvertFailed(RuntimeError):
    """Đã gọi LibreOffice nhưng không có tệp đầu ra dùng được."""


def cache_dir() -> str:
    d = os.environ.get(CONVERT_CACHE_ENV) or os.path.join(
        tempfile.gettempdir(), "youdoo_convert")
    os.makedirs(d, exist_ok=True)
    return d


def _profile_uri() -> str:
    """Profile LibreOffice dùng lại giữa các lượt gọi.

    Đo 2026-08-30: lượt chuyển ĐẦU tốn 17,5 giây vì dựng profile, các lượt
    sau 5,2 giây. Không giữ profile thì mọi tệp đều trả giá lượt đầu."""
    p = os.path.join(cache_dir(), "lo_profile").replace("\\", "/")
    return "file:///" + p.lstrip("/")


def _run_soffice(soffice: str, path: str, target: str, outdir: str) -> str | None:
    """Gọi soffice, trả đường dẫn tệp đầu ra nếu thấy, không thì None.

    CỐ Ý KHÔNG dựa vào mã thoát: đợt cài 2026-08-30 gặp ba mã thoát nói dối,
    trong đó có một cái báo HỎNG khi thật ra đã THÀNH CÔNG."""
    subprocess.run(
        [soffice, "--headless", f"-env:UserInstallation={_profile_uri()}",
         "--convert-to", target, "--outdir", outdir, path],
        capture_output=True, timeout=CONVERT_TIMEOUT_S, check=False)
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(outdir, f"{stem}.{target}")
    return out if os.path.isfile(out) else None


def convert_file(path: str, content_hash: str) -> str:
    """Chuyển tệp định dạng cũ, trả đường dẫn bản đã chuyển.

    Dùng lại bản cũ khi `content_hash` trùng — mỗi lượt gọi soffice tốn ~5s.
    """
    ext = os.path.splitext(path)[1].lower()
    target = TARGET_EXT.get(ext)
    if target is None:
        raise ConvertFailed(f"{path}: không có đích chuyển đổi cho đuôi {ext}")

    soffice = soffice_path()
    if soffice is None:
        raise ConverterMissing(
            f"{path}: cần LibreOffice để chuyển {ext} sang .{target}, nhưng "
            f"không tìm thấy soffice. Đặt biến môi trường {SOFFICE_ENV} trỏ "
            f"tới soffice.exe, hoặc cài LibreOffice.")

    outdir = os.path.join(cache_dir(), content_hash)
    stem = os.path.splitext(os.path.basename(path))[0]
    cached = os.path.join(outdir, f"{stem}.{target}")
    if os.path.isfile(cached):
        return cached

    os.makedirs(outdir, exist_ok=True)
    out = _run_soffice(soffice, path, target, outdir)
    if out is None:
        raise ConvertFailed(
            f"{path}: LibreOffice chạy xong nhưng không sinh tệp .{target} "
            f"trong {outdir}. Tệp có thể hỏng hoặc được bảo vệ bằng mật khẩu.")
    return out
```

- [ ] **Step 4: Nối vào `ingest.py`**

Thay `_ingest_convertible` (bản tạm ở Task 2) bằng:

```python
def _ingest_convertible(path: str, ext: str, conn) -> IngestReport:
    """Định dạng cũ: chuyển sang đuôi hiện đại rồi nạp bản đã chuyển.

    `doc_id` giữ nguyên theo tệp GỐC, không theo bản đã chuyển — nếu không,
    cùng một quy chế sẽ có hai doc_id khi bộ chuyển đổi đổi thư mục cache."""
    from . import convert
    try:
        converted = convert.convert_file(path, _hash(path))
    except (convert.ConverterMissing, convert.ConvertFailed) as e:
        return IngestReport(rejected=[Rejection(path, str(e))])

    kind = _EXT.get(os.path.splitext(converted)[1].lower())
    if kind is None:
        return IngestReport(rejected=[Rejection(
            path, f"đã chuyển thành {converted} nhưng đuôi đó vẫn không nạp được")])
    return _ingest_known(converted, kind, conn, doc_id_source=path)
```

Sửa chữ ký `_ingest_known` để nhận nguồn định danh:

```python
def _ingest_known(path: str, kind: str, conn,
                  doc_id_source: str | None = None) -> IngestReport:
    """`path` là tệp ĐỌC được (có thể là bản đã chuyển đổi).
    `doc_id_source` là tệp GỐC người dùng đưa vào — dùng cho định danh và
    content_hash, để một quy chế `.doc` không đổi doc_id mỗi lần thư mục
    cache chuyển đổi thay đổi."""
    origin = doc_id_source or path
    doc_id, content_hash = _doc_id(origin), _hash(origin)
```

Phần còn lại của hàm giữ nguyên như Task 2, **trừ** hai chỗ dùng `path` (không
phải `origin`) vì chúng nói về tệp thực sự được đọc:
- `chunks = _chunks_for(path, kind, doc_id)`
- `source_file` truyền xuống `chunk_text_blocks` / `chunk_xlsx_sheets` bên trong
  `_chunks_for` — không cần sửa, nó đã nhận `path`.

Hệ quả có chủ ý: `source_file` trong DB trỏ tới **bản đã chuyển**, còn `doc_id`
trỏ tới **tệp gốc**. Nếu muốn `source_file` cũng là tệp gốc thì phải truyền thêm
tham số xuống `_chunks_for` — **không làm trong kế hoạch này**, vì `source_file`
chỉ dùng để hiển thị nhãn và bản đã chuyển vẫn là nguồn trung thực của nội dung
đã nạp. Ghi lại ở đây để người sau biết đây là lựa chọn, không phải sơ suất.

- [ ] **Step 5: Chạy test**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/ -v -m "not integration and not live"`
Expected: PASS toàn bộ.

- [ ] **Step 6: Chạy test live trên máy có LibreOffice**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_convert.py -v -m live`
Expected: PASS — `.doc` thật chuyển được và `parse_docx` ra > 20 block có chữ `CHƯƠNG`.

- [ ] **Step 7: Phép thử phá**

Tạm sửa `_run_soffice` để luôn `return out` (không kiểm `os.path.isfile`).
Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_convert.py::test_soffice_chay_xong_ma_khong_co_tep_thi_nem_ConvertFailed -v -m "not integration and not live"`
Expected: **ĐỎ**. Hoàn tác.

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/convert.py backend/tests/rag/test_convert.py backend/src/rag/ingest.py
git commit -m "feat(rag): cau chuyen doi LibreOffice cho dinh dang cu"
```

---

### Task 4: Parser `.pptx`

**Files:**
- Modify: `backend/src/rag/parse.py` (thêm `parse_pptx`)
- Modify: `backend/src/rag/ingest.py` (thêm `.pptx` vào `_EXT`, định tuyến trong `_chunks_for`)
- Create: `backend/tests/rag/test_parse_pptx.py`
- Modify: `backend/requirements.txt` (thêm `python-pptx`)

**Interfaces:**
- Consumes: không có từ task trước.
- Produces: `parse.parse_pptx(path: str) -> list[dict]` — cùng dạng block như `parse_docx`: `{"text": str, "heading_level": int | None, "page": int | None}`. `page` mang **số slide** (bắt đầu từ 1).

- [ ] **Step 1: Cài phụ thuộc**

```bash
./.venv/Scripts/python.exe -m pip install python-pptx
```

Thêm vào `backend/requirements.txt` (cùng lúc bổ sung hai gói đã cài trong lúc khảo sát nhưng chưa khai báo):

```
python-pptx
pdfplumber
pytesseract
```

- [ ] **Step 2: Viết test đỏ**

Tạo `backend/tests/rag/test_parse_pptx.py`:

```python
# backend/tests/rag/test_parse_pptx.py
"""Parser slide — spec 2026-08-29 mục 5.1.

Fixture tự dựng, đáp án chắc 100% (spec mục 6.1 tầng 1). Chưa có tệp .pptx
thật trong kho test; khi có thì thêm một test `live` đọc nó.
"""
import pytest

pptx = pytest.importorskip("pptx")

from src.rag.parse import parse_pptx


def _make_deck(path):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Quy trình bán hàng"
    s1.placeholders[1].text = "Bước 1: tiếp nhận yêu cầu\nBước 2: báo giá"
    s1.notes_slide.notes_text_frame.text = "Nhấn mạnh thời hạn báo giá 24 giờ."

    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Định mức chiết khấu"
    tbl = s2.shapes.add_table(3, 2, Inches(1), Inches(2),
                              Inches(6), Inches(2)).table
    tbl.cell(0, 0).text = "Sản lượng"; tbl.cell(0, 1).text = "Chiết khấu"
    tbl.cell(1, 0).text = "dưới 100";  tbl.cell(1, 1).text = "5%"
    tbl.cell(2, 0).text = "từ 100";    tbl.cell(2, 1).text = "10%"
    prs.save(path)


def test_tieu_de_slide_thanh_heading(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    blocks = parse_pptx(p)
    heads = [b["text"] for b in blocks if b["heading_level"]]
    assert "Quy trình bán hàng" in heads
    assert "Định mức chiết khấu" in heads


def test_so_slide_duoc_ghi_vao_page(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    blocks = parse_pptx(p)
    assert {b["page"] for b in blocks} == {1, 2}


def test_bang_giu_duoc_rang_buoc_hang(tmp_path):
    """Lỗi 4 của spec là số bị tách khỏi nhãn của nó. Bảng trong slide phải
    ra một dòng một hàng, cột ngăn bằng dấu sổ đứng — như `parse_docx`."""
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert "dưới 100 | 5%" in text
    assert "từ 100 | 10%" in text
    assert "Sản lượng | Chiết khấu" in text


def test_ghi_chu_thuyet_trinh_duoc_giu(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert "24 giờ" in text


def test_slide_rong_khong_sinh_block_rac(tmp_path):
    from pptx import Presentation
    p = str(tmp_path / "trong.pptx")
    prs = Presentation(); prs.slides.add_slide(prs.slide_layouts[6]); prs.save(p)
    assert parse_pptx(p) == []
```

- [ ] **Step 3: Chạy để chắc chắn nó ĐỎ**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pptx.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'parse_pptx'`

- [ ] **Step 4: Viết `parse_pptx`**

Thêm vào cuối `backend/src/rag/parse.py`:

```python
def _pptx_table_to_text(tbl) -> str:
    """Bảng trong slide thành text nhiều dòng, mỗi dòng một hàng, cột ngăn
    bởi "|" — CÙNG khuôn với `_bang_thanh_text` của .docx, để tầng chunk và
    tầng tổng hợp chỉ phải hiểu một dạng bảng."""
    rows = []
    for row in tbl.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def parse_pptx(path: str) -> list[dict]:
    """Blocks theo thứ tự slide; `page` mang SỐ SLIDE (từ 1).

    Tiêu đề slide thành heading cấp 1 — đó là phân cấp duy nhất một bộ slide
    có. Ghi chú thuyết trình được giữ vì trong tài liệu nội bộ chúng thường
    chứa điều kiện và ngoại lệ mà slide chỉ nói tóm tắt.
    """
    from pptx import Presentation

    prs = Presentation(path)
    blocks: list[dict] = []
    for idx, slide in enumerate(prs.slides, start=1):
        title = None
        if slide.shapes.title is not None:
            title = (slide.shapes.title.text or "").strip()
        if title:
            blocks.append({"text": title, "heading_level": 1, "page": idx})

        for shape in slide.shapes:
            if shape.has_table:
                text = _pptx_table_to_text(shape.table)
                if text:
                    blocks.append({"text": text, "heading_level": None, "page": idx})
                continue
            if not shape.has_text_frame:
                continue
            if slide.shapes.title is not None and shape is slide.shapes.title:
                continue
            text = shape.text_frame.text.strip()
            if text:
                blocks.append({"text": text, "heading_level": None, "page": idx})

        if slide.has_notes_slide:
            note = (slide.notes_slide.notes_text_frame.text or "").strip()
            if note:
                blocks.append({"text": f"Ghi chú: {note}",
                               "heading_level": None, "page": idx})
    return blocks
```

- [ ] **Step 5: Nối vào `ingest.py`**

Thêm `".pptx": "pptx"` vào `_EXT`. Sửa `_chunks_for`:

```python
def _chunks_for(path: str, kind: str, doc_id: str) -> list[dict]:
    if kind == "xlsx":
        return chunk_xlsx_sheets(parse_xlsx(path), doc_id=doc_id, source_file=path)
    low = path.lower()
    if low.endswith(".pdf"):
        blocks = parse_pdf(path)
    elif low.endswith(".pptx"):
        blocks = parse_pptx(path)
    else:
        blocks = parse_docx(path)
    if not blocks:
        return []
    return chunk_text_blocks(blocks, doc_id=doc_id, source_file=path)
```

Thêm `parse_pptx` vào dòng import từ `.parse`.

- [ ] **Step 6: Chạy toàn bộ suite mặc định**

Run: `./.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS toàn bộ, số test tăng đúng bằng số test mới thêm. **Đối chiếu số lượng trước/sau**: một script sửa test từng lặng lẽ nuốt 3 test mà suite vẫn xanh (spec dự án 2026-08-22).

- [ ] **Step 7: Phép thử phá**

Tạm bỏ nhánh `if shape.has_table` trong `parse_pptx`.
Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pptx.py::test_bang_giu_duoc_rang_buoc_hang -v -m "not integration and not live"`
Expected: **ĐỎ**. Hoàn tác.

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/parse.py backend/src/rag/ingest.py backend/tests/rag/test_parse_pptx.py backend/requirements.txt
git commit -m "feat(rag): parser pptx va khai bao phu thuoc con thieu"
```

---

### Task 5: Nghiệm thu trên kho tài liệu thật

**Files:**
- Create: `backend/tests/rag/test_ingest_kho_that.py`

**Interfaces:**
- Consumes: `ingest._ingest_file`, `IngestReport` từ Task 1–4.
- Produces: không có.

Đây là **tầng 2** của spec mục 6.1: tài liệu thật ở `tmp-docs/`, ngoài repo. Test phải `skip` sạch khi thư mục không tồn tại, để máy khác vẫn chạy suite được.

- [ ] **Step 1: Viết test**

Tạo `backend/tests/rag/test_ingest_kho_that.py`:

```python
# backend/tests/rag/test_ingest_kho_that.py
"""Nghiệm thu tầng 2 — tài liệu THẬT, ngoài repo (spec mục 6.1, mục 7).

Không có `tmp-docs/` thì skip: kho này không được commit (tệp nặng, văn bản
bên thứ ba), nên máy khác sẽ không có.
"""
import os
import pytest

from src.rag import ingest as _ing

KHO = "d:/Youdoo/tmp-docs"
pytestmark = pytest.mark.live


class _FakeConn:
    """Đủ cho nhánh kiểm content_hash và cho INSERT giả.

    KHÔNG truyền `conn=None`: tệp nào đi tới nhánh ghi DB sẽ ném
    AttributeError và test vỡ thay vì đo được điều gì. Cùng khuôn với
    `_FakeConn` trong test_ingest_guard.py."""

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None          # chưa từng nạp tệp này


@pytest.fixture
def _no_embed(monkeypatch):
    """Chặn gọi embedder thật: bài này đo ĐỊNH TUYẾN ĐỊNH DẠNG, không đo
    chất lượng vector, và một lượt embed thật tốn hạn mức."""
    monkeypatch.setattr(_ing, "embed_texts",
                        lambda texts: [[0.01] * 1024 for _ in texts])


def _co_kho():
    return os.path.isdir(KHO)


@pytest.mark.skipif(not _co_kho(), reason="chưa có tmp-docs")
def test_khong_tai_lieu_nao_bien_mat_im_lang(_no_embed):
    """Trước bản sửa: `.doc`, `.xlsm`, `.pptx` trả toàn 0 và không lời nào.
    Sau bản sửa: mỗi tệp tài liệu phải ra ở MỘT trong ba trạng thái —
    không tệp nào rơi vào khoảng trắng "0 mọi thứ, ok=True"."""
    tai_lieu = sorted(f for f in os.listdir(KHO)
                      if os.path.splitext(f)[1].lower() in _ing.DOCUMENT_EXT)
    assert len(tai_lieu) >= 10, "kho test quá nhỏ, xem lại tmp-docs"

    im_lang = []
    for name in tai_lieu:
        try:
            rep = _ing._ingest_file(os.path.join(KHO, name), conn=_FakeConn())
        except _ing.IngestError:
            continue          # hỏng TO TIẾNG — đúng ý đồ, không phải im lặng
        if rep.ingested == 0 and rep.unchanged == 0 and rep.ok:
            im_lang.append(name)
    assert im_lang == [], f"vẫn còn tài liệu biến mất im lặng: {im_lang}"


@pytest.mark.skipif(not _co_kho(), reason="chưa có tmp-docs")
def test_dem_theo_dinh_dang_de_doc_duoc_bang_mat(_no_embed):
    """In bảng phân bố trạng thái theo đuôi. Không phải khẳng định chặt —
    mục đích là để người chạy NHÌN THẤY kho thật rơi vào đâu, vì con số
    tổng không nói được tài liệu nào vắng mặt."""
    from collections import Counter
    dem = Counter()
    for name in sorted(os.listdir(KHO)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in _ing.DOCUMENT_EXT:
            continue
        try:
            rep = _ing._ingest_file(os.path.join(KHO, name), conn=_FakeConn())
            trang_thai = ("rejected" if rep.rejected else
                          "ingested" if rep.ingested else
                          "unchanged" if rep.unchanged else "IM_LANG")
        except _ing.IngestError:
            trang_thai = "IngestError"
        dem[(ext, trang_thai)] += 1
    for (ext, tt), n in sorted(dem.items()):
        print(f"  {ext:<7} {tt:<12} {n}")
    assert dem, "không đọc được tệp nào"
    assert not any(tt == "IM_LANG" for (_, tt) in dem)
```

- [ ] **Step 2: Chạy**

Run: `./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest_kho_that.py -v -m live`
Expected: PASS (hoặc skip sạch nếu thiếu `tmp-docs/`).

- [ ] **Step 3: Chạy toàn bộ suite mặc định lần cuối**

Run: `./.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS toàn bộ.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/rag/test_ingest_kho_that.py
git commit -m "test(rag): nghiem thu tang 2 tren kho tai lieu that"
```

---

## Sau khi xong kế hoạch này

Ghi vào repo phần **khó khăn / hướng đã chọn / giới hạn còn lại** của đợt, gồm cả giả thuyết nào bị số đo bác bỏ. Đây là yêu cầu thường trực của chủ dự án, không phải tuỳ chọn.

Kế hoạch tiếp theo: **B2 — Excel dò hàng tiêu đề** (spec mục 5.2), nơi danh sách cảnh báo mức sheet có nguồn sinh đầu tiên.
