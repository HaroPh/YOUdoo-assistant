# backend/tests/jobs/test_eval_read.py
"""Set read: tool_acc / param_acc / fabricated_param (giá trị thực thể bịa)."""
import pytest

from evals import cases, run_eval


def test_read_cases_shape():
    assert len(cases.READ_CASES) >= 16
    for text, tool, args, entity_keys in cases.READ_CASES:
        assert isinstance(text, str) and text.strip()
        assert isinstance(tool, str) and tool.strip()
        assert isinstance(args, dict)
        assert isinstance(entity_keys, tuple)
        # mọi entity_key phải có trong args kỳ vọng, nếu không quy tắc vô nghĩa
        for k in entity_keys:
            assert k in args, f"{tool}: entity_key {k} thiếu trong expected args"


class _FakeToolCallResp:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _ToolCallLLM:
    """Giả model có bind_tools: trả tool_calls đã dựng sẵn."""
    def __init__(self, tool_calls_per_case):
        self.scripted = list(tool_calls_per_case)
        self.calls = 0
        self.bound = False

    def bind_tools(self, tools):
        self.bound = True
        return self

    async def ainvoke(self, messages):
        i = min(self.calls, len(self.scripted) - 1)
        self.calls += 1
        return _FakeToolCallResp(self.scripted[i])


def _tc(name, args):
    return [{"name": name, "args": args, "id": "call_1"}]


@pytest.mark.asyncio
async def test_eval_read_correct_tool_and_params(monkeypatch):
    only = [("tồn kho Desk Pad còn bao nhiêu?", "get_stock",
             {"product": "Desk Pad"}, ("product",))]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([_tc("get_stock", {"product": "Desk Pad"})])
    r = await run_eval.eval_read(llm)
    assert r["set"] == "read" and r["n"] == 1
    assert r["tool_acc"] == 1.0 and r["param_acc"] == 1.0
    assert r["fabricated_param"] == 0
    assert llm.bound is True    # phải bind_tools, không gọi trần


@pytest.mark.asyncio
async def test_eval_read_wrong_tool(monkeypatch):
    only = [("tồn kho Desk Pad còn bao nhiêu?", "get_stock",
             {"product": "Desk Pad"}, ("product",))]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([_tc("get_lots", {"product": "Desk Pad"})])
    r = await run_eval.eval_read(llm)
    assert r["tool_acc"] == 0.0


@pytest.mark.asyncio
async def test_eval_read_fabricated_entity_value_detected(monkeypatch):
    # đúng lớp lỗi thật round 6/round 3: bịa tên thực thể không có trong câu hỏi
    only = [("tồn kho Desk Pad còn bao nhiêu?", "get_stock",
             {"product": "Desk Pad"}, ("product",))]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([_tc("get_stock", {"product": "NCC"})])
    r = await run_eval.eval_read(llm)
    assert r["fabricated_param"] == 1
    assert r["param_acc"] == 0.0


@pytest.mark.asyncio
async def test_eval_read_extra_non_entity_key_is_not_fabrication(monkeypatch):
    # model tự thêm limit là hợp lý — KHÔNG tính bịa
    only = [("liệt kê đơn bán tháng này", "list_sale_orders", {}, ())]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([_tc("list_sale_orders", {"limit": 50})])
    r = await run_eval.eval_read(llm)
    assert r["fabricated_param"] == 0
    assert r["tool_acc"] == 1.0 and r["param_acc"] == 1.0


@pytest.mark.asyncio
async def test_eval_read_no_tool_call_counts_as_fail_not_fabrication(monkeypatch):
    only = [("tồn kho Desk Pad còn bao nhiêu?", "get_stock",
             {"product": "Desk Pad"}, ("product",))]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([[]])          # không gọi tool nào
    r = await run_eval.eval_read(llm)
    assert r["tool_acc"] == 0.0
    assert r["fabricated_param"] == 0


@pytest.mark.asyncio
async def test_eval_read_reports_latency(monkeypatch):
    only = [("liệt kê đơn bán tháng này", "list_sale_orders", {}, ())]
    monkeypatch.setattr(run_eval, "READ_CASES", only)
    monkeypatch.setattr(run_eval, "build_erp_query_tools", lambda: [])
    llm = _ToolCallLLM([_tc("list_sale_orders", {})])
    r = await run_eval.eval_read(llm)
    assert "lat_p50" in r and "lat_p95" in r
