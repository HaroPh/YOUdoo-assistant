# backend/tests/agents/test_erp_agent.py
"""ERPAgent: dựng + truyền Langfuse handler xuống graph/LLM."""
import pytest

from src.agents import erp_agent as erp_agent_module
from src.agents.erp_agent import ERPAgent


class _FakeHandler:
    """Đại diện CallbackHandler thật — chỉ cần phân biệt được bằng identity."""


def test_answer_stateless_truyen_callback_khi_co_handler(monkeypatch):
    """Xác nhận answer_stateless() truyền đúng config={"callbacks":[handler]}
    xuống RoutedChatModel.ainvoke() khi self._handler đã được dựng."""
    import asyncio

    fake_handler = _FakeHandler()
    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["config"] = config
            class _R:
                content = "ok"
            return _R()

    agent = ERPAgent()
    agent._handler = fake_handler
    agent._llms = {"synthesis": _FakeLLM()}

    result = asyncio.run(agent.answer_stateless("câu hỏi gì đó"))

    assert result == "ok"
    assert captured["config"] == {"callbacks": [fake_handler]}


def test_answer_stateless_config_none_khi_khong_co_handler():
    """self._handler is None (Langfuse tắt/lỗi) → config=None, không callback
    nào được truyền — hành vi y hệt không có Langfuse."""
    import asyncio

    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["config"] = config
            class _R:
                content = "ok"
            return _R()

    agent = ERPAgent()
    agent._handler = None
    agent._llms = {"synthesis": _FakeLLM()}

    asyncio.run(agent.answer_stateless("câu hỏi gì đó"))

    assert captured["config"] is None


@pytest.mark.asyncio
async def test_setup_goi_tracing_get_handler_that_qua_setup_day_du(monkeypatch):
    """Khác test_setup_dung_handler_tu_tracing ở trên (test đó tự gán
    self._handler thủ công, không gọi setup() thật — không bắt được regression
    nếu thứ tự dựng handler trong setup() bị đổi). Test này mock TOÀN BỘ hạ
    tầng nặng của setup() (MCP client, Postgres pool, checkpointer, graph) để
    không cần Postgres/MCP sống, nhưng gọi setup() THẬT — nếu dòng
    `self._handler = tracing.get_handler()` bị xoá hoặc dời sau make_llms()
    theo cách làm hỏng thứ tự, test này phải đỏ."""
    fake_handler = _FakeHandler()
    monkeypatch.setattr(erp_agent_module.tracing, "get_handler",
                        lambda: fake_handler)
    monkeypatch.setattr(erp_agent_module, "make_llms",
                        lambda: {"synthesis": object()})

    class _FakeTool:
        name = "fake_tool"

    class _FakeMCPClient:
        def __init__(self, *a, **k):
            pass

        async def get_tools(self):
            return [_FakeTool()]

    monkeypatch.setattr(erp_agent_module, "MultiServerMCPClient", _FakeMCPClient)

    class _FakePool:
        def __init__(self, *a, **k):
            pass

        async def open(self):
            pass

    monkeypatch.setattr(erp_agent_module, "AsyncConnectionPool", _FakePool)

    class _FakeCheckpointer:
        def __init__(self, *a, **k):
            pass

        async def setup(self):
            pass

    monkeypatch.setattr(erp_agent_module, "AsyncPostgresSaver", _FakeCheckpointer)
    monkeypatch.setattr(erp_agent_module, "build_graph",
                        lambda *a, **k: object())

    agent = ERPAgent()
    await agent.setup()

    assert agent._handler is fake_handler
    assert agent.tool_names == ["fake_tool"]
