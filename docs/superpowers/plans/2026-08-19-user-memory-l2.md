# Ký ức xuyên phiên L2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Youdoo nhớ được sở thích tương tác và từ vựng riêng của từng người dùng, xuyên các phiên hội thoại khác nhau.

**Architecture:** Một bảng Postgres append-only khoá theo `user_id`. Model phát tín hiệu bằng **marker trong chính câu trả lời** (không phải tool call — `chitchat` không có tool loop), code tất định bóc ra, chuẩn hoá key, chặn fact mang mã chứng từ, ghi DB, rồi tự chèn dòng công bố. Chiều đọc nạp một lần ở `chat()` và ghép vào đầu system prompt của 4 node sinh câu trả lời.

**Tech Stack:** Python 3.11, LangGraph, psycopg3 (`AsyncConnectionPool` đã có sẵn trong `ERPAgent`), Postgres.

**Spec:** `docs/superpowers/specs/2026-08-19-user-memory-l2-design.md`

## Global Constraints

- **Lệnh pytest LUÔN kèm `-m "not integration and not live"`.** Lệnh trần sẽ gọi API LLM thật và tiêu hạn mức — đã gây sự cố trước đây.
- **Định danh trong code phải bằng TIẾNG ANH** (biến, hàm, tham số). Comment/docstring và **tên hàm test** giữ tiếng Việt theo đúng quy ước repo.
- **Bất biến append-only:** không bao giờ `UPDATE user_memory.fact_value`, không bao giờ `DELETE FROM user_memory`. Sửa/gỡ đều là chèn dòng mới + đánh dấu dòng cũ `superseded_by`.
- **Tất cả riêng tư theo `user_id`.** Không có bảng dùng chung, không có truy vấn nào bỏ điều kiện `user_id`.
- **KHÔNG đụng** `INTENT_ROUTER_PROMPT` (bất biến byte-for-byte một plan khác đang canh), `WRITE_PLANNER_PROMPT`, `GATHER_ERP_PROMPT`.
- **0 lượt gọi LLM thêm.** Không task nào được thêm một lượt `ainvoke` mới vào đường nóng.
- **Trần 50 fact đang hiệu lực mỗi người.**
- Số test kỳ vọng là **số CỘNG DỒN** từ mốc **1763 passed, 2 skipped, 53 deselected** (đo lại 2026-08-20, sau khi nhánh `rag-gpu-reranker-p0` merge vào main — mốc 1698 trong bản plan đầu đã lỗi thời). Lệch thì đếm lại bằng `--collect-only` và ghi số THẬT vào báo cáo, đừng sửa cho khớp plan.

---

## Task 1: Logic thuần — chuẩn hoá key, cổng phủ quyết, render khối ký ức

Không đụng DB, không đụng graph. Toàn bộ task này test được ở chế độ nhanh.

**Files:**
- Create: `backend/migrations/003_user_memory.sql`
- Create: `backend/src/agents/user_memory.py`
- Modify: `docs/getting-started.md` (thêm dòng migration thứ ba)
- Test: `backend/tests/agents/test_user_memory.py`

**Interfaces:**
- Produces:
  - `normalize_key(raw: str) -> str`
  - `is_document_code(value: str) -> bool`
  - `render_memory_block(facts: list[tuple[str, str]]) -> str`
  - `MEMORY_CAP = 50`

- [ ] **Step 1: Viết migration**

`backend/migrations/003_user_memory.sql`:

```sql
-- Ký ức xuyên phiên, tầng fact bền (spec 2026-08-19 §4).
-- APPEND-ONLY: không bao giờ UPDATE fact_value, không bao giờ DELETE.
-- Sửa/gỡ đều là chèn dòng mới + đánh dấu dòng cũ superseded_by.
CREATE TABLE IF NOT EXISTS user_memory (
    id            bigserial PRIMARY KEY,
    user_id       text        NOT NULL,
    fact_key      text        NOT NULL,
    fact_value    text        NOT NULL,
    thread_id     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    superseded_by bigint      REFERENCES user_memory(id),
    superseded_at timestamptz
);

CREATE INDEX IF NOT EXISTS user_memory_active
    ON user_memory (user_id) WHERE superseded_by IS NULL;
```

- [ ] **Step 2: Viết test cho `normalize_key` (chạy để thấy ĐỎ)**

`backend/tests/agents/test_user_memory.py`:

```python
"""Ký ức xuyên phiên — logic thuần (spec 2026-08-19 §4, §6.1).

Chuẩn hoá key BỎ DẤU là điều kiện để chống trùng chạy đúng: người Việt gõ cả
có dấu lẫn không dấu, nên "kho chính" và "kho chinh" phải ra CÙNG một key —
nếu không, người dùng sửa một fact mà bản cũ vẫn còn hiệu lực.
"""
import pytest

from src.agents.user_memory import (
    MEMORY_CAP, is_document_code, normalize_key, render_memory_block)


@pytest.mark.parametrize("raw,expected", [
    ("kho chính", "kho_chinh"),
    ("Kho Chính", "kho_chinh"),
    ("kho chinh", "kho_chinh"),
    ("  độ dài trả lời  ", "do_dai_tra_loi"),
    ("đơn khẩn", "don_khan"),
    ("Đã có gạch_dưới", "da_co_gach_duoi"),
])
def test_chuan_hoa_key_bo_dau_va_thuong_hoa(raw, expected):
    assert normalize_key(raw) == expected


def test_co_dau_va_khong_dau_ra_cung_mot_key():
    # Đây là lý do tồn tại của việc bỏ dấu — hai cách gõ phải supersede nhau.
    assert normalize_key("kho chính") == normalize_key("kho chinh")
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.user_memory'`

- [ ] **Step 3: Viết `normalize_key`**

`backend/src/agents/user_memory.py`:

```python
"""Ký ức xuyên phiên — tầng fact bền (L2). Spec 2026-08-19.

CHỈ giữ thứ Odoo KHÔNG chứa: sở thích tương tác và từ vựng riêng. Sự thật
nghiệp vụ đã ở Odoo và truy vấn được; chép sang đây là tạo nguồn sự thật thứ
hai sẽ trôi lệch khỏi bản ghi thật.

APPEND-ONLY: mọi thay đổi là chèn dòng mới + đánh dấu dòng cũ superseded.
Nhờ vậy ký ức sai luôn gỡ được và vẫn còn vệt kiểm toán.
"""
import re
import unicodedata

# Trần fact đang hiệu lực mỗi người. Vượt trần thì supersede cái CŨ NHẤT —
# không mất gì vì bảng append-only.
MEMORY_CAP = 50

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_key(raw: str) -> str:
    """Chuẩn hoá key: chữ thường, BỎ DẤU, mọi thứ không phải chữ/số → gạch dưới.

    BỎ DẤU là bắt buộc, không phải tuỳ chọn: người Việt gõ cả có dấu lẫn không
    dấu (đợt đa ngôn ngữ 2026-08-18 đo được đây là kiểu gõ phổ biến thật). Giữ
    dấu thì "kho_chính" và "kho_chinh" thành hai fact khác nhau và cơ chế
    supersede IM LẶNG ngừng hoạt động.
    """
    text = unicodedata.normalize("NFD", (raw or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return _NON_WORD.sub("_", text).strip("_")
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: PASS (7 test)

- [ ] **Step 5: Viết test cho cổng phủ quyết (chạy để thấy ĐỎ)**

Thêm vào `backend/tests/agents/test_user_memory.py`:

```python
@pytest.mark.parametrize("value", [
    "P00003", "S00012", "INV/2026/00004", "WH/OUT/00001",
    "đơn P00003 là quan trọng nhất", "xem hoá đơn INV/2026/00017 nhé",
])
def test_chan_fact_mang_ma_chung_tu_cu_the(value):
    # Marker do LLM phát ra, mà ở erp_read model đang NHÌN THẤY dữ liệu ERP —
    # không có gì ngăn nó ghi một mã đơn vào ký ức, rồi mã đó rò sang cloud ở
    # lượt chitchat sau (M5/ADR-009). Cổng này là thứ ngăn.
    assert is_document_code(value) is True


