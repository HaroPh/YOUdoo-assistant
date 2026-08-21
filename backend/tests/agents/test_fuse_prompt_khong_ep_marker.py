# backend/tests/agents/test_fuse_prompt_khong_ep_marker.py
"""FUSE_PROMPT KHÔNG được ép model phải phát marker ĐỀ_XUẤT_GHI.

VÌ SAO CÓ TEST NÀY. Ngày 2026-08-21 tôi thêm vào FUSE_PROMPT một câu ràng:
"Dòng ĐỀ_XUẤT_GHI là HỢP ĐỒNG MÁY-ĐỌC bắt buộc: đã đề xuất thao tác ghi thì PHẢI
có nó...". Nó được merge vào production rồi gỡ ra trong cùng ngày.

Lúc gỡ, lý do mới chỉ là "căn cứ nhận nó đã mất hiệu lực". Đo lại sau đó thì nó
NGUY HIỂM THẬT, tất định 3/3 lượt: với câu ràng đó cộng một fact ép định dạng,
model trả lời "Tôi đã ghi nhận... và THỰC HIỆN KHÓA CÔNG NỢ đối với Gemini
Furniture TRÊN HỆ THỐNG" — trong khi fuse_answer KHÔNG có tool nào và không thao
tác gì cả. Không có câu ràng thì 0/9 lượt (ba chân ký ức).

CƠ CHẾ: ép model tuân thủ một hợp đồng máy-đọc khiến nó BỊA RA chính sự kiện mà
hợp đồng đó mô tả. Nó không đề xuất nhiều hơn — nó kể rằng đã làm, để câu chuyện
khớp với marker.

Hậu quả nếu lọt ra production: người dùng tin một thao tác ghi đã xong trong khi
KHÔNG CÓ GÌ xảy ra, và không có cách nào biết. Đó là hỏng nặng hơn mọi thứ khác
tìm được trong đợt điều tra ký ức.

Chi tiết + số đo: docs/superpowers/specs/2026-08-20-memory-synthesis-eval.md §14.
"""
from src.agents.prompts import FUSE_PROMPT, SYSTEM_PROMPT


def test_fuse_prompt_khong_chua_cau_ep_marker():
    for cum in ("HỢP ĐỒNG MÁY-ĐỌC", "PHẢI có nó"):
        assert cum not in FUSE_PROMPT, (
            f"FUSE_PROMPT chứa lại câu ép marker ({cum!r}). Câu đó đã được đo là "
            f"khiến model BỊA rằng nó đã thực hiện thao tác ghi (3/3 lượt). Xem "
            f"docstring tệp này trước khi thêm lại.")


def test_system_prompt_cung_khong_chua():
    """SYSTEM_PROMPT mang CÙNG hướng dẫn marker và cũng có khối ký ức đứng
    trước. Nó chưa bao giờ được đo với câu ràng đó, nên càng không được thêm
    vào — hại đã biết ở một đường, chưa biết ở đường kia."""
    for cum in ("HỢP ĐỒNG MÁY-ĐỌC", "PHẢI có nó"):
        assert cum not in SYSTEM_PROMPT
