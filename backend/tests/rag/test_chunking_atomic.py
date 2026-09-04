from src.rag.chunking import chunk_text_blocks


def test_block_khong_co_khoa_atomic_hanh_vi_nhu_cu():
    blocks = [
        {"text": "Điều 1. Tiêu đề", "heading_level": 4, "page": None},
        {"text": "Câu một. Câu hai.", "heading_level": None, "page": None},
    ]
    out = chunk_text_blocks(blocks, doc_id="d1", source_file="f.docx")
    assert len(out) == 1
    assert out[0]["chunk_text"] == "Câu một. Câu hai."


def test_block_atomic_luon_mot_chunk_rieng_du_ngan():
    blocks = [
        {"text": "Điều 1. Bảng thuế", "heading_level": 4, "page": None},
        {"text": "Mã: A | Mức: 10%", "heading_level": None, "page": 1, "atomic": True},
        {"text": "Mã: B | Mức: 5%", "heading_level": None, "page": 1, "atomic": True},
        {"text": "Ghi chú ngắn.", "heading_level": None, "page": None},
    ]
    out = chunk_text_blocks(blocks, doc_id="d1", source_file="f.pdf")
    texts = [c["chunk_text"] for c in out]
    assert "Mã: A | Mức: 10%" in texts
    assert "Mã: B | Mức: 5%" in texts
    # Hai hàng KHÔNG được gộp chung một chunk dù cộng dồn rất ngắn.
    assert not any("Mã: A" in t and "Mã: B" in t for t in texts)
    assert "Ghi chú ngắn." in texts


def test_block_atomic_khong_di_qua_split_section_text_du_vuot_ngan_sach(monkeypatch):
    from src.rag import chunking
    # Ép ngân sách token cực nhỏ để mô phỏng "hàng vượt CHUNK_SIZE_TOKENS".
    monkeypatch.setattr(chunking, "CHUNK_SIZE_TOKENS", 1)
    blocks = [{"text": "Mã: A | Mô tả: một câu khá dài để vượt ngân sách token nhỏ này",
              "heading_level": None, "page": 1, "atomic": True}]
    out = chunk_text_blocks(blocks, doc_id="d1", source_file="f.pdf")
    assert len(out) == 1
    assert out[0]["chunk_text"] == blocks[0]["text"]
