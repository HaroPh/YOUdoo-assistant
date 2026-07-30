# backend/tests/conftest.py
import os
import sys

import pytest
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from unittest.mock import AsyncMock, MagicMock

# Windows: psycopg async (AsyncConnectionPool/AsyncPostgresSaver, dùng bởi
# erp_agent.setup() — Task 13) không chạy được trên ProactorEventLoop, mặc
# định của asyncio trên Windows từ 3.8. Thiếu dòng này, MỌI asyncio.run() chạm
# Postgres qua đường async treo ~30s rồi psycopg_pool.PoolTimeout — dù Postgres
# đang chạy tốt và một connect SYNC tới đúng conninfo thành công tức thì (xác
# nhận thực nghiệm khi chạy test_dau_cuoi.py -m live lần đầu). Chỉ ảnh hưởng
# máy dev Windows chạy pytest trực tiếp; container Linux dùng
# SelectorEventLoop mặc định nên không cần policy này.
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Nạp .env ở gốc repo TRƯỚC khi bất kỳ test module nào chạy code cấp module
# (vd rag/config.py đọc os.environ.get("DATABASE_URL", ...) ngay khi import).
# Dùng đường dẫn tuyệt đối theo __file__ — không dựa vào cwd lúc pytest chạy,
# vì cwd có thể không phải gốc repo tùy cách gọi (vd chạy từ backend/).
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def make_mock_llm(response_text: str):
    """Return a mock LLM that always responds with response_text."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=response_text))
    return llm


def make_mock_llm_seq(responses):
    """Mock LLM trả lần lượt từng phần tử — cho test corrective retry (A5).
    Gọi quá số phần tử sẽ raise StopIteration → lộ ngay lỗi gọi thừa."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        side_effect=[AIMessage(content=r) for r in responses])
    return llm


@pytest.fixture(autouse=True)
def friction_log_path(tmp_path, monkeypatch):
    """Mọi test ghi friction vào tmp — không làm bẩn logs/planner_friction.jsonl
    thật. File thật là telemetry dùng để ra quyết định (spec 2026-07-12);
    event từ test (model='mock') sẽ làm sai lệch tỷ lệ nếu lọt vào."""
    p = tmp_path / "friction.jsonl"
    monkeypatch.setenv("FRICTION_LOG_PATH", str(p))
    return p


@pytest.fixture(autouse=True)
def semantic_resolve_off(monkeypatch):
    """resolve_entity đi đường legacy từng bit trong test — không PG/Ollama,
    không bao giờ chạm reranker 2.3GB (spec 2026-07-13 §11). Test nào bật
    "1" phải mock cả semantic.semantic_candidates lẫn reranker.score_pairs."""
    monkeypatch.setenv("ERP_SEMANTIC_RESOLVE", "0")


@pytest.fixture(autouse=True)
def langfuse_tat_cho_test_khong_live(request, monkeypatch):
    """Test không đánh dấu `live` không bao giờ được chạm Langfuse thật — dù
    .env cục bộ CÓ sẵn LANGFUSE_PUBLIC_KEY/SECRET_KEY thật (vd sau khi chạy
    xác nhận sống SP-1C2, Task 8 — đúng tình huống thường gặp trong worktree
    này). Bất biến toàn dự án: test mặc định không chạm mạng (xem Global
    Constraints, spec SP-1C2). Test đánh dấu `live` giữ nguyên biến thật."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
