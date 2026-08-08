# Mở rộng gửi mail sang 3 điểm nối mới — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm 3 coordinator gửi mail (`send_invoice_email`, `send_rfq_email`,
`send_quotation_email`) bằng cách gom cả 4 coordinator gửi mail (kể cả
`send_order_confirmation_email` đã có) về chung một factory tham số hoá.

**Architecture:** `backend/src/agents/mail_write.py` chuyển từ hardcode
`sale.order` sang `EmailCfg` + 2 factory tham số hoá (Node 1 preview, Node 2
confirm+send), theo đúng mẫu `OrderCfg`/`SALE_CFG`/`PURCHASE_CFG` đã có trong
`create_order.py`. `graph.py` giữ nguyên kiểu hand-wiring 2 node, nhân lên 4
cặp node riêng biệt qua vòng lặp trên danh sách config. Task 1 là refactor
thuần (chứng minh không đổi hành vi); Task 2 mới thêm tính năng.

**Tech Stack:** Python, LangGraph (2-node interrupt pattern), Odoo XML-RPC
qua MCP tool `preview_template_email`/`send_prepared_email`/
`discard_prepared_email` (KHÔNG sửa file tool — 3 tool này đã domain-agnostic).

## Global Constraints

- **KHÔNG sửa `mcp-servers/odoo/tools/mail.py`.** 3 tool MCP đã hoàn toàn
  domain-agnostic (nhận `template_name`/`res_model`/`ref` làm tham số).
  Quyết định BÁC BỎ `extra_domain` đã ghi trong spec §4 kèm bằng chứng đo
  thật — không thêm tham số nào vào tool.
- **KHÔNG đăng ký bất kỳ coordinator mới nào vào `NEXT_STEPS`.** Cả 3 khoá
  (`create_quotation`, `create_rfq`, `post_invoice`) ĐÃ có bước kế chiếm
  chỗ; `NEXT_STEPS` là dict một entry mỗi khoá nên thêm vào sẽ GHI ĐÈ im
  lặng, phá chuỗi có sẵn.
- **BẮT BUỘC thêm dòng vào `WRITE_PLANNER_PROMPT`** cho mỗi tool mới — vì
  không nằm trong `NEXT_STEPS`, đây là đường DUY NHẤT LLM biết tool tồn tại.
- Giữ nguyên bất biến 2 node: node preview KHÔNG được có unconditional edge
  thẳng `write_continuation` (preview là một write thật — tạo `mail.mail`).
- Live-verify TRƯỚC khi merge vào `main`, chạy trên worktree của nhánh.
- Test suite baseline hiện tại: `1212 passed, 4 skipped, 46 deselected`.

## Sửa spec: Node 2 KHÔNG generic 100%

Spec §2 viết "Node 2 ĐÃ generic 100% — không chứa gì riêng của sale... KHÔNG
cần config". **Sai** — phát hiện khi đọc code lúc viết plan này. Node 2 hiện
hardcode 4 chỗ riêng của sale: tiền tố text xác nhận `"Mail xác nhận đơn"`,
tên tool trong `_finish("send_order_confirmation_email", result)`, đọc
`args.get("order_ref")`, và câu từ chối `"Đã hủy gửi mail xác nhận đơn."`.
Vì vậy **cả 2 factory đều nhận `cfg`**, không phải chỉ Node 1. Mọi chỗ khác
của spec giữ nguyên.

---

### Task 1: `EmailCfg` + 2 factory tham số hoá (refactor thuần, không đổi hành vi)

**Files:**
- Modify: `backend/src/agents/mail_write.py`
- Modify: `backend/src/agents/write_registry.py:16-17, 49-51`
- Modify: `backend/src/agents/graph.py:18, 94-110`
- Test: `backend/tests/agents/test_mail_write.py` (chỉ đổi dòng dựng node,
  KHÔNG đổi assertion nào)

**Interfaces:**
- Produces (Task 2 dùng lại):
  - `EmailCfg(tool_name: str, template_name: str, res_model: str, ref_arg: str,
    label: str, missing_ref_msg: str)` — frozen dataclass, có 2 property
    `preview_node -> str` (`f"{tool_name}_preview"`) và `send_node -> str`
    (`tool_name`).
  - `make_send_template_email_preview_node(tools, cfg: EmailCfg)` → async node
  - `make_send_template_email_node(tools, cfg: EmailCfg)` → async node
  - `make_route_after_mail_preview(cfg: EmailCfg)` → `(state) -> str`
  - `MAIL_COORDINATOR_CFGS: tuple[EmailCfg, ...]` — Task 2 nối thêm 3 phần tử
  - `ORDER_CONFIRMATION_CFG: EmailCfg`

**Bối cảnh bắt buộc đọc trước:** đây là refactor THUẦN. Bằng chứng "không đổi
hành vi" là toàn bộ 11 test hiện có trong `test_mail_write.py` phải xanh mà
**KHÔNG sửa một assertion nào** — chỉ được sửa dòng *dựng* node (tên factory
đổi). Nếu phải sửa một assertion để test xanh, nghĩa là hành vi ĐÃ đổi: dừng
lại, báo cáo, đừng sửa assertion cho vừa.

