# backend/evals/synthesis_live_score.py
"""Chấm điểm synthesis_live — THUẦN, không chạm DB/Ollama/LLM.

Tách khỏi run_eval.py để toàn bộ logic chấm chạy trong chế độ pytest mặc
định. Cùng lối đã dùng cho evals/retrieval_score.py.

GUARD_MSG import từ chính production (src.agents.synthesis) chứ không chép
lại chuỗi: bộ đo phải hỏng lớn tiếng nếu ai đổi câu từ chối, thay vì âm thầm
chấm sai.
"""
from src.agents.synthesis import GUARD_MSG
from evals.matching import _grounded_match

CITATION_HEADER = "📄 Nguồn:"


def split_body_and_footer(answer: str) -> tuple[str, str]:
    """Tách thân bài khỏi footer trích dẫn.

    BẮT BUỘC tách trước khi chấm sự kiện: footer chứa section_path, nên một
    `expect` trùng chữ với tiêu đề mục ("Nghỉ hằng năm") sẽ khớp nhờ footer dù
    thân bài không hề nêu — tính ĐẠT cho một câu trả lời rỗng."""
    head, sep, tail = answer.partition(CITATION_HEADER)
    return (head, tail) if sep else (answer, "")


def score_answer(body: str, kind: str, expect, expect_source: str) -> dict:
    """Chấm MỘT câu trả lời đầu-cuối.

    kind: "deep_chunk" | "distractor" | "insufficient".
    Trả None cho số đo KHÔNG áp dụng — ca `insufficient` không có sự kiện lẫn
    trích dẫn để chấm. Bên gọi chỉ trung bình trên ca áp dụng; trả True thay
    cho None sẽ thổi phồng số đo.
    """
    answer = body or ""
    refused = GUARD_MSG in answer
    if kind == "insufficient":
        return {"refusal_ok": refused, "fact_ok": None, "citation_ok": None}

    text, footer = split_body_and_footer(answer)
    return {
        "refusal_ok": not refused,
        "fact_ok": (not refused) and _grounded_match(expect, text),
        "citation_ok": (not refused) and bool(footer) and expect_source in footer,
    }
