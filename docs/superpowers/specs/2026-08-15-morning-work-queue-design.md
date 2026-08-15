# Bản tin việc cần xử lý — thiết kế

**Ngày:** 2026-08-15
**Trạng thái:** đã duyệt, chờ viết implementation plan
**Xuất phát từ:** ADR-012 §2/§3 (P1), sau khi ĐO LẠI làm đổi đề bài

---

## 1. Vì sao P1 của ADR-012 không còn đúng như đã viết

ADR-012 §2 lập luận: *"mọi tool đọc đều là tra cứu theo tên/mã… không persona
nào hỏi được câu quan trọng nhất mỗi sáng"*, và nêu bằng chứng *"có
`validate_picking` để hoàn tất một phiếu kho, nhưng không có gì để xem hàng đợi
94 phiếu đang chờ. Như có nút Gửi mà không có Inbox."*

Đo lại 2026-08-15, **cả hai vế đều đã sai**:

- Đếm trên `backend/src/erp_query/`: có ít nhất **bảy tool liệt kê hàng đợi
  không cần biết trước hỏi gì** — `get_overdue_invoices`, `list_late_deliveries`,
  `list_reorder_needed`, `list_po_mismatches`, `list_manufacturing_orders`,
  `list_sale_orders`, `list_purchase_orders`.
- Nửa `mail.activity` mà ghi chú 2026-08-12 nói "chỉ còn lại nửa này" cũng đã
  xong: `find_my_activities` (MCP) + `close_activity` + `log_activity` tổng quát
  hoá. Vòng tạo → đọc → đóng đã khép.

### Đề bài thật, đo được

Ba phép đo qua đúng đường chat (`POST /v1/chat/completions`, header
`x-openwebui-user-id` mang vai thật), cùng vai kho, cùng thời điểm:

| Cách hỏi | Kết quả |
|---|---|
| "Hôm nay tôi cần xử lý gì?" | *"Không có việc nào được giao cho bạn"* — **3/3 vai** |
| "Có đơn giao hàng nào trễ hạn không?" | **29 phiếu trễ**, đầy đủ, đúng |
| "…hãy tự kiểm tra mọi hàng đợi liên quan tới vai của tôi" | 29 phiếu trễ + **13 hóa đơn quá hạn** + **2 mặt hàng cần đặt** + đối soát PO |

⇒ **Năng lực có đủ. Hỏng nằm ở ĐỊNH TUYẾN Ý ĐỊNH.** Khi nghe "việc cần xử lý",
trợ lý ánh xạ sang trục **quyền sở hữu** (activity giao đích danh) → ra 0 →
dừng → hỏi ngược người dùng.

Thủ phạm là đúng một dòng trong `backend/src/agents/prompts.py`:

```
- Việc được giao: list_my_activities (dùng khi user hỏi "có việc gì chuyển cho
  tôi không", "việc của tôi").
```

Mà trục đó **chính ADR-012 §3 đã chứng minh là sai**: *"91/94 phiếu kho chờ xử
lý KHÔNG có người phụ trách… Trục hữu ích ở kho là thời gian + loại phiếu,
không phải quyền sở hữu."* Tri thức đã nằm trong ADR từ đầu; nó chưa bao giờ đi
vào prompt. Trợ lý đang mắc đúng cái bẫy tài liệu thiết kế của nó cảnh báo.

Hậu quả không nhẹ: **29 phiếu trễ và 13 hóa đơn quá hạn** đang nằm đó, mà câu
hỏi tự nhiên nhất mỗi sáng trả lời "không có việc nào".

---

## 2. Quyết định: không xây tính năng đọc mới

Ba hướng đã cân nhắc:

| | Hướng | Vì sao loại / chọn |
|---|---|---|
| A | Chỉ sửa prompt | Nhỏ nhất, và phép đo chứng minh LLM làm được khi được bảo. Nhưng **số hàng đợi nó quét mỗi lượt là xác suất**, và "còn gì nữa" phó mặc hoàn toàn cho LLM. |
| B | Dựng SOP skill mới | Đúng khuôn có sẵn, không đụng `SYSTEM_PROMPT`. Nhưng **không né được chi phí eval** (skill thêm vào khối worker nối vào prompt router — thứ cổng `intent` đo), và router vẫn phải đề cử được nó từ câu buổi sáng, tức bài toán cũ chỉ dời chỗ. |
| **C** | **Tool tổng hợp phía server + một câu móc trong prompt** | **CHỌN.** |

