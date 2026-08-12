"""Giới hạn phạm vi mail theo vai — cưỡng chế TRONG tiến trình MCP.

Mỗi tiến trình MCP chỉ nắm credential của một vai (:8003 admin / :8004 kho /
:8005 kế toán). Bộ lọc tool ở backend là lớp UX; nó KHÔNG với tới đường gọi
thẳng vào cổng MCP. Module này là lớp chặn cho đường đó.

CỐ TÌNH không import server/odoo_call: giữ thuần để test được trực tiếp, và
để nó không bao giờ trở thành một đường ra Odoo mới.

Giá trị env ngăn cách bằng NEWLINE, không phải dấu phẩy — tên template Odoo
có thể chứa dấu phẩy.

Env rỗng/không đặt = KHÔNG giới hạn. Đó là hợp đồng cho tiến trình admin và
cho mọi test MCP hiện có (chúng không đặt biến nào)."""

ALLOWED_TEMPLATES_ENV = "MCP_ALLOWED_TEMPLATES"
ALLOWED_MAIL_MODELS_ENV = "MCP_ALLOWED_MAIL_MODELS"


def parse(raw):
    """Chuỗi env -> set. Bỏ dòng rỗng và khoảng trắng thừa hai đầu."""
    if not raw:
        return set()
    return {d.strip() for d in raw.split("\n") if d.strip()}


def allowed(value, raw):
    """True nếu `value` được phép. Danh sách rỗng = không giới hạn."""
    allowed_set = parse(raw)
    if not allowed_set:
        return True
    return value in allowed_set
