# Suy ra bảng bộ phận + chốt drift bảng quyền — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xoá một trong hai danh sách khai tay đang mô tả cùng một sự thật ("tool X thuộc bộ phận nào"), và thêm người canh cho bảng quyền chép tay còn lại.

**Architecture:** `DEPT_OF` chuyển từ `prompts.py` sang `roles.py` và thành nguồn duy nhất; `RoleCfg.other_dept` từ trường khai tay thành **thuộc tính suy ra** từ bảng đó, cộng một lối thoát `other_dept_extra` chỉ dùng cho thứ suy diễn không diễn đạt được. Riêng `TOOL_ACCESS_MAP` giữ nguyên dạng tường minh nhưng được một test canh ở phạm vi **model**.

**Tech Stack:** Python 3.11, dataclasses, pytest, `ast` để quét nguồn tool.

**Spec:** `docs/superpowers/specs/2026-08-12-role-declaration-derivation-design.md`

## Global Constraints

- **Ngôn ngữ:** comment và chuỗi hiển thị bằng tiếng Việt, theo lối viết các file xung quanh. **Tên hàm và biến bằng tiếng Anh** — ba task của đợt trước đã phải mở vòng sửa vì điều này.
- **Không hồi quy:** `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"` phải giữ **1289 passed, 4 skipped, 46 deselected** cộng các test mới. Đây là chuẩn đã đo.
- **`allowed_tools()` KHÔNG được đổi** ở bất kỳ vai/profile nào. Đó là ranh giới quyền tài khoản Odoo; đợt này chỉ đụng nội dung prompt. Task 2 có test đối chứng khoá bất biến này.
- **Không suy `operation` tự động** trong Task 3. `ODOO_METHOD_OPERATION_MAP` chỉ được dùng để phân biệt **đọc/ghi**, không dùng để kết luận một method ghi cần `create` hay `write` — xem spec §4.3, đó là đúng lỗi đã phải sửa ngày 2026-08-12.
- `backend/tests/jobs/test_eval_latency.py::test_timed_returns_result_and_positive_latency` **flaky sẵn có** (assert theo ngưỡng thời gian). Nếu đỏ, chạy lại riêng để xác nhận rồi nói rõ — KHÔNG "sửa" nó.
- Chạy full suite có thể làm bẩn `backend/tests/rag/fixtures/*` — lỗi sẵn có, **để nguyên, không commit**.
- **Subagent KHÔNG được khởi động/dừng/khởi động lại tiến trình hay container, KHÔNG chạy verify sống, KHÔNG nối Odoo.** Toàn bộ việc chạm hạ tầng do controller làm (§ Nghiệm thu sống cuối plan).

---

### Task 1: `DEPT_OF` chuyển sang `roles.py` và bổ sung 3 mục thiếu

Task này một mình đã sửa chế độ hỏng thứ hai (lời từ chối nói "bộ phận **khác**" thay vì nêu tên).

**Files:**
- Modify: `backend/src/agents/roles.py` (thêm `DEPT_OF` ở module level)
- Modify: `backend/src/agents/prompts.py:266`, `:270-290` (xoá `_DEPT_OF`, import từ `roles`)
- Test: `backend/tests/agents/test_dept_of.py` (tạo mới)

**Interfaces:**
- Consumes: `roles.PROFILES`, `RoleCfg.own`, `RoleCfg.needs_sign_off`, `RoleCfg.label`
- Produces:
  - `roles.DEPT_OF: dict[str, str]` — tool → tên bộ phận. Task 2 suy `other_dept` từ chính bảng này.
  - `prompts.dept_of(tool) -> str` giữ NGUYÊN chữ ký và hành vi (`"khác"` khi không có) — `nodes.py:231` không phải đổi.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_dept_of.py`:

```python
"""DEPT_OF là nguồn sự thật duy nhất cho "tool X thuộc bộ phận nào".

Bảng này từng nằm ở prompts.py và ĐÃ TRÔI LỆCH: đo 2026-08-12 thấy thiếu đúng
3 tool (flag_order_for_review, send_delivery_email, send_invoice_email), cả ba
được thêm vào roles.py ở các đợt sau mà không ai cập nhật bảng. Hệ quả là lời
từ chối nói "liên hệ bộ phận khác" thay vì nêu tên bộ phận thật.

Test dưới đây khoá bất biến đó lại: một tool đã được vai nào đó sở hữu mà chưa
khai bộ phận là đỏ ngay."""
from src.agents import roles
from src.agents import prompts


def _tools_owned_by_any_role():
    """Mọi tool nằm trong own ∪ needs_sign_off của bất kỳ vai nào, mọi profile."""
    owned = set()
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            if cfg.unrestricted:
                continue
            owned |= set(cfg.own) | set(cfg.needs_sign_off)
    return owned


def test_moi_tool_duoc_so_huu_deu_co_bo_phan():
    owned = _tools_owned_by_any_role()
    assert owned, "rỗng thì test này vô nghĩa"
    missing = sorted(t for t in owned if t not in roles.DEPT_OF)
    assert not missing, (
        "tool đã được một vai sở hữu nhưng chưa khai bộ phận trong DEPT_OF — "
        "lời từ chối cho tool này sẽ nói 'bộ phận khác' thay vì nêu tên: "
        f"{missing}")


