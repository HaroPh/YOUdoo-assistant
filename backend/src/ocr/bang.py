"""Bậc 2: dựng lưới bảng từ toạ độ chữ mà Tesseract trả về.

Module LÁ: nhận `list[OcrWord]`, trả về `list[list[str]]` là bảng với cấu trúc
cột. KHÔNG sửa chữ trong ô, KHÔNG dò bảng — chỉ lo cấu trúc.
"""
import statistics
from .engine import OcrWord

# ĐO 2026-09-07 (SAU khi đổi thuật toán `tim_ranh_cot` từ ĐIỂM GIỮA khe sang
# MÉP cạnh khe — xem lý do ở docstring hàm đó) trên toàn bộ trang bảng vector
# của corpus (107 tệp có ô, 234 trang, 7.456 ô chấm được + 2.485 ô BỎ vì tầng
# đọc hỏng [= 25% tổng 9.941 ô, chủ yếu bảng danh mục hoá chất trong phụ lục
# luật — giới hạn của TẦNG ĐỌC, không phải của bậc 2] — đáp án tự sinh từ
# `pdfplumber` bóc chính trang đó, đọc lại bằng `tools/hieu_chinh_bang.py`).
# Quét lưới 6x5 tham số + một cấu hình THỬ PHÁ. Bảng này THAY TRỌN bảng đo
# 2026-09-06 của thuật toán điểm-giữa cũ (số liệu không so được trực tiếp vì
# thuật toán khác nhau).
#
#    boi_khe   ty_le      giu     tach      min  bo_doc_hong   cot_tb  trang_suy_bien
#        3.0     0.6   0.8746   0.9061   0.8746         2485     4.11             153
#        2.0     0.6   0.8730   0.9565   0.8730         2485     4.53             148
#        3.0    0.45   0.8722   0.9217   0.8722         2485     4.31             133
#        1.5     0.6   0.8720   0.9568   0.8720         2485     4.55             142
#        1.0     0.6   0.8718   0.9568   0.8718         2485     4.60             135
#        2.0    0.45   0.8702   0.9594   0.8702         2485     4.67             125
#        1.5    0.45   0.8696   0.9594   0.8696         2485     4.72             118
#        1.0    0.45   0.8676   0.9602   0.8676         2485     4.84             109
#        3.0     0.3   0.8674   0.9259   0.8674         2485     4.51             119   <- chọn (không phải MIN cao nhất — xem lý do dưới)
#        1.0    0.75   0.8778   0.8649   0.8649         2485     3.76             162
#        1.5    0.75   0.8780   0.8649   0.8649         2485     3.73             166
#        2.0    0.75   0.8780   0.8649   0.8649         2485     3.72             170
#        2.0     0.3   0.8623   0.9622   0.8623         2485     4.91             108
#        3.0    0.15   0.8580   0.9293   0.8580         2485     4.85             112
#        1.5     0.3   0.8550   0.9623   0.8550         2485     5.04              96
#        1.0     0.3   0.8527   0.9626   0.8527         2485     5.35              84
#        2.0    0.15   0.8396   0.9656   0.8396         2485     5.33              95
#        1.5    0.15   0.8250   0.9659   0.8250         2485     5.64              80
#        1.0    0.15   0.8208   0.9660   0.8208         2485     6.27              70
#        3.0    0.75   0.8826   0.7682   0.7682         2485     3.21             174
#        5.0    0.15   0.8690   0.7605   0.7605         2485     3.88             125
#        5.0     0.3   0.8790   0.7299   0.7299         2485     3.59             130
#        0.5    0.75   0.7053   0.8751   0.7053         2485     5.56              75
#        5.0    0.45   0.8841   0.7048   0.7048         2485     3.40             141
#        0.5     0.6   0.6742   0.9622   0.6742         2485     7.23              55
#        5.0     0.6   0.8860   0.6734   0.6734         2485     3.23             159
#        0.5    0.45   0.6670   0.9622   0.6670         2485     8.77              47
#        0.5     0.3   0.6660   0.9633   0.6660         2485    10.56              38
#        0.5    0.15   0.6647   0.9661   0.6647         2485    12.01              36
#        5.0    0.75   0.8896   0.6037   0.6037         2485     2.56             176
#
#    (THỬ PHÁ — suy biến một cột, boi_khe=1000.0, ty_le=0.3)
#     1000.0     0.3   0.9014   0.0916   0.0916         2485     1.00             386
#
# Cột THỬ PHÁ chứng minh thước còn sống: `boi_khe=1000` (không khe nào đủ
# lớn để thành ranh giới) suy biến MỌI bảng về MỘT cột (`cot_tb=1.00`,
# `trang_suy_bien=386` — nhiều nhất bảng) và bị phạt xuống `min=0.0916`, thấp
# hơn hẳn cặp tốt nhất — nếu nó KHÔNG rớt thì thước không đo gì.
#
# ═══ TẠI SAO ĐỔI THUẬT TOÁN (2026-09-07) — VÀ TẠI SAO KHÔNG CHỌN THEO BẢNG TRÊN ═══
#
# 1. ĐIỂM-GIỮA-KHE KHÔNG CHẠY TRÊN SCAN THẬT. Bảng trên đo trên corpus VECTOR,
#    nhưng lý do sửa hàm là BCTC SCAN THẬT (SCID) — trên đó, nhãn chỉ tiêu kết
#    thúc ở x khác nhau mỗi hàng nên điểm giữa khe tản mát, KHÔNG BAO GIỜ CỤM.
#    Đo được bằng thuật toán điểm-giữa CŨ: trang 12 ra `[234]`, trang 13 ra
#    `[228]` — cả hai chỉ là rãnh sau SỐ THỨ TỰ, không phải cột thật; **trang
#    17 ra `[]` — MỘT cột, không tìm được ranh giới nào**. Tức là bậc 2 không
#    chạy được trên đúng tài liệu nó sinh ra để xử lý. Mép cạnh khe (mép trái
#    của từ sau khe, mép phải của từ trước khe, rồi lọc cột rỗng) sửa đúng chỗ
#    này — xem docstring `tim_ranh_cot`.
#
# 2. HAI CỔNG ĐÒI THAM SỐ KHÁC NHAU, và corpus vector không phải cổng quyết
#    định. Trên bảng ở trên, `ty_le_ung_ho=0.6` (boi_khe=3.0) có MIN cao nhất
#    (0,8746). Nhưng đo THẲNG số cột `tim_ranh_cot` dựng ra trên 7 trang BCTC
#    SCAN THẬT (trang 12–18) theo từng mức `ty_le` (`boi_khe` hầu như không
#    ảnh hưởng trên scan — 1.0/2.0/3.0 cho kết quả gần hệt nhau):
#
#       ty_le   số cột từng trang (12, 13, 14, 15, 16, 17, 18)
#         0.6   [6, 6, 6, 1, 1, 1, 1]    <- 4/7 trang SẬP về một cột
#        0.45   [6, 8, 6, 2, 5, 6, 1]    <- 2/7 trang sập
#         0.3   [9, 12, 8, 6, 8, 8, 5]   <- CHẠY trên MỌI trang, không trang nào sập
#
#    `ty_le=0.6` — giá trị mà cổng vector thích nhất — làm bậc 2 sập về một
#    cột trên hơn nửa số trang scan thật, tức đúng loại hỏng mà bản mép-cạnh-
#    khe này được viết ra để chữa. Chọn theo MIN cao nhất của cổng vector ở
#    đây là chọn nhầm mục tiêu: corpus vector đã đi qua `pdfplumber` ở tầng B4
#    và KHÔNG CẦN bậc 2 — bậc 2 sinh ra để xử lý đúng thứ pdfplumber không đọc
#    được, tức là SCAN. Cổng vector là cổng còn-sống trên một proxy DỄ HƠN,
#    không phải mục tiêu thật.
#
# 3. CHỐT: `BOI_KHE=3.0, TY_LE_UNG_HO=0.3` — KHÔNG phải cấu hình MIN cao nhất
#    trên bảng corpus vector (đó là `3.0/0.6`, min=0,8746). Đánh đổi MIN tụt
#    còn `0,8674` (dòng `<- chọn` ở trên, chênh ≈0,007) để đổi lấy việc bậc 2
#    THẬT SỰ CHẠY trên cả 7/7 trang scan thay vì chết trên 4/7.
#
# 4. GIỚI HẠN: ở `ty_le=0.3`, trang 12–13 của BCTC scan ra 9–12 cột trong khi
#    bảng thật chỉ có 5 cột — TÁCH HƠI VỤN (rãnh nội bộ trong ô đôi khi bị bắt
#    nhầm thành ranh giới). Chấp nhận: hỏng-vụn vẫn giữ được dữ liệu đọc được
#    (khác hẳn hỏng-sập-về-một-cột, là MẤT TRẮNG cấu trúc — xem mục "HAI KIỂU
#    HỎNG KHÔNG CÙNG GIÁ" dưới). Cần đo lại nếu kho có thêm tài liệu scan để
#    xem mức tách-vụn này có ổn định không.
#
# GIỚI HẠN ĐO ĐƯỢC KHÁC, nói thẳng vì đây là dữ kiện chứ không phải chi tiết vặt:
# - **`trang_suy_bien = 119/234`** ở cấu hình chọn (đo trên corpus vector) —
#   một phần bảng trong corpus vector không dựng lại được cấu trúc (suy biến
#   về một cột), chủ yếu vì tầng đọc không đọc nổi chúng (danh mục hoá chất,
#   biểu mẫu chữ nhỏ).
# - **`2.485/9.941 ô (25%)`** bị bỏ vì tầng đọc hỏng khi chấm điểm — giới hạn
#   của TẦNG ĐỌC, không phải của bậc 2 (spec §2.4, §10).
#
# LÝ DO CHỌN, tổng quát hoá cho cả hai cổng: HAI KIỂU HỎNG KHÔNG CÙNG GIÁ.
#   - Bảng SUY BIẾN VỀ MỘT CỘT = bậc 2 không cho gì thêm = ĐÚNG BẰNG hành vi
#     hôm nay (dòng phẳng). Hỏng AN TOÀN, không đưa gì sai vào corpus.
#   - Bảng TÁCH SAI/VỤN CỘT = ranh giới ô sai đi THẲNG vào corpus như dữ liệu
#     thật. Hỏng CÓ HẠI, nhưng còn dữ liệu để dùng — khác hẳn mất trắng.
# Tiêu chí chốt là tối đa hoá độ đúng cấu trúc Ở NƠI CÓ dựng cấu trúc, ưu tiên
# KHÔNG SẬP trên tài liệu SCAN THẬT (mục tiêu thật của bậc 2) hơn là MIN cao
# nhất trên corpus vector (proxy). Nếu về sau đo thấy tách-vụn ở `ty_le=0.3`
# gây hại nhiều hơn dự đoán trên tập scan lớn hơn, đổi tham số là SỬA HAI DÒNG
# hằng số — bảng trên đã đủ để so lại không cần đo thêm trên corpus vector.
#
# LỊCH SỬ BỊ BÁC BỎ (giữ lại để người sau không lặp lại): một tiêu chí sớm
# từng thử "MIN cao nhất trong số cấu hình KHÔNG làm tăng `trang_suy_bien` so
# với `ty_le` liền dưới cùng `boi_khe`" — script `hieu_chinh_bang.py` vẫn tự
# in ra lựa chọn này ở cuối mỗi lần chạy (`boi_khe=3.0 ty_le=0.15`) NHƯNG đó
# không phải tham số chốt của module này. Tiêu chí đó SAI: vì `trang_suy_bien`
# tăng đơn điệu theo `ty_le` ở MỌI `boi_khe` trên corpus vector, nó loại sạch
# 24/30 cấu hình một cách MÁY MÓC và chỉ còn lại đúng cột `ty_le=0.15` — đó là
# LỌC, không phải CHỌN, và không phân biệt được hai kiểu hỏng khác giá ở trên,
# càng không biết gì về hành vi trên scan thật (mục 2 ở trên).
#
# FIX ROUND 1 (2026-09-06): lượt đo ĐẦU TIÊN dùng thước so NGUYÊN VĂN ở đúng
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
# FIX ROUND 3 (cùng ngày): mở lưới thêm một nấc `ty_le=0.75` để dò xem đỉnh có
# nằm ngoài rìa cũ không, và thêm cột `trang_suy_bien` (đếm bảng mà đáp án có
# ≥2 cột nhưng bậc 2 chỉ dựng ra 1) sau khi phát hiện điểm TỔNG THỂ có thể
# tăng trong khi TỪNG TRANG cụ thể (`luat-thuexuatnhapkhau.pdf` tr.14) đã sập
# về một cột — trung bình che mất thảm hoạ cục bộ. Tiêu chí chọn ban đầu của
# round 3 sau đó bị chính round này bác bỏ — xem "LỊCH SỬ BỊ BÁC BỎ" ở trên.
#
# ĐƠN VỊ KHÔNG THỨ NGUYÊN, có chủ ý: dung sai theo BỀ RỘNG KÝ TỰ TRUNG VỊ và
# ngưỡng theo TỶ LỆ SỐ DÒNG. Pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ
# đúng lúc đổi sang tài liệu định dạng khác (spec §5).
BOI_KHE = 3.0
TY_LE_UNG_HO = 0.3


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
    """Ranh giới cột = MÉP của từ cạnh một KHE LỚN, cụm lại qua nhiều dòng.

    Ba bước, và cả ba đều cần thiết:

    1. Trong TỪNG dòng, khe giữa hai từ liền nhau rộng hơn `boi_khe` lần bề rộng
       ký tự là ứng viên. Đây là thứ phân biệt khe giữa hai từ trong CÙNG một ô
       (khoảng một ký tự) với khe sang cột khác (hàng chục ký tự).
    2. Vị trí lấy từ MÉP cạnh khe, KHÔNG phải điểm giữa khe: mép TRÁI của từ SAU
       khe (cột căn trái, ví dụ `Mã số`) và mép PHẢI của từ TRƯỚC khe (cột căn
       phải, ví dụ cột tiền). Ứng viên phải cụm lại cùng một x qua đủ nhiều dòng.

       Điểm giữa khe KHÔNG dùng được, và đây là chỗ đã trả giá: nhãn chỉ tiêu
       kết thúc ở x khác nhau mỗi hàng nên điểm giữa tản mát, không bao giờ cụm.
       Đo được trên BCTC scan thật: cách điểm-giữa chỉ tìm ra rãnh sau SỐ THỨ TỰ
       (x≈230) và bỏ sót toàn bộ cột thật; trang 17 không ra ranh giới nào. Cách
       mép ra đúng `930/965` (cột `Mã số`), `1300` và `1549` — khớp chính xác số
       đo spec §2.2 (tiền căn phải ở x≈1290–1305 và x≈1545–1560).
    3. Bỏ ranh giới nào sinh ra cột RỖNG ở mọi hàng — một cột không bao giờ có
       chữ thì không phải cột. Bước này gỡ được cặp mép của CÙNG một rãnh mà
       không phá ranh giới thật.

    KHÔNG mâu thuẫn spec §2.1 (khe trắng suốt trang đã bị bác bỏ): khe ở đây đo
    CỤC BỘ trong từng dòng, nên một dòng tiêu đề ngang chỉ đơn giản không đóng
    góp ứng viên nào, còn mấy chục dòng thân vẫn đóng góp.
    """
    boi_khe = BOI_KHE if boi_khe is None else boi_khe
    ty_le_ung_ho = TY_LE_UNG_HO if ty_le_ung_ho is None else ty_le_ung_ho
    if not words:
        return []
    dong = _theo_dong(words)
    rong_ky_tu = be_rong_ky_tu(words)
    nguong_khe = boi_khe * rong_ky_tu

    mep_trai: list[int] = []       # mép trái của từ SAU khe
    mep_phai: list[int] = []       # mép phải của từ TRƯỚC khe
    for ws in dong.values():
        theo_x = sorted(ws, key=lambda w: w.left)
        for a, b in zip(theo_x, theo_x[1:]):
            het_a = a.left + a.width
            if b.left - het_a >= nguong_khe:
                mep_trai.append(b.left)
                mep_phai.append(het_a)

    toi_thieu = max(2, int(len(dong) * ty_le_ung_ho))
    ung_vien = sorted({int(statistics.median(c))
                       for tap in (mep_trai, mep_phai)
                       for c in _cum(tap, rong_ky_tu) if len(c) >= toi_thieu})
    if not ung_vien:
        return []

    def _co_chu(lo: int, hi: int) -> bool:
        return any(lo <= (w.left + w.width // 2) < hi for w in words)

    giu: list[int] = []
    for x in ung_vien:
        if _co_chu(giu[-1] if giu else -10**9, x):
            giu.append(x)
    if giu and not _co_chu(giu[-1], 10**9):
        giu.pop()
    return giu


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
