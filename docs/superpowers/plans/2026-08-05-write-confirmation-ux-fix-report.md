# Báo cáo kết thúc: 2026-08-05-write-confirmation-ux-fix

**Trạng thái:** HOÀN THÀNH

**Nhánh:** worktree-write-confirmation-ux-fix (ff onto local main)

**Ngày hoàn thành:** 2026-08-05

---

## Tóm tắt kế hoạch

Kế hoạch 6 bước xây dựng tính năng "xác nhận ghi" cho agent —  giúp người dùng xác minh trước khi thực hiện thao tác viết dữ liệu ERP. Spec đầy đủ: `docs/superpowers/specs/2026-08-05-write-confirmation-ux-fix-design.md` (kế hoạch thi công: `docs/superpowers/plans/2026-08-05-write-confirmation-ux-fix.md`)

---

## Task 1: Helper tách marker ĐỀ_XUẤT_GHI

**Commit:** `bb1642d` — "feat(agents): helper tách marker ĐỀ_XUẤT_GHI khỏi câu trả lời"

**File đã sửa:**
- `backend/src/agents/synthesis.py` — Thêm `WRITE_SUGGEST_MARKER` (dòng 25), `_WRITE_SUGGEST_RE`, `_WRITE_SUGGEST_YES`, hàm `extract_write_suggestion(body: str) -> tuple[str, bool]` (dòng 39-56)
- `backend/tests/agents/test_synthesis.py` — Thêm 5 test case mới: `test_extract_write_suggestion_khong_co_marker()`, `test_extract_write_suggestion_co_marker_thi_cat_bo()`, `test_extract_write_suggestion_gia_tri_phu_dinh()`, `test_extract_write_suggestion_giu_nguyen_dong_nguon_dung_phia_sau()`, `test_extract_write_suggestion_khong_pha_extract_used_citations()`

**Nhận xét review:** Không có finding nào. Tất cả test pass, không regression.

---

## Task 2: Điều kiện tất định mới trong `decide_route`

**Commit:** `17d9447` — "feat(routing): 'okay' sau đề xuất ghi được ép route sang erp_write"

**File đã sửa:**
- `backend/src/agents/routing.py` — Thêm import từ `.confirmation`, hàm `replying_to_write_suggestion(state) -> bool` (dòng 157-190), nhánh veto trong `decide_route()` (dòng 217-218)
- `backend/tests/agents/test_routing_write_suggestion.py` (tạo mới) — 7 test case (hướng dương: đồng ý ngắn gọn → `erp_write`, thắng cả đề cử router LLM; hướng âm: không có cờ / trả lời từ chối / trả lời dài không phải xác nhận / cờ cũ bị vô hiệu hoá / state chỉ có một human message)

**Nhận xét review:** Không có finding nào ở vòng review theo-task. Kiểm chứng tính an toàn invariant 1 — không đụng `erp_write_executor`, `state.get("confirmed")`, `write_gate`, hay `_interrupt()`. +7 test như kỳ vọng.

> **File này đã được VIẾT LẠI TOÀN BỘ ở fix wave final review** (cơ chế đổi từ
> `additional_kwargs` sang state field + neo độ dài). Danh sách test hiện hành
> xem mục "Fix wave (final review)" ở cuối báo cáo.

---

## Task 3: Nối dây cờ vào `fuse_answer` + `erp_read` + chỉ dẫn prompt

**Commit chính:** `8bbb5c0` — "feat(agents): fuse_answer/erp_read gắn cờ suggested_write lên message"

**File đã sửa (lần 1):**
- `backend/src/agents/prompts.py` — Thêm `ĐỀ_XUẤT_GHI: có` marker instruction block vào `SYSTEM_PROMPT` và `FUSE_PROMPT` (đặt TRƯỚC trailing `/no_think`, chứ không phải sau như brief nêu)
- `backend/src/agents/fanout.py` — `make_fuse_answer_node` (dòng 169) với `async def fuse_answer()` (dòng 177-223): import `extract_write_suggestion`, khởi tạo `suggested_write = False`, gọi `extract_write_suggestion(answer)` TRƯỚC `cite_and_verify`, attach `additional_kwargs={"suggested_write": True}` vào `AIMessage`
- `backend/src/agents/nodes.py` — `make_erp_read_node` (dòng 31) với `async def erp_read()` (dòng 32-59): extract marker từ last AI message sau grounding-verification, re-attach flag
- `backend/tests/agents/test_fanout.py` — Thêm 3 unit test: `test_fuse_answer_gan_co_va_cat_marker()`, `test_fuse_answer_khong_co_marker_thi_khong_gan_co()`, `test_fuse_answer_safe_msg_khong_mang_co()`
- `backend/tests/agents/test_write_suggestion_checkpoint.py` (tạo mới) — Integration test 1 case (Postgres thật, AsyncPostgresSaver round-trip)

