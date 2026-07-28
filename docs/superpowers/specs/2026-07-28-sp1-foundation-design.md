# SP-1 Foundation — Thiết kế

- **Ngày:** 2026-07-28
- **Trạng thái:** Đã duyệt, sẵn sàng lập kế hoạch triển khai
- **Bối cảnh gốc:** [ADR-010 — Multi-Agent Upgrade Context Handoff](../../ADR-010-multi-agent-upgrade-context.md)
- **Repo nguồn để port:** `D:\Project` (ERP AI Assistant, ~22k dòng Python / 176 file)

---

## §0. Mục đích và phạm vi

SP-1 dựng nền móng cho repo `YOUdoo-assistant`: gateway/fallback 3 nhà cung cấp
cloud, tracing bằng Langfuse, và port tầng tool/security/RAG từ repo cũ.

**SP-1 tồn tại để trả lời đúng một câu hỏi:** *đổi model chat từ `qwen3:8b`
local sang cloud API thì 7 bộ eval của SP-0 dịch chuyển ra sao?*

Mọi quyết định phạm vi trong tài liệu này đều suy ra từ câu đó. Nguyên tắc chi
phối: **mỗi lần chỉ đổi một biến.** Bất cứ thứ gì đổi song song với cú flip
model — embedding, topology graph, hành vi planner — đều làm delta eval mất
khả năng quy trách nhiệm, nên bị đẩy sang sau.

Phạm vi đã chốt: **substrate + một đường chat tối thiểu chạy được**. Không có
đường chat thật thì không re-run được 6 baseline SP-0, mà ADR-009 QĐ M3 bắt
buộc eval-gate trước mọi cú flip model/prompt. Langfuse cũng không có gì để
trace.

---

## §1. Kiến trúc và bố cục repo

### Nguyên tắc chi phối

**`src/llm/` là tầng duy nhất biết đến nhà cung cấp LLM.** Không tầng nào khác
biết Google / Groq / OpenRouter tồn tại.

Đây là khuôn repo cũ đã dùng thành công hai lần: `transport.py` mang dây nối
Odoo còn `gateway.py` mang chính sách; `models.py` giữ mọi model ID để logic
nghiệp vụ không hardcode. SP-1 lặp lại khuôn đó cho tầng provider.

Quy tắc phụ thuộc, một chiều:

- `llm/` **không biết gì** về ERP, RAG, Odoo. Nhận vai trò + ước lượng token,
  trả về client đã chọn.
- `agents/` phụ thuộc `llm/`.
- `erp_query/` và `rag/` **không** phụ thuộc `llm/` — trừ `rag/embed.py`, vốn
  có nhà cung cấp riêng của nó.

Hệ quả: `llm/` test được bằng provider giả, không cần Odoo hay Postgres.

### Bố cục

```
YOUdoo-assistant/
├── .gitignore                     commit #1 — .env, models.csv, .venv, __pycache__
├── .env.example
├── docker-compose.yml             postgres · ollama · [profile: observability] langfuse
│                                  (ollama phục vụ embedding lâu dài, và chat
│                                   một lần cuối cho bước re-baseline — §8)
├── docs/
│   ├── ADR-010-multi-agent-upgrade-context.md   (đã có)
│   ├── ADR-011-sp1-foundation.md                nơi ghi mọi quyết định SP-1 không được lật lại
│   ├── provider-quotas.md                       bảng hạn mức đã đo — KHÔNG chứa key
│   └── superpowers/specs/
├── backend/
│   ├── src/
│   │   ├── llm/                   MỚI — trái tim SP-1
│   │   │   ├── catalog.py             model · hạn mức · upstream thật
│   │   │   ├── budget.py              kế toán RPM / TPM / RPD
│   │   │   ├── router.py              vai trò → model, quyết định fallback
│   │   │   ├── providers.py           3 client OpenAI-compatible
│   │   │   └── tracing.py             Langfuse handler, degrade êm
│   │   ├── agents/                port: graph lõi + write tier-1 + security gates
│   │   ├── erp_query/             port gần như nguyên văn
│   │   ├── rag/                   port + embed.py đặt sau interface
│   │   └── main.py                port FastAPI OpenAI-compatible
│   ├── evals/                     port + sửa fabricated_number + re-baseline
│   ├── jobs/
│   └── tests/
└── mcp-servers/odoo/              port + chẻ server.py 1865 dòng theo domain
```

### Quyết định: SP-1 thay thế QĐ M2 của ADR-009

`backend/src/agents/models.py` ở repo cũ có:

```python
CLOUD_ALLOWED = frozenset({"router", "evaluator", "chitchat"})
```

QĐ M2 (đánh dấu **KHÓA**) ghim `read` / `planner` / `fusion` / `synthesis` vào
local vĩnh viễn vì chúng mang dữ liệu nghiệp vụ.

**SP-1 phá khóa đó, có chủ đích.** Bỏ Ollama khỏi đường chat nghĩa là 4 vai kia
không còn chỗ nào chạy ngoài cloud.

Lý do (chủ dự án xác nhận 2026-07-28, ghi nguyên văn vì mạnh hơn cách ADR-010
diễn đạt): **dữ liệu Odoo trong project này là dữ liệu demo**, và bản thân
project là demo/portfolio. Đây không phải "tạm gác rủi ro" mà là "không có rủi
ro để gác". Nếu sau này dùng API trả phí thật thì mới cần quan tâm.

Dữ kiện liên quan, ghi lại để phiên sau khỏi tra: tier **trả phí** của Anthropic
và OpenAI mặc định không dùng dữ liệu API để huấn luyện; **free tier của Google
AI Studio thì có** — điều khoản Unpaid Services nói rõ Google dùng nội dung để
cải thiện sản phẩm. Nên ranh giới "free demo giờ / trả phí thật sau" là ranh
giới đúng.

