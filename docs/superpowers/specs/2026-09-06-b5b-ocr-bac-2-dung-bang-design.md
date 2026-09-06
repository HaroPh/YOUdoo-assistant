# OCR bậc 2 — dựng lại bảng từ toạ độ chữ

**Spec cha:** `docs/superpowers/specs/2026-09-04-tang-ocr-dung-chung-design.md`
(§6 hợp đồng artifact vùng-có-kiểu, §14 xếp bậc theo thứ tự). Spec này mở mục
"bậc 2" của bảng đó, sau khi điều kiện chặn — *có tài liệu scan thật để hiệu
chỉnh* — đã được gỡ ngày 2026-09-06.

## 1. Đề bài

Bậc 1 đọc được chữ từ ảnh, nhưng nhả ra **dòng phẳng**. Trên một trang bảng
thật, hàng thì còn mà cột thì mất sạch:

```
B- TÀI SẢN DÀI HẠN 200 2.083.822.081.658 2.078.113.448.434
```

Không có gì phân biệt `Mã số 200` với hai cột tiền, cũng không biết số nào là
*cuối kỳ* số nào là *đầu năm*. Đưa dòng này cho LLM đọc là mời nó đoán — đúng
thứ toàn bộ tầng nạp tài liệu được dựng ra để tránh.

**Việc của bậc 2, đúng một câu:** từ toạ độ chữ, trả lời *ô nào thuộc cột nào
và hàng nào*.

## 2. Số đo — cơ sở của mọi lựa chọn dưới đây

Đo ngày 2026-09-06 trên BCTC hợp nhất bán niên SCID (63 trang, **0 ký tự lớp
text**, không bị máy scan chèn OCR, **150 DPI thật**, rasterise đọc ở 200 DPI).

### 2.1 Khoảng trắng dọc KHÔNG phải tín hiệu — đã thử và bác bỏ

Cách hiển nhiên nhất là tìm khe trắng chạy dọc suốt trang. Đo thật:

| trang | số cột thật | khe trắng dọc suốt trang tìm được |
|---|---|---|
| 12 | 5 | 3 |
| 13 | 5 | 3 |
| 16 | 5 | **1** |
| 17 | 5 | **1** |

Nguyên nhân: dòng tiêu đề và chân trang chạy hết bề ngang, bịt mọi khe.

Đã thử bản vá hiển nhiên — loại các dòng "chạy suốt bề ngang" ra trước khi tính
khe. **Cũng hỏng: 0/4 trang loại được dòng nào**, vì dòng văn xuôi cũng có khe
giữa các từ vượt ngưỡng. Ghi lại cả hai thất bại ở đây để người sau không mất
thời gian đi lại.

### 2.2 Căn lề LÀ tín hiệu — sạch trên mọi trang đo được

Cụm mép **phải** của token tiền (khớp khuôn nhóm ba chữ số):

| trang | cụm 1 | cụm 2 | ⇒ số cột tiền |
|---|---|---|---|
| 12 | x≈1290–1305 (19 token) | x≈1545–1560 (19) | **2** ✓ |
| 13 | x≈1290–1305 (22) | x≈1545–1560 (20) | **2** ✓ |
| 16 | x≈1275 (18) | x≈1530 (18) | **2** ✓ |
| 17 | x≈1290–1305 (19) | x≈1530–1545 (16) | **2** ✓ |

Mép **trái** của chính những token đó thì tản mát — đúng như kỳ vọng với số căn
phải. Ngược lại, cột `Mã số` cụm rất chặt theo mép **trái** (trang 13: 38/38
token ở x≈915–930).

**Kết luận:** cột sinh ra từ **căn lề**, không phải từ khoảng trắng. Điều này
tổng quát được, vì nếu một bảng không căn lề thì chính người đọc cũng không
phân biệt nổi cột.

### 2.3 Kho đáp án miễn phí, đa định dạng

Corpus hiện có PDF **số** mà `pdfplumber` bóc bảng được:

| | |
|---|---|
| Tệp có bảng | **106** |
| Trang có bảng | **229** |
| Ô trích được | **31.416** |

Phủ phụ lục luật, biểu mẫu BCTC, 100 hoá đơn, biểu mẫu SSC, và sổ tay nhân sự
**tiếng Anh**. Đây là nền của cổng A ở §7.

