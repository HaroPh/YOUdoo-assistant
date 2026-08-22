# backend/tests/test_main_auth.py
"""Cổng xác thực cho `/v1/*` (mục 14, vá 2026-08-22).

Trước bản vá `/v1` KHÔNG có xác thực nào: backend bind `0.0.0.0:8002` và quyền
được suy DUY NHẤT từ header `x-openwebui-user-id` — một chuỗi client tự khai.
Ai trong cùng LAN gửi header của admin là mở khoá toàn bộ 33 tool ghi Odoo.

Đây không phải suy đoán: lỗ hổng được xác nhận bằng cách KHAI THÁC thật trong
phiên 2026-08-22 (gửi header, không kèm credential nào, nhận toàn quyền admin).
"""
import httpx
import pytest

from src import main as main_module

TOKEN = "token-thu-cho-test"


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://test")


class _AgentGia:
    async def chat(self, *a, **k):
        return "xong"


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch):
    monkeypatch.setenv("YOUDOO_API_TOKEN", TOKEN)
    monkeypatch.setenv("YOUDOO_ROLE_MAP", "uid-thu:admin")
    main_module._state["agent"] = _AgentGia()
    yield
    main_module._state.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("duong_dan", ["/v1/models", "/v1/chat/completions"])
async def test_khong_co_token_thi_401(duong_dan):
    """Kiểm CẢ HAI endpoint. Bọc một cái quên cái kia là để hở đúng một nửa."""
    async with _client() as c:
        r = (await c.get(duong_dan) if duong_dan.endswith("models")
             else await c.post(duong_dan, json={"messages": []}))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_token_SAI_thi_401():
    async with _client() as c:
        r = await c.get("/v1/models",
                        headers={"Authorization": "Bearer token-bay-ba"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_header_khong_dung_khuon_Bearer_thi_401():
    """Gửi token trần, không có tiền tố — phải từ chối chứ không "đoán giúp"."""
    async with _client() as c:
        r = await c.get("/v1/models", headers={"Authorization": TOKEN})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_dung_token_thi_qua():
    async with _client() as c:
        r = await c.get("/v1/models",
                        headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tien_to_Bearer_KHONG_phan_biet_hoa_thuong():
    """Client thật gửi "Bearer", "bearer", có client gửi "BEARER". Từ chối vì
    hoa/thường là một cách hỏng khó chẩn đoán mà không đổi lấy an toàn nào."""
    async with _client() as c:
        r = await c.get("/v1/models",
                        headers={"Authorization": f"bearer {TOKEN}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_health_VAN_MO(monkeypatch):
    """`/health` cố ý không cần token: `start-dev.ps1` và mọi phép kiểm sẵn
    sàng đều gọi nó, và nó không tiết lộ gì. Đóng nó lại là làm hỏng khởi động
    mà không mua thêm an toàn."""
    async with _client() as c:
        r = await c.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_THIEU_bien_moi_truong_thi_TU_CHOI_chu_khong_mo_toang(monkeypatch):
    """Quyết định fail-closed (chủ dự án chốt phương án A).

    Đây là nửa quan trọng nhất của bản vá. Nếu thiếu cấu hình mà hệ vẫn chạy
    "tạm thời không xác thực" thì lỗ hổng quay lại IM LẶNG đúng vào lúc người
    ta quên — cùng lớp với chân sparse chết, reranker chết, guardrail fail-open
    không log. Một cổng an toàn có thể tự tắt vì thiếu cấu hình thì không phải
    cổng an toàn.
    """
    monkeypatch.delenv("YOUDOO_API_TOKEN", raising=False)
    async with _client() as c:
        with pytest.raises(RuntimeError, match="YOUDOO_API_TOKEN"):
            await c.get("/v1/models", headers={"Authorization": "Bearer x"})


def test_YOUDOO_FALLBACK_ROLE_da_bi_go_khoi_ma_nguon():
    """Cửa hậu cũ: nó cho một request KHÔNG có danh tính nhận vai bất kỳ, tức
    vô hiệu hoá đúng cổng phân quyền mà roles.py dựng lên. Test này chặn việc
    ai đó thêm lại "cho tiện khi dev"."""
    import pathlib

    nguon = pathlib.Path(main_module.__file__).read_text(encoding="utf-8")
    dong_thuc_thi = [d for d in nguon.splitlines()
                     if "YOUDOO_FALLBACK_ROLE" in d and not d.strip().startswith("#")]
    assert dong_thuc_thi == [], f"cửa hậu quay lại: {dong_thuc_thi}"
