"""Test tích hợp — cần Postgres đang chạy VÀ migration 003 đã chạy.

Chạy:  pytest tests/agents/test_user_memory_postgres.py -m integration -v
Bỏ:    pytest -m "not integration"
"""
import os
import uuid

import pytest
from psycopg_pool import AsyncConnectionPool

from src.agents.user_memory import MEMORY_CAP, forget_fact, load_active_facts, save_fact

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


async def test_vuot_tran_thi_bo_fact_cu_nhat_va_giu_fact_moi(pool, user_id):
    """MEMORY_CAP phải bỏ fact CŨ NHẤT, giữ fact MỚI NHẤT.

    Sai chiều (DESC ↔ ASC) sẽ âm thầm vứt đúng thứ người dùng VỪA nói, và
    không ca test nào khác trong file này bắt được — đó là lý do ca này tồn tại.
    """
    total = MEMORY_CAP + 2
    for i in range(total):
        await save_fact(pool, user_id, f"key_{i:03d}", f"value_{i:03d}", "t")

    keys = [key for key, _value in await load_active_facts(pool, user_id)]
    assert len(keys) == MEMORY_CAP
    assert f"key_{total - 1:03d}" in keys, "fact MỚI NHẤT phải còn hiệu lực"
    assert "key_000" not in keys, "fact CŨ NHẤT phải bị supersede"

    # Append-only: vượt trần là SUPERSEDE, không phải xoá.
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) FROM user_memory WHERE user_id = %s", (user_id,))
        assert (await cur.fetchone())[0] == total
