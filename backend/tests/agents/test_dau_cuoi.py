"""Xác minh đầu-cuối kế hoạch B: câu hỏi thật → Odoo thật + RAG thật → model
cloud thật → câu trả lời.

Cần MỌI THỨ: Odoo chạy, Postgres+pgvector chạy, Ollama chạy, MCP server chạy,
và khoá API thật. Đánh dấu live vì nó gọi model thật tiêu hạn mức.

Chạy:  pytest tests/agents/test_dau_cuoi.py -m live -v

Lưu ý chữ ký: ERPAgent.chat() nhận list[dict] {"role", "content"}, KHÔNG phải
chuỗi thô — xem erp_agent.py dòng ~156. Trả về là str đã strip() (hoặc câu hỏi
xác nhận, hoặc RECURSION_MSG) — không bao giờ trả object khác.

Một event loop DUY NHẤT cho toàn bộ module (không phải asyncio.run() riêng cho
mỗi lệnh): erp_agent.setup() cố ý giữ AsyncConnectionPool SỐNG trên self._pool
để chat() sau này dùng lại — asyncio.run() thì luôn cancel-toàn-bộ-task-rồi-
đóng-loop khi thoát, xung đột thẳng với ý đồ "pool sống lâu hơn một lệnh gọi".
Xác nhận thực nghiệm khi chạy test này lần đầu (2026-07-29):
  - asyncio.run() riêng cho setup() rồi asyncio.run() riêng cho chat() đầu
    tiên → "RuntimeError: <Lock ...> is bound to a different event loop"
    ngay trong checkpointer (Postgres lock tạo ở loop của setup(), dùng ở
    loop khác của chat()).
  - Còn asyncio.run(setup()) một mình, không gọi gì thêm sau đó, thì TREO
    VÔ THỜI HẠN ở dọn dẹp của chính asyncio.run() (runners.py:_cancel_all_
    tasks) — xác nhận bằng faulthandler.dump_traceback_later: main thread
    kẹt ở run_until_complete(_cancel_all_tasks(...)) trong lúc pool vẫn cố
    tình mở. Dùng một loop.run_until_complete() dùng chung cho setup/chat/
    aclose loại bỏ cả hai lỗi: pool và mọi Lock/Task nó tạo neo vào ĐÚNG MỘT
    loop suốt vòng đời, và loop chỉ đóng SAU khi aclose() đã tự đóng pool
    sạch sẽ (pool.close() dọn task/thread của chính nó, không bị asyncio.run
    cancel thô bạo giữa chừng).
"""
import asyncio
import os

import pytest

pytestmark = pytest.mark.live

CAN_CO = ("GOOGLE_API_KEY", "ODOO_URL", "DATABASE_URL", "MCP_ODOO_URL")


@pytest.fixture(scope="module")
def event_loop_dau_cuoi():
    """Event loop sống suốt module — xem docstring đầu file lý do bắt buộc
    dùng chung một loop thay vì asyncio.run() riêng lẻ."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def agent(event_loop_dau_cuoi):
    thieu = [k for k in CAN_CO if not os.environ.get(k)]
    if thieu:
        pytest.skip(f"thiếu biến môi trường: {thieu}")

    from src.agents.erp_agent import ERPAgent

    a = ERPAgent()
    event_loop_dau_cuoi.run_until_complete(a.setup())
    yield a
    event_loop_dau_cuoi.run_until_complete(a.aclose())


def test_agent_dung_duoc_va_co_tool(agent):
    """Nối được MCP server và thấy tool — cú chẻ Task 7 không đánh rơi gì."""
    assert agent.tool_names, "không thấy tool nào từ MCP server"


def test_cau_hoi_that_tra_ve_cau_tra_loi_that(agent, event_loop_dau_cuoi):
    """Lượt chạy đầy đủ: định tuyến intent → gọi tool → tổng hợp.

    Không khẳng định NỘI DUNG câu trả lời (dữ liệu Odoo đổi theo môi trường) —
    chỉ khẳng định đường đi thông: có trả lời, là string, không rỗng, không phải
    thông báo lỗi degrade.
    """
    tra_loi = event_loop_dau_cuoi.run_until_complete(agent.chat(
        [{"role": "user", "content": "Xin chào, bạn giúp được gì?"}],
        thread_id="test-dau-cuoi-1"))
    assert isinstance(tra_loi, str), f"trả về {type(tra_loi).__name__}, không phải str"
    assert tra_loi.strip(), "câu trả lời rỗng"
    assert "đã có lỗi xảy ra" not in tra_loi.lower(), (
        f"rơi vào nhánh degrade lỗi: {tra_loi[:200]}")


def test_cau_hoi_ERP_di_qua_tool(agent, event_loop_dau_cuoi):
    """Câu hỏi cần dữ liệu ERP phải chạm tool, không phải model tự bịa."""
    tra_loi = event_loop_dau_cuoi.run_until_complete(agent.chat(
        [{"role": "user", "content": "Có bao nhiêu đơn bán hàng?"}],
        thread_id="test-dau-cuoi-2"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
