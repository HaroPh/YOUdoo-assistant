# Endpoint trích tài liệu (lát 1) — kế hoạch thi hành

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend nhận tệp từ Open WebUI, chạy parser sẵn có (kể cả OCR bậc 1+2), trả text theo trang — vá lỗ tài liệu scan hiện bị trích ra 15 dấu cách.

**Architecture:** Một module lá `src/rag/extract.py` (thuần, nhận `path`, trả list dict, không biết HTTP) cộng một route mỏng trong `src/main.py` lo xác thực, tệp tạm và ánh xạ lỗi sang mã HTTP. Không trạng thái: không lưu tệp, không ghi DB, không đụng `retrieve()` hay agent.

**Tech Stack:** FastAPI, httpx + ASGITransport cho test, pytest-asyncio, các parser sẵn có trong `src/rag/parse.py`.

**Spec:** `docs/superpowers/specs/2026-09-09-endpoint-trich-tai-lieu-design.md`

## Global Constraints

- **Định danh trong code (tên hàm, class, biến, hằng số, tên tệp) BẮT BUỘC bằng TIẾNG ANH.** Chú thích viết tiếng Việt.
- Mọi lệnh pytest phải kèm `-m "not integration and not live"`. Bỏ cờ này từng gọi API LLM thật và gây sự cố.
- venv nằm ở `D:/Youdoo/backend/.venv` — worktree **không** có venv riêng. Chạy pytest từ thư mục `backend` của worktree bằng `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest`.
- **Trích ra rỗng KHÔNG BAO GIỜ trả 200.** "Rỗng" = không còn block nào có text khác rỗng sau `strip()`, KHÔNG phải độ dài 0 — Open WebUI trả 15 ký tự dấu cách và coi là nội dung, đó chính là lỗi đang đi vá.
- Không dựng cơ chế xác thực thứ hai: dùng `_kiem_token` đã có trong `main.py`.
- Không lưu tệp, không ghi DB, không đụng `retrieve()`/agent/prompt.

---

### Task 1: Module trích tài liệu (`src/rag/extract.py`)

**Files:**
- Create: `backend/src/rag/extract.py`
- Test: `backend/tests/rag/test_extract.py`

**Interfaces:**
- Consumes: `src.rag.parse.parse_pdf/parse_docx/parse_pptx/parse_xlsx` — cả bốn nhận `path`, KHÔNG nhận bytes
- Produces: `SUPPORTED_EXT: dict[str, str]`, `extract_documents(path: str, filename: str) -> list[dict]`, `UnsupportedFormat(ValueError)`, `EmptyExtraction(ValueError)`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/rag/test_extract.py
"""`extract.extract_documents` — trích tài liệu cho endpoint HTTP.

Cái bẫy trung tâm: Open WebUI trả 15 ký tự TOÀN DẤU CÁCH cho một bản scan 16
trang và coi đó là nội dung, nên người dùng nghe "không tìm thấy tài liệu liên
quan" thay vì "tôi không đọc được tài liệu". Test whitespace là chốt cửa đó.
"""
import pytest

from src.rag import extract


def test_pdf_blocks_group_into_one_document_per_page(monkeypatch):
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([
        {"text": "dong A", "heading_level": None, "page": 1},
        {"text": "dong B", "heading_level": None, "page": 1},
        {"text": "dong C", "heading_level": None, "page": 2},
    ], []))
    docs = extract.extract_documents("/khong/quan/trong.pdf", "x.pdf")
    assert [d["metadata"]["page"] for d in docs] == [1, 2]
    assert docs[0]["page_content"] == "dong A\ndong B"


def test_docx_becomes_a_single_document_because_it_has_no_pages(monkeypatch):
    # `parse_docx` đặt page=None cho MỌI block — .docx không có khái niệm
    # trang. Bịa ra một cách chia là bịa cấu trúc.
    monkeypatch.setattr(extract, "parse_docx", lambda p: [
        {"text": "mot", "heading_level": 1, "page": None},
        {"text": "hai", "heading_level": None, "page": None},
    ])
    docs = extract.extract_documents("/x.docx", "x.docx")
    assert len(docs) == 1
    assert docs[0]["page_content"] == "mot\nhai"
    assert "page" not in docs[0]["metadata"]


