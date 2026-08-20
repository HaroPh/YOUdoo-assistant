# backend/src/agents/erp_agent.py
import os
import uuid
import time

from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from langgraph.errors import GraphRecursionError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .graph import build_graph
from .confirmation import CONFIRM, UNCLEAR, classify_confirmation
from .disambiguation import parse_selection
from .language import EN, VI, detect_lang
from .localize import localize
from .models import make_llms
from . import roles as roles_mod
from .user_memory import (extract_memory_markers, forget_fact, is_document_code,
                          normalize_key, save_fact)
from src.llm import tracing

MCP_ODOO_URL = os.environ.get("MCP_ODOO_URL", "http://localhost:8003/sse")
PG_CONN      = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:changeme@localhost:5433/ai_assistant",
)
RECURSION_MSG = ("Yêu cầu này chạy quá số bước xử lý cho phép nên đã được "
                 "dừng an toàn. Nếu bạn vừa yêu cầu một thao tác ghi, hãy "
                 "kiểm tra lại trạng thái đơn trước khi thử lại.")

# Công bố do CODE chèn, KHÔNG giao cho model nhớ: ghi âm thầm đúng là thứ cần
# tránh, mà model thì có lượt sẽ quên nói (spec §7).
MEMORY_NOTICE_PREFIX = "📝 Đã ghi nhớ:"
MEMORY_BLOCKED_PREFIX = "⚠️ Không ghi nhớ:"


def _question_from_interrupts(interrupts) -> str | None:
    """Pull the confirmation question out of a tuple of Interrupt objects."""
    for it in interrupts or ():
        value = getattr(it, "value", None)
        if isinstance(value, dict) and value.get("question"):
            return value["question"]
    return None


def _pending_question(snapshot) -> str | None:
    """Question of the interrupt a parked thread is currently waiting on."""
    for task in getattr(snapshot, "tasks", ()) or ():
        question = _question_from_interrupts(getattr(task, "interrupts", ()))
        if question:
            return question
    return None


def _pending_expiry(snapshot) -> float | None:
    """Epoch-seconds expiry of the interrupt a parked thread waits on, or None."""
    for task in getattr(snapshot, "tasks", ()) or ():
        for it in getattr(task, "interrupts", ()) or ():
            value = getattr(it, "value", None)
            if isinstance(value, dict) and "expires_at" in value:
                return value["expires_at"]
    return None


def _is_parked(snapshot) -> bool:
    """Is the thread waiting on the user (a pending interrupt)? Check the pending
    interrupt directly, not just `snapshot.next`: after resuming one interrupt and
    hitting a SECOND in the same node (disambiguation → confirm), LangGraph leaves
    `snapshot.next` empty while the confirm interrupt is still pending — so relying
    on `next` alone drops the user's confirm into the fresh-request path."""
    return bool(_pending_question(snapshot)) or bool(getattr(snapshot, "next", None))


def _pending_kind(snapshot) -> str | None:
    """Kind of the interrupt a parked thread waits on: 'confirm'|'disambiguation'."""
    for task in getattr(snapshot, "tasks", ()) or ():
        for it in getattr(task, "interrupts", ()) or ():
            value = getattr(it, "value", None)
            if isinstance(value, dict) and value.get("question"):
                return value.get("kind", "confirm")
    return None


def _pending_options(snapshot) -> list:
    """Candidate options of a parked option-bearing interrupt (else []).

    "next_action" is no longer produced by continuation.py (round 7: the
    blocking next-step menu was replaced by a non-blocking suggestion) —
    kept here so a conversation checkpointed mid-menu BEFORE that deploy
    still resumes correctly instead of erroring. Safe to delete once no
    such in-flight checkpoint can remain (e.g. after the checkpointer's
    retention window has passed)."""
    for task in getattr(snapshot, "tasks", ()) or ():
        for it in getattr(task, "interrupts", ()) or ():
            value = getattr(it, "value", None)
            if isinstance(value, dict) and value.get("kind") in (
                    "disambiguation", "next_action"):
                return value.get("options") or []
    return []


