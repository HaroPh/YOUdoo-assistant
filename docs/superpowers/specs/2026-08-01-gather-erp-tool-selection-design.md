# Sửa hướng dẫn chọn tool của `gather_erp` — thiết kế

**Mục tiêu:** Sửa đúng nguyên nhân đã xác minh của 2 ca `multi_source` còn
FAIL từ trước SP-2b — `gather_erp` luôn gọi `get_sale_order_detail` (không
có field ngày) thay vì `list_sale_orders` (có `date_order`/`delivery_status`)
khi câu hỏi cần biết ngày/trạng thái giao của một đơn cụ thể. Đồng thời sửa
2 ca `GATHER_CASES` (SP-2c) đang tự gán nhầm khả năng cho tool trong fixture,
khiến bộ đo không thể phát hiện đúng bug này.

**Bối cảnh:** Sau khi SP-2c đóng câu hỏi "supervisor" (§7 spec SP-2b) và kết
luận `gather_erp` đạt 1.0/1.0 trên 4 ca đo, việc đọc lại 2 ca `multi_source`
FAIL (chưa từng đổi từ trước SP-2b) dẫn tới một điều tra trực tiếp: chạy
THẬT `make_gather_erp_node` với tool thật, Odoo thật, trên đúng 2 câu hỏi
đang fail. Kết quả: cả hai lần đều chỉ gọi `get_sale_order_detail(ref=
"S00042")` — tool này (`backend/src/erp_query/sales.py:49`) chỉ trả
`{id, name, partner_id, amount_total, state}` + dòng sản phẩm, KHÔNG có
field ngày. `list_sale_orders(customer="Azure Interior")` (đã gọi thật để
xác nhận) trả về đúng đơn S00042 kèm `date_order: "2026-07-04 16:55:50"`,
`delivery_status: false` — dữ liệu tồn tại, chỉ là model không gọi tool
đúng.

---

## §0. Phạm vi

**Trong phạm vi:**
- Sửa `GATHER_ERP_PROMPT` (`backend/src/agents/prompts.py`) — thêm quy tắc
  chọn tool cho câu hỏi cần ngày/trạng thái giao.
- Sửa 2 case `GATHER_CASES` hiện có (`sla_giao_hang`, `chinh_sach_hoan_hang`)
  — dữ liệu ngày chuyển từ fixture của `get_sale_order_detail` sang
  `list_sale_orders`, `required_tools` đổi theo. Đây không phải case mới —
  là sửa lỗi fixture của case cũ.
- Đo lại `gather` (TRƯỚC/SAU) và `multi_source` (TRƯỚC/SAU) thật.

**Ngoài phạm vi — cố ý:**

| Hạng mục | Vì sao không làm ở đây |
|---|---|
| Sửa mô tả tool dùng chung (`get_sale_order_detail`/`list_sale_orders` trong `erp_query/tools.py`) | Ảnh hưởng mọi nơi dùng 25 tool này, kể cả `erp_read` — chưa ai quan sát thấy `erp_read` mắc lỗi tương tự. Đây là phương án B đã cân và loại lúc brainstorm |
| Thêm tool mới gộp chi tiết + ngày | Đụng business layer `sales.py`, đổi bề mặt tool ở mọi nơi — quá tay cho một field thiếu |
| Cơ chế truy xuất lại (CRAG/retry) | Đã điều tra và loại: retry với cùng logic chọn tool sẽ gọi lại đúng tool sai. Không phải lỗi thiếu vòng, là lỗi hướng dẫn |
| `graph.py`, `fanout.py`'s node wiring, `state.py` | Không cần đụng — đây là sửa prompt + dữ liệu eval, không phải kiến trúc |

---

## §1. Phát hiện thứ hai — fixture `GATHER_CASES` gán nhầm khả năng cho tool

