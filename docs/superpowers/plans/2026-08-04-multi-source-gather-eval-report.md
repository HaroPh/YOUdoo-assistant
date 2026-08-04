# Báo cáo — Task 4: mở rộng contract test + đo thật

Plan: `docs/superpowers/plans/2026-08-04-multi-source-gather-eval.md`
Spec: `docs/superpowers/specs/2026-08-04-multi-source-gather-eval-design.md`

## 1. Số đo cả hai set (đo thật, model `gemini-3.1-flash-lite`, role `fusion`)

| Set | both_source_coverage | citation_validity | fabricated_number | gate | log |
|---|---|---|---|---|---|
| `multi_source` | 0.750 (baseline 0.750) | 1.000 | 0 | PASS | `logs/jobs/eval-gate-20260804T120042.json` |
| `multi_source_gather` | 0.750 (không baseline, gác nhẹ) | 1.000 | 1 | PASS | `logs/jobs/eval-gate-20260804T120308.json` |

`both_source_coverage` của `multi_source` giữ nguyên 0.750 — đúng tiêu chí
hoàn thành của Task 1 (refactor `_score_fusion` không đổi hành vi set đang
gác). `multi_source_gather` ra 0.750, **KHÔNG THẤP HƠN** `multi_source` như
dự đoán "rất có thể thấp hơn" của spec §2/brief — nhưng đây vẫn là kết quả
nằm trong phạm vi đã được xác nhận trước là hợp lệ ("thấp hơn HOẶC không đổi
đều là kết quả dự đoán, không phải hồi quy"). Chi tiết đáng chú ý: **2 ca
fail của set mới KHÔNG PHẢI cùng 2 ca fail của `multi_source`** — xem §3.

## 2. So sánh thành phần fail (không được dự đoán trước trong spec, ghi nhận vì minh bạch)

`multi_source` fail ở: (1) `sla_giao_hang`/S00042 (mô hình từ chối trả lời vì
`erp_block` viết tay không có ngày xác nhận/ngày giao), (2)
`chinh_sach_hoan_hang`/INV/2026/00017 (thiếu loại sản phẩm).

`multi_source_gather` fail ở: (1) `sla_giao_hang`/S00042 (cùng câu hỏi,
nhưng gather_erp THẬT lấy được đủ field, nguyên nhân fail khác hẳn — xem
bảng §3), (2) `sla_giao_hang`/WH/OUT/00001 (case này PASS bên
`multi_source`). Ca `chinh_sach_hoan_hang`/INV/2026/00017 — fail bên
`multi_source` — lại PASS bên set mới.

Đây là bằng chứng gián tiếp cho đúng luận điểm nêu ra ở đầu spec: hai set đo
hai thứ khác nhau (tổng hợp trên văn bản tĩnh vs. tổng hợp trên đầu ra thật
của `gather_erp`), nên không chỉ SỐ có thể khác — THÀNH PHẦN case fail cũng
có thể khác, dù tổng tỷ lệ trùng nhau là ngẫu nhiên (8 ca, 2 fail cả hai bên
nhưng khác ca).

## 3. Bảng chi tiết fail của `multi_source_gather` (set MỚI)

| topic | question | called | erp_facts (rút gọn) | both | citation_ok | fabricated | nguyên nhân |
|---|---|---|---|---|---|---|---|
| sla_giao_hang | Đơn S00042 có đáp ứng SLA giao hàng không? | `get_sale_order_detail` | "Ngày giao dự kiến: 20/07/2026; Ngày giao thực tế: 21/07/2026; Trạng thái giao: Đã giao đủ (full)" | false | true | `["01"]` | **tổng hợp kém** |
| sla_giao_hang | Phiếu WH/OUT/00001 có vi phạm SLA không? | `get_sale_order_detail`, `list_late_deliveries` | "Trạng thái: Trễ hạn (assigned); Khách hàng: Azure Interior; Ngày hẹn giao: 18/07/2026" | false | true | `[]` | **tổng hợp kém** |

**Cả hai ca đều là "tổng hợp kém", KHÔNG PHẢI "chọn sai tool"**:

- Ca 1: `called` đúng tool duy nhất mà fixture yêu cầu
  (`get_sale_order_detail`) — thu thập ĐÚNG, đủ field
  (`ngày giao dự kiến`/`ngày giao thực tế`/`trạng thái giao`, đối chiếu qua
  contract test đã mở rộng ở Task 4). `both=false` vì `doc_fact` kỳ vọng
  ("3 ngày" — điều khoản "đơn hàng khẩn cấp xử lý trong 3 ngày") không xuất
  hiện trong câu trả lời: model chọn lập luận theo hướng "trễ 1 ngày → phạt
  0,5%" thay vì đối chiếu với điều khoản 3-ngày. `fabricated=["01"]` là số
  "01" trong cụm "chậm 01 ngày" — đây là kết quả TÍNH TOÁN (hiệu số
  20/07→21/07), không phải chuỗi ký tự có sẵn nguyên văn trong tool_fixtures
  /chunks/câu hỏi, nên bị scanner tính là "bịa". Đây là **giới hạn thiết kế
  đã biết của scanner `_score_fusion`/`_digits`**, cùng lớp với hiện tượng
  đã ghi nhận thủ công trong `MULTI_SOURCE_DERIVED_DIGITS` (cases.py, ca
  INV/2026/00020: model tính đúng ngày dương lịch nhưng bị quy oan là bịa) —
  chỉ khác phép tính (hiệu số ngày thay vì cộng ngày). KHÔNG coi đây là
  hallucination số liệu nghiệp vụ thật.
- Ca 2: `called` gồm đúng tool bắt buộc (`list_late_deliveries`) CỘNG một
  lệnh gọi thừa `get_sale_order_detail` (không có fixture cho topic này nên
  trả "Không có dữ liệu liên quan.") — dò tìm thêm không gây hại, không tính
  là chọn sai tool (cùng khoan dung tool-recall dùng ở set `gather`:
  required_tools là TẬP CON của called). `both=false` vì `doc_fact` kỳ vọng
  ("0,5%" — mức phạt) không xuất hiện; response trích dẫn một điều khoản
  THẬT khác (nghĩa vụ báo trước 48 giờ) thay vì điều khoản phạt theo %.
  `fabricated=[]` — không có số bịa.

## 4. Đầu ra nguyên văn removal probe (Step 10)

```
ok: gỡ get_sale_order_detail.commitment_date → test FAIL đúng như kỳ vọng
ok: gỡ get_sale_order_detail.effective_date → test FAIL đúng như kỳ vọng
ok: gỡ get_sale_order_detail.date_order → test FAIL đúng như kỳ vọng
ok: gỡ get_sale_order_detail.delivery_status → test FAIL đúng như kỳ vọng
ok: gỡ list_invoices.invoice_date → test FAIL đúng như kỳ vọng
ok: gỡ list_invoices.invoice_date_due → test FAIL đúng như kỳ vọng
ok: gỡ get_overdue_invoices.invoice_date_due → test FAIL đúng như kỳ vọng
```

Cả 7 dòng đều `ok:` — không có dòng "KHÔNG BẢO VỆ" nào. Contract test mở
rộng ở Task 4 THỰC SỰ canh được cả 2 nhãn hóa đơn mới lẫn 4 nhãn ngày/trạng
thái cũ trên fixture đã mở rộng, không phải một máy móc chỉ pass vì tình
cờ khớp cấu trúc.

## 5. Những gì CỐ Ý không sửa

- **Fixture `get_product_price` trong `GATHER_CASES`** (`backend/evals/cases.py`,
  ca `bang_gia_chiet_khau`): khẳng định
  `"...đã áp chiết khấu số lượng 12%"`, nhưng `sales.get_product_price`
  (sales.py:73-90) chỉ đọc `list_price` — docstring nói rõ KHÔNG áp
  pricelist/chiết khấu (cần ORM method mà gateway read-only không cho
  phép). Đúng "hạng lỗi thứ ba" (fixture khẳng định năng lực tool không có)
  mà contract test CHƯA phủ (nhãn hiện tại chỉ về ngày/trạng thái, không về
  giá). Đã ghi nhận từ spec §7, KHÔNG sửa trong Task 4: `required_facts`
  của ca đó là `("12%",)` — sửa fixture sẽ đổi số đo của set `gather` (khác
  set đang đo trong plan này) và cần một lượt đo riêng để quy trách nhiệm
  đúng nguyên nhân, tránh trộn 2 thay đổi vào một lần đo.
- **Ca ngày-tháng cần suy luận số học** (`MULTI_SOURCE_DERIVED_DIGITS`,
  cases.py) — giới hạn scanner đã biết từ trước plan này, không mở rộng
  thêm trong Task 4 dù §3 ở trên cho thấy giới hạn tương tự lại xuất hiện ở
  set mới (ca "01" ngày trễ). Không sửa vì đây đúng quyết định "không xây
  bộ xác minh số học tổng quát" đã chốt trước đó (rủi ro
  over-engineering/heuristic mờ) — ghi nhận thủ công từng trường hợp cụ
  thể khi nó xảy ra thật, không suy đoán trước.

## 6. Kết luận theo tiêu chí hoàn thành (spec §10)

1. `pytest` toàn bộ (unit-only, `-m "not integration and not live"`): xanh
   — **ĐẠT**.
2. `_score_fusion` giữ nguyên hành vi `eval_multi_source` (đã xác nhận ở
   Task 1/3, tái xác nhận ở đây qua `both_source_coverage=0.750` không đổi):
   **ĐẠT**.
3. `--set multi_source` một lượt: `both_source_coverage` vẫn 0.750, gate
   PASS: **ĐẠT**.
4. `--set multi_source_gather` một lượt, ghi số đo (kể cả `called` của mỗi
   ca fail) vào report: **ĐẠT** — xem §1, §3.
