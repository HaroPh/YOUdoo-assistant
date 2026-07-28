import pytest

from src.llm.catalog import (CATALOG, CHAINS, HEAVY_ROLES, HEAVY_TPM_FLOOR,
                             ROLES, TOOL_ROLES, chain_for, spec_for)


def test_moi_alias_trong_chain_deu_ton_tai_trong_catalog():
    """Bất biến #2 — chuỗi trỏ tới alias lạ là lỗi cấu hình, phải chết sớm."""
    for role, aliases in CHAINS.items():
        for alias in aliases:
            assert alias in CATALOG, f"chuỗi {role!r} trỏ tới alias lạ: {alias!r}"


def test_khong_hai_mat_xich_nao_trong_mot_chuoi_chung_upstream():
    """Bất biến #1 — fallback phải vượt qua ranh giới miền lỗi thật.

    Đo 2026-07-28: google/gemma-4-31b-it:free trên OpenRouter trả 429 kèm
    provider_name "Google AI Studio" — nó proxy ngược về chính Google. Rơi từ
    Gemini xuống đó là rơi vào lại chỗ vừa ngã.
    """
    for role, aliases in CHAINS.items():
        upstreams = [CATALOG[a].upstream for a in aliases]
        assert len(upstreams) == len(set(upstreams)), (
            f"chuỗi {role!r} có hai mắt xích chung upstream: {upstreams}")


def test_vai_nang_chi_dung_model_du_tpm():
    """Bất biến #3 — một lượt synthesis có RAG tốn ~3–4K token input."""
    for role in HEAVY_ROLES:
        for spec in chain_for(role):
            assert spec.tpm is None or spec.tpm >= HEAVY_TPM_FLOOR, (
                f"{spec.alias!r} có tpm={spec.tpm} < {HEAVY_TPM_FLOOR}, "
                f"không gánh nổi vai nặng {role!r}")


def test_vai_can_tool_chi_dung_model_ho_tro_tool():
    """Bất biến #4 — vai gọi tool mà trúng model không tool-call thì hỏng câm."""
    for role in TOOL_ROLES:
        for spec in chain_for(role):
            assert spec.supports_tools, (
                f"{spec.alias!r} không hỗ trợ tool nhưng nằm trong chuỗi "
                f"của vai {role!r}")


def test_moi_vai_deu_co_chuoi_va_khong_co_chuoi_thua():
    assert set(CHAINS) == set(ROLES)


def test_khong_co_model_openrouter_nao_co_upstream_google():
    """Chốt cứng phát hiện 2026-07-28 ở tầng dữ liệu, không chỉ ở chuỗi."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.upstream != "google", (
                f"{spec.alias!r} proxy về Google — không được vào catalog")


def test_quota_scope_chi_nhan_hai_gia_tri_hop_le():
    for spec in CATALOG.values():
        assert spec.quota_scope in ("model", "account")


def test_openrouter_dung_quota_scope_account():
    """Hạn mức free của OpenRouter tính theo TÀI KHOẢN, dùng chung mọi model."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.quota_scope == "account"


def test_alias_khop_voi_khoa_trong_catalog():
    for key, spec in CATALOG.items():
        assert spec.alias == key


def test_spec_for_nem_loi_voi_alias_la():
    with pytest.raises(KeyError):
        spec_for("model-khong-ton-tai")


def test_chain_for_nem_loi_voi_vai_la():
    with pytest.raises(KeyError):
        chain_for("vai-khong-ton-tai")


def test_chain_for_tra_ve_dung_thu_tu():
    specs = chain_for("read")
    assert [s.alias for s in specs] == list(CHAINS["read"])
