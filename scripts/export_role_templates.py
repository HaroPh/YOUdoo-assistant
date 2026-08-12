# scripts/export_role_templates.py
"""In ra biến môi trường giới hạn phạm vi mail cho MỘT vai.

Dùng bởi start-dev.ps1 để cấu hình từng tiến trình MCP. Xuất CẢ HAI biến vì
cả hai suy từ cùng một phép ghép roles.py × EmailCfg — tách làm hai script
là tạo cơ hội cho chúng lệch nhau.

Vai admin (unrestricted, templates_for_role trả None) in ra giá trị RỖNG:
env rỗng = không giới hạn, đúng hợp đồng phía MCP.

VAI BỊ GIỚI HẠN NHƯNG KHÔNG CÓ COORDINATOR MAIL NÀO (templates_for_role trả
frozenset RỖNG, không phải None) là MỘT TRẠNG THÁI KHÁC — hợp đồng env hiện
tại (rỗng = không giới hạn) KHÔNG có cách biểu diễn "giới hạn về 0" mà không
đụng đúng chuỗi rỗng đã có nghĩa khác. In rỗng ở đây sẽ ÂM THẦM cấp quyền VÔ
HẠN cho một vai lẽ ra phải bị cấm tuyệt đối — leo thang đặc quyền im lặng.
Script DỪNG HẲN (exit non-zero) ở trường hợp này thay vì đoán, biến lỗi cấu
hình thành lỗi to tiếng ngay tại nơi duy nhất nó có thể phát sinh.

MỖI BIẾN LUÔN ĐÚNG MỘT DÒNG "KEY=value" (hợp đồng phía Task 5: parse theo
dòng, dòng không có "=" bị bỏ qua): nhiều tên template được nối bằng NEWLINE
THẬT rồi ESCAPE thành hai ký tự '\\n' (backslash + n) trước khi in — newline
thật bên trong value sẽ vỡ hợp đồng "2 dòng" ngay khi vai có ≥2 template.
Phía gọi (start-dev.ps1, Task 5) phải UNESCAPE '\\n' về lại newline thật
trước khi gán biến môi trường.

Chạy: python scripts/export_role_templates.py warehouse
Ra:   MCP_ALLOWED_TEMPLATES=Shipping: Send by Email
      MCP_ALLOWED_MAIL_MODELS=stock.picking
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.agents import roles                      # noqa: E402
from src.agents import mail_write                 # noqa: E402

# Ngăn cách LOGIC giữa nhiều giá trị bằng NEWLINE, không phải dấu phẩy: tên
# template Odoo có thể chứa dấu phẩy (vd "Invoice: Sending, Reminder"), tách
# bằng phẩy sẽ vỡ âm thầm. Newline thật này bị ESCAPE thành '\n' hai ký tự
# trước khi in — xem docstring module.
SEP = "\n"


def _dong_env(khoa: str, values, ten_vai: str) -> str:
    """Dựng đúng MỘT dòng "khoa=value" cho một biến env.

    values là None (admin, không giới hạn — xem templates_for_role/
    mail_models_for_role trong mail_write.py) → value RỖNG.
    values là frozenset RỖNG (vai bị giới hạn nhưng không có coordinator mail
    nào) là trạng thái hợp đồng env hiện tại không biểu diễn được — dừng hẳn
    thay vì im lặng cấp quyền vô hạn (xem docstring module)."""
    if values is None:
        return f"{khoa}="
    if not values:
        sys.exit(
            f"Vai {ten_vai!r} không được cấp coordinator mail nào — hợp đồng "
            f"env hiện tại (rỗng = không giới hạn) không có cách biểu diễn "
            f"'giới hạn về 0' cho {khoa} mà không bị hiểu nhầm thành không "
            f"giới hạn. Dừng lại thay vì cấp quyền vô hạn ngoài ý muốn.")
    # Nối bằng newline THẬT (phân định logic giữa các giá trị), rồi escape
    # thành '\n' hai ký tự để cả dòng vẫn là MỘT dòng duy nhất khi in ra.
    raw = SEP.join(sorted(values))
    return f"{khoa}=" + raw.replace("\n", "\\n")


def main():
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: export_role_templates.py <role>")
    ten_vai = sys.argv[1]
    profile = roles.load_profile()
    if ten_vai not in profile:
        sys.exit(f"Vai không có trong profile: {ten_vai!r} "
                 f"(có: {', '.join(sorted(profile))})")
    cfg = profile[ten_vai]

    tpl = mail_write.templates_for_role(cfg)
    mod = mail_write.mail_models_for_role(cfg)
    # Dựng CẢ HAI dòng trước khi in bất cứ gì: nếu một trong hai kích hoạt
    # sys.exit (trạng thái "giới hạn về 0"), không được để lại output nửa
    # chừng (dòng đầu đã in nhưng dòng sau thì không).
    dong_template = _dong_env("MCP_ALLOWED_TEMPLATES", tpl, ten_vai)
    dong_model = _dong_env("MCP_ALLOWED_MAIL_MODELS", mod, ten_vai)
    print(dong_template)
    print(dong_model)


if __name__ == "__main__":
    main()
