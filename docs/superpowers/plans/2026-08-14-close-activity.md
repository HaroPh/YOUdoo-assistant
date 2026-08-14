# Đóng activity từ phía trợ lý — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người dùng nói *"việc trên đơn S00012 xong rồi"* và activity được giao
cho bộ phận mình được đánh dấu hoàn tất, qua cổng xác nhận ghi sẵn có.

**Architecture:** Hai tool MCP mới trong `tools/crm.py` (`find_my_activities` tra
ứng viên, `close_activity` đóng) — **cả hai lọc theo `get_uid()`**, là tài khoản
Odoo đã xác thực của vai, nên về mặt cấu tạo không chạm nổi việc của người khác.
Một coordinator trong `crm_write.py` lo giải chứng từ, hỏi lại khi trùng, và cổng
xác nhận. `find_my_activities` vào graph qua `Spec.deps` (khuôn `MAIL_DEPS`) nên
nó **không lọt vào danh sách tool planner nhìn thấy**.

**Tech Stack:** Python 3.11, FastMCP, LangGraph, Odoo 19 XML-RPC, pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-close-activity-design.md` — đọc
trước khi bắt đầu Task 1. Mọi con số đo trong plan này đến từ §1 của spec.

## Global Constraints

- **Lệnh pytest LUÔN kèm bộ lọc marker:** `pytest -m "not integration and not live" -q`.
  Lệnh trần gọi API LLM thật và Postgres thật — đã gây sự cố một lần.
- **Định danh trong `backend/src/` và `mcp-servers/` viết bằng TIẾNG ANH.**
  Chú thích và chuỗi hiển thị bằng tiếng Việt. (Đã có bảy lần định danh tiếng
  Việt lọt vào mã nguồn vì implementer chép nguyên code trong plan.)
- **Fail-closed:** mơ hồ thì từ chối, không đoán.
- **Không lộ nguyên văn lỗi Odoo hay tên nhóm quyền Odoo** ra câu trả lời
  người dùng.
- **Không chạm hạ tầng sống.** Implementer KHÔNG được khởi động/dừng/khởi động
  lại tiến trình, container, hay ghi vào Odoo thật. Mọi test dùng gateway giả /
  `monkeypatch`. Nghiệm thu sống do controller làm.
- **Mọi test dựng được ứng viên phải tiêm tool giả.** Vòng trước có một test gọi
  Odoo THẬT vì thiếu điểm tiêm; nghiệm thu sống tạo đúng bản ghi đó khiến 3 test
  đỏ như một hồi quy bí ẩn.
- **Không thụt:** `pytest -m "not integration and not live" -q` phải giữ
  **≥ 1387 passed, 4 skipped**.

---

## File Structure

| file | trách nhiệm | task |
|---|---|---|
| `mcp-servers/odoo/security.py` | allowlist method XML-RPC (deny-by-default) — thêm `action_feedback` | 1 |
| `mcp-servers/odoo/tools/crm.py` | `close_activity` (Task 1), `find_my_activities` (Task 2) | 1, 2 |
| `backend/src/agents/crm_write.py` | coordinator `make_close_activity_node` + 2 helper | 3 |
| `backend/src/agents/write_registry.py` | một dòng `WRITE_COORDINATORS` kèm `deps` | 4 |
| `backend/src/agents/roles.py` | `DEPT_OF` + `own` của hai vai, hai hồ sơ | 4 |
| `backend/src/agents/handoff.py` | `NO_DOCUMENT_TOOLS` — bắt buộc, xem Task 4 | 4 |
| `backend/src/agents/prompts.py` | một dòng `WRITE_PLANNER_PROMPT` | 4 |
| `scripts/check_role_odoo_consistency.py` | `TOOL_ACCESS_MAP` | 4 |
| `backend/src/erp_query/crm.py` | sửa chú thích sai (chỉ chú thích) | 5 |
| `backend/tests/mcp/test_close_activity_tool.py` | test Task 1 | 1 |
| `backend/tests/mcp/test_find_my_activities_tool.py` | test Task 2 | 2 |
| `backend/tests/agents/test_close_activity_node.py` | test Task 3 | 3 |
| `backend/tests/agents/test_close_activity_roles.py` | test Task 4 | 4 |

---

## Task 1: Tool MCP `close_activity` + mở allowlist cho `action_feedback`

**Files:**
- Modify: `mcp-servers/odoo/security.py` (thêm 1 dòng vào `ODOO_METHOD_OPERATION_MAP`)
- Modify: `mcp-servers/odoo/tools/crm.py` (thêm tool ở cuối file)
- Test: `backend/tests/mcp/test_close_activity_tool.py` (tạo mới)

**Interfaces:**
- Consumes: `from server import mcp`, `from odoo_call import odoo, get_uid`,
  `from helpers import envelope` — cả ba đã có sẵn ở đầu `tools/crm.py`.
- Produces: tool MCP `close_activity(activity_id: int, note: str = "") -> str`.
  Trả JSON-string dạng `envelope`: `{"ok", "ref", "model", "res_id", "state",
  "display"}`. Thành công → `ok=True`, `model="mail.activity"`,
  `res_id=activity_id`, `state="done"`.

**Bối cảnh bắt buộc đọc trước khi viết:**

`mcp-servers/odoo/odoo_call.py` bắt mọi lệnh đi qua `classify_operation()`.
Method **không có trong `ODOO_METHOD_OPERATION_MAP` thì bị TỪ CHỐI**
(deny-by-default, `raise ValueError("Method ... không được phép")`).
`action_feedback` hiện **không có trong bảng**. Không thêm thì tool này chết
ngay ở lớp bảo mật của chính dự án, trước khi chạm Odoo — và phép đo XML-RPC
trong spec §1 KHÔNG thấy được điều đó vì nó đi thẳng vào Odoo, vòng qua lớp này.

- [ ] **Step 1: Viết test cho allowlist (đỏ trước)**

Tạo `backend/tests/mcp/test_close_activity_tool.py` với phần đầu:

```python
"""close_activity — đóng MỘT việc đang giao cho tài khoản đang gọi.

Đo trên Odoo thật 2026-08-14 (spec §1.3): Odoo KHÔNG chặn một tài khoản đóng
việc của người khác. Bộ lọc user_id trong tool là lớp cưỡng chế DUY NHẤT, nên
nó có test riêng và phải chịu được phép thử phá.

Test gọi thẳng hàm đã đăng ký trong registry FastMCP với odoo() bị monkeypatch
— KHÔNG chạm Odoo thật (cùng khuôn tests/mcp/test_log_activity_tool.py)."""
import importlib.util
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
def close_fn(crm_mod):
    import server
    return server.mcp._tool_manager._tools["close_activity"].fn


