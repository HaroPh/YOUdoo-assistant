# backend/tests/rag/test_retrieve_hidden.py
"""Tín hiệu `hidden_classes` (spec 2026-09-21 §3): bản bóng KHÔNG lọc chạy khi
vai bị giới hạn, luật hạng-1, và chunk bị giấu không bao giờ rời retrieve().

Phần unit: conn giả HAI POOL — trả `visible` khi SQL có mệnh đề lọc, `all_`
khi không. Mọi chân trả cùng danh sách nên thứ tự RRF = thứ tự danh sách:
phần tử đầu của `all_` chính là hạng-1 của bản bóng. Phần integration ở dưới
(Task 5) chạy DB thật.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.visibility import UNRESTRICTED

VIS_CLAUSE = "c.visibility = ANY(%s)"
CHI_ALL = frozenset({"all"})


def _row(id_, source_file, vis, score, text="x"):
    """Hàng khớp `_COLS` + score: (id, doc_id, source_file, doc_title, section_path,
    page, sheet, row_range, chunk_text, effective_date, source_kind, visibility, score)."""
    return (id_, f"d{id_}", source_file, "T", None, None, None, None,
            text, None, "text", vis, score)


class _Cur:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _ConnHaiPool:
    def __init__(self, visible, all_):
        self.visible, self.all_ = visible, all_
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cur(self.visible if VIS_CLAUSE in sql else self.all_)


@pytest.fixture
def khong_ra_ngoai(monkeypatch):
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")


TM = _row(1, "seed\\discount_policy.docx", "commercial", 0.9)
ALL = _row(2, "seed/policy.docx", "all", 0.5)


def test_bi_gioi_han_va_hang_1_bi_giau_thi_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    # BẤT BIẾN AN TOÀN: chunk trả về vẫn là bản đã lọc — không có hàng thương mại
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]


def test_bi_gioi_han_nhung_hang_1_thay_duoc_thi_khong_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[ALL, TM])
    r = rt.retrieve("hoàn hàng", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()


def test_ban_bong_rong_thi_khong_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[], all_=[])
    r = rt.retrieve("không có gì", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.is_empty()


def test_unrestricted_khong_chay_ban_bong(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=UNRESTRICTED)
    assert r.hidden_classes == frozenset()
    assert len(conn.calls) == 3, [s[:40] for s, _ in conn.calls]   # 3 chân, KHÔNG bóng
    assert not any(VIS_CLAUSE in s for s, _ in conn.calls)


def test_bi_gioi_han_chay_dung_hai_luot_ba_chan(khong_ra_ngoai):
    """Lượt LỌC trước, lượt BÓNG sau — 6 câu; nửa đầu có mệnh đề, nửa sau không.
    Thứ tự là hợp đồng: test hình dạng SQL của 19b nhận diện chân bằng câu ĐẦU."""
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    co_loc = [VIS_CLAUSE in s for s, _ in conn.calls]
    assert co_loc == [True, True, True, False, False, False], co_loc


def test_khong_truyen_visibility_van_chay_bong_vi_fail_closed(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn)          # None → {'all'} → bị giới hạn
    assert r.hidden_classes == frozenset({"commercial"})


def test_hidden_at_rank_one_don_vi():
    fused = {1: {"row": TM, "rrf": 0.03}, 2: {"row": ALL, "rrf": 0.02}}
    assert rt._hidden_at_rank_one(fused, CHI_ALL) == frozenset({"commercial"})
    assert rt._hidden_at_rank_one({2: {"row": ALL, "rrf": 0.02}}, CHI_ALL) == frozenset()
    assert rt._hidden_at_rank_one({}, CHI_ALL) == frozenset()
    assert rt._hidden_at_rank_one(fused, frozenset({"all", "commercial"})) == frozenset()
