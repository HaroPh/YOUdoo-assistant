# Cưỡng chế vai cho tầng mail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khôi phục năng lực gửi mail cho hai vai non-admin (hiện đang chết hoàn toàn), đóng hạng lỗi "phụ thuộc nội bộ không khai báo", và thêm một tầng cưỡng chế dưới tầng agent cho 4 tool gửi mail.

**Architecture:** `Spec` khai `deps` tường minh; graph truyền cho hàm dựng node coordinator một danh sách tool RIÊNG (đã lọc + deps), tách khỏi danh sách planner-visible. Allowlist template được **suy ra** từ `roles.py × EmailCfg` và truyền vào tiến trình MCP qua env; tiến trình MCP tự cưỡng chế. Cuối cùng đo `ir.rule` phía Odoo để xem có giữ được lớp thứ ba không.

**Tech Stack:** Python 3.11, LangGraph, FastMCP, Odoo 19 XML-RPC, pytest, PowerShell 5.1.

**Spec:** `docs/superpowers/specs/2026-08-12-mail-role-enforcement-design.md`

## Global Constraints

- **Ngôn ngữ:** comment và chuỗi hiển thị bằng tiếng Việt, theo đúng lối viết các file xung quanh. Tên hàm/biến tiếng Anh.
- **Không hồi quy:** `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"` phải giữ **1254 passed, 4 skipped, 46 deselected** cộng các test mới. Đây là chuẩn đã đo, không phải ước lượng.
- **Hai danh sách tool là bất biến bảo mật.** `preview_template_email`, `send_prepared_email`, `discard_prepared_email` KHÔNG được lọt vào danh sách truyền cho planner / `erp_write_executor` / node SOP. Chỉ hàm dựng node coordinator được thấy chúng. Vi phạm điều này là mở đúng lỗ hổng plan đang đi bịt.
- **Fail-open cho test:** `tools_for_coordinator(spec, tools, mcp_all_tools=None)` trả `tools` nguyên vẹn. Hàng trăm test hiện có dựng graph không truyền `mcp_all_tools`; raise ở đó sẽ làm đỏ diện rộng mà không bắt được lỗi thật nào.
- **Env rỗng = không giới hạn.** `MCP_ALLOWED_TEMPLATES` / `MCP_ALLOWED_MAIL_MODELS` không đặt hoặc rỗng thì MCP không chặn gì — tiến trình admin và mọi test MCP hiện có giữ nguyên hành vi.
- **Không hardcode id Odoo.** Tra template theo `name`.
- **Không có giá trị mật khẩu thật trong file được git theo dõi.**
- **Subagent KHÔNG được khởi động/dừng/khởi động lại tiến trình hay container, và KHÔNG chạy verify sống.** Toàn bộ việc chạm hạ tầng sống do controller làm (§ Nghiệm thu sống ở cuối plan).

---

### Task 1: `Spec.deps` + `tools_for_coordinator` + nối vào graph

Đây là task sửa đúng lỗi đang có: `send_delivery_email` (vai kho) và `send_invoice_email` (vai kế toán) hiện trả `"Công cụ soạn mail không khả dụng."`

**Files:**
- Modify: `backend/src/agents/write_registry.py:22-26` (dataclass `Spec`), `:57-60` (vòng lặp mail), thêm hàm mới cuối file
- Modify: `backend/src/agents/mail_write.py` (thêm hằng `MAIL_DEPS` cạnh `MAIL_COORDINATOR_CFGS`)
- Modify: `backend/src/agents/graph.py:90-91`, `:132-138`
- Test: `backend/tests/agents/test_coordinator_deps.py` (tạo mới)

**Interfaces:**
- Consumes: `WRITE_COORDINATORS` (dict tool_name → `Spec`), `MAIL_COORDINATOR_CFGS` (tuple `EmailCfg`), `build_graph(llm, tools, checkpointer, role_cfg=None, mcp_all_tools=None)`
- Produces:
  - `Spec.deps: frozenset` — mặc định `frozenset()`, nên 20 dòng coordinator hiện có không phải sửa
  - `mail_write.MAIL_DEPS: frozenset[str]`
  - `write_registry.tools_for_coordinator(spec, tools, mcp_all_tools=None) -> list` — Task 2 dùng `Spec.deps`; không task nào khác gọi hàm này

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_coordinator_deps.py`:

```python
"""Coordinator có phụ thuộc nội bộ (tool MCP tên KHÁC tên coordinator) phải
khai tường minh, và graph phải resolve chúng từ registry MCP đầy đủ.

Lỗi thật đã xảy ra (đo sống 2026-08-12): bộ lọc theo vai cắt mất
preview_template_email, nên send_delivery_email của chính vai kho trả
"Công cụ soạn mail không khả dụng." — trong khi 1254 test vẫn xanh, vì
test mail không biết đến vai và test vai không biết đến mail."""
import json
import pytest
from unittest.mock import MagicMock

import src.agents.mail_write as mw
from src.agents.write_registry import WRITE_COORDINATORS, tools_for_coordinator


def _fake_tool(name):
    t = MagicMock()
    t.name = name

    async def ainvoke(args):
        return json.dumps({"ok": True, "display": "x", "mail_id": 1,
                           "subject": "s", "recipients": []}, ensure_ascii=False)

    t.ainvoke = ainvoke
    return t


def test_khong_deps_thi_tra_nguyen_danh_sach():
    spec = WRITE_COORDINATORS["post_invoice"]
    tools = [_fake_tool("post_invoice")]
    assert tools_for_coordinator(spec, tools, [_fake_tool("bat_ky")]) is tools


def test_mcp_all_tools_None_thi_tra_nguyen_danh_sach():
    """Hàng trăm test hiện có dựng graph không truyền mcp_all_tools — nhánh
    này giữ chúng nguyên vẹn."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    assert tools_for_coordinator(spec, tools, None) is tools


def test_resolve_dep_thieu_tu_registry_day_du():
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    full = tools + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    ket_qua = tools_for_coordinator(spec, tools, full)
    ten = {t.name for t in ket_qua}
    assert mw.MAIL_DEPS <= ten
    assert "send_delivery_email" in ten


def test_dep_khong_ton_tai_o_dau_ca_thi_raise():
    """Phân biệt hai loại lỗi: tool không có trong registry MCP là lỗi CẤU
    HÌNH (raise), khác hẳn tool có nhưng vai không được cấp (bỏ qua)."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    tools = [_fake_tool("send_delivery_email")]
    with pytest.raises(ValueError, match="preview_template_email"):
        tools_for_coordinator(spec, tools, tools)


