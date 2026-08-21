"""
FastAPI backend — OpenAI-compatible API bọc ERP agent.
Open WebUI nối vào endpoint /v1 này như một "model" (erp-assistant).

Chạy (host, cần mcp-odoo SSE :8003 đang chạy):
    cd backend
    python run.py
"""
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.agents.erp_agent import ERPAgent
from src.agents import roles as roles_mod

logger = logging.getLogger(__name__)

from src.llm.catalog import (MODEL_CHON_DUOC, MODEL_MAC_DINH,
                             MODEL_NGUOI_DUNG_CHON)
from src.llm.router import THUNG_FALLBACK

MODEL_ID = "erp-assistant"
ERROR_MSG = "Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu. Vui lòng thử lại."
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent = ERPAgent()
    await agent.setup()
    _state["agent"] = agent
    print(f"✓ ERP agent ready — tools: {agent.tool_names}")
    yield
    agent = _state.get("agent")
    if agent is not None:
        await agent.aclose()
    _state.clear()


app = FastAPI(title="ERP AI Assistant Backend", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": "agent" in _state}


@app.get("/v1/models")
async def list_models():
    """Liệt kê model cho dropdown của Open WebUI.

    Dropdown ĐÃ CÓ SẴN ở client — trước đây endpoint này trả đúng một mục nên
    nó vô dụng, và trường `model` trong request không ai đọc. Liệt kê lựa chọn
    thật ở đây là toàn bộ phần "giao diện" của tính năng chọn model.

    Tên hiển thị là TÊN MODEL THẬT, không phải nhãn sản phẩm kiểu "Nhanh /
    Chính xác": nhãn như thế là lời hứa về KẾT QUẢ mà chưa ai đo, còn mục đích
    của việc cho chọn chính là để biết model nào đang trả lời.

    `MODEL_ID` giữ nguyên ở đầu danh sách để mọi client cũ (và mọi cấu hình
    Open WebUI đang trỏ vào nó) không gãy — nó nghĩa là "dùng mặc định".
    """
    created = int(time.time())
    ids = (MODEL_ID, *MODEL_CHON_DUOC)
    return {"object": "list", "data": [
        {"id": i, "object": "model", "created": created, "owned_by": "erp-ai"}
        for i in ids
    ]}


def _filter_messages(messages: list[dict]) -> list[dict]:
    """Bỏ system (đã có baked prompt), giữ user/assistant để multi-turn."""
    return [{"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant") and m.get("content")]


def _explicit_session(body: dict) -> bool:
    """Did the client supply its own session id (body session_id/id)?

    Such clients manage their own conversation state and may send
    single-message resume turns — never enable fresh-reset for them.
    """
    return bool(body.get("session_id") or body.get("id"))


_OWUI_TASK_PREFIX = "### Task:\n"


def _is_owui_task_prompt(messages: list[dict]) -> bool:
    """Is this Open WebUI's own background auto-generation call (title/tags/
    follow-up/query generation), not a real user turn?

    R7 hotfix (live-verify 2026-07-09, spec §8): these calls carry the SAME
    x-openwebui-chat-id/-user-id headers as real user turns and are always a
    single user message with no session_id — indistinguishable from a real
    "fresh conversation" by headers alone, which would wipe a real parked
    confirm via the fresh-reset in ERPAgent.chat. Open WebUI's task prompts
    use this stable internal template prefix INCLUDING the newline (confirmed
    2026-07-09 against a live instance, twice, both with "\n" immediately
    after "Task:") — the newline narrows the (already unlikely) false-positive
    where a real user's opener happens to start with "### Task:".

    Residual risks (spec §8): an admin who customizes Open WebUI's task
    prompt templates (Admin Settings) silently defeats this check and
    reopens the original bug with no warning; a real user's first message
    starting with this exact prefix+newline is silently answered without
    the ERP agent (no state is wiped either way — see spec §8).
    """
    return (len(messages) == 1 and messages[0].get("role") == "user"
            and (messages[0].get("content") or "").startswith(_OWUI_TASK_PREFIX))


def _role_from_headers(headers):
    """Suy vai từ tài khoản đăng nhập Open WebUI.

    CHỈ đọc x-openwebui-user-id (chuỗi mờ) — name/email/role là PII, không bao
    giờ được đọc (xem docstring _derive_thread_id). Vai KHÔNG lấy từ body: mọi
    thứ trong body đều do client gửi, tức tự khai được.

    Trả None khi không xác định được — gọi tầng trên phải TỪ CHỐI, không được
    mặc định thành admin."""
    if headers is None:
        return None
    return roles_mod.role_for_user(headers.get("x-openwebui-user-id"))


def _derive_thread_id(body: dict, messages: list[dict], headers=None,
                      role: str | None = None) -> str | None:
    """Stable per-conversation thread for interrupt/resume.

    Priority (R7 fix, spec 2026-07-09-r7-thread-scoping):
      0. Vai (role) là TIỀN TỐ của mọi phương án dưới đây — đổi vai phải sang
         luồng mới, nếu không một câu xác nhận đang treo ở vai cũ sẽ bị resume
         trong graph của vai mới (graph đó không có node tương ứng).
      1. Open WebUI identity headers — real per-chat id, sent when the
         open-webui container has ENABLE_FORWARD_USER_INFO_HEADERS=true.
         Only the two id headers are read; name/email/role are PII and must
         never be read or logged.
      2. Explicit id from the client body (scripts/curl).
      3. Hash of the FIRST user message — stable across the turns of one
         conversation, but collides across conversations with identical
         openers; the fresh-conversation reset in ERPAgent.chat mitigates.
      4. None (no user message).
    """
    if headers is not None:
        chat_id = headers.get("x-openwebui-chat-id")
        if chat_id:
            user_id = headers.get("x-openwebui-user-id") or "anon"
            return f"{role or 'norole'}:owui:{user_id}:{chat_id}"
    if _explicit_session(body):
        return f"{role or 'norole'}:" + str(body.get("session_id") or body.get("id"))
    first_user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    if not first_user:
        return None
    return (f"{role or 'norole'}:conv-"
            + hashlib.sha1(first_user.encode("utf-8")).hexdigest()[:16])


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    stream = bool(body.get("stream", False))
    messages = _filter_messages(body.get("messages", []))
    # Model người dùng chọn ở dropdown. Đặt vào ContextVar để resolve() của
    # Router đọc được; nó chỉ ĐƯA MODEL LÊN ĐẦU CHUỖI, mọi mắt xích dự phòng
    # vẫn nguyên (xem catalog.chain_for). Tên lạ / tên MODEL_ID → None = dùng
    # chuỗi mặc định của từng vai; KHÔNG nổ, vì tên model là dữ liệu do client
    # gửi và một cấu hình Open WebUI cũ không được phép làm hỏng lượt chat.
    chosen = body.get("model")
    # Không chọn (hoặc chọn MODEL_ID / tên lạ) → MODEL_MAC_DINH, KHÔNG phải
    # None. None nghĩa là "mỗi vai dùng chuỗi riêng của nó" — tức hành vi CŨ,
    # nhiều model, đúng thứ quyết định 2026-08-21 đi bỏ. Với mặc định này,
    # mắt xích đầu cũ của từng vai tụt xuống làm dự phòng; tiện thể chữa
    # luôn việc `gemini-3.5-flash` (rpd=20) từng là mắt xích ĐẦU của
    # chitchat, tức tán gẫu rơi xuống Groq sau ~20 tin nhắn mỗi ngày.
    MODEL_NGUOI_DUNG_CHON.set(
        chosen if chosen in MODEL_CHON_DUOC else MODEL_MAC_DINH)
    # Thùng gom fallback: dict MỚI mỗi request. Node sửa TẠI CHỖ (set()
    # trong task con không lan ngược về đây — đã kiểm bằng graph thật).
    THUNG_FALLBACK.set({})

    agent: ERPAgent = _state["agent"]
    try:
        if _is_owui_task_prompt(messages):
            # Open WebUI's own background task call (title/tags/follow-up/query
            # generation) — answer it directly, never touch thread/checkpoint
            # state (R7 hotfix, spec §8).
            answer = await agent.answer_stateless(messages[0]["content"])
        else:
            # Stable thread per conversation so multi-turn confirmation resumes
            # correctly. Priority: Open WebUI identity headers (R7) > explicit
            # client session_id/id > hash of the first user message (see
            # _derive_thread_id docstring).
            role = _role_from_headers(req.headers)
            if role is None:
                role = os.environ.get("YOUDOO_FALLBACK_ROLE") or None
            if role is None:
                answer = ("Không xác định được quyền truy cập của bạn. "
                          "Vui lòng đăng nhập bằng tài khoản đã được cấp vai, "
                          "hoặc liên hệ quản trị viên.")
            else:
                thread_id = _derive_thread_id(body, messages, headers=req.headers,
                                              role=role)
                answer = await agent.chat(messages, thread_id=thread_id, role=role,
                                          reset_if_fresh=not _explicit_session(body),
                                          user_id=req.headers.get("x-openwebui-user-id"))
    except Exception:
        # Finding 2 (live-test 2026-07-10): a transient failure (cloud LLM
        # hiccup/timeout/rate-limit) here used to propagate uncaught → FastAPI
        # 500, forcing Open WebUI's own retry to paper over it (and the
        # traceback was never captured — logs on this host truncate on every
        # restart). rag_node/fuse_answer already degrade to a safe message on
        # failure; this is the same pattern at the endpoint's outermost layer,
        # covering EVERY node (chitchat included, which lacked its own guard).
        logger.exception("chat_completions failed")
        answer = ERROR_MSG

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if not stream:
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": MODEL_ID,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": answer},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    # Streaming: agent trả nguyên câu → emit 1 content chunk + [DONE] (đủ cho Open WebUI)
    async def sse():
        base = {"id": cid, "object": "chat.completion.chunk",
                "created": created, "model": MODEL_ID}
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})}\n\n'
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
