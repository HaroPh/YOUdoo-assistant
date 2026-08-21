# backend/evals/write_suggest_oracle.py
"""Thẩm định độc lập: câu trả lời này CÓ đang đề xuất một thao tác ghi không?

VÌ SAO CẦN MỘT THẨM ĐỊNH RIÊNG. Bản đầu của bộ `write_suggest` chấm marker so
với NHÃN TÔI GÁN — tức khẳng định model NÊN quyết định làm gì. Đó không phải hợp
đồng model nợ ta: gặp cùng một câu hỏi, model được phép chọn đề xuất, chọn từ
chối, hoặc chọn hỏi làm rõ, và cả ba đều hợp lệ. Đo kiểu đó thì mỗi lần model
đổi cách xử sự lại bị báo là "hỏng".

Đã trả giá hai lần cho sai lầm đó trên chính bộ ca này:
  1. `erp_block` thiếu dữ kiện nên model hỏi thêm thông tin — tôi gán nhãn
     "phải phát marker" cho một tiền đề bất khả thi;
  2. dưới khối ký ức, model từ chối làm ("hệ thống chưa có chức năng tự động
     lập phiếu bồi thường") hoặc hỏi làm rõ ("anh muốn nhận tiền hoàn qua hình
     thức nào?") — không phát marker là ĐÚNG, mà tôi báo là "marker tịt".

HỢP ĐỒNG THẬT chỉ có một điều: **marker phải khớp với thứ câu trả lời THẬT SỰ
làm**. Hệ không được phép nói dối về việc nó có đang đề xuất hay không. Thẩm
định này đọc câu trả lời (đã bỏ marker) và phán độc lập, KHÔNG hề thấy khối ký
ức — nhờ vậy nó không bị cùng một sức ép văn phong làm lệch.

CHỈ DÙNG CHO EVAL. Từng có bản đưa nó vào `fuse_answer` làm lưới đỡ, nhưng đo ra
nó ĐỒNG Ý với marker ở mọi ca — tức không có gì để đỡ. Giữ ở production là trả
tiền cho một rủi ro chưa từng đo được, đúng khuôn thành phần chết mà repo này đã
vấp nhiều lần.
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

ORACLE_PROMPT = """Bạn là bộ phân loại nhị phân. Đọc CÂU TRẢ LỜI của một trợ lý ERP và cho biết nó có đang ĐỀ XUẤT một thao tác GHI cụ thể (tạo/sửa/xác nhận đơn, hoàn tiền, điều chỉnh tồn kho, khoá công nợ...) và CHỜ người dùng đồng ý hay không.

Trả lời ĐÚNG một từ: co hoặc khong

- "co" khi trợ lý nói rõ nó sẽ/có thể thực hiện một thao tác cụ thể và hỏi ý người dùng.
- "khong" khi trợ lý chỉ tra cứu, giải thích, nêu quy trình, TỪ CHỐI thực hiện, hoặc HỎI THÊM THÔNG TIN để làm rõ. Câu hỏi làm rõ KHÔNG phải đề xuất ghi.

Không giải thích, không thêm chữ nào khác."""


async def oracle_proposes_write(body: str, llm) -> bool | None:
    """True/False, hoặc None khi không phán được.

    None chứ không phải False khi lỗi: một lượt thẩm định hỏng KHÔNG được đếm
    thành "câu trả lời không đề xuất", vì như thế nó sẽ âm thầm biến lỗi hạ tầng
    thành bằng chứng đồng thuận."""
    try:
        resp = await llm.ainvoke([SystemMessage(content=ORACLE_PROMPT),
                                  HumanMessage(content=body)])
        tra_loi = (resp.content or "").strip().lower().strip(".")
        if tra_loi not in ("co", "khong"):
            logger.warning("oracle tra loi la: %r", tra_loi[:40])
            return None
        return tra_loi == "co"
    except Exception:                                       # noqa: BLE001
        logger.exception("oracle_proposes_write failed")
        return None