def test_whitespace_only_extraction_raises_instead_of_returning_content(monkeypatch):
    # ĐÂY LÀ LỖI ĐANG ĐI VÁ. Kiểm theo độ dài chuỗi sẽ cho 15 dấu cách lọt qua.
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([
        {"text": "   ", "heading_level": None, "page": 1},
        {"text": "\n\t ", "heading_level": None, "page": 2},
    ], []))
    with pytest.raises(extract.EmptyExtraction):
        extract.extract_documents("/x.pdf", "x.pdf")


def test_no_blocks_at_all_raises(monkeypatch):
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([], []))
    with pytest.raises(extract.EmptyExtraction):
        extract.extract_documents("/x.pdf", "x.pdf")


def test_unsupported_extension_raises_and_names_what_is_supported():
    with pytest.raises(extract.UnsupportedFormat) as e:
        extract.extract_documents("/x.doc", "x.doc")
    assert ".pdf" in str(e.value)


def test_extension_is_read_from_filename_not_from_path(monkeypatch):
    # Tệp tạm mang đuôi ngẫu nhiên; đuôi thật đến từ header X-Filename.
    monkeypatch.setattr(extract, "parse_docx", lambda p: [
        {"text": "noi dung", "heading_level": None, "page": None}])
    docs = extract.extract_documents("/tmp/abc123.tmp", "bao-cao.docx")
    assert docs[0]["page_content"] == "noi dung"


def test_supported_ext_stays_in_sync_with_the_ingest_table():
    """Hai bảng đuôi tệp phải phủ cùng một tập.

    Lệch nhau nghĩa là endpoint nhận thứ đường nạp không xử lý được, hoặc từ
    chối thứ nó xử lý được — và không ai phát hiện cho tới khi người dùng gửi
    đúng loại tệp đó. Dự án đã có tiền lệ hai danh sách đuôi trôi lệch (xem
    chú thích trên `ingest.DOCUMENT_EXT`).
    """
    from src.rag import ingest
    assert set(extract.SUPPORTED_EXT) == set(ingest._EXT)
```

- [ ] **Step 2: Chạy test cho chắc nó ĐỎ**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_extract.py -q -m "not integration and not live"`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.rag.extract'`

- [ ] **Step 3: Viết `src/rag/extract.py`**

