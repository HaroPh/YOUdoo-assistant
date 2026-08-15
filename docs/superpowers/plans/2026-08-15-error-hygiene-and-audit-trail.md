# Vệ sinh thông báo lỗi + khôi phục vệt kiểm toán — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Không còn chỗ nào nội suy nguyên văn exception vào câu trả lời người dùng, và mọi lỗi bị giấu đi đều có dấu vết ở nơi kiểm được.

**Architecture:** Ba lớp việc. (1) Dựng bảng `mcp_call_log` — hiện KHÔNG tồn tại nên toàn bộ vệt kiểm toán MCP chưa từng ghi được gì — rồi làm cho "bảng có thật" thành thứ fail-loud lúc khởi động. (2) Thay 89 chỗ rò trên 4 tầng bằng ba helper cùng khuôn (log rồi trả câu chung), kèm một lưới quét theo LOẠI TRỪ phủ mọi cây nguồn. (3) Đưa quyền đọc `mail.activity` vào bảng kiểm quyền và mở nguồn phủ để tool chỉ-đọc không lọt.

**Tech Stack:** Python 3.11, FastMCP, psycopg2, pytest, XML-RPC (Odoo 17), Postgres.

**Spec:** `docs/superpowers/specs/2026-08-14-error-hygiene-and-audit-trail-design.md`

## Global Constraints

- **Lệnh test BẮT BUỘC:** `pytest -m "not integration and not live"` chạy từ `backend/`. Lệnh `pytest` trần gọi API LLM thật và Postgres thật — đã gây sự cố, không bao giờ dùng.
- **Định danh tiếng Anh trong mã nguồn** (`backend/src`, `mcp-servers`, `backend/skills`); chú thích và chuỗi hiển thị tiếng Việt. Mã test trong `backend/tests` theo quy ước phiên âm tiếng Việt đã có sẵn ở đó.
- **Quy tắc đổi thông báo — dùng NGUYÊN VĂN, không sáng tác lại:** giữ nguyên phần tiền tố đang có, chỉ bỏ `: {e}` và nối hậu tố cố định.
  - Tầng GHI (MCP tools, agents, skills): `f"<tiền tố đang có> — thao tác chưa được thực hiện. Nếu lặp lại, báo quản trị viên."`
  - Tầng ĐỌC (`erp_query`): `f"<tiền tố đang có> — không lấy được dữ liệu. Nếu lặp lại, báo quản trị viên."`
  - ⚠️ Đây là **chi tiết hoá** của spec §2.3, không phải đi ngược: spec nêu một câu ví dụ (`"Không tạo được hóa đơn cho đơn SO123 — …"`), plan chọn giữ tiền tố cũ vì ba lý do — ít churn hơn trên 89 chỗ, giữ được thông tin "thao tác nào / chứng từ nào hỏng", và giữ 1 trong 2 test đang khớp chuỗi khỏi phải sửa.