def test_ba_tool_tung_thieu_nay_da_co():
    """Đối chứng cho phép đo 2026-08-12 — nêu tên thẳng để nếu ai đó gỡ chúng
    ra thì đỏ vì đúng lý do, không phải vì một khẳng định chung chung."""
    assert roles.DEPT_OF["send_delivery_email"] == "Kho"
    assert roles.DEPT_OF["send_invoice_email"] == "Kế toán"
    assert roles.DEPT_OF["flag_order_for_review"] == "Kho"


def test_label_cua_moi_vai_la_mot_bo_phan_co_that():
    """Task 2 suy other_dept bằng cách so DEPT_OF[t] với cfg.label. Nếu label
    không phải một giá trị có trong bảng thì phép so LUÔN đúng và other_dept
    phình ra âm thầm — đây là điểm yếu duy nhất của cách suy diễn đó
    (spec §3.2, §6), nên ghim nó lại."""
    depts = set(roles.DEPT_OF.values())
    for profile_name, profile in roles.PROFILES.items():
        for role_name, cfg in profile.items():
            if cfg.unrestricted:
                continue
            assert cfg.label in depts, (
                f"{profile_name}/{role_name} có label {cfg.label!r} không nằm "
                f"trong các bộ phận của DEPT_OF ({sorted(depts)})")


def test_bang_giu_ca_bo_phan_chua_co_vai_ai():
    """DEPT_OF phải giữ được nghiệp vụ của bộ phận CHƯA có vai AI (Bán hàng,
    Mua hàng). Đây chính là thông tin mà suy diễn từ roles.py KHÔNG tạo ra
    được, và là lý do bảng phải tồn tại thay vì bị bỏ hẳn."""
    owned = _tools_owned_by_any_role()
    khong_vai_nao = {t: d for t, d in roles.DEPT_OF.items() if t not in owned}
    assert khong_vai_nao, "bảng mất hết nghiệp vụ của bộ phận chưa có vai AI"
    assert set(khong_vai_nao.values()) >= {"Bán hàng", "Mua hàng"}


def test_dept_of_cua_prompts_van_doc_tu_roles():
    """prompts.dept_of giữ nguyên chữ ký cho nodes.py, nhưng KHÔNG được giữ
    bản sao bảng thứ hai — đó là đúng thứ đợt này đi xoá."""
    assert prompts.dept_of("post_invoice") == "Kế toán"
    assert prompts.dept_of("send_delivery_email") == "Kho"
    assert prompts.dept_of("tool_bia_ra") == "khác"
    assert not hasattr(prompts, "_DEPT_OF"), (
        "prompts.py không được giữ bản sao _DEPT_OF nữa")
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_dept_of.py -v`
Expected: FAIL — `AttributeError: module 'src.agents.roles' has no attribute 'DEPT_OF'`

- [ ] **Step 3: Thêm `DEPT_OF` vào `roles.py`**

Đặt ngay sau bốn hằng trạng thái (`OWN`/`NEEDS_SIGN_OFF`/`OTHER_DEPT`/`DENIED`), TRƯỚC `class RoleCfg` — Task 2 sẽ dùng nó trong thân class:

```python
# Bộ phận phụ trách từng nghiệp vụ — NGUỒN SỰ THẬT DUY NHẤT cho "tool X thuộc
# bộ phận nào", dùng cho câu từ chối tất định (nodes.py) và cho hint trong
# prompt của planner (prompts.py).
#
# Chuyển từ prompts.py sang đây (spec 2026-08-12 §3.1): đây là dữ liệu phân
# quyền chứ không phải dữ liệu prompt, và other_dept được SUY RA từ chính bảng
# này nên nó phải sống cùng module với RoleCfg.
#
# Bảng CÓ những nghiệp vụ chưa vai AI nào sở hữu (Bán hàng, Mua hàng). Đó là
# thông tin mà suy diễn từ own/needs_sign_off KHÔNG tạo ra được, và là lý do
# bảng phải tồn tại thay vì bỏ hẳn.
#
# Ba mục cuối được bổ sung 2026-08-12: chúng vào roles.py ở các đợt sau mà
# không ai cập nhật bảng, gây 5 khoảng trống trên 2 profile. tests/agents/
# test_dept_of.py giờ khoá lại: sở hữu tool nào thì phải khai bộ phận tool đó.
DEPT_OF = {
    "post_invoice": "Kế toán", "register_payment": "Kế toán",
    "create_credit_memo": "Kế toán", "create_invoice_from_order": "Kế toán",
    "create_bill_from_po": "Kế toán",
    "create_quotation": "Bán hàng", "confirm_sale_order": "Bán hàng",
    "create_rfq": "Mua hàng", "confirm_purchase_order": "Mua hàng",
    "deliver_order": "Kho", "receive_order": "Kho", "validate_picking": "Kho",
    "internal_transfer": "Kho", "inventory_adjustment": "Kho",
    "scrap_product": "Kho", "return_order": "Kho",
    # bổ sung 2026-08-12 — xem comment trên
    "send_delivery_email": "Kho",
    "send_invoice_email": "Kế toán",
    "flag_order_for_review": "Kho",
}
```

- [ ] **Step 4: Xoá bản sao trong `prompts.py`**

Xoá nguyên khối `_DEPT_OF = { ... }` (hiện ở dòng ~280-290, kể cả dòng comment `# Bộ phận phụ trách từng nghiệp vụ — dùng để câu từ chối chỉ được sang đâu.` ngay trên nó).

