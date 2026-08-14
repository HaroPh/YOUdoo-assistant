"""find_my_activities — ứng viên cho coordinator đóng việc.

Lọc theo get_uid() (tài khoản Odoo đã xác thực của vai), KHÔNG theo một chuỗi
login suy ra từ tên vai: đây là cùng lớp cưỡng chế mà close_activity dựa vào.

"Đang mở" = active=True, và Odoo lọc như vậy theo MẶC ĐỊNH. Đo 2026-08-14:
action_feedback đặt active=False chứ KHÔNG xoá bản ghi (spec §1.1), nên truyền
active_test=False ở đây sẽ lôi cả việc đã đóng vào danh sách ứng viên và cho
phép đóng lại một việc đã xong."""
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
        import server  # noqa: F401
    finally:
        sys.path.remove(str(MCP_DIR))
    return sys.modules["tools.crm"]


@pytest.fixture(scope="module")
def find_fn(crm_mod):
    import server
    return server.mcp._tool_manager._tools["find_my_activities"].fn


ROW = {"id": 55, "summary": "Kho đề nghị: phát hành hóa đơn",
       "res_model": "sale.order", "res_id": 12, "res_name": "S00012",
       "date_deadline": "2026-08-20"}


def _fake_odoo(calls, rows=(ROW,)):
    def odoo(model, method, args, kw=None):
        calls.append((model, method, args, kw))
        return list(rows)

    return odoo


def test_luon_loc_theo_tai_khoan_dang_goi(crm_mod, find_fn, monkeypatch):
    """Phép thử phá nhắm vào test này: gỡ leaf user_id thì nó phải đỏ."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    domain = calls[0][2][0]
    assert ["user_id", "=", 10] in domain


def test_khong_truyen_active_test_false(crm_mod, find_fn, monkeypatch):
    """Việc đã đóng vẫn CÒN bản ghi (chỉ active=False). Truyền active_test=False
    sẽ cho đóng lại một việc đã xong."""
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    kw = calls[0][3] or {}
    assert "active_test" not in json.dumps(kw)


def test_loc_them_theo_chung_tu_khi_duoc_neu(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn(res_model="sale.order", res_id=12)

    domain = calls[0][2][0]
    assert ["res_model", "=", "sale.order"] in domain
    assert ["res_id", "=", 12] in domain


def test_khong_neu_chung_tu_thi_khong_loc_theo_chung_tu(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    domain = calls[0][2][0]
    assert not [leaf for leaf in domain if leaf[0] in ("res_model", "res_id")]


def test_tra_ve_du_truong_de_hien_thi_va_chon(crm_mod, find_fn, monkeypatch):
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo([]))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(find_fn())

    assert out["ok"] is True
    row = out["rows"][0]
    for field in ("id", "summary", "res_name", "date_deadline"):
        assert field in row


def test_sap_theo_han_gan_nhat_truoc(crm_mod, find_fn, monkeypatch):
    calls = []
    monkeypatch.setattr(crm_mod, "odoo", _fake_odoo(calls))
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    find_fn()

    assert (calls[0][3] or {}).get("order") == "date_deadline asc"


def test_odoo_hong_thi_tra_ok_false_khong_vo(crm_mod, find_fn, monkeypatch):
    def odoo_error(*a, **k):
        raise Exception("Odoo sập")

    monkeypatch.setattr(crm_mod, "odoo", odoo_error)
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(find_fn())
    assert out["ok"] is False and out["rows"] == []


def test_loi_tra_ve_dung_hop_dong_khong_thua_khoa(crm_mod, find_fn, monkeypatch):
    """Lỗi trả về ĐÚNG hợp đồng: chỉ hai khoá {"ok", "rows"}, không thua khoá nào."""
    def odoo_error(*a, **k):
        raise Exception("Odoo sập")

    monkeypatch.setattr(crm_mod, "odoo", odoo_error)
    monkeypatch.setattr(crm_mod, "get_uid", lambda: 10)
    out = json.loads(find_fn())
    assert set(out) == {"ok", "rows"}
