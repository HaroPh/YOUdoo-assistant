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
    """Nhận diện chân theo dấu hiệu riêng của từng câu SQL.

    Lấy câu ĐẦU mỗi chân — bản bóng không lọc (spec 2026-09-21) chạy SAU và
    không được đè."""
    ra = {}
    for sql, params in conn.calls:
        if "<=>" in sql:
            ra.setdefault("dense", (sql, params))
        elif "ts_vector_fold" in sql:
            ra.setdefault("fold", (sql, params))
        elif "c.ts_vector @@" in sql:
            ra.setdefault("sparse", (sql, params))
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
    """Đường admin phải KHÔNG có mệnh đề lọc — để cổng dương so được với
    baseline cũ mà không tốn thêm chi phí lọc.

    Từ task hidden_classes (2026-09-21), `_COLS` thêm `c.visibility` ở CUỐI
    cho MỌI truy vấn (kể cả đường admin) — bản lọc và bản bóng phải cùng hình
    dạng cột để dùng chung `_fuse_legs`/`_hidden_at_rank_one`. Do đó chữ
    "visibility" giờ luôn có mặt trong SELECT; bất biến thật sự cần giữ là
    KHÔNG có mệnh đề lọc (`VIS_CLAUSE`), không phải "không có chữ visibility"."""
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility=UNRESTRICTED)
    chan = _sql_cua_ba_chan(conn)
    assert set(chan) == {"dense", "sparse", "fold"}
    for ten, (sql, _p) in chan.items():
        assert VIS_CLAUSE not in sql, ten


def test_tap_lop_di_vao_tham_so_da_sap_xep(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility={"commercial", "all"})
    for ten, (sql, params) in _sql_cua_ba_chan(conn).items():
        assert ["all", "commercial"] in [list(p) for p in params
                                         if isinstance(p, (list, tuple))], (ten, params)


def _sql_theo_chan(conn: _FakeConn) -> dict[str, list[tuple[str, tuple]]]:
    """Như `_sql_cua_ba_chan` nhưng GOM cả list thay vì ghi đè — cần khi một
    lượt `retrieve()` gọi cùng một chân nhiều lần (primary + mỗi aux).

    Dựng dict ĐỘNG, không gieo sẵn ba khoá (G2 vòng sửa 2): bản gieo sẵn cũ
    khiến `set(chan)` luôn đúng bằng `{"dense","sparse","fold"}` bất kể thực
    tế chạy gì — một chân im lặng hoàn toàn vẫn để lại khoá với list rỗng,
    nên `assert set(chan) == {...}` ở nơi gọi là một hằng đúng, không đo được
    hồi quy thật nào. Giống hệt `_sql_cua_ba_chan`: một chân không bắn câu SQL
    nào phải làm khoá đó BIẾN MẤT."""
    ra: dict[str, list[tuple[str, tuple]]] = {}
    for sql, params in conn.calls:
        if "<=>" in sql:
            ra.setdefault("dense", []).append((sql, params))
        elif "ts_vector_fold" in sql:
            ra.setdefault("fold", []).append((sql, params))
        elif "c.ts_vector @@" in sql:
            ra.setdefault("sparse", []).append((sql, params))
    return ra


def test_aux_queries_cung_bi_loc(khong_ra_ngoai):
    """Lượt hỏi trước (aux) đi qua cùng BA hàm — không có cửa sau.

    Đường thật: `rag_node` và `gather_docs` đều truyền `(prev,)` ở MỌI lượt
    hỏi tiếp theo, nên một lượt `retrieve()` với 1 aux sinh SÁU câu SQL — 3
    chân × (primary + aux). Trước bản sửa này, test chỉ soi cặp DENSE (nhận
    diện qua `"<=>"`) và bỏ sót sparse/fold: xoá `visibility` khỏi lời gọi
    aux của `_sparse`/`_lexical_fold` (retrieve.py:284, :287) mà suite vẫn
    xanh — xem xác nhận tay ở nhật ký thực thi task này."""
    conn = _FakeConn()
    rt.retrieve("câu sau", conn=conn, aux_queries=("câu trước",))
    chan = _sql_theo_chan(conn)
    # F4 (vòng sửa 1): khẳng định lại "đủ ba chân" — bản cũ `{ten: len(calls)}
    # == {...}` đồng thời khẳng định điều này; vòng lặp bên dưới một mình sẽ
    # ĐÚNG RỖNG nếu một chân biến mất hẳn khỏi đường aux.
    assert set(chan) == {"dense", "sparse", "fold"}
    # 4 câu mỗi chân: [primary lọc, aux lọc, primary bóng, aux bóng]. Nửa đầu
    # PHẢI có mệnh đề (không cửa sau cho aux); nửa sau là bản bóng không lọc.
    for ten, calls in chan.items():
        assert [VIS_CLAUSE in sql for sql, _params in calls] == [True, True, False, False], ten


