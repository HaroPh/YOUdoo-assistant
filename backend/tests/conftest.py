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
def so_vlm_khong_cham_postgres(request):
    """Sổ `llm_usage` của VLM phải là bản TRONG BỘ NHỚ trong test.

    Từ 2026-09-19 `VisionReader` MẶC ĐỊNH tự có sổ (`vision._SoVlm`) thay vì
    chờ người gọi tiêm — cần thiết, vì bản vá chỉ-đặt-ở-nhà-máy bị đi vòng qua
    ngay trong ngày. Nhưng nó biến mọi test đọc-thành-công bằng client giả
    thành một lượt GHI THẬT vào `public.llm_usage`: đo được 18 dòng rác
    `p=1200 c=300 t=1500` (payload giả của `test_vision.py`) lọt vào sổ sản
    xuất trong hai lượt chạy suite. Sổ ngân sách bị test bơm phồng thì mọi
    quyết định hạn mức đọc từ nó đều sai — cùng lớp lỗi với "test làm bẩn bảng
    kiểm toán" đã trả giá trước đây.

    Test `live` giữ sổ thật: đó là lúc lượt gọi CÓ thật và đáng được đếm."""
    from src.ocr import vision
    if request.node.get_closest_marker("live") is not None:
        return
    from src.llm.store import InMemoryUsageStore
    cu_store, cu_thu = vision._SoVlm._store, vision._SoVlm._da_thu
    vision._SoVlm._store, vision._SoVlm._da_thu = InMemoryUsageStore(), True
    yield
    vision._SoVlm._store, vision._SoVlm._da_thu = cu_store, cu_thu


@pytest.fixture(autouse=True)
def vlm_keys_off_unless_live(request, monkeypatch):
    """Khoá VLM (`YOUDOO_VLM_API_KEY*`) chỉ tồn tại trong test đánh dấu `live`.
    Không có fixture này, một test đơn vị đi qua `parse_pdf` với trang có tiêu
    đề báo cáo chính sẽ gọi Gemini THẬT khi .env có khoá — đúng lớp sự cố
    "pytest trần chạm API thật" đã xảy ra một lần trong repo. Test không-live
    muốn VLM phải tiêm client giả qua `parse.VISION_READER_FACTORY`."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("YOUDOO_VLM_API_KEY", raising=False)
        for i in range(2, 10):
            monkeypatch.delenv(f"YOUDOO_VLM_API_KEY_{i}", raising=False)


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
