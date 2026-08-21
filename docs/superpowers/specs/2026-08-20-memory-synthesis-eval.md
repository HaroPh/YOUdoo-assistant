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

### 10.3 Bản sửa V2: câu ràng trong `FUSE_PROMPT` — chữa MỘT trong hai loại fact

Đã áp dụng 2026-08-21. Thêm vào ngay sau hướng dẫn marker trong `FUSE_PROMPT`:

> Dòng ĐỀ_XUẤT_GHI là HỢP ĐỒNG MÁY-ĐỌC bắt buộc: đã đề xuất thao tác ghi thì
> PHẢI có nó, bất kể ghi nhớ về người dùng nói gì về cách xưng hô, độ dài hay
> cách trình bày.

| chân | trước V2 | sau V2 |
|---|---|---|
| không ký ức | 1,0000 · 1,0000 | 1,0000 |
| `format` | 0,7500 · 0,7500 | **1,0000 · 1,0000 · 1,0000** |
| `inert` | 0,7500 · 0,7500 | **0,7500 · 0,7500 · 0,7500** |

Không hồi quy trên `multi_source` (cùng dùng `FUSE_PROMPT`): `citation_validity`
giữ 1,0000, `fabricated_number` giữ 0. `both_source_coverage` nhích 0,7500 →
0,8750 nhưng đó là MỘT lượt trên MỘT ca, trong khi mốc cũ là tất định 3/3 — ghi
nhận, không tính là thắng lợi.

**CHỈ SỬA `FUSE_PROMPT`, KHÔNG sửa `SYSTEM_PROMPT`.** Cùng câu hướng dẫn marker
tồn tại ở CẢ HAI prompt (một assertion trong lệnh sửa bắt được điều này). Đường
`erp_node` chạy `SYSTEM_PROMPT` thì CHƯA ĐO, và áp một thay đổi chưa đo sang
đường thứ hai là đúng lớp lỗi bộ spec này đi tìm.

**Vì sao V2 chữa `format` mà không chữa `inert` — giả thuyết, CHƯA đo.**
Câu ràng nêu đích danh "cách xưng hô", mà `inert` chính là fact xưng hô, vậy mà
không đỡ. Cơ chế có lẽ không phải "chỉ thị định dạng lấn chỉ thị marker" mà là
**dịch chuyển văn phong**: fact xưng hô đẩy model vào giọng trò chuyện cá nhân
("Chào anh Ba, …") và trong văn phong đó những dòng giao thức máy-đọc rơi ra một
cách tự nhiên. Giả thuyết này giải thích luôn §3(c) — cũng chính fact `inert`
khiến model tự viết lời từ chối thay vì phát sentinel `KHÔNG_ĐỦ_THÔNG_TIN` trên
đường RAG. Một cơ chế, hai triệu chứng, hai đường khác nhau.

Kiểm được bằng cách soi xem các câu trượt dưới `inert` có mở đầu bằng lời chào
cá nhân hoá không. Chưa làm.

**V2 là bảo vệ MỘT PHẦN, không phải bản sửa.** Người dùng thật mang CẢ HAI loại
fact (`xung_ho = anh Hào` VÀ `do_dai_phan_hoi = ngan_gon`), nên nửa còn lại vẫn
hở. Hướng tiếp theo đang chờ duyệt: khi khối ký ức khác rỗng VÀ marker không
phát, hỏi lại bằng một lượt gọi riêng KHÔNG hề thấy khối ký ức — dựa trên số đo
rằng ngữ cảnh sạch ký ức cho marker_acc = 1,0. Điều kiện nghiệm thu bắt buộc:
`false_positive` phải giữ 0 trên cả 4 ca âm, vì cơ chế đó THÊM cờ và thêm cờ là
chiều nguy hiểm.

**Một hướng đã bị BÁC BỎ trước khi viết code**: bắt lượt "ok" khi không có cờ mà
câu trả lời trước kết thúc bằng câu hỏi. Đó đúng là heuristic dò văn bản mà
docstring `replying_to_write_suggestion` đã cân nhắc và loại bỏ, kèm đúng phản ví
dụ ("Bạn có muốn tôi giải thích thêm không?" theo sau bởi "ok").

## 11. RÚT LẠI §10 — và §10.3 (V2) đã được gỡ

Ngày 2026-08-21. Đây là đính chính, không phải bổ sung.

