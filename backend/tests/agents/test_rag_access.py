"""Tên phòng ban SUY từ RoleCfg.rag_visibility — không có bảng khai tay để trôi
(spec 2026-09-21 §4). Câu từ chối tất định, có marker để probe bắt được."""
import pytest

from src.agents import rag_access, roles

TM = frozenset({"commercial"})


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_commercial_thuoc_ke_toan_va_ban_hang(profile):
    p = roles.PROFILES[profile]
    assert rag_access.departments_for(TM, p) == ["Kế toán", "Bán hàng"]


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_admin_khong_bao_gio_la_phong_ban(profile):
    """Admin là UNRESTRICTED — không 'được xem lớp' theo nghĩa khai báo, nên
    không xuất hiện trong danh sách chỉ dẫn."""
    p = roles.PROFILES[profile]
    for cls in ("all", "commercial"):
        assert "Quản trị" not in rag_access.departments_for(frozenset({cls}), p)


def test_lop_khong_ai_xem_thi_rong():
    assert rag_access.departments_for(frozenset({"khong-ton-tai"}),
                                      roles.PROFILES["small-business"]) == []


def test_khong_truyen_profile_thi_doc_env(monkeypatch):
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "enterprise")
    assert rag_access.departments_for(TM) == ["Kế toán", "Bán hàng"]


def test_cau_tu_choi_neu_vai_va_phong_ban():
    kho = roles.PROFILES["small-business"]["warehouse"]
    msg = rag_access.denied_message(kho, TM, roles.PROFILES["small-business"])
    assert msg == ("Tài liệu về việc này thuộc phạm vi Kế toán / Bán hàng; "
                   "vai Kho không được xem. Bạn có thể hỏi trực tiếp phòng "
                   "Kế toán hoặc Bán hàng.")
    assert rag_access.DENIED_MARKER in msg
    assert "📄" not in msg and "NGUỒN" not in msg     # không footer trích dẫn


def test_cau_tu_choi_mot_phong_ban():
    kho = roles.PROFILES["small-business"]["warehouse"]
    chi_ke_toan = {"x": roles.RoleCfg("x", "Kế toán", "http://localhost:1/sse",
                                      rag_visibility=frozenset({"all", "commercial"}))}
    msg = rag_access.denied_message(kho, TM, chi_ke_toan)
    assert msg.endswith("hỏi trực tiếp phòng Kế toán.")


def test_cau_tu_choi_khong_phong_ban_khong_no():
    kho = roles.PROFILES["small-business"]["warehouse"]
    msg = rag_access.denied_message(kho, frozenset({"khong-ton-tai"}),
                                    roles.PROFILES["small-business"])
    assert msg == "Vai Kho không được xem tài liệu về việc này."


def test_cau_tu_choi_khong_co_role_cfg():
    """role_cfg=None chỉ xảy ra ở test; vẫn phải ra câu hợp lệ, không AttributeError."""
    msg = rag_access.denied_message(None, TM, roles.PROFILES["small-business"])
    assert "vai hiện tại không được xem" in msg