@pytest.mark.parametrize("value", [
    "WH/Stock",           # kho: có gạch chéo nhưng KHÔNG có chữ số → quy ước, cho qua
    "ngắn gọn",
    "giao trong 24h",     # có chữ số nhưng không phải mã chứng từ
    "tiếng Anh",
])
def test_cho_qua_fact_noi_ve_loai_hoac_quy_uoc(value):
    assert is_document_code(value) is False
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'is_document_code'`

- [ ] **Step 6: Viết `is_document_code`**

Thêm vào `backend/src/agents/user_memory.py`:

```python
# Mã chứng từ CỤ THỂ — hai hình dạng thật trong repo này:
#   - chữ+số liền: P00003, S00012, E-COM07
#   - có gạch chéo VÀ có chữ số: INV/2026/00004, WH/OUT/00001
# Ranh giới cố ý: "WH/Stock" (không chữ số) là tên KHO — một quy ước, cho qua.
# "WH/OUT/00001" (có chữ số) là MỘT phiếu cụ thể — chặn.
_DOC_CODE = re.compile(r"\b[A-Z]{1,4}\d{3,}\b|\b[A-Z]{2,}(?:/[A-Z0-9]+)*/\d+\b",
                       re.IGNORECASE)


def is_document_code(value: str) -> bool:
    """Fact có trỏ tới MỘT bản ghi ERP cụ thể không?

    Đúng khuôn "model đề xuất, code phủ quyết" của decide_route /
    verify_erp_grounding / facts_survived. Ký ức là nơi giữ quy ước, không phải
    nơi giữ bản ghi — bản ghi đã ở Odoo và truy vấn được.
    """
    return bool(_DOC_CODE.search(value or ""))
```

- [ ] **Step 7: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: PASS (17 test)

- [ ] **Step 8: Viết test cho `render_memory_block` (chạy để thấy ĐỎ)**

Thêm vào `backend/tests/agents/test_user_memory.py`:

```python
def test_render_khoi_ky_uc_rong_thi_tra_chuoi_rong():
    # Chuỗi rỗng để caller ghép có điều kiện, đúng khuôn render_working_context.
    assert render_memory_block([]) == ""


def test_render_khoi_ky_uc_liet_ke_tung_fact():
    block = render_memory_block([("do_dai_tra_loi", "ngắn gọn"),
                                 ("kho_chinh", "WH/Stock")])
    assert "do_dai_tra_loi = ngắn gọn" in block
    assert "kho_chinh = WH/Stock" in block


def test_tran_ky_uc_la_50():
    assert MEMORY_CAP == 50
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'render_memory_block'`

- [ ] **Step 9: Viết `render_memory_block`**

Thêm vào `backend/src/agents/user_memory.py`:

```python
def render_memory_block(facts: list[tuple[str, str]]) -> str:
    """Khối ký ức ghép vào ĐẦU system prompt. Rỗng khi không có fact nào.

    Đặt TRƯỚC prompt gốc (caller làm) để chỉ thị định dạng / '/no_think' của
    prompt gốc giữ vị trí cuối — cùng lý do render_working_context làm vậy.
    """
    if not facts:
        return ""
    lines = "\n".join(f"- {key} = {value}" for key, value in facts)
    return ("Ghi nhớ về người dùng này (họ đã tự khai ở phiên trước):\n"
            f"{lines}\n"
            "Áp dụng khi phù hợp. Nếu yêu cầu hiện tại mâu thuẫn với ghi nhớ, "
            "ưu tiên yêu cầu hiện tại.")
```

- [ ] **Step 10: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory.py -v -m "not integration and not live"`
Expected: PASS (20 test)

- [ ] **Step 11: Cập nhật `docs/getting-started.md`**

Trong khối lệnh migration (quanh dòng 139-143), thêm file thứ ba vào **cả hai** lệnh:

```powershell
docker cp backend\migrations\003_user_memory.sql youdoo-postgres:/tmp/003_user_memory.sql
docker exec youdoo-postgres psql -U admin -d ai_assistant -f /tmp/003_user_memory.sql
```

⚠️ Không bỏ qua bước này: **không có migration runner tự động**, nên thiếu dòng này là người dựng máy tiếp theo sẽ thiếu bảng và lỗi chỉ lộ ra lúc chạy thật.

- [ ] **Step 12: Chạy full suite**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1783 passed (1763 + 20), 2 skipped, 53 deselected

- [ ] **Step 13: Commit**

```bash
git add backend/migrations/003_user_memory.sql backend/src/agents/user_memory.py backend/tests/agents/test_user_memory.py docs/getting-started.md
git commit -m "feat(memory): schema + logic thuan cho ky uc xuyen phien L2"
```

---

## Task 2: Tầng truy cập DB

**Files:**
- Modify: `backend/src/agents/user_memory.py`
- Test: `backend/tests/agents/test_user_memory_postgres.py`

**Interfaces:**
- Consumes: `MEMORY_CAP`, `normalize_key` (Task 1)
- Produces:
  - `async load_active_facts(pool, user_id: str) -> list[tuple[str, str]]`
  - `async save_fact(pool, user_id: str, key: str, value: str, thread_id: str | None) -> None`
  - `async forget_fact(pool, user_id: str, key: str) -> bool`

- [ ] **Step 1: Viết test tích hợp (chạy để thấy ĐỎ)**

`backend/tests/agents/test_user_memory_postgres.py`:

```python
"""Test tích hợp — cần Postgres đang chạy VÀ migration 003 đã chạy.

Chạy:  pytest tests/agents/test_user_memory_postgres.py -m integration -v
Bỏ:    pytest -m "not integration"
"""
import os
import uuid

import pytest
from psycopg_pool import AsyncConnectionPool

from src.agents.user_memory import forget_fact, load_active_facts, save_fact

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")


@pytest.fixture
async def pool():
    if not DSN:
        pytest.skip("DATABASE_URL chưa đặt")
    p = AsyncConnectionPool(DSN, min_size=1, max_size=2, open=False)
    await p.open()
    yield p
    await p.close()


@pytest.fixture
def user_id():
    # user_id riêng mỗi lần chạy — test KHÔNG được đụng dữ liệu người thật.
    return f"test-{uuid.uuid4().hex[:12]}"


async def test_ghi_roi_doc_lai_duoc(pool, user_id):
    await save_fact(pool, user_id, "do_dai_tra_loi", "ngắn gọn", "thread-1")
    assert await load_active_facts(pool, user_id) == [("do_dai_tra_loi", "ngắn gọn")]


async def test_khai_lai_cung_key_thi_supersede_ban_cu(pool, user_id):
    await save_fact(pool, user_id, "kho_chinh", "WH2", "thread-1")
    await save_fact(pool, user_id, "kho_chinh", "WH/Stock", "thread-2")
    # Chỉ còn MỘT fact hiệu lực, và là bản mới.
    assert await load_active_facts(pool, user_id) == [("kho_chinh", "WH/Stock")]


async def test_supersede_khong_xoa_ban_cu(pool, user_id):
    await save_fact(pool, user_id, "kho_chinh", "WH2", "thread-1")
    await save_fact(pool, user_id, "kho_chinh", "WH/Stock", "thread-2")
    # Bất biến append-only: bản cũ VẪN CÒN trong bảng, chỉ bị đánh dấu.
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            "SELECT fact_value, superseded_by FROM user_memory "
            "WHERE user_id = %s ORDER BY id", (user_id,))).fetchall()
    assert len(rows) == 2
    assert rows[0][1] is not None      # bản cũ đã bị supersede
    assert rows[1][1] is None          # bản mới đang hiệu lực


async def test_quen_thi_khong_con_hieu_luc_nhung_van_con_dong(pool, user_id):
    await save_fact(pool, user_id, "kho_chinh", "WH/Stock", "thread-1")
    assert await forget_fact(pool, user_id, "kho_chinh") is True
    assert await load_active_facts(pool, user_id) == []
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            "SELECT count(*) FROM user_memory WHERE user_id = %s", (user_id,))).fetchall()
    assert rows[0][0] == 1             # KHÔNG bị DELETE


async def test_quen_key_khong_ton_tai_tra_false(pool, user_id):
    assert await forget_fact(pool, user_id, "khong_co_that") is False


async def test_ky_uc_cua_nguoi_nay_khong_lo_sang_nguoi_khac(pool, user_id):
    other = f"{user_id}-other"
    await save_fact(pool, user_id, "kho_chinh", "WH/Stock", "thread-1")
    assert await load_active_facts(pool, other) == []
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory_postgres.py -m integration -v`
Expected: FAIL — `ImportError: cannot import name 'load_active_facts'`

