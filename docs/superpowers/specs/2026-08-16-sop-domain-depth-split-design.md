# Tách miền nghiệp vụ khỏi độ sâu ở tầng định tuyến SOP — thiết kế

**Ngày:** 2026-08-16
**Trạng thái:** đã duyệt hướng, chờ viết implementation plan
**Xuất phát từ:** câu hỏi của chủ dự án — *"có cần bắt user nhắc 'quy trình nhập
kho' thì mới theo flow SOP không?"* — và một ca eval hỏng bền bỉ từ 2026-07-16

---

## 1. Đề bài, đo được chứ không suy đoán

### 1.1 Hiện tượng bề mặt

Cổng eval `sop_select` là **gate tuyệt đối** (`acc == 1.0 và hijack == 0`,
`jobs/eval_gate.py`), và nó FAIL 16/17 liên tục từ 2026-07-31. Đúng một ca
trượt, luôn là ca đó:

```
"quy trình nhập kho cho đơn mua P00021"  →  intent=rag, sop=null  →  rag
kỳ vọng: nhap-kho
```

Ca này sống sót qua: hai model router khác nhau (`gemma-4-26b` →
`gemini-3.1-flash-lite`), hai lần viết lại mô tả skill, và mọi phép đo từ tháng
7. Đo lại 2026-08-16 với model hiện tại: vẫn `acc=0.9412`, vẫn đúng ca đó, và
tất định 3/3 lượt.

Vì gate này đỏ vĩnh viễn, nó bị loại khỏi `--set all` của job hàng đêm để không
che tín hiệu của 7 gate khác — tức **một hàng rào an toàn định tuyến đang không
được job nào gác**.

### 1.2 Đề bài thật, lớn hơn hẳn

Câu hỏi của chủ dự án dẫn tới một phép đo chưa ai làm: câu **không mang dấu hiệu
quy trình nào** nhưng nghiệp vụ đúng là SOP thì đi đâu? Đo 2026-08-16, 6 câu
kiểu người dùng thật:

| câu | định tuyến hiện tại | đúng? |
|---|---|---|
| "hàng của đơn mua P00021 về rồi, xử lý giúp tôi" | `nhap-kho` | ✅ |
| "đơn mua P00021 vừa giao tới, làm nốt phần còn lại nhé" | `nhap-kho` | ✅ |
| "kho báo hàng P00021 đã tới, cần làm gì tiếp" | `rag` | ⚠️ mơ hồ thật |
| "đơn S00012 đóng gói xong rồi, cho đi giao" | `erp_write` | ❌ |
| "khách giục đơn S00012, xuất cho khách đi" | `erp_write` | ❌ |
| "Wood Corner mua 10 Desk Pad, tính giá cho khách này giúp tôi" | `erp_read` | ❌ |

Hệ quả thật, không phải thẩm mỹ: rơi về `erp_write` nghĩa là planner chọn **một
tool ghi đơn lẻ**, nên các bước kiểm tra mà SOP dựng ra bị bỏ qua. Ca báo giá
rơi sang `erp_read` còn nặng hơn — người dùng nhờ tính giá cho khách mà hệ thống
đi đường đọc, không tạo báo giá và không áp chính sách chiết khấu nào.

### 1.3 Vì sao bộ đo không thấy

