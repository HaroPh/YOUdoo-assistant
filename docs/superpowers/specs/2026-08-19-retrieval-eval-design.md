# Số đo truy xuất (P0) — thiết kế

Ngày: 2026-08-19
Trạng thái: đã duyệt (chủ dự án chốt neo nhãn + nguồn câu hỏi 2026-08-19)

## 1. Vấn đề

Repo không có một số đo nào cho tầng truy xuất. `grep` toàn bộ
`backend/src`, `backend/evals`, `backend/tests`, `docs` cho
`hit_rate|recall@|MRR|ndcg|context_precision|ragas` trả về **rỗng**.

Hệ quả đo được, không phải suy đoán:

- 13 test trong `backend/tests/rag/test_retrieve.py` đều **cơ học** (thứ tự,
  fail-open, plumbing của `aux_queries`) trên tài liệu seed tổng hợp. Không
  test nào đo chất lượng xếp hạng.
- `eval_synthesis` và `eval_multi_source` nạp `fixtures.load_chunks(topic)`
  — **retriever bị bypass hoàn toàn**. Chúng đo LLM trên ngữ cảnh hoàn hảo.
- Vì thế reranker chết 100% từ 2026-07-12 đến 2026-08-19 mà **không một số
  đo nào nhúc nhích**. Nó chỉ lộ ra khi có người đọc `method` của
  `RetrievalResult` bằng tay.
- Spike `gemini-embedding` (2026-08-15) bị hoãn vì "không quy được thay đổi
  cho biến nào". Con số cần để mở nút đó chính là recall@k — chưa tồn tại.

Đây là lần thứ năm lớp lỗi "danh sách/cổng khai báo mà không đo gì" tái phát
trong project. Lần này nó nằm ở tầng lõi nhất.

## 2. Phạm vi

**Trong phạm vi:** một bộ eval mới `retrieval` chạy `retrieve()` THẬT trên
corpus thật, cộng golden set và baseline JSON.

**Ngoài phạm vi (các plan riêng):** metadata filtering (P1), tầng query
rewrite/multi-query (P2), chất lượng ingest PDF/XLSX (P3), thay
`compress()` và sửa `passes_floor` (P4). Plan này **không đổi một dòng nào
của đường production** — nó chỉ thêm khả năng quan sát.

## 3. Bối cảnh corpus (đo 2026-08-19)

| Nhóm | Số chunk | Tỉ lệ |
|---|---|---|
| 9 PDF luật | 3.256 | 98.7% |
| 8 tài liệu nghiệp vụ (docx/xlsx) | 44 | 1.3% |
| **Tổng** | **3.300** | |

Sự thật quan trọng: **mọi câu hỏi rag trong `backend/evals/cases.py` hiện chỉ
chạm 44 chunk nghiệp vụ.** 98.7% corpus chưa từng được bất kỳ bộ eval nào
chạm tới. Golden set phải sửa mất cân đối này, nếu không nó chỉ đo lại đúng
vùng đã đo.

Khảo sát 2026-08-19 còn lộ ra chất lượng `section_path` của PDF luật kém hơn
tưởng — dữ liệu này thuộc P3 nhưng ghi ở đây vì nó ràng buộc cách gán nhãn:

- `_HEADING_RE` khớp cả tham chiếu chéo GIỮA câu: **15 "mục" thực chất là
  mảnh câu** (`"Điều 11 của Luật này quy định."`, `"Điều 133 của Bộ luật
  này."`). Mỗi mảnh cắt đôi một mục thật.
- Luật `isupper()` biến quốc hiệu/tên cơ quan thành mục: `"CỘNG HÒA XÃ HỘI
  CHỦ NGHĨA VIỆT NAM"`, `"CHỦ TỊCH QUỐC HỘI"`, `"QUỐC HỘI"`, `"LUẬT"`.
- Heading PDF phẳng cấp 2 nên `"Chương I"`…`"Chương V"` đứng trơ, và
  `"Điều 5. …"` không nằm dưới chương của nó — phân cấp mất sạch.

