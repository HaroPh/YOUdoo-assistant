"""Công thức gate của set `retrieval` — KHÔNG gọi embedder/DB.

Đóng #28: `_gate` không có nhánh `retrieval` nên `run_eval --set retrieval
--baseline` rơi xuống nhánh mặc định đòi `false_confirm` → KeyError sau khi
đã in JSON. Bộ đo truy xuất vì thế chưa từng có cổng tự động.

Khuôn: giống 4 cổng anh em (planner/read/synthesis/multi_source) — một điều
kiện KHÔNG nới + một điều kiện so baseline có dung sai.
"""
import json

import pytest

from evals import run_eval
from jobs.eval_gate import _gate

# Hình dạng đúng của `baseline-bge-m3-retrieval.json` (2026-09-19): 109 ca,
# recall báo cáo 4 chữ số thập phân.
N = 109
BASE = {"dang_go": "co_dau", "rerank": True, "role": "admin", "n": N,
        "recall_at_20": 0.9771, "recall_at_6": 0.9633, "mrr": 0.8058}


def _ket_qua(**doi):
    return {**BASE, **doi}


def test_gate_bang_baseline_thi_qua():
    assert _gate("retrieval", _ket_qua(), BASE) is True


def test_gate_recall_at_20_tuyet_doi_tut_bat_ky_la_truot():
    """`recall_at_20` là TRẦN POOL: reranker chỉ chọn trong 20 ứng viên này.
    Tụt nghĩa là có tài liệu bị lọc mất khỏi ứng viên — đúng thứ 19b (lọc
    `visibility` trong SQL) có thể gây ra, nên KHÔNG dung sai."""
    assert _gate("retrieval", _ket_qua(recall_at_20=0.9770), BASE) is False
    # tụt r@20 trượt DÙ r@6 tăng
    assert _gate("retrieval", _ket_qua(recall_at_20=0.9770,
                                       recall_at_6=1.0), BASE) is False


def test_gate_recall_at_6_dung_sai_mot_ca():
    """Rerank blend có thể lật một ca biên, nên r@6 chịu dung sai 1/n như
    `confirm`. Test cố ý tránh ĐIỂM BIÊN (đúng 1/n): recall báo cáo đã làm
    tròn 4 chữ số nên một ca tụt đúng biên có thể rơi lệch phía ngưỡng — đó
    là lớp lỗi làm tròn đã dính ở `retrieval_stats`; công thức này không
    hứa gì về đúng-biên, chỉ hứa "khoảng một ca"."""
    nua_ca, mot_ruoi_ca = 0.5 / N, 1.5 / N
    assert _gate("retrieval", _ket_qua(recall_at_6=BASE["recall_at_6"] - nua_ca),
                 BASE) is True
    assert _gate("retrieval", _ket_qua(recall_at_6=BASE["recall_at_6"] - mot_ruoi_ca),
                 BASE) is False
    # tăng thì đương nhiên qua
    assert _gate("retrieval", _ket_qua(recall_at_6=1.0), BASE) is True


def test_gate_khong_gac_mrr():
    """Thứ hạng BÊN TRONG 6 chunk model đều đọc cả (kết luận rerank blend
    2026-08-20) — mrr chỉ vào báo cáo, không phải điều kiện cổng."""
    assert _gate("retrieval", _ket_qua(mrr=0.1), BASE) is True


@pytest.mark.parametrize("khoa,gia_tri", [("dang_go", "khong_dau"),
                                          ("rerank", False)])
def test_gate_tu_choi_baseline_khac_cau_hinh(khoa, gia_tri):
    """Có 3 file baseline khác `dang_go` và cờ `--no-rerank`: so kết quả với
    baseline khác cấu hình là so táo với cam. Đây là DÙNG SAI, không phải hồi
    quy — ném lỗi nói rõ khoá nào lệch, không trả FAIL."""
    with pytest.raises(ValueError, match=khoa):
        _gate("retrieval", _ket_qua(**{khoa: gia_tri}), BASE)


def test_gate_tu_choi_baseline_khac_vai():
    """Lượt --role warehouse so với baseline admin: FAIL là ĐÚNG về mặt số,
    nhưng đó là dùng sai cổng — cổng âm có công cụ riêng (compare_visibility)."""
    with pytest.raises(ValueError, match="role"):
        _gate("retrieval", _ket_qua(role="warehouse"), BASE)


def test_gate_baseline_cu_khong_co_role_hieu_la_admin():
    """baseline-bge-m3-retrieval.json ghi trước 19b không có khoá role."""
    base_cu = {k: v for k, v in BASE.items() if k != "role"}
    assert _gate("retrieval", _ket_qua(), base_cu) is True


async def test_main_baseline_retrieval_in_dong_gate_bang_recall_at_6(
        monkeypatch, tmp_path, capsys):
    """Lỗi THỨ HAI của #28, bị KeyError `false_confirm` che: sau `_gate`,
    `main` chọn `key` để in `GATE … model=… baseline=…` và rơi về `"acc"` —
    retrieval không có `acc`. Đường `--baseline` phải chạy TRỌN tới exit 0
    và in đúng số r@6 của cả hai bên."""
    async def gia_retrieval(pace=0.0, checkpoint_path=None, **kw):
        return {**_ket_qua(), "fails": [], "errors": []}

    monkeypatch.setattr(run_eval, "eval_retrieval", gia_retrieval)
    duong_baseline = tmp_path / "baseline-bge-m3-retrieval.json"
    duong_baseline.write_text(json.dumps({**BASE, "fails": [], "errors": []}),
                              encoding="utf-8")

    with pytest.raises(SystemExit) as ei:
        await run_eval.main(["--set", "retrieval", "--model", "bge-m3",
                             "--pace", "0", "--baseline", str(duong_baseline)])
    assert ei.value.code == 0
    dong_gate = [d for d in capsys.readouterr().out.splitlines()
                 if d.startswith("GATE ")]
    assert dong_gate == ["GATE PASS — model=0.963 baseline=0.963"]
