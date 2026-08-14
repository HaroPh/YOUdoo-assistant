"""--role: plumbing và quy ước tên baseline.

Quy ước tên là chỗ nguy hiểm nhất của đợt: sai một lần là GHI ĐÈ baseline admin
đang dùng, và không có cách nào lấy lại ngoài chạy đo lại.
"""
import os

import pytest

from evals import run_eval
from evals.role_config import ROLE_SENSITIVE_SETS


def test_admin_khong_co_hau_to_trung_ten_file_dang_co():
    p = run_eval.baseline_path("qwen3-8b", "intent", "admin")
    assert os.path.basename(p) == "baseline-qwen3-8b-intent.json"


def test_mac_dinh_la_admin():
    assert run_eval.baseline_path("qwen3-8b", "intent") == \
        run_eval.baseline_path("qwen3-8b", "intent", "admin")


def test_vai_khac_co_hau_to():
    p = run_eval.baseline_path("qwen3-8b", "intent", "accounting")
    assert os.path.basename(p) == "baseline-qwen3-8b-intent-accounting.json"


def test_dau_hai_cham_trong_ten_model_van_duoc_thay():
    """Giữ nguyên hành vi cũ: alias model có thể chứa ':' (tên Ollama), mà ':'
    không hợp lệ trong tên file Windows."""
    p = run_eval.baseline_path("qwen3:8b", "intent", "admin")
    assert ":" not in os.path.basename(p)


def test_nam_file_baseline_dang_co_deu_tra_ve_dung_duong_dan():
    """Đối chứng mạnh: nếu quy ước lệch, ít nhất một trong năm file này sẽ trỏ
    sai và cổng sẽ đọc nhầm/ghi đè."""
    for set_name in ("intent", "confirm", "planner", "read", "synthesis"):
        p = run_eval.baseline_path("qwen3-8b", set_name, "admin")
        assert os.path.exists(p), f"không thấy baseline admin cho {set_name}: {p}"


def test_ba_bo_nhay_vai_nhan_tham_so_role():
    """Ba hàm đo nhạy-vai phải NHẬN role; các hàm khác KHÔNG — nhận mà không
    dùng còn tệ hơn không nhận, vì nó trông như đã hỗ trợ."""
    import inspect
    for name in ROLE_SENSITIVE_SETS:
        fn = getattr(run_eval, f"eval_{name}")
        assert "role" in inspect.signature(fn).parameters, name
    for name in ("confirm", "chitchat", "read", "synthesis"):
        fn = getattr(run_eval, f"eval_{name}")
        assert "role" not in inspect.signature(fn).parameters, name


@pytest.mark.asyncio
async def test_eval_intent_dung_prompt_cua_vai_duoc_chi_dinh(monkeypatch):
    """Đo THẬT cái prompt được gửi đi, không đo ý định."""
    from src.agents.prompts import INTENT_ROUTER_PROMPT
    thay = {}

    class FakeLLM:
        async def ainvoke(self, messages):
            thay["system"] = messages[0].content

            class R:
                content = "erp_read"
            return R()

    monkeypatch.setattr(run_eval, "INTENT_CASES", [("xem đơn S00012", "erp_read")])
    await run_eval.eval_intent(FakeLLM(), pace=0.0, role="accounting")
    assert thay["system"] == INTENT_ROUTER_PROMPT      # kế toán: worker block RỖNG

    await run_eval.eval_intent(FakeLLM(), pace=0.0, role="admin")
    assert thay["system"] != INTENT_ROUTER_PROMPT      # admin: có khối worker
