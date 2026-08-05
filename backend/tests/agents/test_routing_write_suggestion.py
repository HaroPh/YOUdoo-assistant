"""Điều kiện tất định mới của decide_route: trả lời ngắn gọn cho một ĐỀ XUẤT
GHI ở lượt trước phải đi vào erp_write, không rơi về chitchat.

Bug thật đã xảy ra (2026-08-05): fuse_answer gợi ý "Bạn có muốn tôi tiến hành
tạo đơn mua ... không?", user trả lời "okay" → rơi vào chitchat, mất ngữ cảnh.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.routing import decide_route, replying_to_write_suggestion


def _ai_goi_y(text="Bạn có muốn tôi tạo đơn mua không?"):
    return AIMessage(content=text, additional_kwargs={"suggested_write": True})


def _ai_thuong(text="Đơn S00012 đang ở trạng thái nháp."):
    return AIMessage(content=text)


# ── hướng DƯƠNG ──────────────────────────────────────────────────────────────

def test_dong_y_ngan_gon_sau_de_xuat_ghi_thi_route_erp_write():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="okay")],
             "intent": "unknown", "sop": None}
    assert decide_route(state) == "erp_write"


def test_thang_intent_router_du_router_de_xuat_khac():
    """Điều kiện này là lớp PHỦ QUYẾT — thắng cả đề cử của router LLM."""
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="có")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "erp_write"


# ── hướng ÂM (chống hồi quy hội thoại thường) ────────────────────────────────

def test_khong_co_co_thi_khong_ep_route():
    """RAG/chitchat cũng hay hỏi '...không?' — KHÔNG được ép sang erp_write."""
    state = {"messages": [HumanMessage(content="chính sách hoàn hàng?"),
                          _ai_thuong("Bạn có muốn tôi giải thích thêm không?"),
                          HumanMessage(content="ok")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "rag"


def test_tra_loi_tu_choi_thi_khong_ep_route():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="không")],
             "intent": "unknown", "sop": None}
    assert decide_route(state) == "unknown"


def test_tra_loi_dai_khong_phai_xac_nhan_thi_khong_ep_route():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="thế còn nhà cung cấp khác thì sao?")],
             "intent": "erp_read", "sop": None}
    assert decide_route(state) == "erp_read"


def test_co_moi_hon_khong_mang_co_thi_vo_hieu_hoa_co_cu():
    """Tự hết hạn: decide_route chỉ đọc AI message MỚI NHẤT, nên một câu trả
    lời mới không mang cờ sẽ tự vô hiệu hoá cờ của lượt cũ — không cần cơ chế
    dọn dẹp nào."""
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="chính sách hoàn hàng?"),
                          _ai_thuong(),
                          HumanMessage(content="ok")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "rag"


def test_khong_co_ai_message_nao_thi_an_toan():
    """eval_sop_select dựng state chỉ có MỘT human message — điều kiện mới
    phải là no-op ở đó, nếu không sẽ làm lệch bộ eval đang đo decide_route."""
    state = {"messages": [HumanMessage(content="ok")],
             "intent": "erp_read", "sop": None}
    assert replying_to_write_suggestion(state) is False
    assert decide_route(state) == "erp_read"
