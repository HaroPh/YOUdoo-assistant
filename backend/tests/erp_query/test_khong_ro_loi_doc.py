"""Đường ĐỌC không được nội suy exception vào câu trả lời.

Tầng này nặng nhất trong bốn tầng: gateway._call gọi thẳng Odoo và không bọc
gì, nên Fault bay nguyên vẹn lên đây. 44 chỗ, đo 2026-08-14.

RO_LOI/quet_file dùng chung từ tests.leak_scan (Ruling D, task-3) — không
khai báo lại ở đây."""
from pathlib import Path

from tests.leak_scan import quet_file

QUERY_DIR = Path(__file__).resolve().parents[2] / "src" / "erp_query"


def test_khong_ham_doc_nao_ro_exception():
    ro = [m for p in sorted(QUERY_DIR.glob("*.py")) for m in quet_file(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_fail_read_sach_ca_display_lan_error(monkeypatch):
    """Cả HAI trường chuỗi phải sạch. `error` cũng đi ra ngoài trong cùng
    dict và không có gì đảm bảo nơi nhận không hiển thị nó.

    (Ruling G) Không chỉ kiểm "logger có được gọi": phải kiểm nguyên văn lỗi
    thật sự có mặt trong đối số truyền cho logger — nếu không, nửa vệt kiểm
    toán mà fail_read hứa (log nguyên văn, trả câu sạch) không hề được đo."""
    from src.erp_query import envelope as env

    da_log = []
    monkeypatch.setattr(env.logger, "exception", lambda *a, **k: da_log.append(a))

    exc = ValueError("Youdoo AI / Read Only")
    res = env.fail_read("tra_lead", "Lỗi tra cứu lead/cơ hội — không lấy "
                                    "được dữ liệu.", exc)

    assert res["status"] == "error"
    assert res["data"] is None
    assert "Youdoo AI" not in res["display"]
    assert "Youdoo AI" not in res["error"]
    assert da_log, "không ghi log — bản sửa chỉ giấu lỗi đi"
    # logger.exception("%s thất bại: %s: %s", where, type(exc).__name__, exc)
    # — exc (đối tượng exception) là đối số cuối trong tuple positional args
    # đã bắt được. Chỉ "có gọi" thôi không đủ: phải kiểm nguyên văn lỗi thật
    # sự có mặt, không thì detail rỗng/thiếu vẫn qua được assert trên.
    assert "Youdoo AI / Read Only" in str(da_log[0][-1]), \
        "logger có được gọi nhưng KHÔNG mang nguyên văn lỗi — nửa vệt " \
        "kiểm toán này vô giá trị"
