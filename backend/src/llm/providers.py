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

# SDK KHÔNG được tự thử lại (2026-08-19). Đặt TƯỜNG MINH cho cả hai nhánh:
# ChatGoogleGenerativeAI mặc định 6, ChatOpenAI mặc định None (rơi về mặc định
# của SDK OpenAI). Cả hai đều là thử-lại-mù.
#
# VÌ SAO 0 CHỨ KHÔNG PHẢI 1-2. Có BA lớp thử lại chồng nhau:
#   1. SDK          — 6 (Google) / 2 (OpenAI)
#   2. Router       — chuỗi fallback + cooldown, hoặc 1 lần nếu ghim
#   3. run_resilient — 2, ở đường eval
# Lớp SDK là lớp DUY NHẤT mù: nó không phân biệt 429-trần-phút (đáng chờ) với
# 429-trần-ngày (vô vọng), không biết còn mắt xích nào để tụt xuống, và không
# ghi sổ ngân sách. Lớp 2 và 3 biết cả ba thứ đó.
#
# TÁC HẠI ĐO ĐƯỢC 2026-08-19: mỗi lần SDK bắn lại ĐỐT THÊM hạn mức mà
# Router._finish() KHÔNG ghi (nó chỉ chạy trên phản hồi thành công). Kết quả:
# llm_usage ghi 179 lượt/24h trong khi Google tính 500/500 cho cùng model. Đó
# là vòng luẩn quẩn — càng gần trần càng nhiều 429, mỗi 429 đẻ 6 lần bắn lại,
# mỗi lần bắn lại đốt thêm hạn mức. Sổ ngân sách tồn tại để chặn TRƯỚC khi
# chạm trần nhà cung cấp, và nó không thấy được phần lớn lượng tiêu thụ thật.
#
# Đo trên model đã cạn trần ngày: max_retries=0 hỏng sau 0,4s; max_retries=6
# mất 33,4s. 33 giây đó là thời gian ngồi thử lại một hạn mức NGÀY — thứ không
# hồi trong vài chục giây — thay vì tụt ngay sang mắt xích kế của chuỗi.
MAX_RETRIES = 0

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
            max_retries=MAX_RETRIES,  # xem chú thích ở MAX_RETRIES
        )
    return ChatOpenAI(
        model=spec.model_id,          # ID GỐC của nhà cung cấp, không phải alias
        base_url=BASE_URLS[spec.provider],
        api_key=api_key,
        temperature=0,
        timeout=spec.timeout_s,
        max_tokens=spec.max_output_tokens,
        max_retries=MAX_RETRIES,      # xem chú thích ở MAX_RETRIES
    )
