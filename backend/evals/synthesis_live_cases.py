# backend/evals/synthesis_live_cases.py
"""Bộ ca gây áp lực cho synthesis_live — spec 2026-08-19 §4.

VÌ SAO `expect` NGẮN. Bản đầu (2026-08-19) dùng chuỗi DÀI để thoả ràng buộc
"duy nhất một tệp". Lượt chạy thật đầu tiên cho fact_acc = 0,50 — và cả 8 ca
trượt đều là CÂU TRẢ LỜI ĐÚNG, chỉ khác vài hư từ: "được" → "sẽ được",
"kết thúc họp" → "kết thúc cuộc họp", "không quá 8%" → "không được vượt quá
8%". Chuỗi càng dài thì diễn đạt lại càng chắc chắn phá vỡ; hai yêu cầu
"duy nhất" và "bền với diễn đạt" chống nhau trong cùng một trường.

Tách hai mối lo: `citation_acc` lo "ĐÚNG VĂN BẢN" (footer phải nêu đúng tệp),
còn `expect` chỉ lo "ĐÚNG SỰ KIỆN" — dùng chuỗi ngắn nhất mang tính phân
biệt. Với ca `distractor`, sức phân biệt do trường `rival` gánh: expect phải
VẮNG MẶT trong mục cạnh tranh.

CẤU TRÚC: xem class Case bên dưới.
  kind:
    deep_chunk   — đáp án nằm ở chunk thứ 2+ của một Điều dài. Bắt mọi thay
                   đổi ở compress()/TOP_K làm mất phần sau của đúng điều luật.
                   55% chunk của corpus nằm trong mục nhiều-chunk.
    distractor   — có mục gần-đúng cạnh tranh. Bắt lỗi "trả lời đúng số của
                   nhầm văn bản" (spec P0 §11.1).
    insufficient — ngoài corpus hoàn toàn. Bắt bịa, và bắt guard hỏng.

MỌI CHUỖI expect DƯỚI ĐÂY ĐÃ ĐỐI CHIẾU VỚI rag_chunks NGÀY 2026-08-19 bằng
truy vấn thật. test_synthesis_live_cases.py chốt lại mỗi lần chạy.

MỘT CẶP ĐÃ BỊ LOẠI vì đo ra là không phân biệt được: "Điều 35 vs Điều 36"
(quyền đơn phương chấm dứt HĐLĐ, phía NLĐ và phía NSDLĐ) dùng CHUNG các con
số 03/12/30/36/45 — hỏi phía nào cũng ra "45 ngày", nên fact_acc không thể
bắt lỗi chọn nhầm điều. Thay bằng chiều ngược lại, dùng "05 ngày làm việc
liên tục" vốn CHỈ có ở Điều 36.

KHÔNG dùng các "mục" rác do parse_pdf sinh ra (quốc hiệu, tên cơ quan, mảnh
câu tham chiếu chéo "Điều 11 của Luật này quy định.") — chúng sẽ biến mất khi
P3 chạy.
"""
from typing import NamedTuple


class Case(NamedTuple):
    """Một ca. `section`/`rival` chỉ dùng cho test hợp đồng, không vào prompt."""
    question: str
    kind: str          # deep_chunk | distractor | insufficient
    expect: object     # str, hoặc tuple[str, ...] các phương án ĐÃ QUAN SÁT THẬT
    source: str        # basename tệp, đúng thứ build_citations in ra
    section: str = ""  # section_path chứa đáp án (rỗng với insufficient)
    rival: str = ""    # section_path cạnh tranh (chỉ ca distractor)


_LAODONG = "boluat-laodong.pdf"
_DANSSU = "boluat-danssu.pdf"
_THUONGMAI = "boluat-thuongmai.pdf"
_DOANHNGHIEP = "luat-doanhnghiep.pdf"
_QUANLYTHUE = "luat-quanlythue.pdf"
_BHXH = "luat-baohiemxahoi.pdf"
_DAUTU = "luat-dautu.pdf"
_XNK = "luat-thuexuatnhapkhau.pdf"
_GTGT = "luat-thuegtgt.pdf"

_D35 = "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động"
_D36 = ("Điều 36. Quyền đơn phương chấm dứt hợp đồng lao động của người sử "
        "dụng lao động")

