"""Điều kiện tất định mới của decide_route: trả lời ngắn gọn cho một ĐỀ XUẤT
GHI ở lượt trước phải đi vào erp_write, không rơi về chitchat.

Bug thật đã xảy ra (2026-08-05): fuse_answer gợi ý "Bạn có muốn tôi tiến hành
tạo đơn mua ... không?", user trả lời "okay" → rơi vào chitchat, mất ngữ cảnh.

Tín hiệu đi qua HAI STATE KEY RIÊNG (`suggested_write` + neo `suggested_write_at`),
KHÔNG qua AIMessage.additional_kwargs. Bản đầu dùng additional_kwargs đã được
final review đo là hỏng trong production: erp_agent._invoke_fresh dựng lại toàn
bộ kênh "messages" từ history text thuần của client trên MỌI lượt không parked
nên cờ trên message không sống nổi một lượt. Các test dưới đây vì thế dựng state
thẳng bằng key riêng — đó chính là hình dạng state mà decide_route gặp thật.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.routing import decide_route, replying_to_write_suggestion


def _ai(text="Bạn có muốn tôi tạo đơn mua không?"):
    """AIMessage TRẦN — cố ý không mang additional_kwargs: cơ chế mới không
    đọc gì từ message ngoài phần human cuối."""
    return AIMessage(content=text)


def _state(messages, *, suggested_write=None, at=None, intent="unknown"):
    state = {"messages": messages, "intent": intent, "sop": None}
    if suggested_write is not None:
        state["suggested_write"] = suggested_write
    if at is not None:
        state["suggested_write_at"] = at
    return state


def _sau_de_xuat(reply: str, intent="unknown"):
    """State của lượt NGAY SAU một đề xuất ghi: 3 message (hỏi, đáp, trả lời
    mới) và neo = 2 → len(messages) == at + 1, đúng điều kiện tin cờ."""
    return _state([HumanMessage(content="tôi muốn nhập 20 cái"),
                   _ai(),
                   HumanMessage(content=reply)],
                  suggested_write=True, at=2, intent=intent)


# ── hướng DƯƠNG ──────────────────────────────────────────────────────────────

def test_dong_y_ngan_gon_sau_de_xuat_ghi_thi_route_erp_write():
    assert decide_route(_sau_de_xuat("okay")) == "erp_write"


def test_thang_intent_router_du_router_de_xuat_khac():
    """Điều kiện này là lớp PHỦ QUYẾT — thắng cả đề cử của router LLM."""
    assert decide_route(_sau_de_xuat("có", intent="rag")) == "erp_write"


def test_co_doc_tu_state_key_khong_phai_tu_additional_kwargs():
    """Ca hồi quy cho ĐÚNG cái bug mà thiết kế này đóng lại.

    Cờ nằm ở state dict, message hoàn toàn TRẦN (không additional_kwargs) —
    đây là hình dạng state duy nhất tồn tại trong production sau khi
    _invoke_fresh dựng lại kênh messages từ payload {"role","content"} của
    client. Cơ chế cũ đọc message nên ở đây sẽ trả False.
    """
    state = _sau_de_xuat("ok")
    assert all(not getattr(m, "additional_kwargs", None)
               for m in state["messages"])
    assert replying_to_write_suggestion(state) is True


def test_co_tren_additional_kwargs_khong_con_duoc_doc():
    """Chiều ngược lại của cùng ranh giới: cơ chế MỚI không được lén đọc lại
    message — cờ chỉ nằm trên message (không có state key) phải là KHÔNG."""
    state = _state([HumanMessage(content="tôi muốn nhập 20 cái"),
                    AIMessage(content="Bạn có muốn tôi tạo đơn mua không?",
                              additional_kwargs={"suggested_write": True}),
                    HumanMessage(content="ok")])
    assert replying_to_write_suggestion(state) is False
    assert decide_route(state) == "unknown"


# ── hướng ÂM (chống hồi quy hội thoại thường) ────────────────────────────────

def test_khong_co_co_thi_khong_ep_route():
    """RAG/chitchat cũng hay hỏi '...không?' — KHÔNG được ép sang erp_write."""
    state = _state([HumanMessage(content="chính sách hoàn hàng?"),
                    _ai("Bạn có muốn tôi giải thích thêm không?"),
                    HumanMessage(content="ok")],
                   suggested_write=False, at=2, intent="rag")
    assert decide_route(state) == "rag"


def test_tra_loi_tu_choi_thi_khong_ep_route():
    assert decide_route(_sau_de_xuat("không")) == "unknown"


def test_tra_loi_dai_khong_phai_xac_nhan_thi_khong_ep_route():
    assert decide_route(_sau_de_xuat("thế còn nhà cung cấp khác thì sao?",
                                     intent="erp_read")) == "erp_read"


def test_co_cu_het_han_khi_da_qua_them_luot_khac():
    """TỰ HẾT HẠN theo neo độ dài: cờ đặt từ mấy lượt trước (at=2) nhưng
    messages đã dài thêm hơn 1 (có một lượt hỏi-đáp khác xen giữa) → không
    được bắn phủ quyết. Nhờ neo này KHÔNG node nào phải chủ động dọn cờ."""
    state = _state([HumanMessage(content="tôi muốn nhập 20 cái"),
                    _ai(),
                    HumanMessage(content="chính sách hoàn hàng?"),
                    _ai("Hoàn hàng trong 30 ngày."),
                    HumanMessage(content="ok")],
                   suggested_write=True, at=2, intent="rag")
    assert len(state["messages"]) > state["suggested_write_at"] + 1
    assert replying_to_write_suggestion(state) is False
    assert decide_route(state) == "rag"


def test_thieu_neo_thi_khong_tin_co():
    """Cờ True nhưng không có neo (checkpoint cũ từ trước fix wave, hoặc node
    nào đó chỉ ghi một nửa) → fail an toàn."""
    state = _state([HumanMessage(content="tôi muốn nhập 20 cái"),
                    _ai(),
                    HumanMessage(content="ok")],
                   suggested_write=True, intent="unknown")
    assert replying_to_write_suggestion(state) is False


def test_khong_co_ai_message_nao_thi_an_toan():
    """eval_sop_select dựng state chỉ có MỘT human message — điều kiện mới
    phải là no-op ở đó, nếu không sẽ làm lệch bộ eval đang đo decide_route."""
    state = _state([HumanMessage(content="ok")], intent="erp_read")
    assert replying_to_write_suggestion(state) is False
    assert decide_route(state) == "erp_read"


def test_khong_co_human_message_thi_an_toan():
    state = _state([_ai()], suggested_write=True, at=0)
    assert replying_to_write_suggestion(state) is False
