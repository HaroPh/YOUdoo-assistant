# backend/tests/rag/test_ingest_guard.py
"""Guard chống ingest chết im lặng — spec 2026-08-19-ingest-hygiene §5.

TÁCH KHỎI test_ingest.py có chủ đích: file đó đặt
`pytestmark = pytest.mark.integration` ở mức module, nên mọi test trong đó chỉ
chạy khi có Postgres. Hai test dưới đây KHÔNG cần Postgres, và một guard sinh
ra để chặn "hỏng im lặng" thì phải chạy ở suite MẶC ĐỊNH — bỏ nó vào file
integration là dựng lại đúng cái bẫy nó đi đóng (xem reranker: test model thật
nằm sau một biến môi trường không ai đặt, nên tính năng chết 6 tuần).
"""
import pytest

from src.rag import ingest as _ing


class _FakeConn:
    """Đủ cho nhánh kiểm content_hash: _ingest_file gọi conn.execute(...)
    .fetchone() TRƯỚC khi tới nhánh 0-chunk, nên truyền None sẽ ném
    AttributeError chứ không phải IngestError — test xanh/đỏ vì lý do sai."""

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None          # chưa từng ingest tệp này


def test_tep_duoc_nhan_nhung_ra_rong_thi_nem_loi(monkeypatch, tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(_ing, "_chunks_for", lambda *a, **k: [])
    with pytest.raises(_ing.IngestError) as e:
        _ing._ingest_file(str(f), conn=_FakeConn())
    assert "scan.pdf" in str(e.value)


def test_duoi_KHONG_PHAI_tai_lieu_van_bo_qua_im_lang(tmp_path):
    """Giữ nguyên lý lẽ của bản 2026-08-19: `.txt` chưa bao giờ là tài liệu
    để mà bỏ, nên nó KHÔNG phải `rejected`. Nếu tính nó là từ chối thì một
    tệp `.gitkeep` trong thư mục sẽ làm tiến trình thoát khác 0."""
    f = tmp_path / "ghi_chu.txt"
    f.write_text("khong phai tai lieu", encoding="utf-8")
    rep = _ing._ingest_file(str(f), conn=None)
    assert rep.ingested == 0 and rep.unchanged == 0
    assert rep.rejected == []
    assert rep.ok is True


def test_duoi_LA_TAI_LIEU_nhung_chua_nap_duoc_thi_bi_TU_CHOI(tmp_path, monkeypatch):
    """Đây là lỗi cả spec đi đóng: `.doc` là tài liệu thật, người dùng nghĩ
    đã nạp, nhưng hệ trả toàn 0 và không nói gì.

    Giả lập KHÔNG có LibreOffice để test không phụ thuộc máy chạy."""
    from src.rag import convert as _conv
    monkeypatch.setattr(_conv, "soffice_path", lambda: None)
    f = tmp_path / "quy_che.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0 fake OLE")
    rep = _ing._ingest_file(str(f), conn=None)
    assert rep.ok is False
    assert len(rep.rejected) == 1
    assert rep.rejected[0].path.endswith("quy_che.doc")
    assert "LibreOffice" in rep.rejected[0].reason


def test_moi_duoi_nap_duoc_deu_nam_trong_danh_sach_tai_lieu():
    """Chống trôi hai chiều: không thể thêm một đuôi vào `_EXT` mà quên khai
    nó là tài liệu. Danh sách gõ tay trôi khỏi sự thật là lớp lỗi đã tái phát
    nhiều lần trong dự án này."""
    assert set(_ing._EXT) <= _ing.DOCUMENT_EXT


def test_dinh_dang_cu_pho_bien_deu_duoc_coi_la_tai_lieu():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".pptx", ".xlsm"):
        assert ext in _ing.DOCUMENT_EXT, ext


class _RecordingConn(_FakeConn):
    """Như `_FakeConn` (chưa từng ingest tệp này) nhưng CÒN GHI LẠI tham số
    của mọi lệnh INSERT INTO rag_documents, để test đọc lại doc_id đã ghi."""

    def __init__(self):
        self.doc_inserts = []

    def execute(self, sql, params=None):
        if params is not None and "INSERT INTO rag_documents" in sql:
            self.doc_inserts.append(params)
        return self

    def transaction(self):
        import contextlib
        return contextlib.nullcontext()


def test_doc_chuyen_thanh_cong_thi_doc_id_theo_TEP_GOC(monkeypatch, tmp_path):
    """Vòng sửa 2 (Task 3): trọng tâm ý nghĩa của Step 4 là `doc_id` và
    `content_hash` tính theo TỆP GỐC, nội dung đọc từ bản đã chuyển đổi.
    Trước test này, KHÔNG tệp test nào chạy qua một lượt convert THÀNH CÔNG —
    nếu ai lỡ đổi `doc_id_source=path` thành `doc_id_source=converted` trong
    `_ingest_convertible`, toàn bộ suite vẫn xanh. Test này khoá đúng chỗ đó
    bằng cách đi qua đường thật `_ingest_file` → `_ingest_convertible` →
    `_ingest_known`, với `convert.soffice_path`/`_run_soffice` giả lập thay vì
    gọi `_ingest_known` trực tiếp (gọi trực tiếp sẽ bỏ qua đúng dòng nối cần
    khoá)."""
    from docx import Document
    from src.rag import convert as _conv

    goc = tmp_path / "quy_che.doc"
    goc.write_bytes(b"\xd0\xcf\x11\xe0 fake OLE")

    converted_dir = tmp_path / "converted"
    converted_dir.mkdir()
    converted_path = converted_dir / "quy_che.docx"
    doc = Document()
    doc.add_heading("Điều 1", level=1)
    doc.add_paragraph("Nội dung thử nghiệm.")
    doc.save(str(converted_path))

    monkeypatch.setenv(_conv.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(_conv, "soffice_path", lambda: "/gia/soffice")
    monkeypatch.setattr(_conv, "_run_soffice",
                        lambda soffice, path, target, outdir: str(converted_path))
    monkeypatch.setattr(_ing, "embed_texts", lambda texts: [[0.0, 0.0] for _ in texts])

    conn = _RecordingConn()
    rep = _ing._ingest_file(str(goc), conn)

    assert rep.ingested == 1
    assert len(conn.doc_inserts) == 1
    doc_id = conn.doc_inserts[0][0]
    assert doc_id.endswith("quy_che.doc"), doc_id
    assert not doc_id.endswith("quy_che.docx"), doc_id
