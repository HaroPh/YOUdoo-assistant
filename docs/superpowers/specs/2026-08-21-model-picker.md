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
