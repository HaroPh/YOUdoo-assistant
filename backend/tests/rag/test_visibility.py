"""Vốn từ lớp hiển thị + fail-closed của resolve() (spec 2026-09-20 §3)."""
import pytest

from src.rag import visibility as vis


def test_class_for_tach_ca_hai_dau_phan_cach():
    """rag_documents.source_file đang lưu 'src/rag/seed\\bang_gia.xlsx' (lẫn '/'
    và '\\'); os.path.basename trên Linux (CI) trả 'seed\\bang_gia.xlsx' → nhãn
    'all' lặng lẽ. Cả bốn kiểu đường dẫn phải ra cùng lớp."""
    for path in ("bang_gia.xlsx", "src/rag/seed/bang_gia.xlsx",
                 "src/rag/seed\\bang_gia.xlsx", "D:\\Youdoo\\backend\\src\\rag\\seed\\bang_gia.xlsx"):
        assert vis.class_for(path) == "commercial", path


def test_class_for_bon_tep_thuong_mai_va_tep_la():
    assert {vis.class_for(f) for f in ("discount_policy.docx", "bang_gia.xlsx",
                                       "payment_policy.docx", "sla.docx")} == {"commercial"}
    assert vis.class_for("policy.docx") == "all"
    assert vis.class_for("seed/law/luat-dautu.pdf") == "all"
    assert vis.class_for("khong_ton_tai.txt") == "all"


def test_moi_gia_tri_DOC_VISIBILITY_nam_trong_von_tu():
    assert set(vis.DOC_VISIBILITY.values()) <= vis.VISIBILITY_CLASSES
    assert "all" in vis.VISIBILITY_CLASSES
    assert vis.DEFAULT_VISIBILITY == frozenset({"all"})


@pytest.mark.parametrize("value", [None, frozenset(), set(), [], ()])
def test_resolve_fail_closed_khi_thieu_hoac_rong(value):
    assert vis.resolve(value) == vis.DEFAULT_VISIBILITY


def test_resolve_chi_sentinel_that_moi_mo():
    assert vis.resolve(vis.UNRESTRICTED) is vis.UNRESTRICTED
    # Một _Unrestricted() KHÁC không phải sentinel — so bằng `is`, không phải kiểu
    khac = type(vis.UNRESTRICTED)()
    assert vis.resolve(khac) == vis.DEFAULT_VISIBILITY


def test_resolve_giu_tap_lop_da_cho():
    assert vis.resolve({"all", "commercial"}) == frozenset({"all", "commercial"})
    assert vis.resolve(["all"]) == frozenset({"all"})
