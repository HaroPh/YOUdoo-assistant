# Sửa ca `bang_gia_chiet_khau` trong `GATHER_CASES` — đổi từ tra chiết khấu sang tra giá niêm yết

**Ngày:** 2026-08-04
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`GATHER_CASES` (`backend/evals/cases.py:720-727`), ca `bang_gia_chiet_khau`,
câu hỏi "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
`required_facts = ("12%",)`, fixture `get_product_price` khẳng định:

```
"Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): "
"2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"
```

`sales.get_product_price` (`backend/src/erp_query/sales.py:73-90`) chỉ đọc
`list_price`, trả đúng format:
`f"Giá {name}: {price:,.0f} (SL {qty:g})."` — KHÔNG có chiết khấu, docstring
nói rõ: pricelist-applied pricing cần ORM method (`_get_contextual_price`)
mà gateway read-only không cho phép. Đây là "hạng lỗi thứ ba" (fixture
khẳng định năng lực tool không có), phát hiện ở spec
`2026-08-04-multi-source-gather-eval-design.md` §7, cố ý chưa sửa từ đó —
chờ đúng plan này.

## 2. Vì sao khó hơn ca `get_overdue_invoices` đã sửa

Ở plan `gather-cases-overdue-invoices-fix` (2026-08-04, cùng ngày),
`required_facts` của ca đó (`"INV/2026/00030"`) KHÔNG đụng tới field bịa
("quá hạn N ngày") — chỉ cần sửa fixture text là xong, số đo không đổi.

Ở ca này, `required_facts = ("12%",)` **CHÍNH LÀ** con số bịa. Không tool
ERP nào trong hệ thống (đã xác nhận qua docstring + kiến trúc gateway
read-only, không phải giả định) có thể trả về % chiết khấu — sửa fixture
text để khớp thật sẽ khiến `required_facts` cũ không bao giờ thoả, ca này
FAIL vĩnh viễn nếu không đổi luôn cả câu hỏi/`required_facts`. Cùng lớp
kết luận với ca `S00042` vừa đóng
(`docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md`
§6): giới hạn năng lực thật, không phải field bị bỏ sót.

## 3. Quyết định: đổi câu hỏi sang tra giá niêm yết, giữ nguyên chuỗi 3-tool

Đổi:
- **Câu hỏi**: "Azure Interior đặt 50 Large Cabinet, giá niêm yết là bao
  nhiêu?" (hỏi giá, không hỏi chiết khấu).
- **`required_facts`**: `("12%",)` → `("2.400.000",)` — giá niêm yết thật.
- **Fixture `get_product_price`**: đổi sang `"Giá Large Cabinet: 2.400.000
  (SL 50)."` — **nguyên văn** đã dùng và đo thật ở ca song sinh trong
  `MULTI_SOURCE_GATHER_CASES` (`cases.py`, ca `bang_gia_chiet_khau` thứ
  nhất, plan `multi-source-gather-eval`) — không phải chữ mới, tái dùng
  văn bản đã kiểm chứng.
- **`required_tools`**: GIỮ NGUYÊN `("find_customer", "find_product",
  "get_product_price")` — vẫn đúng mục đích gốc của ca này ("đo tool_recall
  trên một chuỗi nhiều bước", comment tại `cases.py:706-708`). `partner_id`
  không ảnh hưởng tới giá tính ra, nhưng câu hỏi tự nhiên vẫn cần model tự
  phân giải "Azure Interior" → ID trước khi tra giá — không có gì sai khi
  giữ 3 tool.

**Không đổi tên topic** `bang_gia_chiet_khau` — dùng chung ở
`MULTI_SOURCE_CASES`/`MULTI_SOURCE_GATHER_CASES` cho `fixtures.load_chunks()`;
đổi tên sẽ ảnh hưởng ngoài phạm vi ca này. Thêm 1 comment ghi nhận: trong
`GATHER_CASES` cụ thể, ca này giờ đo TRA GIÁ, không phải TRA CHIẾT KHẤU —
tên topic không khớp hoàn toàn nội dung ca, nhưng đổi tên topic không nằm
trong phạm vi plan này.

**Không sửa các doc/report lịch sử đã trích dẫn defect cũ**
(`2026-08-01-sp2c-gather-eval.md`, `2026-08-04-multi-source-gather-eval*.md`,
`2026-08-04-gather-cases-overdue-invoices-fix*.md`) — giữ nguyên làm biên
bản lịch sử, đúng quy ước dự án đã áp dụng nhất quán (xem
`docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`).

## 4. Kiểm chứng

Đo thật `--set gather` SAU khi sửa: ca `bang_gia_chiet_khau` phải PASS
(`tool_recall` — đủ 3 tool trong `called` — và `fact_coverage` — "2.400.000"
xuất hiện trong `erp_facts` model tổng hợp). 3 ca còn lại
(`sla_giao_hang`, `chinh_sach_hoan_hang`, `chinh_sach_thanh_toan`) không
đổi số đo (không chạm fixture của chúng).

Baseline hiện tại (đo lần gần nhất — Task 1 Step 5 của plan
`gather-cases-overdue-invoices-fix`, cùng ngày): `tool_recall=1.0,
fact_coverage=1.0` trên 4 ca — nhưng đó là 4 ca CŨ (bao gồm ca
`bang_gia_chiet_khau` với `required_facts=("12%",)` thoả nhờ fixture bịa).
Sau khi sửa, đây là phép đo với NỘI DUNG CA khác — không so trực tiếp với
con số cũ dưới danh nghĩa "trước/sau", mà xác nhận ca mới tự nó PASS đúng
nghĩa (giá trị thật, không phải giá trị được fixture "mớm sẵn").

## 5. File bị chạm

| File | Việc |
|---|---|
| `backend/evals/cases.py` | Sửa câu hỏi + `required_facts` + fixture text của ca `bang_gia_chiet_khau` trong `GATHER_CASES`; xoá comment `CẢNH BÁO CHƯA SỬA`, thay bằng comment xác nhận đã sửa |
| `docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix-report.md` (mới) | Số đo `--set gather` thật sau khi sửa |

## 6. Tiêu chí hoàn thành

1. `pytest tests/jobs/ -q` xanh (không có test nào phụ thuộc chuỗi "12%"
   hay câu hỏi cũ bị đổi — xác nhận bằng cách chạy trước khi sửa để có
   baseline, không chỉ đọc mã).
2. Chạy thật `--set gather`: ca `bang_gia_chiet_khau` PASS
   (`tool_recall`/`fact_coverage` đều đạt cho ca này), 3 ca còn lại giữ
   nguyên kết quả như trước khi sửa.
3. Không còn comment `CẢNH BÁO CHƯA SỬA` nào trỏ tới defect
   `get_product_price`/"12%" trong `GATHER_CASES`.
