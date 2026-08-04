# Tách tầng định tuyến thành một đơn vị có tên — Design

**Ngày:** 2026-08-04
**Trạng thái:** đã chốt với chủ dự án, chưa lập plan

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| SP-2a | SOP skill dạng thư mục | xong, đã merge |
| SP-2b | Fan-out đường đọc; `fusion` chết | xong, đã merge |
| SP-2c | Bộ đo `gather_erp` | xong, đã merge (giả thuyết bị bác bỏ) |
| *(không đánh số)* | **Supervisor nuốt `intent_router`** | **HUỶ — xem §0** |
| *(spec này)* | Tách tầng định tuyến thành đơn vị có tên | brainstorm xong |

---

## §0. Vì sao đây KHÔNG phải "supervisor phase"

Giai đoạn kế tiếp trong roadmap từ SP-2a tới nay luôn được gọi là *"supervisor
nuốt `intent_router`"*. Nó bị huỷ. Ghi lại đầy đủ ở đây vì đời sau **không
được bàn lại mà không đọc phần này**, và vì bản thân chuỗi lập luận này là
tài sản của dự án.

### 0.1 Câu hỏi mở đã đóng, hai lần, độc lập nhau

`2026-08-01-sp2b-read-fanout-design.md` §7 đã chốt: một supervisor LLM
**không được thay** lớp phủ quyết tất định, chỉ được **đứng trước** nó —
*"y hệt vai trò router hiện tại"*. Bằng chứng nội bộ: sự cố live 2026-07-16
(lệnh thật lỡ route **3/3 lần**), thí nghiệm model 2026-07-31 (`gemini-3.1-
flash-lite` **hoà** đúng ca đang FAIL với `gemma-4-26b`; `groq-gpt-oss-120b`
**tệ hơn**, đẻ thêm 1 ca hijack mới).

Research độc lập do chủ dự án đặt ngoài dự án (nhận 2026-08-04, 8 câu hỏi)
xác nhận lại bằng nguồn ngoài: đây là hiện tượng *inverse / U-shaped scaling*
đã công bố (McKenzie et al., "Inverse Scaling: When Bigger Isn't Better,"
TMLR 2023 — mô hình lớn hơn dựa vào prior lúc pretrain nhiều hơn, bám prompt
ít hơn), và pattern chuẩn ngành cho đúng tình huống này là **hybrid: lớp đề
xuất + veto tất định**, đúng thiết kế đang có.

**Hệ quả:** một supervisor được phép tồn tại sẽ làm đúng việc `intent_router`
đang làm. Đó là đổi tên, không phải giai đoạn.

### 0.2 Ứng viên thay thế cũng đã bị bác bỏ — bằng đo, cùng ngày

SP-2b §7 nói tiếp: *"Khoảng trống thật còn lại không phải 'cần supervisor'"*
— mà là năng lực truy xuất lại khi thiếu căn cứ, tên chuẩn là **Corrective
RAG / Adaptive-RAG**, và đó *"là ứng viên hợp lý hơn cho giai đoạn kế tiếp,
thay vì supervisor"*.

Đã đo thật trước khi xây (2026-08-04, cùng kỷ luật SP-2c). Chạy `--set
multi_source_gather` live (`gemini-3.1-flash-lite`, Postgres + Odoo;
`both_source_coverage=0.750`, log `logs/jobs/eval-gate-20260804T173640.json`)
rồi tái dựng 2 ca fail bằng chính hàm production (`make_gather_erp_node` +
`render_fuse_input` + `FUSE_PROMPT`), lấy câu trả lời **không bị cắt** — bản
trong log bị cắt còn 300 ký tự (`run_eval.py:727`, `body[:300]`) nên không đủ
để chẩn đoán lớp lỗi này.

- Ca `sla_giao_hang`/S00042 (`fabricated=["01"]`): đúng giới hạn digit-scanner
  đã biết, không liên quan.
- Ca `sla_giao_hang`/WH-OUT-00001: **chunk đúng (`[23790]`, chứa nguyên văn
  `doc_fact` "0,5%") ĐÃ nằm sẵn** trong context đưa vào `fuse_answer`, cạnh 3
  chunk nhiễu. Câu trả lời đầy đủ không hề nhắc "0,5%" — model xây câu trả lời
  quanh chunk `23788` sai-nhưng-gần-chủ-đề.

