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
    headers = {"x-openwebui-chat-id": "chat123", "x-openwebui-user-id": "user9"}
    tid = _derive_thread_id({}, [], headers=headers)
    assert tid == "owui:user9:chat123"


def test_derive_thread_id_uu_tien_session_id_neu_khong_co_header():
    tid = _derive_thread_id({"session_id": "sess1"}, [], headers={})
    assert tid == "sess1"


def test_derive_thread_id_hash_tin_nhan_dau_neu_khong_co_gi_khac():
    messages = [{"role": "user", "content": "câu hỏi đầu tiên"}]
    tid = _derive_thread_id({}, messages, headers={})
    assert tid is not None and tid.startswith("conv-")


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
