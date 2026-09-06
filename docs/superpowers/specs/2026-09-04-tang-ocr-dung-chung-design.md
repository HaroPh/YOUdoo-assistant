# Tầng đọc tài liệu ảnh (OCR + VLM) — thiết kế

**Ngày**: 2026-09-04. **Nhánh**: `worktree-tang-nap-tai-lieu-1`. **Trạng thái**: thiết kế đã
duyệt, CHƯA viết code, CHƯA có implementation plan (cố ý — xem mục 14).

Thay thế phần **kiến trúc** của `2026-08-29-tang-nap-tai-lieu.md` mục 5.5. Mọi **số đo** trong
mục đó vẫn còn giá trị nguyên và được chép lại đây (mục 4) để tài liệu này tự đủ.

## 1. Đề bài

Spec 2026-08-29 mô tả OCR như một **nhánh `if` bên trong `ingest`**: PDF không có lớp text thì
thử OCR trước khi từ chối. Định vị đó sai ở hai điểm mà chủ dự án nêu ra 2026-09-04.

**Sai thứ nhất — phạm vi phục vụ.** Đọc chữ trong ảnh là năng lực chung của trợ lý, không phải
phụ kiện của RAG:

| tác vụ | trạng thái |
|---|---|
| Nạp tài liệu scan vào RAG | đã có kế hoạch, chưa làm |
| Phân tích tài liệu người dùng đưa vào chat | chưa có, sẽ cần |
| Đọc attachment trong Odoo (hoá đơn chụp ảnh) | mục 10 spec 2026-08-29 ghi "quyết định sản phẩm, chưa có" |

Nếu OCR nằm bên trong `rag/ingest.py` thì hai tác vụ sau hoặc phải gọi vòng qua tầng nạp tài liệu
(kéo theo DB, chunk, embedding — thứ chúng không cần), hoặc viết lại bộ đọc ảnh lần thứ hai.

**Sai thứ hai — "OCR" không đủ.** Một trang tài liệu ảnh có **ba loại nội dung**, và Tesseract chỉ
giải được một:

| loại | Tesseract làm được gì | cần gì thêm |
|---|---|---|
| Chữ | đọc tốt (số đo mục 4) | — |
| Bảng biểu | trả về **từ + toạ độ**, KHÔNG trả về ô | dựng lại hàng/cột từ toạ độ, hoặc VLM |
| Hình ảnh / đồ thị | chỉ đọc chữ *trong* ảnh, không mô tả được nội dung | VLM |

Đồ thị là ca nguy hiểm nhất: OCR một biểu đồ cho ra các nhãn trục rời rạc *trông như dữ liệu*
nhưng mất hết quan hệ — **tệ hơn không có gì**, vì nó nạp vào corpus thứ đọc như số liệu thật.

Bài này thiết kế **một tầng có ranh giới riêng, hai máy đọc phía sau một hợp đồng**.

## 2. Hai máy đọc, một hợp đồng

Điểm cốt lõi của thiết kế: **OCR và VLM là hai chiến lược, không phải hai tầng.** Consumer không
cần biết trang này được đọc bằng cách nào; nó chỉ nhận về các **vùng có kiểu** kèm mức tin cậy.

| máy đọc | chạy ở đâu | chi phí | dùng cho |
|---|---|---|---|
| Tesseract | **local, CPU** | miễn phí, ~2,5 s/trang | vùng chữ |
| Gemini flash-lite | **API** | một suất hạn mức, ~3-5 s/trang | vùng bảng, hình, đồ thị |

Bộ định tuyến quyết định vùng nào đi đường nào, và **bản thân nó chạy local, rẻ**: Tesseract đã
trả về hộp chữ, nên vùng rộng mà không có hộp nào chính là vùng hình. Không cần gọi VLM để quyết
định có gọi VLM hay không.

## 3. Ba tầng

Mỗi tầng có đúng một trách nhiệm và **không biết gì về tầng trên**.

| tầng | tệp | biết gì | KHÔNG biết gì |
|---|---|---|---|
| 0 — máy đọc | `backend/src/ocr/engine.py`, `vision.py` | một ảnh → chữ/mô tả + độ tin cậy | PDF, trang, DB, chunk, agent |
| 1 — tài liệu | `backend/src/ocr/document.py` | PDF → ảnh từng trang → phân vùng → định tuyến → đệm | DB, chunk, ai đang gọi mình |
| 2 — consumer | `rag/parse.py`, (sau: chat, Odoo) | khi nào cần chữ, và làm gì với chữ đó | cách đọc hoạt động |

