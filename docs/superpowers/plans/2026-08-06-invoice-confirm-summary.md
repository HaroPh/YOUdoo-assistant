# Tóm tắt hóa đơn trước cổng xác nhận — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người dùng thấy bảng dòng hàng + số tiền của đúng hóa đơn *trước*
khi xác nhận `post_invoice` / `register_payment`, kể cả khi hai thao tác này
là bước trong chuỗi tự động.

**Architecture:** Hai node điều phối mới theo đúng khuôn `create_credit_memo`
đã có (backend resolve → render → `_interrupt` → gọi tool bằng `invoice_id`
đã resolve). Đăng ký vào `WRITE_COORDINATORS` khiến đường gọi trực tiếp chạy
đúng mà không sửa routing. Đường chuỗi tự động được chuyển hướng vào chính
hai node đó bằng một tập tường minh `CONFIRM_IN_CHAIN`.

**Tech Stack:** Python 3.11, LangGraph (interrupt/checkpoint), pytest +
pytest-asyncio, Odoo XML-RPC qua `erp_query.gateway`.

**Spec:** `docs/superpowers/specs/2026-08-06-invoice-confirm-summary-design.md`

## Global Constraints

- Câu xác nhận **bắt buộc** dùng hằng số `WRITE_CONFIRM_SUFFIX` từ
  `src/agents/prompts.py` — không tự chế câu mới (bất biến C tầng 3 đã gom
  19 chỗ về hằng số này).
- Coordinator **luôn** gọi tool kèm `invoice_id` đã resolve — không bao giờ
  để tool tự resolve lại (spec §5.1).
- Bộ lọc `["display_type", "=", "product"]` khi đọc `account.move.line` là
  **bắt buộc**, không phải tối ưu.
- Tên sản phẩm hiển thị lấy từ `product_id[1]`, **không** lấy `line["name"]`.
- `register_payment` hiển thị `amount_residual` làm số tiền sẽ chuyển, **không**
  phải `amount_total`.
- `CONFIRM_IN_CHAIN` phải là tập **tường minh** `{"post_invoice",
  "register_payment"}` — **không** được viết thành điều kiện
  `in COORDINATED_TOOLS`.
- Mọi hàm `erp_query` trả envelope `ok(data, display)` / `err(message)` từ
  `src/erp_query/envelope.py`, và nhận tham số `gw=None` để test tiêm gateway giả.
- Không thêm cờ môi trường bật/tắt hành vi mới.

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/src/erp_query/accounting.py` (sửa) | 3 hàm đọc mới: chi tiết hóa đơn + dòng hàng, tìm nháp, tìm hóa đơn còn nợ | 1 |
| `backend/tests/erp_query/test_accounting.py` (sửa) | Test 3 hàm trên bằng gateway giả | 1 |
| `backend/src/agents/invoice_write.py` (**mới**) | Helper render/pick + 2 node điều phối | 2, 3 |
| `backend/tests/agents/test_invoice_write.py` (**mới**) | Test 2 node bằng tool giả + graph in-memory | 2, 3 |
| `backend/src/agents/write_registry.py` (sửa) | Đăng ký 2 coordinator + hằng số `CONFIRM_IN_CHAIN` | 2, 3, 4 |
| `backend/src/agents/continuation.py` (sửa) | Bước chuỗi đụng tiền không auto-run | 4 |
| `backend/src/agents/graph.py` (sửa) | Mở rộng target map của `write_continuation` | 4 |
| `backend/tests/agents/test_auto_chain.py` (sửa) | Test hành vi chuỗi mới + chống hồi quy | 4 |

---

## Sai lệch có chủ đích so với spec

Spec §5.1 đề xuất một chốt chặn: *"một test `@pytest.mark.live` gọi cả hai
đường với cùng `partner_name` và assert chúng chọn ra cùng một
`invoice_id`"*. **Plan này KHÔNG làm điều đó, vì nó không thực hiện được một
cách an toàn.**

Lý do: `post_invoice` **không tách rời** phần resolve khỏi hành động ghi —
gọi `post_invoice(partner_name="Acme")` sẽ **phát hành thật** một hóa đơn
trên Odoo, không có chế độ dry-run nào để chỉ lấy kết quả resolve. Một test
như vậy sẽ phát hành hóa đơn thật mỗi lần chạy suite.

Biện pháp thay thế đã có trong plan: bất biến "**luôn** truyền `invoice_id`"
được test trực tiếp
(`test_post_invoice_xac_nhan_thi_goi_bang_invoice_id`,
`test_register_payment_xac_nhan_thi_goi_bang_invoice_id` assert
`rec["args"] == {"invoice_id": ...}`). Chừng nào bất biến đó còn đúng thì
phần resolve của tool **không bao giờ chạy** trên đường này, nên hai bên
không thể lệch nhau lúc chạy thật.

Rủi ro còn lại (ai đó gọi tool trực tiếp không kèm `invoice_id`) được ghi
nhận là **chấp nhận**, không có test tự động phủ.

---

### Task 1: Ba hàm đọc hóa đơn trong `erp_query`

**Files:**
- Modify: `backend/src/erp_query/accounting.py`
- Test: `backend/tests/erp_query/test_accounting.py`

**Interfaces:**
- Consumes: `ok`/`err` từ `.envelope`, `default_gateway` từ `.gateway` (cả hai đã được import sẵn ở đầu file).
- Produces:
  - `get_invoice_detail(invoice_id, *, gw=None) -> envelope` với
    `data = {"invoice": <dict>, "lines": [<dict>, ...]}`
  - `find_draft_invoices(partner_name, amount=None, invoice_date=None, *, gw=None) -> envelope`
    với `data = {"rows": [...], "count": int}`
  - `find_open_invoices(invoice_ref=None, partner_name=None, amount=None, invoice_date=None, *, gw=None) -> envelope`
    với `data = {"rows": [...], "count": int}`

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/erp_query/test_accounting.py`:

