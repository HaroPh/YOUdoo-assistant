"""TOOL_ACCESS_MAP trong scripts/check_role_odoo_consistency.py chép tay từ
mã nguồn tool. Đo 2026-08-12: 8/18 dòng sai — 3 dòng sai operation, 5 dòng
thiếu cặp. Cả hai con số mà báo cáo phân quyền đưa ra đều dựa trên bảng hỏng
đó.

Bảng CỐ Ý giữ dạng tường minh (xem comment trong chính script): một parser
trong production sai thì đo sai âm thầm, một parser trong test sai thì chỉ
gây ồn. Nên bảng ở lại, và test này canh nó.

PHẠM VI: chỉ kiểm MODEL, KHÔNG kiểm operation. ODOO_METHOD_OPERATION_MAP ánh
xạ action_create_invoice -> "create", nên một test dựa vào nó để suy operation
sẽ tái lập đúng dòng sai đã phải sửa (create_bill_from_po gọi
action_create_invoice trên PO CÓ SẴN, cần "write" chứ không phải "create" trên
purchase.order — đo sống đã bác bỏ). Bảng đó phân loại tác dụng phụ phục vụ
cổng xác nhận, không phải quyền Odoo. Ở đây nó CHỈ được dùng để phân biệt đọc
với ghi, điều đó an toàn bất kể ngữ nghĩa quyền.

GIỚI HẠN: một số tool gọi Odoo qua helper dùng chung (vd _validate_order_pickings
trong helpers.py), nên quét thân tool là hụt. Test đi thêm ĐÚNG MỘT CẤP vào hàm
được định nghĩa trong cùng package mcp-servers/odoo. Sâu hơn thì KHÔNG — nêu
thẳng ở đây thay vì để người sau tưởng nó phủ hết.

TASK 8 (đo 2026-08-15): thêm update_quotation_lines/update_rfq_lines vào
TOOL_ACCESS_MAP lộ một hạng giới hạn khác của bước "đi một cấp" — cả hai tool
delegate 100% cho helpers._apply_line_ops(model, qty_field, order_ref, ops),
và model chỉ là THAM SỐ trong thân helper (odoo(model, "search_read", ...)),
không phải literal, nên bước Constant-check cũ luôn bỏ qua cặp đó dù đi đúng
một cấp vào tới nơi. _odoo_calls giờ mang theo _subst — literal truyền Ở LỆNH
GỌI CẤP 0 khớp theo VỊ TRÍ tham số của hàm được gọi.

FIX ROUND 1 (review Important, đo 2026-08-15): bản đầu áp _subst KHÔNG ĐIỀU
KIỆN cho MỌI lệnh gọi cấp 0→1 trong toàn mcp-servers/odoo, không riêng
_apply_line_ops — 3 đường tạo ra substitution SAI (không phải chỉ thiếu):
zip() lờ đi posonlyargs (callee có tham số buộc vị trí thì lệch tên), lờ đi
self nếu funcs từng trỏ vào bound method (hiện KHÔNG có class nào trong
mcp-servers/odoo nên ngủ yên, nhưng không gì chặn), và callee có thể GÁN LẠI
tên tham số trước khi dùng trong odoo() mà substitution vẫn ghi đè bằng giá
trị đã bắt ở lệnh gọi. Cả ba đều ĐANG NGỦ YÊN (đo thật: probe model giả và
hoán đổi sale.order/purchase.order đều lên ĐỎ đúng), nhưng "chưa lộ" khác
"không lộ được" — một docstring liệt kê nguy cơ không tự nó chặn được nguy
cơ (đúng luận điểm xuyên suốt nhánh này: khai báo xuông thì trôi, chỉ cơ chế
máy mới giữ). Nên _odoo_calls giờ CHỦ ĐỘNG TỪ CHỐI substitution (không phải
chỉ ghi chú) khi không tin được khớp vị trí — xem _khop_vi_tri_an_toan/
_ten_bi_gan_lai bên dưới và docstring _odoo_calls. Từ chối là hướng AN
TOÀN: substitution thiếu → model không giải được → khai báo không thỏa →
test_model_khai_deu_co_that_trong_nguon_tool đỏ ẦM Ĩ; substitution sai →
lặng thinh và có thể đóng dấu OK nhầm. Bất đối xứng đó là toàn bộ lý do
fail-closed thay vì chỉ cảnh báo bằng lời.

SỬA SO VỚI BẢN GỐC CỦA BRIEF (đo thật khi chạy Step 2, không phải đoán):
send_delivery_email/send_invoice_email trong TOOL_ACCESS_MAP KHÔNG phải hàm
MCP — chúng là tên coordinator tầng agent (EmailCfg.tool_name,
backend/src/agents/mail_write.py), tra thẳng theo tên trong mcp-servers/odoo
sẽ luôn "không tìm thấy hàm" dù model khai đúng 100% (đọc mail.py xác nhận:
mail.template/mail.mail trong bảng khớp CHÍNH XÁC 3 lệnh odoo() thật trong
preview_template_email/send_prepared_email/discard_prepared_email — 3 tool
MCP DÙNG CHUNG mà MỌI coordinator mail gọi, mail_write.py tự khai rõ là
MAIL_DEPS). Đây là lỗi cách tra cứu của TEST (thiếu ca coordinator), không
phải dòng bảng sai — nên vá test bằng alias, không đụng TOOL_ACCESS_MAP."""
import ast
import importlib.util
import pathlib
import sys

