# P3a — Vệ sinh ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gỡ rác header/footer trang khỏi 22% chunk PDF, chặn `_HEADING_RE` khớp tham chiếu giữa câu, cho PDF rỗng báo lỗi lớn tiếng — rồi re-index và đo bằng cả hai bộ eval.

**Architecture:** Hai hàm thuần mới trong `parse.py` (chuẩn hoá chữ số, nhận diện rác trang) để test được không cần PDF thật; `parse_pdf` đổi từ một-lượt sang hai-lượt (gom dòng theo trang → lọc → dựng block); `_HEADING_RE` siết nhánh `Điều`; `_ingest_file` ném lỗi thay vì `skipped` im lặng.

**Tech Stack:** Python 3.11, pypdf 5.1.0, pytest 9.1.1, Postgres+pgvector, Ollama `bge-m3`.

**Spec:** `docs/superpowers/specs/2026-08-19-ingest-hygiene-design.md`

## Global Constraints

- **Định danh trong code viết bằng tiếng Anh.** Comment/docstring tiếng Việt **có dấu** (đồng bộ với `parse.py` hiện tại).
- **Lệnh pytest LUÔN kèm `-m "not integration and not live"`** trừ khi bước ghi rõ khác.
- Chạy pytest từ `backend/`, dùng `./.venv/Scripts/python.exe -m pytest`.
- Chạy `evals.run_eval` phải nạp env trước (nó KHÔNG tự đọc `.env`):
  ```bash
  set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
  export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
  ```
- Ngưỡng chốt theo spec §3: `page_ratio = 0.6`, `edge_ratio = 0.9`, `edge = 2` dòng mỗi đầu, sàn `min_pages = 5`.
- **Không sửa** `chunking.py`, `retrieve.py`, `src/agents/**`, và **không** đụng luật `isupper()` (spec §4).
- Mốc hiện tại: 3.300 chunk / 17 tài liệu; 727 chunk chứa `about:blank`; 15 mục là mảnh câu; 1739 test mặc định + 37 integration xanh.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/rag/parse.py` (sửa) | Thêm `_normalize_digits` + `detect_page_furniture` (thuần, test được); `parse_pdf` đổi sang hai lượt; siết `_HEADING_RE`. |
| `backend/src/rag/ingest.py` (sửa) | `_ingest_file` ném lỗi khi tệp được nhận nhưng ra 0 chunk. |
| `backend/tests/rag/test_parse_pdf.py` (sửa) | Test cho bộ lọc rác trang và regex heading. |
| `backend/tests/rag/test_ingest.py` (sửa) | Test cho nhánh báo lỗi. |
| `backend/evals/baseline-*.json` (ghi lại) | Sau khi cổng §7 qua. |

---

## Task 1: Nhận diện rác trang (hai hàm thuần)

**Files:**
- Modify: `backend/src/rag/parse.py`
- Test: `backend/tests/rag/test_parse_pdf.py`

**Interfaces:**
- Consumes: không gì.
- Produces:
  - `_normalize_digits(text: str) -> str` — thay mọi chuỗi chữ số bằng `#`.
  - `detect_page_furniture(pages: list[list[str]], *, min_pages: int = 5, page_ratio: float = 0.6, edge_ratio: float = 0.9, edge: int = 2) -> set[str]` — trả tập **dạng đã chuẩn hoá** của các dòng là header/footer.

Tách hàm thuần nhận `list[list[str]]` (dòng theo trang) thay vì đường dẫn PDF: nhờ vậy toàn bộ luật lọc test được bằng dữ liệu dựng tay, không cần PDF thật và không cần đọc đĩa.

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `backend/tests/rag/test_parse_pdf.py`:

```python
# ── Lọc rác header/footer trang (spec 2026-08-19 §3) ─────────────────────────
# 727/3256 chunk PDF (22%) đang mang chuỗi kiểu
# "22:47 13/7/26 about:blank about:blank 1/164" NẰM GIỮA nội dung — nó đi vào
# embedding, ts_vector, cặp cho reranker và ngữ cảnh gửi LLM.
from src.rag.parse import _normalize_digits, detect_page_furniture


def _fake_pages(n, *, header=True, footer=True, middle_table=False):
    """n trang: [header] + 5 dòng thân + [footer].

    Thân PHẢI đủ 5 dòng. Với edge=2 tính từ CẢ HAI đầu, một trang 3 dòng thì
    mọi dòng đều nằm ở rìa và "khác." sẽ bị nhận nhầm là rác — bản đầu của
    plan này dựng đúng như vậy và test lẽ ra đỏ oan."""
    pages = []
    for i in range(1, n + 1):
        body = [f"Điều {i}. Nội dung riêng của trang {i}",
                "Câu mở đoạn không lặp lại.",
                "khác.",                       # lặp mọi trang, nhưng ở GIỮA
                "Câu tiếp theo cũng không lặp.",
                f"Đoạn kết riêng của trang {i}."]
        if middle_table:
            body.insert(2, f"{i} {i}.{i}")     # hàng bảng, cũng ở GIỮA
        lines = (["22:47 13/7/26 about:blank"] if header else []) + body
        if footer:
            lines.append(f"about:blank {i}/{n}")
        pages.append(lines)
    return pages


def test_normalize_digits_gop_cac_bien_the_so_trang():
    # Mấu chốt: "about:blank 5/164" và "about:blank 6/164" là hai chuỗi khác
    # nhau; đếm trần thì mỗi cái chỉ 1 trang và bộ lọc bỏ sót hoàn toàn.
    assert _normalize_digits("about:blank 5/164") == _normalize_digits("about:blank 6/164")
    assert _normalize_digits("about:blank 5/164") == "about:blank #/#"


def test_detect_bat_duoc_ca_header_lan_footer():
    got = detect_page_furniture(_fake_pages(20))
    assert _normalize_digits("about:blank 1/20") in got
    assert _normalize_digits("22:47 13/7/26 about:blank") in got


def test_detect_khong_an_dong_than_bai_lap_lai():
    # "khác." lặp ở MỌI trang nhưng nằm giữa → không phải rác trang.
    got = detect_page_furniture(_fake_pages(20))
    assert "khác." not in got


def test_detect_khong_an_hang_bang_o_giua_trang():
    # Ca dương-tính-giả THẬT đã đo được: "# #.#" là hàng bảng mã HS trong phụ
    # lục luat-thuexuatnhapkhau.pdf — nhiều hàng KHÁC NHAU bị chuẩn hoá gộp
    # chung, đẩy tần suất lên 48%. Chỉ điều kiện vị-trí-rìa mới loại được nó.
    got = detect_page_furniture(_fake_pages(20, middle_table=True))
    assert "# #.#" not in got


def test_detect_bo_qua_tai_lieu_qua_ngan():
    # Tài liệu 2 trang: một dòng hợp lệ lặp ở cả hai trang đã là 100%.
    assert detect_page_furniture(_fake_pages(2)) == set()


def test_detect_khong_an_dong_chi_o_ria_mot_vai_trang():
    # Xuất hiện ở rìa nhưng chỉ trên 3/20 trang → dưới ngưỡng tần suất.
    pages = _fake_pages(20, header=False, footer=False)
    for i in range(3):
        pages[i].append("Ghi chú cuối trang hiếm gặp.")
    assert "Ghi chú cuối trang hiếm gặp." not in detect_page_furniture(pages)


def test_detect_tra_ve_dang_da_chuan_hoa():
    # Hợp đồng đầu ra: caller so bằng _normalize_digits(line), nên tập trả về
    # phải là dạng ĐÃ chuẩn hoá — không còn chữ số nào.
    got = detect_page_furniture(_fake_pages(20))
    assert got, "phải bắt được ít nhất một dòng rác"
    assert not any(ch.isdigit() for g in got for ch in g)
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pdf.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `ImportError: cannot import name '_normalize_digits'`.

- [ ] **Step 3: Viết implementation**

Trong `backend/src/rag/parse.py`, thêm ngay dưới `_HEADING_RE`:

```python
_DIGITS_RE = re.compile(r"\d+")


def _normalize_digits(text: str) -> str:
    """Thay mọi chuỗi chữ số bằng '#'.

    Không có bước này thì bộ lọc tần suất bỏ sót hoàn toàn: 'about:blank 5/164'
    và 'about:blank 6/164' là hai chuỗi khác nhau, mỗi cái chỉ xuất hiện đúng
    một trang."""
    return _DIGITS_RE.sub("#", text)