Thêm vào khối import đầu file:

```python
from .working_context import ORDER_MODELS
from .roles import DEPT_OF
```

(`roles.py` không import gì từ `agents/` nên chiều này không tạo vòng — đã kiểm.)

Sửa dòng 266 trong `planner_prompt_for`:

```python
            kept.append(f"#   - {t} → thuộc bộ phận {DEPT_OF.get(t, 'khác')}")
```

Sửa thân `dept_of` và docstring của nó:

```python
def dept_of(tool: str) -> str:
    """Accessor cho roles.DEPT_OF — nguồn sự thật duy nhất cho "tool X thuộc
    bộ phận nào". Giữ ở đây để nodes.py không phải đổi import, nhưng bảng đã
    chuyển sang roles.py (spec 2026-08-12 §3.1): nó là dữ liệu phân quyền, và
    RoleCfg.other_dept được suy ra từ chính nó. 'khác' = tool không có trong
    bảng (vd tên tool LLM bịa ra) — không có bộ phận cụ thể để chỉ sang."""
    return DEPT_OF.get(tool, "khác")
```

- [ ] **Step 5: Chạy test mới**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_dept_of.py -v`
Expected: PASS, 5 test

- [ ] **Step 6: Chạy toàn bộ suite**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1294 passed, 4 skipped, 46 deselected` (1289 + 5)

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/roles.py backend/src/agents/prompts.py backend/tests/agents/test_dept_of.py
git commit -m "refactor(roles): DEPT_OF về roles.py + bổ sung 3 tool thiếu

Bảng tự nhận trong docstring là 'nguồn sự thật duy nhất' nhưng đã trôi lệch:
thiếu đúng flag_order_for_review, send_delivery_email, send_invoice_email — cả
ba vào roles.py ở các đợt sau mà không ai cập nhật bảng. Hệ quả đo được là lời
từ chối nói 'liên hệ bộ phận khác' thay vì nêu tên bộ phận.

Chuyển sang roles.py vì đây là dữ liệu phân quyền, không phải dữ liệu prompt,
và other_dept sắp được suy ra từ chính nó. prompts.dept_of giữ nguyên chữ ký
nên nodes.py không đổi.

Test khoá bất biến: sở hữu tool nào thì phải khai bộ phận tool đó."
```

---

### Task 2: `other_dept` thành thuộc tính suy ra

Task này sửa chế độ hỏng thứ nhất: lời từ chối **không xảy ra** vì planner không biết tool tồn tại.

**Files:**
- Modify: `backend/src/agents/roles.py:27-53` (`RoleCfg`), `:68-82` (xoá `_WH_OTHER`/`_ACC_OTHER`), `:88-114` (`PROFILES`)
- Modify: `backend/tests/agents/test_roles.py:61-63`, `:71-73` (hai chỗ dựng `RoleCfg`)
- Test: `backend/tests/agents/test_other_dept_derived.py` (tạo mới)

**Interfaces:**
- Consumes: `roles.DEPT_OF` (Task 1)
- Produces:
  - `RoleCfg.other_dept_extra: frozenset` — trường khai tay MỚI, thay chỗ `other_dept` cũ trong constructor
  - `RoleCfg.other_dept` — nay là `@property`, KHÔNG còn là tham số constructor. Mọi nơi đọc `cfg.other_dept` (`prompts.py:248`, `roles.py` `state_of`, `test_roles.py:50`) không phải đổi.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_other_dept_derived.py`:

