"""Test embed.py — hai implementation + marker chống lệch.

Không chạm mạng: OllamaEmbedder được test qua httpx mock, GeminiEmbedder chỉ
test phần cấu hình (nó TẮT mặc định nên không có đường chạy thật ở SP-1).
"""
import pytest

from src.rag.embed import (Embedder, GeminiEmbedder, OllamaEmbedder,
                           assert_embedding_marker, get_embedder)


def test_ollama_la_mac_dinh():
    """Nguyên tắc một-biến: SP-1 đổi LLM, KHÔNG đổi embedding cùng lúc."""
    assert isinstance(get_embedder(), OllamaEmbedder)


def test_ollama_khai_bao_dung_model_va_chieu():
    e = OllamaEmbedder()
    assert e.model_name == "bge-m3"
    assert e.dim == 1024


def test_gemini_khai_bao_dung_model_va_chieu():
    e = GeminiEmbedder()
    assert e.model_name == "gemini-embedding-001"
    assert e.dim == 3072


def test_ca_hai_deu_thoa_protocol():
    assert isinstance(OllamaEmbedder(), Embedder)
    assert isinstance(GeminiEmbedder(), Embedder)


def test_marker_khop_thi_khong_nem(fake_conn_khop):
    assert_embedding_marker(fake_conn_khop)      # không raise là đạt


def test_marker_lech_model_thi_nem_RuntimeError(fake_conn_lech_model):
    with pytest.raises(RuntimeError, match="embedding"):
        assert_embedding_marker(fake_conn_lech_model)


def test_marker_lech_chieu_thi_nem_RuntimeError(fake_conn_lech_dim):
    with pytest.raises(RuntimeError, match="1024|dim"):
        assert_embedding_marker(fake_conn_lech_dim)


def test_marker_chua_co_ban_ghi_thi_khong_nem(fake_conn_rong):
    """DB trống (chưa index gì) không phải lệch — chỉ là chưa có gì để lệch."""
    assert_embedding_marker(fake_conn_rong)


class _FakeConn:
    """Kết nối giả trả sẵn một hàng marker."""

    def __init__(self, row) -> None:
        self._row = row

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return self._row


@pytest.fixture
def fake_conn_khop():
    return _FakeConn(("bge-m3", 1024))


@pytest.fixture
def fake_conn_lech_model():
    return _FakeConn(("gemini-embedding-001", 1024))


@pytest.fixture
def fake_conn_lech_dim():
    return _FakeConn(("bge-m3", 3072))


@pytest.fixture
def fake_conn_rong():
    return _FakeConn(None)


def test_module_level_embed_texts_uy_quyen_dung_provider_dang_bat(monkeypatch):
    """Bug thật đã sửa: retrieve.py/ingest.py import embed_texts/embed_query
    Ở CẤP MODULE (không phải qua get_embedder()) — hàm module-level phải thật
    sự gọi qua get_embedder(), không phải một no-op hay một provider khác."""
    from src.rag import embed
    goi = {}

    class _FakeEmbedder:
        model_name = "fake-model"
        dim = 4

        def embed_texts(self, texts):
            goi["texts"] = texts
            return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

        def embed_query(self, text):
            goi["query"] = text
            return [0.9, 0.9, 0.9, 0.9]

    monkeypatch.setattr(embed, "get_embedder", lambda: _FakeEmbedder())
    assert embed.embed_texts(["a", "b"]) == [[0.1, 0.2, 0.3, 0.4]] * 2
    assert goi["texts"] == ["a", "b"]
    assert embed.embed_query("hoi gi do") == [0.9, 0.9, 0.9, 0.9]
    assert goi["query"] == "hoi gi do"