### 2.4 Giới hạn của tầng đọc, KHÔNG phải việc của bậc 2

Trên trang 17: Tesseract đọc **35/37 số tiền dài đúng tuyệt đối**, nhưng cột
`Mã số` hai chữ số **sai 3/14 (21%)** — `01`→`0`, `02`→`022`, `11`→`1`. Token
dài có khuôn nhóm-3 tự ràng buộc nó; token trần không có gì để tự sửa.

Đây là lỗi **chữ**, không phải lỗi **cấu trúc**, nên nằm ngoài bậc 2 (§10). Ghi
ở đây vì nó có hệ quả trực tiếp lên cổng B: cổng phải phân biệt được "đỏ vì bậc
2 dựng sai cột" với "đỏ vì tầng đọc đọc sai chữ".

## 3. Ranh giới

Bậc 2 là **một hàm thuần** trong `backend/src/ocr/bang.py`:

```
list[OcrWord]  →  list[list[str]]
```

Không đọc tệp, không gọi mạng, không biết gì về PDF. Module lá, chỉ phụ thuộc
`engine.OcrWord`.

**Vì sao nó nhỏ hơn vẻ ngoài:** `src/rag/pdf_table.py` (B4, 222 dòng) nhận đầu
vào là lưới `list[list]` — `pdfplumber` mới là thứ dò bảng, `pdf_table.py` chỉ
hậu xử lý. Toàn bộ chuỗi sau đó **không quan tâm lưới đến từ đâu**:

```
split_header_body → column_names → row_to_text → checksum_gap
```

Bậc 2 **không sửa một dòng nào** trong đó, chỉ nối vào đầu vào của nó. Hệ quả:
hàng bảng đọc-từ-ảnh và hàng bảng đọc-từ-vector đi **cùng một đường** sau điểm
đó — không có đường code thứ hai phải giữ đồng bộ, đúng bài học `xlsx_header.py`
(hai predicate gần giống hệt đã gây một hồi quy thật).

## 4. Thuật toán — ba bước

**Bước 1: gom dòng.** Dùng `line_id` Tesseract đã trả sẵn (bậc 1 đã lưu vào
artifact ở trường `"g"`). **Không** tự gom lại theo toạ độ y: tesseract gom tốt
hơn, và spec bậc 1 đã ghi bài học "đừng sắp xếp lại thứ tự đọc" — sự khác biệt
thứ tự đọc từng bị nhầm thành chất lượng OCR kém.

**Bước 2: tìm mốc cột bằng cụm căn lề.** Với mỗi cột ứng viên, cụm **cả hai
mép** và lấy mép nào chụm hơn.

Cố ý **không** dùng quy tắc "số căn phải, chữ căn trái" dù §2.2 cho thấy nó
đúng trên tài liệu này: đó là quy ước kế toán Việt/Âu, và biểu mẫu khác có thể
căn khác. Để dữ liệu tự nói mép nào chụm hơn thì hết phụ thuộc quy ước — kể cả
`1.234.567` với `1,234,567`.

**Bước 3: gán ô.** Mỗi từ vào cột gần nhất theo mép của nó; các từ cùng dòng
cùng cột nối lại bằng dấu cách.

**Suy biến tự nhiên, KHÔNG có bộ dò bảng.** Trang văn xuôi không có cụm căn lề
nào đủ mạnh ⇒ ra **một cột** ⇒ mỗi dòng thành một ô ⇒ đúng hệt hành vi hôm nay.
Không có bộ dò thì không có gì để bắn nhầm — tránh luôn lớp lỗi "cổng trông như
đang gác nhưng không đo gì" mà riêng Kế hoạch 1 đếm được tám lần.

## 5. Tham số phải KHÔNG THỨ NGUYÊN

Dung sai tính bằng **pixel là sai** — nó vỡ khi đổi DPI hoặc cỡ chữ, tức là vỡ
đúng lúc đổi sang định dạng khác. Mọi tham số phải chuẩn hoá:

| tham số | đơn vị |
|---|---|
| dung sai cụm mép | phần của **bề rộng ký tự trung vị** (suy từ bbox chia số ký tự — Tesseract cho sẵn) |
| ngưỡng "bao nhiêu token thành một cột" | phần của **số dòng trong vùng**, không phải số tuyệt đối |

