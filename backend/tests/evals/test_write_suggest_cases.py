# backend/tests/evals/test_write_suggest_cases.py
"""Hợp đồng bộ ca `ĐỀ_XUẤT_GHI`."""
import pytest

from evals.write_suggest_cases import WRITE_SUGGEST_CASES


def test_du_ca_hai_chieu():
    """Thiếu ca âm thì bộ này chỉ đo được chiều tịt marker, và một bản cài đặt
    phát marker cho MỌI câu vẫn xanh tuyệt đối."""
    duong = [c for c in WRITE_SUGGEST_CASES if c.expect_marker]
    am = [c for c in WRITE_SUGGEST_CASES if not c.expect_marker]
    assert len(duong) >= 4, f"chỉ có {len(duong)} ca dương"
    assert len(am) >= 4, f"chỉ có {len(am)} ca âm"


def test_ca_am_phai_MANG_tu_vung_ghi():
    """Ca âm phải là 'suýt trúng', không phải hiển nhiên.

    Một bộ ca âm toàn câu hỏi vô thưởng vô phạt sẽ xanh mãi mãi mà không chứng
    minh được model biết PHÂN BIỆT hỏi-trạng-thái với nhờ-làm. Mỗi ca âm phải
    chứa ít nhất một từ vựng thao tác ghi."""
    tu_ghi = ("xác nhận", "hoàn", "chiết khấu", "tạo", "khoá", "lập", "áp")
    yeu = [c.question for c in WRITE_SUGGEST_CASES
           if not c.expect_marker
           and not any(t in c.question.lower() for t in tu_ghi)]
    assert not yeu, f"ca âm không mang từ vựng ghi nên quá dễ: {yeu}"


def test_khong_trung_cau_hoi():
    qs = [c.question for c in WRITE_SUGGEST_CASES]
    assert len(qs) == len(set(qs))


@pytest.mark.integration
def test_moi_topic_co_fixture_that():
    """Sai tên topic thì load_chunks trả rỗng và ca đo trên ngữ cảnh TRỐNG —
    vẫn chạy, vẫn ra số, nhưng đo nhầm thứ."""
    from evals import fixtures
    thieu = []
    for c in WRITE_SUGGEST_CASES:
        try:
            if not fixtures.load_chunks(c.topic):
                thieu.append(c.topic)
        except Exception:
            thieu.append(c.topic)
    assert not thieu, f"topic không có fixture: {sorted(set(thieu))}"
