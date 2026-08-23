"""Cross-encoder reranker (spec 2026-07-12-rag-reranker-design §3.2).

BGE-Reranker-v2-m3, lazy load ở lần gọi đầu. Fail-open tuyệt đối: mọi sự cố
(chưa có mạng lần tải model đầu, OOM, lỗi inference) → None và retrieval quay
về đúng hành vi hybrid-rrf hiện tại — không bao giờ tệ hơn hiện trạng, không
bao giờ raise vào rag_node. Trạng thái hỏng cache trong process (sentinel
False) — không thử tải lại model 2.3GB mỗi query; restart mới thử lại.

Kill-switch: env RAG_RERANK_ENABLED=0 (mặc định bật), đọc mỗi lần gọi.

THIẾT BỊ (đổi 2026-08-19). Bản 2026-07-12 ghi "chạy CPU (torch build +cpu —
CUDA không tồn tại trong env này)" và CỐ Ý không ghim torch/transformers vào
requirements.txt, để production không phải kéo dep nặng. Hệ quả KHÔNG lường
trước: trong venv thật của backend hai gói đó không có, nên _load() ném
ModuleNotFoundError, fail-open nuốt gọn, sentinel cắm False — reranker CHẾT
100% một cách im lặng suốt từ lúc port sang Youdoo. Đo được 2026-08-19:
retrieve() thật trên corpus 3300 chunk trả method="hybrid-rrf", không có
"+rerank". Bốn test rerank vẫn xanh vì tất cả đều monkeypatch score_pairs;
test model thật thì nằm sau biến môi trường RUN_RERANK_MODEL không ai đặt.

Nay máy dev có RTX 5060 Ti (sm_120) cấp cho project này, torch cu128 và
transformers đã ghim vào requirements.txt, và _resolve_device() là chỗ DUY
NHẤT quyết định thiết bị — ép CPU bằng RERANK_DEVICE=cpu để đo đối chứng.
"""
import logging
import os

from .config import RERANK_MODEL, RERANK_MAX_LENGTH, RERANK_DEVICE

logger = logging.getLogger(__name__)

# "model": None = chưa load | False = hỏng (không thử lại) | object = sẵn sàng
_state: dict = {"model": None, "tokenizer": None}


def _cuda_available() -> bool:
    """Tách riêng để test thay được — import torch nằm TRONG hàm, giữ đúng
    lối lazy-import của module (không có torch vẫn import được module này)."""
    import torch
    return torch.cuda.is_available()


def _resolve_device() -> str:
    """Thiết bị chạy cross-encoder: "cuda" hoặc "cpu".

    RERANK_DEVICE = "auto" (mặc định) | "cuda" | "cpu", đọc MỖI LẦN gọi như
    kill-switch RAG_RERANK_ENABLED — cùng lối, để đổi hành vi không cần
    restart lúc đo.

    Mọi sự cố lúc dò CUDA (torch thiếu, driver lệch, thiếu kernel cho sm_120)
    → "cpu", KHÔNG ném. Ném ở đây sẽ bị except của score_pairs bắt và cắm
    sentinel hỏng vĩnh viễn, tức một trục trặc GPU sẽ giết luôn cả đường CPU
    vốn vẫn chạy được."""
    want = os.environ.get("RERANK_DEVICE", RERANK_DEVICE).strip().lower()
    if want != "auto":
        return want
    try:
        return "cuda" if _cuda_available() else "cpu"
    except Exception:  # noqa: BLE001 — xem docstring
        logger.warning("Không dò được CUDA — reranker chạy CPU", exc_info=True)
        return "cpu"


def _load():
    """Load model + tokenizer (1 lần). Raise nếu lỗi — caller cache sentinel.

    fp16 CHỈ trên cuda: nửa độ chính xác trên CPU chậm hơn fp32 chứ không
    nhanh hơn (thiếu kernel), nên ép half() ở đó là tự bắn vào chân."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    device = _resolve_device()
    tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(RERANK_MODEL)
    if device == "cuda":
        model = model.half()
    model = model.to(device)
    model.eval()
    logger.info("Reranker %s đã nạp trên %s", RERANK_MODEL, device)
    return model, tokenizer


def nap_am() -> bool:
    """Nạp sẵn model lúc khởi động. True = đã sẵn sàng, False = tắt/hỏng.

    Vì sao cần (mục 22, đo 2026-08-23): `_load()` chạy LƯỜI, ở lượt rerank đầu
    tiên. Nên câu hỏi tài liệu ĐẦU TIÊN sau mỗi lần khởi động lại trả **15,8s**
    trong khi lượt ấm chỉ **4,9s** — người dùng đầu tiên gánh ~10s nạp trọng số
    thay cho cả hệ, và với một buổi demo thì đó đúng là câu hỏi tệ nhất để chậm.

    KHÔNG ném: giữ nguyên hợp đồng fail-open của module. Hỏng ở đây chỉ có
    nghĩa "vẫn nạp lười như cũ", không có nghĩa backend không khởi động được —
    reranker là thứ tăng chất lượng, không phải thứ bắt buộc.

    Tôn trọng cả hai công tắc tắt sẵn có (`RAG_RERANK_ENABLED=0` và sentinel
    `_state["model"] is False`), nếu không nó sẽ lặng lẽ nạp một model mà cấu
    hình đã bảo đừng dùng.
    """
    if os.environ.get("RAG_RERANK_ENABLED", "1") == "0":
        return False
    if _state["model"] is False:
        return False
    if _state["model"] is not None:
        return True
    try:
        _state["model"], _state["tokenizer"] = _load()
        return True
    except Exception:                                       # noqa: BLE001
        logger.warning("Không nạp ấm được reranker — sẽ thử lại khi có lượt "
                       "rerank đầu tiên", exc_info=True)
        return False


def score_pairs(query: str, texts: list[str]) -> list[float] | None:
    """Điểm relevance từng cặp (query, text). None = tắt/hỏng (fail-open)."""
    if os.environ.get("RAG_RERANK_ENABLED", "1") == "0":
        return None
    if _state["model"] is False:
        return None
    try:
        if _state["model"] is None:
            _state["model"], _state["tokenizer"] = _load()
        import torch
        pairs = [[query, t] for t in texts]
        inputs = _state["tokenizer"](pairs, padding=True, truncation=True,
                                     max_length=RERANK_MAX_LENGTH,
                                     return_tensors="pt")
        # Tensor input PHẢI nằm cùng thiết bị với model, nếu không torch ném
        # "Expected all tensors to be on the same device" — và fail-open sẽ
        # nuốt nó thành một lượt rerank chết lặng, đúng lớp lỗi đợt này đi
        # đóng. hasattr: tokenizer giả trong unit test trả dict thuần.
        device = _resolve_device()
        inputs = {k: (v.to(device) if hasattr(v, "to") else v)
                  for k, v in inputs.items()}
        with torch.no_grad():
            logits = _state["model"](**inputs).logits.view(-1)
        scores = [float(s) for s in logits]
        if len(scores) != len(texts):
            raise ValueError(f"expected {len(texts)} scores, got {len(scores)}")
        return scores
    except Exception:  # noqa: BLE001 — fail-open theo spec §4
        logger.warning("Reranker unavailable — falling back to hybrid-rrf order",
                       exc_info=True)
        _state["model"] = False
        return None
