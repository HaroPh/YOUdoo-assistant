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
        ("erp_write", "giao-hang", "full_sop")


def test_parse_empty_sop_field():
    assert parse_proposal("intent: rag\nsop:", SOPS) == ("rag", None, "none")
    assert parse_proposal("intent: rag\nsop: ", SOPS) == ("rag", None, "none")


def test_parse_drops_hallucinated_sop_name():
    # Fail an toàn: tên worker model bịa ra KHÔNG BAO GIỜ thành node đích —
    # trả nó ra sẽ làm LangGraph ném lỗi định tuyến giữa lượt chat thật.
    assert parse_proposal("intent: erp_write\nsop: xoa-sach-du-lieu", SOPS) == \
        ("erp_write", None, "none")


def test_parse_invalid_intent_falls_back_to_unknown():
    assert parse_proposal("intent: banana\nsop:", SOPS) == ("unknown", None, "none")


def test_parse_bare_intent_word_back_compat():
    # Model nhỏ bỏ qua format 2 dòng và trả đúng 1 từ như hợp đồng CŨ → vẫn
    # hiểu được, rơi về đúng hành vi hôm nay thay vì "unknown".
    assert parse_proposal("erp_read", SOPS) == ("erp_read", None, "none")
    assert parse_proposal("  RAG  ", SOPS) == ("rag", None, "none")


def test_parse_garbage_is_unknown_not_exception():
    assert parse_proposal("", SOPS) == ("unknown", None, "none")
    assert parse_proposal("tôi không hiểu câu hỏi", SOPS) == ("unknown", None, "none")


def test_parse_is_case_insensitive_and_tolerates_extra_lines():
    assert parse_proposal("Intent: ERP_WRITE\nSOP: giao-hang\nghi chú: x",
                          SOPS) == ("erp_write", "giao-hang", "full_sop")


@pytest.mark.asyncio
async def test_node_returns_both_fields():
    node = make_intent_router_node(
        make_mock_llm("intent: erp_write\nsop: giao-hang"),
        worker_block="worker: giao-hang\nmô tả: x", valid_sops=SOPS)
    from langchain_core.messages import HumanMessage
    out = await node({"messages": [HumanMessage(content="làm quy trình giao hàng cho S1")]})
    assert out == {"intent": "erp_write", "sop": "giao-hang", "depth": "full_sop"}


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
    assert await node({"messages": []}) == {"intent": "unknown", "sop": None, "depth": "none"}


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
    dataclass sẽ làm eval gãy — test này đỏ TRƯỚC khi điều đó xảy ra.

    2026-08-16: hợp đồng thành BA trường. Test này đã đỏ đúng lúc thêm
    `depth` và chỉ đúng chỗ 2 chỗ gọi trong run_eval.py phải sửa — đó là nó
    làm đúng việc, không phải nó cản đường."""
    from src.agents.routing import RouteProposal
    proposal = parse_proposal("intent: mixed\nsop: giao-hang\ndepth: full_sop", SOPS)
    intent, sop, depth = proposal               # phải unpack được
    assert (intent, sop, depth) == ("mixed", "giao-hang", "full_sop")
    assert isinstance(proposal, tuple)
    assert proposal.intent == "mixed"           # và vẫn truy cập theo tên được
    assert proposal.sop == "giao-hang"
    assert proposal.depth == "full_sop"
    assert RouteProposal("rag", None, "none") == ("rag", None, "none")


# ── depth: trường thứ ba của hợp đồng router ─────────────────────────────────


def test_parse_doc_duoc_depth():
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: erp_write\nsop: nhap-kho\ndepth: full_sop", SOPS)
    assert got.sop == "nhap-kho"
    assert got.depth == "full_sop"


def test_depth_la_none_khi_sop_rong():
    """Bất biến: `depth` chỉ có nghĩa khi có `sop`. Model vẫn hay điền bừa
    depth vào lượt sop rỗng (đo được ở spike vòng 1) — chuẩn hoá tại đây để
    decide_route không phải phòng thủ."""
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: rag\nsop:\ndepth: unsure", SOPS)
    assert got.sop is None
    assert got.depth == "none"


def test_depth_la_khong_hop_le_thi_ve_full_sop():
    """FAIL AN TOÀN: có sop nhưng depth không đọc được thì chạy ĐỦ quy trình.
    Chiều ngược lại (one_step) là chiều BỎ QUA các bước kiểm tra — không bao
    giờ được là mặc định của một lỗi parse."""
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: erp_write\nsop: nhap-kho\ndepth: banana", SOPS)
    assert got.depth == "full_sop"
    got2 = parse_proposal("intent: erp_write\nsop: nhap-kho", SOPS)
    assert got2.depth == "full_sop"


def test_hop_dong_hai_dong_cu_van_doc_duoc():
    """Checkpoint Postgres của hội thoại đang park mang phản hồi theo hợp đồng
    CŨ. Hợp đồng mới không được làm chúng thành 'unknown'."""
    from src.agents.routing import parse_proposal
    assert parse_proposal("intent: rag\nsop:", SOPS) == ("rag", None, "none")
    assert parse_proposal("erp_read", SOPS) == ("erp_read", None, "none")
