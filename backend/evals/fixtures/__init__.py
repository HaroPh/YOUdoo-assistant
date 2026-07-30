# backend/evals/fixtures/__init__.py
"""Fixture chunk ĐÓNG BĂNG từ RAG DB thật (SP-0 spec §4.0b).

Vì sao fixture thay vì retrieval sống: retrieval KHÔNG đổi khi migrate cloud
(embedding + reranker vẫn local, không phải role LLM) — fixture cô lập đúng
biến đang đổi là model sinh câu trả lời. Phụ lợi: không phụ thuộc Postgres
đang sống, không trôi kết quả khi corpus thay đổi (bài học round 6: RAG dev
data từng bị xoá giữa session).

chunks.json được SINH bằng script trong plan (Task 4 Step 1) từ retrieve()
thật — KHÔNG viết tay nội dung tài liệu.
"""
import json
from pathlib import Path

from src.rag.types import Chunk

_PATH = Path(__file__).resolve().parent / "chunks.json"
_FIELDS = ("chunk_id", "doc_id", "source_file", "doc_title", "section_path",
           "page", "sheet", "row_range", "text", "dense_score",
           "sparse_score", "rrf_score", "rank", "rerank_score")


def _data() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def available_topics() -> list[str]:
    return sorted(_data())


def load_chunks(topic: str) -> list[Chunk]:
    """Chunk của 1 topic, đúng thứ tự đã đóng băng. KeyError nếu topic lạ."""
    raw = _data()
    if topic not in raw:
        raise KeyError(f"topic không có trong fixture: {topic}")
    return [Chunk(**{k: row[k] for k in _FIELDS}) for row in raw[topic]]
