# Báo bị chặn ở tầng RAG — kế hoạch thi hành

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vai bị chặn (hiện là `warehouse`) hỏi đúng vào tài liệu thương mại thì nhận một câu từ chối **tất định** nêu đúng phòng ban, trên cả đường `rag` lẫn `mixed` — thay vì câu trả lời lạc đề có trích dẫn; chứng minh bằng cổng ÂM mở rộng (cờ `hidden` đúng 10/10 · 0/99) và probe sống 4 vai.

**Architecture:** `retrieve()` chạy thêm một **bản bóng không lọc** (cùng vector/từ khoá đã tính, cùng RRF, không rerank) khi vai bị giới hạn, và nếu ứng viên hạng-1 của bản bóng thuộc lớp bị giấu thì trả `hidden_classes={lớp}` — chunk bị giấu không bao giờ rời hàm. `rag_access.py` (mới) suy tên phòng ban từ `RoleCfg.rag_visibility` (không khai bảng) và dựng câu từ chối. `rag_node` trả câu đó **trước** `synthesize()`; `gather_docs` đẩy câu đó qua state `doc_denied` để `fuse_answer` nối vào cuối câu trả lời ERP.

**Tech Stack:** Python 3.11, psycopg 3 + pgvector, LangGraph (không đụng graph), pytest (marker `integration`/`live`), PostgreSQL 16 container `youdoo-postgres` (:5434).

**Spec:** `docs/superpowers/specs/2026-09-21-bao-bi-chan-tang-rag-design.md` — plan lập luận từ spec; người thi hành đọc cả hai. Spec nền: `docs/superpowers/specs/2026-09-20-rbac-tang-rag-design.md` (19b).

## Global Constraints

