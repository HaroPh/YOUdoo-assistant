# backend/tests/rag/test_migration_009_contract.py
"""DOC_VISIBILITY xuất hiện HAI chỗ (Python + SQL migration 009). Hai nguồn
không được trôi: bốn basename trong SQL == bốn khoá Python."""
import pathlib
import re

from src.rag.visibility import DOC_VISIBILITY

MIGRATION = (pathlib.Path(__file__).resolve().parents[2]
             / "migrations" / "009_rag_visibility_backfill.sql")


def test_bon_basename_trong_sql_bang_dung_DOC_VISIBILITY():
    sql = MIGRATION.read_text(encoding="utf-8")
    trong_sql = set(re.findall(r"LIKE '%([^']+)'", sql))
    # Bỏ mẫu gỡ SID — không phải nhãn lớp
    trong_sql = {b for b in trong_sql if "BaoCaoTaiChinh" not in b}
    assert trong_sql == set(DOC_VISIBILITY), (trong_sql, set(DOC_VISIBILITY))


def test_migration_go_SID_va_idempotent_theo_van_ban():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "BaoCaoTaiChinhBanNien" in sql
    assert "visibility <> 'commercial'" in sql, "UPDATE phải có điều kiện để chạy lại vô hại"
    assert "RAISE NOTICE" in sql, "lượt chạy tay phải để lại bằng chứng số dòng"
