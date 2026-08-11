# backend/tests/test_main_roles.py
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
