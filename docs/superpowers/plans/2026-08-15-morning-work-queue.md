# Bản tin việc cần xử lý — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Câu "hôm nay tôi cần xử lý gì?" quét mọi hàng đợi việc tồn đọng và trả về bản tin ngắn có số, thay vì trả lời "không có việc nào" như hiện nay.

**Architecture:** Một hàm tổng hợp phía server (`list_pending_work`) gọi 5 hàng đợi tầng 1, gom số đếm, và trả envelope chuẩn. Prompt chỉ đổi một dòng để trỏ câu hỏi buổi sáng sang tool mới. Đưa việc điều phối vào code thay vì phó mặc LLM khiến bản tin **tất định và test được không cần LLM** — điều quan trọng vì cổng eval `read` đang ở 1.000, không còn chỗ trượt.

**Tech Stack:** Python 3.11, LangChain `@tool`, XML-RPC (Odoo 19), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-morning-work-queue-design.md`

## Global Constraints

- **Lệnh test BẮT BUỘC:** `pytest -m "not integration and not live"` chạy từ `backend/`. Lệnh `pytest` trần gọi API LLM thật và Postgres thật — đã gây sự cố, không bao giờ dùng.
- **Định danh tiếng Anh trong mã nguồn** (`backend/src`); chú thích và chuỗi hiển thị tiếng Việt. Mã test trong `backend/tests` theo quy ước phiên âm tiếng Việt sẵn có ở đó.
- **Số đếm phải lấy từ `data["count"]` khi có, chỉ lùi về `len(data["rows"])` khi KHÔNG có khoá đó.** Đo 2026-08-15: `list_late_deliveries` trả `rows=15` nhưng `count=29` (nó chặn rows). Dùng `len(rows)` là báo sai một nửa ngay ở con số tiêu đề.
- **Hàng đợi hỏng KHÔNG BAO GIỜ được đếm thành 0.** Hỏng có thể về dưới dạng exception HOẶC envelope `status == "error"`. Cả hai vào `failed`. "Rỗng" và "không kiểm được" phải phân biệt được — đó là toàn bộ lý do tính năng này tồn tại.
- **`display` không được nói "không còn việc gì nữa".** Nó nói **đã kiểm những gì**. Xem spec §4.
- **Không đụng prompt router, planner, hay SOP skill nào.** Chỉ `SYSTEM_PROMPT`, đúng một dòng.
- Baseline trước khi bắt đầu: **1548 passed, 4 skipped, 48 deselected**.
- Cổng eval: `read` **1.000** (n=20), `intent` 0.8704 (n=54), `planner` 1.000 (n=25), `multi_source` 0.75 (n=8). Chỉ `read` chịu rủi ro.

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/src/erp_query/work_queue.py` | **Tạo mới.** Quét 5 hàng đợi, gom số đếm, tách rỗng khỏi hỏng | 1 |
| `backend/tests/erp_query/test_work_queue.py` | **Tạo mới.** Test tất định, giả 5 hàng đợi | 1, 2 |
| `backend/src/erp_query/work_queue.py` | Suy vai→bộ phận, xếp thứ tự | 2 |
| `backend/src/erp_query/tools.py` | Đăng ký tool, đóng gói `role_cfg` | 3 |
| `backend/src/agents/prompts.py` | Đổi đúng một dòng trong `SYSTEM_PROMPT` | 3 |
| `backend/evals/cases.py` | Ca eval mới: câu buổi sáng + chống-cướp | 4 |

---

## Task 1: Quét hàng đợi, tách "rỗng" khỏi "không kiểm được"

**Files:**
- Create: `backend/src/erp_query/work_queue.py`
- Test: `backend/tests/erp_query/test_work_queue.py` (tạo mới)

**Interfaces:**
- Consumes: `crm.list_my_activities(login, limit=20)`, `inventory.list_late_deliveries(direction=None)`, `accounting.get_overdue_invoices(limit=20)`, `inventory.list_reorder_needed()`, `purchase.list_po_mismatches()` — tất cả trả envelope `{status, data, display}`.
- Produces: `list_pending_work(role: str | None = None) -> dict` — envelope chuẩn. `data` có ba khoá `checked` / `not_checked` / `failed`. Task 2 thêm thứ tự vào `checked`; Task 3 gọi hàm này.

