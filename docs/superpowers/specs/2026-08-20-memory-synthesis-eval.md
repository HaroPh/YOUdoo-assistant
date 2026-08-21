# Chân đối chứng ký ức cho bộ `synthesis_live`

Ngày: 2026-08-20. Trạng thái: đã dựng, đã đo, **đã quyết và đã sửa** (§7).

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

## 7. Quyết định của tab ký ức — CẮT dây nối, không thêm câu ràng

Chốt: **ký ức không còn được ghép vào prompt tổng hợp RAG.** `rag_node` gọi
`synthesize(query, result, llm)` không kèm `memory`.

**Vì sao không dùng câu ràng đã đo.** Câu ấy chữa được (c) nhưng mở đầu bằng
*"Ghi nhớ chỉ ảnh hưởng cách xưng hô và giọng điệu"*, trong khi
`render_memory_block()` cấp cho **cả ba** prompt. Hai trong ba ca `fact` của
`MEMORY_CASES` là fact NỘI DUNG chứ không phải giọng điệu — `kho chính của tôi
là WH/Stock`, `đơn khẩn nghĩa là giao trong 24h`. Dán câu đó vào hàm là bảo
model bỏ qua đúng những fact mà tính năng này sinh ra để lưu. Chữ *"căn cứ thay
cho tài liệu"* cũng chỉ có nghĩa ở đường RAG. Câu ràng đúng cho MỘT đường,
không đúng làm phát biểu toàn cục.

**Vì sao cắt hẳn thay vì đặt câu ràng riêng cho đường RAG.** Xâu §3 lại theo
loại fact thì ký ức trên đường tài liệu **không loại nào dương**: giọng điệu
phá hợp đồng guard, ép định dạng mất 8,3% fact_acc, fact nội dung bị bỏ qua
đúng thiết kế nên đóng góp bằng không. Cắt đóng cả (b) lẫn (c) tại gốc, không
cần phân loại fact bằng heuristic từ khoá (hỏng thì hỏng im lặng), và là lựa
chọn **duy nhất đã có sẵn số đo** — chân gốc `memory=""` chính là nó: 1,0/1,0/1,0.

**Giá phải trả, nói rõ:** câu trả lời tra cứu tài liệu không xưng hô theo tên
người dùng và không theo sở thích trình bày. Ký ức giữ **nguyên hiệu lực** ở
`erp_node` và `chitchat`. Với trợ lý tra cứu luật, tính toàn vẹn của dấu vết
trích dẫn đắt hơn một lời chào.

**Chống trôi.** `test_rag_node_nap_khoi_ky_uc` bị **đảo chiều** thành
`test_rag_node_KHONG_nap_khoi_ky_uc` chứ không xoá — một quyết định đã đo cần
chặn trôi cả hai chiều. Đã chứng minh bằng phép thử ngược: nối lại `memory=`
thì test đỏ. Test còn kèm `assert llm.system_prompts` vì khẳng định phủ định sẽ
xanh giả nếu node không gửi prompt nào.

**Ba chân `--memory` giữ nguyên, đổi vai thành DÂY BẪY.** Chúng không còn đo
đường production; comment trong `run_eval.py` đã sửa để không ai đọc nhầm số
của chân khác rỗng thành số production. Nối lại ký ức vào đường tài liệu thì
chạy lại ba chân này là thấy thiệt hại ngay.

## 8. Nợ đã đóng: bộ `memory` nay cũng có chân đối chứng

Cả 7 ca `MEMORY_CASES` vốn chạy với khối RỖNG (một lượt, không fact có sẵn),
trong khi production từ lượt thứ hai trở đi LUÔN có khối khác rỗng. §3 chứng
minh khối ký ức ĐỦ SỨC lấn một chỉ thị định dạng cứng, nên rủi ro "càng nhiều
fact thì marker càng dễ tịt" là thật — và nó nhắm đúng cơ chế mà tính năng ký
ức sống nhờ. Đã dựng chân `--memory` cho bộ này (ghép y hệt production:
`memory + "

" + prompt`, nodes.py:51/:139) và ĐO.

**Kết quả: không quan sát thấy suy giảm.** `gemini-3.1-flash-lite`, `--pace 4.5`:

| chân | số lượt | false_injection | leaked_doc_code | truncated_answer | recall |
|---|---|---|---|---|---|
| gốc (khối rỗng) | 1 | 0 | 0 | 0 | 1,0 |
| `inert` | 3 | 0 | 0 | 0 | 1,0 |
| `format` | 2 | 0 | 0 | 0 | 1,0 |

Cộng lại **15/15 ca sinh marker đều phát đúng** khi có khối ký ức khác rỗng, 0
lượt hỏng. Chân `format` ("luôn trả lời gọn trong đúng 2 đoạn") là chân đáng lo
nhất — sức ép độ dài đối đầu trực tiếp với việc phải in thêm một dòng marker —
và nó không nuốt marker lần nào.