**Kết luận:** đây là lỗi **tổng hợp / chọn chunk trong `fuse_answer`**, không
phải thiếu retrieval. CRAG nhắm vào *dưới-truy-xuất*; ca này là *truy xuất đủ
nhưng chọn sai* — CRAG không chạm tới. Không xây CRAG dựa trên bằng chứng này.
(Lỗi tổng hợp đó đã được xử lý riêng, ngoài phạm vi spec này — xem plan
`2026-08-04-fuse-prompt-obligation-penalty-fix`.)

### 0.3 Vì sao hierarchical không phải kiến trúc đúng cho miền này

Chủ dự án đặt thẳng câu hỏi: ERP trợ lý này có cần kiến trúc agent phân cấp
không. Trả lời, suy từ tính chất miền chứ không từ thời thượng:

1. **Không gian task ĐÓNG và liệt kê được** (đơn/hoá đơn/giao hàng/tồn kho,
   hoặc 1 trong N SOP — biết hết lúc build). Đây đúng là điều kiện dùng
   **Routing**. **Orchestrator-Workers** dành cho task *không đoán trước được
   cách phân rã* — ERP đoán được, nên dùng nó là trả giá phân rã động cho một
   bài toán tĩnh.
2. **Write không đảo ngược được** → bắt buộc human-in-the-loop + cổng tất
   định. Loại **Blackboard** (rủi ro write-conflict + vòng lặp vô hạn) và
   **Swarm/Mesh** (không có đường quyền hạn rõ để gắn confirm-gate).
3. **Suy luận vốn tuần tự** — phát hiện thực nghiệm của chính dự án
   (SP-2b §1.2: cả 8 ca `mixed` đều cần *một giá trị trong tài liệu* để *diễn
   giải* một bản ghi ERP → *"chỉ thu thập mới song song được"*). Loại
   **Aggregator/voting** và **Mesh**. Khớp cảnh báo của Anthropic mà research
   trích: *"domains that require all agents to share the same context ... are
   not a good fit for multi-agent systems today."*
4. **Chat tương tác + quota free-tier** → mỗi tầng điều phối là thêm 1 hop LLM.

Thêm nữa: **dự án ĐÃ có phân cấp thực thi**. Mỗi SOP skill là sub-agent tự
chủ (ReAct loop riêng, tool bị `SKILL.md` giới hạn quyền, `recursion_limit`
riêng, `ask_human` riêng); write coordinator cũng là subgraph riêng. Thứ
không có là *LLM supervisor* ở tầng đỉnh — và đó là lựa chọn có số đo chứng
minh, không phải thiếu sót.

Và SP-2a §8 đã nêu cơ chế: SOP **bàn giao**, không quay về —
*"Không ai cần điều phối nó."* Supervisor tồn tại để điều phối thứ quay về.

**Khi nào Tầng-2 mới chính đáng ở đây:** khi các agent khác nhau về **phần
cứng / vòng đời / quyền hạn**, không phải khi chúng chỉ khác chủ đề câu hỏi.
Trường hợp đó đã nằm sẵn trong roadmap — **SP-4 meeting agent** (Whisper trên
GPU + Groq, chạy nền theo lịch riêng), đúng 2 trigger mà ADR-008 §5 đã
pre-register và ADR-010 gọi là *"strongest concrete justification"*.

---

## §1. Động cơ

**Một động cơ duy nhất, chủ dự án chốt 2026-08-04: kiến trúc rõ để trình bày
portfolio.** Đây là ưu tiên B của ADR-010, và có tiền lệ — SP-2b §1.1 ghi
thẳng động cơ của chính nó là *"kiến trúc rõ và tái dùng được"*, kèm thừa
nhận *"không có lỗi vận hành nào đang thúc việc này"*.

Ghi rõ để đời sau không suy diễn lại: **chất lượng trả lời và latency KHÔNG
phải mục tiêu.** Không kỳ vọng một số đo nào nhúc nhích. Chất lượng là **sàn
phải giữ**, không phải thứ biện minh cho việc làm spec này.

