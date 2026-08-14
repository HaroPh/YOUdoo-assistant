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


# ── eval_multi_source_gather + đăng ký eval_gate ─────────────────────────────

from evals import run_eval


def test_eval_calls_real_gather_node_and_real_fuse_prompt():
    """Chống trôi (cùng khuôn test_eval_gather.py đã dùng): hàm PHẢI đi qua
    node/prompt production thật, không dựng lại logic thu thập hay tổng
    hợp — đó là điều kiện để phép đo không trôi khỏi thứ nó đang đo."""
    import inspect
    src = inspect.getsource(run_eval.eval_multi_source_gather)
    for token in ("make_gather_erp_node", "_stub_erp_tools", "FUSE_PROMPT",
                  "render_fuse_input", "_score_fusion",
                  "allowed_extra_text=question"):
        assert token in src, f"thiếu {token}"


def test_eval_scores_against_tool_fixtures_not_model_output():
    """basis của `allowed` phải là tool_fixtures (sự thật gốc), KHÔNG phải
    erp_facts model sinh ra — nếu lấy erp_facts, số do chính tầng gather bịa
    sẽ tự được hợp thức hoá (spec §5)."""
    import inspect
    src = inspect.getsource(run_eval.eval_multi_source_gather)
    assert "tool_fixtures.values()" in src


def test_eval_wires_gather_output_into_fuse_input():
    """Kiểm THẬT SỰ chạy (không chỉ đọc mã): erp_facts do gather_erp trả về
    phải đi vào render_fuse_input, và `called` phải được ghi lại."""
    import asyncio
    import unittest.mock
    from langchain_core.messages import AIMessage

    seen_fuse_inputs = []

    class _FakeLLM:
        async def ainvoke(self, messages):
            seen_fuse_inputs.append(messages[-1].content)
            return AIMessage(content="câu trả lời bất kỳ\nĐã dùng: 1")

    async def _fake_node(state):
        return {"erp_facts": "DẤU-VÂN-TAY-GATHER"}

    with unittest.mock.patch.object(run_eval, "make_gather_erp_node",
                                    lambda llm, tools: _fake_node):
        out = asyncio.run(run_eval.eval_multi_source_gather(_FakeLLM()))

    assert out["set"] == "multi_source_gather"
    assert out["n"] == len(cases.MULTI_SOURCE_GATHER_CASES)
    assert not out["errors"], out["errors"]
    assert any("DẤU-VÂN-TAY-GATHER" in s for s in seen_fuse_inputs), (
        "erp_facts của gather_erp phải đi vào render_fuse_input")
    for f in out["fails"]:
        assert "called" in f, (
            "mỗi bản ghi fail phải kèm `called` — không có nó thì không phân "
            "biệt được 'chọn sai tool' với 'tổng hợp kém'")


def test_registered_in_eval_gate():
    from jobs import eval_gate
    assert eval_gate.EVAL_FN["multi_source_gather"] is run_eval.eval_multi_source_gather
    assert eval_gate.ROLE_FOR_SET["multi_source_gather"] == "fusion"


def test_no_baseline_and_gate_always_passes():
    """Chưa có baseline (set ra đời 2026-08-04, không model cũ nào từng đo)
    — GÁC NHẸ y như `gather`: chỉ ghi nhận."""
    from jobs import eval_gate
    assert "multi_source_gather" not in eval_gate.BASELINE_SETS
    assert eval_gate._gate("multi_source_gather",
                           {"both_source_coverage": 0.0,
                            "citation_validity": 0.0,
                            "fabricated_number": 9}, None) is True
    assert eval_gate._gate("multi_source_gather",
                           {"both_source_coverage": 1.0,
                            "citation_validity": 1.0,
                            "fabricated_number": 0}, None) is True


def test_excluded_from_set_all_but_selectable():
    """Trong `all` sẽ luôn PASS giả và làm loãng tín hiệu job hàng đêm —
    cùng lý do `gather`/`sop_select` bị loại."""
    import argparse
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args(["--set", "multi_source_gather"]).set == "multi_source_gather"
    sets = [s for s in eval_gate.EVAL_FN
            if s not in ("sop_select", "gather", "multi_source_gather")]
    assert "multi_source_gather" not in sets
    assert "multi_source" in sets  # sanity: loại trừ không quá tay
