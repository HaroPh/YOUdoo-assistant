"""Lưu trữ lượt gọi LLM — chỉ dây nối, KHÔNG chính sách (spec SP-1 §2).

Cùng khuôn transport.py / gateway.py của repo nguồn: chính sách hạn mức nằm ở
budget.py và không được biết Postgres tồn tại. Nhờ vậy toàn bộ logic ngân sách
test được bằng InMemoryUsageStore, không cần DB.

Bản Postgres nằm ở cùng file này (Task 6) — giữ hai implementation cạnh nhau
để hợp đồng giữa chúng nhìn thấy được trong một màn hình.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Usage:
    requests: int
    total_tokens: int


def _check_exactly_one(alias: str | None, provider: str | None) -> None:
    """Gộp theo alias (quota_scope="model") HOẶC theo provider (="account").
    Đưa cả hai, hoặc không đưa gì, đều là lỗi gọi — không đoán ý."""
    if (alias is None) == (provider is None):
        raise ValueError("phải đưa đúng một trong hai: alias hoặc provider")


class UsageStore(Protocol):
    def record(self, *, ts: datetime, alias: str, provider: str, upstream: str,
               prompt_tokens: int, completion_tokens: int,
               total_tokens: int) -> None: ...

    def usage_since(self, *, since: datetime, alias: str | None = None,
                    provider: str | None = None) -> Usage: ...


class InMemoryUsageStore:
    """Bản cho unit test và cho chế độ degrade khi Postgres không có.

    Không tự dọn bản ghi cũ: vòng đời của nó là một tiến trình test hoặc một
    lần chạy ngắn, nên tăng trưởng bộ nhớ không phải vấn đề. PostgresUsageStore
    mới là chỗ cần nghĩ tới chuyện đó.
    """

    def __init__(self) -> None:
        self._rows: list[tuple] = []   # (ts, alias, provider, total_tokens)

    def record(self, *, ts: datetime, alias: str, provider: str, upstream: str,
               prompt_tokens: int, completion_tokens: int,
               total_tokens: int) -> None:
        # upstream/prompt/completion không dùng cho phép cộng nào ở đây; giữ
        # trong chữ ký để hợp đồng khớp bản Postgres, nơi chúng được lưu để
        # chẩn đoán (so est_tokens với actual, xem span Langfuse ở kế hoạch C).
        self._rows.append((ts, alias, provider, total_tokens))

    def usage_since(self, *, since: datetime, alias: str | None = None,
                    provider: str | None = None) -> Usage:
        _check_exactly_one(alias, provider)
        idx = 1 if alias is not None else 2
        want = alias if alias is not None else provider
        hits = [r for r in self._rows if r[0] >= since and r[idx] == want]
        return Usage(requests=len(hits),
                     total_tokens=sum(r[3] for r in hits))
