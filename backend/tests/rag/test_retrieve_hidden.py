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


def test_hidden_at_rank_one_voi_sentinel_thi_no_to():
    """Cổng hợp đồng thường trực (G1-c vòng sửa 2): biến tiền điều kiện F5
    (docstring) thành một cổng CI thật. `visibility` PHẢI là frozenset đã
    resolve — gọi với sentinel `UNRESTRICTED` phải NỔ `TypeError`, không được
    lặng lẽ trả `frozenset()`. `fused` phải KHÁC RỖNG, nếu không hàm trả sớm
    ở nhánh `if not fused` trước khi chạm `cls in visibility` — test sẽ
    đúng-rỗng (vacuous)."""
    fused = {1: {"row": TM, "rrf": 0.03}}
    with pytest.raises(TypeError):
        rt._hidden_at_rank_one(fused, UNRESTRICTED)


def test_vis_idx_khop_voi_cot_that():
    """Cổng tất định, không cần DB (F2 vòng sửa 1): `VIS_IDX` phải trỏ đúng cột
    `c.visibility` trong CHUỖI `_COLS` THẬT của production — không chỉ trong
    hàng `_row()` dựng tay ở trên. Nếu sau này ai đổi thứ tự `_COLS` mà quên
    sửa `VIS_IDX`, các test khác ở trên vẫn xanh (vì `_row()` không đọc
    `_COLS`) trong khi production đọc nhầm cột và báo ra một tên lớp bậy —
    đúng lằn "fixture khác trường thật" đã cắn repo này một lần."""
    assert [c.strip() for c in rt._COLS.split(",")][rt.VIS_IDX] == "c.visibility"


class _ConnBongLoi:
    """Mô phỏng lỗi DB CHỈ ở lượt bóng (không lọc) — lượt LỌC vẫn chạy bình
    thường, y hệt tình huống F3 (vòng sửa 1) mô tả."""

    def __init__(self, visible):
        self.visible = visible

    def execute(self, sql, params=None):
        if VIS_CLAUSE in sql:
            return _Cur(self.visible)
        raise RuntimeError("DB lỗi giả lập ở lượt bóng")


def test_loi_luot_bong_khong_giet_ket_qua_da_loc(khong_ra_ngoai):
    """F3 (vòng sửa 1): lượt bóng hỏng không được giết một retrieval ĐÃ lọc
    SQL thành công — fail-open, giống cách `rerank()` đã fail-open."""
    conn = _ConnBongLoi(visible=[ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    # BẤT BIẾN: lỗi lượt bóng không vứt bỏ chunks đã lọc SQL thành công.
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]
    # Fail-open: mất tín hiệu TƯ VẤN hidden_classes, không mất kết quả.
    assert r.hidden_classes == frozenset()


# ─── Integration: DB thật ──────────────────────────────────────────────────

from tests.rag.test_retrieve_visibility import _DIM, _nap_hai_tai_lieu
from src.rag.visibility import UNRESTRICTED as _UNR


def _truc(hot: int):
    v = [0.0] * _DIM
    v[hot] = 1.0
    return v


@pytest.mark.integration
def test_ca_thuan_commercial_hang_1_thi_bao(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))   # gần chunk commercial
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    assert {c.source_file for c in r.chunks} == {"seed/policy.docx"}   # vẫn lọc


@pytest.mark.integration
def test_ca_nguoc_all_hang_1_thi_khong_bao(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(1))   # gần chunk 'all'
    r = rt.retrieve("hoàn hàng", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.chunks, "fixture sai — không có ứng viên thì test tự vô hiệu"


@pytest.mark.integration
def test_admin_khong_bao_va_thay_ca_hai(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))
    r = rt.retrieve("chiết khấu", conn=conn, visibility=_UNR)
    assert r.hidden_classes == frozenset()
    assert {c.source_file for c in r.chunks} == {"seed\\discount_policy.docx", "seed/policy.docx"}