**Bối cảnh mà người thực thi không thể tự biết:** `data` của mỗi hàng đợi có hình dạng KHÁC NHAU, đo 2026-08-15 trên Odoo thật:

| hàng đợi | khoá của `data` | rows | count |
|---|---|---|---|
| `list_my_activities` | `{rows}` | 0 | **không có** |
| `list_late_deliveries` | `{rows, count, capped}` | 15 | **29** |
| `get_overdue_invoices` | `{rows, count}` | 22 | 22 |
| `list_reorder_needed` | `{rows, count}` | 2 | 2 |
| `list_po_mismatches` | `{rows, count, capped}` | 0 | 0 |

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/erp_query/test_work_queue.py`:

```python
"""Bản tin việc cần xử lý — quét nhiều hàng đợi, gom số đếm.

Lớp lỗi nguy hiểm nhất của tính năng này: một hàng đợi HỎNG trông giống hệt
một hàng đợi RỖNG nếu chỉ đọc data rồi len(). Lúc đó bản tin nói "không có
việc" trong khi sự thật là "không hỏi được" — đúng con bug tính năng này sinh
ra để diệt, tái sinh bên trong chính nó. Mọi test dưới đây xoay quanh chỗ đó."""
import pytest

from src.erp_query import work_queue


def _ok(data):
    return {"status": "success", "data": data, "display": "x"}


def _loi():
    return {"status": "error", "data": None, "display": "hỏng", "error": "hỏng"}


@pytest.fixture
def gia_hang_doi(monkeypatch):
    """Thay cả 5 hàm hàng đợi bằng bản giả.

    ⚠️ TRẢ VỀ CHÍNH dict mà work_queue đọc, không phải một bản sao. Test sửa
    `gia_hang_doi["x"] = ...` là sửa thẳng vào đó. Nếu fixture trả về một dict
    cục bộ thì mọi test sửa hàng đợi sẽ XANH GIẢ — chúng đo bản sao chứ không
    đo thứ hàm thật đọc.
    """
    ban = {
        "list_my_activities": _ok({"rows": []}),
        "list_late_deliveries": _ok({"rows": [1] * 15, "count": 29}),
        "get_overdue_invoices": _ok({"rows": [1] * 22, "count": 22}),
        "list_reorder_needed": _ok({"rows": [1, 1], "count": 2}),
        "list_po_mismatches": _ok({"rows": [], "count": 0}),
    }
    monkeypatch.setattr(work_queue, "_HANG_DOI_GIA", ban)
    return work_queue._HANG_DOI_GIA


def test_fixture_that_su_lai_duoc_hang_doi(gia_hang_doi):
    """Đối chứng cho chính fixture: sửa qua nó phải đổi được kết quả. Không có
    test này thì một fixture trả bản sao sẽ làm mọi test hàng-đợi-hỏng xanh
    giả mà không ai biết."""
    gia_hang_doi["list_reorder_needed"] = _ok({"rows": [], "count": 0})
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_reorder_needed"] == 0


def test_lay_count_chu_khong_phai_len_rows(gia_hang_doi):
    """list_late_deliveries chặn rows ở 15 nhưng count thật là 29. Đếm theo
    len(rows) là báo sai MỘT NỬA ngay ở con số tiêu đề."""
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_late_deliveries"] == 29, "đếm theo rows thay vì count"


def test_thieu_khoa_count_thi_lui_ve_len_rows(gia_hang_doi):
    """list_my_activities KHÔNG có khoá count — phải lùi về len(rows), không
    được nổ và không được bỏ qua hàng đợi."""
    gia_hang_doi["list_my_activities"] = _ok({"rows": [1, 1, 1]})
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_my_activities"] == 3


def test_envelope_loi_vao_failed_khong_dem_thanh_0(gia_hang_doi):
    """CA QUAN TRỌNG NHẤT. Hàng đợi trả status=error không được xuất hiện
    trong checked với count=0 — như thế là nói dối rằng đã kiểm và không có
    việc."""
    gia_hang_doi["list_po_mismatches"] = _loi()
    res = work_queue.list_pending_work()
    da_kiem = {c["queue"] for c in res["data"]["checked"]}
    hong = {f["queue"] for f in res["data"]["failed"]}
    assert "list_po_mismatches" not in da_kiem
    assert "list_po_mismatches" in hong