**Yêu cầu triển khai:** `models.py` mới **phải** mang khối bình luận nói thẳng
rằng QĐ M2 bị SP-1 thay thế có chủ đích, kèm trỏ tới ADR-010/ADR-011. Không có
nó, một phiên nào đó sáu tháng sau sẽ đọc M2, tưởng có lỗ hổng, và "sửa" nó.
Đây là áp dụng trực tiếp standing rule cuối ADR-010.

---

## §2. Gateway `src/llm/`

### `catalog.py` — bảng model, nguồn sự thật duy nhất

```python
@dataclass(frozen=True)
class ModelSpec:
    alias: str              # tên code gọi
    provider: str           # google | groq | openrouter
    model_id: str           # ID gốc phía provider
    upstream: str           # MIỀN LỖI THẬT
    quota_scope: str        # "model" | "account"
    rpm: int | None
    tpm: int | None
    rpd: int | None
    token_multiplier: float # hiệu chỉnh đếm token theo provider
    weight: str             # heavy | light
    max_output_tokens: int | None   # thay hằng số 4096 ghim cho qwen3:8b
    timeout_s: int                  # thay nhánh is_qwen()
    supports_tools: bool            # prompt-guard / whisper (SP-2, SP-4) thì False
    emits_thought_tags: bool        # họ Gemma nhả <thought> vào content
```

Bốn trường sinh ra từ đo đạc ngày 2026-07-28 (chi tiết ở Phụ lục A):

- **`upstream`** — miền lỗi thật, không phải tên provider. `or-ling` có
  `provider="openrouter"` nhưng `upstream="novita"`.
  `google/gemma-4-31b-it:free` **bị loại khỏi catalog** kèm bình luận giải
  thích: đo được 429 với `provider_name: "Google AI Studio"`, tức
  `upstream="google"` — xếp nó sau Gemini trong một chuỗi fallback là tự lừa
  mình.
- **`quota_scope`** — Google và Groq tính hạn mức **theo từng model**;
  OpenRouter free tính **theo tài khoản**, dùng chung cho mọi model free.
  Thiếu trường này thì sổ ngân sách cộng sai cho OpenRouter.
- **`token_multiplier`** — Groq đếm 133 token cho request mà Google đếm 57
  (cùng payload). Với trần 8K TPM, ước lượng lệch 2.3 lần là gọi thẳng vào 429.
  Giá trị khởi tạo là số đo tay; §5 mô tả cách hiệu chỉnh bằng dữ liệu thật.
- **`max_output_tokens` / `timeout_s`** — thay hai chỗ hardcode theo qwen3:8b
  trong `models.py` cũ (xem §3).

**Phát hiện về sức chứa:** vì hạn mức tính theo từng model, `Gemma 4 26B` và
`Gemma 4 31B` có **hai ví 14.4K RPD riêng biệt** (cộng lại 28.8K lượt/ngày);
`Gemini 3.5 Flash Lite` và `3.1 Flash Lite` mỗi cái 500 RPD. Các vai được **cố
ý rải sang model anh em** để tiêu hai ví thay vì một.

### `budget.py` — bộ kế toán hạn mức

```python
class BudgetLedger:
    def can_afford(spec, est_tokens) -> Verdict   # ok | rpm | tpm | rpd | cooldown
    def record(spec, prompt_tokens, completion_tokens, total_tokens)
    def cooldown(spec, seconds)
```

**`total_tokens` là con số có thẩm quyền, KHÔNG phải `prompt + completion`.**
Đo được ngày 2026-07-28: `gemma-4-26b-a4b-it` trả
`prompt_tokens: 11, completion_tokens: 36, total_tokens: 337` — có ~290 token
"thinking" **không xuất hiện trong `completion_tokens` nhưng vẫn bị tính vào
tổng**. Cộng hai thành phần sẽ đếm thiếu **7 lần**, tức sổ báo còn hạn mức
trong khi ví đã cạn. `prompt_tokens`/`completion_tokens` vẫn lưu để chẩn đoán,
nhưng mọi phép kiểm TPM/TPD dùng `total_tokens`.

Bốn quyết định cần giữ nguyên:

**Cửa sổ trượt 24h, không phải "ngày lịch".** Google reset lúc nửa đêm giờ Thái
Bình Dương, Groq và OpenRouter giờ khác — ba múi giờ là ba con bug đang chờ.
Cửa sổ trượt chỉ có một cách hiện thực và luôn *thận trọng hơn* mức thật. Giá
phải trả: hơi bi quan ngay sau một đợt dùng dồn. Chấp nhận.

**Một bảng Postgres duy nhất cho cả ba cửa sổ.**
`llm_usage(ts timestamptz, alias text, provider text, upstream text,
prompt_tokens int, completion_tokens int)`, index `(alias, ts)` và
`(provider, ts)`. RPM/TPM/RPD đều là `WHERE ts > now() - interval ...`. Không
cache, không sổ kép — ở lưu lượng vài nghìn lượt/ngày Postgres làm việc này
không tốn gì, mà một cơ chế thì không bao giờ lệch với chính nó.

**Gộp theo `quota_scope`.** `quota_scope == "model"` (Google, Groq) → gộp theo
`alias`. `quota_scope == "account"` (OpenRouter) → gộp theo `provider`, tức mọi
model free của OpenRouter chia chung một ví. Đây là lý do cột `provider` phải
có trong bảng, không suy ra từ `alias` lúc truy vấn.

**Ước lượng token trước khi gọi.** `tiktoken` với encoding `cl100k_base`
(`tiktoken` đã là dependency sẵn) trên toàn bộ messages + JSON schema của tool,
rồi nhân `spec.token_multiplier`. Đây là ước lượng, không phải phép đo — nên
`record()` ghi cả `est_tokens` lẫn `actual` từ trường `usage` của response, và
span Langfuse mang cả hai (§5) để hiệu chỉnh `token_multiplier` bằng dữ liệu
thật thay vì con số đo tay ban đầu.