import pytest

from src.agents import mail_write, roles

REPO = pathlib.Path(__file__).resolve().parents[3]
MCP_DIR = REPO / "mcp-servers" / "odoo"
SCRIPT = REPO / "scripts" / "check_role_odoo_consistency.py"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script_mod():
    if not SCRIPT.exists():
        pytest.skip("chưa có scripts/check_role_odoo_consistency.py")
    return _load_module(SCRIPT, "_check_role_odoo_consistency_for_test")


@pytest.fixture(scope="module")
def read_methods():
    """Tên method THUẦN ĐỌC, lấy từ security.py — không khai lại."""
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sec = _load_module(MCP_DIR / "security.py", "_mcp_security_for_test")
    return {m for m, op in sec.ODOO_METHOD_OPERATION_MAP.items() if op == "read"}


@pytest.fixture(scope="module")
def funcs():
    """{tên hàm: ast.FunctionDef} cho mọi file .py trong mcp-servers/odoo."""
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    out = {}
    for f in sorted(MCP_DIR.rglob("*.py")):
        if ".venv" in f.parts or "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, node)
    return out


def _khop_vi_tri_an_toan(callee):
    """True nếu chữ ký `callee` đơn giản đủ để zip() theo VỊ TRÍ với các đối
    số ở lệnh gọi mà KHÔNG lệch tên — chỉ tham số thường (args), không
    positional-only (posonlyargs — review Fix 1: '/' làm lệch mọi tên sau
    nó), không keyword-only, không *args/**kwargs (thay đổi số lượng/thứ tự
    khớp). False = TỪ CHỐI substitution cho TOÀN BỘ callee này, không cố
    khớp một phần."""
    a = callee.args
    return not (a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg)


def _ten_co_trong_target(target, ten):
    """True nếu `ten` xuất hiện như một BINDING TARGET bên trong node target
    (xử lý cả unpacking: (a, b) = ..., [a, b] = ...)."""
    return any(isinstance(n, ast.Name) and n.id == ten for n in ast.walk(target))


def _ten_bi_gan_lai(callee, ten):
    """True nếu tham số `ten` bị GÁN LẠI ở bất kỳ đâu trong thân `callee`
    (review Fix 3) — assignment thường, augmented assignment, annotated
    assignment, target vòng for, with ... as, walrus (:=), target
    comprehension, hoặc tên except-handler. Bảo thủ có chủ ý: không phân
    biệt scope lồng bên trong (hàm/lambda con) — thấy `ten` làm target ở
    ĐÂU cũng coi là rebind, thà bỏ sót một substitution còn hơn dùng nhầm
    giá trị đã bắt tại lệnh gọi cấp trên."""
    for sub in ast.walk(callee):
        if isinstance(sub, ast.Assign):
            if any(_ten_co_trong_target(t, ten) for t in sub.targets):
                return True
        elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
            if _ten_co_trong_target(sub.target, ten):
                return True
        elif isinstance(sub, (ast.For, ast.AsyncFor)):
            if _ten_co_trong_target(sub.target, ten):
                return True
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            if any(item.optional_vars and _ten_co_trong_target(item.optional_vars, ten)
                   for item in sub.items):
                return True
        elif isinstance(sub, ast.NamedExpr):
            if _ten_co_trong_target(sub.target, ten):
                return True
        elif isinstance(sub, ast.comprehension):
            if _ten_co_trong_target(sub.target, ten):
                return True
        elif isinstance(sub, ast.ExceptHandler):
            if sub.name == ten:
                return True
    return False


