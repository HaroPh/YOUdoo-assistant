# Tổng quát hoá `log_activity` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gỡ ba tầng bó buộc của `log_activity` (chỉ `crm.lead`, chỉ `Call`/`Meeting`, người nhận luôn là chính nó) để activity xuất hiện từ việc dùng thật thay vì phải bơm vào.

**Architecture:** Tool MCP nhận `res_model` + `res_id` đã giải sẵn (giữ phân tầng chuẩn của dự án — coordinator giải tham chiếu của con người, tool nhận id); loại hoạt động được **suy ra** từ `mail.activity.type.res_model` thay vì hardcode; coordinator có bảng giải tham chiếu theo model, giữ nguyên `_resolve_lead` cho CRM. Một nhóm quyền Odoo hẹp mới cấp `ir.model` read cho ba tài khoản ghi.

**Tech Stack:** Python 3.11, FastMCP, Odoo 19 XML-RPC, LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-08-12-log-activity-generalisation-design.md`

## Global Constraints

- **Ngôn ngữ:** comment và chuỗi hiển thị bằng tiếng Việt. **Định danh trong MÃ NGUỒN (`backend/src`, `mcp-servers`) bằng tiếng Anh, không ngoại lệ** — bốn task ở các đợt trước đã phải mở vòng sửa vì điều này. Trong `backend/tests` thì giữ quy ước phiên âm tiếng Việt sẵn có, không đổi tên gì.
- **Không hồi quy:** `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"` phải giữ **1309 passed, 4 skipped, 46 deselected** cộng các test mới. Đây là chuẩn đã đo trên `main`.
- **ĐỢT NÀY CỐ Ý ĐỔI `allowed_tools()`** — ngược hẳn ràng buộc cứng của đợt trước. Thêm `log_activity` vào `own` của hai vai nghĩa là `scripts/odoo_setup_ai_accounts.py` sinh ra bộ nhóm quyền Odoo khác trước. Đây là thay đổi CÓ CHỦ ĐÍCH, không phải hồi quy.
- **Không hardcode danh sách loại hoạt động.** Hợp lệ hay không do `mail.activity.type.res_model` quyết định (rỗng = mọi model). Đổi hardcode 2 giá trị thành hardcode 5 là lặp lại đúng hạng lỗi hai đợt vừa rồi đi sửa.
- **Giữ nguyên `_resolve_lead`** cho `crm.lead`: nó có tìm mờ, bỏ kính ngữ và hỏi-lại-khi-trùng. Thay nó bằng tra `name =` chính xác là gỡ mất tính năng đang chạy.
- Không có giá trị mật khẩu thật trong file được git theo dõi; `AI_ACCOUNT_PASSWORD` giữ nguyên là env bắt buộc không mặc định.
- `backend/tests/jobs/test_eval_latency.py::test_timed_returns_result_and_positive_latency` **flaky sẵn có** (assert theo ngưỡng thời gian). Nếu đỏ, chạy lại riêng để xác nhận rồi nói rõ — KHÔNG "sửa" nó.
- Chạy full suite có thể làm bẩn `backend/tests/rag/fixtures/*` — lỗi sẵn có, **để nguyên, không commit**.
- **Subagent KHÔNG được khởi động/dừng/khởi động lại tiến trình hay container, KHÔNG nối Odoo, KHÔNG chạy `scripts/odoo_setup_ai_accounts.py`.** Toàn bộ việc chạm hạ tầng do controller làm (§ Nghiệm thu sống cuối plan).

---

### Task 1: Tool MCP — tổng quát theo model, loại, người nhận

**Files:**
- Modify: `mcp-servers/odoo/tools/crm.py:109-153` (`log_activity`)
- Test: `backend/tests/mcp/test_log_activity_tool.py` (tạo mới)

**Interfaces:**
- Consumes: `odoo()` từ `odoo_call`, `envelope()`/`today_iso()` từ `helpers`, `get_uid()` (đang dùng sẵn trong file)
- Produces:
  - `log_activity(res_model: str, res_id: int, activity_type: str, summary: str, date_deadline: str = "", assignee: str = "") -> str`
  - Task 2 (coordinator) gọi tool này với `res_model`/`res_id` đã giải sẵn.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_log_activity_tool.py`:

```python
"""log_activity tổng quát theo model / loại / người nhận.

Ba giới hạn cũ và vì sao chúng là lỗi:
  - hardcode crm.lead: activity gắn được vào MỌI chứng từ, và đó là điều kiện
    để bàn giao liên bộ phận sau này có chỗ bám.
  - chỉ Call/Meeting: bỏ mất To-Do (loại NHIỀU NHẤT trong dữ liệu thật, 11/31),
    Email, Document.
  - user_id luôn = tài khoản gọi: không giao việc cho ai khác được.

Test gọi thẳng hàm đã đăng ký trong registry FastMCP với odoo() bị
monkeypatch — KHÔNG chạm Odoo thật (cùng khuôn
tests/mcp/test_mail_role_scope_wiring.py)."""
import importlib
import json
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def crm_mod():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server  # noqa: F401  — đăng ký tool
    finally:
        sys.path.remove(str(MCP_DIR))
    return sys.modules["tools.crm"]


