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
_DOC_CODE = re.compile(r"\b[A-Z]{1,4}-?[A-Z]{0,4}\d{2,}\b|"
                       r"\b[A-Z]{2,}(?:/[A-Z0-9]+)*/\d+\b",
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


async def load_active_facts(pool, user_id: str) -> list[tuple[str, str]]:
    """Fact đang hiệu lực của MỘT người, cũ trước mới sau.

    KHÔNG có đường nào bỏ điều kiện user_id — ký ức riêng tư tuyệt đối theo
    người (spec §4).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT fact_key, fact_value FROM user_memory "
            "WHERE user_id = %s AND superseded_by IS NULL ORDER BY id",
            (user_id,))
        return [(row[0], row[1]) for row in await cur.fetchall()]


async def save_fact(pool, user_id: str, key: str, value: str,
                    thread_id: str | None) -> None:
    """Chèn fact mới và supersede mọi bản cũ CÙNG key. Không bao giờ UPDATE giá trị.

    Vượt MEMORY_CAP thì supersede fact CŨ NHẤT — không xoá, nên vẫn truy lại được.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO user_memory (user_id, fact_key, fact_value, thread_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, key, value, thread_id))
        new_id = (await cur.fetchone())[0]
        await conn.execute(
            "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
            "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
            "AND id <> %s",
            (new_id, user_id, key, new_id))
        await conn.execute(
            "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
            "WHERE id IN (SELECT id FROM user_memory "
            "             WHERE user_id = %s AND superseded_by IS NULL "
            "             ORDER BY id DESC OFFSET %s)",
            (new_id, user_id, MEMORY_CAP))


async def forget_fact(pool, user_id: str, key: str) -> bool:
    """Supersede fact đang hiệu lực của key này. True nếu có gỡ được cái nào.

    KHÔNG DELETE: "quên" với người dùng là "không còn áp dụng", còn vệt kiểm
    toán thì giữ nguyên.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE user_memory SET superseded_at = now() "
            "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
            "RETURNING id",
            (user_id, key))
        rows = await cur.fetchall()
        if not rows:
            return False
        await conn.execute(
            "UPDATE user_memory SET superseded_by = id "
            "WHERE id = ANY(%s)", ([r[0] for r in rows],))
        return True
