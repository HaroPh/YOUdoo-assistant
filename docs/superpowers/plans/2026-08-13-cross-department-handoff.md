# Bàn giao chéo bộ phận — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biến lời từ chối chéo bộ phận thành một bàn giao có ghi nhận — activity gắn trên đúng chứng từ, giao cho bộ phận có thẩm quyền — và cho bên nhận một đường để đọc được việc đó.

**Architecture:** Một module thuần mới (`agents/handoff.py`) quyết định "có dựng được bàn giao không" và dựng plan; hai chỗ guard vai trong `nodes.py` thay `plan` bằng plan đó. Vì `log_activity` LÀ coordinated tool, toàn bộ máy móc sẵn có (tra chứng từ, kiểm loại, tra người nhận, cổng xác nhận) chạy y nguyên — không thêm cơ chế nào. Nửa đọc là một tool `erp_query` mới lọc **tường minh** theo vai.

**Tech Stack:** Python 3.11, LangGraph, Odoo XML-RPC qua `erp_query.gateway`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-cross-department-handoff-design.md`

## Global Constraints

- **Định danh trong `backend/src` viết bằng TIẾNG ANH.** Chú thích và chuỗi hiển thị cho người dùng viết tiếng Việt. Quy ước repo đã bị vi phạm sáu đợt liên tiếp — không lặp lại.
- **`backend/tests` NGƯỢC LẠI**: tên hàm test phiên âm tiếng Việt không dấu (`test_dung_duoc_ban_giao_thi_thay_plan`), nhất quán 19+ file. Theo đúng quy ước đó.
- **SÀN, bất biến của cả đợt:** không nhánh nào được làm lời từ chối hôm nay biến mất hoặc xấu đi. Dựng bàn giao không được ⇒ trả **đúng** câu từ chối hiện tại và `pending_action = None`.
- **KHÔNG tự động ghi.** Bàn giao luôn đi qua cổng xác nhận sẵn có. Không đục thêm đường ghi nào.
- **`role_cfg=None` (vai admin, mọi test cũ) phải giữ NGUYÊN hành vi.** Guard vai vốn không chạy khi `role_cfg is None`.
- **LỆNH CHẠY TEST BẮT BUỘC** — luôn kèm bộ lọc marker:

  ```
  cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
  ```

  `pytest.ini` khai marker `live`/`integration` nhưng **KHÔNG** có `addopts` loại trừ, còn `tests/conftest.py` tự `load_dotenv()` một `.env` THẬT ⇒ `pytest` trần sẽ **gọi API LLM thật và chạm Postgres**. Sự cố đã xảy ra thật ngày 2026-08-13.
  Chạy full suite làm bẩn 2 fixture RAG git-tracked — `git checkout -- backend/tests/rag/fixtures/` sau đó, và đừng để chúng lọt vào commit.
  Mốc hiện tại: **1349 passed, 4 skipped, 46 deselected**.

---

## Dữ kiện đã ĐO, dùng luôn — đừng đo lại

| dữ kiện | giá trị |
|---|---|
| `ai-readonly` đọc `mail.activity` | ĐƯỢC — 31 bản ghi, thấy cả của tài khoản khác |
| lọc `[["user_id.login", "=", login]]` qua `gateway.search_read` | CHẠY — `res.users` bị denylist nhưng đường chấm không bị chặn |
| trường `mail.activity` có sẵn | `id, summary, user_id, res_model, res_id, res_name, date_deadline, activity_type_id` |
| uid các tài khoản | `ai-readonly`=7, `ai-admin`=8, `ai-warehouse`=9, `ai-accounting`=10 |
| `DEPT_OF` | **20** tool — Kho 10, Kế toán 6, Bán hàng 2, Mua hàng 2 |
| `RoleCfg.label` | admin=`"Quản trị"`, warehouse=`"Kho"`, accounting=`"Kế toán"` |
| `log_activity` ∈ `WRITE_COORDINATORS` | ĐÚNG — planner trả sớm, coordinator tự lo cổng xác nhận |

**Hệ quả quan trọng:** `"Bán hàng"` và `"Mua hàng"` **không có vai nào** ⇒ 4/20 tool luôn rơi về sàn. Đó là hành vi đúng theo spec §6, không phải thiếu sót.

## File Structure

| file | trách nhiệm |
|---|---|
| `backend/src/agents/handoff.py` | **MỚI** — thuần, không I/O: bảng tool→chứng từ, tra nhãn→vai, dựng plan bàn giao |
| `backend/src/agents/nodes.py` | hai chỗ guard vai thay `plan` bằng plan bàn giao |
| `backend/src/erp_query/crm.py` | truy vấn `mail.activity` theo login |
| `backend/src/erp_query/tools.py` | tool `list_my_activities`; `build_erp_query_tools(role_cfg=None)` |
| `backend/src/agents/graph.py` | chuyển `role_cfg` xuống đường đọc |
| `backend/src/agents/prompts.py` | thêm `list_my_activities` vào `SYSTEM_PROMPT` |

---

## Task 1: Module `handoff.py` — thuần, kèm lưới đỡ trôi ba chiều

**Files:**
- Create: `backend/src/agents/handoff.py`
- Test: `backend/tests/agents/test_handoff.py` (mới)

**Interfaces:**
- Consumes: `roles.DEPT_OF`, `roles.load_profile`, `roles.RoleCfg`
- Produces:
  - `HANDOFF_DOC_OF: dict[str, tuple[str, str]]` — tool → (tên tham số, `res_model`)
  - `NO_DOCUMENT_TOOLS: frozenset[str]`
  - `role_name_for_label(label: str) -> str | None`
  - `build_handoff(role_cfg, tool: str, args: dict, summary: str | None) -> dict | None`

- [ ] **Bước 1: Viết test cho bảng + lưới đỡ — phải đỏ trước**

Tạo `backend/tests/agents/test_handoff.py`:

```python
import pytest

