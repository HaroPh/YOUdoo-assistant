# Phản hồi rỗng phải là lượt gọi hỏng, không phải câu trả lời

**Ngày:** 2026-08-13
**Trạng thái:** thiết kế đã duyệt, chờ plan

## 0. Tóm tắt

`Router` đang trả về phản hồi LLM **không có nội dung** như thể đó là câu trả
lời hợp lệ. Chuỗi fallback của vai không bao giờ được kích hoạt, vì nó chỉ chạy
khi có exception — còn đây là HTTP 200.

Sửa: phản hồi **rỗng và không gọi tool** được tính là lượt gọi hỏng; ghi sổ
ngân sách rồi tụt xuống mắt xích sau.

## 1. Lỗi, đo được

### 1.1 Cơ chế

`gemma-4-26b` — mắt xích 1 của vai `router` — với một số câu hỏi đốt hết ngân
sách đầu ra vào suy luận nội bộ và phát ra 0 token hiển thị:

```
finish_reason      = MAX_TOKENS
output_tokens      = 2045          (max_output_tokens = 2048)
  trong đó reasoning = 2045
content            = ''
```

Từ đó: `parse_proposal('')` → `unknown` → node `respond_unknown`. Người dùng
nhận một câu hội thoại lan man thay vì việc mình yêu cầu.

`parse_proposal` **không sai** — nó fail-an-toàn về `unknown` khi không parse
được, đúng thiết kế. Cái sai là **một sự cố hạ tầng bị biến thành một phân loại
ý định**, rồi hệ định tuyến theo phân loại đó.

### 1.2 Vì sao nó không tự khỏi

`Router.invoke` / `Router.ainvoke` chỉ `continue` sang mắt xích sau khi lượt gọi
**ném exception**. Một phản hồi 200 với content rỗng đi thẳng vào `_finish` và
được trả về. Hai mắt xích còn lại của vai `router` (`groq-gpt-oss-20b`,
`or-ling`) không bao giờ được gọi.

Đo: `groq-gpt-oss-20b` trả lời **đúng 5/5** chính hai câu mà gemma hỏng, tốn
312–562 token suy luận, `finish_reason=stop`. **Câu trả lời đúng đã nằm sẵn
trong chuỗi.**

### 1.3 Hình dạng: đuôi tất định, không phải nhiễu ngẫu nhiên

Token suy luận trên 18 câu, mỗi cấu hình prompt (trần production = 2048):

| cấu hình | p50 | p90 | max | chạm trần |
|---|---|---|---|---|
| có khối worker SOP | 301 | 572 | 1876 | 1/18 |
| khối rỗng (vai kế toán) | 374 | 2045 | 2045 | 2/18 |

Phân bố **hai đỉnh**: hầu hết câu xong dưới 600 token, rồi nhảy thẳng lên
1876–2045, không có gì ở giữa. Với một câu đã rơi vào đuôi, nó hỏng **5/5 lần**
— người dùng diễn đạt kiểu đó *không bao giờ* nhận được câu trả lời đúng. Đây
tệ hơn một lỗi chập chờn 5%.

Ở cấu hình có khối worker, câu nặng nhất cách vách đá **172 token**.

### 1.4 Bán kính

- Lỗi ở tầng hạ tầng LLM, **chạm mọi vai**, không riêng vai kế toán và không
  liên quan tới phân quyền.
- Hai vai khác cũng chạy gemma có thinking: `chitchat` (`gemma-4-31b`) và
  `evaluator` (mắt xích 2). Cùng bề mặt, **chưa đo**.
- **Cổng xác nhận ghi**: trước bản sửa, `confirmation.py` biến content rỗng
  thành `UNCLEAR` ⇒ không thực thi. Đây là suy giảm **chất lượng**, không phải
  **an toàn**.

  > **ĐÍNH CHÍNH (final review, 2026-08-13).** Câu trên đúng với hiện trạng
  > nhưng **sai sau bản sửa**. Vai `evaluator` — vai chạy chính cổng xác nhận
  > ghi — có chuỗi `("groq-gpt-oss-20b", "gemma-4-26b")`. Sau bản sửa, một
  > phản hồi rỗng ở mắt xích 1 **không còn** thành `UNCLEAR`; nó tụt xuống
  > `gemma-4-26b`, đúng model có đuôi rỗng đã đo, và model đó trả về một phân
  > loại thật (có thể là `CONFIRM`).
  >
  > Đánh giá: đây **không** phải lỗ hổng an toàn, và nhiều khả năng là cải
  > thiện — nhận một phân loại thật từ mắt xích 2 tốt hơn một `UNCLEAR` chắc
  > chắn. Nhưng **đường quyết định của cổng ghi ĐÃ ĐỔI**, và spec bản đầu
  > khẳng định ngược lại. Nghiệm thu sống §4.2 bổ sung kịch bản #5 để đo.