- [ ] **Step 2: Viết tầng DB**

Thêm vào `backend/src/agents/user_memory.py`:

```python
async def load_active_facts(pool, user_id: str) -> list[tuple[str, str]]:
    """Fact đang hiệu lực của MỘT người, cũ trước mới sau.

    KHÔNG có đường nào bỏ điều kiện user_id — ký ức riêng tư tuyệt đối theo
    người (spec §4).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT fact_key, fact_value FROM user_memory "
            "WHERE user_id = %s AND superseded_by IS NULL ORDER BY id",
            (user_id,))
        return [(row[0], row[1]) for row in await cur.fetchall()]


async def save_fact(pool, user_id: str, key: str, value: str,
                    thread_id: str | None) -> None:
    """Chèn fact mới và supersede mọi bản cũ CÙNG key. Không bao giờ UPDATE giá trị.

    Vượt MEMORY_CAP thì supersede fact CŨ NHẤT — không xoá, nên vẫn truy lại được.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO user_memory (user_id, fact_key, fact_value, thread_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, key, value, thread_id))
        new_id = (await cur.fetchone())[0]
        await conn.execute(
            "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
            "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
            "AND id <> %s",
            (new_id, user_id, key, new_id))
        await conn.execute(
            "UPDATE user_memory SET superseded_by = %s, superseded_at = now() "
            "WHERE id IN (SELECT id FROM user_memory "
            "             WHERE user_id = %s AND superseded_by IS NULL "
            "             ORDER BY id DESC OFFSET %s)",
            (new_id, user_id, MEMORY_CAP))


async def forget_fact(pool, user_id: str, key: str) -> bool:
    """Supersede fact đang hiệu lực của key này. True nếu có gỡ được cái nào.

    KHÔNG DELETE: "quên" với người dùng là "không còn áp dụng", còn vệt kiểm
    toán thì giữ nguyên.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE user_memory SET superseded_at = now() "
            "WHERE user_id = %s AND fact_key = %s AND superseded_by IS NULL "
            "RETURNING id",
            (user_id, key))
        rows = await cur.fetchall()
        if not rows:
            return False
        await conn.execute(
            "UPDATE user_memory SET superseded_by = id "
            "WHERE id = ANY(%s)", ([r[0] for r in rows],))
        return True
```

⚠️ `forget_fact` đặt `superseded_by = id` (tự trỏ vào chính nó) làm dấu "đã gỡ, không có bản thay thế". Đây là lý do cột cho phép self-reference — đừng thêm ràng buộc `CHECK (superseded_by <> id)`.

- [ ] **Step 3: Chạy test tích hợp — phải XANH**

Điều kiện: Postgres đang chạy và migration 003 đã chạy (Task 1 Step 11).

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory_postgres.py -m integration -v`
Expected: PASS (6 test)

- [ ] **Step 4: Chạy full suite chế độ nhanh — không được đổi số**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1783 passed (không đổi — test mới đều là `integration`), 2 skipped, deselected tăng 6 → 59

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/user_memory.py backend/tests/agents/test_user_memory_postgres.py
git commit -m "feat(memory): tang truy cap DB append-only cho user_memory"
```

---

## Task 3: Bóc marker khỏi câu trả lời

**Files:**
- Modify: `backend/src/agents/user_memory.py`
- Test: `backend/tests/agents/test_user_memory_markers.py`

**Interfaces:**
- Consumes: (không có)
- Produces:
  - `MEMORY_SAVE_MARKER = "GHI_NHỚ"`, `MEMORY_FORGET_MARKER = "QUÊN"`
  - `extract_memory_markers(body: str) -> tuple[str, list[tuple[str, str]], list[str]]`
    trả `(văn bản đã bỏ marker, [(key_thô, value)], [key_thô cần quên])`

- [ ] **Step 1: Viết test (chạy để thấy ĐỎ)**

`backend/tests/agents/test_user_memory_markers.py`:

```python
"""Bóc marker ký ức — phải bắt CẢ HAI dạng đặt marker.

Lịch sử có thật (2026-08-06): với marker ĐỀ_XUẤT_GHI, model đặt marker NGAY SAU
dấu hỏi thay vì xuống dòng như prompt yêu cầu, tái lập 2/2 lần qua backend
live. Pattern neo-đầu-dòng bỏ sót ca đó → marker LỘ RA văn bản người dùng thấy
VÀ tín hiệu không tới nơi. Đừng lặp lại: hỗ trợ cả hai dạng ngay từ đầu.
"""
from src.agents.user_memory import extract_memory_markers


def test_marker_dau_dong_duoc_boc():
    body = 'Được rồi.\nGHI_NHỚ: kho chính = WH/Stock'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert forgets == []
    assert "GHI_NHỚ" not in clean
    assert clean.strip() == "Được rồi."


def test_marker_dan_dinh_cuoi_cau_van_duoc_boc():
    # Đây là ca mà pattern neo-đầu-dòng bỏ sót.
    body = 'Được rồi, tôi nhớ nhé. GHI_NHỚ: kho chính = WH/Stock'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert "GHI_NHỚ" not in clean


def test_marker_quen_duoc_boc():
    body = 'Đã bỏ.\nQUÊN: kho chính'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == []
    assert forgets == ["kho chính"]
    assert "QUÊN" not in clean


def test_nhieu_marker_trong_mot_cau_tra_loi():
    body = 'Xong.\nGHI_NHỚ: độ dài trả lời = ngắn gọn\nGHI_NHỚ: kho chính = WH/Stock'
    _clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("độ dài trả lời", "ngắn gọn"), ("kho chính", "WH/Stock")]


def test_khong_co_marker_thi_tra_nguyen_van():
    body = "Đơn P00003 của Azure Interior, tổng 255.0."
    clean, saves, forgets = extract_memory_markers(body)
    assert clean == body
    assert saves == []
    assert forgets == []


def test_marker_thieu_dau_bang_thi_bo_qua_nhung_van_cat_khoi_van_ban():
    # Model viết sai khuôn: không được ghi bừa, nhưng cũng KHÔNG được để lộ
    # marker ra văn bản người dùng đọc.
    body = "Xong.\nGHI_NHỚ: cái gì đó không có dấu bằng"
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == []
    assert "GHI_NHỚ" not in clean
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory_markers.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'extract_memory_markers'`

- [ ] **Step 2: Viết `extract_memory_markers`**

Thêm vào `backend/src/agents/user_memory.py`:

```python
MEMORY_SAVE_MARKER = "GHI_NHỚ"
MEMORY_FORGET_MARKER = "QUÊN"

# Hai pattern mỗi marker, đúng khuôn _WRITE_SUGGEST_RE / _WRITE_SUGGEST_TRAILING_RE
# ở synthesis.py. Pattern neo-đầu-dòng KHÔNG đủ: model dán marker vào cuối câu
# trong thực tế (bug thật 2026-08-06), khiến marker lộ ra văn bản hiển thị.
_SAVE_LINE = re.compile(rf'\n?^{MEMORY_SAVE_MARKER}:([^\n]*)',
                        re.IGNORECASE | re.MULTILINE)
_SAVE_TAIL = re.compile(rf'[ \t]*{MEMORY_SAVE_MARKER}:([^\n]*)$', re.IGNORECASE)
_FORGET_LINE = re.compile(rf'\n?^{MEMORY_FORGET_MARKER}:([^\n]*)',
                          re.IGNORECASE | re.MULTILINE)
_FORGET_TAIL = re.compile(rf'[ \t]*{MEMORY_FORGET_MARKER}:([^\n]*)$', re.IGNORECASE)


def extract_memory_markers(body: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Tách marker ký ức khỏi văn bản. Người dùng KHÔNG BAO GIỜ thấy marker.

    Trả (văn bản sạch, [(key thô, value)], [key thô cần quên]). Key ở đây còn
    THÔ — caller phải gọi normalize_key(). Tách hai việc để test được riêng.

    Marker viết sai khuôn (thiếu dấu '=') bị BỎ QUA nhưng vẫn bị CẮT khỏi văn
    bản: thà mất một ghi nhớ còn hơn để lộ ký hiệu máy-đọc ra câu người dùng.
    """
    text = body or ""
    saves: list[tuple[str, str]] = []
    forgets: list[str] = []

    for pattern in (_SAVE_LINE, _SAVE_TAIL):
        for raw in pattern.findall(text):
            key, sep, value = raw.partition("=")
            if sep and key.strip() and value.strip():
                saves.append((key.strip(), value.strip()))
        text = pattern.sub("", text)

    for pattern in (_FORGET_LINE, _FORGET_TAIL):
        for raw in pattern.findall(text):
            if raw.strip():
                forgets.append(raw.strip())
        text = pattern.sub("", text)

    return text.rstrip(), saves, forgets
```