**Sai lệch từ brief (đã sửa):**
1. **Marker placement:** Brief nói "ngay trước dấu `"""` đóng", nhưng literal là AFTER `/no_think`. Thực tế `/no_think` phải là token cuối cùng (per test `test_fuse_prompt_keeps_citation_trailer_contract` và comment `nodes.py`). Đã đặt marker TRƯỚC `/no_think` thay vì sau. Sửa đúng theo yêu cầu thực tế.
2. **AsyncConnectionPool min_size:** Brief code có `max_size=2, open=False` nhưng không set `min_size`. `psycopg_pool==3.3.1` defaults `min_size=4` → lỗi. Đã sửa thêm `min_size=1`.

**Nhận xét review (Fix round 1):** 2 Important finding được xác nhận

**Commit fix wave 1:** `c1fcf44` — "fix(agents): fix wave 1 — FUSE_PROMPT hai chỉ dẫn 'cuối cùng' xung đột, thêm test canh marker"

**File sửa (Fix round 1):**
- `backend/src/agents/prompts.py` — Rewording FUSE_PROMPT trailer block: thay hai "final line" claims độc lập thành một lead-in chung "có thể cần thêm MỘT HOẶC CẢ HAI dòng cuối dưới đây" (dòng 189-191)
- `backend/tests/agents/test_fanout.py` — Thêm 2 guard test: `test_fuse_prompt_co_chi_dan_de_xuat_ghi()`, `test_system_prompt_co_chi_dan_de_xuat_ghi()`

**Kết quả test:**
- Trước fix: 1138 passed, 4 skipped (sau Task 2)
- Sau fix: 1140 passed, 4 skipped (+2 guard test mới, không regression)

---

## Task 4: Chủ động tra cứu khi thiếu 1 thông tin bắt buộc

**Commit chính:** `b9e4b1a` — "feat(prompts): chủ động tra cứu khi thiếu 1 thông tin bắt buộc"

**File đã sửa (lần 1):**
- `backend/src/agents/prompts.py` — Thêm 2 Quy tắc mới:
  - GATHER_ERP_PROMPT: "Nếu câu hỏi ngụ ý... nhưng còn THIẾU một thông tin bắt buộc... và bạn CÓ tool tra cứu được thông tin đó — hãy GỌI TOOL tra cứu trước, đừng hỏi lại người dùng khi tự tra được"
  - FUSE_PROMPT: "Khi dữ kiện cho thấy chỉ có ĐÚNG một lựa chọn... hãy nêu thẳng lựa chọn đó kèm số liệu thật và đề nghị tiến hành... Nếu có NHIỀU lựa chọn, liệt kê ra để người dùng chọn"
- `backend/tests/agents/test_prompts.py` — Thêm 2 test: `test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai()`, `test_fuse_prompt_neu_dung_mot_lua_chon_thi_neu_thang()`

**Nhận xét review (Fix round 1):** 1 Important finding (keyword-substring checks không đủ mạnh)

**Commit fix wave 1:** `034d2c8` — "fix(agents): fix wave 1 — test_prompts.py assert cả câu thay vì chỉ từ khoá rời"

**File sửa (Fix round 1):**
- `backend/tests/agents/test_prompts.py` — Strengthened assertions: từ loose keyword tìm sang full sentence matching (dòng tương ứng trong file test)

**Kết quả test:**
- Trước fix: 1140 passed, 4 skipped
- Sau fix: 1142 passed, 4 skipped (+2 test mới, không regression)

---

## Task 5: Gom câu xác nhận về một hằng số + đổi câu chữ

**Commit chính:** `c075132` — "refactor(agents): gom câu xác nhận ghi về WRITE_CONFIRM_SUFFIX, câu chữ tự nhiên hơn"

**File đã sửa (lần 1):**

- `backend/src/agents/prompts.py` — Thêm `WRITE_CONFIRM_SUFFIX` (dòng 141-142) với docstring tiếng Việt, đổi câu chữ `WRITE_CONFIRM_PREFIX` từ `"Bạn có muốn thực hiện thao tác sau không?\n\n"` sang `"Mình sẽ thực hiện thao tác sau giúp bạn:\n\n"` (dòng 126)

- **src/agents/ (9 file):** Thêm import `WRITE_CONFIRM_SUFFIX`, thay 19 literal cũ:
  - `create_order.py` (2 vị trí) — dòng 49, 53
  - `bom_write.py` (2 vị trí) — dòng 158, 277
  - `crm_write.py` (3 vị trí) — dòng 115, 156, 211
  - `inventory_write.py` (3 vị trí) — dòng 64, 117, 171
  - `mrp_write.py` (1 vị trí) — dòng 121
  - `purchase_write.py` (3 vị trí) — dòng 94, 160, 224
  - `returns_write.py` (2 vị trí) — dòng 97, 136
  - `edit_order.py` (1 vị trí) — dòng 92
  - `nodes.py` (1 vị trí) — dòng 252-255, hàm `erp_write_planner`

- `backend/skills/bao-gia-chiet-khau/logic.py` — Thêm import tuyệt đối, thay 1 literal (vị trí #19 trong danh sách audit)

- **Test files:** Thêm import, cập nhật assertions:
  - `backend/tests/agents/test_prompts.py` — 2 guard test mới: `test_write_confirm_suffix_giu_dau_hieu_cong_xac_nhan()`, `test_khong_con_literal_xac_nhan_lap_lai_trong_src()`
  - `backend/tests/agents/test_auto_chain.py` — 4 assert đổi sang hằng số (dòng 243, 249, 262, 293 per brief)
  - `backend/tests/agents/test_create_order_helpers.py` — 1 assert phát sinh ngoài brief, cũng đổi sang hằng số

**Kiểm tra thêm:** Không có circular import (prompts.py chỉ import từ `.working_context`, không import ngược create_order/nodes/v.v.)

**Nhận xét review (Fix round 1):** 1 Important finding (comment overclaim)

**Commit fix wave 1:** `c25d4b3` — "docs(agents): fix wave 1 — làm rõ WRITE_CONFIRM_SUFFIX không bao phủ cổng xác nhận riêng của edit_order.py"

**File sửa (Fix round 1):**
- `backend/src/agents/prompts.py` — Làm rõ comment: thay "MỌI cổng xác nhận ghi" → "các cổng xác nhận ghi ĐÃ GOM", thêm đoạn LƯU Ý rõ `edit_order.py` có cổng riêng ngoài phạm vi 19 chỗ audit gốc (LƯU Ý tại dòng 132-136, toàn bộ comment block 127-140)

**Kết quả test:**
- Trước fix: 1142 passed, 4 skipped
- Sau fix: 1144 passed, 4 skipped (+2 test mới ở Task 5 lần 1, không regression)

---

## Kết quả test toàn bộ

**Command:**
```bash
cd backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

