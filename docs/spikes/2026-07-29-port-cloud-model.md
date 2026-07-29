# Spike: hình dạng đầu ra model cloud với prompt hiệu chỉnh cho qwen3:8b

> Chạy ngày 2026-07-29. Kết quả THẬT — 3 provider (Google/Groq/OpenRouter) gọi
> thật qua `llm/router.py`, không giả lập. Script vứt đi:
> `backend/spikes/spike_port_smoke.py` + 3 script đào sâu cùng thư mục, đã xoá
> sau khi trích kết quả vào file này (Bước 6).

## Cách đo

Venv `backend/.venv` dựng mới (Python 3.11.9,
`pip install -r backend/requirements.txt`, không lỗi). `.env` ở gốc repo có
`GOOGLE_API_KEY` (tiền tố lạ `AQ.Ab8...`, đã xác nhận với người dùng),
`GROQ_API_KEY`, `OPENROUTER_API_KEY` — nạp bằng `load_dotenv()` thêm vào đầu
script spike (chưa có `load_dotenv()` nào khác trong repo). Xác minh trước khi
chạy:

```
$ .venv/Scripts/python.exe -c "from dotenv import load_dotenv; import os; load_dotenv(); print(bool(os.environ.get('GOOGLE_API_KEY')), bool(os.environ.get('GROQ_API_KEY')), bool(os.environ.get('OPENROUTER_API_KEY')))"
True True True
```

Google key hoạt động bình thường trong mọi lượt gọi bên dưới — **không có lỗi
xác thực nào**, tiền tố `AQ.Ab8...` không phải dấu hiệu key hỏng.

`INTENT_ROUTER_PROMPT`, `WRITE_PLANNER_PROMPT`, `RAG_SYNTHESIS_PROMPT` rút
bằng AST từ `D:\Project\backend\src\agents\prompts.py` (935/7426/1168 ký tự —
khớp bảng trong brief), bắn qua `Router(BudgetLedger(InMemoryUsageStore()))`
với sổ ngân sách trống (mọi vai rơi vào mắt xích ĐẦU chuỗi = model rẻ/generous
nhất). Câu hỏi dùng chung: *"Tồn kho sản phẩm ABC còn bao nhiêu?"*.

Ngoài script gốc trong brief, chạy thêm 3 script phụ (cùng vứt đi) để trả lời
đủ 4 câu hỏi bắt buộc — lý do từng cái ghi ngay tại điểm dùng bên dưới.

## Câu hỏi cần trả lời

1. `.content` có phải list với model gemini-3.x không?
2. Prompt planner (hiệu chỉnh qwen3) còn sinh JSON hợp lệ không?
3. `finish_reason` / `response_metadata` có hình dạng gì theo từng provider?
4. Còn chỗ nào khác vỡ?

(Phát sinh thêm trong lúc đo, quan trọng không kém 4 câu trên: **vai `router`
— không chạm gemini-3.x — có vỡ theo cách khác không?** Câu trả lời: có, và
nặng hơn dự tính ban đầu — xem phát hiện #2/#3 bên dưới.)

## Kết quả đo

### Lượt 1 — script gốc theo brief (`spike_port_smoke.py`), 3 vai qua sổ ngân sách trống

```json
[
  {
    "vai": "router",
    "LOI": "TypeError: expected string or bytes-like object, got 'list'"
  },
  {
    "vai": "planner",
    "alias": "gemini-3.5-flash-lite",
    "provider": "google",
    "kieu_content": "list[1] các phần tử kiểu ['dict']",
    "content_la_list": true,
    "content_50_ky_tu_dau": "[{'type': 'text', 'text': '```json\\n{\\n  \"tool\": \"",
    "co_tool_calls": false,
    "response_metadata_keys": ["finish_reason", "model_name", "model_provider", "safety_ratings"],
    "co_usage_metadata": true,
    "total_tokens": 2463,
    "finish_reason": "STOP"
  },
  {
    "vai": "synthesis",
    "alias": "gemini-3.1-flash-lite",
    "provider": "google",
    "kieu_content": "list[1] các phần tử kiểu ['dict']",
    "content_la_list": true,
    "content_50_ky_tu_dau": "[{'type': 'text', 'text': 'KHÔNG_ĐỦ_THÔNG_TIN', 'e",
    "co_tool_calls": false,
    "response_metadata_keys": ["finish_reason", "model_name", "model_provider", "safety_ratings"],
    "co_usage_metadata": true,
    "total_tokens": 403,
    "finish_reason": "STOP"
  }
]
```

`router` ném `TypeError` **bên trong `Router.ainvoke()`**, không phải lỗi
mạng/API — điều tra ngay bên dưới.

### Lượt 2 — đào sâu vai `router` (gọi thẳng client, né `strip_thought()` để xem content thật)

```
=== RAW gemma-4-26b (router role, bỏ qua strip_thought) ===
type(content): list
  [0] type=dict -> {"type": "thinking", "thinking": "*   User message: \"Tồn kho sản phẩm ABC còn bao nhiêu?\"...(rút gọn)"}
  [1] type=dict -> {"type": "text", "text": "erp_read"}