```python
# backend/src/rag/extract.py
"""Trích tài liệu cho endpoint HTTP — module LÁ, không biết gì về FastAPI.

Vì sao tách khỏi `main.py`: phần nặng (chọn parser, gom trang, quyết định
rỗng) phải test được mà không cần dựng client HTTP. `main.py` chỉ còn lo xác
thực, tệp tạm và ánh xạ lỗi sang mã HTTP.

Vì sao module này tồn tại: đo 2026-09-09, Open WebUI trích `DVT_2022.pdf`
(scan 16 trang, 5,1 MB) ra 15 ký tự toàn dấu cách, `status=failed`, và người
dùng chỉ thấy "không tìm thấy tài liệu liên quan". Repo này đã có OCR đọc được
chính tệp đó, nhưng không route nào nhận tệp nên năng lực đó chưa bao giờ tới
được người dùng.
"""
import os

from .parse import parse_docx, parse_pdf, parse_pptx, parse_xlsx


class UnsupportedFormat(ValueError):
    """Đuôi tệp không nạp thẳng được."""


class EmptyExtraction(ValueError):
    """Không trích được nội dung nào — người gọi PHẢI báo lỗi, không trả rỗng."""


# Đuôi -> loại parser. PHẢI khớp `ingest._EXT`; có test bất biến giữ điều đó.
# `.doc`/`.xls` cần LibreOffice chuyển đổi (`convert.py`), ngoài phạm vi lát 1.
SUPPORTED_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xltx": "xlsx",
    ".pptx": "pptx",
}


def _warning_lines(warnings) -> list[str]:
    """Cảnh báo parser -> danh sách chuỗi đọc được. KHÔNG nuốt."""
    return [f"{a}: {b}" for a, b in warnings]


def _documents_from_blocks(blocks, filename, warnings, *, group_by_page):
    """Block -> list Document. Bỏ block rỗng SAU `strip()`.

    `group_by_page=False` dùng cho .docx: `parse_docx` đặt `page=None` cho mọi
    block, nên gom theo trang sẽ tạo đúng một nhóm mang khoá `None` — nhãn sai
    còn tệ hơn không có nhãn.
    """
    kept = [b for b in blocks if (b.get("text") or "").strip()]
    if not kept:
        return []
    lines = _warning_lines(warnings)
    if not group_by_page:
        return [{"page_content": "\n".join(b["text"] for b in kept),
                 "metadata": {"source": filename, "warnings": lines}}]

    by_page: dict = {}
    for b in kept:
        by_page.setdefault(b.get("page"), []).append(b)
    docs = []
    for page in sorted(by_page, key=lambda p: (p is None, p)):
        group = by_page[page]
        # `source_kind`/`ocr_conf` do `parse_pdf` đặt CHUNG cho cả trang, nên
        # lấy giá trị đầu tiên gặp là đủ; mặc định "text" khi không có.
        conf = next((b["ocr_conf"] for b in group
                     if b.get("ocr_conf") is not None), None)
        kind = "ocr" if any(b.get("source_kind") == "ocr" for b in group) else "text"
        meta = {"source": filename, "source_kind": kind, "ocr_conf": conf,
                # Cảnh báo gắn vào MỌI document chứ không riêng cái đầu: Open
                # WebUI cắt chunk theo từng document, nên gắn một chỗ nghĩa là
                # phần lớn chunk mất cảnh báo.
                "warnings": lines}
        if page is not None:
            meta["page"] = page
        docs.append({"page_content": "\n".join(b["text"] for b in group),
                     "metadata": meta})
    return docs


def _documents_from_sheets(sheets, filename, warnings):
    """Bảng tính: đơn vị tách là SHEET, không phải trang.

    `parse_xlsx` trả `sheets` (khoá `sheet`/`columns`/`rows`) chứ không trả
    block có `page`, nên nó không đi qua `_documents_from_blocks` được.
    """
    lines = _warning_lines(warnings)
    docs = []
    for sh in sheets:
        rows = [" | ".join("" if c is None else str(c) for c in row)
                for row in sh["rows"]]
        rows = [r for r in rows if r.strip(" |")]
        if not rows:
            continue
        header = " | ".join(str(c) for c in sh["columns"])
        body = [header] + rows if header.strip(" |") else rows
        docs.append({
            "page_content": "\n".join(body),
            "metadata": {"source": filename, "sheet": sh["sheet"],
                         "source_kind": "text", "warnings": lines},
        })
    return docs


def extract_documents(path: str, filename: str) -> list[dict]:
    """Tệp -> list {"page_content", "metadata"}, một phần tử mỗi trang/sheet.

    `path` là tệp TẠM (đuôi ngẫu nhiên); `filename` là tên thật do người dùng
    gửi và là NGUỒN DUY NHẤT để chọn parser — không đoán định dạng từ nội dung.

    Ném `EmptyExtraction` khi không còn nội dung nào sau `strip()`. Người gọi
    PHẢI báo lỗi thay vì trả 200 với chuỗi rỗng: đó đúng là hành vi của Open
    WebUI mà endpoint này sinh ra để thay thế.

    `TesseractMissing` từ `parse_pdf` được thả LÊN nguyên vẹn — người gọi ánh
    xạ nó thành 503, vì "thiếu binary" khác hẳn "tài liệu không có chữ".
    """
    ext = os.path.splitext(filename)[1].lower()
    kind = SUPPORTED_EXT.get(ext)
    if kind is None:
        ten = ext or "(khong co)"
        raise UnsupportedFormat(
            f"duoi {ten} khong nap thang duoc. "
            f"Ho tro: {', '.join(sorted(SUPPORTED_EXT))}")

    if kind == "pdf":
        blocks, warnings = parse_pdf(path)
        docs = _documents_from_blocks(blocks, filename, warnings,
                                      group_by_page=True)
    elif kind == "pptx":
        docs = _documents_from_blocks(parse_pptx(path), filename, [],
                                      group_by_page=True)
    elif kind == "docx":
        docs = _documents_from_blocks(parse_docx(path), filename, [],
                                      group_by_page=False)
    else:
        sheets, warnings = parse_xlsx(path)
        docs = _documents_from_sheets(sheets, filename, warnings)

    if not docs:
        raise EmptyExtraction(
            f"{filename}: khong trich duoc noi dung nao. Voi PDF, day thuong "
            f"la ban scan ma tang OCR cung khong doc ra chu.")
    return docs
```

