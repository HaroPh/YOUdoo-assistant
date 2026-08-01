# SP-2c — báo cáo số đo bước thu thập ERP

Plan: `docs/superpowers/plans/2026-08-01-sp2c-gather-eval.md`
Spec: `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md`

## Nhánh `base` (production hôm nay — được gate gác)

Chạy qua `jobs run eval-gate --set gather`, model: `gemini-3.1-flash-lite`
(đầu chuỗi `chain_for("fusion")`, role `fusion` — đúng model `gather_erp`
dùng thật trong production).

- verdict: `PASS` — gate trả `True` vô điều kiện ở lượt đầu (không có
  baseline model cũ để so, xem `jobs/eval_gate.py:_gate` nhánh `gather`)
- `tool_recall`: `1.0` (4/4 ca gọi đủ `required_tools`)
- `fact_coverage`: `1.0` (4/4 ca, `erp_facts` chứa đủ mọi `required_facts`
  nguyên văn)
- `lat_p50` / `lat_p95`: `4123` / `20853` ms
- log gốc: `logs/jobs/eval-gate-20260801T163040.json`
- Chi tiết ca FAIL: không có — `fails: []`. Cả 4 case
  (`sla_giao_hang`, `chinh_sach_hoan_hang`, `chinh_sach_thanh_toan`,
  `bang_gia_chiet_khau`) đều đạt cả hai trục.

**Lưu ý về case `chinh_sach_thanh_toan` (bổ sung sau review toàn nhánh, đợt
sửa cuối):** case này ban đầu có `required_fact` là "32 ngày" — chuỗi ĐÃ có
sẵn nguyên văn trong chính câu hỏi (`GATHER_CASES`,
`backend/evals/cases.py`), nghĩa là `fact_coverage=1.0` báo cáo ở trên thực
chất dựa trên 3 case sạch hoàn toàn cộng 1 case mà về lý thuyết có thể đạt
chỉ bằng cách lặp lại câu hỏi, không cần thu thập thật từ tool. Case đã
được sửa (`required_fact` đổi thành `INV/2026/00030`, mã hoá đơn CHỈ xuất
hiện trong dữ liệu tool) — nhưng LƯỢT ĐO GỐC được báo cáo ở đây (log
`logs/jobs/eval-gate-20260801T163040.json`) dùng phiên bản case CŨ, rò rỉ;
các con số phía trên KHÔNG được chạy lại và giữ nguyên làm biên bản lịch
sử. Đồng thời, fixture của tool `get_overdue_invoices` trong case này ban
đầu tự mâu thuẫn — dòng tiêu đề ghi "3 hóa đơn quá hạn" trong khi chỉ liệt
kê 2 dòng dữ liệu — cũng đã được sửa. Sự tự-mâu-thuẫn này là một lời giải
thích thay thế khả dĩ (chưa loại trừ) cho ca FAIL duy nhất của nhánh
`policy` mô tả bên dưới: `verify_erp_grounding` có thể đã phản ứng với sự
bất nhất nội bộ của dữ liệu fixture, chứ không nhất thiết chỉ vì prompt dài
hơn như phần `## Kết luận` hiện đang quy kết. Ghi nhận đây là một khả năng
chưa loại trừ — không khẳng định đã xác định được nguyên nhân đúng, vì việc
đó cần chạy lại phép đo, ngoài phạm vi của đợt sửa này.

## Nhánh `policy` (có ghép chính sách vào prompt — chỉ ghi nhận, không gate)

Chạy trực tiếp `eval_gather(..., branch="policy")` qua script chẩn đoán
một lần (không commit), cùng model `gemini-3.1-flash-lite` (cùng
`chain_for("fusion")[0]`, `run_eval._llm(spec.alias, role="fusion")` —
khớp đúng cách job CLI resolve role cho set `gather`).

- `tool_recall`: `1.0` (hiệu số so `base`: `+0.0` — không đổi, 4/4 ca vẫn
  gọi đủ tool bắt buộc)
- `fact_coverage`: `0.75` (hiệu số so `base`: `-0.25` — THẤP HƠN base 25
  điểm phần trăm, không phải cao hơn)
