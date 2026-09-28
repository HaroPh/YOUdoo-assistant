"""Nhật ký MỌI lượt gọi VLM (`vlm_call_log`) — chủ dự án chấp nhận VLM dùng
chung ví Gemini với chat (2026-09-28), với điều kiện mọi lượt gọi đều được ghi.

Bất biến chính: **số dòng nhật ký == `reader.calls`** trong mọi kịch bản — mỗi
lần bấm gọi API là đúng một dòng, kể cả 429, lỗi mạng, phản hồi hỏng. `llm_usage`
KHÔNG đổi (chỉ lượt thành công) vì bộ kiểm hạn mức đếm dòng ở đó.
"""
import json

import pytest

from src.ocr import vision
from src.ocr.call_log import InMemoryVlmCallLog, redact_error
from src.ocr.vision import (VisionBadResponse, VisionCapReached, VisionQuotaExhausted,
                            VisionReader, VisionUnavailable)

_PAYLOAD = {"trang": {"mau": "B01/BCTC", "thong_tu": "107/2017/TT-BTC",
                      "cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
            "hang": [{"muc": "I.", "nhan": "Tiền", "ma_so": "01", "thuyet_minh": None,
                      "so_tien": ["750.005.854", "40.565.652.481"]}]}
_PAYLOAD_TM = {"cot": ["Số cuối năm", "Số đầu năm"],
               "hang": [{"bang": "9. CHI PHÍ TRẢ TRƯỚC", "cap": 1, "loai": "thuong",
                         "nhan": "Ngắn hạn", "gia_tri": ["1.299.253.023", "1.046.686.892"]}]}

_USAGE = {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}


class _Resp:
    def __init__(self, content, usage=None):
        self.content = content
        self.usage_metadata = usage or _USAGE


class _Loi429(Exception):
    status_code = 429


class _Client:
    def __init__(self, script):
        self.script = list(script)

    def invoke(self, msgs):
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def khoa(monkeypatch):
    for i in range(2, 10):
        monkeypatch.delenv(f"YOUDOO_VLM_API_KEY_{i}", raising=False)
    monkeypatch.setenv("YOUDOO_VLM_API_KEY", "vlm-a")
    monkeypatch.setenv("YOUDOO_VLM_API_KEY_2", "vlm-b")


def _reader(clients_by_key, log, **kw):
    return VisionReader(client_factory=lambda spec, k: clients_by_key[k],
                        store=None, call_log=log, **kw)


def _ok():
    return _Resp(json.dumps(_PAYLOAD))


def test_luot_thanh_cong_ghi_mot_dong_du_cot(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([_ok()])}, log)
    r.read_table(b"png", source="DVT_2022.pdf", page=7)
    assert len(log.rows) == r.calls == 1
    row = log.rows[0]
    assert row["outcome"] == "ok"
    assert (row["source"], row["page"], row["mode"]) == ("DVT_2022.pdf", 7, "bang_chi_tieu")
    assert row["key_index"] == 0
    assert row["model"] == vision.vlm_model_alias()
    assert row["prompt_version"] == vision.PROMPT_VERSION
    assert (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"]) == (1200, 300, 1500)
    assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0
    assert row["error"] is None
    assert row["ts"].tzinfo is not None


def test_ts_la_luc_BAT_DAU_goi_khong_phai_luc_ghi(khoa):
    """`ts` là lúc bấm gọi; thời gian chờ nằm ở `latency_ms`. Ghi lúc kết thúc
    thì một lượt treo 60s sẽ hiện ra như gọi muộn 60s.

    So THỨ TỰ, không so ngưỡng: bản đầu của test này so `latency_ms >= 300`
    và `ts - trước < 200ms` và chập chờn 2/3 lượt (đo 297 < 300) — đồng hồ
    monotonic của Windows nhảy ~16 ms. `ts <= lúc client nhận lượt gọi` thì
    tất định cả hai chiều: bản ghi-lúc-kết-thúc luôn muộn hơn đúng 0,3 s."""
    import time
    from datetime import datetime, timezone
    moc = {}

    class _Cham:
        def invoke(self, msgs):
            moc["vao"] = datetime.now(timezone.utc)
            time.sleep(0.3)
            return _ok()
    log = InMemoryVlmCallLog()
    _reader({"vlm-a": _Cham()}, log).read_table(b"png")
    row = log.rows[0]
    assert row["ts"] <= moc["vao"], "ts phải là lúc BẮT ĐẦU gọi, trước khi client nhận"
    assert row["latency_ms"] >= 250, "0,3 s chờ, chừa sai số đồng hồ Windows ~16 ms"


def test_429_roi_xoay_khoa_thanh_cong_ghi_HAI_dong(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([_Loi429("429 RESOURCE_EXHAUSTED")]),
                 "vlm-b": _Client([_ok()])}, log)
    r.read_table(b"png", source="x.pdf", page=3)
    assert len(log.rows) == r.calls == 2
    assert [x["outcome"] for x in log.rows] == ["rate_limited", "ok"]
    assert [x["key_index"] for x in log.rows] == [0, 1]
    assert log.rows[0]["total_tokens"] is None          # Google không trả gì
    assert "_Loi429" in log.rows[0]["error"]


def test_429_het_moi_khoa_moi_luot_deu_co_dong(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([_Loi429("429")]),
                 "vlm-b": _Client([_Loi429("429")])}, log)
    with pytest.raises(VisionQuotaExhausted):
        r.read_table(b"png")
    assert len(log.rows) == r.calls == 2
    assert {x["outcome"] for x in log.rows} == {"rate_limited"}


