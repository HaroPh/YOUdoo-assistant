# P3a — Vệ sinh ingest cho PDF luật

Ngày: 2026-08-19
Trạng thái: đã duyệt (chủ dự án chốt phạm vi P3a+P3d, hoãn P3b, bỏ P3c)
Tiền đề: `2026-08-19-retrieval-eval-design.md` (P0),
`2026-08-19-synthesis-live-eval-design.md`

## 1. Vấn đề, đo được

Corpus 3.300 chunk, trong đó 3.256 từ 9 PDF luật.

| Hỏng hóc | Quy mô | Đã chứng minh gây hại chưa? |
|---|---|---|
| Rác header/footer trang nằm **giữa nội dung** | **727/3256 chunk (22%)** | Chưa đo trực tiếp, nhưng nó vào embedding, `ts_vector`, cặp cho reranker VÀ ngữ cảnh gửi LLM |
| Mục là **mảnh câu tham chiếu chéo** | 15 mục | **RỒI** — `"Điều ước quốc tế mà Cộng hòa…"` chiếm hạng 1 của một câu hỏi thật (P0 §11.1(b)) |
| PDF ra 0 block → `skipped` im lặng | chưa xảy ra | Chưa; là bề mặt lỗi, không phải lỗi hiện hành |

Ví dụ rác trang, nguyên văn từ `rag_chunks`:

```
…yền nhân thân và tài sản. 22:47 13/7/26 about:blank about:blank 1/164 2. Cá nhân, pháp nhâ…
```

Mỗi mảnh câu tham chiếu (`"Điều 11 của Luật này quy định."`) **cắt đôi một Điều
thật**, làm nửa sau mất breadcrumb đúng.

## 2. Phạm vi

**Trong phạm vi:** lọc rác trang theo tần suất **và vị trí rìa**; sửa `_HEADING_RE` khỏi khớp
tham chiếu giữa câu; PDF 0 block báo lỗi lớn tiếng; re-index; đo bằng cả hai
bộ eval.

**Ngoài phạm vi, và vì sao:**

- **Phân cấp Chương › Mục › Điều (P3b).** Nó đổi hình dạng `section_path`, phá
  **cả 57 nhãn** của hai bộ eval vừa xây, nên phải kèm một đợt di trú nhãn.
  Giá đó chỉ đáng trả khi có bằng chứng phân cấp giúp truy xuất — chưa có, và
  nay đã có hai thước đo để lấy bằng chứng đó.
- **XLSX gom cửa sổ hàng (P3c).** `bang_gia.xlsx` có đúng **8 chunk** toàn
  corpus. YAGNI cho tới khi có bảng tính thật.
- **Luật `isupper()`.** Xem §4.

## 3. Lọc rác trang: tần suất, KHÔNG khớp mẫu cứng

Trong `parse_pdf`, sau khi tách dòng và trước khi trả về: đếm số **trang phân
biệt** mà mỗi dòng xuất hiện, **sau khi thay mọi chữ số bằng `#`**. Loại dòng
nào xuất hiện trên ≥60% số trang của tài liệu.

**Chuẩn hoá chữ số là mấu chốt.** `about:blank 5/164` và `about:blank 6/164`
là hai chuỗi khác nhau; đếm trần thì mỗi cái chỉ 1 trang và bộ lọc bỏ sót.
Chuẩn hoá xong, cả hai thành `about:blank #/#`.

**Và tần suất một mình là CHƯA ĐỦ.** Quét cả 9 tệp (bản đầu của spec này chỉ
đo `boluat-danssu.pdf` rồi kết luận "vực rộng 23 lần" — sai vì cỡ mẫu 1):

| | tần suất theo trang | nằm ở **rìa trang** |
|---|---|---|
| 18 nhóm rác (2 nhóm × 9 tệp) | **100%** | **100%** |
| `# #.#` — dương tính giả | 48% | 15% |

