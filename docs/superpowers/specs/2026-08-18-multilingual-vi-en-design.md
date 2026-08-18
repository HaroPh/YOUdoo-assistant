# Đa ngôn ngữ Việt–Anh — thiết kế

**Ngày:** 2026-08-18
**Trạng thái:** đã đo bằng spike, chờ duyệt để viết implementation plan
**Xuất phát từ:** quyết định hoãn ngày 2026-08-15 ("có, nhưng chưa phải bây giờ") nay được mở lại

---

## 1. Đề bài

Youdoo hôm nay chỉ nói tiếng Việt. Người dùng gõ tiếng Anh vẫn nhận câu trả lời
tiếng Việt. Mục tiêu: hỗ trợ **đúng hai** ngôn ngữ — Việt và Anh — mọi thứ khác
rơi về tiếng Việt.

Hồ sơ 2026-08-15 ước lượng đợt này gồm ba phần: (1) 4 prompt ghim cứng tiếng
Việt, (2) ~90 chuỗi thông báo ở ba tầng, (3) tầng nhận diện ngôn ngữ chưa tồn
tại. **Spike ngày 2026-08-18 cho thấy ước lượng đó sai ở phần nặng nhất** —
xem §2.

## 2. Bằng chứng: spike đo qua HTTP thật

Toàn bộ số dưới đây đo bằng cách vá prompt trên một nhánh spike, chạy backend
thật, gọi qua đúng entry point HTTP. Không có số nào là suy luận.

### 2.1 Ba vòng đầu — hai giả thuyết bị BÁC BỎ

| biến thể | hỏi tiếng Anh |
|---|---|
| **E1** — đổi câu *"trả lời bằng tiếng Việt"* thành *"reply in the same language"* | ❌ trả lời **toàn tiếng Việt** |
| **E2** — E1 + sửa luật `display` thành *"diễn đạt lại theo ngôn ngữ người dùng"* | ❌ vẫn **toàn tiếng Việt** |
| **E3** — thêm khối `LANGUAGE RULE` ở **CUỐI** prompt, dứt khoát | ✅ **toàn tiếng Anh**, dịch cả nhãn |

Kết luận: thủ phạm **không phải** luật `display` (E2 bác bỏ điều đó). Thủ phạm
là **vị trí và độ dứt khoát** của chỉ dẫn — một hai câu tiếng Anh lọt giữa một
prompt toàn tiếng Việt không lật nổi ngôn ngữ đầu ra.

### 2.2 Hệ quả lớn: tầng 2 KHÔNG cần dịch

~200 chuỗi ở tầng MCP (`mcp-servers/odoo/tools/`) và tầng đọc
(`backend/src/erp_query/`) trả JSON, LLM đọc rồi **tự viết lại**. Với
`LANGUAGE RULE` đúng cách, chúng ra tiếng Anh **mà không sửa một chuỗi nào**.
Đây là phần lớn nhất của khối lượng ước lượng ban đầu, và nó biến mất.

### 2.3 Đo nhiều ca — phát hiện chỉ lộ ra khi không dừng ở một ca

| đường đi | hỏi tiếng Anh | hỏi tiếng Việt |
|---|---|---|
| `erp_read` (2 ca) | ✅ | ✅ |
| `chitchat` | ✅ | ✅ |
| `rag` (2 ca) | ✅ (thân câu) | ✅ |
| `mixed` / fuse | ❌ → ✅ sau khi sửa thêm | ✅ |
| **`erp_write` (câu xác nhận)** | ❌ **tiếng Việt** | ✅ |

**`mixed` hỏng vì `FUSE_PROMPT` tự mâu thuẫn**: đầu prompt ghi *"trả lời bằng
tiếng Việt"*, cuối prompt là `LANGUAGE RULE`. Ở các đường khác quy tắc cuối vẫn
thắng; riêng fuse — nơi ngữ cảnh nạp vào là hàng loạt đoạn tài liệu tiếng Việt
**cộng** dữ liệu ERP tiếng Việt — sức nặng tiếng Việt đủ để câu mở đầu thắng
lại. Gỡ câu mở đầu là đúng ngay.

⇒ **Luật rút ra:** phải GỠ chỉ dẫn ngôn ngữ ghim cứng ở đầu **và** THÊM khối
quy tắc ở cuối. Làm nửa vời sẽ hỏng đúng ở đường phức tạp nhất.

**`erp_write` ra tiếng Việt là ĐÚNG NHƯ DỰ ĐOÁN** — câu xác nhận không do LLM
sinh ra. Đây là bằng chứng thực nghiệm cho §4.

### 2.4 Bẫy đo lường đã gặp

Bộ dò "lọt tiếng Việt" của spike đếm nhầm phần **trích dẫn nguồn** (tên tài
liệu tiếng Việt) là lỗi. Tên tài liệu/sản phẩm/đối tác là **danh từ riêng**,
giữ nguyên mới đúng. Bộ eval của đợt này bắt buộc phải phân biệt **nhãn** với
**danh từ riêng**, nếu không nó sẽ báo động giả mãi mãi.

## 3. Tầng 1 — bốn prompt

Sửa cả bốn (`SYSTEM_PROMPT`, `CHITCHAT_PROMPT`, `RAG_SYNTHESIS_PROMPT`,
`FUSE_PROMPT`) theo đúng công thức đã đo:

1. **Gỡ** chỉ dẫn ngôn ngữ ghim cứng ở đầu ("trả lời bằng tiếng Việt").
2. **Thêm** khối `LANGUAGE RULE` ở cuối, nói rõ: viết câu trả lời cuối cùng
   bằng **cùng ngôn ngữ với tin nhắn mới nhất của người dùng**; dịch mọi nhãn
   lấy từ tool/tài liệu; **danh từ riêng giữ nguyên**.

**Tầng này KHÔNG cần biết `lang`.** LLM tự nhìn tin nhắn. Đây là điểm khác biệt
lớn so với thiết kế phác ban đầu và nó xoá cả một lớp phụ thuộc.

⚠️ Bốn prompt này là thứ các cổng `read`, `planner`, `multi_source`,
`synthesis` đang đo. Mọi bước sửa phải chạy lại các cổng đó, không chỉ chạy
test.

## 4. Tầng 3 — chuỗi điều phối ghi (phần khó duy nhất còn lại)

Những chuỗi này **chính là** câu trả lời: `_msg()` tạo thẳng `AIMessage`, và
`question` của `interrupt` đi thẳng ra người dùng. Không LLM nào đứng giữa, nên
§3 không chạm tới được.

**Quyết định của chủ dự án (2026-08-18): cho LLM dịch**, thay vì dựng bảng
thông điệp hai ngôn ngữ.

Rủi ro đã nêu và đã được chấp nhận: nếu bản dịch làm sai số liệu hoặc mã chứng
từ, người dùng có thể **duyệt nhầm một thao tác ghi thật**. Thiết kế dưới đây
chặn đúng rủi ro đó.

### 4.1 Một chốt duy nhất, không sửa 188 điểm gọi

Đặt `localize()` tại **nơi chuỗi rời khỏi hệ thống**, trong `ERPAgent.chat()`.

`chat()` hiện có **SÁU** chỗ `return` (đã đếm trong mã, không ước lượng): câu
nhắc nhập, câu từ chối vai, câu hỏi-lại của `_decide_resume`, `RECURSION_MSG`,
`question` của interrupt, và nội dung message cuối. Vá từng chỗ là để sót —
đúng lớp lỗi "danh sách khai báo thiếu âm thầm" đã tái phát nhiều lần ở repo
này.

⇒ Đổi thân hàm hiện tại thành `_chat_inner()` và để `chat()` chỉ còn là lớp
bọc: `return await self._localize(await self._chat_inner(...), lang)`. Một chốt,
phủ **mọi** đường ra kể cả những đường thêm sau này, không đụng điểm gọi nào.

### 4.2 Tự cổng, không dịch thừa

- `lang == "vi"` → trả nguyên văn. **Hành vi hôm nay byte-identical**, chi phí 0.
- `lang == "en"` **và** văn bản có dấu tiếng Việt → mới dịch. Câu trả lời do LLM
  sinh sẵn bằng tiếng Anh không có dấu tiếng Việt nên **không bị đụng tới**.

### 4.3 Lớp phủ quyết tất định

Sau khi LLM dịch, kiểm bằng code: mọi **con số**, **số tiền** và **mã chứng từ**
(`P00021`, `S00012`, `WH/OUT/00001`, `E-COM07`) trích từ bản gốc phải xuất hiện
**nguyên vẹn** trong bản dịch. Lệch bất kỳ cái nào → **trả về bản tiếng Việt**.

Model được phép đổi *câu chữ*, không được phép đổi *sự việc*. Đây đúng khuôn
"lớp xác suất + lớp phủ quyết tất định" mà repo đã dùng ở `decide_route` và
`verify_erp_grounding`.

Không bao giờ ném: mọi lỗi → bản gốc tiếng Việt.

## 5. Nhận diện ngôn ngữ

Chỉ §4 cần biết `lang`. Tất định, không LLM:

- Tin nhắn có ký tự đặc trưng tiếng Việt (`ăâđêôơư` + dấu thanh) → `vi`.
- Không có, và có ít nhất một hư từ tiếng Anh → `en`.
- Mọi trường hợp khác → `vi` (fail-safe, giữ hành vi hôm nay).

Người viết tiếng Anh nhưng nhắc tên sản phẩm tiếng Việt sẽ bị nhận là `vi` —
chấp nhận được, vì đó là chiều an toàn.

⚠️ **`lang` phải lưu vào `ERPAgentState`, xác định ở lượt MỞ ĐẦU luồng, không
nhận diện lại ở lượt trả lời.** Lượt xác nhận thường chỉ là `"có"` / `"yes"` /
`"1"` — quá ngắn để nhận diện. Đây đúng lớp lỗi mà cơ chế write-confirmation
bản đầu đã mắc: tín hiệu sống-qua-lượt phải nằm ở state/checkpointer.

## 6. Đo lường

Bộ eval mới `localize`, gác hai thứ:

1. **Sự việc sống sót**: dịch xong, mọi số và mã chứng từ còn nguyên.
2. **Cổng rơi về đúng chiều**: cố tình phá bản dịch → phải trả bản tiếng Việt.

Cộng một bộ smoke song ngữ theo §2.3 (mỗi đường đi một ca mỗi ngôn ngữ), với bộ
dò **phân biệt nhãn và danh từ riêng** (§2.4).

Bốn cổng hiện có phải chạy lại và **không được thụt**.

## 7. Ngoài phạm vi

- Ngôn ngữ thứ ba.
- Dịch tên tài liệu/sản phẩm/đối tác (danh từ riêng — giữ nguyên là đúng).
- Bảng thông điệp hai ngôn ngữ (đã cân nhắc và bác ở §4; nếu §4.3 rơi về tiếng
  Việt quá thường xuyên khi đo thật thì mở lại quyết định này).
