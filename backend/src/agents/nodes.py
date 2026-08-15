# backend/src/agents/nodes.py
import os
import re
import asyncio
import json
import time
import logging
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.agents import create_agent as _create_agent
from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .prompts import (SYSTEM_PROMPT, WRITE_PLANNER_PROMPT,
                      WRITE_CONFIRM_PREFIX, WRITE_CONFIRM_SUFFIX,
                      CHITCHAT_PROMPT, render_working_context, dept_of)
from .roles import OTHER_DEPT, DENIED, DEPT_OF
from .write_registry import COORDINATED_TOOLS, expand_chain
from .handoff import build_handoff, existing_handoff
from ..erp_query import crm
from ..rag.retrieve import retrieve
from .synthesis import synthesize, SAFE_MSG, extract_write_suggestion
from .erp_grounding import verify_erp_grounding
from .tool_result import _tool_result_text, parse_write_result
from .working_context import derive_working_context, enforce_explicit_ref
from . import write_gate
from .friction import log_friction

logger = logging.getLogger(__name__)


# ── erp_read ─────────────────────────────────────────────────────────────────

def make_erp_read_node(llm, tools):
    async def erp_read(state: ERPAgentState) -> dict:
        # Invariant A: MỘT system prompt hiệu dụng duy nhất. Context đặt TRƯỚC
        # SYSTEM_PROMPT để '/no_think' giữ vị trí cuối. Build agent per-call là
        # cách thoả invariant (chi phí ~ms, stack local); context KHÔNG được
        # chèn vào messages nên không thể leak vào state.
        wc = state.get("working_context")
        prompt = (render_working_context(wc) + "\n\n" + SYSTEM_PROMPT) \
            if wc else SYSTEM_PROMPT
        agent = _create_agent(llm, tools, system_prompt=prompt)
        result = await agent.ainvoke({"messages": state["messages"]})
        # Return only messages added by the agent (skip the input messages)
        new_msgs = result["messages"][len(state["messages"]):]
        tool_outputs = [m.content for m in new_msgs if m.type == "tool"]
        if tool_outputs and new_msgs and new_msgs[-1].type == "ai":
            verified = await verify_erp_grounding(new_msgs[-1].content, tool_outputs, llm)
            if verified != new_msgs[-1].content:
                new_msgs = [*new_msgs[:-1], AIMessage(content=verified)]
        # Tách cờ ĐỀ_XUẤT_GHI khỏi câu trả lời cuối (nếu có). Cờ đi qua STATE
        # KEY RIÊNG chứ KHÔNG gắn lên message: `_invoke_fresh` (erp_agent.py)
        # dựng lại toàn bộ kênh "messages" từ history text thuần của client
        # trên MỌI lượt không parked, nên cờ nằm trên message không bao giờ tới
        # được decide_route trong production (xem routing.py).
        suggested = False
        if new_msgs and new_msgs[-1].type == "ai":
            clean, suggested = extract_write_suggestion(new_msgs[-1].content or "")
            if clean != new_msgs[-1].content:
                new_msgs = [*new_msgs[:-1], AIMessage(content=clean)]
        # Neo đếm theo cái NGƯỜI DÙNG THẤY (history vào + 1 câu trả lời), KHÔNG
        # theo len(new_msgs): node này là ReAct nên new_msgs thường gồm cả
        # ai-tool-call + tool-result, nhưng erp_agent.chat() chỉ trả về
        # messages[-1].content nên client chỉ gửi lại ĐÚNG MỘT assistant
        # message cho lượt này — và chính history đó là thứ `_invoke_fresh`
        # dựng thành state["messages"] ở lượt sau. Neo theo độ dài kênh nội bộ
        # thì trên đường có gọi tool sẽ KHÔNG BAO GIỜ khớp (đo thật, final
        # review fix wave 2026-08-05).
        return {"messages": new_msgs, "suggested_write": suggested,
                "suggested_write_at": len(state["messages"]) + 1}

    return erp_read


