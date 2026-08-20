"""Đường GHI của ký ức, tại chốt duy nhất ERPAgent.chat().

Chốt thay vì vá từng node: lớp lỗi "danh sách khai báo thiếu âm thầm" đã tái
phát 5 lần trong repo này. chat() vừa được chứng minh là chốt đúng ở đợt đa
ngôn ngữ (localize).
"""
import pytest

from src.agents.erp_agent import (
    MEMORY_BLOCKED_PREFIX, MEMORY_NOTICE_PREFIX, ERPAgent)


class _FakePool:
    """Ghi lại lời gọi thay vì chạm Postgres."""

    def __init__(self):
        self.saved: list[tuple] = []
        self.forgotten: list[tuple] = []


async def _fake_save(pool, user_id, key, value, thread_id):
    pool.saved.append((user_id, key, value, thread_id))


async def _fake_forget(pool, user_id, key):
    pool.forgotten.append((user_id, key))
    return True


@pytest.fixture
def agent(monkeypatch):
    a = ERPAgent.__new__(ERPAgent)          # bỏ qua __init__ (cần Postgres/MCP)
    a._pool = _FakePool()
    # PHẢI có khoá "evaluator": chat() đọc self._llms["evaluator"] để gọi
    # localize. Để dict rỗng thì KeyError rơi vào except và test vẫn xanh —
    # nhưng xanh vì đường lỗi, không phải vì đường đúng. Đó là test không đo gì.
    a._llms = {"evaluator": object()}
    monkeypatch.setattr("src.agents.erp_agent.save_fact", _fake_save)
    monkeypatch.setattr("src.agents.erp_agent.forget_fact", _fake_forget)
    monkeypatch.setattr("src.agents.erp_agent.localize",
                        lambda text, lang, llm: _identity(text))
    return a


async def _identity(text):
    return text


async def test_ghi_nho_duoc_luu_va_cong_bo(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Được rồi.\nGHI_NHỚ: kho chính = WH/Stock"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "kho chính là WH/Stock"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.saved == [("u1", "kho_chinh", "WH/Stock", "t1")]
    assert MEMORY_NOTICE_PREFIX in out
    assert "kho_chinh = WH/Stock" in out
    assert "GHI_NHỚ" not in out          # marker không bao giờ lộ ra


async def test_cau_tra_loi_chi_co_marker_khong_de_dong_trong_dau(agent, monkeypatch):
    """Debt sweep: khi model trả lời CHỈ có marker (không câu chữ nào khác),
    `clean` rỗng — join thẳng `[clean, *notices]` để lại một dòng trống ở đầu
    trước dòng công bố. Lọc phần rỗng trước khi join để đóng lỗ đó."""
    async def fake_inner(*args, **kwargs):
        return "GHI_NHỚ: kho chính = WH/Stock"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "kho chính là WH/Stock"}],
                           thread_id="t1", user_id="u1")

    assert not out.startswith("\n")
    assert out.startswith(MEMORY_NOTICE_PREFIX)


async def test_fact_mang_ma_chung_tu_bi_chan_va_noi_ro(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Ừ.\nGHI_NHỚ: đơn quan trọng = P00003"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "nhớ đơn P00003 nhé"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.saved == []        # cổng phủ quyết đã chặn
    assert MEMORY_BLOCKED_PREFIX in out   # và KHÔNG im lặng


async def test_quen_duoc_thuc_hien(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Đã bỏ.\nQUÊN: kho chính"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "quên kho chính đi"}],
                           thread_id="t1", user_id="u1")

    assert agent._pool.forgotten == [("u1", "kho_chinh")]
    assert "QUÊN" not in out


async def test_khong_co_user_id_thi_khong_ghi_gi(agent, monkeypatch):
    # Fail-closed: không xác định được người thì KHÔNG ghi ký ức cho ai cả.
    async def fake_inner(*args, **kwargs):
        return "Ừ.\nGHI_NHỚ: kho chính = WH/Stock"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id=None)

    assert agent._pool.saved == []
    assert "GHI_NHỚ" not in out           # vẫn phải cắt marker khỏi văn bản


async def test_loi_ghi_ky_uc_khong_lam_hong_luot_chat(agent, monkeypatch):
    async def fake_inner(*args, **kwargs):
        return "Được rồi.\nGHI_NHỚ: kho chính = WH/Stock"

    async def boom(*args, **kwargs):
        raise RuntimeError("DB sập")

    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)
    monkeypatch.setattr("src.agents.erp_agent.save_fact", boom)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id="u1")

    assert "Được rồi." in out             # câu trả lời vẫn tới người dùng


async def test_db_hong_giua_chung_van_cong_bo_fact_da_ghi(agent, monkeypatch):
    """Ghi được mà KHÔNG báo là ghi âm thầm — người dùng không biết để gỡ.

    Ba marker, cái thứ hai làm DB ném: hai cái còn lại phải ghi được VÀ được
    công bố đầy đủ.
    """
    async def flaky_save(pool, user_id, key, value, thread_id):
        if key == "khoa_hai":
            raise RuntimeError("DB sập")
        pool.saved.append((user_id, key, value, thread_id))

    monkeypatch.setattr("src.agents.erp_agent.save_fact", flaky_save)

    async def fake_inner(*args, **kwargs):
        return ("Được rồi.\nGHI_NHỚ: khoa mot = gia tri mot\n"
                "GHI_NHỚ: khoa hai = gia tri hai\n"
                "GHI_NHỚ: khoa ba = gia tri ba")
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id="u1")

    written = [row[1] for row in agent._pool.saved]
    assert written == ["khoa_mot", "khoa_ba"]      # fact sau vẫn được thử
    assert out.count(MEMORY_NOTICE_PREFIX) == 2    # và cả hai đều được công bố
    assert "GHI_NHỚ" not in out


async def test_khong_co_user_id_thi_khong_bao_ly_do_sai(agent, monkeypatch):
    """Thiếu user_id thì im lặng hoàn toàn — không được báo "chặn vì mã chứng
    từ", vì lý do thật là không có ai để ghi cho."""
    async def fake_inner(*args, **kwargs):
        return "Ừ.\nGHI_NHỚ: đơn quan trọng = P00003"
    monkeypatch.setattr(ERPAgent, "_chat_inner", fake_inner)

    out = await agent.chat([{"role": "user", "content": "x"}],
                           thread_id="t1", user_id=None)

    assert agent._pool.saved == []
    assert MEMORY_BLOCKED_PREFIX not in out
    assert MEMORY_NOTICE_PREFIX not in out
    assert "GHI_NHỚ" not in out
