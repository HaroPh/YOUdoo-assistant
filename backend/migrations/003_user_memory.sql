-- Ký ức xuyên phiên, tầng fact bền (spec 2026-08-19 §4).
-- APPEND-ONLY: không bao giờ UPDATE fact_value, không bao giờ DELETE.
-- Sửa/gỡ đều là chèn dòng mới + đánh dấu dòng cũ superseded_by.
CREATE TABLE IF NOT EXISTS user_memory (
    id            bigserial PRIMARY KEY,
    user_id       text        NOT NULL,
    fact_key      text        NOT NULL,
    fact_value    text        NOT NULL,
    thread_id     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    superseded_by bigint      REFERENCES user_memory(id),
    superseded_at timestamptz
);

CREATE INDEX IF NOT EXISTS user_memory_active
    ON user_memory (user_id) WHERE superseded_by IS NULL;