Hệ quả cho plan này: **không gán nhãn đúng vào các mục rác đó.** Chúng sẽ
biến mất khi P3 chạy, và gán nhãn vào chúng là đóng đinh lỗi ingest vào
chính thước đo.

## 4. Neo nhãn: `(source_file, section_path)`

Nhãn ghi "câu hỏi này phải trúng *Mục 2* của *policy.docx*", không ghi
chunk_id.

**Vì sao không phải chunk_id:** `rag_chunks.id` là `bigserial`. Re-index đổi
sạch id — mà re-index là việc **bắt buộc** khi thử embedding mới, tức golden
set sẽ chết đúng lúc cần nhất.

**Vì sao không phải hash nội dung:** sống qua re-index nhưng chết khi đổi
`CHUNK_SIZE_TOKENS` hoặc sửa `parse_pdf` — mà đó chính là nội dung của P3.

**Vì sao là CẶP, không phải `section_path` đơn:** `section_path` trùng nhau
giữa các văn bản luật. Đo được: `"Điều 3. Giải thích từ ngữ"` có 32 chunk
nằm rải ở nhiều file khác nhau. Neo bằng `section_path` đơn sẽ tính một cú
trúng nhầm luật thành trúng.

**Đánh đổi đã chấp nhận:** không phân biệt được hai chunk trong cùng một
mục, nên recall rộng tay hơn thực tế. Chấp nhận được vì mục tiêu là **so
sánh giữa các cấu hình**, không phải một con số tuyệt đối.

Một số đo phụ trợ dùng để bù đánh đổi này: `chunk_span` — số chunk trung
bình mà một nhãn phủ. Nó tăng lên nghĩa là nhãn đang mất sức phân giải.

## 5. Số đo

Với mỗi câu hỏi, `retrieve()` trả về danh sách chunk đã xếp hạng. Quy chiếu
mỗi chunk về cặp `(source_file, section_path)` rồi so với tập nhãn đúng.

| Số đo | Định nghĩa | Đọc để làm gì |
|---|---|---|
| `recall_at_20` | tỉ lệ nhãn đúng có mặt trong pool 20 (TRƯỚC khi cắt k) | trần chất lượng của tầng một; reranker không bao giờ cứu được cái không có trong pool |
| `recall_at_6` | tỉ lệ nhãn đúng có mặt trong 6 chunk cuối | thứ LLM thật sự nhìn thấy |
| `mrr` | trung bình `1/hạng của nhãn đúng đầu tiên` | chất lượng xếp hạng, nhạy với thay đổi rerank |
| `chunk_span` | số chunk trung bình một nhãn phủ | canh sức phân giải của neo (mục 4) |

Cổng: `recall_at_20 >= baseline` và `mrr >= baseline`. `recall_at_6` báo cáo
nhưng không gác — nó là hàm của cả `TOP_K` lẫn rerank, nên gác nó sẽ khoá
cứng `TOP_K=6` một cách vô tình.

## 6. `rerank_delta` — phép đo đối chứng

Cùng golden set, chạy hai lần: `RAG_RERANK_ENABLED=0` và `=1`. Báo cáo hiệu
số của cả bốn số đo.

Đây là lý do tồn tại quan trọng nhất của plan này ở thời điểm hiện tại: từ
2026-08-19 project ghim `torch==2.11.0+cu128` (~2.5GB) và trả ~21ms GPU cho
mỗi truy vấn. `rerank_delta` là bằng chứng duy nhất cho việc đó đáng hay
không. Nếu delta ≈ 0, quyết định đúng là gỡ dep chứ không phải giữ.

`recall_at_20` **không được đổi** giữa hai lần chạy (rerank chỉ sắp xếp lại
pool, không thêm ứng viên). Nếu nó đổi, phép đo hỏng chứ không phải reranker
tốt lên — bộ chấm phải khẳng định điều này.

## 7. Golden set

~60 câu, gộp từ hai nguồn:

**(a) Tái dùng câu hỏi eval sẵn có.** `cases.py` đã có câu hỏi `rag` trong
`INTENT_CASES`, `SOP_SELECT_CASES`, `SYNTHESIS_CASES`, `MULTI_SOURCE_CASES`.
Gộp lại và gán nhãn. Lợi ích: khi một bộ khác đổi, hai bộ nói về cùng câu
hỏi nên truy nguyên được.

**(b) Bổ sung tay cho 9 PDF luật** — vùng 98.7% corpus chưa ai đo.

Ba hạng độ khó, đánh dấu tường minh trong dữ liệu để chấm điểm tách được:

| Hạng | Nghĩa | Vì sao cần |
|---|---|---|
| `easy` | từ khoá câu hỏi trùng mặt chữ trong chunk | FTS một mình cũng trúng; bắt hồi quy thô |
| `hard` | diễn đạt khác hẳn, phải hiểu nghĩa | chỗ dense + rerank kiếm ăn |
| `trap` | từ khoá trùng nhưng ý KHÁC | bắt lỗi trúng-nhầm; nhãn đúng là **luật khác** với luật mà từ khoá gợi ý |

Hạng `trap` bắt buộc phải có vì 9 PDF luật đều mở đầu bằng cùng cấu trúc
("Điều 1. Phạm vi điều chỉnh", "Điều 2. Đối tượng áp dụng") — chính điều mà
spike Gemini đã nêu là phép thử khó.

## 8. Nhãn phải được xác minh bằng máy

Nhãn viết tay có thể trỏ vào cặp `(source_file, section_path)` **không tồn
tại** — sai chính tả, đổi tên file, hay heading bị `parse_pdf` cắt khác đi.
Nhãn như vậy làm recall tụt mà không ai hiểu vì sao.

Vì thế bộ eval có một test hợp đồng: **mọi nhãn trong golden set phải khớp ít
nhất một hàng thật trong `rag_chunks`.** Không khớp là đỏ, kèm tên nhãn.

Đây là bài học trực tiếp từ `GATHER_CASES`: fixture trôi khỏi dữ liệu thật
mà không ai biết, phải thêm test hợp đồng sau. Lần này viết cùng lúc.

## 9. Không đụng production

Plan này **chỉ thêm**: một file dữ liệu, một hàm `eval_retrieval`, một
baseline JSON, các test. Không sửa `retrieve.py`, `chunking.py`, `config.py`
hay bất kỳ đường chạy thật nào.

Lý do: mọi thay đổi P1–P4 sau này cần một điểm mốc **đo trên hành vi hiện
tại**. Sửa production trong cùng plan sẽ làm baseline mất nghĩa ngay khi
sinh ra.

## 10. Kết quả đo (baseline đầu tiên, 2026-08-19)

Corpus 3.300 chunk / 17 tài liệu, embedding `bge-m3`, n=56 câu, `TOP_N=20`,
`TOP_K=6`. Độ trễ p50/p95 = 460/553 ms.

| Số đo | rerank BẬT | rerank TẮT | delta |
|---|---|---|---|
| `recall_at_20` | 1.0000 | 1.0000 | 0.0000 ✅ bất biến giữ |
| `recall_at_6` | 0.9196 | 0.9405 | **−0.0209** |
| `mrr` | 0.8253 | 0.8269 | −0.0016 |

Theo hạng độ khó:

| Hạng | n | recall@20 (bật/tắt) | mrr bật | mrr tắt | delta mrr |
|---|---|---|---|---|---|
| easy | 31 | 1.0000 / 1.0000 | 0.9285 | 0.8753 | **+0.0532** |
| hard | 17 | 1.0000 / 1.0000 | 0.6136 | 0.7158 | **−0.1022** |
| trap | 8 | 1.0000 / 1.0000 | 0.8750 | 0.8750 | 0.0000 |

### 10.1 Ba kết luận