**Tầng 0** — hai module song song, cùng trả về một kiểu kết quả:
`ocr_image(png) -> OcrResult` (Tesseract) và `describe_region(png) -> VisionResult` (Gemini). Dò
binary `tesseract` qua biến môi trường có fallback, **đúng khuôn `convert.py` đã dựng cho
`soffice`** (env → PATH → vài vị trí quen thuộc).

**Tầng 1** — `read_pdf(path, pages=None) -> list[Page]`. Rasterise bằng `pypdfium2` (đã có sẵn
theo `pdfplumber`, không thêm phụ thuộc), phân vùng, định tuyến, quản lý đệm (mục 7).

**Tầng 2** — mỗi consumer chỉ dịch input/output. Consumer đầu tiên và duy nhất trong phạm vi hiện
tại là `parse_pdf` (mục 11).

Module tầng 0 và 1 là **module lá** theo đúng nghĩa dự án đã dùng cho `xlsx_header.py`: import
được từ bất cứ đâu mà không kéo theo DB hay cấu hình runtime.

## 4. Số đo

### 4.1 Chân OCR (đo 2026-08-29, chép từ spec cũ)

**Chọn engine:**

| phương án | phụ thuộc thêm | phán quyết |
|---|---|---|
| EasyOCR | 12 gói, **đè `torch` 2.11.0+cu128 lên 2.13.0** | **Loại** — gần như chắc giết reranker GPU |
| RapidOCR (onnxruntime) | 7 gói, không đụng torch | An toàn nhưng tiếng Việt yếu |
| **Tesseract + `pytesseract`** | **1 gói pip** + 1 binary | **Chọn** |

**Chế độ phân vùng trang (PSM): bắt buộc 6.** Đo trên 3 trang bảng, thước là recall theo TỪ:

| chế độ | trang 14 | trang 16 | trang 18 | TB |
|---|---|---|---|---|
| PSM 3 (mặc định) | 0,810 | 0,642 | **0,256** | 0,569 |
| PSM 4 | 0,693 | 0,802 | 0,576 | 0,690 |
| **PSM 6** | **0,851** | **0,862** | **0,882** | **0,865** |
| PSM 11 | 0,822 | 0,713 | 0,800 | 0,778 |
| PSM 12 | 0,798 | 0,697 | 0,789 | 0,761 |

Điều đáng sợ không phải PSM 3 kém, mà là nó **hỏng không đều giữa các trang** — 0,26 ở trang này,
0,81 ở trang kia, **không báo gì**.

**Độ phân giải: 200 DPI**, đo lại dưới PSM 6:

| DPI | tốc độ | recall TB |
|---|---|---|
| 150 | 2,2 s/trang | 0,840 |
| **200** | **2,5 s/trang** | **0,865** |
| 300 | 4,5 s/trang | 0,847 |
| 400 | 5,9 s/trang | 0,866 |

**Cài đặt**: Tesseract 5.4.0 qua winget; `vie.traineddata` từ `tessdata_best` (12,4 MB), để ở
`C:/Users/ADMIN/.tessdata` trỏ bằng `TESSDATA_PREFIX` (ghi vào `Program Files` cần admin nên
thất bại). Ngôn ngữ chạy: `vie+eng`.

### 4.2 Chân VLM (đo 2026-09-04, probe mới)

Gửi thẳng ảnh rasterise 200 DPI (1654×2339 px) tới hai model trong catalog:

| | `gemini-3.1-flash-lite` | `gemini-3.5-flash-lite` |
|---|---|---|
| Nhận ảnh | ✓ | ✓ |
| Biểu mẫu BCTC (`bieumau_bctc_hopnhat.pdf` tr.3) | 4,9 s | 3,5 s |
| Hoá đơn thật (`invoice_51109301.pdf`) | 4,1 s | 2,9 s |
| **Số khớp NGUYÊN VĂN với lớp text gốc** | **30/30** | **30/30** |

Trên hoá đơn, cả 30 chuỗi số — mã hoá đơn, ngày, số lượng, đơn giá, thành tiền — chép lại đúng
từng ký tự. Trên biểu mẫu BCTC: giữ đúng dấu tiếng Việt, đúng mã số chỉ tiêu, đúng phân cấp
`VI.` → `1.` → `2.`

