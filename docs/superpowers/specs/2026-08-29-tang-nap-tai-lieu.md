# Tầng nạp tài liệu — bốn lỗi mất mát âm thầm

**Ngày**: 2026-08-29. **Nhánh**: `main`. **Trạng thái**: thiết kế đã duyệt, chưa viết code.

## 1. Đề bài

Bốn khiếm khuyết tìm ra bằng phép đo trong đợt khảo sát 2026-08-28/29. Không cái
nào do đọc code mà ra; mỗi cái đều có số.

| # | lỗi | bằng chứng | hậu quả |
|---|---|---|---|
| 1 | `.doc`, `.xlsm`, `.pptx` bị bỏ qua **im lặng** | `_ingest_file` trả `{'ingested': 0, 'skipped': 0, 'chunks': 0}` | **mất trắng cả tài liệu**, không rơi vào bộ đếm nào |
| 2 | Excel lấy hàng đầu làm tiêu đề | **0/81 sheet** đúng trên sổ kế toán thật; 23 sheet chứng minh được header bị tụt xuống hàng dữ liệu | mọi con số mang nhãn cột sai |
| 3 | Word không có style Heading → breadcrumb thành đường dẫn tệp | `b09-dn.docx`: 377/377 block `heading_level=None`; 74/74 chunk có `section_path` bằng đường dẫn tệp | vô hiệu hoá P3b; nhúng đường dẫn Windows vào vector |
| 4 | PDF gắn số sang hàng bên cạnh | **70/195 mã** trong bảng thuế có mức sai nằm kề; 3/198 mã không có đáp án đúng trong chunk | ~36% câu hỏi tra bảng bị gài bẫy |

### 1.1 Cơ chế lỗi 3, đã truy tới dòng

```
chunking.py:52   doc_title = next((b["text"] for b in blocks if b["heading_level"]), source_file)
chunking.py:61   crumb     = " › ".join(t for _, t in path_stack) or doc_title
```

Không block nào có heading → `doc_title` lùi về `source_file` → `crumb` lùi về
`doc_title` → `index_text()` nối nó vào text đem đi embed. Đường dẫn tệp được
nhúng vào vector của **mọi** chunk trong tài liệu, **giống hệt nhau**, nên nó vừa
vô nghĩa vừa **làm giảm khả năng phân biệt giữa chính các chunk đó**.

### 1.2 Cơ chế lỗi 4

`pypdf.extract_text()` xuất mức thuế **sau** phần mô tả của hàng mình nhưng
**trước** mã của hàng kế. Nối dòng thành đoạn cho ra `10-35 35 25.17`, đọc như
thể `10-35` thuộc `25.17`. Hàng ngắn (`41 25.24 Amiăng. 5-30`) lại gắn **đúng**.
Bảng trộn hai kiểu.

Vì sao sống lâu: 125/195 số kề bên **tình cờ đúng** (nhiều hàng liên tiếp cùng
mức), nên dò ngẫu nhiên vài mã sẽ thấy ổn.

## 2. Cột sống: bốn lỗi là một lỗi

| lỗi | mất gì | `ingest` báo gì |
|---|---|---|
| 1 | cả tệp | `ingested: 0` — trông như không có việc |
| 2 | ngữ nghĩa cột | có chunk, số đếm bình thường |
| 3 | phân cấp tài liệu | có chunk, số đếm bình thường |
| 4 | ràng buộc hàng | có chunk, số đếm bình thường |

Cả bốn **mất thông tin rồi báo thành công**. Lý do chúng sống sót lâu là chung
một cái: `ingest` báo **số lượng, không báo độ trung thực**. Số đếm không phân
biệt nổi 50 chunk tốt với 50 chunk rác.

Docstring của `IngestError` đã tuyên bố đúng nguyên tắc — *"Hỏng lớn tiếng còn
hơn thiếu âm thầm"* — nhưng chỉ bịt nhánh "đuôi quen mà 0 chunk". Nhánh "đuôi lạ"
vẫn im, và ba lỗi kia **có** sinh chunk nên không nhánh nào kêu.

## 3. Ba phương án đã cân nhắc

