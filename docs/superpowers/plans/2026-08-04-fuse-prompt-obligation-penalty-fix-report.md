# Báo cáo — Task 2: Đo thật FUSE_PROMPT fix (lặp lại + multi_source không lùi + multi_source_gather)

Plan: `docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix.md`
Spec: `docs/superpowers/specs/2026-08-04-fuse-prompt-obligation-penalty-fix-design.md`

Fix đo ở đây là commit `9da99a4` (Task 1, đã merge vào worktree này) —
thêm đúng 1 dòng quy tắc vào `FUSE_PROMPT`
(`backend/src/agents/prompts.py`) yêu cầu đối chiếu đủ cặp
NGHĨA VỤ/THỜI HẠN + HẬU QUẢ/MỨC PHẠT cho câu hỏi tuân thủ/vi phạm. Mọi số
đo dưới đây chạy qua production path thật (`make_gather_erp_node` +
`render_fuse_input` + `FUSE_PROMPT` sống), model `gemini-3.1-flash-lite`
(role `fusion`), không dùng số liệu suy đoán hay tái sử dụng phép đo trước
khi plan tồn tại.

## 1. Bước 1 — Xác nhận hạ tầng

- `docker ps --filter name=youdoo-postgres`: `Up 9 hours (healthy)`.
- `curl http://localhost:8069`: `HTTP 303` (redirect bình thường tới
  `/web`) — Odoo phản hồi.

Hạ tầng đủ điều kiện đo thật, không cần dừng.

## 2. Bước 2 — Đo lặp lại N=5 lần, ca `WH/OUT/00001`

Script tạm `backend/_probe_fix_repeat.py` (đúng nguyên văn brief), chạy
qua `.venv/Scripts/python.exe`, đã XOÁ ngay sau khi lấy kết quả (`git
status --short` xác nhận sạch, không còn file này trước khi qua Step 3).

Đầu ra nguyên văn:

```
rep 1: PASS both=True citation_ok=True fabricated=[]
rep 2: PASS both=True citation_ok=True fabricated=[]
rep 3: PASS both=True citation_ok=True fabricated=[]
rep 4: PASS both=True citation_ok=True fabricated=[]
rep 5: PASS both=True citation_ok=True fabricated=[]
=== 5/5 PASS ===
```

**5/5 PASS** — khớp kỳ vọng của spec §6. Fix ổn định, không phải may mắn
một lần.

## 3. Bước 3 — `--set multi_source` (ràng buộc cứng: KHÔNG được lùi)

