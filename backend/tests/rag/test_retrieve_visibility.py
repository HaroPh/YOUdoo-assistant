# backend/tests/rag/test_retrieve_visibility.py
"""Lọc visibility ở ĐÚNG ba chân, trước LIMIT, và fail-closed (spec §4).

Phần unit: conn giả ghi lại SQL + tham số — kiểm HÌNH DẠNG câu lệnh, cùng
cách test_sparse_van_chet.py. Phần integration ở dưới (Task 4) chạy DB thật.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.visibility import UNRESTRICTED

VIS_CLAUSE = "c.visibility = ANY(%s)"


class _Cursor:
    def fetchall(self):
        return []


class _FakeConn:
    """Ghi lại mọi (sql, params); mọi chân trả rỗng nên rerank không chạy."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor()


@pytest.fixture
def khong_ra_ngoai(monkeypatch):
    """Chặn embed (Ollama) và giữ chân bỏ dấu BẬT để đủ ba chân chạy."""
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")


def _sql_cua_ba_chan(conn: _FakeConn) -> dict[str, tuple[str, tuple]]:
    """Nhận diện chân theo dấu hiệu riêng của từng câu SQL."""
    ra = {}
    for sql, params in conn.calls:
        if "<=>" in sql:
            ra["dense"] = (sql, params)
        elif "ts_vector_fold" in sql:
            ra["fold"] = (sql, params)
        elif "c.ts_vector @@" in sql:
            ra["sparse"] = (sql, params)
    return ra


def test_khong_truyen_thi_loc_all_tren_ca_ba_chan(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất giá trị gia tăng", conn=conn)
    chan = _sql_cua_ba_chan(conn)
    assert set(chan) == {"dense", "sparse", "fold"}, chan.keys()
    for ten, (sql, params) in chan.items():
        assert VIS_CLAUSE in sql, ten
        assert ["all"] in [list(p) for p in params if isinstance(p, (list, tuple))], (ten, params)
        # Lọc phải đứng TRƯỚC ORDER BY/LIMIT — lọc sau pool là rò qua total_candidates
        assert sql.index(VIS_CLAUSE) < sql.index("ORDER BY"), ten


def test_truyen_None_cung_fail_closed(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility=None)
    for ten, (sql, _p) in _sql_cua_ba_chan(conn).items():
        assert VIS_CLAUSE in sql, ten


def test_unrestricted_thi_sql_khong_co_visibility(khong_ra_ngoai):
    """Đường admin phải là ĐÚNG SQL trước 19b — để cổng dương so được với
    baseline cũ mà không có mệnh đề thừa."""
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility=UNRESTRICTED)
    chan = _sql_cua_ba_chan(conn)
    assert set(chan) == {"dense", "sparse", "fold"}
    for ten, (sql, _p) in chan.items():
        assert "visibility" not in sql, ten


def test_tap_lop_di_vao_tham_so_da_sap_xep(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility={"commercial", "all"})
    for ten, (sql, params) in _sql_cua_ba_chan(conn).items():
        assert ["all", "commercial"] in [list(p) for p in params
                                         if isinstance(p, (list, tuple))], (ten, params)


def test_aux_queries_cung_bi_loc(khong_ra_ngoai):
    """Lượt hỏi trước (aux) đi qua cùng ba hàm — không có cửa sau."""
    conn = _FakeConn()
    rt.retrieve("câu sau", conn=conn, aux_queries=("câu trước",))
    dense_calls = [sql for sql, _ in conn.calls if "<=>" in sql]
    assert len(dense_calls) == 2
    assert all(VIS_CLAUSE in s for s in dense_calls)
