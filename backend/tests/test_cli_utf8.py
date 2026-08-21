# backend/tests/test_cli_utf8.py
"""Mọi cửa vào CLI phải sống được khi stdout/stderr là cp1252.

VÌ SAO CÓ TEST NÀY, VÀ VÌ SAO NÓ KHÔNG PHẢI CÁI ĐANG BỊ SKIP.

Lớp lỗi: khi output bị chuyển hướng ra tệp (Task Scheduler `>> log 2>&1`),
Windows dùng ANSI codepage thay vì UTF-8, và một thông điệp tiếng Việt có dấu
làm CHÍNH dòng in ném UnicodeEncodeError — nuốt mất chẩn đoán và phá hợp đồng
exit 0/1/2.

Repo ĐÃ CÓ một test gác lớp này: tests/jobs/test_cli.py::
test_cli_survives_redirected_cp1252_stdout. Nhưng nó **skip cứng** vì cần job
`e2e-smoke` chưa được port. Bài học được ghi thành test rồi tắt đi — nên khi lớp
lỗi cắn lần thứ hai (2026-08-21, ở evals/run_eval.py) nó không cứu được ai.

Test này cố ý KHÔNG phụ thuộc job nào: nó chạy các cửa vào có sẵn và chỉ cần
chúng in được tiếng Việt. Nhờ vậy nó chạy ở chế độ mặc định, không chờ C2.
"""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _chay(args: list[str]) -> subprocess.CompletedProcess:
    """Chạy THẬT qua subprocess với cp1252 ép buộc.

    Phải là tiến trình con: reconfigure() tác động lên stream của tiến trình,
    nên gọi trong cùng tiến trình pytest sẽ đo môi trường của pytest chứ không
    đo môi trường CLI thật."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    return subprocess.run([sys.executable, *args], cwd=REPO, env=env,
                          capture_output=True, timeout=120)


def test_bien_chung_lop_loi_van_con_that():
    """Chứng minh cp1252 VẪN làm vỡ một lệnh in tiếng Việt không được che.

    Không có phép thử này thì ba test dưới có thể xanh chỉ vì môi trường CI
    tình cờ là UTF-8, và cả tệp trở thành trang trí."""
    r = _chay(["-c", "print('lỗi tiếng Việt có dấu')"])
    assert r.returncode != 0, "cp1252 không còn gây lỗi — test dưới mất ý nghĩa"
    assert b"UnicodeEncodeError" in r.stderr


def test_jobs_list_song_duoc():
    r = _chay(["-m", "jobs", "list"])
    assert r.returncode == 0, r.stderr[-400:]
    assert b"UnicodeEncodeError" not in r.stderr


def test_run_eval_bao_loi_DOC_DUOC_tren_stderr():
    """Lỗi argparse của run_eval là tiếng Việt và đi ra STDERR — phải ĐỌC ĐƯỢC.

    STDERR KHÔNG vỡ như stdout: Python mặc định cho stderr `errors=
    "backslashreplace"`, nên ký tự ngoài cp1252 thành chuỗi thoát `ỉ` chứ
    không ném. Bản đầu của test này tuyên bố "đường này vẫn vỡ" — SAI, và phép
    thử phá đã bắt được: vô hiệu hoá bản vá mà test vẫn xanh.

    Cái bản vá thật sự mua được ở stderr là ĐỘ ĐỌC ĐƯỢC: có vá thì thông điệp
    ra tiếng Việt thật, không vá thì ra "chỉ d?ng được".
    Với một dòng chẩn đoán thì khác biệt đó là toàn bộ giá trị của nó."""
    # `planner` KHÔNG nằm trong danh sách bộ nhận --memory, nên argparse từ
    # chối NGAY và không chạy lượt gọi LLM nào. Chọn ca này có chủ đích: test
    # phải nhanh và không chạm hạ tầng.
    r = _chay(["-m", "evals.run_eval", "--set", "planner", "--model", "x",
               "--memory", "inert"])
    assert b"UnicodeEncodeError" not in r.stderr, r.stderr[-400:]
    assert r.returncode == 2, "argparse phải thoát 2, không phải 1 trống rỗng"
    # Tiếng Việt THẬT, không phải chuỗi thoát — đây là vế phân biệt được.
    assert "chỉ dùng được".encode("utf-8") in r.stderr, (
        f"thông điệp bị mã hoá thoát, không đọc được: {r.stderr[-200:]!r}")


@pytest.mark.parametrize("module", ["src.rag.ingest", "src.erp_query.sync_index"])
def test_cua_vao_khac_import_duoc_va_khong_vo(module):
    """Chỉ import + gọi use_utf8_streams, KHÔNG chạy việc thật (cần DB/Odoo)."""
    r = _chay(["-c",
               f"import {module}; "
               "from src.cli_console import use_utf8_streams; "
               "use_utf8_streams(); print('tiếng Việt có dấu')"])
    assert r.returncode == 0, r.stderr[-400:]
    assert b"UnicodeEncodeError" not in r.stderr