# ── rag (doc-only answering) ──────────────────────────────────────────────────

def make_rag_node(llm):
    """Document Q&A: retrieve (sync, off the loop) → grounded synthesis + citations.

    retrieve() is sync psycopg; asyncio.to_thread keeps the event loop free.
    Any failure degrades to SAFE_MSG — the graph never crashes.
    """
    async def rag_node(state: ERPAgentState) -> dict:
        last_human = next(
            (m for m in reversed(state["messages"]) if m.type == "human"), None)
        if last_human is None:
            return {"messages": [AIMessage(content=SAFE_MSG)]}
        query = last_human.content
        try:
            result = await asyncio.to_thread(retrieve, query)
            answer = await synthesize(query, result, llm)
        except Exception:
            logger.exception("rag_node failed")
            answer = SAFE_MSG
        return {"messages": [AIMessage(content=answer)]}

    return rag_node


# ── respond_unknown ───────────────────────────────────────────────────────────

def make_respond_unknown_node(llm):
    async def respond_unknown(state: ERPAgentState) -> dict:
        # M5 (ADR-009): role chit-chat được phép chạy cloud (QĐ M2) → không
        # gửi full history — assistant-turn trước có thể mang dữ liệu ERP từ
        # erp_read. Chỉ gửi tin nhắn user cuối. Nếu KHÔNG có tin nhắn user
        # nào trong state (route hiếm gặp), KHÔNG gọi LLM — trả câu mặc
        # định, triệt tiêu hoàn toàn khả năng forward nội dung assistant-turn
        # ra ngoài.
        last_human = next(
            (m for m in reversed(state["messages"]) if m.type == "human"), None)
        if last_human is None:
            return {"messages": [AIMessage(content="Xin lỗi, bạn cần hỗ trợ gì?")]}
        response = await llm.ainvoke([SystemMessage(content=CHITCHAT_PROMPT), last_human])
        return {"messages": [response]}

    return respond_unknown


# ── erp_write_planner ─────────────────────────────────────────────────────────

# A5 redefined (spec 2026-07-10-a5-planner-json-retry): qwen3:8b là model họ
# thinking và WRITE_PLANNER_PROMPT không có /no_think — các dạng JSON hỏng
# dễ đoán (khối <think>, markdown fence) cứu được tất định trước khi tốn
# 1 call LLM sửa lỗi. Khóa #7 cấm escalate cloud; sau Phase B không còn
# model local thứ 2 → retry CÙNG model, đúng 1 lần.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

_JSON_CORRECTION = (
    "Câu trả lời trên không phải JSON hợp lệ. Trả lời LẠI CHỈ bằng JSON "
    "đúng định dạng đã yêu cầu — không markdown fence, không giải thích, "
    "không text nào khác."
)


def _try_loads(text: str) -> dict | None:
    """json.loads trả dict, mọi thứ khác (parse fail / JSON không phải dict
    như list, số) → None — plan bắt buộc là object."""
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def _parse_plan_tiered(raw: str) -> tuple[dict | None, str | None]:
    """Parse pipeline 2 tầng (spec §3.1), trả thêm tier cứu được:
    ("raw" | "salvage" | None). Tầng 1: loads thẳng. Tầng 2: salvage tất
    định — strip mọi khối <think>…</think> rồi strip markdown fence nếu nó
    bọc TOÀN BỘ phần còn lại. KHÔNG brace-extract tùy tiện (có thể vớ JSON
    nháp trong khối think). (None, None) = không cứu được."""
    text = raw.strip()
    plan = _try_loads(text)
    if plan is not None:
        return plan, "raw"
    stripped = _THINK_RE.sub("", text).strip()
    fence = _FENCE_RE.fullmatch(stripped)
    if fence:
        stripped = fence.group(1).strip()
    plan = _try_loads(stripped)
    if plan is not None:
        return plan, "salvage"
    return None, None