from src.agents.handoff import (HANDOFF_DOC_OF, NO_DOCUMENT_TOOLS,
                                build_handoff, role_name_for_label)
from src.agents.roles import DEPT_OF, load_profile


def test_moi_khoa_trong_bang_deu_co_trong_DEPT_OF():
    """Chiều 1 của lưới đỡ trôi."""
    la = set(HANDOFF_DOC_OF) - set(DEPT_OF)
    assert not la, f"bảng có tool không thuộc DEPT_OF: {sorted(la)}"


def test_moi_tool_trong_DEPT_OF_deu_duoc_xep_loai():
    """Chiều 2: thêm tool vào DEPT_OF mà quên xếp loại ở đây thì ĐỎ."""
    chua_xep = set(DEPT_OF) - set(HANDOFF_DOC_OF) - set(NO_DOCUMENT_TOOLS)
    assert not chua_xep, (
        f"tool trong DEPT_OF chưa xếp loại: {sorted(chua_xep)} — thêm vào "
        "HANDOFF_DOC_OF (có chứng từ) hoặc NO_DOCUMENT_TOOLS (không có)")


def test_danh_sach_ngoai_le_khong_co_muc_chet():
    """Chiều 3 — bài học GATHER_CASES: lần đó lưới đỡ được dựng nhưng chính
    danh sách ngoại lệ lại không ai canh, và lỗi tái xuất cao hơn một tầng."""
    chet = set(NO_DOCUMENT_TOOLS) - set(DEPT_OF)
    assert not chet, f"NO_DOCUMENT_TOOLS có mục không còn trong DEPT_OF: {sorted(chet)}"


def test_hai_tap_khong_giao_nhau():
    trung = set(HANDOFF_DOC_OF) & set(NO_DOCUMENT_TOOLS)
    assert not trung, f"tool vừa có vừa không có chứng từ: {sorted(trung)}"


def test_tra_nhan_bo_phan_ve_ten_vai():
    assert role_name_for_label("Kế toán") == "accounting"
    assert role_name_for_label("Kho") == "warehouse"


def test_bo_phan_khong_co_vai_thi_tra_None():
    """Bán hàng / Mua hàng có trong DEPT_OF nhưng KHÔNG có vai nào — 4/20
    tool luôn rơi về sàn. Hành vi đúng, không phải thiếu sót."""
    assert role_name_for_label("Bán hàng") is None
    assert role_name_for_label("Mua hàng") is None
    assert role_name_for_label("khác") is None
```

- [ ] **Bước 2: Viết test cho `build_handoff` — phải đỏ trước**

Thêm vào cùng file:

```python
def _vai(ten):
    return load_profile("small-business")[ten]


def test_dung_duoc_ban_giao_cho_tool_co_chung_tu():
    got = build_handoff(_vai("warehouse"), "create_invoice_from_order",
                        {"order_ref": "S00012"}, "Phát hành hóa đơn cho đơn S00012")

    assert got["tool"] == "log_activity"
    assert got["args"]["res_model"] == "sale.order"
    assert got["args"]["ref"] == "S00012"
    assert got["args"]["assignee"] == "ai-accounting"
    assert got["args"]["activity_type"] == "To-Do"
    # Nguồn gốc phải nằm trong summary — bên nhận cần biết AI đề nghị.
    assert "Kho" in got["args"]["summary"]
    assert "Phát hành hóa đơn" in got["args"]["summary"]


def test_khong_dung_duoc_khi_tool_khong_co_chung_tu():
    assert build_handoff(_vai("warehouse"), "post_invoice",
                         {"partner_name": "Acme"}, "Phát hành hóa đơn") is None


def test_khong_dung_duoc_khi_thieu_gia_tri_tham_so():
    """Tool CÓ trong bảng nhưng args rỗng — vẫn phải rơi về sàn."""
    assert build_handoff(_vai("warehouse"), "create_invoice_from_order",
                         {}, "x") is None


def test_khong_dung_duoc_khi_bo_phan_khong_co_vai():
    """create_quotation thuộc 'Bán hàng' — không vai nào nhận."""
    assert build_handoff(_vai("accounting"), "create_quotation",
                         {"partner_name": "Acme"}, "Tạo báo giá") is None


def test_khong_dung_duoc_voi_ten_tool_bia():
    """LLM bịa tên tool ('other') → dept_of trả 'khác' → sàn."""
    assert build_handoff(_vai("warehouse"), "other", {}, "x") is None


def test_khong_bao_gio_ban_giao_chinh_log_activity():
    """log_activity LÀ kênh bàn giao, không bao giờ là đích của nó."""
    assert build_handoff(_vai("warehouse"), "log_activity",
                         {"ref": "S00012"}, "x") is None
```

- [ ] **Bước 3: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_handoff.py -m "not integration and not live" -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.handoff'`.

- [ ] **Bước 4: Viết `handoff.py`**