2 case `sla_giao_hang`/`chinh_sach_hoan_hang` (SP-2c) đặt "ngày xác nhận"/
"ngày giao" vào fixture của **`get_sale_order_detail`** — một khả năng
**không có thật**: tool đó không có field ngày trong business layer thật
(`sales.py:49-68`, đã đọc trực tiếp và xác nhận qua gọi Odoo thật). Đây là
lý do `gather` báo `fact_coverage=1.0` cho 2 case này trong khi production
thật fail đúng 2 câu hỏi cùng hình dạng.

**Đây là hạng lỗi thứ ba trong lịch sử eval của dự án này**, khác hai hạng
trước: (1) SP-2a's `eval_intent` lệch hợp đồng đầu ra sau khi production đổi
— sửa bằng dùng chung hàm parse; (2) SP-2c's case S00050 có `required_fact`
rò rỉ từ chính câu hỏi — sửa bằng test tự-nhất-quán "fact không nằm sẵn
trong câu hỏi". Hạng thứ ba này: **fixture tự nhất quán về mặt cú pháp
(fact có mặt trong tool được gán) nhưng gán SAI tool** — tool được chọn để
"có" dữ kiện đó trong đời thực lại không có. Tự-nhất-quán cú pháp không đủ;
phải khớp với khả năng THẬT của tool.

**Hệ quả cho lần sửa này:** phải sửa CẢ HAI — prompt (hành vi thật) và
fixture (bộ đo đo đúng thứ prompt ảnh hưởng). Sửa một mà không sửa hai sẽ để
lại lỗ hổng: chỉ sửa fixture mà không sửa prompt → `gather` tự lộ FAIL đúng
(tốt, nhưng vẫn còn bug production); chỉ sửa prompt mà không sửa fixture →
`gather` tiếp tục mù trước bug này ngay cả khi nó xảy ra lại.

---

## §2. Sửa `GATHER_ERP_PROMPT`

Thêm MỘT gạch đầu dòng vào `Quy tắc:` của `GATHER_ERP_PROMPT`
(`backend/src/agents/prompts.py:148-156`), ngay sau dòng "Chỉ NÊU DỮ KIỆN":

```
- Câu hỏi cần NGÀY (xác nhận, đặt hàng, giao hàng) hoặc TRẠNG THÁI GIAO của
  MỘT đơn bán cụ thể: dùng `list_sale_orders` (lọc theo tên khách hoặc điều
  kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng
  `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG
  có ngày hay trạng thái giao).
```

Không đổi gì khác trong prompt — giữ nguyên cấu trúc, giữ `/no_think` ở
cuối.

---

## §3. Sửa 2 case `GATHER_CASES`

### Case `sla_giao_hang`

Hiện tại (`backend/evals/cases.py:515-521`):

```python
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("get_sale_order_detail",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận) | "
      "ngày xác nhận: 18/07/2026 | ngày giao dự kiến: 20/07/2026 | "
      "loại đơn: thường"}),
```

Sửa thành: dữ liệu ngày chuyển sang fixture của `list_sale_orders` (đúng
tool thật có field này), `required_tools` đổi theo. `get_sale_order_detail`
giữ một fixture RIÊNG, KHÔNG chứa ngày — đúng khả năng thật của nó, để nếu
model vẫn lỡ gọi tool cũ, case vẫn FAIL đúng (không vô tình pass vì
fixture khác lại có sẵn field ngày).

```python
    # sla_giao_hang — SỬA sau điều tra 2026-08-01: dữ liệu ngày chuyển từ
    # get_sale_order_detail (KHÔNG có field ngày thật — sales.py:49-68) sang
    # list_sale_orders (CÓ date_order/delivery_status thật — sales.py:24-39,
    # xác nhận bằng gọi Odoo thật). get_sale_order_detail giữ fixture riêng
    # không có ngày, để nếu model lỡ gọi tool cũ thì case vẫn FAIL đúng.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("list_sale_orders",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận)",
      "list_sale_orders":
      "S00042 | Azure Interior | sale | ngày xác nhận: 18/07/2026 | "
      "ngày giao dự kiến: 20/07/2026"}),
