"""Client cho từng nhà cung cấp + chuẩn hoá đầu ra (spec SP-1 §2).

Chỗ DUY NHẤT biết base_url, tên biến môi trường, và loại client của từng nhà.
Không tầng nào khác được nhắc tới Google/Groq/OpenRouter.

Google dùng ChatGoogleGenerativeAI, KHÔNG dùng ChatOpenAI: spike Task 1
(docs/spikes/2026-07-28-thought-signature.md, 2026-07-28) đo hội thoại tool
2 lượt thật qua endpoint OpenAI-compat của Google và thấy vòng lặp KHÔNG hội
tụ — ChatOpenAI không mang thought_signature đi qua request kế tiếp, và
Google từ chối cứng ở lượt 2 với 400 INVALID_ARGUMENT. Groq và OpenRouter vẫn
ChatOpenAI: cả hai vẫn OpenAI-compatible và giữ tool-calling tiếng Việt bình
thường (đã đo — spec Phụ lục A). Đây vẫn là lý do SP-1 bỏ LiteLLM cho hai nhà
này: giá trị "hợp nhất giao thức" của nó đã bốc hơi.
"""
import os
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from .catalog import ModelSpec

# Chỉ Groq/OpenRouter dùng — Google không có base_url (SDK tự quản endpoint).
BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

ENV_KEYS = {
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Khối suy nghĩ MỞ ĐẦU. Neo vào đầu chuỗi (\A) có chủ đích: chỉ khối đầu tiên
# là suy nghĩ của model; chuỗi trông giống thẻ nằm giữa câu trả lời thật (người
# dùng hỏi về chính cú pháp đó) không được đụng tới.
_THOUGHT_RE = re.compile(r"\A\s*<thought>.*?</thought>\s*", re.DOTALL)
_THOUGHT_OPEN_RE = re.compile(r"\A\s*<thought>", re.DOTALL)


def strip_thought(content: str | None) -> str:
    """Gỡ khối <thought>…</thought> mở đầu — TẤT ĐỊNH, không nhờ prompt.

    Đo 2026-07-28: endpoint OpenAI-compat của Google KHÔNG tách phần suy nghĩ
    ra khỏi content cho họ Gemma; nó nối thẳng vào, câu trả lời thật nằm sau
    thẻ đóng. Và thinking không tắt được — reasoning_effort trả 400 "Thinking
    budget is not supported for this model".

    Cùng hình dạng với tool_leak_guard.py của repo nguồn: một cú scrub tất định
    tại ranh giới, vì định dạng model trả về chỉ tuân theo prompt một cách xác
    suất.

    Thiếu thẻ đóng (bị cắt giữa chừng) → trả RỖNG, để node gọi degrade về
    SAFE_MSG. Trả nửa khối suy nghĩ cho người dùng còn tệ hơn trả rỗng.
    """
    if not content:
        return ""

    stripped, n = _THOUGHT_RE.subn("", content, count=1)
    if n:
        return stripped

    # Có thẻ mở nhưng không khớp _THOUGHT_RE ⇒ thiếu thẻ đóng (bị cắt giữa
    # chừng). Trả rỗng thay vì nửa khối suy nghĩ.
    if _THOUGHT_OPEN_RE.match(content):
        return ""

    # Không có thẻ mở ở đầu chuỗi — không phải khối suy nghĩ, giữ nguyên.
    return content


def client_for(spec: ModelSpec):
    """Dựng client cho một model. Thiếu khoá → chết ngay, không đợi lúc gọi.

    Google → ChatGoogleGenerativeAI; Groq/OpenRouter → ChatOpenAI (quyết định
    spike Task 1). Đọc khoá và kiểm rỗng CHUNG cho cả hai nhánh trước khi rẽ,
    để thông báo lỗi thiếu biến môi trường nhất quán bất kể provider nào.
    """
    env_name = ENV_KEYS[spec.provider]
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(
            f"thiếu biến môi trường {env_name} — cần cho provider "
            f"{spec.provider!r} (model {spec.alias!r}). Xem .env.example.")

    if spec.provider == "google":
        # KHÔNG có base_url — SDK tự quản endpoint. Field tên `model` (không
        # phải `model_name`), `max_output_tokens` (không phải `max_tokens`,
        # dù đó là alias hợp lệ — dùng tên chính cho rõ nghĩa), `timeout`.
        return ChatGoogleGenerativeAI(
            model=spec.model_id,      # ID GỐC của nhà cung cấp, không phải alias
            api_key=api_key,
            temperature=0,
            timeout=spec.timeout_s,
            max_output_tokens=spec.max_output_tokens,
        )
    return ChatOpenAI(
        model=spec.model_id,          # ID GỐC của nhà cung cấp, không phải alias
        base_url=BASE_URLS[spec.provider],
        api_key=api_key,
        temperature=0,
        timeout=spec.timeout_s,
        max_tokens=spec.max_output_tokens,
    )
