# SP-2a: Nền tảng SOP skill dạng thư mục — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đưa 3 quy trình nghiệp vụ (SOP) tier-2 ra khỏi mã Python, vào thư mục
`backend/skills/<tên>/SKILL.md` mà người dùng low-code sửa được — mà không
nhường một chút thẩm quyền ghi nào cho markdown.

**Architecture:** Một loader chạy đúng một lần lúc `build_graph()`: quét
`backend/skills/*/SKILL.md`, validate fail-loud, **tự sinh** wrapper tool ghi
đã bọc `_confirm_write` (markdown không bao giờ định nghĩa tool mới), dựng
`create_agent` node với prose làm system prompt. Định tuyến **hybrid**: router
LLM trả thêm trường `sop` (đề cử, xác suất) trong **cùng một lượt gọi**, và
`_looks_like_question()` **phủ quyết tất định** — che đúng chiều lỗi live-verify
2026-07-16 (router thua 3/3 lần khi giao toàn quyền chọn SOP cho LLM).

**Tech Stack:** Python 3.11, PyYAML (parse frontmatter), LangGraph 1.1.10
(`StateGraph`, subgraph-as-node), LangChain 1.2.18 (`create_agent`,
`StructuredTool`), pytest 3 chế độ.

**Spec nguồn:** `docs/superpowers/specs/2026-07-29-sp2a-sop-skills-design.md`.
Mọi số hiệu §x.y dưới đây trỏ vào spec đó.

## Global Constraints

- **Python 3.11+.** Dùng `X | None`, không `Optional[X]`.
- **Bình luận tiếng Việt, định danh tiếng Anh** — khớp quy ước repo.
- **Repo đích là `D:\Youdoo`. `D:\Project` là repo nguồn CHỈ ĐỌC** — không bao
  giờ sửa, không bao giờ chạy test trong đó, không bao giờ chạm dữ liệu của nó.
- **Import trong `backend/tests/` và `backend/skills/` dùng tiền tố `src.`**
  (rootdir pytest là `backend/`), **KHÔNG** dùng `backend.src.` như repo nguồn.
  Mọi test port sang phải sửa lại import; bỏ luôn 2 dòng
  `sys.path.insert(...)` đầu file của repo nguồn (Youdoo không cần).
- **Test đơn vị không chạm mạng, không cần Postgres** theo mặc định. Cần
  Postgres → `@pytest.mark.integration`. Cần mạng/Odoo thật →
  `@pytest.mark.live`.
- **Quy tắc port test (kế thừa SP-1B, KHÔNG đổi):** test port sang mà đỏ **vì
  hạ tầng** (đường import, tên module, fixture) → sửa nối dây. Đỏ **vì hành
  vi** → DỪNG, báo cáo trong task report, **không sửa test cho xanh**.
- **Markdown không bao giờ định nghĩa tool mới.** Mọi tool ghi trong một node
  SOP phải là wrapper do loader sinh và luôn bọc `_confirm_write`. Không có
  `exec`, không có `eval`, không có đường nào cho prose cấp thêm thẩm quyền.
- **`recursion_limit` áp tại wiring** (`.with_config(...)` lúc `add_node`),
  KHÔNG trong hàm dựng node — bài học spike v10b: thiếu nó thì subgraph chạy
  **không giới hạn** (mặc định 25 của LangGraph không truyền vào
  subgraph-as-node).
- **`ERP_SKILLS_ENABLED` giữ nguyên semantics:** `"0"` là giá trị tắt **duy
  nhất** được nhận; mọi giá trị khác (kể cả chưa đặt) là bật. Kill-switch
  **cấp định tuyến** — an toàn ghi do `write_gate` bảo đảm độc lập.
- **Chạy `tests/rag/` làm bẩn 2 fixture nhị phân** (`bang_gia.xlsx`,
  `policy.docx`) — sau mọi lần chạy full suite, `git checkout -- backend/tests/rag/fixtures/`
  trước khi commit.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/requirements.txt` | **Sửa** — thêm `PyYAML==6.0.3` (đang là dep bắc cầu, giờ dùng trực tiếp) |
| `backend/src/agents/agentic_context_sync.py` | **Mới** — port nguyên văn từ `D:\Project`; bàn giao state tier-2 → tier-1 + scrub rò tên tool |
| `backend/src/agents/skill_manifest.py` | **Mới** — `SkillSpec`/`WriteToolSpec`, `parse_skill_md()`, `SkillManifestError`. Validate **cấu trúc từng file**. Không import LangChain |
| `backend/src/agents/skill_loader.py` | **Mới** — quét thư mục, validate **liên-file + ràng buộc tool**, sinh wrapper ghi đã gate, dựng node, kết xuất khối mô tả worker |
| `backend/skills/giao-hang/SKILL.md` | **Mới** — SOP giao hàng (khai báo thuần) |
| `backend/skills/nhap-kho/SKILL.md` | **Mới** — SOP nhập kho (khai báo thuần) |
| `backend/skills/bao-gia-chiet-khau/SKILL.md` | **Mới** — prose SOP báo giá chiết khấu |
| `backend/skills/bao-gia-chiet-khau/logic.py` | **Mới** — bất biến tiền bạc, port ~109 dòng |
| `backend/src/agents/state.py` | **Sửa** — `ERPAgentState` thêm `sop: str \| None` |
| `backend/src/agents/prompts.py` | **Sửa** — `INTENT_ROUTER_PROMPT` đổi hợp đồng đầu ra sang 2 dòng; thêm `render_intent_router_prompt()` |
| `backend/src/agents/nodes.py` | **Sửa** — `make_intent_router_node` nhận worker block + tập sop hợp lệ, parse 2 trường |
| `backend/src/agents/graph.py` | **Sửa** — `_route_by_intent` hybrid, wiring node SOP + `agentic_context_sync` |
| `backend/evals/cases.py` | **Sửa** — thêm `SOP_SELECT_CASES`; chú thích ranh giới lên 2 case cũ |
| `backend/evals/run_eval.py` | **Sửa** — `eval_sop_select()` + đăng ký CLI |
| `backend/jobs/eval_gate.py` | **Sửa** — đăng ký set `sop_select` (gate tuyệt đối, không baseline) |
| `backend/tests/agents/test_agentic_context_sync.py` | **Mới** — port từ `D:\Project` |
| `backend/tests/agents/test_skill_manifest.py` | **Mới** |
| `backend/tests/agents/test_skill_loader.py` | **Mới** |
| `backend/tests/agents/test_skill_giao_hang.py` | **Mới** — port từ `test_skill_agentic_delivery.py` |
| `backend/tests/agents/test_skill_nhap_kho.py` | **Mới** — port từ `test_skill_agentic_warehouse_receiving.py` |
| `backend/tests/agents/test_skill_bao_gia_chiet_khau.py` | **Mới** — port từ `test_skill_agentic_discount_quote.py` |
| `backend/tests/agents/test_skill_giao_hang_flow.py` | **Mới** — port luồng ReAct (interrupt/resume) từ `D:\Project` |
| `backend/tests/agents/test_skill_nhap_kho_flow.py` | **Mới** — port luồng ReAct từ `D:\Project` |
| `backend/tests/agents/test_skill_bao_gia_chiet_khau_flow.py` | **Mới** — port luồng ReAct từ `D:\Project` |
| `backend/tests/agents/test_sop_select_gate.py` | **Mới** — đăng ký + công thức gate `sop_select` (không gọi LLM) |
| `backend/tests/agents/test_intent_router.py` | **Mở rộng** — parse 2 trường, fail an toàn |
| `backend/tests/agents/test_graph_build.py` | **Mở rộng** — wiring + bất biến bảo mật + bảng định tuyến |
| `backend/tests/agents/test_dau_cuoi_sop.py` | **Mới** — `@pytest.mark.live` flow SOP thật qua MCP + Odoo |

**Thứ tự phụ thuộc:** Task 1 độc lập. Task 2 → 3 → 4 → 5 (chuỗi loader).
Task 6, 7 cần 5. Task 8 → 9 cần 5. Task 10 cần 9. Task 11 cần tất cả.

---

### Task 1: Port `agentic_context_sync.py` + test của nó

Module này bàn giao state từ tier-2 về tier-1 sau khi một SOP chạy xong, và
scrub tên tool MCP rò ra câu trả lời cuối. Port **nguyên văn**, không sửa hành
vi — mọi phụ thuộc của nó đã có sẵn trong `D:\Youdoo`
(`tool_result._tool_result_text`, `tool_leak_guard.has_tool_leak`,
`working_context.derive_working_context` — đã xác minh tồn tại).

**Files:**
- Create: `backend/src/agents/agentic_context_sync.py`
- Create: `backend/tests/agents/test_agentic_context_sync.py`

**Interfaces:**
- Consumes: `src.agents.tool_result._tool_result_text`,
  `src.agents.tool_leak_guard.has_tool_leak` / `TOOL_LEAK_FALLBACK_MSG`,
  `src.agents.working_context.derive_working_context` (đều đã tồn tại)
- Produces: `make_agentic_context_sync_node() -> async (state) -> dict` — Task 9
  gắn nó làm node `"agentic_context_sync"`

- [ ] **Bước 1: Copy nguyên văn module nguồn**

Copy `D:\Project\backend\src\agents\agentic_context_sync.py` sang
`D:\Youdoo\backend\src\agents\agentic_context_sync.py`, **không sửa một ký tự
nào** (kể cả docstring — nó ghi lại residual risk có chủ đích của đường
interrupt). Các import tương đối (`.tool_result`, `.tool_leak_guard`,
`.working_context`) đã đúng cho Youdoo, không phải đổi.

```bash
cp /d/Project/backend/src/agents/agentic_context_sync.py \
   /d/Youdoo/backend/src/agents/agentic_context_sync.py
```

- [ ] **Bước 2: Copy test và sửa đường import**

Copy `D:\Project\backend\tests\agents\test_agentic_context_sync.py` sang
`D:\Youdoo\backend\tests\agents\test_agentic_context_sync.py`, rồi sửa:
- Xoá 2 dòng `import os, sys` + `sys.path.insert(...)` ở đầu file (nếu có).
- Đổi mọi `backend.src.` → `src.`.

- [ ] **Bước 3: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_agentic_context_sync.py -v`
Expected: PASS toàn bộ.

Nếu đỏ **vì đường import / tên module** → sửa nối dây. Nếu đỏ **vì hành vi**
→ DỪNG, ghi lại vào task report, không sửa test.

- [ ] **Bước 4: Commit**

```bash
git add backend/src/agents/agentic_context_sync.py backend/tests/agents/test_agentic_context_sync.py
git commit -m "feat(agents): port agentic_context_sync — bàn giao state tier-2 → tier-1"
```

---

### Task 2: `skill_manifest.py` — parse + validate cấu trúc từng file

Tách riêng khỏi loader có chủ đích: file này trả lời **"file này nói gì, có
hợp lệ về cấu trúc không"** — thuần túy, không import LangChain, không chạm MCP
registry, nên test chạy tức thì. Ràng buộc cần biết registry MCP (tool có thật
không) thuộc về Task 4.

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/src/agents/skill_manifest.py`
- Test: `backend/tests/agents/test_skill_manifest.py`

**Interfaces:**
- Consumes: không có (chỉ stdlib + PyYAML)
- Produces:
  - `class SkillManifestError(Exception)`
  - `@dataclass(frozen=True) WriteToolSpec(name: str, confirm: str, fixed_args: dict)`
  - `@dataclass(frozen=True) SkillSpec(name, description, prose, dir, read_tools, write_tools, entry, declares_tools, max_steps)`
    — `read_tools: tuple[str, ...]`, `write_tools: tuple[WriteToolSpec, ...]`,
    `entry: str | None`, `declares_tools: tuple[str, ...]`, `max_steps: int`,
    `dir: pathlib.Path`
  - `parse_skill_md(path: Path) -> SkillSpec`
  - `DEFAULT_MAX_STEPS = 15`, `MAX_STEPS_CAP = 25`
  - `MISSING_NEGATIVE_WARNING` (chuỗi định dạng dùng cho log cảnh báo)

- [ ] **Bước 1: Thêm PyYAML vào requirements.txt**

`backend/requirements.txt`, thêm vào cuối:

```
# PyYAML: đang có sẵn như dep bắc cầu (langchain), nay là dep TRỰC TIẾP —
# skill_manifest.py parse frontmatter SKILL.md bằng yaml.safe_load. Ghim
# tường minh để một lần gỡ dep bắc cầu không lặng lẽ làm app không lên.
PyYAML==6.0.3
```

Cài lại: `cd backend && pip install -r requirements.txt`

- [ ] **Bước 2: Viết test đỏ — parse một SKILL.md tối thiểu**

Tạo `backend/tests/agents/test_skill_manifest.py`:

```python
from pathlib import Path

import pytest

from src.agents.skill_manifest import (DEFAULT_MAX_STEPS, SkillManifestError,
                                       parse_skill_md)


def _write_skill(root: Path, name: str, frontmatter: str,
                 prose: str = "Bạn là trợ lý kho.") -> Path:
    """Dựng một thư mục skill giả trong tmp_path. Trả về đường dẫn SKILL.md."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{prose}\n", encoding="utf-8")
    return p


def test_parse_minimal_declarative_skill(tmp_path):
    p = _write_skill(tmp_path, "giao-hang", """
name: giao-hang
description: >-
  Dùng khi người dùng muốn THỰC HIỆN quy trình giao hàng.
  KHÔNG dùng khi: người dùng chỉ HỎI về quy trình.
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
""".strip(), prose="Bạn là trợ lý kho.\nQuy trình: 1. ...")
    spec = parse_skill_md(p)
    assert spec.name == "giao-hang"
    assert "KHÔNG dùng khi" in spec.description
    assert spec.prose.startswith("Bạn là trợ lý kho.")
    assert spec.read_tools == ("get_sale_order_detail",)
    assert len(spec.write_tools) == 1
    assert spec.write_tools[0].name == "deliver_order"
    assert spec.write_tools[0].confirm == "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
    assert spec.write_tools[0].fixed_args == {}
    assert spec.entry is None
    assert spec.max_steps == DEFAULT_MAX_STEPS
    assert spec.dir == p.parent
```

- [ ] **Bước 3: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_skill_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.skill_manifest'`

- [ ] **Bước 4: Viết `skill_manifest.py`**

Tạo `backend/src/agents/skill_manifest.py`:

```python
# backend/src/agents/skill_manifest.py
"""Đọc + validate CẤU TRÚC một file backend/skills/<tên>/SKILL.md.

Ranh giới trách nhiệm (cố ý tách khỏi skill_loader.py): file này chỉ trả lời
"file này nói gì, có hợp lệ về cấu trúc không" — thuần stdlib + PyYAML, không
import LangChain, không biết gì về registry MCP. Ràng buộc cần registry thật
(tool có tồn tại không, tham số confirm có khớp schema tool không) nằm ở
skill_loader.py.

