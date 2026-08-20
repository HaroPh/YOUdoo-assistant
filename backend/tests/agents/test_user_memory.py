"""Ký ức xuyên phiên — logic thuần (spec 2026-08-19 §4, §6.1).

Chuẩn hoá key BỎ DẤU là điều kiện để chống trùng chạy đúng: người Việt gõ cả
có dấu lẫn không dấu, nên "kho chính" và "kho chinh" phải ra CÙNG một key —
nếu không, người dùng sửa một fact mà bản cũ vẫn còn hiệu lực.
"""
import pytest

from src.agents.user_memory import (
    MEMORY_CAP, is_document_code, normalize_key, render_memory_block)


@pytest.mark.parametrize("raw,expected", [
    ("kho chính", "kho_chinh"),
    ("Kho Chính", "kho_chinh"),
    ("kho chinh", "kho_chinh"),
    ("  độ dài trả lời  ", "do_dai_tra_loi"),
    ("đơn khẩn", "don_khan"),
    ("Đã có gạch_dưới", "da_co_gach_duoi"),
])
def test_chuan_hoa_key_bo_dau_va_thuong_hoa(raw, expected):
    assert normalize_key(raw) == expected


def test_co_dau_va_khong_dau_ra_cung_mot_key():
    # Đây là lý do tồn tại của việc bỏ dấu — hai cách gõ phải supersede nhau.
    assert normalize_key("kho chính") == normalize_key("kho chinh")


@pytest.mark.parametrize("value", [
    "P00003", "S00012", "INV/2026/00004", "WH/OUT/00001",
    "đơn P00003 là quan trọng nhất", "xem hoá đơn INV/2026/00017 nhé",
])
def test_chan_fact_mang_ma_chung_tu_cu_the(value):
    # Marker do LLM phát ra, mà ở erp_read model đang NHÌN THẤY dữ liệu ERP —
    # không có gì ngăn nó ghi một mã đơn vào ký ức, rồi mã đó rò sang cloud ở
    # lượt chitchat sau (M5/ADR-009). Cổng này là thứ ngăn.
    assert is_document_code(value) is True


@pytest.mark.parametrize("value", [
    "WH/Stock",           # kho: có gạch chéo nhưng KHÔNG có chữ số → quy ước, cho qua
    "ngắn gọn",
    "giao trong 24h",     # có chữ số nhưng không phải mã chứng từ
    "tiếng Anh",
])
def test_cho_qua_fact_noi_ve_loai_hoac_quy_uoc(value):
    assert is_document_code(value) is False


def test_render_khoi_ky_uc_rong_thi_tra_chuoi_rong():
    # Chuỗi rỗng để caller ghép có điều kiện, đúng khuôn render_working_context.
    assert render_memory_block([]) == ""


def test_render_khoi_ky_uc_liet_ke_tung_fact():
    block = render_memory_block([("do_dai_tra_loi", "ngắn gọn"),
                                 ("kho_chinh", "WH/Stock")])
    assert "do_dai_tra_loi = ngắn gọn" in block
    assert "kho_chinh = WH/Stock" in block


def test_tran_ky_uc_la_50():
    assert MEMORY_CAP == 50