- [ ] **Step 4: Chạy test cho chắc nó XANH**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_extract.py -q -m "not integration and not live"`
Expected: PASS, 7 test

- [ ] **Step 5: Commit**

Dùng lệnh sau (thông điệp viết không dấu theo lệ của repo):

```
git add backend/src/rag/extract.py backend/tests/rag/test_extract.py
git commit -F - <<'MSG'
feat(rag): module trich tai lieu cho endpoint HTTP

Module LA, khong biet FastAPI: nhan path + ten tep that, tra list
{page_content, metadata}, mot phan tu moi trang (moi sheet voi bang tinh, mot
Document ca tep voi .docx vi parse_docx dat page=None cho moi block).

Trich ra rong -> nem EmptyExtraction. "Rong" = khong con block nao co text
khac rong sau strip(), KHONG phai do dai 0: Open WebUI tra 15 ky tu dau cach
cho mot ban scan 16 trang va coi la noi dung, do chinh la loi dang di va.

Test bat bien giu SUPPORTED_EXT khop ingest._EXT -- lech nhau thi endpoint
nhan thu duong nap khong xu ly duoc, va khong ai biet cho toi khi nguoi dung
gui dung loai tep do.
MSG
```

---

### Task 2: Route `PUT /v1/documents/process`

**Files:**
- Modify: `backend/src/main.py` — thêm route ngay sau `list_models`
- Test: `backend/tests/test_main_documents.py`

**Interfaces:**
- Consumes: `src.rag.extract.{SUPPORTED_EXT, extract_documents, UnsupportedFormat, EmptyExtraction}` (Task 1); `main._kiem_token(req)` đã có; `src.ocr.engine.TesseractMissing` đã có
- Produces: route `PUT /v1/documents/process` trả JSON list `[{"page_content", "metadata"}, ...]`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_main_documents.py
"""`PUT /v1/documents/process` — endpoint trích tài liệu.

Nói đúng hợp đồng `external_document_loader` của Open WebUI (đọc từ
`retrieval/loaders/external_document.py` của họ): body là bytes THÔ, tên tệp
đến qua header `X-Filename` đã urlencode, trả về list {page_content, metadata}.
"""
import os

import httpx
import pytest

from src import main as main_module
from src.rag import extract

TOKEN = "token-thu-cho-test"


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://test")


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch):
    monkeypatch.setenv("YOUDOO_API_TOKEN", TOKEN)
    yield


def _headers(filename="x.pdf", token=TOKEN):
    h = {"X-Filename": filename}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


@pytest.mark.asyncio
async def test_rejects_a_request_without_a_token():
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers={"X-Filename": "x.pdf"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rejects_a_request_without_the_filename_header():
    # Không đoán định dạng từ nội dung — đoán sai thì parser nổ ở chỗ khó hiểu.
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_rejects_an_unsupported_extension_with_415():
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("bao-cao.doc"))
    assert r.status_code == 415
    assert ".pdf" in r.json()["detail"]


@pytest.mark.asyncio
async def test_empty_extraction_returns_422_not_200(monkeypatch):
    # LỖI ĐANG ĐI VÁ: trả 200 với nội dung rỗng làm người dùng nghe "không tìm
    # thấy tài liệu liên quan" thay vì biết tài liệu không đọc được.
    def _no(path, filename):
        raise extract.EmptyExtraction("khong trich duoc noi dung nao")

    monkeypatch.setattr(main_module, "extract_documents", _no)
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("x.pdf"))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_returns_the_documents_the_extractor_produced(monkeypatch):
    monkeypatch.setattr(main_module, "extract_documents", lambda p, f: [
        {"page_content": "trang 1", "metadata": {"source": f, "page": 1}}])
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("bao-cao.pdf"))
    assert r.status_code == 200
    assert r.json() == [{"page_content": "trang 1",
                         "metadata": {"source": "bao-cao.pdf", "page": 1}}]


@pytest.mark.asyncio
async def test_the_temp_file_is_removed_even_when_the_parser_raises(monkeypatch):
    """Rò tệp tạm là loại lỗi chỉ lộ ra sau hàng nghìn request."""
    seen = {}

    def _no(path, filename):
        seen["path"] = path
        raise RuntimeError("parser hong")

    monkeypatch.setattr(main_module, "extract_documents", _no)
    async with _client() as c:
        with pytest.raises(RuntimeError):
            await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("x.pdf"))
    assert not os.path.exists(seen["path"])


@pytest.mark.asyncio
async def test_the_filename_header_is_url_decoded(monkeypatch):
    # Open WebUI gửi `quote(basename)`, nên tên có dấu cách hoặc tiếng Việt tới
    # nơi dưới dạng %XX. Không giải mã thì đuôi vẫn đúng nhưng `source` sai.
    monkeypatch.setattr(
        main_module, "extract_documents",
        lambda p, f: [{"page_content": "x", "metadata": {"source": f}}])
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("b%C3%A1o%20c%C3%A1o.pdf"))
    assert r.json()[0]["metadata"]["source"] == "báo cáo.pdf"
```

