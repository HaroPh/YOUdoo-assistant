# SP-1C2 — Báo cáo xác nhận sống (Task 8)

Ngày chạy: 2026-07-30. Stack: Docker Desktop (Windows), Postgres đã có sẵn từ
worktree khác (`youdoo-postgres`, container chia sẻ theo thiết kế — xem
`docker-compose.yml`), Langfuse self-host dựng qua `docker compose --profile
observability`, backend chạy native (`python run.py`), MCP Odoo server chạy
native (`python server.py`), Odoo thật đã có sẵn tại `localhost:8069`.

## Bước 1 — Test suite 2 chế độ

```
.venv/Scripts/python.exe -m pytest tests/ -q -m "not integration and not live" --continue-on-collection-errors
```
Kết quả: **884 passed, 4 skipped, 39 deselected, 1 error** (lỗi
`KeyError: 'ODOO_URL'` ở `tests/mcp/test_odoo_tool_boundary.py` — lỗi đã
biết, không phải hồi quy: worktree không kế thừa `.env` gitignored; đã tự
sửa bằng cách copy `.env` thật vào worktree cho phần còn lại của Task 8).

Sau khi Task 9 (bug fix, xem dưới) hoàn tất, chạy lại toàn bộ suite (bao gồm
test mới của Task 9): **887 passed, 4 skipped, 39 deselected, 0 error**
(worktree lúc này đã có `.env` nên lỗi `ODOO_URL` không còn xuất hiện — không
phải hồi quy biến mất, chỉ là môi trường đã đủ biến).

2 fixture nhị phân `tests/rag/fixtures/{bang_gia.xlsx,policy.docx}` bị chạm
nhiều lần trong quá trình chạy test lặp lại (tác dụng phụ đã biết) — luôn
`git checkout --` khôi phục trước khi commit.

## Bước 2 — Secret Langfuse thật

Sinh 6 secret thật (`LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`,
`LANGFUSE_ENCRYPTION_KEY`, `LANGFUSE_REDIS_AUTH`,
`LANGFUSE_CLICKHOUSE_PASSWORD`, `LANGFUSE_MINIO_ROOT_PASSWORD`) bằng
`secrets.token_hex()`/`secrets.token_urlsafe()`, ghi vào `.env` (không
commit — khớp `.gitignore`).

**Khác kế hoạch gốc ở đúng 1 điểm, đã được người dùng chấp thuận trước khi
làm:** thay vì đăng ký tài khoản thủ công trên UI Langfuse (Bước 5 gốc của
kế hoạch), phiên này không có công cụ trình duyệt nên đã dùng cơ chế
**headless initialization** chính thức của Langfuse (`LANGFUSE_INIT_*` env
var — xem `self-hosting/administration/headless-initialization` trong docs
Langfuse) để tự động tạo org/project/API key khi container `langfuse-web`
khởi động, qua một file `docker-compose.override.yml` **tạm thời, không
commit** (Docker Compose tự nạp file này cạnh `docker-compose.yml` nếu có
mặt — cơ chế override chuẩn của Compose, không đụng đến
`docker-compose.yml` đã được Task 7 review). File này đã bị xoá trước khi
commit báo cáo này (xem Bước 9).

Xác nhận project được tạo đúng qua API:
```
GET /api/public/projects (Basic Auth pk-lf-.../sk-lf-...)
→ {"data":[{"id":"youdoo-sp1c2-verify","name":"SP-1C2 live-verify",...}]}
```

## Bước 3 — Dựng hạ tầng

