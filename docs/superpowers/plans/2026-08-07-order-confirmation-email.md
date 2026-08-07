# Gửi mail xác nhận đơn hàng thật — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent gửi được mail xác nhận đơn hàng thật cho khách (dùng
template Odoo "Sales: Order Confirmation"), qua cổng xác nhận trước khi
gửi — chứng minh cơ chế gửi mail lõi hoạt động đầu-cuối để nhân rộng sang
các điểm khác ở plan sau.

**Architecture:** 2 method Odoo mới vào whitelist bảo mật MCP
(`send_mail`, `send`) → 2 tool MCP dùng chung (`preview_template_email`,
`send_prepared_email`) → 1 coordinator agent hardcode template
("Sales: Order Confirmation") theo đúng khuôn `invoice_write.py`
(resolve → render/preview → `_interrupt` → gọi tool). Đăng ký vào
`WRITE_COORDINATORS` + `CONFIRM_IN_CHAIN`, **không** đăng ký vào
`NEXT_STEPS` (tránh ghi đè bước "Giao hàng" có sẵn của `confirm_sale_order`).

**Tech Stack:** Python 3.11, FastMCP (`mcp-servers/odoo`), LangGraph
(interrupt/checkpoint), pytest + pytest-asyncio, Odoo XML-RPC.

**Spec:** `docs/superpowers/specs/2026-08-07-order-confirmation-email-design.md`

## Global Constraints

- Câu xác nhận **bắt buộc** dùng hằng số `WRITE_CONFIRM_SUFFIX` từ
  `src/agents/prompts.py`.
- Coordinator **luôn** gọi `send_prepared_email` bằng `mail_id` đã có từ
  `preview_template_email` — không bao giờ gọi lại `send_mail`/tạo bản
  ghi mail mới ở bước gửi.
- Bản `mail.mail` nháp khi người dùng từ chối gửi **không bị dọn/xóa** —
  khớp cách các coordinator khác xử lý draft bị từ chối.
- **Không** đăng ký `send_order_confirmation_email` vào `NEXT_STEPS` —
  giữ nguyên chuỗi `confirm_sale_order → deliver_order` có sẵn.
- Không thêm cờ môi trường bật/tắt hành vi mới.
- MCP tool `preview_template_email`/`send_prepared_email` **mọi** đường ra
  Odoo phải qua `odoo_call.odoo()` — không gọi `ServerProxy`/`execute_kw`
  trực tiếp (bất biến có sẵn, `backend/tests/mcp/test_odoo_tool_boundary.py`
  tự động phủ tool mới, không cần sửa file test đó).
- **Sửa quan trọng so với spec:** code mẫu trong spec dùng sai shape
  envelope cho `preview_template_email` (gọi `envelope(..., mail_id=...,
  subject=..., ...)` — hàm `envelope()` thật trong `helpers.py` có chữ ký
  cố định `(ok, display, *, ref=None, model=None, res_id=None,
  state=None)`, KHÔNG nhận kwarg tuỳ ý). Plan này sửa: `preview_template_email`
  tự dựng JSON bằng `json.dumps({"ok":..., "display":..., "mail_id":...,
  "subject":..., "recipient_count":...})` (không gọi hàm `envelope()`
  chung) — vẫn tương thích `parse_write_result` (chỉ cần key `"ok"` +
  `"display"`). Coordinator đọc field trực tiếp trên `env` (dict phẳng),
  KHÔNG qua `env["data"]` (đó là shape của `erp_query/envelope.py`, khác
  hoàn toàn shape MCP write-tool `{ok, ref, model, res_id, state,
  display}` mà `parse_write_result`/`_finish` dùng — xem
  `backend/src/agents/tool_result.py`).

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `mcp-servers/odoo/security.py` (sửa) | Whitelist 2 method mới: `send_mail`, `send` | 1 |
| `mcp-servers/odoo/tools/mail.py` (**mới**) | 2 tool: `preview_template_email`, `send_prepared_email` | 2 |
| `mcp-servers/odoo/server.py` (sửa) | Import module `mail` để tự đăng ký tool | 2 |
| `backend/src/agents/mail_write.py` (**mới**) | Coordinator `make_send_order_confirmation_email_node` | 3 |
| `backend/src/agents/write_registry.py` (sửa) | Đăng ký `WRITE_COORDINATORS` + `CONFIRM_IN_CHAIN` | 3 |
| `backend/tests/mcp/test_security_whitelist.py` (**mới**) | Test whitelist 2 method mới | 1 |
| `backend/tests/agents/test_mail_write.py` (**mới**) | Test coordinator bằng tool giả | 3 |

