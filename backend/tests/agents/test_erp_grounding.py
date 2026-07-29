import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.erp_grounding import (
    verify_erp_grounding, ERP_GROUNDING_FALLBACK_MSG,
)


def _llm(reply_text):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=reply_text))
    return llm


@pytest.mark.asyncio
async def test_grounded_answer_kept_unchanged():
    llm = _llm("CÓ")
    result = await verify_erp_grounding(
        "Đơn S00123 đang ở trạng thái sale.", ['{"status": "success"}'], llm)
    assert result == "Đơn S00123 đang ở trạng thái sale."


@pytest.mark.asyncio
async def test_ungrounded_answer_replaced_with_fallback():
    llm = _llm("KHÔNG")
    result = await verify_erp_grounding(
        "Đơn S00123 đang ở trạng thái sale, tạo ngày 2026-07-07.",
        ['{"status": "success", "data": {"date_order": "2026-07-22"}}'], llm)
    assert result == ERP_GROUNDING_FALLBACK_MSG


@pytest.mark.asyncio
async def test_empty_tool_outputs_skips_llm_call():
    llm = _llm("KHÔNG")  # would fail the test if ever called
    result = await verify_erp_grounding("Câu trả lời bất kỳ.", [], llm)
    assert result == "Câu trả lời bất kỳ."
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_llm_error_fails_open_keeps_answer():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))
    result = await verify_erp_grounding(
        "Đơn S00123 đang ở trạng thái sale.", ['{"status": "success"}'], llm)
    assert result == "Đơn S00123 đang ở trạng thái sale."


@pytest.mark.asyncio
async def test_verdict_without_diacritics_also_recognized():
    # Local model output isn't guaranteed to render Vietnamese diacritics
    # consistently in a short verdict reply — "KHONG" must be recognized
    # the same as "KHÔNG".
    llm = _llm("KHONG")
    result = await verify_erp_grounding(
        "Câu trả lời có số liệu bịa.", ['{"status": "success"}'], llm)
    assert result == ERP_GROUNDING_FALLBACK_MSG
