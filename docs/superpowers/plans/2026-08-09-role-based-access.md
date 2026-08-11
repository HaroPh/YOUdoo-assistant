# Phân quyền theo vai — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent thôi chạy bằng tài khoản Odoo cá nhân có quyền Administrator; thay bằng 4 tài khoản AI riêng, vai suy từ tài khoản đăng nhập Open WebUI, và quyền được cưỡng chế ở tầng Odoo chứ không chỉ ở tầng LLM.

**Architecture:** Ba tầng danh tính (đăng nhập → ánh xạ vai phía server → credential Odoo theo vai). Ba tiến trình MCP cô lập, mỗi tiến trình chỉ nắm credential của vai mình. Backend dựng 3 graph dùng chung `llms`/pool/checkpointer, lọc tool theo vai; Odoo là lớp cưỡng chế cuối.

**Tech Stack:** Python, LangGraph, FastAPI, Odoo XML-RPC, Open WebUI (Docker), PowerShell (script dev).

## Global Constraints

- **KHÔNG sửa `mcp-servers/odoo/`.** `MCP_ODOO_PORT`, `ODOO_USERNAME`, `ODOO_PASSWORD` đã lấy từ env ⇒ 3 tiến trình chỉ là 3 bộ biến môi trường.
- **Vai KHÔNG được là tham số tool** (LLM điền được ⇒ bảo mật giả) và **KHÔNG được là model trong dropdown** (người dùng tự chọn ⇒ tự khai).
- **Ánh xạ khoá theo `x-openwebui-user-id` (chuỗi mờ), KHÔNG theo email/tên** — quyết định PII tại `main.py:114-118`.
- **Fail-closed:** tool không được khai báo trạng thái ⇒ `denied`. Người dùng không có trong bảng ánh xạ ⇒ từ chối, KHÔNG mặc định thành admin.
- Trạng thái quyền: `own` (Đ) · `needs_sign_off` (X) · `other_dept` (E) · `denied` (K). Vòng này: X xử lý **như** Đ kèm ghi chú; E và K đều từ chối (E nêu rõ bộ phận phụ trách).
- Quyền trên tài khoản Odoo = tập `own` ∪ `needs_sign_off`. E và K **không** có quyền ⇒ Odoo cưỡng chế.
- Test suite baseline: `1214 passed, 4 skipped, 46 deselected`.
- Live-verify TRƯỚC merge, trên worktree của nhánh.

---

### Task 1: Tài khoản Odoo và 2 nhóm quyền tuỳ chỉnh

**Files:**
- Create: `scripts/odoo_setup_ai_accounts.py`

**Interfaces:**
- Produces: 4 tài khoản Odoo (`ai-readonly`, `ai-admin`, `ai-warehouse`, `ai-accounting`, mật khẩu lấy từ biến môi trường `AI_ACCOUNT_PASSWORD`) và 2 nhóm `Youdoo AI / Mail`, `Youdoo AI / Read Only`. Task 2 và Task 8 dùng các login này trong env.

> **⚠️ Task này thay đổi cấu hình Odoo thật.** Nếu môi trường tự động bị chặn quyền, DỪNG và báo người dùng chạy tay — không tìm đường lách.

**Bối cảnh:** nhóm mặc định của Odoo KHÔNG đủ (đo 2026-08-09): `mail.mail` và `ir.config_parameter` **chỉ** do `Role / Administrator` cấp, nên mọi vai gửi mail sẽ phải là admin nếu không có nhóm hẹp. Odoo cũng không có nhóm "chỉ đọc" (mọi nhóm `*/User` cấp đọc **và** ghi).

- [ ] **Step 1: Viết script tạo nhóm + tài khoản (idempotent)**

```python
# scripts/odoo_setup_ai_accounts.py
"""Tạo 4 tài khoản AI + 2 nhóm quyền tuỳ chỉnh cho kiến trúc phân vai.

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
    "ai-accounting": [BASE_USER, g_mail] + [gid_by_full_name(n) for n in (
        "Accounting / Invoicing", "Contact / Creation")],
}

for login, gids in PLAN.items():
    ex = call("res.users", "search_read", [[["login", "=", login]]],
              {"fields": ["id"], "context": {"active_test": False}})
    vals = {"group_ids": [(6, 0, sorted(set(gids)))], "active": True}
    if ex:
        call("res.users", "write", [[ex[0]["id"]], vals]); print("  cập nhật:", login, "uid", ex[0]["id"])
    else:
        vals |= {"name": "AI " + login.replace("ai-", "").title(), "login": login, "password": NEW_PWD}
        print("  TẠO:", login, "uid", call("res.users", "create", [vals]))
print("\nMật khẩu:", NEW_PWD)
```

- [ ] **Step 2: Chạy script**

```bash
cd d:/Youdoo && set -a && . ./.env && set +a && backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py
```

Nếu bị chặn quyền: DỪNG, báo người dùng chạy tay, đừng dùng công cụ khác để lách.

- [ ] **Step 3: Xác minh bằng đăng nhập THẬT từng tài khoản**

```bash
cd d:/Youdoo && set -a && . ./.env && set +a && backend/.venv/Scripts/python.exe -c "
import os, xmlrpc.client
URL=os.environ['ODOO_URL']; DB=os.environ['ODOO_DB']; PWD=os.environ['AI_ACCOUNT_PASSWORD']
for login in ['ai-readonly','ai-admin','ai-warehouse','ai-accounting']:
    uid = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/common').authenticate(DB, login, PWD, {})
    o = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/object')
    def ha(model, op): return o.execute_kw(DB, uid, PWD, model, 'has_access', [[], op], {})
    print('%-15s uid=%-4s | mail.mail(write)=%-5s | acc.move(write)=%-5s | stock.quant(write)=%-5s | cfg_param(read)=%s' % (
        login, uid, ha('mail.mail','write'), ha('account.move','write'),
        ha('stock.quant','write'), ha('ir.config_parameter','read')))
"
```

ĐẠT khi:
- `ai-admin`: mail=True, account.move=True, stock.quant=True, cfg=True
- `ai-warehouse`: mail=True, account.move=**False**, stock.quant=True, cfg=True
- `ai-accounting`: mail=True, account.move=True, stock.quant=**False**, cfg=True
- `ai-readonly`: mail=**False**, account.move=**False**, stock.quant=**False**, cfg=True

Hai ô `False` in đậm ở warehouse/accounting là bằng chứng cưỡng chế thật. Nếu chúng ra True, nhóm quyền sai — DỪNG, báo cáo, đừng đi tiếp.