```python
class TwoModelTransport:
    """account.move rồi account.move.line — phân biệt bằng tên model."""
    def __init__(self, move_rows, line_rows):
        self.move_rows = move_rows
        self.line_rows = line_rows
        self.calls = []

    def call(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        return self.move_rows if model == "account.move" else self.line_rows


_DRAFT = {"id": 105, "name": False, "partner_id": [41, "Acme Corporation"],
          "invoice_date": "2026-08-06", "amount_total": 17520.0,
          "amount_residual": 17520.0, "move_type": "in_invoice", "state": "draft"}
_LINE = {"product_id": [7, "[FURN_0789] Individual Workplace"],
         "quantity": 20.0, "price_subtotal": 17520.0}


def test_get_invoice_detail_loc_dong_product():
    """Bẫy thật đo trên Odoo 2026-08-06: account.move.line của một hóa đơn
    trả về CẢ dòng 'payment_term' (đối ứng phải thu/phải trả, 0 đồng).
    Thiếu bộ lọc display_type thì bảng tóm tắt có một dòng rác 0 đồng."""
    t = TwoModelTransport([_DRAFT], [_LINE])
    out = accounting.get_invoice_detail(105, gw=Gateway(t))
    assert out["status"] == "success"
    assert out["data"]["invoice"]["id"] == 105
    assert out["data"]["lines"] == [_LINE]
    line_domain = t.calls[1][2][0]
    assert ["move_id", "=", 105] in line_domain
    assert ["display_type", "=", "product"] in line_domain


def test_get_invoice_detail_khong_thay_thi_bao_loi():
    out = accounting.get_invoice_detail(999, gw=_gw([]))
    assert out["status"] == "error"
    assert "999" in out["display"]


def test_find_draft_invoices_domain_va_tra_danh_sach():
    """Trả DANH SÁCH: hóa đơn nháp chưa có số nên nhiều bản cùng đối tác là
    chuyện thường (đo thật: 5 bản nháp cùng 'Acme', 4 trùng số tiền)."""
    t = TwoModelTransport([_DRAFT, {**_DRAFT, "id": 99}], [])
    out = accounting.find_draft_invoices("Acme", gw=Gateway(t))
    assert out["data"]["count"] == 2
    dom = t.calls[0][2][0]
    assert ["state", "=", "draft"] in dom
    assert ["partner_id.name", "ilike", "Acme"] in dom


def test_find_draft_invoices_loc_them_khi_co_amount_va_date():
    t = TwoModelTransport([_DRAFT], [])
    accounting.find_draft_invoices("Acme", amount=140.0,
                                   invoice_date="2026-08-06", gw=Gateway(t))
    dom = t.calls[0][2][0]
    assert ["amount_total", "=", 140.0] in dom
    assert ["invoice_date", "=", "2026-08-06"] in dom


def test_find_draft_invoices_rong_thi_bao_loi():
    out = accounting.find_draft_invoices("Không Tồn Tại", gw=_gw([]))
    assert out["status"] == "error"


def test_find_open_invoices_chi_lay_con_no():
    """Hóa đơn đã trả hết không còn gì để thanh toán — đưa vào danh sách
    chọn chỉ gây nhiễu."""
    posted = {**_DRAFT, "id": 100, "name": "INV/2026/00028",
              "state": "posted", "move_type": "out_invoice",
              "amount_total": 350.0, "amount_residual": 350.0}
    t = TwoModelTransport([posted], [])
    out = accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t))
    assert out["data"]["count"] == 1
    dom = t.calls[0][2][0]
    assert ["state", "=", "posted"] in dom
    assert ["payment_state", "in", ["not_paid", "partial"]] in dom


def test_find_open_invoices_nhan_ca_invoice_ref_lan_partner_name():
    """register_payment nhận CẢ HAI — đường partner_name mơ hồ y hệt
    post_invoice nên phải xử lý cùng cách."""
    t = TwoModelTransport([], [])
    accounting.find_open_invoices(invoice_ref="INV/2026/00028", gw=Gateway(t))
    assert ["name", "=", "INV/2026/00028"] in t.calls[0][2][0]
    t2 = TwoModelTransport([], [])
    accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t2))
    assert ["partner_id.name", "ilike", "Acme"] in t2.calls[0][2][0]


def test_find_open_invoices_bao_gom_ca_hoa_don_mua():
    """KHÔNG dùng lại find_posted_invoice được: hàm đó lọc cứng
    move_type='out_invoice', trong khi register_payment phục vụ cả
    in_invoice (mình trả NCC)."""
    t = TwoModelTransport([], [])
    accounting.find_open_invoices(partner_name="Acme", gw=Gateway(t))
    dom = t.calls[0][2][0]
    move_type_cond = [c for c in dom if c[0] == "move_type"][0]
    assert "in_invoice" in move_type_cond[2]
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_accounting.py -k "detail or draft_invoices or open_invoices" -v`
Expected: FAIL — `AttributeError: module 'src.erp_query.accounting' has no attribute 'get_invoice_detail'`

- [ ] **Step 3: Cài đặt**

Thêm vào `backend/src/erp_query/accounting.py`, ngay dưới `_FIELDS`:

```python
_DETAIL_FIELDS = ["id", "name", "partner_id", "invoice_date", "amount_total",
                  "amount_residual", "move_type", "state"]
_LINE_FIELDS = ["product_id", "quantity", "price_subtotal"]
_INVOICE_TYPES = ["out_invoice", "in_invoice", "out_refund", "in_refund"]
```

Thêm ba hàm vào cuối file:

```python
def get_invoice_detail(invoice_id, *, gw=None):
    """Chi tiết 1 hóa đơn + dòng hàng, cho coordinator render bản tóm tắt
    trước cổng xác nhận ghi (spec 2026-08-06 §3.1).

    Lọc display_type='product' là BẮT BUỘC, không phải tối ưu: đo thật trên
    Odoo 2026-08-06 cho thấy account.move.line của một hóa đơn còn chứa dòng
    'payment_term' (dòng đối ứng phải thu/phải trả, số tiền 0) — không lọc
    thì bảng tóm tắt có một dòng rác 0 đồng."""
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("account.move", [["id", "=", invoice_id]],
                              _DETAIL_FIELDS, limit=1)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn: {e}")
    if not rows:
        return err(f"Không tìm thấy hóa đơn ID {invoice_id}.")
    try:
        lines = gw.search_read("account.move.line",
                               [["move_id", "=", invoice_id],
                                ["display_type", "=", "product"]],
                               _LINE_FIELDS, limit=100)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra dòng hóa đơn: {e}")
    return ok({"invoice": rows[0], "lines": lines},
              f"Hóa đơn ID {invoice_id}: {len(lines)} dòng.")


def find_draft_invoices(partner_name, amount=None, invoice_date=None, *, gw=None):
    """Danh sách hóa đơn NHÁP khớp tên đối tác — cho coordinator post_invoice.

    Trả DANH SÁCH (không phải một) có chủ đích: hóa đơn nháp chưa có số
    (name=False, đo thật 2026-08-06 — 5 bản nháp cùng 'Acme Corporation',
    4 trùng y hệt số tiền), nên coordinator phải để người dùng chọn TRƯỚC
    cổng xác nhận, thay vì để tool báo lỗi mơ hồ SAU khi đã xác nhận.
    Domain khớp domain của mcp-servers/odoo/tools/accounting.py:57-64."""
    gw = gw or default_gateway()
    domain = [["move_type", "in", _INVOICE_TYPES],
              ["state", "=", "draft"],
              ["partner_id.name", "ilike", partner_name]]
    if amount is not None:
        domain.append(["amount_total", "=", amount])
    if invoice_date:
        domain.append(["invoice_date", "=", invoice_date])
    try:
        rows = gw.search_read("account.move", domain, _DETAIL_FIELDS,
                              order="invoice_date desc", limit=10)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn nháp: {e}")
    if not rows:
        return err(f"Không tìm thấy hóa đơn nháp nào của '{partner_name}'.")
    return ok({"rows": rows, "count": len(rows)},
              f"{len(rows)} hóa đơn nháp.")


def find_open_invoices(invoice_ref=None, partner_name=None, amount=None,
                       invoice_date=None, *, gw=None):
    """Hóa đơn ĐÃ PHÁT HÀNH còn nợ — cho coordinator register_payment.

    KHÔNG dùng lại find_posted_invoice được: hàm đó lọc cứng
    move_type='out_invoice' (chỉ hóa đơn bán) trong khi register_payment
    phục vụ cả in_invoice (mình trả NCC), nó không đọc amount_residual, và
    chỉ nhận số hóa đơn chính xác chứ không nhận tên đối tác.

    payment_state lọc not_paid/partial: hóa đơn đã trả hết không còn gì để
    thanh toán, đưa vào danh sách chọn chỉ gây nhiễu."""
    gw = gw or default_gateway()
    domain = [["move_type", "in", _INVOICE_TYPES],
              ["state", "=", "posted"],
              ["payment_state", "in", ["not_paid", "partial"]]]
    if invoice_ref:
        domain.append(["name", "=", invoice_ref])
    if partner_name:
        domain.append(["partner_id.name", "ilike", partner_name])
    if amount is not None:
        domain.append(["amount_total", "=", amount])
    if invoice_date:
        domain.append(["invoice_date", "=", invoice_date])
    try:
        rows = gw.search_read("account.move", domain, _DETAIL_FIELDS,
                              order="invoice_date desc", limit=10)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra hóa đơn: {e}")
    if not rows:
        return err("Không tìm thấy hóa đơn đã phát hành còn nợ phù hợp.")
    return ok({"rows": rows, "count": len(rows)}, f"{len(rows)} hóa đơn.")
```

- [ ] **Step 4: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/erp_query/test_accounting.py -v`
Expected: PASS toàn bộ file (test cũ vẫn xanh).

- [ ] **Step 5: Commit**

```bash
git add backend/src/erp_query/accounting.py backend/tests/erp_query/test_accounting.py
git commit -m "feat(erp_query): đọc chi tiết hóa đơn + dòng hàng, tìm nháp/còn nợ"
```

---

### Task 2: Coordinator `post_invoice`

**Files:**
- Create: `backend/src/agents/invoice_write.py`
- Modify: `backend/src/agents/write_registry.py`
- Test: `backend/tests/agents/test_invoice_write.py` (mới)

**Interfaces:**
- Consumes: `accounting.get_invoice_detail`, `accounting.find_draft_invoices` (Task 1);
  `_by_id`, `_ttl_expiry`, `_msg`, `_disambig_q`, `WRITE_DISABLED_MSG` từ `.create_order`;
  `WRITE_CONFIRM_SUFFIX` từ `.prompts`; `parse_write_result` từ `.tool_result`.
- Produces:
  - `render_invoice_summary(head: str, lines: list, totals: list[str]) -> str`
  - `_pick_invoice(env: dict, label: str) -> tuple[str, dict]` — `("ok", <row>)` | `("msg", <state update>)`
  - `make_post_invoice_node(tools) -> node`
  - `Spec("post_invoice", ...)` trong `WRITE_COORDINATORS` dưới khóa `"post_invoice"`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_invoice_write.py`:

