# Báo cáo kết thúc: 2026-08-06-invoice-confirm-summary

**Trạng thái:** HOÀN THÀNH — merge vào `main` (fast-forward), §Cổng đánh giá live-verify ĐẠT cả 4 tiêu chí (đo thật, có bằng chứng DB).

**Nhánh:** `invoice-confirm-summary` (worktree, đã xoá sau merge)

**Ngày hoàn thành:** 2026-08-07

**Spec:** `docs/superpowers/specs/2026-08-06-invoice-confirm-summary-design.md`
**Plan:** `docs/superpowers/plans/2026-08-06-invoice-confirm-summary.md`

---

## Tóm tắt

Người dùng nay thấy bảng dòng hàng + số tiền của đúng hóa đơn **trước** khi
xác nhận `post_invoice`/`register_payment`, kể cả khi hai thao tác này là
bước trong chuỗi tự động (trước đây chỉ hiện `"(post_invoice:
partner_name=Acme)"` — không biết hóa đơn nào, bao nhiêu tiền, một lỗ hổng
an toàn thật trên thao tác đụng tiền).

## Task 1: Ba hàm đọc hóa đơn trong `erp_query`

**Commit:** `ffdad6c` — "feat(erp_query): đọc chi tiết hóa đơn + dòng hàng, tìm nháp/còn nợ"

**File:** `backend/src/erp_query/accounting.py` (+3 hàm: `get_invoice_detail`,
`find_draft_invoices`, `find_open_invoices`), `backend/tests/erp_query/test_accounting.py`

**Review:** Spec ✅, quality Approved. 2 minor deferred (test hơi phức tạp;
`_INVOICE_TYPES` gồm cả refund — theo dõi tiếp ở Task 1-review, xử lý thật ở
fix wave final review, xem dưới).

## Task 2: Coordinator `post_invoice`

**Commit:** `d3faef7` + fix round `a620eda`

**Phát hiện giữa chừng:** plan tự mâu thuẫn — literal test dùng dấu chấm
(`"17.520"`, kiểu Việt Nam) nhưng code mẫu dùng `:,.0f` (dấu phẩy, mặc định
Python). Người dùng quyết: giữ quy ước có sẵn của repo (dấu phẩy). Fix round
1 bỏ helper `_vnd()` tạm, sửa 2 literal test.

**Review:** Spec ✅, quality Approved, 0 finding sau fix round.

## Task 3: Coordinator `register_payment`

**Commit:** `ee15239`

**Review:** Spec ✅, quality Approved, **0 finding** — không phát sinh lệch
plan nào, tái sử dụng đúng helper của Task 2 (`render_invoice_summary`,
`_pick_invoice`, `_detail_or_msg`, `_finish`).

## Task 4: Chuỗi tự động dừng hỏi lại ở bước đụng tiền

**Commit:** `6752117` + fix round `033d31e`

**Review (model Opus, task rủi ro cao nhất — đụng routing dùng chung):**
reviewer tự viết probe ngoài cây chạy graph thật + coordinator thật, xác
nhận cơ chế đúng. Nhưng 3 finding Important: `graph.py` map target mới
(2 dòng) không có test nào phủ (xoá đi vẫn compile sạch, chỉ vỡ lúc runtime);
helper test `_write_graph()` lệch khỏi wiring `graph.py` thật; hành vi đầu
đề của plan (chuỗi dừng đúng chỗ) chưa được test qua graph có conditional
edge thật. Đúng hình dạng lỗi `write-confirmation-ux-fix` (2026-08-05): cơ
chế đúng logic nhưng chưa ai test qua đường thật.

**Fix round 1:** `033d31e` — chỉ sửa file test (3 test mới/sửa, production
code không đổi). Re-review: cả 3 ADDRESSED, verify độc lập bằng cách đọc
trực tiếp code (không tin báo cáo).

## Final whole-branch review (model Opus)

**Ready to merge: With fixes.** 2 finding Important, cả hai đều là **lỗi
của chính plan** (implementer làm đúng theo plan) nhưng tái tạo đúng lỗ hổng
UX mà tính năng này sinh ra để diệt — nên vẫn phải sửa trước merge, không
park:

1. Coordinator đọc `move_type`/`state` từ `get_invoice_detail` nhưng không
   validate trước khi hiện bảng xác nhận. Đường thật: chuỗi
   `create_credit_memo → post_invoice → register_payment` (có trong
   `NEXT_STEPS`) có thể chạm một hóa đơn hoàn tiền (`out_refund`/`in_refund`)
   — `register_payment` MCP tool chỉ nhận `out_invoice`/`in_invoice` — user
   xác nhận xong mới bị báo "không tìm thấy". Tương tự `post_invoice` không
   check `state=draft` (hóa đơn đã phát hành vẫn hiện được).
2. `_invoice_label` (viết cho draft, `amount_total==amount_residual` luôn
   đúng) bị dùng lại nguyên cho picker `register_payment` — hiện sai số
   (tổng thay vì số dư) và không phân biệt được 2 hóa đơn cùng tổng khác số
   dư — đúng vấn đề plan viện dẫn để tạo `find_open_invoices` riêng.

**Fix wave:** `cea29f6` — thêm guard `state`/`move_type` trước cổng xác
nhận ở cả 2 coordinator; `_invoice_label`/`_pick_invoice` nhận tham số
`amount_field`, `register_payment` picker nay hiện `amount_residual`;
`find_open_invoices`'s filter `amount` đổi bind sang `amount_residual` khớp
tool gốc. +4 test (TDD, RED→GREEN đủ). Re-review: cả 2 finding ADDRESSED,
không breakage mới.

**Minor deferred (không chặn merge):** chain-note nói "tự động" cho bước
nay không còn tự động (an toàn theo hướng thừa cảnh báo); header xác nhận
`post_invoice` thiếu `invoice_id` (ca 10-draft-trùng-tiền không phân biệt
được ở đúng bước xác nhận — disambig bước trước có ID); type hint
`totals: list` vs `list[str]`; `except Exception` rộng quanh `tool.ainvoke`
(khớp pattern 5 coordinator anh em khác); chưa có test cancel-mid-chain
(đã trace tay đúng, chỉ thiếu test); duplicate import trong
`test_auto_chain.py`; plan doc gốc còn literal "17.520" sai (code/test đã
đúng "17,520" — xem Task 2).

## Kết quả test toàn bộ

**Baseline trước plan:** 1153 passed, 0 fail thật (đo trên worktree).
**Cuối cùng (sau final-review fix wave, trên `main` đã merge):**

```
cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"
```
```
1185 passed, 4 skipped, 46 deselected in 22.63s
```

**Tổng cộng:** +32 test mới (1185 − 1153).

---

## Cổng đánh giá — kết quả thật (controller đo sau merge, 2026-08-07)

Nhánh đã merge vào `main` (fast-forward, commit `cea29f6`). Controller khởi
động lại backend thật (`D:\Youdoo\backend`, không qua worktree) với code vừa
merge, đo trực tiếp qua API thật (`POST /v1/chat/completions`, gửi lại
**toàn bộ lịch sử hội thoại** mỗi lượt, **không** `session_id` — đúng mô
phỏng client Open WebUI thật, theo đúng phương pháp đã rút ra từ
`write-confirmation-ux-fix`). Write kill-switch
(`erp_ai.write_actions_enabled`) đã sẵn `True` từ trước (không cần bật lại).

### Tiêu chí 1 — gọi trực tiếp, có mơ hồ thật: ✅ ĐẠT

