# scripts/odoo_setup_ai_accounts.py
"""Tạo 4 tài khoản AI + 5 nhóm quyền tuỳ chỉnh cho kiến trúc phân vai.

IDEMPOTENT: chạy lại không tạo trùng. KHÔNG sửa/xoá tài khoản có sẵn.
Chạy: backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py
"""
import os
import sys
import xmlrpc.client
from pathlib import Path

URL = os.environ["ODOO_URL"]; DB = os.environ["ODOO_DB"]
ADMIN = os.environ["ODOO_USERNAME"]; PWD = os.environ["ODOO_PASSWORD"]
NEW_PWD = os.environ["AI_ACCOUNT_PASSWORD"]   # BẮT BUỘC — không đặt mặc định

uid = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/common").authenticate(DB, ADMIN, PWD, {})
if not uid:
    sys.exit("Odoo authentication failed")
o = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/object")
def call(m, meth, a, k=None): return o.execute_kw(DB, uid, PWD, m, meth, a, k or {})

# Model đường ĐỌC (trích từ backend/src/erp_query/) + ir.config_parameter cho write-gate
READ_MODELS = [
    "account.move", "account.move.line", "crm.lead", "mrp.bom", "mrp.bom.line",
    "mrp.production", "product.product", "product.supplierinfo", "purchase.order",
    "purchase.order.line", "res.partner", "res.partner.bank", "sale.order",
    "sale.order.line", "stock.lot", "stock.quant", "stock.picking",
    "stock.warehouse.orderpoint", "ir.config_parameter",
]

def model_id(tech):
    r = call("ir.model", "search_read", [[["model", "=", tech]]], {"fields": ["id"], "limit": 1})
    if not r: sys.exit("Không tìm thấy model: %s" % tech)
    return r[0]["id"]

def ensure_group(name):
    r = call("res.groups", "search_read", [[["name", "=", name]]], {"fields": ["id"], "limit": 1})
    if r:
        print("  nhóm đã có:", name); return r[0]["id"]
    gid = call("res.groups", "create", [{"name": name}])
    print("  TẠO nhóm:", name); return gid

def ensure_access(name, gid, tech, perms):
    """perms: dict {'read':1,'write':0,'create':0,'unlink':0}"""
    existing = call("ir.model.access", "search_read", [[["name", "=", name]]], {"fields": ["id"], "limit": 1})
    vals = {"name": name, "model_id": model_id(tech), "group_id": gid,
            "perm_read": perms.get("read", 0), "perm_write": perms.get("write", 0),
            "perm_create": perms.get("create", 0), "perm_unlink": perms.get("unlink", 0)}
    if existing:
        call("ir.model.access", "write", [[existing[0]["id"]], vals]); print("    cập nhật:", name)
    else:
        call("ir.model.access", "create", [vals]); print("    tạo:", name)

def ensure_rule(name, gid, tech, domain):
    """ir.rule ĐỌC theo nhóm. Idempotent theo `name`.

    Chỉ đặt perm_read: perm_write/create/unlink trên mail.template đã có 2
    luật gốc của Odoo quản (đo 2026-08-12, cả hai đều perm_read=False), thêm
    luật ghi ở đây là giẫm lên chúng.

    Ngữ nghĩa Odoo: luật THEO NHÓM chỉ áp lên thành viên của nhóm, và OR với
    nhau. Tài khoản không thuộc nhóm nào có luật trên model này thì không bị
    giới hạn — đó là lý do KHÔNG cần (và không nên) tạo nhóm cho admin.
    """
    vals = {"name": name, "model_id": model_id(tech), "domain_force": domain,
            "groups": [(6, 0, [gid])],
            "perm_read": True, "perm_write": False,
            "perm_create": False, "perm_unlink": False}
    ex = call("ir.rule", "search_read", [[["name", "=", name]]],
              {"fields": ["id"], "limit": 1})
    if ex:
        call("ir.rule", "write", [[ex[0]["id"]], vals]); print("    cập nhật luật:", name)
    else:
        call("ir.rule", "create", [vals]); print("    tạo luật:", name)