def test_exception_cung_vao_failed(gia_hang_doi, monkeypatch):
    """Hỏng cũng có thể là exception chứ không phải envelope lỗi."""
    def _no(*a, **k):
        raise ValueError("Youdoo AI / Read Only")
    monkeypatch.setitem(work_queue._HANG_DOI_GIA, "list_reorder_needed", _no)
    res = work_queue.list_pending_work()
    hong = {f["queue"] for f in res["data"]["failed"]}
    assert "list_reorder_needed" in hong
    assert "Youdoo AI" not in res["display"], "nguyên văn lỗi rò ra người dùng"


def test_mot_hang_doi_hong_khong_giet_ca_ban_tin(gia_hang_doi):
    """Kế toán trục trặc không được che mất 29 phiếu kho trễ."""
    gia_hang_doi["get_overdue_invoices"] = _loi()
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_late_deliveries"] == 29


def test_tat_ca_rong_van_khong_noi_het_viec(gia_hang_doi):
    """Ràng buộc cứng của spec §4: nói ĐÃ KIỂM GÌ, không nói KHÔNG CÒN GÌ."""
    for ten in gia_hang_doi:
        gia_hang_doi[ten] = _ok({"rows": [], "count": 0})
    res = work_queue.list_pending_work()
    d = res["display"]
    assert "đã kiểm" in d.lower()
    for cam in ("không còn việc", "hết việc", "không có việc nào"):
        assert cam not in d.lower(), f"khẳng định đã quét hết: {cam!r}"


def test_not_checked_mang_dung_tang_hai(gia_hang_doi):
    """Câu "còn gì nữa không" phải có nguyên liệu tất định để trả lời."""
    res = work_queue.list_pending_work()
    assert set(res["data"]["not_checked"]) == set(work_queue.TANG_HAI)
    assert len(work_queue.TANG_HAI) >= 5
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.erp_query.work_queue'`.

- [ ] **Step 3: Viết `work_queue.py`**

Tạo `backend/src/erp_query/work_queue.py`:

