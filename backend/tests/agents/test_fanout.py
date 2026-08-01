# backend/tests/agents/test_fanout.py
"""Test fan-out đường đọc (SP-2b) — 4 node thay node `fusion` cũ."""

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.rag.types import Chunk, RetrievalResult


def _chunk(**kw) -> Chunk:
    d = dict(chunk_id=1, doc_id="d", source_file="C:/docs/policy.docx",
             doc_title="P", section_path="Chính sách hoàn hàng › Điều 4",
             page=1, sheet=None, row_range=None,
             text="Hoàn hàng trong 30 ngày.", dense_score=0.7,
             sparse_score=None, rrf_score=0.02, rank=0)
    d.update(kw)
    return Chunk(**d)


def _result(chunks) -> RetrievalResult:
    return RetrievalResult(query="q", query_used="q", chunks=chunks,
                           top_score=(chunks[0].rrf_score if chunks else 0.0),
                           total_candidates=len(chunks), method="hybrid-rrf")


def _state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "intent": "mixed",
            "doc_context": None, "erp_facts": None}


def test_state_has_fanout_keys():
    from src.agents.state import ERPAgentState
    ann = ERPAgentState.__annotations__
    assert "doc_context" in ann
    assert "erp_facts" in ann


def test_gather_erp_prompt_forbids_concluding():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG kết luận" in GATHER_ERP_PROMPT
    assert GATHER_ERP_PROMPT.rstrip().endswith("/no_think")


def test_gather_erp_prompt_forbids_citing_documents():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG viện dẫn" in GATHER_ERP_PROMPT


def test_fuse_prompt_keeps_citation_trailer_contract():
    from src.agents.prompts import FUSE_PROMPT
    from src.agents.synthesis import USED_MARKER
    # extract_used_citations() parse đúng dòng này — không phải trang trí.
    assert USED_MARKER in FUSE_PROMPT
    assert FUSE_PROMPT.rstrip().endswith("/no_think")


def test_fuse_prompt_forbids_inline_section_numbers():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in FUSE_PROMPT
    assert "HAY số thứ tự đoạn tài liệu" in FUSE_PROMPT


def test_fuse_prompt_mentions_no_write():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG thực hiện thao tác ghi" in FUSE_PROMPT


def test_chunk_dict_roundtrip_is_lossless():
    from src.agents.fanout import chunk_to_dict, chunks_from_dicts
    c = _chunk(rerank_score=0.9)
    back = chunks_from_dicts([chunk_to_dict(c)])
    assert back == [c]


def test_chunk_to_dict_is_plain_json_types():
    from src.agents.fanout import chunk_to_dict
    d = chunk_to_dict(_chunk())
    assert isinstance(d, dict)
    assert all(v is None or isinstance(v, (str, int, float)) for v in d.values())


def test_chunks_from_dicts_handles_none():
    from src.agents.fanout import chunks_from_dicts
    assert chunks_from_dicts(None) == []


async def test_gather_docs_writes_chunks_as_dicts(monkeypatch):
    import src.agents.fanout as fanout
    c = _chunk(dense_score=0.7)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([c]))
    out = await fanout.make_gather_docs_node()(_state("chính sách hoàn hàng?"))
    assert out == {"doc_context": [asdict(c)]}


async def test_gather_docs_retrieves_with_full_question(monkeypatch):
    """Khác `fusion` cũ (agent tự chọn query, hay truyền từ khoá trần) —
    fan-out LUÔN truy xuất bằng nguyên câu hỏi, nên aux_queries thành thừa."""
    import src.agents.fanout as fanout
    calls = []

    def fake_retrieve(q, *a, **kw):
        calls.append((q, kw.get("aux_queries")))
        return _result([])

    monkeypatch.setattr(fanout, "retrieve", fake_retrieve)
    await fanout.make_gather_docs_node()(_state("Đơn S00042 hoàn được không?"))
    assert calls == [("Đơn S00042 hoàn được không?", None)]


async def test_gather_docs_below_floor_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    c = _chunk(dense_score=0.2, sparse_score=None)
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([c]))
    out = await fanout.make_gather_docs_node()(_state("câu ngoài corpus"))
    assert out == {"doc_context": []}


async def test_gather_docs_empty_result_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([]))
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert out == {"doc_context": []}


async def test_gather_docs_swallows_exception(monkeypatch):
    """Exception THOÁT RA sẽ giết CẢ superstep — tức chân ERP chạy song song
    cũng mất theo. Chân phải tự nuốt lỗi và ghi giá trị rỗng."""
    import src.agents.fanout as fanout

    def boom(q, *a, **kw):
        raise RuntimeError("pgvector down")

    monkeypatch.setattr(fanout, "retrieve", boom)
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert out == {"doc_context": []}