- [ ] **Step 4: Commit**

```bash
git add scripts/odoo_setup_ai_accounts.py
git commit -m "feat(odoo): script tạo 4 tài khoản AI + 2 nhóm quyền tuỳ chỉnh"
```

---

### Task 2: Nhịp 1a — chuyển sang `ai-admin`, chứng minh không hồi quy

**Files:**
- Modify: `.env`, `backend/.env`

**Interfaces:**
- Consumes: tài khoản `ai-admin` từ Task 1.
- Produces: hệ thống chạy dưới `ai-admin`; Task 8 sẽ tách tiếp theo vai.

**Bối cảnh:** đã đo — `ai-admin` phủ 0/57 phép đo bị thiếu, chỉ kém tài khoản cá nhân 3 nhóm (`Multi Companies`, `Dashboard / Admin`, `Maintenance / Equipment Manager`) mà **không tool nào chạm tới**. Nên đây là thay đổi chức năng-không-đổi.

- [ ] **Step 1: Đổi credential trong cả 2 file .env**

Trong `.env` và `backend/.env`, đổi:

```
ODOO_USERNAME=phamhao14170@gmail.com
ODOO_PASSWORD=14170Asd
```

thành:

```
ODOO_USERNAME=ai-admin
ODOO_PASSWORD=${AI_ACCOUNT_PASSWORD}
```

- [ ] **Step 2: Khởi động lại backend + mcp-odoo, kiểm tra health**

Dừng tiến trình đang giữ cổng 8002/8003, khởi động lại, xác nhận
`GET http://localhost:8002/health` trả `agent_ready = true`.

- [ ] **Step 3: Chạy lại chuỗi nghiệp vụ chính qua API thật**

Gửi qua `/v1/chat/completions` (resend toàn bộ lịch sử mỗi lượt, KHÔNG dùng
`session_id`): tạo báo giá cho một khách thật → xác nhận đơn → giao hàng →
tạo hoá đơn → phát hành. Rồi gửi 1 mail xác nhận đơn.

ĐẠT khi mọi bước cho kết quả như trước khi đổi tài khoản.

- [ ] **Step 4: Chứng minh vấn đề nhật ký đã đóng**

```bash
cd d:/Youdoo && set -a && . ./.env && set +a && backend/.venv/Scripts/python.exe -c "
import os, xmlrpc.client
URL=os.environ['ODOO_URL']; DB=os.environ['ODOO_DB']; U=os.environ['ODOO_USERNAME']; P=os.environ['ODOO_PASSWORD']
uid = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/common').authenticate(DB,U,P,{})
o = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/object')
r = o.execute_kw(DB,uid,P,'sale.order','search_read',[[]],{'fields':['name','create_uid'],'order':'id desc','limit':3})
for x in r: print(x['name'], '| tạo bởi:', x['create_uid'][1])
"
```

ĐẠT khi đơn vừa tạo ở Step 3 hiện `tạo bởi: AI Admin`, KHÔNG phải tên cá nhân.

- [ ] **Step 5: Commit ghi chú (KHÔNG commit .env — đang gitignore)**

```bash
git commit --allow-empty -m "chore(1a): agent chuyển sang tài khoản ai-admin

.env không được track (gitignore). Ghi nhận mốc: từ đây create_uid trong
Odoo phân biệt được AI với người thật."
```

---

### Task 3: `roles.py` — cấu hình vai và chính sách

**Files:**
- Create: `backend/src/agents/roles.py`
- Test: `backend/tests/agents/test_roles.py`

**Interfaces:**
- Produces (Task 4-6 dùng):
  - Hằng trạng thái: `OWN`, `NEEDS_SIGN_OFF`, `OTHER_DEPT`, `DENIED` (đều là `str`)
  - `RoleCfg(name, label, mcp_url, own, needs_sign_off, other_dept, unrestricted=False)` — frozen dataclass; `own`/`needs_sign_off`/`other_dept` là `frozenset[str]`
  - `RoleCfg.state_of(tool: str) -> str`
  - `RoleCfg.allowed_tools() -> frozenset[str]`
  - `load_profile(name: str) -> dict[str, RoleCfg]` — trả `{role_name: RoleCfg}`
  - `role_for_user(user_id: str | None) -> str | None` — `None` = không xác định được vai
  - `PROFILES: dict[str, dict[str, RoleCfg]]` với 2 khoá `"small-business"`, `"enterprise"`

- [ ] **Step 1: Viết test (đỏ trước)**

```python
# backend/tests/agents/test_roles.py
import pytest
from src.agents import roles


def test_tool_khong_khai_bao_thi_mac_dinh_bi_tu_choi():
    """Fail-closed: quên khai báo một tool = tool đó bị CẤM, không phải được
    phép. Nếu mặc định là 'own', thêm tool mới vào hệ thống sẽ âm thầm cấp nó
    cho mọi vai — đúng lớp lỗi mà toàn bộ thiết kế này sinh ra để ngăn."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset(),
                        other_dept=frozenset())
    assert cfg.state_of("a") == roles.OWN
    assert cfg.state_of("tool_chua_ton_tai") == roles.DENIED


def test_allowed_tools_gom_own_va_needs_sign_off_khong_gom_other_dept():
    """Quyền trên tài khoản Odoo = own ∪ needs_sign_off. other_dept KHÔNG nằm
    trong đó — đó chính là chỗ Odoo cưỡng chế."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset({"b"}),
                        other_dept=frozenset({"c"}))
    assert cfg.allowed_tools() == frozenset({"a", "b"})
    assert cfg.state_of("c") == roles.OTHER_DEPT


def test_vai_admin_khong_bi_gioi_han():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert cfg.unrestricted is True
    assert cfg.state_of("bat_ky_tool_nao") == roles.OWN
    assert cfg.allowed_tools() is None   # None = không lọc


def test_warehouse_khong_duoc_phat_hanh_hoa_don():
    """Từ phỏng vấn thật (câu 22): post_invoice với kho là 'việc phòng khác'."""
    cfg = roles.PROFILES["small-business"]["warehouse"]
    assert cfg.state_of("post_invoice") == roles.OTHER_DEPT
    assert "post_invoice" not in cfg.allowed_tools()


def test_accounting_duoc_phat_hanh_hoa_don_nhung_can_duyet():
    """Phỏng vấn A2 câu 1 = X: việc của mình, nhưng kế toán trưởng ký.
    Khác hẳn kho — cùng một tool, hai trạng thái khác nhau. Đây là phép đo
    chứng minh 2 vai thật sự khác nhau."""
    cfg = roles.PROFILES["small-business"]["accounting"]
    assert cfg.state_of("post_invoice") == roles.NEEDS_SIGN_OFF
    assert "post_invoice" in cfg.allowed_tools()


def test_ho_so_enterprise_go_quyen_khoi_vai_kho():
    """Hồ sơ enterprise phải khiến nghiệp vụ RỜI tập own∪needs_sign_off —
    chỉ khi đó quyền mới bị gỡ khỏi tài khoản Odoo. Chuyển other_dept→denied
    KHÔNG đổi gì ở tầng Odoo (cả hai đều là 'không có quyền')."""
    small = roles.PROFILES["small-business"]["warehouse"]
    ent = roles.PROFILES["enterprise"]["warehouse"]
    assert "inventory_adjustment" in small.allowed_tools()
    assert "inventory_adjustment" not in ent.allowed_tools()


def test_user_khong_co_trong_bang_anh_xa_thi_khong_co_vai(monkeypatch):
    """Fail-closed: người lạ KHÔNG được mặc định thành admin."""
    monkeypatch.setenv("YOUDOO_ROLE_MAP", "abc:admin")
    assert roles.role_for_user("abc") == "admin"
    assert roles.role_for_user("nguoi_la") is None
    assert roles.role_for_user(None) is None


def test_bang_anh_xa_rong_thi_khong_ai_co_vai(monkeypatch):
    monkeypatch.delenv("YOUDOO_ROLE_MAP", raising=False)
    assert roles.role_for_user("bat_ky") is None
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_roles.py`
Expected: FAIL — `ModuleNotFoundError: src.agents.roles`