def _parse_plan(raw: str) -> dict | None:
    """Wrapper giữ contract cũ — 15 test A5 và mọi caller khác không đổi."""
    plan, _tier = _parse_plan_tiered(raw)
    return plan


def _friction_event(llm, outcome: str, tool, raw_len: list,
                    excerpt: str | None = None) -> dict:
    """Event schema spec §3.3. model LUÔN ép str() — MagicMock auto-attribute
    không JSON-serializable, thiếu str() thì log_friction nuốt lỗi và test
    wiring 'mất dòng' khó hiểu."""
    return {
        "ts": datetime.now().astimezone().isoformat(),
        "source": "planner_json",
        "outcome": outcome,
        "tool": tool,
        "model": str(getattr(llm, "model_name", "")),
        "raw_len": raw_len,
        "excerpt": excerpt,
    }


async def _plan_json(llm, system: str, messages: list) -> dict | None:
    """Gọi planner LLM + parse, với đúng 1 lần corrective retry CÙNG model
    khi lần đầu không parse được (A5 redefined — khóa #7 cấm escalate cloud,
    không còn model local thứ 2 sau Phase B). 2 message sửa lỗi chỉ sống
    trong lời gọi này — không rò vào state["messages"] (spec §3.2).
    Mỗi lời gọi ghi đúng 1 friction event (spec 2026-07-12) — kể cả khi
    thành công ngay, để có mẫu số tính tỷ lệ."""
    base = [SystemMessage(content=system), *messages]
    response = await llm.ainvoke(base)
    plan, tier = _parse_plan_tiered(response.content)
    if plan is not None:
        log_friction(_friction_event(
            llm, "raw" if tier == "raw" else "salvage",
            plan.get("tool"), [len(response.content)]))
        return plan
    logger.warning("Write planner returned non-JSON: %s", response.content)
    retry = await llm.ainvoke([
        *base,
        AIMessage(content=response.content),
        HumanMessage(content=_JSON_CORRECTION),
    ])
    plan, tier = _parse_plan_tiered(retry.content)
    if plan is not None:
        log_friction(_friction_event(
            llm, "retry_raw" if tier == "raw" else "retry_salvage",
            plan.get("tool"), [len(response.content), len(retry.content)]))
        return plan
    logger.warning("Write planner returned non-JSON after 2 attempts: %s",
                   retry.content)
    log_friction(_friction_event(
        llm, "fail", None, [len(response.content), len(retry.content)],
        excerpt=retry.content[:500]))
    return None


def _role_refusal_message(role_cfg, tool: str) -> str:
    """Câu từ chối tất định khi vai hiện tại không có quyền gọi `tool`
    (state OTHER_DEPT/DENIED — xem roles.RoleCfg.state_of). Dùng chung cho
    cả hai nguyên nhân: (a) tool có thật nhưng thuộc bộ phận khác, và (b)
    tool không hề tồn tại trong bất kỳ vai nào (vd LLM bịa tên như 'other') —
    RoleCfg.state_of fail-closed nên cả hai rơi vào cùng nhánh DENIED/OTHER_DEPT,
    và dept_of trả 'khác' cho trường hợp (b) vì không có bộ phận cụ thể để chỉ
    sang."""
    dept = dept_of(tool)
    return (f"Việc này không thuộc quyền hạn của bộ phận {role_cfg.label}. "
            f"Vui lòng liên hệ bộ phận {dept} để thực hiện.")


def _handoff_notice(role_cfg, tool: str) -> str:
    """Câu giải thích ĐI KÈM đề xuất bàn giao.

    Không được bỏ. Bản đầu của Task 2 chỉ thay `plan` rồi im lặng: người dùng
    thấy một đề nghị tạo activity mà không hiểu vì sao việc mình xin lại thành
    ra thế. Test có sẵn `test_accounting_refused_deliver_order_no_pending_action`
    canh đúng điều này và đã ĐỎ — nó bảo vệ LỜI GIẢI THÍCH, không chỉ bảo vệ
    `pending_action is None`."""
    return (f"Việc này không thuộc quyền hạn của bộ phận {role_cfg.label}. "
            f"Tôi có thể chuyển cho bộ phận {dept_of(tool)} — bạn xác nhận nhé.")


