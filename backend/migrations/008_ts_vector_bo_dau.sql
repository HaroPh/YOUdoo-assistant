-- 008: chân từ vựng BỎ DẤU cho truy xuất tiếng Việt.
--
-- Vì sao: đo 2026-09-08 trên bộ vàng 64 ca, truy vấn gõ KHÔNG DẤU cho
-- recall@20 = 1/64 = 0,0156 — và trả về SAI HẲN chứ không phải rỗng. Người
-- dùng thật có gõ không dấu. Thêm chân RRF khớp mặt chữ trên text đã bỏ dấu
-- đưa số đó lên 0,6406, và nửa dấu 0,8594 -> 0,9219, đổi lấy 1 ca có dấu.
--
-- `chunk_text_fold` do Python ghi (xem `chunking.fold_vi`) chứ không dùng
-- extension `unaccent`: unaccent không map đ/Đ -> d/D, mà đó là chữ cái riêng
-- trong tiếng Việt, bỏ sót là hỏng một phần đáng kể.
--
-- Idempotent. Chạy tay, theo lệ của thư mục này.
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS chunk_text_fold text;

ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS ts_vector_fold tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk_text_fold, '')))
    STORED;

CREATE INDEX IF NOT EXISTS rag_chunks_ts_fold_gin
    ON rag_chunks USING gin (ts_vector_fold);
