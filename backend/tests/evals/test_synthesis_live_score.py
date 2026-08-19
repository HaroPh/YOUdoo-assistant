# backend/tests/evals/test_synthesis_live_score.py
"""Bộ chấm synthesis_live — unit thuần, KHÔNG cần Postgres/Ollama/LLM."""
from src.agents.synthesis import GUARD_MSG
from evals.synthesis_live_score import score_answer

_FOOTER = "\n\n📄 Nguồn:\n• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)"


def test_answerable_all_three_ok():
    body = "Từ ngày thứ 03 trở đi được tính thêm thời gian đi đường." + _FOOTER
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got == {"refusal_ok": True, "fact_ok": True, "citation_ok": True}


def test_answerable_refused_is_failure_on_all_applicable():
    # Từ chối một câu TRẢ LỜI ĐƯỢC là hỏng: không có sự kiện, không có footer.
    got = score_answer(GUARD_MSG, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got == {"refusal_ok": False, "fact_ok": False, "citation_ok": False}


def test_fact_missing_but_citation_right():
    # Dẫn đúng nguồn mà không nêu được sự kiện — hai số đo phải TÁCH nhau,
    # nếu gộp thì không biết lỗi ở truy xuất hay ở sinh.
    body = "Tôi không rõ con số cụ thể." + _FOOTER
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is False
    assert got["citation_ok"] is True


def test_fact_right_but_citation_wrong_file():
    # Trả lời ĐÚNG nhưng dẫn NHẦM nguồn — lỗi thật mà fact_acc không thấy.
    body = ("Từ ngày thứ 03 trở đi được tính thêm."
            "\n\n📄 Nguồn:\n• Điều 9. Thuế suất (luat-thuegtgt.pdf, tr.3)")
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is True
    assert got["citation_ok"] is False


def test_citation_ok_when_expected_source_among_several():
    # Chấm là "CÓ MẶT", không phải "là nguồn duy nhất" (spec §5): build_citations
    # dựng footer từ mọi chunk sống sót sau verify_citations.
    body = ("ngày thứ 03\n\n📄 Nguồn:\n"
            "• Điều 9. Thuế suất (luat-thuegtgt.pdf, tr.3)\n"
            "• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)")
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["citation_ok"] is True


def test_expect_may_be_tuple_of_observed_alternatives():
    # Cơ chế tuple của _grounded_match: mỗi phương án là một diễn đạt THẬT đã
    # quan sát, vẫn khớp nguyên văn — không có logic mờ nào.
    body = "được tính thêm thời gian đi đường" + _FOOTER
    got = score_answer(body, "deep_chunk",
                       ("ngày thứ 03", "được tính thêm thời gian đi đường"),
                       "boluat-laodong.pdf")
    assert got["fact_ok"] is True


def test_insufficient_refused_correctly():
    got = score_answer(GUARD_MSG, "insufficient", "", "")
    assert got == {"refusal_ok": True, "fact_ok": None, "citation_ok": None}


def test_insufficient_answered_is_fabrication():
    body = "Thủ đô nước Pháp là Paris." + _FOOTER
    got = score_answer(body, "insufficient", "", "")
    assert got["refusal_ok"] is False
    assert got["fact_ok"] is None


def test_distractor_kind_scored_like_answerable():
    body = "Đáp án đúng." + _FOOTER
    got = score_answer(body, "distractor", "Đáp án đúng", "boluat-laodong.pdf")
    assert got == {"refusal_ok": True, "fact_ok": True, "citation_ok": True}


def test_citation_ok_false_when_no_footer_at_all():
    got = score_answer("ngày thứ 03", "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is True
    assert got["citation_ok"] is False


def test_fact_not_matched_from_citation_footer_text():
    # BẪY THẬT: footer chứa section_path, nên nếu expect trùng chữ trong tiêu
    # đề mục thì so khớp trên TOÀN BỘ body sẽ tính ĐẠT dù thân bài không hề
    # nêu. Phải chấm sự kiện trên phần THÂN, không tính footer.
    body = ("Tôi không tìm thấy thông tin.\n\n📄 Nguồn:\n"
            "• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)")
    got = score_answer(body, "deep_chunk", "Nghỉ hằng năm", "boluat-laodong.pdf")
    assert got["fact_ok"] is False