def _duplicate_handoff(handoff: dict) -> dict | None:
    """Activity đang mở trên ĐÚNG chứng từ của `handoff`, hoặc None.

    Chống spam (ADR-012 §5): hỏi lại ba lần thì bộ phận kia nhận ba việc
    giống nhau. Tra TRƯỚC KHI ĐỀ XUẤT, không phải trước khi ghi — đề xuất
    trùng đã là phiền rồi.

    Tra hỏng KHÔNG được chặn bàn giao: bọc try/except, lỗi tra chỉ log
    warning rồi coi như không có việc trùng — cùng lắm là một việc trùng,
    còn hơn mất hẳn đường bàn giao."""
    try:
        # limit=100 (final-review I5), không phải mặc định 20: gateway sắp
        # theo date_deadline asc, vai đích có thể đã có nhiều việc quá hạn
        # cũ chiếm hết 20 dòng đầu, đẩy dòng trùng thật ra ngoài cửa sổ —
        # khiến _duplicate_handoff báo "không trùng" SAI. 100 là MAX_LIMIT
        # của gateway (đủ lớn, không phải không giới hạn).
        env = crm.list_my_activities(handoff["args"]["assignee"], limit=100)
        return existing_handoff((env.get("data") or {}).get("rows"),
                                handoff["args"]["res_model"],
                                handoff["args"]["ref"])
    except Exception:                                       # noqa: BLE001
        logger.warning("không tra được activity trùng", exc_info=True)
        return None


