"""Test tích hợp — cần Postgres đang chạy.

Chạy:  pytest tests/agents/test_write_suggestion_checkpoint.py -m integration -v
Bỏ:    pytest -m "not integration"

VÌ SAO PHẢI LÀ INTEGRATION TEST, KHÔNG PHẢI UNIT TEST MOCK: state.py ghi rõ
bài học SP-1C2 — có loại lỗi CHỈ hỏng khi checkpointer Postgres thật chạy
(dữ liệu không JSON-thuần đi qua sạch mọi unit test rồi hỏng trên production).
Cơ chế "đề xuất ghi" dựa vào việc cờ sống sót vòng lưu/đọc checkpoint GIỮA HAI
LƯỢT, nên phải đo bằng Postgres thật.

VÀ VÌ SAO PHẢI ĐI QUA ĐÚNG KHUÔN `_invoke_fresh`: bản đầu của test này chỉ
invoke MỘT lượt rồi `graph.aget_state()` đọc lại — chứng minh additional_kwargs
sống sót vòng lưu/đọc, đúng nhưng LẠC ĐỀ, nên nó pass trong khi cơ chế hỏng
hoàn toàn ngoài đời. Thứ giết cờ cũ không phải checkpointer mà là
`erp_agent._invoke_fresh`: nó chạy trên MỌI lượt không parked và ghi đè NGUYÊN
kênh "messages" bằng history text thuần client gửi lên
(`[RemoveMessage(REMOVE_ALL_MESSAGES), *messages]`, với messages đã bị
`main.py._filter_messages` lược còn {"role","content"}). Các test dưới đây vì
thế BẮT BUỘC gọi lại đúng khuôn đó, nhiều lượt liên tiếp, trên cùng thread_id.
"""
import os
import sys
import uuid

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.agents.erp_agent import ERPAgent
from src.agents.state import ERPAgentState
from src.agents.routing import replying_to_write_suggestion

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")

GOI_Y = "Chỉ có Acme Corporation. Bạn có muốn tôi tạo đơn mua không?"
TRA_LOI_THUONG = "Chính sách cho phép hoàn hàng trong 30 ngày."


def _skip_guard():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    if sys.platform == "win32":
        # psycopg3 async KHÔNG chạy trên ProactorEventLoop (xem backend/run.py).
        import asyncio
        if not isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
            pytest.skip("cần SelectorEventLoop trên Windows")


def _pool():
    # min_size tường minh: psycopg_pool (>=3.2) mặc định min_size=4, và
    # min_size > max_size ném ValueError NGAY TẠI __init__, trước khi kịp chạm
    # Postgres.
    return AsyncConnectionPool(
        conninfo=DSN, min_size=1, max_size=2, open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0,
                "row_factory": dict_row})


async def _invoke_fresh(graph, messages: list[dict], config: dict):
    """Gọi THẲNG erp_agent.ERPAgent._invoke_fresh THẬT — không giữ bản sao.

    Bản sao từng có ở đây (docstring tự nhận "BẢN SAO NGUYÊN VĂN") đã LỆCH
    khỏi production: production thêm `"user_memory": memory_block` vào
    payload ainvoke (đợt ký ức xuyên phiên L2) mà bản sao không hề cập nhật
    theo — đúng cảnh báo đầu file "test mà đi đường khác thì không đo gì cả",
    lần này áp lên chính test này. Gọi thẳng hàm thật để KHÔNG CÒN đường nào
    lệch được nữa.

    `self=None` an toàn: thân hàm `_invoke_fresh` không hề đụng tới `self`
    (không đọc self._pool, self._llms, ...), chỉ dùng đúng bốn tham số
    messages/config/graph/memory_block — xác nhận bằng đọc mã nguồn, không
    phải giả định. `messages` vẫn là list dict thuần {"role","content"} như
    main.py._filter_messages trả ra, giữ nguyên khuôn gọi thật.
    """
    return await ERPAgent._invoke_fresh(None, messages, config, graph)


def _u(text: str) -> dict:
    return {"role": "user", "content": text}


