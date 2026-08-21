# backend/tests/rag/test_reranker_deps.py
"""Chốt: reranker phải THẬT SỰ chạy được trong venv này, không chỉ "code đúng".

VÌ SAO TỒN TẠI. Từ 2026-07-12 đến 2026-08-19, reranker chết 100% trong
production: torch/transformers cố ý không nằm trong requirements.txt, nên
_load() ném ModuleNotFoundError, fail-open nuốt thành None, sentinel cắm
False. retrieve() trả method="dense-rrf" thay vì "hybrid-rrf+rerank" suốt
gần 6 tuần mà KHÔNG một test nào đỏ:

  - 4 test trong test_reranker.py đều monkeypatch _load hoặc score_pairs,
    nên chúng đo logic sắp xếp chứ không đo model có nạp được không;
  - 2 test dùng pytest.importorskip("torch") → SKIP, màu xanh;
  - test_real_model_scores_relevance nằm sau env RUN_RERANK_MODEL mà không
    ai đặt → SKIP, cũng màu xanh.

Mọi lớp bảo vệ đều tự vô hiệu hoá đúng vào lúc cần nhất. Test dưới đây KHÔNG
skip và KHÔNG mock: nó là chỗ duy nhất khẳng định dep thật có mặt.

Cố ý KHÔNG dùng importorskip: "thiếu dep" chính là hỏng hóc cần bắt, biến nó
thành skip là dựng lại đúng cái bẫy vừa thoát ra.
"""
import pytest

from src.rag import reranker


@pytest.fixture(autouse=True)
def _reset_state():
    reranker._state.update(model=None, tokenizer=None)
    yield
    reranker._state.update(model=None, tokenizer=None)


def test_torch_va_transformers_co_that_trong_venv():
    """Thiếu một trong hai là reranker chết im lặng — đỏ ở đây, không ở prod."""
    import torch          # noqa: F401
    import transformers   # noqa: F401


def test_resolve_device_tra_ve_gia_tri_torch_hieu_duoc():
    """_resolve_device() phải trả chuỗi torch.device() nhận, không phải chuỗi
    tuỳ ý — sai một ký tự thì lỗi chỉ lộ ra lúc _load() chạy thật, tức sau
    khi fail-open đã nuốt mất."""
    import torch
    device = reranker._resolve_device()
    assert device in ("cuda", "cpu")
    torch.device(device)  # raise nếu chuỗi không hợp lệ


@pytest.mark.integration
def test_model_that_nap_duoc_va_cham_diem_dung_thu_tu(monkeypatch):
    """Nạp model 2.3GB THẬT và chấm điểm — bắt cả lỗi thiếu kernel sm_120.

    Đánh dấu `integration` (không phải env var như bản cũ): chế độ chạy mặc
    định của repo là -m "not integration and not live", nên nó không làm chậm
    vòng lặp thường, NHƯNG nó nằm trong một marker có sẵn mà quy trình đã
    biết chạy — khác hẳn RUN_RERANK_MODEL, một biến không xuất hiện trong bất
    kỳ lệnh nào của repo.

    setenv là BẮT BUỘC, không thừa: conftest.py của thư mục này có fixture
    autouse `_rerank_off` đặt RAG_RERANK_ENABLED=0 cho MỌI test trong
    tests/rag/ (để test cũ không vô tình tải model 2.3GB). Đó là lớp làm-câm
    thứ tư của cùng câu chuyện — viết test đúng ở đây mà quên dòng này thì nó
    vẫn xanh vô nghĩa. Đã tự dẫm phải đúng một lần khi viết file này.
    """
    monkeypatch.setenv("RAG_RERANK_ENABLED", "1")
    scores = reranker.score_pairs(
        "khách hàng muốn hoàn hàng sau 30 ngày",
        ["Khách hàng có thể hoàn hàng trong vòng 30 ngày kể từ ngày mua.",
         "Quy trình bảo trì máy CNC định kỳ 6 tháng."])
    assert scores is not None, (
        "score_pairs trả None — reranker đang fail-open, tức nó KHÔNG chạy. "
        "Đây đúng trạng thái chết im lặng 2026-07-12..08-19.")
    assert len(scores) == 2
    assert scores[0] > scores[1]
