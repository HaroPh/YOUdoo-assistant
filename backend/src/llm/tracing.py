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
tra "current" ở đâu cả.

ĐÃ KHẮC PHỤC 2026-08-18 (with_route_metadata): thông tin định tuyến nay đi
kèm `config["metadata"]["route"]` xuống lệnh gọi model, nên CallbackHandler
gắn nó lên đúng observation GENERATION BÊN TRONG trace hội thoại. Nghiệm thu
sống qua Langfuse thật: 5/5 generation của một lượt chat mang metadata, cùng
traceId với hội thoại. Đoạn dưới mô tả giới hạn của routed_span() — vẫn đúng
với riêng span đó, và span đó GIỮ LẠI vì nó mang phần kế toán SAU lượt gọi
(actual_tokens/discarded_tokens/attempts) mà config không mang được.

GIỚI HẠN ĐÃ BIẾT (xác nhận bằng chạy sống 2026-07-30, KHÔNG như dự đoán ban
đầu): span mới KHÔNG lồng làm con của cây trace hội thoại — nó xuất hiện
như MỘT TRACE GỐC RIÊNG (parentObservationId=null, traceId khác trace
LangGraph/intent_router/...). Lý do: việc gắn span CHA cho routed_span()
cũng dựa vào "current span" ambient (qua start_as_current_observation()),
nên chịu ĐÚNG loại giới hạn context-propagation nói trên — không chỉ riêng
update_current_span() mới bị. Metadata VẪN tra cứu đúng, đủ field qua API/UI
Langfuse (tìm theo tên span "route:<role>"), chỉ KHÔNG cùng trace với hội
thoại. Cách khắc phục đã ghi sẵn ở đây từ 2026-07-30 — tiêm
role/alias/provider thẳng vào config["metadata"] để CallbackHandler tự gắn
lên đúng GENERATION nó tạo trong trace thật — nay ĐÃ LÀM, xem
with_route_metadata() ngay dưới."""
import logging
import os
from contextlib import contextmanager

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from .budget import Verdict

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
    prompt_tokens+completion_tokens (bất biến toàn dự án).

    budget_verdict CHỈ giữ phán quyết NGÂN SÁCH thật (rpm/tpm/rpd/cooldown).
    Từ khi có nhánh phản hồi-rỗng, decision.skipped còn chứa cả mắt xích bị
    bỏ vì Verdict.EMPTY (model không ốm, không cạn hạn mức — nó chỉ không trả
    lời nổi prompt này trong CHÍNH lượt gọi này). Gộp chung vào
    budget_verdict sẽ làm ai đó truy vấn khoá này để đếm số lần cạn hạn mức
    đếm dư. Tách sang khoá riêng empty_skips (danh sách alias), phân biệt
    bằng Verdict.EMPTY chứ không so chuỗi.

    actual_tokens là token của lượt ĐƯỢC TRẢ VỀ, KHÔNG phải chi phí thật của
    lời gọi: một lượt tụt mắt xích còn đốt discarded_tokens ở những lượt bị
    vứt. Hai con số để RIÊNG chứ không cộng sẵn — cộng vào actual_tokens sẽ
    làm nó lệch khỏi con số provider báo cho đúng lượt đó, phá bất biến
    "không bao giờ tự tính lại tổng token" của toàn dự án. Muốn chi phí thật
    thì cộng ở nơi truy vấn."""
    return {
        "role": decision.role,
        "alias": decision.spec.alias,
        "provider": decision.spec.provider,
        "upstream": decision.spec.upstream,
        "fallback_depth": decision.fallback_depth,
        "budget_verdict": [(s.alias, s.verdict.value)
                           for s in decision.skipped
                           if s.verdict is not Verdict.EMPTY],
        "empty_skips": [s.alias for s in decision.skipped
                        if s.verdict is Verdict.EMPTY],
        "est_tokens": decision.base_tokens,
        "actual_tokens": result.total_tokens,
        "discarded_tokens": getattr(result, "discarded_tokens", 0),
        # Cắt 200 ký tự: a.error có thể là nguyên văn exception nhà cung cấp
        # (dài, đôi khi kèm payload). Trace là chỗ chẩn đoán, cần alias + đủ
        # chữ để nhận ra loại lỗi, không cần cả stack.
        "attempts": [(a.alias, (a.error or "")[:200])
                     for a in getattr(result, "attempts", ())],
    }


