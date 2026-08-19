import re

from docx import Document
import openpyxl
import pypdf

# Nhánh số CHỈ nhận numbering đa cấp ("1.1", "3.2.1"), sub-level 1-2 chữ số:
# numbering 1 cấp ("1. ...") là KHOẢN (nội dung) trong luật VN chứ không phải
# heading, còn nhóm 3 chữ số là dấu phân cách nghìn ("5.000.000.000 đồng.")
# hoặc mã HS phụ lục ("2931.9080") — cả ba từng bị nhận nhầm heading khiến
# chunking nuốt nội dung (spec 2026-07-15-rag-heading-detection-fix).
_HEADING_RE = re.compile(
    r"^\s*(Chương|Mục|Điều)\b"
    r"|^\s*\d+\.\d{1,2}(\.\d{1,2})*(?!\d)[\.\)]?\s+\S")


_DIGITS_RE = re.compile(r"\d+")


def _normalize_digits(text: str) -> str:
    """Thay mọi chuỗi chữ số bằng '#'.

    Không có bước này thì bộ lọc tần suất bỏ sót hoàn toàn: 'about:blank 5/164'
    và 'about:blank 6/164' là hai chuỗi khác nhau, mỗi cái chỉ xuất hiện đúng
    một trang."""
    return _DIGITS_RE.sub("#", text)


def detect_page_furniture(pages: list[list[str]], *, min_pages: int = 5,
                          page_ratio: float = 0.6, edge_ratio: float = 0.9,
                          edge: int = 2) -> set[str]:
    """Dạng-đã-chuẩn-hoá của các dòng là header/footer trang.

    Điều kiện KÉP, không phải hoặc (spec 2026-08-19-ingest-hygiene §3):
      (a) xuất hiện trên >= page_ratio số trang, VÀ
      (b) >= edge_ratio số lần xuất hiện nằm trong `edge` dòng đầu hoặc cuối
          của trang.

    Vì sao cần (b): chuẩn hoá chữ số gộp NHIỀU hàng bảng khác nhau thành một
    nhóm. Đo thật trên luat-thuexuatnhapkhau.pdf: nhóm '# #.#' (hàng bảng mã
    HS) đạt 48% số trang — chỉ thoát ngưỡng 60% nhờ 12 điểm phần trăm, quá
    mỏng để tin. Với (b) thì nó ra 15% và bị loại dứt khoát, trong khi 18 nhóm
    rác thật của 9 tệp đều đạt 100%/100%.

    Vì sao không khớp mẫu 'about:blank': đó là dấu vết của CÁCH IN bộ PDF này
    (print-to-PDF từ trình duyệt). Tài liệu nguồn khác mang rác khác; tần suất
    bắt được cả loại chưa gặp, khớp mẫu cứng thì không.
    """
    n_pages = len(pages)
    if n_pages < min_pages:
        return set()
    seen_pages: dict[str, set[int]] = {}
    at_edge: dict[str, int] = {}
    total: dict[str, int] = {}
    for pageno, lines in enumerate(pages):
        for i, text in enumerate(lines):
            key = _normalize_digits(text)
            seen_pages.setdefault(key, set()).add(pageno)
            total[key] = total.get(key, 0) + 1
            if i < edge or i >= len(lines) - edge:
                at_edge[key] = at_edge.get(key, 0) + 1
    return {key for key, pgs in seen_pages.items()
            if len(pgs) / n_pages >= page_ratio
            and at_edge.get(key, 0) / total[key] >= edge_ratio}


def parse_docx(path: str) -> list[dict]:
    """Blocks in order; a heading block carries heading_level (1..n), body carries None."""
    doc = Document(path)
    blocks: list[dict] = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "") if p.style else ""
        level = None
        if style.startswith("Heading"):
            try:
                level = int(style.split()[-1])
            except ValueError:
                level = 1
        blocks.append({"text": text, "heading_level": level, "page": None})
    return blocks


def parse_pdf(path: str) -> list[dict]:
    """Heuristic headings (no font info): numbered/keyword headings & short ALL-CAPS lines."""
    reader = pypdf.PdfReader(path)
    blocks: list[dict] = []
    for pageno, page in enumerate(reader.pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            # pypdf maps some unrecognized glyphs (e.g. a custom bullet-point
            # font) to U+0000 instead of dropping them; Postgres text columns
            # reject NUL bytes outright, so strip them at the source.
            text = line.replace("\x00", "").strip()
            if not text:
                continue
            is_heading = bool(_HEADING_RE.match(text)) or (
                text.isupper() and len(text) <= 80
            )
            blocks.append({"text": text,
                           "heading_level": 2 if is_heading else None,
                           "page": pageno})
    return blocks


def parse_xlsx(path: str) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[dict] = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c is not None for c in r)]
        if not rows:
            continue
        header = [str(c) if c is not None else "" for c in rows[0]]
        sheets.append({"sheet": ws.title, "columns": header, "rows": rows[1:]})
    wb.close()
    return sheets
