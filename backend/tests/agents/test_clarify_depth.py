# backend/tests/agents/test_clarify_depth.py
"""Node hỏi lại khi router không chắc người dùng muốn chạy đủ quy trình hay
làm nhanh một bước.

Đo 2026-08-16: `unsure` bắn 2/18 ca (11%) và cả hai đều mơ hồ thật, tất định
qua 3 lượt. Đây là đường DUY NHẤT thật sự mới của đợt này.
"""
import pytest

from src.agents.nodes import CLARIFY_DEPTH_OPTIONS, make_clarify_depth_node
from src.agents.routing import route_after_clarify


def test_hai_lua_chon_dung_id_khop_valid_depths():
    """id của lựa chọn ĐI THẲNG vào state["depth"] qua Command(resume=...),
    nên phải là giá trị depth hợp lệ, không phải nhãn hiển thị."""
    from src.agents.routing import VALID_DEPTHS
    ids = [o["id"] for o in CLARIFY_DEPTH_OPTIONS]
    assert ids == ["full_sop", "one_step"]
    assert set(ids) <= VALID_DEPTHS
    assert all(o["name"].strip() for o in CLARIFY_DEPTH_OPTIONS)


@pytest.mark.asyncio
async def test_node_park_bang_interrupt_dang_disambiguation(monkeypatch):
    """kind PHẢI là "disambiguation": erp_agent._decide_resume parse lựa chọn
    TẤT ĐỊNH cho kind đó (parse_selection). Rơi về "confirm" sẽ ép câu trả lời
    qua bộ phân loại có/không và phá hẳn lượt hỏi hai lựa chọn."""
    import src.agents.nodes as nodes_mod
    da_goi = {}

    def gia_interrupt(payload):
        da_goi.update(payload)
        return "full_sop"

    monkeypatch.setattr(nodes_mod, "_interrupt", gia_interrupt)
    node = make_clarify_depth_node()
    out = await node({"messages": [], "sop": "nhap-kho", "depth": "unsure"})

    assert da_goi["kind"] == "disambiguation"
    assert da_goi["options"] == CLARIFY_DEPTH_OPTIONS
    assert da_goi["question"].strip()
    assert out["depth"] == "full_sop"


@pytest.mark.asyncio
async def test_tra_loi_khong_hop_le_thi_ve_full_sop(monkeypatch):
    """FAIL AN TOÀN, cùng lý do với parse_proposal: chiều one_step là chiều bỏ
    qua kiểm tra, không bao giờ là mặc định khi không hiểu câu trả lời."""
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_interrupt", lambda payload: "banana")
    node = make_clarify_depth_node()
    out = await node({"messages": [], "sop": "nhap-kho", "depth": "unsure"})
    assert out["depth"] == "full_sop"


def test_sau_khi_chon_thi_di_dung_dich():
    assert route_after_clarify(
        {"sop": "nhap-kho", "depth": "full_sop"}) == "nhap-kho"
    assert route_after_clarify(
        {"sop": "nhap-kho", "depth": "one_step"}) == "erp_write"


def test_mat_sop_thi_khong_treo_lai():
    """`sop` TRANSIENT. Nếu vì lý do nào đó nó rỗng lúc quay lại, phải có đích
    đi tiếp chứ không được trả một tên node không tồn tại."""
    assert route_after_clarify({"sop": None, "depth": "full_sop"}) == "erp_write"


def test_clarify_depth_co_mat_trong_graph_that():
    """Đường dây graph phải có test canh. Đo được ở đợt bản-tin-việc-cần-xử-lý:
    hardcode role=None mà 1564/1565 test vẫn xanh, vì không test nào dựng graph
    thật để kiểm cạnh.

    KHÔNG được chỉ kiểm "có cạnh ra nào đó": thực đo thấy LangGraph tự thêm
    cạnh ngầm clarify_depth -> "__end__" cho một node KHÔNG có
    add_conditional_edges nào cả (node cụt thành lá) — nên assertion "canh_ra
    không rỗng" xanh CẢ KHI dòng add_conditional_edges("clarify_depth", ...)
    bị xoá hẳn (xác nhận thực nghiệm khi phá thử Step 7). Phải đòi đúng ĐÍCH
    THẬT (erp_write_planner) mới bắt được lỗi thiếu dây."""
    from src.agents.graph import build_graph
    from tests.conftest import make_mock_llm

    llms = {k: make_mock_llm("intent: rag\nsop:\ndepth: none")
            for k in ("router", "read", "planner", "rag", "fusion",
                      "synthesis", "chitchat", "evaluator")}
    graph = build_graph(llms, tools=[], checkpointer=None)
    ve = graph.get_graph()
    assert "clarify_depth" in ve.nodes
    canh_ra = {(e.target, e.conditional) for e in ve.edges
              if e.source == "clarify_depth"}
    assert ("erp_write_planner", True) in canh_ra, (
        "clarify_depth không có cạnh có điều kiện tới erp_write_planner — "
        "người dùng chọn xong sẽ kẹt tại __end__ ngầm của LangGraph")
    assert ("__end__", False) not in canh_ra, (
        "clarify_depth chỉ còn cạnh cụt ngầm tới __end__ — route_after_clarify "
        "chưa được đấu dây")
