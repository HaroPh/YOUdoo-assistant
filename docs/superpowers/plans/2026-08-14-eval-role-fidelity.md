# Eval đo đúng cấu hình theo vai — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bộ đo eval dựng prompt bằng **chính hàm production dùng**, cho một vai
chỉ định — thay vì luôn dựng từ tập skill và tập tool đầy đủ mà không vai nào chạy.

**Architecture:** Trích phép lọc skill của `graph.py` thành một hàm dùng chung
(`specs_for_role`), rồi cho bộ đo gọi đúng hàm đó. Bộ đo cấp cho nó một registry
tool **giả mang đúng tên tool MCP thật** (lấy bằng cách import module `server`,
không cần MCP sống, không chạm Odoo). Thêm `--role`, mặc định `admin` để mọi
baseline hiện có giữ nguyên nghĩa.

**Tech Stack:** Python 3.11, pytest, LangChain core (`@tool`), FastMCP (chỉ để
đọc tên tool đã đăng ký).

**Spec:** `docs/superpowers/specs/2026-08-14-eval-role-fidelity-design.md` — đọc
trước khi bắt đầu Task 1. Mọi con số trong plan này đến từ §1 của spec, đo bằng
chính hàm production.

## Global Constraints

- **Lệnh pytest LUÔN kèm bộ lọc marker:** `pytest -m "not integration and not live" -q`.
  Lệnh trần gọi API LLM thật và Postgres thật — đã gây sự cố một lần.
- **Định danh trong `backend/src/`, `backend/evals/`, `backend/jobs/` viết bằng
  TIẾNG ANH.** Chú thích và chuỗi hiển thị bằng tiếng Việt.
- **KHÔNG chạy eval thật.** Mọi task trong plan này chỉ chạy `pytest`. Việc đo
  bằng LLM thật là của controller, sau khi toàn bộ plan xong.
- **KHÔNG chạm hạ tầng sống**: không khởi động/dừng tiến trình hay container,
  không ghi vào Odoo.
- **Vai `admin` KHÔNG được đổi hành vi.** Đây là điều kiện để 5 file baseline
  hiện có còn dùng được. Mọi task phải giữ bất biến này.
- **Quy ước tên baseline:** admin ⇒ `baseline-{model}-{set}.json` (**không** hậu
  tố, trùng đúng 5 file đang có); vai khác ⇒ `baseline-{model}-{set}-{role}.json`.
- **Fail-closed:** thiếu registry MCP thật ⇒ **báo lỗi**, KHÔNG âm thầm rơi về
  tập đầy đủ. Rơi về im lặng chính là con bọ đợt này đi đóng.
- **Không thụt:** `pytest -m "not integration and not live" -q` phải giữ
  **≥ 1420 passed, 4 skipped**.

---

## Số đo nền — dùng để viết assertion, không được đoán lại

Đo 2026-08-14 bằng chính `skill_role_gap` + `_filter_tools_for_role`:

| hồ sơ | vai | tool sau lọc | skill giữ | worker block |
|---|---|---|---|---|
| small-business | admin | 35 | 3/3 | 10 dòng |
| small-business | warehouse | 10 | 2/3 (bỏ `bao-gia-chiet-khau`) | 7 dòng |
| small-business | accounting | 7 | **0/3** | **RỖNG** |
| enterprise | admin | 35 | 3/3 | 10 dòng |
| enterprise | warehouse | 6 | 1/3 (bỏ `bao-gia-chiet-khau`, `nhap-kho`) | 4 dòng |
| enterprise | accounting | 7 | **0/3** | **RỖNG** |

Số tool trong prompt planner (`planner_prompt_for`): admin 35, warehouse 10
(sb) / 7 (ent), accounting 8.

⚠️ Số tool sau lọc (7) và số tool trong prompt planner (8) của vai accounting
**cố ý khác nhau** — hai hàm lọc hai thứ khác nhau (`allowed_tools()` lọc đối
tượng tool; `planner_prompt_for` lọc dòng văn bản). **Đừng viết test khẳng định
chúng bằng nhau.**

---

## File Structure

| file | trách nhiệm | task |
|---|---|---|
| `backend/src/agents/skill_loader.py` | thêm `specs_for_role` — một nguồn sự thật cho phép lọc skill | 1 |
| `backend/src/agents/graph.py` | dùng `specs_for_role` thay cho vòng lặp tại chỗ | 1 |
| `backend/evals/role_config.py` | **tạo mới** — dựng prompt theo vai cho bộ đo | 2 |
| `backend/evals/run_eval.py` | 3 hàm đo nhận vai; `--role`; hàm dựng đường dẫn baseline | 3 |
| `backend/jobs/eval_gate.py` | `--role`; baseline theo vai | 4 |
| `backend/evals/cases.py` | thêm `send_delivery_email` vào `WRITE_TOOL_NAMES` | 5 |
| `backend/tests/agents/test_close_activity_roles.py` | thay test chuỗi-con bằng bất biến | 5 |
| `backend/tests/agents/test_skill_role_filtering.py` | test cho `specs_for_role` | 1 |
| `backend/tests/jobs/test_eval_role_config.py` | **tạo mới** — lưới đỡ §5 của spec | 2 |
| `backend/tests/jobs/test_run_eval_role.py` | **tạo mới** — plumbing vai + quy ước baseline | 3 |
| `backend/tests/jobs/test_eval_gate.py` | mở rộng cho `--role` | 4 |

---

## Task 1: `specs_for_role` — một nguồn sự thật cho phép lọc skill

**Files:**
- Modify: `backend/src/agents/skill_loader.py` (thêm hàm, cuối file)
- Modify: `backend/src/agents/graph.py` (thay vòng lặp lọc skill)
- Test: `backend/tests/agents/test_skill_role_filtering.py` (thêm test vào cuối)

