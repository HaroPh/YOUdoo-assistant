"""Bậc 2: dựng lưới bảng từ toạ độ chữ mà Tesseract trả về.

Module LÁ: nhận `list[OcrWord]`, trả về `list[list[str]]` là bảng với cấu trúc
cột. KHÔNG sửa chữ trong ô, KHÔNG dò bảng — chỉ lo cấu trúc.
"""
import re
import statistics
from .engine import OcrWord

# ĐO LẠI 2026-09-07 SAU KHI GỘP THƯỚC (phát hiện I6 của review toàn nhánh):
# `calibrate_table.py` và cổng A nay dùng CHUNG `src/ocr/table_score.py`, và
# thước chung loại ô XUỐNG DÒNG khỏi CẢ HAI vế — bản `_score` chép tay cũ
# trong `calibrate_table.py` KHÔNG có xử lý đó, nên bảng số đo chốt tham số
# trước đây được sinh bởi một cái thước KHÁC cái thước cổng A đang gác. Bảng
# dưới đây THAY TRỌN bảng cũ; mẫu số đổi từ 7.456 xuống 7.042 ô (414 ô xuống
# dòng nay bị loại khỏi vế `kept` ở phía hiệu chỉnh nữa), nên MỌI con số đều
# nhích lên và KHÔNG so trực tiếp được với bảng cũ.
#
# Đo trên toàn bộ trang bảng vector của corpus (107 tệp có ô, 234 trang, 7.042
# ô chấm được + 2.485 ô BỎ vì tầng đọc hỏng, chủ yếu bảng danh mục hoá chất
# trong phụ lục luật — giới hạn của TẦNG ĐỌC, không phải của bậc 2). Đáp án tự
# sinh từ `pdfplumber` bóc chính trang đó. Quét lưới 6x5 tham số + một cấu
# hình THỬ PHÁ. Thuật toán `find_column_bounds` là bản MÉP CẠNH KHE (xem
# docstring hàm đó).
#
#    gap_factor   ty_le      kept     tach      min  unreadable   cot_tb  trang_suy_bien
#        2.0     0.6   0.9227   0.9517   0.9227         2485     4.53             148
#        1.5     0.6   0.9218   0.9521   0.9218         2485     4.55             142
#        1.0     0.6   0.9215   0.9521   0.9215         2485     4.60             135
#        2.0    0.45   0.9198   0.9549   0.9198         2485     4.67             125
#        1.5    0.45   0.9192   0.9549   0.9192         2485     4.72             118
#        1.0    0.45   0.9171   0.9559   0.9171         2485     4.84             109
#        3.0     0.3   0.9156   0.9188   0.9156         2485     4.51             119   <- chọn (không phải MIN cao nhất — xem lý do dưới)
#        3.0    0.45   0.9208   0.9143   0.9143         2485     4.31             133
#        2.0     0.3   0.9114   0.9580   0.9114         2485     4.91             108
#        3.0    0.15   0.9059   0.9225   0.9059         2485     4.85             112
#        1.5     0.3   0.9037   0.9581   0.9037         2485     5.04              96
#        1.0     0.3   0.9014   0.9584   0.9014         2485     5.35              84
#        3.0     0.6   0.9227   0.8978   0.8978         2485     4.11             153
#        2.0    0.15   0.8875   0.9617   0.8875         2485     5.33              95
#        1.5    0.15   0.8721   0.9620   0.8721         2485     5.64              80
#        1.0    0.15   0.8678   0.9622   0.8678         2485     6.27              70
#        1.0    0.75   0.9263   0.8547   0.8547         2485     3.76             162
#        1.5    0.75   0.9264   0.8546   0.8546         2485     3.73             166
#        2.0    0.75   0.9264   0.8546   0.8546         2485     3.72             170
#        3.0    0.75   0.9264   0.7542   0.7542         2485     3.21             174
#        5.0    0.15   0.9060   0.7506   0.7506         2485     3.88             125
#        0.5    0.75   0.7438   0.8659   0.7438         2485     5.56              75
#        5.0     0.3   0.9156   0.7189   0.7189         2485     3.59             130
#        0.5     0.6   0.7126   0.9578   0.7126         2485     7.23              55
#        0.5    0.45   0.7051   0.9579   0.7051         2485     8.77              47
#        0.5     0.3   0.7041   0.9591   0.7041         2485    10.56              38
#        0.5    0.15   0.7026   0.9622   0.7026         2485    12.01              36
#        5.0    0.45   0.9208   0.6927   0.6927         2485     3.40             141
#        5.0     0.6   0.9227   0.6595   0.6595         2485     3.23             159
#        5.0    0.75   0.9264   0.5850   0.5850         2485     2.56             176
#
#    (THỬ PHÁ — suy biến một cột, gap_factor=1000.0, ty_le=0.3)
#     1000.0     0.3   0.9387   0.0365   0.0365         2485     1.00             386
#
# Cột THỬ PHÁ chứng minh thước còn sống: `gap_factor=1000` (không khe nào đủ
# lớn để thành bounds giới) suy biến MỌI bảng về MỘT cột (`cot_tb=1.00`,
# `trang_suy_bien=386` — nhiều nhất bảng) và bị phạt xuống `min=0.0365`, thấp
# hơn hẳn cặp tốt nhất — nếu nó KHÔNG rớt thì thước không đo gì.
#
# ═══ TẠI SAO ĐỔI THUẬT TOÁN (2026-09-07) — VÀ TẠI SAO KHÔNG CHỌN THEO BẢNG TRÊN ═══
#
# 1. ĐIỂM-GIỮA-KHE KHÔNG CHẠY TRÊN SCAN THẬT. Bảng trên đo trên corpus VECTOR,
#    nhưng lý do sửa hàm là BCTC SCAN THẬT (SCID) — trên đó, nhãn chỉ tiêu kết
#    thúc ở x khác nhau mỗi hàng nên điểm giữa khe tản mát, KHÔNG BAO GIỜ CỤM.
#    Đo được bằng thuật toán điểm-giữa CŨ: trang 12 ra `[234]`, trang 13 ra
#    `[228]` — cả hai chỉ là rãnh sau SỐ THỨ TỰ, không phải cột thật; **trang
#    17 ra `[]` — MỘT cột, không tìm được bounds giới nào**. Tức là bậc 2 không
#    chạy được trên đúng tài liệu nó sinh ra để xử lý. Mép cạnh khe (mép trái
#    của từ sau khe, mép phải của từ trước khe, rồi lọc cột rỗng) sửa đúng chỗ
#    này — xem docstring `find_column_bounds`.
#
# 2. HAI CỔNG ĐÒI THAM SỐ KHÁC NHAU, và corpus vector không phải cổng quyết
#    định. Trên bảng ở trên, `support_ratio=0.6` (gap_factor=2.0) có MIN cao nhất
#    (0,9227). Nhưng đo THẲNG số cột `find_column_bounds` dựng ra trên 7 trang BCTC
#    SCAN THẬT (trang 12–18) theo từng mức `ty_le` (`gap_factor` hầu như không
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
# 3. CHỐT: `GAP_FACTOR=3.0, SUPPORT_RATIO=0.3` — KHÔNG phải cấu hình MIN cao nhất
#    trên bảng corpus vector (đó là `2.0/0.6`, min=0,9227). Đánh đổi MIN tụt
#    còn `0,9156` (dòng `<- chọn` ở trên, chênh ≈0,007) để đổi lấy việc bậc 2
#    THẬT SỰ CHẠY trên cả 7/7 trang scan thay vì chết trên 4/7. Đo lại sau khi
#    gộp thước (2026-09-07) KHÔNG đổi kết luận: cấu hình tối ưu của corpus
#    vector dịch từ `3.0/0.6` sang `2.0/0.6` nhưng vẫn ở `ty_le=0.6`, mức làm
#    4/7 trang scan sập về một cột, và khoảng cách tới cấu hình chọn vẫn
#    ≈0,007 — cùng một đánh đổi, cùng một phán quyết (P13).
#
# 4. GIỚI HẠN: ở `ty_le=0.3`, trang 12–13 của BCTC scan ra 9–12 cột trong khi
#    bảng thật chỉ có 5 cột — TÁCH HƠI VỤN (rãnh nội bộ trong ô đôi khi bị bắt
#    nhầm thành bounds giới). Chấp nhận: hỏng-vụn vẫn giữ được dữ liệu đọc được
#    (khác hẳn hỏng-sập-về-một-cột, là MẤT TRẮNG cấu trúc — xem mục "HAI KIỂU
#    HỎNG KHÔNG CÙNG GIÁ" dưới). Cần đo lại nếu kho có thêm tài liệu scan để
#    xem mức tách-vụn này có ổn định không.
#
# GIỚI HẠN ĐO ĐƯỢC KHÁC, nói thẳng vì đây là dữ kiện chứ không phải chi tiết vặt:
# - **`trang_suy_bien = 119/234`** ở cấu hình chọn (đo trên corpus vector) —
#   một phần bảng trong corpus vector không dựng lại được cấu trúc (suy biến
#   về một cột), chủ yếu vì tầng đọc không đọc nổi chúng (danh mục hoá chất,
#   biểu mẫu chữ nhỏ).
# - **`2.485/9.527 ô (26%)`** bị bỏ vì tầng đọc hỏng khi chấm điểm — giới hạn
#   của TẦNG ĐỌC, không phải của bậc 2 (spec §2.4, §10).
#
# LÝ DO CHỌN, tổng quát hoá cho cả hai cổng: HAI KIỂU HỎNG KHÔNG CÙNG GIÁ.
#   - Bảng SUY BIẾN VỀ MỘT CỘT = bậc 2 không cho gì thêm = ĐÚNG BẰNG hành vi
#     hôm nay (dòng phẳng). Hỏng AN TOÀN, không đưa gì sai vào corpus.
#   - Bảng TÁCH SAI/VỤN CỘT = bounds giới ô sai đi THẲNG vào corpus như dữ liệu
#     thật. Hỏng CÓ HẠI, nhưng còn dữ liệu để dùng — khác hẳn mất trắng.
# Tiêu chí chốt là tối đa hoá độ đúng cấu trúc Ở NƠI CÓ dựng cấu trúc, ưu tiên
# KHÔNG SẬP trên tài liệu SCAN THẬT (mục tiêu thật của bậc 2) hơn là MIN cao
# nhất trên corpus vector (proxy). Nếu về sau đo thấy tách-vụn ở `ty_le=0.3`
# gây hại nhiều hơn dự đoán trên tập scan lớn hơn, đổi tham số là SỬA HAI DÒNG
# hằng số — bảng trên đã đủ để so lại không cần đo thêm trên corpus vector.
#
# LỊCH SỬ BỊ BÁC BỎ (giữ lại để người sau không lặp lại): một tiêu chí sớm
# từng thử "MIN cao nhất trong số cấu hình KHÔNG làm tăng `trang_suy_bien` so
# với `ty_le` liền dưới cùng `gap_factor`" — script `calibrate_table.py` vẫn tự
# in ra lựa chọn này ở cuối mỗi lần chạy (`gap_factor=3.0 ty_le=0.15`) NHƯNG đó
# không phải tham số chốt của module này. Tiêu chí đó SAI: vì `trang_suy_bien`
# tăng đơn điệu theo `ty_le` ở MỌI `gap_factor` trên corpus vector, nó loại sạch
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
# mẫu số (đếm ra ở `unreadable`).
#
# FIX ROUND 2 (cùng ngày): thước round 1 CHỈ đo một vế — "không tách nhầm" —
# nên một lưới suy biến MỘT CỘT ăn điểm tuyệt đối miễn phí (cả hàng là một ô
# nên vế đó luôn đúng). Đo được: `gap_factor=1000` vẫn đạt 0,9014 trên thước
# round 1 dù không dựng bounds giới nào. Sửa: thêm vế đối xứng "không gộp
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
#
# ================== VÒNG 2026-09-07: SUPPORT_RATIO 0.3 -> 0.15 ==============
# `ty_le=0.3` ở trên được chốt trên corpus VECTOR cộng một phán quyết bằng mắt
# sau khi nhìn ĐÚNG MỘT tài liệu scan (SCID), và thực ra chỉ 7 trang của nó.
# Kéo về thêm 5 báo cáo tài chính ảnh thuần rồi đo lại thì cấu hình đó
# **sập 12 trang bảng** trên corpus scan, tách đúng chỉ 0,7736.
#
# Chỗ đau nhất: 7 trang đáp án của SCID đạt 91/91 = 1,000, còn 21 trang bảng
# CÒN LẠI của chính tài liệu đó chỉ 124/231 = 0,537. Bảy trang ấy do chính tôi
# chọn — chúng không chỉ dễ hơn, chúng là phần DUY NHẤT chạy đúng.
#
# NGUYÊN NHÂN: `min_support` lấy mẫu số là số dòng CẢ TRANG. Trang thuyết minh
# có bảng nhỏ (6-12 hàng) nằm trong trang dài (40-52 dòng), nên một ranh giới
# được 12/12 hàng bảng ủng hộ vẫn chỉ đạt 23% của trang và bị loại.
#
# BỘ HIỆU CHỈNH NAY CÓ HAI CHÂN (`tools/calibrate_table.py`), và điểm chốt là
# min(chân vector, chân scan). Bảng đầy đủ ở `calibrate_table_result.txt`:
#
#   gap  ty_le | vector min | scan tách  sập  cột_max | GỘP
#   3.0   0.15     0.9059       0.9648    1      18     0.9059  <- CHỐT
#   3.0   0.12     0.9023       0.9757    0      18     0.9023
#   3.0   0.30     0.9156       0.7736   12      12     0.7736  <- đang ship
#   2.0   0.60     0.9227       0.2303   82       6     0.2303
#   thử phá (gap=1000)  0.0365   0.0000   —       —     0.0000
#
# Hai dòng cuối là lý do chân scan phải tồn tại: `2.0/0.6` có chân vector CAO
# NHẤT cả bảng mà làm sập 82 trang scan. Và `3.0/0.3` đang ship cũng có chân
# vector cao hơn cấu hình được chọn — nghĩa là nhìn riêng corpus vector thì
# thay đổi này trông như đi lùi. Nó không lùi: scan mới là đầu vào thật của
# bậc 2, corpus vector đã có pdfplumber lo.
#
# SỬA LẠI LẬP LUẬN "HAI KIỂU HỎNG KHÔNG CÙNG GIÁ" Ở TRÊN: vẫn đúng rằng suy
# biến về một cột KHÔNG làm hỏng dữ liệu (hàng rơi ra ngoài dải bảng thì
# `parse.py` trả về đường dòng phẳng cũ). Nhưng nó bị dùng để BIỆN MINH cho
# `ty_le` cao, mà giá thật của nó là bậc 2 KHÔNG LÀM GÌ trên 12/38 trang scan
# — hỏng an toàn vẫn là hỏng, và ở đây là hỏng trên phần lớn tài liệu đích.
#
# VÀ MỘT LẦN TỰ SỬA: đoạn "LỊCH SỬ BỊ BÁC BỎ" ở trên bác `ty_le=0.15` vì tiêu
# chí sinh ra nó là LỌC máy móc chứ không phải CHỌN. Lời bác đó VẪN ĐÚNG về
# tiêu chí. Nhưng con số nó bác lại là con số đúng — đến bằng đường khác, qua
# hai chân đo. Trùng hợp, không phải minh oan cho tiêu chí cũ.
#
# 0,15 vs 0,12 gần như hoà (0,9059 vs 0,9023, chênh nằm ở chân vector); 0,12
# hơn ở chỗ 0 trang sập. Chốt theo ĐÚNG output của công cụ, không đè bằng tay
# — đè bằng tay chính là cách `ty_le=0.3` ra đời.
GAP_FACTOR = 3.0
SUPPORT_RATIO = 0.15

