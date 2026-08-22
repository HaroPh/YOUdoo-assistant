# backend/tests/test_main_roles.py
import pytest

from src.main import _derive_thread_id, _role_from_headers


class H(dict):
    def get(self, k, d=None): return dict.get(self, k, d)


def test_thread_id_mang_vai_de_doi_vai_khong_resume_nham_graph():
    """Cạm bẫy: đổi vai giữa lúc một câu xác nhận đang treo sẽ khiến LangGraph
    resume interrupt trong graph không có node đó. Đưa vai vào thread_id ⇒ đổi
    vai = sang luồng mới."""
    body, msgs = {"session_id": "s1"}, [{"role": "user", "content": "x"}]
    a = _derive_thread_id(body, msgs, headers=None, role="warehouse")
    b = _derive_thread_id(body, msgs, headers=None, role="accounting")
    assert a != b
    assert "warehouse" in a


def test_khong_co_header_thi_khong_suy_ra_vai():
    """Fail-closed: thiếu header (vd chưa bật ENABLE_FORWARD_USER_INFO_HEADERS)
    KHÔNG được mặc định thành admin."""
    assert _role_from_headers(None) is None
    assert _role_from_headers(H()) is None


def test_suy_vai_tu_user_id_qua_bang_anh_xa(monkeypatch):
    monkeypatch.setenv("YOUDOO_ROLE_MAP", "u-kho:warehouse")
    assert _role_from_headers(H({"x-openwebui-user-id": "u-kho"})) == "warehouse"
    assert _role_from_headers(H({"x-openwebui-user-id": "nguoi-la"})) is None


@pytest.mark.asyncio
async def test_endpoint_tu_choi_truoc_khi_cham_agent_khi_khong_suy_duoc_vai(monkeypatch):
    """Cạm bẫy: nếu logic từ chối bị vòng qua (regression), request sẽ lọt
    tới agent.chat() với role không xác định — đây là net kiểm tra điều đó
    KHÔNG xảy ra ở tầng endpoint, không chỉ ở các hàm thuần bên trên."""
    import httpx
    from src import main as main_module

    class _FakeAgentRecords:
        def __init__(self):
            self.called = False

        async def chat(self, *a, **k):
            self.called = True
            return "không nên tới đây"

    # Không có header đăng nhập, không mapping nào khớp caller ⇒ role phải là
    # None ở mọi nguồn. (`YOUDOO_FALLBACK_ROLE` đã bị GỠ 2026-08-22 — nó chính
    # là "escape hatch" mà test này từng phải tắt đi bằng tay.)
    #
    # Token thì VẪN phải hợp lệ: test này đo cổng PHÂN QUYỀN, không phải cổng
    # xác thực. Thiếu token thì request dừng ở 401 và ta không còn đo được gì.
    monkeypatch.setenv("YOUDOO_API_TOKEN", "token-thu")
    monkeypatch.delenv("YOUDOO_ROLE_MAP", raising=False)

    fake_agent = _FakeAgentRecords()
    main_module._state["agent"] = fake_agent
    try:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": "Bearer token-thu"})
        assert resp.status_code == 200
        # Assertion order is deliberate: agent.called is the one that actually
        # proves the refusal happens BEFORE the agent (a bypass regression
        # would reach agent.chat and this is the assertion that catches it),
        # so it runs first rather than being masked by the content check.
        assert fake_agent.called is False
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        assert "Không xác định được quyền truy cập" in content
    finally:
        main_module._state.clear()
