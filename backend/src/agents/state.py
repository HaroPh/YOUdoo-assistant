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
                                  # định cuối vẫn do routing.decide_route
                                  # (phủ quyết tất định), không do trường này.
    depth: str | None             # độ sâu SOP router đề cử: "full_sop" |
                                  # "one_step" | "unsure" | "none". TRANSIENT
                                  # y hệt `sop` — intent_router ghi khoá này
                                  # trên MỌI return. "none" khi sop rỗng.
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
    suggested_write: bool | None  # TRANSIENT — cờ "lượt trả lời trước có đề
                                  # xuất một hành động ghi không". Tự hết hạn
                                  # qua suggested_write_at (neo độ dài messages)
                                  # — KHÔNG cần node nào chủ động dọn dẹp field
                                  # này, vì decide_route chỉ tin nó khi
                                  # len(messages) hiện tại == đúng
                                  # suggested_write_at + 1 (đúng NGAY lượt kế
                                  # tiếp, không có gì xen giữa). Lịch sử: bản
                                  # đầu gắn cờ này vào AIMessage.additional_kwargs
                                  # thay vì state — bị `_invoke_fresh`
                                  # (erp_agent.py) xoá sạch trên MỌI lượt không
                                  # parked (client gửi lại history dạng text
                                  # thuần, không mang additional_kwargs), nên
                                  # cờ không bao giờ tới được decide_route trong
                                  # production. State field riêng KHÔNG bị
                                  # _invoke_fresh đụng tới (nó chỉ ghi đè kênh
                                  # "messages"), nên sống sót đúng cách.
    suggested_write_at: int | None  # NEO TỰ HẾT HẠN cho field phía trên: số
                                  # message NGƯỜI DÙNG THẤY sau lượt đặt cờ, tức
                                  # len(state["messages"]) lúc node chạy + 1 câu
                                  # trả lời node đó phát ra. KHÔNG phải độ dài
                                  # kênh messages nội bộ sau khi node ghi xong:
                                  # erp_read (ReAct) còn phụ thêm cả ai-tool-call
                                  # lẫn tool-result, nhưng erp_agent.chat() chỉ
                                  # trả về messages[-1].content nên client chỉ
                                  # thấy ĐÚNG MỘT message/lượt, và chính history
                                  # text thuần của client mới là thứ
                                  # `_invoke_fresh` dựng lại thành
                                  # state["messages"] ở lượt sau. Neo theo độ
                                  # dài nội bộ sẽ không bao giờ khớp trên đường
                                  # erp_read có gọi tool (xem final-review fix
                                  # wave 2026-08-05, có đo thật).
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
    user_memory: str | None       # khối ký ức đã render, nạp MỘT LẦN ở chat()
                                  # rồi ghép vào đầu system prompt của 4 node
                                  # sinh câu trả lời. Đọc-thôi với mọi node —
                                  # không node nào ghi key này.