```python
"""other_dept được SUY RA từ DEPT_OF, không khai tay từng vai.

Vì sao quan trọng: guard tất định trong nodes.py:275 xử lý OTHER_DEPT và DENIED
Y HỆT NHAU, nên other_dept KHÔNG quyết định câu chữ từ chối. Nó quyết định lời
từ chối có XẢY RA hay không — nó là hint trong prompt cho planner biết tool có
tồn tại, để planner trả về đúng tên tool và guard mới có gì để bắt. Thiếu ⇒ LLM
không biết tool có thật ⇒ trả lời hội thoại lan man, guard không chạy. Đo được
đúng như vậy ở nghiệm thu 2026-08-12 (kịch bản 4)."""
import pytest

from src.agents import roles

# Đo 2026-08-12: 5 tool bị denied trong khi vai KHÁC sở hữu chúng.
THIEU_TRUOC_DAY = {
    "warehouse": {"create_invoice_from_order", "create_bill_from_po",
                  "send_invoice_email"},
    "accounting": {"send_delivery_email", "flag_order_for_review"},
}

# Chốt không-hồi-quy cho ranh giới quyền Odoo: allowed_tools() = own ∪
# needs_sign_off, và đợt này KHÔNG được đụng vào nó (spec §3.4).
ALLOWED_MONG_DOI = {
    ("small-business", "warehouse"): {
        "deliver_order", "receive_order", "validate_picking",
        "internal_transfer", "inventory_adjustment", "scrap_product",
        "flag_order_for_review", "return_order", "send_delivery_email"},
    ("small-business", "accounting"): {
        "create_credit_memo", "send_invoice_email",
        "create_invoice_from_order", "create_bill_from_po",
        "post_invoice", "register_payment"},
    ("enterprise", "warehouse"): {
        "deliver_order", "receive_order", "validate_picking",
        "internal_transfer", "send_delivery_email"},
    ("enterprise", "accounting"): {
        "create_credit_memo", "send_invoice_email",
        "create_invoice_from_order", "create_bill_from_po",
        "post_invoice", "register_payment"},
}


@pytest.mark.parametrize("role_name,thieu", sorted(THIEU_TRUOC_DAY.items()))
def test_nam_khoang_trong_da_dong(role_name, thieu):
    cfg = roles.PROFILES["small-business"][role_name]
    con_thieu = sorted(t for t in thieu if cfg.state_of(t) != roles.OTHER_DEPT)
    assert not con_thieu, (
        f"{role_name}: các tool này thuộc bộ phận khác nhưng vẫn bị coi là "
        f"denied, nên planner không được nhắc tên chúng và lời từ chối sẽ "
        f"không xảy ra: {con_thieu}")


def test_other_dept_khong_chua_tool_cua_chinh_vai():
    """Suy diễn phải loại chính nghiệp vụ của vai ra, kể cả tool needs_sign_off."""
    for profile_name, profile in roles.PROFILES.items():
        for role_name, cfg in profile.items():
            if cfg.unrestricted:
                continue
            lan = sorted(cfg.other_dept & (cfg.own | cfg.needs_sign_off))
            assert not lan, f"{profile_name}/{role_name} tự xếp mình vào other_dept: {lan}"


def test_admin_khong_co_other_dept():
    cfg = roles.PROFILES["small-business"]["admin"]
    assert cfg.other_dept == frozenset()


def test_enterprise_giu_duoc_loi_thoat_other_dept_extra():
    """3 nghiệp vụ này thuộc bộ phận KHO nhưng enterprise cố tình xếp ra ngoài
    vai kho, nên suy diễn (so DEPT_OF[t] != label) KHÔNG lấy chúng. Đó là lý do
    other_dept_extra tồn tại (spec §3.3)."""
    ent = roles.PROFILES["enterprise"]["warehouse"]
    for t in ("inventory_adjustment", "scrap_product", "return_order"):
        assert t in ent.other_dept, f"{t} rơi mất khỏi other_dept của enterprise"


def test_enterprise_cung_duoc_ba_tool_moi_suy_ra():
    """KHÔNG phải 'giữ nguyên y hệt bản cũ': tập suy ra RỘNG HƠN tập khai tay
    cũ đúng 3 mục, và đó chính là phần sửa (spec §5.1)."""
    ent = roles.PROFILES["enterprise"]["warehouse"]
    for t in ("create_invoice_from_order", "create_bill_from_po",
              "send_invoice_email"):
        assert t in ent.other_dept


@pytest.mark.parametrize("key,mong_doi", sorted(ALLOWED_MONG_DOI.items()))
def test_allowed_tools_khong_doi(key, mong_doi):
    """Đối chứng cho spec §3.4: đợt này chỉ đụng nội dung prompt, KHÔNG đụng
    ranh giới quyền tài khoản Odoo. Nếu test này đỏ thì
    scripts/odoo_setup_ai_accounts.py sẽ sinh ra bộ nhóm quyền khác trước."""
    profile_name, role_name = key
    cfg = roles.PROFILES[profile_name][role_name]
    assert set(cfg.allowed_tools()) == mong_doi


def test_other_dept_extra_van_duoc_ton_trong_khi_dung_tay():
    """RoleCfg tự chế: label 'X' không có trong DEPT_OF nên mọi mục của bảng
    đều là 'bộ phận khác', cộng thêm phần khai tay."""
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}),
                        other_dept_extra=frozenset({"c"}))
    assert cfg.state_of("a") == roles.OWN
    assert cfg.state_of("c") == roles.OTHER_DEPT
    assert cfg.state_of("post_invoice") == roles.OTHER_DEPT   # từ DEPT_OF
    assert cfg.state_of("tool_bia_ra") == roles.DENIED        # fail-closed
```

