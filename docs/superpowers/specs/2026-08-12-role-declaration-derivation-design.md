# Thiết kế — suy ra bảng bộ phận, và chốt drift cho bảng quyền (2026-08-12)

**Trạng thái:** đã duyệt, chờ viết plan.
**Nối tiếp:** `2026-08-09-role-based-access-design.md`,
`2026-08-12-mail-role-enforcement-design.md`. Đóng hai việc còn lại của mạch
phân quyền.

## 1. Vấn đề

Cùng một hạng lỗi đã lặp **năm** lần trong mạch này: một danh sách khai bằng
tay trôi lệch khỏi sự thật, âm thầm, trong khi test vẫn xanh. Hai chỗ còn lại
đều thuộc hạng đó.

### 1.1 Hai danh sách cho cùng một sự thật, đã lệch nhau

`_DEPT_OF` (`prompts.py:281`) tự nhận trong docstring là "**NGUỒN SỰ THẬT DUY
NHẤT** cho tool X thuộc bộ phận nào". Nhưng `RoleCfg.other_dept` (`roles.py`)
khai lại cùng thông tin đó dưới dạng tập hợp, từng vai một.

Đo thật (2026-08-12): `_DEPT_OF` thiếu **đúng 3 tool** — `flag_order_for_review`,
`send_delivery_email`, `send_invoice_email`. Cả ba được thêm vào `roles.py` ở
các đợt sau mà không ai cập nhật bảng. Hệ quả là **5 khoảng trống** trên 2
profile:

| Vai | Tool bị `denied` trong khi vai KHÁC sở hữu |
|---|---|
| kho | `create_invoice_from_order`, `create_bill_from_po`, `send_invoice_email` |
| kế toán | `send_delivery_email`, `flag_order_for_review` |

Con số này cũng minh hoạ chính vấn đề: backlog trước đó ghi "3", đo ra 5.

### 1.2 Hai chế độ hỏng KHÁC NHAU, do hai danh sách khác nhau

Đây là chỗ dễ hiểu sai, nên nói rõ. Guard tất định trong `nodes.py:275` xử lý
`OTHER_DEPT` và `DENIED` **y hệt nhau** — cùng nhánh, cùng câu từ chối. Vậy
`other_dept` để làm gì?

- **`other_dept` quyết định lời từ chối có XẢY RA hay không.** Nó là hint trong
  prompt của planner (`prompts.py:248-266`) cho LLM biết tool có tồn tại, để
  planner trả về ĐÚNG tên tool và guard mới có gì để bắt. Thiếu ⇒ LLM không
  biết tool có thật ⇒ trả lời hội thoại lan man, guard không bao giờ chạy.
- **`_DEPT_OF` quyết định lời từ chối NÊU ĐÚNG bộ phận hay rơi về "khác".**

Cả hai đều đã được quan sát trong nghiệm thu sống của đợt trước
(`2026-08-12-mail-role-enforcement-report.md`): kịch bản 3 là chế độ hỏng thứ
hai (nói "bộ phận khác"), kịch bản 4 là chế độ hỏng thứ nhất (không từ chối,
trả lời lan man).

### 1.3 `TOOL_ACCESS_MAP` chép tay từ mã nguồn tool

`scripts/check_role_odoo_consistency.py` giữ một bảng tool → `[(model,
operation)]`, chép tay từ `mcp-servers/odoo/tools/*.py`. Đo ngày 2026-08-12:
**8/18 dòng sai** — 3 dòng sai `operation`, 5 dòng thiếu cặp. Cả hai con số mà
báo cáo phân quyền đưa ra đều dựa trên bảng hỏng này.

## 2. Phạm vi

**Làm:**
1. `DEPT_OF` thành nguồn duy nhất; `other_dept` suy ra (§3)
2. Chốt drift cho `TOOL_ACCESS_MAP`, phạm vi **model** (§4)

**Không làm (ghi nhận):**
- Luồng duyệt (state `X`). Profile `enterprise` xếp `inventory_adjustment` /
  `scrap_product` / `return_order` ra ngoài vai kho nhưng chúng **vẫn thuộc bộ
  phận Kho**, nên câu "không thuộc quyền hạn của bộ phận Kho, vui lòng liên hệ
  bộ phận Kho" đọc vẫn vô lý. Sửa đúng cần một thông điệp khác hẳn ("cần cấp
  trên duyệt"), thuộc vòng duyệt đã hoãn từ ADR-012 §5. Đợt này giữ nguyên hành
  vi đó, không làm xấu thêm.
- Kiểm `operation` tự động trong §4 — xem §4.3 giải thích vì sao không thể.
- Xác thực cho `/v1/chat/completions`.

## 3. `DEPT_OF` — một nguồn thay vì hai

### 3.1 Chuyển nhà