# ─── Integration: DB thật ──────────────────────────────────────────────────

from src.rag.chunking import fold_vi
from src.rag.ingest import segment_vi

_DIM = 1024


def _vec(hot: int) -> str:
    """Vector đơn vị trục `hot`, dạng chuỗi cho %s::vector."""
    v = ["0"] * _DIM
    v[hot] = "1"
    return "[" + ",".join(v) + "]"


def _nap_hai_tai_lieu(conn):
    """1 chunk 'commercial' (trục 0) + 1 chunk 'all' (trục 1); cùng từ khoá
    'chiết khấu' để chân sparse và chân bỏ dấu đều có ứng viên."""
    rows = [("d-tm", "seed\\discount_policy.docx", "commercial", 0,
             "Chính sách chiết khấu: bậc 5%, cộng 2%, trần 15%."),
            ("d-all", "seed/policy.docx", "all", 1,
             "Chính sách hoàn hàng và chiết khấu chung trong 30 ngày.")]
    for doc_id, src, vis, hot, text in rows:
        conn.execute("INSERT INTO rag_documents (doc_id, source_file, content_hash) "
                     "VALUES (%s, %s, %s)", (doc_id, src, doc_id))
        conn.execute(
            "INSERT INTO rag_chunks (doc_id, source_file, chunk_text, visibility, "
            "embedding, ts_vector, chunk_text_fold) "
            "VALUES (%s, %s, %s, %s, %s::vector, to_tsvector('simple', %s), %s)",
            (doc_id, src, text, vis, _vec(hot), segment_vi(text), fold_vi(text)))


@pytest.mark.integration
def test_ba_chan_tren_db_that_khong_lo_commercial_cho_all(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    # Truy vấn "nhìn" giống chunk commercial nhất: trục 0 → dense xếp nó đầu
    monkeypatch.setattr(rt, "embed_query", lambda q: [1.0] + [0.0] * (_DIM - 1))
    q = "chiết khấu"
    chi_all = frozenset({"all"})

    dense = rt._dense(conn, [1.0] + [0.0] * (_DIM - 1), chi_all)
    sparse = rt._sparse(conn, segment_vi(q), chi_all)
    fold = rt._lexical_fold(conn, fold_vi(q), chi_all)
    for ten, rows in (("dense", dense), ("sparse", sparse), ("fold", fold)):
        assert rows, f"chân {ten} không có ứng viên — fixture sai, test tự vô hiệu"
        # cột 2 = source_file (xem _COLS)
        assert all("policy.docx" in r[2] and "discount" not in r[2] for r in rows), (ten, rows)

    ket_qua = rt.retrieve(q, conn=conn, visibility=chi_all)
    assert {c.source_file for c in ket_qua.chunks} == {"seed/policy.docx"}


@pytest.mark.integration
def test_unrestricted_thay_ca_hai(clean_tables, monkeypatch):
    """Khẳng định TẬP, không khẳng định thứ tự: hai chunk hoà điểm ts_rank ở
    chân sparse/fold, RRF có thể xếp 'all' trước — thứ tự không phải điều
    test này đo."""
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: [1.0] + [0.0] * (_DIM - 1))
    ket_qua = rt.retrieve("chiết khấu", conn=conn, visibility=UNRESTRICTED)
    assert {c.source_file for c in ket_qua.chunks} == {"seed\\discount_policy.docx",
                                                        "seed/policy.docx"}
