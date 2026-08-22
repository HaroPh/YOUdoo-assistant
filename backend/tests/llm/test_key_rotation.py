# backend/tests/llm/test_key_rotation.py
"""Xoay khoá API bên trong một mắt xích (mục 7, 2026-08-21).

Hạn mức free tier của Google tính theo **project**, nên hai khoá của hai
project là HAI VÍ RIÊNG. Trước bản này, cạn khoá duy nhất là cạn cho cả hệ:
`providers.ENV_KEYS` chỉ ánh xạ một biến môi trường mỗi upstream.

Xoay BÊN TRONG một mắt xích, KHÔNG thành mắt xích mới — bất biến #1 (không hai
mắt xích chung upstream) tồn tại để tránh rơi từ miền lỗi này vào lại chính nó,
còn đây là cùng miền nhưng khác ví.

Số khoá ở mọi test dưới đây là DỮ LIỆU CỦA TEST, không phải của môi trường:
fixture `mot_khoa_moi_provider` (conftest) dọn sạch hậu tố trước mỗi test, rồi
test tự khai đúng số nó cần.
"""
import pytest
from langchain_core.messages import HumanMessage

from src.llm.budget import BudgetLedger
from src.llm.providers import keys_for
from src.llm.router import Router
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import (FakeChatClient, FakeRateLimit, FakeServerError,
                                fake_ai)

MSGS = [HumanMessage("Tồn kho ABC?")]
MAT_XICH_DAU = "gemini-3.1-flash-lite"       # mắt xích 1 của mọi vai
MAT_XICH_HAI = "groq-gpt-oss-120b"           # mắt xích cuối (khác upstream)


def _ba_khoa(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "k1")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "k2")
    monkeypatch.setenv("GOOGLE_API_KEY_3", "k3")


def _router_theo_khoa(clock, theo_khoa: dict, khac: dict | None = None):
    """client_factory phân biệt theo (alias, api_key) — đây là điểm mấu chốt:
    nếu Router không thật sự truyền khoá xuống, mọi test dưới đây sẽ nhận cùng
    một client giả và không đo được gì."""
    khac = khac or {}
    ledger = BudgetLedger(InMemoryUsageStore(), clock=clock)

    def factory(spec, api_key=None):
        if spec.alias in khac:
            return khac[spec.alias]
        return theo_khoa[api_key]

    return Router(ledger, client_factory=factory)


def test_429_o_khoa_dau_thi_xoay_khoa_chu_KHONG_tut_mat_xich(clock, monkeypatch):
    """Đây là toàn bộ mục đích của cơ chế: cạn một ví thì tiêu ví kế, KHÔNG
    tụt xuống model yếu hơn."""
    _ba_khoa(monkeypatch)
    k1 = FakeChatClient([FakeRateLimit("quá hạn mức")])
    k2 = FakeChatClient([fake_ai("ok")])
    r = _router_theo_khoa(clock, {"k1": k1, "k2": k2, "k3": FakeChatClient([])})

    got = r.invoke("read", MSGS)
    assert got.message.content == "ok"
    assert got.decision.spec.alias == MAT_XICH_DAU, "không được tụt mắt xích"
    assert got.decision.fallback_depth == 0
    assert len(k1.calls) == 1 and len(k2.calls) == 1


def test_luot_sau_bat_dau_tu_khoa_DANG_DUNG(clock, monkeypatch):
    """Nhớ khoá đang dùng, nếu không thì mỗi lượt đều phải trả giá một cú 429
    cho cái ví đã biết là cạn."""
    _ba_khoa(monkeypatch)
    k1 = FakeChatClient([FakeRateLimit("quá hạn mức")])
    k2 = FakeChatClient([fake_ai("ok"), fake_ai("ok2")])
    r = _router_theo_khoa(clock, {"k1": k1, "k2": k2, "k3": FakeChatClient([])})

    r.invoke("read", MSGS)
    r.invoke("read", MSGS)
    assert len(k1.calls) == 1, "không được hỏi lại cái ví vừa báo cạn"
    assert len(k2.calls) == 2


