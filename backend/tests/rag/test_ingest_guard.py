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


def test_tep_duoi_la_khong_nem_va_khong_dem_la_skipped(tmp_path):
    """Đuôi lạ vẫn đi nhánh cũ, KHÔNG ném — chỉ tệp ĐƯỢC NHẬN mà ra rỗng
    mới là lỗi.

    Giá trị kỳ vọng chép từ hành vi THẬT của `_ingest_file` (`skipped: 0`),
    không phải từ trí nhớ: tệp đuôi lạ không được tính là "bỏ qua" vì nó chưa
    bao giờ là tài liệu để mà bỏ. Bản đầu của test này đoán `skipped: 1` và
    đỏ — code đúng, test sai."""
    f = tmp_path / "ghi_chu.txt"
    f.write_text("khong phai tai lieu duoc ho tro", encoding="utf-8")
    assert _ing._ingest_file(str(f), conn=None) == {
        "ingested": 0, "skipped": 0, "chunks": 0}
