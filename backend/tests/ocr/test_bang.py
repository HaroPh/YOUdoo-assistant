from src.ocr.bang import be_rong_ky_tu, tim_ranh_cot, dung_luoi
from src.ocr.engine import OcrWord


def tu(text: str, left: int, top: int, width: int, *, line: int = 0) -> OcrWord:
    """Tạo OcrWord cho test."""
    return OcrWord(
        text=text,
        conf=99.0,
        left=left,
        top=top,
        width=width,
        height=16,
        line_id=(line, 0, 0)
    )


def test_be_rong_ky_tu_tinh_trung_binh_do_rong_ky_tu():
    """Trung bình = tổng độ rộng / tổng số ký tự."""
    words = [tu("ABC", 0, 0, 30)]  # 3 chars, 30 width → 10 per char
    assert be_rong_ky_tu(words) == 10.0


def _bang_hai_cot_tien():
    """Ba hàng: nhãn ở x=100, hai cột số căn PHẢI ở x=500 và x=800."""
    words = []
    for i, (nhan, a, b) in enumerate([("Tien", "1.000", "2.000"),
                                      ("Hang", "30.000", "40.000"),
                                      ("Khac", "500.000", "600.000")]):
        words.append(tu(nhan, 100, 100 + i * 30, 40, line=i))
        words.append(tu(a, 500 - len(a) * 10, 100 + i * 30, len(a) * 10, line=i))
        words.append(tu(b, 800 - len(b) * 10, 100 + i * 30, len(b) * 10, line=i))
    return words


def test_tim_ranh_cot_bat_duoc_hai_ranh_giua_ba_cot():
    ranh = tim_ranh_cot(_bang_hai_cot_tien(), boi_khe=2.0, ty_le_ung_ho=0.6)
    assert len(ranh) == 2
    assert 140 < ranh[0] < 450 and 500 < ranh[1] < 730


def test_khe_GIUA_TU_trong_cung_mot_o_KHONG_thanh_ranh_cot():
    """Đây là chỗ cơ chế cụm-mép hỏng: khe giữa `Tai` và `san` là một bề rộng
    ký tự, khe sang cột số là 30 — phải phân biệt được hai loại khe đó."""
    words = []
    for i in range(3):
        words.append(tu("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(tu("san", 140, 100 + i * 30, 30, line=i))
        words.append(tu("100", 470, 100 + i * 30, 30, line=i))
    ranh = tim_ranh_cot(words, boi_khe=2.0, ty_le_ung_ho=0.6)
    assert len(ranh) == 1, "chi duoc mot ranh: giua nhan hai tu va cot so"
    assert 170 < ranh[0] < 470


def test_van_xuoi_khong_can_le_ra_KHONG_ranh_nao():
    """Không có bộ dò bảng: trang văn xuôi tự nhiên suy biến về một cột."""
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    assert tim_ranh_cot(words, boi_khe=2.0, ty_le_ung_ho=0.6) == []


def test_dung_luoi_tra_dung_luoi_ba_cot():
    luoi = dung_luoi(_bang_hai_cot_tien(), boi_khe=2.0, ty_le_ung_ho=0.6)
    assert luoi == [["Tien", "1.000", "2.000"],
                    ["Hang", "30.000", "40.000"],
                    ["Khac", "500.000", "600.000"]]


def test_dung_luoi_noi_nhieu_tu_trong_cung_mot_o():
    """Nhãn nhiều từ phải thành MỘT ô, không phải nhiều cột."""
    words = []
    for i in range(3):
        words.append(tu("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(tu("san", 140, 100 + i * 30, 30, line=i))
        words.append(tu("100", 470, 100 + i * 30, 30, line=i))
    ket = dung_luoi(words, boi_khe=2.0, ty_le_ung_ho=0.6)
    assert ket == [["Tai san", "100"]] * 3


def test_van_xuoi_ra_luoi_MOT_cot_giu_nguyen_tung_dong():
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    ket = dung_luoi(words, boi_khe=2.0, ty_le_ung_ho=0.6)
    assert ket == [[f"dong{i}"] for i in range(6)]


def test_dung_luoi_KHONG_sap_lai_hang_theo_toa_do_y():
    """Bậc 1 đã ghi bài học: khác biệt thứ tự đọc từng bị nhầm thành OCR kém.

    Đầu vào ở đây CỐ Ý không theo thứ tự y (từ ở y=500 đứng trước từ ở y=100),
    mô phỏng một trang mà tesseract đọc theo thứ tự khác thứ tự hình học. Đầu
    ra phải theo ĐÚNG THỨ TỰ ĐẦU VÀO, chứng minh ta không tự sắp lại theo y.
    Đòi đầu ra theo `line_id` mới là sắp lại — đúng thứ bị cấm."""
    words = [tu("duoc_doc_truoc", 100, 500, 40, line=1),
             tu("duoc_doc_sau", 100, 100, 40, line=0)]
    ket = dung_luoi(words, boi_khe=2.0, ty_le_ung_ho=0.6)
    assert ket == [["duoc_doc_truoc"], ["duoc_doc_sau"]]
