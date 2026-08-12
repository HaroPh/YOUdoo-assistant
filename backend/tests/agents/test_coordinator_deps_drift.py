"""Mọi tool MCP mà node coordinator tra bằng `by_name.get("...")` phải là
tên một coordinator, hoặc được khai trong Spec.deps.

Đây là chốt drift cho hạng lỗi đã lặp NĂM lần trong mạch phân quyền: một
danh sách khai báo thiếu âm thầm. Lần gần nhất (2026-08-12) làm mọi tool
mail chết với vai non-admin trong khi 1254 test vẫn xanh.

GIỚI HẠN CỐ Ý — nêu thẳng để người sau không tưởng test này phủ hết: nó chỉ
thấy được literal chuỗi. Bốn chỗ tra bằng biến nằm NGOÀI tầm:
  - nodes.py `by_name.get(name)` — tên động, đúng thiết kế
  - edit_order.py `by_name.get(FLAG_TOOL)` — hằng module
  - edit_order.py / create_order.py `by_name.get(cfg.tool_name)` — trùng tên
    coordinator nên vô hại
FLAG_TOOL hiện là 'flag_order_for_review', có trong _WH_OWN của roles.py, nên
hôm nay không sao. Đổi nó thành một tool ngoài roles.py thì test này KHÔNG
bắt được."""
import pathlib
import re

from src.agents.write_registry import WRITE_COORDINATORS

AGENTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "agents"
MAU = re.compile(r"""by_name\.get\(\s*["']([^"']+)["']\s*\)""")


def test_moi_literal_by_name_deu_da_duoc_khai():
    cho_phep = set(WRITE_COORDINATORS)
    for spec in WRITE_COORDINATORS.values():
        cho_phep |= set(spec.deps)

    vi_pham = []
    for f in sorted(AGENTS_DIR.glob("*.py")):
        for so_dong, dong in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for ten in MAU.findall(dong):
                if ten not in cho_phep:
                    vi_pham.append(f"{f.name}:{so_dong} tra {ten!r}")

    assert not vi_pham, (
        "tool MCP tra trong node coordinator phải là tên coordinator hoặc "
        "được khai ở Spec.deps — nếu không, bộ lọc theo vai sẽ cắt mất nó và "
        "node trả lỗi 'không khả dụng' với vai non-admin:\n"
        + "\n".join(vi_pham))


def test_mau_regex_that_su_bat_duoc_dong_that():
    """Đối chứng: nếu regex hỏng, test trên sẽ xanh giả (không tìm thấy gì
    thì không có vi phạm). Khẳng định nó thấy được ít nhất 3 tool mail đã
    biết chắc là có trong mail_write.py."""
    mail_py = (AGENTS_DIR / "mail_write.py").read_text(encoding="utf-8")
    tim_duoc = set(MAU.findall(mail_py))
    assert {"preview_template_email", "send_prepared_email",
            "discard_prepared_email"} <= tim_duoc
