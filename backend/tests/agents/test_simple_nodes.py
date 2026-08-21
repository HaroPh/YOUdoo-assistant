# backend/tests/agents/test_simple_nodes.py
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from src.agents.state import ERPAgentState
from tests.conftest import make_mock_llm


def _state(text: str) -> ERPAgentState:
    return ERPAgentState(
        messages=[HumanMessage(content=text)],
        intent=None, pending_action=None, confirmed=None,
    )


@pytest.mark.asyncio
async def test_rag_node_synthesizes_answer(monkeypatch):
    import src.agents.nodes as nodes_mod
    from src.rag.types import Chunk, RetrievalResult
    c = Chunk(chunk_id=1, doc_id="d", source_file="C:/docs/policy.docx", doc_title="P",
              section_path="Chính sách hoàn hàng › Mục 1", page=1, sheet=None,
              row_range=None, text="Hoàn hàng trong 30 ngày.", dense_score=0.7,
              sparse_score=None, rrf_score=0.02, rank=0)
    result = RetrievalResult(query="q", query_used="q", chunks=[c], top_score=0.02,
                             total_candidates=1, method="dense-rrf")
    captured = {}

    def fake_retrieve(query, *a, **kw):
        captured["query"] = query
        return result

    monkeypatch.setattr(nodes_mod, "retrieve", fake_retrieve)

    from src.agents.nodes import make_rag_node
    node = make_rag_node(make_mock_llm("Khách được hoàn trong 30 ngày."))
    out = await node(_state("khách hoàn hàng mấy ngày?"))
    assert captured["query"] == "khách hoàn hàng mấy ngày?"
    content = out["messages"][0].content
    assert "Khách được hoàn trong 30 ngày." in content
    assert "📄 Nguồn:" in content


@pytest.mark.asyncio
async def test_rag_node_safe_message_on_retrieve_error(monkeypatch):
    import src.agents.nodes as nodes_mod
    from src.agents.synthesis import SAFE_MSG

    def boom(query, *a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(nodes_mod, "retrieve", boom)

    from src.agents.nodes import make_rag_node
    node = make_rag_node(make_mock_llm("unused"))
    out = await node(_state("bất kỳ"))
    assert out["messages"][0].content == SAFE_MSG


@pytest.mark.asyncio
async def test_respond_unknown_node_calls_llm():
    from src.agents.nodes import make_respond_unknown_node
    llm = make_mock_llm("Xin chào! Tôi có thể giúp gì cho bạn?")
    node = make_respond_unknown_node(llm)
    result = await node(_state("xin chào"))
    msgs = result["messages"]
    assert len(msgs) == 1
    assert "xin chào" in msgs[0].content.lower() or "giúp" in msgs[0].content.lower()


@pytest.mark.asyncio
async def test_erp_read_node_invokes_agent(monkeypatch):
    """erp_read node calls the inner agent and returns its last message."""
    from unittest.mock import AsyncMock, MagicMock
    from src.agents.nodes import make_erp_read_node
    from langchain_core.messages import HumanMessage, AIMessage

    # Stub an inner agent whose ainvoke returns a messages dict
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="query"),
            AIMessage(content="Kết quả: 5 đơn trễ"),
        ]
    })

    # Patch create_agent used inside make_erp_read_node
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_create_agent", lambda *a, **kw: mock_agent)

    node = make_erp_read_node(llm=MagicMock(), tools=[])
    state = ERPAgentState(
        messages=[HumanMessage(content="Đơn nào trễ?")],
        intent="erp_read", pending_action=None, confirmed=None,
    )
    result = await node(state)
    # Should return only the new AI message
    assert any("trễ" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_erp_read_context_yields_single_effective_system_prompt(monkeypatch):
    # Invariant A: ONE system prompt containing render + SYSTEM_PROMPT (context
    # first, so SYSTEM_PROMPT's trailing /no_think stays last); state messages
    # passed through untouched; context never leaks into returned messages.
    from unittest.mock import AsyncMock, MagicMock
    import src.agents.nodes as nodes_mod
    from src.agents.nodes import make_erp_read_node
    from src.agents.prompts import SYSTEM_PROMPT, render_working_context

    wc = {"ref": "S00040", "model": "sale.order", "display": "x"}
    captured = {}
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={
        "messages": [HumanMessage(content="q"), AIMessage(content="Đã giao 2/2.")]})

    def fake_create(llm, tools, system_prompt=None):
        captured["prompt"] = system_prompt
        return mock_agent

    monkeypatch.setattr(nodes_mod, "_create_agent", fake_create)
    node = make_erp_read_node(llm=MagicMock(), tools=[])
    state = ERPAgentState(messages=[HumanMessage(content="đơn đó giao chưa?")],
                          intent="erp_read", pending_action=None, confirmed=None,
                          working_context=wc)
    result = await node(state)
    assert captured["prompt"].startswith(render_working_context(wc))
    assert SYSTEM_PROMPT in captured["prompt"]
    sent_msgs = mock_agent.ainvoke.await_args[0][0]["messages"]
    assert sent_msgs == state["messages"]          # no extra SystemMessage injected
    assert all("Ngữ cảnh phiên làm việc" not in m.content
               for m in result["messages"])        # no leak into state


