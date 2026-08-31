# backend/tests/rag/test_ingest_guard.py
"""Guard chống ingest chết im lặng — spec 2026-08-19-ingest-hygiene §5.

TÁCH KHỎI test_ingest.py có chủ đích: file đó đặt
`pytestmark = pytest.mark.integration` ở mức module, nên mọi test trong đó chỉ
chạy khi có Postgres. Hai test dưới đây KHÔNG cần Postgres, và một guard sinh
ra để chặn "hỏng im lặng" thì phải chạy ở suite MẶC ĐỊNH — bỏ nó vào file
integration là dựng lại đúng cái bẫy nó đi đóng (xem reranker: test model thật
nằm sau một biến môi trường không ai đặt, nên tính năng chết 6 tuần).
"""
import os

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
    nhiều lần trong dự án này.

    Bất biến này CHỈ có nghĩa vì `DOCUMENT_EXT` là một literal ĐỘC LẬP. Bản
    trước khai `DOCUMENT_EXT = frozenset(_EXT) | {...}`, nên phép khẳng định
    dưới đây đúng theo định nghĩa và không gác gì: thêm `".epub": "text"` vào
    `_EXT` thì test vẫn xanh (đo 2026-08-31). Nếu ai đó gộp hai danh sách lại,
    cổng này chết âm thầm lần nữa."""
    assert set(_ing._EXT) <= _ing.DOCUMENT_EXT


def test_dinh_dang_cu_pho_bien_deu_duoc_coi_la_tai_lieu():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".pptx", ".xlsm"):
        assert ext in _ing.DOCUMENT_EXT, ext


class _RecordingConn(_FakeConn):
    """Như `_FakeConn` (chưa từng ingest tệp này) nhưng CÒN GHI LẠI tham số
    của mọi lệnh INSERT INTO rag_documents VÀ rag_chunks, để test đọc lại
    đúng những gì sẽ nằm trong DB."""

    def __init__(self):
        self.doc_inserts = []
        self.chunk_inserts = []

    def execute(self, sql, params=None):
        if params is not None and "INSERT INTO rag_documents" in sql:
            self.doc_inserts.append(params)
        if params is not None and "INSERT INTO rag_chunks" in sql:
            self.chunk_inserts.append(params)
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


def test_doc_chuyen_thanh_cong_thi_source_file_theo_TEP_GOC(monkeypatch, tmp_path):
    """C1 (review toàn nhánh 2026-08-31): `source_file` phải là TỆP GỐC, không
    phải bản đã chuyển đổi nằm trong thư mục cache tạm.

    Vì sao nghiêm trọng hơn một nhãn hiển thị sai: tài liệu KHÔNG CÓ HEADING
    (đúng ca `quyche_taichinh.doc` thật — 51/51 block heading_level=None) thì
    chunking.py:52 lùi `doc_title` về `source_file`, :61 lùi `crumb` về
    `doc_title`, rồi `index_text()` nối crumb vào chuỗi đem đi EMBED và vào
    `ts_vector`. Đường dẫn cache chứa content_hash nên nó ĐỔI theo nội dung và
    KHÁC giữa các máy, lại GIỐNG HỆT ở mọi chunk nên làm giảm khả năng phân
    biệt giữa chính các chunk đó.

    Docx dựng ở đây CỐ Ý không có heading nào — đó là điều kiện kích hoạt
    đường lùi. Có heading thì lỗi ẩn đi và test không đo được gì."""
    from docx import Document
    from src.rag import convert as _conv

    goc = tmp_path / "quy_che.doc"
    goc.write_bytes(b"\xd0\xcf\x11\xe0 fake OLE")

    # Thư mục cache mang đúng tên thật để phép khẳng định "không lẫn đường dẫn
    # cache" đo được thứ nó tuyên bố đo.
    monkeypatch.setenv(_conv.CONVERT_CACHE_ENV, str(tmp_path / "youdoo_convert"))
    monkeypatch.setattr(_conv, "soffice_path", lambda: "/gia/soffice")

    def _fake_run(soffice, path, target, outdir):
        out = os.path.join(outdir, "quy_che.docx")
        d = Document()
        d.add_paragraph("CHUONG I: QUY DINH CHUNG")   # paragraph thường, KHÔNG heading
        d.add_paragraph("Dieu 1: Pham vi dieu chinh cua quy che nay.")
        d.save(out)
        return out
    monkeypatch.setattr(_conv, "_run_soffice", _fake_run)
    monkeypatch.setattr(_ing, "embed_texts", lambda texts: [[0.0, 0.0] for _ in texts])

    conn = _RecordingConn()
    rep = _ing._ingest_file(str(goc), conn)

    assert rep.ingested == 1
    assert conn.chunk_inserts, "không ghi chunk nào — test không đo được gì"

    # Thứ tự cột của INSERT INTO rag_chunks: doc_id, source_file, doc_title,
    # section_path, ...
    for params in conn.chunk_inserts:
        source_file, doc_title, section_path = params[1], params[2], params[3]
        assert source_file.endswith(".doc"), source_file
        assert not source_file.endswith(".docx"), source_file
        assert "youdoo_convert" not in (section_path or ""), section_path
        assert "youdoo_convert" not in (doc_title or ""), doc_title

    # rag_documents cũng phải mang tệp gốc.
    assert conn.doc_inserts[0][1].endswith(".doc")
    assert not conn.doc_inserts[0][1].endswith(".docx")