@pytest.fixture(scope="module")
def log_activity_fn():
    import server
    return server.mcp._tool_manager._tools["log_activity"].fn


def _fake_odoo(calls, *, types=None, users=None, rec=True):
    """types: [{'id','name','res_model'}]; users: [{'id','name','login'}]."""
    types = [{"id": 7, "name": "To-Do", "res_model": False}] if types is None else types
    users = [] if users is None else users

    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        if model == "mail.activity.type":
            return types
        if model == "res.users":
            return users
        if model == "ir.model":
            return [3]
        if method == "create":
            return 999
        # search_read bản ghi đích
        return [{"id": args[0][0][2], "name": "S00119"}] if rec else []

    return odoo


def test_tao_duoc_tren_model_bat_ky(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "Gọi lại khách"))
    assert out["ok"] is True
    tao = [c for c in calls if c[1] == "create" and c[0] == "mail.activity"]
    assert len(tao) == 1
    vals = tao[0][2][0]
    assert vals["res_id"] == 119
    assert vals["res_model_id"] == 3
    assert vals["user_id"] == 8          # bỏ trống assignee = tài khoản gọi


def test_loai_gan_model_khac_bi_tu_choi(crm_mod, log_activity_fn, monkeypatch):
    """Maintenance Request gắn cứng maintenance.request trong Odoo. Từ chối
    phải đến TỪ DỮ LIỆU Odoo, không từ một danh sách cấm viết tay."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, types=[{"id": 9, "name": "Maintenance Request",
                       "res_model": "maintenance.request"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Maintenance Request", "x"))
    assert out["ok"] is False
    assert "maintenance.request" in out["display"]
    assert not [c for c in calls if c[1] == "create"]


def test_loai_khong_ton_tai(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, types=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Bịa Ra", "x"))
    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "create"]


def test_ban_ghi_dich_khong_ton_tai(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, rec=False))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 404, "To-Do", "x"))
    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "create"]


def test_assignee_khop_login(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, users=[{"id": 10, "name": "AI Accounting", "login": "ai-accounting"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="ai-accounting"))
    assert out["ok"] is True
    vals = [c for c in calls if c[1] == "create"][0][2][0]
    assert vals["user_id"] == 10


def test_assignee_khong_tim_thay_thi_tu_choi(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, users=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="Nguyễn Bịa"))
    assert out["ok"] is False
    assert "Nguyễn Bịa" in out["display"]
    assert not [c for c in calls if c[1] == "create"]


def test_assignee_trung_nhieu_thi_tu_choi_va_liet_ke(crm_mod, log_activity_fn, monkeypatch):
    """KHÔNG tự chọn khi mơ hồ — fail-closed, giống mọi chỗ khác trong dự án."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, users=[{"id": 5, "name": "Marc Demo", "login": "demo"},
                      {"id": 6, "name": "Marc Khác", "login": "marc2"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="Marc"))
    assert out["ok"] is False
    assert "Marc Demo" in out["display"] and "Marc Khác" in out["display"]
    assert not [c for c in calls if c[1] == "create"]
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/mcp/test_log_activity_tool.py -v`
Expected: FAIL — chữ ký cũ nhận `lead_id`, gọi `log_activity_fn("sale.order", ...)` sẽ `TypeError`.

- [ ] **Step 3: Viết lại `log_activity` trong `mcp-servers/odoo/tools/crm.py`**

Thay nguyên hàm hiện tại (dòng 109-153) bằng:

```python
@mcp.tool()
def log_activity(res_model: str, res_id: int, activity_type: str, summary: str,
                 date_deadline: str = "", assignee: str = "") -> str:
    """Lên lịch một hoạt động (To-Do, Call, Meeting, Email, Document...) gắn
    vào MỘT chứng từ bất kỳ trong Odoo. YÊU CẦU XÁC NHẬN từ người dùng trước
    khi gọi.

    Loại hợp lệ do chính Odoo quyết định: mail.activity.type có res_model
    RỖNG dùng được cho mọi model, có giá trị thì chỉ model đó (vd
    "Maintenance Request" chỉ gắn được vào maintenance.request). KHÔNG có
    danh sách cấm viết tay ở đây.

    Args:
        res_model: Model của chứng từ, vd "sale.order".
        res_id: ID chứng từ (coordinator đã giải từ mã người dùng gõ).
        activity_type: Tên loại trong Odoo, vd "To-Do".
        summary: Nội dung ngắn gọn.
        date_deadline: Hạn (YYYY-MM-DD); bỏ trống = hôm nay.
        assignee: Người nhận — login hoặc tên. Bỏ trống = tài khoản đang gọi.
    """
    try:
        recs = odoo(res_model, "search_read", [[["id", "=", res_id]]],
                    {"fields": ["id", "name"], "limit": 1})
        if not recs:
            return envelope(False, f"Không tìm thấy bản ghi ID {res_id} "
                                   f"trong {res_model}.")
        rec = recs[0]
        ref = rec.get("name") or str(res_id)

        types = odoo("mail.activity.type", "search_read",
                     [[["name", "=", activity_type]]],
                     {"fields": ["id", "name", "res_model"], "limit": 1})
        if not types:
            return envelope(False, f"Loại hoạt động '{activity_type}' không có "
                                   f"trong Odoo.")
        atype = types[0]
        # res_model RỖNG = dùng cho mọi model. Có giá trị = chỉ model đó.
        if atype.get("res_model") and atype["res_model"] != res_model:
            return envelope(False,
                            f"Loại '{atype['name']}' chỉ dùng được cho "
                            f"{atype['res_model']}, không phải {res_model}.")

        user_id = get_uid()
        if assignee:
            user_id = _resolve_assignee(assignee)
            if isinstance(user_id, str):        # chuỗi = câu từ chối
                return envelope(False, user_id)

        # Probe-verified (2026-07-19): mail.activity create BẮT BUỘC
        # res_model_id (ir.model id, tra runtime) — shape res_model (char) bị
        # Odoo từ chối. Hai vai non-admin KHÔNG có ir.model read theo mặc
        # định; nhóm "Youdoo AI / Activity" cấp đúng quyền đó (spec §6).
        model_ids = odoo("ir.model", "search", [[["model", "=", res_model]]],
                         {"limit": 1})
        if not model_ids:
            return envelope(False, f"Model '{res_model}' không tồn tại trong Odoo.")

        han = date_deadline or today_iso()
        act_id = odoo("mail.activity", "create",
                      [{"res_model_id": model_ids[0], "res_id": res_id,
                        "activity_type_id": atype["id"],
                        "summary": summary,
                        "date_deadline": han,
                        "user_id": user_id}])
        return envelope(True,
                        f"Đã lên lịch {atype['name']} cho '{ref}': {summary} "
                        f"— hạn {han}.",
                        ref=ref, model="mail.activity", res_id=act_id,
                        state="planned")
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi lên lịch hoạt động: {e}")
```

- [ ] **Step 4: Thêm helper `_resolve_assignee` ngay TRƯỚC `log_activity`**

```python
def _resolve_assignee(assignee: str):
    """→ user_id (int) | câu từ chối (str).

    Thứ tự: login chính xác → name chính xác → tìm gần đúng theo name.
    Trùng nhiều ở bước cuối thì TỪ CHỐI và liệt kê, không tự chọn — fail-closed
    giống mọi chỗ giải thực thể khác trong dự án.

    Chỉ xét người dùng nội bộ (share=False): người dùng portal không nhận
    việc được.
    """
    noi_bo = [["share", "=", False]]
    for domain in ([["login", "=", assignee]] + noi_bo,
                   [["name", "=", assignee]] + noi_bo):
        rows = odoo("res.users", "search_read", [domain],
                    {"fields": ["id", "name", "login"], "limit": 2})
        if len(rows) == 1:
            return rows[0]["id"]
    rows = odoo("res.users", "search_read",
                [[["name", "ilike", assignee]] + noi_bo],
                {"fields": ["id", "name", "login"], "limit": 6})
    if not rows:
        return f"Không tìm thấy người dùng '{assignee}'."
    if len(rows) > 1:
        ten = ", ".join(f"{r['name']} ({r['login']})" for r in rows)
        return f"Có nhiều người khớp '{assignee}': {ten}. Vui lòng nêu rõ hơn."
    return rows[0]["id"]