**Giới hạn của chính phép đo này, nói rõ để không ai đọc bảng trên thành nhiều hơn nó có:**

- **N = 1 trang** cho phần số. Đây là phép thử khói, **không phải hiệu chỉnh**. Ngưỡng chấp nhận
  phải đo trên tập lớn hơn khi có việc thật.
- Ảnh là bản rasterise **sạch** từ PDF số — không nghiêng, không nhiễu, không dấu mộc, không chữ
  ký đè. Cùng giới hạn mà cổng tự nuôi (mục 13) cũng mắc.
- **Chưa thử đồ thị lần nào.** Ràng buộc "không trích số liệu từ biểu đồ" (mục 9) giữ nguyên,
  không được nới dựa trên bảng số này.
- Lần probe đầu tôi chọn nhầm một trang **biểu mẫu TRỐNG** nên phép đối chiếu trả `0/0` — không
  tìm thấy số nào để kiểm. Ghi lại vì suýt báo một kết quả trông sạch với mẫu số bằng 0, đúng
  lớp lỗi "cổng không đo gì" đã tái phát nhiều lần trong dự án.

### 4.3 Phần cứng (đo 2026-09-04)

| | |
|---|---|
| GPU | NVIDIA RTX 5060 Ti, **8 GB VRAM** (1,1 GB lúc nghỉ) |
| CPU | **20 nhân** |
| Embedder | `bge-m3` qua Ollama riêng, cổng 11435 |
| Reranker | `BAAI/bge-reranker-v2-m3`, GPU |

## 5. Vì sao KHÔNG dùng VLM local

Giả thuyết ban đầu ("có GPU thì chạy VLM local") **bị số đo bác bỏ**, và lý do tinh hơn là "hết
VRAM":

- `bge-m3` + `bge-reranker-v2-m3` khi cùng nóng chiếm khoảng **2,5-3 GB** → còn ~5 GB.
- VLM **đủ giỏi** cho chữ Việt có dấu + bảng dày là cỡ 7B trở lên: Qwen2.5-VL 7B Q4 riêng trọng
  số ~5,5 GB, cộng bộ mã hoá thị giác và **KV cache cho ảnh độ phân giải cao** (một trang 200 DPI
  sinh hàng nghìn token thị giác) → cần ~6,5-7 GB. **Không vừa.**
- Cỡ **vừa** được là 3B (~3,5 GB cả KV) — nhưng 3B trên tài liệu hành chính tiếng Việt thì chất
  lượng không đáng tin, và trong kho hoá đơn/thuế thì "không đáng tin" là thứ tệ nhất.

Nên đây không phải "không còn chỗ", mà là **chỗ chỉ đủ cho cỡ model không đủ tin cậy cho đúng
loại tài liệu này**. Kết quả phụ đáng mừng: vì Gemini làm tốt phần này (mục 4.2), GPU cứ để yên
cho embedder và reranker.

**Con số 2,5-3 GB là ƯỚC LƯỢNG từ kích thước model, chưa đo đỉnh thật** (lúc đo GPU chỉ dùng
1,1 GB nên cả hai chưa nạp). Ai cần con số cứng thì chạy một truy vấn RAG thật rồi đo đỉnh VRAM.

## 6. Artifact: vùng CÓ KIỂU, không phải khối text phẳng

Mỗi trang lưu thành JSON chứa danh sách vùng, mỗi vùng có kiểu:

| kiểu | nội dung |
|---|---|
| `text` | dòng chữ + confidence **từng từ** + **toạ độ** |
| `table` | dựng lại từ toạ độ, xuất đúng **khuôn bảng dự án đã dùng ở mọi nơi khác**: mỗi hàng một dòng, cột ngăn bằng `\|` (giống `_bang_thanh_text` của docx và `_pptx_table_to_text` của slide) |
| `figure` | **không giả vờ trích được text**: ghi nhận là hình/đồ thị, giữ ảnh cắt, kèm mô tả VLM (tuỳ chọn) |

**Vì sao KHÔNG lưu Markdown.** Markdown đòi ai đó *suy ra* đâu là tiêu đề — mà suy cấu trúc là
việc của tầng parse, trên tài liệu gốc có nhiều thông tin hơn (style, lưới bảng, font). Nếu tầng
đọc nhả Markdown thì phỏng đoán cấu trúc bị **đóng băng vào artifact**: sai thì đóng băng luôn cái
sai, và tầng sau không phân biệt nổi đâu là cấu trúc thật. Tệ hơn, nó tạo **bộ dò tiêu đề thứ
hai** phải giữ đồng bộ với bộ trong `parse.py` — đúng thứ review toàn nhánh vừa gắn cờ ở
`xlsx_header.py` (hai predicate gần giống nhau, chỉ khác trong docstring, đã gây một hồi quy
thật).