- [ ] **Step 2: Chạy test cho chắc nó ĐỎ**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/test_main_documents.py -q -m "not integration and not live"`
Expected: FAIL — route chưa tồn tại (404 hoặc 405)

- [ ] **Step 3: Thêm import vào `src/main.py`**

Nối vào các khối import sẵn có, giữ nguyên cách nhóm đang dùng trong tệp:

```python
import tempfile
from urllib.parse import unquote

from src.ocr.engine import TesseractMissing
from src.rag.extract import (EmptyExtraction, SUPPORTED_EXT, UnsupportedFormat,
                             extract_documents)
```

- [ ] **Step 4: Thêm route ngay sau `list_models`**

```python
@app.put("/v1/documents/process")
async def process_document(req: Request):
    """Trích text từ tệp người dùng đính kèm.

    Nói đúng hợp đồng `external_document_loader` của Open WebUI: body là bytes
    THÔ (không multipart), tên tệp qua `X-Filename` đã urlencode, trả về list
    {page_content, metadata}. Hợp đồng đó đủ tổng quát để cũng là hợp đồng của
    ta — không có lớp adapter nào.

    Vì sao tồn tại: đo 2026-09-09, Open WebUI trích `DVT_2022.pdf` (scan 16
    trang) ra 15 ký tự toàn dấu cách và người dùng nghe "không tìm thấy tài
    liệu liên quan". Repo đã có OCR đọc được tệp đó nhưng chưa route nào nhận
    tệp.
    """
    _kiem_token(req)
    filename = unquote(req.headers.get("x-filename") or "").strip()
    if not filename:
        raise HTTPException(
            status_code=400,
            detail="thieu header X-Filename - dinh dang suy tu TEN tep, "
                   "khong doan tu noi dung")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXT:
        raise HTTPException(
            status_code=415,
            detail=f"duoi {ext or '(khong co)'} chua ho tro. "
                   f"Ho tro: {', '.join(sorted(SUPPORTED_EXT))}")
    data = await req.body()
    if not data:
        raise HTTPException(status_code=400, detail="body rong")

    fd, tmp = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # `to_thread` BẮT BUỘC: parser (nhất là OCR) chặn CPU hàng phút. Chạy
        # thẳng trong vòng lặp sự kiện là treo mọi request khác của backend.
        # Open WebUI cũng gọi loader của họ theo đúng cách này.
        docs = await asyncio.to_thread(extract_documents, tmp, filename)
    except EmptyExtraction as e:
        raise HTTPException(status_code=422, detail=str(e))
    except UnsupportedFormat as e:
        raise HTTPException(status_code=415, detail=str(e))
    except TesseractMissing as e:
        # "thiếu binary" khác hẳn "tài liệu không có chữ" — đừng gộp vào 422,
        # người đọc log sẽ không biết phải sửa gì.
        raise HTTPException(status_code=503, detail=str(e))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return docs
```

- [ ] **Step 5: Chạy test cho chắc nó XANH**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/test_main_documents.py -q -m "not integration and not live"`
Expected: PASS, 7 test

- [ ] **Step 6: Chạy TOÀN suite để chắc không phá gì**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not integration and not live" -p no:randomly`
Expected: PASS. Nền trước kế hoạch này: 2481 passed, 1 skipped, 0 failed.

