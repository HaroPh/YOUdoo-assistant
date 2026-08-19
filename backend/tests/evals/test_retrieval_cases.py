# backend/tests/evals/test_retrieval_cases.py
"""Hợp đồng golden set ↔ corpus thật.

Nhãn viết tay có thể trỏ vào cặp (tệp, section_path) KHÔNG tồn tại — sai
chính tả, đổi tên tệp, hay heading bị parse_pdf cắt khác đi. Nhãn như vậy
làm recall tụt mà không ai hiểu vì sao, và trông y hệt "model kém đi".

Đây đúng lớp lỗi GATHER_CASES từng dính: fixture trôi khỏi dữ liệu thật mà
không ai biết, phải thêm test hợp đồng sau. Lần này viết cùng lúc.
"""
import pytest

from evals.retrieval_cases import RETRIEVAL_CASES
from evals.retrieval_score import label_of
from src.rag import db as _db


def test_moi_ca_co_it_nhat_mot_nhan():
    for question, expected, _difficulty in RETRIEVAL_CASES:
        assert expected, f"ca không có nhãn nào: {question!r}"


def test_difficulty_chi_nhan_ba_gia_tri():
    for question, _expected, difficulty in RETRIEVAL_CASES:
        assert difficulty in ("easy", "hard", "trap"), \
            f"hạng lạ {difficulty!r} ở ca {question!r}"


def test_co_du_ca_ba_hang_do_kho():
    # trap BẮT BUỘC phải có: 9 PDF luật đều mở đầu bằng cùng cấu trúc
    # ("Điều 1. Phạm vi điều chỉnh"), nên bộ đo thiếu ca bẫy sẽ không bao
    # giờ thấy lỗi trúng-nhầm-văn-bản.
    seen = {d for _q, _e, d in RETRIEVAL_CASES}
    assert seen == {"easy", "hard", "trap"}


def test_du_so_ca_bay():
    # Ngưỡng cứng, không phải "có là được": ca bẫy là hạng duy nhất phân biệt
    # được "trúng tài liệu" với "trúng ĐÚNG tài liệu".
    n_trap = sum(1 for _q, _e, d in RETRIEVAL_CASES if d == "trap")
    assert n_trap >= 8, f"chỉ có {n_trap} ca bẫy, spec §7 đòi >=8"


def test_da_so_ca_cham_pdf_luat():
    # 98,7% corpus là PDF luật nhưng mọi câu hỏi rag trong cases.py chỉ chạm
    # 44 chunk nghiệp vụ. Nếu golden set cũng vậy thì nó chỉ đo lại vùng đã
    # đo, và 3.256 chunk vẫn không ai gác.
    n_law = sum(1 for _q, exp, _d in RETRIEVAL_CASES
                if any(f.endswith(".pdf") for f, _s in exp))
    assert n_law >= 30, f"chỉ có {n_law} ca chạm PDF luật, spec §3 đòi >=30"


def test_khong_co_cau_hoi_trung_lap():
    questions = [q for q, _e, _d in RETRIEVAL_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_nhan_khop_it_nhat_mot_chunk_that():
    """Nhãn không khớp hàng nào trong rag_chunks → ĐỎ, kèm tên nhãn."""
    conn = _db.connect()
    try:
        rows = conn.execute(
            "select source_file, section_path, sheet from rag_chunks").fetchall()
    finally:
        conn.close()

    class _Row:
        def __init__(self, r):
            self.source_file, self.section_path, self.sheet = r

    real = {label_of(_Row(r)) for r in rows}
    missing = sorted({lab for _q, exp, _d in RETRIEVAL_CASES for lab in exp
                      if lab not in real})
    assert not missing, (
        f"{len(missing)} nhãn không khớp chunk thật nào — golden set đã trôi "
        f"khỏi corpus (hoặc sai chính tả). Nhãn hỏng: {missing[:10]}")
