# backend/src/agents/history.py
"""Đọc ngữ cảnh hội thoại cho tầng truy xuất.

VÌ SAO TỒN TẠI. `rag_node` và `gather_docs` đều lấy DUY NHẤT tin nhắn người
dùng cuối cùng làm truy vấn, nên một câu hỏi nối tiếp rút gọn đi vào
`retrieve()` trần trụi. Đo trên bộ eval `multiturn` (2026-08-20):

    recall@6   0,7500 (không ngữ cảnh — hành vi cũ)  →  1,0000 (có ngữ cảnh)
    mrr        0,7271                                →  0,9375

Ca khắc nghiệt nhất — "trong bao lâu?", không còn một từ nội dung nào — biến
mất khỏi cả pool 20 khi thiếu ngữ cảnh, lên hạng 1 khi có.
"""


def previous_user_turn(messages) -> str:
    """Nội dung lượt hỏi NGƯỜI DÙNG liền trước lượt hiện tại. "" nếu chưa có.

    Chỉ lấy MỘT lượt, không phải N: đó là cấu hình đã đo. Nhiều lượt hơn nghĩa
    là nhiều ứng viên hơn tranh 20 chỗ trong pool của `retrieve()` — chưa đo,
    và đó chính là cơ chế đã làm hỏng việc hồi sinh chân sparse (spec P0 §13).

    Chỉ lấy lượt người dùng, KHÔNG lấy câu trả lời của trợ lý: câu trả lời dài
    và mang văn phong tổng hợp, nhúng nó thành truy vấn là đưa nhiễu vào pool.

    Bỏ qua tin nhắn rỗng/toàn khoảng trắng — chúng không phải ngữ cảnh và sẽ
    làm `retrieve()` tốn một lượt embed vô ích.
    """
    seen_current = False
    for m in reversed(messages):
        if getattr(m, "type", None) != "human":
            continue
        text = (m.content or "").strip() if isinstance(m.content, str) else ""
        if not text:
            continue
        if not seen_current:
            seen_current = True      # đây là lượt HIỆN TẠI, bỏ qua
            continue
        return text
    return ""
