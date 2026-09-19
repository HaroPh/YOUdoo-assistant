"""`ocr/vision.py` — máy đọc VLM, test bằng client giả (không API).

Bốn thứ của nền phải đúng TRƯỚC lượt gọi thật đầu tiên (spec §18): khoá riêng
tắt/mở, xoay chỉ khi 429 và hết vòng thì dừng, trần cứng, ghi sổ `vlm-ocr`.
Cộng bẫy đã trả giá hai lần: `.content` là list khối, không phải str.
"""
import json
from types import SimpleNamespace

import pytest

from src.ocr import vision
from src.ocr.vision import (VisionBadResponse, VisionCapReached, VisionQuotaExhausted,
                            VisionReader, VisionUnavailable)

_PAYLOAD = {"trang": {"mau": "B01/BCTC", "thong_tu": "107/2017/TT-BTC",
                      "cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
            "hang": [{"muc": "I.", "nhan": "Tiền", "ma_so": "01", "thuyet_minh": None,
                      "so_tien": ["750.005.854", "40.565.652.481"]}]}


class _Resp:
    def __init__(self, content, usage=None):
        self.content = content
        self.usage_metadata = usage or {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}


class _Client:
    """Client giả: kịch bản là list các phản hồi hoặc exception theo lượt gọi."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def invoke(self, msgs):
        self.calls += 1
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class _Store:
    def __init__(self):
        self.rows = []

    def record(self, **kw):
        self.rows.append(kw)


@pytest.fixture
def khoa(monkeypatch):
    for i in range(2, 10):
        monkeypatch.delenv(f"YOUDOO_VLM_API_KEY_{i}", raising=False)
    monkeypatch.setenv("YOUDOO_VLM_API_KEY", "vlm-a")
    monkeypatch.setenv("YOUDOO_VLM_API_KEY_2", "vlm-b")
    monkeypatch.setenv("GOOGLE_API_KEY", "chat-KHONG-DUOC-DUNG")


def _factory(clients_by_key: dict):
    seen = []

    def f(spec, api_key):
        seen.append((spec.alias, api_key))
        return clients_by_key[api_key]
    f.seen = seen
    return f


def test_khong_co_khoa_thi_tat_han_va_khong_dung_client(monkeypatch):
    monkeypatch.delenv("YOUDOO_VLM_API_KEY", raising=False)
    for i in range(2, 10):
        monkeypatch.delenv(f"YOUDOO_VLM_API_KEY_{i}", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "chat")
    assert not vision.vlm_enabled()
    r = VisionReader(client_factory=lambda s, k: pytest.fail("không được dựng client"))
    with pytest.raises(VisionUnavailable):
        r.read_table(b"png")
    assert r.calls == 0


def test_doc_duoc_bang_va_ghi_so_vlm_ocr_bang_khoa_rieng(khoa):
    c = _Client([_Resp("```json\n" + json.dumps(_PAYLOAD, ensure_ascii=False) + "\n```")])
    store = _Store()
    r = VisionReader(client_factory=_factory({"vlm-a": c}), store=store)
    t = r.read_table(b"png")
    assert t.payload == _PAYLOAD and t.prompt_version == vision.PROMPT_VERSION
    assert t.total_tokens == 1500
    assert store.rows == [dict(ts=store.rows[0]["ts"], alias="vlm-ocr", provider="google", upstream="google",
                               prompt_tokens=1200, completion_tokens=300, total_tokens=1500)]
    assert r._client_factory.seen == [(vision.vlm_model_alias(), "vlm-a")], "chỉ khoá VLM, không khoá chat"


def test_content_la_list_khoi_thi_van_boc_duoc(khoa):
    blocks = [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": json.dumps(_PAYLOAD)}]
    r = VisionReader(client_factory=_factory({"vlm-a": _Client([_Resp(blocks)])}))
    assert r.read_table(b"png").payload["hang"][0]["ma_so"] == "01"


def test_429_xoay_sang_khoa_2_trong_cung_luot(khoa):
    e = RuntimeError("429 Resource exhausted")
    e.status_code = 429
    a = _Client([e])
    b = _Client([_Resp(json.dumps(_PAYLOAD))])
    r = VisionReader(client_factory=_factory({"vlm-a": a, "vlm-b": b}))
    assert r.read_table(b"png").payload == _PAYLOAD
    assert a.calls == 1 and b.calls == 1
    assert r._ring.index["vlm-ocr"] == 1


def test_429_het_ca_vong_thi_QuotaExhausted_va_ve_khoa_0(khoa):
    e = RuntimeError("429")
    e.status_code = 429
    r = VisionReader(client_factory=_factory({"vlm-a": _Client([e]), "vlm-b": _Client([e])}))
    with pytest.raises(VisionQuotaExhausted):
        r.read_table(b"png")
    assert r._ring.index["vlm-ocr"] == 0


def test_loi_KHONG_phai_429_thi_khong_xoay_ma_nem_ra(khoa):
    b = _Client([_Resp(json.dumps(_PAYLOAD))])
    r = VisionReader(client_factory=_factory({"vlm-a": _Client([TimeoutError("timeout")]), "vlm-b": b}))
    with pytest.raises(TimeoutError):
        r.read_table(b"png")
    assert b.calls == 0 and r.failures == 1


def test_tran_cung_theo_luot_nap(khoa):
    c = _Client([_Resp(json.dumps(_PAYLOAD))] * 3)
    r = VisionReader(client_factory=_factory({"vlm-a": c}), max_calls=2)
    r.read_table(b"png")
    r.read_table(b"png")
    with pytest.raises(VisionCapReached):
        r.read_table(b"png")
    assert c.calls == 2


@pytest.mark.parametrize("text", ["", "Không đọc được.", "{\"hang\": [", "[1, 2]", "{\"trang\": {}}"])
def test_json_hong_la_BadResponse_mang_do_dai_khong_mang_noi_dung(khoa, text):
    r = VisionReader(client_factory=_factory({"vlm-a": _Client([_Resp(text)])}))
    with pytest.raises(VisionBadResponse) as ei:
        r.read_table(b"png")
    assert f"({len(text)} ký tự)" in str(ei.value)
    assert r.failures == 1


def test_parse_response_boc_json_giua_van_ban():
    d = vision.parse_response("Đây là kết quả:\n```json\n" + json.dumps(_PAYLOAD) + "\n```\nHết.")
    assert d["trang"]["cot_gia_tri"] == ["Số cuối năm", "Số đầu năm"]


def test_page_png_tra_bytes_png():
    from PIL import Image
    b = vision.page_png(Image.new("RGB", (4, 4), "white"))
    assert b[:8] == b"\x89PNG\r\n\x1a\n"


def test_VisionReader_mac_dinh_TU_CO_so_khong_can_ai_tiem():
    """#29 vòng 2: bản vá đầu chỉ đặt sổ ở `parse.VISION_READER_FACTORY`, nên
    MỌI chỗ dựng `VisionReader()` trực tiếp vẫn vô hình với sổ ngân sách — spike
    trang thuyết minh 2026-09-19 gọi 23 lượt thật và sổ ghi 0. Mặc định phải TỰ
    có sổ; `store=None` tường minh mới là tắt."""
    assert VisionReader()._store is not None
    assert VisionReader(store=None)._store is None, "tắt sổ phải tường minh"


def test_so_VLM_trong_test_la_ban_TRONG_BO_NHO_khong_cham_postgres():
    """Đối chứng cho rào `so_vlm_khong_cham_postgres` ở conftest: nếu rào chết,
    test này đỏ TRƯỚC khi 18 dòng rác nữa lọt vào `public.llm_usage`."""
    from src.llm.store import InMemoryUsageStore
    assert isinstance(vision._SoVlm._store, InMemoryUsageStore)
    assert vision._SoVlm._da_thu is True, "đã 'thử mở' rồi nên record() không dựng pool thật"
