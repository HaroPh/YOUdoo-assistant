# `synthesis_live` — eval sinh câu trả lời qua retrieval thật

Ngày: 2026-08-19
Trạng thái: đã duyệt (chủ dự án chốt cách chấm + nguồn câu hỏi 2026-08-19)
Tiền đề: `docs/superpowers/specs/2026-08-19-retrieval-eval-design.md` (P0)

## 1. Vấn đề

P0 đóng được nửa retrieval của lỗ hổng eval-fidelity. Nửa sinh vẫn hở:
`eval_synthesis` và `eval_multi_source` nạp `fixtures.load_chunks(topic)` —
chunk **đóng băng** — nên retriever bị bypass hoàn toàn. Chúng đo LLM trên
ngữ cảnh hoàn hảo.

Hệ quả đã đo được, không phải suy đoán:

- Reranker chết 100% suốt 6 tuần mà không số đo nào nhúc nhích (P0 §1).
- Thay đổi `compress()` (trần theo mục) chạy được, có 10 test, nhưng
  `recall@6` và `mrr` **bằng hệt** ở cả bốn cấu hình `cap=0/1/2/3`. Không
  thước đo nào phân biệt được nó với việc không làm gì, nên phải park
  (P0 §12).

Cả P1 (metadata filtering), P2 (query rewrite), P3 (dọn ingest) và P4 (thay
`compress`, sửa `passes_floor`) đều đổi **ngữ cảnh gửi cho LLM**. Không có
thước đo ở tầng câu trả lời thì cả bốn đều không chứng minh được giá trị.
Vì thế bộ này đứng TRƯỚC P1–P4.

## 2. Vì sao không dùng LLM làm giám khảo