```

- [ ] **Step 5: Chạy test mới**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/mcp/test_log_activity_tool.py -v`
Expected: PASS, 7 test

- [ ] **Step 6: Chạy test biên MCP để xác nhận không phá bất biến cũ**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/mcp/ -v`
Expected: PASS toàn bộ. `_resolve_assignee` đi qua `odoo()` nên
`test_khong_tool_nao_goi_thang_odoo` vẫn xanh.

- [ ] **Step 7: Commit**

```bash
git add mcp-servers/odoo/tools/crm.py backend/tests/mcp/test_log_activity_tool.py
git commit -m "feat(crm): log_activity nhận mọi model, mọi loại, mọi người nhận

Ba giới hạn cũ: hardcode crm.lead, chỉ Call/Meeting, user_id luôn là tài khoản
gọi. Hệ quả đo được: 1/37 activity là do dự án sinh ra, phần còn lại là seed.

Loại hợp lệ nay do mail.activity.type.res_model quyết định (rỗng = mọi model)
thay vì một danh sách viết tay — đổi hardcode 2 thành hardcode 5 là lặp lại
đúng hạng lỗi hai đợt vừa rồi đi sửa.

assignee giải theo login rồi name rồi gần đúng; trùng nhiều thì từ chối và liệt
kê, không tự chọn."
```

---

### Task 2: Coordinator — giải tham chiếu theo model

**Files:**
- Modify: `backend/src/agents/crm_write.py:22-27` (`_ACTIVITY_ALIASES`), `:180-240` (node `log_activity`), thêm bảng giải mới
- Modify: `backend/src/agents/prompts.py:85` (dòng khai tool trong `WRITE_PLANNER_PROMPT`)
- Modify: `backend/tests/agents/test_crm_write.py:231-280` (3 test hiện có)

**Interfaces:**
- Consumes: `log_activity(res_model, res_id, activity_type, summary, date_deadline="", assignee="")` từ Task 1; `_resolve_lead(lead_ref)` hiện có, **giữ nguyên**
- Produces: node coordinator gọi tool với `res_model` + `res_id`; planner nhận args mới `res_model`, `ref`, `activity_type`, `summary`, `date_deadline`, `assignee`

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_crm_write.py`. **Dùng helper SẴN CÓ
của file** (`_fake_tool(name, rec)`, `_graph(node)`, `_state(tool, args)`,
`_ok_resolve`) — KHÔNG định nghĩa lại, chúng đã tồn tại ở đầu file và đặt trùng
tên sẽ che mất bản gốc:

