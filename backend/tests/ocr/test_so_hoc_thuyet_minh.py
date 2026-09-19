# -*- coding: utf-8 -*-
"""Cổng số học cho TRANG THUYẾT MINH — ràng buộc suy từ bảng con, không từ mã số.

Vì sao cần tầng này: trang thuyết minh không có cột mã số nên `tt99.json` không
dựng được ràng buộc nào, và `classify_rows` trần cả trang ở `unverified`
("ít hơn 2 hàng có mã số"). Nhưng bảng con của nó CÓ hàng TỔNG CỘNG — tài liệu
vẫn tự mang đáp án, chỉ ở dạng khác.

SỐ trong các test dưới là SỐ THẬT, chép từ phản hồi VLM lưu ở
`fixtures/vlm_tm/NTC_tr*.json` (spike 2026-09-19, 23 lượt Gemini). `cap`/`loai`
là chú thích của hợp đồng tm-v1 do TÔI đặt — spike chạy hợp đồng tm-v0 cũ chỉ
có `bang`/`la_tong`. Việc "model có trả đúng `cap` không" là test `live` riêng.
"""
import pytest

from src.ocr.so_hoc import (Constraint, Verdict, classify_rows, evaluate,
                            rang_buoc_tu_bang_con, rows_from_vision_tm, RowStatus)

COT = ["Số cuối năm", "Số đầu năm"]


def _tm(bang, cap, nhan, gia_tri, loai="thuong"):
    return {"bang": bang, "cap": cap, "nhan": nhan, "gia_tri": gia_tri, "loai": loai}


# NTC tr61 mục 29.2 — bảng PHẲNG, đã kiểm tay PASS 4/4 (ghi chú thi hành).
_TR61 = {"cot": COT, "hang": [
    _tm("29.2 Cam kết thuê hoạt động", 1, "Đến 1 năm", ["5.753.213.767", "5.999.543.767"]),
    _tm("29.2 Cam kết thuê hoạt động", 1, "Từ 1 đến 5 năm", ["17.897.201.285", "18.310.928.759"]),
    _tm("29.2 Cam kết thuê hoạt động", 1, "Trên 5 năm", ["61.153.500.007", "64.464.642.383"]),
    _tm("29.2 Cam kết thuê hoạt động", 0, "TỔNG CỘNG", ["84.803.915.059", "88.775.114.909"], "cong_don"),
]}

