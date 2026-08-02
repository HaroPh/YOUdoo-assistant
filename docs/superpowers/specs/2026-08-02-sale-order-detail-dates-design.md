# Sửa lỗ hổng tra cứu trung gian — `get_sale_order_detail` có ngày — Design

## Bối cảnh

Plan trước (`docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix.md`,
merged `3d938fb`) sửa `GATHER_ERP_PROMPT` để `gather_erp` chọn `list_sale_orders`
thay vì `get_sale_order_detail` khi câu hỏi cần ngày/trạng thái giao hàng của một
đơn bán cụ thể. Sau khi merge, controller chẩn đoán thêm qua Odoo thật (mục
"Điều tra thêm của controller" trong report của plan đó) và phát hiện: quy tắc
này **có thể làm production tệ hơn**, không chỉ "chưa đủ tốt", cho đúng lớp câu
hỏi chỉ nêu MÃ ĐƠN (không kèm tên khách hàng) — ví dụ "Đơn S00042 có đáp ứng SLA
giao hàng không?".

Nguyên nhân gốc (đã xác nhận bằng mã nguồn và đo thật):

- `list_sale_orders` (`backend/src/erp_query/sales.py:24-46`) chỉ lọc theo
  `state`/`customer`/`date_from`/`date_to` — **không có tham số tìm theo mã đơn**.
- `_reject_ref_shaped_partner_names` (`backend/src/erp_query/tools.py`) chặn cứng
  khi gọi `list_sale_orders(customer="S00042")` (dạng giống mã đơn bị coi là tên
  khách hàng sai).
- `get_sale_order_detail(ref)` (`sales.py:49-68`) là đường DUY NHẤT tra mã đơn →
  tên khách hàng, nhưng quy tắc prompt vừa thêm lại bảo model "KHÔNG dùng
  `get_sale_order_detail` cho việc này".
- Kết quả quan sát: model gọi `list_sale_orders()` không lọc được gì (trang mặc
  định không chứa đơn cũ như S00042), thử `list_sale_orders(customer="S00042")`
  bị chặn, bỏ cuộc → `verify_erp_grounding` thay toàn bộ câu trả lời bằng thông
  báo fallback (0 dữ kiện). TRƯỚC bản sửa, ít nhất còn lấy được tên khách
  hàng/trạng thái/tổng tiền (thiếu ngày) — SAU bản sửa, không còn gì.
- Bộ đo `gather` (SP-2c) không phát hiện được vì `_stub_erp_tools` trả cố định
  fixture text bất kể tham số gọi tool là gì — đo được "gọi đúng TÊN tool",
  không đo được "có xây được đúng THAM SỐ tìm kiếm hay không".

Người dùng đã xem finding này và chọn đóng plan trước như đã có (không tự sửa
thêm), để lỗ hổng này cho một phase sau. Đây là phase đó.

## Phạm vi

**Chỉ đơn bán** (`sales.py`). `get_purchase_order_detail`
(`backend/src/erp_query/purchase.py:35-54`) có CÙNG hình dạng lỗi (thiếu
`date_order`, `list_purchase_orders` có) nhưng **chưa từng đo được lỗi thật xảy
ra ở đó** — không sửa theo suy luận tương tự, chỉ ghi nhận là rủi ro đã biết,
cùng hình dạng, cho một điều tra riêng nếu sau này có bằng chứng thật.

**Không đụng** `backend/src/agents/graph.py`, `fanout.py`, `state.py`.

## Kiến trúc

Thay vì tiếp tục dẫn dắt model qua prompt để phối hợp đúng 2 lệnh gọi tool
(`get_sale_order_detail` để lấy tên khách hàng → `list_sale_orders` để lấy
ngày) — một hành vi đã chứng minh mong manh qua 3 vòng đo thật của plan trước —
sửa thẳng lỗ hổng năng lực: `get_sale_order_detail` đã tra chính xác theo mã
đơn (`search_read` với `name = ref`) trên CÙNG model `sale.order` mà
`list_sale_orders` đọc `date_order`/`delivery_status` — hai field này đã chứng
minh đọc được qua cùng gateway. Thêm 2 field đó vào `get_sale_order_detail`.
Một lệnh gọi tool duy nhất khi đó đủ trả lời câu hỏi mã-đơn-kèm-ngày, loại bỏ
hoàn toàn nhu cầu phối hợp nhiều tool.

**Thay đổi cụ thể:**

