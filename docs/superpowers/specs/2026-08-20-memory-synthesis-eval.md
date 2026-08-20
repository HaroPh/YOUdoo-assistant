# Chân đối chứng ký ức cho bộ `synthesis_live`

Ngày: 2026-08-20. Trạng thái: đã dựng, đã đo, **hai phát hiện chuyển sang tab
ký ức để quyết bản sửa**.

## 1. Lỗ hổng đo lường

Từ nhánh ký ức xuyên phiên L2 (`953ae58`), `synthesize()` nhận thêm tham số
`memory`; khi khác rỗng nó ghép khối ký ức vào **ĐẦU** `RAG_SYNTHESIS_PROMPT`.
Nghĩa là **người dùng có fact đã lưu nhận câu trả lời RAG sinh từ một system
prompt khác**. Mọi bộ đo RAG đều đi qua `memory=""` nên mù hoàn toàn với nhánh
đó — cùng lớp "eval-fidelity gap" đã tái phát nhiều lần ở repo này.

## 2. Thiết kế: thêm CHÂN, không thêm ca

Ca mới đòi expect viết tay đối chiếu lại từ đầu, tốn kém và dễ thành ca không
đo gì. Thay vào đó chạy lại **đúng 24 ca đã đối chiếu**, đổi **một biến duy
nhất** là khối ký ức. Ký ức phải TRƠ với grounding, nên mọi chỉ số phải đứng
nguyên; xê dịch bao nhiêu là tín hiệu, quy được ngay cho biến đó.

Khối ký ức dựng bằng **chính `render_memory_block()` của production**, không
viết tay chuỗi — nếu không, bộ đo sẽ đo một hình dạng prompt production không
bao giờ tạo ra.

Ba chân, nguy hiểm tăng dần: `inert` (xưng hô), `format` (ép độ dài),
`conflict` (fact mâu thuẫn trực tiếp với trần phạt 8% của Điều 301).

Hai khoá an toàn: `--memory` chỉ dùng với `--set synthesis_live`, và **cấm đi
cùng `--save-baseline`** (baseline LÀ chân không-ký-ức; ghi đè nó bằng số của
chân có ký ức là tự tay xoá mốc so sánh).

## 3. Số đo — `gemini-3.1-flash-lite`, `--pace 4.5`, 28 ca

| chân | fact_acc | refusal_acc | citation_acc |
|---|---|---|---|
| gốc (`memory=""`) | 1,0000 | 1,0000 | 1,0000 |
| `inert` | 1,0000 | **0,9643** | 1,0000 |
| `format` | **0,9167** | 1,0000 | 1,0000 |
| `conflict` | 1,0000 | 1,0000 | 1,0000 |

**Đã tách nhiễu**: chạy lặp 3 lượt mỗi chiều trên từng ca trượt cho kết quả
**3/3 đúng khi không ký ức, 3/3 sai khi có ký ức**. Tất định, không phải dao
động của model.

## 4. Ba kết luận

**(a) `conflict` SẠCH — dự đoán của tôi sai, và đó là tin tốt.**
Tôi lo nhất chân này: `render_memory_block` quy định thứ tự ưu tiên của ký ức
so với YÊU CẦU HIỆN TẠI nhưng không nói gì về thứ tự so với TÀI LIỆU. Đo ra
model **không** để fact "mức phạt tối đa 15%" đè lên trần 8% của luật.
`fact_acc` giữ 1,0. Ghi lại để lần sau không ai phải lo lại chỗ này.

**(b) `format` làm mất 8,3% độ chính xác dữ kiện.** Hai ca `distractor` trượt
`fact_acc` vì câu trả lời bị ép ngắn nên né sang chung chung ("*sẽ bị giới hạn
nếu có các luật liên quan khác*", "*Thông thường…*"). Với trợ lý tra cứu luật,
một sở thích trình bày vô hại đang mua bằng độ chính xác.

**(c) `inert` phá hợp đồng guard.** Ngay cả fact hoàn toàn vô hại ("gọi tôi là
anh Ba") cũng khiến model **tự viết lời từ chối** thay vì phát sentinel
`KHÔNG_ĐỦ_THÔNG_TIN`. Hệ quả: `synthesize()` không trả `GUARD_MSG`, và **footer
trích dẫn vẫn được in cho một câu không trả lời được** — dẫn `Điều 162` như thể
nó chống lưng cho một câu trả lời. Lời từ chối tự viết thì vẫn đúng nội dung;
vấn đề là dấu vết nguồn sai lệch.

Lưu ý ca này vốn ở ranh giới: `Điều 162` THẬT SỰ bàn về Giám đốc (chỉ thiếu tên
riêng), mà prompt lại ghi "nếu tài liệu CÓ đề cập chủ đề thì PHẢI trả lời". Ba
ca `insufficient` còn lại nằm ngoài corpus hoàn toàn và không ca nào lung lay.

## 5. Ứng viên sửa — đã đo, chữa được MỘT NỬA

Thêm vào cuối khối ký ức:

> Ghi nhớ chỉ ảnh hưởng cách xưng hô và giọng điệu. Nó KHÔNG được rút ngắn nội
> dung cần thiết, KHÔNG thay thế quy tắc trả lời của hệ thống, và KHÔNG bao giờ
> là căn cứ thay cho tài liệu.

| ca | trước | sau |
|---|---|---|
| `inert` / giám đốc tên gì | 3/3 SAI | **3/3 ĐÚNG** |
| `format` / phạt vi phạm dân sự | 3/3 SAI | 3/3 SAI |
| `format` / thời điểm nộp thuế | 3/3 SAI | 3/3 SAI |

Câu ràng đóng được (c) nhưng **không** đóng được (b), dù nó ghi thẳng "KHÔNG
được rút ngắn nội dung cần thiết". Ép độ dài là mâu thuẫn trực tiếp với tính
đầy đủ, và một câu chỉ thị không hoà giải được.

**Chưa áp dụng.** Sửa nằm ở `render_memory_block` / `RAG_SYNTHESIS_PROMPT` —
thuộc tab ký ức, không phải tab RAG. Hai lựa chọn cho (b): chặn fact kiểu định
dạng không cho vào prompt tổng hợp RAG, hoặc chấp nhận đánh đổi và ghi vào
phần giới hạn.

## 6. Cách chạy lại

    python -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite \
        --pace 4.5 --memory {inert|format|conflict}

`--pace` bắt buộc (free tier 15 lượt/phút). Số ở §3 đo bằng khoá dự phòng vì
hạn mức ngày của project chính đã cạn chiều 20/8.