- [ ] **Step 3: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_user_memory_markers.py -v -m "not integration and not live"`
Expected: PASS (6 test)

- [ ] **Step 4: Chạy full suite**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1789 passed (1783 + 6), 2 skipped, 59 deselected

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/user_memory.py backend/tests/agents/test_user_memory_markers.py
git commit -m "feat(memory): boc marker GHI_NHO/QUEN, bat ca dang dan cuoi cau"
```

---

## Task 4: Nối đường GHI vào `ERPAgent.chat()`

**Files:**
- Modify: `backend/src/agents/erp_agent.py` (hàm `chat`, quanh dòng 189-224)
- Modify: `backend/src/main.py` (điểm gọi `agent.chat`, quanh dòng 176)
- Test: `backend/tests/agents/test_chat_memory.py`

**Interfaces:**
- Consumes: `extract_memory_markers`, `normalize_key`, `is_document_code`, `save_fact`, `forget_fact` (Task 1-3)
- Produces: `ERPAgent.chat(..., user_id: str | None = None)`; hằng `MEMORY_NOTICE_PREFIX = "📝 Đã ghi nhớ:"`, `MEMORY_BLOCKED_PREFIX = "⚠️ Không ghi nhớ:"`

- [ ] **Step 1: Viết test (chạy để thấy ĐỎ)**

`backend/tests/agents/test_chat_memory.py`:

```python
"""Đường GHI của ký ức, tại chốt duy nhất ERPAgent.chat().

Chốt thay vì vá từng node: lớp lỗi "danh sách khai báo thiếu âm thầm" đã tái
phát 5 lần trong repo này. chat() vừa được chứng minh là chốt đúng ở đợt đa
ngôn ngữ (localize).
"""
import pytest

from src.agents.erp_agent import (
    MEMORY_BLOCKED_PREFIX, MEMORY_NOTICE_PREFIX, ERPAgent)


class _FakePool:
    """Ghi lại lời gọi thay vì chạm Postgres."""

    def __init__(self):
        self.saved: list[tuple] = []
        self.forgotten: list[tuple] = []


async def _fake_save(pool, user_id, key, value, thread_id):
    pool.saved.append((user_id, key, value, thread_id))


async def _fake_forget(pool, user_id, key):
    pool.forgotten.append((user_id, key))
    return True


@pytest.fixture
def agent(monkeypatch):
    a = ERPAgent.__new__(ERPAgent)          # bỏ qua __init__ (cần Postgres/MCP)
    a._pool = _FakePool()
    # PHẢI có khoá "evaluator": chat() đọc self._llms["evaluator"] để gọi
    # localize. Để dict rỗng thì KeyError rơi vào except và test vẫn xanh —
    # nhưng xanh vì đường lỗi, không phải vì đường đúng. Đó là test không đo gì.
    a._llms = {"evaluator": object()}
    monkeypatch.setattr("src.agents.erp_agent.save_fact", _fake_save)
    monkeypatch.setattr("src.agents.erp_agent.forget_fact", _fake_forget)
    monkeypatch.setattr("src.agents.erp_agent.localize",
                        lambda text, lang, llm: _identity(text))
    return a


async def _identity(text):
    return text


async def test_ghi_nho_duoc_luu_va_cong_bo(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Được rồi.\nGHI_NHỚ: kho chính = WH/Stock"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "kho chính là WH/Stock"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.saved == [("u1", "kho_chinh", "WH/Stock", "t1")]
    assert MEMORY_NOTICE_PREFIX in out
    assert "kho_chinh = WH/Stock" in out
    assert "GHI_NHỚ" not in out          # marker không bao giờ lộ ra


async def test_fact_mang_ma_chung_tu_bi_chan_va_noi_ro(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Ừ.\nGHI_NHỚ: đơn quan trọng = P00003"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "nhớ đơn P00003 nhé"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.saved == []        # cổng phủ quyết đã chặn
    assert MEMORY_BLOCKED_PREFIX in out   # và KHÔNG im lặng


async def test_quen_duoc_thuc_hien(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Đã bỏ.\nQUÊN: kho chính"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "quên kho chính đi"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.forgotten == [("u1", "kho_chinh")]
    assert "QUÊN" not in out


async def test_khong_co_user_id_thi_khong_ghi_gi(agent, monkeypatch):
    # Fail-closed: không xác định được người thì KHÔNG ghi ký ức cho ai cả.
    async def fake_inner(*args, **kwargs):
        return "Ừ.\nGHI_NHỚ: kho chính = WH/Stock"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id=None)

    assert agent._pool.saved == []
    assert "GHI_NHỚ" not in out           # vẫn phải cắt marker khỏi văn bản


async def test_loi_ghi_ky_uc_khong_lam_hong_luot_chat(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Được rồi.\nGHI_NHỚ: kho chính = WH/Stock"

    async def boom(*args, **kwargs):
        raise RuntimeError("DB sập")

    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)
    monkeypatch.setattr("src.agents.erp_agent.save_fact", boom)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id="u1")

    assert "Được rồi." in out             # câu trả lời vẫn tới người dùng
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_chat_memory.py -v -m "not integration and not live"`
Expected: FAIL — `ImportError: cannot import name 'MEMORY_NOTICE_PREFIX'`

- [ ] **Step 2: Sửa `chat()`**

Trong `backend/src/agents/erp_agent.py`, thêm import:

```python
from .user_memory import (extract_memory_markers, forget_fact, is_document_code,
                          normalize_key, save_fact)
```

Thêm hằng ở đầu module (cạnh các hằng thông báo đã có):

```python
# Công bố do CODE chèn, KHÔNG giao cho model nhớ: ghi âm thầm đúng là thứ cần
# tránh, mà model thì có lượt sẽ quên nói (spec §7).
MEMORY_NOTICE_PREFIX = "📝 Đã ghi nhớ:"
MEMORY_BLOCKED_PREFIX = "⚠️ Không ghi nhớ:"
```

Thay thân `chat()` (giữ nguyên toàn bộ docstring cũ, thêm đoạn mô tả ký ức):

```python
    async def chat(self, messages: list[dict], thread_id: str | None = None,
                   reset_if_fresh: bool = False, role: str = "admin",
                   user_id: str | None = None) -> str:
        answer = await self._chat_inner(messages, thread_id=thread_id,
                                        reset_if_fresh=reset_if_fresh,
                                        role=role)
        answer = await self._apply_memory_markers(answer, user_id, thread_id)
        lang = VI
        for m in messages or []:
            if m.get("role") == "user" and detect_lang(m.get("content")) == EN:
                lang = EN
                break
        try:
            return await localize(answer, lang, self._llms["evaluator"])
        except Exception:                                   # noqa: BLE001
            return answer

    async def _apply_memory_markers(self, answer: str, user_id: str | None,
                                    thread_id: str | None) -> str:
        """Bóc marker, ghi ký ức, chèn dòng công bố. KHÔNG BAO GIỜ ném.

        Chạy TRƯỚC localize() để bản dịch không làm hỏng marker, và để dòng
        công bố cũng được dịch cho người dùng tiếng Anh.

        Marker luôn bị cắt kể cả khi không ghi được (thiếu user_id, DB lỗi,
        cổng phủ quyết chặn) — ký hiệu máy-đọc không bao giờ được lọt ra câu
        người dùng đọc.
        """
        clean, saves, forgets = extract_memory_markers(answer)
        if not saves and not forgets:
            return clean
        notices: list[str] = []
        try:
            for raw_key, value in saves:
                key = normalize_key(raw_key)
                if not key:
                    continue
                if is_document_code(value):
                    notices.append(f"{MEMORY_BLOCKED_PREFIX} {key} — ký ức chỉ "
                                   "giữ quy ước, không giữ mã chứng từ cụ thể.")
                    continue
                if user_id:
                    await save_fact(self._pool, user_id, key, value, thread_id)
                    notices.append(f'{MEMORY_NOTICE_PREFIX} {key} = {value} '
                                   '— nói "quên đi" nếu sai.')
            for raw_key in forgets:
                key = normalize_key(raw_key)
                if key and user_id and await forget_fact(self._pool, user_id, key):
                    notices.append(f"🗑️ Đã bỏ ghi nhớ: {key}")
        except Exception:                                   # noqa: BLE001
            return clean
        return "\n\n".join([clean, *notices]) if notices else clean
```