`# #.#` là **hàng bảng mã HS** trong phụ lục `luat-thuexuatnhapkhau.pdf`:
nhiều hàng KHÁC NHAU bị chuẩn hoá chữ số gộp chung một nhóm, đẩy tần suất lên
48%. Đó đúng là cơ chế hỏng §8 lo tới, và với ngưỡng 60% thì nó chỉ thoát nhờ
12 điểm phần trăm — quá mỏng để tin.

Vì thế điều kiện là **VÀ**, không phải hoặc: một dòng bị loại khi
(a) dạng chuẩn-hoá-chữ-số xuất hiện trên ≥60% số trang, **VÀ**
(b) ≥90% số lần nó xuất hiện nằm trong 2 dòng đầu hoặc 2 dòng cuối của trang.

Điều kiện (b) có nguyên lý chứ không phải tinh chỉnh: header/footer **theo
định nghĩa** nằm ở rìa trang, còn hàng bảng nằm giữa. Số đo xác nhận:
rác 100% ở rìa, hàng bảng 15%.

**Vì sao không khớp mẫu `about:blank`:** đó là dấu vết của *cách in* bộ PDF
này (print-to-PDF từ trình duyệt). Tài liệu nguồn khác sẽ mang rác khác — số
trang, tên tệp, ngày in. Tần suất bắt được cả loại chưa gặp; khớp mẫu cứng
chỉ bắt được loại đã gặp, và im lặng bỏ sót phần còn lại.

**Chốt an toàn:** chỉ áp dụng khi tài liệu có ≥5 trang. Với tài liệu 2 trang,
một dòng hợp lệ lặp ở cả hai trang đã là 100%.

## 4. `_HEADING_RE` không được khớp tham chiếu giữa câu

Hiện tại nhánh từ khoá là `^\s*(Chương|Mục|Điều)\b`, nên `"Điều 11 của Luật
này quy định."` được nhận là heading.

Sửa: `Điều` chỉ là heading khi mang dạng `Điều <số>.` và theo sau là tiêu đề —
loại các dạng `Điều <số> của…`, `Điều <số> này…`, `Điều <số> khoản…`.

`Chương` và `Mục` **giữ nguyên** cách nhận hiện tại. Chúng sinh ra 190 mục
trống, nhưng đó là vấn đề của P3b; đụng vào bây giờ là trộn thêm biến vào
cùng một lần re-index.

**KHÔNG đụng luật `isupper()` lần này**, dù review 2026-08-19 có nêu. Ca gây
hại đã chứng minh được là do tham chiếu giữa câu, không phải ALL-CAPS. Bản
thân ALL-CAPS thì lẫn lộn: quốc hiệu và tên cơ quan là rác, nhưng tiêu đề
chương (`"QUY ĐỊNH CHUNG"`) là heading thật — và phân biệt hai loại đó cần
chính phân cấp Chương mà §2 vừa hoãn.

## 5. PDF ra 0 block → báo lỗi lớn tiếng

`_ingest_file` hiện trả `{"ingested": 0, "skipped": 1, "chunks": 0}` khi
`_chunks_for` không sinh gì. Với PDF scan (không có lớp text), tài liệu vắng
mặt khỏi corpus mà không ai biết — cùng lớp lỗi với reranker chết im lặng.

Đổi thành ném lỗi nêu tên tệp. Tệp không hỗ trợ (đuôi lạ) vẫn `skipped` như
cũ; chỉ tệp **được nhận** mà ra rỗng mới là lỗi.

## 6. Re-index: cái bẫy phải nêu trước

`_ingest_file` bỏ qua tệp khi `content_hash` khớp bản trong `rag_documents`.
Ở đợt này **tệp không đổi, chỉ code đổi**, nên chạy lại `ingest_path` sẽ báo
`skipped` cho cả 17 tài liệu và **không gì xảy ra** — trong khi trông như đã
chạy xong.

Re-index bắt buộc phải **xoá `rag_documents` trước** (cascade xoá
`rag_chunks`). Đây là bẫy dễ mắc nhất của cả đợt và phải nằm ngay trong plan,
không phải trong đầu người chạy.

