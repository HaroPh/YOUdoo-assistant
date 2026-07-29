# SP-2a: Nền tảng SOP skill dạng thư mục — thiết kế

**Mục tiêu:** Đưa quy trình nghiệp vụ (SOP) ra khỏi mã Python, vào thư mục
`SKILL.md` mà người dùng low-code sửa được — mà không nhường một chút thẩm
quyền ghi nào cho markdown.

**Bối cảnh:** SP-1A (LLM gateway) và SP-1B (port tầng nghiệp vụ) đã xong và
merge vào `main`. Ba skill agentic tier-2 ở repo nguồn `D:\Project` **cố ý
chưa port** ở SP-1 — spec SP-1 ghi rõ chúng "chính là hình dạng specialist
agent SP-2 sẽ dựng lại, port vào cấu trúc sắp bị thay là công toi". Spec này
là lượt dựng lại đó.

---

## §0. Vị trí trong lộ trình và phạm vi

| SP | Nội dung | Trạng thái |
|---|---|---|
| SP-1A / SP-1B | Gateway + tầng nghiệp vụ | **xong, đã merge** |
| **SP-1C** | `main.py` FastAPI `/v1` + Langfuse + port eval harness + eval gate | **làm trước spec này** |
| **SP-2a** | *(spec này)* Nền tảng SOP skill: thư mục `SKILL.md`, loader, định tuyến hybrid, di trú 3 skill, bộ eval chọn-SOP | brainstorm xong |
| SP-2b | Topology: supervisor nuốt `intent_router`, `fusion` chết, fan-out đường đọc | sau, cần số đo từ SP-1C |

### Vì sao SP-1C phải đi trước

Không phải lý do thủ tục. Hai lý do cơ học:

1. **Bộ eval chọn-SOP (§5) chạy trên harness của SP-1C.** Không có harness thì
   không có cách nào biết định tuyến mới đúng hay sai.
2. **Không có `/v1` thì người sửa SOP không có gì để thử.** "Low-code
   authoring" mà không chạy thử được thì chưa phải năng lực.

### Trong phạm vi

- Cấu trúc thư mục `backend/skills/<tên>/SKILL.md` + schema frontmatter.
- Loader: quét, validate fail-loud, sinh tool wrapper đã gate, dựng node.
- Định tuyến hybrid: `description` đề cử (xác suất) + marker câu hỏi phủ
  quyết (tất định).
- Di trú 3 skill tier-2 từ `D:\Project`.
- Bộ eval `SOP_SELECT_CASES` mới.
- Port `agentic_gate.py` + `agentic_context_sync.py` (không sửa).

### Ngoài phạm vi — cố ý

| Hạng mục | Vì sao không làm ở đây |
|---|---|
| UI soạn thảo SOP trong trình duyệt | Là một SP riêng: cần auth, versioning, preview. Giai đoạn này "low-code user" = người sửa file bằng editor thường |
| Lưu SOP trong Postgres | Kéo theo migration, đồng bộ, phân quyền — chưa đáng khi số SOP còn đếm trên đầu ngón tay |
| Hot-reload | SOP nạp lúc khởi động; sửa thì restart backend (~vài giây). Nạp lại lúc chạy cần cô lập lỗi và khoá đồng thời, không đáng đổi |
| Orchestrator / bỏ `intent_router` | SP-2b. Xem §8 — spec này thiết kế để việc đó rẻ, không phải để tránh nó |
| Đụng đường ghi tier-1 (18 coordinator + executor) | Bất biến bảo mật đã được review toàn nhánh SP-1B xác minh và có test chốt. Không có lý do chạm vào |
| Progressive disclosure (file tham chiếu nạp khi cần) | Xem §1.3 — vô dụng với kiến trúc hiện tại trừ khi mở thêm bề mặt tool |

---

## §1. Động cơ và bằng chứng

### 1.1 Động cơ

Hai động cơ, được nêu rõ để đời sau không suy diễn lại:

- **Chuyển SOP sang `.md`:** để **user low-code sửa được quy trình nghiệp vụ**
  mà không phải đụng Python, và bám theo **một chuẩn có sẵn** (Claude Code
  skill) cho quen thuộc.
- **Đổi topology (SP-2b):** **kiến trúc rõ ràng / portfolio** — ADR-010 ưu tiên
  B. Ghi rõ: **không có lỗi vận hành nào đang thúc việc này.** Đây là lý do
  SP-2b nằm sau và phải có số đo, chứ không phải làm ngay vì "nghe hay".

### 1.2 Tiền đề ban đầu đã bị bằng chứng bác bỏ

