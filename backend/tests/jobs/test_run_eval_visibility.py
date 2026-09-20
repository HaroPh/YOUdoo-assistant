# backend/tests/jobs/test_run_eval_visibility.py
"""--role đi tới visibility của ba bộ gọi retrieve() thật; baseline có hậu tố
vai để --role warehouse --save-baseline KHÔNG đè baseline admin."""
import pytest

from evals import role_config, run_eval
from src.rag.visibility import UNRESTRICTED


def test_ba_bo_nhay_visibility_khai_tuong_minh():
    assert role_config.VISIBILITY_SENSITIVE_SETS == frozenset(
        {"retrieval", "synthesis_live", "multiturn"})
    # KHÔNG trộn với ROLE_SENSITIVE_SETS — cái đó là về PROMPT
    assert not (role_config.VISIBILITY_SENSITIVE_SETS & role_config.ROLE_SENSITIVE_SETS)


def test_visibility_for_theo_vai():
    assert role_config.visibility_for("admin") is UNRESTRICTED
    assert role_config.visibility_for("warehouse") == frozenset({"all"})
    assert role_config.visibility_for("sales") == frozenset({"all", "commercial"})


def test_baseline_path_retrieval_co_hau_to_vai_non_admin():
    assert run_eval.baseline_path("bge-m3", "retrieval", "admin").endswith(
        "baseline-bge-m3-retrieval.json")
    assert run_eval.baseline_path("bge-m3", "retrieval", "warehouse").endswith(
        "baseline-bge-m3-retrieval-warehouse.json")
    # bộ KHÔNG nhạy vai vẫn chuẩn hoá về admin như cũ
    assert run_eval.baseline_path("m", "confirm", "warehouse").endswith(
        "baseline-m-confirm.json")


@pytest.mark.asyncio
async def test_main_truyen_visibility_va_role_vao_eval_retrieval(monkeypatch):
    thay = {}

    async def gia(pace=0.0, checkpoint_path=None, **kw):
        thay.update(kw)
        return {"set": "retrieval", "n": 1, "rerank": True, "dang_go": "co_dau",
                "role": kw.get("role"), "recall_at_20": 1.0, "recall_at_6": 1.0,
                "mrr": 1.0, "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_retrieval", gia)
    await run_eval.main(["--set", "retrieval", "--model", "bge-m3",
                         "--pace", "0", "--role", "warehouse"])
    assert thay["visibility"] == frozenset({"all"})
    assert thay["role"] == "warehouse"


@pytest.mark.asyncio
async def test_main_mac_dinh_admin_la_unrestricted(monkeypatch):
    thay = {}

    async def gia(pace=0.0, checkpoint_path=None, **kw):
        thay.update(kw)
        return {"set": "retrieval", "n": 1, "rerank": True, "dang_go": "co_dau",
                "role": "admin", "recall_at_20": 1.0, "recall_at_6": 1.0,
                "mrr": 1.0, "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_retrieval", gia)
    await run_eval.main(["--set", "retrieval", "--model", "bge-m3", "--pace", "0"])
    assert thay["visibility"] is UNRESTRICTED
