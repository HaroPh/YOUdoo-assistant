import dataclasses

from . import db as _db
from . import reranker
from .config import TOP_N, TOP_K, RRF_K, RAG_SCHEMA
from .embed import embed_query
from .ingest import segment_vi
from .chunking import index_text
from .types import Chunk, RetrievalResult

_COLS = ("id, doc_id, source_file, doc_title, section_path, page, sheet, row_range, chunk_text")


def _dense(conn, qvec) -> list[tuple]:
    return conn.execute(
        f"SELECT {_COLS}, 1 - (embedding <=> %s::vector) AS score "
        f"FROM rag_chunks WHERE embedding IS NOT NULL "
        f"ORDER BY embedding <=> %s::vector LIMIT %s",
        (qvec, qvec, TOP_N),
    ).fetchall()


def _sparse(conn, qseg) -> list[tuple]:
    """Chân từ-khoá của hệ hybrid.

    ⚠️ ĐO ĐƯỢC 2026-08-20: chân này trả về **0 kết quả cho 64/64** câu hỏi của
    golden set. `plainto_tsquery` nối mọi từ tố bằng AND, mà sau pyvi một câu
    hỏi thật thành "thuế_suất thuế giá_trị gia_tăng là bao_nhiêu ?" — đòi cả
    "là" lẫn "bao_nhiêu" phải có trong CÙNG một chunk. Văn bản luật không bao
    giờ chứa "bao nhiêu", nên AND luôn hỏng.

    Hệ quả: `retrieve()` thực chất chạy **dense-only**, và `_rrf` hợp nhất
    đúng MỘT nguồn dù tên hàm và `method="hybrid-rrf"` nói khác. Lỗi không lộ
    ra ở test cơ học vì truy vấn từ khoá NGẮN vẫn chạy ("thuế suất" → 20 kết
    quả); nó chỉ lộ với câu hỏi thật của người dùng.

    ĐÃ THỬ HỒI SINH VÀ ĐÃ BỎ. Đổi sang `to_tsquery` dạng OR làm FTS bắn được
    64/64 câu, nhưng **`recall@20` tụt 1,0000 → 0,9766**: ứng viên sparse
    chiếm chỗ trong pool 20 và đẩy chunk đúng ra ngoài. Giả thuyết "do hư từ"
    cũng bị bác — lọc token có document-frequency > 30% cho kết quả y hệt
    (0,9766) và `mrr` còn nhích xuống.

    Nói cách khác: trên corpus này, dense-only **tốt hơn** hybrid như đang
    thiết kế. Muốn hồi sinh sparse thì phải đổi cách ứng viên vào pool (ví dụ
    mỗi chân giữ TOP_N riêng thay vì chia nhau 20 chỗ), chứ không phải sửa
    truy vấn."""
    return conn.execute(
        f"SELECT {_COLS}, ts_rank(ts_vector, plainto_tsquery('simple', %s)) AS score "
        f"FROM rag_chunks WHERE ts_vector @@ plainto_tsquery('simple', %s) "
        f"ORDER BY score DESC LIMIT %s",
        (qseg, qseg, TOP_N),
    ).fetchall()


def _rrf(dense: list[tuple], sparse: list[tuple], acc: dict | None = None) -> dict:
    """Reciprocal Rank Fusion → {row_id: {'row', 'rrf', 'dense', 'sparse'}}.

    acc: accumulator to extend (default: fresh dict). Passing an existing
    dict lets retrieve() fold multiple queries' dense/sparse results into
    one pool (aux_queries) — dedup by row id is inherent to the dict."""
    acc = {} if acc is None else acc
    for rank, row in enumerate(dense):
        acc.setdefault(row[0], {"row": row, "rrf": 0.0, "dense": None, "sparse": None})
        acc[row[0]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        acc[row[0]]["dense"] = float(row[-1])
    for rank, row in enumerate(sparse):
        acc.setdefault(row[0], {"row": row, "rrf": 0.0, "dense": None, "sparse": None})
        acc[row[0]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        acc[row[0]]["sparse"] = float(row[-1])
    return acc


def rerank(query: str, chunks: list[Chunk]) -> tuple[list[Chunk], bool]:
    """Cross-encoder rerank, fail-open (spec 2026-07-12 §3.3).

    (chunks, False) khi reranker tắt/hỏng — nguyên trạng thứ tự RRF, đúng
    hành vi trước khi có feature; (reordered, True) khi có điểm. Gọi
    score_pairs qua module attr để test monkeypatch được. sorted ổn định:
    điểm bằng nhau giữ nguyên thứ tự RRF."""
    if not chunks:
        return chunks, False
    # Pair = đúng chuỗi đã index (crumb + body) — nếu chỉ đưa body, chunk
    # match nhờ crumb sẽ bị cross-encoder dìm (spec 2026-07-15 §3C).
    scores = reranker.score_pairs(query, [index_text(c.section_path, c.text)
                                          for c in chunks])
    if scores is None:
        return chunks, False
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    reordered = [dataclasses.replace(chunks[i], rerank_score=scores[i], rank=pos)
                 for pos, i in enumerate(order)]
    return reordered, True


def compress(query: str, chunks: list[Chunk], k: int) -> list[Chunk]:
    return chunks[:k]  # Phase 2: top-k selection (extractive slot)


def retrieve(query: str, k: int = TOP_K, conn=None,
             aux_queries: tuple[str, ...] = ()) -> RetrievalResult:
    own = conn is None
    if own:
        conn = _db.connect()
        _db.ensure_schema(conn, RAG_SCHEMA)
    try:
        qvec = embed_query(query)
        qseg = segment_vi(query)
        dense, sparse = _dense(conn, qvec), _sparse(conn, qseg)
        fused = _rrf(dense, sparse)
        for aux in aux_queries:
            if aux == query:
                continue
            aux_dense = _dense(conn, embed_query(aux))
            aux_sparse = _sparse(conn, segment_vi(aux))
            fused = _rrf(aux_dense, aux_sparse, acc=fused)
        ordered = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)

        # Pool RỘNG (TOP_N) cho reranker chọn lọc, cắt k SAU rerank —
        # cắt trước là bug: reranker chỉ nhận 6 chunk đã chốt (spec §1.2).
        pool: list[Chunk] = []
        for rank, e in enumerate(ordered[:TOP_N]):
            row = e["row"]
            pool.append(Chunk(
                chunk_id=row[0], doc_id=row[1], source_file=row[2], doc_title=row[3],
                section_path=row[4], page=row[5], sheet=row[6], row_range=row[7],
                text=row[8], dense_score=e["dense"], sparse_score=e["sparse"],
                rrf_score=e["rrf"], rank=rank))
        rerank_query = query if not aux_queries else query + "\n" + "\n".join(aux_queries)
        chunks, reranked = rerank(rerank_query, pool)
        chunks = compress(query, chunks, k)
        return RetrievalResult(
            query=query, query_used=qseg, chunks=chunks,
            top_score=chunks[0].rrf_score if chunks else 0.0,
            total_candidates=len(fused),
            method="hybrid-rrf+rerank" if reranked else "hybrid-rrf")
    finally:
        if own:
            conn.close()
