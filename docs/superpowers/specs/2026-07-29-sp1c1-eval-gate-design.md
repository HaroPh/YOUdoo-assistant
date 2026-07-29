# SP-1C1: Vá blocker hạ tầng + eval harness + chạy cổng M3 — thiết kế

**Mục tiêu:** Trả lời câu hỏi mà SP-1 cố ý chưa trả lời — *thay qwen3:8b bằng
model cloud có làm chất lượng thụt lùi không?* — bằng số đo thật, trước khi mở
bất kỳ cửa HTTP nào.

**Bối cảnh:** SP-1A (LLM gateway) và SP-1B (port tầng nghiệp vụ) đã merge vào
`main`. SP-1B tuyên bố có chủ đích: *"kế hoạch B cố ý không tuyên bố 'không hồi
quy', chỉ tuyên bố 'port đúng'"*. Spec này là lượt đo để có quyền tuyên bố điều
còn thiếu.

---

## §0. Vị trí trong lộ trình và phạm vi

Kế hoạch C tách đôi ở đúng cổng **ADR-009 QĐ M3** (*eval gate phải chạy TRƯỚC
khi mở `/v1`*):

| | Nội dung | Điều kiện đầu vào (ghi ở plan SP-1B) |
|---|---|---|
| **C1** *(spec này)* | Vá 3 blocker hạ tầng, thích nghi eval harness, sửa scanner `multi_source`, **chạy gate thật** → bảng trước/sau | #1 pool timeout, #2 Postgres đồng bộ, #3 tiktoken |
| **C2** | `main.py` FastAPI `/v1` + Langfuse tracing | #5 `assert_embedding_marker()` chưa có người gọi |
| SP-2a | Nền tảng SOP skill dạng thư mục | cần harness của C1 cho bộ eval chọn-SOP |
| SP-2b | Topology: supervisor, bỏ `fusion`, fan-out | cần số `multi_source` của C1 |

**Vì sao tách đôi thay vì một spec:** cổng M3 phải là **ranh giới thật giữa hai
spec**, không phải một checkbox giữa một kế hoạch dài. Gate đỏ nghĩa là dừng và
quay lại sửa model/prompt — điều đó dễ bị vượt qua khi đang đà giữa kế hoạch,
và khó bị vượt qua khi nó là điều kiện khởi động của spec kế tiếp.

### Trong phạm vi

- Vá 3 blocker hạ tầng đã ghi sẵn ở plan SP-1B (§1).
- Port + **thích nghi** `backend/evals/` và `backend/jobs/` từ `D:\Project` (§2).
- Sửa bug scanner `fabricated_number` + chấm lại baseline `multi_source` (§3).
- Chạy 7 bộ eval với model ghim, ra bảng trước/sau (§4).

### Ngoài phạm vi — cố ý

| Hạng mục | Vì sao không ở đây |
|---|---|
| `main.py`, mọi thứ HTTP | C2. Cổng M3 nằm giữa |
| Langfuse tracing | C2. Và nó **không phải port** — `grep -rn "langfuse"` trên toàn `D:\Project` trả về rỗng, đây là dựng mới hoàn toàn |
| `assert_embedding_marker()` có người gọi | Cần điểm khởi động thật (`main.py`) → C2 |
| Bộ eval chọn-SOP | SP-2a. C1 chỉ dựng cái harness mà bộ đó sẽ chạy trên |
| Đụng `agents/`, `erp_query/`, `rag/`, MCP server | Không có lý do. Nếu gate đỏ và nguyên nhân nằm ở đó thì đó là phát hiện của C1, xử lý ở lượt sau |
| Job `e2e_*` (`jobs/e2e_skill_*.py`, `e2e_smoke.py`) | Chúng kiểm 3 skill SOP tier-2 — chưa tồn tại ở Youdoo, thuộc SP-2a |

---

## §1. Ba blocker hạ tầng

Cả ba đã xác nhận bằng cách đọc mã thật, không phải suy đoán.

### 1.1 Pool Postgres không có timeout

`backend/src/llm/store.py:88`:

```python
self._pool = ConnectionPool(dsn or os.environ["DATABASE_URL"], ...)
```

Thiếu tham số timeout → DB không tới được thì mỗi lượt gọi chặn ~90 giây trước
khi fail-open.

**Vá:** timeout **ngắn** (~2s) cho cả `timeout` (chờ connection rảnh trong pool)
lẫn `connect_timeout` truyền xuống psycopg qua `kwargs`.