**Postgres chết → fail-OPEN, cho gọi.** Ngược với `write_gate.py` vốn
fail-closed, và lý do khác nhau nên không mâu thuẫn: `write_gate` chặn thao tác
**ghi ERP không hoàn tác được**, mơ hồ thì phải khóa. Budget chỉ bảo vệ khỏi một
cái **429 tự lành**, mà fallback chain đã xử lý sẵn. Fail-closed ở đây là đánh
sập cả hệ thống để bảo vệ một hạn mức miễn phí — sai tỉ lệ.

### `providers.py` — ba client

**Cập nhật sau spike Task 1 (2026-07-28), thay cho bản gốc "cả ba đều
`ChatOpenAI` qua base_url riêng":** spike đo hội thoại tool 2 lượt thật qua
endpoint OpenAI-compat của Google và thấy vòng lặp **không hội tụ** — Google
trả lỗi `400 INVALID_ARGUMENT` ngay lượt 2 vì thiếu `thought_signature`
trong `functionCall` (chi tiết: `docs/spikes/2026-07-28-thought-signature.md`).
`ChatOpenAI` không mang trường này qua lượt kế tiếp được vì nó không thuộc
schema OpenAI. Quyết định: Google chuyển sang client native
`langchain-google-genai` / `ChatGoogleGenerativeAI`; Groq và OpenRouter giữ
nguyên `ChatOpenAI` vì cả hai đều hội tụ bình thường qua đường OpenAI-compat.

| provider | client | base_url / cách gọi |
|---|---|---|
| google | `ChatGoogleGenerativeAI` (native, gói `langchain-google-genai`) | SDK tự quản lý endpoint `generativelanguage.googleapis.com` |
| groq | `ChatOpenAI` | `https://api.groq.com/openai/v1` |
| openrouter | `ChatOpenAI` | `https://openrouter.ai/api/v1` |

Groq và OpenRouter vẫn OpenAI-compatible và giữ được tool-calling tiếng Việt
(đã đo — Phụ lục A). Đây vẫn là lý do SP-1 **không** dùng LiteLLM cho hai
provider này: giá trị "hợp nhất giao thức" của nó đã bốc hơi, còn bài toán
thật — kế toán hạn mức free-tier theo ngày — lại đúng chỗ LiteLLM yếu nhất.

Vì ba client giờ **không cùng một lớp**, `client_for()` (Task 7) phải phân
nhánh theo `spec.provider` thay vì dựng một `ChatOpenAI` chung với `base_url`
khác nhau theo provider. `langchain-google-genai` được thêm vào
`backend/requirements.txt`.

### `router.py` — vai trò → model

```python
def resolve(role, est_tokens, pin: str | None = None) -> ModelSpec
def invoke(role, messages, tools)   # resolve → gọi → lỗi thì cooldown + tụt
```

**Chuỗi theo vai**, rải cố ý sang model anh em:

| Vai | Trọng lượng | Chuỗi |
|---|---|---|
| `router` | nhẹ, tần suất cao nhất | `gemma-4-26b` → `groq-gpt-oss-20b` → `or-ling` |
| `chitchat` | nhẹ | `gemma-4-31b` → `groq-gpt-oss-20b` |
| `evaluator` | nhẹ, chạy theo lô | `groq-gpt-oss-20b` → `gemma-4-26b` |
| `planner` | vừa, nhạy đúng-sai | `gemini-3.5-flash-lite` → `groq-gpt-oss-120b` → `or-nemotron` |
| `read` | nặng (ngữ cảnh RAG) | `gemini-3.5-flash-lite` → `groq-llama-3.3-70b` → `or-nemotron` |
| `fusion` | nặng | `gemini-3.1-flash-lite` → `groq-llama-3.3-70b` |
| `synthesis` | nặng | `gemini-3.1-flash-lite` → `groq-llama-3.3-70b` → `or-nemotron` |

Cơ sở phân vai: **gán provider theo trọng lượng token của vai, không theo chuỗi
"primary → fallback" chung chung.** Ràng buộc thật của Groq là TPM chứ không
phải RPM — một lượt synthesis có RAG tốn ~3–4K token input, nên ở trần 8K TPM
chỉ chạy được ~2 request/phút, trong khi RPM 30 còn chưa dùng tới 1/15. Ai
thiết kế theo RPM sẽ bị TPM đánh úp.

**Ba bất biến, ép bằng unit test trên chính CATALOG + CHAINS:**

1. Trong một chuỗi, **không hai mắt xích nào chung `upstream`**.
2. Mọi alias trong chuỗi đều tồn tại trong catalog.
3. Vai `heavy` chỉ dùng model có `tpm >= 12_000`. Ngưỡng này chọn theo số đo:
   một lượt synthesis có RAG tốn ~3–4K token input, và 12K là mức của
   `groq-llama-3.3-70b` — mắt xích Groq duy nhất đủ sức gánh vai heavy.
   `gpt-oss-*` ở 8K bị loại khỏi vai heavy đúng bởi bất biến này.

### Chuẩn hoá đầu ra: gỡ `<thought>` của họ Gemma

Đo được 2026-07-28: `gemma-4-26b-a4b-it` và `gemma-4-31b-it` nhả nguyên khối
`<thought>…</thought>` vào **trường `content`** qua endpoint OpenAI-compat —
câu trả lời thật nằm ngay sau thẻ đóng. `gemini-3.5/3.1-flash-lite` **không**
bị. Và thinking **không tắt được**: đặt `reasoning_effort` trả
`400 "Thinking budget is not supported for this model"`.

Vì `chitchat` và `router` chạy Gemma, không gỡ thì người dùng nhìn thấy phần
suy nghĩ thô trong câu trả lời.

Nên gateway gỡ **tất định** phần `<thought>…</thought>` ở đầu `content` cho mọi
spec có `emits_thought_tags=True`. Cùng hình dạng với `tool_leak_guard.py` đã
có: một cú scrub tất định tại ranh giới, vì định dạng model trả về không đáng
tin. Không dùng prompt để nhờ model đừng làm vậy.