@pytest.mark.asyncio
async def test_erp_read_without_context_uses_base_prompt(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import src.agents.nodes as nodes_mod
    from src.agents.nodes import make_erp_read_node
    from src.agents.prompts import SYSTEM_PROMPT

    captured = {}
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [
        HumanMessage(content="q"), AIMessage(content="ok")]})
    monkeypatch.setattr(nodes_mod, "_create_agent",
                        lambda llm, tools, system_prompt=None:
                        captured.update(prompt=system_prompt) or mock_agent)
    node = make_erp_read_node(llm=MagicMock(), tools=[])
    await node(_state("có đơn nào trễ không?"))
    assert captured["prompt"] == SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_erp_read_node_verifies_grounding_when_tools_called(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from src.agents.nodes import make_erp_read_node
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="query"),
            ToolMessage(content='{"status": "success", "data": {"count": 5}}',
                       name="list_late_deliveries", tool_call_id="1"),
            AIMessage(content="Có 5 đơn trễ."),
        ]
    })
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_create_agent", lambda *a, **kw: mock_agent)

    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append((answer, tool_outputs))
        return "Có 5 đơn trễ (verified)."

    monkeypatch.setattr(nodes_mod, "verify_erp_grounding", fake_verify)

    node = make_erp_read_node(llm=MagicMock(), tools=[])
    state = ERPAgentState(
        messages=[HumanMessage(content="Đơn nào trễ?")],
        intent="erp_read", pending_action=None, confirmed=None,
    )
    result = await node(state)
    assert calls == [("Có 5 đơn trễ.", ['{"status": "success", "data": {"count": 5}}'])]
    assert result["messages"][-1].content == "Có 5 đơn trễ (verified)."


@pytest.mark.asyncio
async def test_erp_read_node_skips_verify_when_no_tools_called(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from src.agents.nodes import make_erp_read_node
    from langchain_core.messages import HumanMessage, AIMessage

    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="query"),
            AIMessage(content="Xin chào!"),
        ]
    })
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_create_agent", lambda *a, **kw: mock_agent)

    calls = []

    async def fake_verify(answer, tool_outputs, llm):
        calls.append((answer, tool_outputs))
        return answer

    monkeypatch.setattr(nodes_mod, "verify_erp_grounding", fake_verify)

    node = make_erp_read_node(llm=MagicMock(), tools=[])
    state = ERPAgentState(
        messages=[HumanMessage(content="Chào")],
        intent="erp_read", pending_action=None, confirmed=None,
    )
    await node(state)
    assert calls == []


# ── Ngữ cảnh hội thoại cho truy xuất (2026-08-20) ────────────────────────────
# rag_node và gather_docs đều lấy DUY NHẤT tin nhắn cuối, nên câu hỏi nối tiếp
# rút gọn ("trong bao lâu?") đi vào retrieve() trần trụi. Đo trên bộ multiturn:
# recall@6 0,7500 (không ngữ cảnh) vs 1,0000 (có) — một phần tư câu hỏi nối
# tiếp không tìm ra tài liệu đúng trong 6 chunk gửi cho LLM.

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.history import previous_user_turn


def test_previous_user_turn_bo_qua_cau_tra_loi_cua_tro_ly():
    # Chỉ lấy lượt NGƯỜI DÙNG. Câu trả lời của trợ lý dài và mang văn phong
    # tổng hợp; nhúng nó thành truy vấn là đưa nhiễu vào pool.
    msgs = [HumanMessage(content="chính sách đổi trả thế nào?"),
            AIMessage(content="Khách hàng được hoàn hàng trong 30 ngày..."),
            HumanMessage(content="thế còn hàng giảm giá?")]
    assert previous_user_turn(msgs) == "chính sách đổi trả thế nào?"


def test_previous_user_turn_luot_dau_tien_khong_co_ngu_canh():
    msgs = [HumanMessage(content="chính sách đổi trả thế nào?")]
    assert previous_user_turn(msgs) == ""


def test_previous_user_turn_danh_sach_rong():
    assert previous_user_turn([]) == ""