**Vì sao ngắn:** sổ ngân sách là **tư vấn và đã fail-open sẵn**
(`budget.py:70-77`). Chặn lượt của người dùng quá 2 giây chỉ để tra một cuốn sổ
tư vấn là đánh đổi sai — thà mất một dòng kế toán. Đây là cùng một lập luận tỉ
lệ mà `budget.py` đã dùng để chọn fail-open thay vì fail-closed.

### 1.2 `Router.ainvoke()` gọi Postgres đồng bộ

`resolve()` đọc store 2 lần (`budget.can_afford` → `usage_since` ×2),
`_finish()` ghi 1 lần (`budget.record` → `store.record`). Cả ba đồng bộ, đều
nằm trong `async def ainvoke` (`router.py:266-282`). Dưới uvicorn/LangGraph
async, chúng chặn event loop.

**Vá:** `asyncio.to_thread` tại **đúng hai điểm** trong `ainvoke`:

```python
decision = await asyncio.to_thread(self.resolve, role, base, pin=pin)
...
return await asyncio.to_thread(self._finish, decision, response, attempts)
```

**`BudgetLedger`, `UsageStore`, `InMemoryUsageStore`, `PostgresUsageStore`
không đổi một dòng.** Giữ đúng tuyên bố thiết kế ở `budget.py:3` — *"Chính sách
thuần — KHÔNG biết Postgres tồn tại"* — nhờ đó toàn bộ test SP-1A còn nguyên
giá trị. Đường `invoke()` đồng bộ cũng không đổi.

Đã cân nhắc và loại: (a) làm sổ async thật — kéo theo `UsageStore` Protocol và
mọi hiện thực lẫn test SP-1A; (b) cache trong bộ nhớ + flush nền — thêm trạng
thái cũ vào đúng chỗ đang quyết định tiêu hạn mức. Cả hai đắt hơn nhiều so với
vấn đề thật đang giải (chặn event loop).

### 1.3 `tiktoken` cần mạng lần dùng đầu

`backend/src/llm/tokens.py:15,26` nạp lười đúng cách, nhưng lần dùng **đầu tiên
tải bảng mã qua mạng**. Chỗ này nằm trên đường test **mặc định**, vốn phải không
chạm mạng. Máy dev đã có cache nên không lộ; **CI lạnh sẽ vỡ**.

**Vá:** `estimate_base_tokens` bắt lỗi khi `tiktoken` không nạp được và tụt
xuống ước lượng thô (số ký tự ÷ 4), kèm cảnh báo một lần.

**Vì sao chấp nhận được:** con số này chỉ dùng để kiểm TPM **trước** khi gọi.
Con số **có thẩm quyền** để ghi sổ là `total_tokens` lấy từ response
(`budget.py:93`). Ước lượng thô làm phép kiểm TPM bi quan/lạc quan hơn một
chút, không làm sai kế toán.

Kèm một test chốt: đường mặc định chạy được **không chạm mạng**.

---

## §2. Thích nghi eval harness

Đích: `backend/evals/` và `backend/jobs/` (hiện **chưa tồn tại** ở Youdoo).

**Đây không phải port nguyên văn.** Bốn nhóm phải đổi:

| Chỗ | Cũ | Mới |
|---|---|---|
| `run_eval._llm(model)` (`run_eval.py:41-45`) | `ChatOpenAI(base_url=LITELLM_URL, api_key=LITELLM_MASTER_KEY)` — **LiteLLM đã gỡ bỏ hoàn toàn ở SP-1** | `RoutedChatModel(router, role, pin=alias)` |
| `eval_gate.py:87` | `model_for(role)` — **xoá ở SP-1B Task 8** | `chain_for(role)[0].alias` (từ `llm/catalog.py`) |
| `eval_gate.py:48` (`_auto_pace`) | `is_qwen(model)` → 0s local / 5s cloud — **`is_qwen` xoá ở Task 8** | `(60 / spec.rpm) * 1.2` giây, suy từ catalog |
| Toàn bộ `evals/`, `jobs/` | `from backend.src.X` + `sys.path.insert` | `from src.X` — y hệt cú sửa đã làm 6 lần ở SP-1B |

Áp **quy tắc port test của SP-1B** không đổi: đỏ vì hạ tầng → sửa nối dây; đỏ vì
**hành vi** → dừng, báo cáo, không sửa cho xanh.

