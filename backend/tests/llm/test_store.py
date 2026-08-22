from datetime import datetime, timedelta, timezone

import pytest

from src.llm.store import InMemoryUsageStore, Usage

T0 = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def _record(store, ts, alias="a1", provider="p1", upstream="u1",
            prompt=10, completion=20, total=30):
    store.record(ts=ts, alias=alias, provider=provider, upstream=upstream,
                 prompt_tokens=prompt, completion_tokens=completion,
                 total_tokens=total)


def test_kho_rong_tra_ve_khong():
    store = InMemoryUsageStore()
    assert store.usage_since(since=T0, alias="a1") == Usage(requests=0,
                                                            total_tokens=0)


def test_dem_dung_so_luot_va_tong_token_theo_alias():
    store = InMemoryUsageStore()
    _record(store, T0, total=30)
    _record(store, T0 + timedelta(seconds=1), total=70)
    assert store.usage_since(since=T0 - timedelta(minutes=1), alias="a1") == \
        Usage(requests=2, total_tokens=100)


def test_loc_theo_alias_bo_qua_alias_khac():
    store = InMemoryUsageStore()
    _record(store, T0, alias="a1", total=30)
    _record(store, T0, alias="a2", total=500)
    got = store.usage_since(since=T0 - timedelta(minutes=1), alias="a1")
    assert got == Usage(requests=1, total_tokens=30)


def test_loc_theo_provider_gop_moi_alias_cua_provider_do():
    """OpenRouter dùng quota_scope="account" — mọi model free chung một ví."""
    store = InMemoryUsageStore()
    _record(store, T0, alias="or-ling", provider="openrouter", total=30)
    _record(store, T0, alias="or-nemotron", provider="openrouter", total=70)
    _record(store, T0, alias="gemini-3.1-flash-lite", provider="google", total=999)
    got = store.usage_since(since=T0 - timedelta(minutes=1),
                            provider="openrouter")
    assert got == Usage(requests=2, total_tokens=100)


def test_moc_since_loai_ban_ghi_cu_hon():
    store = InMemoryUsageStore()
    _record(store, T0 - timedelta(hours=25), total=999)   # ngoài cửa sổ 24h
    _record(store, T0 - timedelta(hours=1), total=50)     # trong cửa sổ
    got = store.usage_since(since=T0 - timedelta(hours=24), alias="a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_moc_since_la_bien_dong_ban_ghi_dung_bang_since_duoc_tinh():
    store = InMemoryUsageStore()
    _record(store, T0, total=50)
    got = store.usage_since(since=T0, alias="a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_tong_dung_total_tokens_khong_phai_prompt_cong_completion():
    """Gemma trả p=11, c=36 nhưng total=337 (~290 token thinking vô hình).
    Cộng p+c đếm thiếu 7 lần — sổ báo còn hạn mức trong khi ví đã cạn."""
    store = InMemoryUsageStore()
    _record(store, T0, prompt=11, completion=36, total=337)
    got = store.usage_since(since=T0 - timedelta(minutes=1), alias="a1")
    assert got.total_tokens == 337


def test_phai_dua_dung_mot_trong_hai_alias_hoac_provider():
    store = InMemoryUsageStore()
    with pytest.raises(ValueError):
        store.usage_since(since=T0)
    with pytest.raises(ValueError):
        store.usage_since(since=T0, alias="a1", provider="p1")


def test_postgres_store_dung_pool_voi_timeout_ngan(monkeypatch):
    """Blocker #1: pool không có timeout → chặn ~90s trước khi fail-open.
    Xác nhận cấu hình timeout ngắn thật sự được truyền xuống ConnectionPool,
    không chỉ "đã sửa" trong lời commit."""
    calls = []

    class FakePool:
        def __init__(self, dsn, **kwargs):
            calls.append(kwargs)
            self._dsn = dsn

        def connection(self):
            import contextlib

            class _Conn:
                def execute(self, *a, **k):
                    return None
            @contextlib.contextmanager
            def _cm():
                yield _Conn()
            return _cm()

    monkeypatch.setattr("psycopg_pool.ConnectionPool", FakePool)
    from src.llm.store import PostgresUsageStore
    PostgresUsageStore(dsn="postgresql://fake/db")
    assert len(calls) == 1
    assert calls[0]["timeout"] <= 3.0
    assert calls[0]["kwargs"]["connect_timeout"] <= 3
