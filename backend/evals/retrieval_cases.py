# backend/evals/retrieval_cases.py
"""Golden set truy xuất — spec 2026-08-19 §7.

CẤU TRÚC: (question, expected_labels, difficulty)
  expected_labels: frozenset[(basename tệp, section_path)] — xem
  retrieval_score.label_of(). Neo vào CẶP chứ không phải chunk_id (bigserial,
  re-index đổi sạch) và không phải section_path đơn ("Điều 3. Giải thích từ
  ngữ" có 32 chunk nằm rải nhiều luật khác nhau — neo đơn sẽ tính trúng nhầm
  luật thành trúng).

  difficulty:
    easy — từ khoá câu hỏi trùng mặt chữ với tiêu đề mục; FTS một mình cũng trúng
    hard — diễn đạt khác hẳn, KHÔNG mượn từ ngữ của tiêu đề; chỗ dense + rerank
           kiếm ăn
    trap — từ khoá trùng nhưng ý KHÁC; nhãn đúng nằm ở VĂN BẢN KHÁC với văn bản
           mà từ khoá gợi ý. Bắt lỗi trúng-nhầm-văn-bản.

MỌI NHÃN Ở ĐÂY ĐÃ ĐỐI CHIẾU với rag_chunks ngày 2026-08-19, chép nguyên văn.
test_retrieval_cases.py chốt lại điều này mỗi lần chạy — đừng sửa theo trí nhớ.

CÂN ĐỐI CÓ CHỦ ĐÍCH: 3.256/3.300 chunk (98,7%) là 9 PDF luật, nhưng mọi câu
hỏi rag trong cases.py chỉ chạm 44 chunk nghiệp vụ. Bộ này đảo lại tỉ lệ đó.

BA CÂU BỊ LOẠI khỏi nguồn tái dùng vì corpus KHÔNG có tài liệu trả lời:
"quy trình xử lý khiếu nại khách hàng?", "điều kiện bảo hành sản phẩm gỗ?",
"quy định về đặt cọc cho đơn hàng lớn?". Chúng vẫn hữu ích cho bộ `synthesis`
(đo khả năng từ chối), nhưng ở đây thì vô nghĩa: golden set đòi >=1 nhãn
đúng, mà nhãn đúng của chúng không tồn tại.

KHÔNG gán nhãn vào các "mục" rác do parse_pdf sinh ra ("CỘNG HÒA XÃ HỘI CHỦ
NGHĨA VIỆT NAM", "CHỦ TỊCH QUỐC HỘI", "Chương I" trống, và 15 mảnh câu tham
chiếu chéo kiểu "Điều 11 của Luật này quy định."). Chúng là lỗi ingest mà P3
sẽ xoá; gán nhãn vào đó là đóng đinh lỗi vào chính thước đo.
"""

_POLICY = "policy.docx"
_DISCOUNT = "discount_policy.docx"
_PAYMENT = "payment_policy.docx"
_SLA = "sla.docx"
_SOP = "sop.docx"
_SALES = "sales_process.docx"
_OUTBOUND = "warehouse_outbound.docx"
_GIA = "bang_gia.xlsx"

_DANSSU = "boluat-danssu.pdf"
_THUONGMAI = "boluat-thuongmai.pdf"
_LAODONG = "boluat-laodong.pdf"
_DOANHNGHIEP = "luat-doanhnghiep.pdf"
_QUANLYTHUE = "luat-quanlythue.pdf"
_BHXH = "luat-baohiemxahoi.pdf"
_DAUTU = "luat-dautu.pdf"
_XNK = "luat-thuexuatnhapkhau.pdf"
_GTGT = "luat-thuegtgt.pdf"