response_metadata: {"finish_reason": "STOP", "model_name": "gemma-4-26b-a4b-it", "safety_ratings": [], "model_provider": "google_genai"}
usage_metadata: {'input_tokens': 229, 'output_tokens': 180, 'total_tokens': 409, 'input_token_details': {'cache_read': 0}, 'output_token_details': {'reasoning': 177}}
```

Nhãn phân loại thật (`erp_read`) đúng như `INTENT_ROUTER_PROMPT` kỳ vọng —
model KHÔNG hỏng, chỉ là output nằm trong list 2 phần tử (`thinking` +
`text`), và `strip_thought()` (viết cho string) crash khi nhận list.

### Lượt 2 (tiếp) — content ĐẦY ĐỦ + `json.loads()` cho planner/synthesis

```
=== FULL content — vai planner (alias=gemini-3.5-flash-lite) ===
type(content): list
  [0] {"type": "text", "text": "{\n  \"tool\": \"other\",\n  \"args\": {},\n  \"summary\": \"Kiểm tra tồn kho sản phẩm ABC\"\n}", "extras": {"signature": "EjQKMgERTTIPMHg6S37C0GOASlbTeSBiZj7wHpE5HhV714k1O3ktLxktFgQjzauAIqYbGjX+"}}
--- content gộp thành string (dài 81 ký tự) ---
{
  "tool": "other",
  "args": {},
  "summary": "Kiểm tra tồn kho sản phẩm ABC"
}
--- có chuỗi '<thought>' không: False
--- json.loads(nguyên văn): OK ---

=== FULL content — vai synthesis (alias=gemini-3.1-flash-lite) ===
type(content): list
  [0] {"type": "text", "text": "KHÔNG_ĐỦ_THÔNG_TIN", "extras": {"signature": "EjQKMgERTTIPTJlWckgvgDoc2UOQ5cu28JBjx0dumKFrdFj0Aemb4JovHYiaYgoOKg8EcyRF"}}
