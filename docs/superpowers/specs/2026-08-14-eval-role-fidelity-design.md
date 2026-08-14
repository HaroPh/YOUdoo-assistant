# Eval đo đúng cấu hình theo vai — thiết kế

**Ngày:** 2026-08-14
**Trạng thái:** thiết kế đã duyệt, chờ plan
**Nguồn:** khoảng trống đã biết, ghi trong "Còn lại" của
`2026-08-13-cross-department-handoff-design.md` và của
`2026-08-14-close-activity-design.md`

## 0. Tóm tắt

Ba cổng eval (`intent`, `sop_select`, `planner`) chấm điểm trên một cấu hình
prompt mà **không vai nào chạy trong production**. Bộ đo dựng prompt từ tập
skill và tập tool **đầy đủ**; production lọc cả hai theo vai.

Hệ quả: mọi kết luận "cấu hình hiện tại còn khoẻ" chỉ đúng cho vai `admin`.

Đợt này làm bộ đo dựng prompt bằng **chính hàm production dùng**, cho một vai
chỉ định, và cho cổng chạy hai cấu hình: `admin` (rộng nhất) và `accounting`
(hẹp nhất).

## 1. Đo được, không phải suy đoán

Đo trên `main` sau `d28e180`, ngày 2026-08-14:

Worker block — đo bằng **chính `skill_role_gap` của production**, cấp cho nó
registry tool giả mang đúng 35 tên tool MCP thật:

| hồ sơ | vai | tool sau lọc | skill giữ | worker block |
|---|---|---|---|---|
| — | **eval đang đo** | (không lọc) | **3/3** | **10 dòng** |
| small-business | admin | 35 | 3/3 | 10 dòng |
| small-business | kho | 10 | 2/3 | 7 dòng |
| small-business | **kế toán** | 7 | **0/3** | **RỖNG** |
| enterprise | kho | 6 | 1/3 | 4 dòng |
| enterprise | **kế toán** | 7 | **0/3** | **RỖNG** |

Prompt planner — đo bằng chính `planner_prompt_for(cfg)`:

| | eval đang đo | kho (sb) | kho (ent) | kế toán |
|---|---|---|---|---|
| `WRITE_PLANNER_PROMPT` | **35 tool** | 10 | 7 | **8** |

⚠️ **Sửa so với bản duyệt đầu (2026-08-14, phát hiện khi viết plan).** Bản đầu
ghi vai kế toán giữ "1/3 skill, 4 dòng". Con số đó đến từ một **proxy so tên**
(`write_tools ⊆ allowed_tools`) do controller tự viết, KHÔNG phải từ hàm thật.
Đo lại bằng `skill_role_gap`: **0/3**. Chênh lệch vì `bao-gia-chiet-khau` có
`declares_tools=('create_discount_quote',)` và `entry='logic.py'`, nên nó đi vào
nhánh `build_skill_tools` chứ không phải nhánh so tên — và nhánh đó loại nó.

Bài học tự nó chứng minh nguyên tắc §2: **một phép tái lập viết tay đã lệch khỏi
hàm thật ngay trong chính tài liệu đi sửa lỗi lệch.**

Cổng `planner` chấm điểm chọn-đúng-tool trên thực đơn 35 mục, trong khi mọi vai
non-admin nhìn thấy 7–10 mục. Độ chính xác trên hai bài toán đó không so được
với nhau.

`SYSTEM_PROMPT` **không** có bản theo vai, nên `eval_read` không dính trục này.
Các bộ `confirm`, `chitchat`, `synthesis`, `multi_source` cũng không.

### 1.1 Khoảng trống này ĐÃ để lọt một lỗi thật

Khối worker **rỗng** khiến router phân loại lệnh ghi thành `unknown` **3/3** cho
vai kế toán — vai đó không bao giờ tới được planner của nó. Nghiệm thu sống bắt
được; eval **về mặt cấu trúc không thể** bắt, vì nó chưa bao giờ dựng cấu hình
đó.

Và §1 vừa cho thấy khối worker rỗng **không phải giả định** — nó là cấu hình
production **hiện tại** của vai kế toán, trên **cả hai** hồ sơ. `render_intent_
router_prompt("")` trả về đúng `INTENT_ROUTER_PROMPT` trần, nên với vai kế toán,
**prompt trần CHÍNH LÀ production** — đúng cấu hình mà §1.2 dưới đây ghi là
"KHÔNG PHẢI production thật".