**§10 kết luận SAI.** Tôi báo "ký ức làm marker `ĐỀ_XUẤT_GHI` tịt 50% số ca,
hỏng im lặng, người dùng gật mà không có gì xảy ra". Đọc được ĐUÔI câu trả lời
thật thì model **không hề giấu marker — nó không đề xuất ghi**:

- ca SLA: *"Hiện tại, hệ thống chưa có chức năng tự động lập phiếu bồi thường,
  anh Ba vui lòng thực hiện khấu trừ thủ công"* — TỪ CHỐI làm;
- ca hoàn tiền: *"Anh muốn nhận tiền hoàn qua hình thức thanh toán ban đầu hay
  chuyển khoản ngân hàng ạ?"* — HỎI LÀM RÕ.

Cả hai, không phát marker là ĐÚNG theo chính `FUSE_PROMPT`. Điều thật sự xảy ra:
**ký ức đổi HÀNH VI của trợ lý, không đổi cách nó báo cáo hành vi.** Không có gì
để người dùng gật cả.

**Vì sao tôi sai hai lần liên tiếp trên cùng bộ ca này.** Cả hai lần đều do đọc
bằng chứng bị cắt cụt: bản ghi `fails` lưu 300 ký tự ĐẦU, mà marker và phần đề
xuất nằm ở CUỐI. Đã sửa bộ đo để lưu thêm `response_tail`.

**Lỗi gốc nằm ở thiết kế phép đo.** `marker_acc` chấm marker so với NHÃN TAY —
tức khẳng định model NÊN quyết định gì. Model được phép chọn đề xuất, từ chối,
hay hỏi làm rõ; cả ba hợp lệ. Hợp đồng thật chỉ có một điều: **marker phải khớp
với thứ câu trả lời THẬT SỰ làm**.

### 11.1 Thước mới: độ khớp marker ↔ câu trả lời

`eval_write_suggest` nay chấm bằng một **thẩm định độc lập**
(`evals/write_suggest_oracle.py`) đọc câu trả lời đã bỏ marker và phán, KHÔNG hề
thấy khối ký ức. Báo cáo hai số tách bạch:

- `agreement` — CỔNG: marker có nói đúng về câu trả lời không;
- `proposed_rate` — SỐ ĐO HÀNH VI, không phải cổng: trong 4 ca mời một thao tác
  ghi, model thật sự đề xuất bao nhiêu lần.

| chân | agreement | proposed_rate |
|---|---|---|
| không ký ức | 0,8750 | 0,7500 |
| `inert` | **1,0000** | 0,5000 |
| `format` | **0,7500** | 0,5000 |

Ký ức HẠ `proposed_rate` (0,75 → 0,50) — trợ lý ít sẵn sàng đề nghị tự làm hơn.
Đó là thay đổi hành vi có thật, và nó KHÁC HẲN việc phá hợp đồng marker.

Mọi bất đồng đều là **marker nói DƯ** (marker bật, câu trả lời không đề xuất) —
chiều nguy hiểm. Đọc từng ca:

1. `none`/INV00017 — *"Bạn vui lòng xác nhận hình thức nhận tiền hoàn để tôi ghi
   chú vào hệ thống"*: ĐÚNG là đề xuất chờ đồng ý. **Thẩm định sai**, marker đúng.
2. `format`/INV00017 — *"Theo quy trình, bộ phận kế toán sẽ tiến hành hoàn tiền
   trong vòng 5-10 ngày"*: thuần mô tả. **Marker nói dư.**
3. `format`/S00050 — *"Tôi đã ghi nhận… và **thực hiện khóa công nợ** trên hệ
   thống"* + marker: model **tuyên bố ĐÃ LÀM một thao tác ghi** mà `fuse_answer`
   không có tool nào để làm, đồng thời tự mâu thuẫn với marker (nghĩa là *đang
   đề xuất, chờ đồng ý*). Đây là phát hiện MỚI và nặng hơn chuyện marker.

Thẩm định sai 1/24 lượt phán, nên `agreement` **không phải cổng tự động** — nó
lọc ra ứng viên để người đọc, đúng như vừa làm ở trên.

### 11.2 V2 đã được GỠ

Gỡ câu ràng khỏi `FUSE_PROMPT`. Lý do **không phải** vì đã chứng minh nó có hại,
mà vì **căn cứ nhận nó đã mất hiệu lực**: nó được duyệt trên `marker_acc`, thước
nay biết là đo sai thứ. Dưới thước đúng, chân `format` — chân V2 "chữa được" —
có nhiều bất đồng nhất, và một trong đó là bịa hành động.