async def _decide_resume(kind, options, question, reply, llm):
    """Turn the user's reply into a resume Command, or a re-ask string.

    disambiguation → parse the selection (deterministic) → resume the chosen id;
    next_action → parse the menu pick (ids are booleans; False = "Dừng" is a
    valid pick, so compare `is not None`) with a yes/no fallback;
    free_text → resume the raw reply unchanged, no classification at all
    (SOP-skill checkpoints needing an open-ended answer, e.g. a counted
    quantity — coercing it through the yes/no classifier would destroy it);
    confirm (or unspecified) → classify yes/no → resume a bool. Ambiguous → re-ask."""
    if kind == "disambiguation":
        chosen = parse_selection(reply, options)
        if chosen is None:
            return question or "Vui lòng chọn một mục trong danh sách."
        return Command(resume=chosen)
    if kind == "next_action":
        # No longer produced going forward (round 7) — see _pending_options.
        chosen = parse_selection(reply, options)
        if chosen is not None:
            return Command(resume=chosen)
        verdict = await classify_confirmation(reply, llm)
        if verdict == UNCLEAR:
            return question or "Bạn muốn tiếp tục hay dừng? (chọn một mục hoặc có/không)"
        return Command(resume=verdict == CONFIRM)
    if kind == "free_text":
        return Command(resume=reply)
    verdict = await classify_confirmation(reply, llm)
    if verdict == UNCLEAR:
        return question or "Bạn xác nhận thực hiện thao tác này? (có / không)"
    return Command(resume=verdict == CONFIRM)


def _filter_tools_for_role(tools, cfg):
    """Lọc tool xuống tập vai được phép. None = không lọc (vai admin).

    Đây là lớp UX/độ-chính-xác, KHÔNG phải lớp bảo mật: LLM chỉ thấy tool liên
    quan nên chọn đúng hơn (dự án đo tool_acc/dangerous_misroute). Lớp cưỡng
    chế thật là tài khoản Odoo của tiến trình MCP tương ứng — nếu bộ lọc này
    có bug, Odoo vẫn chặn."""
    allowed = cfg.allowed_tools()
    if allowed is None:
        return list(tools)
    return [t for t in tools if t.name in allowed]


