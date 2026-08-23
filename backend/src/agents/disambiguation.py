# backend/src/agents/disambiguation.py
"""Deterministic parser for a user's reply to a disambiguation interrupt.

The user is shown a numbered candidate list ("1. Azur Interior  2. Azur
Furniture") and replies with an index or a name. This maps the reply to a
candidate id, or None when it cannot be resolved cleanly (the caller re-asks).
No LLM — a write flow must not guess which entity was meant.

The id's type is whatever the caller put in `options`: an ERP record id (int)
for entity pickers, but a plain string for `clarify_depth`, whose ids are the
depth values ("full_sop"/"one_step") that flow straight into state."""


# Chữ chỉ thứ tự trong tiếng Việt → chỉ số 1-based. "hai" và "nhì" cùng là 2.
# Chỉ tới 5 vì danh sách gợi ý của hệ này cắt ở 5 mục (xem nút hỏi lại).
_CHU_THU_TU = {
    "nhất": 1, "đầu": 1, "đầu tiên": 1, "một": 1,
    "nhì": 2, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5,
}
_CHU_CUOI = ("cuối", "cuối cùng", "chót")

_SO = __import__("re").compile(r"\d+")


# Từ chỉ đơn vị đứng sau số lượng. Bóc chúng để phần còn lại là TÊN.
_TU_DON_VI = ("cái", "chiếc", "con", "bộ", "chục", "hộp", "thùng", "kg", "m")


def _bo_so_luong_dau_cau(s: str) -> str:
    """"2 cái bàn học sinh" → "bàn học sinh". Không có số lượng thì trả nguyên."""
    tu = s.split()
    i = 0
    if i < len(tu) and tu[i].isdigit():
        i += 1
        if i < len(tu) and tu[i] in _TU_DON_VI:
            i += 1
        return " ".join(tu[i:]).strip()
    return s


def _chi_so_tu_cau(s: str, n: int) -> int | None:
    """Chỉ số 1-based suy từ một CÂU, hoặc None nếu không suy được chắc chắn.

    Sinh ra từ một ngõ cụt đo được (2026-08-23): trợ lý đưa danh sách đánh số,
    người dùng gõ "cái thứ 2", parse trả None, nút hỏi LẠI y nguyên danh sách
    trong 0,2s — trông như treo, và người dùng không có cách nào biết phải gõ
    gì. Bản cũ chỉ nhận số TRẦN ("2"), tức chỉ nhận đúng một cách gõ.

    KHÔNG đoán khi còn phân vân: nhiều số trong câu ("1 hoặc 2") trả None để
    nút hỏi lại — chọn bừa trong một luồng GHI thì tệ hơn hỏi thêm một câu.
    """
    if any(t in s for t in _CHU_CUOI):
        return n
    for chu, i in _CHU_THU_TU.items():
        # Ranh giới từ: "tư" không được khớp trong "tủ", "năm" không khớp
        # trong "năm nay". Dùng tách theo khoảng trắng thay vì regex unicode.
        if chu in s.split() or s.endswith(" " + chu):
            return i
    so = _SO.findall(s)
    if len(so) == 1:                    # đúng MỘT số ⇒ mới dám hiểu là lựa chọn
        return int(so[0])
    return None


def parse_selection(reply: str, options: list[dict]) -> int | str | None:
    s = (reply or "").strip().lower()
    if not s or not options:
        return None
    if s.isdigit():
        i = int(s)
        return options[i - 1]["id"] if 1 <= i <= len(options) else None

    # TÊN chạy TRƯỚC số thứ tự (quyết định 2026-08-23): "2 cái bàn học sinh"
    # vừa có số vừa có tên, và người dùng gần như chắc chắn đang nêu tên kèm
    # số lượng chứ không chọn mục 2.
    exact = [o for o in options if (o["name"] or "").strip().lower() == s]
    if len(exact) == 1:
        return exact[0]["id"]
    subs = [o for o in options if s in (o["name"] or "").strip().lower()]
    if len(subs) == 1:
        return subs[0]["id"]
    # Bóc phần SỐ LƯỢNG ở đầu rồi khớp lại: "2 cái bàn học sinh" → "bàn học
    # sinh". Người dùng nêu tên hiếm khi gõ trọn tên trong danh sách (tên thật
    # là "Bàn học sinh gỗ MDF"), nên phép khớp phải chạy trên phần CÒN LẠI của
    # câu, không phải trên cả câu.
    con_lai = _bo_so_luong_dau_cau(s)
    if con_lai and con_lai != s:
        subs2 = [o for o in options
                 if con_lai in (o["name"] or "").strip().lower()]
        if len(subs2) == 1:
            return subs2[0]["id"]

    i = _chi_so_tu_cau(s, len(options))
    if i is not None and 1 <= i <= len(options):
        return options[i - 1]["id"]
    return None
