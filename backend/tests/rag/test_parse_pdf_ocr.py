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


class _FakeBang:
    """Một bảng giả tối thiểu: chỉ đủ trường `parse_pdf` đọc tới khi bảng
    RỖNG hoàn toàn (không hàng nào) — đúng thực tế của trang đọc-bằng-ảnh,
    nơi không có đối tượng chữ (vector) nào để `bang.extract()` bám vào."""
    bbox = (0, 0, 100, 100)

    def extract(self):
        return []


class _FakeWithinBbox:
    def extract_text(self):
        return ""

    def find_tables(self, table_settings=None):
        return []


class _FakePlumberPage:
    width = 100
    height = 100

    def __init__(self, bangs=None):
        self._bangs = bangs or []

    def find_tables(self, table_settings=None):
        return self._bangs

    def within_bbox(self, bbox, relative=False):
        return _FakeWithinBbox()


class _FakePlumberPDF:
    def __init__(self, n, bangs_theo_trang=None):
        bangs_theo_trang = bangs_theo_trang or {}
        self.pages = [_FakePlumberPage(bangs_theo_trang.get(i + 1))
                     for i in range(n)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _doc_gia(text, conf=90.0):
    r = Region(kind="text", text=text, mean_conf=conf, bbox=(0, 0, 100, 100))
    return PageRead(page=1, regions=[r], mean_conf=conf, tu_dem=False)


def _dung_canh(monkeypatch, pypdf_pages, ocr_text="Điều 1. Chữ đọc từ ảnh.",
               conf=90.0, bangs_theo_trang=None):
    import pypdf
    import pdfplumber
    from src.rag import parse
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: _FakeReader(pypdf_pages))
    monkeypatch.setattr(pdfplumber, "open",
                        lambda path: _FakePlumberPDF(len(pypdf_pages),
                                                     bangs_theo_trang))
    monkeypatch.setattr(parse, "read_page",
                        lambda path, pageno, **kw: _doc_gia(ocr_text, conf))
    return parse


def test_trang_ocr_co_luoi_sinh_block_atomic_theo_HANG(monkeypatch):
    """Trang đọc-từ-ảnh có lưới >1 cột phải sinh MỖI HÀNG một block atomic,
    đi đúng đường của B4 — không có đường code thứ hai phải giữ đồng bộ."""
    grid = [["Chi tieu", "Ma so", "So tien"],
            ["Tien mat", "111", "1.000"],
            ["Tien gui", "112", "2.000"]]
    parse = _dung_canh(monkeypatch, [""])          # 1 trang RỖNG -> đi qua OCR
    monkeypatch.setattr(parse, "read_page", lambda path, pageno, **kw: PageRead(
        page=1, mean_conf=90.0, tu_dem=False,
        regions=[Region(kind="text", mean_conf=90.0, bbox=(0, 0, 100, 100),
                        text="\n".join(" ".join(h) for h in grid),
                        words=[], grid=grid)]))

    blocks, warnings = parse.parse_pdf("x.pdf")
    atomic = [b for b in blocks if b.get("atomic")]
    assert len(atomic) == 2, "phai co 2 hang than, moi hang mot block atomic"
    assert all(b["source_kind"] == "ocr" for b in atomic)
    assert all(b["ocr_conf"] == 90.0 for b in atomic)
    assert "Ma so: 111" in atomic[0]["text"]
    assert warnings == []


def test_dung_luoi_HONG_thi_bao_co_ten_va_van_giu_du_noi_dung(monkeypatch):
    """Spec §9: mất cấu trúc còn hơn mất nội dung — nhưng KHÔNG được im lặng."""
    parse = _dung_canh(monkeypatch, [""])
    monkeypatch.setattr(parse, "read_page", lambda path, pageno, **kw: PageRead(
        page=1, mean_conf=90.0, tu_dem=False,
        regions=[Region(kind="text", mean_conf=90.0, bbox=(0, 0, 100, 100),
                        text="Điều 1. Chữ đọc từ ảnh.", words=[], grid=[],
                        grid_error="ValueError: hong that")]))

    blocks, warnings = parse.parse_pdf("x.pdf")
    # noi dung phai con nguyen — mat cau truc KHONG duoc keo theo mat chu
    assert [b["text"] for b in blocks] == ["Điều 1. Chữ đọc từ ảnh."]
    # va phai co canh bao CO TEN, khong duoc nuot
    assert len(warnings) == 1
    assert "hong that" in warnings[0][1]


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


def test_trang_CO_MOT_KY_TU_RAT_NGAN_thi_KHONG_goi_OCR(monkeypatch):
    # Finding review toàn nhánh A5: ràng buộc mạnh nhất của kế hoạch là CẤM
    # đặt ngưỡng "dưới N ký tự" — "rỗng" nghĩa là danh sách dòng rỗng HẲN sau
    # strip, không phải "ít chữ". Test khác trong tệp này đều dùng câu 19 ký
    # tự nên vẫn xanh nếu ai đó lén thêm `if len(...) < 10: goi_OCR()`. Trang
    # ở đây chỉ có MỘT token rất ngắn (số trang "3") — phải đi qua NHƯ TRANG
    # CÓ CHỮ, không được coi là "gần rỗng" rồi rơi vào OCR.
    import pypdf
    import pdfplumber
    from src.rag import parse
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: _FakeReader(["3"]))
    monkeypatch.setattr(pdfplumber, "open", lambda path: _FakePlumberPDF(1))

    def _no(*a, **kw):
        raise AssertionError("KHÔNG được gọi OCR cho trang có lớp text, dù rất ngắn")

    monkeypatch.setattr(parse, "read_page", _no)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert [b["text"] for b in blocks] == ["3"]
    assert "source_kind" not in blocks[0]
    assert warnings == []


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


