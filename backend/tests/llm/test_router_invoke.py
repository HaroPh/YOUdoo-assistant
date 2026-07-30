import pytest
from langchain_core.messages import HumanMessage

from src.llm.budget import BudgetLedger
from src.llm.catalog import spec_for
from src.llm.router import (COOLDOWN_RATE_LIMIT_S, ChainExhausted,
                            RoutedChatModel, Router)
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai, fake_ai_google)

MSGS = [HumanMessage("Tồn kho ABC?")]


def _router(clock, by_alias):
    """by_alias: {alias: FakeChatClient} — router lấy client theo alias."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    return Router(ledger, client_factory=lambda spec: by_alias[spec.alias])


def test_goi_thanh_cong_tra_ve_message_va_quyet_dinh(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.5-flash-lite": client})
    got = r.invoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."
    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert got.decision.fallback_depth == 0
    assert len(client.calls) == 1


def test_ghi_so_ngan_sach_bang_total_tokens_khong_phai_p_cong_c(clock):
    """Gemma: p=11, c=36, total=337. Cộng p+c đếm thiếu 7 lần."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    client = FakeChatClient([fake_ai("ok", prompt=11, completion=36, total=337)])
    r = Router(ledger, client_factory=lambda spec: client)
    r.invoke("chitchat", MSGS)
    got = store.usage_since(since=clock(), alias="gemma-4-31b")
    assert got.total_tokens == 337