| | cách | phán quyết |
|---|---|---|
| 1 | Vá bốn parser tại chỗ | Rẻ nhất, nhưng để nguyên gốc rễ. Lỗi thứ năm sẽ lại đến trong im lặng. **Loại.** |
| 2 | **Ba tầng: to tiếng + sửa bốn lỗi + bộ nghiệm thu** | Nhiều việc hơn, đóng luôn cái khiến chúng tái phát. **Chọn.** |
| 3 | Thay cả tầng parser bằng Docling / unstructured | Đã **đo**: `pdfplumber` giải xong ca PDF mà không cần torch (8/8 mã đúng). Và Docling **không** chữa lỗi 2, 3 — đó là logic của chúng ta chứ không phải của parser. Đổi lớn, không giải đúng bệnh. **Loại.** |

## 4. Tầng A — không bao giờ im lặng

Mỗi tệp đi vào phải ra ở **đúng một trong ba trạng thái**:

| trạng thái | nghĩa |
|---|---|
| `ingested` | đã sinh chunk và ghi DB |
| `unchanged` | `content_hash` trùng, bỏ qua có chủ ý |
| `rejected` | **kèm lý do**, được gọi tên trong báo cáo |

Không có trạng thái thứ tư. `ingest_path()` trả về danh sách `rejected`; `main()`
in ra từng tệp kèm lý do và **thoát với mã khác 0**.

Nguyên nhân từ chối: **định dạng tài liệu** mà không nạp được (định dạng cũ không
có bộ chuyển đổi, PDF không lớp text, parse ra rỗng).

**Không phải mọi đuôi lạ đều là từ chối.** Phải tách hai loại, nếu không một tệp
`.gitkeep` trong thư mục sẽ làm tiến trình thoát khác 0:

| loại | ví dụ | xử lý |
|---|---|---|
| **là tài liệu**, nhưng chưa nạp được | `.doc`, `.pptx`, `.rtf`, `.odt`, `.ppt`, `.xls` | **`rejected`** — gọi tên, thoát khác 0 |
| **không phải tài liệu** | `.txt`, `.py`, `.png`, `.gitkeep` | bỏ qua im lặng như hiện tại — **đúng** |

Ranh giới là một **danh sách đuôi được coi là tài liệu**, tách khỏi danh sách đuôi
**nạp được**. Đây chính là chỗ hôm nay chỉ có một danh sách, nên `.doc` và `.pptx`
rơi vào cùng rọ với `.gitkeep`.

Test `test_tep_duoi_la_khong_nem_va_khong_dem_la_skipped` (2026-08-19) đang khoá
hành vi cũ với lý lẽ *"tệp đuôi lạ chưa bao giờ là tài liệu để mà bỏ"* — lý lẽ đó
**đúng cho `.txt`** và phải giữ. Test cần **viết lại có chủ ý** để nói rõ nó nói về
loại thứ hai, kèm một test anh em cho loại thứ nhất. Đây không phải "sửa test cho
xanh".

**Cảnh báo là chuyện khác, không phải trạng thái thứ tư.** Ba trạng thái trên nói
về **tệp**. Còn những thứ như "sheet này không dò được hàng tiêu đề" (mục 5.2) hay
"bảng này thiếu 3 hàng theo checksum" (mục 5.4) là mối lo ở mức **sheet/bảng**:
tệp vẫn được nạp, nhưng chỗ đáng ngờ phải nằm trong một **danh sách cảnh báo
riêng**, cũng được in ra và cũng gọi tên cụ thể. Nuốt cảnh báo chính là lỗi mà cả
spec này đi đóng.

Tầng này **không cần quyết định sản phẩm nào** và đang che ba lỗi còn lại, nên
làm trước.

## 5. Tầng B — sửa bốn lỗi, cộng OCR

### 5.1 Phủ định dạng

| định dạng | cách |
|---|---|
| `.xlsm`, `.xltx` | thêm vào `_EXT`; openpyxl đọc sẵn, gần như miễn phí |
| `.pptx` | parser mới qua `python-pptx`: mỗi slide một block, tiêu đề slide làm heading, bảng ngăn bằng dấu sổ đứng như docx, kèm ghi chú thuyết trình |
| `.doc`, `.xls`, `.ppt` | chuyển đổi trước bằng LibreOffice `soffice --headless --convert-to`, nhớ đệm bản đã chuyển theo `content_hash`; không có LibreOffice thì rơi xuống Tầng A |

