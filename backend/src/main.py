"""
FastAPI backend — OpenAI-compatible API bọc ERP agent.
Open WebUI nối vào endpoint /v1 này như một "model" (erp-assistant).

Chạy (host, cần mcp-odoo SSE :8003 đang chạy):
    cd backend
    python run.py
"""
import hashlib
import asyncio
import json
import logging
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.agents.erp_agent import ERPAgent
from src.agents.tien_trinh import HANG_TIEN_TRINH
from src.agents import roles as roles_mod

logger = logging.getLogger(__name__)

from src.llm.catalog import (MODEL_CHON_DUOC, MODEL_MAC_DINH,
                             MODEL_NGUOI_DUNG_CHON, model_tra_loi)
from src.llm.router import THUNG_FALLBACK, THUNG_MODEL

# Tên endpoint, KHÔNG phải một model. Từ 2026-08-21 nó không còn được
# quảng cáo ở /v1/models (xem docstring ở đó) nhưng vẫn giữ: client cũ và
# harness nghiệm thu sống (tests/live_verify_common.py) vẫn gửi tên này, và
# nhánh "tên lạ → MODEL_MAC_DINH" nhận nó mà không nổ.
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


def _doc_token() -> str:
    """Token bắt buộc cho /v1/*. Thiếu ⇒ CHẾT NGAY, không chạy mở toang.

    Trước 2026-08-22 `/v1` KHÔNG có xác thực nào: backend bind `0.0.0.0:8002`
    và quyền được suy DUY NHẤT từ header `x-openwebui-user-id` — một chuỗi do
    client tự khai. Ai trong cùng mạng LAN gửi header của admin là mở khoá
    toàn bộ 33 tool ghi Odoo (duyệt đơn, phát hành hoá đơn, gửi mail ra ngoài).
    Kiểm toán 2026-08-22 gọi đây là FM-1; nó được xác nhận bằng cách KHAI THÁC
    thật trong chính phiên đó.

    Fail-closed có chủ đích (chủ dự án chốt phương án A): một cổng an toàn có
    thể tự tắt vì thiếu cấu hình thì không phải cổng an toàn. Cùng khuôn với
    `providers.client_for` — chết ngay lúc dựng, nêu đúng tên biến phải đặt.

    Đường ống đã có sẵn hai đầu: `docker-compose.yml` vốn đã truyền
    `OPENAI_API_KEY` cho Open WebUI, tức nó ĐANG gửi `Authorization: Bearer`
    mỗi lượt — backend chỉ chưa từng đọc.
    """
    token = os.environ.get("YOUDOO_API_TOKEN")
    if not token:
        raise RuntimeError(
            "thiếu biến môi trường YOUDOO_API_TOKEN — /v1/* bắt buộc phải có "
            "token. Đặt nó trong .env, và docker-compose truyền cùng giá trị "
            "đó cho Open WebUI qua OPENAI_API_KEY. Xem .env.example.")
    return token


def _kiem_token(req: Request) -> None:
    """Ném HTTPException 401 nếu header Authorization không khớp.

    `compare_digest` chứ không phải `==`: so sánh chuỗi thường thoát sớm ở ký
    tự lệch đầu tiên, tức thời gian phản hồi rò rỉ từng ký tự của token.
    """
    token = _doc_token()
    header = req.headers.get("authorization") or ""
    prefix = "bearer "
    gui = header[len(prefix):] if header.lower().startswith(prefix) else ""
    if not (gui and secrets.compare_digest(gui, token)):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": "agent" in _state}


@app.get("/v1/models")
async def list_models(req: Request):
    """Liệt kê model cho dropdown của Open WebUI.

    Dropdown ĐÃ CÓ SẴN ở client — trước đây endpoint này trả đúng một mục nên
    nó vô dụng, và trường `model` trong request không ai đọc. Liệt kê lựa chọn
    thật ở đây là toàn bộ phần "giao diện" của tính năng chọn model.

    Tên hiển thị là TÊN MODEL THẬT, không phải nhãn sản phẩm kiểu "Nhanh /
    Chính xác": nhãn như thế là lời hứa về KẾT QUẢ mà chưa ai đo, còn mục đích
    của việc cho chọn chính là để biết model nào đang trả lời.

    `MODEL_ID` KHÔNG còn nằm trong danh sách (2026-08-21). Nó là tên của
    ENDPOINT, không phải một model, và vì tên lạ được map về MODEL_MAC_DINH nên
    ô đó có hành vi Y HỆT ô `gemini-3.1-flash-lite`: ba ô nhưng hai hành vi.
    Một lựa chọn trùng hành vi làm hỏng đúng thứ tính năng này sinh ra để phục
    vụ — biết model nào đang trả lời. Client cũ không gãy vì nhánh "tên lạ →
    MODEL_MAC_DINH" ở /v1/chat/completions vẫn nhận `erp-assistant`.
    """
    _kiem_token(req)
    created = int(time.time())
    ids = MODEL_CHON_DUOC
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