Hai chuỗi hiển thị phải khớp CHÍNH XÁC bản cũ cho `ORDER_CONFIRMATION_CFG`:
`"mail xác nhận đơn".capitalize()` = `"Mail xác nhận đơn"` (khớp tiền tố
text xác nhận cũ), và `f"Đã hủy gửi {label}."` = `"Đã hủy gửi mail xác nhận
đơn."` (khớp câu từ chối cũ).

- [ ] **Step 1: Sửa helper dựng graph trong test cho khớp API mới (test đỏ trước)**

Trong `backend/tests/agents/test_mail_write.py`, thay TOÀN BỘ hàm `_graph`
(dòng 28-38) bằng:

```python
def _graph(cfg, preview_node, send_node):
    g = StateGraph(ERPAgentState)
    g.add_node(cfg.preview_node, preview_node)
    g.add_node(cfg.send_node, send_node)
    g.add_conditional_edges(
        cfg.preview_node, mw.make_route_after_mail_preview(cfg),
        {cfg.send_node: cfg.send_node, "write_continuation": END})
    g.add_edge(cfg.send_node, END)
    g.set_entry_point(cfg.preview_node)
    return g.compile(checkpointer=MemorySaver())


def _build(tools, cfg=mw.ORDER_CONFIRMATION_CFG):
    """Dựng graph 2-node cho MỘT EmailCfg — thay 2 factory hardcode cũ bằng
    factory tham số hoá (spec 2026-08-08 mail-trigger-points). Chỉ đổi CÁCH
    DỰNG; mọi assertion bên dưới giữ nguyên, đó chính là bằng chứng refactor
    không đổi hành vi."""
    return _graph(cfg,
                  mw.make_send_template_email_preview_node(tools, cfg),
                  mw.make_send_template_email_node(tools, cfg))
```

**Lưu ý bắt buộc:** hàm `_graph` cũ tham chiếu `mw.route_after_mail_preview`
(hàm module-level) và hardcode 2 tên node — cả hai đều biến mất sau Step 4,
nên KHÔNG được giữ nguyên hàm này.

Rồi thay MỌI chỗ xuất hiện cặp dòng này (có 10 chỗ trong file):

```python
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
```

thành:

```python
    graph = _build(tools)
```

KHÔNG sửa gì khác trong file này ở step này.

- [ ] **Step 2: Chạy test để xác nhận ĐỎ (factory mới chưa tồn tại)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py 2>&1 | tail -5`
Expected: FAIL — `AttributeError: module 'src.agents.mail_write' has no
attribute 'make_send_template_email_preview_node'`.

- [ ] **Step 3: Thêm `EmailCfg` + `ORDER_CONFIRMATION_CFG` vào `mail_write.py`**

Thêm `from dataclasses import dataclass` vào khối import đầu file, rồi chèn
khối sau NGAY TRƯỚC hàm `_finish` (khoảng dòng 77):

```python
@dataclass(frozen=True)
class EmailCfg:
    """Cấu hình 1 coordinator gửi mail. Theo đúng mẫu OrderCfg/SALE_CFG/
    PURCHASE_CFG trong create_order.py — không phát minh pattern mới.

    tool_name        tên tool coordinator (khoá WRITE_COORDINATORS) — cũng là
                     tên node 2, và là tool_name ghi vào last_write qua _finish
    template_name    tên mail.template Odoo, phải khớp CHÍNH XÁC
    res_model        model bản ghi nguồn (sale.order / purchase.order / account.move)
    ref_arg          tên arg LLM truyền vào ("order_ref" hoặc "invoice_ref")
    label            nhãn CHỮ THƯỜNG, vd "mail xác nhận đơn" — dùng cho CẢ text
                     xác nhận (.capitalize()) LẪN câu từ chối, nên đổi nó là
                     đổi cả hai chỗ, không lệch nhau được
    missing_ref_msg  câu hỏi lại khi LLM không truyền ref
    """
    tool_name: str
    template_name: str
    res_model: str
    ref_arg: str
    label: str
    missing_ref_msg: str

    @property
    def preview_node(self) -> str:
        return f"{self.tool_name}_preview"

    @property
    def send_node(self) -> str:
        return self.tool_name


ORDER_CONFIRMATION_CFG = EmailCfg(
    tool_name="send_order_confirmation_email",
    template_name="Sales: Order Confirmation",
    res_model="sale.order",
    ref_arg="order_ref",
    label="mail xác nhận đơn",
    missing_ref_msg="Bạn cần cho biết mã đơn bán cần gửi mail xác nhận.")