- [ ] **Step 2: Chạy test để xác nhận nó thất bại**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_other_dept_derived.py -v`
Expected: FAIL — `TypeError: RoleCfg.__init__() got an unexpected keyword argument 'other_dept_extra'`

- [ ] **Step 3: Sửa `RoleCfg`**

Thay trường `other_dept` bằng `other_dept_extra`, và thêm property:

```python
@dataclass(frozen=True)
class RoleCfg:
    name: str
    label: str
    mcp_url: str
    own: frozenset = field(default_factory=frozenset)
    needs_sign_off: frozenset = field(default_factory=frozenset)
    # Chỉ dùng cho thứ SUY DIỄN KHÔNG DIỄN ĐẠT ĐƯỢC: nghiệp vụ thuộc bộ phận
    # của CHÍNH vai này nhưng bị xếp ra ngoài vai AI (spec 2026-08-12 §3.3).
    # Hiện chỉ hồ sơ 'enterprise' cần, đúng 3 mục. Nghiệp vụ của bộ phận KHÁC
    # thì KHÔNG khai ở đây — other_dept tự suy ra từ DEPT_OF.
    other_dept_extra: frozenset = field(default_factory=frozenset)
    unrestricted: bool = False        # chỉ vai admin

    @property
    def other_dept(self) -> frozenset:
        """Nghiệp vụ vai này KHÔNG làm nhưng có bộ phận cụ thể để chỉ sang.

        SUY RA từ DEPT_OF thay vì khai tay (spec 2026-08-12 §3.2): hai danh
        sách cho cùng một sự thật đã trôi lệch nhau, gây 5 khoảng trống trên 2
        hồ sơ. So sánh dựa trên `label`, vốn đã trùng đúng giá trị bộ phận
        ("Kho", "Kế toán") — test_dept_of.py ghim ràng buộc đó lại.

        Tác dụng thật: đây là HINT trong prompt của planner để nó trả về đúng
        tên tool, nhờ đó guard tất định (nodes.py) mới có gì để bắt và câu từ
        chối mới xảy ra. Guard xử lý OTHER_DEPT và DENIED y hệt nhau, nên tập
        này KHÔNG đổi câu chữ — nó đổi việc câu đó có xuất hiện hay không.
        """
        if self.unrestricted:
            return frozenset()
        derived = frozenset(t for t, d in DEPT_OF.items() if d != self.label)
        return (derived - self.own - self.needs_sign_off) | self.other_dept_extra
```

`state_of` và `allowed_tools` giữ NGUYÊN — `state_of` đọc `self.other_dept` nên tự dùng property mới.

- [ ] **Step 4: Xoá hai tập khai tay và cập nhật `PROFILES`**

Xoá nguyên hai khối `_WH_OTHER = frozenset({...})` và `_ACC_OTHER = frozenset({...})`.

Sửa `PROFILES` — bỏ mọi `other_dept=`, chỉ enterprise/warehouse giữ lối thoát:

```python
PROFILES = {
    "small-business": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg("warehouse", "Kho", MCP_WAREHOUSE,
                             own=_WH_OWN, needs_sign_off=_WH_SIGN_OFF),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF),
    },
    # Doanh nghiệp lớn chia nhỏ trách nhiệm: 3 nghiệp vụ RỜI tập own∪sign_off
    # của vai kho ⇒ quyền bị gỡ khỏi tài khoản Odoo (khác với việc chỉ đổi
    # other_dept↔denied, vốn không đổi gì ở tầng Odoo).
    #
    # Ba nghiệp vụ đó vẫn thuộc bộ phận KHO, nên suy diễn (DEPT_OF[t] != label)
    # không lấy chúng — phải khai qua other_dept_extra để planner vẫn được
    # nhắc tên và lời từ chối vẫn xảy ra.
    "enterprise": {
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True),
        "warehouse": RoleCfg(
            "warehouse", "Kho", MCP_WAREHOUSE,
            own=frozenset({"deliver_order", "receive_order", "validate_picking",
                           "internal_transfer"}),
            needs_sign_off=frozenset({"send_delivery_email"}),
            other_dept_extra=frozenset({"inventory_adjustment",
                                        "scrap_product", "return_order"})),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF),
    },
}
```

- [ ] **Step 5: Sửa hai chỗ dựng `RoleCfg` trong test cũ**

`backend/tests/agents/test_roles.py`, đổi tên tham số ở đúng hai chỗ:

Dòng 61-63:
```python
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset(),
                        other_dept_extra=frozenset())
```

Dòng 71-73:
```python
    cfg = roles.RoleCfg(name="x", label="X", mcp_url="http://localhost:1",
                        own=frozenset({"a"}), needs_sign_off=frozenset({"b"}),
                        other_dept_extra=frozenset({"c"}))
```

KHÔNG đổi gì khác trong file đó — `test_moi_ten_tool_trong_role_cfg_la_tool_that` (dòng 50) đọc `cfg.other_dept` và nay nhận tập suy ra; nó vẫn phải xanh, và nếu đỏ thì đó là phát hiện thật (một tên trong `DEPT_OF` không phải tool có thật), không phải lỗi test.

- [ ] **Step 6: Chạy test mới**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_other_dept_derived.py tests/agents/test_roles.py -v`
Expected: PASS toàn bộ; file mới có **11** test — 2 từ `test_nam_khoang_trong_da_dong` (parametrize 2 vai), 4 từ `test_allowed_tools_khong_doi` (parametrize 2 profile × 2 vai), cộng 5 test thường.

