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
    """Tren Windows, mot handle con mo lam os.unlink nem PermissionError.

    Xac nhan thuc nghiem truoc khi viet test nay (mo mot tay cam doc roi goi
    os.unlink cung tep tren may nay): unlink NEM that. Route phai LOG that
    bai do, khong duoc nuot lang le nhu truoc - nuot lang le dung la loai loi
    "chi lo ra sau hang nghin request" ma docstring cua test ben tren canh bao.
    """
    seen = {}

    def _leaves_a_handle_open(path, filename):
        seen["path"] = path
        seen["handle"] = open(path, "rb")  # KHONG dong -> unlink se that bai
        raise RuntimeError("parser hong")

    monkeypatch.setattr(main_module, "extract_documents", _leaves_a_handle_open)
    with caplog.at_level(logging.WARNING):
        async with _client() as c:
            with pytest.raises(RuntimeError):
                await c.put("/v1/documents/process", content=b"abc",
                            headers=_headers("x.pdf"))
    seen["handle"].close()
    os.unlink(seen["path"])  # don that su cho test - route khong xoa duoc luc nay
    assert seen["path"] in caplog.text


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
