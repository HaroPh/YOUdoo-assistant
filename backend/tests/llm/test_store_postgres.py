"""Test tích hợp — cần Postgres đang chạy.

Chạy:  pytest tests/llm/test_store_postgres.py -m integration -v
Bỏ:    pytest -m "not integration"
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.llm.store import PostgresUsageStore, Usage

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")


@pytest.fixture
def store():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    s = PostgresUsageStore(DSN)
    with s._pool.connection() as conn:          # dọn sạch trước mỗi test
        conn.execute("DELETE FROM llm_usage WHERE alias LIKE 'test-%'")
    yield s
    s.close()


def _rec(store, ts, alias="test-a1", provider="test-p1", total=30):
    store.record(ts=ts, alias=alias, provider=provider, upstream="test-u1",
                 prompt_tokens=10, completion_tokens=20, total_tokens=total)


def test_ghi_roi_doc_lai_dung_so(store):
    now = datetime.now(timezone.utc)
    _rec(store, now, total=30)
    _rec(store, now, total=70)
    got = store.usage_since(since=now - timedelta(minutes=1), alias="test-a1")
    assert got == Usage(requests=2, total_tokens=100)


def test_khong_co_gi_thi_tra_ve_khong_chu_khong_phai_None(store):
    now = datetime.now(timezone.utc)
    got = store.usage_since(since=now, alias="test-khong-ton-tai")
    assert got == Usage(requests=0, total_tokens=0)


def test_loc_theo_provider_gop_moi_alias(store):
    now = datetime.now(timezone.utc)
    _rec(store, now, alias="test-a1", provider="test-or", total=30)
    _rec(store, now, alias="test-a2", provider="test-or", total=70)
    got = store.usage_since(since=now - timedelta(minutes=1),
                            provider="test-or")
    assert got == Usage(requests=2, total_tokens=100)


def test_moc_since_loai_ban_ghi_ngoai_cua_so(store):
    now = datetime.now(timezone.utc)
    _rec(store, now - timedelta(hours=25), total=999)
    _rec(store, now - timedelta(hours=1), total=50)
    got = store.usage_since(since=now - timedelta(hours=24), alias="test-a1")
    assert got == Usage(requests=1, total_tokens=50)


def test_phai_dua_dung_mot_trong_hai_alias_hoac_provider(store):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        store.usage_since(since=now)
    with pytest.raises(ValueError):
        store.usage_since(since=now, alias="a", provider="p")


# ─── Fail-loud khi thiếu migration (review toàn nhánh, không phải task riêng) ─
#
# DSN riêng, KHÔNG dùng fixture `store` ở trên: fixture đó giả định bảng
# llm_usage đã tồn tại (nó DELETE khỏi bảng đó trước mỗi test). Hai test dưới
# đây cần một database KHÔNG có bảng — phải tự cầm DSN của DATABASE_URL và tự
# quyết định lúc nào bảng có/không có, không đi qua fixture.

def _skip_neu_thieu_dsn() -> None:
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")


def test_thieu_migration_thi_nem_RuntimeError_ro_rang():
    """Không có bảng llm_usage → dựng PostgresUsageStore phải chết NGAY tại
    __init__, không đợi tới lượt record()/usage_since() đầu tiên — đó chính là
    lỗ hổng mà review toàn nhánh bắt được: BudgetLedger fail-open trên bất kỳ
    exception nào từ store, nên nếu lỗi "thiếu bảng" chỉ nổi lên muộn (hoặc
    không nổi lên loud), quên chạy migration sẽ lặng lẽ tắt vĩnh viễn việc
    kiểm ngân sách."""
    _skip_neu_thieu_dsn()
    import psycopg
    # Xoá bảng nếu có, để chắc chắn đang test đúng kịch bản "chưa migrate".
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS llm_usage")
    try:
        with pytest.raises(RuntimeError, match="llm_usage"):
            PostgresUsageStore(DSN)
    finally:
        # Dựng lại bảng để không làm hỏng các test khác chạy sau trong cùng
        # tiến trình (fixture `store` ở trên giả định bảng đã tồn tại).
        with open("migrations/001_llm_usage.sql", encoding="utf-8") as f:
            sql = f.read()
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql)


def test_co_migration_thi_van_dung_binh_thuong():
    """Đối chứng: bảng đã tồn tại → constructor không được ném gì cả, và store
    vẫn hoạt động y như trước khi thêm cú kiểm fail-loud này."""
    _skip_neu_thieu_dsn()
    import psycopg
    with open("migrations/001_llm_usage.sql", encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(sql)   # idempotent (CREATE TABLE IF NOT EXISTS)

    s = PostgresUsageStore(DSN)
    try:
        now = datetime.now(timezone.utc)
        _rec(s, now, alias="test-fail-loud", total=42)
        got = s.usage_since(since=now - timedelta(minutes=1),
                            alias="test-fail-loud")
        assert got == Usage(requests=1, total_tokens=42)
    finally:
        with s._pool.connection() as conn:
            conn.execute("DELETE FROM llm_usage WHERE alias = 'test-fail-loud'")
        s.close()
