# backend/tests/test_main.py
"""main.py: hàm thuần (không cần FastAPI TestClient) + endpoint lỗi."""
import pytest

from src.main import (_derive_thread_id, _explicit_session,
                      _is_owui_task_prompt, _filter_messages)


def test_filter_messages_bo_system_giu_user_assistant():
    messages = [
        {"role": "system", "content": "prompt hệ thống"},
        {"role": "user", "content": "câu hỏi"},
        {"role": "assistant", "content": "trả lời"},
        {"role": "user", "content": ""},  # rỗng, phải bị loại
    ]
    result = _filter_messages(messages)
    assert result == [
        {"role": "user", "content": "câu hỏi"},
        {"role": "assistant", "content": "trả lời"},
    ]


def test_explicit_session_true_khi_co_session_id():
    assert _explicit_session({"session_id": "abc"}) is True
    assert _explicit_session({"id": "xyz"}) is True


def test_explicit_session_false_khi_khong_co():
    assert _explicit_session({}) is False


def test_is_owui_task_prompt_dung_dinh_dang():
    messages = [{"role": "user", "content": "### Task:\nTóm tắt hội thoại"}]
    assert _is_owui_task_prompt(messages) is True


def test_is_owui_task_prompt_khong_khop_neu_thieu_newline():
    messages = [{"role": "user", "content": "### Task: không có newline"}]
    assert _is_owui_task_prompt(messages) is False


def test_is_owui_task_prompt_false_khi_nhieu_tin_nhan():
    messages = [
        {"role": "user", "content": "### Task:\nx"},
        {"role": "assistant", "content": "y"},
    ]
    assert _is_owui_task_prompt(messages) is False


def test_derive_thread_id_uu_tien_header_openwebui():
    # role không truyền vào ⇒ tiền tố "norole:" (xem test_main_roles.py cho
    # hành vi tiền tố vai thật — ở đây chỉ kiểm tra thứ tự ưu tiên nguồn).
    headers = {"x-openwebui-chat-id": "chat123", "x-openwebui-user-id": "user9"}
    tid = _derive_thread_id({}, [], headers=headers)
    assert tid == "norole:owui:user9:chat123"


def test_derive_thread_id_uu_tien_session_id_neu_khong_co_header():
    tid = _derive_thread_id({"session_id": "sess1"}, [], headers={})
    assert tid == "norole:sess1"


def test_derive_thread_id_hash_tin_nhan_dau_neu_khong_co_gi_khac():
    messages = [{"role": "user", "content": "câu hỏi đầu tiên"}]
    tid = _derive_thread_id({}, messages, headers={})
    assert tid is not None and tid.startswith("norole:conv-")


def test_derive_thread_id_none_neu_khong_co_user_message():
    tid = _derive_thread_id({}, [], headers={})
    assert tid is None


@pytest.mark.asyncio
async def test_chat_completions_tra_error_msg_khi_agent_nem_loi(monkeypatch):
    import httpx
    from src import main as main_module

    class _FakeAgentThrows:
        async def chat(self, *a, **k):
            raise RuntimeError("lỗi giả lập agent")

    # Request không có header đăng nhập ⇒ role sẽ là None trừ khi có escape
    # hatch dev tường minh. Đặt YOUDOO_FALLBACK_ROLE để yêu cầu này đi tới
    # agent.chat() thật sự — mục đích của test là kiểm tra lỗi từ agent.chat
    # được bọc thành ERROR_MSG, không phải kiểm tra đường từ chối vì thiếu vai.
    monkeypatch.setenv("YOUDOO_FALLBACK_ROLE", "admin")
    main_module._state["agent"] = _FakeAgentThrows()
    try:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions",
                                     json={"messages": [{"role": "user",
                                                         "content": "hi"}]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["choices"][0]["message"]["content"] == main_module.ERROR_MSG
    finally:
        main_module._state.clear()


@pytest.mark.asyncio
async def test_health_endpoint_khi_chua_co_agent():
    import httpx
    from src import main as main_module

    main_module._state.clear()
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "agent_ready": False}


