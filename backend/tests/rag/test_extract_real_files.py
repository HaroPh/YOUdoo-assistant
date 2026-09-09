# backend/tests/rag/test_extract_real_files.py
"""Nghiệm thu `extract_documents` trên TỆP THẬT, không phải block dựng tay.

Test của Task 1 đều monkeypatch parser, nên chúng chứng minh logic gom trang
đúng — KHÔNG chứng minh trích được chữ từ tệp thật. Hai chuyện khác nhau, và
dự án này đã đếm được nhiều lần một cổng "trông như đang gác nhưng không đo gì".

Ca quan trọng nhất là `DVT_2022.pdf`: Open WebUI trích nó ra 15 ký tự toàn dấu
cách (`status=failed`) và người dùng nghe "không tìm thấy tài liệu liên quan".
Cùng tệp, qua đường này, phải ra chữ thật.

Đánh dấu `integration`: cần Tesseract và mất khoảng một phút cho 16 trang scan.
"""
import os

import pytest

from src.ocr.engine import tesseract_path
from src.rag.extract import extract_documents

# Đường dẫn TUYỆT ĐỐI: `tmp-docs` là thư mục gitignore, chỉ tồn tại ở cây chính
# D:\Youdoo, không nằm trong worktree nào.
SCAN = r"D:\Youdoo\tmp-docs\ocr-scan-that\DVT_2022.pdf"
DIGITAL_PDF = "src/rag/seed/law/luat-thuegtgt.pdf"
DOCX = "src/rag/seed/policy.docx"


@pytest.mark.integration
@pytest.mark.skipif(not os.path.isfile(DIGITAL_PDF), reason="thieu kho luat")
def test_digital_pdf_yields_one_document_per_page_with_real_text():
    docs = extract_documents(DIGITAL_PDF, "luat-thuegtgt.pdf")
    assert len(docs) > 1
    assert all(d["page_content"].strip() for d in docs)
    pages = [d["metadata"]["page"] for d in docs]
    assert pages == sorted(pages)
    assert all(d["metadata"]["source_kind"] == "text" for d in docs)


@pytest.mark.integration
@pytest.mark.skipif(not os.path.isfile(DOCX), reason="thieu tai lieu nghiep vu")
def test_docx_yields_exactly_one_document():
    docs = extract_documents(DOCX, "policy.docx")
    assert len(docs) == 1
    assert docs[0]["page_content"].strip()


@pytest.mark.integration
@pytest.mark.skipif(tesseract_path() is None or not os.path.isfile(SCAN),
                    reason="chua cai tesseract hoac thieu kho scan")
def test_the_scanned_pdf_open_webui_could_not_read_now_yields_real_text():
    """Phép nghiệm thu THẬT: cùng tệp, khác kết quả.

    Open WebUI: 15 ký tự, toàn dấu cách, status=failed.
    Đường này: phải ra chữ Việt thật VÀ phải đánh dấu là do OCR đọc.
    """
    docs = extract_documents(SCAN, "DVT_2022.pdf")
    assert len(docs) >= 10, f"chi ra {len(docs)} trang tren tai lieu 16 trang"
    tong = sum(len(d["page_content"]) for d in docs)
    assert tong > 5000, f"chi trich duoc {tong} ky tu - Open WebUI ra 15"
    assert any(d["metadata"]["source_kind"] == "ocr" for d in docs), \
        "khong trang nao danh dau la OCR - tep nay KHONG co lop text"
    assert any(d["metadata"]["ocr_conf"] for d in docs)
    het = " ".join(d["page_content"] for d in docs).lower()
    assert "báo cáo" in het or "bao cao" in het
