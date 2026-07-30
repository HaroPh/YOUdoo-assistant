from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.llm.tokens import estimate_base_tokens


def test_khong_co_gi_thi_bang_khong():
    assert estimate_base_tokens([]) == 0


def test_tin_nhan_dai_hon_thi_uoc_luong_lon_hon():
    ngan = estimate_base_tokens([HumanMessage("Xin chào")])
    dai = estimate_base_tokens([HumanMessage("Xin chào " * 200)])
    assert dai > ngan > 0


def test_cong_don_qua_nhieu_tin_nhan():
    mot = estimate_base_tokens([HumanMessage("Tồn kho sản phẩm ABC?")])
    ba = estimate_base_tokens([
        SystemMessage("Bạn là trợ lý ERP."),
        HumanMessage("Tồn kho sản phẩm ABC?"),
        AIMessage("Sản phẩm ABC còn 42 cái."),
    ])
    assert ba > mot


def test_schema_tool_duoc_tinh_vao():
    """Agent ERP bind hàng chục tool — phần schema thường lớn hơn câu hỏi."""
    msgs = [HumanMessage("Tồn kho ABC?")]
    tools = [{
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Tra tồn kho theo tên sản phẩm trong hệ thống Odoo",
            "parameters": {
                "type": "object",
                "properties": {"product": {"type": "string"}},
                "required": ["product"],
            },
        },
    }]
    assert estimate_base_tokens(msgs, tools) > estimate_base_tokens(msgs)


def test_chap_nhan_dict_kieu_openai_lan_message_cua_langchain():
    """Đường eval dựng message dạng dict thô; graph dùng message LangChain."""
    dang_dict = estimate_base_tokens([{"role": "user", "content": "Tồn kho ABC?"}])
    dang_obj = estimate_base_tokens([HumanMessage("Tồn kho ABC?")])
    assert dang_dict > 0 and dang_obj > 0
    assert abs(dang_dict - dang_obj) <= 5


def test_noi_dung_rong_khong_lam_no_vo():
    assert estimate_base_tokens([HumanMessage("")]) >= 0
    assert estimate_base_tokens([{"role": "user", "content": None}]) >= 0


def test_ket_qua_la_so_nguyen_khong_am():
    got = estimate_base_tokens([HumanMessage("Tồn kho ABC?")])
    assert isinstance(got, int) and got >= 0


def test_tiktoken_khong_nap_duoc_thi_tut_ve_uoc_luong_tho(monkeypatch):
    """Blocker #3: đường mặc định không được chạm mạng. Mô phỏng lỗi nạp
    (giống lần đầu chạy không có cache, CI lạnh) — hàm vẫn phải trả số dùng
    được, không ném lỗi, không thử nạp lại lần thứ hai trong cùng test."""
    import src.llm.tokens as tokens_mod

    monkeypatch.setattr(tokens_mod, "_enc", None)
    monkeypatch.setattr(tokens_mod, "_enc_failed", False)

    def _no_mang(*a, **k):
        raise OSError("network is unreachable (mô phỏng)")

    monkeypatch.setattr(tokens_mod.tiktoken, "get_encoding", _no_mang)

    from langchain_core.messages import HumanMessage
    n = tokens_mod.estimate_base_tokens([HumanMessage("một hai ba bốn")])
    assert n > 0
    assert tokens_mod._enc_failed is True

    # Gọi lại lần 2 KHÔNG được thử nạp lại (đã đánh dấu thất bại)
    calls_before = 0
    def _dem(*a, **k):
        nonlocal calls_before
        calls_before += 1
        raise OSError("vẫn không có mạng")
    monkeypatch.setattr(tokens_mod.tiktoken, "get_encoding", _dem)
    tokens_mod.estimate_base_tokens([HumanMessage("lượt hai")])
    assert calls_before == 0
