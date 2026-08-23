"""Chặn bộ test ghi vào vệt kiểm toán THẬT.

Cùng lý do và cùng khuôn với `tests/mcp/conftest.py`: từ 2026-08-23 mọi tool
đọc đều sinh một dòng `mcp_call_log`, nên mỗi lượt chạy `tests/erp_query/` sẽ
đổ rác vào đúng bảng dùng để điều tra sự cố. Đo được ngay lượt đầu: bộ test
thêm **9 dòng**.

Dùng đúng công tắc mà module thiết kế sẵn — `DATABASE_URL` rỗng nghĩa là
"không cấu hình = tắt log", `_db()` trả None ngay. Không mock gì.

Ca `integration` được MIỄN: chúng cố ý kiểm hành vi ghi thật.
"""
import pytest

from src.erp_query import audit


@pytest.fixture(autouse=True)
def _tat_ghi_vet_doc(request, monkeypatch):
    if "integration" in request.keywords:
        return
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(audit, "_conn", None, raising=False)
