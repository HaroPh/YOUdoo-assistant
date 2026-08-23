-- Mục 17b — vệt kiểm toán cho ĐƯỜNG ĐỌC.
--
-- Trước bản này, 28 tool `erp_query` sinh ra **0 dòng** kiểm toán:
-- `src/erp_query/transport.py` gọi Odoo bằng ServerProxy riêng, không qua
-- `odoo()` của MCP, nên không qua `log_mcp_event`. Câu "ai đã đọc công nợ
-- khách hàng / bảng giá" không trả lời được từ bất kỳ đâu.
--
-- ⚠️ CỘT NÀY LƯU GIÁ TRỊ THẬT, NGƯỢC VỚI QUYẾT ĐỊNH Ở MỤC 17.
-- Đường GHI cố ý chỉ lưu digest + tên khoá (tham số mang tên khách, số tiền).
-- Đường ĐỌC thì ngược: **chính tham số mới là câu trả lời**.
--
--   get_partner_balance + digest  → "có người xem công nợ", không biết của AI
--   get_partner_balance + args    → "vai kho xem công nợ Azure Interior 14:32"
--
-- Câu hỏi mà mục 17b sinh ra chỉ trả lời được ở vế thứ hai. Quyết định của chủ
-- dự án 2026-08-23 (phương án B). Đánh đổi đã biết: log chứa tên khách, mã
-- đơn, khoảng ngày người dùng tra — KHÔNG chứa số tiền (đó là kết quả, không
-- phải tham số).
--
-- ⚠️ args_json KHÔNG nằm trong chuỗi hash, CÓ CHỦ ĐÍCH:
--   * đường đọc không chained (xem docstring src/erp_query/audit.py);
--   * `compute_entry_hash` sống ở cây mcp-servers, backend không dùng chung —
--     đưa cột này vào chuỗi sẽ buộc chép lại công thức băm sang backend, tức
--     đặt một nguyên thủy an ninh ở hai nơi và chờ nó trôi.
-- `verify_audit_chain._COLUMNS` CỐ Ý không liệt kê cột này.

ALTER TABLE mcp_call_log ADD COLUMN IF NOT EXISTS args_json text;

-- Truy vấn hay dùng nhất khi điều tra: "người X đã đọc gì" / "ai đã đọc tool Y".
CREATE INDEX IF NOT EXISTS mcp_call_log_http_user_idx
    ON mcp_call_log (http_user, created_at DESC)
    WHERE http_user IS NOT NULL;
