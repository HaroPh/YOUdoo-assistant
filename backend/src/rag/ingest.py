import hashlib
import os
import sys

from pyvi import ViTokenizer

from . import db as _db
from .config import RAG_SCHEMA
from .embed import EmbeddingError, embed_texts, get_embedder
from .parse import (extract_effective_date, parse_docx, parse_pdf,
                    parse_pptx, parse_xlsx)
from .chunking import chunk_text_blocks, chunk_xlsx_sheets, index_text
from .ingest_report import IngestReport, Rejection, Warning
from src.cli_console import use_utf8_streams

# Đuôi nạp được TRỰC TIẾP → loại parser.
_EXT = {
    ".pdf": "text",
    ".docx": "text",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",     # sổ kế toán Việt Nam gần như luôn là .xlsm (có macro)
    ".xltx": "xlsx",
    ".pptx": "pptx",
}

# Đuôi ĐƯỢC COI LÀ TÀI LIỆU — rộng hơn `_EXT`. Tệp mang đuôi ở đây mà không
# nạp được thì phải bị TỪ CHỐI CÓ TÊN, không được im lặng.
#
# Vì sao cần hai danh sách: trước 2026-08-30 chỉ có `_EXT`, nên `.doc` và
# `.gitkeep` rơi vào cùng một nhánh "đuôi lạ, bỏ qua". Một cái là rác trong
# thư mục, cái kia là quy chế công ty biến mất khỏi corpus.
#
# LIÊN TỤC LIỆT KÊ ĐỦ, KHÔNG suy ra từ `_EXT`. Bản trước viết
# `frozenset(_EXT) | {...}`, và vì thế bất biến `set(_EXT) <= DOCUMENT_EXT`
# ĐÚNG THEO ĐỊNH NGHĨA — nó không gác được gì. Đo 2026-08-31: thêm
# `".epub": "text"` vào `_EXT` (đúng kịch bản docstring của test nói phải
# chặn) thì test VẪN XANH. Danh sách độc lập làm bất biến đó có nghĩa trở lại:
# thêm một đuôi nạp được mà quên khai nó là tài liệu thì test ĐỎ.
DOCUMENT_EXT = frozenset({
    # nạp được TRỰC TIẾP — phải khớp với `_EXT` ở trên
    ".pdf", ".docx", ".xlsx", ".xlsm", ".xltx", ".pptx",
    # định dạng cũ, cần LibreOffice
    ".doc", ".xls", ".ppt",
    # định dạng khác LibreOffice đọc được
    ".rtf", ".odt", ".ods", ".odp",
})


class IngestError(RuntimeError):
    """Tệp được nhận nhưng không sinh được chunk nào.

    Trước 2026-08-19 ca này trả {"skipped": 1} im lặng, nên một PDF scan
    (không có lớp text) vắng mặt khỏi corpus mà không ai biết — cùng lớp lỗi
    với reranker chết im lặng 6 tuần. Hỏng lớn tiếng còn hơn thiếu âm thầm."""


def segment_vi(text: str) -> str:
    """pyvi word segmentation; the SAME transform is used at ingest and query time."""
    return ViTokenizer.tokenize(text)


def _hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _doc_id(path: str) -> str:
    """Stable document identity, independent of the process's CWD at call
    time — os.path.relpath(path) resolves against os.getcwd(), so the same
    file ingested from two different working directories (e.g. repo root vs.
    backend/) would get two different doc_ids and duplicate every chunk."""
    return os.path.abspath(path).replace("\\", "/")