Triết lý validate giống assert_embedding_marker(): thà app không lên còn hơn
lên sai. Mọi luật dưới đây dính tới THẨM QUYỀN hoặc tính đúng đắn cấu trúc →
raise. Ngoại lệ DUY NHẤT là vế "KHÔNG dùng khi" trong description: nó là chất
lượng prompt, không phải thẩm quyền — một description tồi làm SOP bị chọn nhầm,
và lớp phủ quyết tất định (graph._route_by_intent) cùng confirm-gate vẫn chặn
hậu quả. Chặn cứng ở đó sẽ biến một lỗi soạn thảo thành sự cố ngừng dịch vụ,
sai tỉ lệ → chỉ cảnh báo (xem skill_loader.load_skill_specs)."""
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Trần bước cho ReAct loop của một skill (mỗi chu kỳ agent→tools = 2 bước).
# Flow hợp lệ dài nhất hiện tại (nhap-kho: hỏi PO → hỏi số lượng → tra PO →
# [flag | hỏi QC → receive] → chốt) ≈ 6 lượt model ≈ 13 bước; 15 cho headroom.
DEFAULT_MAX_STEPS = 15
MAX_STEPS_CAP = 25

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

MISSING_NEGATIVE_WARNING = (
    "skill %r: description thiếu vế 'KHÔNG dùng khi' — SOP này dễ bị chọn "
    "nhầm cho câu hỏi VỀ quy trình. Vẫn nạp (xem docstring skill_manifest)."
)


class SkillManifestError(Exception):
    """SKILL.md sai cấu trúc/thẩm quyền — app KHÔNG được lên."""


@dataclass(frozen=True)
class WriteToolSpec:
    name: str            # tên tool MCP đã tồn tại — markdown KHÔNG định nghĩa tool mới
    confirm: str         # template câu xác nhận, nội suy tham số của chính tool đó
    fixed_args: dict = field(default_factory=dict)
    # fixed_args: tham số HẰNG do manifest ghim, model KHÔNG thấy và KHÔNG đặt
    # được. Có mặt vì wrapper viết tay cũ của nhap-kho ghim
    # model="purchase.order" cho flag_order_for_review — không có cơ chế này thì
    # skill đó không di trú nguyên vẹn được. Loader loại các khoá này khỏi
    # schema model nhìn thấy (skill_loader._visible_schema).


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    prose: str
    dir: Path
    read_tools: tuple[str, ...] = ()
    write_tools: tuple[WriteToolSpec, ...] = ()
    entry: str | None = None
    declares_tools: tuple[str, ...] = ()
    max_steps: int = DEFAULT_MAX_STEPS
    # frozen=True nhưng CÓ trường dict (WriteToolSpec.fixed_args): không bao giờ
    # hash SkillSpec/WriteToolSpec — chỉ dùng làm giá trị, không làm khoá dict.


def _require(cond, msg: str) -> None:
    if not cond:
        raise SkillManifestError(msg)


def _check_confirm_template(where: str, template: str) -> tuple[str, ...]:
    """Trả về tên các placeholder. Chỉ chấp nhận placeholder CÓ TÊN, không
    positional ({}, {0}), không attribute/index ({a.b}, {a[0]}) — câu xác nhận
    là thứ người dùng đọc trước khi cho ghi, không phải chỗ để chạy biểu thức."""
    names: list[str] = []
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as e:
        raise SkillManifestError(f"{where}: confirm không phải template hợp lệ: {e}")
    for _literal, fname, _spec, _conv in parsed:
        if fname is None:
            continue
        _require(fname != "", f"{where}: confirm dùng placeholder không tên '{{}}'")
        _require(fname.isidentifier(),
                 f"{where}: confirm chỉ được nội suy TÊN tham số, gặp '{{{fname}}}'")
        names.append(fname)
    return tuple(names)


def parse_skill_md(path: Path) -> SkillSpec:
    """Đọc 1 SKILL.md → SkillSpec đã validate cấu trúc. raise SkillManifestError."""
    path = Path(path)
    where = str(path)
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    _require(m is not None, f"{where}: thiếu frontmatter YAML (khối --- ... ---)")
    raw, prose = m.group(1), m.group(2).strip()

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise SkillManifestError(f"{where}: frontmatter không parse được: {e}")
    _require(isinstance(data, dict), f"{where}: frontmatter phải là mapping YAML")

    name = data.get("name")
    _require(isinstance(name, str) and name.strip(), f"{where}: thiếu 'name'")
    name = name.strip()
    _require(_NAME_RE.match(name), f"{where}: 'name' phải kebab-case, gặp {name!r}")
    _require(name == path.parent.name,
             f"{where}: 'name' ({name!r}) phải khớp tên thư mục "
             f"({path.parent.name!r}) — tên node graph lấy từ đây")

    description = data.get("description")
    _require(isinstance(description, str) and description.strip(),
             f"{where}: thiếu 'description'")
    description = " ".join(description.split())

    _require(prose, f"{where}: thiếu phần prose sau frontmatter "
                    "(prose LÀ system prompt của SOP)")

    tools = data.get("tools") or {}
    _require(isinstance(tools, dict), f"{where}: 'tools' phải là mapping")
    entry = data.get("entry")
    _require(entry is None or (isinstance(entry, str) and entry.strip()),
             f"{where}: 'entry' phải là tên file")

    raw_write = tools.get("write") or []
    _require(not (raw_write and entry),
             f"{where}: có CẢ 'tools.write' lẫn 'entry' — hai đường sinh tool "
             "trong một skill là chỗ để lọt gate")

    raw_read = tools.get("read") or []
    _require(isinstance(raw_read, list) and all(isinstance(x, str) for x in raw_read),
             f"{where}: 'tools.read' phải là danh sách tên tool")

    _require(isinstance(raw_write, list), f"{where}: 'tools.write' phải là danh sách")
    write_tools = []
    for item in raw_write:
        _require(isinstance(item, dict), f"{where}: mỗi mục 'tools.write' phải là mapping")
        wname = item.get("name")
        _require(isinstance(wname, str) and wname.strip(),
                 f"{where}: mục 'tools.write' thiếu 'name'")
        confirm = item.get("confirm")
        _require(isinstance(confirm, str) and confirm.strip(),
                 f"{where}: tool ghi {wname!r} thiếu 'confirm'")
        _check_confirm_template(f"{where}/{wname}", confirm)
        fixed = item.get("fixed_args") or {}
        _require(isinstance(fixed, dict) and all(isinstance(k, str) for k in fixed),
                 f"{where}: tool ghi {wname!r} có 'fixed_args' không phải mapping tên→giá trị")
        write_tools.append(WriteToolSpec(wname.strip(), confirm, dict(fixed)))

    declares = data.get("declares_tools") or []
    _require(isinstance(declares, list) and all(isinstance(x, str) for x in declares),
             f"{where}: 'declares_tools' phải là danh sách tên tool")
    _require(bool(entry) == bool(declares),
             f"{where}: 'entry' và 'declares_tools' phải đi CÙNG NHAU — thiếu một "
             "vế nghĩa là logic.py có thể lặng lẽ mở thêm tool mà frontmatter không khai")

    max_steps = data.get("max_steps", DEFAULT_MAX_STEPS)
    _require(isinstance(max_steps, int) and not isinstance(max_steps, bool)
             and max_steps > 0,
             f"{where}: 'max_steps' phải là số nguyên dương")
    _require(max_steps <= MAX_STEPS_CAP,
             f"{where}: 'max_steps'={max_steps} vượt trần cứng {MAX_STEPS_CAP}")

    return SkillSpec(name=name, description=description, prose=prose,
                     dir=path.parent, read_tools=tuple(raw_read),
                     write_tools=tuple(write_tools), entry=entry,
                     declares_tools=tuple(declares), max_steps=max_steps)
```

- [ ] **Bước 5: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_manifest.py -v`
Expected: PASS

- [ ] **Bước 6: Viết test cho MỌI luật chặn cứng**

Thêm vào `backend/tests/agents/test_skill_manifest.py`:

```python
def test_reject_missing_name(tmp_path):
    p = _write_skill(tmp_path, "x", 'description: "Dùng khi X. KHÔNG dùng khi: Y."')
    with pytest.raises(SkillManifestError, match="thiếu 'name'"):
        parse_skill_md(p)


def test_reject_missing_description(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x")
    with pytest.raises(SkillManifestError, match="thiếu 'description'"):
        parse_skill_md(p)


def test_reject_name_not_matching_directory(tmp_path):
    p = _write_skill(tmp_path, "giao-hang", "name: nhap-kho\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="phải khớp tên thư mục"):
        parse_skill_md(p)


def test_reject_name_not_kebab_case(tmp_path):
    p = _write_skill(tmp_path, "Giao_Hang", "name: Giao_Hang\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="kebab-case"):
        parse_skill_md(p)


def test_reject_both_write_and_entry(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
entry: logic.py
declares_tools: [t]
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order_ref}?"
""".strip())
    with pytest.raises(SkillManifestError, match="hai đường sinh tool"):
        parse_skill_md(p)


