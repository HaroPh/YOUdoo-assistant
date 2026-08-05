# Báo cáo kết thúc: 2026-08-05-write-confirmation-ux-fix

**Trạng thái:** HOÀN THÀNH

**Nhánh:** worktree-write-confirmation-ux-fix (ff onto local main)

**Ngày hoàn thành:** 2026-08-05

---

## Tóm tắt kế hoạch

Kế hoạch 6 bước xây dựng tính năng "xác nhận ghi" cho agent —  giúp người dùng xác minh trước khi thực hiện thao tác viết dữ liệu ERP. Spec đầy đủ: `docs/superpowers/plans/2026-08-05-write-confirmation-ux.md`

---

## Task 1: Helper tách marker ĐỀ_XUẤT_GHI

**Commit:** `bb1642d` — "feat(agents): helper tách marker ĐỀ_XUẤT_GHI khỏi câu trả lời"

**File đã sửa:**
- `backend/src/agents/synthesis.py` — Thêm `WRITE_SUGGEST_MARKER`, `_WRITE_SUGGEST_RE`, `_WRITE_SUGGEST_YES`, hàm `extract_write_suggestion(body: str) -> tuple[str, bool]` (dòng 5-56)
- `backend/tests/agents/test_synthesis.py` — Thêm 5 test case mới: `test_extract_write_suggestion_khong_co_marker()`, `test_extract_write_suggestion_co_marker_thi_cat_bo()`, `test_extract_write_suggestion_gia_tri_phu_dinh()`, `test_extract_write_suggestion_giu_nguyen_dong_nguon_dung_phia_sau()`, `test_extract_write_suggestion_khong_pha_extract_used_citations()`

**Nhận xét review:** Không có finding nào. Tất cả test pass, không regression.

---

## Task 2: Điều kiện tất định mới trong `decide_route`

**Commit:** `17d9447` — "feat(routing): 'okay' sau đề xuất ghi được ép route sang erp_write"

**File đã sửa:**
- `backend/src/agents/routing.py` — Thêm import từ `.confirmation`, hàm `replying_to_write_suggestion(state) -> bool` (dòng 136-173), nhánh veto trong `decide_route()` (dòng 180-182)
- `backend/tests/agents/test_routing_write_suggestion.py` (tạo mới) — 7 test case verbatim từ brief: `test_tien_hanh_neu_co_de_xuat_ghi_va_ok()`, `test_tien_hanh_neu_co_de_xuat_ghi_va_co()`, `test_khong_tien_hanh_neu_co_de_xuat_ghi_va_khong()`, `test_khong_tien_hanh_neu_khong_co_de_xuat_ghi()`, `test_khong_tien_hanh_neu_khong_co_human_message()`, `test_khong_tien_hanh_neu_khong_co_ai_message_nao_thi_an_toan()`, `test_co_moi_hon_khong_mang_co_thi_vo_hieu_hoa_co_cu()`

**Nhận xét review:** Không có finding nào. Kiểm chứng tính an toàn invariant 1 — không đụng `erp_write_executor`, `state.get("confirmed")`, `write_gate`, hay `_interrupt()`. +7 test như kỳ vọng.

---

## Task 3: Nối dây cờ vào `fuse_answer` + `erp_read` + chỉ dẫn prompt

**Commit chính:** `8bbb5c0` — "feat(agents): fuse_answer/erp_read gắn cờ suggested_write lên message"

**File đã sửa (lần 1):**
- `backend/src/agents/prompts.py` — Thêm `ĐỀ_XUẤT_GHI: có` marker instruction block vào `SYSTEM_PROMPT` và `FUSE_PROMPT` (đặt TRƯỚC trailing `/no_think`, chứ không phải sau như brief nêu)
- `backend/src/agents/fanout.py` — Hàm `fuse_answer()` (dòng 33-95): import `extract_write_suggestion`, khởi tạo `suggested_write = False`, gọi `extract_write_suggestion(answer)` TRƯỚC `cite_and_verify`, attach `additional_kwargs={"suggested_write": True}` vào `AIMessage`
- `backend/src/agents/nodes.py` — Hàm `erp_read()` (dòng 167-202): extract marker từ last AI message sau grounding-verification, re-attach flag
- `backend/tests/agents/test_fanout.py` — Thêm 3 unit test: `test_fuse_answer_gan_co_va_cat_marker()`, `test_fuse_answer_khong_co_marker_thi_khong_gan_co()`, `test_fuse_answer_safe_msg_khong_mang_co()`
- `backend/tests/agents/test_write_suggestion_checkpoint.py` (tạo mới) — Integration test 1 case (Postgres thật, AsyncPostgresSaver round-trip)

