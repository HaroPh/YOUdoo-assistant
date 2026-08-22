# backend/tests/jobs/test_eval_gate.py
"""eval-gate: verdict aggregation, resolution model theo config sống, pacing auto."""
import argparse

import pytest

from evals import run_eval
from jobs import eval_gate
from jobs.registry import GATE_FAIL, INFRA_ERROR, PASS


def _args(model=None, set_="both", pace=None, role="admin",
          baseline_model=eval_gate.BASELINE_MODEL):
    """Namespace dựng TAY, không qua argparse — nên mỗi cờ mới của add_args
    phải được thêm vào đây, nếu không `run` ném AttributeError và mọi test
    trong file này đỏ cùng lúc (đã xảy ra khi thêm --baseline-model).

    Mặc định lấy TỪ eval_gate.BASELINE_MODEL chứ không viết lại chuỗi
    "qwen3-8b": hai nơi khai cùng một hằng là cách nó trôi lệch."""
    return argparse.Namespace(model=model, set=set_, pace=pace, role=role,
                              baseline_model=baseline_model)


def _patch_baseline(monkeypatch, set_name, path):
    """Giả baseline cho MỘT set, các set khác vẫn rơi về _baseline_for thật.
    Thay cho monkeypatch.setitem(eval_gate.BASELINES, ...) cũ — BASELINES đã
    bị thay bằng BASELINE_SETS + _baseline_for (Task 4, single source of
    truth run_eval.baseline_path)."""
    orig = eval_gate._baseline_for

    def fake(name, model, role):
        if name == set_name:
            return str(path)
        return orig(name, model, role)
    monkeypatch.setattr(eval_gate, "_baseline_for", fake)


def _fake_eval(set_name, acc, false_confirm=0, n=40):
    async def fn(llm, pace=0.0, checkpoint_path=None, **kw):
        # Bắt kwarg thừa bằng **kw thay vì khai `role=None`: chỉ như vậy mới
        # phân biệt được "run() CÓ truyền role" với "run() KHÔNG truyền". Bản
        # cũ khai role=None rồi VỨT ĐI, nên gỡ hẳn dây --role khỏi run() vẫn
        # xanh — dây đó không ai canh (final review I4).
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path,
                         "kw": kw})
        d = {"set": set_name, "n": n, "acc": acc, "fails": [], "errors": []}
        if set_name == "confirm":
            d["false_confirm"] = false_confirm
        return d
    fn.calls = []
    return fn


def _patch(monkeypatch, intent_acc=1.0, confirm_acc=1.0, false_confirm=0):
    fi = _fake_eval("intent", intent_acc)
    fc = _fake_eval("confirm", confirm_acc, false_confirm, n=24)
    monkeypatch.setitem(eval_gate.EVAL_FN, "intent", fi)
    monkeypatch.setitem(eval_gate.EVAL_FN, "confirm", fc)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    return fi, fc


def test_both_pass_exit_zero(monkeypatch):
    _patch(monkeypatch)
    result = eval_gate.run(_args())
    assert result.exit_code == PASS and result.verdict == "PASS"
    assert set(result.detail) == {"intent", "confirm"}


def test_one_set_fail_exit_one(monkeypatch):
    # confirm: false_confirm=1 → fail bất kể acc (điều kiện tuyệt đối M3)
    _patch(monkeypatch, confirm_acc=1.0, false_confirm=1)
    result = eval_gate.run(_args())
    assert result.exit_code == GATE_FAIL and result.verdict == "FAIL"
    assert result.detail["confirm"]["gate"] == "FAIL"
    assert result.detail["intent"]["gate"] == "PASS"


def test_intent_below_baseline_fails(monkeypatch):
    _patch(monkeypatch, intent_acc=0.0)
    result = eval_gate.run(_args(set_="intent"))
    assert result.exit_code == GATE_FAIL


def test_eval_exception_exit_two(monkeypatch):
    async def boom(llm, pace=0.0, checkpoint_path=None, role=None):
        raise ConnectionError("litellm chết")
    monkeypatch.setitem(eval_gate.EVAL_FN, "intent", boom)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="intent"))
    assert result.exit_code == INFRA_ERROR and result.verdict == "ERROR"
    assert "litellm chết" in result.detail["intent"]["error"]


def test_set_intent_only_runs_one_set(monkeypatch):
    fi, fc = _patch(monkeypatch)
    result = eval_gate.run(_args(set_="intent"))
    assert list(result.detail) == ["intent"]
    assert len(fi.calls) == 1 and len(fc.calls) == 0


def test_khong_truyen_model_thi_dung_dau_chuoi_catalog(monkeypatch):
    """Thay test_default_measures_live_config (bản cũ đọc MODEL_ROUTER/
    MODEL_EVALUATOR/AGENT_MODEL — cơ chế đó đã bị xoá ở SP-1B Task 8). Hành vi
    MỚI: không truyền --model thì mỗi bộ dùng đúng chain_for(role)[0].alias
    từ catalog tĩnh — không đọc biến môi trường nào."""
    _patch(monkeypatch)
    result = eval_gate.run(_args())
    assert result.detail["intent"]["model"] == "gemini-3.1-flash-lite"
    assert result.detail["confirm"]["model"] == "gemini-3.1-flash-lite"