### 2.1 Vì sao đo qua `Router` chứ không qua client thô

SP-1A đã thiết kế sẵn cho đúng việc này và đã tính đúng. `router.py:139-144`:

> *"pin: bỏ qua toàn bộ chuỗi, ép đúng một model. Chế độ này TỒN TẠI VÌ EVAL:
> thiết kế fallback khiến cùng một câu hỏi có thể được trả lời bởi 3 model khác
> nhau tuỳ trạng thái ngân sách lúc đó, nên eval phải đo MỘT MODEL chứ không
> phải một trạng thái ngân sách. Ghim là ghim — ngân sách cạn cũng không tụt,
> vì tụt lặng lẽ sẽ làm hỏng phép đo mà không báo gì."*

Hai tính chất quan trọng, cả hai đã đúng sẵn, không phải sửa gì:

1. **`resolve()` khi có `pin` trả về sớm** (`router.py:146-149`), **không đọc sổ
   ngân sách** → trạng thái ngân sách không ảnh hưởng phép đo.
2. **`_finish()` vẫn ghi** lượng tiêu thụ thật → eval tiêu hạn mức thật thì sổ
   phải biết. Đúng cả hai chiều.

Đo qua `Router` cũng là đo **đúng đường sản xuất** (có `_gop_content()`,
`strip_thought()` — hai thứ Task 1/2 thêm vào và đã chứng minh cần thiết trước
sự trôi API của Google), thay vì đo model trần.

---

## §3. Sửa scanner `multi_source` và chấm lại baseline

### 3.1 Bug

`run_eval.py:372` dựng tập số hợp lệ **lệch cơ sở** so với thứ model thật sự
nhìn thấy:

```python
# dòng 359 — model nhìn thấy cái này:
HumanMessage(content=f"TÀI LIỆU:\n{_format_context(chunks)}\n\n...")
# dòng 372 — nhưng allowed lại dựng từ cái khác:
allowed = _digits(erp_block) | _digits(" ".join(c.text for c in chunks))
```

`_format_context` (`agents/synthesis.py:101-107`) trả về
`f"[{i}] ({label}) {c.text}"` — nghĩa là nó chứa **nguyên `c.text`**, cộng thêm
chỉ số `[i]` và nhãn mục. Số nằm trong nhãn mục bị quy oan là "bịa".

Hệ quả đã ghi trong ADR-010 và `cases.py`: baseline qwen3:8b có
`fabricated_number = 4` và **tự nó không đạt gate của chính nó**.

**Sửa:**

```python
allowed = _digits(erp_block) | _digits(_format_context(chunks))
```

Đúng bản sửa mà ghi chép gốc đã đặc tả sẵn. Lý do hoãn khi đó — *"sửa basis
giữa lúc chụp baseline sẽ làm mất ý nghĩa 'trước' của phép đo"* — **đã hết hiệu
lực**: baseline chụp xong rồi.

### 3.2 Chấm lại baseline — và cái bẫy phải tránh

**Bẫy:** `run_eval.py:377` lưu `response: body[:300]` — **cắt cụt**. Quét lại
văn bản đã cắt sẽ **đếm thiếu** số bịa nằm sau ký tự 300, và sai lặng lẽ.

**Lối đúng:** bản ghi cũng lưu `fabricated: [...]` — danh sách tính trên văn bản
**đầy đủ** dưới tập cũ. Vì `_format_context` chứa nguyên `c.text`, ta có
`allowed_new ⊇ allowed_old` (chặt chẽ), nên đại số tập hợp cho công thức chính
xác:

```
fabricated_new = fabricated_old \ allowed_new
               = [d for d in bản_ghi["fabricated"] if d not in allowed_new]
```

**Không cần chạm tới văn bản response.** Đúng cho cả 8 ca:

- 6 ca có bản ghi trong `fails` → tính lại theo công thức trên.
- 2 ca không lưu vốn đã `fabricated = 0` dưới tập **nhỏ hơn**, nên chắc chắn vẫn
  `0` dưới tập **lớn hơn** (tính đơn điệu).

Chỉ `fabricated_number` đổi. `citation_validity` (1.0), `both_source_coverage`
(0.75) và độ trễ không liên quan tới bug này.

### 3.3 Đây là phép thử thật, không phải đóng dấu