# ═══ DẢI HÀNG TRÔNG NHƯ BẢNG (thêm 2026-09-07, đóng phát hiện C1) ═══
#
# VÌ SAO CẦN: bậc 1 luôn nhả ĐÚNG MỘT `Region` phủ CẢ TRANG, nên `build_grid`
# chạy trên cả letterhead/tiêu đề/chân trang chứ không riêng thân bảng. Lưới
# cả trang đi thẳng vào `split_header_body`/`column_names` thì ba dòng
# letterhead thành TÊN CỘT. Đo được trên SCID tr12 TRƯỚC khi sửa: tên cột dài
# **136 ký tự** ("TY CỔ PHẦN ĐẦU TƯ PHÁT TRIỂN SÀI GÒN CO.OP Số 199-205 Nguyễn
# Thái Học, ... TÀI CHÍNH HỢP NHAT GIỮA NIÊN ĐỘ"), lặp trong MỌI block, hàng
# header thật rơi xuống thân, hai cột tiền thành `Cột 6`/`Cột 8`.
#
# CÁCH LÀM: chỉ những DẢI HÀNG LIÊN TIẾP trông như bảng mới đi đường lưới;
# hàng ngoài dải quay về đường dòng-phẳng cũ (`heading_level` + lọc furniture).
#
# ĐO 2026-09-07 — lưới 2 chiều (K = số ô KHÔNG RỖNG tối thiểu của một hàng
# "trông như bảng"; M = số hàng tối thiểu của một dải) trên 7 trang BCTC SCAN
# THẬT (SCID tr12–18, 93 hàng đáp án đối chiếu được). `LH` = số dải mà
# `column_names()` của nó CÒN chứa chữ letterhead (0 là bắt buộc — đó chính là
# nghiệm thu C1); `maxCột` = tên cột dài nhất sinh ra; `phủ` = số hàng đáp án
# nằm TRONG một dải bảng (cao là tốt: hàng rơi ra ngoài dải mất cấu trúc cột).
#
#    K   M   dải   maxCột   LH    phủ/93
#    2   2    24      286    7     93      <- thiết kế "≥2 ô" ĐƠN THUẦN: letterhead VẪN vào tên cột
#    2   3    16      286    6     91
#    2   4    16      286    6     91
#    2   5    13      286    6     89
#    2   6    12      286    5     89
#    3   2    34       93    3     89
#    3   3    21       93    2     86
#    3   4    18       93    2     84
#    3   5    11       51    0     77
#    3   6    11       51    0     77
#    4   2    23       21    0     88      <- CHỌN
#    4   3    17       21    0     83
#    4   4    15       21    0     80
#    4   5     9       15    0     72
#    4   6     9       15    0     72
#    5   2    20       21    0     80
#    5   3    15       21    0     74
#    5   4    10       21    0     69
#    5   5     8       15    0     65
#    5   6     8       15    0     65
#
# ĐỌC BẢNG: ngưỡng "≥2 ô không rỗng" KHÔNG đủ ở BẤT KỲ M nào — kể cả M=8
# (đo riêng: LH=5, maxCột=286). Lý do đo được: trên tr13–tr17 khối letterhead
# LIỀN MẠCH với thân bảng (không có hàng gần-rỗng nào chen giữa), nên mọi dải
# đều nuốt letterhead bất kể dải dài bao nhiêu. Phải siết chính vị từ
# "trông như bảng", không phải chỉ độ dài dải. Trong số các cấu hình SẠCH
# letterhead (LH=0), K=4/M=2 có độ phủ CAO NHẤT (88/93 = 0,946).
#
# ĐO TRÊN TẬP 6 TRANG CỦA CỔNG A (cùng hai hằng số, lưới CẢ TRANG như đường
# `parse.py` chứ không phải lưới trong khung bảng như cổng A chấm):
#
#    K   M   dải   maxCột   phủ/20
#    2   2    17      175     17     <- letterhead/tiêu đề vào tên cột (maxCột=175)
#    3   2    13       15      0
#    4   2     0        0      0     <- CHỌN: KHÔNG dải nào, mọi hàng về đường dòng-phẳng
#
# Lưới CẢ TRANG của 6 trang này chỉ có 2–3 cột (trang vector nhiều văn xuôi,
# `find_column_bounds` chỉ tìm được 1–2 ranh giới), nên không hàng nào đạt 4 ô
# không rỗng và đường lưới TẮT HẲN trên chúng. Đó là suy biến AN TOÀN, đúng
# nguyên tắc "hai kiểu hỏng không cùng giá" ở trên: không dựng bảng = đúng
# bằng hành vi hôm nay, còn dựng bảng từ lưới 3 cột của một trang văn xuôi thì
# đưa tên cột rác vào corpus. Và 6 trang này là tài liệu VECTOR — production
# không bao giờ OCR chúng (`parse_pdf` chỉ gọi bậc 1 khi trang KHÔNG có lớp
# text), nên đây là proxy, không phải mục tiêu.
#
# GIỚI HẠN CÒN LẠI, nói thẳng: dải bảng của tr12 bắt đầu ở hàng 13 vì hàng 12
# (một ký tự rác "C") cắt đứt dải khỏi hàng header thật (hàng 10–11: "CHỈ TIÊU
# | Mã số | Thuyết minh | Số cuối kỳ | Số đầu năm"). Hậu quả: tên cột của dải
# đó là `Cột 1..N` chứ KHÔNG phải tên thật. Letterhead đã hết (nghiệm thu C1
# đạt) nhưng câu hỏi "số nào cuối kỳ, số nào đầu năm" chỉ đóng được ở những
# trang mà header dính liền thân. Nối dải qua khe 1 hàng là hướng sửa tiếp,
# CHƯA làm vì nó là hằng số THỨ BA và phải đo riêng.
MIN_TABLE_ROW_CELLS = 4
MIN_TABLE_RUN_ROWS = 2