def detect_page_furniture(pages: list[list[str]], *, min_pages: int = 5,
                          page_ratio: float = 0.6, edge_ratio: float = 0.9,
                          edge: int = 2) -> set[str]:
    """Dạng-đã-chuẩn-hoá của các dòng là header/footer trang.

    Điều kiện KÉP, không phải hoặc (spec 2026-08-19 §3):
      (a) xuất hiện trên >= page_ratio số trang, VÀ
      (b) >= edge_ratio số lần xuất hiện nằm trong `edge` dòng đầu hoặc cuối
          của trang.

    Vì sao cần (b): chuẩn hoá chữ số gộp NHIỀU hàng bảng khác nhau thành một
    nhóm. Đo thật trên luat-thuexuatnhapkhau.pdf: nhóm '# #.#' (hàng bảng mã
    HS) đạt 48% số trang — chỉ thoát ngưỡng 60% nhờ 12 điểm phần trăm, quá
    mỏng để tin. Với (b) thì nó ra 15% và bị loại dứt khoát, trong khi 18 nhóm
    rác thật của 9 tệp đều đạt 100%/100%.

    Vì sao không khớp mẫu 'about:blank': đó là dấu vết của CÁCH IN bộ PDF này
    (print-to-PDF từ trình duyệt). Tài liệu nguồn khác mang rác khác; tần suất
    bắt được cả loại chưa gặp, khớp mẫu cứng thì không.
    """
    n_pages = len(pages)
    if n_pages < min_pages:
        return set()
    seen_pages: dict[str, set[int]] = {}
    at_edge: dict[str, int] = {}
    total: dict[str, int] = {}
    for pageno, lines in enumerate(pages):
        for i, text in enumerate(lines):
            key = _normalize_digits(text)
            seen_pages.setdefault(key, set()).add(pageno)
            total[key] = total.get(key, 0) + 1
            if i < edge or i >= len(lines) - edge:
                at_edge[key] = at_edge.get(key, 0) + 1
    return {key for key, pgs in seen_pages.items()
            if len(pgs) / n_pages >= page_ratio
            and at_edge.get(key, 0) / total[key] >= edge_ratio}
```

- [ ] **Step 4: Chạy để xác nhận xanh**

```bash
./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pdf.py -q -m "not integration and not live"
```

Kỳ vọng: PASS (7 test mới cộng các test sẵn có của file).

- [ ] **Step 5: Commit**

```bash
cd /d/Youdoo
git add backend/src/rag/parse.py backend/tests/rag/test_parse_pdf.py
git commit -m "feat(rag): nhan dien rac header/footer trang bang tan suat VA vi tri ria"
```

---

## Task 2: `parse_pdf` hai lượt + siết `_HEADING_RE`

**Files:**
- Modify: `backend/src/rag/parse.py`
- Test: `backend/tests/rag/test_parse_pdf.py`

**Interfaces:**
- Consumes: `_normalize_digits`, `detect_page_furniture` (Task 1).
- Produces: `parse_pdf(path)` giữ nguyên chữ ký và hình dạng trả về (`list[dict]` với khoá `text`/`heading_level`/`page`) — chỉ bớt dòng rác và bớt heading giả.

- [ ] **Step 1: Viết test đỏ cho regex heading**

Thêm vào `backend/tests/rag/test_parse_pdf.py`:

```python
# ── _HEADING_RE không được khớp tham chiếu giữa câu (spec §4) ────────────────
# 15 "mục" trong rag_chunks thực chất là mảnh câu tham chiếu chéo, mỗi mảnh
# CẮT ĐÔI một Điều thật. Đây là lỗi DUY NHẤT đã chứng minh gây hại đo được:
# chuỗi "Điều ước quốc tế mà Cộng hòa..." chiếm hạng 1 của một câu hỏi thật.
import pytest

from src.rag.parse import _HEADING_RE


@pytest.mark.parametrize("line", [
    "Điều 113. Nghỉ hằng năm",
    "Điều 5. Đối tượng không chịu thuế",
    "Chương I",
    "Mục 2. CHẾ ĐỘ THAI SẢN",
    "1.1 Phạm vi",
])
def test_heading_that_van_duoc_nhan(line):
    assert _HEADING_RE.match(line), f"{line!r} phải là heading"


@pytest.mark.parametrize("line", [
    "Điều 11 của Luật này quy định.",
    "Điều 133 của Bộ luật này.",
    "Điều 14 của Luật này;",
    "Điều 20 của Luật này được giải quyết thông qua một trong những cơ quan sau đây:",
    "Điều 228 của Bộ luật này.",
    "Điều ước quốc tế mà Cộng hòa xã hội chủ nghĩa Việt Nam là thành viên.",
])
def test_tham_chieu_giua_cau_khong_phai_heading(line):
    assert not _HEADING_RE.match(line), f"{line!r} KHÔNG được là heading"
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