Câu chuyện khớp: V2 nói "đã đề xuất thì PHẢI phát marker", và model đáp lại bằng
cách **phát marker nhiều hơn**, không phải **đề xuất nhiều hơn**.

Gánh nặng chứng minh thuộc về việc GIỮ một thay đổi prompt production, không
thuộc về việc gỡ nó. Muốn nhận lại thì phải đo bằng `agreement` với đủ lượt lặp.

### 11.3 Còn mở

- **Model bịa đã thực hiện thao tác ghi** (ca 3 ở trên). n=1, chưa lặp lại, chưa
  biết có xảy ra khi không có ký ức không. Nặng nhất trong những gì thấy được
  hôm nay và đáng đo riêng.
- Thẩm định sai 1/24 — cần ca kiểm tra chính thẩm định nếu muốn dùng nó làm cổng.
- Đường `erp_node` vẫn chưa đo.

## 12. Đường `erp_node`: ký ức gần như vô hại — và bảng lọc theo loại fact BỊ BÁC

Ngày 2026-08-21. Đóng mục 1b của `docs/trang-thai-chung.md`.

`erp_node` là chỗ ký ức sống mà chưa ai đo, đồng thời là đường THAO TÁC GHI thật
sự chạy. Thêm chân `--memory` cho `eval_read` (mirror `SYSTEM_PROMPT` +
`bind_tools`, đúng hình dạng node), ghép khối y hệt nodes.py:49-51.

| chân | tool_acc | param_acc | bịa tham số |
|---|---|---|---|
| không ký ức | 1,0000 | 1,0000 | 0 |
| `format` | **1,0000** | 1,0000 | 0 |
| `conflict` | **1,0000** | 1,0000 | 0 |
| `inert` | 0,9630 · 0,9630 | 0,9630 | 0 |

`inert` trượt ĐÚNG MỘT ca qua hai lượt (tất định): *"khách Azure Interior thông
tin thế nào?"* chọn `find_customer` thay vì `get_customer_detail` — hai tool
khách hàng gần nhau. 1/27.

### 12.1 Bảng lọc theo loại fact — ĐỀ XUẤT CỦA TÔI, ĐÃ BỊ SỐ LIỆU BÁC

Trước phép đo này tôi đề xuất: *"fact nội dung đi khắp nơi; fact định dạng/xưng
hô chỉ vào `chitchat`"*, kèm cột `fact_type`, phân loại lúc ghi, lọc lúc đọc.

Ghép cả bốn đợt đo:

| đường | nội dung | xưng hô | định dạng |
|---|---|---|---|
| `rag_node` | vô hại, nhưng đóng góp 0 | **phá hợp đồng guard** | **−8,3% fact_acc** |
| `fuse_answer` | sạch | agreement 1,0 | agreement 0,75 |
| `erp_node` | 1,0 | 0,963 | **1,0** |

**Tác hại tập trung ở ĐÚNG MỘT đường — `rag_node` — và nó đã bị cắt.** Trên hai
đường còn lại, fact định dạng đạt 1,0 ở `erp_node` và fact nội dung sạch ở mọi
nơi. Không có căn cứ cho bảng lọc.

Xây nó sẽ là dựng cột DB + bước phân loại + lớp lọc để giải một vấn đề chỉ tồn
tại ở nơi đã xử lý xong. **Đo trước khi xây đã tiết kiệm đúng chỗ đó.**

### 12.2 Nợ còn lại của tính năng ký ức, sau khi đã đo bốn đường

Danh sách này NGẮN HƠN nhiều so với lúc chưa đo:

1. **Mọi phép đo đều dùng ĐÚNG MỘT fact; người dùng thật có NĂM.** Đây là lỗ
   hổng lớn nhất còn lại — không có gì cho biết hiệu ứng cộng dồn thế nào.
2. **Hai key cho cùng một fact** (`hien_thi_ma_don` + `always_show_order_code`)
   đã có trong dữ liệu thật. Khối ký ức phình theo hướng lặp lại chính nó.
3. **Không có trần số fact.** Chưa hại ở 5 fact (11% `SYSTEM_PROMPT`) nhưng ở 50
   thì khối bằng 130% `CHITCHAT_PROMPT`.
4. `chitchat` chưa đo — rủi ro thấp nhất (không mang hợp đồng nào).
5. Ca `format`/`fuse`: model **bịa rằng đã thực hiện thao tác ghi** (n=1).