def _a(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _last_human_text(state) -> str:
    return next((m.content for m in reversed(state["messages"])
                 if m.type == "human"), "")


def _build_graph(cp, verdicts, flags, de_xuat_khi: set, new_msgs_fn=None):
    """Graph tối thiểu nhưng ĐÚNG THỨ TỰ của graph thật:

        START ─► router ─► answer ─► END

    `router` đứng đúng chỗ decide_route đứng (chạy TRƯỚC node trả lời, đọc
    state của lượt này) và ghi lại phán quyết replying_to_write_suggestion —
    đây mới là phép đo thật, không phải đọc state sau khi mọi thứ đã xong.

    `answer` bắt chước fuse_answer/erp_read: CHỈ ghi cặp key cờ khi lượt đó
    thật sự có đề xuất ghi. Lượt khác trả về ĐÚNG {"messages": ...} — giống
    rag_node/chitchat/respond_unknown ngoài đời, tức KHÔNG node nào dọn cờ hộ.
    Đó là điều kiện để test tính tự-hết-hạn của neo cho ra kết quả có nghĩa.
    """
    async def router(state):
        verdicts.append(replying_to_write_suggestion(state))
        flags.append((state.get("suggested_write"),
                      state.get("suggested_write_at"),
                      len(state["messages"])))
        return {}

    async def answer(state):
        text = _last_human_text(state)
        if text not in de_xuat_khi:
            return {"messages": [AIMessage(content=TRA_LOI_THUONG)]}
        new_msgs = new_msgs_fn() if new_msgs_fn else [AIMessage(content=GOI_Y)]
        # Neo đếm theo cái NGƯỜI DÙNG THẤY: history vào + ĐÚNG 1 câu trả lời
        # (erp_agent.chat() chỉ trả về messages[-1].content), KHÔNG phải độ dài
        # kênh nội bộ sau khi node ghi xong.
        return {"messages": new_msgs,
                "suggested_write": True,
                "suggested_write_at": len(state["messages"]) + 1}

    g = StateGraph(ERPAgentState)
    g.add_node("router", router)
    g.add_node("answer", answer)
    g.add_edge(START, "router")
    g.add_edge("router", "answer")
    g.add_edge("answer", END)
    return g.compile(checkpointer=cp)


async def test_co_song_sot_qua_dung_khuon_invoke_fresh_hai_luot():
    """Ca gốc: lượt 1 đề xuất ghi, lượt 2 user trả lời "okay" → phủ quyết BẬT.

    Cơ chế cũ (cờ trên AIMessage.additional_kwargs) trả False ở đây vì lượt 2
    dựng lại toàn bộ messages từ text thuần.
    """
    _skip_guard()
    pool = _pool()
    await pool.open()
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()
        verdicts, flags = [], []
        graph = _build_graph(cp, verdicts, flags, {"tôi muốn nhập 20 cái"})

        tid = "test-write-suggest-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": tid}}

        # LƯỢT 1 — client chỉ có 1 message
        await _invoke_fresh(graph, [_u("tôi muốn nhập 20 cái")], config)
        # LƯỢT 2 — client GỬI LẠI history dạng text thuần + câu trả lời mới
        await _invoke_fresh(
            graph, [_u("tôi muốn nhập 20 cái"), _a(GOI_Y), _u("okay")], config)

        assert verdicts == [False, True], f"verdicts={verdicts} flags={flags}"

        # cờ + neo thật sự nằm trong checkpoint Postgres (không phải in-memory)
        snap = await graph.aget_state(config)
        assert snap.values["suggested_write"] is True
        assert snap.values["suggested_write_at"] == 2

        await cp.adelete_thread(tid)
    finally:
        await pool.close()


async def test_co_khong_ro_ri_sang_luot_xa_hon_nho_neo_do_dai():
    """Chống rò rỉ: lượt 1 đề xuất ghi → lượt 2 là một lượt KHÁC hoàn toàn
    (node trả lời thường, KHÔNG dọn cờ) → lượt 3 user gõ "ok".

    Phủ quyết PHẢI TẮT ở lượt 3. Test cũng khẳng định cờ vẫn còn True trong
    checkpoint lúc đó — tức thứ cứu ta là NEO ĐỘ DÀI, không phải một cú dọn
    dẹp tình cờ ở đâu đó.
    """
    _skip_guard()
    pool = _pool()
    await pool.open()
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()
        verdicts, flags = [], []
        graph = _build_graph(cp, verdicts, flags, {"tôi muốn nhập 20 cái"})

        tid = "test-write-suggest-stale-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": tid}}

        await _invoke_fresh(graph, [_u("tôi muốn nhập 20 cái")], config)
        await _invoke_fresh(
            graph, [_u("tôi muốn nhập 20 cái"), _a(GOI_Y),
                    _u("chính sách hoàn hàng thế nào?")], config)
        await _invoke_fresh(
            graph, [_u("tôi muốn nhập 20 cái"), _a(GOI_Y),
                    _u("chính sách hoàn hàng thế nào?"), _a(TRA_LOI_THUONG),
                    _u("ok")], config)

        assert verdicts == [False, False, False], \
            f"verdicts={verdicts} flags={flags}"
        # cờ CHƯA HỀ được dọn — neo mới là thứ làm nó hết hạn
        assert flags[-1] == (True, 2, 5), f"flags={flags}"

        await cp.adelete_thread(tid)
    finally:
        await pool.close()