def test_model_override_applies_to_all_sets(monkeypatch):
    _patch(monkeypatch)
    result = eval_gate.run(_args(model="candidate-x"))
    assert result.detail["intent"]["model"] == "candidate-x"
    assert result.detail["confirm"]["model"] == "candidate-x"


def test_nhip_tu_dong_suy_tu_rpm_catalog(monkeypatch):
    """Thay test_pace_auto_cloud_5s_local_0 (bản cũ giả định có model 'local'
    pace=0 — không còn model local nào trong catalog kể từ SP-1). Hành vi
    MỚI: pace luôn = (60/rpm)*1.2, không có nhánh đặc biệt nào."""
    from src.llm.catalog import chain_for

    fi, fc = _patch(monkeypatch)
    eval_gate.run(_args())
    # Suy kỳ vọng TỪ CATALOG, không ghim hằng số: sau đợt gom 2026-08-21 mọi
    # vai chung một mắt xích đầu, nên hai dòng dưới ra CÙNG một con số. Ghim
    # hằng số thì test vẫn xanh kể cả khi công thức bị thay bằng một hằng —
    # nó sẽ không còn đo gì. Suy từ rpm thì nó vẫn đo đúng công thức.
    def nhip(vai):
        return (60 / chain_for(vai)[0].rpm) * 1.2

    assert fi.calls[0]["pace"] == pytest.approx(nhip("router"))
    assert fc.calls[0]["pace"] == pytest.approx(nhip("evaluator"))
    assert nhip("router") > 0


def test_pace_override_wins(monkeypatch):
    fi, _ = _patch(monkeypatch)
    eval_gate.run(_args(set_="intent", pace=1.5))
    assert fi.calls[0]["pace"] == 1.5


def test_router_reset_between_sets(monkeypatch):
    """Important #1 (final review SP-1C1): mỗi set chạy asyncio.run() riêng =
    event loop riêng; client async bám vào loop đã tạo ra nó, nên
    run_eval._router (cache cả tiến trình) phải bị xoá GIỮA hai set để set
    sau không tái sử dụng client bám loop đã đóng ("Event loop is closed").
    Xác nhận rẻ: bắt giá trị run_eval._router tại đúng thời điểm _llm() được
    gọi cho mỗi set — set đầu thấy giá trị CŨ (chưa bị đụng tới), set sau
    (confirm) phải thấy None (đã bị run() reset ở cuối vòng lặp set trước)."""
    seen = []

    def fake_llm(model, role=None):
        seen.append(run_eval._router)
        return object()

    fi, fc = _patch(monkeypatch)
    monkeypatch.setattr(run_eval, "_llm", fake_llm)
    sentinel = object()
    monkeypatch.setattr(run_eval, "_router", sentinel)

    eval_gate.run(_args())

    assert seen == [sentinel, None]
    # Sau khi cả hai set chạy xong, router cũng phải ở lại None (rebuild lười
    # ở lượt gọi kế tiếp bên ngoài job này), không rò rỉ instance nào ra ngoài.
    assert run_eval._router is None


def test_registered_and_schedulable():
    from jobs.registry import JOBS
    assert "eval-gate" in JOBS and JOBS["eval-gate"].schedulable is True


def _fake_chitchat_eval(violations=0, n=16):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        fails = [{"text": "x", "response": "Đã tạo", "matched_markers": ["đã tạo"]}
                 for _ in range(violations)]
        return {"set": "chitchat", "n": n, "violations": violations,
                "fails": fails, "errors": []}
    fn.calls = []
    return fn


def _fake_sop_select_eval(acc=1.0, hijack=0, n=20):
    async def fn(llm, pace=0.0, checkpoint_path=None, role=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        fails = []
        # Đơn giản hóa: nếu hijack > 0, có 1 fail
        if hijack > 0:
            fails.append({"text": "x", "expected": "tier1", "got": "sop",
                         "hijack": True})
        return {"set": "sop_select", "n": n, "acc": acc, "hijack": hijack,
                "lat_p50": 1000, "lat_p95": 2000, "fails": fails, "errors": []}
    fn.calls = []
    return fn


def _fake_gather_eval(tool_recall=1.0, fact_coverage=1.0, n=10):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        fails = []
        # Đơn giản hóa: nếu tool_recall hoặc fact_coverage < 1.0, có fails
        if tool_recall < 1.0:
            fails.append({"text": "x", "tool_recall": tool_recall})
        if fact_coverage < 1.0:
            fails.append({"text": "x", "fact_coverage": fact_coverage})
        return {"set": "gather", "n": n, "tool_recall": tool_recall,
                "fact_coverage": fact_coverage, "lat_p50": 1000, "lat_p95": 2000,
                "fails": fails, "errors": []}
    fn.calls = []
    return fn


def _fake_localize_eval(acc=1.0, fact_loss=0, n=7):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        fails = []
        if fact_loss > 0:
            fails.append({"text": "Xác nhận x", "lang": "en",
                         "reason": "roi_ve_ban_goc"})
        return {"set": "localize", "n": n, "acc": acc, "fact_loss": fact_loss,
                "lat_p50": 500, "lat_p95": 1000, "fails": fails, "errors": []}
    fn.calls = []
    return fn


def _fake_language_eval(acc=1.0, n=6):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        fails = []
        return {"set": "language", "n": n, "acc": acc,
                "lat_p50": 600, "lat_p95": 1200, "fails": fails, "errors": []}
    fn.calls = []
    return fn


def _fake_memory_eval(false_injection=0, leaked_doc_code=0, truncated_answer=0,
                      recall=1.0, n=7):
    async def fn(llm, **kwargs):
        fn.calls.append(kwargs)
        return {"set": "memory", "n": n,
                "false_injection": false_injection,
                "leaked_doc_code": leaked_doc_code,
                "truncated_answer": truncated_answer,
                "recall": recall,
                "lat_p50": 1, "lat_p95": 2, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_memory_ba_dem_deu_khong_thi_pass(monkeypatch):
    fmemory = _fake_memory_eval(false_injection=0, leaked_doc_code=0,
                                truncated_answer=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "memory", fmemory)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="memory"))
    assert result.exit_code == PASS and result.verdict == "PASS"
    assert result.detail["memory"]["gate"] == "PASS"