Giả định lúc đầu: *"skill viết thành file Python vì model nhỏ mất context khi
đọc full `skill.md`"*.

Đọc mã thật thì không phải: `skill_agentic_warehouse_receiving.py` truyền
**nguyên cả** `SOP_PROMPT` (~38 dòng prose) vào `create_agent(...)` làm system
prompt — không chia nhỏ, không nạp dần. Phần prose **đã** là "skill.md" rồi,
chỉ khác là nó nằm trong dấu nháy Python.

Thứ file `.py` thực sự mua được là chỗ khác: `_build_tools()` khiến
`receive_order` **không tồn tại** trong tầm với của model trừ khi đã bọc
`_confirm_write`. Và nguyên tắc cho đúng câu hỏi "model to hơn rồi thì có bớt
guard được không" đã có sẵn trong spec SP-1
(`2026-07-28-sp1-foundation-design.md:621`):

> **Guard bù cho sự kém cỏi thì co lại được. Guard ràng buộc thẩm quyền thì
> không.**

Nên: prose chuyển sang `.md` được; gate tool thì model mạnh hơn **càng cần**.

### 1.3 Skill Claude Code thật ra trông thế nào

Đo trực tiếp trên bộ skill đang chạy
(`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/`):

| # | Sự thật đo được | Áp dụng cho Youdoo? |
|---|---|---|
| 1 | Skill là **một thư mục**, không phải một file | **Có** — §2 |
| 2 | Frontmatter chỉ có `name` + `description` | **Một phần** — Youdoo buộc phải thêm `tools` (xem dưới) |
| 3 | `description` viết như **chỉ dẫn khi nào dùng**, không phải mô tả | **Có** — §2, §4 |
| 4 | Skill **có đóng gói mã chạy được** (`scripts/`) | **Có** — đây là chỗ `logic.py` ngồi |
| 5 | Progressive disclosure có thật, có ngân sách token | **Không** — xem dưới |
| 6 | Ba khuôn tổ chức theo độ phức tạp | **Có** — §2 dùng khuôn 1 và 3 |

Điểm 4 lật ngược cả giả định ban đầu lẫn đề xuất đầu tiên trong lúc
brainstorm ("hai hạng skill: khai báo `.md` vs mã `.py`"). Skill Claude Code
**không phải markdown thuần** — nó là *prose + mã, đóng gói chung một thư mục*.
Nên Youdoo dùng **một mô hình duy nhất**: mỗi skill một thư mục;
`bao-gia-chiet-khau` không phải "hạng khác", nó chỉ là skill có thêm
`logic.py` bên cạnh `SKILL.md`.

**Bốn chỗ Youdoo không bê nguyên được:**

1. **Mô hình tin cậy khác hẳn.** Skill Claude Code do chính người chạy nó viết,
   trên máy của họ. SOP Youdoo do **user nghiệp vụ** viết, chạy vào **ERP thật,
   ghi không hoàn tác được**. Claude Code không có gì tương đương
   `_confirm_write` vì nó không cần. Youdoo phải tự dựng tầng validate (§3).
2. **Skill Claude Code chạy mã qua Bash của agent. SOP Youdoo không được có
   Bash.** Tool bind lúc dựng graph, tool ghi bắt buộc qua wrapper gate. Nên
   `SKILL.md` **không bao giờ** nói "chạy script này" — mã do loader import và
   bind, không do model gọi. Đây là lý do frontmatter Youdoo phải có `tools`
   trong khi Claude Code thì không.
3. **Progressive disclosure gần như vô dụng ở đây.** Claude Code đọc file phụ
   *giữa chừng* vì nó có tool `Read`. SOP agent Youdoo là `create_agent` với
   đúng 3 tool cố định (`ask_human`, tool đọc, tool ghi đã gate) — **không có
   đường nào đọc file lúc chạy**. Muốn có disclosure phải cấp thêm tool đọc tài
   liệu, tức mở thêm bề mặt. Không làm ở SP-2a.
4. **Chọn skill bằng `description` là xác suất.** Xem §1.4 — đây là chỗ có bằng
   chứng phản đối mạnh nhất, và là lý do §4 chọn hybrid.

### 1.4 Bằng chứng quyết định hình dạng định tuyến