- [ ] **Step 7: Commit**

```
git add backend/src/main.py backend/tests/test_main_documents.py
git commit -F - <<'MSG'
feat(api): PUT /v1/documents/process - endpoint trich tai lieu

Noi dung hop dong external_document_loader cua Open WebUI: body bytes THO,
ten tep qua X-Filename (urlencode), tra list {page_content, metadata}. Hop
dong do du tong quat de cung la hop dong cua ta, khong can adapter.

Dung lai _kiem_token co san, khong dung co che xac thuc thu hai.

Parser chay trong asyncio.to_thread: OCR chan CPU hang phut, chay thang trong
vong lap su kien la treo moi request khac cua backend.

Ba tinh huong loi anh xa RIENG: 422 khong trich duoc noi dung, 415 dinh dang
chua ho tro, 503 thieu Tesseract. Gop chung thi nguoi doc log khong biet sua gi.

Tep tam xoa trong finally KE CA khi parser nem, co test rieng.
MSG
```

---

### Task 3: Cổng nghiệm thu trên TỆP THẬT

**Files:**
- Test: `backend/tests/rag/test_extract_real_files.py`

**Interfaces:**
- Consumes: `src.rag.extract.extract_documents` (Task 1)
- Produces: không gì cho task sau — đây là cổng nghiệm thu cuối

- [ ] **Step 1: Viết cổng**

```python
# backend/tests/rag/test_extract_real_files.py
"""Nghiệm thu `extract_documents` trên TỆP THẬT, không phải block dựng tay.

Test của Task 1 đều monkeypatch parser, nên chúng chứng minh logic gom trang
đúng — KHÔNG chứng minh trích được chữ từ tệp thật. Hai chuyện khác nhau, và
dự án này đã đếm được nhiều lần một cổng "trông như đang gác nhưng không đo gì".

Ca quan trọng nhất là `DVT_2022.pdf`: Open WebUI trích nó ra 15 ký tự toàn dấu
cách (`status=failed`) và người dùng nghe "không tìm thấy tài liệu liên quan".
Cùng tệp, qua đường này, phải ra chữ thật.

Đánh dấu `integration`: cần Tesseract và mất khoảng một phút cho 16 trang scan.
"""
import os

import pytest

from src.ocr.engine import tesseract_path
from src.rag.extract import extract_documents

# Đường dẫn TUYỆT ĐỐI: `tmp-docs` là thư mục gitignore, chỉ tồn tại ở cây chính
# D:\Youdoo, không nằm trong worktree nào.
SCAN = r"D:\Youdoo\tmp-docs\ocr-scan-that\DVT_2022.pdf"
DIGITAL_PDF = "src/rag/seed/law/luat-thuegtgt.pdf"
DOCX = "src/rag/seed/policy.docx"


@pytest.mark.integration
@pytest.mark.skipif(not os.path.isfile(DIGITAL_PDF), reason="thieu kho luat")
def test_digital_pdf_yields_one_document_per_page_with_real_text():
    docs = extract_documents(DIGITAL_PDF, "luat-thuegtgt.pdf")
    assert len(docs) > 1
    assert all(d["page_content"].strip() for d in docs)
    pages = [d["metadata"]["page"] for d in docs]
    assert pages == sorted(pages)
    assert all(d["metadata"]["source_kind"] == "text" for d in docs)


@pytest.mark.integration
@pytest.mark.skipif(not os.path.isfile(DOCX), reason="thieu tai lieu nghiep vu")
def test_docx_yields_exactly_one_document():
    docs = extract_documents(DOCX, "policy.docx")
    assert len(docs) == 1
    assert docs[0]["page_content"].strip()


@pytest.mark.integration
@pytest.mark.skipif(tesseract_path() is None or not os.path.isfile(SCAN),
                    reason="chua cai tesseract hoac thieu kho scan")
def test_the_scanned_pdf_open_webui_could_not_read_now_yields_real_text():
    """Phép nghiệm thu THẬT: cùng tệp, khác kết quả.

    Open WebUI: 15 ký tự, toàn dấu cách, status=failed.
    Đường này: phải ra chữ Việt thật VÀ phải đánh dấu là do OCR đọc.
    """
    docs = extract_documents(SCAN, "DVT_2022.pdf")
    assert len(docs) >= 10, f"chi ra {len(docs)} trang tren tai lieu 16 trang"
    tong = sum(len(d["page_content"]) for d in docs)
    assert tong > 5000, f"chi trich duoc {tong} ky tu - Open WebUI ra 15"
    assert any(d["metadata"]["source_kind"] == "ocr" for d in docs), \
        "khong trang nao danh dau la OCR - tep nay KHONG co lop text"
    assert any(d["metadata"]["ocr_conf"] for d in docs)
    het = " ".join(d["page_content"] for d in docs).lower()
    assert "báo cáo" in het or "bao cao" in het
```

