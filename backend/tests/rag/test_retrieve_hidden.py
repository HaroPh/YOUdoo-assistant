# backend/tests/rag/test_retrieve_hidden.py
"""Tín hiệu `hidden_classes` (spec 2026-09-21 §3): bản bóng KHÔNG lọc chạy khi
vai bị giới hạn, luật TOP-K (`HIDDEN_TOP_K`, ĐỔI 2026-09-22 từ hạng-1 — xem
task-9-brief: cổng ÂM thật trên 109 ca chỉ bắt 5/10 với luật hạng-1, k=3 bắt
9/10 với 0/99 từ chối oan), và chunk bị giấu không bao giờ rời retrieve().

Phần unit: conn giả HAI POOL — trả `visible` khi SQL có mệnh đề lọc, `all_`
khi không. Mọi chân trả cùng danh sách nên thứ tự RRF = thứ tự danh sách:
vị trí trong `all_` chính là thứ hạng của bản bóng (0-index → hạng vị trí+1).
Phần integration ở dưới (Task 5, mở rộng Task 9) chạy DB thật.
"""
import pytest

from src.rag import retrieve as rt
from src.rag.visibility import UNRESTRICTED

VIS_CLAUSE = "c.visibility = ANY(%s)"
CHI_ALL = frozenset({"all"})


def _row(id_, source_file, vis, score, text="x"):
    """Hàng khớp `_COLS` + score: (id, doc_id, source_file, doc_title, section_path,
    page, sheet, row_range, chunk_text, effective_date, source_kind, visibility, score)."""
    return (id_, f"d{id_}", source_file, "T", None, None, None, None,
            text, None, "text", vis, score)


class _Cur:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _ConnHaiPool:
    def __init__(self, visible, all_):
        self.visible, self.all_ = visible, all_
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cur(self.visible if VIS_CLAUSE in sql else self.all_)


@pytest.fixture
def khong_ra_ngoai(monkeypatch):
    monkeypatch.setattr(rt, "embed_query", lambda q: [0.0] * 1024)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")


TM = _row(1, "seed\\discount_policy.docx", "commercial", 0.9)
ALL = _row(2, "seed/policy.docx", "all", 0.5)
# 3 hàng lớp 'all' THÊM, id RIÊNG BIỆT (Task 9) — bản bóng cần ≥4 hàng để biểu
# diễn được biên top-3 ("bị giấu ở hạng 4 → không báo"). Dùng chung `ALL` cho cả
# 3 vị trí sẽ SAI: `_ConnHaiPool` cho mọi chân trả về CÙNG object nên `_rrf` gộp
# theo `row[0]` (id) — id trùng thì các bản sao chập vào MỘT khoá trong `fused`,
# bản bóng lại chỉ còn 2 hàng phân biệt, đúng cái bẫy fixture nông đã cắn task này.
ALL2 = _row(3, "seed/policy_b.docx", "all", 0.4)
ALL3 = _row(4, "seed/policy_c.docx", "all", 0.3)
ALL4 = _row(5, "seed/policy_d.docx", "all", 0.2)


def test_bi_gioi_han_va_hang_1_bi_giau_thi_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    # BẤT BIẾN AN TOÀN: chunk trả về vẫn là bản đã lọc — không có hàng thương mại
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]


def test_bi_giau_o_hang_3_thi_bao(khong_ra_ngoai):
    """MỚI (Task 9): TM đứng hạng 3 của bản bóng SÂU 4 hàng. Luật hạng-1 cũ BỎ
    SÓT đúng ca này — cổng ÂM thật trên 109 ca chỉ bắt 5/10 câu thương mại vì
    phần lớn tài liệu bị giấu không đứng hạng 1 (xem bảng hạng trong
    task-9-brief.md: "khách nợ quá hạn mức", "mua nhiều có giảm thêm", "giá
    niêm yết sản phẩm" đều hạng 3). Luật top-3 mới PHẢI báo."""
    conn = _ConnHaiPool(visible=[ALL], all_=[ALL2, ALL3, TM, ALL4])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]