# Task 2 nối thêm 3 config mới vào tuple này. graph.py lặp trên NÓ để dựng
# node — thêm coordinator gửi mail = thêm 1 phần tử ở đây + 1 dòng
# WRITE_COORDINATORS + 1 dòng WRITE_PLANNER_PROMPT, không đụng graph.py.
MAIL_COORDINATOR_CFGS = (ORDER_CONFIRMATION_CFG,)
```

- [ ] **Step 4: Thay 2 factory hardcode bằng 2 factory tham số hoá**

Thay TOÀN BỘ khối từ `def make_send_order_confirmation_email_preview_node(tools):`
(dòng 83) tới hết `def route_after_mail_preview(state)` (dòng 203) bằng:

```python
def make_send_template_email_preview_node(tools, cfg: EmailCfg):
    """Node 1: soạn mail (1 write thật), lưu kết quả vào state. KHÔNG
    interrupt ở đây — xem docstring module."""
    by_name = {t.name: t for t in tools}

    async def send_template_email_preview_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        action = state.get("pending_action") or {}
        args = action.get("args") or {}
        ref = str(args.get(cfg.ref_arg) or "").strip()
        if not ref:
            return _msg(cfg.missing_ref_msg)

        preview_tool = by_name.get("preview_template_email")
        if preview_tool is None:
            return _msg("Công cụ soạn mail không khả dụng.")
        try:
            result = await preview_tool.ainvoke({
                "template_name": cfg.template_name,
                "res_model": cfg.res_model, "ref": ref})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi soạn mail: {e}")
        # preview_template_email trả JSON phẳng {ok, display, mail_id, subject,
        # recipients} — parse_write_result chỉ cần key "ok"+"display" để coi là
        # envelope hợp lệ, KHÔNG lồng dưới "data" (đó là shape khác của
        # erp_query/envelope.py). env ở đây CHÍNH LÀ dict đã json.loads.
        display, env = parse_write_result(result)
        if env is None:
            return _msg(display)

        # Lưu vào pending_action.args — Node 2 đọc từ ĐÂY, không gọi lại
        # preview_template_email. Đây là ranh giới persist thật (node này
        # return xong mới tới Node 2), không phải biến cục bộ sẽ mất khi
        # LangGraph replay.
        #
        # "recipients" (danh sách chuỗi người-nhận-thật), KHÔNG PHẢI
        # "recipient_count" (final review 2026-08-07, Finding 4) — số lượng
        # không cho người dùng biết AI định gửi mail cho AI, cổng xác nhận vô
        # nghĩa nếu không lộ ra được đối tượng thật.
        return {"pending_action": {**action,
                                   "args": {**args, "mail_id": env.get("mail_id"),
                                            "subject": env.get("subject"),
                                            "recipients": env.get("recipients")}}}

    return send_template_email_preview_node


