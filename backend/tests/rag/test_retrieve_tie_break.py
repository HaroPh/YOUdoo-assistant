# backend/tests/rag/test_retrieve_tie_break.py
"""Thứ hạng truy xuất phải TẤT ĐỊNH khi bảng bị tổ chức lại vật lý.

VÌ SAO TỒN TẠI. Cả ba chân đều `ORDER BY <điểm> ... LIMIT` mà không có khoá
phá hoà. Khi nhiều hàng cùng điểm, Postgres trả theo thứ tự VẬT LÝ của heap —
thứ tự này đổi sau mỗi `UPDATE` (MVCC ghi phiên bản mới nối đuôi), sau VACUUM
FULL, sau CLUSTER, sau khi nạp lại corpus.

Đo được, không phải giả thuyết:
  - bench ngoài 2026-09-23: 117/200 câu TVPL hoà `ts_rank` trong top-20 chân bỏ
    dấu; sau một lệnh `UPDATE visibility`, 21/1.000 câu đổi top-6 mà KHÔNG có
    dòng code nào đổi.
  - corpus production (3.901 chunk): chân bỏ dấu hoà điểm ở 10/24 truy vấn của
    bộ multiturn; 2/24 có nhóm hoà VẮT QUA biên `LIMIT 20`, tức hàng nào lọt vào
    pool cũng do thứ tự vật lý quyết định, không phải do điểm.
  - chân dense không miễn nhiễm: 5 nhóm embedding trùng nhau (16 chunk) trong
    corpus production — nội dung lặp lại thì embedding bằng nhau tuyệt đối.

`test_retrieve_visibility.test_unrestricted_thay_ca_hai` đã phải NÉ chuyện này
(khẳng định tập, không khẳng định thứ tự). Đây là chỗ sửa gốc.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.chunking import fold_vi
from src.rag.ingest import segment_vi
from src.rag.visibility import UNRESTRICTED

_DIM = 1024
_TEXT = "Quy trình nhập kho gồm bước kiểm đếm và bước đối chiếu chứng từ."


def _vec() -> str:
    """MỘT vector dùng cho mọi hàng — dense hoà điểm tuyệt đối."""
    return "[" + ",".join(["0"] * (_DIM - 1) + ["1"]) + "]"


# ─────────────────────────── phần unit (chạy trong CI) ───────────────────────

class _Cursor:
    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor()


def _sql_cua(chan) -> str:
    conn = _FakeConn()
    chan(conn)
    assert len(conn.calls) == 1, f"chân gọi {len(conn.calls)} câu SQL, mong 1"
    return " ".join(conn.calls[0][0].split())


@pytest.mark.parametrize("ten, chan", [
    ("dense", lambda c: rt._dense(c, [0.0] * _DIM, UNRESTRICTED)),
    ("sparse", lambda c: rt._sparse(c, segment_vi(_TEXT), UNRESTRICTED)),
    ("fold", lambda c: rt._lexical_fold(c, fold_vi(_TEXT), UNRESTRICTED)),
])
def test_moi_chan_co_khoa_pha_hoa_trong_order_by(ten, chan):
    """`ORDER BY` của mọi chân phải kết thúc bằng `c.id` — nếu không, hàng hoà
    điểm được xếp theo thứ tự vật lý."""
    sql = _sql_cua(chan)
    order_by = sql[sql.rindex("ORDER BY"):]
    assert "c.id" in order_by, f"chân {ten} thiếu khoá phá hoà: {order_by!r}"


# ────────────────────── phần integration (Postgres thật) ─────────────────────

def _nap_chunk_hoa_diem(conn, n: int) -> list[int]:
    """n chunk CÙNG nội dung ⇒ cùng `ts_rank` ở hai chân FTS và cùng khoảng
    cách ở chân dense. Trả danh sách id theo thứ tự chèn."""
    conn.execute("INSERT INTO rag_documents (doc_id, source_file, content_hash) "
                 "VALUES (%s, %s, %s)", ("d-hoa", "seed/hoa.docx", "d-hoa"))
    ids = []
    for i in range(n):
        row = conn.execute(
            "INSERT INTO rag_chunks (doc_id, source_file, chunk_text, visibility, "
            "embedding, ts_vector, chunk_text_fold) "
            "VALUES (%s, %s, %s, %s, %s::vector, to_tsvector('simple', %s), %s) "
            "RETURNING id",
            ("d-hoa", "seed/hoa.docx", _TEXT, "all", _vec(),
             segment_vi(_TEXT), fold_vi(_TEXT))).fetchone()
        ids.append(row[0])
    return ids


def _thu_tu_vat_ly(conn) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM rag_chunks ORDER BY ctid").fetchall()]


def _to_chuc_lai(conn, ids: list[int]) -> None:
    """Đảo thứ tự vật lý mà KHÔNG đổi id và KHÔNG đổi điểm: cập nhật từng hàng
    theo thứ tự ngược. Mỗi UPDATE ghi một phiên bản tuple mới nối vào cuối heap
    (MVCC), nên heap kết thúc theo đúng thứ tự cập nhật. Đây chính là thao tác
    đã làm 21/1.000 câu đổi top-6 trong bench ngoài (`UPDATE visibility`)."""
    for i in reversed(ids):
        conn.execute("UPDATE rag_chunks SET visibility = visibility WHERE id = %s", (i,))


_CHAN = {
    "dense": lambda c: rt._dense(c, [0.0] * (_DIM - 1) + [1.0], UNRESTRICTED),
    "sparse": lambda c: rt._sparse(c, segment_vi(_TEXT), UNRESTRICTED),
    "fold": lambda c: rt._lexical_fold(c, fold_vi(_TEXT), UNRESTRICTED),
}


@pytest.mark.integration
@pytest.mark.parametrize("ten", list(_CHAN))
def test_thu_hang_khong_doi_sau_khi_to_chuc_lai_bang(clean_tables, ten):
    """Nhiều hàng hoà điểm hơn TOP_N ⇒ phép đo bắt cả THỨ TỰ lẫn THÀNH PHẦN
    pool (hàng nào lọt qua LIMIT)."""
    conn = clean_tables
    ids = _nap_chunk_hoa_diem(conn, rt.TOP_N + 3)

    hang_truoc = _CHAN[ten](conn)
    diem = {float(r[-1]) for r in hang_truoc}
    assert len(diem) == 1, f"fixture sai: điểm KHÔNG hoà ({diem}) — test tự vô hiệu"
    assert len(hang_truoc) == rt.TOP_N, (
        f"mong LIMIT cắt đúng {rt.TOP_N} hàng, nhận {len(hang_truoc)} — test tự vô hiệu")

    vat_ly_truoc = _thu_tu_vat_ly(conn)
    _to_chuc_lai(conn, ids)
    vat_ly_sau = _thu_tu_vat_ly(conn)
    assert vat_ly_truoc != vat_ly_sau, (
        "thứ tự vật lý KHÔNG đổi sau khi tổ chức lại — test không đo gì nữa")

    hang_sau = _CHAN[ten](conn)
    assert [r[0] for r in hang_truoc] == [r[0] for r in hang_sau], (
        f"chân {ten}: thứ hạng đổi sau khi bảng bị tổ chức lại, "
        f"dù không có điểm nào thay đổi")


@pytest.mark.integration
def test_retrieve_dau_cuoi_tat_dinh_sau_khi_to_chuc_lai(clean_tables, monkeypatch):
    """Bất biến đầu-cuối: `retrieve()` trả cùng thứ tự chunk trước và sau khi
    bảng bị tổ chức lại. Đây là thứ eval thật sự đo (`recall@6`)."""
    conn = clean_tables
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * (_DIM - 1) + [1.0])
    ids = _nap_chunk_hoa_diem(conn, rt.TOP_N + 3)

    truoc = rt.retrieve(_TEXT, conn=conn, visibility=UNRESTRICTED)
    assert truoc.chunks, "retrieve() trả rỗng — test tự vô hiệu"

    vat_ly_truoc = _thu_tu_vat_ly(conn)
    _to_chuc_lai(conn, ids)
    assert _thu_tu_vat_ly(conn) != vat_ly_truoc, (
        "thứ tự vật lý KHÔNG đổi — test không đo gì nữa")

    sau = rt.retrieve(_TEXT, conn=conn, visibility=UNRESTRICTED)
    assert [c.chunk_id for c in truoc.chunks] == [c.chunk_id for c in sau.chunks]
