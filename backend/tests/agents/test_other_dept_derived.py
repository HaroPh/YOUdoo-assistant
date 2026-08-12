"""other_dept được SUY RA từ DEPT_OF, không khai tay từng vai.

Vì sao quan trọng: guard tất định trong nodes.py:275 xử lý OTHER_DEPT và DENIED
Y HỆT NHAU, nên other_dept KHÔNG quyết định câu chữ từ chối. Nó quyết định lời
từ chối có XẢY RA hay không — nó là hint trong prompt cho planner biết tool có
tồn tại, để planner trả về đúng tên tool và guard mới có gì để bắt. Thiếu ⇒ LLM
không biết tool có thật ⇒ trả lời hội thoại lan man, guard không chạy. Đo được
đúng như vậy ở nghiệm thu 2026-08-12 (kịch bản 4)."""
import pytest

from src.agents import roles

# Đo 2026-08-12: 5 tool bị denied trong khi vai KHÁC sở hữu chúng.
THIEU_TRUOC_DAY = {
    "warehouse": {"create_invoice_from_order", "create_bill_from_po",
                  "send_invoice_email"},
    "accounting": {"send_delivery_email", "flag_order_for_review"},
}

# Chốt không-hồi-quy cho ranh giới quyền Odoo: allowed_tools() = own ∪
# needs_sign_off, và đợt này KHÔNG được đụng vào nó (spec §3.4).
ALLOWED_MONG_DOI = {
    ("small-business", "warehouse"): {
        "deliver_order", "receive_order", "validate_picking",
        "internal_transfer", "inventory_adjustment", "scrap_product",
        "flag_order_for_review", "return_order", "send_delivery_email"},
    ("small-business", "accounting"): {
        "create_credit_memo", "send_invoice_email",
        "create_invoice_from_order", "create_bill_from_po",
        "post_invoice", "register_payment"},
    ("enterprise", "warehouse"): {
        "deliver_order", "receive_order", "validate_picking",
        "internal_transfer", "send_delivery_email"},
    ("enterprise", "accounting"): {
        "create_credit_memo", "send_invoice_email",
        "create_invoice_from_order", "create_bill_from_po",
        "post_invoice", "register_payment"},
}


@pytest.mark.parametrize("role_name,thieu", sorted(THIEU_TRUOC_DAY.items()))
def test_nam_khoang_trong_da_dong(role_name, thieu):
    cfg = roles.PROFILES["small-business"][role_name]
    con_thieu = sorted(t for t in thieu if cfg.state_of(t) != roles.OTHER_DEPT)
    assert not con_thieu, (
        f"{role_name}: các tool này thuộc bộ phận khác nhưng vẫn bị coi là "
        f"denied, nên planner không được nhắc tên chúng và lời từ chối sẽ "
        f"không xảy ra: {con_thieu}")


def test_other_dept_khong_chua_tool_cua_chinh_vai():
    """Suy diễn phải loại chính nghiệp vụ của vai ra, kể cả tool needs_sign_off."""
    for profile_name, profile in roles.PROFILES.items():
        for role_name, cfg in profile.items():
            if cfg.unrestricted:
                continue
            lan = sorted(cfg.other_dept & (cfg.own | cfg.needs_sign_off))
            assert not lan, f"{profile_name}/{role_name} tự xếp mình vào other_dept: {lan}"


def test_admin_khong_co_other_dept():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert cfg.other_dept == frozenset()


def test_enterprise_giu_duoc_loi_thoat_other_dept_extra():
    """3 nghiệp vụ này thuộc bộ phận KHO nhưng enterprise cố tình xếp ra ngoài
    vai kho, nên suy diễn (so DEPT_OF[t] != label) KHÔNG lấy chúng. Đó là lý do
    other_dept_extra tồn tại (spec §3.3)."""
    ent = roles.PROFILES["enterprise"]["warehouse"]
    for t in ("inventory_adjustment", "scrap_product", "return_order"):
        assert t in ent.other_dept, f"{t} rơi mất khỏi other_dept của enterprise"


def test_enterprise_cung_duoc_ba_tool_moi_suy_ra():
    """KHÔNG phải 'giữ nguyên y hệt bản cũ': tập suy ra RỘNG HƠN tập khai tay
    cũ đúng 3 mục, và đó chính là phần sửa (spec §5.1)."""
    ent = roles.PROFILES["enterprise"]["warehouse"]
    for t in ("create_invoice_from_order", "create_bill_from_po",
              "send_invoice_email"):
        assert t in ent.other_dept


@pytest.mark.parametrize("key,mong_doi", sorted(ALLOWED_MONG_DOI.items()))
def test_allowed_tools_khong_doi(key, mong_doi):
    """Đối chứng cho spec §3.4: đợt này chỉ đụng nội dung prompt, KHÔNG đụng
    ranh giới quyền tài khoản Odoo. Nếu test này đỏ thì
    scripts/odoo_setup_ai_accounts.py sẽ sinh ra bộ nhóm quyền khác trước."""
    profile_name, role_name = key
    cfg = roles.PROFILES[profile_name][role_name]
    assert set(cfg.allowed_tools()) == mong_doi


def test_other_dept_extra_van_duoc_ton_trong_khi_dung_tay():
    """RoleCfg tự chế: label 'X' không có trong DEPT_OF nên mọi mục của bảng
    đều là 'bộ phận khác', cộng thêm phần khai tay."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}),
                        other_dept_extra=frozenset({"c"}))
    assert cfg.state_of("a") == roles.OWN
    assert cfg.state_of("c") == roles.OTHER_DEPT
    assert cfg.state_of("post_invoice") == roles.OTHER_DEPT   # từ DEPT_OF
    assert cfg.state_of("tool_bia_ra") == roles.DENIED        # fail-closed
