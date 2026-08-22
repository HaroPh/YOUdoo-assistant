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
| Google | Gemini 3.5 Flash | `gemini-3.5-flash` | 5 | 250,000 | **20** (chỉ để `--model` ghim đo, KHÔNG vào chuỗi nào) |
| Groq | openai/gpt-oss-120b | `groq-gpt-oss-120b` | 30 | 8,000 | 1,000 (TPD 200,000) |
| OpenRouter | nvidia/nemotron-3-super-120b-a12b:free | `or-nemotron` | — | **không công bố** | ~50 (ví CHUNG cả tài khoản) |

Nhân **ba** cho mọi dòng Google: hạn mức tính theo PROJECT, và `.env` có ba
khoá của ba project (xem spec `2026-08-21-api-key-rotation.md`).

**Đã XOÁ khỏi catalog 2026-08-21** (spec `2026-08-21-catalog-consolidation.md`):

| Alias | Vì sao |
|---|---|
| `groq-llama-3.3-70b` | **CHẾT** — Groq trả *"model does not exist"* |
| `or-ling` | **CHẾT** — OpenRouter gỡ slug `:free` |
| `gemma-4-26b` | thua mọi ứng viên trên bộ `confirm` (0,7917) và chậm gấp 8 |
| `groq-gpt-oss-20b` | kém nhất trên `confirm` (0,6250), cùng ví hạn mức với 120b nên không mua thêm gì |

### `or-nemotron` — xoá 2026-08-21, KHÔI PHỤC 2026-08-22

> ⚠️ Mục này ban đầu ghi một lý do **SAI**, rút từ một phép đo đúng nhưng sai
> hình dạng. Giữ lại cả hai để không ai dựng lại lập luận cũ.

**Lý do nêu ban đầu (đã bị chính số đo bác bỏ):** *"bỏ `or-nemotron` khiến
`groq-gpt-oss-120b` thành dự phòng duy nhất, mà nó trả HTTP 413 cho vai admin
ngay từ lượt đầu"*. Phép đo có thật — nhưng nó bind **cả 35 tool MCP** vào LLM,
và production **không gửi hình dạng đó bao giờ**: `erp_read` bind
`build_erp_query_tools(role_cfg)` = **28 tool `erp_query`**; tool MCP chỉ đi tới
`erp_write_executor`, nút **chạy** tool chứ không bind chúng vào model nào.

**Đo lại đúng hình dạng production** (vai admin, lượt `read`):

| lịch sử | Groq đếm | Gemini đếm |
|---|---|---|
| 0 lượt | 2 762 | 3 119 |
| 20 lượt | 3 542 | — |

≈ 39 token mỗi lượt lịch sử ngắn ⇒ cần ~134 lượt mới chạm trần 8 000. **Groq
không hỏng trong production.**

**Lý do còn lại, vẫn đủ để giữ nó:**

1. **Miền lỗi thứ ba.** Chuỗi Google → Groq chỉ có hai đường thoát;
   `upstream = "nvidia"` thêm đường thứ ba. Bất biến #6 (`test_catalog.py`) nay
   canh đúng điều này: mỗi vai bind tool phải có ≥1 mắt xích ngoài Google.
2. **Thông lượng.** 8 000 tpm của Groq tính trên **cả phút**, mọi lời gọi đồng
   thời cộng dồn ⇒ ~3 lượt có tool trong một phút là 429 (gặp thật lúc đo,
   `Requested=6858`). `tpm = None` không có trần đó.

**Đã cân nhắc và loại `gemini-3.5-flash`** (rpd 20): `upstream = "google"` nên
nó không mua được điểm 1. Với ba khoá, ví Gemini đã ~3 000 lượt/ngày — 20 lượt
là nhiễu; và kịch bản một mắt xích dự phòng THẬT SỰ cứu được (Google trục
trặc/đổi API/khoá tài khoản) thì nó chết cùng lúc.

### Hai lỗi CÓ THẬT với payload 35-tool-MCP — ghi lại để đừng đo lại

Cả hai chỉ xuất hiện khi bind toàn bộ registry MCP vào LLM, việc production
không làm. Nhưng nếu mai có ai định làm, đây là thứ họ sẽ gặp:

| model | lỗi |
|---|---|
| `groq-gpt-oss-120b` | HTTP 413 — *"Limit 8000, Requested 12124"* |
| `gemini-3.1-flash-lite` | HTTP 400 — 10 tham số kiểu `list` **trần** (`lines`, `ops`, `components`, `changes`, `partner_ids`, `vendor_names`) thiếu `items`; Gemini bắt buộc có |
| `or-nemotron` | HTTP 200, 11 024 token |

Lỗi 400 của Gemini nằm ở chú thích kiểu trong `mcp-servers/odoo/tools/*.py`
(`lines: list` thay vì `list[dict]`). Vô hại hôm nay; sẽ thành chặn đường nếu
có ai nối tool MCP thẳng vào một model Gemini.

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
