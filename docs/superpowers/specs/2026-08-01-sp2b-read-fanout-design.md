# SP-2b: Fan-out đường đọc — khai tử node `fusion` — thiết kế

**Mục tiêu:** Thay node `mixed` (một ReAct agent bịa riêng) bằng **fan-out hai
chân thu thập + một node tổng hợp**, dựng nên nguyên thuỷ join mà SP-2c sẽ
dùng lại — mà không đụng một ký tự nào vào lớp định tuyến SP-2a vừa gia cố.

**Bối cảnh:** SP-1 (gateway, tầng nghiệp vụ, `/v1`, Langfuse, eval harness) và
SP-2a (nền tảng SOP skill dạng thư mục) đã xong và merge vào `main`. Dòng
"SP-2b" trong lộ trình SP-2a gộp ba việc; spec này tách ra và chỉ nhận hai
việc đầu.

---

## §0. Vị trí trong lộ trình và phạm vi

| SP | Nội dung | Trạng thái |
|---|---|---|
| SP-1A / SP-1B / SP-1C | Gateway + tầng nghiệp vụ + `/v1` + Langfuse + eval gate | **xong, đã merge** |
| SP-2a | Nền tảng SOP skill dạng thư mục | **xong, đã merge** |
| **SP-2b** | *(spec này)* Fan-out đường đọc; node `fusion` chết | brainstorm xong |
| SP-2c | Supervisor nuốt `intent_router` | sau, chưa brainstorm |

### Vì sao tách SP-2b khỏi SP-2c

Dòng roadmap cũ gộp ba việc — *supervisor nuốt `intent_router`*, *fusion
chết*, *fan-out đường đọc*. Hai việc sau là **một** việc: node `mixed` hôm nay
chính là chỗ ghép hai nguồn, thay nó bằng fan-out thì `fusion` chết theo. Việc
đầu là loại khác hẳn: nó đổi **ai quyết định định tuyến**.

Tách ra vì bằng chứng, không vì thủ tục:

- SP-2a kết luận — có sự cố live 2026-07-16 làm bằng, lệnh thật lỡ route **3/3
  lần** — rằng **router LLM là mắt yếu**, và vá bằng lớp phủ quyết **tất định**
  `_looks_like_question`. Supervisor là **tăng** phần định tuyến do LLM quyết.
- Thí nghiệm model 2026-07-31 (chạy thật trên cổng `sop_select`, không sửa
  `catalog.py`) củng cố thêm: `gemini-3.1-flash-lite` **hoà đúng ca đang FAIL**
  với `gemma-4-26b` (acc 0.941, hijack 0) — tức đó là vấn đề *mô tả nhập
  nhằng*, không phải model yếu; còn `groq-gpt-oss-120b` **tệ hơn** (acc 0.882,
  **đẻ ra 1 ca hijack mới**: lệnh một bước "giao hàng cho đơn S00040 luôn nhé"
  bị SOP `giao-hang` cướp).

Nghĩa là: chưa có bằng chứng nào cho thấy giao định tuyến cho LLM là an toàn
hơn. SP-2b cố tình **không đặt cược vào đó**, và dựng sẵn phần hạ tầng
(worker → key state → node join) mà SP-2c sẽ cần dù nó có chọn hình dạng
supervisor nào.

### Trong phạm vi

- Node `mixed` đổi ruột thành **điểm fan-out**: xoá key join, nhả hai cạnh.
- Hai node thu thập: `gather_docs` (0 lượt LLM) ‖ `gather_erp` (ReAct chế độ
  thu thập).
- Node `fuse_answer`: một lượt tổng hợp + trích dẫn + verify grounding.
- Hai key state mới `doc_context` / `erp_facts`, ràng **JSON thuần**.
- Xoá `backend/src/agents/fusion.py` và `FUSION_PROMPT`.
- Sửa `eval_multi_source` để đo đúng đường mới (§5.2).

### Ngoài phạm vi — cố ý