Tạo `backend/src/agents/handoff.py`:

```python
# backend/src/agents/handoff.py
"""Dựng một BÀN GIAO từ một thao tác ghi bị guard vai từ chối.

Thuần, KHÔNG I/O: chỉ quyết định "có dựng được không" và dựng plan. Việc tra
chứng từ thật trong Odoo, kiểm loại activity, tra người nhận và cổng xác nhận
đều do coordinator `log_activity` (agents/crm_write.py) lo — vì log_activity
NẰM TRONG WRITE_COORDINATORS, planner trả sớm và coordinator chạy tiếp.

SÀN (spec §3.3): trả None ở MỌI trường hợp không chắc. Caller rơi về đúng câu
từ chối như trước. Bàn giao là nâng cấp ở nơi làm được, không bao giờ làm lời
từ chối tệ đi.
"""
from .roles import DEPT_OF, load_profile

# tool → (tên tham số mang mã chứng từ, res_model của chứng từ đó)
#
# Suy từ chữ ký thật trong WRITE_PLANNER_PROMPT (prompts.py). Bảng khai tay sẽ
# trôi — test_handoff.py canh ba chiều: mọi khoá thuộc DEPT_OF, mọi tool trong
# DEPT_OF đều được xếp loại, và NO_DOCUMENT_TOOLS không có mục chết.
HANDOFF_DOC_OF: dict[str, tuple[str, str]] = {
    "confirm_sale_order":        ("order_ref",   "sale.order"),
    "deliver_order":             ("order_ref",   "sale.order"),
    "create_invoice_from_order": ("order_ref",   "sale.order"),
    "return_order":              ("order_ref",   "sale.order"),
    "confirm_purchase_order":    ("order_ref",   "purchase.order"),
    "receive_order":             ("order_ref",   "purchase.order"),
    "create_bill_from_po":       ("order_ref",   "purchase.order"),
    "create_credit_memo":        ("invoice_ref", "account.move"),
    "send_invoice_email":        ("invoice_ref", "account.move"),
    # register_payment: invoice_ref là TUỲ CHỌN (tool cũng nhận partner_name).
    # Xếp vào đây có chủ đích: có invoice_ref thì bàn giao được, không có thì
    # build_handoff trả None vì ref rỗng ⇒ rơi về sàn. Không cần nhánh riêng.
    "register_payment":          ("invoice_ref", "account.move"),
    "validate_picking":          ("picking_ref", "stock.picking"),
    "send_delivery_email":       ("picking_ref", "stock.picking"),
}

# Tool KHÔNG trỏ vào một bản ghi có sẵn: chúng TẠO MỚI hoặc thao tác trên
# vật/kho. Không có chứng từ để gắn activity ⇒ rơi về sàn.
#
# log_activity nằm đây vì lý do KHÁC: nó chính LÀ kênh bàn giao, nên không bao
# giờ là đích của một cuộc bàn giao. Xếp vào đây để lưới đỡ chiều 2 không đỏ.
NO_DOCUMENT_TOOLS: frozenset[str] = frozenset({
    "post_invoice", "create_quotation", "create_rfq",
    "inventory_adjustment", "internal_transfer", "scrap_product",
    "log_activity",
    # flag_order_for_review nằm đây vì HAI lý do (review Task 1 bắt được):
    #   1. KHÔNG có trong WRITE_PLANNER_PROMPT ⇒ planner không nêu được tên nó
    #      ⇒ guard vai (soi plan["tool"]) không bao giờ thấy. Chỉ edit_order.py
    #      gọi nội bộ.
    #   2. Model LƯỠNG TÍNH: edit_order.py truyền model=cfg.model, mà cfg là
    #      SALE_EDIT_CFG ("sale.order") HOẶC PURCHASE_EDIT_CFG
    #      ("purchase.order"). Một tuple tĩnh không biểu diễn nổi.
    "flag_order_for_review",
})

ACTIVITY_TYPE = "To-Do"


def role_name_for_label(label: str) -> str | None:
    """Nhãn bộ phận ("Kế toán") → tên vai ("accounting"), hoặc None.

    DEPT_OF trả NHÃN, còn login Odoo suy từ TÊN VAI, nên phải tra ngược. Trả
    None cho "Bán hàng"/"Mua hàng" (có trong DEPT_OF nhưng không vai nào nhận)
    và cho "khác" (dept_of trả khi tên tool không có trong bảng)."""
    for name, cfg in load_profile().items():
        if cfg.label == label:
            return name
    return None


def build_handoff(role_cfg, tool: str, args: dict,
                  summary: str | None) -> dict | None:
    """Plan `log_activity` đã điền sẵn, hoặc None nếu không dựng được.

    Trả None khi: tool không có chứng từ trong bảng; args thiếu giá trị; bộ
    phận đích không có vai; hoặc đích trùng chính vai đang gọi."""
    target = HANDOFF_DOC_OF.get(tool)
    if target is None:
        return None
    arg_name, res_model = target

    ref = str((args or {}).get(arg_name) or "").strip()
    if not ref:
        return None

    role_name = role_name_for_label(DEPT_OF.get(tool, ""))
    if role_name is None or role_name == role_cfg.name:
        return None

    what = (summary or "").strip() or tool
    return {
        "tool": "log_activity",
        "args": {
            "res_model": res_model,
            "ref": ref,
            "activity_type": ACTIVITY_TYPE,
            # Nguồn gốc nằm ngay trong summary: bên nhận đọc activity phải
            # biết AI đề nghị và vì sao, không phải đi hỏi lại.
            "summary": f"{role_cfg.label} đề nghị: {what}",
            "assignee": f"ai-{role_name}",
        },
        "summary": f"Chuyển việc cho bộ phận {DEPT_OF[tool]}: {what}",
    }
```