def test_memory_truncated_answer_khac_khong_thi_fail(monkeypatch):
    """Debt sweep: truncated_answer giờ là điều kiện gác TUYỆT ĐỐI thứ ba,
    ngang hàng false_injection/leaked_doc_code — trước đây nó chỉ vào báo
    cáo, không làm gate FAIL dù khác 0."""
    fmemory = _fake_memory_eval(false_injection=0, leaked_doc_code=0,
                                truncated_answer=1)
    monkeypatch.setitem(eval_gate.EVAL_FN, "memory", fmemory)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="memory"))
    assert result.exit_code == GATE_FAIL and result.verdict == "FAIL"
    assert result.detail["memory"]["truncated_answer"] == 1


def test_chitchat_zero_violations_passes(monkeypatch):
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="chitchat"))
    assert result.exit_code == PASS and result.verdict == "PASS"
    assert result.detail["chitchat"]["gate"] == "PASS"
    assert result.detail["chitchat"]["violations"] == 0


def test_chitchat_nonzero_violations_fails(monkeypatch):
    fchat = _fake_chitchat_eval(violations=2)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="chitchat"))
    assert result.exit_code == GATE_FAIL and result.verdict == "FAIL"
    assert result.detail["chitchat"]["violations"] == 2


def test_chitchat_never_reads_a_baseline_file(monkeypatch, tmp_path):
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    # chitchat không nằm trong BASELINE_SETS — nếu code lỡ tra cứu, file
    # thiếu sẽ lộ ra thành INFRA_ERROR thay vì PASS. Assert PASS tức là
    # đường code không đọc.
    assert "chitchat" not in eval_gate.BASELINE_SETS
    result = eval_gate.run(_args(set_="chitchat"))
    assert result.exit_code == PASS
    assert "baseline_acc" not in result.detail["chitchat"]
    assert "acc" not in result.detail["chitchat"]


def test_both_still_excludes_chitchat(monkeypatch):
    fi, fc = _patch(monkeypatch)
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)
    result = eval_gate.run(_args(set_="both"))
    assert set(result.detail) == {"intent", "confirm"}
    assert fchat.calls == []


def test_chitchat_model_resolution_uses_chitchat_role(monkeypatch):
    """chitchat dùng chain_for("chitchat")[0].alias từ catalog tĩnh — không
    còn đọc MODEL_CHITCHAT/AGENT_MODEL (cơ chế đó đã xoá ở SP-1B Task 8)."""
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="chitchat"))
    assert result.detail["chitchat"]["model"] == "gemini-3.1-flash-lite"


def test_chitchat_registered_as_valid_set_choice():
    # add_args đăng ký choices cho --set — verify "chitchat" có mặt bằng cách
    # dựng parser thật và parse.
    import argparse as _argparse
    p = _argparse.ArgumentParser()
    eval_gate.add_args(p)
    ns = p.parse_args(["--set", "chitchat"])
    assert ns.set == "chitchat"


def test_result_errors_means_infra_error_not_gate(monkeypatch):
    # S2 spec §3: đo không trọn vẹn → exit 2, KHÔNG có quyền PASS/FAIL —
    # exit 1 phải luôn nghĩa là "model đo được và kém", không phải "mạng hỏng"
    async def fn(llm, pace=0.0, checkpoint_path=None, role=None):
        return {"set": "intent", "n": 40, "acc": 0.975, "fails": [],
                "errors": [{"item": ["câu hỏi", "erp_read"],
                            "error": "timeout", "attempts": 3}]}
    monkeypatch.setitem(eval_gate.EVAL_FN, "intent", fn)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="intent"))
    assert result.exit_code == INFRA_ERROR and result.verdict == "ERROR"
    assert result.detail["intent"]["errors"][0]["error"] == "timeout"


def test_checkpoint_path_passed_per_set(monkeypatch):
    fi, fc = _patch(monkeypatch)
    eval_gate.run(_args())
    assert fi.calls[0]["checkpoint_path"].name == "_checkpoint-eval-gate-intent.json"
    assert fc.calls[0]["checkpoint_path"].name == "_checkpoint-eval-gate-confirm.json"