```python
@pytest.mark.asyncio
async def test_log_activity_tren_sale_order_giai_theo_ma(monkeypatch):
    """Model KHÁC crm.lead giải bằng tra `name =` chính xác — mã đơn vốn là mã
    máy (S00119), không cần tìm mờ."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda model, domain, fields, **kw: [{"id": 119, "name": "S00119"}])
    rec = {}
    graph = _graph(cw.make_log_activity_node([_fake_tool("log_activity", rec)]))
    cfg = {"configurable": {"thread_id": "la1"}}
    res = await graph.ainvoke(_state("log_activity",
                                     {"res_model": "sale.order", "ref": "S00119",
                                      "activity_type": "To-Do",
                                      "summary": "Gọi lại khách"}), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["res_model"] == "sale.order"
    assert rec["args"]["res_id"] == 119


@pytest.mark.asyncio
async def test_log_activity_model_khong_ho_tro_thi_tu_choi(monkeypatch):
    """Fail-closed: model chưa biết cách giải thì từ chối, KHÔNG đoán."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    rec = {}
    graph = _graph(cw.make_log_activity_node([_fake_tool("log_activity", rec)]))
    cfg = {"configurable": {"thread_id": "la2"}}
    res = await graph.ainvoke(_state("log_activity",
                                     {"res_model": "res.partner", "ref": "Acme",
                                      "activity_type": "To-Do", "summary": "x"}), cfg)
    assert "__interrupt__" not in res
    assert "res.partner" in res["messages"][-1].content
    assert rec == {}


@pytest.mark.asyncio
async def test_log_activity_crm_lead_van_dung_resolve_lead(monkeypatch):
    """_resolve_lead có tìm mờ + bỏ kính ngữ + hỏi lại khi trùng. Đường
    crm.lead PHẢI còn đi qua nó, không rơi về tra `name =` chính xác."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(cw.crm, "find_lead", lambda *a, **k: _ok_resolve(
        [{"id": 45, "name": "Cơ hội A", "score": 1}], False))
    # Nếu đường crm.lead lỡ rơi vào _search_by_name thì test đỏ ngay.
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda *a, **k: pytest.fail("crm.lead không được đi qua _search_by_name"))
    rec = {}
    graph = _graph(cw.make_log_activity_node([_fake_tool("log_activity", rec)]))
    cfg = {"configurable": {"thread_id": "la3"}}
    await graph.ainvoke(_state("log_activity",
                               {"res_model": "crm.lead", "ref": "anh Nam",
                                "activity_type": "Call", "summary": "x"}), cfg)
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["res_model"] == "crm.lead" and rec["args"]["res_id"] == 45


@pytest.mark.asyncio
async def test_log_activity_truyen_assignee_xuong_tool(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(cw.crm, "find_lead", lambda *a, **k: _ok_resolve(
        [{"id": 45, "name": "Cơ hội A", "score": 1}], False))
    rec = {}
    graph = _graph(cw.make_log_activity_node([_fake_tool("log_activity", rec)]))
    cfg = {"configurable": {"thread_id": "la4"}}
    res = await graph.ainvoke(_state("log_activity",
                                     {"res_model": "crm.lead", "ref": "Cơ hội A",
                                      "activity_type": "Call", "summary": "x",
                                      "assignee": "ai-accounting"}), cfg)
    assert "ai-accounting" in res["__interrupt__"][0].value["question"]
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["args"]["assignee"] == "ai-accounting"


@pytest.mark.asyncio
async def test_log_activity_tu_choi_o_cong_xac_nhan_thi_khong_ghi(monkeypatch):
    """Spec §9.1: huỷ ở cổng xác nhận KHÔNG được gọi tool."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    monkeypatch.setattr(cw.crm, "find_lead", lambda *a, **k: _ok_resolve(
        [{"id": 45, "name": "Cơ hội A", "score": 1}], False))
    rec = {}
    graph = _graph(cw.make_log_activity_node([_fake_tool("log_activity", rec)]))
    cfg = {"configurable": {"thread_id": "la5"}}
    await graph.ainvoke(_state("log_activity",
                               {"res_model": "crm.lead", "ref": "Cơ hội A",
                                "activity_type": "Call", "summary": "x"}), cfg)
    await graph.ainvoke(Command(resume=False), cfg)
    assert rec == {}
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_crm_write.py -v -k "res_model or khong_ho_tro or resolve_lead or assignee"`
Expected: FAIL — node hiện đọc `lead_ref`, không đọc `res_model`.