def make_erp_write_planner_node(llm, planner_prompt=None, role_cfg=None):
    async def erp_write_planner(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return {"messages": [AIMessage(
                content=(
                    "Tính năng ghi (tạo/sửa đơn hàng, cập nhật tồn kho) "
                    "chưa được kích hoạt trong phiên bản này."
                )
            )], "pending_action": None, "auto_chain": None}

        # Plan the action — invariant A: ONE effective system prompt; context
        # first so the JSON-format block stays last.
        wc = state.get("working_context")
        # planner_prompt = bản rút gọn theo vai (prompts.planner_prompt_for);
        # None = bản đầy đủ, giữ nguyên hành vi cũ cho test và vai admin.
        base_prompt = planner_prompt or WRITE_PLANNER_PROMPT
        system = (render_working_context(wc) + "\n\n" + base_prompt) \
            if wc else base_prompt
        plan = await _plan_json(llm, system, state["messages"])
        if plan is None:
            return {"messages": [AIMessage(content="Không thể xác định thao tác cần thực hiện. Vui lòng mô tả rõ hơn.")],
                    "pending_action": None, "auto_chain": None}

        # Invariant C tầng 2: mã tường minh trong lời user thắng context.
        last_human = next((m.content for m in reversed(state["messages"])
                           if m.type == "human"), "")
        plan = enforce_explicit_ref(plan, last_human)

        # Cổng vai TẤT ĐỊNH (Task 8 fix — live defect 2026-08-09): prompts.py
        # CHỈ dặn LLM từ chối bằng lời (planner_prompt_for), không có cách
        # nào biểu đạt "chỉ trả lời, không hành động" trong hợp đồng JSON bắt
        # buộc nêu tool — nên model bịa tool "other" và node cũ tạo
        # pending_action cho một cái tên không tồn tại, hỏi người dùng "xác
        # nhận" một sự từ chối (vô lý). Bảo đảm phải nằm ở CODE, không phải
        # prompt (đúng nguyên tắc §3 spec role-based-access — LLM không bao
        # giờ là nơi giữ ranh giới duy nhất). role_cfg=None (mọi caller cũ,
        # test, vai admin) → nhánh này không chạy, hành vi giữ y nguyên.
        handoff_note = None
        if role_cfg is not None:
            tool_name = plan.get("tool")
            if tool_name and role_cfg.state_of(tool_name) in (OTHER_DEPT, DENIED):
                # Bàn giao (spec 2026-08-13): thay vì để việc bốc hơi, dựng một
                # activity trên đúng chứng từ giao cho bộ phận có thẩm quyền.
                # log_activity NẰM TRONG WRITE_COORDINATORS nên chỉ cần thay
                # plan — coordinator lo tra chứng từ, kiểm loại, tra người nhận
                # và cổng xác nhận. Không thêm cơ chế nào.
                handoff = build_handoff(role_cfg, tool_name,
                                        plan.get("args") or {},
                                        plan.get("summary"))
                if handoff is None:
                    # SÀN: dựng không được thì giữ NGUYÊN hành vi cũ.
                    return {"messages": [AIMessage(
                        content=_role_refusal_message(role_cfg, tool_name)
                    )], "pending_action": None, "auto_chain": None}
                plan = handoff
                handoff_note = _handoff_notice(role_cfg, tool_name)
                duplicate = _duplicate_handoff(handoff)
                if duplicate is not None:
                    deadline = duplicate.get("date_deadline") or "chưa đặt"
                    return {"messages": [AIMessage(
                        content=(f"Việc này đã được chuyển cho bộ phận "
                                 f"{DEPT_OF.get(tool_name, 'khác')} rồi "
                                 f"(hạn {deadline}), chưa cần chuyển lại.")
                    )], "pending_action": None, "auto_chain": None}

        # Chuỗi đa bước khai báo trước: validate tất định qua registry walk.
        # LLM bịa chain_until → None → single-step như cũ (fail-safe).
        chain = expand_chain(plan.get("tool"), plan.get("chain_until"))

        # Cổng vai TẤT ĐỊNH cho TOÀN CHUỖI (final-review Fix 1, role-based-
        # access): cổng bên trên (dòng ~273) chỉ soi plan["tool"] — bước ĐẦU.
        # expand_chain() duyệt qua NEXT_STEPS mà KHÔNG hỏi role_cfg, nên một
        # chuỗi "giao hàng rồi xuất hóa đơn" của vai kho lọt qua cổng đầu
        # (deliver_order = own), quảng cáo bước cấm trong lời xác nhận, THỰC
        # SỰ giao hàng, và chỉ bị chặn ở executor khi tới create_invoice_from_
        # order — nửa chuỗi đã chạy, ranh giới không còn nằm ở CODE tất định
        # nữa mà trôi ra executor. Kiểm TOÀN BỘ bước còn lại TRƯỚC khi bất cứ
        # gì chạy; nếu có bước cấm, từ chối CẢ CHUỖI (không âm thầm cắt bớt —
        # người dùng hỏi 2 việc mà chỉ được 1 việc, không báo, còn tệ hơn bị
        # từ chối thẳng cả 2).
        # KHÔNG bàn giao ở nhánh này (final-review I4, 2026-08-14): một chuỗi
        # trộn bước được phép (vd deliver_order, own của vai kho) với bước
        # cấm (vd create_invoice_from_order, Kế toán) không rút gọn được
        # thành MỘT activity mà không nói dối — hoặc nội dung activity chỉ
        # nêu bước cấm (bên nhận không biết còn có bước own đi kèm mà chính
        # người dùng đã xin), hoặc giao luôn cả bước own cho bộ phận khác
        # (kế toán bị nhờ đi giao hàng — việc CỦA KHO, không phải của họ).
        # Nhánh tool ĐƠN ở trên không gặp vấn đề này vì chỉ có một tool, một
        # sự thật để nói. Từ chối cả chuỗi, y như trước khi có bàn giao.
        if role_cfg is not None and chain:
            for step_tool, _ in chain:
                if role_cfg.state_of(step_tool) in (OTHER_DEPT, DENIED):
                    return {"messages": [AIMessage(
                        content=_role_refusal_message(role_cfg, step_tool)
                    )], "pending_action": None, "auto_chain": None}

        auto_chain = [t for t, _ in chain] if chain else None
        if chain:
            plan = {**plan, "chain_note":
                    "\n\nSau đó tự động: " + " → ".join(l for _, l in chain)}

        # Coordinated writes own their own resolution + confirm; don't interrupt here.
        if plan.get("tool") in COORDINATED_TOOLS:
            out = {"pending_action": plan, "auto_chain": auto_chain}
            if handoff_note:
                out["messages"] = [AIMessage(content=handoff_note)]
            return out

        summary = plan.get("summary") or plan.get("tool") or "thao tác"
        # Invariant C tầng 3: hiện tool+args TẤT ĐỊNH — user luôn thấy ref thật
        # trước khi "có", kể cả khi summary của LLM mơ hồ.
        args_line = ", ".join(f"{k}={v}" for k, v in (plan.get("args") or {}).items())
        question = WRITE_CONFIRM_PREFIX + (f"**{summary}**\n"
                                           f"({plan.get('tool')}: {args_line})"
                                           f"{plan.get('chain_note') or ''}\n\n"
                                           + WRITE_CONFIRM_SUFFIX)
        ttl = int(os.environ.get("CONFIRMATION_TTL_SECONDS", "300"))
        confirmed = _interrupt({
            "question": question,
            "action": plan,
            "expires_at": time.time() + ttl,
        })
        return {"pending_action": plan, "confirmed": confirmed,
                "auto_chain": auto_chain}

    return erp_write_planner


# ── erp_write_executor ────────────────────────────────────────────────────────

def make_erp_write_executor_node(tools):
    """Execute the confirmed write by invoking the named tool directly.

    Security (write-gate, rate-limit) lives in the MCP gateway; domain
    validation lives in the tool. Here we only route + fail safe so a bad
    plan never crashes the graph.
    """
    by_name = {t.name: t for t in tools}

    async def erp_write_executor(state: ERPAgentState) -> dict:
        cleared = {"pending_action": None, "confirmed": None, "last_write": None}
        if not state.get("confirmed"):
            return {"messages": [AIMessage(content="Đã hủy thao tác.")], **cleared}

        action = state.get("pending_action") or {}
        name = action.get("tool")
        tool = by_name.get(name)
        if tool is None:
            return {"messages": [AIMessage(
                content=f"Thao tác '{name}' không khả dụng."
            )], **cleared}
        try:
            result = await tool.ainvoke(action.get("args") or {})
        except Exception:
            # logger.exception ghi nguyên văn lỗi + traceback vào logger tiến
            # trình (đã đủ vệt kiểm toán); content trả người dùng phải sạch
            # — không đi qua fail_write vì **cleared phải sống sót nguyên vẹn
            # trong dict trả về, và fail_write không biết về nó.
            logger.exception("write executor failed: tool=%s", name)
            return {"messages": [AIMessage(
                content="Lỗi khi thực hiện thao tác — thao tác chưa được "
                        "thực hiện. Nếu lặp lại, báo quản trị viên."
            )], **cleared}
        display, env = parse_write_result(result)
        upd = {"messages": [AIMessage(content=display)],
               "pending_action": None, "confirmed": None,
               "last_write": {"tool": name, **env} if env else None}
        wc = derive_working_context(env)
        if wc:
            # omit-vs-None: chỉ THÊM key khi có đơn mới — không bao giờ set None
            # (None sẽ xoá đơn đang nhớ; các path khác cũng phải OMIT key này).
            upd["working_context"] = wc
        return upd

    return erp_write_executor
