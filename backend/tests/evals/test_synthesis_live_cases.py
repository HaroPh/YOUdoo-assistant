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
    for c in SYNTHESIS_LIVE_CASES:
        assert c.kind in ("deep_chunk", "distractor", "insufficient"), \
            f"loại lạ {c.kind!r} ở ca {c.question!r}"


def test_co_du_ca_ba_loai():
    seen = {c.kind for c in SYNTHESIS_LIVE_CASES}
    assert seen == {"deep_chunk", "distractor", "insufficient"}


def test_du_so_ca_moi_loai():
    # Ngưỡng cứng theo plan. deep_chunk là loại duy nhất gây áp lực lên phần
    # SAU của một mục, distractor là loại duy nhất phân biệt "trúng tài liệu"
    # với "trúng ĐÚNG tài liệu". Thiếu một trong hai thì bộ đo mất đúng khả
    # năng mà nó sinh ra để có.
    from collections import Counter
    n = Counter(c.kind for c in SYNTHESIS_LIVE_CASES)
    assert n["deep_chunk"] >= 10, f"chỉ có {n['deep_chunk']} ca deep_chunk"
    assert n["distractor"] >= 13, f"chỉ có {n['distractor']} ca distractor"
    assert n["insufficient"] >= 4, f"chỉ có {n['insufficient']} ca insufficient"


def test_ca_tra_loi_duoc_phai_co_expect_nguon_va_muc():
    for c in SYNTHESIS_LIVE_CASES:
        if c.kind == "insufficient":
            continue
        assert c.expect, f"ca {c.question!r} thiếu expect"
        assert c.source.endswith((".pdf", ".docx", ".xlsx")), \
            f"source của {c.question!r} phải là basename có đuôi tệp, gặp {c.source!r}"
        assert c.section, f"ca {c.question!r} thiếu section — test hợp đồng cần nó"


def test_ca_distractor_phai_khai_muc_canh_tranh():
    # Không có `rival` thì ca bẫy không chứng minh được gì: nó chỉ là một ca
    # thường mang nhãn khác.
    for c in SYNTHESIS_LIVE_CASES:
        if c.kind == "distractor":
            assert c.rival, f"ca bẫy {c.question!r} thiếu rival"


def test_khong_co_cau_hoi_trung_lap():
    questions = [c.question for c in SYNTHESIS_LIVE_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_expect_co_that_trong_dung_tep_nguon():
    conn = _db.connect()
    try:
        bad = []
        for c in SYNTHESIS_LIVE_CASES:
            if c.kind == "insufficient":
                continue
            for alt in _expects(c.expect):
                n = conn.execute(
                    "select count(*) from rag_chunks where source_file like %s "
                    "and section_path = %s and chunk_text like %s",
                    ("%" + c.source, c.section, "%" + alt + "%")).fetchone()[0]
                if n == 0:
                    bad.append((c.question, alt, c.source, c.section))
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
        for c in SYNTHESIS_LIVE_CASES:
            if c.kind != "deep_chunk":
                continue
            first_alt = _expects(c.expect)[0]
            # Phạm vi hẹp theo (tệp, MỤC): expect ngắn kiểu "06 tháng" xuất
            # hiện ở nhiều mục khác trong cùng tệp, nên không giới hạn theo
            # mục thì test sẽ soi nhầm chunk và báo sai.
            idxs = [r[0] for r in conn.execute(
                "select chunk_index from rag_chunks where source_file like %s "
                "and section_path = %s and chunk_text like %s order by chunk_index",
                ("%" + c.source, c.section, "%" + first_alt + "%")).fetchall()]
            assert idxs, f"không tìm thấy chunk chứa {first_alt!r} trong {c.section!r}"
            first_idx = conn.execute(
                "select min(chunk_index) from rag_chunks "
                "where source_file like %s and section_path = %s",
                ("%" + c.source, c.section)).fetchone()[0]
            if first_idx in idxs:
                shallow.append((c.question, c.section, first_idx))
    finally:
        conn.close()
    assert not shallow, (
        f"{len(shallow)} ca gắn nhãn deep_chunk nhưng đáp án nằm ở chunk ĐẦU "
        f"của mục — không gây áp lực gì lên tầng truy xuất: {shallow}")


@pytest.mark.integration
def test_ca_distractor_co_expect_duy_nhat_o_mot_tep():
    """Với ca bẫy, expect phải VẮNG MẶT trong mục cạnh tranh — nhờ vậy trả lời
    đúng chuỗi đó là bằng chứng đã dùng ĐÚNG mục, không phải mục gần giống.

    Đo theo MỤC chứ không theo tệp: cặp bẫy mạnh nhất (Điều 35 vs Điều 36) nằm
    trong CÙNG một tệp, nên so theo tệp sẽ mù đúng ca quan trọng nhất."""
    conn = _db.connect()
    try:
        leaky = []
        for c in SYNTHESIS_LIVE_CASES:
            if c.kind != "distractor":
                continue
            for alt in _expects(c.expect):
                n = conn.execute(
                    "select count(*) from rag_chunks "
                    "where section_path = %s and chunk_text like %s",
                    (c.rival, "%" + alt + "%")).fetchone()[0]
                if n:
                    leaky.append((c.question, alt, c.rival, n))
    finally:
        conn.close()
    assert not leaky, (
        f"expect của ca bẫy CŨNG xuất hiện trong mục cạnh tranh nên không phân "
        f"biệt được gì: {leaky[:5]}")
