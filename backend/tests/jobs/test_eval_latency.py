# backend/tests/jobs/test_eval_latency.py
"""Latency capture: _percentiles thuần + 3 set cũ trả lat_p50/lat_p95."""
import asyncio

import pytest

from evals import run_eval


def test_percentiles_empty_returns_zeros():
    assert run_eval._percentiles([]) == (0, 0)


def test_percentiles_single_sample():
    assert run_eval._percentiles([120.0]) == (120, 120)


def test_percentiles_sorted_selection():
    # 10 mẫu 100..1000: p50 = phần tử thứ ceil(0.5*10)=5 (index 4) = 500
    # p95 = phần tử thứ ceil(0.95*10)=10 (index 9) = 1000
    samples = [float(x) for x in (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000)]
    assert run_eval._percentiles(samples) == (500, 1000)


def test_percentiles_unsorted_input_is_sorted_first():
    samples = [1000.0, 100.0, 500.0]
    p50, p95 = run_eval._percentiles(samples)
    assert p50 == 500 and p95 == 1000


@pytest.mark.asyncio
async def test_timed_returns_result_and_positive_latency():
    # sleep 50ms nhưng chỉ đòi >= 10ms: biên 5 lần, CÓ CHỦ ĐÍCH.
    #
    # Bản cũ ngủ 10ms rồi đòi >= 10.0 — biên BẰNG KHÔNG. Độ phân giải bộ đếm
    # của Windows là ~15,6ms, nên dưới tải toàn suite `asyncio.sleep` thỉnh
    # thoảng về sớm hơn ngưỡng vài phần trăm mili-giây và test đỏ ngẫu nhiên
    # (quan sát được 2026-08-19: đỏ một lần trong lượt chạy đầy đủ, xanh khi
    # chạy riêng và xanh ở lượt chạy đầy đủ kế tiếp).
    #
    # KHÔNG hạ ngưỡng xuống `> 0`: như vậy test chỉ còn chứng minh đồng hồ
    # chạy, không chứng minh nó đo đúng khoảng thời gian của coro. Giữ ngưỡng
    # và nới thời gian ngủ thì khẳng định vẫn có nghĩa, chỉ tốn thêm 40ms.
    async def work():
        await asyncio.sleep(0.05)
        return "xong"
    result, ms = await run_eval._timed(work())
    assert result == "xong"
    assert ms >= 10.0


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """Trả cố định 1 nội dung cho mọi lời gọi."""
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, messages):
        return _FakeResp(self.content)


@pytest.mark.asyncio
async def test_eval_intent_reports_latency_keys():
    result = await run_eval.eval_intent(_FakeLLM("erp_read"))
    assert "lat_p50" in result and "lat_p95" in result
    assert isinstance(result["lat_p50"], int)
    assert isinstance(result["lat_p95"], int)


@pytest.mark.asyncio
async def test_eval_confirm_reports_latency_keys():
    result = await run_eval.eval_confirm(_FakeLLM("CONFIRM"))
    assert "lat_p50" in result and "lat_p95" in result


@pytest.mark.asyncio
async def test_eval_chitchat_reports_latency_keys():
    result = await run_eval.eval_chitchat(_FakeLLM("Xin chào, mình có thể giúp gì?"))
    assert "lat_p50" in result and "lat_p95" in result