Khác biệt giữa "vùng có kiểu" và Markdown: kiểu vùng **đo được từ hình học** (vùng rộng không có
hộp chữ → là hình), còn cấp tiêu đề là **phỏng đoán ngữ nghĩa**. Cái đầu ghi vào artifact được,
cái sau thì không.

**Giữ toạ độ vì nó miễn phí** (Tesseract xuất TSV sẵn) và vì spec cũ đã ghi bài học Tesseract xếp
cột khác pdfplumber — không có toạ độ thì sau này không ai dựng lại được thứ tự đọc hay tách cột.
Nguyên tắc: **không mất mát ở tầng dưới, diễn giải ở tầng trên.** Vứt thông tin ở tầng 0 là không
đảo ngược được; thêm diễn giải ở trên thì lúc nào cũng thêm được.

## 7. Kho đệm: trên đĩa, khoá theo hash + cấu hình

Kết quả đọc là thứ **dẫn xuất được**, nên là đệm, không phải dữ liệu gốc. Không dựng bảng Postgres
cho nó: hôm nay chưa consumer nào cần truy vấn chéo, và một bảng chưa ai đọc là hạ tầng phải bảo
trì mà không trả lại gì.

**Khoá đệm phải gồm cả dấu vân tay cấu hình**, không chỉ `content_hash`:

    khoá = hash(nội dung tệp) + hash(PSM, DPI, lang, phiên bản tesseract, model VLM)

Vì sao: đổi PSM/DPI/model là ra kết quả khác. `convert.py` hiện **đang có đúng lỗ hổng này** — nó
khoá đệm chỉ theo hash tệp, nên đổi tham số LibreOffice sẽ dùng lại bản cũ mà không ai biết. Chưa
lộ ra vì LibreOffice ổn định hơn; tầng này không lặp lại nó.

**Ghi tạm rồi đổi tên nguyên tử** — bài học đã trả giá ở `convert.py`: tệp cụt do timeout ở lại
thì bẩn **vĩnh viễn**, vì khoá đệm không bao giờ tự lành.

## 8. Cờ xuất xứ: ba bậc, trong DB

`rag_chunks` thêm hai cột:

| cột | giá trị |
|---|---|
| `source_kind` | `'text'` > `'ocr'` > `'ocr_repaired'` > `'vision_description'` — tin cậy giảm dần |
| `ocr_conf` | độ tin cậy trung bình, `NULL` khi `source_kind='text'` |

Phải nằm trong DB chứ không trong đệm: đây là chiều **"có đáng tin không"** mà retrieval và việc
chống injection gián tiếp (mục 10 spec 2026-08-29) sẽ cần đọc được, và nó phải sống sót qua mọi
lần re-chunk.

**Quy tắc gộp là BI QUAN**, ghi rõ vì đây đúng loại quyết định hay bị quyết ngầm và quyết sai:

- một `block` mang khoá tuỳ chọn `source_kind`; vắng khoá nghĩa là `'text'`
- một `chunk` gộp nhiều block lấy bậc **thấp tin cậy nhất** trong các block thành phần
- `ocr_conf` của chunk lấy **min**

**Bậc `ocr_repaired` (thêm 2026-09-06).** Chữ do Tesseract đọc, sau đó được VLM sửa trong giới hạn
mục 9. Nằm **giữa** `ocr` và `vision_description`, không phải dưới cùng: `vision_description` là
văn LLM **tự viết** về một tấm hình, còn `ocr_repaired` là chữ **máy đọc**, LLM chỉ chạm vào token
không chứa chữ số.

Vì sao là **một giá trị enum nữa** chứ không phải cột cờ trực giao: quy tắc gộp bi quan là đúng một
phép `max(rank)` trên một thứ tự **tuyến tính**. Thêm cột cờ là phải định nghĩa nó tương tác với
rank ra sao — thêm chỗ để đảo ngược quy tắc tin cậy, đúng lớp lỗi review toàn nhánh đã bắt hai lần
(giá trị lạ được thăng lên hạng tin nhất; chữ OCR chui vào embedding dưới nhãn `text`).

