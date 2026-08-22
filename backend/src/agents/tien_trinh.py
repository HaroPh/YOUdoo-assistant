"""Báo tiến trình từng chặng cho lượt streaming (mục 21).

Module RIÊNG chứ không nằm trong erp_agent.py: `nodes.py` cũng cần
`bao_tien_trinh()` để báo các chặng CON, mà erp_agent → graph → nodes là một
vòng nhập nếu nodes nhập ngược lại erp_agent.

KHÔNG có gì ở đây được phép ném: một thanh tiến trình không được là nguồn sự
cố cho lượt chat.
"""
import asyncio
from contextvars import ContextVar

from langchain_core.callbacks import AsyncCallbackHandler


# ── Báo tiến trình từng chặng (mục 21) ──────────────────────────────────────
#
# VÌ SAO KHÔNG phải streaming token: đo 2026-08-22 trên lượt ERP thật, tổng
# 9,95s gồm ~4 lời gọi LLM NỐI TIẾP (router ý định 1,72s · erp_read quyết định
# tool 1,80s · erp_read sinh câu 1,8s · verify_erp_grounding 1,36s), còn câu
# trả lời cuối chỉ **74 ký tự**. Streaming token sẽ cho người dùng 8–9 giây
# trắng màn hình rồi đổ ra 74 ký tự — gần như không cải thiện gì. Cái người
# dùng thiếu là BIẾT HỆ ĐANG LÀM GÌ, không phải chữ hiện sớm hơn.
#
# Nhãn giữ ở mức "hệ đang làm gì", KHÔNG lộ tên nút/tên tool ra người dùng —
# cùng nguyên tắc với cổng xác nhận ghi (hiện args, không hiện tên tool).
NHAN_TIEN_TRINH: dict[str, str] = {
    "intent_router":        "Đang xác định yêu cầu…",
    "erp_read":             "Đang tra dữ liệu trên hệ thống…",
    "erp_write_planner":    "Đang chuẩn bị thao tác…",
    "erp_write_executor":   "Đang thực hiện thao tác…",
    "rag":                  "Đang tìm trong tài liệu…",
    "gather_docs":          "Đang tìm trong tài liệu…",
    "gather_erp":           "Đang tra dữ liệu trên hệ thống…",
    "fuse_answer":          "Đang tổng hợp câu trả lời…",
    "clarify_depth":        "Đang xác định yêu cầu…",
    "write_continuation":   "Đang chuẩn bị thao tác…",
    "agentic_context_sync": "Đang cập nhật ngữ cảnh…",
}

# Nhãn cho các chặng CON, nút tự phát qua bao_tien_trinh().
NHAN_DOC_TAI_LIEU   = "Đang đọc tài liệu tìm được…"
NHAN_KIEM_CHUNG     = "Đang kiểm chứng số liệu…"
NHAN_GOI_TOOL       = "Đang tra dữ liệu trên hệ thống…"
NHAN_SOAN_CAU       = "Đang soạn câu trả lời…"

# Hàng đợi tiến trình của lượt hiện tại. None = không ai lắng nghe (lượt
# không streaming, script nội bộ, test) và khi đó handler không được gắn.
HANG_TIEN_TRINH: ContextVar["asyncio.Queue | None"] = ContextVar(
    "hang_tien_trinh", default=None)


def bao_tien_trinh(nhan: str) -> None:
    """Cho một NÚT tự báo chặng con của nó.

    Cần vì callback chỉ bắn ở ranh giới NÚT, mà chặng dài nhất nằm BÊN TRONG
    một nút: đo 2026-08-22 trên lượt ERP, panel tiến trình đứng im từ 1,69s tới
    9,67s vì `erp_read` làm cả LLM → tool → LLM → kiểm chứng trong một nút.

    Không làm gì khi không ai lắng nghe, và không bao giờ ném.
    """
    try:
        hang = HANG_TIEN_TRINH.get()
        if hang is not None:
            hang.put_nowait(nhan)
    except Exception:                                       # noqa: BLE001
        pass


class BaoTienTrinh(AsyncCallbackHandler):
    """Đẩy nhãn tiến trình vào hàng đợi mỗi khi graph bước sang nút mới.

    Dùng callback chứ không đổi `ainvoke` thành `astream`: ba chỗ gọi graph
    trong `_chat_inner` có cả đường `Command(resume=…)` của interrupt, và đổi
    kiểu gọi ở đó là đổi hành vi của cổng xác nhận ghi — cái giá quá lớn cho
    một tính năng hiển thị.

    Lọc theo tag `graph:step:` vì `on_chain_start` cũng bắn cho chain ngoài
    cùng (name='LangGraph') và cho mọi chain con của LangChain bên trong nút.
    Đo 2026-08-22: chỉ nút graph mới mang tag đó.

    KHÔNG BAO GIỜ ném: một thanh tiến trình không được làm hỏng lượt chat.
    """

    async def on_chain_start(self, serialized, inputs, **kwargs) -> None:
        try:
            hang = HANG_TIEN_TRINH.get()
            if hang is None:
                return
            tags = kwargs.get("tags") or []
            if not any(str(t).startswith("graph:step:") for t in tags):
                return
            ten = (kwargs.get("metadata") or {}).get("langgraph_node")                 or kwargs.get("name")
            nhan = NHAN_TIEN_TRINH.get(ten)
            if nhan:
                hang.put_nowait(nhan)
        except Exception:                                   # noqa: BLE001
            pass

    async def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        """Lời gọi tool nằm BÊN TRONG nút nên callback nút không thấy nó.

        Không lộ tên tool ra người dùng — cùng nguyên tắc với cổng xác nhận
        ghi (hiện args, KHÔNG hiện tên tool).
        """
        bao_tien_trinh(NHAN_GOI_TOOL)

    async def on_tool_end(self, output, **kwargs) -> None:
        """Tách thời gian TRA dữ liệu khỏi thời gian SOẠN câu trả lời.

        Không có mốc này thì hai chặng dính làm một khoảng im lặng ~7s và
        không ai biết hệ đang chờ Odoo hay đang chờ model.
        """
        bao_tien_trinh(NHAN_SOAN_CAU)