@pytest.fixture(scope="module")
def security_mod():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    spec = importlib.util.spec_from_file_location(
        "_mcp_security_for_close_test", MCP_DIR / "security.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_action_feedback_nam_trong_allowlist(security_mod):
    """odoo_call.odoo() từ chối mọi method vắng mặt trong bảng này
    (deny-by-default). Thiếu dòng này thì close_activity chết ở lớp bảo mật
    của chính dự án, TRƯỚC khi chạm Odoo — và phép đo XML-RPC trong spec §1
    không thấy được, vì nó vòng qua lớp này."""
    assert security_mod.classify_operation("action_feedback") == "write"
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `pytest backend/tests/mcp/test_close_activity_tool.py -m "not integration and not live" -v`
Expected: FAIL — `close_activity` chưa có trong registry (fixture `close_fn`
lỗi `KeyError`) và `classify_operation("action_feedback")` trả `None`.

- [ ] **Step 3: Thêm `action_feedback` vào allowlist**

Trong `mcp-servers/odoo/security.py`, khối `# WRITE — Phase 3: cần confirmation`,
thêm ngay dưới dòng `"convert_opportunity": "write",`:

```python
    # mail.activity.action_feedback — đánh dấu việc hoàn tất. Đo 2026-08-14:
    # KHÔNG xoá bản ghi mà đặt active=False, state='done', date_done=<hôm nay>,
    # và ghi một tin vào chatter chứng từ. Nên đây là "write", không phải
    # "unlink".
    "action_feedback": "write",
```

- [ ] **Step 4: Viết test cho tool (đỏ trước)**

Thêm vào cuối `backend/tests/mcp/test_close_activity_tool.py`:

```python
def _fake_odoo(calls, *, rows=None):
    """rows = kết quả search_read mail.activity. Trả BẤT KỂ domain — để test
    bộ lọc phải khẳng định trên domain đã ghi lại, không dựa vào việc fake
    tình cờ trả rỗng."""
    rows = [{"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
             "res_name": "S00012"}] if rows is None else rows

    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        if method == "search_read":
            return rows
        return True

    return odoo


def test_dong_duoc_viec_cua_minh(crm_mod, close_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55, note="đã phát hành xong"))

    assert out["ok"] is True
    assert out["state"] == "done" and out["res_id"] == 55
    done = [c for c in calls if c[1] == "action_feedback"]
    assert len(done) == 1
    assert done[0][0] == "mail.activity"
    assert done[0][2] == [[55]]
    assert done[0][3]["feedback"] == "đã phát hành xong"


def test_bo_loc_user_id_co_mat_trong_domain(crm_mod, close_fn, monkeypatch):
    """Lớp cưỡng chế DUY NHẤT (spec §1.3). Gỡ leaf user_id ra khỏi domain thì
    test này PHẢI đỏ — đó là phép thử phá bắt buộc ở Step 8.

    Khẳng định trên DOMAIN chứ không trên kết quả: fake trả cùng một dòng bất
    kể domain, nên một test chỉ nhìn kết quả sẽ xanh cả khi bộ lọc biến mất."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    close_fn(55)

    reads = [c for c in calls if c[1] == "search_read"]
    assert len(reads) == 1
    domain = reads[0][2][0]
    assert ["user_id", "=", 10] in domain
    assert ["id", "=", 55] in domain


def test_khong_phai_viec_cua_minh_thi_tu_choi(crm_mod, close_fn, monkeypatch):
    """Việc của người khác và việc đã đóng dùng CHUNG một câu — tách ra sẽ để
    lộ việc của bộ phận khác có tồn tại hay không (spec §2.2)."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, rows=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))

    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "action_feedback"]


def test_note_rong_van_dong_duoc(crm_mod, close_fn, monkeypatch):
    """Lời nhắn là tuỳ chọn, nhưng chatter vẫn phải có gì đó để hiển thị."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))

    assert out["ok"] is True
    feedback = [c for c in calls if c[1] == "action_feedback"][0][3]["feedback"]
    assert feedback.strip(), "feedback rỗng — chatter sẽ không có gì để hiện"


def test_odoo_hong_thi_tra_loi_khong_vo(crm_mod, close_fn, monkeypatch):
    def odoo_error(model, method, args, kw=None):
        raise Exception("access-denied-detail: nhóm quyền XYZ")

    monkeypatch.setattr(crm_mod, "odoo", odoo_error)
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))
    assert out["ok"] is False
```

- [ ] **Step 5: Chạy để thấy nó đỏ**

Run: `pytest backend/tests/mcp/test_close_activity_tool.py -m "not integration and not live" -v`
Expected: `test_action_feedback_nam_trong_allowlist` PASS; năm test còn lại FAIL
vì `close_activity` chưa tồn tại.

- [ ] **Step 6: Viết tool**

Thêm vào cuối `mcp-servers/odoo/tools/crm.py`:

```python
@mcp.tool()
def close_activity(activity_id: int, note: str = "") -> str:
    """Đánh dấu MỘT việc (hoạt động/activity) đang được giao cho tài khoản hiện
    tại là ĐÃ HOÀN TẤT. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Chỉ đóng được việc giao cho CHÍNH tài khoản đang gọi. Đo trên Odoo thật
    2026-08-14: Odoo KHÔNG chặn một tài khoản đóng việc của người khác
    (ai-warehouse đóng trót lọt việc của ai-accounting), nên bộ lọc user_id
    dưới đây là lớp cưỡng chế DUY NHẤT — không được bỏ.

    Đóng việc KHÔNG xoá bản ghi: Odoo đặt active=False, state='done',
    date_done=<hôm nay>, và ghi một tin vào chatter của chứng từ kèm nguyên văn
    `note`. Thao tác hoàn tác được và có dấu vết.

    Args:
        activity_id: ID việc cần đóng (coordinator đã giải từ chứng từ).
        note: Lời nhắn ghi kèm, vào chatter chứng từ. Bỏ trống cũng được.
    """
    try:
        rows = odoo("mail.activity", "search_read",
                    [[["id", "=", activity_id], ["user_id", "=", get_uid()]]],
                    {"fields": ["id", "summary", "res_name"], "limit": 1})
        if not rows:
            # MỘT câu cho cả hai nguyên nhân (việc của người khác / đã đóng
            # rồi) — tách ra là để lộ việc của bộ phận khác có tồn tại không.
            return envelope(False, "Việc này không được giao cho bộ phận của "
                                   "bạn, hoặc đã đóng rồi.")
        act = rows[0]
        odoo("mail.activity", "action_feedback", [[activity_id]],
             {"feedback": note or "Đã hoàn tất."})
        what = act.get("summary") or f"việc #{activity_id}"
        where = act.get("res_name") or ""
        where_part = f" trên '{where}'" if where else ""
        return envelope(True, f"Đã đóng {what}{where_part}.",
                        ref=where or what, model="mail.activity",
                        res_id=activity_id, state="done")
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return envelope(False, f"Lỗi khi đóng việc: {e}")
```

- [ ] **Step 7: Chạy để thấy xanh**

Run: `pytest backend/tests/mcp/test_close_activity_tool.py -m "not integration and not live" -v`
Expected: 6 passed.

- [ ] **Step 8: Phép thử phá — BẮT BUỘC**

Tạm gỡ leaf `["user_id", "=", get_uid()]` khỏi domain trong `close_activity`,
chạy lại:

Run: `pytest backend/tests/mcp/test_close_activity_tool.py -m "not integration and not live" -v`
Expected: `test_bo_loc_user_id_co_mat_trong_domain` **FAIL**.

Nếu nó vẫn xanh thì test không đo gì — sửa test, không sửa kết luận. Khôi phục
leaf rồi chạy lại cho xanh trước khi commit. **Ghi kết quả thử phá vào báo cáo
task.**

- [ ] **Step 9: Chạy toàn bộ để chắc không thụt**

Run: `pytest -m "not integration and not live" -q`
Expected: ≥ 1393 passed (1387 nền + 6 test mới), 4 skipped.

- [ ] **Step 10: Commit**

```bash
git add mcp-servers/odoo/security.py mcp-servers/odoo/tools/crm.py backend/tests/mcp/test_close_activity_tool.py
git commit -m "feat(mcp): close_activity — đóng việc của chính tài khoản đang gọi"
```

---

## Task 2: Tool MCP `find_my_activities`

**Files:**
- Modify: `mcp-servers/odoo/tools/crm.py` (thêm `import json` ở đầu file + tool ở cuối)
- Test: `backend/tests/mcp/test_find_my_activities_tool.py` (tạo mới)

**Interfaces:**
- Consumes: `odoo`, `get_uid` (đã import sẵn trong `tools/crm.py`).
- Produces: tool MCP
  `find_my_activities(res_model: str = "", res_id: int = 0, limit: int = 20) -> str`.
  Trả JSON-string **shape riêng, KHÔNG phải `envelope`**:
  `{"ok": bool, "rows": [{"id", "summary", "res_model", "res_id", "res_name", "date_deadline"}, ...]}`.
  Lỗi → `{"ok": False, "rows": []}`.
  Task 3 parse đúng shape này.

**Vì sao không dùng `envelope`:** `helpers.envelope` chỉ có các khoá
`ok/ref/model/res_id/state/display` — không chở được danh sách dòng. Đây là tool
đọc trả nhiều dòng nên nó có shape riêng, khai rõ ở đây.

- [ ] **Step 1: Viết test (đỏ trước)**

Tạo `backend/tests/mcp/test_find_my_activities_tool.py`:

```python
"""find_my_activities — ứng viên cho coordinator đóng việc.

Lọc theo get_uid() (tài khoản Odoo đã xác thực của vai), KHÔNG theo một chuỗi
login suy ra từ tên vai: đây là cùng lớp cưỡng chế mà close_activity dựa vào.

"Đang mở" = active=True, và Odoo lọc như vậy theo MẶC ĐỊNH. Đo 2026-08-14:
action_feedback đặt active=False chứ KHÔNG xoá bản ghi (spec §1.1), nên truyền
active_test=False ở đây sẽ lôi cả việc đã đóng vào danh sách ứng viên và cho
phép đóng lại một việc đã xong."""
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
        import server  # noqa: F401
    finally:
        sys.path.remove(str(MCP_DIR))
    return sys.modules["tools.crm"]


@pytest.fixture(scope="module")
def find_fn(crm_mod):
    import server
    return server.mcp._tool_manager._tools["find_my_activities"].fn


ROW = {"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
       "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
       "date_deadline": "2026-08-20"}


def _fake_odoo(calls, rows=(ROW,)):
    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        return list(rows)

    return odoo


def test_luon_loc_theo_tai_khoan_dang_goi(crm_mod, find_fn, monkeypatch):
    """Phép thử phá nhắm vào test này: gỡ leaf user_id thì nó phải đỏ."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    domain = calls[0][2][0]
    assert ["user_id", "=", 10] in domain


def test_khong_truyen_active_test_false(crm_mod, find_fn, monkeypatch):
    """Việc đã đóng vẫn CÒN bản ghi (chỉ active=False). Truyền active_test=False
    sẽ cho đóng lại một việc đã xong."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    kw = calls[0][3] or {}
    assert "active_test" not in json.dumps(kw)


def test_loc_them_theo_chung_tu_khi_duoc_neu(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn(res_model="sale.order", res_id=12)

    domain = calls[0][2][0]
    assert ["res_model", "=", "sale.order"] in domain
    assert ["res_id", "=", 12] in domain


def test_khong_neu_chung_tu_thi_khong_loc_theo_chung_tu(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    domain = calls[0][2][0]
    assert not [leaf for leaf in domain if leaf[0] in ("res_model", "res_id")]


def test_tra_ve_du_truong_de_hien_thi_va_chon(crm_mod, find_fn, monkeypatch):
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo([]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(find_fn())

    assert out["ok"] is True
    row = out["rows"][0]
    for field in ("id", "summary", "res_name", "date_deadline"):
        assert field in row


def test_sap_theo_han_gan_nhat_truoc(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    assert "date_deadline" in (calls[0][3] or {}).get("order", "")


def test_odoo_hong_thi_tra_ok_false_khong_vo(crm_mod, find_fn, monkeypatch):
    def odoo_error(*a, **k):
        raise Exception("Odoo sập")

    monkeypatch.setattr(crm_mod, "odoo", odoo_error)
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(find_fn())
    assert out["ok"] is False and out["rows"] == []
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `pytest backend/tests/mcp/test_find_my_activities_tool.py -m "not integration and not live" -v`
Expected: FAIL — `KeyError: 'find_my_activities'` ở fixture.

- [ ] **Step 3: Viết tool**

Thêm `import json` vào đầu `mcp-servers/odoo/tools/crm.py` (ngay trên
`from server import mcp`), rồi thêm tool vào cuối file:

```python
@mcp.tool()
def find_my_activities(res_model: str = "", res_id: int = 0,
                       limit: int = 20) -> str:
    """Các việc (hoạt động/activity) ĐANG MỞ được giao cho tài khoản hiện tại,
    hạn gần nhất trước. Bỏ trống res_model/res_id = mọi chứng từ.

    Tool này phục vụ coordinator đóng việc (nó cần danh sách ứng viên trước khi
    hỏi người dùng chọn). Đường tra cứu của NGƯỜI DÙNG là list_my_activities ở
    tầng backend, không phải tool này.

    Lọc theo get_uid() — tài khoản Odoo đã xác thực của vai — chứ không theo
    một chuỗi login suy ra từ tên vai.

    "Đang mở" = active=True; Odoo lọc như vậy theo mặc định nên domain không
    cần điều kiện gì thêm. KHÔNG truyền active_test=False: đo 2026-08-14 cho
    thấy việc đã đóng vẫn CÒN bản ghi (active=False, state='done'), nên bật
    active_test=False sẽ cho phép đóng lại một việc đã xong.

    Args:
        res_model: Lọc theo model chứng từ, vd "sale.order". Bỏ trống = mọi model.
        res_id: Lọc theo ID chứng từ. Bỏ trống/0 = mọi chứng từ.
        limit: Số dòng tối đa.
    """
    try:
        domain = [["user_id", "=", get_uid()]]
        if str(res_model or "").strip():
            domain.append(["res_model", "=", res_model])
        if res_id:
            domain.append(["res_id", "=", res_id])
        rows = odoo("mail.activity", "search_read", [domain],
                    {"fields": ["id", "summary", "res_model", "res_id",
                                "res_name", "date_deadline"],
                     "order": "date_deadline asc", "limit": limit})
        return json.dumps({"ok": True, "rows": rows}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return json.dumps({"ok": False, "rows": [],
                           "display": f"Lỗi khi tra việc được giao: {e}"},
                          ensure_ascii=False)
```

- [ ] **Step 4: Chạy để thấy xanh**

Run: `pytest backend/tests/mcp/test_find_my_activities_tool.py -m "not integration and not live" -v`
Expected: 7 passed.

- [ ] **Step 5: Phép thử phá — BẮT BUỘC**

Tạm đổi `domain = [["user_id", "=", get_uid()]]` thành `domain = []`, chạy lại:

Run: `pytest backend/tests/mcp/test_find_my_activities_tool.py -m "not integration and not live" -v`
Expected: `test_luon_loc_theo_tai_khoan_dang_goi` **FAIL**.

Khôi phục rồi chạy lại cho xanh. **Ghi kết quả thử phá vào báo cáo task.**

- [ ] **Step 6: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: ≥ 1400 passed (1393 + 7 test mới), 4 skipped.

- [ ] **Step 7: Commit**

```bash
git add mcp-servers/odoo/tools/crm.py backend/tests/mcp/test_find_my_activities_tool.py
git commit -m "feat(mcp): find_my_activities — ứng viên cho coordinator đóng việc"
```

---

## Task 3: Coordinator `make_close_activity_node`

**Files:**
- Modify: `backend/src/agents/crm_write.py` (thêm `import json` + 2 helper + 1 hàm dựng node)
- Test: `backend/tests/agents/test_close_activity_node.py` (tạo mới)

**Interfaces:**
- Consumes:
  - tool MCP `find_my_activities(res_model: str, res_id: int)` → JSON-string
    `{"ok": bool, "rows": [...]}` (Task 2);
  - tool MCP `close_activity(activity_id: int, note: str)` → JSON-string
    `envelope` (Task 1);
  - có sẵn trong `crm_write.py`: `_resolve_doc`, `_msg`, `_finish`,
    `_ttl_expiry`, `_disambig_q`, `WRITE_DISABLED_MSG`, `write_gate`,
    `WRITE_CONFIRM_SUFFIX`, `_interrupt`.
- Produces: `make_close_activity_node(tools) -> node` — chữ ký **giống hệt**
  `make_log_activity_node(tools)`, để Task 4 đăng ký được bằng
  `lambda llm, tools: make_close_activity_node(tools)`.

**Hai điều KHÔNG được làm:**

1. **Không nhận `role_cfg`.** `Spec.build` là `(llm, tools) -> node` cho cả 24
   coordinator; đổi hợp đồng đó để phục vụ một tính năng là bán kính ảnh hưởng
   quá lớn. Danh tính đã được cưỡng chế bằng `get_uid()` ở tầng MCP (Task 1, 2)
   — đúng chỗ duy nhất có tài khoản đã xác thực.
2. **Không tự viết đường tra Odoo thứ hai** trong `erp_query`. `find_my_activities`
   là đường duy nhất, dùng cho cả hai nhánh (có chứng từ / không có).

- [ ] **Step 1: Viết test (đỏ trước)**

Tạo `backend/tests/agents/test_close_activity_node.py`:

```python
"""Coordinator đóng việc — hai nhánh vào (có chứng từ / không), hỏi lại khi
trùng, cổng xác nhận.

Toàn bộ tool đều là tool GIẢ: coordinator không được chạm Odoo thật. Vòng
trước có một test gọi Odoo thật vì thiếu điểm tiêm, và nghiệm thu sống tạo
đúng bản ghi đó khiến 3 test đỏ như một hồi quy bí ẩn."""
import json

import pytest
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.state import ERPAgentState
import src.agents.crm_write as cw
from src.agents import write_gate

ROW_A = {"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
         "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
         "date_deadline": "2026-08-20"}
ROW_B = {"id": 56, "summary": "Kho đề nghị: ghi nhận thanh toán",
         "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
         "date_deadline": "2026-08-21"}


def _finder(rows, recorder):
    t = MagicMock()
    t.name = "find_my_activities"

    async def ainvoke(args):
        recorder.setdefault("find", []).append(args)
        return json.dumps({"ok": True, "rows": list(rows)}, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def _broken_finder():
    t = MagicMock()
    t.name = "find_my_activities"

    async def ainvoke(args):
        return json.dumps({"ok": False, "rows": []})

    t.ainvoke = ainvoke
    return t


def _closer(recorder):
    t = MagicMock()
    t.name = "close_activity"

    async def ainvoke(args):
        recorder["close"] = args
        return json.dumps({"ok": True, "ref": "S00012", "model": "mail.activity",
                           "res_id": args["activity_id"], "state": "done",
                           "display": "Đã đóng việc."}, ensure_ascii=False)

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
            "pending_action": {"tool": "close_activity", "args": args,
                               "summary": "đóng việc"}}


def _node(rows, recorder):
    return cw.make_close_activity_node([_finder(rows, recorder), _closer(recorder)])


@pytest.fixture(autouse=True)
def _write_on(monkeypatch):
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)


@pytest.fixture(autouse=True)
def _no_real_odoo(monkeypatch):
    """_resolve_doc đi qua _search_by_name; chặn cứng để không test nào lỡ ra
    Odoo thật."""
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda model, domain, fields, **kw: [{"id": 12, "name": "S00012"}])


