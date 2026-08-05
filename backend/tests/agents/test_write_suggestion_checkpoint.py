"""Test tích hợp — cần Postgres đang chạy.

Chạy:  pytest tests/agents/test_write_suggestion_checkpoint.py -m integration -v
Bỏ:    pytest -m "not integration"

VÌ SAO PHẢI LÀ INTEGRATION TEST, KHÔNG PHẢI UNIT TEST MOCK: state.py ghi rõ
bài học SP-1C2 — có loại lỗi CHỈ hỏng khi checkpointer Postgres thật chạy
(dữ liệu không JSON-thuần đi qua sạch mọi unit test rồi hỏng trên production).
Toàn bộ cơ chế ở đây dựa vào việc additional_kwargs sống sót vòng lưu/đọc
checkpoint, nên phải đo bằng Postgres thật.
"""
import os
import sys
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.agents.state import ERPAgentState
from src.agents.routing import replying_to_write_suggestion

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")


async def test_co_suggested_write_song_sot_qua_checkpoint_postgres():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    if sys.platform == "win32":
        # psycopg3 async KHÔNG chạy trên ProactorEventLoop (xem backend/run.py).
        import asyncio
        if not isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
            pytest.skip("cần SelectorEventLoop trên Windows")

    pool = AsyncConnectionPool(
        # min_size tường minh: psycopg_pool (>=3.2) mặc định min_size=4, và
        # min_size > max_size ném ValueError NGAY TẠI __init__, trước khi kịp
        # chạm Postgres — không phải lỗi của brief gốc mà là version khác lúc
        # viết brief; sửa tối thiểu để pool nhỏ (2 kết nối) vẫn hợp lệ.
        conninfo=DSN, min_size=1, max_size=2, open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0,
                "row_factory": dict_row})
    await pool.open()
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()

        async def node(state):
            return {"messages": [AIMessage(
                content="Bạn có muốn tôi tạo đơn mua không?",
                additional_kwargs={"suggested_write": True})]}

        g = StateGraph(ERPAgentState)
        g.add_node("a", node)
        g.add_edge(START, "a")
        g.add_edge("a", END)
        graph = g.compile(checkpointer=cp)

        tid = "test-write-suggest-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": tid}}
        await graph.ainvoke(
            {"messages": [HumanMessage(content="tôi muốn nhập 20 cái")]},
            config=config)

        # ĐỌC LẠI TỪ POSTGRES, không dùng giá trị in-memory vừa trả về
        snap = await graph.aget_state(config)
        msgs = snap.values["messages"]
        last_ai = [m for m in msgs if m.type == "ai"][-1]
        assert last_ai.additional_kwargs.get("suggested_write") is True

        # và decide_route đọc được cờ đó sau khi qua checkpoint
        assert replying_to_write_suggestion(
            {"messages": [*msgs, HumanMessage(content="okay")]}) is True

        await cp.adelete_thread(tid)
    finally:
        await pool.close()