- **Không được lộ** trong chuỗi trả về người dùng: nội dung exception, tên nhóm quyền Odoo, tên model kỹ thuật không có sẵn trong tiền tố cũ, đường dẫn file, traceback.
- **Ba chỗ `raise` nội bộ GIỮ NGUYÊN**, không đụng: `backend/src/agents/skill_manifest.py:83`, `skill_manifest.py:106`, `backend/src/rag/embed.py:78`. Đó là fail-loud lúc nạp cấu hình, hướng tới lập trình viên, không ra người dùng.
- **Không đụng prompt.** Cổng eval (`intent` 0.870, `planner` 1.000, `sop_select` hijack=0) không được thụt; đợt này không có lý do gì chạm tới chúng.
- Số liệu nền, đo 2026-08-14: **89 chỗ rò** = 21 (`mcp-servers/odoo/tools/`) + 44 (`backend/src/erp_query/`) + 23 (`backend/src/agents/`) + 1 (`backend/skills/`).

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/migrations/002_mcp_call_log.sql` | **Tạo mới.** Schema bảng vệt kiểm toán, đúng 12 cột code hiện hành đọc/ghi | 1 |
| `mcp-servers/odoo/event_log.py` | Thêm `assert_log_table_ready()` — fail-loud khi có DSN mà thiếu bảng | 1 |
| `mcp-servers/odoo/server.py` | Gọi hàm trên lúc khởi động + `logging.basicConfig` tường minh | 1 |
| `mcp-servers/odoo/verify_audit_chain.py` | Tách "bảng rỗng" khỏi "chuỗi nguyên vẹn" | 2 |
| `docs/getting-started.md` | Mục chạy migration (cả `001` lẫn `002`) | 2 |
| `mcp-servers/odoo/helpers.py` | `fail()` — helper tầng MCP: log + audit + envelope sạch | 3 |
| `mcp-servers/odoo/tools/*.py` | 21 điểm gọi | 3 |
| `backend/src/erp_query/envelope.py` | `fail_read()` — helper tầng đọc | 4 |
| `backend/src/erp_query/*.py` | 44 điểm gọi | 4 |
| `backend/src/agents/create_order.py` | `fail_write()` — helper tầng điều phối, đặt cạnh `_msg()` | 5 |
| `backend/src/agents/*.py`, `backend/skills/bao-gia-chiet-khau/logic.py` | 23 + 1 điểm gọi | 5 |
| `backend/tests/mcp/test_khong_ro_loi_exception.py` | **Tạo mới.** Lưới quét theo loại trừ, phủ mọi cây nguồn | 6 |
| `scripts/check_role_odoo_consistency.py` | Cặp `("mail.activity","read")` + dòng `find_my_activities` | 7 |
| `backend/tests/mcp/test_tool_access_map_drift.py` | Mở nguồn phủ sang mọi tool MCP đã đăng ký | 8 |

---

## Task 1: Bảng vệt kiểm toán + fail-loud lúc khởi động

**Files:**
- Create: `backend/migrations/002_mcp_call_log.sql`
- Modify: `mcp-servers/odoo/event_log.py`
- Modify: `mcp-servers/odoo/server.py`
- Test: `backend/tests/mcp/test_audit_log_table.py` (tạo mới)

**Interfaces:**
- Consumes: `event_log._get_db()` (đã có), `config.DATABASE_URL` (đã có)
- Produces: `event_log.assert_log_table_ready() -> None` — không có `DATABASE_URL` thì trả về ngay; có mà thiếu bảng `mcp_call_log` thì `raise RuntimeError`. Task 2 và Task 3 đều dựa vào bảng này tồn tại.

**Bối cảnh mà người thực thi không thể tự biết:** bảng `mcp_call_log` **chưa bao giờ tồn tại** trong database này. `event_log.log_mcp_event` bọc toàn bộ thân hàm trong `try/except Exception: pass`, nên `UndefinedTable` bị nuốt im lặng ở mọi lượt gọi kể từ ngày port code sang. Không có `CREATE TABLE` ở bất kỳ đâu trong repo. Đây là lý do tồn tại của cả Task này.

- [ ] **Step 1: Viết migration**

Tạo `backend/migrations/002_mcp_call_log.sql`:

```sql
-- Vệt kiểm toán mọi lệnh gọi MCP (event_log.py + audit_chain.py).
--
-- ⚠️ Bảng này CHƯA TỪNG tồn tại trong database Youdoo: code ghi log được port
-- sang nhưng schema thì không, và log_mcp_event nuốt mọi lỗi ghi ("không được
-- làm hỏng tool") nên UndefinedTable bị nuốt im lặng ở từng lượt gọi. Toàn bộ
-- permission_denied / rate_limit / model_access / write_gate_error chưa từng
-- được ghi. Đo 2026-08-14.
--
-- 12 cột dưới đây là ĐÚNG tập mà event_log.log_mcp_event INSERT và
-- verify_audit_chain._COLUMNS SELECT. Đừng thêm bớt mà không sửa cả hai nơi.
--
-- KHÔNG đặt CHECK trên event_type: thêm một loại sự kiện mới (đợt này thêm
-- 'tool_error') không được đòi migration mới.

CREATE TABLE IF NOT EXISTS mcp_call_log (
    id            bigserial   PRIMARY KEY,
    created_at    timestamptz NOT NULL,
    event_type    text        NOT NULL,
    caller        text,
    tool_name     text,
    model_name    text,
    operation     text,
    duration_ms   integer,
    error_code    text,
    error_message text,
    -- NULL được: verify_audit_chain lọc WHERE entry_hash IS NOT NULL, tức
    -- schema đã lường trước dòng chưa hash-chain.
    entry_hash    text,
    prev_hash     text
);

-- verify_audit_chain duyệt theo id tăng dần; log_mcp_event đọc dòng cuối để
-- lấy prev_hash. Cả hai đều đi theo id nên PK đã đủ, không cần index thêm.
```

- [ ] **Step 2: Viết test thất bại cho `assert_log_table_ready`**

Tạo `backend/tests/mcp/test_audit_log_table.py`:

```python
"""Vệt kiểm toán MCP: bảng phải CÓ THẬT, và thiếu thì phải nổ to.

Bối cảnh: mcp_call_log chưa từng tồn tại trong database Youdoo, và
log_mcp_event nuốt mọi lỗi ghi nên cả cơ chế chết im lặng suốt. Lưới duy
nhất chặn được chuyện đó tái diễn là kiểm lúc khởi động."""
import importlib
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


@pytest.fixture
def event_log_mod():
    sys.path.insert(0, str(MCP_DIR))
    try:
        import event_log
        yield importlib.reload(event_log)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_khong_co_dsn_thi_im_lang(event_log_mod, monkeypatch):
    """Không cấu hình DATABASE_URL = tắt log, là thiết kế có chủ ý của
    event_log. Không được biến nó thành lỗi khởi động."""
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", None)
    event_log_mod.assert_log_table_ready()          # không được ném


def test_co_dsn_ma_thieu_bang_thi_nem(event_log_mod, monkeypatch):
    """Đúng trạng thái thật của hệ thống trước đợt này."""
    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (False,)

    class FakeConn:
        def cursor(self): return FakeCursor()

    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: FakeConn())
    with pytest.raises(RuntimeError, match="002_mcp_call_log.sql"):
        event_log_mod.assert_log_table_ready()


def test_co_dsn_va_co_bang_thi_qua(event_log_mod, monkeypatch):
    """Đối chứng: nếu hàm ném vô điều kiện thì test trên vẫn xanh giả."""
    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (True,)

    class FakeConn:
        def cursor(self): return FakeCursor()

    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: FakeConn())
    event_log_mod.assert_log_table_ready()          # không được ném


def test_server_goi_kiem_bang_va_chi_trong_main():
    """Hai khẳng định, mỗi cái chặn một hướng hỏng khác nhau.

    (1) Gỡ lời gọi khỏi server.py ⇒ ĐỎ. Không có nó thì hàm trên có thể đúng
        hoàn toàn mà chẳng ai gọi.
    (2) Lời gọi phải nằm SAU `if __name__ == "__main__":`. Ở cấp module nó
        làm 8 file test + evals/role_config.py — những chỗ `import server`
        chỉ để đọc registry tool — nổ khi chưa chạy migration, tức đúng
        trạng thái của mọi lần checkout mới."""
    src = (MCP_DIR / "server.py").read_text(encoding="utf-8")
    assert "assert_log_table_ready()" in src

    vi_tri_main = src.index('if __name__ == "__main__":')
    vi_tri_goi = src.index("assert_log_table_ready()")
    assert vi_tri_goi > vi_tri_main, \
        "lời gọi nằm ở cấp module — sẽ làm mọi `import server` nổ khi chưa " \
        "chạy migration"


def test_import_server_khong_can_bang(monkeypatch):
    """Đối chứng bằng hành vi, không bằng vị trí văn bản: `import server`
    phải chạy được kể cả khi bảng chưa có. Đây là hồi quy thật — 8 file test
    hiện hành phụ thuộc vào nó."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://khong-ton-tai/x")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        assert server.mcp._tool_manager._tools, "registry rỗng — import hỏng"
    finally:
        sys.path.remove(str(MCP_DIR))
```

- [ ] **Step 3: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/mcp/test_audit_log_table.py -m "not integration and not live" -v`
Expected: FAIL — `AttributeError: module 'event_log' has no attribute 'assert_log_table_ready'` ở 3 test đầu, và `ValueError: substring not found` / `AssertionError` ở `test_server_goi_kiem_bang_va_chi_trong_main`. `test_import_server_khong_can_bang` XANH ngay từ đầu (hiện chưa có gì chặn import) — nó là lưới hồi quy cho Step 5, không phải test dẫn dắt.

- [ ] **Step 4: Cài `assert_log_table_ready`**

Thêm vào `mcp-servers/odoo/event_log.py`, sau `_get_db`:

```python
def assert_log_table_ready() -> None:
    """Fail-loud khi có DSN mà thiếu bảng — gọi MỘT LẦN lúc khởi động.

    Vì sao cần: log_mcp_event nuốt MỌI lỗi ghi (đúng — log không được làm
    hỏng tool), nên thiếu bảng là trạng thái hoàn toàn im lặng. Đo 2026-08-14:
    mcp_call_log chưa từng tồn tại và không ai biết, suốt từ ngày port.

    Không có DATABASE_URL ⇒ trả về ngay: "không cấu hình = tắt log" là thiết
    kế có chủ ý của module này, không phải lỗi.
    """
    if not DATABASE_URL:
        return
    conn = _get_db()
    if conn is None:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.mcp_call_log') IS NOT NULL")
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "Thiếu bảng mcp_call_log — vệt kiểm toán MCP sẽ im lặng không "
                "ghi gì. Chạy backend/migrations/002_mcp_call_log.sql trên "
                "database ở DATABASE_URL rồi khởi động lại.")
```

- [ ] **Step 5: Nối vào `server.py` — trong `__main__`, KHÔNG ở cấp module**

⚠️ **Đây là chỗ dễ làm sai nhất trong cả plan.** Lời gọi phải nằm trong khối `if __name__ == "__main__":`, không phải ở cấp module.

Lý do (đã kiểm 2026-08-15): **tám file test cộng `backend/evals/role_config.py` đều chạy `import server`** chỉ để đọc registry tool — `test_close_activity_tool.py`, `test_find_my_activities_tool.py`, `test_log_activity_tool.py`, `test_mail_role_scope_wiring.py`, `test_odoo_tool_boundary.py`, `test_eval_role_config.py`, và `role_config._mcp_tool_fns`. Đặt lời gọi ở cấp module thì mọi chỗ đó nổ khi có `DATABASE_URL` mà chưa chạy migration — tức đúng trạng thái của mọi lần checkout mới, và của chính CI.

Tiến trình thật khởi động bằng `python server.py` (`start-dev.ps1:125`), nên `__main__` bắn đúng cho tiến trình phục vụ request và chỉ cho nó.

Thêm `import logging` cạnh `import os`/`import sys`, rồi sửa khối cuối file:

```python
# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # CẢ HAI dòng dưới đây thuộc về ĐIỂM VÀO TIẾN TRÌNH, không phải cấp
    # module: 8 file test và evals/role_config.py `import server` chỉ để đọc
    # registry tool. Ở cấp module, assert_log_table_ready sẽ làm tất cả nổ
    # khi chưa chạy migration, và basicConfig sẽ gắn handler vào root logger
    # của tiến trình pytest.
    #
    # stderr mỗi tiến trình MCP được start-dev.ps1 chuyển vào
    # logs/mcp-odoo-<vai>_err.log. Không có dòng basicConfig này,
    # logger.exception chỉ tới đó nhờ handler `lastResort` mặc định của
    # Python — đúng ngẫu nhiên, và im lặng mất nếu ai đó thêm cấu hình khác.
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Thà không lên còn hơn lên sai — cùng triết lý assert_embedding_marker.
    from event_log import assert_log_table_ready

    assert_log_table_ready()

    mcp.run(transport="sse")
```

- [ ] **Step 6: Chạy lại — phải XANH**

Run: `pytest tests/mcp/test_audit_log_table.py -m "not integration and not live" -v`
Expected: PASS, 5 passed.

- [ ] **Step 7: Chạy toàn bộ để chắc không vỡ gì**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS, không có test nào mới đỏ.

- [ ] **Step 8: Commit**

```bash
git add backend/migrations/002_mcp_call_log.sql mcp-servers/odoo/event_log.py mcp-servers/odoo/server.py backend/tests/mcp/test_audit_log_table.py
git commit -m "feat(audit): dựng bảng mcp_call_log + fail-loud khi thiếu

Bảng chưa từng tồn tại; log_mcp_event nuốt mọi lỗi ghi nên cả vệt kiểm
toán chết im lặng từ ngày port. Thiếu bảng giờ chặn khởi động."
```

---

## Task 2: Phân biệt "bảng rỗng" với "chuỗi nguyên vẹn" + vòng ghi khép kín

**Files:**
- Modify: `mcp-servers/odoo/verify_audit_chain.py`
- Modify: `docs/getting-started.md`
- Test: `backend/tests/mcp/test_audit_log_table.py` (thêm vào file Task 1 tạo)

**Interfaces:**
- Consumes: `verify_audit_chain.verify(rows) -> tuple[bool, str]` (đã có), `event_log.log_mcp_event` (đã có), `audit_chain.compute_entry_hash` (đã có)
- Produces: `verify_audit_chain.verify` giữ nguyên chữ ký nhưng trả `(False, …)` khi `rows` rỗng.

**Bối cảnh:** `verify()` hiện duyệt danh sách rỗng, không vào vòng lặp nào, rồi trả `(True, "OK — 0 dòng, chuỗi nguyên vẹn")` và `main()` thoát 0. Nghĩa là công cụ kiểm tra tính toàn vẹn báo "toàn vẹn" trên đúng cái trạng thái hỏng mà Task 1 vừa sửa.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/mcp/test_audit_log_table.py`:

```python
@pytest.fixture
def verify_mod():
    sys.path.insert(0, str(MCP_DIR))
    try:
        import verify_audit_chain
        yield importlib.reload(verify_audit_chain)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_bang_rong_khong_phai_nguyen_ven(verify_mod):
    """Bảng rỗng là "chưa có gì để kiểm", KHÔNG phải bằng chứng toàn vẹn.
    Trước bản sửa này verify([]) trả (True, "... chuỗi nguyên vẹn") và main()
    thoát 0 — tức công cụ báo OK trên đúng trạng thái hỏng."""
    ok, msg = verify_mod.verify([])
    assert ok is False
    assert "rỗng" in msg or "không có dòng" in msg
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/mcp/test_audit_log_table.py::test_bang_rong_khong_phai_nguyen_ven -m "not integration and not live" -v`
Expected: FAIL — `assert True is False`.

- [ ] **Step 3: Sửa `verify`**

Trong `mcp-servers/odoo/verify_audit_chain.py`, chèn ngay đầu thân hàm `verify`, trước `prev = audit_chain.GENESIS_HASH`:

```python
    if not rows:
        # Danh sách rỗng đi hết vòng lặp mà không kiểm gì, nên bản cũ trả
        # (True, "OK — 0 dòng") — công cụ kiểm toàn vẹn báo toàn vẹn trên
        # đúng trạng thái mcp_call_log chưa từng ghi được dòng nào.
        return False, ("Bảng rỗng — không có dòng nào đã hash-chain để kiểm. "
                       "Đây KHÔNG phải bằng chứng toàn vẹn.")
```

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `pytest tests/mcp/test_audit_log_table.py -m "not integration and not live" -v`
Expected: PASS, 6 passed.

- [ ] **Step 5: Viết test tích hợp cho vòng ghi khép kín**

Thêm vào cùng file:

```python
@pytest.mark.integration
def test_ghi_roi_doc_lai_duoc(event_log_mod):
    """Test DUY NHẤT chứng minh vòng ghi khép kín: gọi log_mcp_event rồi ĐỌC
    LẠI dòng vừa ghi và tính lại hash.

    Đây chính là thứ đã vắng mặt suốt và là lý do cả cơ chế chết mà không ai
    biết — mọi test khác chỉ khẳng định hàm ĐƯỢC GỌI, không khẳng định có
    dòng nào ra tới database.

    Cần DATABASE_URL thật và migration 002 đã chạy. Chạy riêng:
        pytest tests/mcp/test_audit_log_table.py -m integration
    """
    import psycopg2

    import audit_chain

    if not event_log_mod.DATABASE_URL:
        pytest.skip("cần DATABASE_URL")

    dau = "test-ghi-doc-lai"
    event_log_mod.log_mcp_event("tool_error", tool_name=dau,
                                error_code="E500", error_message="probe")

    conn = psycopg2.connect(event_log_mod.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT created_at, event_type, caller, tool_name, model_name,"
                " operation, duration_ms, error_code, error_message,"
                " entry_hash, prev_hash FROM mcp_call_log"
                " WHERE tool_name = %s ORDER BY id DESC LIMIT 1", (dau,))
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, "không có dòng nào ra tới database"
    (created_at, event_type, caller, tool_name, model_name, operation,
     duration_ms, error_code, error_message, entry_hash, prev_hash) = row
    assert error_message == "probe"
    assert audit_chain.compute_entry_hash(
        prev_hash, created_at, event_type, caller, tool_name, model_name,
        operation, duration_ms, error_code, error_message) == entry_hash
```

- [ ] **Step 6: Xác nhận test tích hợp KHÔNG chạy ở cổng mặc định**

Run: `pytest tests/mcp/test_audit_log_table.py -m "not integration and not live" -q`
Expected: PASS, 6 passed — dòng tổng kết phải có `1 deselected`.

- [ ] **Step 7: Bổ sung `docs/getting-started.md`**

Chèn mục sau vào bước cài đặt database, **trước** bước khởi động dịch vụ:

```markdown
### Chạy migration

Repo **không có runner migration tự động**. Các file trong
`backend/migrations/` phải chạy tay một lần, theo thứ tự số:

```bash
psql "$DATABASE_URL" -f backend/migrations/001_llm_usage.sql
psql "$DATABASE_URL" -f backend/migrations/002_mcp_call_log.sql
```

Cả hai đều `CREATE TABLE IF NOT EXISTS` nên chạy lại nhiều lần vô hại.

`001_llm_usage.sql` — sổ ngân sách LLM. `002_mcp_call_log.sql` — vệt kiểm
toán mọi lệnh gọi MCP.

**Quên chạy `002` thì tiến trình MCP từ chối khởi động**, kèm thông báo nêu
đúng tên file cần chạy. Đó là chủ đích: bảng này từng thiếu suốt một thời
gian dài mà không ai biết, vì `log_mcp_event` nuốt mọi lỗi ghi để không làm
hỏng tool.
```

⚠️ `001_llm_usage.sql` hiện **không được nhắc ở đâu** trong tài liệu, dù bảng của nó có thật trong database — tức nó đã được chạy tay và không ai ghi lại. Đưa cả hai vào là một phần của việc sửa, không phải tiện tay thêm.

- [ ] **Step 8: Commit**

```bash
git add mcp-servers/odoo/verify_audit_chain.py backend/tests/mcp/test_audit_log_table.py docs/getting-started.md
git commit -m "fix(audit): bảng rỗng không còn được báo là chuỗi nguyên vẹn

Thêm test tích hợp ghi-rồi-đọc-lại: lưới duy nhất chứng minh vòng ghi
khép kín, thứ đã vắng mặt suốt."
```

---

## Task 3: Helper tầng MCP + 21 điểm gọi

**Files:**
- Modify: `mcp-servers/odoo/helpers.py`
- Modify: `mcp-servers/odoo/tools/accounting.py` (5), `crm.py` (3), `inventory.py` (1), `mrp.py` (5), `purchase.py` (4), `sales.py` (3)
- Test: `backend/tests/mcp/test_khong_ro_loi_mcp.py` (tạo mới)

**Interfaces:**
- Consumes: `event_log.log_mcp_event` (Task 1 đã đảm bảo bảng tồn tại), `helpers.envelope` (đã có)
- Produces: `helpers.fail(tool_name: str, display: str, exc: Exception) -> str` — trả về đúng chuỗi JSON mà `envelope(False, display)` trả về.

**Bối cảnh:** `helpers.py` hiện **không có logger** (chỉ `import json`, `datetime`, `odoo_call`). Phải thêm. Không có vòng import: `event_log` chỉ phụ thuộc `audit_chain` và `config`, không phụ thuộc `helpers`.

**Vì sao ghi log ở đây dù `odoo_call.odoo()` đã ghi:** `odoo()` chỉ ghi lỗi đi qua nó. `except Exception` ở tầng tool bắt rộng hơn — bug Python của chính tool (`KeyError` trong helper resolve, lỗi parse). Bịt chúng mà không ghi lại sẽ biến cả một hạng lỗi thành vô hình. Và ghi **cả hai đích** vì `log_mcp_event` im lặng không làm gì khi thiếu `DATABASE_URL`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/mcp/test_khong_ro_loi_mcp.py`:

```python
"""Tầng MCP không được nội suy exception vào câu trả lời người dùng.

Đo 2026-08-14: lỗi Odoo thật liệt kê NGUYÊN BẢN ĐỒ PHÂN QUYỀN — kể cả tên
nhóm tự tạo của dự án ("Youdoo AI / Read Only") — nên đây là lộ thông tin,
không phải chuyện thẩm mỹ."""
import re
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"
TOOLS_DIR = MCP_DIR / "tools"

# Bắt mọi nội suy f-string của biến exception thông dụng: {e}, {exc}, {err},
# kể cả có định dạng phía sau ({e!r}, {e:s}).
RO_LOI = re.compile(r"\{\s*(e|exc|err)\s*[!:}]")


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not TOOLS_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


def _cho_ro(path: Path):
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if RO_LOI.search(line):
            out.append(f"{path.name}:{i}: {line.strip()}")
    return out


def test_khong_tool_mcp_nao_ro_exception():
    """Đo trước khi sửa: 21 chỗ trên 6 file."""
    ro = [m for p in sorted(TOOLS_DIR.glob("*.py")) for m in _cho_ro(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_fail_ghi_ca_hai_dich_va_khong_lo_gi(monkeypatch):
    """Câu trả về phải sạch, VÀ nguyên văn lỗi phải tới cả hai đích. Thiếu vế
    thứ hai thì bản sửa chỉ là giấu lỗi đi."""
    sys.path.insert(0, str(MCP_DIR))
    try:
        import helpers
        import json as _json

        da_ghi = {}
        monkeypatch.setattr(helpers, "log_mcp_event",
                            lambda *a, **k: da_ghi.update(k))
        da_log = []
        monkeypatch.setattr(helpers.logger, "exception",
                            lambda *a, **k: da_log.append(a))

        exc = ValueError("Youdoo AI / Read Only")
        raw = helpers.fail("post_invoice", "Lỗi khi tạo hóa đơn — thao tác "
                                           "chưa được thực hiện.", exc)
        data = _json.loads(raw)

        assert data["ok"] is False
        assert "Youdoo AI" not in data["display"]
        assert "ValueError" not in data["display"]
        assert "Youdoo AI / Read Only" in da_ghi["error_message"]
        assert da_ghi["tool_name"] == "post_invoice"
        assert da_log, "không ghi vào logger tiến trình — thiếu DATABASE_URL " \
                       "thì lỗi sẽ biến mất hoàn toàn"
    finally:
        sys.path.remove(str(MCP_DIR))
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/mcp/test_khong_ro_loi_mcp.py -m "not integration and not live" -v`
Expected: FAIL — test đầu liệt kê 21 dòng; test sau `AttributeError: module 'helpers' has no attribute 'fail'`.

- [ ] **Step 3: Thêm `fail` vào `helpers.py`**

Thêm vào đầu file, cạnh các import sẵn có:

```python
import logging

from event_log import log_mcp_event

logger = logging.getLogger(__name__)
```

Và thêm hàm, ngay sau `envelope`:

```python
def fail(tool_name: str, display: str, exc: Exception) -> str:
    """Ghi nguyên văn lỗi vào log tiến trình VÀ vệt kiểm toán; trả người dùng
    câu KHÔNG lộ gì.

    Ghi cả hai đích có chủ ý: log_mcp_event im lặng không làm gì khi thiếu
    DATABASE_URL, nên nếu chỉ dựa vào nó thì môi trường không cấu hình DB sẽ
    làm lỗi biến mất hoàn toàn — đúng lỗ hổng đợt này đi đóng.

    Nguyên văn lỗi Odoo KHÔNG được vào `display`: đo 2026-08-14, lỗi phân
    quyền của Odoo liệt kê đầy đủ danh sách nhóm được phép, kể cả nhóm tự tạo
    của dự án.
    """
    detail = f"{type(exc).__name__}: {exc}"
    logger.exception("tool %s thất bại: %s", tool_name, detail)
    log_mcp_event("tool_error", tool_name=tool_name, error_code="E500",
                  error_message=detail)
    return envelope(False, display)
```

- [ ] **Step 4: Đổi 21 điểm gọi**

Trong 6 file `mcp-servers/odoo/tools/{accounting,crm,inventory,mrp,purchase,sales}.py`, đổi mọi dòng dạng

```python
        return envelope(False, f"<tiền tố>: {e}")
```

thành

```python
        return fail("<tên tool của hàm đang ở trong>",
                    f"<tiền tố> — thao tác chưa được thực hiện. "
                    f"Nếu lặp lại, báo quản trị viên.", e)
```

Giữ **nguyên văn** phần `<tiền tố>`, kể cả biến nội suy trong đó (`{order_ref}` v.v.). `<tên tool>` là tên hàm mang `@mcp.tool()` chứa dòng đó. Thêm `fail` vào dòng `from helpers import ...` sẵn có ở mỗi file.

Ví dụ cụ thể, `tools/accounting.py:140`:

```python
    # trước
        return envelope(False, f"Lỗi khi tạo hóa đơn cho đơn {order_ref}: {e}")
    # sau
        return fail("create_invoice_from_order",
                    f"Lỗi khi tạo hóa đơn cho đơn {order_ref} — thao tác chưa "
                    f"được thực hiện. Nếu lặp lại, báo quản trị viên.", e)
```

- [ ] **Step 5: Chạy lại — phải XANH**

Run: `pytest tests/mcp/test_khong_ro_loi_mcp.py -m "not integration and not live" -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS. Nếu có test đỏ vì khớp chuỗi lỗi cũ, **dừng lại và báo cáo** — đừng sửa test cho vừa nếu chưa chắc chuỗi mới đúng ý spec.

- [ ] **Step 7: Commit**

```bash
git add mcp-servers/odoo/helpers.py mcp-servers/odoo/tools/ backend/tests/mcp/test_khong_ro_loi_mcp.py
git commit -m "fix(mcp): 21 tool không còn rò nguyên văn lỗi Odoo

Lỗi phân quyền Odoo liệt kê nguyên bản đồ nhóm quyền, kể cả nhóm tự tạo
của dự án. Nguyên văn giờ vào logger + mcp_call_log."
```

---

## Task 4: Helper tầng đọc + 44 điểm gọi

**Files:**
- Modify: `backend/src/erp_query/envelope.py`
- Modify: `backend/src/erp_query/accounting.py` (9), `crm.py` (3), `inventory.py` (7), `mrp.py` (9), `purchase.py` (8), `resolve.py` (2), `sales.py` (6)
- Test: `backend/tests/erp_query/test_khong_ro_loi_doc.py` (tạo mới)

**Interfaces:**
- Consumes: `erp_query.envelope.err(message, display=None) -> dict` (đã có)
- Produces: `erp_query.envelope.fail_read(where: str, display: str, exc: Exception) -> dict` — trả `{"status": "error", "data": None, "display": display, "error": display}`. ⚠️ Trường `error` **cũng** phải sạch: nó là chuỗi, đi cùng dict ra ngoài, và không có gì đảm bảo nơi nhận không hiển thị nó.

**Bối cảnh — đây là tầng NẶNG NHẤT, không phải MCP.** `erp_query/gateway.py:32-36` gọi thẳng Odoo và **không bọc gì**, nên `xmlrpc.client.Fault` bay nguyên vẹn lên `erp_query/*.py` rồi vào `err(f"…: {e}")`. Đường ĐỌC là đường được dùng nhiều nhất trong toàn trợ lý, và nó rò **đúng nguyên văn** đoạn liệt kê nhóm quyền đo được ở spec §1.3 — trong khi tầng MCP chỉ rò gián tiếp.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/erp_query/test_khong_ro_loi_doc.py`:

```python
"""Đường ĐỌC không được nội suy exception vào câu trả lời.

Tầng này nặng nhất trong bốn tầng: gateway._call gọi thẳng Odoo và không bọc
gì, nên Fault bay nguyên vẹn lên đây. 44 chỗ, đo 2026-08-14."""
import re
from pathlib import Path

QUERY_DIR = Path(__file__).resolve().parents[2] / "src" / "erp_query"
RO_LOI = re.compile(r"\{\s*(e|exc|err)\s*[!:}]")


def _cho_ro(path: Path):
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if RO_LOI.search(line):
            out.append(f"{path.name}:{i}: {line.strip()}")
    return out


def test_khong_ham_doc_nao_ro_exception():
    ro = [m for p in sorted(QUERY_DIR.glob("*.py")) for m in _cho_ro(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_fail_read_sach_ca_display_lan_error(monkeypatch):
    """Cả HAI trường chuỗi phải sạch. `error` cũng đi ra ngoài trong cùng
    dict và không có gì đảm bảo nơi nhận không hiển thị nó."""
    from src.erp_query import envelope as env

    da_log = []
    monkeypatch.setattr(env.logger, "exception", lambda *a, **k: da_log.append(a))

    exc = ValueError("Youdoo AI / Read Only")
    res = env.fail_read("tra_lead", "Lỗi tra cứu lead/cơ hội — không lấy "
                                    "được dữ liệu.", exc)

    assert res["status"] == "error"
    assert res["data"] is None
    assert "Youdoo AI" not in res["display"]
    assert "Youdoo AI" not in res["error"]
    assert da_log, "không ghi log — bản sửa chỉ giấu lỗi đi"
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/erp_query/test_khong_ro_loi_doc.py -m "not integration and not live" -v`
Expected: FAIL — test đầu liệt kê 44 dòng; test sau `AttributeError: … has no attribute 'fail_read'`.

- [ ] **Step 3: Thêm `fail_read` vào `envelope.py`**

`envelope.py` **chưa có logger** (đã kiểm 2026-08-15) — thêm cả hai dòng đầu:

```python
import logging

logger = logging.getLogger(__name__)


def fail_read(where: str, display: str, exc: Exception) -> dict:
    """Ghi nguyên văn lỗi vào logger; trả câu KHÔNG lộ gì.

    Backend không có bảng kiểm toán riêng (dựng thêm một cái là quyết định
    kiến trúc khác), nên đích ở đây là logger tiến trình — logs/backend_err.log.

    `error` nhận CHÍNH `display`, không nhận nguyên văn lỗi: dict này đi ra
    ngoài nguyên vẹn và không có gì đảm bảo nơi nhận chỉ hiển thị `display`.
    """
    logger.exception("%s thất bại: %s: %s", where, type(exc).__name__, exc)
    return err(display, display)
```

- [ ] **Step 4: Đổi 44 điểm gọi**

Trong 7 file `backend/src/erp_query/{accounting,crm,inventory,mrp,purchase,resolve,sales}.py`, đổi mọi dòng dạng

```python
        return err(f"<tiền tố>: {e}")
```

thành

```python
        return fail_read("<tên hàm đang ở trong>",
                         f"<tiền tố> — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
```

Giữ **nguyên văn** `<tiền tố>`. Thêm `fail_read` vào dòng import `envelope` sẵn có ở mỗi file.

Ví dụ cụ thể, `erp_query/crm.py:92`:

```python
    # trước
        return err(f"Lỗi tra việc được giao: {e}")
    # sau
        return fail_read("list_my_activities",
                         f"Lỗi tra việc được giao — không lấy được dữ liệu. "
                         f"Nếu lặp lại, báo quản trị viên.", e)
```

- [ ] **Step 5: Chạy lại — phải XANH**

Run: `pytest tests/erp_query/test_khong_ro_loi_doc.py -m "not integration and not live" -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/erp_query/ backend/tests/erp_query/test_khong_ro_loi_doc.py
git commit -m "fix(erp_query): 44 điểm đọc không còn rò nguyên văn Fault Odoo

Tầng nặng nhất trong bốn: gateway gọi thẳng Odoo, không bọc gì, nên Fault
bay nguyên vẹn ra người dùng trên chính đường được dùng nhiều nhất."
```

---

## Task 5: Helper tầng điều phối + 23 + 1 điểm gọi

**Files:**
- Modify: `backend/src/agents/create_order.py` (thêm helper + 1 điểm gọi)
- Modify: `backend/src/agents/bom_write.py` (2), `crm_write.py` (4), `edit_order.py` (2), `inventory_write.py` (3), `invoice_write.py` (2), `mail_write.py` (2), `mrp_write.py` (1), `nodes.py` (1), `purchase_write.py` (3), `returns_write.py` (2)
- Modify: `backend/skills/bao-gia-chiet-khau/logic.py` (1)
- Test: `backend/tests/agents/test_khong_ro_loi_ghi.py` (tạo mới)

**Interfaces:**
- Consumes: `create_order._msg(text: str) -> dict` (đã có, `create_order.py:67`)
- Produces: `create_order.fail_write(where: str, display: str, exc: Exception) -> dict` — trả `_msg(display)`.

**Bối cảnh:** `_msg` định nghĩa **một chỗ duy nhất** ở `create_order.py:67`; 8 coordinator khác import lại từ đó (`from .create_order import … _msg …`). Helper mới đặt ngay cạnh nó nên mọi coordinator dùng được qua đúng đường import sẵn có.

⚠️ `skills/bao-gia-chiet-khau/logic.py` nằm **ngoài** cây `src/`, được nạp động bởi `skill_loader`, nên **không import được** helper trên. Xử lý tại chỗ theo cùng khuôn: `logging.getLogger(__name__).exception(...)` rồi trả chuỗi sạch.

⚠️ **GIỮ NGUYÊN 2 chỗ ở `skill_manifest.py`** (dòng 83 và 106) — đó là `raise SkillManifestError`, fail-loud lúc nạp cấu hình, hướng tới lập trình viên. Đếm 25 chỗ khớp `{e}` trong `src/agents/`, trừ 2 chỗ đó còn **23**.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_khong_ro_loi_ghi.py`:

```python
"""Tầng điều phối ghi không được nội suy exception vào tin nhắn trả về.

Miễn trừ có chủ ý: skill_manifest.py raise SkillManifestError(f"...{e}") là
fail-loud lúc NẠP CẤU HÌNH, hướng tới lập trình viên, không đi ra người dùng.
Miễn trừ ghi tường minh ở đây chứ không im lặng bỏ qua."""
import re
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "agents"
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
RO_LOI = re.compile(r"\{\s*(e|exc|err)\s*[!:}]")

MIEN_TRU = {
    "skill_manifest.py": "raise SkillManifestError lúc nạp SKILL.md — "
                         "fail-loud cho lập trình viên, không ra người dùng",
}


def _cho_ro(path: Path):
    if path.name in MIEN_TRU:
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if RO_LOI.search(line):
            out.append(f"{path.name}:{i}: {line.strip()}")
    return out


def test_khong_coordinator_nao_ro_exception():
    ro = [m for p in sorted(AGENTS_DIR.glob("*.py")) for m in _cho_ro(p)]
    ro += [m for p in sorted(SKILLS_DIR.rglob("*.py")) for m in _cho_ro(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_mien_tru_van_con_that(monkeypatch):
    """Đối chứng cho danh sách miễn trừ: nếu skill_manifest.py hết chỗ khớp
    thì miễn trừ đã thành rác và phải gỡ, không để nó âm thầm che file khác
    trùng tên về sau."""
    src = (AGENTS_DIR / "skill_manifest.py").read_text(encoding="utf-8")
    assert RO_LOI.search(src), \
        "skill_manifest.py không còn chỗ nào khớp — gỡ khỏi MIEN_TRU"


def test_fail_write_sach_va_co_log(monkeypatch):
    from src.agents import create_order as co

    da_log = []
    monkeypatch.setattr(co.logger, "exception", lambda *a, **k: da_log.append(a))

    exc = ValueError("Youdoo AI / Read Only")
    res = co.fail_write("tao_don", "Lỗi khi tạo đơn — thao tác chưa được "
                                   "thực hiện.", exc)
    noi_dung = res["messages"][-1].content

    assert "Youdoo AI" not in noi_dung
    assert "ValueError" not in noi_dung
    assert da_log, "không ghi log — bản sửa chỉ giấu lỗi đi"
```

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/agents/test_khong_ro_loi_ghi.py -m "not integration and not live" -v`
Expected: FAIL — test đầu liệt kê 24 dòng (23 ở `src/agents/` + 1 ở `skills/`); test cuối `AttributeError: … has no attribute 'fail_write'`.

- [ ] **Step 3: Thêm `fail_write` vào `create_order.py`**

`create_order.py` **chưa có logger** (đã kiểm 2026-08-15) — thêm `import logging` cạnh các import sẵn có và `logger = logging.getLogger(__name__)` ở cấp module, rồi thêm hàm ngay sau `_msg`:

```python
def fail_write(where: str, display: str, exc: Exception) -> dict:
    """Ghi nguyên văn lỗi vào logger; trả người dùng tin nhắn KHÔNG lộ gì.

    Đặt cạnh _msg vì _msg là định nghĩa DUY NHẤT trong cây agents (8
    coordinator khác import lại từ đây), nên helper này đi theo đúng đường
    import sẵn có, không tạo module mới.

    Đích là logger tiến trình (logs/backend_err.log): backend không có bảng
    kiểm toán riêng, và dựng thêm một cái là quyết định kiến trúc khác.
    """
    logger.exception("%s thất bại: %s: %s", where, type(exc).__name__, exc)
    return _msg(display)
```

- [ ] **Step 4: Đổi 23 điểm gọi trong `src/agents/`**

Đổi mọi dòng dạng

```python
            return _msg(f"<tiền tố>: {e}")
```

thành

```python
            return fail_write("<tên hàm/node đang ở trong>",
                              f"<tiền tố> — thao tác chưa được thực hiện. "
                              f"Nếu lặp lại, báo quản trị viên.", e)
```

Giữ nguyên văn `<tiền tố>`. Thêm `fail_write` vào dòng `from .create_order import (…)` sẵn có ở mỗi file. Trong chính `create_order.py` thì gọi trực tiếp.

- [ ] **Step 5: Đổi 1 điểm gọi trong skill**

`backend/skills/bao-gia-chiet-khau/logic.py:135`:

```python
    # trước
                return f"Lỗi khi tạo báo giá: {e}"
    # sau
                logging.getLogger(__name__).exception(
                    "tao_bao_gia thất bại: %s: %s", type(e).__name__, e)
                return ("Lỗi khi tạo báo giá — thao tác chưa được thực hiện. "
                        "Nếu lặp lại, báo quản trị viên.")
```

Thêm `import logging` ở đầu file nếu chưa có. Không import từ `src/` — module này được `skill_loader` nạp động từ ngoài cây `src/`.

- [ ] **Step 6: ĐO LẠI danh sách test khớp chuỗi, rồi mới sửa**

Spec §4.1 yêu cầu đo lại tại thời điểm sửa chứ không dùng lại con số viết sẵn — chính đợt này đã một lần đếm thiếu (21 vs 89). Chạy:

```bash
cd backend && grep -rn '"Lỗi khi\|Lỗi tra\|startswith("Lỗi' tests/ --include=*.py
```

Nếu kết quả **nhiều hơn** hai file nêu dưới, **dừng và báo cáo** — có test khớp chuỗi mà plan này không biết.

`backend/tests/agents/test_skill_bao_gia_chiet_khau_flow.py:320` hiện là
`assert res.startswith("Lỗi khi tạo báo giá:")` — dấu hai chấm không còn.
Đổi thành:

```python
    assert res.startswith("Lỗi khi tạo báo giá")
    assert "—" in res and "báo quản trị viên" in res
    assert "ValueError" not in res and "Traceback" not in res
```

`backend/tests/agents/test_create_order_node.py:312` (`assert "Lỗi khi tạo đơn" in …`) **không cần đổi** — quy tắc giữ nguyên tiền tố nên nó vẫn khớp. Chạy để xác nhận chứ đừng sửa mò.

- [ ] **Step 7: Chạy lại — phải XANH**

Run: `pytest tests/agents/test_khong_ro_loi_ghi.py -m "not integration and not live" -v`
Expected: PASS, 3 passed.

- [ ] **Step 8: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/ backend/skills/ backend/tests/agents/
git commit -m "fix(agents): 24 điểm điều phối không còn rò exception

Giữ nguyên 2 chỗ raise ở skill_manifest.py — fail-loud lúc nạp cấu hình,
hướng tới lập trình viên. Miễn trừ ghi tường minh kèm đối chứng."
```

---

## Task 6: Lưới quét theo LOẠI TRỪ, phủ mọi cây nguồn

**Files:**
- Test: `backend/tests/mcp/test_khong_ro_loi_exception.py` (tạo mới)

**Interfaces:**
- Consumes: không có — test này chỉ đọc file nguồn.
- Produces: không có.

**Bối cảnh — vì sao loại trừ chứ không liệt kê:** ba test ở Task 3/4/5 mỗi cái quét **một** thư mục đã biết. Đó chính là cơ chế đã khiến nợ gốc chỉ đếm 21/89 chỗ: người viết liệt kê những thư mục mình đang nghĩ tới. Thêm một cây nguồn thứ năm và cả ba test kia vẫn xanh. Lưới này duyệt **mọi** `*.py` từ gốc repo trừ một danh sách nhỏ và ổn định, nên cây nguồn mới **tự động được phủ** — hụt về phía an toàn.

Ba test kia **giữ lại**, không xoá: chúng hẹp hơn nhưng chẩn đoán tốt hơn (biết ngay tầng nào rò).

- [ ] **Step 1: Viết lưới**

Tạo `backend/tests/mcp/test_khong_ro_loi_exception.py`:

```python
"""Lưới cuối: KHÔNG cây nguồn nào được nội suy exception ra người dùng.

Quét theo LOẠI TRỪ, không theo liệt kê. Liệt kê thư mục nguồn chính là cơ
chế đã khiến nợ gốc chỉ đếm 21/89 chỗ — người viết liệt kê đúng những thư
mục mình đang nghĩ tới. Loại trừ thì cây nguồn mới tự động được phủ.

Phép thử phá bắt buộc (chạy tay khi sửa file này): thêm lại một chỗ rò vào
MỖI tầng trong bốn tầng — mcp-servers/odoo/tools/, backend/src/erp_query/,
backend/src/agents/, backend/skills/ — lưới phải ĐỎ ở cả bốn. Lưới chỉ đỏ ở
ba tầng là lưới nói dối."""
import re
from pathlib import Path

GOC = Path(__file__).resolve().parents[3]
RO_LOI = re.compile(r"\{\s*(e|exc|err)\s*[!:}]")

# Nhỏ và ổn định. Mọi thứ KHÔNG nằm ở đây đều bị quét — kể cả cây nguồn chưa
# tồn tại lúc viết dòng này.
BO_QUA_THU_MUC = {
    ".git", ".venv", "__pycache__", "node_modules",
    ".worktrees", ".claude", ".superpowers",
    "docs", "logs", "migrations",
    "tests",      # test được phép nhắc {e} trong chuỗi kỳ vọng
    "spikes",     # mã thử nghiệm, không phục vụ người dùng
}

# Miễn trừ theo từng file — nhưng khoá bằng SỐ LƯỢNG, không phải bằng tên.
#
# Miễn trừ cả file là đúng cái bẫy nó đi đóng: thêm một chỗ rò MỚI vào file
# đã được miễn trừ thì lưới im lặng. Ghim số dòng khớp mong đợi ⇒ chỗ rò thứ
# n+1 làm lưới ĐỎ dù file nằm trong danh sách này.
#
# Cả sáu đều hướng tới lập trình viên / người vận hành, không tới người dùng
# chat. Đo 2026-08-15.
MIEN_TRU = {
    "backend/src/agents/skill_manifest.py": (
        2, "raise SkillManifestError lúc nạp SKILL.md — fail-loud cho lập "
           "trình viên, app không lên chứ không lên sai"),
    "backend/src/rag/embed.py": (
        1, "raise EmbeddingError — lỗi hạ tầng lúc index, không ra người dùng"),
    "backend/evals/role_config.py": (
        1, "RuntimeError nói rõ bộ đo thiếu biến môi trường nào — người chạy "
           "eval bằng CLI đọc, không phải người dùng chat"),
    "backend/evals/run_eval.py": (
        1, "print('INFRA ERROR: …') ra console của người chạy eval"),
    "backend/jobs/resilience.py": (
        1, "raise … from e trong job nền — đi vào log, không vào hội thoại"),
    "scripts/check_role_odoo_consistency.py": (
        1, "script rà quyền chạy tay; nguyên văn lỗi Odoo CHÍNH LÀ kết quả "
           "cần đọc của nó"),
}


def _moi_file_nguon():
    for path in GOC.rglob("*.py"):
        if any(phan in BO_QUA_THU_MUC for phan in path.relative_to(GOC).parts):
            continue
        yield path


def _khoa(path: Path) -> str:
    return path.relative_to(GOC).as_posix()


def test_khong_cay_nguon_nao_ro_exception():
    ro = []
    for path in sorted(_moi_file_nguon()):
        if _khoa(path) in MIEN_TRU:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RO_LOI.search(line):
                ro.append(f"{_khoa(path)}:{i}: {line.strip()}")
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_luoi_that_su_quet_du_bon_tang():
    """Đối chứng cho chính bộ lọc: nếu BO_QUA_THU_MUC nuốt nhầm một cây
    nguồn, test trên xanh giả mà không ai biết. Khẳng định cả bốn tầng đều
    thật sự có file được quét."""
    da_quet = {_khoa(p) for p in _moi_file_nguon()}
    for tien_to in ("mcp-servers/odoo/tools/",
                    "backend/src/erp_query/",
                    "backend/src/agents/",
                    "backend/skills/"):
        assert any(k.startswith(tien_to) for k in da_quet), \
            f"không file nào dưới {tien_to} được quét — bộ lọc nuốt nhầm"


def test_moi_mien_tru_dung_so_luong():
    """Khoá danh sách miễn trừ theo SỐ LƯỢNG, hai chiều.

    Ít hơn mong đợi ⇒ miễn trừ đã thành rác, gỡ đi (để nó nằm lại là dựng
    sẵn chỗ núp cho một chỗ rò mới trong cùng file).
    Nhiều hơn ⇒ có chỗ rò MỚI trong file được miễn trừ — đúng lỗ hổng mà
    miễn trừ-cả-file gây ra, và là lý do test này đếm thay vì chỉ kiểm tồn
    tại."""
    lech = []
    for khoa, (mong_doi, ly_do) in MIEN_TRU.items():
        path = GOC / khoa
        if not path.exists():
            lech.append(f"{khoa}: file không còn tồn tại")
            continue
        that = sum(1 for l in path.read_text(encoding="utf-8").splitlines()
                   if RO_LOI.search(l))
        if that != mong_doi:
            lech.append(f"{khoa}: khớp {that} dòng, ghim {mong_doi} ({ly_do})")
    assert lech == [], "miễn trừ lệch thực tế:\n" + "\n".join(lech)
```

- [ ] **Step 2: Chạy — phải XANH ngay**

Run: `pytest tests/mcp/test_khong_ro_loi_exception.py -m "not integration and not live" -v`
Expected: PASS, 3 passed.

**Đo trước 2026-08-15 để bạn không bị bất ngờ:** quét toàn repo theo đúng bộ lọc trên cho ra **96** dòng khớp, không phải 89. Chênh lệch là 92 (89 chỗ ra người dùng + 3 chỗ `raise` nội bộ) cộng **4 chỗ nằm ngoài bốn tầng đã liệt kê** — `backend/evals/role_config.py`, `backend/evals/run_eval.py`, `backend/jobs/resilience.py`, `scripts/check_role_odoo_consistency.py`. Cả bốn hướng tới lập trình viên/người vận hành nên đã nằm sẵn trong `MIEN_TRU` với số lượng ghim.

Đây chính là điều lưới này tồn tại để làm, và nó đã chứng minh trên chính bản plan: bốn chỗ đó **không** nằm trong bất kỳ danh sách tầng nào tôi liệt kê được bằng cách nghĩ.

Nếu vẫn ĐỎ ở một file **ngoài** sáu file trong `MIEN_TRU`: nó vừa tìm ra chỗ rò thật mà ba task trước không quét tới. **Báo cáo, đừng thêm vào `MIEN_TRU`** — quyết định miễn trừ một cây nguồn mới là việc của controller, không phải của task này.

- [ ] **Step 3: Phép thử phá — tầng 1**

Thêm tạm vào cuối một hàm bất kỳ trong `mcp-servers/odoo/tools/sales.py`:
`msg = f"tạm {e}"` (trong một khối `except Exception as e:` sẵn có).

Run: `pytest tests/mcp/test_khong_ro_loi_exception.py::test_khong_cay_nguon_nao_ro_exception -m "not integration and not live" -q`
Expected: FAIL, nêu đúng `mcp-servers/odoo/tools/sales.py:<dòng>`. Hoàn nguyên.

- [ ] **Step 4: Phép thử phá — tầng 2**

Lặp lại y hệt với `backend/src/erp_query/sales.py`.
Expected: FAIL nêu đúng file đó. Hoàn nguyên.

- [ ] **Step 5: Phép thử phá — tầng 3**

Lặp lại y hệt với `backend/src/agents/crm_write.py`.
Expected: FAIL nêu đúng file đó. Hoàn nguyên.

- [ ] **Step 6: Phép thử phá — tầng 4**

Lặp lại y hệt với `backend/skills/bao-gia-chiet-khau/logic.py`.
Expected: FAIL nêu đúng file đó. Hoàn nguyên.

- [ ] **Step 7: Xác nhận đã hoàn nguyên sạch**

Run: `git status --short` rồi `pytest -m "not integration and not live" -q`
Expected: không còn thay đổi ngoài file test mới; toàn bộ XANH.

- [ ] **Step 8: Commit**

Ghi **kết quả bốn phép thử phá** vào thân commit — chúng là bằng chứng lưới đo thật, và người review sẽ hỏi.

```bash
git add backend/tests/mcp/test_khong_ro_loi_exception.py
git commit -m "test: lưới quét rò exception theo LOẠI TRỪ, phủ mọi cây nguồn

Liệt kê thư mục là cơ chế đã khiến nợ gốc chỉ đếm 21/89. Quét loại trừ
nên cây nguồn mới tự động được phủ.

Phép thử phá: thêm lại một chỗ rò vào mỗi tầng trong bốn tầng — lưới đỏ ở
cả bốn, nêu đúng file và dòng."
```

---

## Task 7: `mail.activity` vào bảng kiểm quyền

**Files:**
- Modify: `scripts/check_role_odoo_consistency.py`
- Test: `backend/tests/agents/test_close_activity_roles.py`

**Interfaces:**
- Consumes: `check_role_odoo_consistency.TOOL_ACCESS_MAP` (đã có)
- Produces: không có API mới.

**Bối cảnh, đo 2026-08-14:** cả `ai-warehouse` (uid 9) và `ai-accounting` (uid 10) **đọc được** `mail.activity` — không có lỗi sống cần sửa. Task này thuần là dựng lưới. Lý do nó đáng làm: cả hai vai trả **0 dòng của chính mình**, nên nếu quyền đọc hỏng thì kết quả trông y hệt "không có việc nào được giao" — không suy ra được từ kết quả rỗng.

`close_activity` khai `[("mail.activity","write")]` nhưng tool đó `search_read` **trước** khi ghi (`crm.py:272`). `find_my_activities` (`crm.py:330`) không có trong bảng nào cả.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/agents/test_close_activity_roles.py`, cạnh khẳng định sẵn có ở dòng 98-99:

```python
def test_close_activity_khai_ca_quyen_doc():
    """close_activity search_read mail.activity TRƯỚC khi action_feedback
    (crm.py:272) — bộ lọc chủ sở hữu là lớp cưỡng chế duy nhất, vì Odoo
    KHÔNG chặn một tài khoản đóng việc của người khác. Thiếu quyền đọc thì
    lớp đó sập, nên cặp read phải được khai."""
    import scripts.check_role_odoo_consistency as mod
    assert ("mail.activity", "read") in mod.TOOL_ACCESS_MAP["close_activity"]


def test_find_my_activities_co_trong_bang():
    """Tool CHỈ-ĐỌC nên nó lọt qua cả hai lưới: không ở roles.py (nên
    test_moi_tool_trong_roles_deu_duoc_bang_phu không phủ), không ở
    TOOL_ACCESS_MAP, không ở UNMAPPED_TOOLS."""
    import scripts.check_role_odoo_consistency as mod
    assert ("mail.activity", "read") in mod.TOOL_ACCESS_MAP["find_my_activities"]
```

⚠️ Import `scripts.check_role_odoo_consistency` theo đúng cách file test hiện hành đang làm (xem fixture `script_mod` trong `backend/tests/mcp/test_tool_access_map_drift.py`) — `scripts/` không phải package con của `backend/`.

- [ ] **Step 2: Chạy để chắc chắn ĐỎ**

Run: `pytest tests/agents/test_close_activity_roles.py -m "not integration and not live" -v`
Expected: FAIL — `assert ('mail.activity', 'read') in [('mail.activity', 'write')]` và `KeyError: 'find_my_activities'`.

- [ ] **Step 3: Sửa bảng**

Trong `scripts/check_role_odoo_consistency.py`, thay dòng `close_activity` và thêm dòng mới:

```python
    # action_feedback đặt active=False + state='done' trên chính bản ghi
    # mail.activity (đo 2026-08-14) — là "write", không phải "unlink".
    # Cặp READ cũng bắt buộc: tool search_read mail.activity TRƯỚC khi ghi
    # (crm.py:272) để lọc theo chủ sở hữu, và bộ lọc đó là lớp cưỡng chế DUY
    # NHẤT vì Odoo không chặn đóng việc của người khác. Mất quyền đọc =
    # sập lớp cưỡng chế, không phải chỉ mất tiện ích.
    "close_activity":          [("mail.activity", "read"),
                                ("mail.activity", "write")],  # crm.py close_activity
    # Tool CHỈ-ĐỌC. Đo 2026-08-14: cả hai vai non-admin đọc được, nhưng cả
    # hai trả 0 dòng của chính mình — nên quyền đọc hỏng sẽ trông y hệt
    # "không có việc nào được giao". Phải canh tường minh.
    "find_my_activities":      [("mail.activity", "read")],  # crm.py find_my_activities
```

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `pytest tests/agents/test_close_activity_roles.py tests/mcp/test_tool_access_map_drift.py -m "not integration and not live" -v`
Expected: PASS. Nếu `test_model_khai_deu_co_that_trong_nguon_tool` đỏ vì không tìm thấy hàm `find_my_activities`, đó là thông tin thật về cách test đó dò nguồn — **báo cáo**, đừng gỡ dòng vừa thêm.

- [ ] **Step 5: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_role_odoo_consistency.py backend/tests/agents/test_close_activity_roles.py
git commit -m "fix(roles): quyền đọc mail.activity được khai và được canh

close_activity đọc trước khi ghi, và bộ lọc chủ sở hữu dựa trên phép đọc
đó là lớp cưỡng chế duy nhất. find_my_activities trước đây không nằm
trong bảng nào cả."
```

---

## Task 8: Mở nguồn phủ sang mọi tool MCP đã đăng ký

**Files:**
- Modify: `backend/tests/mcp/test_tool_access_map_drift.py`
- Modify: `scripts/check_role_odoo_consistency.py` (bổ sung dòng cho tool còn thiếu)

**Interfaces:**
- Consumes: `check_role_odoo_consistency.TOOL_ACCESS_MAP`, `UNMAPPED_TOOLS` (đã có); registry MCP thật qua `server.mcp._tool_manager._tools`.
- Produces: không có API mới.

**Bối cảnh — đây là lỗ cấu trúc, không phải một dòng thiếu.** `_declared_tools()` (`test_tool_access_map_drift.py:132-140`) lấy tên tool từ `roles.py` (`cfg.own | cfg.needs_sign_off | cfg.other_dept`) — toàn tool **GHI**. Tool **chỉ-đọc** không xuất hiện ở đó nên lọt hoàn toàn: `find_my_activities` ở Task 7 là một trường hợp, không phải trường hợp duy nhất.

Nguồn đúng là registry MCP thật. Khuôn lấy registry đã có sẵn hai chỗ trong repo: `backend/evals/role_config.py::_mcp_tool_fns` và fixture trong `backend/tests/jobs/test_eval_role_config.py`.

⚠️ Mở nguồn phủ sẽ làm lộ ra một loạt tool chưa khai. Đó là **kết quả mong muốn**, không phải sự cố. Với mỗi tool lộ ra: đọc thân hàm trong `mcp-servers/odoo/tools/*.py`, liệt kê mọi lệnh `odoo("<model>", "<method>", …)`, tra `<method>` sang operation bằng `ODOO_METHOD_OPERATION_MAP` trong `mcp-servers/odoo/security.py`, rồi thêm dòng. Tool không map sạch vào một cặp cố định thì vào `UNMAPPED_TOOLS` **kèm lý do cụ thể** theo khuôn dòng `flag_order_for_review` đã có.

- [ ] **Step 1: Đo trước — liệt kê tool sẽ lộ ra**

Chạy đoạn sau và **ghi kết quả vào báo cáo task**; nó quyết định khối lượng Step 3:

```bash
cd backend && ./.venv/Scripts/python.exe -c "
import sys, pathlib
from dotenv import load_dotenv
load_dotenv(pathlib.Path('..')/'.env')
mcp = pathlib.Path('..')/'mcp-servers'/'odoo'
sys.path.insert(0, str(mcp)); sys.path.insert(0, '../scripts')
import server, check_role_odoo_consistency as m
phu = set(m.TOOL_ACCESS_MAP) | set(m.UNMAPPED_TOOLS)
thieu = sorted(set(server.mcp._tool_manager._tools) - phu)
print(len(thieu), 'tool chua khai:'); [print(' ', t) for t in thieu]
"
```

- [ ] **Step 2: Viết test thất bại**

Trong `backend/tests/mcp/test_tool_access_map_drift.py`, thêm cạnh `test_moi_tool_trong_roles_deu_duoc_bang_phu` (giữ nguyên test cũ — nó hẹp hơn nhưng chẩn đoán tốt hơn):

```python
def _registered_tools():
    """Mọi tool MCP đã đăng ký, lấy từ chính registry — nguồn phủ ĐÚNG.

    _declared_tools() chỉ lấy tool GHI khai trong roles.py, nên tool CHỈ-ĐỌC
    lọt hoàn toàn qua cả hai lưới (find_my_activities là một trường hợp thật,
    đo 2026-08-14). Registry thì không phân biệt đọc/ghi."""
    import sys
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        return set(server.mcp._tool_manager._tools)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_moi_tool_mcp_dang_ky_deu_duoc_bang_phu(script_mod):
    """Tool CHỈ-ĐỌC cũng phải được khai hoặc được miễn trừ kèm lý do."""
    phu = set(script_mod.TOOL_ACCESS_MAP) | set(script_mod.UNMAPPED_TOOLS)
    thieu = sorted(_registered_tools() - phu)
    assert not thieu, (
        "tool đã đăng ký trên MCP nhưng không có trong TOOL_ACCESS_MAP cũng "
        f"không trong UNMAPPED_TOOLS: {thieu}")


def test_nguon_phu_moi_rong_hon_nguon_cu(script_mod):
    """Đối chứng: nếu _registered_tools() vì lý do nào đó trả tập rỗng hoặc
    hẹp hơn roles.py, test trên xanh giả và lỗ cấu trúc vẫn nguyên."""
    assert _declared_tools() < _registered_tools()
```

⚠️ `MCP_DIR` phải trỏ đúng `mcp-servers/odoo`; file test này đã có hằng tương đương — dùng lại, đừng khai trùng.

- [ ] **Step 3: Chạy để chắc chắn ĐỎ, rồi bổ sung bảng**

Run: `pytest tests/mcp/test_tool_access_map_drift.py -m "not integration and not live" -v`
Expected: FAIL, liệt kê đúng tập tool ở Step 1.

Bổ sung từng dòng theo phương pháp ở phần Bối cảnh. Mỗi dòng kèm chú thích nêu tool nằm ở file nào.

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `pytest tests/mcp/test_tool_access_map_drift.py -m "not integration and not live" -v`
Expected: PASS.

- [ ] **Step 5: Phép thử phá**

Xoá tạm một dòng bất kỳ vừa thêm ở Step 3.
Run: `pytest tests/mcp/test_tool_access_map_drift.py::test_moi_tool_mcp_dang_ky_deu_duoc_bang_phu -m "not integration and not live" -q`
Expected: FAIL, nêu đúng tên tool vừa xoá. Hoàn nguyên.

- [ ] **Step 6: Chạy toàn bộ**

Run: `pytest -m "not integration and not live" -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/mcp/test_tool_access_map_drift.py scripts/check_role_odoo_consistency.py
git commit -m "test(roles): nguồn phủ bảng quyền lấy từ registry MCP thật

_declared_tools() chỉ lấy tool GHI khai trong roles.py nên mọi tool
chỉ-đọc lọt qua cả hai lưới. Giữ test cũ làm lưới chẩn đoán hẹp hơn."
```

---

## Nghiệm thu sống — TRƯỚC khi merge

⚠️ **Controller làm, không phải subagent.** Mọi thao tác khởi động/dừng tiến trình sống thuộc về controller.

Chạy trên worktree của nhánh, không phải trên `main`:

1. Chạy `backend/migrations/002_mcp_call_log.sql` trên database ở `DATABASE_URL`.
2. Khởi động lại **cả bốn** tiến trình MCP + backend. Bốn, không phải một: mỗi vai một tiến trình, và `assert_log_table_ready` chạy ở từng cái.
3. Qua **UI thật**, gây một lỗi quyền: đăng nhập vai kho, hỏi một dữ liệu kế toán. Kiểm câu trả lời **không chứa** tên nhóm Odoo nào (`Accounting/`, `Youdoo AI /`, `Sales/User`).
4. Truy vấn `mcp_call_log` — phải có dòng tương ứng, `error_message` chứa nguyên văn lỗi.
5. Chạy `python verify_audit_chain.py` — phải báo chuỗi nguyên vẹn trên **dữ liệu thật**, không phải trên bảng rỗng.

Bước 3 và 4 là **một cặp**: câu trả lời sạch **và** dấu vết còn. Thiếu một trong hai thì đợt này thất bại theo đúng nghĩa nó đặt ra.

---

## Ngoài phạm vi — đừng làm

- `ai-warehouse` đọc được `ir.config_parameter` và `res.groups` (spec §6.1). Vấn đề cấu hình quyền Odoo, cần rà riêng.
- Bảng kiểm toán cho tầng backend (spec §6.2). Backend ghi vào logger; dựng bảng thứ hai là quyết định kiến trúc khác.
- `erp_query/crm.py:88` đọc `mail.activity` ở tầng gateway backend (spec §6.3) — nằm ngoài `TOOL_ACCESS_MAP` theo đúng thiết kế của bảng đó.
- Khôi phục spec hash-chain gốc (spec §6.4) — không có trong repo này.
- Phân loại nguyên nhân lỗi cho người dùng (spec §6.6) — đã loại có chủ ý ở §2.3.
