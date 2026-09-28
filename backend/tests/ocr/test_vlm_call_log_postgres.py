"""Test tích hợp `PostgresVlmCallLog` — cần Postgres đang chạy.

Chạy:  pytest tests/ocr/test_vlm_call_log_postgres.py -m integration -v

Schema RIÊNG, dựng từ chính migration 010 rồi xoá — KHÔNG chạm
`public.vlm_call_log` (cùng lý do `tests/llm/test_store_postgres.py`: test từng
xoá sạch sổ ngân sách thật).
"""
import os
from datetime import datetime, timezone

import pytest

from src.ocr.call_log import PostgresVlmCallLog

pytestmark = pytest.mark.integration

_DSN_THAT = os.environ.get("DATABASE_URL")
SCHEMA_THU = "thu_vlm_call_log"
DSN = (None if not _DSN_THAT else
       _DSN_THAT + ("&" if "?" in _DSN_THAT else "?")
       + f"options=-csearch_path%3D{SCHEMA_THU}")


@pytest.fixture(scope="module", autouse=True)
def _schema_rieng():
    if not _DSN_THAT:
        yield
        return
    import psycopg
    with psycopg.connect(_DSN_THAT, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_THU}")
    with open("migrations/010_vlm_call_log.sql", encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(sql)
    yield
    with psycopg.connect(_DSN_THAT, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_THU} CASCADE")


def _row(**over):
    row = dict(ts=datetime.now(timezone.utc), source="DVT_2022.pdf", page=7,
               mode="bang_chi_tieu", model="vlm-test", prompt_version="v1",
               key_index=0, outcome="ok", latency_ms=1234, prompt_tokens=1200,
               completion_tokens=300, total_tokens=1500, error=None)
    row.update(over)
    return row


def test_ghi_roi_doc_lai_du_cot_ca_luot_loi():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    log = PostgresVlmCallLog(DSN)
    try:
        log.record(**_row())
        log.record(**_row(outcome="rate_limited", key_index=1, prompt_tokens=None,
                          completion_tokens=None, total_tokens=None,
                          error="_Loi429: 429 RESOURCE_EXHAUSTED"))
        with log._pool.connection() as conn:
            rows = conn.execute("SELECT outcome, key_index, total_tokens, error, source, page "
                                "FROM vlm_call_log ORDER BY id").fetchall()
    finally:
        log.close()
    assert rows == [("ok", 0, 1500, None, "DVT_2022.pdf", 7),
                    ("rate_limited", 1, None, "_Loi429: 429 RESOURCE_EXHAUSTED", "DVT_2022.pdf", 7)]


def test_outcome_la_bi_CHECK_chan():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    import psycopg
    log = PostgresVlmCallLog(DSN)
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            log.record(**_row(outcome="thanh_cong"))
    finally:
        log.close()


def test_thieu_migration_thi_no_ro_rang_luc_dung():
    if not _DSN_THAT:
        pytest.skip("chưa đặt DATABASE_URL")
    import psycopg
    trong = "thu_vlm_call_log_trong"
    with psycopg.connect(_DSN_THAT, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {trong}")
    try:
        dsn = (_DSN_THAT + ("&" if "?" in _DSN_THAT else "?")
               + f"options=-csearch_path%3D{trong}")
        with pytest.raises(RuntimeError, match="010_vlm_call_log"):
            PostgresVlmCallLog(dsn)
    finally:
        with psycopg.connect(_DSN_THAT, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {trong} CASCADE")