- Có một đường thứ hai dẫn tới cùng chỗ, đã có tài liệu: `strip_thought` trả
  rỗng khi khối `<thought>` bị cắt cụt thiếu thẻ đóng (`providers.py`). Nghĩa là
  content rỗng vốn đã được lường trước như tín hiệu suy giảm — cái thiếu là
  không ai thử lại mắt xích sau.

### 1.5 Hai chẩn đoán trước đều sai

| chẩn đoán | thực tế |
|---|---|
| Báo cáo 2026-08-12: "khối worker rỗng ⇒ router phân loại `unknown`" | đúng hiện tượng, sai cơ chế |
| Giả thuyết đầu phiên này: "tham chiếu treo *the list below* làm model lẫn" | sai hoàn toàn |

Khối worker không liên quan tới ngữ nghĩa. Nó cho model một danh sách cụ thể để
đối chiếu, nhờ đó **rút ngắn suy luận** và tình cờ giữ model dưới trần. Vai kế
toán chỉ là vai duy nhất không nạp SOP skill nào, nên là nơi lỗi lộ ra trước.

**Định tuyến của hệ đang phụ thuộc vào một tác dụng phụ không ai thiết kế.**

## 2. Phương án đã loại, kèm lý do đo được

### 2.1 Nâng `max_output_tokens` — LOẠI

Đo ở trần 4096: sửa được (`erp_write` 5/5, `reasoning=2418`). Nhưng lượt ngay
sau đó ăn **504 DEADLINE_EXCEEDED** — nghĩ nhiều hơn thì lâu hơn, `timeout_s=60`
không đủ. Và gemma có `tpm=16_000`; nâng trần phá chính lý do chọn model này.

> Bẫy đo, ghi lại để đời sau không mất công: lần đo đầu cho kết quả "nâng trần
> không có tác dụng", `reasoning=2045` **y hệt** ở cả 2048/4096/8192. Sai —
> `Router._client` cache client theo alias, nên cả ba lần dùng lại client dựng ở
> 2048. Ba con số giống hệt nhau **chính là dấu hiệu của confound**, không phải
> bằng chứng của kết luận.

### 2.2 Đổi hẳn model (bỏ gemma, dùng Gemini flash) — HOÃN, không loại

Chủ dự án đề xuất. Có lý, và có một lý lẽ mạnh: gemma đốt 300–2045 token suy
luận cho một việc phân loại **một từ**, ~8s mỗi lượt, chạy trên **mọi** tin
nhắn trước khi bất cứ việc gì khác bắt đầu.

Nhưng ba dữ kiện làm nó thành một quyết định riêng:

1. `gemini-3.5-flash-lite` **đã** là mắt xích 1 của cả `planner` lẫn `read`;
   `gemini-3.1-flash-lite` của cả `fusion` lẫn `synthesis`. Thêm `router` +
   `chitchat` là dồn sáu vai vào hai ví `rpd=500`. Khi cạn, cạn **đồng thời cho
   mọi vai**. Thiết kế "ví riêng biệt" của gemma (`rpd=14_400`/model) tồn tại
   chính vì điều này.
2. Catalog **không có** entry `pro` nào. Thêm là phải đo hạn mức thật — repo có
   quy ước cứng: số trong catalog phải đo được, không phỏng đoán.
3. **Đổi model không đóng được lỗi này.** Nó làm lỗi hiếm đi. `Router` vẫn coi
   mọi phản hồi rỗng là hợp lệ, và `strip_thought` vẫn có đường trả rỗng riêng.

ADR-009 M3 vốn đã bắt buộc qua eval gate mới được đổi model. Bộ `intent` có sẵn
(n=54, baseline `acc=0.870`) — đó là công cụ đúng để quyết định, ở một đợt riêng.

#### Bổ sung 2026-08-13: bốn model free chủ dự án vừa cấp

`Gemini 3.5 Flash`, `Gemini 3.6 Flash`, `Gemini 3 Flash`, `Gemini 2.5 Flash` —
**rpm=5, rpd=20** (tpm chờ xác nhận, xem dưới).

`rpd=20` loại chúng khỏi vai trò **mắt xích 1 của `router`**: router chạy trên
mọi tin nhắn, 20 lượt/ngày là hết trong vài phút trò chuyện. Chỗ đúng của chúng
là **mắt xích sâu trong chuỗi** — nơi chỉ được gọi khi mắt xích trên hỏng, tức
hiếm.

