from src.rag.ingest import _chunks_for


def test_chunks_for_pdf_tra_ve_warnings_tu_parse_pdf(monkeypatch, tmp_path):
    from src.rag import ingest

    def _fake_parse_pdf(path):
        return (
            [{"text": "Mã: A | Mức: 10%", "heading_level": None, "page": 1,
              "atomic": True}],
            [("trang 1, bảng", "cột đếm đứt đoạn tại: 2→4")],
        )

    monkeypatch.setattr(ingest, "parse_pdf", _fake_parse_pdf)
    chunks, warnings = _chunks_for("x.pdf", "text", "doc1", source_file="x.pdf")
    assert warnings == [("trang 1, bảng", "cột đếm đứt đoạn tại: 2→4")]
    assert len(chunks) == 1