### 1.2 Đây là cùng một lỗi, sâu hơn một lớp

Docstring `eval_intent` (`evals/run_eval.py`) ghi lại một bản sửa trước đây:

> *"SystemMessage trước đó dùng INTENT_ROUTER_PROMPT TRẦN, không nối worker
> block — khác với hợp đồng production thật … Trước fix này, điều kiện 'bộ
> intent cũ không được thụt' đo trên một cấu hình prompt KHÔNG PHẢI production
> thật."*

Bản sửa đó nối khối worker vào — nhưng là khối **đầy đủ**. Cùng một hạng lỗi,
dừng lại đúng một bước trước đích.

### 1.3 Hệ quả trực tiếp, xảy ra trong chính đợt trước

Đợt `close-activity` duyệt một thay đổi `INTENT_ROUTER_PROMPT` dựa trên cổng
`intent` **0.944**. Thay đổi đó tác động **cả ba vai**. Con số 0.944 đo cấu hình
admin, nên nó không nói gì về vai kế toán — vốn chạy worker block ngắn hơn 60%.

## 2. Nguyên tắc thiết kế

**Bộ đo dựng prompt bằng CHÍNH hàm production dùng, không tự dựng lại.**

Mỗi lần dự án này để một danh sách hoặc một prompt được dựng lại ở nơi thứ hai,
nó đã trôi lệch. `planner_prompt_for` viết đúng điều đó trong docstring của
chính nó:

> *"Sinh từ chính RoleCfg thay vì viết tay 3 bản — nếu viết tay, danh sách tool
> trong prompt sẽ trôi lệch khỏi tập tool thật (lớp lỗi đã gặp ở
> mail-trigger-points…)"*

Nguyên tắc này loại thẳng một phương án: **không** khai cứng cấu hình mong đợi
của từng vai trong bộ đo.

## 3. Kiến trúc

### 3.1 `eval_planner` — đơn giản nhất

`planner_prompt_for(cfg)` **đã thuần**: chỉ cần `RoleCfg`, không cần tool, không
cần Odoo. Vai admin (`allowed_tools()` trả `None`) nhận nguyên bản gốc, nên
đường admin **không đổi hành vi** — điều kiện để baseline hiện có giữ nguyên ý
nghĩa.

### 3.2 `eval_intent` / `eval_sop_select` — lọc skill bằng chính hàm production

Production lọc trong `graph.py`:

```python
for spec in load_skill_specs():
    reason = skill_role_gap(spec, tools, mcp_all_tools, role_cfg)
    if reason:
        continue
    skill_specs.append(spec)
```

Bộ đo phải gọi **đúng `skill_role_gap` đó**, không tái lập phép lọc.

### 3.3 Cấp tool cho bộ lọc mà không cần MCP sống

`skill_role_gap` cần hai danh sách tool (đã lọc theo vai / đầy đủ). Bộ đo không
có kết nối MCP. Giải:

1. Lấy **tên** tool MCP thật bằng cách import module `server` của
   `mcp-servers/odoo`. **Đã kiểm 2026-08-14: cho ra đủ 35 tên, không cần MCP
   sống, không chạm Odoo** (chỉ cần biến môi trường có mặt; `get_uid()` là lười).
   Khuôn này đã dùng sẵn ở `backend/tests/mcp/test_log_activity_tool.py`.
2. Dựng **tool giả mang đúng tên đó**, lọc theo `role_cfg.allowed_tools()`, rồi
   gọi `skill_role_gap` thật.

Khuôn "tool giả mang tên thật" đã được chứng minh trong repo:
`backend/tests/agents/test_skill_role_filtering.py` dựng registry giả bằng
`@lc_tool` và **build graph thật** với nó.

**Giả định duy nhất:** bộ lọc chỉ quan tâm **tên** tool. Giả định này **phải
được khoá bằng test**, không được để nguyên là niềm tin — xem §5.

### 3.4 Bề mặt CLI

Thêm `--role` cho `evals/run_eval.py` và cho job `eval-gate`
(`jobs/eval_gate.py::add_args`), với `choices` lấy **từ `roles.PROFILES`** chứ
không viết tay. **Mặc định `admin`**, để mọi lệnh đang có và baseline đang có
giữ nguyên nghĩa.

