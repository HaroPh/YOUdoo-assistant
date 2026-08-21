# backend/tests/jobs/test_e2e_jobs.py
"""4 job `e2e-*` — port 2026-08-21 (nợ SP-1C1 Bước 8).

Cả bốn job chạy thật thì GHI DỮ LIỆU vào Odoo và cần full stack, nên không test
nào ở đây chạy chúng. Thứ test được — và là thứ thật sự dễ hỏng câm — là lớp
khai báo: job có đăng ký không, có bị lên lịch nhầm không, script nó trỏ tới có
tồn tại không, và chấm điểm có suy PASS nhầm từ exit code không.
"""
import importlib
import json

import pytest

import jobs.__main__  # noqa: F401  — kéo theo đăng ký side-effect của mọi job
from jobs import e2e_common
from jobs.registry import GATE_FAIL, INFRA_ERROR, JOBS, PASS

E2E = {ten: job for ten, job in JOBS.items() if ten.startswith("e2e-")}


def test_bon_job_e2e_deu_dang_ky():
    assert set(E2E) == {"e2e-smoke", "e2e-skill-discount",
                        "e2e-skill-delivery", "e2e-skill-warehouse"}


@pytest.mark.parametrize("ten", sorted(E2E))
def test_khong_job_e2e_nao_duoc_len_lich(ten):
    """Bất biến an toàn: mỗi lượt chạy ghi thật vào Odoo. Một job như thế lọt
    vào lịch đêm là ghi dữ liệu thật lúc không ai nhìn."""
    assert E2E[ten].schedulable is False


def test_bang_module_khop_hai_chieu_voi_danh_sach_job():
    """Đối chiếu HAI CHIỀU, không so với danh sách cứng.

    Danh sách cứng trong test sẽ im lặng khi ai đó thêm job thứ năm mà quên —
    lớp lỗi đã tái phát nhiều lần ở repo này (gần nhất: test đăng ký công cụ
    mail chấm trên một danh sách viết tay).
    """
    assert set(e2e_common.E2E_MODULES) == set(E2E)


@pytest.mark.parametrize("module", sorted(set(e2e_common.E2E_MODULES.values())))
def test_script_moi_job_tro_toi_deu_import_duoc(module):
    """Tên module nằm trong chuỗi ký tự nên gõ sai KHÔNG bị Python bắt lúc
    import job — nó chỉ nổ lúc chạy thật, tức lúc stack đã bật và người ta đã
    ngồi chờ. Test này kéo lỗi đó về thời điểm chạy suite."""
    m = importlib.import_module(module)
    assert callable(getattr(m, "main", None)), f"{module} thiếu main()"


# ── chấm điểm ───────────────────────────────────────────────────────────────
def _stdout_co_ket_qua(n: int, passed: int) -> str:
    body = json.dumps({"job": "x", "n": n, "passed": passed, "scenarios": []},
                      ensure_ascii=False)
    return f"loi tao\n=== RESULT_JSON ===\n{body}\n=== END_RESULT_JSON ===\nduoi"


def test_extract_result_json_bat_duoc_khoi_giua_rac():
    got = e2e_common.extract_result_json(_stdout_co_ket_qua(3, 3))
    assert got is not None and got["n"] == 3


def test_extract_result_json_tra_None_khi_khong_co():
    assert e2e_common.extract_result_json("khong co gi o day") is None


def _chay_gia(monkeypatch, stdout: str, returncode: int):
    monkeypatch.setattr(e2e_common, "preflight", lambda: None)

    class _Proc:
        pass

    proc = _Proc()
    proc.stdout, proc.stderr, proc.returncode = stdout, "", returncode
    monkeypatch.setattr(e2e_common.subprocess, "run", lambda *a, **k: proc)
    return e2e_common.run_live_script("job-thu", "tests.live_verify_auto_chain", "ghi chu")


def test_du_lieu_day_du_thi_PASS(monkeypatch):
    r = _chay_gia(monkeypatch, _stdout_co_ket_qua(3, 3), 0)
    assert (r.exit_code, r.verdict) == (PASS, "PASS")


def test_thieu_mot_kich_ban_thi_GATE_FAIL(monkeypatch):
    r = _chay_gia(monkeypatch, _stdout_co_ket_qua(3, 2), 1)
    assert (r.exit_code, r.verdict) == (GATE_FAIL, "FAIL")


def test_KHONG_suy_PASS_tu_exit_code_khi_thieu_RESULT_JSON(monkeypatch):
    """Quyết định có chủ đích, dễ bị "sửa" nhầm thành PASS.

    Script chết trước lúc chấm điểm (import lỗi, stack sập giữa chừng) vẫn có
    thể thoát 0. Suy PASS từ đó là biến một job hỏng thành một job xanh — đúng
    kiểu hỏng im lặng mà cả bốn job này sinh ra để bắt.
    """
    r = _chay_gia(monkeypatch, "script chet som, khong in gi", 0)
    assert (r.exit_code, r.verdict) == (INFRA_ERROR, "ERROR")
    assert "RESULT_JSON" in r.detail["error"]


def test_preflight_doc_cong_tu_moi_truong(monkeypatch):
    """Ghi cứng cổng ở job trong khi helper đọc env = job báo "backend không
    chạy" trong khi script con gọi đúng chỗ. Chẩn đoán sai còn tệ hơn không có."""
    monkeypatch.setenv("BACKEND_PORT", "59999")   # chắc chắn không ai nghe
    err = e2e_common.preflight()
    assert err is not None and "59999" in err
