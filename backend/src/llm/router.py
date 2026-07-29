"""Định tuyến vai trò → model (spec SP-1 §2).

resolve() CHỈ chọn, không gọi — gọi thật nằm ở Router.invoke() (Task 9). Tách
vậy để toàn bộ logic chọn test được bằng sổ ngân sách giả, không cần client.
"""
import logging
from dataclasses import dataclass

from .budget import BudgetLedger, Verdict
from .catalog import ModelSpec, chain_for, spec_for
from .providers import client_for

logger = logging.getLogger(__name__)


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
