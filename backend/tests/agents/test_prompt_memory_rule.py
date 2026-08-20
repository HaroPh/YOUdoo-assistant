"""Chỉ HAI prompt được dạy phát marker ghi nhớ.

Đặt khắp nơi chỉ tăng nguy cơ bắn marker vu vơ — và false_injection là hướng
nguy hiểm được gác TUYỆT ĐỐI ở bộ eval `memory`.
"""
from src.agents import prompts


def test_hai_prompt_hoi_thoai_co_luat_ghi_nho():
    assert prompts.MEMORY_RULE in prompts.SYSTEM_PROMPT
    assert prompts.MEMORY_RULE in prompts.CHITCHAT_PROMPT


def test_prompt_khac_khong_co_luat_ghi_nho():
    for name in ("RAG_SYNTHESIS_PROMPT", "FUSE_PROMPT", "INTENT_ROUTER_PROMPT",
                 "WRITE_PLANNER_PROMPT", "GATHER_ERP_PROMPT"):
        assert prompts.MEMORY_RULE not in getattr(prompts, name), name


def test_luat_ghi_nho_cam_ghi_ma_chung_tu():
    # Cổng tất định vẫn là lưới cuối, nhưng prompt phải nói trước để cổng ít
    # phải bắn — cùng khuôn "lớp xác suất + lớp phủ quyết".
    assert "mã chứng từ" in prompts.MEMORY_RULE


def test_no_think_still_ends_system_prompt():
    """Marker /no_think phải nằm ở CUỐI SYSTEM_PROMPT để tắt suy luận.

    Áp lên cả LANGUAGE_RULE lẫn MEMORY_RULE — chúng không được đẩy nó vào
    giữa chuỗi, nếu không sẽ thay đổi hành vi model một cách âm thầm."""
    assert prompts.SYSTEM_PROMPT.endswith(" /no_think"), (
        f"SYSTEM_PROMPT phải kết thúc bằng ' /no_think' để tắt suy luận; "
        f"kết thúc thực tế: {prompts.SYSTEM_PROMPT[-50:]!r}")
