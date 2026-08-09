# backend/src/agents/graph.py
from langgraph.graph import StateGraph, END

from .state import ERPAgentState
from ..erp_query.tools import build_erp_query_tools
from .nodes import (
    make_erp_read_node,
    make_erp_write_planner_node,
    make_erp_write_executor_node,
    make_rag_node,
    make_respond_unknown_node,
)
from .routing import make_intent_router_node, decide_route
from .fanout import (make_fuse_answer_node, make_gather_docs_node,
                     make_gather_erp_node, make_mixed_node)
from .write_registry import WRITE_COORDINATORS, COORDINATED_TOOLS, CONFIRM_IN_CHAIN
from .continuation import make_write_continuation_node, _route_after_continuation
from .mail_write import (MAIL_COORDINATOR_CFGS, make_send_template_email_node,
                         make_route_after_mail_preview)
from .models import llms_from_single
from .skill_loader import build_skill_node, load_skill_specs, render_worker_block
from .agentic_context_sync import make_agentic_context_sync_node


def _route_after_write_planner(state: ERPAgentState) -> str:
    action = state.get("pending_action")
    if action is None:
        # Write locked or unparseable: planner already added a message → END
        return END
    tool = action.get("tool")
    if tool in COORDINATED_TOOLS:
        return WRITE_COORDINATORS[tool].node
    return "erp_write_executor"


def build_graph(llm, tools, checkpointer) -> object:
    # Nhận single-llm (test/back-compat: mọi role chung 1 model) HOẶC mapping
    # role→llm (production, từ make_llms()). Normalize về mapping.
    llms = llm if isinstance(llm, dict) else llms_from_single(llm)

    g = StateGraph(ERPAgentState)

    # Nạp SOP MỘT LẦN, fail-loud: SKILL.md sai thẩm quyền/cấu trúc → ném
    # SkillManifestError ra ngoài build_graph → ERPAgent.setup() → app KHÔNG
    # LÊN. Thà không lên còn hơn lên sai (cùng triết lý assert_embedding_marker).
    skill_specs = load_skill_specs()

    g.add_node("intent_router", make_intent_router_node(
        llms["router"], render_worker_block(skill_specs),
        frozenset(s.name for s in skill_specs)))
    g.add_node("erp_read", make_erp_read_node(llms["read"], build_erp_query_tools()))
    g.add_node("erp_write_planner", make_erp_write_planner_node(llms["planner"]))
    g.add_node("erp_write_executor", make_erp_write_executor_node(tools))
    g.add_node("rag", make_rag_node(llms["synthesis"]))
    # Fan-out đường đọc (SP-2b): `mixed` giữ TÊN và giữ chỗ trong intent_targets
    # để decide_route không phải đổi — hàm đó là thứ SOP_SELECT_CASES đo
    # trực tiếp. Hai chân chạy cùng superstep (hai cạnh thẳng ra), fuse_answer
    # có hai cạnh vào nên chỉ chạy sau khi CẢ HAI xong.
    g.add_node("mixed", make_mixed_node())
    g.add_node("gather_docs", make_gather_docs_node())
    g.add_node("gather_erp", make_gather_erp_node(
        llms["fusion"], build_erp_query_tools()))
    g.add_node("fuse_answer", make_fuse_answer_node(llms["fusion"]))
    g.add_node("respond_unknown", make_respond_unknown_node(llms["chitchat"]))
    for spec in WRITE_COORDINATORS.values():
        g.add_node(spec.node, spec.build(llms["planner"], tools))
    g.add_node("write_continuation", make_write_continuation_node())

    for spec in skill_specs:
        # Node SOP add THẲNG vào graph ngoài (không bọc hàm async viết tay) —
        # điều kiện để interrupt() trong tool của nó compose đúng với
        # checkpointer. recursion_limit áp trong build_skill_node (wiring).
        g.add_node(spec.name, build_skill_node(spec, llms["planner"], tools))
        g.add_edge(spec.name, "agentic_context_sync")
    g.add_node("agentic_context_sync", make_agentic_context_sync_node())
    g.add_edge("agentic_context_sync", END)

    g.set_entry_point("intent_router")

    intent_targets = {
        "erp_read": "erp_read",
        "erp_write": "erp_write_planner",
        "rag": "rag",
        "mixed": "mixed",
        "unknown": "respond_unknown",
    }
    intent_targets.update({s.name: s.name for s in skill_specs})
    g.add_conditional_edges("intent_router", decide_route, intent_targets)

    g.add_edge("erp_read", END)
    write_targets = {END: END, "erp_write_executor": "erp_write_executor"}
    write_targets.update({spec.node: spec.node for spec in WRITE_COORDINATORS.values()})
    g.add_conditional_edges("erp_write_planner", _route_after_write_planner, write_targets)
    g.add_edge("erp_write_executor", "write_continuation")
    mail_preview_nodes = {cfg.preview_node for cfg in MAIL_COORDINATOR_CFGS}
    for spec in WRITE_COORDINATORS.values():
        if spec.node in mail_preview_nodes:
            continue  # coordinator 2 node, nối tay ngay dưới — xem docstring
                     # mail_write.py: preview là 1 write thật, không được
                     # unconditional-edge thẳng write_continuation
        g.add_edge(spec.node, "write_continuation")

    # Mỗi coordinator gửi mail là 2 node. Node 1 (preview) đã add ở vòng lặp
    # add_node phía trên (.node của Spec trỏ vào nó). Node 2 (gửi) KHÔNG nằm
    # trong WRITE_COORDINATORS — add tay ở đây, MỘT CẶP RIÊNG cho mỗi cfg
    # (không share node instance giữa các lối vào).
    for cfg in MAIL_COORDINATOR_CFGS:
        g.add_node(cfg.send_node, make_send_template_email_node(tools, cfg))
        g.add_conditional_edges(
            cfg.preview_node, make_route_after_mail_preview(cfg),
            {cfg.send_node: cfg.send_node,
             "write_continuation": "write_continuation"})
        g.add_edge(cfg.send_node, "write_continuation")

    cont_targets = {"erp_write_executor": "erp_write_executor", END: END}
    cont_targets.update({WRITE_COORDINATORS[t].node: WRITE_COORDINATORS[t].node
                         for t in CONFIRM_IN_CHAIN})
    g.add_conditional_edges("write_continuation", _route_after_continuation,
                            cont_targets)
    g.add_edge("rag", END)
    g.add_edge("mixed", "gather_docs")
    g.add_edge("mixed", "gather_erp")
    g.add_edge("gather_docs", "fuse_answer")
    g.add_edge("gather_erp", "fuse_answer")
    g.add_edge("fuse_answer", END)
    g.add_edge("respond_unknown", END)

    return g.compile(checkpointer=checkpointer)
