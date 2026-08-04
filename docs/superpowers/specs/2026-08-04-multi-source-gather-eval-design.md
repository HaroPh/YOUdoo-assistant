# Set eval `multi_source_gather` — nối phép đo tổng hợp với `gather_erp` THẬT

**Ngày:** 2026-08-04
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

`eval_multi_source` (backend/evals/run_eval.py) đo bước TỔNG HỢP của nhánh
`mixed` bằng cách nạp `erp_block` — một chuỗi văn bản VIẾT TAY, đóng băng
trong `MULTI_SOURCE_CASES` — vào vị trí `erp_facts` của `render_fuse_input`.
Nghĩa là nó **chưa từng gọi `gather_erp`**. Hệ quả đã đo được: bốn plan liên
tiếp trong session này (`gather-erp-tool-selection-fix`,
`sale-order-detail-dates`, `gather-cases-contract-test`,
`sale-order-effective-dates`) đều sửa đúng vào năng lực thu thập ERP, và
`both_source_coverage` của `multi_source` **không nhúc nhích** (0.750 trước
và sau) — không phải vì các bản sửa vô dụng, mà vì phép đo mù về mặt kiến
trúc với mọi thay đổi phía ERP.

Đây là lỗ hổng đã được nêu tên ít nhất 3 lần trong session (bao gồm ngay
trong docstring của chính `eval_gather`: *"multi_source đo bước TỔNG HỢP
trên erp_block viết tay, KHÔNG đo được liệu gather_erp thật có lấy đủ field
hay không"*) nhưng chưa lần nào được đóng.

## 2. Chẩn đoán trước khi thiết kế (đã chạy, 2026-08-04)

Chạy pipeline THẬT (`make_gather_erp_node` + tool Odoo thật + `FUSE_PROMPT`)
cho đúng 2 câu hỏi đang fail của `multi_source`:

| Câu hỏi | Tool gather_erp gọi | Kết quả |
|---|---|---|
| `Đơn S00042 có đáp ứng SLA giao hàng không?` | `get_sale_order_detail` | Tool trả ĐÚNG, nhưng S00042 vẫn ở trạng thái `draft`; `commitment_date`/`effective_date`/`delivery_status` đều rỗng trong Odoo demo |
| `Hóa đơn INV/2026/00017 có được hoàn tiền không?` | `list_invoices` | Tool trả ĐÚNG dữ liệu hóa đơn, nhưng câu hỏi cần **loại sản phẩm** (giảm giá/thực phẩm/điện tử) để áp đúng điều khoản; không tool nào trong 25 tool trả về dòng sản phẩm của hóa đơn |

**Kết luận có tính quyết định cho thiết kế:** nối `eval_multi_source` với
`gather_erp` thật sẽ **KHÔNG** làm `both_source_coverage` tăng. Hai ca fail
còn lại có nguyên nhân nằm ngoài phạm vi mọi bản sửa đã làm — một là dữ liệu
demo chết, một là lỗ hổng năng lực chưa từng được đụng tới. Giá trị của việc
nối là **đóng lỗ hổng kiến trúc cho các plan ERP TƯƠNG LAI**, không phải để
chứng minh 4 plan vừa rồi có tác dụng. Thiết kế dưới đây được chọn theo đúng
kết luận đó: ưu tiên rủi ro thấp và tính so sánh được, không ưu tiên "làm
điểm số đẹp lên".

## 3. Quyết định kiến trúc: set MỚI, song song, KHÔNG gate

Thêm set `multi_source_gather` **bên cạnh** `multi_source`, không thay thế.

**Vì sao không thay `erp_block` hẳn trong `eval_multi_source`:** `multi_source`
là một trong 6 set đang GÁC thật (`_gate()` yêu cầu `citation_validity == 1.0`,
`fabricated_number == 0`, `both_source_coverage >= baseline`). Chèn thêm một
tầng LLM (`gather_erp`) vào giữa phép đo vốn chỉ đo `fuse_answer` sẽ làm số
đo dao động vì lý do không liên quan tới thứ gate đang canh, và làm mất
đường so sánh với baseline `baseline-qwen3-8b-multi_source.json`.

**Vì sao set mới không gate:** đúng khuôn `gather` (SP-2c) đã dùng: chưa có
baseline, chưa có ngưỡng tuyệt đối nào được xác nhận → `_gate()` trả `True`
vô điều kiện, chỉ GHI NHẬN; siết ngưỡng sau khi có đủ số đo. Và cùng lý do
với `gather`, set này **bị loại khỏi `--set all`** — để trong `all` sẽ luôn
PASS giả và làm loãng tín hiệu của job hàng đêm.

## 4. Hình dạng dữ liệu

`MULTI_SOURCE_GATHER_CASES` trong `backend/evals/cases.py`:

```
(topic, tool_fixtures, question, doc_fact, erp_fact)
```

Đúng hình dạng `MULTI_SOURCE_CASES` với `erp_block` (chuỗi viết tay) thay
bằng `tool_fixtures` (dict `{tool_name: text}`) — cùng cơ chế đã dùng cho
`GATHER_CASES`. Tool nào không có trong dict thì `_stub_erp_tools` trả
`"Không có dữ liệu liên quan."`.

**8 case, phản chiếu 1-1 `MULTI_SOURCE_CASES`**: cùng `topic`, cùng
`question`, cùng `doc_fact`, cùng `erp_fact`, cùng thứ tự. Chỉ ERP đổi từ
"văn bản viết tay" thành "đầu ra tool giả lập mà `gather_erp` phải tự đi
lấy". Một test chốt cứng điều này (`(topic, question)` của hai danh sách
phải bằng nhau, đúng thứ tự) — nếu không, hai bộ số hết so sánh được và cả
plan này mất lý do tồn tại.

