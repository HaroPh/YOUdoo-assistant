# Lộ trình RAG — viết lại theo số đo

Ngày: 2026-08-20
Thay thế: bảng P1–P4 trong review 2026-08-19

## 1. Vì sao viết lại

P1–P4 được viết khi project **chưa có một số đo nào** cho tầng truy xuất hay
tầng sinh. Chúng là suy luận từ đọc code — hợp lý, nhưng chưa được kiểm chứng.

Nay đã có hai bộ đo chạy trên corpus thật, và chúng **bác bỏ tiền đề chính**
của P1 và P2.

## 2. Những gì nay đã đo được

**Bộ `retrieval`** — 64 câu, neo `(tệp, mục)`:

| Số đo | Giá trị |
|---|---|
| `recall_at_20` | **1,0000** |
| `recall_at_6` | 0,9453 |
| `mrr` | 0,8385 |

**Bộ `synthesis_live`** — 28 câu, chạy `retrieve()` → `synthesize()` thật:

| Số đo | trước sửa prompt | sau |
|---|---|---|
| `fact_acc` | 0,8750 | **0,9583** |
| `refusal_acc` | 0,9643 | **1,0000** |
| `citation_acc` | 0,9167 | **1,0000** |
| `distractor` fact | 0,7857 | **0,9286** |

### 2.1 Ba kết luận buộc phải đổi lộ trình

**(a) Tầng truy xuất KHÔNG phải nút thắt.** `recall@20 = 1,0000` trên cả 64
câu — kể cả 8 cặp Điều **trùng hệt tiêu đề trong cùng một tệp**. Hệ thống tìm
ra đúng tài liệu ở **mọi** câu. `deep_chunk` fact = 1,0000, nên "đọc tới chunk
sau" cũng không phải chỗ hỏng.

**(b) Nút thắt là CHỌN ĐÚNG ĐIỀU trong số đã tìm được.** Ba ca trượt của
baseline đều là một điểm yếu, biểu hiện ba kiểu: trộn hai nguồn, lấy nhầm
điều, và bỏ cuộc (trả `GUARD_MSG` dù đáp án ở hạng 3).

**(c) Một đoạn prompt chữa được phần lớn.** Thêm đúng một quy tắc phân định
đối tượng: `distractor` fact **0,7857 → 0,9286**, `refusal_acc` lên 1,0000,
hai trong ba ca trượt biến mất. Không đụng hạ tầng, không đổi model.

Và quan trọng: trước khi sửa prompt, `3.1-flash-lite` thua rõ `3.5-flash-lite`
ở nhóm khó (0,7857 vs 0,9286). **Sau khi sửa, 3.1 đạt đúng con số của 3.5.**
Khoảng cách giữa hai model là **prompt thiếu một quy tắc**, không phải năng
lực model.

## 3. Ba thành phần chết, phát hiện trong một ngày

| Thành phần | Trong code | Chạy thật? | Cách phát hiện |
|---|---|---|---|
| Cross-encoder rerank | có, 4 test | **chết 6 tuần** — dep không nằm trong `requirements.txt` | đọc `method` của `RetrievalResult` bằng tay |
| Chân sparse của hybrid | có, có test, có trong RRF | **0/64 câu trả về gì** — `plainto_tsquery` nối AND | đo trên câu hỏi thật |
| Sổ ngân sách | có, ghi đúng lượt thành công | **mù với mọi lượt hỏng** — `_finish()` chỉ chạy khi thành công | ép hỏng bằng key sai |

**Điểm chung, và đây mới là bài học**: cả ba đều *fail-open* hoặc *skip* khi
trục trặc, và không cái nào khẳng định "tôi đã thực sự chạy". Test cơ học
không bắt được vì chúng mock hoặc dùng dữ liệu tổng hợp.

Cách chữa đã dùng và nên dùng tiếp: **test không mock, không skip, không nằm
sau biến môi trường** — `test_reranker_deps.py`, `test_ingest_guard.py`.

## 4. Lộ trình mới

### Nhóm A — tính đúng và an toàn, KHÔNG phụ thuộc chất lượng xếp hạng

Giá trị của nhóm này không đổi dù `recall@20` có bằng 1,0 hay không.

**A1. Sổ ngân sách phải đếm thứ nhà cung cấp đếm.** Hiện sổ đếm lượt *thành
công*, Google đếm lượt *gọi*. Khi mọi thứ suôn sẻ chúng trùng nhau; đúng lúc
bắt đầu 429 — lúc sổ cần chính xác nhất — chúng tách ra và sổ báo còn dư
trong khi ví đã cạn. Hôm nay việc này làm hỏng **hai** lượt chạy eval.

**A2. RAG không tôn trọng phân quyền vai.** Cột `visibility` tồn tại trong
`schema.sql` nhưng **không code nào đọc**. ERP có 4 tài khoản Odoo riêng và 3
tiến trình MCP cách ly; RAG thì mọi vai đọc mọi chunk. Đây là bất đối xứng an
ninh, không phải chuyện chất lượng.

