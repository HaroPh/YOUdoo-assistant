import dataclasses
import os
import re

from . import db as _db
from . import reranker
from .config import TOP_N, TOP_K, RRF_K, RAG_SCHEMA
from .embed import embed_query
from .ingest import segment_vi
from .chunking import fold_vi, index_text
from .types import Chunk, RetrievalResult
from .visibility import UNRESTRICTED, resolve

# `d.effective_date` lấy qua LEFT JOIN: nó thuộc rag_documents chứ không
# thuộc chunk. LEFT chứ không INNER — tài liệu nghiệp vụ không có ngày, và
# INNER JOIN sẽ lặng lẽ loại chúng khỏi mọi kết quả truy xuất.
_COLS = ("c.id, c.doc_id, c.source_file, c.doc_title, c.section_path, c.page, "
         "c.sheet, c.row_range, c.chunk_text, d.effective_date, c.source_kind")
_FROM = "rag_chunks c LEFT JOIN rag_documents d ON d.doc_id = c.doc_id"


def _vis_clause(visibility) -> tuple[str, tuple]:
    """Mệnh đề lọc lớp + tham số đi kèm. ('', ()) khi UNRESTRICTED — SQL của
    đường admin bằng ĐÚNG SQL trước 19b. Lọc đứng trong WHERE, tức TRƯỚC
    ORDER BY/LIMIT: lọc sau pool vừa tốn chỗ trong TOP_N vừa rò qua
    total_candidates."""
    if visibility is UNRESTRICTED:
        return "", ()
    return " AND c.visibility = ANY(%s)", (sorted(visibility),)


def _dense(conn, qvec, visibility) -> list[tuple]:
    clause, extra = _vis_clause(visibility)
    return conn.execute(
        f"SELECT {_COLS}, 1 - (c.embedding <=> %s::vector) AS score "
        f"FROM {_FROM} WHERE c.embedding IS NOT NULL{clause} "
        f"ORDER BY c.embedding <=> %s::vector LIMIT %s",
        (qvec, *extra, qvec, TOP_N),
    ).fetchall()


def _sparse(conn, qseg, visibility) -> list[tuple]:
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
    clause, extra = _vis_clause(visibility)
    return conn.execute(
        f"SELECT {_COLS}, ts_rank(c.ts_vector, plainto_tsquery('simple', %s)) AS score "
        f"FROM {_FROM} WHERE c.ts_vector @@ plainto_tsquery('simple', %s){clause} "
        f"ORDER BY score DESC LIMIT %s",
        (qseg, qseg, *extra, TOP_N),
    ).fetchall()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _or_tsquery(text_fold: str) -> str:
    """`a | b | c` — HỢP các từ, không phải GIAO.

    `plainto_tsquery` nối bằng AND: câu dài đòi chunk chứa MỌI từ, và đo được
    2026-09-08 là **0 chunk khớp** trên corpus 4.870 chunk. Đó chính là lỗi đã
    giết chân sparse cũ (0/64 truy vấn có kết quả) — bản đầu của chân bỏ dấu
    này tái tạo y nguyên nó, và chỉ số đo mới lộ ra: recall không dấu nhích
    0,0156 -> 0,0312 thay vì lên 0,6406 như mô phỏng.

    Lọc còn `[a-z0-9]+` sau khi đã bỏ dấu, nên chuỗi luôn an toàn cho
    `to_tsquery` — không cần escape, và không token nào mang ký tự toán tử."""
    return " | ".join(dict.fromkeys(
        t for t in _TOKEN_RE.findall(text_fold) if len(t) >= 2))


def method_label(fold_gop: bool, reranked: bool) -> str:
    """Nhãn `method` — kể đúng chân nào ĐÓNG GÓP, không phải chân nào được bật.

    `fold_gop` là "chân bỏ dấu có trả về ứng viên nào không", KHÔNG phải
    "chân bỏ dấu có bật không". Phân biệt này chính là bài học đắt nhất của
    tệp `test_sparse_van_chet.py`: nhãn cũ nói `hybrid` trong khi chân sparse
    **có chạy nhưng luôn rỗng** suốt nhiều tháng. "Có chạy" không phải "có
    đóng góp", và người đọc trace cần biết vế thứ hai.

    Hàm riêng chứ không dựng chuỗi tại chỗ, để test kiểm được TỪNG tổ hợp mà
    không cần DB.
    """
    return ("dense+fold-rrf" if fold_gop else "dense-rrf") +            ("+rerank" if reranked else "")