def _fake_planner_eval(tool_acc=1.0, dangerous_misroute=0, n=24):
    async def fn(llm, pace=0.0, checkpoint_path=None, role=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "planner", "n": n, "tool_acc": tool_acc, "args_acc": tool_acc,
                "dangerous_misroute": dangerous_misroute, "parse_fail": 0,
                "lat_p50": 900, "lat_p95": 1500, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_planner_gate_passes_at_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    _patch_baseline(monkeypatch, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", _fake_planner_eval(tool_acc=0.8))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == PASS


def test_planner_gate_fails_below_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    _patch_baseline(monkeypatch, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", _fake_planner_eval(tool_acc=0.7))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == GATE_FAIL


def test_planner_dangerous_misroute_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: ghi sai tool = ghi sai dữ liệu ERP, không nhân nhượng
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    _patch_baseline(monkeypatch, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner",
                        _fake_planner_eval(tool_acc=1.0, dangerous_misroute=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == GATE_FAIL
    assert result.detail["planner"]["gate"] == "FAIL"


def test_set_all_runs_every_registered_set_except_triple_light_gate(monkeypatch, tmp_path):
    """--set all phải chạy TẤT CẢ set đã đăng ký, TRỪ `gather`,
    `multi_source_gather`, và `localize` (gate của chúng không theo ngưỡng
    baseline nên để trong "all" chỉ tạo PASS/FAIL giả mà không gác được thứ
    gì thật).

    `sop_select` ĐÃ QUAY LẠI "all" (2026-08-17): nó bị loại 2026-07-31 vì cổng
    tuyệt đối (acc == 1.0) biết trước FAIL nên sẽ đỏ vĩnh viễn; lý do đó hết
    khi cổng về khuôn chung (hijack==0 + acc>=baseline). Để nó ngoài "all"
    thêm nữa nghĩa là hàng rào an toàn định tuyến tiếp tục không ai gác.

    `language` CŨNG ĐÃ QUAY LẠI "all" (final review, 2026-08-18): nó bị loại
    khi Task 6 tạo ra set này, với lý do "gate tuyệt đối = PASS/FAIL giả" —
    nhưng lý do đó tự mâu thuẫn với `chitchat` (cũng gate tuyệt đối, vẫn luôn
    nằm trong "all"), và loại nó khỏi job đêm nghĩa là không ai gác 4 prompt
    (CHITCHAT/RAG_SYNTHESIS/FUSE) khỏi hồi quy tiếng Anh — đúng thứ set này
    được viết ra để bắt. An toàn để đưa lại vì `eval_language`'s "en" giờ đòi
    bằng chứng dương (Fix 5 cùng đợt), không còn suy ngầm từ thiếu bằng chứng
    tiếng Việt (từng khiến body rỗng/lỗi lặng lẽ tính là "en" = PASS giả).

    `memory` (Task 7) CŨNG NẰM TRONG "all": nó có hai điều kiện an toàn TUYỆT
    ĐỐI (false_injection == 0, leaked_doc_code == 0), đúng tiền lệ `chitchat`
    và `language` — không phải phép đo tương đối cần baseline chưa có.

    Ba set còn lại KHÔNG nằm trong "all": gather, multi_source_gather,
    localize — đều có gate không theo baseline nên để trong "all" chỉ tạo
    PASS/FAIL giả mà không gác được thứ gì thật.

    Bẫy thật (nhiều lần: Task 2's fix round, rồi TÁI PHÁT khi Task 3/4/5 thêm
    read/synthesis/multi_source, rồi TÁI PHÁT LẦN NỮA ở plan
    2026-08-04-multi-source-gather-eval Task 3 khi multi_source_gather ra
    đời — cùng bị loại khỏi "all" nên assertion hard-code cứng danh sách tên
    phải theo kịp) mà quên patch vào test này — nếu 1 set không được patch,
    hàm eval THẬT sẽ chạy, lỗi (thiếu LLM/baseline thật), bị run()'s except
    nuốt mất, và assertion cũ (chỉ check key cố định) vẫn qua dù set đó CHƯA
    BAO GIỜ thực sự chạy thành công. Assert bằng
    set(eval_gate.EVAL_FN) - {"gather", "multi_source_gather", "localize"}
    (không phải danh sách cứng ngoài các tên bị loại) + exit_code + mỗi fake
    gọi đúng 1 lần, để không tái phát."""
    fi, fc = _patch(monkeypatch)
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)

    planner_base = tmp_path / "planner.json"
    planner_base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    _patch_baseline(monkeypatch, "planner", planner_base)
    fplanner = _fake_planner_eval(tool_acc=0.8)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", fplanner)

    read_base = tmp_path / "read.json"
    read_base.write_text('{"set":"read","n":20,"tool_acc":0.85}', encoding="utf-8")
    _patch_baseline(monkeypatch, "read", read_base)
    fread = _fake_read_eval(tool_acc=0.85)
    monkeypatch.setitem(eval_gate.EVAL_FN, "read", fread)

    synthesis_base = tmp_path / "synthesis.json"
    synthesis_base.write_text('{"set":"synthesis","n":12,"grounded_acc":1.0}', encoding="utf-8")
    _patch_baseline(monkeypatch, "synthesis", synthesis_base)
    fsynthesis = _fake_synthesis_eval(grounded_acc=1.0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "synthesis", fsynthesis)

    _patch_baseline(monkeypatch, "multi_source", _ms_base(tmp_path, coverage=0.75))
    fms = _fake_ms_eval(coverage=0.75)
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source", fms)

    sop_base = tmp_path / "sop.json"
    sop_base.write_text('{"set":"sop_select","n":27,"acc":0.9259}',
                        encoding="utf-8")
    _patch_baseline(monkeypatch, "sop_select", sop_base)
    fsop = _fake_sop_select_eval(acc=0.9259, hijack=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "sop_select", fsop)

    # gather's gate always returns True by design (no threshold yet) —
    # the real detector for accidental invocation is `calls == []` below,
    # not a FAIL verdict.
    fgather = _fake_gather_eval(tool_recall=0.0, fact_coverage=0.0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "gather", fgather)

    # multi_source_gather cũng bị loại khỏi "all" (chưa có baseline, gate
    # trả True vô điều kiện) — cùng lý do gather/sop_select ở trên.
    fmsg = _fake_multi_source_gather_eval(coverage=0.0, fabricated_number=9)
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source_gather", fmsg)

    # localize cũng bị loại khỏi "all" (chưa có baseline, gate trả True vô
    # điều kiện) — cùng lý do gather/multi_source_gather ở trên.
    flocalize = _fake_localize_eval(acc=1.0, fact_loss=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "localize", flocalize)

    # language ĐÃ QUAY LẠI "all" (final review, 2026-08-18) — xem docstring.
    flanguage = _fake_language_eval(acc=1.0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "language", flanguage)

    # memory NẰM TRONG "all": ba điều kiện an toàn TUYỆT ĐỐI (false_injection
    # == 0, leaked_doc_code == 0, truncated_answer == 0 — cái thứ ba thêm ở
    # debt sweep sau merge), đúng tiền lệ chitchat và language. Không thêm
    # vào tập loại trừ.
    fmemory = _fake_memory_eval()
    monkeypatch.setitem(eval_gate.EVAL_FN, "memory", fmemory)

    result = eval_gate.run(_args(set_="all"))

    assert set(result.detail) == \
        set(eval_gate.EVAL_FN) - {"gather", "multi_source_gather", "localize"}
    assert "sop_select" in result.detail
    assert "gather" not in result.detail
    assert "multi_source_gather" not in result.detail
    assert "localize" not in result.detail
    assert "language" in result.detail
    assert "memory" in result.detail
    assert result.exit_code == PASS
    for fn in (fi, fc, fchat, fplanner, fread, fsynthesis, fms, fsop, flanguage,
               fmemory):
        assert len(fn.calls) == 1, f"{fn} was not called exactly once"
    assert fgather.calls == [], "gather KHÔNG được chạy dưới --set all"
    assert fmsg.calls == [], "multi_source_gather KHÔNG được chạy dưới --set all"
    assert flocalize.calls == [], "localize KHÔNG được chạy dưới --set all"


def test_set_sop_select_still_runs_standalone(monkeypatch):
    """sop_select vẫn đăng ký đầy đủ và chạy được RIÊNG qua --set sop_select
    — Finding 5 chỉ loại nó khỏi tập "all", không xoá đăng ký."""
    fsop = _fake_sop_select_eval(acc=1.0, hijack=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "sop_select", fsop)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="sop_select"))
    assert result.exit_code == PASS
    assert list(result.detail) == ["sop_select"]
    assert len(fsop.calls) == 1


def test_set_gather_still_runs_standalone(monkeypatch):
    """gather vẫn đăng ký đầy đủ và chạy được RIÊNG qua --set gather
    — loại khỏi tập "all" nhưng không xoá đăng ký. Regression test:
    end-to-end run() không crash với KeyError: 'violations' (bug fix task-4
    round 1)."""
    fgather = _fake_gather_eval(tool_recall=0.95, fact_coverage=0.90)
    monkeypatch.setitem(eval_gate.EVAL_FN, "gather", fgather)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="gather"))
    assert result.exit_code == PASS
    assert list(result.detail) == ["gather"]
    assert result.detail["gather"]["tool_recall"] == 0.95
    assert result.detail["gather"]["fact_coverage"] == 0.90
    assert result.detail["gather"]["branch"] is None
    assert "violations" not in result.detail["gather"]
    assert len(fgather.calls) == 1


