# So sánh ba reranker — kế hoạch thực thi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một bảng số trên corpus thật cho ba reranker (`bge-reranker-v2-m3`, `Qwen3-Reranker-0.6B`, `Qwen3-Reranker-4B`) trên cùng bộ `retrieval` 64 ca, cùng ngày, cùng corpus — đủ để quyết định có đổi reranker production hay không. **Production không đổi trong plan này.**

**Architecture:** `RERANK_MODEL` từ hằng thành env (mặc định cũ). `reranker.py` thêm một **họ** model thứ hai: Qwen3-Reranker là decoder LM chấm bằng logit `yes`/`no` ở token cuối, khác hẳn cross-encoder đang có — nên có `_score_qwen3()` bên cạnh `_score_seq_cls()`, chọn theo tên model, cả hai sống trong cùng `try` fail-open. 4B không vừa GPU ở fp16 nên có đường nạp `device_map` qua `accelerate` (tràn CPU RAM), gate bằng env, chỉ dùng cho lượt đo. Bốn chân eval chạy bằng 4 tiến trình riêng vì `_load()` cache một lần/tiến trình.

**Tech Stack:** Python 3.11, `torch 2.11.0+cu128`, `transformers 5.15.0`, `accelerate` (mới), pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-so-sanh-reranker-design.md` — đọc §3 (vì sao 4B đi đường `device_map`), §4.1 (left padding là chỗ sai im lặng nhất), §7 (rủi ro fail-open nuốt lỗi thiết bị).

## Global Constraints

- **Định danh trong `backend/src` tiếng Anh.** Chú thích, docstring, thông điệp tiếng Việt. Tên hàm test tiếng Việt theo quy ước `backend/tests`.
- **Mọi lệnh pytest kèm** `-m "not integration and not live"` **và** `PYTHONIOENCODING=utf-8`, dùng `.venv/Scripts/python.exe`. Lệnh trần gọi API LLM thật.
- **Worktree không có `.venv` riêng.** Dùng interpreter cây chính, cwd trong worktree.
- **Mốc nền suite: `2707 passed, 1 skipped, 113 deselected`** (đo 2026-09-17 trên `main`, 214s). Mọi task giữ hoặc tăng số passed.
- **`RERANK_MODEL` mặc định KHÔNG đổi** (`BAAI/bge-reranker-v2-m3`). Đổi production là quyết định riêng sau khi có bảng.
- **Hợp đồng fail-open giữ nguyên:** `score_pairs` trả `None` khi hỏng, `_state["model"] = False`. 4 test cũ trong `test_reranker.py` monkeypatch `_load` trả **2-tuple** `(model, tokenizer)` — chữ ký đó **không được đổi**.
- **Đọc `method` trong kết quả của MỌI chân eval trước khi tin số.** `"dense-rrf"` ở chân có reranker = model đã chết lặng, không phải "model không hiệu quả".
- **Trước mỗi lượt đo**: `docker exec ollama ollama ps` phải rỗng (Ollama thứ hai vẫn có GPU passthrough).
- Mỗi task xong ghi vào spec mục "## 8. Ghi chép thực thi": *khó khăn* / *hướng chọn* / *giới hạn còn lại*.

---

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/src/rag/config.py` | **Sửa.** `RERANK_MODEL`, `RERANK_DEVICE_MAP`, `RERANK_GPU_BUDGET` đọc từ env. |
| `backend/src/rag/reranker.py` | **Sửa.** `_family()`, `_instantiate()`, `_input_device()`, `_score_seq_cls()`, `_score_qwen3()`; `_load()` và `score_pairs()` rẽ theo họ. |
| `backend/tests/rag/test_reranker_qwen3.py` | **Tạo mới.** Đường Qwen3 với tokenizer/model giả — không tải model. |
| `backend/tests/rag/test_reranker_device_map.py` | **Tạo mới.** Đường nạp `device_map` với lớp giả. |
| `backend/requirements.txt` | **Sửa.** Ghim `accelerate`. |
| `backend/spikes/spike_reranker_smoke.py` | **Tạo mới.** Khói: 3 cặp, in điểm + VRAM đỉnh + ms, cho từng model. |
| `backend/evals/results/reranker-2026-09-17/` | **Tạo mới.** 4 JSON thô của 4 chân đo. |
| `backend/src/rag/retrieve.py` | **Sửa (Task 5, tuỳ chọn).** `RAG_RERANK_MODE=override`. |

