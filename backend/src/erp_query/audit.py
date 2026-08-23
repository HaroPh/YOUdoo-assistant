"""Vệt kiểm toán cho ĐƯỜNG ĐỌC (mục 17b).

VÌ SAO Ở TẦNG TOOL, KHÔNG Ở `transport.call()`:
`Gateway._call()` là điểm thắt nút thật, nhưng nó chỉ biết `model` + `method`
— KHÔNG biết tên tool. Và một tool thường gọi gateway vài lượt (`sales.py` một
mình có 9 chỗ gọi), nên ghi ở đó sẽ ra nhiều dòng vô danh cho một hành động.
Bọc ở tầng tool cho **một dòng mỗi lời gọi tool**, kèm tên và tham số — đúng
đối xứng với cách đường GHI đang log ở `odoo_call.odoo()`.

VÌ SAO KHÔNG HASH-CHAIN:
  * `compute_entry_hash` sống ở cây `mcp-servers/odoo`, backend không dùng
    chung. Chain nghĩa là chép lại công thức băm (đặt một nguyên thủy an ninh
    ở hai nơi rồi chờ nó trôi) hoặc nhập chéo cây.
  * `verify_audit_chain` LỌC `WHERE entry_hash IS NOT NULL` — dòng không
    chained là **hợp lệ theo thiết kế**; dòng `chain_reset` của migration 005
    đang dùng đúng thế.
  * Chain lấy `pg_advisory_xact_lock` mỗi dòng. Đọc nhiều hơn ghi, nên mọi
    lượt đọc sẽ nối đuôi với mọi lượt ghi qua cả 6 tiến trình.
Muốn chain sau thì việc đúng là đưa `audit_chain.py` ra chỗ dùng chung — một
đợt refactor riêng, không nhét lén vào đây.

FAIL-OPEN TUYỆT ĐỐI: mọi lỗi ghi log đều nuốt. Một vệt kiểm toán không được là
thứ làm hỏng lượt tra cứu của người dùng.
"""
import functools
import json
import logging
import os
import threading
import time

from ..phien import NGUOI_DUNG_HIEN_TAI

logger = logging.getLogger(__name__)

# Trần độ dài chuỗi tham số. Tham số tool đọc là tên/mã người dùng gõ nên gần
# như luôn ngắn; trần chỉ để một đầu vào bất thường không thổi phồng một dòng
# log. Cắt thay vì bỏ — ghi được thứ méo còn hơn không ghi gì.
ARGS_JSON_MAX = 4_000

_conn = None
_lock = threading.Lock()


def _db():
    """Kết nối lười, tự nối lại. None khi không cấu hình DATABASE_URL.

    "Không cấu hình = tắt log" là thiết kế có chủ ý (khớp `event_log.py` bên
    MCP), không phải lỗi — đó cũng là công tắc mà conftest của bộ test dùng.
    """
    global _conn
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    if _conn is None or getattr(_conn, "closed", 1):
        import psycopg2
        _conn = psycopg2.connect(dsn)
        _conn.autocommit = True
    return _conn


def _tham_so_json(kwargs: dict) -> str | None:
    """Tham số ĐẦY ĐỦ dạng JSON (quyết định chủ dự án 2026-08-23, phương án B).

    Ngược với đường GHI (chỉ digest + tên khoá) VÌ Ở ĐƯỜNG ĐỌC CHÍNH THAM SỐ LÀ
    CÂU TRẢ LỜI: "có người xem công nợ" không dùng được, "xem công nợ của Azure
    Interior" mới dùng được.
    """
    try:
        if not kwargs:
            return None
        s = json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str)
        return s if len(s) <= ARGS_JSON_MAX else s[:ARGS_JSON_MAX] + "…[cắt]"
    except Exception:                                       # noqa: BLE001
        return None


def ghi_luot_doc(tool_name: str, caller: str, kwargs: dict,
                 duration_ms: int, error: str | None = None) -> None:
    """Một dòng `event_type='erp_read'`. KHÔNG BAO GIỜ ném."""
    try:
        with _lock:
            conn = _db()
            if conn is None:
                return
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mcp_call_log
                    (created_at, event_type, caller, tool_name, operation,
                     duration_ms, error_code, error_message, http_user,
                     args_json)
                    VALUES (now(), 'erp_read', %s, %s, 'read', %s, %s, %s,
                            %s, %s)
                """, (caller, tool_name, duration_ms,
                      "E500" if error else None, error,
                      NGUOI_DUNG_HIEN_TAI.get(), _tham_so_json(kwargs)))
    except Exception:                                       # noqa: BLE001
        global _conn
        _conn = None            # ép nối lại lượt sau
        logger.warning("không ghi được vệt kiểm toán lượt đọc %s", tool_name,
                       exc_info=True)


def boc_ghi_vet(t, caller: str):
    """Bọc MỘT tool đọc để mỗi lời gọi sinh đúng một dòng kiểm toán.

    Bọc `t.func` chứ không thay `t`: giữ nguyên tên/mô tả/args_schema mà
    LangChain đã suy ra, nên phía LLM không thấy khác gì — hai wrapper sẵn có
    trong `build_erp_query_tools` cũng theo khuôn này.
    """
    goc = t.func

    @functools.wraps(goc)
    def _boc_ham(*args, **kwargs):
        t0 = time.monotonic()
        loi = None
        try:
            return goc(*args, **kwargs)
        except Exception as e:                              # noqa: BLE001
            # CHỈ tên loại, KHÔNG nguyên văn lỗi. Hai lý do, cả hai đều đủ:
            #   * Với vệt kiểm toán đọc, "lượt này hỏng, loại gì" là đủ —
            #     nguyên văn đã được `envelope.fail_read` log riêng cho người
            #     vận hành.
            #   * Nội suy nguyên văn exception vào f-string trong
            #     `src/erp_query/*.py` bị test_khong_ro_loi_doc.py bắt (bộ
            #     quét rò lỗi, 44 chỗ đã đóng; nó đọc theo DÒNG nên bắt cả
            #     chú thích). Có cơ chế miễn trừ, nhưng miễn trừ là nợ, và
            #     ở đây không cần vì bản không-nguyên-văn đã đủ dùng.
            loi = type(e).__name__
            raise
        finally:
            ghi_luot_doc(t.name, caller, kwargs,
                         int((time.monotonic() - t0) * 1000), loi)

    t.func = _boc_ham
    return t