Trường hợp biên phải xử lý: thiếu thẻ đóng (bị cắt giữa chừng) → coi như toàn
bộ `content` là suy nghĩ, trả chuỗi rỗng để node gọi degrade về `SAFE_MSG`,
chứ không trả nửa khối suy nghĩ cho người dùng.

### Chế độ ghim (bắt buộc)

Thiết kế trên đẻ ra một rủi ro mới: **cùng một câu hỏi có thể được trả lời bởi
3 model khác nhau tuỳ trạng thái ngân sách lúc đó.** Eval trở nên nhiễu và bug
report khó tái hiện.

Nên `resolve()` có tham số `pin`: khi chạy eval, bỏ qua fallback chain, ép đúng
một model. **Eval phải đo một model, không đo một trạng thái ngân sách.** Thiếu
điều này thì toàn bộ phép so sánh với baseline SP-0 mất giá trị.

### Giữ nguyên hình dạng code đã port

Code `agents/` cũ gọi `self._llms["read"].invoke(...)` với object dựng sẵn một
lần; nhưng ngân sách đổi theo từng lượt nên không dựng sẵn được. Giải pháp:
`RoutedChatModel` là một `Runnable` của LangChain, **giải quyết model tại thời
điểm invoke**. `make_llms()` trả dict các `RoutedChatModel`. Nhờ vậy toàn bộ
`agents/` port sang không phải sửa dòng nào ở chỗ gọi LLM.

### Rủi ro đã chọc: `thought_signature` (chốt ở Task 1, 2026-07-28)

Google trả `extra_content.google.thought_signature` **bên trong** `tool_calls`.
Gemini 3 dùng chữ ký này để giữ mạch suy luận qua nhiều lượt tool.

Spike `backend/spikes/spike_thought_signature.py` chạy hội thoại tool 2 lượt
thật qua `ChatOpenAI` → Google (`gemini-3.5-flash-lite`, endpoint
OpenAI-compat). Kết quả quan sát được: `ChatOpenAI` không mang
`thought_signature` đi qua lượt kế tiếp, và Google từ chối ngay ở lượt 2 với
lỗi `400 INVALID_ARGUMENT — "Function call is missing a thought_signature in
functionCall parts"` — vòng lặp **không hội tụ**. Output đầy đủ và quyết định
chi tiết: `docs/spikes/2026-07-28-thought-signature.md`.

Đường lui đã dùng: Google chuyển sang `langchain-google-genai` native
**chỉ riêng cho Google** — ba client trong `providers.py` (mục trên) không
còn cùng một lớp. `client_for()` (Task 7) phải phân nhánh theo
`spec.provider`. Agent ERP sống bằng tool loop nên đây không phải chi tiết
nhỏ.

---

## §3. Port ba tầng

### Sang gần như nguyên văn

- `src/erp_query/` toàn bộ 15 file — `gateway.py` (4 guard), `transport.py`,
  6 module domain, `tools.py`, `resolve.py`, `semantic.py`, `envelope.py`
- Security gates: `write_gate.py`, `agentic_gate.py`, `write_registry.py`,
  `skill_gate.py`, `tool_leak_guard.py`
- Graph lõi `src/agents/`: `state`, `prompts`, `nodes`, `graph`, `erp_agent`,
  `confirmation`, `continuation`, `disambiguation`, `friction`,
  `erp_grounding`, `synthesis`, `fusion`, `tool_result`, `working_context`,
  `create_order`, `edit_order`, và 6 write node (bom / crm / inventory / mrp /
  purchase / returns)
- `src/rag/` trừ `embed.py`

### Sửa khi port — đúng bốn chỗ

| File | Sửa gì |
|---|---|
| `agents/models.py` | Thành mặt tiền mỏng trên `llm/router.py`. Bỏ `CLOUD_ALLOWED` kèm khối bình luận supersession QĐ M2 (§1). `max_tokens` planner và timeout đọc từ `catalog.py` |
| `rag/embed.py` | Interface + `OllamaEmbedder` (bật) + `GeminiEmbedder` (tắt) + marker `embedding_model`/`dim` trong schema |
| `mcp-servers/odoo/server.py` | Chẻ theo domain |
| `evals/cases.py` + `run_eval.py` | Sửa basis `fabricated_number`; thêm biến thể chạy `multi_source` lượt hai |

#### Hai chỗ hardcode theo qwen3:8b phải gỡ

`models.py:47-72` có `max_tokens = 4096` cho vai `planner` — circuit breaker
cho vòng sinh không dừng đã xác nhận của qwen3:8b (quan sát 7000+ token). Con
số 4096 hiệu chỉnh riêng cho model đó: ~3.3 lần nhu cầu hợp lệ cao nhất đo
được (1250 token), ở tốc độ ~65 token/giây. Cả hai giả định — token "thinking"
vô hình và tốc độ sinh — đều không còn đúng với Gemini hay Groq. → chuyển thành
`max_output_tokens` theo model trong catalog. Vẫn là lưới an toàn thật, chỉ là
ngưỡng phải theo model chứ không phải hằng số ghim cho một model đã rời hệ
thống.

`models.py:45` có `timeout = 120 if is_qwen(name) else 30`. → `timeout_s` theo
model trong catalog.

#### `rag/embed.py`

Corpus nhỏ (17 tài liệu, 8.2MB, phần lớn là `seed/law/`) nên re-index qua
Gemini chỉ tốn 30–60 phút — chi phí không phải rào cản. Rào cản là **đo đạc**:
đổi embedding cùng lúc đổi LLM là đổi hai biến, `read` và `multi_source` lệch
đi thì không quy được cho biến nào.

Nên: hai implementation, `OllamaEmbedder` (bge-m3, 1024-dim) **bật mặc định**,
`GeminiEmbedder` viết sẵn nhưng tắt. Sau khi eval-gate của cú flip LLM đi qua,
lật embedding là **thí nghiệm thứ hai, đo riêng**.

