# Báo cáo kết thúc: 2026-08-07-customer-contact-detail

**Trạng thái:** HOÀN THÀNH — merge vào `main`, §Cổng đánh giá live-verify ĐẠT
cả 3 tiêu chí gốc + phát hiện và vá thêm 1 khoảng trống thật lúc live-verify.

**Nhánh:** `customer-contact-detail` (worktree, đã xoá sau merge)

**Ngày hoàn thành:** 2026-08-07

**Spec:** `docs/superpowers/specs/2026-08-07-customer-contact-detail-design.md`
**Plan:** `docs/superpowers/plans/2026-08-07-customer-contact-detail.md`

---

## Tóm tắt

Agent nay có thể tra cứu và **chủ động** nêu email/SĐT của một khách hàng cụ
thể trong câu trả lời — năng lực trước đây chỉ có cho nhà cung cấp
(`get_supplier_detail`).

## Task 1: `get_customer_detail` + `_resolve_single` dùng chung

**Commit:** `94f7657`

Chuyển `_resolve_single` từ private helper của `purchase.py` sang
`erp_query/resolve.py` (dùng chung), thêm `get_customer_detail` mirror
`get_supplier_detail` (không đọc `bank_ids`). Review: spec ✅, quality
Approved, 0 finding — verify độc lập cả 2 call site cũ của
`_resolve_single` không đổi hành vi.

## Task 2: Đăng ký tool

**Commit:** `c4fcaf3`

Review: spec ✅, quality Approved, 0 finding.

## Task 3: Rule chủ động trong `GATHER_ERP_PROMPT`

**Commit:** `91c05f2`

Review: spec ✅, quality Approved, 0 finding.

## Final whole-branch review (model Opus)

**Ready to merge: With fixes.** 4 finding Important:

1. `SYSTEM_PROMPT` (dùng ở node `erp_read`, bind FULL tool set) chưa liệt kê
   `get_customer_detail` — tái tạo bất đối xứng trên một đường prompt khác.
2. Task 2 đổi `build_erp_query_tools()` — đúng input mà
   `evals/run_eval.py --set read` dùng qua `bind_tools`; case
   `cases.py:242` có nguy cơ flip sang `get_customer_detail`.
3. `sales.py` `get_customer_detail` dùng `limit=200` nhưng
   `Gateway.search_read` tự clamp `MAX_LIMIT=100` — literal `200` là dead
   code.
4. Test rule prompt mới chỉ pin mệnh đề HÀNH ĐỘNG, không pin mệnh đề ĐIỀU
   KIỆN kích hoạt ("ĐÚNG MỘT... không phải danh sách nhiều đối tác") — đúng
   phần mang rủi ro nhiễu.

**Fix wave:** commit `2a58f8a`. Finding 1, 3, 4 sửa bằng code + test mới.
Finding 2 xử lý bằng đo thật: chạy trực tiếp
`evals/run_eval.py --set read --model gemma-4-26b` (20 case, không dùng
baseline cũ vì model catalog đã đổi) → `tool_acc=1.0, fails=[]` — case 242
KHÔNG flip. Ruling: rủi ro có căn cứ nhưng không xảy ra thật, không sửa
`cases.py`. Re-review scoped: cả 4 finding ADDRESSED, không breakage mới.

## Sự cố giữa phiên: 2 tab Claude Code trùng nhau

Trong lúc chuẩn bị merge, phát hiện `main` đã bị merge sẵn (fast-forward,
đúng commit `2a58f8a`) và có 2 file sửa **chưa commit** — hoá ra người dùng
lỡ mở 2 tab Claude Code cùng chạy plan này trên cùng một checkout. Tab kia
đã tự đi trước, merge xong, và trong lúc live-verify Task 4 phát hiện thêm
một khoảng trống thật (xem mục dưới) trước khi bị đóng. Người dùng xác nhận
đã đóng tab kia; phiên này tiếp quản, xác minh lại toàn bộ (test suite xanh,
tiến trình backend/mcp-odoo đã được tab kia khởi động lại với code mới —
xác nhận qua PID khác PID phiên này đã khởi động trước đó), rồi commit tiếp.

### Finding phát sinh lúc live-verify: `SYSTEM_PROMPT` cũng cần rule

**Commit:** `c46081d`