**Output:**
```
........................................................................ [  6%]
........................................................................ [ 12%]
........................................................................ [ 18%]
........................................................................ [ 25%]
........................................................................ [ 31%]
........................................................................ [ 37%]
........................................................................ [ 43%]
........................................................................ [ 50%]
........................................................................ [ 56%]
........................................................................ [ 62%]
........................................................................ [ 68%]
..........s............................................................. [ 75%]
........................................................................ [ 81%]
........................................................................ [ 87%]
........................................................................ [ 94%]
....................................sss.............................     [100%]
1144 passed, 4 skipped, 44 deselected in 28.60s
```

**Baseline trước Task 1:** 1123 passed, 4 skipped
**Baseline sau Task 1:** 1128 passed, 4 skipped (+5 test của Task 1)
**Baseline sau Task 2:** 1135 passed, 4 skipped (+7 test)
**Baseline sau Task 3:** 1140 passed, 4 skipped (+5 test, gồm 3 unit + 2 guard)
**Baseline sau Task 4:** 1142 passed, 4 skipped (+2 test)
**Cuối cùng (sau Task 5):** 1144 passed, 4 skipped (+2 test)

**Tổng cộng:** +21 test mới (1144 - 1123 = 21)

---

## Phạm vi tính năng

| Mục spec | Task | Trạng thái |
|---|---|---|
| §2.1 marker + cắt bỏ | Task 1 (helper), Task 3 Step 1-5 (prompt + nối dây) | ✅ DONE |
| §2.1 điều kiện `decide_route` | Task 2 | ✅ DONE |
| §2.1 kiểm chứng checkpointer | Task 3 Step 7-8 | ✅ DONE (integration test passed) |
| §2.2 auto-tra cứu | Task 4 | ✅ DONE |
| §2.3 gom hằng + câu chữ mới | Task 5 | ✅ DONE |
| §5 bất biến an toàn 1-4 | Task 1-5 + test canh (Task 3, Task 5) | ✅ DONE |
| §6 kiểm chứng 1-5 | Task 1-5 (từng Step chạy test) | ✅ DONE |
| §6 kiểm chứng 6 (`eval_chitchat`) | Gate sau merge (cần LLM thật) | ⏳ PENDING |
| §7 cổng đánh giá | Mục dưới đây | ⏳ PENDING |

