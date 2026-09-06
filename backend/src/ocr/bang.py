"""Bậc 2: dựng lưới bảng từ toạ độ chữ mà Tesseract trả về.

Module LÁ: nhận `list[OcrWord]`, trả về `list[list[str]]` là bảng với cấu trúc
cột. KHÔNG sửa chữ trong ô, KHÔNG dò bảng — chỉ lo cấu trúc.
"""
import statistics
from .engine import OcrWord


def be_rong_ky_tu(words: list[OcrWord]) -> float:
    """Bề rộng một ký tự, lấy TRUNG VỊ trên tỷ lệ TỪNG TỪ.

    Đây là ĐƠN VỊ CHUẨN HOÁ của cả module. Mọi ngưỡng tính theo nó chứ không
    theo pixel: pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ đúng lúc đổi
    sang tài liệu định dạng khác (spec §5).

    TRUNG VỊ chứ không trung bình, và tính trên tỷ lệ TỪNG TỪ chứ không phải
    tổng-chia-tổng: scan thật sinh ra token rác bbox rộng mà ít ký tự (đo được
    trên trang 1 bản BCTC — dấu mộc đỏ đọc thành `_Ƒ_Gẻ]ùỉ—m//—.ẶẲó—[`). Một
    token như thế kéo trung bình đi rất xa; trung vị miễn nhiễm. Lệch đơn vị
    chuẩn hoá là lệch MỌI ngưỡng trong module.
    """
    rong = [w.width / len(w.text) for w in words if w.text]
    if not rong:
        return 1.0          # không có từ nào: trả 1 để phép chia sau không nổ
    return statistics.median(rong)


def _theo_dong(words: list[OcrWord]) -> dict:
    """Gom từ theo `line_id`, GIỮ NGUYÊN thứ tự dòng xuất hiện."""
    ra: dict = {}
    for w in words:
        ra.setdefault(w.line_id, []).append(w)
    return ra


def _cum(gia_tri: list[int], dung_sai: float) -> list[list[int]]:
    """Gom số gần nhau thành cụm, tham lam theo thứ tự tăng dần."""
    if not gia_tri:
        return []
    da_sap = sorted(gia_tri)
    xong: list[list[int]] = [[da_sap[0]]]
    for v in da_sap[1:]:
        if v - xong[-1][-1] <= dung_sai:
            xong[-1].append(v)
        else:
            xong.append([v])
    return xong


def tim_ranh_cot(words: list[OcrWord], *, boi_khe: float,
                 ty_le_ung_ho: float) -> list[int]:
    """Ranh giới cột = vị trí KHE LỚN trong dòng, CỤM LẠI qua nhiều dòng.

    Hai bước, và cả hai đều cần thiết:

    1. Trong TỪNG dòng, một khe giữa hai từ liền nhau là ứng viên ranh giới khi
       nó rộng hơn `boi_khe` lần bề rộng ký tự. Đây là thứ phân biệt khe giữa
       hai từ trong CÙNG một ô (khoảng một ký tự) với khe sang cột khác (hàng
       chục ký tự). Cụm căn lề đơn thuần KHÔNG phân biệt được hai loại khe đó —
       đó là lý do cơ chế cụm-mép bị loại (ledger, mục P1).
    2. Ứng viên phải CỤM LẠI cùng một x qua đủ nhiều dòng mới thành ranh giới
       thật. Đây chính là đòi hỏi CĂN LỀ mà spec §2.2 đo được.

    KHÔNG mâu thuẫn spec §2.1 (khe trắng đã bị bác bỏ): §2.1 bác khe chạy dọc
    SUỐT CẢ TRANG — một dòng tiêu đề ngang là đủ bịt nó. Ở đây khe đo CỤC BỘ
    trong từng dòng rồi mới cụm, nên dòng tiêu đề chỉ đơn giản không đóng góp
    ứng viên nào, còn mấy chục dòng thân vẫn đóng góp.
    """
    if not words:
        return []
    dong = _theo_dong(words)
    rong_ky_tu = be_rong_ky_tu(words)
    nguong_khe = boi_khe * rong_ky_tu

    ung_vien: list[int] = []
    for ws in dong.values():
        theo_x = sorted(ws, key=lambda w: w.left)
        for a, b in zip(theo_x, theo_x[1:]):
            het_a = a.left + a.width
            if b.left - het_a >= nguong_khe:
                ung_vien.append((het_a + b.left) // 2)

    # Dung sai cụm = MỘT bề rộng ký tự: một ranh giới xê dịch quá một ký tự
    # giữa các dòng thì là ranh giới KHÁC, không phải cùng một cột.
    toi_thieu = max(2, int(len(dong) * ty_le_ung_ho))
    return sorted(int(statistics.median(c))
                  for c in _cum(ung_vien, rong_ky_tu) if len(c) >= toi_thieu)


def dung_luoi(words: list[OcrWord], *, boi_khe: float,
              ty_le_ung_ho: float) -> list[list[str]]:
    """`list[OcrWord]` -> `list[list[str]]`.

    Hàng lấy theo `line_id` Tesseract đã trả sẵn, GIỮ NGUYÊN thứ tự xuất hiện.
    Không tự gom lại theo toạ độ y: tesseract gom tốt hơn, và bậc 1 đã ghi bài
    học "đừng sắp xếp lại thứ tự đọc" — khác biệt thứ tự đọc từng bị nhầm thành
    chất lượng OCR kém.

    Không ranh giới nào = MỘT cột. Đó là đường suy biến cho trang văn xuôi,
    KHÔNG phải lỗi: không có bộ dò bảng thì không có gì để bắn nhầm (spec §4).
    """
    if not words:
        return []
    ranh = tim_ranh_cot(words, boi_khe=boi_khe, ty_le_ung_ho=ty_le_ung_ho)
    luoi: list[list[str]] = []
    for ws in _theo_dong(words).values():
        o: list[list[str]] = [[] for _ in range(len(ranh) + 1)]
        for w in sorted(ws, key=lambda x: x.left):
            tam = w.left + w.width // 2
            o[sum(1 for r in ranh if tam > r)].append(w.text)
        luoi.append([" ".join(phan) for phan in o])
    return luoi
