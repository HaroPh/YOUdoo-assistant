# backend/tests/agents/test_fanout_graph.py
"""Test wiring fan-out trên build_graph() THẬT.

Bài học SP-2a (review toàn nhánh): toàn bộ test node skill dựng StateGraph
bằng tay nên KHÔNG chứng minh được wiring thật; test đầu tiên gọi build_graph()
thật phải thêm vào ở đợt vá cuối. SP-2b làm ngay từ đầu.
"""
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.graph import build_graph


def _graph():
    return build_graph(MagicMock(), tools=[], checkpointer=None)


def test_build_graph_has_all_four_fanout_nodes():
    nodes = _graph().get_graph().nodes
    for name in ("mixed", "gather_docs", "gather_erp", "fuse_answer"):
        assert name in nodes


def test_build_graph_has_no_fusion_module():
    import importlib
    try:
        importlib.import_module("src.agents.fusion")
    except ModuleNotFoundError:
        return
    raise AssertionError("src.agents.fusion phải bị xoá ở SP-2b")


def test_gather_erp_tools_subset_of_read_tools(monkeypatch):
    """Lớp phòng thủ THẬT thay cho deny-list WRITE_TOOL_NAMES đã bỏ: node chỉ
    bao giờ nhận allow-list build_erp_query_tools()."""
    import src.agents.graph as graph_mod
    from src.erp_query.tools import build_erp_query_tools
    captured = {}
    real = graph_mod.make_gather_erp_node

    def spy(llm, tools):
        captured["names"] = {t.name for t in tools}
        return real(llm, tools)

    monkeypatch.setattr(graph_mod, "make_gather_erp_node", spy)
    graph_mod.build_graph(MagicMock(), tools=[], checkpointer=None)
    read_names = {t.name for t in build_erp_query_tools()}
    assert captured["names"] <= read_names
    assert {"list_sale_orders", "get_stock", "get_overdue_invoices"} <= captured["names"]


def test_route_by_intent_still_returns_plain_mixed_string():
    """Hợp đồng đầu ra mà SOP_SELECT_CASES đo — không được đổi ở SP-2b."""
    from src.agents.graph import _route_by_intent
    state = {"intent": "mixed", "sop": None,
             "messages": [HumanMessage(content="theo chính sách, đơn X hoàn được không?")]}
    assert _route_by_intent(state) == "mixed"


async def test_real_graph_mixed_turn_produces_one_answer(monkeypatch):
    """Một lượt `mixed` đầu-cuối qua build_graph() THẬT: cả hai chân chạy, ra
    ĐÚNG MỘT AIMessage, cả hai key join về None ở state cuối."""
    import src.agents.fanout as fanout
    from src.rag.types import Chunk, RetrievalResult

    c = Chunk(chunk_id=1, doc_id="d", source_file="C:/docs/policy.docx",
              doc_title="P", section_path="Chính sách hoàn hàng › Điều 4",
              page=1, sheet=None, row_range=None,
              text="Hoàn hàng trong 30 ngày.", dense_score=0.7,
              sparse_score=None, rrf_score=0.02, rank=0)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: RetrievalResult(
        query=q, query_used=q, chunks=[c], top_score=0.02, total_candidates=1))

    ran = set()

    def fake_agent(llm, tools, system_prompt=None):
        agent = MagicMock()

        async def ainvoke(payload):
            ran.add("gather_erp")
            return {"messages": [AIMessage(content="- Đơn S00042 giao 15/07/2026")]}

        agent.ainvoke = ainvoke
        return agent

    monkeypatch.setattr(fanout, "_create_agent", fake_agent)
    monkeypatch.setattr(fanout, "cite_and_verify",
                        AsyncMock(side_effect=lambda b, ch, l: b + "\n\n📄 Nguồn: policy.docx, tr.1"))
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))

    router_llm = MagicMock()
    router_llm.ainvoke = AsyncMock(return_value=AIMessage(content="intent: mixed\nsop:"))
    fuse_llm = MagicMock()
    fuse_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Đơn đã quá 30 ngày."))

    class _LLMs(dict):
        def __missing__(self, k):
            return MagicMock()

    llms = _LLMs(router=router_llm, fusion=fuse_llm)
    graph = build_graph(llms, tools=[], checkpointer=None)
    final = await graph.ainvoke(
        {"messages": [HumanMessage(content="Đơn S00042 hoàn được không theo chính sách?")]})

    assert "gather_erp" in ran                       # chân ERP đã chạy
    answers = [m for m in final["messages"] if m.type == "ai"]
    assert len(answers) == 1
    assert "Đơn đã quá 30 ngày." in answers[0].content
    assert "📄 Nguồn:" in answers[0].content          # chân tài liệu đã chạy
    assert final["doc_context"] is None
    assert final["erp_facts"] is None