**Bằng chứng A — router LLM đã thua đúng bài này, 3/3 lần.**
`D:\Project\backend\src\agents\graph.py:41-51` ghi lại live-verify 2026-07-16:
bản đầu gate bằng `intent == "erp_write"` (AND) đóng được ca hijack gốc
("quy trình nhập kho là gì?" → skill thay vì RAG) nhưng lộ chiều lỗi ngược —
router phân loại `mixed`/`erp_read` cho **chính hai câu lệnh dùng nguyên văn
TRIGGERS**, khiến lệnh thật lỡ route **3/3 lần thử**. Nguyên nhân ghi rõ trong
mã: *"router chưa từng được tune để phân biệt 'hỏi về SOP' khỏi 'thực thi SOP
cho 1 đơn cụ thể'"*. Cách vá đã chứng minh hiệu quả: **chuyển gate sang tất
định** (`_looks_like_question`), không phụ thuộc phân loại LLM cho quyết định
này.

→ Giao **toàn bộ** việc chọn SOP cho `description` là quay lại đúng cơ chế đã
thua, chỉ đổi model. §4 giữ lại đúng một lớp tất định đó.

**Bằng chứng B — ranh giới tier-1/tier-2 hiện tại rất mong manh.**

| Nguồn | Nội dung |
|---|---|
| `evals/cases.py:29` (INTENT) | `("giao hàng cho đơn S00040 luôn nhé", "erp_write")` |
| `evals/cases.py:147` (PLANNER) | `("giao hàng cho đơn S00040", "deliver_order", {...})` |
| `skill_agentic_delivery.TRIGGERS` | `("giao hang cho don **ban**", "xuat kho cho don ban", "giao hang theo don")` |

Khác biệt duy nhất giữa "đi tier-1" và "đi SOP" là chữ **"bán"**. Với người
dùng, `giao hàng cho đơn S00040` và `giao hàng cho đơn bán S00040` là **một
ý**. Ranh giới đó không bảo vệ được → §5 thay bằng ranh giới bảo vệ được.

**Bằng chứng C — chưa từng có bộ eval nào đo việc chọn SOP.** Bảy bộ của SP-0
(`intent`, `confirm`, `chitchat`, `planner`, `read`, `synthesis`,
`multi_source`) không có bộ nào cho tier-2; ba skill SOP ra đời **sau** SP-0.
Nghĩa là mọi cơ chế chọn SOP — cũ lẫn mới — đều chưa có số. §5 dựng bộ đó.

### 1.5 Ba skill hiện tại lệch nhau rất xa

| Skill | Tổng dòng | Prose | Mã thật | Bản chất |
|---|---:|---:|---:|---|
| `delivery` | 68 | 24 | ~15 (bọc gate mỏng) | khai báo được |
| `warehouse_receiving` | 109 | 38 | ~30 (2 gate mỏng) | khai báo được |
| `discount_quote` | 177 | 29 | **~109** | **không khai báo được** |

Hai skill đầu là boilerplate gần như y hệt nhau (lấy tool theo tên → bọc
`_confirm_write` → `ainvoke`), sinh từ manifest được 100%.

`discount_quote` thì không, lý do nằm trong docstring của chính nó:

> **Bất biến tiền bạc:** % chiết khấu và đơn giá **LUÔN tính trong code** —
> model chỉ gom tham số, không bao giờ tính hay truyền số tiền.

`compute_discount_pct()`, `_render_discount_draft()`, vòng resolve khách/sản
phẩm rồi tra giá — ~109 dòng đó **là** bất biến an toàn. Đẩy vào markdown nghĩa
là giao việc tính tiền cho model. Đây là lý do khuôn "thư mục + `logic.py`"
(§1.3 điểm 4) là bắt buộc, không phải tuỳ chọn.

---

## §2. Cấu trúc thư mục và schema `SKILL.md`

```
backend/skills/                      # ngoài src/ — địa bàn của người sửa SOP
  giao-hang/
    SKILL.md                         # ✏️ low-code sửa được
  nhap-kho/
    SKILL.md                         # ✏️
  bao-gia-chiet-khau/
    SKILL.md                         # ✏️ prose quy trình
    logic.py                         # 🔒 bất biến tiền bạc — KHÔNG đụng
```

### 2.1 Skill khai báo thuần

`backend/skills/giao-hang/SKILL.md` — tái tạo 100% hành vi
`skill_agentic_delivery.py`:

```markdown
---
name: giao-hang
description: >
  Dùng khi người dùng muốn THỰC HIỆN quy trình giao hàng đầy đủ cho một đơn
  bán đã xác nhận (tra đơn, kiểm tra, xác nhận giao).
  KHÔNG dùng khi: người dùng chỉ HỎI về quy trình giao hàng (đó là tra cứu
  tài liệu), hoặc ra lệnh giao nhanh một đơn cụ thể mà không nhắc tới quy
  trình (đó là lệnh ghi trực tiếp, đi qua planner tier-1).
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
---

Bạn là trợ lý kho, thực hiện quy trình giao hàng cho đơn bán.
Bạn có các công cụ: get_sale_order_detail (tra chi tiết đơn bán), ask_human
(hỏi người dùng và chờ trả lời), deliver_order (xác nhận giao hàng vào Odoo).

Quy trình, làm đúng thứ tự:
1. Xác định mã đơn bán cần giao hàng từ yêu cầu của người dùng. Nếu tin nhắn
   chưa nêu rõ mã đơn, dùng ask_human để hỏi.
...
```

### 2.2 Skill có mã riêng

`backend/skills/bao-gia-chiet-khau/SKILL.md`:

```markdown
---
name: bao-gia-chiet-khau
description: >
  Dùng khi người dùng muốn tạo báo giá CÓ CHIẾT KHẤU theo cấp khách hàng.
  KHÔNG dùng khi: người dùng chỉ hỏi về chính sách chiết khấu (tra cứu tài
  liệu), hoặc muốn tạo báo giá thường không chiết khấu (lệnh ghi tier-1).
entry: logic.py
declares_tools: [create_discount_quote]
---

Bạn là trợ lý bán hàng, thực hiện quy trình báo giá có chiết khấu theo cấp
khách hàng.
...
```

`logic.py` cung cấp đúng một hàm: `build_tools(mcp_tools) -> list[BaseTool]`.
Nội dung là ~109 dòng chuyển nguyên từ `skill_agentic_discount_quote.py`.

### 2.3 Luật schema

| # | Luật | Lý do |
|---|---|---|
| 1 | `name` bắt buộc, kebab-case, khớp tên thư mục | Tên node graph; trùng lặp là lỗi cấu hình, không phải chuyện thẩm mỹ |
| 2 | `description` bắt buộc, **phải có hai vế**: "Dùng khi" và "KHÔNG dùng khi" | Đây là hàng rào tự phân định — vế thứ hai chính là thứ router cần để không hijack. Thiếu vế hai → **lint cảnh báo**, không chặn (xem §3 để biết vì sao cảnh báo chứ không chặn) |
| 3 | `tools.read` chỉ tham chiếu tên có trong `build_erp_query_tools()` | Tầng đó đã read-only qua `Gateway` allowlist |
| 4 | `tools.write[].name` chỉ tham chiếu tool MCP **đã tồn tại**; loader tự sinh wrapper cùng tên bọc `_confirm_write` | Markdown **không bao giờ** định nghĩa tool mới, không có `exec` |
| 5 | `tools.write[].confirm` là template chuỗi, chỉ được nội suy tên tham số của chính tool đó | Câu xác nhận là thứ người dùng đọc trước khi cho ghi |
| 6 | `ask_human` luôn được cấp, không cần khai | Mọi SOP đều cần; bắt khai chỉ tạo chỗ để quên |
| 7 | `entry` + `declares_tools` đi cùng nhau; loader đối chiếu danh sách tool `build_tools()` trả về với `declares_tools`, lệch là từ chối nạp | Chống `logic.py` lặng lẽ mở thêm tool mà frontmatter không khai |
| 8 | `max_steps` tuỳ chọn, mặc định 15, trần cứng 25 | `AGENTIC_RECURSION_LIMIT` hiện tại. Áp bằng `with_config({"recursion_limit": ...})` **tại wiring**, không trong `make_node` — bài học spike v10b: thiếu nó thì subgraph chạy **không giới hạn**, vì mặc định 25 của LangGraph không truyền vào subgraph-as-node |
| 9 | Một skill có `tools.write` **hoặc** `entry`, không cả hai | Hai đường sinh tool trong một skill là chỗ để lọt gate |

---

## §3. Loader và biên giới thẩm quyền

### 3.1 Luồng nạp

Chạy **một lần lúc `build_graph()`** — đúng chỗ `AGENTIC_SKILLS` được đọc ở bản
gốc:

```
quét backend/skills/*/SKILL.md
  → parse frontmatter + prose
  → validate (§3.2) — fail-LOUD, app không lên nếu sai
  → sinh tool: ask_human + read tools + wrapper ghi đã gate (hoặc logic.build_tools)
  → node = create_agent(llms["planner"], tools, system_prompt=prose)
              .with_config({"recursion_limit": max_steps})
  → g.add_node(name, node); g.add_edge(name, "agentic_context_sync")
  → registry kết xuất khối mô tả worker (§8) cho intent_router
```

