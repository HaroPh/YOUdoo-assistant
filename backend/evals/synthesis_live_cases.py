# backend/evals/synthesis_live_cases.py
"""Bộ ca gây áp lực cho synthesis_live — spec 2026-08-19 §4.

CẤU TRÚC: (question, kind, expect, expect_source)
  kind:
    deep_chunk   — đáp án nằm ở chunk thứ 2+ của một Điều dài. Bắt mọi thay
                   đổi ở compress()/TOP_K làm mất phần sau của đúng điều luật.
                   55% chunk của corpus nằm trong mục nhiều-chunk.
    distractor   — có điều luật gần-đúng trong pool mang con số KHÁC. Bắt lỗi
                   "trả lời đúng số của nhầm văn bản" (spec P0 §11.1).
    insufficient — ngoài corpus hoàn toàn. Bắt bịa, và bắt guard hỏng.
  expect: chuỗi phải xuất hiện NGUYÊN VĂN, hoặc tuple nhiều phương án ĐÃ QUAN
          SÁT THẬT (cơ chế của _grounded_match — không có logic mờ nào).
  expect_source: BASENAME tệp, đúng thứ build_citations in ra.

MỌI CHUỖI expect DƯỚI ĐÂY ĐÃ ĐỐI CHIẾU VỚI rag_chunks NGÀY 2026-08-19 bằng
truy vấn thật: xác nhận có mặt, xác nhận chỉ nằm ở một tệp, và với ca
deep_chunk là xác nhận chunk chứa nó KHÔNG phải chunk đầu của mục.
test_synthesis_live_cases.py chốt lại cả ba điều đó mỗi lần chạy.

KHÔNG dùng các "mục" rác do parse_pdf sinh ra (quốc hiệu, tên cơ quan, mảnh
câu tham chiếu chéo "Điều 11 của Luật này quy định.") — chúng sẽ biến mất khi
P3 chạy.
"""

_LAODONG = "boluat-laodong.pdf"
_DANSSU = "boluat-danssu.pdf"
_THUONGMAI = "boluat-thuongmai.pdf"
_DOANHNGHIEP = "luat-doanhnghiep.pdf"
_QUANLYTHUE = "luat-quanlythue.pdf"
_BHXH = "luat-baohiemxahoi.pdf"
_DAUTU = "luat-dautu.pdf"
_XNK = "luat-thuexuatnhapkhau.pdf"
_GTGT = "luat-thuegtgt.pdf"

