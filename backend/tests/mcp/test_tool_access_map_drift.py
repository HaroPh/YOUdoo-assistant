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


def _odoo_calls(node, funcs, _depth=0):
    """{(model, method)} cho mọi lệnh odoo(...) trong `node`, đi thêm ĐÚNG MỘT
    cấp vào hàm cùng package được gọi trong thân nó."""
    found = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        ten = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if ten == "odoo" and len(sub.args) >= 2:
            model, method = sub.args[0], sub.args[1]
            if isinstance(model, ast.Constant) and isinstance(method, ast.Constant):
                found.add((model.value, method.value))
        elif _depth == 0 and ten in funcs and ten != node.name:
            found |= _odoo_calls(funcs[ten], funcs, _depth + 1)
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


def test_model_khai_deu_co_that_trong_nguon_tool(script_mod, funcs, coordinator_aliases):
    """Khai -> có thật. Bắt model khai nhầm hoặc không còn được đụng tới."""
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
    """Có thật -> đã khai. Bắt ĐÚNG 5 dòng thiếu cặp của lần trước."""
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
    """Đối chứng cho giới hạn nêu ở docstring: nếu việc đi một cấp hỏng, hai
    test trên sẽ xanh giả cho mọi tool gọi Odoo qua helper. deliver_order là
    ví dụ thật — nó không tự gọi odoo() trên stock.picking mà đi qua
    _validate_order_pickings trong helpers.py."""
    node = funcs.get("deliver_order")
    assert node is not None, "không tìm thấy deliver_order"
    models = {m for m, _ in _odoo_calls(node, funcs)}
    assert "stock.picking" in models, (
        "đi một cấp vào helper không hoạt động — hai test kia sẽ xanh giả")
