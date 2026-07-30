# backend/tests/jobs/test_eval_gate.py
"""eval-gate: verdict aggregation, resolution model theo config sống, pacing auto."""
import argparse

import pytest

from evals import run_eval
from jobs import eval_gate
from jobs.registry import GATE_FAIL, INFRA_ERROR, PASS


def _args(model=None, set_="both", pace=None):
    return argparse.Namespace(model=model, set=set_, pace=pace)


def _fake_eval(set_name, acc, false_confirm=0, n=40):
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
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
    async def boom(llm, pace=0.0, checkpoint_path=None):
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
    assert result.detail["intent"]["model"] == "gemma-4-26b"
    assert result.detail["confirm"]["model"] == "groq-gpt-oss-20b"


def test_model_override_applies_to_all_sets(monkeypatch):
    _patch(monkeypatch)
    result = eval_gate.run(_args(model="candidate-x"))
    assert result.detail["intent"]["model"] == "candidate-x"
    assert result.detail["confirm"]["model"] == "candidate-x"


def test_nhip_tu_dong_suy_tu_rpm_catalog(monkeypatch):
    """Thay test_pace_auto_cloud_5s_local_0 (bản cũ giả định có model 'local'
    pace=0 — không còn model local nào trong catalog kể từ SP-1). Hành vi
    MỚI: pace luôn = (60/rpm)*1.2, không có nhánh đặc biệt nào."""
    fi, fc = _patch(monkeypatch)
    eval_gate.run(_args())
    # gemma-4-26b (router, dòng đầu) rpm=30 -> (60/30)*1.2 = 2.4
    assert fi.calls[0]["pace"] == pytest.approx(2.4)
    # groq-gpt-oss-20b (evaluator, dòng đầu) rpm=30 -> cùng 2.4
    assert fc.calls[0]["pace"] == pytest.approx(2.4)


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
    # BASELINES không có "chitchat" — nếu code lỡ tra cứu, KeyError sẽ lộ ra
    # thành INFRA_ERROR thay vì PASS. Assert PASS tức là đường code không đọc.
    assert "chitchat" not in eval_gate.BASELINES
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
    assert result.detail["chitchat"]["model"] == "gemma-4-31b"


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
    async def fn(llm, pace=0.0, checkpoint_path=None):
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
    async def fn(llm, pace=0.0, checkpoint_path=None):
        fn.calls.append({"pace": pace, "checkpoint_path": checkpoint_path})
        return {"set": "planner", "n": n, "tool_acc": tool_acc, "args_acc": tool_acc,
                "dangerous_misroute": dangerous_misroute, "parse_fail": 0,
                "lat_p50": 900, "lat_p95": 1500, "fails": [], "errors": []}
    fn.calls = []
    return fn


def test_planner_gate_passes_at_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", _fake_planner_eval(tool_acc=0.8))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == PASS


def test_planner_gate_fails_below_baseline(monkeypatch, tmp_path):
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", _fake_planner_eval(tool_acc=0.7))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == GATE_FAIL


