# backend/tests/agents/test_localize.py
"""Dịch chuỗi điều phối ghi, có lớp phủ quyết tất định.

Model được phép đổi CÂU CHỮ, không được phép đổi SỰ VIỆC. Đây là đường an
toàn: người dùng đọc câu này rồi duyệt một thao tác ghi THẬT.
"""
import pytest

from src.agents.localize import extract_facts, facts_survived, localize

GOC = ('Mình sẽ thực hiện thao tác sau giúp bạn:\n\n'
       '**Nhận hàng cho đơn mua P00003**\n(receive_order: order_ref=P00003)\n'
       'Tổng: 255\n'
       'Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)')


def test_trich_duoc_so_va_ma_chung_tu():
    facts = extract_facts(GOC)
    assert "P00003" in facts
    assert "255" in facts


def test_trich_duoc_ma_phieu_kho_co_gach_cheo():
    assert "WH/OUT/00001" in extract_facts("Xác nhận phiếu WH/OUT/00001?")


def test_ban_dich_giu_du_su_viec_thi_qua():
    dich = ('I will perform the following action:\n\n**Receive goods for '
            'purchase order P00003**\n(receive_order: order_ref=P00003)\n'
            'Total: 255\nDo you confirm? (reply "yes" to proceed, "no" to cancel)')
    assert facts_survived(GOC, dich) is True


def test_doi_MOT_chu_so_thi_truot():
    """Đây là ca đắt nhất nếu lọt: người dùng duyệt một con số khác."""
    assert facts_survived(GOC, GOC.replace("255", "265")) is False


def test_lam_mat_ma_don_thi_truot():
    assert facts_survived(GOC, GOC.replace("P00003", "the order")) is False


@pytest.mark.asyncio
async def test_lang_vi_thi_tra_nguyen_van_khong_goi_llm():
    """Hành vi hôm nay phải BYTE-IDENTICAL và chi phí bằng 0."""
    class LLMKhongDuocGoi:
        async def ainvoke(self, *a, **k):
            raise AssertionError("lang=vi không được gọi LLM")
    assert await localize(GOC, "vi", LLMKhongDuocGoi()) == GOC


@pytest.mark.asyncio
async def test_van_ban_khong_co_dau_tieng_viet_thi_khong_dich():
    """Câu trả lời do LLM sinh sẵn bằng tiếng Anh không được đem đi dịch lại."""
    class LLMKhongDuocGoi:
        async def ainvoke(self, *a, **k):
            raise AssertionError("không có dấu tiếng Việt thì không dịch")
    anh = "Order P00003 has been received."
    assert await localize(anh, "en", LLMKhongDuocGoi()) == anh


@pytest.mark.asyncio
async def test_dich_dat_thi_tra_ban_dich():
    class LLMGia:
        async def ainvoke(self, messages):
            class R:
                content = ('I will perform the following action: Receive goods '
                           'for purchase order P00003 (receive_order: '
                           'order_ref=P00003) Total: 255 Do you confirm?')
            return R()
    out = await localize(GOC, "en", LLMGia())
    assert "purchase order P00003" in out
    assert "Mình sẽ thực hiện" not in out


@pytest.mark.asyncio
async def test_dich_lam_sai_so_thi_ROI_VE_BAN_GOC():
    """Lớp phủ quyết: sai sự việc thì thà giữ tiếng Việt còn hơn cho duyệt
    nhầm."""
    class LLMBia:
        async def ainvoke(self, messages):
            class R:
                content = "I will receive purchase order P99999. Total: 999."
            return R()
    assert await localize(GOC, "en", LLMBia()) == GOC


@pytest.mark.asyncio
async def test_llm_nem_thi_ROI_VE_BAN_GOC():
    """Bất biến: một lượt chat không bao giờ vỡ vì lớp dịch."""
    class LLMHong:
        async def ainvoke(self, messages):
            raise RuntimeError("provider hỏng")
    assert await localize(GOC, "en", LLMHong()) == GOC


@pytest.mark.asyncio
async def test_llm_tra_rong_thi_ROI_VE_BAN_GOC():
    class LLMRong:
        async def ainvoke(self, messages):
            class R:
                content = "   "
            return R()
    assert await localize(GOC, "en", LLMRong()) == GOC


def test_ma_gach_noi_khac_nhau_tao_fact_khac_nhau():
    """Hồi quy: E-COM07 vs F-COM07 phải tạo fact set khác nhau để gate phân biệt."""
    facts_e = extract_facts("E-COM07")
    facts_f = extract_facts("F-COM07")
    assert facts_e != facts_f
    assert "E-COM07" in facts_e
    assert "F-COM07" in facts_f


def test_hoan_doi_ngay_thang_nam_thi_truot():
    """Hồi quy: ngày dạng D/M/YYYY là token nguyên, hoán đổi ngày/tháng bị bắt."""
    src = "Thực hiện ngày 3/4/2026"
    out_hoandoi = "Perform on 4/3/2026"  # hoán đổi ngày/tháng → ngày/tháng khác
    assert facts_survived(src, out_hoandoi) is False