- [ ] **Step 3: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_chat_memory.py -v -m "not integration and not live"`
Expected: PASS (5 test)

- [ ] **Step 4: Nối `user_id` ở `main.py`**

Trong `backend/src/main.py`, điểm gọi `agent.chat` (quanh dòng 176) đổi thành:

```python
                answer = await agent.chat(messages, thread_id=thread_id, role=role,
                                          reset_if_fresh=not _explicit_session(body),
                                          user_id=req.headers.get("x-openwebui-user-id"))
```

⚠️ Dùng ĐÚNG header này, không đọc name/email — đó là PII và bị cấm (`roles.py:186-203`). `user_id` là chuỗi mờ, hợp sẵn làm khoá ký ức.

- [ ] **Step 5: Chạy full suite**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1794 passed (1789 + 5), 2 skipped, 59 deselected

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/erp_agent.py backend/src/main.py backend/tests/agents/test_chat_memory.py
git commit -m "feat(memory): duong ghi tai chot chat(), cong bo do code chen"
```

---

## Task 5: Nối đường ĐỌC — nạp và ghép vào 4 prompt

**Files:**
- Modify: `backend/src/agents/state.py` (thêm field)
- Modify: `backend/src/agents/erp_agent.py` (`_chat_inner`, `_invoke_fresh`)
- Modify: `backend/src/agents/nodes.py` (`erp_read`, `respond_unknown`, `rag_node`)
- Modify: `backend/src/agents/synthesis.py` (`synthesize` nhận thêm tham số)
- Modify: `backend/src/agents/fanout.py` (`fuse_answer`)
- Test: `backend/tests/agents/test_memory_injection.py`

**Interfaces:**
- Consumes: `load_active_facts`, `render_memory_block` (Task 1-2)
- Produces: `ERPAgentState["user_memory"]: str | None`; `synthesize(query, result, llm, memory: str = "")`

- [ ] **Step 1: Viết test chống trôi (chạy để thấy ĐỎ)**

`backend/tests/agents/test_memory_injection.py`:

```python
"""Cả BỐN node sinh câu trả lời đều phải nạp khối ký ức.

Bốn chỗ ghép = bốn chỗ có thể quên. Lớp lỗi "danh sách khai báo thiếu âm thầm"
đã tái phát 5 lần ở repo này, nên chống trôi bằng TEST chứ không bằng lời hứa.
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

MEMORY_BLOCK = "Ghi nhớ về người dùng này"


class _SpyLLM:
    """Bắt lại system prompt mà node thật sự gửi đi."""

    def __init__(self):
        self.system_prompts: list[str] = []

    async def ainvoke(self, messages, config=None):
        for m in messages:
            if m.type == "system":
                self.system_prompts.append(m.content)
        return AIMessage(content="ok")


@pytest.fixture
def state():
    return {"messages": [HumanMessage(content="xin chào")],
            "user_memory": "Ghi nhớ về người dùng này:\n- do_dai_tra_loi = ngắn gọn"}


async def test_respond_unknown_nap_khoi_ky_uc(state):
    from src.agents.nodes import make_respond_unknown_node
    llm = _SpyLLM()
    await make_respond_unknown_node(llm)(state)
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


async def test_fuse_answer_nap_khoi_ky_uc(state):
    from src.agents.fanout import make_fuse_answer_node
    llm = _SpyLLM()
    state = {**state, "doc_context": [], "erp_facts": "Đơn S00042 | 1.500.000"}
    await make_fuse_answer_node(llm)(state)
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


async def test_synthesize_nap_khoi_ky_uc():
    from src.agents.synthesis import SENTINEL, synthesize
    from src.rag.types import RetrievalResult

    class _Chunk:
        text = "Chính sách hoàn hàng trong 30 ngày."
        section_path = "Điều 1"
        source_file = "policy.docx"
        sheet = None
        page = None
        row_range = None
        dense_score = 0.9
        sparse_score = None

    class _SentinelLLM(_SpyLLM):
        """Trả SENTINEL để synthesize dừng NGAY sau lượt gọi đầu — system
        prompt đã bắt được rồi, và không phải dựng chunk giả đủ thật cho
        cite_and_verify chạy tiếp."""

        async def ainvoke(self, messages, config=None):
            await super().ainvoke(messages, config)
            return AIMessage(content=SENTINEL)

    llm = _SentinelLLM()
    result = RetrievalResult(query="q", query_used="q", chunks=[_Chunk()],
                             top_score=0.9, total_candidates=1)
    await synthesize("hỏi gì đó", result, llm,
                     memory="Ghi nhớ về người dùng này:\n- do_dai_tra_loi = ngắn gọn")
    assert any(MEMORY_BLOCK in p for p in llm.system_prompts)


def test_state_co_field_user_memory():
    from src.agents.state import ERPAgentState
    assert "user_memory" in ERPAgentState.__annotations__
```

⚠️ `test_erp_read_nap_khoi_ky_uc` KHÔNG viết ở đây: `erp_read` dựng ReAct agent qua `_create_agent`, không gọi `llm.ainvoke` trực tiếp nên `_SpyLLM` không bắt được. Thay bằng test đọc prompt đã dựng ở Step 5 bên dưới.

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_memory_injection.py -v -m "not integration and not live"`
Expected: FAIL — `AssertionError` (chưa node nào nạp)

- [ ] **Step 2: Thêm field vào state**

Trong `backend/src/agents/state.py`, thêm vào `ERPAgentState`:

```python
    user_memory: str | None       # khối ký ức đã render, nạp MỘT LẦN ở chat()
                                  # rồi ghép vào đầu system prompt của 4 node
                                  # sinh câu trả lời. Đọc-thôi với mọi node —
                                  # không node nào ghi key này.
```

- [ ] **Step 3: Nạp ký ức ở `_chat_inner` và truyền qua `_invoke_fresh`**

Trong `backend/src/agents/erp_agent.py`, thêm import `load_active_facts, render_memory_block` vào dòng import `user_memory` đã có ở Task 4.

`_chat_inner` nhận thêm `user_id`, và `chat()` truyền xuống:

```python
        answer = await self._chat_inner(messages, thread_id=thread_id,
                                        reset_if_fresh=reset_if_fresh,
                                        role=role, user_id=user_id)
```

Đổi chữ ký `_chat_inner`:

```python
    async def _chat_inner(self, messages: list[dict], thread_id: str | None = None,
                          reset_if_fresh: bool = False, role: str = "admin",
                          user_id: str | None = None) -> str:
```

Trong `_chat_inner`, ngay sau `tid = thread_id or uuid.uuid4().hex`:

```python
        memory_block = ""
        if user_id:
            try:
                facts = await load_active_facts(self._pool, user_id)
                memory_block = render_memory_block(facts)
            except Exception:                               # noqa: BLE001
                memory_block = ""     # ký ức hỏng KHÔNG được làm hỏng lượt chat
```

`_invoke_fresh` nhận thêm và ghi vào state:

```python
    async def _invoke_fresh(self, messages: list[dict], config: dict, graph,
                            memory_block: str = ""):
        if graph is None:
            raise ValueError("_invoke_fresh: graph is required (no admin fallback)")
        reset = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]
        return await graph.ainvoke({"messages": reset, "user_memory": memory_block},
                                   config=config)
