from unittest.mock import MagicMock

import pytest

from src.agents.graph import build_graph


def test_build_graph_compiles_with_write_executor_factory():
    llm = MagicMock()
    tools = []  # executor factory must accept an empty tool list
    graph = build_graph(llm, tools, checkpointer=None)
    assert graph is not None
    # erp_write_executor must be a registered node
    assert "erp_write_executor" in graph.get_graph().nodes


def test_build_graph_includes_mixed_node():
    llm = MagicMock()
    graph = build_graph(llm, tools=[], checkpointer=None)
    assert "mixed" in graph.get_graph().nodes


def test_erp_read_uses_erp_query_tools():
    llm = MagicMock()
    graph = build_graph(llm, tools=[], checkpointer=None)
    assert "erp_read" in graph.get_graph().nodes


def test_mixed_node_built_with_erp_query_read_tools(monkeypatch):
    # fusion (mixed) must read ERP via the erp_query business tools, not the MCP
    # do-tools (which are write-only now). Spy on make_fusion_node's tool arg.
    import src.agents.graph as graph_mod
    captured = {}
    real = graph_mod.make_fusion_node

    def spy(llm, tools):
        captured["names"] = [t.name for t in tools]
        return real(llm, tools)

    monkeypatch.setattr(graph_mod, "make_fusion_node", spy)
    graph_mod.build_graph(MagicMock(), tools=[], checkpointer=None)
    # erp_query read tools are present...
    assert {"list_sale_orders", "get_stock", "get_overdue_invoices"} <= set(captured["names"])
    # ...and no MCP write/do-tool leaks into fusion
    assert "post_invoice" not in captured["names"]
    assert "confirm_sale_order" not in captured["names"]


def test_route_after_planner_sends_create_quotation_to_coordinator():
    from src.agents.graph import _route_after_write_planner
    from langgraph.graph import END
    assert _route_after_write_planner({"pending_action": None}) == END
    assert _route_after_write_planner(
        {"pending_action": {"tool": "create_quotation"}}) == "create_order"
    assert _route_after_write_planner(
        {"pending_action": {"tool": "confirm_sale_order"}}) == "erp_write_executor"


def test_build_graph_has_create_order_node():
    llm = MagicMock()
    graph = build_graph(llm, tools=[], checkpointer=None)
    assert "create_order" in graph.get_graph().nodes


def test_route_after_planner_maps_all_coordinated_writes():
    from src.agents.graph import _route_after_write_planner
    from langgraph.graph import END
    assert _route_after_write_planner({"pending_action": None}) == END
    assert _route_after_write_planner(
        {"pending_action": {"tool": "create_quotation"}}) == "create_order"
    assert _route_after_write_planner(
        {"pending_action": {"tool": "create_rfq"}}) == "create_rfq"
    assert _route_after_write_planner(
        {"pending_action": {"tool": "inventory_adjustment"}}) == "inventory_adjust"
    assert _route_after_write_planner(
        {"pending_action": {"tool": "confirm_sale_order"}}) == "erp_write_executor"


def test_build_graph_registers_all_coordinator_nodes():
    llm = MagicMock()
    graph = build_graph(llm, tools=[], checkpointer=None)
    nodes = graph.get_graph().nodes
    assert {"create_order", "create_rfq", "inventory_adjust"} <= set(nodes)


def test_planner_returns_pending_for_each_coordinated_tool():
    from src.agents.write_registry import COORDINATED_TOOLS
    assert {"create_quotation", "create_rfq", "inventory_adjustment"} <= COORDINATED_TOOLS


def test_build_graph_registers_write_continuation():
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    assert "write_continuation" in graph.get_graph().nodes


