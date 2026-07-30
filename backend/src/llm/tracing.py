"""Langfuse tracing — không đường nào để lỗi ở đây làm hỏng một lượt chat.

get_handler(): CallbackHandler của Langfuse, gắn ở tầng LangChain (mỗi node
LangGraph tự thành 1 span lồng nhau khi truyền vào config={"callbacks":[...]}).
Construct lỗi (bug SDK, import hỏng) → trả None, log 1 lần, không throw. SDK
tự nó ĐÃ no-op êm khi thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY (đọc
nguồn: langfuse._client.client.Langfuse.__init__ — thiếu key thì gán
self._otel_tracer = NoOpTracer() rồi return sớm, KHÔNG raise) — get_handler()
không cần tự kiểm tra env, chỉ cần bọc try/except phòng lỗi construct khác.

routed_span()/annotate_span(): gắn thuộc tính định tuyến lên MỘT SPAN RIÊNG
do chính RoutedChatModel dựng (spec §4.2), KHÔNG dựa vào "current span" của
OTel sau khi lệnh gọi model async đã trả về.

Lý do (xác nhận bằng chạy sống 2026-07-30 + đọc mã nguồn cài đặt, không suy
đoán): CallbackHandler của Langfuse gắn span "current" bằng
context.attach() bên trong _attach_observation() — TRONG các hook đồng bộ
on_llm_start/on_llm_end. Khi LangChain dispatch một callback handler không
đồng bộ (mặc định run_inline=False), nó chạy các hook đồng bộ đó qua
loop.run_in_executor(None, functools.partial(copy_context().run, ...)) (xác
nhận trong langchain_core/callbacks/manager.py, _ahandle_event_for_handler)
— tức trong MỘT LUỒNG KHÁC, trên MỘT BẢN SAO context. context.attach() bên
trong bản sao đó không bao giờ lan ngược về coroutine gọi RoutedChatModel —
nên get_client().update_current_span() (thiết kế cũ) luôn thấy "No active
span in current context" trên đường async thật, dù mọi test mock get_client()
đều pass (không test nào chạy qua dispatch async thật của LangChain).

Sửa bằng cách: RoutedChatModel tự dựng span RIÊNG (routed_span), giữ tham
chiếu trực tiếp, gắn metadata thẳng lên đối tượng đó (annotate_span) — không
tra "current" ở đâu cả. Span mới vẫn lồng đúng làm cha của GENERATION gốc vì
context.attach() cho nó chạy TRỰC TIẾP trong coroutine gọi, TRƯỚC khi
copy_context() của CallbackHandler chạy cho dispatch on_chat_model_start —
bản sao đó thấy đúng span cha tại thời điểm sao chép."""
import logging
from contextlib import contextmanager

from langfuse import get_client
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)
_warned_once = False


def get_handler() -> "CallbackHandler | None":
    global _warned_once
    try:
        return CallbackHandler()
    except Exception:
        if not _warned_once:
            logger.warning(
                "Không dựng được Langfuse CallbackHandler — tắt tracing cho "
                "phiên chạy này (không ảnh hưởng lượt chat).", exc_info=True)
            _warned_once = True
        return None


def _metadata(decision, result) -> dict:
    """decision: RouteDecision (router.py). result: InvokeResult (router.py)
    — result.total_tokens là con số có thẩm quyền, KHÔNG cộng
    prompt_tokens+completion_tokens (bất biến toàn dự án)."""
    return {
        "role": decision.role,
        "alias": decision.spec.alias,
        "provider": decision.spec.provider,
        "upstream": decision.spec.upstream,
        "fallback_depth": decision.fallback_depth,
        "budget_verdict": [(s.alias, s.verdict.value)
                           for s in decision.skipped],
        "est_tokens": decision.base_tokens,
        "actual_tokens": result.total_tokens,
    }


@contextmanager
def routed_span(role: str):
    """Span riêng cho MỘT lượt gọi định tuyến. Không bao giờ raise — nếu
    get_client()/start_as_current_observation() lỗi (SDK hỏng, tracer hỏng…)
    thì yield None và lệnh gọi model thật bên trong khối with vẫn chạy bình
    thường, không có span bọc (bất biến toàn module: một lượt chat không bao
    giờ vỡ vì lỗi tracing).

    start_as_current_observation() (SDK) chỉ hỗ trợ `with` đồng bộ (kiểm tra
    trực tiếp: lớp trả về, _AgnosticContextManager, kế thừa
    contextlib._GeneratorContextManager và CHỈ override __enter__, không có
    __aenter__/__aexit__) — nên dùng `with` thường ở CẢ invoke() (sync) LẪN
    ainvoke() (async) của RoutedChatModel là đúng, không cần async with."""
    cm = None
    span = None
    try:
        cm = get_client().start_as_current_observation(
            name=f"route:{role}", as_type="span")
        span = cm.__enter__()
    except Exception:
        cm = None
    try:
        yield span
    finally:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass


def annotate_span(span, decision, result) -> None:
    """Gắn thuộc tính định tuyến lên span TRUYỀN VÀO trực tiếp — không tra
    "current" ở đâu cả (xem routed_span()/module docstring để biết lý do).
    span=None (routed_span lỗi lúc mở, hoặc gọi ngoài khối with) → no-op êm.
    Đây là đường NÓNG (gọi mỗi lượt LLM) nên im lặng hoàn toàn khi lỗi, không
    log lặp lại như get_handler()."""
    if span is None:
        return
    try:
        span.update(metadata=_metadata(decision, result))
    except Exception:
        pass
