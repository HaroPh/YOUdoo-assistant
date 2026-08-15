"""Postgres logging cho mọi lệnh gọi MCP (spec 2026-07-13-mcp-server-
modularization). Port pattern log_event từ mcp_log.py. Mỗi dòng ghi kèm
hash-chain (audit_chain.compute_entry_hash) để phát hiện sửa/xoá dòng sau
khi ghi — xem docs/superpowers/specs/2026-07-23-audit-trail-hash-chain-
design.md."""
import threading
from datetime import datetime, timezone

import audit_chain
from config import DATABASE_URL

MAX_TEXT = 10_000
_db_conn = None
_db_lock = threading.Lock()

def _truncate(text: str | None) -> str | None:
    if text and len(text) > MAX_TEXT:
        return text[:MAX_TEXT] + "... [truncated]"
    return text

def _get_db():
    """Lazy connection, reconnect khi lỗi. None nếu không cấu hình DATABASE_URL."""
    global _db_conn
    if not DATABASE_URL:
        return None
    if _db_conn is None or getattr(_db_conn, "closed", 1):
        import psycopg2
        _db_conn = psycopg2.connect(DATABASE_URL)
        _db_conn.autocommit = True
    return _db_conn

def assert_log_table_ready() -> None:
    """Fail-loud khi có DSN mà thiếu bảng — gọi MỘT LẦN lúc khởi động.

    Vì sao cần: log_mcp_event nuốt MỌI lỗi ghi (đúng — log không được làm
    hỏng tool), nên thiếu bảng là trạng thái hoàn toàn im lặng. Đo 2026-08-14:
    mcp_call_log chưa từng tồn tại và không ai biết, suốt từ ngày port.

    Không có DATABASE_URL ⇒ trả về ngay: "không cấu hình = tắt log" là thiết
    kế có chủ ý của module này, không phải lỗi.
    """
    if not DATABASE_URL:
        return
    conn = _get_db()
    if conn is None:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.mcp_call_log') IS NOT NULL")
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "Thiếu bảng mcp_call_log — vệt kiểm toán MCP sẽ im lặng không "
                "ghi gì. Chạy backend/migrations/002_mcp_call_log.sql trên "
                "database ở DATABASE_URL rồi khởi động lại.")

def log_mcp_event(event_type: str, *, tool_name=None, model_name=None,
                  operation=None, duration_ms=None, error_code=None,
                  error_message=None, caller="mcp-odoo") -> None:
    """Ghi mcp_call_log kèm hash-chain. Mọi lỗi log đều nuốt — KHÔNG được
    làm hỏng tool."""
    global _db_conn
    try:
        with _db_lock:
            conn = _get_db()
            if conn is None:
                return
            with conn.cursor() as cur:
                cur.execute("SELECT entry_hash FROM mcp_call_log "
                           "ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
                prev_hash = row[0] if row and row[0] else audit_chain.GENESIS_HASH

                now = datetime.now(timezone.utc)
                truncated_error = _truncate(error_message)
                entry_hash = audit_chain.compute_entry_hash(
                    prev_hash, now, event_type, caller, tool_name, model_name,
                    operation, duration_ms, error_code, truncated_error)

                cur.execute("""
                    INSERT INTO mcp_call_log
                    (event_type, caller, tool_name, model_name, operation,
                     duration_ms, error_code, error_message, created_at,
                     entry_hash, prev_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (event_type, caller, tool_name, model_name, operation,
                      duration_ms, error_code, truncated_error, now,
                      entry_hash, prev_hash))
    except Exception:
        _db_conn = None   # ép reconnect lần sau
