# Thiết kế — tổng quát hoá `log_activity` (2026-08-12)

**Trạng thái:** đã duyệt, chờ viết plan.
**Nối tiếp:** `docs/ADR-012` §5 (bàn giao liên bộ phận, đang hoãn),
`2026-08-12-role-declaration-derivation-design.md`.

## 1. Vấn đề

`log_activity` là **vế GHI** của bất đối xứng mà ADR-012 nêu ra: nó ghi vào một
danh sách việc mà không tool nào đọc được. Nhưng vấn đề sâu hơn là **nó gần như
không được dùng**.

Bằng chứng, đo 2026-08-12 theo tháng tạo bản ghi:

| model | tổng | do dự án sinh | seed gốc |
|---|---|---|---|
| `stock.picking` | 208 | 156 | 52 |
| `sale.order` | 172 | 146 | 26 |
| `mail.activity` | 37 | **1** | 36 |

Phiếu và đơn giàu lên vì có tool tạo ra chúng. `mail.activity` đứng yên vì
`log_activity` bị bó ba tầng:

| Giới hạn hiện tại | Odoo thực ra cho phép |
|---|---|
| hardcode `crm.lead` | mọi model — chỉ cần `res_model_id` + `res_id` |
| chỉ `Call` / `Meeting` | thêm **To-Do**, **Email**, **Document** dùng được cho mọi model. To-Do đang là loại nhiều nhất trong dữ liệu (11/31) |
| `user_id = get_uid()` cố định | 6 người dùng nội bộ: 4 tài khoản AI + Marc Demo + Mitchell Admin |

Và nó là `denied` với **cả hai** vai non-admin, nên chỉ admin gọi được.

## 2. Phạm vi

**Làm:**
1. Tổng quát hoá tool theo model, loại, người nhận (§3–§5)
2. Nhóm quyền Odoo hẹp cho `ir.model` read (§6)
3. Cấp tool cho hai vai + bổ sung `DEPT_OF` (§7)
4. Sửa coordinator tương ứng (§8)

**KHÔNG làm — và lý do là một phép đo, không phải sự thận trọng:**

- **Bàn giao liên bộ phận** (ADR-012 §5, trạng thái `E`): agent tự đề nghị tạo
  activity giao sang bộ phận đúng khi từ chối một yêu cầu ngoài vai. Cửa kích
  hoạt của nó là **đường từ chối**, mà đường đó hiện **không chạy với vai kế
  toán**: vai này không nạp SOP skill nào ⇒ `render_worker_block([])` rỗng ⇒
  intent router phân loại yêu cầu ghi là `unknown` 3/3 thay vì `erp_write` ⇒
  planner không chạy ⇒ guard không có gì để chặn (đo 2026-08-12, xem
  `2026-08-12-role-declaration-derivation-report.md` §2.3).

  Xây bàn giao lúc này sẽ cho ra một tính năng chạy với vai kho và **im lặng
  không kích hoạt** với vai kế toán — đúng hạng lỗi đã xảy ra với tool mail,
  nơi một bộ 1254 test xanh không thấy gì. Phải sửa worker block trước.

- Tool **đọc** activity. Lý do sắp xếp: dữ liệu nên xuất hiện từ việc dùng
  thật trước, rồi mới xây thứ hiển thị nó — chứ không bơm dữ liệu để tool đọc
  có việc làm.

## 3. Hình dạng tool — soi gương `preview_template_email`

Dự án **đã có** một tool tổng quát theo model, đã chạy sống qua 4 model
(`sale.order`, `purchase.order`, `account.move`, `stock.picking`):

```python
preview_template_email(template_name: str, res_model: str, ref: str)
```

Nó tra bản ghi bằng `search_read([["name", "=", ref]])` **ngay trong tool**.

**Nhưng khuôn đó KHÔNG áp được nguyên xi ở đây, và đây là chỗ bản nháp đầu của
thiết kế này sai.** `_resolve_lead` trong coordinator hiện làm ba việc mà tra
`name =` chính xác không làm được:

1. tìm mờ qua `crm.find_lead` (không cần gõ đúng tên lead)
2. bỏ kính ngữ ("anh/chị Nam" → "Nam")
3. **hỏi lại khi trùng nhiều**, qua `_interrupt` với danh sách lựa chọn

Chuyển việc giải tham chiếu vào tool sẽ xoá cả ba. Đó là gỡ mất tính năng đang
chạy để đổi lấy sự đối xứng hình thức — không đáng.

Nên **giữ nguyên phân tầng đang là chuẩn của dự án**: coordinator giải tham
chiếu của con người, tool nhận id.

```python
log_activity(res_model: str, res_id: int, activity_type: str, summary: str,
             date_deadline: str = "", assignee: str = "") -> str
```

`preview_template_email` là ngoại lệ chứ không phải khuôn mẫu — nó tra trong
tool vì template mail vốn địa chỉ hoá bản ghi theo tên, và nó không có nhu cầu
hỏi lại.