Baseline hiệu chỉnh **phải tự đạt gate của chính nó** (`fabricated_number == 0`):

| Kết quả chấm lại | Hành động |
|---|---|
| 4 → 0 | Bản sửa đúng. Đi tiếp §4 |
| 4 → 1 hoặc 2 | **DỪNG, báo cáo.** Hoặc bản sửa chưa đủ, hoặc qwen3:8b bịa thật. Điều tra trước khi đốt ~150 lượt gọi |

Bước này chạy **trước** lượt đo thật, nên nó vừa rẻ vừa là tín hiệu sớm.

### 3.4 Mất mát về độ chính xác — ghi rõ để không ai ngạc nhiên

Thêm `_format_context` cũng thêm các chỉ số `[1]`..`[8]` vào tập hợp lệ, nên
**số nguyên nhỏ 1–8 từ nay được coi là hợp lệ ở mọi vị trí** — một fabrication
dạng "3 ngày" sẽ không bị bắt nữa.

Bản chặt hơn (chỉ thêm nhãn, bỏ chỉ số) lại có nguy cơ **báo oan** khi model
trích dẫn nội dòng dạng `[2]`. Không có lựa chọn nào thắng trên giấy.

**Bước chấm lại ở §3.2 chính là trọng tài:** nếu bản rộng cho 4 → 0, giữ bản
rộng và ghi lại mất mát này. Nếu không, cân nhắc lại bản chặt. Quyết định dựa
trên số đo, không dựa trên tranh luận.

### 3.5 Xuất xứ

Baseline hiệu chỉnh **ghi đè đúng tên file cũ** (để `eval_gate.BASELINES` không
phải đổi), kèm hai trường tự khai:

```json
"rescored_at": "2026-...",
"original_fabricated_number": 4
```

`git diff` của commit đó là bằng chứng xuất xứ đầy đủ. Script chấm lại phải
**tất định và idempotent** — chạy hai lần ra cùng kết quả.

---

## §4. Chạy cổng M3

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Model mỗi bộ | `chain_for(ROLE_FOR_SET[set])[0]`, ghim; alias ghi vào kết quả | `llm/catalog.py` |
| Nhịp giữa 2 lượt | `(60 / spec.rpm) * 1.2` giây — tức **chậm hơn** mức RPM cho phép 20% để có biên | `ModelSpec.rpm` |
| Số ca | **159**: intent 54, confirm 24, planner 25, read 20, **chitchat 16**, synthesis 12, multi_source 8 | `evals/cases.py` |
| Thời lượng | ~10–15 phút cả 7 bộ — nhịp chờ ≈ 9 phút, **cộng** độ trễ model thật (baseline ghi `multi_source` p50 ≈ 7.0s/ca) | tính từ RPM 15–30 + `lat_p50` baseline |
| Hạn mức | **Không phải rào cản** — mọi bộ lọt trong RPD model đầu chuỗi; **không bộ nào chạm OpenRouter** (~50/ngày) | đối chiếu `CATALOG` |
| Khôi phục | Checkpoint sẵn có `_checkpoint-eval-gate-{set}.json` + `run_resilient` retry có trần; lỗi hạ tầng → `INFRA_ERROR`, không gate và không lưu baseline | `jobs/` |

**Công thức `_gate()` giữ nguyên văn** — nó mã hoá ADR-009 M3, không phải chỗ
để tối ưu. Sáu bộ so baseline; `chitchat` gate tuyệt đối (`violations == 0`) vì
chit-chat tự do không có "câu trả lời đúng" để làm baseline.

**Đầu ra:** bảng trước/sau, một dòng mỗi bộ, kèm alias model đã ghim và cả hai
phía số liệu.

**Gate đỏ nghĩa là gì:** C2 **không được bắt đầu**. Điều tra, sửa model/prompt,
chạy lại. Đây là toàn bộ lý do C tách đôi.

---

## §5. Testing

