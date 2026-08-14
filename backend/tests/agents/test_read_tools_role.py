# backend/tests/agents/test_read_tools_role.py
"""final-review I1: nửa ĐỌC của bàn giao chéo bộ phận — `list_my_activities`
(erp_query/tools.py) chỉ trả đúng việc của bộ phận mình nếu graph.py THẬT SỰ
truyền `role_cfg` xuống `build_erp_query_tools(role_cfg)`. Trước fix wave
này, không test nào canh dây nối đó: đổi `build_erp_query_tools(role_cfg)`
thành `build_erp_query_tools()` ở graph.py, HOẶC đổi `f"ai-{role_cfg.name}"`
thành `""` ở tools.py, 1375 test vẫn XANH — nghĩa là một vai có thể đọc được
việc bàn giao của vai khác (hoặc không đọc được việc của chính mình) mà
không ai biết.

Ba test dưới đây khoá lại, độc lập với Odoo thật (monkeypatch crm)."""
import json

from src.agents import roles
from src.erp_query.tools import build_erp_query_tools

ACCOUNTING = roles.PROFILES["small-business"]["accounting"]


def test_list_my_activities_dung_login_theo_vai(monkeypatch):
    """build_erp_query_tools(role_cfg) với vai kế toán ⇒ tool gọi
    crm.list_my_activities với login "ai-accounting"."""
    import src.erp_query.tools as tmod

    captured = {}

    def fake_list_my_activities(login, limit=20, **kw):
        captured["login"] = login
        return {"status": "success", "data": {"rows": []}}

    monkeypatch.setattr(tmod.crm, "list_my_activities", fake_list_my_activities)

    tool = next(t for t in build_erp_query_tools(ACCOUNTING)
               if t.name == "list_my_activities")
    tool.invoke({})

    assert captured["login"] == "ai-accounting"


def test_list_my_activities_khong_role_cfg_thi_login_rong():
    """build_erp_query_tools() KHÔNG tham số ⇒ login rỗng ⇒ envelope 'Không
    xác định được tài khoản để tra việc.' — KHÔNG được lộ việc của vai khác
    (fail-closed, không phải fail-open sang một login mặc định nào đó)."""
    tool = next(t for t in build_erp_query_tools()
               if t.name == "list_my_activities")
    out = json.loads(tool.invoke({}))

    assert out["data"]["rows"] == []
    assert "Không xác định được tài khoản để tra việc." in out["display"]


def test_graph_build_truyen_role_cfg_xuong_build_erp_query_tools(monkeypatch):
    """Khoá dây nối graph.py → build_erp_query_tools: `build_graph(...,
    role_cfg=...)` phải TRUYỀN đúng role_cfg đó xuống, không phải gọi
    build_erp_query_tools() trơn. Gọi ĐỦ 2 lần thật trong graph.py: node
    erp_read (llms["read"]) và node gather_erp (llms["fusion"])."""
    from unittest.mock import MagicMock

    import src.agents.graph as graph_mod

    calls = []

    def fake_build_erp_query_tools(role_cfg=None):
        calls.append(role_cfg)
        return []

    monkeypatch.setattr(graph_mod, "build_erp_query_tools",
                        fake_build_erp_query_tools)

    graph_mod.build_graph(MagicMock(), [], checkpointer=None, role_cfg=ACCOUNTING)

    assert calls.count(ACCOUNTING) >= 2, (
        f"build_erp_query_tools phải nhận đúng role_cfg={ACCOUNTING!r} ở cả "
        f"erp_read lẫn gather_erp, thực tế các lần gọi: {calls!r}")