Quyết định của chủ dự án 2026-08-29: **cài LibreOffice**. Lý do: giải một lần cả
ba định dạng cũ, chạy được trên server, không cần phiên desktop. Đã loại phương
án điều khiển MS Word qua COM (chỉ Windows, cần desktop, dễ vỡ).

#### 5.1.1 Thực tế cài đặt 2026-08-30 — ba lần hỏng trước khi được

| lần | cách | kết quả |
|---|---|---|
| 1 | `winget install` | **treo 27 phút** chờ hộp thoại UAC mà phiên không tương tác không trả lời được; CPU chỉ 1,0 giây — nó không hề tải gì |
| 2 | `scoop install` | tải được 33/357 MB rồi đứt (`unexpected EOF`), **báo mã thoát 0** |
| 3 | `curl` nối tiếp từ mirror chính thức | 116/357 MB ở **~16 KB/s**, ước tính còn 4 giờ; băm không khớp |
| 4 | `curl` từ `ftp.acc.umu.se` | **25,9 MB/s**, xong trong ~10 giây, **băm khớp** `4aa6c6e1…` |

`download.documentfoundation.org` đo được **13 KB/s**, mirror Thuỵ Điển **1675 KB/s**
ở phép thử và 25,9 MB/s khi tải thật — chênh hơn **hai bậc độ lớn**. Ai cài lại
nên trỏ thẳng mirror, đừng dùng URL chuyển hướng chính thức.

**Bung MSI báo lỗi 1603 nhưng thật ra THÀNH CÔNG**: scoop in `Failed to extract
files`, log msi rỗng, `scoop list` ghi `Install failed` — nhưng cây tệp có đủ
**19.417 tệp, 1,6 GB**, và `soffice.exe` chạy được. Đây là **mã trạng thái nói dối
lần thứ ba** trong cùng một đợt cài. Bài học áp thẳng vào Tầng A: **kiểm bằng sản
phẩm, không kiểm bằng mã thoát.**

Hệ quả cần xử lý: scoop không tạo junction `current` lẫn shim vì nó tưởng đã hỏng.
Đã tạo junction bằng tay. Đường dẫn dùng:

    C:\Users\ADMIN\scoop\apps\libreoffice\current\LibreOffice\program\soffice.exe

**Nợ triển khai**: đường dẫn này và `TESSDATA_PREFIX` (mục 5.5.2) đều là đường dẫn
máy cá nhân. Cả hai **phải khai qua biến môi trường, không được viết cứng**, và
máy khác sẽ không có sẵn.

#### 5.1.2 Nghiệm thu đầu-cuối đã chạy

Không dừng ở "đã cài xong". Chạy trọn chuỗi trên tệp thật `quyche_taichinh.doc`:

    .doc → soffice --headless --convert-to docx → parse_docx() → 51 block, 5.926 ký tự

Nội dung ra đúng: `QUY CHẾ TÀI CHÍNH CÔNG TY`, `CHƯƠNG I:`, `Điều 1:`, `Điều 2:`…

Thời gian: **17,5 giây lần đầu** (gồm dựng profile người dùng), **5,2 giây** các
lần sau. Nên bước chuyển đổi phải **giữ lại profile** giữa các lần gọi, nếu không
mỗi tệp phải trả giá lần đầu.

Và chính tệp này lập tức phơi bày lỗi 3: cả 51 block đều `heading_level=None`
trong khi tài liệu có rành mạch `CHƯƠNG I` / `Điều 1` / `Điều 2`. Nó là fixture
sẵn có cho mục 5.3.

### 5.2 Excel dò hàng tiêu đề

Bản sửa **không được là một cú đoán im lặng khác** — đó đúng lớp lỗi đang đóng.

- quét một số hàng đầu, chấm điểm từng hàng: ô ngắn, không phải số, liền mạch, và
  các hàng **bên dưới** mang dáng dữ liệu
- **số hàng quét và ngưỡng điểm KHÔNG được chọn theo cảm tính.** Cả hai phải hiệu
  chỉnh trên 23 sheet đã chứng minh được đáp án (hàng chứa "STT") của sổ kế toán
  thật, và giá trị chốt lại phải kèm số đo. Một hằng số rút từ không khí là đúng
  thứ đã sinh ra lỗi này