**Interfaces:**
- Consumes: `skill_role_gap(spec, tools, all_tools, role_cfg) -> str | None` (đã có).
- Produces:
  ```python
  def specs_for_role(specs, tools, all_tools, role_cfg, logger=None) -> list
  ```
  Trả danh sách `SkillSpec` **giữ nguyên thứ tự** của `specs`, bỏ những spec mà
  `skill_role_gap` trả lý do. `logger=None` ⇒ không log. Task 2 gọi hàm này.

**Bối cảnh:** `graph.py` hiện lọc bằng một vòng lặp tại chỗ. Bộ đo cần **đúng
phép lọc đó**. Nếu bộ đo tự viết lại, nó sẽ trôi lệch — đó là chính xác điều đã
xảy ra một lần trong quá trình viết spec này (proxy so tên cho ra 1/3 skill,
hàm thật cho ra 0/3).

- [ ] **Step 1: Viết test (đỏ trước)**

Thêm vào cuối `backend/tests/agents/test_skill_role_filtering.py`:

```python
# ── specs_for_role: một nguồn sự thật cho phép lọc skill ───────────────────

from src.agents.skill_loader import load_skill_specs, specs_for_role  # noqa: E402


def _specs_kept(role_name, profile="small-business"):
    """Tên skill còn lại sau khi lọc theo vai, dùng ĐÚNG đường production đi."""
    cfg = roles.PROFILES[profile][role_name]
    raw = _full_mcp_registry()
    tools = _filter_tools_for_role(raw, cfg)
    return [s.name for s in specs_for_role(load_skill_specs(), tools, raw, cfg)]


def test_specs_for_role_khop_so_do_that():
    """Đo 2026-08-14 bằng chính skill_role_gap. Nêu SỐ và TÊN cụ thể để nếu ai
    đó đổi chính sách vai, test đỏ vì đúng lý do — không phải vì một khẳng định
    chung chung."""
    assert _specs_kept("admin") == ["bao-gia-chiet-khau", "giao-hang", "nhap-kho"]
    assert _specs_kept("warehouse") == ["giao-hang", "nhap-kho"]
    assert _specs_kept("accounting") == []
    assert _specs_kept("warehouse", "enterprise") == ["giao-hang"]
    assert _specs_kept("accounting", "enterprise") == []


def test_specs_for_role_giu_nguyen_thu_tu():
    """Thứ tự quyết định thứ tự dòng trong worker block, mà worker block đi
    thẳng vào prompt — đảo thứ tự là đổi prompt."""
    goc = [s.name for s in load_skill_specs()]
    giu = _specs_kept("admin")
    assert giu == [n for n in goc if n in giu]


def test_specs_for_role_vai_admin_khong_lo_gi():
    """Bất biến của cả đợt: vai admin KHÔNG đổi hành vi, nếu không 5 baseline
    hiện có mất nghĩa."""
    assert _specs_kept("admin") == [s.name for s in load_skill_specs()]
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `cd D:/Youdoo/backend && python -m pytest tests/agents/test_skill_role_filtering.py -m "not integration and not live" -v`
Expected: FAIL — `ImportError: cannot import name 'specs_for_role'`.

- [ ] **Step 3: Viết `specs_for_role`**

Thêm vào cuối `backend/src/agents/skill_loader.py`:

```python
def specs_for_role(specs, tools, all_tools, role_cfg, logger=None) -> list:
    """Các skill được nạp cho vai hiện tại — GIỮ NGUYÊN thứ tự của `specs`.

    Trích từ vòng lặp vốn nằm trong graph.py để bộ đo eval gọi được ĐÚNG phép
    lọc mà production dùng. Viết lại phép lọc ở nơi thứ hai là cách nó trôi
    lệch: một phép tái lập bằng tay (write_tools ⊆ allowed_tools) đã cho 1/3
    skill trong khi hàm thật cho 0/3, vì nhánh declares_tools không được tái
    lập.

    Thứ tự có ý nghĩa: nó quyết định thứ tự dòng trong render_worker_block,
    mà khối đó đi thẳng vào prompt router.
    """
    kept = []
    for spec in specs:
        reason = skill_role_gap(spec, tools, all_tools, role_cfg)
        if reason:
            if logger is not None:
                logger.info("skill %r bỏ qua cho vai %r: %s", spec.name,
                            getattr(role_cfg, "name", None), reason)
            continue
        kept.append(spec)
    return kept
```

- [ ] **Step 4: Cho `graph.py` dùng nó**

Trong `backend/src/agents/graph.py`, thay vòng lặp lọc skill:

```python
    skill_specs = []
    for spec in load_skill_specs():
        reason = skill_role_gap(spec, tools, mcp_all_tools, role_cfg)
        if reason:
            logger.info("skill %r bỏ qua cho vai %r: %s", spec.name,
                       getattr(role_cfg, "name", None), reason)
            continue
        skill_specs.append(spec)
```

bằng:

```python
    skill_specs = specs_for_role(load_skill_specs(), tools, mcp_all_tools,
                                 role_cfg, logger=logger)
```

Sửa dòng import ở đầu file để lấy thêm `specs_for_role` từ `.skill_loader`
(giữ nguyên các tên đang import; `skill_role_gap` có thể không còn được dùng
trực tiếp ở `graph.py` — nếu vậy thì bỏ nó khỏi dòng import, đừng để import thừa).

- [ ] **Step 5: Chạy test của task này**

Run: `cd D:/Youdoo/backend && python -m pytest tests/agents/test_skill_role_filtering.py -m "not integration and not live" -v`
Expected: PASS toàn bộ (gồm 15 test cũ — chúng đi qua `build_graph`, tức qua
chính đường vừa sửa, nên chúng là bằng chứng "refactor không đổi hành vi").

- [ ] **Step 6: Chạy toàn bộ**

Run: `cd D:/Youdoo/backend && python -m pytest -m "not integration and not live" -q`
Expected: ≥ 1423 passed (1420 + 3 test mới), 4 skipped.

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/skill_loader.py backend/src/agents/graph.py backend/tests/agents/test_skill_role_filtering.py
git commit -m "refactor(skills): trích specs_for_role — một nguồn sự thật cho phép lọc skill theo vai"
```

