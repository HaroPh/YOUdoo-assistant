import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree
import openpyxl
import pypdf

# Nhánh số CHỈ nhận numbering đa cấp ("1.1", "3.2.1"), sub-level 1-2 chữ số:
# numbering 1 cấp ("1. ...") là KHOẢN (nội dung) trong luật VN chứ không phải
# heading, còn nhóm 3 chữ số là dấu phân cách nghìn ("5.000.000.000 đồng.")
# hoặc mã HS phụ lục ("2931.9080") — cả ba từng bị nhận nhầm heading khiến
# chunking nuốt nội dung (spec 2026-07-15-rag-heading-detection-fix).
#
# Nhánh `Điều` SIẾT LẠI 2026-08-19 (spec ingest-hygiene §4): trước đây là
# `^\s*(Chương|Mục|Điều)\b`, nên khớp cả tham chiếu chéo GIỮA câu — "Điều 11
# của Luật này quy định.", "Điều ước quốc tế mà Cộng hòa..." — sinh ra 15 mục
# là mảnh câu, mỗi mảnh CẮT ĐÔI một Điều thật. Đây là lỗi ingest DUY NHẤT đã
# chứng minh gây hại đo được: chuỗi "Điều ước quốc tế..." chiếm hạng 1 của một
# câu hỏi thật (spec P0 §11.1(b)). Nay `Điều` phải mang dạng "Điều <số>." rồi
# mới tới tiêu đề.
#
# `Chương` và `Mục` GIỮ NGUYÊN: chúng sinh 190 mục trống, nhưng đó là việc của
# P3b (phân cấp) — đụng vào đây là trộn thêm một biến vào cùng một lần re-index.
_HEADING_RE = re.compile(
    r"^\s*(Chương|Mục)\b"
    r"|^\s*Điều\s+\d+\s*[\.\-–]\s*\S"
    r"|^\s*\d+\.\d{1,2}(\.\d{1,2})*(?!\d)[\.\)]?\s+\S")

_CHUONG_RE = re.compile(r"^\s*Chương\b")
_MUC_RE = re.compile(r"^\s*Mục\b")
_DIEU_RE = re.compile(r"^\s*Điều\s+\d+\s*[\.\-–]\s*\S")


def heading_level(text: str) -> int | None:
    """Cấp của một dòng tiêu đề, hoặc None nếu không phải tiêu đề.

    TRƯỚC 2026-08-20 mọi tiêu đề đều là cấp 2, tức `Chương`, `Mục` và `Điều`
    là ANH EM. Vì `chunk_text_blocks` đẩy khỏi stack mọi mục cùng-hoặc-cao-cấp,
    "Điều 102" hất "Chương VI" ra và section_path thành PHẮNG.

    Tác hại đo được: 27 cặp điều luật trong corpus TRÙNG TIÊU ĐỀ từng chữ, và
    thứ phân biệt chúng nằm ở chương. Ví dụ đã bắt được trong bộ synthesis_live:

        Điều 70  ← Chương V  — BẢO HIỂM XÃ HỘI BẮT BUỘC
        Điều 102 ← Chương VI — BẢO HIỂM XÃ HỘI TỰ NGUYỆN

    cả hai cùng tên "Hưởng bảo hiểm xã hội một lần". Hỏi về TỰ NGUYỆN thì cả
    dense lẫn cross-encoder đều chọn Điều 70, vì từ "tự nguyện" không dính vào
    văn bản index của Điều 102 — trớ trêu là nó lại nằm trong THÂN Điều 70
    ("không bao gồm số tiền ngân sách nhà nước hỗ trợ đóng bảo hiểm xã hội tự
    nguyện"). Đáp án đúng không lọt nổi top-6.

    THANG CẤP và lý do khoảng cách:

        1  Chương
        2  dòng IN HOA          — tiêu đề của chương nằm ở DÒNG SAU số chương
                                  ("Chương VI" / "BẢO HIỂM XÃ HỘI TỰ NGUYỆN"),
                                  và chính nó mang từ phân biệt. Phải nằm GIỮA
                                  Chương và Mục: để cùng cấp với Mục thì Mục đầu
                                  tiên sẽ hất nó ra và mất đúng từ đó.
        3  Mục
        4  Điều
        5  numbering đa cấp

    Dòng IN HOA ở cấp 2 còn là hàng rào an toàn: một dòng IN HOA lạc giữa
    chương (vd "ĐIỀU KHOẢN THI HÀNH" in giữa văn bản) chỉ hất được các Mục,
    KHÔNG hất được Chương — nên chương vẫn sống sót cho mọi điều phía sau.
    """
    if _CHUONG_RE.match(text):
        return 1
    if _MUC_RE.match(text):
        return 3
    if _DIEU_RE.match(text):
        return 4
    if _HEADING_RE.match(text):
        return 5      # numbering đa cấp "1.1", "3.2.1"
    if text.isupper() and len(text) <= 80:
        return 2
    return None



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


