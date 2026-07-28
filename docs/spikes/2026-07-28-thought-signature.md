# Spike: `thought_signature` của Gemini 3 qua `ChatOpenAI` — 2026-07-28

## Câu hỏi

`ChatOpenAI` (LangChain, qua endpoint OpenAI-compatible của Google) có giữ
được `extra_content.google.thought_signature` mà Gemini 3 gắn vào
`tool_calls`, đủ để một vòng lặp tool nhiều lượt (gọi tool → trả kết quả →
gọi tiếp) hoàn tất bình thường không? Nếu không, đường lui là đổi client
Google trong `providers.py` (Task 7) sang `langchain-google-genai` /
`ChatGoogleGenerativeAI` native.

## Cách đo

Script: `backend/spikes/spike_thought_signature.py`. Dựng một `ChatOpenAI`
trỏ tới `https://generativelanguage.googleapis.com/v1beta/openai/`, model
`gemini-3.5-flash-lite`, `bind_tools([get_stock, get_price])`. Gửi câu hỏi
tiếng Việt cần cả hai tool ("Sản phẩm ABC còn bao nhiêu hàng, và đơn giá bao
nhiêu?"), lặp tối đa 3 lượt: gọi model → nếu có `tool_calls` thì thực thi
tool cục bộ và nối `ToolMessage` vào lịch sử → gọi lại model với lịch sử đã
nối. Mỗi lượt in `tool_calls`, `additional_kwargs`, `response_metadata`, và
có chuỗi `"thought_signature"` xuất hiện ở đâu đó trong ba trường đó không.

Lệnh chạy thật (venv `backend/.venv`, Python 3.11.9, cài đúng
`backend/requirements.txt`):

```bash
cd backend
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.spike_thought_signature
```

(Biến `PYTHONIOENCODING=utf-8` chỉ để console Windows/cp1252 không vỡ khi in
tiếng Việt — không ảnh hưởng gì tới hành vi gọi API hay nội dung script.)

## Kết quả quan sát được

Output thật, dán nguyên văn, không diễn giải (stdout và stderr của cùng một
lần chạy, ghép lại đúng theo trình tự thực thi: model trả lời lượt 1 thành
công và có `tool_calls`, rồi request lượt 2 — gửi kèm `ToolMessage` — bị
Google từ chối với `400`):

```
─── Lượt 1 ───
  tool_calls        : ['get_stock', 'get_price']
  additional_kwargs : {"refusal": null}
  response_metadata : {"token_usage": {"completion_tokens": 32, "prompt_tokens": 107, "total_tokens": 139, "completion_tokens_details": null, "prompt_tokens_details": null}, "model_provider": "openai", "model_name": "gemini-3.5-flash-lite", "system_fingerprint": null, "id": "969oauyvGbDp1e8PypPvuAc", "finish_reason": "tool_calls", "logprobs": null}
  CÓ thought_signature: False

Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\spikes\spike_thought_signature.py", line 74, in <module>
    main()
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\spikes\spike_thought_signature.py", line 49, in main
    ai = bound.invoke(messages)
         ^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_core\runnables\base.py", line 6004, in invoke
    return self.bound.invoke(
           ^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 476, in invoke
    self.generate_prompt(
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1849, in generate_prompt
    return self.generate(prompt_messages, stop=stop, callbacks=callbacks, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1656, in generate
    self._generate_with_cache(
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1994, in _generate_with_cache
    result = self._generate(
             ^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_openai\chat_models\base.py", line 1690, in _generate
    _handle_openai_bad_request(e)
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\langchain_openai\chat_models\base.py", line 1687, in _generate
    raw_response = self.client.with_raw_response.create(**payload)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\openai\_legacy_response.py", line 369, in wrapped
    return cast(LegacyAPIResponse[R], func(*args, **kwargs))
                                      ^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\openai\_utils\_utils.py", line 298, in wrapper
    return func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\openai\resources\chat\completions\completions.py", line 1284, in create
    return self._post(
           ^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\openai\_base_client.py", line 1360, in post
    return cast(ResponseT, self.request(cast_to, opts, stream=stream, stream_cls=stream_cls))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Youdoo\.claude\worktrees\agent-a109f74ee1cc974df\backend\.venv\Lib\site-packages\openai\_base_client.py", line 1133, in request
    raise self._make_status_error_from_response(err.response) from None
openai.BadRequestError: Error code: 400 - [{'error': {'code': 400, 'message': 'Function call is missing a thought_signature in functionCall parts. This is required for tools to work correctly, and missing thought_signature may lead to degraded model performance. Additional data, function call `default_api:get_stock` , position 2. Please refer to https://ai.google.dev/gemini-api/docs/thought-signatures for more details.', 'status': 'INVALID_ARGUMENT'}}]
```

Đối chiếu với ba điểm cần quan sát:

1. **Vòng lặp có hội tụ không?** Không. Chạy dừng ngay ở lượt 2 với ngoại lệ
   `openai.BadRequestError` chưa bắt — kịch bản chưa từng chạm tới câu trả
   lời cuối, chưa nói gì tới việc câu trả lời đó có đúng cả tồn kho lẫn giá
   hay không.
2. **`thought_signature` có xuất hiện trong `additional_kwargs` /
   `response_metadata` / `tool_calls` không?** Không. Ở lượt 1 (lượt duy
   nhất model trả lời thành công), script tự kiểm tra chuỗi
   `"thought_signature"` trong cả ba trường gộp lại và in ra
   `CÓ thought_signature: False`. `additional_kwargs` chỉ có `{"refusal":
   null}`, không mang theo trường `extra_content.google.thought_signature`
   nào — `ChatOpenAI` không expose/giữ trường này.
3. **Có lỗi `400` liên quan chữ ký không?** Có. Ngay lượt 2 (request đầu
   tiên có kèm `ToolMessage` trong lịch sử), Google trả:
   `400 INVALID_ARGUMENT — "Function call is missing a thought_signature in
   functionCall parts. This is required for tools to work correctly..."`
   — đúng loại lỗi mà spec §2/§12 đã cảnh báo trước.

## Quyết định

Rơi vào **hàng thứ hai** của bảng quyết định trong brief: vòng lặp không hội
tụ, và Google trả lỗi liên quan trực tiếp tới `thought_signature`.

**Quyết định:** Task 7 (`providers.py`) sẽ dùng `langchain-google-genai` /
`ChatGoogleGenerativeAI` **cho riêng Google**; Groq và OpenRouter tiếp tục
dùng `ChatOpenAI` qua endpoint OpenAI-compatible (không có bằng chứng nào
cho thấy hai provider này có vấn đề tương tự — họ không phát hành
`thought_signature`). `client_for()` trong `providers.py` phải phân nhánh
theo `spec.provider` thay vì dựng một `ChatOpenAI` chung với `base_url` khác
nhau. `langchain-google-genai==4.2.0` đã được thêm vào
`backend/requirements.txt` (bản ghim tương thích với `langchain-core==1.4.8`
đã pin theo repo nguồn — đã xác minh bằng `pip install --dry-run` không kéo
theo việc nâng `langchain-core`).

Spec `docs/superpowers/specs/2026-07-28-sp1-foundation-design.md` đã được
cập nhật theo quyết định này ở ba chỗ: bảng rủi ro §12 (đánh dấu "đã xác
nhận"), mục `providers.py` trong §2 (bảng ba client đổi từ ba `ChatOpenAI`
cùng lớp khác `base_url` sang Google dùng `ChatGoogleGenerativeAI`), và mục
"Rủi ro đã chọc: `thought_signature`" trong §2 (từ "phải chọc sớm" sang "đã
chọc", kèm kết quả và tham chiếu tới tài liệu này).
