"""Tầng tài liệu của tầng OCR — spec 2026-09-04-tang-ocr §3 (tầng 1).

PDF → ảnh từng trang → vùng CÓ KIỂU, có đệm trên đĩa. KHÔNG biết DB, chunk,
hay ai đang gọi mình.

BẬC 1 chỉ sinh vùng kiểu `text` (spec §14). Kiểu `table` (dựng từ toạ độ) và
`figure` (mô tả bằng VLM) là bậc 2/3, chờ có tài liệu scan thật — nhưng HỢP
ĐỒNG artifact dựng sẵn từ bây giờ để hai bậc sau không phải đổi kho đệm.
"""
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field

from . import engine

OCR_CACHE_ENV = "YOUDOO_OCR_CACHE"

# Tăng khi ĐỔI HÌNH DẠNG artifact (thêm/bớt trường, đổi nghĩa). Nó nằm trong
# dấu vân tay nên bản đệm cũ tự động thành lạc khoá, không cần xoá tay.
ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class Region:
    kind: str          # bậc 1: luôn "text"
    text: str
    mean_conf: float
    bbox: tuple[int, int, int, int]     # (left, top, right, bottom) theo pixel ảnh
    words: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PageRead:
    page: int
    regions: list[Region]
    mean_conf: float
    tu_dem: bool

    @property
    def text(self) -> str:
        return "\n".join(r.text for r in self.regions if r.text)


def cache_dir() -> str:
    d = os.environ.get(OCR_CACHE_ENV) or os.path.join(
        tempfile.gettempdir(), "youdoo_ocr")
    os.makedirs(d, exist_ok=True)
    return d


def config_fingerprint(*, dpi: int = engine.OCR_DPI, psm: int = engine.OCR_PSM,
                       lang: str = engine.OCR_LANG) -> str:
    """Dấu vân tay của MỌI thứ ảnh hưởng tới kết quả đọc.

    Khoá đệm = hash(nội dung tệp) + vân tay này. Thiếu nửa sau thì đổi PSM/DPI
    /model xong vẫn dùng lại bản cũ mà không ai biết — đúng lỗ hổng `convert.py`
    đang có, spec §7 yêu cầu không lặp lại."""
    raw = f"{ARTIFACT_VERSION}|{dpi}|{psm}|{lang}|{engine.tesseract_version()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _hash_tep(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _duong_dem(path: str, pageno: int, van_tay: str) -> str:
    return os.path.join(cache_dir(), f"{_hash_tep(path)}-{van_tay}-p{pageno}.json")


def _anh_cua_trang(path: str, pageno: int, dpi: int):
    """Rasterise MỘT trang (đếm từ 1) thành ảnh PIL.

    `pypdfium2` đã có sẵn theo `pdfplumber` — không thêm phụ thuộc (spec §3)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return pdf[pageno - 1].render(scale=dpi / 72).to_pil()
    finally:
        pdf.close()


def _tu_json(data: dict) -> PageRead:
    regions = [Region(kind=r["kind"], text=r["text"], mean_conf=r["mean_conf"],
                      bbox=tuple(r["bbox"]), words=r["words"])
               for r in data["regions"]]
    return PageRead(page=data["page"], regions=regions,
                    mean_conf=data["mean_conf"], tu_dem=True)


def _ghi_nguyen_tu(duong: str, data: dict) -> None:
    """Ghi tạm rồi đổi tên — bài học đã trả giá ở `convert.py`: tệp cụt do
    timeout ở lại thì bẩn VĨNH VIỄN, vì khoá đệm không bao giờ tự lành."""
    tam = f"{duong}.tmp"
    with open(tam, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tam, duong)


def read_page(path: str, pageno: int, *, dpi: int = engine.OCR_DPI) -> PageRead:
    """Đọc MỘT trang PDF bằng ảnh (đếm từ 1). Ném `TesseractMissing` khi thiếu
    binary — người gọi quyết định biến nó thành cảnh báo hay từ chối."""
    van_tay = config_fingerprint(dpi=dpi)
    duong = _duong_dem(path, pageno, van_tay)
    if os.path.isfile(duong):
        try:
            with open(duong, encoding="utf-8") as f:
                return _tu_json(json.load(f))
        except (ValueError, KeyError, OSError):
            pass          # đệm hỏng → đọc lại, xem test `dem_hong_giua_chung`

    img = _anh_cua_trang(path, pageno, dpi)
    kq = engine.ocr_image(img)
    rong, cao = getattr(img, "size", (0, 0))
    # BẬC 1: đúng MỘT vùng kiểu `text` phủ cả trang. Phân vùng hình học (vùng
    # rộng không có hộp chữ = vùng hình) là bộ định tuyến của bậc 3 — chưa có
    # tài liệu scan có hình để hiệu chỉnh, nên chưa dựng (spec §14).
    region = Region(kind="text", text=kq.text, mean_conf=kq.mean_conf,
                    bbox=(0, 0, rong, cao),
                    words=[{"t": w.text, "c": w.conf, "l": w.left, "y": w.top,
                            "w": w.width, "h": w.height} for w in kq.words])
    data = {"artifact_version": ARTIFACT_VERSION, "page": pageno,
            "config": {"dpi": dpi, "psm": engine.OCR_PSM,
                       "lang": engine.OCR_LANG,
                       "tesseract": engine.tesseract_version()},
            "mean_conf": kq.mean_conf,
            "regions": [{"kind": region.kind, "text": region.text,
                         "mean_conf": region.mean_conf,
                         "bbox": list(region.bbox), "words": region.words}]}
    _ghi_nguyen_tu(duong, data)
    return PageRead(page=pageno, regions=[region], mean_conf=kq.mean_conf,
                    tu_dem=False)