def test_loi_KHONG_phai_429_thi_KHONG_xoay_khoa(clock, monkeypatch):
    """Lỗi 5xx/404 là hỏng phía nhà cung cấp — đổi khoá không liên quan, chỉ
    đốt thêm lượt gọi cho một thứ đang hỏng."""
    _ba_khoa(monkeypatch)
    k1 = FakeChatClient([FakeServerError("sập")])
    k2 = FakeChatClient([fake_ai("khong-duoc-goi")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router_theo_khoa(clock, {"k1": k1, "k2": k2, "k3": FakeChatClient([])},
                          khac={MAT_XICH_HAI: tot})

    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == MAT_XICH_HAI, "5xx phải tụt mắt xích"
    assert k2.calls == [], "lỗi không phải 429 mà vẫn xoay khoá"


def test_het_khoa_moi_cooldown_va_tut_mat_xich(clock, monkeypatch):
    _ba_khoa(monkeypatch)
    hong = [FakeChatClient([FakeRateLimit("quá hạn mức")]) for _ in range(3)]
    tot = FakeChatClient([fake_ai("ok")])
    r = _router_theo_khoa(clock,
                          {"k1": hong[0], "k2": hong[1], "k3": hong[2]},
                          khac={MAT_XICH_HAI: tot})

    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == MAT_XICH_HAI
    assert all(len(h.calls) == 1 for h in hong), "phải thử ĐỦ ba ví trước khi bỏ"


def test_het_khoa_thi_DAT_LAI_ve_khoa_dau(clock, monkeypatch):
    """Hạn mức ngày của Google là cửa sổ TRƯỢT 24h (đo 2026-08-21: model vừa
    báo PerDayPerProjectPerModel trả 200 lại sau vài phút). Giữ nguyên ở khoá
    cuối là tự khoá mình vào cái ví cạn gần nhất."""
    _ba_khoa(monkeypatch)
    r = _router_theo_khoa(clock, {k: FakeChatClient([]) for k in ("k1", "k2", "k3")})
    spec = r.resolve("read", 100).spec

    assert r._xoay_khoa(spec) is True and r._chi_so_khoa[spec.alias] == 1
    assert r._xoay_khoa(spec) is True and r._chi_so_khoa[spec.alias] == 2
    assert r._xoay_khoa(spec) is False
    assert r._chi_so_khoa[spec.alias] == 0, "hết khoá phải đặt lại về khoá đầu"


def test_mot_khoa_thi_khong_xoay_duoc(clock, monkeypatch):
    """Đối chứng: máy chỉ cấu hình một khoá phải giữ NGUYÊN hành vi cũ."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k1")
    assert len(keys_for("google")) == 1
    hong = FakeChatClient([FakeRateLimit("quá hạn mức")])
    tot = FakeChatClient([fake_ai("ok")])
    r = _router_theo_khoa(clock, {"k1": hong}, khac={MAT_XICH_HAI: tot})

    got = r.invoke("read", MSGS)
    assert got.decision.spec.alias == MAT_XICH_HAI
    assert len(hong.calls) == 1


@pytest.mark.asyncio
async def test_xoay_khoa_o_ca_duong_BAT_DONG_BO(clock, monkeypatch):
    """Hai cửa (invoke + ainvoke) là hai chỗ để quên một nửa — production chạy
    đường bất đồng bộ."""
    _ba_khoa(monkeypatch)
    k1 = FakeChatClient([FakeRateLimit("quá hạn mức")])
    k2 = FakeChatClient([fake_ai("ok")])
    r = _router_theo_khoa(clock, {"k1": k1, "k2": k2, "k3": FakeChatClient([])})

    got = await r.ainvoke("read", MSGS)
    assert got.message.content == "ok"
    assert got.decision.spec.alias == MAT_XICH_DAU
    assert len(k1.calls) == 1 and len(k2.calls) == 1