```python
"""Bản tin "hôm nay tôi cần xử lý gì?" — quét mọi hàng đợi việc tồn đọng.

Vì sao tổng hợp ở ĐÂY chứ không để LLM tự gọi 5 tool: đo 2026-08-15 cho thấy
LLM LÀM ĐƯỢC khi được bảo tường minh, nhưng số hàng đợi nó quét mỗi lượt là
XÁC SUẤT. Gom vào một hàm biến câu hỏi không kiểm được ("có quét đủ 5 không?")
thành câu hỏi cùng loại với mọi tool khác ("có chọn đúng một tool không?"), và
làm bản tin test được mà không cần gọi LLM.
"""
import logging

from . import accounting, crm, inventory, purchase
from .envelope import ok

logger = logging.getLogger(__name__)

# Cửa sau CHỈ dùng cho test: test đặt hàm/kết quả giả vào đây thay vì
# monkeypatch từng module. Rỗng trong chạy thật.
_HANG_DOI_GIA: dict = {}

# ── Tầng 1: bản thân định nghĩa đã là việc tồn đọng ───────────────────────────
# (tên, nhãn tiếng Việt, bộ phận, hàm gọi). Bộ phận None = việc giao đích danh,
# luôn đứng đầu, không xếp theo bộ phận.
TANG_MOT = [
    ("list_my_activities",   "việc được giao đích danh", None,
     lambda role: crm.list_my_activities(f"ai-{role}" if role else "", limit=20)),
    ("list_late_deliveries", "phiếu giao/nhận trễ hạn",  "Kho",
     lambda role: inventory.list_late_deliveries()),
    ("get_overdue_invoices", "hóa đơn quá hạn",          "Kế toán",
     lambda role: accounting.get_overdue_invoices(limit=20)),
    ("list_reorder_needed",  "mặt hàng cần đặt bổ sung", "Mua hàng",
     lambda role: inventory.list_reorder_needed()),
    ("list_po_mismatches",   "đơn mua lệch hóa đơn",     "Mua hàng",
     lambda role: purchase.list_po_mismatches()),
]

# ── Tầng 2: chỉ thành việc khi lọc trạng thái ────────────────────────────────
# KHÔNG quét mặc định; là nguyên liệu tất định cho câu "còn gì nữa không".
TANG_HAI = [
    "list_sale_orders(state=draft)",
    "list_purchase_orders(state=draft)",
    "list_manufacturing_orders(state=confirmed)",
    "list_crm_leads",
    "find_open_invoices",
]


def _dem(data) -> int:
    """Số việc thật của một hàng đợi.

    ƯU TIÊN data["count"]: đo 2026-08-15, list_late_deliveries trả rows=15
    nhưng count=29 vì nó CHẶN rows. Đếm theo len(rows) là báo sai một nửa.
    Chỉ lùi về len(rows) khi không có khoá count (list_my_activities).
    """
    if not isinstance(data, dict):
        return 0
    if "count" in data:
        return int(data["count"] or 0)
    return len(data.get("rows") or [])


def _goi(ten, ham, role):
    """Gọi một hàng đợi. Trả (count, None) khi được, (None, lý do) khi hỏng."""
    gia = _HANG_DOI_GIA.get(ten)
    try:
        res = gia(role) if callable(gia) else (gia if gia is not None else ham(role))
    except Exception as e:                                  # noqa: BLE001
        logger.exception("hàng đợi %s hỏng: %s: %s", ten, type(e).__name__, e)
        return None, "lỗi hệ thống"
    # Hỏng KHÔNG chỉ đến dưới dạng exception: các hàm hàng đợi trả envelope,
    # nên status="error" cũng là hỏng. Nếu bỏ qua vế này, hàng đợi hỏng sẽ
    # được đếm thành 0 và trông y hệt hàng đợi rỗng — đúng lỗ hổng tính năng
    # này sinh ra để bịt.
    if not isinstance(res, dict) or res.get("status") != "success":
        logger.warning("hàng đợi %s trả envelope lỗi", ten)
        return None, "không lấy được dữ liệu"
    return _dem(res.get("data")), None


def list_pending_work(role: str | None = None) -> dict:
    """Quét tầng 1, trả bản tin ngắn có số.

    `role` do tool wrapper đóng gói truyền xuống, KHÔNG do LLM điền — mọi thứ
    LLM điền được đều là thứ tự khai được (cùng lý do như _role_from_headers).
    """
    checked, failed = [], []
    for ten, nhan, bo_phan, ham in TANG_MOT:
        count, ly_do = _goi(ten, ham, role)
        if ly_do is not None:
            failed.append({"queue": ten, "label": nhan, "reason": ly_do})
        else:
            checked.append({"queue": ten, "label": nhan,
                            "dept": bo_phan, "count": count})
    data = {"checked": checked, "not_checked": list(TANG_HAI), "failed": failed}
    return ok(data, _dung_display(checked, failed))


def _dung_display(checked, failed) -> str:
    """Câu hiển thị.

    RÀNG BUỘC CỨNG (spec §4): không bao giờ nói "không còn việc gì nữa" — chỉ
    nói ĐÃ KIỂM NHỮNG GÌ. Khác biệt giữa "không có việc" và "không có việc TÔI
    BIẾT CÁCH TÌM" chính là con bug ADR-012 tồn tại để chỉ ra.
    """
    co_viec = [c for c in checked if c["count"] > 0]
    dong = [f"- {c['label']}: {c['count']}" for c in co_viec]
    if co_viec:
        dau = f"Có việc cần xử lý ở {len(co_viec)} nhóm:"
    else:
        dau = f"Đã kiểm {len(checked)} hàng đợi, tất cả đang trống:"
        dong = [f"- {c['label']}: 0" for c in checked]
    duoi = []
    if failed:
        duoi.append("Không kiểm được: "
                    + ", ".join(f"{f['label']}" for f in failed) + ".")
    duoi.append("Đã kiểm: " + ", ".join(c["label"] for c in checked) + ".")
    return "\n".join([dau, *dong, *duoi])
```

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: PASS, 8 passed.

- [ ] **Step 5: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS, 1548 + 8 = 1556 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/erp_query/work_queue.py backend/tests/erp_query/test_work_queue.py
git commit -m "feat(work_queue): quét hàng đợi việc, tách rỗng khỏi không-kiểm-được

