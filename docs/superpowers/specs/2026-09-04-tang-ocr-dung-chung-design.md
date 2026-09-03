# Tầng OCR dùng chung — thiết kế

**Ngày**: 2026-09-04. **Nhánh**: `worktree-tang-nap-tai-lieu-1`. **Trạng thái**: thiết kế đã
duyệt, CHƯA viết code, CHƯA có implementation plan (cố ý — xem mục 11).

Thay thế phần **kiến trúc** của `2026-08-29-tang-nap-tai-lieu.md` mục 5.5. Mọi **số đo** trong
mục đó vẫn còn giá trị nguyên và được chép lại đây (mục 3) để tài liệu này tự đủ.

## 1. Đề bài

Spec 2026-08-29 mô tả OCR như một **nhánh `if` bên trong `ingest`**: PDF không có lớp text thì
thử OCR trước khi từ chối. Định vị đó sai ở một điểm mà chủ dự án nêu ra 2026-09-04: **đọc chữ
trong ảnh là năng lực chung của trợ lý**, không phải phụ kiện của RAG. Các tác vụ sẽ cần nó:

| tác vụ | trạng thái |
|---|---|
| Nạp tài liệu scan vào RAG | đã có kế hoạch (B5), chưa làm |
| Phân tích tài liệu người dùng đưa vào chat | chưa có, sẽ cần |
| Đọc attachment trong Odoo (hoá đơn chụp ảnh) | mục 10 spec 2026-08-29 ghi "quyết định sản phẩm, chưa có" |

Nếu OCR nằm bên trong `rag/ingest.py` thì tác vụ thứ hai và thứ ba hoặc phải gọi vòng qua tầng
nạp tài liệu (kéo theo DB, chunk, embedding — thứ chúng không cần), hoặc viết lại bộ đọc ảnh lần
thứ hai. Cả hai đều sai. Bài này thiết kế OCR thành **một tầng có ranh giới riêng**.

## 2. Ba tầng

Mỗi tầng có đúng một trách nhiệm và **không biết gì về tầng trên**.

| tầng | tệp | biết gì | KHÔNG biết gì |
|---|---|---|---|
| 0 — máy đọc | `backend/src/ocr/engine.py` | một ảnh → chữ + độ tin cậy | PDF, trang, DB, chunk, agent |
| 1 — tài liệu | `backend/src/ocr/document.py` | PDF → ảnh từng trang → gọi tầng 0; đệm kết quả | DB, chunk, ai đang gọi mình |
| 2 — consumer | `rag/parse.py`, (sau này: chat, Odoo) | khi nào cần chữ, và làm gì với chữ đó | cách OCR hoạt động |

**Tầng 0** — `ocr_image(png_bytes) -> OcrResult{text, mean_conf}`. Dò binary `tesseract` qua biến
môi trường có fallback, **đúng khuôn `convert.py` đã dựng cho `soffice`** (env → PATH → vài vị
trí quen thuộc). Hằng số cấu hình mang số đo ngay trong docstring, không phải con số trần.

**Tầng 1** — `ocr_pdf(path, pages=None) -> list[OcrPage]`. Rasterise bằng `pypdfium2` (đã có sẵn
theo `pdfplumber`, không thêm phụ thuộc). Quản lý đệm (mục 4).

**Tầng 2** — mỗi consumer chỉ dịch input/output, không chứa logic OCR. Consumer đầu tiên và duy
nhất trong phạm vi hiện tại là `parse_pdf` (mục 6).

Module tầng 0 và 1 là **module lá** theo đúng nghĩa dự án đã dùng cho `xlsx_header.py`: import
được từ bất cứ đâu mà không kéo theo DB hay cấu hình runtime.

## 3. Số đo đã có (chép từ spec 2026-08-29 mục 5.5, không đo lại)

**Chọn engine** — đo 2026-08-29:

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
0,81 ở trang kia, **không báo gì**. Dùng mặc định thì một phần corpus scan biến mất âm thầm.

**Độ phân giải: 200 DPI**, đo lại dưới PSM 6:

| DPI | tốc độ | recall TB |
|---|---|---|
| 150 | 2,2 s/trang | 0,840 |
| **200** | **2,5 s/trang** | **0,865** |
| 300 | 4,5 s/trang | 0,847 |
| 400 | 5,9 s/trang | 0,866 |

400 DPI ngang 200 DPI về chất lượng nhưng chậm 2,4 lần.

**Cài đặt**: Tesseract 5.4.0 qua winget; `vie.traineddata` lấy từ `tessdata_best` (12,4 MB). Ghi
vào `Program Files` cần quyền admin nên thất bại — gói ngôn ngữ để ở `C:/Users/ADMIN/.tessdata`,
trỏ bằng `TESSDATA_PREFIX`. Ngôn ngữ chạy: `vie+eng` (corpus trộn hai thứ tiếng).

**Chạy local trên CPU, không đụng GPU.** GPU là của reranker; đó chính là lý do EasyOCR bị loại.
2,5 s/trang là chi phí chấp nhận được cho đường nạp chạy nền.

## 4. Kho kết quả: đệm trên đĩa, khoá theo hash + cấu hình

Text OCR là thứ **dẫn xuất được** (cùng ảnh + cùng cấu hình → cùng text), nên nó là đệm, không
phải dữ liệu gốc. Không dựng bảng Postgres cho nó: hôm nay chưa consumer nào cần truy vấn chéo
("trang nào confidence thấp", "kho đã OCR bao nhiêu %"), và một bảng chưa ai đọc là hạ tầng phải
bảo trì mà không trả lại gì. Nếu nhu cầu truy vấn xuất hiện thật, thêm bảng sau — đệm đĩa không
chặn đường đó.

**Khoá đệm phải gồm cả dấu vân tay cấu hình**, không chỉ `content_hash`:

    khoá = hash(nội dung tệp) + hash(PSM, DPI, lang, phiên bản tesseract)

Vì sao: đổi PSM hay DPI là ra text khác. `convert.py` hiện **đang có đúng lỗ hổng này** — nó khoá
đệm chỉ theo hash tệp, nên đổi tham số LibreOffice sẽ dùng lại bản cũ mà không ai biết. Chưa lộ ra
vì LibreOffice ổn định hơn, nhưng đây là cùng một lớp lỗi; tầng OCR không lặp lại nó.

**Ghi tạm rồi đổi tên nguyên tử** — bài học đã trả giá ở `convert.py`: tệp cụt do timeout ở lại
thì bẩn **vĩnh viễn**, vì khoá đệm không bao giờ tự lành.

## 5. Cờ xuất xứ: trong DB, không trong đệm

`rag_chunks` thêm hai cột:

| cột | nghĩa |
|---|---|
| `source_kind` | `'text'` (mặc định) hoặc `'ocr'` |
| `ocr_conf` | độ tin cậy trung bình, `NULL` khi `source_kind='text'` |

Vì sao phải nằm trong DB chứ không trong đệm: đây là chiều **"có đáng tin không"** mà retrieval và
việc chống injection gián tiếp (mục 10 spec 2026-08-29) sẽ cần đọc được, và nó phải sống sót qua
mọi lần re-chunk. Đệm trên đĩa không truy vấn được.

**Quy tắc gộp là BI QUAN**, ghi rõ vì đây đúng loại quyết định hay bị quyết ngầm và quyết sai:

- một `block` mang khoá tuỳ chọn `source_kind`; vắng khoá nghĩa là `'text'`
- một `chunk` gộp nhiều block tính là `'ocr'` nếu **bất kỳ** block thành phần nào là OCR
- `ocr_conf` của chunk lấy **min** của các block OCR thành phần — độ tin thấp nhất thắng

## 6. Điểm kích hoạt: tự động, theo TRANG, bên trong `parse_pdf`

Mô hình gọi là **pipeline tự động**, không phải tool cho agent (quyết định 2026-09-04): tài liệu
nào vào hệ mà không đọc được chữ thì tự đi qua tầng 1. Agent không cần biết OCR tồn tại — nó chỉ
thấy "tài liệu này có text". Ít đường rẽ, khó quên gọi, dễ đo.