Không giới hạn danh sách `res_model` ở tầng tool: activity là một ghi chú gắn
vào chứng từ, không phải hành động đặc quyền, và Odoo tự từ chối model không
tồn tại. Giới hạn thật nằm ở coordinator, nơi phải biết cách giải `ref` cho
model đó (§8).

## 4. Loại hoạt động — suy ra, không hardcode

Hiện hardcode `Call | Meeting`. Đổi thành hardcode 5 giá trị là lặp lại đúng
hạng lỗi mà hai đợt vừa rồi đi sửa.

Thay vào đó: tra `mail.activity.type` theo tên, rồi **kiểm trường `res_model`
của chính loại đó** — rỗng nghĩa là dùng được cho mọi model, có giá trị nghĩa là
chỉ model đó. Odoo mang sẵn thông tin này:

| loại | `res_model` |
|---|---|
| To-Do, Email, Call, Meeting, Document | (rỗng — mọi model) |
| Maintenance Request | `maintenance.request` |

Nên `Maintenance Request` trên `sale.order` bị từ chối **vì Odoo nói vậy**,
không vì ta viết một danh sách cấm.

## 5. `assignee`

Giải trong `res.users` có `share = False` (6 người dùng nội bộ). Thứ tự tra,
nêu rõ để không mơ hồ:

1. khớp **chính xác `login`** (vd `ai-accounting`) — đường mà bàn giao giữa các
   vai AI sẽ dùng, và là đường duy nhất không nhập nhằng
2. nếu không có, khớp **chính xác `name`** (vd `Marc Demo`)
3. nếu vẫn không, tìm gần đúng theo `name`; **trùng nhiều thì từ chối** và liệt
   kê các ứng viên tìm được — KHÔNG tự chọn

Bỏ trống = tài khoản đang gọi, giữ nguyên hành vi hiện tại.

Bước 3 cố ý **không** dùng `_interrupt` để hỏi lại như `_resolve_lead`: người
nhận là tham số phụ, và thêm một cổng hỏi lại thứ hai vào giữa luồng đã có cổng
xác nhận là làm rối trải nghiệm cho một trường hợp hiếm.

Trường này **cố ý làm sớm hơn nhu cầu**: hôm nay chưa ai dùng, nhưng nó biến
bàn giao liên bộ phận (§2) thành *thêm một nhánh kích hoạt* thay vì *viết lại
tool*. Chi phí gần bằng không vì cùng một trường `user_id`.

Không tìm thấy người → từ chối, nêu tên đã gõ. Không liệt kê danh sách người
dùng trong câu từ chối.

## 6. Quyền Odoo — nhóm hẹp `Youdoo AI / Activity`

Đo 2026-08-12:

```
ai-admin       activity.create=True  ir.model.read=True
ai-warehouse   activity.create=True  ir.model.read=FALSE
ai-accounting  activity.create=True  ir.model.read=FALSE
```

`mail.activity` create **bắt buộc `res_model_id`** — id của `ir.model`, tra
runtime; truyền `res_model` dạng chuỗi bị Odoo từ chối (probe-verify
2026-07-19, ghi trong chính `crm.py`). Nên tool phải đọc `ir.model`, và hai vai
non-admin không có quyền đó.

Nếu bỏ qua, tool sẽ gãy **đúng kiểu coordinator mail đã gãy**: quyền chính có,
quyền phụ không, và chỉ live-verify mới thấy.

Thêm nhóm `Youdoo AI / Activity` cấp **đúng `ir.model` read**, gán cho ba tài
khoản ghi. Cùng khuôn mẫu đã dùng bốn lần (`Youdoo AI / Mail`,
`Sale Invoicing`, `Read Only`, `Mail Warehouse|Accounting`). Không cấp gì hơn.

## 7. Nối vào vai — đợt này CÓ đổi quyền Odoo

`log_activity` thêm vào `own` của cả `warehouse` và `accounting`, và thêm một
mục vào `DEPT_OF` (nó là một trong 16 tool thiếu bảng đó).

**Khác hẳn đợt trước.** Đợt `role-declaration-derivation` có ràng buộc cứng
"`allowed_tools()` không được đổi". Đợt này **cố ý đổi** — thêm một tool vào
`own` nghĩa là `scripts/odoo_setup_ai_accounts.py` sinh ra bộ nhóm quyền khác
trước. Phải nêu tường minh trong Global Constraints của plan, và
`scripts/check_role_odoo_consistency.py` phải được chạy lại: nó sẽ báo một dòng
mới, và dòng đó phải **khớp**, không phải thành GAP thứ 10.

