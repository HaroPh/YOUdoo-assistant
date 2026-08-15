# backend/tests/test_hau_to_thong_bao_loi.py
"""Khoá HAI thuộc tính của mọi lời gọi fail / fail_read / fail_write.

Vì sao có file này: bản rà soát cuối đợt 2026-08-15-error-hygiene-and-audit-
trail CHỨNG MINH BẰNG TAY rằng cả 88 chỗ gọi helper đều đúng hậu tố theo tầng
và đều truyền đúng tên hàm bao quanh làm đối số đầu — nhưng KHÔNG có gì bắt
buộc hai thuộc tính đó. Chỗ gọi thứ 89 viết sai sẽ không ai biết.

Vì sao không rút hậu tố thành hằng số dùng chung (đã cân nhắc và loại):
~90 TIỀN TỐ tiếng Việt vẫn phải nằm tại chỗ gọi, nên hằng số chỉ gom được
nửa câu, đổi lại mất khả năng đọc trọn câu ngay tại chỗ. Khoá bằng test thì
giữ được cả hai.

Bộ quét ở đây tự nó cũng được kiểm (phần "Kiểm chính bộ quét" bên dưới) —
một bộ quét hỏng sẽ khiến phần đối chiếu toàn repo xanh giả.
"""
import ast
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parents[2]
THU_MUC_QUET = ("backend/src", "mcp-servers/odoo", "backend/skills")

# Hậu tố tầng ĐỌC: chỉ nói "không lấy được dữ liệu" — đúng trong mọi trường hợp.
HAU_TO_DOC = "— không lấy được dữ liệu. Nếu lặp lại, báo quản trị viên."

# Hậu tố tầng GHI. KHÔNG được khẳng định "thao tác chưa được thực hiện":
# nhiều tool ghi bọc CẢ commit LẪN các lệnh gọi Odoo sau đó trong cùng một
# try (register_payment gọi action_create_payments — tiền đã chuyển — rồi mới
# read lại kết quả; deliver_order/receive_order validate nhiều phiếu trong
# vòng lặp). Lỗi ở nhánh sau khiến câu "chưa được thực hiện" thành SAI, và
# phản xạ tự nhiên của người dùng là thử lại ⇒ trả tiền hai lần.
HAU_TO_GHI = "— thao tác có thể chưa hoàn tất. Nếu lặp lại, báo quản trị viên."

# Tầng theo TÊN helper: fail (tool MCP) và fail_write (điều phối viết) là
# tầng ghi; fail_read là tầng đọc.
TEN_HELPER_GHI = {"fail", "fail_write"}
TEN_HELPER_DOC = {"fail_read"}
MOI_TEN_HELPER = TEN_HELPER_GHI | TEN_HELPER_DOC


