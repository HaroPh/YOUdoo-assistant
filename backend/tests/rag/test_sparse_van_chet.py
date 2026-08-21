# backend/tests/rag/test_sparse_van_chet.py
"""Chân sparse của hệ "hybrid" trả RỖNG — test này canh khi điều đó ĐỔI.

ĐÂY KHÔNG PHẢI TEST KHOÁ MỘT LỖI LẠI. Nó chốt một sự thật đã đo, và cái đáng
giá là lúc nó ĐỎ.

SỰ THẬT ĐÃ ĐO (2026-08-20): `_sparse()` trả 0 kết quả cho **64/64** câu của bộ
`retrieval`. Nguyên nhân: `plainto_tsquery` nối các lexeme bằng AND, nên một câu
hỏi tự nhiên gần như không bao giờ khớp trọn vẹn. Hệ chạy DENSE-ONLY từ đầu mà
không ai biết, suốt nhiều tháng.

HỒI SINH ĐÃ THỬ VÀ ĐÃ BỎ: đổi sang OR làm `recall@20` TỆ ĐI (1,0 → 0,9766).
Nên đây không phải "tính năng hỏng chờ sửa" — nó là tính năng đã được đo là
KHÔNG giúp gì cho corpus này. Chi phí giữ lại: ~1,6ms/truy vấn và 2,7s mỗi lần
re-index, nên gỡ hẳn không đáng churn.

NẾU TEST NÀY ĐỎ, ĐỌC KỸ TRƯỚC KHI "SỬA":
  - Corpus đã có nội dung khớp được theo mặt chữ (mã hàng, mã chứng từ, số
    hiệu)? Vậy thì hybrid có thể đáng đo lại — chạy `--set retrieval` cả hai
    chiều và so recall@20.
  - Hay chỉ là cấu hình Postgres/tokenizer đổi? Vậy thì kiểm xem nó có kéo theo
    recall tệ đi không, đúng như lần hồi sinh trước.
Trong CẢ HAI trường hợp, việc cần làm là ĐO rồi cập nhật test này — không phải
tắt nó đi.
"""
import pytest

from evals.retrieval_cases import RETRIEVAL_CASES
from src.rag import db as _db
from src.rag import retrieve as rt
from src.rag.ingest import segment_vi


@pytest.mark.integration
def test_chan_sparse_van_tra_rong_tren_corpus_that():
    conn = _db.connect()
    try:
        co_ket_qua = [q for q, _e, _d in RETRIEVAL_CASES
                      if rt._sparse(conn, segment_vi(q))]
    finally:
        conn.close()
    assert not co_ket_qua, (
        f"{len(co_ket_qua)}/{len(RETRIEVAL_CASES)} câu NAY có kết quả sparse — "
        f"trước đây là 0/64. Đây là TIN TỨC, không phải lỗi: đọc docstring tệp "
        f"này rồi ĐO lại hybrid, đừng tắt test. Ví dụ: {co_ket_qua[:3]}")


def test_nhan_method_noi_dung_su_that():
    """Nhãn phải nói `dense`, không được nói `hybrid`, chừng nào chân sparse
    còn rỗng. Ba lần dự án này bị đốt đều vì một thành phần âm thầm không làm
    điều tên nó nói."""
    from src.rag.types import RetrievalResult
    assert "hybrid" not in RetrievalResult.__dataclass_fields__["method"].default
    import inspect
    from src.rag import retrieve
    src = inspect.getsource(retrieve.retrieve)
    assert "hybrid-rrf" not in src, "retrieve() còn sinh ra nhãn 'hybrid'"
