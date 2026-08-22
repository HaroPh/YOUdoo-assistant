# backend/tests/erp_query/test_transport_timeout.py
"""XML-RPC tới Odoo phải có TRẦN THỜI GIAN.

Trước 2026-08-22 `ServerProxy` được dựng trần, không transport, không timeout —
nên nó dùng timeout socket toàn cục, mà nơi này không đặt gì. Hệ quả: Odoo treo
thì lượt chat của người dùng treo THEO, vô hạn, không thông báo, không đường
thoát. Người dùng chỉ thấy màn hình đứng im.

Không test được bằng cách dựng một Odoo treo thật, nhưng test được thứ QUYẾT
ĐỊNH hành vi đó: transport có thật sự mang timeout xuống tận connection không.
"""
import xmlrpc.client

import pytest

from src.erp_query.transport import (ODOO_TIMEOUT_S, XmlRpcTransport,
                                     _transport_co_timeout)


def test_timeout_di_xuong_tan_connection():
    """`make_connection` là nơi duy nhất đặt được timeout — nếu bản sửa chỉ
    dựng transport mà không chạm connection thì test này đỏ."""
    t = _transport_co_timeout("http://odoo.local:8069", 12.5)
    conn = t.make_connection("odoo.local:8069")
    assert conn.timeout == 12.5


def test_https_dung_SafeTransport_http_dung_Transport():
    """Dùng nhầm lớp cơ sở thì kết nối hỏng, không chỉ mất timeout."""
    assert isinstance(_transport_co_timeout("https://odoo.example.com", 5),
                      xmlrpc.client.SafeTransport)
    t = _transport_co_timeout("http://odoo.local:8069", 5)
    assert isinstance(t, xmlrpc.client.Transport)
    assert not isinstance(t, xmlrpc.client.SafeTransport)


def test_tran_mac_dinh_co_gia_tri_huu_han():
    """Bất biến rẻ nhất: nếu ai đó đặt về 0/None để "bỏ giới hạn", lỗi cũ sống
    lại nguyên vẹn."""
    assert ODOO_TIMEOUT_S and ODOO_TIMEOUT_S > 0


def test_ca_HAI_endpoint_deu_duoc_boc(monkeypatch):
    """`authenticate` và `execute_kw` là HAI ServerProxy khác nhau. Bọc một
    cái quên cái kia là để hở đúng một nửa — và nửa bị hở (`execute_kw`) lại
    là nửa chạy ở MỌI lời gọi, không chỉ lượt đăng nhập đầu.
    """
    da_dung = []

    class _ProxyGia:
        def __init__(self, url, transport=None, **kw):
            da_dung.append(transport)

        def authenticate(self, *a, **k):
            return 7

        def execute_kw(self, *a, **k):
            return []

    monkeypatch.setattr(xmlrpc.client, "ServerProxy", _ProxyGia)
    XmlRpcTransport("http://odoo.local:8069", "db", "u", "p").call(
        "res.partner", "search_read", [[]], {})

    assert len(da_dung) == 2, "phải dựng đúng 2 ServerProxy (common + object)"
    assert all(t is not None for t in da_dung), (
        "có endpoint dựng ServerProxy KHÔNG transport ⇒ không có timeout")
