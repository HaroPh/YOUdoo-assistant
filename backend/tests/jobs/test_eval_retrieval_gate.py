# backend/tests/jobs/test_eval_retrieval_gate.py
"""Bộ `retrieval` trong job eval-gate.

VÌ SAO TỒN TẠI. `_gate` đã có nhánh `retrieval` từ trước (CLI `--baseline` gọi
thẳng vào đó), nhưng bộ này KHÔNG nằm trong `EVAL_FN`, nên **không job nào
chạy nó**. Hệ quả đo được: hard-set mở rộng 17→62 ca ngày 2026-09-19 mà chỉ
baseline dạng CÓ DẤU được chốt lại; hai baseline `nua_dau`/`khong_dau` ở lại
64 ca và mỗi lần ai đó chạy tay là `GATE FAIL` giả, lệch tới 0,09. Không ai
biết trong 5 tuần.

Đo lại trên CÙNG 64 ca thì không có hồi quy: nửa dấu khớp đúng 0,8203; không
dấu lệch 1 ca, và lệch đó có TRƯỚC phiên sửa 2026-09-24.
"""
import argparse

import pytest

from evals import run_eval
from jobs import eval_gate


def _kq(n=109, r20=0.9771, r6=0.963, dang_go="co_dau", rerank=True, role="admin"):
    return {"set": "retrieval", "n": n, "rerank": rerank, "dang_go": dang_go,
            "role": role, "recall_at_20": r20, "recall_at_6": r6, "mrr": 0.8}


BASE = _kq()


def test_da_noi_vao_job():
    assert eval_gate.EVAL_FN["retrieval"] is run_eval.eval_retrieval
    assert "retrieval" in eval_gate.NO_LLM_SETS, "hàm đo không nhận `llm`"
    assert "retrieval" in eval_gate.BASELINE_SETS, (
        "khác `multiturn`: bộ này CÓ baseline, không phải cổng tuyệt đối")


def test_neo_baseline_la_model_NHUNG_khong_phai_model_chat():
    """`BASELINE_MODEL` của job là `qwen3-8b`, một model CHAT. Bộ này không gọi
    LLM lần nào và baseline thật tên `bge-m3` — dùng neo chung sẽ đi tìm một
    tệp không tồn tại và INFRA_ERROR mỗi đêm."""
    import os
    p = eval_gate._baseline_for("retrieval", eval_gate.EMBED_MODEL_LABEL, "admin")
    assert p is not None and os.path.exists(p), p
    assert "bge-m3" in os.path.basename(p)
    thieu = eval_gate._baseline_for("retrieval", eval_gate.BASELINE_MODEL, "admin")
    assert not os.path.exists(thieu), (
        "tệp theo neo model chat lại TỒN TẠI — test này hết đo được gì")


def test_nam_trong_set_all():
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args(["--set", "retrieval"]).set == "retrieval"


def test_pass_khi_bang_baseline():
    assert eval_gate._gate("retrieval", _kq(), BASE) is True


def test_r20_KHONG_co_dung_sai():
    """r@20 là TRẦN POOL — tụt nghĩa là tài liệu bị lọc mất khỏi ứng viên,
    reranker không cứu được. Một ca cũng trượt."""
    assert eval_gate._gate("retrieval", _kq(r20=0.9771 - 1 / 109), BASE) is False


def test_r6_chiu_dung_sai_mot_ca():
    """rerank blend có thể lật một ca biên — cùng khuôn `confirm`."""
    assert eval_gate._gate("retrieval", _kq(r6=0.963 - 1 / 109 + 1e-9), BASE) is True
    assert eval_gate._gate("retrieval", _kq(r6=0.963 - 2 / 109), BASE) is False


@pytest.mark.parametrize("khac", [
    {"n": 64},
    {"dang_go": "khong_dau"},
    {"rerank": False},
    {"role": "warehouse"},
])
def test_baseline_khac_cau_hinh_thi_NEM_chu_khong_FAIL(khac):
    """So táo với cam là DÙNG SAI, không phải hồi quy — trả FAIL sẽ khiến
    người ta đi tìm lỗi chất lượng không tồn tại.

    `n` là khoá THÊM 2026-09-24: nó chính là kẽ hở đã cho phép so 109 ca với
    mốc 64 ca trôi qua trong im lặng."""
    with pytest.raises(ValueError):
        eval_gate._gate("retrieval", _kq(**khac), BASE)


def test_n_lech_bi_bat_du_chat_luong_TOT_HON():
    """Chiều quan trọng: `n` lệch phải bị chặn kể cả khi số trông ĐẸP. Nếu chỉ
    chặn khi số xấu thì một baseline cũ vẫn lặng lẽ cho qua mọi lượt may mắn."""
    with pytest.raises(ValueError):
        eval_gate._gate("retrieval", _kq(n=64, r20=1.0, r6=1.0), BASE)
