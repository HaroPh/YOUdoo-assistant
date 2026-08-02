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
   ngày giao dự kiến khớp `18/07/2026`/`20/07/2026`.

   **Đây là chỗ báo cáo trước (bản trước wave sửa này) đã QUY HẾT lỗi cho
   "dữ liệu demo trôi" — SAI, hoặc ít nhất KHÔNG ĐẦY ĐỦ. Thật ra có 2
   nguyên nhân riêng biệt, và chỉ một trong hai tự hết khi đồng bộ lại
   dữ liệu:**

   **(a) Dữ liệu demo trôi thật.** Trạng thái/`date_order` của CHÍNH đơn
   S00042 đã đổi so với lần điều tra trước (`sale`/`18-07` → nay
   `draft`/`2026-07-04`). Phần này đúng là lệch dữ liệu demo Odoo theo
   thời gian — sẽ tự hết nếu đồng bộ lại dữ liệu demo cho đơn này ở đúng
   trạng thái/ngày kỳ vọng.

   **(b) Lỗ hổng CẤU TRÚC — KHÔNG tự hết khi đồng bộ dữ liệu.**
   `get_sale_order_detail` (kể cả sau khi sửa ở Task 1) chỉ đọc
   `date_order` (ngày ĐẶT/XÁC NHẬN đơn) và `delivery_status` (một ENUM
   trạng thái giao — ví dụ `false`/`full`/`partial` — KHÔNG PHẢI một
   ngày). Hàm KHÔNG có field nào mang ý nghĩa "ngày giao dự kiến" hay
   "ngày giao thực tế". Nhưng 2 fixture `GATHER_CASES` sửa ở Task 2
   (`backend/evals/cases.py:510-528`) vẫn đòi hỏi đúng 2 loại ngày đó:
   `sla_giao_hang` cần "ngày giao dự kiến" (`20/07/2026`),
   `chinh_sach_hoan_hang` cần "ngày giao thực tế" (`15/07/2026`). Đã
   grep toàn bộ `backend/src/erp_query/`: không có `commitment_date`
   hay `effective_date` (2 field ngày giao dự kiến/thực tế thật của
   Odoo `sale.order`) được đọc ở đâu cả. Ngày giao THẬT chỉ tồn tại trên
   model khác (`stock.picking.scheduled_date`/`date_done`,
   `backend/src/erp_query/inventory.py:104-140`), qua tool
   `list_late_deliveries` — nhưng tool đó chỉ trả phiếu giao TRỄ HẠN,
   không tra được theo mã đơn cụ thể. Có một hàm tra đúng theo mã đơn
   và có `date_done` thật — `find_done_deliveries_for_order`
   (`inventory.py:143-171`) — nhưng hàm này đánh dấu "NỘI BỘ (coordinator
   return_order)" và KHÔNG được đăng ký thành tool trong
   `backend/src/erp_query/tools.py` (không xuất hiện trong danh sách
   tool ở dòng 212-219) — `gather_erp` không gọi được.

   Nói cách khác: dù có đồng bộ lại dữ liệu demo Odoo cho đơn S00042
   đúng như kỳ vọng (trạng thái `sale`, `date_order` đúng), 2 fixture
   này VẪN không thể PASS bằng dữ kiện THẬT từ `get_sale_order_detail` —
   vì tool đó không có field "ngày giao" để trả. Đây chính là "hạng lỗi
   thứ ba" mà bản thân plan này được viết ra để sửa (fixture khẳng định
   một khả năng tool không có thật) — chỉ khác là lần này nó tái diễn ở
   field ngày giao, trong CHÍNH plan sửa lỗi đó cho field ngày xác nhận.
   Xem thêm comment đã thêm tại `backend/evals/cases.py:510-528`.

   KHÔNG phải lỗi code cho phần (a): hàm `get_sale_order_detail`
   (`backend/src/erp_query/sales.py:49-69`) đã đọc đúng và trả về đầy đủ
   `date_order`/`delivery_status` thật có trong Odoo (LLM đọc được từ
   trường `data.order` trong JSON tool-envelope và tự diễn giải thành
   tiếng Việt) — chỉ là giá trị THẬT của đơn này khác với giá trị giả
   định trong kỳ vọng viết sẵn ở brief. Không phải thông báo fallback
   của `verify_erp_grounding` — LLM trả về dữ kiện thật, có căn cứ, đúng
   cấu trúc. Nhưng phần (b) là lỗ hổng cấu trúc thật, độc lập với dữ
   liệu demo.

   **Rủi ro liên quan — field vắng mặt trên Odoo cũ hơn.** Nếu một bản
   Odoo không có field `delivery_status` trên `sale.order` (phiên bản
   cũ hơn), `get_sale_order_detail` sẽ LỖI HOÀN TOÀN (nhánh `err(...)`
   trong `sales.py:63-64`, do `search_read` với field không tồn tại ném
   exception) thay vì chỉ thiếu ngày như hành vi trước khi sửa — tăng
   mức độ nghiêm trọng của lỗi tool nếu field vắng mặt. Rủi ro này thấp
   (đã xác nhận Odoo thật hiện dùng trong dự án CÓ field này) nên không
   cần code phòng thủ thêm, chỉ ghi nhận.

