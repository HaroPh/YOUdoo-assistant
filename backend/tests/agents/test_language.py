# backend/tests/agents/test_language.py
"""Nhận diện ngôn ngữ — TẤT ĐỊNH, không LLM.

Chỉ dùng cho tầng điều phối ghi (chuỗi đi thẳng ra người dùng). Tầng prompt
KHÔNG dùng hàm này: LLM tự nhìn tin nhắn, đo được 2026-08-18.
"""
import pytest

from src.agents.language import EN, VI, detect_lang


@pytest.mark.parametrize("text", [
    "cho tôi xem chi tiết đơn mua P00003",
    "nhận hàng cho đơn mua P00003",
    "chào bạn",
])
def test_nhan_ra_tieng_viet(text):
    assert detect_lang(text) == VI


@pytest.mark.parametrize("text", [
    "show me the details of purchase order P00003",
    "which invoices are overdue?",
    "receive the goods for purchase order P00003",
])
def test_nhan_ra_tieng_anh(text):
    assert detect_lang(text) == EN


def test_cau_tieng_anh_co_ten_rieng_tieng_viet_thi_ve_vi():
    """FAIL AN TOÀN: có dấu tiếng Việt ⇒ vi, kể cả khi phần còn lại là tiếng
    Anh. Đoán nhầm sang `en` sẽ kéo câu xác nhận ghi qua một lượt dịch không
    cần thiết; đoán nhầm sang `vi` chỉ giữ nguyên hành vi hôm nay."""
    assert detect_lang("create a quotation for Cửa hàng ABC") == VI


def test_ten_rieng_viet_hoa_co_dau_trong_cau_tieng_anh():
    """Hồi quy: tên riêng tiếng Việt với ký tự HOA có dấu thanh (Á, À, Ả, ...).
    Trước đây kiểm tra _VI_CHARS trên chuỗi gốc (không lowercase), nên chỉ bắt
    được ký tự HOA KHÔNG dấu (ĂÂĐÊÔƠƯ) nhưng bỏ qua HOA+DẤU (Á, À, ...).
    Sửa: chạy kiểm tra trên chuỗi đã lowercase."""
    assert detect_lang("Ánh is my colleague") == VI


@pytest.mark.parametrize("text", ["", "   ", "1", "ok", None])
def test_khong_du_tin_hieu_thi_ve_vi(text):
    """Lượt trả lời xác nhận thường chỉ là "1"/"ok" — quá ngắn để nhận diện.
    Rơi về vi là chiều an toàn; Task 4 quét TOÀN BỘ lịch sử người dùng nên
    lượt đó vẫn ra đúng ngôn ngữ khi client gửi đủ lịch sử."""
    assert detect_lang(text) == VI


def test_khong_dau_khong_du_hu_tu_thi_ve_vi():
    # Diacritic-free Vietnamese with exactly ONE incidental EN-word collision
    # must NOT trigger English — this was the bug (single-word false positive).
    assert detect_lang("toi can bao gia cho khach hang Azure") == "vi"
    assert detect_lang("kiem tra ton kho san pham Cabinet A") == "vi"
    assert detect_lang("lam on kiem tra hoa don INV/2026/00004") == "vi"
    assert detect_lang("cam on ban") == "vi"


def test_hai_hu_tu_tieng_anh_van_ve_en():
    # Real English with >=2 function words must still detect correctly.
    assert detect_lang("show me the details of purchase order P00003") == "en"
    assert detect_lang("which invoices are overdue?") == "en"
    assert detect_lang("receive the goods for purchase order P00003") == "en"