- [ ] **Step 3: Thêm bảng giải tham chiếu vào `crm_write.py`**

Đặt ngay sau `_resolve_lead` (kết thúc dòng 80):

```python
# Model giải bằng tra `name =` chính xác: mã của chúng vốn là mã máy
# (S00119, WH/OUT/00138, P00068) nên tìm mờ không thêm giá trị mà chỉ thêm
# đường sai. crm.lead KHÔNG nằm đây — nó có _resolve_lead riêng với tìm mờ,
# bỏ kính ngữ và hỏi lại khi trùng, và mất ba thứ đó là gỡ tính năng đang chạy.
_EXACT_NAME_MODELS = ("sale.order", "purchase.order", "account.move",
                      "stock.picking", "mrp.production")


def _search_by_name(model, domain, fields, **kw):
    """Tách ra thành hàm riêng để test monkeypatch được mà không cần Odoo."""
    from ..erp_query.gateway import default_gateway
    return default_gateway().search_read(model, domain, fields, **kw)


def _resolve_doc(res_model: str, ref: str):
    """→ ("ok", {"id","name"}) | ("msg", <dict trả ngay>).

    Fail-closed: model chưa biết cách giải thì TỪ CHỐI, không đoán."""
    if res_model == "crm.lead":
        return _resolve_lead(ref)
    if res_model not in _EXACT_NAME_MODELS:
        ho_tro = ", ".join(("crm.lead",) + _EXACT_NAME_MODELS)
        return "msg", _msg(f"Chưa hỗ trợ gắn hoạt động vào '{res_model}'. "
                           f"Hiện hỗ trợ: {ho_tro}.")
    rows = _search_by_name(res_model, [["name", "=", ref]], ["id", "name"],
                           limit=2)
    if not rows:
        # Hoá đơn NHÁP có name=False (đo 2026-08-08) nên tra theo mã chỉ tìm
        # được hoá đơn ĐÃ phát hành — nói rõ để người dùng không tưởng gõ sai.
        them = (" Lưu ý: hoá đơn nháp chưa có số nên chưa tra được theo mã."
                if res_model == "account.move" else "")
        return "msg", _msg(f"Không tìm thấy '{ref}' trong {res_model}.{them}")
    if len(rows) > 1:
        return "msg", _msg(f"Có nhiều bản ghi tên '{ref}' trong {res_model}. "
                           f"Vui lòng nêu rõ hơn.")
    return "ok", rows[0]
```

- [ ] **Step 4: Xoá `_ACTIVITY_ALIASES` và sửa node**

Xoá nguyên khối `_ACTIVITY_ALIASES` (dòng 22-27) cùng comment ngay trên nó — việc kiểm loại nay thuộc về tool, nơi có Odoo để hỏi.

Trong `make_log_activity_node`, thay phần đọc args + kiểm + giải (từ `lead_ref = ...` tới hết `kind, lead = _resolve_lead(lead_ref)`) bằng:

```python
        args = (state.get("pending_action") or {}).get("args") or {}
        res_model = str(args.get("res_model") or "").strip()
        ref = str(args.get("ref") or "").strip()
        activity_type = str(args.get("activity_type") or "").strip()
        summary = str(args.get("summary") or "").strip()
        deadline = str(args.get("date_deadline") or "").strip()
        assignee = str(args.get("assignee") or "").strip()

        # Slot-fill GỘP: liệt kê MỌI slot còn thiếu trong một câu.
        missing = []
        if not res_model or not ref:
            missing.append("gắn vào chứng từ nào (loại và mã, vd đơn bán S00119)")
        if not activity_type:
            missing.append("loại hoạt động (vd To-Do, Call, Meeting)")
        if not summary:
            missing.append("nội dung ngắn gọn")
        if missing:
            return _msg("Vui lòng cho biết: " + "; ".join(missing) + ".")

        kind, doc = _resolve_doc(res_model, ref)
        if kind == "msg":
            return doc
```

