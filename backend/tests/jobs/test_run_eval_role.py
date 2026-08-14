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


@pytest.mark.asyncio
async def test_main_truyen_role_xuong_dung_bo_nhay_vai(monkeypatch, capsys):
    """Nửa thứ hai của dây --role. `eval_gate.run` đã có test riêng; `main` thì
    chưa — gỡ hẳn khối `if args.set in ROLE_SENSITIVE_SETS` khỏi main thì toàn
    bộ suite vẫn xanh, và ba bộ nhạy vai lặng lẽ đo cấu hình admin (final
    review I4)."""
    thay = {}

    async def gia_intent(llm, pace=0.0, checkpoint_path=None, **kw):
        thay["intent"] = kw
        return {"set": "intent", "n": 1, "acc": 1.0, "fails": [], "errors": []}

    async def gia_confirm(llm, pace=0.0, checkpoint_path=None, **kw):
        thay["confirm"] = kw
        return {"set": "confirm", "n": 1, "acc": 1.0, "false_confirm": 0,
                "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_intent", gia_intent)
    monkeypatch.setattr(run_eval, "eval_confirm", gia_confirm)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())

    await run_eval.main(["--set", "intent", "--model", "m",
                         "--role", "accounting", "--pace", "0"])
    assert thay["intent"] == {"role": "accounting"}, "intent phải nhận role"

    await run_eval.main(["--set", "confirm", "--model", "m",
                         "--role", "accounting", "--pace", "0"])
    assert "role" not in thay["confirm"], \
        "confirm KHÔNG nhạy vai — nhận role là sai"


def test_bo_khong_nhay_vai_khong_co_hau_to_vai():
    """Hậu tố vai chỉ tồn tại với bộ nhạy vai. Bộ khác đo ở vai nào cũng cho
    kết quả y hệt admin, nên một file `…-confirm-accounting.json` sẽ KHÔNG AI
    TỪNG GHI ra — và cổng đi tìm nó là hỏng vĩnh viễn (final review I1)."""
    import os
    for s in ("confirm", "read", "synthesis", "multi_source"):
        p = run_eval.baseline_path("qwen3-8b", s, "accounting")
        assert os.path.basename(p) == f"baseline-qwen3-8b-{s}.json", s
    for s in ("intent", "planner"):
        p = run_eval.baseline_path("qwen3-8b", s, "accounting")
        assert os.path.basename(p) == f"baseline-qwen3-8b-{s}-accounting.json", s
