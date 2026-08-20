"""Ký ức xuyên phiên — tầng fact bền (L2). Spec 2026-08-19.

CHỈ giữ thứ Odoo KHÔNG chứa: sở thích tương tác và từ vựng riêng. Sự thật
nghiệp vụ đã ở Odoo và truy vấn được; chép sang đây là tạo nguồn sự thật thứ
hai sẽ trôi lệch khỏi bản ghi thật.

APPEND-ONLY: mọi thay đổi là chèn dòng mới + đánh dấu dòng cũ superseded.
Nhờ vậy ký ức sai luôn gỡ được và vẫn còn vệt kiểm toán.
"""
import re
import unicodedata

# Trần fact đang hiệu lực mỗi người. Vượt trần thì supersede cái CŨ NHẤT —
# không mất gì vì bảng append-only.
MEMORY_CAP = 50

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_key(raw: str) -> str:
    """Chuẩn hoá key: chữ thường, BỎ DẤU, mọi thứ không phải chữ/số → gạch dưới.

    BỎ DẤU là bắt buộc, không phải tuỳ chọn: người Việt gõ cả có dấu lẫn không
    dấu (đợt đa ngôn ngữ 2026-08-18 đo được đây là kiểu gõ phổ biến thật). Giữ
    dấu thì "kho_chính" và "kho_chinh" thành hai fact khác nhau và cơ chế
    supersede IM LẶNG ngừng hoạt động.
    """
    text = unicodedata.normalize("NFD", (raw or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return _NON_WORD.sub("_", text).strip("_")


# Mã chứng từ CỤ THỂ — hai hình dạng thật trong repo này:
#   - chữ+số liền: P00003, S00012, E-COM07
#   - có gạch chéo VÀ có chữ số: INV/2026/00004, WH/OUT/00001
# Ranh giới cố ý: "WH/Stock" (không chữ số) là tên KHO — một quy ước, cho qua.
# "WH/OUT/00001" (có chữ số) là MỘT phiếu cụ thể — chặn.
_DOC_CODE = re.compile(r"\b[A-Z]{1,4}\d{3,}\b|\b[A-Z]{2,}(?:/[A-Z0-9]+)*/\d+\b",
                       re.IGNORECASE)


def is_document_code(value: str) -> bool:
    """Fact có trỏ tới MỘT bản ghi ERP cụ thể không?

    Đúng khuôn "model đề xuất, code phủ quyết" của decide_route /
    verify_erp_grounding / facts_survived. Ký ức là nơi giữ quy ước, không phải
    nơi giữ bản ghi — bản ghi đã ở Odoo và truy vấn được.
    """
    return bool(_DOC_CODE.search(value or ""))


def render_memory_block(facts: list[tuple[str, str]]) -> str:
    """Khối ký ức ghép vào ĐẦU system prompt. Rỗng khi không có fact nào.

    Đặt TRƯỚC prompt gốc (caller làm) để chỉ thị định dạng / '/no_think' của
    prompt gốc giữ vị trí cuối — cùng lý do render_working_context làm vậy.
    """
    if not facts:
        return ""
    lines = "\n".join(f"- {key} = {value}" for key, value in facts)
    return ("Ghi nhớ về người dùng này (họ đã tự khai ở phiên trước):\n"
            f"{lines}\n"
            "Áp dụng khi phù hợp. Nếu yêu cầu hiện tại mâu thuẫn với ghi nhớ, "
            "ưu tiên yêu cầu hiện tại.")
