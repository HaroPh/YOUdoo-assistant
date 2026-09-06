"""Bậc 2: dựng lưới bảng từ toạ độ chữ mà Tesseract trả về.

Module LÁ: nhận `list[OcrWord]`, trả về `list[list[str]]` là bảng với cấu trúc
cột. KHÔNG sửa chữ trong ô, KHÔNG dò bảng — chỉ lo cấu trúc.
"""
import statistics
from .engine import OcrWord

# ĐO 2026-09-06 trên toàn bộ trang bảng vector của corpus (107 tệp có ô, 234
# trang, 7.456 ô chấm được + 2.485 ô BỎ vì tầng đọc hỏng [= 25% tổng 9.941 ô,
# chủ yếu bảng danh mục hoá chất trong phụ lục luật — giới hạn của TẦNG ĐỌC,
# không phải của bậc 2] — đáp án tự sinh từ `pdfplumber` bóc chính trang đó,
# đọc lại bằng `tools/hieu_chinh_bang.py`). Quét lưới 6x4 tham số + một cấu
# hình THỬ PHÁ, chọn cặp có điểm MIN (giữ, tách) cao nhất — xem "FIX ROUND 2"
# để hiểu vì sao điểm phải là MIN của hai vế chứ không phải một thước đơn.
#
#    boi_khe   ty_le      giu     tach      min  bo_doc_hong   cot_tb
#        2.0     0.6   0.8899   0.9112   0.8899         2485     3.24   <- chọn
#        1.5     0.6   0.8892   0.9112   0.8892         2485     3.24
#        1.0     0.6   0.8891   0.9116   0.8891         2485     3.28
#        3.0     0.3   0.8884   0.9006   0.8884         2485     3.26
#        2.0    0.45   0.8883   0.9317   0.8883         2485     3.41
#        1.5    0.45   0.8879   0.9317   0.8879         2485     3.44
#        3.0    0.45   0.8889   0.8877   0.8877         2485     3.07
#        1.0    0.45   0.8863   0.9327   0.8863         2485     3.51
#        3.0    0.15   0.8859   0.9074   0.8859         2485     3.52
#        2.0     0.3   0.8852   0.9381   0.8852         2485     3.61
#        1.5     0.3   0.8790   0.9388   0.8790         2485     3.68
#        1.0     0.3   0.8775   0.9396   0.8775         2485     3.91
#        2.0    0.15   0.8723   0.9439   0.8723         2485     3.91
#        1.5    0.15   0.8600   0.9443   0.8600         2485     4.07
#        1.0    0.15   0.8578   0.9448   0.8578         2485     4.53
#        3.0     0.6   0.8899   0.8447   0.8447         2485     2.84
#        5.0    0.15   0.8975   0.7298   0.7298         2485     2.84
#        0.5     0.6   0.7124   0.9457   0.7124         2485     4.81
#        5.0     0.3   0.9001   0.7048   0.7048         2485     2.61
#        0.5    0.45   0.6978   0.9550   0.6978         2485     5.99
#        0.5     0.3   0.6965   0.9561   0.6965         2485     7.32
#        0.5    0.15   0.6951   0.9591   0.6951         2485     8.27
#        5.0    0.45   0.9006   0.6751   0.6751         2485     2.44
#        5.0     0.6   0.9009   0.6213   0.6213         2485     2.25
#
#    (THỬ PHÁ — suy biến một cột, boi_khe=1000.0, ty_le=0.3)
#     1000.0     0.3   0.9014   0.0916   0.0916         2485     1.00
#
# Cột THỬ PHÁ chứng minh thước còn sống: `boi_khe=1000` (không khe nào đủ
# lớn để thành ranh giới) suy biến MỌI bảng về MỘT cột (`cot_tb=1.00`) và bị
# phạt xuống `min=0.0916`, thấp hơn hẳn cặp tốt nhất (0,8899) — nếu nó KHÔNG
# rớt thì thước không đo gì.
#
# FIX ROUND 1 (cùng ngày): lượt đo ĐẦU TIÊN dùng thước so NGUYÊN VĂN ở đúng
# chỉ số (hàng, cột), ra tỷ lệ cao nhất chỉ 0,1092 — SUÝT bị chốt nhầm. Thước
# đó gộp "OCR đọc sai chữ" với "bậc 2 dựng sai cột" (ví dụ thật:
# `luat-dautu.pdf` tr.38 — Tesseract đọc `oripavine` thành `Pitcetytmonphine`,
# thước cũ tính đây là bậc 2 sai) và đòi trùng chỉ số hàng/cột nên một ô
# xuống dòng kéo sập cả phần sau. Sửa: so token (>=3 ký tự) có nằm CÙNG một ô
# lưới hay không, bất kể vị trí, và loại hẳn ô tầng đọc không đọc được khỏi
# mẫu số (đếm ra ở `bo_doc_hong`).
#
# FIX ROUND 2 (cùng ngày): thước round 1 CHỈ đo một vế — "không tách nhầm" —
# nên một lưới suy biến MỘT CỘT ăn điểm tuyệt đối miễn phí (cả hàng là một ô
# nên vế đó luôn đúng). Đo được: `boi_khe=1000` vẫn đạt 0,9014 trên thước
# round 1 dù không dựng ranh giới nào. Sửa: thêm vế đối xứng "không gộp
# nhầm" — hai ô KHÁC NHAU trong cùng một hàng đáp án không được rơi chung một
# ô lưới — và điểm cuối lấy MIN của hai vế, để cả hai hướng suy biến (tách vụn
# lẫn gộp hết) đều bị phạt. `cot_tb` (số cột trung bình bậc 2 dựng ra) in kèm
# để người đọc thấy ngay khi nào một cấu hình suy biến.
#
# ĐƠN VỊ KHÔNG THỨ NGUYÊN, có chủ ý: dung sai theo BỀ RỘNG KÝ TỰ TRUNG VỊ và
# ngưỡng theo TỶ LỆ SỐ DÒNG. Pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ
# đúng lúc đổi sang tài liệu định dạng khác (spec §5).
BOI_KHE = 2.0
TY_LE_UNG_HO = 0.6


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