`"Phát hành hóa đơn nháp của Acme Corporation"` → trả về **danh sách 10 bản
nháp thật** để chọn (dữ liệu thật đã tích luỹ qua nhiều phiên live-verify
trước, nhiều hơn 5 bản plan mô tả ban đầu — cùng hiện tượng: đều "Acme
Corporation", đa số trùng 140), **chưa phát hành gì**. Chọn mục 1 → hiện
đúng bảng dòng hàng + tổng tiền:

```
Hóa đơn nháp của Acme Corporation — ngày chưa có:
  - [FURN_7777] Office Chair × 2 = 140
  Tổng: 140
Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)
```

Trả lời "không" → `"Đã hủy phát hành hóa đơn."` — xác nhận DB: hóa đơn ID 77
vẫn `state=draft`, không bị đụng.

### Tiêu chí 2 — chuỗi có bước đụng tiền phải DỪNG: ✅ ĐẠT

Gửi (mở rộng thành chuỗi 3 bước để phủ luôn tiêu chí 3 rủi ro cao nhất):
`"Tạo hóa đơn cho đơn S00120 rồi phát hành và ghi nhận thanh toán luôn"`

→ Xác nhận khai báo chuỗi 3 bước đúng (`create_invoice_from_order` →
"Phát hành hóa đơn" → "Ghi nhận thanh toán"). Trả lời "có" → hóa đơn nháp
được tạo thật từ đơn S00120 (sản phẩm thật `[FURN_78236] Table Kit`), rồi
**DỪNG LẠI** hỏi xác nhận kèm bảng tóm tắt, **KHÔNG** tự phát hành:

```
Hóa đơn nháp của Acme Corporation — ngày chưa có:
  - [FURN_78236] Table Kit × 1 = 147
  Tổng: 169
Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)
```

### Tiêu chí 3 — resume giữa chuỗi phải chạy nốt: ✅ ĐẠT (hạng mục rủi ro cao nhất)

Trả lời "có" → `post_invoice` chạy thật (hóa đơn được cấp số
`INV/2026/00030`), và `auto_chain` còn `register_payment` → bước đó **tiếp
tục tự động dừng lại** hỏi xác nhận kèm `amount_residual`:

```
Thanh toán hóa đơn INV/2026/00030 — Acme Corporation:
  - [FURN_78236] Table Kit × 1 = 147
  Tổng hóa đơn: 169
  Số dư sẽ thanh toán: 169
Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)
```

Trả lời "có" lần 3 → `"Đã ghi nhận thanh toán 169đ cho hóa đơn INV/2026/00030
(Acme Corporation) qua sổ Bank. Đã thanh toán đủ."`

**Xác nhận DB độc lập** (không chỉ tin văn bản trả lời):
```
account.move id=106 name='INV/2026/00030' state='posted'
  payment_state='paid' amount_total=169.05 amount_residual=0.0
  invoice_origin='S00120'
sale.order id=120 name='S00120' state='sale' invoice_status='invoiced'
```
Khớp hoàn toàn với hội thoại — cả 3 bước của chuỗi 3-hop đụng tiền chạy
đúng, dừng đúng chỗ, không rò rỉ resume value giữa các interrupt (đúng như
final review đã chứng minh bằng probe ngoài cây).

### Tiêu chí 4 — chống hồi quy chaining nói chung: ✅ ĐẠT

`"Tạo báo giá 2 Office Chair cho Acme rồi xác nhận luôn"` (qua 2 lượt
disambig thật — khách hàng trùng tên, sản phẩm trùng tên — không liên quan
tới thay đổi của plan này) → hiện bảng báo giá kèm `"Sau đó tự động: Xác
nhận báo giá"`. Trả lời "có" → `"Đã xác nhận đơn S00166."` — chuỗi
`create_quotation → confirm_sale_order` **auto-run, không** dừng lại hỏi
xác nhận ở bước `confirm_sale_order`, đúng hành vi trước khi có thay đổi.

**Xác nhận DB:** `sale.order id=166 name='S00166' state='sale'` (đã xác
nhận thật).

### Kết luận cổng đánh giá

**Cả 4 tiêu chí ĐẠT — đo thật trên backend production đã merge, có bằng
chứng DB độc lập cho từng tiêu chí.** Không phần nào bị revert.

---

## Nhận xét cuối

- ✅ Tất cả 4 task code hoàn thành + final whole-branch review (1 fix wave,
  2 Important đã sửa) + merge fast-forward vào `main` (không conflict)
- ✅ Test suite 1185 passed, 4 skipped (không regression) — đo lại trên
  `main` sau merge
- ✅ Tổng 8 finding Important qua toàn bộ review loop (Task 4: 3, final
  review: 2, cộng các finding nhỏ hơn) đều được xác nhận + sửa, verify độc
  lập bằng cách đọc code trực tiếp (không tin báo cáo implementer)
- ✅ Bất biến an toàn: coordinator luôn gọi tool bằng `invoice_id` đã
  resolve; `WRITE_CONFIRM_SUFFIX` dùng nhất quán; `CONFIRM_IN_CHAIN` là tập
  tường minh 2 phần tử, không rò rỉ sang `convert_lead`/`update_vendor_pricing`
- ✅ **Cổng đánh giá live-verify ĐẠT cả 4 tiêu chí — đo thật trên backend
  production, có bằng chứng DB độc lập cho từng bước** (mục trên)
- ⏳ Minor deferred (7 mục, liệt kê ở "Final whole-branch review" phía
  trên) không chặn merge, để dành đợt sau nếu cần
