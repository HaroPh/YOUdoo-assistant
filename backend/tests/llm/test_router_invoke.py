import pytest
from langchain_core.messages import HumanMessage

from src.llm.budget import BudgetLedger
from src.llm.catalog import CHAINS, spec_for
from src.llm.router import (COOLDOWN_RATE_LIMIT_S, EMPTY_RESPONSE_REASON,
                            ChainExhausted, RoutedChatModel, Router)
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai, fake_ai_google, fake_ai_rong,
                                fake_ai_tool_call)

MSGS = [HumanMessage("Tồn kho ABC?")]


def _router(clock, by_alias, mac_dinh=None):
    """by_alias: {alias: FakeChatClient} — router lấy client theo alias.

    `mac_dinh` dùng cho các ca "MỌI mắt xích cùng hỏng/cùng rỗng": đưa một
    client duy nhất áp cho cả chuỗi thay vì gõ tay từng alias. Gõ tay khiến ca
    đó gắn cứng vào ĐỘ DÀI chuỗi — mà chuỗi đã đổi độ dài hai lần trong hai
    ngày. Khi KHÔNG truyền `mac_dinh`, alias lạ vẫn ném KeyError như cũ, để các
    ca "phải tụt đúng tới mắt xích 2" không im lặng nuốt một mắt xích thứ ba.
    """
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)

    def _lay(spec, api_key=None):
        if mac_dinh is not None:
            return by_alias.get(spec.alias, mac_dinh)
        return by_alias[spec.alias]

    return Router(ledger, client_factory=_lay)


def test_goi_thanh_cong_tra_ve_message_va_quyet_dinh(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.1-flash-lite": client})
    got = r.invoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."
    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert got.decision.fallback_depth == 0
    assert len(client.calls) == 1


def test_ghi_so_ngan_sach_bang_total_tokens_khong_phai_p_cong_c(clock):
    """Gemma: p=11, c=36, total=337. Cộng p+c đếm thiếu 7 lần.

    Dùng vai `evaluator` (mắt xích 1 = gemma-4-26b) — trước 2026-08-13 là vai
    `chitchat`, vai đó nay không còn chạy gemma."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    client = FakeChatClient([fake_ai("ok", prompt=11, completion=36, total=337)])
    r = Router(ledger, client_factory=lambda spec, api_key=None: client)
    r.invoke("evaluator", MSGS)
    got = store.usage_since(since=clock(), alias="gemini-3.1-flash-lite")
    assert got.total_tokens == 337


def test_usage_metadata_cua_google_duoc_doc_dung_khong_qua_response_metadata(clock):
    """evaluator chạy gemma-4-26b, provider="google" → client thật là
    ChatGoogleGenerativeAI, KHÔNG BAO GIỜ set response_metadata["token_usage"].
    _usage() phải rơi xuống nhánh usage_metadata và lấy total_tokens THÔ của
    API (337), không phải p+c tính lại (11+36=47) — cùng phép đo Gemma ở test
    test_ghi_so_ngan_sach_bang_total_tokens_khong_phai_p_cong_c, nhưng lần này
    đi qua đúng hình dạng response mà production thật sự nhận được."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    client = FakeChatClient([fake_ai_google("ok", prompt=11, completion=36,
                                            total=337, reasoning=290)])
    r = Router(ledger, client_factory=lambda spec, api_key=None: client)
    r.invoke("evaluator", MSGS)
    got = store.usage_since(since=clock(), alias="gemini-3.1-flash-lite")
    assert got.total_tokens == 337