Câu hỏi nghiệp vụ đơn giản về MỘT khách hàng cụ thể (vd "công nợ của khách
X là bao nhiêu?") đi qua node `erp_read`/route `route:read` — dùng
`SYSTEM_PROMPT`, KHÔNG qua `gather_erp` (dùng `GATHER_ERP_PROMPT`). Rule
Task 3 thêm chỉ nằm ở `GATHER_ERP_PROMPT`, nên **không bao giờ chạy** trên
đường phổ biến này dù tool `get_customer_detail` đã được bind đầy đủ. Đo
thật (tab trước khi đóng) qua Langfuse trace xác nhận route chỉ có đúng 1
observation "route:read". Vá bằng cách thêm ĐÚNG câu rule đã duyệt vào
`SYSTEM_PROMPT`, kèm 2 test: pin cả câu (học từ finding 4 ở trên) và guard
`/no_think` vẫn là token cuối.

## Kết quả test toàn bộ

```
cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"
```
```
1197 passed, 4 skipped, 46 deselected in 35.47s
```

**Baseline trước plan:** 1185 passed (đo trên `main` sau khi merge
`invoice-confirm-summary`). **Tổng cộng:** +12 test mới (1197 − 1185).

---

## Cổng đánh giá — kết quả thật (controller đo sau merge, 2026-08-07)

Backend đã restart để nạp đúng code mới nhất (kể cả fix `SYSTEM_PROMPT`,
commit `c46081d`) — xác nhận PID tiến trình khác PID đã chạy trước khi có
commit này. Đo qua `POST /v1/chat/completions`, resend toàn bộ lịch sử mỗi
lượt, không `session_id`. Write kill-switch đã sẵn `True` từ trước.

### Tiêu chí 1 — câu hỏi đơn khách hàng cụ thể, có tính nghiệp vụ: ✅ ĐẠT

`"Khách Acme Corporation có đơn hàng nào đang chờ giao không?"` → liệt kê
đúng 11 đơn thật đang chờ giao, **kèm** đúng:
```
Thông tin liên hệ của khách hàng:
- Email: info@agrolait.com
- Điện thoại: (603)-996-3829
```
(khớp dữ liệu thật của Acme Corporation đo trực tiếp qua Odoo).

### Tiêu chí 2 — câu hỏi liệt kê nhiều đối tác, KHÔNG kích hoạt: ✅ ĐẠT

`"Hóa đơn nào quá hạn thanh toán?"` → liệt kê 22 hóa đơn quá hạn từ 4 khách
khác nhau (Acme Corporation, OpenWood, LightsUp, Azure Interior), **không**
tự động kèm bộ contact cho từng khách — chứng minh ngưỡng "đúng một đối
tác" hoạt động đúng, không nhiễu.

### Tiêu chí 3 — nhà cung cấp, chống hồi quy: ✅ ĐẠT

`"Hồ sơ nhà cung cấp Hồng Phúc, thông tin liên lạc thế nào?"` → trả lời
đúng `get_supplier_detail` (nêu đúng po_count=2, báo trung thực dữ liệu
liên lạc thật sự trống trên Odoo cho NCC này — không phải lỗi, là dữ liệu
thật). `get_supplier_detail` không bị phá bởi thay đổi của plan này.

(Lưu ý phương pháp: câu hỏi đầu thử với "Nhà cung cấp Individual Workplace
là ai" bị agent hiểu nhầm "Individual Workplace" — vốn là TÊN SẢN PHẨM —
thành tên đối tác, một vấn đề route sản phẩm↔NCC có sẵn từ trước, không
liên quan tới thay đổi của plan này. Đổi câu hỏi rõ ràng hơn để đo đúng
tiêu chí.)

### Xác nhận bổ sung — fix `SYSTEM_PROMPT` (phát sinh giữa phiên): ✅ ĐẠT

`"Công nợ của khách Azure Interior là bao nhiêu?"` (đi qua route:read,
KHÔNG qua gather_erp) → trả lời **kèm** đầy đủ:
```
Thông tin liên hệ của khách hàng:
- Email: vauxoo@yourcompany.example.com
- Điện thoại: +58 212 681 0538
- Địa chỉ: 4557 De Silva St, Fremont
- Điều khoản thanh toán: End of Following Month
```
Xác nhận trực tiếp: fix `SYSTEM_PROMPT` (commit `c46081d`) đóng đúng
khoảng trống đã phát hiện — đường `route:read` nay cũng chủ động nêu contact
y hệt đường `gather_erp`.

### Kết luận cổng đánh giá

**Cả 3 tiêu chí gốc + 1 xác nhận bổ sung đều ĐẠT — đo thật trên backend
production đã merge, có dữ liệu Odoo thật làm bằng chứng.** Không phần nào
bị revert.

---

## Nhận xét cuối

- ✅ Tất cả 3 task code + final review (1 fix wave, 4 finding đã xử lý) +
  merge vào `main` (fast-forward)
- ✅ Test suite 1197 passed, 4 skipped (không regression)
- ✅ Live-verify phát hiện thêm 1 khoảng trống thật (`SYSTEM_PROMPT` thiếu
  rule) ngoài phạm vi 3 tiêu chí gốc — đã vá và xác nhận lại bằng đo thật,
  đúng tinh thần "tìm lỗi thật lúc live-verify thì sửa ngay" đã có tiền lệ
  trong dự án
- ✅ Sự cố 2 tab trùng nhau được phát hiện SỚM (trước khi commit/push gây
  xung đột), điều tra kỹ trước khi hành động, không ghi đè công việc đang
  dở của tab kia
- ⏳ Minor deferred (7 mục, liệt kê ở final whole-branch review) không chặn
  merge, để dành đợt sau nếu cần
