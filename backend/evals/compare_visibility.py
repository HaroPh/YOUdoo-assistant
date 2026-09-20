# backend/evals/compare_visibility.py
"""Cổng ÂM của 19b — so hai lượt `--set retrieval`: admin (không lọc) và một
vai bị chặn (spec 2026-09-20 §7).

Bất biến:
  (a) ca THUẦN thương mại (mọi nhãn mong đợi thuộc DOC_VISIBILITY) →
      recall_at_pool của vai bị chặn == 0. Không phải "thấp": bằng 0.
  (b) ca khác → recall_at_pool bị chặn >= admin. Gỡ ứng viên không-đáp-án
      khỏi pool 20 không đẩy được đáp án ra, chỉ kéo được vào.
recall_at_final CHỈ báo cáo: pool khác → reranker thấy tập khác.

Chạy: python -m evals.compare_visibility admin.json warehouse.json → exit 0/1.
"""
import json
import sys

from evals.retrieval_cases import RETRIEVAL_CASES
from src.rag.visibility import DOC_VISIBILITY, basename


def _is_commercial_case(expected) -> bool | None:
    """True/False, hoặc None nếu LẪN (có cả hai loại tệp)."""
    kinds = {basename(doc) in DOC_VISIBILITY for doc, _section in expected}
    return None if len(kinds) == 2 else kinds.pop()


def compare(admin: dict, restricted: dict, cases=RETRIEVAL_CASES) -> dict:
    by_q_admin = {r["question"]: r for r in admin["per_case"]}
    by_q_res = {r["question"]: r for r in restricted["per_case"]}
    leaked, regressed = [], []
    n_commercial = n_other = 0
    for question, expected, _difficulty in cases:
        if question not in by_q_admin or question not in by_q_res:
            raise ValueError(f"thiếu ca ở một bên: {question!r}")
        kind = _is_commercial_case(expected)
        if kind is None:
            raise ValueError(f"ca lẫn (nhãn từ cả tệp thương mại lẫn tệp khác), "
                             f"không xếp được: {question!r}")
        a, r = by_q_admin[question], by_q_res[question]
        if kind:
            n_commercial += 1
            if r["recall_at_pool"] != 0:
                leaked.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
        else:
            n_other += 1
            if r["recall_at_pool"] < a["recall_at_pool"]:
                regressed.append({"question": question,
                                  "admin": a["recall_at_pool"],
                                  "restricted": r["recall_at_pool"]})
    return {"ok": not leaked and not regressed,
            "n_commercial": n_commercial, "n_other": n_other,
            "commercial_leaked": leaked, "regressed": regressed}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("dùng: python -m evals.compare_visibility <admin.json> <restricted.json>")
        return 2
    admin = json.load(open(argv[0], encoding="utf-8"))
    restricted = json.load(open(argv[1], encoding="utf-8"))
    result = compare(admin, restricted)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"CỔNG ÂM {'PASS' if result['ok'] else 'FAIL'} — thương mại {result['n_commercial']} ca "
          f"(lộ {len(result['commercial_leaked'])}), khác {result['n_other']} ca "
          f"(kém đi {len(result['regressed'])})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
