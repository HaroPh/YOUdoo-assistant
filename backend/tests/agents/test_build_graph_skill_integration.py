"""Test tích hợp CHẠY QUA build_graph() THẬT (Finding 3, final review fix
wave 2026-07-31): xác nhận một lượt chat có ngôn ngữ quy trình đi đúng từ
intent_router → node SOP thật → agentic_context_sync THẬT → END, VÀ
working_context được bàn giao đúng trong state cuối cùng của graph.ainvoke().

Trước file này, 3 test flow (test_skill_giao_hang_flow.py,
test_skill_nhap_kho_flow.py, test_skill_bao_gia_chiet_khau_flow.py) đều tự
dựng StateGraph tối giản riêng thay vì build_graph() thật — cố ý, vì mục
tiêu của chúng là behavior-equivalence với module gốc D:\\Project (xem
docstring đã sửa của test_skill_bao_gia_chiet_khau_flow.py). Chưa file nào
trong số đó (và không unit test nào của Task 1/9) từng đi qua build_graph()
sản xuất thật đến node SOP — đây là test ĐẦU TIÊN lấp khoảng trống đó, đồng
thời là bằng chứng đầu tiên cho "agentic_context_sync hoạt động ĐÚNG trong
graph thật nó sẽ chạy trong production" (không chỉ đơn vị — Task 1 — và
không chỉ topology — Task 9 — mà cả hành vi thật).

Pattern _SeqModel / recording tools tái dùng NGUYÊN VĂN từ
test_skill_giao_hang_flow.py — không phát minh lại."""
import json

import pytest
from pydantic import PrivateAttr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.graph import build_graph
import src.erp_query.sales as erp_sales


class _SeqModel(BaseChatModel):
    """Phát lại đúng 1 AIMessage mỗi lần model được gọi, theo thứ tự — cùng
    pattern test_skill_giao_hang_flow.py đã dùng và đã verify thực nghiệm:
    LangGraph không replay các bước ĐÃ HOÀN THÀNH của một subgraph khi resume
    (chỉ bước bị interrupt mới replay giá trị đã cache), nên một bộ đếm index
    đơn giản là an toàn.

    graph.py's llms_from_single() trải MỘT instance của model này ra MỌI vai
    (router, planner, read, ...) — nên toàn bộ lượt chat (intent_router +
    ReAct loop bên trong node SOP) dùng CHUNG một dãy kịch bản tuần tự, không
    phải mock riêng cho từng vai."""
    _responses: list = PrivateAttr()
    _idx: list = PrivateAttr(default_factory=lambda: [0])

    def __init__(self, responses, **kwargs):
        super().__init__(**kwargs)
        self._responses = list(responses)

    @property
    def _llm_type(self) -> str:
        return "seq"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        i = self._idx[0]
        self._idx[0] += 1
        return ChatResult(generations=[ChatGeneration(message=self._responses[i])])


def _po_detail_fn(ref, *, gw=None):
    return {"status": "success",
            "data": {"order": {"id": 12, "name": ref, "state": "sale"},
                     "lines": [{"product_id": [1, "Tủ gỗ"], "product_uom_qty": 10.0,
                               "price_unit": 100.0, "price_subtotal": 1000.0}]},
            "display": "x"}


