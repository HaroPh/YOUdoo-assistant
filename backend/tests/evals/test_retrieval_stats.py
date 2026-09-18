# backend/tests/evals/test_retrieval_stats.py
"""Kiểm định ghép cặp — spec 2026-09-18 §1/§8. Thuần, dữ liệu giả có đáp án."""
import json

import pytest

from evals import retrieval_stats as rs


def _rows(vals, difficulty="hard", final=None):
    """vals: dict question -> reciprocal_rank; final: dict question -> recall_at_final."""
    return {q: {"question": q, "difficulty": difficulty, "reciprocal_rank": v,
                "recall_at_final": (final or {}).get(q, 1.0 if v > 0 else 0.0),
                "hit_ranks": [], "method": "x"} for q, v in vals.items()}


def test_paired_diffs_la_other_tru_base_theo_thu_tu_cau():
    base = _rows({"a": 1.0, "b": 0.5}); other = _rows({"a": 0.5, "b": 1.0})
    assert rs.paired_diffs(base, other, ["a", "b"]) == [-0.5, 0.5]


def test_permutation_moi_chenh_deu_duong_p_bang_2_tren_2_mu_n():
    # n=10 chênh đều +1: chỉ 2/1024 cách gán dấu có |mean| >= 1 (toàn + hoặc toàn −).
    p = rs.permutation_p([1.0] * 10)
    assert abs(p - 2 / 1024) < 1e-12


def test_permutation_khong_co_chenh_p_bang_1():
    assert rs.permutation_p([0.0, 0.0, 0.0]) == 1.0


def test_permutation_bo_qua_chenh_bang_0_khi_dem_hoan_vi():
    # 5 chênh +1 và 5 chênh 0: hoán vị chỉ trên 5 chênh ≠ 0 → 2/32.
    p = rs.permutation_p([1.0] * 5 + [0.0] * 5)
    assert abs(p - 2 / 32) < 1e-12


def test_permutation_monte_carlo_khi_qua_nhieu_chenh():
    diffs = [1.0] * 30                       # > max_exact=22 → Monte Carlo
    p = rs.permutation_p(diffs, n_mc=2000, seed=1)
    assert 0.0 <= p < 0.01                  # gần 2/2^30, không thể bằng 1


def test_bootstrap_du_lieu_hang_thi_ci_bang_hang():
    lo, hi = rs.bootstrap_ci([0.25] * 8)
    assert lo == 0.25 and hi == 0.25


def test_bootstrap_ci_chua_mean_va_tai_lap_theo_seed():
    d = [0.9, -0.3, 0.6, 0.0, 0.4, -0.1, 0.7, 0.2]
    lo1, hi1 = rs.bootstrap_ci(d, seed=7); lo2, hi2 = rs.bootstrap_ci(d, seed=7)
    assert (lo1, hi1) == (lo2, hi2)
    m = sum(d) / len(d)
    assert lo1 <= m <= hi1


def test_wins_ties_losses():
    assert rs.wins_ties_losses([0.5, 0.0, -0.2, 0.1]) == (2, 1, 1)


def test_dropouts_chi_dem_ca_base_giu_ma_other_lam_van():
    base = _rows({"a": 1.0, "b": 0.0, "c": 0.5}, final={"a": 1, "b": 0, "c": 1})
    other = _rows({"a": 0.0, "b": 0.0, "c": 0.5}, final={"a": 0, "b": 0, "c": 1})
    assert rs.dropouts(base, other, ["a", "b", "c"]) == ["a"]


def test_select_loc_theo_difficulty_va_theo_danh_sach_cau():
    rows = {**_rows({"a": 1.0}, "hard"), **_rows({"b": 1.0}, "easy")}
    assert rs.select(rows, difficulty="hard") == ["a"]
    assert rs.select(rows, questions=["b", "zzz"]) == ["b"]


def test_compare_gop_du_truong():
    base = _rows({"a": 1.0, "b": 0.5, "c": 0.0}); other = _rows({"a": 1.0, "b": 1.0, "c": 0.5})
    got = rs.compare(base, other, ["a", "b", "c"])
    assert got["n"] == 3 and abs(got["mean_diff"] - 1 / 3) < 1e-9
    assert set(got) >= {"ci_lo", "ci_hi", "p", "wins", "ties", "losses", "dropouts"}
    assert (got["wins"], got["ties"], got["losses"]) == (2, 1, 0)


def test_load_per_case_doc_json_that(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"per_case": [{"question": "q1", "difficulty": "hard",
                                           "reciprocal_rank": 0.5, "recall_at_final": 1.0,
                                           "hit_ranks": [2], "method": "m"}]}),
                 encoding="utf-8")
    rows = rs.load_per_case(str(p))
    assert rows["q1"]["reciprocal_rank"] == 0.5
