# backend/jobs/e2e_common.py
"""Khung chung cho 4 job `e2e-*` — bọc một script live-verify thành Job.

VÌ SAO CÓ TỆP NÀY. Bản gốc ở D:\\Project lặp `_preflight` gần như từng chữ
trong bốn tệp job, và `_extract_result_json` trong ba tệp. Port nguyên trạng
là bê nguyên bốn bản sao sang đây, mà chúng KHÔNG bất biến theo thời gian: cổng
backend đã đổi 8000→8002 một lần rồi (spec 2026-08-05), và mỗi lần đổi là bốn
chỗ phải nhớ sửa. Gom về một chỗ là sửa gốc, không phải dọn thẩm mỹ.

BỐN JOB ĐỀU `schedulable=False`, cưỡng chế ở CLI (`--scheduled` bị từ chối):
mỗi lượt chạy GHI DỮ LIỆU THẬT vào Odoo và cần full stack sống (start-dev.ps1),
thứ không chắc có ban đêm.
"""
import json
import os
import re
import socket
import subprocess
import sys
import urllib.request

from jobs.registry import (GATE_FAIL, INFRA_ERROR, PASS, REPO_ROOT, Job,
                           JobResult, register)

# CHẠY JOB PHẢI ĐỨNG Ở backend/. `python -m jobs …` từ gốc repo trả
# "No module named jobs" vì gói `jobs` nằm dưới backend/. Đã cắn hai lần trong
# một ngày: một lần trong test bị skip (cwd=REPO_ROOT, xem tests/jobs/
# test_cli.py) và một lần khi chính tôi gõ lệnh từ gốc repo — lỗi im lặng vì
# nó không giống lỗi cấu hình, chỉ giống "chưa cài".
BACKEND_DIR = REPO_ROOT / "backend"

# job e2e → module script nó bọc. Tồn tại để TEST đối chiếu được hai chiều:
# mọi job `e2e-*` phải có mục ở đây, và mọi module ở đây phải import được. Nếu
# chỉ viết một danh sách cứng trong test thì thêm job thứ năm mà quên cập nhật
# test sẽ không ai biết — lớp lỗi "danh sách khai báo mà không ai gác" đã tái
# phát nhiều lần ở repo này.
E2E_MODULES: dict[str, str] = {}
_RESULT_RE = re.compile(r"=== RESULT_JSON ===\n(.+?)\n=== END_RESULT_JSON ===",
                        re.DOTALL)


def _backend_port() -> str:
    return os.environ.get("BACKEND_PORT", "8002")


def _mcp_port() -> int:
    # Youdoo chạy BA tiến trình mcp-odoo theo vai (8003 admin / 8004 warehouse /
    # 8005 accounting). Chỉ kiểm cái backend thật sự nối tới — kiểm cả ba sẽ
    # bắt job phải chết vì một vai không liên quan tới kịch bản đang chạy.
    return int(os.environ.get("MCP_ODOO_PORT", "8003"))


def preflight() -> str | None:
    """None = stack sẵn sàng; str = lý do không chạy được.

    Đọc cổng từ môi trường chứ không ghi cứng: `live_verify_common` đã đọc
    `BACKEND_PORT`, nên job ghi cứng một cổng khác sẽ báo "backend không chạy"
    trong khi script con lại gọi đúng chỗ — một chẩn đoán sai còn tệ hơn không
    có chẩn đoán.
    """
    port = _backend_port()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                    timeout=3) as r:
            if r.status != 200:
                return f"backend /health trả {r.status}"
    except OSError as e:
        return f"backend :{port} không chạy ({e}) — bật start-dev.ps1 trước"
    mcp = _mcp_port()
    try:
        with socket.create_connection(("127.0.0.1", mcp), timeout=3):
            pass
    except OSError as e:
        return f"MCP :{mcp} không chạy ({e}) — bật start-dev.ps1 trước"
    return None


def extract_result_json(stdout: str) -> dict | None:
    m = _RESULT_RE.search(stdout)
    return json.loads(m.group(1)) if m else None


def run_live_script(job: str, module: str, note: str, timeout_s: int = 900) -> JobResult:
    """Chạy một script live-verify như MODULE, chấm điểm từ RESULT_JSON.

    `-m tests.…` với cwd=backend/ chứ không phải `python tests/….py`: chạy theo
    đường tệp thì sys.path[0] là `backend/tests`, nên `import tests.…` và
    `import src.…` bên trong script đều hỏng. Chạy theo module đặt cwd lên
    sys.path, khớp đúng cách pytest và `python -m jobs` đang chạy.
    """
    err = preflight()
    if err:
        print(f"PREFLIGHT FAIL: {err}")
        return JobResult(job, INFRA_ERROR, "ERROR", {"preflight": err})
    print(f"LƯU Ý: {note}.")
    try:
        proc = subprocess.run([sys.executable, "-m", module], cwd=BACKEND_DIR,
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        return JobResult(job, INFRA_ERROR, "ERROR",
                         {"error": f"timeout sau {e.timeout}s — script con treo",
                          "note": note})

    detail = {"returncode": proc.returncode, "note": note,
              "raw_stdout": proc.stdout[-8000:], "stderr": proc.stderr[-4000:]}
    result_json = extract_result_json(proc.stdout)
    if result_json is None:
        # KHÔNG suy ra PASS từ returncode==0 ở đây: script không phát
        # RESULT_JSON nghĩa là nó chết trước khi chấm điểm (import lỗi, stack
        # sập giữa chừng), và một exit 0 tình cờ sẽ thành PASS giả.
        detail["error"] = "không parse được RESULT_JSON từ stdout script con"
        return JobResult(job, INFRA_ERROR, "ERROR", detail)
    detail["result"] = result_json
    if result_json["passed"] == result_json["n"]:
        return JobResult(job, PASS, "PASS", detail)
    return JobResult(job, GATE_FAIL, "FAIL", detail)


def register_e2e(name: str, module: str, description: str, note: str) -> None:
    """Đăng ký một job e2e. `schedulable=False` KHÔNG phải tham số — bốn job
    này đều ghi thật vào Odoo, và để ai đó bật lịch cho một trong số chúng
    bằng một tham số là để ngỏ đúng cánh cửa cần đóng."""
    def run(args) -> JobResult:
        return run_live_script(name, module, note)

    E2E_MODULES[name] = module
    register(Job(name, run, description, schedulable=False))
