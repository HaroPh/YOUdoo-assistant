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
        self.configs: list = []             # MỚI: config từng lượt
        self.bound_tools = None
        self.bound_tool_kwargs: dict = {}   # MỚI: kwargs của bind_tools

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        self.bound_tool_kwargs = dict(kwargs)
        return self

    def _next(self, messages, config=None):
        self.calls.append(messages)
        self.configs.append(config)
        item = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def invoke(self, messages, config=None, **kwargs):
        return self._next(messages, config)

    async def ainvoke(self, messages, config=None, **kwargs):
        return self._next(messages, config)


def fake_ai(content="xong", *, prompt=10, completion=20, total=30):
    """AIMessage kèm usage ở ĐÚNG chỗ mà provider thật đặt nó (ChatOpenAI).

    Hình dạng này khớp Groq/OpenRouter: usage nằm ở
    response_metadata["token_usage"]. KHÔNG khớp Google — xem fake_ai_google()."""
    return AIMessage(
        content=content,
        response_metadata={"token_usage": {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total}})


def fake_ai_google(content="xong", *, prompt=10, completion=20, total=30,
                   reasoning=0):
    """AIMessage kèm usage ở ĐÚNG chỗ mà ChatGoogleGenerativeAI thật đặt nó.

    Nguồn sự thật: langchain_google_genai.chat_models._response_to_result()
    (backend/.venv/Lib/site-packages/langchain_google_genai/chat_models.py,
    ~dòng 1119-1140, bản 4.2.0). Client này KHÔNG BAO GIỜ set
    response_metadata["token_usage"] — usage chỉ nằm ở usage_metadata (một
    UsageMetadata TypedDict), với output_tokens đã CỘNG SẴN
    candidates_token_count + thoughts_token_count, và total_tokens là
    total_token_count thô của API (không phải input+output tính lại).
    response_metadata vẫn tồn tại (prompt_feedback, finish_reason, ...) nhưng
    không bao giờ mang khoá "token_usage" — nên để rỗng ở đây cho đúng hình
    dạng thật, không phải vì "không quan trọng"."""
    meta = {"input_tokens": prompt, "output_tokens": completion,
             "total_tokens": total}
    if reasoning:
        meta["output_token_details"] = {"reasoning": reasoning}
    return AIMessage(content=content, response_metadata={},
                     usage_metadata=meta)


def fake_ai_rong(*, prompt=361, completion=2045, total=2406,
                 finish_reason="MAX_TOKENS"):
    """Phản hồi RỖNG mà production thật sự nhận được.

    Số liệu chép từ phép đo sống 2026-08-13 với gemma-4-26b ở vai router:
    toàn bộ 2045 token đầu ra là reasoning, content rỗng, finish_reason
    MAX_TOKENS. Đây là hình dạng đã làm intent router phân loại nhầm thành
    'unknown'."""
    return AIMessage(
        content="",
        response_metadata={"finish_reason": finish_reason},
        usage_metadata={"input_tokens": prompt, "output_tokens": completion,
                        "total_tokens": total,
                        "output_token_details": {"reasoning": completion}})


def fake_ai_tool_call(name="get_stock", *, prompt=10, completion=20, total=30):
    """Lượt gọi tool THÀNH CÔNG — content RỖNG, có tool_calls.

    Đo 2026-08-13: cả gemini-3.5-flash-lite lẫn gemma-4-26b đều trả đúng hình
    dạng này (content='', 1 tool_call, finish_reason=STOP) cho câu hỏi tồn
    kho. Đây là ca dễ bị bản sửa phá nhất."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": "call_1"}],
        response_metadata={"token_usage": {
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total}})


class FakeRateLimit(Exception):
    status_code = 429


class FakeServerError(Exception):
    status_code = 503