def _odoo_calls(node, funcs, _depth=0, _subst=None):
    """{(model, method)} cho mọi lệnh odoo(...) trong `node`, đi thêm ĐÚNG MỘT
    cấp vào hàm cùng package được gọi trong thân nó.

    _subst: {tên tham số: giá trị literal} áp cho THÂN `node` khi nó được gọi
    ở lệnh gọi cấp 0 với đối số chuỗi literal khớp VỊ TRÍ tham số. Trường hợp
    thật cần đến (đo 2026-08-15, xem docstring module): helpers._apply_line_ops
    nhận model QUA THAM SỐ (dùng chung cho update_quotation_lines/
    update_rfq_lines), nên thân nó chỉ có odoo(model, "search_read", ...) —
    model là ast.Name, không phải ast.Constant.

    FAIL-CLOSED (review Fix 1, đo 2026-08-15): substitution chỉ được XÂY khi
    _khop_vi_tri_an_toan(callee) đúng (không posonly/kwonly/*args/**kwargs —
    khớp lệch tên nếu có), và CHỈ đưa một tên cụ thể vào substitution khi
    _ten_bi_gan_lai(callee, tên) SAI (callee không gán lại tên đó trước khi
    dùng). Bất kỳ điều kiện nào không thỏa → KHÔNG substitute (cho toàn bộ
    callee, hoặc cho đúng tên đó) — model ở callee vẫn là ast.Name không
    resolve được, cặp không được báo cáo, TOOL_ACCESS_MAP khai model đó sẽ
    làm test_model_khai_deu_co_that_trong_nguon_tool đỏ. Đó là hướng AN
    TOÀN có chủ ý: thiếu substitution gây ồn (đỏ), substitution sai gây im
    lặng (đóng dấu OK nhầm) — xem docstring module."""
    subst = _subst or {}
    found = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        ten = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if ten == "odoo" and len(sub.args) >= 2:
            model, method = sub.args[0], sub.args[1]
            if isinstance(model, ast.Constant):
                model_val = model.value
            elif isinstance(model, ast.Name):
                model_val = subst.get(model.id)
            else:
                model_val = None
            method_val = method.value if isinstance(method, ast.Constant) else None
            if model_val is not None and method_val is not None:
                found.add((model_val, method_val))
        elif _depth == 0 and ten in funcs and ten != node.name:
            callee = funcs[ten]
            call_subst = {}
            if _khop_vi_tri_an_toan(callee):
                for param, arg in zip(callee.args.args, sub.args):
                    if isinstance(arg, ast.Constant) and not _ten_bi_gan_lai(callee, param.arg):
                        call_subst[param.arg] = arg.value
            found |= _odoo_calls(callee, funcs, _depth + 1, _subst=call_subst)
    return found


@pytest.fixture(scope="module")
def coordinator_aliases():
    """{tên tool trong TOOL_ACCESS_MAP: {tên hàm MCP thật cần quét}} cho tool
    coordinator tầng agent không có hàm cùng tên trong mcp-servers/odoo (xem
    docstring module — send_delivery_email, send_invoice_email). Nguồn sự
    thật là mail_write.MAIL_DEPS, không khai lại ở đây."""
    return {cfg.tool_name: mail_write.MAIL_DEPS for cfg in mail_write.MAIL_COORDINATOR_CFGS}


def _odoo_calls_for_tool(tool, funcs, aliases):
    """{(model, method)} chạm bởi `tool`. Ưu tiên hàm cùng tên trong
    mcp-servers/odoo; nếu không có, thử alias coordinator (aliases). Trả
    None khi không tìm được cách nào — caller coi đó là "không tìm thấy"."""
    node = funcs.get(tool)
    if node is not None:
        return _odoo_calls(node, funcs)
    alias_funcs = aliases.get(tool)
    if not alias_funcs:
        return None
    found = set()
    for name in alias_funcs:
        alias_node = funcs.get(name)
        if alias_node is not None:
            found |= _odoo_calls(alias_node, funcs)
    return found