**Không con số nào trong bảng trên được chốt trong spec này.** Chúng phải đo
trên 229 trang ở §7 rồi mới chốt, theo đúng lệ dự án: không nhận hằng số từ
trên trời.

## 6. Vì sao KHÔNG có cơ chế adaptive kiểu chọn chiến lược

Chuẩn hoá không thứ nguyên ở §5 **là** phần adaptive đáng làm — nó sửa một lỗi
thiết kế thật. Ba loại còn lại bị loại có lý do:

- **Chạy nhiều chiến lược rồi chấm điểm chọn cái tốt nhất** — lỗi đặc trưng là
  **bộ chấm điểm trở thành một cổng không ai đo**: kết quả xấu thì không biết do
  chiến lược sai hay do bộ chấm sai. Dự án đã mất thời gian đúng chỗ này. Giới
  hạn của thứ được chấp nhận là `merge_table_rows` của B4: gộp hai chế độ và
  **phát cảnh báo khi chúng bất đồng**, chứ không lặng lẽ chọn.
- **Ngưỡng riêng theo nhóm định dạng** — cần thêm một bộ phân loại, tức thêm một
  cổng có thể sai cả hai chiều. Quyết: **một bộ tham số dùng chung cho cả 229
  trang**; định dạng nào tụt thì **ghi lại làm giới hạn đã biết**, không đẻ nhánh.
- **Học từ phản hồi** — không có dữ liệu huấn luyện, và nó giết tính tất định,
  mà tất định chính là toàn bộ giá trị của cổng.

**Nguyên tắc thứ tự:** dựng cổng đa-định-dạng **trước**, rồi để số liệu nói cần
thêm bao nhiêu cơ chế. Thêm cơ chế trước khi đo là cách dự án này đã nhiều lần
tự làm khổ mình.

## 7. Cổng nghiệm thu — hai tầng, thiếu cái nào cũng không đủ

### Cổng A — tự nuôi, đa định dạng, chạy trong test suite

Lấy trang bảng **vector** → rasterise → vứt lớp text → chạy bậc 2 trên ảnh → so
lưới thu được với lưới `pdfplumber` bóc từ **chính trang đó**.

- đáp án **tự sinh**, không gõ tay ô nào
- phủ **nhiều định dạng** (§2.3), đúng chỗ yếu của việc hiệu chỉnh trên một tài liệu
- chứng minh đường này **còn sống** ở mỗi lượt chạy test

**Thước:** tỷ lệ ô của lưới đáp án xuất hiện đúng **ô cùng chỉ số (hàng, cột)**
trong lưới bậc 2 dựng ra. So *vị trí*, không so *nội dung* — chữ sai là việc của
tầng đọc (§2.4), còn cổng này chỉ hỏi ô có nằm đúng chỗ không. Ô nào Tesseract
đọc lệch chữ thì so theo tập từ, không so nguyên văn, để lỗi đọc không bị tính
thành lỗi cấu trúc.

**Ngưỡng đạt chưa chốt ở đây**, cùng lý do với §5: phải đo trên 229 trang rồi
mới suy, không nhận số từ trên trời. Cách suy đã dùng ở bậc 1 và giữ nguyên:
làm tròn xuống hai chữ số của (giá trị nhỏ nhất quan sát được − biên), và biên
chỉ để chịu sai khác máy/phiên bản, **không** để che một hồi quy thật.

Đo *độ phủ định dạng*. Trong suite chạy một tập con đủ nhanh cho suite đơn vị;
tập đầy đủ chạy tay khi hiệu chỉnh. Plan chốt con số cụ thể.

### Cổng B — scan thật, dùng lại cổng số học đã có

Chạy bậc 2 trên trang 12–18 BCTC, kiểm bằng
`backend/tests/fixtures/ocr_bang_that/kiem_so_hoc.py` (đã duyệt 2026-09-06,
85/85 ràng buộc, đã thử phá bốn kiểu).

**Không cần đặt tên cột.** Với mỗi hàng trong đáp án, chỉ hỏi: ba giá trị của nó
có rơi vào **cùng một hàng** đầu ra, đúng thứ tự tương đối không. Dựng sai cột là
gãy ngay, mà không phải suy diễn cột nào là cột nào — tránh được một tầng suy
diễn có thể tự nó sai.

