"""DEPT_OF là nguồn sự thật duy nhất cho "tool X thuộc bộ phận nào".

Bảng này từng nằm ở prompts.py và ĐÃ TRÔI LỆCH: đo 2026-08-12 thấy thiếu đúng
3 tool (flag_order_for_review, send_delivery_email, send_invoice_email), cả ba
được thêm vào roles.py ở các đợt sau mà không ai cập nhật bảng. Hệ quả là lời
từ chối nói "liên hệ bộ phận khác" thay vì nêu tên bộ phận thật.

Test dưới đây khoá bất biến đó lại: một tool đã được vai nào đó sở hữu mà chưa
khai bộ phận là đỏ ngay."""
from src.agents import roles
from src.agents import prompts


def _tools_owned_by_any_role():
    """Mọi tool nằm trong own ∪ needs_sign_off của bất kỳ vai nào, mọi profile."""
    owned = set()
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            if cfg.unrestricted:
                continue
            owned |= set(cfg.own) | set(cfg.needs_sign_off)
    return owned


def test_moi_tool_duoc_so_huu_deu_co_bo_phan():
    owned = _tools_owned_by_any_role()
    assert owned, "rỗng thì test này vô nghĩa"
    missing = sorted(t for t in owned if t not in roles.DEPT_OF)
    assert not missing, (
        "tool đã được một vai sở hữu nhưng chưa khai bộ phận trong DEPT_OF — "
        "lời từ chối cho tool này sẽ nói 'bộ phận khác' thay vì nêu tên: "
        f"{missing}")


def test_ba_tool_tung_thieu_nay_da_co():
    """Đối chứng cho phép đo 2026-08-12 — nêu tên thẳng để nếu ai đó gỡ chúng
    ra thì đỏ vì đúng lý do, không phải vì một khẳng định chung chung."""
    assert roles.DEPT_OF["send_delivery_email"] == "Kho"
    assert roles.DEPT_OF["send_invoice_email"] == "Kế toán"
    assert roles.DEPT_OF["flag_order_for_review"] == "Kho"


def test_label_cua_moi_vai_la_mot_bo_phan_co_that():
    """Task 2 suy other_dept bằng cách so DEPT_OF[t] với cfg.label. Nếu label
    không phải một giá trị có trong bảng thì phép so LUÔN đúng và other_dept
    phình ra âm thầm — đây là điểm yếu duy nhất của cách suy diễn đó
    (spec §3.2, §6), nên ghim nó lại."""
    depts = set(roles.DEPT_OF.values())
    for profile_name, profile in roles.PROFILES.items():
        for role_name, cfg in profile.items():
            if cfg.unrestricted:
                continue
            assert cfg.label in depts, (
                f"{profile_name}/{role_name} có label {cfg.label!r} không nằm "
                f"trong các bộ phận của DEPT_OF ({sorted(depts)})")


def test_bang_giu_ca_bo_phan_chua_co_vai_ai():
    """DEPT_OF phải giữ được nghiệp vụ của bộ phận CHƯA có vai AI (Bán hàng,
    Mua hàng). Đây chính là thông tin mà suy diễn từ roles.py KHÔNG tạo ra
    được, và là lý do bảng phải tồn tại thay vì bị bỏ hẳn."""
    owned = _tools_owned_by_any_role()
    khong_vai_nao = {t: d for t, d in roles.DEPT_OF.items() if t not in owned}
    assert khong_vai_nao, "bảng mất hết nghiệp vụ của bộ phận chưa có vai AI"
    assert set(khong_vai_nao.values()) >= {"Bán hàng", "Mua hàng"}


def test_dept_of_cua_prompts_van_doc_tu_roles():
    """prompts.dept_of giữ nguyên chữ ký cho nodes.py, nhưng KHÔNG được giữ
    bản sao bảng thứ hai — đó là đúng thứ đợt này đi xoá."""
    assert prompts.dept_of("post_invoice") == "Kế toán"
    assert prompts.dept_of("send_delivery_email") == "Kho"
    assert prompts.dept_of("tool_bia_ra") == "khác"
    assert not hasattr(prompts, "_DEPT_OF"), (
        "prompts.py không được giữ bản sao _DEPT_OF nữa")