Sửa câu hỏi xác nhận cho khớp:

```python
        nguoi = f" — giao {assignee}" if assignee else ""
        confirmed = _interrupt({
            "kind": "confirm",
            "question": (f"Lên lịch {activity_type} cho '{doc['name']}': "
                         f"{summary} — hạn {deadline}{nguoi}.\n"
                         + WRITE_CONFIRM_SUFFIX),
            "expires_at": _ttl_expiry()})
```

Và lời gọi tool:

```python
            result = await tool.ainvoke({"res_model": res_model,
                                         "res_id": doc["id"],
                                         "activity_type": activity_type,
                                         "summary": summary,
                                         "date_deadline": deadline,
                                         "assignee": assignee})
```

- [ ] **Step 5: Sửa dòng khai tool trong `WRITE_PLANNER_PROMPT`**

`backend/src/agents/prompts.py:85`, thay bằng:

```
- log_activity(res_model: str, ref: str, activity_type: str, summary: str, date_deadline: str = null, assignee: str = null)  # gắn hoạt động (To-Do | Call | Meeting | Email | Document) vào một chứng từ; res_model là "crm.lead" | "sale.order" | "purchase.order" | "account.move" | "stock.picking" | "mrp.production"; ref là mã chứng từ; assignee là người nhận (login hoặc tên), bỏ trống = chính mình; date_deadline dạng YYYY-MM-DD, bỏ trống = hôm nay
```

- [ ] **Step 6: Sửa 3 test cũ ở `test_crm_write.py:231-280`**

Ba test hiện có dùng `lead_ref` và alias tiếng Việt. Sửa **ý định giữ nguyên**, chỉ đổi đường đi:

- `test_log_activity_slot_ask_combined`: đổi args từ `{"lead_ref": "Quan tâm lốp"}` thành `{}` (không còn `lead_ref`), và đổi assertion thành `assert "chứng từ" in msg and "loại hoạt động" in msg and "nội dung" in msg` — nay phải nêu **cả ba** slot thiếu.
- `test_log_activity_alias_goi_dien_maps_to_call`: **XOÁ**. Alias đã bị gỡ có chủ đích; giữ lại là khoá một hành vi vừa cố ý bỏ. Ghi lý do trong commit message.
- `test_log_activity_invalid_type_lists_options`: **XOÁ**. Việc kiểm loại chuyển xuống tool và đã có `test_loai_khong_ton_tai` + `test_loai_gan_model_khac_bi_tu_choi` ở Task 1 phủ, với kiểm chứng mạnh hơn (đến từ dữ liệu Odoo thay vì danh sách tay).

- [ ] **Step 7: Chạy test**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_crm_write.py tests/agents/test_prompts.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 8: Chạy toàn bộ suite**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1319 passed, 4 skipped, 46 deselected` (1309 + 7 của Task 1 + 5 mới của Task 2 − 2 test đã xoá).

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/crm_write.py backend/src/agents/prompts.py backend/tests/agents/test_crm_write.py
git commit -m "feat(crm): coordinator log_activity giải tham chiếu theo model

crm.lead GIỮ NGUYÊN _resolve_lead (tìm mờ + bỏ kính ngữ + hỏi lại khi trùng);
5 model còn lại tra name= chính xác vì mã của chúng vốn là mã máy. Model chưa
biết cách giải thì từ chối, không đoán.

Xoá _ACTIVITY_ALIASES: việc kiểm loại chuyển xuống tool, nơi hỏi được Odoo.
Xoá 2 test cũ khoá đúng hành vi vừa cố ý bỏ (alias tiếng Việt, danh sách loại
viết tay) — chúng đã được thay bằng test mạnh hơn ở tầng tool."
```

---

### Task 3: Quyền Odoo + cấp tool cho hai vai

**Files:**
- Modify: `scripts/odoo_setup_ai_accounts.py` (thêm nhóm `Youdoo AI / Activity`, gán cho 3 tài khoản ghi)
- Modify: `backend/src/agents/roles.py` (`_WH_OWN`, `_ACC_OWN`, `DEPT_OF`)
- Modify: `scripts/check_role_odoo_consistency.py` (`TOOL_ACCESS_MAP`)
- Test: `backend/tests/agents/test_log_activity_roles.py` (tạo mới)

**Interfaces:**
- Consumes: `log_activity` từ Task 1/2
- Produces: `log_activity` là `own` của cả `warehouse` và `accounting` ở cả hai profile; nhóm Odoo `Youdoo AI / Activity`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_log_activity_roles.py`:

```python
"""log_activity được cấp cho cả hai vai non-admin.

ĐỢT NÀY CỐ Ý ĐỔI allowed_tools() — ngược ràng buộc cứng của đợt trước. Thêm
một tool vào `own` nghĩa là scripts/odoo_setup_ai_accounts.py sinh ra bộ nhóm
quyền Odoo khác trước, nên thay đổi này phải được khoá bằng test chứ không để
nó âm thầm."""
import pathlib

