# SP-2a: Nền tảng SOP skill dạng thư mục — Báo cáo xác nhận sống (Task 11)

**Ngày chạy:** 2026-07-31, ~17:30–18:45 (giờ Việt Nam).
**Môi trường:** worktree `sp2a-sop-skills`, backend venv riêng, MCP server
`mcp-odoo` chạy native (venv riêng dựng mới), Postgres `youdoo-postgres`
(container sẵn có, port 5434), Odoo native tại `localhost:8069` (đã chạy sẵn),
backend FastAPI tại `localhost:8000`.

**Tóm tắt 1 dòng:** Task 1-10 đều xanh (review sạch); Task 11 phát hiện và sửa
1 bug thật (`eval_intent` parse sai sau đổi hợp đồng router), 1 lần thử sửa
bị revert vì gây hồi quy khác, 1 rủi ro đã biết chấp nhận (`sop_select` gate
16/17), và 1 khoảng trống thật mới phát hiện (nhánh bắc cầu "không có PO"
không truy cập được qua router hiện tại) — ghi lại đầy đủ bên dưới, không che
giấu.

---

## 1. Kết quả 3 chế độ test

| Chế độ | Lệnh | Kết quả |
|---|---|---|
| Mặc định | `pytest -q --continue-on-collection-errors -m "not live and not integration"` | **1031 passed, 4 skipped, 42 deselected** |
| Integration | `pytest -q --continue-on-collection-errors -m "integration"` | **27 passed, 1050 deselected** |
| Live (`test_dau_cuoi_sop.py`) | `pytest tests/agents/test_dau_cuoi_sop.py -v -m live` | **3 passed** (xem §6) |

Fixture `tests/rag/fixtures/{bang_gia.xlsx,policy.docx}` bị re-serialize sau
mỗi lần chạy suite mặc định — đã `git checkout --` trước mỗi commit, theo
đúng quy ước dự án.

---

## 2. Eval gate `sop_select` — 3 lượt chạy (giữ nguyên làm provenance)

**Lượt 1** (mô tả `nhap-kho` nguyên bản từ Task 6):

```
[sop_select] model=gemma-4-26b pace=2.4s acc=0.9412 hijack=0 → FAIL
```

Ca duy nhất trượt: `"quy trình nhập kho cho đơn mua P00021"` (chính ca hồi
quy 2026-07-16) → `raw_intent="rag", raw_sop=null, got="rag"`. **Không phải
hijack** — router chỉ đơn giản không đề cử `sop`, lớp phủ quyết tất định
(Task 9) không có gì để phủ quyết vì không có đề cử.

**Chẩn đoán:** gọi trực tiếp router (script chẩn đoán, không qua eval
harness) với đúng prompt thật, 3/3 lần đều `'intent: rag\nsop:'` — nhất quán,
không phải nhiễu. Nguyên nhân: mô tả gốc dùng chung cụm "quy trình nhập kho"
ở cả vế "Dùng khi" và "KHÔNG dùng khi" — model rẻ (gemma-4-26b) không phân
biệt được câu lệnh cụ thể (có mã đơn) với câu hỏi khái quát chỉ dựa overlap
từ vựng đó.