Đo *đúng trên scan thật*.

### Phân biệt hai loại đỏ

Vì §2.4, cổng B có thể đỏ vì **tầng đọc** đọc sai chữ chứ không phải bậc 2 dựng
sai cột. Cổng phải nói rõ được điều đó, nếu không nó sẽ bị tắt sau vài lần đỏ
oan — và một cổng bị tắt thì bằng không.

## 8. Luồng vào `parse.py`

`read_page` trả về vùng có thể mang `kind="table"`. Nhánh OCR trong `parse_pdf`
xử theo kiểu vùng:

| kiểu vùng | xử lý |
|---|---|
| `text` | dòng phẳng, **y hệt hôm nay** |
| `table` | lưới → `split_header_body` → `column_names` → `row_to_text`; mỗi hàng một block `atomic=True`, `source_kind="ocr"` |

Giống hệt nhánh bảng vector của B4 sau điểm đó.

`ARTIFACT_VERSION` tăng **2 → 3** (vùng mang thêm lưới). Đệm cũ tự hết hiệu lực
qua dấu vân tay cấu hình — cơ chế đã có từ bậc 1, không phải dựng mới.

## 9. Hỏng thì to tiếng, nhưng không làm vỡ lượt nạp

Bậc 2 **không bao giờ ném lỗi vào lượt nạp**. Hỏng thì lùi về dòng phẳng như hôm
nay, kèm **cảnh báo có tên** qua `IngestReport` — hạ tầng đã có từ Kế hoạch 1,
không phát minh cơ chế mới. Tệ nhất là **mất cấu trúc, không mất nội dung**.

## 10. Ngoài phạm vi

- **Sửa chữ trong ô.** Bậc 2 chỉ trả lời "ô nào thuộc cột/hàng nào". Chữ sai là
  việc của tầng đọc (bậc 1) và làm giàu (bậc 3, §9.1 spec cha). Giữ mỗi bậc một
  trách nhiệm.
- **Trang lai** (khung bảng vector + chữ ảnh). Đã đo 2026-09-05: bản scan thuần
  không bao giờ chạm nhánh này.
- **Bảng xoay ngang; bảng vắt nhiều trang.**
- **Ô có nội dung xuống dòng** — cách gom theo dòng hiện tại sẽ tách thành hai
  hàng.

## 11. Giới hạn đã biết, nói thẳng

- ⚠️ **Bố cục văn xuôi nhiều cột** kiểu tạp chí, xét về hình học, trông y hệt
  một bảng hai cột. Đây là **rủi ro dương tính giả có thật**, sinh ra từ quyết
  định không dựng bộ dò (§4). Van an toàn duy nhất là ngưỡng ở §5, và nó sẽ được
  đo trên 229 trang. Corpus hiện tại là tài liệu nghiệp vụ nên rủi ro thấp,
  nhưng nó **không bằng không**, và ai nạp tài liệu dạng tạp chí phải biết.
- **Cổng A dùng ảnh rasterise sạch**, giống hệt giới hạn của cổng tự nuôi bậc 1:
  chứng minh "còn sống và đại khái đúng", **không** chứng minh "chịu được scan
  đời thật". Cổng B mới chạm scan thật, nhưng chỉ **một** tài liệu, phẳng và
  sạch.
- **Chưa có tài liệu nghiêng, nhiễu, hay photo nhiều đời** trong cả hai cổng.

## 12. Thứ tự thực thi

1. `bang.py` — hàm thuần, test đơn vị trên lưới dựng tay
2. Cổng A trên 229 trang — **đo trước, chốt tham số §5 sau**
3. Cổng B trên trang 12–18, kèm cơ chế phân biệt hai loại đỏ
4. Nối vào `parse.py`, tăng `ARTIFACT_VERSION`
5. Nghiệm thu lại toàn corpus: đường không-OCR phải **byte-identical**

Bước 5 là bất biến an toàn đã dùng ở B4 và bậc 1, giữ nguyên: bậc 2 chỉ được
đụng tới trang đi qua OCR, mọi trang khác phải ra kết quả không đổi một bit.