# ĐO 2026-09-08, trên 95 trang / 6 tài liệu scan, thước KHÔNG CẦN ĐÁP ÁN
# (hàng có ≥2 chuỗi tiền phân biệt; `row_to_text` gán cho chúng nhãn gì):
#   bắc cầu  cửa sổ header   tên cột CÓ NGHĨA
#   (không)  (không)          98/326 = 0,301   <- trước
#   1        (không)         165/383 = 0,431
#   (không)  3               153/326 = 0,469
#   1        3               234/383 = 0,611   <- chốt
#   1        6               235/383 = 0,614   (hơn 0,003, cửa sổ rộng gấp đôi)
#   2        3               222/404 = 0,550
# Trên 7 trang đáp án SCID cùng cấu hình: 24/88 = 0,273 -> 54/94 = 0,574. Số
# trên CẢ CORPUS nhỉnh hơn số trên 7 trang, tức lần này KHÔNG có hiệu ứng chọn
# mẫu — khác hẳn vòng chốt SUPPORT_RATIO (xem mục 8 ghi chú thi hành).
MAX_RUN_GAP_ROWS = 1
HEADER_SEARCH_ROWS = 3
MIN_HEADER_CELLS = 3

# Chuỗi tiền kiểu Việt. MỘT bản duy nhất, dùng bởi cả `find_header_rows` (loại
# hàng có số ra khỏi ứng viên header) lẫn `table_score.score_unlabelled`.
MONEY = re.compile(r"^\(?\d{1,3}(?:\.\d{3})+\)?$")


