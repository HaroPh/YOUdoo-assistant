"""Máy đọc chữ từ ảnh (Tesseract) — tầng 0 của spec 2026-09-04-tang-ocr §3.

Module LÁ: nhận một ảnh PIL, trả về TỪ kèm toạ độ và độ tin cậy. KHÔNG biết
PDF, trang, DB, chunk, hay ai đang gọi mình. Tầng 1 (`document.py`) lo việc
rasterise và đệm; tầng 2 (`rag/parse.py`) lo việc dùng chữ để làm gì.
"""
import logging
import os
import re
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TESSERACT_ENV = "TESSERACT_PATH"
TESSDATA_ENV = "TESSDATA_PREFIX"

# HIỆU CHỈNH BẰNG ĐO (spec §4.1), không phải mặc định của thư viện:
#
# PSM 6 — recall theo TỪ trung bình 0,865 trên 3 trang bảng, so với 0,569 của
# PSM 3 (mặc định của tesseract). Điều đáng sợ không phải PSM 3 kém, mà là nó
# hỏng KHÔNG ĐỀU giữa các trang: 0,26 trang này, 0,81 trang kia, không báo gì.
# Dùng mặc định thì một phần corpus scan sẽ biến mất âm thầm.
#
# 200 DPI — 2,5 s/trang, recall 0,865; 400 DPI ngang chất lượng nhưng chậm
# 2,4 lần; 150 DPI nhanh hơn chút nhưng recall thấp hơn.
OCR_PSM = 6
OCR_DPI = 200
OCR_LANG = "vie+eng"

# KHÔNG viết cứng một đường dẫn duy nhất — cùng lý do `convert.soffice_path()`
# đã nêu: máy dev hiện tại cài qua winget vào Program Files, máy khác sẽ khác
# (spec §18 "nợ triển khai").
_FALLBACK_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)

# `vie.traineddata` KHÔNG nằm cạnh binary trên máy dev: ghi vào Program Files
# cần quyền admin nên lúc cài đã thất bại, gói ngôn ngữ để ở thư mục người
# dùng (spec §4.1). Không trỏ đúng chỗ này thì tesseract chạy nhưng KHÔNG có
# tiếng Việt — hỏng âm thầm đúng loại spec đi đóng.
_FALLBACK_TESSDATA = (
    r"C:\Users\ADMIN\.tessdata",
    r"C:\Program Files\Tesseract-OCR\tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tessdata",
)


class TesseractMissing(RuntimeError):
    """Không tìm thấy binary tesseract."""


@dataclass(frozen=True)
class OcrWord:
    """Một TỪ tesseract đọc được, kèm toạ độ và độ tin cậy 0-100.

    Giữ toạ độ vì nó MIỄN PHÍ (tesseract xuất sẵn trong TSV) và vì bậc 2 sẽ
    cần nó để dựng lại bảng. Nguyên tắc spec §6: không mất mát ở tầng dưới,
    diễn giải ở tầng trên — vứt thông tin ở tầng 0 là không đảo ngược được.
    """
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    line_id: tuple[int, int, int]   # (block_num, par_num, line_num)


@dataclass(frozen=True)
class OcrResult:
    words: list[OcrWord]
    text: str          # dòng nối bằng "\n", từ trong dòng nối bằng " "
    mean_conf: float   # trung bình conf các TỪ; 0.0 khi không đọc được từ nào


def tesseract_path() -> str | None:
    """Đường dẫn binary tesseract, hoặc None. Thứ tự: biến môi trường → PATH
    → vài vị trí quen thuộc — ĐÚNG KHUÔN `convert.soffice_path()`."""
    env = os.environ.get(TESSERACT_ENV)
    if env and os.path.isfile(env):
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _FALLBACK_TESSERACT:
        if os.path.isfile(p):
            return p
    return None


def tessdata_prefix() -> str | None:
    """Thư mục chứa `vie.traineddata`, hoặc None."""
    env = os.environ.get(TESSDATA_ENV)
    if env and os.path.isdir(env):
        return env
    for d in _FALLBACK_TESSDATA:
        if os.path.isdir(d):
            return d
    return None


def parse_tsv(tsv: str) -> list[OcrWord]:
    """Lọc TSV của `image_to_data` xuống các TỪ thật.

    Dạng thật (đo trên tesseract 5.4.0, 2026-09-05): cột là
    `level page_num block_num par_num line_num word_num left top width height
    conf text`, và CHỈ hàng `level == 5` là từ — mọi mức thấp hơn là khung cấu
    trúc (trang/khối/đoạn/dòng) với `conf = -1` và text rỗng.

    Lọc theo `level` chứ không theo `conf >= 0`: hôm nay hai tiêu chí trùng
    nhau, nhưng `level` là thứ tesseract ĐỊNH NGHĨA, còn conf chỉ là hệ quả.
    """
    out: list[OcrWord] = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        text = c[11].strip()
        if not text:
            continue
        out.append(OcrWord(
            text=text, conf=float(c[10]),
            left=int(c[6]), top=int(c[7]), width=int(c[8]), height=int(c[9]),
            line_id=(int(c[2]), int(c[3]), int(c[4]))))
    return out


