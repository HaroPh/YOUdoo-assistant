# backend/tests/mcp/test_odoo_call_ngoai_try.py
"""Lưới chặn hồi quy cho lỗ hổng "12 tool không có try" (2026-08-15).

Bối cảnh: helpers.fail(tool_name, display, exc) ghi nguyên văn lỗi vào CẢ
logger tiến trình LẪN vệt kiểm toán (mcp_call_log), rồi trả một câu sạch cho
người dùng. Cơ chế này chỉ chạy khi exception bị bắt — 23/35 tool MCP có toàn
bộ thân hàm trong một try/except gọi fail() đúng cách. 12 tool còn lại (đo
bằng AST, co_try_o_dong=[] cho từng cái) KHÔNG có try nào cả: khi Odoo raise,
exception xuyên thẳng qua tool, fail() không bao giờ chạy, và ở môi trường
thiếu DATABASE_URL lỗi biến mất hoàn toàn khỏi mọi nơi có thể xem được.

Nhánh 2026-08-15-tool-try-coverage đóng 12 chỗ đó bằng tay. Nhưng danh sách
"12 tool" chỉ đúng tại một thời điểm — tool thứ 36 lặp lại đúng lỗi này (thêm
một odoo() ngoài try) sẽ không ai biết, giống hệt cách 12 tool này đã lọt qua
đợt vệ sinh lỗi trước. Test này quét TOÀN BỘ mcp-servers/odoo/tools/ bằng AST:
với mỗi hàm có decorator @mcp.tool(), thu thập mọi node nằm trong THÂN của bất
kỳ ast.Try nào bên trong hàm đó, rồi báo bất kỳ lời gọi odoo(...) nào không
nằm trong tập đó.

Cố ý CHỈ xét thân (body) của Try, không xét except/else/finally — một odoo()
gọi trong except/finally của một try khác vẫn xuyên thẳng ra ngoài như thường
nếu bản thân nó không có try riêng bao quanh.
"""
import ast
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"
TOOLS_DIR = MCP_DIR / "tools"


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not TOOLS_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


def _la_tool_mcp(node: ast.AST) -> bool:
    """True nếu `node` là FunctionDef/AsyncFunctionDef có decorator dạng
    mcp.tool hoặc mcp.tool(...) (chấp cả hai dạng — FastMCP cho phép gọi
    không tham số)."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for dec in node.decorator_list:
        goc = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(goc, ast.Attribute) and goc.attr == "tool":
            return True
    return False


def _cac_id_duoc_bao_ve(ham: ast.AST) -> set[int]:
    """id() của mọi node là hậu duệ (hoặc chính nó) của một statement nằm
    trong THÂN (body) của bất kỳ ast.Try nào bên trong `ham`.

    Try lồng nhau tự động được tính: thân của try lồng bên trong vẫn là hậu
    duệ của thân try ngoài, nên đã nằm trong tập id() ở vòng quét try ngoài
    rồi — không cần xử lý đệ quy riêng.

    GIỚI HẠN ĐÃ BIẾT (final review 2026-08-15): ast.walk(stmt) đi CẢ VÀO một
    `def` lồng bên trong thân try, nên odoo() gọi trong THÂN của một hàm chỉ
    ĐỊNH NGHĨA trong try (không nhất thiết được GỌI trong try đó — vd một
    closure trả ra ngoài rồi gọi sau) vẫn bị tính là được bảo vệ, dù lúc gọi
    thật có thể đã ở ngoài phạm vi try. Không sai với bất kỳ tool nào trong
    cây hiện tại (hàm lồng duy nhất, mrp.py `_raw_moves` trong
    complete_manufacturing_order, vừa định nghĩa vừa được gọi trong CÙNG một
    try) — nhưng một closure tương lai có thể lọt qua lưới này. Không sửa
    logic ở đây (đã cân nhắc và loại — cây hiện tại không cần, thêm máy móc
    đón trước một trường hợp chưa xảy ra là suy đoán không có bằng chứng)."""
    bao_ve: set[int] = set()
    for con in ast.walk(ham):
        if isinstance(con, ast.Try):
            for stmt in con.body:
                for n in ast.walk(stmt):
                    bao_ve.add(id(n))
    return bao_ve


def _goi_odoo_ngoai_try(ham: ast.AST) -> list[ast.Call]:
    """Mọi lời gọi odoo(...) trong `ham` mà KHÔNG nằm trong tập id() được
    bảo vệ ở trên."""
    bao_ve = _cac_id_duoc_bao_ve(ham)
    ngoai = []
    for con in ast.walk(ham):
        if (isinstance(con, ast.Call) and isinstance(con.func, ast.Name)
                and con.func.id == "odoo" and id(con) not in bao_ve):
            ngoai.append(con)
    return ngoai


def _quet_file(path: Path) -> list[str]:
    """Trả một mục 'file:function:line' cho MỖI lời gọi odoo() nằm ngoài try,
    trong mọi hàm @mcp.tool() của `path`. File không parse được → rỗng (cùng
    quy ước với các scanner AST khác trong repo, vd
    test_hau_to_thong_bao_loi.quet_chuoi_goi_helper)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    ket_qua: list[str] = []
    for node in ast.walk(tree):
        if _la_tool_mcp(node):
            for call in _goi_odoo_ngoai_try(node):
                ket_qua.append(f"{path.name}:{node.name}:{call.lineno}")
    return ket_qua


