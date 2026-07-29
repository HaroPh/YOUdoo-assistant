"""Cửa DUY NHẤT ra Odoo — mọi tool phải đi qua đây (spec SP-1B §3c).

Năm cổng bảo mật nằm ở hàm odoo() bên dưới: xác thực, rate limit, denylist,
audit chain, event log. Một tool gọi thẳng ServerProxy/execute_kw sẽ vòng qua
CẢ NĂM mà vẫn chạy đúng — nên sai sót loại này không lộ ra bằng test chức năng,
chỉ lộ khi có sự cố và không ai truy được dấu vết.

backend/tests/mcp/test_odoo_tool_boundary.py ép bất biến này: nó lấy
inspect.getsource() của từng tool đã đăng ký và khẳng định không tool nào nhắc
ServerProxy hay execute_kw.
"""
import sys
import time
import xmlrpc.client

from config import ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PWD
from security import classify_operation, sanitize_model, sanitize_payload_keys
from rate_limit import check_rate_limit
from event_log import log_mcp_event

# ─── Odoo connection ──────────────────────────────────────────────────────────

_uid: int | None = None

def get_uid() -> int:
    global _uid
    if _uid is None:
        common = xmlrpc.client.ServerProxy(ODOO_URL + "/xmlrpc/2/common")
        _uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PWD, {})
        if not _uid:
            raise RuntimeError("Odoo authentication failed — kiểm tra ODOO_USERNAME/PASSWORD")
    return _uid

def odoo(model: str, method: str, args: list, kwargs: dict | None = None,
         tool_name: str | None = None) -> object:
    """
    Gọi Odoo XML-RPC qua các gate bảo mật (mọi tool đều đi qua đây):
      1. sanitize model name      4. rate limit
      2. classify + deny method    5. timing + log
      3. enforce read-only (Phase 1)
    tool_name tự lấy từ hàm gọi (tool) nếu không truyền vào.
    """
    if tool_name is None:
        tool_name = sys._getframe(1).f_code.co_name   # tên tool đang gọi
    model = sanitize_model(model)
    sanitize_payload_keys(args)
    sanitize_payload_keys(kwargs or {})

    op = classify_operation(method)
    if op is None:
        log_mcp_event("permission_denied", tool_name=tool_name, model_name=model,
                      operation=method, error_code="E403",
                      error_message=f"Method '{method}' không có trong whitelist")
        raise ValueError(f"Method '{method}' không được phép")
    if op != "read" and not write_actions_enabled():
        log_mcp_event("permission_denied", tool_name=tool_name, model_name=model,
                      operation=op, error_code="E403",
                      error_message="Write actions đang tắt (toggle Odoo "
                                    "erp_ai.write_actions_enabled)")
        raise ValueError(f"Thao tác '{op}' bị chặn — write-mode đang tắt "
                         "(erp_ai.write_actions_enabled)")

    if not check_rate_limit(tool_name or "default"):
        log_mcp_event("rate_limit", tool_name=tool_name, model_name=model, operation=op,
                      error_code="E429", error_message="Rate limit exceeded")
        raise ValueError("Quá nhiều request — thử lại sau 1 phút")

    start = time.monotonic()
    try:
        obj = xmlrpc.client.ServerProxy(ODOO_URL + "/xmlrpc/2/object")
        result = obj.execute_kw(ODOO_DB, get_uid(), ODOO_PWD, model, method, args, kwargs or {})
        log_mcp_event("model_access", tool_name=tool_name, model_name=model, operation=op,
                      duration_ms=int((time.monotonic() - start) * 1000))
        return result
    except xmlrpc.client.Fault as e:
        # Odoo commits the transaction in its service layer BEFORE serializing the
        # response, so a void (None-returning) method that already succeeded still
        # raises this marshalling Fault (allow_none=False). It can only occur
        # post-commit, so treat it as a successful void return. A method that
        # itself raised produces a different Fault (carrying its traceback), which
        # does NOT match and falls through to error + re-raise below.
        if "cannot marshal None" in str(e):
            log_mcp_event("model_access", tool_name=tool_name, model_name=model, operation=op,
                          duration_ms=int((time.monotonic() - start) * 1000))
            return None
        log_mcp_event("error", tool_name=tool_name, model_name=model, operation=op,
                      duration_ms=int((time.monotonic() - start) * 1000),
                      error_code="E500", error_message=str(e))
        raise
    except Exception as e:
        log_mcp_event("error", tool_name=tool_name, model_name=model, operation=op,
                      duration_ms=int((time.monotonic() - start) * 1000),
                      error_code="E500", error_message=str(e))
        raise

# ─── Write toggle (S3) — đọc runtime từ Odoo, cache TTL, fail-closed ──────────

_WRITE_GATE_KEY = "erp_ai.write_actions_enabled"
_WRITE_GATE_TTL_S = 5.0
_write_gate_cache = {"value": False, "expires_at": 0.0}


def write_actions_enabled() -> bool:
    """True chỉ khi ir.config_parameter[_WRITE_GATE_KEY] == "true" (strip+lower).
    Đọc qua odoo() sẵn có: search_read được classify "read" nên KHÔNG đệ quy
    qua nhánh chặn ghi. Fail-closed (spec §3): mọi lỗi đọc / key thiếu /
    value khác "true" → False; kết quả lỗi cũng cache — không spam retry."""
    now = time.monotonic()
    if now < _write_gate_cache["expires_at"]:
        return _write_gate_cache["value"]
    try:
        rows = odoo("ir.config_parameter", "search_read",
                    [[("key", "=", _WRITE_GATE_KEY)]],
                    {"fields": ["value"], "limit": 1},
                    tool_name="write_gate_check")
        # Odoo XML-RPC trả False (không phải None) cho char field rỗng → `or ""`
        value = bool(rows) and str(rows[0].get("value") or "").strip().lower() == "true"
    except Exception as e:  # noqa: BLE001 — fail-closed (spec §3)
        log_mcp_event("write_gate_error", tool_name="write_gate_check",
                      error_code="E503", error_message=str(e))
        value = False
    _write_gate_cache["value"] = value
    _write_gate_cache["expires_at"] = now + _WRITE_GATE_TTL_S
    return value