def median_char_width(words: list[OcrWord]) -> float:
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


def _group_by_line(words: list[OcrWord]) -> dict:
    """Gom từ theo `line_id`, GIỮ NGUYÊN thứ tự dòng xuất hiện."""
    ra: dict = {}
    for w in words:
        ra.setdefault(w.line_id, []).append(w)
    return ra


def _cluster(values: list[int], tolerance: float) -> list[list[int]]:
    """Gom số gần nhau thành cụm, tham lam theo thứ tự tăng dần."""
    if not values:
        return []
    ordered = sorted(values)
    groups: list[list[int]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - groups[-1][-1] <= tolerance:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def find_column_bounds(words: list[OcrWord], *, gap_factor: float | None = None,
                 support_ratio: float | None = None) -> list[int]:
    """Ranh giới cột = MÉP của từ cạnh một KHE LỚN, cụm lại qua nhiều dòng.

    Ba bước, và cả ba đều cần thiết:

    1. Trong TỪNG dòng, khe giữa hai từ liền nhau rộng hơn `gap_factor` lần bề rộng
       ký tự là ứng viên. Đây là thứ phân biệt khe giữa hai từ trong CÙNG một ô
       (khoảng một ký tự) với khe sang cột khác (hàng chục ký tự).
    2. Vị trí lấy từ MÉP cạnh khe, KHÔNG phải điểm giữa khe: mép TRÁI của từ SAU
       khe (cột căn trái, ví dụ `Mã số`) và mép PHẢI của từ TRƯỚC khe (cột căn
       phải, ví dụ cột tiền). Ứng viên phải cụm lại cùng một x qua đủ nhiều dòng.

       Điểm giữa khe KHÔNG dùng được, và đây là chỗ đã trả giá: nhãn chỉ tiêu
       kết thúc ở x khác nhau mỗi hàng nên điểm giữa tản mát, không bao giờ cụm.
       Đo được trên BCTC scan thật: cách điểm-giữa chỉ tìm ra rãnh sau SỐ THỨ TỰ
       (x≈230) và bỏ sót toàn bộ cột thật; trang 17 không ra bounds giới nào. Cách
       mép ra đúng `930/965` (cột `Mã số`), `1300` và `1549` — khớp chính xác số
       đo spec §2.2 (tiền căn phải ở x≈1290–1305 và x≈1545–1560).
    3. Bỏ bounds giới nào sinh ra cột RỖNG ở mọi hàng — một cột không bao giờ có
       chữ thì không phải cột. Bước này gỡ được cặp mép của CÙNG một rãnh mà
       không phá bounds giới thật.

    KHÔNG mâu thuẫn spec §2.1 (khe trắng suốt trang đã bị bác bỏ): khe ở đây đo
    CỤC BỘ trong từng dòng, nên một dòng tiêu đề ngang chỉ đơn giản không đóng
    góp ứng viên nào, còn mấy chục dòng thân vẫn đóng góp.
    """
    gap_factor = GAP_FACTOR if gap_factor is None else gap_factor
    support_ratio = SUPPORT_RATIO if support_ratio is None else support_ratio
    if not words:
        return []
    dong = _group_by_line(words)
    char_w = median_char_width(words)
    gap_min = gap_factor * char_w

    left_edges: list[int] = []       # mép trái của từ SAU khe
    right_edges: list[int] = []       # mép phải của từ TRƯỚC khe
    for ws in dong.values():
        by_x = sorted(ws, key=lambda w: w.left)
        for a, b in zip(by_x, by_x[1:]):
            a_right = a.left + a.width
            if b.left - a_right >= gap_min:
                left_edges.append(b.left)
                right_edges.append(a_right)

    min_support = max(2, int(len(dong) * support_ratio))
    candidates = sorted({int(statistics.median(c))
                       for tap in (left_edges, right_edges)
                       for c in _cluster(tap, char_w) if len(c) >= min_support})
    if not candidates:
        return []

    def _has_text(lo: int, hi: int) -> bool:
        return any(lo <= (w.left + w.width // 2) < hi for w in words)

    kept: list[int] = []
    for x in candidates:
        if _has_text(kept[-1] if kept else -10**9, x):
            kept.append(x)
    if kept and not _has_text(kept[-1], 10**9):
        kept.pop()
    return kept


def build_grid(words: list[OcrWord], *, gap_factor: float | None = None,
              support_ratio: float | None = None) -> list[list[str]]:
    """`list[OcrWord]` -> `list[list[str]]`.

    Hàng lấy theo `line_id` Tesseract đã trả sẵn, GIỮ NGUYÊN thứ tự xuất hiện.
    Không tự gom lại theo toạ độ y: tesseract gom tốt hơn, và bậc 1 đã ghi bài
    học "đừng sắp xếp lại thứ tự đọc" — khác biệt thứ tự đọc từng bị nhầm thành
    chất lượng OCR kém.

    Không bounds giới nào = MỘT cột. Đó là đường suy biến cho trang văn xuôi,
    KHÔNG phải lỗi: không có bộ dò bảng thì không có gì để bắn nhầm (spec §4).
    """
    if not words:
        return []
    # Giải lúc GỌI, không dùng hằng số làm giá trị mặc định — xem test
    # `test_mac_dinh_doc_lai_hang_so_luc_GOI...` và bẫy đã cắn bậc 1. Chỉ
    # chuyển tiếp xuống `find_column_bounds`, nhưng vẫn phải nhận `None` ở đây để
    # người gọi không phải tự tra hằng số.
    gap_factor = GAP_FACTOR if gap_factor is None else gap_factor
    support_ratio = SUPPORT_RATIO if support_ratio is None else support_ratio
    bounds = find_column_bounds(words, gap_factor=gap_factor, support_ratio=support_ratio)
    grid: list[list[str]] = []
    for ws in _group_by_line(words).values():
        o: list[list[str]] = [[] for _ in range(len(bounds) + 1)]
        for w in sorted(ws, key=lambda x: x.left):
            centre = w.left + w.width // 2
            o[sum(1 for r in bounds if centre > r)].append(w.text)
        grid.append([" ".join(phan) for phan in o])
    return grid


def is_table_like_row(row: list[str], *, min_cells: int | None = None) -> bool:
    """Hàng lưới có ĐỦ số ô không rỗng để trông như một hàng bảng.

    Hằng số đọc lúc GỌI, không dùng làm giá trị mặc định của tham số — cùng
    bẫy đã cắn bậc 1 (xem `build_grid`)."""
    min_cells = MIN_TABLE_ROW_CELLS if min_cells is None else min_cells
    return sum(1 for c in row if c.strip()) >= min_cells


def table_row_runs(grid: list[list[str]], *, min_cells: int | None = None,
                   min_rows: int | None = None,
                   max_gap: int | None = None) -> list[tuple[int, int]]:
    """Các DẢI `[start, end)` hàng LIÊN TIẾP trông như bảng, dải đủ dài.

    Trả về danh sách khoảng nửa mở, tăng dần, KHÔNG chồng nhau. Hàng không
    nằm trong dải nào là hàng văn xuôi/letterhead/chân trang — người gọi phải
    đưa nó về đường dòng-phẳng, đừng nhét vào `split_header_body`.

    BẮC CẦU (`max_gap`, 2026-09-08): dải được phép nuốt tối đa `max_gap` hàng
    KHÔNG-trông-như-bảng nằm GIỮA hai hàng bảng. Không có nó thì một hàng rác
    scan cắt lìa header khỏi thân: đo được trên SCID tr12 — hàng 11 là header
    thật (`CHỈ TIÊU | số | minh | Số cuối kỳ | Số đầu năm`, 6 ô đầy), hàng 12
    chứa ĐÚNG MỘT ký tự `C` (vệt dấu mộc), nên hàng 11 đứng một mình thành
    dải dài 1 < `MIN_TABLE_RUN_ROWS` và bị vứt; thân bảng bắt đầu lại ở hàng
    13 với KHÔNG hàng header nào, `column_names([])` trả rỗng, mọi cột thành
    `Cột N`. Xem bảng đo cạnh `MAX_RUN_GAP_ROWS`.

    Khe ở HAI ĐẦU dải KHÔNG được tính — chỉ khe nằm giữa hai hàng bảng, nên
    dải không bao giờ dài ra quá hàng-bảng cuối cùng.

    Xem bảng đo cạnh `MIN_TABLE_ROW_CELLS` để biết vì sao hai hằng số kia là 4
    và 2, và vì sao ngưỡng "≥2 ô không rỗng" một mình KHÔNG đủ.
    """
    min_rows = MIN_TABLE_RUN_ROWS if min_rows is None else min_rows
    max_gap = MAX_RUN_GAP_ROWS if max_gap is None else max_gap
    runs: list[tuple[int, int]] = []
    start: int | None = None
    end = 0          # sau hàng-bảng CUỐI CÙNG đã thấy trong dải đang mở
    gap = 0
    for i, row in enumerate(grid):
        if is_table_like_row(row, min_cells=min_cells):
            if start is None:
                start = i
            end = i + 1
            gap = 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                if end - start >= min_rows:
                    runs.append((start, end))
                start, gap = None, 0
    if start is not None and end - start >= min_rows:
        runs.append((start, end))
    return runs


def has_numeric_data(row: list[str]) -> bool:
    """Hàng lưới có mang dữ liệu SỐ không (mã số, tiền, ngày, tỷ lệ...).

    Hàng thân KHÔNG có chữ số nào gần như luôn là văn xuôi lọt vào dải bảng:
    dòng tiêu đề mục, câu chú thích cuối bảng, mảnh letterhead, khối chữ ký.
    Xé chúng thành cột làm hỏng chunk — đo được 633/1980 = 32,0% hàng thân đi
    qua đường lưới rơi vào loại này, và chuỗi sinh ra trông như
    `Cột 2: Báo | VÕ THỊ KIM LANG: cáo này phải được doc cing với Bản`: một
    câu bị băm làm đôi và dán nhãn bằng TÊN NGƯỜI.

    Đây KHÔNG phải ngưỡng hiệu chỉnh mà là một bất biến: người gọi đưa hàng
    không có số về đường dòng-phẳng, y như hàng nằm ngoài dải.
    """
    return any(c.isdigit() for cell in row for c in cell)


def find_header_rows(grid: list[list[str]], body_start: int, *,
                     window: int | None = None,
                     min_cells: int | None = None) -> list[list[str]]:
    """Tối đa hai hàng HEADER nằm ngay trên `body_start`, tìm theo NỘI DUNG.

    Vì sao không tin `split_header_body` một mình: nó coi MỌI hàng trước hàng
    có-ô-số-thuần đầu tiên là header. Trên scan thật, một token số lạc trong
    letterhead (ngày tháng, số trang, mảnh dấu mộc) làm nó tuyên bố thân bảng
    đã bắt đầu, nên hàng header THẬT rơi vào thân và tên cột lấy từ letterhead
    — đo được trên SCID tr13: tên cột thành `'TY CỔ PHẦN ĐẦU Số 199-205
    Nguyễn Thái TÀI CHÍNH HỢP'`. Đây là họ hàng gần của C1, thu nhỏ từ CẢ
    TRANG xuống một dải.

    Tiêu chí một hàng header: ≥`min_cells` ô không rỗng và KHÔNG chứa chuỗi
    tiền nào. Gặp hàng có tiền thì DỪNG hẳn — đã chạm thân bảng, không leo
    tiếp lên trên. Lấy tối đa hai hàng để đỡ được header hai dòng kiểu
    `Mã`/`số`, `Thuyết`/`minh`.

    Trả về [] khi không tìm thấy; người gọi giữ nguyên header cũ khi đó.
    """
    window = HEADER_SEARCH_ROWS if window is None else window
    min_cells = MIN_HEADER_CELLS if min_cells is None else min_cells
    out: list[list[str]] = []
    for i in range(body_start - 1, max(-1, body_start - 1 - window), -1):
        row = grid[i]
        if any(MONEY.match(t) for cell in row for t in cell.split()):
            break
        if sum(1 for c in row if c.strip()) >= min_cells:
            out.insert(0, row)
            if len(out) == 2:
                break
    return out
