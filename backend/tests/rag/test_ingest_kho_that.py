# backend/tests/rag/test_ingest_kho_that.py
"""Nghiệm thu tầng 2 — tài liệu THẬT, ngoài repo (spec mục 6.1, mục 7).

Không có `tmp-docs/` thì skip: kho này không được commit (tệp nặng, văn bản
bên thứ ba), nên máy khác sẽ không có.
"""
import os
import pytest

from src.rag import ingest as _ing

KHO = "d:/Youdoo/tmp-docs"
pytestmark = pytest.mark.live


class _FakeConn:
    """Đủ cho nhánh kiểm content_hash và cho INSERT giả.

    KHÔNG truyền `conn=None`: tệp nào đi tới nhánh ghi DB sẽ ném
    AttributeError và test vỡ thay vì đo được điều gì. Cùng khuôn với
    `_FakeConn` trong test_ingest_guard.py.

    Có thêm `transaction()` so với `_FakeConn` gốc trong test_ingest_guard.py:
    kho thật có tài liệu NẠP ĐƯỢC thật (không chỉ tệp bị từ chối), nên
    `_ingest_known` đi tới `with conn.transaction():` thật — thiếu phương
    thức này thì mọi tệp nạp thành công đều vỡ AttributeError, không phải
    một trạng thái test đang đo tới. Cùng khuôn với `_RecordingConn` trong
    test_ingest_guard.py."""

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return None          # chưa từng nạp tệp này

    def transaction(self):
        import contextlib
        return contextlib.nullcontext()


@pytest.fixture
def _no_embed(monkeypatch):
    """Chặn gọi embedder thật: bài này đo ĐỊNH TUYẾN ĐỊNH DẠNG, không đo
    chất lượng vector, và một lượt embed thật tốn hạn mức."""
    monkeypatch.setattr(_ing, "embed_texts",
                        lambda texts: [[0.01] * 1024 for _ in texts])


def _co_kho():
    return os.path.isdir(KHO)


@pytest.mark.skipif(not _co_kho(), reason="chưa có tmp-docs")
def test_khong_tai_lieu_nao_bien_mat_im_lang(_no_embed):
    """Trước bản sửa: `.doc`, `.xlsm`, `.pptx` trả toàn 0 và không lời nào.
    Sau bản sửa: mỗi tệp tài liệu phải ra ở MỘT trong ba trạng thái —
    không tệp nào rơi vào khoảng trắng "0 mọi thứ, ok=True"."""
    tai_lieu = sorted(f for f in os.listdir(KHO)
                      if os.path.splitext(f)[1].lower() in _ing.DOCUMENT_EXT)
    assert len(tai_lieu) >= 10, "kho test quá nhỏ, xem lại tmp-docs"

    im_lang = []
    for name in tai_lieu:
        try:
            rep = _ing._ingest_file(os.path.join(KHO, name), conn=_FakeConn())
        except _ing.IngestError:
            continue          # hỏng TO TIẾNG — đúng ý đồ, không phải im lặng
        if rep.ingested == 0 and rep.unchanged == 0 and rep.ok:
            im_lang.append(name)
    assert im_lang == [], f"vẫn còn tài liệu biến mất im lặng: {im_lang}"


@pytest.mark.skipif(not _co_kho(), reason="chưa có tmp-docs")
def test_dem_theo_dinh_dang_de_doc_duoc_bang_mat(_no_embed):
    """In bảng phân bố trạng thái theo đuôi. Không phải khẳng định chặt —
    mục đích là để người chạy NHÌN THẤY kho thật rơi vào đâu, vì con số
    tổng không nói được tài liệu nào vắng mặt."""
    from collections import Counter
    dem = Counter()
    for name in sorted(os.listdir(KHO)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in _ing.DOCUMENT_EXT:
            continue
        try:
            rep = _ing._ingest_file(os.path.join(KHO, name), conn=_FakeConn())
            trang_thai = ("rejected" if rep.rejected else
                          "ingested" if rep.ingested else
                          "unchanged" if rep.unchanged else "IM_LANG")
        except _ing.IngestError:
            trang_thai = "IngestError"
        dem[(ext, trang_thai)] += 1
    for (ext, tt), n in sorted(dem.items()):
        print(f"  {ext:<7} {tt:<12} {n}")
    assert dem, "không đọc được tệp nào"
    assert not any(tt == "IM_LANG" for (_, tt) in dem)
