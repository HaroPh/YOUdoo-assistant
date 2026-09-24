# backend/tests/evals/test_retrieval_cases.py
"""Hợp đồng golden set ↔ corpus thật.

Nhãn viết tay có thể trỏ vào cặp (tệp, section_path) KHÔNG tồn tại — sai
chính tả, đổi tên tệp, hay heading bị parse_pdf cắt khác đi. Nhãn như vậy
làm recall tụt mà không ai hiểu vì sao, và trông y hệt "model kém đi".

Đây đúng lớp lỗi GATHER_CASES từng dính: fixture trôi khỏi dữ liệu thật mà
không ai biết, phải thêm test hợp đồng sau. Lần này viết cùng lúc.
"""
import hashlib

import pytest

from evals.hard_expansion_cases import HARD_EXPANSION_CASES
from evals.hard_gate import HARD_MAX_OVERLAP, overlap
from evals.retrieval_cases import RETRIEVAL_CASES
from evals.retrieval_score import label_matches, label_of
from src.rag import db as _db


def test_moi_ca_co_it_nhat_mot_nhan():
    for question, expected, _difficulty in RETRIEVAL_CASES:
        assert expected, f"ca không có nhãn nào: {question!r}"


def test_difficulty_chi_nhan_ba_gia_tri():
    for question, _expected, difficulty in RETRIEVAL_CASES:
        assert difficulty in ("easy", "hard", "trap"), \
            f"hạng lạ {difficulty!r} ở ca {question!r}"


def test_co_du_ca_ba_hang_do_kho():
    # trap BẮT BUỘC phải có: 9 PDF luật đều mở đầu bằng cùng cấu trúc
    # ("Điều 1. Phạm vi điều chỉnh"), nên bộ đo thiếu ca bẫy sẽ không bao
    # giờ thấy lỗi trúng-nhầm-văn-bản.
    seen = {d for _q, _e, d in RETRIEVAL_CASES}
    assert seen == {"easy", "hard", "trap"}


def test_du_so_ca_bay():
    # Ngưỡng cứng, không phải "có là được": ca bẫy là hạng duy nhất phân biệt
    # được "trúng tài liệu" với "trúng ĐÚNG tài liệu".
    n_trap = sum(1 for _q, _e, d in RETRIEVAL_CASES if d == "trap")
    assert n_trap >= 16, f"chỉ có {n_trap} ca bẫy"


def test_da_so_ca_cham_pdf_luat():
    # 98,7% corpus là PDF luật nhưng mọi câu hỏi rag trong cases.py chỉ chạm
    # 44 chunk nghiệp vụ. Nếu golden set cũng vậy thì nó chỉ đo lại vùng đã
    # đo, và 3.256 chunk vẫn không ai gác.
    n_law = sum(1 for _q, exp, _d in RETRIEVAL_CASES
                if any(f.endswith(".pdf") for f, _s in exp))
    assert n_law >= 30, f"chỉ có {n_law} ca chạm PDF luật, spec §3 đòi >=30"


def test_khong_co_cau_hoi_trung_lap():
    questions = [q for q, _e, _d in RETRIEVAL_CASES]
    assert len(questions) == len(set(questions))


# Băm nội dung 64 ca cũ. Sinh MỘT LẦN khi nối bộ mở rộng (Task 5, 2026-09-18)
# bằng lệnh ở docstring; đỏ = ai đó đã sửa/xoá/thêm ca cũ — không được phép,
# vì old-64 là đối chứng hạ tầng (spec 2026-09-18 §7).
_CORE_SHA256 = "845473c4d72d15ee7cdbccde4bb9262c168be97412bca466612b8700a00ea44e"


def _core_digest() -> str:
    from evals.retrieval_cases import _CORE
    canon = repr([(q, sorted(exp), d) for q, exp, d in _CORE])
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_64_ca_cu_khong_doi_mot_ky_tu():
    from evals.retrieval_cases import _CORE
    assert len(_CORE) == 64
    assert _core_digest() == _CORE_SHA256, (
        "64 ca cũ đã đổi. Nếu CỐ Ý, cập nhật _CORE_SHA256 bằng:\n"
        "  python -c \"from tests.evals.test_retrieval_cases import _core_digest; print(_core_digest())\"")


