# backend/tests/evals/test_hard_gate.py
"""Thước overlap câu hỏi ↔ tiêu đề mục — spec 2026-09-18 §3.

Thước này biến "hard" từ phán đoán thành số đo. Hiệu chỉnh trên 64 ca cũ:
easy trung vị 0,67, hard trung vị 0,33 → ngưỡng 0,40 loại 28/31 easy.
Đổi định nghĩa token hay lá là đổi thước — các số đó phải đo lại.
"""
from evals.hard_gate import HARD_MAX_OVERLAP, leaf, overlap, tokens


def test_nguong_la_0_40():
    assert HARD_MAX_OVERLAP == 0.40


def test_tokens_bo_dau_lower_va_bo_token_mot_ky_tu():
    assert tokens("Đơn phương chấm dứt") == {"don", "phuong", "cham", "dut"}
    assert tokens("a B cc") == {"cc"}


def test_leaf_lay_phan_sau_dau_phan_cach_cuoi():
    assert leaf("Chương I › NHỮNG QUY ĐỊNH CHUNG › Điều 4. Giải thích") == "Điều 4. Giải thích"
    assert leaf("Điều 428. Đơn phương chấm dứt") == "Điều 428. Đơn phương chấm dứt"


def test_overlap_trung_het_la_1_khong_trung_la_0():
    assert overlap("thuế suất", ["Thuế suất"]) == 1.0
    assert overlap("giá bán lẻ", ["Thuế suất"]) == 0.0


def test_overlap_la_ti_le_tren_token_cua_la():
    # lá: {dieu, 428, don, phuong, cham, dut} = 6; câu trúng {cham, dut} = 2
    got = overlap("hợp đồng bị chấm dứt thì sao", ["Điều 428. Đơn phương chấm dứt"])
    assert abs(got - 2 / 6) < 1e-9


def test_overlap_khong_phu_thuoc_dau():
    a = overlap("đơn phương chấm dứt", ["Điều 428. Đơn phương chấm dứt"])
    b = overlap("don phuong cham dut", ["Điều 428. Đơn phương chấm dứt"])
    assert a == b


def test_overlap_nhieu_nhan_lay_max():
    got = overlap("thuế suất", ["Phạm vi", "Thuế suất"])
    assert got == 1.0


def test_overlap_la_rong_tra_0():
    assert overlap("gì đó", [""]) == 0.0
    assert overlap("gì đó", []) == 0.0
