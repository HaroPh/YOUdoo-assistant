"""Mục 17 — vệt kiểm toán ghi được AI ĐÃ GỌI và GỌI CÁI GÌ.

Trước bản này `mcp_call_log` chỉ có `caller = mcp-odoo/<vai>` (tên tiến
trình): trả lời được "AI vai nào", KHÔNG trả lời được ai đã yêu cầu, cũng
không nói được lệnh gọi mang tham số gì.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(scope="module")
def mcp_mods():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import audit_chain
        import event_log
        import verify_audit_chain
    finally:
        sys.path.remove(str(MCP_DIR))
    return audit_chain, event_log, verify_audit_chain


# ── Hằng tên header: hai tiến trình, không nhập chung được ───────────────────

def test_ten_header_KHOP_giua_backend_va_mcp(mcp_mods):
    """Backend gắn header, MCP đọc header — hai tiến trình khác nhau nên hằng
    phải chép tay ở hai nơi. Chép tay thì trôi được, và trôi ở đây KHÔNG làm
    hỏng gì thấy được: tool vẫn chạy, chỉ `http_user` lặng lẽ về NULL mãi mãi.
    Đúng lớp lỗi "thành phần tự tắt trong im lặng" mà repo này gặp nhiều lần.
    """
    _audit, event_log, _verify = mcp_mods
    from src.agents.erp_agent import HEADER_NGUOI_DUNG
    assert HEADER_NGUOI_DUNG == event_log.HEADER_NGUOI_DUNG


# ── Đọc header phía MCP ──────────────────────────────────────────────────────

def test_ngoai_ngu_canh_request_thi_khong_co_nguoi_dung(mcp_mods):
    """Script nội bộ, tác vụ nền, test — không có request nào. NULL trung
    thực hơn là bịa."""
    _audit, event_log, _verify = mcp_mods
    assert event_log._http_user() is None


class _RequestGia:
    def __init__(self, headers):
        self.headers = headers


class _CtxGia:
    def __init__(self, request):
        self.request = request


def test_doc_duoc_header_trong_ngu_canh_request(mcp_mods, monkeypatch):
    _audit, event_log, _verify = mcp_mods
    from mcp.server.lowlevel.server import request_ctx
    token = request_ctx.set(_CtxGia(_RequestGia(
        {event_log.HEADER_NGUOI_DUNG: "nguoi-dung-abc"})))
    try:
        assert event_log._http_user() == "nguoi-dung-abc"
    finally:
        request_ctx.reset(token)


def test_header_qua_dai_bi_CAT_chu_khong_bi_tu_choi(mcp_mods):
    """Header đến từ ngoài. Cắt thay vì từ chối: vệt kiểm toán ghi được thứ
    méo còn hơn không ghi gì."""
    _audit, event_log, _verify = mcp_mods
    from mcp.server.lowlevel.server import request_ctx
    dai = "x" * (event_log.HTTP_USER_MAX + 500)
    token = request_ctx.set(_CtxGia(_RequestGia(
        {event_log.HEADER_NGUOI_DUNG: dai})))
    try:
        assert len(event_log._http_user()) == event_log.HTTP_USER_MAX
    finally:
        request_ctx.reset(token)


def test_request_hong_KHONG_lam_hong_tool(mcp_mods):
    """Một vệt kiểm toán không được là nguồn sự cố."""
    _audit, event_log, _verify = mcp_mods
    from mcp.server.lowlevel.server import request_ctx

    class _No:
        @property
        def headers(self):
            raise RuntimeError("hỏng")

    token = request_ctx.set(_CtxGia(_No()))
    try:
        assert event_log._http_user() is None
    finally:
        request_ctx.reset(token)


# ── Dấu vân tay tham số ──────────────────────────────────────────────────────

def test_args_fingerprint_tra_ve_TEN_truong_khong_tra_ve_gia_tri(mcp_mods):
    """Đánh đổi riêng tư đã chọn (chủ dự án 2026-08-22): tham số mang tên
    khách, số tiền, công nợ — vệt kiểm toán không được thành nơi chứa chúng."""
    audit_chain, _e, _v = mcp_mods
    digest, khoa = audit_chain.args_fingerprint(
        [{"partner_id": 14, "amount_total": 12_500_000}],
        {"context": {"lang": "vi_VN"}})
    assert khoa == ["amount_total", "context", "lang", "partner_id"]
    ca_chuoi = " ".join([digest, *khoa])
    assert "12500000" not in ca_chuoi and "vi_VN" not in ca_chuoi
    assert "14" not in khoa


def test_args_fingerprint_cung_tham_so_thi_cung_digest(mcp_mods):
    audit_chain, _e, _v = mcp_mods
    a = audit_chain.args_fingerprint([{"b": 1, "a": 2}], {"k": 3})
    b = audit_chain.args_fingerprint([{"a": 2, "b": 1}], {"k": 3})
    assert a == b, "thứ tự khoá không được đổi digest"
    khac = audit_chain.args_fingerprint([{"a": 2, "b": 9}], {"k": 3})
    assert khac[0] != a[0], "đổi GIÁ TRỊ phải đổi digest"


def test_args_fingerprint_KHONG_BAO_GIO_nem(mcp_mods):
    audit_chain, _e, _v = mcp_mods

    class _KhongJson:
        def __repr__(self):
            raise RuntimeError("hỏng")

    assert audit_chain.args_fingerprint([_KhongJson()], {}) == (None, [])


def test_args_fingerprint_co_TRAN_do_sau_va_so_khoa(mcp_mods):
    """Đầu vào của người dùng không được quyết định hàm này chạy bao lâu."""
    audit_chain, _e, _v = mcp_mods
    sau = {"k0": None}
    nut = sau
    for i in range(1, 50):
        nut["k%d" % i] = {}
        nut = nut["k%d" % i]
    _d, khoa = audit_chain.args_fingerprint([sau], {})
    assert len(khoa) <= audit_chain.ARGS_KEYS_MAX
    assert len(khoa) <= audit_chain.ARGS_DEPTH_MAX + 1


# ── Ba cột mới PHẢI nằm trong chuỗi hash ─────────────────────────────────────

_DONG = dict(prev_hash="0" * 64,
             created_at=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
             event_type="model_access", caller="mcp-odoo/ai-admin",
             tool_name="get_stock", model_name="stock.quant", operation="read",
             duration_ms=12, error_code=None, error_message=None)


@pytest.mark.parametrize("truong, gia_tri", [
    ("http_user", "ke-tan-cong"),
    ("args_digest", "deadbeefdeadbeef"),
    ("args_keys", ["amount_total"]),
])
def test_doi_mot_trong_BA_COT_MOI_thi_hash_phai_doi(mcp_mods, truong, gia_tri):
    """Nếu ba cột này nằm NGOÀI chuỗi băm thì đúng hai thứ quý nhất của một
    cuộc điều tra — ai đã gọi và gọi CÁI GÌ — sửa được mà verify vẫn báo xanh.

    Đây là lý do chấp nhận đứt chuỗi MỘT LẦN ở migration 005 thay vì đánh
    phiên bản hàm băm.
    """
    audit_chain, _e, _v = mcp_mods
    goc = audit_chain.compute_entry_hash(**_DONG)
    sua = audit_chain.compute_entry_hash(**_DONG, **{truong: gia_tri})
    assert goc != sua, f"{truong} không ảnh hưởng entry_hash ⇒ sửa được mà không lộ"


def test_verify_doc_DU_ba_cot_moi(mcp_mods):
    """Cột thiếu trong `_COLUMNS` = cột nằm ngoài phép kiểm. Test này là rào
    chống trôi giữa bên GHI (event_log) và bên KIỂM (verify_audit_chain)."""
    _a, _e, verify_audit_chain = mcp_mods
    for cot in ("http_user", "args_digest", "args_keys"):
        assert cot in verify_audit_chain._COLUMNS


# ── Interceptor phía backend ────────────────────────────────────────────────

class _YeuCauGia:
    def __init__(self, headers=None):
        self.headers = headers

    def override(self, **kw):
        moi = _YeuCauGia(self.headers)
        for k, v in kw.items():
            setattr(moi, k, v)
        return moi


async def _bat(request):
    return request


@pytest.mark.asyncio
async def test_interceptor_gan_nguoi_dung_vao_header():
    from src.agents.erp_agent import (HEADER_NGUOI_DUNG, NGUOI_DUNG_HIEN_TAI,
                                      _gan_nguoi_dung_vao_header)
    token = NGUOI_DUNG_HIEN_TAI.set("db5db1c8-ai-do")
    try:
        ra = await _gan_nguoi_dung_vao_header(_YeuCauGia({"x": "y"}), _bat)
    finally:
        NGUOI_DUNG_HIEN_TAI.reset(token)
    assert ra.headers[HEADER_NGUOI_DUNG] == "db5db1c8-ai-do"
    assert ra.headers["x"] == "y", "header sẵn có không được mất"


@pytest.mark.asyncio
async def test_khong_co_nguoi_dung_thi_KHONG_gan_gi():
    """Script nội bộ/tác vụ nền: `http_user` NULL trung thực hơn giá trị bịa.

    Cũng là ca đối chứng cho test trên — nếu header xuất hiện ở CẢ HAI ca thì
    nó đến từ đâu đó khác, và test kia không đo interceptor.
    """
    from src.agents.erp_agent import (HEADER_NGUOI_DUNG, NGUOI_DUNG_HIEN_TAI,
                                      _gan_nguoi_dung_vao_header)
    token = NGUOI_DUNG_HIEN_TAI.set(None)
    try:
        ra = await _gan_nguoi_dung_vao_header(_YeuCauGia({"x": "y"}), _bat)
    finally:
        NGUOI_DUNG_HIEN_TAI.reset(token)
    assert HEADER_NGUOI_DUNG not in (ra.headers or {})


@pytest.mark.asyncio
async def test_client_MCP_that_su_duoc_gan_interceptor():
    """Rào chống "viết interceptor rồi quên nối vào".

    Đọc thẳng mã nguồn `setup`: dựng ERPAgent thật ở đây sẽ kéo theo
    Postgres + ba tiến trình MCP, tức test sẽ skip trên máy sạch và rào biến
    mất đúng lúc cần nhất.
    """
    import inspect
    from src.agents import erp_agent as EA
    src = inspect.getsource(EA.ERPAgent.setup)
    assert "tool_interceptors" in src
    assert "_gan_nguoi_dung_vao_header" in src