Hồ sơ (`small-business` / `enterprise`) lấy theo `YOUDOO_POLICY_PROFILE` như
production, không thêm cờ riêng — bớt một trục cấu hình phải đồng bộ.

`--role` chỉ đổi hành vi của ba bộ `intent`, `sop_select`, `planner`. Với các bộ
khác nó được **chấp nhận nhưng không có tác dụng**; điều đó phải nêu trong
`help` và được **ghim bằng một test liệt kê đúng ba bộ nhạy-vai** — nếu sau này
một bộ thứ tư trở thành nhạy-vai mà quên khai, test đỏ.

## 4. Cổng chạy hai cấu hình

| cấu hình | vì sao |
|---|---|
| `admin` | rộng nhất; giữ baseline hiện có còn ý nghĩa; là cấu hình demo hay dùng |
| `accounting` | **hẹp nhất: worker block RỖNG (0/3 skill), 8 tool trong prompt planner** — đúng cấu hình con bọ §1.1 đã sống trong đó |

Vai kho nằm giữa hai đầu phổ, nên không đo trong đợt này. Đây là **đánh đổi có
chủ ý**, ghi ra để người sau biết nó là lựa chọn chứ không phải sơ suất: nếu
sau này có một lỗi chỉ xảy ra ở vai kho, đây là chỗ đầu tiên cần xem lại.

Chi phí: 96 ca (54 + 17 + 25) mỗi cấu hình, ~8 phút ở nhịp hiện tại ⇒ ~16 phút
cho một lượt cổng, gấp đôi hôm nay.

**Baseline cho vai hẹp dựng bằng phép đo trong đợt này**, đúng cách mọi baseline
khác đã được dựng (`--save-baseline`). KHÔNG đòi nó phải ngang admin — đòi hỏi
đó tuỳ tiện: hai cấu hình là hai bài toán khác nhau.

**Quy ước tên baseline** — phải chốt, nếu không bản mới sẽ **ghi đè** bản admin
đang dùng:

- vai `admin` giữ **nguyên tên cũ** `baseline-{model}-{set}.json` (5 file hiện
  có không được đổi tên — đổi là làm hỏng mọi lệnh và mọi tham chiếu đang có);
- vai khác thêm hậu tố vai: `baseline-{model}-{set}-{role}.json`.

Nói cách khác: không hậu tố **nghĩa là** admin. Quy ước này phải nằm trong một
hàm dựng đường dẫn duy nhất, dùng chung cho cả `run_eval` lẫn `eval_gate` — hai
nơi tự ghép chuỗi là đúng hạng lỗi §2.

## 5. Lưới đỡ đóng vĩnh viễn hạng lỗi này

Hai vế §3 và §4 chỉ sửa **hiện trạng**. Vế này ngăn **tái diễn**, và nó là phần
quan trọng nhất của đợt.

Một test **KHÔNG gọi LLM** khẳng định: với **mọi vai × mọi hồ sơ**, prompt mà bộ
đo dựng **giống hệt** prompt production dựng.

Test này bắt được cả hai chiều trôi lệch trong tương lai:

- production đổi cách dựng prompt mà bộ đo không đổi theo;
- bộ đo đổi mà production không đổi.

Đây là điều mà cả ba bản sửa trước đó (§1.2) **không** làm, và là lý do hạng lỗi
này tái diễn.

**Phép thử phá bắt buộc:** đổi bộ đo về dùng tập đầy đủ ⇒ test này **phải đỏ**.
Vẫn xanh nghĩa là nó không đo gì.

## 6. Hai món đo-lường đi kèm

Gộp vào đợt này vì chúng **là cùng một câu hỏi** — một danh sách đo bị lệch —
chỉ ở tầng khác.

### 6.1 `send_delivery_email` thiếu trong `WRITE_TOOL_NAMES`

Đo trên `main` 2026-08-14:

```
tool trong WRITE_PLANNER_PROMPT : 35
tool trong WRITE_TOOL_NAMES     : 34
thiếu ở bảng                    : ['send_delivery_email']
chiều ngược lại                 : (không có)
```