---

## Task 2: `evals/role_config.py` — dựng prompt theo vai cho bộ đo

**Files:**
- Create: `backend/evals/role_config.py`
- Test: `backend/tests/jobs/test_eval_role_config.py` (tạo mới)

**Interfaces:**
- Consumes: `specs_for_role(specs, tools, all_tools, role_cfg, logger=None)` (Task 1);
  `_filter_tools_for_role(tools, cfg)` từ `src.agents.erp_agent`;
  `planner_prompt_for(cfg)`, `render_intent_router_prompt(worker_block)`,
  `render_worker_block(specs)`; `roles.load_profile()`.
- Produces — Task 3 gọi đúng bốn hàm này:
  ```python
  ROLE_SENSITIVE_SETS: frozenset   # {"intent", "sop_select", "planner"}
  def role_cfg(role_name: str)               # -> RoleCfg
  def intent_prompt(role_name: str) -> str
  def planner_prompt(role_name: str) -> str
  def valid_sops(role_name: str) -> frozenset[str]
  ```

**Bối cảnh bắt buộc đọc:** `skill_role_gap` cần hai danh sách **đối tượng tool**.
Bộ đo không có kết nối MCP. Cách giải đã kiểm 2026-08-14: lấy **tên** tool bằng
cách import module `server` của `mcp-servers/odoo` (cho ra đủ 35 tên, **không**
cần MCP sống, **không** chạm Odoo — `get_uid()` là lười), rồi dựng tool giả mang
đúng tên đó. Khuôn "import module server" đã dùng ở
`backend/tests/mcp/test_log_activity_tool.py`; khuôn "tool giả mang tên thật" đã
dùng ở `backend/tests/agents/test_skill_role_filtering.py`.

- [ ] **Step 1: Viết test (đỏ trước)**

Tạo `backend/tests/jobs/test_eval_role_config.py`:

```python
"""Lưới đỡ đóng vĩnh viễn hạng lỗi "bộ đo dựng prompt khác production".

KHÔNG gọi LLM. Đây là phần quan trọng nhất của đợt: hai vế còn lại chỉ sửa
hiện trạng, vế này ngăn tái diễn. Ba bản sửa trước cùng hạng lỗi đều thiếu nó.
"""
import pathlib

import pytest

from evals import role_config
from src.agents import roles
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.prompts import (INTENT_ROUTER_PROMPT, planner_prompt_for,
                                render_intent_router_prompt)
from src.agents.skill_loader import (load_skill_specs, render_worker_block,
                                     specs_for_role)

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"
PROFILES = ["small-business", "enterprise"]
ROLES = ["admin", "warehouse", "accounting"]


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


def test_ten_tool_gia_khop_registry_mcp_that():
    """Nếu danh sách tên lệch khỏi registry thật, mọi phép lọc phía sau đo sai
    — và sai IM LẶNG. Đây là giả định duy nhất của cách tiếp cận, nên nó phải
    được đo chứ không được tin."""
    import sys
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        that = set(server.mcp._tool_manager._tools)
    finally:
        sys.path.remove(str(MCP_DIR))

    gia = {t.name for t in role_config._fake_registry()}
    assert gia == that


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_intent_prompt_khop_cach_production_dung(role, profile, monkeypatch):
    """Bất biến trung tâm: prompt bộ đo dựng == prompt production dựng."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    raw = role_config._fake_registry()
    mong_doi = render_intent_router_prompt(render_worker_block(
        specs_for_role(load_skill_specs(), _filter_tools_for_role(raw, cfg),
                       raw, cfg)))
    assert role_config.intent_prompt(role) == mong_doi


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("role", ROLES)
def test_planner_prompt_khop_ham_production(role, profile, monkeypatch):
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    cfg = roles.PROFILES[profile][role]
    assert role_config.planner_prompt(role) == planner_prompt_for(cfg)


def test_vai_admin_giu_nguyen_cach_dung_cu(monkeypatch):
    """Điều kiện để 5 baseline hiện có còn dùng được: vai admin phải dựng ra
    ĐÚNG chuỗi mà bộ đo dựng TRƯỚC đợt này (tập skill đầy đủ, prompt gốc)."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "small-business")
    cu_intent = render_intent_router_prompt(render_worker_block(load_skill_specs()))
    from src.agents.prompts import WRITE_PLANNER_PROMPT
    assert role_config.intent_prompt("admin") == cu_intent
    assert role_config.planner_prompt("admin") == WRITE_PLANNER_PROMPT


@pytest.mark.parametrize("profile", PROFILES)
def test_vai_ke_toan_co_worker_block_RONG(profile, monkeypatch):
    """Đo 2026-08-14: kế toán giữ 0/3 skill trên CẢ HAI hồ sơ, nên
    render_intent_router_prompt("") trả về prompt TRẦN. Với vai này, prompt
    trần CHÍNH LÀ production — và đó là cấu hình con bọ 'router phân loại lệnh
    ghi thành unknown 3/3' đã sống trong đó."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", profile)
    assert role_config.intent_prompt("accounting") == INTENT_ROUTER_PROMPT
    assert role_config.valid_sops("accounting") == frozenset()


def test_vai_kho_hep_hon_admin_nhung_khong_rong(monkeypatch):
    """Đối chứng: nếu phép lọc hỏng theo hướng 'lọc sạch mọi thứ', test kế toán
    ở trên vẫn xanh giả. Vai kho phải giữ MỘT PHẦN."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "small-business")
    sops = role_config.valid_sops("warehouse")
    assert sops == {"giao-hang", "nhap-kho"}


def test_ba_bo_nhay_vai_duoc_ghim():
    """Bộ thứ tư trở thành nhạy-vai mà quên khai ⇒ nó sẽ âm thầm đo cấu hình
    admin. Ghim danh sách lại."""
    assert role_config.ROLE_SENSITIVE_SETS == frozenset(
        {"intent", "sop_select", "planner"})


def test_vai_khong_ton_tai_thi_tu_choi():
    """Fail-closed: rơi âm thầm về admin chính là con bọ đợt này đi đóng."""
    with pytest.raises(KeyError):
        role_config.role_cfg("bia-ra")
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_eval_role_config.py -m "not integration and not live" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.role_config'`.

