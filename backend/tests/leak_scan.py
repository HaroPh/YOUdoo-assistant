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
Bản thân regex/hàm quét được kiểm bằng test_leak_scan.py."""
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
