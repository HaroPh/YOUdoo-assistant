# backend/tests/evals/test_multiturn_cases.py
"""Hợp đồng bộ ca hai lượt ↔ corpus thật, cùng khuôn với hai bộ đã có."""
import pytest

from evals.multiturn_cases import MULTITURN_CASES
from evals.retrieval_score import label_of
from src.rag import db as _db


def test_kind_chi_nhan_hai_gia_tri():
    for c in MULTITURN_CASES:
        assert c.kind in ("elliptical", "independent"), \
            f"loại lạ {c.kind!r} ở ca {c.question!r}"


def test_co_du_ca_hai_nhom():
    # `independent` là nửa đo mặt HẠI. Thiếu nó thì bộ này chỉ đo mặt lợi và
    # mù với việc truyền ngữ cảnh làm nhiễu pool — đúng cơ chế đã làm hỏng
    # việc hồi sinh chân sparse.
    from collections import Counter
    n = Counter(c.kind for c in MULTITURN_CASES)
    assert n["elliptical"] >= 8, f"chỉ có {n['elliptical']} ca elliptical"
    assert n["independent"] >= 4, f"chỉ có {n['independent']} ca independent"


def test_moi_ca_co_du_hai_luot_va_nhan():
    for c in MULTITURN_CASES:
        assert c.prev_turn, f"ca {c.question!r} thiếu prev_turn"
        assert c.question, "thiếu question"
        assert c.expect, f"ca {c.question!r} thiếu nhãn"


def test_khong_co_cau_hoi_trung_lap():
    qs = [c.question for c in MULTITURN_CASES]
    assert len(qs) == len(set(qs))


def test_ca_independent_khong_duoc_lien_quan_luot_truoc():
    """Hai lượt phải KHÁC chủ đề, nếu không nhóm này không đo được mặt hại.

    Xấp xỉ bằng chồng lấn từ: hai câu chia nhau quá nhiều từ nội dung thì
    không còn là "độc lập" nữa và ca đó âm thầm mất tác dụng."""
    import re

    # Tách bằng regex chứ KHÔNG dùng split(): split() để dấu câu dính vào
    # token, nên "nào?" không khớp mục "nào" trong danh sách hư từ và test đỏ
    # oan vì một từ để hỏi. Bản đầu của test này mắc đúng lỗi đó.
    stop = {"là", "của", "gì", "thế", "nào", "bao", "nhiêu", "có", "được",
            "những", "trong", "cho", "thì", "và", "các", "quy", "định",
            "khi", "gồm", "một", "hai", "người"}
    words = lambda s: {w for w in re.findall(r"\w+", s.lower(), re.UNICODE)
                       if w not in stop}
    for c in MULTITURN_CASES:
        if c.kind != "independent":
            continue
        shared = words(c.prev_turn) & words(c.question)
        assert not shared, \
            f"ca independent {c.question!r} chia từ {shared} với lượt trước"


@pytest.mark.integration
def test_moi_nhan_khop_chunk_that():
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
    missing = sorted({lab for c in MULTITURN_CASES for lab in c.expect
                      if lab not in real})
    assert not missing, (
        f"{len(missing)} nhãn không khớp chunk thật nào: {missing[:5]}")