def make_send_template_email_node(tools, cfg: EmailCfg):
    """Node 2: đọc mail_id/subject/recipients đã lưu (Node 1), xác nhận, gửi.
    Từ chối → hủy bản nháp (best-effort, thất bại im lặng nuốt vì bản nháp
    đã trơ tính từ lúc tạo — xem docstring module).

    RE-CHECK write_gate Ở ĐÂY, KHÔNG chỉ ở Node 1 (review round 2, Finding
    1 — Important): mọi coordinator 1-node khác tự động re-check gate ở MỌI
    lần resume, vì LangGraph replay TOÀN BỘ node (gồm cả check ở đầu) khi
    resume sau _interrupt(). Tách 2 node đã vô tình xóa mất bất biến đó —
    Node 1 chỉ chạy 1 lần TRƯỚC KHI interrupt tồn tại, nên gate có thể bị
    tắt (từ Odoo UI, giữa lúc câu hỏi xác nhận đang chờ) mà Node 1 không
    bao giờ biết. Đo thật: gate tắt lúc đang chờ + resume(confirm=True) →
    node cũ (không check) vẫn gửi mail thật.

    NHẬN cfg (spec mail-trigger-points sửa lại nhận định "Node 2 generic
    100%" của spec gốc): node này hardcode 4 chỗ riêng của sale — tiền tố
    text xác nhận, tên tool cho _finish, tên arg ref, và câu từ chối."""
    by_name = {t.name: t for t in tools}

    async def _discard_draft(mail_id) -> None:
        """Best-effort dọn dẹp bản nháp bị từ chối/gate-tắt. Bản nháp đã trơ
        tính (state='cancel' — mcp-servers/odoo/tools/mail.py, spec
        2026-08-08) ngay từ lúc Node 1 tạo ra nó, nên thất bại ở đây (vd
        unlink cũng bị chặn bởi write_actions_enabled() giống mọi write
        khác) chỉ để lại một bản ghi rác nằm im trong Odoo — KHÔNG còn kéo
        theo rủi ro gửi ngoài ý muốn (khác thiết kế cũ trước 2026-08-08)."""
        discard_tool = by_name.get("discard_prepared_email")
        if discard_tool is None:
            return
        try:
            await discard_tool.ainvoke({"mail_id": mail_id})
        except Exception:  # noqa: BLE001 — best-effort, không raise cho user
            pass

    async def send_template_email_node(state: ERPAgentState) -> dict:
        args = (state.get("pending_action") or {}).get("args") or {}
        mail_id = args.get("mail_id")

        if not write_gate.write_actions_enabled():
            # Bản nháp (Node 1) đã tồn tại thật, nhưng đã trơ tính
            # (state='cancel', spec 2026-08-08) ngay từ lúc tạo — dọn ở đây
            # chỉ là best-effort, không còn ảnh hưởng tới an toàn (xem
            # docstring module + _discard_draft).
            await _discard_draft(mail_id)
            return _msg(WRITE_DISABLED_MSG)

        ref = str(args.get(cfg.ref_arg) or "")
        recipients = args.get("recipients") or []
        preview_text = (f"{cfg.label.capitalize()} {ref}:\n"
                        f"  Tới: {', '.join(recipients) if recipients else 'không rõ người nhận'}\n"
                        f"  Tiêu đề: {args.get('subject')}\n"
                        + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": preview_text,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            await _discard_draft(mail_id)
            return _msg(f"Đã hủy gửi {cfg.label}.")

        send_tool = by_name.get("send_prepared_email")
        if send_tool is None:
            return _msg("Công cụ gửi mail không khả dụng.")
        try:
            result = await send_tool.ainvoke({"mail_id": mail_id})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi gửi mail: {e}")
        return _finish(cfg.tool_name, result)

    return send_template_email_node


def make_route_after_mail_preview(cfg: EmailCfg):
    """Node 1 → Node 2 (thành công, có mail_id) hoặc thẳng write_continuation
    (lỗi/thiếu input — Node 1 đã tự trả _msg lỗi, Node 2 không cần chạy).
    Tham số hoá theo cfg vì tên node đích khác nhau giữa 4 coordinator."""
    def route_after_mail_preview(state: ERPAgentState) -> str:
        args = (state.get("pending_action") or {}).get("args") or {}
        if args.get("mail_id"):
            return cfg.send_node
        return "write_continuation"

    return route_after_mail_preview
```

- [ ] **Step 5: Cập nhật docstring module cho khớp thiết kế mới**

Trong docstring module `mail_write.py`, thay 2 dòng đầu:

```python
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07, cập nhật
spec 2026-08-08 (bản nháp trơ tính — xem mcp-servers/odoo/tools/mail.py).
```

thành:

```python
"""Coordinator gửi mail thật — spec 2026-08-07, cập nhật spec 2026-08-08
(bản nháp trơ tính — xem mcp-servers/odoo/tools/mail.py) và spec 2026-08-08
mail-trigger-points (gom 4 coordinator gửi mail về chung 1 factory tham số
hoá EmailCfg, theo mẫu OrderCfg/SALE_CFG/PURCHASE_CFG của create_order.py).
```

Và thay 2 dòng mô tả tên node cụ thể:

```python
  Node 1 (send_order_confirmation_email_preview): gọi preview_template_email
```
```python
  Node 2 (send_order_confirmation_email): đọc dữ liệu đã lưu từ Node 1
```

thành:

```python
  Node 1 (cfg.preview_node): gọi preview_template_email
```
```python
  Node 2 (cfg.send_node): đọc dữ liệu đã lưu từ Node 1
```

- [ ] **Step 6: Cập nhật `write_registry.py`**

Thay import (dòng 16-17):

```python
from .mail_write import (make_send_order_confirmation_email_preview_node,
                         make_send_order_confirmation_email_node)
```

thành:

```python
from .mail_write import make_send_template_email_preview_node, ORDER_CONFIRMATION_CFG
```

Thay entry registry (dòng 49-51):

```python
    "send_order_confirmation_email": Spec(
        "send_order_confirmation_email_preview",
        lambda llm, tools: make_send_order_confirmation_email_preview_node(tools)),
```

thành:

```python
    # Spec.node PHẢI khớp cfg.preview_node — graph.py lặp trên
    # MAIL_COORDINATOR_CFGS để dựng node 2 + conditional edge, hai bên phải
    # gọi cùng một tên node thì đồ thị mới nối được.
    ORDER_CONFIRMATION_CFG.tool_name: Spec(
        ORDER_CONFIRMATION_CFG.preview_node,
        lambda llm, tools: make_send_template_email_preview_node(
            tools, ORDER_CONFIRMATION_CFG)),
```

- [ ] **Step 7: Cập nhật `graph.py` — lặp trên `MAIL_COORDINATOR_CFGS`**

Thay import (dòng 18):

```python
from .mail_write import make_send_order_confirmation_email_node, route_after_mail_preview
```

thành:

```python
from .mail_write import (MAIL_COORDINATOR_CFGS, make_send_template_email_node,
                         make_route_after_mail_preview)
```

Thay khối wiring (dòng 94-110):

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

thành:

```python
    mail_preview_nodes = {cfg.preview_node for cfg in MAIL_COORDINATOR_CFGS}
    for spec in WRITE_COORDINATORS.values():
        if spec.node in mail_preview_nodes:
            continue  # coordinator 2 node, nối tay ngay dưới — xem docstring
                     # mail_write.py: preview là 1 write thật, không được
                     # unconditional-edge thẳng write_continuation
        g.add_edge(spec.node, "write_continuation")

    # Mỗi coordinator gửi mail là 2 node. Node 1 (preview) đã add ở vòng lặp
    # add_node phía trên (.node của Spec trỏ vào nó). Node 2 (gửi) KHÔNG nằm
    # trong WRITE_COORDINATORS — add tay ở đây, MỘT CẶP RIÊNG cho mỗi cfg
    # (không share node instance giữa các lối vào).
    for cfg in MAIL_COORDINATOR_CFGS:
        g.add_node(cfg.send_node, make_send_template_email_node(tools, cfg))
        g.add_conditional_edges(
            cfg.preview_node, make_route_after_mail_preview(cfg),
            {cfg.send_node: cfg.send_node,
             "write_continuation": "write_continuation"})
        g.add_edge(cfg.send_node, "write_continuation")
```

- [ ] **Step 8: Chạy test file mail — phải XANH, KHÔNG sửa assertion nào**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py -v 2>&1 | tail -20`
Expected: PASS toàn bộ 11 test. Nếu một assertion nào đỏ → hành vi ĐÃ đổi:
DỪNG, báo cáo, KHÔNG sửa assertion cho vừa.

- [ ] **Step 9: Chạy toàn bộ suite xác nhận không hồi quy**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration" 2>&1 | tail -5`
Expected: `1212 passed, 4 skipped, 46 deselected` — đúng bằng baseline
(task này không thêm test mới).

- [ ] **Step 10: Commit**

```bash
git add backend/src/agents/mail_write.py backend/src/agents/write_registry.py backend/src/agents/graph.py backend/tests/agents/test_mail_write.py
git commit -m "$(cat <<'EOF'
refactor(mail): gom coordinator gửi mail về factory tham số hoá EmailCfg

Chuẩn bị cho 3 điểm nối mới. Refactor thuần: toàn bộ 11 test hiện có xanh
KHÔNG sửa assertion nào — chỉ đổi cách dựng node. Node 2 cũng nhận cfg
(sửa nhận định "Node 2 generic 100%" của spec: nó hardcode 4 chỗ riêng
của sale).
EOF
)"
```

---

### Task 2: 3 coordinator gửi mail mới

**Files:**
- Modify: `backend/src/agents/mail_write.py` (thêm 3 `EmailCfg`, nối vào `MAIL_COORDINATOR_CFGS`)
- Modify: `backend/src/agents/write_registry.py` (3 dòng `WRITE_COORDINATORS`, `CONFIRM_IN_CHAIN`)
- Modify: `backend/src/agents/prompts.py` (3 dòng `WRITE_PLANNER_PROMPT`)
- Test: `backend/tests/agents/test_mail_write.py`, `backend/tests/agents/test_graph_build.py`

**Interfaces:**
- Consumes (từ Task 1): `EmailCfg`, `make_send_template_email_preview_node(tools, cfg)`,
  `make_send_template_email_node(tools, cfg)`, `make_route_after_mail_preview(cfg)`,
  `MAIL_COORDINATOR_CFGS`, `ORDER_CONFIRMATION_CFG`.
- `graph.py` KHÔNG cần sửa ở task này — Task 1 đã làm nó lặp trên
  `MAIL_COORDINATOR_CFGS`; thêm config là đủ.

**Bối cảnh bắt buộc đọc trước:** hóa đơn NHÁP có `name = False` (đo thật
2026-08-08), nên `send_invoice_email` chỉ áp dụng cho hóa đơn ĐÃ phát hành —
tra theo mã sẽ tự trả "Không tìm thấy bản ghi… trong account.move" cho hóa
đơn nháp. Đó là hành vi ĐÚNG, không cần chặn riêng (spec §5).

- [ ] **Step 1: Viết test đăng ký cho 3 tool mới (đỏ trước)**

Thêm vào cuối `backend/tests/agents/test_mail_write.py`:

```python
def test_ba_coordinator_mail_moi_dang_ky_day_du():
    """Cùng lớp bảo vệ như test_send_order_confirmation_email_registered_...
    ở trên: 3 tool này KHÔNG nằm trong NEXT_STEPS (cố ý — cả 3 khoá đã có
    bước kế chiếm chỗ, thêm vào sẽ GHI ĐÈ im lặng), nên dòng trong
    WRITE_PLANNER_PROMPT là đường DUY NHẤT LLM biết chúng tồn tại. Thiếu
    dòng đó thì coordinator dù đúng hoàn toàn vẫn không bao giờ chạm tới
    được từ một lượt chat thật."""
    from src.agents.write_registry import (COORDINATED_TOOLS, WRITE_COORDINATORS,
                                            NEXT_STEPS, CONFIRM_IN_CHAIN)
    from src.agents.prompts import WRITE_PLANNER_PROMPT
    for tool, ref_arg in (("send_invoice_email", "invoice_ref"),
                          ("send_rfq_email", "order_ref"),
                          ("send_quotation_email", "order_ref")):
        assert tool in COORDINATED_TOOLS, tool
        assert WRITE_COORDINATORS[tool].node == f"{tool}_preview", tool
        assert tool not in NEXT_STEPS, tool
        assert tool in CONFIRM_IN_CHAIN, tool
        assert f"{tool}({ref_arg}" in WRITE_PLANNER_PROMPT, tool


def test_moi_cfg_mail_co_template_va_model_rieng_biet():
    """Copy-paste một EmailCfg rồi quên đổi template_name/res_model sẽ khiến
    một coordinator âm thầm gửi SAI loại mail cho SAI đối tượng — lỗi chỉ lộ
    ra khi mail đã bay đi thật. Khoá lại: 4 config phải đôi một khác nhau ở
    cả tool_name lẫn cặp (template_name, res_model)."""
    cfgs = mw.MAIL_COORDINATOR_CFGS
    assert len(cfgs) == 4
    assert len({c.tool_name for c in cfgs}) == 4
    assert len({(c.template_name, c.res_model) for c in cfgs}) == 4
    assert len({c.preview_node for c in cfgs}) == 4
    assert len({c.send_node for c in cfgs}) == 4


@pytest.mark.asyncio
async def test_cfg_quyet_dinh_template_model_va_ten_arg_gui_xuong_tool(monkeypatch):
    """Node 1 phải chuyển ĐÚNG template_name/res_model của cfg xuống tool, và
    đọc ref từ ĐÚNG tên arg của cfg (invoice_ref cho hóa đơn, order_ref cho
    đơn) — nếu nó vẫn hardcode "order_ref" như bản trước refactor thì
    send_invoice_email sẽ luôn báo thiếu mã dù LLM truyền invoice_ref đúng."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    cfg = mw.INVOICE_EMAIL_CFG
    preview_calls, send_calls, discard_calls = [], [], []
    preview_tool, send_tool, discard_tool = _tools(preview_calls, send_calls, discard_calls)
    tools = [preview_tool, send_tool, discard_tool]
    graph = _build(tools, cfg)
    state = {"messages": [], "intent": "erp_write", "confirmed": None,
             "pending_action": {"tool": cfg.tool_name,
                                "args": {"invoice_ref": "INV/2026/00030"},
                                "summary": "x"}}
    res = await graph.ainvoke(state, {"configurable": {"thread_id": "mi1"}})
    assert preview_calls == [{"template_name": "Invoice: Sending",
                              "res_model": "account.move",
                              "ref": "INV/2026/00030"}]
    assert "INV/2026/00030" in res["__interrupt__"][0].value["question"]
    assert send_calls == []
```

- [ ] **Step 2: Chạy 3 test mới để xác nhận ĐỎ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py -k "moi or cfg" 2>&1 | tail -15`
Expected: FAIL — `KeyError: 'send_invoice_email'` / `AttributeError:
INVOICE_EMAIL_CFG` (config và đăng ký chưa tồn tại).

- [ ] **Step 3: Thêm 3 `EmailCfg` vào `mail_write.py`**

Thay khối `MAIL_COORDINATOR_CFGS = (ORDER_CONFIRMATION_CFG,)` (Task 1 Step 3)
bằng:

```python
QUOTATION_EMAIL_CFG = EmailCfg(
    tool_name="send_quotation_email",
    template_name="Sales: Send Quotation",
    res_model="sale.order",
    ref_arg="order_ref",
    label="mail báo giá",
    missing_ref_msg="Bạn cần cho biết mã báo giá cần gửi mail.")

RFQ_EMAIL_CFG = EmailCfg(
    tool_name="send_rfq_email",
    template_name="Purchase: Request For Quotation",
    res_model="purchase.order",
    ref_arg="order_ref",
    label="mail yêu cầu báo giá",
    missing_ref_msg="Bạn cần cho biết mã đơn mua (RFQ) cần gửi mail.")

# Hóa đơn NHÁP có name = False (đo thật 2026-08-08), nên tra theo mã chỉ
# tìm được hóa đơn ĐÃ PHÁT HÀNH — đúng ý đồ (post_invoice → gửi mail), và
# hóa đơn nháp tự nhiên trả "Không tìm thấy bản ghi… trong account.move".
INVOICE_EMAIL_CFG = EmailCfg(
    tool_name="send_invoice_email",
    template_name="Invoice: Sending",
    res_model="account.move",
    ref_arg="invoice_ref",
    label="mail hóa đơn",
    missing_ref_msg="Bạn cần cho biết số hóa đơn cần gửi mail.")

# graph.py lặp trên tuple NÀY để dựng node — thêm coordinator gửi mail =
# thêm 1 phần tử ở đây + 1 dòng WRITE_COORDINATORS + 1 dòng
# WRITE_PLANNER_PROMPT, không đụng graph.py.
MAIL_COORDINATOR_CFGS = (ORDER_CONFIRMATION_CFG, QUOTATION_EMAIL_CFG,
                         RFQ_EMAIL_CFG, INVOICE_EMAIL_CFG)
```

- [ ] **Step 4: Đăng ký 3 coordinator trong `write_registry.py`**

Thay import `from .mail_write import make_send_template_email_preview_node, ORDER_CONFIRMATION_CFG`
thành:

```python
from .mail_write import (make_send_template_email_preview_node,
                         MAIL_COORDINATOR_CFGS)
```

**XÓA HẲN** entry `ORDER_CONFIRMATION_CFG.tool_name: Spec(...)` (do Task 1
Step 6 thêm) ra khỏi dict literal `WRITE_COORDINATORS = {...}` — vòng lặp
dưới đây sẽ đăng ký lại nó cùng 3 cái mới. Rồi thêm khối sau NGAY SAU dấu
`}` đóng dict, và **BẮT BUỘC trước** dòng `COORDINATED_TOOLS = frozenset(...)`
(dòng đó chụp lại nội dung dict tại thời điểm import — chạy vòng lặp sau nó
thì 4 tool gửi mail sẽ vắng mặt khỏi `COORDINATED_TOOLS`, planner không định
tuyến được):

```python
# 4 coordinator gửi mail dựng từ MAIL_COORDINATOR_CFGS (mail_write.py) —
# Spec.node PHẢI khớp cfg.preview_node, vì graph.py lặp trên chính tuple đó
# để dựng node 2 + conditional edge; hai bên lệch tên là đồ thị đứt.
# Dùng default-arg `c=cfg` để mỗi lambda bắt ĐÚNG cfg của vòng lặp mình —
# thiếu nó, cả 4 lambda cùng trỏ vào cfg CUỐI (late binding), nghĩa là mọi
# coordinator gửi mail đều gửi mail hóa đơn.
for cfg in MAIL_COORDINATOR_CFGS:
    WRITE_COORDINATORS[cfg.tool_name] = Spec(
        cfg.preview_node,
        lambda llm, tools, c=cfg: make_send_template_email_preview_node(tools, c))
```

Thay `CONFIRM_IN_CHAIN` (dòng 63-64):

```python
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment",
                              "send_order_confirmation_email"})
```

thành:

```python
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment"}
                             | {cfg.tool_name for cfg in MAIL_COORDINATOR_CFGS})
```

- [ ] **Step 5: Thêm 3 dòng vào `WRITE_PLANNER_PROMPT`**

Trong `backend/src/agents/prompts.py`, thêm NGAY SAU dòng
`- send_order_confirmation_email(order_ref: str)  # ...` (dòng 95):

```
- send_quotation_email(order_ref: str)  # gửi BÁO GIÁ (đơn bán CHƯA xác nhận) cho khách qua email (template Odoo "Sales: Send Quotation"); order_ref = mã báo giá, vd "S00161"; chỉ gọi khi user yêu cầu rõ ràng
- send_rfq_email(order_ref: str)  # gửi YÊU CẦU BÁO GIÁ cho NHÀ CUNG CẤP qua email (template Odoo "Purchase: Request For Quotation"); order_ref = mã đơn mua, vd "P00078"; chỉ gọi khi user yêu cầu rõ ràng
- send_invoice_email(invoice_ref: str)  # gửi HÓA ĐƠN ĐÃ PHÁT HÀNH cho khách qua email (template Odoo "Invoice: Sending"); invoice_ref = số hóa đơn thật, vd "INV/2026/00030" (hóa đơn NHÁP chưa có số — phải phát hành trước); chỉ gọi khi user yêu cầu rõ ràng
```

- [ ] **Step 6: Mở rộng bất biến đồ thị từ 1 node lên cả 4**

Trong `backend/tests/agents/test_graph_build.py`, thay thân hàm
`test_mail_preview_node_has_no_unconditional_edge_to_continuation`
(dòng 148-154, GIỮ NGUYÊN docstring phía trên) bằng:

```python
    from src.agents.mail_write import MAIL_COORDINATOR_CFGS
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target, e.conditional) for e in graph.get_graph().edges]
    assert len(MAIL_COORDINATOR_CFGS) == 4, "rỗng/thiếu thì test này vô nghĩa"
    for cfg in MAIL_COORDINATOR_CFGS:
        assert (cfg.preview_node, "write_continuation", False) not in edges, cfg.tool_name
        # And the conditional path (the CORRECT wiring) must still exist.
        assert (cfg.preview_node, "write_continuation", True) in edges, cfg.tool_name
        assert (cfg.preview_node, cfg.send_node, True) in edges, cfg.tool_name
```

- [ ] **Step 7: Chạy 2 file test liên quan, xác nhận XANH**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py tests/agents/test_graph_build.py -v 2>&1 | tail -20`
Expected: PASS toàn bộ (11 test cũ + 3 test mới trong `test_mail_write.py`,
và toàn bộ `test_graph_build.py`).

- [ ] **Step 8: Chạy toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration" 2>&1 | tail -5`
Expected: `1215 passed, 4 skipped, 46 deselected` (baseline 1212 + 3 test mới).

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/mail_write.py backend/src/agents/write_registry.py backend/src/agents/prompts.py backend/tests/agents/test_mail_write.py backend/tests/agents/test_graph_build.py
git commit -m "$(cat <<'EOF'
feat(mail): 3 điểm nối gửi mail mới (hóa đơn, RFQ, báo giá)

send_invoice_email / send_rfq_email / send_quotation_email dựng từ cùng
factory EmailCfg với send_order_confirmation_email. Không vào NEXT_STEPS
(cả 3 khoá đã có bước kế chiếm chỗ) — đăng ký qua WRITE_PLANNER_PROMPT.
EOF
)"
```

---

### Task 3: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi kết quả vào
`docs/superpowers/plans/2026-08-08-mail-trigger-points-report.md`.

**Bối cảnh bắt buộc đọc trước:** unit test ở Task 1-2 mock toàn bộ tool, KHÔNG
đủ để chứng minh 3 template mới render được và cơ chế bản-nháp-trơ-tính hoạt
động trên model MỚI (`account.move`, `purchase.order`) — trước đây chỉ đo trên
`sale.order`. Gọi qua `/v1/chat/completions` thật, resend toàn bộ lịch sử hội
thoại mỗi lượt, KHÔNG dùng `session_id` (khớp shape client Open WebUI thật).

- [ ] **Step 1: Khởi động lại backend + mcp-odoo trỏ vào code WORKTREE**

Dừng tiến trình đang giữ cổng 8002/8003 (nếu có), rồi khởi động lại từ
worktree của nhánh này — KHÔNG phải `D:\Youdoo` (main). Xác nhận PID
trước/sau đã đổi thật, và `GET http://localhost:8002/health` trả
`agent_ready = true`.

