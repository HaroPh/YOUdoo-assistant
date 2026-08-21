# Người dùng chọn model, kèm báo khi tụt mắt xích

Ngày: 2026-08-21. Trạng thái: đã cài, 1902 test default + 52 integration xanh.

## 1. Vấn đề

Bảy vai, bảy chuỗi khác nhau, bốn mắt xích đầu khác nhau. Chủ dự án thấy việc
chia model theo "độ quan trọng của task" là rườm rà và làm hệ rời rạc, và muốn
**một model cho cả luồng, người dùng tự chọn** — giống chọn Opus/Sonnet.

Rà lại thì bảng gán cũ **phân bổ gần như ngược với lưu lượng**:

| model | rpd | vai |
|---|---|---|
| `gemini-3.5-flash` | **20** | `chitchat` |
| `gemini-3.1-flash-lite` | 500 | `router`, `synthesis`, `fusion` |
| `gemini-3.5-flash-lite` | 500 | `planner`, `read` |
| `gemma-4-26b` | **14 400** | `evaluator` |

Tán gẫu ăn model mạnh nhất **nhưng chỉ 20 lượt/ngày** — tức từ tin nhắn thứ 21
trở đi Groq trả lời, và **không ai từng biết** vì không có dòng báo nào. Còn
model dung lượng lớn nhất thì đậu trên vai chạy ít nhất.

## 2. Cài đặt — ba mảnh, cả ba đã có sẵn đường

**Chọn model**: `/v1/models` trước đây trả đúng MỘT mục và trường `model` trong
request **chưa ai đọc**. Liệt kê lựa chọn thật ở đó là toàn bộ phần giao diện —
**dropdown của Open WebUI đã có sẵn**, không dựng UI mới. Tên hiển thị là TÊN
MODEL THẬT, không phải nhãn "Nhanh / Chính xác": nhãn kiểu đó là lời hứa về kết
quả mà chưa ai đo, còn mục đích của việc cho chọn chính là để biết model nào
đang trả lời.

**`prefer`, KHÔNG phải `pin`**: Router đã có `pin` nhưng nó **bỏ qua toàn bộ
chuỗi**, thử một lần, không fallback (eval dùng để quy kết quả). `prefer` chỉ
ĐỔI THỨ TỰ — mắt xích đầu cũ **tụt xuống làm dự phòng**. Nhầm hai thứ này là mất
fallback mà không có gì báo. Có test khoá.

**Báo fallback**: `fallback_depth` trước đây chỉ đi vào Langfuse, chưa từng tới
người dùng.

## 3. Cái bẫy làm hỏng kế hoạch đầu, và cách vòng qua

Kế hoạch đầu là đọc `_QUYET_DINH` (ContextVar sẵn có) ở lớp bọc `erp_agent` sau
mỗi lượt. **Hỏng.** Chú thích trong `router.py` đã cảnh báo, và đo lại bằng
graph thật thì đúng: **giá trị `set()` bên trong một asyncio.Task KHÔNG lan
ngược về cha**. Node LangGraph chạy trong task con; cha đọc thấy `{}`.

Cách dùng được — cũng đã đo bằng graph thật: cha đặt sẵn một dict **khả biến**,
node **sửa tại chỗ**. Chiều xuôi thì ContextVar lan bình thường.

Mặc định của thùng là **None chứ không phải `{}`**: một dict mặc định dùng chung
mọi ngữ cảnh, sửa tại chỗ trên nó là rò rỉ giữa các request — đúng thứ chú thích
của `_QUYET_DINH` đang tránh.

Ghi tại `RoutedChatModel` — **chỗ nghẽn duy nhất** mọi lượt gọi LLM đi qua —
thay vì sửa từng node. Sửa từng node chính là lỗi "năm chỗ ghép, đếm nhầm thành
bốn" vừa xảy ra ở tính năng ký ức.

Dòng thông báo gắn **sau** `_apply_memory_markers` và **trước** `localize`: sau,
vì nó là văn bản cuối câu trả lời — đúng vùng `NGUỒN_DÙNG:` và `ĐỀ_XUẤT_GHI`
sống; trước, để người dùng tiếng Anh nhận nó bằng tiếng Anh.

