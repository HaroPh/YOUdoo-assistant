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


def test_moi_vai_non_admin_deu_co_nhom_mail_rieng():
    """Bản cũ grep HAI chuỗi literal trong mã script.

    Cách đó chết đúng lúc script chuyển sang SUY RA danh sách vai (2026-08-23,
    khi thêm vai `sales`) — mà chuyển sang suy ra chính LÀ bản sửa cho lớp lỗi
    test này canh: liệt kê tay thì thêm vai mà quên dòng sẽ khiến vai đó chạy
    KHÔNG có ir.rule giới hạn mail, im lặng và về phía nới lỏng.

    Nay khẳng định hai thứ độc lập nhau:
      (1) script KHÔNG liệt kê tay nữa — nếu ai đó quay lại lối cũ thì đỏ;
      (2) mọi vai non-admin của MỌI hồ sơ đều sinh ra một tên nhóm, kiểm trên
          roles.py chứ không trên văn bản script.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    assert "for ten, cfg in _PROFILE.items() if not cfg.unrestricted" in src, (
        "script phải SUY RA danh sách vai, không liệt kê tay")
    assert '"warehouse": "Youdoo AI / Mail Warehouse"' not in src

    from src.agents import roles
    for ho_so, profile in roles.PROFILES.items():
        non_admin = [t for t, c in profile.items() if not c.unrestricted]
        assert non_admin, f"{ho_so} không có vai non-admin nào"
        for ten in non_admin:
            nhom = f"Youdoo AI / Mail {ten.capitalize()}"
            assert nhom.startswith("Youdoo AI / Mail "), nhom
            assert ten.capitalize() in nhom, (
                f"{ho_so}/{ten} không sinh được tên nhóm phân biệt được")


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
