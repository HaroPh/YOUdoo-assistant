"""Postgres logging cho mọi lệnh gọi MCP (spec 2026-07-13-mcp-server-
modularization). Port pattern log_event từ mcp_log.py. Mỗi dòng ghi kèm
hash-chain (audit_chain.compute_entry_hash) để phát hiện sửa/xoá dòng sau
khi ghi — xem docs/superpowers/specs/2026-07-23-audit-trail-hash-chain-
design.md."""
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import audit_chain
from config import DATABASE_URL, ODOO_USER

logger = logging.getLogger(__name__)

MAX_TEXT = 10_000
_db_conn = None
_db_lock = threading.Lock()

# Nhãn mặc định của bên ghi. KHÔNG được là hằng "mcp-odoo": start-dev.ps1
# chạy BA tiến trình MCP (ai-admin / ai-warehouse / ai-accounting) cùng ghi
# vào MỘT bảng, nên một hằng chung khiến mọi dòng permission_denied trả lời
# được "có chuyện gì bị từ chối" mà không trả lời được "AI nào" — trong khi
# cách ly theo vai chính là biện pháp an ninh chính của hệ thống.
DEFAULT_CALLER = f"mcp-odoo/{ODOO_USER}"

# Khoá advisory dùng chung cho MỌI tiến trình ghi mcp_call_log. Xem
# docstring log_mcp_event: _db_lock chỉ là threading.Lock, tức chỉ serialise
# TRONG một tiến trình. Hằng số phải giống hệt nhau ở mọi tiến trình mới có
# tác dụng — đừng suy ra từ biến môi trường nào.
CHAIN_LOCK_KEY = 20260814

# Tên header mang danh tính người dùng HTTP từ backend sang tiến trình MCP.
# PHẢI khớp `HEADER_NGUOI_DUNG` trong backend/src/agents/erp_agent.py — hai
# tiến trình khác nhau, không nhập chung được hằng số, nên
# backend/tests/mcp/test_audit_http_user.py đối chiếu hai chuỗi này.
HEADER_NGUOI_DUNG = "x-youdoo-user"

# Trần độ dài: header đến từ ngoài, và không có lý do gì để một id người dùng
# dài hơn thế. Cắt thay vì từ chối — vệt kiểm toán ghi được thứ méo còn hơn
# không ghi gì.
HTTP_USER_MAX = 200

# Retry kết nối lúc khởi động (assert_log_table_ready). start-dev.ps1 chạy
# `docker compose up -d` rồi đi thẳng vào vòng khởi động MCP; lệnh đó trả về
# khi container đã ĐƯỢC TẠO, không phải khi Postgres đã nhận kết nối.
CONNECT_RETRIES = 5
CONNECT_BACKOFF = 0.5      # giây; nhân đôi mỗi lần ⇒ tổng ≈ 7.5s


