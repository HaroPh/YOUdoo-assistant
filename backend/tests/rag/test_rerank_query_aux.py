# backend/tests/rag/test_rerank_query_aux.py
"""Lượt hỏi TRƯỚC đi vào chân truy xuất, KHÔNG đi vào reranker.

VÌ SAO TỒN TẠI. `retrieve()` nhận `aux_queries` (lượt người dùng liền trước,
`nodes.py`/`fanout.py` luôn truyền từ lượt thứ hai trở đi) để câu rút gọn
("trong bao lâu?") vẫn dựng được pool đúng. Bản đầu cũng ghép lượt trước vào
truy vấn đưa cho cross-encoder:

    rerank_query = query + "\\n" + "\\n".join(aux_queries)

Cross-encoder chấm MỘT cặp (truy vấn, đoạn văn). Ghép hai câu khác chủ đề làm
một thì mọi đoạn đều chỉ khớp được một nửa, điểm sụp và thứ tự đảo.

ĐO ĐƯỢC (bộ multiturn, 2026-09-24, corpus production). Ca `independent`
"các hình thức xử lý kỷ luật lao động gồm những gì?" sau lượt "giá niêm yết
của sản phẩm là bao nhiêu?": đáp án đúng (Điều 124) tụt hạng 5 → 7, tức rơi
khỏi top-6. KHÔNG phải do tranh chỗ trong pool — top-6 vẫn y nguyên tập chunk
đó, chỉ đổi thứ tự. Reranker vẫn chấm Điều 124 CAO NHẤT trong cả hai lần
(5,68 rồi 2,50 so với á quân 0,90); chính việc ghép chuỗi kéo sụp cả thang
điểm (≈3–5 xuống ≈ −1…+0,9) và đảo thứ tự.

NHƯNG ghép chuỗi KHÔNG phải di sản sai — nó đúng cho `override` và sai cho
`blend`. Đo cả bốn ô (recall@6 / MRR, có ngữ cảnh):

                        ghép chuỗi          chỉ câu hiện tại
    blend  elliptical   1,00 / 0,9375       1,00 / 0,9000
    blend  independent  0,75 / 0,6190 (!)   1,00 / 0,6042
    ovrrd  elliptical   1,00 / 0,9000       1,00 / 0,7292
    ovrrd  independent  1,00 / 1,0000       1,00 / 0,8750

Đúng theo VAI TRÒ của cross-encoder: khi nó tự quyết thứ tự (override), truy
vấn trống nghĩa phá thứ tự nên nó CẦN ngữ cảnh — đó là lý do ghép chuỗi ra
đời 2026-07-29. Khi nó chỉ là lá phiếu hoà với RRF (đổi 2026-08-20), RRF đã
mang sẵn bằng chứng từ `aux` ở chân truy xuất, nên ngữ cảnh thừa chỉ còn kéo
sụp thang điểm. Vì thế truy vấn rerank buộc theo `rerank_override()`.

Cùng lớp lỗi với C1 (lượt bóng hợp nhất lượt trước ngang trọng số RRF, sửa
2026-09-22) — cùng gốc, hai chỗ, vòng sửa C1 chỉ đụng một.

Test khoá CẢ HAI NỬA: bỏ `aux` khỏi reranker mà lỡ bỏ luôn khỏi chân truy
xuất thì câu rút gọn hỏng, và bộ multiturn 12 ca là thứ duy nhất bắt được.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.ingest import segment_vi
from src.rag.visibility import UNRESTRICTED

CAU_NAY = "các hình thức xử lý kỷ luật lao động gồm những gì?"
LUOT_TRUOC = "giá niêm yết của sản phẩm là bao nhiêu?"


class _Cursor:
    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor()


@pytest.fixture
def bat_rerank(monkeypatch):
    """Ghi lại truy vấn đưa cho reranker. Trả về dict có `goi` để test khẳng
    định reranker THẬT SỰ được gọi — nếu không, mọi assert dưới đều rỗng."""
    ghi = {"goi": 0, "query": None}

    def _gia(query, chunks):
        ghi["goi"] += 1
        ghi["query"] = query
        return chunks, False

    monkeypatch.setattr(rt, "rerank", _gia)
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    return ghi


def test_blend_chi_nhan_cau_hien_tai_du_co_luot_truoc(bat_rerank, monkeypatch):
    """Chế độ PRODUCTION (blend): truy vấn của cross-encoder = ĐÚNG câu vừa hỏi."""
    monkeypatch.delenv("RAG_RERANK_MODE", raising=False)   # mặc định = blend
    rt.retrieve(CAU_NAY, 6, _FakeConn(), (LUOT_TRUOC,), visibility=UNRESTRICTED)

    assert bat_rerank["goi"] == 1, "reranker không được gọi — test tự vô hiệu"
    assert bat_rerank["query"] == CAU_NAY, (
        f"reranker nhận {bat_rerank['query']!r}, phải là đúng câu hiện tại")
    assert LUOT_TRUOC not in bat_rerank["query"], (
        "lượt trước lọt vào truy vấn của cross-encoder")


def test_override_VAN_ghep_luot_truoc(bat_rerank, monkeypatch):
    """Chế độ override: cross-encoder tự quyết thứ tự nên nó CẦN ngữ cảnh.

    Chiều này giữ nguyên hành vi 2026-07-29 và giữ nguyên ý nghĩa của
    `test_retrieve.test_rerank_recovers_doc_when_bare_query_lacks_context`."""
    monkeypatch.setenv("RAG_RERANK_MODE", "override")
    rt.retrieve(CAU_NAY, 6, _FakeConn(), (LUOT_TRUOC,), visibility=UNRESTRICTED)

    assert bat_rerank["goi"] == 1, "reranker không được gọi — test tự vô hiệu"
    assert bat_rerank["query"] == CAU_NAY + "\n" + LUOT_TRUOC


def test_gia_tri_la_coi_nhu_blend(bat_rerank, monkeypatch):
    """`rerank_override()` không ném với giá trị lạ — và chỗ dùng nó ở đây
    phải thừa hưởng đúng mặc định đó, không tự suy diễn."""
    monkeypatch.setenv("RAG_RERANK_MODE", "OvErRiDe")
    rt.retrieve(CAU_NAY, 6, _FakeConn(), (LUOT_TRUOC,), visibility=UNRESTRICTED)
    assert bat_rerank["query"] == CAU_NAY + "\n" + LUOT_TRUOC, "phải chuẩn hoá hoa/thường"

    monkeypatch.setenv("RAG_RERANK_MODE", "linh tinh")
    rt.retrieve(CAU_NAY, 6, _FakeConn(), (LUOT_TRUOC,), visibility=UNRESTRICTED)
    assert bat_rerank["query"] == CAU_NAY, "giá trị lạ phải rơi về blend"


def test_khong_co_luot_truoc_thi_khong_doi_gi(bat_rerank):
    """Chiều đối chứng: đường MỘT LƯỢT (mọi eval một-lượt, mọi câu hỏi đầu
    hội thoại) phải y như cũ."""
    rt.retrieve(CAU_NAY, 6, _FakeConn(), (), visibility=UNRESTRICTED)

    assert bat_rerank["goi"] == 1, "reranker không được gọi — test tự vô hiệu"
    assert bat_rerank["query"] == CAU_NAY


def test_luot_truoc_VAN_di_vao_chan_truy_xuat(bat_rerank):
    """Nửa còn lại của hợp đồng: `aux` vẫn phải dựng pool, nếu không câu rút
    gọn mất chỗ dựa duy nhất."""
    conn = _FakeConn()
    rt.retrieve(CAU_NAY, 6, conn, (LUOT_TRUOC,), visibility=UNRESTRICTED)

    tham_so = " ".join(str(p) for _sql, p in conn.calls)
    assert segment_vi(LUOT_TRUOC) in tham_so, (
        "lượt trước KHÔNG tới chân truy xuất — câu rút gọn sẽ hỏng")
    assert segment_vi(CAU_NAY) in tham_so, "câu hiện tại không tới chân truy xuất"


@pytest.mark.parametrize("gia_tri, mong", [
    ("override", "override"), ("OVERRIDE", "override"), (" override ", "override"),
    ("blend", "blend"), ("linh tinh", "blend"), (None, "blend"),
])
def test_nhan_rerank_mode_cua_eval_KHOP_hanh_vi_that(monkeypatch, gia_tri, mong):
    """Nhãn `rerank_mode` mà `eval_retrieval` ghi vào kết quả phải là chế độ
    THẬT SỰ chạy — tức lấy từ `rerank_override()`, không tự đọc lại env.

    Bản trước ghi nguyên văn `os.environ.get("RAG_RERANK_MODE", "blend")`:
    với "OVERRIDE" hệ thống chạy override (vì `rerank_override()` chuẩn hoá hoa
    thường) nhưng nhãn ghi "OVERRIDE"; với "linh tinh" hệ chạy blend mà nhãn
    ghi "linh tinh". Cổng so nhãn này với baseline, nên nhãn nói dối là cổng
    ném lỗi giả — hoặc tệ hơn, cho qua một phép so lệch cấu hình."""
    from evals import run_eval
    if gia_tri is None:
        monkeypatch.delenv("RAG_RERANK_MODE", raising=False)
    else:
        monkeypatch.setenv("RAG_RERANK_MODE", gia_tri)
    assert run_eval.rerank_mode_label() == mong
    assert (mong == "override") is rt.rerank_override()