## 13. Cấu hình THẬT (5 fact): cộng dồn không phá hợp đồng, nhưng tắt hẳn việc đề xuất ghi

Ngày 2026-08-21. Đóng mục 1b.

Mọi kết luận trong spec này tới §12 đều dựa trên cấu hình **một fact** — cấu hình
không ai thật sự dùng. Người dùng thật duy nhất của hệ có **năm**. Chân `real5`
sao lại đúng năm fact ấy, **giữ nguyên cặp key trùng** (`hien_thi_ma_don` +
`always_show_order_code` — một điều nói hai lần, do model tự sinh key), vì đó là
tính chất có thật của dữ liệu.

| bộ | không ký ức | 1 fact | **5 fact** |
|---|---|---|---|
| `read` (erp_node) `tool_acc` | 1,0000 | 0,9630 (`inert`) | **1,0000** |
| `multi_source` `both_source` | 0,7500 | 0,8750 | 0,8750 |
| `multi_source` `citation_validity` | 1,0000 | 1,0000 | 1,0000 |
| `write_suggest` `agreement` | 0,8750 | 1,0 / 0,75 | 0,8750 |
| **`write_suggest` `proposed_rate`** | **0,7500** | **0,5000** | **0,0000** |

**Cộng dồn KHÔNG làm hỏng thứ ta lo.** Chọn tool trở lại 1,0 (tốt hơn chân một
fact `inert`); trích dẫn giữ 1,0; `agreement` bằng đúng mốc không-ký-ức. Nỗi lo
"càng nhiều fact càng hỏng" — không có cơ sở trên ba mặt đó.

**Nhưng `proposed_rate` giảm ĐƠN ĐIỆU về 0.** Tất định qua **3 lượt** (12 lượt
chạy ca): với ký ức thật của người dùng, trợ lý **không đề xuất thao tác ghi lần
nào** trong 4 ca được thiết kế để mời. Nó vẫn trả lời đúng — nhưng thay vì
*"tôi sẽ làm X, anh đồng ý chứ?"* thì nó giải thích quy trình, bảo người dùng tự
làm, hoặc hỏi thêm thông tin.

**Hệ quả sản phẩm**: chuỗi *đề xuất → "ok" → thực thi* trên đường `fuse_answer`
**thực tế không bao giờ lên đạn** cho người dùng thật. Không phải vì marker hỏng
— `agreement` chứng minh marker vẫn nói đúng — mà vì **không có gì để đánh dấu**.

**Đây là câu hỏi sản phẩm, không phải lỗi.** Trợ lý thận trọng hơn có thể là
điều mong muốn với một hệ chạm dữ liệu ERP thật. Số liệu chỉ nói rằng ký ức đã
tắt hành vi đó, chưa nói nên bật lại hay không.

**Phạm vi**: chỉ đường `fuse_answer`. Hành vi đề xuất trên `erp_node` chưa đo —
`eval_read` dừng ở lượt chọn tool, không sinh câu trả lời cuối.

## 14. ĐÓNG mục "model bịa đã thực hiện thao tác ghi" — thủ phạm là V2

Ngày 2026-08-21. Đóng mục 1 của `docs/trang-thai-chung.md`.

§11.1 ghi nhận một ca (n=1) model trả lời *"Tôi đã ghi nhận… và **thực hiện khóa
công nợ** đối với Gemini Furniture **trên hệ thống** theo đúng quy trình"* —
trong khi `fuse_answer` không có tool nào và không thao tác gì. Đây là mục nguy
hiểm nhất trên bảng: người dùng tin một thao tác đã xong trong khi không có gì
xảy ra, và không có cách nào biết.

**Tái hiện được, và tìm ra điều kiện:**

| cấu hình | bịa đã thao tác |
|---|---|
| không V2 — chân `none` / `format` / `real5` | **0/9** |
| **V2 + `format`** | **3/3** |
| V2 + `real5` | 0/3 |

**Thủ phạm là V2** — câu ràng ở §10.3, thêm vào rồi gỡ ra trong cùng ngày
2026-08-21. Ca gốc được quan sát đúng lúc V2 còn trong `FUSE_PROMPT`.

**CƠ CHẾ, và đây là bài học rộng hơn bản thân ca này**: ép model tuân thủ một
hợp đồng máy-đọc khiến nó **BỊA RA chính sự kiện mà hợp đồng đó mô tả**. V2 nói
"đã đề xuất thao tác ghi thì PHẢI phát marker". Model không đề xuất nhiều hơn —
nó **kể rằng đã làm**, để câu chuyện khớp với marker nó vừa phát.