- [ ] **Step 3: Viết module**

Tạo `backend/evals/role_config.py`:

```python
"""Dựng prompt theo VAI cho bộ đo eval — bằng chính hàm production dùng.

Vì sao cần: production lọc cả tập skill lẫn tập tool theo vai (graph.py,
planner_prompt_for), còn bộ đo trước đây luôn dựng từ tập ĐẦY ĐỦ. Đo
2026-08-14: vai kế toán chạy worker block RỖNG (0/3 skill) trong khi bộ đo đo
3/3 — nên mọi kết luận "cấu hình còn khoẻ" chỉ đúng cho vai admin.

skill_role_gap cần ĐỐI TƯỢNG tool, mà bộ đo không có kết nối MCP. Giải: lấy
TÊN tool thật bằng cách import module server của mcp-servers/odoo (đã kiểm:
cho ra đủ 35 tên, không cần MCP sống, không chạm Odoo — get_uid() là lười),
rồi dựng tool giả mang đúng tên đó. Giả định duy nhất — bộ lọc chỉ quan tâm
TÊN — được khoá bằng test, không để là niềm tin.
"""
import functools
import pathlib
import sys

from langchain_core.tools import tool as lc_tool

from src.agents import roles
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.prompts import (planner_prompt_for, render_intent_router_prompt)
from src.agents.skill_loader import (load_skill_specs, render_worker_block,
                                     specs_for_role)

# Ba bộ mà prompt của chúng phụ thuộc vai. Bộ nào KHÔNG ở đây thì --role không
# đổi gì — và điều đó phải tường minh, vì một bộ thứ tư trở thành nhạy-vai mà
# quên khai sẽ âm thầm đo cấu hình admin.
ROLE_SENSITIVE_SETS = frozenset({"intent", "sop_select", "planner"})

_MCP_DIR = (pathlib.Path(__file__).resolve().parents[2]
            / "mcp-servers" / "odoo")


@functools.lru_cache(maxsize=1)
def _mcp_tool_names() -> tuple[str, ...]:
    """Tên mọi tool MCP đã đăng ký, lấy từ chính module server.

    Fail-closed: thiếu thư mục MCP thì BÁO LỖI, không rơi về một danh sách
    đoán — đo sai im lặng chính là con bọ module này đi đóng.
    """
    if not _MCP_DIR.exists():
        raise RuntimeError(
            f"không tìm thấy {_MCP_DIR} — bộ đo cần tên tool MCP thật để dựng "
            "đúng cấu hình theo vai")
    sys.path.insert(0, str(_MCP_DIR))
    try:
        import server
        return tuple(sorted(server.mcp._tool_manager._tools))
    finally:
        sys.path.remove(str(_MCP_DIR))


@functools.lru_cache(maxsize=1)
def _fake_registry():
    """Tool giả mang ĐÚNG tên tool MCP thật.

    Bộ lọc theo vai chỉ so tên (erp_agent._filter_tools_for_role) và
    skill_role_gap chỉ cần tên để quyết định, nên thân hàm không bao giờ chạy.
    """
    out = []
    for name in _mcp_tool_names():
        def _stub(**kwargs):
            """tool giả — chỉ mang tên, không bao giờ được gọi"""
            raise AssertionError("tool giả của bộ đo không được phép chạy")
        out.append(lc_tool(name)(_stub))
    return tuple(out)


def role_cfg(role_name: str):
    """RoleCfg của vai, theo hồ sơ đang bật (YOUDOO_POLICY_PROFILE) — cùng
    nguồn production dùng. Vai không tồn tại ⇒ KeyError (fail-closed)."""
    return roles.load_profile()[role_name]


def _specs(role_name: str):
    cfg = role_cfg(role_name)
    raw = list(_fake_registry())
    return specs_for_role(load_skill_specs(),
                          _filter_tools_for_role(raw, cfg), raw, cfg)


def intent_prompt(role_name: str) -> str:
    """Prompt router mà vai này thật sự chạy. Vai giữ 0 skill ⇒ khối worker
    rỗng ⇒ render_intent_router_prompt trả prompt gốc."""
    return render_intent_router_prompt(render_worker_block(_specs(role_name)))


def planner_prompt(role_name: str) -> str:
    return planner_prompt_for(role_cfg(role_name))


def valid_sops(role_name: str) -> frozenset:
    return frozenset(s.name for s in _specs(role_name))
```