RETRIEVAL_CASES: list[tuple[str, frozenset, str]] = [

    # ══ TÀI LIỆU NGHIỆP VỤ ═══════════════════════════════════════════════
    # Câu có chú thích "(cases.py)" là CHÉP NGUYÊN VĂN từ bộ eval sẵn có —
    # để hai bộ đo nói về cùng một câu hỏi, truy nguyên được khi một bên đổi.

    ("chính sách đổi trả hàng như thế nào?",  # (cases.py)
     frozenset({(_POLICY, "Chính sách hoàn hàng › Mục 1 — Điều kiện hoàn hàng"),
                (_POLICY, "Chính sách hoàn hàng › Mục 3 — Quy trình hoàn hàng"),
                (_POLICY, "Chính sách hoàn hàng › Mục 5 — Đổi hàng")}),
     "easy"),
    ("hàng giảm giá có được hoàn trả không?",  # (cases.py)
     frozenset({(_POLICY, "Chính sách hoàn hàng › Mục 2 — Ngoại lệ không được hoàn trả")}),
     "easy"),
    ("thời gian xử lý hoàn tiền là bao lâu?",  # (cases.py)
     frozenset({(_POLICY, "Chính sách hoàn hàng › Mục 4 — Hoàn tiền")}),
     "easy"),
    ("SOP nhập kho gồm những bước nào?",  # (cases.py)
     frozenset({(_SOP, "Quy trình nhập kho › Bước 1 — Kiểm đếm hàng hóa"),
                (_SOP, "Quy trình nhập kho › Bước 3 — Kiểm tra chất lượng"),
                (_SOP, "Quy trình nhập kho › Bước 5 — Bàn giao")}),
     "easy"),
    ("SLA giao hàng nội thành là bao lâu?",  # (cases.py)
     frozenset({(_SLA, "Thỏa thuận mức dịch vụ nhà cung cấp › Điều 3 — Thời gian giao hàng")}),
     "easy"),
    ("chính sách chiết khấu theo cấp khách như thế nào?",  # (cases.py)
     frozenset({(_DISCOUNT, "Chính sách chiết khấu theo cấp khách hàng › Mục 1 — Phân cấp khách hàng"),
                (_DISCOUNT, "Chính sách chiết khấu theo cấp khách hàng › Mục 2 — Mức chiết khấu theo cấp")}),
     "easy"),
    ("quy trình giao hàng gồm những bước nào?",  # (cases.py)
     frozenset({(_OUTBOUND, "Quy trình xuất kho › Mục 3 — Đóng gói và dán nhãn"),
                (_OUTBOUND, "Quy trình xuất kho › Mục 4 — Bàn giao và cập nhật hệ thống")}),
     "easy"),
    ("nhà cung cấp giao trễ thì bị xử lý ra sao?",
     frozenset({(_SLA, "Thỏa thuận mức dịch vụ nhà cung cấp › Điều 5 — Phạt chậm trễ giao hàng")}),
     "hard"),
    ("khách nợ quá hạn mức thì làm gì?",
     frozenset({(_PAYMENT, "Chính sách thanh toán và công nợ khách hàng › Điều 2 — Hạn mức công nợ"),
                (_PAYMENT, "Chính sách thanh toán và công nợ khách hàng › Điều 4 — Xử lý chậm thanh toán")}),
     "hard"),
    ("mua nhiều thì có được giảm thêm không?",
     frozenset({(_DISCOUNT, "Chính sách chiết khấu theo cấp khách hàng › Mục 3 — Chiết khấu theo số lượng")}),
     "hard"),
    ("kho báo thiếu hàng khi soạn đơn thì xử lý thế nào?",
     frozenset({(_OUTBOUND, "Quy trình xuất kho › Mục 5 — Xử lý thiếu hàng")}),
     "hard"),
    ("khách đổi ý sau khi đã chốt đơn thì sao?",
     frozenset({(_SALES, "Quy trình bán hàng › Mục 5 — Xử lý thay đổi đơn hàng")}),
     "hard"),
    ("hàng về kho có khớp với đơn đặt mua không thì ai kiểm?",
     frozenset({(_SOP, "Quy trình nhập kho › Bước 2 — Đối chiếu với đơn mua")}),
     "hard"),
    ("bên bán phải đóng gói hàng ra sao trước khi chuyển đi?",
     frozenset({(_SLA, "Thỏa thuận mức dịch vụ nhà cung cấp › Điều 4 — Đóng gói và vận chuyển")}),
     "hard"),
    ("giá niêm yết của sản phẩm là bao nhiêu?",
     frozenset({(_GIA, "Bảng giá")}),
     "easy"),

    # ══ LUẬT LAO ĐỘNG ════════════════════════════════════════════════════

    ("quy định về làm thêm giờ như thế nào?",
     frozenset({(_LAODONG, "Điều 107. Làm thêm giờ")}), "easy"),
    ("nghỉ hằng năm được bao nhiêu ngày?",
     frozenset({(_LAODONG, "Điều 113. Nghỉ hằng năm")}), "easy"),
    ("nghỉ lễ tết theo luật gồm những ngày nào?",
     frozenset({(_LAODONG, "Điều 112. Nghỉ lễ, tết")}), "easy"),
    ("trợ cấp thôi việc tính thế nào?",
     frozenset({(_LAODONG, "Điều 46. Trợ cấp thôi việc")}), "easy"),
    ("các hình thức xử lý kỷ luật lao động gồm những gì?",
     frozenset({(_LAODONG, "Điều 124. Hình thức xử lý kỷ luật lao động")}), "easy"),
    ("công ty muốn cho nhân viên nghỉ việc thì cần căn cứ gì?",
     frozenset({(_LAODONG, "Điều 36. Quyền đơn phương chấm dứt hợp đồng lao động của người sử dụng lao động")}),
     "hard"),
    ("làm ca đêm thì được trả thêm bao nhiêu phần trăm?",
     frozenset({(_LAODONG, "Điều 98. Tiền lương làm thêm giờ, làm việc vào ban đêm")}),
     "hard"),
    ("bảo hiểm xã hội bắt buộc thì người lao động đóng bao nhiêu?",
     frozenset({(_BHXH, "Điều 33. Mức đóng, phương thức và thời hạn đóng bảo hiểm xã hội bắt buộc của người lao động")}),
     "hard"),

    # ══ LUẬT THƯƠNG MẠI ══════════════════════════════════════════════════

    ("nghĩa vụ bảo hành hàng hoá của bên bán là gì?",
     frozenset({(_THUONGMAI, "Điều 49. Nghĩa vụ bảo hành hàng hoá")}), "easy"),
    ("thời hạn giao hàng trong hợp đồng thương mại quy định ra sao?",
     frozenset({(_THUONGMAI, "Điều 37. Thời hạn giao hàng")}), "easy"),
    ("bồi thường thiệt hại trong thương mại được quy định thế nào?",
     frozenset({(_THUONGMAI, "Điều 302. Bồi thường thiệt hại")}), "easy"),
    ("bên mua chưa trả tiền đúng hẹn thì luật thương mại nói gì?",
     frozenset({(_THUONGMAI, "Điều 55. Thời hạn thanh toán")}), "hard"),

    # ══ BỘ LUẬT DÂN SỰ ═══════════════════════════════════════════════════

    ("giao dịch dân sự có hiệu lực khi nào?",
     frozenset({(_DANSSU, "Điều 117. Điều kiện có hiệu lực của giao dịch dân sự")}), "easy"),
    ("giao dịch dân sự vô hiệu do giả tạo được hiểu thế nào?",
     frozenset({(_DANSSU, "Điều 124. Giao dịch dân sự vô hiệu do giả tạo")}), "easy"),
    ("hai bên ký hợp đồng giả để che giấu giao dịch khác thì hợp đồng đó ra sao?",
     frozenset({(_DANSSU, "Điều 124. Giao dịch dân sự vô hiệu do giả tạo")}), "hard"),
    ("một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?",
     frozenset({(_DANSSU, "Điều 428. Đơn phương chấm dứt thực hiện hợp đồng")}), "hard"),

    # ══ LUẬT DOANH NGHIỆP ════════════════════════════════════════════════

    ("người đại diện theo pháp luật của doanh nghiệp là ai?",
     frozenset({(_DOANHNGHIEP, "Điều 12. Người đại diện theo pháp luật của doanh nghiệp")}), "easy"),
    ("điều lệ công ty phải có những nội dung gì?",
     frozenset({(_DOANHNGHIEP, "Điều 24. Điều lệ công ty")}), "easy"),
    ("công ty cổ phần được định nghĩa thế nào?",
     frozenset({(_DOANHNGHIEP, "Điều 111. Công ty cổ phần")}), "easy"),
    ("ai là người được ký hợp đồng thay mặt cho công ty?",
     frozenset({(_DOANHNGHIEP, "Điều 12. Người đại diện theo pháp luật của doanh nghiệp")}), "hard"),

    # ══ QUẢN LÝ THUẾ ═════════════════════════════════════════════════════

    ("thời hạn nộp hồ sơ khai thuế là khi nào?",
     frozenset({(_QUANLYTHUE, "Điều 44. Thời hạn nộp hồ sơ khai thuế")}), "easy"),
    ("trách nhiệm của người nộp thuế gồm những gì?",
     frozenset({(_QUANLYTHUE, "Điều 17. Trách nhiệm của người nộp thuế")}), "easy"),
    ("nộp thuế trễ thì bị tính tiền phạt ra sao?",
     frozenset({(_QUANLYTHUE, "Điều 59. Xử lý đối với việc chậm nộp tiền thuế")}), "hard"),

    # ══ THUẾ GTGT ════════════════════════════════════════════════════════

    ("thuế suất thuế giá trị gia tăng là bao nhiêu?",
     frozenset({(_GTGT, "Điều 9. Thuế suất")}), "easy"),
    ("đối tượng không chịu thuế giá trị gia tăng gồm những gì?",
     frozenset({(_GTGT, "Điều 5. Đối tượng không chịu thuế")}), "easy"),
    ("khấu trừ thuế giá trị gia tăng đầu vào thế nào?",
     frozenset({(_GTGT, "Điều 14. Khấu trừ thuế giá trị gia tăng đầu vào")}), "easy"),
    ("khi nào thì xác định được thời điểm tính thuế GTGT?",
     frozenset({(_GTGT, "Điều 8. Thời điểm xác định thuế giá trị gia tăng")}), "hard"),

    # ══ THUẾ XUẤT NHẬP KHẨU ══════════════════════════════════════════════

    ("trường hợp nào được miễn thuế xuất nhập khẩu?",
     frozenset({(_XNK, "Điều 16. Miễn thuế")}), "easy"),
    ("thuế chống bán phá giá được áp dụng khi nào?",
     frozenset({(_XNK, "Điều 12. Thuế chống bán phá giá")}), "easy"),
    ("hạn ngạch thuế quan áp dụng cho hàng nhập khẩu ra sao?",
     frozenset({(_XNK, "Điều 7. Thuế đối với hàng hóa nhập khẩu áp dụng hạn ngạch thuế quan")}),
     "easy"),

    # ══ ĐẦU TƯ ═══════════════════════════════════════════════════════════

    ("ngành nghề nào được ưu đãi đầu tư?",
     frozenset({(_DAUTU, "Điều 15. Ngành, nghề ưu đãi đầu tư và địa bàn ưu đãi đầu tư")}), "easy"),
    ("dự án nào phải xin chấp thuận chủ trương đầu tư?",
     frozenset({(_DAUTU, "Điều 24. Dự án thuộc diện chấp thuận chủ trương đầu tư")}), "easy"),
    ("nhà đầu tư nước ngoài muốn góp vốn mua cổ phần thì theo hình thức nào?",
     frozenset({(_DAUTU, "Điều 21. Đầu tư theo hình thức góp vốn, mua cổ phần, mua phần vốn góp")}),
     "hard"),

    # ══ BẪY — từ khoá gợi ý SAI văn bản ══════════════════════════════════
    # Chín PDF luật đều mở đầu bằng cùng cấu trúc và dùng chung rất nhiều
    # thuật ngữ ("thuế suất", "thời hạn nộp thuế", "phạt vi phạm", "hoàn
    # thuế", "đơn phương chấm dứt"). Không có hạng này thì bộ đo không bao
    # giờ thấy lỗi trúng-nhầm-văn-bản.

    ("căn cứ tính thuế với hàng nhập khẩu theo tỷ lệ phần trăm là gì?",
     # "thuế suất"/"căn cứ tính thuế" kéo mạnh về luat-thuegtgt (Điều 6, Điều 9)
     frozenset({(_XNK, "Điều 5. Căn cứ tính thuế xuất khẩu, thuế nhập khẩu đối với hàng hóa áp dụng phương pháp tính thuế theo tỷ lệ phần trăm")}),
     "trap"),
    ("thời hạn nộp thuế đối với hàng hoá xuất khẩu, nhập khẩu?",
     # luat-quanlythue cũng có đúng tiêu đề "Điều 55. Thời hạn nộp thuế"
     frozenset({(_XNK, "Điều 9. Thời hạn nộp thuế")}),
     "trap"),
    ("hoàn thuế xuất nhập khẩu áp dụng trong trường hợp nào?",
     # luat-thuegtgt có "Điều 15. Hoàn thuế giá trị gia tăng"
     frozenset({(_XNK, "Điều 19. Hoàn thuế")}),
     "trap"),
    ("mức phạt vi phạm hợp đồng thương mại tối đa là bao nhiêu?",
     # boluat-danssu có "Điều 418. Thỏa thuận phạt vi phạm"
     frozenset({(_THUONGMAI, "Điều 301. Mức phạt vi phạm")}),
     "trap"),
    ("thời hiệu khởi kiện tranh chấp hợp đồng là bao lâu?",
     # "hợp đồng"/"tranh chấp" kéo về boluat-thuongmai; nhãn đúng ở dân sự
     frozenset({(_DANSSU, "Điều 429. Thời hiệu khởi kiện về hợp đồng")}),
     "trap"),
    ("người lao động muốn nghỉ việc thì phải báo trước bao nhiêu ngày?",
     # Điều 36 (phía NSDLĐ) có tiêu đề gần như y hệt Điều 35 (phía NLĐ)
     frozenset({(_LAODONG, "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động")}),
     "trap"),
    ("thoả thuận phạt vi phạm trong hợp đồng dân sự được quy định ở đâu?",
     # ngược chiều ca trên: lần này nhãn đúng LÀ dân sự, không phải thương mại
     frozenset({(_DANSSU, "Điều 418. Thỏa thuận phạt vi phạm")}),
     "trap"),
    ("hàng hoá nhập khẩu có thuộc đối tượng chịu thuế giá trị gia tăng không?",
     # "nhập khẩu" kéo mạnh về luat-thuexuatnhapkhau; nhãn đúng ở luật GTGT
     frozenset({(_GTGT, "Điều 3. Đối tượng chịu thuế")}),
     "trap"),
]