### 1.1 Vấn đề cụ thể: pattern có thật, nhưng không hiện diện trong mã

Tầng định tuyến hôm nay là hybrid 2 lớp — nhưng nằm rải ở 4 file, và **không
file nào tự nhận mình là tầng định tuyến**:

| Mảnh | Vị trí (xác nhận tại HEAD `4c2fd49`) | Lớp |
|---|---|---|
| `INTENT_ROUTER_PROMPT`, `render_intent_router_prompt` | `prompts.py:26-58` | đề xuất |
| `VALID_INTENTS` | `nodes.py:28` | đề xuất |
| `_parse_router_output` | `nodes.py:31-57` | đề xuất |
| `make_intent_router_node` | `nodes.py:60-84` | đề xuất |
| `_QUESTION_MARKERS` | `graph.py:25-29` | **veto** |
| `_looks_like_question` | `graph.py:32-33` | **veto** |
| `_route_by_intent` | `graph.py:36-65` | **veto** |
| `_fold` | `skill_gate.py` | veto (dùng chung) |
| `intent_targets`, `add_conditional_edges` | `graph.py:123-131` | wiring |

Lời giải thích đầy đủ nhất về pattern này (15 dòng, gồm cả bằng chứng sự cố
3/3) nằm trong docstring của `_route_by_intent` — chỗ người đọc mới không tìm
tới trước. Muốn hiểu cơ chế phải đọc 4 file và tự ghép.

### 1.2 Vấn đề này KHÔNG phải thiếu test

Đã kiểm tra, để không giải sai bài: tầng này đã có **28 test đơn vị** — 19
trong `test_intent_router.py` (parse fail-safe, hành vi node, render prompt),
8 trong `test_graph_build.py` (marker câu hỏi, veto, kill-switch), 1 contract
test trong `test_fanout_graph.py` — cộng bất biến cấu trúc toàn đồ thị
`test_skill_nodes_reachable_only_from_intent_router`
(`test_graph_build.py:327`) chốt *"node SOP chỉ vào được từ `intent_router` —
nơi DUY NHẤT áp phủ quyết tất định"*. Spec này **không** thêm cơ chế test
mới cho lớp lỗi nào; đây thuần là vấn đề **hiện diện**, không phải **bảo vệ**.

---

## §2. Kiến trúc

### 2.1 File mới `backend/src/agents/routing.py`

Chuyển vào, giữ nguyên logic từng dòng:

| Từ | Symbol cũ | Tên mới | Lớp |
|---|---|---|---|
| `nodes.py:28` | `VALID_INTENTS` | *(giữ)* | đề xuất |
| `nodes.py:31-57` | `_parse_router_output` | `parse_proposal` | đề xuất |
| `nodes.py:60-84` | `make_intent_router_node` | *(giữ — xem §2.3)* | đề xuất |
| `graph.py:25-29` | `_QUESTION_MARKERS` | *(giữ)* | veto |
| `graph.py:32-33` | `_looks_like_question` | `looks_like_question` | veto |
| `graph.py:36-65` | `_route_by_intent` | `decide_route` | veto |

**Ở nguyên chỗ cũ, có lý do:**

| Thứ | Vì sao không chuyển |
|---|---|
| `INTENT_ROUTER_PROMPT`, `render_intent_router_prompt` | Quy ước dự án: **mọi** prompt sống ở `prompts.py`. Phá quy ước đó tốn nhiều hơn được |
| `intent_targets`, `add_conditional_edges` | Đó là **sơ đồ**, không phải logic định tuyến. `graph.py` đúng vai khi giữ nó |
| `_fold` (`skill_gate.py`) | Dùng chung ngoài routing; kéo sang là mở rộng phạm vi vô cớ |

### 2.2 Payload thật của spec này: docstring đầu `routing.py`

Đây là thứ duy nhất trong repo nói trọn hợp đồng 2 lớp ở một chỗ. Bắt buộc có:

1. **Lớp 1 — xác suất.** LLM đề xuất `intent` + `sop` trong **cùng một** lượt
   gọi (không tốn call thêm — quan trọng khi OpenRouter ~50 req/ngày).
