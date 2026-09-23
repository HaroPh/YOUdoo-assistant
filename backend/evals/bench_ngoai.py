# backend/evals/bench_ngoai.py
"""Benchmark retriever + reranker trên dataset NGOÀI có qrels thật.

Vì sao: bộ `retrieval` tự viết chỉ có 62 ca `hard`, p của phép so 4B/0.6B/bge
nằm sát ngưỡng 0,01 (trang-thai-chung #31). Hai bộ dưới đây có corpus +
queries + qrels, gốc tiếng Việt, license cho phép tạo tập con:

- `zalo`: GreenNode/zalo-ai-legal-text-retrieval-vn (MIT; gốc Zalo AI Challenge
  2021 Legal Text Retrieval) — 61.425 Điều luật, 788 câu test có qrels.
- `tvpl`: GreenNode/TVPL-Retrieval-VN (CC-BY-SA-4.0) — 10.576 đoạn, 9.985 câu;
  lấy mẫu `TVPL_SAMPLE` câu với seed cố định.

Dữ liệu tải về `evals/external-data/` (gitignore). Tải lại:
    huggingface_hub.snapshot_download(repo_id=..., repo_type="dataset",
                                      local_dir="evals/external-data/<tên>")
TVPL chỉ có parquet — đổi sang jsonl cạnh tệp gốc (cùng tên, đuôi .jsonl).

ĐO ĐÚNG HỆ THỐNG THẬT, KHÔNG ĐO MỘT BẢN SAO:
- Nạp: mỗi passage cắt bằng CHÍNH `_split_section_text` (400 token, overlap
  60), `title` → `section_path`, rồi embed/ts_vector/fold qua đúng các biến đổi
  của `ingest._ingest_known` (index_text, segment_vi, fold_vi). 43% passage
  Zalo dài hơn 512 token — nạp nguyên passage sẽ đo một hệ không tồn tại.
  `doc_id = corpus-id` nên qrels map thẳng: một câu trúng khi BẤT KỲ chunk nào
  của passage đúng lọt top-k. Schema riêng (`bench_<tên>`), không đụng public.
- Pool: `retrieve()` thật, k=TOP_N, rerank TẮT (`RAG_RERANK_ENABLED=0`, đọc mỗi
  lần gọi) → 20 ứng viên theo thứ tự RRF, dựng MỘT lần, lưu cache.
- Chân đo: `retrieve.rerank()` thật trên đúng pool đó. Mọi chân chung một
  pool nên chênh lệch chỉ đến từ reranker/chế độ — không lẫn nhiễu truy xuất.
  Mỗi chân một tiến trình (reranker cache model một lần).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import random
import statistics
import sys
import time

BASE = os.path.join(os.path.dirname(__file__), "external-data")
CACHE = os.path.join(BASE, "bench-cache")
TVPL_SAMPLE = 1000
SEED = 20260923
K_FINAL = 6
K_NDCG = 10

DATASETS = {
    "zalo": {
        "dir": "zalo-ai-legal-text-retrieval-vn",
        "corpus": "corpus.jsonl", "queries": "queries.jsonl",
        "qrels": "qrels/test.jsonl", "id": "_id", "sample": None,
    },
    "tvpl": {
        "dir": "TVPL-Retrieval-VN",
        "corpus": "corpus/test-00000-of-00001.jsonl",
        "queries": "queries/test-00000-of-00001.jsonl",
        "qrels": "qrels/test-00000-of-00001.jsonl", "id": "id",
        "sample": TVPL_SAMPLE,
    },
}


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _path(ds, key):
    cfg = DATASETS[ds]
    return os.path.join(BASE, cfg["dir"], cfg[key])


def schema_of(ds: str) -> str:
    return f"bench_{ds}"


def load_queries(ds: str) -> list[tuple[str, str, frozenset]]:
    """[(qid, text, relevant corpus-ids)] — chỉ câu có qrels; mẫu tất định."""
    cfg = DATASETS[ds]
    rel: dict[str, set] = {}
    for r in _jsonl(_path(ds, "qrels")):
        if float(r["score"]) > 0:
            rel.setdefault(r["query-id"], set()).add(r["corpus-id"])
    texts = {q[cfg["id"]]: q["text"] for q in _jsonl(_path(ds, "queries"))}
    qids = sorted(q for q in rel if q in texts)
    if cfg["sample"] and len(qids) > cfg["sample"]:
        qids = sorted(random.Random(SEED).sample(qids, cfg["sample"]))
    return [(q, texts[q], frozenset(rel[q])) for q in qids]


def score_case(doc_ids: list[str], rel: frozenset,
               k_final: int = K_FINAL, k_ndcg: int = K_NDCG) -> dict:
    """Điểm một câu trên danh sách doc_id của chunk theo thứ hạng (1 chunk = 1
    vị trí). Một passage trúng ở vị trí chunk ĐẦU TIÊN của nó; chunk trùng passage
    sau đó không cộng thêm (nDCG) — cùng tinh thần `retrieval_score`."""
    hit_ranks = [i + 1 for i, d in enumerate(doc_ids) if d in rel]
    seen, gains = set(), 0.0
    for i, d in enumerate(doc_ids[:k_ndcg]):
        if d in rel and d not in seen:
            gains += 1.0 / math.log2(i + 2)
        seen.add(d)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), k_ndcg)))
    return {
        "recall_at_pool": len(rel & set(doc_ids)) / len(rel),
        "recall_at_final": len(rel & set(doc_ids[:k_final])) / len(rel),
        "reciprocal_rank": 1.0 / hit_ranks[0] if hit_ranks else 0.0,
        "ndcg_at_10": gains / ideal if ideal else 0.0,
        "hit_ranks": hit_ranks,
    }


# ─── nạp ────────────────────────────────────────────────────────────────────

def ingest(ds: str, batch_docs: int = 32, embed_batch: int = 64) -> None:
    from src.rag import db as _db
    from src.rag.chunking import _split_section_text, count_tokens, fold_vi, index_text
    from src.rag.embed import embed_texts, get_embedder
    from src.rag.ingest import segment_vi
    import numpy as np

    schema = schema_of(ds)
    conn = _db.connect(schema)
    _db.ensure_schema(conn, schema)
    emb = get_embedder()
    conn.execute("INSERT INTO rag_embedding_marker (embedding_model, dim) "
                 "SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM rag_embedding_marker)",
                 (emb.model_name, emb.dim))
    done = {r[0] for r in conn.execute("SELECT doc_id FROM rag_documents")}
    idk = DATASETS[ds]["id"]
    todo = [c for c in _jsonl(_path(ds, "corpus")) if c[idk] not in done]
    print(f"[{ds}] schema {schema}: đã có {len(done)}, còn {len(todo)} passage",
          flush=True)
    t0, n_chunks = time.time(), 0
    for g in range(0, len(todo), batch_docs):
        group = todo[g:g + batch_docs]
        rows = []
        for c in group:
            title = (c.get("title") or "").strip() or None
            for j, body in enumerate(_split_section_text(c["text"])):
                rows.append((c[idk], title, body, j))
        idx = [index_text(t, b) for _, t, b, _ in rows]
        vecs = []
        for i in range(0, len(idx), embed_batch):
            vecs.extend(embed_texts(idx[i:i + embed_batch]))
        # executemany + vector numpy nhị phân: INSERT từng dòng đo được 46 ms/dòng
        # (21,5 chunk/s, round-trip) — executemany 312 chunk/s. Cùng cột, cùng
        # biến đổi với ingest._ingest_known; chỉ khác cách gửi.
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany("INSERT INTO rag_documents (doc_id, source_file, content_hash) "
                            "VALUES (%s, %s, %s)",
                            [(c[idk], f"{ds}/{c[idk]}", "bench") for c in group])
            cur.executemany(
                "INSERT INTO rag_chunks (doc_id, source_file, doc_title, section_path, "
                "chunk_index, token_count, chunk_text, source_kind, embedding, "
                "visibility, ts_vector, chunk_text_fold) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,'text',%s,'all',to_tsvector('simple', %s),%s)",
                [(cid, f"{ds}/{cid}", title or cid, title, j, count_tokens(body), body,
                  np.asarray(vec, dtype=np.float32), segment_vi(it), fold_vi(it))
                 for (cid, title, body, j), vec, it in zip(rows, vecs, idx)])
        n_chunks += len(rows)
        done_n = g + len(group)
        if (g // batch_docs) % 20 == 0 or done_n == len(todo):
            el = time.time() - t0
            print(f"[{ds}] {done_n}/{len(todo)} passage, {n_chunks} chunk, "
                  f"{done_n / el:.1f} passage/s, ETA {(len(todo) - done_n) / max(done_n / el, 1e-9) / 60:.1f} phút",
                  flush=True)
    conn.close()


# ─── pool ───────────────────────────────────────────────────────────────────

def pools_path(ds: str) -> str:
    return os.path.join(CACHE, f"{ds}-pools.json")


def build_pools(ds: str) -> None:
    os.environ["RAG_RERANK_ENABLED"] = "0"
    from src.rag import db as _db
    from src.rag.config import TOP_N
    from src.rag.retrieve import retrieve
    from src.rag.visibility import UNRESTRICTED

    conn = _db.connect(schema_of(ds))
    qs = load_queries(ds)
    out, t0 = [], time.time()
    for i, (qid, text, rel) in enumerate(qs):
        res = retrieve(text, k=TOP_N, conn=conn, visibility=UNRESTRICTED)
        assert not res.method.endswith("rerank"), res.method
        out.append({"qid": qid, "query": text, "rel": sorted(rel), "method": res.method,
                    "chunks": [dataclasses.asdict(c) for c in res.chunks]})
        if i % 100 == 0:
            print(f"[{ds}] pool {i}/{len(qs)} ({time.time() - t0:.0f}s)", flush=True)
    conn.close()
    os.makedirs(CACHE, exist_ok=True)
    with open(pools_path(ds), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[{ds}] {len(out)} pool → {pools_path(ds)}", flush=True)


# ─── chân đo ────────────────────────────────────────────────────────────────

def run_leg(ds: str, leg: str) -> dict:
    """leg = 'no-rerank' hoặc bất kỳ nhãn nào; model/chế độ lấy từ env
    RERANK_MODEL / RAG_RERANK_MODE do người gọi đặt TRƯỚC khi chạy tiến trình."""
    from src.rag import retrieve as R
    from src.rag.types import Chunk

    with open(pools_path(ds), encoding="utf-8") as f:
        pools = json.load(f)
    per_case, errors, lat = [], 0, []
    for p in pools:
        chunks = [Chunk(**c) for c in p["chunks"]]
        if leg == "no-rerank":
            order, ok = chunks, True
        else:
            t = time.perf_counter()
            order, ok = R.rerank(p["query"], chunks)
            lat.append((time.perf_counter() - t) * 1000)
            if not ok:
                errors += 1
        row = score_case([c.doc_id for c in order], frozenset(p["rel"]))
        row.update(question=p["qid"], text=p["query"], difficulty=ds,
                   method=p["method"] + ("+rerank" if leg != "no-rerank" and ok else ""))
        per_case.append(row)
    n = len(per_case)
    mean = lambda k: sum(r[k] for r in per_case) / n
    return {
        "set": ds, "leg": leg, "n": n, "errors": errors,
        "rerank_model": os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        if leg != "no-rerank" else None,
        "rerank_mode": os.environ.get("RAG_RERANK_MODE", "blend") if leg != "no-rerank" else None,
        "recall_at_pool": mean("recall_at_pool"), "recall_at_6": mean("recall_at_final"),
        "mrr": mean("reciprocal_rank"), "ndcg_at_10": mean("ndcg_at_10"),
        "p50_rerank_ms": statistics.median(lat) if lat else 0.0,
        "per_case": per_case,
    }


# ─── pha B: vai ─────────────────────────────────────────────────────────────
# Vai trong Youdoo chạm RAG ở ĐÚNG một chỗ: cột `visibility` của chunk (lọc SQL)
# + lượt bóng `hidden_classes`. Nhãn là thuộc tính TÀI LIỆU (DOC_VISIBILITY theo
# tệp), nên gán cho PASSAGE; câu hỏi mang lớp của passage đáp án. Hệ thống chỉ có
# 2 lớp (all/commercial) → 2 nhóm hành vi thật: {admin, accounting, sales} và
# {warehouse}. Nhãn là GIẢ LẬP bằng từ khoá (evals/vlegal_bench_roles.py) —
# đo CƠ CHẾ, mật độ commercial ~25% so với production <1% nên tỉ lệ báo oan ở
# đây cao hơn thực tế nhiều.
ROLES_B = ("admin", "accounting", "warehouse")  # sales cùng rag_visibility với accounting


def passage_class(title: str | None, text: str) -> str:
    from evals.vlegal_bench_roles import ROLE_KEYWORDS
    t = f"{title or ''} {text}".lower()
    hit = {r for r, kws in ROLE_KEYWORDS.items() if any(k in t for k in kws)}
    return "commercial" if hit & {"accounting", "sales"} else "all"


def passage_labels(ds: str) -> dict[str, str]:
    idk = DATASETS[ds]["id"]
    return {c[idk]: passage_class(c.get("title"), c["text"])
            for c in _jsonl(_path(ds, "corpus"))}


def apply_labels(ds: str) -> None:
    from src.rag import db as _db
    lab = passage_labels(ds)
    com = sorted(d for d, v in lab.items() if v == "commercial")
    conn = _db.connect(schema_of(ds))
    with conn.transaction():
        conn.execute("UPDATE rag_chunks SET visibility = 'all'")
        conn.execute("UPDATE rag_chunks SET visibility = 'commercial' WHERE doc_id = ANY(%s)",
                     (com,))
    got = conn.execute("SELECT visibility, count(*) FROM rag_chunks GROUP BY 1").fetchall()
    conn.close()
    print(f"[{ds}] passage commercial {len(com)}/{len(lab)} → chunk {dict(got)}", flush=True)


def run_role(ds: str, role: str) -> dict:
    """retrieve() ĐẦU-CUỐI (cấu hình reranker lấy từ env, như production) với
    đúng rag_visibility của vai trong src/agents/roles.py — không tự viết tay."""
    from src.agents.roles import load_profile
    from src.rag import db as _db
    from src.rag.config import TOP_N
    from src.rag.retrieve import retrieve

    vis = load_profile("small-business")[role].rag_visibility
    lab = passage_labels(ds)
    conn = _db.connect(schema_of(ds))
    per_case = []
    for qid, text, rel in load_queries(ds):
        res = retrieve(text, k=TOP_N, conn=conn, visibility=vis)
        docs = [c.doc_id for c in res.chunks]
        gold = "commercial" if any(lab[d] == "commercial" for d in rel) else "all"
        row = score_case(docs, rel)
        row.update(question=qid, text=text, difficulty=gold, method=res.method,
                   hidden=sorted(res.hidden_classes),
                   leak=sum(lab[d] == "commercial" for d in docs[:K_FINAL])
                   if role == "warehouse" else 0)
        per_case.append(row)
    conn.close()
    return {"set": ds, "role": role, "n": len(per_case),
            "rerank_model": os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            "rerank_mode": os.environ.get("RAG_RERANK_MODE", "blend"),
            "per_case": per_case}


def role_summary(res: dict) -> dict:
    out = {}
    for gold in ("all", "commercial"):
        rows = [r for r in res["per_case"] if r["difficulty"] == gold]
        if not rows:
            continue
        n = len(rows)
        out[gold] = {
            "n": n,
            "recall_at_6": sum(r["recall_at_final"] for r in rows) / n,
            "mrr": sum(r["reciprocal_rank"] for r in rows) / n,
            "hidden_rate": sum(bool(r["hidden"]) for r in rows) / n,
            "leak_cases": sum(r["leak"] > 0 for r in rows),
        }
    return out


def second_half_gate(leg: dict, base: dict) -> tuple[float, float, bool]:
    """Cổng R12: nửa SAU theo thứ tự chạy, recall@6 của chân có reranker không
    được dưới chân tắt rerank — bắt suy giảm giữa lượt mà cổng tổng không thấy."""
    h = len(leg["per_case"]) // 2
    a = statistics.fmean(r["recall_at_final"] for r in leg["per_case"][h:])
    b = statistics.fmean(r["recall_at_final"] for r in base["per_case"][h:])
    return a, b, a >= b


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Benchmark retriever/reranker trên dataset ngoài.")
    ap.add_argument("cmd", choices=["ingest", "pools", "leg", "label", "role"])
    ap.add_argument("ds", choices=sorted(DATASETS))
    ap.add_argument("--leg", default="no-rerank")
    ap.add_argument("--role", choices=ROLES_B)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "ingest":
        ingest(a.ds)
    elif a.cmd == "pools":
        build_pools(a.ds)
    elif a.cmd == "label":
        apply_labels(a.ds)
    elif a.cmd == "role":
        res = run_role(a.ds, a.role)
        print(f"[{a.ds}/{a.role}] {json.dumps(role_summary(res))}", file=sys.stderr)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    else:
        res = run_leg(a.ds, a.leg)
        print(f"[{a.ds}/{a.leg}] n={res['n']} errors={res['errors']} "
              f"r@20={res['recall_at_pool']:.4f} r@6={res['recall_at_6']:.4f} "
              f"mrr={res['mrr']:.4f} ndcg@10={res['ndcg_at_10']:.4f} "
              f"p50={res['p50_rerank_ms']:.0f}ms", file=sys.stderr)
        text = json.dumps(res, ensure_ascii=False, indent=1)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            print(text)


if __name__ == "__main__":
    main()
