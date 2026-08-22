"""Wire to Odoo. Transport is swappable (XML-RPC today, JSON-2 later); it carries
NO policy — the gateway does. Keep this file free of any allowlist/limit logic so
the JSON-2 swap stays a one-file change."""
import os
from typing import Any, Protocol
import xmlrpc.client

# Trần thời gian cho MỘT lời gọi XML-RPC tới Odoo.
#
# Trước 2026-08-22 KHÔNG có trần nào: `ServerProxy` mặc định dùng timeout của
# socket toàn cục, mà nơi này không đặt gì cả ⇒ Odoo treo là lượt chat của
# người dùng treo THEO, vô hạn. Không có thông báo, không có đường thoát —
# người dùng chỉ thấy màn hình đứng im.
#
# 30 giây: dài hơn mọi truy vấn lành mạnh đã đo (read_group nặng nhất ~1-2s),
# và vẫn ngắn hơn ngưỡng kiên nhẫn của người đang chờ một câu trả lời.
ODOO_TIMEOUT_S = float(os.environ.get("ODOO_TIMEOUT_S", "30"))


def _transport_co_timeout(url: str, timeout: float):
    """`ServerProxy` KHÔNG nhận tham số timeout — phải bọc qua Transport.

    Chọn lớp cơ sở theo scheme: `SafeTransport` cho https, `Transport` cho
    http. Dùng nhầm lớp thì kết nối hỏng chứ không phải chỉ mất timeout.
    """
    base = (xmlrpc.client.SafeTransport if url.lower().startswith("https")
            else xmlrpc.client.Transport)

    class _CoTimeout(base):
        def make_connection(self, host):
            conn = super().make_connection(host)
            conn.timeout = timeout
            return conn

    return _CoTimeout()


class Transport(Protocol):
    def call(self, model: str, method: str, args: list, kwargs: dict) -> Any: ...


class XmlRpcTransport:
    """Odoo XML-RPC via execute_kw (Odoo 19; deprecated, removed in Odoo 20)."""

    def __init__(self, url: str, db: str, user: str, password: str) -> None:
        self._url, self._db, self._user, self._pwd = url, db, user, password
        self._uid: int | None = None

    def _uid_(self) -> int:
        if self._uid is None:
            common = xmlrpc.client.ServerProxy(
                self._url + "/xmlrpc/2/common",
                transport=_transport_co_timeout(self._url, ODOO_TIMEOUT_S))
            self._uid = common.authenticate(self._db, self._user, self._pwd, {})
            if not self._uid:
                raise RuntimeError("Odoo authentication failed — kiểm tra ODOO_USERNAME/PASSWORD")
        return self._uid

    def call(self, model: str, method: str, args: list, kwargs: dict) -> Any:
        uid = self._uid_()
        obj = xmlrpc.client.ServerProxy(
            self._url + "/xmlrpc/2/object",
            transport=_transport_co_timeout(self._url, ODOO_TIMEOUT_S))
        return obj.execute_kw(self._db, uid, self._pwd, model, method, args, kwargs or {})


class Json2Transport:
    """Placeholder for the Odoo 19 JSON-2 (/json/2/) + API-key path. Implement when
    migrating off XML-RPC; the gateway above is unaffected."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url, self._api_key = base_url, api_key

    def call(self, model: str, method: str, args: list, kwargs: dict) -> Any:
        raise NotImplementedError("JSON-2 transport chưa triển khai — dùng XmlRpcTransport.")
