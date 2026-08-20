"""Ký ức xuyên phiên — tầng fact bền (L2). Spec 2026-08-19.

CHỈ giữ thứ Odoo KHÔNG chứa: sở thích tương tác và từ vựng riêng. Sự thật
nghiệp vụ đã ở Odoo và truy vấn được; chép sang đây là tạo nguồn sự thật thứ
hai sẽ trôi lệch khỏi bản ghi thật.

APPEND-ONLY: mọi thay đổi là chèn dòng mới + đánh dấu dòng cũ superseded.
Nhờ vậy ký ức sai luôn gỡ được và vẫn còn vệt kiểm toán.
"""
import re
import unicodedata

from psycopg.rows import tuple_row

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


# Mã chứng từ CỤ THỂ — ba hình dạng thật trong repo này:
#   - chữ+số liền: P00003, S00012, E-COM07
#   - có gạch chéo VÀ có chữ số: INV/2026/00004, WH/OUT/00001
#   - sổ nhật ký Odoo CÓ CHỮ SỐ ngay ở đoạn đầu: BNK1/2026/00001,
#     PBNK1/2026/00001, CSH1/2026/00007 — final review đo được đoạn đầu
#     "[A-Z]{2,}" (chỉ chữ) để lọt cả ba, vì post_invoice/register_payment
#     làm vai đọc thấy đúng những tên sổ này.
# Ranh giới cố ý: "WH/Stock" (không chữ số) là tên KHO — một quy ước, cho qua.
# "WH/OUT/00001" (có chữ số) là MỘT phiếu cụ thể — chặn.
_DOC_CODE = re.compile(r"\b[A-Z]{1,4}-?[A-Z]{0,4}\d{2,}\b|"
                       r"\b[A-Z][A-Z0-9]*(?:/[A-Z0-9]+)*/\d+\b",
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
        # Pool production dùng row_factory=dict_row (bắt buộc cho
        # AsyncPostgresSaver — xem erp_agent.py::setup). Lấy ô theo vị trí
        # (row[0]) trên dict sẽ KeyError: 0. Ép tuple_row NGAY TRÊN CURSOR để
        # hàm này đúng bất kể pool cấu hình row factory gì.
        cur = conn.cursor(row_factory=tuple_row)
        await cur.execute(
            "SELECT fact_key, fact_value FROM user_memory "
            "WHERE user_id = %s AND superseded_by IS NULL ORDER BY id",
            (user_id,))
        return [(row[0], row[1]) for row in await cur.fetchall()]


async def save_fact(pool, user_id: str, key: str, value: str,
                    thread_id: str | None) -> None:
    """Chèn fact mới và supersede mọi bản cũ CÙNG key. Không bao giờ UPDATE giá trị.

    Vượt MEMORY_CAP thì supersede fact CŨ NHẤT — không xoá, nên vẫn truy lại được.

    BA CÂU LỆNH TRONG MỘT TRANSACTION: pool production mở với autocommit=True
    (bắt buộc cho AsyncPostgresSaver — xem erp_agent.py::setup), nên KHÔNG bọc
    transaction thì mỗi câu tự commit riêng. Hỏng giữa chừng (VD sau INSERT,
    trước UPDATE supersede) để lại HAI fact cùng key cùng hiệu lực — cả hai
    cùng render vào khối ký ức mọi lượt sau, trong khi `except: continue` của
    caller (erp_agent._apply_memory_markers) nuốt lỗi, không báo gì. `async
    with conn.transaction()` của psycopg3 vẫn mở transaction thật dù pool
    autocommit=True.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = conn.cursor(row_factory=tuple_row)
            await cur.execute(
                "INSERT INTO user_memory (user_id, fact_key, fact_value, thread_id) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, key, value, thread_id))
            new_id = (await cur.fetchone())[0]
            await conn.execute(
                "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
                "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
                "AND id <> %s",
                (new_id, user_id, key, new_id))
            # AND user_id = %s dưới đây làm bất biến "không lộ ký ức sang
            # người khác" GREPPABLE thay vì chỉ ĐÚNG NHỜ id đến từ subquery
            # đã lọc user_id — an toàn hôm nay, nhưng chỉ đọc code mới thấy.
            await conn.execute(
                "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
                "WHERE user_id = %s AND id IN "
                "      (SELECT id FROM user_memory "
                "       WHERE user_id = %s AND superseded_by IS NULL "
                "       ORDER BY id DESC OFFSET %s)",
                (new_id, user_id, user_id, MEMORY_CAP))


async def forget_fact(pool, user_id: str, key: str) -> bool:
    """Supersede fact đang hiệu lực của key này. True nếu có gỡ được cái nào.

    KHÔNG DELETE: "quên" với người dùng là "không còn áp dụng", còn vệt kiểm
    toán thì giữ nguyên.

    HAI CÂU LỆNH TRONG MỘT TRANSACTION (cùng lý do save_fact ở trên): hỏng
    GIỮA hai câu để lại `superseded_at` đã đặt mà `superseded_by` còn NULL —
    fact đó vẫn hiệu lực (load_active_facts lọc theo superseded_by IS NULL),
    tức forget_fact báo True nhưng fact không hề biến mất.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = conn.cursor(row_factory=tuple_row)
            await cur.execute(
                "UPDATE user_memory SET superseded_at = now() "
                "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
                "RETURNING id",
                (user_id, key))
            rows = await cur.fetchall()
            if not rows:
                return False
            # AND user_id = %s: xem chú thích tương ứng ở save_fact.
            await conn.execute(
                "UPDATE user_memory SET superseded_by = id "
                "WHERE user_id = %s AND id = ANY(%s)",
                (user_id, [r[0] for r in rows]))
            return True


MEMORY_SAVE_MARKER = "GHI_NHỚ"
MEMORY_FORGET_MARKER = "QUÊN"

# QUÊN phải khớp ĐÚNG HOA: "quên:" là văn xuôi tiếng Việt bình thường
# ("Đừng quên: kiểm tra tồn kho..."), nên IGNORECASE ở đây sẽ CẮT CỤT câu trả
# lời thật và ghi một lệnh quên bịa. GHI_NHỚ có gạch dưới nên không phải văn
# xuôi, giữ IGNORECASE được.
_FORGET_LITERAL = f"(?-i:{MEMORY_FORGET_MARKER})"

# MỘT pattern mỗi marker. Ba tính chất, mỗi cái đóng một lỗi thật:
#   MULTILINE  — `$` khớp cuối DÒNG, không phải cuối chuỗi. Thiếu nó thì marker
#                nằm ở dòng giữa sẽ LỌT ra văn bản người dùng và mất luôn tín
#                hiệu (đúng lớp bug 2026-08-06 của ĐỀ_XUẤT_GHI).
#   non-greedy + lookahead — capture DỪNG trước marker kế tiếp, nên hai marker
#                cùng một dòng không nuốt lẫn nhau.
#   dấu ':' BẮT BUỘC — xem chú thích GIỚI HẠN bên dưới. Đây là thứ DUY NHẤT
#                phân biệt marker máy với văn xuôi tiếng Việt bình thường.
_NEXT_MARKER = rf'(?=[ \t]*(?:{MEMORY_SAVE_MARKER}|{_FORGET_LITERAL})[ \t]*:|$)'
_SAVE_RE = re.compile(
    rf'[ \t]*{MEMORY_SAVE_MARKER}[ \t]*:[ \t]*([^\n]*?){_NEXT_MARKER}',
    re.IGNORECASE | re.MULTILINE)
_FORGET_RE = re.compile(
    rf'[ \t]*{_FORGET_LITERAL}[ \t]*:[ \t]*([^\n]*?){_NEXT_MARKER}',
    re.IGNORECASE | re.MULTILINE)


def extract_memory_markers(body: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Tách marker ký ức khỏi văn bản. Người dùng KHÔNG BAO GIỜ thấy marker.

    Trả (văn bản sạch, [(key thô, value)], [key thô cần quên]). Key ở đây còn
    THÔ — caller phải gọi normalize_key(). Tách hai việc để test được riêng.

    Marker viết sai khuôn (thiếu dấu '=') bị BỎ QUA nhưng vẫn bị CẮT khỏi văn
    bản: thà mất một ghi nhớ còn hơn để lộ ký hiệu máy-đọc ra câu người dùng.

    GIỚI HẠN CÓ CHỦ ĐÍCH — dấu ':' là BẮT BUỘC: marker viết thiếu dấu hai chấm
    ("GHI_NHỚ a = b") sẽ hiện ra như văn bản thường. Đã thử làm dấu ':' tuỳ chọn
    để đóng lỗ đó và ĐO ĐƯỢC hồi quy nặng hơn nhiều: "quên" là TỪ TIẾNG VIỆT
    THẬT, nên 4/5 câu văn bình thường bị cắt nát ("Tôi quên mất rồi, xin lỗi bạn
    nhé." → người dùng chỉ còn thấy "Tôi", kèm một lệnh quên bịa). Dấu hai chấm
    là thứ duy nhất phân biệt marker máy với văn xuôi người — giữ bắt buộc.

    GIỚI HẠN THỨ HAI đã đóng (final review, trước merge): dấu ':' một mình
    KHÔNG đủ — "Đừng quên: kiểm tra tồn kho..." là văn xuôi CÓ dấu ':' thật.
    _FORGET_LITERAL tắt IGNORECASE cho riêng QUÊN nên chỉ chữ HOA đúng khuôn
    máy mới khớp; GHI_NHỚ giữ IGNORECASE vì gạch dưới đã đủ phân biệt nó khỏi
    văn xuôi.
    """
    text = body or ""
    saves: list[tuple[str, str]] = []
    forgets: list[str] = []

    for raw in _SAVE_RE.findall(text):
        key, sep, value = raw.partition("=")
        if sep and key.strip() and value.strip():
            saves.append((key.strip(), value.strip()))
    text = _SAVE_RE.sub("", text)

    for raw in _FORGET_RE.findall(text):
        if raw.strip():
            forgets.append(raw.strip())
    text = _FORGET_RE.sub("", text)

    return text.rstrip(), saves, forgets
