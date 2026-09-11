"""Trích tài liệu cho endpoint HTTP — module LÁ, không biết gì về FastAPI.

Vì sao tách khỏi `main.py`: phần nặng (chọn parser, gom trang, quyết định
rỗng) phải test được mà không cần dựng client HTTP. `main.py` chỉ còn lo xác
thực, tệp tạm và ánh xạ lỗi sang mã HTTP.

Vì sao module này tồn tại: đo 2026-09-09, Open WebUI trích `DVT_2022.pdf`
(scan 16 trang, 5,1 MB) ra 15 ký tự toàn dấu cách, `status=failed`, và người
dùng chỉ thấy "không tìm thấy tài liệu liên quan". Repo này đã có OCR đọc được
chính tệp đó, nhưng không route nào nhận tệp nên năng lực đó chưa bao giờ tới
được người dùng.
"""
import os

from .chunking import _gop_bi_quan
from .parse import parse_docx, parse_pdf, parse_pptx, parse_xlsx


class UnsupportedFormat(ValueError):
    """Đuôi tệp không nạp thẳng được."""


class EmptyExtraction(ValueError):
    """Không trích được nội dung nào — người gọi PHẢI báo lỗi, không trả rỗng."""


# Đuôi -> loại parser. PHẢI khớp `ingest._EXT`; có test bất biến giữ điều đó.
# `.doc`/`.xls` cần LibreOffice chuyển đổi (`convert.py`), ngoài phạm vi lát 1.
SUPPORTED_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xltx": "xlsx",
    ".pptx": "pptx",
}


def _warning_lines(warnings) -> list[str]:
    """Cảnh báo parser -> danh sách chuỗi đọc được. KHÔNG nuốt."""
    return [f"{a}: {b}" for a, b in warnings]


def _documents_from_blocks(blocks, filename, warnings, *, group_by_page):
    """Block -> list Document. Bỏ block rỗng SAU `strip()`.

    `group_by_page=False` dùng cho .docx: `parse_docx` đặt `page=None` cho mọi
    block, nên gom theo trang sẽ tạo đúng một nhóm mang khoá `None` — nhãn sai
    còn tệ hơn không có nhãn.
    """
    kept = [b for b in blocks if (b.get("text") or "").strip()]
    if not kept:
        return []
    lines = _warning_lines(warnings)
    if not group_by_page:
        return [{"page_content": "\n".join(b["text"] for b in kept),
                 "metadata": {"source": filename, "warnings": lines}}]

    by_page: dict = {}
    for b in kept:
        by_page.setdefault(b.get("page"), []).append(b)
    docs = []
    for page in sorted(by_page, key=lambda p: (p is None, p)):
        group = by_page[page]
        # Bậc xuất xứ XẤU NHẤT của trang + conf nhỏ nhất — cùng quy tắc với
        # chunking (`_gop_bi_quan`). Trước 2026-09-11 dòng này gộp thành
        # `"ocr" if any(... == "ocr") else "text"`: một trang toàn hàng VLM chưa
        # kiểm sẽ mang nhãn "text", bậc tin cậy CAO NHẤT — sai đúng chiều duy
        # nhất trường này không được sai.
        kind, conf = _gop_bi_quan([(b["text"], b.get("source_kind", "text"), b.get("ocr_conf"))
                                   for b in group])
        meta = {"source": filename, "source_kind": kind, "ocr_conf": conf,
                # Cảnh báo gắn vào MỌI document chứ không riêng cái đầu: Open
                # WebUI cắt chunk theo từng document, nên gắn một chỗ nghĩa là
                # phần lớn chunk mất cảnh báo.
                "warnings": lines}
        if page is not None:
            meta["page"] = page
        docs.append({"page_content": "\n".join(b["text"] for b in group),
                     "metadata": meta})
    return docs


def _documents_from_sheets(sheets, filename, warnings):
    """Bảng tính: đơn vị tách là SHEET, không phải trang.

    `parse_xlsx` trả `sheets` (khoá `sheet`/`columns`/`rows`) chứ không trả
    block có `page`, nên nó không đi qua `_documents_from_blocks` được.
    """
    lines = _warning_lines(warnings)
    docs = []
    for sh in sheets:
        # Lọc hàng per-cell trước khi nối: giữ chỉ hàng có ít nhất một ô không rỗng
        kept = [row for row in sh["rows"]
                if any(c is not None and str(c).strip() for c in row)]
        if not kept:
            continue
        rows = [" | ".join("" if c is None else str(c) for c in row)
                for row in kept]
        # Áp dụng cùng logic cho header: kiểm tra xem có ô không rỗng nào không
        has_header = any(c is not None and str(c).strip() for c in sh["columns"])
        header = " | ".join("" if c is None else str(c) for c in sh["columns"])
        body = [header] + rows if has_header else rows
        docs.append({
            "page_content": "\n".join(body),
            "metadata": {"source": filename, "sheet": sh["sheet"],
                         "source_kind": "text", "warnings": lines},
        })
    return docs


def extract_documents(path: str, filename: str) -> list[dict]:
    """Tệp -> list {"page_content", "metadata"}, một phần tử mỗi trang/sheet.

    `path` là tệp TẠM (đuôi ngẫu nhiên); `filename` là tên thật do người dùng
    gửi và là NGUỒN DUY NHẤT để chọn parser — không đoán định dạng từ nội dung.

    Ném `EmptyExtraction` khi không còn nội dung nào sau `strip()`. Người gọi
    PHẢI báo lỗi thay vì trả 200 với chuỗi rỗng: đó đúng là hành vi của Open
    WebUI mà endpoint này sinh ra để thay thế.

    `TesseractMissing` từ `parse_pdf` được thả LÊN nguyên vẹn — người gọi ánh
    xạ nó thành 503, vì "thiếu binary" khác hẳn "tài liệu không có chữ".
    """
    ext = os.path.splitext(filename)[1].lower()
    kind = SUPPORTED_EXT.get(ext)
    if kind is None:
        raise UnsupportedFormat(
            f"duoi {ext or '(khong co)'} khong nap thang duoc. "
            f"Ho tro: {', '.join(sorted(SUPPORTED_EXT))}")

    if kind == "pdf":
        blocks, warnings = parse_pdf(path)
        docs = _documents_from_blocks(blocks, filename, warnings,
                                      group_by_page=True)
    elif kind == "pptx":
        docs = _documents_from_blocks(parse_pptx(path), filename, [],
                                      group_by_page=True)
    elif kind == "docx":
        docs = _documents_from_blocks(parse_docx(path), filename, [],
                                      group_by_page=False)
    else:
        sheets, warnings = parse_xlsx(path)
        docs = _documents_from_sheets(sheets, filename, warnings)

    if not docs:
        raise EmptyExtraction(
            f"{filename}: khong trich duoc noi dung nao. Voi PDF, day thuong "
            f"la ban scan ma tang OCR cung khong doc ra chu.")
    return docs