Số đếm lấy từ data['count'] chứ không phải len(rows): list_late_deliveries
chặn rows ở 15 nhưng count thật là 29. Hàng đợi hỏng vào failed, không bao
giờ đếm thành 0 — rỗng và không-hỏi-được phải phân biệt được."
```

---

## Task 2: Suy vai → bộ phận, và xếp thứ tự

**Files:**
- Modify: `backend/src/erp_query/work_queue.py`
- Test: `backend/tests/erp_query/test_work_queue.py` (thêm vào file Task 1 tạo)

**Interfaces:**
- Consumes: `roles.PROFILES`, `roles.DEPT_OF` (`backend/src/agents/roles.py`), và `list_pending_work` của Task 1.
- Produces: `bo_phan_cua_vai(role: str) -> str | None`; `checked` trong `data` được xếp theo thứ tự.

**Bối cảnh:** `DEPT_OF` ánh xạ **tool GHI** → tên bộ phận tiếng Việt. Không có bảng vai → bộ phận, và **không được tạo bảng thứ hai** — suy ra bằng đa số. Đo 2026-08-15: kho `{Kho: 9}`, kế toán `{Kế toán: 4, Kho: 2}`.

⚠️ Hai phiếu "Kho" của vai kế toán là `log_activity`/`close_activity`, mà **chính comment trong `roles.py` ghi rõ giá trị đó là TUỲ TIỆN**. Suy theo đa số đúng hôm nay nhưng dựa trên một giá trị tuỳ tiện — nên phải ghim bằng test.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/erp_query/test_work_queue.py`:

```python
def test_suy_bo_phan_tu_tool_so_huu():
    """Suy ra, KHÔNG khai bảng thứ hai. Ghim kết quả vì nó dựa một phần vào
    giá trị mà roles.py tự nhận là TUỲ TIỆN (log_activity/close_activity =
    "Kho"); nếu đa số đổi chiều, test này phải đỏ để có người xem lại."""
    assert work_queue.bo_phan_cua_vai("warehouse") == "Kho"
    assert work_queue.bo_phan_cua_vai("accounting") == "Kế toán"
    assert work_queue.bo_phan_cua_vai("admin") is None      # unrestricted
    assert work_queue.bo_phan_cua_vai("khong-ton-tai") is None


def test_viec_dich_danh_luon_dung_dau(gia_hang_doi):
    """Bất kể vai nào — việc giao đích danh không xếp theo bộ phận."""
    for vai in ("warehouse", "accounting", None):
        res = work_queue.list_pending_work(vai)
        assert res["data"]["checked"][0]["queue"] == "list_my_activities"


def test_hang_doi_bo_phan_cua_vai_len_truoc(gia_hang_doi):
    """Sau việc đích danh, hàng đợi thuộc bộ phận của vai đứng trước."""
    kho = [c["queue"] for c in
           work_queue.list_pending_work("warehouse")["data"]["checked"]]
    assert kho[1] == "list_late_deliveries"                 # Kho

    kt = [c["queue"] for c in
          work_queue.list_pending_work("accounting")["data"]["checked"]]
    assert kt[1] == "get_overdue_invoices"                  # Kế toán


def test_vai_khong_ro_bo_phan_giu_thu_tu_khai(gia_hang_doi):
    """admin (unrestricted) không suy ra được bộ phận ⇒ giữ nguyên thứ tự."""
    ad = [c["queue"] for c in
          work_queue.list_pending_work("admin")["data"]["checked"]]
    assert ad == [t[0] for t in work_queue.TANG_MOT]


def test_bang_bo_phan_hang_doi_ghim_hai_chieu():
    """TANG_MOT là nguồn sự thật THỨ HAI (DEPT_OF chỉ phủ tool ghi). Ghim cả
    hai chiều: thiếu dòng nào, hoặc thêm bộ phận lạ, đều phải đỏ."""
    that = {ten: bo_phan for ten, _, bo_phan, _ in work_queue.TANG_MOT}
    assert that == {
        "list_my_activities": None,
        "list_late_deliveries": "Kho",
        "get_overdue_invoices": "Kế toán",
        "list_reorder_needed": "Mua hàng",
        "list_po_mismatches": "Mua hàng",
    }
    hop_le = set(roles_mod.DEPT_OF.values()) | {None}
    assert set(that.values()) <= hop_le, "bộ phận không có trong DEPT_OF"
```

Thêm import ở đầu file test: `from src.agents import roles as roles_mod`.

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: FAIL — `AttributeError: module 'src.erp_query.work_queue' has no attribute 'bo_phan_cua_vai'`.

- [ ] **Step 3: Cài suy bộ phận + xếp thứ tự**

Thêm vào `work_queue.py`, sau `TANG_HAI`:

```python
def bo_phan_cua_vai(role: str | None) -> str | None:
    """Bộ phận của một vai — SUY RA từ tool nó sở hữu, không khai bảng thứ hai.

    Lấy đa số của DEPT_OF trên cfg.own. Đo 2026-08-15: kho {Kho: 9}, kế toán
    {Kế toán: 4, Kho: 2}. Hai phiếu "Kho" của kế toán là log_activity/
    close_activity, mà roles.py tự ghi rằng giá trị đó TUỲ TIỆN — nên kết quả
    được ghim bằng test, không thả trôi.

    Vai unrestricted (admin) không có bộ phận ⇒ None ⇒ giữ thứ tự khai.
    """
    if not role:
        return None
    from collections import Counter

    from ..agents import roles as roles_mod

    for profile in roles_mod.PROFILES.values():
        cfg = profile.get(role)
        if cfg is None or getattr(cfg, "unrestricted", False):
            continue
        dem = Counter(roles_mod.DEPT_OF[t] for t in cfg.own
                      if t in roles_mod.DEPT_OF)
        if dem:
            return dem.most_common(1)[0][0]
    return None
```

Rồi sửa `list_pending_work`: sau vòng lặp, trước khi dựng `data`, chèn

```python
    bo_phan = bo_phan_cua_vai(role)
    if bo_phan:
        # Việc đích danh (dept None) luôn đứng đầu tuyệt đối; sau đó hàng đợi
        # thuộc bộ phận của vai; phần còn lại giữ nguyên thứ tự khai.
        checked.sort(key=lambda c: (c["dept"] is not None,
                                    c["dept"] != bo_phan))
```

`list.sort` ổn định nên phần còn lại giữ nguyên thứ tự khai.

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: PASS, 13 passed.

- [ ] **Step 5: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS, 1561 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/erp_query/work_queue.py backend/tests/erp_query/test_work_queue.py
git commit -m "feat(work_queue): xếp hàng đợi theo bộ phận của vai

Vai→bộ phận SUY RA từ DEPT_OF trên cfg.own, không khai bảng thứ hai. Kết
quả được ghim bằng test vì nó dựa một phần vào giá trị mà roles.py tự nhận
là tuỳ tiện."
```

---

## Task 3: Đăng ký tool và móc vào prompt

**Files:**
- Modify: `backend/src/erp_query/tools.py`
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/erp_query/test_work_queue.py` (thêm)

**Interfaces:**
- Consumes: `work_queue.list_pending_work(role)` (Task 1+2), `build_erp_query_tools(role_cfg)` (`tools.py:63`).
- Produces: tool `list_pending_work` trong danh sách trả về của `build_erp_query_tools`.

**Bối cảnh:** `build_erp_query_tools(role_cfg=None)` đã nhận `role_cfg` sẵn, và `tools.py:228-230` đã có khuôn đóng gói y hệt cho `list_my_activities`:

```python
if role_cfg is None:
    return _json(crm.list_my_activities("", limit=limit))
return _json(crm.list_my_activities(f"ai-{role_cfg.name}", limit=limit))
```

⚠️ **Tool KHÔNG được nhận tham số `role`.** LLM điền được thì vai tự khai được — phá đúng nguyên tắc `_role_from_headers` dựng lên ("vai KHÔNG lấy từ body"). Đóng gói `role_cfg` trong closure.

⚠️ `_forbid_extra_kwargs` và `_reject_ref_shaped_partner_names` chạy trên mọi tool ở `tools.py:240-242` — tool mới cũng phải qua được.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/erp_query/test_work_queue.py`:

```python
def test_tool_duoc_dang_ky_va_khong_lo_tham_so_role():
    """LLM không được nhìn thấy tham số role — điền được là tự khai được."""
    from src.erp_query.tools import build_erp_query_tools

    class _Cfg:
        name = "warehouse"
        own = set()
        unrestricted = False

    ten = {t.name for t in build_erp_query_tools(_Cfg())}
    assert "list_pending_work" in ten

    t = next(t for t in build_erp_query_tools(_Cfg())
             if t.name == "list_pending_work")
    assert "role" not in (t.args or {}), "LLM tự khai được vai"


def test_prompt_khong_con_day_ket_luan_tu_mot_hang_doi():
    """Dòng cũ dạy trợ lý trục 'việc của tôi' — đúng trục ADR-012 §3 chứng
    minh sai (91/94 phiếu kho không có người phụ trách)."""
    from src.agents.prompts import SYSTEM_PROMPT

    assert "list_pending_work" in SYSTEM_PROMPT
    assert "KHÔNG được kết luận" in SYSTEM_PROMPT
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: FAIL — `list_pending_work` không có trong tên tool; `SYSTEM_PROMPT` chưa nhắc tới.