def test_loi_mang_ghi_dong_error_roi_moi_nem(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([TimeoutError("read timed out")])}, log)
    with pytest.raises(TimeoutError):
        r.read_table(b"png")
    assert len(log.rows) == r.calls == 1
    assert log.rows[0]["outcome"] == "error"
    assert log.rows[0]["error"].startswith("TimeoutError: read timed out")


def test_phan_hoi_hong_van_ghi_dong_CO_token(khoa):
    """Google đã tính token cho lượt này dù JSON không dùng được."""
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([_Resp("không phải JSON")])}, log)
    with pytest.raises(VisionBadResponse):
        r.read_table(b"png")
    assert len(log.rows) == r.calls == 1
    assert log.rows[0]["outcome"] == "bad_response"
    assert log.rows[0]["total_tokens"] == 1500
    assert log.rows[0]["error"].startswith("VisionBadResponse")


def test_che_do_thuyet_minh_ghi_dung_mode_va_prompt_version(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([_Resp(json.dumps(_PAYLOAD_TM))])}, log)
    r.read_table(b"png", che_do="thuyet_minh")
    assert log.rows[0]["mode"] == "thuyet_minh"
    assert log.rows[0]["prompt_version"] == vision.PROMPT_TM_VERSION


def test_khong_goi_API_thi_khong_co_dong(khoa, monkeypatch):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([])}, log, max_calls=0)
    with pytest.raises(VisionCapReached):
        r.read_table(b"png")
    assert log.rows == [] and r.calls == 0

    monkeypatch.delenv("YOUDOO_VLM_API_KEY")
    monkeypatch.delenv("YOUDOO_VLM_API_KEY_2")
    r2 = _reader({}, log)
    with pytest.raises(VisionUnavailable):
        r2.read_table(b"png")
    assert log.rows == [] and r2.calls == 0


def test_nhat_ky_hong_khong_giet_luot_doc(khoa, caplog):
    class _Hong:
        def record(self, **kw):
            raise RuntimeError("postgres sập")
    r = _reader({"vlm-a": _Client([_ok()])}, _Hong())
    t = r.read_table(b"png")
    assert t.payload["hang"]
    assert "vlm_call_log" in caplog.text


def test_loi_khong_lo_khoa_API(khoa):
    """Thông điệp lỗi SDK có thể chứa khoá (URL `?key=`). Cột `error` không
    được mang khoá — cả khoá đang cấu hình lẫn chuỗi dạng khoá Google."""
    la = "AIza" + "B" * 35
    e = RuntimeError(f"400 bad request url=...?key=vlm-a&x=1 other={la}")
    msg = redact_error(e, secrets=["vlm-a", "vlm-b"])
    assert "vlm-a" not in msg and la not in msg
    assert msg.startswith("RuntimeError: ")
    assert len(redact_error(RuntimeError("x" * 5000), secrets=[])) <= 200


def test_loi_that_trong_read_table_da_che_khoa(khoa):
    log = InMemoryVlmCallLog()
    r = _reader({"vlm-a": _Client([RuntimeError("500 ?key=vlm-a")])}, log)
    with pytest.raises(RuntimeError):
        r.read_table(b"png")
    assert "vlm-a" not in log.rows[0]["error"]


def test_mac_dinh_la_nhat_ky_bat_bien_cua_LOP(khoa):
    """Như sổ `llm_usage` (#29 vòng 2): dựng `VisionReader()` trực tiếp vẫn
    phải có nhật ký — không để lối gọi nào vô hình. Trong test, rào ở conftest
    thay bản Postgres bằng bản trong bộ nhớ."""
    from src.ocr import call_log
    before = len(call_log.DefaultVlmCallLog._store.rows)
    r = VisionReader(client_factory=lambda spec, k: _Client([_ok()]), store=None)
    r.read_table(b"png")
    assert len(call_log.DefaultVlmCallLog._store.rows) == before + 1


def test_postgres_hong_luc_dung_thi_MOI_luot_deu_canh_bao_nhung_chi_thu_ket_noi_MOT_lan(
        khoa, monkeypatch, caplog):
    """Chỉ thử dựng MỘT lần (timeout 2s mỗi lần thử — không được nhân lên theo
    số trang). Nhưng lượt nào mất dòng cũng phải để lại cảnh báo: im lặng từ
    lượt thứ hai là đúng cái "không ai biết đã mất" mà nhật ký này sinh ra để chặn."""
    from src.ocr import call_log
    thu = []

    class _PgHong:
        def __init__(self, *a, **k):
            thu.append(1)
            raise RuntimeError("bảng vlm_call_log không tồn tại")
    monkeypatch.setattr(call_log, "PostgresVlmCallLog", _PgHong)
    monkeypatch.setattr(call_log.DefaultVlmCallLog, "_store", None)
    monkeypatch.setattr(call_log.DefaultVlmCallLog, "_tried", False)
    monkeypatch.setattr(call_log.DefaultVlmCallLog, "_failure", None, raising=False)

    r = VisionReader(client_factory=lambda spec, k: _Client([_ok(), _ok()]), store=None)
    r.read_table(b"png")
    r.read_table(b"png")
    assert len(thu) == 1, "chỉ thử kết nối một lần mỗi tiến trình"
    assert caplog.text.count("không ghi được vlm_call_log") == 2