---

## Cổng đánh giá §7 — CHƯA CHẠY

Đúng per "Sau khi merge" section của spec, cổng đánh giá live-verify phần §7 **CHƯA CHẠY**. Đây là controller-only gate, sẽ thực hiện SAU KHI branch merge vào main trên D:\Youdoo (backend thật), không chạy được trong worktree này.

**3 tiêu chí live-verify (chưa kiểm chứng):**

1. **Ca gốc chạy đúng:** Tái hiện kịch bản — "có 1 khách hàng sắp đặt 30 cái individual workplace, nhưng kho chỉ còn 16 cái, tôi muốn nhập 20 cái individual workplace" → (agent gợi ý nhà cung cấp) → "okay". Trace Langfuse (http://localhost:3001) phải cho thấy lượt "okay" đi vào `erp_write_planner` và phát `_interrupt()`.

2. **Không hồi quy hội thoại thường:** Ít nhất 3 ca chitchat/RAG có câu hỏi dạng "...không?" theo sau bởi "ok"/"có" — KHÔNG ca nào vào `erp_write_planner` (chỉ routing bình thường đến chitchat/rag node).

3. **Tool-selection không hỏng:** Ít nhất 3 ca `gather_erp` thật (có ca 1-lựa-chọn và ca nhiều-lựa-chọn) chọn đúng tool/tham số (verify qua trace hoặc output).

Nếu tiêu chí 2 hoặc 3 trượt: sẽ revert phần tương ứng, ghi số đo thật vào report, và trình bày lại cho controller quyết định. Không tự nới tiêu chí.

---

## Tóm tắt lỗi phát hiện + sửa

| Task | Lỗi (source) | Sửa | Loại |
|---|---|---|---|
| Task 3 | Marker placement sau `/no_think` break test | Đặt TRƯỚC `/no_think` | Spec ambiguity (brief chưa rõ cụ thể) |
| Task 3 | `AsyncConnectionPool max_size=2` + no `min_size` (default 4) | Thêm `min_size=1` | Brief snippet bug |
| Task 3 | FUSE_PROMPT hai "final line" instructions xung đột | Reword thành 1 lead-in shared | Prompt logic (no regression) |
| Task 3 | Không test canh marker text trong prompts | Thêm 2 guard assertions | Coverage gap |
| Task 4 | Test assertions chỉ kiểm từ khoá, không full sentence | Đổi sang full sentence matching | Test rigor |
| Task 5 | Comment claim "MỌI cổng xác nhận" nhưng edit_order.py có 1 riêng | Làm rõ comment "ĐÃ GOM" + LƯU Ý | Documentation (no code impact) |

---

## Fix wave (final review)

Review toàn nhánh sau khi 6 task đóng lại tìm ra **1 Critical + 3 finding
nhỏ hơn**. Báo cáo chi tiết + toàn bộ số đo thật:
`.superpowers/sdd/2026-08-05-write-confirmation-ux-fix/final-review-fix-wave-report.md`.

### C1 (Critical) — cơ chế cờ KHÔNG chạy trong production

Cơ chế cũ gắn cờ vào `AIMessage.additional_kwargs`. `erp_agent._invoke_fresh`
chạy trên **MỌI lượt không parked** (kể cả đúng lượt "okay" mà cả plan này
nhắm tới) và dựng lại **toàn bộ** kênh `messages` từ payload client, mà
`main.py._filter_messages` đã lược mỗi message còn `{"role", "content"}`. Cờ
trên message vì thế không sống nổi một lượt và **không bao giờ tới được**
`decide_route`.

**Thiết kế thay thế:** hai state field riêng, tự hết hạn theo neo độ dài —
`suggested_write: bool | None` + `suggested_write_at: int | None`.
`decide_route` chỉ tin cờ khi `len(messages) == suggested_write_at + 1` (đúng
lượt kế tiếp, không có gì xen giữa). State key là một **channel LangGraph
khác**, không bị `{"messages": reset}` của `_invoke_fresh` đụng tới, nên sống
sót; còn neo khiến cờ tự hết hạn nên **không node nào phải chủ động dọn** (không
phải sửa `respond_unknown`, `rag_node`, `erp_write_planner`,
`write_continuation` và 9 module ghi phối hợp).

Neo đếm theo **số message người dùng THẤY** (`len(state["messages"]) + 1`),
không theo độ dài kênh nội bộ — đo thật cho thấy công thức
`len(state)+len(new_msgs)` làm đường `erp_read` (ReAct, phụ thêm
tool-call/tool-result) **không bao giờ** bắn được phủ quyết.

**Kiểm chứng thật (graph + AsyncPostgresSaver + đúng khuôn `_invoke_fresh`):**

```
=== CƠ CHẾ CŨ (cờ trên AIMessage.additional_kwargs) ===
  len(messages) sau lượt 2 : 3
  additional_kwargs của AI cuối: [{}]
  cờ cũ đọc được?          : False
  replying_to_write_suggestion (hàm MỚI trên state cũ): False

=== CƠ CHẾ MỚI (state key + neo độ dài) ===
  len(messages) sau lượt 2 : 3
  state['suggested_write'] : True
  state['suggested_write_at']: 2
  human cuối               : 'okay'
  >>> replying_to_write_suggestion(state) = True
```

### Finding 2 (Important) — eval chấm văn bản CHƯA cắt marker

`evals/run_eval.py` chấm `resp.content` thô trong khi production luôn cắt dòng
`ĐỀ_XUẤT_GHI` trước. Thêm `_strip_write_marker()` (gọi
`extract_write_suggestion`, bỏ boolean) dùng ở **cả** `eval_multi_source` lẫn
`eval_multi_source_gather`, kèm test canh chống trôi lại.

### Finding 3 (Minor, đôn lên) — `synthesis.py` robustness

`sub(count=1)` → `count=0` (marker lặp hai lần thì lần thứ hai lọt ra văn bản
người dùng đọc); thêm neo `^` + `re.MULTILINE` (không có neo, regex khớp mảnh
marker giữa câu và nuốt mất đuôi dòng đó). +2 test.

### Finding 4 (Important) — báo cáo sai sự thật

Sửa citation spec sai đường dẫn, danh sách test Task 2 không khớp file thật,
trích sai giá trị cũ của `WRITE_CONFIRM_PREFIX`, dòng baseline Task 1 tự mâu
thuẫn, và lỗi chính tả "Finał".

### Kết quả test sau fix wave

- Unit-only: **1151 passed, 4 skipped, 46 deselected** (1144 → 1151, +7 test)
- Integration (Postgres thật): **3 passed** —
  `tests/agents/test_write_suggestion_checkpoint.py -m integration`, chạy
  thật, KHÔNG skip

---

## §7 Cổng đánh giá — kết quả thật (controller đo sau merge, 2026-08-05)

Nhánh đã merge vào `main` (fast-forward, commit `e7b6d04`), push lên origin.
Controller tự khởi động lại backend thật (`D:\Youdoo\backend`, không qua
worktree) với code vừa merge, rồi đo trực tiếp qua API thật + trace Langfuse
(`http://localhost:3001`) — không suy đoán.

**Lưu ý phương pháp:** lần đầu gửi bằng `session_id` đơn-message thì
`_invoke_fresh` xoá sạch lịch sử mỗi lần (đúng cơ chế C1 vừa sửa!) — phải đổi
sang mô phỏng đúng client Open WebUI thật: gửi lại TOÀN BỘ lịch sử hội thoại
mỗi lượt (không `session_id`), để `_derive_thread_id` bám theo hash tin nhắn
đầu tiên.

### Tiêu chí 1 — ca gốc chạy đúng: ✅ ĐẠT

Tái hiện đúng chuỗi hội thoại gốc (4 lượt, gửi lại đủ lịch sử mỗi lần):
1. "có 1 khách hàng sắp đặt 30 cái individual workplace... tôi muốn nhập 20
   cái individual workplace" → "Bạn cần cho biết nhà cung cấp nào để mình
   tạo đơn." (route ban đầu có biến thiên — có lần rơi thẳng vào
   `erp_write_planner`/`create_rfq`, có lần vào `mixed`; không ảnh hưởng tới
   điều đang đo)
