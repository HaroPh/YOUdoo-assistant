import pytest
from langchain_core.messages import AIMessage

from src.llm.budget import BudgetLedger, Verdict
from src.llm.catalog import CHAINS, spec_for
from src.llm.router import (ChainExhausted, RouteDecision, Router, SkippedLink,
                            _usable)
from src.llm.store import InMemoryUsageStore


def _router(clock, store=None):
    return Router(BudgetLedger(store or InMemoryUsageStore(), clock=clock))


def _fill(router, alias, n, total_tokens=1):
    spec = spec_for(alias)
    for _ in range(n):
        router._ledger.record(spec, prompt_tokens=1, completion_tokens=1,
                              total_tokens=total_tokens)


def test_so_sach_trong_thi_chon_mat_xich_dau_tien(clock):
    got = _router(clock).resolve("read", base_tokens=100)
    assert got.spec.alias == "gemini-3.1-flash-lite"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_mat_xich_dau_can_thi_tut_xuong_cai_ke(clock):
    r = _router(clock)
    _fill(r, "gemini-3.1-flash-lite", 500)      # rpd = 500
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-gpt-oss-120b"
    assert got.fallback_depth == 1
    assert got.skipped == (
        SkippedLink(alias="gemini-3.1-flash-lite", verdict=Verdict.RPD),)


