"""Tầng MCP không được nội suy exception vào câu trả lời người dùng.

Đo 2026-08-14: lỗi Odoo thật liệt kê NGUYÊN BẢN ĐỒ PHÂN QUYỀN — kể cả tên
nhóm tự tạo của dự án ("Youdoo AI / Read Only") — nên đây là lộ thông tin,
không phải chuyện thẩm mỹ.

RO_LOI/quet_file dùng chung từ tests.leak_scan (Ruling D, task-3) — không
khai báo lại ở đây."""
import sys
from pathlib import Path

import pytest

from tests.leak_scan import quet_file

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"
TOOLS_DIR = MCP_DIR / "tools"


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not TOOLS_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


def test_khong_tool_mcp_nao_ro_exception():
    """Đo trước khi sửa: 21 chỗ trên 6 file."""
    ro = [m for p in sorted(TOOLS_DIR.glob("*.py")) for m in quet_file(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_fail_ghi_ca_hai_dich_va_khong_lo_gi(monkeypatch):
    """Câu trả về phải sạch, VÀ nguyên văn lỗi phải tới cả hai đích — không
    chỉ "có gọi", mà phải MANG nguyên văn. log_mcp_event im lặng không làm
    gì khi thiếu DATABASE_URL, nên logger tiến trình là dấu vết SỐNG SÓT
    DUY NHẤT trong môi trường chưa cấu hình DB — một test chỉ kiểm tra
    logger "có được gọi" mà không kiểm nội dung thì để đúng lỗ hổng này lọt
    qua."""
    sys.path.insert(0, str(MCP_DIR))
    try:
        import helpers
        import json as _json

        da_ghi = {}
        monkeypatch.setattr(helpers, "log_mcp_event",
                            lambda *a, **k: da_ghi.update(k))
        da_log = []
        monkeypatch.setattr(helpers.logger, "exception",
                            lambda *a, **k: da_log.append(a))

        exc = ValueError("Youdoo AI / Read Only")
        raw = helpers.fail("post_invoice", "Lỗi khi tạo hóa đơn — thao tác "
                                           "chưa được thực hiện.", exc)
        data = _json.loads(raw)

        assert data["ok"] is False
        assert "Youdoo AI" not in data["display"]
        assert "ValueError" not in data["display"]
        assert "Youdoo AI / Read Only" in da_ghi["error_message"]
        assert da_ghi["tool_name"] == "post_invoice"
        assert da_log, "không ghi vào logger tiến trình — thiếu DATABASE_URL " \
                       "thì lỗi sẽ biến mất hoàn toàn"
        # logger.exception("tool %s thất bại: %s", tool_name, detail) — detail
        # là đối số cuối trong tuple positional args đã bắt được. Chỉ "có gọi"
        # thôi không đủ: nếu detail rỗng/thiếu, câu trên vẫn đúng mà nguyên
        # văn lỗi đã biến mất khỏi đích sống sót duy nhất.
        assert "Youdoo AI / Read Only" in da_log[0][-1], \
            "logger có được gọi nhưng KHÔNG mang nguyên văn lỗi — nửa vệt " \
            "kiểm toán này vô giá trị"
    finally:
        sys.path.remove(str(MCP_DIR))