**(a) Tầng một KHÔNG phải nút thắt.** `recall@20 = 1.0000` — hybrid
dense+sparse tìm đúng tài liệu cho cả 56/56 câu trong 20 ứng viên. Mọi giả
thuyết kiểu "cần embedding tốt hơn để tìm ra tài liệu" bị bác trên corpus
này. Việc hoãn nâng cấp embedding (2026-08-19) là đúng, và nay có số đo
chống lưng chứ không chỉ là lập luận.

**(b) Cross-encoder rerank hiện KHÔNG đáng đồng tiền — nhưng vì chất lượng,
không phải vì chi phí.** Chi phí chỉ 21ms trên GPU, không đáng kể. Vấn đề là
nó làm `recall_at_6` **tụt 2,1 điểm phần trăm** và MRR đi ngang. Tách theo
hạng thì thấy hai chiều ngược nhau: nó **giúp** câu `easy` (+0,053 MRR) và
**hại** câu `hard` (−0,102 MRR) — đúng ngược với lý do người ta dùng
cross-encoder.

**(c) Golden set này đã cạn dư địa ở `recall@20`.** Bằng 1,0 nghĩa là không
thay đổi nào của P1/P2/P3 có thể cải thiện số đó — nó chỉ còn phân giải được
qua `recall_at_6` và `mrr`. Đây là hạn chế thật của bộ đo, phải nói ra: muốn
đo tầng một thì cần câu khó hơn (hỏi bắc cầu nhiều văn bản, hỏi bằng thuật
ngữ dân dã không xuất hiện trong luật).

### 10.2 Giả thuyết đã BÁC — đừng điều tra lại

Nghi ngờ đầu tiên cho (b) là `RERANK_MAX_LENGTH=512` cắt mất phần liên quan,
vì tokenizer XLM-R sinh nhiều token hơn `cl100k` cho tiếng Việt. **Sai.** Đo
trên cả 3.300 chunk qua đúng tokenizer của `bge-reranker-v2-m3`:

```
XLM-R tokens : p50=138  p90=217  p99=364  max=1581
vượt 512     : 11 chunk (0,3%)
```

Cắt ngắn không phải nguyên nhân.

### 10.3 Quyết định về `torch==2.11.0+cu128`

**Giữ dep, nhưng "bật rerank mặc định" trở thành câu hỏi mở.**

Giữ vì: (i) chi phí thật là 21ms/truy vấn, không phải lý do để gỡ; (ii) nay
đã có thước đo nên mọi thay đổi rerank sau này đo được; (iii) kill-switch
`RAG_RERANK_ENABLED` hoạt động đúng, đã kiểm cả hai chiều.

Chưa đổi mặc định vì spec §9 chốt plan này **không đụng production** — đổi
`RAG_RERANK_ENABLED` mặc định sẽ làm chính baseline vừa sinh mất nghĩa. Việc
đó thuộc plan sau, và plan đó cần trả lời trước: vì sao cross-encoder lại
dìm đúng nhóm câu diễn đạt khác? Cảnh báo cỡ mẫu: `hard` chỉ n=17, nên
−0,102 MRR tương đương 1–2 câu đổi hạng. Cần mở rộng nhóm `hard` trước khi
kết luận mạnh hơn.

> **Câu hỏi mở nêu ở đây ĐÃ ĐƯỢC TRẢ LỜI cùng ngày — xem §11.** Giữ nguyên
> mục này làm bản ghi trạng thái tại thời điểm sinh baseline.

## 11. Vì sao rerank dìm nhóm `hard` — spike 2026-08-19

Chạy lại golden set hai chiều, ghi hạng của nhãn đúng cho **từng câu**.

### 11.1 Là quy luật, không phải nhiễu — nhưng "rerank kém" là kết luận SAI

| Hạng | n | tệ đi | tốt lên | không đổi |
|---|---|---|---|---|
| easy | 31 | 1 | 4 | 26 |
| hard | 17 | **6** | 4 | 7 |
| trap | 8 | 1 | 1 | 6 |