SYNTHESIS_LIVE_CASES: list[tuple[str, str, object, str]] = [

    # ══ deep_chunk — đáp án nằm ở chunk thứ 2+ của mục ═══════════════════
    # Mỗi ca ghi kèm (idx đáp án / idx chunk đầu của mục) đo được 2026-08-19.

    # 193/191. Chunk đầu nói "12 ngày"/"14 ngày" phép năm — con số hoàn toàn
    # khác, nên trả lời đúng chuỗi này chứng minh đã đọc tới chunk thứ ba.
    ("nghỉ phép hằng năm mà đi đường mất nhiều ngày thì có được tính thêm không?",
     "deep_chunk", "từ ngày thứ 03 trở đi được tính thêm thời gian đi đường", _LAODONG),
    # 318/317
    ("cổ tức phải được thanh toán trong bao lâu sau đại hội cổ đông thường niên?",
     "deep_chunk", "thanh toán đầy đủ trong thời hạn 06 tháng kể từ ngày kết thúc họp",
     _DOANHNGHIEP),
    # 341/340
    ("họp đại hội cổ đông lần thứ ba thì thông báo mời họp gửi trong bao lâu?",
     "deep_chunk", "thông báo mời họp lần thứ ba phải được gửi trong thời hạn 20 ngày",
     _DOANHNGHIEP),
    # 271/269
    ("cổ đông phải nắm bao nhiêu phần trăm cổ phần mới được xem sổ biên bản hội đồng quản trị?",
     "deep_chunk", "sở hữu từ 05% tổng số cổ phần phổ thông trở lên", _DOANHNGHIEP),
    # 252/251
    ("báo cáo tài chính đã kiểm toán phải công bố trong thời hạn bao lâu?",
     "deep_chunk", "kiểm toán độc lập trong thời hạn 150 ngày kể từ ngày kết thúc năm tài chính",
     _DOANHNGHIEP),
    # 105/104
    ("dự án đầu tư chậm tiến độ bao lâu thì bị chấm dứt hoạt động?",
     "deep_chunk", "Sau 24 tháng kể từ thời điểm kết thúc tiến độ", _DAUTU),
    # 50/49
    ("hàng tái xuất khẩu thì số thuế nhập khẩu được hoàn lại tính trên cơ sở nào?",
     "deep_chunk", "trị giá sử dụng còn lại của hàng hóa khi tái xuất khẩu", _XNK),
    # 20/19
    ("doanh nghiệp được áp dụng chế độ ưu tiên thì nộp thuế trong tháng chậm nhất ngày nào?",
     "deep_chunk", "chậm nhất vào ngày thứ mười", _XNK),
    # 34/33
    ("hàng hóa xuất khẩu chịu mức thuế giá trị gia tăng bao nhiêu?",
     "deep_chunk", "Mức thuế suất 0% áp dụng đối với hàng hóa", _GTGT),
    # 91/90. Chunk đầu nói "8%" (nhóm đối tượng khác) — con số cạnh tranh nằm
    # ngay trong CÙNG một mục, nên ca này còn bắt cả lỗi lấy nhầm khoản.
    ("người tham gia theo điểm g đóng bảo hiểm xã hội hằng tháng bao nhiêu phần trăm tiền lương?",
     "deep_chunk", "Mức đóng hằng tháng bằng 22% tiền lương làm căn cứ đóng bảo hiểm xã hội bắt buộc",
     _BHXH),

    # ══ distractor — từ khoá gợi ý SAI văn bản ═══════════════════════════
    # Mỗi ca ghi kèm văn bản cạnh tranh mà từ khoá kéo về.

    # cạnh tranh: boluat-danssu "Điều 418. Thỏa thuận phạt vi phạm"
    ("mức phạt vi phạm hợp đồng thương mại tối đa bao nhiêu phần trăm?",
     "distractor", "không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm", _THUONGMAI),
    # cạnh tranh: boluat-thuongmai "Điều 301. Mức phạt vi phạm" (ngược chiều ca trên)
    ("bộ luật dân sự quy định mức phạt vi phạm hợp đồng thế nào?",
     "distractor", "Mức phạt vi phạm do các bên thỏa thuận, trừ trường hợp luật liên quan có quy định khác",
     _DANSSU),
    # cạnh tranh: luat-quanlythue "Điều 55. Thời hạn nộp thuế" (TRÙNG TÊN MỤC)
    ("hàng nhập khẩu phải nộp thuế vào thời điểm nào?",
     "distractor", "phải nộp thuế trước khi thông quan hoặc giải phóng hàng hóa", _XNK),
    # cạnh tranh: luat-thuexuatnhapkhau "Điều 9. Thời hạn nộp thuế" (ngược chiều)
    ("người nộp thuế tự tính thuế thì hạn nộp thuế là khi nào?",
     "distractor", "thời hạn nộp thuế chậm nhất là ngày cuối cùng của thời hạn nộp hồ sơ khai thuế",
     _QUANLYTHUE),
    # cạnh tranh: "Điều 36. Quyền đơn phương chấm dứt HĐLĐ của NGƯỜI SỬ DỤNG
    # lao động" — tiêu đề gần như y hệt, chỉ khác chủ thể. Đây đúng ca mà
    # spike 2026-08-19 §11.1 thấy cross-encoder chọn nhầm.
    ("người lao động nghỉ việc theo hợp đồng không xác định thời hạn phải báo trước bao nhiêu ngày?",
     "distractor", "Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn",
     _LAODONG),
    # cạnh tranh: luat-thuexuatnhapkhau "Điều 19. Hoàn thuế"
    ("hoàn thuế giá trị gia tăng cho hàng xuất khẩu áp dụng từ mức nào?",
     "distractor", "chưa được khấu trừ hết từ 300 triệu đồng trở lên", _GTGT),

    # ══ insufficient — ngoài corpus hoàn toàn ════════════════════════════
    ("giá cổ phiếu công ty hôm nay là bao nhiêu?", "insufficient", "", ""),
    ("thủ đô nước Pháp là thành phố nào?", "insufficient", "", ""),
    ("dự báo thời tiết Hà Nội tuần sau thế nào?", "insufficient", "", ""),
    ("giám đốc công ty tên gì?", "insufficient", "", ""),
]
