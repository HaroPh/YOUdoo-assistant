"""Cổng TỰ NUÔI — spec 2026-09-04-tang-ocr §13.

Corpus hôm nay có 0 tài liệu cần đọc bằng ảnh. Một thành phần không ai chạy
qua thì CHẾT ÂM THẦM — dự án đã trả giá ba lần (reranker chết 6 tuần; chân
sparse chết từ ngày đầu, 0/64 câu; riêng Kế hoạch 1 đếm được TÁM lần "cổng
trông như đang gác nhưng không đo gì").

Cơ chế: lấy trang ĐÃ CÓ lớp text → rasterise → vứt lớp text → đọc lại bằng
ảnh → so ngược. Corpus tự sinh đáp án, không gán tay ô nào.

Thước là RECALL THEO TỪ, không phải độ giống chuỗi: `SequenceMatcher` từng cho
0,46 và suýt dẫn tới kết luận "OCR tiếng Việt kém" — thật ra chữ nhận gần đúng
hết, điểm thấp do THỨ TỰ ĐỌC khác và đường kẻ bảng bị đọc thành ký tự.

GIỚI HẠN nói thẳng: ảnh rasterise SẠCH HƠN scan đời thật. Cổng này chứng minh
"còn sống và đại khái đúng", KHÔNG chứng minh "chịu được scan đời thật".
"""
import os
import re

import pypdf
import pytest

from src.ocr.document import read_page
from src.ocr.engine import tesseract_path

KHO_LUAT = "D:/Documents"

# NGƯỠNG ĐO ĐƯỢC 2026-09-05, KHÔNG phải số kế thừa từ spec (spec ghi 0,865
# nhưng đo trên tập trang khác — 3 trang bảng của một tài liệu).
# Số thật từng trang (PSM 6, 200 DPI, tesseract 5.4.0):
#   luat-thuegtgt.pdf            tr.1  recall=0,9905
#   luat-thuegtgt.pdf            tr.5  recall=0,9894
#   luat-thuexuatnhapkhau.pdf    tr.3  recall=0,9893
#   luat-thuexuatnhapkhau.pdf    tr.6  recall=0,9915
#   luat-thuexuatnhapkhau.pdf    tr.13 recall=0,9473  (trang BẢNG — thấp nhất)
#   luat-thuexuatnhapkhau.pdf    tr.20 recall=0,9508
# min quan sát = 0,9473 → NGUONG = làm tròn xuống 2 chữ số của (0,9473 - 0,05)
#              = làm tròn xuống của 0,8973 = 0,89
# Chi tiết đầy đủ + phép thử phá (PSM 3) trong ghi chú thực thi mục
# "Tầng OCR bậc 1" và trong task-5-report.md.
NGUONG_RECALL = 0.89

TAP_TRANG = [
    ("luat-thuegtgt.pdf", 1),
    ("luat-thuegtgt.pdf", 5),
    ("luat-thuexuatnhapkhau.pdf", 3),
    ("luat-thuexuatnhapkhau.pdf", 6),
    ("luat-thuexuatnhapkhau.pdf", 13),     # trang BẢNG — ca khó, cố ý giữ
    ("luat-thuexuatnhapkhau.pdf", 20),
]


def _tu(s: str) -> list[str]:
    return [w for w in re.findall(r"\w+", s.lower(), re.UNICODE) if w]


def _recall_tu(goc: str, doc: str) -> float:
    g, o = _tu(goc), set(_tu(doc))
    return sum(1 for w in g if w in o) / max(len(g), 1)


def _co_kho() -> bool:
    return all(os.path.isfile(os.path.join(KHO_LUAT, t)) for t, _ in TAP_TRANG)


@pytest.mark.skipif(tesseract_path() is None or not _co_kho(),
                    reason="chưa có tesseract hoặc kho luật")
@pytest.mark.parametrize("tep,trang", TAP_TRANG)
def test_cong_tu_nuoi_duong_doc_bang_anh_con_song(tep, trang, tmp_path, monkeypatch):
    from src.ocr import document
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    duong = os.path.join(KHO_LUAT, tep)
    goc = pypdf.PdfReader(duong).pages[trang - 1].extract_text() or ""
    assert _tu(goc), f"{tep} tr.{trang} không có lớp text — chọn sai trang mẫu"
    r = _recall_tu(goc, read_page(duong, trang).text)
    print(f"\n[tu nuoi] {tep} tr.{trang}: recall={r:.4f}")
    assert r >= NGUONG_RECALL, f"{tep} tr.{trang}: recall {r:.3f} < {NGUONG_RECALL}"