def _mcp_tools():
    """3 tool ghi khai báo bởi giao-hang + nhap-kho — registry KHÔNG được để
    rỗng (registry rỗng làm skill_loader bỏ qua MỌI tool ghi ở CẢ 3 skill,
    xem docstring build_skill_tools trong skill_loader.py: "registry MCP RỖNG
    = đường test... không phải đường production"). Vì build_graph() nạp CẢ 3
    skill thật từ backend/skills/ (không chỉ giao-hang), một registry
    KHÔNG-RỖNG thiếu tool receive_order/flag_order_for_review của nhap-kho sẽ
    làm skill_loader raise SkillManifestError ("tool ghi ... không có trong
    registry MCP") — receive_order/flag_order_for_review có mặt CHỈ để thoả
    điều kiện đó, không được gọi trong flow test này.

    bao-gia-chiet-khau không cần "create_quotation" ở đây: entry logic.py TỰ
    bỏ qua việc thêm create_discount_quote khi thiếu tool đó trong registry
    (nhánh `if create is not None`, không raise — xem logic.py build_tools)."""
    calls = {"deliver": []}

    @tool("deliver_order")
    def deliver_order(order_ref: str) -> str:
        """Fake deliver_order (recording)."""
        calls["deliver"].append({"order_ref": order_ref})
        return json.dumps({"ok": True, "ref": order_ref, "model": "sale.order",
                           "display": f"Đã giao hàng cho đơn {order_ref} (1 phiếu)."},
                          ensure_ascii=False)

    @tool("receive_order")
    def receive_order(order_ref: str) -> str:
        """Fake receive_order — chỉ có mặt để registry MCP không rỗng cho
        nhap-kho; KHÔNG được gọi trong flow test này."""
        return json.dumps({"ok": True, "ref": order_ref, "model": "purchase.order",
                           "display": "stub"}, ensure_ascii=False)

    @tool("flag_order_for_review")
    def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """Fake flag_order_for_review — cùng lý do có mặt như receive_order."""
        return json.dumps({"ok": True, "ref": order_ref, "model": model,
                           "display": "stub"}, ensure_ascii=False)

    return [deliver_order, receive_order, flag_order_for_review], calls


@pytest.mark.asyncio
async def test_build_graph_real_routes_sop_and_syncs_working_context(monkeypatch):
    """"làm quy trình giao hàng cho đơn bán S00012" qua build_graph() THẬT:
    intent_router (LLM giả, hợp đồng 2 dòng thật) → node giao-hang
    (create_agent thật, tool đọc + tool ghi đã gate thật) → cổng xác nhận →
    agentic_context_sync (node THẬT, không tự dựng) → END. Xác nhận
    working_context trong state CUỐI CÙNG trả về từ graph.ainvoke() — không
    qua HTTP, không tự dựng StateGraph rút gọn."""
    monkeypatch.setattr(erp_sales, "get_sale_order_detail", _po_detail_fn)
    mcp_tools, calls = _mcp_tools()

    responses = [
        # 1) intent_router: hợp đồng 2 dòng thật (nodes.py._parse_router_output)
        AIMessage(content="intent: erp_write\nsop: giao-hang"),
        # 2) node giao-hang, lượt ReAct #1: tra chi tiết đơn
        AIMessage(content="", tool_calls=[
            {"name": "get_sale_order_detail", "args": {"ref": "S00012"}, "id": "c1"}]),
        # 3) lượt ReAct #2: gọi tool ghi — park tại interrupt confirm
        AIMessage(content="", tool_calls=[
            {"name": "deliver_order", "args": {"order_ref": "S00012"}, "id": "c2"}]),
        # 4) sau resume=True: model chốt câu trả lời cuối cùng
        AIMessage(content="Đã giao hàng cho đơn S00012 (1 phiếu)."),
    ]
    llm = _SeqModel(responses)

    graph = build_graph(llm, mcp_tools, MemorySaver())
    cfg = {"configurable": {"thread_id": "build-graph-sop-integration-1"}}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(
            content="làm quy trình giao hàng cho đơn bán S00012")]}, cfg)

    # Router thật đã đề cử ĐÚNG SOP và lớp phủ quyết tất định (graph.
    # _route_by_intent) đã cho SOP nhận trọn lượt (không bị veto).
    assert first.get("intent") == "erp_write"
    assert first.get("sop") == "giao-hang"
    assert "__interrupt__" in first, "phải park ở cổng xác nhận TRƯỚC khi ghi"
    payload = first["__interrupt__"][0].value
    assert payload["kind"] == "confirm"
    assert "S00012" in payload["question"]
    assert calls["deliver"] == []          # chưa ghi gì trước khi user xác nhận

    final_state = await graph.ainvoke(Command(resume=True), cfg)

    assert "__interrupt__" not in final_state
    assert calls["deliver"] == [{"order_ref": "S00012"}]   # đúng 1 lần, đúng args

    # agentic_context_sync THẬT (add_edge thẳng trong build_graph(), không tự
    # dựng) đã chạy sau node SOP và set working_context từ envelope write
    # thành công vừa xảy ra — bằng chứng chính của Finding 3.
    assert final_state.get("working_context") == {
        "ref": "S00012", "model": "sale.order",
        "display": "Đã giao hàng cho đơn S00012 (1 phiếu).",
    }
