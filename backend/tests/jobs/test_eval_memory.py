"""Bộ đo ký ức phải bắt đúng ba hướng, và không tự lừa mình."""
import pytest

from evals import run_eval
from evals.cases import MEMORY_CASES


class _Resp:
    def __init__(self, content):
        self.content = content


class _ScriptedLLM:
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, messages):
        return _Resp(self.content)


def test_moi_loai_ky_vong_deu_co_ca():
    kinds = {kind for _p, _q, kind in MEMORY_CASES}
    assert kinds == {"none", "fact", "blocked"}


async def test_ghi_vu_vo_bi_tinh_la_false_injection(monkeypatch):
    only = [("CHITCHAT_PROMPT", "hôm nay trời đẹp nhỉ", "none")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    r = await run_eval.eval_memory(_ScriptedLLM("Vâng!\nGHI_NHỚ: thời tiết = đẹp"))
    assert r["false_injection"] == 1


async def test_ma_chung_tu_lot_qua_bi_tinh_la_leak(monkeypatch):
    only = [("SYSTEM_PROMPT", "nhớ đơn P00003 nhé", "blocked")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    # Cổng is_document_code phải chặn — nếu nó chặn đúng thì KHÔNG tính leak.
    r = await run_eval.eval_memory(_ScriptedLLM("Ừ.\nGHI_NHỚ: đơn quan trọng = P00003"))
    assert r["leaked_doc_code"] == 0


async def test_khong_phat_marker_khi_can_thi_tinh_missed(monkeypatch):
    only = [("CHITCHAT_PROMPT", "từ giờ trả lời ngắn gọn", "fact")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    r = await run_eval.eval_memory(_ScriptedLLM("Vâng ạ."))
    assert r["recall"] == 0.0
    assert r["false_injection"] == 0