def words_to_lines(words: list[OcrWord]) -> list[str]:
    """Gom từ thành dòng theo `line_id`, GIỮ NGUYÊN thứ tự tesseract trả.

    Không sắp xếp lại theo toạ độ: tesseract đã xếp theo thứ tự đọc của nó, và
    spec §13 ghi rõ bài học "thứ tự đọc khác pdfplumber" — sắp lại ở đây là
    thêm một phỏng đoán nữa vào tầng đáng lẽ không được phỏng đoán.
    """
    lines: list[str] = []
    cur_id: tuple[int, int, int] | None = None
    cur: list[str] = []
    for w in words:
        if w.line_id != cur_id:
            if cur:
                lines.append(" ".join(cur))
            cur_id, cur = w.line_id, []
        cur.append(w.text)
    if cur:
        lines.append(" ".join(cur))
    return lines


def tesseract_version() -> str:
    """Phiên bản binary, dạng chuỗi — đi vào dấu vân tay đệm của tầng 1."""
    import pytesseract
    _dam_bao_moi_truong()
    return str(pytesseract.get_tesseract_version())


def _dam_bao_moi_truong() -> None:
    """Trỏ pytesseract vào đúng binary và đúng thư mục tessdata.

    Chỉ ĐẶT khi chưa có: người triển khai đặt sẵn biến môi trường thì phải
    thắng phỏng đoán của ta."""
    import pytesseract
    path = tesseract_path()
    if path is None:
        raise TesseractMissing(
            "không tìm thấy binary tesseract — đặt biến môi trường "
            f"{TESSERACT_ENV}, hoặc cài tesseract vào PATH")
    pytesseract.pytesseract.tesseract_cmd = path
    if not os.environ.get(TESSDATA_ENV):
        prefix = tessdata_prefix()
        if prefix:
            os.environ[TESSDATA_ENV] = prefix


def ocr_image(img, *, lang: str | None = None, psm: int | None = None) -> OcrResult:
    """Đọc chữ trong MỘT ảnh PIL. Ném `TesseractMissing` khi thiếu binary.

    lang và psm đọc từ hằng số lúc GỌI, không phải lúc định nghĩa hàm, để
    cho phép đột biến chúng lúc chạy (mục đích: Task 3 sẽ gán OCR_PSM = 3
    rồi đo lại chất lượng)."""
    import pytesseract
    _dam_bao_moi_truong()
    lang = OCR_LANG if lang is None else lang
    psm = OCR_PSM if psm is None else psm
    tsv = pytesseract.image_to_data(img, lang=lang, config=f"--psm {psm}")
    words = parse_tsv(tsv)
    mean = sum(w.conf for w in words) / len(words) if words else 0.0
    return OcrResult(words=words, text="\n".join(words_to_lines(words)),
                     mean_conf=mean)


def osd_rotation(img) -> int:
    """Góc cần xoay (0/90/180/270, theo chiều kim đồng hồ như Tesseract báo
    `Rotate:`) để trang đứng thẳng — `image_to_osd`, tất định, không tốn hạn mức.

    Trả 0 khi OSD thất bại (thiếu `osd.traineddata`, ảnh quá ít chữ) — không
    làm vỡ lượt đọc; tầng tài liệu ghi góc vào artifact nên "0 vì thất bại" và
    "0 vì đứng thẳng" phân biệt được qua log, không qua dữ liệu. Đo 2026-09-11
    trên 281 trang scan: 27 trang OSD báo xoay; 20 xoay thật (conf 43→86, số
    tiền đọc được 0→20..57), 7 báo sai với độ tin OSD 0–3 — nên tầng tài liệu
    KHÔNG tin OSD một chiều mà đọc cả hai hướng và giữ hướng tốt hơn."""
    import pytesseract
    _dam_bao_moi_truong()
    try:
        out = pytesseract.image_to_osd(img, config="--psm 0")
    except Exception as e:                                  # noqa: BLE001
        logger.warning("OSD thất bại, coi như không xoay: %s: %s", type(e).__name__, e)
        return 0
    m = re.search(r"Rotate:\s*(\d+)", out)
    return int(m.group(1)) % 360 if m else 0