@pytest.mark.asyncio
async def test_mot_viec_tren_chung_tu_thi_hoi_xac_nhan_roi_dong():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca1"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012", "note": "xong"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"
    question = res["__interrupt__"][0].value["question"]
    assert "S00012" in question and "phát hành hóa đơn" in question
    assert "2026-08-20" in question

    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"] == {"activity_id": 55, "note": "xong"}
    assert rec["find"][0]["res_model"] == "sale.order"
    assert rec["find"][0]["res_id"] == 12


@pytest.mark.asyncio
async def test_huy_o_cong_xac_nhan_thi_khong_goi_tool():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca2"}}
    await graph.ainvoke(_state({"res_model": "sale.order", "ref": "S00012"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)

    assert "close" not in rec
    assert "hủy" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_khong_co_viec_nao_tren_chung_tu_thi_noi_ro():
    rec = {}
    graph = _graph(_node([], rec))
    cfg = {"configurable": {"thread_id": "ca3"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert "__interrupt__" not in res
    assert "S00012" in res["messages"][-1].content
    assert "close" not in rec


@pytest.mark.asyncio
async def test_nhieu_viec_thi_hoi_chon_truoc_khi_xac_nhan():
    rec = {}
    graph = _graph(_node([ROW_A, ROW_B], rec))
    cfg = {"configurable": {"thread_id": "ca4"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    res = await graph.ainvoke(Command(resume=56), cfg)
    assert res["__interrupt__"][0].value["kind"] == "confirm"
    assert "ghi nhận thanh toán" in res["__interrupt__"][0].value["question"]

    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"]["activity_id"] == 56


@pytest.mark.asyncio
async def test_khong_neu_chung_tu_thi_liet_ke_chu_khong_doi_ma():
    """Đây là đường lui chủ dự án chốt: câu "xong việc rồi" ngay sau khi vừa
    xem danh sách là cách nói tự nhiên nhất, không được chặn lại để đòi mã."""
    rec = {}
    graph = _graph(_node([ROW_A, ROW_B], rec))
    cfg = {"configurable": {"thread_id": "ca5"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "disambiguation"
    assert rec["find"][0]["res_model"] == ""
    assert rec["find"][0]["res_id"] == 0


@pytest.mark.asyncio
async def test_khong_neu_chung_tu_va_chi_co_mot_viec_thi_di_thang_toi_xac_nhan():
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca6"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"


@pytest.mark.asyncio
async def test_khong_co_viec_nao_ca_thi_noi_ro():
    rec = {}
    graph = _graph(_node([], rec))
    cfg = {"configurable": {"thread_id": "ca7"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert "__interrupt__" not in res
    assert "không có việc" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_tra_ung_vien_hong_thi_khong_dong_bua():
    """ok=False từ tool tra cứu KHÔNG được hiểu thành "không có việc nào" —
    hai chuyện đó khác nhau, và nhầm chúng sẽ báo sai sự thật cho người dùng."""
    rec = {}
    node = cw.make_close_activity_node([_broken_finder(), _closer(rec)])
    graph = _graph(node)
    cfg = {"configurable": {"thread_id": "ca8"}}
    res = await graph.ainvoke(_state({}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec
    assert "không tra được" in res["messages"][-1].content.lower()


@pytest.mark.asyncio
async def test_chung_tu_khong_giai_duoc_thi_dung_lai(monkeypatch):
    rec = {}
    monkeypatch.setattr(cw, "_search_by_name",
                        lambda model, domain, fields, **kw: [])
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca9"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S99999"}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec
    assert "find" not in rec


@pytest.mark.asyncio
async def test_write_gate_tat_thi_khong_lam_gi(monkeypatch):
    """monkeypatch ở đây ĐÈ LÊN fixture _write_on (fixture chạy trước), và vẫn
    được gỡ đúng cách sau test — khác hẳn việc gán thẳng vào module."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: False)
    rec = {}
    graph = _graph(_node([ROW_A], rec))
    cfg = {"configurable": {"thread_id": "ca10"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert "__interrupt__" not in res
    assert "close" not in rec and "find" not in rec


@pytest.mark.asyncio
async def test_dong_duoc_ca_viec_khong_phai_ban_giao():
    """Spec §2.4: KHÔNG lọc theo HANDOFF_MARKER. Một việc do chính vai tự đặt
    (log_activity không có assignee) cũng là việc của vai đó và cũng phải đóng
    được. Giới hạn vào riêng việc bàn giao là ranh giới nhân tạo."""
    rec = {}
    tu_dat = {"id": 57, "summary": "Kiểm lại tồn kho cuối tháng",
              "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
              "date_deadline": "2026-08-22"}
    graph = _graph(_node([tu_dat], rec))
    cfg = {"configurable": {"thread_id": "ca11"}}
    res = await graph.ainvoke(
        _state({"res_model": "sale.order", "ref": "S00012"}), cfg)

    assert res["__interrupt__"][0].value["kind"] == "confirm"
    await graph.ainvoke(Command(resume=True), cfg)
    assert rec["close"]["activity_id"] == 57
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `pytest backend/tests/agents/test_close_activity_node.py -m "not integration and not live" -v`
Expected: FAIL — `AttributeError: module 'src.agents.crm_write' has no attribute 'make_close_activity_node'`.

- [ ] **Step 3: Viết helper**

Thêm `import json` vào đầu `backend/src/agents/crm_write.py` (ngay trên
`from datetime import date`), rồi thêm hai helper ngay trên
`def make_log_activity_node(tools):`:

```python
def _activity_label(row) -> str:
    """Một dòng cho menu hỏi lại — đủ để phân biệt hai việc trên CÙNG chứng từ,
    nên nội dung việc phải có mặt, không chỉ mã chứng từ."""
    where = row.get("res_name") or row.get("res_model") or "—"
    what = row.get("summary") or "(không có mô tả)"
    return f"{where}: {what} (hạn {row.get('date_deadline') or 'chưa đặt'})"


async def _my_open_activities(finder, res_model: str, res_id: int):
    """Ứng viên đóng việc → list[row], hoặc None khi TRA HỎNG.

    None và [] KHÔNG được gộp: "tra hỏng" và "không có việc nào" là hai sự thật
    khác nhau, và nói nhầm cái sau khi gặp cái trước là báo sai cho người dùng.
    """
    try:
        raw = await finder.ainvoke({"res_model": res_model, "res_id": res_id})
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 — never crash the graph
        return None
    if not data.get("ok"):
        return None
    return data.get("rows") or []
```

- [ ] **Step 4: Viết node**

Thêm vào cuối `backend/src/agents/crm_write.py`:

```python
def make_close_activity_node(tools):
    """Đóng MỘT việc được giao cho bộ phận đang gọi.

    Danh tính KHÔNG được cưỡng chế ở đây: cả hai tool MCP lọc theo get_uid(),
    tài khoản Odoo đã xác thực của vai. Đó là lý do node này không cần role_cfg,
    và cũng là lý do KHÔNG được thêm một đường tra Odoo thứ hai ở tầng backend
    (nó sẽ lọc theo một chuỗi login suy diễn, yếu hơn hẳn).
    """
    by_name = {t.name: t for t in tools}

    async def close_activity_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        res_model = str(args.get("res_model") or "").strip()
        ref = str(args.get("ref") or "").strip()
        note = str(args.get("note") or "").strip()

        finder = by_name.get("find_my_activities")
        closer = by_name.get("close_activity")
        if finder is None or closer is None:
            return _msg("Công cụ đóng việc không khả dụng.")

        if res_model and ref:
            kind, doc = _resolve_doc(res_model, ref)
            if kind == "msg":
                return doc
            rows = await _my_open_activities(finder, res_model, doc["id"])
            empty_msg = (f"Không có việc nào của bộ phận bạn đang mở trên "
                         f"'{doc['name']}'.")
        else:
            rows = await _my_open_activities(finder, "", 0)
            empty_msg = "Hiện không có việc nào được giao cho bạn."

        if rows is None:
            return _msg("Không tra được danh sách việc được giao. "
                        "Vui lòng thử lại.")
        if not rows:
            return _msg(empty_msg)

        if len(rows) == 1:
            act = rows[0]
        else:
            options = [{"id": r["id"], "name": _activity_label(r)} for r in rows]
            chosen = _interrupt({"kind": "disambiguation",
                                 "question": _disambig_q("việc đang mở", options),
                                 "options": options, "expires_at": _ttl_expiry()})
            act = next((r for r in rows if r["id"] == chosen), None)
            if act is None:
                return _msg("Đã hủy.")

        confirmed = _interrupt({
            "kind": "confirm",
            "question": (f"Đánh dấu hoàn tất việc "
                         f"'{act.get('summary') or '(không có mô tả)'}' trên "
                         f"'{act.get('res_name') or '—'}' "
                         f"(hạn {act.get('date_deadline') or 'chưa đặt'}).\n"
                         + WRITE_CONFIRM_SUFFIX),
            "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy đóng việc.")

        try:
            result = await closer.ainvoke({"activity_id": act["id"], "note": note})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi đóng việc: {e}")
        return _finish("close_activity", result)

    return close_activity_node
```

- [ ] **Step 5: Chạy để thấy xanh**

Run: `pytest backend/tests/agents/test_close_activity_node.py -m "not integration and not live" -v`
Expected: 11 passed.

- [ ] **Step 6: Phép thử phá — BẮT BUỘC**

Tạm đổi `if rows is None:` thành `if False:` (gộp "tra hỏng" vào "không có việc
nào"), chạy lại:

Run: `pytest backend/tests/agents/test_close_activity_node.py -m "not integration and not live" -v`
Expected: `test_tra_ung_vien_hong_thi_khong_dong_bua` **FAIL**.

Khôi phục rồi chạy lại cho xanh. **Ghi kết quả thử phá vào báo cáo task.**

- [ ] **Step 7: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: ≥ 1411 passed (1400 + 11 test mới), 4 skipped.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/crm_write.py backend/tests/agents/test_close_activity_node.py
git commit -m "feat(agents): coordinator đóng việc — theo chứng từ, có đường lui liệt kê"
```

---

## Task 4: Đăng ký — registry, vai, bộ phận, bảng bàn giao, prompt planner, bảng quyền

**Files:**
- Modify: `backend/src/agents/write_registry.py`
- Modify: `backend/src/agents/roles.py`
- Modify: `backend/src/agents/handoff.py`
- Modify: `backend/src/agents/prompts.py`
- Modify: `scripts/check_role_odoo_consistency.py`
- Test: `backend/tests/agents/test_close_activity_roles.py` (tạo mới)

**Interfaces:**
- Consumes: `make_close_activity_node(tools)` từ Task 3; tool MCP
  `find_my_activities` từ Task 2.
- Produces: `close_activity` là một coordinated write tool đầy đủ — planner nêu
  được tên nó, guard vai cho qua, graph có node cho nó.

**Bốn lưới đỡ SẼ ĐỎ nếu bỏ sót một mục — đây là tính năng, không phải phiền
toái. Task này phải làm đủ cả năm chỗ khai báo:**

1. `test_dept_of.py::test_moi_tool_duoc_so_huu_deu_co_bo_phan` — tool được
   `own` mà thiếu `DEPT_OF` → đỏ.
2. `test_handoff.py` — mọi tool trong `DEPT_OF` phải nằm trong `HANDOFF_DOC_OF`
   **hoặc** `NO_DOCUMENT_TOOLS` → thiếu là đỏ.
3. `test_tool_access_map_drift.py::test_moi_tool_trong_roles_deu_duoc_bang_phu`
   — tool khai trong `roles.py` mà thiếu `TOOL_ACCESS_MAP` → đỏ.
4. `test_tool_access_map_drift.py::test_model_khai_deu_co_that_trong_nguon_tool`
   — model khai trong `TOOL_ACCESS_MAP` phải thật sự xuất hiện trong lệnh
   `odoo(...)` của hàm cùng tên trong `mcp-servers/odoo` → khai bừa là đỏ.

- [ ] **Step 1: Viết test (đỏ trước)**

Tạo `backend/tests/agents/test_close_activity_roles.py`:

```python
"""close_activity được cấp cho cả hai vai non-admin, ở CẢ HAI hồ sơ.

Thêm một tool vào `own` nghĩa là scripts/odoo_setup_ai_accounts.py sinh ra bộ
nhóm quyền Odoo khác trước, nên thay đổi này phải được khoá bằng test chứ không
để nó âm thầm (cùng lý do test_log_activity_roles.py tồn tại)."""
import importlib.util
import pathlib
import sys

from src.agents import handoff, prompts, roles, write_registry

REPO = pathlib.Path(__file__).resolve().parents[3]
CHECK = REPO / "scripts" / "check_role_odoo_consistency.py"


def test_ca_hai_vai_deu_so_huu_close_activity():
    for profile_name, profile in roles.PROFILES.items():
        for role_name in ("warehouse", "accounting"):
            cfg = profile[role_name]
            assert cfg.state_of("close_activity") == roles.OWN, (
                f"{profile_name}/{role_name} không sở hữu close_activity")
            assert "close_activity" in cfg.allowed_tools()


def test_close_activity_co_trong_dept_of():
    assert "close_activity" in roles.DEPT_OF


def test_close_activity_khong_co_chung_tu_de_ban_giao():
    """Nó tác động lên MỘT activity, không lên một chứng từ — và cả hai vai đều
    sở hữu nên không bao giờ phát sinh bàn giao. Phải nằm ở NO_DOCUMENT_TOOLS,
    không phải HANDOFF_DOC_OF."""
    assert "close_activity" in handoff.NO_DOCUMENT_TOOLS
    assert "close_activity" not in handoff.HANDOFF_DOC_OF


def test_dang_ky_coordinator_kem_dep_tra_ung_vien():
    spec = write_registry.WRITE_COORDINATORS["close_activity"]
    assert spec.node == "crm_close_activity"
    assert "find_my_activities" in spec.deps, (
        "thiếu dep thì coordinator không có tool tra ứng viên — nhánh liệt kê "
        "im lặng chết trong production dù test dùng tool giả vẫn xanh")


def test_dep_tra_ung_vien_khong_lot_vao_danh_sach_planner():
    """deps CHỈ được thêm cho coordinator. Lọt vào danh sách planner-visible là
    mở đúng lỗ hổng mà cơ chế deps đi bịt: LLM gọi thẳng tool tra cứu, bỏ qua
    coordinator và cổng xác nhận."""
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            allowed = cfg.allowed_tools()
            if allowed is None:
                continue
            assert "find_my_activities" not in allowed


def test_planner_biet_ten_tool():
    assert "close_activity(" in prompts.WRITE_PLANNER_PROMPT


def test_bang_quyen_odoo_co_dong_cho_close_activity():
    spec = importlib.util.spec_from_file_location(
        "_check_role_for_close_test", CHECK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert "close_activity" in mod.TOOL_ACCESS_MAP
    assert ("mail.activity", "write") in mod.TOOL_ACCESS_MAP["close_activity"]
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `pytest backend/tests/agents/test_close_activity_roles.py -m "not integration and not live" -v`
Expected: 7 FAIL.

- [ ] **Step 3: Đăng ký coordinator**

Trong `backend/src/agents/write_registry.py`, sửa dòng import CRM:

```python
from .crm_write import (make_create_lead_node, make_convert_lead_node,
                        make_log_activity_node, make_close_activity_node)
```

Rồi thêm vào `WRITE_COORDINATORS`, ngay dưới dòng `"log_activity"`:

```python
    # deps: coordinator cần tool tra ứng viên, nhưng tool đó KHÔNG được vào
    # danh sách planner nhìn thấy (khuôn MAIL_DEPS) — nếu không, LLM sẽ gọi
    # thẳng nó và bỏ qua cổng xác nhận.
    "close_activity": Spec("crm_close_activity",
                           lambda llm, tools: make_close_activity_node(tools),
                           frozenset({"find_my_activities"})),
```

- [ ] **Step 4: Khai bộ phận và cấp cho hai vai**

Trong `backend/src/agents/roles.py`, thêm vào `DEPT_OF` ngay dưới mục
`"log_activity": "Kho",`:

```python
    # Cùng lý do và cùng cảnh báo như log_activity ngay trên: cả hai vai
    # non-admin đều `own` nên other_dept không bao giờ chỉ sang đâu cho tool
    # này, và giá trị "Kho" là TUỲ TIỆN. Nó chỉ bắt đầu có nghĩa nếu sau này
    # có một vai KHÔNG sở hữu close_activity — lúc đó phải xem lại.
    "close_activity": "Kho",
```

Thêm `"close_activity"` vào cả ba tập:

```python
_WH_OWN = frozenset({
    "deliver_order", "receive_order", "validate_picking", "internal_transfer",
    "inventory_adjustment", "scrap_product", "flag_order_for_review",
    "log_activity", "close_activity",
})
```

```python
_ACC_OWN = frozenset({
    "create_credit_memo", "send_invoice_email", "create_invoice_from_order",
    "create_bill_from_po", "log_activity", "close_activity",
})
```

và trong `PROFILES["enterprise"]["warehouse"]`:

```python
            own=frozenset({"deliver_order", "receive_order", "validate_picking",
                           "internal_transfer", "log_activity",
                           "close_activity"}),
```

- [ ] **Step 5: Khai vào bảng bàn giao**

Trong `backend/src/agents/handoff.py`, thêm `"close_activity"` vào
`NO_DOCUMENT_TOOLS`:

```python
NO_DOCUMENT_TOOLS: frozenset[str] = frozenset({
    "post_invoice", "create_quotation", "create_rfq",
    "inventory_adjustment", "internal_transfer", "scrap_product",
    "log_activity", "flag_order_for_review", "close_activity"})
```

- [ ] **Step 6: Cho planner biết tên tool**

Trong `backend/src/agents/prompts.py`, `WRITE_PLANNER_PROMPT`, thêm ngay dưới
dòng `- log_activity(...)`:

```
- close_activity(res_model: str = null, ref: str = null, note: str = null)  # đánh dấu MỘT việc đang được giao cho bộ phận mình là ĐÃ XONG/hoàn tất, vd "việc trên đơn S00012 xong rồi", "đã làm xong việc kế toán chuyển sang"; res_model + ref là chứng từ việc đó gắn vào (cùng giá trị như log_activity); BỎ TRỐNG CẢ HAI nếu người dùng không nêu chứng từ — hệ thống sẽ liệt kê việc đang mở để chọn; note là lời nhắn ghi kèm (tùy chọn)
```

- [ ] **Step 7: Khai vào bảng quyền Odoo**

Trong `scripts/check_role_odoo_consistency.py`, `TOOL_ACCESS_MAP`, thêm ngay
dưới dòng `"log_activity"`:

```python
    # action_feedback đặt active=False + state='done' trên chính bản ghi
    # mail.activity (đo 2026-08-14) — là "write", không phải "unlink".
    "close_activity":          [("mail.activity", "write")],  # crm.py close_activity
```

- [ ] **Step 8: Chạy test của task này**

Run: `pytest backend/tests/agents/test_close_activity_roles.py -m "not integration and not live" -v`
Expected: 7 passed.

- [ ] **Step 9: Chạy các lưới đỡ liên quan**

Run: `pytest backend/tests/agents/test_dept_of.py backend/tests/agents/test_handoff.py backend/tests/mcp/test_tool_access_map_drift.py -m "not integration and not live" -v`
Expected: tất cả PASS.

Nếu `test_model_khai_deu_co_that_trong_nguon_tool` đỏ với thông điệp
*"close_activity: khai model 'mail.activity' nhưng nguồn không gọi
odoo('mail.activity', ...)"* thì lỗi nằm ở Task 1 (tool không gọi Odoo bằng
model đó), không phải ở bảng — báo cáo lại, đừng sửa bảng cho hết đỏ.

- [ ] **Step 10: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: ≥ 1418 passed (1411 + 7 test mới), 4 skipped.

- [ ] **Step 11: Commit**

```bash
git add backend/src/agents/write_registry.py backend/src/agents/roles.py backend/src/agents/handoff.py backend/src/agents/prompts.py scripts/check_role_odoo_consistency.py backend/tests/agents/test_close_activity_roles.py
git commit -m "feat(roles): cấp close_activity cho hai vai, đăng ký coordinator và bảng quyền"
```

---

## Task 5: Sửa chú thích sai về hành vi unlink

**Files:**
- Modify: `backend/src/erp_query/crm.py:57-89` (docstring `list_my_activities`)

**Interfaces:**
- Consumes: không.
- Produces: không. **Chỉ sửa chú thích — KHÔNG đổi một dòng code nào.**

**Vì sao đây là một task chứ không phải dọn dẹp vặt:** chú thích hiện tại khẳng
định một điều đã được đo là SAI. Kết luận của nó (không cần điều kiện lọc nào
thêm) vẫn đúng, nhưng **đúng vì một lý do khác**. Để nguyên thì người sau sẽ
dựa vào nó mà suy ra điều sai — ví dụ "đóng việc là mất dữ liệu, phải sao lưu
trước", hoặc "muốn xem việc đã đóng thì chịu".

- [ ] **Step 1: Sửa chú thích**

Trong `backend/src/erp_query/crm.py`, thay đúng đoạn cuối docstring
`list_my_activities`:

```python
    mail.activity bản chất là việc CHƯA xong — Odoo unlink bản ghi khi đánh dấu
    hoàn tất — nên không cần điều kiện "đang mở" nào thêm."""
```

bằng:

```python
    Không cần điều kiện "đang mở" nào thêm, nhưng KHÔNG phải vì lý do trước đây
    ghi ở đây. Đo trên Odoo 19 thật (2026-08-14): đánh dấu hoàn tất KHÔNG unlink
    bản ghi — nó đặt active=False, state='done', date_done=<hôm nay>, và bản ghi
    vẫn đọc lại được qua context={"active_test": False}. Lý do thật là Odoo tự
    lọc active=True theo mặc định.

    Hệ quả cho người đọc sau: việc đã đóng là dữ liệu CÒN, hoàn tác được và tra
    lại được — đừng suy ra rằng đóng việc là mất dữ liệu.

    Cách phân biệt khi đo lại: mail.activity CÓ field active, nên một bản ghi bị
    lưu trữ biến mất khỏi search mặc định y hệt một bản ghi bị xoá. Phải đo với
    active_test=False mới tách được hai trường hợp."""
```

- [ ] **Step 2: Chạy test của file đó**

Run: `pytest backend/tests/erp_query/test_my_activities.py -m "not integration and not live" -v`
Expected: 5 passed — hành vi không đổi vì không có dòng code nào bị đụng.

- [ ] **Step 3: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: ≥ 1418 passed, 4 skipped — **không đổi so với Task 4**, vì task này
không thêm test và không đụng dòng code nào.

- [ ] **Step 4: Commit**

```bash
git add backend/src/erp_query/crm.py
git commit -m "docs(erp_query): sửa chú thích sai — đóng activity là lưu trữ, không xoá"
```

---

## Nghiệm thu sống — controller làm, TRƯỚC merge

**Không thuộc task nào. Implementer KHÔNG chạm vào phần này** (ràng buộc "không
chạm hạ tầng sống"). Ghi ở đây để plan tự chứa đủ.

Chạy trên worktree của nhánh, không phải trên `main`.

| # | kịch bản | vai | kỳ vọng |
|---|---|---|---|
| 1 | *"có việc gì chuyển cho tôi không?"* | kế toán | thấy việc bàn giao (nửa đọc vẫn chạy) |
| 2 | *"việc trên đơn S00012 xong rồi"* | kế toán | hỏi xác nhận → đóng → Odoo `state='done'` |
| 3 | hỏi lại #1 | kế toán | việc đó **biến mất** khỏi danh sách |
| 4 | *"xong việc rồi"* (không nêu chứng từ) | kế toán | liệt kê rồi hỏi chọn |
| 5 | xin đóng một việc giao cho kế toán | kho | từ chối, **và bản ghi Odoo còn nguyên** |
| 6 | ≥5 cách diễn đạt của "xong rồi" | kế toán | đo tỉ lệ tới được planner |

\#3 và #5 là hai phép đo **quyết định**. #5 phải kiểm bằng cách **đọc trạng thái
Odoo sau đó** — một câu từ chối hiện ra không chứng minh bản ghi còn nguyên.

\#6 là rủi ro spec §4: `INTENT_ROUTER_PROMPT` có luật *"khi phân vân
erp_read/erp_write thì chọn erp_read"*, và mô tả `erp_read` vừa được thêm cụm
"việc của tôi" ở vòng trước. **Không sửa prompt router trước khi đo.** Nếu đo
được là cửa đóng thì mới sửa, và phải chạy lại **cả hai** cổng eval `intent` và
`sop_select` (`eval_gate.ROLE_FOR_SET` ánh xạ cả hai vào vai `router`), rồi ghi
lại giá phải trả — bản sửa tương tự vòng trước tốn 1 ca eval
(`intent` 0.9630 → 0.9444, vẫn ≥ baseline 0.8704).