def test_set_multi_source_gather_still_runs_standalone(monkeypatch):
    """multi_source_gather vẫn đăng ký đầy đủ và chạy được RIÊNG qua
    --set multi_source_gather — loại khỏi tập "all" nhưng không xoá đăng ký
    (cùng khuôn test_set_gather_still_runs_standalone ở trên). Regression
    test: nhánh báo cáo `base is None` mới thêm
    (`elif set_name == "multi_source_gather":`) không crash vì thiếu khoá —
    đúng lớp lỗi đã xảy ra THẬT ở set gather (KeyError: 'violations', bug fix
    task-4 round 1). Dùng cố ý coverage thấp + fabricated_number > 0 để
    chứng minh gate vẫn PASS vô điều kiện ("gác nhẹ") thay vì tình cờ pass vì
    số đẹp."""
    fmsg = _fake_multi_source_gather_eval(coverage=0.2, fabricated_number=3)
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source_gather", fmsg)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="multi_source_gather"))
    assert result.exit_code == PASS
    assert list(result.detail) == ["multi_source_gather"]
    entry = result.detail["multi_source_gather"]
    assert entry["gate"] == "PASS"
    assert entry["both_source_coverage"] == 0.2
    assert entry["citation_validity"] == 1.0
    assert entry["fabricated_number"] == 3
    assert entry["lat_p50"] == 3000
    assert entry["lat_p95"] == 4500
    assert len(fmsg.calls) == 1