**Nhãn phải trung thực**: chunk chỉ mang `ocr_repaired` khi có **ít nhất một sửa đổi được chấp
nhận**. Verifier vứt hết đề xuất thì nó vẫn là `ocr`.

Bốn giá trị làm quy tắc **allow-list** cho consumer đầu tiên càng bắt buộc: tin khi `== 'text'`,
không bao giờ viết deny-list — càng nhiều giá trị thì deny-list càng dễ sót một.

## 9. Ba ràng buộc giữ chân VLM lành

**Ràng buộc 1 — KHÔNG bao giờ để LLM viết lại text đã trích được.**

Kho này là hoá đơn, bảng thuế, sổ kế toán. Một LLM "sửa lỗi OCR" có thể lặng lẽ đổi `1.500.000`
thành `1.800.000` — một sửa đổi *trông rất hợp lý* và không cách nào phát hiện. Đó là bịa đặt có
vẻ đáng tin, ngược hẳn nguyên tắc "hỏng lớn tiếng còn hơn thiếu âm thầm". Nó còn **phá vệt kiểm
toán**: `ocr_conf` mô tả thứ Tesseract đọc được; nếu LLM viết lại thì con số đó không còn mô tả
thứ đang nằm trong DB.

Cách dùng LLM **đúng chỗ** cho cùng mục đích:
- **LLM là người ĐỌC, không phải người SỬA**: chunk mang `source_kind`/`ocr_conf` đi tới lúc trả
  lời; prompt tổng hợp được biết "đoạn này từ OCR, ký tự có thể sai, đừng trích số như thể chính
  xác". Vẫn dùng khả năng vá-nghĩa-theo-ngữ-cảnh, nhưng ở chỗ **người dùng nhìn thấy được**.
- **Đánh dấu chỗ yếu thay vì sửa nó**: từ nào confidence dưới ngưỡng thì ghi nhận, để cả người lẫn
  LLM biết *chữ nào* đang lung lay.

Mô tả từ VLM (mục 6, kiểu `figure`) **không vi phạm ràng buộc này** vì nó khác về bản chất: nó
*tạo thêm* thứ mà trước đó không có gì cả, không phá huỷ phép đo nào. Nhưng nó phải mang bậc
`vision_description` và **không bao giờ trộn vào văn bản trích được**.

### 9.1 Sửa đổi ràng buộc 1 — ngoại lệ CÓ ĐÁY cho token không chứa chữ số (2026-09-06)

Chủ dự án quyết định cho VLM **làm giàu** chữ Tesseract đọc được (dấu tiếng Việt sai, rác dấu
mộc), sau khi đo trên tài liệu scan thật đầu tiên. Ràng buộc 1 **không bị bỏ**, nó bị **thu hẹp
phạm vi** — và ranh giới phải cưỡng chế bằng mã, không bằng prompt.

| loại token | VLM được sửa? | vì sao |
|---|---|---|
| **không chứa chữ số** (`lity kể`→`lũy kế`) | **có** | từ vựng tiếng Việt là tập đóng; sửa sai ra một từ *trông sai ngay*, không phải lời nói dối hợp lý. Rủi ro có đáy |
| **chứa chữ số** (`1.500.000`, `V.2c`, mã `01`) | **không, tuyệt đối** | `1.500.000`→`1.800.000` hợp lý y hệt nhau. Đây đúng ca ràng buộc 1 sinh ra để chặn |

**Số đo làm ranh giới này sắc hơn** (trang 17 bản BCTC scan thật, 2026-09-06): Tesseract đọc
**35/37 số tiền dài chính xác tuyệt đối** — không cần ai làm giàu ở đó. Chỗ nó hỏng là (a) chữ có
dấu và (b) **token số ngắn** (`01`→`0`, `02`→`022`, sai 3/14 = 21% cột `Mã số`). Mà (b) chính là
chỗ VLM **không được** đụng. Nghĩa là vùng giao có ích chỉ còn **chữ có dấu** — vẫn đáng làm,
nhưng nhỏ hơn vẻ ngoài của ý tưởng. Đừng bán nó to hơn thế.

**Cưỡng chế bằng mã, không bằng prompt.** Prompt "đừng đổi số" là lời đề nghị, không phải cơ chế.
Sau khi VLM trả về, diff từng token:
- token đổi mà **chứa chữ số** → **vứt bản sửa, giữ bản gốc**
- token đổi mà **khoảng cách sửa quá lớn** → cũng vứt: đó là viết lại, không phải sửa lỗi