```

**Cả BA điểm gọi `_invoke_fresh` trong `_chat_inner`** phải truyền thêm
`memory_block` — đọc file thật để tìm đủ, đừng tin danh sách này là đã đủ:

1. nhánh `if is_fresh:`
2. nhánh checkpoint hết hạn (`result = await self._invoke_fresh(...)` sau `Command(resume=False)`)
3. nhánh `else:` cuối (thread không parked)

```python
                result = await self._invoke_fresh(messages, config, graph, memory_block)
```

Sót một chỗ = ký ức im lặng biến mất ở đúng nhánh đó, và không test nào hiện có
bắt được. Đây chính là lớp lỗi "danh sách khai báo thiếu âm thầm" đã tái phát 5 lần.

- [ ] **Step 4: Ghép vào 3 node có state**

`backend/src/agents/nodes.py` — `respond_unknown`, thay dòng gọi LLM:

```python
        system = CHITCHAT_PROMPT
        memory = state.get("user_memory")
        if memory:
            system = memory + "\n\n" + CHITCHAT_PROMPT
        response = await llm.ainvoke([SystemMessage(content=system), last_human])
```

`backend/src/agents/nodes.py` — `erp_read`, sửa khối dựng prompt sẵn có:

```python
        wc = state.get("working_context")
        prompt = (render_working_context(wc) + "\n\n" + SYSTEM_PROMPT) \
            if wc else SYSTEM_PROMPT
        memory = state.get("user_memory")
        if memory:
            prompt = memory + "\n\n" + prompt
```

`backend/src/agents/nodes.py` — `rag_node`, truyền xuống `synthesize`:

```python
            answer = await synthesize(query, result, llm,
                                      memory=state.get("user_memory") or "")
```

`backend/src/agents/fanout.py` — `fuse_answer`, sửa khối gọi LLM:

```python
            system = FUSE_PROMPT
            memory = state.get("user_memory")
            if memory:
                system = memory + "\n\n" + FUSE_PROMPT
            resp = await llm.ainvoke([
                SystemMessage(content=system),
                HumanMessage(content=render_fuse_input(
                    chunks, erp_facts, _last_human(state))),
            ])
```

- [ ] **Step 5: Ghép vào `synthesize` (node thứ tư)**

`backend/src/agents/synthesis.py`, đổi chữ ký và khối gọi:

```python
async def synthesize(query, result, llm, memory: str = ""):
```

```python
    system = RAG_SYNTHESIS_PROMPT
    if memory:
        system = memory + "\n\n" + RAG_SYNTHESIS_PROMPT
    resp = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=f"TÀI LIỆU:\n{_format_context(result.chunks)}\n\nCÂU HỎI: {query}"),
    ])
```

- [ ] **Step 6: Thêm test cho `erp_read` (đường ReAct)**

Thêm vào `backend/tests/agents/test_memory_injection.py`:

```python
async def test_erp_read_nap_khoi_ky_uc(state, monkeypatch):
    """erp_read dựng ReAct agent nên _SpyLLM không bắt được lời gọi LLM —
    chặn ở _create_agent để đọc chính chuỗi system_prompt nó nhận."""
    from src.agents import nodes

    seen: list[str] = []

    def fake_create_agent(llm, tools, system_prompt):
        seen.append(system_prompt)

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [*payload["messages"], AIMessage(content="ok")]}
        return _Agent()

    monkeypatch.setattr(nodes, "_create_agent", fake_create_agent)
    await nodes.make_erp_read_node(_SpyLLM(), [])(state)
    assert any(MEMORY_BLOCK in p for p in seen)
```

- [ ] **Step 7: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_memory_injection.py -v -m "not integration and not live"`
Expected: PASS (5 test)

- [ ] **Step 8: Chạy full suite — đây là task dễ vỡ test cũ nhất**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1799 passed (1794 + 5), 2 skipped, 59 deselected

Nếu có test cũ ĐỎ: đọc hiểu bất biến thật của nó rồi sửa cho đúng, **không nới lỏng assertion**. `synthesize` đổi chữ ký là chỗ nhiều khả năng vỡ nhất — tham số `memory` có giá trị mặc định nên mọi điểm gọi cũ phải vẫn chạy được.

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/state.py backend/src/agents/erp_agent.py backend/src/agents/nodes.py backend/src/agents/synthesis.py backend/src/agents/fanout.py backend/tests/agents/test_memory_injection.py
git commit -m "feat(memory): nap ky uc vao 4 prompt sinh cau tra loi"
```

---

## Task 6: Dạy model phát marker

**Files:**
- Modify: `backend/src/agents/prompts.py` (`SYSTEM_PROMPT`, `CHITCHAT_PROMPT`)
- Test: `backend/tests/agents/test_prompt_memory_rule.py`

**Interfaces:**
- Consumes: (không có)
- Produces: `MEMORY_RULE` (hằng chuỗi trong `prompts.py`)

- [ ] **Step 1: Viết test (chạy để thấy ĐỎ)**

`backend/tests/agents/test_prompt_memory_rule.py`:

```python
"""Chỉ HAI prompt được dạy phát marker ghi nhớ.

Đặt khắp nơi chỉ tăng nguy cơ bắn marker vu vơ — và false_injection là hướng
nguy hiểm được gác TUYỆT ĐỐI ở bộ eval `memory`.
"""
from src.agents import prompts


def test_hai_prompt_hoi_thoai_co_luat_ghi_nho():
    assert prompts.MEMORY_RULE in prompts.SYSTEM_PROMPT
    assert prompts.MEMORY_RULE in prompts.CHITCHAT_PROMPT


def test_prompt_khac_khong_co_luat_ghi_nho():
    for name in ("RAG_SYNTHESIS_PROMPT", "FUSE_PROMPT", "INTENT_ROUTER_PROMPT",
                 "WRITE_PLANNER_PROMPT", "GATHER_ERP_PROMPT"):
        assert prompts.MEMORY_RULE not in getattr(prompts, name), name


def test_luat_ghi_nho_cam_ghi_ma_chung_tu():
    # Cổng tất định vẫn là lưới cuối, nhưng prompt phải nói trước để cổng ít
    # phải bắn — cùng khuôn "lớp xác suất + lớp phủ quyết".
    assert "mã chứng từ" in prompts.MEMORY_RULE
```

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_prompt_memory_rule.py -v -m "not integration and not live"`
Expected: FAIL — `AttributeError: module 'src.agents.prompts' has no attribute 'MEMORY_RULE'`

- [ ] **Step 2: Thêm `MEMORY_RULE` và ghép vào 2 prompt**

Trong `backend/src/agents/prompts.py`, thêm hằng (đặt cạnh `LANGUAGE_RULE`):

```python
MEMORY_RULE = """
QUY TẮC GHI NHỚ:
Khi người dùng nêu một SỞ THÍCH lâu dài ("từ giờ trả lời ngắn gọn") hoặc một
QUY ƯỚC riêng ("kho chính của tôi là WH/Stock", "đơn khẩn nghĩa là 24h"), hãy
thêm một dòng CUỐI CÙNG:
GHI_NHỚ: <tên quy ước> = <giá trị>
Khi người dùng bảo bỏ một ghi nhớ, thêm dòng:
QUÊN: <tên quy ước>

TUYỆT ĐỐI KHÔNG ghi nhớ:
- mã chứng từ hay bản ghi cụ thể (P00003, INV/2026/00004) — dữ liệu đó đã ở
  trong hệ thống ERP và tra được bất cứ lúc nào
- câu hỏi hay yêu cầu dùng một lần

Phần lớn lượt trò chuyện KHÔNG có gì đáng ghi nhớ. Không có thì đừng thêm dòng
nào — ghi nhớ vu vơ làm nhiễu, không làm nên trí nhớ."""
```

Ghép vào cuối `SYSTEM_PROMPT` và `CHITCHAT_PROMPT`, **trước** `/no_think` nếu prompt đó có, đúng cách `LANGUAGE_RULE` đã được ghép.

- [ ] **Step 3: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/agents/test_prompt_memory_rule.py -v -m "not integration and not live"`
Expected: PASS (3 test)

- [ ] **Step 4: Chạy full suite**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1802 passed (1799 + 3), 2 skipped, 59 deselected

Test cũ trong `tests/agents/test_prompts.py` có thể vỡ nếu nó khẳng định `/no_think` nằm cuối chuỗi — sửa cho đúng vị trí mới, **giữ nguyên bất biến gốc**.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompt_memory_rule.py
git commit -m "feat(memory): MEMORY_RULE cho SYSTEM_PROMPT va CHITCHAT_PROMPT"
```