- **Lệnh test unit** luôn là `pytest -m "not integration and not live"` — lệnh trần chạy cả live/integration. Test `integration` cần Postgres 5434; chạy riêng, **không** song song với suite khác (schema `rag_test` dùng chung).
- **Worktree** (tạo bằng `superpowers:using-git-worktrees`) **không có** `.env` lẫn `.venv`. Trước khi chạy gì: (1) junction `backend/.venv` → `D:\Youdoo\backend\.venv` bằng PowerShell `New-Item -ItemType Junction -Path backend\.venv -Target D:\Youdoo\backend\.venv`; (2) chạy pytest qua launcher nạp `.env` (`ODOO_*` + `DATABASE_URL`, đổi `localhost`→`127.0.0.1`) — mẫu ở `.superpowers/sdd/2026-09-20-rbac-tang-rag/pytest_env.py` của phiên 19b, hoặc viết lại 20 dòng tương đương. **Không có `DATABASE_URL` thì test integration `skip` lặng lẽ thành xanh giả.** Trước `git worktree remove` phải xoá junction bằng `(Get-Item -Force <path>).Delete()`.
- **Mọi identifier trong code là tiếng Anh**; prose/docstring/comment tiếng Việt như repo; tên hàm test và biến cục bộ trong test tiếng Việt theo lệ repo.
- **Cwd khi chạy test/eval**: `backend/`.
- **Mọi CLI mới/sửa** gọi `use_utf8_streams()` đầu `main()`; test nào chạy CLI thật qua subprocess phải ép `PYTHONIOENCODING=cp1252` (bài học 19b Task 8).
- **Không chuỗi cổng với hành động**; **không** chạy `run_eval.py` hay probe sống trong task code — đó là Task 8 do controller giám sát.
- Mỗi task: test đỏ → code tối thiểu → xanh → commit. Commit subject **không dấu, tiếng Việt** (lệ repo, không tiếng Anh), thân **có dấu**; kết bằng `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Mỗi cổng/test mới phải kèm bằng chứng đột biến** trong report: cố ý phá đúng thứ nó canh → dán output ĐỎ → khôi phục (`git diff` rỗng) → xanh lại.

---

## Bản đồ tệp

| Tệp | Vai trò | Task |
|---|---|---|
| `backend/src/rag/types.py` | `RetrievalResult.hidden_classes` | 1 |
| `backend/src/rag/retrieve.py` | `_COLS` + `c.visibility`; `_prepare_queries`, `_fuse_legs`, `_hidden_at_rank_one`; bản bóng | 1 |
| `backend/tests/rag/test_retrieve_visibility.py` | sửa 2 helper để bản bóng không làm test cũ nhận nhầm câu SQL | 1 |
| `backend/tests/rag/test_retrieve_hidden.py` | **mới** — unit (conn giả hai pool) + integration (Task 5) | 1, 5 |
| `backend/src/agents/rag_access.py` | **mới** — `departments_for`, `denied_message`, `DENIED_MARKER` | 2 |
| `backend/tests/agents/test_rag_access.py` | **mới** | 2 |
| `backend/src/agents/nodes.py` | `rag_node` trả từ chối trước `synthesize()` | 3 |
| `backend/tests/agents/test_rag_denied_nodes.py` | **mới** — rag_node, gather_docs, fuse_answer | 3, 4 |
| `backend/src/agents/state.py`, `fanout.py` | `doc_denied`; `mixed` xoá lúc vào; `gather_docs` đặt; `fuse_answer` dùng; `render_fuse_input(..., doc_denied=None)` | 4 |
| `backend/tests/agents/test_fanout.py` | sửa 1 assert dict + 1 assert annotation | 4 |
| `backend/evals/run_eval.py` | `per_case[].hidden` | 6 |
| `backend/evals/compare_visibility.py` | bất biến (c): `commercial_unflagged`, `other_flagged` | 6 |
| `backend/tests/jobs/test_run_eval_visibility.py`, `tests/evals/test_compare_visibility.py` | thêm ca | 6 |
| `backend/tests/live_verify_rbac_rag.py` | oracle mới hai chiều | 7 |
| `docs/superpowers/specs/2026-09-21-...-design.md` §10, `docs/trang-thai-chung.md`, `README.md` | ghi chép + đóng nợ | 8 |

---

### Task 1: `retrieve()` — bản bóng không lọc, luật hạng-1, `hidden_classes`

**Files:**
- Modify: `backend/src/rag/types.py:41-56` (`RetrievalResult`)
- Modify: `backend/src/rag/retrieve.py:17-19` (`_COLS`), `:256-320` (`retrieve`)
- Modify: `backend/tests/rag/test_retrieve_visibility.py:41-52` (`_sql_cua_ba_chan`), `:103-119` (`test_aux_queries_cung_bi_loc`)
- Test: `backend/tests/rag/test_retrieve_hidden.py` (mới, phần unit)

**Interfaces:**
- Produces: `RetrievalResult.hidden_classes: frozenset[str]` (mặc định `frozenset()`); `retrieve.VIS_IDX = 11`; `_prepare_queries(query, aux_queries) -> list[tuple[list[float], str, str]]`; `_fuse_legs(conn, prepared, visibility) -> tuple[dict, bool]`; `_hidden_at_rank_one(fused, visibility) -> frozenset[str]`.
- Bất biến: `result.chunks` là bản đã lọc SQL; hàng của bản bóng không rời hàm.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/rag/test_retrieve_hidden.py
"""Tín hiệu `hidden_classes` (spec 2026-09-21 §3): bản bóng KHÔNG lọc chạy khi
vai bị giới hạn, luật hạng-1, và chunk bị giấu không bao giờ rời retrieve().

Phần unit: conn giả HAI POOL — trả `visible` khi SQL có mệnh đề lọc, `all_`
khi không. Mọi chân trả cùng danh sách nên thứ tự RRF = thứ tự danh sách:
phần tử đầu của `all_` chính là hạng-1 của bản bóng. Phần integration ở dưới
(Task 5) chạy DB thật.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.visibility import UNRESTRICTED

VIS_CLAUSE = "c.visibility = ANY(%s)"
CHI_ALL = frozenset({"all"})


def _row(id_, source_file, vis, score, text="x"):
    """Hàng khớp `_COLS` + score: (id, doc_id, source_file, doc_title, section_path,
    page, sheet, row_range, chunk_text, effective_date, source_kind, visibility, score)."""
    return (id_, f"d{id_}", source_file, "T", None, None, None, None,
            text, None, "text", vis, score)


class _Cur:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _ConnHaiPool:
    def __init__(self, visible, all_):
        self.visible, self.all_ = visible, all_
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cur(self.visible if VIS_CLAUSE in sql else self.all_)


@pytest.fixture
def khong_ra_ngoai(monkeypatch):
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")


TM = _row(1, "seed\\discount_policy.docx", "commercial", 0.9)
ALL = _row(2, "seed/policy.docx", "all", 0.5)


def test_bi_gioi_han_va_hang_1_bi_giau_thi_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    # BẤT BIẾN AN TOÀN: chunk trả về vẫn là bản đã lọc — không có hàng thương mại
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]


def test_bi_gioi_han_nhung_hang_1_thay_duoc_thi_khong_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[ALL, TM])
    r = rt.retrieve("hoàn hàng", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()


def test_ban_bong_rong_thi_khong_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[], all_=[])
    r = rt.retrieve("không có gì", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.is_empty()


def test_unrestricted_khong_chay_ban_bong(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=UNRESTRICTED)
    assert r.hidden_classes == frozenset()
    assert len(conn.calls) == 3, [s[:40] for s, _ in conn.calls]   # 3 chân, KHÔNG bóng
    assert not any(VIS_CLAUSE in s for s, _ in conn.calls)


def test_bi_gioi_han_chay_dung_hai_luot_ba_chan(khong_ra_ngoai):
    """Lượt LỌC trước, lượt BÓNG sau — 6 câu; nửa đầu có mệnh đề, nửa sau không.
    Thứ tự là hợp đồng: test hình dạng SQL của 19b nhận diện chân bằng câu ĐẦU."""
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    co_loc = [VIS_CLAUSE in s for s, _ in conn.calls]
    assert co_loc == [True, True, True, False, False, False], co_loc


def test_khong_truyen_visibility_van_chay_bong_vi_fail_closed(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn)          # None → {'all'} → bị giới hạn
    assert r.hidden_classes == frozenset({"commercial"})


def test_hidden_at_rank_one_don_vi():
    fused = {1: {"row": TM, "rrf": 0.03}, 2: {"row": ALL, "rrf": 0.02}}
    assert rt._hidden_at_rank_one(fused, CHI_ALL) == frozenset({"commercial"})
    assert rt._hidden_at_rank_one({2: {"row": ALL, "rrf": 0.02}}, CHI_ALL) == frozenset()
    assert rt._hidden_at_rank_one({}, CHI_ALL) == frozenset()
    assert rt._hidden_at_rank_one(fused, frozenset({"all", "commercial"})) == frozenset()
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_hidden.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `TypeError: __init__() got an unexpected keyword argument 'hidden_classes'` hoặc `AttributeError: ... 'hidden_classes'` / `_hidden_at_rank_one`.

- [ ] **Step 3: Sửa `types.py`**

Sau `method: str = "dense-rrf"` trong `RetrievalResult` thêm:

```python
    # Lớp bị GIẤU mà lẽ ra đứng hạng 1 nếu không lọc (spec 2026-09-21 §3).
    # Rỗng khi UNRESTRICTED, khi bản bóng trống, hay khi hạng-1 thấy được.
    # Chỉ mang TÊN LỚP — hàng bị giấu không bao giờ rời retrieve().
    hidden_classes: frozenset = frozenset()
```

- [ ] **Step 4: Sửa `retrieve.py`**

Đổi `_COLS` (giữ 11 cột cũ đúng chỗ, thêm `c.visibility` ở cuối) và thêm hằng chỉ số:

```python
_COLS = ("c.id, c.doc_id, c.source_file, c.doc_title, c.section_path, c.page, "
         "c.sheet, c.row_range, c.chunk_text, d.effective_date, c.source_kind, "
         "c.visibility")
VIS_IDX = 11   # vị trí c.visibility trong hàng; score vẫn là row[-1]
```

Trước `def retrieve(` thêm ba hàm:

```python
def _prepare_queries(query: str, aux_queries) -> list[tuple[list[float], str, str]]:
    """Nhúng + tách từ + bỏ dấu MỘT LẦN cho query chính và mọi aux. Bản lọc lẫn
    bản bóng dùng chung danh sách này — không nhúng lại (Ollama), không tách lại."""
    prepared = [(embed_query(query), segment_vi(query), fold_vi(query))]
    for aux in aux_queries:
        if aux == query:
            continue
        prepared.append((embed_query(aux), segment_vi(aux), fold_vi(aux)))
    return prepared


def _fuse_legs(conn, prepared, visibility) -> tuple[dict, bool]:
    """Ba chân × mọi truy vấn đã chuẩn bị, gộp RRF theo ĐÚNG thứ tự cũ
    (dense+sparse rồi fold, cho query chính rồi từng aux). Trả (fused, fold_gop)."""
    fused: dict = {}
    fold_gop = False
    use_fold = fold_enabled()
    for qvec, qseg, qfold in prepared:
        fused = _rrf(_dense(conn, qvec, visibility),
                     _sparse(conn, qseg, visibility), acc=fused)
        if use_fold:
            hang_fold = _lexical_fold(conn, qfold, visibility)
            fold_gop = fold_gop or bool(hang_fold)
            fused = _rrf_fold(hang_fold, fused)
    return fused, fold_gop


def _hidden_at_rank_one(fused: dict, visibility) -> frozenset:
    """Luật hạng-1 (spec §3): lớp của ứng viên đứng đầu bản bóng, nếu vai
    không được xem lớp đó. Hạng-5 bị giấu KHÔNG tính — vai kho hỏi hoàn hàng
    mà bảng giá lọt hạng 5 vẫn phải được trả lời."""
    if not fused:
        return frozenset()
    top = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)[0]
    cls = top["row"][VIS_IDX]
    return frozenset() if cls in visibility else frozenset({cls})