# ─── Dropdown chọn model + trường `model` của phản hồi (2026-08-21) ──────────
# Tới trước ngày này KHÔNG test nào chạm /v1/models, và KHÔNG test nào đọc
# trường `model` của phản hồi chat. Cả hai đổi được mà toàn bộ suite vẫn xanh —
# đúng lớp lỗi "danh sách khai báo mà không ai gác" đã tái phát nhiều lần ở
# repo này.

async def _post_chat(main_module, body, monkeypatch):
    import httpx
    monkeypatch.setenv("YOUDOO_FALLBACK_ROLE", "admin")
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        return await client.post("/v1/chat/completions", json=body)


@pytest.mark.asyncio
async def test_v1_models_chi_liet_ke_model_chon_duoc():
    """Ba ô nhưng hai hành vi là hỏng: `erp-assistant` map về MODEL_MAC_DINH nên
    nó trùng y hệt `gemini-3.1-flash-lite`."""
    import httpx
    from src import main as main_module
    from src.llm.catalog import MODEL_CHON_DUOC

    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        resp = await client.get("/v1/models")
    ids = [m["id"] for m in resp.json()["data"]]
    assert ids == list(MODEL_CHON_DUOC)
    assert main_module.MODEL_ID not in ids


@pytest.mark.asyncio
async def test_ten_model_cu_van_chay_va_ve_mac_dinh(monkeypatch):
    """Gỡ khỏi danh sách KHÔNG được làm gãy client cũ. Harness nghiệm thu sống
    (tests/live_verify_common.py) vẫn gửi đúng tên này."""
    from src import main as main_module
    from src.llm.catalog import MODEL_MAC_DINH

    class _Agent:
        async def chat(self, *a, **k):
            return "xong"

    main_module._state["agent"] = _Agent()
    try:
        resp = await _post_chat(main_module, {
            "model": "erp-assistant",
            "messages": [{"role": "user", "content": "hi"}]}, monkeypatch)
        assert resp.status_code == 200
        # Không vai nào chạy nên rơi về model người dùng chọn — mà "erp-assistant"
        # là tên lạ, tức MODEL_MAC_DINH.
        assert resp.json()["model"] == MODEL_MAC_DINH
    finally:
        main_module._state.clear()


@pytest.mark.asyncio
async def test_truong_model_la_model_THAT_da_tra_loi(monkeypatch):
    """Trước 2026-08-21 trường này là hằng số "erp-assistant" bất kể ai trả lời,
    nên API tự nó không cho biết model nào chạy."""
    from src import main as main_module
    from src.llm.router import THUNG_MODEL

    class _Agent:
        async def chat(self, *a, **k):
            # Sửa TẠI CHỖ đúng như RoutedChatModel làm từ trong node.
            THUNG_MODEL.get().update({"router": "gemini-3.5-flash-lite",
                                      "chitchat": "gemini-3.5-flash"})
            return "chào bạn"

    main_module._state["agent"] = _Agent()
    try:
        resp = await _post_chat(main_module, {
            "model": "gemini-3.5-flash-lite",
            "messages": [{"role": "user", "content": "hi"}]}, monkeypatch)
        # `chitchat` là vai SINH câu trả lời; `router` chỉ phân loại.
        assert resp.json()["model"] == "gemini-3.5-flash"
    finally:
        main_module._state.clear()


@pytest.mark.asyncio
async def test_truong_model_khi_luot_hong_ve_model_nguoi_dung_chon(monkeypatch):
    """Lượt nổ trước khi tới vai sinh câu trả lời: nhãn phải suy biến êm, không
    được kéo cả lượt chat xuống theo."""
    from src import main as main_module

    class _Agent:
        async def chat(self, *a, **k):
            raise RuntimeError("nổ")

    main_module._state["agent"] = _Agent()
    try:
        resp = await _post_chat(main_module, {
            "model": "gemini-3.5-flash-lite",
            "messages": [{"role": "user", "content": "hi"}]}, monkeypatch)
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == main_module.ERROR_MSG
        assert resp.json()["model"] == "gemini-3.5-flash-lite"
    finally:
        main_module._state.clear()