2. **Lớp 2 — tất định, và nó THẮNG.** Điều kiện veto không phụ thuộc phân
   loại LLM.
3. **Bằng chứng vì sao lớp 2 tất định**: sự cố live 2026-07-16 (3/3), thí
   nghiệm model 2026-07-31 (model to hơn hoà hoặc tệ hơn), inverse scaling
   (McKenzie et al., TMLR 2023).
4. **Điều kiện để được tháo veto** — hiện tại: **không có điều kiện nào**.
   Muốn tháo phải có số đo mới bác bỏ được cả 3 bằng chứng trên.
5. **Lưới đỡ cuối không phải lớp này**: router sai chiều nào thì confirm-gate
   tại tool boundary vẫn chặn mọi write chưa duyệt.

### 2.3 Một thứ KHÔNG được đổi tên — tên node graph `"intent_router"`

Ràng buộc cứng. Ba lý do, lý do đầu là lý do chặn:

1. **Checkpoint đang sống.** Dự án dùng `interrupt()` + Postgres checkpointer
   nặng (`confirm`, `free_text`, `disambiguation`). Tên node nằm trong
   checkpoint đã lưu — đổi tên làm hỏng resume của mọi hội thoại đang park ở
   cổng xác nhận.
2. `test_skill_nodes_reachable_only_from_intent_router` assert
   `source == "intent_router"`.
3. Trace Langfuse mất tính liên tục trước/sau.

Vì node giữ tên nên factory `make_intent_router_node` **cũng giữ tên** — nó
đặt tên cho node nó dựng, lệch tên sẽ gây hiểu nhầm nặng hơn cái được. Việc
đặt tên theo lớp diễn ra ở `parse_proposal` / `decide_route` /
`looks_like_question` / `RouteProposal`.

### 2.4 Kiểu mới `RouteProposal`

```python
class RouteProposal(NamedTuple):
    intent: str          # luôn thuộc VALID_INTENTS; "unknown" khi không parse được
    sop: str | None      # ĐỀ CỬ, chưa phải quyết định — decide_route có quyền bỏ
```

`parse_proposal()` trả `RouteProposal` thay cho `tuple[str, str | None]`.

**Vì sao NamedTuple chứ không dataclass:** `eval_sop_select` unpack kiểu
tuple (`intent, sop = _parse_router_output(...)`, `run_eval.py:447`).
NamedTuple **vẫn là tuple** nên chỗ đó không gãy — đây là ràng buộc chọn kiểu,
không phải sở thích.

Giá trị: từ nay chữ ký hàm tự nói cái đi ra khỏi lớp 1 là *đề cử*, không phải
*đường đi*. Đó là điểm mà mọi người đọc mới hiểu sai đầu tiên.

### 2.5 Luồng dữ liệu — không đổi một bước

```
message ──► [node "intent_router"] ──state──► [decide_route] ──► node đích
             lớp 1: LLM đề xuất               lớp 2: tất định
             RouteProposal(intent, sop)       veto thắng → trả 1 chuỗi
```

Hai lớp **buộc phải** là node + conditional-edge riêng: LangGraph persist
state giữa chúng. Nên chúng không gộp được thành một hàm, và **đơn vị làm rõ
là FILE, không phải hàm.** Ghi rõ điều này trong docstring để đời sau không
tưởng là thiết kế dở.

---

## §3. Vệ sinh cross-reference

Chỗ dự án đã bị bỏng **hai lần liên tiếp** (cả 2 final review gần nhất đều
bắt lỗi comment lỗi thời) — nên đây là **hạng mục công việc**, không phải dọn
dẹp phụ.

### 3.1 Import site — 5 file phải sửa

`src/agents/graph.py` · `evals/run_eval.py:38-39` ·
`tests/agents/test_intent_router.py` · `tests/agents/test_graph_build.py` ·
`tests/agents/test_fanout_graph.py:55`

**Không để lại shim re-export ở `nodes.py`/`graph.py`.** Shim là đúng thứ sẽ
mục: nó cho phép import cũ sống tiếp nên không ai biết chỗ nào còn dùng đường
cũ. Sửa hết import site, fail-loud nếu sót.