```python
import json
import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.invoice_write as iw
from src.agents import write_gate


def _fake_tool(name, recorder, ref="INV/2026/00030", res_id=105):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        recorder["args"] = args
        return json.dumps({"ok": True, "ref": ref, "model": "account.move",
                           "res_id": res_id, "state": "posted",
                           "display": "Đã phát hành."}, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _graph(node):
    g = StateGraph(ERPAgentState)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def _state(tool, args):
    return {"messages": [], "intent": "erp_write", "confirmed": None,
            "pending_action": {"tool": tool, "args": args, "summary": "x"}}


_DRAFT = {"id": 105, "name": False, "partner_id": [41, "Acme Corporation"],
          "invoice_date": "2026-08-06", "amount_total": 17520.0,
          "amount_residual": 17520.0, "move_type": "in_invoice", "state": "draft"}
_LINE = {"product_id": [7, "[FURN_0789] Individual Workplace"],
         "quantity": 20.0, "price_subtotal": 17520.0}


def _detail(monkeypatch, inv=None, lines=None):
    monkeypatch.setattr(iw.accounting, "get_invoice_detail", lambda *a, **k: {
        "status": "success",
        "data": {"invoice": inv or _DRAFT, "lines": lines or [_LINE]},
        "display": "x"})


def _drafts(monkeypatch, rows):
    monkeypatch.setattr(iw.accounting, "find_draft_invoices", lambda *a, **k: {
        "status": "success", "data": {"rows": rows, "count": len(rows)},
        "display": "x"})


# ── render ──────────────────────────────────────────────────────────────────

def test_render_dung_ten_san_pham_khong_dung_line_name():
    """Đo thật: line['name'] chứa mô tả NHIỀU DÒNG
    ('[FURN_0789] Individual Workplace\\n[FURN_0...') — hiển thị nó sẽ vỡ
    bảng. Tên đúng nằm ở product_id[1]."""
    out = iw.render_invoice_summary("Đầu:", [_LINE], ["  Tổng: 17.520"])
    assert "[FURN_0789] Individual Workplace × 20 = 17.520" in out
    assert "\n[FURN_0" not in out


def test_render_luon_ket_bang_hang_so_xac_nhan():
    from src.agents.prompts import WRITE_CONFIRM_SUFFIX
    out = iw.render_invoice_summary("Đầu:", [_LINE], ["  Tổng: 1"])
    assert out.endswith(WRITE_CONFIRM_SUFFIX)


# ── post_invoice: đường chuỗi (đã có invoice_id) ────────────────────────────

@pytest.mark.asyncio
async def test_post_invoice_co_id_thi_hien_bang_roi_moi_hoi(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p1"}}
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "confirm"
    assert "Acme Corporation" in itr["question"]
    assert "Individual Workplace × 20" in itr["question"]
    assert "17.520" in itr["question"]
    assert "args" not in rec           # chưa gọi tool trước khi xác nhận


@pytest.mark.asyncio
async def test_post_invoice_xac_nhan_thi_goi_tool_bang_invoice_id(monkeypatch):
    """Bất biến §5.1: LUÔN truyền invoice_id — nhánh đó của tool bỏ qua hoàn
    toàn phần resolve của chính nó, nên chỉ có ĐÚNG MỘT phép resolve."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p2"}}
    await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 105}
    assert res["last_write"]["tool"] == "post_invoice"


@pytest.mark.asyncio
async def test_post_invoice_tu_choi_thi_khong_goi_tool(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p3"}}
    await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert "args" not in rec
    assert "hủy" in res["messages"][-1].content.lower()


# ── post_invoice: đường gọi trực tiếp (phải resolve) ────────────────────────

@pytest.mark.asyncio
async def test_post_invoice_nhieu_nhap_thi_hoi_chon_truoc(monkeypatch):
    """Ca thật: 5 bản nháp cùng 'Acme', 4 trùng số tiền. Phải hỏi chọn
    TRƯỚC cổng xác nhận, không để tool báo lỗi SAU khi đã xác nhận."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _drafts(monkeypatch, [_DRAFT, {**_DRAFT, "id": 99, "amount_total": 140.0}])
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p4"}}
    res = await graph.ainvoke(_state("post_invoice", {"partner_name": "Acme"}), cfg)
    itr = res["__interrupt__"][0].value
    assert itr["kind"] == "disambiguation"
    assert len(itr["options"]) == 2
    res = await graph.ainvoke(Command(resume=99), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_post_invoice_mot_nhap_thi_di_thang_toi_xac_nhan(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _drafts(monkeypatch, [_DRAFT])
    _detail(monkeypatch)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    cfg = {"configurable": {"thread_id": "p5"}}
    res = await graph.ainvoke(_state("post_invoice", {"partner_name": "Acme"}), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_post_invoice_thieu_ca_id_lan_ten_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {}),
                              {"configurable": {"thread_id": "p6"}})
    assert "__interrupt__" not in res
    assert "args" not in rec


@pytest.mark.asyncio
async def test_post_invoice_write_tat_thi_tu_choi_ngay(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    rec = {}
    graph = _graph(iw.make_post_invoice_node([_fake_tool("post_invoice", rec)]))
    res = await graph.ainvoke(_state("post_invoice", {"invoice_id": 105}),
                              {"configurable": {"thread_id": "p7"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_invoice_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.invoice_write'`

- [ ] **Step 3: Tạo `backend/src/agents/invoice_write.py`**

