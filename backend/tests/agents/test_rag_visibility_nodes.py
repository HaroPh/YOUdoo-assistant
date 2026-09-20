# backend/tests/agents/test_rag_visibility_nodes.py
"""Hai node gọi retrieve() phải truyền visibility của VAI; không vai → None
(retrieve tự fail-closed). Không LLM thật, không DB: patch retrieve, bắt kwargs."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, roles
import src.agents.nodes as nodes_mod
from src.rag.types import RetrievalResult
from src.rag.visibility import UNRESTRICTED

SEES_COMMERCIAL = frozenset({"all", "commercial"})


class _NoopLLM:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="KHÔNG_ĐỦ_THÔNG_TIN")


def _rong(query="q", **_):
    return RetrievalResult(query=query, query_used=query, chunks=[],
                           top_score=0.0, total_candidates=0)


def _state(text):
    return {"messages": [HumanMessage(content=text)]}


def _bat(monkeypatch, module):
    got = {}

    def fake_retrieve(query, *a, **kw):
        got["visibility"] = kw.get("visibility", "KHONG_TRUYEN")
        return _rong(query)
    monkeypatch.setattr(module, "retrieve", fake_retrieve)
    return got


@pytest.mark.parametrize("vai,muon", [
    ("admin", UNRESTRICTED), ("accounting", SEES_COMMERCIAL),
    ("sales", SEES_COMMERCIAL), ("warehouse", frozenset({"all"}))])
async def test_rag_node_truyen_visibility_cua_vai(monkeypatch, vai, muon):
    got = _bat(monkeypatch, nodes_mod)
    cfg = roles.PROFILES["small-business"][vai]
    await nodes_mod.make_rag_node(_NoopLLM(), role_cfg=cfg)(_state("chiết khấu?"))
    assert got["visibility"] is muon if muon is UNRESTRICTED else got["visibility"] == muon


async def test_rag_node_khong_vai_truyen_None(monkeypatch):
    got = _bat(monkeypatch, nodes_mod)
    await nodes_mod.make_rag_node(_NoopLLM())(_state("chiết khấu?"))
    assert got["visibility"] is None


@pytest.mark.parametrize("vai,muon", [
    ("admin", UNRESTRICTED), ("warehouse", frozenset({"all"}))])
async def test_gather_docs_truyen_visibility_cua_vai(monkeypatch, vai, muon):
    got = _bat(monkeypatch, fanout)
    cfg = roles.PROFILES["small-business"][vai]
    await fanout.make_gather_docs_node(role_cfg=cfg)(_state("chiết khấu?"))
    assert got["visibility"] is muon if muon is UNRESTRICTED else got["visibility"] == muon


async def test_gather_docs_khong_vai_truyen_None(monkeypatch):
    got = _bat(monkeypatch, fanout)
    await fanout.make_gather_docs_node()(_state("chiết khấu?"))
    assert got["visibility"] is None
