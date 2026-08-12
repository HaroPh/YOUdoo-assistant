"""log_activity tổng quát theo model / loại / người nhận.

Ba giới hạn cũ và vì sao chúng là lỗi:
  - hardcode crm.lead: activity gắn được vào MỌI chứng từ, và đó là điều kiện
    để bàn giao liên bộ phận sau này có chỗ bám.
  - chỉ Call/Meeting: bỏ mất To-Do (loại NHIỀU NHẤT trong dữ liệu thật, 11/31),
    Email, Document.
  - user_id luôn = tài khoản gọi: không giao việc cho ai khác được.

Test gọi thẳng hàm đã đăng ký trong registry FastMCP với odoo() bị
monkeypatch — KHÔNG chạm Odoo thật (cùng khuôn
tests/mcp/test_mail_role_scope_wiring.py)."""
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
def log_activity_fn():
    import server
    return server.mcp._tool_manager._tools["log_activity"].fn


def _domain_khop(domain, rec):
    """Đánh giá tối giản domain Odoo dùng trong test này — chỉ leaf
    [field,'=',val] và toán tử '|' áp lên đúng hai leaf theo sau, đúng hình
    dạng domain crm.py dùng cho mail.activity.type (F3/F4)."""
    def leaf(term):
        field, op, val = term
        assert op == "="
        return rec.get(field) == val

    terms, i = [], 0
    while i < len(domain):
        if domain[i] == "|":
            terms.append(leaf(domain[i + 1]) or leaf(domain[i + 2]))
            i += 3
        else:
            terms.append(leaf(domain[i]))
            i += 1
    return all(terms)


def _fake_odoo(calls, *, types=None, users=None, rec=True):
    """types: cả "hồ bơi" bản ghi mail.activity.type có thật trong Odoo giả
    lập — mọi truy vấn lọc trên hồ bơi này theo domain thật (F3/F4 dựa vào
    lọc domain đúng, không phải nhận nguyên cụm không điều kiện).
    users: [{'id','name','login'}]."""
    types = [{"id": 7, "name": "To-Do", "res_model": False}] if types is None else types
    users = [] if users is None else users

    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        if model == "mail.activity.type":
            domain = args[0]
            return [t for t in types if _domain_khop(domain, t)]
        if model == "res.users":
            return users
        if model == "ir.model":
            return [3]
        if method == "create":
            return 999
        # search_read bản ghi đích
        return [{"id": args[0][0][2], "name": "S00119"}] if rec else []

    return odoo


def test_tao_duoc_tren_model_bat_ky(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "Gọi lại khách"))
    assert out["ok"] is True
    created = [c for c in calls if c[1] == "create" and c[0] == "mail.activity"]
    assert len(created) == 1
    vals = created[0][2][0]
    assert vals["res_id"] == 119
    assert vals["res_model_id"] == 3
    assert vals["user_id"] == 8          # bỏ trống assignee = tài khoản gọi


def test_loai_gan_model_khac_bi_tu_choi(crm_mod, log_activity_fn, monkeypatch):
    """Maintenance Request gắn cứng maintenance.request trong Odoo. Từ chối
    phải đến TỪ DỮ LIỆU Odoo, không từ một danh sách cấm viết tay."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, types=[{"id": 9, "name": "Maintenance Request",
                       "res_model": "maintenance.request"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Maintenance Request", "x"))
    assert out["ok"] is False
    assert "maintenance.request" in out["display"]
    assert not [c for c in calls if c[1] == "create"]


def test_loai_khong_ton_tai(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, types=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Bịa Ra", "x"))
    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "create"]


def test_loai_khong_ton_tai_liet_ke_lua_chon_hop_le(crm_mod, log_activity_fn, monkeypatch):
    """F3: từ chối SAU cửa xác nhận phải nêu lựa chọn — lấy TỪ Odoo, không
    từ danh sách viết tay. Loại chỉ dùng cho model khác (Maintenance Request)
    không được liệt kê vì không dùng được cho sale.order."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, types=[{"id": 7, "name": "To-Do", "res_model": False},
                      {"id": 8, "name": "Call", "res_model": False},
                      {"id": 9, "name": "Maintenance Request",
                       "res_model": "maintenance.request"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Bịa Ra", "x"))
    assert out["ok"] is False
    assert "To-Do" in out["display"] and "Call" in out["display"]
    assert "Maintenance Request" not in out["display"]
    assert not [c for c in calls if c[1] == "create"]


def test_loai_trung_ten_uu_tien_dung_khop_model(crm_mod, log_activity_fn, monkeypatch):
    """F4: hai loại trùng tên, một buộc model khác (id nhỏ hơn) và một khớp
    đúng model đang gọi (id lớn hơn). Domain phải chọn được dòng khớp model
    thay vì rơi vào "limit 1 không lọc" — trước fix, id nhỏ hơn thắng bất kể
    đúng hay không, khiến yêu cầu hợp lệ này bị từ chối oan."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, types=[{"id": 1, "name": "Dup", "res_model": "other.model"},
                      {"id": 2, "name": "Dup", "res_model": "sale.order"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 119, "Dup", "x"))
    assert out["ok"] is True
    created = [c for c in calls if c[1] == "create" and c[0] == "mail.activity"]
    assert created[0][2][0]["activity_type_id"] == 2


def test_ban_ghi_dich_khong_ton_tai(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, rec=False))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 8)
    out = json.loads(log_activity_fn("sale.order", 404, "To-Do", "x"))
    assert out["ok"] is False
    assert not [c for c in calls if c[1] == "create"]


def test_assignee_khop_login(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, users=[{"id": 10, "name": "AI Accounting", "login": "ai-accounting"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="ai-accounting"))
    assert out["ok"] is True
    vals = [c for c in calls if c[1] == "create"][0][2][0]
    assert vals["user_id"] == 10


def test_assignee_khong_tim_thay_thi_tu_choi(crm_mod, log_activity_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls, users=[]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="Nguyễn Bịa"))
    assert out["ok"] is False
    assert "Nguyễn Bịa" in out["display"]
    assert not [c for c in calls if c[1] == "create"]


def test_assignee_trung_nhieu_thi_tu_choi_va_liet_ke(crm_mod, log_activity_fn, monkeypatch):
    """KHÔNG tự chọn khi mơ hồ — fail-closed, giống mọi chỗ khác trong dự án."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(
        calls, users=[{"id": 5, "name": "Marc Demo", "login": "demo"},
                      {"id": 6, "name": "Marc Khác", "login": "marc2"}]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 9)
    out = json.loads(log_activity_fn("sale.order", 119, "To-Do", "x",
                                     assignee="Marc"))
    assert out["ok"] is False
    assert "Marc Demo" in out["display"] and "Marc Khác" in out["display"]
    assert not [c for c in calls if c[1] == "create"]
