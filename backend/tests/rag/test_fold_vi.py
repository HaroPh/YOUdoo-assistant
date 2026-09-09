"""`chunking.fold_vi` — bỏ dấu tiếng Việt cho chân từ vựng bất biến-với-dấu.

Hàm này quyết định một chân RRF của production, và nó có ĐÚNG MỘT cái bẫy đã
cắn thật: `đ`/`Đ` là CHỮ CÁI riêng (U+0111/U+0110), không phải `d` + dấu tổ
hợp, nên `NFD` không tách chúng. Bỏ sót chỗ đó thì một phía ra `dau tu` còn
phía kia ra `đau tu` và không bao giờ khớp — đã làm một phép đo báo 0/181 nhãn
đọc đúng trong khi thật ra là 91,7%.
"""
from src.rag.chunking import fold_vi


def test_strips_tone_marks_and_lowercases():
    assert fold_vi("TÀI SẢN NGẮN HẠN") == "tai san ngan han"


def test_maps_d_with_stroke_both_cases():
    # Cái bẫy. NFD KHÔNG tách `đ`, phải map tay.
    assert fold_vi("Đầu tư") == "dau tu"
    assert fold_vi("đồng") == "dong"
    assert fold_vi("ĐẦU TƯ ĐÀI HẠN") == "dau tu dai han"


def test_already_folded_text_is_unchanged_apart_from_case():
    assert fold_vi("dau tu tai chinh") == "dau tu tai chinh"
    assert fold_vi("Dau Tu") == "dau tu"


def test_folding_is_idempotent():
    # Bất biến cần thiết: ingest gọi một lần, truy vấn gọi một lần, hai bên
    # phải hội tụ về cùng một chuỗi.
    x = "Lợi nhuận sau thuế chưa phân phối"
    assert fold_vi(fold_vi(x)) == fold_vi(x)


def test_accented_and_unaccented_input_fold_to_the_same_string():
    # Đây là TÍNH CHẤT mà cả chân từ vựng dựa vào.
    assert fold_vi("Đầu tư nắm giữ đến ngày đáo hạn") == \
           fold_vi("Dau tu nam giu den ngay dao han")


def test_keeps_digits_and_punctuation():
    # Số tiền và mã số phải sống sót: chân từ vựng dùng chúng để khớp.
    assert fold_vi("Mã số: 110 — 148.058.124.948") == \
           "ma so: 110 — 148.058.124.948"


def test_empty_string_survives():
    assert fold_vi("") == ""
