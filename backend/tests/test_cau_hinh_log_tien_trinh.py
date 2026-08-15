# backend/tests/test_cau_hinh_log_tien_trinh.py
"""Backend phải TỰ cấu hình logging ở điểm vào tiến trình.

Đo 2026-08-15: toàn repo backend không có một dòng basicConfig/dictConfig
nào. uvicorn.Config dùng log_config mặc định, và cấu hình đó chỉ chạm các
logger tên "uvicorn*" — root logger không được đụng tới. Hệ quả: cả 68 chỗ
fail_read/fail_write (logger.exception) chỉ ra được stderr nhờ handler
`lastResort` của Python — WARNING trở lên, KHÔNG timestamp, KHÔNG level,
KHÔNG tên logger — trong khi docstring của envelope.py và create_order.py
hứa hẳn "logger tiến trình — logs/backend_err.log". Và `lastResort` biến mất
im lặng ngay khi ai đó thêm một dictConfig ở chỗ khác.

Kiểm bằng VỊ TRÍ VĂN BẢN, cùng khuôn mẫu
test_audit_log_table.test_server_goi_kiem_bang_va_chi_trong_main: `import
run` sẽ dựng cả uvicorn.Config, và trong pytest thì không được phép.
"""
import ast
from pathlib import Path

RUN_PY = Path(__file__).resolve().parents[1] / "run.py"


def _cay():
    return ast.parse(RUN_PY.read_text(encoding="utf-8"))


def test_run_py_co_cau_hinh_logging():
    assert "logging.basicConfig(" in RUN_PY.read_text(encoding="utf-8"), \
        "backend không cấu hình logging ⇒ mọi logger.exception rơi vào " \
        "handler lastResort (không timestamp/level/tên logger)"


def test_cau_hinh_nam_trong_main_khong_o_cap_module():
    """Ở cấp module, dòng này gắn handler vào root logger của MỌI tiến trình
    chỉ `import run` (test, công cụ) — cùng lý do đã ghi ở
    mcp-servers/odoo/server.py cho assert_log_table_ready."""
    trong_main = False
    for node in ast.walk(_cay()):
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for con in ast.walk(node):
            if (isinstance(con, ast.Call)
                    and isinstance(con.func, ast.Attribute)
                    and con.func.attr == "basicConfig"):
                trong_main = True
    assert trong_main, "basicConfig không nằm trong main()"

    for node in _cay().body:            # cấp module, không đệ quy vào hàm
        assert not (isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "basicConfig"), \
            "basicConfig ở cấp module — mọi `import run` sẽ gắn handler"


def test_cau_hinh_chay_truoc_khi_dung_server():
    """Cấu hình sau khi uvicorn.Config đã dựng thì các dòng log lúc khởi tạo
    đã mất rồi."""
    src = RUN_PY.read_text(encoding="utf-8")
    assert src.index("logging.basicConfig(") < src.index("Config("), \
        "basicConfig phải chạy TRƯỚC khi dựng uvicorn.Config"