**Lý do chọn C:** nó biến câu hỏi *không kiểm được* ("LLM có quét đủ cả 5 hàng
đợi không?") thành câu hỏi *cùng loại với mọi tool khác* ("LLM có chọn đúng một
tool không?") — việc hệ này vốn làm tốt (cổng `read` đang 1.000). Và bản tin
trở nên **test được mà không cần gọi LLM**. Phép đo hôm nay chỉ chạy một lần;
không có bằng chứng nào cho lần thứ mười.

---

## 3. Hợp đồng

### Module
`backend/src/erp_query/work_queue.py` — module riêng, vì tính năng **liên bộ
phận theo bản chất** (inventory + accounting + purchase + crm). Nhét vào bất kỳ
file nào trong số đó cũng sai chỗ.

### Hàm
```python
list_pending_work(role: str | None = None) -> dict   # envelope chuẩn
```

`data` có ba khoá, mỗi khoá trả lời một câu hỏi khác nhau:

| khoá | nội dung | phục vụ |
|---|---|---|
| `checked` | mỗi hàng đợi đã kiểm: tên, nhãn tiếng Việt, số việc, bộ phận | bản tin chính |
| `not_checked` | tầng 2 chưa quét | câu **"còn gì nữa không"** |
| `failed` | hàng đợi gọi hỏng + lý do sạch | §5 |

### Hai tầng hàng đợi

**Tầng 1 — bản thân định nghĩa đã là việc tồn đọng** (quét mặc định):

| hàng đợi | bộ phận |
|---|---|
| `list_my_activities` | (đích danh — luôn đứng đầu) |
| `list_late_deliveries` | Kho |
| `get_overdue_invoices` | Kế toán |
| `list_reorder_needed` | Mua hàng |
| `list_po_mismatches` | Mua hàng |

**Tầng 2 — chỉ thành việc khi lọc trạng thái** (giữ trong `not_checked`):
`list_sale_orders(draft)`, `list_purchase_orders(draft)`,
`list_manufacturing_orders(confirmed)`, `list_crm_leads(stage)`,
`find_open_invoices`.

### Xếp thứ tự theo vai
- **Vai → bộ phận: SUY RA, không khai lần hai.** Lấy đa số từ
  `DEPT_OF[t] for t in cfg.own`. Đo thật: kho `{Kho: 9}`, kế toán
  `{Kế toán: 4, Kho: 2}`.
  ⚠️ Hai phiếu "Kho" của vai kế toán là `log_activity`/`close_activity`, mà
  **chính comment trong `roles.py` ghi rõ giá trị đó là TUỲ TIỆN**. Suy theo đa
  số đúng hôm nay nhưng dựa trên một giá trị tuỳ tiện ⇒ **phải ghim bằng test**,
  không thả trôi.
- **Hàng đợi → bộ phận: một bảng 5 dòng, khai tường minh.** `DEPT_OF` chỉ phủ
  tool GHI nên không suy ra được. Đây là **nguồn sự thật thứ hai** — nói thẳng
  ra thay vì giấu — nên nó phải có **test ghim hai chiều** như mọi danh sách
  khai báo khác trong repo này.
- Vai `admin` (`unrestricted`) không suy ra được bộ phận ⇒ giữ thứ tự mặc định.

**Thứ tự chính xác, để không đọc hai nghĩa:** `list_my_activities` **luôn đứng
đầu tuyệt đối** (việc giao đích danh không cần xếp hạng theo bộ phận). Bốn hàng
đợi còn lại xếp sau nó: hàng đợi thuộc bộ phận của vai lên trước, phần còn lại
giữ nguyên thứ tự khai trong bảng. "Vai kho xếp Kho trước" ở §7 nghĩa là *trước
các hàng đợi bộ phận khác*, không phải trước `list_my_activities`.

### Vai được truyền vào bằng đường nào
`build_erp_query_tools(role_cfg=None)` (`backend/src/erp_query/tools.py:63`) đã
nhận `role_cfg` sẵn. Tool wrapper của `list_pending_work` **đóng gói (closure)**
`role_cfg` đó và tự truyền xuống — LLM **không** được nhìn thấy hay tự khai
tham số `role`. Cùng lý do như `_role_from_headers` ở `main.py`: mọi thứ LLM
điền được đều là thứ tự khai được. Chữ ký `list_pending_work(role=...)` là để
test gọi trực tiếp, không phải để mô hình điền.

---

## 4. Ràng buộc cứng: không bao giờ khẳng định đã quét hết

> `display` **không được** nói "không còn việc gì nữa". Nó nói **đã kiểm những
> gì**.

Khi mọi hàng đợi đều rỗng, câu đúng là *"Đã kiểm 5 hàng đợi (…), tất cả đang
trống"* — không phải *"bạn không có việc gì"*.

Khác biệt nghe nhỏ nhưng chính là khác biệt giữa **"không có việc"** và
**"không có việc TÔI BIẾT CÁCH TÌM"**. Sau tầng 2 là hết — không có năng lực tự
đi tìm việc mở. Một bản tin dám nói "hết rồi" là dựng lại đúng con bug ADR-012
tồn tại để chỉ ra, trong một lớp vỏ đẹp hơn.

---

## 5. Xử lý lỗi: phân biệt "rỗng" với "không kiểm được"

Đây là chỗ nguy hiểm nhất của cả tính năng.

Năm hàng đợi gọi độc lập. Một cái hỏng thì:
- **không** làm hỏng cả bản tin — kế toán trục trặc không được che mất 29 phiếu
  kho trễ;
- **không** im lặng bỏ qua;
- **và tuyệt đối không đếm thành 0.**

Vế cuối là bẫy thật: các hàm hàng đợi trả **envelope**, nên hỏng có thể về dưới
dạng `status == "error"` chứ **không** phải exception. Nếu chỉ đọc `data` rồi
`len()`, hàng đợi hỏng trông **giống hệt** hàng đợi rỗng — bản tin nói "không có
việc" trong khi sự thật là "không hỏi được". Đó là đúng con bug tính năng này
sinh ra để diệt, tái sinh bên trong chính nó.

⇒ Bắt **cả hai** dạng (exception lẫn error-envelope) → `failed` → ghi nguyên văn
vào logger (đường log backend đã thật sự hoạt động sau đợt vệ sinh lỗi
2026-08-15) → `display` nêu rõ *"Không kiểm được: đối soát PO."*

---

## 6. Móc vào prompt

Thay đúng dòng `- Việc được giao: …` trong `SYSTEM_PROMPT` bằng hai dòng:

```
- Việc cần xử lý: list_pending_work (khi user hỏi "hôm nay cần xử lý gì",
  "có việc gì không", "còn gì nữa không"). KHÔNG được kết luận "không có
  việc" chỉ từ list_my_activities — đó chỉ là MỘT trong nhiều hàng đợi.
- Việc giao đích danh cho một người: list_my_activities.
```

---

## 7. Đo lường

### Cổng đang có và mức rủi ro

| cổng | n | điểm hiện tại | rủi ro |
|---|---|---|---|
| **`read`** (đo chính `SYSTEM_PROMPT`) | 20 | **1.000 — kín trần** | cao |
| `intent` | 54 | 0.8704 | thấp (không đổi prompt router) |
| `planner` | 25 | 1.000 | thấp |
| `multi_source` | 8 | 0.75 | thấp |

Cổng `read` **không có chỗ để trượt**: một câu chọn nhầm tool là rơi 0.95.

### Rủi ro hai chiều — phải đo cả hai
1. **Thụt:** một trong 20 ca cũ chọn nhầm sang tool mới.
2. **Cướp (hijack):** câu như *"liệt kê đơn bán tháng này"* bị hút về
   `list_pending_work` thay vì `list_sale_orders`.

⇒ Bộ `read` phải **THÊM CA**, không chỉ chạy lại: ca khẳng định câu buổi sáng đi
đúng tool mới, **và** ca chống-cướp khẳng định câu cũ vẫn đi đúng chỗ cũ. Thiếu
nhóm thứ hai thì hành vi mới không được đo.

### Test tất định (không cần LLM)
Giả 5 hàm hàng đợi:
- **hàng đợi hỏng → vào `failed`, KHÔNG đếm thành 0** *(ca quan trọng nhất)*
- tất cả rỗng → `display` nói "đã kiểm 5 hàng đợi", **không** nói "không có việc"
- vai kho xếp Kho trước; vai kế toán xếp Kế toán trước; admin giữ mặc định
- bảng hàng đợi→bộ phận ghim hai chiều
- `not_checked` mang đúng tầng 2

### Nghiệm thu sống có LẶP LẠI
Phép đo hôm nay chạy **đúng một lần** mỗi vai — nó chứng minh hành vi *có thể*
xảy ra, không chứng minh nó *ổn định*. Với LLM, 1/1 và 3/5 nhìn giống hệt nhau
nếu chỉ chạy một lần; mà 3/5 nghĩa là hai buổi sáng mỗi tuần người dùng bị báo
"không có việc" trong khi có 29 phiếu trễ.

⇒ **5 lượt × 3 vai = 15 lượt**, qua đúng đường chat thật, ghi tỉ lệ định tuyến.

**Điều kiện trượt cứng, quan trọng hơn tỉ lệ:** bất kỳ lượt nào trả lời "không
có việc" trong khi hàng đợi không rỗng đều là **TRƯỢT**, bất kể 14/15 hay 15/15
— vì đó là tác hại cụ thể đang đi diệt, không phải một con số thống kê.

---

## 8. Ngoài phạm vi

- **Không** xây năng lực "tự đi tìm việc" mở ngoài tầng 1 + tầng 2. Giới hạn đó
  được **nói ra** (§4), không được che.
- **Không** đổi kiến trúc đọc: `read_tools` vẫn là "tất cả" cho mọi vai
  (ADR-012 §7.2 — đường đọc dùng một credential, không qua MCP). Bản tin chỉ
  **xếp thứ tự**, không lọc theo vai.
- **Không** đụng prompt router, planner, hay SOP skill nào.
- **Không** gieo thêm dữ liệu demo để bản tin trông đẹp hơn — lý do đã ghi ở
  ghi chú 2026-08-12: đó là chế tạo bằng chứng cho chính tính năng.
