# RBAC tầng RAG (19b) — kế hoạch thi hành

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vai `warehouse` không còn đọc được 4 tài liệu thương mại qua RAG; `accounting`/`sales`/`admin` vẫn đọc được; chứng minh bằng cổng dương + cổng âm tất định trên bộ `retrieval` và probe sống 4 vai.

**Architecture:** Nhãn là *lớp* (`'all'` | `'commercial'`) ghi vào cột `rag_chunks.visibility` có sẵn; vai→lớp khai trong `RoleCfg.rag_visibility`; `retrieve()` lọc `AND c.visibility = ANY(%s)` trước `LIMIT` trên **cả ba** chân dense/sparse/fold và **fail-closed** (`None`/rỗng → `{'all'}`, chỉ sentinel `UNRESTRICTED` mới mở). Hai node production truyền `role_cfg` xuống; ba bộ eval gọi `retrieve()` thật nhận `--role`. Migration 009 backfill 24 chunk thương mại và **gỡ 660 chunk SID**.

**Tech Stack:** Python 3.11, psycopg 3 + pgvector, FastMCP/LangGraph (không đụng), pytest (marker `integration`/`live`), PostgreSQL 16 trong container `youdoo-postgres` (port 5434).

**Spec:** `docs/superpowers/specs/2026-09-20-rbac-tang-rag-design.md` — plan lập luận từ spec; người thi hành đọc cả hai.

## Global Constraints

- **Lệnh test unit** luôn là `pytest -m "not integration and not live"` — lệnh trần chạy cả live/integration (`backend/pytest.ini` chỉ *đăng ký* marker, không tự loại). Test `integration` cần Postgres 5434; chạy riêng, **không** song song với suite khác (schema `rag_test` là tài nguyên dùng chung).
- **Worktree** (tạo bằng `superpowers:using-git-worktrees` lúc thi hành) **không có** `.env` lẫn `.venv`. Bắt buộc trước khi chạy gì: (1) junction `backend/.venv` → `D:\Youdoo\backend\.venv` bằng PowerShell `New-Item -ItemType Junction -Path backend\.venv -Target D:\Youdoo\backend\.venv`; (2) test cần `ODOO_URL/ODOO_DB/ODOO_USERNAME/ODOO_PASSWORD` chỉ để *import* registry tool — nạp qua launcher Python đọc `D:\Youdoo\.env`, **không** `eval` trong Bash (harness chặn). Trước `git worktree remove` phải xoá junction bằng `(Get-Item -Force <path>).Delete()` — xoá đệ quy đi xuyên junction và xoá venv thật.
- **Mọi identifier trong code là tiếng Anh** (`feedback_plan_code_identifier_language`); prose/docstring/comment tiếng Việt như repo.
- **Cwd khi chạy test/eval**: `backend/` (import `src`, `evals`, `jobs` theo rootdir).
- **Không chuỗi cổng với hành động** (`feedback_never_chain_gate_with_action`): migration 009 trên DB thật là thao tác **phá huỷ** — chạy riêng, sau khi chủ dự án gật, không nối `&&` với eval.
- Mỗi task: test đỏ → code tối thiểu → xanh → commit. Commit subject không dấu (lệ repo), thân có dấu; kết bằng `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Bản đồ tệp

| Tệp | Vai trò | Task |
|---|---|---|
| `backend/src/rag/visibility.py` | **mới** — vốn từ lớp, `DOC_VISIBILITY`, `UNRESTRICTED`, `resolve()`, `class_for()` | 1 |
| `backend/src/agents/roles.py` | `RoleCfg.rag_visibility` + 4 hồ sơ × 2 profile + `rag_visibility_of()` | 2 |
| `backend/src/rag/retrieve.py` | `retrieve(..., visibility=None)`, 3 chân nhận `visibility`, `_vis_clause()` | 3 |
| `backend/tests/rag/test_retrieve_visibility.py` | unit (conn giả, hình dạng SQL) + integration (schema `rag_test`) | 3, 4 |
| `backend/src/rag/ingest.py` | INSERT ghi `visibility = class_for(...)` | 5 |
| `backend/src/agents/nodes.py`, `fanout.py`, `graph.py` | truyền `role_cfg` → `visibility` vào 2 node | 6 |
| `backend/evals/role_config.py`, `run_eval.py`, `jobs/eval_gate.py` | `--role` → visibility cho 3 bộ; `role` trong JSON; hậu tố baseline; parity `role` ở `_gate` | 7 |
| `backend/evals/compare_visibility.py` | **mới** — cổng ÂM: so hai lượt retrieval | 8 |
| `backend/migrations/009_rag_visibility_backfill.sql`, `docs/getting-started.md` | backfill + gỡ SID; hợp đồng SQL↔`DOC_VISIBILITY` | 9 |
| `backend/tests/live_verify_rbac_rag.py` | probe sống 4 vai | 10 |

---

### Task 1: `src/rag/visibility.py` — vốn từ lớp, sentinel, `resolve()`, `class_for()`

**Files:**
- Create: `backend/src/rag/visibility.py`
- Test: `backend/tests/rag/test_visibility.py`

**Interfaces:**
- Produces: `VISIBILITY_CLASSES: frozenset[str]`, `DEFAULT_VISIBILITY: frozenset[str]`, `DOC_VISIBILITY: dict[str, str]`, `UNRESTRICTED` (singleton `_Unrestricted`), `basename(source_file: str) -> str`, `class_for(source_file: str) -> str`, `resolve(visibility) -> frozenset[str] | _Unrestricted`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/rag/test_visibility.py
"""Vốn từ lớp hiển thị + fail-closed của resolve() (spec 2026-09-20 §3)."""
import pytest

from src.rag import visibility as vis


def test_class_for_tach_ca_hai_dau_phan_cach():
    """rag_documents.source_file đang lưu 'src/rag/seed\\bang_gia.xlsx' (lẫn '/'
    và '\\'); os.path.basename trên Linux (CI) trả 'seed\\bang_gia.xlsx' → nhãn
    'all' lặng lẽ. Cả bốn kiểu đường dẫn phải ra cùng lớp."""
    for path in ("bang_gia.xlsx", "src/rag/seed/bang_gia.xlsx",
                 "src/rag/seed\\bang_gia.xlsx", "D:\\Youdoo\\backend\\src\\rag\\seed\\bang_gia.xlsx"):
        assert vis.class_for(path) == "commercial", path


def test_class_for_bon_tep_thuong_mai_va_tep_la():
    assert {vis.class_for(f) for f in ("discount_policy.docx", "bang_gia.xlsx",
                                       "payment_policy.docx", "sla.docx")} == {"commercial"}
    assert vis.class_for("policy.docx") == "all"
    assert vis.class_for("seed/law/luat-dautu.pdf") == "all"
    assert vis.class_for("khong_ton_tai.txt") == "all"


def test_moi_gia_tri_DOC_VISIBILITY_nam_trong_von_tu():
    assert set(vis.DOC_VISIBILITY.values()) <= vis.VISIBILITY_CLASSES
    assert "all" in vis.VISIBILITY_CLASSES
    assert vis.DEFAULT_VISIBILITY == frozenset({"all"})


@pytest.mark.parametrize("value", [None, frozenset(), set(), [], ()])
def test_resolve_fail_closed_khi_thieu_hoac_rong(value):
    assert vis.resolve(value) == vis.DEFAULT_VISIBILITY


def test_resolve_chi_sentinel_that_moi_mo():
    assert vis.resolve(vis.UNRESTRICTED) is vis.UNRESTRICTED
    # Một _Unrestricted() KHÁC không phải sentinel — so bằng `is`, không phải kiểu
    khac = type(vis.UNRESTRICTED)()
    assert vis.resolve(khac) == vis.DEFAULT_VISIBILITY


def test_resolve_giu_tap_lop_da_cho():
    assert vis.resolve({"all", "commercial"}) == frozenset({"all", "commercial"})
    assert vis.resolve(["all"]) == frozenset({"all"})
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'src.rag.visibility'`

- [ ] **Step 3: Viết module tối thiểu**

```python
# backend/src/rag/visibility.py
"""Lớp hiển thị của chunk RAG và cách vai mở/đóng lớp (spec 2026-09-20 §3).

Nhãn trong DB là LỚP ('all' | 'commercial'), không phải danh sách vai — thêm
vai mới là sửa code (RoleCfg), không backfill DB. Vai biết lớp, lớp không
biết vai: module này KHÔNG import src.agents.
"""
import re

VISIBILITY_CLASSES = frozenset({"all", "commercial"})
DEFAULT_VISIBILITY = frozenset({"all"})

# Khoá theo BASENAME — cùng cách retrieval_cases.py neo nhãn. Tệp không có ở
# đây → 'all'. Migration 009 lặp lại bốn tên này trong SQL; test hợp đồng
# (tests/rag/test_migration_009_contract.py) giữ hai nguồn không trôi.
DOC_VISIBILITY = {
    "discount_policy.docx": "commercial",
    "bang_gia.xlsx": "commercial",
    "payment_policy.docx": "commercial",
    "sla.docx": "commercial",
}


class _Unrestricted:
    """Sentinel 'không lọc'. KHÔNG phải None: None là 'mất vai' → fail-closed.
    Một caller lỡ viết `visibility=cfg.rag_visibility if cfg else None` phải
    rơi về THẤY ÍT NHẤT — đúng chiều ngược với lỗ mục 17b."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNRESTRICTED"


UNRESTRICTED = _Unrestricted()

_SEP = re.compile(r"[\\/]")


def basename(source_file: str) -> str:
    """Tách trên CẢ '/' lẫn '\\' — source_file trong DB lẫn hai dấu, và
    os.path.basename trên Linux không hiểu '\\'."""
    return _SEP.split(source_file)[-1]


def class_for(source_file: str) -> str:
    return DOC_VISIBILITY.get(basename(source_file), "all")


def resolve(visibility) -> frozenset | _Unrestricted:
    """None/rỗng → DEFAULT_VISIBILITY. Chỉ đúng đối tượng UNRESTRICTED mới mở."""
    if visibility is UNRESTRICTED:
        return UNRESTRICTED
    return frozenset(visibility) if visibility else DEFAULT_VISIBILITY
```