`SOP_SELECT_CASES` có đúng **một** ca dương-không-chữ-"quy trình" mỗi skill, và
cả ba ca đó vẫn **nói rõ điều kiện ra** ("kiểm tra kỹ hàng trước khi giao", "xác
nhận đã kiểm đếm hàng… rồi mới nhập kho"). Không ca nào giống cách người ta nói
thật. Nên gate báo 16/17 và trông như chỉ có một ca lẻ hỏng, trong khi 2/3 skill
không nhận diện được theo ngữ nghĩa.

Đây là lớp lỗi lặp lại của dự án này: **phép đo không đo thứ nó tưởng đang đo.**

---

## 2. Chẩn đoán: một trường đang trả lời hai câu hỏi

Hợp đồng router hôm nay có 2 dòng:

```
intent: <erp_read | erp_write | rag | mixed | unknown>
sop:    <tên worker, hoặc để trống>
```

Khối luật cho `sop` bắt model để trống khi *"the user gives a plain one-step
command without procedure wording"*, và cả ba mô tả `SKILL.md` đều nhắc lại:
*"KHÔNG dùng khi… ra một lệnh NGẮN GỌN một bước"*.

Nghĩa là **một trường `sop` phải trả lời hai câu hỏi khác hẳn nhau**:

1. *Việc này thuộc nghiệp vụ nào?* — câu hỏi về **miền**
2. *Chạy sâu tới đâu?* — câu hỏi về **độ sâu**

Ca `"quy trình nhập kho cho đơn mua P00021"` hỏng chính vì thế: cụm "quy trình
nhập kho" nằm cả ở vế *Dùng khi* lẫn *KHÔNG dùng khi*, model khớp vế sau trước
khi kịp cân nhắc mã đơn phía sau. Ba câu chị em cùng nghĩa nhưng **mở đầu bằng
động từ** ("làm…", "nhập kho theo…") thì đậu 3/3.

Và câu đó **thật sự mơ hồ trong tiếng Việt** — đọc là *"cho tôi xem quy trình
nhập kho áp dụng cho đơn P00021"* cũng hợp lý ngang *"hãy chạy quy trình nhập
kho cho đơn P00021"*. Đó là lý do không model nào và không bản viết lại mô tả
nào chữa được: nó không phải lỗi model.

---

## 3. Bằng chứng: spike ba vòng

Toàn bộ spike chạy **không sửa file nào trong repo** — dựng prompt biến thể từ
prompt thật, đo bằng `gemini-3.1-flash-lite` (đúng model router đang chạy).

### Vòng 1 — bác bỏ phương án rẻ

Chỉ sửa khối *Rules for sop*, thêm trường `depth`. Kết quả: trong 11 dòng có
`sop` được điền, **0 dòng nào là `unsure`** — luật kích hoạt sẽ không bao giờ
bắn, node hỏi-lại thành code chết.

Lý do: **mô tả skill thắng khối luật.** Bằng chứng trực tiếp —
`"nhận hàng cho đơn mua P00003"` vẫn ra `sop=None` dù luật mới nói thẳng *"Do
NOT leave it empty merely because the command is short"*.

⇒ Muốn tách thật thì **phải viết lại mô tả `SKILL.md`**, không chỉ khối prompt.

### Vòng 2 — tách thật, và một lỗi của chính spike

Thay ba mô tả bằng bản **thuần miền**, dời toàn bộ hướng dẫn độ sâu sang
`depth`. Nhận diện ngữ nghĩa 6/6, hijack 0. Nhưng `one_step` chiếm 65% và ba câu
nói rõ "quy trình" bị gán `one_step` — tức **sẽ bỏ qua kiểm tra ở đúng những câu
đã yêu cầu quy trình đầy đủ**.

Nguyên nhân nằm ở spike, không ở model: danh sách tín hiệu `full_sop` của vòng 2
quên mất chính chữ "quy trình".

### Vòng 3 — sau khi sửa tín hiệu

| nhóm | kết quả |
|---|---|
| 6 câu đời thật, không dấu hiệu quy trình | **6/6 đúng miền** (trước: 1/6) |
| 5 câu hỏi-VỀ-quy-trình + điều chỉnh tồn kho | **5/5 `sop` rỗng**, hijack 0 |
| 3 câu nói rõ "quy trình" | **3/3 `full_sop`** |
| ca hồi quy 2026-07-16 | **`nhap-kho` + `full_sop`** ✅ |
| `unsure` | **2/18 (11%)**, cả hai mơ hồ thật |

**Ca hồi quy tự khỏi.** Nó không được nhắm tới — nó hết hỏng khi hai câu hỏi
được tách ra. Đây là bằng chứng mạnh nhất cho chẩn đoán ở §2.

### Vòng 4 — độ ổn định (3 lượt/câu)

**10/10 ca tất định**, không ca nào lệch. **Hijack 0/15.**

Hai ca `unsure` **ổn định là mơ hồ** — model không lưỡng lự ngẫu nhiên mà nhận
ra sự mơ hồ một cách nhất quán, đúng điều kiện cần để làm luật kích hoạt.

---

## 4. Hợp đồng mới

### 4.1 Router — vẫn MỘT lượt gọi, ba trường

```
intent: <erp_read | erp_write | rag | mixed | unknown>
sop:    <tên worker, hoặc để trống>
depth:  <full_sop | one_step | unsure | none>
```

**Không thêm lượt LLM thứ hai.** Giá trị nằm ở chỗ tách hai câu hỏi, không ở chỗ
gọi thêm. Router chạy trên mọi tin nhắn, và ví `gemini-3.1-flash-lite`
(`rpd=500`) đã đo được 317 lượt/ngày = 63% — nó gánh mắt xích chính của
`router` + `fusion` + `synthesis`.

Một lớp "thinking" riêng chỉ đáng bỏ tiền khi quyết định độ sâu cần **thông tin
lớp 1 chưa có** (ví dụ phải đọc xem đơn đã kiểm đếm chưa). Dựa vào câu chữ người
dùng thì lượt thứ hai không biết thêm gì. Ngoài phạm vi đợt này.

**Không dùng chain-of-thought.** Repo này có tiền sử hỏng nặng đã đo được:
`gemma-4-26b` từng đốt 2045/2048 token đầu ra vào suy luận nội bộ rồi phát ra
**0 token hiển thị** (`content=''`, HTTP 200), tất định theo cách diễn đạt — mất
nguyên một nhánh để sửa, và chính lần viết lại mô tả `nhap-kho` lượt 2 cũng chết
vì cơ chế đó (5/5 lần). Model router hiện tại được chọn một phần vì tiêu ~370
token/lượt và `emits_thought_tags=False`.

### 4.2 `sop` — chỉ còn là MIỀN NGHIỆP VỤ

Điền khi người dùng muốn **việc được làm** trong một miền đã khai, **bất kể câu
ngắn hay dài**. Để trống chỉ khi:

- người dùng chỉ **hỏi VỀ** một quy trình/chính sách (tra cứu tài liệu), hoặc
- việc không thuộc miền nào đã khai.

Cấm để trống chỉ vì câu ngắn.

### 4.3 `depth` — độ sâu, tách hẳn ra

- `full_sop` — muốn chạy đủ quy trình kèm các bước kiểm tra. Tín hiệu: nói "quy
  trình"/"SOP"/"đầy đủ"; hoặc đòi kiểm/đếm/đối chiếu; hoặc nêu điều kiện; hoặc
  mô tả nhiều bước. **Gọi tên quy trình là tín hiệu mạnh nhất** — bỏ sót đúng
  dòng này là lỗi của spike vòng 2.
- `one_step` — muốn làm ngay một bước, không kiểm tra thêm ("luôn", "ngay", hoặc
  lệnh trần nêu hành động + chứng từ).
- `unsure` — nêu đủ miền và chứng từ nhưng **không có tín hiệu nào** về độ sâu;
  hai cách đọc hợp lý ngang nhau.
- `none` — khi `sop` rỗng.

Luật viết vào prompt: **không được đoán** giữa `full_sop` và `one_step`; không
có tín hiệu thật thì `unsure`. Đoán sai một chiều là bỏ qua kiểm tra an toàn,
chiều kia là làm phiền người dùng.

### 4.4 Ba mô tả `SKILL.md` viết lại thuần miền

Toàn bộ câu *"KHÔNG dùng khi… lệnh NGẮN GỌN một bước"* **rời khỏi mô tả** và
sống ở luật `depth`. Mô tả chỉ còn nói: miền này là gì, khi nào thuộc về nó, và
khi nào là câu hỏi tra cứu.

`bao-gia-chiet-khau` đang **mỏng hơn hẳn hai cái kia** — không có câu nhận-diện-
theo-ý-định, không dấu hiệu ngữ nghĩa, không ví dụ. Đây là lý do
`"tính giá cho khách này giúp tôi"` rơi sang `erp_read`. Phải nâng ngang hai
skill kia.

Ba mô tả dưới đây là **bản đã qua spike vòng 3–4** (tất cả số đo ở §3 đo trên
đúng văn bản này). Là **điểm khởi đầu có số đo, không phải bản cuối** — plan
phải đo lại tại chỗ sau khi áp vào `SKILL.md` thật, vì `SKILL.md` còn phần thân
prompt phía dưới mà spike không nạp.

```
worker: bao-gia-chiet-khau
mô tả: Miền báo giá cho khách. Chọn worker này khi người dùng muốn LÀM một
báo giá / tính giá bán cho một khách hàng cụ thể — kể cả khi họ không nhắc
tới chữ "chiết khấu" (cấp khách và chiết khấu do chính quy trình xác định).
KHÔNG chọn khi người dùng chỉ hỏi về chính sách chiết khấu.

worker: giao-hang
mô tả: Miền giao hàng cho đơn bán. Chọn worker này khi người dùng muốn ĐƯA
HÀNG ĐI GIAO cho một đơn bán — kể cả câu rất ngắn, kể cả khi không nhắc chữ
"quy trình", kể cả khi chỉ mô tả tình huống ("đóng gói xong rồi, cho đi giao",
"khách giục đơn này, xuất cho khách"). KHÔNG chọn khi người dùng chỉ hỏi
quy trình giao hàng gồm những gì.

worker: nhap-kho
mô tả: Miền nhận hàng vào kho theo một đơn mua. Chọn worker này khi người
dùng muốn NHẬN HÀNG cho một đơn mua — kể cả câu rất ngắn, kể cả khi không
nhắc chữ "quy trình", kể cả khi chỉ mô tả tình huống ("hàng về rồi, xử lý
giúp tôi"). KHÔNG chọn khi người dùng chỉ hỏi quy trình nhập kho gồm những
gì, hoặc khi họ muốn điều chỉnh tồn kho trực tiếp không qua đơn mua.
```

Luật `depth` đã đo (§4.3) cũng chép nguyên vào plan, **đặc biệt là dòng "gọi tên
quy trình là tín hiệu mạnh nhất"** — bỏ sót đúng dòng đó là lỗi đã xảy ra ở
spike vòng 2 và nó khiến 3 câu yêu cầu quy trình đầy đủ bị gán `one_step`.

### 4.5 `decide_route` ánh xạ `(sop, depth)`

| `sop` | `depth` | đi đâu | ghi chú |
|---|---|---|---|
| rỗng | `none` | `intent` như hôm nay | không đổi |
| có | `full_sop` | node SOP đó | không đổi |
| có | `one_step` | **`erp_write`** (write planner) | **hành vi cuối GIỐNG HỆT hôm nay** |
| có | `unsure` | node `clarify` mới | đường duy nhất thật sự mới |

`one_step` → write planner là **quyết định của chủ dự án**, và nó khiến đợt này
gần như thuần **THÊM** khả năng: ba ca eval đang kỳ vọng `erp_write`
(`"giao hàng cho đơn S00040 luôn nhé"`, `"nhận hàng cho đơn mua P00003"`,
`"tạo báo giá cho Azure Interior, 2 Large Cabinet"`) **giữ nguyên kỳ vọng**, dù
router nay điền `sop` cho chúng.

### 4.6 Lớp phủ quyết tất định GIỮ NGUYÊN

`decide_route` hôm nay có lớp phủ quyết không phụ thuộc LLM: câu mang dấu hiệu
câu hỏi thì rớt `sop`, dùng `intent`. Spike cho thấy model mới tự xử đúng 15/15
ở nhóm an toàn — **nhưng đó không phải lý do để tháo một lớp phòng thủ tốn 10
dòng đã chứng minh giá trị**. Giữ, và thêm test khẳng định nó vẫn cắn.

---

## 5. Node `clarify` — hỏi lại khi `unsure`

Chỉ chạy khi `depth == "unsure"`. Hỏi đúng hai lựa chọn: chạy đủ quy trình có
kiểm tra, hay làm nhanh một bước.

### Cơ chế: dùng lại `interrupt`, không phát minh cái thứ ba

Repo đã có **hai** cơ chế hỏi-rồi-chờ, cả hai chạy production và đều dùng
`interrupt` của LangGraph:

- `ask_human` (`agentic_gate.py`) — `kind="free_text"`
- `_confirm_write` — `kind="confirm"` + TTL

`decide_route` là hàm trên **cạnh**, không phải node, nên `interrupt` không gọi
được ở đó — phải là một **node** `clarify` mà cạnh trỏ tới.

⚠️ **Bài học bắt buộc đọc trước khi thiết kế chỗ này:** cơ chế write-confirmation
bản đầu gắn tín hiệu vào `AIMessage.additional_kwargs` và **chết hoàn toàn trong
production** — `_invoke_fresh` (`erp_agent.py`) dựng lại `state["messages"]` từ
history text thuần của client nên xoá sạch, và **6 vòng review không ai thấy** vì
không test nào đi qua entry point thật. Bất kỳ tín hiệu nào phải sống qua lượt
đều PHẢI nằm ở **state field riêng** hoặc ở trạng thái parked của `interrupt`,
không bao giờ trên message.

Plan phải chốt `kind` cho lượt hỏi này (hai lựa chọn — không phải `free_text`,
không phải `confirm` nhị phân) và đường `_decide_resume` tương ứng.

### Tần suất

Đo được **2/18 (11%)** trên tập spike, và cả hai ca đều mơ hồ thật. Plan phải đo
lại tỷ lệ này trên bộ eval mở rộng — nếu vượt ~20% thì ma sát quá lớn và luật
`unsure` cần siết.

---

## 6. Đo lường

### 6.1 Bộ eval phải hết mù

`SOP_SELECT_CASES` cần thêm hai nhóm ca **hiện không có**:

1. **Ngữ nghĩa** — câu đời thật, không dấu hiệu quy trình, mỗi skill ≥2 ca. Đây
   là nhóm mà bộ đo hiện tại mù, và là nhóm chở đúng yêu cầu của chủ dự án.
2. **Độ sâu** — mỗi skill ít nhất một cặp cùng miền khác độ sâu, và ít nhất một
   ca `unsure`.

Kỳ vọng của ca phải đổi từ *một* giá trị sang *cặp* `(đích định tuyến, depth)` —
nếu vẫn chỉ chấm đích, `depth` sẽ không được canh và có thể trôi âm thầm. Đây
đúng lớp lỗi "test không đo gì" đã xuất hiện ba lần trong một đợt trước.

### 6.2 Cổng và ngưỡng

`sop_select` giữ **gate tuyệt đối** (`acc == 1.0 và hijack == 0`) — nó là hàng
rào an toàn, không phải phép đo tương đối.

Mục tiêu của đợt này là **đưa `sop_select` về xanh lần đầu kể từ 2026-07-31**,
nhờ đó nó được nhận lại vào `--set all` của job hàng đêm. Nếu không đạt, phải
nói rõ còn ca nào và vì sao, chứ không nới ngưỡng.

`intent` (n=54, baseline 0.8704) phải **không thụt** — hợp đồng đổi từ 2 dòng
sang 3 dòng chạm vào mọi lượt phân loại ý định, không chỉ SOP.

### 6.3 Rủi ro hai chiều, phải đo cả hai

| chiều | biểu hiện | đo bằng |
|---|---|---|
| nới quá tay | câu hỏi VỀ quy trình bị SOP cướp | `hijack` phải = 0 |
| siết quá tay | câu đời thật không vào được SOP | nhóm ca ngữ nghĩa mới |

### 6.4 Vai không phải admin

Toàn bộ spike chạy trên vai `admin`. Vai **kế toán có 0 skill** ⇒ khối worker
RỖNG ⇒ `sop` luôn rỗng, `depth` luôn `none`. Phải có test khẳng định hợp đồng 3
dòng không làm hỏng gì ở cấu hình đó — khối worker rỗng **đã từng làm router
phân loại lệnh ghi thành `unknown` 3/3** và chỉ nghiệm thu sống mới bắt được.

### 6.5 Nghiệm thu sống

Bắt buộc, và phải chạy qua **entry point HTTP thật** chứ không gọi graph trực
tiếp — xem lại §5 về `_invoke_fresh`. Tối thiểu: một ca `full_sop`, một ca
`one_step`, một ca `unsure` đi trọn vòng hỏi-đáp, và một câu hỏi-VỀ-quy-trình để
xác nhận không hijack.

---

## 7. Ngoài phạm vi

- **Lớp thinking riêng đọc dữ liệu ERP trước khi quyết độ sâu** (§4.1). Chỉ đáng
  làm khi có ca thật chứng minh câu chữ người dùng không đủ.
- **Thêm cột `role` vào `llm_usage`** — nợ M3, đã đo và ghi nhận, chủ dự án chọn
  chưa làm.
- **Chuỗi/model router** — không đụng.
- **Bản thân nội dung ba SOP** (các bước bên trong node) — không đụng; đợt này
  chỉ đổi cách VÀO chúng.

---

## 8. Quy ước cho implementation plan

- **Định danh trong `backend/src` viết bằng tiếng Anh.** Người thực thi chép
  nguyên code trong plan, nên plan để lọt tên biến tiếng Việt là plan sinh lỗi —
  đã xảy ra ở năm plan liên tiếp.
- **Tên hàm test giữ quy ước chuyển tự tiếng Việt** (`test_khong_hijack_...`) —
  đây là quy ước có chủ đích của `backend/tests`, KHÔNG phải vi phạm luật trên.
- **Mọi lệnh pytest trong plan phải kèm `-m "not integration and not live"`.**
  Lệnh trần gọi API LLM thật và đã gây sự cố.
- Số ca eval trong plan phải **đếm lại tại thời điểm viết** bằng `--collect-only`,
  không chép từ spec này.