Wrapper ghi sinh tự động — đúng boilerplate `delivery`/`warehouse_receiving`
đang viết tay:

```python
@tool(spec.name)
async def _gated(**kwargs) -> str:
    if not _confirm_write(spec.confirm.format(**kwargs)):
        return REFUSED_MSG
    return await mcp_tool.ainvoke(kwargs)
```

Schema tham số của wrapper **chép từ chính tool MCP**, không do markdown khai —
markdown không có quyền mô tả tham số của một tool ghi.

### 3.2 Validate — chặn cứng lúc khởi động

Triết lý giống `assert_embedding_marker()`: thà không lên còn hơn lên sai.

| Vi phạm | Xử lý |
|---|---|
| `tools.write[].name` không có trong registry MCP | **từ chối nạp, app không lên** |
| `tools.read[]` không có trong `build_erp_query_tools()` | **từ chối** |
| `name` trùng skill khác, hoặc trùng tên 5 intent tier-1 | **từ chối** |
| `entry` khai mà file không tồn tại / không có `build_tools` | **từ chối** |
| `logic.build_tools()` trả tool ngoài `declares_tools` | **từ chối** |
| Có cả `tools.write` lẫn `entry` | **từ chối** |
| Thiếu `name` hoặc `description` | **từ chối** |
| `max_steps` > 25 | **từ chối** |
| `description` thiếu vế "KHÔNG dùng khi" | **cảnh báo lúc khởi động** (log), vẫn nạp |

Vì sao vế "KHÔNG dùng khi" chỉ cảnh báo: nó là **chất lượng prompt**, không
phải **thẩm quyền**. Một description tồi làm SOP bị chọn nhầm — và lớp phủ
quyết tất định (§4) cùng confirm-gate vẫn chặn hậu quả. Chặn cứng ở đây sẽ
biến một lỗi soạn thảo thành sự cố ngừng dịch vụ, sai tỉ lệ. Ngược lại, mọi
luật ở trên nó đều dính tới thẩm quyền hoặc tính đúng đắn cấu trúc → chặn cứng.

### 3.3 Biên giới thẩm quyền — toàn bộ mô hình trong một câu

> Sửa `SKILL.md` chỉ có thể thay đổi **thứ tự và điều kiện** gọi những tool đã
> được gate sẵn — không bao giờ thêm được thẩm quyền mới.

Hệ quả cụ thể của việc soạn SOP sai:

| Sai kiểu gì | Hậu quả xấu nhất |
|---|---|
| Quy trình dở, thiếu bước | Trợ lý làm việc kém — đúng địa hạt của người viết SOP |
| Gọi tool ghi sai lúc | User bị hỏi xác nhận vô lý → bấm "không". Không có gì được ghi |
| Cố khai tool ngoài quyền | App không lên. Phát hiện lúc khởi động, không phải lúc chạy |
| Prose bảo model "bỏ qua xác nhận" | Vô hiệu — gate nằm trong wrapper Python, không nằm trong prose |

Tiền và tồn kho không đi qua tay markdown. Ba tầng giữ nguyên từ bản gốc:
wrapper gate (tất định) → `write_gate` phía Odoo fail-closed → `ERP_SKILLS_ENABLED`
kill-switch cấp định tuyến.

---

## §4. Định tuyến hybrid

### 4.1 Cơ chế

Router trả **hai trường** trong **một lượt gọi duy nhất** — không tốn thêm call,
điều quan trọng khi OpenRouter chỉ ~50 req/ngày:

```
intent: erp_read | erp_write | rag | mixed | unknown
sop:    <tên skill, hoặc rỗng>   # chỉ khi câu là yêu cầu THỰC THI khớp mô tả
```

Khối mô tả worker (§8) nối vào cuối `INTENT_ROUTER_PROMPT`.

Quyết định cuối **tất định**, giữ nguyên điều kiện đã kiểm chứng của bản gốc,
chỉ đổi nguồn đề cử từ "khớp trigger" sang "router đề cử":

```python
def _route_by_intent(state) -> str:
    intent = state.get("intent") or "unknown"
    sop = state.get("sop")
    if skill_gate.skills_enabled() and sop:
        folded = _fold(last_human_message(state))
        if intent == "erp_write" or not _looks_like_question(folded):
            return sop            # SOP nhận trọn lượt
    return intent                 # phủ quyết: rớt sop, dùng intent
```