- [ ] **Step 3: Viết `roles.py`**

```python
# backend/src/agents/roles.py
"""Cấu hình vai và chính sách quyền — spec 2026-08-09-role-based-access.

BỐN TRẠNG THÁI, không phải hai. Phỏng vấn nhân viên kho thật (2026-08-09,
docs/role-permission-interview.md) cho 13 câu Đ, 11 câu X, 0 câu K: ở doanh
nghiệp nhỏ gần như không có gì bị cấm tuyệt đối. Nhưng hai chữ X không cùng
nghĩa — "việc của tôi, cần sếp ký" khác hẳn "việc phòng khác, xin thì được":
cái đầu cần LUỒNG DUYỆT, cái sau cần BÀN GIAO. Gộp chúng làm một là lý do
bản thiết kế đầu tiên khiến vai kho và vai kế toán trông giống nhau.

QUYỀN TRÊN TÀI KHOẢN ODOO = own ∪ needs_sign_off. other_dept và denied KHÔNG
có quyền — đó là chỗ Odoo cưỡng chế thật. Hệ quả: sức mạnh lớp cưỡng chế tỉ
lệ thuận với số nghiệp vụ tổ chức xếp ra ngoài tập đó, nên hồ sơ
'small-business' (gần như không có) cưỡng chế yếu — đúng chính sách của nó,
không phải khuyết điểm kiến trúc.

FAIL-CLOSED: tool không khai báo = denied. Thêm tool mới vào hệ thống mà quên
khai báo sẽ khiến nó bị CẤM, không phải được cấp cho mọi vai."""
import os
from dataclasses import dataclass, field

OWN = "own"
NEEDS_SIGN_OFF = "needs_sign_off"
OTHER_DEPT = "other_dept"
DENIED = "denied"


@dataclass(frozen=True)
class RoleCfg:
    name: str
    label: str
    mcp_url: str
    own: frozenset = field(default_factory=frozenset)
    needs_sign_off: frozenset = field(default_factory=frozenset)
    other_dept: frozenset = field(default_factory=frozenset)
    unrestricted: bool = False        # chỉ vai admin

    def state_of(self, tool: str) -> str:
        if self.unrestricted:
            return OWN
        if tool in self.own:
            return OWN
        if tool in self.needs_sign_off:
            return NEEDS_SIGN_OFF
        if tool in self.other_dept:
            return OTHER_DEPT
        return DENIED                 # fail-closed — xem docstring module

    def allowed_tools(self):
        """Tập tool được phép gọi. None = không lọc (vai admin)."""
        if self.unrestricted:
            return None
        return self.own | self.needs_sign_off


# ── Nghiệp vụ theo vai, suy trực tiếp từ phiếu phỏng vấn đã điền ────────────
# Kho: A1.1-A1.4 là địa hạt của họ (Đ hoặc X); A1.5 "Ngoài phạm vi kho" nên
# mọi X trong mục đó là OTHER_DEPT, không phải NEEDS_SIGN_OFF.
_WH_OWN = frozenset({
    "deliver_order", "receive_order", "validate_picking", "internal_transfer",
    "inventory_adjustment", "scrap_product",
})
_WH_SIGN_OFF = frozenset({"return_order", "send_delivery_email"})
_WH_OTHER = frozenset({
    "create_quotation", "create_rfq", "post_invoice", "confirm_sale_order",
    "register_payment", "create_credit_memo", "confirm_purchase_order",
})

_ACC_OWN = frozenset({
    "create_credit_memo", "send_invoice_email", "create_invoice_from_order",
    "create_bill_from_po",
})
_ACC_SIGN_OFF = frozenset({"post_invoice", "register_payment"})
_ACC_OTHER = frozenset({
    "deliver_order", "receive_order", "validate_picking", "internal_transfer",
    "inventory_adjustment", "scrap_product", "return_order",
    "create_quotation", "create_rfq",
})

MCP_ADMIN = os.environ.get("MCP_ODOO_URL", "http://localhost:8003/sse")
MCP_WAREHOUSE = os.environ.get("MCP_ODOO_URL_WAREHOUSE", "http://localhost:8004/sse")
MCP_ACCOUNTING = os.environ.get("MCP_ODOO_URL_ACCOUNTING", "http://localhost:8005/sse")

PROFILES = {
    "small-business": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg("warehouse", "Kho", MCP_WAREHOUSE,
                             own=_WH_OWN, needs_sign_off=_WH_SIGN_OFF,
                             other_dept=_WH_OTHER),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF,
                              other_dept=_ACC_OTHER),
    },
    # Doanh nghiệp lớn chia nhỏ trách nhiệm: 3 nghiệp vụ RỜI tập own∪sign_off
    # của vai kho ⇒ quyền bị gỡ khỏi tài khoản Odoo (khác với việc chỉ đổi
    # other_dept↔denied, vốn không đổi gì ở tầng Odoo).
    "enterprise": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg(
            "warehouse", "Kho", MCP_WAREHOUSE,
            own=frozenset({"deliver_order", "receive_order", "validate_picking",
                           "internal_transfer"}),
            needs_sign_off=frozenset({"send_delivery_email"}),
            other_dept=_WH_OTHER | frozenset({"inventory_adjustment",
                                              "scrap_product", "return_order"})),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF,
                              other_dept=_ACC_OTHER),
    },
}


def load_profile(name: str | None = None) -> dict:
    return PROFILES[name or os.environ.get("YOUDOO_POLICY_PROFILE", "small-business")]


def role_for_user(user_id):
    """Ánh xạ user_id (chuỗi mờ từ header Open WebUI) → tên vai.

    Khoá theo user_id, KHÔNG theo email/tên — quyết định PII tại main.py.
    Trả None khi không xác định được: KHÔNG mặc định thành admin (fail-closed).

    Định dạng YOUDOO_ROLE_MAP: "id1:admin,id2:warehouse,id3:accounting"
    """
    if not user_id:
        return None
    raw = os.environ.get("YOUDOO_ROLE_MAP", "")
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        uid, _, role = pair.partition(":")
        if uid.strip() == str(user_id).strip():
            return role.strip() or None
    return None
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_roles.py -v`
Expected: 8 test PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/roles.py backend/tests/agents/test_roles.py
git commit -m "feat(roles): RoleCfg 4 trạng thái + 2 hồ sơ chính sách, fail-closed"
```

---

### Task 4: `ERPAgent` dựng 3 graph, `chat()` nhận vai

**Files:**
- Modify: `backend/src/agents/erp_agent.py:127-158` (`__init__`, `setup`), `:159-215` (`chat`)
- Test: `backend/tests/agents/test_erp_agent_roles.py`

**Interfaces:**
- Consumes (Task 3): `roles.load_profile()`, `RoleCfg.mcp_url`, `RoleCfg.allowed_tools()`.
- Produces: `ERPAgent.graphs: dict[str, CompiledGraph]`, `ERPAgent.chat(messages, thread_id=None, reset_if_fresh=False, role="admin")`.

- [ ] **Step 1: Viết test (đỏ trước)**

```python
# backend/tests/agents/test_erp_agent_roles.py
import pytest
from src.agents import roles