class ERPAgent:
    def __init__(self) -> None:
        self.graphs: dict = {}
        self.tool_names: list[str] = []
        self._pool = None
        self._llms = None
        self._checkpointer = None
        self._handler = None

    async def setup(self) -> None:
        self._handler = tracing.get_handler()
        self._llms = make_llms()

        self._pool = AsyncConnectionPool(
            conninfo=PG_CONN,
            max_size=20,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await self._pool.open()
        checkpointer = AsyncPostgresSaver(self._pool)
        await checkpointer.setup()  # creates checkpoint tables if not present
        self._checkpointer = checkpointer

        # MỘT graph mỗi vai. llms/pool/checkpointer DÙNG CHUNG nên 3 graph gần
        # như không tốn thêm bộ nhớ; chỉ tool khác nhau. Mỗi vai nối tới tiến
        # trình MCP riêng — tiến trình đó nắm credential Odoo của vai, nên nó
        # KHÔNG THỂ làm việc ngoài quyền dù graph có gọi nhầm.
        self.graphs = {}
        for role_name, cfg in roles_mod.load_profile().items():
            client = MultiServerMCPClient(
                {"odoo": {"url": cfg.mcp_url, "transport": "sse"}}
            )
            # raw_tools = registry MCP ĐẦY ĐỦ (chưa lọc) — cần giữ lại tách
            # biệt với `tools` (đã lọc theo vai) để build_graph phân biệt
            # được "tool bị lọc vì chính sách vai" (skip skill) khỏi "tool
            # không tồn tại trong registry MCP ở bất kỳ đâu" (lỗi cấu hình
            # thật, vẫn phải SkillManifestError) — xem skill_loader.skill_role_gap.
            raw_tools = await client.get_tools()
            tools = _filter_tools_for_role(raw_tools, cfg)
            if role_name == "admin":
                self.tool_names = [t.name for t in tools]
            self.graphs[role_name] = build_graph(self._llms, tools, checkpointer,
                                                 role_cfg=cfg, mcp_all_tools=raw_tools)

    async def chat(self, messages: list[dict], thread_id: str | None = None,
                   reset_if_fresh: bool = False, role: str = "admin",
                   user_id: str | None = None) -> str:
        """Lớp bọc: chạy lượt chat, áp marker ký ức, rồi đưa câu trả lời qua localize.

        Bọc thay vì vá từng `return`: _chat_inner có SÁU đường ra (câu nhắc
        nhập, từ chối vai, hỏi-lại, RECURSION_MSG, question của interrupt,
        message cuối) và những đường thêm sau này sẽ không ai nhớ vá.

        Ký ức chạy TRƯỚC localize (xem _apply_memory_markers) để bản dịch
        không làm hỏng marker, và để dòng công bố cũng được dịch cho người
        dùng tiếng Anh.

        `lang` suy từ TOÀN BỘ tin nhắn người dùng trong lượt này, không chỉ tin
        nhắn mới nhất: lượt trả lời xác nhận thường chỉ là "yes"/"1" — quá ngắn
        để nhận diện. Client thật (Open WebUI) gửi đủ lịch sử mỗi lượt, nên câu
        hỏi tiếng Anh mở đầu vẫn nằm trong `messages` và quyết đúng ngôn ngữ.

        Chỉ cần MỘT tin nhắn tiếng Anh là cả lượt tính là "en": detect_lang đã
        fail an toàn về "vi" (đòi có hư từ tiếng Anh VÀ không có dấu tiếng
        Việt), nên một chữ lạc không đủ kích hoạt.

        GIỚI HẠN CÒN LẠI, có ghi: client script chỉ gửi đúng một tin nhắn mỗi
        lượt (kiểu `{"session_id": ..., "messages": [{"role": "user",
        "content": "yes"}]}`) sẽ mất ngôn ngữ ở lượt xác nhận → rơi về "vi".
        Đó là chiều an toàn (giữ đúng hành vi hôm nay), không phải lỗi.

        KHÔNG BAO GIỜ để lớp dịch làm hỏng một lượt chat: mọi lỗi → câu gốc.
        """
        answer = await self._chat_inner(messages, thread_id=thread_id,
                                        reset_if_fresh=reset_if_fresh,
                                        role=role)
        answer = await self._apply_memory_markers(answer, user_id, thread_id)
        lang = VI
        for m in messages or []:
            if m.get("role") == "user" and detect_lang(m.get("content")) == EN:
                lang = EN
                break
        try:
            return await localize(answer, lang, self._llms["evaluator"])
        except Exception:                                   # noqa: BLE001
            return answer

    async def _apply_memory_markers(self, answer: str, user_id: str | None,
                                    thread_id: str | None) -> str:
        """Bóc marker, ghi ký ức, chèn dòng công bố. KHÔNG BAO GIỜ ném.

        Chạy TRƯỚC localize() để bản dịch không làm hỏng marker, và để dòng
        công bố cũng được dịch cho người dùng tiếng Anh.

        Marker luôn bị cắt kể cả khi không ghi được (thiếu user_id, DB lỗi,
        cổng phủ quyết chặn) — ký hiệu máy-đọc không bao giờ được lọt ra câu
        người dùng đọc.
        """
        clean, saves, forgets = extract_memory_markers(answer)
        if not saves and not forgets:
            return clean
        notices: list[str] = []
        try:
            for raw_key, value in saves:
                key = normalize_key(raw_key)
                if not key:
                    continue
                if is_document_code(value):
                    notices.append(f"{MEMORY_BLOCKED_PREFIX} {key} — ký ức chỉ "
                                   "giữ quy ước, không giữ mã chứng từ cụ thể.")
                    continue
                if user_id:
                    await save_fact(self._pool, user_id, key, value, thread_id)
                    notices.append(f'{MEMORY_NOTICE_PREFIX} {key} = {value} '
                                   '— nói "quên đi" nếu sai.')
            for raw_key in forgets:
                key = normalize_key(raw_key)
                if key and user_id and await forget_fact(self._pool, user_id, key):
                    notices.append(f"🗑️ Đã bỏ ghi nhớ: {key}")
        except Exception:                                   # noqa: BLE001
            return clean
        return "\n\n".join([clean, *notices]) if notices else clean

    async def _chat_inner(self, messages: list[dict], thread_id: str | None = None,
                          reset_if_fresh: bool = False, role: str = "admin") -> str:
        """
        messages: list of {"role", "content"} dicts (user/assistant).
        thread_id: stable ID per conversation — needed for interrupt/resume.
                   Defaults to a fresh UUID (safe when write gate is locked).
        reset_if_fresh: opt-in (R7): when the caller DERIVED thread_id from a
                   full-history client (Open WebUI headers / sha1 of the first
                   message), a single-user-message turn means a brand-new
                   conversation — wipe whatever an OLDER conversation parked
                   under the same thread id and skip the resume branch. Leave
                   False for clients that manage their own session_id and send
                   single-message resume turns ("có").
        """
        if not messages:
            return "Vui lòng nhập câu hỏi."

        graph = self.graphs.get(role)
        if graph is None:
            return "Không xác định được quyền truy cập của bạn. Liên hệ quản trị viên."

        tid = thread_id or uuid.uuid4().hex
        config = {"configurable": {"thread_id": tid}}
        if self._handler:
            config["callbacks"] = [self._handler]

        is_fresh = (reset_if_fresh and thread_id is not None
                    and len(messages) == 1 and messages[0].get("role") == "user")
        try:
            if is_fresh:
                await self._checkpointer.adelete_thread(tid)
                result = await self._invoke_fresh(messages, config, graph)
            else:
                # If the thread is parked at a write-confirmation interrupt, this
                # turn is the user's answer — classify it and resume instead of
                # starting over.
                snapshot = await graph.aget_state(config)
                if _is_parked(snapshot):
                    expires_at = _pending_expiry(snapshot)
                    if expires_at is not None and time.time() > expires_at:
                        # Stale confirmation: discard it (resume=False is a no-op
                        # write, result ignored) and process this turn as fresh.
                        await graph.ainvoke(Command(resume=False), config=config)
                        result = await self._invoke_fresh(messages, config, graph)
                    else:
                        reply = messages[-1]["content"]
                        decision = await _decide_resume(
                            _pending_kind(snapshot), _pending_options(snapshot),
                            _pending_question(snapshot), reply, self._llms["evaluator"])
                        if isinstance(decision, str):
                            # Unclear reply: re-ask, leave the thread parked.
                            return decision
                        result = await graph.ainvoke(decision, config=config)
                else:
                    result = await self._invoke_fresh(messages, config, graph)
        except GraphRecursionError:
            # Spike v10b 2026-07-16: subgraph-as-node KHÔNG bị chặn bởi
            # default 25 — trần thật đến từ with_config tại graph wiring.
            # Chạm trần (agentic skill loop, hoặc erp_read tự loop) → câu
            # trả lời lịch sự thay vì rơi vào catch-all generic của main.py.
            return RECURSION_MSG

        # A write planner that called interrupt() surfaces as "__interrupt__" with
        # no final AI message — return its confirmation question to the user.
        question = _question_from_interrupts(result.get("__interrupt__"))
        if question:
            return question

        return result["messages"][-1].content.strip()

    async def answer_stateless(self, content: str) -> str:
        """Answer a single prompt with no thread/checkpoint state at all.

        R7 hotfix (live-verify 2026-07-09): Open WebUI's own background task
        calls (title/tags/follow-up/query generation) share the same chat
        identity as real user turns, so routing them through chat() would
        risk wiping a real parked confirm (main.py's _is_owui_task_prompt
        routes them here instead).

        Deliberately uses the "synthesis" role, NOT "chitchat": Open WebUI's
        task prompts embed recent conversation history to generate relevant
        titles/follow-ups, which may include real ERP data (prices, customer
        names) produced by the read/synthesis roles earlier in the
        conversation.

        Post-SP-1 correction (docstring only — the role choice below is
        unchanged): the mechanism this comment used to cite no longer exists.
        The old models.py enforced CLOUD_ALLOWED = {"router", "evaluator",
        "chitchat"} at the call layer — model_for() failed closed for any
        role outside that set, so "read"/"synthesis" were ALWAYS local by
        construction and "chitchat" was cloud-eligible on the premise it only
        ever saw raw user text. SP-1 removed Ollama from the chat path
        entirely; agents/models.py is now a thin facade over
        llm/router.py (Task 8), and EVERY role — including "chitchat" —
        routes through the same cloud gateway. There is no longer a role that
        is "always local by construction", so the original privacy-boundary
        rationale for preferring "synthesis" here no longer holds as stated.
        "synthesis" is kept anyway because its model chain (catalog.py) is
        tuned for longer, data-bearing completions rather than short
        chitchat replies, which fits Open WebUI's task-prompt payloads
        better — but if a real privacy boundary between roles matters again
        (e.g. once this system carries non-demo data), this choice needs a
        fresh look rather than resting on the stale CLOUD_ALLOWED premise.
        """
        config = {"callbacks": [self._handler]} if self._handler else None
        response = await self._llms["synthesis"].ainvoke(
            [HumanMessage(content=content)], config=config)
        return response.content

    async def _invoke_fresh(self, messages: list[dict], config: dict, graph):
        """Run a non-resume turn, overwriting the persisted message channel.

        Open WebUI resends the full conversation every turn, so appending it to
        the checkpointer (the add_messages default) duplicates history without
        bound. Prepending RemoveMessage(REMOVE_ALL_MESSAGES) clears the channel
        first, leaving state["messages"] == exactly the incoming history.

        `graph` is REQUIRED (final-review Fix 4, role-based-access): the old
        `graph or self.graphs["admin"]` fallback was dead on every current call
        site (all three pass graph explicitly, already resolved+None-checked by
        the caller), but in a permission system a latent "if unspecified, use
        admin" defaults open — the wrong direction. Fail loudly instead.
        """
        if graph is None:
            raise ValueError("_invoke_fresh: graph is required (no admin fallback)")
        reset = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]
        return await graph.ainvoke({"messages": reset}, config=config)

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