```bash
./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pdf.py -q -m "not integration and not live" -k heading
```

Kỳ vọng: 6 test `test_tham_chieu_giua_cau_khong_phai_heading` FAIL (regex hiện khớp cả chúng).

- [ ] **Step 3: Siết regex**

Trong `backend/src/rag/parse.py`, thay `_HEADING_RE` bằng:

```python
# Nhánh số CHỈ nhận numbering đa cấp ("1.1", "3.2.1"), sub-level 1-2 chữ số:
# numbering 1 cấp ("1. ...") là KHOẢN (nội dung) trong luật VN chứ không phải
# heading, còn nhóm 3 chữ số là dấu phân cách nghìn ("5.000.000.000 đồng.")
# hoặc mã HS phụ lục ("2931.9080") — cả ba từng bị nhận nhầm heading khiến
# chunking nuốt nội dung (spec 2026-07-15-rag-heading-detection-fix).
#
# Nhánh `Điều` SIẾT LẠI 2026-08-19 (spec ingest-hygiene §4): trước đây là
# `^\s*(Chương|Mục|Điều)\b`, nên khớp cả tham chiếu chéo GIỮA câu — "Điều 11
# của Luật này quy định.", "Điều ước quốc tế mà Cộng hòa..." — sinh ra 15 mục
# là mảnh câu, mỗi mảnh CẮT ĐÔI một Điều thật. Nay `Điều` phải mang dạng
# "Điều <số>." rồi mới tới tiêu đề.
#
# `Chương` và `Mục` GIỮ NGUYÊN: chúng sinh 190 mục trống, nhưng đó là việc của
# P3b (phân cấp) — đụng vào đây là trộn thêm một biến vào cùng một lần re-index.
_HEADING_RE = re.compile(
    r"^\s*(Chương|Mục)\b"
    r"|^\s*Điều\s+\d+\s*[\.\-–]\s*\S"
    r"|^\s*\d+\.\d{1,2}(\.\d{1,2})*(?!\d)[\.\)]?\s+\S")
```

- [ ] **Step 4: Chạy để xác nhận xanh**

```bash
./.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pdf.py -q -m "not integration and not live"
```

Kỳ vọng: PASS toàn bộ.

- [ ] **Step 5: Đổi `parse_pdf` sang hai lượt**

Thay thân `parse_pdf` trong `backend/src/rag/parse.py` bằng:

```python
def parse_pdf(path: str) -> list[dict]:
    """Heuristic headings (no font info): numbered/keyword headings & short ALL-CAPS lines.

    HAI LƯỢT từ 2026-08-19: gom dòng theo trang trước, nhận diện rác
    header/footer trên toàn tài liệu, rồi mới dựng block. Một lượt thì không
    thể biết một dòng có lặp trên phần lớn số trang hay không.
    """
    reader = pypdf.PdfReader(path)
    pages: list[list[str]] = []
    for page in reader.pages:
        lines = []
        for line in (page.extract_text() or "").splitlines():
            # pypdf maps some unrecognized glyphs (e.g. a custom bullet-point
            # font) to U+0000 instead of dropping them; Postgres text columns
            # reject NUL bytes outright, so strip them at the source.
            text = line.replace("\x00", "").strip()
            if text:
                lines.append(text)
        pages.append(lines)

    furniture = detect_page_furniture(pages)
    blocks: list[dict] = []
    for pageno, lines in enumerate(pages, start=1):
        for text in lines:
            if _normalize_digits(text) in furniture:
                continue
            is_heading = bool(_HEADING_RE.match(text)) or (
                text.isupper() and len(text) <= 80
            )
            blocks.append({"text": text,
                           "heading_level": 2 if is_heading else None,
                           "page": pageno})
    return blocks
```

- [ ] **Step 6: Kiểm trên PDF THẬT — trước/sau, không tin test giả**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -c "
import sys, io, glob, os; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.rag.parse import parse_pdf
tot = junk = head = 0
for p in sorted(glob.glob('src/rag/seed/**/*.pdf', recursive=True)):
    b = parse_pdf(p)
    tot += len(b)
    junk += sum(1 for x in b if 'about:blank' in x['text'])
    head += sum(1 for x in b if x['heading_level'])
    print('%-28s block=%5d rac=%3d heading=%4d' % (os.path.basename(p)[:28], len(b), sum(1 for x in b if 'about:blank' in x['text']), sum(1 for x in b if x['heading_level'])))
