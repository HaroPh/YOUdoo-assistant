import pytest
from langchain_core.messages import HumanMessage

from src.llm.budget import BudgetLedger
from src.llm.catalog import spec_for
from src.llm.router import (COOLDOWN_RATE_LIMIT_S, EMPTY_RESPONSE_REASON,
                            ChainExhausted, RoutedChatModel, Router)
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai, fake_ai_google, fake_ai_rong,
                                fake_ai_tool_call)

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


def test_phan_hoi_rong_thi_tut_mat_xich(clock):
    """Lỗi sống 2026-08-13: gemma-4-26b đốt hết 2045/2048 token vào suy luận
    nội bộ, phát ra 0 token hiển thị, HTTP 200. Trước bản sửa, chuỗi fallback
    không bao giờ chạy vì nó chỉ chạy khi có exception."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    got = r.invoke("router", MSGS)

    assert got.message.content == "intent: erp_write"
    assert got.decision.spec.alias == "groq-gpt-oss-20b"
    assert len(rong.calls) == 1        # gọi ĐÚNG một lần, không lặp lại
    assert len(tot.calls) == 1


def test_phan_hoi_rong_NHUNG_co_tool_call_thi_KHONG_tut(clock):
    """Ca dễ phá nhất: một lượt gọi tool THÀNH CÔNG cũng có content rỗng.
    Luật thiếu vế tool_calls sẽ làm hỏng erp_read, gather_erp,
    erp_write_planner và mọi node SOP."""
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI — không được gọi tới đây")])
    r = _router(clock, {"gemini-3.5-flash-lite": goi_tool,
                        "groq-llama-3.3-70b": khong_duoc_cham})

    got = r.invoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert got.message.tool_calls[0]["name"] == "get_stock"
    assert len(khong_duoc_cham.calls) == 0


def test_luot_bi_bo_van_duoc_ghi_so_ngan_sach(clock):
    """Token đã tiêu THẬT. Không ghi sổ thì sổ đếm thiếu và làm hỏng chính
    cơ chế chọn model."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = Router(ledger, client_factory=lambda spec: {
        "gemma-4-26b": rong, "groq-gpt-oss-20b": tot}[spec.alias])

    r.invoke("router", MSGS)

    assert store.usage_since(since=clock(),
                             alias="gemma-4-26b").total_tokens == 2406
    assert store.usage_since(since=clock(),
                             alias="groq-gpt-oss-20b").total_tokens == 800


def test_phan_hoi_rong_KHONG_dat_cooldown(clock):
    """Đây không phải 429 và model không ốm — nó chỉ không trả lời nổi prompt
    này. Lượt sau vẫn phải thử lại mắt xích 1."""
    rong = FakeChatClient([fake_ai_rong(), fake_ai("intent: erp_read")])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    r.invoke("router", MSGS)          # lượt 1: rỗng → tụt
    got = r.invoke("router", MSGS)    # lượt 2: mắt xích 1 PHẢI được thử lại

    assert len(rong.calls) == 2
    assert got.decision.spec.alias == "gemma-4-26b"
    assert got.message.content == "intent: erp_read"


def test_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem(clock):
    """Giữ hành vi hôm nay làm SÀN: bản sửa chỉ được cải thiện, không được đẻ
    ra đường crash mới. Không caller nào trong repo bắt ChainExhausted."""
    rong = FakeChatClient([fake_ai_rong()])
    r = _router(clock, {"gemini-3.1-flash-lite": rong,
                        "groq-llama-3.3-70b": rong})

    got = r.invoke("fusion", MSGS)    # chuỗi fusion chỉ có 2 mắt xích

    assert got.message.content == ""
    assert len(got.attempts) == 2
    assert all(a.error == EMPTY_RESPONSE_REASON for a in got.attempts)


def test_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan(clock):
    """Ghim là ghim. Toàn bộ eval dựa vào điều này — tụt lặng lẽ sẽ làm eval
    đo một model khác model được ghim."""
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: rong)

    got = r.invoke("router", MSGS, pin="gemma-4-26b")

    assert got.message.content == ""
    assert got.decision.spec.alias == "gemma-4-26b"
    assert len(rong.calls) == 1