def _chunks_for(read_path: str, kind: str, doc_id: str,
                source_file: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """`read_path` là tệp ĐỌC nội dung (có thể là bản đã chuyển đổi trong
    thư mục cache tạm); `source_file` là tệp GỐC người dùng đưa vào.

    HAI THAM SỐ TÁCH RỜI, không phải một. Trước 2026-08-31 chỉ có một tham
    số và nó vừa dùng để đọc vừa dùng làm nhãn, nên tệp `.doc/.xls/.ppt` ghi
    ĐƯỜNG DẪN CACHE TẠM vào `source_file` — một chuỗi chứa content_hash, ĐỔI
    mỗi lần tài liệu đổi và KHÁC NHAU giữa các máy.

    Chuỗi đó từng chảy tiếp vào embedding qua `chunking.py` (doc_title lùi về
    source_file → crumb lùi về doc_title → `index_text()`). Nhánh đó đã bị
    CẮT 2026-09-04 (B3): `crumb` không còn lùi về `doc_title` nữa. Việc tách
    hai tham số ở đây vẫn cần — `source_file` là nhãn người dùng thấy, và nó
    phải là tệp GỐC dù đường rò kia đã đóng."""
    if kind == "xlsx":
        sheets, sheet_warnings = parse_xlsx(read_path)
        return (chunk_xlsx_sheets(sheets, doc_id=doc_id, source_file=source_file),
                sheet_warnings)
    low = read_path.lower()
    if low.endswith(".pdf"):
        blocks, pdf_warnings = parse_pdf(read_path)
    elif low.endswith(".pptx"):
        blocks, pdf_warnings = parse_pptx(read_path), []
    else:
        blocks, pdf_warnings = parse_docx(read_path), []
    if not blocks:
        return [], []
    return (chunk_text_blocks(blocks, doc_id=doc_id, source_file=source_file),
            pdf_warnings)


def _ingest_file(path: str, conn) -> IngestReport:
    ext = os.path.splitext(path)[1].lower()
    kind = _EXT.get(ext)
    if kind is None:
        if ext not in DOCUMENT_EXT:
            return IngestReport()          # không phải tài liệu — im lặng ĐÚNG
        return _ingest_convertible(path, ext, conn)
    return _ingest_known(path, kind, conn)


def _ingest_convertible(path: str, ext: str, conn) -> IngestReport:
    """Định dạng cũ: chuyển sang đuôi hiện đại rồi nạp bản đã chuyển.

    `doc_id` giữ nguyên theo tệp GỐC, không theo bản đã chuyển — nếu không,
    cùng một quy chế sẽ có hai doc_id khi bộ chuyển đổi đổi thư mục cache."""
    from . import convert
    try:
        converted = convert.convert_file(path, _hash(path))
    except (convert.ConverterMissing, convert.ConvertFailed) as e:
        return IngestReport(rejected=[Rejection(path, str(e))])

    kind = _EXT.get(os.path.splitext(converted)[1].lower())
    if kind is None:
        return IngestReport(rejected=[Rejection(
            path, f"đã chuyển thành {converted} nhưng đuôi đó vẫn không nạp được")])
    return _ingest_known(converted, kind, conn, doc_id_source=path)


def _ingest_known(path: str, kind: str, conn,
                  doc_id_source: str | None = None) -> IngestReport:
    """`path` là tệp ĐỌC được (có thể là bản đã chuyển đổi).
    `doc_id_source` là tệp GỐC người dùng đưa vào — dùng cho định danh và
    content_hash, để một quy chế `.doc` không đổi doc_id mỗi lần thư mục
    cache chuyển đổi thay đổi."""
    origin = doc_id_source or path
    doc_id, content_hash = _doc_id(origin), _hash(origin)
    existing = conn.execute(
        "SELECT content_hash FROM rag_documents WHERE doc_id = %s", (doc_id,)
    ).fetchone()
    if existing and existing[0] == content_hash:
        return IngestReport(unchanged=1)

    # `path` CHỈ để đọc nội dung; mọi nhãn ghi ra ngoài dùng `origin`.
    chunks, sheet_warnings = _chunks_for(path, kind, doc_id, source_file=origin)
    if not chunks:
        raise IngestError(
            f"{path}: tệp được nhận ({kind}) nhưng không sinh được chunk nào. "
            f"Với PDF, nguyên nhân thường gặp là bản scan không có lớp text — "
            f"cần OCR trước khi ingest. KHÔNG bỏ qua âm thầm: tài liệu sẽ vắng "
            f"mặt khỏi corpus mà không ai biết.")

    # Embed BEFORE any DB write — if Ollama is down no orphan rows are created
    # Embed/ts_vector trên crumb + body (index_text) — tìm được theo heading
    # ("Điều 124") dù nó chỉ nằm trong section_path; chunk_text lưu DB vẫn
    # body-only (spec 2026-07-15 §3C).
    vectors = embed_texts([index_text(c["section_path"], c["chunk_text"])
                           for c in chunks])

    with conn.transaction():
        if existing:
            conn.execute("DELETE FROM rag_documents WHERE doc_id = %s", (doc_id,))  # cascade
        # Ngày hiệu lực trích từ TOÀN VĂN, không từ riêng chunk nào: điều
        # khoản thi hành nằm gần cuối văn bản và rơi vào chunk nào là tuỳ tệp.
        # NULL là hợp lệ — 8/17 tài liệu trong corpus là tài liệu nghiệp vụ
        # (.docx/.xlsx), không phải văn bản quy phạm nên không có ngày.
        eff = extract_effective_date(" ".join(c["chunk_text"] for c in chunks))
        conn.execute(
            "INSERT INTO rag_documents (doc_id, source_file, content_hash, "
            "effective_date) VALUES (%s, %s, %s, %s)",
            (doc_id, origin, content_hash, eff),
        )
        for c, vec in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO rag_chunks (doc_id, source_file, doc_title, section_path, page, "
                "sheet, row_range, columns, chunk_index, token_count, chunk_text, embedding, "
                "ts_vector) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, "
                "to_tsvector('simple', %s))",
                (c["doc_id"], c["source_file"], c["doc_title"], c["section_path"], c["page"],
                 c["sheet"], c["row_range"], c["columns"], c["chunk_index"], c["token_count"],
                 c["chunk_text"], vec,
                 segment_vi(index_text(c["section_path"], c["chunk_text"]))),
            )
    report = IngestReport(ingested=1, chunks=len(chunks))
    for sheet, reason in sheet_warnings:
        report.warnings.append(Warning(origin, sheet, reason))
    return report


class IngestTargetMissing(IngestError):
    """Đường dẫn đích của cả LƯỢT NẠP không tồn tại.

    Trước 2026-08-31 `ingest_path("d:/khong/he/ton/tai")` trả
    `IngestReport(0, 0, 0, [])` với `ok=True` và `main()` thoát 0: gõ sai
    đường dẫn cho ra một BÁO CÁO THÀNH CÔNG. Đó là mâu thuẫn nội tại — chính
    hình dạng "0 mọi thứ, ok=True" đã được `test_ingest_kho_that.py` gọi tên
    là IM_LANG khi nó xảy ra với một TỆP, rồi lại được chấp nhận khi nó xảy
    ra với cả LƯỢT.

    Thư mục CÓ THẬT mà không chứa tài liệu nào thì KHÔNG phải lỗi (thư mục
    rỗng là hợp lệ) — `render()` nói rõ là không thấy tài liệu nào."""


def ingest_path(path: str, conn=None) -> IngestReport:
    if not os.path.exists(path):
        raise IngestTargetMissing(
            f"{path}: đường dẫn không tồn tại. Không có gì được nạp — đây là "
            f"lỗi của lượt chạy, không phải một lượt nạp thành công với 0 tệp.")
    own = conn is None
    if own:
        conn = _db.connect()
        _db.ensure_schema(conn, RAG_SCHEMA)
    try:
        # Ghi marker nếu chưa có — để lần khởi động sau assert_embedding_marker()
        # bắt được cú đổi provider mà không re-index.
        embedder = get_embedder()
        conn.execute(
            "INSERT INTO rag_embedding_marker (embedding_model, dim) "
            "SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM rag_embedding_marker)",
            (embedder.model_name, embedder.dim))
        report = IngestReport()
        files = ([path] if os.path.isfile(path)
                 else [os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs])
        for f in files:
            try:
                report.merge(_ingest_file(f, conn))
            except EmbeddingError:
                # NGOẠI LỆ CỦA LÁ CHẮN. Embedder chết là hỏng HẠ TẦNG, không
                # phải khiếm khuyết của tệp này: biến nó thành `rejected` sẽ
                # cho ra một báo cáo "117 tài liệu bị từ chối" trong khi sự
                # thật là "Ollama không chạy" — che đúng nguyên nhân và đổ lỗi
                # cho tài liệu của người dùng. Để nó nổ, và nổ ngay tệp đầu.
                raise
            except Exception as e:
                # LÁ CHẮN MỘT TỆP — spec 2026-08-29 mục 4: MỖI tệp phải ra ở
                # đúng một trong ba trạng thái, và "PDF không lớp text, parse
                # ra rỗng" được nêu ĐÍCH DANH là nguyên nhân `rejected`. Trước
                # 2026-08-31 `IngestError` (và PackageNotFoundError của .docx
                # hỏng/khoá mật khẩu, InvalidFileException/BadZipFile của
                # .xlsx, NotImplementedError của .pptx) không ai bắt: một tệp
                # hỏng làm SẬP TRỌN lượt nạp và xoá sạch báo cáo của mọi tệp
                # đã xử lý trước đó — tức là để đóng một lỗi "mất im lặng" ta
                # lại mất báo cáo của tất cả những tệp khác.
                #
                # KHÔNG nuốt ngoại lệ: loại lỗi và thông điệp đi vào lý do
                # từ chối, hiện trong `render()` và làm `main()` thoát khác 0.
                report.merge(IngestReport(rejected=[
                    Rejection(f, f"{type(e).__name__}: {e}")]))
        return report
    finally:
        if own:
            conn.close()


def main() -> None:
    use_utf8_streams()
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOCUMENTS_PATH", ".")
    try:
        report = ingest_path(target)
    except IngestTargetMissing as e:
        # To tiếng nhưng ĐỌC ĐƯỢC: một dòng nói rõ chuyện gì, không phải
        # traceback, và vẫn thoát khác 0.
        print(f"LỖI  {e}")
        sys.exit(1)
    print(report.render())
    # Thoát khác 0 khi có tài liệu bị từ chối: một lượt nạp bỏ sót tài liệu
    # KHÔNG phải là một lượt nạp thành công, và người gọi (script, CI) phải
    # biết được điều đó mà không cần đọc chữ.
    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