- [ ] **Step 3: Đăng ký tool**

Trong `backend/src/erp_query/tools.py`, thêm `work_queue` vào dòng import sẵn có, rồi thêm tool ngay TRƯỚC `list_my_activities` (đứng cạnh nhau vì chúng là cặp dễ nhầm):

```python
    @tool
    def list_pending_work() -> str:
        """Mọi việc đang tồn đọng cần xử lý, gom theo nhóm, có số lượng.

        Dùng khi người dùng hỏi kiểu "hôm nay tôi cần xử lý gì?", "có việc gì
        không?", "còn gì nữa không?" — tức hỏi CHUNG, không nêu rõ loại chứng
        từ nào. Tool này quét nhiều hàng đợi cùng lúc (việc được giao, phiếu
        trễ, hóa đơn quá hạn, hàng cần đặt, đơn mua lệch).

        KHÔNG dùng khi người dùng hỏi về MỘT loại cụ thể — lúc đó gọi thẳng
        tool của loại đó (list_late_deliveries, get_overdue_invoices, ...).
        """
        return _json(work_queue.list_pending_work(
            role_cfg.name if role_cfg is not None else None))
```

Thêm `list_pending_work` vào danh sách `tools = [...]` ở cuối hàm.

- [ ] **Step 4: Sửa prompt — đúng một dòng thành hai**

Trong `backend/src/agents/prompts.py`, thay dòng

```
- Việc được giao: list_my_activities (dùng khi user hỏi "có việc gì chuyển cho tôi không", "việc của tôi").
```

bằng

```
- Việc cần xử lý: list_pending_work (khi user hỏi "hôm nay cần xử lý gì", "có việc gì không", "còn gì nữa không"). KHÔNG được kết luận "không có việc" chỉ từ list_my_activities — đó chỉ là MỘT trong nhiều hàng đợi.
- Việc giao đích danh cho một người: list_my_activities.
```

- [ ] **Step 5: Chạy lại — phải XANH**

Run: `pytest tests/erp_query/test_work_queue.py -m "not integration and not live" -v`
Expected: PASS, 15 passed.

- [ ] **Step 6: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS. Nếu có test đỏ vì khớp nội dung `SYSTEM_PROMPT`, **dừng lại và báo cáo** — đừng sửa test cho vừa.

- [ ] **Step 7: Commit**

```bash
git add backend/src/erp_query/tools.py backend/src/agents/prompts.py backend/tests/erp_query/test_work_queue.py
git commit -m "feat(tools): đăng ký list_pending_work + móc prompt

Vai đóng gói trong closure, KHÔNG là tham số tool — LLM điền được thì vai
tự khai được. Prompt cấm kết luận 'không có việc' chỉ từ một hàng đợi."
```

---

## Task 4: Ca eval — đo cả thụt lẫn cướp

**Files:**
- Modify: `backend/evals/cases.py`

**Interfaces:**
- Consumes: `READ_CASES` (`cases.py:243`) — tuple `(câu hỏi, tool kỳ vọng, args chốt, entity_keys)`.
- Produces: không có API mới.

**Bối cảnh:** cổng `read` đang **1.000 trên n=20** — kín trần, một câu chọn nhầm là rơi 0.95. Thêm tool vào prompt tạo rủi ro **hai chiều**, và bộ eval phải đo cả hai, nếu không hành vi mới là hành vi không được đo.

- [ ] **Step 1: Thêm ca**

Trong `backend/evals/cases.py`, thêm vào cuối `READ_CASES`:

```python
    # ── Bản tin việc cần xử lý (2026-08-15) ─────────────────────────────────
    # Nhóm A — câu buổi sáng phải đi tới tool tổng hợp. Đo trước khi có tool
    # này: 3/3 vai trả lời "không có việc nào được giao" trong khi hệ thống
    # có 29 phiếu trễ và 22 hóa đơn quá hạn.
    ("hôm nay tôi cần xử lý gì?", "list_pending_work", {}, ()),
    ("có việc gì cần làm không?", "list_pending_work", {}, ()),
    ("còn gì nữa không?", "list_pending_work", {}, ()),
    # Nhóm B — CHỐNG CƯỚP. Câu nêu rõ MỘT loại chứng từ phải đi thẳng tool
    # của loại đó, không bị hút về tool tổng hợp. Thiếu nhóm này thì tool mới
    # có thể nuốt hết mà điểm vẫn đẹp.
    ("có phiếu giao nào trễ hạn không?", "list_late_deliveries", {}, ()),
    ("liệt kê hóa đơn quá hạn", "get_overdue_invoices", {}, ()),
    ("hàng nào cần đặt bổ sung?", "list_reorder_needed", {}, ()),
```