1. `backend/src/erp_query/sales.py::get_sale_order_detail` — thêm
   `"date_order"`, `"delivery_status"` vào danh sách field đọc từ `sale.order`
   (dòng 52-53 hiện tại: `["id", "name", "partner_id", "amount_total",
   "state"]`). **Chỉ cần vậy là đủ** để model thấy được 2 field này —
   `tools.py::_json()` (dòng 12-13) dump NGUYÊN VẸN envelope (`data.order...`)
   thành JSON cho model đọc trực tiếp, không qua văn bản `message`/`body`
   dạng prose. Xác nhận bằng chính tiền lệ `list_sale_orders`: nó CŨNG không
   đưa `date_order`/`delivery_status` vào dòng prose (`lines`, dòng 43-44) —
   2 field đó chỉ nằm trong `rows` (structured), và model vẫn đọc được qua
   JSON như đã thấy ở chẩn đoán Odoo thật trước đây. Không cần sửa
   `body`/dòng prose của `get_sale_order_detail` (dòng 64-68) — giữ nguyên,
   đúng tiền lệ của tool song sinh.

2. `backend/src/erp_query/tools.py` — sửa docstring tool `get_sale_order_detail`
   (dòng 88-90 hiện tại: `"""Chi tiết dòng sản phẩm của một đơn bán theo mã (vd
   S00042)."""`) để nói rõ giờ có ngày/trạng thái giao, không chỉ dòng sản
   phẩm.

