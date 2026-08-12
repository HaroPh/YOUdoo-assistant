"""Script tạo tài khoản phải sinh luật mail.template theo vai từ CÙNG nguồn
suy ra mà tiến trình MCP dùng — không phải một danh sách viết tay thứ hai.

Test đọc NGUỒN script, không chạy nó: chạy script là chạm Odoo sống, việc
đó do controller làm."""
import pathlib

SCRIPT = (pathlib.Path(__file__).resolve().parents[3]
          / "scripts" / "odoo_setup_ai_accounts.py")


def test_khong_viet_tay_ten_template():
    """Tên template chỉ được xuất hiện qua templates_for_role, không hardcode."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "templates_for_role" in src, (
        "luật mail.template phải suy từ mail_write.templates_for_role")
    for ten in ("Shipping: Send by Email", "Invoice: Sending",
                "Sales: Order Confirmation"):
        assert ten not in src, f"tên template {ten!r} bị viết cứng trong script"


def test_co_hai_nhom_mail_theo_vai():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "Youdoo AI / Mail Warehouse" in src
    assert "Youdoo AI / Mail Accounting" in src


def test_khong_tao_nhom_han_che_cho_admin():
    """ir.rule theo nhóm chỉ áp lên thành viên — admin không thuộc nhóm nào
    là tự do đọc. Tạo nhóm 'cho phép tất cả' cho admin là thừa và dễ hiểu sai
    thành 'admin cũng bị giới hạn'."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "Youdoo AI / Mail Admin" not in src


def test_luat_chi_gioi_han_doc():
    """perm_write/create/unlink trên mail.template đã có luật Odoo gốc quản;
    thêm luật ghi ở đây là giẫm lên chúng."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "perm_read" in src