- **header hai tầng**: hàng trên có ô gộp trải ngang thì ghép nhãn `cha · con`
- **nạp ô gộp** — bắt buộc bỏ `read_only=True`, vì chế độ đó **không** nạp
  `merged_cells`. Đã thử với chính tệp 12,5 MB của chủ dự án: mở được, thời gian
  chấp nhận được
- **có độ tin cậy**: sheet chấm dưới ngưỡng thì **báo ra** qua Tầng A, không nuốt

### 5.3 Word suy phân cấp từ chữ

- ưu tiên style Heading như hiện tại
- tài liệu **không có heading nào** thì suy từ mẫu chữ hành chính Việt: `PHẦN`,
  `CHƯƠNG`, `MỤC`, `Điều N`, `I.`, `1.`, `1.1.`, `A.`; có thể đối chiếu thêm tín
  hiệu định dạng (đậm, in hoa, căn giữa) mà python-docx đọc được
- `parse_pdf` **đã** dò "Chương/Điều" — **tách ra dùng chung**, không viết lần hai
- sửa `chunking.py:52`: không có phân cấp thì `section_path` phải **rỗng**, tuyệt
  đối không phải `source_file`

### 5.4 PDF bóc bảng

- tách bảng khỏi văn xuôi, xử lý riêng
- ghép hai chế độ `pdfplumber` rồi đối chiếu:

| chế độ | hàng lấy được | mô tả | mức |
|---|---|---|---|
| mặc định | 194/210 — **mất 14 hàng** vắt qua ngắt trang | nguyên vẹn | đúng |
| `horizontal_strategy` đặt là `text` | **210/210** | **55 hàng rỗng mô tả** | đúng, 12 hàng thiếu |

  Chưa chế độ nào đủ một mình — đó là lý do phải ghép, không phải chọn.
- mỗi hàng bảng thành **một đơn vị tự đủ nghĩa** (tiêu đề kèm từng ô), để ranh
  giới chunk **không thể** tách con số khỏi mã của nó
- tài liệu có cột đếm liên tục thì dùng làm checksum, thiếu hàng thì báo qua Tầng A

### 5.5 OCR cho tài liệu không có lớp text

Chủ dự án yêu cầu đưa OCR vào đợt này (2026-08-29), sau khi mục 8 ghi rằng hôm nay
chưa tài liệu nào cần tới nó.

**Kích hoạt**: trang PDF (hoặc cả tệp) **không có lớp text**. Hiện `IngestError` ném
lỗi ở đúng ca này; đổi thành: **thử OCR trước, hết cách mới từ chối**.

**Engine**: Tesseract kèm `vie` và `eng`, gọi qua `pytesseract`. Bảng so đã đo
2026-08-29:

| phương án | phụ thuộc thêm | phán quyết |
|---|---|---|
| EasyOCR | 12 gói, **đè `torch` 2.11.0+cu128 lên 2.13.0** | **Loại** — gần như chắc giết reranker GPU, đúng lớp lỗi đã làm reranker chết âm thầm 6 tuần |
| RapidOCR (onnxruntime) | 7 gói, không đụng torch | An toàn nhưng tiếng Việt yếu |
| **Tesseract + `pytesseract`** | **1 gói pip** + 1 binary | **Chọn** — không đụng gì trong cây phụ thuộc; đi cùng binary LibreOffice đã đồng ý |

**Bộ dựng ảnh**: `pypdfium2` (đã có sẵn, đi kèm pdfplumber).

#### 5.5.2 Cấu hình đã đo, không phải đoán

Cài đặt 2026-08-30: Tesseract 5.4.0 qua winget; `vie.traineddata` lấy từ
`tessdata_best` (12,4 MB). **Ghi vào `Program Files` cần quyền admin nên thất bại**
— gói ngôn ngữ để ở `C:/Users/ADMIN/.tessdata`, trỏ bằng biến `TESSDATA_PREFIX`.
Chỗ này phải khai lại khi triển khai máy khác.

**Chế độ phân vùng trang (PSM): bắt buộc đặt 6.** Đo trên 3 trang bảng, đối chiếu
với lớp text sẵn có, thước là recall theo TỪ (không phạt thứ tự đọc):