| Hạng mục | Vì sao không làm ở đây |
|---|---|
| Supervisor nuốt `intent_router` | SP-2c. `_route_by_intent` và `intent_targets` **không đổi một ký tự** — xem §2.2 |
| Tách `erp_read` / `rag` đơn nguồn thành worker+join | Phương án B đã cân và loại: thêm **1 lượt LLM cho đường nóng nhất** để đổi lấy tính đối xứng. Xem §1.3 |
| Đụng đường ghi (29 tool ghi, 18 coordinator, confirm-gate) | Không có lý do chạm vào. Giống hệt quyết định SP-2a |
| Cho `gather_erp` đọc `working_context` | `fusion` hôm nay **không** đọc. Thêm vào là thêm *tính năng*, làm bẩn phép so `multi_source` trước/sau. Ứng viên riêng, đo riêng |
| Vòng truy xuất tài liệu **thứ hai** trong `fuse_answer` | Năng lực `fusion` mất đi (§1.4). Cổng `multi_source` sẽ nói có cần không. Dựng trước = dựng cơ chế chưa có bằng chứng là cần |
| Đổi vai model cho các node mới | QĐ M3 (ADR-009) cấm đổi model/prompt khi chưa qua eval gate. Xem §4.3 |
| Đổi tên vai `fusion` trong catalog | Xem §2.4 — **vai sống, node chết** |

---

## §1. Động cơ và bằng chứng

### 1.1 Động cơ

Một động cơ duy nhất, chủ dự án chốt 2026-08-01: **kiến trúc rõ và tái dùng
được cho SP-2c**. Cụ thể là dựng được một **nguyên thuỷ fan-out/join**: worker
đọc trả về *dữ kiện* vào key state riêng, một node tổng hợp gộp lại. `mixed`
chỉ là khách hàng đầu tiên.

Ghi rõ để đời sau không suy diễn lại: **latency và chất lượng trả lời KHÔNG
phải mục tiêu** của SP-2b. Chất lượng là **sàn phải giữ** (cổng `multi_source`,
§5), latency là **số quan sát** (§5.3) — không phải thứ biện minh cho việc
làm SP-2b. Đây vẫn là ưu tiên B của ADR-010 (kiến trúc rõ ràng), và **không
có lỗi vận hành nào đang thúc việc này**.

### 1.2 Hình dạng thật của câu hỏi `mixed` — ràng buộc lái thiết kế

Đọc cả 8 ca `MULTI_SOURCE_CASES`: tất cả cùng một hình dạng — cần **một giá
trị trong tài liệu** (30 ngày, 3 ngày, 0,5%, bảng chiết khấu) để **diễn giải**
một bản ghi ERP.

Hệ quả: **suy luận là tuần tự, chỉ thu thập mới song song được.** Câu
"read-only tasks parallelize freely" trong ADR-010 nói lướt qua chỗ này. Fan-
out kiểu "hai nhánh cùng trả lời rồi ghép hai câu trả lời" sẽ hỏng: mỗi nhánh
chỉ thấy nửa dữ kiện nên đều trả "không đủ thông tin".

Nên hình dạng đúng là **fan-out của việc THU THẬP, không phải của việc TRẢ
LỜI** — hai chân nộp dữ kiện thô, đúng một node suy luận.

### 1.3 Vì sao không hợp nhất luôn `erp_read` và `rag`

Có một bất đối xứng thật trong mã hiện tại:

- `rag` ([nodes.py:120-132](../../../backend/src/agents/nodes.py)) **đã** là
  hình dạng worker+tổng hợp: `retrieve()` thuần (0 lượt LLM) rồi
  `synthesize()`. Tách ra không tốn gì.
- `erp_read` ([nodes.py:89-107](../../../backend/src/agents/nodes.py)) là ReAct
  agent **tự trả lời luôn**. Tách thành "thu thập → tổng hợp" sẽ **thêm 1 lượt
  LLM cho đường nóng nhất của hệ**.

Phương án hợp nhất triệt để (mọi đường đọc đều worker+join, một node
`synthesize` duy nhất) đối xứng đẹp hơn và gần hình dạng supervisor hơn — cái
giá là latency/chi phí trên ca phổ biến nhất, cộng rủi ro cho **2 bộ eval đang
xanh** (`read`, `synthesis`). Loại, vì lợi ích duy nhất là tính đối xứng và
SP-2c không cần nó để chạy.

### 1.4 Một năng lực bị mất — nêu thẳng

`fusion` là vòng lặp ReAct nên **có thể truy xuất tài liệu lần hai** với query
đã tinh chỉnh sau khi thấy dữ liệu ERP. Fan-out truy xuất **đúng một lần**.

Với cả 8 ca `MULTI_SOURCE_CASES` thì tài liệu đều tìm được từ câu hỏi gốc, nên
đây được **ghi nhận là giới hạn chấp nhận, có cổng `multi_source` canh**. Nếu
eval tụt vì lý do này thì mới thêm vòng truy xuất bổ sung — không dựng trước.