```

### Case `chinh_sach_hoan_hang`

Hiện tại (`backend/evals/cases.py:522-529`):

```python
    # chinh_sach_hoan_hang — cùng hình dạng: chính sách cần "ngày giao thực
    # tế" để tính hạn 30 ngày hoàn hàng.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("get_sale_order_detail",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao) | "
      "ngày giao thực tế: 15/07/2026"}),
```

Sửa cùng khuôn:

```python
    # chinh_sach_hoan_hang — cùng lý do sửa như sla_giao_hang ở trên.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("list_sale_orders",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao)",
      "list_sale_orders":
      "S00042 | Azure Interior | done | ngày giao thực tế: 15/07/2026"}),
```

**Không đổi** 2 case còn lại (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`)
— không liên quan tới bug này.

---

## §4. Trình tự xác minh — TRƯỚC phải thật là FAIL

Khác mọi lần đo trước trong dự án này (nơi số TRƯỚC luôn là số đo trên hành
vi CHƯA sửa, PASS hay FAIL đều ghi nhận): lần này **số TRƯỚC bắt buộc phải
là FAIL** để chứng minh case đã sửa thật sự tái hiện được bug — nếu số TRƯỚC
lỡ PASS (nghĩa là sửa fixture chưa đủ, hoặc giả thuyết sai), phải dừng lại
điều tra tiếp, KHÔNG được sửa prompt trước rồi mới đo.

1. Sửa 2 case `GATHER_CASES` (§3) — CHƯA sửa `GATHER_ERP_PROMPT`.
2. Chạy `--set gather` thật. **Kỳ vọng: cả 2 case sửa đều FAIL**
   (`tool_recall_ok: false` — vì `gather_erp` hiện tại vẫn gọi
   `get_sale_order_detail`). Nếu không FAIL, dừng lại, không sang bước 3.
3. Sửa `GATHER_ERP_PROMPT` (§2).
4. Chạy lại `--set gather` thật. Kỳ vọng: cả 2 case PASS.
5. Chạy `--set multi_source` thật. Kỳ vọng: `both_source_coverage` tăng từ
   0.75 lên cao hơn (lý tưởng 1.0, 8/8) — đây là thước đo cuối cùng, vì đó
   là nơi bug được phát hiện ban đầu (SP-2b's report).
6. Chạy full suite (3 chế độ pytest) để chắc không hồi quy chỗ khác.

---

## §5. "Xong" nghĩa là

1. `GATHER_ERP_PROMPT` có quy tắc chọn tool mới (§2).
2. 2 case `GATHER_CASES` phản ánh đúng khả năng thật của tool (§3), có test
   tự-nhất-quán hiện có (`test_gather_cases_required_facts_exist_in_fixtures`,
   `test_gather_cases_required_tools_are_real_erp_tool_names`) vẫn PASS trên
   dạng mới.
3. Số đo TRƯỚC (2 case FAIL) và SAU (2 case PASS) của `gather` đều ghi vào
   báo cáo — TRƯỚC bắt buộc phải FAIL, không FAIL thì dừng điều tra (§4).
4. `multi_source` đo lại thật, `both_source_coverage` không tệ hơn 0.75 và
   lý tưởng tăng lên (báo cáo trung thực dù có tăng hết hay không).
5. Toàn bộ test xanh cả 3 chế độ.
6. `graph.py`, `fanout.py`, `state.py`, mô tả 25 tool dùng chung — 0 dòng
   thay đổi.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

| Quyết định | File |
|---|---|
| `get_sale_order_detail` không có field ngày thật — quy tắc chọn tool trong `GATHER_ERP_PROMPT` tồn tại vì lý do này, không phải sở thích diễn đạt | `prompts.py`, tại `GATHER_ERP_PROMPT` |
| 2 case `GATHER_CASES` sửa vì fixture cũ gán nhầm khả năng cho tool — không phải case mới | `cases.py`, tại 2 case sửa |
