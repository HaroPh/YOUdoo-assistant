# Sửa fixture `get_overdue_invoices` trong `GATHER_CASES`

**Ngày:** 2026-08-04
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`GATHER_CASES` (`backend/evals/cases.py`, ca `chinh_sach_thanh_toan`,
tool `get_overdue_invoices`) có fixture text khẳng định:

```
"2 hóa đơn quá hạn:\n"
"  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
"quá hạn 32 ngày | còn 4.200.000\n"
"  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
"quá hạn 20 ngày | còn 1.000.000"
```

`accounting.get_overdue_invoices` (`backend/src/erp_query/accounting.py:35-51`)
chỉ đọc/trả `_FIELDS` (`accounting.py:7-8`: `name`, `partner_id`,
`invoice_date`, `invoice_date_due`, `amount_total`, `amount_residual`,
`payment_state`) — KHÔNG có field số-ngày-quá-hạn nào. Display line thật
(`accounting.py:47-49`):

```python
f"  {r['name']} | {(r['partner_id'] or [0, 'N/A'])[1]} "
f"| đến hạn {r.get('invoice_date_due') or 'N/A'} "
f"| còn {r['amount_residual']:,.0f}"
```

Đây là "hạng lỗi thứ ba" (fixture khẳng định năng lực tool không có) —
phát hiện khi viết plan `2026-08-04-multi-source-gather-eval` (spec §7),
đã SỬA ở fixture song sinh trong `MULTI_SOURCE_GATHER_CASES`
(`cases.py:518-536`, plan đó) nhưng CỐ Ý chưa sửa ở `GATHER_CASES` — cần
một lượt đo riêng để quy trách nhiệm, không trộn vào phép đo của plan khác.
Đã có 2 comment `CẢNH BÁO CHƯA SỬA` tại chỗ (`cases.py:672-684` và cross-
reference trong `MULTI_SOURCE_GATHER_CASES`) chờ đúng plan này.

## 2. Vì sao an toàn để sửa ngay bây giờ

`required_facts` của ca này là `("INV/2026/00030",)` — không chạm chuỗi
"quá hạn N ngày". Cơ chế chấm điểm của `eval_gather`
(`run_eval.py:202-260`, hàm chấm `fact_coverage`) chỉ kiểm
`required_facts` có xuất hiện (case-insensitive) trong `erp_facts` gom
được hay không; `required_tools` chỉ so với `called`. Xoá cụm "quá hạn N
ngày" khỏi fixture text KHÔNG đụng tới bất kỳ điều kiện nào trong hai phép
kiểm đó — về lý thuyết, số đo của ca này không đổi. Đo thật ở Task 1 xác
nhận giả thuyết này, không chỉ tin vào suy luận.

## 3. Quyết định: sửa TỐI THIỂU, không xây guard mới

Chỉ sửa đúng fixture text cho khớp format thật + dọn 2 comment cảnh báo đã
hết hiệu lực. KHÔNG thêm cơ chế canh mới cho lớp "fixture khẳng định field
không tồn tại mà không có nhãn thật để đối chiếu" — nhất quán với quyết
định đã có của dự án về giới hạn scanner số học
(`MULTI_SOURCE_DERIVED_DIGITS`): ghi nhận và sửa thủ công từng trường hợp
cụ thể khi phát hiện, không xây bộ xác minh tổng quát cho một lớp lỗi chưa
đủ tần suất để chứng minh giá trị của cơ chế mới. `_DATE_STATUS_LABELS`
hiện chỉ map nhãn → field CÓ THẬT; "quá hạn N ngày" không có field thật
nào để map tới, nên không thể biểu diễn bằng cơ chế hiện có mà không mở
rộng nó — mở rộng đó là việc của một quyết định riêng, không phải phần
của fix này.

## 4. Nội dung sửa

**`backend/evals/cases.py`:**
1. Fixture text của ca `chinh_sach_thanh_toan`/`get_overdue_invoices`:
   xoá `"quá hạn 32 ngày | "` và `"quá hạn 20 ngày | "` khỏi 2 dòng, giữ
   nguyên mọi phần còn lại (mã hoá đơn, khách hàng, ngày đến hạn, số tiền
   còn lại) — kết quả khớp byte-for-byte với format thật ở §1 và với
   fixture đã sửa trong `MULTI_SOURCE_GATHER_CASES` (cùng 2 hoá đơn, cùng
   số tiền).
2. Xoá comment `CẢNH BÁO CHƯA SỬA` tại `cases.py:672-684`, thay bằng một
   câu ngắn xác nhận đã sửa (đúng khuôn phong cách 2 comment "đã hết hiệu
   lực" mà plan `multi-source-gather-eval` từng viết cho 2 case
   `sla_giao_hang`/`chinh_sach_hoan_hang`).
3. Cập nhật comment cross-reference trong `MULTI_SOURCE_GATHER_CASES`
   (`cases.py:518-528`, câu "Lỗi tương tự VẪN CÒN nguyên trong
   GATHER_CASES — CỐ Ý chưa sửa ở đó") — đổi sang thì hiện tại xác nhận đã
   sửa, tránh tái diễn đúng lớp lỗi "comment tự mô tả sai trạng thái code"
   vừa bị final review của plan trước bắt được.

**Không sửa:** `required_facts`, `required_tools`, `question` của ca này —
giữ nguyên để phép đo trước/sau so sánh được trên đúng một biến.

## 5. Đo thật

Chạy `--set gather` một lượt (Postgres + Odoo + LLM thật) SAU khi sửa, ghi
số đo vào report của plan này, so với baseline đã biết từ SP-2c
(`tool_recall=1.0, fact_coverage=1.0`, 4 case — xem
`docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md` nếu cần đối
chiếu). Kỳ vọng: không đổi (lý do ở §2). Nếu lệch, DỪNG và báo
cáo nguyên nhân — không tự suy diễn là "chắc do model", vì đây đúng loại
giả thuyết plan `multi-source-gather-eval` đã cảnh báo không nên tin mà
không đo.

## 6. File bị chạm

| File | Việc |
|---|---|
| `backend/evals/cases.py` | Sửa fixture text `get_overdue_invoices` trong `GATHER_CASES`; xoá 2 comment cảnh báo đã hết hiệu lực |
| `docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md` (mới) | Số đo `--set gather` trước/sau, xác nhận không hồi quy |

## 7. Tiêu chí hoàn thành

1. `pytest tests/jobs/ -q` xanh (không có test nào phụ thuộc chuỗi "quá
   hạn N ngày" bị xoá — xác nhận bằng cách chạy trước khi sửa để có
   baseline test, không chỉ đọc mã).
2. Chạy thật `--set gather`: `tool_recall`/`fact_coverage` khớp baseline
   SP-2c đã biết (hoặc lệch có giải thích, không phải bị bỏ qua).
3. Không còn comment `CẢNH BÁO CHƯA SỬA` nào trỏ tới defect này trong repo
   (cả 2 vị trí ở §4).
