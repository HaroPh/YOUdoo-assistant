"""Langfuse tracing — không đường nào để lỗi ở đây làm hỏng một lượt chat.

get_handler(): CallbackHandler của Langfuse, gắn ở tầng LangChain (mỗi node
LangGraph tự thành 1 span lồng nhau khi truyền vào config={"callbacks":[...]}).
Construct lỗi (bug SDK, import hỏng) → trả None, log 1 lần, không throw. SDK
tự nó ĐÃ no-op êm khi thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY (đọc
nguồn: langfuse._client.client.Langfuse.__init__ — thiếu key thì gán
self._otel_tracer = NoOpTracer() rồi return sớm, KHÔNG raise) — get_handler()
không cần tự kiểm tra env, chỉ cần bọc try/except phòng lỗi construct khác.

annotate_current_span(): gắn thuộc tính định tuyến lên span Langfuse HIỆN
TẠI. Gọi ngay bên trong RoutedChatModel.ainvoke()/.invoke() (spec §4.2),
KHÔNG phải ở agents/nodes.py — giữ đúng ràng buộc "chỉ llm/ biết provider",
và làm giàu miễn phí cả đường eval harness (evals/run_eval.py cũng gọi
RoutedChatModel). Langfuse.update_current_span() của SDK tự no-op nếu không
có span đang mở hoặc tracing tắt (đọc nguồn: kiểm self._tracing_enabled và
self._get_current_otel_span() is not None trước khi làm gì) — không cần tự
kiểm tra điều đó ở đây, chỉ cần bọc try/except phòng lỗi SDK khác. Đây là
đường NÓNG (gọi mỗi lượt LLM) nên im lặng hoàn toàn khi lỗi, không log lặp
lại như get_handler()."""
import logging

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


def annotate_current_span(decision, result) -> None:
    """decision: RouteDecision (router.py). result: InvokeResult (router.py)
    — result.total_tokens là con số có thẩm quyền, KHÔNG cộng
    prompt_tokens+completion_tokens (bất biến toàn dự án)."""
    try:
        get_client().update_current_span(metadata={
            "role": decision.role,
            "alias": decision.spec.alias,
            "provider": decision.spec.provider,
            "upstream": decision.spec.upstream,
            "fallback_depth": decision.fallback_depth,
            "budget_verdict": [(s.alias, s.verdict.value)
                              for s in decision.skipped],
            "est_tokens": decision.base_tokens,
            "actual_tokens": result.total_tokens,
        })
    except Exception:
        pass