---

### Task 1: Whitelist bảo mật cho 2 method mail mới

**Files:**
- Modify: `mcp-servers/odoo/security.py`
- Test: `backend/tests/mcp/test_security_whitelist.py` (mới)

**Interfaces:**
- Consumes: không có (module độc lập, không import gì ngoài `re`).
- Produces: `classify_operation("send_mail") == "create"`,
  `classify_operation("send") == "write"` — dùng bởi `odoo_call.odoo()`
  ở Task 2.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_security_whitelist.py`:

```python
"""Whitelist bảo mật cho 2 method mail mới (spec 2026-08-07 §3.2) —
security.py là module Python thuần, import trực tiếp được (khác
test_odoo_tool_boundary.py cần sys.path.insert để import cả gói `server`
qua FastMCP)."""
import importlib.util
import pathlib

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def security():
    path = MCP_DIR / "security.py"
    if not path.exists():
        pytest.skip("chưa có mcp-servers/odoo/security.py")
    spec = importlib.util.spec_from_file_location("security_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_send_mail_duoc_phep_va_phan_loai_create(security):
    assert security.classify_operation("send_mail") == "create"


def test_send_duoc_phep_va_phan_loai_write(security):
    assert security.classify_operation("send") == "write"


def test_send_khong_phan_biet_hoa_thuong(security):
    """classify_operation lowercase method trước khi tra map (security.py
    hiện có, hành vi có sẵn) — khoá test này lại cho 2 method mới."""
    assert security.classify_operation("SEND") == "write"
    assert security.classify_operation("Send_Mail") == "create"
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_security_whitelist.py -v`
Expected: FAIL — `assert None == "create"` (2 method chưa có trong map).

- [ ] **Step 3: Thêm 2 method vào whitelist**

Trong `mcp-servers/odoo/security.py`, thêm vào `ODOO_METHOD_OPERATION_MAP`
(dưới nhóm `# WRITE`, cạnh `"action_register_payment": "write",`):

```python
    "send_mail": "create",   # mail.template.send_mail — tạo bản mail.mail nháp
    "send": "write",         # mail.mail.send — gửi thật (hoặc set state=exception)
```

- [ ] **Step 4: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_security_whitelist.py -v`
Expected: PASS toàn bộ 3 test.

- [ ] **Step 5: Commit**

```bash
git add mcp-servers/odoo/security.py backend/tests/mcp/test_security_whitelist.py
git commit -m "feat(mcp-security): whitelist send_mail/send cho tính năng gửi mail"
```

---

### Task 2: 2 tool MCP gửi mail dùng chung

**Files:**
- Create: `mcp-servers/odoo/tools/mail.py`
- Modify: `mcp-servers/odoo/server.py`

**Interfaces:**
- Consumes: `mcp` từ `server` (side-effect import, khớp pattern các tool
  khác — xem `mcp-servers/odoo/tools/sales.py:8`), `odoo` từ `odoo_call`.
  Whitelist `send_mail`/`send` từ Task 1.
- Produces: 2 tool đăng ký trong FastMCP registry:
  - `preview_template_email(template_name: str, res_model: str, ref: str) -> str`
    trả JSON `{"ok": bool, "display": str, "mail_id": int, "subject": str,
    "recipient_count": int}` khi thành công, `{"ok": False, "display": str}`
    khi lỗi.
  - `send_prepared_email(mail_id: int) -> str` trả envelope chuẩn
    `{ok, ref, model, res_id, state, display}` (dùng hàm `envelope()` có
    sẵn trong `helpers.py`).

**Không có test tự động riêng cho task này** — codebase hiện KHÔNG có quy
ước unit-test nội bộ cho logic từng tool MCP (đã kiểm tra: thư mục
`backend/tests/mcp/` chỉ có 1 bất biến cấu trúc dùng chung
`test_odoo_tool_boundary.py`, không có test nào mock `odoo()` để kiểm
logic riêng một tool — đúng cho mọi tool hiện có trong `tools/*.py`, đúng
luôn cho 2 tool mới này). Bất biến cấu trúc (không gọi thẳng
`ServerProxy`/`execute_kw`) được `test_odoo_tool_boundary.py` **tự động
phủ** sau khi đăng ký (Step 3) — không cần sửa file đó. Đúng đắn nghiệp
vụ (resolve đúng, render đúng, gửi đúng) được xác nhận ở Task 4
(live-verify qua Odoo thật) — khớp cách MỌI tool khác trong `tools/*.py`
đã và đang được xác nhận trong dự án này.

- [ ] **Step 1: Tạo `mcp-servers/odoo/tools/mail.py`**

```python
"""Tool MCP domain Mail (mail.template / mail.mail) — spec 2026-08-07.

2 tool DÙNG CHUNG cho MỌI điểm nối gửi mail tương lai (không riêng theo
domain — cơ chế gốc Odoo mail.template.send_mail/mail.mail.send đã là hàm
chung, không có logic nghiệp vụ riêng theo domain, khác hẳn
confirm_sale_order nơi state-check là logic riêng của sale). LLM KHÔNG tự
chọn template — mỗi coordinator ở tầng agent hardcode template_name của
chính nó; 2 tool này chỉ là lớp thực thi.

preview_template_email TẠO một bản mail.mail nháp thật (Odoo không cho
render template mà không tạo bản ghi qua XML-RPC — các method render nội
bộ như _render_template bị chặn gọi từ xa, đã kiểm chứng thật 2026-08-07).
Đây KHÔNG phải thao tác đọc thuần — bản nháp bị từ chối gửi không được
dọn (spec §4.1, người dùng đã duyệt)."""
import json

from server import mcp
from odoo_call import odoo
from helpers import envelope


@mcp.tool()
def preview_template_email(template_name: str, res_model: str, ref: str) -> str:
    """
    Soạn (nhưng CHƯA gửi) một mail từ template Odoo có sẵn cho MỘT bản ghi
    cụ thể. LƯU Ý: bước này TẠO một bản ghi mail.mail nháp thật trong Odoo
    (Odoo không cho render template mà không tạo bản ghi qua XML-RPC) —
    KHÔNG phải thao tác đọc thuần. YÊU CẦU XÁC NHẬN từ người dùng trước
    khi gọi send_prepared_email với mail_id trả về.

    Args:
        template_name: Tên chính xác của mail.template, vd "Sales: Order Confirmation".
        res_model: Model của bản ghi nguồn, vd "sale.order".
        ref: Mã bản ghi (field 'name'), vd "S00166".
    """
    tpls = odoo("mail.template", "search_read",
               [[["name", "=", template_name], ["model", "=", res_model]]],
               {"fields": ["id"], "limit": 2})
    if not tpls:
        return json.dumps({"ok": False,
                           "display": f"Không tìm thấy template '{template_name}' cho model '{res_model}'."},
                          ensure_ascii=False)

    recs = odoo(res_model, "search_read", [[["name", "=", ref]]], {"fields": ["id"], "limit": 2})
    if not recs:
        return json.dumps({"ok": False, "display": f"Không tìm thấy bản ghi '{ref}' trong {res_model}."},
                          ensure_ascii=False)
    if len(recs) > 1:
        return json.dumps({"ok": False, "display": f"Có nhiều bản ghi '{ref}'. Vui lòng nêu rõ hơn."},
                          ensure_ascii=False)

    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False})
    rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["subject", "recipient_ids"]})
    m = rows[0]
    return json.dumps({"ok": True, "display": f"Đã soạn mail '{m['subject']}', chờ xác nhận gửi.",
                       "mail_id": mail_id, "subject": m["subject"],
                       "recipient_count": len(m["recipient_ids"] or [])},
                      ensure_ascii=False)


@mcp.tool()
def send_prepared_email(mail_id: int) -> str:
    """
    Gửi thật một mail đã soạn sẵn qua preview_template_email (dùng ĐÚNG
    mail_id đã trả về, không tạo lại). YÊU CẦU XÁC NHẬN từ người dùng
    trước khi gọi.

    Args:
        mail_id: ID bản ghi mail.mail đã soạn (từ preview_template_email).
    """
    odoo("mail.mail", "send", [[mail_id]], {})
    rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["state", "failure_reason", "subject"]})
    m = rows[0]
    if m["state"] == "exception":
        return envelope(False, f"Gửi thất bại: {m['failure_reason'] or 'không rõ lý do'}.",
                        ref=m["subject"], model="mail.mail", res_id=mail_id, state=m["state"])
    return envelope(True, "Đã gửi mail.", ref=m["subject"], model="mail.mail",
                    res_id=mail_id, state=m["state"])
```

- [ ] **Step 2: Đăng ký module trong `server.py`**

Trong `mcp-servers/odoo/server.py`, sửa dòng import (hiện tại):
```python
from tools import sales, purchase, inventory, mrp, crm, accounting  # noqa: E402,F401
```
thành:
```python
from tools import sales, purchase, inventory, mrp, crm, accounting, mail  # noqa: E402,F401
```

**Vị trí bắt buộc:** dòng này phải nằm **trước**
`forbid_extra_kwargs(mcp._tool_manager)` (dòng cuối file) — mọi
`@mcp.tool()` phải đăng ký xong trước khi hàm đó chạy (comment có sẵn
trong file đã giải thích rõ, không cần đọc lại).

- [ ] **Step 3: Xác nhận bất biến cấu trúc tự động phủ tool mới**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_odoo_tool_boundary.py -v`
Expected: PASS — không tool nào (kể cả 2 tool mới) nhắc `ServerProxy`/`execute_kw` trực tiếp.

- [ ] **Step 4: Commit**

```bash
git add mcp-servers/odoo/tools/mail.py mcp-servers/odoo/server.py
git commit -m "feat(mcp-mail): 2 tool dùng chung — preview_template_email, send_prepared_email"
```

---

### Task 3: Coordinator `send_order_confirmation_email`

**Files:**
- Create: `backend/src/agents/mail_write.py`
- Modify: `backend/src/agents/write_registry.py`
- Test: `backend/tests/agents/test_mail_write.py` (mới)

**Interfaces:**
- Consumes: `_ttl_expiry`, `_msg`, `WRITE_DISABLED_MSG` từ `.create_order`;
  `write_gate` module; `WRITE_CONFIRM_SUFFIX` từ `.prompts`;
  `parse_write_result` từ `.tool_result`; tool `preview_template_email`,
  `send_prepared_email` (Task 2).
- Produces: `make_send_order_confirmation_email_node(tools) -> node`;
  `Spec("send_order_confirmation_email", ...)` trong `WRITE_COORDINATORS`
  dưới khóa `"send_order_confirmation_email"`; thêm cùng tên vào
  `CONFIRM_IN_CHAIN`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_mail_write.py`:

```python
import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.mail_write as mw
from src.agents import write_gate


def _fake_tool(name, recorder, response):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        recorder["args"] = args
        return json.dumps(response, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(node):
    g = StateGraph(ERPAgentState)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def _state(args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": "send_order_confirmation_email",
                               "args": args, "summary": "x"}}


_PREVIEW_OK = {"ok": True, "display": "Đã soạn mail 'Order Confirmation', chờ xác nhận gửi.",
              "mail_id": 60, "subject": "Order Confirmation (Ref S00166)",
              "recipient_count": 1}
_SEND_OK = {"ok": True, "display": "Đã gửi mail.", "ref": "Order Confirmation (Ref S00166)",
           "model": "mail.mail", "res_id": 60, "state": "sent"}


@pytest.mark.asyncio
async def test_co_order_ref_thi_hien_preview_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m1"}}
    res = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "S00166" in itr["question"]
    assert "1 người nhận" in itr["question"]
    assert preview_rec["args"] == {"template_name": "Sales: Order Confirmation",
                                   "res_model": "sale.order", "ref": "S00166"}
    assert "args" not in send_rec           # chưa gửi trước khi xác nhận


@pytest.mark.asyncio
async def test_xac_nhan_thi_goi_send_bang_dung_mail_id(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m2"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert send_rec["args"] == {"mail_id": 60}
    assert res["last_write"]["tool"] == "send_order_confirmation_email"
    assert res["last_write"]["state"] == "sent"


@pytest.mark.asyncio
async def test_tu_choi_thi_khong_goi_send(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    cfg = {"configurable": {"thread_id": "m3"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "args" not in send_rec
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_tim_thay_don_thi_bao_loi_khong_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec,
                              {"ok": False, "display": "Không tìm thấy bản ghi 'S99999' trong sale.order."})
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({"order_ref": "S99999"}),
                              {"configurable": {"thread_id": "m4"}})
    assert "__interrupt__" not in res
    assert "args" not in send_rec


@pytest.mark.asyncio
async def test_thieu_order_ref_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({}), {"configurable": {"thread_id": "m5"}})
    assert "__interrupt__" not in res
    assert "args" not in preview_rec
    assert "args" not in send_rec


@pytest.mark.asyncio
async def test_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    preview_rec, send_rec = {}, {}
    preview_tool = _fake_tool("preview_template_email", preview_rec, _PREVIEW_OK)
    send_tool = _fake_tool("send_prepared_email", send_rec, _SEND_OK)
    graph = _graph(mw.make_send_order_confirmation_email_node([preview_tool, send_tool]))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m6"}})
    assert "__interrupt__" not in res
    assert "args" not in preview_rec
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_mail_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.mail_write'`

- [ ] **Step 3: Tạo `backend/src/agents/mail_write.py`**

```python
# backend/src/agents/mail_write.py
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07.

Dùng 2 tool MCP dùng chung (preview_template_email, send_prepared_email —
xem mcp-servers/odoo/tools/mail.py) qua đúng khuôn resolve → render →
_interrupt → gọi tool của invoice_write.py. Khác biệt duy nhất: bước
"render" ở đây (preview_template_email) TỰ NÓ đã là một write thật (tạo
mail.mail nháp) — Odoo không cho render template mà không tạo bản ghi qua
XML-RPC. Bản nháp bị từ chối gửi KHÔNG bị dọn (spec §4.1).

KHÔNG đăng ký vào NEXT_STEPS: confirm_sale_order đã có bước kế tiếp
"deliver_order" — thêm bước này vào sẽ ghi đè, phá chuỗi giao hàng có sẵn
(spec §3.4). Gửi mail xác nhận là hành động người dùng tự yêu cầu riêng."""
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import _ttl_expiry, _msg, WRITE_DISABLED_MSG
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX


def _finish(tool_name: str, result) -> dict:
    display, env = parse_write_result(result)
    return {**_msg(display), "pending_action": None,
            "last_write": {"tool": tool_name, **env} if env else None}


def make_send_order_confirmation_email_node(tools):
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        order_ref = str(args.get("order_ref") or "").strip()
        if not order_ref:
            return _msg("Bạn cần cho biết mã đơn bán cần gửi mail xác nhận.")

        preview_tool = by_name.get("preview_template_email")
        if preview_tool is None:
            return _msg("Công cụ soạn mail không khả dụng.")
        result = await preview_tool.ainvoke({
            "template_name": "Sales: Order Confirmation",
            "res_model": "sale.order", "ref": order_ref})
        # preview_template_email trả JSON phẳng {ok, display, mail_id, subject,
        # recipient_count} — parse_write_result chỉ cần key "ok"+"display" để
        # coi là envelope hợp lệ, KHÔNG lồng dưới "data" (đó là shape khác của
        # erp_query/envelope.py). env ở đây CHÍNH LÀ dict đã json.loads.
        display, env = parse_write_result(result)
        if env is None:
            return _msg(display)

        preview_text = (f"Mail xác nhận đơn {order_ref}:\n"
                        f"  Tới: {env.get('recipient_count', 0)} người nhận\n"
                        f"  Tiêu đề: {env.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy gửi mail xác nhận đơn.")

        send_tool = by_name.get("send_prepared_email")
        if send_tool is None:
            return _msg("Công cụ gửi mail không khả dụng.")
        try:
            result = await send_tool.ainvoke({"mail_id": env.get("mail_id")})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi gửi mail: {e}")
        return _finish("send_order_confirmation_email", result)

    return send_order_confirmation_email_node
```

- [ ] **Step 4: Đăng ký vào registry**

Trong `backend/src/agents/write_registry.py`, thêm import sau dòng
`from .invoice_write import ...`:

```python
from .mail_write import make_send_order_confirmation_email_node
```

Thêm dòng vào cuối dict `WRITE_COORDINATORS` (trước dấu `}`):

```python
    "send_order_confirmation_email": Spec(
        "send_order_confirmation_email",
        lambda llm, tools: make_send_order_confirmation_email_node(tools)),
```

Sửa `CONFIRM_IN_CHAIN` từ:
```python
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment"})
```
thành:
```python
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment",
                              "send_order_confirmation_email"})
```

**KHÔNG** thêm gì vào `NEXT_STEPS` — xem docstring `mail_write.py` và
Global Constraints ở trên.

- [ ] **Step 5: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_mail_write.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Chạy test hồi quy toàn agents + auto_chain**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/ -q -m "not live and not integration"`
Expected: không có fail MỚI. Đặc biệt xác nhận
`test_auto_chain.py::test_confirm_in_chain_la_tap_tuong_minh_chi_2_tool_dung_tien`
(nếu còn tên cũ, giờ SẼ fail vì `CONFIRM_IN_CHAIN` có 3 phần tử — đây là
**thay đổi có chủ đích**, không phải hồi quy; nếu gặp, sửa test đó khớp
tập 3 phần tử mới, cùng commit).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/mail_write.py backend/src/agents/write_registry.py backend/tests/agents/test_mail_write.py
git commit -m "feat(agents): coordinator send_order_confirmation_email — gửi mail xác nhận đơn thật"
```

---

### Task 4: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi kết quả vào
`docs/superpowers/plans/2026-08-07-order-confirmation-email-report.md`.

**Bối cảnh bắt buộc đọc trước:** unit test ở Task 1-3 dựng state/tool giả,
**không đủ** để chứng minh cơ chế gửi mail thật hoạt động (đặc biệt:
`send_mail`/`send` mới lần đầu chạm Odoo thật qua whitelist mới — rủi ro
cao nhất chưa từng có tiền lệ đo). Cách gửi request phải khớp client
thật: resend toàn bộ lịch sử hội thoại mỗi lượt, KHÔNG dùng `session_id`.

- [ ] **Step 1: Khởi động lại backend + mcp-odoo để nạp code mới**

```powershell
.\start-dev.ps1
```

Nếu backend/mcp-odoo đã chạy sẵn từ phiên trước, **phải dừng và khởi động
lại thủ công** (script tự phát hiện cổng đã có tiến trình khỏe mạnh và
BỎ QUA khởi động lại — không đủ để nạp code Task 1-3 vừa viết). Kiểm tra
PID trước/sau để xác nhận đã restart thật.

- [ ] **Step 2: Xác nhận SMTP đã cấu hình**

Kiểm tra `ir.mail_server` qua XML-RPC hoặc Odoo UI (Settings → Technical →
Email → Outgoing Mail Servers) — phải có ít nhất 1 bản ghi. **Nếu chưa
có:** vẫn chạy Tiêu chí 1-2 (không cần SMTP), ghi rõ Tiêu chí 3 KHÔNG ĐẠT
vì thiếu hạ tầng — không suy đoán, không tô hồng.

- [ ] **Step 3: Tiêu chí 1 — soạn mail xem trước, gọi trực tiếp**

Xác nhận thật một đơn bán (chuỗi `create_quotation → confirm_sale_order`
qua đối tác/sản phẩm thật), rồi gửi: `"Gửi mail xác nhận đơn [mã đơn
thật] cho khách"`.

ĐẠT khi: hiện bản xem trước (số người nhận + tiêu đề) rồi mới hỏi xác
nhận, **chưa** gửi gì; và **không** tự động chạy tiếp `deliver_order`
(xác nhận đơn vẫn ở đúng trạng thái, không bị giao hàng ngoài ý muốn).

- [ ] **Step 4: Tiêu chí 2 — từ chối không gửi**

Từ Tiêu chí 1, trả lời `"không"`.

ĐẠT khi: qua XML-RPC xác nhận `mail.mail` (đọc bằng `mail_id` đã thấy ở
bước soạn, hoặc tìm theo `subject`+thời gian gần nhất) **chưa** ở trạng
thái đã gửi.

- [ ] **Step 5: Tiêu chí 3 — gửi thật (chỉ chạy nếu Step 2 xác nhận có SMTP)**

Lặp lại Tiêu chí 1 với một đơn khác, trả lời `"có"`.

ĐẠT khi: `mail.mail.state` chuyển sang trạng thái đã gửi (không phải
`exception`), xác nhận qua XML-RPC. Nếu có quyền truy cập hộp mail nhận
thật, xác nhận email thật sự tới nơi.

- [ ] **Step 6: Viết report và commit**

Ghi rõ từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (nội dung phản hồi
thật, trạng thái `mail.mail` đọc trực tiếp từ Odoo). Nếu Tiêu chí 3 không
chạy được vì thiếu SMTP, ghi rõ **CHƯA ĐO ĐƯỢC** (không phải KHÔNG ĐẠT —
phân biệt rõ "đã thử và fail" với "chưa đủ điều kiện để thử").

```bash
git add docs/superpowers/plans/2026-08-07-order-confirmation-email-report.md
git commit -m "docs(order-confirmation-email): kết quả live-verify"
```
