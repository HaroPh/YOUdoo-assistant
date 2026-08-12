"""Bằng chứng NỐI DÂY: chứng minh guard role_scope thật sự nằm TRONG thân hai
tool mail (preview_template_email, send_prepared_email) như đã đăng ký vào
FastMCP — không chỉ là role_scope.py đứng riêng qua được test thuần
(test_role_scope.py chỉ kiểm tra chính module đó, không chạm tới tool nào).

Dùng lại đúng cách lấy hàm THẬT từ registry FastMCP mà
test_odoo_tool_boundary.py dùng (server.mcp._tool_manager._tools[...].fn) —
để nếu một lần chẻ/refactor domain sau này lặng lẽ đánh rơi guard khỏi thân
hàm, bộ test này phải đỏ, không chỉ role_scope.py tự kiểm chính nó.

odoo() bị monkeypatch thành một hàm ghi log lệnh gọi — KHÔNG chạm Odoo/MCP
sống. Vá thẳng vào namespace module tools.mail (nơi `odoo` được bind qua
`from odoo_call import odoo`), không vá odoo_call.odoo (tool không tra cứu
lại tên đó lúc chạy)."""
import json
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"

ENV_TEMPLATES = "MCP_ALLOWED_TEMPLATES"
ENV_MODELS = "MCP_ALLOWED_MAIL_MODELS"


@pytest.fixture(scope="module")
def registry():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
    except ImportError as exc:
        pytest.skip(f"không import được server.py: {exc}")
    finally:
        sys.path.remove(str(MCP_DIR))
    reg = getattr(server.mcp, "_tool_manager", None)
    tools = getattr(reg, "_tools", None) if reg else None
    if not tools:
        pytest.skip("không đọc được registry FastMCP — cấu trúc nội bộ đã đổi")
    return tools


@pytest.fixture
def preview_fn(registry):
    tool = registry["preview_template_email"]
    return getattr(tool, "fn", None) or getattr(tool, "func", None)


@pytest.fixture
def send_fn(registry):
    tool = registry["send_prepared_email"]
    return getattr(tool, "fn", None) or getattr(tool, "func", None)


@pytest.fixture
def mail_module():
    # Đã nằm trong sys.modules từ lúc fixture `registry` import server (kéo
    # theo `from tools import ..., mail`) — lấy lại qua sys.modules, không
    # import lần hai (import lần hai sẽ tạo bản mail.py độc lập, KHÔNG phải
    # module mà registry đang giữ tham chiếu hàm tới).
    return sys.modules["tools.mail"]


def fake_odoo(calls, responses=None):
    """Trả hàm giả thay odoo(); ghi mọi lệnh gọi vào `calls`, trả về
    responses.get((model, method), []) hoặc [] mặc định."""
    responses = responses or {}

    def _odoo(model, method, args, kwargs=None):
        calls.append((model, method, args, kwargs))
        return responses.get((model, method), [])

    return _odoo


def test_preview_tu_choi_template_ngoai_allowlist_khong_goi_odoo(
        preview_fn, mail_module, monkeypatch):
    monkeypatch.setenv(ENV_TEMPLATES, "Allowed Template")
    calls = []
    monkeypatch.setattr(mail_module, "odoo", fake_odoo(calls))

    result = json.loads(preview_fn("Not Allowed", "sale.order", "S00001"))

    assert result["ok"] is False
    assert "phạm vi" in result["display"]
    assert calls == [], "guard phải chặn TRƯỚC bất kỳ lệnh gọi odoo() nào"


def test_preview_cho_qua_template_trong_allowlist_cham_toi_odoo(
        preview_fn, mail_module, monkeypatch):
    monkeypatch.setenv(ENV_TEMPLATES, "Allowed Template")
    calls = []
    monkeypatch.setattr(mail_module, "odoo", fake_odoo(calls))

    preview_fn("Allowed Template", "sale.order", "S00001")

    assert calls, "template trong allowlist phải vượt qua guard, chạm tới odoo()"
    assert calls[0][0] == "mail.template"
    assert calls[0][1] == "search_read"


def test_send_tu_choi_model_ngoai_allowlist_khong_ghi_khong_gui(
        send_fn, mail_module, monkeypatch):
    """LƯU Ý mock: cùng một entry ("mail.mail", "read") trong `responses` bị
    dùng lại cho CẢ HAI lệnh read khác nhau trong send_prepared_email — lệnh
    đối chiếu model của guard (chỉ cần field "model") VÀ lệnh đọc trạng thái
    sau send() (cần "state"/"failure_reason"/"subject", xem mail.py dòng
    159). fake_odoo không lọc theo `fields` yêu cầu, chỉ trả nguyên response
    đã đăng ký cho khóa (model, method) — nên phải có ĐỦ field cho CẢ hai
    người gọi tiềm năng, không chỉ người gọi đầu tiên (guard).
    Nếu thiếu "state": khi ai đó xóa guard (dòng 145-152), thân hàm sẽ chạy
    tiếp xuống lệnh write()/send()/read() thật, và rows[0]["state"] ném
    KeyError — test đỏ vì CRASH ngẫu nhiên của mock, không phải vì assertion
    "result['ok'] is False" bên dưới. Có đủ field, guard bị xóa sẽ khiến
    send "thành công" giả (state="sent" → ok=True) và chính assertion phát
    hiện regression, đúng bằng chứng cần có."""
    monkeypatch.setenv(ENV_MODELS, "stock.picking")
    calls = []
    responses = {("mail.mail", "read"): [{"model": "account.move",
                                          "state": "sent",
                                          "failure_reason": None,
                                          "subject": "x"}]}
    monkeypatch.setattr(mail_module, "odoo", fake_odoo(calls, responses))

    result = json.loads(send_fn(123))

    assert result["ok"] is False
    assert "phạm vi" in result["display"]
    # Chỉ được phép có ĐÚNG lệnh đọc model nguồn — không write, không send.
    methods_called = [c[1] for c in calls]
    assert methods_called == ["read"]


def test_env_khong_dat_thi_ca_hai_tool_chay_nhu_cu(
        preview_fn, send_fn, mail_module, monkeypatch):
    """Hợp đồng 'env rỗng = không giới hạn' phải giữ nguyên ở tầng tool, không
    chỉ ở tầng role_scope.py thuần."""
    monkeypatch.delenv(ENV_TEMPLATES, raising=False)
    monkeypatch.delenv(ENV_MODELS, raising=False)

    calls = []
    monkeypatch.setattr(mail_module, "odoo", fake_odoo(calls))
    preview_fn("Bat Ky Template Nao", "sale.order", "S00001")
    assert calls, "env rỗng: preview_template_email phải chạm odoo() ngay, không bị chặn"
    assert calls[0][0] == "mail.template"

    calls.clear()
    send_fn(123)
    assert calls, "env rỗng: send_prepared_email phải chạm odoo() ngay, không bị chặn"
    # Không có bước đọc model để đối chiếu phạm vi — lệnh odoo() ĐẦU TIÊN
    # phải là write() lật state, đúng hành vi TRƯỚC khi có role_scope.
    assert calls[0][0] == "mail.mail"
    assert calls[0][1] == "write"
