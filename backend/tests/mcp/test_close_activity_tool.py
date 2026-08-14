"""close_activity — đóng MỘT việc đang giao cho tài khoản đang gọi.

Đo trên Odoo thật 2026-08-14 (spec §1.3): Odoo KHÔNG chặn một tài khoản đóng
việc của người khác. Bộ lọc user_id trong tool là lớp cưỡng chế DUY NHẤT, nên
nó có test riêng và phải chịu được phép thử phá.

Test gọi thẳng hàm đã đăng ký trong registry FastMCP với odoo() bị monkeypatch
— KHÔNG chạm Odoo thật (cùng khuôn tests/mcp/test_log_activity_tool.py)."""
import importlib.util
import json
import pathlib
import sys

import pytest

MCP_DIR = pathlib.Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def crm_mod():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server  # noqa: F401  — đăng ký tool
    finally:
        sys.path.remove(str(MCP_DIR))
    return sys.modules["tools.crm"]


@pytest.fixture(scope="module")
def close_fn(crm_mod):
    import server
    return server.mcp._tool_manager._tools["close_activity"].fn


@pytest.fixture(scope="module")
def security_mod():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    spec = importlib.util.spec_from_file_location(
        "_mcp_security_for_close_test", MCP_DIR / "security.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_action_feedback_nam_trong_allowlist(security_mod):
    """odoo_call.odoo() từ chối mọi method vắng mặt trong bảng này
    (deny-by-default). Thiếu dòng này thì close_activity chết ở lớp bảo mật
    của chính dự án, TRƯỚC khi chạm Odoo — và phép đo XML-RPC trong spec §1
    không thấy được, vì nó vòng qua lớp này."""
    assert security_mod.classify_operation("action_feedback") == "write"


def _fake_odoo(calls, *, rows=None):
    """rows = kết quả search_read mail.activity. Trả BẤT KỂ domain — để test
    bộ lọc phải khẳng định trên domain đã ghi lại, không dựa vào việc fake
    tình cờ trả rỗng."""
    rows = [{"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
             "res_name": "S00012"}] if rows is None else rows

    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        if method == "search_read":
            return rows
        return True

    return odoo


def test_dong_duoc_viec_cua_minh(crm_mod, close_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55, note="đã phát hành xong"))

    assert out["ok"] is True
    assert out["state"] == "done" and out["res_id"] == 55
    done = [c for c in calls if c[1] == "action_feedback"]
    assert len(done) == 1
    assert done[0][0] == "mail.activity"
    assert done[0][2] == [[55]]
    assert done[0][3]["feedback"] == "đã phát hành xong"


def test_bo_loc_user_id_co_mat_trong_domain(crm_mod, close_fn, monkeypatch):
    """Lớp cưỡng chế DUY NHẤT (spec §1.3). Gỡ leaf user_id ra khỏi domain thì
    test này PHẢI đỏ — đó là phép thử phá bắt buộc ở Step 8.

    Khẳng định trên DOMAIN chứ không trên kết quả: fake trả cùng một dòng bất
    kể domain, nên một test chỉ nhìn kết quả sẽ xanh cả khi bộ lọc biến mất."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    close_fn(55)

    reads = [c for c in calls if c[1] == "search_read"]
    assert len(reads) == 1
    domain = reads[0][2][0]
    assert ["user_id", "=", 10] in domain
    assert ["id", "=", 55] in domain


def test_khong_phai_viec_cua_minh_thi_tu_choi(crm_mod, close_fn, monkeypatch):
    """Việc của người khác và việc đã đóng dùng CHUNG một câu — tách ra sẽ để
    lộ việc của bộ phận khác có tồn tại hay không (spec §2.2)."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, rows=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))

    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "action_feedback"]


def test_note_rong_van_dong_duoc(crm_mod, close_fn, monkeypatch):
    """Lời nhắn là tuỳ chọn, nhưng chatter vẫn phải có gì đó để hiển thị."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))

    assert out["ok"] is True
    feedback = [c for c in calls if c[1] == "action_feedback"][0][3]["feedback"]
    assert feedback.strip(), "feedback rỗng — chatter sẽ không có gì để hiện"


def test_odoo_hong_thi_tra_loi_khong_vo(crm_mod, close_fn, monkeypatch):
    """Search_read đầu tiên bị AccessError — lớp bảo vệ bọc riêng nó, không lộ
    chi tiết lỗi Odoo hay tên nhóm quyền. Khẳng định trên DOMAIN + message."""
    calls = []
    def odoo_error(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        raise Exception("access-denied-detail: nhóm quyền XYZ")

    monkeypatch.setattr(crm_mod, "odoo", odoo_error)
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(close_fn(55))

    assert out["ok"] is False
    # Không lộ nguyên văn lỗi Odoo trong display
    assert "access-denied-detail" not in out["display"]
    assert "nhóm quyền" not in out["display"]
    # Không chạy action_feedback vì search_read đã hỏng
    assert not [c for c in calls if c[1] == "action_feedback"]
