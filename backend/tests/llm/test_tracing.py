# backend/tests/llm/test_tracing.py
"""tracing.py: get_handler()/routed_span()/annotate_span() — không đường nào
được phép ném exception ra ngoài (bất biến toàn module)."""
import dataclasses

import pytest
from langchain_core.messages import AIMessage

from src.llm import tracing
from src.llm.budget import Verdict
from src.llm.catalog import spec_for
from src.llm.router import (AttemptError, InvokeResult, RouteDecision,
                            SkippedLink)


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


def test_routed_span_khong_throw_khi_get_client_loi(monkeypatch):
    def _no():
        raise RuntimeError("lỗi giả lập get_client")
    monkeypatch.setattr(tracing, "get_client", _no)
    with tracing.routed_span("router") as span:
        assert span is None  # mở lỗi -> span None, không throw


def test_annotate_span_no_op_khi_span_none():
    decision, result = _fake_decision_and_result()
    tracing.annotate_span(None, decision, result)  # không throw là đủ


def test_annotate_span_khong_throw_khi_update_loi():
    class _FakeSpanLoi:
        def update(self, **kwargs):
            raise RuntimeError("lỗi giả lập update")
    decision, result = _fake_decision_and_result()
    tracing.annotate_span(_FakeSpanLoi(), decision, result)  # không throw là đủ


def test_annotate_span_gan_dung_field_qua_fake_span():
    """Test nhanh, không cần OTel thật — chỉ xác nhận annotate_span() gọi
    span.update(metadata=...) với ĐÚNG field. Test sau (dùng OTel/Langfuse
    THẬT) mới là bài xác nhận cơ chế context thật hoạt động đúng."""
    captured = {}

    class _FakeSpan:
        def update(self, *, metadata):
            captured.update(metadata)

    decision, result = _fake_decision_and_result()
    tracing.annotate_span(_FakeSpan(), decision, result)

    assert captured["role"] == "router"
    assert captured["alias"] == "gemma-4-26b"
    assert captured["provider"] == "google"
    assert captured["upstream"] == "google"
    assert captured["fallback_depth"] == 1
    assert captured["budget_verdict"] == [("groq-gpt-oss-20b", "cooldown")]
    assert captured["est_tokens"] == 123
    assert captured["actual_tokens"] == 30


def test_annotate_span_tach_empty_skip_khoi_budget_verdict():
    """M2: decision.skipped có thể trộn cả phán quyết ngân sách thật
    (rpm/tpm/rpd/cooldown) LẪN mắt xích bị bỏ vì phản hồi rỗng
    (Verdict.EMPTY) — từ khi có nhánh router-empty-response-fallthrough.
    budget_verdict chỉ được giữ cái đầu; ai truy vấn khoá này để đếm cạn hạn
    mức mà đếm luôn cả EMPTY thì đếm dư. EMPTY phải sang khoá riêng
    empty_skips, phân biệt bằng Verdict.EMPTY chứ không so chuỗi."""
    captured = {}

    class _FakeSpan:
        def update(self, *, metadata):
            captured.update(metadata)

    decision = RouteDecision(
        role="router", spec=spec_for("groq-gpt-oss-20b"), fallback_depth=2,
        skipped=(SkippedLink("gemma-4-26b", Verdict.EMPTY),
                 SkippedLink("gemini-3.5-flash-lite", Verdict.COOLDOWN)),
        base_tokens=123)
    result = InvokeResult(
        message=AIMessage(content="ok"), decision=decision,
        prompt_tokens=10, completion_tokens=20, total_tokens=30, attempts=())

    tracing.annotate_span(_FakeSpan(), decision, result)

    assert captured["budget_verdict"] == [("gemini-3.5-flash-lite", "cooldown")]
    assert captured["empty_skips"] == ["gemma-4-26b"]


def test_metadata_mang_chi_phi_that_cua_luot_tut_mat_xich():
    """I2: trước bản sửa, trace chỉ có actual_tokens của lượt ĐƯỢC TRẢ VỀ —
    lượt bị vứt vì phản hồi rỗng đốt token thật (sổ ngân sách đã đếm) nhưng
    vô hình trên Langfuse. Hai khoá để RIÊNG, không cộng sẵn vào
    actual_tokens (bất biến 'không tự tính lại tổng token')."""
    captured = {}

    class _FakeSpan:
        def update(self, *, metadata):
            captured.update(metadata)

    decision = RouteDecision(
        role="router", spec=spec_for("groq-gpt-oss-20b"), fallback_depth=1,
        skipped=(SkippedLink("gemini-3.1-flash-lite", Verdict.EMPTY),),
        base_tokens=123)
    result = InvokeResult(
        message=AIMessage(content="ok"), decision=decision,
        prompt_tokens=10, completion_tokens=20, total_tokens=800,
        attempts=(AttemptError("gemini-3.1-flash-lite", "phản hồi rỗng"),),
        discarded_tokens=2406)

    tracing.annotate_span(_FakeSpan(), decision, result)

    assert captured["actual_tokens"] == 800
    assert captured["discarded_tokens"] == 2406
    assert captured["attempts"] == [("gemini-3.1-flash-lite", "phản hồi rỗng")]