def _http_user() -> str | None:
    """Id người dùng HTTP của lượt gọi hiện tại, lấy từ header do backend gắn.

    Vì sao phải qua header: ba tiến trình MCP nắm credential Odoo của BA VAI,
    nên `caller` chỉ nói được "AI vai nào" — nó KHÔNG nói được ai đã yêu cầu.
    Sau một sự cố, đó đúng là câu hỏi đầu tiên.

    Đọc `request_ctx` — ContextVar cấp module của mcp.server.lowlevel.server —
    chứ KHÔNG nhập `server.py`: server.py nhập các module tool, các module đó
    nhập odoo_call, odoo_call nhập chính module này. Nhập ngược lại là vòng.

    Trả None ngoài ngữ cảnh request (test, khởi động, tác vụ nền). Nuốt mọi
    lỗi: một vệt kiểm toán không được là thứ làm hỏng tool.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
        ctx = request_ctx.get(None)
        req = getattr(ctx, "request", None) if ctx is not None else None
        if req is None:
            return None
        gia_tri = req.headers.get(HEADER_NGUOI_DUNG)
        return gia_tri[:HTTP_USER_MAX] if gia_tri else None
    except Exception:                                       # noqa: BLE001
        return None


def _truncate(text: str | None) -> str | None:
    if text and len(text) > MAX_TEXT:
        return text[:MAX_TEXT] + "... [truncated]"
    return text


def _dsn_target(dsn: str) -> str:
    """host:port/database từ DSN — KHÔNG bao giờ kèm mật khẩu.

    urlsplit tách sẵn hostname/port/path, nên không có đường nào để phần
    userinfo (chứa mật khẩu) lọt vào chuỗi trả về.
    """
    try:
        parts = urlsplit(dsn)
        return (f"{parts.hostname or '?'}:{parts.port or 5432}"
                f"/{(parts.path or '').lstrip('/') or '?'}")
    except Exception:                                       # noqa: BLE001
        return "?"


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


def _connect_with_retry():
    """Kết nối, thử lại có backoff. Ném RuntimeError nếu vẫn không tới được.

    Tách RÕ hai kiểu hỏng: "không tới được database" khác hẳn "tới được
    nhưng thiếu bảng". Trước bản này chỉ kiểu thứ hai có thông báo tử tế;
    kiểu thứ nhất ném thẳng psycopg2.OperationalError ra ngoài và giết tiến
    trình, trái với đúng những gì docs/getting-started.md hứa người vận hành
    sẽ thấy.
    """
    global _db_conn
    loi_cuoi = None
    for lan in range(CONNECT_RETRIES):
        try:
            return _get_db()
        except Exception as exc:                            # noqa: BLE001
            loi_cuoi = exc
            _db_conn = None
            if lan == CONNECT_RETRIES - 1:
                break
            time.sleep(CONNECT_BACKOFF * (2 ** lan))
    # Nguyên văn lỗi chỉ vào log tiến trình, không vào thông báo ném ra:
    # chuỗi lỗi của driver có thể mang theo nguyên cả DSN.
    logger.exception("không kết nối được Postgres cho vệt kiểm toán MCP")
    raise RuntimeError(
        f"Không kết nối được Postgres ({_dsn_target(DATABASE_URL)}) sau "
        f"{CONNECT_RETRIES} lần thử — vệt kiểm toán MCP không khởi động "
        f"được. Kiểm tra container youdoo-postgres đã lên chưa "
        f"(docker compose up -d) và DATABASE_URL trong .env. "
        f"Loại lỗi: {type(loi_cuoi).__name__}.") from None


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
    conn = _connect_with_retry()
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
                  error_message=None, caller=None, args_digest=None,
                  args_keys=None) -> None:
    """Ghi mcp_call_log kèm hash-chain. Mọi lỗi log đều nuốt — KHÔNG được
    làm hỏng tool.

    Đọc-tính-ghi phải là MỘT giao dịch có pg_advisory_xact_lock: hàm này đọc
    entry_hash của dòng cuối rồi mới INSERT dòng chained vào nó, và
    start-dev.ps1 chạy BA tiến trình MCP ghi chung một bảng. _db_lock là
    threading.Lock — chỉ serialise trong MỘT tiến trình — nên hai tiến trình
    đọc cùng một đỉnh chuỗi sẽ chained cùng một prev_hash, và
    verify_audit_chain báo "Chuỗi đứt tại id=N" trên dữ liệu không ai sửa.
    Khoá advisory được giữ tới hết giao dịch (xact), nên phải chạy với
    autocommit TẮT; bật lại ngay sau commit để mọi đường khác của module giữ
    nguyên hành vi cũ.
    """
    global _db_conn
    try:
        with _db_lock:
            conn = _get_db()
            if conn is None:
                return
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(%s)",
                                (CHAIN_LOCK_KEY,))
                    cur.execute("SELECT entry_hash FROM mcp_call_log "
                                "ORDER BY id DESC LIMIT 1")
                    row = cur.fetchone()
                    prev_hash = (row[0] if row and row[0]
                                 else audit_chain.GENESIS_HASH)

                    now = datetime.now(timezone.utc)
                    truncated_error = _truncate(error_message)
                    http_user = _http_user()
                    entry_hash = audit_chain.compute_entry_hash(
                        prev_hash, now, event_type, caller or DEFAULT_CALLER,
                        tool_name, model_name, operation, duration_ms,
                        error_code, truncated_error,
                        http_user, args_digest, args_keys)

                    cur.execute("""
                        INSERT INTO mcp_call_log
                        (event_type, caller, tool_name, model_name, operation,
                         duration_ms, error_code, error_message, created_at,
                         entry_hash, prev_hash, http_user, args_digest,
                         args_keys)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (event_type, caller or DEFAULT_CALLER, tool_name,
                          model_name, operation, duration_ms, error_code,
                          truncated_error, now, entry_hash, prev_hash,
                          http_user, args_digest,
                          list(args_keys) if args_keys else None))
                conn.commit()
            except Exception:                               # noqa: BLE001
                # Kết thúc giao dịch dở TRƯỚC khi ném tiếp — không được để
                # connection nằm lại ở trạng thái aborted cho lượt sau.
                # rollback() tự nó cũng có thể ném (connection đã chết);
                # nuốt, vì except bên ngoài sẽ vứt hẳn connection.
                try:
                    conn.rollback()
                except Exception:                           # noqa: BLE001
                    pass
                raise
            # Chỉ gán được khi KHÔNG còn giao dịch mở — nên nằm sau commit.
            conn.autocommit = True
    except Exception:                                       # noqa: BLE001
        _db_conn = None   # ép reconnect lần sau
