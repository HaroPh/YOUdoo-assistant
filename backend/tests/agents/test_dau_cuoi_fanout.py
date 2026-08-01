# backend/tests/agents/test_dau_cuoi_fanout.py
"""Xác minh sống fan-out `mixed` (SP-2b) — LLM thật, Postgres thật, RAG thật,
MCP/Odoo thật.

Chạy: pytest tests/agents/test_dau_cuoi_fanout.py -m live -v

Lưu ý chữ ký thật của ERPAgent (đọc từ src/agents/erp_agent.py, KHÔNG suy
đoán): `chat()` nhận `messages: list[dict]` dạng {"role", "content"} — không
phải chuỗi thô; và phương thức đóng pool tên là `aclose()`, không phải
`close()`. Trả về của `chat()` là str đã `.strip()`.
"""
import pytest

pytestmark = pytest.mark.live


async def test_mixed_question_returns_one_grounded_answer_with_citations():
    from src.agents.erp_agent import ERPAgent
    agent = ERPAgent()
    await agent.setup()
    try:
        answer = await agent.chat(
            [{"role": "user",
              "content": "Theo chính sách hoàn hàng, đơn S00042 còn hoàn được không?"}],
            thread_id="sp2b-live-fanout")
    finally:
        await agent.aclose()
    assert answer.strip()
    # fuse_answer phải đính khối trích dẫn tất định khi có chân tài liệu
    assert "📄 Nguồn:" in answer
    # KHÔNG được lộ marker nội bộ ra người dùng
    assert "NGUỒN_DÙNG" not in answer