print("=== NHÓM QUYỀN TUỲ CHỈNH ===")
g_mail = ensure_group("Youdoo AI / Mail")
ensure_access("youdoo_ai_mail_mail_mail", g_mail, "mail.mail",
              {"read": 1, "write": 1, "create": 1, "unlink": 1})
ensure_access("youdoo_ai_mail_config_param", g_mail, "ir.config_parameter", {"read": 1})

# `create_invoice_from_order` gọi wizard sale.advance.payment.inv, mà nhóm
# "Accounting / Invoicing" KHÔNG cấp — nên tool này khai `own` cho kế toán
# nhưng gãy thật khi chạy (đo 2026-08-11). Nhóm chuẩn duy nhất cấp wizard đó
# là "Sales / User: Own Documents Only", nhưng nó kéo theo 52 cặp (model,
# operation) trên 25 model — gồm mrp.production create/write, toàn bộ CRM, và
# sale.order create (thứ này biến `create_quotation` từ CHẶN ĐÚNG thành một
# khoảng trống mới). Nhóm hẹp dưới đây mở đúng 1 model, không hơn.
g_sinv = ensure_group("Youdoo AI / Sale Invoicing")
ensure_access("youdoo_ai_sinv_wizard", g_sinv, "sale.advance.payment.inv",
              {"read": 1, "write": 1, "create": 1})

# mail.activity create BẮT BUỘC res_model_id (id của ir.model, tra runtime —
# truyền res_model dạng chuỗi bị Odoo từ chối, probe-verify 2026-07-19). Đo
# 2026-08-12: cả ba tài khoản ghi CÓ mail.activity create, nhưng
# ai-warehouse/ai-accounting KHÔNG có ir.model read. Thiếu quyền phụ này thì
# log_activity gãy đúng kiểu coordinator mail đã gãy: quyền chính có, quyền
# phụ không, và chỉ live-verify mới thấy.
g_act = ensure_group("Youdoo AI / Activity")
ensure_access("youdoo_ai_activity_ir_model", g_act, "ir.model", {"read": 1})

# Backstop Odoo cho tầng mail (spec 2026-08-12 §5). Nhóm `Youdoo AI / Mail`
# ở trên cấp mail.mail cho CẢ BA vai — cần thiết, nhưng vì thế Odoo không
# phân biệt được vai nào gửi template nào. Hai nhóm dưới đây thêm luật ĐỌC
# trên mail.template.
#
# Domain giới hạn theo MODEL NGUỒN (res_model của template), KHÔNG theo tên
# template. Đo live 2026-08-12: domain theo tên template chặn cả chính
# template trong-vai của mình — `mail.template.send_mail` đọc nhiều dòng
# mail.template hơn dòng đang gửi (lỗi "không có quyền truy cập 'đọc' vào:
# Mẫu email" dù đúng vai). Tắt luật thì gọi qua; bật lại thì gãy lại — nhân
# quả xác nhận rõ. Domain theo model vẫn đo được là chặn đúng chéo vai (mỗi
# vai chỉ đọc được số template nằm trên model của chính vai đó; admin không
# thuộc nhóm nào nên đọc hết) trong khi không chặn nhầm lượt đọc phụ mà
# send_mail cần trong CÙNG model — xem báo cáo 2026-08-12 để có số đo cụ thể.
#
# Phân công hai tầng theo đó: Odoo chặn CHÉO MODEL (một vai không đọc được
# bất kỳ dòng mail.template nào ngoài model của mình); tầng MCP `role_scope`
# (đã có, Task 4) chặn CHÉO TEMPLATE trong cùng model.
#
# Tập model SUY RA từ mail_write.mail_models_for_role — cùng nguồn mà tiến
# trình MCP dùng. Viết tay ở đây là tạo danh sách song song thứ hai, đúng
# hạng lỗi mà cả mạch phân quyền đang đi sửa.
#
# KHÔNG tạo nhóm cho admin: xem docstring ensure_rule.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from src.agents import roles as _roles          # noqa: E402
from src.agents import mail_write as _mw        # noqa: E402

_PROFILE = _roles.load_profile()
MAIL_ROLE_GROUPS = {"warehouse": "Youdoo AI / Mail Warehouse",
                    "accounting": "Youdoo AI / Mail Accounting"}
