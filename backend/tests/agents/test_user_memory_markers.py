"""Bóc marker ký ức — phải bắt CẢ HAI dạng đặt marker.

Lịch sử có thật (2026-08-06): với marker ĐỀ_XUẤT_GHI, model đặt marker NGAY SAU
dấu hỏi thay vì xuống dòng như prompt yêu cầu, tái lập 2/2 lần qua backend
live. Pattern neo-đầu-dòng bỏ sót ca đó → marker LỘ RA văn bản người dùng thấy
VÀ tín hiệu không tới nơi. Đừng lặp lại: hỗ trợ cả hai dạng ngay từ đầu.
"""
from src.agents.user_memory import extract_memory_markers


def test_marker_dau_dong_duoc_boc():
    body = 'Được rồi.\nGHI_NHỚ: kho chính = WH/Stock'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert forgets == []
    assert "GHI_NHỚ" not in clean
    assert clean.strip() == "Được rồi."


def test_marker_dan_dinh_cuoi_cau_van_duoc_boc():
    # Đây là ca mà pattern neo-đầu-dòng bỏ sót.
    body = 'Được rồi, tôi nhớ nhé. GHI_NHỚ: kho chính = WH/Stock'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert "GHI_NHỚ" not in clean


def test_marker_quen_duoc_boc():
    body = 'Đã bỏ.\nQUÊN: kho chính'
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == []
    assert forgets == ["kho chính"]
    assert "QUÊN" not in clean


def test_nhieu_marker_trong_mot_cau_tra_loi():
    body = 'Xong.\nGHI_NHỚ: độ dài trả lời = ngắn gọn\nGHI_NHỚ: kho chính = WH/Stock'
    _clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("độ dài trả lời", "ngắn gọn"), ("kho chính", "WH/Stock")]


def test_khong_co_marker_thi_tra_nguyen_van():
    body = "Đơn P00003 của Azure Interior, tổng 255.0."
    clean, saves, forgets = extract_memory_markers(body)
    assert clean == body
    assert saves == []
    assert forgets == []


def test_marker_thieu_dau_bang_thi_bo_qua_nhung_van_cat_khoi_van_ban():
    # Model viết sai khuôn: không được ghi bừa, nhưng cũng KHÔNG được để lộ
    # marker ra văn bản người dùng đọc.
    body = "Xong.\nGHI_NHỚ: cái gì đó không có dấu bằng"
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == []
    assert "GHI_NHỚ" not in clean


def test_marker_giua_cau_nuot_ca_duoi_cau_gioi_han_da_biet():
    """GIỚI HẠN ĐÃ BIẾT, cố ý không sửa: marker đặt GIỮA câu mà còn chữ phía
    sau sẽ nuốt cả phần đuôi làm value và cắt cụt câu hiển thị.

    Không dùng được mẹo "đúng MỘT token" của _WRITE_SUGGEST_TRAILING_RE vì
    value của GHI_NHỚ vốn nhiều từ. Ca hỏng THẬT quan sát được ở production là
    marker DÍNH CUỐI, và ca đó chạy đúng. Ca này chỉ ghim hành vi cho tường
    minh — người dùng thấy ngay vì có dòng công bố, và gỡ được bằng "quên đi".
    """
    body = "Toi se GHI_NHỚ: kho chính = WH/Stock cho ban nhe."
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock cho ban nhe.")]
    assert clean == "Toi se"
    assert "GHI_NHỚ" not in clean          # marker vẫn KHÔNG lọt ra ngoài


def test_marker_o_dong_giua_van_duoc_boc():
    """Critical: `$` không có MULTILINE chỉ khớp cuối CHUỖI, nên marker ở dòng
    giữa từng lọt ra văn bản người dùng VÀ mất tín hiệu."""
    body = "Xong.\n   GHI_NHỚ: kho chinh = WH/Stock\nCòn gì nữa không?"
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("kho chinh", "WH/Stock")]
    assert "GHI_NHỚ" not in clean


def test_marker_dan_giua_dong_con_dong_sau():
    body = "A. GHI_NHỚ: x = y\nB còn nội dung."
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("x", "y")]
    assert "GHI_NHỚ" not in clean


def test_hai_marker_cung_dong_khong_nuot_nhau():
    """Marker sau từng bị nuốt nguyên văn vào VALUE của marker trước."""
    body = "Xong. GHI_NHỚ: a = b GHI_NHỚ: c = d"
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("a", "b"), ("c", "d")]
    assert "GHI_NHỚ" not in clean


def test_van_xuoi_tieng_viet_co_tu_quen_khong_bi_cat():
    """Vì sao dấu ':' phải BẮT BUỘC: "quên" là từ tiếng Việt thật."""
    for prose in ("Tôi quên mất rồi, xin lỗi bạn nhé.",
                  "Đừng quên kiểm tra tồn kho trước khi giao.",
                  "Tôi sẽ ghi nhớ điều đó cho bạn.",
                  "Đừng quên: kiểm tra lại tồn kho trước khi xác nhận đơn nhé.",
                  "Quên: chuyện đó bỏ qua đi."):
        clean, saves, forgets = extract_memory_markers(prose)
        assert clean == prose, prose
        assert saves == [] and forgets == [], prose


def test_crlf_khong_de_lai_r_mo_coi():
    # Debt sweep: "$" của MULTILINE chỉ khớp trước "\n" — câu trả lời CRLF để
    # lại một "\r" mồ côi ngay trước chỗ marker bị cắt nếu không chuẩn hoá.
    body = 'Được rồi.\r\nGHI_NHỚ: kho chính = WH/Stock\r\nCòn gì nữa không?'
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert "\r" not in clean
    # Dòng marker rỗng đi nhưng \n hai bên vẫn còn (cùng hành vi đã ghim ở
    # test_marker_o_dong_giua_van_duoc_boc) — điều test này ghim là KHÔNG còn
    # "\r" mồ côi, không phải hình dạng khoảng trắng quanh chỗ cắt.
    assert clean == "Được rồi.\n\nCòn gì nữa không?"


def test_trang_tri_markdown_quanh_marker_bi_bo_ca_hai_dau():
    # Debt sweep: model hay tô đậm cả dòng marker. Trang trí phải bị bóc khỏi
    # CẢ value lẫn văn bản còn lại — không để "**" mồ côi lộ ra người dùng,
    # không để "**" dính vào value lưu vào ký ức.
    body = 'Được rồi.\n**GHI_NHỚ: kho chính = WH/Stock**\nCòn gì nữa không?'
    clean, saves, _forgets = extract_memory_markers(body)
    assert saves == [("kho chính", "WH/Stock")]
    assert "*" not in clean
    assert clean == "Được rồi.\n\nCòn gì nữa không?"


def test_trang_tri_markdown_quanh_marker_quen():
    body = 'Đã bỏ.\n**QUÊN: kho chính**'
    clean, _saves, forgets = extract_memory_markers(body)
    assert forgets == ["kho chính"]
    assert "*" not in clean


def test_thieu_dau_hai_cham_thi_khong_ghi_va_khong_cat_gioi_han_da_biet():
    """GIỚI HẠN ĐÃ BIẾT, cố ý: thiếu ':' → không ghi gì, và KHÔNG cắt câu.

    Đánh đổi có chủ đích — xem docstring của extract_memory_markers."""
    body = "Xong.\nGHI_NHỚ a = b"
    clean, saves, forgets = extract_memory_markers(body)
    assert saves == [] and forgets == []
    assert clean == body
