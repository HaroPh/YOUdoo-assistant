# Đóng activity từ phía trợ lý — thiết kế

**Ngày:** 2026-08-14
**Trạng thái:** thiết kế đã duyệt, chờ plan
**Nguồn:** hệ quả trực tiếp của `2026-08-13-cross-department-handoff-design.md`
(ADR-012 §5), mục "Còn lại"

## 0. Tóm tắt

Vòng bàn giao chéo bộ phận đóng được hai phần ba của một vòng lặp: trợ lý **tạo**
được activity (`log_activity` qua `WRITE_COORDINATORS`) và **đọc** được
(`list_my_activities`). Không có gì **đóng** được.

Hệ quả: mỗi lần bàn giao sinh ra một activity sống mãi. Sau vài tuần, vai kế
toán mở "việc của tôi" ra sẽ thấy một danh sách toàn việc quá hạn — **tái tạo
đúng con số 37/37 mà ADR-012 §2 đã đo**, chỉ lùi lại một bước và lần này do
chính trợ lý sinh ra.

Đợt này thêm bước thứ ba: người dùng nói *"việc này xong rồi"* và activity được
đánh dấu hoàn tất, qua cổng xác nhận ghi sẵn có.

## 1. Bốn phép đo làm nền cho thiết kế

Đo trên Odoo thật (`ODOO_URL=http://localhost:8069`, db `odoo`) ngày 2026-08-14,
bằng đúng phép toán tính năng sẽ thực hiện. Tạo gì xoá nấy: tổng activity
31 → 31 sau cả bốn vòng.

### 1.1 Đóng activity là LƯU TRỮ, không phải xoá

`mail.activity.action_done` / `action_feedback` đặt `active=False`,
`state='done'`, `date_done=<hôm nay>`. Bản ghi **vẫn còn**, đọc lại được qua
`context={"active_test": False}`:

```
trước:  {'state': 'planned', 'active': True,  'date_done': False}
sau:    {'state': 'done',    'active': False, 'date_done': '2026-08-14'}
```

Nghĩa là đóng việc **hoàn tác được và để lại dấu vết** — không phải thao tác huỷ.

**Vòng đo đầu suýt kết luận ngược.** `mail.activity` CÓ field `active`, nên
`search_count([["id","=",id]])` lọc ngầm `active=True`: một bản ghi bị lưu trữ
biến mất khỏi kết quả **y hệt** một bản ghi bị xoá. Phải đo lại với
`active_test=False` mới phân biệt được.

### 1.2 Chú thích đang có trong repo là SAI

`backend/src/erp_query/crm.py:71` viết:

> *"mail.activity bản chất là việc CHƯA xong — Odoo unlink bản ghi khi đánh dấu
> hoàn tất — nên không cần điều kiện 'đang mở' nào thêm."*