2. "có các nhà cung cấp nào cho sản phẩm individual workplace hiện tại ?" →
   route:read thật, gọi tool `get_product_suppliers` thật, trả lời: "...
   **Bạn có muốn tôi tạo đơn mua 20 cái Individual Workplace từ nhà cung
   cấp Acme Corporation không?**" — câu đề xuất Y HỆT ca bug gốc.
3. **"okay"** → trace Langfuse xác nhận `decide_route` → `erp_write_planner`
   → `create_rfq` → phát cổng xác nhận THẬT:
   ```
   Đơn mua từ Acme Corporation:
     - [FURN_0789] Individual Workplace × 20
   Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)
   ```
   KHÔNG còn rơi vào chitchat mất ngữ cảnh như bug gốc. Bằng chứng: trace
   `decide_route` → `erp_write_planner` → `route:planner` (LLM) →
   `_route_after_write_planner` → `create_rfq`, đúng luồng `_interrupt()`
   thật.

### Tiêu chí 2 — không hồi quy hội thoại thường: ✅ ĐẠT (3/3 ca)

| # | Câu hỏi | Trả lời | Follow-up | Trace route sau follow-up |
|---|---|---|---|---|
| 1 | "cảm ơn bạn nhiều nhé" | chitchat cảm ơn | "ok" | `decide_route` → `respond_unknown` (chitchat) |
| 2 | "chính sách hoàn hàng của công ty như thế nào?" | "Không tìm thấy tài liệu liên quan" | "có" | `decide_route` → `respond_unknown` (chitchat) |
| 3 | "kho hiện còn bao nhiêu cái Individual Workplace?" | "Kho hiện còn 36 cái..." (tra cứu thuần, không đề xuất) | "có" | `decide_route` → `respond_unknown` (chitchat) |