## 4. Chọn model mặc định — và tôi đã đổi ý sau lượt lặp

Đo `read` / `planner` / `intent`, mỗi bộ 2 lượt:

| | intent acc | intent p95 | read | planner |
|---|---|---|---|---|
| `3.1-flash-lite` | **0,9444 · 0,9444** | 11 220 · 7 900ms | 1,0 | 1,0 |
| `3.5-flash-lite` | 0,9074 · 0,8889 | **1 058 · 1 073ms** | 1,0 | 1,0 |

`read`/`planner` **bão hoà** (cả hai 1,0) nên không phân biệt được — chỉ `intent`
còn dư địa.

**Lượt đầu tôi nghiêng 3.5** vì chênh acc trông như nhiễu. Lượt lặp cho thấy nó
ổn định: 3.1 giữ đúng 0,9444 cả hai lần, 3.5 dao động 0,89–0,91. Chênh 4-6 điểm
phần trăm, có thật.

**Chọn 3.1 dù CHẬM HƠN 7-10 lần ở đuôi**, vì hai kiểu hỏng không cùng hạng:
chậm là hỏng **lớn tiếng** (người dùng thấy, không nhận thông tin sai); định
tuyến nhầm là hỏng **im lặng** — câu `mixed` bị phân thành nguồn đơn nên thiếu
hẳn nửa tài liệu mà người dùng không biết là thiếu. Mặc định phục vụ người không
bao giờ đổi lựa chọn; với họ, thiếu âm thầm tệ hơn chậm.

Ai ưu tiên tốc độ thì đổi ở dropdown — **đó chính là lý do tính năng này tồn
tại**, và nó biến một đánh đổi bắt buộc thành một lựa chọn.

## 5. Giới hạn còn lại

- **Gộp về một model nghĩa là bảy vai chia CHUNG một ví 500 lượt/ngày**, thay vì
  ba ví như trước. Đổi lại chuỗi dự phòng nay giàu hơn (mắt xích đầu cũ tụt
  xuống làm dự phòng) nên suy giảm êm, và dòng báo cho người dùng biết.
- `gemma-4-26b` (rpd 14 400) là model DUY NHẤT đủ sức gánh cả hệ một mình.
  **Chưa đo** trên các vai này nên chưa cho chọn. Nếu hạn mức thành nút thắt,
  đây là ứng viên đáng đo trước tiên.
- `gemini-3.5-flash` (rpd 20) **cố ý không cho chọn** — làm dự phòng thì được.
- Chưa đo chuỗi thật sự tụt trên production (cần một model cạn hạn mức thật).

## 6. Bổ sung: chênh lệch acc giữa hai model phần lớn là do PROMPT, không do model

Ngày 2026-08-21, sau §4.

§4 chọn 3.1 làm mặc định vì nó hơn 3.5 khoảng 4-6 điểm phần trăm ở `intent`. Soi
ca trượt thì **mọi ca đều cùng một khuôn**: *"đối chiếu một bản ghi ERP với một
quy tắc trong tài liệu"* — trễ SLA chưa, có vi phạm SLA không, có khớp bảng giá
không, có dưới ngưỡng trong SOP không.

Prompt tả `mixed` bằng **đúng một ví dụ**, và nó là dạng **nêu chính sách ra
trước**: *"theo chính sách hoàn hàng, đơn của khách X có được hoàn không?"*.
Toàn bộ ca trượt là dạng **nhúng** — tên tài liệu nằm lẫn trong câu như một
thuộc tính. **Prompt dạy một hình thái, thực tế hỏng ở hình thái khác.**

**Bản vá**: thêm một quy tắc chung (không phải chép ca trượt vào làm ví dụ — làm
thế thì acc lên là đương nhiên và chứng minh được gì). Ví dụ dùng trong prompt
là một câu KHÁC cùng khuôn.

