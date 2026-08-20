CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.rag_documents (
    doc_id        text PRIMARY KEY,
    source_file   text NOT NULL,
    content_hash  text NOT NULL,
    lang          text NOT NULL DEFAULT 'vi',
    -- Ngày hiệu lực của văn bản. NULL hợp lệ (tài liệu nghiệp vụ không có).
    -- Xem migrations/003_effective_date.sql cho lý do đầy đủ. CREATE TABLE ở
    -- đây dùng cho DB dựng MỚI; migration 003 vá DB đã tồn tại. Hai chỗ phải
    -- khớp nhau — thiếu ở đây thì mọi test integration dựng bảng sạch sẽ đỏ
    -- ngay, đó chính là cách khoảng lệch này bị bắt.
    effective_date date,
    ingested_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.rag_chunks (
    id            bigserial PRIMARY KEY,
    doc_id        text NOT NULL REFERENCES {schema}.rag_documents(doc_id) ON DELETE CASCADE,
    source_file   text NOT NULL,
    doc_title     text NOT NULL DEFAULT '',
    section_path  text,
    page          int,
    sheet         text,
    row_range     text,
    columns       text[],
    chunk_index   int NOT NULL DEFAULT 0,
    token_count   int NOT NULL DEFAULT 0,
    visibility    text NOT NULL DEFAULT 'all',
    chunk_text    text NOT NULL,
    embedding     vector({dim}),
    ts_vector     tsvector
);

CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw
    ON {schema}.rag_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS rag_chunks_ts_gin
    ON {schema}.rag_chunks USING gin (ts_vector);
CREATE INDEX IF NOT EXISTS rag_chunks_doc_id
    ON {schema}.rag_chunks (doc_id);

-- Marker chống lệch embedding (spec SP-1B §3b). Một hàng duy nhất, ghi lúc
-- index. Provider đang bật lệch với hàng này → app không lên (embed.py
-- assert_embedding_marker). Vector bge-m3 và vector Gemini nằm ở hai không gian
-- khác nhau; truy vấn chéo trả rác mà không báo lỗi.
CREATE TABLE IF NOT EXISTS {schema}.rag_embedding_marker (
    embedding_model text    NOT NULL,
    dim             integer NOT NULL
);