---

### Task 1: Họ model thứ hai — đường chấm điểm Qwen3

**Files:**
- Modify: `backend/src/rag/config.py:38-46`
- Modify: `backend/src/rag/reranker.py:64-143`
- Create: `backend/tests/rag/test_reranker_qwen3.py`

**Interfaces:**
- Consumes: `_state`, `_resolve_device()`, `RERANK_MAX_LENGTH` — đã có.
- Produces:
  - `config.RERANK_MODEL: str` — giờ đọc env, mặc định `"BAAI/bge-reranker-v2-m3"`.
  - `reranker.QWEN3_FAMILY_PREFIX = "Qwen/Qwen3-Reranker"`
  - `reranker.QWEN3_INSTRUCTION: str`, `reranker._QWEN3_PREFIX: str`, `reranker._QWEN3_SUFFIX: str`
  - `reranker._family(model_name: str | None = None) -> str` — `"qwen3"` | `"seq_cls"`, đọc `reranker.RERANK_MODEL` khi không truyền.
  - `reranker._input_device(model) -> str`
  - `reranker._score_seq_cls(model, tokenizer, query, texts) -> list[float]`
  - `reranker._score_qwen3(model, tokenizer, query, texts) -> list[float]` — ném `ValueError` nếu `tokenizer.padding_side != "left"`.
  - `_load()` **vẫn trả `(model, tokenizer)`**.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_reranker_qwen3.py`:

```python
# backend/tests/rag/test_reranker_qwen3.py
"""Đường chấm điểm Qwen3-Reranker — spec 2026-09-17 §4.1.

Unit thuần với tokenizer/model GIẢ — không tải model, không cần GPU. Điểm là
xác suất `yes` ở token cuối; hai chỗ sai im lặng nhất được gác ở đây:
(1) cắt ngắn làm mất suffix, (2) right padding làm "token cuối" là pad.
"""
import types

import pytest
import torch

from src.rag import reranker

YES, NO, PAD, PREFIX_TOK, SUFFIX_TOK, BODY_TOK = 7, 3, 0, 1, 2, 9


class _FakeQwenTok:
    """prefix → [1,1]; suffix → [2,2]; body → một token 9 mỗi từ."""
    def __init__(self, padding_side="left"):
        self.padding_side = padding_side

    def encode(self, text, add_special_tokens=False):
        if text == reranker._QWEN3_PREFIX:
            return [PREFIX_TOK, PREFIX_TOK]
        if text == reranker._QWEN3_SUFFIX:
            return [SUFFIX_TOK, SUFFIX_TOK]
        return [BODY_TOK] * len(text.split())

    def __call__(self, bodies, max_length=None, **kw):
        ids = [[BODY_TOK] * min(len(b.split()), max_length) for b in bodies]
        return {"input_ids": ids, "attention_mask": [[1] * len(x) for x in ids]}

    def pad(self, enc, padding=True, return_tensors="pt"):
        longest = max(len(x) for x in enc["input_ids"])
        rows = []
        for x in enc["input_ids"]:
            fill = [PAD] * (longest - len(x))
            rows.append(fill + x if self.padding_side == "left" else x + fill)
        ids = torch.tensor(rows)
        return {"input_ids": ids, "attention_mask": (ids != PAD).long()}

    def convert_tokens_to_ids(self, tok):
        return {"yes": YES, "no": NO}[tok]


class _FakeQwenModel:
    """logit[yes] cao KHI VÀ CHỈ KHI token cuối là suffix nguyên vẹn."""
    def eval(self):
        pass

    def __call__(self, input_ids, attention_mask):
        batch, length = input_ids.shape
        logits = torch.zeros(batch, length, 10)
        for b in range(batch):
            intact = int(input_ids[b, -1]) == SUFFIX_TOK
            logits[b, -1, YES] = 5.0 if intact else -5.0
            logits[b, -1, NO] = -5.0 if intact else 5.0
        return types.SimpleNamespace(logits=logits)