```python
# backend/src/agents/invoice_write.py
"""Coordinator cho hai thao tác đụng tiền: post_invoice (phát hành hóa đơn
nháp) và register_payment (ghi nhận thanh toán).

VÌ SAO CẦN COORDINATOR RIÊNG (spec 2026-08-06 §1.1): nhánh fallback chung của
erp_write_planner chỉ hiện "(post_invoice: partner_name=Acme)" — người dùng
xác nhận mà KHÔNG biết hóa đơn nào, bao nhiêu tiền. Đo thật trên Odoo
2026-08-06: 5 hóa đơn nháp đều của cùng "Acme Corporation", 4 cái trùng y hệt
số tiền, và hóa đơn nháp chưa có số (name=False). Lỗi mơ hồ của tool chỉ hiện
ra SAU khi người dùng đã bấm xác nhận — với thao tác đụng tiền thì đó là lỗ
hổng an toàn, không phải vấn đề thẩm mỹ.

LUÔN gọi tool bằng invoice_id đã resolve: nhánh `if invoice_id:` của tool
(mcp-servers/odoo/tools/accounting.py:29-51) bỏ qua hoàn toàn phần resolve
của chính nó, nên lúc chạy chỉ có ĐÚNG MỘT phép resolve — logic trùng không
phải hai resolver chạy đua rồi lệch nhau (spec §5.1). Đây là đường tool đã
dành sẵn: docstring gọi invoice_id là "đường nội bộ", ưu tiên hơn partner_name.
"""
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import (_by_id, _ttl_expiry, _msg, _disambig_q,
                           WRITE_DISABLED_MSG)
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX
from ..erp_query import accounting


def _finish(tool_name: str, result) -> dict:
    display, env = parse_write_result(result)
    return {**_msg(display), "pending_action": None,
            "last_write": {"tool": tool_name, **env} if env else None}


def render_invoice_summary(head: str, lines: list, totals: list) -> str:
    """Bảng tóm tắt hóa đơn, khớp khuôn render_draft của create_order.py.

    Tên hiển thị lấy từ product_id[1], KHÔNG lấy line["name"]: đo thật thấy
    trường đó chứa mô tả nhiều dòng ('[FURN_0789] Individual Workplace\\n...'),
    hiển thị nguyên sẽ vỡ bảng."""
    body = [f"  - {(l.get('product_id') or [0, '?'])[1]}"
            f" × {(l.get('quantity') or 0):g}"
            f" = {(l.get('price_subtotal') or 0):,.0f}" for l in lines]
    return "\n".join([head, *body, *totals]) + "\n" + WRITE_CONFIRM_SUFFIX


def _invoice_label(r: dict) -> str:
    """Nhãn chọn trong disambig. PHẢI có số tiền + ngày: hóa đơn nháp không
    có số nên chỉ tên đối tác thì không phân biệt được."""
    partner = (r.get("partner_id") or [0, "?"])[1]
    return (f"{r.get('name') or 'chưa có số'} — {partner}"
            f" — {(r.get('amount_total') or 0):,.0f}"
            f" — {r.get('invoice_date') or 'chưa có ngày'}")


def _pick_invoice(env: dict, label: str):
    """envelope find_*_invoices → ('ok', <row>) | ('msg', <state update>).
    Nhiều kết quả → disambig interrupt (pattern _resolve_product của
    returns_write.py)."""
    if env.get("status") != "success":
        return "msg", _msg(env.get("display") or "Lỗi tra cứu hóa đơn.")
    rows = (env.get("data") or {}).get("rows") or []
    if not rows:
        return "msg", _msg("Không tìm thấy hóa đơn phù hợp.")
    if len(rows) == 1:
        return "ok", rows[0]
    options = [{"id": r["id"], "name": _invoice_label(r)} for r in rows]
    chosen = _interrupt({"kind": "disambiguation",
                         "question": _disambig_q(label, options),
                         "options": options, "expires_at": _ttl_expiry()})
    picked = _by_id(options, chosen)
    if picked is None:
        return "msg", _msg("Đã hủy.")
    return "ok", next(r for r in rows if r["id"] == picked["id"])


def _detail_or_msg(invoice_id: int):
    """→ ('ok', (inv, lines)) | ('msg', <state update>)."""
    env = accounting.get_invoice_detail(invoice_id)
    if env.get("status") != "success":
        return "msg", _msg(env.get("display") or "Lỗi tra chi tiết hóa đơn.")
    data = env.get("data") or {}
    return "ok", (data.get("invoice") or {}, data.get("lines") or [])


def make_post_invoice_node(tools):
    by_name = {t.name: t for t in tools}

    async def post_invoice_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        invoice_id = args.get("invoice_id") or 0

        if not invoice_id:
            partner_name = str(args.get("partner_name") or "").strip()
            if not partner_name:
                return _msg("Bạn cần cho biết khách hàng (hoặc ID) của hóa đơn nháp.")
            kind, val = _pick_invoice(
                accounting.find_draft_invoices(partner_name, args.get("amount"),
                                               args.get("invoice_date")),
                "hóa đơn nháp")
            if kind == "msg":
                return val
            invoice_id = val["id"]

        kind, val = _detail_or_msg(invoice_id)
        if kind == "msg":
            return val
        inv, lines = val

        partner = (inv.get("partner_id") or [0, "?"])[1]
        head = (f"Hóa đơn nháp của {partner} — ngày "
                f"{inv.get('invoice_date') or 'chưa có'}:")
        draft = render_invoice_summary(
            head, lines, [f"  Tổng: {(inv.get('amount_total') or 0):,.0f}"])
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy phát hành hóa đơn.")

        tool = by_name.get("post_invoice")
        if tool is None:
            return _msg("Công cụ phát hành hóa đơn không khả dụng.")
        try:
            result = await tool.ainvoke({"invoice_id": invoice_id})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi phát hành hóa đơn: {e}")
        return _finish("post_invoice", result)

    return post_invoice_node
```

- [ ] **Step 4: Đăng ký vào registry**

Trong `backend/src/agents/write_registry.py`, thêm import sau dòng
`from .returns_write import ...`:

```python
from .invoice_write import make_post_invoice_node
```

Thêm dòng vào cuối dict `WRITE_COORDINATORS` (trước dấu `}`):

```python
    "post_invoice": Spec("post_invoice", lambda llm, tools: make_post_invoice_node(tools)),
```

- [ ] **Step 5: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_invoice_write.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Chạy test hồi quy toàn agents**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/ -q`
Expected: không có fail MỚI. (Ghi chú: `tests/agents/test_dau_cuoi_sop.py` có
1 test live đã fail sẵn từ trước plan này — nếu nó fail thì bỏ qua, nhưng
phải xác nhận đúng là nó chứ không phải test khác.)

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/invoice_write.py backend/tests/agents/test_invoice_write.py backend/src/agents/write_registry.py
git commit -m "feat(agents): coordinator post_invoice — tóm tắt hóa đơn trước xác nhận"
```

---

### Task 3: Coordinator `register_payment`

**Files:**
- Modify: `backend/src/agents/invoice_write.py`
- Modify: `backend/src/agents/write_registry.py`
- Test: `backend/tests/agents/test_invoice_write.py`

**Interfaces:**
- Consumes: `render_invoice_summary`, `_pick_invoice`, `_detail_or_msg`, `_finish` (Task 2);
  `accounting.find_open_invoices`, `accounting.get_invoice_detail` (Task 1).