@pytest.mark.asyncio
async def test_node_preview_khong_con_bao_khong_kha_dung():
    """Hồi quy TRỰC TIẾP cho lỗi sống: dựng node preview bằng danh sách ĐÃ
    LỌC theo vai kho (chỉ có send_delivery_email) cộng deps resolve từ
    registry đầy đủ — node phải chạy được, không trả câu 'không khả dụng'."""
    cfg = mw.DELIVERY_EMAIL_CFG
    spec = WRITE_COORDINATORS[cfg.tool_name]
    da_loc = [_fake_tool(cfg.tool_name)]
    full = da_loc + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    node = mw.make_send_template_email_preview_node(
        tools_for_coordinator(spec, da_loc, full), cfg)
    state = {"messages": [], "intent": "erp_write", "confirmed": None,
             "pending_action": {"tool": cfg.tool_name,
                                "args": {cfg.ref_arg: "WH/OUT/00138"},
                                "summary": "x"}}
    ket_qua = await node(state)
    noi_dung = ket_qua["messages"][-1].content
    assert "không khả dụng" not in noi_dung


def test_dep_khong_lot_vao_danh_sach_planner_visible():
    """Bất biến bảo mật (spec §3.2, §7.2): tools_for_coordinator KHÔNG được
    sửa danh sách gốc. Nếu nó mutate `tools` tại chỗ thay vì trả bản mới,
    dep sẽ lan sang planner/erp_write_executor — tức LLM gọi thẳng được
    preview_template_email với template bất kỳ, đúng lỗ hổng đang đi bịt."""
    spec = WRITE_COORDINATORS["send_delivery_email"]
    da_loc = [_fake_tool("send_delivery_email")]
    full = da_loc + [_fake_tool(n) for n in sorted(mw.MAIL_DEPS)]
    tools_for_coordinator(spec, da_loc, full)
    assert [t.name for t in da_loc] == ["send_delivery_email"]
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_coordinator_deps.py -v`
Expected: FAIL — `ImportError: cannot import name 'tools_for_coordinator'`

- [ ] **Step 3: Thêm `MAIL_DEPS` vào `mail_write.py`**

Đặt ngay dưới `MAIL_COORDINATOR_CFGS` (cuối khối định nghĩa cfg):

```python
# Ba tool MCP mà MỌI coordinator mail gọi nội bộ. Tên chúng KHÁC tên
# coordinator, nên bộ lọc theo vai (chỉ giữ own ∪ needs_sign_off) cắt mất
# chúng — đó chính là lỗi làm mọi tool mail chết với vai non-admin (đo sống
# 2026-08-12). Khai ở đây để write_registry gắn vào Spec.deps; graph resolve
# lại từ registry MCP đầy đủ. Mọi coordinator KHÁC tra đúng tool trùng tên
# mình nên không cần khai gì.
MAIL_DEPS = frozenset({"preview_template_email", "send_prepared_email",
                       "discard_prepared_email"})
```

- [ ] **Step 4: Thêm trường `deps` và hàm `tools_for_coordinator`**

Trong `backend/src/agents/write_registry.py`, sửa dataclass:

```python
@dataclass(frozen=True)
class Spec:
    node: str                 # graph node name
    build: Callable           # (llm, tools) -> node
    deps: frozenset = frozenset()   # tool MCP cần THÊM, ngoài tool trùng tên
```

Sửa import ở đầu file:

```python
from .mail_write import (make_send_template_email_preview_node,
                         MAIL_COORDINATOR_CFGS, MAIL_DEPS)
```

Sửa vòng lặp mail (dòng 57-60) — thêm đối số thứ ba:

```python
for _cfg in MAIL_COORDINATOR_CFGS:
    WRITE_COORDINATORS[_cfg.tool_name] = Spec(
        _cfg.preview_node,
        lambda llm, tools, c=_cfg: make_send_template_email_preview_node(tools, c),
        MAIL_DEPS)
```

Thêm hàm vào cuối file:

```python
def tools_for_coordinator(spec, tools, mcp_all_tools=None):
    """Danh sách tool cho hàm dựng node coordinator: `tools` ĐÃ LỌC theo vai,
    cộng các dep của spec resolve từ registry MCP đầy đủ.

    KHÔNG dùng cho planner / erp_write_executor / node SOP. Dep lọt vào danh
    sách planner-visible là mở đúng lỗ hổng thiết kế này đi bịt: LLM sẽ gọi
    thẳng preview_template_email với template bất kỳ, bỏ qua coordinator và
    guard vai gác ở cửa vào nó (spec 2026-08-12 §3.2).

    mcp_all_tools=None → trả `tools` nguyên vẹn. Đó là đường của vai admin
    (danh sách vốn không lọc nên đã đủ dep) và của mọi test dựng graph không
    truyền registry đầy đủ.
    """
    if not spec.deps or mcp_all_tools is None:
        return tools
    thieu = spec.deps - {t.name for t in tools}
    if not thieu:
        return tools
    theo_ten = {t.name: t for t in mcp_all_tools}
    them = []
    for ten in sorted(thieu):
        t = theo_ten.get(ten)
        if t is None:
            # Tool KHÔNG có ở đâu cả = lỗi cấu hình, khác hẳn "có nhưng vai
            # không được cấp" (trường hợp bình thường, xử lý ở nhánh trên).
            # Cùng cách phân biệt mà skill_loader.py dùng cho
            # SkillManifestError.
            raise ValueError(
                f"coordinator {spec.node!r} khai dep {ten!r} nhưng tool này "
                f"không có trong registry MCP — lỗi cấu hình, không phải vai")
        them.append(t)
    return list(tools) + them
```

- [ ] **Step 5: Nối vào `graph.py`**

Sửa import (khối import từ `.write_registry`) để có thêm `tools_for_coordinator`.

Sửa dòng 90-91:

```python
    for spec in WRITE_COORDINATORS.values():
        g.add_node(spec.node, spec.build(
            llms["planner"], tools_for_coordinator(spec, tools, mcp_all_tools)))
```

Sửa dòng 132-133 (node 2 của coordinator mail):

```python
    for cfg in MAIL_COORDINATOR_CFGS:
        _spec = WRITE_COORDINATORS[cfg.tool_name]
        g.add_node(cfg.send_node, make_send_template_email_node(
            tools_for_coordinator(_spec, tools, mcp_all_tools), cfg))
```

**KHÔNG** đổi dòng 78 (`erp_write_executor`) và dòng 98 (node SOP) — chúng phải tiếp tục nhận `tools` đã lọc. Đó là bất biến bảo mật nêu ở Global Constraints.

- [ ] **Step 6: Chạy test mới**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_coordinator_deps.py -v`
Expected: PASS, 6 test