Hồi quy lan trên nhóm `hard` (6/17) chứ không dồn vào 1–2 câu, nên không thể
gạt đi là nhiễu. Nhưng ba ca tệ nhất có **ba nguyên nhân khác nhau**, và chỉ
một thuộc về reranker.

**(a) Reranker không phân biệt quy tắc với ngoại lệ của chính nó.**
*"công ty muốn cho nhân viên nghỉ việc thì cần căn cứ gì?"* (hạng 1 → 10).
Nhãn đúng: `Điều 36. Quyền đơn phương chấm dứt HĐLĐ của người sử dụng lao
động`. Rerank đưa lên hạng 2: `Điều 37. Trường hợp người sử dụng lao động
KHÔNG được thực hiện quyền đơn phương chấm dứt`. Cross-encoder bám cụm từ
pháp lý dùng chung và chọn **điều phủ định**. Đây là điểm yếu thật, và giải
thích vì sao câu `hard` (diễn đạt dân dã: "công ty", "nghỉ việc") chịu thiệt
nhiều hơn câu `easy`.

**(b) Rác từ ingest chiếm hạng 1 — lỗi P3 tràn vào rerank.**
*"trường hợp nào được miễn thuế xuất nhập khẩu?"* (hạng 7 → 12). Hạng 1 và 3
đều là `"Điều ước quốc tế mà Cộng hòa xã hội chủ nghĩa Việt Nam là..."` —
đúng loại mảnh câu mà `_HEADING_RE` nhận nhầm làm mục (§3). Reranker không
sai; nó bị cho ăn rác. Đây là bằng chứng THẬT đầu tiên cho thấy lỗi ingest
gây hại đo được, không còn là mối lo lý thuyết.

**(c) Nhãn của golden set quá hẹp.**
*"một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?"* (hạng 3 → 7).
Rerank đưa lên `Điều 309/311/315` Luật Thương mại (*hậu quả pháp lý của tạm
ngừng / đình chỉ hợp đồng*) — **câu trả lời hợp lý**, nhưng nhãn chỉ chấp
nhận Bộ luật Dân sự. Lỗi ở bộ đo, không phải ở retriever.

### 11.2 Phát hiện phụ: top-6 chứa 4,80 mục phân biệt

> **SỬA LẠI 2026-08-19, cùng ngày.** Bản đầu của mục này đặt tiêu đề "20% ô
> ngữ cảnh đang lãng phí vì trùng lặp" và gọi đó là phát hiện đáng giá hơn cả
> câu hỏi gốc. **Chữ "lãng phí" là suy diễn, không phải số đo — và nó sai.**
> Đã thử sửa và đo, kết quả ở §11.4. Giữ mục này để thấy quan sát nào là
> thật và diễn giải nào là thêm vào.

Số đo (thật): top-6 chứa **4,80/6 mục phân biệt** trung bình, và **20/56 câu
có ≤4 mục phân biệt**. Ví dụ ca (a): `Điều 42` ở hạng 1 *và* 4, `Điều 99` ở
hạng 3 *và* 6.

Rerank **không** phải nguyên nhân: bật 4,80 vs tắt 4,73 mục phân biệt — bật
còn nhỉnh hơn.

Diễn giải (đã bị bác ở §11.4): rằng các ô đó "lãng phí" và pipeline cần một
bước khử trùng lặp theo mục.

### 11.3 Kết luận: KHÔNG đổi `RAG_RERANK_ENABLED`

Bằng chứng không ủng hộ "rerank có hại". Nó hoà hoặc thắng ở `easy` và
`trap`, và 2 trong 3 ca hồi quy nặng nhất có nguyên nhân **nằm ngoài
reranker**. Tắt nó là chữa sai chỗ.

Thứ tự việc tiếp theo, đã ĐỔI so với bảng cuối plan dựa trên dữ liệu này:

1. ~~Khử trùng lặp theo mục trong top-k~~ — **ĐÃ THỬ VÀ PARK, xem §11.4.**
2. **Eval sinh câu trả lời chạy qua retrieval THẬT** — nay là việc chặn, xem
   §11.4.
