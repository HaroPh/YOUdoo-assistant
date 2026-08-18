"""Dịch chuỗi ĐIỀU PHỐI sang ngôn ngữ người dùng, có lớp phủ quyết tất định.

VÌ SAO CẦN: chuỗi ở tầng điều phối ghi (create_order._msg, question của
interrupt, thông báo lỗi) đi THẲNG ra người dùng — không LLM nào đứng giữa để
viết lại, nên khối LANGUAGE_RULE ở prompt không chạm tới được. Đo 2026-08-18
qua HTTP thật: hỏi tiếng Anh vẫn nhận câu xác nhận ghi bằng tiếng Việt.

VÌ SAO CÓ LỚP PHỦ QUYẾT: người dùng đọc chính câu này rồi DUYỆT một thao tác
ghi thật. Một bản dịch đổi "255" thành "265" hay đánh rơi mã đơn là đổi thứ
người ta đang duyệt. Model được phép đổi CÂU CHỮ, không được phép đổi SỰ VIỆC
— cùng khuôn "lớp xác suất + lớp phủ quyết tất định" của routing.decide_route
và erp_grounding.verify_erp_grounding.

Không bao giờ ném: mọi lỗi → bản gốc tiếng Việt.
"""
import re

# Ký tự chỉ tiếng Việt mới có — dùng để bỏ qua văn bản đã là tiếng Anh.
_VI_CHARS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")

# Hư từ tiếng Việt phổ biến — dùng để phân biệt "câu tiếng Việt thật" với
# "câu tiếng Anh có trích dẫn/chân trang mang dấu tiếng Việt" (ví dụ chân
# trang "📄 Nguồn:" của build_citations(), hay tên đối tác/sản phẩm tiếng
# Việt). Chỉ có dấu KHÔNG đủ để kết luận cần dịch — cùng bài học đã áp dụng
# cho looks_vietnamese() ở evals/run_eval.py, viết lại tự chứa ở đây để
# không đảo hướng phụ thuộc sản phẩm→eval.
_VI_WORDS = re.compile(
    r"\b(của|và|là|cho|không|được|với|các|những|này|tôi|bạn|mình|hãy|"
    r"nếu|theo|khi|đã|sẽ|có thể|vui lòng|từ)\b", re.IGNORECASE)


def _has_vietnamese_prose(text: str) -> bool:
    """Văn bản có PHẢI câu tiếng Việt thật không (không chỉ mang dấu)."""
    return bool(_VI_CHARS.search(text) and _VI_WORDS.search(text))

# SỰ VIỆC không được phép đổi:
#   - ngày dạng D/M/YYYY hoặc YYYY-MM-DD là MỘT token nguyên (không tách rời
#     ngày/tháng/năm)
#   - mã chứng từ có gạch chéo: WH/OUT/00001, INV/2026/00004
#   - mã dạng chữ+số: P00003, S00012, E-COM07, F-COM07
#   - mọi cụm chữ số: 255, 25.5, 10.0
# Cố ý RỘNG: thà bắt nhầm một token vô hại (bản dịch giữ nguyên nó thì vẫn
# qua) còn hơn bỏ sót một con số người dùng sắp duyệt.
#
# LƯU Ý GIỚI HẠN: cổng kiểm KHÔNG bắt được sự hoán đổi giữa hai số độc lập
# không phải ngày (ví dụ: số lượng vs. đơn giá), vì dùng set-based comparison
# thay vì paired-label checking. Rủi ro này được chấp nhận vì: (a) localize()
# chỉ gọi khi lang=="en" VÀ text chứa dấu tiếng Việt (hẹp); (b) thất bại luôn
# → lùi về Việt, không bao giờ "hiển thị bản dịch chưa đọc"; (c) người dùng
# vẫn đọc trước duyệt; (d) trước đây không có dịch nên localize() là thêm-lớp-
# an-toàn chứ không hồi quy.
_FACT = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Z]{2,}/[A-Z0-9/]+|"
    r"[A-Za-z]+(?:-[A-Za-z]+)*-?\d[\w/-]*|\d[\d.,]*\d|\d")

TRANSLATE_PROMPT = (
    "Translate the message below into {target}. Keep EVERY number, amount, "
    "reference code and tool name EXACTLY as they appear — do not reformat, "
    "round, or re-order them. Keep proper nouns (product, partner, document "
    "names) unchanged. Keep the line structure. Reply with the translation "
    "only, no preamble.\n\n{text}")

_TARGET = {"en": "English", "vi": "Vietnamese"}


def extract_facts(text: str) -> set[str]:
    """Các token KHÔNG được phép đổi trong bản dịch."""
    return set(_FACT.findall(text or ""))


def facts_survived(src: str, out: str) -> bool:
    """Mọi sự việc của bản gốc còn nguyên trong bản dịch?

    Chỉ kiểm CHIỀU MẤT/ĐỔI. Bản dịch thêm token mới (ví dụ "1." của danh sách)
    là vô hại và không bị chặn — chặn cả chiều đó sẽ làm cổng bắn giả liên tục
    và người ta sẽ tắt nó.
    """
    if not (out or "").strip():
        return False
    return extract_facts(src) <= extract_facts(out)


async def localize(text: str, lang: str, llm) -> str:
    """Bản dịch nếu ĐẠT lớp phủ quyết, ngược lại bản gốc. Không bao giờ ném."""
    if not text or lang not in _TARGET or lang == "vi":
        return text
    if not _has_vietnamese_prose(text):
        return text          # đã là tiếng Anh (hoặc chỉ mang dấu qua trích dẫn/tên riêng) — không dịch lại
    try:
        from langchain_core.messages import HumanMessage
        prompt = TRANSLATE_PROMPT.format(target=_TARGET[lang], text=text)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        out = (getattr(response, "content", "") or "").strip()
    except Exception:                                       # noqa: BLE001
        return text
    return out if facts_survived(text, out) else text