print('TONG: block=%d | con rac=%d (phai = 0) | heading=%d' % (tot, junk, head))
assert junk == 0, 'VAN CON RAC'
print('OK')"
```

Kỳ vọng: `con rac=0`.

- [ ] **Step 7: Chạy toàn bộ test**

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

Kỳ vọng: PASS (mốc: 1739 passed, 2 skipped).

- [ ] **Step 8: Commit**

```bash
cd /d/Youdoo
git add backend/src/rag/parse.py backend/tests/rag/test_parse_pdf.py
git commit -m "feat(rag): parse_pdf hai luot loc rac trang + siet _HEADING_RE khoi tham chieu giua cau"
```

---

## Task 3: PDF ra 0 block → báo lỗi lớn tiếng

**Files:**
- Modify: `backend/src/rag/ingest.py`
- Test: `backend/tests/rag/test_ingest.py`

**Interfaces:**
- Consumes: không gì.
- Produces: `IngestError(RuntimeError)` xuất từ `src.rag.ingest`; `_ingest_file` ném nó khi tệp **được nhận** (đuôi nằm trong `_EXT`) nhưng `_chunks_for` trả rỗng.

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `backend/tests/rag/test_ingest.py`:

```python
# ── PDF ra 0 block phải BÁO LỖI, không skipped im lặng (spec §5) ─────────────
# PDF scan (không có lớp text) hiện trả {"skipped": 1} và tài liệu vắng mặt
# khỏi corpus mà không ai biết — cùng lớp lỗi với reranker chết im lặng suốt
# 6 tuần.
import pytest

from src.rag import ingest as _ing


class _FakeConn:
    """Đủ cho nhánh kiểm content_hash: _ingest_file gọi conn.execute(...)
    .fetchone() TRƯỚC khi tới nhánh 0-chunk, nên truyền None sẽ ném
    AttributeError chứ không phải IngestError — test xanh/đỏ vì lý do sai."""

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None          # chưa từng ingest tệp này