# ─── Đối chiếu toàn repo ──────────────────────────────────────────────────

def test_khong_tool_nao_goi_odoo_ngoai_try():
    """Lưới chặn tool thứ 36 lặp lại lỗ hổng '12 tool không try' (xem
    docstring module)."""
    vi_pham = []
    for p in sorted(TOOLS_DIR.glob("*.py")):
        vi_pham += _quet_file(p)
    assert vi_pham == [], (
        "gọi odoo(...) ngoài try trong tool MCP — exception sẽ xuyên thẳng "
        "qua tool, bỏ qua helpers.fail() (mất cả logger tiến trình lẫn "
        "đường ghi audit qua đó):\n" + "\n".join(vi_pham))


# ─── Kiểm chính bộ quét ───────────────────────────────────────────────────

def _quet_nguon(tmp_path, nguon: str) -> list[str]:
    p = tmp_path / "vidu.py"
    p.write_text(nguon, encoding="utf-8")
    return _quet_file(p)


def test_luoi_phan_biet_trong_try_va_ngoai_try(tmp_path):
    """Kiểm chính bộ quét bằng một AST tổng hợp có CẢ HAI hình dạng: một hàm
    @mcp.tool() gọi odoo() BÊN TRONG try (không được báo) và một hàm gọi
    odoo() HOÀN TOÀN NGOÀI try (phải bị báo). Một bộ quét luôn báo hết hoặc
    luôn im lặng (net vô dụng theo cả hai hướng) sẽ vẫn xanh nếu chỉ kiểm
    một chiều — hình dạng lỗi này đã xảy ra ba lần trên nhánh dự án này rồi,
    nên khoá cả hai chiều trong cùng một test."""
    nguon = (
        "@mcp.tool()\n"
        "def an_toan():\n"
        "    try:\n"
        "        return odoo('x', 'y', [])\n"
        "    except Exception as e:\n"
        "        return fail('an_toan', 'loi', e)\n"
        "\n"
        "@mcp.tool()\n"
        "def khong_an_toan():\n"
        "    return odoo('x', 'y', [])\n"
    )
    ds = _quet_nguon(tmp_path, nguon)
    ten_ham_bi_bao = {d.split(":")[1] for d in ds}
    assert ten_ham_bi_bao == {"khong_an_toan"}, (
        "bộ quét phải bắt ĐÚNG hàm không có try, và KHÔNG báo hàm đã có "
        f"try: thấy {ten_ham_bi_bao!r}")


def test_luoi_bo_qua_ham_khong_phai_mcp_tool(tmp_path):
    """Đối chứng: một hàm KHÔNG có decorator @mcp.tool() gọi odoo() ngoài try
    (vd helper nội bộ) không thuộc phạm vi test này — chỉ tool đã đăng ký với
    FastMCP mới bị soi."""
    nguon = (
        "def helper_noi_bo():\n"
        "    return odoo('x', 'y', [])\n"
    )
    ds = _quet_nguon(tmp_path, nguon)
    assert ds == []