`_looks_like_question` và `_QUESTION_MARKERS` **đã nằm sẵn** trong
`backend/src/agents/graph.py:20-28` (giữ lại có chủ đích ở SP-1B Task 10 làm
móc cho SP-2). `skill_gate.py` đã port ở Task 9. Không phải viết mới.

Bốn chỗ phải đổi để router trả được hai trường:

| File | Đổi gì |
|---|---|
| `backend/src/agents/state.py` | `ERPAgentState` thêm trường `sop: str \| None` |
| `backend/src/agents/prompts.py` | `INTENT_ROUTER_PROMPT` đổi hợp đồng đầu ra từ *một từ* sang hai dòng `intent:` / `sop:`, và nối khối mô tả worker (§8) vào cuối |
| `backend/src/agents/nodes.py` | `make_intent_router_node` parse hai trường. **Fail an toàn:** không parse được `sop` → coi như rỗng (rơi về đúng hành vi hôm nay), không phải ném lỗi |
| `backend/src/agents/graph.py` | `_route_by_intent` như trên; `intent_targets` thêm node SOP từ registry |

Hợp đồng đầu ra của router là **thay đổi hành vi**, nên nó nằm trong phạm vi đo
của bộ `intent` cũ (§5.3 điều kiện 2): bộ đó không được thụt sau khi đổi.

### 4.2 Bốn tầng phòng thủ, đúng thứ tự

| Tầng | Cơ chế | Tính chất |
|---|---|---|
| 1 | `description` có vế "KHÔNG dùng khi" | xác suất |
| 2 | `_looks_like_question` phủ quyết | **tất định** — che đúng chiều lỗi 2026-07-16 |
| 3 | Câu bắc cầu trong prose SOP (§6.4) | xác suất, nhưng rẻ và đã chạy thật |
| 4 | `_confirm_write` tại tool boundary | **tất định**, fail-closed |

Tầng 2 là lý do spec này không chọn "thuần description": bằng chứng A cho thấy
router LLM thua đúng bài này 3/3 lần, và lớp tất định là thứ đã sửa được nó.
Đổi model to hơn *có thể* đủ — nhưng "có thể" không phải cơ sở để tháo một lớp
phòng thủ đã chứng minh giá trị, khi giữ nó tốn 10 dòng.

### 4.3 `ERP_SKILLS_ENABLED`

Giữ nguyên semantics: `"0"` là giá trị tắt **duy nhất** được nhận, mọi giá trị
khác (kể cả chưa đặt) là bật. Tắt → mọi đề cử `sop` bị bỏ qua, hệ thống hành xử
đúng như hôm nay. Đây là kill-switch **cấp định tuyến**; an toàn ghi vẫn do
`write_gate` bảo đảm độc lập.

---

## §5. Eval

### 5.1 Hai case cũ: KHÔNG sửa, chỉ chú thích

Ranh giới mới ở §2 — *SOP chỉ nhận **ngôn ngữ quy trình**; lệnh trực tiếp đơn lẻ
đi tier-1* — làm cho kỳ vọng cũ **vẫn đúng**:

- `evals/cases.py:29` — `"giao hàng cho đơn S00040 luôn nhé"` → `erp_write` ✅
  (không nhắc quy trình)
- `evals/cases.py:147` — `"giao hàng cho đơn S00040"` → `deliver_order` ✅

Và đúng cả về vận hành: đi tier-1 rẻ hơn (một call planner thay vì cả ReAct
loop) và vẫn có confirm-gate riêng.

**Việc cần làm: chú thích ranh giới này ngay cạnh hai case**, để đời sau không
"sửa giúp". Ranh giới cũ "bán / không bán" (bằng chứng B) chết đi, thay bằng
ranh giới bảo vệ được: *có / không có ngôn ngữ quy trình*.

### 5.2 Bộ mới `SOP_SELECT_CASES`

Mỗi skill tối thiểu 4 hướng — **hai hướng âm cũng quan trọng ngang hai hướng
dương**, vì lỗi đã xảy ra thật là lỗi hijack:

| Hướng | Ví dụ (`giao-hang`) | Kỳ vọng |
|---|---|---|
| Thực thi, có ngôn ngữ quy trình | "làm quy trình giao hàng cho đơn S00012" | `sop:giao-hang` |
| **Hỏi VỀ** quy trình | "quy trình giao hàng gồm những bước nào?" | `rag`, sop bị phủ quyết |
| Lệnh trực tiếp, không nhắc quy trình | "giao hàng cho đơn S00040" | `erp_write` |
| **Hồi quy 2026-07-16** | "quy trình nhập kho cho đơn mua P00021" *(nguyên văn ca thua 3/3)* | `sop:nhap-kho` |