- Produces: `make_register_payment_node(tools) -> node`;
  `Spec("register_payment", ...)` trong `WRITE_COORDINATORS` dưới khóa `"register_payment"`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_invoice_write.py`:

```python
_POSTED = {"id": 100, "name": "INV/2026/00028",
           "partner_id": [41, "Acme Corporation"], "invoice_date": "2026-08-01",
           "amount_total": 350.0, "amount_residual": 350.0,
           "move_type": "out_invoice", "state": "posted"}
_CHAIR = {"product_id": [9, "[FURN_7777] Office Chair"],
          "quantity": 2.0, "price_subtotal": 140.0}


def _opens(monkeypatch, rows):
    monkeypatch.setattr(iw.accounting, "find_open_invoices", lambda *a, **k: {
        "status": "success", "data": {"rows": rows, "count": len(rows)},
        "display": "x"})


@pytest.mark.asyncio
async def test_register_payment_hien_so_du_khong_phai_tong(monkeypatch):
    """Tool LUÔN thanh toán đủ số dư còn lại, không trả một phần — nên số
    quyết định là amount_residual. Hiển thị amount_total sẽ SAI với hóa đơn
    đã trả một phần (payment_state='partial')."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    partial = {**_POSTED, "amount_total": 350.0, "amount_residual": 210.0}
    _detail(monkeypatch, inv=partial, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(_state("register_payment", {"invoice_id": 100}),
                              {"configurable": {"thread_id": "r1"}})
    q = res["__interrupt__"][0].value["question"]
    assert "INV/2026/00028" in q
    assert "Số dư sẽ thanh toán: 210" in q
    assert "Tổng hóa đơn: 350" in q


@pytest.mark.asyncio
async def test_register_payment_xac_nhan_thi_goi_bang_invoice_id(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r2"}}
    await graph.ainvoke(_state("register_payment", {"invoice_id": 100}), cfg)
    res = await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 100}
    assert res["last_write"]["tool"] == "register_payment"


@pytest.mark.asyncio
async def test_register_payment_giu_journal_neu_co(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r3"}}
    await graph.ainvoke(
        _state("register_payment", {"invoice_id": 100, "journal": "bank"}), cfg)
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"] == {"invoice_id": 100, "journal": "bank"}


@pytest.mark.asyncio
async def test_register_payment_partner_name_mo_ho_thi_hoi_chon(monkeypatch):
    """register_payment nhận CẢ invoice_ref LẪN partner_name — đường
    partner_name mơ hồ y hệt post_invoice nên phải xử lý cùng cách."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    _opens(monkeypatch, [_POSTED, {**_POSTED, "id": 96,
                                   "name": "INV/2026/00026"}])
    _detail(monkeypatch, inv=_POSTED, lines=[_CHAIR])
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    cfg = {"configurable": {"thread_id": "r4"}}
    res = await graph.ainvoke(
        _state("register_payment", {"partner_name": "Acme"}), cfg)
    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    assert "args" not in rec