- [ ] **Step 7: Chạy toàn bộ suite để xác nhận không hồi quy**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1260 passed, 4 skipped, 46 deselected` (1254 cũ + 6 mới)

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/write_registry.py backend/src/agents/mail_write.py backend/src/agents/graph.py backend/tests/agents/test_coordinator_deps.py
git commit -m "fix(mail): coordinator mail resolve dep từ registry MCP đầy đủ

Bộ lọc theo vai cắt mất preview/send/discard_prepared_email — ba tool MCP mà
coordinator mail tra nội bộ và không nằm trong tập nào của roles.py. Hệ quả:
send_delivery_email (vai kho) và send_invoice_email (vai kế toán) trả 'Công cụ
soạn mail không khả dụng' kể từ khi nhánh phân quyền merge.

Spec.deps khai tường minh; graph truyền cho hàm dựng node coordinator một danh
sách RIÊNG (đã lọc + deps). Danh sách planner-visible giữ nguyên — dep lọt vào
đó là mở đúng lỗ hổng đang đi bịt."
```

---

### Task 2: Test chốt drift cho phụ thuộc chưa khai

Task 1 sửa triệu chứng. Task này ngăn nó tái diễn: thêm helper mới mà quên khai `deps` phải đỏ test ngay, không đợi live-verify phát hiện như lần này.

**Files:**
- Test: `backend/tests/agents/test_coordinator_deps_drift.py` (tạo mới)

**Interfaces:**
- Consumes: `WRITE_COORDINATORS` (đã có `deps` từ Task 1)
- Produces: không có API mới — chỉ là cổng nghiệm thu

- [ ] **Step 1: Viết test**

Tạo `backend/tests/agents/test_coordinator_deps_drift.py`:

```python
"""Mọi tool MCP mà node coordinator tra bằng `by_name.get("...")` phải là
tên một coordinator, hoặc được khai trong Spec.deps.

Đây là chốt drift cho hạng lỗi đã lặp NĂM lần trong mạch phân quyền: một
danh sách khai báo thiếu âm thầm. Lần gần nhất (2026-08-12) làm mọi tool
mail chết với vai non-admin trong khi 1254 test vẫn xanh.

GIỚI HẠN CỐ Ý — nêu thẳng để người sau không tưởng test này phủ hết: nó chỉ
thấy được literal chuỗi. Bốn chỗ tra bằng biến nằm NGOÀI tầm:
  - nodes.py `by_name.get(name)` — tên động, đúng thiết kế
  - edit_order.py `by_name.get(FLAG_TOOL)` — hằng module
  - edit_order.py / create_order.py `by_name.get(cfg.tool_name)` — trùng tên
    coordinator nên vô hại
FLAG_TOOL hiện là 'flag_order_for_review', có trong _WH_OWN của roles.py, nên
hôm nay không sao. Đổi nó thành một tool ngoài roles.py thì test này KHÔNG
bắt được."""
import pathlib
import re

from src.agents.write_registry import WRITE_COORDINATORS

AGENTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "agents"
MAU = re.compile(r"""by_name\.get\(\s*["']([^"']+)["']\s*\)""")


def test_moi_literal_by_name_deu_da_duoc_khai():
    cho_phep = set(WRITE_COORDINATORS)
    for spec in WRITE_COORDINATORS.values():
        cho_phep |= set(spec.deps)

    vi_pham = []
    for f in sorted(AGENTS_DIR.glob("*.py")):
        for so_dong, dong in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for ten in MAU.findall(dong):
                if ten not in cho_phep:
                    vi_pham.append(f"{f.name}:{so_dong} tra {ten!r}")

    assert not vi_pham, (
        "tool MCP tra trong node coordinator phải là tên coordinator hoặc "
        "được khai ở Spec.deps — nếu không, bộ lọc theo vai sẽ cắt mất nó và "
        "node trả lỗi 'không khả dụng' với vai non-admin:\n"
        + "\n".join(vi_pham))


def test_mau_regex_that_su_bat_duoc_dong_that():
    """Đối chứng: nếu regex hỏng, test trên sẽ xanh giả (không tìm thấy gì
    thì không có vi phạm). Khẳng định nó thấy được ít nhất 3 tool mail đã
    biết chắc là có trong mail_write.py."""
    mail_py = (AGENTS_DIR / "mail_write.py").read_text(encoding="utf-8")
    tim_duoc = set(MAU.findall(mail_py))
    assert {"preview_template_email", "send_prepared_email",
            "discard_prepared_email"} <= tim_duoc
```

- [ ] **Step 2: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_coordinator_deps_drift.py -v`
Expected: PASS, 2 test. (Task 1 đã khai `MAIL_DEPS` nên không còn vi phạm.)

- [ ] **Step 3: Chứng minh guard bắt được lỗi thật (deliberate-break)**

Tạm sửa `backend/src/agents/write_registry.py`, đổi `MAIL_DEPS` thành `frozenset()` ở vòng lặp mail:

```python
        lambda llm, tools, c=_cfg: make_send_template_email_preview_node(tools, c),
        frozenset())
```

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_coordinator_deps_drift.py::test_moi_literal_by_name_deu_da_duoc_khai -v`
Expected: FAIL, liệt kê đúng 3 dòng `mail_write.py:181/241/273`

Hoàn nguyên thay đổi tạm đó, chạy lại → PASS. Một test không được chứng minh là bắt được lỗi thì chỉ là trang trí.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/agents/test_coordinator_deps_drift.py
git commit -m "test(mail): chốt drift cho phụ thuộc coordinator chưa khai

