# backend/tests/jobs/test_eval_gather.py
"""Set gather: đo bước THU THẬP của gather_erp — tách khỏi bước tổng hợp mà
multi_source đã đo. Không gate baseline-relative (không có baseline model cũ
— node gather_erp không tồn tại trước SP-2b)."""
from evals import cases, fixtures


def test_gather_cases_shape_and_topics_exist():
    assert len(cases.GATHER_CASES) >= 4
    topics = set(fixtures.available_topics())
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert question.strip()
        assert required_tools and all(t.strip() for t in required_tools)
        assert required_facts and all(f.strip() for f in required_facts)


def test_gather_cases_required_tools_have_fixtures():
    """Mọi tool trong required_tools PHẢI có mặt trong tool_fixtures của
    chính case đó — nếu không, case tự mâu thuẫn: đòi model gọi một tool mà
    không có dữ liệu nào để nó lấy được."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in tool_fixtures, (
                f"required_tools có {t!r} nhưng case {topic}/{question!r} "
                f"không có fixture cho tool đó")


def test_gather_cases_required_facts_exist_in_fixtures():
    """Nửa còn lại của kiểm tra tự-mâu-thuẫn: mỗi required_fact PHẢI xuất
    hiện nguyên văn (không phân biệt hoa/thường) trong ÍT NHẤT MỘT fixture
    của case đó — nếu không, case đòi model nói điều dữ liệu không hề chứa."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        corpus = " ".join(tool_fixtures.values()).casefold()
        for f in required_facts:
            assert f.casefold() in corpus, (
                f"required_fact {f!r} không có trong tool_fixtures của case "
                f"{topic}/{question!r}")


def test_gather_cases_required_tools_are_real_erp_tool_names():
    from src.erp_query.tools import build_erp_query_tools
    real_names = {t.name for t in build_erp_query_tools()}
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in real_names, (
                f"required_tools có {t!r} — không phải tên tool thật nào "
                f"trong build_erp_query_tools()")