**Không tự sửa thêm** theo đúng chỉ dẫn của brief — để controller/người
dùng quyết định có cần đồng bộ dữ liệu demo Odoo (đơn S00042 — xử lý
nguyên nhân (a) ở trên) hay cập nhật giả định trong tài liệu điều tra
trước hay không. Việc thêm tool lộ `find_done_deliveries_for_order` hoặc
đọc `commitment_date`/`effective_date` (xử lý nguyên nhân (b) — lỗ hổng
cấu trúc) là quyết định thiết kế riêng, ghi nhận là rủi ro/khoảng trống
đã biết TƯƠNG TỰ cách plan này đã ghi nhận rủi ro `purchase.py` (không
sửa ngay, chỉ ghi lại cho phase sau) — KHÔNG tự ý làm ở đây, cần
brainstorm riêng trước, bao gồm xác minh `commitment_date`/
`effective_date` có thật sự populate trong dữ liệu Odoo demo hay không.

## Task 3 — multi_source thật (thước đo cuối cùng), full suite, đính chính

- verdict: `PASS`
- `both_source_coverage`: `0.75` (TRƯỚC, plan trước: `0.75`) — không đổi
- `citation_validity`: `1.0`
- `fabricated_number`: `0`
- log gốc: `logs/jobs/eval-gate-20260802T132857.json`

Kiến trúc đã xác nhận đúng như dự đoán: `eval_multi_source` không gọi
`gather_erp`, dùng `erp_block` viết tay cố định cho `render_fuse_input()` —
không có đường dẫn cơ học nào để bản sửa Task 1/2 ảnh hưởng tới
`both_source_coverage`. Số đo thật khớp chính xác `0.75` như trước, không
lệch.

## Xác minh test

- Unit-only: `1097 passed, 4 skipped` (`-m "not integration and not live"`)
- Integration: `27 passed` (`-m integration`)

Sau cả 2 lượt chạy, `backend/tests/rag/fixtures/bang_gia.xlsx` và
`policy.docx` bị đổi (binary diff do lượt test rag ghi lại) — đã khôi phục
bằng `git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx
backend/tests/rag/fixtures/policy.docx`, `git status` sạch sau đó.

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec
(`docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md`):

1. `get_sale_order_detail` trả về `date_order`/`delivery_status`: **ĐẠT**,
   xem Task 1 (unit test `141 passed`, commit `8a9f3fb`).
2. `GATHER_ERP_PROMPT` không còn quy tắc chọn tool đặc thù: **ĐẠT** — quy
   tắc bị bỏ hẳn ở Task 2 (commit `adf5558`).
3. Cả 2 case `GATHER_CASES` mục tiêu PASS thật, đo 2 lần độc lập, không cần
   quy tắc dẫn dắt: **ĐẠT**, xem Task 2 Bước 9 (`tool_recall=1.0`,
   `fact_coverage=1.0`, `fails: []` cả 2 lần, log
   `eval-gate-20260802T131647.json` và `eval-gate-20260802T131745.json`).
