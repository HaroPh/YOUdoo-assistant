# SP-1B — Port tầng nghiệp vụ: thiết kế

**Mục tiêu:** Mang `erp_query/`, `rag/`, security gates và graph lõi `agents/` từ
repo nguồn `D:\Project` sang Youdoo, nối vào tầng `llm/` đã dựng ở kế hoạch A,
và chẻ MCP server Odoo theo domain. Hết kế hoạch B, graph trả lời được câu hỏi
thật qua model cloud — chạy bằng pytest, chưa cần HTTP.

**Kế hoạch A đã xong** (merge `a188b08`): `backend/src/llm/` định tuyến vai trò →
model qua 3 nhà cung cấp free-tier với kế toán hạn mức và tụt mắt xích. Nhưng
chưa ai gọi nó. Kế hoạch B là bên gọi đầu tiên.

**Spec gốc:** [2026-07-28-sp1-foundation-design.md](2026-07-28-sp1-foundation-design.md)
§3 (Port ba tầng). Tài liệu này chi tiết hoá §3 thành thiết kế thực thi được, và
giải quyết vài mâu thuẫn giữa spec §3 với bảng tóm tắt cuối kế hoạch A.

---

## §0. Ranh giới B và C

Spec §3 xếp graph lõi vào "port gần như nguyên văn"; bảng tóm tắt của kế hoạch A
lại xếp "Graph lõi" vào kế hoạch C. **Hai chỗ này mâu thuẫn — quyết định: graph
thuộc kế hoạch B.**

Lý do không phải thẩm mỹ: `graph.py` import trực tiếp từ `agents/models.py` (file
đang sửa ở B) và từ `erp_query/`/`rag/` (cũng đang port ở B). Để graph lại cho C
nghĩa là C phải vá lại đúng đám import ấy lần nữa, và C sẽ vừa port graph vừa
dựng FastAPI/Langfuse/eval cùng lúc — lúc có lỗi thì không tách được "agent sai"
với "tracing sai".

### Thuộc kế hoạch B

| Hạng mục | Ghi chú |
|---|---|
| Làm cứng `RoutedChatModel` | Ba phát hiện kế hoạch A để lại — xem §5 |
| `rag/` trừ `embed.py` | Lá của đồ thị phụ thuộc, port trước |
| `rag/embed.py` | Viết lại: interface + 2 implementation + marker chống lệch |
| `erp_query/` — cả 15 file | `gateway.py` (4 guard), `transport.py`, 6 module domain, `tools.py`, `resolve.py`, `semantic.py`, `envelope.py` |
| Security gates | `write_gate`, `agentic_gate`, `write_registry`, `skill_gate`, `tool_leak_guard` |
| Graph lõi `agents/` | `state`, `prompts`, `nodes`, `graph`, `erp_agent`, `confirmation`, `continuation`, `disambiguation`, `friction`, `erp_grounding`, `synthesis`, `fusion`, `tool_result`, `working_context`, `create_order`, `edit_order`, và 6 write node |
| `agents/models.py` | Thành mặt tiền mỏng trên `llm/router.py` |
| Chẻ `mcp-servers/odoo/server.py` | 1865 dòng → `odoo_call.py` + `tools/` theo domain |
| `docker-compose.yml` | Youdoo chưa có file nào — xem §6 |
| 62 file test | Xem §4 |

### KHÔNG thuộc kế hoạch B

| Hoãn sang | Hạng mục | Lý do |
|---|---|---|
| C | `main.py` / FastAPI `/v1` | Kế hoạch B kết thúc ở "graph chạy qua pytest" |
| C | Langfuse `tracing.py` | Handler gắn ở tầng LangGraph lúc invoke graph |
| C | Eval harness (`tests/jobs/`, 13 file), `evals/cases.py`, gate 7 bộ | Xem §7 |
| C | `multi_source` lượt hai | Đi cùng eval |
| SP-2 | 3 skill agentic tier-2 + `agentic_registry.py` + `agentic_context_sync.py` | Spec §3: chúng CHÍNH LÀ hình dạng "specialist agent" SP-2 sẽ dựng lại. Port vào cấu trúc sắp bị thay là công toi |
| Thí nghiệm sau | Bật `GeminiEmbedder` | Nguyên tắc một-biến — xem §3b |