## 7. Cách đo

Chạy trước và sau trên cùng một lượt re-index.

**Số đo cơ học (tất định, không tốn LLM):**

| Chỉ số | Trước | Kỳ vọng sau |
|---|---|---|
| chunk chứa `about:blank` | 727 | 0 |
| mục là mảnh câu (`^Điều \d+ (của\|này\|khoản)`) | 15 | 0 |
| tổng số chunk | 3.300 | giảm nhẹ (rác biến mất khỏi thân) |

**Số đo chất lượng:**

- `retrieval` — `recall@20 / recall@6 / mrr`. 57 nhãn sống sót vì
  `section_path` của các Điều hợp lệ không đổi chuỗi.
- `synthesis_live` — `fact / refusal / citation`.

**KHÔNG cam kết trước rằng eval sẽ nhúc nhích.** `synthesis_live` đang chạm
trần 1,0 nên nhiều khả năng đứng yên; `retrieval` có dư địa ở `recall@6` và
`mrr`. Nếu cả hai đứng yên, kết luận là "dọn rác không đổi chất lượng đo
được" và phải ghi đúng như vậy — giống hệt cách đã xử lý kết quả âm của khử
trùng lặp (P0 §12).

Cổng: cả hai bộ `>= baseline`. Tụt là chặn, vì đợt này chỉ dọn rác — không
có lý do nào để chất lượng đi xuống.

## 8. Rủi ro

**Bộ lọc ăn nhầm nội dung thật.** Rủi ro này ĐÃ THÀNH HIỆN THỰC ở bản thiết
kế đầu và được bắt bằng cách mở rộng phép đo từ 1 tệp lên 9 — xem §3. Chốt
bằng điều kiện kép (tần suất VÀ vị trí rìa), sàn ≥5 trang, và một test dựng
tài liệu giả có hàng bảng lặp ở GIỮA trang để khẳng định nó KHÔNG bị loại.

**Nhãn eval trôi.** `section_path` của Điều hợp lệ không đổi, nhưng
`chunk_index` thì đổi hết. Cả hai bộ eval đã neo theo `(tệp, mục)` chứ không
theo `chunk_index` — đúng lý do đã chọn neo đó (P0 §4). Test hợp đồng của cả
hai bộ phải chạy lại sau re-index và phải xanh; đó là phép kiểm rằng quyết
định neo hồi P0 thật sự trả cổ tức.

**Baseline cũ mất nghĩa.** Sau re-index, baseline `retrieval` và
`synthesis_live` phải ghi lại. Ghi đè chỉ khi cổng §7 đã qua.

## 9. Kết quả (2026-08-19)

Re-index mất 3m58s, `ingested: 17, skipped: 0, chunks: 3249`.

### 9.1 Số đo cơ học — đạt hoàn toàn

| Chỉ số | Trước | Sau |
|---|---|---|
| chunk chứa `about:blank` | 727 | **0** |
| mục là mảnh câu | 15 | **0** |
| tổng chunk | 3.300 | 3.249 |
| tài liệu | 17 | 17 |

**Test hợp đồng của cả hai bộ eval sau re-index: XANH.** `chunk_index` đổi hết
mà không nhãn nào trôi — quyết định neo theo `(tệp, mục)` hồi P0 §4 trả cổ
tức đúng như dự đoán.

### 9.2 `retrieval` — cổng ĐẠT, cải thiện thật

| Số đo | Trước | Sau | delta |
|---|---|---|---|
| `recall_at_20` | 1,0000 | 1,0000 | 0 |
| `recall_at_6` | 0,9196 | **0,9375** | **+0,0179** |
| `mrr` | 0,8253 | **0,8416** | **+0,0163** |
| `easy` mrr | 0,9285 | **0,9581** | **+0,0296** |
| `hard` / `trap` mrr | — | không đổi | 0 |

