# coding: utf-8
"""Unit test cho oracle THUẦN của probe sống 19b (tests/live_verify_rbac_rag.py).

Bổ sung của controller (task-7-brief.md, "lần 2"): oracle mới (marker + footer +
count==1 + endswith) không có cách nào được chứng minh "trượt được" trước khi
Task 8 đốt hạn mức chạy probe thật. File này chứng minh TỪNG điều kiện của
`evaluate_rag`/`evaluate_mixed` có thể ĐỎ riêng rẽ, bằng `ket`/`kho_mixed` TỔNG
HỢP (chuỗi tay) — KHÔNG mạng, KHÔNG DB, KHÔNG marker `live`. Phải chạy được cả
qua launcher (`pytest_env.py`) lẫn KHÔNG launcher (không `DATABASE_URL`) và cho
kết quả GIỐNG NHAU — `evaluate_rag`/`evaluate_mixed` không đọc env, không gọi
mạng (xem docstring của chúng trong live_verify_rbac_rag.py).

Import `tests.live_verify_rbac_rag` đã được xác minh THỦ CÔNG là sạch: kéo theo
`tests.live_verify_common` nhưng module đó tự bọc `load_env()` trong
try/except FileNotFoundError ở import-time, và không mở kết nối mạng/DB nào chỉ
vì được import (nó chỉ định nghĩa BASE_URL từ os.environ.get với giá trị mặc
định). `src.agents.rag_access`/`src.agents.roles` cũng không chạm DB. Test này
tự kiểm lại bất biến đó ở `test_import_khong_can_database_url_hay_env`.
"""
import importlib
import os
import subprocess
import sys

import pytest

from src.agents.rag_access import DENIED_MARKER
from src.agents.roles import PROFILES
from tests.live_verify_rbac_rag import (
    CAU_HOI_MIXED,
    NGUON_MONG_DOI,
    evaluate_mixed,
    evaluate_rag,
    expected_denied_message,
)

PROFILE = PROFILES["small-business"]
KHO_TU_CHOI = expected_denied_message(PROFILE)
# Tính lại độc lập bằng chính hàm nguồn sự thật, để không hai bài test nào
# cùng tin vào MỘT chuỗi hardcode giống nhau mà đều sai giống nhau.
FOOTER_SALES = f"5% cho khách thân thiết. 📄 Nguồn: {NGUON_MONG_DOI}"
FOOTER_ACC = f"5% cho khách thân thiết. 📄 Nguồn: {NGUON_MONG_DOI}"
FOOTER_ADMIN = f"5% cho khách thân thiết, 10% cho đối tác chiến lược. 📄 Nguồn: {NGUON_MONG_DOI}"


def _ket_dung() -> dict:
    """`ket` hoàn toàn đúng — nền cho mọi ca đột biến bên dưới (chỉ đổi ĐÚNG
    một khoá mỗi test, giữ ba khoá kia đúng, để suy luận rõ điều kiện nào bắt
    ca đó)."""
    return {
        "warehouse": KHO_TU_CHOI,
        "sales": FOOTER_SALES,
        "accounting": FOOTER_ACC,
        "admin": FOOTER_ADMIN,
    }


# ── evaluate_rag ─────────────────────────────────────────────────────────────

def test_rag_kho_thieu_marker_thi_fail():
    ket = _ket_dung()
    ket["warehouse"] = "Chính sách chiết khấu của công ty hiện áp dụng theo cấp khách hàng."
    ok, tom_tat = evaluate_rag(ket, KHO_TU_CHOI)
    assert ok is False
    assert "kho từ chối đúng câu tất định: False" in tom_tat


def test_rag_kho_co_marker_nhung_thieu_ten_phong_ban_thi_fail():
    ket = _ket_dung()
    # Cắt "; vai Kho không được xem." trở đi — còn marker (nếu có trong phần
    # bị cắt thì cũng mất luôn) nhưng chắc chắn KHÔNG còn nguyên câu, vì
    # thiếu vế "Bạn có thể hỏi trực tiếp phòng Kế toán hoặc Bán hàng." — tức
    # thiếu tên phòng ban thứ hai so với câu tất định đầy đủ.
    cham = KHO_TU_CHOI.index("Bạn có thể hỏi")
    ket["warehouse"] = KHO_TU_CHOI[:cham] + "Bạn có thể hỏi phòng Kế toán."
    assert DENIED_MARKER in ket["warehouse"]           # vẫn còn marker
    ok, tom_tat = evaluate_rag(ket, KHO_TU_CHOI)
    assert ok is False
    assert "kho từ chối đúng câu tất định: False" in tom_tat


def test_rag_kho_co_footer_lac_de_thi_fail():
    ket = _ket_dung()
    ket["warehouse"] = KHO_TU_CHOI + f" (xem thêm 📄 Nguồn: {NGUON_MONG_DOI})"
    ok, tom_tat = evaluate_rag(ket, KHO_TU_CHOI)
    assert ok is False
    assert "kho không trích lạc đề: False" in tom_tat


def test_rag_vai_duoc_xem_thieu_footer_thi_fail():
    ket = _ket_dung()
    ket["accounting"] = "Chính sách chiết khấu áp dụng 5% cho khách thân thiết."
    ok, tom_tat = evaluate_rag(ket, KHO_TU_CHOI)
    assert ok is False
    assert "'accounting': False" in tom_tat


