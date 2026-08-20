"""Cả NĂM chỗ sinh câu trả lời đều phải nạp khối ký ức.

Năm chỗ ghép = năm chỗ có thể quên. Lớp lỗi "danh sách khai báo thiếu âm thầm"
đã tái phát 5 lần ở repo này, nên chống trôi bằng TEST chứ không bằng lời hứa.

BỐN → NĂM ngày 2026-08-20: bản đầu đếm bốn và kiểm `synthesize()` ở mức HÀM.
Nhưng `rag_node` mới là chỗ TRUYỀN ký ức vào hàm đó, và nó không được kiểm.
Đo bằng phép thử gỡ: thay `memory=state.get("user_memory") or ""` bằng
`memory=""` trong rag_node thì 1866 test vẫn XANH — tính năng chết trên đường
hỏi-đáp tài liệu mà không phép đo nào nhúc nhích. Cùng lớp lỗi đã bắt được
cùng ngày với dây nối `aux_queries` (xem test_simple_nodes.py).
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

MEMORY_BLOCK = "Ghi nhớ về người dùng này"


class _SpyLLM:
    """Bắt lại system prompt mà node thật sự gửi đi."""

    def __init__(self):
        self.system_prompts: list[str] = []

    async def ainvoke(self, messages, config=None):
        for m in messages:
            if m.type == "system":
                self.system_prompts.append(m.content)
        return AIMessage(content="ok")


@pytest.fixture
def state():
    return {"messages": [HumanMessage(content="xin chào")],
            "user_memory": "Ghi nhớ về người dùng này:\n- do_dai_tra_loi = ngắn gọn"}


async def test_respond_unknown_nap_khoi_ky_uc(state):
    from src.agents.nodes import make_respond_unknown_node
    llm = _SpyLLM()
    await make_respond_unknown_node(llm)(state)
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


async def test_fuse_answer_nap_khoi_ky_uc(state):
    from src.agents.fanout import make_fuse_answer_node
    llm = _SpyLLM()
    state = {**state, "doc_context": [], "erp_facts": "Đơn S00042 | 1.500.000"}
    await make_fuse_answer_node(llm)(state)
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


async def test_synthesize_nap_khoi_ky_uc():
    from src.agents.synthesis import SENTINEL, synthesize
    from src.rag.types import RetrievalResult

    class _Chunk:
        text = "Chính sách hoàn hàng trong 30 ngày."
        section_path = "Điều 1"
        source_file = "policy.docx"
        sheet = None
        page = None
        row_range = None
        dense_score = 0.9
        sparse_score = None

    class _SentinelLLM(_SpyLLM):
        """Trả SENTINEL để synthesize dừng NGAY sau lượt gọi đầu — system
        prompt đã bắt được rồi, và không phải dựng chunk giả đủ thật cho
        cite_and_verify chạy tiếp."""

        async def ainvoke(self, messages, config=None):
            await super().ainvoke(messages, config)
            return AIMessage(content=SENTINEL)

    llm = _SentinelLLM()
    result = RetrievalResult(query="q", query_used="q", chunks=[_Chunk()],
                             top_score=0.9, total_candidates=1)
    await synthesize("hỏi gì đó", result, llm,
                     memory="Ghi nhớ về người dùng này:\n- do_dai_tra_loi = ngắn gọn")
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


def test_state_co_field_user_memory():
    from src.agents.state import ERPAgentState
    assert "user_memory" in ERPAgentState.__annotations__


async def test_erp_read_nap_khoi_ky_uc(state, monkeypatch):
    """erp_read dựng ReAct agent nên _SpyLLM không bắt được lời gọi LLM —
    chặn ở _create_agent để đọc chính chuỗi system_prompt nó nhận."""
    from src.agents import nodes

    seen: list[str] = []

    def fake_create_agent(llm, tools, system_prompt):
        seen.append(system_prompt)

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [*payload["messages"], AIMessage(content="ok")]}
        return _Agent()

    monkeypatch.setattr(nodes, "_create_agent", fake_create_agent)
    await nodes.make_erp_read_node(_SpyLLM(), [])(state)
    assert any(MEMORY_BLOCK in p for p in seen)


async def test_rag_node_nap_khoi_ky_uc(state, monkeypatch):
    """Chỗ thứ NĂM: rag_node phải TRUYỀN ký ức vào synthesize().

    test_synthesize_nap_khoi_ky_uc ở trên chứng minh HÀM tôn trọng tham số.
    Test này chứng minh NODE thật sự truyền tham số đó — hai chuyện khác nhau,
    và chỉ chuyện thứ hai mới là thứ người dùng nhận được."""
    import src.agents.nodes as nodes_mod
    from src.agents.synthesis import SENTINEL
    from src.rag.types import RetrievalResult

    class _Chunk:
        text = "Chính sách hoàn hàng trong 30 ngày."
        section_path = "Điều 1"
        source_file = "policy.docx"
        sheet = None
        page = None
        row_range = None
        dense_score = 0.9
        sparse_score = None

    class _SentinelLLM(_SpyLLM):
        async def ainvoke(self, messages, config=None):
            await super().ainvoke(messages, config)
            return AIMessage(content=SENTINEL)

    monkeypatch.setattr(
        nodes_mod, "retrieve",
        lambda *a, **kw: RetrievalResult(query="q", query_used="q",
                                         chunks=[_Chunk()], top_score=0.9,
                                         total_candidates=1))
    llm = _SentinelLLM()
    st = {**state, "messages": [HumanMessage(content="chính sách hoàn hàng?")]}
    await nodes_mod.make_rag_node(llm)(st)
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)