- [ ] **Step 4: Chạy để thấy xanh**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_eval_role_config.py -m "not integration and not live" -v`
Expected: PASS, **không có FAIL**. (Số ca do pytest nở ra từ `parametrize`:
2 hồ sơ × 3 vai cho hai test prompt, cộng 2 ca cho test kế toán, cộng 5 test
không tham số hoá.)

⚠️ Nếu `test_intent_prompt_khop_cach_production_dung` đỏ vì `lru_cache` giữ
kết quả cũ giữa các hồ sơ: `_fake_registry` và `_mcp_tool_names` **không** phụ
thuộc hồ sơ nên cache chúng là đúng; nhưng `_specs`/`intent_prompt` **không
được** cache. Nếu bạn thêm cache cho chúng, gỡ đi — đó là lỗi, không phải test sai.

- [ ] **Step 5: Phép thử phá — BẮT BUỘC**

Tạm đổi `_specs` để bỏ lọc:

```python
def _specs(role_name: str):
    return load_skill_specs()          # THỬ PHÁ — bỏ lọc theo vai
```

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_eval_role_config.py -m "not integration and not live" -q`
Expected: **FAIL** ở `test_vai_ke_toan_co_worker_block_RONG`,
`test_vai_kho_hep_hon_admin_nhung_khong_rong`, và
`test_intent_prompt_khop_cach_production_dung` (các ca vai non-admin).

Vẫn xanh nghĩa là lưới đỡ không đo gì — **sửa test, đừng bỏ qua bước này**.
Khôi phục rồi chạy lại cho xanh. **Ghi nguyên văn kết quả vào báo cáo.**

- [ ] **Step 6: Chạy toàn bộ**

Run: `cd D:/Youdoo/backend && python -m pytest -m "not integration and not live" -q`
Expected: không có FAIL; số passed tăng so với Task 1.

- [ ] **Step 7: Commit**

```bash
git add backend/evals/role_config.py backend/tests/jobs/test_eval_role_config.py
git commit -m "feat(evals): role_config — dựng prompt theo vai bằng chính hàm production"
```

---

## Task 3: `--role` trong `run_eval` + quy ước tên baseline

**Files:**
- Modify: `backend/evals/run_eval.py`
- Test: `backend/tests/jobs/test_run_eval_role.py` (tạo mới)

**Interfaces:**
- Consumes: `role_config.intent_prompt/planner_prompt/valid_sops/ROLE_SENSITIVE_SETS` (Task 2).
- Produces — Task 4 gọi hàm này:
  ```python
  def baseline_path(model: str, set_name: str, role: str = "admin") -> str
  ```
  Trả đường dẫn tuyệt đối. `role == "admin"` ⇒ **không** hậu tố.

  Và ba hàm đo nhận thêm tham số:
  ```python
  async def eval_intent(llm, pace=0.0, checkpoint_path=None, role="admin")
  async def eval_sop_select(llm, pace=0.0, checkpoint_path=None, role="admin")
  async def eval_planner(llm, pace=0.0, checkpoint_path=None, role="admin")
  ```
  Các hàm đo khác **giữ nguyên chữ ký** — chúng không nhạy vai.

- [ ] **Step 1: Viết test (đỏ trước)**

Tạo `backend/tests/jobs/test_run_eval_role.py`:

```python
"""--role: plumbing và quy ước tên baseline.

Quy ước tên là chỗ nguy hiểm nhất của đợt: sai một lần là GHI ĐÈ baseline admin
đang dùng, và không có cách nào lấy lại ngoài chạy đo lại.
"""
import os

import pytest

from evals import run_eval
from evals.role_config import ROLE_SENSITIVE_SETS


def test_admin_khong_co_hau_to_trung_ten_file_dang_co():
    p = run_eval.baseline_path("qwen3-8b", "intent", "admin")
    assert os.path.basename(p) == "baseline-qwen3-8b-intent.json"


def test_mac_dinh_la_admin():
    assert run_eval.baseline_path("qwen3-8b", "intent") == \
        run_eval.baseline_path("qwen3-8b", "intent", "admin")


def test_vai_khac_co_hau_to():
    p = run_eval.baseline_path("qwen3-8b", "intent", "accounting")
    assert os.path.basename(p) == "baseline-qwen3-8b-intent-accounting.json"


def test_dau_hai_cham_trong_ten_model_van_duoc_thay():
    """Giữ nguyên hành vi cũ: alias model có thể chứa ':' (tên Ollama), mà ':'
    không hợp lệ trong tên file Windows."""
    p = run_eval.baseline_path("qwen3:8b", "intent", "admin")
    assert ":" not in os.path.basename(p)


def test_nam_file_baseline_dang_co_deu_tra_ve_dung_duong_dan():
    """Đối chứng mạnh: nếu quy ước lệch, ít nhất một trong năm file này sẽ trỏ
    sai và cổng sẽ đọc nhầm/ghi đè."""
    for set_name in ("intent", "confirm", "planner", "read", "synthesis"):
        p = run_eval.baseline_path("qwen3-8b", set_name, "admin")
        assert os.path.exists(p), f"không thấy baseline admin cho {set_name}: {p}"


def test_ba_bo_nhay_vai_nhan_tham_so_role():
    """Ba hàm đo nhạy-vai phải NHẬN role; các hàm khác KHÔNG — nhận mà không
    dùng còn tệ hơn không nhận, vì nó trông như đã hỗ trợ."""
    import inspect
    for name in ROLE_SENSITIVE_SETS:
        fn = getattr(run_eval, f"eval_{name}")
        assert "role" in inspect.signature(fn).parameters, name
    for name in ("confirm", "chitchat", "read", "synthesis"):
        fn = getattr(run_eval, f"eval_{name}")
        assert "role" not in inspect.signature(fn).parameters, name


@pytest.mark.asyncio
async def test_eval_intent_dung_prompt_cua_vai_duoc_chi_dinh(monkeypatch):
    """Đo THẬT cái prompt được gửi đi, không đo ý định."""
    from src.agents.prompts import INTENT_ROUTER_PROMPT
    thay = {}

    class FakeLLM:
        async def ainvoke(self, messages):
            thay["system"] = messages[0].content

            class R:
                content = "erp_read"
            return R()

    monkeypatch.setattr(run_eval, "INTENT_CASES", [("xem đơn S00012", "erp_read")])
    await run_eval.eval_intent(FakeLLM(), pace=0.0, role="accounting")
    assert thay["system"] == INTENT_ROUTER_PROMPT      # kế toán: worker block RỖNG

    await run_eval.eval_intent(FakeLLM(), pace=0.0, role="admin")
    assert thay["system"] != INTENT_ROUTER_PROMPT      # admin: có khối worker
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_run_eval_role.py -m "not integration and not live" -v`
Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute 'baseline_path'`.

- [ ] **Step 3: Thêm `baseline_path`**

Thêm vào `backend/evals/run_eval.py`, ngay dưới `def _llm(...)`:

```python
def baseline_path(model: str, set_name: str, role: str = "admin") -> str:
    """Đường dẫn file baseline. MỘT nguồn sự thật cho quy ước tên — eval_gate
    import lại hàm này thay vì tự ghép chuỗi.

    Vai admin KHÔNG có hậu tố: 5 file baseline đang có mang đúng tên đó, và đổi
    tên chúng là làm hỏng mọi lệnh lẫn mọi tham chiếu đang dùng. Nói cách khác:
    không hậu tố NGHĨA LÀ admin.
    """
    here = os.path.dirname(__file__)
    stem = f"baseline-{model.replace(':', '-')}-{set_name}"
    if role != "admin":
        stem = f"{stem}-{role}"
    return os.path.join(here, f"{stem}.json")
