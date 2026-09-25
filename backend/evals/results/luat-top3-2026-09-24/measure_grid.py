"""Lưới 2 chiều cho luật "báo bị chặn": {luật cũ, luật mới} × k ∈ 1…6.

VÌ SAO. Luật hiện tại hỏi "có BẤT KỲ thứ BỊ GIẤU nào trong top-k lượt bóng
không?" → có thì từ chối. Bench ngoài 2026-09-23 đo được nó từ chối oan
40,6%/43,4% câu mà vai `kho` ĐÃ tìm đúng đáp án (235 và 196 ca trong số đó đáp
án ở HẠNG 1). Luật không bao giờ hỏi "phần thấy được đã đủ trả lời chưa".

Luật đề xuất đảo câu hỏi: "có BẤT KỲ thứ THẤY ĐƯỢC nào trong top-k lượt bóng
không?" → KHÔNG có thì mới từ chối. Lọc chỉ bỏ bớt hàng nên hạng của một chunk
thấy được trong lượt bóng luôn ≥ hạng của nó trong lượt lọc; nếu kết quả tốt
nhất của vai cũng nằm trong top-k toàn cục thì không có gì hơn hẳn bị giữ lại.

CHIỀU Ý NGHĨA CỦA k ĐẢO NGƯỢC giữa hai luật:
  - luật cũ: k lớn → bắt nhiều hơn VÀ oan nhiều hơn
  - luật mới: k lớn → ÍT từ chối hơn (nhiều cơ hội thấy một chunk thấy được)
nên con số k=3 chốt cho luật cũ KHÔNG mang sang được.

CÁCH ĐO. Mỗi câu dựng bảng xếp hạng bóng ĐÚNG MỘT LẦN (cùng `_fuse_legs` +
`prepared[:1]` mà production dùng), rồi chấm cả 12 ô từ chính bảng đó — không
chạy 12 lượt, nên không có chỗ cho hai lượt lệch nhau.

Chạy:
  export DATABASE_URL=...  OLLAMA_URL=http://127.0.0.1:11435
  python -m evals.results.luat-top3-2026-09-24.measure_grid tvpl warehouse
  python evals/results/luat-top3-2026-09-24/measure_grid.py tvpl warehouse
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", ".."))

K_MAX = 6
K_FINAL = 6


def _rank_bong(conn, text, prepared_fn, fuse_fn, unrestricted):
    """Bảng xếp hạng lượt BÓNG (không lọc), thứ tự RRF — đúng thứ production
    tính trong `retrieve()`."""
    prepared = prepared_fn(text, ())
    fused, _fold = fuse_fn(conn, prepared[:1], unrestricted)
    return sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)


def _quyet_dinh(rank, vis_idx, thay_duoc, k):
    """Trả (luật CŨ có từ chối, luật MỚI có từ chối) ở ngưỡng k."""
    topk = [e["row"][vis_idx] for e in rank[:k]]
    co_bi_giau = any(v not in thay_duoc for v in topk)
    co_thay_duoc = any(v in thay_duoc for v in topk)
    return co_bi_giau, (not co_thay_duoc)


def main(ds: str, role: str) -> dict:
    from evals import bench_ngoai as B
    from src.agents.roles import load_profile
    from src.rag import db as _db
    from src.rag.config import TOP_N
    from src.rag.retrieve import (VIS_IDX, _fuse_legs, _prepare_queries,
                                  retrieve)
    from src.rag.visibility import UNRESTRICTED

    thay_duoc = load_profile("small-business")[role].rag_visibility
    assert thay_duoc is not UNRESTRICTED, f"vai {role} không bị chặn gì — đo vô nghĩa"
    lab = B.passage_labels(ds)
    conn = _db.connect(B.schema_of(ds))

    rows = []
    for i, (qid, text, rel) in enumerate(B.load_queries(ds), 1):
        res = retrieve(text, k=TOP_N, conn=conn, visibility=thay_duoc)
        docs = [c.doc_id for c in res.chunks]
        sc = B.score_case(docs, rel)
        gold = "commercial" if any(lab[d] == "commercial" for d in rel) else "all"
        rank = _rank_bong(conn, text, _prepare_queries, _fuse_legs, UNRESTRICTED)
        qd = {k: _quyet_dinh(rank, VIS_IDX, thay_duoc, k) for k in range(1, K_MAX + 1)}
        rows.append({"qid": qid, "gold": gold,
                     "tim_dung": sc["recall_at_final"] > 0,
                     "ro_ri": sum(lab[d] == "commercial" for d in docs[:K_FINAL]),
                     "quyet_dinh": {str(k): list(v) for k, v in qd.items()}})
        if i % 100 == 0:
            print(f"[{ds}/{role}] {i} câu", file=sys.stderr, flush=True)
    conn.close()
    return {"set": ds, "role": role, "n": len(rows), "per_case": rows}


def bang(res: dict) -> None:
    rows = res["per_case"]
    tm = [r for r in rows if r["gold"] == "commercial"]
    al = [r for r in rows if r["gold"] == "all"]
    print(f"\n=== {res['set']} / {res['role']} — "
          f"thương mại {len(tm)} câu, khác {len(al)} câu ===")
    print(f"{'k':>2}  {'luật':<5} {'bắt đúng (TM)':>16} {'từ chối oan (khác)':>21}"
          f" {'rò rỉ':>7}")
    ro = sum(r["ro_ri"] > 0 for r in rows)
    for idx, ten in ((0, "cũ"), (1, "mới")):
        for k in range(1, K_MAX + 1):
            bat = sum(r["quyet_dinh"][str(k)][idx] for r in tm)
            oan = sum(r["quyet_dinh"][str(k)][idx] and r["tim_dung"] for r in al)
            print(f"{k:>2}  {ten:<5} {bat:>6}/{len(tm):<4} ({bat/len(tm):5.1%})"
                  f" {oan:>7}/{len(al):<4} ({oan/len(al):5.1%}) {ro:>7}")
        print()


if __name__ == "__main__":
    ds, role = sys.argv[1], sys.argv[2]
    out = main(ds, role)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, f"grid-{ds}-{role}.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    bang(out)