| chế độ | trang 14 | trang 16 | trang 18 | TB |
|---|---|---|---|---|
| **PSM 3 (mặc định)** | 0,810 | 0,642 | **0,256** | 0,569 |
| PSM 4 | 0,693 | 0,802 | 0,576 | 0,690 |
| **PSM 6** | **0,851** | **0,862** | **0,882** | **0,865** |
| PSM 11 | 0,822 | 0,713 | 0,800 | 0,778 |
| PSM 12 | 0,798 | 0,697 | 0,789 | 0,761 |

Điều đáng sợ không phải PSM 3 kém, mà là nó **hỏng không đều giữa các trang** —
0,26 ở trang này, 0,81 ở trang kia, **không báo gì**. Dùng mặc định thì một phần
corpus scan sẽ biến mất âm thầm: đúng lớp lỗi cả spec này đi đóng.

**Độ phân giải: chốt 200 DPI.** Đo lại dưới PSM 6:

| DPI | tốc độ | recall TB |
|---|---|---|
| 150 | 2,2 s/trang | 0,840 |
| **200** | **2,5 s/trang** | **0,865** |
| 300 | 4,5 s/trang | 0,847 |
| 400 | 5,9 s/trang | 0,866 |

400 DPI ngang 200 DPI về chất lượng nhưng chậm 2,4 lần.

#### 5.5.3 Hai bẫy đo lường đã dính, ghi lại để không lặp

- **Thước ký tự cho kết quả SAI.** `SequenceMatcher` trên toàn chuỗi cho 0,46 và
  suýt khiến tôi kết luận "OCR tiếng Việt kém". Thật ra chữ nhận gần đúng hết;
  điểm thấp do **thứ tự đọc khác** (Tesseract xếp cột khác pdfplumber) và **đường
  kẻ bảng bị đọc thành ký tự**, nuốt chữ cái đầu dòng (`ừ xi` thay vì `từ xỉ`,
  `ltệt Nam` thay vì `Việt Nam`). Phải dùng thước **không phạt thứ tự**.
- **So DPI dưới PSM sai.** Lần đầu tôi so DPI khi còn dùng PSM 3 và kết luận "300
  DPI tệ hơn 200". Đo lại dưới PSM 6 thì kết luận đó không đứng vững. Đổi một
  tham số thì mọi tham số đã so trước đó phải so lại.

**Ngưỡng đạt của cổng**: chưa chốt. `0,865` là số **đường cơ sở**, không phải mục
tiêu, và nó đo với đáp án là lớp text của pdfplumber — bản thân lớp đó cũng có
lỗi thứ tự bảng (mục 1.2), nên một phần "sai" có thể là lỗi của đáp án chứ không
phải của OCR. Ngưỡng chốt sau, kèm số.

**Phải to tiếng**: OCR ra text gần rỗng thì **từ chối**, không được nạp rác vào
corpus rồi báo thành công.

**Ghi xuất xứ**: chunk sinh ra từ OCR phải mang cờ đánh dấu. Độ tin cậy của chúng
thấp hơn, và về sau chính cờ này là chiều "có đáng tin không" mà việc chống
injection gián tiếp (mục 10) sẽ cần.

#### 5.5.1 OCR KHÔNG chữa lỗi 4

Nói rõ để không ai nhầm: Tesseract trả về **chữ**, không trả về **ô**. Một trang
bảng đi qua OCR vẫn dính nguyên bài toán gắn số sang hàng bên cạnh, thậm chí nặng
hơn vì mất cả đường kẻ. OCR và cấu trúc bảng là **hai bài toán rời**; mục 5.4 vẫn
phải làm đầy đủ.

## 6. Tầng C — bộ nghiệm thu

| bộ | đáp án lấy từ đâu | quy mô |
|---|---|---|
| 100 hoá đơn PDF | **số học tự kiểm**: số lượng nhân đơn giá bằng thành tiền; thành tiền cộng thuế bằng tổng; tổng các dòng bằng SUMMARY | 855 hàng, **0 ô gán tay** |
| bảng thuế XNK | STT liên tục 1..210 (checksum) + 8 mức đã đối chiếu tay | 210 hàng |
| sổ kế toán `.xlsm` | 23 sheet chứng minh được: header phải là hàng chứa "STT" | 81 sheet |
| biểu mẫu BCTC `.docx` | `section_path` phải chứa đánh số của chính tài liệu, không phải đường dẫn | 10 tệp |
| **OCR** | **corpus tự sinh đáp án**: rasterise trang **đã có lớp text**, vứt lớp text, OCR ảnh rồi so ngược với bản gốc | tuỳ chọn số trang; 1 trang đã cho 2.613 ký tự |

