"""Mục 17b — vệt kiểm toán cho đường ĐỌC."""
import json

import pytest

from src.erp_query import audit
from src.erp_query.tools import build_erp_query_tools
from src.phien import NGUOI_DUNG_HIEN_TAI


@pytest.fixture
def bat_ghi(monkeypatch):
    """Thay chỗ ghi DB bằng một danh sách — conftest đã tắt DATABASE_URL."""
    ghi = []
    monkeypatch.setattr(audit, "ghi_luot_doc",
                        lambda *a, **k: ghi.append((a, k)))
    return ghi


def _tool(ten="find_customer", role="warehouse"):
    from src.agents import roles as r
    ts = {t.name: t for t in build_erp_query_tools(r.load_profile()[role])}
    return ts[ten]


def test_khong_cau_hinh_DB_thi_khong_ghi_va_khong_nem(monkeypatch):
    """"Không cấu hình = tắt log" là thiết kế có chủ ý, khớp event_log.py."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert audit._db() is None
    audit.ghi_luot_doc("find_customer", "erp_query/warehouse", {"name": "X"}, 5)


def test_ghi_LUU_GIA_TRI_tham_so_chu_khong_chi_digest():
    """Quyết định chủ dự án 2026-08-23 (phương án B), NGƯỢC với đường ghi.

    Ở đường ĐỌC chính tham số mới là câu trả lời: "có người xem công nợ" không
    dùng được, "xem công nợ của Azure Interior" mới dùng được."""
    got = audit._tham_so_json({"name": "Azure Interior", "limit": 5})
    assert "Azure Interior" in got
    assert json.loads(got) == {"name": "Azure Interior", "limit": 5}


def test_tham_so_qua_dai_bi_CAT_chu_khong_bi_bo():
    got = audit._tham_so_json({"name": "x" * (audit.ARGS_JSON_MAX + 500)})
    assert len(got) <= audit.ARGS_JSON_MAX + 20
    assert got.endswith("…[cắt]")


def test_tham_so_khong_json_duoc_thi_tra_None_chu_khong_nem():
    class _La:
        def __repr__(self):
            raise RuntimeError("hỏng")

    assert audit._tham_so_json({"x": _La()}) is None


def test_moi_loi_goi_tool_sinh_DUNG_MOT_dong(bat_ghi):
    t = _tool()
    try:
        t.func(name="Azure")
    except Exception:
        pass
    assert len(bat_ghi) == 1
    vi_tri, _ = bat_ghi[0]
    ten, caller, kwargs = vi_tri[0], vi_tri[1], vi_tri[2]
    assert ten == "find_customer"
    assert caller == "erp_query/warehouse"
    assert kwargs == {"name": "Azure"}


def test_caller_mang_TEN_VAI():
    """Không có tên vai thì không trả lời được "vai nào đã đọc"."""
    for vai in ("warehouse", "accounting", "sales"):
        t = _tool(role=vai)
        assert t is not None
    from src.agents import roles as r
    ts = build_erp_query_tools(r.load_profile()["sales"])
    assert ts, "rỗng thì test vô nghĩa"


def test_tool_HONG_van_ghi_va_van_nem_tiep(bat_ghi, monkeypatch):
    """Vệt kiểm toán phải ghi CẢ lượt hỏng — "ai đã cố đọc gì" là câu hỏi của
    điều tra. Và nó KHÔNG được nuốt exception: nuốt sẽ biến một lỗi thành một
    câu trả lời rỗng."""
    t = _tool()
    from src.erp_query import sales as sales_mod
    monkeypatch.setattr(sales_mod, "find_customer",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    with pytest.raises(ValueError):
        t.func(name="Azure")
    assert len(bat_ghi) == 1
    vi_tri, kw = bat_ghi[0]
    loi = kw.get("error") if "error" in kw else (vi_tri[4] if len(vi_tri) > 4 else None)
    assert loi == "ValueError", f"phải ghi LOẠI lỗi, nhận {loi!r}"


def test_boc_KHONG_lam_mat_ten_mo_ta_hay_schema():
    """Bọc mà đổi metadata thì phía LLM thấy khác — bộ tool là hợp đồng với
    model, không phải chi tiết nội bộ."""
    t = _tool()
    assert t.name == "find_customer"
    assert "khách hàng" in t.description
    assert sorted(t.args) == ["name"]


def test_MOI_tool_doc_deu_duoc_boc():
    """Rào chống trôi: thêm tool đọc mới mà quên bọc thì nó im lặng không có
    vệt kiểm toán — đúng lớp lỗi mà mục 17b đi đóng."""
    from src.agents import roles as r
    ts = build_erp_query_tools(r.load_profile()["admin"])
    assert len(ts) >= 28
    chua_boc = [t.name for t in ts
                if getattr(t.func, "__wrapped__", None) is None]
    assert not chua_boc, f"tool đọc chưa được bọc ghi vết: {chua_boc}"
