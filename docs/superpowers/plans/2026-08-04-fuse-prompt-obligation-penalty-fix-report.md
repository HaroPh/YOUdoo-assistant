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

| | before (baseline file) | after (đo thật, lần này) |
|---|---|---|
| `both_source_coverage` | 0.750 | 0.750 |
| `citation_validity` | 1.0 | 1.0 |
| `fabricated_number` | 0 | 0 |
| ca fail | `sla_giao_hang`/S00042, `chinh_sach_hoan_hang`/INV/2026/00017 | `sla_giao_hang`/S00042, `chinh_sach_hoan_hang`/INV/2026/00017 (giống hệt) |

`both_source_coverage` giữ nguyên 0.750, KHÔNG lùi — gate PASS. Thành phần
2 ca fail cũng giống hệt baseline (cùng câu hỏi, cùng lý do: `S00042`
thiếu ngày xác nhận/giao trong `erp_block` viết tay của set này;
`INV/2026/00017` thiếu loại sản phẩm). Đúng ràng buộc cứng của Global
Constraints/spec §4: `multi_source` không hồi quy.

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
`fabricated=[]` — response không còn nêu số ngày trễ tự tính (đổi cách lập
luận vì có quy tắc mới), nhưng `both` vẫn `false` vì lý do khác hẳn (thiếu
trường "khẩn cấp" trong ERP, không phải bịa số). Không phải cùng một lỗi
lặp lại — thành phần lỗi bên trong ca fail cũng đã đổi, dù `both_source_coverage`
tổng thể của ca này (fail cả hai lần) không đổi.

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

## Status contract (Task 2)

- **Status:** DONE
- N=5 lặp lại ca `WH/OUT/00001`: 5/5 PASS (nguyên văn ở §2).
- `--set multi_source`: KHÔNG hồi quy — `both_source_coverage` giữ nguyên
  0.750, gate PASS.
- `--set multi_source_gather`: `both_source_coverage` = 0.875 (7/8), ca
  fail còn lại đúng `S00042` (đã biết, ngoài phạm vi plan này).
- Log JSON: `logs/jobs/eval-gate-20260804T184404.json` (multi_source),
  `logs/jobs/eval-gate-20260804T185149.json` (multi_source_gather).