# "hiệu lực THI HÀNH từ ngày ..." — KHÔNG phải "có hiệu lực từ ngày ...".
# Cụm "có hiệu lực" xuất hiện dày đặc trong NỘI DUNG điều luật (hiệu lực của
# hợp đồng, của giao dịch dân sự), và bản đầu của regex này khớp đúng chúng:
# đo trên 9 PDF thì 8 tệp trả về câu về hiệu lực HỢP ĐỒNG, chỉ 1 tệp ra ngày
# thật. Chữ "thi hành" là thứ phân biệt ngày của CHÍNH VĂN BẢN với mọi cách
# dùng khác.
_EFFECTIVE_RE = re.compile(
    r"hiệu\s+lực\s+thi\s+hành\s+(?:kể\s+)?từ\s+ngày\s+"
    r"(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE)


def extract_effective_date(text: str | None):
    """Ngày hiệu lực của văn bản, hoặc None.

    None là kết quả HỢP LỆ, không phải lỗi: 8 tài liệu nghiệp vụ (.docx,
    .xlsx) trong corpus không phải văn bản quy phạm và không có ngày hiệu lực.
    Cả 9/9 PDF luật thì đều đọc được ngày (đo 2026-08-20 trên DB thật).

    Con số 9/9 này SỬA LẠI một phép đo sai của chính tôi. Phép đo đầu báo 8/9
    vì nó đi tìm MỤC mang tên "Hiệu lực thi hành"; `luat-doanhnghiep.pdf` đặt
    tên mục là "Điều khoản thi hành" nên bị bỏ sót, dù câu "Luật này có hiệu
    lực thi hành từ ngày 01 tháng 01 năm 2021" nằm ngay trong đó. Tìm theo CÂU
    trên toàn văn không phụ thuộc vào cách đặt tên mục, nên bắt được cả hai.

    Ngày không hợp lệ (45 tháng 13) trả None thay vì ném: một cú trích hỏng
    không được làm vỡ việc ingest cả tài liệu."""
    import datetime as _dt
    if not text:
        return None
    m = _EFFECTIVE_RE.search(text)
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    try:
        return _dt.date(year, month, day)
    except ValueError:
        return None


def _bang_thanh_text(tbl) -> str:
    """Một bảng .docx thành text nhiều dòng, mỗi dòng một hàng, cột ngăn bởi "|".

    Giữ HÀNG TIÊU ĐỀ ở dòng đầu vì đó là thứ mang nghĩa cho mọi hàng dưới: một
    ô "5%" tách khỏi cột "Chiết khấu" là vô nghĩa.

    Ô gộp (merged) làm `row.cells` lặp lại cùng nội dung — chấp nhận, vì lặp
    một nhãn còn hơn mất nó.
    """
    dong = []
    for hang in tbl.rows:
        o = [c.text.strip().replace("\n", " ") for c in hang.cells]
        if any(o):
            dong.append(" | ".join(o))
    return "\n".join(dong)


def parse_docx(path: str) -> list[dict]:
    """Blocks in order; a heading block carries heading_level (1..n), body carries None.

    DUYỆT THÂN TÀI LIỆU THEO THỨ TỰ, không phải `doc.paragraphs` rồi `doc.tables`.
    Trước 2026-08-22 hàm này chỉ đọc `doc.paragraphs`, tức **bỏ 100% bảng biểu** —
    bảng chính sách chiết khấu, SLA, định mức bị nuốt sạch. Tệ hơn: tệp vẫn sinh
    chunk từ các đoạn văn nên `IngestError` KHÔNG kích hoạt, và trợ lý tự tin trả
    lời "chính sách không quy định" cho thứ có trong tài liệu.

    Vì sao không thể chỉ nối thêm `for t in doc.tables`: `chunk_text_blocks` dựng
    `section_path` theo THỨ TỰ block, nên dồn mọi bảng xuống cuối sẽ gắn chúng vào
    chương SAI. Bảng bị gắn nhầm chương còn nguy hiểm hơn bảng bị bỏ — nó trả lời
    sai một cách tự tin thay vì im lặng.

    `doc.element.body` là nơi duy nhất giữ đúng thứ tự xen kẽ đoạn văn / bảng;
    `doc.paragraphs` cũng KHÔNG chứa đoạn nằm bên trong ô bảng.
    """
    doc = Document(path)
    blocks: list[dict] = []
    for child in doc.element.body.iterchildren():
        tag = etree.QName(child).localname if hasattr(child, "tag") else ""
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or "") if para.style else ""
            level = None
            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
            blocks.append({"text": text, "heading_level": level, "page": None})
        elif tag == "tbl":
            text = _bang_thanh_text(Table(child, doc))
            if text:
                # heading_level=None: bảng là THÂN, không bao giờ là tiêu đề —
                # để nó thành heading sẽ phá breadcrumb của cả mục.
                blocks.append({"text": text, "heading_level": None, "page": None})
    return blocks


