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
    # single-doc path không inject source_kind/ocr_conf; page-grouped path có.
    # Nếu group_by_page lật thành True cho docx, test này sẽ fail.
    assert "source_kind" not in docs[0]["metadata"]
    assert "ocr_conf" not in docs[0]["metadata"]


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


def test_xlsx_whitespace_only_raises_same_as_pdf(monkeypatch):
    # xlsx là cửa khác của bẫy PDF: một ô chỉ chứa tab sẽ lọt qua .strip(" |")
    # nhưng phải bị bắt bởi kiểm tra rỗng như PDF. Đây là xlsx_twin của
    # whitespace trap.
    monkeypatch.setattr(extract, "parse_xlsx", lambda p: ([{
        "sheet": "sheet1",
        "columns": ["col1"],
        "rows": [["\t"], [None]],
    }], []))
    with pytest.raises(extract.EmptyExtraction):
        extract.extract_documents("/x.xlsx", "x.xlsx")


def test_xlsx_with_multiple_sheets_and_blank_rows(monkeypatch):
    # Mỗi sheet trở thành một document, mang sheet name trong metadata.
    # Hàng toàn trắng không xuất hiện trong page_content.
    monkeypatch.setattr(extract, "parse_xlsx", lambda p: ([
        {
            "sheet": "sheet1",
            "columns": ["name", "age"],
            "rows": [["Alice", "30"], ["", ""], ["Bob", "25"]],
        },
        {
            "sheet": "sheet2",
            "columns": ["id", "value"],
            "rows": [["S2-1", "100"]],
        },
    ], []))
    docs = extract.extract_documents("/x.xlsx", "x.xlsx")
    assert len(docs) == 2
    assert docs[0]["metadata"]["sheet"] == "sheet1"
    assert docs[1]["metadata"]["sheet"] == "sheet2"
    content_lines = docs[0]["page_content"].split("\n")
    # Hàng toàn trắng ["", ""] bị lọc, nên chỉ có 3 hàng (header + 2 data rows)
    assert len(content_lines) == 3
    assert "name | age" in content_lines[0]
    assert "Alice | 30" in content_lines[1]
    assert "Bob | 25" in content_lines[2]


def test_pptx_groups_by_slide_number(monkeypatch):
    # pptx nhóm theo trang/slide, giống PDF nhóm theo trang.
    monkeypatch.setattr(extract, "parse_pptx", lambda p: [
        {"text": "slide 1 text", "heading_level": None, "page": 1},
        {"text": "slide 2 text", "heading_level": None, "page": 2},
    ])
    docs = extract.extract_documents("/x.pptx", "x.pptx")
    assert [d["metadata"]["page"] for d in docs] == [1, 2]
    assert docs[0]["page_content"] == "slide 1 text"
    assert docs[1]["page_content"] == "slide 2 text"


def test_source_kind_cua_trang_la_bac_XAU_NHAT_khong_phai_ocr_hay_text(monkeypatch):
    """Trước 2026-09-11: `"ocr" if any(...=="ocr") else "text"` — một trang toàn
    hàng VLM chưa kiểm mang nhãn "text", bậc tin cậy CAO NHẤT. Nay gộp theo
    bậc xấu nhất, cùng quy tắc với chunking."""
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([
        {"text": "TAI SAN", "heading_level": 1, "page": 1, "source_kind": "vision_unverified", "ocr_conf": None},
        {"text": "Mã số: 50 | Số đầu năm: 69.862.687.223", "heading_level": None, "page": 1,
         "source_kind": "vision_verified", "ocr_conf": None},
        {"text": "dong ocr", "heading_level": None, "page": 2, "source_kind": "ocr", "ocr_conf": 0.7},
        {"text": "dong ocr 2", "heading_level": None, "page": 2, "source_kind": "ocr", "ocr_conf": 0.9},
        {"text": "dong text", "heading_level": None, "page": 3},
    ], []))
    docs = extract.extract_documents("/x.pdf", "x.pdf")
    kinds = [(d["metadata"]["page"], d["metadata"]["source_kind"], d["metadata"]["ocr_conf"]) for d in docs]
    assert kinds == [(1, "vision_unverified", None), (2, "ocr", 0.7), (3, "text", None)]


# ─── dấu xuất xứ trong TEXT (2026-09-12) ──────────────────────────────────────
# Đã xác minh trong container: Open WebUI `get_source_context`
# (utils/middleware.py:807) dựng prompt CHỈ từ `doc` body + id/name/resource-*,
# BỎ mọi metadata khác. Nên `metadata.source_kind` không bao giờ tới model trên
# đường tệp đính kèm, và body là kênh xuất xứ duy nhất còn sống.
def test_hang_chua_kiem_co_so_mang_tien_to_trong_page_content(monkeypatch):
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([
        {"text": "TAI SAN", "heading_level": 1, "page": 7,
         "source_kind": "vision_unverified"},
        {"text": "Mã số: 52 | Năm trước: 358.487.382", "heading_level": None, "page": 7,
         "source_kind": "vision_unverified", "unverified_money": True},
        {"text": "Mã số: 50 | Năm nay: 79.611.117.804", "heading_level": None, "page": 7,
         "source_kind": "vision_verified"},
        {"text": "dong ocr", "heading_level": None, "page": 8, "source_kind": "ocr"},
    ], []))
    docs = extract.extract_documents("/x.pdf", "x.pdf")
    tr7 = docs[0]["page_content"].split("\n")
    assert tr7[0] == "TAI SAN", "hàng nhãn không có số -> không gắn dấu"
    assert tr7[1] == f"{extract.UNVERIFIED_PREFIX}Mã số: 52 | Năm trước: 358.487.382"
    assert tr7[2] == "Mã số: 50 | Năm nay: 79.611.117.804", "hàng đã kiểm -> không gắn"
    assert docs[1]["page_content"] == "dong ocr", "bậc ocr KHÔNG gắn dấu — xem bảng lý do"
    # Dấu chỉ vào body; metadata vẫn giữ nguyên cho người gọi nào đọc được nó.
    assert docs[0]["metadata"]["source_kind"] == "vision_unverified"


def test_tien_to_tu_giai_thich_va_khong_lap_khi_da_co(monkeypatch):
    """Dấu phải tự nói nghĩa (không có dòng chú giải đầu trang — nó chết ở khối
    thứ hai khi Open WebUI cắt 1000 ký tự), và không cộng dồn nếu block đã mang."""
    assert "CHƯA KIỂM" in extract.UNVERIFIED_PREFIX
    monkeypatch.setattr(extract, "parse_pdf", lambda p: ([
        {"text": f"{extract.UNVERIFIED_PREFIX}Mã số: 52 | Năm trước: 358.487.382",
         "heading_level": None, "page": 7, "source_kind": "vision_unverified",
         "unverified_money": True},
    ], []))
    docs = extract.extract_documents("/x.pdf", "x.pdf")
    assert docs[0]["page_content"].count("CHƯA KIỂM") == 1