Đó là lý do mạnh hơn hẳn lý do tôi dùng lúc gỡ V2 (§11.2: "căn cứ nhận nó đã mất
hiệu lực"). Lúc đó tôi chỉ biết V2 vô căn cứ; giờ biết nó nguy hiểm.

**Trạng thái**: đã sạch trên production từ `34158d4` (V2 đã gỡ). Rào chống thêm
lại: `tests/agents/test_fuse_prompt_khong_ep_marker.py`, chặn cả `FUSE_PROMPT`
lẫn `SYSTEM_PROMPT` — đường thứ hai mang CÙNG hướng dẫn marker và cũng có khối
ký ức đứng trước, nhưng CHƯA BAO GIỜ được đo với câu ràng đó.

**Giới hạn**: chỉ thử trên một ca (`S00050` khoá công nợ) và một model
(`gemini-3.1-flash-lite`). Không biết cơ chế này còn xảy ra ở hình thức ép buộc
nào khác. Điều biết chắc: **đừng viết "PHẢI phát marker X" vào prompt sinh câu
trả lời.**

## 15. `proposed_rate`: lọc theo LOẠI fact KHÔNG cứu được — kích thước khối mới là biến

Ngày 2026-08-21. Chủ dự án chốt: **muốn** trợ lý chủ động đề nghị "để tôi làm
giúp". Điều đó biến `proposed_rate` thành chỉ số ưu tiên, và §12.1 (bác bảng lọc
theo loại fact) cần được xét lại trên chỉ số mới.

Giả thuyết đem đi đo: *fact nội dung vô hại, fact xưng hô/định dạng mới ức chế —
nên lọc hai loại sau khỏi `FUSE_PROMPT` sẽ khôi phục việc đề nghị*.

**Đo ra là SAI.** `write_suggest`, `gemini-3.1-flash-lite`, `--pace 4.5`, mỗi
chân 3 lượt (trừ hai chân đã đo trước):

| khối ký ức | proposed_rate | agreement |
|---|---|---|
| không ký ức | 0,7500 | 0,8750 |
| `conflict` (chính sách phạt công ty) | **1,0000** ×3 | 1,0000 |
| `content` (`kho_chinh = WH/Stock`) | **0,5000** ×3 | 1,0000 |
| `inert` (xưng hô) | 0,5000 | 1,0000 |
| `format` (độ dài) | 0,5000 | 0,7500 |
| `real5` (cả năm fact thật) | **0,0000** ×3 | 0,8750 |

**Fact nội dung ức chế y hệt fact xưng hô** (cùng 0,5000). Giữ lại mỗi
`kho_chinh` cho 0,50 chứ không phải 0,75 — lọc theo loại **không khôi phục
được**.

**Biến thật sự có vẻ là KÍCH THƯỚC KHỐI, không phải loại fact**: 1 fact → 0,50;
5 fact → 0,00. Ngoại lệ duy nhất là `conflict`, và nó giải thích được: fact ấy
nói về một QUY TẮC NGHIỆP VỤ công ty, tức nội dung của chính nó mồi khung hành
động, nên đẩy lên 1,0 — cao hơn cả chân không-ký-ức.

Đây là lần thứ HAI bảng lọc theo loại fact bị số đo bác, nay trên đúng chỉ số mà
quyết định sản phẩm vừa làm cho quan trọng.

### 15.1 Đòn bẩy duy nhất đã đo được, và cái giá của nó

Muốn `proposed_rate` trở lại 0,75 thì phải **bỏ khối ký ức khỏi `FUSE_PROMPT`**.
Không có cấu hình ký ức nào đã đo cho kết quả tốt hơn.