**Giới hạn của kết luận này, nói thẳng vì đây là kết quả PHỦ ĐỊNH:** mỗi lượt
chỉ có 3 ca sinh marker, mỗi chân gieo đúng MỘT fact, và `ĐỀ_XUẤT_GHI` không
nằm trong bộ ca này (`MEMORY_CASES` không có ca ghi/xác nhận) nên hợp đồng token
đó vẫn chưa được đo với khối khác rỗng. Một suy giảm tất định như §3 hẳn đã lộ
ra; một suy giảm xác suất thấp thì cỡ mẫu này không thấy được.

**Lượt thứ ba của `format` bỏ dở: cạn hạn mức NGÀY của khoá dự phòng.** Đã
phân biệt được với giới hạn phút — chạy lại ở `--pace 9` (~6,7 lượt/phút, thừa
dưới trần 15) vẫn cooldown. Sổ `llm_usage` không phản ánh chuyện này vì nó chỉ
ghi lượt THÀNH CÔNG.

**Một khiếm khuyết của chính bộ đo, đã vá:** thông điệp `INFRA ERROR` có dấu
tiếng Việt làm CHÍNH dòng in lỗi ném `UnicodeEncodeError` trên console cp1252,
nuốt mất chẩn đoán và đổi exit 2 (đọc được) thành exit 1 trống rỗng — đúng lỗi
này che mất chữ "cooldown" một lượt. `main()` nay đặt
`sys.stdout.reconfigure(errors="replace")`.

## 9. Đường `fuse_answer`: KHÔNG suy giảm — và ĐỪNG cắt ký ức ở đây

Ngày 2026-08-21. Đóng nợ mục 1 của `docs/trang-thai-chung.md`.

**Vì sao phải đo.** §7 cắt ký ức khỏi `rag_node`, nhưng `fuse_answer`
(fanout.py:202) **vẫn nhận** khối ký ức và cũng sinh câu trả lời có căn cứ tài
liệu: cùng hợp đồng `NGUỒN_DÙNG:` (prompts.py:227), cùng `cite_and_verify()`.
Comment quyết định ở nodes.py liệt kê "erp_node và chitchat" và sót chỗ này.
Người dùng THẬT đang mang sẵn fact `do_dai_phan_hoi = ngan_gon` — đúng loại fact
§3 đo được làm mất 8,3% `fact_acc` trên đường RAG.

Đã thêm chân `--memory` cho `eval_multi_source`, ghép khối **y hệt production**
(`memory + "\n\n" + FUSE_PROMPT`).

**Số đo** — `gemini-3.1-flash-lite`, `--pace 4.5`, 8 ca:

| chân | both_source_coverage | citation_validity | fabricated |
|---|---|---|---|
| không ký ức | 0,7500 | 1,0000 | 0 |
| `inert` | 0,8750 | 1,0000 | 0 |
| `format` | 0,8750 | 1,0000 | 0 |
| `conflict` | 0,7500 | 1,0000 | 0 |

**Đã tách nhiễu** (n=8 quá nhỏ để tin một lượt): chạy lặp 3 lượt cho chân
`none` và chân `format` — **tất định 3/3 mỗi bên**, đúng các con số trên.

**Kết luận, và nó NGƯỢC với đường RAG.**

- Hợp đồng trích dẫn **không hề suy giảm**: `citation_validity` giữ 1,0 ở mọi
  chân. Phơi nhiễm tôi cảnh báo là có thật về mặt cấu trúc nhưng **không gây
  hại đo được**.
- Ca `INV/2026/00017` trượt `both` khi KHÔNG có ký ức và ĐẠT khi có khối ép
  ngắn. Cùng loại fact cho hai kết quả trái ngược:

  | | fact ép định dạng |
  |---|---|
  | đường RAG (`synthesis_live`) | `fact_acc` 1,0 → 0,9167 |
  | đường fuse (`multi_source`) | `both_source` 0,750 → 0,875 |

  Giải thích hợp lý: trên đường RAG, ép ngắn khiến câu trả lời né sang chung
  chung và mất dữ kiện; trên đường fuse, nó buộc model nói gọn **cả hai** nguồn
  thay vì lan man vào một nguồn. Hai đường có áp lực khác nhau nên cùng một fact
  cho hai dấu khác nhau.

**Hệ quả cho quyết định: ĐỪNG cắt ký ức khỏi `fuse_answer`.** Sự không nhất quán
giữa hai đường (`rag_node` không nạp / `fuse_answer` có nạp) trông như bỏ sót,
nhưng số đo bảo vệ nó. Nên ghi lý do vào comment ở nodes.py thay vì "sửa cho
nhất quán" — cắt sẽ làm mất một ca đang đúng.

**Cẩn trọng, nói rõ:** n=8, và khác biệt nằm ở ĐÚNG MỘT ca. Tất định qua 3 lượt
nên không phải nhiễu, nhưng "ký ức làm đường fuse tốt lên" là kết luận cỡ mẫu
này chưa đỡ nổi. Điều bộ số này chống lưng được là mệnh đề phủ định: **không
quan sát thấy suy giảm**.