| Nhóm | Nội dung |
|---|---|
| Blocker #1 | DSN không tới được → fail **nhanh** (< ~3s), không phải ~90s |
| Blocker #2 | Store giả chậm + một task chạy song song: task kia **vẫn tiến** trong lúc `ainvoke` đang chờ sổ — chứng minh event loop không bị chặn, không chỉ chứng minh "có gọi to_thread" |
| Blocker #3 | `tiktoken` không nạp được → dùng ước lượng thô, **không chạm mạng**, hàm vẫn trả số dùng được |
| Harness | `_llm` thay thế ghim đúng (`decision.spec.alias == alias yêu cầu`) **và** ghim không đọc sổ ngân sách |
| Scanner | Chunk có nhãn mục chứa số → **không** bị quy là bịa (test tái hiện đúng bug đã biết) |
| Chấm lại | Tất định và idempotent; chạy hai lần ra cùng kết quả |
| Quy ước | Grep toàn repo: không còn `backend.src`, `sys.path.insert`, `LITELLM_`, `model_for`, `is_qwen` |

Ba chế độ giữ nguyên quy ước SP-1B (mặc định không mạng/không Postgres,
`-m integration`, `-m live`). Bản thân lượt chạy gate là `@pytest.mark.live` —
nó tiêu hạn mức thật.

---

## §6. "SP-1C1 xong" nghĩa là

1. Ba blocker vá xong, **mỗi cái có test chứng minh không còn** — không phải
   "đã sửa", mà là "đã chứng minh".
2. `backend/evals/` + `backend/jobs/` chạy được trong Youdoo; grep sạch dấu vết
   LiteLLM / `model_for` / `is_qwen` / `backend.src`.
3. Scanner `multi_source` sửa; baseline chấm lại; **baseline hiệu chỉnh tự đạt
   gate của chính nó** — nghịch lý "baseline trượt gate của chính mình" biến mất.
4. 7 bộ chạy thật với model ghim → bảng trước/sau đầy đủ, có alias model.
5. Gate xanh → mở đường C2. Gate đỏ → báo cáo rõ ràng và C2 **dừng**.
6. Toàn bộ test xanh ở cả ba chế độ.

**Chưa làm được sau C1:** chưa có HTTP endpoint, chưa có trace. Đó là C2.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

Theo luật đã áp dụng từ SP-0 (quyết định nào đời sau không được phép bàn lại thì
phải có comment trong **file được version-control**, tại đúng điểm mã nó ảnh
hưởng):

| Quyết định | File |
|---|---|
| Timeout pool cố ý **ngắn** vì sổ ngân sách là tư vấn và đã fail-open | `backend/src/llm/store.py`, tại `ConnectionPool(...)` |
| `to_thread` ở đây, và **`BudgetLedger` cố ý ở lại đồng bộ** để giữ thiết kế "chính sách thuần, không biết Postgres tồn tại" | `backend/src/llm/router.py`, tại hai điểm `to_thread` |
| Ước lượng thô chấp nhận được vì `total_tokens` mới là con số có thẩm quyền | `backend/src/llm/tokens.py`, tại nhánh fallback |
| Basis của `allowed` phải khớp **đúng thứ model nhìn thấy** (`_format_context`), kèm mất mát 1–8 đã biết | `backend/evals/run_eval.py`, tại `allowed = ...` |
| Chấm lại dùng danh sách `fabricated` đã lưu, **không** dùng `response` (đã cắt cụt 300 ký tự) | script chấm lại |
| Eval đo qua `Router` với `pin` vì `pin` không đọc sổ nhưng `_finish` vẫn ghi | `backend/evals/run_eval.py`, tại hàm dựng LLM |

## Phụ lục B — Rủi ro đã biết

| Rủi ro | Xử lý |
|---|---|
| Bản sửa scanner làm mất khả năng bắt fabrication số 1–8 | Ghi rõ ở §3.4; bước chấm lại là trọng tài; nếu 4 → 0 thì giữ và chấp nhận có ghi chép |
| Gate đỏ ở một bộ nào đó | Đúng chức năng của gate. C2 dừng, điều tra. Không có đường vòng |
| `to_thread` tốn một thread mỗi lượt gọi | Pool psycopg vốn đã đồng bộ; thread ở đây chỉ thay chỗ chặn, không tạo thêm việc. Nếu thành nút cổ chai thì đó là lúc cân nhắc sổ async thật — có số đo mới bàn |
| 2 ca `multi_source` không lưu trong `fails` không kiểm chứng lại được trực tiếp | Tính đơn điệu bảo đảm chúng vẫn `0`. Lập luận ghi ở §3.2, không phải giả định ngầm |
| Baseline `chitchat` không tồn tại nên không có "trước" để so | Cố ý từ SP-0: chit-chat tự do không có câu trả lời đúng. Gate tuyệt đối `violations == 0` thay thế |
