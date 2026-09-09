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
