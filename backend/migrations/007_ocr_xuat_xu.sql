-- backend/migrations/007_ocr_xuat_xu.sql — cờ xuất xứ cho chunk sinh từ ảnh.
--
-- VÌ SAO NẰM TRONG DB, không nằm trong kho đệm OCR: đây là chiều "có đáng tin
-- không" mà retrieval và việc chống injection gián tiếp sẽ cần đọc được, và
-- nó phải sống sót qua mọi lần re-chunk (spec 2026-09-04-tang-ocr §8).
--
-- Ba bậc, tin cậy giảm dần: 'text' (đọc thẳng lớp text của tệp) > 'ocr' (đọc
-- bằng ảnh qua Tesseract) > 'vision_description' (mô tả hình bằng VLM — bậc 3,
-- chưa dùng). Mặc định 'text' vì toàn bộ corpus hiện tại đọc được lớp text.
--
-- ocr_conf NULL là HỢP LỆ và là trạng thái thường gặp: chỉ chunk có nguồn từ
-- ảnh mới có độ tin cậy để ghi.
--
-- Idempotent, an toàn khi chạy lại.
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS source_kind text NOT NULL DEFAULT 'text';
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS ocr_conf real;