**CÒN NỢ**: `ĐỀ_XUẤT_GHI` vẫn chưa đo. Nó nằm trong cả `SYSTEM_PROMPT`
(prompts.py:29) lẫn `FUSE_PROMPT` (:228), đều sau khối ký ức. `eval_multi_source`
KHÔNG đo được nó: `_strip_write_marker()` chỉ **cắt** marker chứ không chấm, và
`MULTI_SOURCE_CASES` không có ca nào đề xuất thao tác ghi. Cần bộ ca riêng.

## 10. `ĐỀ_XUẤT_GHI`: khối ký ức làm marker TỊT một nửa số ca

Ngày 2026-08-21. Đóng nốt mục 1 của `docs/trang-thai-chung.md`.

Bộ ca mới `evals/write_suggest_cases.py` (8 ca: 4 dương, 4 âm), chạy qua đúng
hình dạng production của `fuse_answer` (`FUSE_PROMPT` + `render_fuse_input`), và
nhận marker bằng **chính `extract_write_suggestion`** chứ không viết lại.

**Vì sao marker này quan trọng hơn vẻ ngoài.** Nó ARM cơ chế xác nhận ghi:
`fuse_answer` tách nó thành `state["suggested_write"]` (fanout.py:217), và
`replying_to_write_suggestion` chỉ cho lượt "ok" của người dùng đi vào đường GHI
khi cờ đó bật. Marker tịt ⇒ **người dùng gật mà không có gì xảy ra**, và không ai
thấy gì sai. Marker này đã hỏng im lặng HAI lần trong lịch sử dự án.

**Số đo** — `gemini-3.1-flash-lite`, `--pace 4.5`, 8 ca, mỗi chân 2 lượt:

| chân | marker_acc (2 lượt) | false_negative | false_positive |
|---|---|---|---|
| không ký ức | **1,000 · 1,000** | 0 · 0 | 0 |
| `inert` | **0,750 · 0,750** | 2 · 2 | 0 |
| `format` | **0,750 · 0,750** | 2 · 2 | 0 |
| `conflict` (1 lượt) | 1,000 | 0 | 0 |

**Kết luận: khối ký ức làm mất một nửa số marker đáng phát.** Tỉ lệ lặp lại
chính xác qua hai lượt; *ca nào* bị tịt thì đổi giữa các lượt (lượt 1 của `inert`
mất ca SLA + khoá công nợ, `format` mất ca SLA + hoàn tiền). Tức hiệu ứng ổn
định ở mức tổng, ngẫu nhiên ở mức từng ca.

**Không có false positive nào.** Model không bao giờ phát marker oan — nó chỉ
KHÔNG phát. Chiều hỏng này là chiều im lặng: người dùng đồng ý và hệ thống không
làm gì, không báo lỗi.

**Đây là chỗ ký ức gây hại NẶNG NHẤT trong ba đường đã đo**, và nó ngược hẳn kết
quả §9 (cùng đường `fuse_answer`, cùng khối ký ức, nhưng hợp đồng `NGUỒN_DÙNG:`
không hề suy giảm còn `ĐỀ_XUẤT_GHI` mất một nửa). Hai hợp đồng nằm cạnh nhau
trong cùng một prompt mà chịu ảnh hưởng khác hẳn nhau.

### 10.1 Bản đầu của bộ ca này SAI, và cách phát hiện

Lượt đo đầu cho chân KHÔNG ký ức chỉ 0,625 — tôi suýt báo là lỗi production. Đọc
đuôi câu trả lời thật thì model ĐÚNG: `erp_block` (dùng lại nguyên từ
`MULTI_SOURCE_CASES`) không có ngày giao, nên nó không kết luận được đơn có trễ
SLA hay không, nên nó **hỏi thêm thông tin** — mà `FUSE_PROMPT` ghi rõ "câu hỏi
làm rõ thông thường thì KHÔNG thêm marker". Nhãn "phải phát marker" là **tiền đề
bất khả thi**, không phải model hỏng.

Một sai lầm phụ suýt che mất chuyện này: bản ghi `fails` cắt câu trả lời ở 300
ký tự, mà marker nằm ở CUỐI. Soi chuỗi đã cắt cụt rồi kết luận "model không phát
marker" là đọc nhầm bằng chứng.

**Phép hiệu chỉnh bắt buộc**: chân KHÔNG ký ức phải đạt `marker_acc` gần tuyệt
đối. Nếu nó không sạch thì bộ ca đang đo chính nó chứ không đo ảnh hưởng của ký
ức. Sau khi mỗi ca dương được cấp đủ dữ kiện để việc DUY NHẤT còn lại là thao tác
ghi, chân đó lên 1,0 và phép đo mới có nghĩa.

### 10.2 Còn lại

Đường `erp_node` (nodes.py:68) cũng sinh marker này, sau `SYSTEM_PROMPT` cũng có
khối ký ức đứng trước. CHƯA đo — nó cần agent gọi tool thật nên đắt hơn hẳn
đường fuse. Không có lý do để tin nó miễn nhiễm.