**Lượt 2** (thử sửa mô tả — siết vế "KHÔNG dùng khi" neo vào tín hiệu "có/
không có mã đơn cụ thể"):

```
[sop_select] model=gemma-4-26b pace=2.4s acc=0.9412 hijack=0 → FAIL
```

Cùng acc (16/17) nhưng KHÁC ca thất bại về bản chất: cùng câu
`"quy trình nhập kho cho đơn mua P00021"`, nhưng lần này
`raw_intent="unknown", raw_sop=null` — router trả về **rỗng hoàn toàn**.
Chẩn đoán sâu hơn (5/5 lần lặp lại, luôn rỗng): `finish_reason: MAX_TOKENS`,
`output_token_details.reasoning: 2045` — Gemma tiêu hết ngân sách token cho
"suy nghĩ" (thinking) trước khi kịp trả lời 2 dòng, do mô tả dài hơn đẩy
prompt vào vùng phức tạp hơn. Đã thử bản mô tả rút gọn hơn (giữ đúng ý neo
vào mã đơn cụ thể) — vẫn 2/2 lần MAX_TOKENS cho đúng câu này, trong khi các
câu chị em tương tự (`"nhập kho theo quy trình cho đơn mua P00021"`, `"làm
quy trình nhập kho cho đơn mua P00021"`) lại đúng và ổn định (`finish_reason:
STOP`, 2/2 lần).

**Phát hiện phụ nghiêm trọng hơn:** áp mô tả lượt 2 vào `SKILL.md` thật rồi
kiểm tra nhánh bắc cầu "không có PO" (SP-2a §6.4) qua flow thật — mô tả mới
KHÔNG cho phép vào node `nhap-kho` khi câu không có mã đơn cụ thể, kể cả khi
đó là yêu cầu thực thi rõ ràng ("làm quy trình nhập kho giúp tôi, nhưng tôi
chưa có đơn mua nào cả") — router phân loại `rag` thay vì đề cử `sop`. Đây là
hồi quy thật: bước 1 của prose `nhap-kho` (`SKILL.md`) được thiết kế để CHO
PHÉP vào SOP rồi hỏi mã đơn sau (`ask_human`) — không đòi mã đơn phải có sẵn
từ đầu. Mô tả lượt 2 mâu thuẫn trực tiếp với thiết kế này.

→ **Đã `git revert` commit mô tả lượt 2** (`82db6e0` → revert `380fc4c`),
khôi phục nguyên văn mô tả Task 6.

**Lượt 3** (xác nhận sau revert, số liệu cuối cùng dùng cho báo cáo):

```
[sop_select] model=gemma-4-26b pace=2.4s acc=0.9412 hijack=0 → FAIL
```

Đúng lại ca lượt 1 (`raw_intent="rag", raw_sop=null`) — xác nhận `git revert`
khôi phục đúng hành vi gốc.

**Quyết định cuối (người dùng đã xác nhận):** chấp nhận `sop_select` gate FAIL
16/17 làm rủi ro đã biết, đúng tinh thần Phụ lục B của spec ("Vai router
dùng model rẻ nhất chuỗi... Nếu đỏ: nâng model vai router, hoặc siết vế
'KHÔNG dùng khi'"). Đã thử remedy "siết mô tả" — không thành công (đổi loại
lỗi, không giảm được lỗi, và có nguy cơ gây hồi quy nếu không cẩn thận).
Remedy còn lại ("nâng model vai router") là thay đổi `catalog.py` ảnh hưởng
TOÀN HỆ THỐNG, ngoài phạm vi file của SP-2a — để lại cho SP-2b hoặc một
quyết định vận hành riêng.

**Bài học chung (đáng ghi vào memory dự án):** mô tả SKILL.md dài hơn/nhiều
ví dụ hơn không đơn thuần "an toàn hơn" — với model có chế độ "suy nghĩ"
(Gemma), độ dài prompt tăng có thể đẩy model vào tiêu hết ngân sách token cho
reasoning trước khi trả lời, biến một lỗi phân loại nhẹ thành một câu trả lời
rỗng. Và một mô tả "siết" đúng ca lỗi có thể vô tình loại luôn các ca hợp lệ
khác dùng chung tín hiệu bề mặt (ở đây: "có/không có mã đơn cụ thể") — bài
học layer-1 (description) không cần cố gắng phân biệt "câu hỏi" khỏi "câu
lệnh" một cách hoàn hảo, vì đó chính là việc của layer-2 (`_looks_like_
question`, tất định) — cố làm luôn việc của layer 2 ở layer 1 dễ tạo tác
dụng phụ không lường trước.

---

## 3. Eval gate `intent` — bug thật tìm thấy và sửa

**Lượt 1:**

```
[intent] model=gemma-4-26b pace=2.4s acc=0.148 baseline=0.870 → FAIL
```

**Không phải lỗi model — lỗi code thật.** Mọi case (52/56) rơi về `"unknown"`.
Nguyên nhân: Task 8 đổi `INTENT_ROUTER_PROMPT` từ "trả 1 từ intent" sang "trả
2 dòng `intent:`/`sop:`", nhưng `eval_intent()` ở `backend/evals/run_eval.py`
(hàm ĐO, không nằm trong phạm vi sửa của Task 8) vẫn parse kiểu cũ:
`got = resp.content.strip().lower()` rồi so trực tiếp với `VALID_INTENTS`.
Chuỗi 2 dòng không bao giờ khớp 1 từ trong tập đó → mọi case (dù model phân
loại đúng hay sai) đều rơi về `"unknown"`.

Node thật (`nodes.py`, Task 8) **không có lỗi này** — nó dùng
`_parse_router_output` từ đầu. Chỉ hàm đo `eval_intent()` bị bỏ sót vì sống ở
module khác Task 8 không chạm tới. Unit test không bắt được vì mock LLM trả
thẳng bare-word (`"erp_read"`), tình cờ vẫn khớp qua nhánh fallback bare-word
của `_parse_router_output` — chỉ lộ ra khi gọi model thật trả đúng hợp đồng 2
dòng nó thật sự dùng trong production. **Đúng loại lỗi bước xác nhận sống này
tồn tại để bắt** (tương tự SP-1C2 Task 8 tìm ra lỗi `annotate_current_span`).

**Fix** (commit `c14b61b`): `eval_intent()` dùng chung `_parse_router_output`
với node thật và `eval_sop_select` — một nguồn sự thật duy nhất cho cách
parse đầu ra router.

**Lượt 2** (sau fix):

```
[intent] model=gemma-4-26b pace=2.4s acc=0.944 baseline=0.870 → PASS
```

**PASS**, thậm chí cao hơn baseline (0.944 vs 0.870) — bộ `intent` cũ **không
thụt** sau khi đổi hợp đồng router 2 dòng, đúng điều kiện §5.3 điều kiện 2
của spec.

---

## 4. Fail-loud khi SKILL.md khai tool ngoài quyền (§9.3)

Đổi tạm `backend/skills/giao-hang/SKILL.md`: `deliver_order` →
`xoa_sach_don_hang` (tool không tồn tại), gọi `build_graph()` với registry MCP
có `deliver_order` thật (không rỗng — đường fail-loud, không phải đường test).

**Kết quả: PASS.**

```
src.agents.skill_manifest.SkillManifestError: skill 'giao-hang': tool ghi
'xoa_sach_don_hang' không có trong registry MCP
```

App không lên, traceback nêu đúng tên skill và tên tool sai — đúng điều kiện
"log chỉ đúng file và đúng dòng sai". Đã khôi phục file, `git status` sạch
sau khi khôi phục.

---

## 5. "Sửa prose + restart → hành vi đổi, không đụng .py" (§9.2)

Backend + `mcp-odoo` đã chạy sống. Gửi `"làm quy trình giao hàng cho đơn bán
S00012"` qua `/v1/chat/completions` thật → router → node `giao-hang` → tra
đơn thật (Odoo có đơn S00012, khách "Gemini Furniture", state="sale") → dừng
ở cổng xác nhận: `"Xác nhận GIAO HÀNG cho đơn bán S00012?"`.

Sửa **một dòng prose** trong `backend/skills/giao-hang/SKILL.md` (bước 4):
thêm câu bắt buộc *"LUÔN kết thúc câu trả lời bằng đúng câu 'Đã xong nhé.'"*.
Restart backend (kill process cũ, chạy lại `run.py`). Gửi lại đúng flow
(3 message: lệnh gốc → câu hỏi xác nhận → `"có"`).

**Câu trả lời SAU khi sửa prose:**

```
Đơn S00012 không có phiếu cần giao (dịch vụ hoặc đã giao đủ).

Đã xong nhé.
```

Câu `"Đã xong nhé."` xuất hiện **đúng như prose mới yêu cầu** — xác nhận trực
tiếp: sửa prose + restart → hành vi trợ lý đổi theo, không cần sửa file `.py`
nào (`tools`/wrapper/gate hoàn toàn giữ nguyên qua cả hai lượt gọi).

`git checkout -- backend/skills/giao-hang/SKILL.md`, sau đó `git status`
**sạch toàn repo** — xác nhận không file `.py` nào bị đụng trong toàn bộ quá
trình này.

(Kết quả nghiệp vụ "không có phiếu cần giao" là dữ liệu Odoo thật của môi
trường test — không phải lỗi; nó xác nhận `deliver_order` thật sự được gọi
và Odoo thật sự trả lời, không phải mock.)

---

## 6. Test live e2e — `backend/tests/agents/test_dau_cuoi_sop.py`

Tạo mới đúng theo mẫu ở plan (fixture `event_loop_sop` module-scope, dùng
trực tiếp `ERPAgent`, không qua HTTP).

```
tests/agents/test_dau_cuoi_sop.py::test_lenh_co_ngon_ngu_quy_trinh_vao_node_sop PASSED
tests/agents/test_dau_cuoi_sop.py::test_cau_hoi_ve_quy_trinh_khong_bi_sop_cuop PASSED
tests/agents/test_dau_cuoi_sop.py::test_tu_choi_xac_nhan_thi_khong_ghi_gi PASSED

3 passed in 95.66s (0:01:35)
```

**3/3 PASS** — chạy thật, không skip (đủ biến môi trường). Cảnh báo
`Failed to export span batch due to timeout` lúc thoát là Langfuse flush
timeout (bất đồng bộ, không ảnh hưởng kết quả test) — không liên quan
SP-2a.

---

## 7. Flow SOP đầu-cuối qua Odoo thật (kiểm bằng tay)

Cần `mcp-odoo` :8001 (đã khởi động, venv mới dựng), Odoo :8069 (đã chạy
sẵn), Postgres :5434 (`youdoo-postgres`, đã chạy sẵn), backend :8000 (đã
khởi động).

1. **Câu xác nhận đúng nguyên văn** — PASS, xem §5.
   `"Xác nhận GIAO HÀNG cho đơn bán S00012?"`.
2. **Trả lời "không" → không ghi gì** — PASS.
   Câu trả lời: `"Người dùng TỪ CHỐI xác nhận — KHÔNG thực hiện thao tác.
   Hãy hỏi người dùng muốn làm gì tiếp."` — echo đúng `REFUSED_MSG`, không
   có dấu hiệu ghi nào (không tool ghi nào được gọi — wrapper trả sớm trước
   `ainvoke`, đã xác nhận bằng code review Task 4/9).
3. **Trả lời "có" → chạm Odoo thật** — PASS (xem §5): trợ lý trả lời dựa trên
   kết quả thật của `deliver_order` gọi vào Odoo ("không có phiếu cần giao").
   Không kiểm được "chuyển trạng thái đúng" cho case này cụ thể (đơn S00012
   không có phiếu để giao trong dữ liệu hiện tại của môi trường) — đã xác
   nhận qua §5 rằng tool ghi thật sự được gọi (không phải mock), đó là bằng
   chứng chính cần có ở bước này.
4. **Nhánh bắc cầu "không có PO"** — ⚠️ **PHÁT HIỆN KHOẢNG TRỐNG THẬT, CHƯA
   XỬ LÝ.** Xem chi tiết §8.4 bên dưới.
5. **`agentic_context_sync` bàn giao `working_context`** — ⚠️ **KHÔNG KIỂM
   ĐƯỢC** — đã ghi nhận từ review Task 7/9: `agentic_context_sync` đã port
   và có test riêng (Task 1) nhưng **không được wire vào `build_graph()`**
   trong phạm vi SP-2a (không có task nào trong 11 task nối nó vào graph
   thật — spec §0 liệt kê rõ đây là hạn chế đã biết, không phải lỗi). Do đó
   không có handoff `working_context` thật giữa lượt SOP và lượt tier-1 kế
   tiếp trong repo này.

---

## 8. Bằng chứng cho từng điều kiện "SP-2a xong" (§9 của spec)

| # | Điều kiện | Trạng thái |
|---|---|---|
| 1 | `backend/skills/` có 3 thư mục đúng cấu trúc | ✅ Xác nhận qua review Task 6, 7 |
| 2 | Sửa prose + restart → hành vi đổi, không đụng `.py` | ✅ §5, kiểm thật |
| 3 | Khai tool ngoài quyền → app không lên, log đúng | ✅ §4, kiểm thật |
| 4 | `SOP_SELECT_CASES` xanh toàn bộ + `intent` không thụt | ⚠️ **Một phần**: `intent` PASS (0.944 ≥ 0.870, sau khi sửa bug thật). `sop_select` **FAIL 16/17** — rủi ro đã biết, chấp nhận theo quyết định người dùng (§2). Ca hồi quy nguyên văn 2026-07-16 CÓ mặt trong `SOP_SELECT_CASES` (đúng yêu cầu) nhưng KHÔNG đạt. |
| 5 | Test bất biến bảo mật mở rộng xanh | ✅ Review Task 9: 5 thuộc tính an toàn cốt lõi hand-verify + test thật, xanh sau 1 vòng fix |
| 6 | Toàn bộ test xanh ở cả ba chế độ | ✅ §1: mặc định 1031 passed, integration 27 passed, live 3 passed |
| 7 | Một flow SOP thật chạy đầu-cuối qua Odoo thật | ✅ **Một phần**: §7 mục 1-3 PASS thật; mục 4 (bắc cầu) phát hiện khoảng trống; mục 5 (context handoff) không kiểm được do hạn chế đã biết từ trước |

### 8.4. Chi tiết khoảng trống: nhánh bắc cầu "không có PO"

**Hiện tượng:** câu `"làm quy trình nhập kho giúp tôi"` (không có mã đơn cụ
thể nào, dù rất rõ ràng là yêu cầu thực thi, không phải câu hỏi) route sang
`rag` thay vì `nhap-kho` — kể cả với mô tả GỐC của Task 6 (đã xác nhận độc
lập, không liên quan gì tới lượt sửa mô tả ở §2). Router không đề cử `sop`
khi câu thiếu tín hiệu mã đơn cụ thể.

**Hệ quả:** bước 2 của prose `nhap-kho` (nhánh "không có PO", `SKILL.md`
dòng 34-37 — trả nguyên văn `NO_PO_BRIDGE_MSG`) **hiện không thể truy cập
được** qua cách phân loại router hiện tại, vì: để vào được node `nhap-kho`
router cần một tín hiệu đủ mạnh (thường là có mã đơn cụ thể trong câu), nhưng
nếu người dùng ĐÃ nói "không có đơn mua" thì theo định nghĩa họ không có mã
đơn để cung cấp — tự mâu thuẫn với điều kiện router hiện đang cần để đề cử.

**Đây là khoảng trống PHÁT HIỆN MỚI qua Task 11**, không có trong
`SOP_SELECT_CASES` (17 ca của Task 10 đều dùng câu CÓ mã đơn cụ thể cho
`nhap-kho`) và không được test đơn vị nào phủ (test đơn vị mock LLM, không đo
hành vi phân loại thật). Chưa sửa trong phạm vi SP-2a này — cùng loại rủi ro
với §2 (phụ thuộc chất lượng phân loại của model rẻ ở vai router), remedy
giống nhau (nâng model vai router, hoặc thiết kế lại cách đề cử SOP không chỉ
dựa vào mã đơn — cả hai đều ngoài phạm vi file của SP-2a).

---

## 9. Hạn chế còn lại (nói thẳng, không giấu)

1. **`sop_select` eval gate FAIL 16/17** (§2) — chấp nhận làm rủi ro đã biết
   theo quyết định người dùng. Ca duy nhất trượt là chính ca hồi quy
   2026-07-16 mà kiến trúc SP-2a được thiết kế để bảo vệ — router (model rẻ
   gemma-4-26b) không đề cử được `sop` cho câu đó, dù lớp phủ quyết tất định
   (đã port và test xanh) sẽ xử lý đúng NẾU được đề cử.
2. **Nhánh bắc cầu "không có PO" của `nhap-kho` không truy cập được** (§8.4)
   — phát hiện mới, chưa xử lý.
3. **`agentic_context_sync` không được wire vào `build_graph()`** — đã biết
   từ Task 7/9's review, nằm ngoài phạm vi 11 task của plan này (không task
   nào giao việc nối nó vào graph thật). `working_context` không bàn giao
   được giữa lượt SOP và lượt tier-1 kế tiếp.
4. **Chưa có UI soạn SOP, chưa hot-reload, chưa có orchestrator, `fusion`
   vẫn còn** — đúng như spec §9 đã liệt kê là "chưa làm được sau SP-2a", cố
   ý, không phải thiếu sót.
5. **`_visible_schema()`'s dict branch** (Task 4) chỉ có 1 test tự viết
   thêm ở vòng fix — chưa có test end-to-end qua registry MCP thật dạng dict
   (dù đã verify đúng hình dạng qua review).

---

## 10. Commit trong quá trình Task 11

| Commit | Nội dung |
|---|---|
| `82db6e0` | (đã revert) thử siết mô tả `nhap-kho` |
| `380fc4c` | Revert `82db6e0` — phát hiện gây hồi quy nhánh bắc cầu |
| `c14b61b` | fix thật: `eval_intent()` parse sai sau đổi hợp đồng router 2 dòng |
| (task này) | `backend/tests/agents/test_dau_cuoi_sop.py` (mới), báo cáo này |

**Kết luận:** Task 1-10 hoàn thành sạch qua review. Task 11 xác nhận sống
bắt được 1 bug thật cần sửa (đã sửa, PASS), tránh được 1 hồi quy do chính
lượt vá của Task 11 gây ra (đã phát hiện và revert kịp), và phát hiện 2 rủi
ro/khoảng trống thật (đã biết + mới) liên quan tới độ tin cậy phân loại của
model rẻ ở vai router khi không có mã đơn cụ thể trong câu — cả hai đều
không phải lỗi an toàn (không có write nào xảy ra sai, `hijack=0` xuyên
suốt mọi lượt gate), chỉ là giới hạn UX/độ phủ của tier-2 routing, ghi nhận
làm việc tiếp cho SP-2b hoặc một vòng tinh chỉnh router riêng.