```

Trong `retrieve()`, thay toàn bộ đoạn từ `qvec = embed_query(query)` đến `ordered = sorted(...)` bằng:

```python
        prepared = _prepare_queries(query, aux_queries)
        qseg = prepared[0][1]
        fused, fold_gop = _fuse_legs(conn, prepared, visibility)
        ordered = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
```

và ngay trước `return RetrievalResult(` thêm:

```python
        # Bản BÓNG không lọc: cùng vector/từ khoá, cùng RRF, KHÔNG rerank, chỉ
        # để hỏi "thứ tốt nhất có bị giấu không". Hàng của nó chết tại đây —
        # chỉ TÊN LỚP đi ra. Admin (UNRESTRICTED) không tốn thêm gì.
        hidden_classes = frozenset()
        if visibility is not UNRESTRICTED:
            shadow, _fold = _fuse_legs(conn, prepared, UNRESTRICTED)
            hidden_classes = _hidden_at_rank_one(shadow, visibility)
```

và thêm `hidden_classes=hidden_classes,` vào lời gọi `RetrievalResult(...)`.

- [ ] **Step 5: Sửa hai helper của test 19b để không nhận nhầm câu bóng**

`tests/rag/test_retrieve_visibility.py` — `_sql_cua_ba_chan`: đổi ba phép gán `ra["..."] = (sql, params)` thành `ra.setdefault("...", (sql, params))` (câu ĐẦU mỗi chân là câu lọc; câu bóng đến sau). Docstring thêm một dòng: *"Lấy câu ĐẦU mỗi chân — bản bóng không lọc (spec 2026-09-21) chạy SAU và không được đè."*

`test_aux_queries_cung_bi_loc`: thay hai assert cuối bằng

```python
    chan = _sql_theo_chan(conn)
    # 4 câu mỗi chân: [primary lọc, aux lọc, primary bóng, aux bóng]. Nửa đầu
    # PHẢI có mệnh đề (không cửa sau cho aux); nửa sau là bản bóng không lọc.
    for ten, calls in chan.items():
        assert [VIS_CLAUSE in sql for sql, _params in calls] == [True, True, False, False], ten
```

- [ ] **Step 6: Chạy lại, phải xanh — kèm toàn bộ test retrieve cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_hidden.py tests/rag/test_retrieve_visibility.py tests/rag/test_sparse_van_chet.py tests/rag/test_fold_vi.py tests/rag/test_rerank_mode.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 7: Bằng chứng đột biến**

Tạm đổi `return frozenset() if cls in visibility else frozenset({cls})` thành `return frozenset()` → `test_bi_gioi_han_va_hang_1_bi_giau_thi_bao` và `test_khong_truyen_visibility_van_chay_bong_vi_fail_closed` phải ĐỎ. Khôi phục, `git diff --stat src/rag/retrieve.py` phải rỗng so với bản đã sửa, chạy lại xanh. Dán cả hai output vào report.

- [ ] **Step 8: Commit**

```bash
git add backend/src/rag/types.py backend/src/rag/retrieve.py backend/tests/rag/test_retrieve_hidden.py backend/tests/rag/test_retrieve_visibility.py
git commit -m "feat(rag): retrieve() chay ban bong khong loc, luat hang-1 -> hidden_classes"
```

---

### Task 2: `rag_access.py` — suy phòng ban, dựng câu từ chối

**Files:**
- Create: `backend/src/agents/rag_access.py`
- Test: `backend/tests/agents/test_rag_access.py`

**Interfaces:**
- Consumes: `roles.load_profile(name=None) -> dict[str, RoleCfg]`, `RoleCfg.label`, `RoleCfg.rag_visibility` (frozenset hoặc `UNRESTRICTED`) từ 19b Task 2.
- Produces: `DENIED_MARKER = "không được xem"`; `departments_for(classes: frozenset[str], profile: dict | None = None) -> list[str]`; `denied_message(role_cfg, classes: frozenset[str], profile: dict | None = None) -> str`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/agents/test_rag_access.py
"""Tên phòng ban SUY từ RoleCfg.rag_visibility — không có bảng khai tay để trôi
(spec 2026-09-21 §4). Câu từ chối tất định, có marker để probe bắt được."""
import pytest

from src.agents import rag_access, roles

TM = frozenset({"commercial"})


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_commercial_thuoc_ke_toan_va_ban_hang(profile):
    p = roles.PROFILES[profile]
    assert rag_access.departments_for(TM, p) == ["Kế toán", "Bán hàng"]


@pytest.mark.parametrize("profile", sorted(roles.PROFILES))
def test_admin_khong_bao_gio_la_phong_ban(profile):
    """Admin là UNRESTRICTED — không 'được xem lớp' theo nghĩa khai báo, nên
    không xuất hiện trong danh sách chỉ dẫn."""
    p = roles.PROFILES[profile]
    for cls in ("all", "commercial"):
        assert "Quản trị" not in rag_access.departments_for(frozenset({cls}), p)


def test_lop_khong_ai_xem_thi_rong():
    assert rag_access.departments_for(frozenset({"khong-ton-tai"}),
                                      roles.PROFILES["small-business"]) == []


def test_khong_truyen_profile_thi_doc_env(monkeypatch):
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "enterprise")
    assert rag_access.departments_for(TM) == ["Kế toán", "Bán hàng"]


def test_cau_tu_choi_neu_vai_va_phong_ban():
    kho = roles.PROFILES["small-business"]["warehouse"]
    msg = rag_access.denied_message(kho, TM, roles.PROFILES["small-business"])
    assert msg == ("Tài liệu về việc này thuộc phạm vi Kế toán / Bán hàng; "
                   "vai Kho không được xem. Bạn có thể hỏi trực tiếp phòng "
                   "Kế toán hoặc Bán hàng.")
    assert rag_access.DENIED_MARKER in msg
    assert "📄" not in msg and "NGUỒN" not in msg     # không footer trích dẫn


def test_cau_tu_choi_mot_phong_ban():
    kho = roles.PROFILES["small-business"]["warehouse"]
    chi_ke_toan = {"x": roles.RoleCfg("x", "Kế toán", "http://localhost:1/sse",
                                      rag_visibility=frozenset({"all", "commercial"}))}
    msg = rag_access.denied_message(kho, TM, chi_ke_toan)
    assert msg.endswith("hỏi trực tiếp phòng Kế toán.")


def test_cau_tu_choi_khong_phong_ban_khong_no():
    kho = roles.PROFILES["small-business"]["warehouse"]
    msg = rag_access.denied_message(kho, frozenset({"khong-ton-tai"}),
                                    roles.PROFILES["small-business"])
    assert msg == "Vai Kho không được xem tài liệu về việc này."


def test_cau_tu_choi_khong_co_role_cfg():
    """role_cfg=None chỉ xảy ra ở test; vẫn phải ra câu hợp lệ, không AttributeError."""
    msg = rag_access.denied_message(None, TM, roles.PROFILES["small-business"])
    assert "vai hiện tại không được xem" in msg
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_access.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'src.agents.rag_access'`.

- [ ] **Step 3: Viết module**

```python
# backend/src/agents/rag_access.py
"""Câu từ chối khi tài liệu bị chặn theo vai (spec 2026-09-21 §4).

Tầng: rag_access → roles → visibility, không chiều ngược. Tên phòng ban SUY
từ `RoleCfg.rag_visibility` — thêm vai/lớp mới thì tự đúng, không có bảng khai
tay để trôi khỏi sự thật (lớp lỗi README gọi tên).
"""
from .roles import load_profile
from src.rag.visibility import UNRESTRICTED

DENIED_MARKER = "không được xem"   # probe sống + eval bắt marker này, không bắt số %


def departments_for(classes: frozenset, profile: dict | None = None) -> list[str]:
    """Tên hiển thị của các vai được xem ít nhất một lớp trong `classes`, theo
    thứ tự khai trong profile. Admin là UNRESTRICTED (không phải tập) → tự loại."""
    profile = load_profile() if profile is None else profile
    names: list[str] = []
    for cfg in profile.values():
        vis = cfg.rag_visibility
        if vis is UNRESTRICTED:
            continue
        if classes & vis and cfg.label not in names:
            names.append(cfg.label)
    return names


def denied_message(role_cfg, classes: frozenset, profile: dict | None = None) -> str:
    """Chuỗi TẤT ĐỊNH — không LLM, không footer trích dẫn (spec §5)."""
    role_label = f"vai {role_cfg.label}" if role_cfg is not None else "vai hiện tại"
    depts = departments_for(classes, profile)
    if not depts:
        return f"{role_label[0].upper()}{role_label[1:]} {DENIED_MARKER} tài liệu về việc này."
    scope = " / ".join(depts)
    ask = " hoặc ".join(depts)
    return (f"Tài liệu về việc này thuộc phạm vi {scope}; {role_label} {DENIED_MARKER}. "
            f"Bạn có thể hỏi trực tiếp phòng {ask}.")
```

- [ ] **Step 4: Chạy lại, phải xanh**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_access.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `9 passed`.

- [ ] **Step 5: Bằng chứng đột biến** — tạm đổi `if classes & vis` thành `if False` → hai test đầu ĐỎ; khôi phục, xanh lại.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/rag_access.py backend/tests/agents/test_rag_access.py
git commit -m "feat(agents): rag_access — suy phong ban tu RoleCfg, cau tu choi tat dinh"
```

---

### Task 3: `rag_node` trả câu từ chối trước `synthesize()`

**Files:**
- Modify: `backend/src/agents/nodes.py` (import + `rag_node`, quanh dòng 127-133)
- Test: `backend/tests/agents/test_rag_denied_nodes.py` (mới, phần rag_node)

**Interfaces:**
- Consumes: `RetrievalResult.hidden_classes` (Task 1), `rag_access.denied_message` (Task 2), `roles.load_profile`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/agents/test_rag_denied_nodes.py
"""Vai bị chặn phải nhận câu từ chối TẤT ĐỊNH — không LLM (spec 2026-09-21 §5).
Patch retrieve, LLM giả nổ nếu bị gọi."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, rag_access, roles
import src.agents.nodes as nodes_mod
from src.rag.types import RetrievalResult

TM = frozenset({"commercial"})
KHO = roles.PROFILES["small-business"]["warehouse"]


class _LLMKhongDuocGoi:
    async def ainvoke(self, messages, config=None):
        raise AssertionError("LLM bị gọi dù đã có câu từ chối tất định")


class _LLMKhongDu:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="KHÔNG_ĐỦ_THÔNG_TIN")


def _ket_qua(hidden=frozenset()):
    return RetrievalResult(query="q", query_used="q", chunks=[], top_score=0.0,
                           total_candidates=0, hidden_classes=hidden)


def _state(text="Chính sách chiết khấu?"):
    return {"messages": [HumanMessage(content=text)]}


async def test_rag_node_bi_chan_tra_cau_tu_choi_khong_goi_llm(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua(TM))
    out = await nodes_mod.make_rag_node(_LLMKhongDuocGoi(), role_cfg=KHO)(_state())
    msg = out["messages"][0].content
    assert msg == rag_access.denied_message(KHO, TM, roles.load_profile())
    assert "Kế toán" in msg and "Bán hàng" in msg and rag_access.DENIED_MARKER in msg


async def test_rag_node_khong_bi_chan_van_di_synthesize(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua())
    out = await nodes_mod.make_rag_node(_LLMKhongDu(), role_cfg=KHO)(_state())
    assert rag_access.DENIED_MARKER not in out["messages"][0].content
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_denied_nodes.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: test đầu FAIL với `AssertionError: LLM bị gọi ...` (node chưa kiểm `hidden_classes`).

- [ ] **Step 3: Sửa `nodes.py`**

Thêm import cạnh `from .roles import rag_visibility_of`:

```python
from .rag_access import denied_message
```

Trong `rag_node`, ngay sau `bao_tien_trinh(NHAN_DOC_TAI_LIEU)` và **trước** `answer = await synthesize(...)`:

```python
            if result.hidden_classes:
                # Kiểm tra TẤT ĐỊNH, không giao cho model: thứ tốt nhất bị giấu
                # theo vai → từ chối có tên phòng ban, không LLM, không footer
                # (spec 2026-09-21 §5). Model tự viết lời từ chối từng đo ra
                # refusal_acc tụt — nên không đưa nó vào synthesize().
                logger.info("rag_node: vai %s bị chặn lớp %s",
                            getattr(role_cfg, "name", None), sorted(result.hidden_classes))
                return {"messages": [AIMessage(content=denied_message(role_cfg, result.hidden_classes))]}
```

- [ ] **Step 4: Chạy lại, phải xanh — kèm test node cũ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_denied_nodes.py tests/agents/test_rag_visibility_nodes.py tests/agents/test_simple_nodes.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/nodes.py backend/tests/agents/test_rag_denied_nodes.py
git commit -m "feat(agents): rag_node tra cau tu choi tat dinh khi hidden_classes, truoc synthesize()"
```

---

### Task 4: Đường `mixed` — `doc_denied` qua state, `fuse_answer` nối câu từ chối

**Files:**
- Modify: `backend/src/agents/state.py:80-82` (sau `erp_facts`)
- Modify: `backend/src/agents/fanout.py:78-79` (`mixed`), `:96-120` (`gather_docs`), `:162-178` (`render_fuse_input`), `:189-260` (`fuse_answer`)
- Modify: `backend/tests/agents/test_fanout.py:31,37`
- Test: `backend/tests/agents/test_rag_denied_nodes.py` (thêm phần fan-out)

**Interfaces:**
- Produces: state `doc_denied: str | None`; `render_fuse_input(chunks, erp_facts, question, doc_denied: str | None = None)` (tham số mới có mặc định — `evals.run_eval.eval_multi_source` gọi 3 tham số vẫn chạy).

- [ ] **Step 1: Viết test đỏ** — nối vào `test_rag_denied_nodes.py`:

```python
# ─── Đường mixed ───────────────────────────────────────────────────────────

class _LLMGhiInput:
    """Ghi lại input để kiểm dòng 'bị hạn chế theo vai'; trả câu ERP thuần."""
    def __init__(self):
        self.seen = []

    async def ainvoke(self, messages, config=None):
        self.seen.append(messages[-1].content)
        return AIMessage(content="Đơn S00042 đã giao ngày 12/09.")


async def test_gather_docs_bi_chan_dat_doc_denied(monkeypatch):
    monkeypatch.setattr(fanout, "retrieve", lambda *a, **kw: _ket_qua(TM))
    out = await fanout.make_gather_docs_node(role_cfg=KHO)(_state())
    assert out["doc_context"] == []
    assert out["doc_denied"] == rag_access.denied_message(KHO, TM, roles.load_profile())


async def test_gather_docs_khong_bi_chan_khong_co_khoa_doc_denied(monkeypatch):
    """Giữ nguyên hình dạng cũ để `mixed` (xoá lúc VÀO) là lớp chịu lực duy nhất."""
    monkeypatch.setattr(fanout, "retrieve", lambda *a, **kw: _ket_qua())
    out = await fanout.make_gather_docs_node(role_cfg=KHO)(_state())
    assert "doc_denied" not in out


async def test_mixed_xoa_doc_denied_luc_vao():
    out = await fanout.make_mixed_node()({"messages": [], "doc_denied": "cũ"})
    assert out["doc_denied"] is None


async def test_fuse_bi_chan_va_erp_rong_tra_thang_cau_tu_choi():
    msg = rag_access.denied_message(KHO, TM, roles.load_profile())
    out = await fanout.make_fuse_answer_node(_LLMKhongDuocGoi())(
        {"messages": [HumanMessage(content="q")], "doc_context": [],
         "erp_facts": "", "doc_denied": msg})
    assert out["messages"][0].content == msg
    assert out["doc_denied"] is None            # clear lúc RA


async def test_fuse_bi_chan_co_erp_noi_cau_tu_choi_vao_cuoi(monkeypatch):
    async def _giu_nguyen(answer, *a, **kw):
        return answer
    monkeypatch.setattr(fanout, "cite_and_verify", _giu_nguyen)
    monkeypatch.setattr(fanout, "verify_erp_grounding", _giu_nguyen)
    msg = rag_access.denied_message(KHO, TM, roles.load_profile())
    llm = _LLMGhiInput()
    out = await fanout.make_fuse_answer_node(llm)(
        {"messages": [HumanMessage(content="S00042 có được chiết khấu không?")],
         "doc_context": [], "erp_facts": "S00042: đã giao 12/09", "doc_denied": msg})
    answer = out["messages"][0].content
    assert answer.startswith("Đơn S00042 đã giao ngày 12/09.")
    assert answer.endswith(msg)                  # tất định, nối vào CUỐI
    assert "bị hạn chế theo vai" in llm.seen[0]  # model được BÁO, không được tự suy
    assert "KHÔNG kết luận gì về chính sách" in llm.seen[0]


def test_render_fuse_input_mac_dinh_khong_doi():
    from src.agents.fanout import render_fuse_input
    assert render_fuse_input([], "erp", "q") == "TÀI LIỆU:\n\n\nDỮ LIỆU ERP:\nerp\n\nCÂU HỎI: q"
    assert "bị hạn chế theo vai" in render_fuse_input([], "erp", "q", doc_denied="x")
```

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_denied_nodes.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: các test mixed FAIL (`KeyError: 'doc_denied'`, `TypeError: ... doc_denied`).

- [ ] **Step 3: Sửa `state.py`** — sau khối `erp_facts` thêm:

```python
    doc_denied: str | None        # chân TÀI LIỆU của `mixed` bị CHẶN THEO VAI: câu
                                  # từ chối đã dựng (rag_access.denied_message).
                                  # Mang CHUỖI vì gather_docs có role_cfg còn
                                  # fuse_answer không. Cùng vòng đời với
                                  # doc_context: `mixed` xoá lúc VÀO, fuse xoá lúc RA.
```

- [ ] **Step 4: Sửa `fanout.py`**

Import: thêm `from .rag_access import denied_message` cạnh `from .roles import rag_visibility_of`.

`mixed` (dòng 78-79):

```python
    async def mixed(state: ERPAgentState) -> dict:
        return {"doc_context": None, "erp_facts": None, "doc_denied": None}
```

`gather_docs` — trong `try`, ngay sau lời gọi `retrieve`:

```python
            if result.hidden_classes:
                # Thứ tốt nhất bị giấu theo vai: chân tài liệu KHÔNG rỗng về
                # thông tin — nó biết mình bị chặn. Đẩy câu từ chối qua state
                # để fuse_answer nối vào, model không được tự viết.
                return {"doc_context": [],
                        "doc_denied": denied_message(role_cfg, result.hidden_classes)}
```

`render_fuse_input`:

```python
def render_fuse_input(chunks, erp_facts: str, question: str,
                      doc_denied: str | None = None) -> str:
    ...docstring cũ giữ nguyên, thêm một dòng:
    `doc_denied` (spec 2026-09-21 §5): phần TÀI LIỆU ghi rõ bị hạn chế theo vai
    để model KHÔNG tự suy "chính sách không đề cập"; eval gọi 3 tham số như cũ.
    ...
    tai_lieu = (_format_context(chunks) if chunks or not doc_denied
                else "(bị hạn chế theo vai — KHÔNG kết luận gì về chính sách)")
    return (f"TÀI LIỆU:\n{tai_lieu}\n\n"
            f"DỮ LIỆU ERP:\n{erp_facts}\n\n"
            f"CÂU HỎI: {question}")
```

`fuse_answer`:
- `clear = {"doc_context": None, "erp_facts": None, "doc_denied": None}`
- sau `erp_facts = state.get("erp_facts") or ""` thêm `doc_denied = state.get("doc_denied")`
- trong `try`, **trước** nhánh `if not chunks and not erp_facts:` thêm:

```python
            if doc_denied and not erp_facts:
                # Chân tài liệu bị chặn, chân ERP rỗng → chỉ còn câu từ chối.
                # Đứng TRƯỚC nhánh SAFE_MSG: bị chặn không phải "không có gì".
                return {"messages": [AIMessage(content=doc_denied)], **clear,
                        "suggested_write": False, "suggested_write_at": anchor}
```

- `HumanMessage(content=render_fuse_input(chunks, erp_facts, _last_human(state), doc_denied=doc_denied))`
- sau khối `if erp_facts: answer = await verify_erp_grounding(...)` thêm:

```python
            if doc_denied:
                answer = answer.rstrip() + "\n\n" + doc_denied
```

- [ ] **Step 5: Sửa `tests/agents/test_fanout.py`**

Dòng 31: `{"doc_context": None, "erp_facts": None}` → `{"doc_context": None, "erp_facts": None, "doc_denied": None}`.
Sau dòng 37 (`assert "doc_context" in ann`) thêm `assert "doc_denied" in ann`.

- [ ] **Step 6: Chạy lại, phải xanh — kèm test fan-out cũ + eval multi_source dùng `render_fuse_input`**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_rag_denied_nodes.py tests/agents/test_fanout.py tests/agents/test_fanout_graph.py tests/evals -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed`.

- [ ] **Step 7: Bằng chứng đột biến** — tạm xoá dòng `answer = answer.rstrip() + "\n\n" + doc_denied` → `test_fuse_bi_chan_co_erp_noi_cau_tu_choi_vao_cuoi` ĐỎ; khôi phục, xanh.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/state.py backend/src/agents/fanout.py backend/tests/agents/test_rag_denied_nodes.py backend/tests/agents/test_fanout.py
git commit -m "feat(agents): duong mixed — doc_denied qua state, fuse_answer noi cau tu choi tat dinh"
```

---

### Task 5: Integration — DB thật, ca thuận và ca ngược

**Files:**
- Modify: `backend/tests/rag/test_retrieve_hidden.py` (thêm phần integration ở cuối)

**Interfaces:**
- Consumes: fixture `clean_tables` (`tests/rag/conftest.py`), helper `_nap_hai_tai_lieu`, `_vec`, `_DIM` từ `tests/rag/test_retrieve_visibility.py` (import từ module test anh em — chấp nhận, thay vì chép 15 dòng).

- [ ] **Step 1: Viết test**

```python
# ─── Integration: DB thật ──────────────────────────────────────────────────

from tests.rag.test_retrieve_visibility import _DIM, _nap_hai_tai_lieu
from src.rag.visibility import UNRESTRICTED as _UNR


def _truc(hot: int):
    v = [0.0] * _DIM
    v[hot] = 1.0
    return v


@pytest.mark.integration
def test_ca_thuan_commercial_hang_1_thi_bao(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))   # gần chunk commercial
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    assert {c.source_file for c in r.chunks} == {"seed/policy.docx"}   # vẫn lọc


@pytest.mark.integration
def test_ca_nguoc_all_hang_1_thi_khong_bao(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(1))   # gần chunk 'all'
    r = rt.retrieve("hoàn hàng", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.chunks, "fixture sai — không có ứng viên thì test tự vô hiệu"


@pytest.mark.integration
def test_admin_khong_bao_va_thay_ca_hai(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))
    r = rt.retrieve("chiết khấu", conn=conn, visibility=_UNR)
    assert r.hidden_classes == frozenset()
    assert {c.source_file for c in r.chunks} == {"seed\\discount_policy.docx", "seed/policy.docx"}
```

- [ ] **Step 2: Chạy integration (cần Postgres 5434, MỘT MÌNH)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/rag/test_retrieve_hidden.py -m integration -q -p no:cacheprovider`
Expected: `3 passed` — **không** `skipped` (skip = thiếu `DATABASE_URL`, xanh giả).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/rag/test_retrieve_hidden.py
git commit -m "test(rag): integration hidden_classes — ca thuan, ca nguoc, admin, tren DB that"
```

---

### Task 6: Eval ghi `hidden`; cổng ÂM thêm bất biến (c)

**Files:**
- Modify: `backend/evals/run_eval.py:1142-1143` (`per_case.append`)
- Modify: `backend/evals/compare_visibility.py:37-85` (`compare`), `:98-102` (banner)
- Test: `backend/tests/jobs/test_run_eval_visibility.py` (thêm 1 ca), `backend/tests/evals/test_compare_visibility.py` (sửa fixture + thêm 3 ca)

**Interfaces:**
- Produces: `per_case[].hidden: bool`; `compare()` trả thêm `commercial_unflagged: list`, `other_flagged: list`; `ok` đòi cả hai rỗng; thiếu khoá `hidden` ở bất kỳ ca nào → `ValueError`.

- [ ] **Step 1: Viết test đỏ**

Vào `tests/jobs/test_run_eval_visibility.py` thêm:

```python
async def test_eval_retrieval_per_case_mang_hidden(monkeypatch):
    from src.rag.types import RetrievalResult
    case = ("câu thử", frozenset({("a.pdf", "Điều 1")}), "hard")
    monkeypatch.setattr(run_eval, "RETRIEVAL_CASES", [case])
    fake = RetrievalResult(query="q", query_used="q", chunks=[], top_score=0.0,
                           total_candidates=0, hidden_classes=frozenset({"commercial"}))
    monkeypatch.setattr(run_eval, "_retrieve", lambda *a, **kw: fake)
    result = await run_eval.eval_retrieval(pace=0.0)
    assert result["per_case"][0]["hidden"] is True
```

Vào `tests/evals/test_compare_visibility.py` — helper `_run(rows)` (dòng 14) dựng
`per_case` từ 4-tuple `(q, p, f, r)`. Đổi thành:

```python
_TM = {"chiết khấu bậc mấy?", "SLA giao hàng?"}   # hai ca THUẦN thương mại trong CASES


def _run(rows, restricted=False):
    """`hidden` mặc định ĐÚNG: vế bị chặn bật ở ca thương mại, vế admin tắt hết.
    Test nào muốn sai thì sửa từng dòng SAU khi dựng."""
    return {"per_case": [{"question": q, "recall_at_pool": p, "recall_at_final": f,
                          "reciprocal_rank": r, "hidden": restricted and q in _TM}
                         for q, p, f, r in rows]}
```

và ở **mọi** test hiện có, lời gọi dựng vế bị chặn `kho = _run([...])` thêm
`restricted=True` (grep `kho = _run(` — kể cả trong
`test_neu_bo_loc_bi_tat_cong_phai_that_bai`, `test_hai_luot_kho_that_bai`,
`test_cung_tep_hai_lan_that_bai`, `test_admin_khong_thay_thuong_mai_bi_tu_choi`;
vế admin giữ nguyên). Rồi thêm ba ca:

```python
def _cap_dung():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 0.5),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)], restricted=True)
    return admin, kho


def test_ca_thuong_mai_khong_bat_co_thi_that_bai():
    admin, kho = _cap_dung()
    kho["per_case"][1]["hidden"] = False            # "SLA giao hàng?" bị chặn mà không báo
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["commercial_unflagged"]] == ["SLA giao hàng?"]
    assert ra["commercial_leaked"] == [] and ra["other_flagged"] == []


def test_ca_khac_bat_co_oan_thi_that_bai():
    admin, kho = _cap_dung()
    kho["per_case"][2]["hidden"] = True             # "thuế suất GTGT?" bị từ chối oan
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["other_flagged"]] == ["thuế suất GTGT?"]
    assert ra["commercial_unflagged"] == []


def test_thieu_khoa_hidden_la_loi():
    admin, kho = _cap_dung()
    del kho["per_case"][0]["hidden"]
    with pytest.raises(ValueError, match="hidden"):
        cv.compare(admin, kho, cases=CASES)
```

`test_cli_exit_khac_0_khi_that_bai` mock `compare` bằng dict thiếu hai khoá mới → thêm
`"commercial_unflagged": [], "other_flagged": []` vào cả hai dict mock (banner mới đọc chúng).

Vào `tests/test_cli_utf8.py` (test CLI cp1252 của 19b, dòng ~124-129): `_full_case_json`
thêm `"hidden": overrides.get(q, 1.0) == 0.0 and q in commercial_questions` — tức vế
"thất bại" (thương mại còn lộ) không có cờ, vế "đạt" (thương mại về 0) có cờ đúng — để
nhánh ĐẠT của test đó vẫn PASS dưới bất biến (c) và nhánh HỎNG vẫn FAIL vì `lộ`.

- [ ] **Step 2: Chạy để chắc nó đỏ**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs/test_run_eval_visibility.py tests/evals/test_compare_visibility.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `KeyError: 'hidden'` / `KeyError: 'commercial_unflagged'`.

- [ ] **Step 3: Sửa `run_eval.py`** — trong `per_case.append({...})` của `eval_retrieval` thêm `"hidden": bool(result.hidden_classes),` sau `"method": result.method,`.

- [ ] **Step 4: Sửa `compare_visibility.py`**

Trong `compare()`: khai thêm `unflagged, flagged = [], []`; trong vòng lặp, sau khi lấy `a, r`:

```python
        if "hidden" not in r:
            raise ValueError(f"thiếu khoá 'hidden' ở vế bị chặn cho ca {question!r} — "
                             f"chạy lại eval sau khi retrieve() có hidden_classes")
        if kind:
            ...leaked như cũ...
            if not r["hidden"]:
                unflagged.append({"question": question})
        else:
            ...regressed như cũ...
            if r["hidden"]:
                flagged.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
```

`return`: `"ok": not leaked and not regressed and not unflagged and not flagged, ..., "commercial_unflagged": unflagged, "other_flagged": flagged`.

Banner trong `main()`:

```python
    print(f"CỔNG ÂM {'PASS' if result['ok'] else 'FAIL'} — thương mại {result['n_commercial']} ca "
          f"(lộ {len(result['commercial_leaked'])}, không báo chặn {len(result['commercial_unflagged'])}), "
          f"khác {result['n_other']} ca (kém đi {len(result['regressed'])}, "
          f"từ chối oan {len(result['other_flagged'])})")
```

Docstring đầu module thêm bất biến (c) bằng một câu: *"(c) cờ `hidden` phải bật ở mọi ca thuần thương mại và tắt ở mọi ca khác — precision/recall của phép báo bị chặn."*

- [ ] **Step 5: Chạy lại, phải xanh — kèm test CLI cp1252**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/jobs tests/evals tests/test_cli_utf8.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: tất cả `passed` (test CLI subprocess của 19b dựng JSON có đủ khoá — nếu nó đỏ vì thiếu `hidden`, sửa fixture của test đó thêm `"hidden"` đúng nghĩa, KHÔNG nới `compare()`).

- [ ] **Step 6: Commit**

```bash
git add backend/evals/run_eval.py backend/evals/compare_visibility.py backend/tests/jobs/test_run_eval_visibility.py backend/tests/evals/test_compare_visibility.py backend/tests/test_cli_utf8.py
git commit -m "feat(evals): per_case.hidden + cong AM bat bien (c) — khong bao chan / tu choi oan"
```

---

### Task 7: Probe sống — oracle hai chiều

**Files:**
- Modify: `backend/tests/live_verify_rbac_rag.py`

- [ ] **Step 1: Viết lại phần kiểm** — thay `DAU_HIEU_LO` và ba dòng tính `lo_kho`/`thay`/`ok` bằng:

```python
from src.agents.rag_access import DENIED_MARKER

NGUON_MONG_DOI = "discount_policy.docx"   # footer trích dẫn của 3 vai được xem
...
    kho = ket["warehouse"]
    kho_tu_choi = DENIED_MARKER in kho and "Kế toán" in kho and "Bán hàng" in kho
    kho_khong_trich = NGUON_MONG_DOI not in kho
    thay = {v: NGUON_MONG_DOI in ket[v] and DENIED_MARKER not in ket[v]
            for v in ("sales", "accounting", "admin")}
    ok = kho_tu_choi and kho_khong_trich and all(thay.values())
    print(f"kho từ chối đúng: {kho_tu_choi} | kho không trích: {kho_khong_trich} | "
          f"thấy: {thay} | {'PASS' if ok else 'FAIL'}")
```

Docstring thêm: *"Oracle theo MARKER + FOOTER, không theo chuỗi con '5%' ('15%' chứa '5%')."*

- [ ] **Step 2: Kiểm biên dịch** — `cd backend && .venv/Scripts/python.exe -m py_compile tests/live_verify_rbac_rag.py` (exit 0). **Không chạy** — cần backend :8002 và tốn hạn mức; Task 8.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/live_verify_rbac_rag.py
git commit -m "test(19b): probe song — oracle marker tu choi + footer trich dan, bo chuoi con 5%"
```

---

### Task 8: Nghiệm thu sống trong worktree, TRƯỚC merge (controller giám sát)

**Files:**
- Modify: `docs/superpowers/specs/2026-09-21-bao-bi-chan-tang-rag-design.md` §10; `docs/trang-thai-chung.md` (thêm mục mới, đóng); `README.md` (Known limitations: gỡ mục "not told it was blocked"; Roadmap: gỡ dòng tương ứng; Role-based access: một câu về câu từ chối)
- Create: `backend/evals/results/bao-bi-chan-2026-09-21/{admin.json,warehouse.json,README.md}`

- [ ] **Step 1: Toàn suite unit trên worktree, KHÔNG giới hạn thư mục**

Run: `cd backend && .venv/Scripts/python.exe <launcher> -m "not integration and not live" -q -p no:cacheprovider`
Expected: `≥ 2 890 passed` (2 864 + ~26 test mới), 0 failed. Chạy thêm một lượt `DATABASE_URL= ...` cho `tests/jobs tests/evals tests/agents` để mô phỏng runner CI (bài học `bc7eae2`).

- [ ] **Step 2: Integration (một mình)**

Run: `tests/rag/test_retrieve_hidden.py tests/rag/test_retrieve_visibility.py tests/rag/test_retrieve.py -m integration` → tất cả `passed`, không `skipped`.

- [ ] **Step 3: Hai lượt eval retrieval (cục bộ, không LLM) → cổng ÂM mở rộng**

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role admin     > evals/results/bao-bi-chan-2026-09-21/admin.json
.venv\Scripts\python.exe -m evals.run_eval --set retrieval --model bge-m3 --role warehouse > evals/results/bao-bi-chan-2026-09-21/warehouse.json
.venv\Scripts\python.exe -m evals.compare_visibility evals/results/bao-bi-chan-2026-09-21/admin.json evals/results/bao-bi-chan-2026-09-21/warehouse.json
```

Expected: `CỔNG ÂM PASS — thương mại 10 ca (lộ 0, không báo chặn 0), khác 99 ca (kém đi 0, từ chối oan 0)`, exit 0. Ghi `lat_p50` vai kho (mốc 521 ms). **Nếu `từ chối oan > 0`:** DỪNG, ghi danh sách ca vào §10, và mở quyết định "siết luật hạng-1 thành hạng-1 + sàn điểm" (spec §6.3) — không nới cổng.
Cổng DƯƠNG admin: chạy thêm `--baseline evals/baseline-bge-m3-retrieval.json` → `GATE PASS`.
README của thư mục kết quả theo mẫu `evals/results/19b-2026-09-20/README.md`.

- [ ] **Step 4: Probe sống** — khởi backend + 4 MCP từ worktree (`start-dev.ps1` từ worktree; cần junction `mcp-servers/odoo/.venv` và bản sao `.env` **xoá ngay sau**); xác minh mã đang chạy là worktree (log worktree tươi; main chưa có `rag_access.py`); `cd backend && python -m tests.live_verify_rbac_rag`. Expected: `PASS`; **đọc toàn văn** 4 câu trả lời, dán vào §10. Dừng đúng 5 tiến trình đã khởi; xoá `.env` sao; gỡ junction MCP.

- [ ] **Step 5: Ghi chép** — §10 spec (số cờ, lat_p50, 4 câu trả lời, khó khăn, giả thuyết bị bác); `docs/trang-thai-chung.md` thêm mục mới ✅ ĐÓNG; README ba chỗ nêu trên.

- [ ] **Step 6: Commit** — `docs(bao-bi-chan): ghi chep thuc thi §10, dong muc, cap nhat README` rồi review toàn nhánh → merge theo `superpowers:finishing-a-development-branch`.

---

## Tự rà plan (đã làm khi viết)

- **Phủ spec:** §3 → Task 1, 5; §4 → Task 2; §5 → Task 3, 4; §6.1 → Task 1-4; §6.2 → Task 5; §6.3 → Task 6, 8; §6.4 → Task 7, 8; §6.5 → Task 8. §8 ngoài phạm vi: không task nào chạm — đúng.
- **Nhất quán kiểu:** `hidden_classes: frozenset` (Task 1) ↔ `_ket_qua(hidden=frozenset(...))` (Task 3/4) ↔ `bool(result.hidden_classes)` (Task 6); `denied_message(role_cfg, classes, profile=None)` (Task 2) ↔ gọi 2 tham số ở node (Task 3/4, profile đọc env) ↔ gọi 3 tham số trong test; `doc_denied: str | None` (Task 4) ↔ `render_fuse_input(..., doc_denied=None)`.
- **Tương thích test cũ:** `test_fanout.py` so dict → `gather_docs` chỉ trả `doc_denied` khi bị chặn (Task 4 Step 4/5); test hình dạng SQL 19b nhận câu ĐẦU (Task 1 Step 5); `render_fuse_input` 3 tham số cho eval (Task 4).
- **Bẫy đã biết:** integration `skip` = xanh giả (Global); CLI cp1252 (Task 6 Step 5 chạy `test_cli_utf8.py`); lệnh chờ CI phải đọc `conclusion` (Task 8 Step 6, sau push).