Và đây là điểm đáng chú ý: **chúng chỉ có giá trị SAU khi đợt này xong.** Hôm
nay, thêm bao nhiêu mắt xích vào chuỗi cũng vô ích trước lỗi phản hồi rỗng, vì
chuỗi không bao giờ được duyệt qua. Bản sửa này biến độ sâu của chuỗi thành giá
trị thật.

Hai điểm phải xác nhận trước khi đưa vào catalog (quy ước repo: số trong catalog
phải đo được):

1. **"250 tpm" là 250 hay 250.000?** 250 token/phút thì không gọi nổi một lượt
   nào — prompt router đã ~360 token. Nhiều khả năng là 250K, đồng bộ với hai
   entry `flash-lite` sẵn có.
2. **Bốn model dùng CHUNG một ví hay mỗi model một ví?** Chung ⇒ tổng 20
   lượt/ngày, gần như vô dụng. Riêng ⇒ 80 lượt/ngày, đủ làm lớp đệm thật.
   `ModelSpec.quota_scope` phân biệt đúng hai trường hợp này
   (`"model"` vs `"account"`), nên đây không phải chi tiết vụn.

## 3. Thiết kế

### 3.1 Nguyên tắc

Một phản hồi **không dùng được** phải được tính là **lượt gọi hỏng**, để chuỗi
fallback của vai làm đúng việc nó sinh ra để làm.

### 3.2 Luật nhận diện — CẤU TRÚC, không phải chuỗi

> `content` rỗng sau chuẩn hoá **VÀ** không có `tool_calls`

**Không** bắt theo `finish_reason`. Google trả `'MAX_TOKENS'`, Groq trả
`'length'`, chữ hoa chữ thường khác nhau — đó là so chuỗi của nhà cung cấp, đúng
lớp lỗi mà bài học "phát hiện theo *nơi* ném lỗi, không theo *nội dung*" (đợt
`log_activity`) đã cảnh báo. "Rỗng và không gọi tool" là tính chất cấu trúc,
không phụ thuộc nhà cung cấp.

### 3.3 Cái bẫy, đã đo

Một lượt gọi tool **thành công** trông y hệt lượt hỏng:

| | `content` | `tool_calls` | `finish_reason` |
|---|---|---|---|
| `get_stock` bình thường (`gemini-3.5-flash-lite`) | `''` | 1 | `STOP` |
| `get_stock` bình thường (`gemma-4-26b`) | `''` | 1 | `STOP` |
| router chạm trần | `''` | 0 | `MAX_TOKENS` |

Luật "content rỗng ⇒ hỏng" mà thiếu vế `tool_calls` sẽ phá **mọi** lượt gọi tool
trong hệ: `erp_read`, `gather_erp`, `erp_write_planner`, toàn bộ node SOP. Đây
là rủi ro hồi quy lớn nhất của đợt này.

### 3.4 Luồng

Trong `Router.invoke` và `Router.ainvoke`, mỗi vòng lặp:

1. Gọi client. Exception → giữ nguyên hành vi hôm nay (cooldown + `continue`).
2. Gọi `_finish` cho **mọi** lượt. `_finish` chuẩn hoá content
   (`_gop_content` + `strip_thought`) **và ghi sổ ngân sách**. Token đã tiêu
   thật, lượt bị bỏ cũng phải vào sổ — nếu không, sổ đếm thiếu và làm hỏng chính
   cơ chế chọn model.
3. Kết quả **dùng được** → trả về ngay (đường chạy phổ biến, không đổi gì).
4. Kết quả **không dùng được** → ghi một `AttemptError` với lý do phân biệt
   được, **không** đặt cooldown (đây không phải 429), nhớ lại kết quả này,
   `continue`.
5. Hết mắt xích → trả về kết quả **cuối cùng** đã nhớ. **Không ném exception.**

### 3.5 Vì sao không ném exception ở bước 5

Không caller nào trong repo bắt `ChainExhausted` — nó xuyên thẳng ra ngoài. Giữ
hành vi hôm nay làm **sàn**: bản sửa chỉ có thể cải thiện, không bao giờ đẻ ra
đường crash mới.

Quyết định của chủ dự án, 2026-08-13.

> **ĐÍNH CHÍNH (final review, 2026-08-13).** Bản đầu viết "ném lỗi sẽ biến một
> câu trả lời kém thành **lỗi 500**". **Sai ở tiền đề**: `main.py:178` có
> `except Exception` bọc toàn bộ endpoint, nên người dùng nhận `ERROR_MSG` chứ
> không phải 500. Kết luận thì không đổi — mất trọn một lượt vẫn tệ hơn một
> câu trả lời kém — nhưng lý lẽ phải nói đúng sự thật.
>
> Quan trọng hơn: bản hiện thực đầu tiên **không giữ được** chính lời hứa này.
> `resolve()` nằm ngoài `try/except` nên nó ném `ChainExhausted` giữa vòng lặp
> khi các mắt xích sau hết ngân sách, vứt mất kết quả đang cầm. Đã đo trên hai
> worktree: cùng đầu vào, `main` trả `message=''`, nhánh thì NÉM. Sửa ở fix
> wave — xem `.superpowers/sdd/.../fix-wave-report.md`.