def ghep_chuoi(node: ast.AST) -> str | None:
    """Dựng lại literal chuỗi của `node`, coi mọi `{…}` là hộp đen.

    Trả None khi biểu thức không phải literal chuỗi (biến, gọi hàm, nối bằng
    `+`) — chỗ gọi như vậy không đối chiếu được và sẽ bị báo riêng.

    Nối chuỗi ngầm nhiều dòng (`"a" "b"`, `f"a" "b"`) do chính parser của
    Python gộp sẵn thành MỘT Constant hoặc MỘT JoinedStr, nên hàm này không
    cần xử lý gì thêm cho trường hợp đó.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        phan = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                phan.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                phan.append("{}")          # hộp đen: nội dung không xét
            else:
                return None
        return "".join(phan)
    return None


def _ten_helper(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def quet_chuoi_goi_helper(path: Path, nhan: str | None = None) -> list[dict]:
    """Trả một mục cho MỖI lời gọi fail/fail_read/fail_write trong file.

    Mỗi mục: {"nhan", "dong", "helper", "ham_bao", "doi_so_dau", "display"}.
      - ham_bao    — tên hàm def bao quanh gần nhất (None nếu ở cấp module)
      - doi_so_dau — giá trị đối số đầu nếu nó là literal chuỗi, None nếu không
      - display    — đối số thứ hai đã ghép, None nếu không dựng lại được
    """
    nhan = path.name if nhan is None else nhan
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    ket_qua: list[dict] = []

    def di(node: ast.AST, ham_bao: str | None) -> None:
        for con in ast.iter_child_nodes(node):
            if isinstance(con, (ast.FunctionDef, ast.AsyncFunctionDef)):
                di(con, con.name)
                continue
            if isinstance(con, ast.Call) and _ten_helper(con.func) in MOI_TEN_HELPER:
                ds = con.args
                ket_qua.append({
                    "nhan": nhan,
                    "dong": con.lineno,
                    "helper": _ten_helper(con.func),
                    "ham_bao": ham_bao,
                    "doi_so_dau": (ds[0].value
                                   if ds and isinstance(ds[0], ast.Constant)
                                   and isinstance(ds[0].value, str) else None),
                    "display": ghep_chuoi(ds[1]) if len(ds) > 1 else None,
                })
            di(con, ham_bao)

    di(tree, None)
    return ket_qua


def _moi_cho_goi() -> list[dict]:
    out = []
    for thu_muc in THU_MUC_QUET:
        goc = GOC / thu_muc
        if not goc.exists():
            continue
        for p in sorted(goc.rglob("*.py")):
            out += quet_chuoi_goi_helper(
                p, nhan=p.relative_to(GOC).as_posix())
    return out


@pytest.fixture(scope="module")
def cho_goi():
    ds = _moi_cho_goi()
    assert ds, ("không tìm thấy chỗ gọi helper nào — bộ quét hỏng hoặc "
                "đường dẫn sai, mọi khẳng định dưới đây sẽ xanh giả")
    return ds


# ─── Đối chiếu toàn repo ──────────────────────────────────────────────────

def test_dinh_nghia_helper_khong_bi_dem_nham(cho_goi):
    """Đối chứng: phải quét được cả ba tầng, không phải chỉ một."""
    ten = {c["helper"] for c in cho_goi}
    assert ten == MOI_TEN_HELPER, f"chỉ thấy {sorted(ten)}"


def test_moi_display_deu_dung_lai_duoc(cho_goi):
    """Chỗ nào không dựng lại được literal thì hai khẳng định dưới sẽ ÂM THẦM
    bỏ qua nó — nên chặn ngay ở đây."""
    hong = [f"{c['nhan']}:{c['dong']}" for c in cho_goi if c["display"] is None]
    assert hong == [], (
        "không dựng lại được chuỗi display (biến? nối bằng +?):\n"
        + "\n".join(hong))


def test_hau_to_dung_theo_tang(cho_goi):
    sai = []
    for c in cho_goi:
        can = HAU_TO_GHI if c["helper"] in TEN_HELPER_GHI else HAU_TO_DOC
        if not c["display"].endswith(can):
            sai.append(f"{c['nhan']}:{c['dong']} ({c['helper']}) "
                       f"kết thúc bằng …{c['display'][-60:]!r}")
    assert sai == [], ("sai hậu tố theo tầng:\n" + "\n".join(sai))


def test_doi_so_dau_bang_ten_ham_bao_quanh(cho_goi):
    sai = []
    for c in cho_goi:
        if c["doi_so_dau"] != c["ham_bao"]:
            sai.append(f"{c['nhan']}:{c['dong']} ({c['helper']}) "
                       f"đối số đầu={c['doi_so_dau']!r} "
                       f"nhưng hàm bao quanh={c['ham_bao']!r}")
    assert sai == [], (
        "đối số đầu phải là tên hàm bao quanh — nó là NHÃN duy nhất định vị "
        "chỗ hỏng trong log:\n" + "\n".join(sai))


def test_hau_to_ghi_khong_khang_dinh_da_khong_thuc_hien(cho_goi):
    """Chặn hồi quy CỤ THỂ: câu cũ khẳng định thao tác KHÔNG xảy ra. Sai ở
    mọi tool ghi có commit rồi còn gọi Odoo tiếp trong cùng try."""
    sai = [f"{c['nhan']}:{c['dong']}" for c in cho_goi
           if "chưa được thực hiện" in c["display"]]
    assert sai == [], (
        "còn khẳng định 'chưa được thực hiện' — câu này có thể SAI và dẫn "
        "người dùng tới thao tác lặp (vd trả tiền hai lần):\n" + "\n".join(sai))


# ─── Kiểm chính bộ quét ───────────────────────────────────────────────────

def _quet_nguon(tmp_path, nguon: str) -> list[dict]:
    p = tmp_path / "vidu.py"
    p.write_text(nguon, encoding="utf-8")
    return quet_chuoi_goi_helper(p)


def test_quet_noi_chuoi_ngam_nhieu_dong(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return fail("t", "A "\n'
                     '                     "B", e)\n')
    assert len(ds) == 1
    assert ds[0]["display"] == "A B"
    assert ds[0]["ham_bao"] == "t"
    assert ds[0]["doi_so_dau"] == "t"


def test_quet_fstring_coi_placeholder_la_hop_den(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return fail_read("t", f"X {ten} Y", e)\n')
    assert ds[0]["display"] == "X {} Y"
    assert ds[0]["helper"] == "fail_read"


def test_quet_tron_fstring_va_chuoi_thuong(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return fail_write("t", f"A{x}"\n'
                     '                           " B", e)\n')
    assert ds[0]["display"] == "A{} B"


def test_quet_lay_ham_def_gan_nhat_khong_phai_ham_ngoai(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def ngoai():\n'
                     '    def trong():\n'
                     '        return fail("trong", "M", e)\n'
                     '    return trong\n')
    assert ds[0]["ham_bao"] == "trong"


def test_quet_bat_ca_dang_goi_qua_module(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return helpers.fail("t", "M", e)\n')
    assert ds[0]["helper"] == "fail"


def test_quet_bao_display_none_khi_khong_phai_literal(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return fail("t", cau_noi, e)\n')
    assert ds[0]["display"] is None


def test_quet_bo_qua_ham_ten_khac(tmp_path):
    ds = _quet_nguon(tmp_path,
                     'def t():\n'
                     '    return failsafe("t", "M", e)\n')
    assert ds == []


def test_quet_file_khong_parse_duoc_tra_rong(tmp_path):
    p = tmp_path / "hong.py"
    p.write_text('def f(:\n    pass\n', encoding="utf-8")
    assert quet_chuoi_goi_helper(p) == []