def test_du_so_ca_hard_cho_thong_ke():
    # sd ≈ 0,395 trên chênh RR → se 0,05 cần ~62 ca (spec 2026-09-18 §1).
    n_hard = sum(1 for _q, _e, d in RETRIEVAL_CASES if d == "hard")
    assert n_hard >= 60, f"chỉ có {n_hard} ca hard"


def test_moi_ca_mo_rong_qua_cong_overlap():
    # Cổng CHỈ áp lên bộ mới — vài ca hard cũ gán theo ngữ nghĩa có overlap tới 0,83.
    bad = [(q, round(overlap(q, [s for _f, s in exp]), 2))
           for q, exp, _d in HARD_EXPANSION_CASES
           if overlap(q, [s for _f, s in exp]) > HARD_MAX_OVERLAP]
    assert not bad, f"vượt cổng {HARD_MAX_OVERLAP}: {bad}"
    assert all(d == "hard" for _q, _e, d in HARD_EXPANSION_CASES)


@pytest.mark.integration
def test_moi_nhan_khop_it_nhat_mot_chunk_that():
    """Nhãn không khớp hàng nào trong rag_chunks → ĐỎ, kèm tên nhãn."""
    conn = _db.connect()
    try:
        rows = conn.execute(
            "select source_file, section_path, sheet from rag_chunks").fetchall()
    finally:
        conn.close()

    class _Row:
        def __init__(self, r):
            self.source_file, self.section_path, self.sheet = r

    real = {label_of(_Row(r)) for r in rows}
    missing = sorted({lab for _q, exp, _d in RETRIEVAL_CASES for lab in exp
                      if not any(label_matches(rl, lab) for rl in real)})
    assert not missing, (
        f"{len(missing)} nhãn không khớp chunk thật nào — golden set đã trôi "
        f"khỏi corpus (hoặc sai chính tả). Nhãn hỏng: {missing[:10]}")


def _baseline_retrieval_files():
    """Mọi baseline của bộ `retrieval`, gồm cả biến thể dạng gõ và vai."""
    import glob
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "evals")
    return sorted(glob.glob(os.path.join(here, "baseline-*-retrieval*.json")))


def test_moi_baseline_do_tren_DUNG_bo_ca_hien_tai():
    """Baseline phải được chốt trên CHÍNH bộ ca hiện tại.

    LỖI THẬT (phát hiện 2026-09-24): hard-set mở rộng 17→62 ca ngày 2026-09-19
    nhưng chỉ baseline dạng CÓ DẤU được chốt lại. Hai baseline `nua_dau` /
    `khong_dau` ở lại 64 ca, nên mỗi lần chạy là so 109 ca với mốc 64 ca —
    `GATE FAIL` giả, lệch tới 0,09. Không ai thấy trong 5 tuần vì bộ
    `retrieval` không nằm trong `EVAL_FN` của job nào.

    Đo lại trên CÙNG 64 ca thì không có hồi quy nào: nửa dấu khớp đúng
    0,8203 = 0,8203, không dấu lệch 1 ca (và lệch đó có TRƯỚC phiên sửa).

    Test này bắt đúng cơ chế đã xảy ra — bộ ca đổi mà baseline không theo —
    thay vì phải chạy cả ba dạng gõ mỗi đêm.
    """
    import collections
    import json

    muon = collections.Counter(d for _q, _e, d in RETRIEVAL_CASES)
    files = _baseline_retrieval_files()
    assert files, "không tìm thấy baseline nào của bộ retrieval — glob sai?"

    sai = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)
        ten = path.rsplit("baseline-", 1)[-1]
        if b["n"] != len(RETRIEVAL_CASES):
            sai.append(f"{ten}: n={b['n']}, bộ ca hiện tại {len(RETRIEVAL_CASES)}")
            continue
        co = {k: v["n"] for k, v in b.get("by_difficulty", {}).items()}
        if co != dict(muon):
            sai.append(f"{ten}: độ khó {co}, hiện tại {dict(muon)}")
    assert not sai, (
        "baseline chốt trên bộ ca KHÁC bộ ca hiện tại — mọi phép so với chúng "
        "là khập khiễng:\n  " + "\n  ".join(sai)
        + "\nChốt lại: python -m evals.run_eval --set retrieval --model bge-m3 "
          "--dang-go <dạng> --save-baseline")
