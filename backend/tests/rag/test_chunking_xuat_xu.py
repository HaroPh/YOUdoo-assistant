import contextlib

from src.rag import ingest as ingest_mod
from src.rag.chunking import chunk_text_blocks


def test_block_khong_khai_gi_thi_chunk_la_text_conf_None():
    blocks = [{"text": "Câu thường.", "heading_level": None, "page": 1}]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["source_kind"] == "text"
    assert out[0]["ocr_conf"] is None


def test_mot_block_ocr_lam_ca_chunk_thanh_ocr():
    # BI QUAN: trộn text sạch với text đọc từ ảnh thì cả chunk chỉ đáng tin
    # bằng phần yếu nhất của nó — không được làm tròn lên (spec §8).
    blocks = [
        {"text": "Câu sạch.", "heading_level": None, "page": 1},
        {"text": "Câu từ ảnh.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 88.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert len(out) == 1
    assert out[0]["source_kind"] == "ocr"
    assert out[0]["ocr_conf"] == 88.0


def test_nhieu_block_ocr_thi_conf_lay_NHO_NHAT():
    blocks = [
        {"text": "A.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 95.0},
        {"text": "B.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 61.5},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["ocr_conf"] == 61.5


def test_bac_thap_nhat_thang_ke_ca_khi_dung_sau():
    blocks = [
        {"text": "A.", "heading_level": None, "page": 1,
         "source_kind": "vision_description"},
        {"text": "B.", "heading_level": None, "page": 1,
         "source_kind": "ocr", "ocr_conf": 90.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    assert out[0]["source_kind"] == "vision_description"


def test_block_atomic_giu_xuat_xu_cua_RIENG_no():
    # Hàng bảng là chunk riêng (B4) — nó không được "lây" xuất xứ của văn xuôi
    # đứng cạnh, và văn xuôi cũng không được lây của nó.
    blocks = [
        {"text": "Văn xuôi sạch.", "heading_level": None, "page": 1},
        {"text": "Cột 1: X | Cột 2: Y", "heading_level": None, "page": 1,
         "atomic": True, "source_kind": "ocr", "ocr_conf": 70.0},
    ]
    out = chunk_text_blocks(blocks, doc_id="d", source_file="f.pdf")
    theo_text = {c["chunk_text"]: c for c in out}
    assert theo_text["Văn xuôi sạch."]["source_kind"] == "text"
    assert theo_text["Cột 1: X | Cột 2: Y"]["source_kind"] == "ocr"
    assert theo_text["Cột 1: X | Cột 2: Y"]["ocr_conf"] == 70.0


class _FakeResult:
    """Đứng thay cho kết quả `conn.execute(...)` — chỉ `_ingest_known` gọi
    `.fetchone()` (SELECT content_hash), luôn trả None (không có doc cũ)."""

    def fetchone(self):
        return None


class _FakeConn:
    """`conn` giả cho `_ingest_known`: không chạm DB thật, chỉ ghi lại mọi
    câu SQL + tham số của `.execute(...)` để test soi đúng câu INSERT sinh
    ra, thay vì soi mã nguồn (không chứng minh hành vi nào)."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _FakeResult()

    def transaction(self):
        return contextlib.nullcontext()


def _cot_va_gia_tri(sql: str, params: tuple, ten_cot: str):
    """Vị trí của `ten_cot` trong danh sách cột `INSERT INTO ... (a, b, c) VALUES`
    và giá trị tham số cùng vị trí đó — tránh giả định thứ tự cột cố định."""
    cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
    return params[cols.index(ten_cot)]


def test_INSERT_co_hai_cot_moi_va_chiu_duoc_chunk_thieu_khoa(tmp_path, monkeypatch):
    # Một chunk CÓ khai source_kind/ocr_conf (hình dạng Task 4 sẽ tạo ra từ
    # trang đọc bằng ảnh) và một chunk KHÔNG khai gì (hình dạng THẬT của
    # chunk_xlsx_sheets hôm nay) phải cùng đi qua được INSERT — không được để
    # đường .xlsx vỡ vì KeyError.
    chunk_co_khoa = {
        "doc_id": "d", "source_file": "f.pdf", "doc_title": "f", "section_path": None,
        "page": 1, "sheet": None, "row_range": None, "columns": None,
        "chunk_index": 0, "token_count": 3, "chunk_text": "A.",
        "source_kind": "ocr", "ocr_conf": 77.0,
    }
    chunk_khong_khoa = {
        "doc_id": "d", "source_file": "f.pdf", "doc_title": "f", "section_path": None,
        "page": None, "sheet": "Sheet1", "row_range": "row 1", "columns": ["x"],
        "chunk_index": 1, "token_count": 2, "chunk_text": "B.",
        # KHÔNG có source_kind/ocr_conf — đúng hình dạng chunk_xlsx_sheets.
    }
    monkeypatch.setattr(ingest_mod, "parse_pdf",
                         lambda path: ([{"text": "x", "heading_level": None, "page": 1}], []))
    monkeypatch.setattr(ingest_mod, "chunk_text_blocks",
                         lambda *a, **k: [chunk_co_khoa, chunk_khong_khoa])
    monkeypatch.setattr(ingest_mod, "embed_texts", lambda texts: [[0.0]] * len(texts))

    real_file = tmp_path / "f.pdf"
    real_file.write_bytes(b"noi dung gia, chi de tinh hash")

    conn = _FakeConn()
    report = ingest_mod._ingest_known(str(real_file), "text", conn)

    assert report.ingested == 1
    assert report.chunks == 2

    insert_chunk_calls = [c for c in conn.calls if c[0].startswith("INSERT INTO rag_chunks")]
    assert len(insert_chunk_calls) == 2

    sql0, params0 = insert_chunk_calls[0]
    assert "source_kind" in sql0 and "ocr_conf" in sql0
    assert _cot_va_gia_tri(sql0, params0, "source_kind") == "ocr"
    assert _cot_va_gia_tri(sql0, params0, "ocr_conf") == 77.0

    sql1, params1 = insert_chunk_calls[1]
    assert _cot_va_gia_tri(sql1, params1, "source_kind") == "text"
    assert _cot_va_gia_tri(sql1, params1, "ocr_conf") is None