- [ ] **Step 2: Tiêu chí 1 — `send_invoice_email` trên hóa đơn ĐÃ phát hành**

Tìm một hóa đơn khách `state='posted'` thật qua XML-RPC, rồi gửi:
`"Gửi mail hóa đơn [số hóa đơn thật] cho khách"`.

ĐẠT khi: hiện bản xem trước với **tên + email khách thật** và tiêu đề, chưa
gửi gì; đọc `mail.mail.state` trực tiếp qua XML-RPC = **`'cancel'`** (cơ chế
trơ tính hoạt động trên `account.move`, model chưa từng đo). Trả lời `"có"` →
`"Đã gửi mail."`, bản ghi biến mất (auto_delete sau gửi thành công).

- [ ] **Step 3: Tiêu chí 2 — `send_rfq_email` gửi tới NHÀ CUNG CẤP**

Tìm một `purchase.order` thật, gửi: `"Gửi mail yêu cầu báo giá đơn mua [mã
đơn thật] cho nhà cung cấp"`.

ĐẠT khi: bản xem trước hiện **tên + email NHÀ CUNG CẤP** (KHÔNG phải khách
hàng — đây là điểm rủi ro cao nhất của plan, vai trò người nhận khác 3 ca
kia, phải nhìn tận mắt chứ không suy ra từ các ca khác); `mail.mail.state` =
`'cancel'` trước xác nhận. Trả lời `"không"` → xác nhận bản ghi đã bị xóa.

