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
from .ingest_report import IngestReport, Rejection
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
DOCUMENT_EXT = frozenset(_EXT) | {
    ".doc", ".xls", ".ppt",          # định dạng cũ, cần LibreOffice
    ".rtf", ".odt", ".ods", ".odp",  # định dạng khác LibreOffice đọc được
    ".pptx",                          # có parser riêng, xem Task 4
}


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


def _chunks_for(path: str, kind: str, doc_id: str) -> list[dict]:
    if kind == "xlsx":
        return chunk_xlsx_sheets(parse_xlsx(path), doc_id=doc_id, source_file=path)
    low = path.lower()
    if low.endswith(".pdf"):
        blocks = parse_pdf(path)
    elif low.endswith(".pptx"):
        blocks = parse_pptx(path)
    else:
        blocks = parse_docx(path)
    if not blocks:
        return []
    return chunk_text_blocks(blocks, doc_id=doc_id, source_file=path)


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

    chunks = _chunks_for(path, kind, doc_id)
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
            (doc_id, path, content_hash, eff),
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
    return IngestReport(ingested=1, chunks=len(chunks))


def ingest_path(path: str, conn=None) -> IngestReport:
    own = conn is None
    if own:
        conn = _db.connect()
        _db.ensure_schema(conn, RAG_SCHEMA)
    try:
        # Ghi marker nếu chưa có — để lần khởi động sau assert_embedding_marker()
        # bắt được cú đổi provider mà không re-index.
        e = get_embedder()
        conn.execute(
            "INSERT INTO rag_embedding_marker (embedding_model, dim) "
            "SELECT %s, %s WHERE NOT EXISTS (SELECT 1 FROM rag_embedding_marker)",
            (e.model_name, e.dim))
        report = IngestReport()
        files = ([path] if os.path.isfile(path)
                 else [os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs])
        for f in files:
            report.merge(_ingest_file(f, conn))
        return report
    finally:
        if own:
            conn.close()


def main() -> None:
    use_utf8_streams()
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOCUMENTS_PATH", ".")
    report = ingest_path(target)
    print(report.render())
    # Thoát khác 0 khi có tài liệu bị từ chối: một lượt nạp bỏ sót tài liệu
    # KHÔNG phải là một lượt nạp thành công, và người gọi (script, CI) phải
    # biết được điều đó mà không cần đọc chữ.
    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
