import pytest


def _seed(conn, rows):
    """rows: list of (doc_id, text, vec). Inserts a doc + one chunk each."""
    for doc_id, text, vec in rows:
        conn.execute("INSERT INTO rag_documents (doc_id, source_file, content_hash) "
                     "VALUES (%s,%s,%s)", (doc_id, f"{doc_id}.docx", doc_id))
        conn.execute(
            "INSERT INTO rag_chunks (doc_id, source_file, doc_title, section_path, "
            "chunk_index, token_count, chunk_text, embedding, ts_vector) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s, to_tsvector('simple', %s))",
            (doc_id, f"{doc_id}.docx", "T", "A › B", 0, 5, text, vec, text))


@pytest.mark.integration
def test_retrieve_returns_result_with_scores_and_ordering(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    # doc A is the exact dense match; doc B is far
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
        ("B", "Quy trình bảo trì máy CNC", [0.0] * 1023 + [1.0]),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)

    res = r.retrieve("chính sách hoàn hàng", k=5, conn=clean_tables)
    assert res.method == "hybrid-rrf"
    assert not res.is_empty()
    assert res.chunks[0].doc_id == "A"                 # nearest dense → top
    assert res.top_score == res.chunks[0].rrf_score
    assert res.chunks[0].rank == 0
    assert res.chunks[0].dense_score is not None