Model ID Gemini embedding đã xác nhận tồn tại qua `GET /v1beta/models`:
`gemini-embedding-001`, `gemini-embedding-2-preview`, `gemini-embedding-2`.

Lưu ý kỹ thuật: embedding Gemini **bất đối xứng** (`task_type` phân biệt
`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) trong khi bge-m3 đối xứng. `embed.py`
hiện đã tách `embed_texts()` / `embed_query()` — đúng hình dạng cần có.

**Marker chống lệch:** schema RAG mang `embedding_model` + `dim`. Provider đang
bật mà lệch với marker trong DB → **fail lớn tiếng lúc khởi động**, app không
lên. Trả kết quả retrieval rác một cách im lặng tệ hơn nhiều so với không chạy.

### Chẻ MCP server

```
mcp-servers/odoo/
├── server.py          chỉ còn khởi tạo FastMCP + đăng ký + chạy
├── odoo_call.py       hàm odoo() — 5 cổng bảo mật, cửa DUY NHẤT ra Odoo
├── security.py  rate_limit.py  audit_chain.py  event_log.py  helpers.py  config.py
└── tools/
    └── sales.py  purchase.py  inventory.py  mrp.py  crm.py  accounting.py
```

Lý do chẻ (không phải refactor lạc đề): SP-2 cần cấp cho mỗi specialist agent
một tập tool hẹp riêng — đường cắt theo domain chính là đường biên SP-2 sẽ
dùng.

**Bất biến bảo vệ cú chẻ, ép bằng test:** duyệt registry FastMCP, với mỗi tool
đã đăng ký lấy `inspect.getsource()` và khẳng định nó không nhắc `ServerProxy`
hay `execute_kw` trực tiếp — mọi đường ra Odoo phải qua `odoo_call.odoo()`.
Chẻ file là lúc dễ đánh rơi một guard nhất.

### Hoãn sang SP-2 — không port

3 agentic SOP skill tier-2 (`skill_agentic_delivery`,
`skill_agentic_discount_quote`, `skill_agentic_warehouse_receiving`) cùng
`agentic_registry.py`, `agentic_context_sync.py`, và phần wiring của chúng
trong `graph.py`.

Lý do: chúng không nằm trong bất kỳ bộ nào trong 7 eval set, và chúng **chính
là hình dạng "specialist agent"** mà SP-2 sẽ dựng lại. Port vào một cấu trúc
sắp bị thay là công toi.

**Để không hiểu nhầm:** 32 MCP tool vẫn port đủ. Thứ hoãn là các *node graph*
điều phối chúng, không phải bản thân tool. `tool_leak_guard.py` và
`skill_gate.py` port nhưng nằm im tới SP-2 — chúng bé, và mất chúng đắt hơn
giữ.

### `fusion` giữ nguyên qua SP-1

`fusion` là nhánh intent `mixed` — một ReAct agent được bind sẵn cả tool đọc
ERP lẫn `search_documents`, cho câu hỏi cần đồng thời tài liệu nội bộ và dữ
liệu ERP sống.

Nó **sẽ** biến mất ở SP-2 (đã ghi sẵn trong `evals/cases.py:325` từ SP-0):
orchestrator tự dispatch 2 nguồn rồi tổng hợp. Nhưng không phải ở SP-1, vì lý
do một-biến: `multi_source` có số "trước" đo trên qwen3:8b *với topology
fusion*.

Cũng lưu ý: xoá node không xoá phần việc. `cite_and_verify` (footer trích dẫn
tất định), `verify_erp_grounding` (kiểm tra chống bịa đối chiếu tool output),
`passes_floor` (lọc retrieval lạc đề), bộ lọc `WRITE_TOOL_NAMES` (giữ nhánh
read-only) đều nằm ở `synthesis.py` dùng chung. Bỏ `fusion` là **dời** đám máy
móc đó, không phải bỏ.

**SP-1 biến phỏng đoán thành phép đo:** chạy `multi_source` hai lượt — một qua
fusion như cũ, một qua cờ thử nghiệm định tuyến `mixed` → agent-đủ-tool-một-nốt.
Tốn một lượt eval, đổi lại SP-2 quyết định gộp nhánh bằng số liệu thay vì giả
định.

---

## §4. Chat path

`src/main.py` port nguyên: `/v1/chat/completions` (streaming và không),
`/v1/models`, `/health`. Open WebUI cắm vào như cũ.

Bổ sung: `/health` báo **trạng thái ngân sách từng model** — còn bao nhiêu RPD,
model nào đang cooldown.

---

## §5. Langfuse

**Hạ tầng:** self-host, `docker-compose.yml` profile `observability` —
`langfuse-web`, `langfuse-worker`, `clickhouse`, `redis`, `minio`. Postgres
dùng chung instance đã có, schema riêng. `docker compose up` mặc định không kéo
theo nhóm này.

Chọn self-host thay vì Langfuse Cloud vì hai lẽ. Một, **trace không cùng loại
rủi ro với API call**: quyết định gác data-egress ở ADR-010 nói về lời gọi API
thoáng qua, còn Langfuse Cloud là **kho lưu trữ tập trung, tìm kiếm được, tồn
tại lâu dài** của mọi nội dung ERP đi qua hệ thống. Hai, SP-3 là chạy tải dưới
fan-out — một request multi-agent sinh 10–20+ observation, nên hạn mức
observation/tháng sẽ cắn đúng lúc cần nhất. Máy đủ sức: RAM 31.8 GB (trống
15.7), ổ D: trống 406 GB.

**`src/llm/tracing.py`:** `get_handler()` trả `CallbackHandler` của Langfuse,
hoặc **no-op** nếu thiếu env hoặc không kết nối được. Không có đường nào để
tracer làm hỏng một lượt chat. Gắn ở tầng LangChain lúc invoke graph → mỗi node
LangGraph thành một span lồng nhau.

**Thuộc tính span tuỳ biến** — mục tiêu: một trace tự trả lời được câu *"vì sao
lượt này chạy Groq chứ không phải Gemini?"*

- `role` · `alias` · `provider` · `upstream`
- `fallback_depth` — 0 là lựa chọn đầu
- `budget_verdict` của **những mắt xích bị bỏ qua**: `rpd_exhausted`,
  `tpm_exhausted`, `cooldown`
- `est_tokens` so với `actual_tokens` — khép vòng hiệu chỉnh
  `token_multiplier` bằng dữ liệu thật thay vì số đo tay

Lấy mẫu 100% ở SP-1. SP-3 mới là lúc bàn sampling.

---

## §6. Xử lý lỗi

Hai nguyên tắc, mọi ô trong bảng đều suy ra từ chúng:

- **Lỗi tạm thời của một nhà cung cấp** → chuyển hướng, im lặng, ghi trace.
- **Lỗi cấu hình lệch lạc** → chết ngay lúc khởi động, thật ồn ào.

| Sự cố | Ứng xử |
|---|---|
| Provider trả 429 | cooldown alias đó, tụt xuống mắt xích kế |
| Provider 5xx / timeout | như trên, cooldown ngắn hơn |
| **Cạn cả chuỗi** cho một vai | canned message tiếng Việt (mẫu `SAFE_MSG` đã có), trace ghi `chain_exhausted`. Không bao giờ ném stack trace ra người dùng |
| Postgres (sổ ngân sách) chết | **fail-open** — cho gọi (§2) |
| Langfuse chết | handler thành no-op |
| Ollama (embed) chết | RAG fail → node degrade về `SAFE_MSG`, hành vi cũ port nguyên |
| **embedding model ≠ marker trong DB** | **chết lúc khởi động**, app không lên |
| alias trong chuỗi không có trong catalog | chết lúc khởi động |
| Odoo chết | envelope error hiện có, port nguyên |
| Model trả tool call méo | `_parse_plan_tiered` hiện có, port nguyên |

---

## §7. Kiểm thử

**1. Unit, không chạm mạng** — phần đáng giá nhất, và là lý do §2 chọn Python
thuần thay vì YAML của LiteLLM:

- `budget.py` — cửa sổ trượt, lăn qua mốc 24h, `quota_scope` account
  (OpenRouter) khác model (Google/Groq), fail-open khi PG chết
- `router.py` — chọn mắt xích đầu đủ ngân sách, tụt khi cooldown, xử lý cạn
  chuỗi, **chế độ ghim**
- `catalog.py` — ba bất biến ở §2, chạy trên chính CATALOG thật
- Provider giả, không chạm mạng

**2. Contract test có mạng, `@pytest.mark.live`** — không chạy trong CI thường:

- Mỗi provider: request tool-calling → khẳng định
  `finish_reason == "tool_calls"`
- **Hội thoại tool 2 lượt qua Google** → chốt rủi ro `thought_signature`.
  Chạy sớm nhất có thể
- `GET /v1beta/models` + `/openai/v1/models` → khẳng định mọi `model_id` trong
  catalog còn tồn tại. Đây là cái bắt được lúc provider khai tử một model free,
  thường là lặng lẽ

**3. Bộ test hiện có** — port ~90 file. Lưới an toàn cho cú port và cú chẻ MCP.

**4. Bất biến MCP** — mọi tool đã đăng ký không tham chiếu `ServerProxy` /
`execute_kw` trực tiếp.

---

## §8. Eval gate — trình tự bắt buộc

1. Sửa basis của `fabricated_number` trong `evals/cases.py` — hiện so với raw
   chunk text thay vì context có nhãn section mà model thực sự thấy. Hướng sửa
   đã ghi sẵn tại `cases.py:317-321`: đổi basis thành
   `_digits(_format_context(chunks))`, và/hoặc whitelist số ngày-tháng suy ra
   được từ phép tính hợp lệ.
2. **Re-baseline `qwen3:8b`** với scanner đã sửa → số "trước" hợp lệ.
3. Chạy 7 eval set trên cấu hình cloud, **ghim model** từng vai.
4. So sánh, hard gate như SP-0.
5. Chạy `multi_source` lượt hai với cờ gộp nhánh → dữ liệu cho SP-2.

**Cảnh báo về thứ tự:** bước 2 là **lần cuối cùng repo cần Ollama chạy model
chat**. Sau đó Ollama chỉ còn phục vụ embedding. Đừng gỡ đường chat Ollama
trước khi xong bước 2 — nghe hiển nhiên, nhưng đây đúng là loại việc dễ làm sai
thứ tự rồi mất luôn khả năng đo "trước".

---

## §9. Bí mật và cấu hình

- **`.gitignore` là commit #1**, trước dòng code đầu tiên: `.env`, `models.csv`,
  `.venv*`, `__pycache__`, `*.key`
- `.env.example` — placeholder cho `GOOGLE_API_KEY`, `GROQ_API_KEY`,
  `OPENROUTER_API_KEY`, `LANGFUSE_*`, `DATABASE_URL`, `ODOO_*`
- `models.csv` tách đôi: **khoá** → `.env`; **bảng hạn mức** →
  `docs/provider-quotas.md`. Bảng hạn mức là **dữ kiện thiết kế** —
  `catalog.py` phải khớp với nó, nên nó thuộc về file tracked (standing rule
  ADR-010)
- Không khoá nào nằm trong `catalog.py`

Tình trạng lúc viết spec: `models.csv` chứa key thật của cả 3 provider, đã đo
được là **untracked và chưa vào lịch sử git** → không cần xoay key.

---

## §10. Phi mục tiêu

| Hoãn tới | Hạng mục |
|---|---|
| SP-2 | orchestrator / multi-agent / fan-out |
| SP-2 | 3 agentic SOP skill tier-2 |
| SP-2 | prompt-guard rail ở input + chunk RAG |
| SP-2 | structured output / JSON mode cho planner |
| SP-2 | gộp nhánh `mixed` (nhưng SP-1 **đo** giúp) |
| SP-3 | siết quota dưới tải fan-out |
| SP-4 | meeting agent |
| sau eval-gate | lật embedding sang Gemini — code có, cờ tắt |

### Quyết định: không dùng NVIDIA NeMo Guardrails

Đã xét và **loại**, ba lý do:

1. **Ăn đúng thứ khan hiếm nhất.** Phần lớn rail của NeMo hoạt động bằng cách
   gọi thêm LLM. Một input rail + một output rail = 2 lượt gọi thêm mỗi turn.
   Trên ngân sách mà Gemini Flash chỉ có 20–500 RPD, đó là nhân ba mức tiêu
   thụ tài nguyên hiếm nhất.
2. **Xác suất, trong khi chỗ này đã tất định và tốt hơn.** `agentic_gate`
   không *kiểm tra* xem model có gọi tool ghi bậy không — nó làm tool ghi
   **không tồn tại** trong tầm với của model. Execution rail của NeMo là bước
   lùi từ "bất khả" xuống "được kiểm tra". Triết lý này đã viết sẵn trong
   `tool_leak_guard.py`: prompt "chỉ có xác suất tuân theo".
3. **Hai thẩm quyền điều khiển luồng** — Colang có runtime luồng hội thoại
   riêng, đặt cạnh LangGraph.

**Nhưng khoảng trống nó chỉ ra là có thật:** repo hiện không có gì che
**prompt injection**, cả ở đầu vào người dùng lẫn — nguy hiểm hơn — **qua tài
liệu RAG**. Câu trả lời rẻ hơn nhiều đã có sẵn trên Groq free tier:
`meta-llama/llama-prompt-guard-2-22m` / `-86m`, classifier chuyên trị
jailbreak/prompt-injection, 22–86 triệu tham số.

→ Ghi thành mục tiêu **SP-2**. SP-1 chỉ cần cho hai model đó vào `catalog.py`
sẵn để lúc dùng không phải đụng hạ tầng.

### Nguyên tắc: guard nào co được, guard nào không

> **Guard bù cho sự kém cỏi thì co lại được. Guard ràng buộc thẩm quyền thì
> không.**

`agentic_gate` không tồn tại vì qwen3:8b ngu; nó tồn tại vì **ghi vào Odoo
không hoàn tác được**. Model mạnh hơn là model *giỏi hơn* trong việc tìm ra
đường đi chưa lường tới — nên ràng buộc thẩm quyền nếu có gì thì càng cần hơn.

| | Hạng mục | Xử lý |
|---|---|---|
| **Bớt** | `planner max_tokens=4096` | → catalog theo model (§3) |
| **Bớt** | `is_qwen()` → timeout 120s/30s | → catalog theo model (§3) |
| **Bớt** | 4 nhánh intent `erp_read`/`rag`/`mixed` | SP-2, có số đo từ lượt eval thứ hai |
| **Giữ, hạ ưu tiên** | `_parse_plan_tiered` salvage-parse/retry | Cloud khá hơn nhiều, nhưng xoá error handling vì "model giờ giỏi rồi" là kiểu lạc quan sẽ cắn lại. Giữ, đừng đầu tư thêm |
| **Không đụng** | `gateway.py` 4 guard, `write_gate` fail-closed, `agentic_gate` confirm-gate, `_reject_ref_shaped_partner_names` | Ràng buộc thẩm quyền |
| **Không đụng** | Ghi luôn tuần tự | Tính chất của Odoo (race condition), không phải của model |

---

## §11. "SP-1 xong" nghĩa là

1. `docker compose up` → postgres + ollama lên; thêm profile `observability` →
   Langfuse lên
2. Backend chạy, Open WebUI hỏi được, câu trả lời đi qua cloud model
3. **Chặn Google giữa chừng → tự tụt sang Groq, trace ghi `fallback_depth: 1`**
   ← bài nghiệm thu của cả SP-1
4. Langfuse hiện cây span lồng nhau, và một trace tự trả lời được câu "vì sao
   lượt này chạy Groq"
5. 7 eval set chạy được với model ghim, có bảng so sánh trước/sau
6. Toàn bộ test đã port đều xanh
7. `git log` không chứa khoá nào

---

## §12. Rủi ro đã biết

| Rủi ro | Mức | Đối sách |
|---|---|---|
| `ChatOpenAI` nuốt `thought_signature` của Gemini 3 → tool loop nhiều lượt hỏng | Cao (đã xác nhận, Task 1 — 2026-07-28) | Google chuyển sang `langchain-google-genai` / `ChatGoogleGenerativeAI` native; xem `docs/spikes/2026-07-28-thought-signature.md` |
| Gemma nhả `<thought>` vào `content` → lộ suy nghĩ thô ra người dùng | Cao (đã xác nhận) | Scrub tất định ở gateway theo cờ `emits_thought_tags`; thiếu thẻ đóng → trả rỗng để node degrade |
| Kế toán token thiếu 7× trên Gemma | Cao (đã xác nhận) | Sổ ngân sách dùng `total_tokens`, không cộng `prompt + completion` |
| Groq 8K TPM chặn synthesis có RAG ngữ cảnh lớn | Trung bình | Vai heavy đặt Google đứng đầu chuỗi; `token_multiplier` chặn ước lượng lệch |
| Chẻ `server.py` 1865 dòng làm rơi một security guard | Trung bình | Bất biến source-scan (§3) + bộ test đã port |
| Re-baseline cần Ollama + qwen3:8b sống | Trung bình | Thứ tự bắt buộc ở §8; không gỡ Ollama trước bước 2 |
| Provider khai tử model free, lặng lẽ | Thấp | Contract test đối chiếu catalog với `/models` |
| OpenRouter ~50 req/ngày cạn nhanh dưới fan-out | Thấp ở SP-1 | Chỉ dùng làm mắt xích cuối; SP-3 xử lý thật |

---

## Phụ lục A — Số đo ngày 2026-07-28

Ba key trong `models.csv` đều xác nhận hoạt động.

### Bảng hạn mức (từ `models.csv`, sẽ chuyển vào `docs/provider-quotas.md`)

| Provider | Model | RPM | TPM | RPD |
|---|---|---|---|---|
| Google | Gemini 3.5 Flash Lite | 15 | 250K | **500** |
| Google | Gemini 3.1 Flash Lite | 15 | 250K | **500** |
| Google | Gemini 2.5 / 3 / 3.5 / 3.6 Flash | 5 | 250K | **20** ← gần như vô dụng |
| Google | Gemma 4 26B | 30 | 16K | **14.4K** |
| Google | Gemma 4 31B | 30 | 16K | **14.4K** |
| Groq | openai/gpt-oss-120b | 30 | **8K** | 1K (TPD 200K) |
| Groq | openai/gpt-oss-20b | 30 | **8K** | 1K (TPD 200K) |
| Groq | llama-3.3-70b-versatile | 30 | **12K** | 1K (TPD 100K) |
| OpenRouter | 4 model free | — | — | ~50/ngày, **theo tài khoản** |

### Kết quả thí nghiệm

- **Cả 3 provider đều OpenAI-compatible và giữ được tool-calling tiếng Việt.**
  Google qua `v1beta/openai/chat/completions` trả `finish_reason: tool_calls`
  đúng chuẩn. → giá trị "hợp nhất giao thức" của LiteLLM bốc hơi.
- **Google nhét `extra_content.google.thought_signature` vào trong
  `tool_calls`** → rủi ro §12.
- **Groq đếm token nặng tay hơn:** cùng payload, Groq `prompt_tokens: 133` vs
  Google `57` (≈2.3×). Với trần 8K TPM đây là chênh lệch thật.
- **`google/gemma-4-31b-it:free` trên OpenRouter trả 429 với
  `provider_name: "Google AI Studio"`** — nó proxy ngược về chính Google, dùng
  chung hồ hạn mức. → sinh ra trường `upstream` và bất biến #1 ở §2.
- **Model OpenRouter thật sự độc lập miền lỗi:**
  `inclusionai/ling-3.0-flash:free` (upstream Novita) và
  `nvidia/nemotron-3-super-120b-a12b:free` (upstream Nvidia) — cả hai tool-call
  bình thường.
- **Google có sẵn 3 model embedding:** `gemini-embedding-001`,
  `gemini-embedding-2-preview`, `gemini-embedding-2`.
- **Groq host sẵn `whisper-large-v3` + `whisper-large-v3-turbo`** — ghi lại cho
  SP-4: có thể bỏ nhu cầu GPU cục bộ cho meeting agent.
- **Groq có `qwen/qwen3.6-27b`, `llama-3.1-8b-instant`,
  `openai/gpt-oss-safeguard-20b`** — chưa có trong `models.csv`, hạn mức chưa
  xác nhận.

### Model ID đã xác nhận tồn tại (`GET /v1beta/models`, `/openai/v1/models`)

| Provider | model_id |
|---|---|
| Google | `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `meta-llama/llama-prompt-guard-2-22m`, `meta-llama/llama-prompt-guard-2-86m`, `whisper-large-v3`, `whisper-large-v3-turbo` |
| OpenRouter | `inclusionai/ling-3.0-flash:free`, `nvidia/nemotron-3-super-120b-a12b:free` |

### Hành vi `<thought>` và kế toán token

| Model | `<thought>` rò vào `content` | `p+c` vs `total_tokens` |
|---|---|---|
| `gemini-3.5-flash-lite` | Không | 48 = 48 |
| `gemini-3.1-flash-lite` | Không | 48 = 48 |
| `gemma-4-26b-a4b-it` | **Có** | 47 vs **337** (thiếu 7.2×) |
| `gemma-4-31b-it` | **Có** | 45 vs **315** (thiếu 7.0×) |

Không tắt được: `reasoning_effort=none` → `400 "Thinking budget is not
supported for this model"`; `reasoning_effort=low` → `400 "Thinking level is
not supported for this model"`.

**Gemma 4 CÓ hỗ trợ tool-calling** — `finish_reason: tool_calls` hoạt động.
Lo ngại ban đầu (họ Gemma thường không có function calling) là sai với Gemma 4.

### Đính chính cần đưa vào ADR-010

ADR-010 viết *"summarization cho meeting agent giao Groq (nhanh với văn bản
dài)"*. Với trần 8K TPM, một transcript họp dài **không lọt nổi một request**.
Việc của SP-4, nhưng nên sửa ghi chú sớm.