def test_rag_vai_duoc_xem_bi_tu_choi_oan_thi_fail():
    ket = _ket_dung()
    ket["sales"] = FOOTER_SALES + f" ({DENIED_MARKER} phần phụ lục.)"
    ok, tom_tat = evaluate_rag(ket, KHO_TU_CHOI)
    assert ok is False
    assert "'sales': False" in tom_tat


def test_rag_ket_hoan_toan_dung_thi_pass():
    ok, tom_tat = evaluate_rag(_ket_dung(), KHO_TU_CHOI)
    assert ok is True
    assert "PASS" in tom_tat


# ── evaluate_mixed ───────────────────────────────────────────────────────────

def _mixed_dung() -> str:
    return ("Tồn kho hiện tại của [E-COM07] Large Cabinet là 25 sản phẩm.\n\n"
            + KHO_TU_CHOI)


def test_mixed_marker_lap_lai_hai_lan_thi_fail():
    kho_mixed = ("Tồn kho Large Cabinet là 25 sản phẩm. Vai Kho " + DENIED_MARKER
                + " chính sách chiết khấu.\n\n" + KHO_TU_CHOI)
    assert kho_mixed.count(DENIED_MARKER) == 2
    ok, tom_tat = evaluate_mixed(kho_mixed, KHO_TU_CHOI)
    assert ok is False
    assert "marker đúng 1 lần: False" in tom_tat


def test_mixed_mot_lan_nhung_khong_ket_bang_cau_tat_dinh_thi_fail():
    kho_mixed = _mixed_dung() + " Bạn cần hỏi thêm gì không?"
    assert kho_mixed.count(DENIED_MARKER) == 1
    ok, tom_tat = evaluate_mixed(kho_mixed, KHO_TU_CHOI)
    assert ok is False
    assert "kết bằng câu tất định: False" in tom_tat


def test_mixed_phan_truoc_rong_thi_fail():
    kho_mixed = KHO_TU_CHOI   # không có phần ERP nào đứng trước — bị nuốt
    ok, tom_tat = evaluate_mixed(kho_mixed, KHO_TU_CHOI)
    assert ok is False
    assert "phần ERP trước đó không rỗng: False" in tom_tat


def test_mixed_trich_lac_de_thi_fail():
    kho_mixed = (f"Tồn kho Large Cabinet là 25 sản phẩm (xem thêm 📄 Nguồn: "
                f"{NGUON_MONG_DOI}).\n\n" + KHO_TU_CHOI)
    ok, tom_tat = evaluate_mixed(kho_mixed, KHO_TU_CHOI)
    assert ok is False
    assert "không trích lạc đề: False" in tom_tat


def test_mixed_hoan_toan_dung_thi_pass():
    ok, tom_tat = evaluate_mixed(_mixed_dung(), KHO_TU_CHOI)
    assert ok is True
    assert "PASS" in tom_tat


# ── wiring / import hygiene ──────────────────────────────────────────────────

def test_expected_denied_message_tinh_qua_denied_message_khong_hardcode():
    """`expected_denied_message()` phải THỰC SỰ gọi rag_access.denied_message()
    trên RoleCfg kho lấy từ roles.PROFILES — không phải một chuỗi hardcode
    trùng hợp giống. So sánh với một lệnh gọi ĐỘC LẬP thứ hai."""
    from src.agents.rag_access import denied_message
    doc_lap = denied_message(PROFILE["warehouse"], frozenset({"commercial"}), PROFILE)
    assert expected_denied_message(PROFILE) == doc_lap
    assert DENIED_MARKER in doc_lap


def test_cau_hoi_mixed_khong_rong_va_ket_thuc_bang_dau_hoi():
    """Câu mixed phải là một CÂU HỎI thật (kết bằng '?') — lớp phủ quyết tất
    định `looks_like_question` (routing.py) dựa vào đó để không cho câu này bị
    kéo vào SOP chiết khấu dù router đề cử `sop`."""
    assert CAU_HOI_MIXED.strip().endswith("?")
    assert "chiết khấu" in CAU_HOI_MIXED or "chính sách" in CAU_HOI_MIXED


def test_import_khong_can_database_url_hay_env(monkeypatch):
    """Import module probe KHÔNG được đòi DATABASE_URL/ODOO_*/.env. Chạy trong
    subprocess con SẠCH (không kế thừa env hiện có) để không bị launcher pytest_env.py
    (nếu đang chạy qua nó) che giấu thiếu sót — đúng yêu cầu "chạy cả có lẫn
    không launcher, kết quả giống nhau"."""
    env_sach = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_URL", "ODOO_URL", "ODOO_DB",
                           "ODOO_USERNAME", "ODOO_PASSWORD",
                           "YOUDOO_POLICY_PROFILE")}
    r = subprocess.run(
        [sys.executable, "-c",
         "import tests.live_verify_rbac_rag as m; print('OK', m.CAU_HOI[:5])"],
        cwd=os.path.dirname(os.path.dirname(__file__)) or ".",
        env=env_sach, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "OK" in r.stdout