```

- [ ] **Step 4: Cho ba hàm đo nhận vai**

Trong `eval_intent`, thay hai dòng dựng prompt:

```python
    specs = load_skill_specs()
    prompt = render_intent_router_prompt(render_worker_block(specs))
    valid_sops = frozenset(s.name for s in specs)
```

bằng:

```python
    # Prompt phải là prompt VAI NÀY thật sự chạy, không phải tập skill đầy đủ.
    # Đo 2026-08-14: vai kế toán chạy worker block RỖNG (0/3 skill) trong khi
    # bộ đo cũ luôn đo 3/3 — nên số cũ chỉ nói về vai admin.
    prompt = role_config.intent_prompt(role)
    valid_sops = role_config.valid_sops(role)
```

Làm **y hệt** trong `eval_sop_select` (nó có cùng hai dòng đó).

Trong `eval_planner`, thay `SystemMessage(content=WRITE_PLANNER_PROMPT)` bằng:

```python
             SystemMessage(content=role_config.planner_prompt(role)),
```

và dựng `planner_prompt` **một lần trước vòng lặp**, không gọi lại mỗi ca:

```python
    prompt = role_config.planner_prompt(role)
```

rồi dùng `SystemMessage(content=prompt)` trong `call`.

Thêm `role: str = "admin"` vào chữ ký cả ba hàm, và
`from evals import role_config` vào phần import đầu file.

- [ ] **Step 5: Thêm `--role` vào CLI**

Trong `main()`, thêm sau `--set`:

```python
    ap.add_argument("--role", default="admin",
                    choices=sorted(roles.load_profile()),
                    help="vai để dựng prompt (chỉ có tác dụng với "
                         "intent/sop_select/planner; các bộ khác bỏ qua)")
```

`roles` import từ `src.agents` — thêm `from src.agents import roles` nếu chưa có.

Truyền vai xuống **chỉ** cho ba bộ nhạy-vai:

```python
        kwargs = {"pace": args.pace}
        if args.set in role_config.ROLE_SENSITIVE_SETS:
            kwargs["role"] = args.role
        result = await _FN[args.set](_llm(args.model, role=args.set), **kwargs)
```

Và đổi nhánh `--save-baseline` sang dùng hàm mới:

```python
    if args.save_baseline:
        path = baseline_path(args.model, args.set, args.role)
        json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"baseline saved: {path}"); sys.exit(0)
```

- [ ] **Step 6: Chạy test của task này**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_run_eval_role.py -m "not integration and not live" -v`
Expected: PASS.

- [ ] **Step 7: Phép thử phá — BẮT BUỘC**

Tạm đổi `baseline_path` để admin cũng có hậu tố (`stem = f"{stem}-{role}"` không
điều kiện).

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_run_eval_role.py -m "not integration and not live" -q`
Expected: **FAIL** ở `test_admin_khong_co_hau_to_trung_ten_file_dang_co` và
`test_nam_file_baseline_dang_co_deu_tra_ve_dung_duong_dan`.

Khôi phục rồi chạy lại cho xanh. **Ghi kết quả vào báo cáo.**

- [ ] **Step 8: Chạy toàn bộ**

Run: `cd D:/Youdoo/backend && python -m pytest -m "not integration and not live" -q`
Expected: không có FAIL.

- [ ] **Step 9: Commit**

```bash
git add backend/evals/run_eval.py backend/tests/jobs/test_run_eval_role.py
git commit -m "feat(evals): --role cho run_eval + quy ước tên baseline một nguồn"
```

---

## Task 4: `--role` trong job `eval-gate`

**Files:**
- Modify: `backend/jobs/eval_gate.py`
- Test: `backend/tests/jobs/test_eval_gate.py` (thêm test vào cuối)

**Interfaces:**
- Consumes: `run_eval.baseline_path(model, set_name, role)` (Task 3);
  `role_config.ROLE_SENSITIVE_SETS` (Task 2).
- Produces: job `eval-gate` nhận `--role`, đọc baseline theo vai, truyền vai
  xuống ba bộ nhạy-vai.

**Bối cảnh:** `eval_gate.BASELINES` hiện là một dict **đường dẫn cứng** cho 6 bộ.
Với vai, đường dẫn phụ thuộc `(set, role)` nên dict cứng không đủ. Thay bằng lời
gọi `run_eval.baseline_path(...)`, giữ nguyên **tập bộ có baseline** (chitchat và
sop_select vẫn KHÔNG có baseline — cổng tuyệt đối).

- [ ] **Step 1: Viết test (đỏ trước)**

Thêm vào cuối `backend/tests/jobs/test_eval_gate.py`:

```python
# ── --role ────────────────────────────────────────────────────────────────

