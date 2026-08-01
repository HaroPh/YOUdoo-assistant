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


def test_stub_erp_tools_wraps_all_real_tools():
    from evals.run_eval import _stub_erp_tools
    from src.erp_query.tools import build_erp_query_tools
    called = []
    tools = _stub_erp_tools({}, called)
    real_names = {t.name for t in build_erp_query_tools()}
    stub_names = {t.name for t in tools}
    assert stub_names == real_names


def test_stub_erp_tools_returns_fixture_for_named_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({"get_stock": "Còn 10 Desk Pad."}, called)
    t = next(t for t in tools if t.name == "get_stock")
    out = t.func(product="Desk Pad")
    assert out == "Còn 10 Desk Pad."
    assert called == ["get_stock"]


def test_stub_erp_tools_default_no_data_for_unlisted_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({}, called)
    t = next(t for t in tools if t.name == "find_customer")
    out = t.func(name="anyone")
    assert out == "Không có dữ liệu liên quan."
    assert called == ["find_customer"]


def test_stub_erp_tools_no_late_binding_closure_bug():
    """Chốt đúng bẫy nêu trong docstring _stub_erp_tools — mỗi stub phải trả
    ĐÚNG fixture của TOOL CỦA NÓ, không phải fixture của tool cuối vòng lặp."""
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools(
        {"get_stock": "A", "find_customer": "B", "find_product": "C"}, called)
    a = next(t for t in tools if t.name == "get_stock").func()
    b = next(t for t in tools if t.name == "find_customer").func()
    c = next(t for t in tools if t.name == "find_product").func()
    assert (a, b, c) == ("A", "B", "C")
    assert called == ["get_stock", "find_customer", "find_product"]


from evals import run_eval


def test_score_gather_both_ok():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026, giao dự kiến 20/07/2026",
        ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and fact_ok


def test_score_gather_tool_recall_fails_when_required_tool_not_called():
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026, 20/07/2026", ["find_customer"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert not tool_ok


def test_score_gather_fact_coverage_fails_when_fact_missing():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026", ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and not fact_ok


def test_score_gather_extra_tool_call_does_not_fail_recall():
    """required_tools là TẬP CON của called, không phải khớp tuyệt đối —
    model gọi thêm tool khác (dò tìm thêm) không bị tính là lỗi."""
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026", ["find_customer", "get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert tool_ok


def test_score_gather_fact_match_is_case_insensitive_normalized():
    tool_ok, fact_ok = run_eval._score_gather(
        "quá hạn 32 NGÀY", ["get_overdue_invoices"],
        ("get_overdue_invoices",), ("32 ngày",))
    assert tool_ok and fact_ok


def test_eval_gather_base_branch_calls_real_gather_erp_node():
    """Chống trôi: nhánh base PHẢI gọi make_gather_erp_node thật, không dựng
    lại logic thu thập (Global Constraint) — kiểm bằng đọc mã nguồn, cùng
    khuôn Task 8 SP-2b đã dùng cho eval_multi_source/render_fuse_input."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "make_gather_erp_node" in src
    assert "_stub_erp_tools" in src
    assert "_score_gather" in src


def test_eval_gather_policy_branch_does_not_call_real_node():
    """Nhánh policy KHÔNG gọi make_gather_erp_node — production chưa có
    nhánh này, gọi hàm thật sẽ chỉ chạy lại đúng prompt cũ, không đo được gì
    mới. Phải đi qua _run_gather_with_prompt riêng."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "_run_gather_with_prompt" in src


def test_run_gather_with_prompt_returns_erp_facts_key():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from langchain_core.messages import AIMessage, HumanMessage

    async def _run():
        agent = MagicMock()
        agent.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="18/07/2026")]})
        import src.agents.fanout as fanout_mod
        import unittest.mock
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: agent):
            out = await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])
        return out

    out = asyncio.run(_run())
    assert out == {"erp_facts": "18/07/2026"}


def test_run_gather_with_prompt_degrades_to_empty_on_exception():
    import asyncio
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    import unittest.mock

    async def _run():
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: (_ for _ in ()).throw(
                    RuntimeError("llm down"))):
            return await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])

    out = asyncio.run(_run())
    assert out == {"erp_facts": ""}


def test_gather_registered_in_eval_gate():
    from jobs import eval_gate
    assert "gather" in eval_gate.EVAL_FN
    assert eval_gate.EVAL_FN["gather"] is run_eval.eval_gather
    assert eval_gate.ROLE_FOR_SET["gather"] == "fusion"


def test_gather_excluded_from_baselines():
    """Không có baseline model cũ — node gather_erp không tồn tại trước
    SP-2b."""
    from jobs import eval_gate
    assert "gather" not in eval_gate.BASELINES


def test_gather_gate_returns_true_unconditionally():
    """Lượt đo đầu tiên: chưa có ngưỡng tuyệt đối, chỉ ghi nhận (spec §2)."""
    from jobs import eval_gate
    assert eval_gate._gate("gather", {"tool_recall": 0.0, "fact_coverage": 0.0}, None) is True
    assert eval_gate._gate("gather", {"tool_recall": 1.0, "fact_coverage": 1.0}, None) is True


def test_gather_excluded_from_set_all():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "all"])
    assert args.set == "all"
    assert "gather" in eval_gate.EVAL_FN  # đăng ký...
    # ...nhưng run() phải tự loại nó khi set == "all" — kiểm qua cùng công
    # thức run() dùng, không gọi run() thật (tốn API call thật).
    sets = [s for s in eval_gate.EVAL_FN if s not in ("sop_select", "gather")]
    assert "gather" not in sets
    assert "sop_select" not in sets
    assert "intent" in sets  # sanity: loại trừ không quá tay


def test_set_choices_includes_gather():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "gather"])
    assert args.set == "gather"