`parse_pdf` vốn **đã chạy hai lượt** (gom dòng theo trang, nhận diện rác header/footer trên toàn
tài liệu, rồi mới dựng block). Điểm chèn nằm sẵn giữa hai lượt:

1. lượt một dựng `pages: list[list[str]]` như hiện tại
2. **mới**: trang nào ra rỗng → không có lớp text → gọi tầng 1 cho ĐÚNG trang đó, đổ dòng vào chỗ
   trống, ghi số trang vào một tập `ocr_pages`

   **"Rỗng" nghĩa là KHÔNG CÒN DÒNG NÀO** sau bước strip hiện có (`pages[i] == []`), không phải
   "ít chữ". Nói rõ vì có một biến thể đã biết là sẽ tới: máy scan đời mới thường nhúng sẵn một
   lớp OCR kém, nên trang scan có thể trả về **vài ký tự rác** thay vì rỗng hẳn — khi đó điều
   kiện `== []` bỏ sót nó. KHÔNG đặt ngưỡng "dưới N ký tự thì coi là rỗng" ở đây: chưa có tài
   liệu scan thật nào để hiệu chỉnh N, và một ngưỡng rút từ không khí đúng là thứ dự án này cấm.
   Xử lý khi có dữ liệu thật, kèm số đo.
3. `detect_page_furniture` chạy sau, nên header/footer của trang scan cũng được nhận diện như mọi
   trang khác
4. lượt hai dựng block như hiện tại, block của trang trong `ocr_pages` mang `source_kind='ocr'`

Không đụng cấu trúc hàm, không thêm lượt, không OCR trang đã có chữ.

## 7. Hỏng thì to tiếng

OCR ra text gần rỗng, hoặc confidence dưới ngưỡng → **`Rejection` mang tên tệp và số trang** trong
`IngestReport`. Không nạp rác vào corpus rồi báo thành công.

Thiết kế này rơi đúng vào hạ tầng Kế hoạch 1 đã dựng (ba trạng thái tệp + danh sách từ chối có
tên) — không phát minh cơ chế mới.

**Ngưỡng confidence CHƯA CHỐT.** Phải hiệu chỉnh trên số đo thật rồi mới ghi, đúng luật "không
hằng số rút từ không khí" của dự án. `0,865` là **đường cơ sở**, không phải mục tiêu, và nó đo với
đáp án là lớp text của pdfplumber — bản thân lớp đó cũng có lỗi thứ tự bảng, nên một phần "sai" có
thể là lỗi của đáp án chứ không phải của OCR.

## 8. Cổng tự nuôi — phần quan trọng nhất

Hôm nay corpus có **0 tài liệu cần OCR** (683/683 trang PDF luật và 100/100 hoá đơn đều có lớp
text). Một thành phần không ai chạy qua thì **chết âm thầm**. Dự án này đã trả giá đúng ba lần:
reranker chết 6 tuần vì thiếu một dependency mà bốn lớp test đều che; chân sparse của hybrid chết
từ ngày đầu (0/64 câu); và riêng Kế hoạch 1 đếm được **tám** lần "cổng trông như đang gác nhưng
không đo gì".

Cổng: lấy trang **đã có** lớp text → rasterise → vứt lớp text → OCR ảnh → so ngược với bản gốc.

- **luôn có dữ liệu để chạy** (corpus tự sinh đáp án, không cần gán tay ô nào)
- chứng minh đường OCR còn **sống** ở mỗi lượt chạy test
- 1 trang đã thử cho 2.613 ký tự

**Thước đo phải là recall theo TỪ, không phạt thứ tự đọc.** Bẫy đã dính và ghi lại: `SequenceMatcher`
trên toàn chuỗi cho 0,46 và suýt dẫn tới kết luận "OCR tiếng Việt kém". Thật ra chữ nhận gần đúng
hết; điểm thấp do **thứ tự đọc khác** (Tesseract xếp cột khác pdfplumber) và **đường kẻ bảng bị
đọc thành ký tự**, nuốt chữ cái đầu dòng (`ừ xi` thay vì `từ xỉ`, `ltệt Nam` thay vì `Việt Nam`).

