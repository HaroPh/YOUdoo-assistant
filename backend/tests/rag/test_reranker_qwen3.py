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

    class _RecordingModel(_FakeQwenModel):
        """Ghi lại chiều dài chuỗi THẬT đã lắp ráp (prefix+body+suffix, sau
        pad) — đây mới là chỗ `- len(prefix_ids) - len(suffix_ids)` trong
        body_max phải giữ. Điểm số một mình không bắt được: một cách tính
        body_max sai (ví dụ quên trừ) vẫn giữ suffix nguyên vẹn ở cuối, vẫn
        cho điểm cao, nhưng CHUỖI TỔNG vượt ngân sách."""
        last_shape = None

        def __call__(self, input_ids, attention_mask):
            _RecordingModel.last_shape = tuple(input_ids.shape)
            return super().__call__(input_ids, attention_mask)

    got = reranker._score_qwen3(_RecordingModel(), _FakeQwenTok(), "q", [long_doc])
    assert got[0] > 0.99, f"suffix bị cắt mất, điểm = {got[0]}"
    assert _RecordingModel.last_shape[1] <= reranker.RERANK_MAX_LENGTH, (
        "prefix+body+suffix vượt ngân sách — body_max không trừ đủ")


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
