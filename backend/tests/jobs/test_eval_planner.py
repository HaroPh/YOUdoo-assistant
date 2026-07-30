# backend/tests/jobs/test_eval_planner.py
"""Set planner: tool_acc / args_acc / dangerous_misroute / parse_fail."""
import json

import pytest

from evals import cases, run_eval


def test_planner_cases_shape():
    assert len(cases.PLANNER_CASES) >= 20
    for text, tool, args in cases.PLANNER_CASES:
        assert isinstance(text, str) and text.strip()
        assert isinstance(tool, str) and tool.strip()
        assert isinstance(args, dict)


def test_norm_strips_and_casefolds():
    assert run_eval._norm("  S00042  ") == "s00042"
    assert run_eval._norm(5) == "5"


def test_args_match_exact_string():
    assert run_eval._args_match({"order_ref": "S00042"}, {"order_ref": "s00042"})


def test_args_match_number_tolerant_of_type():
    assert run_eval._args_match({"qty": 5}, {"qty": 5.0})
    assert run_eval._args_match({"price": 12000}, {"price": "12000"})


def test_args_match_missing_key_fails():
    assert not run_eval._args_match({"order_ref": "S00042"}, {})


def test_args_match_wrong_value_fails():
    assert not run_eval._args_match({"order_ref": "S00042"}, {"order_ref": "S00099"})


def test_args_match_ignores_extra_keys_in_got():
    assert run_eval._args_match({"order_ref": "S00042"},
                                {"order_ref": "S00042", "note": None})


def test_args_match_list_of_dict_declared_keys_only():
    expected = {"lines": [{"product": "Large Cabinet", "qty": 2}]}
    got = {"lines": [{"product": "Large Cabinet", "qty": 2, "price_unit": 100}]}
    assert run_eval._args_match(expected, got)


def test_args_match_list_length_mismatch_fails():
    expected = {"lines": [{"product": "A", "qty": 1}]}
    got = {"lines": []}
    assert not run_eval._args_match(expected, got)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _ScriptedLLM:
    """Trả nội dung theo thứ tự case (list), lặp lại phần tử cuối nếu hết."""
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    async def ainvoke(self, messages):
        i = min(self.calls, len(self.contents) - 1)
        self.calls += 1
        return _FakeResp(self.contents[i])


def _plan_json_str(tool, args):
    return json.dumps({"tool": tool, "args": args, "summary": "x"},
                      ensure_ascii=False)


@pytest.mark.asyncio
async def test_eval_planner_all_correct_gives_perfect_scores(monkeypatch):
    only = [("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"})]
    monkeypatch.setattr(cases, "PLANNER_CASES", only)
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM([_plan_json_str("confirm_sale_order",
                                       {"order_ref": "S00042"})])
    r = await run_eval.eval_planner(llm)
    assert r["set"] == "planner" and r["n"] == 1
    assert r["tool_acc"] == 1.0 and r["args_acc"] == 1.0
    assert r["dangerous_misroute"] == 0 and r["parse_fail"] == 0
    assert r["errors"] == []


@pytest.mark.asyncio
async def test_eval_planner_wrong_write_tool_is_dangerous_misroute(monkeypatch):
    only = [("xác nhận phiếu WH/IN/00005", "validate_picking",
             {"picking_ref": "WH/IN/00005"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    # đúng lớp lỗi thật round 11: validate_picking bị nhầm confirm_purchase_order
    llm = _ScriptedLLM([_plan_json_str("confirm_purchase_order",
                                       {"order_ref": "WH/IN/00005"})])
    r = await run_eval.eval_planner(llm)
    assert r["tool_acc"] == 0.0
    assert r["dangerous_misroute"] == 1


@pytest.mark.asyncio
async def test_eval_planner_misroute_is_case_insensitive(monkeypatch):
    # review finding round 1: tool_ok so bằng _norm (case/whitespace-
    # insensitive) nhưng dangerous_misroute từng so raw string với
    # WRITE_TOOL_NAMES — model trả tool đúng NHƯNG khác hoa/thường
    # ("Confirm_Purchase_Order") phải vẫn tính là misroute, không được lọt lưới.
    only = [("xác nhận phiếu WH/IN/00005", "validate_picking",
             {"picking_ref": "WH/IN/00005"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM([_plan_json_str("Confirm_Purchase_Order",
                                       {"order_ref": "WH/IN/00005"})])
    r = await run_eval.eval_planner(llm)
    assert r["tool_acc"] == 0.0
    assert r["dangerous_misroute"] == 1


@pytest.mark.asyncio
async def test_eval_planner_other_is_not_dangerous_misroute(monkeypatch):
    only = [("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM([_plan_json_str("other", {})])
    r = await run_eval.eval_planner(llm)
    assert r["tool_acc"] == 0.0
    # "other" = "không biết" → an toàn, KHÔNG tính misroute
    assert r["dangerous_misroute"] == 0


@pytest.mark.asyncio
async def test_eval_planner_unparseable_counts_parse_fail_not_misroute(monkeypatch):
    only = [("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM(["đây không phải JSON gì cả"])
    r = await run_eval.eval_planner(llm)
    assert r["parse_fail"] == 1
    assert r["dangerous_misroute"] == 0
    assert r["tool_acc"] == 0.0


@pytest.mark.asyncio
async def test_eval_planner_right_tool_wrong_args(monkeypatch):
    only = [("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM([_plan_json_str("confirm_sale_order",
                                       {"order_ref": "S00099"})])
    r = await run_eval.eval_planner(llm)
    assert r["tool_acc"] == 1.0
    assert r["args_acc"] == 0.0
    assert r["dangerous_misroute"] == 0


@pytest.mark.asyncio
async def test_eval_planner_reports_latency(monkeypatch):
    only = [("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"})]
    monkeypatch.setattr(run_eval, "PLANNER_CASES", only)
    llm = _ScriptedLLM([_plan_json_str("confirm_sale_order",
                                       {"order_ref": "S00042"})])
    r = await run_eval.eval_planner(llm)
    assert "lat_p50" in r and "lat_p95" in r
