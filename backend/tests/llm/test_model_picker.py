# backend/tests/llm/test_model_picker.py
"""Người dùng chọn model ở dropdown; fallback vẫn nguyên; có tụt thì báo."""
import asyncio
from contextvars import ContextVar
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from src.llm.catalog import (MODEL_CHON_DUOC, MODEL_MAC_DINH,
                             MODEL_NGUOI_DUNG_CHON, VAI_TRA_LOI, chain_for,
                             model_tra_loi)
from src.llm.router import THUNG_FALLBACK, THUNG_MODEL


# ── chain_for(prefer=…) ──────────────────────────────────────────────────────
def test_prefer_dua_model_len_dau_va_GIU_fallback():
    """Đây là điểm dễ cài nhầm nhất: dùng `pin` thì mất fallback mà không báo."""
    goc = [s.alias for s in chain_for("router")]
    moi = [s.alias for s in chain_for("router", "gemini-3.5-flash-lite")]
    assert moi[0] == "gemini-3.5-flash-lite"
    # Mắt xích cũ TỤT XUỐNG làm dự phòng, không biến mất.
    assert goc[0] in moi[1:]
    assert set(goc) <= set(moi), "mất mắt xích dự phòng"


def test_prefer_da_co_trong_chuoi_thi_KHONG_nhan_doi():
    """Thử cùng một model hai lần trong một lượt là đốt hạn mức cho một kết quả
    đã biết."""
    moi = [s.alias for s in chain_for("router", "gemini-3.1-flash-lite")]
    assert len(moi) == len(set(moi)), "không được nhân đôi mắt xích"
    assert moi[0] == "gemini-3.1-flash-lite"
    # KHÔNG so bằng chain_for("router") nữa: từ 2026-08-21 `prefer` còn CHÈN
    # thêm các model chọn được khác (mục 8), nên hai chuỗi cố ý khác nhau.
    assert set(MODEL_CHON_DUOC) <= set(moi)


def test_prefer_ten_la_thi_bo_qua():
    """Tên model là dữ liệu do client gửi — không được làm nổ lượt chat."""
    assert chain_for("router", "khong-ton-tai") == chain_for("router")
    assert chain_for("router", None) == chain_for("router")


def test_mac_dinh_nam_trong_danh_sach_chon_duoc():
    assert MODEL_MAC_DINH in MODEL_CHON_DUOC


# ── thùng gom fallback lan được qua LangGraph ────────────────────────────────
@pytest.mark.asyncio
async def test_thung_fallback_lan_duoc_tu_node_ve_caller():
    """CƠ CHẾ CỐT LÕI, và nó KHÔNG hiển nhiên.

    Router có ghi chú (đã kiểm chứng): giá trị `set()` bên trong một
    asyncio.Task KHÔNG lan ngược về task cha. Node LangGraph chạy trong task
    con, còn dòng thông báo được gắn ở cha — nên cách hiển nhiên (node set(),
    cha get()) HỎNG. Đo bằng graph thật: cha đọc được {}.

    Cách dùng được là cha đặt sẵn một dict KHẢ BIẾN rồi node sửa TẠI CHỖ. Test
    này khoá đúng tính chất đó; nếu ai đổi sang set() thì nó đỏ."""
    class S(TypedDict):
        x: int

    async def node(state):
        thung = THUNG_FALLBACK.get()
        if thung is not None:
            thung["router"] = "groq-gpt-oss-120b"
        await asyncio.sleep(0)          # ép qua ranh giới task
        return {"x": 1}

    g = StateGraph(S)
    g.add_node("n", node)
    g.add_edge(START, "n"); g.add_edge("n", END)
    app = g.compile()

    thung = {}
    THUNG_FALLBACK.set(thung)
    await app.ainvoke({"x": 0})
    assert thung == {"router": "groq-gpt-oss-120b"}


def test_mac_dinh_cua_thung_la_None_khong_phai_dict():
    """Một dict mặc định dùng chung mọi ngữ cảnh; sửa tại chỗ trên nó là rò rỉ
    giữa các request. None buộc mỗi request phải tự đặt thùng của mình."""
    assert THUNG_FALLBACK.get() is None or isinstance(THUNG_FALLBACK.get(), dict)
    import contextvars
    ctx = contextvars.Context()
    assert ctx.run(THUNG_FALLBACK.get) is None


# ── dòng thông báo ───────────────────────────────────────────────────────────
def test_khong_tut_thi_KHONG_gan_gi():
    from src.agents.erp_agent import _them_dong_bao_fallback
    THUNG_FALLBACK.set({})
    assert _them_dong_bao_fallback("câu trả lời") == "câu trả lời"


