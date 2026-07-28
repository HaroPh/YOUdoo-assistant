-- Sổ ngân sách LLM (spec SP-1 §2).
--
-- MỘT bảng cho cả ba cửa sổ (phút / phút / 24 giờ). Không cache, không sổ kép:
-- ở lưu lượng vài nghìn lượt/ngày Postgres làm việc này không tốn gì, mà một
-- cơ chế thì không bao giờ lệch với chính nó.
--
-- prompt_tokens và completion_tokens lưu để CHẨN ĐOÁN, không dùng cho phép
-- kiểm hạn mức nào. Con số có thẩm quyền là total_tokens — đo 2026-07-28,
-- gemma-4-26b-a4b-it trả p=11, c=36 nhưng total=337 (~290 token "thinking"
-- vô hình). Cộng p+c đếm thiếu 7 lần.

CREATE TABLE IF NOT EXISTS llm_usage (
    id                bigserial PRIMARY KEY,
    ts                timestamptz NOT NULL,
    alias             text        NOT NULL,
    provider          text        NOT NULL,
    upstream          text        NOT NULL,
    prompt_tokens     integer     NOT NULL,
    completion_tokens integer     NOT NULL,
    total_tokens      integer     NOT NULL
);

-- Gộp theo alias khi quota_scope="model" (Google, Groq).
CREATE INDEX IF NOT EXISTS llm_usage_alias_ts_idx
    ON llm_usage (alias, ts DESC);

-- Gộp theo provider khi quota_scope="account" (OpenRouter dùng chung một ví).
-- Cột provider PHẢI có thật, không suy ra từ alias lúc truy vấn.
CREATE INDEX IF NOT EXISTS llm_usage_provider_ts_idx
    ON llm_usage (provider, ts DESC);

-- Dọn bản ghi cũ: mọi truy vấn chỉ nhìn lại tối đa 24 giờ, nên phần cũ hơn chỉ
-- còn giá trị chẩn đoán. SP-1 KHÔNG tự dọn (lưu lượng quá nhỏ để đáng bận tâm).
-- Khi cần:  DELETE FROM llm_usage WHERE ts < now() - interval '30 days';
