"""log_activity được cấp cho cả hai vai non-admin.

ĐỢT NÀY CỐ Ý ĐỔI allowed_tools() — ngược ràng buộc cứng của đợt trước. Thêm
một tool vào `own` nghĩa là scripts/odoo_setup_ai_accounts.py sinh ra bộ nhóm
quyền Odoo khác trước, nên thay đổi này phải được khoá bằng test chứ không để
nó âm thầm."""
import pathlib

from src.agents import roles

SETUP = (pathlib.Path(__file__).resolve().parents[3]
         / "scripts" / "odoo_setup_ai_accounts.py")
CHECK = (pathlib.Path(__file__).resolve().parents[3]
         / "scripts" / "check_role_odoo_consistency.py")


def test_ca_hai_vai_deu_so_huu_log_activity():
    for profile_name, profile in roles.PROFILES.items():
        for role_name in ("warehouse", "accounting"):
            cfg = profile[role_name]
            assert cfg.state_of("log_activity") == roles.OWN, (
                f"{profile_name}/{role_name} không sở hữu log_activity")
            assert "log_activity" in cfg.allowed_tools()


def test_log_activity_co_trong_dept_of():
    """Test bao phủ của đợt trước đòi mọi tool được sở hữu phải có bộ phận."""
    assert "log_activity" in roles.DEPT_OF


def test_nhom_activity_duoc_tao_va_gan_cho_ba_tai_khoan_ghi():
    """Đọc NGUỒN script, không chạy nó — chạy là chạm Odoo sống.

    Bản cũ của test này chỉ đo "ir.model" in src và ba login xuất hiện trong
    file — cả bốn đã ĐÚNG từ trước nhánh này (đo lại trên
    dda37c4:scripts/odoo_setup_ai_accounts.py, commit gốc trước khi nhánh này
    thêm log_activity: cả bốn assertion cũ đều pass). Nghĩa là xoá cả ba dòng
    g_act khỏi PLAN thì test vẫn xanh — không khoá được gì. Viết lại để đo
    đúng hai thứ nhánh này thêm: (1) tên ensure_access ir.model read mới,
    (2) nhóm g_act có mặt ở CẢ BA tài khoản ghi và VẮNG MẶT ở ai-readonly."""
    src = SETUP.read_text(encoding="utf-8")
    assert "Youdoo AI / Activity" in src
    assert "youdoo_ai_activity_ir_model" in src

    keys = ("ai-readonly", "ai-admin", "ai-warehouse", "ai-accounting")
    starts = sorted(((k, src.index(f'"{k}":')) for k in keys), key=lambda kv: kv[1])
    plan_end = src.index("\n}", starts[-1][1])
    rows = {}
    for i, (k, pos) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else plan_end
        rows[k] = src[pos:end]

    assert "g_act" not in rows["ai-readonly"], (
        "ai-readonly không được có g_act — vai này không tạo/ghi activity")
    for k in ("ai-admin", "ai-warehouse", "ai-accounting"):
        assert "g_act" in rows[k], f"dòng PLAN của {k} thiếu g_act"


def test_bang_quyen_co_dong_cho_log_activity():
    """log_activity trước đây nằm trong UNMAPPED_TOOLS hoặc không có; nay nó là
    own của hai vai nên script kiểm tra phải đo được nó."""
    src = CHECK.read_text(encoding="utf-8")
    assert "log_activity" in src
