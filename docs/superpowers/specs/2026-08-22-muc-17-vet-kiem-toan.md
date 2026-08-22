# Mục 17 — vệt kiểm toán trả lời được AI ĐÃ GỌI và GỌI CÁI GÌ

**Ngày**: 2026-08-22. **Nhánh**: `main`.

## 1. Đề bài

`mcp_call_log` ghi `caller = mcp-odoo/<vai>` (tên tiến trình). Nó trả lời được
"AI vai nào", **không** trả lời được ai đã yêu cầu, cũng không nói được lệnh gọi
mang tham số gì. Sau một sự cố, đó đúng là hai câu hỏi đầu tiên.

## 2. Việc đã làm

| # | thay đổi | tệp |
|---|---|---|
| 1 | `args_fingerprint()` — sha256 (16 ký tự) + **tên** tham số, không có giá trị | `mcp-servers/odoo/audit_chain.py` |
| 2 | `compute_entry_hash` băm thêm `http_user`, `args_digest`, `args_keys` | cùng tệp |
| 3 | `_http_user()` đọc header qua `request_ctx` (không nhập `server.py` ⇒ không vòng nhập) | `event_log.py` |
| 4 | 7 lời gọi log trong `odoo()` đều mang dấu vân tay, kể cả nhánh `permission_denied` | `odoo_call.py` |
| 5 | `_COLUMNS` của bên KIỂM khớp bên GHI | `verify_audit_chain.py` |
| 6 | ContextVar `NGUOI_DUNG_HIEN_TAI` + interceptor gắn header theo TỪNG lượt | `backend/src/agents/erp_agent.py` |
| 7 | Migration 005: lưu trữ + 3 cột + dọn + dòng `chain_reset` | `backend/migrations/005_…sql` |
| 8 | conftest chặn bộ test ghi vào bảng thật | `backend/tests/mcp/conftest.py` |

Đường truyền danh tính đã **đo trước khi viết**, bằng một máy chủ FastMCP tí hon
ở cổng riêng: có interceptor ⇒ tool đọc được id; không có ⇒ `None`.

## 3. Nghiệm thu sống (sau khi khởi động lại cả 4 tiến trình)

Gọi `find_my_activities` qua tiến trình MCP **thật** (:8003), hai lượt:

| ngữ cảnh | `http_user` ghi vào bảng | `args_digest` | `args_keys` |
|---|---|---|---|
| có người dùng | `db5db1c8-3a8a-4bc8-9e88-bd8551dae252` | `54a89a823f04a3ff` | `['fields','limit','order']` |
| không có | `None` | `54a89a823f04a3ff` | `['fields','limit','order']` |

Ca thứ hai là **đối chứng**: nếu header xuất hiện ở cả hai thì giá trị đến từ
đâu đó khác, và phép đo không đo interceptor.

Chuỗi hash, phép thử phá trên dữ liệu thật:

```
KIEM CHUOI            : True  — OK, 2 dòng, chuỗi nguyên vẹn
SAU KHI SUA http_user : False — Chuỗi đứt tại id=2698: entry_hash không khớp
SAU KHI TRA LAI       : True  — OK, 2 dòng, chuỗi nguyên vẹn
```

## 4. ⚠️ Hai lần tôi kết luận sai trong chính đợt này

### 4.1 "Bộ test làm bẩn bảng" → tự rút lại → hoá ra ĐÚNG

Đo lần một: `tests/mcp/` thêm 0 dòng ⇒ tôi tuyên bố giả thuyết của mình sai.

Đo lần hai (sau khi chạy migration): `tests/mcp/` thêm **10 dòng** (5 tool × 2,
từ `test_fail_prefix_thieu_ten.py` — tệp không có marker nên chạy trong bộ mặc
định và cố ý làm `odoo()` ném).

Vì sao lần một đọc ra 0: **đường ghi lúc đó đã chết** — tôi vừa thêm ba cột vào
câu INSERT mà chưa chạy migration, và `log_mcp_event` nuốt mọi lỗi ghi. Tức phép
đo chạy qua một cơ chế đã hỏng và trả về con số trông như kết quả.

### 4.2 Thay đổi của tôi suýt giết vệt kiểm toán trong im lặng