Quét literal by_name.get() trong backend/src/agents/*.py, khẳng định mỗi tên
là coordinator hoặc đã khai ở Spec.deps. Chứng minh bằng deliberate-break:
gỡ MAIL_DEPS thì test đỏ đúng 3 dòng.

Giới hạn (ghi trong docstring): chỉ thấy literal, không thấy 4 chỗ tra bằng
biến."
```

---

### Task 3: `templates_for_role` + script xuất env

**Files:**
- Modify: `backend/src/agents/mail_write.py` (thêm hàm cuối file)
- Create: `scripts/export_role_templates.py`
- Test: `backend/tests/agents/test_templates_for_role.py` (tạo mới)

**Interfaces:**
- Consumes: `RoleCfg.allowed_tools()` (trả `None` cho admin), `MAIL_COORDINATOR_CFGS`
- Produces:
  - `mail_write.templates_for_role(role_cfg) -> frozenset[str] | None`
  - `mail_write.mail_models_for_role(role_cfg) -> frozenset[str] | None`
  - `scripts/export_role_templates.py <role>` in ra 2 dòng `KEY=value`, dùng bởi Task 5

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_templates_for_role.py`:

```python
"""Allowlist template phải được SUY RA từ roles.py × EmailCfg, không khai lại.

Khai lại là đẻ thêm đúng loại danh sách song song mà cả mạch phân quyền đang
đi sửa — và tiến trình MCP không import được backend nên không tự suy được."""
import src.agents.mail_write as mw
from src.agents import roles


def _vai(ten):
    return roles.load_profile()[ten]


def test_admin_khong_gioi_han():
    assert mw.templates_for_role(_vai("admin")) is None
    assert mw.mail_models_for_role(_vai("admin")) is None


def test_kho_chi_duoc_template_giao_hang():
    assert mw.templates_for_role(_vai("warehouse")) == frozenset(
        {mw.DELIVERY_EMAIL_CFG.template_name})
    assert mw.mail_models_for_role(_vai("warehouse")) == frozenset(
        {mw.DELIVERY_EMAIL_CFG.res_model})


def test_ke_toan_chi_duoc_template_hoa_don():
    assert mw.templates_for_role(_vai("accounting")) == frozenset(
        {mw.INVOICE_EMAIL_CFG.template_name})
    assert mw.mail_models_for_role(_vai("accounting")) == frozenset(
        {mw.INVOICE_EMAIL_CFG.res_model})


def test_suy_ra_chu_khong_hardcode():
    """Đối chứng cho tính 'suy ra': với MỘT RoleCfg tự chế được cấp đúng một
    coordinator mail khác, hàm phải trả template của coordinator ĐÓ — không
    phải một danh sách viết cứng."""
    cfg = roles.RoleCfg("thu", "Thử", "http://x", own=frozenset({"send_rfq_email"}))
    assert mw.templates_for_role(cfg) == frozenset({mw.RFQ_EMAIL_CFG.template_name})


def test_vai_khong_co_coordinator_mail_thi_rong():
    cfg = roles.RoleCfg("thu", "Thử", "http://x", own=frozenset({"deliver_order"}))
    assert mw.templates_for_role(cfg) == frozenset()


def test_moi_profile_deu_suy_duoc_khong_no():
    for ten_profile in roles.PROFILES:
        for cfg in roles.load_profile(ten_profile).values():
            mw.templates_for_role(cfg)
            mw.mail_models_for_role(cfg)
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_templates_for_role.py -v`
Expected: FAIL — `AttributeError: module 'src.agents.mail_write' has no attribute 'templates_for_role'`

- [ ] **Step 3: Thêm hai hàm vào `mail_write.py`**

Đặt cuối file, sau `MAIL_DEPS`:

```python
def _cfgs_cho_vai(role_cfg):
    """EmailCfg mà vai này được phép dùng. None = mọi cfg (admin)."""
    cho_phep = role_cfg.allowed_tools()
    if cho_phep is None:
        return None
    return [c for c in MAIL_COORDINATOR_CFGS if c.tool_name in cho_phep]


def templates_for_role(role_cfg):
    """Tên các mail.template vai này được phép dùng. None = không giới hạn.

    SUY RA từ roles.py × EmailCfg, không khai lại: thêm coordinator mail mới
    là allowlist tự đúng theo. Tiến trình MCP không import được backend nên
    giá trị này phải đi qua env — xem scripts/export_role_templates.py."""
    cfgs = _cfgs_cho_vai(role_cfg)
    if cfgs is None:
        return None
    return frozenset(c.template_name for c in cfgs)


def mail_models_for_role(role_cfg):
    """Model nguồn vai này được phép gửi mail về. None = không giới hạn.

    Dùng cho send_prepared_email, tool nhận mail_id chứ không nhận template
    nên allowlist template không chạm tới được (spec 2026-08-12 §4.3)."""
    cfgs = _cfgs_cho_vai(role_cfg)
    if cfgs is None:
        return None
    return frozenset(c.res_model for c in cfgs)
```

- [ ] **Step 4: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_templates_for_role.py -v`
Expected: PASS, 6 test

- [ ] **Step 5: Viết script xuất env**

Tạo `scripts/export_role_templates.py`:

```python
# scripts/export_role_templates.py
"""In ra biến môi trường giới hạn phạm vi mail cho MỘT vai.

Dùng bởi start-dev.ps1 để cấu hình từng tiến trình MCP. Xuất CẢ HAI biến vì
cả hai suy từ cùng một phép ghép roles.py × EmailCfg — tách làm hai script
là tạo cơ hội cho chúng lệch nhau.

Vai admin (unrestricted) in ra giá trị RỖNG: env rỗng = không giới hạn, đúng
hợp đồng phía MCP.

Chạy: python scripts/export_role_templates.py warehouse
Ra:   MCP_ALLOWED_TEMPLATES=Shipping: Send by Email
      MCP_ALLOWED_MAIL_MODELS=stock.picking
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.agents import roles                      # noqa: E402
from src.agents import mail_write                 # noqa: E402

# Ngăn cách bằng NEWLINE, không phải dấu phẩy: tên template Odoo có thể chứa
# dấu phẩy (vd "Invoice: Sending, Reminder"), tách bằng phẩy sẽ vỡ âm thầm.
SEP = "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: export_role_templates.py <role>")
    ten_vai = sys.argv[1]
    profile = roles.load_profile()
    if ten_vai not in profile:
        sys.exit(f"Vai không có trong profile: {ten_vai!r} "
                 f"(có: {', '.join(sorted(profile))})")
    cfg = profile[ten_vai]

    tpl = mail_write.templates_for_role(cfg)
    mod = mail_write.mail_models_for_role(cfg)
    # None (admin) → chuỗi rỗng, đúng hợp đồng "env rỗng = không giới hạn".
    print("MCP_ALLOWED_TEMPLATES=" + (SEP.join(sorted(tpl)) if tpl else ""))
    print("MCP_ALLOWED_MAIL_MODELS=" + (SEP.join(sorted(mod)) if mod else ""))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Kiểm script chạy được cho cả ba vai**

Run:
```bash
cd /d/Youdoo && for r in admin warehouse accounting; do echo "--- $r"; backend/.venv/Scripts/python.exe scripts/export_role_templates.py $r; done
```
Expected: `admin` in ra hai dòng có giá trị rỗng; `warehouse` in `Shipping: Send by Email` + `stock.picking`; `accounting` in `Invoice: Sending` + `account.move`.

- [ ] **Step 7: Chạy toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1268 passed, 4 skipped, 46 deselected`

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/mail_write.py scripts/export_role_templates.py backend/tests/agents/test_templates_for_role.py
git commit -m "feat(mail): suy allowlist template/model theo vai từ roles.py x EmailCfg

Tiến trình MCP không import được backend, nên allowlist phải đi qua env. Suy
ra thay vì khai lại: thêm coordinator mail mới là allowlist tự đúng theo, không
đẻ thêm danh sách song song."
```

---

### Task 4: Cưỡng chế allowlist trong tiến trình MCP

**Files:**
- Create: `mcp-servers/odoo/role_scope.py`
- Modify: `mcp-servers/odoo/tools/mail.py` (đầu `preview_template_email`, đầu `send_prepared_email`)
- Test: `backend/tests/mcp/test_role_scope.py` (tạo mới)

**Interfaces:**
- Consumes: env `MCP_ALLOWED_TEMPLATES`, `MCP_ALLOWED_MAIL_MODELS` (Task 3 sinh, Task 5 truyền)
- Produces: `role_scope.allowed(gia_tri, raw) -> bool` — hàm THUẦN, không import `server`/`odoo_call`, nên test import thẳng được

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_role_scope.py`:

```python
"""Giới hạn phạm vi mail theo vai, cưỡng chế TRONG tiến trình MCP.

Đây là lớp dưới tầng agent: nó chặn cả đường gọi thẳng vào cổng MCP (:8004 /
:8005), thứ mà bộ lọc tool ở backend không với tới. role_scope.py cố tình
không import server/odoo_call để test được như hàm thuần."""
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def rs():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import role_scope
    finally:
        sys.path.remove(str(MCP_DIR))
    return role_scope


def test_env_rong_thi_khong_gioi_han(rs):
    """Hợp đồng cho tiến trình admin và cho mọi test MCP hiện có."""
    assert rs.allowed("bat ky", "") is True
    assert rs.allowed("bat ky", None) is True


def test_gia_tri_trong_danh_sach_thi_cho_qua(rs):
    raw = "Shipping: Send by Email"
    assert rs.allowed("Shipping: Send by Email", raw) is True


def test_gia_tri_ngoai_danh_sach_thi_chan(rs):
    raw = "Shipping: Send by Email"
    assert rs.allowed("Invoice: Sending", raw) is False


def test_nhieu_gia_tri_ngan_cach_bang_newline(rs):
    raw = "Shipping: Send by Email\nInvoice: Sending"
    assert rs.allowed("Invoice: Sending", raw) is True
    assert rs.allowed("Sales: Send Quotation", raw) is False


def test_ten_chua_dau_phay_khong_bi_che_doi(rs):
    """Lý do chọn newline làm ký tự ngăn cách thay vì dấu phẩy."""
    raw = "Invoice: Sending, Reminder"
    assert rs.allowed("Invoice: Sending, Reminder", raw) is True
    assert rs.allowed("Invoice: Sending", raw) is False


def test_bo_qua_khoang_trang_thua_va_dong_rong(rs):
    raw = "\n  Shipping: Send by Email  \n\n"
    assert rs.allowed("Shipping: Send by Email", raw) is True
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_role_scope.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'role_scope'`

- [ ] **Step 3: Viết `role_scope.py`**

Tạo `mcp-servers/odoo/role_scope.py`:

```python
"""Giới hạn phạm vi mail theo vai — cưỡng chế TRONG tiến trình MCP.

Mỗi tiến trình MCP chỉ nắm credential của một vai (:8003 admin / :8004 kho /
:8005 kế toán). Bộ lọc tool ở backend là lớp UX; nó KHÔNG với tới đường gọi
thẳng vào cổng MCP. Module này là lớp chặn cho đường đó.

CỐ TÌNH không import server/odoo_call: giữ thuần để test được trực tiếp, và
để nó không bao giờ trở thành một đường ra Odoo mới.

Giá trị env ngăn cách bằng NEWLINE, không phải dấu phẩy — tên template Odoo
có thể chứa dấu phẩy.

Env rỗng/không đặt = KHÔNG giới hạn. Đó là hợp đồng cho tiến trình admin và
cho mọi test MCP hiện có (chúng không đặt biến nào)."""

ALLOWED_TEMPLATES_ENV = "MCP_ALLOWED_TEMPLATES"
ALLOWED_MAIL_MODELS_ENV = "MCP_ALLOWED_MAIL_MODELS"


def parse(raw):
    """Chuỗi env -> set. Bỏ dòng rỗng và khoảng trắng thừa hai đầu."""
    if not raw:
        return set()
    return {d.strip() for d in raw.split("\n") if d.strip()}


def allowed(gia_tri, raw):
    """True nếu `gia_tri` được phép. Danh sách rỗng = không giới hạn."""
    cho_phep = parse(raw)
    if not cho_phep:
        return True
    return gia_tri in cho_phep
```

- [ ] **Step 4: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_role_scope.py -v`
Expected: PASS, 6 test

- [ ] **Step 5: Nối vào `preview_template_email`**

Trong `mcp-servers/odoo/tools/mail.py`, khối import hiện là:

```python
import json

from server import mcp
from odoo_call import odoo
from helpers import envelope
```

Sửa thành (`os` vào nhóm thư viện chuẩn cạnh `json`; `role_scope` vào nhóm module nội bộ):

```python
import json
import os

from server import mcp
from odoo_call import odoo
from helpers import envelope
import role_scope
```

Thêm ngay đầu thân `preview_template_email`, TRƯỚC lệnh `odoo(...)` đầu tiên (dòng 55):

```python
    # Cưỡng chế phạm vi vai TRONG tiến trình MCP — chặn cả đường gọi thẳng
    # cổng này, thứ mà bộ lọc tool ở backend không với tới (spec 2026-08-12
    # §4.2). KHÔNG nêu danh sách được phép trong câu từ chối: không rò cấu
    # hình vai cho người gọi trực tiếp.
    if not role_scope.allowed(template_name,
                              os.environ.get(role_scope.ALLOWED_TEMPLATES_ENV)):
        return json.dumps(
            {"ok": False,
             "display": f"Template '{template_name}' không thuộc phạm vi của vai này."},
            ensure_ascii=False)
```

- [ ] **Step 6: Nối vào `send_prepared_email`**

`send_prepared_email` nhận `mail_id` chứ không nhận template, nên allowlist template không chạm tới. Thêm ngay đầu thân hàm, TRƯỚC lệnh `odoo("mail.mail", "write", ...)` (dòng 128):

```python
    # Cửa sau của §4.2: tool này chỉ nhận mail_id, nên ai gọi thẳng cổng MCP
    # có thể lấy BẤT KỲ bản nháp mail.mail nào đang có và gửi đi. Đối chiếu
    # model nguồn của bản ghi với phạm vi vai (spec 2026-08-12 §4.3).
    #
    # GIỚI HẠN ĐÃ BIẾT: hai vai cùng res_model thì kiểm này không tách được.
    # Hiện không xảy ra (stock.picking chỉ của kho, account.move chỉ của kế
    # toán) — đừng tưởng nó mạnh hơn thực tế.
    pham_vi = os.environ.get(role_scope.ALLOWED_MAIL_MODELS_ENV)
    if role_scope.parse(pham_vi):
        rows = odoo("mail.mail", "read", [[mail_id]], {"fields": ["model"]})
        if not rows:
            return envelope(False, f"Không tìm thấy mail nháp id={mail_id}.")
        model_nguon = rows[0].get("model") or ""
        if not role_scope.allowed(model_nguon, pham_vi):
            return envelope(False, "Mail này không thuộc phạm vi của vai hiện tại.")
```

- [ ] **Step 7: Chạy test biên MCP để xác nhận không phá bất biến cũ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/ -v`
Expected: PASS toàn bộ. `role_scope.py` không nhắc `ServerProxy`/`execute_kw` nên `test_chi_odoo_call_duoc_nhac_ServerProxy` vẫn xanh.

- [ ] **Step 8: Chạy toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1274 passed, 4 skipped, 46 deselected`

- [ ] **Step 9: Commit**

```bash
git add mcp-servers/odoo/role_scope.py mcp-servers/odoo/tools/mail.py backend/tests/mcp/test_role_scope.py
git commit -m "feat(mcp): cưỡng chế phạm vi mail theo vai trong tiến trình MCP

Lớp dưới tầng agent: chặn cả đường gọi thẳng vào cổng MCP, thứ bộ lọc tool ở
backend không với tới. preview_template_email kiểm template_name;
send_prepared_email kiểm model nguồn của bản ghi (tool này chỉ nhận mail_id
nên allowlist template không chạm tới được).

Env rỗng = không giới hạn — tiến trình admin và mọi test MCP hiện có giữ
nguyên hành vi."
```

---

### Task 5: MCP bind cấu hình được + nối env vào start-dev.ps1 + tài liệu

**Files:**
- Modify: `mcp-servers/odoo/server.py:19-20`
- Modify: `start-dev.ps1:93-123` (vòng lặp `$mcpRoles`)
- Modify: `docs/getting-started.md`
- Test: `backend/tests/mcp/test_server_bind.py` (tạo mới)

**Interfaces:**
- Consumes: `scripts/export_role_templates.py` (Task 3), env `MCP_ALLOWED_*` (Task 4)
- Produces: env `MCP_ODOO_HOST` (mặc định `127.0.0.1`)

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_server_bind.py`:

```python
"""server.py phải bind 127.0.0.1 theo mặc định, không phải 0.0.0.0.

0.0.0.0 khiến ba cổng MCP (8003/8004/8005) lộ ra mạng LAN. Mỗi tiến trình
nắm credential ghi của một vai, và cổng không có xác thực — nên bind rộng là
đường tấn công trực tiếp mà toàn bộ Task 4 đang đi bịt.

Quét NGUỒN chứ không khởi động server: test không được chạm hạ tầng sống."""
import pathlib
import re

SERVER_PY = (pathlib.Path(__file__).resolve().parents[3]
             / "mcp-servers" / "odoo" / "server.py")


def test_khong_hardcode_0_0_0_0():
    src = SERVER_PY.read_text(encoding="utf-8")
    dong_code = [d for d in src.splitlines()
                 if '"0.0.0.0"' in d or "'0.0.0.0'" in d]
    assert not dong_code, (
        "server.py không được hardcode 0.0.0.0 — dùng "
        'os.environ.get("MCP_ODOO_HOST", "127.0.0.1"):\n' + "\n".join(dong_code))


def test_mac_dinh_la_localhost():
    src = SERVER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"""MCP_ODOO_HOST["']\s*,\s*["']127\.0\.0\.1["']""", src), (
        "phải có mặc định 127.0.0.1 cho MCP_ODOO_HOST")
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_server_bind.py -v`
Expected: FAIL cả 2 — `server.py:19` đang hardcode `host="0.0.0.0"`

- [ ] **Step 3: Sửa `server.py`**

Thay dòng 19-20:

```python
# Mặc định 127.0.0.1: mỗi tiến trình MCP nắm credential GHI của một vai và
# cổng không có xác thực, nên bind 0.0.0.0 (mặc định cũ) là lộ quyền ghi Odoo
# ra toàn mạng LAN. Đặt MCP_ODOO_HOST=0.0.0.0 khi chạy trong container, nơi
# bind rộng là bắt buộc để container khác gọi tới.
mcp = FastMCP("odoo-mcp",
              host=os.environ.get("MCP_ODOO_HOST", "127.0.0.1"),
              port=int(os.environ.get("MCP_ODOO_PORT", "8003")))
```

- [ ] **Step 4: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/mcp/test_server_bind.py -v`
Expected: PASS, 2 test

- [ ] **Step 5: Nối env vào `start-dev.ps1`**

Trong vòng lặp `foreach ($r in $mcpRoles)`, thêm ngay sau `$env:ODOO_PASSWORD = $env:AI_ACCOUNT_PASSWORD` (dòng 101):

```powershell
    # Phạm vi mail theo vai — SUY RA từ roles.py x EmailCfg, không viết tay ở
    # đây (spec 2026-08-12 §4.1). Vai admin nhận giá trị rỗng = không giới hạn.
    $env:MCP_ALLOWED_TEMPLATES = ""
    $env:MCP_ALLOWED_MAIL_MODELS = ""
    foreach ($dong in (& $backendPy (Join-Path $root "scripts\export_role_templates.py") $($r.Role))) {
        $i = $dong.IndexOf("=")
        if ($i -lt 1) { continue }
        $ten = $dong.Substring(0, $i)
        $gt = $dong.Substring($i + 1)
        if ($ten -eq "MCP_ALLOWED_TEMPLATES")   { $env:MCP_ALLOWED_TEMPLATES = $gt }
        if ($ten -eq "MCP_ALLOWED_MAIL_MODELS") { $env:MCP_ALLOWED_MAIL_MODELS = $gt }
    }
```

Và thêm khoá `Role` vào bảng `$mcpRoles` (dòng 88-92) để có tên vai của `roles.py`, khác với login Odoo:

```powershell
$mcpRoles = @(
    @{ Port = 8003; User = "ai-admin";      Role = "admin";      Log = "mcp-odoo-admin" },
    @{ Port = 8004; User = "ai-warehouse";  Role = "warehouse";  Log = "mcp-odoo-warehouse" },
    @{ Port = 8005; User = "ai-accounting"; Role = "accounting"; Log = "mcp-odoo-accounting" }
)
```

**Lưu ý PowerShell 5.1:** một allowlist nhiều template sẽ chứa newline; gán vào `$env:` giữ nguyên newline và `Start-Process` truyền được. Chỉ tách theo dấu `=` ĐẦU TIÊN (`IndexOf`), vì tên template có thể chứa dấu `=`.

- [ ] **Step 6: Cập nhật `docs/getting-started.md`**

Thêm vào mục biến môi trường, cạnh `MCP_ODOO_PORT`:

```markdown
- **`MCP_ODOO_HOST`** — bind address of each mcp-odoo process; defaults to
  `127.0.0.1`. Each process holds one role's **write** credential and the port
  has no authentication, so binding wider exposes Odoo write access to the
  whole LAN. Set it to `0.0.0.0` only when running mcp-odoo inside a container,
  where a wide bind is required for other containers to reach it.
- **`MCP_ALLOWED_TEMPLATES` / `MCP_ALLOWED_MAIL_MODELS`** — per-role mail scope,
  newline-separated. Do **not** set these by hand: `start-dev.ps1` derives them
  from `roles.py` × `EmailCfg` via `scripts/export_role_templates.py`. Empty or
  unset means no restriction (that is what the admin process gets).
```

- [ ] **Step 7: Chạy toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1276 passed, 4 skipped, 46 deselected`

- [ ] **Step 8: Commit**

```bash
git add mcp-servers/odoo/server.py start-dev.ps1 docs/getting-started.md backend/tests/mcp/test_server_bind.py
git commit -m "fix(mcp): bind 127.0.0.1 mặc định + truyền phạm vi mail theo vai

server.py hardcode 0.0.0.0 khiến 3 cổng MCP lộ ra LAN, mỗi cổng nắm credential
ghi của một vai và không có xác thực. Mặc định thành 127.0.0.1, đặt lại qua
MCP_ODOO_HOST khi chạy trong container.

start-dev.ps1 gọi export_role_templates.py sinh MCP_ALLOWED_* cho từng tiến
trình — không viết tay allowlist ở script."
```

---

### Task 6: Nhóm quyền Odoo theo vai cho `mail.template`

Task này CHUẨN BỊ cho vòng đo ở §5.2 của spec. Nó tạo nhóm và luật; **quyết định giữ hay gỡ là của controller sau khi đo**, không phải của task này.

**Files:**
- Modify: `scripts/odoo_setup_ai_accounts.py`
- Test: `backend/tests/agents/test_odoo_setup_mail_groups.py` (tạo mới)

**Interfaces:**
- Consumes: `mail_write.templates_for_role` (Task 3), `roles.load_profile()`
- Produces: hai nhóm Odoo `Youdoo AI / Mail Warehouse`, `Youdoo AI / Mail Accounting`, mỗi nhóm một `ir.rule` đọc trên `mail.template`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_odoo_setup_mail_groups.py`:

```python
"""Script tạo tài khoản phải sinh luật mail.template theo vai từ CÙNG nguồn
suy ra mà tiến trình MCP dùng — không phải một danh sách viết tay thứ hai.

Test đọc NGUỒN script, không chạy nó: chạy script là chạm Odoo sống, việc
đó do controller làm."""
import pathlib

SCRIPT = (pathlib.Path(__file__).resolve().parents[3]
          / "scripts" / "odoo_setup_ai_accounts.py")


def test_khong_viet_tay_ten_template():
    """Tên template chỉ được xuất hiện qua templates_for_role, không hardcode."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "templates_for_role" in src, (
        "luật mail.template phải suy từ mail_write.templates_for_role")
    for ten in ("Shipping: Send by Email", "Invoice: Sending",
                "Sales: Order Confirmation"):
        assert ten not in src, f"tên template {ten!r} bị viết cứng trong script"


def test_co_hai_nhom_mail_theo_vai():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "Youdoo AI / Mail Warehouse" in src
    assert "Youdoo AI / Mail Accounting" in src


def test_khong_tao_nhom_han_che_cho_admin():
    """ir.rule theo nhóm chỉ áp lên thành viên — admin không thuộc nhóm nào
    là tự do đọc. Tạo nhóm 'cho phép tất cả' cho admin là thừa và dễ hiểu sai
    thành 'admin cũng bị giới hạn'."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "Youdoo AI / Mail Admin" not in src


def test_luat_chi_gioi_han_doc():
    """perm_write/create/unlink trên mail.template đã có luật Odoo gốc quản;
    thêm luật ghi ở đây là giẫm lên chúng."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "perm_read" in src
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_odoo_setup_mail_groups.py -v`
Expected: FAIL 3/4 (chỉ `test_khong_tao_nhom_han_che_cho_admin` xanh sẵn)

- [ ] **Step 3: Thêm hàm `ensure_rule` vào script**

Trong `scripts/odoo_setup_ai_accounts.py`, thêm sau `ensure_access` (dòng ~51):

```python
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
```

- [ ] **Step 4: Thêm khối tạo nhóm mail theo vai**

Thêm ngay sau khối `g_sinv` (nhóm `Youdoo AI / Sale Invoicing`), TRƯỚC `g_ro`:

```python
# Backstop Odoo cho tầng mail (spec 2026-08-12 §5). Nhóm `Youdoo AI / Mail`
# ở trên cấp mail.mail cho CẢ BA vai — cần thiết, nhưng vì thế Odoo không
# phân biệt được vai nào gửi template nào. Hai nhóm dưới đây thêm luật ĐỌC
# trên mail.template, giới hạn đúng template của vai.
#
# Danh sách template SUY RA từ mail_write.templates_for_role — cùng nguồn mà
# tiến trình MCP dùng. Viết tay ở đây là tạo danh sách song song thứ hai,
# đúng hạng lỗi mà cả mạch phân quyền đang đi sửa.
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
    _tpls = _mw.templates_for_role(_PROFILE[_role])
    if not _tpls:
        print("  bỏ qua (vai không có coordinator mail):", _gname)
        continue
    _gid = ensure_group(_gname)
    g_mail_role[_role] = _gid
    ensure_rule("youdoo_ai_mail_tpl_" + _role, _gid, "mail.template",
                repr([("name", "in", sorted(_tpls))]))
```

Thêm import ở đầu file (cạnh `import os`):

```python
from pathlib import Path
```

Và thêm nhóm vào `PLAN`:

```python
    "ai-warehouse":  [BASE_USER, g_mail] + ([g_mail_role["warehouse"]]
                                            if "warehouse" in g_mail_role else []) + [
        gid_by_full_name(n) for n in ("Inventory / User", "Contact / Creation")],
    "ai-accounting": [BASE_USER, g_mail, g_sinv] + ([g_mail_role["accounting"]]
                                                    if "accounting" in g_mail_role else []) + [
        gid_by_full_name(n) for n in ("Accounting / Invoicing", "Contact / Creation")],
```

- [ ] **Step 5: Chạy test**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/agents/test_odoo_setup_mail_groups.py -v`
Expected: PASS, 4 test

- [ ] **Step 6: Kiểm cú pháp script (KHÔNG chạy — chạy là chạm Odoo sống)**

Run: `cd /d/Youdoo && backend/.venv/Scripts/python.exe -m py_compile scripts/odoo_setup_ai_accounts.py && echo OK`
Expected: `OK`

**Lưu ý cho người thực hiện:** `py_compile` chỉ chứng minh cú pháp, KHÔNG chứng minh hợp đồng gọi Odoo đúng. Script này từng "py_compile sạch" rồi crash ở lần chạy sống đầu tiên. Controller sẽ chạy thật ở phần Nghiệm thu sống.

- [ ] **Step 7: Chạy toàn bộ suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1280 passed, 4 skipped, 46 deselected`

- [ ] **Step 8: Commit**

```bash
git add scripts/odoo_setup_ai_accounts.py backend/tests/agents/test_odoo_setup_mail_groups.py
git commit -m "feat(odoo): nhóm mail theo vai + ir.rule đọc trên mail.template

Backstop tầng Odoo cho 4 tool gửi mail — nhóm Youdoo AI / Mail cấp mail.mail
cho cả ba vai nên Odoo không phân biệt được ai gửi template nào. Danh sách
template suy từ mail_write.templates_for_role, cùng nguồn tiến trình MCP dùng.

Không tạo nhóm cho admin: ir.rule theo nhóm chỉ áp lên thành viên.

GIỮ HAY GỠ luật này là quyết định sau vòng đo hồi quy (spec §5.2) — luật có
thể chặn thừa một thao tác khác cần đọc template."
```

---

## Nghiệm thu sống — CONTROLLER làm, không phải subagent

Chạy sau khi cả 6 task xong và đã merge test xanh. Mọi bước dưới đây chạm hạ tầng sống (khởi động lại tiến trình, ghi vào Odoo), nên thuộc về controller.

### A. Khởi động lại stack

```powershell
& "d:\Youdoo\start-dev.ps1"
```
Xác nhận `:8002` trả 200 và ba cổng MCP mở. Kiểm `logs/mcp-odoo-warehouse.log` không có lỗi khởi động.

### B. Áp nhóm/luật Odoo

```bash
set -a; . ./.env; set +a
backend/.venv/Scripts/python.exe scripts/odoo_setup_ai_accounts.py
```
Chạy **hai lần**, lần hai phải in "nhóm đã có" / "cập nhật luật" — chứng minh idempotent.

### C. Bảy kịch bản nghiệm thu (spec §7.1)

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1 | kho: *"gửi email báo giao hàng cho phiếu WH/OUT/00138"* | soạn được, có cổng xác nhận |
| 2 | kế toán: *"gửi email hóa đơn INV/2026/00030 cho khách"* | soạn được, có cổng xác nhận |
| 3 | kho: *"gửi email hóa đơn INV/2026/00030 cho khách"* | từ chối ở tầng agent, KHÔNG cổng xác nhận |
| 4 | kế toán: *"gửi email báo giao hàng cho phiếu WH/OUT/00138"* | từ chối ở tầng agent |
| 5 | gọi thẳng `:8004` `preview_template_email("Invoice: Sending", "account.move", ...)` | MCP từ chối |
| 6 | gọi thẳng `:8004` `send_prepared_email` với mail_id của bản ghi `account.move` | MCP từ chối |
| 7 | admin: soạn thử cả 5 coordinator mail | không hồi quy |

Kịch bản 1-4, 7 gọi qua `POST :8002/v1/chat/completions` kèm header `x-openwebui-user-id` của vai tương ứng. **Gửi payload từ file UTF-8** (`curl --data-binary @file`) — shell mã hoá sai tiếng Việt sẽ làm backend trả 500 và trông như lỗi code.

Kịch bản 5-6 là phép đo QUYẾT ĐỊNH: chúng bỏ qua toàn bộ tầng agent. Không có chúng thì §4 chỉ được chứng minh gián tiếp.

**Dọn dẹp:** mọi bản nháp `mail.mail` sinh ra trong lúc đo phải xoá (`state='cancel'` là trơ tính nhưng vẫn nên dọn). KHÔNG xác nhận gửi ở bất kỳ kịch bản nào — mail gửi đi là không thu hồi được.

### D. Vòng đo hồi quy cho `ir.rule` (spec §5.2)

Với luật đang áp, chạy qua cổng vào thật toàn bộ tool `own` của hai vai:

- **kho:** `deliver_order`, `receive_order`, `validate_picking`, `internal_transfer`, `inventory_adjustment`, `scrap_product`, `return_order`
- **kế toán:** `post_invoice`, `register_payment`, `create_credit_memo`, `create_invoice_from_order`, `create_bill_from_po`

Với mỗi tool: dừng ở cổng xác nhận nếu chỉ cần biết nó ĐẾN được tool; xác nhận thật chỉ khi thao tác đảo ngược được, và dọn sau đó.

**Tiêu chí giữ:** không tool nào gãy vì lý do liên quan `mail.template`.
**Nếu gãy:** gỡ hai nhóm khỏi `PLAN` trong `odoo_setup_ai_accounts.py`, chạy lại script, giữ Task 4. Ghi số đo và lý do vào báo cáo. **Đây là kết quả hợp lệ, không phải thất bại** — §4 vẫn đóng đường tấn công thật.

### E. Chạy script nhất quán quyền

```bash
backend/.venv/Scripts/python.exe scripts/check_role_odoo_consistency.py
```
Hai khoảng trống mail (`warehouse/send_invoice_email`, `accounting/send_delivery_email`) sẽ vẫn hiện là GAP nếu luật `mail.template` không đổi kết quả `has_access` trên `mail.mail` — **đó là đúng**, vì script đo `ir.model.access` chứ không đo `ir.rule`. Ghi nhận điều này trong báo cáo thay vì sửa `KNOWN_ODOO_GAPS` cho khớp: sửa cho khớp sẽ giấu mất sự thật rằng script không nhìn thấy `ir.rule`.

### F. Viết báo cáo

`docs/superpowers/plans/2026-08-12-mail-role-enforcement-report.md` — kết quả 7 kịch bản, kết quả vòng đo D (giữ hay gỡ, kèm số liệu), và ghi nhận E.
