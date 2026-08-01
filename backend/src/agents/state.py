# backend/src/agents/state.py
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ERPAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str | None            # "erp_read" | "erp_write" | "rag" | "unknown"
    sop: str | None               # tên skill SOP router ĐỀ CỬ cho lượt này
                                  # (hoặc None). TRANSIENT như pending_action —
                                  # intent_router ghi key này trên MỌI return
                                  # nên không sống sót sang lượt sau; quyết
                                  # định cuối vẫn do graph._route_by_intent
                                  # (phủ quyết tất định), không do trường này.
    pending_action: dict | None   # {"tool": str, "args": dict, "summary": str}
    confirmed: bool | None        # None=not asked, True=yes, False=no
    last_write: dict | None       # last write result handle:
                                  # {"tool", "ok", "ref", "model", "res_id", "state", "display"}
    working_context: dict | None  # bản ghi ĐƠN đang làm việc (cross-turn):
                                  # {"ref","model","display"}. PERSISTENT — NGƯỢC với
                                  # pending_action/confirmed/last_write (clear mọi path):
                                  # không node nào set None/clear key này; node chỉ THÊM
                                  # key khi có giá trị mới (omit-vs-None) → giá trị sống
                                  # xuyên lượt nhờ channel semantics của LangGraph.
    auto_chain: list | None       # hàng đợi tool user đã duyệt TRƯỚC qua 1 confirm
                                  # đầu chuỗi ("... rồi xác nhận luôn"). TRANSIENT
                                  # như pending_action/last_write — NGƯỢC với
                                  # working_context: erp_write_planner và
                                  # write_continuation ghi key này trên MỌI return;
                                  # không node nào khác đụng tới.
    doc_context: list[dict] | None  # chân TÀI LIỆU của fan-out `mixed`:
                                  # [dataclasses.asdict(chunk), ...]. JSON
                                  # THUẦN — Chunk là @dataclass(frozen=True),
                                  # nhét thẳng vào state là loại lỗi CHỈ hỏng
                                  # khi checkpointer Postgres thật chạy (bài
                                  # học SP-1C2). TRANSIENT, dọn ở HAI chỗ với
                                  # HAI lý do: node `mixed` xoá lúc VÀO là lớp
                                  # chịu lực chống dữ liệu ôi qua lượt (channel
                                  # semantics của LangGraph giữ giá trị khi node
                                  # bỏ qua key); `fuse_answer` xoá lúc RA là vệ
                                  # sinh (lượt erp_read sau không vác theo cả
                                  # đống chunk trong checkpoint và trace).
    erp_facts: str | None         # chân ERP của fan-out `mixed`: dữ kiện thô
                                  # dạng văn bản (KHÔNG phải câu trả lời), hoặc
                                  # "". Cùng vòng đời với doc_context.