def parse_pdf(path: str) -> list[dict]:
    """Heuristic headings (no font info): numbered/keyword headings & short ALL-CAPS lines.

    HAI LƯỢT từ 2026-08-19: gom dòng theo trang trước, nhận diện rác
    header/footer trên toàn tài liệu, rồi mới dựng block. Một lượt thì không
    thể biết một dòng có lặp trên phần lớn số trang hay không.
    """
    reader = pypdf.PdfReader(path)
    pages: list[list[str]] = []
    for page in reader.pages:
        lines = []
        for line in (page.extract_text() or "").splitlines():
            # pypdf maps some unrecognized glyphs (e.g. a custom bullet-point
            # font) to U+0000 instead of dropping them; Postgres text columns
            # reject NUL bytes outright, so strip them at the source.
            text = line.replace("\x00", "").strip()
            if text:
                lines.append(text)
        pages.append(lines)

    furniture = detect_page_furniture(pages)
    blocks: list[dict] = []
    for pageno, lines in enumerate(pages, start=1):
        for text in lines:
            if _normalize_digits(text) in furniture:
                continue
            blocks.append({"text": text,
                           "heading_level": heading_level(text),
                           "page": pageno})
    return blocks


def _pptx_table_to_text(tbl) -> str:
    """Bảng trong slide thành text nhiều dòng, mỗi dòng một hàng, cột ngăn
    bởi "|" — CÙNG khuôn với `_bang_thanh_text` của .docx, để tầng chunk và
    tầng tổng hợp chỉ phải hiểu một dạng bảng."""
    rows = []
    for row in tbl.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _pptx_shape_type(shape):
    """`shape.shape_type` đọc PHÒNG THỦ — trả None khi không đọc được.

    python-pptx ném `NotImplementedError("Shape instance of unrecognized shape
    type")` với một `<p:sp>` không placeholder, không `prstGeom`, không
    `custGeom` và không cờ `txBox`. Đó là loại shape mà công cụ NGOÀI
    PowerPoint sinh ra — KỂ CẢ LibreOffice, tức chính cầu chuyển đổi
    `.ppt → .pptx` mà nhánh này vừa dựng. Không ai bắt lỗi đó ở phía trên nên
    nó sẽ sập TRỌN `ingest_path` và mất báo cáo của mọi tệp trước đó."""
    try:
        return shape.shape_type
    except NotImplementedError:
        return None


def _pptx_xml_text(shape) -> str:
    """Mọi nút `a:t` trong XML của shape, nối bằng xuống dòng.

    Lưới an toàn cuối cùng cho shape không có `text_frame` mà vẫn mang chữ."""
    el = getattr(shape, "element", None)
    if el is None:
        return ""
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    try:
        parts = [(t.text or "").strip() for t in el.findall(".//a:t", ns)]
    except Exception:
        return ""
    return "\n".join(p for p in parts if p).strip()


