"""Mục 22 — nạp ấm reranker lúc khởi động."""
import inspect

import src.main as main_mod
from src.rag import reranker


def test_lifespan_CO_goi_nap_am():
    """Rào chống "viết hàm rồi quên nối vào" — cùng khuôn với rào interceptor
    của mục 17. Đọc mã nguồn vì dựng lifespan thật sẽ kéo theo Postgres + 4
    tiến trình MCP, tức test sẽ skip trên máy sạch và rào biến mất đúng lúc
    cần nhất."""
    src = inspect.getsource(main_mod.lifespan)
    assert "nap_am" in src


def test_ton_trong_cong_tac_tat_bang_bien_moi_truong(monkeypatch):
    """Nạp ấm mà bỏ qua công tắc tắt thì nó lặng lẽ nạp một model mà cấu hình
    đã bảo đừng dùng."""
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")
    monkeypatch.setitem(reranker._state, "model", None)
    goi = []
    monkeypatch.setattr(reranker, "_load", lambda: goi.append(1) or (1, 2))
    assert reranker.nap_am() is False
    assert goi == [], "đã tắt mà vẫn nạp"


def test_ton_trong_sentinel_hong(monkeypatch):
    monkeypatch.delenv("RAG_RERANK_ENABLED", raising=False)
    monkeypatch.setitem(reranker._state, "model", False)   # sentinel "hỏng"
    goi = []
    monkeypatch.setattr(reranker, "_load", lambda: goi.append(1) or (1, 2))
    assert reranker.nap_am() is False
    assert goi == []


def test_da_nap_roi_thi_KHONG_nap_lai(monkeypatch):
    monkeypatch.delenv("RAG_RERANK_ENABLED", raising=False)
    monkeypatch.setitem(reranker._state, "model", "da-co")
    goi = []
    monkeypatch.setattr(reranker, "_load", lambda: goi.append(1) or (1, 2))
    assert reranker.nap_am() is True
    assert goi == []


def test_nap_duoc_thi_tra_True_va_dat_vao_state(monkeypatch):
    monkeypatch.delenv("RAG_RERANK_ENABLED", raising=False)
    monkeypatch.setitem(reranker._state, "model", None)
    monkeypatch.setattr(reranker, "_load", lambda: ("M", "T"))
    assert reranker.nap_am() is True
    assert reranker._state["model"] == "M"
    assert reranker._state["tokenizer"] == "T"


def test_nap_HONG_thi_KHONG_nem_va_khong_dat_sentinel(monkeypatch):
    """Fail-open: hỏng lúc nạp ấm chỉ có nghĩa "vẫn nạp lười như cũ", KHÔNG
    được làm backend không khởi động được, và KHÔNG được đặt sentinel `False`
    — đặt sentinel sẽ TẮT VĨNH VIỄN reranker cho cả tiến trình vì một lỗi có
    thể chỉ nhất thời."""
    monkeypatch.delenv("RAG_RERANK_ENABLED", raising=False)
    monkeypatch.setitem(reranker._state, "model", None)

    def _hong():
        raise RuntimeError("hết VRAM")

    monkeypatch.setattr(reranker, "_load", _hong)
    assert reranker.nap_am() is False
    assert reranker._state["model"] is None, "không được đặt sentinel hỏng"


# ── Nửa thứ hai: embedder (mục 22, vòng 2) ──────────────────────────────────
#
# Nạp ấm MÌNH reranker chỉ đưa câu hỏi tài liệu đầu tiên từ 15,8s xuống
# 10,9s — chưa đạt. Phần còn lại là Ollama nạp model nhúng theo yêu cầu.
# Ấm cả hai: 6,1s, nằm gọn trong khoảng ấm (4,5–7,0s).

def test_lifespan_nap_am_CA_HAI():
    """Rào cho đúng bài học vòng 1: chỉ ấm một nửa thì con số không xuống."""
    import inspect
    src = inspect.getsource(main_mod.lifespan)
    assert "nap_am_rerank" in src
    assert "nap_am_embed" in src


def test_embed_nap_am_goi_dung_MOT_luot(monkeypatch):
    from src.rag import embed as embed_mod
    goi = []
    monkeypatch.setattr(embed_mod, "embed_query",
                        lambda t: goi.append(t) or [0.0])
    assert embed_mod.nap_am() is True
    assert len(goi) == 1


def test_embed_nap_am_HONG_thi_khong_nem(monkeypatch):
    """Ollama chưa lên thì backend vẫn phải khởi động được — hỏng ở đây chỉ
    có nghĩa "lượt truy xuất đầu tiên vẫn chậm như cũ"."""
    from src.rag import embed as embed_mod

    def _hong(t):
        raise RuntimeError("ollama chưa lên")

    monkeypatch.setattr(embed_mod, "embed_query", _hong)
    assert embed_mod.nap_am() is False