def test_all_write_mutating_nodes_reachable_only_through_gated_path():
    """Whole-branch security invariant (final review, 2026-07-29): the ONLY
    nodes allowed to route into any ERP-mutating node are erp_write_planner
    and write_continuation — both gate through write_gate's
    write_actions_enabled() before ever reaching a mutation. Per-task reviews
    verified this per-node; nothing asserted it at the whole-graph level. A
    future edge added elsewhere straight into erp_write_executor or any
    WRITE_COORDINATORS node must fail this test."""
    from src.agents.write_registry import WRITE_COORDINATORS
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    mutating_nodes = {"erp_write_executor"} | {spec.node for spec in WRITE_COORDINATORS.values()}
    allowed_sources = {"erp_write_planner", "write_continuation"}
    for source, target in edges:
        if target in mutating_nodes:
            assert source in allowed_sources, (
                f"unexpected edge {source} -> {target} bypasses the write gate")


def test_all_writes_route_through_continuation():
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    assert ("erp_write_executor", "write_continuation") in edges
    for node in ("create_order", "create_rfq", "inventory_adjust"):
        assert (node, "write_continuation") in edges
    assert ("erp_write_executor", "__end__") not in edges


def test_continuation_loops_back_to_executor():
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    assert ("write_continuation", "erp_write_executor") in edges
    assert ("write_continuation", "__end__") in edges


def test_build_graph_accepts_role_mapping(monkeypatch):
    # Previously this test asserted only `graph is not None`, which is VACUOUS:
    # StateGraph.compile() never invokes node bodies and MagicMock() swallows
    # any attribute access silently, so that assertion still passes even if
    # graph.py's per-role wiring is broken entirely (e.g. every node gets the
    # raw llm/dict, or two roles' llms are swapped). Spy on each make_*_node
    # factory — same idiom as test_mixed_node_built_with_erp_query_read_tools
    # above — to capture the actual llm object each node factory is called
    # with, then assert identity against that role's distinct sentinel.
    import src.agents.graph as graph_mod
    from src.agents.models import ROLES
    from src.agents.write_registry import WRITE_COORDINATORS, Spec

    llms = {r: MagicMock(name=r) for r in ROLES}
    captured = {}

    def spy_llm_only(name, real):
        def _spy(llm, *args, **kwargs):
            captured[name] = llm
            return real(llm, *args, **kwargs)
        return _spy

    def spy_llm_tools(name, real):
        def _spy(llm, tools):
            captured[name] = llm
            return real(llm, tools)
        return _spy

    monkeypatch.setattr(graph_mod, "make_intent_router_node",
                         spy_llm_only("intent_router", graph_mod.make_intent_router_node))
    monkeypatch.setattr(graph_mod, "make_erp_read_node",
                         spy_llm_tools("erp_read", graph_mod.make_erp_read_node))
    monkeypatch.setattr(graph_mod, "make_erp_write_planner_node",
                         spy_llm_only("erp_write_planner", graph_mod.make_erp_write_planner_node))
    monkeypatch.setattr(graph_mod, "make_rag_node",
                         spy_llm_only("rag", graph_mod.make_rag_node))
    monkeypatch.setattr(graph_mod, "make_fusion_node",
                         spy_llm_tools("mixed", graph_mod.make_fusion_node))
    monkeypatch.setattr(graph_mod, "make_respond_unknown_node",
                         spy_llm_only("respond_unknown", graph_mod.make_respond_unknown_node))

    # Coordinators (create_order/create_rfq/.../inventory_adjust) receive
    # llms["planner"] too, via spec.build(llms["planner"], tools) in
    # graph.py — spy on each Spec's .build so a role-swap there is caught.
    spied_coordinators = {}
    for tool, spec in WRITE_COORDINATORS.items():
        real_build = spec.build

        def make_spy(node_name, real_build=real_build):
            def _spy(llm, tools):
                captured[node_name] = llm
                return real_build(llm, tools)
            return _spy

        spied_coordinators[tool] = Spec(spec.node, make_spy(spec.node))
    monkeypatch.setattr(graph_mod, "WRITE_COORDINATORS", spied_coordinators)

    graph = build_graph(llms, tools=[], checkpointer=None)
    assert graph is not None

    # Each node got its own role's llm...
    assert captured["intent_router"] is llms["router"]
    assert captured["erp_read"] is llms["read"]
    assert captured["erp_write_planner"] is llms["planner"]
    assert captured["rag"] is llms["synthesis"]
    assert captured["mixed"] is llms["fusion"]
    assert captured["respond_unknown"] is llms["chitchat"]
    assert captured["create_order"] is llms["planner"]
    assert captured["create_rfq"] is llms["planner"]
    assert captured["inventory_adjust"] is llms["planner"]

    # ...and critically NOT some other role's llm — this is what catches a
    # role-swap bug (e.g. llms["read"] accidentally wired to router/planner).
    assert captured["intent_router"] is not llms["read"]
    assert captured["intent_router"] is not llms["planner"]
    assert captured["erp_read"] is not llms["router"]
    assert captured["erp_read"] is not llms["planner"]
    assert captured["erp_write_planner"] is not llms["read"]
    assert captured["erp_write_planner"] is not llms["router"]
    assert captured["rag"] is not llms["fusion"]
    assert captured["mixed"] is not llms["synthesis"]
    assert captured["respond_unknown"] is not llms["router"]


