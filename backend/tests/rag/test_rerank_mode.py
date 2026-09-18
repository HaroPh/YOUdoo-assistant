# backend/tests/rag/test_rerank_mode.py
"""RAG_RERANK_MODE — spec 2026-09-17 §5. Mặc định `blend` = hành vi cũ."""
import dataclasses

from src.rag import reranker, retrieve
from src.rag.types import Chunk


def _chunks(n):
    return [Chunk(chunk_id=i, doc_id="d", source_file="d", doc_title="t",
                  section_path=None, page=None, sheet=None, row_range=None,
                  text=f"c{i}", dense_score=0.5, sparse_score=None,
                  rrf_score=1.0 / (i + 1), rank=i) for i in range(4)]


def test_override_xep_thuan_theo_diem_cross_encoder(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_MODE", "override")
    # CE đảo ngược hoàn toàn thứ tự RRF.
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, ok = retrieve.rerank("q", _chunks(4))
    assert ok and [c.chunk_id for c in out] == [3, 2, 1, 0]


def test_blend_mac_dinh_giu_hanh_vi_hoa(monkeypatch):
    monkeypatch.delenv("RAG_RERANK_MODE", raising=False)
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, ok = retrieve.rerank("q", _chunks(4))
    # Hoà 1:1: chunk 0 (RRF hạng 1, CE hạng 4) và chunk 3 (RRF hạng 4, CE
    # hạng 1) BẰNG điểm; sorted ổn định giữ chunk 0 trước.
    assert ok and [c.chunk_id for c in out][0] == 0


def test_gia_tri_la_thi_lui_ve_blend(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_MODE", "gì đó")
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, _ = retrieve.rerank("q", _chunks(4))
    assert [c.chunk_id for c in out][0] == 0