Cùng nguyên nhân, nhìn từ phía khác: giữa lúc sửa xong code và lúc chạy
migration, `log_mcp_event` **không ghi được một dòng nào** và không có gì báo.
Đúng cách cơ chế này từng chết lần trước (đo 2026-08-14: bảng chưa từng tồn tại
và không ai biết). Chỉ bắt được vì tôi gọi thẳng `log_mcp_event` rồi đếm dòng
trước/sau, chứ không phải vì test hay log nào đỏ.

## 5. Phát hiện lớn ngoài đề bài: ĐƯỜNG ĐỌC KHÔNG CÓ VỆT KIỂM TOÁN NÀO

Sau khi mọi thứ đã chạy, một câu hỏi ERP thật qua cổng vào production (HTTP 200)
sinh ra **0 dòng** trong `mcp_call_log`.

Nguyên nhân: `erp_read` bind `build_erp_query_tools(role_cfg)`, và
`src/erp_query/transport.py` gọi Odoo bằng `ServerProxy`/`execute_kw` **của
riêng nó** — không đi qua MCP, nên không đi qua `odoo()`, nên không có
`log_mcp_event`. Cả 35 tool MCP đều là tool **ghi**; tool đọc duy nhất là
`find_my_activities`.

Nghĩa là:

* Vệt kiểm toán phủ **đường ghi**, hoàn toàn không phủ **đường đọc**.
* Câu hỏi "ai đã đọc công nợ khách hàng / bảng giá" hiện **không trả lời được**,
  và đó đúng là câu hỏi mà thảo luận RBAC tầng RAG (mục 19b) vừa nêu.

Chưa sửa — nó là một mục riêng, không phải phần mở rộng của mục 17.

## 6. Khó khăn / hướng đã chọn / giới hạn còn lại

**Khó khăn 1 — danh tính người dùng ở backend, log ở tiến trình khác.**
`SSEConnection.headers` chỉ đặt được lúc dựng kết nối, mà client dựng MỘT LẦN
mỗi vai lúc khởi động và dùng chung cho mọi người dùng của vai đó ⇒ header cố
định sẽ ghi sai tên vào vệt kiểm toán của mọi người. *Hướng đã chọn*:
`tool_interceptors` + `request.override(headers=…)` — đặt được theo TỪNG lượt.
*Giới hạn*: hằng tên header phải chép tay ở hai tiến trình; đã dựng test đối
chiếu hai chuỗi, vì trôi ở đây không làm hỏng gì thấy được (tool vẫn chạy,
`http_user` lặng lẽ về NULL mãi mãi).

**Khó khăn 2 — ContextVar qua LangGraph.** Đường từ `chat()` tới lời gọi tool đi
qua graph → node → `create_react_agent` → ToolNode, không chặng nào nhận thêm
tham số được. *Hướng đã chọn*: ContextVar, dựa vào việc asyncio **chép** ngữ
cảnh vào task con lúc tạo (chiều cha→con). *Giới hạn*: chiều con→cha KHÔNG chạy
— đợt tracing 2026-07 đã trả giá cho điều đó; ở đây chỉ cần chiều cha→con, và
nghiệm thu sống xác nhận.

**Khó khăn 3 — đứt chuỗi hash.** Thêm cột vào `compute_entry_hash` làm 2 671
dòng cũ không verify được. *Hướng đã chọn* (chủ dự án quyết): lưu trữ nguyên vẹn
sang `mcp_call_log_archive`, dọn bảng gốc, khởi động chuỗi mới từ genesis, và
**ghi lại chính việc dọn** thành một dòng `chain_reset` có `entry_hash` NULL —
nó đứng ngoài chuỗi nên không giả vờ là mắt xích, và việc xoá không diễn ra lén.
*Giới hạn*: mất tính liên tục qua mốc này. Có chủ đích, có ghi lại.

**Giới hạn của `args_keys`:** domain Odoo là tuple `("field","=",value)` chứ
không phải dict, nên **tên trường trong điều kiện lọc không được bóc ra**. Tham
số của `create`/`write` là dict nên chúng CÓ. Với mục đích kiểm toán (cái gì đã
bị GHI) đây là phía quan trọng hơn, nhưng khác biệt này cần biết trước khi ai đó
dựa vào `args_keys` để trả lời câu hỏi về đường đọc.
