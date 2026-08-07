# Gửi mail xác nhận đơn hàng thật — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent gửi được mail xác nhận đơn hàng thật cho khách (dùng
template Odoo "Sales: Order Confirmation"), qua cổng xác nhận trước khi
gửi — chứng minh cơ chế gửi mail lõi hoạt động đầu-cuối để nhân rộng sang
các điểm khác ở plan sau.

**Architecture:** 2 method Odoo mới vào whitelist bảo mật MCP
(`send_mail`, `send`) → 3 tool MCP dùng chung (`preview_template_email`,
`send_prepared_email`, `discard_prepared_email`) → 1 coordinator agent
hardcode template ("Sales: Order Confirmation"), **TÁCH 2 NODE LangGraph**
(khác mọi coordinator single-node khác trong package — xem lý do trong
Task 3: preview là 1 write thật, phải nằm ở node RIÊNG trước `_interrupt`
để không bị LangGraph replay khi resume). Đăng ký vào `WRITE_COORDINATORS`
+ `CONFIRM_IN_CHAIN` + `WRITE_PLANNER_PROMPT` (bắt buộc — không nằm trong
`NEXT_STEPS` nên planner-prompt là đường duy nhất LLM biết tool tồn tại),
**không** đăng ký vào `NEXT_STEPS` (tránh ghi đè bước "Giao hàng" có sẵn
của `confirm_sale_order`).

**Tech Stack:** Python 3.11, FastMCP (`mcp-servers/odoo`), LangGraph
(interrupt/checkpoint), pytest + pytest-asyncio, Odoo XML-RPC.

**Spec:** `docs/superpowers/specs/2026-08-07-order-confirmation-email-design.md`

## Global Constraints

- Câu xác nhận **bắt buộc** dùng hằng số `WRITE_CONFIRM_SUFFIX` từ
  `src/agents/prompts.py`.
- Coordinator **luôn** gọi `send_prepared_email` bằng `mail_id` đã có từ
  `preview_template_email` — không bao giờ gọi lại `send_mail`/tạo bản
  ghi mail mới ở bước gửi. **Bắt buộc kiến trúc 2 node** (Task 3) để giữ
  đúng bất biến này qua resume — bản 1-node ban đầu VI PHẠM bất biến này
  (đo thật bằng probe lúc review: LangGraph replay node, preview bị gọi
  2 lần, mail gửi đi không phải bản đã duyệt).
- **Sửa quyết định so với spec §4.1 (đảo ngược sau khi đo thêm):** bản
  `mail.mail` nháp khi người dùng từ chối gửi **PHẢI được chủ động hủy**
  (gọi `discard_prepared_email`) — spec gốc quyết định "không dọn", nhưng
  quyết định đó được duyệt TRƯỚC KHI phát hiện Odoo có cron "Mail: Email
  Queue Manager" đang bật (đo thật qua XML-RPC, 2026-08-07), tự động gửi
  MỌI `mail.mail` ở trạng thái `outgoing` mỗi giờ — kể cả bản bị từ chối
  nếu không chủ động hủy. Không hủy = cổng xác nhận chỉ trì hoãn việc gửi
  tối đa 1 giờ, không thực sự chặn.
