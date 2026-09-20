"""Vai nào thấy lớp nào (spec 2026-09-20 §2.1, §3) — cả hai profile."""
import pytest

from src.agents import roles
from src.rag.visibility import DEFAULT_VISIBILITY, UNRESTRICTED, VISIBILITY_CLASSES

SEES_COMMERCIAL = frozenset({"all", "commercial"})


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_bon_vai_dung_lop(profile):
    p = roles.PROFILES[profile]
    assert p["admin"].rag_visibility is UNRESTRICTED
    assert p["accounting"].rag_visibility == SEES_COMMERCIAL
    assert p["sales"].rag_visibility == SEES_COMMERCIAL
    assert p["warehouse"].rag_visibility == DEFAULT_VISIBILITY


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_unrestricted_keo_theo_khong_loc(profile):
    """Hai cờ cho admin phải nhất quán: unrestricted=True ⇒ không lọc RAG."""
    for cfg in roles.PROFILES[profile].values():
        if cfg.unrestricted:
            assert cfg.rag_visibility is UNRESTRICTED, cfg.name


def test_mac_dinh_thay_it_nhat():
    """Hồ sơ nào quên khai rag_visibility thì THẤY ÍT NHẤT, không phải tất cả."""
    cfg = roles.RoleCfg("x", "X", "http://localhost:1/sse")
    assert cfg.rag_visibility == DEFAULT_VISIBILITY


def test_rag_visibility_of_none_tra_none():
    """None để retrieve() tự fail-closed — không lặp lại luật ở caller."""
    assert roles.rag_visibility_of(None) is None
    admin = roles.PROFILES["small-business"]["admin"]
    assert roles.rag_visibility_of(admin) is UNRESTRICTED


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_moi_lop_khai_trong_role_thuoc_visibility_classes(profile):
    """`roles.py` có `_SEES_COMMERCIAL` — một bản khai lớp ĐỘC LẬP, không đối
    chiếu với `VISIBILITY_CLASSES` (nguồn thật ở src/rag/visibility.py). Một
    lỗi gõ như 'comercial' vẫn fail-closed (lớp lạ không khớp gì trong SQL
    ANY(%s)) nhưng ÂM THẦM làm vai kế toán/bán hàng MẤT tài liệu thương mại,
    không có test nào bắt được. Kiểm mọi lớp mà mỗi vai (trừ UNRESTRICTED)
    khai ra đều nằm trong VISIBILITY_CLASSES."""
    for cfg in roles.PROFILES[profile].values():
        if cfg.rag_visibility is UNRESTRICTED:
            continue
        assert cfg.rag_visibility <= VISIBILITY_CLASSES, (cfg.name, cfg.rag_visibility)
