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
import logging

import tiktoken

logger = logging.getLogger(__name__)

_ENCODING = "cl100k_base"
_enc = None
_enc_failed = False


def _encoder():
    # Nạp lười: tiktoken tải bảng mã ở lần dùng đầu, không nên trả giá đó lúc
    # import module. Blocker #3: lần nạp đầu tiên CẦN MẠNG — nằm trên đường
    # test mặc định vốn phải không chạm mạng. Máy dev có cache nên không lộ;
    # CI lạnh sẽ vỡ. Nạp lỗi thì đánh dấu và không thử lại mỗi lượt gọi (thử
    # lại mỗi lần sẽ làm MỌI request đều trả giá network timeout).
    global _enc, _enc_failed
    if _enc is None and not _enc_failed:
        try:
            _enc = tiktoken.get_encoding(_ENCODING)
        except Exception:
            _enc_failed = True
            logger.warning(
                "không nạp được tiktoken (%s) — tụt về ước lượng thô "
                "ký tự/4. Không ảnh hưởng kế toán: total_tokens từ response "
                "mới là con số có thẩm quyền, đây chỉ dùng để ước lượng "
                "TRƯỚC khi gọi.", _ENCODING, exc_info=True)
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


def _estimate_crude(messages: list, tools: list | None) -> int:
    total = sum(len(_text_of(m)) for m in messages)
    if tools:
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(blob)
    return total // 4


def estimate_base_tokens(messages: list, tools: list | None = None) -> int:
    """Ước lượng token đầu vào cho một lượt gọi, chưa nhân hệ số provider."""
    if not messages and not tools:
        return 0
    enc = _encoder()
    if enc is None:
        return _estimate_crude(messages, tools)
    total = sum(len(enc.encode(_text_of(m))) for m in messages)
    if tools:
        # Schema tool đi vào prompt dưới dạng JSON. Với agent ERP bind hàng
        # chục tool, phần này thường lớn hơn cả câu hỏi người dùng — bỏ qua nó
        # là ước lượng thiếu ở đúng chỗ đau nhất (Groq 8K TPM).
        blob = json.dumps(tools, ensure_ascii=False, default=str)
        total += len(enc.encode(blob))
    return total
