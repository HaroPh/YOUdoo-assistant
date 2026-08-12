"""Hợp đồng output của scripts/export_role_templates.py — final review round 1
(2026-08-12) tìm thấy 2 lỗi thật ở đây mà bộ test gốc của Task 3 không chạm
tới: None/frozenset-rỗng bị export.py gộp làm một (leo thang đặc quyền im
lặng), và nhiều template bị nối bằng newline THẬT phá vỡ hợp đồng "1 dòng
KEY=value" mà Task 5 dựa vào.

HAI KIỂU GỌI khác nhau trong file này, có chủ đích:
  - admin / vai có ĐÚNG MỘT coordinator mail (warehouse, accounting của
    profile small-business) là VAI THẬT trong roles.PROFILES → gọi qua
    subprocess, kiểm stdout THẬT của script (không chỉ hàm nội bộ).
  - Vai có ≥2 coordinator mail và vai có 0 coordinator mail KHÔNG tồn tại
    trong roles.PROFILES thật (không được phép thêm vai giả vào đó — xem
    test_suy_ra_chu_khong_hardcode ở test_templates_for_role.py, cùng
    nguyên tắc) — dựng RoleCfg tự chế rồi gọi thẳng _dong_env(), hàm nội
    bộ dựng từng dòng, cùng cách test_suy_ra_chu_khong_hardcode đã làm với
    templates_for_role."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

import src.agents.mail_write as mw
from src.agents import roles

_SCRIPT = (Path(__file__).resolve().parents[3] / "scripts"
           / "export_role_templates.py")

_spec = importlib.util.spec_from_file_location("export_role_templates", _SCRIPT)
ert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ert)


def _chay_script(ten_vai: str) -> subprocess.CompletedProcess:
    """Gọi script THẬT qua subprocess (cùng interpreter đang chạy pytest),
    profile ép cứng 'small-business' để test không phụ thuộc env ambient.

    Kế thừa TOÀN BỘ os.environ (không thay hẳn bằng dict rỗng): trên Windows,
    thiếu các biến hệ thống (SystemRoot, ...) khiến chính `import asyncio` ở
    tiến trình con lỗi WinError 10106 (winsock provider) TRƯỚC KHI kịp chạy
    logic của script — đo thật khi lần đầu viết test này."""
    env = {**os.environ, "YOUDOO_POLICY_PROFILE": "small-business"}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), ten_vai],
        capture_output=True, text=True, timeout=30, env=env)


def test_admin_export_rong_qua_subprocess():
    ket = _chay_script("admin")
    assert ket.returncode == 0
    assert ket.stdout == "MCP_ALLOWED_TEMPLATES=\nMCP_ALLOWED_MAIL_MODELS=\n"


def test_vai_mot_template_dung_mot_dong_moi_khoa_qua_subprocess():
    ket = _chay_script("warehouse")
    assert ket.returncode == 0
    ky_vong = (f"MCP_ALLOWED_TEMPLATES={mw.DELIVERY_EMAIL_CFG.template_name}\n"
              f"MCP_ALLOWED_MAIL_MODELS={mw.DELIVERY_EMAIL_CFG.res_model}\n")
    assert ket.stdout == ky_vong


def test_vai_hai_template_van_dung_hai_dong_va_escape_newline():
    """RoleCfg tự chế được cấp 2 coordinator mail (RFQ + hóa đơn) — output
    phải vẫn đúng 2 dòng (1 dòng/khoa), newline PHÂN TÁCH GIỮA 2 tên template
    phải là chuỗi '\\n' hai ký tự (escape), không phải newline thật — newline
    thật sẽ đẻ ra dòng thứ 3 không có 'KEY=' và vỡ hợp đồng parse-theo-dòng
    của Task 5."""
    cfg = roles.RoleCfg("thu", "Thử", "http://x",
                        own=frozenset({"send_rfq_email", "send_invoice_email"}))
    tpl = mw.templates_for_role(cfg)
    mod = mw.mail_models_for_role(cfg)
    assert len(tpl) == 2 and len(mod) == 2  # đối chứng: đúng là ca ≥2 template

    dong_tpl = ert._dong_env("MCP_ALLOWED_TEMPLATES", tpl, "thu")
    dong_mod = ert._dong_env("MCP_ALLOWED_MAIL_MODELS", mod, "thu")

    # Mỗi dòng riêng lẻ không chứa newline thật nào — toàn bộ đã escape.
    assert "\n" not in dong_tpl
    assert "\n" not in dong_mod
    # Cách nhau bằng '\n' escape (2 ký tự: backslash + n), không phải rỗng.
    assert "\\n" in dong_tpl
    assert "\\n" in dong_mod

    # Ghép lại như main() thật sự làm (print từng dòng) → đúng 2 dòng nội
    # dung, mỗi dòng có tiền tố KEY= riêng.
    toan_bo = dong_tpl + "\n" + dong_mod
    dong_list = toan_bo.split("\n")
    assert len(dong_list) == 2
    assert dong_list[0].startswith("MCP_ALLOWED_TEMPLATES=")
    assert dong_list[1].startswith("MCP_ALLOWED_MAIL_MODELS=")

    # Unescape lại đúng bằng tên template thật (round-trip đúng ý contract).
    ten_that = dong_tpl.split("=", 1)[1].replace("\\n", "\n").split("\n")
    assert frozenset(ten_that) == tpl


def test_vai_khong_co_coordinator_mail_thi_export_dung_non_zero():
    """RoleCfg tự chế bị giới hạn (own khác rỗng) nhưng KHÔNG có coordinator
    mail nào — templates_for_role trả frozenset RỖNG, KHÁC None (admin).
    _dong_env phải DỪNG HẲN (SystemExit khác 0), không được in chuỗi rỗng —
    chuỗi rỗng sẽ bị hợp đồng 'env rỗng = không giới hạn' hiểu nhầm thành
    admin, cấp quyền VÔ HẠN cho một vai lẽ ra bị cấm tuyệt đối."""
    cfg = roles.RoleCfg("thu", "Thử", "http://x", own=frozenset({"deliver_order"}))
    tpl = mw.templates_for_role(cfg)
    assert tpl == frozenset()  # đối chứng: đúng là ca 0 coordinator mail, không phải None

    with pytest.raises(SystemExit) as exc:
        ert._dong_env("MCP_ALLOWED_TEMPLATES", tpl, "thu")
    # sys.exit(chuỗi) → SystemExit.code là chuỗi thông báo lỗi (không phải
    # 0/None) và tiến trình thật sự thoát mã khác 0 — kiểm cả hai: code phải
    # "có" (truthy, tức khác 0/None/rỗng) VÀ phải là thông báo, không phải
    # số 0 trá hình.
    assert exc.value.code
    assert isinstance(exc.value.code, str)
