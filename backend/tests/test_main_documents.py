# backend/tests/test_main_documents.py
"""`PUT /v1/documents/process` — endpoint trích tài liệu.

Nói đúng hợp đồng `external_document_loader` của Open WebUI (đọc từ
`retrieval/loaders/external_document.py` của họ): body là bytes THÔ, tên tệp
đến qua header `X-Filename` đã urlencode, trả về list {page_content, metadata}.
"""
import logging
import os

import httpx
import pytest

from src import main as main_module
from src.ocr.engine import TesseractMissing
from src.rag import extract

TOKEN = "token-thu-cho-test"


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://test")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
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
async def test_rejects_an_empty_body_with_400():
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"",
                        headers=_headers("x.pdf"))
    assert r.status_code == 400


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
async def test_unsupported_format_from_the_extractor_returns_415(monkeypatch):
    # Khac voi test_rejects_an_unsupported_extension_with_415 (kiem tien-kiem
    # o main.py doc duoi tep): test nay kiem NHANH except UnsupportedFormat -
    # bo except do di thi test tien-kiem van xanh, chi test nay bat duoc.
    def _no(path, filename):
        raise extract.UnsupportedFormat("dinh dang khong nap thang duoc")

    monkeypatch.setattr(main_module, "extract_documents", _no)
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("x.pdf"))
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_tesseract_missing_returns_503(monkeypatch):
    # Nhanh nay khong co tien-kiem nao khac dung sau no (khac 415, khong co
    # gate o main.py) - thieu except nay se khong bi bat boi test nao khac.
    def _no(path, filename):
        raise TesseractMissing("khong tim thay binary tesseract")

    monkeypatch.setattr(main_module, "extract_documents", _no)
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("x.pdf"))
    assert r.status_code == 503


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
async def test_temp_file_cleanup_failure_is_logged(monkeypatch, caplog):
    """Gia lap that bai xoa tep tam bang monkeypatch, khong dua vao viec
    Windows tu choi os.unlink khi con tay cam mo.

    Ban truoc mo mot tay cam doc roi khong dong, dua vao Windows tu choi
    os.unlink - chi dung tren Windows: tren POSIX unlink thanh cong, khong
    log gi, assertion cuoi rot, va dong don dep cua chinh test con nem
    FileNotFoundError truoc ca do. Ban nay ep that bai truc tiep nen kiem
    duoc nhanh logger.warning tren moi he dieu hanh.

    Chi ep that bai o LAN GOI DAU (route tu don dep trong finally); lan goi
    thu hai - don dep that cua chinh test ben duoi - duoc di qua that, vi tep
    tam van con nguyen tren dia sau khi lan dau that bai.
    """
    seen = {}

    def _no(path, filename):
        seen["path"] = path
        raise RuntimeError("parser hong")

    real_unlink = os.unlink
    calls = {"n": 0}

    def _fail_once(path, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("gia lap: handle dang mo (Windows)")
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(main_module, "extract_documents", _no)
    monkeypatch.setattr(os, "unlink", _fail_once)
    with caplog.at_level(logging.WARNING):
        async with _client() as c:
            with pytest.raises(RuntimeError):
                await c.put("/v1/documents/process", content=b"abc",
                            headers=_headers("x.pdf"))
    assert seen["path"] in caplog.text
    os.unlink(seen["path"])  # don that su cho test - lan goi nay (thu 2) thanh cong that


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


@pytest.mark.asyncio
async def test_a_percent_encoded_newline_is_stripped_from_the_filename(monkeypatch):
    # Header goc khong the chua xuong dong, nhung "%0A" giai ma thanh "\n" -
    # nguoi goi da xac thuc co the gia mao dong log qua ten tep. Ky tu dieu
    # khien phai bi loai truoc khi ten tep di vao metadata.source.
    monkeypatch.setattr(
        main_module, "extract_documents",
        lambda p, f: [{"page_content": "x", "metadata": {"source": f}}])
    async with _client() as c:
        r = await c.put("/v1/documents/process", content=b"abc",
                        headers=_headers("bao%0Acao.pdf"))
    source = r.json()[0]["metadata"]["source"]
    assert "\n" not in source
    assert source == "baocao.pdf"