- [ ] **Step 2: Chạy cổng**

Run: `D:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_extract_real_files.py -q -m "integration and not live"`
Expected: PASS, 3 test. Mất khoảng một phút vì OCR 16 trang scan (lần sau nhanh nhờ đệm OCR khoá theo băm nội dung).

- [ ] **Step 3: Nếu ca scan ĐỎ, ĐỌC trước khi sửa**

Ngưỡng `tong > 5000` và `len(docs) >= 10` suy từ số đo 2026-09-08: OCR đọc được
`DVT_2022.pdf` với tỉ lệ tách hai cột tiền 0,889 trên 6 trang bảng của nó. Nếu
con số thật thấp hơn nhiều, **đừng hạ ngưỡng** — đó là tin tức, nghĩa là đường
trích này không đưa được kết quả OCR ra như tưởng. Ghi số thật rồi báo cáo.

- [ ] **Step 4: Commit**

```
git add backend/tests/rag/test_extract_real_files.py
git commit -F - <<'MSG'
test(rag): cong nghiem thu extract_documents tren TEP THAT

Test cua Task 1 deu monkeypatch parser -- chung minh logic gom trang dung,
KHONG chung minh trich duoc chu tu tep that. Hai chuyen khac nhau.

Ca quan trong nhat: DVT_2022.pdf, tep ma Open WebUI trich ra 15 ky tu toan dau
cach (status=failed). Cung tep, qua duong nay, phai ra chu that VA phai danh
dau source_kind=ocr.

Nguong suy tu so do 2026-09-08, khong rut tu khong khi. Neu do thap hon nhieu
thi DUNG ha nguong -- do la tin tuc.
MSG
```

---

### Task 4: Ghi chú thi hành + hướng dẫn cắm vào Open WebUI

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md` — nối mục mới ở cuối
- Modify: `docs/getting-started.md` — thêm mục cấu hình Open WebUI

**Interfaces:**
- Consumes: số đo thật của Task 3
- Produces: không gì cho task sau

- [ ] **Step 1: Nối ghi chú thi hành**

Nối vào cuối `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md`
một mục mới, đánh số tiếp theo mục cuối cùng đang có trong tệp, gồm:

- số đo THẬT của Task 3 — bao nhiêu trang, tổng bao nhiêu ký tự, `ocr_conf` —
  đặt cạnh con số 15 ký tự của Open WebUI để so sánh được;
- những gì **chưa** làm: không lưu tệp, `.doc`/`.xls` trả 415, không báo trước
  thời gian (thuộc lát 2);
- khó khăn gặp phải khi thi hành, nếu có.

Đây là yêu cầu đứng của chủ dự án: khó khăn, hướng đi và giới hạn ghi **trong
repo**, không chỉ trong đầu người làm.

- [ ] **Step 2: Thêm hướng dẫn cắm vào `docs/getting-started.md`**

Thêm mục sau, đặt cạnh phần nói về Open WebUI:

```markdown
### Cho Open WebUI dùng bộ trích tài liệu của backend

Mặc định Open WebUI trích PDF bằng bộ đọc lớp text — **tài liệu scan ra rỗng**
(đo 2026-09-09: một bản scan 16 trang trích ra 15 ký tự toàn dấu cách). Trỏ nó
vào backend để dùng OCR bậc 1 và bậc 2:

Settings, Admin Settings, Documents, Content Extraction Engine, chọn **External**

- URL: `http://host.docker.internal:8002/v1/documents`
  (Open WebUI tự nối `/process` vào cuối)