### 3.2 Comment/docstring viết tên theo đường dẫn cũ — 8 file, 13 dòng

| File | Dòng | Nội dung sai sau khi chuyển |
|---|---|---|
| `src/agents/prompts.py` | 23 | `graph._route_by_intent` |
| `src/agents/skill_manifest.py` | 14 | `(graph._route_by_intent)` |
| `src/agents/state.py` | 14 | `graph._route_by_intent` |
| `src/agents/fanout.py` | 61, 63, 65 | `_route_by_intent` ×2, `_looks_like_question` |
| `evals/cases.py` | 568 | `_route_by_intent() TRẢ VỀ` |
| `tests/agents/test_build_graph_skill_integration.py` | 145-146 | `graph._route_by_intent` |
| `tests/agents/test_fanout_graph.py` | 53-54 | tên test + docstring |
| `tests/agents/test_graph_build.py` | 206, 211-212, 249 | `_looks_like_question`, `_route_by_intent` |

### 3.3 Ranh giới: KHÔNG sửa file trong `docs/superpowers/specs/`

Spec cũ là **hồ sơ lịch sử** ghi quyết định tại thời điểm đó. Sửa chúng cho
khớp mã hôm nay là làm giả hồ sơ và phá chính giá trị mà spec này (§0) đang
dựa vào. Spec cũ nói `graph._route_by_intent` thì để nguyên — đúng tại thời
điểm viết.

---

## §4. Xử lý lỗi — không đổi

`parse_proposal` giữ nguyên fail-safe cả ba hướng:

- intent không nhận ra → `"unknown"`;
- tên SOP model bịa → `None` (không bao giờ thành node đích — nếu trả ra sẽ
  làm LangGraph ném lỗi định tuyến giữa một lượt chat thật);
- không thấy format 2 dòng → đọc cả chuỗi như MỘT từ intent (back-compat hợp
  đồng cũ; model nhỏ hay bỏ format).

Không thêm nhánh lỗi nào. Không đổi hành vi kill-switch `skills_enabled()`.

---

## §5. Kiểm chứng

### 5.1 Bằng chứng CHÍNH — test đơn vị hiện có, assert không đổi

**28 test** của tầng này (§1.2) chạy lại với **nội dung assert không đổi một
ký tự**, chỉ đổi dòng import. Đây là điều kiện quyết định:

> **Nếu một assert phải sửa nội dung → đã đổi hành vi → DỪNG, báo cáo, không
> tự sửa assert cho khớp.**

Cộng toàn bộ suite unit-only: `pytest -m "not integration and not live"`.
Plan phải **chụp baseline TRƯỚC khi sửa dòng đầu tiên** (số passed/skipped
tại HEAD lúc bắt đầu) rồi đối chiếu sau — **không tăng số fail**. Không cite
con số từ plan cũ: `main` đang được nhiều nhánh merge vào, con số cũ có thể
đã lệch.

### 5.2 Bằng chứng cấu trúc

`test_skill_nodes_reachable_only_from_intent_router` phải vẫn xanh — chứng
minh việc chuyển nhà không làm thủng seam bảo mật. Test này assert trên
**tên node** (`"intent_router"`), nên nó cũng là canh gác cho §2.3.

### 5.3 Test MỚI — đúng 1, rẻ

`RouteProposal` unpack được thành 2-tuple (`intent, sop = parse_proposal(...)`).
Khoá lại chính chỗ back-compat mà `eval_sop_select` đang dựa vào — nếu ai đó
sau này đổi `RouteProposal` sang dataclass thì test này đỏ trước khi eval gãy.

### 5.4 Xác nhận (KHÔNG phải bằng chứng chính)

Một lượt `--set sop_select` thật. Bar chuẩn từ SP-2b §8.4: `hijack = 0`,
`acc ≥ 16/17` (gate tuyệt đối của set này biết trước là không xanh — ca hồi
quy 2026-07-16).

