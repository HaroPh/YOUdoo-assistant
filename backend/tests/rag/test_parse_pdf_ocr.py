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
