import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable

from src.llm.budget import BudgetLedger
from src.llm.catalog import ROLES
from src.llm.router import Router, RoutedChatModel, make_llms
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import FakeChatClient, FakeRateLimit, fake_ai

MSGS = [HumanMessage("Tồn kho ABC?")]


def _router(clock, client):
    return Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                  client_factory=lambda spec: client)


def test_la_mot_Runnable_that(clock):
    """Graph LangGraph bind nó vào node, nên nó phải là Runnable thật."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read")
    assert isinstance(llm, Runnable)


def test_invoke_tra_ve_AIMessage_chu_khong_phai_InvokeResult(clock):
    """Chỗ gọi ở agents/ mong nhận AIMessage — hợp đồng cũ phải giữ nguyên."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai("Còn 42.")])),
                          "read")
    got = llm.invoke(MSGS)
    assert got.content == "Còn 42."
    assert hasattr(got, "type")


async def test_ainvoke_cung_tra_ve_AIMessage(clock):
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai("Còn 42.")])),
                          "read")
    got = await llm.ainvoke(MSGS)
    assert got.content == "Còn 42."


def test_bind_tools_giu_lai_tool_cho_luot_invoke(clock):
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    llm.bind_tools(tools).invoke(MSGS)
    assert client.bound_tools == tools


def test_bind_tools_tra_ve_ban_MOI_khong_sua_ban_goc(clock):
    """Khớp ngữ nghĩa bind_tools của LangChain — bản gốc phải sạch."""
    client = FakeChatClient([fake_ai("ok"), fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    llm.bind_tools([{"type": "function", "function": {"name": "get_stock"}}])
    llm.invoke(MSGS)                      # bản gốc: không bind tool nào
    assert client.bound_tools is None


def test_quyet_dinh_dinh_tuyen_cua_luot_cuoi_lay_lai_duoc(clock):
    """Kế hoạch C cần nó để đổ thuộc tính vào span Langfuse."""
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "gemini-3.5-flash-lite"
    assert llm.last_decision.fallback_depth == 0


def test_ghim_truyen_xuong_router(clock):
    llm = RoutedChatModel(_router(clock, FakeChatClient([fake_ai()])), "read",
                          pin="or-nemotron")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "or-nemotron"


def test_van_tut_mat_xich_qua_lop_boc(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    by_alias = {"gemini-3.5-flash-lite": hong, "groq-llama-3.3-70b": tot}
    router = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                    client_factory=lambda spec: by_alias[spec.alias])
    llm = RoutedChatModel(router, "read")
    llm.invoke(MSGS)
    assert llm.last_decision.spec.alias == "groq-llama-3.3-70b"


def test_make_llms_tra_ve_du_moi_vai(clock):
    llms = make_llms(_router(clock, FakeChatClient([fake_ai()])))
    assert set(llms) == set(ROLES)
    assert all(isinstance(v, RoutedChatModel) for v in llms.values())


def test_make_llms_nhan_ghim_theo_tung_vai(clock):
    """Đường eval ghim từng vai một để đo đúng một model."""
    llms = make_llms(_router(clock, FakeChatClient([fake_ai()])),
                     pins={"read": "or-nemotron"})
    llms["read"].invoke(MSGS)
    assert llms["read"].last_decision.spec.alias == "or-nemotron"
    llms["chitchat"].invoke(MSGS)
    assert llms["chitchat"].last_decision.spec.alias == "gemma-4-31b"