def test_co_tut_thi_neu_ten_model_THAT_da_tra_loi():
    from src.agents.erp_agent import _them_dong_bao_fallback
    THUNG_FALLBACK.set({"router": "groq-gpt-oss-120b",
                        "synthesis": "groq-gpt-oss-120b"})
    out = _them_dong_bao_fallback("câu trả lời")
    assert out.startswith("câu trả lời")
    assert "groq-gpt-oss-120b" in out
    assert out.count("groq-gpt-oss-120b") == 1, "trùng vai thì gộp, không lặp"


# ── mặc định phải THẬT SỰ gộp về một model ───────────────────────────────────
def test_mac_dinh_gop_MOI_vai_ve_cung_mot_model():
    """Đây là bất biến của cả tính năng, và nó dễ hụt: đặt MODEL_MAC_DINH mà
    quên dùng nó thì người không chọn gì vẫn nhận hành vi CŨ (nhiều model theo
    vai) — tính năng trông như đã làm mà thật ra chưa."""
    from src.llm.catalog import CHAINS
    for role in CHAINS:
        assert chain_for(role, MODEL_MAC_DINH)[0].alias == MODEL_MAC_DINH, role


def test_mat_xich_dau_CU_tut_xuong_lam_du_phong_chu_khong_mat():
    """Gộp về một model KHÔNG được làm mất khả năng chống cạn hạn mức."""
    from src.llm.catalog import CHAINS
    for role in CHAINS:
        cu = {s.alias for s in chain_for(role)}
        moi = {s.alias for s in chain_for(role, MODEL_MAC_DINH)}
        assert cu <= moi, f"vai {role} mất mắt xích: {cu - moi}"


def test_model_rpd_qua_thap_KHONG_duoc_cho_chon():
    """`gemini-3.5-flash` có rpd=20 — chết sau ~20 tin nhắn/ngày. Mời người dùng
    chọn nó là mời họ thất vọng; làm mắt xích DỰ PHÒNG thì được."""
    from src.llm.catalog import spec_for
    for alias in MODEL_CHON_DUOC:
        assert spec_for(alias).rpd >= 500, f"{alias} rpd quá thấp để cho chọn"


# ── ai đã trả lời lượt này (trường `model` của phản hồi) ─────────────────────
def test_model_tra_loi_uu_tien_vai_SINH_cau_tra_loi():
    """Một lượt `mixed` đi qua router → planner → read → fusion. Chỉ `fusion`
    viết ra văn bản người dùng đọc."""
    da_dung = {"router": "R", "planner": "P", "read": "D", "fusion": "F"}
    assert model_tra_loi(da_dung, "mac-dinh") == "F"


def test_model_tra_loi_KHONG_lay_loi_goi_LLM_cuoi_cung():
    """`evaluator` (localize) chạy SAU vai sinh câu trả lời nhưng chỉ DỊCH LẠI
    văn bản đã có. Lấy "lời gọi cuối" là lấy nhầm nó."""
    assert "evaluator" not in VAI_TRA_LOI
    assert model_tra_loi({"chitchat": "C", "evaluator": "E"}, "mac-dinh") == "C"


def test_model_tra_loi_ve_mac_dinh_khi_khong_ro():
    """Nhãn hiển thị, không phải cổng an toàn: không xác định được thì suy biến
    êm chứ không nổ."""
    for thung in (None, {}, {"router": "R"}):
        assert model_tra_loi(thung, "mac-dinh") == "mac-dinh"


@pytest.mark.asyncio
async def test_thung_model_lan_duoc_tu_node_ve_caller():
    """Cùng bẫy ContextVar với THUNG_FALLBACK — thùng thứ hai nên bẫy thứ hai.

    Ghi riêng test chứ không tin vào việc "hai thùng dùng chung một cửa ghi":
    chính chỗ gọi mới là thứ có thể quên, và nó có HAI cửa (invoke + ainvoke).
    """
    class S(TypedDict):
        x: int

    async def node(state):
        thung = THUNG_MODEL.get()
        if thung is not None:
            thung["chitchat"] = "gemini-3.5-flash-lite"
        await asyncio.sleep(0)          # ép qua ranh giới task
        return {"x": 1}

    g = StateGraph(S)
    g.add_node("n", node)
    g.add_edge(START, "n"); g.add_edge("n", END)
    app = g.compile()

    thung = {}
    THUNG_MODEL.set(thung)
    await app.ainvoke({"x": 0})
    assert thung == {"chitchat": "gemini-3.5-flash-lite"}