--- content gộp thành string (dài 18 ký tự) ---
KHÔNG_ĐỦ_THÔNG_TIN
--- có chuỗi '<thought>' không: False
```

### Lượt 3 — lặp lại vai planner 3 lần (pin `gemini-3.5-flash-lite`, cùng prompt, cùng `temperature=0`) để đo độ ổn định định dạng

````
--- lần 1 --- co_fence=False  parse_nguyen_van=OK
{
  "tool": "other",
  "args": {},
  "summary": "Kiểm tra tồn kho sản phẩm ABC"
}

--- lần 2 --- co_fence=True   parse_nguyen_van=LOI: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```json
{
  "tool": "other",
  "args": {},
  "summary": "Kiểm tra tồn kho sản phẩm ABC"
}
```

--- lần 3 --- co_fence=True   parse_nguyen_van=LOI: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```json
{
  "tool": "other",
  "args": {},
  "summary": "Kiểm tra tồn kho sản phẩm ABC"
}
```
````

Gộp với lượt 1 và lượt 2: **5 lần gọi tổng cộng, 2/5 không có fence (parse thẳng OK),
3/5 có fence bọc bằng ba dấu backtick + `json` (kiểu markdown code fence) TOÀN
BỘ nội dung (parse thẳng THẤT BẠI)** — cùng prompt, cùng câu hỏi,
`temperature=0`. Đây là non-determinism thật của Gemini, không phải lỗi đo.

Kiểm tra tiếp: `_parse_plan_tiered` ở repo nguồn (`D:\Project\backend\src\
agents\nodes.py` dòng 148–165) đã có tầng "salvage" strip `<think>` +
fence-fullmatch. Chạy đúng regex đó (đọc từ file, không suy đoán) lên output
fenced thật ở trên:

```python
>>> parse_plan_tiered(fenced_output)
({'tool': 'other', 'args': {}, 'summary': 'Kiểm tra tồn kho sản phẩm ABC'}, 'salvage')
```

**Salvage tier cứu được** — với điều kiện đầu vào là STRING. Chi tiết ở phát
hiện #5 bên dưới.

### Lượt 4 — so sánh hình dạng response giữa 3 provider (pin Groq/OpenRouter, vì sổ ngân sách trống luôn chọn Google cho cả 3 vai gốc)

```json
[
  {
    "vai": "planner", "pin": "groq-gpt-oss-120b", "provider": "groq",
    "kieu_content": "str dài 81", "content_la_list": false,
    "content_100_ky_tu_dau": "{\n  \"tool\": \"other\",\n  \"args\": {},\n  \"summary\": \"Kiểm tra tồn kho sản phẩm ABC\"\n}",
    "response_metadata": {
      "token_usage": {"completion_tokens": 77, "prompt_tokens": 2299, "total_tokens": 2376,
        "completion_tokens_details": {"reasoning_tokens": 40, "...": null}},
      "model_provider": "openai", "model_name": "openai/gpt-oss-120b",
      "system_fingerprint": "fp_df9620fe21", "id": "chatcmpl-0d71500e-...",
      "service_tier": "on_demand", "finish_reason": "stop", "logprobs": null
    },
    "total_tokens": 2376, "finish_reason": "stop"
  },
  {
    "vai": "synthesis", "pin": "or-nemotron", "provider": "openrouter",
    "kieu_content": "str dài 18", "content_la_list": false,
    "content_100_ky_tu_dau": "KHÔNG_ĐỦ_THÔNG_TIN",
    "response_metadata": {
      "token_usage": {"completion_tokens": 102, "prompt_tokens": 449, "total_tokens": 551,
        "completion_tokens_details": {"reasoning_tokens": 88, "...": null},
        "cost": 0, "is_byok": false},
      "model_provider": "openai", "model_name": "nvidia/nemotron-3-super-120b-a12b:free",
      "system_fingerprint": null, "id": "gen-1785302421-...",
      "finish_reason": "stop", "logprobs": null
    },
    "total_tokens": 551, "finish_reason": "stop"
  }
]
```

Không có `ChainExhausted` hay fallback bất ngờ nào trong toàn bộ phép đo (11
lượt gọi thật tổng cộng: Lượt 1 = 3, Lượt 2 = 3, Lượt 3 = 3, Lượt 4 = 2) —
mọi lượt (trừ router, hỏng SAU khi gọi thành công) trả lời ngay ở mắt xích
được resolve, không bị 429/cooldown.

## Kết luận chi phối task sau

| # | Phát hiện | Ảnh hưởng task nào | Phải làm gì |
|---|---|---|---|
| 1 | Giả thuyết `.content` list-shape **ĐÚNG**, xác nhận trực tiếp: cả `gemini-3.5-flash-lite` (planner) và `gemini-3.1-flash-lite` (synthesis) đều trả `.content` là `list[{"type":"text",...}]`, không phải string. | Task 2 | Giữ nguyên tiền đề chuẩn hoá `.content`. |
| 2 | **Phát hiện MỚI, ngoài giả thuyết gốc:** `.content` list-shape KHÔNG chỉ xảy ra với model có tiền tố `"gemini-3"`. Vai `router` (chain đầu là `gemma-4-26b`, KHÔNG khớp `_is_gemini_3_or_later`) cũng trả `.content` list, qua một nhánh khác trong `langchain_google_genai/chat_models.py`: khi `part.thought` có giá trị (Gemma "không tắt được thinking" — đã ghi ở `catalog.py`), thư viện tạo block `{"type":"thinking",...}` rồi các block `text` theo sau CŨNG bị giữ dạng list (dòng 916–943 của `chat_models.py`, đọc mã trực tiếp, không đoán). | Task 2 (mở rộng phạm vi bắt buộc) | Chuẩn hoá `.content` list→string phải áp dụng cho **MỌI response từ provider Google** (Gemini lẫn Gemma), không được if/else theo tên model chứa `"gemini-3"`. Vì 6/7 chain có Google làm mắt xích ĐẦU (`router, chitchat, planner, read, fusion, synthesis` — chỉ `evaluator` có Groq đầu), đây là đường chạy MẶC ĐỊNH, không phải edge case. |
| 3 | **Lỗi thật, nghiêm trọng, đang tồn tại ngay bây giờ:** vai `router` với `emits_thought_tags=True` (Gemma) gọi `strip_thought(response.content)` trong `Router._finish()` — hàm này kỳ vọng `str`, nhận `list`, ném `TypeError` KHÔNG BỊ BẮT. Dòng `return self._finish(...)` trong cả `invoke()` và `ainvoke()` nằm NGOÀI khối `try/except` bọc lệnh gọi model, nên exception này lan thẳng lên node gọi — **không degrade êm về SAFE_MSG** như thiết kế của `ChainExhausted` (đọc docstring `router.py`: "Node gọi bắt lỗi này và degrade về SAFE_MSG — người dùng không bao giờ thấy stack trace"). Đây là crash thật, đo được bằng traceback thật, không phải suy diễn. | Task 2 (khẩn cấp — chặn Task 9) | Bước chuẩn hoá `.content` (phát hiện #1/#2) PHẢI chạy TRƯỚC dòng `if decision.spec.emits_thought_tags: strip_thought(...)` trong `_finish()`. Cân nhắc thêm: bọc toàn bộ `_finish()` bằng try/except tương tự khối gọi model, hoặc ít nhất viết test tái hiện đúng case này (vai `router`, Gemma, list content) để không tái phát. |
| 4 | Nếu chuẩn hoá list→string bằng cách nối MỌI phần tử bất kể `type`, nội dung suy nghĩ nội bộ sẽ lẫn vào output cuối — đo được: block `thinking` của router dài ~180 token reasoning (`output_token_details.reasoning: 177`), tách biệt hoàn toàn với block `text` chứa nhãn thật (`"erp_read"`). Gộp thô sẽ phá cả nhãn phân loại (router) lẫn JSON (planner). | Task 2 | Hàm normalize phải **lọc theo `type`**: chỉ giữ `type == "text"`, bỏ `type == "thinking"` (và các type khác như `executable_code`/`code_execution_result` nếu gặp — không xuất hiện trong phép đo này nhưng cùng họ vấn đề). Không join thô `str(content)`. |
| 5 | Cơ chế `emits_thought_tags` + `strip_thought()` (regex tìm `<thought>...</thought>` trong MỘT STRING) được thiết kế và đo (2026-07-28, ghi trong docstring `providers.py`) cho **endpoint OpenAI-compat cũ** của Google, nơi Gemma nối thẳng suy nghĩ vào content dạng text. `providers.py` từ Task 7 đã chuyển TOÀN BỘ Google (kể cả Gemma) sang `ChatGoogleGenerativeAI` SDK gốc — nơi Gemma trả "thinking" như **block cấu trúc riêng trong list** (phát hiện #2), không còn tag XML nhúng trong string nữa. Sau khi chuẩn hoá theo phát hiện #4 (lọc bỏ block `thinking`), `strip_thought()` gần như luôn no-op cho Gemma qua SDK mới. | Task 2 | KHÔNG xoá `strip_thought()` (vô hại, đúng như brief đã lường trước) — nhưng ghi rõ trong code/comment rằng nó nay là lưới an toàn dự phòng (phòng khi model nhét `<thought>` literal vào một block `text`), KHÔNG còn là cơ chế chính xử lý thinking của Gemma. Thứ tự bắt buộc: chuẩn hoá list→string (lọc `type`) TRƯỚC, `strip_thought()` SAU. |
| 6 | Prompt `WRITE_PLANNER_PROMPT` (hiệu chỉnh qwen3:8b) chạy qua `gemini-3.5-flash-lite`: sau khi gộp `.content` đúng cách (chỉ lấy block `text`), JSON tầng "raw" (`json.loads` trực tiếp) chỉ thành công **2/5 lần đo** — 3/5 lần model tự bọc output trong fence ` ```json ... ``` `, cùng prompt/câu hỏi/`temperature=0`. Đây là non-determinism THẬT của Gemini-3.x, đo lặp lại 3 lần liên tiếp cho cùng kết quả nội dung nhưng khác định dạng bọc. | Task 2, Task 9–13 (node planner / logic A5) | **Không cần viết thêm logic strip-fence mới.** `_parse_plan_tiered` ở repo nguồn (`nodes.py` dòng 148–165) ĐÃ có tầng "salvage": strip `<think>` rồi `_FENCE_RE.fullmatch()` nếu fence bọc TOÀN BỘ phần còn lại. Đã kiểm thực nghiệm: chạy nguyên văn regex đó (đọc từ mã nguồn, không chép trí nhớ) lên output fenced thật ở trên → salvage THÀNH CÔNG, trả đúng dict. Điều kiện DUY NHẤT: `_parse_plan_tiered(raw: str)` phải nhận STRING — nếu nhận `list` nguyên trạng, `raw.strip()` ở dòng đầu hàm sẽ `AttributeError` ngay lập tức, sớm hơn và tệ hơn cả case fence. Vậy đây là lý do CHẶT CHẼ NHẤT khiến phát hiện #1–#4 (chuẩn hoá list→string, đúng vị trí, đúng bộ lọc `type`) là điều kiện TIÊN QUYẾT để logic parse JSON cũ port nguyên vẹn mà không cần sửa gì thêm bên trong `_parse_plan_tiered`. |
| 7 | `finish_reason` khác dạng chữ theo provider: Google trả `"STOP"` (in hoa), Groq và OpenRouter đều trả `"stop"` (thường) — đo trực tiếp ở cả 5 lượt Google và 2 lượt Groq/OpenRouter pin riêng. `response_metadata` cũng khác cấu trúc hẳn theo provider: Google KHÔNG có khoá `"token_usage"` (chỉ có `finish_reason`, `model_name`, `model_provider`, `safety_ratings` — dùng `usage_metadata` riêng, đúng như docstring `Router._usage()` đã ghi từ trước); Groq/OpenRouter đều có `"token_usage"` lồng bên trong `response_metadata`, hình dạng OpenAI chuẩn (`prompt_tokens`/`completion_tokens`/`completion_tokens_details`), OpenRouter thêm các trường `cost`/`is_byok`/`cost_details` mà Groq không có. | Task 9–13 (bất kỳ chỗ nào so sánh `finish_reason` bằng string, hoặc đọc `response_metadata["token_usage"]` không kiểm tra tồn tại trước) | Nếu code port có so khớp `finish_reason == "stop"` (kiểu OpenAI/Ollama mà repo nguồn dùng), **PHẢI** chuẩn hoá hoa/thường trước khi so sánh (`.upper()`/`.lower()`), nếu không nhánh Google sẽ luôn không khớp một cách âm thầm. Chỗ nào đọc `response_metadata["token_usage"]` trực tiếp (không qua `Router._usage()` đã có sẵn 2 nhánh) sẽ vỡ với Google — ưu tiên luôn đi qua `InvokeResult.total_tokens`/`prompt_tokens`/`completion_tokens` đã chuẩn hoá sẵn ở `router.py`, đừng đọc lại `response_metadata` thô trong `agents/`. |
| 8 | Vai `synthesis` (`RAG_SYNTHESIS_PROMPT`, hiệu chỉnh qwen3) chạy qua `gemini-3.1-flash-lite`: trả đúng sentinel `"KHÔNG_ĐỦ_THÔNG_TIN"` như prompt yêu cầu khi thiếu ngữ cảnh RAG (script không truyền tool/context nào), sạch — không `<thought>`, không xuống dòng thừa, không markdown lạ. Chain của `synthesis` (`gemini-3.1-flash-lite → groq-llama-3.3-70b → or-nemotron`) **không có Gemma** nên rủi ro tag `<thought>` không áp dụng cho vai này ở bất kỳ mắt xích nào. | Task 2, Task 13 | Không cần xử lý gì thêm ngoài chuẩn hoá list→string chung (#1/#4). Không cần logic riêng cho `<thought>` ở vai `synthesis`. |
| 9 | Không quan sát được `ChainExhausted` hay fallback bất ngờ nào trong toàn bộ 11 lượt gọi thật — mọi vai (trừ crash TypeError của router, xảy ra SAU khi model trả lời thành công) resolve đúng mắt xích đầu chuỗi ngay từ lần thử đầu, không đụng 429/cooldown. | (tham khảo, không cần hành động) | Xác nhận `BudgetLedger`/`Router.resolve()` hoạt động đúng thiết kế khi ví trống — không có gì cần sửa ở tầng định tuyến/hạn mức từ phép đo này. |
| 10 | Phép đo này **không** exercise hình dạng `tool_calls` qua provider nào (không có script nào `bind_tools()` — `co_tool_calls` luôn `false`). `TOOL_ROLES = {read, planner, fusion, synthesis}` đều cần tool thật khi port. | Task 9–13 | Đây là khoảng trống CHƯA đo, không phải "đã đo và ổn". Spike `2026-07-28-thought-signature.md` (SP-1A) có đo tool-calling cho Google (2 lượt, thất bại — đó là lý do đổi sang `ChatGoogleGenerativeAI`) nhưng KHÔNG đo cho Groq/OpenRouter tuning theo prompt tiếng Việt hiệu chỉnh qwen3. Task 9 nên có phép đo tool-calling riêng, không giả định nó "chắc cũng giống". |