from src.agents import roles

SETUP = (pathlib.Path(__file__).resolve().parents[3]
         / "scripts" / "odoo_setup_ai_accounts.py")
CHECK = (pathlib.Path(__file__).resolve().parents[3]
         / "scripts" / "check_role_odoo_consistency.py")


def test_ca_hai_vai_deu_so_huu_log_activity():
    for profile_name, profile in roles.PROFILES.items():
        for role_name in ("warehouse", "accounting"):
            cfg = profile[role_name]
            assert cfg.state_of("log_activity") == roles.OWN, (
                f"{profile_name}/{role_name} không sở hữu log_activity")
            assert "log_activity" in cfg.allowed_tools()


def test_log_activity_co_trong_dept_of():
    """Test bao phủ của đợt trước đòi mọi tool được sở hữu phải có bộ phận."""
    assert "log_activity" in roles.DEPT_OF


def test_nhom_activity_duoc_tao_va_gan_cho_ba_tai_khoan_ghi():
    """Đọc NGUỒN script, không chạy nó — chạy là chạm Odoo sống."""
    src = SETUP.read_text(encoding="utf-8")
    assert "Youdoo AI / Activity" in src
    assert "ir.model" in src
    for login in ("ai-admin", "ai-warehouse", "ai-accounting"):
        assert login in src


def test_bang_quyen_co_dong_cho_log_activity():
    """log_activity trước đây nằm trong UNMAPPED_TOOLS hoặc không có; nay nó là
    own của hai vai nên script kiểm tra phải đo được nó."""
    src = CHECK.read_text(encoding="utf-8")
    assert "log_activity" in src
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_log_activity_roles.py -v`
Expected: FAIL — `state_of("log_activity")` hiện trả `denied`.

- [ ] **Step 3: Cấp tool cho hai vai trong `roles.py`**

Thêm `"log_activity"` vào `_WH_OWN` và `_ACC_OWN`. Với profile `enterprise`, vai kho khai `own` inline — thêm `"log_activity"` vào đó nữa.

Thêm vào `DEPT_OF`:

```python
    # Giá trị này KHÔNG ảnh hưởng hành vi hôm nay: cả hai vai non-admin đều
    # `own` log_activity, mà other_dept trừ đi own — nên không vai nào cần chỉ
    # sang đâu cho tool này. Chọn "Kho" là tuỳ tiện, và nó CHỈ bắt đầu có nghĩa
    # nếu sau này có một vai KHÔNG sở hữu log_activity; lúc đó phải xem lại.
    # Vẫn thêm mục thay vì nới test bao phủ DEPT_OF — nới test để lấy một ngoại
    # lệ là làm yếu đúng cái lưới vừa dựng.
    "log_activity": "Kho",
```

- [ ] **Step 4: Thêm nhóm `Youdoo AI / Activity` vào script tạo tài khoản**

Trong `scripts/odoo_setup_ai_accounts.py`, thêm sau khối `g_sinv`:

```python
# mail.activity create BẮT BUỘC res_model_id (id của ir.model, tra runtime —
# truyền res_model dạng chuỗi bị Odoo từ chối, probe-verify 2026-07-19). Đo
# 2026-08-12: cả ba tài khoản ghi CÓ mail.activity create, nhưng
# ai-warehouse/ai-accounting KHÔNG có ir.model read. Thiếu quyền phụ này thì
# log_activity gãy đúng kiểu coordinator mail đã gãy: quyền chính có, quyền
# phụ không, và chỉ live-verify mới thấy.
g_act = ensure_group("Youdoo AI / Activity")
ensure_access("youdoo_ai_activity_ir_model", g_act, "ir.model", {"read": 1})
```

Và thêm `g_act` vào cả ba dòng tài khoản ghi trong `PLAN`:

```python
    "ai-admin":      [BASE_USER, g_mail, g_act] + [gid_by_full_name(n) for n in (
        "Inventory / Administrator", "Accounting / Administrator", "Sales / Administrator",
        "Purchase / Administrator", "Manufacturing / Administrator", "Contact / Creation",
        "Role / Administrator")],
```

(tương tự thêm `g_act` cho `ai-warehouse` và `ai-accounting`; **không** thêm cho `ai-readonly`.)

- [ ] **Step 5: Thêm dòng `log_activity` vào `TOOL_ACCESS_MAP`**

Trong `scripts/check_role_odoo_consistency.py`, thêm vào bảng:

```python
    "log_activity":            [("mail.activity", "create")],  # crm.py log_activity
```

Nếu `log_activity` đang nằm trong `UNMAPPED_TOOLS` thì xoá nó khỏi đó — nay nó
map sạch vào một cặp.

- [ ] **Step 6: Chạy test mới + test chốt drift của đợt trước**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_log_activity_roles.py tests/agents/test_dept_of.py tests/agents/test_other_dept_derived.py tests/mcp/test_tool_access_map_drift.py -v`
Expected: PASS toàn bộ.

