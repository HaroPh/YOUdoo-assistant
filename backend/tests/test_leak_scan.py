# backend/tests/test_leak_scan.py
"""Test trực tiếp cho tests/leak_scan.py — bộ quét dùng chung của Task 3-6
(xem docstring ở đó cho Ruling D). Rủi ro DUY NHẤT của việc dùng chung một
bộ quét: một lỗi trong regex/hàm quét sẽ làm MÙ CẢ BỐN lưới cùng lúc — test
này khoá hành vi bằng chứng cứ trực tiếp trên regex và trên quet_file(),
không qua trung gian nào."""
from tests.leak_scan import RO_LOI, quet_file


def test_ro_loi_khop_e():
    assert RO_LOI.search('f"Lỗi: {e}"')


def test_ro_loi_khop_exc():
    assert RO_LOI.search('f"Lỗi: {exc}"')


def test_ro_loi_khop_err():
    assert RO_LOI.search('f"Lỗi: {err}"')


def test_ro_loi_khop_e_dinh_dang_repr():
    assert RO_LOI.search('f"Lỗi: {e!r}"')


def test_ro_loi_khop_e_dinh_dang_format_spec():
    assert RO_LOI.search('f"Lỗi: {e:s}"')


def test_ro_loi_khong_khop_ten_chi_bat_dau_giong():
    # Tên biến CHỈ bắt đầu bằng e/err không được tính — false positive ở đây
    # sẽ chặn oan code hợp lệ trên toàn repo.
    for line in ['f"{era}"', 'f"{expected}"', 'f"{error_code}"']:
        assert not RO_LOI.search(line), line


def test_quet_file_nhan_mac_dinh_la_ten_file(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text('x = f"Lỗi: {e}"\n', encoding="utf-8")
    assert quet_file(p) == ['vidu.py:1: x = f"Lỗi: {e}"']


def test_quet_file_nhan_tuy_chinh(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text('x = f"Lỗi: {e}"\n', encoding="utf-8")
    assert quet_file(p, nhan="tools/vidu.py") == ['tools/vidu.py:1: x = f"Lỗi: {e}"']


def test_quet_file_khong_co_dong_nao_khop(tmp_path):
    p = tmp_path / "sach.py"
    p.write_text('x = f"Không có gì lộ ra"\n', encoding="utf-8")
    assert quet_file(p) == []


def test_quet_file_nhieu_dong_giu_dung_thu_tu(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text('a = 1\nb = f"Lỗi: {e}"\nc = f"Lỗi khác: {exc}"\n', encoding="utf-8")
    assert quet_file(p) == [
        'vidu.py:2: b = f"Lỗi: {e}"',
        'vidu.py:3: c = f"Lỗi khác: {exc}"',
    ]
