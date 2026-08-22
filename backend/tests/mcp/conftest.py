"""Chặn bộ test ghi vào vệt kiểm toán THẬT.

Đo 2026-08-22: `mcp_call_log` có 2 671 dòng, trong đó **2 502 (94%) là rác
của bộ test** — chủ yếu từ `test_fail_prefix_thieu_ten.py`, tệp KHÔNG có
marker nên chạy trong bộ mặc định và cố ý làm `odoo()` ném. Mỗi lần ném là
một dòng `tool_error` ghi thẳng vào database production, dưới tài khoản cá
nhân trong `.env`. Chỉ 70 dòng đến từ ba tài khoản AI thật.

Hệ quả không chỉ là bảng to: một vệt kiểm toán 94% nhiễu thì **không đọc
được**, tức cơ chế điều tra sự cố đã hỏng trong im lặng — cùng lớp lỗi với
fixture RAG từng ghi đè tệp đã commit (spec 2026-08-19).

Cách chặn dùng đúng công tắc mà chính module thiết kế sẵn: `DATABASE_URL`
rỗng nghĩa là "không cấu hình = tắt log", và `_get_db()` trả None ngay. Không
phải mock, không giả lập gì — chỉ là không cấu hình.

Ca `integration` được MIỄN: chúng cố ý kiểm hành vi ghi thật trên một
database thật, và đó là lý do tồn tại của chúng.
"""
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(autouse=True)
def _tat_ghi_vet_kiem_toan_that(request, monkeypatch):
    if "integration" in request.keywords:
        return
    if not MCP_DIR.exists():
        return
    sys.path.insert(0, str(MCP_DIR))
    try:
        import event_log
    except Exception:                                       # noqa: BLE001
        return
    finally:
        sys.path.remove(str(MCP_DIR))
    monkeypatch.setattr(event_log, "DATABASE_URL", "", raising=False)
