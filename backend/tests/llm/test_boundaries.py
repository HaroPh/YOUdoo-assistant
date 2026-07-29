"""Ép quy tắc phụ thuộc một chiều của spec §1.

src/llm/ KHÔNG được biết gì về ERP, RAG, Odoo. Nhờ vậy nó test được bằng
provider giả mà không cần Odoo hay Postgres — và nhờ vậy nó dùng lại được
nguyên vẹn khi SP-2 dựng orchestrator.
"""
import pathlib

LLM_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "llm"

CAM = ("src.agents", "src.erp_query", "src.rag",
       "from ..agents", "from ..erp_query", "from ..rag")


def test_tang_llm_khong_import_tang_nghiep_vu():
    vi_pham = []
    for path in sorted(LLM_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for cam in CAM:
            if cam in text:
                vi_pham.append(f"{path.name} tham chiếu {cam!r}")
    assert not vi_pham, "\n".join(vi_pham)


def test_khong_co_khoa_api_nao_bi_hardcode():
    """Khoá chỉ đến từ biến môi trường (spec §9).

    Dò theo HÌNH DẠNG, cố ý không nhúng tiền tố khoá thật của bất kỳ ai: một
    chuỗi dài gán thẳng vào biến có tên nghe như khoá. Nhúng mảnh khoá thật vào
    test là tự tạo ra chính thứ mình đang đi tìm.
    """
    import re

    nghi_ngo = re.compile(
        r"""(?i)(api[_-]?key|secret|token)\s*=\s*["'][A-Za-z0-9_\-.]{20,}["']""")
    for path in sorted(LLM_DIR.glob("*.py")):
        m = nghi_ngo.search(path.read_text(encoding="utf-8"))
        assert not m, f"{path.name}: có vẻ hardcode khoá — {m.group(0)[:40]}"
