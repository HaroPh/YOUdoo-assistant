# backend/src/agents/erp_grounding.py
"""ERP answer-grounding verify (agents layer) — mirror synthesis.py's
verify_citations nhưng cho dữ liệu ERP thay vì chunk tài liệu. Không có
khái niệm 'footer trích dẫn' để lọc chọn lọc; khi phát hiện bịa, thay
TOÀN BỘ câu trả lời (spec 2026-07-24-erp-guardrails)."""
import logging

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

ERP_GROUNDING_VERIFY_PROMPT = """Bạn kiểm tra xem CÂU TRẢ LỜI có số liệu (ngày tháng, con số, trạng thái) nào MÂU THUẪN với DỮ LIỆU THẬT hay không — KHÔNG phải kiểm tra mọi chữ trong câu trả lời có xuất hiện y hệt trong dữ liệu hay không.

Câu trả lời có thể tham khảo thêm nguồn khác ngoài DỮ LIỆU THẬT (vd tài liệu chính sách, quy định) — đó là BÌNH THƯỜNG, không tính là mâu thuẫn.
Nếu câu trả lời nói "không tìm thấy" / "không có dữ liệu" và DỮ LIỆU THẬT cũng cho thấy không có kết quả (rỗng, count=0, lỗi không tìm thấy), đó KHÔNG phải mâu thuẫn — trả lời CÓ.

CHỈ trả lời KHÔNG khi có số liệu cụ thể (ngày, số, trạng thái) trong câu trả lời TRÁI NGƯỢC với giá trị THẬT tương ứng trong dữ liệu (vd câu trả lời nêu ngày/số khác hẳn với ngày/số thật của cùng bản ghi).

Nếu không phát hiện mâu thuẫn nào, trả lời CÓ.

CHỈ trả lời CÓ hoặc KHÔNG, không giải thích thêm. /no_think"""

ERP_GROUNDING_FALLBACK_MSG = (
    "Xin lỗi, tôi không chắc chắn về độ chính xác của câu trả lời này. "
    "Vui lòng kiểm tra lại trực tiếp trên hệ thống hoặc hỏi lại cụ thể hơn."
)


async def verify_erp_grounding(answer: str, tool_outputs: list[str], llm) -> str:
    """1 lệnh gọi LLM so answer với đúng JSON tool đã trả về turn này.
    Fail-open toàn phần (lỗi/timeout → giữ nguyên answer, giống
    verify_citations round 2). tool_outputs rỗng (không tool nào được gọi)
    → trả nguyên answer, không gọi LLM."""
    if not tool_outputs:
        return answer
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=ERP_GROUNDING_VERIFY_PROMPT),
            HumanMessage(content=(
                f"CÂU TRẢ LỜI:\n{answer}\n\nDỮ LIỆU THẬT (JSON từ hệ thống):\n"
                + "\n".join(tool_outputs))),
        ])
        verdict = (resp.content or "").strip().upper()
        if verdict.startswith("KHÔNG") or verdict.startswith("KHONG"):
            return ERP_GROUNDING_FALLBACK_MSG
        return answer
    except Exception:
        # Fail-open GIỮ NGUYÊN (chặn câu trả lời tốt vì hạ tầng lỗi thì tệ
        # hơn), nhưng nay NÓI RA. Trước 2026-08-22 nhánh này nuốt lỗi hoàn
        # toàn, nên cổng chống bịa số liệu ERP có thể đã tắt hàng loạt lượt mà
        # không để lại một dòng nào — và nó tắt đúng lúc cạn hạn mức, tức đúng
        # lúc model trả lời đang yếu nhất (kiểm toán 2026-08-22, FM-2).
        #
        # KHÔNG có ghi chú ra người dùng như phía trích dẫn: ở đây không có
        # footer nào hứa hẹn "đã kiểm chứng", nên không có lời hứa nào để rút
        # lại. Thứ thiếu là khả năng QUAN SÁT, và đó là thứ được vá.
        logger.warning(
            "verify_erp_grounding HỎNG — trả nguyên câu trả lời CHƯA đối "
            "chiếu với dữ liệu ERP. Cổng chống bịa đã tắt ở lượt này.",
            exc_info=True)
        return answer
