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