@pytest.mark.integration
def test_retrieve_empty_on_no_match(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    res = r.retrieve("không có gì", k=5, conn=clean_tables)
    assert res.is_empty() and res.top_score == 0.0


# ── Cross-encoder rerank wiring (spec 2026-07-12-rag-reranker) ────────────────
# Mock reranker.score_pairs qua module attr (fake bỏ qua env — autouse
# _rerank_off không ảnh hưởng các test này).


@pytest.mark.integration
def test_rerank_reorders_and_tags_scores(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
        ("B", "Quy trình bảo trì máy CNC", [1.0, 1.0] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    # A đứng đầu theo RRF; mock cho B điểm cao hơn → B phải lên đầu
    monkeypatch.setattr(r.reranker, "score_pairs",
                        lambda q, texts: [0.1, 0.9])
    res = r.retrieve("hoàn hàng chính sách", k=5, conn=clean_tables)
    assert res.method == "hybrid-rrf+rerank"
    assert res.chunks[0].doc_id == "B"
    assert res.chunks[0].rerank_score == pytest.approx(0.9)
    assert res.chunks[0].rank == 0
    assert res.chunks[1].doc_id == "A"
    assert res.chunks[1].rank == 1
    # invariant giữ nguyên công thức: top_score = rrf của chunk ĐỨNG ĐẦU
    assert res.top_score == res.chunks[0].rrf_score


@pytest.mark.integration
def test_rerank_pool_wider_than_k(clean_tables, monkeypatch):
    # FIX CHÍNH: chunk hạng-7-theo-RRF (ngoài top-6) phải lọt được vào kết
    # quả khi cross-encoder chấm nó cao nhất — trước fix, rerank chỉ nhận 6
    # chunk đã chốt nên điều này bất khả thi.
    from src.rag import retrieve as r
    rows = []
    for i in range(8):
        marker = " MARKER" if i == 6 else ""
        rows.append((f"D{i}", f"nội dung tài liệu số {i}{marker}",
                     [1.0, float(i)] + [0.0] * 1022))
    _seed(clean_tables, rows)
    # cos(q, D_i) = 1/sqrt(1+i^2) giảm dần theo i → RRF order = D0..D7
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    monkeypatch.setattr(r.reranker, "score_pairs",
                        lambda q, texts: [10.0 if "MARKER" in t else 0.0
                                          for t in texts])
    res = r.retrieve("an toàn kho lạnh", k=6, conn=clean_tables)
    ids = [c.doc_id for c in res.chunks]
    assert len(ids) == 6
    assert ids[0] == "D6"                      # hạng-7 RRF lên đầu nhờ rerank
    # sort ổn định: các điểm 0.0 giữ nguyên thứ tự RRF → D0..D4 theo sau
    assert ids == ["D6", "D0", "D1", "D2", "D3", "D4"]
    assert "D5" not in ids and "D7" not in ids
    assert res.chunks[0].rerank_score == pytest.approx(10.0)


@pytest.mark.integration
def test_rerank_fail_open_keeps_rrf_order(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
        ("B", "Quy trình bảo trì máy CNC", [1.0, 1.0] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    monkeypatch.setattr(r.reranker, "score_pairs", lambda q, texts: None)
    res = r.retrieve("hoàn hàng", k=5, conn=clean_tables)
    assert res.method == "hybrid-rrf"          # không nói dối khi fail-open
    assert res.chunks[0].doc_id == "A"          # nguyên trạng thứ tự RRF
    assert res.chunks[0].rerank_score is None
    assert res.top_score == res.chunks[0].rrf_score


@pytest.mark.integration
def test_rerank_pairs_include_section_path(clean_tables, monkeypatch):
    # Spec 2026-07-15 §3C: tầng nào chấm điểm phải thấy đúng chuỗi đã index —
    # nếu reranker chỉ thấy body, chunk match nhờ crumb sẽ bị dìm xuống.
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    seen = []

    def _capture(q, texts):
        seen.extend(texts)
        return [0.5 for _ in texts]

    monkeypatch.setattr(r.reranker, "score_pairs", _capture)
    r.retrieve("hoàn hàng", k=5, conn=clean_tables)
    # _seed chèn section_path="A › B" → pair = crumb + body
    assert seen == ["A › B Khách hàng hoàn hàng trong 30 ngày"]


# ── aux_queries: multi-query candidate pooling ─────────────────────────────


def test_rrf_accumulates_into_existing_acc():
    from src.rag.retrieve import _rrf
    dense1 = [(1, "d1", "f1", "t1", None, None, None, None, "x", 0.9)]
    acc = _rrf(dense1, [])
    dense2 = [(2, "d2", "f2", "t2", None, None, None, None, "y", 0.8)]
    merged = _rrf(dense2, [], acc=acc)
    assert merged is acc  # mutates + returns the SAME dict passed in
    assert set(merged.keys()) == {1, 2}
    assert merged[1]["rrf"] > 0 and merged[2]["rrf"] > 0


@pytest.mark.integration
def test_retrieve_without_aux_query_never_calls_embed_query_extra(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
    ])
    calls = []

    def fake_embed(q):
        calls.append(q)
        return [1.0] + [0.0] * 1023

    monkeypatch.setattr(r, "embed_query", fake_embed)
    r.retrieve("chính sách hoàn hàng", k=5, conn=clean_tables)
    assert calls == ["chính sách hoàn hàng"]  # default aux_queries=() → no extra call


@pytest.mark.integration
def test_retrieve_aux_query_equal_to_primary_is_skipped(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
    ])
    calls = []

    def fake_embed(q):
        calls.append(q)
        return [1.0] + [0.0] * 1023

    monkeypatch.setattr(r, "embed_query", fake_embed)
    r.retrieve("chính sách hoàn hàng", k=5, conn=clean_tables,
               aux_queries=("chính sách hoàn hàng",))
    assert calls == ["chính sách hoàn hàng"]  # aux == query → no 2nd embed call


@pytest.mark.integration
def test_retrieve_aux_query_pulls_crowded_out_doc_into_pool(clean_tables, monkeypatch):
    """Reproduces the real bug's shape: 20 distractors all rank closer to the
    primary query than the true target doc, pushing it out of _dense()'s
    TOP_N=20 fetch window entirely. aux_queries must still recover it — doc B
    gets a dense AND sparse hit on the aux query (rank-0 on both channels),
    which is mathematically guaranteed to outscore any single distractor's
    best possible combined score (see spec Findings — no reliance on SQL
    tie-break order)."""
    from src.rag import retrieve as r
    rows = [(f"D{i}", f"distractor {i}", [1.0, float(i + 1)] + [0.0] * 1022)
            for i in range(20)]
    rows.append(("B", "qb noi dung tai lieu dich", [0.0] * 1023 + [1.0]))
    _seed(clean_tables, rows)

    VEC_A = [1.0] + [0.0] * 1023
    VEC_B = [0.0] * 1023 + [1.0]

    def fake_embed(q):
        return VEC_B if q == "qB" else VEC_A

    monkeypatch.setattr(r, "embed_query", fake_embed)

    without_aux = r.retrieve("qA", k=25, conn=clean_tables)
    assert "B" not in [c.doc_id for c in without_aux.chunks]

    with_aux = r.retrieve("qA", k=25, conn=clean_tables, aux_queries=("qB",))
    assert "B" in [c.doc_id for c in with_aux.chunks]


# ── Task 3: rerank query concatenates aux_queries (spec Finding #7) ────────


@pytest.mark.integration
def test_rerank_query_includes_aux_when_present(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "noi dung tai lieu", [1.0] + [0.0] * 1023),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    seen = []

    def _capture(q, texts):
        seen.append(q)
        return [0.5 for _ in texts]

    monkeypatch.setattr(r.reranker, "score_pairs", _capture)
    r.retrieve("SLA", k=5, conn=clean_tables,
               aux_queries=("Theo SLA giao hang khan cap",))
    assert seen == ["SLA\nTheo SLA giao hang khan cap"]


@pytest.mark.integration
def test_rerank_query_unchanged_when_no_aux(clean_tables, monkeypatch):
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "noi dung tai lieu", [1.0] + [0.0] * 1023),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    seen = []

    def _capture(q, texts):
        seen.append(q)
        return [0.5 for _ in texts]

    monkeypatch.setattr(r.reranker, "score_pairs", _capture)
    r.retrieve("SLA", k=5, conn=clean_tables)  # aux_queries defaults to ()
    assert seen == ["SLA"]  # no "\n" join — byte-for-byte pre-Task-3 behavior


@pytest.mark.integration
def test_rerank_recovers_doc_when_bare_query_lacks_context(clean_tables, monkeypatch):
    """Deterministic version of the live bug (spec Finding #7): a fake
    cross-encoder that can only recognize the right doc's content when the
    AUX query's context reaches the rerank string — proves concatenation
    (not just pooling) is what lets a bare-acronym primary query still
    surface the doc in the final result."""
    from src.rag import retrieve as r
    # RIGHT's text deliberately does NOT contain the literal string "SLA" —
    # if it did, plainto_tsquery('simple', 'SLA') would sparse-match it
    # directly against the bare primary query alone, pre-empting the very
    # thing this test isolates (whether rerank, not pooling, recovers it).
    _seed(clean_tables, [
        ("RIGHT", "quy dinh ve thoi gian giao hang khan cap", [1.0, 1.0] + [0.0] * 1022),
        ("WRONG", "chuong muc luat lao dong chung chung", [1.0, 0.9] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)

    def fake_score(q, texts):
        # Only recognizes RIGHT's content when the rerank query carries the
        # "khan cap" marker — absent from bare "SLA" alone, present only via
        # the concatenated aux query.
        return [1.0 if ("khan cap" in q and "quy dinh ve thoi gian" in t) else 0.1
                for t in texts]

    monkeypatch.setattr(r.reranker, "score_pairs", fake_score)

    without_aux = r.retrieve("SLA", k=2, conn=clean_tables)
    assert without_aux.chunks[0].doc_id != "RIGHT"  # bare query alone can't recover it

    with_aux = r.retrieve("SLA", k=2, conn=clean_tables,
                          aux_queries=("SLA giao hang khan cap",))
    assert with_aux.chunks[0].doc_id == "RIGHT"  # concatenation recovers it


# ── compress(): trần theo mục có bù (2026-08-19) ──────────────────────────────
# Trước đây compress() là chunks[:k] thuần, không có gì ngăn nhiều chunk của
# CÙNG một Điều chiếm nhiều ô trong 6 ô gửi cho LLM. Đo trên golden set thật:
# top-6 chỉ có 4,80/6 mục phân biệt, 20/56 câu có <=4 — tức ~20% ô ngữ cảnh là
# bản trùng (spec 2026-08-19 §11.2).
#
# LƯU Ý VỀ BỘ ĐO: recall@6/mrr chấm trên NHÃN, nên khử trùng lặp chỉ có thể làm
# chúng tăng hoặc giữ nguyên — theo cấu tạo, không phải theo chất lượng. Mặt
# hại thật (một Điều dài bị chia 3 chunk, ta chỉ đưa 1, phần chứa câu trả lời
# nằm ở chunk bị bỏ) thì bộ đo MÙ hoàn toàn. Đó là lý do cap mặc định phải
# thận trọng, không chọn theo số.

def _chunk(chunk_id, source_file, section_path, *, sheet=None, rank=0):
    from src.rag.types import Chunk
    return Chunk(chunk_id=chunk_id, doc_id="d", source_file=source_file,
                 doc_title="T", section_path=section_path, page=None, sheet=sheet,
                 row_range=None, text=f"t{chunk_id}", dense_score=None,
                 sparse_score=None, rrf_score=0.0, rank=rank)


def test_compress_backfills_from_deeper_pool_when_capped(monkeypatch):
    # Pool: A,A,A,B,C — cap=1 phải trả về A,B,C chứ không phải A,A,A.
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 1)
    pool = [_chunk(1, "f.pdf", "A"), _chunk(2, "f.pdf", "A"), _chunk(3, "f.pdf", "A"),
            _chunk(4, "f.pdf", "B"), _chunk(5, "f.pdf", "C")]
    got = r.compress("q", pool, 3)
    assert [c.chunk_id for c in got] == [1, 4, 5]


def test_compress_keeps_highest_ranked_chunk_of_each_section(monkeypatch):
    # Giữ bản ĐẦU TIÊN của mỗi mục — pool đã xếp hạng, nên bản đầu là bản tốt
    # nhất. Giữ bản sau là âm thầm hạ chất lượng.
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 1)
    pool = [_chunk(9, "f.pdf", "A"), _chunk(1, "f.pdf", "A"), _chunk(4, "f.pdf", "B")]
    got = r.compress("q", pool, 2)
    assert [c.chunk_id for c in got] == [9, 4]


def test_compress_cap_two_allows_two_chunks_of_same_section(monkeypatch):
    # Điều dài bị chia nhiều chunk vẫn được vào 2 ô — đây chính là lý do mặc
    # định KHÔNG phải cap=1 (chunk_span baseline = 2,39).
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 2)
    pool = [_chunk(1, "f.pdf", "A"), _chunk(2, "f.pdf", "A"), _chunk(3, "f.pdf", "A"),
            _chunk(4, "f.pdf", "B")]
    got = r.compress("q", pool, 3)
    assert [c.chunk_id for c in got] == [1, 2, 4]


def test_compress_same_section_path_in_different_files_not_merged(monkeypatch):
    # "Điều 3. Giải thích từ ngữ" có 32 chunk nằm rải NHIỀU luật khác nhau.
    # Khoá phải là CẶP (tệp, mục); khoá bằng mục đơn sẽ gộp nhầm hai văn bản.
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 1)
    pool = [_chunk(1, "luat-a.pdf", "Điều 3"), _chunk(2, "luat-b.pdf", "Điều 3")]
    got = r.compress("q", pool, 2)
    assert [c.chunk_id for c in got] == [1, 2]