def test_metadata_cat_ngan_loi_nguyen_van_cua_nha_cung_cap():
    """a.error có thể là nguyên văn exception provider — dài, đôi khi kèm
    payload. Trace cần đủ chữ để nhận ra loại lỗi, không cần cả stack."""
    captured = {}

    class _FakeSpan:
        def update(self, *, metadata):
            captured.update(metadata)

    decision, result = _fake_decision_and_result()
    dai = "x" * 500
    result = dataclasses.replace(
        result, attempts=(AttemptError("groq-gpt-oss-20b", dai),))

    tracing.annotate_span(_FakeSpan(), decision, result)

    alias, loi = captured["attempts"][0]
    assert alias == "groq-gpt-oss-20b"
    assert len(loi) == 200


def test_routed_span_gan_dung_span_lam_cha_qua_otel_that(monkeypatch):
    """Bài test QUAN TRỌNG NHẤT của task này: dựng một Langfuse client với
    TracerProvider/InMemorySpanExporter THẬT (opentelemetry-sdk, không cần
    mạng, không cần LANGFUSE_PUBLIC_KEY/SECRET_KEY thật) — xác nhận
    context.attach() THẬT của SDK gắn đúng span do routed_span() dựng, và
    span đó thật sự được export ra với đúng metadata.

    Đây chính xác là loại test mà thiết kế CŨ (hàm gắn metadata cũ dựa trên
    "current span" ambient, mock get_client() hoàn toàn) không có — và vì
    vậy không phát hiện được bug context-propagation đã xác nhận ở
    live-verify 2026-07-30 (xem module docstring tracing.py). KHÔNG mock
    get_client() ở bài test này."""
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # should_export_span=False chặn hẳn network POST thật lúc flush() —
    # InMemorySpanExporter đã bắt được span TRƯỚC khi filter này áp dụng ở
    # tầng export (SimpleSpanProcessor gọi exporter của TA ngay khi span kết
    # thúc, độc lập với export riêng của Langfuse client), nên assertion vẫn
    # đọc đúng attributes. Không có filter này, test này (không đánh dấu
    # `live`, chạy trong mode unit mặc định) sẽ âm thầm gọi mạng thật tới
    # LANGFUSE_HOST/cloud.langfuse.com mỗi lần flush() — chỉ tình cờ fail
    # nhanh (401) ở máy này vì có sẵn 1 Langfuse Docker đang chạy ở
    # localhost:3001; trên CI thiếu .env hoặc mạng bị chặn kiểu drop gói,
    # có thể treo/không đoán trước được.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-0000")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-0000")
    client = Langfuse(public_key="pk-lf-test-0000", secret_key="sk-lf-test-0000",
                      tracer_provider=provider, flush_at=1,
                      should_export_span=lambda span: False)
    monkeypatch.setattr(tracing, "get_client", lambda: client)

    decision, result = _fake_decision_and_result()
    with tracing.routed_span("router") as span:
        assert span is not None
        tracing.annotate_span(span, decision, result)

    client.flush()
    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    span_thoat = finished[0]
    assert span_thoat.name == "route:router"

    # Khoá THẬT đã xác nhận bằng chạy sống (không đoán): Langfuse serialize
    # metadata= thành MỘT khoá attribute riêng cho từng field, tiền tố
    # "langfuse.observation.metadata.<field>" — field nào KHÔNG phải kiểu
    # OTel-attribute nguyên thuỷ (str/int/float/bool) — ở đây budget_verdict,
    # một list các tuple — được SDK tự json.dumps() thành chuỗi.
    attrs = dict(span_thoat.attributes)
    assert attrs["langfuse.observation.metadata.role"] == "router"
    assert attrs["langfuse.observation.metadata.alias"] == "gemma-4-26b"
    assert attrs["langfuse.observation.metadata.provider"] == "google"
    assert attrs["langfuse.observation.metadata.upstream"] == "google"
    assert attrs["langfuse.observation.metadata.fallback_depth"] == 1
    assert attrs["langfuse.observation.metadata.est_tokens"] == 123
    assert attrs["langfuse.observation.metadata.actual_tokens"] == 30

    import json
    budget_verdict = json.loads(
        attrs["langfuse.observation.metadata.budget_verdict"])
    assert budget_verdict == [["groq-gpt-oss-20b", "cooldown"]]
