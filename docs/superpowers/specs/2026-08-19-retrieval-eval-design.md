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