Ca hồi quy lấy **nguyên văn** ba câu đã thua trong live-verify, không diễn giải
lại — đó là toàn bộ giá trị của nó.

### 5.3 Điều kiện lên sóng

1. `SOP_SELECT_CASES` **xanh toàn bộ**.
2. Bộ `intent` cũ **không thụt** so với baseline.
3. Cả hai chạy qua eval gate của SP-1C.

Eval ở đây là **giấy phép**, không phải trang trí — nhất quán với ADR-009 QĐ M3.

---

## §6. Di trú 3 skill

### 6.1 Port nguyên, không sửa

- `agentic_gate.py` — `ask_human`, `_confirm_write`, `REFUSED_MSG`. Bé, đã kiểm
  chứng live.
- `agentic_context_sync.py` — bàn giao state tier-2 → tier-1 + scrub rò tên
  tool. Mọi node SOP nối cạnh → `agentic_context_sync` → `END`, y bản gốc.

Áp **quy tắc port test của SP-1B** không đổi: test đỏ vì hạ tầng → sửa nối dây;
đỏ vì **hành vi** → dừng, báo cáo, không sửa test cho xanh.

### 6.2 `giao-hang`, `nhap-kho` — chỉ `SKILL.md`

Wrapper do loader sinh. Bắt buộc có **test tương đương hành vi**: mock tool MCP,
so sánh luồng confirm của wrapper sinh tự động với wrapper viết tay cũ (cùng
câu hỏi xác nhận, cùng `REFUSED_MSG`, cùng payload `ainvoke`).

### 6.3 `bao-gia-chiet-khau` — `SKILL.md` + `logic.py`

~109 dòng chuyển nguyên. **Bắt buộc kèm comment tại chỗ** ghi bất biến tiền bạc
(xem Phụ lục A).

### 6.4 Câu bắc cầu

`NO_PO_BRIDGE_MSG` sống trong prose của `nhap-kho/SKILL.md`, trở thành **mẫu**
cho SOP viết sau. Cơ chế của nó cần được hiểu đúng: nó **không tự định tuyến
lại** — nó nói cho người dùng biết **câu cần gõ tiếp**, rồi định tuyến bình
thường lo phần còn lại.

Ràng buộc kế thừa từ bản gốc: **câu bắc cầu phải được kiểm là không tự kích
hoạt lại chính SOP đó** (bản gốc verify "điều chỉnh tồn kho ... về ..." không
khớp TRIGGERS). Với định tuyến mới, tương đương: câu gợi ý trong bridge không
được rơi trúng `description` của chính skill đang thoát ra. Đây là một case
trong `SOP_SELECT_CASES`.

---

## §7. Testing

| Nhóm | Nội dung |
|---|---|
| **Loader — từ chối** | Mỗi luật chặn cứng ở §3.2 có một test fail-loud riêng (tool lạ, trùng tên, `logic.py` lệch `declares_tools`, thiếu field, `max_steps` quá trần, có cả `write` lẫn `entry`) |
| **Loader — cảnh báo** | `description` thiếu vế "KHÔNG dùng khi" → có log cảnh báo **và vẫn nạp** |
| **Wrapper sinh tự động** | Gọi `_confirm_write` đúng câu đã nội suy; trả `REFUSED_MSG` khi False; `ainvoke` đúng payload khi True |
| **Định tuyến** | Bảng tổ hợp (có/không đề cử `sop`) × (câu hỏi / không) × (intent) — style `test_graph_build.py` |
| **Bất biến bảo mật** | Nối dài test bất biến toàn đồ thị của SP-1B: *mọi node SOP chỉ đến được từ `intent_router`*, và *mọi tool ghi trong node SOP đều là wrapper đã gate* |
| **Tương đương hành vi** | §6.2 — wrapper sinh tự động vs wrapper viết tay cũ |
| **Live e2e** | Một flow SOP thật qua MCP + Odoo, `@pytest.mark.live`, kiểu `test_dau_cuoi.py` |

Ba chế độ test giữ nguyên quy ước SP-1B: mặc định (không mạng, không Postgres),
`-m integration`, `-m live`.

---

## §8. Hợp đồng với SP-2b

Registry SOP **không nói chuyện trực tiếp** với `intent_router`. Nó kết xuất
một **khối mô tả worker** trung lập:

```
worker: <name>
mô tả:  <description>
```

- **SP-2a:** `intent_router` tiêu thụ khối đó (nối vào prompt).
- **SP-2b:** supervisor tiêu thụ **cùng khối đó**; `intent_router` bị hấp thụ.