- [ ] **Bước 5: Chạy test, xác nhận XANH**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_handoff.py -m "not integration and not live" -q`
Expected: PASS toàn bộ.

- [ ] **Bước 6: CHỨNG MINH lưới đỡ canh thật — phá có chủ đích**

Một test xanh là một tuyên bố, không phải bằng chứng. Lớp lỗi "test không đo gì" đã xuất hiện **ba lần trong một đợt** ngày 2026-08-13.

1. Xoá tạm `"scrap_product"` khỏi `NO_DOCUMENT_TOOLS`. Chạy lại.
   **Phải ĐỎ** ở `test_moi_tool_trong_DEPT_OF_deu_duoc_xep_loai`. Khôi phục.
2. Thêm tạm `"khong_ton_tai"` vào `NO_DOCUMENT_TOOLS`. Chạy lại.
   **Phải ĐỎ** ở `test_danh_sach_ngoai_le_khong_co_muc_chet`. Khôi phục.

Ghi kết quả cả hai vào report. Nếu phép nào KHÔNG đỏ, DỪNG và báo lại.

- [ ] **Bước 7: Chạy toàn bộ test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS. Số passed tăng đúng bằng số test mới.

- [ ] **Bước 8: Commit**

```bash
git add backend/src/agents/handoff.py backend/tests/agents/test_handoff.py
git commit -m "feat(agents): module handoff dựng bàn giao chéo bộ phận, kèm lưới đỡ trôi 3 chiều"
```

---

## Task 2: Guard vai thay `plan` bằng plan bàn giao

**Files:**
- Modify: `backend/src/agents/nodes.py` (hai nhánh guard vai trong `erp_write_planner`)
- Test: `backend/tests/agents/test_handoff_planner.py` (mới)

**Interfaces:**
- Consumes từ Task 1: `build_handoff(role_cfg, tool, args, summary) -> dict | None`
- Produces: không có (Task 3 độc lập)

### Vì sao chỉ cần thay `plan`

`log_activity` **nằm trong `WRITE_COORDINATORS`**. Sau hai nhánh guard, `erp_write_planner` có:

```python
if plan.get("tool") in COORDINATED_TOOLS:
    return {"pending_action": plan, "auto_chain": auto_chain}
```

Nên chỉ cần gán `plan = handoff` là toàn bộ máy móc sẵn có chạy tiếp: coordinator `log_activity` tra chứng từ, kiểm loại, tra người nhận, dựng cổng xác nhận. **Không thêm cơ chế nào.**

Phải đặt lại `chain = []` sau khi thay: `chain` được tính từ plan CŨ, giữ lại sẽ quảng cáo những bước không còn liên quan.

- [ ] **Bước 1: Viết test — phải đỏ trước**

Tạo `backend/tests/agents/test_handoff_planner.py`:

```python
import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import make_erp_write_planner_node
from src.agents.roles import load_profile


def _vai(ten):
    return load_profile("small-business")[ten]


class FakeLLM:
    """Trả đúng một plan JSON — planner chỉ parse, không cần LLM thật."""

    def __init__(self, payload):
        self._payload = payload

    async def ainvoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage
        return AIMessage(content=self._payload)


def _state(text="phát hành hóa đơn cho đơn S00012"):
    return {"messages": [HumanMessage(content=text)]}


@pytest.mark.asyncio
async def test_dung_duoc_ban_giao_thi_thay_plan(monkeypatch):
    """Vai kho xin phát hành hoá đơn (thuộc Kế toán) VÀ có mã đơn ⇒ plan bị
    thay bằng log_activity, đi tiếp qua cổng xác nhận sẵn có."""
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "create_invoice_from_order", '
                '"args": {"order_ref": "S00012"}, '
                '"summary": "Phát hành hóa đơn cho đơn S00012"}'),
        role_cfg=_vai("warehouse"))

    out = await node(_state())

    plan = out["pending_action"]
    assert plan is not None, "phải có pending_action, không phải từ chối trơn"
    assert plan["tool"] == "log_activity"
    assert plan["args"]["assignee"] == "ai-accounting"
    assert plan["args"]["ref"] == "S00012"
    assert out.get("auto_chain") is None


@pytest.mark.asyncio
async def test_khong_dung_duoc_thi_giu_nguyen_loi_tu_choi(monkeypatch):
    """SÀN: tool không có chứng từ ⇒ đúng câu từ chối cũ, pending_action None."""
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "post_invoice", "args": {"partner_name": "Acme"}, '
                '"summary": "Phát hành hóa đơn"}'),
        role_cfg=_vai("warehouse"))

    out = await node(_state("phát hành hóa đơn cho khách Acme"))

    assert out["pending_action"] is None
    noi_dung = out["messages"][0].content
    assert "không thuộc quyền hạn của bộ phận Kho" in noi_dung
    assert "Kế toán" in noi_dung