---

## Phụ lục B — Các quyết định phải ghi vào file tracked

Theo standing rule cuối ADR-010 (*"quyết định nào phiên sau không được lật lại
thì phải có bình luận trong file tracked, ngay tại điểm code nó chi phối"*):

| Quyết định | Ghi ở đâu |
|---|---|
| QĐ M2 bị thay thế có chủ đích | Khối bình luận đầu `agents/models.py` |
| `google/*:free` bị loại vì `upstream=google` | Bình luận trong `catalog.py` |
| Budget fail-open (ngược `write_gate` fail-closed) | Bình luận trong `budget.py` |
| Dùng `total_tokens`, không cộng `p+c` (Gemma thiếu 7×) | Bình luận trong `budget.py` |
| Scrub `<thought>` vì Gemma không tắt được thinking | Bình luận trong `providers.py` |
| Cửa sổ trượt 24h thay vì ngày lịch | Bình luận trong `budget.py` |
| `fusion` giữ qua SP-1, bỏ ở SP-2 | Đã có sẵn `evals/cases.py:325` |
| Loại NeMo Guardrails, chọn prompt-guard cho SP-2 | ADR-011 |
| Bảng hạn mức là dữ kiện thiết kế | `docs/provider-quotas.md` |
| Lý do bỏ LiteLLM | ADR-011 |