- **Không** đăng ký `send_order_confirmation_email` vào `NEXT_STEPS` —
  giữ nguyên chuỗi `confirm_sale_order → deliver_order` có sẵn. Vì vậy
  **bắt buộc** đăng ký tool này vào `WRITE_PLANNER_PROMPT` (`prompts.py`)
  — nếu không, planner không bao giờ chọn được tool, coordinator không
  thể chạm tới từ một lượt chat thật dù mọi test dựng state tay vẫn xanh.
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
| `mcp-servers/odoo/tools/mail.py` (**mới**, sửa thêm ở Task 3) | 3 tool: `preview_template_email`, `send_prepared_email`, `discard_prepared_email` | 2, 3 |
| `mcp-servers/odoo/server.py` (sửa) | Import module `mail` để tự đăng ký tool | 2 |
| `backend/src/agents/mail_write.py` (**mới**) | Coordinator 2 node: `make_send_order_confirmation_email_preview_node`, `make_send_order_confirmation_email_node`, `route_after_mail_preview` | 3 |
| `backend/src/agents/write_registry.py` (sửa) | Đăng ký `WRITE_COORDINATORS` + `CONFIRM_IN_CHAIN` | 3 |
| `backend/src/agents/graph.py` (sửa) | Nối dây 2 node coordinator (loại trừ khỏi vòng lặp generic, add tay) | 3 |
| `backend/src/agents/prompts.py` (sửa) | Đăng ký tool vào `WRITE_PLANNER_PROMPT` — bắt buộc để planner chọn được | 3 |
| `backend/tests/mcp/test_security_whitelist.py` (**mới**) | Test whitelist 2 method mới | 1 |
| `backend/tests/agents/test_mail_write.py` (**mới**) | Test coordinator 2 node bằng tool giả, chốt chặn bug replay | 3 |

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

### Task 3: Coordinator `send_order_confirmation_email` (2 node — sửa kiến trúc sau review)