def tim_ranh_cot(words: list[OcrWord], *, boi_khe: float | None = None,
                 ty_le_ung_ho: float | None = None) -> list[int]:
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
    # Giải lúc GỌI, không dùng hằng số làm giá trị mặc định — xem test
    # `test_mac_dinh_doc_lai_hang_so_luc_GOI...` và bẫy đã cắn bậc 1.
    boi_khe = BOI_KHE if boi_khe is None else boi_khe
    ty_le_ung_ho = TY_LE_UNG_HO if ty_le_ung_ho is None else ty_le_ung_ho

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


def dung_luoi(words: list[OcrWord], *, boi_khe: float | None = None,
              ty_le_ung_ho: float | None = None) -> list[list[str]]:
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
    # Giải lúc GỌI, không dùng hằng số làm giá trị mặc định — xem test
    # `test_mac_dinh_doc_lai_hang_so_luc_GOI...` và bẫy đã cắn bậc 1. Chỉ
    # chuyển tiếp xuống `tim_ranh_cot`, nhưng vẫn phải nhận `None` ở đây để
    # người gọi không phải tự tra hằng số.
    boi_khe = BOI_KHE if boi_khe is None else boi_khe
    ty_le_ung_ho = TY_LE_UNG_HO if ty_le_ung_ho is None else ty_le_ung_ho
    ranh = tim_ranh_cot(words, boi_khe=boi_khe, ty_le_ung_ho=ty_le_ung_ho)
    luoi: list[list[str]] = []
    for ws in _theo_dong(words).values():
        o: list[list[str]] = [[] for _ in range(len(ranh) + 1)]
        for w in sorted(ws, key=lambda x: x.left):
            tam = w.left + w.width // 2
            o[sum(1 for r in ranh if tam > r)].append(w.text)
        luoi.append([" ".join(phan) for phan in o])
    return luoi