def test_planner_dangerous_misroute_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: ghi sai tool = ghi sai dữ liệu ERP, không nhân nhượng
    base = tmp_path / "b.json"
    base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "planner", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner",
                        _fake_planner_eval(tool_acc=1.0, dangerous_misroute=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    result = eval_gate.run(_args(set_="planner"))
    assert result.exit_code == GATE_FAIL
    assert result.detail["planner"]["gate"] == "FAIL"


def test_set_all_runs_every_registered_set(monkeypatch, tmp_path):
    """--set all phải chạy TẤT CẢ 7 set đã đăng ký, không chỉ 4 set cũ.
    Bẫy thật (2 lần: 1 lần Task 2's fix round, rồi TÁI PHÁT khi Task 3/4/5
    thêm read/synthesis/multi_source mà quên patch vào test này) — nếu 1 set
    không được patch, hàm eval THẬT sẽ chạy, lỗi (thiếu LLM/baseline thật),
    bị run()'s except nuốt mất, và assertion cũ (chỉ check 4 key cố định)
    vẫn qua dù set đó CHƯA BAO GIỜ thực sự chạy thành công. Assert bằng
    set(eval_gate.EVAL_FN) (không phải danh sách cứng) + exit_code + mỗi
    fake gọi đúng 1 lần, để không tái phát lần thứ 3 khi có set #8."""
    fi, fc = _patch(monkeypatch)
    fchat = _fake_chitchat_eval(violations=0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "chitchat", fchat)

    planner_base = tmp_path / "planner.json"
    planner_base.write_text('{"set":"planner","n":24,"tool_acc":0.8}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "planner", planner_base)
    fplanner = _fake_planner_eval(tool_acc=0.8)
    monkeypatch.setitem(eval_gate.EVAL_FN, "planner", fplanner)

    read_base = tmp_path / "read.json"
    read_base.write_text('{"set":"read","n":20,"tool_acc":0.85}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "read", read_base)
    fread = _fake_read_eval(tool_acc=0.85)
    monkeypatch.setitem(eval_gate.EVAL_FN, "read", fread)

    synthesis_base = tmp_path / "synthesis.json"
    synthesis_base.write_text('{"set":"synthesis","n":12,"grounded_acc":1.0}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "synthesis", synthesis_base)
    fsynthesis = _fake_synthesis_eval(grounded_acc=1.0)
    monkeypatch.setitem(eval_gate.EVAL_FN, "synthesis", fsynthesis)

    monkeypatch.setitem(eval_gate.BASELINES, "multi_source", _ms_base(tmp_path, coverage=0.75))
    fms = _fake_ms_eval(coverage=0.75)
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source", fms)

    result = eval_gate.run(_args(set_="all"))

    assert set(result.detail) == set(eval_gate.EVAL_FN)
    assert result.exit_code == PASS
    for fn in (fi, fc, fchat, fplanner, fread, fsynthesis, fms):
        assert len(fn.calls) == 1, f"{fn} was not called exactly once"


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
    monkeypatch.setitem(eval_gate.BASELINES, "read", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "read", _fake_read_eval(tool_acc=0.85))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="read")).exit_code == PASS


def test_read_fabricated_param_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: tham số bịa = trả dữ liệu bản ghi khác, user tin sai
    base = tmp_path / "b.json"
    base.write_text('{"set":"read","n":20,"tool_acc":0.85}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "read", base)
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
    monkeypatch.setitem(eval_gate.BASELINES, "synthesis", base)
    monkeypatch.setitem(eval_gate.EVAL_FN, "synthesis",
                        _fake_synthesis_eval(grounded_acc=0.7))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="synthesis")).exit_code == PASS


def test_synthesis_false_answer_fails_even_with_perfect_acc(monkeypatch, tmp_path):
    # gate CỨNG: bịa nội dung tài liệu tệ hơn nói "không biết"
    base = tmp_path / "b.json"
    base.write_text('{"set":"synthesis","n":10,"grounded_acc":0.7}', encoding="utf-8")
    monkeypatch.setitem(eval_gate.BASELINES, "synthesis", base)
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


def test_multi_source_gate_passes_at_baseline(monkeypatch, tmp_path):
    monkeypatch.setitem(eval_gate.BASELINES, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source", _fake_ms_eval(coverage=0.75))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == PASS


def test_multi_source_invalid_citation_fails(monkeypatch, tmp_path):
    # gate CỨNG: trích dẫn không map được = mất tính kiểm chứng
    monkeypatch.setitem(eval_gate.BASELINES, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source",
                        _fake_ms_eval(coverage=1.0, citation_validity=0.9))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == GATE_FAIL


def test_multi_source_fabricated_number_fails(monkeypatch, tmp_path):
    # gate CỨNG: bịa số = user ra quyết định trên số sai
    monkeypatch.setitem(eval_gate.BASELINES, "multi_source", _ms_base(tmp_path))
    monkeypatch.setitem(eval_gate.EVAL_FN, "multi_source",
                        _fake_ms_eval(coverage=1.0, fabricated_number=1))
    monkeypatch.setattr(run_eval, "_llm", lambda m, role=None: object())
    assert eval_gate.run(_args(set_="multi_source")).exit_code == GATE_FAIL