**Không bao giờ ghi đè.** `Region` giữ thêm `text_goc` (Tesseract thuần) bên cạnh `text` (đã làm
giàu). Nằm trong **artifact đệm**, KHÔNG thêm cột vào `rag_chunks`: một chunk gộp nhiều block nên
không map 1-1 với region, lưu "bản gốc theo chunk" phải dựng lại ánh xạ — thêm một chỗ lệch được.
Và 98,9% corpus là `text` thuần, hai cột sẽ giống hệt nhau.

Muốn dựng lại corpus **không làm giàu**: chunk lại từ đệm — không OCR lại, không gọi API lại.
Giới hạn nói thẳng: **đệm là thứ dẫn xuất được, không phải vệt kiểm toán vĩnh viễn.** Xoá đệm hoặc
đổi model VLM (đổi vân tay cấu hình) là mất `text_goc` cũ; dựng lại phần Tesseract thì miễn phí,
phần VLM thì tốn một lượt gọi.

**Bản đi vào embedding và bản hiện cho người dùng đều là bản đã làm giàu** — đó chính là điểm của
việc này (`lity kể` không khớp truy vấn `lũy kế`). Phần LLM chạm vào đã bị giới hạn ở token không
chứa chữ số, nên đây không phải là để LLM viết lại nội dung.

**Khi VLM và Tesseract lệch nhau ở token CÓ chữ số**: giữ Tesseract, và phát **cảnh báo có tên**
qua `IngestReport`. Dùng đường to-tiếng đã có, không dựng cơ chế mới, không thêm cột.

**Ngoại lệ hẹp, ghi lại kẻo bị nới**: cổng số học nội tại của báo cáo tài chính (dòng tổng phải
bằng tổng các dòng thành phần) là **cơ chế duy nhất** có thể cho phép sửa một chữ số an toàn — nó
là ràng buộc ngoài mà LLM không thoả được bằng cách nghe hợp lý. Nhưng nó chỉ tồn tại trong bảng
tài chính, không phải mọi tài liệu. Không được suy rộng thành quy tắc chung.

**Ràng buộc 2 — KHÔNG trích số liệu từ đồ thị.** Mô tả *đồ thị nói về cái gì* (tiêu đề, trục, xu
hướng); tuyệt đối không đọc giá trị từng cột rồi trình bày như dữ liệu. Khi cần số chính xác,
bảng gốc gần như luôn nằm đâu đó khác trong tài liệu.

**Ràng buộc 3 — có cổng và có đếm.** Xem mục 10.

## 10. Hạn mức là ràng buộc KIẾN TRÚC, không phải ghi chú vận hành

3 khoá × rpd 500 = 1.500 lượt/ngày. Nghe rộng rãi, nhưng đây **cùng một hồ với chính con
chatbot**: router, chitchat, tổng hợp câu trả lời đều rút từ đúng những khoá và model này.

Đáng chú ý: **hôm nay đường nạp tài liệu KHÔNG tiêu hạn mức nào** (embedder chạy local qua
Ollama). Chân VLM sẽ là **lần đầu tiên việc nạp tài liệu tranh hạn mức với chat**.

Hậu quả nếu bỏ qua: một lượt nạp hàng loạt có thể **làm trợ lý ngừng trả lời được** — và cạn hạn
mức không báo lỗi rõ ràng mà **âm thầm hạ chất lượng** (model yếu bỏ qua chỉ dẫn SOP, không phân
biệt được với lỗi hành vi). Đã có tiền lệ: spike Gemini embedding bị **hoãn hẳn** vì rpd không đủ
cho một lượt index corpus trong ngày.

Phép tính thô: kho scan 200 trang, ~15% có hình cần VLM → 30 lượt, không sao. Kho 2.000 trang có
hình mọi trang → 2.000 lượt = **4 ngày hạn mức**.

**Bắt buộc, chọn ít nhất một:**

1. dành riêng một khoá cho ingest, tách khỏi khoá chat; hoặc
2. chạy nạp hàng loạt theo lịch ngoài giờ; hoặc
3. trần cứng số lượt VLM cho mỗi lượt nạp, vượt thì dừng và **báo có tên**, không âm thầm cắt.

