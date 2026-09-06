# backend/tests/rag/test_xlsx_kho_that.py
"""Nghiệm thu tầng 2 — sổ kế toán THẬT, ngoài repo (spec mục 6.1, 7).

Đáp án lấy từ chính tài liệu: sheet nào có ô "STT" thì hàng chứa ô đó là
hàng tiêu đề. Trước bản sửa: 0/23 sheet đúng.

Cổng cứng DUY NHẤT: `sai == 0` (không sheet nào tự tin lấy SAI hàng tiêu đề
trong tập 23 sheet có đáp án STT). `dung` chỉ báo cáo trung thực, KHÔNG đặt
ngưỡng cứng — ruling của controller tại Task 3 (đo ra 17/23, heuristic tổng
quát cho 81 sheet kế toán làm tay, bố cục cực đa dạng, đòi 87% là không có
cơ sở).

Ruling Task 5 (sau vòng đo đầu tiên ra sai=6): sheet nào `find_header` trả
`None` (tức xuất hiện trong `canh_bao` — cảnh báo có tên do `parse_xlsx`
phát ra) là kết quả AN TOÀN, KHÔNG được tính vào `sai`, dù ô "STT" gốc vẫn
còn nằm trong `body` (vì `parse_xlsx` không cắt `body` khi không dò được
hàng tiêu đề). Coi "None có cảnh báo" là "sai" đo NGƯỢC tinh thần spec mục
4 ("Nuốt cảnh báo chính là lỗi mà cả spec này đi đóng") và khuyến khích
detector đoán bừa để né bucket sai thay vì cảnh báo an toàn. `sai` chỉ đếm
sheet mà detector TỰ TIN chọn một hàng cụ thể (không có cảnh báo) nhưng hàng
đó không phải hàng chứa STT — đúng phương pháp Task 3 đã dùng để đóng cổng
17/0/6 (đọc trực tiếp None/cảnh báo, không suy luận gián tiếp qua nội dung
body).
"""
import os
import pytest

from src.rag.parse import parse_xlsx

SO = "d:/Youdoo/tmp-docs/Sổ-Sách-Kế-Toán-Trên-Excel-TT 200 (1).xls.xlsm"
pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.path.isfile(SO), reason="chưa có sổ kế toán thật")
def test_moi_sheet_co_cot_STT_deu_lay_dung_hang_tieu_de():
    sheets, canh_bao = parse_xlsx(SO)
    assert len(sheets) >= 50, "đọc thiếu sheet, xem lại tệp"

    sheet_co_canh_bao = {ten for ten, _ly_do in canh_bao}

    dung = sai = 0
    sai_ten = []
    for s in sheets:
        cols = [str(c).strip().upper() for c in s["columns"]]
        if "STT" in cols:
            dung += 1
            continue
        if s["sheet"] in sheet_co_canh_bao:
            # None an toàn: đã có cảnh báo mang tên, không phải detector tự
            # tin chọn nhầm — không tính vào sai (cũng không tính vào dung).
            continue
        co_stt_o_body = any(
            any(str(c).strip().upper() == "STT" for c in row if c is not None)
            for row in s["rows"])
        if co_stt_o_body:
            sai += 1
            if len(sai_ten) < 8:
                sai_ten.append(s["sheet"])

    print("\n  sheet lấy ĐÚNG hàng tiêu đề : %d" % dung)
    print("  sheet vẫn lấy SAI          : %d  %s" % (sai, sai_ten))
    print("  sheet sinh cảnh báo        : %d" % len(canh_bao))
    assert sai == 0, f"còn {sai} sheet lấy sai hàng tiêu đề: {sai_ten}"


@pytest.mark.skipif(not os.path.isfile(SO), reason="chưa có sổ kế toán thật")
def test_khong_sheet_nao_lay_chuoi_cong_thuc_lam_nhan_cot():
    """Sheet `BK NHẬP - XUẤT` từng lấy `$B$7:$M$100` làm nhãn cột."""
    sheets, _ = parse_xlsx(SO)
    xau = [s["sheet"] for s in sheets
           if any("$" in str(c) and ":" in str(c) for c in s["columns"])]
    assert xau == [], f"vẫn còn nhãn cột trông như công thức: {xau}"
