# backend/tests/agents/test_rag_denied_nodes.py
"""Vai bị chặn phải nhận câu từ chối TẤT ĐỊNH — không LLM (spec 2026-09-21 §5).
Patch retrieve, LLM giả nổ nếu bị gọi."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, rag_access, roles
import src.agents.nodes as nodes_mod
from src.rag.types import RetrievalResult

TM = frozenset({"commercial"})
KHO = roles.PROFILES["small-business"]["warehouse"]


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