def test_sop_select_still_a_valid_set_choice():
    # add_args vẫn đăng ký "sop_select" trong choices --set dù đã loại khỏi
    # "all" — dựng parser thật, parse để xác nhận.
    import argparse as _argparse
    p = _argparse.ArgumentParser()
    eval_gate.add_args(p)
    ns = p.parse_args(["--set", "sop_select"])
    assert ns.set == "sop_select"


def _fake_read_eval(tool_acc=1.0, fabricated_param=0, n=20):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "read", "n": n, "tool_acc": tool_acc, "param_acc": tool_acc,
                "fabricated_param": fabricated_param,
                "lat_p50": 800, "lat_p95": 1400, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_read_gate_passes_at_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"read","n":20,"tool_acc":0.85}', encoding="utf-8")
    _patch_baseline(monkeypatch, "read", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "read", _fake_read_eval(tool_acc=0.85))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="read")).exit_code == PASS


def test_read_fabricated_param_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: tham số bịa = trả dữ liệu bản ghi khác, user tin sai
    base = tmp_path / "b.json"
    base.write_text('{"set":"read","n":20,"tool_acc":0.85}', encoding="utf-8")
    _patch_baseline(monkeypatch, "read", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "read",
                        _fake_read_eval(tool_acc=1.0, fabricated_param=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="read")).exit_code == GATE_FAIL


def _fake_synthesis_eval(grounded_acc=1.0, false_answer=0, n=10):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "synthesis", "n": n, "grounded_acc": grounded_acc,
                "false_answer": false_answer, "false_insufficient": 0,
                "lat_p50": 2000, "lat_p95": 3000, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_synthesis_gate_passes_at_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"synthesis","n":10,"grounded_acc":0.7}', encoding="utf-8")
    _patch_baseline(monkeypatch, "synthesis", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "synthesis",
                        _fake_synthesis_eval(grounded_acc=0.7))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="synthesis")).exit_code == PASS


def test_synthesis_false_answer_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: bịa nội dung tài liệu tệ hơn nói "không biết"
    base = tmp_path / "b.json"
    base.write_text('{"set":"synthesis","n":10,"grounded_acc":0.7}', encoding="utf-8")
    _patch_baseline(monkeypatch, "synthesis", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "synthesis",
                        _fake_synthesis_eval(grounded_acc=1.0, false_answer=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="synthesis")).exit_code == GATE_FAIL


def _fake_ms_eval(coverage=1.0, citation_validity=1.0, fabricated_number=0, n=8):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "multi_source", "n": n,
                "both_source_coverage": coverage,
                "citation_validity": citation_validity,
                "fabricated_number": fabricated_number,
                "lat_p50": 3000, "lat_p95": 4500, "fails": [], "errors": []}
    fn.calls = []
    return fn


def _ms_base(tmp_path, coverage=0.75):
    p = tmp_path / "b.json"
    p.write_text('{"set":"multi_source","n":8,"both_source_coverage":%s}' % coverage,
                 encoding="utf-8")
    return p


