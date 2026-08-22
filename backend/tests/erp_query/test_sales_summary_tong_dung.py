# backend/tests/erp_query/test_sales_summary_tong_dung.py
"""`sales_summary` phải trả TỔNG ĐẦY ĐỦ, không phụ thuộc số khách hàng.

Lỗi tìm ra ở đợt kiểm toán 2026-08-22: tổng doanh thu được cộng từ các nhóm
partner đã bị cắt `limit=100` và KHÔNG có `orderby`. Doanh nghiệp trên 100
khách bị báo THIẾU doanh thu — im lặng, không cờ, không cảnh báo.

Đây là kiểu sai nguy hiểm nhất với một con số tài chính: nó **trông hợp lý**
nên không ai kiểm lại. Với 250 khách mỗi khách 1.000, bản cũ trả 100.000 thay
vì 250.000 — thiếu 60%, mà báo cáo vẫn in ra một con số tròn trịa.
"""
from src.erp_query import sales


class _GatewayGia:
    """Phân biệt hai lời gọi: có groupby (bị cắt) và không groupby (tổng thật)."""

    def __init__(self, so_khach: int, tien_moi_khach: float = 1_000.0) -> None:
        self.so_khach = so_khach
        self.tien = tien_moi_khach
        self.goi = []

    def read_group(self, model, domain, fields, groupby,
                   orderby=None, limit=None, lazy=False):
        self.goi.append({"groupby": groupby, "orderby": orderby, "limit": limit})
        if not groupby:
            return [{"amount_total": self.so_khach * self.tien}]
        n = min(self.so_khach, limit or self.so_khach)
        return [{"partner_id": [i, f"KH{i}"], "amount_total": self.tien}
                for i in range(n)]


def _tom(out):
    return out["data"] if "data" in out else out


def test_tong_dung_khi_duoi_tran():
    gw = _GatewayGia(so_khach=50)
    d = _tom(sales.sales_summary(gw=gw))
    assert d["total"] == 50 * 1_000
    assert d["capped"] is False


def test_tong_VAN_DUNG_khi_vuot_tran_nhom():
    """Ca hồi quy chính. Bản cũ trả `TRAN_NHOM_KHACH * tiền` thay vì tổng thật."""
    gw = _GatewayGia(so_khach=250)
    d = _tom(sales.sales_summary(gw=gw))
    assert d["total"] == 250 * 1_000, "tổng bị cắt theo trần nhóm — lỗi cũ tái phát"
    assert d["total"] != sales.TRAN_NHOM_KHACH * 1_000


def test_vuot_tran_thi_GAN_CO_capped_va_noi_ro_trong_van_ban():
    """Bảng phân rã bị cắt là chấp nhận được; **giấu chuyện đó** thì không."""
    out = sales.sales_summary(gw=_GatewayGia(so_khach=250))
    d = _tom(out)
    assert d["capped"] is True
    assert len(d["by_partner"]) == sales.TRAN_NHOM_KHACH
    # `display` là trường người dùng THẬT SỰ đọc (envelope dùng khoá này, không
    # phải "message" — kiểm bằng cách in ra vỏ thật chứ không đoán tên khoá).
    van_ban = out.get("display") or ""
    assert "tổng ở trên vẫn là tổng ĐẦY ĐỦ" in van_ban


def test_nhom_khach_lay_theo_orderby_giam_dan():
    """Không có `orderby`, 100 nhóm giữ lại là 100 khách TUỲ Ý — nên "Top khách"
    có thể bỏ sót đúng khách lớn nhất. Đây là nửa thứ hai của lỗi cũ."""
    gw = _GatewayGia(so_khach=250)
    sales.sales_summary(gw=gw)
    co_groupby = [g for g in gw.goi if g["groupby"]]
    assert co_groupby and co_groupby[0]["orderby"] == "amount_total desc"


def test_dung_HAI_loi_goi_mot_co_groupby_mot_khong():
    """Khoá chính cơ chế: tổng đến từ lời gọi KHÔNG groupby. Ai đó gộp lại
    thành một lời gọi cho "gọn" là làm lỗi cũ sống lại."""
    gw = _GatewayGia(so_khach=10)
    sales.sales_summary(gw=gw)
    assert [bool(g["groupby"]) for g in gw.goi] == [False, True]
