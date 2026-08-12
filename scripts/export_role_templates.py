# scripts/export_role_templates.py
"""In ra biến môi trường giới hạn phạm vi mail cho MỘT vai.

Dùng bởi start-dev.ps1 để cấu hình từng tiến trình MCP. Xuất CẢ HAI biến vì
cả hai suy từ cùng một phép ghép roles.py × EmailCfg — tách làm hai script
là tạo cơ hội cho chúng lệch nhau.

Vai admin (unrestricted) in ra giá trị RỖNG: env rỗng = không giới hạn, đúng
hợp đồng phía MCP.

Chạy: python scripts/export_role_templates.py warehouse
Ra:   MCP_ALLOWED_TEMPLATES=Shipping: Send by Email
      MCP_ALLOWED_MAIL_MODELS=stock.picking
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.agents import roles                      # noqa: E402
from src.agents import mail_write                 # noqa: E402

# Ngăn cách bằng NEWLINE, không phải dấu phẩy: tên template Odoo có thể chứa
# dấu phẩy (vd "Invoice: Sending, Reminder"), tách bằng phẩy sẽ vỡ âm thầm.
SEP = "\n"


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
    # None (admin) → chuỗi rỗng, đúng hợp đồng "env rỗng = không giới hạn".
    print("MCP_ALLOWED_TEMPLATES=" + (SEP.join(sorted(tpl)) if tpl else ""))
    print("MCP_ALLOWED_MAIL_MODELS=" + (SEP.join(sorted(mod)) if mod else ""))


if __name__ == "__main__":
    main()