def test_loc_tool_theo_vai_bo_tool_ngoai_quyen():
    """Bộ lọc backend là lớp UX/chính xác (lớp cưỡng chế thật là Odoo).
    Vai kho không được thấy post_invoice trong danh sách tool."""
    from src.agents.erp_agent import _filter_tools_for_role

    class T:
        def __init__(self, name): self.name = name

    tools = [T("deliver_order"), T("post_invoice"), T("validate_picking")]
    cfg = roles.PROFILES["small-business"]["warehouse"]
    kept = [t.name for t in _filter_tools_for_role(tools, cfg)]
    assert "deliver_order" in kept
    assert "validate_picking" in kept
    assert "post_invoice" not in kept


def test_vai_admin_giu_nguyen_moi_tool():
    from src.agents.erp_agent import _filter_tools_for_role

    class T:
        def __init__(self, name): self.name = name

    tools = [T("deliver_order"), T("post_invoice")]
    cfg = roles.PROFILES["small-business"]["admin"]
    assert len(_filter_tools_for_role(tools, cfg)) == 2
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_erp_agent_roles.py`
Expected: FAIL — `ImportError: cannot import name '_filter_tools_for_role'`

- [ ] **Step 3: Thêm hàm lọc + dựng nhiều graph trong `setup()`**

Thêm import ở đầu `erp_agent.py`:

```python
from . import roles as roles_mod
```

Thêm hàm module-level ngay trước `class ERPAgent`:

```python
def _filter_tools_for_role(tools, cfg):
    """Lọc tool xuống tập vai được phép. None = không lọc (vai admin).

    Đây là lớp UX/độ-chính-xác, KHÔNG phải lớp bảo mật: LLM chỉ thấy tool liên
    quan nên chọn đúng hơn (dự án đo tool_acc/dangerous_misroute). Lớp cưỡng
    chế thật là tài khoản Odoo của tiến trình MCP tương ứng — nếu bộ lọc này
    có bug, Odoo vẫn chặn."""
    allowed = cfg.allowed_tools()
    if allowed is None:
        return list(tools)
    return [t for t in tools if t.name in allowed]