g_mail_role = {}
for _role, _gname in MAIL_ROLE_GROUPS.items():
    _models = _mw.mail_models_for_role(_PROFILE[_role])
    if _models is None:
        # None = vai không giới hạn (admin) — không tạo nhóm, xem docstring
        # ensure_rule. Nhánh này không thật sự chạm tới vì MAIL_ROLE_GROUPS
        # chỉ liệt kê vai không phải admin, nhưng giữ tường minh để không
        # âm thầm coi "không giới hạn" và "giới hạn còn rỗng" là một.
        print("  bỏ qua (vai không giới hạn):", _gname)
        continue
    _gid = ensure_group(_gname)
    g_mail_role[_role] = _gid
    if _models:
        _domain = repr([("model", "in", sorted(_models))])
    else:
        # frozenset RỖNG (khác None): vai bị giới hạn nhưng không có
        # coordinator mail nào được cấp. Fail-closed (xem docstring
        # roles.py) — domain này KHÔNG khớp bản ghi nào, chặn toàn bộ
        # mail.template thay vì bỏ qua và vô tình để ngỏ (fail-open).
        print("  vai không có coordinator mail, chặn toàn bộ template:", _gname)
        _domain = repr([("id", "=", 0)])
    ensure_rule("youdoo_ai_mail_tpl_" + _role, _gid, "mail.template", _domain)

g_ro = ensure_group("Youdoo AI / Read Only")
for tech in READ_MODELS:
    ensure_access("youdoo_ai_ro_" + tech.replace(".", "_"), g_ro, tech, {"read": 1})

print("\n=== TÀI KHOẢN ===")
def gid_by_full_name(full):
    for g in call("res.groups", "search_read", [[]], {"fields": ["id", "full_name"]}):
        if g["full_name"] == full: return g["id"]
    sys.exit("Không tìm thấy nhóm: %s" % full)

BASE_USER = call("ir.model.data", "search_read",
                 [[["module", "=", "base"], ["name", "=", "group_user"]]],
                 {"fields": ["res_id"]})[0]["res_id"]

PLAN = {
    "ai-readonly":   [BASE_USER, g_ro],
    "ai-admin":      [BASE_USER, g_mail, g_act] + [gid_by_full_name(n) for n in (
        "Inventory / Administrator", "Accounting / Administrator", "Sales / Administrator",
        "Purchase / Administrator", "Manufacturing / Administrator", "Contact / Creation",
        "Role / Administrator")],
    "ai-warehouse":  [BASE_USER, g_mail, g_act] + ([g_mail_role["warehouse"]]
                                            if "warehouse" in g_mail_role else []) + [
        gid_by_full_name(n) for n in ("Inventory / User", "Contact / Creation")],
    "ai-accounting": [BASE_USER, g_mail, g_sinv, g_act] + ([g_mail_role["accounting"]]
                                                    if "accounting" in g_mail_role else []) + [
        gid_by_full_name(n) for n in ("Accounting / Invoicing", "Contact / Creation")],
}

for login, gids in PLAN.items():
    ex = call("res.users", "search_read", [[["login", "=", login]]],
              {"fields": ["id"], "context": {"active_test": False}})
    # "active" chỉ đặt lúc TẠO. Không đặt lại trên nhánh cập nhật: một operator
    # có thể đã chủ động vô hiệu hoá tài khoản AI này trong Odoo (đó là công
    # tắc tắt DUY NHẤT các tài khoản này có) — script "idempotent" ghi đè
    # active=True mỗi lần chạy lại sẽ âm thầm bật lại nó, xoá mất công tắc.
    vals = {"group_ids": [(6, 0, sorted(set(gids)))]}
    if ex:
        call("res.users", "write", [[ex[0]["id"]], vals]); print("  cập nhật:", login, "uid", ex[0]["id"])
    else:
        vals |= {"name": "AI " + login.replace("ai-", "").title(), "login": login,
                 "password": NEW_PWD, "active": True}
        print("  TẠO:", login, "uid", call("res.users", "create", [vals]))
