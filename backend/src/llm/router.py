"""Định tuyến vai trò → model (spec SP-1 §2).

resolve() CHỈ chọn, không gọi — gọi thật nằm ở Router.invoke() (Task 9). Tách
vậy để toàn bộ logic chọn test được bằng sổ ngân sách giả, không cần client.
"""
import logging
from dataclasses import dataclass

from .budget import BudgetLedger, Verdict
from .catalog import ModelSpec, chain_for, spec_for
from .providers import client_for, strip_thought      # mở rộng import cũ
from .tokens import estimate_base_tokens

logger = logging.getLogger(__name__)

# 429 nghỉ lâu hơn lỗi khác: hạn mức hồi theo phút/ngày, còn 5xx với timeout
# thường là sự cố thoáng qua vài giây.
COOLDOWN_RATE_LIMIT_S = 60.0
COOLDOWN_ERROR_S = 15.0


@dataclass(frozen=True)
class SkippedLink:
    alias: str
    verdict: Verdict


@dataclass(frozen=True)
class RouteDecision:
    """Quyết định định tuyến của MỘT lượt gọi.

    Mang cả những mắt xích bị bỏ qua và lý do, không chỉ mang cái được chọn:
    đây đúng là bộ thuộc tính span mà kế hoạch C đổ vào Langfuse để một trace
    tự trả lời được "vì sao lượt này chạy Groq chứ không phải Gemini". Không
    ghi lại lúc quyết định thì sau đó không dựng lại được.
    """
    role: str
    spec: ModelSpec
    fallback_depth: int
    skipped: tuple[SkippedLink, ...]
    base_tokens: int


class ChainExhausted(RuntimeError):
    """Cạn cả chuỗi cho một vai. Node gọi bắt lỗi này và degrade về SAFE_MSG —
    người dùng không bao giờ thấy stack trace (spec §6)."""

    def __init__(self, role: str, skipped: tuple[SkippedLink, ...]) -> None:
        self.role = role
        self.skipped = skipped
        chi_tiet = ", ".join(f"{s.alias}={s.verdict.value}" for s in skipped)
        super().__init__(f"cạn chuỗi cho vai {role!r}: {chi_tiet}")


@dataclass(frozen=True)
class AttemptError:
    alias: str
    error: str


@dataclass(frozen=True)
class InvokeResult:
    message: object                 # AIMessage, content đã được scrub
    decision: RouteDecision
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    attempts: tuple[AttemptError, ...]   # các mắt xích đã thử và hỏng