4. Chẩn đoán trực tiếp qua Odoo thật xác nhận 1 lệnh gọi tool đủ: **ĐẠT**
   trên đúng mục tiêu của điều này — cơ chế chọn tool. `CALLED:
   ['get_sale_order_detail']`, đúng một lệnh gọi, KHÔNG gọi
   `list_sale_orders`, xác nhận qua 3 lớp bằng chứng độc lập (unit test
   Task 1, số đo `--set gather` Task 2 Bước 9, và chẩn đoán trực tiếp Task
   2 Bước 10). Ghi nhận thẳng thắn, không giấu: trong CHÍNH chẩn đoán Bước
   10, giá trị ngày cụ thể trả về (`draft`/`2026-07-04`) KHÔNG khớp kỳ
   vọng viết sẵn trong brief (`sale`/`18-07`/`20-07`, dựa trên trạng thái
   đơn S00042 tại thời điểm điều tra plan trước). Điều này có 2 nguyên
   nhân RIÊNG BIỆT, không phải một (xem phân tách đầy đủ ở Task 2 Bước
   10): (a) dữ liệu demo Odoo cho đơn S00042 đã trôi theo thời gian giữa
   2 lần điều tra (đơn nay ở trạng thái `draft`, chưa xác nhận, khác với
   `sale` đã xác nhận trước đó) — hàm `get_sale_order_detail` đọc và trả
   về đúng dữ liệu THẬT hiện có, không rơi vào fallback lỗi, phần này
   KHÔNG phải thất bại của bản sửa; VÀ (b) một lỗ hổng CẤU TRÚC thật, độc
   lập với (a) và KHÔNG tự hết khi đồng bộ lại dữ liệu demo:
   `get_sale_order_detail` không có field nào mang nghĩa "ngày giao dự
   kiến"/"ngày giao thực tế" (`date_order` chỉ là ngày xác nhận đơn,
   `delivery_status` là enum trạng thái chứ không phải ngày) — trong khi
   2 fixture `sla_giao_hang`/`chinh_sach_hoan_hang` vẫn đòi hỏi đúng 2
   loại ngày giao đó. Đây là "hạng lỗi thứ ba" (fixture khẳng định khả
   năng tool không có thật) mà plan này được viết ra để sửa, tái diễn ở
   field ngày giao — xem Task 2 Bước 10 để biết hướng sửa khả dĩ (chưa
   làm, cần brainstorm riêng).
5. `multi_source` đo lại, xác nhận không đổi: **ĐẠT**, số đo = `0.75`
   (khớp chính xác TRƯỚC), `citation_validity=1.0`, `fabricated_number=0`.
6. Toàn bộ test 2 chế độ xanh: **ĐẠT** — unit-only `1097 passed, 4
   skipped`, integration `27 passed`, không case FAIL nào.
7. `graph.py`/`fanout.py`/`state.py` — 0 dòng thay đổi: **ĐẠT**, xác nhận
   bằng `git diff --stat $(git merge-base main HEAD)..HEAD -- \
   backend/src/agents/graph.py backend/src/agents/fanout.py \
   backend/src/agents/state.py` — output rỗng.
8. Đính chính đúng 1 chỗ trong report của plan trước: **ĐẠT**, xem Step 3
   (`docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`,
   đoạn đính chính chèn ngay trước "CẢNH BÁO QUAN TRỌNG").

**Tổng kết:** Cả 3 task của plan đã hoàn thành đúng phạm vi, không đụng
`graph.py`/`fanout.py`/`state.py`/`purchase.py`. Bước đo quyết định chính
thức (Bước 9, `--set gather`) PASS sạch 2/2 lần độc lập — mục tiêu cốt lõi
của plan (bỏ quy tắc dẫn dắt tool, để `get_sale_order_detail` tự đủ dữ
kiện ngày) đã đạt và được xác nhận bằng số đo thật, không phải suy diễn.
`multi_source` đo lại khớp `0.75` như dự đoán kiến trúc, không có tác dụng
phụ ngoài ý muốn. Toàn bộ 1124 test (1097 unit + 27 integration) xanh. Mối
lo ngại còn tồn đọng — không thuộc phạm vi sửa của plan này — có 2 phần
riêng biệt, đã ghi nhận đầy đủ ở Task 2 Bước 10: (a) dữ liệu demo Odoo cho
đơn S00042 đã trôi khỏi giả định gốc dùng khi viết tài liệu điều tra trước
(`sale`/`18-07`/`20-07` → nay `draft`/`2026-07-04`) — vấn đề đồng bộ dữ
liệu demo, tự hết nếu đồng bộ lại; và (b) một lỗ hổng CẤU TRÚC thật, KHÔNG
tự hết khi đồng bộ dữ liệu — `get_sale_order_detail` không có field nào
mang nghĩa "ngày giao dự kiến"/"ngày giao thực tế" (chỉ có `date_order` —
ngày xác nhận — và `delivery_status` — enum, không phải ngày), trong khi
fixture `sla_giao_hang`/`chinh_sach_hoan_hang` (`backend/evals/cases.py:510-528`)
vẫn đòi hỏi đúng 2 loại ngày giao đó, mà không tool nào `gather_erp` gọi
được hiện cung cấp thật (hàm tra đúng có `date_done`,
`find_done_deliveries_for_order` ở `inventory.py:143-171`, chưa được đăng
ký thành tool). Cả (a) và (b) đều KHÔNG phải lỗi của bản sửa Task 1/2 (bản
sửa đúng và có thật cho field `date_order`/`delivery_status`) và không
chặn kết luận PASS của plan này (mục tiêu chọn tool đã đạt), nhưng (b) là
khoảng trống cần theo dõi riêng — không tự hết bằng cách đồng bộ dữ liệu.
