# backend/src/agents/language.py
"""Nhận diện ngôn ngữ người dùng — TẤT ĐỊNH, không gọi LLM.

Chỉ hai ngôn ngữ: "vi" và "en". Mọi thứ khác rơi về "vi".

VÌ SAO KHÔNG DÙNG LLM: đây là đường nóng (mỗi lượt chat) và câu trả lời có
thể suy ra từ chính ký tự. Ngân sách xác suất để dành cho việc thật sự cần
phán đoán. Cùng lý do lớp phủ quyết của routing.decide_route là tất định.

VÌ SAO FAIL VỀ "vi": đoán nhầm sang "en" kéo câu xác nhận ghi qua một lượt
dịch không cần thiết (tốn tiền + thêm một chỗ có thể sai); đoán nhầm sang
"vi" chỉ giữ nguyên đúng hành vi hôm nay.
"""
import re

VI = "vi"
EN = "en"

# Ký tự CHỈ tiếng Việt mới có (đủ dấu thanh + nguyên âm riêng). Chỉ cần MỘT
# ký tự trong nhóm này là chắc chắn tiếng Việt.
_VI_CHARS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")

# Hư từ tiếng Anh — cần ít nhất một để dám kết luận "en". Không có nghĩa là
# tiếng Việt; nghĩa là KHÔNG ĐỦ TÍN HIỆU, và không đủ thì về "vi".
_EN_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
    "show", "me", "my", "what", "which", "who", "when", "where", "how",
    "for", "of", "to", "in", "on", "and", "or", "with", "please", "can",
    "could", "would", "should", "list", "give", "create", "receive",
    "confirm", "order", "invoice", "customer", "supplier", "details",
})

_WORD = re.compile(r"[a-z]+")


def detect_lang(text) -> str:
    """"vi" | "en". Không bao giờ ném; đầu vào rỗng/None → "vi"."""
    s = (text or "").strip()
    if not s:
        return VI
    if _VI_CHARS.search(s.lower()):
        return VI
    words = set(_WORD.findall(s.lower()))
    return EN if words & _EN_WORDS else VI