@pytest.mark.asyncio
async def test_vai_admin_khong_doi_gi(monkeypatch):
    """role_cfg=None ⇒ guard vai không chạy, hành vi y như trước."""
    monkeypatch.setattr("src.agents.write_gate.write_actions_enabled",
                        lambda: True)
    node = make_erp_write_planner_node(
        FakeLLM('{"tool": "create_invoice_from_order", '
                '"args": {"order_ref": "S00012"}, "summary": "x"}'),
        role_cfg=None)

    out = await node(_state())

    assert out["pending_action"]["tool"] == "create_invoice_from_order"
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_handoff_planner.py -m "not integration and not live" -q`
Expected: FAIL ở `test_dung_duoc_ban_giao_thi_thay_plan` — hiện `pending_action` là `None` vì guard trả về lời từ chối trơn.

Nếu test khác cũng đỏ vì lý do khác (vd `FakeLLM` không khớp cách node gọi LLM), sửa **test** cho khớp thực tế node — đừng sửa node để chiều test.

- [ ] **Bước 3: Sửa nhánh guard tool đơn**

Trong `backend/src/agents/nodes.py`, thêm vào khối import:

```python
from .handoff import build_handoff
```

Thay nhánh guard tool đơn (hiện là):

```python
        if role_cfg is not None:
            tool_name = plan.get("tool")
            if tool_name and role_cfg.state_of(tool_name) in (OTHER_DEPT, DENIED):
                return {"messages": [AIMessage(
                    content=_role_refusal_message(role_cfg, tool_name)
                )], "pending_action": None, "auto_chain": None}
```

bằng:

```python
        if role_cfg is not None:
            tool_name = plan.get("tool")
            if tool_name and role_cfg.state_of(tool_name) in (OTHER_DEPT, DENIED):
                # Bàn giao (spec 2026-08-13): thay vì để việc bốc hơi, dựng một
                # activity trên đúng chứng từ giao cho bộ phận có thẩm quyền.
                # log_activity NẰM TRONG WRITE_COORDINATORS nên chỉ cần thay
                # plan — coordinator lo tra chứng từ, kiểm loại, tra người nhận
                # và cổng xác nhận. Không thêm cơ chế nào.
                handoff = build_handoff(role_cfg, tool_name,
                                        plan.get("args") or {},
                                        plan.get("summary"))
                if handoff is None:
                    # SÀN: dựng không được thì giữ NGUYÊN hành vi cũ.
                    return {"messages": [AIMessage(
                        content=_role_refusal_message(role_cfg, tool_name)
                    )], "pending_action": None, "auto_chain": None}
                plan = handoff
```

- [ ] **Bước 4: Sửa nhánh guard chuỗi**

Thay nhánh guard chuỗi (hiện là):

```python
        if role_cfg is not None and chain:
            for step_tool, _ in chain:
                if role_cfg.state_of(step_tool) in (OTHER_DEPT, DENIED):
                    return {"messages": [AIMessage(
                        content=_role_refusal_message(role_cfg, step_tool)
                    )], "pending_action": None, "auto_chain": None}
```

bằng:

```python
        if role_cfg is not None and chain:
            for step_tool, _ in chain:
                if role_cfg.state_of(step_tool) in (OTHER_DEPT, DENIED):
                    handoff = build_handoff(role_cfg, step_tool,
                                            plan.get("args") or {},
                                            plan.get("summary"))
                    if handoff is None:
                        return {"messages": [AIMessage(
                            content=_role_refusal_message(role_cfg, step_tool)
                        )], "pending_action": None, "auto_chain": None}
                    plan = handoff
                    # chain được tính từ plan CŨ — giữ lại sẽ quảng cáo những
                    # bước không còn liên quan trong lời xác nhận.
                    chain = []
                    break
```

- [ ] **Bước 5: Chạy test, xác nhận XANH**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_handoff_planner.py -m "not integration and not live" -q`
Expected: PASS toàn bộ.

- [ ] **Bước 6: CHỨNG MINH sàn canh thật — phá có chủ đích**

Trong `handoff.build_handoff`, đổi tạm `return None` đầu tiên (nhánh `target is None`) thành trả một dict bất kỳ. Chạy `pytest tests/agents/ -m "not integration and not live" -q`.
**Phải ĐỎ** ở `test_khong_dung_duoc_thi_giu_nguyen_loi_tu_choi`. Khôi phục.

Ghi kết quả vào report. Không đỏ ⇒ DỪNG và báo lại.

- [ ] **Bước 7: Chạy toàn bộ test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS. Đặc biệt chú ý các test cũ về từ chối vai vẫn xanh — chúng chính là lưới canh SÀN.

- [ ] **Bước 8: Commit**

```bash
git add backend/src/agents/nodes.py backend/tests/agents/test_handoff_planner.py
git commit -m "feat(agents): guard vai dựng bàn giao thay vì để việc bốc hơi"
```

---

## Task 3: Nửa đọc — `list_my_activities`

**Files:**
- Modify: `backend/src/erp_query/crm.py` (thêm hàm truy vấn)
- Modify: `backend/src/erp_query/tools.py` (thêm tool, đổi chữ ký `build_erp_query_tools`)
- Modify: `backend/src/agents/graph.py:73` và `:88` (chuyển `role_cfg` xuống)
- Modify: `backend/src/agents/prompts.py` (`SYSTEM_PROMPT`)
- Test: `backend/tests/erp_query/test_my_activities.py` (mới)

