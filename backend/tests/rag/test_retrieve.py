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
    # BA tài liệu, không phải hai: từ 2026-08-20 cross-encoder chỉ là MỘT LÁ
    # PHIẾU hoà vào thứ hạng RRF. Với đúng hai ứng viên đảo chỗ cho nhau, hai
    # lá phiếu triệt tiêu nhau tuyệt đối và thứ tự RRF thắng tie-break — xem
    # test_rerank_khong_lat_duoc_cap_doi_xung ngay dưới. Muốn chứng minh "có
    # xếp lại thật" thì cần đủ ứng viên để lá phiếu tạo được chênh lệch.
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
        ("B", "Quy trình bảo trì máy CNC", [1.0, 1.0] + [0.0] * 1022),
        ("C", "Biểu mẫu đề nghị thanh toán", [1.0, 2.0] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    # RRF: A, B, C. Cross-encoder: B, C, A → hoà lại thì B lên đầu.
    monkeypatch.setattr(r.reranker, "score_pairs",
                        lambda q, texts: [0.1, 0.9, 0.5])
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
def test_rerank_khong_lat_duoc_cap_doi_xung(clean_tables, monkeypatch):
    """Hai ứng viên đảo chỗ cho nhau → RRF thắng, cross-encoder KHÔNG lật được.

    Đây là hệ quả CÓ CHỦ Ý của việc hoà hai thứ hạng (2026-08-20), không phải
    lỗi: một chunk phải tệ ở CẢ HAI thứ hạng mới rơi, nên một lá phiếu lệch
    không đủ sức đẩy đáp án đúng ra ngoài. Cái giá là ở tình huống đối xứng
    tuyệt đối này lá phiếu bị vô hiệu hoàn toàn.

    Test này tồn tại để tính chất đó được TUYÊN BỐ. Không có nó, ai đó sau này
    gặp hiện tượng "mock cho B điểm cao mà B không lên đầu" sẽ tưởng reranker
    hỏng và đi sửa nhầm chỗ — đúng cách reranker đã chết im lặng 6 tuần.

    Điểm vẫn được gắn đầy đủ: reranker CÓ chạy, chỉ là không thắng."""
    from src.rag import retrieve as r
    _seed(clean_tables, [
        ("A", "Khách hàng hoàn hàng trong 30 ngày", [1.0] + [0.0] * 1023),
        ("B", "Quy trình bảo trì máy CNC", [1.0, 1.0] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)
    monkeypatch.setattr(r.reranker, "score_pairs", lambda q, texts: [0.1, 0.9])
    res = r.retrieve("hoàn hàng chính sách", k=5, conn=clean_tables)

    assert res.method == "hybrid-rrf+rerank"          # reranker CÓ chạy
    assert [c.doc_id for c in res.chunks] == ["A", "B"]  # RRF vẫn thắng
    assert [c.rerank_score for c in res.chunks] == [0.1, 0.9]  # điểm vẫn gắn


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
    # BẤT BIẾN THẬT của fix này: chunk hạng-7 theo RRF LỌT ĐƯỢC vào kết quả
    # cuối. Nó vẫn đúng sau khi đổi sang hoà thứ hạng (2026-08-20).
    assert "D6" in ids
    # Nó KHÔNG còn lên hạng 1. Trước đây cross-encoder ghi đè nên một mình nó
    # quyết; nay là lá phiếu hoà với RRF, mà D6 đứng hạng 7 ở chân RRF. Đây là
    # đánh đổi CÓ CHỦ Ý, không phải hồi quy: đo trên 64 ca thật thì cách ghi đè
    # làm hai câu hỏi `hard` mất hẳn đáp án khỏi top-6.
    assert ids == ["D0", "D1", "D2", "D6", "D3", "D4"]
    assert "D5" not in ids and "D7" not in ids
    assert next(c for c in res.chunks if c.doc_id == "D6").rerank_score         == pytest.approx(10.0)


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
    # BA tài liệu: cross-encoder nay là lá phiếu hoà với RRF, nên với đúng hai
    # ứng viên đảo chỗ cho nhau hai lá phiếu triệt tiêu và RRF thắng tie-break.
    # Muốn kéo được RIGHT lên đầu, lá phiếu phải vừa NÂNG RIGHT vừa DÌM WRONG —
    # đúng thứ một cross-encoder có ích phải làm được.
    _seed(clean_tables, [
        ("RIGHT", "quy dinh ve thoi gian giao hang khan cap", [1.0, 1.0] + [0.0] * 1022),
        ("WRONG", "chuong muc luat lao dong chung chung", [1.0, 0.9] + [0.0] * 1022),
        ("FILLER", "bieu mau de nghi thanh toan noi bo", [1.0, 2.0] + [0.0] * 1022),
    ])
    monkeypatch.setattr(r, "embed_query", lambda q: [1.0] + [0.0] * 1023)

    def fake_score(q, texts):
        # Only recognizes RIGHT's content when the rerank query carries the
        # "khan cap" marker — absent from bare "SLA" alone, present only via
        # the concatenated aux query. WRONG bị chấm thấp nhất dù ở hạng 1 theo
        # RRF; FILLER ở giữa.
        out = []
        for t in texts:
            if "chuong muc luat lao dong" in t:
                out.append(0.0)
            elif "quy dinh ve thoi gian" in t:
                out.append(1.0 if "khan cap" in q else 0.2)
            else:
                out.append(0.5)
        return out

    monkeypatch.setattr(r.reranker, "score_pairs", fake_score)

    without_aux = r.retrieve("SLA", k=2, conn=clean_tables)
    assert without_aux.chunks[0].doc_id != "RIGHT"  # bare query alone can't recover it

    with_aux = r.retrieve("SLA", k=2, conn=clean_tables,
                          aux_queries=("SLA giao hang khan cap",))
    assert with_aux.chunks[0].doc_id == "RIGHT"  # concatenation recovers it
