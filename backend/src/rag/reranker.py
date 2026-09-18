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
transformers đã ghim vào requirements.txt. _resolve_device() quyết định thiết
bị lúc NẠP model (và là chỗ ép CPU bằng RERANK_DEVICE=cpu để đo đối chứng);
từ spec 2026-09-17 (đường `device_map` cho 4B), thiết bị đưa INPUT vào đi qua
_input_device() — ưu tiên `model.device` khi model đã tự biết mình ở đâu
(nạp bằng accelerate device_map), lùi về _resolve_device() khi model không
có thuộc tính đó (nạp kiểu cũ, hoặc model giả trong test). Nhờ vậy input
không còn thể LỆCH khỏi thiết bị thật của một model ĐÃ NẠP nếu RERANK_DEVICE
đổi giữa tiến trình — trước đây input luôn đi theo _resolve_device() đọc lại
mỗi lần gọi, bất kể model đang thực sự nằm ở đâu.
"""
import logging
import os

from .config import (RERANK_MODEL, RERANK_MAX_LENGTH, RERANK_DEVICE,
                     RERANK_DEVICE_MAP, RERANK_GPU_BUDGET)

logger = logging.getLogger(__name__)

# "model": None = chưa load | False = hỏng (không thử lại) | object = sẵn sàng
_state: dict = {"model": None, "tokenizer": None}

QWEN3_FAMILY_PREFIX = "Qwen/Qwen3-Reranker"

# Theo model card chính thức của Qwen3-Reranker. Điểm = P(yes) ở token cuối.
_QWEN3_PREFIX = ("<|im_start|>system\nJudge whether the Document meets the "
                 "requirements based on the Query and the Instruct provided. "
                 "Note that the answer can only be \"yes\" or \"no\"."
                 "<|im_end|>\n<|im_start|>user\n")
_QWEN3_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
# Instruction MẶC ĐỊNH của model card, cố ý không Việt hoá ở lượt đo này:
# đổi instruction và đổi model cùng lúc thì không quy được kết quả cho cái
# nào (spec §4.1).
QWEN3_INSTRUCTION = ("Given a web search query, retrieve relevant passages "
                     "that answer the query")


def _family(model_name: str | None = None) -> str:
    """Họ model quyết định ĐƯỜNG CHẤM ĐIỂM, không phải kích thước.

    bge-reranker là cross-encoder: một logit mỗi cặp. Qwen3-Reranker là
    decoder LM: xác suất token "yes" sau một prompt. Hai giao diện khác hẳn
    nhau, và 0.6B với 4B dùng chung một đường — nên đổi sang bất kỳ bản Qwen
    nào cũng phải có đường này."""
    name = RERANK_MODEL if model_name is None else model_name
    return "qwen3" if name.startswith(QWEN3_FAMILY_PREFIX) else "seq_cls"


def _input_device(model) -> str:
    """Thiết bị để đưa input vào. Model nạp bằng `device_map` tự biết mình ở
    đâu (`.device`); model nạp kiểu cũ và model giả trong test thì không —
    lùi về `_resolve_device()` như trước."""
    dev = getattr(model, "device", None)
    return str(dev) if dev is not None else _resolve_device()


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


def _instantiate(model_cls, device: str):
    """Nạp trọng số theo một trong hai đường — KHÔNG trộn.

    Đường `device_map`: accelerate đã đặt từng lớp lên GPU/CPU rồi, gọi
    `.to(device)` sau đó là lỗi "Expected all tensors to be on the same
    device" — và fail-open sẽ NUỐT nó thành một chân eval `dense-rrf` trông
    y như "model không hiệu quả" (spec §7)."""
    import torch
    if RERANK_DEVICE_MAP:
        return model_cls.from_pretrained(
            RERANK_MODEL, dtype=torch.float16, device_map=RERANK_DEVICE_MAP,
            max_memory={0: RERANK_GPU_BUDGET, "cpu": "20GiB"})
    model = model_cls.from_pretrained(RERANK_MODEL)
    if device == "cuda":
        model = model.half()
    return model.to(device)


def _load():
    """Load model + tokenizer (1 lần). Raise nếu lỗi — caller cache sentinel.

    fp16 CHỈ trên cuda: nửa độ chính xác trên CPU chậm hơn fp32 chứ không
    nhanh hơn (thiếu kernel), nên ép half() ở đó là tự bắn vào chân."""
    from transformers import AutoTokenizer
    device = _resolve_device()
    tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
    if _family() == "qwen3":
        from transformers import AutoModelForCausalLM
        # BẮT BUỘC: điểm đọc ở vị trí -1. Right padding làm vị trí đó là pad
        # cho mọi cặp ngắn hơn cặp dài nhất — điểm rác, không lỗi.
        tokenizer.padding_side = "left"
        model = _instantiate(AutoModelForCausalLM, device)
    else:
        from transformers import AutoModelForSequenceClassification
        model = _instantiate(AutoModelForSequenceClassification, device)
    model.eval()
    logger.info("Reranker %s (%s) đã nạp trên %s", RERANK_MODEL, _family(),
                _input_device(model))
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


def _score_seq_cls(model, tokenizer, query: str, texts: list[str]) -> list[float]:
    """Cross-encoder: một logit mỗi cặp (đường cũ, không đổi hành vi)."""
    import torch
    pairs = [[query, t] for t in texts]
    inputs = tokenizer(pairs, padding=True, truncation=True,
                       max_length=RERANK_MAX_LENGTH, return_tensors="pt")
    # Tensor input PHẢI nằm cùng thiết bị với model, nếu không torch ném
    # "Expected all tensors to be on the same device" — và fail-open sẽ
    # nuốt nó thành một lượt rerank chết lặng. hasattr: tokenizer giả
    # trong unit test trả dict thuần.
    device = _input_device(model)
    inputs = {k: (v.to(device) if hasattr(v, "to") else v)
              for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits.view(-1)
    return [float(s) for s in logits]


def _score_qwen3(model, tokenizer, query: str, texts: list[str]) -> list[float]:
    """Decoder LM: P(yes) ở token cuối, theo model card Qwen3-Reranker.

    Cắt ngắn ở PHẦN THÂN rồi mới nối prefix/suffix — không cắt cả prompt.
    Cắt cả prompt từ phải sẽ mất suffix, tức mất chính vị trí đọc điểm, và
    kết quả là số rác chứ không phải lỗi."""
    import torch
    if getattr(tokenizer, "padding_side", None) != "left":
        raise ValueError("Qwen3-Reranker cần tokenizer.padding_side == 'left'")
    prefix_ids = tokenizer.encode(_QWEN3_PREFIX, add_special_tokens=False)
    suffix_ids = tokenizer.encode(_QWEN3_SUFFIX, add_special_tokens=False)
    # max(1, ...): nếu RERANK_MAX_LENGTH nhỏ hơn cả prefix+suffix, body_max âm
    # sẽ làm max_length âm truyền vào tokenizer — lỗi khó đọc thay vì cắt còn
    # 1 token thân bài (vẫn tệ, nhưng không phải crash không rõ nguyên nhân).
    body_max = max(1, RERANK_MAX_LENGTH - len(prefix_ids) - len(suffix_ids))
    bodies = [f"<Instruct>: {QWEN3_INSTRUCTION}\n<Query>: {query}\n<Document>: {t}"
              for t in texts]
    enc = tokenizer(bodies, padding=False, truncation=True, max_length=body_max,
                    add_special_tokens=False)
    enc["input_ids"] = [prefix_ids + ids + suffix_ids for ids in enc["input_ids"]]
    enc["attention_mask"] = [[1] * len(ids) for ids in enc["input_ids"]]
    inputs = tokenizer.pad(enc, padding=True, return_tensors="pt")
    device = _input_device(model)
    inputs = {k: (v.to(device) if hasattr(v, "to") else v)
              for k, v in inputs.items()}
    yes_id = tokenizer.convert_tokens_to_ids("yes")
    no_id = tokenizer.convert_tokens_to_ids("no")
    with torch.no_grad():
        last = model(**inputs).logits[:, -1, :]
    pair = torch.stack([last[:, no_id], last[:, yes_id]], dim=1).float()
    probs = torch.log_softmax(pair, dim=1)[:, 1].exp()
    return [float(p) for p in probs]


def score_pairs(query: str, texts: list[str]) -> list[float] | None:
    """Điểm relevance từng cặp (query, text). None = tắt/hỏng (fail-open)."""
    if os.environ.get("RAG_RERANK_ENABLED", "1") == "0":
        return None
    if _state["model"] is False:
        return None
    try:
        if _state["model"] is None:
            _state["model"], _state["tokenizer"] = _load()
        scorer = _score_qwen3 if _family() == "qwen3" else _score_seq_cls
        scores = scorer(_state["model"], _state["tokenizer"], query, texts)
        if len(scores) != len(texts):
            raise ValueError(f"expected {len(texts)} scores, got {len(scores)}")
        return scores
    except Exception:  # noqa: BLE001 — fail-open theo spec §4
        logger.warning("Reranker unavailable — falling back to hybrid-rrf order",
                       exc_info=True)
        _state["model"] = False
        return None