**Interfaces:**
- Consumes: `erp_query.gateway.default_gateway`, `erp_query.envelope.ok/err`
- Produces: `crm.list_my_activities(login, limit=20, *, gw=None) -> envelope`

### Vì sao phải lọc TƯỜNG MINH theo vai

**Đường đọc và đường ghi chạy bằng hai tài khoản Odoo khác nhau.** Backend gọi `build_erp_query_tools()` trong tiến trình của chính nó với `ODOO_USERNAME=ai-readonly`; tool ghi đi qua tiến trình MCP riêng của vai. Nên "việc của tôi" mà lọc theo "người dùng hiện tại" sẽ trả về việc của `ai-readonly` — **sai người**.

Đã đo: `ai-readonly` đọc được `mail.activity` (31 bản ghi, thấy cả của tài khoản khác), và lọc `[["user_id.login", "=", login]]` chạy qua đúng gateway dù `res.users` nằm trong `MODEL_DENYLIST` — denylist chỉ chặn model ở cấp cao nhất, không chặn đường chấm.

- [ ] **Bước 1: Viết test — phải đỏ trước**

Tạo `backend/tests/erp_query/test_my_activities.py`:

```python
from src.erp_query import crm


class FakeGateway:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search_read(self, model, domain, fields, order=None, limit=50,
                    context=None):
        self.calls.append({"model": model, "domain": domain, "fields": fields,
                           "order": order, "limit": limit})
        return self.rows


def test_loc_theo_login_duoc_truyen_vao_khong_phai_tai_khoan_hien_tai():
    """Đường đọc chạy bằng ai-readonly còn đường ghi chạy bằng tài khoản vai —
    lọc theo 'người dùng hiện tại' sẽ trả về việc của ai-readonly, SAI NGƯỜI."""
    gw = FakeGateway([])
    crm.list_my_activities("ai-accounting", gw=gw)

    goi = gw.calls[0]
    assert goi["model"] == "mail.activity"
    assert ["user_id.login", "=", "ai-accounting"] in goi["domain"]


def test_sap_theo_han_gan_nhat_truoc():
    gw = FakeGateway([])
    crm.list_my_activities("ai-accounting", gw=gw)
    assert "date_deadline" in (gw.calls[0]["order"] or "")


def test_tra_ve_cac_truong_can_de_hien_thi():
    gw = FakeGateway([{"id": 1, "summary": "Kho đề nghị: phát hành hóa đơn",
                       "res_model": "sale.order", "res_name": "S00012",
                       "date_deadline": "2026-08-15",
                       "user_id": [10, "ai-accounting"]}])
    got = crm.list_my_activities("ai-accounting", gw=gw)

    assert got["status"] == "ok"
    assert got["data"]["rows"][0]["res_name"] == "S00012"
    assert "S00012" in got["display"]


def test_khong_co_viec_nao_thi_noi_ro():
    got = crm.list_my_activities("ai-accounting", gw=FakeGateway([]))
    assert got["status"] == "ok"
    assert got["data"]["rows"] == []
    assert "không có" in got["display"].lower()


def test_gateway_hong_thi_tra_loi_khong_vo():
    class Hong:
        def search_read(self, *a, **k):
            raise RuntimeError("Odoo sập")

    got = crm.list_my_activities("ai-accounting", gw=Hong())
    assert got["status"] == "error"
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/erp_query/test_my_activities.py -m "not integration and not live" -q`
Expected: FAIL — `AttributeError: module 'src.erp_query.crm' has no attribute 'list_my_activities'`.

- [ ] **Bước 3: Thêm hàm truy vấn vào `erp_query/crm.py`**

Thêm vào cuối `backend/src/erp_query/crm.py`:

```python
ACTIVITY_FIELDS = ["summary", "user_id", "res_model", "res_id", "res_name",
                   "date_deadline", "activity_type_id"]


def list_my_activities(login, limit=20, *, gw=None):
    """Activity đang mở giao cho `login`, hạn gần nhất trước.

    LỌC TƯỜNG MINH theo login truyền vào, KHÔNG theo "người dùng hiện tại":
    đường đọc chạy bằng ai-readonly còn đường ghi chạy bằng tài khoản của vai,
    nên "người dùng hiện tại" ở đây luôn là ai-readonly — sai người.

    Đường chấm `user_id.login` đi qua được dù res.users nằm trong
    MODEL_DENYLIST: denylist chỉ chặn model ở cấp cao nhất (gateway._check_model).

    mail.activity bản chất là việc CHƯA xong — Odoo unlink bản ghi khi đánh dấu
    hoàn tất — nên không cần điều kiện "đang mở" nào thêm."""
    login = str(login or "").strip()
    if not login:
        return ok({"rows": []}, "Không xác định được tài khoản để tra việc.")
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("mail.activity", [["user_id.login", "=", login]],
                              ACTIVITY_FIELDS, order="date_deadline asc",
                              limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra việc được giao: {e}")
    if not rows:
        return ok({"rows": []}, "Hiện không có việc nào được giao cho bạn.")
    dong = [f"- {r.get('res_name') or r.get('res_model')}: "
            f"{r.get('summary') or '(không có mô tả)'} "
            f"(hạn {r.get('date_deadline') or 'chưa đặt'})" for r in rows]
    return ok({"rows": rows},
              f"{len(rows)} việc đang được giao cho bạn:\n" + "\n".join(dong))
```