`postgres` đã chạy sẵn (container chia sẻ `youdoo-postgres`, healthy, từ
worktree `sp1b-port-business-layer` — đúng thiết kế "container tên cố định
dùng chung" của `docker-compose.yml`). Database `langfuse` tạo thành công
qua `scripts/create-langfuse-db.sh` (idempotent, xác nhận Task 7).

`docker compose --profile observability up -d` gặp xung đột tên container
với `postgres` (do container đó thuộc về một compose project KHÁC — mỗi
worktree có project riêng theo tên thư mục) — xử lý bằng
`docker network connect <project>_default youdoo-postgres --alias postgres`
(thao tác thuần mạng, không đụng dữ liệu/không restart container) rồi khởi
động CHỈ 5 service Langfuse (`--no-deps`, không đụng service `postgres` của
project này). Đây là hệ quả của việc chạy nhiều worktree song song trên cùng
máy, không phải lỗi của `docker-compose.yml`.

Kết quả `docker compose --profile observability ps`: `clickhouse`,
`minio`, `redis` đều `healthy`; `langfuse-web`, `langfuse-worker` đều `Up`
(đúng kỳ vọng — 2 service này không có healthcheck riêng trong compose).

## Bước 4 — `main.py` chạy được

```
GET /health → {"status":"ok","agent_ready":true}
```
(Gặp 1 sự cố môi trường không liên quan mã nguồn: chạy `python run.py` qua
`nohup ... > file` trên Windows dùng codepage `cp1252` mặc định, làm
`UnicodeEncodeError` khi in ký tự `✓` — sửa bằng `PYTHONIOENCODING=utf-8`
khi khởi động, không phải sửa code.)

## Bước 5 — API key Langfuse

Xem Bước 2 — dùng headless init thay vì UI, đã disclose rõ.

## Bước 6 — Câu hỏi thật

Request:
```json
{"messages":[{"role":"user","content":"Xin chào, bạn có thể giúp gì?"}]}
```
Response (nguyên văn, thật):
```json
{"id":"chatcmpl-b2f29ba5897f47b3a933eae1","object":"chat.completion","created":1785416176,
 "choices":[{"index":0,"message":{"role":"assistant","content":
 "Xin chào! Tôi là trợ lý ERP nội bộ, rất vui được hỗ trợ bạn.\n\nTôi có thể giúp bạn thực hiện các công việc sau:\n* **Tra cứu thông tin:** Đơn hàng, tồn kho, chi tiết khách hàng và nhà cung cấp.\n* **Tìm kiếm tài liệu:** Các chính sách và hướng dẫn nội bộ của công ty.\n* **Xử lý đơn từ:** Tạo mới hoặc chỉnh sửa báo giá, đơn mua hàng và điều chỉnh tồn kho.\n\nBạn cần tôi hỗ trợ điều gì cụ thể hôm nay không? Hãy cho tôi biết nhé!"},
 "finish_reason":"stop"}],"usage":{...}}
```
Không phải `ERROR_MSG` — câu trả lời hợp lý, đúng vai trò trợ lý ERP.

(Ghi chú môi trường: gửi tiếng Việt có dấu qua `curl -d '...'` trực tiếp
trong Git Bash bị lỗi mã hoá `UnicodeDecodeError` phía server — nguyên nhân
là shell/codepage Windows làm hỏng byte UTF-8 khi truyền qua argument dòng
lệnh, KHÔNG phải lỗi `main.py`. Sửa bằng cách ghi payload JSON ra file UTF-8
rồi `curl --data-binary @file` — không phải sửa mã nguồn.)

## Bước 7 — Xác nhận trace + PHÁT HIỆN LỖI QUAN TRỌNG (dẫn tới Task 9)

**Lượt chạy đầu (trước Task 9):** trace xuất hiện đúng — cây span lồng nhau
đúng thật (`LangGraph` → `intent_router` → `ChatGoogleGenerativeAI`, →
`_route_by_intent` → `respond_unknown` → `ChatGoogleGenerativeAI`) — nhưng
**KHÔNG span nào mang metadata định tuyến** (`role`/`alias`/`provider`/
`upstream`/`fallback_depth`/`budget_verdict`/`est_tokens`/`actual_tokens`)
mà Task 2/3 được thiết kế để gắn. Log backend xác nhận lý do — dòng này nổ
ra đúng 2 lần, khớp 2 lượt gọi LLM thật trong trace:
```
Context error: No active span in current context. Operations that depend on
an active span will be skipped.
```

**Nguyên nhân gốc (xác nhận bằng đọc mã nguồn cài đặt thật, không suy
đoán):** `tracing.annotate_current_span()` (thiết kế Task 2/3) đọc "current
span" qua `opentelemetry.trace.get_current_span()` — một giá trị theo ngữ
cảnh (contextvars) ambient. `CallbackHandler` của Langfuse gắn span "current"
bằng `context.attach()` bên trong các hook ĐỒNG BỘ (`on_llm_start`/
`on_llm_end`). Khi LangChain dispatch một callback handler không đồng bộ
(mặc định `run_inline=False`), nó chạy các hook đồng bộ đó qua
`loop.run_in_executor(None, functools.partial(copy_context().run, event, ...))`
(xác nhận trực tiếp trong `langchain_core/callbacks/manager.py`, hàm
`_ahandle_event_for_handler`) — TRONG MỘT LUỒNG KHÁC, trên MỘT BẢN SAO
context. `context.attach()` bên trong bản sao đó không bao giờ lan ngược về
coroutine đang gọi `RoutedChatModel.ainvoke()` — nên mọi lệnh gọi
`update_current_span()` sau đó đều thấy "không có span nào đang mở".

**Quyết định:** người dùng chọn mở task sửa ngay (không hoãn) → **Task 9**:
thay `annotate_current_span()` bằng
`routed_span()`/`annotate_span()` — `RoutedChatModel` tự dựng và tự giữ tham
chiếu TRỰC TIẾP tới một span riêng, gắn metadata thẳng lên đối tượng đó,
không tra "current" ở đâu cả. Đã review (spec ✅, code quality ✅), 1 fix
round (chặn network call thật trong test mới bằng
`should_export_span=lambda span: False`), review lại sạch.

**Lượt chạy lại (sau Task 9 — backend khởi động lại để nạp code mới):**
```
grep "Context error" backend log → KHÔNG còn dòng nào (trước đây có 2 dòng mỗi lượt)
```
Câu hỏi thật gửi lại, trả lời hợp lý (không phải `ERROR_MSG`). Trace mới,
đọc qua API:
```
GET /api/public/v2/observations?traceId=445f197c64695b00b7e23bf9dd63bc45&fields=core,basic,metadata
→ {"id":"99cb0d654a10c272","type":"SPAN","name":"route:router",
   "parentObservationId":null,"isRootObservation":true,
   "metadata":{"role":"router","alias":"gemma-4-26b","provider":"google",
               "upstream":"google","fallback_depth":0,"budget_verdict":[],
               "est_tokens":228,"actual_tokens":316, ...}}
```
**Metadata đúng và đủ 8 field, giá trị thật khớp quyết định định tuyến thật
của lượt gọi đó** (vai "router", model "gemma-4-26b", không tụt bậc nào,
228 token ước tính / 316 token thật). Đây là bằng chứng bằng mắt (qua API,
không qua UI trình duyệt — phiên này không có công cụ trình duyệt, người
dùng đã chấp thuận tự động hoá qua API thay vì "xem UI bằng mắt" theo nghĩa
đen của spec, xem trao đổi trong phiên làm việc) rằng cơ chế gắn metadata
CUỐI CÙNG đã hoạt động đúng trong đường chạy sống thật.

**GIỚI HẠN ĐÃ BIẾT, CHẤP NHẬN Ở PHẠM VI SP-1C2 NÀY (theo quyết định người
dùng):** span `route:*` mang metadata đúng nhưng xuất hiện như MỘT TRACE
GỐC RIÊNG (`parentObservationId: null`, `traceId` khác với trace hội thoại
thật `LangGraph`/`intent_router`/...), KHÔNG lồng vào trong cây trace của
lượt hội thoại. Nguyên nhân: việc gắn span cha cho `routed_span()` cũng dựa
vào "current span" ambient (qua `start_as_current_observation()`), nên chịu
đúng loại giới hạn context-propagation nói trên — cơ chế nối cây ĐÚNG của
Langfuse (dùng `run_id`/`parent_run_id` tường minh do LangChain truyền qua
tham số hàm, không qua ambient context) không được tái tạo ở bản sửa này.

Hệ quả thực tế: metadata định tuyến VẪN tra cứu được đầy đủ, chính xác qua
API/UI Langfuse (mở đúng project, tìm đúng span theo tên `route:<role>` hoặc
theo khoảng thời gian) — nhưng KHÔNG hiện cùng một trace với nội dung hội
thoại thực tế của lượt chat đó, nên không "click 1 trace, thấy hết" như kỳ
vọng thiết kế gốc. Nếu cần khắc phục, hướng đi đúng là thay `routed_span()`
bằng một `BaseCallbackHandler` tự viết, dùng `run_id`/`parent_run_id` tường
minh (tham số hàm, không phải context) để nối đúng span cha — việc này để
ngỏ cho một vòng làm việc sau nếu observability trở thành ưu tiên cao hơn.

**Mức độ nghiêm trọng thật (bổ sung sau review toàn nhánh cuối cùng, Task
10):** mô tả "không tiện tra cứu" ở trên nhẹ hơn thực tế. Span `route:*`
KHÔNG mang bất kỳ khoá tương quan nào với hội thoại — không chung `traceId`,
không `session_id`/`user_id`/`thread_id`, chỉ có timestamp + `role`. Với
NHIỀU LƯỢT CHAT ĐỒNG THỜI cùng vai (vd nhiều user cùng hỏi qua vai "router"
cùng lúc), KHÔNG THỂ xác định span `route:router` nào ứng với hội thoại nào
— đây không chỉ là bất tiện tra cứu, mà là KHÔNG THỂ tương quan dưới tải
đồng thời.

Hướng khắc phục rẻ hơn cách đã đề xuất ở trên (tự viết `BaseCallbackHandler`
riêng): tiêm `role`/`alias`/`provider`/`upstream`/`fallback_depth`/
`est_tokens`/`budget_verdict` thẳng vào `config["metadata"]` trước khi gọi
`self._client(...).ainvoke()` trong `Router.invoke()`/`ainvoke()`
(`router.py`) — CallbackHandler của Langfuse đã tự đọc `metadata` từ
LangChain run và gắn đúng field đó lên ĐÚNG span GENERATION nó tạo bên trong
trace thật (cơ chế parent-linkage riêng của SDK, không qua ambient context,
không chịu giới hạn context-propagation nói trên). `actual_tokens` Langfuse
đã tự bắt qua usage tracking nội bộ của chính CallbackHandler, không cần
tiêm lại. Đây là khuyến nghị cho một vòng làm việc sau, CHƯA làm ở phạm vi
Task 10 này.

## Bước 8 — Đối chiếu "SP-1C2 xong" (spec §7)

1. ✅ `main.py`/`run.py` chạy được, `/health`/`/v1/chat/completions` trả lời
   đúng qua curl (xác nhận thật, 2 lượt — trước và sau Task 9).
2. ✅ `tracing.py` có test chứng minh no-op an toàn ở mọi nhánh lỗi (Task 2,
   giữ nguyên; Task 9 thêm test OTel thật xác nhận cơ chế gắn metadata làm
   việc đúng qua context thật, không mock).
3. ✅ `RoutedChatModel.ainvoke()`/`.invoke()` gọi đúng cơ chế gắn metadata —
   xác nhận LẠI bằng chạy sống thật sau Task 9 (không chỉ bằng test), với
   giới hạn đã ghi ở Bước 7 (span tách trace riêng).
4. ⚠️ Trace/span đúng, metadata đúng — nhưng KHÔNG lồng chung 1 trace với
   hội thoại (giới hạn đã biết, người dùng chấp thuận chấp nhận cho phạm vi
   này). Xác nhận qua API (không qua UI trình duyệt bằng mắt theo nghĩa
   đen — phiên này tự động hoá hoàn toàn, người dùng đã chấp thuận).
5. ✅ profile `observability` không ảnh hưởng `docker compose up` mặc định
   (Task 7, xác nhận lại: `docker compose config --services` mặc định chỉ
   ra `postgres`).
6. ✅ Test suite 2 chế độ xanh, không hồi quy (884→887 passed sau khi thêm
   test Task 9, đúng 1 lỗi môi trường đã biết trước khi có `.env`, hết lỗi
   sau khi có `.env`).

## Bước 9 — Dọn dẹp

- Dừng `python run.py` (backend) và `python server.py` (MCP Odoo).
- `docker compose --profile observability down` (giữ `postgres` chạy —
  container chia sẻ, không phải của riêng worktree này).
- Ngắt kết nối mạng thủ công đã tạo giữa `youdoo-postgres` và network của
  project này (`docker network disconnect`).
- Xoá `docker-compose.override.yml` (tạm thời, dùng cho headless init —
  không phải một phần deliverable, không commit).
- `.env` của worktree này giữ lại 6 secret Langfuse thật đã sinh (không
  commit, khớp `.gitignore`) — cần sinh lại nếu dựng lại hạ tầng observability
  ở một phiên làm việc khác (secret hiện tại gắn với project
  `youdoo-sp1c2-verify` cụ thể của phiên xác nhận này).

## Kết luận

SP-1C2 đạt yêu cầu chính: HTTP endpoint OpenAI-compatible hoạt động đúng qua
curl thật, Langfuse tracing hoạt động (trace hiện đúng cây span, không throw
lỗi, không ảnh hưởng lượt chat khi Langfuse tắt/lỗi), và metadata định tuyến
cuối cùng gắn đúng và tra cứu được thật (sau khi Task 8 phát hiện và Task 9
sửa một lỗi context-propagation nghiêm trọng mà toàn bộ unit test trước đó
không phát hiện được). Giới hạn còn lại (span metadata tách trace riêng,
không lồng chung hội thoại) đã ghi rõ, người dùng chấp thuận chấp nhận cho
phạm vi này.
