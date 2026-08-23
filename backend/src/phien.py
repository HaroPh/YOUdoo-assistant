"""Ngữ cảnh của MỘT lượt chat — module LÁ, không nhập gì của dự án.

Vì sao tách khỏi `agents/erp_agent.py`: `src/erp_query/audit.py` cần biết ai
đang hỏi, mà `agents/graph.py` đã nhập `src.erp_query.tools` — nhập ngược lại
là vòng. Module này cố ý không có phụ thuộc nội bộ nào để cả hai phía nhập
được mà không bao giờ tạo chu trình.

ContextVar truyền được từ `chat()` xuống tận lời gọi tool vì asyncio CHÉP ngữ
cảnh vào task con lúc tạo (chiều cha→con). Chiều ngược lại KHÔNG chạy — đợt
tracing 2026-07 đã trả giá cho điều đó.
"""
from contextvars import ContextVar

# Id người dùng Open WebUI của lượt hiện tại. None = không có người dùng
# (script nội bộ, tác vụ nền, test) — ghi NULL trung thực hơn là bịa.
NGUOI_DUNG_HIEN_TAI: ContextVar[str | None] = ContextVar(
    "nguoi_dung_hien_tai", default=None)
