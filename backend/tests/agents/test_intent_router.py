# backend/tests/agents/test_intent_router.py
import pytest
from langchain_core.messages import HumanMessage

from src.agents.state import ERPAgentState
from src.agents.routing import parse_proposal, make_intent_router_node
from src.agents.prompts import INTENT_ROUTER_PROMPT, render_intent_router_prompt
from tests.conftest import make_mock_llm

SOPS = frozenset({"giao-hang", "nhap-kho", "bao-gia-chiet-khau"})


def _state(text: str) -> ERPAgentState:
    return ERPAgentState(
        messages=[HumanMessage(content=text)],
        intent=None,
        pending_action=None,
        confirmed=None,
    )


@pytest.mark.asyncio
async def test_router_erp_read():
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("erp_read"))
    result = await node(_state("Đơn hàng nào đang trễ?"))
    assert result["intent"] == "erp_read"


@pytest.mark.asyncio
async def test_router_erp_write():
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("erp_write"))
    result = await node(_state("Tạo đơn hàng cho khách Nguyễn Văn A"))
    assert result["intent"] == "erp_write"


@pytest.mark.asyncio
async def test_router_rag():
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("rag"))
    result = await node(_state("Quy trình nhập kho là gì?"))
    assert result["intent"] == "rag"


@pytest.mark.asyncio
async def test_router_unknown():
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("unknown"))
    result = await node(_state("Xin chào"))
    assert result["intent"] == "unknown"


@pytest.mark.asyncio
async def test_router_invalid_llm_response_falls_back_to_unknown():
    """If LLM returns garbage, router must return 'unknown' not crash."""
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("I don't know, maybe erp?"))
    result = await node(_state("blah"))
    assert result["intent"] == "unknown"


@pytest.mark.asyncio
async def test_router_empty_messages():
    """Empty message list → unknown, no crash."""
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("erp_read"))
    state = ERPAgentState(messages=[], intent=None, pending_action=None, confirmed=None)
    result = await node(state)
    assert result["intent"] == "unknown"


@pytest.mark.asyncio
async def test_router_mixed():
    from src.agents.routing import make_intent_router_node
    node = make_intent_router_node(make_mock_llm("mixed"))
    result = await node(_state("Theo chính sách hoàn hàng, đơn của khách A có được hoàn không?"))
    assert result["intent"] == "mixed"


def test_parse_two_field_output():
    assert parse_proposal("intent: erp_write\nsop: giao-hang", SOPS) == \
        ("erp_write", "giao-hang")


def test_parse_empty_sop_field():
    assert parse_proposal("intent: rag\nsop:", SOPS) == ("rag", None)
    assert parse_proposal("intent: rag\nsop: ", SOPS) == ("rag", None)


def test_parse_drops_hallucinated_sop_name():
    # Fail an toàn: tên worker model bịa ra KHÔNG BAO GIỜ thành node đích —
    # trả nó ra sẽ làm LangGraph ném lỗi định tuyến giữa lượt chat thật.
    assert parse_proposal("intent: erp_write\nsop: xoa-sach-du-lieu", SOPS) == \
        ("erp_write", None)


def test_parse_invalid_intent_falls_back_to_unknown():
    assert parse_proposal("intent: banana\nsop:", SOPS) == ("unknown", None)


def test_parse_bare_intent_word_back_compat():
    # Model nhỏ bỏ qua format 2 dòng và trả đúng 1 từ như hợp đồng CŨ → vẫn
    # hiểu được, rơi về đúng hành vi hôm nay thay vì "unknown".
    assert parse_proposal("erp_read", SOPS) == ("erp_read", None)
    assert parse_proposal("  RAG  ", SOPS) == ("rag", None)


def test_parse_garbage_is_unknown_not_exception():
    assert parse_proposal("", SOPS) == ("unknown", None)
    assert parse_proposal("tôi không hiểu câu hỏi", SOPS) == ("unknown", None)


def test_parse_is_case_insensitive_and_tolerates_extra_lines():
    assert parse_proposal("Intent: ERP_WRITE\nSOP: giao-hang\nghi chú: x",
                                SOPS) == ("erp_write", "giao-hang")


@pytest.mark.asyncio
async def test_node_returns_both_fields():
    node = make_intent_router_node(
        make_mock_llm("intent: erp_write\nsop: giao-hang"),
        worker_block="worker: giao-hang\nmô tả: x", valid_sops=SOPS)
    from langchain_core.messages import HumanMessage
    out = await node({"messages": [HumanMessage(content="làm quy trình giao hàng cho S1")]})
    assert out == {"intent": "erp_write", "sop": "giao-hang"}


@pytest.mark.asyncio
async def test_node_always_writes_sop_key_so_it_never_leaks_across_turns():
    node = make_intent_router_node(make_mock_llm("intent: rag\nsop:"), valid_sops=SOPS)
    from langchain_core.messages import HumanMessage
    out = await node({"messages": [HumanMessage(content="chính sách đổi trả?")]})
    assert out["sop"] is None


@pytest.mark.asyncio
async def test_node_with_no_human_message_returns_unknown_and_no_sop():
    node = make_intent_router_node(make_mock_llm("intent: rag\nsop: giao-hang"),
                                   valid_sops=SOPS)
    assert await node({"messages": []}) == {"intent": "unknown", "sop": None}


def test_render_prompt_appends_worker_block():
    block = "worker: giao-hang\nmô tả: Dùng khi X."
    rendered = render_intent_router_prompt(block)
    assert rendered.startswith(INTENT_ROUTER_PROMPT)
    assert rendered.endswith(block)


def test_render_prompt_without_skills_is_base_prompt():
    assert render_intent_router_prompt("") == INTENT_ROUTER_PROMPT


def test_route_proposal_unpacks_as_tuple():
    """RouteProposal PHẢI unpack được kiểu tuple: eval_sop_select
    (evals/run_eval.py:447) làm `intent, sop = parse_proposal(...)`. Đổi sang
    dataclass sẽ làm eval gãy — test này đỏ TRƯỚC khi điều đó xảy ra."""
    from src.agents.routing import RouteProposal
    proposal = parse_proposal("intent: mixed\nsop: giao-hang", SOPS)
    intent, sop = proposal                      # phải unpack được
    assert (intent, sop) == ("mixed", "giao-hang")
    assert isinstance(proposal, tuple)
    assert proposal.intent == "mixed"           # và vẫn truy cập theo tên được
    assert proposal.sop == "giao-hang"
    assert RouteProposal("rag", None) == ("rag", None)
