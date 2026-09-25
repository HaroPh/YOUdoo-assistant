# backend/tests/evals/test_bench_ngoai.py
"""Chấm điểm benchmark ngoài — hàm thuần, không DB/model."""
import math

from evals import bench_ngoai as bn


def test_trung_o_chunk_dau_tien_cua_passage_dung():
    got = bn.score_case(["a", "b", "x", "x", "c", "d"], frozenset({"x"}))
    assert got["hit_ranks"] == [3, 4]
    assert got["reciprocal_rank"] == 1 / 3
    assert got["recall_at_final"] == 1.0


def test_ngoai_top6_nhung_trong_pool():
    doc_ids = [f"d{i}" for i in range(6)] + ["x"]
    got = bn.score_case(doc_ids, frozenset({"x"}))
    assert got["recall_at_final"] == 0.0
    assert got["recall_at_pool"] == 1.0
    assert got["reciprocal_rank"] == 1 / 7


def test_truot_han():
    got = bn.score_case(["a", "b"], frozenset({"x"}))
    assert got == {"recall_at_pool": 0.0, "recall_at_final": 0.0,
                   "reciprocal_rank": 0.0, "ndcg_at_10": 0.0, "hit_ranks": []}


def test_nhieu_passage_dung_recall_la_ti_le():
    got = bn.score_case(["x", "a", "b", "c", "d", "e", "y"], frozenset({"x", "y"}))
    assert got["recall_at_final"] == 0.5
    assert got["recall_at_pool"] == 1.0


def test_ndcg_khong_cong_chunk_trung_passage():
    # "x" xuất hiện 2 lần: chỉ lần đầu (hạng 1) được tính — nDCG = 1, không > 1.
    got = bn.score_case(["x", "x", "a"], frozenset({"x"}))
    assert math.isclose(got["ndcg_at_10"], 1.0)


def test_ndcg_hang_2():
    got = bn.score_case(["a", "x"], frozenset({"x"}))
    assert math.isclose(got["ndcg_at_10"], 1 / math.log2(3))


def test_passage_ke_toan_hoac_sales_la_commercial():
    assert bn.passage_class("Điều 5. Thuế suất", "Thuế suất áp dụng...") == "commercial"
    assert bn.passage_class(None, "Hợp đồng thương mại giữa các bên") == "commercial"


def test_passage_kho_hoac_chung_la_all():
    assert bn.passage_class("Điều 2", "Vận chuyển hàng hóa qua kho hàng") == "all"
    assert bn.passage_class("Điều 1", "Phạm vi điều chỉnh của đê điều") == "all"


def test_role_summary_tach_theo_lop_dap_an():
    res = {"per_case": [
        {"difficulty": "all", "recall_at_final": 1.0, "reciprocal_rank": 1.0,
         "hidden": [], "leak": 0},
        {"difficulty": "all", "recall_at_final": 0.0, "reciprocal_rank": 0.0,
         "hidden": ["commercial"], "leak": 0},
        {"difficulty": "commercial", "recall_at_final": 0.0, "reciprocal_rank": 0.0,
         "hidden": ["commercial"], "leak": 0},
    ]}
    s = bn.role_summary(res)
    assert s["all"] == {"n": 2, "recall_at_6": 0.5, "mrr": 0.5,
                        "hidden_rate": 0.5, "leak_cases": 0}
    assert s["commercial"]["hidden_rate"] == 1.0


def test_sales_cung_visibility_voi_ke_toan():
    # ROLES_B bỏ sales vì nó CÙNG rag_visibility với accounting — khoá lại
    # giả định đó để hồ sơ vai đổi thì test đỏ, không lặng lẽ bỏ sót vai.
    from src.agents.roles import load_profile
    p = load_profile("small-business")
    assert p["sales"].rag_visibility == p["accounting"].rag_visibility
    assert set(bn.ROLES_B) | {"sales"} == set(p)


def test_cong_nua_sau_bat_suy_giam_cuoi_luot():
    base = {"per_case": [{"recall_at_final": 1.0}] * 4}
    tot_dau_hong_cuoi = {"per_case": [{"recall_at_final": 1.0}] * 2
                         + [{"recall_at_final": 0.0}] * 2}
    a, b, ok = bn.second_half_gate(tot_dau_hong_cuoi, base)
    assert (a, b, ok) == (0.0, 1.0, False)
