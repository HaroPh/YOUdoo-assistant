# backend/tests/jobs/test_cli.py
"""CLI runner: list/run, --scheduled enforcement, crash→exit 2, JSON ghi ra."""
import json
import os
import sys

import pytest

from jobs import registry
from jobs.__main__ import main
from jobs.registry import INFRA_ERROR, Job, JobResult, register


def _fake_job(name="fake", exit_code=0, verdict="PASS", schedulable=True,
              fn=None, add_args=None):
    calls = []
    def default_fn(args):
        calls.append(args)
        return JobResult(name, exit_code, verdict, {"ok": True})
    job = Job(name, fn or default_fn, "test job", schedulable=schedulable,
              add_args=add_args)
    register(job)
    return job, calls


def test_list_shows_name_and_schedulable_marker(capsys):
    _fake_job("fake-sched", schedulable=True)
    _fake_job("fake-manual", schedulable=False)
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "fake-sched" in out and "fake-manual" in out
    assert "on-demand only" in out


def test_run_returns_job_exit_code_and_writes_json():
    _fake_job("fake", exit_code=0)
    assert main(["run", "fake"]) == 0
    files = list((registry.LOGS_DIR).glob("fake-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert data["started_at"] != "" and data["duration_s"] >= 0


def test_run_gate_fail_exit_code_propagates():
    _fake_job("fake", exit_code=1, verdict="FAIL")
    assert main(["run", "fake"]) == 1


def test_scheduled_flag_refuses_on_demand_only_job():
    job, calls = _fake_job("fake-manual", schedulable=False)
    assert main(["run", "fake-manual", "--scheduled"]) == INFRA_ERROR
    assert calls == []          # job fn KHÔNG được gọi


def test_scheduled_flag_allows_schedulable_job():
    job, calls = _fake_job("fake-sched", schedulable=True)
    assert main(["run", "fake-sched", "--scheduled"]) == 0
    assert len(calls) == 1


def test_job_crash_maps_to_infra_error_with_json():
    def boom(args):
        raise RuntimeError("nổ")
    _fake_job("fake-boom", fn=boom)
    assert main(["run", "fake-boom"]) == INFRA_ERROR
    files = list((registry.LOGS_DIR).glob("fake-boom-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["verdict"] == "ERROR" and "nổ" in data["detail"]["error"]


def test_job_specific_args_reach_fn():
    seen = {}
    def fn(args):
        seen["model"] = args.model
        return JobResult("fake-args", 0, "PASS", {})
    def add_args(p):
        p.add_argument("--model", default=None)
    _fake_job("fake-args", fn=fn, add_args=add_args)
    assert main(["run", "fake-args", "--model", "x-model"]) == 0
    assert seen["model"] == "x-model"


def test_cli_survives_redirected_cp1252_stdout():
    """Regression (whole-branch review, Critical): khi stdout bị redirect ra
    file (đúng cách Task Scheduler chạy), Windows dùng ANSI codepage thay vì
    UTF-8 — output tiếng Việt (kể cả "→") từng crash UnicodeEncodeError, mất
    verdict thật và thoát exit 1 (vi phạm exit contract 0/1/2). Chạy CLI THẬT
    qua subprocess với PYTHONIOENCODING=cp1252 ép buộc, dùng job e2e-smoke có
    sẵn với --scheduled (từ chối NGAY trước khi chạm network/subprocess con —
    nhanh, không cần stack sống).

    BẬT LẠI 2026-08-21 sau khi 4 job e2e_* được port (nợ từ SP-1C1 Bước 8). Nó
    skip cứng gần một tháng, và trong thời gian đó lớp lỗi này cắn LẦN THỨ HAI
    ở evals/run_eval.py mà không ai được cảnh báo — xem docstring
    tests/test_cli_utf8.py."""
    import subprocess

    from jobs.registry import INFRA_ERROR as _INFRA_ERROR
    from jobs.registry import REPO_ROOT

    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    # cwd = backend/, KHÔNG phải REPO_ROOT: ở Youdoo gói `jobs` nằm dưới
    # backend/ nên `python -m jobs` chạy từ gốc repo trả "No module named
    # jobs". Bản gốc của test này (D:\Project) dùng REPO_ROOT và không ai
    # phát hiện — nó bị skip cứng từ lúc viết cho tới 2026-08-21.
    proc = subprocess.run(
        [sys.executable, "-m", "jobs", "run", "e2e-smoke", "--scheduled"],
        cwd=REPO_ROOT / "backend", env=env, capture_output=True, text=True,
        # 90s chứ không phải 30s: `python -m jobs` kéo theo `evals.role_config`
        # → `src.agents.erp_agent` → cả `torch` lẫn `google.genai`, và riêng
        # phần import đó tốn ~10s khi bộ nhớ đệm tệp ẤM, **~40s khi NGUỘI**
        # (đo 2026-08-22, ngay sau một lần khởi động lại máy — test này đỏ
        # đúng vì vậy, không phải vì mã hỏng).
        #
        # Đây là nới trần cho một mong manh THẬT, không phải giấu lỗi: nhánh
        # `--scheduled` bị từ chối NGAY, không chạm mạng — nó không cần một
        # dòng nào của torch. Chi phí đó là do import ở cấp module kéo theo.
        # Sửa gốc (import lười cho CLI) là việc riêng, chưa làm.
        encoding="cp1252", timeout=90)
    assert proc.returncode == _INFRA_ERROR
    assert "UnicodeEncodeError" not in proc.stderr
    assert "Traceback" not in proc.stderr
    assert "REFUSED" in proc.stdout