def test_tep_duoc_nhan_nhung_ra_rong_thi_nem_loi(monkeypatch, tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(_ing, "_chunks_for", lambda *a, **k: [])
    with pytest.raises(_ing.IngestError) as e:
        _ing._ingest_file(str(f), conn=_FakeConn())
    assert "scan.pdf" in str(e.value)


def test_tep_duoi_la_van_skipped_khong_nem(tmp_path):
    # Chỉ tệp ĐƯỢC NHẬN mà ra rỗng mới là lỗi; đuôi lạ vẫn bỏ qua như cũ.
    f = tmp_path / "ghi_chu.txt"
    f.write_text("khong phai tai lieu duoc ho tro", encoding="utf-8")
    assert _ing._ingest_file(str(f), conn=None) == {
        "ingested": 0, "skipped": 1, "chunks": 0}
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `AttributeError: module 'src.rag.ingest' has no attribute 'IngestError'`.

- [ ] **Step 3: Viết implementation**

Trong `backend/src/rag/ingest.py`, thêm ngay dưới `_EXT`:

```python
class IngestError(RuntimeError):
    """Tệp được nhận nhưng không sinh được chunk nào.

    Trước 2026-08-19 ca này trả {"skipped": 1} im lặng, nên một PDF scan
    (không có lớp text) vắng mặt khỏi corpus mà không ai biết — cùng lớp lỗi
    với reranker chết im lặng 6 tuần. Hỏng lớn tiếng còn hơn thiếu âm thầm."""
```

Trong `_ingest_file`, thay khối:

```python
    chunks = _chunks_for(path, kind, doc_id)
    if not chunks:
        return {"ingested": 0, "skipped": 1, "chunks": 0}
```

bằng:

```python
    chunks = _chunks_for(path, kind, doc_id)
    if not chunks:
        raise IngestError(
            f"{path}: tệp được nhận ({kind}) nhưng không sinh được chunk nào. "
            f"Với PDF, nguyên nhân thường gặp là bản scan không có lớp text — "
            f"cần OCR trước khi ingest. KHÔNG bỏ qua âm thầm: tài liệu sẽ vắng "
            f"mặt khỏi corpus mà không ai biết.")
```

**Lưu ý thứ tự:** khối này nằm SAU phần kiểm `content_hash`, nên tệp đã ingest thành công trước đó vẫn `skipped` bình thường, không bị lỗi oan.

- [ ] **Step 4: Chạy để xác nhận xanh**

```bash
./.venv/Scripts/python.exe -m pytest tests/rag/test_ingest.py -q -m "not integration and not live"
```

Kỳ vọng: PASS.

- [ ] **Step 5: Commit**

```bash
cd /d/Youdoo
git add backend/src/rag/ingest.py backend/tests/rag/test_ingest.py
git commit -m "feat(rag): PDF ra 0 block nem IngestError thay vi skipped im lang"
```

---

## Task 4: Re-index và đo

**Files:** không sửa code. Sinh ra baseline mới ở Task 5.

- [ ] **Step 1: Ghi lại số ĐO TRƯỚC**

```bash
cd /d/Youdoo/backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.rag import db
c = db.connect()
q = lambda s, *a: c.execute(s, a).fetchone()[0]
print('chunk           :', q('select count(*) from rag_chunks'))
print('tai lieu        :', q('select count(*) from rag_documents'))
print('chunk co rac    :', q('select count(*) from rag_chunks where chunk_text like %s', '%about:blank%'))
print('muc la manh cau :', q(\"select count(distinct section_path) from rag_chunks where section_path ~ '^Điều [0-9]+ (của|này|khoản)'\"))
c.close()"
```

Kỳ vọng khớp mốc: 3300 chunk / 17 tài liệu / 727 chunk rác / 15 mục mảnh câu.

- [ ] **Step 2: XOÁ `rag_documents` trước khi re-index — BƯỚC KHÔNG ĐƯỢC BỎ**

`_ingest_file` bỏ qua tệp khi `content_hash` khớp. Đợt này **tệp không đổi, chỉ code đổi**, nên chạy thẳng `ingest_path` sẽ báo `skipped` cho cả 17 tài liệu và **không gì xảy ra** — trong khi trông như đã chạy xong. Đây là cái bẫy dễ mắc nhất của cả plan.

```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "DELETE FROM rag_documents;" -c "SELECT count(*) AS chunks_con_lai FROM rag_chunks;"
```

Kỳ vọng: `chunks_con_lai = 0` (cascade).

- [ ] **Step 3: Re-index**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -m src.rag.ingest src/rag/seed
```

Kỳ vọng: in dict với `ingested: 17`, `skipped: 0`. Mất ~4 phút (bge-m3 trên GPU).
Nếu `ingested` khác 17, **dừng** — có tệp bị lỗi hoặc Step 2 chưa chạy.

- [ ] **Step 4: Ghi lại số ĐO SAU**

Chạy lại đúng lệnh Step 1.

Kỳ vọng: `chunk co rac = 0`, `muc la manh cau = 0`, `tai lieu = 17`, tổng chunk giảm nhẹ.

- [ ] **Step 5: Test hợp đồng của cả hai bộ eval phải xanh**

Đây là phép kiểm rằng quyết định neo nhãn theo `(tệp, mục)` hồi P0 thật sự trả cổ tức: `chunk_index` đổi hết sau re-index, nhưng nhãn không được trôi.

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/ -q -m "integration"
```

Kỳ vọng: PASS. Nếu đỏ, **dừng và báo** — nghĩa là re-index đã đổi `section_path` của một Điều hợp lệ, điều spec §7 khẳng định là không xảy ra.

- [ ] **Step 6: Đo `retrieval` và so baseline cũ**

```bash
./.venv/Scripts/python.exe -c "
import sys, io, json, asyncio; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from evals.run_eval import eval_retrieval
r = asyncio.run(eval_retrieval())
b = json.load(open('evals/baseline-bge-m3-retrieval.json', encoding='utf-8'))
print('%-13s %9s %9s %9s' % ('so do','sau','baseline','delta'))
for k in ('recall_at_20','recall_at_6','mrr'):
    print('%-13s %9.4f %9.4f %+9.4f' % (k, r[k], b[k], r[k]-b[k]))
print('methods:', r['methods_seen'])
print('CONG:', 'DAT' if r['recall_at_20'] >= b['recall_at_20'] and r['mrr'] >= b['mrr'] else 'TRUOT')
"
```

- [ ] **Step 7: Đo `synthesis_live` và so baseline cũ**

```bash
./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8 2>&1 | grep -vE "^(INFO|WARNING|Loading|Warning)" | ./.venv/Scripts/python.exe -c "
import sys, io, json; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = sys.stdin.read(); d = json.loads(t[t.index('{'):t.rindex('}')+1])
b = json.load(open('evals/baseline-gemini-3.1-flash-lite-synthesis_live.json', encoding='utf-8'))
for k in ('fact_acc','refusal_acc','citation_acc'):
    print('%-13s sau=%.4f baseline=%.4f delta=%+.4f' % (k, d[k], b[k], d[k]-b[k]))
print('fails:', [f['question'][:50] for f in d['fails']])
print('CONG:', 'DAT' if all(d[k] >= b[k] for k in ('fact_acc','refusal_acc','citation_acc')) else 'TRUOT')
"
```

**Nếu bất kỳ cổng nào TRƯỢT: dừng, báo lại, không ghi baseline.** Đợt này chỉ dọn rác nên không có lý do nào để chất lượng đi xuống — tụt là dấu hiệu bộ lọc ăn nhầm nội dung thật.

---

## Task 5: Ghi baseline mới và ghi kết quả vào spec

**Files:**
- Modify: `backend/evals/baseline-bge-m3-retrieval.json`, `backend/evals/baseline-gemini-3.1-flash-lite-synthesis_live.json`
- Modify: `docs/superpowers/specs/2026-08-19-ingest-hygiene-design.md` (thêm §9)

- [ ] **Step 1: Ghi lại hai baseline (chỉ khi Task 4 đã qua cổng)**

```bash
cd /d/Youdoo/backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 --save-baseline
./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8 --save-baseline
```

- [ ] **Step 2: Thêm §9 vào spec, điền số THẬT**

```markdown
## 9. Kết quả (ngày <ngày>)

**Số đo cơ học:**

| Chỉ số | Trước | Sau |
|---|---|---|
| chunk chứa `about:blank` | 727 | <n> |
| mục là mảnh câu | 15 | <n> |
| tổng chunk | 3.300 | <n> |
| tài liệu | 17 | <n> |

**Số đo chất lượng:**

| Bộ | Số đo | Trước | Sau | delta |
|---|---|---|---|---|
| retrieval | `recall_at_20` | 1,0000 | | |
| retrieval | `recall_at_6` | 0,9196 | | |
| retrieval | `mrr` | 0,8253 | | |
| synthesis_live | `fact_acc` | 1,0000 | | |
| synthesis_live | `refusal_acc` | 1,0000 | | |
| synthesis_live | `citation_acc` | 1,0000 | | |

**Kết luận:** <có/không cải thiện đo được, và vì sao>.

**Test hợp đồng của hai bộ eval sau re-index:** <xanh/đỏ>. Đây là phép kiểm
rằng quyết định neo nhãn theo `(tệp, mục)` hồi P0 trả cổ tức — `chunk_index`
đổi hết mà nhãn không trôi.
```

Nếu cả hai bộ đứng yên, **viết đúng như vậy**. Spec §7 đã chốt trước rằng kết quả âm cũng là kết luận có giá trị — đừng tô hồng, và đừng đi thêm ca cho tới khi hết delta.

- [ ] **Step 3: Chạy toàn bộ test lần cuối**

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
./.venv/Scripts/python.exe -m pytest -q -m "integration"
```

- [ ] **Step 4: Commit**

```bash
cd /d/Youdoo
git add backend/evals/baseline-bge-m3-retrieval.json backend/evals/baseline-gemini-3.1-flash-lite-synthesis_live.json docs/superpowers/specs/2026-08-19-ingest-hygiene-design.md
git commit -m "docs(spec): ket qua P3a sau re-index + baseline moi cho ca hai bo eval"
```

---

## Sau plan này

| Việc | Điều kiện mở |
|---|---|
| P3b — phân cấp Chương › Mục › Điều | Cần bằng chứng phân cấp giúp truy xuất; nay có hai thước đo để lấy. Kèm đợt di trú 57 nhãn. |
| Luật `isupper()` | Cùng điều kiện với P3b — phân biệt quốc hiệu với tiêu đề chương cần chính phân cấp đó. |
| P1 metadata filtering, P2 query rewrite, P4 `compress`/`passes_floor` | Không phụ thuộc P3a. |
| Mở rộng nhóm `hard` của golden set P0 | Kết luận "rerank hại câu hard" vẫn dựa trên n=17. |