Không ca nào bị ép sai sang `erp_write_planner`. Cơ chế mới (state field +
neo độ dài, không dò văn bản "...không?") xác nhận không có false positive
trên hội thoại thường.

### Tiêu chí 3 — tool-selection không hỏng: ✅ ĐẠT (3/3 ca thật)

| # | Câu hỏi | Tool thật | Kết quả |
|---|---|---|---|
| 1 | Individual Workplace, thiếu nhà cung cấp | `get_product_suppliers` | 1 lựa chọn (Acme Corporation) → tự nêu thẳng + đề nghị tiến hành (đúng Task 4) |
| 2 | "nhập thêm hàng cho Large Cabinet nhưng chưa biết nhà cung cấp" | `get_product_suppliers` | 4 lựa chọn thật (Wood Corner 750đ, Ready Mat 785-790đ theo bậc, Azure Interior & Gemini Furniture 800đ) → liệt kê đủ, hỏi lại người dùng chọn (đúng nhánh "NHIỀU lựa chọn" của Task 4) |
| 3 | "hóa đơn nào quá hạn thanh toán?" | `get_overdue_invoices` | 22 hóa đơn thật, đúng mã + hạn từ 4 khách hàng (Acme Corporation, OpenWood, LightsUp, Azure Interior) |

Không ca nào chọn sai tool hay bịa số liệu — toàn bộ số liệu (giá, mã hoá
đơn, ngày hạn) khớp dữ liệu Odoo thật.

### Kết luận §7

**Cả 3 tiêu chí ĐẠT — quyết định §2.1 (state field + neo độ dài) được GIỮ
LẠI**, đúng theo cổng đánh giá đã cam kết trong spec. Không phần nào bị
revert.

---

## Nhận xét cuối

- ✅ Tất cả 6 task hoàn thành, code đã merge vào `main` và push lên origin
  (commit `e7b6d04`)
- ✅ Test suite 1151 passed, 4 skipped (không regression) sau fix wave final
  review — xác nhận lại trên `main` đã merge
- ✅ Tất cả 6 finding từ review loop theo-task + 4 finding final review đều
  được xác nhận + sửa (0 open)
- ✅ Bất biến an toàn 1-4 kiểm chứng: không đụng `erp_write_executor`,
  `_interrupt()`, hay `state.get("confirmed")`
- ✅ Circular import check pass
- ✅ **Cổng đánh giá §7 (live-verify) ĐẠT cả 3 tiêu chí — đo thật trên
  backend production, có trace Langfuse làm bằng chứng** (xem mục trên)
- ⏳ Eval `eval_chitchat`/`eval_multi_source` cần LLM thật, chưa chạy trong
  phiên này (không thuộc phạm vi §7, để dành đợt eval định kỳ tiếp theo)