3. `backend/src/agents/prompts.py::GATHER_ERP_PROMPT` — **bỏ hẳn** gạch đầu
   dòng đã thêm ở plan trước (dòng 152, bản Bước 2c: "Câu hỏi hỏi về SLA giao
   hàng, chính sách hoàn hàng..."). Lý do bỏ hẳn thay vì sửa lại: quy tắc đó có
   2 phần — (a) đẩy model dùng `list_sale_orders` thay vì `get_sale_order_detail`
   khi cần ngày (hết cần thiết một khi `get_sale_order_detail` tự nó có ngày);
   (b) câu loại trừ cho thanh toán/hoá đơn (chỉ tồn tại để vá tác dụng phụ do
   chính phần (a) gây ra — hồi quy `chinh_sach_thanh_toan` ở vòng 2 plan
   trước). Bỏ (a) thì (b) cũng mất lý do tồn tại. Hành vi mặc định đã quan sát
   nhiều lần (model luôn thử `get_sale_order_detail` trước khi có mã đơn) giờ
   sẽ tự động đúng, không cần dẫn dắt.

4. `backend/evals/cases.py::GATHER_CASES` — sửa đúng 2 case `sla_giao_hang`,
   `chinh_sach_hoan_hang` (hiện tại dòng 515-530): đổi `required_tools` từ
   `("list_sale_orders",)` về `("get_sale_order_detail",)`; chuyển dữ liệu ngày
   trong fixture sang `get_sale_order_detail` (khớp khả năng thật MỚI); bỏ
   fixture `list_sale_orders` cho 2 case này (không còn là `required_tools`,
   nhưng model VẪN có thể gọi thêm nếu muốn — `_score_gather`'s tool_recall_ok
   là kiểm tra tập con, gọi thêm tool khác không bị tính lỗi). Không đụng 2
   case còn lại (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`).

5. `backend/tests/agents/test_fanout.py` — xoá
   `test_gather_erp_prompt_has_sla_return_tool_selection_rule` (dòng 52-60,
   thêm ở fix wave cuối plan trước) — test này khẳng định sự tồn tại của quy
   tắc sắp bị bỏ, sẽ tự FAIL nếu không xoá.

## Trình tự triển khai & xác minh

Giữ đúng kỷ luật đã dùng xuyên suốt dự án: sửa theo thứ tự tăng dần rủi ro, đo
thật ở bước quyết định, có nhánh BLOCKED tường minh nếu không đạt kỳ vọng —
không tự ý đoán tiếp.

1. Sửa `sales.py` + `tools.py` trước. Viết/chạy unit test xác nhận field mới
   đọc được qua gateway giả lập, theo đúng mẫu
   `test_get_sale_order_detail_includes_state`
   (`backend/tests/erp_query/test_sales.py:48-63`).
2. Sửa 2 case `GATHER_CASES` cho khớp khả năng thật mới (bước 4 ở trên).
3. Bỏ quy tắc trong `GATHER_ERP_PROMPT`, xoá test guard cũ (bước 3, 5 ở trên).
4. Chạy full unit suite (`pytest -m "not integration and not live"`) — xác
   nhận sạch, không hồi quy.
5. **Bước quyết định**: đo thật `--set gather`. Kỳ vọng: **CẢ HAI case
   `sla_giao_hang`, `chinh_sach_hoan_hang` PASS** (`tool_recall_ok: true`,
   `fact_coverage_ok: true`) **MÀ KHÔNG có quy tắc dẫn dắt nào trong prompt**
   — nghĩa là hành vi mặc định của model (gọi `get_sale_order_detail` khi có
   mã đơn) giờ tự đủ. Nếu MỘT trong hai không đạt: DỪNG LẠI, KHÔNG tự ý thêm
   quy tắc mới hay đoán cách sửa khác — ghi lại chi tiết `called`/`erp_facts`,
   báo cáo BLOCKED cho controller/người dùng quyết định.
6. Nếu đạt: chẩn đoán trực tiếp qua Odoo thật (bypass MCP, gọi thẳng
   `make_gather_erp_node` với `build_erp_query_tools()` thật — đúng phương
   pháp đã dùng 2 lần ở plan trước) cho câu hỏi gốc "Đơn S00042 có đáp ứng SLA
   giao hàng không?" — xác nhận MỘT lệnh gọi `get_sale_order_detail` là đủ,
   trả về đầy đủ dữ kiện bao gồm ngày, KHÔNG rơi vào fallback của
   `verify_erp_grounding`.
7. Đo `--set multi_source` thật lần cuối. **Kỳ vọng KHÔNG đổi** —
   `eval_multi_source` không gọi `gather_erp` (kiến trúc tách rời, xác nhận ở
   Task 3 plan trước, finding A) nên không có đường dẫn cơ học nào để bản sửa
   này ảnh hưởng tới `both_source_coverage`. Đo để nhất quán với kỷ luật
   trước/sau của dự án; report phải nêu rõ lý do không kỳ vọng đổi NGAY từ đầu
   (không lặp lại thiếu sót mà final review plan trước bắt lỗi — báo cáo lần
   trước ban đầu không nói rõ điều này cho tới khi bị flag).
8. Chạy full suite cả 3 chế độ (`unit-only`, `integration`; không có `-m live`
   nào trong phạm vi trừ chẩn đoán thủ công ở bước 6, vốn không phải lệnh
   pytest).

## Dọn dẹp tài liệu

Đính chính **đúng một chỗ cần thiết**: mục "CẢNH BÁO QUAN TRỌNG" +
"Kết luận" trong
`docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`
(dòng 473 trở đi) — mục đó nói theo thì hiện tại ("CÓ KHẢ NĂNG bản sửa làm tệ
hơn... vẫn còn"), sẽ gây hiểu lầm nếu không đính chính là ĐÃ vá, trỏ tới plan
này. Không đụng các file spec/plan/report khác (SP-2c, spec/plan gốc của plan
trước) — đó là văn bản lịch sử ghi lại đúng thời điểm viết, không phải kết
luận "mãi mãi đúng" cần cập nhật theo YAGNI.

## Testing

- `backend/tests/erp_query/test_sales.py` — test mới xác nhận
  `get_sale_order_detail` trả về `date_order`/`delivery_status` khi gateway có
  dữ liệu.
- `backend/tests/erp_query/test_tools.py` (nếu có test mô tả tool) — cập nhật
  nếu có assertion về docstring cũ.
- `backend/tests/jobs/test_eval_gather.py` — các test tự-nhất-quán hiện có
  (`test_gather_cases_required_facts_exist_in_fixtures`,
  `test_gather_cases_required_tools_are_real_erp_tool_names`, v.v.) tự động
  kiểm 2 case sửa vì chúng lặp qua TOÀN BỘ `GATHER_CASES` — không cần viết
  test tự-nhất-quán mới, chỉ cần chạy lại xác nhận xanh.
- `backend/tests/agents/test_fanout.py` — xoá test guard cũ (đã nêu ở trên).
  Không cần test guard mới cho việc "bỏ quy tắc" (không có gì để assert sự
  vắng mặt của một đoạn text một cách có ý nghĩa).

## Xong nghĩa là

1. `get_sale_order_detail` trả về `date_order`/`delivery_status`, xác nhận
   bằng unit test.
2. `GATHER_ERP_PROMPT` không còn quy tắc chọn tool đặc thù cho SLA/hoàn
   hàng/bảo hành/đổi trả (đã bỏ hẳn).
3. Cả 2 case `GATHER_CASES` mục tiêu PASS thật (đo 2 lần độc lập) mà không cần
   quy tắc dẫn dắt — nếu không đạt, plan dừng ở BLOCKED, không có bước "xong"
   giả.
4. Chẩn đoán trực tiếp qua Odoo thật xác nhận 1 lệnh gọi tool đủ trả lời đúng
   câu hỏi S00042/SLA, không rơi vào fallback.
5. `multi_source` đo lại, xác nhận không đổi (đúng kỳ vọng, có giải thích kiến
   trúc trong report).
6. Toàn bộ test 2 chế độ (unit-only, integration) xanh.
7. `graph.py`/`fanout.py`/`state.py` — 0 dòng thay đổi.
8. Đính chính đúng 1 chỗ trong report của plan trước.