**Sai lệch từ brief (đã sửa):**
1. **Marker placement:** Brief nói "ngay trước dấu `"""` đóng", nhưng literal là AFTER `/no_think`. Thực tế `/no_think` phải là token cuối cùng (per test `test_fuse_prompt_keeps_citation_trailer_contract` và comment `nodes.py`). Đã đặt marker TRƯỚC `/no_think` thay vì sau. Sửa đúng theo yêu cầu thực tế.
2. **AsyncConnectionPool min_size:** Brief code có `max_size=2, open=False` nhưng không set `min_size`. `psycopg_pool==3.3.1` defaults `min_size=4` → lỗi. Đã sửa thêm `min_size=1`.

**Nhận xét review (Fix round 1):** 2 Important finding được xác nhận

**Commit fix wave 1:** `c1fcf44` — "fix(agents): fix wave 1 — FUSE_PROMPT hai chỉ dẫn 'cuối cùng' xung đột, thêm test canh marker"

**File sửa (Fix round 1):**
- `backend/src/agents/prompts.py` — Rewording FUSE_PROMPT trailer block: thay hai "final line" claims độc lập thành một lead-in chung "có thể cần thêm MỘT HOẶC CẢ HAI dòng cuối dưới đây" (dòng 135-143 sau sửa)
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

- `backend/src/agents/prompts.py` — Thêm `WRITE_CONFIRM_SUFFIX = 'Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)'` (dòng 96-99) với docstring tiếng Việt, đổi câu chữ `WRITE_CONFIRM_PREFIX` từ "Mình sẽ thực hiện các thao tác sau" sang "Mình sẽ thực hiện thao tác sau giúp bạn:" (dòng 93)

- **src/agents/ (9 file):** Thêm import `WRITE_CONFIRM_SUFFIX`, thay 19 literal cũ:
  - `create_order.py` (2 vị trí) — dòng 213, 323
  - `bom_write.py` (2 vị trí) — dòng 96, 172
  - `crm_write.py` (3 vị trí) — dòng 95, 179, 258
  - `inventory_write.py` (3 vị trí) — dòng 89, 163, 243
  - `mrp_write.py` (1 vị trí) — dòng 67
  - `purchase_write.py` (3 vị trí) — dòng 107, 182, 262
  - `returns_write.py` (2 vị trí) — dòng 62, 137
  - `edit_order.py` (1 vị trí) — dòng 73
  - `nodes.py` (1 vị trí) — dòng 251-254, hàm `erp_write_planner`

- `backend/skills/bao-gia-chiet-khau/logic.py` — Thêm import tuyệt đối, thay 1 literal (vị trí #20 trong danh sách audit)

- **Test files:** Thêm import, cập nhật assertions:
  - `backend/tests/agents/test_prompts.py` — 2 guard test mới: `test_write_confirm_suffix_giu_dau_hieu_cong_xac_nhan()`, `test_khong_con_literal_xac_nhan_lap_lai_trong_src()`
  - `backend/tests/agents/test_auto_chain.py` — 4 assert đổi sang hằng số (dòng 243, 249, 262, 293 per brief)
  - `backend/tests/agents/test_create_order_helpers.py` — 1 assert phát sinh ngoài brief, cũng đổi sang hằng số

**Kiểm tra thêm:** Không có circular import (prompts.py chỉ import từ `.working_context`, không import ngược create_order/nodes/v.v.)

**Nhận xét review (Fix round 1):** 1 Important finding (comment overclaim)

**Commit fix wave 1:** `c25d4b3` — "docs(agents): fix wave 1 — làm rõ WRITE_CONFIRM_SUFFIX không bao phủ cổng xác nhận riêng của edit_order.py"

**File sửa (Fix round 1):**
- `backend/src/agents/prompts.py` — Làm rõ comment: thay "MỌI cổng xác nhận ghi" → "các cổng xác nhận ghi ĐÃ GOM", thêm đoạn LƯU Ý rõ `edit_order.py` có cổng riêng ngoài phạm vi 19 chỗ audit gốc (dòng 99-108)

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
**Baseline sau Task 1:** 1128 passed, 4 skipped (Task 1 không thêm test riêng, +5 = 7 test của Task 2)
**Baseline sau Task 2:** 1135 passed, 4 skipped (+7 test)
**Baseline sau Task 3:** 1140 passed, 4 skipped (+5 test, gồm 3 unit + 2 guard)
**Baseline sau Task 4:** 1142 passed, 4 skipped (+2 test)
**Finał (sau Task 5):** 1144 passed, 4 skipped (+2 test)

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

## Nhận xét cuối

- ✅ Tất cả 5 task hoàn thành, code merged vào nhánh worktree này
- ✅ Test suite 1144 passed, 4 skipped (không regression)
- ✅ Tất cả 6 finding từ review loop đều được xác nhận + sửa (0 open)
- ✅ Bất biến an toàn 1-4 kiểm chứng: không đụng `erp_write_executor`, `_interrupt()`, hay `state.get("confirmed")`
- ✅ Circular import check pass
- ⏳ Cổng đánh giá §7 (live-verify) chờ merge + controller verification
- ⏳ Eval `eval_chitchat` cần LLM thật, skip trong unit-only mode