> **Sửa lớn so với bản gốc của Task 3, phát sinh từ review thật (2026-08-07):**
> reviewer dùng probe thật đo được LangGraph **replay toàn bộ node** khi
> resume sau `_interrupt()`. Thiết kế gốc gọi `preview_template_email`
> (một write thật) TRƯỚC `_interrupt` trong CÙNG một node — nên nó bị gọi
> LẦN THỨ HAI lúc resume, tạo `mail.mail` thứ hai, và mail **thật sự gửi
> đi KHÔNG PHẢI bản người dùng đã duyệt**. Đây là lỗi Critical, vi phạm
> đúng bất biến an toàn mà tính năng này sinh ra để bảo đảm.
>
> Điều tra thêm phát hiện Odoo có cron **"Mail: Email Queue Manager" đang
> bật** (đo thật qua XML-RPC), tự động gửi MỌI `mail.mail` ở trạng thái
> `outgoing` mỗi giờ — kể cả bản bị người dùng TỪ CHỐI, nếu không chủ động
> hủy. Điều này **đảo ngược quyết định §4.1 gốc của spec** ("không dọn
> bản nháp khi từ chối", đã được duyệt TRƯỚC KHI biết cron này tồn tại).
>
> Bản Task 3 dưới đây đã sửa cả hai: tách coordinator thành **2 node
> LangGraph** (ranh giới node = ranh giới checkpoint, node đã hoàn tất
> không bị replay), và thêm tool `discard_prepared_email` được gọi chủ
> động ở nhánh từ chối.

**Files:**
- Modify: `mcp-servers/odoo/tools/mail.py` (thêm tool `discard_prepared_email`)
- Create: `backend/src/agents/mail_write.py`
- Modify: `backend/src/agents/write_registry.py`
- Modify: `backend/src/agents/graph.py`
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_mail_write.py` (mới)

**Interfaces:**
- Consumes: `_ttl_expiry`, `_msg`, `WRITE_DISABLED_MSG` từ `.create_order`;
  `write_gate` module; `WRITE_CONFIRM_SUFFIX` từ `.prompts`;
  `parse_write_result` từ `.tool_result`; tool `preview_template_email`,
  `send_prepared_email`, `discard_prepared_email`.
- Produces: `make_send_order_confirmation_email_preview_node(tools) -> node`
  (Node 1 — soạn mail, KHÔNG interrupt); `make_send_order_confirmation_email_node(tools) -> node`
  (Node 2 — xác nhận + gửi); `route_after_mail_preview(state) -> str`
  (điều kiện chuyển Node 1 → Node 2 hoặc thẳng `write_continuation`);
  `Spec(...)` trong `WRITE_COORDINATORS` dưới khóa `"send_order_confirmation_email"`
  với `.node = "send_order_confirmation_email_preview"`; thêm tên tool vào
  `CONFIRM_IN_CHAIN`; dòng mới trong `WRITE_PLANNER_PROMPT` (`prompts.py`)
  để planner có thể chọn tool này (bắt buộc — coordinator không nằm trong
  `NEXT_STEPS` nên đây là đường DUY NHẤT LLM biết tool này tồn tại).

- [ ] **Step 1: Thêm tool `discard_prepared_email` vào `mcp-servers/odoo/tools/mail.py`**

Thêm vào cuối file (sau `send_prepared_email`):

```python
@mcp.tool()
def discard_prepared_email(mail_id: int) -> str:
    """
    Hủy một mail đã soạn qua preview_template_email nhưng người dùng từ
    chối gửi — xóa bản mail.mail nháp. BẮT BUỘC gọi khi từ chối: bản nháp
    nằm ở trạng thái 'outgoing' (hàng đợi gửi), KHÔNG phải trạng thái thụ
    động — Odoo có cron "Mail: Email Queue Manager" chạy định kỳ, tự động
    gửi MỌI bản ghi ở trạng thái này, kể cả bản bị người dùng từ chối nếu
    không chủ động hủy (đã xác nhận thật trên Odoo 2026-08-07: cron đang
    bật, chạy mỗi giờ).

    Args:
        mail_id: ID bản ghi mail.mail cần hủy (từ preview_template_email).
    """
    odoo("mail.mail", "unlink", [[mail_id]], {})
    return envelope(True, "Đã hủy mail nháp.", ref=str(mail_id), model="mail.mail",
                    res_id=mail_id, state="cancelled")
```

Không cần sửa whitelist bảo mật: `unlink` đã có sẵn trong
`ODOO_METHOD_OPERATION_MAP` từ trước (không phải do Task 1 thêm).

- [ ] **Step 2: Viết test thất bại**

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


def _fake_tool(name, calls_list, response_fn):
    """response_fn(call_number) -> dict cho lần gọi thứ N (1-indexed) —
    cho phép trả mail_id KHÁC NHAU mỗi lần gọi, để bắt được bug preview bị
    gọi lại (replay) thay vì chỉ chạy đúng 1 lần."""
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        calls_list.append(args)
        return json.dumps(response_fn(len(calls_list)), ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(preview_node, send_node):
    g = StateGraph(ERPAgentState)
    g.add_node("send_order_confirmation_email_preview", preview_node)
    g.add_node("send_order_confirmation_email", send_node)
    g.add_conditional_edges(
        "send_order_confirmation_email_preview", mw.route_after_mail_preview,
        {"send_order_confirmation_email": "send_order_confirmation_email",
         "write_continuation": END})
    g.add_edge("send_order_confirmation_email", END)
    g.set_entry_point("send_order_confirmation_email_preview")
    return g.compile(checkpointer=MemorySaver())


def _state(args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": "send_order_confirmation_email",
                               "args": args, "summary": "x"}}


def _preview_response(call_number):
    """mail_id ĐỔI theo call_number (58+n) — để test phát hiện được nếu
    preview bị gọi hơn 1 lần (mail_id sẽ khác giữa các lần gọi)."""
    return {"ok": True, "display": "Đã soạn mail 'Order Confirmation', chờ xác nhận gửi.",
           "mail_id": 58 + call_number, "subject": "Order Confirmation (Ref S00166)",
           "recipient_count": 1}


_SEND_OK = {"ok": True, "display": "Đã gửi mail.", "ref": "Order Confirmation (Ref S00166)",
           "model": "mail.mail", "res_id": 59, "state": "sent"}
_DISCARD_OK = {"ok": True, "display": "Đã hủy mail nháp.", "ref": "59",
              "model": "mail.mail", "res_id": 59, "state": "cancelled"}


def _tools(preview_calls, send_calls, discard_calls):
    preview_tool = _fake_tool("preview_template_email", preview_calls, _preview_response)
    send_tool = _fake_tool("send_prepared_email", send_calls, lambda n: _SEND_OK)
    discard_tool = _fake_tool("discard_prepared_email", discard_calls, lambda n: _DISCARD_OK)
    return preview_tool, send_tool, discard_tool


@pytest.mark.asyncio
async def test_co_order_ref_thi_hien_preview_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m1"}}
    res = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "S00166" in itr["question"]
    assert "1 người nhận" in itr["question"]
    assert "Order Confirmation (Ref S00166)" in itr["question"]
    assert preview_calls == [{"template_name": "Sales: Order Confirmation",
                              "res_model": "sale.order", "ref": "S00166"}]
    assert send_calls == []           # chưa gửi trước khi xác nhận


@pytest.mark.asyncio
async def test_xac_nhan_thi_goi_send_bang_dung_mail_id_va_preview_chi_goi_1_lan(monkeypatch):
    """Chốt chặn bug Critical đã đo thật ở review Task 3 (2026-08-07):
    LangGraph replay TOÀN BỘ node khi resume sau _interrupt — nếu preview
    nằm cùng node với interrupt (thiết kế cũ), nó bị gọi LẦN THỨ HAI, tạo
    mail.mail thứ hai, và send() nhận mail_id của bản KHÔNG được duyệt.
    mail_id đổi theo lần gọi (_preview_response) nên nếu bug tái diễn,
    assert send_calls dưới đây sẽ fail vì mail_id không khớp lần gọi đầu."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m2"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert len(preview_calls) == 1                    # KHÔNG bị replay
    assert send_calls == [{"mail_id": 59}]             # 58 + 1 (lần gọi duy nhất)
    assert res["last_write"]["tool"] == "send_order_confirmation_email"
    assert res["last_write"]["state"] == "sent"
    assert discard_calls == []


@pytest.mark.asyncio
async def test_tu_choi_thi_goi_discard_va_khong_goi_send(monkeypatch):
    """Đảo ngược quyết định §4.1 gốc: Odoo có cron 'Mail: Email Queue
    Manager' đang bật (đo thật 2026-08-07), tự gửi MỌI mail.mail ở trạng
    thái 'outgoing' — kể cả bản bị từ chối nếu không chủ động hủy."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    assert discard_calls == [{"mail_id": 59}]
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_discard_loi_khong_chan_thong_bao_huy(monkeypatch):
    """discard_prepared_email lỗi (vd Odoo mạng lỗi) không được chặn thông
    báo 'đã hủy' cho người dùng — best-effort, không phải hợp đồng chính."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3b"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_tim_thay_don_thi_bao_loi_khong_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool = _fake_tool("preview_template_email", preview_calls,
                              lambda n: {"ok": False,
                                        "display": "Không tìm thấy bản ghi 'S99999' trong sale.order."})
    _, send_tool, discard_tool = _tools([], send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S99999"}),
                              {"configurable": {"thread_id": "m4"}})
    assert "__interrupt__" not in res
    assert send_calls == []


@pytest.mark.asyncio
async def test_preview_loi_thi_bao_loi_khong_crash(monkeypatch):
    """Task 2 review finding (plan-mandated, 2 tool MCP không try/except) —
    ruling: xử lý ở tầng coordinator thay vì tool."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    send_calls, discard_calls = [], []

    preview_tool = MagicMock()
    preview_tool.name = "preview_template_email"

    async def _raise(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    preview_tool.ainvoke = _raise
    _, send_tool, discard_tool = _tools([], send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m4b"}})
    assert "__interrupt__" not in res
    assert send_calls == []
    assert "lỗi" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_thieu_order_ref_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({}), {"configurable": {"thread_id": "m5"}})
    assert "__interrupt__" not in res
    assert preview_calls == []
    assert send_calls == []


@pytest.mark.asyncio
async def test_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    res = await graph.ainvoke(_state({"order_ref": "S00166"}),
                              {"configurable": {"thread_id": "m6"}})
    assert "__interrupt__" not in res
    assert preview_calls == []
```

- [ ] **Step 3: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_mail_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.mail_write'`

- [ ] **Step 4: Tạo `backend/src/agents/mail_write.py`**

```python
# backend/src/agents/mail_write.py
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07.

TÁCH 2 NODE LangGraph — KHÁC MỌI coordinator khác trong package này (chỉ
có 1 node). Lý do: preview_template_email TỰ NÓ là một write thật (tạo
mail.mail nháp) — Odoo không cho render template mà không tạo bản ghi qua
XML-RPC. Nếu gọi nó TRƯỚC _interrupt() trong CÙNG một node (khuôn mọi
coordinator khác dùng, vì bước "render" của họ là READ thuần, idempotent),
LangGraph sẽ REPLAY TOÀN BỘ node khi resume sau interrupt — đo thật bằng
probe (review Task 3, 2026-08-07): preview bị gọi LẦN THỨ HAI, tạo bản
mail.mail thứ hai, và mail thật sự gửi đi KHÔNG PHẢI bản người dùng đã
duyệt. Tách node giải quyết triệt để: mỗi node hoàn tất là một ranh giới
checkpoint LangGraph — node đã return xong không bị replay khi node SAU
nó (nơi có interrupt) resume.

  Node 1 (send_order_confirmation_email_preview): gọi preview_template_email
    MỘT LẦN DUY NHẤT, lưu mail_id/subject/recipient_count vào
    pending_action.args (persist qua state, không phải biến cục bộ), rồi
    (qua conditional edge ở graph.py, KHÔNG unconditional) chuyển sang Node 2
    nếu thành công, hoặc thẳng write_continuation nếu lỗi/thiếu input.
  Node 2 (send_order_confirmation_email): đọc dữ liệu đã lưu từ Node 1
    (KHÔNG gọi lại preview), _interrupt xác nhận, rồi gọi send_prepared_email.

TỪ CHỐI GỬI PHẢI CHỦ ĐỘNG HỦY BẢN NHÁP (đảo ngược quyết định §4.1 gốc của
spec — quyết định đó được duyệt TRƯỚC KHI biết Odoo có cron "Mail: Email
Queue Manager" đang bật, tự động gửi MỌI mail.mail ở trạng thái 'outgoing',
kể cả bản bị từ chối, nếu không chủ động hủy). Gọi discard_prepared_email
ở nhánh từ chối — best-effort (lỗi hủy không chặn thông báo "đã hủy" cho
người dùng, vì từ góc nhìn agent, hành động ĐÃ bị hủy; dọn dẹp mail.mail là
lớp phòng vệ thêm, không phải hợp đồng chính).

KHÔNG đăng ký vào NEXT_STEPS: confirm_sale_order đã có bước kế tiếp
"deliver_order" — thêm bước này vào sẽ ghi đè, phá chuỗi giao hàng có sẵn.
Gửi mail xác nhận là hành động người dùng tự yêu cầu riêng — PHẢI được
liệt kê trong WRITE_PLANNER_PROMPT (prompts.py) để planner có thể chọn nó,
khác các coordinator chỉ tới được qua NEXT_STEPS."""
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


def make_send_order_confirmation_email_preview_node(tools):
    """Node 1: soạn mail (1 write thật), lưu kết quả vào state. KHÔNG
    interrupt ở đây — xem docstring module."""
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_preview_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        action = state.get("pending_action") or {}
        args = action.get("args") or {}
        order_ref = str(args.get("order_ref") or "").strip()
        if not order_ref:
            return _msg("Bạn cần cho biết mã đơn bán cần gửi mail xác nhận.")

        preview_tool = by_name.get("preview_template_email")
        if preview_tool is None:
            return _msg("Công cụ soạn mail không khả dụng.")
        try:
            result = await preview_tool.ainvoke({
                "template_name": "Sales: Order Confirmation",
                "res_model": "sale.order", "ref": order_ref})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi soạn mail: {e}")
        # preview_template_email trả JSON phẳng {ok, display, mail_id, subject,
        # recipient_count} — parse_write_result chỉ cần key "ok"+"display" để
        # coi là envelope hợp lệ, KHÔNG lồng dưới "data" (đó là shape khác của
        # erp_query/envelope.py). env ở đây CHÍNH LÀ dict đã json.loads.
        display, env = parse_write_result(result)
        if env is None:
            return _msg(display)

        # Lưu vào pending_action.args — Node 2 đọc từ ĐÂY, không gọi lại
        # preview_template_email. Đây là ranh giới persist thật (node này
        # return xong mới tới Node 2), không phải biến cục bộ sẽ mất khi
        # LangGraph replay.
        return {"pending_action": {**action,
                                   "args": {**args, "mail_id": env.get("mail_id"),
                                            "subject": env.get("subject"),
                                            "recipient_count": env.get("recipient_count")}}}

    return send_order_confirmation_email_preview_node


def make_send_order_confirmation_email_node(tools):
    """Node 2: đọc mail_id/subject/recipient_count đã lưu (Node 1), xác
    nhận, gửi. Từ chối → hủy bản nháp (best-effort) — xem docstring module."""
    by_name = {t.name: t for t in tools}

    async def send_order_confirmation_email_node(state: ERPAgentState) -> dict:
        args = (state.get("pending_action") or {}).get("args") or {}
        order_ref = str(args.get("order_ref") or "")
        mail_id = args.get("mail_id")

        preview_text = (f"Mail xác nhận đơn {order_ref}:\n"
                        f"  Tới: {args.get('recipient_count', 0)} người nhận\n"
                        f"  Tiêu đề: {args.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            discard_tool = by_name.get("discard_prepared_email")
            if discard_tool is not None:
                try:
                    await discard_tool.ainvoke({"mail_id": mail_id})
                except Exception:  # noqa: BLE001 — best-effort, không chặn thông báo hủy
                    pass
            return _msg("Đã hủy gửi mail xác nhận đơn.")

        send_tool = by_name.get("send_prepared_email")
        if send_tool is None:
            return _msg("Công cụ gửi mail không khả dụng.")
        try:
            result = await send_tool.ainvoke({"mail_id": mail_id})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi gửi mail: {e}")
        return _finish("send_order_confirmation_email", result)

    return send_order_confirmation_email_node


def route_after_mail_preview(state: ERPAgentState) -> str:
    """Node 1 → Node 2 (thành công, có mail_id) hoặc thẳng write_continuation
    (lỗi/thiếu input — Node 1 đã tự trả _msg lỗi, Node 2 không cần chạy)."""
    args = (state.get("pending_action") or {}).get("args") or {}
    if args.get("mail_id"):
        return "send_order_confirmation_email"
    return "write_continuation"
```

- [ ] **Step 5: Đăng ký vào registry**

Trong `backend/src/agents/write_registry.py`, thêm import sau dòng
`from .invoice_write import ...`:

```python
from .mail_write import (make_send_order_confirmation_email_preview_node,
                         make_send_order_confirmation_email_node)
```

Thêm dòng vào cuối dict `WRITE_COORDINATORS` (trước dấu `}`) — **lưu ý
`.node` trỏ vào Node 1 (preview), KHÔNG phải tên tool**:

```python
    "send_order_confirmation_email": Spec(
        "send_order_confirmation_email_preview",
        lambda llm, tools: make_send_order_confirmation_email_preview_node(tools)),
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

**KHÔNG** thêm gì vào `NEXT_STEPS`.

- [ ] **Step 6: Nối dây 2 node trong `graph.py`**

Trong `backend/src/agents/graph.py`, thêm import (cạnh các import `.write_registry`/`.continuation` có sẵn):

```python
from .mail_write import make_send_order_confirmation_email_node, route_after_mail_preview
```

Tìm khối vòng lặp hiện có (dùng để nối MỌI coordinator single-node tới `write_continuation`):

```python
    for spec in WRITE_COORDINATORS.values():
        g.add_edge(spec.node, "write_continuation")
```

Thay bằng (loại trừ coordinator 2-node, rồi nối tay Node 2 + conditional edge Node 1→Node 2):

```python
    for spec in WRITE_COORDINATORS.values():
        if spec.node == "send_order_confirmation_email_preview":
            continue  # coordinator 2 node, nối tay ngay dưới — xem docstring
                     # mail_write.py: preview là 1 write thật, không được
                     # unconditional-edge thẳng write_continuation
        g.add_edge(spec.node, "write_continuation")

    # send_order_confirmation_email: coordinator 2 node. Node 1 (preview) đã
    # add ở vòng lặp add_node phía trên (.node của Spec trỏ vào nó). Node 2
    # (gửi) KHÔNG nằm trong WRITE_COORDINATORS — add tay ở đây.
    g.add_node("send_order_confirmation_email",
              make_send_order_confirmation_email_node(tools))
    g.add_conditional_edges(
        "send_order_confirmation_email_preview", route_after_mail_preview,
        {"send_order_confirmation_email": "send_order_confirmation_email",
         "write_continuation": "write_continuation"})
    g.add_edge("send_order_confirmation_email", "write_continuation")
```

**Vị trí bắt buộc:** khối này phải nằm sau dòng
`g.add_node("write_continuation", make_write_continuation_node())` (đích
`"write_continuation"` phải tồn tại trước khi được tham chiếu trong
`add_conditional_edges`/`add_edge`) — khớp đúng vị trí khối vòng lặp gốc
đang nằm (sau `write_continuation` được add, trước `g.add_edge("rag", END)`).

- [ ] **Step 7: Đăng ký tool vào `WRITE_PLANNER_PROMPT` (`prompts.py`)**

Trong `backend/src/agents/prompts.py`, tìm dòng cuối cùng của danh sách
"Available write tools" (dòng `create_bulk_rfq(...)`, ngay trước dòng
trống + "From the user's message, choose the matching tool..."), thêm
NGAY SAU nó:

```python
- send_order_confirmation_email(order_ref: str)  # gửi mail XÁC NHẬN đơn bán ĐÃ XÁC NHẬN cho khách qua email (dùng template Odoo "Sales: Order Confirmation"); order_ref = mã đơn bán, vd "S00012"; KHÔNG tự động chạy sau confirm_sale_order — chỉ gọi khi user yêu cầu rõ ràng
```

**Bắt buộc bước này** — coordinator không nằm trong `NEXT_STEPS` nên đây
là đường DUY NHẤT LLM biết tool tồn tại; thiếu dòng này, `pending_action.tool`
không bao giờ là `"send_order_confirmation_email"` và toàn bộ coordinator
không thể chạm tới được từ một lượt chat thật (dù mọi test dựng state tay
vẫn xanh — đúng lớp lỗi mà `write-confirmation-ux-fix` từng dính).

- [ ] **Step 8: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_mail_write.py -v`
Expected: PASS toàn bộ 8 test.

- [ ] **Step 9: Chạy test hồi quy toàn agents + auto_chain + graph_build**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/ -q -m "not live and not integration"`
Expected: không có fail MỚI. Đặc biệt xác nhận
`test_auto_chain.py::test_confirm_in_chain_la_tap_tuong_minh_chi_2_tool_dung_tien`
(nếu còn tên cũ, giờ SẼ fail vì `CONFIRM_IN_CHAIN` có 3 phần tử — đây là
**thay đổi có chủ đích**, không phải hồi quy; nếu gặp, sửa test đó khớp
tập 3 phần tử mới, cùng commit). Cũng kiểm `test_graph_build.py` — graph
thật phải build được không lỗi (bắt được ngay nếu nối dây Step 6 sai vị
trí/tên node).

- [ ] **Step 10: Commit**

```bash
git add mcp-servers/odoo/tools/mail.py backend/src/agents/mail_write.py backend/src/agents/write_registry.py backend/src/agents/graph.py backend/src/agents/prompts.py backend/tests/agents/test_mail_write.py
git commit -m "feat(agents): coordinator send_order_confirmation_email 2-node — sửa bug replay + cron an toàn + đăng ký planner"
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

ĐẠT khi: hiện bản xem trước (**tên/email người nhận thật** — không phải
chỉ số lượng, sau fix wave Finding 4 của final review — + tiêu đề) rồi
mới hỏi xác nhận, **chưa** gửi gì; và **không** tự động chạy tiếp
`deliver_order` (xác nhận đơn vẫn ở đúng trạng thái, không bị giao hàng
ngoài ý muốn).

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
