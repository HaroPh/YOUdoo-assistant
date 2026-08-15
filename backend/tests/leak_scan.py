# backend/tests/leak_scan.py
"""Bộ quét dùng chung: phát hiện chỗ nội suy nguyên văn exception vào chuỗi
hiển thị người dùng (f"...{e}", f"...{exc}", f"...{err}"...).

Ruling D (2026-08-15-error-hygiene-and-audit-trail, task-3): Task 3/4/5/6 mỗi
task đều cần quét lại lớp lỗi này trên một tập file khác nhau (tool MCP,
đường đọc, điều phối viết, toàn repo). Bốn bản sao gần giống nhau của cùng
một regex + hàm quét là một lỗi thiết kế — nên logic quét sống Ở ĐÂY MỘT LẦN,
bốn task còn lại import từ đây (`from tests.leak_scan import ...`).

Không có tiền tố `test_` nên pytest KHÔNG thu thập module này như một test
(cùng khuôn mẫu với tests/live_verify_common.py + test_live_verify_common.py).
Bản thân regex/hàm quét được kiểm bằng test_leak_scan.py.

Ruling I (task-6): hai lưới BỔ SUNG cho nhau, không lưới nào thay được lưới
kia.
  - RO_LOI/quet_file (regex) chỉ biết ba tên biến e/exc/err — Task 4 phát
    hiện `except Exception as ex:` lọt lưới hoàn toàn vì `ex` không nằm
    trong danh sách. Thêm tên vào regex là lặp lại đúng lỗi "liệt kê" mà
    Task 6 tồn tại để sửa.
  - quet_ast_file (AST) tổng quát hoá: với MỌI `except ... as TÊN:`, tìm
    f-string nội suy TÊN — phủ MỌI cách đặt tên, kể cả tên chưa ai nghĩ tới.
    Nhưng AST chỉ nhìn thấy exception đến từ except-binding; biến exception
    đến từ nơi khác (ví dụ tham số hàm) nằm ngoài phạm vi nó — ví dụ đo
    được: mcp-servers/odoo/helpers.py xây `f"{type(exc).__name__}: {exc}"`
    với `exc` là THAM SỐ của `fail()`, không phải except-binding; regex bắt
    được (đúng vai trò của nó — dòng này build audit-trail nội bộ, không ra
    người dùng, xem MIEN_TRU ở test_khong_ro_loi_exception.py), AST thì
    không, đúng như thiết kế.
Giữ cả hai."""
import ast
import re
from pathlib import Path

# Bắt mọi nội suy f-string của biến exception thông dụng: {e}, {exc}, {err},
# kể cả có định dạng phía sau ({e!r}, {e:s}).
RO_LOI = re.compile(r"\{\s*(e|exc|err)\s*[!:}]")


def quet_file(path: Path, nhan: str | None = None) -> list[str]:
    """Trả ["<nhãn>:<số dòng>: <nội dung dòng>"] cho mọi dòng khớp RO_LOI.

    `nhan` mặc định là path.name (Task 3/4/5 dùng); Task 6 truyền đường dẫn
    tương đối so với gốc repo.
    """
    nhan = path.name if nhan is None else nhan
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if RO_LOI.search(line):
            out.append(f"{nhan}:{i}: {line.strip()}")
    return out


def _bieu_thuc_dung_ten(expr: ast.AST, ten: str) -> bool:
    """True nếu biểu thức bên trong `{...}` có nhắc tới biến `ten` ở bất kỳ
    đâu trong biểu thức — {ten}, {ten!r}, {ten:s}, {str(ten)}, {ten.args[0]}."""
    return any(isinstance(n, ast.Name) and n.id == ten for n in ast.walk(expr))


def quet_ast_file(path: Path, nhan: str | None = None) -> list[str]:
    """Lưới AST: với MỌI `except ... as TÊN:`, tìm f-string bên trong khối
    đó có nội suy TÊN. Xem docstring module cho lý do có lưới này bên cạnh
    RO_LOI/quet_file (Ruling I) — chúng bổ sung, không thay thế nhau.

    Trả cùng khuôn dạng ["<nhãn>:<số dòng>: <nội dung dòng>"] như quet_file,
    một dòng một mục dù dòng đó nội suy TÊN nhiều lần (khớp cách đếm của
    quet_file: mỗi DÒNG tính một lần).

    File không parse được (SyntaxError, vd file .py hỏng cú pháp trong
    fixture/spike) trả [] thay vì làm sập cả bộ test — quét lỗi cú pháp
    không phải việc của lưới này.
    """
    nhan = path.name if nhan is None else nhan
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    dong = text.splitlines()
    so_dong_ro: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and node.name):
            continue
        ten = node.name
        for sub in ast.walk(node):
            if isinstance(sub, ast.JoinedStr) and any(
                isinstance(gia_tri, ast.FormattedValue)
                and _bieu_thuc_dung_ten(gia_tri.value, ten)
                for gia_tri in sub.values
            ):
                so_dong_ro.add(sub.lineno)
    return [f"{nhan}:{i}: {dong[i - 1].strip()}" for i in sorted(so_dong_ro)]