- [ ] **Bước 4: Chạy test, xác nhận XANH**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/erp_query/test_my_activities.py -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Bước 5: Thêm tool vào `erp_query/tools.py`**

Đổi chữ ký `build_erp_query_tools` và thêm tool. Tìm dòng:

```python
def build_erp_query_tools() -> list:
```

đổi thành:

```python
def build_erp_query_tools(role_cfg=None) -> list:
```

Rồi thêm tool này vào TRONG hàm, cạnh các tool CRM khác:

```python
    @tool
    def list_my_activities(limit: int = 20) -> str:
        """Việc (activity) đang được giao cho bộ phận của bạn, hạn gần nhất trước.

        Dùng khi người dùng hỏi kiểu "có việc gì chuyển cho tôi không?",
        "việc của tôi", "tôi cần làm gì".
        """
        if role_cfg is None:
            return _json(crm.list_my_activities("", limit=limit))
        return _json(crm.list_my_activities(f"ai-{role_cfg.name}", limit=limit))
```

Vai admin (`role_cfg=None`, và mọi caller cũ) nhận envelope "không xác định được tài khoản" — không vỡ, và không lộ việc của vai khác.

- [ ] **Bước 6: Chuyển `role_cfg` xuống đường đọc trong `graph.py`**

Trong `backend/src/agents/graph.py`, đổi hai chỗ gọi:

```python
    g.add_node("erp_read", make_erp_read_node(
        llms["read"], build_erp_query_tools(role_cfg)))
```

và

```python
    g.add_node("gather_erp", make_gather_erp_node(
        llms["fusion"], build_erp_query_tools(role_cfg)))
```

`build_graph` đã nhận `role_cfg` sẵn — chỉ chưa chuyển xuống đường đọc.

- [ ] **Bước 7: Thêm tool vào `SYSTEM_PROMPT`**

Trong `backend/src/agents/prompts.py`, trong `SYSTEM_PROMPT`, ngay sau dòng `- CRM: list_crm_leads.` thêm:

```
- Việc được giao: list_my_activities (dùng khi user hỏi "có việc gì chuyển cho tôi không", "việc của tôi").
```

Không khai tool mà chỉ thêm hàm thì LLM không bao giờ gọi tới — đúng lớp lỗi "danh sách khai báo bỏ sót một nhánh" đã dính năm sáu lần.

- [ ] **Bước 8: Chạy toàn bộ test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS. `build_erp_query_tools()` có tham số mặc định nên mọi chỗ gọi cũ không đổi.

- [ ] **Bước 9: Commit**

```bash
git add backend/src/erp_query/crm.py backend/src/erp_query/tools.py backend/src/agents/graph.py backend/src/agents/prompts.py backend/tests/erp_query/test_my_activities.py
git commit -m "feat(erp-query): list_my_activities — bên nhận đọc được việc bàn giao"
```

---

## Task 4: Chống đề xuất trùng

**Files:**
- Modify: `backend/src/agents/handoff.py` (nhận danh sách activity đang mở)
- Modify: `backend/src/agents/nodes.py` (tra trước khi dựng)
- Test: `backend/tests/agents/test_handoff.py` (bổ sung)

**Interfaces:**
- Consumes từ Task 1: `build_handoff`; từ Task 3: `crm.list_my_activities`
- Produces: `existing_handoff(rows, res_model, ref) -> dict | None`

ADR-012 cảnh báo: *"mỗi lần bị chặn đều tạo activity ⇒ kế toán ngập"*. Hỏi lại ba lần thì kế toán nhận ba việc giống nhau.

- [ ] **Bước 1: Viết test — phải đỏ trước**

Thêm vào `backend/tests/agents/test_handoff.py`:

```python
from src.agents.handoff import existing_handoff


def test_tim_thay_viec_dang_mo_tren_cung_ban_ghi():
    rows = [{"res_model": "sale.order", "res_name": "S00012",
             "summary": "Kho đề nghị: phát hành hóa đơn",
             "date_deadline": "2026-08-15"}]
    got = existing_handoff(rows, "sale.order", "S00012")
    assert got is not None
    assert got["date_deadline"] == "2026-08-15"


def test_khac_ban_ghi_thi_khong_tinh_la_trung():
    rows = [{"res_model": "sale.order", "res_name": "S00099", "summary": "x"}]
    assert existing_handoff(rows, "sale.order", "S00012") is None


def test_khac_model_thi_khong_tinh_la_trung():
    """Cùng mã nhưng khác model — vd S00012 không phải picking."""
    rows = [{"res_model": "stock.picking", "res_name": "S00012", "summary": "x"}]
    assert existing_handoff(rows, "sale.order", "S00012") is None


def test_danh_sach_rong_thi_khong_trung():
    assert existing_handoff([], "sale.order", "S00012") is None
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_handoff.py -m "not integration and not live" -q`
Expected: FAIL — `ImportError: cannot import name 'existing_handoff'`.

- [ ] **Bước 3: Thêm `existing_handoff` vào `handoff.py`**

```python
def existing_handoff(rows, res_model: str, ref: str) -> dict | None:
    """Activity đang mở trên ĐÚNG bản ghi này, hoặc None.

    Khớp theo CẢ res_model lẫn res_name: mã đơn có thể trùng nhau giữa các
    model, khớp mỗi mã sẽ báo trùng nhầm."""
    for r in rows or []:
        if (r.get("res_model") == res_model
                and str(r.get("res_name") or "") == str(ref)):
            return r
    return None
```

