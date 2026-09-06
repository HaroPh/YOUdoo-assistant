# backend/tests/rag/test_docx_kho_that.py
"""Nghiệm thu tầng 2 — 12 tệp Word THẬT ngoài repo (spec 2026-09-04 mục 10).

Cổng CỨNG: không chunk nào mang đường dẫn tệp làm `section_path`. Cổng này
không cần gán tay đáp án nào — "breadcrumb là đường dẫn tệp" là thứ máy tự
kiểm được.

Số tài liệu có phân cấp thật thì BÁO CÁO, không đặt ngưỡng cứng — cùng lý do
kế hoạch 2 đã bỏ `đúng >= 20`.

Kho có 11 tệp `.docx` + 1 tệp `.doc` (`quyche_taichinh.doc`, spec mục 12) =
12 tệp Word thật. `.doc` là định dạng nhị phân cũ mà python-docx không mở
được — phải qua cầu LibreOffice (`convert.convert_file`) TRƯỚC `parse_docx`,
đúng khuôn `_chunks_for`/`_ingest_convertible` của `ingest.py`: `read_path`
(tệp thật sự đọc, có thể là bản đã chuyển đổi) và `source_file` (nhãn gốc
người dùng thấy, đi vào `chunk_text_blocks`) TÁCH RỜI. Bỏ sót `.doc` sẽ chỉ
nghiệm thu 11/12 tệp và bỏ lọt đúng ca kiểm luôn cầu chuyển đổi của kế hoạch
1 mà spec mục 12 nêu tên.
"""
import hashlib
import os

import pytest

from src.rag.chunking import chunk_text_blocks
from src.rag.parse import parse_docx

KHO = "d:/Youdoo/tmp-docs"
pytestmark = pytest.mark.live


def _tep_word():
    if not os.path.isdir(KHO):
        return []
    return sorted(f for f in os.listdir(KHO)
                  if f.lower().endswith((".docx", ".doc")))


def _doc_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _duong_doc(name: str) -> tuple[str, str]:
    """(path gốc dùng làm nhãn/breadcrumb, path THẬT SỰ đọc được).

    `.doc` phải qua LibreOffice trước — trả về bản đã chuyển làm path đọc,
    nhưng path GỐC vẫn là nhãn cho `source_file` (không phải đường dẫn cache
    tạm chứa content_hash)."""
    path = os.path.join(KHO, name)
    if name.lower().endswith(".doc"):
        from src.rag import convert
        return path, convert.convert_file(path, _doc_hash(path))
    return path, path


@pytest.mark.skipif(not _tep_word(), reason="chưa có tmp-docs")
def test_KHONG_chunk_nao_mang_duong_dan_tep_lam_breadcrumb():
    ban = []
    for name in _tep_word():
        path, read_path = _duong_doc(name)
        chunks = chunk_text_blocks(parse_docx(read_path), doc_id=name,
                                   source_file=path)
        for c in chunks:
            crumb = c["section_path"] or ""
            if "tmp-docs" in crumb or crumb.endswith((".docx", ".doc")):
                ban.append((name, crumb[:60]))
                break
    assert ban == [], f"vẫn còn breadcrumb là đường dẫn tệp: {ban}"


@pytest.mark.skipif(not _tep_word(), reason="chưa có tmp-docs")
def test_bao_cao_do_phu_phan_cap():
    """Không phải cổng — in ra để người chạy NHÌN THẤY kho thật rơi vào đâu."""
    print()
    co_phan_cap = 0
    for name in _tep_word():
        path, read_path = _duong_doc(name)
        blocks = parse_docx(read_path)
        heads = [b for b in blocks if b["heading_level"]]
        chunks = chunk_text_blocks(blocks, doc_id=name, source_file=path)
        có = sum(1 for c in chunks if c["section_path"])
        co_phan_cap += 1 if heads else 0
        print(f"  {name:<28} block {len(blocks):>4}  tiêu đề {len(heads):>3}  "
              f"chunk {len(chunks):>3}  có breadcrumb {có:>3}")
    print(f"\n  tài liệu có phân cấp: {co_phan_cap}/{len(_tep_word())}")
    assert _tep_word(), "không đọc được tệp nào"