`_DEPT_OF` chuyển từ `prompts.py` sang `roles.py`, đổi tên thành `DEPT_OF`
(công khai). Đây là dữ liệu phân quyền, không phải dữ liệu prompt. `prompts.py`
vốn đã nhận `RoleCfg` làm tham số nên import ngược lại `roles` là đúng chiều,
không tạo vòng. `prompts.dept_of()` giữ nguyên chữ ký để `nodes.py` không đổi;
nó chỉ đọc từ `roles.DEPT_OF`.

Bổ sung 3 mục thiếu:

```python
"send_delivery_email": "Kho",
"send_invoice_email": "Kế toán",
"flag_order_for_review": "Kho",
```

### 3.2 `other_dept` thành thuộc tính suy ra

`RoleCfg.other_dept` từ trường khai tay thành thuộc tính:

```
other_dept = {t for t, d in DEPT_OF.items() if d != self.label}
             - (own | needs_sign_off)
             | other_dept_extra
```

`label` đã sẵn là `"Kho"` / `"Kế toán"`, trùng đúng giá trị trong `DEPT_OF` —
không cần thêm trường cho việc này. Vai admin (`unrestricted=True`) trả tập
rỗng như hiện nay.

Ràng buộc ngầm này (label PHẢI là một giá trị có trong `DEPT_OF`) là điểm yếu
duy nhất của cách làm: gõ sai label thì `other_dept` phình ra âm thầm. §5 có
test ghim nó.

### 3.3 `other_dept_extra` — lối thoát có chủ đích

Trường khai tay MỚI, thay chỗ `other_dept` cũ, nhưng chỉ dùng cho thứ suy diễn
không diễn đạt được: nghiệp vụ **thuộc bộ phận của chính vai này** nhưng bị xếp
ra ngoài vai AI. Hiện chỉ profile `enterprise` cần, đúng 3 mục.

Danh sách khai tay co từ **16 mục xuống 3**. Ba mục còn lại là những mục thật
sự cần con người quyết, không phải chép máy móc.

### 3.4 Hành vi đổi ở đâu

Chỉ đổi **nội dung prompt của planner** (khối hint `other_dept`) và qua đó đổi
chất lượng lời từ chối. **KHÔNG** đổi `allowed_tools()`, nên **không đụng quyền
tài khoản Odoo** — `scripts/odoo_setup_ai_accounts.py` sinh ra đúng cùng một
tập nhóm quyền như trước. Rủi ro giới hạn ở thông điệp.

## 4. Chốt drift cho `TOOL_ACCESS_MAP`

### 4.1 Giữ bảng tường minh, thêm người canh

Comment ở `check_role_odoo_consistency.py:45` ghi rõ đây là "TẬP TƯỜNG MINH,
KHÔNG parser tự động" — lựa chọn có chủ đích. Giữ nguyên lựa chọn đó.

Lý do: một parser trong **production** sai thì đo sai âm thầm; một parser trong
**test** sai thì chỉ gây ồn, không gây im lặng. Bảng cần người canh, nhưng
người canh không nên thay nó ngồi ghế.

### 4.2 Ba kiểm, tất cả ở phạm vi MODEL

1. **Bao phủ tool.** Mọi tool nằm trong `own ∪ needs_sign_off ∪ other_dept` của
   bất kỳ vai nào, ở mọi profile, phải có mặt trong
   `TOOL_ACCESS_MAP ∪ UNMAPPED_TOOLS`. Bắt "thêm tool mới, quên cập nhật bảng".
2. **Khai → có thật.** Mỗi `model` khai cho tool T phải xuất hiện trong một
   lệnh `odoo("<model>", ...)` trong nguồn của T. Bắt model khai nhầm/không tồn
   tại.
3. **Có thật → đã khai.** Mỗi `model` bị GHI trong nguồn của T (lệnh `odoo()`
   với method KHÔNG thuộc nhóm đọc của `ODOO_METHOD_OPERATION_MAP`) phải có mặt
   trong khai báo của T. Bắt **5 dòng thiếu cặp** của lần trước.

Danh sách method đọc lấy từ `ODOO_METHOD_OPERATION_MAP` (`mcp-servers/odoo/
security.py`) — đã tồn tại, không khai lại.

**Không mâu thuẫn với §4.3.** Ở đây bảng chỉ được dùng để phân biệt **đọc hay
ghi**, không dùng để suy ra `operation` nào. Phân biệt đọc/ghi là an toàn:
`read`/`search`/`search_read`/`search_count`/`name_search`/`fields_get`/
`read_group`/`default_get`… không sửa gì, điều đó đúng bất kể ngữ nghĩa quyền.
Thứ KHÔNG an toàn là bước tiếp theo — kết luận một method ghi cần `create` hay
`write` trên chính model đó.

### 4.3 Vì sao KHÔNG kiểm `operation` — điều chỉnh so với ý tưởng ban đầu

