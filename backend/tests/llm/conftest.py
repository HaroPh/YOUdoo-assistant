"""Đồ giả dùng chung cho test tầng llm. Không có gì ở đây chạm mạng hay DB."""
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    """Đồng hồ điều khiển được — cửa sổ trượt không test được bằng time thật."""

    def __init__(self, now: datetime = T0) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)


class ExplodingStore:
    """Kho luôn ném lỗi — dùng để kiểm tra hành vi fail-open của ngân sách."""

    def record(self, **kwargs) -> None:
        raise RuntimeError("Postgres sập")

    def usage_since(self, **kwargs):
        raise RuntimeError("Postgres sập")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


from langchain_core.messages import AIMessage


class FakeChatClient:
    """Client giả — trả sẵn kịch bản, đếm số lần bị gọi.

    responses: danh sách phần tử, mỗi phần tử là AIMessage (thành công) HOẶC
    một Exception (ném ra). Dùng hết thì lặp lại phần tử cuối.
    """

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[list] = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def _next(self, messages):
        self.calls.append(messages)
        item = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def invoke(self, messages, **kwargs):
        return self._next(messages)

    async def ainvoke(self, messages, **kwargs):
        return self._next(messages)


def fake_ai(content="xong", *, prompt=10, completion=20, total=30):
    """AIMessage kèm usage ở ĐÚNG chỗ mà provider thật đặt nó."""
    return AIMessage(
        content=content,
        response_metadata={"token_usage": {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total}})


class FakeRateLimit(Exception):
    status_code = 429


class FakeServerError(Exception):
    status_code = 503