Khối phải đủ tổng quát để **5 intent tier-1 sau này khai báo được cùng dạng** —
nếu không, SP-2b sẽ phải gộp hai danh sách worker (5 intent hard-code trong
`graph.py` + N SOP từ file) mà spec này vừa tạo ra.

**Vì sao SOP hợp với router hôm nay mà vẫn hợp với supervisor mai:** phân biệt
then chốt là *điều khiển có quay về hay không*. SOP **bàn giao** — nó tự chạy
ReAct loop, tự hỏi qua `ask_human`, tự trả lời cuối, hết lượt. Không ai cần
điều phối nó. Ngược lại, thay `fusion` bằng fan-out `erp_read ‖ rag` là **điều
phối** — kết quả bắt buộc quay về để tổng hợp một lần. **Đó mới là lý do cơ học
khiến topology nằm ở SP-2b**, không phải lý do thủ tục.

Khi SP-2b tới: chỉ đổi *ai gọi*. `SKILL.md`, loader, manifest tool, bộ eval —
sống sót nguyên vẹn.

---

## §9. "SP-2a xong" nghĩa là

1. `backend/skills/` có 3 thư mục; `giao-hang` và `nhap-kho` chỉ có `SKILL.md`;
   `bao-gia-chiet-khau` có thêm `logic.py`.
2. Sửa một dòng prose trong `SKILL.md` + restart → hành vi trợ lý đổi theo,
   không đụng file `.py` nào.
3. Khai một tool không có quyền trong `SKILL.md` → **app không lên**, log chỉ
   đúng file và đúng dòng sai.
4. `SOP_SELECT_CASES` xanh toàn bộ, gồm cả ca hồi quy nguyên văn 2026-07-16;
   bộ `intent` cũ không thụt.
5. Test bất biến bảo mật mở rộng xanh: không node SOP nào tới được từ chỗ khác
   `intent_router`; không tool ghi trần nào lọt vào node SOP.
6. Toàn bộ test xanh ở cả ba chế độ.
7. Một flow SOP thật chạy đầu-cuối qua Odoo thật.

**Chưa làm được sau SP-2a:** chưa có UI soạn SOP, chưa hot-reload, chưa có
orchestrator, `fusion` vẫn còn. Đó là việc của SP-2b và sau đó.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

Theo luật đã áp dụng từ SP-1 (quyết định nào đời sau không được phép bàn lại
thì phải có comment trong **file được version-control**, tại đúng điểm mã nó
ảnh hưởng — không chỉ trong ledger hay spec):

| Quyết định | File |
|---|---|
| Bất biến tiền bạc: model không bao giờ tính hay truyền số tiền | `backend/skills/bao-gia-chiet-khau/logic.py` |
| `_looks_like_question` phủ quyết là **tất định có chủ đích**, vì router LLM đã thua bài này 3/3 lần (live-verify 2026-07-16) | `backend/src/agents/graph.py`, tại `_route_by_intent` |
| Markdown không bao giờ định nghĩa tool mới; wrapper ghi luôn do loader sinh và luôn bọc `_confirm_write` | file loader, tại chỗ sinh wrapper |
| `recursion_limit` phải áp **tại wiring**, không trong `make_node` (spike v10b) | file loader, tại chỗ `.with_config(...)` |

## Phụ lục B — Rủi ro đã biết, chưa xử lý ở SP-2a

| Rủi ro | Vì sao chấp nhận |
|---|---|
| Vai `router` dùng model rẻ nhất chuỗi, nay phải phân biệt thêm "thực thi SOP" vs "hỏi về SOP" | Đo được bằng `SOP_SELECT_CASES`. Nếu đỏ: nâng model vai router, hoặc siết vế "KHÔNG dùng khi" — cả hai đều rẻ hơn thêm một lượt gọi |
| Prompt injection qua prose `SKILL.md` do người viết SOP soạn | Người viết SOP là nội bộ, đã tin cậy ở mức ghi ERP. Prompt-guard rail (`llama-prompt-guard-2`) đã ghi sẵn là mục tiêu SP-2, catalog đã có model |
| Số SOP tăng → prompt router phình | Mỗi mô tả ~40-60 từ; 20 SOP ≈ 1000 từ. Khi chạm ngưỡng khó chịu thì đó chính là lúc supervisor của SP-2b có ích — không phải vấn đề của SP-2a |
| Sửa SOP phải restart | Đã nêu ở §0. Hot-reload cần cô lập lỗi + khoá đồng thời, không đáng đổi ở giai đoạn này |