def test_compress_xlsx_keyed_by_sheet(monkeypatch):
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 1)
    pool = [_chunk(1, "g.xlsx", None, sheet="S1"), _chunk(2, "g.xlsx", None, sheet="S1"),
            _chunk(3, "g.xlsx", None, sheet="S2")]
    got = r.compress("q", pool, 2)
    assert [c.chunk_id for c in got] == [1, 3]


def test_compress_falls_back_to_prefix_cut_when_pool_lacks_distinct_sections(monkeypatch):
    # Pool toàn MỘT mục: không có gì để bù. Phải vẫn trả đủ k, KHÔNG trả 1
    # chunk — thà có bản trùng còn hơn bỏ đói ngữ cảnh của LLM.
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 1)
    pool = [_chunk(i, "f.pdf", "A") for i in range(1, 6)]
    got = r.compress("q", pool, 3)
    assert [c.chunk_id for c in got] == [1, 2, 3]


def test_compress_cap_larger_than_pool_is_old_behaviour(monkeypatch):
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 99)
    pool = [_chunk(1, "f.pdf", "A"), _chunk(2, "f.pdf", "A"), _chunk(3, "f.pdf", "B")]
    assert r.compress("q", pool, 2) == pool[:2]


def test_compress_invalid_cap_never_empties_result(monkeypatch):
    # cap=0 do gõ nhầm env: KHÔNG được biến retrieval thành rỗng. Fail-safe về
    # hành vi cũ, cùng triết lý fail-open của reranker.
    from src.rag import retrieve as r
    monkeypatch.setattr(r, "SECTION_CAP", 0)
    pool = [_chunk(1, "f.pdf", "A"), _chunk(2, "f.pdf", "A"), _chunk(3, "f.pdf", "B")]
    assert r.compress("q", pool, 2) == pool[:2]


def test_compress_empty_pool():
    from src.rag import retrieve as r
    assert r.compress("q", [], 6) == []