```
cd backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Đầu ra:

```
[multi_source] model=gemini-3.1-flash-lite pace=4.8s both_source_coverage=0.750 baseline=0.750 → PASS
== PASS == exit 0 → logs/jobs/eval-gate-20260804T184404.json
```

Log JSON đầy đủ: `logs/jobs/eval-gate-20260804T184404.json`.

So sánh trước/sau CÙNG MODEL (`gemini-3.1-flash-lite`), cùng set, cùng ca:
"before" ở đây là `D:/Youdoo/logs/jobs/eval-gate-20260802T182217.json`
(nằm trong logs của repo chính, không phải worktree này — chạy trước plan
này, còn dùng `FUSE_PROMPT` bản CŨ chưa có quy tắc nghĩa vụ/hậu quả).
`backend/evals/baseline-qwen3-8b-multi_source.json` (model khác hẳn,
`qwen3:8b`) KHÔNG dùng làm cột "before" ở đây — đó là ngưỡng `baseline`
mà `_gate()` so sánh cơ học khi chạy job thật (xem lệnh ở trên,
`baseline=0.750` trong dòng log), giữ nguyên vai trò đó; file baseline
này còn 6 mục trong `fails[]` (4 mục có `both: true`, tồn dư từ một lượt
chấm lại trước khi rescore — xem field `original_fabricated_number`/
`rescored_at` trong chính file đó), nên không phải cột đối chiếu sạch để
đọc trực tiếp.

| | before (log cùng model, `eval-gate-20260802T182217.json`, prompt CŨ) | baseline (ngưỡng `_gate()` so sánh, model `qwen3:8b`) | after (đo thật, lần này, prompt MỚI) |
|---|---|---|---|
| `both_source_coverage` | 0.750 | 0.750 | 0.750 |
| `citation_validity` | 1.0 | 1.0 | 1.0 |
| `fabricated_number` | 0 | 0 | 0 |
| ca fail | `sla_giao_hang`/S00042, `chinh_sach_hoan_hang`/INV/2026/00017 | (không đối chiếu ca — model khác) | `sla_giao_hang`/S00042, `chinh_sach_hoan_hang`/INV/2026/00017 (giống hệt before) |

`both_source_coverage` giữ nguyên 0.750, KHÔNG lùi so với cả hai điểm đối
chiếu — gate PASS (so ngưỡng `baseline`) và không hồi quy so cùng model
trước-fix (so `before`). Thành phần 2 ca fail cũng giống hệt `before`
(cùng câu hỏi, cùng lý do: `S00042` thiếu ngày xác nhận/giao trong
`erp_block` viết tay của set này; `INV/2026/00017` thiếu loại sản phẩm).
Đúng ràng buộc cứng của Global Constraints/spec §4: `multi_source` không
hồi quy.

## 4. Bước 4 — `--set multi_source_gather`

```
cd backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source_gather
```

Đầu ra:

```
[multi_source_gather] model=gemini-3.1-flash-lite pace=4.8s both_source_coverage=0.875 citation_validity=1.000 fabricated_number=0 → PASS
== PASS == exit 0 → logs/jobs/eval-gate-20260804T185149.json
```

Log JSON đầy đủ: `logs/jobs/eval-gate-20260804T185149.json`.

`both_source_coverage = 0.875` (7/8) — tăng từ baseline trước-fix 0.750
(6/8), đúng khớp thực nghiệm ở spec §2 (Variant B). Ca `WH/OUT/00001`
(FIXED, PASS — xác nhận lại qua N=5 ở §2) không còn nằm trong danh sách
fail.

Bảng ca fail còn lại (chỉ 1 ca):

| topic | question | called | erp_facts (rút gọn) | both | citation_ok | fabricated |
|---|---|---|---|---|---|---|
| sla_giao_hang | Đơn S00042 có đáp ứng SLA giao hàng không? | `get_sale_order_detail` | "Ngày giao dự kiến: 20/07/2026; Ngày giao thực tế: 21/07/2026; Trạng thái giao: Đã giao đủ (full)" | false | true | `[]` |

Ca fail còn lại đúng là `S00042` — không có ca nào khác mới xuất hiện, nên
không phải hồi quy. Nguyên nhân đã biết trước, ghi ở spec §5 (dẫn chiếu,
không lặp lại toàn văn): dữ liệu ERP của đơn này không có trường nào báo
"khẩn cấp", nên model không có căn cứ áp điều khoản 3-ngày (Điều 3) thay
vì hạn 7-ngày mặc định — đây là lỗ hổng dữ liệu ERP, khác lớp nguyên nhân
với lỗi tổng hợp mà plan này sửa, cố ý ngoài phạm vi.

Đối chiếu nhanh với ca fail duy nhất trước-fix của cùng set (từ report
`docs/superpowers/plans/2026-08-04-multi-source-gather-eval-report.md`
§3): trước-fix, `fabricated=["01"]` (số "01" trong "chậm 01 ngày", giới
hạn thiết kế đã biết của scanner khi model tự tính hiệu số ngày). Sau-fix,
`fabricated=[]` — đây là kết quả đo THẬT (điểm số đọc trực tiếp từ log).
**Cơ chế cụ thể vì sao vẫn là giả thuyết CHƯA xác minh được**: field
`response` trong `logs/jobs/eval-gate-20260804T185149.json` cho ca này bị
log cắt ở đúng 300 ký tự, dừng ngay tại `"...tức là đã chậm "` — đúng chỗ
một số đếm ngày (nếu có) sẽ xuất hiện, và không còn artifact nào khác lưu
response đầy đủ (checkpoint tạm đã bị dọn sau khi chạy xong thành công).
Có thể model không còn nêu số ngày trễ tự tính (đổi cách lập luận vì có
quy tắc mới), nhưng cũng có thể model đã diễn đạt bằng chữ (ví dụ "một
ngày" thay vì "01 ngày") — cả hai khả năng đều cho `fabricated=[]` mà
không cùng cơ chế. Chỉ biết chắc: `both` vẫn `false` vì lý do khác hẳn
(thiếu trường "khẩn cấp" trong ERP, không phải bịa số) — không phải cùng
một lỗi lặp lại với trước-fix, vì `both_source_coverage` tổng thể của ca
này (fail cả hai lần) không đổi nhưng lý do fail đã đổi (từ "tổng hợp kém
+ bịa số suy ra" sang "thiếu dữ liệu khẩn cấp trong ERP, không bịa số").

## 5. Kết luận theo tiêu chí hoàn thành (spec §8)

1. `FUSE_PROMPT` có đúng 1 dòng quy tắc mới, khớp §3 nguyên văn — **ĐẠT**
   (Task 1, commit `9da99a4`).
2. `pytest` unit-only xanh toàn bộ (1121 passed, 4 skipped, 43 deselected)
   — **ĐẠT** (Task 1 Step 6, xem `task-1-report.md`).
3. `--set multi_source`: `both_source_coverage` KHÔNG thấp hơn baseline
   (0.750 = 0.750), `citation_validity == 1.0`, `fabricated_number == 0`,
   gate PASS — **ĐẠT** (§3 ở trên).
4. `--set multi_source_gather`: `both_source_coverage` tăng từ 0.750 lên
   0.875 (7/8), ca `WH/OUT/00001` PASS, `S00042` vẫn FAIL vì lý do khác
   (đã ghi ở spec §5, không phải hồi quy của plan này) — **ĐẠT** (§4 ở
   trên).
5. Ca `WH/OUT/00001` chạy lại N=5 lần: tất cả PASS, xác nhận fix ổn định
   chứ không phải may mắn 1 lần — **ĐẠT** (§2 ở trên, 5/5).

Cả 5 tiêu chí hoàn thành của spec §8 đều ĐẠT. Plan
`2026-08-04-fuse-prompt-obligation-penalty-fix` hoàn tất cả 2 task, chờ
review.

## 6. Rủi ro còn lại — những gì phép đo này KHÔNG phủ

Các số ở §3/§4 chứng minh fix hoạt động trên đúng những ca đã đo, nhưng
không nên đọc rộng hơn thế. Ba giới hạn cụ thể của bằng chứng:

**(a) Không phải 2 mẫu độc lập.** `MULTI_SOURCE_CASES` và
`MULTI_SOURCE_GATHER_CASES` (`backend/evals/cases.py`) là CÙNG 8 câu hỏi
trên CÙNG 4 topic (`sla_giao_hang`, `chinh_sach_hoan_hang`,
`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`) và cùng bộ chunk tài liệu
đóng băng (`fixtures.load_chunks(topic)`, giống hệt cho cả hai set) — hai
set phản chiếu 1-1 nhau theo đúng thiết kế (xem comment "PHẢN CHIẾU 1-1
MULTI_SOURCE_CASES" trong `cases.py`), chỉ khác ở nguồn ERP: `erp_block`
viết tay nạp sẵn (multi_source) so với `gather_erp` thật tự đi lấy qua
`tool_fixtures` (multi_source_gather). Tổng bằng chứng thật đứng sau thay
đổi này là 8 câu hỏi / 4 văn bản chính sách, không phải "16 phép đo độc
lập" — hai set đo hai TẦNG khác nhau của cùng một bộ câu hỏi, không phải
hai bộ câu hỏi khác nhau.

**(b) Không có chỉ số nào bắt được một câu trả lời SAI nhưng tự tin.** Quy
tắc mới yêu cầu model "xác định trước có vi phạm nghĩa vụ hay không" — tức
chủ động đẩy model ra một kết luận nhị phân (tuân thủ hay vi phạm).
`_score_fusion` (`backend/evals/run_eval.py`) chỉ đo ba điều: `both` (hai
chuỗi kỳ vọng `doc_fact`/`erp_fact` có xuất hiện nguyên văn trong câu trả
lời, qua `_grounded_match` — so khớp chuỗi, KHÔNG so cực tính đúng/sai của
kết luận), `citation_ok` (chỉ số trích dẫn nằm trong phạm vi hợp lệ), và
`fabricated` (không có số nằm ngoài whitelist). Một câu trả lời khẳng định
SAI kiểu "có vi phạm, phạt 0,5%" cho một đơn thực ra KHÔNG vi phạm sẽ chấm
điểm giống hệt câu trả lời đúng, miễn là hai chuỗi kỳ vọng đó tình cờ vẫn
xuất hiện trong phần văn xuôi. Đây không phải rủi ro suy đoán: chính
docstring của `_grounded_match` (`run_eval.py`, đoạn "Lịch sử (SP-1C1,
chạy gate thật)") ghi lại việc review độc lập nhiều vòng từng bắt được câu
trả lời đảo cực tính (phủ định thật bị đọc nhầm thành khẳng định) vẫn khớp
qua một biến thể sớm hơn của chính hàm này. `false_confirm` — chỉ số duy
nhất trong hệ eval-gate nhắm đúng dạng lỗi "tự tin nhưng sai" — không phủ
lỗ hổng này cho cả hai set đo ở đây: với `multi_source` nó có mặt trong
log nhưng luôn là `null` (xem `logs/jobs/eval-gate-20260804T184404.json`,
`"false_confirm": null` — set này không phải kiểu case có/không xác nhận
nên chỉ số không áp dụng được); với `multi_source_gather`, field này
không được `eval_gate.py` ghi ra chút nào (nhánh
`elif set_name == "multi_source_gather"` không đưa `false_confirm` vào
`entry`). Tóm lại: không set nào trong hai set này có một phép đo tương
đương cho đúng loại lỗi mà quy tắc mới có nguy cơ tạo ra nhiều hơn (một
kết luận dứt khoát nhưng sai).

**(c) 2 lớp phía sau `fuse_answer` không được đo qua.** `fanout.py`
(`make_fuse_answer_node`, `backend/src/agents/fanout.py`) chạy tiếp
`cite_and_verify` rồi `verify_erp_grounding` NGAY SAU khi có response thô
từ `FUSE_PROMPT` — cả `eval_multi_source` lẫn `eval_multi_source_gather`
(`backend/evals/run_eval.py`) đều dừng lại ở response thô của lệnh gọi
`llm.ainvoke([FUSE_PROMPT, ...])`, không chạy tiếp qua hai lớp đó.
`verify_erp_grounding` (`backend/src/agents/erp_grounding.py`) trả về
"KHÔNG" sẽ thay THẾ TOÀN BỘ câu trả lời bằng `ERP_GROUNDING_FALLBACK_MSG`
("Xin lỗi, tôi không chắc chắn về độ chính xác của câu trả lời này...").
Quy tắc mới làm câu trả lời dài hơn (thêm hẳn một đoạn HẬU QUẢ/MỨC PHẠT
bên cạnh đoạn NGHĨA VỤ/THỜI HẠN) và thêm số liệu trích từ tài liệu chính
sách (mức phạt %, số ngày) vào phần văn xuôi được đối chiếu với dữ liệu
ERP thô ở lớp `verify_erp_grounding` — tức đổi phân bố đầu vào cho đúng
lớp kiểm tra nhị phân đó so với trước khi có quy tắc này. Hiệu ứng cụ thể
(tỷ lệ `verify_erp_grounding` trả "KHÔNG" có đổi hay không trên đường
production thật) chưa được đo qua đường thật ở phép đo này.

Không cần đo lại gì thêm để merge — mục này chỉ để người đọc sau biết bằng
chứng dừng ở đâu, không phải phê bình phép đo đã làm.

## Status contract (Task 2)

- **Status:** DONE
- N=5 lặp lại ca `WH/OUT/00001`: 5/5 PASS (nguyên văn ở §2).
- `--set multi_source`: KHÔNG hồi quy — `both_source_coverage` giữ nguyên
  0.750, gate PASS.
- `--set multi_source_gather`: `both_source_coverage` = 0.875 (7/8), ca
  fail còn lại đúng `S00042` (đã biết, ngoài phạm vi plan này).
- Log JSON: `logs/jobs/eval-gate-20260804T184404.json` (multi_source),
  `logs/jobs/eval-gate-20260804T185149.json` (multi_source_gather).