def test_usage_metadata_cua_google_duoc_doc_dung_khong_qua_response_metadata(clock):
    """chitchat chạy gemma-4-31b, provider="google" → client thật là
    ChatGoogleGenerativeAI, KHÔNG BAO GIỜ set response_metadata["token_usage"].
    _usage() phải rơi xuống nhánh usage_metadata và lấy total_tokens THÔ của
    API (337), không phải p+c tính lại (11+36=47) — cùng phép đo Gemma ở test
    test_ghi_so_ngan_sach_bang_total_tokens_khong_phai_p_cong_c, nhưng lần này
    đi qua đúng hình dạng response mà production thật sự nhận được."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    client = FakeChatClient([fake_ai_google("ok", prompt=11, completion=36,
                                            total=337, reasoning=290)])
    r = Router(ledger, client_factory=lambda spec: client)
    r.invoke("chitchat", MSGS)
    got = store.usage_since(since=clock(), alias="gemma-4-31b")
    assert got.total_tokens == 337


def test_429_thi_dat_cooldown_va_tut_xuong_mat_xich_ke(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == "groq-llama-3.3-70b"
    assert got.decision.fallback_depth == 1
    assert [a.alias for a in got.attempts] == ["gemini-3.5-flash-lite"]


def test_sau_429_mat_xich_do_bi_cooldown_o_luot_sau(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    r.invoke("read", MSGS)
    assert len(hong.calls) == 1
    r.invoke("read", MSGS)          # lượt 2: không được chạm vào cái đang ốm
    assert len(hong.calls) == 1
    assert len(tot.calls) == 2


def test_cooldown_cua_429_dai_hon_cooldown_cua_loi_khac(clock):
    from src.llm.router import COOLDOWN_ERROR_S
    assert COOLDOWN_RATE_LIMIT_S > COOLDOWN_ERROR_S


def test_loi_5xx_cung_lam_tut_mat_xich(clock):
    hong = FakeChatClient([FakeServerError("sập")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    assert r.invoke("read", MSGS).decision.spec.alias == "groq-llama-3.3-70b"


def test_moi_mat_xich_deu_hong_thi_nem_ChainExhausted(clock):
    hong = FakeChatClient([FakeServerError("sập")])
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-llama-3.3-70b": hong})
    with pytest.raises(ChainExhausted):
        r.invoke("fusion", MSGS)      # chuỗi fusion chỉ có 2 mắt xích


def test_go_thought_cho_model_gemma(clock):
    """chitchat chạy gemma-4-31b (emits_thought_tags=True)."""
    client = FakeChatClient([fake_ai("<thought>nghĩ ngợi</thought>Chào bạn!")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    assert r.invoke("chitchat", MSGS).message.content == "Chào bạn!"


def test_khong_go_gi_voi_model_khong_nha_thought(clock):
    """read chạy gemini (emits_thought_tags=False) — nội dung giữ nguyên."""
    client = FakeChatClient([fake_ai("Thẻ <thought> nghĩa là gì?")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    assert r.invoke("read", MSGS).message.content == "Thẻ <thought> nghĩa là gì?"


def test_tool_duoc_bind_vao_client(clock):
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    client = FakeChatClient([fake_ai("ok")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    r.invoke("read", MSGS, tools=tools)
    assert client.bound_tools == tools


def test_ghim_khong_tut_khi_loi_ma_nem_thang_ra(clock):
    """Ghim là ghim — kể cả khi hỏng. Tụt lặng lẽ làm hỏng phép đo eval."""
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: hong)
    with pytest.raises(ChainExhausted):
        r.invoke("read", MSGS, pin="or-nemotron")
    assert len(hong.calls) == 1


async def test_ainvoke_hoat_dong_giong_invoke(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: client)
    got = await r.ainvoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."


async def test_ainvoke_cung_tut_mat_xich_khi_429(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.5-flash-lite": hong,
                        "groq-llama-3.3-70b": tot})
    got = await r.ainvoke("read", MSGS)
    assert got.decision.spec.alias == "groq-llama-3.3-70b"


async def test_ainvoke_khong_chan_event_loop_khi_store_cham(clock):
    """Blocker #2: to_thread phải thực sự nhường event loop, không chỉ gọi
    hàm đồng bộ trong 1 thread khác mà vẫn await liền — task khác PHẢI
    tiến được trong lúc resolve()/_finish() đang chạy trên thread."""
    import asyncio
    import time

    class SlowStore:
        def usage_since(self, **kwargs):
            time.sleep(0.3)          # mô phỏng round-trip Postgres đồng bộ
            from src.llm.store import Usage
            return Usage(requests=0, total_tokens=0)

        def record(self, **kwargs):
            time.sleep(0.3)

    ledger = BudgetLedger(SlowStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))

    progressed = []

    async def dem_nhip():
        for i in range(6):
            await asyncio.sleep(0.05)
            progressed.append(i)

    task = asyncio.create_task(dem_nhip())
    await router.ainvoke("router", [HumanMessage("hi")])
    await task

    assert len(progressed) >= 4, (
        f"chỉ tiến {len(progressed)}/6 nhịp — event loop có vẻ bị chặn "
        "trong lúc ainvoke chạy resolve()/_finish() đồng bộ")


@pytest.mark.asyncio
async def test_ainvoke_dung_routed_span_va_annotate_span(clock, monkeypatch):
    from src.llm import tracing
    import contextlib
    span_calls = []
    annotate_calls = []

    @contextlib.contextmanager
    def _fake_routed_span(role):
        span_calls.append(role)
        yield "FAKE_SPAN"

    monkeypatch.setattr(tracing, "routed_span", _fake_routed_span)
    monkeypatch.setattr(
        tracing, "annotate_span",
        lambda span, decision, result: annotate_calls.append((span, decision, result)))
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))
    llm = RoutedChatModel(router, "router")

    await llm.ainvoke([HumanMessage("hi")])

    assert span_calls == ["router"]
    assert len(annotate_calls) == 1
    span, decision, result = annotate_calls[0]
    assert span == "FAKE_SPAN"
    assert decision is result.decision
    assert result.total_tokens == 30


def test_invoke_dung_routed_span_va_annotate_span(clock, monkeypatch):
    from src.llm import tracing
    import contextlib
    span_calls = []
    annotate_calls = []

    @contextlib.contextmanager
    def _fake_routed_span(role):
        span_calls.append(role)
        yield "FAKE_SPAN"

    monkeypatch.setattr(tracing, "routed_span", _fake_routed_span)
    monkeypatch.setattr(
        tracing, "annotate_span",
        lambda span, decision, result: annotate_calls.append((span, decision, result)))
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    router = Router(ledger, client_factory=lambda spec: FakeChatClient([fake_ai()]))
    llm = RoutedChatModel(router, "router")

    llm.invoke([HumanMessage("hi")])

    assert span_calls == ["router"]
    assert len(annotate_calls) == 1
    span, decision, result = annotate_calls[0]
    assert span == "FAKE_SPAN"
    assert decision is result.decision
    assert result.total_tokens == 30