Bù lại một phần: `fusion` phải mang cơ chế `aux_queries` (nối câu hỏi gốc vào
query của agent) vì agent hay truyền **từ khoá trần** kiểu `"SLA"` — vốn không
bao giờ kéo được `sla.docx` lên. Fan-out **luôn** truy xuất bằng nguyên câu hỏi
đầy đủ, tức chính là query mà docstring của `fusion` nói là "reliably does".
Cơ chế `aux_queries` biến mất khỏi đường này cùng `fusion.py` (hàm
`retrieve(aux_queries=...)` giữ nguyên, chỉ là đường `mixed` không dùng nữa).

---

## §2. Kiến trúc và luồng dữ liệu

### 2.1 Topology

```
intent_router --"mixed"--> mixed ──┬──> gather_docs ──┐
                          (điểm     │                  ├──> fuse_answer ──> END
                           fan-out) └──> gather_erp  ──┘
```

Hai chân chạy **cùng một superstep** LangGraph (hai cạnh thẳng ra từ một node);
`fuse_answer` có hai cạnh vào nên chỉ chạy sau khi **cả hai** xong. Đây là ngữ
nghĩa superstep sẵn có của LangGraph, không cần `Send` hay cơ chế nào thêm.

### 2.2 `mixed` giữ tên, đổi ruột — và vì sao điều đó quan trọng

Node `mixed` **giữ nguyên tên** và **giữ nguyên chỗ trong `intent_targets`**.
Việc duy nhất nó làm:

1. đặt `doc_context = None`, `erp_facts = None`;
2. nhả ra hai cạnh thẳng.

Hệ quả cố ý: **`_route_by_intent` không đổi một ký tự**, `intent_targets` vẫn
map `"mixed" → "mixed"`.