- API Key: cùng giá trị `YOUDOO_API_TOKEN` trong `.env`

Tài liệu scan mất khoảng 4 giây mỗi trang ở lần đầu; lần sau tức thì nhờ đệm
OCR khoá theo băm nội dung tệp.
```

- [ ] **Step 3: Commit**

```
git add docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md docs/getting-started.md
git commit -m "docs: ghi chu thi hanh endpoint trich tai lieu + cach cam vao Open WebUI"
```

---

### Task 5: Nghiệm thu SỐNG qua Open WebUI thật

Spec §9 đòi bước này, và dự án có yêu cầu đứng: **live-verify trước khi merge,
không phải sau**. Suite xanh đã nhiều lần không phát hiện thứ chỉ lộ ra khi
chạy thật — mail tool chết với mọi vai non-admin trong khi 1254 test xanh là ví
dụ đắt nhất.

**Files:** không sửa tệp nào. Đây là phép đo, không phải thay đổi mã.

**Interfaces:**
- Consumes: route của Task 2, chạy thật trên cổng 8002
- Produces: số đo đưa vào ghi chú thi hành của Task 4

- [ ] **Step 1: Chạy backend TỪ WORKTREE NÀY**

```
cd D:/Youdoo/.claude/worktrees/trich-tai-lieu/backend
D:/Youdoo/backend/.venv/Scripts/python.exe run.py
```

Chạy từ cây chính là nghiệm thu nhầm mã CŨ. Dự án đã có một lần merge hỏng đúng
vì nghiệm thu trên worktree thiếu venv rồi tưởng là xanh.

- [ ] **Step 2: Gọi thẳng endpoint bằng tệp scan thật, chưa qua Open WebUI**

```
curl -X PUT http://127.0.0.1:8002/v1/documents/process ^
  -H "Authorization: Bearer <YOUDOO_API_TOKEN>" ^
  -H "X-Filename: DVT_2022.pdf" ^
  -H "Content-Type: application/pdf" ^
  --data-binary "@D:/Youdoo/tmp-docs/ocr-scan-that/DVT_2022.pdf"
```

Kỳ vọng: HTTP 200, thân là một danh sách JSON, có phần tử mang
`metadata.source_kind` bằng `ocr` và `metadata.ocr_conf` khác null.
Ghi lại ba số: số phần tử, tổng độ dài `page_content`, thời gian thực.

Tách bước này khỏi Step 3 có chủ đích: nếu đính kèm qua Open WebUI mà hỏng, ta
cần biết ngay hỏng ở endpoint hay ở cấu hình Open WebUI.

- [ ] **Step 3: Cắm vào Open WebUI rồi đính kèm lại đúng tệp đó**

Settings, Admin Settings, Documents, Content Extraction Engine, chọn
**External**; URL `http://host.docker.internal:8002/v1/documents`; API Key đặt
bằng `YOUDOO_API_TOKEN`.

Rồi đính kèm `DVT_2022.pdf` và hỏi một câu về nội dung bên trong.

Kỳ vọng: trợ lý trả lời được từ nội dung tài liệu. Trước bản vá, câu trả lời là
*"Không tìm thấy tài liệu liên quan đến câu hỏi này."*

- [ ] **Step 4: Xác nhận Open WebUI trích được THẬT, không phải trông như được**

```
docker exec youdoo-open-webui sh -lc "python3 -c \"
import sqlite3, json
c = sqlite3.connect('/app/backend/data/webui.db')
fn, dat = c.execute('select filename, data from file order by created_at desc limit 1').fetchone()
d = json.loads(dat)
print(fn, d.get('status'), len(d.get('content') or ''))
\""
```

Kỳ vọng: `status` là `completed`, và độ dài lớn hơn hẳn con số **15** đo được
2026-09-09. Nếu vẫn `failed`, endpoint có thể vẫn đúng mà Open WebUI chưa trỏ
vào nó — kiểm lại Step 3 trước khi kết luận endpoint hỏng.

- [ ] **Step 5: Đưa số đo vào ghi chú thi hành của Task 4 rồi commit**

Nếu Task 4 đã commit trước, sửa bổ sung rồi commit thêm một lượt. Số của phép
nghiệm thu sống quan trọng hơn số của test, vì nó là thứ người dùng thật gặp.
