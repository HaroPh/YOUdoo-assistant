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

**Trong phạm vi:** lọc rác trang theo tần suất; sửa `_HEADING_RE` khỏi khớp
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

Đo trên `boluat-danssu.pdf` (164 trang), sau chuẩn hoá:

| Dòng | Số trang xuất hiện |
|---|---|
| `about:blank #/#` | 164 |
| `#:# #/#/# about:blank` | 164 |
| `khác.` | 7 |
| `#. Theo thỏa thuận của các bên.` | 7 |

Khoảng cách 164 vs 7 — hơn 23 lần. Ngưỡng 60% nằm giữa một vực rộng, không
phải một con số tinh chỉnh mong manh.

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

**Bộ lọc tần suất ăn nhầm nội dung thật.** Chốt bằng ngưỡng 60% (dữ liệu cho
thấy vực giữa 4% và 100%), sàn ≥5 trang, và một test dựng tài liệu giả có
dòng hợp lệ lặp lại để khẳng định nó KHÔNG bị loại.

**Nhãn eval trôi.** `section_path` của Điều hợp lệ không đổi, nhưng
`chunk_index` thì đổi hết. Cả hai bộ eval đã neo theo `(tệp, mục)` chứ không
theo `chunk_index` — đúng lý do đã chọn neo đó (P0 §4). Test hợp đồng của cả
hai bộ phải chạy lại sau re-index và phải xanh; đó là phép kiểm rằng quyết
định neo hồi P0 thật sự trả cổ tức.

**Baseline cũ mất nghĩa.** Sau re-index, baseline `retrieval` và
`synthesis_live` phải ghi lại. Ghi đè chỉ khi cổng §7 đã qua.
