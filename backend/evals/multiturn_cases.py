# backend/evals/multiturn_cases.py
"""Bộ ca hội thoại HAI LƯỢT — đo giải chiếu ở câu hỏi nối tiếp.

VÌ SAO TỒN TẠI. `rag_node` lấy DUY NHẤT tin nhắn người dùng cuối cùng
(`query = last_human.content`) cho cả truy xuất lẫn sinh; lịch sử hội thoại bị
bỏ hoàn toàn. Cả 12 bộ eval hiện có đều một-lượt, nên chỗ này chưa bao giờ
được đo.

Spike 2026-08-20 trên 6 ca dựng tay: `recall@6` tụt **6/6 → 3/6** khi chỉ dùng
câu rút gọn. Câu càng ít nội dung càng hỏng nặng — "thế còn hàng giảm giá?"
vẫn hạng 1, còn "trong bao lâu?" biến mất khỏi cả pool 20.

CẤU TRÚC: (prev_turn, question, expected_labels, kind)
  prev_turn : câu người dùng hỏi ở lượt TRƯỚC
  question  : câu lượt này — thứ production thật sự đưa vào retrieve()
  kind:
    elliptical  — câu rút gọn, KHÔNG tự đứng được. Truyền ngữ cảnh PHẢI giúp.
    independent — câu tự đứng được, và lượt trước nói chuyện KHÁC HẲN.
                  Truyền ngữ cảnh KHÔNG ĐƯỢC làm tệ đi.

`independent` là nửa bắt buộc của bộ đo, không phải phần thêm cho đẹp: gộp ứng
viên của hai truy vấn vào cùng pool 20 chính là cơ chế đã làm hỏng việc hồi
sinh chân sparse (spec P0 §13) — sparse sống lại chỉ chiếm chỗ của dense.
Không có nhóm `independent` thì bộ này chỉ đo mặt LỢI và mù với mặt HẠI.

MỌI NHÃN đều lấy nguyên từ `retrieval_cases.py`, tức đã qua test hợp đồng đối
chiếu `rag_chunks`.
"""
from typing import NamedTuple


class MultiturnCase(NamedTuple):
    prev_turn: str
    question: str
    expect: frozenset          # {(basename tệp, section_path)}
    kind: str                  # elliptical | independent


_POLICY = "policy.docx"
_SLA = "sla.docx"
_DISCOUNT = "discount_policy.docx"
_SOP = "sop.docx"
_SALES = "sales_process.docx"
_OUTBOUND = "warehouse_outbound.docx"
_LAODONG = "boluat-laodong.pdf"
_THUONGMAI = "boluat-thuongmai.pdf"
_DANSSU = "boluat-danssu.pdf"
_DOANHNGHIEP = "luat-doanhnghiep.pdf"
_XNK = "luat-thuexuatnhapkhau.pdf"
_BHXH = "luat-baohiemxahoi.pdf"

MULTITURN_CASES: list[MultiturnCase] = [

    # ══ elliptical — câu rút gọn, phụ thuộc lượt trước ═══════════════════
    # Mức rút gọn cố ý trải rộng: từ "còn giữ được một từ khoá" đến "toàn hư
    # từ". Spike cho thấy đó chính là biến quyết định mức hỏng.

    MultiturnCase("chính sách đổi trả hàng như thế nào?",
                  "thế còn hàng giảm giá?",
                  frozenset({(_POLICY, "Chính sách hoàn hàng › Mục 2 — Ngoại lệ không được hoàn trả")}),
                  "elliptical"),
    MultiturnCase("chính sách hoàn hàng quy định những gì?",
                  "mất bao lâu thì nhận được tiền?",
                  frozenset({(_POLICY, "Chính sách hoàn hàng › Mục 4 — Hoàn tiền")}),
                  "elliptical"),
    MultiturnCase("nghỉ hằng năm được bao nhiêu ngày?",
                  "còn đi đường thì sao?",
                  frozenset({(_LAODONG, "Điều 113. Nghỉ hằng năm")}),
                  "elliptical"),
    MultiturnCase("làm thêm giờ được trả lương thế nào?",
                  "làm ban đêm thì thêm bao nhiêu?",
                  frozenset({(_LAODONG, "Điều 98. Tiền lương làm thêm giờ, làm việc vào ban đêm")}),
                  "elliptical"),
    MultiturnCase("thuế xuất nhập khẩu quy định thế nào?",
                  "trường hợp nào được miễn?",
                  frozenset({(_XNK, "Điều 16. Miễn thuế")}),
                  "elliptical"),
    MultiturnCase("phạt vi phạm hợp đồng thương mại quy định thế nào?",
                  "tối đa bao nhiêu phần trăm?",
                  frozenset({(_THUONGMAI, "Điều 301. Mức phạt vi phạm")}),
                  "elliptical"),
    # Ca KHẮC NGHIỆT NHẤT: câu hỏi không còn một từ nội dung nào. Spike đo
    # được nó biến mất khỏi cả pool 20 khi thiếu ngữ cảnh.
    MultiturnCase("công ty cổ phần trả cổ tức như thế nào?",
                  "trong bao lâu?",
                  frozenset({(_DOANHNGHIEP, "Điều 135. Trả cổ tức")}),
                  "elliptical"),
    MultiturnCase("nhà cung cấp giao hàng trễ thì sao?",
                  "phạt bao nhiêu?",
                  frozenset({(_SLA, "Thỏa thuận mức dịch vụ nhà cung cấp › Điều 5 — Phạt chậm trễ giao hàng")}),
                  "elliptical"),

    # ══ independent — lượt trước KHÁC HẲN chủ đề ═════════════════════════
    # Nửa đo mặt HẠI. Câu lượt này tự đứng được; truyền lượt trước vào
    # aux_queries chỉ có thể làm nhiễu pool. Nếu nhãn đúng tụt hạng ở đây thì
    # cơ chế truyền ngữ cảnh đang trả giá, và cái giá đó phải đo được.

    MultiturnCase("giá niêm yết của sản phẩm là bao nhiêu?",
                  "các hình thức xử lý kỷ luật lao động gồm những gì?",
                  frozenset({(_LAODONG, "Điều 124. Hình thức xử lý kỷ luật lao động")}),
                  "independent"),
    MultiturnCase("quy trình nhập kho gồm những bước nào?",
                  "giao dịch dân sự có hiệu lực khi nào?",
                  frozenset({(_DANSSU, "Điều 117. Điều kiện có hiệu lực của giao dịch dân sự")}),
                  "independent"),
    MultiturnCase("nghỉ lễ tết theo luật gồm những ngày nào?",
                  "nghĩa vụ bảo hành hàng hoá của bên bán là gì?",
                  frozenset({(_THUONGMAI, "Điều 49. Nghĩa vụ bảo hành hàng hoá")}),
                  "independent"),
    MultiturnCase("bồi thường thiệt hại trong thương mại được quy định thế nào?",
                  "bảo hiểm xã hội bắt buộc thì người lao động đóng bao nhiêu?",
                  frozenset({(_BHXH, "Điều 33. Mức đóng, phương thức và thời hạn đóng bảo hiểm xã hội bắt buộc của người lao động")}),
                  "independent"),
]