Việc đó **lật ngược khuyến nghị §9 của tôi** ("ĐỪNG cắt ký ức khỏi
`fuse_answer`"). §9 đúng với những chỉ số quan trọng lúc đó; quyết định sản phẩm
đổi chỉ số nào chiếm ưu thế, nên đổi cả kết luận.

Cái giá, đã đo:

| bỏ ký ức khỏi `FUSE_PROMPT` | |
|---|---|
| `proposed_rate` | 0,0000 → **0,7500** |
| `both_source_coverage` | 0,8750 → **0,7500** |
| `citation_validity` | 1,0000 → 1,0000 (không đổi) |
| ký ức trên đường doc+ERP | mất hẳn |

Đổi một ca `both_source` lấy ba ca `proposed_rate`. Nhưng đó là **quyết định sản
phẩm**, không phải phép so số thuần: nó cũng có nghĩa là fact `kho_chinh` không
còn tác dụng ở đường trả lời hỗn hợp.

**Chưa đo**: `proposed_rate` trên đường `erp_node` — nơi thao tác ghi thật sự
chạy. `eval_read` dừng ở lượt chọn tool nên không đo được hành vi đề nghị.

## 16. QUYẾT ĐỊNH: chấp nhận `proposed_rate = 0`, không sửa

Ngày 2026-08-21. Chủ dự án chốt sau khi xem cái giá ở §15.1.

**Trạng thái được chấp nhận**: khối ký ức ở lại `FUSE_PROMPT`, và trợ lý **không
chủ động đề nghị thực hiện thao tác ghi** trên đường trả lời hỗn hợp
(`proposed_rate = 0,0000`, tất định 3 lượt với ký ức thật của người dùng).

**Vì sao chấp nhận thay vì sửa.** Đòn bẩy duy nhất đã đo được là bỏ khối ký ức
khỏi `FUSE_PROMPT`, và nó đắt hơn vẻ ngoài: mất `both_source_coverage`
(0,8750 → 0,7500) VÀ mất hiệu lực của `kho_chinh` ở đúng đường trả lời hỗn hợp —
nơi fact ấy có giá trị nhất. Lọc theo loại fact đã bị đo là không cứu được
(§15). Ép bằng chỉ thị prompt đã bị đo là NGUY HIỂM (§14: model bịa rằng đã
thực hiện thao tác, 3/3).

Nói cách khác: ba hướng khả dĩ thì một đắt, một vô dụng, một nguy hiểm.

**Người dùng mất gì.** Trợ lý sẽ giải thích quy trình, chỉ cách làm, hoặc hỏi
thêm thông tin — thay vì nói *"để tôi làm giúp, anh đồng ý chứ?"*. Người dùng
vẫn ra lệnh ghi được bằng cách nói thẳng; chỉ là trợ lý không tự mời.

**Không phải là hỏng.** `agreement` cho thấy marker vẫn nói ĐÚNG về việc câu
trả lời làm gì, và `false_positive` là 0 trên mọi chân. Hệ không nói dối — nó
chỉ ít chủ động hơn.

**ĐỪNG MỞ LẠI nếu không có dữ kiện mới.** Ba hướng đã đo và đã loại. Dữ kiện
đáng để xét lại: (a) `proposed_rate` trên đường `erp_node` — CHƯA ĐO, và đó mới
là nơi thao tác ghi thật chạy; (b) một cách khôi phục nào đó chưa từng thử,
KHÔNG phải chỉ thị prompt.

## 17. `chitchat`: sạch — đóng đường cuối chưa đo

Ngày 2026-08-21. Bốn đường ký ức sống nay đã đo hết.

`eval_chitchat` đo đúng thứ nguy hiểm nhất tìm được trong đợt này: **bịa hành
động đã xảy ra**. `respond_unknown` không bind tool nào, nên mọi khẳng định "đã
làm X" đều là bịa — và đây là **cổng tuyệt đối** (`violations` phải = 0).

Khối ký ức là văn bản do NGƯỜI DÙNG viết, đặt ngay trước prompt, mà chưa ai kiểm
nó có làm tăng tỉ lệ bịa ở đây không. §14 cho thấy một câu ràng trong prompt đủ
sức khiến model bịa đã thao tác trên hệ thống (3/3), nên câu hỏi là chính đáng.

| chân | violations |
|---|---|
| không ký ức | **0** |
| `real5` (cả năm fact thật) | **0** |
| `format` | **0** |

**Sạch.** Ký ức không làm tăng bịa trên đường trò chuyện.

### 17.1 Tổng kết bốn đường

| đường | trạng thái |
|---|---|
| `rag_node` | ký ức ĐÃ CẮT (§7) — đo ra không loại fact nào dương |
| `fuse_answer` | ký ức GIỮ; trích dẫn/marker sạch, `proposed_rate` = 0 đã CHẤP NHẬN (§16) |
| `erp_node` | ký ức GIỮ; chọn tool 1,0 với `format`/`conflict`/`real5`, 0,963 với `inert` (§12) |
| `chitchat` | ký ức GIỮ; không bịa (§17) |

Không còn đường nào của tính năng ký ức nằm trong bóng tối.
