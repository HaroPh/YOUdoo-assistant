import pytest

from src.llm.budget import BudgetLedger, Verdict
from src.llm.catalog import spec_for
from src.llm.router import ChainExhausted, RouteDecision, Router, SkippedLink
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
    assert got.spec.alias == "gemini-3.5-flash-lite"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_mat_xich_dau_can_thi_tut_xuong_cai_ke(clock):
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)      # rpd = 500
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-llama-3.3-70b"
    assert got.fallback_depth == 1
    assert got.skipped == (
        SkippedLink(alias="gemini-3.5-flash-lite", verdict=Verdict.RPD),)


def test_tut_qua_hai_mat_xich(clock):
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)
    _fill(r, "groq-llama-3.3-70b", 1_000)
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "or-nemotron"
    assert got.fallback_depth == 2
    assert [s.alias for s in got.skipped] == [
        "gemini-3.5-flash-lite", "groq-llama-3.3-70b"]


def test_can_ca_chuoi_thi_nem_ChainExhausted_kem_ly_do_tung_mat_xich(clock):
    r = _router(clock)
    _fill(r, "gemini-3.1-flash-lite", 500)
    _fill(r, "groq-llama-3.3-70b", 1_000)
    with pytest.raises(ChainExhausted) as err:
        r.resolve("fusion", base_tokens=100)      # chuỗi fusion chỉ có 2 mắt
    assert [s.alias for s in err.value.skipped] == [
        "gemini-3.1-flash-lite", "groq-llama-3.3-70b"]
    assert all(s.verdict is Verdict.RPD for s in err.value.skipped)


def test_cooldown_cung_lam_tut_mat_xich(clock):
    r = _router(clock)
    r._ledger.cooldown(spec_for("gemini-3.5-flash-lite"), seconds=30)
    got = r.resolve("read", base_tokens=100)
    assert got.spec.alias == "groq-llama-3.3-70b"
    assert got.skipped[0].verdict is Verdict.COOLDOWN


def test_ghim_bo_qua_toan_bo_chuoi(clock):
    """Eval phải đo MỘT MODEL, không đo một trạng thái ngân sách."""
    r = _router(clock)
    got = r.resolve("read", base_tokens=100, pin="or-nemotron")
    assert got.spec.alias == "or-nemotron"
    assert got.fallback_depth == 0
    assert got.skipped == ()


def test_ghim_van_chon_dung_model_ke_ca_khi_no_da_can(clock):
    """Ghim là ghim. Ngân sách cạn thì để lượt gọi ăn 429 thật, chứ tụt sang
    model khác sẽ làm hỏng phép đo mà không báo gì."""
    r = _router(clock)
    _fill(r, "or-nemotron", 50)
    got = r.resolve("read", base_tokens=100, pin="or-nemotron")
    assert got.spec.alias == "or-nemotron"


def test_ghim_alias_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("read", base_tokens=100, pin="model-ma")


def test_vai_khong_ton_tai_thi_nem_KeyError(clock):
    with pytest.raises(KeyError):
        _router(clock).resolve("vai-khong-co", base_tokens=100)


def test_RouteDecision_mang_du_thuoc_tinh_cho_span_langfuse(clock):
    """Kế hoạch C đổ đúng các trường này vào span Langfuse."""
    r = _router(clock)
    _fill(r, "gemini-3.5-flash-lite", 500)
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
