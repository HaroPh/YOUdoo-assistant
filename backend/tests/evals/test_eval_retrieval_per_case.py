# backend/tests/evals/test_eval_retrieval_per_case.py
"""eval_retrieval trả per_case — để đối đầu từng ca giữa các reranker
(spec 2026-09-17 §4). Bảng trung bình giấu được chuyện đáp án văng khỏi
top-6 ở từng câu — bài học của lần đổi reranker 2026-08-20."""
import json
from types import SimpleNamespace

from evals import run_eval


def _chunk(source_file, section_path):
    return SimpleNamespace(source_file=source_file, section_path=section_path,
                           sheet=None)


async def test_ket_qua_co_per_case_du_truong_va_json_hoa_duoc(monkeypatch):
    case = ("câu hỏi thử", frozenset({("a.pdf", "Điều 1")}), "hard")
    monkeypatch.setattr(run_eval, "RETRIEVAL_CASES", [case])
    fake = SimpleNamespace(
        chunks=[_chunk("x/b.pdf", "Điều 9"), _chunk("x/a.pdf", "Điều 1")],
        method="dense-rrf+rerank")
    monkeypatch.setattr(run_eval, "_retrieve", lambda q, k: fake)
    result = await run_eval.eval_retrieval()
    assert len(result["per_case"]) == 1
    row = result["per_case"][0]
    assert row["question"] == "câu hỏi thử"
    assert row["difficulty"] == "hard"
    assert row["method"] == "dense-rrf+rerank"
    assert row["reciprocal_rank"] == 0.5
    assert row["hit_ranks"] == [2]
    json.dumps(result, ensure_ascii=False)