def _pptx_shape_blocks(shape, page: int, title_shape) -> list[dict]:
    """Blocks từ MỘT shape của slide, ĐỆ QUY vào group shape.

    Sự thật đo được (python-pptx 1.0.2): một group shape (PowerPoint "Group
    Objects") xuất hiện ở `slide.shapes` như MỘT shape duy nhất, và chính
    shape đó có `has_table = False` VÀ `has_text_frame = False` — bảng/textbox
    thật nằm bên trong `shape.shapes` (con của group), không lộ ra ở cấp
    ngoài. Vòng lặp cũ chỉ kiểm `has_table`/`has_text_frame` ở cấp ngoài nên
    bỏ qua toàn bộ group: nội dung bên trong biến mất KHỎI CORPUS MÀ KHÔNG CÓ
    CẢNH BÁO NÀO — slide vẫn có tiêu đề nên vẫn sinh block, báo cáo nạp vẫn
    "thành công". Group có thể lồng nhiều tầng (group trong group), nên đây
    phải là đệ quy thật — mở đúng MỘT tầng rồi dừng vẫn để lọt group lồng.
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    if _pptx_shape_type(shape) is MSO_SHAPE_TYPE.GROUP:
        blocks: list[dict] = []
        for sub_shape in getattr(shape, "shapes", ()):
            blocks.extend(_pptx_shape_blocks(sub_shape, page, title_shape))
        return blocks
    if getattr(shape, "has_table", False):
        text = _pptx_table_to_text(shape.table)
        return [{"text": text, "heading_level": None, "page": page}] if text else []
    if getattr(shape, "has_text_frame", False):
        if title_shape is not None and shape is title_shape:
            return []
        text = shape.text_frame.text.strip()
        return [{"text": text, "heading_level": None, "page": page}] if text else []

    # Không rơi vào nhánh nào ở trên. KHÔNG được trả [] ngay: đó đúng là cách
    # group shape từng mất im lặng. Quét mọi nút văn bản `a:t` trong XML của
    # shape — bắt được các shape lạ có chữ mà python-pptx không dựng thành
    # text_frame.
    text = _pptx_xml_text(shape)
    if text:
        return [{"text": text, "heading_level": None, "page": page}]

    # Vẫn không có chữ nào. Nếu ĐỌC ĐƯỢC loại shape (ảnh, đường kẻ, media...)
    # thì im lặng là đúng — chúng vốn không mang chữ. Nhưng `shape_type` bằng
    # None nghĩa là python-pptx KHÔNG NHẬN RA shape: với GraphicFrame đó gần
    # như luôn là SmartArt (`GraphicFrame.shape_type` trả None khi graphicData
    # không phải table/chart/OLE). Nội dung SmartArt nằm trong một part sơ đồ
    # riêng mà parser này chưa đọc — nên phải để lại DẤU VẾT QUAN SÁT ĐƯỢC,
    # đúng nguyên tắc "không bao giờ mất im lặng" của spec 2026-08-29 mục 4.
    if _pptx_shape_type(shape) is None:
        name = (getattr(shape, "name", "") or "").strip() or "không tên"
        return [{"text": f"[NỘI DUNG CHƯA ĐỌC ĐƯỢC] shape \"{name}\" trên slide "
                         f"{page} thuộc loại python-pptx không nhận ra (thường "
                         f"là SmartArt). Nội dung của nó KHÔNG có trong corpus.",
                 "heading_level": None, "page": page}]
    return []


def parse_pptx(path: str) -> list[dict]:
    """Blocks theo thứ tự slide; `page` mang SỐ SLIDE (từ 1).

    Tiêu đề slide thành heading cấp 1 — đó là phân cấp duy nhất một bộ slide
    có. Ghi chú thuyết trình được giữ vì trong tài liệu nội bộ chúng thường
    chứa điều kiện và ngoại lệ mà slide chỉ nói tóm tắt.
    """
    from pptx import Presentation

    prs = Presentation(path)
    blocks: list[dict] = []
    for idx, slide in enumerate(prs.slides, start=1):
        title_shape = slide.shapes.title
        title = (title_shape.text or "").strip() if title_shape is not None else None
        if title:
            blocks.append({"text": title, "heading_level": 1, "page": idx})

        for shape in slide.shapes:
            blocks.extend(_pptx_shape_blocks(shape, idx, title_shape))

        if slide.has_notes_slide:
            note = (slide.notes_slide.notes_text_frame.text or "").strip()
            if note:
                blocks.append({"text": f"Ghi chú: {note}",
                               "heading_level": None, "page": idx})
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