### 3.6 Chế độ ghim không đổi

Có `pin`, `_max_attempts` = 1 ⇒ gọi đúng một lần, rỗng thì trả rỗng. **Toàn bộ
eval không đổi hành vi** vì eval luôn ghim model. "Ghim là ghim" —
`Router.resolve` đã tuyên bố như vậy.

### 3.7 Quan sát được

Một dòng `logger.warning` khi bỏ một lượt, kèm alias, vai, và `finish_reason`.
Đây là cách duy nhất để về sau biết **tần suất thật trên lưu lượng thật**, thay
vì suy từ 36 lượt đo trong spec này. `finish_reason` chỉ dùng để **ghi log**,
không dùng để quyết định — xem §3.2.

## 4. Điều kiện nghiệm thu

### 4.1 Test

| ca | kỳ vọng |
|---|---|
| rỗng + không `tool_calls` | tụt mắt xích, trả kết quả mắt xích 2 |
| **rỗng + CÓ `tool_calls`** | **trả nguyên trạng, KHÔNG tụt** |
| content bình thường | trả mắt xích 1, không gọi thêm lượt nào |
| mọi mắt xích rỗng | trả kết quả cuối, **không** ném exception |
| có `pin` + rỗng | gọi đúng 1 lần, trả rỗng, không tụt |
| lượt bị bỏ | **có mặt trong sổ ngân sách** |
| lượt bị bỏ | **không** đặt cooldown cho model đó |

Áp cho **cả** `invoke` (đồng bộ) lẫn `ainvoke` (bất đồng bộ) — hai thân hàm
riêng biệt, sửa một quên một là lỗi rất dễ xảy ra.

### 4.2 Nghiệm thu sống, TRƯỚC merge

Chạy trên worktree của nhánh, stack cũ dừng hẳn trước.

Hai câu KB4 gốc, qua **cổng HTTP thật**, vai **kế toán**:

- `gửi email báo giao hàng cho phiếu WH/OUT/00138`
- `nhờ gửi mail thông báo giao hàng cho khách của đơn S00119`

Kỳ vọng: nay ra lời từ chối nêu đúng **"bộ phận Kho"**, tức chuỗi
`router → erp_write → planner → guard tất định` chạy trọn, thay vì rơi vào
`respond_unknown`.

Đối chứng âm bắt buộc — thiếu nó thì "chặn được nhiều hơn" không phân biệt được
với "chặn hỏng":

- vai kế toán, việc **thuộc quyền**: `gửi hóa đơn INV/... cho khách qua email`
  → vẫn soạn được, vẫn có cổng xác nhận
- một câu **gọi tool** bất kỳ (vd `tồn kho sản phẩm ... còn bao nhiêu`)
  → vẫn chạy, chứng minh §3.3 không hồi quy
- **#5, thêm sau final review**: trả lời **xác nhận một thao tác ghi** (vd
  "ok làm đi") để đi qua vai `evaluator` — vai chạy cổng xác nhận ghi, và là
  vai mà §1.4 vừa phải đính chính. Đo xem lượt xác nhận có đi đúng đường
  không, và log có xuất hiện dòng bỏ lượt không.

### 4.3 Không được thụt

Bộ test đầy đủ xanh (mốc hiện tại: 1326 passed, 4 skipped, 46 deselected).

## 5. Ngoài phạm vi

Ghi ra để không bị hiểu là bỏ sót:

1. **Đổi model cho vai `router`/`chitchat`** — §2.2, đợt riêng, qua eval gate.
2. **Vai `chitchat` và `evaluator` cùng bề mặt lỗi**, chưa đo. Bản sửa ở tầng
   `Router` che cho chúng luôn, nhưng chưa ai đo chúng chạm trần bao nhiêu.
3. **Bộ eval `intent`/`sop_select` mù với cấu hình khối worker rỗng** —
   `run_eval.py` luôn dựng prompt bằng `load_skill_specs()` đầy đủ. Cấu hình mà
   vai kế toán thật sự chạy chưa từng được đo. Đây là lần thứ sáu của lớp lỗi
   "danh sách khai báo im lặng bỏ sót một nhánh".
4. **Lọc danh sách model theo vai trong prompt planner** — tồn đọng từ đợt
   `log_activity`, không liên quan đợt này.
