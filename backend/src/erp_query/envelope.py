"""The one output shape for every erp_query function: machine-readable `data`
plus a human `display`. Orchestration (C) reads `data`; the UI shows `display`."""
import logging

logger = logging.getLogger(__name__)


def ok(data, display: str) -> dict:
    return {"status": "success", "data": data, "display": display}


def err(message: str, display: str | None = None) -> dict:
    return {"status": "error", "data": None, "display": display or message, "error": message}


def fail_read(where: str, display: str, exc: Exception) -> dict:
    """Ghi nguyên văn lỗi vào logger; trả câu KHÔNG lộ gì.

    Backend không có bảng kiểm toán riêng cho đường đọc (dựng thêm một cái
    là quyết định kiến trúc khác), nên đích ở đây là logger tiến trình —
    logs/backend_err.log.

    `error` nhận CHÍNH `display`, không nhận nguyên văn lỗi: dict này đi ra
    ngoài nguyên vẹn và không có gì đảm bảo nơi nhận chỉ hiển thị `display`.
    """
    logger.exception("%s thất bại: %s: %s", where, type(exc).__name__, exc)
    return err(display, display)