**Giới hạn phải nói thẳng**: ảnh rasterise **sạch hơn scan đời thật** — không nghiêng, không nhiễu,
không dấu mộc, không chữ ký đè. Cổng này chứng minh "còn sống và đại khái đúng", **không** chứng
minh "chịu được scan đời thật".

## 9. Ngoài phạm vi

- **Tool OCR cho agent gọi chủ động** — đã cân nhắc và loại ở vòng này (chọn pipeline tự động).
  Mở lại được mà không phải viết lại gì: tầng 1 đã là hàm thuần, một tool chỉ là consumer thứ hai.
- **Bảng Postgres `ocr_pages`** — hoãn, xem mục 4.
- **Cấu trúc bảng từ ảnh** — Tesseract trả về **chữ**, không trả về **ô**. Một trang bảng đi qua
  OCR vẫn dính nguyên bài toán gắn số sang hàng bên cạnh, thậm chí nặng hơn vì mất đường kẻ. OCR
  và bóc bảng là **hai bài toán rời**; B4 vẫn phải làm đầy đủ.
- **Kho scan thật để nghiệm thu độ bền** (nhiễu, nghiêng, dấu mộc) — cổng mục 8 chỉ dùng ảnh
  rasterise sạch.
- **Hàng đợi / chạy nền cho tài liệu dài** — đường nạp là script batch nên chậm không sao. Ai thêm
  đường vào từ chat sau này phải tự xử lý ràng buộc độ trễ (50 trang × 2,5 s = 125 s, không hợp
  cho một lượt chat); ghi lại ở đây để người đó không phát hiện muộn.

## 10. Giới hạn đã biết và giả thuyết đã bị bác bỏ

- **OCR không chữa lỗi nào đang có.** 683/683 trang PDF luật có lớp text, 100/100 hoá đơn cũng
  vậy. Bệnh hiện tại là **cấu trúc bảng** (B4) và **phân cấp tài liệu** (B3), không phải nhận dạng
  chữ. Đây là việc **chuẩn bị trước**, không phải bản sửa cho lỗi đang đo được — nhận định này
  không bị việc dựng tầng riêng phủ nhận.
- **"EasyOCR là lựa chọn hiển nhiên vì đã có torch+CUDA"** — SAI, `--dry-run` cho thấy nó đè
  `torch` xuống bản mới, gần như chắc giết reranker GPU.
- **"Thước ký tự đo được chất lượng OCR"** — SAI, xem mục 8.
- **"300 DPI tệ hơn 200 DPI"** — kết luận đầu tiên đo dưới PSM 3 (sai chế độ); đo lại dưới PSM 6
  thì nó không đứng vững. Đổi một tham số thì mọi tham số đã so trước đó phải so lại.
- **Chưa đo độ chính xác trên scan thật** — mọi số ở mục 3 đo trên ảnh rasterise từ PDF có sẵn lớp
  text.

## 11. Thứ tự và vì sao chưa có implementation plan

Thứ tự giữ nguyên: **B3 (Word phân cấp) → B4 (PDF bóc bảng) → tầng OCR**.

B3 và B4 sửa tác hại **đo được trên tài liệu đang có** (377/377 block mất phân cấp và nhúng đường
dẫn Windows vào vector; 70/195 mã thuế gắn sai mức). Tầng OCR chuẩn bị cho tài liệu **chưa có**.

**Chưa viết implementation plan có chủ ý**: cả B3 lẫn B4 đều sửa chính `parse_pdf` — đúng chỗ mục
6 cắm vào. Một plan viết hôm nay sẽ lạc hậu trước khi tới lượt chạy. Spec này giữ phần kiến trúc
(thứ không lạc hậu); plan viết khi bắt đầu làm.

## 12. Nợ triển khai

`TESSDATA_PREFIX` (`C:/Users/ADMIN/.tessdata`, vì `Program Files` cần admin) và đường dẫn binary
`tesseract` đều là **đường dẫn máy cá nhân**. Phải khai qua biến môi trường có dò mặc định, không
viết cứng — cùng khuôn `convert.soffice_path()`. Máy khác sẽ không có sẵn binary lẫn gói ngôn ngữ.
