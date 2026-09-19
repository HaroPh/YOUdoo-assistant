# backend/tests/evals/test_retrieval_stats.py
"""Kiểm định ghép cặp — spec 2026-09-18 §1/§8. Thuần, dữ liệu giả có đáp án."""
import itertools
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
    diffs = [1.0] * 35                       # > MAX_EXACT_DEFAULT=30 → Monte Carlo
    p = rs.permutation_p(diffs, n_mc=2000, seed=1)
    assert 0.0 <= p < 0.01                  # gần 2/2^35, không thể bằng 1


def test_exact_dp_khop_dinh_nghia_liet_ke_thang_o_n_16():
    # DP theo tổng dấu phải khớp định nghĩa gốc (liệt kê hết tổ hợp dấu) —
    # kiểm bằng liệt kê thẳng làm ngay trong test, độc lập với cách cài đặt.
    diffs = [0.1, -0.2, 0.3, -0.4, 0.15, -0.25, 0.35, -0.45,
             0.05, -0.05, 0.22, -0.18, 0.33, -0.11, 0.27, -0.29]
    assert len(diffs) == 16
    got = rs.permutation_p(diffs, max_exact=16)
    n = len(diffs)
    obs = abs(sum(diffs) / n)
    hits = total = 0
    for signs in itertools.product((1, -1), repeat=n):
        m = abs(sum(s * d for s, d in zip(signs, diffs)) / n)
        total += 1
        if m >= obs - 1e-12:
            hits += 1
    assert abs(got - hits / total) < 1e-9


def test_permutation_p_o_moc_max_exact_moi_van_doc_lap_voi_seed():
    # 30 chênh ≠ 0 == MAX_EXACT_DEFAULT hiện tại: vẫn phải là nhánh chính
    # xác (không phụ thuộc seed) — đây là mốc vừa nâng từ 22 lên 30.
    diffs = [1.0] * 15 + [-1.0] * 14 + [0.5]
    assert len(diffs) == 30
    p1 = rs.permutation_p(diffs, seed=0)
    p2 = rs.permutation_p(diffs, seed=12345)
    assert p1 == p2


def test_exact_two_sided_p_roi_ve_none_khi_vuot_tran_trang_thai():
    # An toàn khỏi chênh không trùng giá trị (vd float ngẫu nhiên liên tục):
    # DP phải BỎ GIỮA CHỪNG (trả None) thay vì phình bộ nhớ không giới hạn.
    diffs = [0.11, 0.23, 0.37, 0.41]
    obs = abs(sum(diffs) / len(diffs))
    assert rs._exact_two_sided_p(diffs, len(diffs), obs, state_cap=2) is None


def test_exact_two_sided_p_tinh_dung_khi_khong_vuot_tran():
    diffs = [1.0, 1.0]
    obs = abs(sum(diffs) / len(diffs))
    got = rs._exact_two_sided_p(diffs, len(diffs), obs, state_cap=10)
    assert abs(got - 0.5) < 1e-12  # 2/4 tổ hợp dấu đạt |mean| >= 1


def test_permutation_p_and_method_gan_nhan_dung_nhanh():
    p, m = rs._permutation_p_and_method([1.0] * 10)
    assert m == "(exact)"
    p2, m2 = rs._permutation_p_and_method([1.0] * 35, n_mc=100)
    assert m2 == "(MC n=100)"


def test_compare_mang_theo_p_method():
    base = _rows({"a": 1.0, "b": 0.5, "c": 0.0})
    other = _rows({"a": 1.0, "b": 1.0, "c": 0.5})
    got = rs.compare(base, other, ["a", "b", "c"])
    assert got["p_method"] == "(exact)"


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