def with_route_metadata(config, decision):
    """BẢN SAO của `config` có thêm metadata định tuyến của LƯỢT GỌI NÀY.

    Đây là cách khắc phục GIỚI HẠN ĐÃ BIẾT nêu ở docstring module: span do
    `routed_span()` dựng rơi ra thành một TRACE GỐC RIÊNG, không nằm trong cây
    trace hội thoại, vì cả nó lẫn `update_current_span()` đều dựa vào "current
    span" AMBIENT — thứ không lan qua được `loop.run_in_executor` mà LangChain
    dùng để dispatch callback bất đồng bộ.

    Đường này KHÔNG đụng tới ambient context: `CallbackHandler` của Langfuse đã
    nằm sẵn trong `config["callbacks"]` (ERPAgent gắn lúc setup) và tự tạo
    observation GENERATION BÊN TRONG trace hội thoại thật; metadata trong
    `config` được chính nó đọc và gắn lên đúng observation đó. Tức parent
    linkage đi qua THAM SỐ HÀM CALLBACK — cơ chế của chính SDK — chứ không qua
    context.

    Chỉ mang được các sự kiện TRƯỚC lượt gọi (vai, model, vì sao chọn nó). Số
    token là sự kiện SAU, và Langfuse tự ghi chúng lên generation của nó theo
    chuẩn `usage`; phần kế toán đầy đủ (kể cả `discarded_tokens`) vẫn nằm ở
    `routed_span()`/`annotate_span()`. Hai chỗ có chủ đích, không phải trùng
    lặp bỏ quên.

    Gom dưới MỘT khoá "route" thay vì rải khoá phẳng: metadata của Langfuse có
    những khoá mang nghĩa riêng (`langfuse_session_id`, …) và người gọi cũng có
    thể đã đặt metadata của họ — lồng một cấp thì không thể va nhau.

    KHÔNG sửa dict của người gọi: LangGraph tái dùng một config giữa các node,
    sửa tại chỗ là rò rỉ metadata lượt này sang lượt khác.

    Không bao giờ ném (bất biến toàn module): hỏng thì trả nguyên config vào.
    """
    try:
        out = dict(config or {})
        meta = dict(out.get("metadata") or {})
        meta["route"] = {
            "role": decision.role,
            "alias": decision.spec.alias,
            "provider": decision.spec.provider,
            "upstream": decision.spec.upstream,
            "fallback_depth": decision.fallback_depth,
        }
        out["metadata"] = meta
        return out
    except Exception:
        return config


@contextmanager
def routed_span(role: str):
    """Span riêng cho MỘT lượt gọi định tuyến. Không bao giờ raise — nếu
    get_client()/start_as_current_observation() lỗi (SDK hỏng, tracer hỏng…)
    thì yield None và lệnh gọi model thật bên trong khối with vẫn chạy bình
    thường, không có span bọc (bất biến toàn module: một lượt chat không bao
    giờ vỡ vì lỗi tracing).

    Tự kiểm tra LANGFUSE_PUBLIC_KEY/SECRET_KEY TRƯỚC khi gọi get_client() —
    khác get_handler() (không tự kiểm tra env, vì CallbackHandler() no-op êm
    và chỉ construct MỘT LẦN lúc ERPAgent.setup()). routed_span() gọi MỖI
    lượt LLM — nếu thiếu khoá, get_client() (hàm của SDK) vẫn construct một
    Langfuse() rỗng mỗi lần và tự log WARNING "initialized without
    public_key" KHÔNG cache/không im lặng lần 2 (đo được thật: N lượt gọi ->
    N dòng warning) — khác hẳn CallbackHandler's no-op. Tự kiểm tra ở đây
    né hẳn đường đó, không dựa "SDK tự no-op êm" như get_handler().

    start_as_current_observation() (SDK) chỉ hỗ trợ `with` đồng bộ (kiểm tra
    trực tiếp: lớp trả về, _AgnosticContextManager, kế thừa
    contextlib._GeneratorContextManager và CHỈ override __enter__, không có
    __aenter__/__aexit__) — nên dùng `with` thường ở CẢ invoke() (sync) LẪN
    ainvoke() (async) của RoutedChatModel là đúng, không cần async with."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY")
            and os.environ.get("LANGFUSE_SECRET_KEY")):
        yield None
        return
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