- [ ] **Step 4: Chạy lại, phải xanh**

Run: cùng lệnh Step 2. Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/visibility.py backend/tests/rag/test_visibility.py
git commit -m "feat(rag): visibility.py — lop hien thi, sentinel UNRESTRICTED, resolve() fail-closed (19b)"
```

---

### Task 2: `RoleCfg.rag_visibility` + `rag_visibility_of()`

**Files:**
- Modify: `backend/src/agents/roles.py:89-101` (dataclass) và `:199-235` (`PROFILES`)
- Test: `backend/tests/agents/test_rag_visibility_roles.py`

**Interfaces:**
- Consumes: `UNRESTRICTED`, `DEFAULT_VISIBILITY` từ Task 1.
- Produces: trường `RoleCfg.rag_visibility` (mặc định `DEFAULT_VISIBILITY`); hàm module `rag_visibility_of(role_cfg) -> frozenset | _Unrestricted | None` (None khi `role_cfg is None` — để `retrieve()` tự fail-closed, không lặp luật ở caller).

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/agents/test_rag_visibility_roles.py
"""Vai nào thấy lớp nào (spec 2026-09-20 §2.1, §3) — cả hai profile."""
import pytest

from src.agents import roles
from src.rag.visibility import DEFAULT_VISIBILITY, UNRESTRICTED

SEES_COMMERCIAL = frozenset({"all", "commercial"})


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_bon_vai_dung_lop(profile):
    p = roles.PROFILES[profile]
    assert p["admin"].rag_visibility is UNRESTRICTED
    assert p["accounting"].rag_visibility == SEES_COMMERCIAL
    assert p["sales"].rag_visibility == SEES_COMMERCIAL
    assert p["warehouse"].rag_visibility == DEFAULT_VISIBILITY


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_unrestricted_keo_theo_khong_loc(profile):
    """Hai cờ cho admin phải nhất quán: unrestricted=True ⇒ không lọc RAG."""
    for cfg in roles.PROFILES[profile].values():
        if cfg.unrestricted:
            assert cfg.rag_visibility is UNRESTRICTED, cfg.name


def test_mac_dinh_thay_it_nhat():
    """Hồ sơ nào quên khai rag_visibility thì THẤY ÍT NHẤT, không phải tất cả."""
    cfg = roles.RoleCfg("x", "X", "http://localhost:1/sse")
    assert cfg.rag_visibility == DEFAULT_VISIBILITY


def test_rag_visibility_of_none_tra_none():
    """None để retrieve() tự fail-closed — không lặp lại luật ở caller."""
    assert roles.rag_visibility_of(None) is None
    admin = roles.PROFILES["small-business"]["admin"]
    assert roles.rag_visibility_of(admin) is UNRESTRICTED
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_visibility_roles.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `AttributeError: 'RoleCfg' object has no attribute 'rag_visibility'`

- [ ] **Step 3: Sửa `roles.py`**

Ở đầu file (cạnh các import hiện có) thêm:

```python
from src.rag.visibility import DEFAULT_VISIBILITY, UNRESTRICTED
```

Trong `RoleCfg` (sau dòng `unrestricted: bool = False        # chỉ vai admin`, `roles.py:101`) thêm trường:

```python
    # Lớp tài liệu RAG vai này được thấy (spec 2026-09-20 §3). Mặc định
    # THẤY ÍT NHẤT: hồ sơ quên khai thì không lộ tài liệu thương mại.
    rag_visibility: object = DEFAULT_VISIBILITY   # frozenset[str] | UNRESTRICTED
```

Trước `PROFILES = {` thêm:

```python
_SEES_COMMERCIAL = frozenset({"all", "commercial"})
```

Sửa cả hai profile — `small-business` (`roles.py:199-208`) và `enterprise` (`:216-235`):

```python
        "admin": RoleCfg("admin", "Quản trị", MCP_ADMIN, unrestricted=True,
                         rag_visibility=UNRESTRICTED),
        "warehouse": RoleCfg("warehouse", "Kho", MCP_WAREHOUSE,
                             own=_WH_OWN, needs_sign_off=_WH_SIGN_OFF),
        "accounting": RoleCfg("accounting", "Kế toán", MCP_ACCOUNTING,
                              own=_ACC_OWN, needs_sign_off=_ACC_SIGN_OFF,
                              rag_visibility=_SEES_COMMERCIAL),
        "sales": RoleCfg("sales", "Bán hàng", MCP_SALES,
                         own=_SALES_OWN, needs_sign_off=_SALES_SIGN_OFF,
                         rag_visibility=_SEES_COMMERCIAL),
```

(Ở `enterprise`, giữ nguyên `own`/`needs_sign_off`/`other_dept_extra` đang có của `warehouse`; chỉ thêm `rag_visibility=UNRESTRICTED` cho admin và `rag_visibility=_SEES_COMMERCIAL` cho accounting/sales. `warehouse` **không** truyền gì — mặc định là `{all}`.)

Cuối file thêm:

```python
def rag_visibility_of(role_cfg):
    """None khi không có vai — retrieve() tự fail-closed (spec §4), luật đó
    KHÔNG được lặp ở caller."""
    return None if role_cfg is None else role_cfg.rag_visibility
```

- [ ] **Step 4: Chạy lại, phải xanh — và toàn bộ test vai cũ không vỡ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_visibility_roles.py tests/agents/test_dept_of.py tests/agents/test_other_dept_derived.py tests/agents/test_erp_agent_roles.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/roles.py backend/tests/agents/test_rag_visibility_roles.py
git commit -m "feat(roles): RoleCfg.rag_visibility — admin UNRESTRICTED, accounting/sales thay commercial, kho chi 'all' (19b)"
```

---

### Task 3: `retrieve()` lọc trên ba chân, fail-closed — test hình dạng SQL (conn giả)

**Files:**
- Modify: `backend/src/rag/retrieve.py:5-11` (import), `:21-27` (`_dense`), `:54-59` (`_sparse`), `:117-121` (`_lexical_fold`), `:242-271` (`retrieve`)
- Test: `backend/tests/rag/test_retrieve_visibility.py` (phần unit)

**Interfaces:**
- Consumes: `UNRESTRICTED`, `resolve` từ Task 1.
- Produces: `retrieve(query, k=TOP_K, conn=None, aux_queries=(), *, visibility=None)`; ba chân `_dense(conn, qvec, visibility=UNRESTRICTED)`, `_sparse(conn, qseg, visibility=UNRESTRICTED)`, `_lexical_fold(conn, qseg_fold, visibility=UNRESTRICTED)`; `_vis_clause(visibility) -> tuple[str, tuple]`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/rag/test_retrieve_visibility.py
"""Lọc visibility ở ĐÚNG ba chân, trước LIMIT, và fail-closed (spec §4).

Phần unit: conn giả ghi lại SQL + tham số — kiểm HÌNH DẠNG câu lệnh, cùng
cách test_sparse_van_chet.py. Phần integration ở dưới (Task 4) chạy DB thật.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.visibility import UNRESTRICTED

VIS_CLAUSE = "c.visibility = ANY(%s)"


class _Cursor:
    def fetchall(self):
        return []


class _FakeConn:
    """Ghi lại mọi (sql, params); mọi chân trả rỗng nên rerank không chạy."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor()


@pytest.fixture
def khong_ra_ngoai(monkeypatch):
    """Chặn embed (Ollama) và giữ chân bỏ dấu BẬT để đủ ba chân chạy."""
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")


def _sql_cua_ba_chan(conn: _FakeConn) -> dict[str, tuple[str, tuple]]:
    """Nhận diện chân theo dấu hiệu riêng của từng câu SQL."""
    ra = {}
    for sql, params in conn.calls:
        if "<=>" in sql:
            ra["dense"] = (sql, params)
        elif "ts_vector_fold" in sql:
            ra["fold"] = (sql, params)
        elif "c.ts_vector @@" in sql:
            ra["sparse"] = (sql, params)
    return ra


def test_khong_truyen_thi_loc_all_tren_ca_ba_chan(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất giá trị gia tăng", conn=conn)
    chan = _sql_cua_ba_chan(conn)
    assert set(chan) == {"dense", "sparse", "fold"}, chan.keys()
    for ten, (sql, params) in chan.items():
        assert VIS_CLAUSE in sql, ten
        assert ["all"] in [list(p) for p in params if isinstance(p, (list, tuple))], (ten, params)
        # Lọc phải đứng TRƯỚC ORDER BY/LIMIT — lọc sau pool là rò qua total_candidates
        assert sql.index(VIS_CLAUSE) < sql.index("ORDER BY"), ten


def test_truyen_None_cung_fail_closed(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility=None)
    for ten, (sql, _p) in _sql_cua_ba_chan(conn).items():
        assert VIS_CLAUSE in sql, ten


def test_unrestricted_thi_sql_khong_co_visibility(khong_ra_ngoai):
    """Đường admin phải là ĐÚNG SQL trước 19b — để cổng dương so được với
    baseline cũ mà không có mệnh đề thừa."""
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility=UNRESTRICTED)
    chan = _sql_cua_ba_chan(conn)
    assert set(chan) == {"dense", "sparse", "fold"}
    for ten, (sql, _p) in chan.items():
        assert "visibility" not in sql, ten


def test_tap_lop_di_vao_tham_so_da_sap_xep(khong_ra_ngoai):
    conn = _FakeConn()
    rt.retrieve("thuế suất", conn=conn, visibility={"commercial", "all"})
    for ten, (sql, params) in _sql_cua_ba_chan(conn).items():
        assert ["all", "commercial"] in [list(p) for p in params
                                         if isinstance(p, (list, tuple))], (ten, params)


def test_aux_queries_cung_bi_loc(khong_ra_ngoai):
    """Lượt hỏi trước (aux) đi qua cùng ba hàm — không có cửa sau."""
    conn = _FakeConn()
    rt.retrieve("câu sau", conn=conn, aux_queries=("câu trước",))
    dense_calls = [sql for sql, _ in conn.calls if "<=>" in sql]
    assert len(dense_calls) == 2
    assert all(VIS_CLAUSE in s for s in dense_calls)
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `test_khong_truyen_thi_loc_all_tren_ca_ba_chan` FAIL vì `VIS_CLAUSE` không có trong SQL; `test_unrestricted_thi_sql_khong_co_visibility` FAIL với `TypeError: retrieve() got an unexpected keyword argument 'visibility'`.

- [ ] **Step 3: Sửa `retrieve.py`**

Import (`retrieve.py:5-11`), thêm:

```python
from .visibility import UNRESTRICTED, resolve
```

Sau `_FROM = ...` (`:18`) thêm:

```python
def _vis_clause(visibility) -> tuple[str, tuple]:
    """Mệnh đề lọc lớp + tham số đi kèm. ('', ()) khi UNRESTRICTED — SQL của
    đường admin bằng ĐÚNG SQL trước 19b. Lọc đứng trong WHERE, tức TRƯỚC
    ORDER BY/LIMIT: lọc sau pool vừa tốn chỗ trong TOP_N vừa rò qua
    total_candidates."""
    if visibility is UNRESTRICTED:
        return "", ()
    return " AND c.visibility = ANY(%s)", (sorted(visibility),)