@pytest.mark.asyncio
async def test_register_payment_thieu_moi_thu_thi_hoi_lai(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(iw.make_register_payment_node(
        [_fake_tool("register_payment", rec)]))
    res = await graph.ainvoke(_state("register_payment", {}),
                              {"configurable": {"thread_id": "r5"}})
    assert "__interrupt__" not in res
    assert "args" not in rec
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_invoice_write.py -k register_payment -v`
Expected: FAIL — `AttributeError: module 'src.agents.invoice_write' has no attribute 'make_register_payment_node'`

- [ ] **Step 3: Cài đặt — thêm vào cuối `backend/src/agents/invoice_write.py`**

```python
def make_register_payment_node(tools):
    by_name = {t.name: t for t in tools}

    async def register_payment_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        invoice_id = args.get("invoice_id") or 0
        journal = str(args.get("journal") or "").strip()

        if not invoice_id:
            invoice_ref = str(args.get("invoice_ref") or "").strip()
            partner_name = str(args.get("partner_name") or "").strip()
            if not invoice_ref and not partner_name:
                return _msg("Bạn cần cho biết số hóa đơn hoặc tên khách hàng.")
            kind, val = _pick_invoice(
                accounting.find_open_invoices(invoice_ref or None,
                                              partner_name or None,
                                              args.get("amount"),
                                              args.get("invoice_date")),
                "hóa đơn")
            if kind == "msg":
                return val
            invoice_id = val["id"]

        kind, val = _detail_or_msg(invoice_id)
        if kind == "msg":
            return val
        inv, lines = val

        partner = (inv.get("partner_id") or [0, "?"])[1]
        head = (f"Thanh toán hóa đơn {inv.get('name') or 'chưa có số'}"
                f" — {partner}:")
        # amount_residual, KHÔNG phải amount_total: tool luôn thanh toán ĐỦ số
        # dư còn lại, không trả một phần — hiển thị tổng sẽ sai với hóa đơn
        # payment_state='partial'.
        totals = [f"  Tổng hóa đơn: {(inv.get('amount_total') or 0):,.0f}",
                  f"  Số dư sẽ thanh toán: {(inv.get('amount_residual') or 0):,.0f}"]
        draft = render_invoice_summary(head, lines, totals)
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy ghi nhận thanh toán.")

        tool = by_name.get("register_payment")
        if tool is None:
            return _msg("Công cụ ghi nhận thanh toán không khả dụng.")
        payload = {"invoice_id": invoice_id}
        if journal:
            payload["journal"] = journal
        try:
            result = await tool.ainvoke(payload)
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi ghi nhận thanh toán: {e}")
        return _finish("register_payment", result)

    return register_payment_node
```

- [ ] **Step 4: Đăng ký vào registry**

Trong `backend/src/agents/write_registry.py`, sửa dòng import đã thêm ở Task 2:

```python
from .invoice_write import make_post_invoice_node, make_register_payment_node
```

Thêm dòng vào cuối dict `WRITE_COORDINATORS`:

```python
    "register_payment": Spec("register_payment", lambda llm, tools: make_register_payment_node(tools)),
```

- [ ] **Step 5: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_invoice_write.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/invoice_write.py backend/tests/agents/test_invoice_write.py backend/src/agents/write_registry.py
git commit -m "feat(agents): coordinator register_payment — hiện số dư sẽ thanh toán"
```

---

### Task 4: Chuỗi tự động dừng hỏi lại ở bước đụng tiền

**Files:**
- Modify: `backend/src/agents/write_registry.py` (thêm `CONFIRM_IN_CHAIN`)
- Modify: `backend/src/agents/continuation.py:8-11` (docstring), `:38-45`, `:54-57`
- Modify: `backend/src/agents/graph.py:95-96`
- Test: `backend/tests/agents/test_auto_chain.py`

**Interfaces:**
- Consumes: `WRITE_COORDINATORS` (đã có `post_invoice`/`register_payment` từ Task 2, 3).
- Produces: `CONFIRM_IN_CHAIN: frozenset[str]` export từ `write_registry`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_auto_chain.py`:

```python
from src.agents.write_registry import CONFIRM_IN_CHAIN, WRITE_COORDINATORS
from src.agents.continuation import _route_after_continuation


def test_confirm_in_chain_la_tap_tuong_minh_chi_2_tool_dung_tien():
    """PHẢI tường minh, KHÔNG được viết thành `in COORDINATED_TOOLS`:
    convert_lead và update_vendor_pricing cũng vừa coordinated vừa là bước
    trong NEXT_STEPS — điều kiện rộng sẽ đổi luôn hành vi của chúng, ngoài
    phạm vi spec 2026-08-06 §3.3."""
    assert CONFIRM_IN_CHAIN == frozenset({"post_invoice", "register_payment"})


def test_moi_tool_trong_confirm_in_chain_deu_co_coordinator():
    """Nếu thiếu, _route_after_continuation sẽ trả về node không tồn tại và
    LangGraph ném lỗi định tuyến giữa một lượt chat thật."""
    for tool in CONFIRM_IN_CHAIN:
        assert tool in WRITE_COORDINATORS


@pytest.mark.asyncio
async def test_buoc_dung_tien_trong_chuoi_KHONG_auto_run():
    """Đảo hành vi có chủ đích (spec §4): lúc khai báo chuỗi, hóa đơn CHƯA
    tồn tại — user đồng ý với HÀNH ĐỘNG, không thể đồng ý với SỐ TIỀN."""
    lw = {"tool": "create_invoice_from_order", "ok": True, "ref": "INV/2026/00030",
          "model": "account.move", "res_id": 105, "state": "draft",
          "display": "Đã tạo hóa đơn nháp."}
    res = await _cgraph().ainvoke(_cstate(lw, ["post_invoice"]),
                                  {"configurable": {"thread_id": "c1"}})
    assert res["pending_action"]["tool"] == "post_invoice"
    assert res["confirmed"] is not True      # coordinator sẽ tự interrupt
    assert res["auto_chain"] is None         # queue đã tiêu thụ bước này


def test_route_after_continuation_tro_vao_coordinator():
    state = {"pending_action": {"tool": "post_invoice"}, "confirmed": None}
    assert _route_after_continuation(state) == WRITE_COORDINATORS["post_invoice"].node


def test_route_after_continuation_giu_nguyen_duong_executor():
    """Chống hồi quy: bước KHÔNG đụng tiền vẫn đi thẳng executor như cũ."""
    state = {"pending_action": {"tool": "confirm_sale_order"}, "confirmed": True}
    assert _route_after_continuation(state) == "erp_write_executor"
```

- [ ] **Step 2: Chạy test để chắc chắn nó fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_auto_chain.py -k "confirm_in_chain or dung_tien or route_after" -v`
Expected: FAIL — `ImportError: cannot import name 'CONFIRM_IN_CHAIN'`

- [ ] **Step 3: Thêm `CONFIRM_IN_CHAIN` vào `write_registry.py`**

Thêm ngay dưới dòng `COORDINATED_TOOLS = frozenset(WRITE_COORDINATORS)`:

```python
# Bước chuỗi PHẢI dừng hỏi lại kèm bản tóm tắt, KHÔNG auto-run (spec
# 2026-08-06 §3.3, §4).
#
# TẬP TƯỜNG MINH, KHÔNG PHẢI `in COORDINATED_TOOLS`: đối chiếu registry cho
# thấy convert_lead và update_vendor_pricing cũng VỪA là coordinated tool VỪA
# là bước trong NEXT_STEPS — dùng điều kiện rộng sẽ đổi luôn hành vi của hai
# tool đó, vượt phạm vi spec và không có tiêu chí nghiệm thu nào phủ.
CONFIRM_IN_CHAIN = frozenset({"post_invoice", "register_payment"})
```

- [ ] **Step 4: Sửa `continuation.py`**

Sửa import ở đầu file:

```python
from .write_registry import NEXT_STEPS, CONFIRM_IN_CHAIN, WRITE_COORDINATORS
```

Thay khối `if queue:` (dòng 38-45 hiện tại) bằng:

```python
        if queue and queue[0] == step.tool:
            base = {"pending_action": {"tool": step.tool, "args": step.args(lw),
                                       "summary": step.label},
                    "last_write": None, "auto_chain": queue[1:] or None}
            if step.tool in CONFIRM_IN_CHAIN:
                # Bước đụng tiền: KHÔNG auto-run. Giao cho coordinator để nó tự
                # đọc hóa đơn, hiện bảng dòng hàng + số tiền, rồi mới interrupt.
                return {**base, "confirmed": None}
            # Bước kế đã được user duyệt trước ở confirm đầu chuỗi (chain_note)
            # → tự chạy, KHÔNG interrupt.
            return {**base, "confirmed": True}
```

Thay `_route_after_continuation` (dòng 54-57) bằng:

```python
def _route_after_continuation(state: ERPAgentState) -> str:
    action = state.get("pending_action") or {}
    tool = action.get("tool")
    if tool in CONFIRM_IN_CHAIN:
        # Coordinator tự lo cổng xác nhận của nó (giống _route_after_write_planner).
        return WRITE_COORDINATORS[tool].node
    if action and state.get("confirmed"):
        return "erp_write_executor"
    return END
```

Sửa docstring module (dòng 8-11) — thay câu cuối
"*Khi auto_chain còn bước khớp NEXT_STEPS, bước kế tự chạy không interrupt —
user đã tự khai báo cả chuỗi trong 1 câu, mức đồng ý mạnh hơn 1 gợi ý bình
thường.*" bằng:

```
Khi auto_chain còn bước khớp NEXT_STEPS, bước kế tự chạy không interrupt —
user đã tự khai báo cả chuỗi trong 1 câu, mức đồng ý mạnh hơn 1 gợi ý bình
thường. NGOẠI LỆ: bước thuộc CONFIRM_IN_CHAIN (post_invoice,
register_payment) vẫn dừng hỏi lại. Lý lẽ trên có một biên: lúc khai báo
chuỗi, hóa đơn CHƯA tồn tại, nên user đồng ý với HÀNH ĐỘNG chứ không thể
đồng ý với SỐ TIỀN. Những bước đó được chuyển vào coordinator riêng để hiện
bảng dòng hàng trước cổng xác nhận (spec 2026-08-06).
```

- [ ] **Step 5: Mở rộng target map trong `graph.py`**

Sửa import:

```python
from .write_registry import WRITE_COORDINATORS, COORDINATED_TOOLS, CONFIRM_IN_CHAIN
```

Thay hai dòng `g.add_conditional_edges("write_continuation", ...)` (dòng 95-96) bằng:

```python
    cont_targets = {"erp_write_executor": "erp_write_executor", END: END}
    cont_targets.update({WRITE_COORDINATORS[t].node: WRITE_COORDINATORS[t].node
                         for t in CONFIRM_IN_CHAIN})
    g.add_conditional_edges("write_continuation", _route_after_continuation,
                            cont_targets)
```

- [ ] **Step 6: Chạy test để chắc chắn nó pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_auto_chain.py -v`
Expected: PASS toàn bộ — **kể cả các test cũ**
(`test_auto_proceed_no_interrupt`, `test_auto_proceed_keeps_rest_of_queue`)
vì chúng dùng `confirm_sale_order`/`deliver_order`, không thuộc `CONFIRM_IN_CHAIN`.

- [ ] **Step 7: Chạy toàn bộ test suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: không có fail MỚI so với baseline trước plan.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/write_registry.py backend/src/agents/continuation.py backend/src/agents/graph.py backend/tests/agents/test_auto_chain.py
git commit -m "feat(agents): chuỗi tự động dừng hỏi lại ở bước đụng tiền"
```

---

### Task 5: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi kết quả vào
`docs/superpowers/plans/2026-08-06-invoice-confirm-summary-report.md`.

**Bối cảnh bắt buộc đọc trước:** unit test ở Task 1-4 dựng state bằng tay,
**không đủ**. Đúng hình dạng lỗi của `2026-08-05-write-confirmation-ux-fix`:
6 vòng review sạch trên một cơ chế thực tế không chạy được trong production,
vì mọi test đều dựng state thay vì đi qua entry point thật.

Cách gửi request phải khớp client thật: **resend toàn bộ lịch sử hội thoại
mỗi lượt, KHÔNG dùng `session_id`** (dùng `session_id` sẽ đi vào nhánh
single-message wipe của `_invoke_fresh` và không tái hiện đúng).

- [ ] **Step 1: Khởi động hệ thống thật**

```powershell
.\start-dev.ps1
```
Bật write kill-switch: Odoo → Settings → Technical → System Parameters →
`erp_ai.write_actions_enabled` = `True`.

- [ ] **Step 2: Tiêu chí 1 — gọi trực tiếp, có mơ hồ thật**

Gửi: `"Phát hành hóa đơn nháp của Acme Corporation"`

ĐẠT khi: trả về **danh sách nhiều bản nháp để chọn** (dữ liệu thật có 5 bản),
và **chưa phát hành gì**. Sau khi chọn một mục, phải hiện **bảng dòng hàng +
tổng tiền** rồi mới hỏi xác nhận.

- [ ] **Step 3: Tiêu chí 2 — chuỗi có bước đụng tiền phải DỪNG**

Gửi một câu khai báo chuỗi tới `post_invoice`, ví dụ:
`"Tạo hóa đơn cho đơn S00165 rồi phát hành luôn"`

ĐẠT khi: sau khi tạo hóa đơn nháp, hệ thống **dừng lại hỏi xác nhận kèm bảng
tóm tắt**, KHÔNG tự phát hành.

- [ ] **Step 4: Tiêu chí 3 — resume giữa chuỗi phải chạy nốt**

Từ Step 3, trả lời `"có"`.

ĐẠT khi: `post_invoice` chạy thật, và nếu `auto_chain` còn
`register_payment` thì bước đó **tiếp tục** và cũng dừng hỏi lại kèm
`amount_residual`. Đây là hạng mục rủi ro cao nhất (spec §5.3): interrupt
**giữa** chuỗi là tình huống chưa từng tồn tại trước plan này.

- [ ] **Step 5: Tiêu chí 4 — chống hồi quy chaining nói chung**

Gửi: `"Tạo báo giá 2 Office Chair cho Acme rồi xác nhận luôn"`

ĐẠT khi: chuỗi `create_quotation → confirm_sale_order` **vẫn auto-run, không
interrupt ở bước xác nhận đơn** — y hệt trước thay đổi. Đây là chốt chặn
chứng minh ta thu hẹp đúng chỗ biên chứ không phá cơ chế chuỗi.

- [ ] **Step 6: Viết report và commit**

Ghi rõ từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (nội dung phản hồi, mã
hóa đơn thật được tạo). **Nếu bất kỳ tiêu chí nào KHÔNG ĐẠT, ghi nguyên
trạng, không tô hồng.**

```bash
git add docs/superpowers/plans/2026-08-06-invoice-confirm-summary-report.md
git commit -m "docs(invoice-summary): kết quả live-verify 4 tiêu chí"
```