def test_tut_qua_hai_mat_xich(clock):
    """Cần chuỗi BA mắt xích. Từ 2026-08-21 chuỗi tĩnh chỉ có hai, mắt xích thứ
    ba do `prefer` chèn vào (mục 8) — nên test đặt lựa chọn của người dùng thay
    vì dựa vào một chuỗi dài sẵn."""
    from src.llm.catalog import MODEL_NGUOI_DUNG_CHON
    token = MODEL_NGUOI_DUNG_CHON.set("gemini-3.5-flash-lite")
    try:
        r = _router(clock)
        _fill(r, "gemini-3.5-flash-lite", 500)
        _fill(r, "gemini-3.1-flash-lite", 500)
        got = r.resolve("read", base_tokens=100)
        assert got.spec.alias == "groq-gpt-oss-120b"
        assert got.fallback_depth == 2
        assert [s.alias for s in got.skipped] == [
            "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    finally:
        MODEL_NGUOI_DUNG_CHON.reset(token)


def test_can_ca_chuoi_thi_nem_ChainExhausted_kem_ly_do_tung_mat_xich(clock):
    """Vắt cạn rpd của MỌI mắt xích, lấy danh sách từ CHAINS chứ không gõ tay.

    Bản cũ gõ tay hai alias kèm chú thích "chuỗi fusion chỉ có 2 mắt xích".
    Chuỗi đã đổi độ dài HAI LẦN trong hai ngày (gom catalog 2026-08-21 bỏ
    OpenRouter, rồi 2026-08-22 khôi phục `or-nemotron` vì Groq trả 413 cho vai
    có tool). Mỗi lần đổi, một test gõ tay hoặc đỏ oan hoặc — tệ hơn — xanh giả
    vì nó chỉ còn kiểm một phần chuỗi.
    """
    r = _router(clock)
    chuoi = CHAINS["fusion"]
    for alias in chuoi:
        _fill(r, alias, spec_for(alias).rpd)
    with pytest.raises(ChainExhausted) as err:
        r.resolve("fusion", base_tokens=100)
    assert [s.alias for s in err.value.skipped] == list(chuoi)
    assert all(s.verdict is Verdict.RPD for s in err.value.skipped)


def test_cooldown_cung_lam_tut_mat_xich(clock):
    r = _router(clock)
    r._ledger.cooldown(spec_for("gemini-3.1-flash-lite"), seconds=30)
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-gpt-oss-120b"
    assert got.skipped[0].verdict is Verdict.COOLDOWN


def test_ghim_bo_qua_toan_bo_chuoi(clock):
    """Eval phải đo MỘT MODEL, không đo một trạng thái ngân sách."""
    r = _router(clock)
    got = r.resolve("read", base_tokens=100, pin="groq-gpt-oss-120b")
    assert got.spec.alias == "groq-gpt-oss-120b"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_ghim_van_chon_dung_model_ke_ca_khi_no_da_can(clock):
    """Ghim là ghim. Ngân sách cạn thì để lượt gọi ăn 429 thật, chứ tụt sang
    model khác sẽ làm hỏng phép đo mà không báo gì."""
    r = _router(clock)
    _fill(r, "groq-gpt-oss-120b", 1_000)
    got = r.resolve("read", base_tokens=100, pin="groq-gpt-oss-120b")
    assert got.spec.alias == "groq-gpt-oss-120b"


def test_ghim_alias_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("read", base_tokens=100, pin="model-ma")


def test_vai_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("vai-khong-co", base_tokens=100)


def test_RouteDecision_mang_du_thuoc_tinh_cho_span_langfuse(clock):
    """Kế hoạch C đổ đúng các trường này vào span Langfuse."""
    r = _router(clock)
    _fill(r, "gemini-3.1-flash-lite", 500)
    got = r.resolve("read", base_tokens=250)
    assert isinstance(got, RouteDecision)
    assert got.role == "read"
    assert got.base_tokens == 250
    assert got.spec.provider == "groq"
    assert got.spec.upstream == "groq"
    assert got.fallback_depth == 1
    assert got.skipped[0].verdict.value == "rpd_exhausted"


def test_moi_vai_deu_giai_quyet_duoc_khi_so_sach_trong(clock):
    from src.llm.catalog import ROLES
    r = _router(clock)
    for role in ROLES:
        assert r.resolve(role, base_tokens=10).fallback_depth == 0


def test_resolve_bo_qua_mat_xich_trong_skip(clock):
    """skip là cục bộ trong MỘT lượt gọi — không phải cooldown, không có tác
    dụng phụ sang request sau."""
    got = _router(clock).resolve("router", base_tokens=100,
                                 skip=frozenset({"gemini-3.1-flash-lite"}))

    assert got.spec.alias == "groq-gpt-oss-120b"
    assert got.fallback_depth == 1
    assert [(s.alias, s.verdict) for s in got.skipped] == [
        ("gemini-3.1-flash-lite", Verdict.EMPTY)]


def test_resolve_khong_truyen_skip_thi_khong_doi_gi(clock):
    assert _router(clock).resolve(
        "router", base_tokens=100).spec.alias == "gemini-3.1-flash-lite"


def test_resolve_skip_het_chuoi_thi_nem_ChainExhausted(clock):
    """Skip lấy thẳng từ CHAINS.

    Bản cũ gõ tay ba alias, một trong đó là `or-ling` — model đã bị XOÁ khỏi
    catalog ngày 2026-08-21. Test vẫn xanh, vì skip một alias không tồn tại là
    vô hại và hai alias còn lại tình cờ phủ trọn chuỗi. Đó là một danh sách gõ
    tay đã trôi khỏi sự thật mà không cổng nào báo.
    """
    with pytest.raises(ChainExhausted):
        _router(clock).resolve("router", base_tokens=100,
                               skip=frozenset(CHAINS["router"]))


def test_usable_content_co_chu_thi_dung_duoc():
    assert _usable(AIMessage(content="intent: erp_write")) is True


def test_usable_content_rong_khong_tool_call_thi_khong_dung_duoc():
    assert _usable(AIMessage(content="")) is False
    assert _usable(AIMessage(content="   \n  ")) is False


def test_usable_tool_call_co_content_rong_VAN_dung_duoc():
    """Đo 2026-08-13: một lượt gọi tool THÀNH CÔNG cũng có content rỗng —
    cả gemini-3.5-flash-lite lẫn gemma-4-26b trả content='' + 1 tool_call cho
    câu hỏi tồn kho, finish_reason=STOP. Bỏ vế tool_calls sẽ làm hỏng
    erp_read, gather_erp, erp_write_planner và mọi node SOP."""
    msg = AIMessage(content="",
                    tool_calls=[{"name": "get_stock", "args": {}, "id": "c1"}])
    assert _usable(msg) is True