def test_LOI_DOC_ANH_THUONG_thi_bao_co_ten_chu_khong_lam_vo_ca_luot_nap(monkeypatch):
    """Đường hỏng thứ hai của `_doc_trang_bang_anh`: KHÔNG phải thiếu binary
    (đã có test riêng ở trên), mà bản thân việc rasterise/đọc ảnh ném lỗi
    (PDF vỡ, ảnh không rasterise được, v.v.) — nhánh `except Exception as e`.
    """
    parse = _dung_canh(monkeypatch, [""])

    def _hong(path, pageno, **kw):
        raise RuntimeError("khong rasterise duoc trang")

    monkeypatch.setattr(parse, "read_page", _hong)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert blocks == [], "một trang hỏng không được sinh block rác"
    assert len(warnings) == 1
    where, reason = warnings[0]
    assert "trang 1" in where
    assert "RuntimeError" in reason, "cảnh báo phải gọi tên LOẠI lỗi, không nuốt"


def test_trang_DA_OCR_co_bang_VA_co_chu_vector_thi_KHONG_dan_nhan_ocr(monkeypatch):
    """B4 (review toàn nhánh): khi trang vừa được OCR vừa bị `find_tables()`
    báo có bảng, `dai_lines` dựng lại từ
    `plumber_page.within_bbox(...).extract_text()` — LỚP VECTOR, không phải
    OCR. Trước bản vá này, `pageno` vẫn còn trong `ocr_pages` nên các dòng
    vector đó bị dán `source_kind="ocr"` cùng `mean_conf` của một lượt OCR
    KHÁC — nhãn tin cậy nói dối. Sau bản vá, `ocr_pages.pop(pageno, None)`
    chạy ngay khi cảnh báo phát ra, nên các dòng vector này phải ra
    KHÔNG mang `source_kind` (giống trang chữ bình thường)."""
    import pypdf
    import pdfplumber
    from src.rag import parse

    class _WithinBboxCoChu:
        def extract_text(self):
            return "Dòng chữ vector, không phải OCR."

        def find_tables(self, table_settings=None):
            return []

    class _BangGiuaTrang:
        # bbox KHÔNG phủ hết trang (20..80 trong tổng chiều cao 100), để lại
        # dải trên/dưới cho `parse_pdf` dựng `dai_lines` từ lớp vector — nếu
        # bảng phủ hết trang thì không còn dải nào gọi `within_bbox`, và test
        # này không quan sát được gì.
        bbox = (0, 20, 100, 80)

        def extract(self):
            return []

    class _PlumberPageCoBang:
        width = 100
        height = 100

        def __init__(self):
            self._bangs = [_BangGiuaTrang()]

        def find_tables(self, table_settings=None):
            return self._bangs

        def within_bbox(self, bbox, relative=False):
            return _WithinBboxCoChu()

    class _PlumberPDFCoBang:
        def __init__(self):
            self.pages = [_PlumberPageCoBang()]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pypdf, "PdfReader", lambda path: _FakeReader([""]))
    monkeypatch.setattr(pdfplumber, "open", lambda path: _PlumberPDFCoBang())
    monkeypatch.setattr(parse, "read_page",
                        lambda path, pageno, **kw: _doc_gia("Điều 1. Chữ đọc từ ảnh.", 90.0))

    blocks, warnings = parse.parse_pdf("x.pdf")
    assert len(warnings) == 1 and "bảng" in warnings[0][1].lower()
    text_blocks = [b for b in blocks if b["text"] == "Dòng chữ vector, không phải OCR."]
    assert text_blocks, "dòng vector phải vẫn được nạp"
    assert "source_kind" not in text_blocks[0], (
        "dòng đọc từ lớp VECTOR không được mang nhãn xuất xứ 'ocr' của một "
        "lượt đọc ảnh khác")


def test_trang_DA_OCR_ma_lai_co_bang_thi_canh_bao_khong_im_lang(monkeypatch):
    """Finding 2 (review Task 4): trang không có lớp text đã đọc được chữ
    bằng ảnh, nhưng `find_tables()` vẫn báo trang có bảng (khung vẽ sẵn/lưới
    vector chồng lên nội dung scan). Nhánh dựng dải văn xuôi cho trang có
    bảng dùng `plumber_page.within_bbox(...).extract_text()` — nguồn HOÀN
    TOÀN KHÁC OCR — nên chữ đọc bằng ảnh bị bỏ đi. Bậc 1 CHƯA dựng bảng từ
    ảnh (việc của bậc 2); ở đây chỉ cần không im lặng."""
    parse = _dung_canh(monkeypatch, [""], bangs_theo_trang={1: [_FakeBang()]})
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert blocks == [], ("không có lớp vector để dựng lại bảng/dải văn xuôi "
                          "— trang phải RỖNG BLOCK, không được bịa nội dung")
    assert len(warnings) == 1
    where, reason = warnings[0]
    assert where == "trang 1"
    assert "bảng" in reason.lower() and "ảnh" in reason.lower()


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