- [ ] **Step 4: Tiêu chí 3 — `send_quotation_email` trên báo giá nháp**

Tìm một `sale.order` `state='draft'` thật, gửi: `"Gửi mail báo giá [mã báo
giá thật] cho khách"`.

ĐẠT khi: bản xem trước đúng khách + tiêu đề báo giá; `mail.mail.state` =
`'cancel'`; trả lời `"có"` → gửi thành công.

- [ ] **Step 5: Tiêu chí 4 — `send_order_confirmation_email` KHÔNG hồi quy**

Gửi `"Gửi mail xác nhận đơn [mã đơn đã xác nhận thật] cho khách"` — đúng
đường đã live-verify ở 2 plan trước, giờ chạy qua factory mới.

ĐẠT khi: kết quả giống hệt lần đo trước (bản xem trước đúng định dạng
`"Mail xác nhận đơn S00xxx:"`, `state='cancel'`, gửi thành công) — chứng minh
refactor Task 1 không đổi hành vi trên môi trường thật, không chỉ trong test.

- [ ] **Step 6: Viết report và commit**

Ghi rõ từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (nội dung phản hồi thật,
`mail.mail.state` đọc trực tiếp từ Odoo ở mỗi bước). Nếu một tiêu chí không
chạy được vì thiếu dữ liệu phù hợp, ghi rõ **CHƯA ĐO ĐƯỢC** (phân biệt với
"đã thử và fail") — không suy đoán, không tô hồng.

```bash
git add docs/superpowers/plans/2026-08-08-mail-trigger-points-report.md
git commit -m "docs(mail-trigger-points): kết quả live-verify"
```
