"""Cầu chuyển đổi định dạng cũ qua LibreOffice — spec 2026-08-29 mục 5.1.

Task 3 hoàn thiện; Task 2 chỉ cần `soffice_path()` để nhánh từ chối chạy được.
"""
import os
import shutil
import subprocess
import tempfile
import zipfile

SOFFICE_ENV = "SOFFICE_PATH"
CONVERT_CACHE_ENV = "YOUDOO_CONVERT_CACHE"

# Đuôi cũ → đuôi đích (không có dấu chấm, đúng dạng soffice --convert-to nhận)
TARGET_EXT = {
    ".doc": "docx", ".rtf": "docx", ".odt": "docx",
    ".xls": "xlsx", ".ods": "xlsx",
    ".ppt": "pptx", ".odp": "pptx",
}

CONVERT_TIMEOUT_S = 180


class ConverterMissing(RuntimeError):
    """Không tìm thấy LibreOffice."""


class ConvertFailed(RuntimeError):
    """Đã gọi LibreOffice nhưng không có tệp đầu ra dùng được."""


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


def cache_dir() -> str:
    d = os.environ.get(CONVERT_CACHE_ENV) or os.path.join(
        tempfile.gettempdir(), "youdoo_convert")
    os.makedirs(d, exist_ok=True)
    return d


def _profile_uri() -> str:
    """Profile LibreOffice dùng lại giữa các lượt gọi.

    Đo 2026-08-30: lượt chuyển ĐẦU tốn 17,5 giây vì dựng profile, các lượt
    sau 5,2 giây. Không giữ profile thì mọi tệp đều trả giá lượt đầu."""
    p = os.path.join(cache_dir(), "lo_profile").replace("\\", "/")
    return "file:///" + p.lstrip("/")


def _run_soffice(soffice: str, path: str, target: str, outdir: str) -> str | None:
    """Gọi soffice, trả đường dẫn tệp đầu ra nếu thấy, không thì None.

    CỐ Ý KHÔNG dựa vào mã thoát: đợt cài 2026-08-30 gặp ba mã thoát nói dối,
    trong đó có một cái báo HỎNG khi thật ra đã THÀNH CÔNG."""
    try:
        subprocess.run(
            [soffice, "--headless", f"-env:UserInstallation={_profile_uri()}",
             "--convert-to", target, "--outdir", outdir, path],
            capture_output=True, timeout=CONVERT_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        # Không để TimeoutExpired lọt ra ngoài: `_ingest_convertible` chỉ bắt
        # ConvertFailed/ConverterMissing, và vòng lặp ingest_path không có lá
        # chắn nào cho lỗi khác — một tệp .doc treo sẽ sập TRỌN lượt nạp và
        # mất báo cáo của mọi tệp đã xử lý trước đó. Ném ConvertFailed để
        # _ingest_convertible bắt được, tệp thành `rejected` CÓ TÊN thay vì
        # sập cả lượt.
        raise ConvertFailed(
            f"{path}: LibreOffice không phản hồi sau {CONVERT_TIMEOUT_S} giây, "
            f"đã huỷ. Tệp có thể quá lớn hoặc soffice bị treo.")
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(outdir, f"{stem}.{target}")
    return out if os.path.isfile(out) else None


def _ooxml_mo_duoc(path: str) -> bool:
    """Tệp đầu ra có phải một gói OOXML mở được không.

    Mọi đích trong `TARGET_EXT` (docx/xlsx/pptx) đều là zip có
    `[Content_Types].xml`. Phép kiểm này RẺ: `zipfile` chỉ đọc central
    directory ở cuối tệp, không giải nén gì — nhưng nó bắt đúng ca một tệp
    bị ghi dở, vì central directory là thứ được ghi SAU CÙNG. Không tin mã
    thoát, kiểm bằng SẢN PHẨM (bài học cài đặt 2026-08-30)."""
    try:
        with zipfile.ZipFile(path) as z:
            return "[Content_Types].xml" in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def convert_file(path: str, content_hash: str) -> str:
    """Chuyển tệp định dạng cũ, trả đường dẫn bản đã chuyển.

    Dùng lại bản cũ khi `content_hash` trùng — mỗi lượt gọi soffice tốn ~5s.
    """
    ext = os.path.splitext(path)[1].lower()
    target = TARGET_EXT.get(ext)
    if target is None:
        raise ConvertFailed(f"{path}: không có đích chuyển đổi cho đuôi {ext}")

    soffice = soffice_path()
    if soffice is None:
        raise ConverterMissing(
            f"{path}: cần LibreOffice để chuyển {ext} sang .{target}, nhưng "
            f"không tìm thấy soffice. Đặt biến môi trường {SOFFICE_ENV} trỏ "
            f"tới soffice.exe, hoặc cài LibreOffice.")

    outdir = os.path.join(cache_dir(), content_hash)
    stem = os.path.splitext(os.path.basename(path))[0]
    cached = os.path.join(outdir, f"{stem}.{target}")
    if os.path.isfile(cached):
        return cached

    os.makedirs(outdir, exist_ok=True)
    # GHI RA THƯ MỤC TẠM RỒI ĐỔI TÊN NGUYÊN TỬ. Trước 2026-08-31 soffice ghi
    # THẲNG vào vị trí cache: một lượt bị cắt ngang (timeout giết tiến trình
    # con, Ctrl-C, đầy đĩa) để lại một .docx CỤT ĐẦU ở đúng chỗ cache, và lượt
    # sau `os.path.isfile(cached)` trả nguyên tệp cụt mà không kiểm gì. Khoá
    # cache là hash của tệp GỐC nên nội dung không đổi thì hash không đổi →
    # BẨN VĨNH VIỄN, không bao giờ tự lành, và `parse_docx` ném
    # PackageNotFoundError làm sập trọn lượt nạp.
    staging = tempfile.mkdtemp(prefix="dangchuyen-", dir=cache_dir())
    try:
        out = _run_soffice(soffice, path, target, staging)
        if out is None:
            raise ConvertFailed(
                f"{path}: LibreOffice chạy xong nhưng không sinh tệp .{target}. "
                f"Tệp có thể hỏng hoặc được bảo vệ bằng mật khẩu.")
        if not _ooxml_mo_duoc(out):
            raise ConvertFailed(
                f"{path}: LibreOffice sinh ra {os.path.basename(out)} nhưng tệp "
                f"đó không mở được (không phải gói OOXML hợp lệ) — nhiều khả "
                f"năng lượt chuyển bị cắt ngang. KHÔNG đưa vào cache.")
        os.replace(out, cached)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return cached