- [ ] **Bước 4: Nối vào `nodes.py`**

Trong `backend/src/agents/nodes.py`, thêm import:

```python
from .handoff import build_handoff, existing_handoff
```

Ngay SAU khi `handoff` được dựng thành công (cả hai nhánh guard), chèn:

```python
                # Chống spam (ADR-012 §5): hỏi lại ba lần thì bộ phận kia nhận
                # ba việc giống nhau. Tra trước khi ĐỀ XUẤT, không phải trước
                # khi ghi — đề xuất trùng đã là phiền rồi.
                from ..erp_query import crm as _crm
                da_co = None
                try:
                    env = _crm.list_my_activities(handoff["args"]["assignee"])
                    da_co = existing_handoff((env.get("data") or {}).get("rows"),
                                             handoff["args"]["res_model"],
                                             handoff["args"]["ref"])
                except Exception:       # noqa: BLE001
                    # Tra hỏng KHÔNG được chặn bàn giao — cùng lắm là một việc
                    # trùng, còn hơn mất hẳn đường bàn giao.
                    logger.warning("không tra được activity trùng", exc_info=True)
                if da_co is not None:
                    han = da_co.get("date_deadline") or "chưa đặt"
                    return {"messages": [AIMessage(
                        content=(f"Việc này đã được chuyển cho bộ phận "
                                 f"{DEPT_OF.get(tool_name, 'khác')} rồi "
                                 f"(hạn {han}), chưa cần chuyển lại.")
                    )], "pending_action": None, "auto_chain": None}
```

Ở nhánh guard chuỗi, dùng `step_tool` thay cho `tool_name`.

Thêm `DEPT_OF` vào khối import từ `.roles` ở đầu `nodes.py`.

- [ ] **Bước 5: Chạy toàn bộ test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Bước 6: CHỨNG MINH khớp model canh thật**

Trong `existing_handoff`, bỏ tạm vế `r.get("res_model") == res_model`. Chạy `pytest tests/agents/test_handoff.py -m "not integration and not live" -q`.
**Phải ĐỎ** ở `test_khac_model_thi_khong_tinh_la_trung`. Khôi phục. Ghi vào report.

- [ ] **Bước 7: Commit**

```bash
git add backend/src/agents/handoff.py backend/src/agents/nodes.py backend/tests/agents/test_handoff.py
git commit -m "feat(agents): không đề xuất bàn giao trùng trên cùng chứng từ"
```

---

## Nghiệm thu sống — CONTROLLER làm, KHÔNG giao subagent

Subagent **không được** khởi động/dừng tiến trình, container, hay chạm Odoo. Phần này controller tự làm sau khi Task 4 xanh, **TRƯỚC khi merge**, trên worktree của nhánh, stack cũ dừng hẳn trước.

| # | vai | câu | kỳ vọng |
|---|---|---|---|
| 1 | kho | *"phát hành hoá đơn cho đơn S00012"* | từ chối + đề xuất chuyển Kế toán, có cổng xác nhận |
| 2 | kho | xác nhận #1 | activity tạo trên `sale.order` S00012, giao `ai-accounting` |
| 3 | **kế toán** | *"có việc gì chuyển cho tôi không?"* | **thấy đúng việc ở #2** |
| 4 | kho | lặp lại #1 | báo đã có việc đang mở, KHÔNG tạo trùng |
| 5 | kho | *"điều chỉnh tồn kho Bàn gỗ về 50"* (thuộc quyền) | chạy bình thường — đối chứng âm |
| 6 | kế toán | *"tạo báo giá cho khách Acme"* (chéo bộ phận, KHÔNG có chứng từ) | rơi về câu từ chối hôm nay |

**#3 là phép đo quyết định** — nó là thứ duy nhất chứng minh bàn giao không phải một danh sách việc không ai đọc được.

**Một chỗ LỆCH với spec §6, có chủ đích:** spec ghi *"tra chứng từ trong Odoo
hỏng → câu từ chối như hôm nay"*. Thiết kế thật KHÔNG làm vậy: `build_handoff`
thuần, không chạm Odoo, nên lỗi tra chứng từ xảy ra **sau** đó, bên trong
coordinator `log_activity` — và coordinator đã có câu lỗi sạch riêng từ đợt
`log_activity` (*"Không đọc được dữ liệu '<model>'…"*). Người dùng nhận một câu
rõ ràng, chỉ không phải câu từ chối vai. Chấp nhận được, và tốt hơn: câu của
coordinator nói đúng chuyện gì hỏng. Ghi lại để reviewer không báo là sai spec.

**Rủi ro đã biết cần kiểm ở #1:** plan bàn giao đi qua coordinator `log_activity`, nên câu xác nhận do coordinator dựng. Người dùng có thể **không thấy rõ mình vừa bị từ chối** — chỉ thấy một đề nghị tạo activity. Nếu #1 đọc lên khó hiểu, đó là việc của fix wave: đưa lý do từ chối vào `plan["summary"]` (trường này coordinator có hiển thị).

**Dọn sau khi đo:** xoá các `mail.activity` sinh ra trong lúc nghiệm thu (ghi lại id trước khi xoá).

**Không được thụt:** bộ test đầy đủ xanh — mốc hiện tại 1349 passed, 4 skipped, 46 deselected.