def test_429_thi_dat_cooldown_va_tut_xuong_mat_xich_ke(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-gpt-oss-120b": tot})
    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == "groq-gpt-oss-120b"
    assert got.decision.fallback_depth == 1
    assert [a.alias for a in got.attempts] == ["gemini-3.1-flash-lite"]


def test_sau_429_mat_xich_do_bi_cooldown_o_luot_sau(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-gpt-oss-120b": tot})
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
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-gpt-oss-120b": tot})
    assert r.invoke("read", MSGS).decision.spec.alias == "groq-gpt-oss-120b"


def test_moi_mat_xich_deu_hong_thi_nem_ChainExhausted(clock):
    hong = FakeChatClient([FakeServerError("sập")])
    r = _router(clock, {}, mac_dinh=hong)
    with pytest.raises(ChainExhausted):
        r.invoke("fusion", MSGS)


def test_go_thought_khi_spec_bat_co_emits_thought_tags(clock, monkeypatch):
    """Bóc <thought> phải chạy trên ĐƯỜNG ROUTER, không chỉ ở strip_thought().

    Sau đợt gom 2026-08-21, KHÔNG model nào trong CATALOG còn
    emits_thought_tags=True (gemma-4-26b — chủ nhân duy nhất của cờ đó — đã bị
    xoá). Nếu chỉ sửa kỳ vọng thì phần phủ này biến mất âm thầm, trong khi
    NHÁNH CODE vẫn còn và vẫn phải đúng nếu mai có model họ Gemma quay lại.
    Nên test tự bật cờ trên một spec, thay vì dựa vào catalog."""
    from dataclasses import replace

    from src.llm import catalog as cat
    spec = replace(cat.CATALOG["gemini-3.1-flash-lite"], emits_thought_tags=True)
    monkeypatch.setitem(cat.CATALOG, "gemini-3.1-flash-lite", spec)

    client = FakeChatClient([fake_ai("<thought>nghĩ ngợi</thought>Chào bạn!")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: client)
    assert r.invoke("evaluator", MSGS).message.content == "Chào bạn!"


def test_khong_go_gi_voi_model_khong_nha_thought(clock):
    """read chạy gemini (emits_thought_tags=False) — nội dung giữ nguyên."""
    client = FakeChatClient([fake_ai("Thẻ <thought> nghĩa là gì?")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: client)
    assert r.invoke("read", MSGS).message.content == "Thẻ <thought> nghĩa là gì?"


def test_tool_duoc_bind_vao_client(clock):
    tools = [{"type": "function", "function": {"name": "get_stock"}}]
    client = FakeChatClient([fake_ai("ok")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: client)
    r.invoke("read", MSGS, tools=tools)
    assert client.bound_tools == tools


def test_ghim_khong_tut_khi_loi_ma_nem_thang_ra(clock):
    """Ghim là ghim — kể cả khi hỏng. Tụt lặng lẽ làm hỏng phép đo eval."""
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: hong)
    with pytest.raises(ChainExhausted):
        r.invoke("read", MSGS, pin="groq-gpt-oss-120b")
    assert len(hong.calls) == 1


async def test_ainvoke_hoat_dong_giong_invoke(clock):
    client = FakeChatClient([fake_ai("Còn 42 cái.")])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: client)
    got = await r.ainvoke("read", MSGS)
    assert got.message.content == "Còn 42 cái."


async def test_ainvoke_cung_tut_mat_xich_khi_429(clock):
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router(clock, {"gemini-3.1-flash-lite": hong,
                        "groq-gpt-oss-120b": tot})
    got = await r.ainvoke("read", MSGS)
    assert got.decision.spec.alias == "groq-gpt-oss-120b"


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
    router = Router(ledger, client_factory=lambda spec, api_key=None: FakeChatClient([fake_ai()]))

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
    router = Router(ledger, client_factory=lambda spec, api_key=None: FakeChatClient([fake_ai()]))
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
    router = Router(ledger, client_factory=lambda spec, api_key=None: FakeChatClient([fake_ai()]))
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
    không bao giờ chạy vì nó chỉ chạy khi có exception.

    Test dựng phản hồi rỗng ở MẮT XÍCH 1 của vai router, mà mắt xích đó nay là
    gemini-3.1-flash-lite chứ không còn là gemma — KHÔNG phải nhầm lẫn. Cơ chế
    tụt mắt xích không phụ thuộc model; `fake_ai_rong()` là hình dạng phản hồi
    ĐO ĐƯỢC THẬT (từ gemma), dùng để mô phỏng bất kỳ mắt xích nào trả rỗng."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    got = r.invoke("router", MSGS)

    assert got.message.content == "intent: erp_write"
    assert got.decision.spec.alias == "groq-gpt-oss-120b"
    assert len(rong.calls) == 1        # gọi ĐÚNG một lần, không lặp lại
    assert len(tot.calls) == 1


def test_phan_hoi_rong_NHUNG_co_tool_call_thi_KHONG_tut(clock):
    """Ca dễ phá nhất: một lượt gọi tool THÀNH CÔNG cũng có content rỗng.
    Luật thiếu vế tool_calls sẽ làm hỏng erp_read, gather_erp,
    erp_write_planner và mọi node SOP."""
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI — không được gọi tới đây")])
    r = _router(clock, {"gemini-3.1-flash-lite": goi_tool,
                        "groq-gpt-oss-120b": khong_duoc_cham})

    got = r.invoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert got.message.tool_calls[0]["name"] == "get_stock"
    assert len(khong_duoc_cham.calls) == 0


def test_luot_bi_bo_van_duoc_ghi_so_ngan_sach(clock):
    """Token đã tiêu THẬT. Không ghi sổ thì sổ đếm thiếu và làm hỏng chính
    cơ chế chọn model."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = Router(ledger, client_factory=lambda spec, api_key=None: {
        "gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot}[spec.alias])

    r.invoke("router", MSGS)

    assert store.usage_since(since=clock(),
                             alias="gemini-3.1-flash-lite").total_tokens == 2406
    assert store.usage_since(since=clock(),
                             alias="groq-gpt-oss-120b").total_tokens == 800


def test_phan_hoi_rong_KHONG_dat_cooldown(clock):
    """Đây không phải 429 và model không ốm — nó chỉ không trả lời nổi prompt
    này. Lượt sau vẫn phải thử lại mắt xích 1."""
    rong = FakeChatClient([fake_ai_rong(), fake_ai("intent: erp_read")])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    r.invoke("router", MSGS)          # lượt 1: rỗng → tụt
    got = r.invoke("router", MSGS)    # lượt 2: mắt xích 1 PHẢI được thử lại

    assert len(rong.calls) == 2
    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert got.message.content == "intent: erp_read"


def test_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem(clock):
    """Giữ hành vi hôm nay làm SÀN: bản sửa chỉ được cải thiện, không được đẻ
    ra đường crash mới. Không caller nào trong repo bắt ChainExhausted."""
    rong = FakeChatClient([fake_ai_rong()])
    r = _router(clock, {}, mac_dinh=rong)

    got = r.invoke("fusion", MSGS)

    assert got.message.content == ""
    assert len(got.attempts) == len(CHAINS["fusion"])
    assert all(a.error == EMPTY_RESPONSE_REASON for a in got.attempts)


def test_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan(clock):
    """Ghim là ghim. Toàn bộ eval dựa vào điều này — tụt lặng lẽ sẽ làm eval
    đo một model khác model được ghim."""
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: rong)

    got = r.invoke("router", MSGS, pin="gemini-3.1-flash-lite")

    assert got.message.content == ""
    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert len(rong.calls) == 1


async def test_ainvoke_cung_tut_khi_phan_hoi_rong(clock):
    """invoke và ainvoke là HAI thân hàm riêng — sửa một quên một là lỗi rất
    dễ xảy ra ở file này."""
    rong = FakeChatClient([fake_ai_rong()])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    got = await r.ainvoke("router", MSGS)

    assert got.decision.spec.alias == "groq-gpt-oss-120b"
    assert got.message.content == "intent: erp_write"


async def test_ainvoke_phan_hoi_rong_co_tool_call_thi_KHONG_tut(clock):
    goi_tool = FakeChatClient([fake_ai_tool_call()])
    khong_duoc_cham = FakeChatClient([fake_ai("SAI")])
    r = _router(clock, {"gemini-3.1-flash-lite": goi_tool,
                        "groq-gpt-oss-120b": khong_duoc_cham})

    got = await r.ainvoke("read", MSGS)

    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert len(khong_duoc_cham.calls) == 0


async def test_ainvoke_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem(clock):
    """Bản ainvoke của test_moi_mat_xich_deu_rong_thi_tra_ket_qua_cuoi_KHONG_nem
    — spec §4.1 hứa bảng ca áp cho CẢ invoke LẪN ainvoke, nhưng ainvoke mới là
    đường production thật (routing.py/confirmation.py/erp_agent.py đều
    `await llm.ainvoke`)."""
    rong = FakeChatClient([fake_ai_rong()])
    r = _router(clock, {}, mac_dinh=rong)

    got = await r.ainvoke("fusion", MSGS)

    assert got.message.content == ""
    assert len(got.attempts) == len(CHAINS["fusion"])
    assert all(a.error == EMPTY_RESPONSE_REASON for a in got.attempts)


async def test_ainvoke_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan(clock):
    """Bản ainvoke của test_ghim_gap_phan_hoi_rong_thi_goi_dung_mot_lan."""
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(BudgetLedger(InMemoryUsageStore(), clock=clock),
               client_factory=lambda spec, api_key=None: rong)

    got = await r.ainvoke("router", MSGS, pin="gemini-3.1-flash-lite")

    assert got.message.content == ""
    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert len(rong.calls) == 1


async def test_ainvoke_luot_bi_bo_van_duoc_ghi_so_ngan_sach(clock):
    """Bản ainvoke của test_luot_bi_bo_van_duoc_ghi_so_ngan_sach."""
    store = InMemoryUsageStore()
    ledger = BudgetLedger(store, clock=clock)
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = Router(ledger, client_factory=lambda spec, api_key=None: {
        "gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot}[spec.alias])

    await r.ainvoke("router", MSGS)

    assert store.usage_since(since=clock(),
                             alias="gemini-3.1-flash-lite").total_tokens == 2406
    assert store.usage_since(since=clock(),
                             alias="groq-gpt-oss-120b").total_tokens == 800


async def test_ainvoke_phan_hoi_rong_KHONG_dat_cooldown(clock):
    """Bản ainvoke của test_phan_hoi_rong_KHONG_dat_cooldown."""
    rong = FakeChatClient([fake_ai_rong(), fake_ai("intent: erp_read")])
    tot = FakeChatClient([fake_ai("intent: erp_write")])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    await r.ainvoke("router", MSGS)          # lượt 1: rỗng → tụt
    got = await r.ainvoke("router", MSGS)    # lượt 2: mắt xích 1 PHẢI được thử lại

    assert len(rong.calls) == 2
    assert got.decision.spec.alias == "gemini-3.1-flash-lite"
    assert got.message.content == "intent: erp_read"


def test_resolve_can_chuoi_giua_chung_van_tra_ket_qua_rong_KHONG_nem(clock):
    """C1: self.resolve(...) nằm NGOÀI try/except. Mắt xích 1 (rỗng) đã bị
    thêm vào skip cho lượt kế; nếu mắt xích 2 đang cooldown thì resolve() gọi
    lại sẽ cạn TOÀN BỘ chuỗi 2 mắt xích của vai fusion và ném ChainExhausted
    NGAY ĐẦU vòng lặp — TRƯỚC khi chạm nhánh `if last_empty is not None`.
    Kết quả rỗng đang cầm trong tay bị vứt, hàm ném ra ngoài thay vì trả về."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(ledger, client_factory=lambda spec, api_key=None: rong)
    ledger.cooldown(spec_for("groq-gpt-oss-120b"), 60.0)

    got = r.invoke("fusion", MSGS)      # chuỗi fusion: gemini-3.1-flash-lite, groq-llama-3.3-70b

    assert got.message.content == ""    # KHÔNG ném


async def test_ainvoke_resolve_can_chuoi_giua_chung_van_tra_ket_qua_rong_KHONG_nem(clock):
    """Bản async của test C1 ngay trên — invoke()/ainvoke() là hai thân hàm
    riêng, phải chứng minh cả hai cùng bị bug và cùng được sửa."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    rong = FakeChatClient([fake_ai_rong()])
    r = Router(ledger, client_factory=lambda spec, api_key=None: rong)
    ledger.cooldown(spec_for("groq-gpt-oss-120b"), 60.0)

    got = await r.ainvoke("fusion", MSGS)

    assert got.message.content == ""    # KHÔNG ném


def test_can_chuoi_ngay_vong_dau_van_nem_nhu_cu(clock):
    """Đối chứng ÂM cho C1: bản vá bọc resolve() trong try/except, nhưng nó
    CHỈ được nuốt lỗi khi đang cầm một kết quả rỗng. Cạn chuỗi ngay vòng lặp
    ĐẦU (chưa gọi model lần nào) phải ném ra ngoài y như trước bản vá.

    PHẢI kiểm nội dung `skipped`, không chỉ kiểm loại exception: gỡ nhánh
    `if last_empty is None: raise` đi thì luồng rơi xuống `raise` ở CUỐI hàm
    và vẫn ném ĐÚNG loại ChainExhausted — chỉ khác là `skipped` rỗng vì
    `attempts` rỗng. Một test chỉ dùng pytest.raises(ChainExhausted) sẽ XANH
    với cả hai bản, tức không đo gì (đã thử phá và xác nhận)."""
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    khong_duoc_cham = FakeChatClient([fake_ai("SAI — không được gọi model")])
    r = Router(ledger, client_factory=lambda spec, api_key=None: khong_duoc_cham)
    for alias in CHAINS["router"]:
        ledger.cooldown(spec_for(alias), 60.0)

    with pytest.raises(ChainExhausted) as exc:
        r.invoke("router", MSGS)

    # Lỗi phải là lỗi THẬT từ resolve(), mang ĐỦ mắt xích và lý do — không
    # phải cái vỏ rỗng sinh ra ở cuối hàm (chuỗi tĩnh còn 2 từ 2026-08-21).
    assert [s.alias for s in exc.value.skipped] == list(CHAINS["router"])
    assert len(khong_duoc_cham.calls) == 0


async def test_ainvoke_can_chuoi_ngay_vong_dau_van_nem_nhu_cu(clock):
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)
    khong_duoc_cham = FakeChatClient([fake_ai("SAI — không được gọi model")])
    r = Router(ledger, client_factory=lambda spec, api_key=None: khong_duoc_cham)
    for alias in CHAINS["router"]:
        ledger.cooldown(spec_for(alias), 60.0)

    with pytest.raises(ChainExhausted) as exc:
        await r.ainvoke("router", MSGS)

    assert [s.alias for s in exc.value.skipped] == list(CHAINS["router"])
    assert len(khong_duoc_cham.calls) == 0


# ── discarded_tokens: chi phí THẬT của một lượt tụt mắt xích ──────────────────
# Sổ ngân sách đã đếm đủ từ đầu (test_luot_bi_bo_van_duoc_ghi_so_ngan_sach),
# nhưng InvokeResult.total_tokens chỉ mang lượt ĐƯỢC TRẢ VỀ — nên Langfuse
# báo một lượt router tốn 800 token trong khi thật sự tốn 2406+800.


def test_token_luot_bi_bo_vao_discarded_khong_vao_total(clock):
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    got = r.invoke("router", MSGS)

    # total_tokens giữ nguyên nghĩa "con số provider báo cho ĐÚNG lượt này" —
    # cộng gộp vào đây sẽ phá bất biến toàn dự án.
    assert got.total_tokens == 800
    assert got.discarded_tokens == 2406


def test_khong_tut_mat_xich_thi_discarded_bang_khong(clock):
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = _router(clock, {"gemini-3.1-flash-lite": tot})

    got = r.invoke("router", MSGS)

    assert got.discarded_tokens == 0


def test_moi_mat_xich_deu_rong_thi_khong_dem_hai_lan_luot_cuoi(clock):
    """Ca dễ sai nhất: khi cạn chuỗi vì rỗng, kết quả TRẢ VỀ chính là lượt
    rỗng cuối cùng. Token của nó đã nằm ở total_tokens, cộng thêm vào
    discarded là đếm hai lần đúng một lượt gọi."""
    rong1 = FakeChatClient([fake_ai_rong(total=2406)])
    rong2 = FakeChatClient([fake_ai_rong(total=1500)])
    r = _router(clock, {"gemini-3.1-flash-lite": rong1,
                        "groq-gpt-oss-120b": rong2})

    got = r.invoke("fusion", MSGS)    # chuỗi fusion chỉ có 2 mắt xích

    assert got.total_tokens == 1500        # lượt cuối, được trả về
    assert got.discarded_tokens == 2406    # CHỈ lượt đầu
    assert got.total_tokens + got.discarded_tokens == 3906


async def test_ainvoke_cung_dem_discarded(clock):
    """invoke và ainvoke là HAI thân hàm riêng — đường async mới là đường
    production, và lớp lỗi 'sửa một quên một' đã xảy ra thật ở file này."""
    rong = FakeChatClient([fake_ai_rong(total=2406)])
    tot = FakeChatClient([fake_ai("ok", total=800)])
    r = _router(clock, {"gemini-3.1-flash-lite": rong, "groq-gpt-oss-120b": tot})

    got = await r.ainvoke("router", MSGS)

    assert got.total_tokens == 800
    assert got.discarded_tokens == 2406


async def test_ainvoke_moi_mat_xich_deu_rong_khong_dem_hai_lan(clock):
    rong1 = FakeChatClient([fake_ai_rong(total=2406)])
    rong2 = FakeChatClient([fake_ai_rong(total=1500)])
    r = _router(clock, {"gemini-3.1-flash-lite": rong1,
                        "groq-gpt-oss-120b": rong2})

    got = await r.ainvoke("fusion", MSGS)

    assert got.total_tokens == 1500
    assert got.discarded_tokens == 2406