**Để không hiểu nhầm:** 32 MCP tool vẫn port đủ. Thứ hoãn là các *node graph*
điều phối 3 skill agentic, không phải bản thân tool. `tool_leak_guard.py` và
`skill_gate.py` port nhưng nằm im tới SP-2 — chúng bé, và mất chúng đắt hơn giữ.

---

## §1. Đồ thị phụ thuộc

Đã đo bằng cách quét import thật trong repo nguồn, không phỏng đoán:

```
rag/            ← không import gì nội bộ (lá)
  ↓
erp_query/      ← chỉ import ..rag
  ↓
agents/         ← import ..erp_query và ..rag
  ↑
llm/            ← đã có sẵn từ kế hoạch A; agents/ nối vào qua models.py

mcp-servers/odoo/   ← tiến trình riêng, nói chuyện qua SSE :8001.
                      KHÔNG import gì từ backend/src/, và ngược lại.
                      Chẻ nó độc lập hoàn toàn với phần còn lại.
```

Đồ thị nông và sạch — đó là lý do port từ dưới lên khả thi, và là lý do ba việc
`rag/` · `erp_query/` · chẻ MCP có thể đổi thứ tự cho nhau nếu một cái bị chặn.

---

## §2. Thứ tự thực thi

```
Bước 1   SPIKE (vứt đi): nối graph CŨ ở D:\Project vào llm/router.py của
         Youdoo, chạy 2–3 case eval thật, ghi lại cái gì vỡ khi đổi
         qwen3:8b → cloud. Đầu ra là HIỂU BIẾT, không phải code.

Bước 2   Làm cứng RoutedChatModel (§5), theo đúng những gì bước 1 phát hiện.

Bước 3   docker-compose cho Youdoo (§6) — cần trước khi verify được gì.

Bước 4   Port rag/ + 9 test của nó.
Bước 5   Viết lại rag/embed.py (§3b) + test_embed.py.
Bước 6   Port erp_query/ (15 file) + 13 test.
Bước 7   Chẻ mcp-servers/odoo/server.py (§3c) + test bất biến registry.
Bước 8   agents/models.py → mặt tiền (§3a) + viết lại test_models.py.
Bước 9+  Port graph agents/ + ~40 test.
Cuối     Đầu-cuối: câu hỏi thật → Odoo/RAG thật → model cloud thật → câu trả lời.
```

### Vì sao spike đứng trước

Giống hệt Task 1 của kế hoạch A. Ở kế hoạch A, spike phát hiện Google từ chối
cứng lượt 2 của vòng lặp tool với `400 INVALID_ARGUMENT` — một sự thật chi phối
toàn bộ `providers.py`, và nếu phát hiện muộn thì phải viết lại.

Ở đây rủi ro cùng hình dạng: **toàn bộ prompt, ngưỡng và cách xử lý đầu ra của
`agents/` được hiệu chỉnh cho qwen3:8b local.** Đã biết chắc một chỗ vỡ trước cả
khi bắt đầu (`.content` trả list thay vì string — §5), và nó được tìm ra bằng
cách đọc mã nguồn thư viện, không phải bằng cách chạy. Còn bao nhiêu chỗ cùng
loại thì chưa ai biết. Tìm ra chúng *giữa chừng* một cú port 60 file đắt hơn
nhiều so với tìm trước.

Spike phải trả lời được: định dạng prompt còn hợp không, `finish_reason` xử lý
đúng không, hình dạng tool-call có khác không, `.content` list-shape ảnh hưởng
tới node nào, và node nào giả định độ trễ/tốc độ sinh của model local.

---

## §3. Bốn điểm phải sửa khi port

Mọi thứ khác là cơ học. Bốn chỗ này là thiết kế thật.

### §3a. `agents/models.py` → mặt tiền mỏng

File hiện xuất mười thứ, nhưng **chỉ hai thứ thực sự được import ở đâu đó** (đã
quét cả cây nguồn):