**Nếu `test_model_bi_ghi_trong_nguon_deu_da_duoc_khai` đỏ:** đọc kỹ — nó có thể
đang báo rằng `log_activity` chạm thêm model ngoài `mail.activity` (vd
`res.users`, `ir.model`). Đó là **phát hiện đúng**, không phải lỗi test: bổ sung
các cặp còn thiếu vào `TOOL_ACCESS_MAP` thay vì sửa test.

- [ ] **Step 7: Kiểm cú pháp script (KHÔNG chạy — chạy là chạm Odoo sống)**

Run: `cd /d/Youdoo && backend/.venv/Scripts/python.exe -m py_compile scripts/odoo_setup_ai_accounts.py scripts/check_role_odoo_consistency.py && echo OK`
Expected: `OK`

`py_compile` chỉ chứng minh cú pháp, KHÔNG chứng minh hợp đồng gọi Odoo đúng —
chính script này từng py_compile sạch rồi crash ở lần chạy sống đầu tiên.
Controller sẽ chạy thật ở phần Nghiệm thu sống.

- [ ] **Step 8: Chạy toàn bộ suite**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1323 passed, 4 skipped, 46 deselected` (1319 + 4).

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/roles.py scripts/odoo_setup_ai_accounts.py scripts/check_role_odoo_consistency.py backend/tests/agents/test_log_activity_roles.py
git commit -m "feat(roles): cấp log_activity cho kho + kế toán, thêm nhóm Youdoo AI / Activity

Đợt này CỐ Ý đổi allowed_tools() — ngược ràng buộc cứng của đợt trước. Thêm một
tool vào own nghĩa là script tạo tài khoản sinh ra bộ nhóm quyền Odoo khác
trước, nên thay đổi được khoá bằng test thay vì để âm thầm.

Nhóm Youdoo AI / Activity cấp ĐÚNG ir.model read. Đo 2026-08-12: cả ba tài
khoản ghi có mail.activity create nhưng hai vai non-admin không có ir.model
read, mà create bắt buộc res_model_id.

DEPT_OF['log_activity'] là giá trị tuỳ tiện vì cả hai vai đều sở hữu tool này —
ghi rõ trong comment, và vẫn thêm mục thay vì nới test bao phủ."
```

---

## Nghiệm thu sống — CONTROLLER làm, không phải subagent

### A. Áp quyền Odoo

Dừng hẳn stack cũ trước khi khởi động stack của nhánh — `start-dev.ps1` thấy
port đang mở sẽ dùng lại tiến trình cũ chạy code `main`, và toàn bộ nghiệm thu
sẽ là giả. Worktree không có venv/`.env`: sao chép `.env`, tạo junction cho hai
venv, và **gỡ junction TRƯỚC khi xoá worktree**.

```bash
backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py
```
Chạy **hai lần**; lần hai phải in "nhóm đã có" — chứng minh idempotent.

### B. Năm kịch bản (spec §9.2)

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1 | admin: *"tạo việc cần làm cho đơn S00119: gọi lại khách, giao Marc Demo"* | tạo được; đọc lại Odoo thấy đúng `user_id`, `res_model`, hạn |
| 2 | **kho**: tạo activity trên phiếu kho, giao `ai-accounting` | **phép đo QUYẾT ĐỊNH cho nhóm quyền mới** — đi qua đúng đường `ir.model` từng thiếu quyền |
| 3 | loại `Maintenance Request` trên `sale.order` | từ chối, nêu `maintenance.request` |
| 4 | `assignee` gõ sai tên | từ chối, nêu tên đã gõ |
| 5 | `check_role_odoo_consistency.py` | exit 0; dòng `log_activity` mới **KHỚP**, không thành GAP thứ 10 |

Kịch bản 2 là phép đo quyết định: nếu nhóm `Youdoo AI / Activity` không được áp
đúng, nó sẽ gãy ở `ir.model` — và đó là đúng chế độ hỏng mà spec §6 dựng ra để
ngăn.

Gửi payload từ **file UTF-8** (`curl --data-binary @file`) — shell mã hoá sai
tiếng Việt làm backend trả 500 và trông như lỗi code.

### C. Đối chứng âm

Vai kho vẫn từ chối đúng những việc ngoài quyền (vd phát hành hoá đơn) — thêm
một tool vào `own` không được nới thứ khác.

### D. Dọn dẹp

Xoá mọi `mail.activity` tạo ra khi đo (ghi lại id trước khi xoá).

### E. Báo cáo

`docs/superpowers/plans/2026-08-12-log-activity-generalisation-report.md` —
kết quả 5 kịch bản, đối chứng âm, và số liệu `check_role_odoo_consistency.py`
trước/sau.
