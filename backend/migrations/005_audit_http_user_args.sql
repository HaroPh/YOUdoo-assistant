-- Mục 17 — vệt kiểm toán trả lời được AI ĐÃ GỌI và GỌI CÁI GÌ.
--
-- Trước bản này mcp_call_log ghi `caller = mcp-odoo/<vai>` (tên tiến trình).
-- Nó nói được "AI vai nào", KHÔNG nói được ai đã yêu cầu, cũng không nói được
-- lệnh gọi mang tham số gì. Sau một sự cố, đó đúng là hai câu hỏi đầu tiên.
--
-- BA CỘT MỚI:
--   http_user   — id người dùng Open WebUI, backend gắn vào header
--                 `x-youdoo-user` theo TỪNG lượt gọi tool (interceptor của
--                 MultiServerMCPClient), phía MCP đọc qua request_ctx.
--   args_digest — sha256 (16 ký tự đầu) của args+kwargs đã chuẩn hoá.
--   args_keys   — TÊN các tham số, KHÔNG có giá trị nào.
--
-- Vì sao digest chứ không phải tham số đầy đủ (quyết định chủ dự án
-- 2026-08-22): tham số mang tên khách, số tiền, công nợ. Cặp digest+khoá trả
-- lời được "có phải cùng một lệnh gọi", "bản ghi có bị sửa", "động tới trường
-- nào" — không trả lời được "số tiền bao nhiêu". Đó là đánh đổi đã chọn.
--
-- ⚠️ ĐỨT CHUỖI HASH CÓ CHỦ ĐÍCH TẠI ĐÂY.
-- compute_entry_hash nay băm cả ba cột mới, nên 2 671 dòng cũ (băm theo công
-- thức không có chúng) không verify được nữa. Chủ dự án chọn phương án "dọn
-- rác test + khởi động chuỗi mới" thay vì đánh phiên bản hàm băm, vì
-- **2 502/2 671 dòng (94%) là rác của bộ test** — fixture ghi thẳng vào bảng
-- production dưới tài khoản cá nhân. Chỉ 70 dòng đến từ ba tài khoản AI thật.
-- Một vệt kiểm toán 94% nhiễu thì thêm cột cũng không đọc được.
--
-- Dữ liệu cũ KHÔNG bị xoá: nó nằm nguyên trong mcp_call_log_archive.

BEGIN;

-- 1. Lưu trữ nguyên vẹn TRƯỚC khi động vào bảng gốc.
CREATE TABLE IF NOT EXISTS mcp_call_log_archive AS
    SELECT * FROM mcp_call_log;

-- 2. Ba cột mới.
ALTER TABLE mcp_call_log ADD COLUMN IF NOT EXISTS http_user   text;
ALTER TABLE mcp_call_log ADD COLUMN IF NOT EXISTS args_digest text;
ALTER TABLE mcp_call_log ADD COLUMN IF NOT EXISTS args_keys   text[];

-- 3. Dọn bảng gốc để chuỗi mới bắt đầu từ GENESIS.
--    DELETE chứ không TRUNCATE: giữ bigserial chạy tiếp, nên id của dòng mới
--    không bao giờ trùng id đã lưu trữ — đối chiếu hai bảng vẫn rõ ràng.
DELETE FROM mcp_call_log;

-- 4. Ghi lại chính việc dọn này. entry_hash để NULL: dòng này ĐỨNG NGOÀI
--    chuỗi (verify lọc WHERE entry_hash IS NOT NULL), nên nó không giả vờ là
--    một mắt xích — nó là ghi chú vận hành, và việc xoá không diễn ra lén.
INSERT INTO mcp_call_log
    (created_at, event_type, caller, tool_name, error_message)
VALUES
    (now(), 'chain_reset', 'migration/005',
     '005_audit_http_user_args.sql',
     'Chuỗi hash khởi động lại: compute_entry_hash nay băm thêm http_user, '
     'args_digest, args_keys. Dữ liệu trước mốc này nằm ở mcp_call_log_archive '
     '(2671 dòng, trong đó 2502 là rác bộ test).');

COMMIT;
