# Báo cáo — sửa lỗ hổng tra cứu trung gian (get_sale_order_detail có ngày)

Plan: `docs/superpowers/plans/2026-08-02-sale-order-detail-dates.md`
Spec: `docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md`

## Task 1 — get_sale_order_detail đọc thêm date_order/delivery_status

Unit test: `141 passed` (`tests/erp_query/`). Commit: `8a9f3fb`.

## Task 2 — Bỏ quy tắc GATHER_ERP_PROMPT, sửa fixture, đo THẬT

### Bước 9 — đo `--set gather` (bước quyết định)

- Lần 1: `tool_recall`: `1.0`, `fact_coverage`: `1.0`, log:
  `logs/jobs/eval-gate-20260802T131647.json`
- Lần 2 (tái lập): `tool_recall`: `1.0`, `fact_coverage`: `1.0`, log:
  `logs/jobs/eval-gate-20260802T131745.json`
- Case `sla_giao_hang`: `PASS` cả 2 lần — nằm trong tập 4 case của
  `--set gather` ("fails": [] cả 2 lần chạy, gate tổng "gather": PASS).
  Không có breakdown per-case riêng trong log job (chỉ log tổng hợp
  `tool_recall`/`fact_coverage`/`fails` toàn bộ set), nhưng `fails: []`
  xác nhận KHÔNG case nào trong 4 case (kể cả `sla_giao_hang`) thất bại
  tool_recall hay fact_coverage.
- Case `chinh_sach_hoan_hang`: `PASS` cả 2 lần — cùng bằng chứng như trên
  (`fails: []` bao gồm cả 4 case, không case nào bị liệt kê).

**Kết luận Bước 9:** CẢ 4 case PASS 2/2 lần đo (`tool_recall=1.0`,
`fact_coverage=1.0`, `fails: []` ở cả hai log) — `sla_giao_hang` và
`chinh_sach_hoan_hang` PASS MÀ KHÔNG CẦN quy tắc dẫn dắt tool nào trong
`GATHER_ERP_PROMPT` (đã bỏ hẳn ở Bước 2). Tiếp tục Bước 10.

Ghi chú hạ tầng: lần chạy đầu tiên gặp lỗi kết nối Postgres
(`localhost:5434` timeout) vì Docker Desktop chưa khởi động trên máy —
đã khởi động Docker Desktop, container `youdoo-postgres` tự phục hồi
(restart policy, "healthy" sau ~20s), sau đó job chạy bình thường. Không
liên quan tới thay đổi code của Task 2.

### Bước 10 — chẩn đoán trực tiếp qua Odoo thật (bypass MCP)

- `CALLED`: `['get_sale_order_detail']` — đúng một lệnh gọi duy nhất,
  KHÔNG gọi `list_sale_orders`.
- `ERP_FACTS` (nguyên văn):
  ```
  Dữ kiện về đơn hàng S00042:
  *   Ngày đặt hàng: 2026-07-04 16:55:50
  *   Trạng thái đơn hàng: Nháp (draft)
  *   Trạng thái giao hàng: Chưa giao (delivery_status: false)
  ```

**Kết luận Bước 10:** KHÔNG khớp hoàn toàn kỳ vọng — **DONE_WITH_CONCERNS**
(không phải BLOCKED, vì Bước 9 — bộ đo `gather` chính thức — đã PASS 2/2
lần). Phân tách rõ 2 phần của kỳ vọng:

1. **Lựa chọn tool (mục tiêu chính của Task 2): ĐẠT.** Đúng một lệnh gọi
   `get_sale_order_detail`, không cần `list_sale_orders` — xác nhận việc
   bỏ quy tắc dẫn dắt trong `GATHER_ERP_PROMPT` (Bước 2) không làm mất
   khả năng trả lời câu hỏi SLA/hoàn hàng bằng một tool duy nhất, đúng
   như mục tiêu của cả plan này.
2. **Giá trị ngày cụ thể: KHÔNG khớp.** Kỳ vọng ban đầu (viết trong brief,
   dựa trên trạng thái đơn S00042 tại thời điểm điều tra trước — xem
   `docs/superpowers/plans/2026-08-01-*` và ghi chú
   "controller live-Odoo verification") là đơn ở trạng thái `sale` (đã
   xác nhận) với ngày xác nhận `18/07/2026` và ngày giao dự kiến
   `20/07/2026`. Gọi Odoo thật (không qua MCP stub) tại thời điểm chạy
   báo cáo này cho thấy đơn S00042 hiện đang ở trạng thái `draft` (Nháp,
   CHƯA xác nhận), `date_order` = `2026-07-04 16:55:50`,
   `delivery_status` = `false` (chưa giao) — không có ngày xác nhận hay
   ngày giao dự kiến khớp `18/07/2026`/`20/07/2026`. Đây là lệch dữ liệu
   THẬT của đơn S00042 trên Odoo hiện tại so với giả định dùng khi viết
   case eval (case eval dùng dữ liệu STUB tổng hợp, không phải dữ liệu
   Odoo thật — đúng theo thiết kế của `--set gather`, xem comment đầu
   `GATHER_CASES` trong `evals/cases.py`). KHÔNG phải lỗi code: hàm
   `get_sale_order_detail` (`backend/src/erp_query/sales.py:49-69`) đã
   đọc đúng và trả về đầy đủ `date_order`/`delivery_status` thật có trong
   Odoo (LLM đọc được từ trường `data.order` trong JSON tool-envelope và
   tự diễn giải thành tiếng Việt) — chỉ là giá trị THẬT của đơn này khác
   với giá trị giả định trong kỳ vọng viết sẵn ở brief.
   Không phải thông báo fallback của `verify_erp_grounding` — LLM trả về
   dữ kiện thật, có căn cứ, đúng cấu trúc.

**Không tự sửa thêm** theo đúng chỉ dẫn của brief — để controller/người
dùng quyết định có cần đồng bộ dữ liệu demo Odoo (đơn S00042) hay cập
nhật giả định trong tài liệu điều tra trước hay không.