```

Thay thân `setup()` (dòng 137-157) — giữ nguyên phần `_handler`/`_llms`/pool/checkpointer, chỉ đổi phần dựng graph:

```python
    async def setup(self) -> None:
        self._handler = tracing.get_handler()
        self._llms = make_llms()

        self._pool = AsyncConnectionPool(
            conninfo=PG_CONN,
            max_size=20,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await self._pool.open()
        checkpointer = AsyncPostgresSaver(self._pool)
        await checkpointer.setup()
        self._checkpointer = checkpointer

        # MỘT graph mỗi vai. llms/pool/checkpointer DÙNG CHUNG nên 3 graph gần
        # như không tốn thêm bộ nhớ; chỉ tool khác nhau. Mỗi vai nối tới tiến
        # trình MCP riêng — tiến trình đó nắm credential Odoo của vai, nên nó
        # KHÔNG THỂ làm việc ngoài quyền dù graph có gọi nhầm.
        self.graphs = {}
        for role_name, cfg in roles_mod.load_profile().items():
            client = MultiServerMCPClient(
                {"odoo": {"url": cfg.mcp_url, "transport": "sse"}}
            )
            tools = _filter_tools_for_role(await client.get_tools(), cfg)
            if role_name == "admin":
                self.tool_names = [t.name for t in tools]
            self.graphs[role_name] = build_graph(self._llms, tools, checkpointer)
```

Trong `__init__` (dòng 129-135), thay `self.graph = None` bằng:

```python
        self.graphs: dict = {}
```

- [ ] **Step 4: Cho `chat()` nhận vai**

Đổi chữ ký (dòng 159-160):

```python
    async def chat(self, messages: list[dict], thread_id: str | None = None,
                   reset_if_fresh: bool = False, role: str = "admin") -> str:
```

Ngay sau `if not messages: return "Vui lòng nhập câu hỏi."` (dòng 173-174), thêm:

```python
        graph = self.graphs.get(role)
        if graph is None:
            return "Không xác định được quyền truy cập của bạn. Liên hệ quản trị viên."
```

Rồi thay **mọi** `self.graph` trong thân `chat()` bằng `graph` (4 chỗ: dòng
191 `aget_state`, 197 `ainvoke(Command(resume=False))`, 207 `ainvoke(decision)`,
và trong `_invoke_fresh`). Với `_invoke_fresh`, thêm tham số:

```python
    async def _invoke_fresh(self, messages, config, graph=None):
        ...
        return await (graph or self.graphs["admin"]).ainvoke({"messages": reset}, config=config)
```

và mọi lời gọi trong `chat()` truyền `graph`: `await self._invoke_fresh(messages, config, graph)`.

- [ ] **Step 5: Chạy test + toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_erp_agent_roles.py -v`
Expected: 2 PASS.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration" 2>&1 | tail -3`
Expected: 1224 passed (baseline 1214 + 8 Task 3 + 2 Task 4).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/erp_agent.py backend/tests/agents/test_erp_agent_roles.py
git commit -m "feat(agent): dựng 1 graph mỗi vai, chat() nhận role, lọc tool theo vai"
```

---

### Task 5: `main.py` — suy vai từ header, đưa vai vào `thread_id`

**Files:**
- Modify: `backend/src/main.py:100-124` (`_derive_thread_id`), `:127-160` (`chat_completions`)
- Test: `backend/tests/test_main_roles.py`

**Interfaces:**
- Consumes (Task 3): `roles.role_for_user(user_id)`.
- Consumes (Task 4): `agent.chat(..., role=...)`.

**Bối cảnh — cạm bẫy bắt buộc đóng:** `thread_id` hiện KHÔNG mang vai. Nếu một
câu xác nhận đang treo ở vai `warehouse` mà người dùng đổi vai rồi trả lời "có",
LangGraph sẽ resume interrupt trong graph **không có node đó**.

- [ ] **Step 1: Viết test (đỏ trước)**

```python
# backend/tests/test_main_roles.py
from src.main import _derive_thread_id, _role_from_headers


class H(dict):
    def get(self, k, d=None): return dict.get(self, k, d)


def test_thread_id_mang_vai_de_doi_vai_khong_resume_nham_graph():
    """Cạm bẫy: đổi vai giữa lúc một câu xác nhận đang treo sẽ khiến LangGraph
    resume interrupt trong graph không có node đó. Đưa vai vào thread_id ⇒ đổi
    vai = sang luồng mới."""
    body, msgs = {"session_id": "s1"}, [{"role": "user", "content": "x"}]
    a = _derive_thread_id(body, msgs, headers=None, role="warehouse")
    b = _derive_thread_id(body, msgs, headers=None, role="accounting")
    assert a != b
    assert "warehouse" in a


def test_khong_co_header_thi_khong_suy_ra_vai():
    """Fail-closed: thiếu header (vd chưa bật ENABLE_FORWARD_USER_INFO_HEADERS)
    KHÔNG được mặc định thành admin."""
    assert _role_from_headers(None) is None
    assert _role_from_headers(H()) is None


def test_suy_vai_tu_user_id_qua_bang_anh_xa(monkeypatch):
    monkeypatch.setenv("YOUDOO_ROLE_MAP", "u-kho:warehouse")
    assert _role_from_headers(H({"x-openwebui-user-id": "u-kho"})) == "warehouse"
    assert _role_from_headers(H({"x-openwebui-user-id": "nguoi-la"})) is None
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/test_main_roles.py`
Expected: FAIL — `ImportError: cannot import name '_role_from_headers'`

- [ ] **Step 3: Thêm `_role_from_headers` + vai vào `thread_id`**

Thêm import ở đầu `main.py`:

```python
from src.agents import roles as roles_mod
```

Thêm hàm ngay trước `_derive_thread_id`:

```python
def _role_from_headers(headers):
    """Suy vai từ tài khoản đăng nhập Open WebUI.

    CHỈ đọc x-openwebui-user-id (chuỗi mờ) — name/email/role là PII, không bao
    giờ được đọc (xem docstring _derive_thread_id). Vai KHÔNG lấy từ body: mọi
    thứ trong body đều do client gửi, tức tự khai được.

    Trả None khi không xác định được — gọi tầng trên phải TỪ CHỐI, không được
    mặc định thành admin."""
    if headers is None:
        return None
    return roles_mod.role_for_user(headers.get("x-openwebui-user-id"))
```

Đổi chữ ký `_derive_thread_id` (dòng 100) thành:

```python
def _derive_thread_id(body: dict, messages: list[dict], headers=None,
                      role: str | None = None) -> str | None:
```

và bọc giá trị trả về: thay 3 câu `return` trong thân hàm bằng cách tính
`base` rồi trả `f"{role or 'norole'}:{base}"`. Cụ thể, thay toàn bộ thân hàm
(sau docstring) bằng:

```python
    if headers is not None:
        chat_id = headers.get("x-openwebui-chat-id")
        if chat_id:
            user_id = headers.get("x-openwebui-user-id") or "anon"
            return f"{role or 'norole'}:owui:{user_id}:{chat_id}"
    if _explicit_session(body):
        return f"{role or 'norole'}:" + str(body.get("session_id") or body.get("id"))
    first_user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    if not first_user:
        return None
    return (f"{role or 'norole'}:conv-"
            + hashlib.sha1(first_user.encode("utf-8")).hexdigest()[:16])
```

Bổ sung vào docstring của `_derive_thread_id` một dòng:

```
      0. Vai (role) là TIỀN TỐ của mọi phương án dưới đây — đổi vai phải sang
         luồng mới, nếu không một câu xác nhận đang treo ở vai cũ sẽ bị resume
         trong graph của vai mới (graph đó không có node tương ứng).
```

- [ ] **Step 4: Nối vai vào `chat_completions`**

Trong `chat_completions`, thay dòng 145-146:

```python
            thread_id = _derive_thread_id(body, messages, headers=req.headers)
            answer = await agent.chat(messages, thread_id=thread_id,
```

bằng:

```python
            role = _role_from_headers(req.headers)
            if role is None:
                role = os.environ.get("YOUDOO_FALLBACK_ROLE") or None
            if role is None:
                answer = ("Không xác định được quyền truy cập của bạn. "
                          "Vui lòng đăng nhập bằng tài khoản đã được cấp vai, "
                          "hoặc liên hệ quản trị viên.")
            else:
                thread_id = _derive_thread_id(body, messages, headers=req.headers,
                                              role=role)
                answer = await agent.chat(messages, thread_id=thread_id, role=role,
```

*(giữ nguyên các tham số còn lại của lời gọi `agent.chat` ở dòng kế tiếp, và
thụt lề khối `else` cho khớp)*

`YOUDOO_FALLBACK_ROLE` cho phép môi trường dev chưa bật header vẫn chạy được —
nhưng phải **khai báo tường minh**, không có giá trị mặc định ngầm.

- [ ] **Step 5: Chạy test + toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/test_main_roles.py -v`
Expected: 3 PASS.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration" 2>&1 | tail -3`
Expected: 1227 passed. **Nếu có test cũ đỏ vì `thread_id` đổi định dạng: đó là
hồi quy thật, phải sửa test cho khớp thiết kế mới — nhưng báo cáo rõ test nào.**

- [ ] **Step 6: Commit**

```bash
git add backend/src/main.py backend/tests/test_main_roles.py
git commit -m "feat(main): suy vai từ tài khoản đăng nhập, đưa vai vào thread_id"
```

---

### Task 6: Prompt sinh động từ tập tool của vai

**Files:**
- Modify: `backend/src/agents/prompts.py`, `backend/src/agents/nodes.py`
- Test: `backend/tests/agents/test_prompt_per_role.py`

**Interfaces:**
- Consumes (Task 3): `RoleCfg.allowed_tools()`, `RoleCfg.state_of()`, `RoleCfg.label`.
- Produces: `prompts.planner_prompt_for(cfg) -> str`.

**Bối cảnh:** viết tay 3 prompt cứng sẽ trôi lệch khỏi `RoleCfg` — đúng lớp lỗi
đã bắt được ở `mail-trigger-points` (`WRITE_TOOL_NAMES` trong eval thiếu 4 tool
mail khiến chỉ số "misroute nguy hiểm" mù với đúng những tool gửi mail ra ngoài).
Một nguồn sự thật duy nhất.

- [ ] **Step 1: Viết test (đỏ trước)**

```python
# backend/tests/agents/test_prompt_per_role.py
from src.agents import roles
from src.agents.prompts import planner_prompt_for, WRITE_PLANNER_PROMPT


def test_prompt_vai_kho_khong_liet_ke_tool_ngoai_quyen():
    cfg = roles.PROFILES["small-business"]["warehouse"]
    p = planner_prompt_for(cfg)
    assert "deliver_order" in p
    assert "post_invoice(" not in p


def test_prompt_vai_admin_giu_nguyen_ban_goc():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert planner_prompt_for(cfg) == WRITE_PLANNER_PROMPT


def test_prompt_neu_ra_bo_phan_phu_trach_cho_viec_ngoai_quyen():
    """Vai kho bị từ chối post_invoice thì phải biết chỉ sang đâu — nếu không,
    người dùng chỉ nhận 'không làm được' mà không biết làm gì tiếp."""
    cfg = roles.PROFILES["small-business"]["warehouse"]
    p = planner_prompt_for(cfg)
    assert "post_invoice" in p           # vẫn nhắc tên, nhưng để TỪ CHỐI
    assert "Kế toán" in p
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_prompt_per_role.py`
Expected: FAIL — `ImportError: cannot import name 'planner_prompt_for'`

- [ ] **Step 3: Thêm `planner_prompt_for` vào `prompts.py`**

Thêm vào cuối `prompts.py`:

```python
def planner_prompt_for(cfg) -> str:
    """WRITE_PLANNER_PROMPT rút gọn theo vai.

    Sinh từ chính RoleCfg thay vì viết tay 3 bản — nếu viết tay, danh sách tool
    trong prompt sẽ trôi lệch khỏi tập tool thật (lớp lỗi đã gặp ở
    mail-trigger-points: WRITE_TOOL_NAMES thiếu 4 tool mail khiến chỉ số eval
    'misroute nguy hiểm' mù với đúng những tool gửi mail ra ngoài).

    Vai admin dùng nguyên bản gốc — không lọc gì."""
    from .roles import OTHER_DEPT

    allowed = cfg.allowed_tools()
    if allowed is None:
        return WRITE_PLANNER_PROMPT

    kept = []
    for line in WRITE_PLANNER_PROMPT.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and "(" in stripped:
            tool = stripped[2:].split("(", 1)[0].strip()
            if tool and tool not in allowed:
                continue
        kept.append(line)

    kept.append("")
    kept.append(f"# BẠN ĐANG Ở VAI: {cfg.label}")

    sign_off = sorted(cfg.needs_sign_off)
    if sign_off:
        # Vòng này CHƯA có luồng duyệt thật (spec §9). Vẫn cho thực hiện để
        # không mất năng lực hiện có, nhưng phải nói rõ thực tế cần cấp trên
        # duyệt — im lặng sẽ khiến người dùng tưởng đã đủ thẩm quyền.
        kept.append("# Các việc sau thuộc vai này NHƯNG thực tế cần cấp trên duyệt.")
        kept.append("# Vẫn thực hiện được, nhưng khi làm hãy nhắc người dùng một câu")
        kept.append("# rằng theo quy định nội bộ việc này cần được duyệt:")
        for t in sign_off:
            kept.append(f"#   - {t}")

    other = sorted(cfg.other_dept)
    if other:
        kept.append("# Các việc sau KHÔNG thuộc quyền vai này. Nếu người dùng yêu cầu,")
        kept.append("# hãy TỪ CHỐI và nêu rõ bộ phận phụ trách, KHÔNG cố gọi tool:")
        for t in other:
            kept.append(f"#   - {t} → thuộc bộ phận {_DEPT_OF.get(t, 'khác')}")
    return "\n".join(kept)


# Bộ phận phụ trách từng nghiệp vụ — dùng để câu từ chối chỉ được sang đâu.
_DEPT_OF = {
    "post_invoice": "Kế toán", "register_payment": "Kế toán",
    "create_credit_memo": "Kế toán", "create_invoice_from_order": "Kế toán",
    "create_bill_from_po": "Kế toán",
    "create_quotation": "Bán hàng", "confirm_sale_order": "Bán hàng",
    "create_rfq": "Mua hàng", "confirm_purchase_order": "Mua hàng",
    "deliver_order": "Kho", "receive_order": "Kho", "validate_picking": "Kho",
    "internal_transfer": "Kho", "inventory_adjustment": "Kho",
    "scrap_product": "Kho", "return_order": "Kho",
}
```

- [ ] **Step 4: Dùng prompt theo vai khi dựng graph**

**(a)** Trong `backend/src/agents/nodes.py`, đổi chữ ký (dòng 222):

```python
def make_erp_write_planner_node(llm, planner_prompt=None):
```

và thay 2 dòng dùng prompt (dòng 235-236):

```python
        system = (render_working_context(wc) + "\n\n" + WRITE_PLANNER_PROMPT) \
            if wc else WRITE_PLANNER_PROMPT
```

bằng:

```python
        # planner_prompt = bản rút gọn theo vai (prompts.planner_prompt_for);
        # None = bản đầy đủ, giữ nguyên hành vi cũ cho test và vai admin.
        base_prompt = planner_prompt or WRITE_PLANNER_PROMPT
        system = (render_working_context(wc) + "\n\n" + base_prompt) \
            if wc else base_prompt
```

**(b)** Trong `backend/src/agents/graph.py`, đổi chữ ký (dòng 36):

```python
def build_graph(llm, tools, checkpointer, role_cfg=None) -> object:
```

và thay dòng 52:

```python
    g.add_node("erp_write_planner", make_erp_write_planner_node(llms["planner"]))
```

bằng:

```python
    from .prompts import planner_prompt_for
    g.add_node("erp_write_planner", make_erp_write_planner_node(
        llms["planner"],
        planner_prompt_for(role_cfg) if role_cfg is not None else None))
```

**(c)** Trong `backend/src/agents/erp_agent.py`, `setup()` (Task 4 Step 3), thay:

```python
            self.graphs[role_name] = build_graph(self._llms, tools, checkpointer)
```

bằng:

```python
            self.graphs[role_name] = build_graph(self._llms, tools, checkpointer,
                                                 role_cfg=cfg)
```

- [ ] **Step 5: Chạy test + toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_prompt_per_role.py -v`
Expected: 3 PASS.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration" 2>&1 | tail -3`
Expected: 1230 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py backend/src/agents/nodes.py backend/src/agents/graph.py backend/src/agents/erp_agent.py backend/tests/agents/test_prompt_per_role.py
git commit -m "feat(prompts): sinh danh sách tool theo vai từ RoleCfg, một nguồn sự thật"
```

---

### Task 7: `send_delivery_email` — mail báo đã xuất hàng

**Files:**
- Modify: `backend/src/agents/mail_write.py`, `backend/src/agents/write_registry.py`, `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_mail_write.py`

**Interfaces:**
- Consumes: `EmailCfg` và factory từ `mail-trigger-points` (đã merge).

**Bối cảnh:** Odoo có sẵn template `Shipping: Send by Email` trên `stock.picking`.
Phỏng vấn câu 17 = Đ (kho được gửi), câu 18 = X (cần duyệt) ⇒ trạng thái
`needs_sign_off`, đã khai báo trong `roles.py` Task 3.

- [ ] **Step 1: Thêm config**

Trong `mail_write.py`, thêm sau `INVOICE_EMAIL_CFG`:

```python
DELIVERY_EMAIL_CFG = EmailCfg(
    tool_name="send_delivery_email",
    template_name="Shipping: Send by Email",
    res_model="stock.picking",
    ref_arg="picking_ref",
    label="mail báo giao hàng",
    missing_ref_msg="Bạn cần cho biết mã phiếu kho cần gửi mail.")
```

và nối vào tuple:

```python
MAIL_COORDINATOR_CFGS = (ORDER_CONFIRMATION_CFG, QUOTATION_EMAIL_CFG,
                         RFQ_EMAIL_CFG, INVOICE_EMAIL_CFG, DELIVERY_EMAIL_CFG)
```

- [ ] **Step 2: Thêm dòng prompt**

Trong `prompts.py`, ngay sau dòng `send_invoice_email(...)`:

```
- send_delivery_email(picking_ref: str)  # gửi mail báo KHÁCH HÀNG đã xuất hàng/đang giao (template Odoo "Shipping: Send by Email"); picking_ref = mã phiếu kho, vd "WH/OUT/00011"; chỉ gọi khi user yêu cầu rõ ràng
```

- [ ] **Step 3: Cập nhật 2 test đếm cứng số config**

Trong `backend/tests/agents/test_mail_write.py` và
`backend/tests/agents/test_graph_build.py`, đổi mọi assertion `== 4` về số
lượng `MAIL_COORDINATOR_CFGS` thành `== 5`.

- [ ] **Step 4: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py tests/agents/test_graph_build.py -v 2>&1 | tail -5`
Expected: toàn bộ PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/mail_write.py backend/src/agents/prompts.py backend/tests/agents/test_mail_write.py backend/tests/agents/test_graph_build.py
git commit -m "feat(mail): send_delivery_email — báo khách đã xuất hàng (vai kho)"
```

---

### Task 8: Hạ tầng — 3 tiến trình MCP và header Open WebUI

**Files:**
- Modify: `start-dev.ps1`, `docker-compose.yml`, `.env`

- [ ] **Step 1: Bật chuyển tiếp header nhận dạng**

Trong `docker-compose.yml`, khối `open-webui.environment`, thêm:

```yaml
      # Cần cho phân quyền theo vai: backend suy vai từ x-openwebui-user-id
      # (chuỗi mờ). KHÔNG đọc name/email/role — đó là PII (xem main.py).
      ENABLE_FORWARD_USER_INFO_HEADERS: "true"
```

Rồi `docker compose up -d open-webui` để nạp lại.

- [ ] **Step 2: Thêm biến môi trường cho 3 vai**

Trong `.env`, thêm:

```
MCP_ODOO_URL=http://localhost:8003/sse
MCP_ODOO_URL_WAREHOUSE=http://localhost:8004/sse
MCP_ODOO_URL_ACCOUNTING=http://localhost:8005/sse
YOUDOO_POLICY_PROFILE=small-business
YOUDOO_ROLE_MAP=
```

`YOUDOO_ROLE_MAP` điền sau Step 4 (cần user_id thật từ Open WebUI).

- [ ] **Step 3: Cho `start-dev.ps1` khởi động 3 tiến trình MCP**

Thay khối khởi động mcp-odoo đơn lẻ bằng vòng lặp qua 3 cấu hình. Mỗi tiến
trình nhận `MCP_ODOO_PORT` và cặp `ODOO_USERNAME`/`ODOO_PASSWORD` RIÊNG:

```powershell
$mcpRoles = @(
    @{ Port = 8003; User = "ai-admin";      Log = "mcp-odoo-admin" },
    @{ Port = 8004; User = "ai-warehouse";  Log = "mcp-odoo-warehouse" },
    @{ Port = 8005; User = "ai-accounting"; Log = "mcp-odoo-accounting" }
)
foreach ($r in $mcpRoles) {
    if (Test-PortOpen $r.Port) {
        Write-Host "    :$($r.Port) đã có tiến trình — bỏ qua." -ForegroundColor Yellow
        continue
    }
    # Mỗi tiến trình CHỈ nắm credential của vai mình — đó là lý do chọn cô lập
    # theo tiến trình: bug định tuyến vai chỉ gây "sai bộ tool", không leo thang.
    $env:MCP_ODOO_PORT = $r.Port
    $env:ODOO_USERNAME = $r.User
    $env:ODOO_PASSWORD = $env:AI_ACCOUNT_PASSWORD
    Start-Process -FilePath $mcpPy -ArgumentList "server.py" `
        -WorkingDirectory (Join-Path $root "mcp-servers\odoo") `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "$($r.Log).log") `
        -RedirectStandardError (Join-Path $logDir "$($r.Log)_err.log") | Out-Null
    Write-Host "    :$($r.Port) $($r.User)" -ForegroundColor Green
}
# Backend đọc Odoo bằng tài khoản CHỈ ĐỌC — kể cả bị chiếm quyền hoàn toàn
# cũng không ghi được gì, vì tài khoản không có quyền (không phải vì code từ chối).
$env:ODOO_USERNAME = "ai-readonly"
$env:ODOO_PASSWORD = $env:AI_ACCOUNT_PASSWORD
```

Thêm `AI_ACCOUNT_PASSWORD=<mật khẩu bạn tự đặt>` vào `.env` (đã gitignore).

- [ ] **Step 4: Khởi động và lấy `user_id` thật**

Chạy `.\start-dev.ps1`, xác nhận cả 3 cổng 8003/8004/8005 mở. Tạo 3 tài khoản
trong Open WebUI (:3002), đăng nhập từng cái, gửi 1 tin nhắn, rồi đọc
`logs\backend.log` để lấy `x-openwebui-user-id` tương ứng. Điền vào
`YOUDOO_ROLE_MAP` theo dạng `id1:admin,id2:warehouse,id3:accounting` và khởi
động lại backend.

- [ ] **Step 5: Commit**

```bash
git add start-dev.ps1 docker-compose.yml
git commit -m "chore(infra): 3 tiến trình MCP theo vai + bật header nhận dạng Open WebUI"
```

---

### Task 9: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi vào `docs/superpowers/plans/2026-08-09-role-based-access-report.md`.

- [ ] **Step 1: Tiêu chí 1 — vai kho làm được việc kho**

Đăng nhập Open WebUI bằng tài khoản vai `warehouse`, yêu cầu xác nhận một phiếu
kho thật. ĐẠT khi thực hiện được.

- [ ] **Step 2: Tiêu chí 2 — vai kho bị từ chối việc kế toán, và biết chỉ sang đâu**

Cùng phiên đó, yêu cầu phát hành một hoá đơn thật. ĐẠT khi bị từ chối **và**
câu trả lời nêu rõ thuộc bộ phận **Kế toán**.

- [ ] **Step 3: Tiêu chí 3 — vai kế toán làm được đúng việc đó**

Đăng nhập bằng tài khoản vai `accounting`, yêu cầu phát hành đúng hoá đơn ấy.
ĐẠT khi thực hiện được. Đây là phép đo chứng minh hai vai **thật sự khác nhau**,
không phải cùng một quyền đội lốt.

- [ ] **Step 4: Tiêu chí 4 — cưỡng chế là THẬT, không chỉ lọc ở agent**

**Tiêu chí quan trọng nhất của cả plan.** Gọi thẳng Odoo bằng credential
`ai-warehouse`, bỏ qua toàn bộ backend và LLM:

```bash
cd d:/Youdoo && set -a && . ./.env && set +a && backend/.venv/Scripts/python.exe -c "
import os, xmlrpc.client
URL=os.environ['ODOO_URL']; DB=os.environ['ODOO_DB']
U='ai-warehouse'; P=os.environ['AI_ACCOUNT_PASSWORD']
uid = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/common').authenticate(DB,U,P,{})
o = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/object')
print('has_access(account.move, write) =', o.execute_kw(DB,uid,P,'account.move','has_access',[[],'write'],{}))
try:
    inv = o.execute_kw(DB,uid,P,'account.move','search_read',[[['state','=','draft'],['move_type','=','out_invoice']]],{'fields':['id'],'limit':1})
    o.execute_kw(DB,uid,P,'account.move','action_post',[[inv[0]['id']]],{})
    print('!!! ODOO CHO PHÉP — CƯỠNG CHẾ KHÔNG HOẠT ĐỘNG')
except Exception as e:
    print('Odoo TỪ CHỐI (đúng):', str(e).splitlines()[-1][:100])
"
```

ĐẠT khi `has_access` trả `False` **và** lệnh `action_post` bị Odoo từ chối.
Nếu nó chạy được, phân quyền chỉ tồn tại ở tầng LLM — DỪNG và báo cáo.

- [ ] **Step 5: Tiêu chí 5 — đổi vai không resume nhầm graph**

Ở vai `warehouse`, yêu cầu một việc cần xác nhận (vd trả hàng). Khi agent hỏi
xác nhận, **đăng nhập sang vai `accounting`** và trả lời "có". ĐẠT khi câu "có"
được xử lý như một lượt mới, KHÔNG resume interrupt của vai cũ và KHÔNG lỗi.

- [ ] **Step 6: Tiêu chí 6 — người không có vai bị từ chối**

Tạo một tài khoản Open WebUI **không** có trong `YOUDOO_ROLE_MAP`, gửi tin
nhắn. ĐẠT khi nhận thông báo không xác định được quyền — KHÔNG được mặc định
thành admin.

- [ ] **Step 7: Viết report và commit**

Ghi từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (nội dung phản hồi, kết quả
`has_access`). Nếu tiêu chí nào không chạy được vì thiếu điều kiện, ghi **CHƯA
ĐO ĐƯỢC** — phân biệt rõ với "đã thử và fail".

```bash
git add docs/superpowers/plans/2026-08-09-role-based-access-report.md
git commit -m "docs(role-based-access): kết quả live-verify"
```