# Cùng một nhãn tiến trình chỉ phát lại sau chừng này giây. Đủ dài để không
# spam khi agent gọi tool liên tiếp, đủ ngắn để panel không đứng im quá lâu.
LAP_NHAN_TOI_THIEU_S = 2.0


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    _kiem_token(req)
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
    THUNG_MODEL.set({})

    agent: ERPAgent = _state["agent"]

    async def _tinh_cau_tra_loi() -> str:
        """Toàn bộ đường tính câu trả lời, KHÔNG đổi một dòng logic.

        Bọc thành coroutine để lượt streaming chạy được nó như một task
        và vừa chạy vừa phát tiến trình. Lượt không streaming vẫn `await`
        thẳng, tức đường cũ không đổi hành vi.
        """
        answer = None
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
                # `YOUDOO_FALLBACK_ROLE` ĐÃ GỠ 2026-08-22. Nó cho một request KHÔNG
                # có header người dùng nhận vai bất kỳ — tức vô hiệu hoá đúng cổng
                # phân quyền mà `roles.py` dựng lên (kiểm toán 2026-08-22).
                #
                # Trước đây các script nghiệm thu sống cần nó vì `chat()` không gửi
                # header vai. Chuyện đó đã được sửa cùng ngày (live_verify_common
                # nay suy user-id từ YOUDOO_ROLE_MAP), nên biến này không còn ai
                # cần — giữ lại chỉ là giữ một cửa hậu cho tiện.
                role = _role_from_headers(req.headers)
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
        return answer

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    def _model_hien_tai() -> str:
        # Tên model THẬT đã sinh ra câu trả lời, không phải hằng số MODEL_ID.
        # Lượt hỏng (ERROR_MSG) hoặc lượt chưa tới vai sinh câu trả lời thì rơi
        # về model người dùng chọn — xem catalog.model_tra_loi.
        #
        # Gọi lại ở từng chunk chứ không chốt một lần: ở lượt streaming, các
        # chunk tiến trình đi ra TRƯỚC khi vai nào đó kịp ghi vào THUNG_MODEL.
        return model_tra_loi(THUNG_MODEL.get(),
                             MODEL_NGUOI_DUNG_CHON.get() or MODEL_MAC_DINH)

    if not stream:
        answer = await _tinh_cau_tra_loi()
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created,
            "model": _model_hien_tai(),
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": answer},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    # ── Streaming: báo TIẾN TRÌNH, không phải streaming token ────────────────
    #
    # Đo 2026-08-22 trên lượt ERP thật: tổng 9,95s là ~4 lời gọi LLM NỐI TIẾP,
    # còn câu trả lời cuối chỉ 74 ký tự. Streaming token sẽ cho người dùng 8–9
    # giây trắng màn hình rồi đổ ra 74 ký tự — gần như không cải thiện gì.
    #
    # Tiến trình đi trong khối <think>…</think>: đọc mã Open WebUI đang chạy
    # (utils/middleware.py, DEFAULT_REASONING_TAGS) thì thẻ này được dựng thành
    # panel suy nghĩ TÁCH KHỎI câu trả lời, nên chữ tiến trình không nằm lại
    # trong nội dung người dùng lưu.
    #
    # Hậu kỳ của chat() (bóc marker ký ức, dòng báo fallback, dịch) chạy trên
    # câu HOÀN CHỈNH và KHÔNG bị đụng tới: câu trả lời vẫn đi ra nguyên khối
    # sau </think>. Đây là lý do chọn hướng này thay vì stream chữ thô — stream
    # thô sẽ để marker ký ức lọt ra màn hình, đúng lỗi mà đợt write-suggest
    # marker trailing-fix đã đóng.
    async def sse():
        def _chunk(delta, finish=None):
            return "data: " + json.dumps(
                {"id": cid, "object": "chat.completion.chunk", "created": created,
                 "model": _model_hien_tai(),
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]},
                ensure_ascii=False) + "\n\n"

        hang: asyncio.Queue = asyncio.Queue()
        token = HANG_TIEN_TRINH.set(hang)
        # Task CHÉP ngữ cảnh lúc tạo, nên nó thấy hàng đợi vừa đặt (và cả
        # THUNG_MODEL/THUNG_FALLBACK — các node sửa TẠI CHỖ nên bản sửa vẫn
        # nhìn thấy được từ đây).
        viec = asyncio.create_task(_tinh_cau_tra_loi())
        try:
            yield _chunk({"role": "assistant"})
            da_mo_think = False
            da_bao: dict[str, float] = {}
            while True:
                try:
                    nhan = await asyncio.wait_for(hang.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    if viec.done():
                        break
                    continue
                # Khử trùng lặp theo THỜI GIAN, không theo nhãn.
                #
                # Bản đầu khử theo nhãn và đo ra một khoảng 6,9s panel đứng im:
                # agent gọi nhiều tool nối tiếp, mọi lần sau lần đầu đều mang
                # cùng nhãn nên bị nuốt sạch — tức bộ khử trùng lặp giấu đúng
                # chỗ tốn thời gian nhất. Lặp lại nhãn sau vài giây KHÔNG thừa:
                # nó là bằng chứng hệ vẫn đang chạy.
                bay_gio = time.monotonic()
                if bay_gio - da_bao.get(nhan, -99.0) < LAP_NHAN_TOI_THIEU_S:
                    continue
                da_bao[nhan] = bay_gio
                if not da_mo_think:
                    yield _chunk({"content": "<think>\n"})
                    da_mo_think = True
                yield _chunk({"content": nhan + "\n"})
            if da_mo_think:
                yield _chunk({"content": "</think>\n"})
            answer = await viec
        except Exception:                                   # noqa: BLE001
            # Đường hiển thị KHÔNG được là nguồn sự cố: hỏng ở đây vẫn phải trả
            # cho người dùng một câu tử tế.
            logger.exception("sse tiến trình hỏng")
            answer = await viec if not viec.done() else (
                viec.result() if viec.exception() is None else ERROR_MSG)
        finally:
            HANG_TIEN_TRINH.reset(token)

        yield _chunk({"content": answer})
        yield _chunk({}, finish="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