async def test_neo_dung_cho_ca_duong_erp_read_nhieu_message():
    """erp_read (ReAct) phụ THÊM NHIỀU message trong một lượt (ai-tool-call,
    tool-result, câu trả lời) — nhưng client chỉ nhận lại ĐÚNG MỘT message.

    Đây là lý do neo phải đếm theo cái người dùng thấy. Neo theo độ dài kênh
    nội bộ (len(state["messages"]) + len(new_msgs) = 4 ở đây) sẽ không bao giờ
    khớp ở lượt sau (len = 3), tức đường erp_read sẽ im lặng không bao giờ bắn
    phủ quyết — đúng lớp lỗi mà fix wave này đang đóng lại.
    """
    _skip_guard()
    pool = _pool()
    await pool.open()
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()
        verdicts, flags = [], []

        def _react_msgs():
            return [
                AIMessage(content="", tool_calls=[
                    {"name": "search_suppliers", "args": {"q": "workplace"},
                     "id": "call_1"}]),
                ToolMessage(content="Acme Corporation", tool_call_id="call_1"),
                AIMessage(content=GOI_Y),
            ]

        graph = _build_graph(cp, verdicts, flags, {"tôi muốn nhập 20 cái"},
                             new_msgs_fn=_react_msgs)

        tid = "test-write-suggest-react-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": tid}}

        await _invoke_fresh(graph, [_u("tôi muốn nhập 20 cái")], config)
        snap = await graph.aget_state(config)
        # kênh nội bộ dài 4, nhưng neo là 2 (history vào 1 + 1 câu trả lời)
        assert len(snap.values["messages"]) == 4
        assert snap.values["suggested_write_at"] == 2

        await _invoke_fresh(
            graph, [_u("tôi muốn nhập 20 cái"), _a(GOI_Y), _u("ok")], config)
        assert verdicts == [False, True], f"verdicts={verdicts} flags={flags}"

        await cp.adelete_thread(tid)
    finally:
        await pool.close()


async def test_luot_chat_that_nap_khoi_ky_uc_that_vao_system_prompt():
    """Finding 4 (final review, trước merge): KHÔNG ca nào (1822 unit + 44
    integration) từng lái qua ERPAgent._chat_inner's `if user_id:` block VÀ
    ERPAgent._invoke_fresh's `memory_block` argument bằng một graph THẬT —
    mọi test ký ức khác đều mock thẳng `_chat_inner` (test_chat_memory.py)
    hoặc set `state["user_memory"]` tay (test_memory_injection.py). Xoá
    nguyên khối `if user_id:` trong erp_agent.py thì CẢ HAI bộ test đó vẫn
    xanh — đúng lớp lỗi ký ức "ghi được nhưng không bao giờ đọc lại" mà
    branch này đã phải vá một lần rồi (xem test_user_memory_postgres.py
    docstring).

    Dựng graph THẬT qua build_graph (không phải graph tối thiểu router/answer
    ở trên) để _chat_inner đi đúng đường sản xuất: intent_router → decide_route
    → respond_unknown. Router LLM script cứng về "unknown" (quyết định TẤT
    ĐỊNH ở decide_route, không cần model thật phân loại đúng); chitchat LLM là
    spy bắt system prompt thật sự gửi đi — cùng idiom SpyLLM của
    test_memory_injection.py. user_id là uuid4 riêng của test, KHÔNG đụng dữ
    liệu người thật; dọn lại chính hàng đã seed ở finally.
    """
    _skip_guard()
    from unittest.mock import MagicMock

    from src.agents.graph import build_graph
    from src.agents.user_memory import save_fact
    from src.llm.catalog import ROLES

    pool = _pool()
    await pool.open()
    user_id = "test-memory-read-" + uuid.uuid4().hex[:12]
    tid = "test-memory-read-" + uuid.uuid4().hex[:8]
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()

        await save_fact(pool, user_id, "do_dai_tra_loi", "ngan gon", "seed")

        class _RouterLLM:
            async def ainvoke(self, messages, config=None):
                return AIMessage(content="intent: unknown")

        class _ChitchatSpy:
            def __init__(self):
                self.system_prompts: list[str] = []

            async def ainvoke(self, messages, config=None):
                for m in messages:
                    if m.type == "system":
                        self.system_prompts.append(m.content)
                return AIMessage(content="Chao ban.")

        llms = {role: MagicMock(name=role) for role in ROLES}
        llms["router"] = _RouterLLM()
        chitchat = _ChitchatSpy()
        llms["chitchat"] = chitchat

        # mcp_all_tools=None (mặc định) — chứ KHÔNG phải [] — để
        # tools_for_coordinator trả nguyên `tools` (đường "vai admin" của nó)
        # thay vì ném ValueError khi thấy registry MCP rỗng: xem docstring.
        graph = build_graph(llms, tools=[], checkpointer=cp, role_cfg=None)

        agent = ERPAgent.__new__(ERPAgent)  # bỏ __init__ (cần MCP thật)
        agent._pool = pool
        agent._llms = {"evaluator": MagicMock()}
        agent.graphs = {"admin": graph}
        agent._checkpointer = cp
        agent._handler = None

        out = await agent.chat([{"role": "user", "content": "chao ban"}],
                               thread_id=tid, role="admin", user_id=user_id)

        assert chitchat.system_prompts, "respond_unknown không hề gọi LLM"
        assert any("do_dai_tra_loi = ngan gon" in p for p in chitchat.system_prompts), \
            chitchat.system_prompts
        assert "Chao ban" in out

        await cp.adelete_thread(tid)
    finally:
        async with pool.connection() as conn:
            await conn.execute(
                "DELETE FROM user_memory WHERE user_id = %s", (user_id,))
        await pool.close()