- [ ] **Step 7: Chứng minh test bắt được lỗi thật (deliberate-break)**

Tạm xoá `"send_invoice_email": "Kế toán",` khỏi `DEPT_OF` trong `roles.py`.

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/agents/test_dept_of.py tests/agents/test_other_dept_derived.py -q`
Expected: FAIL — `test_moi_tool_duoc_so_huu_deu_co_bo_phan` và `test_nam_khoang_trong_da_dong[warehouse]` cùng đỏ.

Hoàn nguyên, chạy lại → PASS. Ghi output thật vào report. Đợt trước đã có hai công cụ kiểm tra được tin quá mức vì chưa ai chứng minh chúng bắt được thứ chúng khai.

- [ ] **Step 8: Chạy toàn bộ suite**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1305 passed, 4 skipped, 46 deselected` (1294 + 11)

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/roles.py backend/tests/agents/test_roles.py backend/tests/agents/test_other_dept_derived.py
git commit -m "refactor(roles): other_dept suy ra từ DEPT_OF thay vì khai tay

Danh sách khai tay co từ 16 mục xuống 3, và 3 mục còn lại là thứ suy diễn
không diễn đạt được: enterprise xếp inventory_adjustment/scrap_product/
return_order ra ngoài vai kho NHƯNG chúng vẫn thuộc bộ phận Kho.

Đóng 5 khoảng trống đo được 2026-08-12. other_dept không đổi CÂU CHỮ từ chối
(guard xử lý OTHER_DEPT và DENIED y hệt nhau) — nó đổi việc lời từ chối có
XẢY RA hay không, vì planner phải được nhắc tên tool thì mới trả đúng tên cho
guard bắt.

allowed_tools() không đổi ở bất kỳ vai/profile nào — có test đối chứng, vì đó
là ranh giới quyền tài khoản Odoo."
```

---

### Task 3: Chốt drift cho `TOOL_ACCESS_MAP` (phạm vi model)

**Files:**
- Test: `backend/tests/mcp/test_tool_access_map_drift.py` (tạo mới)

Không sửa `scripts/check_role_odoo_consistency.py` — bảng giữ nguyên dạng tường minh, task này chỉ thêm người canh.

**Interfaces:**
- Consumes: `TOOL_ACCESS_MAP` và `UNMAPPED_TOOLS` từ `scripts/check_role_odoo_consistency.py`; `ODOO_METHOD_OPERATION_MAP` từ `mcp-servers/odoo/security.py`; `roles.PROFILES`. **Phụ thuộc Task 2:** `_declared_tools()` đọc `cfg.other_dept`, nay là thuộc tính suy ra và rộng hơn tập khai tay cũ — bảng phải phủ được cả phần rộng thêm đó.
- Produces: không có API mới — chỉ là cổng nghiệm thu

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_tool_access_map_drift.py`:

```python
"""TOOL_ACCESS_MAP trong scripts/check_role_odoo_consistency.py chép tay từ
mã nguồn tool. Đo 2026-08-12: 8/18 dòng sai — 3 dòng sai operation, 5 dòng
thiếu cặp. Cả hai con số mà báo cáo phân quyền đưa ra đều dựa trên bảng hỏng
đó.

Bảng CỐ Ý giữ dạng tường minh (xem comment trong chính script): một parser
trong production sai thì đo sai âm thầm, một parser trong test sai thì chỉ
gây ồn. Nên bảng ở lại, và test này canh nó.

PHẠM VI: chỉ kiểm MODEL, KHÔNG kiểm operation. ODOO_METHOD_OPERATION_MAP ánh
xạ action_create_invoice -> "create", nên một test dựa vào nó để suy operation
sẽ tái lập đúng dòng sai đã phải sửa (create_bill_from_po gọi
action_create_invoice trên PO CÓ SẴN, cần "write" chứ không phải "create" trên
purchase.order — đo sống đã bác bỏ). Bảng đó phân loại tác dụng phụ phục vụ
cổng xác nhận, không phải quyền Odoo. Ở đây nó CHỈ được dùng để phân biệt đọc
với ghi, điều đó an toàn bất kể ngữ nghĩa quyền.

GIỚI HẠN: một số tool gọi Odoo qua helper dùng chung (vd _validate_order_pickings
trong helpers.py), nên quét thân tool là hụt. Test đi thêm ĐÚNG MỘT CẤP vào hàm
được định nghĩa trong cùng package mcp-servers/odoo. Sâu hơn thì KHÔNG — nêu
thẳng ở đây thay vì để người sau tưởng nó phủ hết."""
import ast
import importlib.util
import pathlib
import sys

import pytest

from src.agents import roles

REPO = pathlib.Path(__file__).resolve().parents[3]
MCP_DIR = REPO / "mcp-servers" / "odoo"
SCRIPT = REPO / "scripts" / "check_role_odoo_consistency.py"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script_mod():
    if not SCRIPT.exists():
        pytest.skip("chưa có scripts/check_role_odoo_consistency.py")
    return _load_module(SCRIPT, "_check_role_odoo_consistency_for_test")


@pytest.fixture(scope="module")
def read_methods():
    """Tên method THUẦN ĐỌC, lấy từ security.py — không khai lại."""
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sec = _load_module(MCP_DIR / "security.py", "_mcp_security_for_test")
    return {m for m, op in sec.ODOO_METHOD_OPERATION_MAP.items() if op == "read"}


@pytest.fixture(scope="module")
def funcs():
    """{tên hàm: ast.FunctionDef} cho mọi file .py trong mcp-servers/odoo."""
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    out = {}
    for f in sorted(MCP_DIR.rglob("*.py")):
        if ".venv" in f.parts or "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, node)
    return out


def _odoo_calls(node, funcs, _depth=0):
    """{(model, method)} cho mọi lệnh odoo(...) trong `node`, đi thêm ĐÚNG MỘT
    cấp vào hàm cùng package được gọi trong thân nó."""
    found = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        ten = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if ten == "odoo" and len(sub.args) >= 2:
            model, method = sub.args[0], sub.args[1]
            if isinstance(model, ast.Constant) and isinstance(method, ast.Constant):
                found.add((model.value, method.value))
        elif _depth == 0 and ten in funcs and ten != node.name:
            found |= _odoo_calls(funcs[ten], funcs, _depth + 1)
    return found


def _declared_tools():
    """Mọi tool khai trong roles.py, mọi profile, mọi vai."""
    out = set()
    for profile in roles.PROFILES.values():
        for cfg in profile.values():
            if cfg.unrestricted:
                continue
            out |= set(cfg.own) | set(cfg.needs_sign_off) | set(cfg.other_dept)
    return out


def test_moi_tool_trong_roles_deu_duoc_bang_phu(script_mod):
    """Thêm tool mới vào roles.py mà quên cập nhật bảng => script kiểm tra âm
    thầm bỏ sót nó."""
    phu = set(script_mod.TOOL_ACCESS_MAP) | set(script_mod.UNMAPPED_TOOLS)
    thieu = sorted(_declared_tools() - phu)
    assert not thieu, (
        "tool khai trong roles.py nhưng không có trong TOOL_ACCESS_MAP cũng "
        f"không trong UNMAPPED_TOOLS: {thieu}")


def test_model_khai_deu_co_that_trong_nguon_tool(script_mod, funcs):
    """Khai -> có thật. Bắt model khai nhầm hoặc không còn được đụng tới."""
    vi_pham = []
    for tool, pairs in script_mod.TOOL_ACCESS_MAP.items():
        node = funcs.get(tool)
        if node is None:
            vi_pham.append(f"{tool}: không tìm thấy hàm trong mcp-servers/odoo")
            continue
        thuc_te = {m for m, _ in _odoo_calls(node, funcs)}
        for model, _op in pairs:
            if model not in thuc_te:
                vi_pham.append(
                    f"{tool}: khai model {model!r} nhưng nguồn không gọi "
                    f"odoo({model!r}, ...) — thực tế chạm: {sorted(thuc_te)}")
    assert not vi_pham, "\n".join(vi_pham)


def test_model_bi_ghi_trong_nguon_deu_da_duoc_khai(script_mod, funcs, read_methods):
    """Có thật -> đã khai. Bắt ĐÚNG 5 dòng thiếu cặp của lần trước."""
    vi_pham = []
    for tool, pairs in script_mod.TOOL_ACCESS_MAP.items():
        node = funcs.get(tool)
        if node is None:
            continue
        da_khai = {m for m, _ in pairs}
        for model, method in _odoo_calls(node, funcs):
            if method in read_methods:
                continue
            if model not in da_khai:
                vi_pham.append(
                    f"{tool}: nguồn GHI vào {model!r} qua {method!r} nhưng "
                    f"model đó không có trong khai báo {sorted(da_khai)}")
    assert not vi_pham, "\n".join(vi_pham)


def test_helper_mot_cap_that_su_duoc_di_vao(funcs):
    """Đối chứng cho giới hạn nêu ở docstring: nếu việc đi một cấp hỏng, hai
    test trên sẽ xanh giả cho mọi tool gọi Odoo qua helper. deliver_order là
    ví dụ thật — nó không tự gọi odoo() trên stock.picking mà đi qua
    _validate_order_pickings trong helpers.py."""
    node = funcs.get("deliver_order")
    assert node is not None, "không tìm thấy deliver_order"
    models = {m for m, _ in _odoo_calls(node, funcs)}
    assert "stock.picking" in models, (
        "đi một cấp vào helper không hoạt động — hai test kia sẽ xanh giả")
```