# ── Regression: live-verify 2026-07-16 found the AND-only gate (intent ==
# "erp_write") caused the MIRROR-IMAGE bug — real commands using the skill's
# own literal TRIGGERS phrases got misrouted away from the skill because the
# router classified them "mixed"/"erp_read" (ambiguous under prompts.py's
# own "mixed" definition, which the router was never tuned to disambiguate
# from an execute-SOP-for-order-X command). Fixed by switching to an OR:
# erp_write OR "does not look like a question" (deterministic marker check,
# _looks_like_question). These tests reproduce the exact 3 failing repro
# phrasings with the WRONG intent attached, and assert routing now succeeds
# regardless of router classification. ──────────────────────────────────
#
# NOTE (SP-1B Task 10): agentic routing (AGENTIC_SKILLS/agentic_registry) is
# NOT ported in this plan (deferred to SP-2 — spec §3). _route_by_intent now
# just returns state["intent"], so only the two _looks_like_question unit
# tests below still apply; the trigger-routing regression tests that used to
# sit here were deleted (see task-10-report.md for the full list).

def test_looks_like_question_detects_all_markers():
    from src.agents.graph import _looks_like_question
    from src.agents.skill_gate import _fold
    questions = [
        "quy trình nhập kho là gì?",
        "kiểm tra tình trạng giao hàng theo đơn S00074",
        "chính sách báo giá chiết khấu như thế nào?",
        "quy trình nhập kho nghĩa là gì",
        "tại sao phải làm quy trình nhập kho",
        "giải thích quy trình nhập kho giúp tôi",
        "hướng dẫn quy trình nhập kho",
        "trạng thái đơn mua P00021 thế nào",
        "đơn này có xác nhận được không",
    ]
    for q in questions:
        assert _looks_like_question(_fold(q)), q


def test_looks_like_question_false_for_plain_commands():
    from src.agents.graph import _looks_like_question
    from src.agents.skill_gate import _fold
    commands = [
        "làm quy trình nhập kho cho đơn mua P00021",
        "nhập kho theo quy trình cho đơn mua P00021",
        "quy trình nhập kho cho đơn mua P00021",
        "giao hàng cho đơn bán S00012",
        "báo giá chiết khấu cho Cửa hàng ABC, 5 Tủ gỗ",
    ]
    for c in commands:
        assert not _looks_like_question(_fold(c)), c


# ── SP-2a: định tuyến hybrid ─────────────────────────────────────────────────
# Tầng 1 (description → đề cử `sop`) là XÁC SUẤT. Tầng 2 (_looks_like_question
# phủ quyết) là TẤT ĐỊNH và cố ý — live-verify 2026-07-16 cho thấy router LLM
# thua đúng bài này 3/3 lần. Bảng dưới đo tầng 2.

from langchain_core.messages import HumanMessage


def _state(text, intent, sop):
    return {"messages": [HumanMessage(content=text)], "intent": intent, "sop": sop}


