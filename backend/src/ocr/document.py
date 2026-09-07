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

from . import engine, table

OCR_CACHE_ENV = "YOUDOO_OCR_CACHE"

# Tăng khi ĐỔI HÌNH DẠNG artifact (thêm/bớt trường, đổi nghĩa). Nó nằm trong
# dấu vân tay nên bản đệm cũ tự động thành lạc khoá, không cần xoá tay.
# 2 (2026-09-05, review toàn nhánh B1): thêm trường "g" (line_id) vào mỗi
# word — hình dạng artifact đã đổi, phải bump đúng chú thích ở trên.
# 3 (2026-09-06, bậc 2): vùng mang thêm trường "grid" (lưới bảng dựng từ toạ
# độ). Hình dạng artifact đã đổi, phải bump — đệm cũ tự lạc khoá qua dấu vân
# tay, không cần xoá tay.
ARTIFACT_VERSION = 3


@dataclass(frozen=True)
class Region:
    kind: str          # bậc 1: luôn "text"
    text: str
    mean_conf: float
    bbox: tuple[int, int, int, int]     # (left, top, right, bottom) theo pixel ảnh
    words: list[dict] = field(default_factory=list)
    grid: list[list[str]] = field(default_factory=list)   # bậc 2; rỗng nếu chưa dựng
    grid_error: str | None = None    # lý do dựng lưới hỏng; None = không hỏng


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


def config_fingerprint(*, dpi: int | None = None, psm: int | None = None,
                       lang: str | None = None) -> str:
    """Dấu vân tay của MỌI thứ ảnh hưởng tới kết quả đọc.

    Khoá đệm = hash(nội dung tệp) + vân tay này. Thiếu nửa sau thì đổi PSM/DPI
    /model xong vẫn dùng lại bản cũ mà không ai biết — đúng lỗ hổng `convert.py`
    đang có, spec §7 yêu cầu không lặp lại.

    dpi, psm, lang đọc từ hằng số lúc GỌI, không phải lúc định nghĩa hàm, để
    cho phép đột biến chúng lúc chạy mà vân tay vẫn thay đổi đúng.

    HAI HẰNG SỐ BẬC 2 (`GAP_FACTOR`, `SUPPORT_RATIO`) NẰM TRONG VÂN TAY từ
    2026-09-07 (phát hiện I3 của review toàn nhánh): `Region.grid` được GHI
    vào artifact và ĐỌC LẠI từ đó, nên đổi hai tham số này mà vân tay không
    đổi thì khoá đệm không đổi và ta dùng lại LƯỚI CŨ mà không ai biết —
    đúng lỗ hổng `convert.py` mà spec §7 viện dẫn để cấm. Đọc lúc GỌI vì cùng
    lý do với dpi/psm/lang: cổng A và cổng B đều đột biến `table.GAP_FACTOR`
    lúc chạy để thử phá."""
    dpi = engine.OCR_DPI if dpi is None else dpi
    psm = engine.OCR_PSM if psm is None else psm
    lang = engine.OCR_LANG if lang is None else lang
    raw = (f"{ARTIFACT_VERSION}|{dpi}|{psm}|{lang}|{engine.tesseract_version()}"
           f"|{table.GAP_FACTOR}|{table.SUPPORT_RATIO}")
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
                      bbox=tuple(r["bbox"]), words=r["words"],
                      grid=r.get("grid", []), grid_error=r.get("grid_error"))
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
    if pageno < 1:
        # `pageno=0` (hay âm) trước đây lặng lẽ đọc TRANG CUỐI qua chỉ số âm
        # của `pdf[pageno - 1]` rồi đệm dưới khoá `p0` — sai trang mà không
        # ai biết. `pageno` đếm từ 1 theo đúng docstring, nên 0 trở xuống
        # phải bị từ chối tường minh (review toàn nhánh B3).
        raise ValueError(f"pageno phải >= 1 (đếm từ 1), nhận {pageno}")
    van_tay = config_fingerprint(dpi=dpi)
    duong = _duong_dem(path, pageno, van_tay)
    if os.path.isfile(duong):
        try:
            with open(duong, encoding="utf-8") as f:
                return _tu_json(json.load(f))
        except (ValueError, KeyError, OSError, TypeError):
            # TypeError: đệm cũ đúng cú pháp JSON (đọc `json.load` thành công)
            # nhưng SAI HÌNH DẠNG cho `ARTIFACT_VERSION` hiện tại — vd JSON là
            # một list thay vì dict, hay "bbox" không phải mảng nên
            # `tuple(r["bbox"])` ném TypeError. `van_tay` đã đổi khi hình dạng
            # đổi (B1) nên ca này hiếm, nhưng vẫn là đường DUY NHẤT chạm tới
            # nhánh này khi nó xảy ra — không được để ném ra ngoài, phải đọc
            # lại như mọi đệm hỏng khác (xem test `dem_hong_giua_chung`).
            pass

    img = _anh_cua_trang(path, pageno, dpi)
    kq = engine.ocr_image(img)
    rong, cao = getattr(img, "size", (0, 0))
    # Bậc 2: dựng lưới từ toạ độ. Hỏng thì KHÔNG làm vỡ lượt đọc — mất cấu
    # trúc còn hơn mất nội dung (spec §9). Nhưng KHÔNG được nuốt im lặng: ghi
    # lý do vào artifact để `parse.py` biến nó thành cảnh báo CÓ TÊN. Tầng này
    # là module lá, không biết `IngestReport`, nên nó chỉ ghi — không tự báo.
    try:
        grid, grid_error = table.build_grid(kq.words), None
    except Exception as e:                               # noqa: BLE001
        grid, grid_error = [], f"{type(e).__name__}: {e}"
    # BẬC 1: đúng MỘT vùng kiểu `text` phủ cả trang. Phân vùng hình học (vùng
    # rộng không có hộp chữ = vùng hình) là bộ định tuyến của bậc 3 — chưa có
    # tài liệu scan có hình để hiệu chỉnh, nên chưa dựng (spec §14).
    region = Region(kind="text", text=kq.text, mean_conf=kq.mean_conf,
                    bbox=(0, 0, rong, cao),
                    words=[{"t": w.text, "c": w.conf, "l": w.left, "y": w.top,
                            "w": w.width, "h": w.height,
                            "g": list(w.line_id)} for w in kq.words],
                    grid=grid, grid_error=grid_error)
    data = {"artifact_version": ARTIFACT_VERSION, "page": pageno,
            "config": {"dpi": dpi, "psm": engine.OCR_PSM,
                       "lang": engine.OCR_LANG,
                       "tesseract": engine.tesseract_version()},
            "mean_conf": kq.mean_conf,
            "regions": [{"kind": region.kind, "text": region.text,
                         "mean_conf": region.mean_conf,
                         "bbox": list(region.bbox), "words": region.words,
                         "grid": region.grid, "grid_error": region.grid_error}]}
    _ghi_nguyen_tu(duong, data)
    return PageRead(page=pageno, regions=[region], mean_conf=kq.mean_conf,
                    tu_dem=False)
