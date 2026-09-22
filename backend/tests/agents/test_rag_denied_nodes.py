# backend/tests/agents/test_rag_denied_nodes.py
"""Vai bị chặn phải nhận câu từ chối TẤT ĐỊNH — không LLM (spec 2026-09-21 §5).
Patch retrieve, LLM giả nổ nếu bị gọi."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, rag_access, roles
import src.agents.nodes as nodes_mod
from src.rag.types import Chunk, RetrievalResult

TM = frozenset({"commercial"})
KHO = roles.PROFILES["small-business"]["warehouse"]

# dense_score vượt sàn COS_FLOOR mặc định (synthesis.py, 0.35) để
# passes_floor()/is_empty() của synthesize() KHÔNG tự chặn hộ trước khi tới
# llm.ainvoke() — nếu không, bẫy _LLMKhongDuocGoi bất động bất kể rag_node có
# đúng hay sai (xem "Vòng sửa 1" trong task-3-report.md).
_CHUNK_VUOT_SAN = Chunk(chunk_id=1, doc_id="d1", source_file="f", doc_title="t",
                        section_path=None, page=1, sheet=None, row_range=None,
                        text="nội dung", dense_score=0.9, sparse_score=None,
                        rrf_score=0.9, rank=0)


class _LLMKhongDuocGoi:
    async def ainvoke(self, messages, config=None):
        raise AssertionError("LLM bị gọi dù đã có câu từ chối tất định")


class _LLMKhongDu:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="KHÔNG_ĐỦ_THÔNG_TIN")


def _ket_qua(hidden=frozenset()):
    return RetrievalResult(query="q", query_used="q", chunks=[], top_score=0.0,
                           total_candidates=0, hidden_classes=hidden)


def _state(text="Chính sách chiết khấu?"):
    return {"messages": [HumanMessage(content=text)]}


async def test_rag_node_bi_chan_tra_cau_tu_choi_khong_goi_llm(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua(TM))
    out = await nodes_mod.make_rag_node(_LLMKhongDuocGoi(), role_cfg=KHO)(_state())
    msg = out["messages"][0].content
    assert msg == rag_access.denied_message(KHO, TM, roles.load_profile())
    assert "Kế toán" in msg and "Bán hàng" in msg and rag_access.DENIED_MARKER in msg


async def test_rag_node_khong_bi_chan_van_di_synthesize(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua())
    out = await nodes_mod.make_rag_node(_LLMKhongDu(), role_cfg=KHO)(_state())
    assert rag_access.DENIED_MARKER not in out["messages"][0].content


async def test_rag_node_bi_chan_khong_goi_llm_that_su_du_chunk_khong_rong(monkeypatch):
    """Hai test trên dùng chunks=[] — synthesize() tự chặn ở is_empty() trước
    khi tới LLM, nên bẫy _LLMKhongDuocGoi không bao giờ thực sự có cơ hội nổ
    dù rag_node đúng hay sai (bug/no-bug đều ra 'không gọi LLM' theo cùng lý
    do sai). Test này dùng CHUNK VƯỢT SÀN cosine để loại bỏ đường tắt đó —
    nếu rag_node lỡ rơi xuống synthesize() sau khi đã tính xong câu từ chối,
    llm.ainvoke() SẼ bị gọi thật và bẫy nổ đúng như thiết kế."""
    monkeypatch.setattr(nodes_mod, "retrieve",
                        lambda *a, **kw: RetrievalResult(
                            query="q", query_used="q", chunks=[_CHUNK_VUOT_SAN],
                            top_score=0.9, total_candidates=1, hidden_classes=TM))
    out = await nodes_mod.make_rag_node(_LLMKhongDuocGoi(), role_cfg=KHO)(_state())
    msg = out["messages"][0].content
    assert msg == rag_access.denied_message(KHO, TM, roles.load_profile())