- `lat_p50` / `lat_p95`: `3772` / `12849` ms
- Chi tiết ca còn FAIL (1/4, so với `base` — case này PASS ở `base`):
  - topic `chinh_sach_thanh_toan`, câu hỏi "Đơn S00050 quá hạn thanh toán
    32 ngày, đơn hàng mới của khách này có bị tạm dừng xử lý không?"
  - `required_tools`: `("get_overdue_invoices",)` — ĐÃ được gọi
    (`tool_recall_ok: true`); `called` thực tế: `get_sale_order_detail,
    list_sale_orders, get_overdue_invoices, list_sale_orders,
    list_sale_orders, list_invoices` (model gọi thêm nhiều tool khác,
    không tính lỗi vì `required_tools` là tập con của `called`)
  - `erp_facts` cuối cùng KHÔNG phải dữ kiện — mà là nguyên văn
    `ERP_GROUNDING_FALLBACK_MSG` từ `verify_erp_grounding` (
    `src/agents/erp_grounding.py`): "Xin lỗi, tôi không chắc chắn về độ
    chính xác của câu trả lời này. Vui lòng kiểm tra lại trực tiếp trên hệ
    thống hoặc hỏi lại cụ thể hơn." — nghĩa là model ĐÃ lấy đủ dữ kiện
    (tool trả về đúng "quá hạn 32 ngày"), nhưng bước verify-chống-bịa sau
    đó (cùng cơ chế dùng ở cả hai nhánh, `verify_erp_grounding`) phán câu
    trả lời cuối MÂU THUẪN với dữ liệu tool và THAY TOÀN BỘ câu trả lời
    bằng thông điệp an toàn — xoá luôn con số "32 ngày" khỏi output nên
    `fact_coverage_ok = false`.
  - Đây KHÔNG phải lỗi thu thập (`gather_erp`/logic tool) mà là một ca
    verify-chống-bịa nhạy hơn khi prompt dài hơn (thêm khối "CHÍNH SÁCH
    LIÊN QUAN") — bản thân cơ chế `verify_erp_grounding` áp dụng giống hệt
    ở `base` (`fanout.py:make_gather_erp_node`) nhưng không kích hoạt ở
    case nào của `base`.

## Kết luận

**`fact_coverage` nhánh `base` đã cao (gần 1.0 — thực tế đúng 1.0)**, nên
áp dụng nhánh kết luận thứ nhất của template: giả thuyết "gather_erp không
thấy chính sách nên lấy thiếu field" **SAI**. Với 4 ca đo được thiết kế mô
phỏng đúng hình dạng 2 ca FAIL còn lại của `multi_source` (`sla_giao_hang`,
`chinh_sach_hoan_hang` tái dùng đúng fixture chính sách), `gather_erp` THẬT
(node thật, chưa đổi gì) đã lấy đủ và truyền đạt đủ field cần thiết ở cả
4/4 case — kể cả những case đòi hỏi chuỗi nhiều tool
(`bang_gia_chiet_khau`, 3 tool nối tiếp) hoặc dữ kiện nằm giữa nhiều dòng
dữ liệu khác (`chinh_sach_thanh_toan`, `32 ngày` giữa 3 hoá đơn quá hạn).

Do đó: **không đề xuất SP-2d theo hướng tuần tự hoá fan-out** (ghép chính
sách vào prompt của `gather_erp` trước khi gọi). 2 ca FAIL còn lại của
`multi_source` không phải do bước thu thập ERP thiếu field — nguyên nhân
thật (nếu có) nằm ở chỗ khác (có thể ở bước tổng hợp `fuse_answer`, hoặc ở
chính hai case đó), ngoài phạm vi đo của SP-2c.

**Một điểm đáng chú ý, ngoài dự kiến của giả thuyết ban đầu:** nhánh
`policy` không những không cải thiện `fact_coverage` mà còn THẤP HƠN `base`
25 điểm phần trăm (1 ca tụt từ PASS sang FAIL) — đúng cơ chế mô tả ở trên
(`verify_erp_grounding` phán mâu thuẫn và xoá câu trả lời khi prompt dài
hơn/có thêm khối chính sách). Đây là quan sát bên lề (n=4, một lần chạy,
một model — không đủ để kết luận "ghép chính sách vào prompt của
`gather_erp` có hại"), nhưng nó củng cố thêm — theo hướng ngược với giả
thuyết ban đầu — rằng thêm chính sách vào prompt của bước thu thập không
phải hướng cải thiện rõ ràng, và có thể có tác dụng phụ không lường trước
lên bước verify-chống-bịa hạ nguồn. Không đề xuất theo đuổi hướng này thêm
dựa trên 1 lần đo — nếu muốn xác nhận, cần lặp lại với cỡ mẫu lớn hơn,
ngoài phạm vi SP-2c.