Đây là thay đổi ĐẦU TIÊN trong loạt P có delta dương đo được. Baseline đã ghi
lại.

### 9.3 `synthesis_live` — cổng TRƯỢT, một ca, ổn định 3/3 lượt

| Số đo | Trước | Sau |
|---|---|---|
| `fact_acc` | 1,0000 | **0,9375** |
| `refusal_acc` | 1,0000 | 1,0000 |
| `citation_acc` | 1,0000 | **0,9375** |

Ca trượt: *"bộ luật dân sự quy định mức phạt vi phạm hợp đồng thế nào?"*
(`distractor`, nhãn `boluat-danssu.pdf › Điều 418`, mục cạnh tranh
`Điều 301` của `boluat-thuongmai.pdf`).

Truy xuất ĐÚNG — Điều 418 ở hạng 1, Điều 301 hạng 2. Hỏng ở tầng sinh.

Câu trả lời thật: *"mức phạt vi phạm hợp đồng do các bên tự thỏa thuận. Tuy
nhiên, mức phạt này **không được vượt quá 8%** giá trị phần nghĩa vụ hợp đồng
bị vi phạm…"*, dẫn nguồn **chỉ** `Điều 301 (boluat-thuongmai.pdf)`.

**Câu trả lời này SAI về nội dung, không chỉ khác cách diễn đạt.** Câu hỏi nêu
đích danh Bộ luật Dân sự; Điều 418 khoản 2 nói mức phạt do các bên thỏa
thuận, **không có trần**. Trần 8% là của Luật Thương mại Điều 301 — chính mục
cạnh tranh. Vậy cả `fact_ok=False` lẫn `citation_ok=False` đều là phán quyết
ĐÚNG cho một câu trả lời sai.

> **Ghi lại một nhận định đã rút:** báo cáo đầu tiên mô tả `fact_ok` là "lỗi
> đo, chuỗi `expect` quá dài nên diễn đạt lại thì trượt oan", và đề nghị rút
> ngắn `expect`. Sai — nhận định đó đưa ra trước khi đọc kỹ nội dung. Nới
> `expect` ở đây chính là uốn thước đo để nó chấp nhận một câu trả lời sai.
> KHÔNG sửa `expect`; giữ ca trượt.

### 9.4 Nguyên nhân, đo được ở tầng reranker (không cần LLM)

Điểm cross-encoder cho cùng câu hỏi:

| Chunk | Điểm | Cách mục đúng |
|---|---|---|
| Điều 418 (đúng) | +3,2988 | — |
| Điều 301 **sạch** (sau P3a) | +3,0020 | **0,2969** |
| Điều 301 **có rác** (trước P3a) | +2,2910 | **1,0078** |

**Rác từng đóng vai một bộ phân biệt tình cờ.** Gỡ nó làm mục cạnh tranh mạnh
lên +0,71 điểm, khiến biên giữa mục đúng và mục cạnh tranh sụp từ 1,01 xuống
0,30 — mất 70%. Mục đúng vẫn thắng thứ hạng, nhưng model đứng trước hai đoạn
đều sạch và điểm gần bằng nhau thì trộn cả hai.

### 9.5 Kết luận và việc mở

P3a **đúng về nguyên tắc**: rác không được phép là thứ chịu lực. Việc gỡ nó
đã **phơi ra** một điểm yếu vốn có chứ không tạo ra điểm yếu mới — biên phân
biệt thật giữa Điều 418 và Điều 301 chỉ là 0,30 điểm, và trước đây nó được
che bởi một chuỗi rác in ấn.

Việc mở, KHÔNG thuộc P3a: làm sao để hệ thống không nhập trần 8% của Luật
Thương mại vào câu hỏi Dân sự khi hai điều luật gần nhau. Đó là bài toán của
tầng truy vấn (P2) hoặc của reranker, không phải của ingest.

`synthesis_live` giữ nguyên baseline cũ, **chưa ghi lại** — cổng trượt.