def _declared_tools():
    """Mọi tool khai trong roles.py, mọi profile, mọi vai."""
    out = set()
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            if cfg.unrestricted:
                continue
            out |= set(cfg.own) | set(cfg.needs_sign_off) | set(cfg.other_dept)
    return out


def test_moi_tool_trong_roles_deu_duoc_bang_phu(script_mod):
    """Thêm tool mới vào roles.py mà quên cập nhật bảng => script kiểm tra âm
    thầm bỏ sót nó."""
    phu = set(script_mod.TOOL_ACCESS_MAP) | set(script_mod.UNMAPPED_TOOLS)
    thieu = sorted(_declared_tools() - phu)
    assert not thieu, (
        "tool khai trong roles.py nhưng không có trong TOOL_ACCESS_MAP cũng "
        f"không trong UNMAPPED_TOOLS: {thieu}")


def _registered_tools():
    """Mọi tool MCP đã đăng ký, lấy từ chính registry — nguồn phủ ĐÚNG.

    _declared_tools() chỉ lấy tool GHI khai trong roles.py, nên tool CHỈ-ĐỌC
    lọt hoàn toàn qua cả hai lưới (find_my_activities là một trường hợp thật,
    đo 2026-08-14). Registry thì không phân biệt đọc/ghi."""
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        return set(server.mcp._tool_manager._tools)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_moi_tool_mcp_dang_ky_deu_duoc_bang_phu(script_mod):
    """Tool CHỈ-ĐỌC cũng phải được khai hoặc được miễn trừ kèm lý do."""
    phu = set(script_mod.TOOL_ACCESS_MAP) | set(script_mod.UNMAPPED_TOOLS)
    thieu = sorted(_registered_tools() - phu)
    assert not thieu, (
        "tool đã đăng ký trên MCP nhưng không có trong TOOL_ACCESS_MAP cũng "
        f"không trong UNMAPPED_TOOLS: {thieu}")


def test_nguon_phu_moi_rong_hon_nguon_cu(script_mod):
    """Đối chứng: nếu _registered_tools() vì lý do nào đó trả tập rỗng hoặc
    hẹp hơn roles.py, lưới ở trên xanh giả và lỗ cấu trúc vẫn nguyên.

    RULING B (đo 2026-08-15): khẳng định gốc dự tính cho test này
    (_declared_tools() < _registered_tools(), tập con thực sự) SAI và đã bị
    thay — _declared_tools() KHÔNG phải tập con của registry.
    send_delivery_email/send_invoice_email được khai trong roles.py (cfg.own
    v.v.) nhưng KHÔNG phải hàm MCP thật — chúng là tên coordinator tầng
    agent (EmailCfg.tool_name, backend/src/agents/mail_write.py; xem thêm
    coordinator_aliases ở trên cho cách file này đã xử lý ca tương tự).
    Nên thay bằng hai khẳng định đã đo và xác nhận đúng trên checkout này:"""
    moi = _registered_tools()
    # (1) nguồn phủ mới thực sự lấp đúng khoảng trống đã tạo ra task này.
    assert "find_my_activities" in moi - _declared_tools()
    # (2) chốt CHÍNH XÁC phần không giao nhau: đúng những tên coordinator tầng
    # backend, không phải tool MCP thật.
    #
    # SUY RA từ mail_write thay vì gõ tay (đổi 2026-08-23 khi thêm vai
    # `sales`): bản cũ ghim đúng hai tên và đã đỏ khi vai mới mang theo hai
    # coordinator nữa — đỏ ĐÚNG ý định của nó, nhưng cách sửa đúng là chốt
    # tính chất ("mọi phần thừa đều là coordinator mail") chứ không phải chép
    # thêm hai chuỗi. Nếu một coordinator trở thành tool MCP THẬT thì nó rời
    # tập này và dòng dưới vẫn đỏ.
    from src.agents import mail_write as _mw
    ten_coordinator = {c.tool_name for c in _mw.MAIL_COORDINATOR_CFGS}
    thua = _declared_tools() - moi
    assert thua, "không còn tên nào chỉ có ở roles.py — khẳng định (2) mất nghĩa"
    assert thua <= ten_coordinator, (
        "roles.py khai tên KHÔNG phải tool MCP và cũng KHÔNG phải coordinator "
        f"mail: {sorted(thua - ten_coordinator)}")


