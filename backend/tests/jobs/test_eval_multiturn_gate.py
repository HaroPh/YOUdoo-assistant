# backend/tests/jobs/test_eval_multiturn_gate.py
"""Cổng `multiturn` trong job eval-gate.

VÌ SAO TỒN TẠI. `eval_multiturn` có từ 2026-08-20 nhưng KHÔNG nằm trong
`EVAL_FN` lẫn `BASELINE_SETS`, nên job chưa bao giờ chạy nó và `_gate` chưa
bao giờ có nhánh cho nó — bộ đo sinh ra số mà không ai đọc. Hệ quả đo được:
lỗi truy vấn ghép cho cross-engine làm `independent` recall@6 tụt 1,00 → 0,75
và không cổng nào kêu, mãi tới khi đo tay ngày 2026-09-24.

Cổng TUYỆT ĐỐI, tự so trong cùng một lượt — xem chú thích trong `_gate`.
"""
import argparse

import pytest

from evals import run_eval
from jobs import eval_gate


def _kq(ell_no, ell_with, ind_no, ind_with) -> dict:
    return {"by_kind": {
        "elliptical": {"n": 8, "recall_at_6_no_ctx": ell_no,
                       "recall_at_6_with_ctx": ell_with},
        "independent": {"n": 4, "recall_at_6_no_ctx": ind_no,
                        "recall_at_6_with_ctx": ind_with}}}


def test_da_noi_vao_job():
    assert eval_gate.EVAL_FN["multiturn"] is run_eval.eval_multiturn
    assert "multiturn" in eval_gate.NO_LLM_SETS, (
        "hàm đo không nhận `llm` — không khai ở đây thì job gọi sai khuôn")


def test_khong_doc_baseline():
    """Cổng tuyệt đối. Neo baseline của job là model CHAT (`qwen3-8b`) còn bộ
    này không gọi LLM lần nào — để nó trong BASELINE_SETS là đi tìm một tệp
    `baseline-qwen3-8b-multiturn.json` không tồn tại."""
    assert "multiturn" not in eval_gate.BASELINE_SETS
    assert eval_gate._baseline_for("multiturn", eval_gate.BASELINE_MODEL, "admin") is None
    # base=None phải dùng được — nếu nhánh cổng lỡ đọc `base[...]` thì đây ĐỎ.
    assert eval_gate._gate("multiturn", _kq(0.75, 1.0, 1.0, 1.0), None) is True


def test_nam_trong_set_all():
    """Không nằm trong `all` thì lịch đêm không chạy — đúng cách `sop_select`
    mất tác dụng suốt 6 tuần."""
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "all"])
    assert args.set == "all"
    assert "multiturn" in p.parse_args(["--set", "multiturn"]).set


def test_so_do_that_sau_khi_sua_thi_PASS():
    """Số đo thật, chế độ blend, corpus production, 2026-09-24."""
    assert eval_gate._gate("multiturn", _kq(0.75, 1.0, 1.0, 1.0), None) is True


def test_so_do_that_TRUOC_khi_sua_thi_FAIL():
    """Bằng chứng cổng gác được thật: đây là ĐÚNG số của mã trước f30422b —
    truy vấn ghép cho cross-encoder làm câu tự-đứng-được tệ đi."""
    assert eval_gate._gate("multiturn", _kq(0.75, 1.0, 1.0, 0.75), None) is False


@pytest.mark.parametrize("ind_no, ind_with", [(1.0, 0.75), (0.75, 0.5), (1.0, 0.0)])
def test_chieu_HAI_ngu_canh_lam_cau_tu_dung_duoc_te_di(ind_no, ind_with):
    assert eval_gate._gate("multiturn", _kq(0.75, 1.0, ind_no, ind_with), None) is False


def test_chieu_LOI_aux_chet_thi_FAIL_du_khong_ai_te_di():
    """Gỡ `aux_queries` khỏi chân truy xuất ⇒ with_ctx BẰNG no_ctx. Đây là lý
    do vế lợi dùng `>` chứ không `>=`: `>=` sẽ cho qua đúng lúc tính năng chết."""
    assert eval_gate._gate("multiturn", _kq(0.75, 0.75, 1.0, 1.0), None) is False
    assert eval_gate._gate("multiturn", _kq(0.875, 0.875, 1.0, 1.0), None) is False


def test_loi_thoat_tran_khong_de_cong_do_vinh_vien():
    """Khi corpus tốt lên tới mức câu rút gọn tự đạt 1,0 thì KHÔNG gì vượt
    được 1,0. Không có lối thoát này, cổng đỏ vĩnh viễn — đúng bẫy đã làm
    `sop_select` bị gỡ khỏi `--set all` suốt 6 tuần."""
    assert eval_gate._gate("multiturn", _kq(1.0, 1.0, 1.0, 1.0), None) is True


def test_tran_KHONG_che_lap_chieu_hai():
    """Lối thoát trần chỉ nới vế LỢI. Vế HẠI vẫn phải trượt kể cả khi câu rút
    gọn hoàn hảo — nếu không, một lối thoát lại mở đường cho hồi quy thật."""
    assert eval_gate._gate("multiturn", _kq(1.0, 1.0, 1.0, 0.75), None) is False