def test_bi_giau_o_hang_4_thi_khong_bao(khong_ra_ngoai):
    """MỚI (Task 9) — cổng CHỨNG MINH k thật sự có biên, không phải "báo mọi
    lúc": TM đứng hạng 4, NGOÀI top-3 → không báo. Đột biến bắt buộc của task
    này (HIDDEN_TOP_K 3→2) phải làm `test_bi_giau_o_hang_3_thi_bao` ĐỎ, và
    (3→4) phải làm CHÍNH test này ĐỎ — xem report."""
    conn = _ConnHaiPool(visible=[ALL], all_=[ALL2, ALL3, ALL4, TM])
    r = rt.retrieve("hoàn hàng", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()


def test_bi_gioi_han_nhung_khong_co_gi_bi_giau_thi_khong_bao(khong_ra_ngoai):
    """MỚI (Task 9): bản bóng toàn lớp 'all' (không có gì bị giấu, ở BẤT KỲ
    hạng nào) → không báo. Khác `test_bi_giau_o_hang_4_thi_khong_bao`: ở đó
    thứ bị giấu CÓ tồn tại nhưng ngoài top-k; ở đây không có gì để giấu."""
    conn = _ConnHaiPool(visible=[ALL], all_=[ALL, ALL2, ALL3, ALL4])
    r = rt.retrieve("chính sách chung", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()


def test_ban_bong_rong_thi_khong_bao(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[], all_=[])
    r = rt.retrieve("không có gì", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.is_empty()


def test_unrestricted_khong_chay_ban_bong(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=UNRESTRICTED)
    assert r.hidden_classes == frozenset()
    assert len(conn.calls) == 3, [s[:40] for s, _ in conn.calls]   # 3 chân, KHÔNG bóng
    assert not any(VIS_CLAUSE in s for s, _ in conn.calls)


def test_bi_gioi_han_chay_dung_hai_luot_ba_chan(khong_ra_ngoai):
    """Lượt LỌC trước, lượt BÓNG sau — 6 câu; nửa đầu có mệnh đề, nửa sau không.
    Thứ tự là hợp đồng: test hình dạng SQL của 19b nhận diện chân bằng câu ĐẦU."""
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    co_loc = [VIS_CLAUSE in s for s, _ in conn.calls]
    assert co_loc == [True, True, True, False, False, False], co_loc


def test_khong_truyen_visibility_van_chay_bong_vi_fail_closed(khong_ra_ngoai):
    conn = _ConnHaiPool(visible=[ALL], all_=[TM, ALL])
    r = rt.retrieve("chiết khấu", conn=conn)          # None → {'all'} → bị giới hạn
    assert r.hidden_classes == frozenset({"commercial"})


def test_hidden_in_top_k_don_vi():
    """Đơn vị THUẦN cho `_hidden_in_top_k` (đổi tên Task 9 từ
    `_hidden_at_rank_one`) — gọi thẳng hàm, không qua `retrieve()`/conn giả.
    `fused` dựng ≥4 hàng ID riêng để biên k=3 diễn tả được (2 hàng thì top-3
    luôn chứa hết, không phân biệt được gì — đúng bẫy đã cắn task này)."""
    fused = {1: {"row": TM, "rrf": 0.05}, 2: {"row": ALL, "rrf": 0.04},
             3: {"row": ALL2, "rrf": 0.03}, 4: {"row": ALL3, "rrf": 0.02}}
    # TM hạng 1 (rrf cao nhất) → trong top-3 mặc định (HIDDEN_TOP_K=3) → báo.
    assert rt._hidden_in_top_k(fused, CHI_ALL) == frozenset({"commercial"})
    assert rt._hidden_in_top_k({2: {"row": ALL, "rrf": 0.02}}, CHI_ALL) == frozenset()
    assert rt._hidden_in_top_k({}, CHI_ALL) == frozenset()
    assert rt._hidden_in_top_k(fused, frozenset({"all", "commercial"})) == frozenset()
    # Biên k tại chính hàm thuần (đối chứng cho 2 test đột biến bắt buộc của
    # task 9 chạy qua retrieve()): TM hạng 4 (rrf thấp nhất) → NGOÀI top-3 mặc
    # định → không báo; nhưng báo lại nếu gọi tường minh với k=4.
    fused_hang_4 = {1: {"row": ALL, "rrf": 0.05}, 2: {"row": ALL2, "rrf": 0.04},
                    3: {"row": ALL3, "rrf": 0.03}, 4: {"row": TM, "rrf": 0.02}}
    assert rt._hidden_in_top_k(fused_hang_4, CHI_ALL) == frozenset()
    assert rt._hidden_in_top_k(fused_hang_4, CHI_ALL, k=4) == frozenset({"commercial"})


def test_hidden_in_top_k_voi_sentinel_thi_no_to():
    """Cổng hợp đồng thường trực (G1-c vòng sửa 2 của Task 1, GIỮ NGUYÊN qua
    đổi luật Task 9 — chỉ đổi tên hàm/test theo `_hidden_in_top_k`). Biến tiền
    điều kiện F5 (docstring) thành một cổng CI thật. `visibility` PHẢI là
    frozenset đã resolve — gọi với sentinel `UNRESTRICTED` phải NỔ `TypeError`,
    không được lặng lẽ trả `frozenset()`. `fused` phải KHÁC RỖNG, nếu không
    hàm trả sớm ở nhánh `if not fused` trước khi chạm `cls not in visibility`
    — test sẽ đúng-rỗng (vacuous)."""
    fused = {1: {"row": TM, "rrf": 0.03}}
    with pytest.raises(TypeError):
        rt._hidden_in_top_k(fused, UNRESTRICTED)


def test_vis_idx_khop_voi_cot_that():
    """Cổng tất định, không cần DB (F2 vòng sửa 1): `VIS_IDX` phải trỏ đúng cột
    `c.visibility` trong CHUỖI `_COLS` THẬT của production — không chỉ trong
    hàng `_row()` dựng tay ở trên. Nếu sau này ai đổi thứ tự `_COLS` mà quên
    sửa `VIS_IDX`, các test khác ở trên vẫn xanh (vì `_row()` không đọc
    `_COLS`) trong khi production đọc nhầm cột và báo ra một tên lớp bậy —
    đúng lằn "fixture khác trường thật" đã cắn repo này một lần."""
    assert [c.strip() for c in rt._COLS.split(",")][rt.VIS_IDX] == "c.visibility"


class _ConnBongLoi:
    """Mô phỏng lỗi DB CHỈ ở lượt bóng (không lọc) — lượt LỌC vẫn chạy bình
    thường, y hệt tình huống F3 (vòng sửa 1) mô tả."""

    def __init__(self, visible):
        self.visible = visible

    def execute(self, sql, params=None):
        if VIS_CLAUSE in sql:
            return _Cur(self.visible)
        raise RuntimeError("DB lỗi giả lập ở lượt bóng")


def test_loi_luot_bong_khong_giet_ket_qua_da_loc(khong_ra_ngoai):
    """F3 (vòng sửa 1): lượt bóng hỏng không được giết một retrieval ĐÃ lọc
    SQL thành công — fail-open, giống cách `rerank()` đã fail-open."""
    conn = _ConnBongLoi(visible=[ALL])
    r = rt.retrieve("chiết khấu", conn=conn, visibility=CHI_ALL)
    # BẤT BIẾN: lỗi lượt bóng không vứt bỏ chunks đã lọc SQL thành công.
    assert [c.source_file for c in r.chunks] == ["seed/policy.docx"]
    # Fail-open: mất tín hiệu TƯ VẤN hidden_classes, không mất kết quả.
    assert r.hidden_classes == frozenset()


# ─── Integration: DB thật ──────────────────────────────────────────────────

from src.rag.chunking import fold_vi
from src.rag.ingest import segment_vi
from tests.rag.test_retrieve_visibility import _DIM, _nap_hai_tai_lieu, _vec
from src.rag.visibility import UNRESTRICTED as _UNR


def _truc(hot: int):
    v = [0.0] * _DIM
    v[hot] = 1.0
    return v


def _truc_trong_so(trong_so: dict[int, float]) -> list[float]:
    """Vector giả với NHIỀU trục có trọng số khác nhau — khác `_truc()` (một
    trục, trọng số 1.0). Vì tài liệu fixture là vector đơn vị trực giao
    (`_vec`), tích vô hướng query·doc_i = trọng_số[i]; hạng dense của 4 tài
    liệu do đó do CHÍNH trọng số này quyết, tất định, không may rủi."""
    v = [0.0] * _DIM
    for idx, w in trong_so.items():
        v[idx] = w
    return v


def _nap_them_all(conn, mota: list[str], hot_bat_dau: int = 2):
    """Nạp thêm chunk lớp 'all' để bản bóng có ≥4 hàng (Task 9) — cần để biểu
    diễn được biên top-3 trên DB THẬT: `_nap_hai_tai_lieu` (thuộc 19b) chỉ nạp
    2 tài liệu, và với đúng 2 hàng thì top-3 LUÔN chứa cả hai — không còn ca
    nào diễn tả được "bị giấu NGOÀI top-k". Viết RIÊNG tại đây; KHÔNG sửa
    `_nap_hai_tai_lieu`."""
    for i, text in enumerate(mota):
        hot = hot_bat_dau + i
        doc_id = f"d-all-them-{i}"
        src = f"seed/them_{i}.docx"
        conn.execute(
            "INSERT INTO rag_documents (doc_id, source_file, content_hash) "
            "VALUES (%s, %s, %s)", (doc_id, src, doc_id))
        conn.execute(
            "INSERT INTO rag_chunks (doc_id, source_file, chunk_text, visibility, "
            "embedding, ts_vector, chunk_text_fold) "
            "VALUES (%s, %s, %s, %s, %s::vector, to_tsvector('simple', %s), %s)",
            (doc_id, src, text, "all", _vec(hot), segment_vi(text), fold_vi(text)))


# 2 văn bản 'all' THÊM cho bản bóng sâu — chủ đề khác hẳn "chiết khấu"/"hoàn
# hàng" của `_nap_hai_tai_lieu`, và khác hẳn câu hỏi `_CAU_HOI_SAU` bên dưới,
# để không tài liệu nào vô tình khớp chân sparse/fold.
_MOTA_THEM = [
    "Quy định bảo trì thiết bị văn phòng mỗi quý.",
    "Đăng ký tài khoản nội bộ cho nhân viên mới.",
]

# Câu hỏi KHÔNG chung MỘT từ nào (kể cả sau bỏ dấu) với 4 văn bản fixture —
# xác nhận bằng probe THẬT trên Postgres (không đoán): sparse=None và
# fold=None ở CẢ BỐN hàng (`fold_gop=False`), nên dense là chân DUY NHẤT
# quyết định thứ hạng và biên k không phụ thuộc may rủi hoà điểm.
_CAU_HOI_SAU = "phần mềm quản lý dự án ra mắt bản thử nghiệm"


@pytest.mark.integration
def test_ca_thuan_commercial_hang_1_thi_bao(clean_tables, monkeypatch):
    """Câu hỏi "bậc cộng trần" — CỐ Ý không dùng "chiết khấu": từ đó nằm ở CẢ
    HAI tài liệu fixture (xem `_nap_hai_tai_lieu`), nên chân sparse/fold sẽ
    hoà điểm và hạng-1 của bản bóng rơi vào tay thứ tự vật lý/kế hoạch không
    xác định (đúng như `test_retrieve_visibility.py:196-200` đã cảnh báo cho
    cặp fixture này) — kiểm thực nghiệm: đảo thứ tự INSERT trong
    `_nap_hai_tai_lieu` khiến bản test dùng "chiết khấu" LẬT ĐỎ dù code không
    hồi quy gì (xem task-5-report.md, mục "Vòng sửa 1"). "bậc", "cộng", "trần"
    chỉ xuất hiện trong văn bản 'commercial', không có trong văn bản 'all' —
    đã xác nhận bằng to_tsvector/to_tsquery thật trên Postgres (không đoán
    bằng mắt): sparse/fold của bản bóng chỉ khớp chunk commercial, dense
    (được steer bằng embed_query giả) cũng nghiêng về commercial — cả BA chân
    đồng thuận, hạng-1 không phụ thuộc tie-break."""
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))   # gần chunk commercial
    r = rt.retrieve("bậc cộng trần", conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    assert {c.source_file for c in r.chunks} == {"seed/policy.docx"}   # vẫn lọc


@pytest.mark.integration
def test_ca_thuan_sau_commercial_hang_3_thi_bao(clean_tables, monkeypatch):
    """Case THUẬN với bản bóng SÂU 4 hàng (Task 9): TM đứng hạng 3 → NẰM
    TRONG top-3 → báo. Thứ hạng THẬT quan sát được bằng probe trên Postgres
    thật (kịch bản y hệt, chỉ đổi trọng số — dán ở task-9-report.md):
        hạng 1  d-all           dense 0.801
        hạng 2  d-all-them-0    dense 0.534
        hạng 3  d-tm            dense 0.267   ← commercial, TRONG top-3
        hạng 4  d-all-them-1    dense 0.044
    sparse=None và fold=None ở CẢ BỐN hàng (`fold_gop=False`) — không hoà
    điểm may rủi, dense một mình quyết định thứ hạng."""
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    _nap_them_all(conn, _MOTA_THEM)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query",
                         lambda q: _truc_trong_so({1: 0.9, 2: 0.6, 0: 0.3, 3: 0.05}))
    r = rt.retrieve(_CAU_HOI_SAU, conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset({"commercial"})
    # BẤT BIẾN chống rò rỉ vẫn đúng ở độ sâu 4 hàng: không hàng thương mại nào lọt ra.
    assert {c.source_file for c in r.chunks} == {
        "seed/policy.docx", "seed/them_0.docx", "seed/them_1.docx"}


@pytest.mark.integration
def test_ca_nguoc_sau_commercial_ngoai_top3_thi_khong_bao(clean_tables, monkeypatch):
    """Case NGHỊCH MỚI (Task 9) — THAY THẾ `test_ca_nguoc_all_hang_1_thi_khong_bao`
    cũ: fixture 2 tài liệu của 19b không còn diễn tả được gì dưới luật top-3
    (đúng 2 hàng thì top-3 LUÔN chứa cả hai, nên tài liệu thương mại luôn được
    xem là "trong top-k" bất kể thứ hạng — test cũ sẽ ĐỎ sau khi đổi luật,
    đúng như task-9-brief đã cảnh báo). Nạp thêm 2 chunk 'all' (`_nap_them_all`,
    viết riêng ở trên, không sửa `_nap_hai_tai_lieu`) để có đủ 4 hàng, đủ để
    TM tụt xuống hạng 4 — NGOÀI top-3 → không báo.

    Thứ hạng THẬT quan sát được bằng probe trên Postgres thật (dán ở
    task-9-report.md):
        hạng 1  d-all           dense 0.801
        hạng 2  d-all-them-0    dense 0.534
        hạng 3  d-all-them-1    dense 0.267
        hạng 4  d-tm            dense 0.044   ← commercial, NGOÀI top-3
    sparse=None và fold=None ở CẢ BỐN hàng — câu hỏi `_CAU_HOI_SAU` cố ý không
    chung một từ nào (kể cả sau bỏ dấu) với 4 văn bản fixture, nên dense là
    chân DUY NHẤT quyết định thứ hạng, không phụ thuộc may rủi hoà điểm."""
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    _nap_them_all(conn, _MOTA_THEM)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query",
                         lambda q: _truc_trong_so({1: 0.9, 2: 0.6, 3: 0.3, 0: 0.05}))
    r = rt.retrieve(_CAU_HOI_SAU, conn=conn, visibility=CHI_ALL)
    assert r.hidden_classes == frozenset()
    assert r.chunks, "fixture sai — không có ứng viên thì test tự vô hiệu"


@pytest.mark.integration
def test_admin_khong_bao_va_thay_ca_hai(clean_tables, monkeypatch):
    conn = clean_tables
    _nap_hai_tai_lieu(conn)
    monkeypatch.setenv("RAG_FOLD_ENABLED", "1")
    monkeypatch.setattr(rt, "embed_query", lambda q: _truc(0))
    r = rt.retrieve("chiết khấu", conn=conn, visibility=_UNR)
    assert r.hidden_classes == frozenset()
    assert {c.source_file for c in r.chunks} == {"seed\\discount_policy.docx", "seed/policy.docx"}