```

Ba chân — thay nguyên thân:

```python
def _dense(conn, qvec, visibility=UNRESTRICTED) -> list[tuple]:
    clause, extra = _vis_clause(visibility)
    return conn.execute(
        f"SELECT {_COLS}, 1 - (c.embedding <=> %s::vector) AS score "
        f"FROM {_FROM} WHERE c.embedding IS NOT NULL{clause} "
        f"ORDER BY c.embedding <=> %s::vector LIMIT %s",
        (qvec, *extra, qvec, TOP_N),
    ).fetchall()
```

```python
def _sparse(conn, qseg, visibility=UNRESTRICTED) -> list[tuple]:
    """(giữ nguyên docstring hiện có)"""
    clause, extra = _vis_clause(visibility)
    return conn.execute(
        f"SELECT {_COLS}, ts_rank(c.ts_vector, plainto_tsquery('simple', %s)) AS score "
        f"FROM {_FROM} WHERE c.ts_vector @@ plainto_tsquery('simple', %s){clause} "
        f"ORDER BY score DESC LIMIT %s",
        (qseg, qseg, *extra, TOP_N),
    ).fetchall()
```

```python
def _lexical_fold(conn, qseg_fold: str, visibility=UNRESTRICTED) -> list[tuple]:
    """(giữ nguyên docstring hiện có)"""
    tq = _or_tsquery(qseg_fold)
    if not tq:
        return []
    clause, extra = _vis_clause(visibility)
    cur = conn.execute(
        f"SELECT {_COLS}, ts_rank(c.ts_vector_fold, to_tsquery('simple', %s)) AS score "
        f"FROM {_FROM} WHERE c.ts_vector_fold @@ to_tsquery('simple', %s){clause} "
        f"ORDER BY score DESC LIMIT {TOP_N}", (tq, tq, *extra))
    return cur.fetchall()
```

Thứ tự tham số là điểm dễ sai: `%s` của mệnh đề lọc nằm **sau** các `%s` của SELECT/WHERE và **trước** `%s` của ORDER BY/LIMIT — đúng như ba tuple trên. Mặc định `UNRESTRICTED` trên chân **riêng tư** để `test_sparse_van_chet.py` (gọi `rt._sparse(conn, ...)` trực tiếp) không đổi; hợp đồng fail-closed nằm ở `retrieve()`.

`retrieve()` (`:242-271`):

```python
def retrieve(query: str, k: int = TOP_K, conn=None,
             aux_queries: tuple[str, ...] = (), *, visibility=None) -> RetrievalResult:
    # Fail-closed TẠI ĐÂY (spec §4): không truyền / None / rỗng → {'all'}.
    # Chỉ đúng đối tượng UNRESTRICTED mới bỏ lọc. Mục 17b từng lộ đường mất
    # vai — "quên truyền" phải là THẤY ÍT NHẤT.
    visibility = resolve(visibility)
    own = conn is None
    if own:
        conn = _db.connect()
        _db.ensure_schema(conn, RAG_SCHEMA)
    try:
        qvec = embed_query(query)
        qseg = segment_vi(query)
        dense, sparse = _dense(conn, qvec, visibility), _sparse(conn, qseg, visibility)
        fused = _rrf(dense, sparse)
        fold_gop = False
        if fold_enabled():
            hang_fold = _lexical_fold(conn, fold_vi(query), visibility)
            fold_gop = bool(hang_fold)
            fused = _rrf_fold(hang_fold, fused)
        for aux in aux_queries:
            if aux == query:
                continue
            aux_dense = _dense(conn, embed_query(aux), visibility)
            aux_sparse = _sparse(conn, segment_vi(aux), visibility)
            fused = _rrf(aux_dense, aux_sparse, acc=fused)
            if fold_enabled():
                hang_fold = _lexical_fold(conn, fold_vi(aux), visibility)
                fold_gop = fold_gop or bool(hang_fold)
                fused = _rrf_fold(hang_fold, fused)
        # ... phần còn lại giữ nguyên (ordered / pool / rerank / compress / return)
```

Giữ nguyên các comment giải thích đang có trong thân hàm (chân bỏ dấu, aux) — chỉ thêm tham số `visibility` vào 6 lời gọi chân và dòng `resolve` đầu hàm.

- [ ] **Step 4: Chạy lại, phải xanh — kèm các test retrieve cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_visibility.py tests/rag/test_sparse_van_chet.py tests/rag/test_fold_vi.py tests/rag/test_rerank_mode.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed` (test integration trong `test_sparse_van_chet.py` bị deselect).

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/retrieve.py backend/tests/rag/test_retrieve_visibility.py
git commit -m "feat(rag): retrieve() loc visibility tren ca 3 chan, fail-closed ve {'all'} (19b)"
```

---

### Task 4: Integration — DB thật, hai tài liệu, ba chân

**Files:**
- Modify: `backend/tests/rag/test_retrieve_visibility.py` (thêm phần integration ở cuối)

**Interfaces:**
- Consumes: fixture `rag_conn` / `clean_tables` (`tests/rag/conftest.py`, schema `rag_test`); `rt._dense/_sparse/_lexical_fold/retrieve` từ Task 3.

- [ ] **Step 1: Viết test đỏ (đỏ vì chưa có INSERT `visibility` — Task 5 chưa tồn tại không liên quan: test này INSERT trực tiếp)**

Thêm vào cuối `test_retrieve_visibility.py`:

```python
# ─── Integration: DB thật ──────────────────────────────────────────────────

from src.rag.chunking import fold_vi
from src.rag.ingest import segment_vi

_DIM = 1024


def _vec(hot: int) -> str:
    """Vector đơn vị trục `hot`, dạng chuỗi cho %s::vector."""
    v = ["0"] * _DIM
    v[hot] = "1"
    return "[" + ",".join(v) + "]"


def _nap_hai_tai_lieu(conn):
    """1 chunk 'commercial' (trục 0) + 1 chunk 'all' (trục 1); cùng từ khoá
    'chiết khấu' để chân sparse và chân bỏ dấu đều có ứng viên."""
    rows = [("d-tm", "seed\\discount_policy.docx", "commercial", 0,
             "Chính sách chiết khấu: bậc 5%, cộng 2%, trần 15%."),
            ("d-all", "seed/policy.docx", "all", 1,
             "Chính sách hoàn hàng và chiết khấu chung trong 30 ngày.")]
    for doc_id, src, vis, hot, text in rows:
        conn.execute("INSERT INTO rag_documents (doc_id, source_file, content_hash) "
                     "VALUES (%s, %s, %s)", (doc_id, src, doc_id))
        conn.execute(
            "INSERT INTO rag_chunks (doc_id, source_file, chunk_text, visibility, "
            "embedding, ts_vector, chunk_text_fold) "
            "VALUES (%s, %s, %s, %s, %s::vector, to_tsvector('simple', %s), %s)",
            (doc_id, src, text, vis, _vec(hot), segment_vi(text), fold_vi(text)))