`evals/cases.py::WRITE_TOOL_NAMES` tự khai là đồng bộ với `WRITE_PLANNER_PROMPT`.
Lệch ⇒ chỉ số `dangerous_misroute` xếp một misroute sang `send_delivery_email`
vào rổ **an toàn**. Đây là lần thứ **hai** danh sách này lệch — lần đầu ở
mail-trigger-points, thiếu 4 tool mail.

### 6.2 Thay test yếu bằng bất biến suy ra

`test_planner_biet_ten_tool` chỉ kiểm chuỗi con `"close_activity("` — vẫn xanh
nếu danh sách tham số sai hoàn toàn.

Thay bằng bất biến: **mọi tool trong `WRITE_PLANNER_PROMPT` phải có trong
`WRITE_TOOL_NAMES`**. Bất biến này đóng §6.1 và chặn lần lệch thứ ba, thay vì
sửa một triệu chứng.

## 7. Nghiệm thu

### 7.1 Test

Lệnh chạy **bắt buộc** kèm bộ lọc marker — lệnh trần gọi API LLM thật và
Postgres, đã gây sự cố một lần:

```bash
pytest -m "not integration and not live" -q
```

Điểm phải có test:

- **§5**: prompt eval == prompt production, mọi vai × mọi hồ sơ, không gọi LLM.
  Kèm phép thử phá.
- Giả định §3.3: bộ lọc chỉ quan tâm **tên** tool — khoá lại bằng test dùng tool
  giả, đối chiếu với `skill_role_gap` thật.
- Vai admin: prompt planner và worker block **không đổi** so với trước đợt này
  (điều kiện để baseline hiện có còn dùng được). Kiểm bằng cách so với chuỗi
  dựng từ `WRITE_PLANNER_PROMPT` / `load_skill_specs()` đầy đủ — tức chính cách
  bộ đo dựng prompt TRƯỚC đợt này.
- Quy ước tên baseline: admin ⇒ **không** hậu tố (trùng đúng 5 file đang có),
  vai khác ⇒ có hậu tố. Ghim để một lần sửa nhầm không ghi đè baseline admin.
- Bất biến §6.2, và `send_delivery_email` có trong bảng.
- Tham số vai không tồn tại / sai tên ⇒ **từ chối rõ ràng**, không im lặng rơi
  về admin (fail-closed).

**Không thụt:** suite phải giữ **≥ 1420 passed, 4 skipped**.

### 7.2 Đo bằng LLM thật — controller làm, KHÔNG giao subagent

1. Chạy 3 bộ ở vai `admin`, đối chiếu baseline hiện có: **không được thụt**.
   Đây là phép đo chứng minh đợt này không phá thứ đang chạy.
2. Chạy 3 bộ ở vai `accounting`, `--save-baseline`.
3. **Ghi lại con số của vai hẹp và so với admin.** Nếu nó thấp hơn hẳn, đó là
   một phát hiện thật về sản phẩm — không phải lỗi của đợt này, và phải được
   báo cáo chứ không lặng lẽ nhận làm baseline.

Điểm 3 là lý do đợt này đáng làm: nó có thể lộ ra rằng vai hẹp vốn đã yếu hơn
mà không ai biết.

### 7.3 Không được thụt

Cổng `sop_select` **đỏ vĩnh viễn theo thiết kế** (16/17, ca hồi quy 2026-07-16),
bị loại khỏi `--set all` để không che tín hiệu các cổng khác. Đợt này **không**
đụng vào chuyện đó; chỉ ghi nhận để người sau không tưởng là hồi quy mới.

## 8. Ngoài phạm vi

- **21/33 tool MCP rò nguyên văn lỗi Odoo** — khác hệ thống con, khác loại rủi
  ro, 21 file. Không ảnh hưởng độ chính xác phép đo. Đợt riêng.
- **`limit=20` cắt im lặng danh sách việc** — thuộc tính năng đóng việc.
- **`TOOL_ACCESS_MAP` thiếu cặp `("mail.activity","read")`** — thuộc script đối
  chiếu quyền Odoo: cũng là công cụ đo, nhưng đo **quyền Odoo**, khác dụng cụ.
- **Tag id người gửi** — có điều kiện kích hoạt riêng (một vai có người thứ hai).
- **Vai Bán hàng / Mua hàng** — 4/20 tool trong `DEPT_OF` chưa vai nào sở hữu.
- **Vai kho trong cổng eval** — xem §4, đánh đổi có chủ ý.
