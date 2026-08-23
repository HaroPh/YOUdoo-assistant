"""DEPT_OF là nguồn sự thật duy nhất cho "tool X thuộc bộ phận nào".

Bảng này từng nằm ở prompts.py và ĐÃ TRÔI LỆCH: đo 2026-08-12 thấy thiếu đúng
3 tool (flag_order_for_review, send_delivery_email, send_invoice_email), cả ba
được thêm vào roles.py ở các đợt sau mà không ai cập nhật bảng. Hệ quả là lời
từ chối nói "liên hệ bộ phận khác" thay vì nêu tên bộ phận thật.

Test dưới đây khoá bất biến đó lại: một tool đã được vai nào đó sở hữu mà chưa
khai bộ phận là đỏ ngay.

ĐIỂM MÙ: test_moi_tool_duoc_so_huu_deu_co_bo_phan chỉ duyệt tool đã được MỘT
vai nào đó SỞ HỮU (own ∪ needs_sign_off), nên không thấy được chiều ngược lại
— tool KHÔNG được vai nào sở hữu thì không nằm trong vòng lặp, dù DEPT_OF có
thiếu nó hay không. Đo lại 2026-08-12 sau nhánh log-activity-generalisation
(nhánh này cấp log_activity cho cả kho lẫn kế toán và thêm mục của nó vào
DEPT_OF): DEPT_OF phủ 19/34 write tool khai trong WRITE_PLANNER_PROMPT (20
key, nhưng flag_order_for_review là key thứ 20 — xuất xứ từ khai báo SOP
skill, không phải prompt); 15 tool còn lại (gồm send_order_confirmation_email,
send_quotation_email, send_rfq_email, create_lead, convert_lead,
create_vendor, create_bom, create_bulk_rfq, update_quotation_lines,
update_rfq_lines, update_bom_lines, update_vendor_pricing,
create_manufacturing_order, confirm_manufacturing_order,
complete_manufacturing_order) bị DENIED cho cả vai kho lẫn kế toán, nên cả
hai lỗi mà nhánh trước đó sửa (lời từ chối rơi về "bộ phận khác" thay vì nêu
tên, và other_dept suy nhầm) vẫn còn sống nguyên cho 15 tool đó. Đây là
khoảng trống ĐÃ BIẾT, để lại cho một đợt sau — không phải hồi quy của nhánh
nào đã chạm vào đây. KHÔNG thêm 15 tool đó vào DEPT_OF và KHÔNG mở rộng test
ở đây để che điểm mù này."""
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
    # "Bán hàng" RỜI tập này 2026-08-23 khi vai `sales` ra đời — đúng theo
    # thiết kế của chính bảng: nó theo dõi bộ phận CHƯA có vai, và danh sách đó
    # co lại mỗi lần thêm vai. Giữ "Mua hàng" vì đó là bộ phận duy nhất còn lại
    # có nghiệp vụ trong DEPT_OF mà không vai AI nào sở hữu.
    assert set(khong_vai_nao.values()) >= {"Mua hàng"}
    assert "Bán hàng" not in khong_vai_nao.values(), (
        "vai `sales` phải sở hữu mọi tool Bán hàng trong DEPT_OF — nếu không, "
        "một tool bán hàng đang rơi về sàn thay vì bàn giao được cho vai đó")


def test_dept_of_cua_prompts_van_doc_tu_roles():
    """prompts.dept_of giữ nguyên chữ ký cho nodes.py, nhưng KHÔNG được giữ
    bản sao bảng thứ hai — đó là đúng thứ đợt này đi xoá."""
    assert prompts.dept_of("post_invoice") == "Kế toán"
    assert prompts.dept_of("send_delivery_email") == "Kho"
    assert prompts.dept_of("tool_bia_ra") == "khác"
    assert not hasattr(prompts, "_DEPT_OF"), (
        "prompts.py không được giữ bản sao _DEPT_OF nữa")