@pytest.mark.integration
def test_ba_chan_tren_db_that_khong_lo_commercial_cho_all(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    # Truy vấn "nhìn" giống chunk commercial nhất: trục 0 → dense xếp nó đầu
    monkeypatch.setattr(rt, "embed_query", lambda q: [1.0] + [0.0] * (_DIM - 1))
    q = "chiết khấu"
    chi_all = frozenset({"all"})

    dense = rt._dense(conn, [1.0] + [0.0] * (_DIM - 1), chi_all)
    sparse = rt._sparse(conn, segment_vi(q), chi_all)
    fold = rt._lexical_fold(conn, fold_vi(q), chi_all)
    for ten, rows in (("dense", dense), ("sparse", sparse), ("fold", fold)):
        assert rows, f"chân {ten} không có ứng viên — fixture sai, test tự vô hiệu"
        # cột 2 = source_file (xem _COLS)
        assert all("policy.docx" in r[2] and "discount" not in r[2] for r in rows), (ten, rows)

    ket_qua = rt.retrieve(q, conn=conn, visibility=chi_all)
    assert {c.source_file for c in ket_qua.chunks} == {"seed/policy.docx"}


@pytest.mark.integration
def test_unrestricted_thay_ca_hai(clean_tables, monkeypatch):
    """Khẳng định TẬP, không khẳng định thứ tự: hai chunk hoà điểm ts_rank ở
    chân sparse/fold, RRF có thể xếp 'all' trước — thứ tự không phải điều
    test này đo."""
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: [1.0] + [0.0] * (_DIM - 1))
    ket_qua = rt.retrieve("chiết khấu", conn=conn, visibility=UNRESTRICTED)
    assert {c.source_file for c in ket_qua.chunks} == {"seed\\discount_policy.docx",
                                                        "seed/policy.docx"}