Mỗi cổng kèm **phép thử phá**: gỡ bản sửa ra thì cổng phải đỏ. Cổng không biết đỏ
là cổng không đo gì — lớp lỗi này đã xuất hiện nhiều lần trong dự án.

### 6.1 Bộ test hai tầng

- **Tầng 1 — fixture trong repo**, nhỏ, tự dựng, đáp án chắc 100%, chạy mọi lượt
  test. Đây là cổng chống trôi: rẻ, tất định, không phụ thuộc mạng.
- **Tầng 2 — tài liệu thật**, để ngoài repo tại `tmp-docs/` (đã gitignore), chạy
  tay hoặc theo lịch. Đây là nơi tìm **lỗi chưa biết mình có**.

Lệnh test mặc định phải kèm cờ loại trừ:

```
pytest -m "not integration and not live"
```

### 6.2 Vì sao cổng OCR quan trọng hơn vẻ ngoài của nó

Hôm nay **683/683** trang PDF luật và **100/100** hoá đơn đều có lớp text, tức là
**không tài liệu nào chạy qua đường OCR**. Một thành phần không ai chạy qua thì
chết âm thầm — reranker đã chết đúng như vậy 6 tuần vì thiếu một dependency mà
bốn lớp test đều che.

Cổng "rasterise rồi OCR ngược" giải đúng việc đó: nó **luôn có dữ liệu để chạy**,
đáp án lấy từ chính corpus, không cần gán tay ô nào, và nó chứng minh đường OCR
còn **sống** ở mỗi lượt chạy test.

Giới hạn phải nói rõ: ảnh rasterise **sạch hơn** bản scan thật — không nghiêng,
không nhiễu, không dấu mộc, không chữ ký đè. Nên cổng này chứng minh "còn sống và
đại khái đúng", **không** chứng minh "chịu được scan đời thật". Ca scan thật vẫn
cần, và vẫn nằm ở mục 8.

## 7. Kho tài liệu test đã dựng

Chia theo đúng hai tầng ở mục 6.1: **fixture tự dựng vào repo, tài liệu thật ở
lại `tmp-docs/`** (đã gitignore). Không commit tệp thật nào — chúng nặng, là văn
bản của bên thứ ba, và tầng 1 không cần chúng để chống trôi.

| tệp | quy mô | thử được |
|---|---|---|
| 100 tệp `invoice_*.pdf` | 855 hàng bảng, **0 tệp thiếu lớp text** | nhiều bảng trên một trang, tự kiểm số học |
| `bieumau_bctc_hopnhat.pdf` | 55 trang, 45 trang bảng, 759 hàng | header gộp dọc, hàng đánh số cột, phân cấp A→I→1 |
| `ssc_bieumau.pdf` | 8 trang, 53 hàng, 6 cột | ô nhiều dòng, bảng nhiều trang |
| 10 biểu mẫu BCTC `.docx` | `b09-dn` có **55 bảng**, 377 block | bảng docx thật và lỗi thiếu Heading |
| sổ kế toán `.xlsm` | **84 sheet** (81 có dữ liệu) | header nhiều tầng, ô gộp, sheet rỗng |
| `quyche_taichinh.doc` | 2 trang | định dạng cũ |
| `USA_Employee_Handbook...pdf` | 34 trang | văn xuôi tiếng Anh |
| `bctc_ogop.xlsx`, `quyche_ogop.docx` | nhỏ | fixture tự dựng, đáp án chắc |

**Còn thiếu**: `.pptx` thật. Không chặn việc gì — parser vẫn dựng được và fixture
tự dựng đủ cho cổng chống trôi; chỉ thiếu ca phát hiện lỗi chưa biết.

## 8. Giới hạn đã biết và giả thuyết đã bị bác

Ghi lại để lần sau không đi lại đường cụt.

- **Ước lượng đầu tiên của tôi SAI**: tôi nói "đáp án đúng chưa bao giờ có trong
  ngữ cảnh". Đo đủ 198 mã thì chỉ **3/198 (1,5%)** vắng mặt hoàn toàn — tôi đã
  khái quát từ 3 mẫu, mà ba mẫu đó lại đúng là ba ca cực đoan. Bệnh thật là **gắn
  sai** (70/195), không phải thiếu thông tin.
