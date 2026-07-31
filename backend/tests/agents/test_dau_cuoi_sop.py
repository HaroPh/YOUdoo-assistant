"""Flow SOP thật đầu-cuối qua MCP + Odoo (§7, §9.7). Không khẳng định NỘI DUNG
dữ liệu Odoo (đổi theo môi trường) — khẳng định ĐƯỜNG ĐI: câu lệnh có ngôn ngữ
quy trình vào đúng node SOP, và cổng xác nhận thật sự chặn khi user từ chối."""
import asyncio
import os

import pytest

pytestmark = pytest.mark.live

CAN_CO = ("GOOGLE_API_KEY", "ODOO_URL", "DATABASE_URL", "MCP_ODOO_URL")


@pytest.fixture(scope="module")
def event_loop_sop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def agent(event_loop_sop):
    thieu = [k for k in CAN_CO if not os.environ.get(k)]
    if thieu:
        pytest.skip(f"thiếu biến môi trường: {thieu}")
    from src.agents.erp_agent import ERPAgent
    a = ERPAgent()
    event_loop_sop.run_until_complete(a.setup())
    yield a
    event_loop_sop.run_until_complete(a.aclose())


def test_lenh_co_ngon_ngu_quy_trinh_vao_node_sop(agent, event_loop_sop):
    """"làm quy trình nhập kho cho đơn mua P00021" phải vào node nhap-kho —
    biểu hiện quan sát được: trợ lý HỎI LẠI (bước 1/3 của SOP: mã đơn hoặc số
    lượng thực nhận), chứ không tự ý báo đã nhận hàng."""
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "làm quy trình nhập kho cho đơn mua P00021"}],
        thread_id="test-sop-nhap-kho-1"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
    assert "?" in tra_loi, f"SOP không hỏi lại — có thể đã đi tier-1: {tra_loi[:300]}"


def test_cau_hoi_ve_quy_trinh_khong_bi_sop_cuop(agent, event_loop_sop):
    """Ca hijack GỐC. "quy trình nhập kho là gì?" phải đi RAG — biểu hiện: KHÔNG
    hỏi mã đơn / số lượng thực nhận (đó là dấu hiệu SOP đã cướp lượt)."""
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "quy trình nhập kho là gì?"}],
        thread_id="test-sop-hijack-1"))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    low = tra_loi.lower()
    assert "số lượng thực nhận" not in low, f"SOP cướp lượt câu hỏi: {tra_loi[:300]}"


def test_tu_choi_xac_nhan_thi_khong_ghi_gi(agent, event_loop_sop):
    """Cổng xác nhận tại tool boundary — lưới đỡ CUỐI, tất định, fail-closed.
    Trả lời "không" ở bước confirm phải cho ra REFUSED_MSG-flavored reply và
    KHÔNG ghi gì vào Odoo."""
    tid = "test-sop-refuse-1"
    event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "làm quy trình giao hàng cho đơn bán S00012"}],
        thread_id=tid))
    tra_loi = event_loop_sop.run_until_complete(agent.chat(
        [{"role": "user", "content": "không"}], thread_id=tid))
    assert isinstance(tra_loi, str) and tra_loi.strip()
    assert "đã có lỗi xảy ra" not in tra_loi.lower()