def test_add_args_co_role_mac_dinh_admin():
    import argparse
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args([]).role == "admin"


def test_role_choices_suy_tu_roles_khong_viet_tay():
    """Thêm một vai vào roles.py mà quên thêm vào choices ⇒ không đo được vai
    đó, và không ai biết. Suy ra thay vì khai tay."""
    import argparse
    from jobs import eval_gate
    from src.agents import roles
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    act = [a for a in p._actions if a.dest == "role"][0]
    assert set(act.choices) == set(roles.load_profile())


def test_bo_co_baseline_khong_doi():
    """chitchat và sop_select là cổng TUYỆT ĐỐI — thêm baseline cho chúng là
    đổi ngữ nghĩa cổng, không phải sửa lỗi."""
    from jobs import eval_gate
    assert "chitchat" not in eval_gate.BASELINE_SETS
    assert "sop_select" not in eval_gate.BASELINE_SETS
    assert eval_gate.BASELINE_SETS == frozenset(
        {"intent", "confirm", "planner", "read", "synthesis", "multi_source"})


def test_duong_dan_baseline_theo_vai():
    import os
    from evals import run_eval
    from jobs import eval_gate
    assert os.path.basename(eval_gate._baseline_for("intent", "qwen3-8b", "admin")) \
        == "baseline-qwen3-8b-intent.json"
    assert os.path.basename(
        eval_gate._baseline_for("intent", "qwen3-8b", "accounting")) \
        == "baseline-qwen3-8b-intent-accounting.json"
    assert eval_gate._baseline_for("chitchat", "qwen3-8b", "admin") is None
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_eval_gate.py -m "not integration and not live" -v`
Expected: FAIL — `AttributeError: module 'jobs.eval_gate' has no attribute 'BASELINE_SETS'`.

- [ ] **Step 3: Thay `BASELINES` bằng `BASELINE_SETS` + `_baseline_for`**

Trong `backend/jobs/eval_gate.py`, thay khối `BASELINES = {...}` bằng:

```python
# Bộ nào so với baseline (khác cổng TUYỆT ĐỐI). chitchat và sop_select KHÔNG
# có mặt: chúng là cổng tuyệt đối (violations==0 / hijack==0), không phải phép
# đo tương đối — thêm baseline cho chúng là đổi ngữ nghĩa cổng.
BASELINE_SETS = frozenset({"intent", "confirm", "planner", "read",
                           "synthesis", "multi_source"})


def _baseline_for(set_name: str, model: str, role: str):
    """Đường dẫn baseline, hoặc None nếu bộ này là cổng tuyệt đối.

    Dùng LẠI run_eval.baseline_path — quy ước tên chỉ được sống ở một chỗ.
    """
    if set_name not in BASELINE_SETS:
        return None
    return run_eval.baseline_path(model, set_name, role)
```

- [ ] **Step 4: Dùng chúng trong `run`**

Trong `jobs/eval_gate.py::run`, thay khối đọc baseline:

```python
            base = None
            if set_name in BASELINES:
                base = json.loads(BASELINES[set_name].read_text(encoding="utf-8"))
```

bằng:

```python
            base = None
            bpath = _baseline_for(set_name, model, args.role)
            if bpath is not None:
                with open(bpath, encoding="utf-8") as f:
                    base = json.load(f)
```

Và truyền vai xuống **chỉ** ba bộ nhạy-vai:

```python
                kwargs = {"pace": pace, "checkpoint_path": checkpoint}
                if set_name in role_config.ROLE_SENSITIVE_SETS:
                    kwargs["role"] = args.role
                result = asyncio.run(EVAL_FN[set_name](
                    run_eval._llm(model, role=role), **kwargs))
```

Thêm `from evals import role_config` vào phần import đầu file. Nếu `Path` không
còn được dùng sau khi bỏ `BASELINES`, gỡ import thừa.

- [ ] **Step 5: Thêm `--role` vào `add_args`**

```python
    p.add_argument("--role", default="admin",
                   choices=sorted(roles.load_profile()),
                   help="vai để dựng prompt (chỉ có tác dụng với "
                        "intent/sop_select/planner)")
