# backend/tests/jobs/test_eval_localize.py
"""Bộ ca dịch phải phủ đúng thứ đắt nhất: SỰ VIỆC trong câu xác nhận ghi."""
import re

from evals.cases import LOCALIZE_CASES


def test_moi_ca_la_cap_va_deu_co_dau_tieng_viet():
    vi = re.compile(r"[ăâđêôơưáàảãạéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ]")
    for goc, _lang in LOCALIZE_CASES:
        assert vi.search(goc), goc


def test_moi_ca_deu_mang_it_nhat_mot_su_viec():
    """Ca không có số/mã nào thì lớp phủ quyết không đo được gì."""
    from src.agents.localize import extract_facts
    for goc, _lang in LOCALIZE_CASES:
        assert extract_facts(goc), goc


def test_co_ca_cau_xac_nhan_ghi():
    assert any("xác nhận" in g for g, _ in LOCALIZE_CASES)


def test_du_so_ca():
    assert len(LOCALIZE_CASES) >= 6