def test_model_khai_deu_co_that_trong_nguon_tool(script_mod, funcs, coordinator_aliases):
    """Khai -> có thật. Bắt model khai nhầm hoặc không còn được đụng tới.

    GIỚI HẠN: test này chỉ đòi model được ĐỤNG TỚI, không đòi được GHI. Một
    model khai cho một pair ghi nhưng nguồn chỉ còn gọi odoo() ĐỌC trên model
    đó vẫn xanh. Đo thật: return_order khai ("stock.picking", "create"); nguồn
    chỉ còn đúng một lệnh odoo("stock.picking", ...) và đó là lệnh ĐỌC; xoá
    hẳn dòng khai đó đi thì cả 3 test trong file này vẫn xanh. Vậy test này
    canh "có nhắc tới", không canh "có ghi thật" — không đổi logic để canh
    thêm việc đó."""
    vi_pham = []
    for tool, pairs in script_mod.TOOL_ACCESS_MAP.items():
        calls = _odoo_calls_for_tool(tool, funcs, coordinator_aliases)
        if calls is None:
            vi_pham.append(f"{tool}: không tìm thấy hàm trong mcp-servers/odoo")
            continue
        thuc_te = {m for m, _ in calls}
        for model, _op in pairs:
            if model not in thuc_te:
                vi_pham.append(
                    f"{tool}: khai model {model!r} nhưng nguồn không gọi "
                    f"odoo({model!r}, ...) — thực tế chạm: {sorted(thuc_te)}")
    assert not vi_pham, "\n".join(vi_pham)


def test_model_bi_ghi_trong_nguon_deu_da_duoc_khai(script_mod, funcs, read_methods,
                                                    coordinator_aliases):
    """Có thật -> đã khai.

    Đo lại bằng cách revert từng dòng trong 8 dòng mà 6c06aaa đã sửa rồi chạy
    test: CHỈ 3/8 lên đỏ (return_order, register_payment,
    create_bill_from_po). 5 dòng còn lại (internal_transfer,
    inventory_adjustment, scrap_product, create_credit_memo, và cặp
    send_delivery_email/send_invoice_email) vẫn xanh — không phải vì test
    yếu mà vì cặp thiếu của chúng là một OPERATION thứ hai trên một model ĐÃ
    khai (vd tool đã khai (X, "read") rồi ghi thêm (X, "write") mà không
    thêm dòng), trong khi test này CHỈ so model, không so operation (xem
    PHẠM VI ở docstring module, spec §4.3 — thiết kế model-scope là cố ý,
    không phải chỗ cần sửa). Với những dòng đó, model vẫn nằm trong đã_khai
    nên vòng lặp không có gì để bắt."""
    vi_pham = []
    for tool, pairs in script_mod.TOOL_ACCESS_MAP.items():
        calls = _odoo_calls_for_tool(tool, funcs, coordinator_aliases)
        if calls is None:
            continue
        da_khai = {m for m, _ in pairs}
        for model, method in calls:
            if method in read_methods:
                continue
            if model not in da_khai:
                vi_pham.append(
                    f"{tool}: nguồn GHI vào {model!r} qua {method!r} nhưng "
                    f"model đó không có trong khai báo {sorted(da_khai)}")
    assert not vi_pham, "\n".join(vi_pham)


def test_helper_mot_cap_that_su_duoc_di_vao(funcs):
    """Đối chứng cho giới hạn nêu ở docstring module: nếu việc đi một cấp
    hỏng, KHÔNG phải cả hai test trên đều xanh giả như nhau. Đo thật bằng
    cách tắt bước đi một cấp: test_model_bi_ghi_trong_nguon_deu_da_duoc_khai
    xanh giả thật (nguồn coi như không ghi gì, nên không có gì để bắt) —
    nhưng test_model_khai_deu_co_that_trong_nguon_tool lại chuyển ĐỎ, vì lý
    do khác hẳn: model đã khai (vd stock.picking cho deliver_order) không
    còn được đụng tới ở đâu cả một khi không đi vào helper, nên chính khai
    báo đó bị coi là khai nhầm. deliver_order là ví dụ thật — nó không tự
    gọi odoo() trên stock.picking mà đi qua _validate_order_pickings trong
    helpers.py."""
    node = funcs.get("deliver_order")
    assert node is not None, "không tìm thấy deliver_order"
    models = {m for m, _ in _odoo_calls(node, funcs)}
    assert "stock.picking" in models, (
        "đi một cấp vào helper không hoạt động — test_model_bi_ghi_trong_nguon_deu_da_duoc_khai sẽ xanh giả")