def test_family_theo_ten_model():
    assert reranker._family("Qwen/Qwen3-Reranker-0.6B") == "qwen3"
    assert reranker._family("Qwen/Qwen3-Reranker-4B") == "qwen3"
    assert reranker._family("BAAI/bge-reranker-v2-m3") == "seq_cls"


def test_family_mac_dinh_doc_module_global(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_MODEL", "Qwen/Qwen3-Reranker-0.6B")
    assert reranker._family() == "qwen3"


def test_qwen3_diem_la_xac_suat_yes_trong_khoang_0_1():
    got = reranker._score_qwen3(_FakeQwenModel(), _FakeQwenTok(), "q",
                                ["một hai ba", "bốn năm"])
    assert len(got) == 2
    assert all(0.0 < s < 1.0 for s in got)
    assert all(s > 0.99 for s in got), "suffix nguyên vẹn thì yes phải cao"


def test_qwen3_cat_ngan_van_giu_suffix(monkeypatch):
    # Tài liệu dài hơn max_length: nếu cắt từ phải KHÔNG chừa suffix, token
    # cuối là body và điểm rơi xuống gần 0 — mà không ném lỗi nào.
    monkeypatch.setattr(reranker, "RERANK_MAX_LENGTH", 12)
    long_doc = " ".join(["từ"] * 500)
    got = reranker._score_qwen3(_FakeQwenModel(), _FakeQwenTok(), "q", [long_doc])
    assert got[0] > 0.99, f"suffix bị cắt mất, điểm = {got[0]}"


def test_qwen3_tu_choi_right_padding():
    # Right padding: cặp ngắn có "token cuối" là PAD → điểm rác im lặng.
    # Phải NÉM chứ không được lặng lẽ trả số — fail-open ở score_pairs sẽ bắt
    # và tắt reranker, đúng hành vi mong muốn cho một cấu hình sai.
    with pytest.raises(ValueError, match="left"):
        reranker._score_qwen3(_FakeQwenModel(), _FakeQwenTok("right"), "q",
                              ["ngắn", "dài hơn một chút"])


def test_qwen3_batch_do_dai_khac_nhau_deu_dung(monkeypatch):
    got = reranker._score_qwen3(_FakeQwenModel(), _FakeQwenTok(), "q",
                                ["a", "a b c d e f g"])
    assert all(s > 0.99 for s in got), got


def test_score_pairs_re_theo_ho_qwen3(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_ENABLED", "1")
    monkeypatch.setattr(reranker, "RERANK_MODEL", "Qwen/Qwen3-Reranker-0.6B")
    monkeypatch.setattr(reranker, "_load",
                        lambda: (_FakeQwenModel(), _FakeQwenTok()))
    reranker._state.update(model=None, tokenizer=None)
    got = reranker.score_pairs("q", ["x", "y z"])
    assert got is not None and len(got) == 2
    reranker._state.update(model=None, tokenizer=None)


def test_input_device_uu_tien_model_device():
    m = types.SimpleNamespace(device=torch.device("cpu"))
    assert reranker._input_device(m) == "cpu"
    assert reranker._input_device(object()) in ("cpu", "cuda")
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_reranker_qwen3.py -m "not integration and not live" -q`
Expected: FAIL — `AttributeError: module 'src.rag.reranker' has no attribute '_family'`

- [ ] **Step 3: `config.py` — env-hoá**

Thay dòng `RERANK_MODEL = "BAAI/bge-reranker-v2-m3"` bằng:

```python
# Đọc từ env để bộ eval đổi model theo TIẾN TRÌNH mà không sửa mã (spec
# 2026-09-17 §4: mỗi chân đo là một tiến trình vì _load() cache một lần).
# Mặc định KHÔNG đổi — thay production là quyết định riêng sau khi có bảng số.
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# Rỗng = nạp kiểu cũ (.half().to(device)). "auto" = accelerate đặt lớp lên
# GPU tới ngân sách rồi tràn sang CPU RAM — CHỈ cho lượt đo 4B (fp16 8 GB
# không vừa card 8,15 GB). Độ trễ trên đường này KHÔNG đại diện triển khai.
RERANK_DEVICE_MAP = os.environ.get("RERANK_DEVICE_MAP", "")
RERANK_GPU_BUDGET = os.environ.get("RERANK_GPU_BUDGET", "5GiB")
```

- [ ] **Step 4: `reranker.py` — họ model + hai đường chấm**

Đổi import: `from .config import RERANK_MODEL, RERANK_MAX_LENGTH, RERANK_DEVICE, RERANK_DEVICE_MAP, RERANK_GPU_BUDGET`.

Thêm SAU `_state` và TRƯỚC `_cuda_available`:

```python
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
```

Thay `_load()`:

```python
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
```

Tách thân cũ của `score_pairs` thành `_score_seq_cls` và thêm `_score_qwen3`, đặt TRƯỚC `score_pairs`:

```python
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
    body_max = RERANK_MAX_LENGTH - len(prefix_ids) - len(suffix_ids)
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
```

Rồi `score_pairs` thành:

```python
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
```

- [ ] **Step 5: Chạy test mới + test cũ của reranker**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_reranker_qwen3.py tests/rag/test_reranker.py tests/rag/test_nap_am_reranker.py tests/rag/test_reranker_deps.py -m "not integration and not live" -q`
Expected: `8 passed` mới + toàn bộ test cũ xanh. Nếu test cũ đỏ vì `_FakeTok`/`_FakeModel` thiếu `.device` — `_input_device` đã lùi về `_resolve_device()`, nên không được đỏ; đỏ là do đổi sai chữ ký `_load`.

- [ ] **Step 6: Toàn suite**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2715 passed, 1 skipped, 113 deselected` (2707 + 8).

- [ ] **Step 7: Commit**

```bash
git add backend/src/rag/config.py backend/src/rag/reranker.py backend/tests/rag/test_reranker_qwen3.py
git commit -m "feat(rag): ho model thu hai cho reranker - duong cham diem Qwen3

Qwen3-Reranker la decoder LM cham bang P(yes) o token cuoi, khac han
cross-encoder bge dang co. 0.6B va 4B dung chung duong nay.

Hai cho sai im lang duoc gac bang test: cat ngan phai chua suffix (mat
suffix = mat vi tri doc diem, ra so rac khong loi), va bat buoc left
padding (right padding lam token cuoi cua cap ngan la PAD).

RERANK_MODEL doc tu env, mac dinh KHONG doi.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Đường nạp `device_map` cho 4B

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/rag/test_reranker_device_map.py`

**Interfaces:**
- Consumes: `reranker._instantiate(model_cls, device)` từ Task 1, `config.RERANK_DEVICE_MAP`, `config.RERANK_GPU_BUDGET`.
- Produces: không API mới; `accelerate` có mặt để `device_map="auto"` chạy được.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_reranker_device_map.py`:

```python
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
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_reranker_device_map.py -m "not integration and not live" -q`
Expected: 3 passed, 1 FAIL — `ModuleNotFoundError: No module named 'accelerate'`

- [ ] **Step 3: Cài và ghim `accelerate`**

```bash
cd backend && .venv/Scripts/python.exe -m pip install accelerate
.venv/Scripts/python.exe -c "import accelerate; print(accelerate.__version__)"
```

Ghi vào `requirements.txt` ngay dưới `transformers==5.15.0`, đúng phiên bản vừa in:

```
# accelerate: chỉ để `device_map="auto"` nạp Qwen3-Reranker-4B tràn sang CPU
# RAM cho lượt ĐO (spec 2026-09-17 §3). Thuần Python, không kernel CUDA.
accelerate==<phiên bản vừa in>
```

- [ ] **Step 4: Chạy để xác nhận XANH**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_reranker_device_map.py -m "not integration and not live" -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/tests/rag/test_reranker_device_map.py
git commit -m "feat(rag): duong nap device_map cho reranker 4B + ghim accelerate

fp16 4B = 8 GB, khong vua card 8,15 GB. accelerate dat lop len GPU toi
ngan sach roi tran CPU RAM — chi cho luot do. Test gac: khong duoc .to()
hay .half() len model da dat, fail-open se nuot loi do.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Khói trên model thật — tải, 3 cặp, VRAM, ms

**Files:**
- Create: `backend/spikes/spike_reranker_smoke.py`

**Interfaces:**
- Consumes: `reranker.score_pairs`, `reranker._state`, `reranker.RERANK_MODEL`.
- Produces: bảng khói in ra stdout; số ghi vào spec §8.

> Task này TẢI model: 0.6B ~1,2 GB, 4B ~8 GB. Chạy nền cho 4B. Trước khi chạy: `docker exec ollama ollama ps` phải rỗng; đóng trình duyệt.

- [ ] **Step 1: Viết script**

Tạo `backend/spikes/spike_reranker_smoke.py`:

```python
# backend/spikes/spike_reranker_smoke.py
"""Khói reranker: 3 cặp cố định, in điểm + VRAM đỉnh + ms — cho MỘT model.

Chạy mỗi model bằng một tiến trình riêng (env RERANK_MODEL), vì _load()
cache một lần. Không phải eval — chỉ để chắc model tải được, chấm ra số
có nghĩa, và biết chi phí trước khi đốt 64 × 20 cặp.

    RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B python -m spikes.spike_reranker_smoke
    RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto python -m spikes.spike_reranker_smoke
"""
import sys
import time

sys.path.insert(0, ".")
from src.rag import reranker  # noqa: E402

QUERY = "một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?"
# Cặp 1 là đáp án đúng (Điều 428), cặp 2 là bẫy trùng mặt chữ (Điều 309),
# cặp 3 lạc đề hẳn. Reranker tốt phải xếp 1 > 2 > 3.
DOCS = [
    "Điều 428. Đơn phương chấm dứt thực hiện hợp đồng. Một bên có quyền đơn "
    "phương chấm dứt thực hiện hợp đồng và không phải bồi thường thiệt hại khi "
    "bên kia vi phạm nghiêm trọng nghĩa vụ trong hợp đồng.",
    "Điều 309. Hậu quả pháp lý của việc tạm ngừng thực hiện hợp đồng. Khi hợp "
    "đồng bị tạm ngừng thực hiện thì hợp đồng vẫn còn hiệu lực.",
    "Điều 9. Thuế suất. Mức thuế suất 0% áp dụng đối với hàng hóa, dịch vụ "
    "xuất khẩu.",
]


def main() -> None:
    import torch
    print(f"model       : {reranker.RERANK_MODEL}  ({reranker._family()})")
    print(f"device_map  : {reranker.RERANK_DEVICE_MAP or '(kiểu cũ)'}")
    t0 = time.perf_counter()
    scores = reranker.score_pairs(QUERY, DOCS)
    load_ms = (time.perf_counter() - t0) * 1000
    if scores is None:
        print("HỎNG: score_pairs trả None — đọc warning ở trên.")
        sys.exit(1)
    # Lượt 2 mới là chi phí thật/lượt (lượt 1 gánh cả nạp model).
    t1 = time.perf_counter()
    for _ in range(5):
        reranker.score_pairs(QUERY, DOCS)
    per_call_ms = (time.perf_counter() - t1) * 1000 / 5
    order = sorted(range(3), key=lambda i: scores[i], reverse=True)
    print(f"điểm        : {[round(s, 4) for s in scores]}")
    print(f"thứ tự      : {[i + 1 for i in order]}   (mong đợi [1, 2, 3])")
    print(f"nạp + lượt 1: {load_ms:.0f} ms")
    print(f"ms/lượt (3 cặp, TB 5 lượt): {per_call_ms:.1f}")
    if torch.cuda.is_available():
        print(f"VRAM đỉnh   : {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Chạy cho từng model**

```bash
cd backend
docker exec ollama ollama ps        # PHẢI rỗng
PYTHONIOENCODING=utf-8 RERANK_MODEL=BAAI/bge-reranker-v2-m3 .venv/Scripts/python.exe -m spikes.spike_reranker_smoke
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B .venv/Scripts/python.exe -m spikes.spike_reranker_smoke
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto .venv/Scripts/python.exe -m spikes.spike_reranker_smoke
```

Expected: cả ba in `thứ tự`. **Ghi cả ba dòng `thứ tự` vào spec §8** — đây là phép thử định tính đầu tiên cho chính ca `Điều 428` mà spec §1 nêu. Nếu một model in `HỎNG`, đọc warning, sửa trước khi sang Task 4 — **không** chạy eval với model chết lặng.

Nếu 4B OOM ngay cả với `device_map=auto`: giảm `RERANK_GPU_BUDGET=3GiB`. Nếu vẫn OOM: `RERANK_DEVICE=cpu RERANK_DEVICE_MAP=` (toàn CPU, fp32, ~16 GB RAM) — chậm hơn nhưng vẫn đo được chất lượng.

- [ ] **Step 3: Commit**

```bash
git add backend/spikes/spike_reranker_smoke.py
git commit -m "spike(rag): khoi reranker - 3 cap co dinh, VRAM, ms

<DÁN 3 DÒNG thứ tự + ms + VRAM VÀO ĐÂY>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Bốn chân đo trên bộ `retrieval`

**Files:**
- Create: `backend/evals/results/reranker-2026-09-17/{no-rerank,bge-v2-m3,qwen3-0.6b,qwen3-4b}.json`

**Interfaces:**
- Consumes: `evals.run_eval --set retrieval` (đã có), env `RERANK_MODEL` / `RERANK_DEVICE_MAP` từ Task 1–2.
- Produces: 4 JSON + bảng trong spec §8.

- [ ] **Step 1: Chạy bốn chân, mỗi chân một tiến trình**

```bash
cd backend && mkdir -p evals/results/reranker-2026-09-17
docker exec ollama ollama ps        # PHẢI rỗng

PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 --no-rerank \
  > evals/results/reranker-2026-09-17/no-rerank.json

PYTHONIOENCODING=utf-8 RERANK_MODEL=BAAI/bge-reranker-v2-m3 .venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 \
  > evals/results/reranker-2026-09-17/bge-v2-m3.json

PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B .venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 \
  > evals/results/reranker-2026-09-17/qwen3-0.6b.json

# Chậm (ước 20–60 phút) — chạy nền.
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto .venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 \
  > evals/results/reranker-2026-09-17/qwen3-4b.json
```

`run_eval` in JSON ra stdout (dòng 1483) — redirect là đủ; **không** dùng `--save-baseline` (sẽ ghi đè `baseline-bge-m3-retrieval.json`).

- [ ] **Step 2: Kiểm `method` TRƯỚC khi đọc số**

```bash
cd backend && for f in evals/results/reranker-2026-09-17/*.json; do printf "%-14s " "$(basename $f .json)"; PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d['methods_seen'], 'errors=', len(d['errors']))" "$f"; done
```

Expected: `no-rerank` → `['dense-rrf']`; ba chân kia → `['dense-rrf+rerank']` **duy nhất**, `errors= 0`. Một chân reranker mà thấy `dense-rrf` là model chết lặng giữa lượt — **số của chân đó vô giá trị**, sửa và chạy lại.

- [ ] **Step 3: Dựng bảng**

```bash
cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe - <<'EOF'
import json
rows = ["no-rerank", "bge-v2-m3", "qwen3-0.6b", "qwen3-4b"]
print(f"{'chân':<12} {'r@6':>7} {'mrr':>7} {'easy':>7} {'hard':>7} {'trap':>7} {'p50ms':>7}")
for r in rows:
    d = json.load(open(f"evals/results/reranker-2026-09-17/{r}.json", encoding="utf-8"))
    b = d["by_difficulty"]
    print(f"{r:<12} {d['recall_at_6']:>7.4f} {d['mrr']:>7.4f} "
          f"{b['easy']['mrr']:>7.4f} {b['hard']['mrr']:>7.4f} {b['trap']['mrr']:>7.4f} "
          f"{d['lat_p50']:>7.0f}")
EOF
```

Dán bảng vào spec §8, kèm **đối đầu từng ca** trên nhóm `hard` (ca nào 0.6B/4B thắng bge, ca nào thua — `fails` của mỗi JSON có tên câu). Bảng tổng không đủ: lần trước bảng tổng của cách ghi-đè trông ổn cho tới khi nhìn từng ca thấy đáp án văng hẳn khỏi top-6.

- [ ] **Step 4: Commit số thô**

```bash
git add backend/evals/results/reranker-2026-09-17/
git commit -m "eval(rag): 4 chan do reranker tren bo retrieval 64 ca

<DÁN BẢNG VÀO ĐÂY>

p50 cua qwen3-4b la duong device_map tran CPU — KHONG dai dien trien khai.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5 (tuỳ chọn, chỉ khi có model thắng): mở lại tỉ lệ hoà 1:1

**Files:**
- Modify: `backend/src/rag/retrieve.py` (hàm `rerank`, ~dòng 130-140)
- Create: `backend/tests/rag/test_rerank_mode.py`

**Interfaces:**
- Consumes: `retrieve.rerank(query, chunks)`, `reranker.score_pairs` (monkeypatch trong test).
- Produces: env `RAG_RERANK_MODE` ∈ {`blend` (mặc định, hành vi cũ), `override`}.

**Vì sao:** tỉ lệ hoà 1:1 được chọn 2026-08-20 *vì* reranker cũ yếu ở nhóm `hard`. Với reranker mạnh hơn, cùng tỉ lệ đó là pha loãng 50% thứ vừa mua. `retrieve.py` ghi sẵn đây là câu hỏi mở.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_rerank_mode.py`:

```python
# backend/tests/rag/test_rerank_mode.py
"""RAG_RERANK_MODE — spec 2026-09-17 §5. Mặc định `blend` = hành vi cũ."""
import dataclasses

from src.rag import reranker, retrieve
from src.rag.types import Chunk


def _chunks(n):
    return [Chunk(chunk_id=i, doc_id="d", source_file="d", doc_title="t",
                  section_path=None, page=None, sheet=None, row_range=None,
                  text=f"c{i}", dense_score=0.5, sparse_score=None,
                  rrf_score=1.0 / (i + 1), rank=i) for i in range(4)]


def test_override_xep_thuan_theo_diem_cross_encoder(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_MODE", "override")
    # CE đảo ngược hoàn toàn thứ tự RRF.
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, ok = retrieve.rerank("q", _chunks(4))
    assert ok and [c.chunk_id for c in out] == [3, 2, 1, 0]


def test_blend_mac_dinh_giu_hanh_vi_hoa(monkeypatch):
    monkeypatch.delenv("RAG_RERANK_MODE", raising=False)
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, ok = retrieve.rerank("q", _chunks(4))
    # Hoà 1:1: chunk 0 (RRF hạng 1, CE hạng 4) và chunk 3 (RRF hạng 4, CE
    # hạng 1) BẰNG điểm; sorted ổn định giữ chunk 0 trước.
    assert ok and [c.chunk_id for c in out][0] == 0


def test_gia_tri_la_thi_lui_ve_blend(monkeypatch):
    monkeypatch.setenv("RAG_RERANK_MODE", "gì đó")
    monkeypatch.setattr(reranker, "score_pairs", lambda q, t: [0.1, 0.2, 0.3, 0.9])
    out, _ = retrieve.rerank("q", _chunks(4))
    assert [c.chunk_id for c in out][0] == 0
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_rerank_mode.py -m "not integration and not live" -q`
Expected: `test_override_...` FAIL (thứ tự vẫn là hoà).

- [ ] **Step 3: Cài đặt**

Trong `retrieve.rerank()`, thêm `import os` đầu file và thay đoạn từ `fused = sorted(...)` tới `reordered = ...`:

```python
    # Công tắc ĐO, mặc định giữ hoà 1:1 (đổi 2026-08-20). "override" = xếp
    # thuần theo cross-encoder — cách đã bị bác với reranker CŨ vì nó chấm
    # theo mặt chữ; câu hỏi mở là với reranker MẠNH hơn thì hoà 1:1 có còn
    # đúng không (spec 2026-09-17 §5). Giá trị lạ → blend, không ném.
    if os.environ.get("RAG_RERANK_MODE", "blend") == "override":
        order = by_score
    else:
        order = sorted(range(len(chunks)),
                       key=lambda i: -(1.0 / (RRF_K + i + 1)
                                       + 1.0 / (RRF_K + ce_rank[i] + 1)))
    reordered = [dataclasses.replace(chunks[i], rerank_score=scores[i], rank=pos)
                 for pos, i in enumerate(order)]
```

- [ ] **Step 4: Test + suite**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_rerank_mode.py tests/rag -m "not integration and not live" -q`
Expected: `3 passed` mới, toàn bộ `tests/rag` xanh.

- [ ] **Step 5: Đo `override` cho model thắng**

```bash
cd backend
PYTHONIOENCODING=utf-8 RAG_RERANK_MODE=override RERANK_MODEL=<model thắng> [RERANK_DEVICE_MAP=auto] .venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 \
  > evals/results/reranker-2026-09-17/<model thắng>-override.json
```

Thêm một dòng vào bảng Task 4 Step 3. Ghi cả `trap mrr`: lần trước ghi-đè làm đáp án **văng hẳn** khỏi top-6 ở 2 câu — đó mới là thứ phải nhìn, không phải mrr trung bình.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/retrieve.py backend/tests/rag/test_rerank_mode.py backend/evals/results/reranker-2026-09-17/
git commit -m "feat(rag): RAG_RERANK_MODE=override - cong tac do ti le hoa

Mac dinh blend, hanh vi cu giu nguyen. Do tren model thang:
<DÁN DÒNG override VÀO ĐÂY>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Ghi chép và quyết định

**Files:**
- Modify: `docs/superpowers/specs/2026-09-17-so-sanh-reranker-design.md` (thêm "## 8. Ghi chép thực thi")
- Modify: `docs/trang-thai-chung.md` (mục đang treo)

- [ ] **Step 1: Viết §8 vào spec** — ba mục bắt buộc + bảng Task 4 + đối đầu từng ca `hard` + dòng khói Task 3. Kèm một trong ba kết luận, **nêu tên**:
  - *Giữ bge* — không model nào thắng `hard mrr` mà không làm `recall@6`/`trap` tụt.
  - *Đổi sang 0.6B* — thắng, vừa GPU ở fp16, chỉ cần đổi mặc định `RERANK_MODEL` + `nap_am` + đo lại độ trễ production.
  - *4B đáng đi tiếp* — thắng rõ, nhưng CẦN cổng thứ hai: đo lại ở dạng lượng tử hoá (bitsandbytes trên sm_120 hoặc GGUF/llama.cpp) trước khi thay. Spec này không hứa cổng đó.

- [ ] **Step 2: Cập nhật `docs/trang-thai-chung.md`** — một mục: kết luận, đường dẫn spec, và điều còn treo (nếu chọn 4B: cổng lượng tử hoá; nếu đổi model: Kế hoạch A Task 3 lấy mốc nền SAU khi đổi).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-17-so-sanh-reranker-design.md docs/trang-thai-chung.md
git commit -m "docs(rag): ket luan so sanh 3 reranker + dieu con treo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Cổng nghiệm thu

- [ ] Suite: `2719 passed` (2707 + 8 + 4), hoặc `2722` nếu làm Task 5 (+3), 0 failed.
- [ ] `RERANK_MODEL` không đặt env → `_family() == "seq_cls"` và production **byte-identical** về hành vi: chạy `pytest tests/rag/test_reranker.py` xanh không sửa test.
- [ ] Cả 4 JSON có `methods_seen` đúng như Task 4 Step 2 và `errors = 0`.
- [ ] Spec §8 có bảng + đối đầu từng ca + một trong ba kết luận nêu tên.
- [ ] Không commit nào đổi mặc định `RERANK_MODEL` trong `config.py`.
- [ ] `git status --porcelain` sạch; `backend/tests/rag/fixtures/` không bị đổi.
- [ ] Nghiệm thu sống trên worktree của nhánh TRƯỚC khi merge: bật backend không env, hỏi một câu tài liệu, log phải in `Reranker BAAI/bge-reranker-v2-m3 (seq_cls) đã nạp trên cuda`.