### 4.1 Kỷ luật viết `tool_fixtures`

Kế thừa nguyên vẹn từ `GATHER_CASES` + hướng A đã duyệt ở plan
`gather-cases-contract-test`:

1. Fixture phải mô phỏng đầu ra THẬT của tool đó — dùng đúng những field
   hàm business-layer thật sự đọc, đúng định dạng dòng `display` thật.
2. Không được khẳng định năng lực tool không có (đây chính là "hạng lỗi thứ
   ba" đã tái diễn 4 lần). Contract test mở rộng ở §6 canh việc này.
3. `erp_fact` phải xuất hiện nguyên văn trong `tool_fixtures` **hoặc** trong
   chính `question` (ca `S00050`: mã đơn bán không bao giờ xuất hiện trong
   đầu ra `get_overdue_invoices` thật — nó đến từ câu hỏi).

### 4.2 Khác biệt CÓ CHỦ ĐÍCH so với `erp_block` cũ, phải ghi rõ

Fixture mới mô phỏng đầu ra tool thật, nên đôi khi **giàu hơn** `erp_block`
viết tay. Ví dụ ca `INV/2026/00020`: `erp_block` cũ chỉ nêu `xuất ngày
01/07/2026`, buộc model tự cộng 30 ngày; `list_invoices` thật LUÔN trả kèm
`invoice_date_due`, nên fixture mới có sẵn ngày đến hạn và ca đó dễ hơn.
Đây không phải làm nhẹ đề — đó là tính chất thật của pipeline thật. Ghi
thành comment ngay tại case, để người đọc sau không hiểu nhầm chênh lệch số
đo giữa hai set là do chất lượng model.

## 5. Chấm điểm — tách helper dùng chung

Đoạn chấm điểm trong `eval_multi_source` (run_eval.py:612-639) có lịch sử
lỗi riêng đáng kể (`allowed` từng dựng sai basis, đã sửa;
`MULTI_SOURCE_DERIVED_DIGITS` ra đời từ 2 lần gate fail thật). Chép lại nó
sang hàm thứ hai là mời lỗi. Tách thành helper thuần:

```python
def _score_fusion(body, chunks, erp_text, doc_fact, erp_fact,
                  topic, question, allowed_extra_text="") -> dict
```

trả `{"both", "citation_ok", "fabricated"}`. Cả hai eval gọi nó.

- `eval_multi_source` truyền `erp_text=erp_block`, `allowed_extra_text=""`
  → **hành vi không đổi một byte nào**. Đây là ràng buộc cứng: set này đang
  gác thật.
- `eval_multi_source_gather` truyền `erp_text` = ghép mọi giá trị trong
  `tool_fixtures` (**không phải** `erp_facts` model sinh ra —
  `tool_fixtures` là sự thật gốc, nên nếu `gather_erp` bịa số và
  `fuse_answer` chép lại thì vẫn bị bắt; lấy `erp_facts` làm basis sẽ tự
  hợp thức hóa số bịa của chính tầng gather), và
  `allowed_extra_text=question`.

**Vì sao `allowed_extra_text=question` chỉ áp cho set mới:** số xuất hiện
nguyên văn trong câu hỏi người dùng thì model chép lại không thể gọi là
"bịa". `erp_block` viết tay xưa nay vẫn nhắc lại số của câu hỏi nên
`eval_multi_source` không cần điều này; đầu ra tool thật thì không (ca
`S00050`: `get_overdue_invoices` trả hóa đơn, không trả mã đơn bán). Áp
riêng cho set mới giữ nguyên công thức của set đang gác — đúng nguyên tắc
"không đụng vào phép đo đang tin cậy".

`MULTI_SOURCE_DERIVED_DIGITS` dùng CHUNG, không nhân bản — nó khoá theo
`(topic, question)` và hai danh sách case có cùng cặp đó (§4).

Kết quả trả về giữ nguyên bộ khoá của `eval_multi_source`
(`both_source_coverage`, `citation_validity`, `fabricated_number`,
`lat_p50/p95`, `fails`, `errors`) cộng `set: "multi_source_gather"`. Mỗi bản
ghi trong `fails` thêm `called` (danh sách tool `gather_erp` đã gọi) — không
có nó thì một ca fail không phân biệt được "chọn sai tool" với "tổng hợp
kém", và đó là câu hỏi đầu tiên người đọc báo cáo sẽ hỏi.

## 6. Mở rộng contract test

`test_gather_cases_fixture_labels_match_real_tool_fields`
(backend/tests/jobs/test_eval_gather.py) hiện chỉ quét `GATHER_CASES`. Mở
rộng để quét CẢ hai danh sách, tái dùng nguyên máy móc đã có
(`_real_fields_for_tool`, `_DATE_STATUS_LABELS`, `_KNOWN_GAPS`,
`_RecordingTransport`) — không xây cơ chế mới.

Ba thay đổi bắt buộc:

1. **Khoá `_KNOWN_GAPS` thành 4-tuple** `(set_name, topic, tool_name, label)`.
   Topic trùng nhau giữa hai danh sách (`sla_giao_hang` có ở cả hai), khoá
   3-tuple sẽ nhập nhằng. `_KNOWN_GAPS` đang RỖNG nên không có migration —
   chỉ đổi hình dạng khoá và mục giả trong test canh
   (`test_known_gaps_catches_entry_when_real_field_now_exists`).
2. **Thêm nhánh `_real_fields_for_tool`** cho `list_invoices` và
   `list_late_deliveries` (2 tool mới xuất hiện trong fixture). Hàm hiện
   `raise KeyError` cho tool chưa biết — cố ý, và sẽ nổ đúng lúc nếu quên.
   `list_late_deliveries` cần thêm dòng mẫu `stock.picking` vào
   `_REPRESENTATIVE_ROWS` (`scheduled_date` phải là chuỗi — formatter thật
   cắt `[:10]`).
3. **Thêm 2 nhãn vào `_DATE_STATUS_LABELS`**: `"ngày hóa đơn"` →
   `("invoice_date",)`, `"đến hạn"` → `("invoice_date_due",)`. Cả hai được
   fixture mới dùng thật; `"đến hạn"` phủ luôn fixture
   `get_overdue_invoices` sẵn có trong `GATHER_CASES` (hiện không nhãn nào
   chạm tới).

Phụ lợi đã tính trước: fixture ca 1 dùng nhãn `"trạng thái giao"` — nhãn
này nằm trong `_DATE_STATUS_LABELS` từ plan trước nhưng **chưa fixture nào
chạm tới** (đã ghi nhận là cấu hình chết, hoãn lại). Plan này khai tử tình
trạng đó mà không cần cơ chế mới.

## 7. Phát hiện phụ (KHÔNG sửa trong plan này)

Khi đối chiếu fixture `get_product_price` để viết ca 7, phát hiện fixture
`GATHER_CASES` hiện có khẳng định:

> `"Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): 2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"`

`sales.get_product_price` (sales.py:73-90) có docstring nói rõ ngược lại:
nó chỉ đọc `list_price` (giá niêm yết), **không** áp pricelist/chiết khấu,
vì pricelist cần ORM method mà gateway read-only không cho phép. Đây là
**đúng hạng lỗi thứ ba đã tái diễn 4 lần**, ở một tool mà contract test
chưa phủ (nhãn hiện tại chỉ về ngày/trạng thái, không về giá/chiết khấu).

**Cố ý không sửa ở đây:** `required_facts` của ca đó là `("12%",)`; sửa
fixture sẽ đổi số đo của set `gather` và cần một lượt đo riêng để biết ảnh
hưởng. Trộn vào plan này sẽ làm hai phép đo đổi cùng lúc, không quy trách
nhiệm được. Fixture ca 7 của set MỚI viết trung thực (chỉ giá niêm yết +
khách hàng; phần trăm chiết khấu đến từ tài liệu, đúng phân công nguồn), và
thêm một comment cảnh báo tại `GATHER_CASES` trỏ về mục này.

## 8. Dọn dẹp đi kèm

Hai comment "CẢNH BÁO" tại `GATHER_CASES` (cases.py, ca `sla_giao_hang` và
`chinh_sach_hoan_hang`) khẳng định *"không tool nào gather_erp gọi được thật
sự trả về"* ngày giao dự kiến/thực tế — **đã SAI** từ khi plan
`sale-order-effective-dates` merge (`get_sale_order_detail` nay đọc
`commitment_date`/`effective_date` thật). Plan này viết fixture mới cho đúng
hai topic đó nên sửa luôn hai comment cho khớp thực tế, đúng như ghi chú
"việc đầu tiên cho ai chạm vào `GATHER_CASES` tiếp theo".

## 9. File bị chạm

| File | Việc |
|---|---|
| `backend/evals/cases.py` | Thêm `MULTI_SOURCE_GATHER_CASES` (8 ca); sửa 2 comment CẢNH BÁO lỗi thời; thêm comment cảnh báo `get_product_price` (§7) |
| `backend/evals/run_eval.py` | Tách `_score_fusion`; `eval_multi_source` gọi helper (hành vi giữ nguyên); thêm `eval_multi_source_gather` |
| `backend/jobs/eval_gate.py` | Đăng ký set mới vào `EVAL_FN`/`ROLE_FOR_SET`/`choices`; `_gate()` trả True; loại khỏi `--set all`; nhánh in báo cáo cho `base is None` |
| `backend/tests/jobs/test_eval_gather.py` | Mở rộng contract test sang danh sách mới; khoá 4-tuple; 2 nhánh `_real_fields_for_tool`; dòng mẫu `stock.picking`; 2 nhãn mới |
| `backend/tests/jobs/test_eval_multi_source_gather.py` (mới) | Test tự-nhất-quán cho danh sách mới, test parity `(topic, question)`, test `_score_fusion` giữ nguyên hành vi, test đăng ký eval_gate |

## 10. Tiêu chí hoàn thành

1. `pytest` toàn bộ (unit + integration) xanh.
2. `_score_fusion` chứng minh được giữ nguyên hành vi `eval_multi_source`:
   test so kết quả helper với công thức cũ chép nguyên văn trên cùng đầu vào.
3. Chạy thật `--set multi_source` một lượt: `both_source_coverage` vẫn
   0.750, gate PASS — set đang gác không đổi.
4. Chạy thật `--set multi_source_gather` một lượt, ghi số đo (kể cả `called`
   của mỗi ca fail) vào report của plan. Số này là ĐƯỜNG CƠ SỞ đầu tiên,
   không phải mục tiêu phải đạt — kết luận §2 đã nói trước rằng nó có thể
   thấp hơn `multi_source`, và điều đó là thông tin đúng chứ không phải hồi
   quy.