async def test_gather_docs_never_writes_messages(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "retrieve", lambda q, *a, **kw: _result([_chunk()]))
    out = await fanout.make_gather_docs_node()(_state("gì đó"))
    assert "messages" not in out


async def test_gather_docs_no_human_message_writes_empty(monkeypatch):
    import src.agents.fanout as fanout
    called = []
    monkeypatch.setattr(fanout, "retrieve",
                        lambda q, *a, **kw: called.append(q) or _result([]))
    out = await fanout.make_gather_docs_node()(
        {"messages": [AIMessage(content="xin chào")]})
    assert out == {"doc_context": []}
    assert called == []


def _fake_agent(messages_out):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": messages_out})
    return agent


async def test_gather_erp_writes_last_ai_content(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="- Đơn S00042 giao 15/07/2026")]))
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert out == {"erp_facts": "- Đơn S00042 giao 15/07/2026"}


async def test_gather_erp_uses_gather_prompt(monkeypatch):
    import src.agents.fanout as fanout
    from src.agents.prompts import GATHER_ERP_PROMPT
    captured = {}

    def spy(llm, tools, system_prompt=None):
        captured["prompt"] = system_prompt
        return _fake_agent([AIMessage(content="ok")])

    monkeypatch.setattr(fanout, "_create_agent", spy)
    await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert captured["prompt"] == GATHER_ERP_PROMPT


async def test_gather_erp_passes_tools_through_unfiltered(monkeypatch):
    """KHÔNG bê deny-list WRITE_TOOL_NAMES của fusion.py sang: nó phủ 9/29 tool
    ghi nên thực tế là no-op, mà lại TRÔNG NHƯ một lớp phòng thủ. Lớp thật là
    allow-list build_erp_query_tools() do graph.py truyền vào — có test chốt
    riêng ở test_fanout_graph.py."""
    import src.agents.fanout as fanout
    captured = {}

    def spy(llm, tools, system_prompt=None):
        captured["names"] = [t.name for t in tools]
        return _fake_agent([AIMessage(content="ok")])

    monkeypatch.setattr(fanout, "_create_agent", spy)
    t = MagicMock(); t.name = "list_sale_orders"
    await fanout.make_gather_erp_node(MagicMock(), tools=[t])(_state("x?"))
    assert captured["names"] == ["list_sale_orders"]


async def test_gather_erp_swallows_exception(monkeypatch):
    import src.agents.fanout as fanout

    def boom(llm, tools, system_prompt=None):
        agent = MagicMock()

        async def explode(payload):
            raise RuntimeError("llm down")

        agent.ainvoke = explode
        return agent

    monkeypatch.setattr(fanout, "_create_agent", boom)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert out == {"erp_facts": ""}


async def test_gather_erp_never_writes_messages(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="ok")]))
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert "messages" not in out


async def test_gather_erp_verifies_grounding_against_raw_tool_output(monkeypatch):
    """fusion cũ verify câu trả lời CUỐI so với tool output THÔ. Fan-out tách
    đôi nên phải verify hai chặng, nếu không dữ kiện bịa ở chân này không bao
    giờ bị bắt."""
    import src.agents.fanout as fanout
    from langchain_core.messages import ToolMessage

    monkeypatch.setattr(
        fanout, "_create_agent",
        lambda llm, tools, system_prompt=None: _fake_agent([
            ToolMessage(content='{"count": 5}', name="list_sale_orders",
                        tool_call_id="1"),
            AIMessage(content="- Có 9 đơn trễ"),
        ]))
    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append((answer, tool_outputs))
        return "- Có 5 đơn trễ"

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert calls == [("- Có 9 đơn trễ", ['{"count": 5}'])]
    assert out == {"erp_facts": "- Có 5 đơn trễ"}


async def test_gather_erp_skips_grounding_when_no_tool_output(monkeypatch):
    import src.agents.fanout as fanout
    monkeypatch.setattr(fanout, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        _fake_agent([AIMessage(content="Không tìm được dữ kiện ERP liên quan.")]))
    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append(answer)
        return answer

    monkeypatch.setattr(fanout, "verify_erp_grounding", fake_verify)
    out = await fanout.make_gather_erp_node(MagicMock(), tools=[])(_state("x?"))
    assert calls == []
    assert out == {"erp_facts": "Không tìm được dữ kiện ERP liên quan."}