| Bên gọi | Dùng gì |
|---|---|
| `agents/erp_agent.py:18,136` | `make_llms()` — gọi không tham số, đúng một lần trong `__init__` |
| `agents/graph.py:17,80` | `llms_from_single()` — chuẩn hoá về mapping cho test |

Nên mặt tiền đúng nghĩa mỏng:

```python
make_llms()            → llm/router.make_llms(build_router())
llms_from_single(llm)  → giữ nguyên (back-compat test, không biết gì về LLM)
```

**Xoá hết phần còn lại:** `LITELLM_URL`, `LITELLM_KEY`, `default_model()`,
`is_qwen()`, `model_for()`, `make_llm()`, `CLOUD_ALLOWED`.

**Hai chỗ hardcode theo qwen3:8b chuyển thành dữ liệu catalog:**

`models.py:72` có `max_tokens = 4096` cho vai `planner` — circuit breaker cho
vòng sinh không dừng đã xác nhận của qwen3:8b (quan sát 7000+ token). Con số hiệu
chỉnh riêng cho model đó: ~3.3 lần nhu cầu hợp lệ cao nhất đo được (1250 token),
ở tốc độ ~65 token/giây. Cả hai giả định — token "thinking" vô hình và tốc độ
sinh — đều không còn đúng với Gemini hay Groq. → dùng `spec.max_output_tokens`.

`models.py:45` có `timeout = 120 if is_qwen(name) else 30`. → dùng
`spec.timeout_s`.

Cả hai vẫn là lưới an toàn thật; chỉ là ngưỡng phải theo model chứ không phải
hằng số ghim cho một model đã rời hệ thống.

**Khối bình luận supersession (bắt buộc, spec Phụ lục B).** File giữ một khối
bình luận ghi rằng QĐ M2 của ADR-009 (`CLOUD_ALLOWED` — pin read/planner/fusion/
synthesis vào local vì privacy) bị **thay thế CÓ CHỦ ĐÍCH**, không phải bị quên:
bỏ Ollama khỏi đường chat nên 4 vai mang dữ liệu không còn chỗ nào ngoài cloud;
chấp nhận được vì dữ liệu Odoo là dữ liệu demo và project là demo/portfolio (chủ
dự án xác nhận 2026-07-28). Ghi kèm dữ kiện: tier trả phí của Anthropic/OpenAI
mặc định không dùng dữ liệu API để huấn luyện, còn free tier Google AI Studio thì
có — nên ranh giới "free demo giờ / trả phí thật sau" là ranh giới đúng. Lý do
đầy đủ ở [ADR-011](../../ADR-011-sp1-foundation.md) mục 1.

### §3b. `rag/embed.py` → interface + hai implementation

`OllamaEmbedder` (bge-m3, 1024-dim) **bật mặc định**; `GeminiEmbedder` viết sẵn
nhưng **tắt**.

Corpus nhỏ (17 tài liệu, 8.2MB) nên re-index qua Gemini chỉ tốn 30–60 phút — chi
phí không phải rào cản. **Rào cản là đo đạc:** đổi embedding cùng lúc đổi LLM là
đổi hai biến; `read` và `multi_source` lệch đi thì không quy được cho biến nào.
Sau khi eval-gate của cú flip LLM đi qua (kế hoạch C), lật embedding là thí
nghiệm thứ hai, đo riêng.