def fold_enabled() -> bool:
    """Công tắc chân BỎ DẤU. Đọc lúc GỌI để tắt được giữa chừng mà không
    phải nạp lại module — cùng khuôn với `RAG_RERANK_ENABLED`."""
    return os.environ.get("RAG_FOLD_ENABLED", "1") != "0"


def _lexical_fold(conn, qseg_fold: str, visibility) -> list[tuple]:
    """Chân khớp mặt chữ trên text ĐÃ BỎ DẤU — cả hai phía đều bỏ dấu.

    Vì sao chân này tồn tại trong khi ghi chú cũ kết luận "hồi sinh sparse là
    CÓ HẠI": kết luận đó vẫn đúng, nhưng nó đo chân FTS CÓ DẤU trên truy vấn
    CÓ DẤU. Chân này khác hẳn — nó bỏ dấu cả hai phía, và giá trị của nó nằm ở
    dạng truy vấn mà bộ vàng cũ CHƯA TỪNG ĐO.

    Đo 2026-09-08, bộ vàng 64 ca, ba dạng gõ (có dấu / nửa dấu / không dấu):
        dense một mình              1,0000 / 0,8594 / 0,0156
        RRF dense + chân này        0,9844 / 0,9219 / 0,6406
    Đổi 1 ca có dấu lấy +40 ca không dấu và +4 ca nửa dấu.
    """
    tq = _or_tsquery(qseg_fold)
    if not tq:
        return []
    clause, extra = _vis_clause(visibility)
    cur = conn.execute(
        f"SELECT {_COLS}, ts_rank(c.ts_vector_fold, to_tsquery('simple', %s)) AS score "
        f"FROM {_FROM} WHERE c.ts_vector_fold @@ to_tsquery('simple', %s){clause} "
        f"ORDER BY score DESC LIMIT {TOP_N}", (tq, tq, *extra))
    return cur.fetchall()


