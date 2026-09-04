"""Ký ức xuyên phiên — logic thuần (spec 2026-08-19 §4, §6.1).

Chuẩn hoá key BỎ DẤU là điều kiện để chống trùng chạy đúng: người Việt gõ cả
có dấu lẫn không dấu, nên "kho chính" và "kho chinh" phải ra CÙNG một key —
nếu không, người dùng sửa một fact mà bản cũ vẫn còn hiệu lực.
"""
import pytest

from src.agents.user_memory import (
    MEMORY_CAP, is_document_code, is_sensitive, normalize_key,
    render_memory_block)


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
    "E-COM07", "F-COM07", "COM07",
    "đơn P00003 là quan trọng nhất", "xem hoá đơn INV/2026/00017 nhé",
    # Final review: sổ nhật ký Odoo có chữ số NGAY Ở ĐOẠN ĐẦU — regex cũ đòi
    # "[A-Z]{2,}" (chỉ chữ) cho đoạn đầu nên lọt cả ba, dù post_invoice /
    # register_payment làm vai đọc thấy đúng những tên sổ này.
    "BNK1/2026/00001", "PBNK1/2026/00001", "CSH1/2026/00007",
    # Ranh giới cấu trúc (final review, trước merge): >=2 dấu gạch chéo, hoặc
    # đoạn số cuối zero-padded — cả hai đều là dấu hiệu mã chứng từ thật.
    "RINV/2026/00003", "INV/0001", "WH/IN/00001",
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
    "khong qua 3 dong", "uu tien don gap trong 48h", "top 10 khach hang",
    # Quy ước đời thường dạng CHỮ/SỐ: đúng 1 gạch chéo, đoạn cuối là năm/số
    # thường (không zero-padded) — không thoả ranh giới cấu trúc, cho qua.
    "Q3/2026", "KPI/2026", "HR/2026", "VN/84", "ISO/9001",
])
def test_cho_qua_fact_noi_ve_loai_hoac_quy_uoc(value):
    assert is_document_code(value) is False


@pytest.mark.parametrize("key,value", [
    # Nhãn trong VALUE.
    ("ghi chú", "số tài khoản của tôi là 19012345678"),
    ("ghi chú", "CCCD 012345678901"),
    ("ghi chú", "mật khẩu là conmeo123"),
    ("ghi chú", "mã OTP hôm nay là 482910"),
    # Nhãn trong KEY.
    ("số tài khoản", "chi nhánh Sài Gòn"),
    ("mật khẩu wifi", "matkhau123"),
    ("CCCD", "012345678901"),
    # Chỉ cần dãy số liền ≥9 chữ số, không cần nhãn đi kèm.
    ("ghi chú", "gọi số 0901234567 khi cần gấp"),
    ("mã số thuế", "0312345678"),
    ("số thẻ", "4111111111111111"),
])
def test_chan_fact_dinh_danh_hoac_bao_mat(key, value):
    assert is_sensitive(key, value) is True


@pytest.mark.parametrize("key,value", [
    ("kho_chinh", "WH/Stock"),
    ("don_khan", "giao trong 24h"),
    ("muc_phat_toi_da", "công ty tôi áp dụng mức phạt tối đa 15%"),
    ("uu_tien", "Q3/2026"),
    ("xung_ho", "gọi tôi là anh Hào"),
    ("do_dai_phan_hoi", "ngan_gon"),
    # Số tiền lớn CÓ dấu chấm phân cách: nhóm ≤3 chữ số, không phải dãy liền.
    ("doanh_so_muc_tieu", "1.234.567.890 đồng"),
    # Ngày viết gọn 8 chữ số: dưới ngưỡng 9, cố ý cho qua.
    ("han_chot", "20260904"),
    # "pin" là NHÃN, nhưng chỉ khi đứng riêng một token — "spin" không phải
    # "pin" nằm trong từ khác, đúng lý do dùng so khớp theo token.
    ("ghi chú", "khách hàng thích uống spin class buổi sáng"),
    # BẮT NGANG RANH GIỚI key/value: hai fact rời rạc, mỗi bên vô hại, nhưng
    # đuôi key nối đầu value từng vô tình ghép thành đúng chuỗi token của một
    # nhãn ("mã SỐ" + "THẺ kho A" → "so_the" = "số thẻ"). Review bắt trước
    # merge — key và value PHẢI so khớp riêng, không nối chuỗi rồi so chung.
    ("mã số", "thẻ kho A"),
    ("tong so", "the nhan vien nam nay"),
])
def test_cho_qua_fact_khong_nhay_cam(key, value):
    assert is_sensitive(key, value) is False


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
