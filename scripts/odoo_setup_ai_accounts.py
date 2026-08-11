# scripts/odoo_setup_ai_accounts.py
"""Tạo 4 tài khoản AI + 3 nhóm quyền tuỳ chỉnh cho kiến trúc phân vai.

IDEMPOTENT: chạy lại không tạo trùng. KHÔNG sửa/xoá tài khoản có sẵn.
Chạy: backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py
"""
import os
import sys
import xmlrpc.client

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
    "ai-admin":      [BASE_USER, g_mail] + [gid_by_full_name(n) for n in (
        "Inventory / Administrator", "Accounting / Administrator", "Sales / Administrator",
        "Purchase / Administrator", "Manufacturing / Administrator", "Contact / Creation",
        "Role / Administrator")],
    "ai-warehouse":  [BASE_USER, g_mail] + [gid_by_full_name(n) for n in (
        "Inventory / User", "Contact / Creation")],
    "ai-accounting": [BASE_USER, g_mail, g_sinv] + [gid_by_full_name(n) for n in (
        "Accounting / Invoicing", "Contact / Creation")],
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