- [ ] **Step 2: Chạy cổng eval `read`**

⚠️ Bộ eval gọi **API LLM thật** — đây là bước DUY NHẤT trong plan được phép, và nó KHÔNG chạy qua `pytest`.

Run: `cd backend && ./.venv/Scripts/python.exe -m evals.run_eval --set read`
Expected: `tool_acc` phải **≥ 1.000 trên n=26**. Bất kỳ ca nào trong 20 ca CŨ chọn nhầm sang `list_pending_work` là **thụt** — dừng và báo cáo, đừng chỉnh ca eval cho vừa.

- [ ] **Step 3: Ghi baseline mới**

Run: `cd backend && ./.venv/Scripts/python.exe -m evals.run_eval --set read --save-baseline`
Expected: `backend/evals/baseline-qwen3-8b-read.json` có `n: 26`.

- [ ] **Step 4: Commit**

```bash
git add backend/evals/cases.py backend/evals/baseline-qwen3-8b-read.json
git commit -m "test(evals): ca cho bản tin việc + ca chống cướp

Cổng read đang 1.000 kín trần nên thêm tool vào prompt là rủi ro hai
chiều: câu cũ chọn nhầm sang tool mới (thụt), hoặc tool mới nuốt câu nêu
rõ loại chứng từ (cướp). Đo cả hai."
```

---

## Nghiệm thu sống — TRƯỚC khi merge

⚠️ **Controller làm, không phải subagent.** Mọi thao tác khởi động/dừng tiến trình sống thuộc về controller.

Phép đo hôm nay chạy **đúng một lần** mỗi vai — nó chứng minh hành vi *có thể* xảy ra, không chứng minh nó *ổn định*. Với LLM, 1/1 và 3/5 nhìn giống hệt nhau nếu chỉ chạy một lần; mà 3/5 nghĩa là hai buổi sáng mỗi tuần người dùng bị báo "không có việc" trong khi có 29 phiếu trễ.

1. Khởi động lại backend + 3 tiến trình MCP từ worktree của nhánh.
2. Gửi "Hôm nay tôi cần xử lý gì?" qua `POST /v1/chat/completions` với header `x-openwebui-user-id` của **từng vai**, **5 lượt mỗi vai** = 15 lượt.
3. Ghi: mỗi lượt có gọi `list_pending_work` không, và câu trả lời có số không.
4. Hỏi tiếp "còn gì nữa không?" ít nhất một lượt — phải nêu được tầng 2, không được bịa.

**Điều kiện đạt:** ≥ 14/15 lượt định tuyến đúng.

**Điều kiện TRƯỢT CỨNG, quan trọng hơn tỉ lệ:** bất kỳ lượt nào trả lời "không có việc" trong khi hàng đợi không rỗng đều là **trượt**, kể cả khi 14 lượt kia đúng — vì đó là tác hại cụ thể đang đi diệt, không phải một con số thống kê.

---

## Ngoài phạm vi — đừng làm

- **Không** xây năng lực "tự đi tìm việc" mở ngoài tầng 1 + tầng 2. Giới hạn đó được **nói ra** ở `display`, không được che.
- **Không** đổi kiến trúc đọc: `read_tools` vẫn là "tất cả" cho mọi vai (ADR-012 §7.2). Bản tin chỉ **xếp thứ tự**, không lọc theo vai.
- **Không** đụng prompt router, planner, hay SOP skill nào.
- **Không** gieo thêm dữ liệu demo để bản tin trông đẹp hơn — đó là chế tạo bằng chứng cho chính tính năng (lý do đã ghi 2026-08-12).
- **Không** sửa `list_my_activities` để nó trả nhiều hơn. Nó trả 0 cho mọi vai AI vì activity được giao cho người thật; đó là sự thật, và bản tin phải trung thực về nó chứ không che.
