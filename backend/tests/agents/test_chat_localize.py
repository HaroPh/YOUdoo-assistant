# backend/tests/agents/test_chat_localize.py
"""chat() bọc MỌI đường ra qua localize.

Vá từng `return` là để sót — chat() có SÁU chỗ trả về, và những đường thêm
sau này sẽ không ai nhớ vá. Lớp bọc phủ hết.
"""
import pytest

from src.agents import erp_agent as agent_mod


class _AgentGia(agent_mod.ERPAgent):
    """Chỉ thay _chat_inner: phần còn lại của chat() (lớp bọc) là thứ đang đo."""
    def __init__(self, tra_ve):
        self._tra_ve = tra_ve
        self._llms = {"evaluator": None}
        self._localize_calls = []

    async def _chat_inner(self, messages, thread_id=None, reset_if_fresh=False,
                          role="admin", user_id=None):
        return self._tra_ve


@pytest.mark.asyncio
async def test_hoi_tieng_viet_thi_khong_dich(monkeypatch):
    goi = []

    async def gia_localize(text, lang, llm):
        goi.append(lang)
        return text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user", "content": "nhận hàng cho đơn P00003"}])
    assert out == "Bạn xác nhận giúp mình nhé?"
    assert goi == ["vi"]


@pytest.mark.asyncio
async def test_hoi_tieng_anh_thi_di_qua_localize(monkeypatch):
    async def gia_localize(text, lang, llm):
        return "TRANSLATED" if lang == "en" else text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user",
                         "content": "receive the goods for order P00003"}])
    assert out == "TRANSLATED"


@pytest.mark.asyncio
async def test_luot_tra_loi_ngan_van_giu_ngon_ngu_cua_luot_dau(monkeypatch):
    """Lượt xác nhận chỉ là "yes" — quá ngắn để nhận diện. Client thật gửi đủ
    lịch sử, nên câu hỏi tiếng Anh mở đầu vẫn quyết đúng ngôn ngữ. Đây là ca
    làm cho luồng GHI bằng tiếng Anh không bị đứt giữa chừng."""
    async def gia_localize(text, lang, llm):
        return "TRANSLATED" if lang == "en" else text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Đã nhận hàng cho đơn P00003.")
    out = await a.chat([
        {"role": "user", "content": "receive the goods for order P00003"},
        {"role": "assistant", "content": "Bạn xác nhận giúp mình nhé?"},
        {"role": "user", "content": "yes"},
    ])
    assert out == "TRANSLATED"


@pytest.mark.asyncio
async def test_localize_nem_thi_van_tra_duoc_cau_goc(monkeypatch):
    """Bất biến: một lượt chat không bao giờ vỡ vì lớp dịch."""
    async def gia_localize(text, lang, llm):
        raise RuntimeError("hỏng")
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user", "content": "receive order P00003"}])
    assert out == "Bạn xác nhận giúp mình nhé?"