class Router:
    def __init__(self, ledger: BudgetLedger, client_factory=client_for) -> None:
        self._ledger = ledger
        # client_factory tiêm được để test bằng client giả. Task 9 dùng tới hai
        # trường dưới; khai đủ ngay từ đây để KHÔNG phải định nghĩa lại
        # __init__ ở task sau.
        self._client_factory = client_factory
        self._clients: dict[str, object] = {}

    def resolve(self, role: str, base_tokens: int,
                pin: str | None = None) -> RouteDecision:
        """Mắt xích đầu tiên còn đủ ngân sách và không bị cooldown.

        pin: bỏ qua toàn bộ chuỗi, ép đúng một model. Chế độ này TỒN TẠI VÌ
        EVAL (spec §2): thiết kế fallback khiến cùng một câu hỏi có thể được
        trả lời bởi 3 model khác nhau tuỳ trạng thái ngân sách lúc đó, nên eval
        phải đo MỘT MODEL chứ không phải một trạng thái ngân sách. Ghim là
        ghim — ngân sách cạn cũng không tụt, vì tụt lặng lẽ sẽ làm hỏng phép đo
        mà không báo gì.
        """
        if pin is not None:
            return RouteDecision(role=role, spec=spec_for(pin),
                                 fallback_depth=0, skipped=(),
                                 base_tokens=base_tokens)

        skipped: list[SkippedLink] = []
        for depth, spec in enumerate(chain_for(role)):
            verdict = self._ledger.can_afford(spec, base_tokens)
            if verdict is Verdict.OK:
                if skipped:
                    logger.info("vai %s tụt xuống %s (bỏ qua: %s)", role,
                                spec.alias,
                                [f"{s.alias}={s.verdict.value}" for s in skipped])
                return RouteDecision(role=role, spec=spec, fallback_depth=depth,
                                     skipped=tuple(skipped),
                                     base_tokens=base_tokens)
            skipped.append(SkippedLink(alias=spec.alias, verdict=verdict))

        raise ChainExhausted(role, tuple(skipped))

    def _client(self, spec: ModelSpec, tools):
        # Cache theo alias: dựng lại client mỗi lượt là lãng phí (dù là
        # ChatOpenAI hay ChatGoogleGenerativeAI — client_for() trả loại nào
        # tuỳ provider, xem Task 7), mà tools thì
        # đổi theo lượt nên bind_tools() gọi lại mỗi lần (nó trả về bản bọc
        # mới, không sửa client gốc).
        if spec.alias not in self._clients:
            self._clients[spec.alias] = self._client_factory(spec)
        client = self._clients[spec.alias]
        return client.bind_tools(tools) if tools else client

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 429 or "429" in str(exc)

    def _cooldown_for(self, spec: ModelSpec, exc: Exception) -> None:
        seconds = (COOLDOWN_RATE_LIMIT_S if self._is_rate_limit(exc)
                   else COOLDOWN_ERROR_S)
        self._ledger.cooldown(spec, seconds)
        logger.warning("%s hỏng (%s) — nghỉ %.0fs", spec.alias, exc, seconds)

    @staticmethod
    def _usage(response) -> tuple[int, int, int]:
        """Rút (prompt, completion, total) — LẤY total THÔ CỦA PROVIDER, không
        bao giờ tự cộng lại prompt + completion.

        Hai nhánh, mỗi nhánh ứng với MỘT client khác nhau (xem providers.py):

        1. response_metadata["token_usage"] — ChatOpenAI (Groq, OpenRouter,
           hình dạng OpenAI-compat). Đây là khối usage thô của endpoint, giữ
           nguyên total_tokens do provider báo. Phép đo gốc ngày 2026-07-28
           cho thấy Gemma đếm thiếu 7 lần nếu tự cộng p+c (p=11, c=36, nhưng
           total=337 — ~290 token "thinking" không nằm trong completion) được
           lấy QUA NHÁNH NÀY, tại thời điểm đó Google còn chạy qua endpoint
           OpenAI-compat. Task 7 đã chuyển Google sang client khác (xem nhánh
           2) chính vì bug thought_signature ở vòng lặp tool — nhánh này từ đó
           không còn được Google đụng tới nữa, chỉ Groq/OpenRouter còn dùng.

        2. usage_metadata — ChatGoogleGenerativeAI (Google: cả Gemini lẫn
           Gemma, kể từ Task 7). Client này KHÔNG BAO GIỜ set
           response_metadata["token_usage"] (xem
           langchain_google_genai.chat_models._response_to_result(), bản đã
           cài trong .venv) nên mọi lượt Google đều rơi xuống nhánh này.
           total_tokens ở đây vẫn là total_token_count THÔ của API — KHÔNG
           phải input_tokens + output_tokens tính lại — nên đáng tin cậy vì
           cùng lý do như nhánh 1: không bao giờ tin một tổng p+c tự tính
           trong cùng một tầng, phải tin con số provider tự báo. (output_tokens
           ở nhánh này đã CỘNG SẴN token "thinking" của Gemma vào — xem
           output_token_details["reasoning"] nếu cần tách riêng để chẩn đoán.)
        """
        raw = (getattr(response, "response_metadata", None) or {}).get(
            "token_usage") or {}
        if raw:
            prompt = int(raw.get("prompt_tokens") or 0)
            completion = int(raw.get("completion_tokens") or 0)
            total = int(raw.get("total_tokens") or (prompt + completion))
            return prompt, completion, total
        meta = getattr(response, "usage_metadata", None) or {}
        prompt = int(meta.get("input_tokens") or 0)
        completion = int(meta.get("output_tokens") or 0)
        return prompt, completion, int(meta.get("total_tokens") or
                                       (prompt + completion))

    def _finish(self, decision: RouteDecision, response,
                attempts: list[AttemptError]) -> InvokeResult:
        if decision.spec.emits_thought_tags:
            response.content = strip_thought(response.content)
        prompt, completion, total = self._usage(response)
        self._ledger.record(decision.spec, prompt_tokens=prompt,
                            completion_tokens=completion, total_tokens=total)
        return InvokeResult(message=response, decision=decision,
                            prompt_tokens=prompt, completion_tokens=completion,
                            total_tokens=total, attempts=tuple(attempts))

    def _max_attempts(self, role: str, pin: str | None) -> int:
        # Ghim thì thử đúng một lần: ghim là ghim, kể cả khi hỏng. Tụt lặng lẽ
        # sẽ làm hỏng phép đo eval mà không báo gì (spec §2).
        return 1 if pin is not None else len(chain_for(role))

    def invoke(self, role: str, messages: list, tools: list | None = None,
               pin: str | None = None) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = self._client(decision.spec, tools).invoke(messages)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))

    async def ainvoke(self, role: str, messages: list,
                      tools: list | None = None,
                      pin: str | None = None) -> InvokeResult:
        base = estimate_base_tokens(messages, tools)
        attempts: list[AttemptError] = []
        for _ in range(self._max_attempts(role, pin)):
            decision = self.resolve(role, base, pin=pin)
            try:
                response = await self._client(
                    decision.spec, tools).ainvoke(messages)
            except Exception as exc:
                attempts.append(AttemptError(decision.spec.alias, str(exc)))
                self._cooldown_for(decision.spec, exc)
                continue
            return self._finish(decision, response, attempts)
        raise ChainExhausted(role, tuple(
            SkippedLink(a.alias, Verdict.COOLDOWN) for a in attempts))


