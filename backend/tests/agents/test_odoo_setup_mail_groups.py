"""Script tạo tài khoản phải sinh luật mail.template theo vai từ CÙNG nguồn
suy ra mà tiến trình MCP dùng — không phải một danh sách viết tay thứ hai.

Test đọc NGUỒN script, không chạy nó: chạy script là chạm Odoo sống, việc
đó do controller làm."""
import pathlib

SCRIPT = (pathlib.Path(__file__).resolve().parents[3]
          / "scripts" / "odoo_setup_ai_accounts.py")


def _khoi_luat_mail_template(src):
    """Cắt riêng khối dựng luật ir.rule trên mail.template (giữa comment mở
    đầu "Backstop Odoo" và nhóm Read Only kế tiếp) để soi hardcode. Không soi
    cả file: READ_MODELS ở trên chứa "account.move"/"stock.picking" một cách
    hợp lệ, cho mục đích khác (ir.model.access, không phải domain ir.rule)."""
    start = src.index("# Backstop Odoo cho tầng mail")
    end = src.index('g_ro = ensure_group("Youdoo AI / Read Only")')
    assert start < end
    return src[start:end]


def test_khong_viet_tay_ten_template():
    """Domain ir.rule chỉ được suy từ mail_write.mail_models_for_role, không
    viết tay tên template lẫn tên model."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "mail_models_for_role" in src, (
        "luật mail.template phải suy từ mail_write.mail_models_for_role")
    khoi = _khoi_luat_mail_template(src)
    for ten in ("Shipping: Send by Email", "Invoice: Sending",
                "Sales: Order Confirmation"):
        assert ten not in khoi, f"tên template {ten!r} bị viết cứng trong script"
    for model in ("stock.picking", "account.move"):
        assert model not in khoi, (
            f"tên model {model!r} bị viết cứng trong khối dựng luật mail.template")


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
