# backend/evals/retrieval_stats.py
"""Kiểm định ghép cặp giữa hai chân đo `retrieval` — spec 2026-09-18 §1, §8.

Vì sao có module này: ngày 2026-09-18 phép kiểm đầu tiên chạy bằng lệnh gõ
tay trong shell và phát hiện chỉ 1/12 phép so có CI không cắt 0. Một phép
kiểm quyết định có đổi reranker production hay không thì phải là mã có test,
tái lập bằng seed, không phải một đoạn shell ai nhớ ai quên.

Thuần Python: không numpy, không DB, không model. Sign-flip permutation hai
phía (chính xác tới `max_exact` chênh ≠ 0, Monte Carlo khi nhiều hơn) và
bootstrap percentile.

Nhánh "chính xác" liệt kê thẳng qua DP theo tổng dấu (`_exact_two_sided_p`) —
nhanh hơn liệt kê `itertools.product` một hệ số ~n vì không tính lại tổng từ
đầu ở mỗi tổ hợp dấu, và rẻ hơn nữa khi các chênh trùng giá trị (thực tế xảy
ra: `reciprocal_rank` chỉ có tối đa 21 giá trị khả dĩ, 0 và 1/1..1/20, nên
nhiều câu hỏi cho cùng một chênh). NHƯNG độ phức tạp tệ nhất vẫn là O(2^n)
trạng thái y hệt liệt kê thẳng — với chênh không trùng nhau (vd float ngẫu
nhiên liên tục), DP không rẻ hơn mà còn tốn bộ nhớ hơn (đã đo: n=28 ngẫu
nhiên liên tục chiếm >8 GB, không xong sau 300 giây). Vì vậy DP có trần trạng
thái (`_DP_STATE_CAP`); vượt trần thì bỏ giữa chừng, rơi về Monte Carlo — an
toàn cho cả hai phía: dữ liệu đo thật (reciprocal_rank, ít giá trị) tính xong
trong mili-giây tới vài giây ngay cả ở `max_exact` mới; dữ liệu bất kỳ không
làm treo máy.
"""
import argparse
import json
import random

MAX_EXACT_DEFAULT = 30       # trước là 22 — hai lần liền p gần ngưỡng đổi phía
                              # (0.6b-override 24 chênh, bge-override 28 chênh)
_DP_STATE_CAP = 2_000_000    # ~vài trăm MB; vượt trần rơi về Monte Carlo


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


def _exact_two_sided_p(nz: list[float], n: int, obs: float,
                       state_cap: int = _DP_STATE_CAP) -> float | None:
    """DP theo tổng dấu: `dp[tổng] = số cách đạt tổng đó`. KHÔNG làm tròn
    khoá — đã thử làm tròn 9 chữ số thập phân để gom trạng thái rẻ hơn, kiểm
    lại bằng liệt kê thẳng thì SAI (hard-62, 0.6b-override: làm tròn cho
    0,01085, liệt kê thẳng cho 0,01099 — hai bên có `>=obs` khác nhau ở vài
    trạng thái gần biên bị gộp lộn). Cùng một tổ hợp dấu, DP và liệt kê thẳng
    cộng các số hạng theo đúng cùng thứ tự nên cho float giống bit-để-bit;
    không làm tròn thì hai cách luôn khớp nhau, chỉ đổi tốc độ gộp trạng
    thái, không đổi kết quả. Trả `None` nếu số trạng thái vượt `state_cap`
    giữa chừng (gọi nơi dùng rơi về Monte Carlo thay vì tiếp tục)."""
    dp = {0.0: 1}
    for d in nz:
        nd: dict[float, int] = {}
        for s, c in dp.items():
            for sign in (1, -1):
                ns = s + sign * d
                nd[ns] = nd.get(ns, 0) + c
        if len(nd) > state_cap:
            return None
        dp = nd
    total = 1 << len(nz)
    hits = sum(c for s, c in dp.items() if abs(s / n) >= obs - 1e-12)
    return hits / total


def _permutation_p_and_method(diffs: list[float], max_exact: int = MAX_EXACT_DEFAULT,
                              n_mc: int = 20000, seed: int = 0) -> tuple[float, str]:
    n = len(diffs)
    if n == 0:
        return 1.0, "(exact)"
    nz = [d for d in diffs if abs(d) > 1e-12]
    if not nz:
        return 1.0, "(exact)"
    obs = abs(sum(diffs) / n)
    if len(nz) <= max_exact:
        p = _exact_two_sided_p(nz, n, obs)
        if p is not None:
            return p, "(exact)"
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_mc):
        m = abs(sum(d if rng.random() < 0.5 else -d for d in nz) / n)
        if m >= obs - 1e-12:
            hits += 1
    return hits / n_mc, f"(MC n={n_mc})"


def permutation_p(diffs: list[float], max_exact: int = MAX_EXACT_DEFAULT,
                  n_mc: int = 20000, seed: int = 0) -> float:
    """p hai phía cho H0 "chênh có dấu ngẫu nhiên". Chênh = 0 không đổi dấu
    được nên không tham gia đếm, nhưng vẫn nằm trong mẫu số của mean."""
    return _permutation_p_and_method(diffs, max_exact, n_mc, seed)[0]


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
    p, p_method = _permutation_p_and_method(d)
    return {"n": len(d), "mean_diff": (sum(d) / len(d)) if d else 0.0,
            "ci_lo": lo, "ci_hi": hi, "p": p, "p_method": p_method,
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
          f"  p={r['p']:.4f} {r['p_method']}  thang/hoa/thua={r['wins']}/{r['ties']}/{r['losses']}")
    for q in r["dropouts"]:
        print(f"  VANG (other mat, base giu): {q}")


if __name__ == "__main__":
    main()
