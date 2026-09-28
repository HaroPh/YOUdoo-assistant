-- Nhật ký MỌI lượt gọi VLM (OCR bậc 3) — spec: quyết định chủ dự án 2026-09-28.
--
-- VLM dùng CHUNG ví Gemini với chatbot (đo 2026-09-28: 3/3 khoá
-- YOUDOO_VLM_API_KEY* trùng GOOGLE_API_KEY*). Chủ dự án chấp nhận điều đó với
-- điều kiện mọi lượt gọi đều được ghi. `llm_usage` chỉ ghi lượt THÀNH CÔNG và
-- phải giữ nguyên như vậy: `usage_since` đếm DÒNG ở đó để kiểm hạn mức, chèn
-- lượt 429 vào là sổ ngân sách đếm sai.
--
-- Một dòng = một lần bấm gọi API (src/ocr/vision.py `VisionReader.read_table`).
-- Bất biến: số dòng == `VisionReader.calls`. Lượt bị chặn TRƯỚC khi gọi (VLM
-- tắt, chạm trần) không có dòng — chúng không tiêu hạn mức.
--
-- Token để NULL khi Google không trả phản hồi (429, lỗi mạng). `bad_response`
-- CÓ token: Google đã tính lượt đó dù JSON không dùng được.
-- `error` đã che khoá API (src/ocr/call_log.py `redact_error`), tối đa 200 ký tự.
-- `key_index` là vị trí trong vòng xoay khoá, KHÔNG phải khoá.

CREATE TABLE IF NOT EXISTS vlm_call_log (
    id                bigserial   PRIMARY KEY,
    ts                timestamptz NOT NULL,
    source            text,
    page              integer,
    mode              text        NOT NULL,
    model             text        NOT NULL,
    prompt_version    text        NOT NULL,
    key_index         integer     NOT NULL,
    outcome           text        NOT NULL
        CHECK (outcome IN ('ok', 'bad_response', 'rate_limited', 'error')),
    latency_ms        integer     NOT NULL,
    prompt_tokens     integer,
    completion_tokens integer,
    total_tokens      integer,
    error             text
);

CREATE INDEX IF NOT EXISTS vlm_call_log_ts_idx ON vlm_call_log (ts DESC);

-- Không tự dọn (cùng lệ với llm_usage). Khi cần:
--   DELETE FROM vlm_call_log WHERE ts < now() - interval '90 days';
