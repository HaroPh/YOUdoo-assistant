# backend/evals/retrieval_stats.py
"""Kiểm định ghép cặp giữa hai chân đo `retrieval` — spec 2026-09-18 §1, §8.

Vì sao có module này: ngày 2026-09-18 phép kiểm đầu tiên chạy bằng lệnh gõ
tay trong shell và phát hiện chỉ 1/12 phép so có CI không cắt 0. Một phép
kiểm quyết định có đổi reranker production hay không thì phải là mã có test,
tái lập bằng seed, không phải một đoạn shell ai nhớ ai quên.

Thuần Python: không numpy, không DB, không model. Sign-flip permutation hai
phía (chính xác tới `max_exact` chênh ≠ 0, Monte Carlo khi nhiều hơn) và
bootstrap percentile.
"""
import argparse
import itertools
import json
import random


def load_per_case(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {row["question"]: row for row in data["per_case"]}


def select(rows: dict, difficulty: str | None = None, questions=None) -> list[str]:
    """Danh sách câu, thứ tự ổn định (thứ tự trong `rows`, hoặc trong `questions`)."""
    if questions is not None:
        return [q for q in questions if q in rows]
    return [q for q, r in rows.items()
            if difficulty is None or r["difficulty"] == difficulty]


def paired_diffs(base: dict, other: dict, questions: list[str],
                 key: str = "reciprocal_rank") -> list[float]:
    return [float(other[q][key]) - float(base[q][key]) for q in questions]


def permutation_p(diffs: list[float], max_exact: int = 22,
                  n_mc: int = 20000, seed: int = 0) -> float:
    """p hai phía cho H0 "chênh có dấu ngẫu nhiên". Chênh = 0 không đổi dấu
    được nên không tham gia đếm, nhưng vẫn nằm trong mẫu số của mean."""
    n = len(diffs)
    if n == 0:
        return 1.0
    nz = [d for d in diffs if abs(d) > 1e-12]
    if not nz:
        return 1.0
    obs = abs(sum(diffs) / n)
    if len(nz) <= max_exact:
        hits = total = 0
        for signs in itertools.product((1, -1), repeat=len(nz)):
            m = abs(sum(s * d for s, d in zip(signs, nz)) / n)
            total += 1
            if m >= obs - 1e-12:
                hits += 1
        return hits / total
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_mc):
        m = abs(sum(d if rng.random() < 0.5 else -d for d in nz) / n)
        if m >= obs - 1e-12:
            hits += 1
    return hits / n_mc


def bootstrap_ci(diffs: list[float], n: int = 20000, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=k)) / k for _ in range(n))
    return means[int(alpha / 2 * n)], means[min(n - 1, int((1 - alpha / 2) * n))]


def wins_ties_losses(diffs: list[float]) -> tuple[int, int, int]:
    w = sum(1 for d in diffs if d > 1e-12)
    l = sum(1 for d in diffs if d < -1e-12)
    return w, len(diffs) - w - l, l


def dropouts(base: dict, other: dict, questions: list[str]) -> list[str]:
    """Câu bị `other` làm văng khỏi top-k trong khi `base` còn giữ."""
    return [q for q in questions
            if other[q]["recall_at_final"] == 0 and base[q]["recall_at_final"] > 0]


def compare(base: dict, other: dict, questions: list[str]) -> dict:
    d = paired_diffs(base, other, questions)
    lo, hi = bootstrap_ci(d)
    w, t, l = wins_ties_losses(d)
    return {"n": len(d), "mean_diff": (sum(d) / len(d)) if d else 0.0,
            "ci_lo": lo, "ci_hi": hi, "p": permutation_p(d),
            "wins": w, "ties": t, "losses": l,
            "dropouts": dropouts(base, other, questions)}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="So hai chân đo retrieval theo ghép cặp.")
    ap.add_argument("base"); ap.add_argument("other")
    ap.add_argument("--difficulty", default=None)
    ap.add_argument("--questions-from", default=None,
                    help="JSON có per_case; chỉ so trên các câu của tệp này")
    a = ap.parse_args(argv)
    base, other = load_per_case(a.base), load_per_case(a.other)
    qs = None
    if a.questions_from:
        qs = list(load_per_case(a.questions_from))
    questions = select(base, a.difficulty, qs)
    if a.difficulty and qs:
        questions = [q for q in questions if base[q]["difficulty"] == a.difficulty]
    r = compare(base, other, questions)
    print(f"n={r['n']}  chenh_TB={r['mean_diff']:+.4f}  CI95=[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
          f"  p={r['p']:.4f}  thang/hoa/thua={r['wins']}/{r['ties']}/{r['losses']}")
    for q in r["dropouts"]:
        print(f"  VANG (other mat, base giu): {q}")


if __name__ == "__main__":
    main()
