# Hạn mức nhà cung cấp (free tier)

> Đo ngày 2026-07-28. Đây là DỮ KIỆN THIẾT KẾ, không phải ghi chú tham khảo:
> `backend/src/llm/catalog.py` phải khớp bảng này. Sửa một nơi thì sửa cả hai.
> Contract test `test_moi_model_id_trong_catalog_van_con_ton_tai` bắt được lúc
> model biến mất, nhưng KHÔNG bắt được lúc con số hạn mức đổi — chỗ đó vẫn cần
> mắt người.
>
> KHÔNG đặt API key vào file này. Khoá nằm ở `.env` (đã gitignore).

## Bảng 1 — Hạn mức từng model (RPM/TPM/RPD)

Khớp nguyên `CATALOG` trong `backend/src/llm/catalog.py`.

| Provider | Model | Alias (catalog.py) | RPM | TPM | RPD |
|---|---|---|---|---|---|
| Google | Gemini 3.5 Flash Lite | `gemini-3.5-flash-lite` | 15 | 250,000 | 500 |
| Google | Gemini 3.1 Flash Lite | `gemini-3.1-flash-lite` | 15 | 250,000 | 500 |
| Google | Gemma 4 26B | `gemma-4-26b` | 30 | 16,000 | 14,400 |
| Google | Gemma 4 31B | `gemma-4-31b` | 30 | 16,000 | 14,400 |
| Groq | openai/gpt-oss-20b | `groq-gpt-oss-20b` | 30 | 8,000 | 1,000 (TPD 200,000) |
| Groq | openai/gpt-oss-120b | `groq-gpt-oss-120b` | 30 | 8,000 | 1,000 (TPD 200,000) |
| Groq | llama-3.3-70b-versatile | `groq-llama-3.3-70b` | 30 | 12,000 | 1,000 (TPD 100,000) |
| OpenRouter | `inclusionai/ling-3.0-flash:free` | `or-ling` | — | — | ~50/ngày, theo TÀI KHOẢN (chung với mọi model free khác) |
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` | `or-nemotron` | — | — | ~50/ngày, theo TÀI KHOẢN (chung với mọi model free khác) |

**Không có trong catalog:**

- Google `Gemini 2.5/3/3.6 Flash` (bản không-Lite, khác với Flash **Lite** ở
  trên) có RPD=20 — gần như vô dụng. Đây là lý do `catalog.py` **cố ý** không
  đưa biến thể Flash không-Lite vào, chỉ dùng bản Lite.
- `google/gemma-4-31b-it:free` trên OpenRouter: đo được nó trả 429 kèm
  `provider_name: "Google AI Studio"` — tức OpenRouter proxy ngược về đúng hồ
  hạn mức của Google, không phải một mắt xích độc lập. Loại có chủ đích; xem
  chú thích "CHÚ THÍCH OPENROUTER" ngay trong `catalog.py`.

## Bảng 2 — Hành vi `<thought>` + kế toán token

| Model | `<thought>` rò vào `content`? | `p+c` vs `total_tokens` |
|---|---|---|
| `gemini-3.5-flash-lite` | Không | 48 = 48 |
| `gemini-3.1-flash-lite` | Không | 48 = 48 |
| `gemma-4-26b-a4b-it` | **Có** | 47 vs **337** (thiếu 7.2×) |
| `gemma-4-31b-it` | **Có** | 45 vs **315** (thiếu 7.0×) |

Thinking không tắt được ở họ Gemma: `reasoning_effort=none` →
`400 "Thinking budget is not supported for this model"`;
`reasoning_effort=low` → `400 "Thinking level is not supported for this
model"`.

Gemma 4 **CÓ** hỗ trợ tool-calling (`finish_reason: tool_calls` hoạt động
bình thường) — giả định ban đầu rằng họ Gemma thiếu function-calling là sai
với Gemma 4.

## Bảng 3 — Model ID đã xác nhận tồn tại

Đo `GET /v1beta/models`, `/openai/v1/models`, ngày 2026-07-28.

| Provider | model_id đã xác nhận |
|---|---|
| Google | `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `meta-llama/llama-prompt-guard-2-22m`, `meta-llama/llama-prompt-guard-2-86m`, `whisper-large-v3`, `whisper-large-v3-turbo` |
| OpenRouter | `inclusionai/ling-3.0-flash:free`, `nvidia/nemotron-3-super-120b-a12b:free` |

Groq cũng có `qwen/qwen3.6-27b`, `llama-3.1-8b-instant`,
`openai/gpt-oss-safeguard-20b` — thấy trong danh sách model nhưng chưa có
hạn mức xác nhận, nên chưa đưa vào `catalog.py`. Ghi lại đây để tham khảo
sau.