from langchain_core.runnables import Runnable

from .catalog import ROLES
from .store import PostgresUsageStore


class RoutedChatModel(Runnable):
    """Mặt tiền giữ nguyên hợp đồng cũ của agents/.

    Code agents/ ở repo nguồn gọi self._llms["read"].invoke(...) với object
    dựng sẵn MỘT LẦN. Ngân sách thì đổi theo từng lượt, nên không dựng sẵn
    được — lớp này giải quyết model TẠI THỜI ĐIỂM INVOKE, giấu chuyện đó đi.
    Nhờ vậy toàn bộ agents/ port sang không phải sửa dòng nào ở chỗ gọi LLM.

    Trả về AIMessage chứ không phải InvokeResult: hợp đồng cũ là AIMessage, và
    đổi nó sẽ lan ra khắp agents/. Quyết định định tuyến lấy lại qua
    .last_decision (kế hoạch C đổ nó vào span Langfuse).
    """

    def __init__(self, router: "Router", role: str, tools: list | None = None,
                 pin: str | None = None) -> None:
        self._router = router
        self._role = role
        self._tools = tools
        self._pin = pin
        self.last_decision: RouteDecision | None = None

    def bind_tools(self, tools: list, **kwargs) -> "RoutedChatModel":
        # Trả bản MỚI, không sửa bản gốc — khớp ngữ nghĩa bind_tools của
        # LangChain. Bản mới dùng chung router nên dùng chung sổ ngân sách.
        return RoutedChatModel(self._router, self._role, tools, self._pin)

    def invoke(self, input, config=None, **kwargs):
        result = self._router.invoke(self._role, input, tools=self._tools,
                                     pin=self._pin)
        self.last_decision = result.decision
        return result.message

    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._router.ainvoke(self._role, input,
                                            tools=self._tools, pin=self._pin)
        self.last_decision = result.decision
        return result.message


def build_router(store=None, clock=None) -> Router:
    """Router cho đường chạy thật. Mặc định dùng sổ Postgres."""
    return Router(BudgetLedger(store or PostgresUsageStore(), clock=clock))


def make_llms(router: Router,
              pins: dict[str, str] | None = None) -> dict[str, RoutedChatModel]:
    """dict vai → model, đúng hình dạng make_llms() cũ của repo nguồn.

    pins: ghim từng vai, dùng cho đường eval — eval phải đo MỘT MODEL chứ
    không phải một trạng thái ngân sách (spec §2).
    """
    pins = pins or {}
    return {role: RoutedChatModel(router, role, pin=pins.get(role))
            for role in ROLES}