**A3. Không có `effective_date` cho văn bản luật.** Corpus 98,7% là PDF luật.
Không có trường hiệu lực nghĩa là không phân biệt được điều khoản còn hiệu lực
với điều đã bị bãi bỏ. Đây là rủi ro **tính đúng**, và với tài liệu pháp luật
thì nó nghiêm trọng.

### Nhóm B — nhắm vào nút thắt đã đo

**B1. Tiếp tục đường prompt.** Nó vừa cho lợi ích lớn nhất với chi phí thấp
nhất trong cả ngày. Ca còn trượt (BHXH tự nguyện) cho thấy model **nay nhận ra
có hai chế độ** nhưng chưa chọn dứt khoát — còn dư địa.

**B2. Reranker cho cặp Điều gần trùng.** Số liệu mâu thuẫn nhau và cần gỡ:
rerank **hại** nhóm `hard` về MRR (−0,102, n=17) nhưng **cứu** một ca
`distractor` mà RRF thuần chọn sai. Có thể nó tốt cho phân định và tệ cho diễn
đạt-khác — chưa đủ dữ liệu để nói.

### Nhóm C — lỗ hổng dụng cụ đo còn chặn quyết định

**C1. Không có bộ eval nào đo hội thoại nhiều lượt.** Cả 12 bộ đều một-lượt.
Nghĩa là việc giải chiếu ở câu hỏi nối tiếp ("thế còn hàng giảm giá?") **chưa
bao giờ được đo**. Đây là lỗ hổng lớn nhất còn lại của hệ đo, và nó là lý do
duy nhất còn sót để cân nhắc P2 (query rewrite).

**C2. Nhóm `hard` chỉ n=17.** Kết luận "rerank hại câu hard" treo trên cỡ mẫu
đó suốt từ đầu.

**C3. `synthesis_live` còn dư địa** (0,9583) nhưng `retrieval` thì **chạm
trần** ở `recall@20`. Mọi thay đổi ở tầng truy xuất sẽ chỉ có thể làm nó tụt.

### Nhóm D — BỎ hoặc HOÃN, kèm lý do đo được

| Việc | Quyết định | Lý do |
|---|---|---|
| **P2 query rewrite** | HOÃN | `recall@20 = 1,0` — nhắm vào chỗ không hỏng. Mở lại nếu C1 cho thấy hội thoại nhiều lượt hỏng. |
| **P1 metadata cho chất lượng truy xuất** | BỎ | cùng lý do. Phần *tính đúng* của P1 chuyển sang A2/A3. |
| **Hồi sinh chân sparse** | HOÃN | đã thử: `recall@20` 1,0000 → 0,9766. Muốn làm phải đổi **cách vào pool**, không phải truy vấn. |
| **P4 `compress()` trần theo mục** | PARK | hai thước đo độc lập đều không phân biệt được nó với việc không làm gì. Nhánh `rag-section-cap-parked`. |
| **P4 `passes_floor`** | KHÔNG SỬA ĐƯỢC BẰNG NGƯỠNG | phân bố chồng lấn: trong corpus min 0,562, ngoài corpus max 0,603. Sentinel của LLM đang gánh việc từ chối và làm tốt (`refusal_acc = 1,0`). |
| **P3b phân cấp Chương › Điều** | HOÃN | phá 57 nhãn của hai bộ eval, cần đợt di trú. Chưa có bằng chứng phân cấp giúp truy xuất. |
| **P3c XLSX** | BỎ | `bang_gia.xlsx` có 8 chunk toàn corpus. |
| **Đổi vai `synthesis` sang 3.5** | KHÔNG | lý do chính đã biến mất sau khi sửa prompt; cái giá (dồn ba vai vào một ví 500/ngày) không đổi. |

## 5. Thứ tự đề xuất

1. **A1** — nó vừa làm hỏng hai lượt đo hôm nay, và mọi việc sau đều cần đo.
2. **C1** — lỗ hổng đo lớn nhất còn lại; nó cũng quyết định P2 sống hay chết.
3. **A2** hoặc **A3** — tuỳ chủ dự án ưu tiên an ninh hay tính đúng pháp lý.
4. **B1/B2** — cải thiện chất lượng, nay đã đo được.

## 6. Nguyên tắc rút ra từ một ngày làm việc

**Đừng tin thành phần nào không có test chạy thật.** Ba thành phần chết trong
một ngày, cả ba đều "có test".

**Kết quả âm là kết quả.** Khử trùng lặp, hồi sinh sparse, lọc hư từ — ba lần
đo cho kết quả âm, và cả ba đều được ghi lại thay vì tinh chỉnh cho đến khi ra
số đẹp.

**Đo trước khi sửa, kể cả khi nguyên nhân "rõ ràng".** Review 2026-08-19 quy
lỗi `passes_floor` cho mệnh đề FTS; đo ra thủ phạm là ngưỡng cosine. Quy lỗi
hồi quy P3a cho việc dọn rác; đo ra là đặc thù của model. Quy lỗi `fact_ok`
cho chuỗi `expect` giòn; đọc kỹ ra câu trả lời sai thật.

**Thay đổi rẻ nhất thường ở prompt, nhưng chỉ khi có thước đo.** Một đoạn văn
cho +0,143 ở nhóm khó nhất. Không có `synthesis_live` thì không ai biết nó có
tác dụng hay không.