def _rrf_fold(folded: list[tuple], acc: dict) -> dict:
    """Cộng chân BỎ DẤU vào cùng phép hợp nhất, NGANG QUYỀN với dense.

    Không đi qua nhánh `sparse` của `_rrf()` vì nhánh đó ghi vào
    `["sparse"]`, làm `Chunk.sparse_score` nói sai chân nào sinh ra nó.
    """
    for rank, row in enumerate(folded):
        acc.setdefault(row[0], {"row": row, "rrf": 0.0, "dense": None,
                                "sparse": None, "fold": None})
        acc[row[0]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        acc[row[0]]["fold"] = float(row[-1])
    return acc


def _rrf(dense: list[tuple], sparse: list[tuple], acc: dict | None = None) -> dict:
    """Reciprocal Rank Fusion → {row_id: {'row', 'rrf', 'dense', 'sparse'}}.

    acc: accumulator to extend (default: fresh dict). Passing an existing
    dict lets retrieve() fold multiple queries' dense/sparse results into
    one pool (aux_queries) — dedup by row id is inherent to the dict."""
    acc = {} if acc is None else acc
    for rank, row in enumerate(dense):
        acc.setdefault(row[0], {"row": row, "rrf": 0.0, "dense": None,
                                "sparse": None, "fold": None})
        acc[row[0]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        acc[row[0]]["dense"] = float(row[-1])
    for rank, row in enumerate(sparse):
        acc.setdefault(row[0], {"row": row, "rrf": 0.0, "dense": None,
                                "sparse": None, "fold": None})
        acc[row[0]]["rrf"] += 1.0 / (RRF_K + rank + 1)
        acc[row[0]]["sparse"] = float(row[-1])
    return acc


def rerank(query: str, chunks: list[Chunk]) -> tuple[list[Chunk], bool]:
    """Cross-encoder rerank HOÀ với thứ tự RRF, fail-open (spec 2026-07-12 §3.3).

    (chunks, False) khi reranker tắt/hỏng — nguyên trạng thứ tự RRF, đúng
    hành vi trước khi có feature; (reordered, True) khi có điểm. Gọi
    score_pairs qua module attr để test monkeypatch được.

    CROSS-ENCODER LÀ MỘT LÁ PHIẾU, KHÔNG PHẢI KẺ GHI ĐÈ (đổi 2026-08-20).
    Trước đây hàm này xếp lại hoàn toàn theo điểm cross-encoder. Đo trên 64 ca
    của bộ `retrieval` thì cách đó THUA cả cách tắt hẳn reranker:

        recall@6   tắt 0,9635 | ghi đè 0,9453 | hoà 0,9766
        hard mrr   tắt 0,7160 | ghi đè 0,6135 | hoà 0,6758

    Đối đầu từng ca trên recall@6: hoà thắng ghi-đè 2–0 và thắng tắt-hẳn 2–0,
    không thua ca nào; còn tắt-hẳn với ghi-đè chỉ hoà 2–2.

    NGUYÊN NHÂN cách ghi đè hỏng: cross-encoder chấm nặng theo TRÙNG MẶT CHỮ
    của tiêu đề. Câu "một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là
    gì?" bị nó đẩy "Điều 309/311. HẬU QUẢ pháp lý của việc tạm ngừng/đình chỉ"
    lên hạng 1-2 với điểm DƯƠNG, còn đáp án đúng "Điều 428. Đơn phương chấm
    dứt" tụt xuống −2,87 và văng khỏi top-6. Trả lời đúng đòi hiểu "tự ý dừng
    giữa chừng" = "đơn phương chấm dứt" — đúng thứ trùng mặt chữ không làm
    được. Nên nó giúp ở nhóm `easy` (vốn đã trùng mặt chữ sẵn) và hại ở nhóm
    `hard` (vốn là nhóm cần truy xuất tốt).

    Hoà bằng RRF làm một chunk phải TỆ Ở CẢ HAI thứ hạng mới rơi khỏi top-k,
    nên một lá phiếu sai lệch không đủ sức đẩy đáp án đúng ra ngoài.

    ĐÁNH ĐỔI ĐÃ BIẾT VÀ CHẤP NHẬN. Trên bộ `multiturn` (12 ca) thứ tự đảo
    ngược — ở đó cách GHI ĐÈ mới là tốt nhất về mrr:

        multiturn mrr   tắt 0,7391 | ghi đè 0,9375 | hoà 0,8292
        multiturn r@6   tắt 1,0000 | ghi đè 1,0000 | hoà 1,0000

    Vẫn chọn hoà, vì hai lẽ: (a) trên multiturn CẢ BA cấu hình đều đạt
    recall@6 = 1,0, nên chênh lệch ở đó chỉ là thứ tự BÊN TRONG 6 chunk mà
    model đều đọc cả; (b) trên bộ `retrieval` cách ghi đè làm đáp án VĂNG HẲN
    khỏi top-6 ở hai câu — hỏng nặng hơn hẳn tụt từ hạng 1 xuống hạng 3.

    CÂU HỎI CÒN MỞ: chưa đo được tác động thật xuống câu trả lời cuối. Chỉ bộ
    `synthesis_live` trả lời được "hạng 1 so với hạng 3 có đổi đáp án không",
    và nó cần hạn mức LLM (đang cooldown lúc đổi, 2026-08-20). Nếu sau này đo
    được rằng thứ hạng trong top-6 có ảnh hưởng thật, cân nhắc lại tỉ trọng
    hai chân thay vì 1:1 như hiện nay.

    Cái giá còn lại: `trap` mrr tụt 0,8906 → 0,8562 so với tắt hẳn, và vẫn tốn
    ~100ms/truy vấn cho lượt gọi cross-encoder.

    sorted ổn định: điểm hoà bằng nhau thì giữ nguyên thứ tự RRF."""
    if not chunks:
        return chunks, False
    # Pair = đúng chuỗi đã index (crumb + body) — nếu chỉ đưa body, chunk
    # match nhờ crumb sẽ bị cross-encoder dìm (spec 2026-07-15 §3C).
    scores = reranker.score_pairs(query, [index_text(c.section_path, c.text)
                                          for c in chunks])
    if scores is None:
        return chunks, False
    # `chunks` đã ở thứ tự RRF, nên chỉ số i CHÍNH LÀ thứ hạng RRF của nó.
    by_score = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    ce_rank = {i: pos for pos, i in enumerate(by_score)}
    # Cùng công thức và cùng hằng RRF_K với _rrf() — hoà thứ hạng ở đây là
    # thêm một chân vào đúng phép hợp nhất đang dùng cho dense/sparse, không
    # phải một cơ chế chấm điểm thứ hai.
    #
    # Công tắc ĐO, mặc định giữ hoà 1:1 (đổi 2026-08-20). "override" = xếp
    # thuần theo cross-encoder — cách đã bị bác với reranker CŨ vì nó chấm
    # theo mặt chữ; câu hỏi mở là với reranker MẠNH hơn thì hoà 1:1 có còn
    # đúng không (spec 2026-09-17 §5). Giá trị lạ → blend, không ném.
    if os.environ.get("RAG_RERANK_MODE", "blend").strip().lower() == "override":
        order = by_score
    else:
        order = sorted(range(len(chunks)),
                       key=lambda i: -(1.0 / (RRF_K + i + 1)
                                       + 1.0 / (RRF_K + ce_rank[i] + 1)))
    reordered = [dataclasses.replace(chunks[i], rerank_score=scores[i], rank=pos)
                 for pos, i in enumerate(order)]
    return reordered, True


def compress(query: str, chunks: list[Chunk], k: int) -> list[Chunk]:
    return chunks[:k]  # Phase 2: top-k selection (extractive slot)


def retrieve(query: str, k: int = TOP_K, conn=None,
             aux_queries: tuple[str, ...] = (), *, visibility=None) -> RetrievalResult:
    # Fail-closed TẠI ĐÂY (spec §4): không truyền / None / rỗng → {'all'}.
    # Chỉ đúng đối tượng UNRESTRICTED mới bỏ lọc. Mục 17b từng lộ đường mất
    # vai — "quên truyền" phải là THẤY ÍT NHẤT.
    visibility = resolve(visibility)
    own = conn is None
    if own:
        conn = _db.connect()
        _db.ensure_schema(conn, RAG_SCHEMA)
    try:
        qvec = embed_query(query)
        qseg = segment_vi(query)
        dense, sparse = _dense(conn, qvec, visibility), _sparse(conn, qseg, visibility)
        fused = _rrf(dense, sparse)
        # Chân BỎ DẤU là một chân RRF NGANG QUYỀN với dense. Quét trọng số
        # 2026-09-08 cho thấy 1,0 là điểm duy nhất chạy được: dưới 0,7 nó
        # không bao giờ chen nổi vào top-20, từ 1,5 trở lên nó nuốt cả chân
        # dense (cả ba dạng gõ tụt về 0,7188).
        fold_gop = False
        if fold_enabled():
            hang_fold = _lexical_fold(conn, fold_vi(query), visibility)
            fold_gop = bool(hang_fold)
            fused = _rrf_fold(hang_fold, fused)
        for aux in aux_queries:
            if aux == query:
                continue
            aux_dense = _dense(conn, embed_query(aux), visibility)
            aux_sparse = _sparse(conn, segment_vi(aux), visibility)
            fused = _rrf(aux_dense, aux_sparse, acc=fused)
            if fold_enabled():
                hang_fold = _lexical_fold(conn, fold_vi(aux), visibility)
                fold_gop = fold_gop or bool(hang_fold)
                fused = _rrf_fold(hang_fold, fused)
        ordered = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)

        # Pool RỘNG (TOP_N) cho reranker chọn lọc, cắt k SAU rerank —
        # cắt trước là bug: reranker chỉ nhận 6 chunk đã chốt (spec §1.2).
        pool: list[Chunk] = []
        for rank, e in enumerate(ordered[:TOP_N]):
            row = e["row"]
            pool.append(Chunk(
                chunk_id=row[0], doc_id=row[1], source_file=row[2], doc_title=row[3],
                section_path=row[4], page=row[5], sheet=row[6], row_range=row[7],
                text=row[8],
                effective_date=row[9].isoformat() if row[9] else None,
                source_kind=row[10] or "text",
                dense_score=e["dense"], sparse_score=e["sparse"],
                fold_score=e.get("fold"),
                rrf_score=e["rrf"], rank=rank))
        rerank_query = query if not aux_queries else query + "\n" + "\n".join(aux_queries)
        chunks, reranked = rerank(rerank_query, pool)
        chunks = compress(query, chunks, k)
        return RetrievalResult(
            query=query, query_used=qseg, chunks=chunks,
            top_score=chunks[0].rrf_score if chunks else 0.0,
            total_candidates=len(fused),
            method=method_label(fold_gop, reranked))
    finally:
        if own:
            conn.close()