```

- [ ] **Step 2: Chạy integration (cần Postgres 5434, KHÔNG chạy song song suite khác)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_visibility.py -m integration -q -p no:cacheprovider`
Expected: `2 passed`. (Nếu `Postgres unreachable` → fixture skip: bật container `youdoo-postgres` rồi chạy lại. Đây là test xác nhận Task 3 trên DB thật; nếu đỏ, sửa Task 3, không sửa test.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/rag/test_retrieve_visibility.py
git commit -m "test(rag): integration — loc visibility tren DB that, ca ba chan (19b)"
```

---

### Task 5: Ingest ghi `visibility`

**Files:**
- Modify: `backend/src/rag/ingest.py:182-207`
- Test: `backend/tests/rag/test_ingest_visibility.py`

**Interfaces:**
- Consumes: `class_for` từ Task 1.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/rag/test_ingest_visibility.py
"""Ingest phải ghi lớp visibility từ DOC_VISIBILITY — lần nạp seed/ sau không
reset về 'all'. Không cần Postgres: conn giả ghi lại INSERT."""
import contextlib
import re

import pytest

from src.rag import ingest as _ing


class _RecConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return None            # chưa từng nạp → đi đường INSERT

    def transaction(self):
        return contextlib.nullcontext()


class _FakeEmbedder:
    model_name = "gia-lap"
    dim = 2


@pytest.fixture
def _khong_ra_ngoai(monkeypatch):
    monkeypatch.setattr(_ing, "get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(_ing, "embed_texts", lambda texts: [[0.0, 0.0] for _ in texts])
    monkeypatch.setattr(_ing._db, "ensure_schema", lambda *a, **k: None)


def _docx(path, than="Chiết khấu bậc 5%."):
    from docx import Document
    d = Document()
    d.add_heading("Điều 1", level=1)
    d.add_paragraph(than)
    d.save(str(path))
    return path


def _visibility_da_ghi(conn: _RecConn) -> set[str]:
    """Đọc giá trị visibility từ INSERT rag_chunks theo VỊ TRÍ cột trong SQL —
    không đoán chỉ số cứng."""
    ra = set()
    for sql, params in conn.calls:
        if not sql.lstrip().startswith("INSERT INTO rag_chunks"):
            continue
        cols = re.search(r"INSERT INTO rag_chunks \((.*?)\)", sql, re.S).group(1)
        names = [c.strip() for c in cols.split(",")]
        assert "visibility" in names, sql
        ra.add(params[names.index("visibility")])
    assert ra, "không có INSERT rag_chunks nào — test tự vô hiệu"
    return ra


@pytest.mark.parametrize("ten,lop", [("discount_policy.docx", "commercial"),
                                     ("policy.docx", "all")])
def test_ingest_ghi_dung_lop(_khong_ra_ngoai, tmp_path, ten, lop):
    conn = _RecConn()
    _ing._ingest_file(str(_docx(tmp_path / ten)), conn)
    assert _visibility_da_ghi(conn) == {lop}
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_ingest_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `AssertionError` tại `assert "visibility" in names` (INSERT chưa có cột).

- [ ] **Step 3: Sửa INSERT trong `_ingest_file` (`ingest.py:183-207`)**

Thêm import ở đầu `ingest.py`: `from .visibility import class_for`.

Thay câu INSERT:

```python
            conn.execute(
                "INSERT INTO rag_chunks (doc_id, source_file, doc_title, section_path, page, "
                "sheet, row_range, columns, chunk_index, token_count, chunk_text, "
                "source_kind, ocr_conf, embedding, visibility, "
                # `chunk_text_fold` đi qua ĐÚNG pipeline của `ts_vector`
                # (index_text + segment_vi) rồi mới bỏ dấu, để hai chân
                # nhìn cùng một chuỗi. `ts_vector_fold` là cột GENERATED
                # nên KHÔNG liệt kê ở đây — Postgres tự dựng.
                "ts_vector, chunk_text_fold) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, "
                "to_tsvector('simple', %s), %s)",
                (c["doc_id"], c["source_file"], c["doc_title"], c["section_path"], c["page"],
                 c["sheet"], c["row_range"], c["columns"], c["chunk_index"], c["token_count"],
                 c["chunk_text"],
                 c.get("source_kind", "text"), c.get("ocr_conf"),
                 vec,
                 # Lớp hiển thị từ basename (spec 2026-09-20 §6) — lần nạp
                 # seed/ sau tự đúng, không reset về 'all'. Re-ingest là NO-OP
                 # khi content_hash không đổi, nên corpus đang có PHẢI backfill
                 # bằng migration 009, không thể "nạp lại cho nó tự đúng".
                 class_for(c["source_file"]),
                 segment_vi(index_text(c["section_path"], c["chunk_text"])),
                 fold_vi(index_text(c["section_path"], c["chunk_text"]))),
            )
```

(Giữ nguyên hai comment cũ về `.get()` và về `fold_vi`; chỉ chèn cột + giá trị `visibility` và comment mới. Đếm lại: 15 `%s` trong VALUES + `to_tsvector(%s)` + `%s` = 17 tham số.)

- [ ] **Step 4: Chạy lại, phải xanh — kèm test ingest cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_ingest_visibility.py tests/rag/test_ingest.py tests/rag/test_ingest_run.py tests/rag/test_ingest_guard.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/ingest.py backend/tests/rag/test_ingest_visibility.py
git commit -m "feat(rag): ingest ghi visibility tu DOC_VISIBILITY theo basename (19b)"
```

---

### Task 6: Hai node production truyền vai xuống `retrieve()`

**Files:**
- Modify: `backend/src/agents/nodes.py:91-135` (`make_rag_node`), `backend/src/agents/fanout.py:83-114` (`make_gather_docs_node`), `backend/src/agents/graph.py:76,82`
- Test: `backend/tests/agents/test_rag_visibility_nodes.py`

**Interfaces:**
- Consumes: `rag_visibility_of` (Task 2), `retrieve(..., visibility=)` (Task 3).
- Produces: `make_rag_node(llm, role_cfg=None)`, `make_gather_docs_node(role_cfg=None)`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/agents/test_rag_visibility_nodes.py
"""Hai node gọi retrieve() phải truyền visibility của VAI; không vai → None
(retrieve tự fail-closed). Không LLM thật, không DB: patch retrieve, bắt kwargs."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, roles
import src.agents.nodes as nodes_mod
from src.rag.types import RetrievalResult
from src.rag.visibility import UNRESTRICTED

SEES_COMMERCIAL = frozenset({"all", "commercial"})


class _NoopLLM:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="KHÔNG_ĐỦ_THÔNG_TIN")


def _rong(query="q", **_):
    return RetrievalResult(query=query, query_used=query, chunks=[],
                           top_score=0.0, total_candidates=0)


def _state(text):
    return {"messages": [HumanMessage(content=text)]}


def _bat(monkeypatch, module):
    got = {}

    def fake_retrieve(query, *a, **kw):
        got["visibility"] = kw.get("visibility", "KHONG_TRUYEN")
        return _rong(query)
    monkeypatch.setattr(module, "retrieve", fake_retrieve)
    return got


@pytest.mark.parametrize("vai,muon", [
    ("admin", UNRESTRICTED), ("accounting", SEES_COMMERCIAL),
    ("sales", SEES_COMMERCIAL), ("warehouse", frozenset({"all"}))])
async def test_rag_node_truyen_visibility_cua_vai(monkeypatch, vai, muon):
    got = _bat(monkeypatch, nodes_mod)
    cfg = roles.PROFILES["small-business"][vai]
    await nodes_mod.make_rag_node(_NoopLLM(), role_cfg=cfg)(_state("chiết khấu?"))
    assert got["visibility"] is muon if muon is UNRESTRICTED else got["visibility"] == muon


async def test_rag_node_khong_vai_truyen_None(monkeypatch):
    got = _bat(monkeypatch, nodes_mod)
    await nodes_mod.make_rag_node(_NoopLLM())(_state("chiết khấu?"))
    assert got["visibility"] is None


@pytest.mark.parametrize("vai,muon", [
    ("admin", UNRESTRICTED), ("warehouse", frozenset({"all"}))])
async def test_gather_docs_truyen_visibility_cua_vai(monkeypatch, vai, muon):
    got = _bat(monkeypatch, fanout)
    cfg = roles.PROFILES["small-business"][vai]
    await fanout.make_gather_docs_node(role_cfg=cfg)(_state("chiết khấu?"))
    assert got["visibility"] is muon if muon is UNRESTRICTED else got["visibility"] == muon


async def test_gather_docs_khong_vai_truyen_None(monkeypatch):
    got = _bat(monkeypatch, fanout)
    await fanout.make_gather_docs_node()(_state("chiết khấu?"))
    assert got["visibility"] is None
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_visibility_nodes.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `TypeError: make_rag_node() got an unexpected keyword argument 'role_cfg'` và tương tự cho `make_gather_docs_node`.

- [ ] **Step 3: Sửa ba tệp**

`nodes.py` — import cạnh các import `roles` hiện có (nếu chưa import `roles`, thêm `from .roles import rag_visibility_of`); sửa chữ ký và lời gọi:

```python
def make_rag_node(llm, role_cfg=None):
    """Document Q&A: retrieve (sync, off the loop) → grounded synthesis + citations.

    retrieve() is sync psycopg; asyncio.to_thread keeps the event loop free.
    Any failure degrades to SAFE_MSG — the graph never crashes.

    role_cfg → visibility (spec 2026-09-20 §5). None → retrieve() tự fail-closed
    về {'all'}: test cũ gọi build_graph() không truyền vai vẫn chạy, chỉ không
    thấy 4 tài liệu thương mại — hồi quy ĐÚNG, lộ chỗ ngầm chạy như admin.
    """
    visibility = rag_visibility_of(role_cfg)

    async def rag_node(state: ERPAgentState) -> dict:
        ...
            result = await asyncio.to_thread(
                retrieve, query, TOP_K, None, (prev,) if prev else (),
                visibility=visibility)
        ...
```

(Giữ nguyên toàn bộ comment dài về aux_queries/ký ức trong thân hàm.)

`fanout.py`:

```python
from .roles import rag_visibility_of   # cạnh các import hiện có

def make_gather_docs_node(role_cfg=None):
    """(giữ docstring hiện có, thêm một dòng:)
    role_cfg → visibility như rag_node (spec 2026-09-20 §5); None → fail-closed.
    """
    visibility = rag_visibility_of(role_cfg)

    async def gather_docs(state: ERPAgentState) -> dict:
        ...
            result = await asyncio.to_thread(
                retrieve, query, TOP_K, None, (prev,) if prev else (),
                visibility=visibility)
        ...
```

`graph.py:76` và `:82`:

```python
    g.add_node("rag", make_rag_node(llms["synthesis"], role_cfg=role_cfg))
    ...
    g.add_node("gather_docs", make_gather_docs_node(role_cfg=role_cfg))
```

- [ ] **Step 4: Chạy lại, phải xanh — kèm test node/graph cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_visibility_nodes.py tests/agents/test_fanout.py tests/agents/test_memory_injection.py tests/agents/test_erp_agent_roles.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/nodes.py backend/src/agents/fanout.py backend/src/agents/graph.py backend/tests/agents/test_rag_visibility_nodes.py
git commit -m "feat(agents): rag_node + gather_docs truyen visibility cua vai xuong retrieve() (19b)"
```

---

### Task 7: Eval nhận `--role` → visibility; JSON mang `role`; baseline có hậu tố vai; `_gate` kiểm parity `role`

**Files:**
- Modify: `backend/evals/role_config.py:32` (thêm tập + hàm), `backend/evals/run_eval.py:87-118` (`baseline_path`), `:1093-1184` (`eval_retrieval`), `:1187-1215` (`eval_synthesis_live`), `:1275-1290` (`eval_multiturn`), `:1466-1487` (`main`), `backend/jobs/eval_gate.py` (nhánh `retrieval`)
- Test: `backend/tests/jobs/test_retrieval_gate.py` (sửa BASE + thêm ca), `backend/tests/jobs/test_run_eval_visibility.py` (mới)

**Interfaces:**
- Consumes: `rag_visibility_of`, `role_cfg()` của `role_config`.
- Produces: `role_config.VISIBILITY_SENSITIVE_SETS = frozenset({"retrieval","synthesis_live","multiturn"})`, `role_config.visibility_for(role_name) -> frozenset | UNRESTRICTED`; `eval_retrieval(..., visibility=UNRESTRICTED, role="admin")` trả thêm khoá `"role"`; `eval_synthesis_live(..., visibility=UNRESTRICTED)`, `eval_multiturn(..., visibility=UNRESTRICTED)`.

- [ ] **Step 1: Viết test đỏ**

Sửa `tests/jobs/test_retrieval_gate.py`: trong `BASE` thêm `"role": "admin"`, và thêm ca parity:

```python
BASE = {"dang_go": "co_dau", "rerank": True, "role": "admin", "n": N,
        "recall_at_20": 0.9771, "recall_at_6": 0.9633, "mrr": 0.8058}
```

```python
def test_gate_tu_choi_baseline_khac_vai():
    """Lượt --role warehouse so với baseline admin: FAIL là ĐÚNG về mặt số,
    nhưng đó là dùng sai cổng — cổng âm có công cụ riêng (compare_visibility)."""
    with pytest.raises(ValueError, match="role"):
        _gate("retrieval", _ket_qua(role="warehouse"), BASE)


def test_gate_baseline_cu_khong_co_role_hieu_la_admin():
    """baseline-bge-m3-retrieval.json ghi trước 19b không có khoá role."""
    base_cu = {k: v for k, v in BASE.items() if k != "role"}
    assert _gate("retrieval", _ket_qua(), base_cu) is True
```

Tạo `tests/jobs/test_run_eval_visibility.py`:

```python
# backend/tests/jobs/test_run_eval_visibility.py
"""--role đi tới visibility của ba bộ gọi retrieve() thật; baseline có hậu tố
vai để --role warehouse --save-baseline KHÔNG đè baseline admin."""
import pytest

from evals import role_config, run_eval
from src.rag.visibility import UNRESTRICTED


def test_ba_bo_nhay_visibility_khai_tuong_minh():
    assert role_config.VISIBILITY_SENSITIVE_SETS == frozenset(
        {"retrieval", "synthesis_live", "multiturn"})
    # KHÔNG trộn với ROLE_SENSITIVE_SETS — cái đó là về PROMPT
    assert not (role_config.VISIBILITY_SENSITIVE_SETS & role_config.ROLE_SENSITIVE_SETS)


def test_visibility_for_theo_vai():
    assert role_config.visibility_for("admin") is UNRESTRICTED
    assert role_config.visibility_for("warehouse") == frozenset({"all"})
    assert role_config.visibility_for("sales") == frozenset({"all", "commercial"})


def test_baseline_path_retrieval_co_hau_to_vai_non_admin():
    assert run_eval.baseline_path("bge-m3", "retrieval", "admin").endswith(
        "baseline-bge-m3-retrieval.json")
    assert run_eval.baseline_path("bge-m3", "retrieval", "warehouse").endswith(
        "baseline-bge-m3-retrieval-warehouse.json")
    # bộ KHÔNG nhạy vai vẫn chuẩn hoá về admin như cũ
    assert run_eval.baseline_path("m", "confirm", "warehouse").endswith(
        "baseline-m-confirm.json")


@pytest.mark.asyncio
async def test_main_truyen_visibility_va_role_vao_eval_retrieval(monkeypatch):
    thay = {}

    async def gia(pace=0.0, checkpoint_path=None, **kw):
        thay.update(kw)
        return {"set": "retrieval", "n": 1, "rerank": True, "dang_go": "co_dau",
                "role": kw.get("role"), "recall_at_20": 1.0, "recall_at_6": 1.0,
                "mrr": 1.0, "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_retrieval", gia)
    await run_eval.main(["--set", "retrieval", "--model", "bge-m3",
                         "--pace", "0", "--role", "warehouse"])
    assert thay["visibility"] == frozenset({"all"})
    assert thay["role"] == "warehouse"


@pytest.mark.asyncio
async def test_main_mac_dinh_admin_la_unrestricted(monkeypatch):
    thay = {}

    async def gia(pace=0.0, checkpoint_path=None, **kw):
        thay.update(kw)
        return {"set": "retrieval", "n": 1, "rerank": True, "dang_go": "co_dau",
                "role": "admin", "recall_at_20": 1.0, "recall_at_6": 1.0,
                "mrr": 1.0, "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_retrieval", gia)
    await run_eval.main(["--set", "retrieval", "--model", "bge-m3", "--pace", "0"])
    assert thay["visibility"] is UNRESTRICTED
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/test_retrieval_gate.py tests/jobs/test_run_eval_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `AttributeError: module 'evals.role_config' has no attribute 'VISIBILITY_SENSITIVE_SETS'`; `test_gate_tu_choi_baseline_khac_vai` FAIL `DID NOT RAISE`; `test_baseline_path_retrieval_co_hau_to_vai_non_admin` FAIL (chưa có hậu tố).

- [ ] **Step 3: Sửa bốn tệp**

`evals/role_config.py` — sau `ROLE_SENSITIVE_SETS` (`:32`):

```python
# Ba bộ gọi retrieve() THẬT. --role ở đây đổi VISIBILITY (tập lớp tài liệu
# được thấy), KHÔNG đổi prompt — cố ý tách khỏi ROLE_SENSITIVE_SETS để hai
# nghĩa không lẫn (spec 2026-09-20 §5). Mặc định --role admin = không lọc =
# đúng hành vi trước 19b, nên baseline cũ vẫn so được.
VISIBILITY_SENSITIVE_SETS = frozenset({"retrieval", "synthesis_live", "multiturn"})


def visibility_for(role_name: str):
    return roles.rag_visibility_of(role_cfg(role_name))
```

`evals/run_eval.py`:

- Import: `from src.rag.visibility import UNRESTRICTED` cạnh `from src.rag.retrieve import retrieve as _retrieve` (`:38`).
- `baseline_path` (`:108`): đổi điều kiện chuẩn hoá:

```python
    if set_name not in (role_config.ROLE_SENSITIVE_SETS
                        | role_config.VISIBILITY_SENSITIVE_SETS):
        role = "admin"
```

  và bổ sung docstring một đoạn: *"Bộ nhạy VISIBILITY cũng giữ hậu tố vai: `--set retrieval --role warehouse --save-baseline` mà không có hậu tố sẽ ĐÈ baseline admin — xoá mốc cổng dương của 19b."*

- `eval_retrieval` (`:1093`): chữ ký và lời gọi:

```python
async def eval_retrieval(pace: float = 0.0, checkpoint_path=None,
                         rerank: bool = True, dang_go: str = "co_dau",
                         visibility=UNRESTRICTED, role: str = "admin"):
```

  trong `call`: `asyncio.to_thread(_retrieve, _dang_go(dang_go)(question), _TOP_N, None, (), visibility=visibility)` — chú ý `retrieve(query, k, conn, aux_queries, *, visibility)`: truyền `None, ()` cho `conn`, `aux_queries` rồi `visibility=` từ khoá. Trong dict trả về thêm `"role": role,` ngay sau `"dang_go": dang_go,`. Docstring thêm: *"`visibility`/`role`: mặc định KHÔNG lọc (bằng hành vi trước 19b, giữ baseline cũ so được); `--role warehouse` là chân của cổng ÂM."*

- `eval_synthesis_live` (`:1187`): thêm tham số `visibility=UNRESTRICTED`; `:1209` → `asyncio.to_thread(_retrieve, question, _TOP_K, None, (), visibility=visibility)` (giữ `k` như hiện tại — hiện đang mặc định `TOP_K`, viết tường minh `_TOP_K`; nếu module chưa có `_TOP_K` thì dùng đúng tên hằng module đang import cho k mặc định).
- `eval_multiturn` (`:1275`): thêm tham số `visibility=UNRESTRICTED`; hai lời gọi `:1283-1284` thêm `visibility=visibility` (lời gọi thứ hai đã truyền `None, (prev,)` — thêm từ khoá sau).
- `main` (`:1470`): sau khối `if args.set in role_config.ROLE_SENSITIVE_SETS:` thêm:

```python
        if args.set in role_config.VISIBILITY_SENSITIVE_SETS:
            kwargs["visibility"] = role_config.visibility_for(args.role)
            if args.set == "retrieval":
                kwargs["role"] = args.role      # vào JSON kết quả → _gate kiểm parity
```

`jobs/eval_gate.py` — nhánh `retrieval` (viết ở #28): sau vòng `for khoa in ("dang_go", "rerank")` thêm:

```python
        # Baseline ghi trước 19b không có khoá role → hiểu là admin.
        measured_role = result.get("role", "admin")
        baseline_role = base.get("role", "admin")
        if measured_role != baseline_role:
            raise ValueError(f"baseline khác cấu hình role: đo={measured_role!r} "
                             f"baseline={baseline_role!r} — cổng ÂM dùng "
                             f"evals/compare_visibility.py, không dùng --baseline")
```

- [ ] **Step 4: Chạy lại, phải xanh — kèm toàn bộ `tests/jobs/`**

Run: `cd backend && .venv/Scripts/python.exe <launcher nạp ODOO_*> tests/jobs/ tests/agents/test_sop_select_gate.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed` (≥ 301: 294 cũ + 7 mới).

- [ ] **Step 5: Commit**

```bash
git add backend/evals/role_config.py backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/jobs/test_retrieval_gate.py backend/tests/jobs/test_run_eval_visibility.py
git commit -m "feat(evals): --role -> visibility cho retrieval/synthesis_live/multiturn; JSON mang role; baseline co hau to vai; _gate kiem parity role (19b)"
```

---

### Task 8: `evals/compare_visibility.py` — cổng ÂM tất định

**Files:**
- Create: `backend/evals/compare_visibility.py`
- Test: `backend/tests/evals/test_compare_visibility.py`

**Interfaces:**
- Consumes: hai JSON kết quả `--set retrieval` (khoá `per_case[]` với `question`, `recall_at_pool`, `recall_at_final`, `reciprocal_rank`), `RETRIEVAL_CASES`, `DOC_VISIBILITY`.
- Produces: `compare(admin: dict, restricted: dict, cases=RETRIEVAL_CASES) -> dict` với `{"ok": bool, "commercial_leaked": [...], "regressed": [...], "n_commercial": int, "n_other": int}`; CLI `python -m evals.compare_visibility <admin.json> <restricted.json>` exit 0/1.

Bất biến đo (spec §7, làm chính xác hoá): với vai bị chặn, (a) mọi ca **thuần thương mại** (mọi nhãn mong đợi thuộc 4 tệp — đo 2026-09-20: 10/10 ca là thuần, 0 ca lẫn) phải có `recall_at_pool == 0`; (b) mọi ca khác có `recall_at_pool_restricted >= recall_at_pool_admin` — gỡ ứng viên không-đáp-án khỏi pool 20 không thể đẩy đáp án ra ngoài, chỉ có thể kéo nó vào. `recall_at_final` chỉ báo cáo (pool khác → reranker thấy tập khác), không gác.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/evals/test_compare_visibility.py
"""Cổng ÂM: vai bị chặn phải MẤT SẠCH ca thương mại và KHÔNG KÉM ca khác."""
import pytest

from evals import compare_visibility as cv

CASES = [
    ("chiết khấu bậc mấy?", frozenset({("discount_policy.docx", "Điều 1")}), "easy"),
    ("SLA giao hàng?", frozenset({("sla.docx", "Mục 2")}), "hard"),
    ("thuế suất GTGT?", frozenset({("luat-thuegtgt.pdf", "Điều 9")}), "easy"),
]


def _run(rows):
    return {"per_case": [{"question": q, "recall_at_pool": p, "recall_at_final": f,
                          "reciprocal_rank": r} for q, p, f, r in rows]}


def test_qua_khi_thuong_mai_ve_0_va_ca_khac_khong_kem():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 0.5),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is True
    assert ra["n_commercial"] == 2 and ra["n_other"] == 1
    assert ra["commercial_leaked"] == [] and ra["regressed"] == []


def test_truot_khi_mot_ca_thuong_mai_van_lo():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.5, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["commercial_leaked"]] == ["SLA giao hàng?"]


def test_truot_khi_ca_khac_kem_di():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 0.5, 0.5, 0.5)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["regressed"]] == ["thuế suất GTGT?"]


def test_ca_lan_bi_tu_choi_to_tieng():
    """Ca có nhãn từ CẢ tệp thương mại lẫn tệp khác không xếp được vào bên nào —
    hôm nay không có ca nào như thế (0/109), nếu xuất hiện phải báo, không đoán."""
    lan = [("hỏi lẫn", frozenset({("sla.docx", "Mục 1"), ("policy.docx", "Điều 2")}), "hard")]
    with pytest.raises(ValueError, match="lẫn"):
        cv.compare(_run([("hỏi lẫn", 1, 1, 1)]), _run([("hỏi lẫn", 0, 0, 0)]), cases=lan)


def test_thieu_ca_o_mot_ben_la_loi():
    admin = _run([("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    with pytest.raises(ValueError, match="thiếu"):
        cv.compare(admin, _run([]), cases=CASES[2:])
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/evals/test_compare_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'evals.compare_visibility'`

- [ ] **Step 3: Viết module**

```python
# backend/evals/compare_visibility.py
"""Cổng ÂM của 19b — so hai lượt `--set retrieval`: admin (không lọc) và một
vai bị chặn (spec 2026-09-20 §7).

Bất biến:
  (a) ca THUẦN thương mại (mọi nhãn mong đợi thuộc DOC_VISIBILITY) →
      recall_at_pool của vai bị chặn == 0. Không phải "thấp": bằng 0.
  (b) ca khác → recall_at_pool bị chặn >= admin. Gỡ ứng viên không-đáp-án
      khỏi pool 20 không đẩy được đáp án ra, chỉ kéo được vào.
recall_at_final CHỈ báo cáo: pool khác → reranker thấy tập khác.

Chạy: python -m evals.compare_visibility admin.json warehouse.json → exit 0/1.
"""
import json
import sys

from evals.retrieval_cases import RETRIEVAL_CASES
from src.rag.visibility import DOC_VISIBILITY, basename


def _is_commercial_case(expected) -> bool | None:
    """True/False, hoặc None nếu LẪN (có cả hai loại tệp)."""
    kinds = {basename(doc) in DOC_VISIBILITY for doc, _section in expected}
    return None if len(kinds) == 2 else kinds.pop()


def compare(admin: dict, restricted: dict, cases=RETRIEVAL_CASES) -> dict:
    by_q_admin = {r["question"]: r for r in admin["per_case"]}
    by_q_res = {r["question"]: r for r in restricted["per_case"]}
    leaked, regressed = [], []
    n_commercial = n_other = 0
    for question, expected, _difficulty in cases:
        if question not in by_q_admin or question not in by_q_res:
            raise ValueError(f"thiếu ca ở một bên: {question!r}")
        kind = _is_commercial_case(expected)
        if kind is None:
            raise ValueError(f"ca lẫn (nhãn từ cả tệp thương mại lẫn tệp khác), "
                             f"không xếp được: {question!r}")
        a, r = by_q_admin[question], by_q_res[question]
        if kind:
            n_commercial += 1
            if r["recall_at_pool"] != 0:
                leaked.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
        else:
            n_other += 1
            if r["recall_at_pool"] < a["recall_at_pool"]:
                regressed.append({"question": question,
                                  "admin": a["recall_at_pool"],
                                  "restricted": r["recall_at_pool"]})
    return {"ok": not leaked and not regressed,
            "n_commercial": n_commercial, "n_other": n_other,
            "commercial_leaked": leaked, "regressed": regressed}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("dùng: python -m evals.compare_visibility <admin.json> <restricted.json>")
        return 2
    admin = json.load(open(argv[0], encoding="utf-8"))
    restricted = json.load(open(argv[1], encoding="utf-8"))
    result = compare(admin, restricted)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"CỔNG ÂM {'PASS' if result['ok'] else 'FAIL'} — thương mại {result['n_commercial']} ca "
          f"(lộ {len(result['commercial_leaked'])}), khác {result['n_other']} ca "
          f"(kém đi {len(result['regressed'])})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Chạy lại, phải xanh**

Run: cùng lệnh Step 2. Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/compare_visibility.py backend/tests/evals/test_compare_visibility.py
git commit -m "feat(evals): compare_visibility — cong AM tat dinh cho 19b"
```

---

### Task 9: Migration 009 + hợp đồng SQL↔`DOC_VISIBILITY` + getting-started

**Files:**
- Create: `backend/migrations/009_rag_visibility_backfill.sql`
- Modify: `docs/getting-started.md:139-147` (thêm 009)
- Test: `backend/tests/rag/test_migration_009_contract.py`

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/rag/test_migration_009_contract.py
"""DOC_VISIBILITY xuất hiện HAI chỗ (Python + SQL migration 009). Hai nguồn
không được trôi: bốn basename trong SQL == bốn khoá Python."""
import pathlib
import re

from src.rag.visibility import DOC_VISIBILITY

MIGRATION = (pathlib.Path(__file__).resolve().parents[2]
             / "migrations" / "009_rag_visibility_backfill.sql")


def test_bon_basename_trong_sql_bang_dung_DOC_VISIBILITY():
    sql = MIGRATION.read_text(encoding="utf-8")
    trong_sql = set(re.findall(r"LIKE '%([^']+)'", sql))
    # Bỏ mẫu gỡ SID — không phải nhãn lớp
    trong_sql = {b for b in trong_sql if "BaoCaoTaiChinh" not in b}
    assert trong_sql == set(DOC_VISIBILITY), (trong_sql, set(DOC_VISIBILITY))


def test_migration_go_SID_va_idempotent_theo_van_ban():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "BaoCaoTaiChinhBanNien" in sql
    assert "visibility <> 'commercial'" in sql, "UPDATE phải có điều kiện để chạy lại vô hại"
    assert "RAISE NOTICE" in sql, "lượt chạy tay phải để lại bằng chứng số dòng"
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_migration_009_contract.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `FileNotFoundError`.

- [ ] **Step 3: Viết migration**

```sql
-- 009: RBAC tầng RAG (spec 2026-09-20 §6) — backfill lớp visibility + gỡ SID.
--
-- Vì sao: cột rag_chunks.visibility có từ tháng 7 nhưng 4 561/4 561 chunk đều
-- 'all' (đo 2026-09-19) — vai kho đọc được chính sách chiết khấu. Ingest nay
-- ghi lớp từ DOC_VISIBILITY (src/rag/visibility.py), nhưng re-ingest là NO-OP
-- khi content_hash không đổi nên corpus đang có PHẢI backfill ở đây.
--
-- Bốn basename bên dưới PHẢI bằng đúng khoá của DOC_VISIBILITY —
-- tests/rag/test_migration_009_contract.py giữ hai nguồn không trôi.
--
-- ⚠️ THAO TÁC PHÁ HUỶ DUY NHẤT của 19b: gỡ tài liệu SID (báo cáo tài chính
-- bán niên, 660 chunk) — nạp tay lúc test OCR bậc 3, không phải tri thức tổ
-- chức, đã gây ô nhiễm chéo (trả số SID cho câu hỏi về NTC, 2026-09-19).
-- Chunk đi theo ON DELETE CASCADE. Chạy SAU khi chủ dự án gật, KHÔNG nối với
-- lệnh khác.
--
-- Idempotent. Chạy tay, theo lệ của thư mục này. Số dòng in ra bằng RAISE
-- NOTICE — lượt chạy tay để lại bằng chứng (kỳ vọng lần đầu: 24 chunk ->
-- commercial; 1 tài liệu SID / 660 chunk gỡ; lần sau: 0 / 0).
DO $$
DECLARE
    n_commercial int;
    n_sid_chunks int;
    n_sid_docs   int;
BEGIN
    UPDATE rag_chunks SET visibility = 'commercial'
     WHERE visibility <> 'commercial'
       AND (source_file LIKE '%discount_policy.docx'
         OR source_file LIKE '%bang_gia.xlsx'
         OR source_file LIKE '%payment_policy.docx'
         OR source_file LIKE '%sla.docx');
    GET DIAGNOSTICS n_commercial = ROW_COUNT;
    RAISE NOTICE '009: % chunk -> commercial', n_commercial;

    SELECT count(*) INTO n_sid_chunks FROM rag_chunks
     WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%';
    DELETE FROM rag_documents WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%';
    GET DIAGNOSTICS n_sid_docs = ROW_COUNT;
    RAISE NOTICE '009: go % tai lieu SID (% chunk theo cascade)', n_sid_docs, n_sid_chunks;
END $$;
```

- [ ] **Step 4: Thêm 009 vào `docs/getting-started.md`** — trong khối PowerShell `:139-147` thêm hai dòng theo đúng mẫu:

```powershell
   docker cp backend\migrations\009_rag_visibility_backfill.sql youdoo-postgres:/tmp/009_rag_visibility_backfill.sql
   docker exec youdoo-postgres psql -U admin -d ai_assistant -f /tmp/009_rag_visibility_backfill.sql
```

  và một câu ngay dưới khối: *"009 **xoá** tài liệu SID khỏi corpus (thao tác phá huỷ, có chủ đích — xem header file); DB dựng mới không có SID nên in `0 / 0`."*

- [ ] **Step 5: Chạy lại, phải xanh**

Run: cùng lệnh Step 2. Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/009_rag_visibility_backfill.sql backend/tests/rag/test_migration_009_contract.py docs/getting-started.md
git commit -m "feat(migrations): 009 backfill visibility 4 tai lieu thuong mai + go SID (19b)"
```

---

### Task 10: Nghiệm thu sống trong worktree, TRƯỚC merge

**Files:**
- Create: `backend/tests/live_verify_rbac_rag.py`
- Modify: `docs/superpowers/specs/2026-09-20-rbac-tang-rag-design.md` §10; `docs/trang-thai-chung.md` (19b, #35)

**Interfaces:**
- Consumes: `tests/live_verify_common.py::role_user_id(role)`, `chat(history, sid, msg, user_id=)`; env `YOUDOO_ROLE_MAP`, `YOUDOO_API_TOKEN` từ `D:\Youdoo\.env`; backend thật `:8002` chạy **từ worktree** (mã đã sửa), 4 tiến trình MCP.

- [ ] **Step 1: Toàn suite unit xanh trên worktree**

Run: `cd backend && .venv/Scripts/python.exe <launcher nạp ODOO_*> -m "not integration and not live" -q -p no:cacheprovider`
Expected: `≥ 2 830 passed` (2 804 + các test mới), 0 failed.

- [ ] **Step 2: Integration của 19b xanh (không song song với suite khác)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_visibility.py -m integration -q -p no:cacheprovider`
Expected: `2 passed`.

- [ ] **Step 3: Đếm trước migration trên DB THẬT (chỉ đọc)**

Run (PowerShell, cwd = worktree `backend/`):
```powershell
& "D:\Youdoo\scripts\load-env.ps1" | Out-Null
.venv\Scripts\python.exe -c "import os,psycopg; c=psycopg.connect(os.environ.get('RAG_DB_DSN') or os.environ['DATABASE_URL']); print(c.execute(\"SELECT visibility,count(*) FROM rag_chunks GROUP BY 1\").fetchall()); print(c.execute(\"SELECT count(*) FROM rag_chunks WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%'\").fetchall())"
```
Expected: `[('all', 4561)]` và `[(660,)]` (hoặc số hiện tại — ghi lại vào §10).

- [ ] **Step 4: DỪNG — xin chủ dự án gật cho thao tác phá huỷ**

Báo đúng câu: *"Migration 009 sẽ đổi 24 chunk sang `commercial` và XOÁ 1 tài liệu SID / 660 chunk khỏi `public.rag_documents`/`rag_chunks` của DB `ai_assistant` (port 5434). Không hoàn tác được ngoài `backup_20260919`. Gật thì tôi chạy — riêng lệnh này, không nối với gì khác."* Chờ trả lời. Không chạy khi chưa có.

- [ ] **Step 5: Chạy 009 trên DB thật (sau khi gật) — LỆNH ĐỨNG MỘT MÌNH**

Run (PowerShell, cwd = worktree root):
```powershell
docker cp backend\migrations\009_rag_visibility_backfill.sql youdoo-postgres:/tmp/009_rag_visibility_backfill.sql
docker exec youdoo-postgres psql -U admin -d ai_assistant -f /tmp/009_rag_visibility_backfill.sql
```
Expected: hai dòng `NOTICE: 009: 24 chunk -> commercial` và `NOTICE: 009: go 1 tai lieu SID (660 chunk theo cascade)`. Chạy lại lần hai phải in `0` / `0` (idempotent). Ghi nguyên văn vào §10.

- [ ] **Step 6: Đếm sau**

Cùng lệnh Step 3. Expected: `[('all', 3877), ('commercial', 24)]` (3 901 tổng) và `[(0,)]`.

- [ ] **Step 7: Cổng DƯƠNG — hai lượt admin, một lấy JSON sạch, một lấy dòng GATE**

Run (PowerShell, cwd = worktree `backend/`, `.env` đã nạp, `$env:PYTHONIOENCODING="utf-8"`; `evals/results/` là thư mục kết quả đang có):
```powershell
# Lượt 1: JSON thuần (KHÔNG --baseline, vì dòng "GATE …" nối sau JSON sẽ làm json.load hỏng)
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role admin > evals/results/19b-admin.json
# Lượt 2: cổng dương
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role admin --baseline evals/baseline-bge-m3-retrieval.json | Select-Object -Last 1
```
Expected: lượt 2 in `GATE PASS — model=… baseline=0.963`, exit 0; trong `19b-admin.json`: r@20 ≥ 0,9771, `errors: []`. Hai lượt admin phải cho cùng r@20/r@6 (retrieval tất định; nếu lệch, ghi lại và điều tra trước khi đi tiếp). Ghi r@20/r@6/mrr/lat_p50 vào §10 (mốc trước 19b: 0,9771 / 0,9633 / 0,8012 / 573 ms).

- [ ] **Step 8: Cổng ÂM**

```powershell
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role warehouse > evals/results/19b-warehouse.json
.venv\Scripts\python.exe -m evals.compare_visibility evals/results/19b-admin.json evals/results/19b-warehouse.json
```
Expected: `CỔNG ÂM PASS — thương mại 10 ca (lộ 0), khác 99 ca (kém đi 0)`, exit 0. Nếu `lộ > 0`: lỗi ở lọc (Task 3/9), **không** nới cổng. Ghi số vào §10.

- [ ] **Step 9: Viết probe sống**

```python
# backend/tests/live_verify_rbac_rag.py
"""Probe sống 19b: cùng câu hỏi, 4 vai, qua backend THẬT (spec §7).
Chạy: python tests/live_verify_rbac_rag.py — cần backend :8002 (mã worktree),
YOUDOO_ROLE_MAP + YOUDOO_API_TOKEN trong env. Marker live; không vào pytest thường."""
import sys
import uuid

from live_verify_common import chat, load_env, role_user_id

CAU_HOI = "Chính sách chiết khấu của công ty như thế nào?"
DAU_HIEU_LO = ("5%", "10%", "15%", "2%")


def main() -> int:
    load_env()
    ket = {}
    for vai in ("warehouse", "sales", "accounting", "admin"):
        uid = role_user_id(vai)
        if not uid:
            print(f"[ERR] không tìm thấy user id cho vai {vai} trong YOUDOO_ROLE_MAP")
            return 2
        tra_loi = chat([], f"19b-{vai}-{uuid.uuid4().hex[:6]}", CAU_HOI, user_id=uid)
        ket[vai] = tra_loi
        print(f"\n=== {vai} ===\n{tra_loi}\n")
    lo_kho = [d for d in DAU_HIEU_LO if d in ket["warehouse"]]
    thay = {v: any(d in ket[v] for d in DAU_HIEU_LO) for v in ("sales", "accounting", "admin")}
    ok = not lo_kho and all(thay.values())
    print(f"kho lộ: {lo_kho or 'không'} | thấy: {thay} | {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10: Khởi động backend TỪ WORKTREE và chạy probe**

Dùng `start-dev.ps1` **của worktree** (nó nạp toàn bộ `.env` từ gốc worktree — worktree không có `.env`, nên copy tạm `D:\Youdoo\.env` vào gốc worktree; tệp này gitignore, không vào commit). **Nếu `:8002` đang bận bởi backend cũ: KHÔNG tự kill** — báo chủ dự án dừng nó (memory: sự cố subagent kill tiến trình ngoài phạm vi). Xác nhận tiến trình `:8002` là mã worktree (`Get-Process -Id (Get-NetTCPConnection -LocalPort 8002).OwningProcess | Select-Object Path` phải trỏ vào `.claude\worktrees\…`) — hai sự cố trước (#30) đều là "backend cũ chạy suốt tuần". Rồi:

```powershell
cd backend; .venv\Scripts\python.exe tests\live_verify_rbac_rag.py
```
Expected: `kho lộ: không | thấy: {'sales': True, 'accounting': True, 'admin': True} | PASS`. Ghi **nguyên văn 4 câu trả lời** vào §10. Nếu vai kho vẫn thấy số: kiểm `x-openwebui-user-id` → vai (`main._role_from_headers`) và rằng tiến trình `:8002` đang chạy mã worktree — hai lần trước đây "backend cũ chạy suốt tuần" là nguyên nhân (memory #30).

- [ ] **Step 11: Ghi chép + cập nhật trạng thái**

- Spec §10: số Step 3/5/6/7/8, 4 câu trả lời Step 10, khó khăn gặp phải, giả thuyết bị bác (nếu có).
- `docs/trang-thai-chung.md`: 19b → `✅ ĐÓNG (<commit>)` với số cổng dương/âm; #35 → `✅ ĐÓNG — SID đã gỡ theo 19b, không nạp lại`.
- `docs/getting-started.md` đã sửa ở Task 9.

Commit:
```bash
git add backend/tests/live_verify_rbac_rag.py docs/superpowers/specs/2026-09-20-rbac-tang-rag-design.md docs/trang-thai-chung.md
git commit -m "docs(19b): ghi chep thi hanh — cong duong/am, probe song 4 vai; dong 19b + #35"
```

- [ ] **Step 12: Hoàn tất nhánh**

Dùng `superpowers:finishing-a-development-branch`: suite unit toàn bộ xanh trên cây gộp; xoá junction `.venv` bằng `(Get-Item -Force).Delete()` **trước** `git worktree remove`.

---

## Tự soát (đã chạy khi viết plan)

- **Phủ spec**: §3 → Task 1, 2; §4 → Task 3, 4; §5 → Task 6, 7; §6 → Task 5, 9; §7 → Task 3-4 (unit/integration), 7-8 (cổng dương/âm), 10 (probe); §9 ngoài phạm vi — không task nào chạm fallback Open WebUI, nhãn theo mục, chỉ số, #25.
- **Chính xác hoá so với spec §7**: "99 ca giống hệt" → bất biến đúng là `recall_at_pool_restricted >= admin` (gỡ ứng viên không-đáp-án khỏi pool không đẩy đáp án ra); `recall_at_final` chỉ báo cáo. Ghi ở Task 8; cập nhật spec §7 một dòng khi thi hành Task 10 Step 11.
- **Nhất quán kiểu/tên**: `rag_visibility` (RoleCfg) · `rag_visibility_of()` (roles) · `visibility=` (retrieve, 3 chân, 2 node, 3 eval fn) · `visibility_for()` (role_config) · `VISIBILITY_SENSITIVE_SETS` · `class_for()`/`basename()`/`resolve()`/`UNRESTRICTED`/`DEFAULT_VISIBILITY`/`DOC_VISIBILITY`/`VISIBILITY_CLASSES` (visibility.py) · `compare()` (compare_visibility). Task 7 `eval_retrieval` gọi `_retrieve(q, _TOP_N, None, (), visibility=…)` khớp chữ ký Task 3 (`aux_queries` là tham số vị trí thứ 4, `visibility` keyword-only).
- **Không placeholder**: mọi bước code đều có code; Task 10 Step 4 là điểm dừng có chủ đích (xin gật), không phải TBD.