3. **P3 dọn rác ingest** — nay có bằng chứng nó chiếm hạng 1 của câu thật.
4. **Sửa nhãn ca (c)** và soát lại golden set cho câu có nhiều văn bản trả
   lời được.
5. *Sau đó* mới quay lại "reranker có phân biệt được quy tắc với ngoại lệ
   không" — pool sạch rồi thì phép đo mới có nghĩa.

## 12. Khử trùng lặp theo mục: đã thử, đã đo, đã PARK

Viết `compress()` thành trần-theo-mục-có-bù (thay cho `chunks[:k]` thuần),
cộng 10 unit test. Code chạy được, 1731 test mặc định xanh. Đo trên chính
golden set 56 câu:

| cap | recall@6 | mrr | mục/6 | câu ≤4 mục |
|---|---|---|---|---|
| 0 (cũ) | 0.9196 | 0.8182 | 4.80 | 20 |
| 1 | 0.9196 | 0.8182 | 6.00 | 0 |
| 2 | 0.9196 | 0.8182 | 5.12 | 16 |
| 3 | 0.9196 | 0.8182 | 4.95 | 20 |

**`recall@6` và `mrr` không đổi một chữ số nào ở cả bốn cấu hình.** Không
phải "tăng nhẹ" — bằng hệt.

### 12.1 Hai điều học được

**(a) Bộ đo mù với cả mặt lợi, không chỉ mặt hại.** §11.2 dự đoán bộ đo
không thấy được mặt hại (bỏ mất chunk chứa câu trả lời của một Điều dài) vì
nhãn không đổi. Thực tế nó cũng không thấy mặt lợi: `recall@20 = 1.0` nên
nhãn đúng luôn nằm trong pool, nhưng bù thêm ~1,2 mục vào top-6 **không cứu
được ca nào**. Suy ra 8% ca trượt có nhãn đúng nằm sâu hơn nhiều, không ở
biên 7–8.

**(b) Tiền đề "ô lãng phí" là SAI.** Hai chunk cùng một Điều **không phải
bản trùng**. `chunking.py` chỉ chia một mục thành nhiều chunk khi mục đó
dài, nên chúng mang **nội dung khác nhau của cùng điều luật**. "6 ô chứa 4,8
mục" không phải lãng phí — giữ thêm một mảnh của đúng điều luật thường có
giá trị hơn mảnh đầu của một điều không liên quan. Chữ "trùng lặp" trong
§11.2 là cách gọi sai, và nó là toàn bộ động cơ của thay đổi này.

### 12.2 Quyết định

Park trên nhánh `rag-section-cap-parked` (commit `de7d23c`), **không merge**.
Code và test giữ nguyên để khỏi viết lại; thứ thiếu là bằng chứng, không
phải code.

### 12.3 Việc chặn tiếp theo: eval sinh chạy qua retrieval thật

Thứ duy nhất đo được lợi/hại của mọi thay đổi ở tầng `compress()` là **chất
lượng câu trả lời**, không phải hạng của nhãn. Hiện `eval_synthesis` nạp
`fixtures.load_chunks()` — chunk đóng băng, retriever bị bypass — nên nó
không thể thấy gì.

Đây cũng chính là lỗ hổng chặn P4 (thay `compress()`, sửa `passes_floor`).
Vì thế nó lên trước P1/P2/P3 trong thứ tự việc.

## 13. Chân sparse của hệ "hybrid" đã chết từ đầu (2026-08-20)

Định sửa `passes_floor` (mệnh đề "bất kỳ FTS hit nào cũng qua cổng"), nhưng
phép đo dẫn tới một thứ lớn hơn.

### 13.1 Số đo

`_sparse()` trả về **0 kết quả cho 64/64** câu hỏi của golden set.

`plainto_tsquery` nối mọi từ tố bằng **AND**. Sau pyvi, một câu hỏi thật thành
`thuế_suất thuế giá_trị gia_tăng là bao_nhiêu ?` — đòi cả `là` lẫn `bao_nhiêu`
phải có trong CÙNG một chunk. Văn bản luật không bao giờ chứa "bao nhiêu", nên
AND luôn hỏng.