Repo đã thử và **bác bỏ** chấm điểm mờ cho đúng việc này. Docstring
`_grounded_match` ghi lại: bản đầu dùng khớp-theo-thứ-tự-từ có rào khoảng
cách; **hai vòng review độc lập liên tục tìm được câu trả lời SAI lọt qua** —
đảo cực tính qua một mệnh đề rào đón ngắn ("Không sao, ... vẫn được hoàn
trả"). Kết luận đã chốt: chỉ khớp **nguyên văn**, mở rộng bằng danh sách
phương án **đã quan sát thật**, không suy luận ngữ nghĩa.

Bộ này theo đúng quyết định đó và **dùng lại chính `_grounded_match`**, kể cả
cơ chế `expect` dạng tuple nhiều phương án. Ba lý do:

1. Không có bề mặt lọt-sai mới nào so với `eval_synthesis` đang chạy.
2. Không tốn thêm lượt LLM nào để chấm.
3. Giám khảo LLM tự nó cũng cần được đo độ tin cậy — một bài toán thứ hai
   chưa ai làm, không nên gánh thêm khi bài toán thứ nhất còn hở.

Đánh đổi đã biết: model diễn đạt lại thì trượt oan. Đã xảy ra 3 lần với
`eval_synthesis`, và cách xử lý là thêm phương án **sau khi quan sát thật**,
không đoán trước.

## 3. Đường chạy: gọi ĐÚNG hàm production

```
retrieve(question)  →  synthesize(question, result, llm)
```

`synthesize` là hàm mà `rag_node` gọi thật, **không mirror**. Nghĩa là bộ đo
đi qua cả `passes_floor`, sentinel `KHÔNG_ĐỦ_THÔNG_TIN`, `cite_and_verify`,
và footer `📄 Nguồn:`.

Không mirror là bắt buộc, không phải tiện tay. Bài học SP-2a: `eval_intent`
mirror hợp đồng đầu ra của router ở module khác; hợp đồng đổi, mirror không
đổi theo, acc rơi 0,870 → 0,148 và không ai nghi ngờ vì lỗi trông y hệt lỗi
chất lượng model.

Tên `synthesis_live` đặt cạnh `synthesis` có chủ đích: hai bộ đo cùng một
thứ, khác nhau đúng ở chỗ **fixture đóng băng vs retrieval thật**. Ai đọc
danh sách `--set` phải thấy ngay khác biệt đó — chính chỗ đó là lỗ hổng.

## 4. Bộ câu hỏi gây áp lực (~20 ca)

Cố ý **không** tái dùng 56 câu golden set của P0. Lý do: `recall@6` đã 0,9196
và phần lớn đáp án nằm ở chunk đầu của mục, nên chạy lại chúng qua chuỗi thật
nhiều khả năng đo lại đúng thứ `recall@6` đã nói — vô cảm với tầng truy xuất,
đúng cái bẫy vừa dẫm phải. Chi phí thì gấp ba (112 lượt LLM thay vì ~40).

Ba loại, đánh dấu tường minh để chấm tách được:

| Loại | Thiết kế | Bắt cái gì |
|---|---|---|
| `deep_chunk` | Đáp án nằm ở chunk thứ 2+ của một Điều dài | Thay đổi `compress()`/`TOP_K` làm mất phần sau của đúng điều luật |
| `distractor` | Có điều luật gần-đúng trong pool mang **con số khác** | Trả lời đúng số của **nhầm văn bản** — lỗi đã chứng minh có thật (P0 §11.1) |
| `insufficient` | Ngoài corpus hoàn toàn | Bịa; và guard hỏng vì thay đổi ngưỡng |

`deep_chunk` khả thi và dư vật liệu — đo 2026-08-19: **55% số chunk
(1809/3292) nằm trong mục bị chia nhiều chunk**, 266 mục có ≥3 chunk, và
**191 mục có số liệu riêng chỉ xuất hiện từ chunk thứ 2 trở đi** (ví dụ
`boluat-laodong.pdf › Điều 113. Nghỉ hằng năm` — "03 năm" chỉ có ở chunk 2).

Chuỗi `expect` **chép nguyên văn từ chunk thật**, không viết tay theo trí
nhớ. Có test hợp đồng khẳng định điều đó, cùng khuôn với golden set P0 §8.

## 5. Ba số đo, đều tất định

| Số đo | Định nghĩa |
|---|---|
| `fact_acc` | chuỗi `expect` xuất hiện nguyên văn trong câu trả lời (`_grounded_match`) |
| `refusal_acc` | ca `insufficient` phải ra `GUARD_MSG`; ca trả lời được **không** được ra nó |
| `citation_acc` | tên tệp nguồn kỳ vọng có **xuất hiện trong** footer `📄 Nguồn:` không |

`citation_acc` nói rõ để khỏi hiểu hai cách: chấm là **"có mặt"**, không phải
**"là nguồn duy nhất"**. Một câu trả lời dẫn đúng tệp cộng thêm một tệp khác
vẫn tính ĐẠT. Lý do: `build_citations` dựng footer từ mọi chunk sống sót sau
`verify_citations`, nên đòi độc nhất là đòi một hành vi production chưa từng
hứa. So khớp trên **basename** (`policy.docx`), đúng thứ `build_citations`
in ra.

`citation_acc` là món thêm gần như miễn phí nhưng đáng giá: nó tất định, và
nhạy trực tiếp với tầng truy xuất. **Trả lời đúng nhưng dẫn nhầm nguồn là lỗi
thật mà `fact_acc` không thấy** — và với corpus 9 luật dùng chung thuật ngữ,
đó là bề mặt lỗi có thật.

Cổng: cả ba `>= baseline`.

## 6. Điều kiện nghiệm thu: bộ eval phải TỰ CHỨNG MINH là nó nhạy

Đây là mục quan trọng nhất của spec, và là bài học trực tiếp từ P0 §12.

Sau khi bộ eval chạy được, **chạy nó trên nhánh `rag-section-cap-parked`
(`cap=1`) và so với `cap=0`**.

- Số đo **có đổi** → bộ eval nhạy với tầng truy xuất; nó làm được việc mà
  `recall@6` không làm được, và nhánh park có câu trả lời (merge hay bỏ).
- Số đo **không đổi** → hoặc bộ eval này cũng vô cảm, hoặc khử trùng lặp thật
  sự không ảnh hưởng. **Cả hai đều là kết luận có giá trị**, và biết ngay còn
  hơn biết sau ba plan nữa.

**KHÔNG cam kết trước rằng nó sẽ nhạy.** Nếu không, báo lại và nghĩ khác. Ghi
điều này vào spec để lần sau không ai đọc kết quả âm như một thất bại cần che.

Nhánh park nhờ vậy có việc ngay: nó là **ca kiểm thử cho chính bộ đo**.

## 7. Chi phí

~20 ca × 2 lượt LLM (synthesis + `verify_citations`) = **~40 lượt/lần chạy**,
vai `synthesis` (`gemini-3.1-flash-lite`, rpd=500 dùng chung với `router` và
`fusion`). Nghiệm thu §6 tốn gấp đôi (~80). Khiêm tốn.

Vai `synthesis_live` **không** nằm trong `catalog.ROLES`, nên `main()` phải
dựng LLM với `role="synthesis"` — cùng chỗ rẽ nhánh mà `retrieval` đã thêm.

## 8. Ngoài phạm vi

Không đụng `eval_synthesis` cũ: nó vẫn có giá trị riêng — cô lập LLM khỏi
retriever, nên khi hai bộ lệch nhau thì chỉ ra được lỗi nằm ở tầng nào.

Không đổi production. Không giải P1–P4. Không đụng `RAG_RERANK_ENABLED`.

## 9. Nghiệm thu độ nhạy (2026-08-19)

Baseline (`RAG_SECTION_CAP` không tồn tại, rerank bật): `fact_acc = 1,0000`,
`refusal_acc = 1,0000`, `citation_acc = 1,0000`, 20/20, p50/p95 =
3284/11656 ms.

### 9.1 Phép đo theo §6: nhánh `rag-section-cap-parked`

| Số đo | cap=1 | cap=0 | delta |
|---|---|---|---|
| `fact_acc` | 1,0000 | 1,0000 | 0 |
| `refusal_acc` | 1,0000 | 1,0000 | 0 |
| `citation_acc` | 1,0000 | 1,0000 | 0 |

`deep_chunk` và `distractor` đều 1,0000 ở cả hai chiều. **Không một số đo nào
nhúc nhích** — đúng kết quả mà §6 đã chốt trước là phải ghi nguyên như nó là.

### 9.2 Phép dò phân định: bộ eval có nhạy không?

Kết quả §9.1 có hai cách đọc — bộ eval vô cảm, hoặc khử trùng lặp thật sự
không ảnh hưởng. Phân định bằng cách tắt reranker, một thay đổi truy xuất
biết chắc là có thật:

| Cấu hình | `fact_acc` | `distractor` fact | ca trượt |
|---|---|---|---|
| rerank BẬT | 1,0000 | 1,0000 | — |
| rerank TẮT | **0,9375** | **0,8333** | "nhân viên tự ý bỏ việc bao nhiêu ngày thì công ty được đơn phương chấm dứt hợp đồng?" |

Chạy 3 lượt độc lập: **cùng con số, cùng một ca**, không phải nhiễu lấy mẫu.

**Kết luận: bộ eval NHẠY với tầng truy xuất.** Nó làm được đúng việc mà
`recall@6` không làm được, và ca nó bắt được là ca `distractor` khó nhất —
Điều 35 vs Điều 36 nằm CÙNG một tệp nên `citation_acc` mù, sức phân biệt hoàn
toàn dựa vào `expect` chỉ có ở Điều 36.

Suy ra §9.1 là kết luận về **khử trùng lặp**, không phải về bộ đo: trần theo
mục **không thay đổi chất lượng câu trả lời** trên 20 ca này.

### 9.3 Hệ quả

**Nhánh `rag-section-cap-parked`: vẫn park, và nay có lý do đo được.** Hai
thước đo độc lập (P0 `recall@6`/`mrr`, và bộ này `fact/refusal/citation`) đều
không phân biệt được nó với việc không làm gì. Chưa merge. Muốn hồi sinh thì
phải nêu được một ca mà nó cải thiện — không có ca đó thì đây là code không
có lý do tồn tại.

**Một phát hiện phụ đáng ghi**: đây là bằng chứng ĐẦU TIÊN cho thấy
cross-encoder rerank giúp được điều gì đó **đo được ở tầng câu trả lời**. Nó
không mâu thuẫn với §11 của spec P0 (rerank hại nhóm `hard` về MRR) — hai bộ
ca khác nhau, hai số đo khác nhau — nhưng nó làm bức tranh cân hơn: rerank
cứu đúng ca "hai điều luật gần giống trong cùng một văn bản", loại ca mà xếp
hạng RRF thuần không phân biệt nổi.

### 9.4 Giới hạn phải nhớ

Baseline chạm trần 1,0 ở cả ba số đo. Nghĩa là bộ này hiện là **máy dò hồi
quy**, không phải máy so hai phương án tốt: mọi thay đổi chỉ có thể làm nó
tụt hoặc đứng yên, không thể làm nó tăng. Muốn đo cải thiện thì phải thêm ca
khó hơn — và ca khó phải khó ở chỗ NGỮ CẢNH, không phải khó ở chỗ diễn đạt
(xem §9.5).

### 9.5 Bài học đã trả giá: `expect` dài là sai

Lượt chạy thật đầu tiên cho `fact_acc = 0,50`, và **cả 8 ca trượt đều là câu
trả lời ĐÚNG** — chỉ khác hư từ: "được" → "sẽ được", "kết thúc họp" → "kết
thúc cuộc họp", "không quá 8%" → "không được vượt quá 8%".

Nguyên nhân: `expect` được chọn DÀI để thoả ràng buộc "duy nhất một tệp". Hai
yêu cầu "duy nhất" và "bền với diễn đạt" chống nhau trong cùng một trường.

Cách sửa đã áp dụng — tách hai mối lo:
- `citation_acc` lo **đúng văn bản** (footer phải nêu đúng tệp);
- `expect` chỉ lo **đúng sự kiện**, dùng chuỗi ngắn nhất mang tính phân biệt;
- sức phân biệt của ca bẫy chuyển sang trường `rival`, kèm test hợp đồng
  "expect phải VẮNG MẶT trong mục cạnh tranh".

Một cặp bẫy bị LOẠI vì đo ra là không phân biệt được: Điều 35 vs Điều 36 dùng
chung các con số 03/12/30/36/45, hỏi phía nào cũng ra "45 ngày". Thay bằng
chiều ngược lại với "05 ngày làm việc liên tục" vốn chỉ có ở Điều 36 — và
chính ca thay thế này là ca duy nhất bắt được reranker ở §9.2.