# NTC tr48 mục 9 — bảng HAI TẦNG. Hàng cha ("Ngắn hạn") vừa là tổng của các con,
# vừa là thành phần của TỔNG CỘNG. Bộ chấm gộp phẳng đếm trùng -> lệch ĐÚNG GẤP
# ĐÔI (6.198.681.064 vs 12.397.362.128) — đó là 8/8 "VLM FAIL" của spike, và cả
# tám là lỗi CHẤM chứ không phải lỗi đọc.
_TR48 = {"cot": COT, "hang": [
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 1, "Ngắn hạn", ["1.299.253.023", "1.046.686.892"], "cong_don"),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí thuê mặt bằng", ["802.000.000", "691.000.000"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí sửa chữa", ["71.431.247", "126.514.845"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí công cụ, dụng cụ", ["12.440.467", "51.221.778"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí khác", ["413.381.309", "177.950.269"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 1, "Dài hạn", ["4.899.428.041", "4.263.963.827"], "cong_don"),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí thuê mặt bằng", ["2.265.000.000", "2.709.000.000"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí sửa chữa", ["1.298.265.635", "768.286.668"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí công cụ, dụng cụ", ["930.727.190", "726.951.827"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 2, "Chi phí khác", ["405.435.216", "59.725.332"]),
    _tm("9. CHI PHÍ TRẢ TRƯỚC", 0, "TỔNG CỘNG", ["6.198.681.064", "5.310.650.719"], "cong_don"),
]}


def _danh_gia(payload):
    rows, cols, issues = rows_from_vision_tm(payload)
    rb = rang_buoc_tu_bang_con(rows)
    return rows, cols, rb, [evaluate(c, {str(i): r for i, r in enumerate(rows)}.get, col,
                                     strict_absent=False) for c in rb for col in cols]


def test_bang_PHANG_mot_rang_buoc_moi_cot_va_PASS():
    rows, cols, rb, ev = _danh_gia(_TR61)
    assert len(rb) == 1, f"một hàng cong_don -> một ràng buộc, có {rb}"
    assert rb[0].total == "3", "khoá là CHỈ SỐ hàng (trang thuyết minh không có mã số)"
    assert sorted(m for m, _ in rb[0].terms) == ["0", "1", "2"]
    assert all(h == 1 for _, h in rb[0].terms), "cộng dồn: hệ số +1"
    assert [e.verdict for e in ev] == [Verdict.PASS, Verdict.PASS]


def test_bang_HAI_TANG_khong_dem_trung_hang_cha():
    """Hàng cha là thành phần của tổng-chung, và là TỔNG của các con — hai vai,
    không được gộp phẳng."""
    rows, cols, rb, ev = _danh_gia(_TR48)
    assert len(rb) == 3, f"2 cha + 1 tổng chung = 3 ràng buộc, có {len(rb)}"
    tong_chung = next(c for c in rb if c.total == "10")
    assert sorted(m for m, _ in tong_chung.terms) == ["0", "5"], (
        "TỔNG CỘNG cộng hai hàng CHA, không cộng lại các con")
    cha = next(c for c in rb if c.total == "0")
    assert sorted(m for m, _ in cha.terms) == ["1", "2", "3", "4"]
    assert [e.verdict for e in ev] == [Verdict.PASS] * 6, (
        f"6 ràng buộc×cột phải PASS hết: {[(e.constraint.total, e.column, e.verdict) for e in ev]}")


def test_hang_HIEU_khong_sinh_rang_buoc_cong_don():
    """VLM (tm-v0) gắn cờ tổng cho `lợi nhuận gộp`, `doanh thu thuần`, `số cuối
    năm` — đó là HIỆU, ràng buộc Σ sai bản chất. `loai='hieu'` phải trơ."""
    pl = {"cot": ["Năm nay"], "hang": [
        _tm("21. DOANH THU", 1, "Doanh thu bán hàng", ["100.000.000"]),
        _tm("21. DOANH THU", 1, "Các khoản giảm trừ", ["10.000.000"]),
        _tm("21. DOANH THU", 0, "Doanh thu thuần", ["90.000.000"], "hieu"),
    ]}
    _, _, rb, ev = _danh_gia(pl)
    assert rb == [], f"hàng `hieu` không được sinh ràng buộc Σ, có {rb}"
    assert ev == []


def test_bang_KHAC_nhau_khong_tron_thanh_phan():
    """Một trang có nhiều bảng con (NTC tr47 có ba). Thành phần không được
    vượt biên `bang` — đó đúng là chỗ lưới phẳng Tesseract làm hỏng."""
    pl = {"cot": ["Số cuối năm"], "hang": [
        _tm("A", 1, "a1", ["10.000.000"]), _tm("A", 1, "a2", ["20.000.000"]),
        _tm("A", 0, "TỔNG CỘNG", ["30.000.000"], "cong_don"),
        _tm("B", 1, "b1", ["1.000.000"]), _tm("B", 1, "b2", ["2.000.000"]),
        _tm("B", 0, "TỔNG CỘNG", ["3.000.000"], "cong_don"),
    ]}
    _, _, rb, ev = _danh_gia(pl)
    assert len(rb) == 2
    assert all(e.verdict == Verdict.PASS for e in ev)
    a = next(c for c in rb if c.total == "2")
    assert sorted(m for m, _ in a.terms) == ["0", "1"], "bảng A không được lấy hàng bảng B"


def test_classify_rows_KHONG_tran_ca_trang_khi_khong_co_ma_so():
    """`classify_rows` trần cả trang ở unverified khi < 2 hàng có mã số — đúng
    cảnh báo đã thấy lúc nạp SID. Trang thuyết minh KHÔNG có mã số nào, nên phải
    tắt trần đó và khoá theo CHỈ SỐ hàng, nếu không cổng mới vô dụng."""
    rows, cols, rb, _ = _danh_gia(_TR61)
    rep = classify_rows(rows, rb, cols, strict_absent=False, key_by_index=True)
    assert not rep.capped_unverified, rep.capped_reason
    assert [r.status for r in rep.rows] == [RowStatus.VERIFIED] * 4


def test_mac_dinh_van_la_duong_MA_SO_khong_doi_mot_byte():
    """Cổng chống hồi quy: `key_by_index` mặc định False -> đường trang báo cáo
    chính giữ nguyên hành vi, kể cả cái trần mã số."""
    rows = [{"chi_tieu": "x", "ma_so": None, "Số cuối năm": "1.000.000"}]
    rep = classify_rows(rows, [], ["Số cuối năm"], strict_absent=False)
    assert rep.capped_unverified and "mã số" in rep.capped_reason


def test_FAIL_tren_duong_tm_HA_xuong_unverified_khong_LOAI():
    """Đo lúc nạp lại corpus sản xuất 2026-09-19: 14 FAIL trên SID kéo theo ~70
    hàng bị LOẠI — chúng từng có trong corpus dưới dạng hàng Tesseract, giờ mất.
    Các FAIL là `Doanh thu thuần`, `Số dư đầu năm`, bảng bộ phận: model gắn
    `cong_don` cho HIỆU/SỐ DƯ dù prompt đã tách `hieu`.

    Bản chất khác đường báo cáo chính: ở đó ràng buộc là `tt99.json` (chuẩn
    ngoài) nên FAIL ⇒ đọc sai ⇒ loại. Ở đây ràng buộc là LỜI KHAI CẤU TRÚC của
    chính model, FAIL không phân biệt được "cấu trúc sai" với "số sai" (spike:
    38/38 chữ số đúng). Loại là quá tay; hạ xuống `unverified` + giữ lại thì
    người dùng vẫn thấy số kèm dấu chưa kiểm — đường đã có."""
    pl = {"cot": COT, "hang": [
        _tm("21. DOANH THU", 1, "Doanh thu bán hàng", ["100.000.000", "90.000.000"]),
        _tm("21. DOANH THU", 1, "Các khoản giảm trừ", ["10.000.000", "5.000.000"]),
        # model gắn nhầm cong_don cho HIỆU -> ràng buộc 2 = 0 + 1 FAIL
        _tm("21. DOANH THU", 0, "Doanh thu thuần", ["90.000.000", "85.000.000"], "cong_don"),
    ]}
    rows, cols, issues = rows_from_vision_tm(pl)
    rb = rang_buoc_tu_bang_con(rows)
    assert len(rb) == 1
    rep = classify_rows(rows, rb, cols, strict_absent=False, key_by_index=True,
                        fail_rejects=False)
    assert [r.status for r in rep.rows] == [RowStatus.UNVERIFIED] * 3, (
        [(r.status, r.reason) for r in rep.rows])
    assert all(r.numeric for r in rep.rows), "cờ numeric giữ để extract gắn dấu"
    assert "lệch" in rep.rows[2].reason, "lý do FAIL phải còn để cảnh báo nêu"


def test_width_bad_money_van_LOAI_du_fail_rejects_False():
    """`fail_rejects=False` chỉ nới FAIL số học. Rác cấu trúc (thừa ô, ô tiền
    rác) vẫn là rác — không có gì để 'chưa kiểm', chỉ có sai."""
    pl = {"cot": COT, "hang": [
        _tm("A", 1, "a1", ["1.000.000", "2.000.000", "THỪA"]),   # width
        _tm("A", 1, "a2", ["1.00O.000", "2.000.000"]),           # bad_money (chữ O)
        _tm("A", 0, "TỔNG CỘNG", ["2.000.000", "4.000.000"], "cong_don"),
    ]}
    rows, cols, issues = rows_from_vision_tm(pl)
    rep = classify_rows(rows, rang_buoc_tu_bang_con(rows), cols, strict_absent=False,
                        key_by_index=True, fail_rejects=False, extra_issues=issues)
    assert rep.rows[0].status == RowStatus.REJECTED and "width" in rep.rows[0].reason
    assert rep.rows[1].status == RowStatus.REJECTED and "bad_money" in rep.rows[1].reason


def test_mac_dinh_fail_van_LOAI_duong_bao_cao_chinh_khong_doi():
    rows, cols, _ = rows_from_vision_tm({"cot": COT, "hang": [
        _tm("A", 1, "a1", ["1.000.000", "1.000.000"]), _tm("A", 1, "a2", ["1.000.000", "1.000.000"]),
        _tm("A", 0, "TỔNG CỘNG", ["9.000.000", "9.000.000"], "cong_don")]})
    rep = classify_rows(rows, rang_buoc_tu_bang_con(rows), cols, strict_absent=False, key_by_index=True)
    assert all(r.status == RowStatus.REJECTED for r in rep.rows), "mặc định giữ hành vi cũ"
