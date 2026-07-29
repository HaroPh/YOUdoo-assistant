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
        """Rút (prompt, completion, total) — LẤY total THÔ CỦA PROVIDER.

        BẪY: một số phiên bản LangChain tự tính lại total = input + output khi
        dựng usage_metadata. Với họ Gemma đó đúng là con số đếm thiếu 7 lần
        (đo 2026-07-28: p=11, c=36 nhưng provider báo total=337 — ~290 token
        "thinking" không nằm trong completion_tokens). Nên ưu tiên
        response_metadata["token_usage"], nơi giữ nguyên khối usage thô.
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