SYNTHESIS_LIVE_CASES: list[Case] = [

    # ══ deep_chunk — đáp án nằm ở chunk thứ 2+ của mục ═══════════════════
    # Mỗi ca ghi kèm (idx chứa đáp án / idx chunk đầu của mục), đo 2026-08-19.

    # 193/191. Chunk đầu nói "12 ngày"/"14 ngày" phép năm — con số khác hẳn,
    # nên trả lời đúng chứng minh đã đọc tới chunk thứ ba.
    Case("nghỉ phép hằng năm mà đi đường mất nhiều ngày thì có được tính thêm không?",
         "deep_chunk", "ngày thứ 03", _LAODONG, "Điều 113. Nghỉ hằng năm"),
    # 318/317
    Case("cổ tức phải được thanh toán trong bao lâu sau đại hội cổ đông thường niên?",
         "deep_chunk", "06 tháng", _DOANHNGHIEP, "Điều 135. Trả cổ tức"),
    # 341/340
    Case("họp đại hội cổ đông lần thứ ba thì thông báo mời họp gửi trong bao lâu?",
         "deep_chunk", "20 ngày", _DOANHNGHIEP,
         "Điều 145. Điều kiện tiến hành họp Đại hội đồng cổ đông"),
    # 271/269
    Case("cổ đông phải nắm bao nhiêu phần trăm cổ phần mới được xem sổ biên bản hội đồng quản trị?",
         "deep_chunk", "05%", _DOANHNGHIEP, "Điều 115. Quyền của cổ đông phổ thông"),
    # 252/251
    Case("báo cáo tài chính đã kiểm toán phải công bố trong thời hạn bao lâu?",
         "deep_chunk", "150 ngày", _DOANHNGHIEP, "Điều 109. Công bố thông tin định kỳ"),
    # 105/104
    Case("dự án đầu tư chậm tiến độ bao lâu thì bị chấm dứt hoạt động?",
         "deep_chunk", "24 tháng", _DAUTU, "Điều 36. Chấm dứt hoạt động của dự án đầu tư"),
    # 50/49
    Case("hàng tái xuất khẩu thì số thuế nhập khẩu được hoàn lại tính trên cơ sở nào?",
         "deep_chunk", "trị giá sử dụng còn lại", _XNK, "Điều 19. Hoàn thuế"),
    # 20/19
    Case("doanh nghiệp được áp dụng chế độ ưu tiên thì nộp thuế trong tháng chậm nhất ngày nào?",
         "deep_chunk", "ngày thứ mười", _XNK, "Điều 9. Thời hạn nộp thuế"),
    # 34/33
    Case("hàng hóa xuất khẩu chịu mức thuế giá trị gia tăng bao nhiêu?",
         "deep_chunk", "thuế suất 0%", _GTGT, "Điều 9. Thuế suất"),
    # 91,93,94 / 90. Chunk đầu nói "8%" (nhóm đối tượng khác) — con số cạnh
    # tranh nằm ngay trong CÙNG một mục, nên ca này bắt cả lỗi lấy nhầm khoản.
    Case("người tham gia theo điểm g đóng bảo hiểm xã hội hằng tháng bao nhiêu phần trăm tiền lương?",
         "deep_chunk", "22%", _BHXH,
         "Điều 33. Mức đóng, phương thức và thời hạn đóng bảo hiểm xã hội "
         "bắt buộc của người lao động"),

    # ══ distractor — mục cạnh tranh mang nội dung khác ═══════════════════
    # `rival` là mục mà từ khoá kéo về; expect phải VẮNG MẶT ở đó.

    Case("mức phạt vi phạm hợp đồng thương mại tối đa bao nhiêu phần trăm?",
         "distractor", "8%", _THUONGMAI, "Điều 301. Mức phạt vi phạm",
         "Điều 418. Thỏa thuận phạt vi phạm"),
    Case("bộ luật dân sự quy định mức phạt vi phạm hợp đồng thế nào?",
         "distractor", "trừ trường hợp luật liên quan có quy định khác", _DANSSU,
         "Điều 418. Thỏa thuận phạt vi phạm", "Điều 301. Mức phạt vi phạm"),
    # Hai mục dưới TRÙNG TÊN nhau ở hai luật khác nhau — cặp bẫy mạnh nhất.
    Case("hàng nhập khẩu phải nộp thuế vào thời điểm nào?",
         "distractor", "trước khi thông quan", _XNK, "Điều 9. Thời hạn nộp thuế",
         "Điều 55. Thời hạn nộp thuế"),
    Case("người nộp thuế tự tính thuế thì hạn nộp thuế là khi nào?",
         "distractor", "ngày cuối cùng của thời hạn nộp hồ sơ khai thuế", _QUANLYTHUE,
         "Điều 55. Thời hạn nộp thuế", "Điều 9. Thời hạn nộp thuế"),
    # Cặp Điều 35/36 cùng một tệp nên citation_acc mù; sức phân biệt hoàn
    # toàn dựa vào expect chỉ có ở Điều 36.
    Case("nhân viên tự ý bỏ việc bao nhiêu ngày thì công ty được đơn phương chấm dứt hợp đồng?",
         "distractor", "05 ngày làm việc liên tục", _LAODONG, _D36, _D35),
    Case("hoàn thuế giá trị gia tăng cho hàng xuất khẩu áp dụng từ mức nào?",
         "distractor", "300 triệu đồng", _GTGT, "Điều 15. Hoàn thuế giá trị gia tăng",
         "Điều 19. Hoàn thuế"),

    # ══ insufficient — ngoài corpus hoàn toàn ════════════════════════════
    Case("giá cổ phiếu công ty hôm nay là bao nhiêu?", "insufficient", "", ""),
    Case("thủ đô nước Pháp là thành phố nào?", "insufficient", "", ""),
    Case("dự báo thời tiết Hà Nội tuần sau thế nào?", "insufficient", "", ""),
    Case("giám đốc công ty tên gì?", "insufficient", "", ""),
]
