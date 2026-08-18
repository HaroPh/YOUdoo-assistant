"""Bốn prompt sinh câu trả lời phải theo ngôn ngữ người dùng.

Đo 2026-08-18 qua HTTP thật: chỉ THÊM quy tắc ở cuối là KHÔNG đủ nếu prompt
còn ghim "trả lời bằng tiếng Việt" ở đầu — `mixed`/fuse hỏng vì ngữ cảnh nạp
vào (đoạn tài liệu + dữ liệu ERP, đều tiếng Việt) đủ nặng để câu mở đầu thắng
lại. Phải GỠ câu đầu VÀ THÊM khối cuối.
"""
import pytest

from src.agents import prompts

BON_PROMPT = ["SYSTEM_PROMPT", "CHITCHAT_PROMPT", "RAG_SYNTHESIS_PROMPT",
              "FUSE_PROMPT"]


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_khong_con_ghim_cung_tieng_viet(ten):
    assert "trả lời bằng tiếng Việt" not in getattr(prompts, ten)


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_co_khoi_language_rule(ten):
    assert prompts.LANGUAGE_RULE.strip() in getattr(prompts, ten)


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_language_rule_nam_o_CUOI(ten):
    """Vị trí là thứ quyết định, không phải nội dung: spike đo được quy tắc
    đặt giữa prompt KHÔNG lật được ngôn ngữ đầu ra."""
    p = getattr(prompts, ten)
    con_lai = p[p.index(prompts.LANGUAGE_RULE.strip())
                + len(prompts.LANGUAGE_RULE.strip()):]
    assert len(con_lai.strip().replace("/no_think", "").strip()) == 0, (
        f"{ten}: còn {len(con_lai)} ký tự sau LANGUAGE_RULE")


def test_language_rule_dan_danh_tu_rieng_giu_nguyen():
    """Tên tài liệu/sản phẩm/đối tác KHÔNG được dịch — nếu dịch thì trích dẫn
    nguồn và mã sản phẩm mất khả năng tra ngược."""
    assert "Proper nouns" in prompts.LANGUAGE_RULE