```

Thêm `from src.agents import roles` vào import đầu file.

- [ ] **Step 6: Chạy test của task này**

Run: `cd D:/Youdoo/backend && python -m pytest tests/jobs/test_eval_gate.py -m "not integration and not live" -v`
Expected: PASS toàn bộ (gồm các test cũ của file — chúng là bằng chứng cổng
không đổi hành vi cho vai admin).

- [ ] **Step 7: Chạy toàn bộ**

Run: `cd D:/Youdoo/backend && python -m pytest -m "not integration and not live" -q`
Expected: không có FAIL.

- [ ] **Step 8: Commit**

```bash
git add backend/jobs/eval_gate.py backend/tests/jobs/test_eval_gate.py
git commit -m "feat(jobs): eval-gate nhận --role, baseline theo vai"
```

---

## Task 5: Hai món đo-lường đi kèm

**Files:**
- Modify: `backend/evals/cases.py` (`WRITE_TOOL_NAMES`)
- Modify: `backend/tests/agents/test_close_activity_roles.py` (thay test yếu)

**Interfaces:** không phụ thuộc task nào; không task nào phụ thuộc nó.

**Bối cảnh:** `WRITE_TOOL_NAMES` tự khai là đồng bộ với `WRITE_PLANNER_PROMPT`.
Đo trên `main` 2026-08-14: 35 tool trong prompt, 34 trong bảng, thiếu đúng
`send_delivery_email`, không có chiều ngược lại. Đây là lần **thứ hai** danh sách
này lệch — lần đầu ở mail-trigger-points, thiếu 4 tool mail. Lệch ⇒ chỉ số
`dangerous_misroute` xếp một misroute sang tool đó vào rổ **an toàn**.

- [ ] **Step 1: Viết test (đỏ trước)**

Trong `backend/tests/agents/test_close_activity_roles.py`, **thay** hàm
`test_planner_biet_ten_tool` bằng:

```python
def test_moi_tool_trong_prompt_planner_deu_co_trong_bang_eval():
    """Bất biến suy ra, thay cho phép kiểm chuỗi con cũ.

    Bản cũ chỉ khẳng định "close_activity(" xuất hiện trong WRITE_PLANNER_PROMPT
    — vẫn xanh nếu danh sách tham số sai hoàn toàn, và không nói gì về 34 tool
    còn lại. Bất biến này đóng luôn khoảng trống đã để `send_delivery_email`
    lọt: WRITE_TOOL_NAMES tự khai là đồng bộ với prompt, nên lệch là lỗi.

    Lệch ⇒ run_eval xếp một misroute sang tool thiếu vào rổ AN TOÀN thay vì rổ
    nguy hiểm. Đã xảy ra hai lần: mail-trigger-points (thiếu 4 tool mail) và
    close-activity (thiếu send_delivery_email).
    """
    import re
    from evals.cases import WRITE_TOOL_NAMES
    from src.agents.prompts import WRITE_PLANNER_PROMPT

    trong_prompt = set(re.findall(r"^- (\w+)\(", WRITE_PLANNER_PROMPT, re.M))
    assert trong_prompt, "regex không bắt được dòng tool nào — sửa regex, đừng nới test"
    thieu = sorted(trong_prompt - set(WRITE_TOOL_NAMES))
    assert not thieu, (
        f"tool có trong WRITE_PLANNER_PROMPT nhưng thiếu ở WRITE_TOOL_NAMES: "
        f"{thieu} — chỉ số dangerous_misroute sẽ mù với chúng")


def test_close_activity_co_trong_ca_prompt_lan_bang():
    """Giữ phần đối chứng cụ thể của test cũ: nêu thẳng tên để nếu ai đó gỡ
    close_activity ra thì đỏ vì đúng lý do, không phải vì một khẳng định chung."""
    from evals.cases import WRITE_TOOL_NAMES
    from src.agents.prompts import WRITE_PLANNER_PROMPT
    assert "close_activity(" in WRITE_PLANNER_PROMPT
    assert "close_activity" in WRITE_TOOL_NAMES
```

- [ ] **Step 2: Chạy để thấy nó đỏ**

Run: `cd D:/Youdoo/backend && python -m pytest tests/agents/test_close_activity_roles.py -m "not integration and not live" -v`
Expected: FAIL ở `test_moi_tool_trong_prompt_planner_deu_co_trong_bang_eval` với
thông điệp nêu `['send_delivery_email']`.

- [ ] **Step 3: Thêm tool thiếu vào bảng**

Trong `backend/evals/cases.py`, `WRITE_TOOL_NAMES`, thêm `"send_delivery_email"`.
Đặt cạnh `"send_invoice_email"` nếu tool đó có mặt, để hai tool mail nằm cùng chỗ.

- [ ] **Step 4: Chạy để thấy xanh**

Run: `cd D:/Youdoo/backend && python -m pytest tests/agents/test_close_activity_roles.py -m "not integration and not live" -v`
Expected: PASS.

- [ ] **Step 5: Phép thử phá — BẮT BUỘC**

Tạm gỡ `"send_delivery_email"` khỏi `WRITE_TOOL_NAMES`.

Run: `cd D:/Youdoo/backend && python -m pytest tests/agents/test_close_activity_roles.py -m "not integration and not live" -q`
Expected: **FAIL** ở `test_moi_tool_trong_prompt_planner_deu_co_trong_bang_eval`.

Khôi phục rồi chạy lại cho xanh. **Ghi kết quả vào báo cáo.**

- [ ] **Step 6: Chạy toàn bộ**

Run: `cd D:/Youdoo/backend && python -m pytest -m "not integration and not live" -q`
Expected: không có FAIL.

- [ ] **Step 7: Commit**

```bash
git add backend/evals/cases.py backend/tests/agents/test_close_activity_roles.py
git commit -m "fix(evals): send_delivery_email vào WRITE_TOOL_NAMES + bất biến prompt↔bảng"
```

---

## Đo bằng LLM thật — controller làm SAU khi plan xong

**Implementer KHÔNG chạm phần này.** Ghi ở đây để plan tự chứa đủ.

1. Ba bộ ở vai `admin`, đối chiếu baseline hiện có — **không được thụt**. Đây là
   phép đo chứng minh đợt này không phá thứ đang chạy:
   ```
   --set intent     --role admin --baseline evals/baseline-qwen3-8b-intent.json
   --set planner    --role admin --baseline evals/baseline-qwen3-8b-planner.json
   --set sop_select --role admin           (cổng tuyệt đối, cần hijack=0)
   ```
2. Ba bộ ở vai `accounting`, `--save-baseline`.
3. **Ghi lại con số vai hẹp và so với admin.** Nếu thấp hơn hẳn, đó là **một
   phát hiện thật về sản phẩm** — vai kế toán vốn đã yếu hơn mà không ai biết —
   không phải lỗi của đợt này, và phải được **báo cáo** chứ không lặng lẽ nhận
   làm baseline.

Điểm 3 là lý do đợt này đáng làm. Với vai kế toán, prompt router là bản **trần**
(worker block rỗng), nên đây là lần đầu tiên cấu hình đó được đo.