---

## Task 7: Bộ eval `memory`

**Files:**
- Modify: `backend/evals/cases.py`
- Modify: `backend/evals/run_eval.py`
- Modify: `backend/jobs/eval_gate.py`
- Test: `backend/tests/jobs/test_eval_memory.py`, `backend/tests/jobs/test_eval_gate.py`

**Interfaces:**
- Consumes: `extract_memory_markers`, `is_document_code`, `normalize_key` (Task 1, 3); `MEMORY_RULE` đã ghép vào prompt (Task 6)
- Produces: `MEMORY_CASES`, `eval_memory(llm, pace, checkpoint_path)` trả dict có khoá `set, n, false_injection, leaked_doc_code, recall, lat_p50, lat_p95, fails, errors`

- [ ] **Step 1: Thêm `MEMORY_CASES`**

Trong `backend/evals/cases.py`, cuối file:

```python
# ── MEMORY_CASES ─────────────────────────────────────────────────────────────
# (tên prompt, câu người dùng, loại kỳ vọng).
#   "none"    — KHÔNG được phát marker (hướng nguy hiểm: gác tuyệt đối)
#   "fact"    — phải phát marker, giá trị hợp lệ
#   "blocked" — model có thể phát marker, nhưng cổng tất định PHẢI chặn
MEMORY_CASES = [
    ("CHITCHAT_PROMPT", "hôm nay trời đẹp nhỉ", "none"),
    ("CHITCHAT_PROMPT", "cảm ơn bạn nhiều nhé", "none"),
    ("SYSTEM_PROMPT", "cho tôi xem chi tiết đơn mua P00003", "none"),
    ("CHITCHAT_PROMPT", "từ giờ trả lời ngắn gọn thôi nhé", "fact"),
    ("CHITCHAT_PROMPT", "kho chính của tôi là WH/Stock", "fact"),
    ("SYSTEM_PROMPT", "nhớ giúp tôi là đơn khẩn nghĩa là giao trong 24h", "fact"),
    ("SYSTEM_PROMPT", "nhớ giúp tôi đơn P00003 là đơn quan trọng nhất", "blocked"),
]
```

- [ ] **Step 2: Viết `eval_memory`**

Trong `backend/evals/run_eval.py`, thêm import ở khối import `src.agents`:

```python
from src.agents.user_memory import extract_memory_markers, is_document_code
```

Thêm hàm (đặt cạnh `eval_language`):

```python
async def eval_memory(llm, pace: float = 0.0, checkpoint_path=None):
    """Ký ức có bị ghi vu vơ không — đo tầng PROMPT + cổng phủ quyết.

    Hai chỉ số gác TUYỆT ĐỐI vì đều là hướng nguy hiểm:
      false_injection — ghi một fact người dùng không hề khai. Ký ức sai KHÔNG
        báo lỗi, nó chỉ âm thầm làm mọi câu trả lời sau tệ đi.
      leaked_doc_code — mã chứng từ lọt vào ký ức, rồi rò sang cloud chitchat
        ở lượt sau (M5/ADR-009).
    `recall` chỉ ghi nhận, chưa gác: chưa có baseline.
    """
    from src.agents import prompts as prompts_mod
    lat: list[float] = []

    async def call(case):
        prompt_name, question, want = case
        system = getattr(prompts_mod, prompt_name)
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=question)]))
        lat.append(ms)
        body = (resp.content or "").strip()
        _clean, saves, _forgets = extract_memory_markers(body)
        stored = [(k, v) for k, v in saves if not is_document_code(v)]
        if want == "none" and saves:
            return {"case": question, "want": want, "got": saves,
                    "kind": "false_injection"}
        if want == "fact" and not stored:
            return {"case": question, "want": want, "got": saves,
                    "kind": "missed"}
        if want == "blocked" and stored:
            return {"case": question, "want": want, "got": stored,
                    "kind": "leaked_doc_code"}
        return None

    fails, errors = await run_resilient(MEMORY_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(MEMORY_CASES)
    p50, p95 = _percentiles(lat)
    want_fact = sum(1 for c in MEMORY_CASES if c[2] == "fact")
    missed = sum(1 for f in fails if f["kind"] == "missed")
    return {"set": "memory", "n": n,
            "false_injection": sum(1 for f in fails if f["kind"] == "false_injection"),
            "leaked_doc_code": sum(1 for f in fails if f["kind"] == "leaked_doc_code"),
            "recall": (want_fact - missed) / want_fact if want_fact else 0.0,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

Thêm `MEMORY_CASES` vào khối import từ `evals.cases` ở đầu file.

- [ ] **Step 3: Đăng ký ở `run_eval.py::main()`**

Thêm `"memory"` vào `choices=[...]` và `"memory": eval_memory` vào `_FN`.

⚠️ Bước này chính là chỗ plan đa ngôn ngữ BỎ SÓT và chỉ lộ ra khi chạy thật (argparse từ chối "invalid choice"). Đừng lặp lại.

- [ ] **Step 4: Đăng ký ở `eval_gate.py`**

Bốn chỗ:

```python
# EVAL_FN
           "memory": run_eval.eval_memory,
# ROLE_FOR_SET
                "memory": "chitchat",
```

`_gate`, thêm nhánh (đặt cạnh nhánh `language`):

```python
    if set_name == "memory":
        # Hai điều kiện TUYỆT ĐỐI, không so baseline: cả hai đều là hướng
        # nguy hiểm (ghi vu vơ / rò mã chứng từ). recall chưa gác vì chưa có
        # baseline — ghi số vào báo cáo để người đọc tự đánh giá.
        return result["false_injection"] == 0 and result["leaked_doc_code"] == 0
```

Nhánh báo cáo `base is None` (cạnh nhánh `language`):

```python
            elif set_name == "memory":
                entry.update(false_injection=result.get("false_injection"),
                             leaked_doc_code=result.get("leaked_doc_code"),
                             recall=result.get("recall"),
                             lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"false_injection={result.get('false_injection')} "
                      f"leaked_doc_code={result.get('leaked_doc_code')} "
                      f"recall={result.get('recall')} → {'PASS' if ok else 'FAIL'}")
```

**`memory` NẰM TRONG `--set all`** (không thêm vào tuple loại trừ) vì có điều kiện an toàn tuyệt đối — đúng tiền lệ `chitchat` và `language`.

- [ ] **Step 5: Viết test cho `eval_memory`**

`backend/tests/jobs/test_eval_memory.py`:

```python
"""Bộ đo ký ức phải bắt đúng ba hướng, và không tự lừa mình."""
import pytest

from evals import run_eval
from evals.cases import MEMORY_CASES


class _Resp:
    def __init__(self, content):
        self.content = content


class _ScriptedLLM:
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, messages):
        return _Resp(self.content)


def test_moi_loai_ky_vong_deu_co_ca():
    kinds = {kind for _p, _q, kind in MEMORY_CASES}
    assert kinds == {"none", "fact", "blocked"}


