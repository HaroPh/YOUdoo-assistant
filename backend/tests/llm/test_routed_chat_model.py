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
    assert llms["chitchat"].last_decision.spec.alias == "gemini-3.5-flash"


def test_content_dang_list_duoc_gop_ve_string(clock):
    """langchain_google_genai nhánh _is_gemini_3_or_later() phát ra content dạng
    list khối {"type": "text"}, khớp CẢ gemini-3.5-flash-lite lẫn
    gemini-3.1-flash-lite — hai model đứng đầu 4/7 chuỗi vai. Mọi code agents/
    port sang đều gọi .content.strip(), nên không gộp ở đây là vỡ rải rác."""
    from langchain_core.messages import AIMessage
    khoi = AIMessage(content=[{"type": "text", "text": "Còn 42 "},
                              {"type": "text", "text": "cái."}],
                     response_metadata={"token_usage": {
                         "prompt_tokens": 5, "completion_tokens": 5,
                         "total_tokens": 10}})
    llm = RoutedChatModel(_router(clock, FakeChatClient([khoi])), "read")
    assert llm.invoke(MSGS).content == "Còn 42 cái."


def test_content_None_thanh_chuoi_rong(clock):
    from langchain_core.messages import AIMessage
    rong = AIMessage(content=[], response_metadata={"token_usage": {
        "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    llm = RoutedChatModel(_router(clock, FakeChatClient([rong])), "read")
    assert llm.invoke(MSGS).content == ""


def test_last_decision_khong_ro_ri_giua_hai_vai(clock):
    """make_llms() dựng mỗi vai một RoutedChatModel MỘT LẦN và ERPAgent là
    singleton dùng chung mọi request — nên last_decision phải tách theo vai,
    không được là một ô nhớ dùng chung."""
    client = FakeChatClient([fake_ai("a"), fake_ai("b")])
    router = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                    client_factory=lambda spec: client)
    doc = RoutedChatModel(router, "read")
    tan_gau = RoutedChatModel(router, "chitchat")
    doc.invoke(MSGS)
    tan_gau.invoke(MSGS)
    assert doc.last_decision.spec.alias == "gemini-3.5-flash-lite"
    assert tan_gau.last_decision.spec.alias == "gemini-3.5-flash"


def test_last_decision_khong_ro_ri_giua_hai_request_dong_thoi(clock):
    """Hai request đồng thời CÙNG VAI không được đọc nhầm quyết định của nhau.

    Đọc last_decision TRONG cùng task đã gọi ainvoke — đúng như graph làm ở
    đường chạy thật (FastAPI cấp mỗi request một task riêng, node đọc quyết định
    ngay trong request đó). ContextVar tách theo ngữ cảnh nên hai task thấy hai
    giá trị khác nhau dù dùng chung một khoá vai.
    """
    import asyncio

    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    by_alias = {"gemini-3.5-flash-lite": hong, "groq-llama-3.3-70b": tot}
    r_tut = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                   client_factory=lambda spec: by_alias[spec.alias])
    r_thang = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
                     client_factory=lambda spec: FakeChatClient([fake_ai("ok")]))
    llm_tut = RoutedChatModel(r_tut, "read")
    llm_thang = RoutedChatModel(r_thang, "read")

    async def mot_request(llm):
        await llm.ainvoke(MSGS)
        return llm.last_decision          # đọc TRONG task, như graph thật

    async def hai_request_song_song():
        return await asyncio.gather(mot_request(llm_tut),
                                    mot_request(llm_thang))

    qd_tut, qd_thang = asyncio.run(hai_request_song_song())
    assert qd_tut.spec.alias == "groq-llama-3.3-70b"    # đã tụt vì 429
    assert qd_thang.spec.alias == "gemini-3.5-flash-lite"
    assert qd_tut is not qd_thang


def test_config_duoc_chuyen_tiep_xuong_client(clock):
    """config là đường LangChain lan callback/tag/metadata xuống runnable con —
    đúng đường handler Langfuse dùng. Nuốt nó là làm hỏng tracing âm thầm.

    Từ 2026-08-17 router CÒN THÊM metadata định tuyến vào bản sao config
    (tracing.with_route_metadata) để thông tin "vì sao lượt này chạy model
    nào" nằm CÙNG trace hội thoại thay vì rơi ra một trace gốc riêng. Nên
    khẳng định đúng ý định gốc — không mất gì của người gọi — chứ không đòi
    giống hệt nữa."""
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    cau_hinh = {"tags": ["thu-nghiem"], "metadata": {"phien": "abc"}}
    llm.invoke(MSGS, config=cau_hinh)

    da_gui = client.configs[-1]
    assert da_gui["tags"] == ["thu-nghiem"]
    assert da_gui["metadata"]["phien"] == "abc"      # không nuốt của người gọi
    assert da_gui["metadata"]["route"]["role"] == "read"
    # dict của người gọi KHÔNG bị sửa tại chỗ (LangGraph tái dùng config)
    assert cau_hinh == {"tags": ["thu-nghiem"], "metadata": {"phien": "abc"}}


def test_bind_tools_giu_lai_kwargs_phu(clock):
    """bind_tools(tools, tool_choice=...) nhận rồi bỏ im lặng là đổi hành vi
    âm thầm tại chỗ gọi đã port."""
    client = FakeChatClient([fake_ai("ok")])
    llm = RoutedChatModel(_router(clock, client), "read")
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    llm.bind_tools(tools, tool_choice="auto").invoke(MSGS)
    assert client.bound_tool_kwargs == {"tool_choice": "auto"}


def test_content_gemma_thinking_block_khong_lam_vo_va_khong_lo_ro(clock):
    """Tái hiện crash THẬT đo được ở spike Task 1 (docs/spikes/2026-07-29-
    port-cloud-model.md, phát hiện #2/#3): vai router có mắt xích đầu là
    gemma-4-26b (emits_thought_tags=True). part.thought truthy khiến
    langchain_google_genai phát ra content dạng [thinking-block, text-block]
    — HOÀN TOÀN không liên quan tới _is_gemini_3_or_later(). Trước khi vá,
    strip_thought() nhận list này và ném TypeError không ai bắt, vượt qua cả
    đường degrade ChainExhausted/SAFE_MSG đã thiết kế.

    Test này khoá CẢ HAI vế: (1) không crash, (2) khối "thinking" bị lọc bỏ —
    không rò rỉ suy nghĩ nội bộ vào câu trả lời cuối cùng."""
    from langchain_core.messages import AIMessage
    phan_hoi_gemma = AIMessage(
        content=[
            {"type": "thinking",
             "thinking": "User đang hỏi tồn kho, đây là câu hỏi đọc dữ liệu."},
            {"type": "text", "text": "erp_read"},
        ],
        response_metadata={"finish_reason": "STOP", "model_name": "gemma-4-26b-a4b-it"},
        usage_metadata={"input_tokens": 229, "output_tokens": 180,
                        "total_tokens": 409,
                        "output_token_details": {"reasoning": 177}})
    llm = RoutedChatModel(_router(clock, FakeChatClient([phan_hoi_gemma])), "router")
    ket_qua = llm.invoke(MSGS)      # không được ném TypeError
    assert ket_qua.content == "erp_read"
    assert "User đang hỏi" not in ket_qua.content    # khối thinking không rò rỉ