def test_reject_entry_without_declares_tools(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nentry: logic.py")
    with pytest.raises(SkillManifestError, match="phải đi CÙNG NHAU"):
        parse_skill_md(p)


def test_reject_declares_tools_without_entry(tmp_path):
    p = _write_skill(tmp_path, "x",
                     "name: x\ndescription: Dùng khi X.\ndeclares_tools: [t]")
    with pytest.raises(SkillManifestError, match="phải đi CÙNG NHAU"):
        parse_skill_md(p)


def test_reject_max_steps_above_cap(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nmax_steps: 26")
    with pytest.raises(SkillManifestError, match="vượt trần cứng 25"):
        parse_skill_md(p)


def test_accept_max_steps_at_cap(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nmax_steps: 25")
    assert parse_skill_md(p).max_steps == 25


def test_reject_write_tool_missing_confirm(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
""".strip())
    with pytest.raises(SkillManifestError, match="thiếu 'confirm'"):
        parse_skill_md(p)


def test_reject_confirm_with_positional_placeholder(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {}?"
""".strip())
    with pytest.raises(SkillManifestError, match="placeholder không tên"):
        parse_skill_md(p)


def test_reject_confirm_with_attribute_access(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order.ref}?"
""".strip())
    with pytest.raises(SkillManifestError, match="chỉ được nội suy TÊN tham số"):
        parse_skill_md(p)


def test_reject_missing_frontmatter(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    p = d / "SKILL.md"
    p.write_text("Bạn là trợ lý kho.\n", encoding="utf-8")
    with pytest.raises(SkillManifestError, match="thiếu frontmatter"):
        parse_skill_md(p)


def test_reject_empty_prose(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.", prose="")
    with pytest.raises(SkillManifestError, match="thiếu phần prose"):
        parse_skill_md(p)


def test_fixed_args_parsed(tmp_path):
    p = _write_skill(tmp_path, "nhap-kho", """
name: nhap-kho
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: flag_order_for_review
      confirm: 'Xác nhận GHI CHÚ lên đơn mua {order_ref}: "{note}"?'
      fixed_args:
        model: purchase.order
""".strip())
    spec = parse_skill_md(p)
    assert spec.write_tools[0].fixed_args == {"model": "purchase.order"}
```

- [ ] **Bước 7: Chạy toàn bộ test manifest, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_manifest.py -v`
Expected: PASS toàn bộ (16 test).

- [ ] **Bước 8: Commit**

```bash
git add backend/requirements.txt backend/src/agents/skill_manifest.py backend/tests/agents/test_skill_manifest.py
git commit -m "feat(skills): skill_manifest — parse + validate cấu trúc SKILL.md"
```

---

### Task 3: `skill_loader.py` phần A — quét thư mục, validate liên-file, khối mô tả worker

Phần này vẫn thuần spec-level: không chạm MCP, không chạm LLM. Nó biết cả **tập
hợp** skill nên bắt được trùng tên và va tên với node tier-1; và nó kết xuất
**khối mô tả worker** trung lập theo hợp đồng §8 với SP-2b.

**Files:**
- Create: `backend/src/agents/skill_loader.py`
- Test: `backend/tests/agents/test_skill_loader.py`

**Interfaces:**
- Consumes: `skill_manifest.parse_skill_md`, `SkillSpec`, `SkillManifestError`,
  `MISSING_NEGATIVE_WARNING`; `write_registry.WRITE_COORDINATORS`
- Produces:
  - `SKILLS_DIR: Path` — `backend/skills`, suy từ `__file__`, KHÔNG từ cwd
  - `RESERVED_NODE_NAMES: frozenset[str]`
  - `load_skill_specs(skills_dir: Path | None = None) -> list[SkillSpec]`
    (sắp xếp theo `name` để thứ tự node/prompt tất định)
  - `render_worker_block(specs) -> str` (rỗng khi `specs` rỗng)

- [ ] **Bước 1: Viết test đỏ**

Tạo `backend/tests/agents/test_skill_loader.py`:

```python
import logging
from pathlib import Path

import pytest

from src.agents.skill_manifest import SkillManifestError
from src.agents.skill_loader import (RESERVED_NODE_NAMES, SKILLS_DIR,
                                     load_skill_specs, render_worker_block)


def _write_skill(root: Path, name: str, frontmatter: str,
                 prose: str = "Bạn là trợ lý kho.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{prose}\n",
                                encoding="utf-8")
    return d


_OK = 'name: {n}\ndescription: "Dùng khi THỰC HIỆN {n}. KHÔNG dùng khi: chỉ HỎI về {n}."'


def test_skills_dir_is_backend_skills_and_cwd_independent():
    # Suy từ __file__ chứ KHÔNG từ cwd: run.py chạy với cwd=backend/, pytest
    # chạy với cwd=backend/, nhưng jobs/CLI có thể chạy từ gốc repo.
    assert SKILLS_DIR.name == "skills"
    assert SKILLS_DIR.parent.name == "backend"


def test_load_returns_specs_sorted_by_name(tmp_path):
    _write_skill(tmp_path, "nhap-kho", _OK.format(n="nhap-kho"))
    _write_skill(tmp_path, "giao-hang", _OK.format(n="giao-hang"))
    specs = load_skill_specs(tmp_path)
    assert [s.name for s in specs] == ["giao-hang", "nhap-kho"]


def test_load_empty_dir_returns_empty(tmp_path):
    assert load_skill_specs(tmp_path) == []


def test_load_missing_dir_returns_empty(tmp_path):
    assert load_skill_specs(tmp_path / "khong-ton-tai") == []


def test_reject_name_colliding_with_tier1_node(tmp_path):
    _write_skill(tmp_path, "erp_read", "name: erp_read\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="kebab-case"):
        load_skill_specs(tmp_path)


def test_reject_name_in_reserved_set(tmp_path):
    # "mixed" là kebab-case hợp lệ NHƯNG trùng tên một node tier-1.
    _write_skill(tmp_path, "mixed", "name: mixed\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="trùng tên node tier-1"):
        load_skill_specs(tmp_path)


def test_reserved_set_covers_every_tier1_node():
    from src.agents.write_registry import WRITE_COORDINATORS
    assert {"intent_router", "erp_read", "erp_write", "rag", "mixed", "unknown",
            "erp_write_planner", "erp_write_executor", "respond_unknown",
            "write_continuation", "agentic_context_sync"} <= RESERVED_NODE_NAMES
    assert {s.node for s in WRITE_COORDINATORS.values()} <= RESERVED_NODE_NAMES


def test_reject_entry_file_missing(tmp_path):
    _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    with pytest.raises(SkillManifestError, match="entry 'logic.py' không tồn tại"):
        load_skill_specs(tmp_path)


def test_warns_but_loads_when_description_lacks_negative_clause(tmp_path, caplog):
    _write_skill(tmp_path, "giao-hang",
                 "name: giao-hang\ndescription: Dùng khi giao hàng.")
    with caplog.at_level(logging.WARNING):
        specs = load_skill_specs(tmp_path)
    assert [s.name for s in specs] == ["giao-hang"]      # VẪN NẠP
    assert "KHÔNG dùng khi" in caplog.text               # nhưng có cảnh báo


def test_render_worker_block_shape(tmp_path):
    _write_skill(tmp_path, "giao-hang", _OK.format(n="giao-hang"))
    _write_skill(tmp_path, "nhap-kho", _OK.format(n="nhap-kho"))
    block = render_worker_block(load_skill_specs(tmp_path))
    assert "worker: giao-hang" in block
    assert "worker: nhap-kho" in block
    assert "mô tả: Dùng khi THỰC HIỆN giao-hang." in block
    # thứ tự tất định — cùng thứ tự với load_skill_specs
    assert block.index("worker: giao-hang") < block.index("worker: nhap-kho")


def test_render_worker_block_empty_when_no_skills():
    assert render_worker_block([]) == ""
```

- [ ] **Bước 2: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.skill_loader'`

- [ ] **Bước 3: Viết phần A của `skill_loader.py`**

Tạo `backend/src/agents/skill_loader.py`:

```python
# backend/src/agents/skill_loader.py
"""Nạp SOP skill dạng thư mục (backend/skills/<tên>/SKILL.md) thành node graph.

Biên giới thẩm quyền — toàn bộ mô hình trong một câu:

    Sửa SKILL.md chỉ có thể thay đổi THỨ TỰ và ĐIỀU KIỆN gọi những tool đã
    được gate sẵn — không bao giờ thêm được thẩm quyền mới.

Cụ thể: markdown KHÔNG BAO GIỜ định nghĩa tool mới. Tool ghi luôn là wrapper do
chính file này sinh, luôn bọc _confirm_write, và schema tham số CHÉP TỪ tool
MCP thật chứ không do markdown khai. Prose bảo model "bỏ qua xác nhận" là vô
hiệu — gate nằm trong Python, không nằm trong prose.

Chạy đúng MỘT LẦN lúc build_graph()."""
import importlib.util
import logging
import sys
from pathlib import Path

from .skill_manifest import (MISSING_NEGATIVE_WARNING, SkillManifestError,
                             SkillSpec, parse_skill_md)
from .write_registry import WRITE_COORDINATORS

logger = logging.getLogger(__name__)

# Suy từ __file__ (backend/src/agents/skill_loader.py → backend/skills), KHÔNG
# từ cwd: run.py chạy với cwd=backend/, nhưng `python -m jobs run ...` có thể
# chạy từ gốc repo.
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# Tên node SOP không được trùng bất kỳ node tier-1 nào (5 intent + các node
# hạ tầng + coordinator ghi). Trùng là lỗi cấu hình làm hỏng bảng định tuyến,
# không phải chuyện thẩm mỹ.
RESERVED_NODE_NAMES = frozenset({
    "intent_router", "erp_read", "erp_write", "rag", "mixed", "unknown",
    "erp_write_planner", "erp_write_executor", "respond_unknown",
    "write_continuation", "agentic_context_sync",
}) | {spec.node for spec in WRITE_COORDINATORS.values()}


def load_skill_specs(skills_dir: Path | None = None) -> list[SkillSpec]:
    """Quét <skills_dir>/*/SKILL.md → list[SkillSpec] đã validate, sắp theo name.

    Thư mục không tồn tại / rỗng → []. Mọi vi phạm THẨM QUYỀN hoặc cấu trúc →
    SkillManifestError (app không lên). Ngoại lệ duy nhất: description thiếu vế
    "KHÔNG dùng khi" chỉ log WARNING và vẫn nạp — xem docstring skill_manifest."""
    root = Path(skills_dir) if skills_dir is not None else SKILLS_DIR
    if not root.is_dir():
        return []

    specs: list[SkillSpec] = []
    seen: dict[str, Path] = {}
    for md in sorted(root.glob("*/SKILL.md")):
        spec = parse_skill_md(md)
        if spec.name in RESERVED_NODE_NAMES:
            raise SkillManifestError(
                f"{md}: skill {spec.name!r} trùng tên node tier-1 — "
                "bảng định tuyến không phân biệt được")
        if spec.name in seen:
            raise SkillManifestError(
                f"{md}: skill {spec.name!r} trùng tên với {seen[spec.name]}")
        if spec.entry and not (spec.dir / spec.entry).is_file():
            raise SkillManifestError(
                f"{md}: entry {spec.entry!r} không tồn tại trong {spec.dir}")
        if "KHÔNG dùng khi" not in spec.description:
            logger.warning(MISSING_NEGATIVE_WARNING, spec.name)
        seen[spec.name] = md
        specs.append(spec)

    specs.sort(key=lambda s: s.name)
    return specs


def render_worker_block(specs) -> str:
    """Khối mô tả worker TRUNG LẬP (hợp đồng §8 với SP-2b).

    SP-2a: intent_router tiêu thụ khối này (nối vào cuối prompt).
    SP-2b: supervisor tiêu thụ CÙNG khối đó; intent_router bị hấp thụ.
    Khối cố ý không nhắc gì tới 'intent' hay 'router' để 5 intent tier-1 sau
    này khai báo được cùng dạng — nếu không, SP-2b sẽ phải gộp hai danh sách
    worker."""
    if not specs:
        return ""
    entries = "\n\n".join(f"worker: {s.name}\nmô tả: {s.description}" for s in specs)
    return f"Danh sách worker quy trình nghiệp vụ (SOP):\n\n{entries}"
```

- [ ] **Bước 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -v`
Expected: PASS toàn bộ (11 test).

- [ ] **Bước 5: Commit**

```bash
git add backend/src/agents/skill_loader.py backend/tests/agents/test_skill_loader.py
git commit -m "feat(skills): skill_loader phần A — quét thư mục, validate liên-file, khối worker"
```

---

### Task 4: `skill_loader.py` phần B — sinh tool ghi đã gate + nạp `logic.py`

Đây là lõi an toàn của cả SP-2a. Hai đường sinh tool, loại trừ nhau:
`tools.write` (loader sinh wrapper) **hoặc** `entry: logic.py` (skill tự sinh,
loader đối chiếu với `declares_tools`).

**Files:**
- Modify: `backend/src/agents/skill_loader.py`
- Test: `backend/tests/agents/test_skill_loader.py` (mở rộng)

**Interfaces:**
- Consumes: `agentic_gate.ask_human` / `_confirm_write` / `REFUSED_MSG` (đã có
  trong repo), `erp_query.tools.build_erp_query_tools`
- Produces: `build_skill_tools(spec: SkillSpec, mcp_tools: list) -> list` —
  Task 5 dùng để dựng node

**Quyết định phải hiểu trước khi viết mã — registry MCP rỗng:**
`build_graph(llm, tools=[], checkpointer=None)` là đường **test**, không phải
đường production: `ERPAgent.setup()` gọi `await client.get_tools()` **trước**
`build_graph`, và lệnh đó ném lỗi nếu MCP sập — nên production không bao giờ tới
`build_graph` với registry rỗng. Vì vậy: **registry rỗng = không có hợp đồng MCP
để đối chiếu** (bỏ qua kiểm tra tồn tại, node dựng với `ask_human` + tool đọc);
**registry KHÔNG rỗng mà thiếu tool đã khai = fail-loud**. Hành vi này khớp
đúng cách tier-1 đã đối xử với `tools` rỗng (`make_erp_write_executor_node([])`).

- [ ] **Bước 1: Viết test đỏ cho wrapper sinh tự động**

Thêm vào `backend/tests/agents/test_skill_loader.py`:

```python
import json
from unittest.mock import patch

from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import build_skill_tools
from src.agents.skill_manifest import parse_skill_md


def _fake_mcp_tools():
    """Fake tool MCP có ghi nhận lệnh gọi — schema khai TRÙNG tool thật
    (deliver_order(order_ref), flag_order_for_review(model, order_ref, note))."""
    calls = {"deliver": [], "flag": []}

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """Xác nhận giao hàng vào Odoo cho một đơn bán ĐÃ XÁC NHẬN."""
        calls["deliver"].append({"order_ref": order_ref})
        return json.dumps({"ok": True, "display": "Đã giao hàng."}, ensure_ascii=False)

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """Ghi chú nội bộ lên đơn."""
        calls["flag"].append({"model": model, "order_ref": order_ref, "note": note})
        return json.dumps({"ok": True, "display": "Đã ghi chú."}, ensure_ascii=False)

    return [deliver_order, flag_order_for_review], calls


_GIAO_HANG = """
name: giao-hang
description: "Dùng khi THỰC HIỆN giao hàng. KHÔNG dùng khi: chỉ HỎI về quy trình."
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
""".strip()


def _spec(tmp_path, name, frontmatter):
    return parse_skill_md(_write_skill(tmp_path, name, frontmatter) / "SKILL.md")


@pytest.mark.asyncio
async def test_generated_wrapper_asks_exact_confirm_then_writes_once(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}
    assert set(tools) == {"ask_human", "get_sale_order_detail", "deliver_order"}

    asked = []

    def _yes(question):
        asked.append(question)
        return True

    with patch("src.agents.skill_loader._confirm_write", _yes):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert asked == ["Xác nhận GIAO HÀNG cho đơn bán S00012?"]
    assert calls["deliver"] == [{"order_ref": "S00012"}]
    assert "Đã giao hàng." in out


@pytest.mark.asyncio
async def test_generated_wrapper_refuses_without_calling_mcp(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}

    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert out == REFUSED_MSG
    assert calls["deliver"] == []       # KHÔNG một lệnh ghi nào chạm MCP


@pytest.mark.asyncio
async def test_fixed_args_merged_into_payload_and_hidden_from_model(tmp_path):
    spec = _spec(tmp_path, "nhap-kho", """
name: nhap-kho
description: "Dùng khi THỰC HIỆN nhập kho. KHÔNG dùng khi: chỉ HỎI về quy trình."
tools:
  write:
    - name: flag_order_for_review
      confirm: 'Xác nhận GHI CHÚ lên đơn mua {order_ref}: "{note}"?'
      fixed_args:
        model: purchase.order
""".strip())
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}
    flag = tools["flag_order_for_review"]

    # model KHÔNG nằm trong schema model nhìn thấy. Dùng .args (không
    # .args_schema): .args trả dict properties cho CẢ hai hình dạng schema
    # (dict của tool MCP thật, và lớp pydantic của @tool trong test này).
    assert set(flag.args) == {"order_ref", "note"}

    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await flag.ainvoke({"order_ref": "P00021", "note": "thiếu 2 cái"})

    # ...nhưng VẪN đi vào payload gửi MCP
    assert calls["flag"] == [{"model": "purchase.order", "order_ref": "P00021",
                              "note": "thiếu 2 cái"}]
    assert asked == ['Xác nhận GHI CHÚ lên đơn mua P00021: "thiếu 2 cái"?']


def test_reject_write_tool_absent_from_nonempty_mcp_registry(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, _ = _fake_mcp_tools()
    other = [t for t in mcp if t.name != "deliver_order"]
    with pytest.raises(SkillManifestError, match="deliver_order"):
        build_skill_tools(spec, other)


def test_empty_mcp_registry_builds_read_only_node(tmp_path):
    # Đường TEST (build_graph(tools=[])): không có hợp đồng MCP để đối chiếu →
    # không có tool ghi nào, và KHÔNG raise.
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    names = {t.name for t in build_skill_tools(spec, [])}
    assert names == {"ask_human", "get_sale_order_detail"}


def test_reject_unknown_read_tool(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  read: [khong_co_tool_nay]
""".strip())
    with pytest.raises(SkillManifestError, match="khong_co_tool_nay"):
        build_skill_tools(spec, [])


def test_reject_confirm_placeholder_not_a_tool_param(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận cho {khach_hang}?"
""".strip())
    mcp, _ = _fake_mcp_tools()
    with pytest.raises(SkillManifestError, match="khach_hang"):
        build_skill_tools(spec, mcp)


def test_reject_fixed_arg_not_a_tool_param(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order_ref}?"
      fixed_args:
        khong_co: 1
""".strip())
    mcp, _ = _fake_mcp_tools()
    with pytest.raises(SkillManifestError, match="khong_co"):
        build_skill_tools(spec, mcp)


def test_entry_logic_py_tools_loaded(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    @tool('create_discount_quote')\n"
        "    async def t(customer: str) -> str:\n"
        "        '''fake'''\n"
        "        return 'ok'\n"
        "    return [t]\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    names = {t.name for t in build_skill_tools(spec, [])}
    assert names == {"ask_human", "create_discount_quote"}


def test_reject_logic_py_returning_undeclared_tool(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    @tool('create_discount_quote')\n"
        "    async def a(customer: str) -> str:\n"
        "        '''fake'''\n"
        "        return 'ok'\n"
        "    @tool('xoa_sach_don_hang')\n"
        "    async def b(x: str) -> str:\n"
        "        '''tool KHÔNG khai trong frontmatter'''\n"
        "        return 'ok'\n"
        "    return [a, b]\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    with pytest.raises(SkillManifestError, match="xoa_sach_don_hang"):
        build_skill_tools(spec, [])


def test_reject_logic_py_without_build_tools(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text("X = 1\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    with pytest.raises(SkillManifestError, match="build_tools"):
        build_skill_tools(spec, [])
```

- [ ] **Bước 2: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_skill_tools'`

- [ ] **Bước 3: Thêm phần B vào `skill_loader.py`**

Sửa khối import ở đầu `backend/src/agents/skill_loader.py` thành:

```python
import importlib.util
import logging
import string
import sys
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import create_model

from .agentic_gate import REFUSED_MSG, _confirm_write, ask_human
from .skill_manifest import (MISSING_NEGATIVE_WARNING, SkillManifestError,
                             SkillSpec, parse_skill_md)
from .write_registry import WRITE_COORDINATORS
from ..erp_query.tools import build_erp_query_tools
```

Thêm vào cuối file:

```python
def _param_names(mcp_tool) -> set[str]:
    """Tên tham số tool MCP. langchain-mcp-adapters đặt args_schema = chính
    JSON Schema (dict) của MCP inputSchema; tool @tool thuần Python thì
    args_schema là lớp pydantic. Đỡ cả hai."""
    schema = mcp_tool.args_schema
    if isinstance(schema, dict):
        return set((schema.get("properties") or {}).keys())
    return set(getattr(schema, "model_fields", {}).keys())


def _visible_schema(mcp_tool, fixed: dict):
    """Schema model NHÌN THẤY = schema tool MCP TRỪ các khoá fixed_args.

    Markdown không có quyền mô tả tham số của một tool ghi — schema chép từ
    chính tool MCP. Việc DUY NHẤT manifest được làm là GIẤU bớt tham số bằng
    cách ghim giá trị hằng cho nó (fixed_args); giấu đi thì model không đặt
    được, nên đây là thu hẹp thẩm quyền, không phải mở rộng.

    Đỡ CẢ HAI hình dạng args_schema, không phải để tổng quát hoá vu vơ mà vì
    hai đường đều xảy ra thật: langchain-mcp-adapters gán args_schema = chính
    JSON Schema (DICT) của MCP inputSchema (tools.py:531) — đường production;
    còn tool dựng bằng @tool trong test cho ra LỚP PYDANTIC."""
    schema = mcp_tool.args_schema
    if not fixed:
        return schema
    if isinstance(schema, dict):
        out = dict(schema)
        out["properties"] = {k: v for k, v in (out.get("properties") or {}).items()
                             if k not in fixed}
        required = [r for r in (out.get("required") or []) if r not in fixed]
        if required:
            out["required"] = required
        else:
            out.pop("required", None)
        return out
    kept = {n: (f.annotation, f) for n, f in schema.model_fields.items()
            if n not in fixed}
    return create_model(f"{mcp_tool.name}_visible_args", **kept)


def _make_gated_write_tool(mcp_tool, wspec):
    """Sinh wrapper CÙNG TÊN bọc _confirm_write quanh một tool ghi MCP.

    Đây là boilerplate mà 3 skill viết tay ở D:\\Project đang chép đi chép lại
    (lấy tool theo tên → bọc _confirm_write → ainvoke). Sinh tự động để không
    có đường nào quên gate: model KHÔNG BAO GIỜ thấy tool ghi thô (chỉ wrapper
    này được bind vào create_agent), nên không có đường vòng bỏ qua cổng."""

    async def _gated(**kwargs) -> str:
        if not _confirm_write(wspec.confirm.format(**kwargs, **wspec.fixed_args)):
            return REFUSED_MSG
        return await mcp_tool.ainvoke({**kwargs, **wspec.fixed_args})

    return StructuredTool.from_function(
        func=None, coroutine=_gated, name=mcp_tool.name,
        description=mcp_tool.description,
        args_schema=_visible_schema(mcp_tool, wspec.fixed_args))


def _load_entry_module(spec: SkillSpec):
    path = spec.dir / spec.entry
    mod_name = f"youdoo_skill_{spec.name.replace('-', '_')}"
    mod_spec = importlib.util.spec_from_file_location(mod_name, path)
    if mod_spec is None or mod_spec.loader is None:
        raise SkillManifestError(f"{path}: không nạp được entry module")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_name] = module
    mod_spec.loader.exec_module(module)
    if not callable(getattr(module, "build_tools", None)):
        raise SkillManifestError(
            f"{path}: entry phải cung cấp hàm build_tools(mcp_tools) -> list[BaseTool]")
    return module


def build_skill_tools(spec: SkillSpec, mcp_tools) -> list:
    """Tool của một node SOP: ask_human + tool đọc + (wrapper ghi ĐÃ GATE
    HOẶC tool do entry sinh). ask_human luôn được cấp, không cần khai — mọi SOP
    đều cần, bắt khai chỉ tạo chỗ để quên.

    registry MCP RỖNG = đường test (build_graph(tools=[])), không phải đường
    production: ERPAgent.setup() gọi await client.get_tools() TRƯỚC build_graph
    và lệnh đó ném lỗi nếu MCP sập, nên production không bao giờ tới đây với
    registry rỗng. Rỗng → không có hợp đồng MCP để đối chiếu, bỏ qua kiểm tra
    tồn tại, dựng node chỉ-đọc. KHÔNG rỗng mà thiếu tool đã khai → fail-loud."""
    by_name = {t.name: t for t in mcp_tools}
    read_by_name = {t.name: t for t in build_erp_query_tools()}

    tools = [ask_human]
    for rname in spec.read_tools:
        if rname not in read_by_name:
            raise SkillManifestError(
                f"skill {spec.name!r}: tool đọc {rname!r} không có trong "
                "build_erp_query_tools()")
        tools.append(read_by_name[rname])

    if spec.entry:
        module = _load_entry_module(spec)
        produced = list(module.build_tools(mcp_tools))
        allowed = set(spec.declares_tools) | {"ask_human"}
        extra = sorted({t.name for t in produced} - allowed)
        # Chỉ chặn chiều LEO THANG (trả tool KHÔNG khai). Chiều thiếu là hợp lệ:
        # registry MCP rỗng thì build_tools() không dựng được tool ghi nào.
        if extra:
            raise SkillManifestError(
                f"skill {spec.name!r}: entry {spec.entry!r} trả tool không khai "
                f"trong declares_tools: {extra}")
        tools.extend(t for t in produced if t.name != "ask_human")
        return tools

    for wspec in spec.write_tools:
        mcp_tool = by_name.get(wspec.name)
        if mcp_tool is None:
            if not by_name:
                continue          # registry rỗng — xem docstring
            raise SkillManifestError(
                f"skill {spec.name!r}: tool ghi {wspec.name!r} không có trong "
                "registry MCP")
        params = _param_names(mcp_tool)
        unknown_fixed = sorted(set(wspec.fixed_args) - params)
        if unknown_fixed:
            raise SkillManifestError(
                f"skill {spec.name!r}/{wspec.name}: fixed_args {unknown_fixed} "
                f"không phải tham số của tool đó (tham số hợp lệ: {sorted(params)})")
        placeholders = {f for _l, f, _s, _c in string.Formatter().parse(wspec.confirm)
                        if f}
        unknown_ph = sorted(placeholders - params)
        if unknown_ph:
            raise SkillManifestError(
                f"skill {spec.name!r}/{wspec.name}: confirm nội suy {unknown_ph} "
                f"không phải tham số của tool đó (tham số hợp lệ: {sorted(params)})")
        tools.append(_make_gated_write_tool(mcp_tool, wspec))

    return tools
```

- [ ] **Bước 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -v`
Expected: PASS toàn bộ.

Nếu `StructuredTool.from_function(func=None, coroutine=...)` báo lỗi ở
langchain-core 1.4.8, đổi sang dựng trực tiếp
`StructuredTool(name=..., description=..., args_schema=..., coroutine=_gated)`
và chạy lại — hai đường đều hợp lệ, chỉ khác API bề mặt.

- [ ] **Bước 5: Commit**

```bash
git add backend/src/agents/skill_loader.py backend/tests/agents/test_skill_loader.py
git commit -m "feat(skills): sinh wrapper ghi đã gate + nạp entry logic.py"
```

---

### Task 5: `skill_loader.py` phần C — dựng node

**Files:**
- Modify: `backend/src/agents/skill_loader.py`
- Test: `backend/tests/agents/test_skill_loader.py` (mở rộng)

**Interfaces:**
- Consumes: `langchain.agents.create_agent`, `build_skill_tools` (Task 4)
- Produces: `build_skill_node(spec: SkillSpec, llm, mcp_tools) -> CompiledStateGraph`
  — Task 9 gọi trong `build_graph()`

- [ ] **Bước 1: Viết test đỏ**

Thêm vào `backend/tests/agents/test_skill_loader.py`:

```python
from unittest.mock import MagicMock

from src.agents.skill_loader import build_skill_node


def test_build_skill_node_uses_prose_as_system_prompt_and_binds_gated_tools(
        tmp_path, monkeypatch):
    import src.agents.skill_loader as loader_mod
    captured = {}

    def fake_create_agent(llm, tools, system_prompt=None):
        captured["llm"] = llm
        captured["tools"] = [t.name for t in tools]
        captured["system_prompt"] = system_prompt
        return MagicMock()

    monkeypatch.setattr(loader_mod, "create_agent", fake_create_agent)
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    llm = MagicMock()
    build_skill_node(spec, llm, _fake_mcp_tools()[0])

    assert captured["llm"] is llm
    assert captured["system_prompt"] == spec.prose
    assert set(captured["tools"]) == {"ask_human", "get_sale_order_detail",
                                      "deliver_order"}


def test_build_skill_node_applies_recursion_limit_at_wiring(tmp_path, monkeypatch):
    # Spike v10b: KHÔNG có trần này thì subgraph chạy KHÔNG GIỚI HẠN — mặc định
    # 25 của LangGraph không truyền vào subgraph-as-node. Phải áp bằng
    # .with_config TẠI wiring, không trong hàm dựng agent.
    import src.agents.skill_loader as loader_mod
    compiled = MagicMock()
    monkeypatch.setattr(loader_mod, "create_agent",
                        lambda llm, tools, system_prompt=None: compiled)
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG + "\nmax_steps: 20")
    node = build_skill_node(spec, MagicMock(), [])
    compiled.with_config.assert_called_once_with({"recursion_limit": 20})
    assert node is compiled.with_config.return_value
```

- [ ] **Bước 2: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -k build_skill_node -v`
Expected: FAIL — `ImportError: cannot import name 'build_skill_node'`

- [ ] **Bước 3: Thêm `build_skill_node`**

Thêm `from langchain.agents import create_agent` vào khối import của
`backend/src/agents/skill_loader.py`, rồi thêm vào cuối file:

```python
def build_skill_node(spec: SkillSpec, llm, mcp_tools):
    """Node SOP = CompiledStateGraph của create_agent, TRẢ VỀ TRỰC TIẾP.

    Node này PHẢI được add_node thẳng vào graph ngoài — không bao giờ bọc trong
    một hàm async viết tay. Đó là điều kiện để interrupt() bên trong tool của nó
    (ask_human / _confirm_write) compose đúng với checkpointer của graph ngoài.

    .with_config áp TẠI ĐÂY (wiring), không trong create_agent: spike v10 chứng
    minh binding giữ nguyên interrupt/resume; spike v10b chứng minh KHÔNG có nó
    thì subgraph chạy không giới hạn (mặc định 25 của LangGraph không truyền
    vào subgraph-as-node, chỉ giá trị tường minh trong config mới kế thừa)."""
    agent = create_agent(llm, build_skill_tools(spec, mcp_tools),
                         system_prompt=spec.prose)
    return agent.with_config({"recursion_limit": spec.max_steps})
```

- [ ] **Bước 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_loader.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 5: Commit**

```bash
git add backend/src/agents/skill_loader.py backend/tests/agents/test_skill_loader.py
git commit -m "feat(skills): build_skill_node — create_agent + recursion_limit tại wiring"
```

---

### Task 6: Di trú `giao-hang` và `nhap-kho` (khai báo thuần)

Hai skill này là boilerplate gần như y hệt nhau ở repo nguồn → sinh từ manifest
được 100%. Prose chép **nguyên văn** `SOP_PROMPT` của module gốc.

**Files:**
- Create: `backend/skills/giao-hang/SKILL.md`
- Create: `backend/skills/nhap-kho/SKILL.md`
- Create: `backend/tests/agents/test_skill_giao_hang.py`
- Create: `backend/tests/agents/test_skill_nhap_kho.py`

**Interfaces:**
- Consumes: `skill_loader.load_skill_specs`, `build_skill_tools`, `build_skill_node`
- Produces: 2 thư mục skill trên đĩa — Task 9 nạp chúng thành node graph

**Về "test tương đương hành vi" (§6.2):** module gốc
`skill_agentic_delivery.py` / `skill_agentic_warehouse_receiving.py` **không tồn
tại trong `D:\Youdoo`** (cố ý không port ở SP-1B), nên không thể import để so
sánh trực tiếp. Tương đương được chốt bằng cách khác, chặt hơn: assert **đúng
nguyên văn** 3 thứ quan sát được — câu xác nhận đã nội suy, `REFUSED_MSG`, và
payload `ainvoke` — với chuỗi kỳ vọng **chép từ mã nguồn `D:\Project`** (đường
dẫn + số dòng ghi trong test). Đó là toàn bộ bề mặt hành vi của wrapper cũ.

- [ ] **Bước 1: Tạo `backend/skills/giao-hang/SKILL.md`**

```markdown
---
name: giao-hang
description: >-
  Dùng khi người dùng muốn THỰC HIỆN việc giao hàng cho một đơn bán đã xác
  nhận theo đúng quy trình đầy đủ — tra đơn, kiểm tra, rồi mới xác nhận giao.
  Nhận diện theo Ý ĐỊNH, KHÔNG cần đúng chữ "quy trình": câu có yêu cầu kiểm
  tra/đối chiếu trước khi giao, nêu điều kiện, hoặc mô tả nhiều bước cũng
  tính (vd "giao hàng cho đơn S00012 nhưng kiểm tra kỹ hàng trước khi giao").
  KHÔNG dùng khi: người dùng chỉ HỎI về quy trình giao hàng (đó là tra cứu
  tài liệu), hoặc ra một lệnh giao NGẮN GỌN một bước, không kèm điều kiện
  hay yêu cầu kiểm tra gì thêm (đó là lệnh ghi trực tiếp, đi qua planner
  tier-1).
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
---

Bạn là trợ lý kho, thực hiện quy trình giao hàng cho đơn bán.
Bạn có các công cụ: get_sale_order_detail (tra chi tiết đơn bán), ask_human
(hỏi người dùng và chờ trả lời), deliver_order (xác nhận giao hàng vào Odoo).

Quy trình, làm đúng thứ tự:
1. Xác định mã đơn bán cần giao hàng từ yêu cầu của người dùng. Nếu tin nhắn
   chưa nêu rõ mã đơn, dùng ask_human để hỏi.
2. Dùng get_sale_order_detail để tra thông tin đơn (khách hàng, mặt hàng) —
   dùng để có ngữ cảnh, không cần hỏi lại người dùng số liệu này.
3. Gọi deliver_order để giao hàng.
4. Thông báo kết quả cho người dùng bằng đúng nội dung câu "display" trong
   kết quả deliver_order trả về — không thêm suy đoán, không tự diễn giải
   khác đi, không chép JSON thô ra ngoài.

Quy tắc bắt buộc, không được vi phạm:
- Không được bịa mã đơn bán hoặc số liệu không có trong hội thoại hoặc kết
  quả tra cứu.
- Không được tự ý gọi deliver_order khi chưa xác định rõ mã đơn.
- Khi bạn gọi deliver_order, hệ thống sẽ TỰ ĐỘNG hỏi người dùng xác nhận
  trước khi ghi — bạn KHÔNG cần tự hỏi xác nhận trước bằng ask_human. Nếu
  công cụ trả về "Người dùng TỪ CHỐI xác nhận", không thử gọi lại ngay — hỏi
  người dùng muốn làm gì tiếp.
- KHÔNG tự động đề xuất hoặc thực hiện bước tiếp theo (tạo hóa đơn) sau khi
  giao hàng xong — dừng lại ở đó, chờ yêu cầu mới từ người dùng.
```

- [ ] **Bước 2: Tạo `backend/skills/nhap-kho/SKILL.md`**

Prose chép nguyên văn `SOP_PROMPT` của
`D:\Project\backend\src\agents\skill_agentic_warehouse_receiving.py:32-69`, với
`{NO_PO_BRIDGE_MSG}` đã nội suy thành văn bản thật (dòng 26-30 của file đó).

```markdown
---
name: nhap-kho
description: >-
  Dùng khi người dùng muốn THỰC HIỆN việc nhập kho cho một đơn mua theo đúng
  quy trình đầy đủ — kiểm đếm, đối chiếu số lượng, kiểm tra QC, rồi mới xác
  nhận nhận hàng. Nhận diện theo Ý ĐỊNH, KHÔNG cần đúng chữ "quy trình": câu
  nhắc tới kiểm đếm/đối chiếu/QC trước khi nhận, hoặc mô tả nhiều bước cũng
  tính (vd "xác nhận đã kiểm đếm hàng cho đơn mua P00021 rồi mới nhập kho").
  KHÔNG dùng khi: người dùng chỉ HỎI về quy trình nhập kho hoặc SOP nhập kho
  (đó là tra cứu tài liệu), hoặc ra một lệnh nhận hàng NGẮN GỌN một bước,
  không kèm điều kiện hay yêu cầu kiểm tra gì thêm (đó là lệnh ghi trực
  tiếp, đi qua planner tier-1), hoặc người dùng muốn điều chỉnh tồn kho trực
  tiếp không qua đơn mua.
tools:
  read: [get_purchase_order_detail]
  write:
    - name: receive_order
      confirm: "Xác nhận NHẬN HÀNG cho đơn mua {order_ref}?"
    - name: flag_order_for_review
      confirm: 'Xác nhận GHI CHÚ lên đơn mua {order_ref}: "{note}"?'
      fixed_args:
        model: purchase.order
---

Bạn là trợ lý kho, thực hiện quy trình nhập kho. Bạn có các
công cụ: get_purchase_order_detail (tra chi tiết đơn mua), ask_human (hỏi
người dùng và chờ trả lời), receive_order (xác nhận nhận hàng vào Odoo),
flag_order_for_review (ghi chú nội bộ lên đơn khi có bất thường — dùng thay
vì receive_order khi số lượng không khớp).

Quy trình, làm đúng thứ tự:
1. Xác định mã đơn mua cần nhập kho từ yêu cầu của người dùng. Nếu tin nhắn
   chưa nêu rõ mã đơn, dùng ask_human để hỏi.
2. Nếu người dùng cho biết KHÔNG CÓ đơn mua (chưa tạo, không định tạo, muốn
   nhập thẳng không qua PO): DỪNG NGAY quy trình này, không hỏi thêm gì về
   số lượng hay QC, không nhắc tên bất kỳ công cụ nào. Trả lời đúng nguyên
   văn (không diễn giải khác, không thêm bớt): "Quy trình nhập kho này yêu cầu có đơn mua (PO). Nếu bạn chỉ cần cập nhật số lượng tồn kho trực tiếp, hãy nói ví dụ: 'điều chỉnh tồn kho <tên sản phẩm> về <số lượng>' — tôi sẽ thực hiện ngay."
3. Dùng ask_human hỏi người dùng đã kiểm đếm hàng chưa và số lượng thực
   nhận (tổng tất cả mặt hàng, một con số) là bao nhiêu.
4. Dùng get_purchase_order_detail để tra số lượng đã đặt trên đơn mua đó.
5. So sánh số lượng thực nhận (bước 3) với tổng số lượng trên đơn (bước 4):
   - Nếu KHỚP: tiếp tục bước 6.
   - Nếu KHÔNG KHỚP (thiếu hoặc thừa): PHẢI dùng flag_order_for_review để
     ghi chú rõ tình trạng (thiếu bao nhiêu / thừa bao nhiêu). TUYỆT ĐỐI
     KHÔNG được gọi receive_order trong trường hợp này. Dừng quy trình,
     báo lại kết quả cho người dùng.
6. Nếu số lượng khớp, dùng ask_human hỏi bộ phận QC đã kiểm tra chất lượng
   xong chưa và kết quả (đạt hay không đạt).
   - Nếu KHÔNG ĐẠT: KHÔNG được gọi receive_order. Báo lại cho người dùng
     là hàng không đạt QC, chờ xử lý theo quy trình trả hàng.
7. Nếu QC đạt: gọi receive_order. Khi bạn gọi công cụ ghi (receive_order
   hoặc flag_order_for_review), hệ thống sẽ TỰ ĐỘNG hỏi người dùng xác nhận
   trước khi ghi — bạn KHÔNG cần tự hỏi xác nhận trước bằng ask_human. Nếu
   công cụ trả về "Người dùng TỪ CHỐI xác nhận", không thử gọi lại ngay —
   hỏi người dùng muốn làm gì tiếp.

Quy tắc bắt buộc, không được vi phạm:
- Không được tự suy đoán số lượng thực nhận hoặc kết quả QC thay cho việc
  hỏi qua ask_human.
- Không được gọi receive_order nếu số lượng không khớp HOẶC QC không đạt.
- Không được bịa mã đơn mua hoặc số liệu không có trong hội thoại hoặc kết
  quả tra cứu.
```

- [ ] **Bước 3: Viết test tương đương hành vi cho `giao-hang`**

Tạo `backend/tests/agents/test_skill_giao_hang.py`:

```python
"""Tương đương hành vi: wrapper deliver_order do skill_loader SINH TỰ ĐỘNG phải
quan sát được y hệt wrapper viết tay cũ ở
D:\\Project\\backend\\src\\agents\\skill_agentic_delivery.py:53-60 —
cùng câu xác nhận đã nội suy, cùng REFUSED_MSG, cùng payload ainvoke.

Module gốc KHÔNG tồn tại trong D:\\Youdoo (cố ý không port ở SP-1B), nên không
import để so sánh trực tiếp được; chuỗi kỳ vọng dưới đây chép từ mã nguồn đó."""
import json
from unittest.mock import patch

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import SKILLS_DIR, build_skill_tools
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "giao-hang" / "SKILL.md")


def _mcp():
    calls = []

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """Xác nhận giao hàng vào Odoo cho một đơn bán ĐÃ XÁC NHẬN."""
        calls.append({"order_ref": order_ref})
        return json.dumps({"ok": True, "ref": order_ref, "model": "sale.order",
                           "display": f"Đã giao hàng cho đơn {order_ref} (1 phiếu)."},
                          ensure_ascii=False)

    return [deliver_order], calls


def test_manifest_matches_source_module():
    assert SPEC.read_tools == ("get_sale_order_detail",)
    assert [w.name for w in SPEC.write_tools] == ["deliver_order"]
    assert SPEC.max_steps == 15
    # Prose LÀ system prompt — phải là nguyên văn SOP_PROMPT cũ, không cắt xén.
    assert SPEC.prose.startswith(
        "Bạn là trợ lý kho, thực hiện quy trình giao hàng cho đơn bán.")
    assert SPEC.prose.rstrip().endswith(
        "dừng lại ở đó, chờ yêu cầu mới từ người dùng.")


def test_description_has_both_clauses():
    assert "Dùng khi" in SPEC.description
    assert "KHÔNG dùng khi" in SPEC.description


@pytest.mark.asyncio
async def test_confirm_question_is_verbatim_and_write_happens_once():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []

    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert asked == ["Xác nhận GIAO HÀNG cho đơn bán S00012?"]
    assert calls == [{"order_ref": "S00012"}]
    assert "Đã giao hàng cho đơn S00012" in out


@pytest.mark.asyncio
async def test_refusal_returns_refused_msg_and_writes_nothing():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})
    assert out == REFUSED_MSG
    assert calls == []


def test_model_never_sees_raw_write_tool():
    """Bất biến: mọi tool ghi bind vào node SOP đều là wrapper đã gate — cùng
    TÊN với tool MCP nhưng KHÁC ĐỐI TƯỢNG."""
    mcp, _ = _mcp()
    raw = {t.name: t for t in mcp}
    for t in build_skill_tools(SPEC, mcp):
        if t.name in raw:
            assert t is not raw[t.name], f"{t.name} bind THẲNG tool MCP, không qua gate"
```

- [ ] **Bước 4: Viết test tương đương hành vi cho `nhap-kho`**

Tạo `backend/tests/agents/test_skill_nhap_kho.py` — cùng khuôn với bước 3,
chuỗi kỳ vọng chép từ
`D:\Project\backend\src\agents\skill_agentic_warehouse_receiving.py:79-100`:

```python
"""Tương đương hành vi cho nhap-kho — chuỗi kỳ vọng chép từ
D:\\Project\\backend\\src\\agents\\skill_agentic_warehouse_receiving.py:79-100.
Điểm khác giao-hang: flag_order_for_review có fixed_args model="purchase.order"
(wrapper cũ ghim hằng đó trong payload ainvoke, dòng 98-99)."""
import json
from unittest.mock import patch

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_loader import SKILLS_DIR, build_skill_tools
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "nhap-kho" / "SKILL.md")


def _mcp():
    calls = {"receive": [], "flag": []}

    @lc_tool("receive_order")
    async def receive_order(order_ref: str) -> str:
        """Xác nhận nhận hàng vào Odoo cho một đơn mua ĐÃ XÁC NHẬN."""
        calls["receive"].append({"order_ref": order_ref})
        return json.dumps({"ok": True, "display": f"Đã nhận hàng cho đơn {order_ref}."},
                          ensure_ascii=False)

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """Ghi chú nội bộ lên đơn."""
        calls["flag"].append({"model": model, "order_ref": order_ref, "note": note})
        return json.dumps({"ok": True, "display": "Đã ghi chú."}, ensure_ascii=False)

    return [receive_order, flag_order_for_review], calls


def test_manifest_matches_source_module():
    assert SPEC.read_tools == ("get_purchase_order_detail",)
    assert [w.name for w in SPEC.write_tools] == ["receive_order",
                                                  "flag_order_for_review"]
    assert SPEC.max_steps == 15
    assert SPEC.prose.startswith("Bạn là trợ lý kho, thực hiện quy trình nhập kho.")


def test_bridge_message_is_verbatim_in_prose():
    """NO_PO_BRIDGE_MSG (nhánh 'không có PO') sống trong prose và phải nguyên
    văn — model được dặn trả ĐÚNG chuỗi này để giảm biến thiên."""
    assert ("Quy trình nhập kho này yêu cầu có đơn mua (PO). Nếu bạn chỉ cần cập "
            "nhật số lượng tồn kho trực tiếp, hãy nói ví dụ: 'điều chỉnh tồn kho "
            "<tên sản phẩm> về <số lượng>' — tôi sẽ thực hiện ngay.") in SPEC.prose


@pytest.mark.asyncio
async def test_receive_order_confirm_verbatim():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await tools["receive_order"].ainvoke({"order_ref": "P00021"})
    assert asked == ["Xác nhận NHẬN HÀNG cho đơn mua P00021?"]
    assert calls["receive"] == [{"order_ref": "P00021"}]


@pytest.mark.asyncio
async def test_flag_confirm_verbatim_and_model_pinned_to_purchase_order():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await tools["flag_order_for_review"].ainvoke(
            {"order_ref": "P00021", "note": "thiếu 2 cái"})
    assert asked == ['Xác nhận GHI CHÚ lên đơn mua P00021: "thiếu 2 cái"?']
    assert calls["flag"] == [{"model": "purchase.order", "order_ref": "P00021",
                              "note": "thiếu 2 cái"}]


@pytest.mark.asyncio
async def test_both_write_tools_refuse_without_touching_mcp():
    mcp, calls = _mcp()
    tools = {t.name: t for t in build_skill_tools(SPEC, mcp)}
    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        assert await tools["receive_order"].ainvoke({"order_ref": "P00021"}) == REFUSED_MSG
        assert await tools["flag_order_for_review"].ainvoke(
            {"order_ref": "P00021", "note": "x"}) == REFUSED_MSG
    assert calls == {"receive": [], "flag": []}
```

- [ ] **Bước 5: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_giao_hang.py tests/agents/test_skill_nhap_kho.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 6: Port các test luồng ReAct từ repo nguồn**

Repo nguồn có 2 file test lớn phủ luồng ReAct đầy đủ (interrupt/resume, đếm
bước, ca thoái hoá):
`D:\Project\backend\tests\agents\test_skill_agentic_delivery.py` (230 dòng) và
`test_skill_agentic_warehouse_receiving.py` (381 dòng).

Copy chúng vào `backend/tests/agents/` (giữ tên mới:
`test_skill_giao_hang_flow.py`, `test_skill_nhap_kho_flow.py`), rồi sửa **chỉ
phần nối dây**:
- Xoá 2 dòng `import os, sys` + `sys.path.insert(...)`.
- `import backend.src.agents.skill_agentic_delivery as sad` →
  ```python
  from src.agents.skill_loader import SKILLS_DIR, build_skill_node
  from src.agents.skill_manifest import parse_skill_md
  ```
- Mọi `sad.make_node(llm, mcp_tools)` →
  `build_skill_node(parse_skill_md(SKILLS_DIR / "giao-hang" / "SKILL.md"), llm, mcp_tools)`.
- `backend.src.erp_query.sales` → `src.erp_query.sales`.
- Mọi `monkeypatch.setattr(sad, "_confirm_write", ...)` →
  `monkeypatch.setattr("src.agents.skill_loader._confirm_write", ...)`.

Run: `cd backend && python -m pytest tests/agents/test_skill_giao_hang_flow.py tests/agents/test_skill_nhap_kho_flow.py -v`
Expected: PASS.

Đỏ **vì hạ tầng** → sửa nối dây. Đỏ **vì hành vi** → DỪNG, ghi vào task report,
KHÔNG sửa test cho xanh.

- [ ] **Bước 7: Commit**

```bash
git add backend/skills/giao-hang backend/skills/nhap-kho backend/tests/agents/test_skill_giao_hang.py backend/tests/agents/test_skill_nhap_kho.py backend/tests/agents/test_skill_giao_hang_flow.py backend/tests/agents/test_skill_nhap_kho_flow.py
git commit -m "feat(skills): di trú giao-hang + nhap-kho sang SKILL.md"
```

---

### Task 7: Di trú `bao-gia-chiet-khau` (`SKILL.md` + `logic.py`)

Skill này **không khai báo thuần được**: ~109 dòng `compute_discount_pct()`,
`_render_discount_draft()`, vòng resolve khách/sản phẩm rồi tra giá — đó **là**
bất biến an toàn về tiền. Đẩy vào markdown nghĩa là giao việc tính tiền cho
model. Đây là lý do khuôn "thư mục + `logic.py`" là bắt buộc, không phải tuỳ chọn.

**Files:**
- Create: `backend/skills/bao-gia-chiet-khau/SKILL.md`
- Create: `backend/skills/bao-gia-chiet-khau/logic.py`
- Create: `backend/tests/agents/test_skill_bao_gia_chiet_khau.py`

**Interfaces:**
- Consumes: `src.agents.agentic_gate`, `src.agents.create_order.resolve_entity_for_order`,
  `src.agents.skill_gate._fold`, `src.erp_query.sales`, `src.erp_query.inventory`
  (đã xác minh tất cả tồn tại trong `D:\Youdoo`)
- Produces: `build_tools(mcp_tools) -> list[BaseTool]` trong `logic.py`

- [ ] **Bước 1: Tạo `backend/skills/bao-gia-chiet-khau/SKILL.md`**

Prose chép nguyên văn `SOP_PROMPT` của
`D:\Project\backend\src\agents\skill_agentic_discount_quote.py:63-91`.

```markdown
---
name: bao-gia-chiet-khau
description: >-
  Dùng khi người dùng muốn tạo báo giá CÓ CHIẾT KHẤU theo cấp khách hàng
  (thường / thân thiết / đối tác chiến lược).
  KHÔNG dùng khi: người dùng chỉ hỏi về chính sách chiết khấu (đó là tra cứu
  tài liệu), hoặc muốn tạo báo giá thường không chiết khấu (đó là lệnh ghi
  trực tiếp, đi qua planner tier-1).
entry: logic.py
declares_tools: [create_discount_quote]
---

Bạn là trợ lý bán hàng, thực hiện quy trình báo giá có chiết khấu
theo cấp khách hàng. Bạn có các công cụ: ask_human (hỏi người dùng và chờ trả
lời), create_discount_quote (tạo báo giá có chiết khấu vào Odoo — hệ thống TỰ
tính đơn giá và % chiết khấu trong code).

Quy trình, làm đúng thứ tự:
1. Xác định từ yêu cầu của người dùng: tên khách hàng và danh sách sản phẩm +
   số lượng. Nếu thiếu bất kỳ thông tin nào, dùng ask_human để hỏi.
2. Dùng ask_human hỏi khách hàng này thuộc cấp nào, nêu rõ 3 lựa chọn:
   Thường / Thân thiết / Đối tác chiến lược.
3. Gọi create_discount_quote với customer, lines, tier đã gom được.
4. Nếu công cụ trả về danh sách nhiều khách hàng/sản phẩm trùng tên: dùng
   ask_human cho người dùng chọn đúng, rồi gọi lại create_discount_quote với
   tên đã chọn.
5. Thông báo kết quả cho người dùng bằng đúng nội dung câu "display" trong kết
   quả create_discount_quote trả về — không thêm suy đoán, không tự diễn giải
   khác đi, không chép JSON thô ra ngoài.

Quy tắc bắt buộc, không được vi phạm:
- TUYỆT ĐỐI không tự tính, không hứa hẹn, không nêu % chiết khấu hay giá tiền —
  mọi con số tiền do hệ thống tính trong code và sẽ hiện trong câu xác nhận.
- Không được bịa tên khách hàng, sản phẩm, số lượng hay cấp khách không có
  trong hội thoại.
- Khi bạn gọi create_discount_quote, hệ thống sẽ TỰ ĐỘNG hỏi người dùng xác
  nhận (kèm đầy đủ số tiền) trước khi ghi — bạn KHÔNG cần tự hỏi xác nhận
  trước bằng ask_human. Nếu công cụ trả về "Người dùng TỪ CHỐI xác nhận",
  không thử gọi lại ngay — hỏi người dùng muốn làm gì tiếp.
- KHÔNG tự động đề xuất hoặc thực hiện bước tiếp theo (xác nhận báo giá) sau
  khi tạo xong — dừng lại ở đó, chờ yêu cầu mới từ người dùng.
```

- [ ] **Bước 2: Tạo `backend/skills/bao-gia-chiet-khau/logic.py`**

Port nguyên phần mã của
`D:\Project\backend\src\agents\skill_agentic_discount_quote.py:24-60, 94-171`.
Ba thay đổi nối dây bắt buộc, không đổi hành vi:
1. Import tương đối (`.agentic_gate`) → tuyệt đối (`src.agents.agentic_gate`)
   — file này nằm ngoài `backend/src/`, được loader nạp theo đường dẫn.
2. `_build_tools` → `build_tools` (tên hợp đồng loader gọi).
3. Bỏ `TRIGGERS`, `SOP_PROMPT`, `make_node` — thuộc về `SKILL.md` và loader.

```python
# backend/skills/bao-gia-chiet-khau/logic.py
"""Mã riêng của SOP bao-gia-chiet-khau — 🔒 KHÔNG dành cho người sửa SOP.

BẤT BIẾN TIỀN BẠC (quyết định KHÔNG được bàn lại): % chiết khấu và đơn giá
LUÔN tính trong code (compute_discount_pct + get_product_price) — model chỉ
gom tham số (khách, dòng hàng, cấp khách), KHÔNG BAO GIỜ tính hay truyền số
tiền. Đây chính là lý do skill này không khai báo thuần bằng SKILL.md được:
đẩy ~109 dòng dưới đây vào markdown nghĩa là giao việc tính tiền cho model.

Port nguyên văn từ D:\\Project\\backend\\src\\agents\\skill_agentic_discount_quote.py
(chỉ đổi import tương đối → tuyệt đối, và _build_tools → build_tools cho khớp
hợp đồng loader). Prose quy trình sống ở SKILL.md cạnh file này."""
from langchain_core.tools import tool

from src.agents.agentic_gate import REFUSED_MSG, _confirm_write, ask_human
from src.agents.create_order import resolve_entity_for_order
from src.agents.skill_gate import _fold
from src.erp_query import sales, inventory

TIER_PCT = {"thuong": 0.0, "than_thiet": 0.05, "doi_tac": 0.10}

# Nhận cả id lẫn cách gõ tự nhiên (đã _fold): model 8-9B hay trả nhãn tiếng
# Việt thay vì id — map tất định, sai thì trả lỗi liệt kê, không đoán.
_TIER_ALIASES = {
    "thuong": "thuong", "khach thuong": "thuong", "binh thuong": "thuong",
    "than thiet": "than_thiet", "than_thiet": "than_thiet",
    "khach than thiet": "than_thiet",
    "doi tac": "doi_tac", "doi_tac": "doi_tac",
    "doi tac chien luoc": "doi_tac", "chien luoc": "doi_tac",
}

TIER_INVALID_MSG = ("Cấp khách không hợp lệ. Ba cấp hợp lệ: Thường / Thân thiết / "
                    "Đối tác chiến lược. Hãy hỏi lại người dùng bằng ask_human.")


def compute_discount_pct(tier_id: str, order_total: float) -> float:
    base = TIER_PCT[tier_id]
    bonus = 0.02 if order_total >= 50_000_000 else 0.0
    # round(): base+bonus in raw IEEE-754 float can land off-integer-percent
    # (e.g. 0.10 + 0.02 == 0.12000000000000001) — all tier/bonus values are
    # whole percentage points, so round to 2dp before the cap comparison.
    return min(round(base + bonus, 2), 0.15)


def _render_discount_draft(partner, lines, pct) -> str:
    body = "\n".join(f"  - {l['name']} × {l['qty']:g} = {l['subtotal']:,.0f}"
                     for l in lines)
    total_before = sum(l["subtotal"] for l in lines)
    total_after = total_before * (1 - pct)
    return (f"Báo giá cho {partner['name']}:\n{body}\n"
            f"Tổng trước chiết khấu: {total_before:,.0f}\n"
            f"Chiết khấu: {pct * 100:g}%\n"
            f"Tổng sau chiết khấu: {total_after:,.0f}\n"
            f"Xác nhận? (có / không)")


def build_tools(mcp_tools):
    """Hợp đồng với skill_loader: trả list[BaseTool]. Loader đối chiếu tên tool
    trả về với declares_tools trong SKILL.md — trả tool KHÔNG khai thì từ chối
    nạp (app không lên)."""
    by_name = {t.name: t for t in mcp_tools}
    tools = [ask_human]

    create = by_name.get("create_quotation")
    if create is not None:
        @tool("create_discount_quote")
        async def create_discount_quote_gated(customer: str, lines: list[dict],
                                              tier: str) -> str:
            """Tạo báo giá có chiết khấu theo cấp khách vào Odoo. Hệ thống tự
            tính đơn giá + % chiết khấu trong code và tự hỏi người dùng xác
            nhận trước khi ghi.

            Args:
                customer: Tên khách hàng.
                lines: Danh sách dòng hàng, mỗi dòng {"product": "<tên>", "qty": <số>}.
                tier: Cấp khách — "thuong" | "than_thiet" | "doi_tac".
            """
            tier_id = _TIER_ALIASES.get(_fold(tier).strip())
            if tier_id is None:
                return TIER_INVALID_MSG
            if not str(customer or "").strip():
                return "Chưa có tên khách hàng. Hãy hỏi người dùng bằng ask_human."
            if not lines:
                return "Chưa có dòng hàng nào. Hãy hỏi người dùng sản phẩm + số lượng."

            kind, val = resolve_entity_for_order(sales.find_customer(customer), customer)
            if kind == "error":
                return val
            if kind == "none":
                return f"Không tìm thấy khách hàng '{customer}'."
            if kind == "ambiguous":
                names = "; ".join(str(o.get("name", "?")) for o in val)
                return (f"Có nhiều khách hàng trùng '{customer}': {names}. "
                        "Hãy hỏi người dùng chọn đúng tên rồi gọi lại.")
            partner = val

            quote_lines = []
            for line in lines:
                ref = str(line.get("product") or "")
                try:
                    qty = float(line.get("qty") or 0)
                except (TypeError, ValueError):
                    return (f"Số lượng không hợp lệ cho '{ref}'. Hãy hỏi lại "
                            "người dùng số lượng (một con số).")
                pkind, pval = resolve_entity_for_order(inventory.find_product(ref), ref)
                if pkind == "error":
                    return pval
                if pkind == "none":
                    return f"Không tìm thấy sản phẩm '{ref}'."
                if pkind == "ambiguous":
                    names = "; ".join(str(o.get("name", "?")) for o in pval)
                    return (f"Có nhiều sản phẩm trùng '{ref}': {names}. "
                            "Hãy hỏi người dùng chọn đúng tên rồi gọi lại.")
                product = pval
                penv = sales.get_product_price(product["id"], partner["id"], qty)
                price = (penv.get("data") or {}).get("price", 0.0) \
                    if penv.get("status") == "success" else 0.0
                quote_lines.append({"product_id": product["id"], "name": product["name"],
                                    "qty": qty, "unit_price": price,
                                    "subtotal": price * qty})

            order_total = sum(l["subtotal"] for l in quote_lines)
            pct = compute_discount_pct(tier_id, order_total)

            if not _confirm_write(_render_discount_draft(partner, quote_lines, pct)):
                return REFUSED_MSG
            try:
                tool_lines = [{"product_id": l["product_id"], "qty": l["qty"],
                               "price_unit": l["unit_price"] * (1 - pct)}
                              for l in quote_lines]
                return await create.ainvoke({"partner_id": partner["id"],
                                             "lines": tool_lines})
            except Exception as e:  # noqa: BLE001 — tool luôn trả text, không phá graph
                return f"Lỗi khi tạo báo giá: {e}"
        tools.append(create_discount_quote_gated)

    return tools
```

- [ ] **Bước 3: Viết test cho manifest + bất biến tiền bạc**

Tạo `backend/tests/agents/test_skill_bao_gia_chiet_khau.py`:

```python
"""bao-gia-chiet-khau: SKILL.md + logic.py. Trọng tâm là BẤT BIẾN TIỀN BẠC —
% chiết khấu và đơn giá luôn tính trong code, model không bao giờ truyền số
tiền. Hàm thuần port nguyên từ
D:\\Project\\backend\\src\\agents\\skill_agentic_discount_quote.py:42-60."""
import pytest

from src.agents.skill_loader import (SKILLS_DIR, build_skill_tools,
                                     load_skill_specs)
from src.agents.skill_manifest import parse_skill_md

SPEC = parse_skill_md(SKILLS_DIR / "bao-gia-chiet-khau" / "SKILL.md")


def _logic():
    """Nạp logic.py qua ĐÚNG đường loader dùng (không import thẳng) — nếu hợp
    đồng nạp hỏng thì test này hỏng theo, đúng ý."""
    from src.agents.skill_loader import _load_entry_module
    return _load_entry_module(SPEC)


def test_manifest_uses_entry_not_declarative_write():
    assert SPEC.entry == "logic.py"
    assert SPEC.declares_tools == ("create_discount_quote",)
    assert SPEC.write_tools == ()          # luật 9: write XOR entry


def test_description_has_both_clauses():
    assert "Dùng khi" in SPEC.description
    assert "KHÔNG dùng khi" in SPEC.description


@pytest.mark.parametrize("tier,total,expected", [
    ("thuong", 1_000_000, 0.0),
    ("than_thiet", 1_000_000, 0.05),
    ("doi_tac", 1_000_000, 0.10),
    ("thuong", 50_000_000, 0.02),          # bonus ngưỡng 50tr
    ("than_thiet", 50_000_000, 0.07),
    ("doi_tac", 50_000_000, 0.12),         # 0.10+0.02 phải là 0.12, không 0.12000000000000001
])
def test_compute_discount_pct(tier, total, expected):
    assert _logic().compute_discount_pct(tier, total) == expected


def test_discount_pct_never_exceeds_cap():
    logic = _logic()
    for tier in ("thuong", "than_thiet", "doi_tac"):
        assert logic.compute_discount_pct(tier, 10**12) <= 0.15


def test_tier_aliases_map_natural_vietnamese():
    logic = _logic()
    from src.agents.skill_gate import _fold
    for typed, expected in [("Đối tác chiến lược", "doi_tac"),
                            ("thân thiết", "than_thiet"),
                            ("Khách thường", "thuong")]:
        assert logic._TIER_ALIASES.get(_fold(typed).strip()) == expected


def test_loader_accepts_entry_and_binds_only_declared_tools():
    from langchain_core.tools import tool as lc_tool

    @lc_tool("create_quotation")
    async def create_quotation(partner_id: int, lines: list) -> str:
        """fake MCP create_quotation."""
        return "{}"

    names = {t.name for t in build_skill_tools(SPEC, [create_quotation])}
    assert names == {"ask_human", "create_discount_quote"}
    # create_quotation THÔ không bao giờ tới tay model
    assert "create_quotation" not in names


def test_all_three_skills_load_from_real_directory():
    specs = load_skill_specs()
    assert [s.name for s in specs] == ["bao-gia-chiet-khau", "giao-hang", "nhap-kho"]
```

- [ ] **Bước 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_skill_bao_gia_chiet_khau.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 5: Port test luồng ReAct từ repo nguồn**

Copy `D:\Project\backend\tests\agents\test_skill_agentic_discount_quote.py`
(344 dòng) → `backend/tests/agents/test_skill_bao_gia_chiet_khau_flow.py`, sửa
**chỉ phần nối dây**:
- Xoá 2 dòng `import os, sys` + `sys.path.insert(...)` ở đầu file.
- Đổi mọi `backend.src.` → `src.` (vd `backend.src.erp_query.sales` →
  `src.erp_query.sales`).
- `import backend.src.agents.skill_agentic_discount_quote as sq` → thay bằng:
  ```python
  from src.agents.skill_loader import (SKILLS_DIR, _load_entry_module,
                                       build_skill_node)
  from src.agents.skill_manifest import parse_skill_md

  SPEC = parse_skill_md(SKILLS_DIR / "bao-gia-chiet-khau" / "SKILL.md")
  logic = _load_entry_module(SPEC)
  ```
- `sq.make_node(llm, mcp)` → `build_skill_node(SPEC, llm, mcp)`.
- `sq.compute_discount_pct` / `sq.TIER_PCT` / `sq._render_discount_draft` →
  `logic.<tên>` (cùng tên, module khác).
- `monkeypatch.setattr(sq, "_confirm_write", ...)` →
  `monkeypatch.setattr(logic, "_confirm_write", ...)` — patch trên chính module
  `logic.py` vừa nạp, **KHÔNG** trên `skill_loader`: skill này tự gọi
  `_confirm_write` bên trong `logic.py`, không đi qua wrapper của loader.

Run: `cd backend && python -m pytest tests/agents/test_skill_bao_gia_chiet_khau_flow.py -v`
Expected: PASS. Đỏ vì hành vi → DỪNG, báo cáo.

- [ ] **Bước 6: Commit**

```bash
git add backend/skills/bao-gia-chiet-khau backend/tests/agents/test_skill_bao_gia_chiet_khau.py backend/tests/agents/test_skill_bao_gia_chiet_khau_flow.py
git commit -m "feat(skills): di trú bao-gia-chiet-khau — SKILL.md + logic.py giữ bất biến tiền bạc"
```

---

### Task 8: Router trả hai trường (`intent` + `sop`)

**Files:**
- Modify: `backend/src/agents/state.py`
- Modify: `backend/src/agents/prompts.py:20-32`
- Modify: `backend/src/agents/nodes.py:30-48`
- Test: `backend/tests/agents/test_intent_router.py` (mở rộng)

**Interfaces:**
- Consumes: `skill_loader.render_worker_block` (Task 3) — nhưng **không import
  trong module này**; graph.py truyền vào (dependency injection)
- Produces:
  - `prompts.render_intent_router_prompt(worker_block: str) -> str`
  - `nodes._parse_router_output(text: str, valid_sops) -> tuple[str, str | None]`
  - `nodes.make_intent_router_node(llm, worker_block: str = "", valid_sops=frozenset())`
    → trả `{"intent": str, "sop": str | None}`

- [ ] **Bước 1: Thêm `sop` vào `ERPAgentState`**

`backend/src/agents/state.py`, thêm ngay sau dòng `intent`:

```python
    sop: str | None               # tên skill SOP router ĐỀ CỬ cho lượt này
                                  # (hoặc None). TRANSIENT như pending_action —
                                  # intent_router ghi key này trên MỌI return
                                  # nên không sống sót sang lượt sau; quyết
                                  # định cuối vẫn do graph._route_by_intent
                                  # (phủ quyết tất định), không do trường này.
```

- [ ] **Bước 2: Viết test đỏ cho parser**

Thêm vào `backend/tests/agents/test_intent_router.py`:

```python
import pytest

from src.agents.nodes import _parse_router_output, make_intent_router_node
from src.agents.prompts import INTENT_ROUTER_PROMPT, render_intent_router_prompt
from tests.conftest import make_mock_llm

SOPS = frozenset({"giao-hang", "nhap-kho", "bao-gia-chiet-khau"})


def test_parse_two_field_output():
    assert _parse_router_output("intent: erp_write\nsop: giao-hang", SOPS) == \
        ("erp_write", "giao-hang")


def test_parse_empty_sop_field():
    assert _parse_router_output("intent: rag\nsop:", SOPS) == ("rag", None)
    assert _parse_router_output("intent: rag\nsop: ", SOPS) == ("rag", None)


def test_parse_drops_hallucinated_sop_name():
    # Fail an toàn: tên worker model bịa ra KHÔNG BAO GIỜ thành node đích —
    # trả nó ra sẽ làm LangGraph ném lỗi định tuyến giữa lượt chat thật.
    assert _parse_router_output("intent: erp_write\nsop: xoa-sach-du-lieu", SOPS) == \
        ("erp_write", None)


def test_parse_invalid_intent_falls_back_to_unknown():
    assert _parse_router_output("intent: banana\nsop:", SOPS) == ("unknown", None)


def test_parse_bare_intent_word_back_compat():
    # Model nhỏ bỏ qua format 2 dòng và trả đúng 1 từ như hợp đồng CŨ → vẫn
    # hiểu được, rơi về đúng hành vi hôm nay thay vì "unknown".
    assert _parse_router_output("erp_read", SOPS) == ("erp_read", None)
    assert _parse_router_output("  RAG  ", SOPS) == ("rag", None)


def test_parse_garbage_is_unknown_not_exception():
    assert _parse_router_output("", SOPS) == ("unknown", None)
    assert _parse_router_output("tôi không hiểu câu hỏi", SOPS) == ("unknown", None)


def test_parse_is_case_insensitive_and_tolerates_extra_lines():
    assert _parse_router_output("Intent: ERP_WRITE\nSOP: giao-hang\nghi chú: x",
                                SOPS) == ("erp_write", "giao-hang")


@pytest.mark.asyncio
async def test_node_returns_both_fields():
    node = make_intent_router_node(
        make_mock_llm("intent: erp_write\nsop: giao-hang"),
        worker_block="worker: giao-hang\nmô tả: x", valid_sops=SOPS)
    from langchain_core.messages import HumanMessage
    out = await node({"messages": [HumanMessage(content="làm quy trình giao hàng cho S1")]})
    assert out == {"intent": "erp_write", "sop": "giao-hang"}


@pytest.mark.asyncio
async def test_node_always_writes_sop_key_so_it_never_leaks_across_turns():
    node = make_intent_router_node(make_mock_llm("intent: rag\nsop:"), valid_sops=SOPS)
    from langchain_core.messages import HumanMessage
    out = await node({"messages": [HumanMessage(content="chính sách đổi trả?")]})
    assert out["sop"] is None


@pytest.mark.asyncio
async def test_node_with_no_human_message_returns_unknown_and_no_sop():
    node = make_intent_router_node(make_mock_llm("intent: rag\nsop: giao-hang"),
                                   valid_sops=SOPS)
    assert await node({"messages": []}) == {"intent": "unknown", "sop": None}


def test_render_prompt_appends_worker_block():
    block = "worker: giao-hang\nmô tả: Dùng khi X."
    rendered = render_intent_router_prompt(block)
    assert rendered.startswith(INTENT_ROUTER_PROMPT)
    assert rendered.endswith(block)


def test_render_prompt_without_skills_is_base_prompt():
    assert render_intent_router_prompt("") == INTENT_ROUTER_PROMPT
```

- [ ] **Bước 3: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_intent_router.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_router_output'`

- [ ] **Bước 4: Đổi `INTENT_ROUTER_PROMPT` + thêm `render_intent_router_prompt`**

Thay `backend/src/agents/prompts.py:20-32` bằng:

```python
# Hợp đồng đầu ra ĐỔI ở SP-2a: từ "một từ intent" sang HAI DÒNG
# (intent + sop) — router đề cử SOP trong CÙNG MỘT lượt gọi, không tốn thêm
# call (quan trọng khi OpenRouter chỉ ~50 req/ngày). Đề cử là XÁC SUẤT; quyết
# định cuối vẫn tất định ở graph._route_by_intent. Đổi hợp đồng này là đổi
# HÀNH VI nên nằm trong phạm vi đo của bộ eval `intent` cũ — bộ đó không được
# thụt (điều kiện lên sóng §5.3).
INTENT_ROUTER_PROMPT = """Classify the user's latest message.

Reply with EXACTLY two lines and nothing else (no punctuation, no explanation):
intent: <one intent word>
sop: <one SOP worker name, or leave empty>

intent — choose EXACTLY ONE of:
erp_read   — query / read data from ERP: orders, inventory, customers, suppliers, revenue, top products, bill of materials (BoM) / production recipes, manufacturing orders
erp_write  — create / update / delete data in ERP: create order, update stock, confirm purchase, etc.
rag        — questions about documents, manuals, policies, procedures, internal knowledge base
mixed      — needs BOTH an internal document/policy AND specific live ERP records together (e.g. "theo chính sách hoàn hàng, đơn của khách X có được hoàn không?")
unknown    — does not clearly fit any of the above

Rules for intent:
- When unsure between erp_read and erp_write, choose erp_read.
- When the question needs a policy/document AND specific ERP records together, choose mixed.
- Greetings / small talk → unknown.

Rules for sop — fill it ONLY when the user is asking to EXECUTE a listed
business procedure end-to-end. Leave it empty (write "sop:" with nothing after
it) when ANY of these holds:
- the user is only ASKING ABOUT a procedure — that is a documentation lookup;
- the user gives a plain one-step command without procedure wording;
- no worker in the list below matches.
Never invent a worker name that is not listed."""


def render_intent_router_prompt(worker_block: str) -> str:
    """Nối khối mô tả worker (skill_loader.render_worker_block) vào cuối prompt
    router. Khối rỗng (không có SOP nào) → prompt gốc, không đổi."""
    if not worker_block:
        return INTENT_ROUTER_PROMPT
    return f"{INTENT_ROUTER_PROMPT}\n\n{worker_block}"
```

- [ ] **Bước 5: Sửa `make_intent_router_node`**

Thay `backend/src/agents/nodes.py:30-48` bằng:

```python
def _parse_router_output(text: str, valid_sops) -> tuple[str, str | None]:
    """Parse hợp đồng 2 dòng của router. FAIL AN TOÀN ở mọi hướng:

    - intent không nhận ra → "unknown" (hành vi cũ);
    - sop không nằm trong valid_sops → None. Tên worker model bịa ra KHÔNG BAO
      GIỜ được trả ra: nó sẽ thành node đích không tồn tại và làm LangGraph ném
      lỗi định tuyến giữa một lượt chat thật;
    - không thấy dòng "intent:" nào → thử đọc cả chuỗi như MỘT TỪ intent (hợp
      đồng CŨ). Model nhỏ hay bỏ qua format; rơi về đúng hành vi hôm nay tốt
      hơn là rơi về "unknown"."""
    intent: str | None = None
    sop: str | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("intent:"):
            value = low[len("intent:"):].strip()
            if value in VALID_INTENTS:
                intent = value
        elif low.startswith("sop:"):
            value = stripped[len("sop:"):].strip()
            if value in valid_sops:
                sop = value
    if intent is None:
        bare = (text or "").strip().lower()
        intent = bare if bare in VALID_INTENTS else "unknown"
    return intent, sop


def make_intent_router_node(llm, worker_block: str = "", valid_sops=frozenset()):
    """worker_block + valid_sops được TIÊM VÀO (graph.py lấy từ skill_loader) —
    nodes.py cố ý không import skill_loader: node này phải test được với bất kỳ
    danh sách worker nào, kể cả rỗng."""
    prompt = render_intent_router_prompt(worker_block)
    valid_sops = frozenset(valid_sops)

    async def intent_router(state: ERPAgentState) -> dict:
        last_human = next(
            (m for m in reversed(state["messages"]) if m.type == "human"),
            None,
        )
        if not last_human:
            return {"intent": "unknown", "sop": None}

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=last_human.content),
        ])
        intent, sop = _parse_router_output(response.content, valid_sops)
        # LUÔN ghi khoá "sop" (kể cả None): nó TRANSIENT, đề cử của lượt trước
        # không được sống sót sang lượt sau.
        return {"intent": intent, "sop": sop}

    return intent_router
```

Thêm `render_intent_router_prompt` vào khối import từ `.prompts` ở
`backend/src/agents/nodes.py:14-15`.

- [ ] **Bước 6: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_intent_router.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 7: Chạy toàn bộ test agents để bắt hồi quy**

Run: `cd backend && python -m pytest tests/agents -q`
Expected: PASS, trừ `test_graph_build.py::test_build_graph_accepts_role_mapping`
có thể đỏ (spy `make_intent_router_node` chỉ nhận 1 tham số). Nếu đỏ, sửa spy
trong Task 9 bước 4 — ghi lại, chưa sửa ở đây.

- [ ] **Bước 8: Commit**

```bash
git add backend/src/agents/state.py backend/src/agents/prompts.py backend/src/agents/nodes.py backend/tests/agents/test_intent_router.py
git commit -m "feat(agents): router trả 2 trường intent+sop trong một lượt gọi"
```

---

### Task 9: Wiring graph — định tuyến hybrid + bất biến bảo mật

**Files:**
- Modify: `backend/src/agents/graph.py`
- Test: `backend/tests/agents/test_graph_build.py` (mở rộng)

**Interfaces:**
- Consumes: `skill_loader.load_skill_specs` / `render_worker_block` /
  `build_skill_node`, `agentic_context_sync.make_agentic_context_sync_node`,
  `nodes.make_intent_router_node(llm, worker_block, valid_sops)`
- Produces: `build_graph()` có node SOP; `_route_by_intent(state) -> str`

- [ ] **Bước 1: Viết test đỏ cho `_route_by_intent`**

Thêm vào `backend/tests/agents/test_graph_build.py`:

```python
# ── SP-2a: định tuyến hybrid ─────────────────────────────────────────────────
# Tầng 1 (description → đề cử `sop`) là XÁC SUẤT. Tầng 2 (_looks_like_question
# phủ quyết) là TẤT ĐỊNH và cố ý — live-verify 2026-07-16 cho thấy router LLM
# thua đúng bài này 3/3 lần. Bảng dưới đo tầng 2.

from langchain_core.messages import HumanMessage


def _state(text, intent, sop):
    return {"messages": [HumanMessage(content=text)], "intent": intent, "sop": sop}


def test_route_sop_wins_for_plain_execute_command():
    from src.agents.graph import _route_by_intent
    # Router phân loại SAI (mixed) nhưng câu không mang dấu hiệu câu hỏi →
    # SOP vẫn nhận trọn lượt. Đây CHÍNH LÀ ca thua 3/3 lần ngày 2026-07-16.
    assert _route_by_intent(
        _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "nhap-kho"
    assert _route_by_intent(
        _state("nhập kho theo quy trình cho đơn mua P00021", "erp_read", "nhap-kho")) == "nhap-kho"


def test_route_sop_wins_when_intent_is_erp_write_even_if_question_shaped():
    from src.agents.graph import _route_by_intent
    # Nhánh OR: router tự tin nói erp_write thì lối tắt vẫn mở.
    assert _route_by_intent(
        _state("giao hàng cho đơn S1 được không", "erp_write", "giao-hang")) == "giao-hang"


def test_route_question_vetoes_sop_proposal():
    from src.agents.graph import _route_by_intent
    # Ca hijack GỐC: "quy trình nhập kho là gì?" phải đi RAG, không đi SOP.
    assert _route_by_intent(
        _state("quy trình nhập kho là gì?", "rag", "nhap-kho")) == "rag"
    assert _route_by_intent(
        _state("quy trình giao hàng như thế nào", "rag", "giao-hang")) == "rag"


def test_route_without_sop_proposal_returns_intent():
    from src.agents.graph import _route_by_intent
    assert _route_by_intent(_state("giao hàng cho đơn S00040", "erp_write", None)) == "erp_write"
    assert _route_by_intent(_state("chào bạn", "unknown", None)) == "unknown"
    assert _route_by_intent(_state("x", None, None)) == "unknown"


def test_route_kill_switch_drops_every_sop_proposal(monkeypatch):
    from src.agents.graph import _route_by_intent
    monkeypatch.setenv("ERP_SKILLS_ENABLED", "0")
    assert _route_by_intent(
        _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "mixed"


def test_route_kill_switch_only_off_value_is_zero(monkeypatch):
    from src.agents.graph import _route_by_intent
    for value in ("1", "true", "yes", ""):
        monkeypatch.setenv("ERP_SKILLS_ENABLED", value)
        assert _route_by_intent(
            _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "nhap-kho"


def test_build_graph_registers_every_skill_node_and_context_sync():
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    nodes = set(graph.get_graph().nodes)
    assert "agentic_context_sync" in nodes
    for spec in load_skill_specs():
        assert spec.name in nodes


def test_every_skill_node_edges_into_context_sync():
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    for spec in load_skill_specs():
        assert (spec.name, "agentic_context_sync") in edges
        assert (spec.name, "__end__") not in edges
    assert ("agentic_context_sync", "__end__") in edges


def test_skill_nodes_reachable_only_from_intent_router():
    """Bất biến bảo mật toàn đồ thị (nối dài test_all_write_mutating_nodes_...):
    một node SOP mang tool ghi đã gate, nhưng chỉ được vào từ intent_router —
    nơi DUY NHẤT áp phủ quyết tất định. Một cạnh tương lai chọc thẳng vào node
    SOP từ chỗ khác sẽ đi vòng qua lớp phòng thủ đó và phải fail test này."""
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    skill_nodes = {s.name for s in load_skill_specs()}
    assert skill_nodes, "không có skill nào — test này vô nghĩa nếu rỗng"
    for source, target in edges:
        if target in skill_nodes:
            assert source == "intent_router", (
                f"cạnh {source} -> {target} vào node SOP không qua intent_router")


def test_every_write_tool_in_a_skill_node_is_gated():
    """Bất biến bảo mật: không tool ghi TRẦN nào lọt vào node SOP. So sánh theo
    ĐỐI TƯỢNG (is), không theo tên — wrapper cố ý mang cùng tên."""
    import json
    from langchain_core.tools import tool as lc_tool
    from src.agents.skill_loader import build_skill_tools, load_skill_specs

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("receive_order")
    async def receive_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("create_quotation")
    async def create_quotation(partner_id: int, lines: list) -> str:
        """fake"""
        return "{}"

    mcp = [deliver_order, receive_order, flag_order_for_review, create_quotation]
    raw = {t.name: t for t in mcp}
    for spec in load_skill_specs():
        for t in build_skill_tools(spec, mcp):
            assert t is not raw.get(t.name), (
                f"{spec.name}: tool ghi {t.name} bind THẲNG, không qua gate")
```

- [ ] **Bước 2: Chạy test, xác nhận đỏ**

Run: `cd backend && python -m pytest tests/agents/test_graph_build.py -v`
Expected: FAIL — `_route_by_intent` chưa nhìn `sop`; các node SOP chưa tồn tại.

- [ ] **Bước 3: Sửa `graph.py`**

Thêm vào khối import của `backend/src/agents/graph.py`:

```python
from . import skill_gate
from .skill_gate import _fold
from .skill_loader import build_skill_node, load_skill_specs, render_worker_block
from .agentic_context_sync import make_agentic_context_sync_node
```

Thay `_route_by_intent` (dòng 31-36) bằng:

```python
def _route_by_intent(state: ERPAgentState) -> str:
    """Quyết định cuối là TẤT ĐỊNH. Đề cử SOP (state["sop"]) chỉ là một trong
    hai điều kiện; điều kiện kia — câu KHÔNG mang dấu hiệu câu hỏi — là lớp
    phủ quyết không phụ thuộc phân loại LLM.

    Vì sao lớp phủ quyết này CỐ Ý tất định và KHÔNG được tháo ra: bản đầu (chỉ
    AND với intent=="erp_write") đóng đúng ca hijack gốc ("quy trình nhập kho
    là gì?" → skill thay vì RAG) nhưng live-verify 2026-07-16 lộ ra chiều lỗi
    ngược — router phân loại "mixed"/"erp_read" cho chính 2 câu lệnh dùng
    nguyên văn ngôn ngữ quy trình ("quy trình nhập kho cho đơn mua P00021",
    "nhập kho theo quy trình cho đơn mua P00021"), khiến lệnh thật bị lỡ route
    3/3 LẦN THỬ — vì router chưa từng được tune để phân biệt "hỏi VỀ SOP" khỏi
    "thực thi SOP cho 1 đơn cụ thể" (đọc rất giống định nghĩa "mixed" trong
    prompts.py dù ý người dùng là hành động). Chuyển gate sang tất định (đánh
    dấu câu hỏi) giữ nguyên bất biến an toàn (câu hỏi không hijack) mà không
    phụ thuộc phân loại LLM cho quyết định này. Model to hơn CÓ THỂ đủ — nhưng
    "có thể" không phải cơ sở để tháo một lớp phòng thủ đã chứng minh giá trị,
    khi giữ nó tốn 10 dòng.

    Lưới đỡ cuối không phải lớp này: router sai chiều nào thì confirm-gate tại
    tool boundary vẫn chặn mọi write chưa được duyệt."""
    intent = state.get("intent") or "unknown"
    sop = state.get("sop")
    if sop and skill_gate.skills_enabled():
        last_human = next((m.content for m in reversed(state["messages"])
                           if m.type == "human"), "")
        folded = _fold(last_human)
        if intent == "erp_write" or not _looks_like_question(folded):
            return sop            # SOP nhận trọn lượt
    return intent                 # phủ quyết: rớt sop, dùng intent
```

Trong `build_graph()`, thay dòng `g.add_node("intent_router", ...)` và dòng
comment "3 skill agentic tier-2 ... KHÔNG port ở SP-1" bằng:

```python
    # Nạp SOP MỘT LẦN, fail-loud: SKILL.md sai thẩm quyền/cấu trúc → ném
    # SkillManifestError ra ngoài build_graph → ERPAgent.setup() → app KHÔNG
    # LÊN. Thà không lên còn hơn lên sai (cùng triết lý assert_embedding_marker).
    skill_specs = load_skill_specs()

    g.add_node("intent_router", make_intent_router_node(
        llms["router"], render_worker_block(skill_specs),
        frozenset(s.name for s in skill_specs)))
```

...và ngay trước `g.set_entry_point("intent_router")`:

```python
    for spec in skill_specs:
        # Node SOP add THẲNG vào graph ngoài (không bọc hàm async viết tay) —
        # điều kiện để interrupt() trong tool của nó compose đúng với
        # checkpointer. recursion_limit áp trong build_skill_node (wiring).
        g.add_node(spec.name, build_skill_node(spec, llms["planner"], tools))
        g.add_edge(spec.name, "agentic_context_sync")
    g.add_node("agentic_context_sync", make_agentic_context_sync_node())
    g.add_edge("agentic_context_sync", END)
```

...và sau khi dựng `intent_targets`:

```python
    intent_targets.update({s.name: s.name for s in skill_specs})
```

- [ ] **Bước 4: Sửa spy trong `test_build_graph_accepts_role_mapping`**

`make_intent_router_node` giờ nhận 3 tham số. Trong
`backend/tests/agents/test_graph_build.py`, sửa `spy_llm_only` thành:

```python
    def spy_llm_only(name, real):
        def _spy(llm, *args, **kwargs):
            captured[name] = llm
            return real(llm, *args, **kwargs)
        return _spy
```

- [ ] **Bước 5: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_graph_build.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 6: Chạy toàn bộ suite đơn vị**

Run: `cd backend && python -m pytest -q --continue-on-collection-errors`
Expected: PASS. Sau đó **bắt buộc**:
`git checkout -- backend/tests/rag/fixtures/` (suite rag re-serialize 2 fixture
nhị phân).

- [ ] **Bước 7: Commit**

```bash
git status                                  # xác nhận fixtures rag đã sạch
git add backend/src/agents/graph.py backend/tests/agents/test_graph_build.py
git commit -m "feat(agents): định tuyến hybrid SOP — đề cử router + phủ quyết tất định"
```

---

### Task 10: Bộ eval `SOP_SELECT_CASES` + đăng ký gate

Bảy bộ eval của SP-0 không có bộ nào đo tier-2 (3 skill SOP ra đời **sau**
SP-0). Nghĩa là mọi cơ chế chọn SOP — cũ lẫn mới — đều **chưa có số**. Bộ này
dựng số đó.

**Files:**
- Modify: `backend/evals/cases.py`
- Modify: `backend/evals/run_eval.py`
- Modify: `backend/jobs/eval_gate.py`

**Interfaces:**
- Consumes: `nodes._parse_router_output`, `graph._route_by_intent`,
  `prompts.render_intent_router_prompt`, `skill_loader.load_skill_specs` /
  `render_worker_block`
- Produces: `SOP_SELECT_CASES`, `run_eval.eval_sop_select`, set `"sop_select"`
  trong CLI `run_eval` và `jobs eval-gate`

- [ ] **Bước 1: Chú thích ranh giới lên 2 case cũ**

Ranh giới cũ "bán / không bán" (khác biệt DUY NHẤT giữa "đi tier-1" và "đi SOP"
là chữ **"bán"**) không bảo vệ được — với người dùng `giao hàng cho đơn S00040`
và `giao hàng cho đơn bán S00040` là **một ý**. Ranh giới mới: *có / không có
ngôn ngữ quy trình*. Hai kỳ vọng cũ **vẫn đúng** dưới ranh giới mới; việc cần
làm là chú thích để đời sau không "sửa giúp".

`backend/evals/cases.py:29`, sửa dòng đó thành:

```python
    # RANH GIỚI SOP (SP-2a §5.1) — ĐỪNG "sửa giúp" kỳ vọng này. Câu không nhắc
    # tới QUY TRÌNH nên đi tier-1 (erp_write → planner), KHÔNG đi SOP
    # giao-hang. Ranh giới cũ "có chữ 'bán' hay không" đã chết (nó không bảo
    # vệ được: với người dùng, có/không có chữ "bán" là một ý). Ranh giới mới
    # bảo vệ được: CÓ ngôn ngữ quy trình → SOP; KHÔNG có → tier-1. Đi tier-1
    # còn rẻ hơn (một call planner thay vì cả ReAct loop) và vẫn có confirm-gate
    # riêng. Đo trực tiếp bởi SOP_SELECT_CASES.
    ("giao hàng cho đơn S00040 luôn nhé", "erp_write"),
```

`backend/evals/cases.py:147` (trong `PLANNER_CASES`), thêm ngay trên dòng đó:

```python
    # RANH GIỚI SOP (SP-2a §5.1) — xem chú thích ở INTENT_CASES. Lệnh trực tiếp
    # không nhắc quy trình → planner tier-1 chọn deliver_order, KHÔNG phải SOP.
```

- [ ] **Bước 2: Thêm `SOP_SELECT_CASES` vào `cases.py`**

Thêm vào cuối `backend/evals/cases.py`:

```python
# ── SOP_SELECT_CASES ────────────────────────────────────────────────────────
# (câu tiếng Việt, ĐÍCH ĐỊNH TUYẾN CUỐI kỳ vọng).
#
# Đích là giá trị _route_by_intent() TRẢ VỀ: tên skill SOP ("giao-hang",
# "nhap-kho", "bao-gia-chiet-khau") hoặc một trong 5 từ intent tier-1. Nghĩa
# là bộ này đo TOÀN BỘ chuỗi quyết định (LLM đề cử + phủ quyết tất định), không
# chỉ đầu ra thô của model — vì lớp tất định LÀ một phần của cơ chế.
#
# Mỗi skill tối thiểu 4 hướng, và HAI HƯỚNG ÂM quan trọng ngang hai hướng
# dương: lỗi đã xảy ra thật là lỗi HIJACK (câu hỏi VỀ quy trình bị SOP cướp).
#
# QUYẾT ĐỊNH (2026-07-31, xem lại lúc viết plan SP-2a): ranh giới SOP là NGỮ
# NGHĨA (ý định "làm đủ quy trình, có kiểm tra/điều kiện" hay không), KHÔNG
# phải khớp chữ "quy trình" — router là LLM đọc `description`, không string-
# match. Mỗi skill dưới đây có ÍT NHẤT một ca dương KHÔNG chứa chữ "quy
# trình" để tự đo đúng việc đó (không phải chỉ nói suông trong description).
SOP_SELECT_CASES = [
    # ── giao-hang ──
    ("làm quy trình giao hàng cho đơn bán S00012", "giao-hang"),
    ("thực hiện quy trình xuất kho cho đơn bán S00015", "giao-hang"),
    # dương, KHÔNG chữ "quy trình" — đo đúng ranh giới ngữ nghĩa (xem quyết
    # định ở trên): có điều kiện/yêu cầu kiểm tra → vẫn là SOP.
    ("giao hàng cho đơn bán S00012 nhưng kiểm tra kỹ hàng trước khi giao",
     "giao-hang"),
    ("quy trình giao hàng gồm những bước nào?", "rag"),          # hỏi VỀ
    ("giao hàng cho đơn S00040 luôn nhé", "erp_write"),          # lệnh trực tiếp, trùng INTENT_CASES:29

    # ── nhap-kho ──
    # 3 ca HỒI QUY 2026-07-16, lấy NGUYÊN VĂN từ live-verify (router phân loại
    # mixed/erp_read cho chính các câu này → lệnh thật lỡ route 3/3 lần thử).
    # Không diễn giải lại — đó là toàn bộ giá trị của chúng.
    ("quy trình nhập kho cho đơn mua P00021", "nhap-kho"),
    ("nhập kho theo quy trình cho đơn mua P00021", "nhap-kho"),
    ("làm quy trình nhập kho cho đơn mua P00021", "nhap-kho"),
    # dương, KHÔNG chữ "quy trình" — cùng lý do với ca giao-hang ở trên.
    ("xác nhận đã kiểm đếm hàng cho đơn mua P00021 rồi mới nhập kho", "nhap-kho"),
    ("quy trình nhập kho là gì?", "rag"),                        # ca hijack GỐC
    ("SOP nhập kho gồm những bước nào?", "rag"),                 # trùng INTENT_CASES:50
    ("nhận hàng cho đơn mua P00003", "erp_write"),               # lệnh trực tiếp

    # ── bao-gia-chiet-khau ──
    # Skill này vốn đã không dựa "quy trình" — ranh giới là "có/không có chiết
    # khấu", một từ khoá miền nghiệp vụ chứ không phải marker quy trình.
    ("làm quy trình báo giá chiết khấu cho Cửa hàng ABC, 5 Tủ gỗ", "bao-gia-chiet-khau"),
    ("báo giá kèm chiết khấu theo cấp khách cho Wood Corner, 10 Desk Pad",
     "bao-gia-chiet-khau"),
    ("chính sách chiết khấu theo cấp khách như thế nào?", "rag"),  # hỏi VỀ
    ("tạo báo giá cho Azure Interior, 2 Large Cabinet", "erp_write"),  # trùng INTENT_CASES:27

    # ── câu bắc cầu (§6.4) ──
    # Ràng buộc kế thừa từ bản gốc: câu gợi ý trong NO_PO_BRIDGE_MSG (prose của
    # nhap-kho) KHÔNG được tự kích hoạt lại chính SOP vừa thoát ra — nếu không
    # người dùng làm đúng lời khuyên sẽ rơi lại vào vòng lặp.
    ("điều chỉnh tồn kho Desk Pad về 100", "erp_write"),
]
```

- [ ] **Bước 3: Thêm `eval_sop_select` vào `run_eval.py`**

Thêm `SOP_SELECT_CASES` vào khối `from evals.cases import (...)`, thêm import:

```python
from src.agents.prompts import render_intent_router_prompt
from src.agents.nodes import _parse_router_output
from src.agents.graph import _route_by_intent
from src.agents.skill_loader import load_skill_specs, render_worker_block
```

Thêm hàm (đặt ngay sau `eval_intent`):

```python
async def eval_sop_select(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo việc CHỌN SOP end-to-end: gọi router thật với prompt thật (đã nối
    khối mô tả worker), parse bằng chính _parse_router_output của node, rồi áp
    chính _route_by_intent của graph. Đo cả chuỗi vì lớp phủ quyết tất định LÀ
    một phần của cơ chế — đo riêng đầu ra thô của model sẽ không nói lên điều
    gì về hành vi thật.

    Gate TUYỆT ĐỐI (giống chitchat, không baseline-relative): đây là hàng rào
    an toàn định tuyến, không phải phép đo chất lượng tương đối. Hướng nguy
    hiểm được đếm riêng: `hijack` = ca kỳ vọng KHÔNG phải SOP mà lại rơi vào
    SOP — đúng lỗi đã xảy ra thật."""
    specs = load_skill_specs()
    prompt = render_intent_router_prompt(render_worker_block(specs))
    valid_sops = frozenset(s.name for s in specs)
    lat: list[float] = []

    async def call(case):
        text, expected = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt), HumanMessage(content=text)]))
        lat.append(ms)
        intent, sop = _parse_router_output(resp.content, valid_sops)
        got = _route_by_intent({"messages": [HumanMessage(content=text)],
                                "intent": intent, "sop": sop})
        if got != expected:
            return {"text": text, "expected": expected, "got": got,
                    "raw_intent": intent, "raw_sop": sop,
                    "hijack": expected not in valid_sops and got in valid_sops}
        return None

    fails, errors = await run_resilient(SOP_SELECT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(SOP_SELECT_CASES)
    # CHỈ đếm từ fails (phép đo thành công) — lỗi API không bao giờ là hijack.
    hijack = sum(1 for f in fails if f["hijack"])
    p50, p95 = _percentiles(lat)
    return {"set": "sop_select", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "hijack": hijack,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

Trong `main()`, thêm `"sop_select"` vào `ap.add_argument("--set", choices=[...])`
và `"sop_select": eval_sop_select` vào dict `_FN`.

- [ ] **Bước 4: Đăng ký set trong `jobs/eval_gate.py`**

`backend/jobs/eval_gate.py`:
- `ROLE_FOR_SET`: thêm `"sop_select": "router"` (SOP đề cử đi cùng lượt gọi
  router, nên đo trên đúng vai đó).
- `EVAL_FN`: thêm `"sop_select": run_eval.eval_sop_select`.
- `BASELINES`: **KHÔNG** thêm entry — gate tuyệt đối, không baseline.
- Trong `_gate()`, thêm ngay sau nhánh `chitchat`:

```python
    if set_name == "sop_select":
        # Gate TUYỆT ĐỐI (§5.3 điều kiện 1: "xanh toàn bộ"), không
        # baseline-relative: đây là hàng rào an toàn định tuyến, không phải phép
        # đo chất lượng tương đối. hijack==0 là hệ quả của acc==1.0 nhưng vẫn
        # kiểm riêng — nó là hướng lỗi đã xảy ra THẬT (live-verify 2026-07-16)
        # và phải nổi rõ trong báo cáo khi gate trượt.
        return result["hijack"] == 0 and result["acc"] == 1.0
```

- Trong `run()`, nhánh `base is None` in ra `violations` — sửa để đỡ cả
  `sop_select`:

```python
        else:
            entry["violations"] = result.get("violations")
            entry["acc"] = result.get("acc")
            entry["hijack"] = result.get("hijack")
            entry.update(lat_p50=result.get("lat_p50"),
                         lat_p95=result.get("lat_p95"))
            print(f"[{set_name}] model={model} pace={pace}s "
                  f"violations={result.get('violations')} "
                  f"acc={result.get('acc')} hijack={result.get('hijack')} "
                  f"→ {'PASS' if ok else 'FAIL'}")
```

- `add_args`: thêm `"sop_select"` vào `choices`.

- [ ] **Bước 5: Test khô — xác nhận đăng ký và công thức gate**

Tạo `backend/tests/agents/test_sop_select_gate.py`:

```python
"""Kiểm tra đăng ký + công thức gate của set sop_select — KHÔNG gọi LLM."""
from evals.cases import SOP_SELECT_CASES
from jobs.eval_gate import BASELINES, EVAL_FN, ROLE_FOR_SET, _gate


def test_set_registered_everywhere():
    assert ROLE_FOR_SET["sop_select"] == "router"
    assert "sop_select" in EVAL_FN
    assert "sop_select" not in BASELINES      # gate tuyệt đối, không baseline


def test_gate_requires_perfect_score_and_zero_hijack():
    assert _gate("sop_select", {"acc": 1.0, "hijack": 0}, None) is True
    assert _gate("sop_select", {"acc": 0.99, "hijack": 0}, None) is False
    assert _gate("sop_select", {"acc": 1.0, "hijack": 1}, None) is False


def test_every_skill_has_at_least_four_cases():
    from src.agents.skill_loader import load_skill_specs
    names = {s.name for s in load_skill_specs()}
    for name in names:
        related = [c for c in SOP_SELECT_CASES if c[1] == name]
        assert len(related) >= 2, f"{name}: quá ít ca hướng DƯƠNG"
    # tổng số ca đủ để mỗi skill có cả hướng âm
    assert len(SOP_SELECT_CASES) >= 4 * len(names)


def test_expectations_are_valid_route_targets():
    from src.agents.nodes import VALID_INTENTS
    from src.agents.skill_loader import load_skill_specs
    valid = VALID_INTENTS | {s.name for s in load_skill_specs()}
    for text, expected in SOP_SELECT_CASES:
        assert expected in valid, f"{text!r}: đích {expected!r} không phải node hợp lệ"


def test_regression_phrasings_present_verbatim():
    """3 câu thua 3/3 lần ở live-verify 2026-07-16 phải có mặt NGUYÊN VĂN."""
    texts = {t for t, _ in SOP_SELECT_CASES}
    assert "quy trình nhập kho cho đơn mua P00021" in texts
    assert "nhập kho theo quy trình cho đơn mua P00021" in texts
    assert "làm quy trình nhập kho cho đơn mua P00021" in texts
    assert "quy trình nhập kho là gì?" in texts      # ca hijack gốc
```

- [ ] **Bước 6: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/agents/test_sop_select_gate.py -v`
Expected: PASS toàn bộ.

- [ ] **Bước 7: Commit**

```bash
git add backend/evals/cases.py backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/agents/test_sop_select_gate.py
git commit -m "feat(evals): bộ SOP_SELECT_CASES + gate tuyệt đối cho việc chọn SOP"
```

---

### Task 11: Xác nhận sống — eval gate thật + một flow SOP đầu-cuối qua Odoo

Task này **không viết mã mới**. Nó chạy hai phép kiểm mà không có phép kiểm đơn
vị nào thay thế được, và ghi kết quả thật vào báo cáo. Bài học SP-1C2 Task 8:
xác minh sống bắt được lỗi Critical mà toàn bộ test đơn vị bỏ lọt.

**Files:**
- Create: `docs/superpowers/plans/2026-07-31-sp2a-sop-skills-report.md`

**Interfaces:**
- Consumes: mọi thứ ở Task 1-10
- Produces: báo cáo có số thật + phán quyết lên sóng

- [ ] **Bước 1: Chạy toàn bộ test đơn vị, 3 chế độ**

```bash
cd backend
python -m pytest -q --continue-on-collection-errors        # mặc định: không mạng, không PG
python -m pytest -q -m integration                          # cần youdoo-postgres :5434
git checkout -- tests/rag/fixtures/                         # BẮT BUỘC sau mọi lần chạy full
```
Expected: PASS cả hai. Ghi số test pass/fail vào báo cáo.

- [ ] **Bước 2: Chạy eval gate THẬT cho `sop_select`**

```bash
cd backend
set -a && source ../.env && set +a
python -m jobs run eval-gate --set sop_select
```
Expected: `GATE PASS`, `acc=1.000 hijack=0`.

Nếu FAIL: **ĐỪNG nới lỏng gate và đừng sửa case cho vừa kết quả.** Hai đường vá
hợp lệ, theo thứ tự rẻ dần (Phụ lục B của spec): (a) siết vế "KHÔNG dùng khi"
trong `description` của skill bị chọn nhầm; (b) nâng model vai `router` trong
catalog. Ghi lại từng lượt chạy (câu nào trượt, `raw_intent`/`raw_sop` là gì)
vào báo cáo làm provenance — đúng cách SP-1C1 giữ 3 lượt gate.

- [ ] **Bước 3: Chạy eval gate THẬT cho `intent` — xác nhận KHÔNG THỤT**

Hợp đồng đầu ra của router vừa đổi (1 từ → 2 dòng), nên bộ `intent` cũ đo đúng
tác động đó.

```bash
cd backend
set -a && source ../.env && set +a
python -m jobs run eval-gate --set intent
```
Expected: `GATE PASS` — `acc >= baseline acc` (baseline
`evals/baseline-qwen3-8b-intent.json`).

Nếu FAIL: hợp đồng 2 dòng làm hại độ chính xác intent. **KHÔNG ghi đè baseline.**
Sửa prompt (`INTENT_ROUTER_PROMPT`) rồi đo lại, ghi từng lượt vào báo cáo.

- [ ] **Bước 4: Xác nhận app fail-loud khi SKILL.md khai tool ngoài quyền**

Đây là điều kiện §9.3 — "app không lên, log chỉ đúng file và đúng dòng sai".

```bash
cd backend
cp skills/giao-hang/SKILL.md /tmp/skill-backup.md
python - <<'PY'
from pathlib import Path
p = Path("skills/giao-hang/SKILL.md")
p.write_text(p.read_text(encoding="utf-8").replace(
    "- name: deliver_order", "- name: xoa_sach_don_hang"), encoding="utf-8")
PY
python -c "
from unittest.mock import MagicMock
from langchain_core.tools import tool
@tool('deliver_order')
async def d(order_ref: str) -> str:
    '''x'''
    return '{}'
from src.agents.graph import build_graph
build_graph(MagicMock(), [d], checkpointer=None)
"
```
Expected: `SkillManifestError: skill 'giao-hang': tool ghi 'xoa_sach_don_hang'
không có trong registry MCP` — traceback nêu đúng tên skill và tên tool sai.

Khôi phục: `cp /tmp/skill-backup.md skills/giao-hang/SKILL.md && git diff --stat`
(phải sạch).

- [ ] **Bước 5: Xác nhận "sửa prose + restart → hành vi đổi, không đụng .py"**

Đây là điều kiện §9.2 — năng lực low-code, lý do tồn tại của cả SP-2a.

1. Khởi động `mcp-odoo` SSE (:8001), Postgres (:5434) và backend:
   `cd backend && python run.py`
2. Sửa **một dòng prose** trong `backend/skills/giao-hang/SKILL.md` (ví dụ đổi
   bước 4 thành "Thông báo kết quả, và LUÔN kết thúc bằng câu 'Đã xong nhé.'").
3. Restart backend, gửi lại cùng một câu, quan sát câu trả lời đổi theo.
4. `git checkout -- backend/skills/giao-hang/SKILL.md`.

Ghi vào báo cáo: câu trả lời trước và sau, kèm khẳng định **không file `.py`
nào bị sửa** (`git status` sạch sau bước 4).

- [ ] **Bước 6: Viết test live e2e (§7 hàng cuối) và chạy nó**

Bước 7 dưới đây kiểm bằng tay, không lặp lại được. §7 của spec yêu cầu thêm một
test `@pytest.mark.live` để flow này được codify và chạy lại được.

Tạo `backend/tests/agents/test_dau_cuoi_sop.py` — cùng khuôn fixture với
`test_dau_cuoi.py` (event loop module-scope là **bắt buộc**: `ERPAgent` giữ
`AsyncConnectionPool` bám vào loop đã tạo ra nó, `asyncio.run()` riêng lẻ mỗi
test sẽ dùng lại pool CHẾT):

```python
"""Flow SOP thật đầu-cuối qua MCP + Odoo (§7, §9.7). Không khẳng định NỘI DUNG
dữ liệu Odoo (đổi theo môi trường) — khẳng định ĐƯỜNG ĐI: câu lệnh có ngôn ngữ
quy trình vào đúng node SOP, và cổng xác nhận thật sự chặn khi user từ chối."""
import asyncio
import os

import pytest

pytestmark = pytest.mark.live

CAN_CO = ("GOOGLE_API_KEY", "ODOO_URL", "DATABASE_URL", "MCP_ODOO_URL")


@pytest.fixture(scope="module")
def event_loop_sop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def agent(event_loop_sop):
    thieu = [k for k in CAN_CO if not os.environ.get(k)]
    if thieu:
        pytest.skip(f"thiếu biến môi trường: {thieu}")
    from src.agents.erp_agent import ERPAgent
    a = ERPAgent()
    event_loop_sop.run_until_complete(a.setup())
    yield a
    event_loop_sop.run_until_complete(a.aclose())


def test_lenh_co_ngon_ngu_quy_trinh_vao_node_sop(agent, event_loop_sop):
    """"làm quy trình nhập kho cho đơn mua P00021" phải vào node nhap-kho —
    biểu hiện quan sát được: trợ lý HỎI LẠI (bước 1/3 của SOP: mã đơn hoặc số
    lượng thực nhận), chứ không tự ý báo đã nhận hàng."""
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "làm quy trình nhập kho cho đơn mua P00021"}],
        thread_id="test-sop-nhap-kho-1"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
    assert "?" in tra_loi, f"SOP không hỏi lại — có thể đã đi tier-1: {tra_loi[:300]}"


def test_cau_hoi_ve_quy_trinh_khong_bi_sop_cuop(agent, event_loop_sop):
    """Ca hijack GỐC. "quy trình nhập kho là gì?" phải đi RAG — biểu hiện: KHÔNG
    hỏi mã đơn / số lượng thực nhận (đó là dấu hiệu SOP đã cướp lượt)."""
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "quy trình nhập kho là gì?"}],
        thread_id="test-sop-hijack-1"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    low = tra_loi.lower()
    assert "số lượng thực nhận" not in low, f"SOP cướp lượt câu hỏi: {tra_loi[:300]}"


def test_tu_choi_xac_nhan_thi_khong_ghi_gi(agent, event_loop_sop):
    """Cổng xác nhận tại tool boundary — lưới đỡ CUỐI, tất định, fail-closed.
    Trả lời "không" ở bước confirm phải cho ra REFUSED_MSG-flavored reply và
    KHÔNG ghi gì vào Odoo."""
    tid = "test-sop-refuse-1"
    event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "làm quy trình giao hàng cho đơn bán S00012"}],
        thread_id=tid))
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "không"}], thread_id=tid))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
```

```bash
cd backend
set -a && source ../.env && set +a
python -m pytest tests/agents/test_dau_cuoi_sop.py -v -m live
```
Expected: PASS (hoặc SKIP nếu thiếu biến môi trường — SKIP **không** tính là
đạt, phải chạy thật ít nhất một lần và ghi kết quả vào báo cáo).

- [ ] **Bước 7: Chạy một flow SOP đầu-cuối qua Odoo thật (kiểm bằng tay)**

Cần `mcp-odoo` :8001, Odoo :8069, Postgres :5434, backend :8000 cùng chạy.

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"erp-assistant","messages":[
        {"role":"user","content":"làm quy trình nhập kho cho đơn mua P00021"}]}' \
  | python -m json.tool
```

Kiểm đúng 5 điều, ghi từng điều vào báo cáo:
1. Trợ lý **hỏi số lượng thực nhận** (bước 3 của SOP) — chứng tỏ node
   `nhap-kho` nhận lượt, không phải tier-1.
2. Trả lời tiếp số lượng → trợ lý tra đơn rồi **hỏi QC** (hoặc ghi chú lệch số
   lượng nếu không khớp).
3. Trước khi ghi, trợ lý **hỏi xác nhận đúng nguyên văn**
   `Xác nhận NHẬN HÀNG cho đơn mua P00021?` — wrapper sinh tự động hoạt động
   thật, không chỉ trong test.
4. Trả lời "không" → **không có gì được ghi vào Odoo** (kiểm trạng thái đơn
   trên :8069).
5. Chạy lại, trả lời "có" → đơn chuyển trạng thái đúng; lượt **sau** đó hỏi
   "đơn đó sao rồi?" hiểu được "đơn đó" — chứng tỏ `agentic_context_sync` đã
   bàn giao `working_context` về tier-1.

Thêm một lượt kiểm nhánh bắc cầu: hỏi `"nhập kho mà không có đơn mua thì sao"`
→ trợ lý trả **nguyên văn** `NO_PO_BRIDGE_MSG`; gõ tiếp đúng câu nó gợi ý
(`điều chỉnh tồn kho Desk Pad về 100`) → đi **tier-1**, không quay lại
`nhap-kho`.

- [ ] **Bước 8: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-07-31-sp2a-sop-skills-report.md` với:
- Kết quả 3 chế độ test (số pass/fail thật, không làm tròn lời).
- Từng lượt chạy eval gate `sop_select` và `intent`: model, pace, acc, hijack,
  danh sách case trượt kèm `raw_intent`/`raw_sop`. Giữ **mọi** lượt, kể cả lượt
  trượt — provenance, đúng cách SP-1C1 giữ 3 lượt.
- Bằng chứng cho từng điều kiện §9.1-§9.7 của spec, ghi rõ điều nào **chưa**
  đạt nếu có.
- Mọi hạn chế còn lại được người dùng chấp nhận, ghi thẳng ra (không giấu
  trong ngoặc).

- [ ] **Bước 9: Commit**

```bash
git status                                  # fixtures rag sạch, skills/ sạch
git add backend/tests/agents/test_dau_cuoi_sop.py docs/superpowers/plans/2026-07-31-sp2a-sop-skills-report.md
git commit -m "docs: báo cáo xác nhận sống SP-2a — eval gate + flow SOP thật qua Odoo"
```

---

## Phụ lục — Quyết định phải có comment tại chỗ

Luật đã áp dụng từ SP-1: quyết định nào đời sau **không được phép bàn lại** thì
phải có comment trong **file được version-control**, tại đúng điểm mã nó ảnh
hưởng — không chỉ trong plan hay spec. Kiểm lại trước khi đóng nhánh:

| Quyết định | File | Task |
|---|---|---|
| Bất biến tiền bạc: model không bao giờ tính hay truyền số tiền | `backend/skills/bao-gia-chiet-khau/logic.py` (docstring module) | 7 |
| `_looks_like_question` phủ quyết là **tất định có chủ đích**, vì router LLM đã thua bài này 3/3 lần (live-verify 2026-07-16) | `backend/src/agents/graph.py`, tại `_route_by_intent` | 9 |
| Markdown không bao giờ định nghĩa tool mới; wrapper ghi luôn do loader sinh và luôn bọc `_confirm_write` | `backend/src/agents/skill_loader.py`, docstring module + `_make_gated_write_tool` | 4 |
| `recursion_limit` áp **tại wiring**, không trong hàm dựng agent (spike v10b) | `backend/src/agents/skill_loader.py`, tại `build_skill_node` | 5 |
| Vế "KHÔNG dùng khi" chỉ **cảnh báo**, không chặn — nó là chất lượng prompt, không phải thẩm quyền | `backend/src/agents/skill_manifest.py`, docstring module | 2 |
| Registry MCP rỗng = đường test, không phải đường production | `backend/src/agents/skill_loader.py`, docstring `build_skill_tools` | 4 |
| Ranh giới SOP: *có/không có ngôn ngữ quy trình*, không phải *có/không có chữ "bán"* | `backend/evals/cases.py`, cạnh 2 case cũ | 10 |

## Phụ lục — "SP-2a xong" nghĩa là (§9 của spec)

1. `backend/skills/` có 3 thư mục; `giao-hang` và `nhap-kho` chỉ có `SKILL.md`;
   `bao-gia-chiet-khau` có thêm `logic.py`. → Task 6, 7
2. Sửa một dòng prose trong `SKILL.md` + restart → hành vi trợ lý đổi theo,
   không đụng file `.py` nào. → Task 11 bước 5
3. Khai một tool không có quyền trong `SKILL.md` → **app không lên**, log chỉ
   đúng file và đúng chỗ sai. → Task 11 bước 4
4. `SOP_SELECT_CASES` xanh toàn bộ, gồm cả ca hồi quy nguyên văn 2026-07-16;
   bộ `intent` cũ không thụt. → Task 11 bước 2, 3
5. Test bất biến bảo mật mở rộng xanh: không node SOP nào tới được từ chỗ khác
   `intent_router`; không tool ghi trần nào lọt vào node SOP. → Task 9
6. Toàn bộ test xanh ở cả ba chế độ. → Task 11 bước 1
7. Một flow SOP thật chạy đầu-cuối qua Odoo thật. → Task 11 bước 6 (test
   `@pytest.mark.live`, chạy lại được) + bước 7 (kiểm bằng tay, sâu hơn)

**Chưa làm được sau SP-2a (cố ý, không phải thiếu sót):** chưa có UI soạn SOP,
chưa hot-reload (sửa SOP phải restart), chưa có orchestrator, `fusion` vẫn còn.
Đó là việc của SP-2b và sau đó.