`DEPT_OF["log_activity"]` = bộ phận nào? Activity là công cụ **dùng chung**,
không thuộc riêng ai — nhưng `DEPT_OF` không có khái niệm đó. Vì cả hai vai đều
`own` nó, giá trị không ảnh hưởng tới `other_dept` của hai vai đó (suy diễn trừ
đi `own`). Chọn `"Kho"` là tuỳ tiện. Chọn cách trung thực hơn: **không thêm vào
`DEPT_OF`** — tool được cả hai vai sở hữu thì không vai nào cần chỉ sang đâu.

Nhưng test `test_moi_tool_duoc_so_huu_deu_co_bo_phan` (đợt trước) khẳng định mọi
tool được sở hữu đều phải có mục `DEPT_OF`. Nên có hai đường:
- thêm mục và chấp nhận nó là tuỳ tiện, hoặc
- nới test cho phép "tool dùng chung".

**Chọn: thêm mục `"Kho"`**, kèm comment nói rõ đây là giá trị không ảnh hưởng
hành vi (cả hai vai đều `own`), và ghi rằng nếu sau này có vai KHÔNG sở hữu
`log_activity` thì giá trị này mới bắt đầu có ý nghĩa và cần xem lại. Nới test
để lấy một ngoại lệ là làm yếu đúng cái lưới vừa dựng.

## 8. Coordinator

`backend/src/agents/crm_write.py` hiện giải lead rồi truyền `lead_id`. Nay phải
giải theo model.

**Bảng giải tham chiếu theo model**, với một hàm giải chung làm mặc định:

| `res_model` | cách giải |
|---|---|
| `crm.lead` | `_resolve_lead` hiện có — GIỮ NGUYÊN, kèm tìm mờ, bỏ kính ngữ, hỏi lại khi trùng |
| `sale.order`, `purchase.order`, `account.move`, `stock.picking`, `mrp.production` | tra `name =` chính xác; mã của chúng vốn là mã máy (`S00119`, `WH/OUT/00138`) nên không cần tìm mờ |
| khác | từ chối, nêu danh sách model hỗ trợ |

Đây là chỗ giới hạn model thật sự nằm — không phải ở tool (§3). Fail-closed:
model chưa biết cách giải thì từ chối, không đoán.

Bỏ `_ACTIVITY_ALIASES` cứng (Call/Meeting) — việc kiểm loại nay thuộc về tool,
nơi có Odoo để hỏi.

Slot-fill gộp giữ nguyên: nó liệt kê mọi slot thiếu trong một câu và đang hoạt
động tốt. Danh sách slot đổi thành: chứng từ nào (model + mã), loại, nội dung.

## 9. Nghiệm thu

### 9.1 Test tự động

- Tool: loại hợp lệ trên model bất kỳ; loại gắn model khác bị từ chối; `ref`
  không tìm thấy; `assignee` không tìm thấy; `assignee` rỗng → tài khoản gọi
- Coordinator: slot-fill gộp nêu đủ slot thiếu; huỷ ở cổng xác nhận không ghi gì
- `DEPT_OF` / `roles.py`: `log_activity` là `own` của cả hai vai, và test bao
  phủ `DEPT_OF` của đợt trước vẫn xanh

### 9.2 Nghiệm thu sống — controller chạy

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1 | admin tạo activity To-Do trên `sale.order` S00119, giao Marc Demo | tạo được, đọc lại đúng người nhận và hạn |
| 2 | **kho** tạo activity giao cho `ai-accounting` | **phép đo quyết định cho §6** — đi qua đúng đường `ir.model` từng thiếu quyền |
| 3 | `Maintenance Request` trên `sale.order` | từ chối sạch, nêu lý do |
| 4 | `assignee` gõ sai tên | từ chối, nêu tên đã gõ |
| 5 | `check_role_odoo_consistency.py` | exit 0; dòng `log_activity` mới **khớp**, không thành GAP thứ 10 |

Dọn mọi activity tạo ra khi đo.

## 10. Rủi ro còn lại đã biết

- **Activity tạo ra có thể VÔ HÌNH với chính vai được giao.** Đo 2026-08-12:
  cùng một truy vấn, chủ dự án thấy 37 activity, `ai-admin`/`ai-readonly` thấy
  31, `ai-warehouse` thấy **12**. Không phải luật đọc — Odoo lọc `mail.activity`
  theo quyền đọc **tài liệu đính kèm**. Nên một activity gắn vào `account.move`
  giao cho `ai-warehouse` sẽ không được vai kho nhìn thấy. Điều này **chưa** ảnh
  hưởng đợt này (chưa có tool đọc), nhưng là ràng buộc thật cho bàn giao ở §2 —
  bàn giao chỉ có nghĩa khi vai nhận đọc được chứng từ.
- **Hoá đơn nháp không tra được theo `name`** (§3).
- `DEPT_OF["log_activity"]` là giá trị tuỳ tiện cho tới khi có vai không sở hữu
  tool này (§7).
- Bàn giao liên bộ phận vẫn bị chặn bởi lỗi worker block (§2).
