-- 009: RBAC tầng RAG (spec 2026-09-20 §6) — backfill lớp visibility + gỡ SID.
--
-- Vì sao: cột rag_chunks.visibility có từ tháng 7 nhưng 4 561/4 561 chunk đều
-- 'all' (đo 2026-09-19) — vai kho đọc được chính sách chiết khấu. Ingest nay
-- ghi lớp từ DOC_VISIBILITY (src/rag/visibility.py), nhưng re-ingest là NO-OP
-- khi content_hash không đổi nên corpus đang có PHẢI backfill ở đây.
--
-- Bốn basename bên dưới PHẢI bằng đúng khoá của DOC_VISIBILITY —
-- tests/rag/test_migration_009_contract.py giữ hai nguồn không trôi.
--
-- ⚠️ THAO TÁC PHÁ HUỶ DUY NHẤT của 19b: gỡ tài liệu SID (báo cáo tài chính
-- bán niên, 660 chunk) — nạp tay lúc test OCR bậc 3, không phải tri thức tổ
-- chức, đã gây ô nhiễm chéo (trả số SID cho câu hỏi về NTC, 2026-09-19).
-- Chunk đi theo ON DELETE CASCADE. Chạy SAU khi chủ dự án gật, KHÔNG nối với
-- lệnh khác.
--
-- Idempotent. Chạy tay, theo lệ của thư mục này. Số dòng in ra bằng RAISE
-- NOTICE — lượt chạy tay để lại bằng chứng (kỳ vọng lần đầu: 24 chunk ->
-- commercial; 1 tài liệu SID / 660 chunk gỡ; lần sau: 0 / 0).
DO $$
DECLARE
    n_commercial int;
    n_sid_chunks int;
    n_sid_docs   int;
BEGIN
    UPDATE rag_chunks SET visibility = 'commercial'
     WHERE visibility <> 'commercial'
       AND (source_file LIKE '%discount_policy.docx'
         OR source_file LIKE '%bang_gia.xlsx'
         OR source_file LIKE '%payment_policy.docx'
         OR source_file LIKE '%sla.docx');
    GET DIAGNOSTICS n_commercial = ROW_COUNT;
    RAISE NOTICE '009: % chunk -> commercial', n_commercial;

    SELECT count(*) INTO n_sid_chunks FROM rag_chunks
     WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%';
    DELETE FROM rag_documents WHERE source_file LIKE '%BaoCaoTaiChinhBanNien%';
    GET DIAGNOSTICS n_sid_docs = ROW_COUNT;
    RAISE NOTICE '009: go % tai lieu SID (% chunk theo cascade)', n_sid_docs, n_sid_chunks;
END $$;