async def test_ghi_vu_vo_bi_tinh_la_false_injection(monkeypatch):
    only = [("CHITCHAT_PROMPT", "hôm nay trời đẹp nhỉ", "none")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    r = await run_eval.eval_memory(_ScriptedLLM("Vâng!\nGHI_NHỚ: thời tiết = đẹp"))
    assert r["false_injection"] == 1


async def test_ma_chung_tu_lot_qua_bi_tinh_la_leak(monkeypatch):
    only = [("SYSTEM_PROMPT", "nhớ đơn P00003 nhé", "blocked")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    # Cổng is_document_code phải chặn — nếu nó chặn đúng thì KHÔNG tính leak.
    r = await run_eval.eval_memory(_ScriptedLLM("Ừ.\nGHI_NHỚ: đơn quan trọng = P00003"))
    assert r["leaked_doc_code"] == 0


async def test_khong_phat_marker_khi_can_thi_tinh_missed(monkeypatch):
    only = [("CHITCHAT_PROMPT", "từ giờ trả lời ngắn gọn", "fact")]
    monkeypatch.setattr(run_eval, "MEMORY_CASES", only)
    r = await run_eval.eval_memory(_ScriptedLLM("Vâng ạ."))
    assert r["recall"] == 0.0
    assert r["false_injection"] == 0
```

- [ ] **Step 6: Cập nhật test `--set all` của `eval_gate`**

Trong `backend/tests/jobs/test_eval_gate.py`, thêm helper (đặt cạnh
`_fake_language_eval` đã có — **đọc file thật** để khớp đúng khuôn `.calls` mà
các fake khác dùng):

```python
def _fake_memory_eval(false_injection=0, leaked_doc_code=0, recall=1.0, n=7):
    async def fn(llm, **kwargs):
        fn.calls.append(kwargs)
        return {"set": "memory", "n": n,
                "false_injection": false_injection,
                "leaked_doc_code": leaked_doc_code,
                "recall": recall,
                "lat_p50": 1, "lat_p95": 2, "fails": [], "errors": []}
    fn.calls = []
    return fn
```

Trong test `test_set_all_runs_every_registered_set_except_triple_light_gate`,
thêm ngay trước dòng `result = eval_gate.run(_args(set_="all"))`:

```python
    # memory NẰM TRONG "all": hai điều kiện an toàn TUYỆT ĐỐI
    # (false_injection == 0, leaked_doc_code == 0), đúng tiền lệ chitchat và
    # language. Không thêm vào tập loại trừ.
    fmemory = _fake_memory_eval()
    monkeypatch.setitem(eval_gate.EVAL_FN, "memory", fmemory)
```

Rồi thêm `fmemory` vào tuple "gọi đúng một lần", và thêm một assertion:

```python
    assert "memory" in result.detail
```

**Tập loại trừ GIỮ NGUYÊN 3 tên** (`gather`, `multi_source_gather`, `localize`)
nên tên test KHÔNG đổi.

Cập nhật docstring của test: thêm một câu nói rõ `memory` vào `all` vì có hai
điều kiện tuyệt đối, cùng lý do `chitchat`/`language`.

- [ ] **Step 7: Chạy test — phải XANH**

Run: `.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_memory.py tests/jobs/test_eval_gate.py -v -m "not integration and not live"`
Expected: PASS

- [ ] **Step 8: Chạy full suite**

Run: `.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: 1806 passed (1802 + 4), 2 skipped, 59 deselected

- [ ] **Step 9: Commit**

```bash
git add backend/evals/cases.py backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/jobs/test_eval_memory.py backend/tests/jobs/test_eval_gate.py
git commit -m "feat(evals): bo memory gac false_injection va leaked_doc_code tuyet doi"
```

---

## Task 8: Đo thật và nghiệm thu sống

Không viết code sản phẩm. Nhiệm vụ: chứng minh đợt này đạt, hoặc nói rõ nó không đạt ở đâu.

**Files:**
- Create: `docs/superpowers/plans/2026-08-19-user-memory-l2-report.md`

- [ ] **Step 1: Chạy migration lên DB thật**

```powershell
docker cp backend\migrations\003_user_memory.sql youdoo-postgres:/tmp/003_user_memory.sql
docker exec youdoo-postgres psql -U admin -d ai_assistant -f /tmp/003_user_memory.sql
```

- [ ] **Step 2: Chạy test tích hợp (giờ mới có bảng thật)**

Run: `.venv/Scripts/python.exe -m pytest -m integration -v`
Expected: các test `test_user_memory_postgres.py` PASS

- [ ] **Step 3: Kiểm hạn mức TRƯỚC khi chạy eval**

Sổ dùng cửa sổ TRƯỢT 24h nên có thể chặn dù nhà cung cấp đã reset. Đo bằng truy vấn `llm_usage` theo `alias` trong 24h gần nhất. Cách chạy khi cạn: xem ghi chú "nghiệm thu sống khi sổ ngân sách báo cạn".

- [ ] **Step 4: Chạy 4 cổng có thể thụt**

Tạo runner tạm **NGOÀI repo** (đừng để lại trong repo), trỏ `sys.path` vào checkout đang làm việc, rồi:

```bash
python "%TMP_RUNNER%" --set read --model gemini-3.5-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-read.json
python "%TMP_RUNNER%" --set planner --model gemini-3.5-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-planner.json
python "%TMP_RUNNER%" --set synthesis --model gemini-3.1-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-synthesis.json
python "%TMP_RUNNER%" --set multi_source --model gemini-3.1-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-multi_source.json
```

Kỳ vọng: **cả 4 GATE PASS**. Thụt cái nào thì DỪNG, ghi rõ ca nào và vì sao — KHÔNG nới baseline.

- [ ] **Step 5: Chạy bộ `memory`**

```bash
python "%TMP_RUNNER%" --set memory --model gemini-3.5-flash --pace 12.0
```

Kỳ vọng: `false_injection = 0` và `leaked_doc_code = 0` (tuyệt đối). Ghi `recall` nguyên văn — thấp thì ghi rõ ca nào trượt và nguyên văn `body`, đừng sửa case cho khớp.

⚠️ `gemini-3.5-flash` có `rpd=20`, rất chật. 7 ca là đủ, nhưng đừng chạy lại nhiều lần trong ngày.

- [ ] **Step 6: Nghiệm thu sống QUA HTTP THẬT**

Khởi động bằng `start-dev.ps1`. Bắt buộc đi qua entry point HTTP, và **gửi kèm header `x-openwebui-user-id`** (không có header này thì `user_id` rỗng và ký ức không ghi — đó là fail-closed đúng thiết kế, không phải bug).

| # | thao tác | kỳ vọng |
|---|---|---|
| 1 | Phiên A: `từ giờ trả lời ngắn gọn thôi nhé` | có dòng `📝 Đã ghi nhớ: do_dai_tra_loi = ...` |
| 2 | Kiểm DB: `SELECT * FROM user_memory WHERE user_id = ...` | đúng 1 dòng, `superseded_by IS NULL` |
| 3 | **Phiên B, session_id KHÁC HẲN**: `cho tôi xem đơn mua P00003` | câu trả lời ngắn gọn — ký ức đã vượt qua ranh giới phiên |
| 4 | Phiên B: `quên độ dài trả lời đi` | có dòng `🗑️ Đã bỏ ghi nhớ` |
| 5 | Kiểm DB lại | vẫn 1 dòng (KHÔNG bị xoá), nay `superseded_by` khác NULL |
| 6 | Phiên C: `nhớ giúp tôi đơn P00003 là quan trọng nhất` | có dòng `⚠️ Không ghi nhớ:` và DB **không** thêm dòng nào |

Kịch bản 3 là kịch bản DUY NHẤT chứng minh cả đợt hoạt động đầu-cuối. Kịch bản 5 là kịch bản duy nhất chứng minh bất biến append-only còn nguyên.

- [ ] **Step 7: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-08-19-user-memory-l2-report.md`: số đo từng bước (nguyên văn JSON), kết quả 6 kịch bản sống, mọi chỗ lệch so với dự đoán của spec, và danh sách những gì CHƯA làm được.

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/plans/2026-08-19-user-memory-l2-report.md
git commit -m "docs(report): so do va nghiem thu song cho ky uc xuyen phien L2"
```

---

## Ghi chú cho người thực thi

- **Số test kỳ vọng là số CỘNG DỒN** từ mốc 1763. Lệch thì đếm lại bằng `--collect-only` và ghi số THẬT vào báo cáo task, đừng sửa cho khớp plan.
- **Chạy lại `git status` sau mỗi lượt pytest.** Bộ test từng ghi đè file fixture đã commit; thấy file lạ "modified" mà mình không đụng thì nghi lớp lỗi đó trước.
- **Không test nào chứng minh được ký ức xuyên phiên.** Mọi khẳng định chỉ có giá trị khi đo qua HTTP thật với hai `session_id` khác nhau (Task 8 Step 6).
- **Cổng phủ quyết `is_document_code` là lưới cuối, không phải lưới duy nhất.** `MEMORY_RULE` cũng dặn model đừng ghi mã chứng từ. Nếu bộ eval cho thấy model bắn nhiều ca `blocked`, đó là tín hiệu sửa PROMPT, không phải nới cổng.
