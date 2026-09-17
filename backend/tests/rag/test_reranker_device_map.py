# backend/tests/rag/test_reranker_device_map.py
"""Đường nạp device_map — spec 2026-09-17 §3 (B) và §7.

Gác đúng MỘT điều: hai đường nạp không được trộn. Gọi .to()/.half() lên
model mà accelerate đã đặt lớp là lỗi thiết bị, và fail-open sẽ nuốt nó.
"""
import types

from src.rag import reranker


class _FakeCls:
    calls: list = []

    @classmethod
    def from_pretrained(cls, name, **kw):
        cls.calls.append(kw)
        m = types.SimpleNamespace(device="cuda:0")
        m.half = lambda: (_ for _ in ()).throw(AssertionError("không được .half()"))
        m.to = lambda d: (_ for _ in ()).throw(AssertionError("không được .to()"))
        return m


class _FakeClsPlain:
    """Đường cũ: .half() rồi .to(device) đều được gọi, trả về chính nó."""
    @classmethod
    def from_pretrained(cls, name, **kw):
        m = types.SimpleNamespace(halved=False, moved=None)
        m.half = lambda: (setattr(m, "halved", True) or m)
        m.to = lambda d: (setattr(m, "moved", d) or m)
        return m


def test_device_map_khong_goi_to_hay_half(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_DEVICE_MAP", "auto")
    monkeypatch.setattr(reranker, "RERANK_GPU_BUDGET", "5GiB")
    _FakeCls.calls.clear()
    m = reranker._instantiate(_FakeCls, "cuda")
    assert m.device == "cuda:0"
    kw = _FakeCls.calls[0]
    assert kw["device_map"] == "auto"
    assert kw["max_memory"][0] == "5GiB"


def test_duong_cu_van_half_roi_to(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_DEVICE_MAP", "")
    m = reranker._instantiate(_FakeClsPlain, "cuda")
    assert m.halved and m.moved == "cuda"


def test_duong_cu_tren_cpu_khong_half(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_DEVICE_MAP", "")
    m = reranker._instantiate(_FakeClsPlain, "cpu")
    assert not m.halved and m.moved == "cpu"


def test_accelerate_da_cai():
    import accelerate  # noqa: F401 — device_map="auto" cần nó