| bộ | model | trước | sau |
|---|---|---|---|
| `intent` | 3.1 | 0,9444 · 0,9444 | **0,9630 · 0,9630** |
| `intent` | 3.5 | 0,9074 · 0,8889 | **0,9630 · 0,9815** |
| `sop_select` | 3.1 | 0,9259 | **0,9630** |
| `sop_select` | 3.5 | 0,8889 | 0,8889 |
| `hijack` | cả hai | 0 | **0** |

Prompt dùng chung cho vai `intent` VÀ `sop_select` nên phải đo cả hai; `hijack`
là bất biến an toàn của router và nó giữ 0 ở cả bốn lượt.

Diacritics đã kiểm riêng: bản không dấu và bản có dấu cho cùng 0,9630 — bản đo
đầu dùng tiếng Việt không dấu do vướng heredoc, nên phải đo lại bản có dấu trước
khi áp, vì áp một văn bản khác bản đã đo là không đo gì cả.

### 6.1 Hệ quả: nên xét lại model mặc định

**Hai model nay HỘI TỤ** (3.1: 0,9630 · 0,9630; 3.5: 0,9630 · 0,9815). Khoảng
cách 4-6 điểm — căn cứ DUY NHẤT để §4 chọn 3.1 — **đã đóng**, và ở lượt thứ hai
3.5 còn nhỉnh hơn.

Nếu acc ngang nhau thì tiêu chí còn lại là độ trễ, và ở đó 3.5 nhanh hơn ~2 lần
ở trung vị (951ms vs 2000ms, đo bằng prompt router thật). Tức lập luận của §4
nay nghiêng về 3.5.

**CHƯA đổi mặc định.** Số của 3.5 sau vá là 0,9630 và 0,9815 — hai lượt chênh
nhau một ca, nên chưa chốt được nó ngang hay hơn. Cần thêm lượt lặp, và hạn mức
ngày của 3.5 đã cạn lúc đo (phải mượn khoá dự phòng). Đây là việc đáng làm khi
hạn mức reset.

### 6.1.1 CHỐT 2026-08-21: giữ 3.1

Chủ dự án quyết **giữ `gemini-3.1-flash-lite` làm mặc định**. Không cần đổi code
— hằng số `MODEL_MAC_DINH` đã là giá trị đó.

Ghi lại cho rõ, vì quyết định này đi **ngược chiều** số đo mới nhất và người đọc
sau sẽ vấp vào §6.1 rồi tưởng đây là nợ chưa đóng:

- Số sau vá cho thấy 3.5 **ngang**, không cho thấy nó **hơn**. Đổi mặc định cần
  bằng chứng nó hơn, không phải bằng chứng nó không kém — mặc định đang chạy có
  quyền được giữ khi hoà.
- Lập luận bất đối xứng của §4 **vẫn còn nguyên**: chậm là hỏng lớn tiếng, định
  tuyến nhầm là hỏng im lặng. Nó không phụ thuộc vào chênh lệch 4-6 điểm đã
  đóng, nên vá prompt không xoá được nó.
- Tốc độ nay là **lựa chọn chứ không phải đánh đổi bắt buộc** — ai cần thì đổi ở
  dropdown. Đó chính là thứ tính năng này sinh ra để giải quyết.

**Điều kiện mở lại**: có số cho thấy 3.5 acc **hơn** 3.1 ổn định qua nhiều lượt.
"Cần thêm lượt lặp" ở §6.1 **không còn là việc đang treo** — nó là điều kiện mở
lại, không phải hàng đợi.

### 6.2 Ca CHƯA chữa được

*"lệnh sản xuất mới có cần kiểm tra chất lượng theo SOP trước khi hoàn tất
không?"* → `rag` thay vì `mixed`, trượt ở **mọi model, mọi phiên bản prompt**.
Nó khác các ca kia: "lệnh sản xuất mới" chưa phải một bản ghi cụ thể, nên câu
này thật sự nằm ở ranh giới.

Và bản vá tạo ra **một ca trượt ngược chiều**: *"phiếu giao hàng nào đang trễ
hạn?"* → `mixed` trong khi kỳ vọng `erp_read`. Ròng vẫn dương, nhưng nó cho thấy
ranh giới `mixed`/`erp_read` mảnh — đừng siết thêm quy tắc mà không đo.