Và **đếm mọi lượt VLM vào sổ `llm_usage`** như mọi lượt gọi khác — một đường tiêu hạn mức không
có trong sổ là đường không ai thấy khi đi tìm nguyên nhân cạn.

## 11. Điểm kích hoạt: tự động, theo TRANG, bên trong `parse_pdf`

Mô hình gọi là **pipeline tự động**, không phải tool cho agent (quyết định 2026-09-04): tài liệu
nào vào hệ mà không đọc được chữ thì tự đi qua tầng 1. Agent không cần biết tầng này tồn tại.

`parse_pdf` vốn **đã chạy hai lượt**. Điểm chèn nằm sẵn giữa hai lượt:

1. lượt một dựng `pages: list[list[str]]` như hiện tại
2. **mới**: trang nào ra rỗng → không có lớp text → gọi tầng 1 cho ĐÚNG trang đó, đổ vùng đọc
   được vào chỗ trống, ghi số trang vào `ocr_pages`

   **"Rỗng" nghĩa là KHÔNG CÒN DÒNG NÀO** sau bước strip hiện có (`pages[i] == []`), không phải
   "ít chữ". Nói rõ vì có một biến thể đã biết là sẽ tới: máy scan đời mới thường nhúng sẵn một
   lớp OCR kém, nên trang scan có thể trả về **vài ký tự rác** thay vì rỗng hẳn. KHÔNG đặt ngưỡng
   "dưới N ký tự thì coi là rỗng" ở đây: chưa có tài liệu scan thật nào để hiệu chỉnh N, và một
   ngưỡng rút từ không khí đúng là thứ dự án này cấm. Xử lý khi có dữ liệu thật, kèm số đo.
3. `detect_page_furniture` chạy sau, nên header/footer của trang scan cũng được nhận diện
4. lượt hai dựng block như hiện tại, block của trang trong `ocr_pages` mang `source_kind` tương ứng

Không đụng cấu trúc hàm, không thêm lượt, không đọc lại trang đã có chữ.

## 12. Hỏng thì to tiếng

Đọc ra text gần rỗng, hoặc confidence dưới ngưỡng → **`Rejection` mang tên tệp và số trang** trong
`IngestReport`. Không nạp rác vào corpus rồi báo thành công. Thiết kế này rơi đúng vào hạ tầng Kế
hoạch 1 đã dựng — không phát minh cơ chế mới.

**Ngưỡng confidence CHƯA CHỐT.** Phải hiệu chỉnh trên số đo thật, đúng luật "không hằng số rút từ
không khí". `0,865` là **đường cơ sở**, không phải mục tiêu, và nó đo với đáp án là lớp text của
pdfplumber — bản thân lớp đó cũng có lỗi thứ tự bảng.

## 13. Cổng tự nuôi

Hôm nay corpus có **0 tài liệu cần đọc bằng ảnh** (683/683 trang PDF luật và 100/100 hoá đơn đều
có lớp text). Một thành phần không ai chạy qua thì **chết âm thầm**. Dự án đã trả giá ba lần:
reranker chết 6 tuần; chân sparse của hybrid chết từ ngày đầu (0/64 câu); riêng Kế hoạch 1 đếm
được **tám** lần "cổng trông như đang gác nhưng không đo gì".

Cổng: lấy trang **đã có** lớp text → rasterise → vứt lớp text → đọc lại bằng ảnh → so ngược.

- **luôn có dữ liệu để chạy**, corpus tự sinh đáp án, không gán tay ô nào
- chứng minh đường đọc-bằng-ảnh còn **sống** ở mỗi lượt chạy test

**Thước đo phải là recall theo TỪ, không phạt thứ tự đọc.** Bẫy đã dính: `SequenceMatcher` trên
toàn chuỗi cho 0,46 và suýt dẫn tới kết luận "OCR tiếng Việt kém". Thật ra chữ nhận gần đúng hết;
điểm thấp do **thứ tự đọc khác** và **đường kẻ bảng bị đọc thành ký tự**, nuốt chữ cái đầu dòng
(`ừ xi` thay vì `từ xỉ`, `ltệt Nam` thay vì `Việt Nam`).

**Giới hạn nói thẳng**: ảnh rasterise **sạch hơn scan đời thật**. Cổng này chứng minh "còn sống và
đại khái đúng", **không** chứng minh "chịu được scan đời thật".

