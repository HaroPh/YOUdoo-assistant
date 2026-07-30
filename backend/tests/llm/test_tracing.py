# backend/tests/llm/test_tracing.py
"""tracing.py: get_handler()/annotate_current_span() — không đường nào
được phép ném exception ra ngoài (bất biến toàn module)."""
import pytest
from langchain_core.messages import AIMessage

from src.llm import tracing
from src.llm.budget import Verdict
from src.llm.catalog import spec_for
from src.llm.router import InvokeResult, RouteDecision, SkippedLink


def test_get_handler_khong_throw_khi_construct_loi(monkeypatch):
    def _no(*a, **k):
        raise RuntimeError("lỗi giả lập construct CallbackHandler")
    monkeypatch.setattr(tracing, "_warned_once", False)
    monkeypatch.setattr(tracing, "CallbackHandler", _no)
    assert tracing.get_handler() is None


def test_get_handler_khong_throw_khi_thieu_bien_moi_truong(monkeypatch):
    """Không set LANGFUSE_PUBLIC_KEY/SECRET_KEY — SDK tự no-op nội bộ, KHÔNG
    ném exception ở construct. Không assert giá trị trả về cụ thể (phụ thuộc
    hành vi nội bộ SDK, không phải hợp đồng của get_handler()) — chỉ assert
    tính an toàn: gọi được, không throw."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tracing, "_warned_once", False)
    tracing.get_handler()  # không throw là đủ


def _fake_decision_and_result():
    decision = RouteDecision(
        role="router", spec=spec_for("gemma-4-26b"), fallback_depth=1,
        skipped=(SkippedLink("groq-gpt-oss-20b", Verdict.COOLDOWN),),
        base_tokens=123)
    result = InvokeResult(
        message=AIMessage(content="ok"), decision=decision,
        prompt_tokens=10, completion_tokens=20, total_tokens=30, attempts=())
    return decision, result


def test_annotate_current_span_khong_throw_khi_khong_co_span_dang_mo():
    """Gọi trực tiếp, không qua CallbackHandler nào — không có span Langfuse
    nào đang mở. Phải không throw."""
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)  # không throw là đủ


def test_annotate_current_span_gan_dung_field(monkeypatch):
    captured = {}

    class _FakeSpanClient:
        def update_current_span(self, *, metadata):
            captured.update(metadata)

    monkeypatch.setattr(tracing, "get_client", lambda: _FakeSpanClient())
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)

    assert captured["role"] == "router"
    assert captured["alias"] == "gemma-4-26b"
    assert captured["provider"] == "google"
    assert captured["upstream"] == "google"
    assert captured["fallback_depth"] == 1
    assert captured["budget_verdict"] == [("groq-gpt-oss-20b", "cooldown")]
    assert captured["est_tokens"] == 123
    assert captured["actual_tokens"] == 30


def test_annotate_current_span_khong_throw_khi_get_client_loi(monkeypatch):
    def _no():
        raise RuntimeError("lỗi giả lập get_client")
    monkeypatch.setattr(tracing, "get_client", _no)
    decision, result = _fake_decision_and_result()
    tracing.annotate_current_span(decision, result)  # không throw là đủ