# ── Fix round 1 (review Important, 2026-08-15): guard fail-closed của
# _odoo_calls đo bằng AST TỔNG HỢP nhỏ, KHÔNG đụng file nguồn thật trong
# mcp-servers/odoo — 3 test dưới đây phải phân biệt được "guard đã chặn
# đúng ca nguy hiểm" với "substitution bị tắt luôn, mọi ca đều rỗng" (một
# guard tắt hết tính năng cũng làm 2 test đầu "xanh" theo nghĩa lỏng lẻo,
# nên test thứ 3 — ca an toàn thật — phải khẳng định substitution VẪN chạy).

def _ham_tu_ma(src):
    """Parse `src`, trả {tên hàm: ast.FunctionDef} — dựng AST tổng hợp nhỏ
    tại chỗ cho test guard, không đọc/ghi file nào."""
    tree = ast.parse(src)
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def test_subst_tu_choi_khi_callee_co_tham_so_buoc_vi_tri():
    """Review Fix 1: callee khai tham số buộc vị trí (a, b, /, model) — chỉ
    `model` nằm trong callee.args.args (a, b bị đẩy sang posonlyargs), nên
    zip() ngây thơ với 3 đối số lệnh gọi sẽ khớp NHẦM đối số ĐẦU TIÊN ("A",
    lẽ ra thuộc `a`) vào tên `model` — SAI, không phải thiếu (đúng ca 1 mà
    review nêu). Không guard: cặp lộ ra sẽ là ("A", "write") — model giả,
    không phải "purchase.order" ở đối số thứ ba. Có guard:
    _khop_vi_tri_an_toan thấy posonlyargs khác rỗng → từ chối TOÀN BỘ
    substitution cho callee này → không cặp nào được báo cáo."""
    src = '''
def caller():
    return helper("A", "B", "purchase.order")

def helper(a, b, /, model):
    return odoo(model, "write")
'''
    funcs = _ham_tu_ma(src)
    calls = _odoo_calls(funcs["caller"], funcs)
    assert calls == set(), (
        "guard không chặn positional-only — substitution lệch tên đã lọt "
        f"qua: {calls}")


def test_subst_tu_choi_khi_ten_bi_gan_lai_truoc_khi_dung():
    """Review Fix 3: callee GÁN LẠI tên tham số trước khi dùng trong odoo() —
    giá trị bắt ở lệnh gọi cấp trên không còn đúng ngữ nghĩa tại điểm gọi
    odoo(). Guard phải từ chối substitute đúng tên đó, nên cặp không được
    báo cáo."""
    src = '''
def caller():
    return helper("sale.order")

def helper(model):
    model = "purchase.order"
    return odoo(model, "write")
'''
    funcs = _ham_tu_ma(src)
    calls = _odoo_calls(funcs["caller"], funcs)
    assert calls == set(), (
        "guard không chặn rebind — substitution có thể đã dùng giá trị cũ "
        f"sai ngữ cảnh: {calls}")


def test_subst_van_hoat_dong_o_ca_an_toan():
    """Đối chứng bắt buộc: ca giống _apply_line_ops thật (tham số thường,
    không rebind) — guard KHÔNG được tắt tính năng, substitution vẫn phải
    chạy và trả đúng model. Thiếu test này thì 2 test trên có thể xanh giả
    vì guard đã vô hiệu hoá toàn bộ cơ chế, không phải vì nó chặn đúng ca
    nguy hiểm."""
    src = '''
def caller():
    return helper("sale.order", "product_uom_qty")

def helper(model, qty_field):
    return odoo(model, "write")
'''
    funcs = _ham_tu_ma(src)
    calls = _odoo_calls(funcs["caller"], funcs)
    assert calls == {("sale.order", "write")}, (
        "guard đã tắt luôn substitution ở ca an toàn — tính năng Task 8 bị "
        f"vô hiệu hoá thay vì chỉ chặn ca nguy hiểm: {calls}")
