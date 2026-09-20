# backend/tests/jobs/test_run_eval_visibility.py
"""--role đi tới visibility của ba bộ gọi retrieve() thật; baseline có hậu tố
vai để --role warehouse --save-baseline KHÔNG đè baseline admin."""
from types import SimpleNamespace

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


# --- Fix-round #1 (review): synthesis_live/multiturn tự khai "role" trong kết
# quả JSON, cùng lý do memory_preset đã tự khai — không có baseline/gate nào
# đọc khoá này (out of scope), nhưng đọc JSON không được phép mù trước cấu
# hình vai đã đo.

@pytest.mark.asyncio
async def test_eval_synthesis_live_ket_qua_mang_role(monkeypatch):
    case = SimpleNamespace(question="câu hỏi", kind="insufficient",
                           expect="không áp dụng", source="x.pdf")
    monkeypatch.setattr(run_eval, "SYNTHESIS_LIVE_CASES", [case])
    monkeypatch.setattr(run_eval, "_retrieve",
                        lambda *a, **kw: SimpleNamespace(chunks=[], method="dense-rrf"))

    async def gia_synthesize(question, result, llm, memory=""):
        return "câu trả lời giả"

    monkeypatch.setattr(run_eval, "_synthesize", gia_synthesize)
    mac_dinh = await run_eval.eval_synthesis_live(object())
    assert mac_dinh["role"] == "admin"
    theo_vai = await run_eval.eval_synthesis_live(object(), role="warehouse")
    assert theo_vai["role"] == "warehouse"


@pytest.mark.asyncio
async def test_eval_multiturn_ket_qua_mang_role(monkeypatch):
    case = SimpleNamespace(prev_turn="câu trước", question="câu hỏi",
                           expect=frozenset({("a.pdf", "Điều 1")}), kind="elliptical")
    monkeypatch.setattr(run_eval, "MULTITURN_CASES", [case])
    monkeypatch.setattr(run_eval, "_retrieve",
                        lambda *a, **kw: SimpleNamespace(chunks=[], method="dense-rrf"))
    mac_dinh = await run_eval.eval_multiturn()
    assert mac_dinh["role"] == "admin"
    theo_vai = await run_eval.eval_multiturn(role="warehouse")
    assert theo_vai["role"] == "warehouse"


@pytest.mark.asyncio
async def test_main_truyen_role_vao_eval_multiturn_va_synthesis_live(monkeypatch):
    thay_multiturn, thay_synth = {}, {}

    async def gia_multiturn(pace=0.0, checkpoint_path=None, **kw):
        thay_multiturn.update(kw)
        return {"set": "multiturn", "n": 0, "role": kw.get("role"),
                "fails": [], "errors": []}

    async def gia_synthesis_live(llm, pace=0.0, checkpoint_path=None, **kw):
        thay_synth.update(kw)
        return {"set": "synthesis_live", "n": 0, "role": kw.get("role"),
                "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_multiturn", gia_multiturn)
    monkeypatch.setattr(run_eval, "eval_synthesis_live", gia_synthesis_live)
    # main() nhánh synthesis_live gọi _llm() → dựng router → PostgresUsageStore
    # đọc os.environ['DATABASE_URL']. Máy dev có .env nên xanh giả; runner CI
    # không có → KeyError → INFRA ERROR → SystemExit(2) (CI đỏ 2026-09-20,
    # run 35519484563). Mock như mọi test lái main() ở test_eval_gate.py.
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())

    await run_eval.main(["--set", "multiturn", "--model", "bge-m3",
                         "--pace", "0", "--role", "warehouse"])
    assert thay_multiturn["role"] == "warehouse"
    assert thay_multiturn["visibility"] == frozenset({"all"})

    await run_eval.main(["--set", "synthesis_live", "--model", "bge-m3",
                         "--pace", "0", "--role", "sales"])
    assert thay_synth["role"] == "sales"
    assert thay_synth["visibility"] == frozenset({"all", "commercial"})