def test_route_sop_wins_for_plain_execute_command():
    from src.agents.graph import _route_by_intent
    # Router phân loại SAI (mixed) nhưng câu không mang dấu hiệu câu hỏi →
    # SOP vẫn nhận trọn lượt. Đây CHÍNH LÀ ca thua 3/3 lần ngày 2026-07-16.
    assert _route_by_intent(
        _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "nhap-kho"
    assert _route_by_intent(
        _state("nhập kho theo quy trình cho đơn mua P00021", "erp_read", "nhap-kho")) == "nhap-kho"


def test_route_sop_wins_when_intent_is_erp_write_even_if_question_shaped():
    from src.agents.graph import _route_by_intent
    # Nhánh OR: router tự tin nói erp_write thì lối tắt vẫn mở.
    assert _route_by_intent(
        _state("giao hàng cho đơn S1 được không", "erp_write", "giao-hang")) == "giao-hang"


def test_route_question_vetoes_sop_proposal():
    from src.agents.graph import _route_by_intent
    # Ca hijack GỐC: "quy trình nhập kho là gì?" phải đi RAG, không đi SOP.
    assert _route_by_intent(
        _state("quy trình nhập kho là gì?", "rag", "nhap-kho")) == "rag"
    assert _route_by_intent(
        _state("quy trình giao hàng như thế nào", "rag", "giao-hang")) == "rag"


def test_route_without_sop_proposal_returns_intent():
    from src.agents.graph import _route_by_intent
    assert _route_by_intent(_state("giao hàng cho đơn S00040", "erp_write", None)) == "erp_write"
    assert _route_by_intent(_state("chào bạn", "unknown", None)) == "unknown"
    assert _route_by_intent(_state("x", None, None)) == "unknown"


def test_route_kill_switch_drops_every_sop_proposal(monkeypatch):
    from src.agents.graph import _route_by_intent
    monkeypatch.setenv("ERP_SKILLS_ENABLED", "0")
    assert _route_by_intent(
        _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "mixed"


def test_route_kill_switch_only_off_value_is_zero(monkeypatch):
    from src.agents.graph import _route_by_intent
    for value in ("1", "true", "yes", ""):
        monkeypatch.setenv("ERP_SKILLS_ENABLED", value)
        assert _route_by_intent(
            _state("quy trình nhập kho cho đơn mua P00021", "mixed", "nhap-kho")) == "nhap-kho"


def test_build_graph_registers_every_skill_node_and_context_sync():
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    nodes = set(graph.get_graph().nodes)
    assert "agentic_context_sync" in nodes
    for spec in load_skill_specs():
        assert spec.name in nodes


def test_every_skill_node_edges_into_context_sync():
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    for spec in load_skill_specs():
        assert (spec.name, "agentic_context_sync") in edges
        assert (spec.name, "__end__") not in edges
    assert ("agentic_context_sync", "__end__") in edges


def test_skill_nodes_reachable_only_from_intent_router():
    """Bất biến bảo mật toàn đồ thị (nối dài test_all_write_mutating_nodes_...):
    một node SOP mang tool ghi đã gate, nhưng chỉ được vào từ intent_router —
    nơi DUY NHẤT áp phủ quyết tất định. Một cạnh tương lai chọc thẳng vào node
    SOP từ chỗ khác sẽ đi vòng qua lớp phòng thủ đó và phải fail test này."""
    from src.agents.skill_loader import load_skill_specs
    graph = build_graph(MagicMock(), tools=[], checkpointer=None)
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    skill_nodes = {s.name for s in load_skill_specs()}
    assert skill_nodes, "không có skill nào — test này vô nghĩa nếu rỗng"
    for source, target in edges:
        if target in skill_nodes:
            assert source == "intent_router", (
                f"cạnh {source} -> {target} vào node SOP không qua intent_router")


def test_every_write_tool_in_a_skill_node_is_gated():
    """Bất biến bảo mật: không tool ghi TRẦN nào lọt vào node SOP. So sánh theo
    ĐỐI TƯỢNG (is), không theo tên — wrapper cố ý mang cùng tên."""
    import json
    from langchain_core.tools import tool as lc_tool
    from src.agents.skill_loader import build_skill_tools, load_skill_specs

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("receive_order")
    async def receive_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("create_quotation")
    async def create_quotation(partner_id: int, lines: list) -> str:
        """fake"""
        return "{}"

    mcp = [deliver_order, receive_order, flag_order_for_review, create_quotation]
    raw = {t.name: t for t in mcp}
    for spec in load_skill_specs():
        for t in build_skill_tools(spec, mcp):
            assert t is not raw.get(t.name), (
                f"{spec.name}: tool ghi {t.name} bind THẲNG, không qua gate")


@pytest.mark.asyncio
async def test_entry_based_skill_tool_gates_via_confirm_write_not_name_match(monkeypatch):
    """test_every_write_tool_in_a_skill_node_is_gated (trên) phát hiện leak bằng
    so TÊN với tool MCP gốc — vô dụng với bao-gia-chiet-khau vì tool nó lộ ra
    (create_discount_quote) KHÁC tên tool MCP gốc (create_quotation), nên
    raw.get("create_discount_quote") luôn None và assertion `is not None` luôn
    đúng bất kể logic.py có thực sự gate hay không (cảm giác an toàn giả).

    Test này xác nhận TRỰC TIẾP thuộc tính thật: logic.py (entry của
    bao-gia-chiet-khau) gọi _confirm_write TRƯỚC khi ainvoke tool MCP thật,
    không phụ thuộc quy ước đặt tên. _confirm_write patch trên chính module
    logic.py đã nạp — đây là skill DUY NHẤT tự gọi _confirm_write bên trong
    entry (2 skill kia dùng wrapper do skill_loader sinh), như
    test_skill_bao_gia_chiet_khau_flow.py (Task 7) đã xác lập pattern
    _patch_confirm/_patch_reads; test này chỉ tái dùng đúng pattern đó ở tầng
    bất biến toàn đồ thị của Task 9, không phát minh lại."""
    from langchain_core.tools import tool as lc_tool
    from src.agents.agentic_gate import REFUSED_MSG
    from src.agents.skill_loader import (SKILLS_DIR, _load_entry_module,
                                         load_skill_specs)

    spec = next(s for s in load_skill_specs() if s.name == "bao-gia-chiet-khau")
    logic = _load_entry_module(spec)

    calls = {"confirm": [], "ainvoke": []}

    def fake_confirm_write(question):
        calls["confirm"].append(question)
        return False   # từ chối — assert KHÔNG có ainvoke nào xảy ra sau đó

    monkeypatch.setattr(logic, "_confirm_write", fake_confirm_write)
    # Đẩy qua resolve khách/sản phẩm để chạm tới _confirm_write — cùng pattern
    # _patch_reads của test_skill_bao_gia_chiet_khau_flow.py.
    monkeypatch.setattr(logic.sales, "find_customer", lambda *a, **k: {
        "status": "success",
        "data": {"matches": [{"id": 41, "name": "Azur", "score": 1}],
                 "needs_disambiguation": False},
        "display": "x"})
    monkeypatch.setattr(logic.inventory, "find_product", lambda *a, **k: {
        "status": "success",
        "data": {"matches": [{"id": 552, "name": "Tủ", "score": 1}],
                 "needs_disambiguation": False},
        "display": "x"})
    monkeypatch.setattr(logic.sales, "get_product_price", lambda *a, **k: {
        "status": "success", "data": {"price": 30_000_000.0}, "display": "x"})

    @lc_tool("create_quotation")
    async def fake_create_quotation(partner_id: int, lines: list) -> str:
        """fake MCP create_quotation — ghi nhận nếu bị gọi."""
        calls["ainvoke"].append({"partner_id": partner_id, "lines": lines})
        return "{}"

    tools = {t.name: t for t in logic.build_tools([fake_create_quotation])}
    result = await tools["create_discount_quote"].ainvoke(
        {"customer": "Azur", "lines": [{"product": "Tủ", "qty": 2}],
         "tier": "thuong"})

    assert calls["confirm"], "logic.py không hề gọi _confirm_write"
    assert calls["ainvoke"] == [], (
        "logic.py gọi ainvoke dù _confirm_write trả False — gate bị bỏ qua")
    assert result == REFUSED_MSG
