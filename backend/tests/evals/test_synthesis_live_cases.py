# backend/tests/evals/test_synthesis_live_cases.py
"""Hợp đồng bộ ca synthesis_live ↔ corpus thật.

Bài học GATHER_CASES: fixture trôi khỏi dữ liệu thật mà không ai biết, phải
thêm test hợp đồng sau. Lần này viết cùng lúc.

Test `deep_chunk` ở đây làm nhiều hơn kiểm chính tả: nó khẳng định ca đó THỰC
SỰ sâu. Một ca `deep_chunk` mà đáp án nằm ở chunk ĐẦU của mục là ca gắn nhãn
sai — nó không gây áp lực gì lên tầng truy xuất, và cả bộ eval sẽ vô cảm đúng
như recall@6 đã vô cảm.
"""
import pytest

from evals.synthesis_live_cases import SYNTHESIS_LIVE_CASES
from src.rag import db as _db


def _expects(expect):
    return expect if isinstance(expect, tuple) else (expect,)


def test_kind_chi_nhan_ba_gia_tri():
    for q, kind, _e, _s in SYNTHESIS_LIVE_CASES:
        assert kind in ("deep_chunk", "distractor", "insufficient"), \
            f"loại lạ {kind!r} ở ca {q!r}"


def test_co_du_ca_ba_loai():
    seen = {k for _q, k, _e, _s in SYNTHESIS_LIVE_CASES}
    assert seen == {"deep_chunk", "distractor", "insufficient"}


def test_du_so_ca_moi_loai():
    # Ngưỡng cứng theo plan. deep_chunk là loại duy nhất gây áp lực lên phần
    # SAU của một mục, distractor là loại duy nhất phân biệt "trúng tài liệu"
    # với "trúng ĐÚNG tài liệu". Thiếu một trong hai thì bộ đo mất đúng khả
    # năng mà nó sinh ra để có.
    from collections import Counter
    n = Counter(k for _q, k, _e, _s in SYNTHESIS_LIVE_CASES)
    assert n["deep_chunk"] >= 10, f"chỉ có {n['deep_chunk']} ca deep_chunk"
    assert n["distractor"] >= 5, f"chỉ có {n['distractor']} ca distractor"
    assert n["insufficient"] >= 4, f"chỉ có {n['insufficient']} ca insufficient"


def test_ca_tra_loi_duoc_phai_co_expect_va_nguon():
    for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
        if kind == "insufficient":
            continue
        assert expect, f"ca {q!r} thiếu expect"
        assert source.endswith((".pdf", ".docx", ".xlsx")), \
            f"expect_source của {q!r} phải là basename có đuôi tệp, gặp {source!r}"


def test_khong_co_cau_hoi_trung_lap():
    questions = [q for q, _k, _e, _s in SYNTHESIS_LIVE_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_expect_co_that_trong_dung_tep_nguon():
    conn = _db.connect()
    try:
        bad = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind == "insufficient":
                continue
            for alt in _expects(expect):
                n = conn.execute(
                    "select count(*) from rag_chunks "
                    "where source_file like %s and chunk_text like %s",
                    ("%" + source, "%" + alt + "%")).fetchone()[0]
                if n == 0:
                    bad.append((q, alt, source))
    finally:
        conn.close()
    assert not bad, (
        f"{len(bad)} chuỗi expect KHÔNG có trong tệp nguồn đã khai — bộ ca đã "
        f"trôi khỏi corpus hoặc chép sai: {bad[:5]}")


@pytest.mark.integration
def test_ca_deep_chunk_thuc_su_nam_o_chunk_sau():
    """Đáp án phải nằm ngoài chunk ĐẦU của mục, nếu không ca này vô nghĩa."""
    conn = _db.connect()
    try:
        shallow = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind != "deep_chunk":
                continue
            first_alt = _expects(expect)[0]
            row = conn.execute(
                "select section_path, chunk_index from rag_chunks "
                "where source_file like %s and chunk_text like %s "
                "order by chunk_index limit 1",
                ("%" + source, "%" + first_alt + "%")).fetchone()
            assert row is not None, f"không tìm thấy chunk chứa {first_alt!r}"
            section, idx = row
            first_idx = conn.execute(
                "select min(chunk_index) from rag_chunks "
                "where source_file like %s and section_path = %s",
                ("%" + source, section)).fetchone()[0]
            if idx == first_idx:
                shallow.append((q, section, idx))
    finally:
        conn.close()
    assert not shallow, (
        f"{len(shallow)} ca gắn nhãn deep_chunk nhưng đáp án nằm ở chunk ĐẦU "
        f"của mục — không gây áp lực gì lên tầng truy xuất: {shallow}")


@pytest.mark.integration
def test_ca_distractor_co_expect_duy_nhat_o_mot_tep():
    """Với ca bẫy, expect phải CHỈ có ở tệp nguồn đúng — nhờ vậy trả lời đúng
    chuỗi đó là bằng chứng đã dùng ĐÚNG văn bản, không phải văn bản gần giống."""
    conn = _db.connect()
    try:
        leaky = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind != "distractor":
                continue
            for alt in _expects(expect):
                n = conn.execute(
                    "select count(*) from rag_chunks "
                    "where source_file not like %s and chunk_text like %s",
                    ("%" + source, "%" + alt + "%")).fetchone()[0]
                if n:
                    leaky.append((q, alt, n))
    finally:
        conn.close()
    assert not leaky, (
        f"expect của ca bẫy xuất hiện ở tệp KHÁC nên không chứng minh được gì: "
        f"{leaky[:5]}")