async def test_ainvoke_cung_tut_khi_phan_hoi_rong(clock):
    """invoke và ainvoke là HAI thân hàm riêng — sửa một quên một là lỗi rất
    dễ xảy ra ở file này."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    got = await r.ainvoke("router", MSGS)

    assert got.decision.spec.alias == "groq-gpt-oss-20b"
    assert got.message.content == "intent: erp_write"


async def test_ainvoke_phan_hoi_rong_co_tool_call_thi_KHONG_tut(clock):
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI")])
    r = _router(clock, {"gemini-3.5-flash-lite": goi_tool,
                        "groq-llama-3.3-70b": khong_duoc_cham})

    got = await r.ainvoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.5-flash-lite"
    assert len(khong_duoc_cham.calls) == 0


async def test_ainvoke_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem(clock):
    """Bản ainvoke của test_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem
    — spec §4.1 hứa bảng ca áp cho CẢ invoke LẪN ainvoke, nhưng ainvoke mới là
    đường production thật (routing.py/confirmation.py/erp_agent.py đều
    `await llm.ainvoke`)."""
    rong = FakeChatClient([fake_ai_rong()])
    r = _router(clock, {"gemini-3.1-flash-lite": rong,
                        "groq-llama-3.3-70b": rong})

    got = await r.ainvoke("fusion", MSGS)    # chuỗi fusion chỉ có 2 mắt xích

    assert got.message.content == ""
    assert len(got.attempts) == 2
    assert all(a.error == EMPTY_RESPONSE_REASON for a in got.attempts)


async def test_ainvoke_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan(clock):
    """Bản ainvoke của test_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan."""
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec: rong)

    got = await r.ainvoke("router", MSGS, pin="gemma-4-26b")

    assert got.message.content == ""
    assert got.decision.spec.alias == "gemma-4-26b"
    assert len(rong.calls) == 1


async def test_ainvoke_luot_bi_bo_van_duoc_ghi_so_ngan_sach(clock):
    """Bản ainvoke của test_luot_bi_bo_van_duoc_ghi_so_ngan_sach."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = Router(ledger, client_factory=lambda spec: {
        "gemma-4-26b": rong, "groq-gpt-oss-20b": tot}[spec.alias])

    await r.ainvoke("router", MSGS)

    assert store.usage_since(since=clock(),
                             alias="gemma-4-26b").total_tokens == 2406
    assert store.usage_since(since=clock(),
                             alias="groq-gpt-oss-20b").total_tokens == 800


async def test_ainvoke_phan_hoi_rong_KHONG_dat_cooldown(clock):
    """Bản ainvoke của test_phan_hoi_rong_KHONG_dat_cooldown."""
    rong = FakeChatClient([fake_ai_rong(), fake_ai("intent: erp_read")])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemma-4-26b": rong, "groq-gpt-oss-20b": tot})

    await r.ainvoke("router", MSGS)          # lượt 1: rỗng → tụt
    got = await r.ainvoke("router", MSGS)    # lượt 2: mắt xích 1 PHẢI được thử lại

    assert len(rong.calls) == 2
    assert got.decision.spec.alias == "gemma-4-26b"
    assert got.message.content == "intent: erp_read"


def test_resolve_can_chuoi_giua_chung_van_tra_ket_qua_rong_KHONG_nem(clock):
    """C1: self.resolve(...) nằm NGOÀI try/except. Mắt xích 1 (rỗng) đã bị
    thêm vào skip cho lượt kế; nếu mắt xích 2 đang cooldown thì resolve() gọi
    lại sẽ cạn TOÀN BỘ chuỗi 2 mắt xích của vai fusion và ném ChainExhausted
    NGAY ĐẦU vòng lặp — TRƯỚC khi chạm nhánh `if last_empty is not None`.
    Kết quả rỗng đang cầm trong tay bị vứt, hàm ném ra ngoài thay vì trả về."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(ledger, client_factory=lambda spec: rong)
    ledger.cooldown(spec_for("groq-llama-3.3-70b"), 60.0)

    got = r.invoke("fusion", MSGS)      # chuỗi fusion: gemini-3.1-flash-lite, groq-llama-3.3-70b

    assert got.message.content == ""    # KHÔNG ném


async def test_ainvoke_resolve_can_chuoi_giua_chung_van_tra_ket_qua_rong_KHONG_nem(clock):
    """Bản async của test C1 ngay trên — invoke()/ainvoke() là hai thân hàm
    riêng, phải chứng minh cả hai cùng bị bug và cùng được sửa."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(ledger, client_factory=lambda spec: rong)
    ledger.cooldown(spec_for("groq-llama-3.3-70b"), 60.0)

    got = await r.ainvoke("fusion", MSGS)

    assert got.message.content == ""    # KHÔNG ném
