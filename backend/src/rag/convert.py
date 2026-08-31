"""Cầu chuyển đổi định dạng cũ qua LibreOffice — spec 2026-08-29 mục 5.1.

Task 3 hoàn thiện; Task 2 chỉ cần `soffice_path()` để nhánh từ chối chạy được.
"""
import os
import shutil

SOFFICE_ENV = "SOFFICE_PATH"

_FALLBACK_PATHS = (
    r"C:\Users\ADMIN\scoop\apps\libreoffice\current\LibreOffice\program\soffice.exe",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
)


def soffice_path() -> str | None:
    """Đường dẫn soffice, hoặc None nếu không tìm thấy.

    Thứ tự: biến môi trường → PATH → vài vị trí quen thuộc. KHÔNG viết cứng
    một đường dẫn duy nhất: máy dev hiện tại cài qua scoop vào thư mục người
    dùng, máy khác sẽ khác (spec mục 5.1.1, "nợ triển khai")."""
    env = os.environ.get(SOFFICE_ENV)
    if env and os.path.isfile(env):
        return env
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for p in _FALLBACK_PATHS:
        if os.path.isfile(p):
            return p
    return None
