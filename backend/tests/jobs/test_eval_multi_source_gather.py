# backend/tests/jobs/test_eval_multi_source_gather.py
"""Set multi_source_gather: đo TOÀN CHUỖI nhánh mixed (gather_erp thật →
fuse_answer) trên cùng bộ câu hỏi/kỳ vọng của multi_source. Không gate —
chưa có baseline (spec 2026-08-04 §3)."""
from evals import cases, fixtures


def test_gather_cases_mirror_multi_source_cases_exactly():
    """Ràng buộc trung tâm của cả plan (spec §4): hai danh sách phải khớp
    (topic, question, doc_fact, erp_fact) theo ĐÚNG thứ tự. Lệch một chỗ là
    hai bộ số hết so sánh được — mà so sánh được chính là toàn bộ lý do set
    này tồn tại. Cũng là điều kiện để dùng CHUNG
    MULTI_SOURCE_DERIVED_DIGITS (khoá theo (topic, question))."""
    assert len(cases.MULTI_SOURCE_GATHER_CASES) == len(cases.MULTI_SOURCE_CASES)
    for g, m in zip(cases.MULTI_SOURCE_GATHER_CASES, cases.MULTI_SOURCE_CASES):
        g_topic, _g_fixtures, g_question, g_doc, g_erp = g
        m_topic, _m_block, m_question, m_doc, m_erp = m
        assert (g_topic, g_question, g_doc, g_erp) == \
               (m_topic, m_question, m_doc, m_erp)


def test_derived_digits_keys_all_reachable():
    """MULTI_SOURCE_DERIVED_DIGITS dùng CHUNG cho hai set — mọi khoá của nó
    phải ứng với một case có thật ở CẢ HAI danh sách, nếu không nó là cấu
    hình chết (đúng lớp lỗi _DATE_STATUS_LABELS['trạng thái giao'] đã mắc)."""
    gather_keys = {(t, q) for t, _f, q, _d, _e in cases.MULTI_SOURCE_GATHER_CASES}
    base_keys = {(t, q) for t, _b, q, _d, _e in cases.MULTI_SOURCE_CASES}
    for key in cases.MULTI_SOURCE_DERIVED_DIGITS:
        assert key in gather_keys, f"khoá {key} không ứng case gather nào"
        assert key in base_keys, f"khoá {key} không ứng case multi_source nào"


def test_gather_cases_shape_and_topics_exist():
    topics = set(fixtures.available_topics())
    for topic, tool_fixtures, question, doc_fact, erp_fact in cases.MULTI_SOURCE_GATHER_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert question.strip()
        assert tool_fixtures and all(
            k.strip() and v.strip() for k, v in tool_fixtures.items())
        assert doc_fact
        assert erp_fact


def test_gather_cases_tool_names_are_real():
    from src.erp_query.tools import build_erp_query_tools
    real_names = {t.name for t in build_erp_query_tools()}
    for topic, tool_fixtures, question, _doc, _erp in cases.MULTI_SOURCE_GATHER_CASES:
        for name in tool_fixtures:
            assert name in real_names, (
                f"case {topic}: tool_fixtures có {name!r} — không phải tên "
                f"tool thật nào trong build_erp_query_tools()")


def test_erp_fact_reachable_from_fixtures_or_question():
    """Tự-mâu-thuẫn là lỗi: erp_fact phải xuất hiện nguyên văn trong
    tool_fixtures HOẶC trong chính câu hỏi — nếu không, case đòi model nói
    điều không nguồn nào chứa. (Ca S00050 nằm ở vế "hoặc": mã đơn bán không
    bao giờ có trong đầu ra get_overdue_invoices thật, nó đến từ câu hỏi.)"""
    for topic, tool_fixtures, question, _doc, erp_fact in cases.MULTI_SOURCE_GATHER_CASES:
        corpus = (" ".join(tool_fixtures.values()) + " " + question).casefold()
        options = (erp_fact,) if isinstance(erp_fact, str) else erp_fact
        assert any(o.casefold() in corpus for o in options), (
            f"case {topic}: erp_fact {erp_fact!r} không có trong "
            f"tool_fixtures lẫn câu hỏi")