Lưu ý kỹ thuật: embedding Gemini **bất đối xứng** (`task_type` phân biệt
`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) trong khi bge-m3 đối xứng. `embed.py`
hiện đã tách `embed_texts()` / `embed_query()` — đúng hình dạng cần có.

Model ID Gemini embedding đã xác nhận tồn tại: `gemini-embedding-001`,
`gemini-embedding-2-preview`, `gemini-embedding-2`.

**Marker chống lệch (bắt buộc):** schema RAG mang `embedding_model` + `dim`.
Provider đang bật mà lệch với marker trong DB → **fail lớn tiếng lúc khởi động**,
app không lên. Trả kết quả retrieval rác một cách im lặng tệ hơn nhiều so với
không chạy. Cùng triết lý với `PostgresUsageStore` fail-loud khi thiếu migration
(kế hoạch A).

### §3c. Chẻ MCP server theo domain

`mcp-servers/odoo/server.py` hiện 1865 dòng. Các helper (`security.py`,
`rate_limit.py`, `audit_chain.py`, `event_log.py`, `helpers.py`, `config.py`) đã
là file riêng sẵn.

```
mcp-servers/odoo/
├── server.py          chỉ còn khởi tạo FastMCP + đăng ký + chạy
├── odoo_call.py       hàm odoo() — 5 cổng bảo mật, cửa DUY NHẤT ra Odoo
├── security.py  rate_limit.py  audit_chain.py  event_log.py  helpers.py  config.py
└── tools/
    └── sales.py  purchase.py  inventory.py  mrp.py  crm.py  accounting.py
```

**Không phải refactor lạc đề:** SP-2 cần cấp cho mỗi specialist agent một tập
tool hẹp riêng — đường cắt theo domain chính là đường biên SP-2 sẽ dùng.

**Bất biến bảo vệ cú chẻ, ép bằng test:** duyệt registry FastMCP, với mỗi tool đã
đăng ký lấy `inspect.getsource()` và khẳng định nó không nhắc `ServerProxy` hay
`execute_kw` trực tiếp — mọi đường ra Odoo phải qua `odoo_call.odoo()`. Chẻ file
là lúc dễ đánh rơi một guard nhất.

### §3d. `fusion` giữ nguyên qua SP-1

`fusion` là nhánh intent `mixed` — một ReAct agent bind sẵn cả tool đọc ERP lẫn
`search_documents`. Nó **sẽ** biến mất ở SP-2 (đã ghi sẵn trong
`evals/cases.py:325` từ SP-0): orchestrator tự dispatch 2 nguồn rồi tổng hợp.
Nhưng không phải ở SP-1, vì lý do một-biến: `multi_source` có số "trước" đo trên
qwen3:8b *với topology fusion*.

Xoá node không xoá phần việc: `cite_and_verify`, `verify_erp_grounding`,
`passes_floor`, bộ lọc `WRITE_TOOL_NAMES` đều nằm ở `synthesis.py` dùng chung.
Bỏ `fusion` là **dời** đám máy móc đó, không phải bỏ.

---

## §4. Chiến lược port test

Repo nguồn có **82 file test**. Phân loại theo quyết định ĐÃ CÓ trong spec, không
phải đánh giá mới từng file:

| Nhóm | Số file | Gồm những gì |
|---|---|---|
| **Bỏ** | 5 | `test_agentic_context_sync`, `test_agentic_registry`, `test_skill_agentic_delivery`, `test_skill_agentic_discount_quote`, `test_skill_agentic_warehouse_receiving` — test của module §0 đã nói không port |
| **Viết lại** | 2 | `test_models.py` (models.py thành mặt tiền), `test_embed.py` (embed.py thêm interface + 2 impl) |
| **Hoãn sang C** | 13 | Toàn bộ `tests/jobs/` — eval harness, thuộc kế hoạch C |
| **Port nguyên văn** | 62 | `tests/erp_query/` (13) + `tests/rag/` (9) + `tests/agents/` (38) + 2 file ở gốc `tests/` |

Kiểm lại số: tổng 82 = agents 44 + rag 10 + erp_query 13 + jobs 13 + gốc 2.
Port nguyên văn 62 = (44−5−1) + (10−1) + 13 + 2.

**`test_skill_gate.py` VẪN GIỮ** — `skill_gate.py` có port (nằm im tới SP-2), nên
test của nó cũng port.

### Quy tắc phân biệt lúc thực thi (quan trọng nhất)

- Test port sang mà đỏ vì **hạ tầng đổi** (LiteLLM → `llm/router`, qwen →
  catalog): sửa phần nối dây cho đúng.
- Test port sang mà đỏ vì **hành vi thật sự đổi**: **DỪNG LẠI ĐIỀU TRA.** Không
  sửa test cho xanh.

Phân biệt này chính là toàn bộ giá trị của việc port test. Một test bị sửa cho
xanh là một hồi quy được ký giấy thông hành.

---

## §5. Ba phát hiện kế hoạch A phải vá TRƯỚC khi port

Review toàn nhánh cuối kế hoạch A để lại năm vấn đề "Important" chưa vá, và ghi
rõ chúng là *điều kiện đầu vào* của kế hoạch B/C. Ba cái dưới đây chạm trực tiếp
vào việc port, nên vá ở bước 2, **trước** khi port graph — để khi port, lỗi nào hiện ra là
lỗi port thật, không phải lỗi mặt tiền. Vá sau thì mỗi lỗi đều phải điều tra hai
khả năng.

**(1) `.content` là LIST, không phải STRING, với cả hai model `gemini-3.x`.**
`langchain_google_genai` có nhánh `_is_gemini_3_or_later()` khớp tiền tố
`"gemini-3"` — đúng với cả `gemini-3.5-flash-lite` lẫn `gemini-3.1-flash-lite`.
Trên nhánh đó client phát ra khối `{"type": "text", ...}`, tức `.content` là
list. Hai model này đứng đầu **4 trong 7 chuỗi vai** (`read`, `planner`,
`fusion`, `synthesis`). Mọi code `agents/` làm `response.content.strip()` sẽ vỡ.
Không test nào hiện bắt được — mọi fake đều dùng content string.
→ Chuẩn hoá `.content` về string tại `RoutedChatModel`.

**(2) `last_decision` không an toàn đa luồng.** `make_llms()` dựng mỗi vai một
`RoutedChatModel` **một lần**, và `ERPAgent` là singleton dựng trong `lifespan`
của FastAPI — tức mọi request dùng chung. `last_decision` là biến instance gán
mỗi lượt `invoke()`, nên hai request cùng vai đua nhau; bên thua đọc được quyết
định của bên kia. Kế hoạch C chỉ định đúng `last_decision` làm móc đổ thuộc tính
span Langfuse.
→ Đổi sang `ContextVar` hoặc trả quyết định qua `config`/callback.

**(3) `invoke()` và `bind_tools()` nuốt mất tham số.** `invoke(self, input,
config=None, **kwargs)` không bao giờ chuyển tiếp `config` — mà trong LangChain,
`config` chính là đường callback/tag/metadata lan xuống runnable con, tức đúng
đường handler Langfuse của kế hoạch C sẽ dùng. `bind_tools(tools, **kwargs)` cũng
nhận rồi bỏ im lặng `tool_choice`, `parallel_tool_calls`… — một cú đổi hành vi
âm thầm tại chỗ gọi đã port, phá đúng cái tính chất "agents/ không phải sửa dòng
nào" mà nó tồn tại để giữ.
→ Chuyển tiếp `config` và `**kwargs` xuống client.

### Hai phát hiện còn lại — thuộc kế hoạch C, ghi ở đây để không rơi

- **Pool Postgres không có timeout tường minh** (`store.py`): DB không truy cập
  được thì mỗi lượt gọi chặn ~90 giây trước khi fail-open, chứ không fail nhanh.
  Chạm vào B nếu graph chạy với Postgres thật và có ai đó tắt DB giữa chừng.
- **`Router.ainvoke()` gọi Postgres đồng bộ** — chặn event loop dưới
  FastAPI/LangGraph async. Thuộc C (C sở hữu đường chat async).
- **`tiktoken` cần mạng lần dùng đầu nếu không có cache cục bộ** — chạy trên
  đường test MẶC ĐỊNH (`-m "not integration and not live"`), vốn phải không chạm
  mạng theo Global Constraints. Máy này đã có cache nên không lộ; **sẽ vỡ trên CI
  lạnh.** Phải đóng trước khi dựng CI.

---

## §6. Hạ tầng

Youdoo **chưa có `docker-compose.yml` nào.** Kế hoạch B verify bằng hạ tầng thật
(đã xác nhận cả ba đều chạy được: Odoo, Postgres+pgvector, Ollama+bge-m3), nên
định nghĩa hạ tầng phải tồn tại trong repo này — không thể mượn file của
`D:\Project`.

Chép từ compose nguồn, **bỏ hai service:**

| Service | Giữ? | Lý do |
|---|---|---|
| `postgres` (pgvector/pgvector:pg16) | Giữ | RAG cần pgvector; sổ ngân sách kế hoạch A cũng dùng Postgres |
| `ollama` | Giữ | `OllamaEmbedder` (bge-m3) bật mặc định ở §3b |
| `litellm` | **BỎ** | SP-1 đã bỏ LiteLLM (ADR-011 mục 2) — cả 3 nhà đã OpenAI-compatible |
| `open-webui` | **BỎ** | Giao diện chat, chỉ có nghĩa khi có `/v1` — kế hoạch C |

Odoo nằm ngoài compose, trỏ qua `ODOO_URL` (repo nguồn dùng
`host.docker.internal:8069`).

`.env.example` của Youdoo phải bổ sung: `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`,
`ODOO_PASSWORD`, `MCP_ODOO_URL`, và biến cấu hình RAG.

---

## §7. Eval gate — vì sao hoãn được

ADR-009 QĐ M3 nói eval-gate là **bắt buộc trước mọi cú đổi model/prompt**. Kế
hoạch B chính là cú đổi đó (qwen3:8b → cloud). Nhưng harness hoãn sang C.

**Điều này không vi phạm ADR**, vì cú flip chưa *có hiệu lực* cho tới khi kế
hoạch C mở `/v1` — hết kế hoạch B chưa ai gọi được hệ thống ngoài pytest. Kế
hoạch C dựng harness và chạy gate 7 bộ đối chiếu baseline qwen3:8b **trước khi**
mở endpoint. Gate vẫn đứng trước lúc ship, đúng chữ của ADR.

Đổi lại, kế hoạch B **không** được tuyên bố "không hồi quy" — nó chỉ tuyên bố
"port đúng, test cũ xanh, graph chạy được". Câu hỏi chất lượng để dành cho gate.

---

## §8. "Kế hoạch B xong" nghĩa là

1. Ba phát hiện §5 đã vá, có test.
2. `docker-compose.yml` + `.env.example` đủ để dựng hạ tầng từ repo Youdoo.
3. `rag/`, `erp_query/`, security gates, graph `agents/` đã port; 62 test cũ
   xanh; 2 test viết lại xanh.
4. `agents/models.py` là mặt tiền mỏng, không còn `CLOUD_ALLOWED`/LiteLLM/
   `is_qwen`, có khối bình luận supersession QĐ M2.
5. `rag/embed.py` có 2 implementation (Ollama bật, Gemini tắt) + marker chống
   lệch fail lớn tiếng.
6. MCP server đã chẻ theo domain; test bất biến registry xanh.
7. Đầu-cuối: một câu hỏi thật đi qua Odoo thật + RAG thật + model cloud thật và
   trả về câu trả lời đúng — chạy từ pytest, không cần server.

**Chưa làm được sau kế hoạch B:** chưa có HTTP endpoint, chưa có trace, chưa có
số eval. Đó là việc của C.

---

## §9. Rủi ro đã biết

| Rủi ro | Đường lui |
|---|---|
| Spike bước 1 phát hiện prompt qwen3 lệch nặng với model cloud | Prompt sửa được — nhưng nếu lệch tới mức phải viết lại nhiều node, dừng lại và tách thành kế hoạch riêng trước khi port tiếp |
| `.content` list-shape lan rộng hơn dự kiến (không chỉ 2 model Gemini) | Chuẩn hoá ở `RoutedChatModel` bọc hết mọi provider, không vá từng node |
| Chẻ MCP đánh rơi một guard bảo mật | Test bất biến registry (§3c) chạy trên MỌI tool đã đăng ký, không chỉ tool mới |
| Test port sang đỏ hàng loạt, không rõ do đâu | Quy tắc §4: hạ tầng thì sửa nối dây, hành vi thì dừng điều tra. Port theo tầng nên phạm vi nghi ngờ luôn hẹp |
| Hạn mức free-tier cạn giữa lúc port (RPD Gemini Lite = 500/ngày) | Sổ ngân sách kế hoạch A tự tụt mắt xích; nếu cạn cả chuỗi thì chờ cửa sổ trượt 24h |
