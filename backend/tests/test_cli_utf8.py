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
import json
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


@pytest.mark.parametrize("module", ["src.rag.ingest", "src.erp_query.sync_index",
                                     "evals.compare_visibility"])
def test_cua_vao_khac_import_duoc_va_khong_vo(module):
    """Chỉ import + gọi use_utf8_streams, KHÔNG chạy việc thật (cần DB/Odoo).

    LƯU Ý về `evals.compare_visibility`: ca này chỉ chứng minh import module
    không vỡ dưới cp1252 và use_utf8_streams() gọi tay vẫn hoạt động — nó
    KHÔNG gọi main() của module nên không tự phát hiện được nếu main() quên
    gọi use_utf8_streams() (đúng lỗi task-8 review round 1 tìm ra). Vì module
    này không cần DB/Odoo (không như hai module kia), phép kiểm THẬT sự cho
    lỗi main() nằm ở test_compare_visibility_cli_song_qua_cp1252 dưới đây —
    chạy `-m evals.compare_visibility` thật, không mock."""
    r = _chay(["-c",
               f"import {module}; "
               "from src.cli_console import use_utf8_streams; "
               "use_utf8_streams(); print('tiếng Việt có dấu')"])
    assert r.returncode == 0, r.stderr[-400:]
    assert b"UnicodeEncodeError" not in r.stderr


def test_compare_visibility_cli_song_qua_cp1252(tmp_path):
    """CLI THẬT của `evals.compare_visibility` phải sống dưới cp1252 ở CẢ hai
    nhánh: cổng ĐẠT (chỉ in banner PASS) và cổng THẤT BẠI (in json.dumps() có
    câu hỏi tiếng Việt trong commercial_leaked, RỒI mới in banner FAIL).

    Đây là ca mà test import-suông ở trên KHÔNG bắt được: main() của module
    này (đến review round 1) không gọi use_utf8_streams() nên bản thân lệnh
    in banner (luôn chạy, dù đạt hay thất bại) ném UnicodeEncodeError — cổng
    ĐẠT chết thành exit 1, và cổng THẤT BẠI mất luôn câu hỏi chẩn đoán trước
    khi in được dòng nào (spec: json.dumps in trước banner).

    Dùng RETRIEVAL_CASES và DOC_VISIBILITY THẬT (không mock) để dựng đủ bộ
    ca — main() không có tham số --cases, luôn so trên bộ đầy đủ; đây vẫn là
    test đơn vị (không DB, không Odoo, không LLM, không mạng)."""
    from evals.retrieval_cases import RETRIEVAL_CASES
    from src.rag.visibility import DOC_VISIBILITY, basename

    def _kind(expected):
        kinds = {basename(doc) in DOC_VISIBILITY for doc, _section in expected}
        return None if len(kinds) == 2 else kinds.pop()

    commercial_questions = {q for q, expected, _difficulty in RETRIEVAL_CASES
                            if _kind(expected) is True}
    assert commercial_questions, "cần >=1 ca thương mại thật để test có ý nghĩa"

    def _full_case_json(overrides):
        return {"per_case": [
            {"question": q, "recall_at_pool": overrides.get(q, 1.0),
             "recall_at_final": overrides.get(q, 1.0),
             "reciprocal_rank": overrides.get(q, 1.0),
             "hidden": overrides.get(q, 1.0) == 0.0 and q in commercial_questions}
            for q, _expected, _difficulty in RETRIEVAL_CASES]}

    admin_path = tmp_path / "admin.json"
    dat_path = tmp_path / "dat.json"
    that_bai_path = tmp_path / "that_bai.json"
    admin_path.write_text(
        json.dumps(_full_case_json({}), ensure_ascii=False), encoding="utf-8")
    dat_path.write_text(
        json.dumps(_full_case_json({q: 0.0 for q in commercial_questions}),
                   ensure_ascii=False), encoding="utf-8")
    # y hệt admin (bộ lọc coi như không tồn tại) -> mọi ca thương mại lộ hết
    that_bai_path.write_text(
        json.dumps(_full_case_json({}), ensure_ascii=False), encoding="utf-8")

    r_dat = _chay(["-m", "evals.compare_visibility", str(admin_path), str(dat_path)])
    dump_dat = r_dat.stdout + r_dat.stderr
    assert b"UnicodeEncodeError" not in dump_dat, dump_dat[-500:]
    assert r_dat.returncode == 0, dump_dat[-500:]
    assert "CỔNG ÂM PASS".encode("utf-8") in r_dat.stdout, r_dat.stdout[-500:]

    r_fail = _chay(["-m", "evals.compare_visibility", str(admin_path), str(that_bai_path)])
    dump_fail = r_fail.stdout + r_fail.stderr
    assert b"UnicodeEncodeError" not in dump_fail, dump_fail[-500:]
    assert r_fail.returncode == 1, dump_fail[-500:]
    assert "CỔNG ÂM FAIL".encode("utf-8") in r_fail.stdout, r_fail.stdout[-500:]
    # câu hỏi thương mại tiếng Việt trong commercial_leaked phải IN RA ĐƯỢC —
    # đây chính là chẩn đoán mà review round 1 nói "mất trước khi in".
    assert any(q.encode("utf-8") in r_fail.stdout for q in commercial_questions), \
        r_fail.stdout[-800:]