Odoo **không** unlink. Kết luận của câu này (không cần điều kiện lọc nào thêm)
vẫn đúng, nhưng **đúng vì một lý do khác**: Odoo tự lọc `active=True` theo mặc
định. Đợt này sửa chú thích cho khớp phép đo. Để nguyên thì lần sau có người dựa
vào nó mà suy ra một điều sai (ví dụ "đóng việc là mất dữ liệu, phải sao lưu
trước").

### 1.3 ⚠️ Odoo KHÔNG chặn đóng việc của người khác

`ai-warehouse` đóng trót lọt một activity giao cho `ai-accounting`. Không có lưới
đỡ nào ở tầng Odoo.

Đây là ràng buộc thiết kế cứng: **quy tắc "chỉ đóng việc của mình" phải nằm
trong code của ta**. Suy từ ma trận quyền Odoo là sai — và đây là lần thứ hai
dự án gặp chuyện quyền Odoo không suy diễn được (lần trước: quyền ĐỌC và quyền
TẠO ACTIVITY không trùng nhau).

Cách cưỡng chế: lọc `user_id = get_uid()` ngay trong tool MCP, để **về mặt cấu
tạo** nó không chạm nổi việc của người khác. Đã đo là hiệu quả:

```
ai-warehouse tìm việc của ai-accounting, CÓ lọc user_id=mình : 0 kết quả
ai-warehouse tìm việc của ai-accounting, KHÔNG lọc           : 1 kết quả
```

### 1.4 Đóng rộng hơn hẳn tạo — nên KHÔNG cần bảng model

```
vai              sale.order   purchase.order   account.move   stock.picking
ai-warehouse     đóng được    đóng được        đóng được      đóng được
ai-accounting    đóng được    đóng được        đóng được      đóng được
```

Đối chiếu với ma trận **tạo** đo ở vòng trước: `ai-warehouse` *không tạo nổi*
activity trên `purchase.order` và `account.move` (đó là lý do
`handoff.ACTIVITY_MODELS_OF` tồn tại). Nhưng nó **đóng được trên cả bốn**.

Hệ quả trực tiếp: tính năng này **không cần bảng model nào cả**. Một nhánh phức
tạp bị loại bỏ bằng phép đo, không bằng suy đoán. Ma trận đo đủ 4/4 model đích
của `HANDOFF_DOC_OF` — vòng đo thứ hai chỉ có 3 và thiếu `purchase.order`; "danh
sách khai thiếu một dòng" là lớp lỗi đã tái diễn năm lần trong dự án này nên
được bịt bằng một vòng đo riêng.

### 1.5 Dấu vết có sẵn, không phải xây

`action_feedback(feedback=...)` ghi một tin vào chatter của chứng từ, chứa nguyên
văn lời nhắn:

```
✓ To-Do done: PROBE dong-activity — q3-feedback-text
```

Cộng với `write_uid` được đặt thành tài khoản đã đóng. Người dùng Odoo thật đọc
được ai đóng việc gì, khi nào — **không cần thêm cơ chế ghi nhật ký nào**.

## 2. Quyết định thiết kế

### 2.1 Người dùng chỉ việc theo CHỨNG TỪ, thiếu thì hỏi lại

```
"việc trên đơn S00012 xong rồi"
  → tra chứng từ → lọc activity giao cho vai mình trên chứng từ đó
  → 1 kết quả → hỏi xác nhận → đóng

"xong việc rồi"                       (không nêu chứng từ)
  → liệt kê việc đang mở của vai → hỏi chọn → hỏi xác nhận → đóng
```

Chọn đường này vì ba lý do: cùng khuôn args với `log_activity` (`res_model` +
`ref`), mã chứng từ là **thứ nửa đọc đã hiển thị** (`- S00012: đề nghị: … (hạn
…)`), và mã chứng từ **kiểm chứng được** nên chống được chuyện LLM bịa.

Đường lui (liệt kê rồi chọn) là bắt buộc, không phải tuỳ chọn: câu *"xong rồi"*
ngay sau khi vừa xem danh sách việc là cách nói tự nhiên nhất, và chặn nó lại để
đòi mã chứng từ là đóng cửa đúng lúc người dùng thấy thuận tay nhất.

### 2.2 Chỉ đóng việc giao cho tài khoản AI của chính vai

Cưỡng chế ở tool MCP (§1.3). Không có tham số nào cho phép đóng việc của người
khác — không phải "mặc định là của mình rồi cho phép ghi đè", mà là **không có
đường**.

Câu từ chối dùng CHUNG cho hai nguyên nhân (việc của người khác / việc đã đóng):

```
Việc này không được giao cho bộ phận của bạn, hoặc đã đóng rồi.
```

Tách hai câu sẽ để lộ việc của bộ phận khác có tồn tại hay không.

### 2.3 Qua cổng xác nhận ghi, như mọi thao tác ghi khác

`close_activity` là một coordinator trong `WRITE_COORDINATORS`, dùng
`_interrupt({"kind": "confirm", ...})` với `WRITE_CONFIRM_SUFFIX` như
`log_activity`. Không có cơ chế mới.

### 2.4 Đóng được MỌI việc giao cho vai, không riêng việc bàn giao

Không lọc theo `HANDOFF_MARKER`. Một activity do chính vai tự đặt (`log_activity`
không có `assignee`) cũng là việc của vai đó và cũng cần đóng được. Giới hạn vào
riêng việc bàn giao là ranh giới nhân tạo, không phản ánh cách người dùng nói.

## 3. Kiến trúc

Ba mảnh, mỗi mảnh một trách nhiệm, khớp đúng khuôn đã có của `log_activity`.

### 3.1 Tool MCP — `mcp-servers/odoo/tools/crm.py`

```python
close_activity(activity_id: int, note: str = "") -> str
```

Tham số tên `note` ở **mọi ranh giới API của ta** (planner → coordinator → tool).
Chữ `feedback` chỉ xuất hiện đúng một chỗ: kwarg của Odoo ở bước 2. Đặt hai tên
khác nhau cho cùng một giá trị dọc đường truyền là nguồn lỗi không cần thiết.

1. Đọc lại bản ghi với domain `[["id","=",activity_id], ["user_id","=",get_uid()]]`.
   Không thấy → từ chối bằng câu ở §2.2.
2. Gọi `action_feedback([[id]], {"feedback": note})`.
3. Trả `envelope(True, …, model="mail.activity", res_id=id, state="done")`.

Bước 1 là **lưới đỡ thứ hai**, không thừa: coordinator đã lọc theo login rồi,
nhưng cái lọc ở đây là cái duy nhất chạy **bằng chính tài khoản sẽ thực hiện
thao tác**. Đó là chỗ §1.3 nói không có lưới nào của Odoo.

### 3.2 Đường tra ứng viên — `backend/src/erp_query/crm.py`

Một hàm mới cạnh `list_my_activities`, **cùng khuôn**: login truyền tường minh
(không phải "người dùng hiện tại" — đường đọc chạy bằng `ai-readonly`), `gw=`
tiêm được cho test, trả envelope. Nhiệm vụ: tra activity đang mở của `login`
**trên một chứng từ cụ thể** (`res_model` + `res_id`).

**"Đang mở" nghĩa là `active=True`**, và điều đó có sẵn: Odoo lọc `active=True`
theo mặc định (§1.1), nên domain **không** cần điều kiện nào cho việc này —
nhưng cũng **không được** truyền `active_test=False`, vì làm thế sẽ lôi cả việc
đã đóng vào danh sách ứng viên và cho phép đóng lại một việc đã xong.

`list_my_activities` giữ nguyên, không sửa hành vi.

### 3.3 Coordinator — `backend/src/agents/crm_write.py`

Args từ planner: `res_model`, `ref`, `note` (lời nhắn, tuỳ chọn).

| tình huống | xử lý |
|---|---|
| `role_cfg is None` | từ chối — không xác định được tài khoản (cùng lối `list_my_activities` đã chọn cho đường eval) |
| thiếu `res_model`/`ref` | **dùng lại `list_my_activities(f"ai-{role_cfg.name}")`** để liệt kê việc đang mở của vai → interrupt hỏi chọn. Không viết đường tra thứ hai cho cùng một câu hỏi |
| có, chứng từ không tra được | dùng lại `_resolve_doc` nguyên vẹn — mọi câu từ chối của nó giữ nguyên |
| 0 việc trên chứng từ | *"Không có việc nào của bộ phận &lt;label&gt; đang mở trên '&lt;ref&gt;'."* |
| đúng 1 việc | hỏi xác nhận → gọi tool |
| nhiều việc | interrupt hỏi chọn, liệt kê theo nội dung việc |

Vai `admin` đi cùng đường: `role_cfg.name == "admin"` → tra việc giao cho
`ai-admin`. Không có nhánh riêng, và `unrestricted=True` không nới quy tắc §2.2 —
admin cũng chỉ đóng được việc của chính tài khoản mình.

Câu xác nhận nêu **nội dung việc, chứng từ và hạn** — người dùng phải thấy đủ để
biết mình đang đóng đúng việc:

```
Đánh dấu hoàn tất việc '<summary>' trên '<res_name>' (hạn <date_deadline>).
```

### 3.4 Đăng ký

| chỗ | thay đổi |
|---|---|
| `write_registry.WRITE_COORDINATORS` | một dòng `"close_activity"` |
| `roles.DEPT_OF` | một dòng — cùng lý do và cùng cảnh báo như `log_activity` (giá trị tuỳ tiện vì cả hai vai đều `own`; chỉ có nghĩa khi sau này có vai KHÔNG sở hữu nó) |
| `roles._WH_OWN`, `roles._ACC_OWN`, `own` của warehouse hồ sơ `enterprise` | thêm `close_activity` |
| `prompts.WRITE_PLANNER_PROMPT` | một dòng mô tả tool |

## 4. Rủi ro đã biết: cửa vào có thể không mở

`INTENT_ROUTER_PROMPT` có luật *"When unsure between erp_read and erp_write,
choose erp_read"*, và mô tả `erp_read` **vừa được thêm** cụm "việc của tôi",
"có việc gì chuyển cho tôi không" ở vòng trước. Câu *"việc trên đơn S00012 xong
rồi"* rất có thể rơi nhầm sang `erp_read` — **đúng dạng lỗi mà nghiệm thu sống
vòng trước bắt được** (nửa đọc coi như không tồn tại với người dùng thật dù
1382 test xanh).

**KHÔNG sửa prompt router trước.** Trình tự bắt buộc:

1. Nghiệm thu sống với ít nhất 5 cách diễn đạt khác nhau.
2. Chỉ khi đo được là cửa đóng mới sửa prompt.
3. Sửa xong phải chạy lại **cả hai** cổng eval `intent` và `sop_select` —
   `eval_gate.ROLE_FOR_SET` ánh xạ cả hai vào vai `router`.
4. Ghi lại giá phải trả. Bản sửa tương tự vòng trước **tốn 1 ca eval**
   (`intent` 0.9630 → 0.9444, vẫn ≥ baseline 0.8704).

Nới mô tả `erp_write` để bắt "xong rồi" có rủi ro kéo ngược ca `erp_read` sang
`erp_write` — nghĩa là câu hỏi thuần đọc bị đưa vào đường ghi. Đó là chiều rủi
ro nguy hiểm hơn, nên cổng eval là bắt buộc chứ không phải hình thức.

## 5. Nghiệm thu

### 5.1 Test

Lệnh chạy **bắt buộc** kèm bộ lọc marker — lệnh trần gọi API LLM thật và
Postgres, đã gây sự cố một lần:

```bash
pytest -m "not integration and not live" -q
```

Điểm phải có test:

- tool MCP: domain lọc `user_id` **có mặt** trong lệnh gọi Odoo (không chỉ kiểm
  kết quả — kết quả rỗng cũng xanh khi thiếu lọc);
- tool MCP: không tìm thấy → envelope lỗi, **không** gọi `action_feedback`;
- coordinator: 0 / 1 / nhiều việc → ba nhánh khác nhau;
- coordinator: thiếu `res_model`/`ref` → đi đường liệt kê, không đòi mã;
- coordinator: `role_cfg is None` → từ chối;
- coordinator: huỷ ở cổng xác nhận → **không** gọi tool;
- đường tra: lọc theo login truyền vào, không theo tài khoản hiện tại (khoá lại
  cùng bất biến mà `test_my_activities.py` đã khoá);
- đăng ký: `close_activity` có trong `WRITE_COORDINATORS`, có trong `DEPT_OF`,
  có trong `own` của cả hai vai ở **cả hai** hồ sơ.

**Mọi test dựng được ứng viên đều phải tiêm gateway giả.** Vòng trước có một
test gọi Odoo THẬT vì thiếu điểm tiêm, và nghiệm thu sống tạo đúng bản ghi khiến
3 test đỏ như một hồi quy bí ẩn.

**Thử phá (break probe) là bắt buộc** cho lưới lọc `user_id`: gỡ điều kiện lọc
ra, test tương ứng **phải đỏ**. Dự án này đã ba lần phát hiện test không đo gì,
một lần nằm trong chính code viết ra để đóng lớp lỗi đó.

### 5.2 Nghiệm thu sống, TRƯỚC merge

Chạy trên worktree của nhánh, không phải trên `main`.

| # | kịch bản | kỳ vọng |
|---|---|---|
| 1 | kế toán: *"có việc gì chuyển cho tôi không?"* | thấy việc bàn giao (nửa đọc vẫn chạy) |
| 2 | kế toán: *"việc trên đơn S00012 xong rồi"* | hỏi xác nhận → đóng → Odoo `state='done'` |
| 3 | kế toán hỏi lại #1 | việc đó **biến mất** khỏi danh sách |
| 4 | kế toán: *"xong việc rồi"* (không nêu chứng từ) | liệt kê rồi hỏi chọn |
| 5 | kho xin đóng một việc giao cho kế toán | từ chối |
| 6 | ≥5 cách diễn đạt khác nhau của "xong rồi" | đo tỉ lệ tới được planner (§4) |

\#3 và #5 là hai phép đo **quyết định**: #3 chứng minh vòng lặp thật sự khép, #5
chứng minh lưới §1.3 hoạt động ở tầng người dùng chứ không chỉ trong unit test.

Kịch bản #5 phải kiểm tra bằng cách **đọc trạng thái Odoo sau đó**, không chỉ đọc
câu trả lời: một câu từ chối hiện ra không chứng minh bản ghi còn nguyên.

### 5.3 Không được thụt

`pytest -m "not integration and not live" -q` phải giữ **1387 passed, 4 skipped**
trở lên. Cổng eval `intent`/`sop_select` chỉ chạy nếu §4 dẫn tới sửa prompt.

## 6. Ngoài phạm vi

### 6.1 Không đóng được việc của người thật

31 activity đang có trong Odoo thuộc về **người dùng thật**, không phải tài khoản
AI. Tool này không đóng được chúng — và theo §2.2 thì không nên.

Nên tính năng này **không phải lời giải cho con số 37/37 quá hạn của ADR-012**.
Nó khép vòng lặp cho việc do **chính trợ lý** sinh ra, để cơ chế bàn giao chéo bộ
phận không tự tích thành một đống việc quá hạn mới. Ghi rõ ở đây để lần sau
không ai đọc nhầm phạm vi.

### 6.2 Hoãn có điều kiện — tag id người gửi

Chủ dự án nêu: có nên gắn id người dùng vào activity để tra cứu ai yêu cầu.

Đã đo và **hoãn**, không phải vì ý tưởng sai:

- `mail.activity.note` là field Html ghi được, vai non-admin **đọc được**, và
  **sống sót qua thao tác đóng** — đây là chỗ chứa đúng nếu làm.
  **Không dùng `summary`**: summary vừa là chữ người dùng đọc vừa là chuỗi mà
  `HANDOFF_MARKER` khớp để chống trùng.
- Provenance **cấp bộ phận đã có sẵn miễn phí**: `create_uid` được ghi và vai
  non-admin đọc được, cộng tiền tố `"Kho đề nghị:"` trong summary.
- Id người dùng **đã chảy tới backend**, nằm trong khoá luồng
  `"{role}:owui:{user_id}:{chat_id}"` — không phải xây đường ống mới.
- **Nhưng `YOUDOO_ROLE_MAP` hiện có 3 mục, mỗi vai đúng 1 người.** Hôm nay id
  người dùng mang đúng bằng không thông tin so với tên vai đã ghi trong summary.
  Và nó là chuỗi mờ: thứ duy nhất biến nó thành tên người (name/email) lại chính
  là thứ quy tắc PII của dự án cấm đọc.

**Điều kiện dựng lại:** khi một vai có **người thứ hai** trong `YOUDOO_ROLE_MAP`.
Lúc đó làm cùng tính năng đọc *"việc tôi đã chuyển đi"* — hôm nay không ai tra
được việc mình đã gửi, vì `list_my_activities` chỉ lọc theo người **nhận**.

### 6.3 Vẫn còn từ vòng trước

- **4/20 tool trong `DEPT_OF` trỏ vào "Bán hàng"/"Mua hàng"** — không vai nào
  sở hữu; muốn đóng phải thêm tài khoản Odoo + tiến trình MCP + nhóm quyền.
- **Bộ eval mù với khối worker rỗng** — `run_eval.py` luôn dựng prompt bằng
  `load_skill_specs()` đầy đủ, nên cấu hình thật của vai kế toán chưa từng được
  đo. Khoảng trống này đã để lọt một lỗi.
- **Ánh xạ bộ phận → người thật** — hôm nay giao cho tài khoản AI của bộ phận.