**Ghi rõ giới hạn của phép đo này:** prompt byte-identical và logic
parse/veto byte-identical, nên chênh lệch nếu có là do **sampling của model**,
**không** kết luận được gì về refactor. Bằng chứng thật là §5.1. Không dùng
số này để tuyên bố thành công, và cũng không dùng nó để kết luận thất bại nếu
lệch — nếu lệch, đối chiếu lại §5.1 trước.

---

## §6. Ngoài phạm vi — cố ý

| Hạng mục | Vì sao không làm ở đây |
|---|---|
| Supervisor / hierarchical | §0 |
| Corrective RAG / vòng truy xuất thứ hai | §0.2 — đã đo, bác bỏ |
| Interface plugin cho lớp đề xuất (`semantic-router`, classifier fine-tune) | YAGNI. Chưa quyết định thay. Đặt tên rõ **đã là** seam; abstraction là thứ khác. Research khuyến nghị đường nâng cấp này nhưng không ai đã chọn đi |
| Sửa `_QUESTION_MARKERS` (thêm/bớt dấu hiệu) | Đổi **hành vi**. Phải có ca fail thật làm cớ và một lượt đo riêng để quy trách nhiệm |
| Đổi tên node graph | §2.3 — checkpoint đang sống |
| Đổi text prompt, đụng đường ghi, đụng fan-out | Không liên quan |
| Sửa spec cũ trong `docs/superpowers/specs/` | §3.3 |

---

## §7. "Xong" nghĩa là

1. `backend/src/agents/routing.py` tồn tại, chứa đủ 6 symbol ở §2.1 với
   docstring đầu file theo §2.2.
2. `_QUESTION_MARKERS`, `_looks_like_question`, `_route_by_intent` **không
   còn trong `graph.py`**; `VALID_INTENTS`, `_parse_router_output`,
   `make_intent_router_node` **không còn trong `nodes.py`**. Không có shim
   re-export ở cả hai file.
3. Tên node graph vẫn là `"intent_router"`.
4. 5 import site đã sửa; 8 chỗ comment ở §3.2 đã sửa; không file nào trong
   `docs/superpowers/specs/` bị đụng.
5. 28 test cũ xanh với **assert không đổi nội dung**; suite unit-only không
   tăng số fail so với baseline chụp ở đầu plan.
6. Test mới ở §5.3 xanh.
7. Một lượt `--set sop_select` đã chạy, số ghi vào report kèm ghi chú giới
   hạn ở §5.4.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

Theo standing rule ADR-010 (quyết định nào đời sau không được bàn lại thì
phải có comment trong **file được version-control**, tại đúng điểm mã nó ảnh
hưởng):

| Quyết định | File, vị trí |
|---|---|
| Hợp đồng 2 lớp + bằng chứng + điều kiện tháo veto (hiện: không có) | `routing.py`, docstring đầu file |
| Tên node `"intent_router"` không được đổi vì checkpoint đang sống | `routing.py`, tại `make_intent_router_node` |
| `RouteProposal` phải là NamedTuple vì `eval_sop_select` unpack kiểu tuple | `routing.py`, tại định nghĩa `RouteProposal` |
| Hai lớp buộc tách node/edge do LangGraph persist state — file là đơn vị làm rõ | `routing.py`, docstring đầu file |
| Supervisor/hierarchical bị huỷ, kèm lý do và điều kiện Tầng-2 chính đáng | spec này §0; con trỏ tới spec đặt ở `routing.py` docstring |

## Phụ lục B — Rủi ro đã biết, chấp nhận

| Rủi ro | Vì sao chấp nhận |
|---|---|
| Refactor thuần, không có số đo nào chứng minh "tốt hơn" | Đúng bản chất mục tiêu (§1). Bằng chứng an toàn là §5.1, không phải bằng chứng cải thiện |
| `graph.py` mỏng đi, người quen mã cũ phải tìm chỗ mới | Một lần, và đó chính là điều đang muốn: chỗ mới có tên đúng |
| Sót một comment cross-reference | §3.2 liệt kê đủ 8 file / 13 dòng đã grep tại HEAD `4c2fd49`; plan phải grep lại trước khi đóng (`main` đang nhận merge từ nhánh khác, danh sách có thể dài thêm) |
