from src.erp_query import crm


class FakeGateway:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search_read(self, model, domain, fields, order=None, limit=50,
                    context=None):
        self.calls.append({"model": model, "domain": domain, "fields": fields,
                           "order": order, "limit": limit})
        return self.rows


def test_loc_theo_login_duoc_truyen_vao_khong_phai_tai_khoan_hien_tai():
    """Đường đọc chạy bằng ai-readonly còn đường ghi chạy bằng tài khoản vai —
    lọc theo 'người dùng hiện tại' sẽ trả về việc của ai-readonly, SAI NGƯỜI."""
    gw = FakeGateway([])
    crm.list_my_activities("ai-accounting", gw=gw)

    goi = gw.calls[0]
    assert goi["model"] == "mail.activity"
    assert ["user_id.login", "=", "ai-accounting"] in goi["domain"]


def test_sap_theo_han_gan_nhat_truoc():
    gw = FakeGateway([])
    crm.list_my_activities("ai-accounting", gw=gw)
    assert "date_deadline" in (gw.calls[0]["order"] or "")


def test_tra_ve_cac_truong_can_de_hien_thi():
    gw = FakeGateway([{"id": 1, "summary": "Kho đề nghị: phát hành hóa đơn",
                       "res_model": "sale.order", "res_name": "S00012",
                       "date_deadline": "2026-08-15",
                       "user_id": [10, "ai-accounting"]}])
    got = crm.list_my_activities("ai-accounting", gw=gw)

    # envelope.ok() trả status="success" (không phải "ok") — xác nhận qua
    # backend/src/erp_query/envelope.py, brief ghi nhầm.
    assert got["status"] == "success"
    assert got["data"]["rows"][0]["res_name"] == "S00012"
    assert "S00012" in got["display"]


def test_khong_co_viec_nao_thi_noi_ro():
    got = crm.list_my_activities("ai-accounting", gw=FakeGateway([]))
    assert got["status"] == "success"
    assert got["data"]["rows"] == []
    assert "không có" in got["display"].lower()


def test_gateway_hong_thi_tra_loi_khong_vo():
    class Hong:
        def search_read(self, *a, **k):
            raise RuntimeError("Odoo sập")

    got = crm.list_my_activities("ai-accounting", gw=Hong())
    assert got["status"] == "error"
