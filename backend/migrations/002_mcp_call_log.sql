-- Vệt kiểm toán mọi lệnh gọi MCP (event_log.py + audit_chain.py).
--
-- ⚠️ Bảng này CHƯA TỪNG tồn tại trong database Youdoo: code ghi log được port
-- sang nhưng schema thì không, và log_mcp_event nuốt mọi lỗi ghi ("không được
-- làm hỏng tool") nên UndefinedTable bị nuốt im lặng ở từng lượt gọi. Toàn bộ
-- permission_denied / rate_limit / model_access / write_gate_error chưa từng
-- được ghi. Đo 2026-08-14.
--
-- 12 cột dưới đây là ĐÚNG tập mà event_log.log_mcp_event INSERT và
-- verify_audit_chain._COLUMNS SELECT. Đừng thêm bớt mà không sửa cả hai nơi.
--
-- KHÔNG đặt CHECK trên event_type: thêm một loại sự kiện mới (đợt này thêm
-- 'tool_error') không được đòi migration mới.

CREATE TABLE IF NOT EXISTS mcp_call_log (
    id            bigserial   PRIMARY KEY,
    created_at    timestamptz NOT NULL,
    event_type    text        NOT NULL,
    caller        text,
    tool_name     text,
    model_name    text,
    operation     text,
    duration_ms   integer,
    error_code    text,
    error_message text,
    -- NULL được: verify_audit_chain lọc WHERE entry_hash IS NOT NULL, tức
    -- schema đã lường trước dòng chưa hash-chain.
    entry_hash    text,
    prev_hash     text
);

-- verify_audit_chain duyệt theo id tăng dần; log_mcp_event đọc dòng cuối để
-- lấy prev_hash. Cả hai đều đi theo id nên PK đã đủ, không cần index thêm.