Ý tưởng đầu tiên là dùng `ODOO_METHOD_OPERATION_MAP` để kiểm luôn `operation`.
**Sai, và sai theo hướng nguy hiểm.** Bảng đó ánh xạ
`action_create_invoice → "create"`, nên một test dựa vào nó sẽ đòi
`create_bill_from_po` khai `("purchase.order", "create")` — **đúng dòng sai đã
được sửa ngày 2026-08-12**, và đo sống đã bác bỏ (`ai-accounting` có
`purchase.order` write=True, create=False, mà tool vẫn chạy).

Nguyên nhân: bảng đó phân loại "method này gây tác dụng phụ loại gì" phục vụ
**cổng xác nhận**, KHÔNG phải "method này cần quyền Odoo nào trên model nào".
Hai khái niệm khác nhau, và không có cách tĩnh nào suy ra chắc chắn khái niệm
thứ hai — đó chính là lý do bảng được làm tay ngay từ đầu.

Nên `operation` vẫn do người khai. Nhưng sau đợt này nó là thứ **duy nhất**
người phải khai đúng, và nó đã có lưới riêng: chạy `has_access` thật trên toàn
ma trận cộng `KNOWN_ODOO_GAPS`.

### 4.4 Giới hạn phải nêu thẳng

Một số tool gọi Odoo qua helper dùng chung (vd `_validate_order_pickings` trong
`helpers.py`), nên quét thân hàm tool là hụt. Test đi thêm **một cấp**: hàm nào
được gọi trong thân tool và định nghĩa trong cùng package `mcp-servers/odoo`
thì gộp nguồn vào. Sâu hơn một cấp thì KHÔNG.

Ghi thẳng trong docstring của test. Ba lần trong dự án này, một công cụ kiểm
tra được tin quá mức chính vì giới hạn của nó không được viết ra.

## 5. Nghiệm thu

### 5.1 Test tự động

- Mọi tool trong `own ∪ needs_sign_off` của mọi vai, mọi profile, có mặt trong
  `DEPT_OF` (§3.1)
- Label của mọi vai non-admin là một giá trị có thật trong `DEPT_OF` (§3.2)
- `other_dept` suy ra cho `small-business` chứa đủ 5 tool đang thiếu, và
  KHÔNG chứa tool của chính vai đó
- `other_dept` cho `enterprise` vẫn chứa đủ 3 mục `other_dept_extra`
  (`inventory_adjustment`, `scrap_product`, `return_order`) — đối chứng cho lối
  thoát ở §3.3.
  **Lưu ý, đây KHÔNG phải "giữ nguyên y hệt":** tập suy ra rộng hơn tập khai
  tay cũ đúng 3 mục (`create_invoice_from_order`, `create_bill_from_po`,
  `send_invoice_email`) — chính là phần sửa. Test phải khẳng định tập MỚI, và
  nêu 3 mục thêm đó tường minh, thay vì so với ảnh chụp cũ.
- `allowed_tools()` của mọi vai, mọi profile, **không đổi** — đối chứng cho
  §3.4 (không đụng quyền Odoo)
- Ba kiểm của §4.2, kèm deliberate-break chứng minh mỗi kiểm bắt được lỗi thật

### 5.2 Nghiệm thu sống

Chạy lại đúng hai kịch bản đã hỏng trong nghiệm thu đợt trước, qua đúng cổng
vào thật:

| # | Kịch bản | Trước | Kỳ vọng sau |
|---|---|---|---|
| 3 | kho xin gửi mail hóa đơn | *"liên hệ bộ phận **khác**"* | *"liên hệ bộ phận **Kế toán**"* |
| 4 | kế toán xin gửi mail giao hàng | trả lời hội thoại lan man, không từ chối | từ chối, nêu bộ phận **Kho** |

Cộng đối chứng âm: kho gửi mail giao hàng và kế toán gửi mail hóa đơn vẫn chạy
(không chặn nhầm việc thuộc quyền).

### 5.3 Chuẩn không hồi quy

`1289 passed, 4 skipped, 46 deselected` với
`pytest -m "not live and not integration"`, cộng các test mới.

## 6. Rủi ro còn lại đã biết

- **`label` gánh hai vai** (nhãn hiển thị và định danh bộ phận). Test ghim được
  sự tồn tại, không ghim được ý nghĩa: đổi `label` của vai kho thành "Kho hàng"
  sẽ làm `other_dept` phình ra âm thầm cho tới khi test đỏ ở kiểm §5.1 dòng 2.
- **`operation` trong `TOOL_ACCESS_MAP` vẫn do người khai** (§4.3). Lưới duy
  nhất là chạy `has_access` thật.
- **Test drift chỉ đi một cấp helper** (§4.4).
- Profile `enterprise` vẫn nói "liên hệ bộ phận Kho" với chính người của Kho
  (§2) — cần vòng duyệt.
