# backend/tests/test_leak_scan.py
"""Test trực tiếp cho tests/leak_scan.py — bộ quét dùng chung của Task 3-6
(xem docstring ở đó cho Ruling D). Rủi ro DUY NHẤT của việc dùng chung một
bộ quét: một lỗi trong regex/hàm quét sẽ làm MÙ CẢ BỐN lưới cùng lúc — test
này khoá hành vi bằng chứng cứ trực tiếp trên regex và trên quet_file(),
không qua trung gian nào.

Phần dưới (Ruling I, task-6) khoá lưới AST — quet_ast_file() — bằng chứng cứ
tương tự: tên biến bất kỳ, biến KHÔNG phải tên đó, không có `as` binding,
file không parse được."""
from tests.leak_scan import RO_LOI, quet_ast_file, quet_file


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


# ─── quet_ast_file (Ruling I) ─────────────────────────────────────────────

def test_quet_ast_bat_ten_bien_thuong_gap(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text(
        'try:\n'
        '    lam_gi()\n'
        'except Exception as ex:\n'
        '    msg = f"loi: {ex}"\n',
        encoding="utf-8")
    assert quet_ast_file(p) == ['vidu.py:4: msg = f"loi: {ex}"']


def test_quet_ast_bat_ten_bien_bat_ky_khong_chi_ex(tmp_path):
    # Đây chính là lý do lưới AST tồn tại: RO_LOI chỉ biết e/exc/err, còn
    # AST phải bắt được BẤT KỲ tên nào — không cần liệt kê thêm tên.
    p = tmp_path / "vidu.py"
    p.write_text(
        'try:\n'
        '    lam_gi()\n'
        'except Exception as problem:\n'
        '    msg = f"loi: {problem}"\n',
        encoding="utf-8")
    assert quet_ast_file(p) == ['vidu.py:4: msg = f"loi: {problem}"']
    assert not RO_LOI.search('msg = f"loi: {problem}"'), \
        "regex đáng lẽ KHÔNG thấy chỗ này — nếu nó thấy, ví dụ không còn " \
        "chứng minh được AST bù cho gì"


def test_quet_ast_khong_bat_bien_khac_trong_cung_khoi(tmp_path):
    # f-string trong khối except nhưng nội suy MỘT biến khác, không phải
    # tên except-binding — không phải chỗ rò.
    p = tmp_path / "vidu.py"
    p.write_text(
        'try:\n'
        '    lam_gi()\n'
        'except Exception as ex:\n'
        '    ma_loi = "E500"\n'
        '    msg = f"loi: {ma_loi}"\n',
        encoding="utf-8")
    assert quet_ast_file(p) == []


def test_quet_ast_khong_bat_khi_khong_co_as(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text(
        'try:\n'
        '    lam_gi()\n'
        'except Exception:\n'
        '    msg = f"loi chung: {ma_loi_mac_dinh}"\n',
        encoding="utf-8")
    assert quet_ast_file(p) == []


def test_quet_ast_file_khong_parse_duoc_tra_rong(tmp_path):
    p = tmp_path / "hong.py"
    p.write_text('def f(:\n    pass\n', encoding="utf-8")
    assert quet_ast_file(p) == []


def test_quet_ast_nhan_tuy_chinh(tmp_path):
    p = tmp_path / "vidu.py"
    p.write_text(
        'try:\n'
        '    lam_gi()\n'
        'except Exception as ex:\n'
        '    msg = f"loi: {ex}"\n',
        encoding="utf-8")
    assert quet_ast_file(p, nhan="tools/vidu.py") == [
        'tools/vidu.py:4: msg = f"loi: {ex}"']