- **Phép đo 35,9% bị vòng tròn một phần**: đáp án dùng chính output pdfplumber.
  Dùng để so cũ-với-mới thì được (có 8 mã neo đối chiếu tay), nhưng **không dùng
  được để nghiệm thu bộ bóc tách mới**. Tầng C phải lấy đáp án từ nguồn độc lập —
  đó là lý do bộ hoá đơn (tự kiểm số học) quan trọng hơn bảng thuế.
- **OCR không chữa lỗi nào đang có**: 683/683 trang PDF luật đã có lớp text, 0
  trang rỗng; 100/100 hoá đơn cũng vậy. Bệnh hiện tại là **cấu trúc bảng**, không
  phải nhận dạng chữ. Chủ dự án vẫn quyết đưa OCR vào (mục 5.5) để đón tài liệu
  scan sắp tới — đó là quyết định **chuẩn bị trước**, không phải bản sửa cho lỗi
  đang đo được. Nhận định này giữ nguyên, không bị quyết định kia phủ nhận.
- **Chưa đo được chất lượng OCR tiếng Việt**: mới đo xong *chi phí phụ thuộc* của
  ba engine, chưa đo *độ chính xác* vì chưa cài Tesseract. Con số đầu tiên phải
  lấy từ cổng ở mục 6.1 rồi mới chốt ngưỡng — không đặt ngưỡng trước.
- **Docling chưa từng được thử** — `pdfplumber` đã qua ngưỡng nên nó không còn gì
  phải chứng minh **cho tài liệu hiện có**. Vẫn có thể cần cho tài liệu scan hoặc
  ảnh sau này. Không kết luận là "Docling kém".
- **Cột STT là may mắn riêng của bảng thuế**. Báo cáo tài chính không có gì tương
  đương, nên phương pháp checksum không tổng quát hoá được.
- **Bảng trong slide có thể là ảnh** — khi đó là ca OCR chứ không phải ca bóc
  bảng. Parser `.pptx` chỉ đọc được bảng thật.

## 9. Thứ tự làm

```
A  →  B2  →  B3  →  B4  →  B5 (OCR)
```

Tầng A trước vì rẻ nhất, không cần quyết định sản phẩm, và đang che ba lỗi kia.
Rồi B2 (0/81, mọi con số sai nhãn), B3 (lớp tài liệu phổ biến nhất), B4 (bài toán
ban đầu, khoảng 36%).

**Toàn bộ B1 đi kèm Tầng A**, không tách riêng: `.xlsm`/`.xltx`, parser `.pptx`,
và cầu chuyển đổi LibreOffice đều là hai mặt của cùng một câu hỏi *"tệp này ra ở
trạng thái nào"*. Làm rời sẽ phải sửa đúng chỗ đó hai lần.

**B5 (OCR) xếp cuối** dù được yêu cầu rõ, vì bốn việc trước sửa lỗi **đang gây hại
đo được** trên tài liệu **đang có**, còn B5 chuẩn bị cho tài liệu **chưa có**. Nó
cũng cắm vào đúng nhánh "PDF không lớp text" mà Tầng A dựng lên, nên làm sau thì
rẻ hơn. Nếu tài liệu scan thật xuất hiện sớm, đảo B5 lên trước được mà không phải
viết lại gì.

## 10. Ngoài phạm vi

- ~~OCR~~ — **đã đưa vào phạm vi** theo yêu cầu chủ dự án 2026-08-29, xem mục 5.5.
  Vẫn ngoài phạm vi: **kho tài liệu scan thật** để nghiệm thu độ bền (nhiễu,
  nghiêng, dấu mộc, chữ ký đè) — cổng ở mục 6.1 chỉ dùng ảnh rasterise sạch
- RBAC tầng RAG (19b) và chống injection gián tiếp — hoãn có điều kiện, mở lại khi
  bắt đầu nạp tài liệu từ **nguồn ngoài**
- Nhận hoá đơn từ ảnh chụp vào Odoo — quyết định sản phẩm, chưa có
- Nạp lại toàn bộ corpus: **có** nằm trong phạm vi (embedder chạy local trên GPU
  nên rẻ), nhưng làm ở cuối, sau khi cả bốn bản sửa đã qua cổng
