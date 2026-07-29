"""models.py sau khi thành mặt tiền — chỉ còn hai thứ.

Test không chạm mạng: build_router() bị thay bằng router dùng sổ trong bộ nhớ.
"""
import pytest

from src.agents import models
from src.llm.budget import BudgetLedger
from src.llm.catalog import ROLES
from src.llm.router import Router, RoutedChatModel
from src.llm.store import InMemoryUsageStore


@pytest.fixture
def router_gia(monkeypatch):
    """Thay build_router() để không cần Postgres."""
    r = Router(BudgetLedger(InMemoryUsageStore()))
    monkeypatch.setattr(models, "build_router", lambda: r)
    return r


def test_make_llms_khong_tham_so_va_du_moi_vai(router_gia):
    """Hợp đồng CŨ của erp_agent.py: make_llms() gọi không tham số."""
    llms = models.make_llms()
    assert set(llms) == set(ROLES)
    assert all(isinstance(v, RoutedChatModel) for v in llms.values())


def test_llms_from_single_van_con_cho_test_cu():
    """graph.py chuẩn hoá về mapping qua hàm này — hợp đồng cũ phải giữ."""
    mock = object()
    got = models.llms_from_single(mock)
    assert set(got) == set(ROLES)
    assert all(v is mock for v in got.values())


@pytest.mark.parametrize("da_bo", [
    "CLOUD_ALLOWED", "LITELLM_URL", "LITELLM_KEY", "default_model",
    "is_qwen", "model_for", "make_llm",
])
def test_moi_thu_gan_voi_litellm_va_qwen_da_bi_xoa(da_bo):
    """Bảy thứ này thuộc kiến trúc cũ. Còn sót lại là còn đường quay về nó."""
    assert not hasattr(models, da_bo), f"{da_bo} lẽ ra đã bị xoá"


def test_co_khoi_binh_luan_supersession_QD_M2():
    """Spec Phụ lục B: quyết định nào phiên sau không được lật lại thì phải có
    bình luận trong file tracked, ngay tại điểm code nó chi phối."""
    import pathlib
    src = pathlib.Path(models.__file__).read_text(encoding="utf-8")
    assert "M2" in src, "thiếu tham chiếu QĐ M2"
    assert "ADR-009" in src, "thiếu tham chiếu ADR-009"
    assert "ADR-011" in src, "thiếu trỏ tới ADR-011 (lý do đầy đủ)"
