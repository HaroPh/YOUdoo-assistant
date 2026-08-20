"""Chân đối chứng `--memory` của bộ `memory` phải ghép prompt ĐÚNG production.

Một chân đối chứng ghép sai còn tệ hơn không có chân nào: nó báo số đẹp về một
hình dạng prompt không tồn tại. Đây đúng lớp lỗi đã giết tính năng ký ức (test
tự dựng pool khác cấu hình production) và là lý do bộ synthesis_live dựng khối
bằng chính render_memory_block().
"""
import pytest

from evals.memory_presets import MEMORY_PRESETS
from evals.run_eval import eval_memory
from src.agents.prompts import CHITCHAT_PROMPT, SYSTEM_PROMPT

pytestmark = pytest.mark.asyncio


class _SpyLLM:
    """Bắt lại system prompt mà bộ đo thật sự gửi đi."""

    def __init__(self):
        self.system_prompts = []

    async def ainvoke(self, messages, config=None):
        self.system_prompts.append(messages[0].content)

        class _R:
            content = "ừ nhỉ"
        return _R()


async def test_chan_rong_khong_doi_prompt():
    """Không truyền --memory thì prompt phải y hệt bản gốc, không thêm gì."""
    llm = _SpyLLM()
    await eval_memory(llm, pace=0.0)
    assert llm.system_prompts
    for p in llm.system_prompts:
        assert p in (SYSTEM_PROMPT, CHITCHAT_PROMPT)


@pytest.mark.parametrize("preset", sorted(MEMORY_PRESETS))
async def test_chan_khac_rong_ghep_dung_nhu_production(preset):
    """production (nodes.py:51, :139) làm `memory + "\n\n" + prompt`.

    Kiểm CẢ HAI vế: khối ký ức đứng TRƯỚC, và prompt gốc còn NGUYÊN phía sau.
    Chỉ kiểm vế đầu thì một chân nuốt mất prompt gốc vẫn xanh.
    """
    llm = _SpyLLM()
    await eval_memory(llm, pace=0.0, memory=preset)
    khoi = MEMORY_PRESETS[preset]
    assert llm.system_prompts
    for p in llm.system_prompts:
        assert p.startswith(khoi + "\n\n"), "khối ký ức không đứng trước"
        goc = p[len(khoi) + 2:]
        assert goc in (SYSTEM_PROMPT, CHITCHAT_PROMPT), "prompt gốc bị đổi"


async def test_ket_qua_tu_mang_ten_chan():
    """Số của chân có ký ức mà không mang nhãn là số sẽ bị đọc nhầm thành số
    production — chính cái bẫy tôi vừa phải sửa comment cho trong run_eval."""
    assert (await eval_memory(_SpyLLM(), pace=0.0))["memory_preset"] == "none"
    assert (await eval_memory(_SpyLLM(), pace=0.0,
                              memory="inert"))["memory_preset"] == "inert"