def _fake_multi_source_gather_eval(coverage=1.0, citation_validity=1.0,
                                   fabricated_number=0, n=8):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "multi_source_gather", "n": n,
                "both_source_coverage": coverage,
                "citation_validity": citation_validity,
                "fabricated_number": fabricated_number,
                "lat_p50": 3000, "lat_p95": 4500, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_multi_source_gate_passes_at_baseline(monkeypatch, tmp_path):
    _patch_baseline(monkeypatch, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source", _fake_ms_eval(coverage=0.75))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == PASS


def test_multi_source_invalid_citation_fails(monkeypatch, tmp_path):
    # gate CỨNG: trích dẫn không map được = mất tính kiểm chứng
    _patch_baseline(monkeypatch, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source",
                        _fake_ms_eval(coverage=1.0, citation_validity=0.9))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == GATE_FAIL


def test_multi_source_fabricated_number_fails(monkeypatch, tmp_path):
    # gate CỨNG: bịa số = user ra quyết định trên số sai
    _patch_baseline(monkeypatch, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source",
                        _fake_ms_eval(coverage=1.0, fabricated_number=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == GATE_FAIL


# ── --role ────────────────────────────────────────────────────────────────

def test_add_args_co_role_mac_dinh_admin():
    import argparse
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args([]).role == "admin"


def test_role_choices_suy_tu_roles_khong_viet_tay():
    """Thêm một vai vào roles.py mà quên thêm vào choices ⇒ không đo được vai
    đó, và không ai biết. Suy ra thay vì khai tay."""
    import argparse
    from jobs import eval_gate
    from src.agents import roles
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    act = [a for a in p._actions if a.dest == "role"][0]
    assert set(act.choices) == set(roles.load_profile())


def test_bo_co_baseline_khong_doi():
    """Thêm/bớt baseline cho một bộ là ĐỔI NGỮ NGHĨA CỔNG, không phải sửa lỗi —
    bài test này tồn tại để việc đó không xảy ra lặng lẽ.

    `chitchat` vẫn tuyệt đối (`violations == 0`): nó đo vi phạm, không đo chất
    lượng, nên "so với hôm qua" vô nghĩa.

    `sop_select` ĐÃ ĐỔI 2026-08-17, có chủ đích: cổng tuyệt đối cũ (acc == 1.0)
    đỏ vĩnh viễn từ 2026-07-31 nên bị gỡ khỏi `--set all`, tức nó gác đúng bằng
    KHÔNG suốt 6 tuần. Nay theo khuôn 4 cổng anh em — `hijack` giữ tuyệt đối
    (thuộc tính an toàn), `acc` so baseline (chất lượng)."""
    from jobs import eval_gate
    assert "chitchat" not in eval_gate.BASELINE_SETS
    assert "sop_select" in eval_gate.BASELINE_SETS
    assert eval_gate.BASELINE_SETS == frozenset(
        {"intent", "confirm", "planner", "read", "synthesis", "multi_source",
         "sop_select"})


def test_duong_dan_baseline_theo_vai():
    import os
    from evals import run_eval
    from jobs import eval_gate
    assert os.path.basename(eval_gate._baseline_for("intent", "qwen3-8b", "admin")) \
        == "baseline-qwen3-8b-intent.json"
    assert os.path.basename(
        eval_gate._baseline_for("intent", "qwen3-8b", "accounting")) \
        == "baseline-qwen3-8b-intent-accounting.json"
    assert eval_gate._baseline_for("chitchat", "qwen3-8b", "admin") is None


# ── --baseline-model: model của BỘ BASELINE, tách khỏi model đang đo ────────

def test_baseline_model_mac_dinh_giu_nguyen_hanh_vi_hom_nay():
    """Job chạy không cờ phải hoạt động y hệt trước đợt này — đó là điều kiện
    để 6 file baseline hiện có còn dùng được."""
    import argparse
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args([]).baseline_model == eval_gate.BASELINE_MODEL


def test_truyen_baseline_model_thi_doi_duong_dan():
    """Không có cờ này thì baseline của một vai MỚI (đo hôm nay, mang tên model
    hôm nay) sẽ không bao giờ được cổng tìm thấy."""
    import argparse
    import os
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--baseline-model", "gemini-3.1-flash-lite"])
    got = eval_gate._baseline_for("intent", args.baseline_model, "accounting")
    assert os.path.basename(got) == \
        "baseline-gemini-3.1-flash-lite-intent-accounting.json"


def test_duong_cong_doc_va_duong_save_hoi_tu_khi_cung_model():
    """Bất biến vừa hở: với CÙNG (model, set, role), đường dẫn cổng ĐỌC phải
    trùng đường dẫn `run_eval --save-baseline` GHI. Lệch là ship một đường chấm
    cổng hỏng câm — cổng đi tìm một file mà không ai từng ghi ra."""
    from evals import run_eval
    from jobs import eval_gate
    for role in ("admin", "accounting", "warehouse"):
        for model in ("qwen3-8b", "gemini-3.1-flash-lite"):
            doc = eval_gate._baseline_for("intent", model, role)
            ghi = run_eval.baseline_path(model, "intent", role)
            assert doc == ghi, (role, model)


def test_run_thuc_su_doc_co_baseline_model(monkeypatch, tmp_path):
    """Ba test trên đo `add_args` và `_baseline_for` — KHÔNG cái nào đo chỗ
    `run` thật sự đọc `args.baseline_model`. Hoàn nguyên `run` về hằng cứng
    thì cả ba vẫn xanh, tức dây nối không ai canh. Test này canh đúng dây đó.
    """
    _patch(monkeypatch)
    thay = []
    orig = eval_gate._baseline_for

    def ghi_lai(name, model, role):
        thay.append(model)
        return orig(name, model, role)

    monkeypatch.setattr(eval_gate, "_baseline_for", ghi_lai)
    eval_gate.run(_args(set_="intent", baseline_model="qwen3-8b"))
    assert thay == ["qwen3-8b"]

    thay.clear()
    eval_gate.run(_args(set_="intent", baseline_model="mot-model-khac"))
    assert thay == ["mot-model-khac"], (
        "run bỏ qua args.baseline_model — cổng sẽ luôn đọc neo cố định và "
        "không bao giờ tìm thấy baseline của một vai mới")


def test_run_truyen_role_xuong_dung_bo_nhay_vai(monkeypatch):
    """Dây --role: `run` phải truyền `role` xuống BA bộ nhạy vai và KHÔNG
    truyền xuống bộ khác.

    Trước test này, gỡ hẳn hai dòng `if set_name in ROLE_SENSITIVE_SETS:
    kwargs["role"] = args.role` khỏi run() thì toàn bộ suite VẪN XANH — và cả
    ba bộ nhạy vai lặng lẽ đo cấu hình admin, đúng thất bại mà cả đợt này tồn
    tại để chặn (final review I4)."""
    fi, fc = _patch(monkeypatch)
    # Vai kế toán CHƯA có file baseline (nó được tạo ở bước đo bằng LLM thật),
    # nên phải giả một cái — nếu không `run` ném FileNotFoundError TRƯỚC khi
    # gọi hàm đo và test đo nhầm chuyện khác.
    _patch_baseline(monkeypatch, "intent",
                    run_eval.baseline_path("qwen3-8b", "intent", "admin"))
    eval_gate.run(_args(role="accounting"))
    assert fi.calls[0]["kw"] == {"role": "accounting"}, "intent phải nhận role"
    assert "role" not in fc.calls[0]["kw"], "confirm KHÔNG nhạy vai, không được nhận role"


def test_bo_khong_nhay_vai_doc_baseline_CUA_ADMIN(monkeypatch):
    """`confirm/read/synthesis/multi_source` không nhận `role`, nên đo chúng ở
    vai kế toán cho kết quả y hệt admin — một file `…-confirm-accounting.json`
    sẽ KHÔNG AI TỪNG GHI ra.

    Không chuẩn hoá thì `--set both` (MẶC ĐỊNH của job) với bất kỳ vai
    non-admin nào là hỏng vĩnh viễn: cổng đi tìm file không tồn tại →
    INFRA_ERROR (final review I1)."""
    import os
    for s in ("confirm", "read", "synthesis", "multi_source"):
        p = eval_gate._baseline_for(s, "qwen3-8b", "accounting")
        assert os.path.basename(p) == f"baseline-qwen3-8b-{s}.json", s
        assert os.path.exists(p), f"{s}: cổng trỏ vào file không tồn tại"
    # đối chứng: bộ NHẠY vai vẫn có hậu tố
    assert eval_gate._baseline_for("intent", "qwen3-8b", "accounting").endswith(
        "baseline-qwen3-8b-intent-accounting.json")


def test_sop_select_ghi_lai_depth_acc(monkeypatch):
    """`depth_acc` là thứ DUY NHẤT phân biệt "trượt MIỀN" với "trượt ĐỘ SÂU".

    Trước bài test này nó bị rơi khỏi entry: `run_eval.eval_sop_select` tính ra
    nhưng `eval_gate` chép sang entry bằng một danh sách khoá viết tay không có
    nó, nên job đêm chỉ thấy `acc` tụt mà không biết tụt vì cái gì — và KHÔNG
    test nào canh, tức gỡ hẳn dòng tính `depth_acc` trong run_eval vẫn xanh
    (đúng lớp lỗi "danh sách khai báo thiếu âm thầm" đã tái phát nhiều lần)."""
    async def fn(llm, pace=0.0, checkpoint_path=None, **kw):
        return {"set": "sop_select", "n": 24, "acc": 1.0, "depth_acc": 0.875,
                "hijack": 0, "lat_p50": 1, "lat_p95": 2,
                "fails": [], "errors": []}
    monkeypatch.setitem(eval_gate.EVAL_FN, "sop_select", fn)
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="sop_select"))
    assert result.detail["sop_select"]["depth_acc"] == 0.875


def _fake_sop(acc=1.0, depth_acc=1.0, hijack=0):
    async def fn(llm, pace=0.0, checkpoint_path=None, **kw):
        return {"set": "sop_select", "n": 27, "acc": acc,
                "depth_acc": depth_acc, "hijack": hijack,
                "lat_p50": 1, "lat_p95": 2, "fails": [], "errors": []}
    return fn


def _run_sop(monkeypatch, tmp_path, *, acc, base_acc=0.9259, hijack=0):
    import json
    p = tmp_path / "base.json"
    p.write_text(json.dumps({"acc": base_acc}), encoding="utf-8")
    _patch_baseline(monkeypatch, "sop_select", p)
    monkeypatch.setitem(eval_gate.EVAL_FN, "sop_select",
                        _fake_sop(acc=acc, hijack=hijack))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    return eval_gate.run(_args(set_="sop_select"))


def test_sop_select_gate_theo_khuon_chung(monkeypatch, tmp_path):
    """sop_select về đúng khuôn của 4 cổng anh em (planner/read/synthesis/
    multi_source): điều kiện AN TOÀN tuyệt đối + chất lượng so baseline.

    Trước đây nó đòi `acc == 1.0`, và hệ quả đo được là cổng đỏ VĨNH VIỄN từ
    2026-07-31 nên bị gỡ khỏi `--set all` — tức hàng rào an toàn định tuyến
    KHÔNG được job nào gác suốt 6 tuần. `hijack` vẫn tuyệt đối: đó mới là
    hướng đã gây sự cố thật (live-verify 2026-07-16)."""
    assert _run_sop(monkeypatch, tmp_path, acc=0.9259).exit_code == PASS
    assert _run_sop(monkeypatch, tmp_path, acc=1.0).exit_code == PASS
    # tụt dưới baseline vẫn TRƯỢT — baseline-relative không có nghĩa là buông
    assert _run_sop(monkeypatch, tmp_path, acc=0.88).exit_code == GATE_FAIL
    # hijack khác 0 trượt DÙ chất lượng đạt
    assert _run_sop(monkeypatch, tmp_path, acc=1.0, hijack=1).exit_code == GATE_FAIL


def test_sop_select_van_ghi_hijack_va_depth_acc_khi_co_baseline(monkeypatch, tmp_path):
    """Nhánh báo cáo CÓ baseline dùng một danh sách khoá viết tay khác hẳn
    nhánh không-baseline. Chuyển sop_select sang nhánh đó mà quên hai khoá này
    là tái lập ĐÚNG lỗi vừa vá ở b4c8d12 (depth_acc rơi khỏi entry), lần này
    thêm cả `hijack` — con số an toàn được trích trong mọi báo cáo."""
    r = _run_sop(monkeypatch, tmp_path, acc=0.9259)
    e = r.detail["sop_select"]
    assert e["depth_acc"] == 1.0
    assert e["hijack"] == 0
    assert e["baseline_acc"] == 0.9259