def test_previous_user_turn_chi_lay_MOT_luot_lien_truoc():
    # Một lượt, KHÔNG phải N: đó là cấu hình đã đo. Nhiều lượt hơn nghĩa là
    # nhiều ứng viên hơn tranh 20 chỗ trong pool — chưa đo, và đó chính là cơ
    # chế đã làm hỏng việc hồi sinh chân sparse.
    msgs = [HumanMessage(content="câu rất cũ"),
            HumanMessage(content="câu liền trước"),
            HumanMessage(content="câu hiện tại")]
    assert previous_user_turn(msgs) == "câu liền trước"


def test_previous_user_turn_bo_qua_noi_dung_rong():
    msgs = [HumanMessage(content="câu thật"),
            HumanMessage(content="   "),
            HumanMessage(content="câu hiện tại")]
    assert previous_user_turn(msgs) == "câu thật"


@pytest.mark.asyncio
async def test_rag_node_truyen_luot_truoc_vao_aux_queries(monkeypatch):
    """DÂY NỐI phải sống: rag_node gọi previous_user_turn và đưa kết quả vào
    aux_queries của retrieve() — KHÔNG trộn vào `query`.

    VÌ SAO TEST NÀY TỒN TẠI. Các test ngay trên chỉ kiểm `previous_user_turn()`
    như HÀM THUẦN. Đo bằng phép thử gỡ ngày 2026-08-20: thay lời gọi trong
    rag_node bằng `retrieve(query, TOP_K)` trần thì **1785 test vẫn XANH**. Bộ
    eval `multiturn` cũng không bắt được, vì nó gọi thẳng retrieve() chứ không
    đi qua node.

    Rủi ro cụ thể đang chờ: nhánh `worktree-user-memory-l2` sửa ĐÚNG câu lệnh
    này (thêm `memory=` cho synthesize) và git báo CONFLICT ở đây. Lấy nguyên
    một bên là mất một tính năng đã đo (multiturn recall@6 0,75 → 1,00). Bản
    hoà đúng giữ CẢ HAI. Test này làm cho bản hoà sai đỏ ngay thay vì im lặng.

    Cùng lớp lỗi với write-confirmation-ux-fix: cơ chế chết trên production mà
    mọi test đơn vị vẫn xanh vì không cái nào đi qua đường thật."""
    import src.agents.nodes as nodes_mod
    from langchain_core.messages import AIMessage
    from src.rag.types import RetrievalResult
    calls = []

    def fake_retrieve(*a, **kw):
        aux = kw["aux_queries"] if "aux_queries" in kw else (
            a[3] if len(a) > 3 else None)
        calls.append((a[0], aux))
        return RetrievalResult(query="q", query_used="q", chunks=[],
                               top_score=0.0, total_candidates=0,
                               method="dense-rrf")

    monkeypatch.setattr(nodes_mod, "retrieve", fake_retrieve)
    from src.agents.nodes import make_rag_node
    node = make_rag_node(make_mock_llm("x"))
    st = _state("còn hàng giảm giá thì sao?")
    st["messages"] = [HumanMessage(content="chính sách hoàn hàng thế nào?"),
                      AIMessage(content="Trong 30 ngày."),
                      HumanMessage(content="còn hàng giảm giá thì sao?")]
    await node(st)

    query, aux = calls[0]
    assert query == "còn hàng giảm giá thì sao?"          # query KHÔNG bị trộn
    assert aux == ("chính sách hoàn hàng thế nào?",)      # ngữ cảnh đi lối aux


@pytest.mark.asyncio
async def test_rag_node_luot_dau_khong_co_aux(monkeypatch):
    """Nửa còn lại: lượt đầu KHÔNG được bịa ra ngữ cảnh.

    Thiếu test này thì một bản cài đặt luôn truyền cả lịch sử vẫn xanh, và nó
    làm pool 20 chỗ loãng đi — đúng cơ chế đã làm hỏng việc hồi sinh chân
    sparse."""
    import src.agents.nodes as nodes_mod
    from src.rag.types import RetrievalResult
    calls = []

    def fake_retrieve(*a, **kw):
        aux = kw["aux_queries"] if "aux_queries" in kw else (
            a[3] if len(a) > 3 else None)
        calls.append(aux)
        return RetrievalResult(query="q", query_used="q", chunks=[],
                               top_score=0.0, total_candidates=0,
                               method="dense-rrf")

    monkeypatch.setattr(nodes_mod, "retrieve", fake_retrieve)
    from src.agents.nodes import make_rag_node
    await make_rag_node(make_mock_llm("x"))(_state("chính sách hoàn hàng?"))
    assert calls == [()]
