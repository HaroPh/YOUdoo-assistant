"""Mục 21 — báo tiến trình từng chặng cho lượt streaming."""
import asyncio

import pytest

from src.agents.tien_trinh import (BaoTienTrinh, HANG_TIEN_TRINH,
                                   NHAN_GOI_TOOL, NHAN_SOAN_CAU,
                                   NHAN_TIEN_TRINH, bao_tien_trinh)


def _lay_het(hang: asyncio.Queue) -> list[str]:
    ra = []
    while not hang.empty():
        ra.append(hang.get_nowait())
    return ra


def test_khong_ai_lang_nghe_thi_khong_lam_gi():
    """Lượt không streaming / script nội bộ / test: không hàng đợi, không nổ."""
    assert HANG_TIEN_TRINH.get() is None
    bao_tien_trinh("bất kỳ")          # không được ném


@pytest.mark.asyncio
async def test_nut_graph_bao_dung_nhan():
    hang = asyncio.Queue()
    token = HANG_TIEN_TRINH.set(hang)
    try:
        await BaoTienTrinh().on_chain_start(
            {}, {}, tags=["graph:step:1"],
            metadata={"langgraph_node": "intent_router"}, name="intent_router")
    finally:
        HANG_TIEN_TRINH.reset(token)
    assert _lay_het(hang) == [NHAN_TIEN_TRINH["intent_router"]]


@pytest.mark.asyncio
async def test_chain_KHONG_phai_nut_graph_thi_bo_qua():
    """Đối chứng cho bộ lọc `graph:step:`.

    ⚠️ Bản đầu của ca này dùng `name="LangGraph"` / `name="RunnableSequence"`
    và **không đo gì**: hai tên đó không có trong NHAN_TIEN_TRINH nên phép tra
    nhãn đã tự loại chúng — gỡ hẳn bộ lọc đi test vẫn xanh (đã thử phá và xác
    nhận).

    Hình dạng THẬT, đo 2026-08-22 bằng một graph dựng riêng: mọi chain con
    chạy BÊN TRONG một nút đều **thừa kế `metadata.langgraph_node` của nút đó**
    nhưng mang tag `seq:step:N` chứ không phải `graph:step:N`. Không lọc thì
    mỗi lời gọi LLM/tool bên trong `erp_read` lại phát lại nhãn của `erp_read`.
    """
    hang = asyncio.Queue()
    token = HANG_TIEN_TRINH.set(hang)
    try:
        for _ in range(2):
            await BaoTienTrinh().on_chain_start(
                {}, {}, tags=["seq:step:1"],
                metadata={"langgraph_node": "erp_read"},
                name="chain_con_ben_trong")
    finally:
        HANG_TIEN_TRINH.reset(token)
    assert _lay_het(hang) == []


@pytest.mark.asyncio
async def test_nut_khong_co_nhan_thi_im_lang():
    """`respond_unknown`, `mixed`… cố ý không có nhãn — không phát nhãn rỗng."""
    hang = asyncio.Queue()
    token = HANG_TIEN_TRINH.set(hang)
    try:
        await BaoTienTrinh().on_chain_start(
            {}, {}, tags=["graph:step:1"],
            metadata={"langgraph_node": "respond_unknown"})
    finally:
        HANG_TIEN_TRINH.reset(token)
    assert _lay_het(hang) == []


@pytest.mark.asyncio
async def test_tool_bao_luc_bat_dau_VA_luc_ket_thuc():
    """Hai mốc, không phải một: đo 2026-08-22 cho thấy khoảng giữa chúng là
    chặng dài nhất của lượt ERP (6,45s trước khi sửa localhost→127.0.0.1).
    Gộp làm một thì không ai biết hệ đang chờ Odoo hay đang chờ model."""
    hang = asyncio.Queue()
    token = HANG_TIEN_TRINH.set(hang)
    try:
        h = BaoTienTrinh()
        await h.on_tool_start({}, "")
        await h.on_tool_end("kết quả")
    finally:
        HANG_TIEN_TRINH.reset(token)
    assert _lay_het(hang) == [NHAN_GOI_TOOL, NHAN_SOAN_CAU]


@pytest.mark.asyncio
async def test_nhan_KHONG_duoc_lo_ten_nut_hay_ten_tool():
    """Cùng nguyên tắc với cổng xác nhận ghi (hiện args, KHÔNG hiện tên tool):
    người dùng thấy hệ đang làm gì, không thấy nội bộ hệ thống."""
    for ten_nut, nhan in NHAN_TIEN_TRINH.items():
        assert ten_nut not in nhan, f"nhãn của {ten_nut} lộ tên nút"
        assert "_" not in nhan, f"nhãn {nhan!r} trông như một định danh mã"


@pytest.mark.asyncio
async def test_handler_KHONG_BAO_GIO_nem():
    """Một thanh tiến trình không được là nguồn sự cố cho lượt chat."""
    class _HangHong:
        def put_nowait(self, x):
            raise RuntimeError("hỏng")

    token = HANG_TIEN_TRINH.set(_HangHong())
    try:
        await BaoTienTrinh().on_chain_start(
            {}, {}, tags=["graph:step:1"],
            metadata={"langgraph_node": "erp_read"})
        await BaoTienTrinh().on_tool_start({}, "")
        bao_tien_trinh("x")
    finally:
        HANG_TIEN_TRINH.reset(token)