- [ ] **Step 2: Chạy test**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/mcp/test_tool_access_map_drift.py -v`
Expected: PASS, 4 test. (Bảng đã được sửa đúng ngày 2026-08-12 nên hôm nay không còn vi phạm.)

Nếu có test đỏ: **KHÔNG sửa test cho khớp bảng.** Đọc kỹ thông báo — nhiều khả năng đó là một dòng map sai thật, và đó chính là thứ task này sinh ra để tìm. Báo lại trong report kèm dòng cụ thể.

- [ ] **Step 3: Chứng minh từng test bắt được lỗi thật (deliberate-break)**

Chạy ba lần, mỗi lần sửa tạm `scripts/check_role_odoo_consistency.py` rồi hoàn nguyên:

1. Đổi `"create_bill_from_po"` thành `"create_bill_from_po_XX"` (khoá không còn khớp tool nào)
   → `test_moi_tool_trong_roles_deu_duoc_bang_phu` đỏ, nêu `create_bill_from_po`
2. Trong `"deliver_order"`, đổi `("stock.picking", "write")` thành `("res.partner", "write")`
   → `test_model_khai_deu_co_that_trong_nguon_tool` đỏ, nêu `res.partner`
3. Trong `"register_payment"`, xoá cặp `("account.payment.register", "create")`
   → `test_model_bi_ghi_trong_nguon_deu_da_duoc_khai` đỏ, nêu `account.payment.register`

Sau mỗi lần: hoàn nguyên và chạy lại → PASS. Ghi output thật của cả ba vào report.

- [ ] **Step 4: Chạy toàn bộ suite**

Run: `cd backend && /d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: `1309 passed, 4 skipped, 46 deselected` (1305 + 4)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/mcp/test_tool_access_map_drift.py
git commit -m "test(roles): chốt drift cho TOOL_ACCESS_MAP ở phạm vi model

Bảng chép tay từ mã nguồn tool và đã sai 8/18 dòng. Giữ nguyên dạng tường minh
(một parser trong production sai thì đo sai âm thầm; trong test sai thì chỉ gây
ồn), thêm ba kiểm: bao phủ tool, khai->có thật, có thật->đã khai.

KHÔNG kiểm operation: ODOO_METHOD_OPERATION_MAP ánh xạ action_create_invoice ->
'create', nên test dựa vào nó sẽ tái lập đúng dòng sai đã sửa. Bảng đó phân
loại tác dụng phụ cho cổng xác nhận, không phải quyền Odoo.

Đi đúng một cấp vào helper cùng package, có test đối chứng riêng cho việc đó
(deliver_order chạm stock.picking qua _validate_order_pickings)."
```

---

## Nghiệm thu sống — CONTROLLER làm, không phải subagent

Chạy sau khi cả 3 task xong và test xanh. Phần này chạm hạ tầng sống.

### A. Khởi động lại stack từ worktree của nhánh

**Dừng hẳn stack cũ trước.** `start-dev.ps1` thấy port đang mở sẽ "dùng lại"
tiến trình cũ đang chạy code `main`, và toàn bộ nghiệm thu sẽ là giả — đã bị
đúng bẫy này ở đợt trước.

Worktree không có `.venv` (gitignore) và không có `.env`: sao chép `.env` sang,
tạo junction cho hai venv, và **gỡ junction TRƯỚC khi xoá worktree**.

### B. Hai kịch bản đã hỏng ở đợt trước

Gửi qua `POST :8002/v1/chat/completions` kèm header `x-openwebui-user-id` của
vai tương ứng. **Payload gửi từ file UTF-8** (`curl --data-binary @file`) —
shell mã hoá sai tiếng Việt sẽ làm backend trả 500 và trông như lỗi code.

| # | Vai | Câu hỏi | Trước | Kỳ vọng |
|---|---|---|---|---|
| 3 | kho | *"gửi email hóa đơn INV/2026/00030 cho khách"* | *"liên hệ bộ phận **khác**"* | *"liên hệ bộ phận **Kế toán**"* |
| 4 | kế toán | *"gửi email báo giao hàng cho phiếu WH/OUT/00138"* | trả lời hội thoại, KHÔNG từ chối | từ chối, nêu bộ phận **Kho** |

### C. Đối chứng âm — không chặn nhầm việc thuộc quyền

| Vai | Câu hỏi | Kỳ vọng |
|---|---|---|
| kho | *"gửi email báo giao hàng cho phiếu WH/OUT/00138"* | soạn được, có cổng xác nhận |
| kế toán | *"gửi email hóa đơn INV/2026/00030 cho khách"* | soạn được, có cổng xác nhận |

Thiếu đối chứng này thì "chặn được nhiều hơn" không phân biệt được với "chặn
hỏng".

**Dọn dẹp:** mọi bản nháp `mail.mail` sinh ra khi đo phải xoá. **KHÔNG xác
nhận gửi** ở bất kỳ kịch bản nào.

### D. Chạy lại script nhất quán quyền

```bash
backend/.venv/Scripts/python.exe scripts/check_role_odoo_consistency.py
```

Phải vẫn exit 0 và vẫn đúng 9 GAP đã biết. `other_dept` rộng ra không được làm
đổi kết quả — script đo `has_access` theo `own ∪ needs_sign_off`, mà tập đó
không đổi (Task 2 có test đối chứng). Nếu số GAP đổi thì đó là dấu hiệu
`allowed_tools()` đã bị đụng ngoài ý muốn.

### E. Viết báo cáo

`docs/superpowers/plans/2026-08-12-role-declaration-derivation-report.md` —
kết quả B, C, D, cộng output deliberate-break của Task 2 và Task 3.