Cổng chạy trên **chân Tesseract** (local, miễn phí, tất định). Chân VLM **không** đưa vào cổng
chạy mặc định — nó tiêu hạn mức và không tất định; nghiệm thu nó bằng một bộ `live` chạy tay.

## 14. Thực thi theo bậc

Hôm nay corpus có 0 tài liệu scan. Dựng trọn cả hai chân bây giờ là xây thứ không ai chạy qua.

| bậc | làm gì | khi nào |
|---|---|---|
| 1 | Chân **Tesseract** đầy đủ + cổng tự nuôi + artifact vùng-có-kiểu (chỉ sinh kiểu `text`) | khi tới lượt, sau B3/B4 |
| 2 | Dựng **bảng** từ toạ độ (local) | khi có tài liệu scan thật để hiệu chỉnh |
| 3 | Chân **VLM** cho `figure` + tách hồ hạn mức | khi có tài liệu scan thật có hình |

Hợp đồng artifact (mục 6) và cột DB (mục 8) dựng **ngay từ bậc 1** để bậc 2 và 3 không phải thiết
kế lại kho đệm hay đổi schema.

## 15. Ngoài phạm vi

- **Tool cho agent gọi chủ động** — đã cân nhắc và loại (chọn pipeline tự động). Mở lại được mà
  không phải viết lại gì: tầng 1 đã là hàm thuần, một tool chỉ là consumer thứ hai.
- **Bảng Postgres cho kết quả đọc** — hoãn, xem mục 7.
- **VLM local** — loại có số đo, xem mục 5.
- **Kho scan thật để nghiệm thu độ bền** (nhiễu, nghiêng, dấu mộc) — cổng mục 13 chỉ dùng ảnh sạch.
- **Hàng đợi / chạy nền cho tài liệu dài** — đường nạp là script batch nên chậm không sao. Ai thêm
  đường vào từ chat sau này phải tự xử lý ràng buộc độ trễ (50 trang × 2,5 s = 125 s, không hợp
  cho một lượt chat); ghi lại để người đó không phát hiện muộn.

## 16. Giới hạn đã biết và giả thuyết đã bị bác bỏ

- **Việc này không chữa lỗi nào đang có.** 683/683 trang PDF luật có lớp text, 100/100 hoá đơn
  cũng vậy. Bệnh hiện tại là **cấu trúc bảng** (B4) và **phân cấp tài liệu** (B3). Đây là chuẩn bị
  trước, không phải bản sửa cho lỗi đang đo được.
- **"Có GPU thì chạy VLM local"** — SAI, xem mục 5. 8 GB chỉ đủ cho cỡ model không đủ tin cậy.
- **"EasyOCR là lựa chọn hiển nhiên vì đã có torch+CUDA"** — SAI, nó đè `torch` xuống bản mới.
- **"Thước ký tự đo được chất lượng OCR"** — SAI, xem mục 13.
- **"300 DPI tệ hơn 200 DPI"** — kết luận đầu đo dưới PSM 3 (sai chế độ); đo lại dưới PSM 6 thì
  không đứng vững. Đổi một tham số thì mọi tham số đã so trước đó phải so lại.
- **Chưa đo trên scan thật, chưa đo trên đồ thị.** Mọi số ở mục 4 đo trên ảnh rasterise sạch.
- **Phép đo VLM là N=1.** Đường cơ sở, không phải ngưỡng.

## 17. Thứ tự và vì sao chưa có implementation plan

Thứ tự giữ nguyên: **B3 (Word phân cấp) → B4 (PDF bóc bảng) → tầng này**.

B3 và B4 sửa tác hại **đo được trên tài liệu đang có** (377/377 block mất phân cấp và nhúng đường
dẫn Windows vào vector; 70/195 mã thuế gắn sai mức). Tầng này chuẩn bị cho tài liệu **chưa có**.

**Chưa viết implementation plan có chủ ý**: cả B3 lẫn B4 đều sửa chính `parse_pdf` — đúng chỗ mục
11 cắm vào. Một plan viết hôm nay sẽ lạc hậu trước khi tới lượt chạy.

## 18. Nợ triển khai

- `TESSDATA_PREFIX` (`C:/Users/ADMIN/.tessdata`) và đường dẫn binary `tesseract` đều là **đường
  dẫn máy cá nhân**. Khai qua biến môi trường có dò mặc định, cùng khuôn `convert.soffice_path()`.
- **Tách hồ hạn mức** (mục 10) là việc phải làm TRƯỚC khi bật chân VLM, không phải sau.
