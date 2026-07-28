"""Ước lượng token TRUNG TÍNH với provider (spec SP-1 §2).

Đây là ước lượng, không phải phép đo. Ba nhà cung cấp tokenize khác nhau —
đo được 2026-07-28: cùng một payload, Groq tính 133 prompt_tokens còn Google
tính 57. Chênh lệch đó được bù bằng ModelSpec.token_multiplier, nhân BÊN TRONG
BudgetLedger.can_afford(), KHÔNG nhân ở đây: lúc ước lượng thì chưa chọn được
model nên chưa biết nhân hệ số nào.

cl100k_base chỉ là thước đo thay thế cho tokenizer thật của từng nhà. Sai số
được khép lại bằng cách BudgetLedger.record() ghi cả ước lượng lẫn số thật từ
trường usage của response (span Langfuse ở kế hoạch C hiển thị cả hai).
"""
import json

import tiktoken

_ENCODING = "cl100k_base"
_enc = None


def _encoder():
    # Nạp lười: tiktoken tải bảng mã ở lần dùng đầu, không nên trả giá đó lúc
    # import module.
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(_ENCODING)
    return _enc


def _text_of(message) -> str:
    """Rút phần chữ từ message LangChain HOẶC dict kiểu OpenAI."""
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # Nội dung nhiều phần (multimodal): chỉ cộng phần chữ. Phần ảnh không đo
    # được bằng tokenizer chữ, và SP-1 không có đường nào sinh ra chúng.
    parts = []
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
        elif isinstance(part, str):
            parts.append(part)
    return " ".join(parts)


def estimate_base_tokens(messages: list, tools: list | None = None) -> int:
    """Ước lượng token đầu vào cho một lượt gọi, chưa nhân hệ số provider."""
    if not messages and not tools:
        return 0
    enc = _encoder()
    total = sum(len(enc.encode(_text_of(m))) for m in messages)
    if tools:
        # Schema tool đi vào prompt dưới dạng JSON. Với agent ERP bind hàng
        # chục tool, phần này thường lớn hơn cả câu hỏi người dùng — bỏ qua nó
        # là ước lượng thiếu ở đúng chỗ đau nhất (Groq 8K TPM).
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(enc.encode(blob))
    return total