Hệ quả: `retrieve()` thực chất chạy **dense-only**; `_rrf` hợp nhất đúng MỘT
nguồn dù `method="hybrid-rrf"` nói khác. Đây là **lần thứ ba trong một ngày**
gặp cùng lớp lỗi *"năng lực khai báo trong code nhưng không bao giờ chạy"* —
sau cross-encoder rerank (chết 6 tuần vì dep thiếu) và sổ ngân sách (mù với
mọi lượt hỏng).

Lỗi không lộ ra ở test cơ học vì truy vấn từ khoá NGẮN vẫn chạy
(`thuế suất` → 20 kết quả). Nó chỉ lộ với **câu hỏi thật của người dùng**.

### 13.2 Đã thử hồi sinh, và đã BỎ

| Cấu hình | FTS bắn được | `recall@20` | `mrr` |
|---|---|---|---|
| Hiện tại (AND) | 0/64 | **1,0000** | **0,8385** |
| `to_tsquery` OR | 64/64 | **0,9766** | 0,8375 |
| OR + lọc token DF>30% | 64/64 | **0,9766** | 0,8367 |

Cả hai biến thể đều **TRƯỢT cổng**. Ứng viên sparse chiếm chỗ trong pool 20 và
đẩy chunk đúng ra ngoài. Giả thuyết "do hư từ kéo `ts_rank` lên" cũng bị bác:
lọc hư từ dựng **từ chính corpus** (document-frequency > 30%) cho kết quả y
hệt và `mrr` còn nhích xuống.

Đã revert; đo lại sau revert khôi phục baseline chính xác từng chữ số.

### 13.3 Kết luận, và vì sao nó không tầm thường

**Trên corpus này, dense-only TỐT HƠN hybrid như đang thiết kế.** Một thành
phần chết suốt nhiều tháng, và hồi sinh nó làm hệ thống tệ đi.

Nguyên nhân nằm ở chỗ ứng viên vào pool, không ở truy vấn: `retrieve()` lấy
`ordered[:TOP_N]` — tức **20 chỗ chia nhau** giữa hai chân. Khi chỉ có dense
sống, dense được cả 20. Khi sparse sống lại, nó lấy mất chỗ của dense mà không
mang lại ứng viên tốt hơn.

Muốn hồi sinh sparse cho đúng thì phải đổi **cách vào pool** (ví dụ mỗi chân
giữ TOP_N riêng, pool tối đa 2×TOP_N trước rerank — reranker trên GPU dư sức
chấm 40 cặp), chứ không phải sửa truy vấn. Đó là một đợt riêng, có rủi ro
riêng, và cần đo lại từ đầu.

### 13.4 Hệ quả cho `passes_floor`

Mệnh đề "bất kỳ FTS hit nào cũng qua cổng" hiện **vô hại vì FTS không bao giờ
hit**. Nó chỉ trở thành nguy hiểm nếu sparse được hồi sinh. Việc sửa
`passes_floor` vì thế **gắn với** việc hồi sinh sparse, không phải việc độc
lập.

Nhưng đo được một điều khác, quan trọng hơn: **cổng `passes_floor` hiện không
chặn gì cả.** Cả 4 câu ngoài corpus đều qua, và **không câu nào có FTS hit** —
chúng qua bằng chính ngưỡng cosine. `bge-m3` chấm 0,353–0,603 cho câu hoàn
toàn lạc đề ("thủ đô nước Pháp", "dự báo thời tiết Hà Nội"), trong khi câu
trong corpus có min 0,562. **Hai phân bố CHỒNG LẤN**, nên không ngưỡng cosine
đơn nào tách sạch được.

Đây là bản đính chính cho review 2026-08-19: tôi đã quy lỗi cổng vô hiệu cho
mệnh đề FTS. Sai — thủ phạm là ngưỡng cosine nằm dưới mức nhiễu của chính
embedding model.
