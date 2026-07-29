from unittest.mock import MagicMock

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
        def _spy(llm):
            captured[name] = llm
            return real(llm)
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