Đây không phải sự lười. Bộ `SOP_SELECT_CASES` của SP-2a **đo trực tiếp giá trị
trả về của `_route_by_intent`** (cases.py ghi rõ: "Đích là giá trị
`_route_by_intent()` TRẢ VỀ"). Phương án "cho `_route_by_intent` trả về list
`["gather_docs","gather_erp"]` khi intent là mixed" trông gọn hơn 1 dòng nhưng
**phá hợp đồng đầu ra mà bộ eval đang đo**, và kéo theo cả lớp phủ quyết
`_looks_like_question` phải chứng minh lại. Đổi 1 dòng lấy 1 bộ eval là lỗ.

Giá phải trả cho lựa chọn này: một node "chỉ để rẽ nhánh". Nhưng nó **không
rỗng** — xem 2.3.

### 2.3 Vì sao `mixed` xoá key lúc vào (không phải trang trí)

LangGraph giữ giá trị channel **qua lượt**: node bỏ qua một key = giữ nguyên
giá trị cũ. Nếu ở lượt sau `gather_docs` ngã và không ghi gì, `fuse_answer` sẽ
lặng lẽ **trích dẫn chunk của lượt trước** — sai, và sai kiểu không ai thấy.

Xoá **tất định tại đúng một chỗ** khiến tính đúng **không phụ thuộc** vào việc
mọi đường lỗi của mọi chân đều nhớ ghi key. (Các chân vẫn ghi giá trị rỗng trên
mọi đường về — §3.3 — nhưng đó là lớp thứ hai, không phải lớp chịu lực.)

### 2.4 Vai `fusion` sống, node `fusion` chết

Chữ "fusion" trong repo mang **hai nghĩa khác nhau**, và spec này chỉ giết một:

| Nghĩa | Ở đâu | SP-2b làm gì |
|---|---|---|
| **Node** trong graph | `backend/src/agents/fusion.py`, `graph.py` | **XOÁ** |
| **Vai model** trong gateway | `CHAINS["fusion"]` (catalog.py), `llms["fusion"]` (models.py), `eval_gate.py:41` | **GIỮ NGUYÊN** |

`eval_gate.py:38` đã có sẵn comment ghi việc này ("role thật vẫn tên 'fusion'
trong catalog.py"), và `cases.py:395` đã đặt tên bộ eval là `multi_source`
(trung tính) chính vì lường trước node sẽ biến mất. Đổi tên vai sẽ lan sang
`catalog.py`, `router.py`, `models.py`, `main.py`, `eval_gate.py` — ngoài phạm
vi, và vi phạm QĐ M3 (§4.3).

### 2.5 Bốn node

**`mixed`** — điểm fan-out. Không LLM, không I/O. Trả `{"doc_context": None,
"erp_facts": None}`.

**`gather_docs`** — `retrieve(<câu hỏi user cuối>)` trong `asyncio.to_thread`
(retrieve là psycopg đồng bộ), áp `passes_floor`, ghi `doc_context`.
**Không gọi LLM lần nào.** Dưới sàn hoặc rỗng → ghi `[]`.

**`gather_erp`** — ReAct agent trên `build_erp_query_tools()` với
`GATHER_ERP_PROMPT` (§4.1). Ghi `erp_facts` là văn bản dữ kiện. Đây là khác
biệt thật so với `erp_read`: hỏi *"Đơn S00042 còn được hoàn hàng theo chính
sách không?"* thì `erp_read` với `SYSTEM_PROMPT` hiện tại rất dễ trả lời "tôi
không biết chính sách" thay vì đi lấy ngày giao của S00042.

**`fuse_answer`** — dựng lại `Chunk` từ `doc_context`, gọi **một lượt** LLM với
`FUSE_PROMPT` trên input do `render_fuse_input()` dựng (§4.2), rồi
`cite_and_verify` + `verify_erp_grounding` — **dùng lại nguyên hàm có sẵn**
trong `synthesis.py` / `erp_grounding.py`. Hỏng → `SAFE_MSG`. Xoá cả hai key
trước khi trả.

### 2.6 File

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Tạo | `backend/src/agents/fanout.py` | 4 node factory + `render_fuse_input()` |
| Xoá | `backend/src/agents/fusion.py` | — |
| Sửa | `backend/src/agents/state.py` | thêm 2 key + comment vòng đời |
| Sửa | `backend/src/agents/prompts.py` | bỏ `FUSION_PROMPT`; thêm `GATHER_ERP_PROMPT`, `FUSE_PROMPT` |
| Sửa | `backend/src/agents/graph.py` | đấu lại `mixed` thành 4 node |
| Sửa | `backend/evals/run_eval.py` | `eval_multi_source` dùng `FUSE_PROMPT` + `render_fuse_input()` (§5.2) |
| Xoá | `backend/tests/agents/test_fusion.py` | thay bằng ↓ |
| Tạo | `backend/tests/agents/test_fanout.py` | §6 |

Tên module là `fanout.py`, không phải `mixed.py`: tên phải nói lên **nguyên
thuỷ**, vì SP-2c dùng lại nguyên thuỷ chứ không dùng lại intent `mixed`.

---

## §3. Hợp đồng state và bất biến

### 3.1 Hai key mới

```python
doc_context: list[dict] | None   # [dataclasses.asdict(chunk), ...]
erp_facts: str | None            # dữ kiện ERP dạng văn bản, hoặc ""
```

### 3.2 Bất biến JSON thuần

**State chỉ chứa JSON thuần.** `gather_docs` ghi `asdict(chunk)`;
`fuse_answer` dựng lại `Chunk(**d)` để đưa vào `cite_and_verify`.

`Chunk` là `@dataclass(frozen=True)` (`backend/src/rag/types.py`). Nhét thẳng
dataclass vào state là loại lỗi **chỉ hỏng khi checkpointer Postgres thật
chạy** — đúng loại mà unit test mock sẽ bỏ lọt. Đây là bài học SP-1C2 nguyên
văn: cơ chế dựa vào tầng hạ tầng thật thì phải có test chạy tầng hạ tầng thật,
hoặc đừng dựa vào nó. Ràng "JSON thuần" chọn vế thứ hai.

Lợi ích kèm theo: checkpoint đọc được bằng mắt trong Postgres và trong trace
Langfuse; và đây chính là hợp đồng SP-2c cần khi có thêm worker.

### 3.3 Vòng đời — dọn ở hai chỗ, hai lý do khác nhau

| Chỗ | Việc | Lý do |
|---|---|---|
| `mixed` (lúc vào) | đặt cả hai về `None` | **tính đúng**: `fuse_answer` không bao giờ thấy dữ liệu lượt trước, kể cả khi một chân ngã |
| `fuse_answer` (lúc ra, **mọi** đường về kể cả `SAFE_MSG`) | đặt cả hai về `None` | **vệ sinh**: lượt `erp_read` sau đó không vác theo cả đống chunk trong checkpoint và trace |

Không phải hai lớp cho cùng một việc. Ghi rõ vì bảng vòng đời key trong
`state.py` (TRANSIENT vs PERSISTENT) là tài liệu đời sau sẽ đọc.

Ngoài một lượt `mixed`, cả hai key **luôn** là `None`.

### 3.4 An toàn ghi song song

Hai chân chạy cùng superstep nhưng:

- ghi **hai key khác nhau** → không có xung đột reducer;
- **không chân nào ghi `messages`** → user không thể nhận hai câu trả lời.

Đây là bất biến **phải có test chốt** (§6), không phải điều hiển nhiên từ mã.

### 3.5 Chân ngã thì sao

LangGraph để exception trong một nhánh **làm hỏng cả superstep**. Nên mỗi chân
**tự bắt lỗi và ghi giá trị rỗng** (`[]` / `""`) thay vì ném ra.

`fuse_answer` **không rẽ nhánh xử lý** cho các tổ hợp thiếu: luật *"thiếu căn
cứ thì nói rõ, không suy đoán"* vốn đã có trong `FUSION_PROMPT` và được
`FUSE_PROMPT` kế thừa nguyên. Hai chân cùng rỗng → `SAFE_MSG` (kiểm tra tất
định trong mã, không giao cho model).

### 3.6 Lọc tool: bỏ deny-list, dùng allow-list + test

`fusion.py` lọc tool ghi bằng deny-list `WRITE_TOOL_NAMES` gồm **9 tên**, trong
khi `WRITE_PLANNER_PROMPT` đang khai **29 tool ghi**. Deny-list phủ 9/29 đó
thực tế là no-op — `graph.py` vốn chỉ đưa `build_erp_query_tools()` (allow-
list, dựng một chỗ, toàn read) vào node.

Vấn đề không phải nó vô hại, mà là nó **trông như một lớp phòng thủ**. Khi
`fusion.py` chết, deny-list **không được bê sang**. Thay bằng test chốt: tập
tên tool của `gather_erp` ⊆ tập tên `build_erp_query_tools()`.

Allow-list + test nói đúng sự thật; deny-list thiếu 20 tên thì không.

---

## §4. Prompt

### 4.1 `GATHER_ERP_PROMPT`

Spec chốt **yêu cầu nội dung**; plan chốt **câu chữ nguyên văn** (lệ đã áp từ
SP-2a cho `description` của SKILL.md). Năm yêu cầu, không thiếu cái nào:

- Nêu **dữ kiện ERP liên quan đến câu hỏi**, dạng gạch đầu dòng ngắn.
- **KHÔNG kết luận**, không phán quyết câu hỏi của user.
- **KHÔNG viện dẫn tài liệu/chính sách** — chân kia lo phần đó.
- Không tìm được gì → nói rõ, không bịa.
- Kết thúc bằng `/no_think` (quy ước sẵn có, xem 4.4).

### 4.2 `FUSE_PROMPT` + `render_fuse_input()`

`FUSE_PROMPT` kế thừa từ `FUSION_PROMPT`, bỏ phần mô tả tool (không còn tool):

- chỉ dùng dữ kiện được cung cấp, không bịa điều khoản hay số liệu;
- thiếu căn cứ → nói rõ, không suy đoán;
- không thao tác ghi;
- không tự viết mục "Nguồn";
- không nêu số Điều/Mục/Khoản hay số thứ tự đoạn trong lời văn;
- **luôn kết thúc bằng dòng `NGUỒN_DÙNG: <các số>`** — hợp đồng đuôi này
  **không phải trang trí**: `extract_used_citations()` parse đúng dòng đó.

`render_fuse_input(chunks, erp_facts, question) -> str` là **nguồn sự thật
duy nhất** cho hình dạng input, dùng bởi **cả** `fuse_answer` **và**
`eval_multi_source` (§5.2).

Một chỗ gọn lại tự rơi ra: `fusion` phải tự quản `start=` tăng dần vì agent gọi
`search_documents` nhiều lần; fan-out truy xuất **đúng một lần** nên
`_format_context(chunks)` chạy `start=1` và sổ sách đó biến mất.

### 4.3 Model không đổi vai

`gather_erp` và `fuse_answer` **đều dùng `llms["fusion"]`** — đúng model mà
node `mixed` đang dùng.

Không phải thận trọng suông: **QĐ M3 (ADR-009) cấm đổi model/prompt khi chưa
qua eval gate**, và nếu đổi topology *và* đổi vai model cùng một lượt thì
`multi_source` tụt hay lên đều **không quy được trách nhiệm**. Phân lại vai
(ví dụ cho `gather_erp` dùng `llms["read"]`) là quyết định riêng, đo riêng.

### 4.4 Quy ước `/no_think`

Cả hai prompt mới kết thúc bằng `/no_think`, theo đúng lệ đang áp trong
`prompts.py`. Chỗ nào ghép context vào system prompt thì ghép **TRƯỚC** prompt
gốc để `/no_think` giữ vị trí cuối (bất biến A, đã ghi tại `nodes.py`).

---

## §5. Cổng đo

### 5.1 Đo hai phần, đừng lẫn hai phần

Cổng có sẵn (`jobs run eval-gate --set multi_source`) so với **file baseline
qwen3:8b**, công thức nguyên văn trong `eval_gate.py`:

```
citation_validity == 1.0
AND fabricated_number == 0
AND both_source_coverage >= base["both_source_coverage"]
```

Đó là **điều kiện merge**, đã có sẵn, SP-2b chỉ cần nó vẫn PASS.

Nhưng qwen3:8b là model yếu hơn hẳn model đang chạy, nên PASS **không** chứng
minh "không hồi quy so với hành vi hôm nay". Vì vậy SP-2b cần **thêm** một cặp
đo trên **cùng model đang chạy**:

- **TRƯỚC**: chạy `multi_source` trên `main` sạch, trước khi sửa dòng đầu tiên;
- **SAU**: chạy lại trên nhánh, cùng model, cùng `--pace`.

Hai phần này khác vai trò và **không thay thế nhau**: phần một là cổng, phần
hai là phép so hồi quy. Cả hai vào report.

### 5.2 `eval_multi_source` phải đo đường mới — bẫy đã cắn SP-2a

`eval_multi_source` ([run_eval.py:474](../../../backend/evals/run_eval.py))
**không gọi node thật**: nó *mirror* `FUSION_PROMPT` bằng một lượt LLM tự dựng
trên fixture đóng băng.

Đây **đúng cái bẫy đã cắn SP-2a**: Task 8 đổi hợp đồng đầu ra của router, nhưng
`eval_intent()` ở module khác vẫn parse hợp đồng cũ — acc rơi 0.870 → 0.148,
mọi ca parse thành `"unknown"`. Lỗi không nằm ở model.

Yêu cầu hạng nhất của SP-2b, và cách chặn:

1. `eval_multi_source` chuyển sang `FUSE_PROMPT`;
2. **input do chính `render_fuse_input()` dựng** — không dựng lại chuỗi
   `"TÀI LIỆU:... DỮ LIỆU ERP:... CÂU HỎI:..."` bằng tay ở phía eval.

Điểm 2 là phần chịu lực: dùng chung hàm thì mirror **không thể trôi** khỏi node
thật. Đây đúng khuôn `_parse_router_output` / `render_intent_router_prompt` mà
SP-2a đã dùng để đóng vĩnh viễn lớp lỗi này.

Tin tốt: dưới fan-out, mirror **trung thực hơn hiện tại** — `fuse_answer` đúng
là một lượt LLM trên (tài liệu + dữ kiện ERP + câu hỏi), còn `fusion` hôm nay
là vòng lặp ReAct mà mirror đang làm phẳng.

`erp_block` trong fixture đóng vai `erp_facts`. Hình dạng khớp: cả hai đều là
văn bản dữ kiện ERP thô, không phải câu trả lời.

### 5.3 Bảng cổng

| Bộ | Vai trò | Điều kiện |
|---|---|---|
| `multi_source` | **cổng chính** | gate PASS (công thức §5.1); **và** `both_source_coverage` SAU ≥ TRƯỚC trên cùng model |
| `intent` | canh hồi quy | gate PASS (`acc >= base["acc"]`) — `_route_by_intent` không đụng, đây là bảo hiểm rẻ |
| `sop_select` | canh hồi quy | **không** đòi gate PASS — xem dưới. Đòi `hijack == 0` và `acc` ≥ 16/17 |
| latency p50/p95 | **quan sát, không gác** | harness ghi sẵn; vào report, không phải điều kiện merge |

Chỉ số của `multi_source` tên là `both_source_coverage` và `citation_validity`,
**không phải `acc`** — ghi rõ vì dễ viết nhầm khi soạn plan.

`sop_select` là **gate tuyệt đối** (`acc == 1.0 and hijack == 0`) và **đang
FAIL biết trước** 16/17 — một ca đã được chủ dự án chấp nhận ở SP-2a (rủi ro
tồn dư, chiều lỗi an toàn). Nó cũng cố ý **không nằm trong `--set all`**
(`eval_gate.py`). Nên điều kiện của SP-2b là **các con số không xấu đi**, không
phải "gate xanh" — đòi gate xanh ở đây là đòi SP-2b sửa việc của người khác.

---

## §6. Test

Đơn vị:

- `mixed` xoá cả hai key lúc vào.
- `fuse_answer` xoá cả hai key lúc ra, trên **mọi** đường về kể cả `SAFE_MSG`.
- `gather_docs` ghi `[]` khi `retrieve` ném; ghi `[]` khi dưới `passes_floor`.
- `gather_erp` ghi `""` khi agent ném.
- **Không chân nào để exception thoát ra** (thoát = chết cả superstep).
- Tập tên tool của `gather_erp` ⊆ tập tên `build_erp_query_tools()` (§3.6).
- `asdict(Chunk) → Chunk(**d)` khứ hồi nguyên vẹn.
- Hai chân cùng rỗng → `SAFE_MSG`.
- `fuse_answer` chỉ ghi `messages`; `gather_*` **không** ghi `messages` (§3.4).

Tích hợp — **trên `build_graph()` thật**, không dựng `StateGraph` bằng tay:

- một lượt `mixed` đầu-cuối → đúng **một** `AIMessage`;
- cả hai key về `None` ở state cuối;
- cả hai chân thật sự đã chạy (không phải một chân im lặng bị bỏ qua).

Bài học SP-2a: review cuối phát hiện toàn bộ test skill node dựng `StateGraph`
bằng tay nên **không chứng minh được wiring thật**; test đầu tiên gọi
`build_graph()` thật phải thêm vào ở đợt vá cuối. SP-2b làm ngay từ đầu.

Live (`@pytest.mark.live`): một câu hỏi `mixed` thật qua `/v1`, ra đúng một câu
trả lời **có khối trích dẫn**.

Toàn bộ phải xanh ở **cả ba chế độ** pytest của repo.

---

## §7. Hợp đồng với giai đoạn sau

**Sửa tên (2026-08-01):** cái tên "SP-2c" cuối cùng đi vào một spec nhỏ hơn
mục này dự tính — bộ đo `gather_erp` (`2026-08-01-sp2c-gather-eval-design.md`),
không phải supervisor. Nội dung §7 dưới đây vẫn đúng, chỉ đổi cách gọi: đây
là hợp đồng cho **giai đoạn supervisor**, hiện chưa đặt số, chưa bắt đầu.

SP-2b để lại cho giai đoạn sau đúng ba thứ, và cố ý **không** để lại gì hơn:

1. **Nguyên thuỷ join**: worker ghi *dữ kiện* vào key state JSON thuần; một
   node tổng hợp gộp. Thêm worker = thêm key + thêm cạnh, không đụng node cũ.
2. **Khuôn "chống trôi"** giữa node thật và eval: một hàm dựng input dùng
   chung (§5.2). Worker mới thừa hưởng khuôn này.
3. **Lớp định tuyến nguyên vẹn**: `_route_by_intent`, `intent_targets`, phủ
   quyết `_looks_like_question`, `SOP_SELECT_CASES` — SP-2b không chạm.

**Câu hỏi mở đã có câu trả lời (2026-08-01, research độc lập ngoài dự án):**
một supervisor LLM có được phép **thay** lớp phủ quyết tất định không, hay
chỉ được **đứng trước** nó — **KHÔNG được thay.** Bằng chứng nội bộ (sự cố
3/3 lần 2026-07-16; thí nghiệm model 2026-07-31 cho thấy model to hơn *không*
cứu được, thậm chí đẻ hijack mới) khớp với bằng chứng ngoài dự án: đây là
hiện tượng *inverse/U-shaped scaling* đã công bố (McKenzie et al., "Inverse
Scaling: When Bigger Isn't Better," TMLR 2023) — mô hình to hơn dựa vào
prior lúc pretrain nhiều hơn, bám prompt ít hơn, đúng cơ chế khiến
`groq-gpt-oss-120b` sinh hijack mới thay vì sửa được ca cũ. Pattern chuẩn
ngành cho đúng tình huống này là **hybrid: lớp đề xuất (embeddings/LLM) +
veto tất định**, không đảo ngược thứ tự — khớp thiết kế `_route_by_intent`
đang có. **Không cần đo thêm để đóng câu hỏi này** — giữ nguyên veto, một
supervisor (nếu làm) chỉ được đứng TRƯỚC nó, y hệt vai trò router hiện tại.

**Khoảng trống thật còn lại không phải "cần supervisor"** — là năng lực
truy xuất lại khi thiếu căn cứ mà `fusion` cũ có (ReAct loop) và fan-out
không có (§1.4). Research chỉ đúng tên: **Corrective RAG / Adaptive-RAG**
— một node chấm điểm tin cậy trên cạnh có điều kiện, bắn ĐÚNG MỘT lượt truy
xuất bổ sung khi `fuse_answer` báo thiếu căn cứ, giữ nguyên fan-out song
song cho lượt đầu. Nhỏ hơn, có tên, có tiền lệ (LangGraph tự có cookbook
cho đúng pattern này) — không phải orchestrator tổng quát. Đây là ứng viên
hợp lý hơn cho giai đoạn kế tiếp, thay vì supervisor.

---

## §8. "SP-2b xong" nghĩa là

1. `backend/src/agents/fusion.py` **không còn trong repo**; `FUSION_PROMPT`
   không còn trong `prompts.py`.
2. `mixed` chạy hai chân song song; `fuse_answer` ra đúng một `AIMessage`.
3. Cổng `multi_source` PASS, **và** `both_source_coverage` SAU ≥ TRƯỚC trên
   cùng model (§5.1); `fabricated_number` = 0, `citation_validity` = 1.0.
4. Cổng `intent` PASS. `sop_select`: `hijack` = 0 và `acc` ≥ 16/17 (không đòi
   gate xanh — §5.3).
5. Toàn bộ test xanh ở cả ba chế độ, gồm test tích hợp gọi `build_graph()`
   thật.
6. Một câu hỏi `mixed` thật chạy qua `/v1` ra một câu trả lời có trích dẫn.
7. Vai model `fusion` trong `catalog.py` **không đổi** (§2.4).

**Chưa làm được sau SP-2b:** chưa có supervisor, `intent_router` vẫn còn,
`erp_read`/`rag` đơn nguồn vẫn là node tự trả lời. Đó là việc của SP-2c.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

Theo standing rule ADR-010 (quyết định nào đời sau không được bàn lại thì phải
có comment trong **file được version-control**, tại đúng điểm mã nó ảnh hưởng):

| Quyết định | File |
|---|---|
| `mixed` xoá key join lúc vào là lớp chịu lực chống dữ liệu ôi qua lượt (channel semantics của LangGraph giữ giá trị khi node bỏ qua key) | `fanout.py`, tại node `mixed` |
| State chỉ chứa JSON thuần; `Chunk` phải `asdict`/dựng lại — vì dataclass trong payload chỉ hỏng khi checkpointer thật chạy | `fanout.py`, tại `gather_docs` và `fuse_answer` |
| Mỗi chân tự bắt lỗi, không để exception thoát — exception một nhánh giết cả superstep | `fanout.py`, tại cả hai node `gather_*` |
| Không bê deny-list `WRITE_TOOL_NAMES` (phủ 9/29); allow-list `build_erp_query_tools()` + test là lớp thật | `fanout.py`, tại `gather_erp` |
| `_route_by_intent` cố ý **không** trả về list, để giữ nguyên hợp đồng mà `SOP_SELECT_CASES` đang đo | `graph.py`, tại chỗ đấu `mixed` |
| Vai model `fusion` sống dù node chết | `catalog.py`, cạnh `CHAINS["fusion"]` |
| `eval_multi_source` phải dựng input bằng `render_fuse_input()` — không dựng tay, vì đó là cách `eval_intent` trôi khỏi router ở SP-2a | `run_eval.py`, tại `eval_multi_source` |

## Phụ lục B — Rủi ro đã biết, chưa xử lý ở SP-2b

| Rủi ro | Vì sao chấp nhận |
|---|---|
| Mất vòng truy xuất tài liệu thứ hai (§1.4) | Cả 8 ca `MULTI_SOURCE_CASES` tìm được tài liệu từ câu hỏi gốc; cổng `multi_source` canh. Dựng trước = cơ chế chưa có bằng chứng cần |
| Tồn tại **hai** cách đọc ERP (`erp_read` trả lời / `gather_erp` thu thập) | Khác **mục đích**, không phải trùng lặp; chung bộ tool và chung `verify_erp_grounding`. Hợp nhất = phương án B, đã cân và loại (§1.3) |
| `gather_erp` không đọc `working_context` nên câu hỏi mixed dạng "đơn đó còn hoàn được không?" vẫn hỏng như hôm nay | Là **lỗi có sẵn của `fusion`**, không phải hồi quy do SP-2b. Sửa trong cùng lượt sẽ làm bẩn phép so `multi_source` trước/sau |
| Một node `mixed` "chỉ để rẽ nhánh" | Giá phải trả để `_route_by_intent` không đổi (§2.2). Node không rỗng — nó là chỗ dọn key (§2.3) |
| Ca `sop_select` FAIL còn tồn từ SP-2a | Đã được chấp nhận có chủ đích ở SP-2a (chiều lỗi an toàn, `hijack=0`). SP-2b chỉ cam kết không làm tệ thêm |
