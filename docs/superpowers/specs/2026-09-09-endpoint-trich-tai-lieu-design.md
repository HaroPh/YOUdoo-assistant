# Endpoint trích tài liệu của backend — thiết kế (lát 1)

**Trạng thái**: thiết kế đã duyệt 2026-09-09, chờ kế hoạch thi hành.

## 1. Vấn đề, đo được chứ không phỏng đoán

Người dùng đính kèm `DVT_2022.pdf` (báo cáo tài chính scan, 16 trang, 5,1 MB)
rồi hỏi. Trợ lý trả lời: *"Không tìm thấy tài liệu liên quan đến câu hỏi này."*

Đo trong DB của Open WebUI:

| tệp | kích thước | status | text trích được |
|---|---|---|---|
| **DVT_2022.pdf** (scan) | 5,1 MB | **`failed`** | **15 ký tự — toàn dấu cách** |
| CV (PDF số) | 114 KB | `completed` | 3.256 ký tự |

Lỗi Open WebUI ghi lại: *"The content provided is empty."*

Nguyên nhân: `rag.content_extraction_engine` là chuỗi rỗng, tức Open WebUI dùng
bộ trích mặc định — chỉ đọc lớp text của PDF, **không có OCR**. Tài liệu ảnh
thuần trích ra rỗng.

**Trong khi đó repo này đã có tầng OCR đọc được chính tệp đó**: bậc 1
(Tesseract) + bậc 2 (dựng lại bảng từ toạ độ chữ), bốn cổng gác, và đã chạy qua
đúng `DVT_2022.pdf` với tỉ lệ tách hai cột tiền 0,889.

Năng lực có. **Đường dẫn tới năng lực thì không** — không route nào của backend
nhận tệp, và `src/ocr/` chỉ có duy nhất `parse.py` gọi tới, qua đường nạp corpus
chạy bằng tay.

**Kiểu hỏng tệ nhất**: Open WebUI *có* ghi `failed`, nhưng người dùng chỉ thấy
"không tìm thấy tài liệu liên quan" — nghe như *tài liệu không chứa thông tin*
chứ không phải *tôi không đọc được tài liệu*. Hỏng mà trông như đã trả lời.

## 2. Phạm vi

Lát 1 làm **một endpoint không trạng thái**. Lát 2 (cảnh báo thời gian và hỏi
có/không trước khi OCR tệp lớn) là việc riêng, cần số đo hôm nay chưa có — §8.

**KHÔNG làm trong lát 1**: không lưu tệp, không ghi DB, không đụng `retrieve()`,
không đụng agent hay prompt. Vì không trạng thái nên **không vướng mục 19b**
(`retrieve()` không có mệnh đề lọc phạm vi, nên mọi chunk ghi vào `rag_chunks`
đều hiển thị với mọi vai).

## 3. Hợp đồng

Đọc thẳng từ mã Open WebUI (`retrieval/loaders/external_document.py`):

```
PUT  {url}/process
     body    = bytes THÔ của tệp (không phải multipart)
     headers = Content-Type: <mime>
               Authorization: Bearer <key>
               X-Filename: <tên tệp, urlencode>
     ->  {"page_content": "...", "metadata": {...}}
         hoặc  [ {...}, {...} ]     <- danh sách được chấp nhận
```

`page_content` + `metadata` là shape **tổng quát**, không có gì riêng của Open
WebUI. Nên **một endpoint duy nhất vừa là hợp đồng của ta, vừa cắm thẳng vào
khe `external_document_loader_url`** — không cần lớp adapter nào.

Đường dẫn chốt: `PUT /v1/documents/process`.

Hai chi tiết đọc được từ mã của họ, cả hai đều có lợi:

- họ gọi trong `asyncio.to_thread` và `requests.put` **không đặt timeout**, nên
  OCR chậm vài phút không bị họ ngắt;
- họ gửi kèm `X-Filename` và header danh tính, nên ta có tên tệp để chọn parser.

## 4. Hình dạng phản hồi: MỘT `Document` mỗi trang

`metadata` mang `page`, `source_kind` (`text` hoặc `ocr`), `ocr_conf`,
`warnings`.

Vì sao không gộp cả tệp làm một: trích dẫn của Open WebUI khi ấy chỉ trỏ tới
"tệp", không tới "trang 12". Và tách theo trang cho người đọc biết **trang nào
do OCR đọc và độ tin bao nhiêu** — thứ Open WebUI hôm nay không có.

**Bảng biểu không cần xử lý thêm.** `parse_pdf` đã dựng hàng bảng thành text có
nhãn cột, dạng `CHỈ TIÊU: Tiền và tương đương tiền cuối kỳ | số: 70 | Nam nay:
148.058.124.948`. Với một LLM, chuỗi đó ngang ngửa bảng Markdown mà không phải
viết thêm bộ dựng nào.

**Đơn vị tách theo từng định dạng** — không suy ra được, phải nêu rõ:

| định dạng | đơn vị | vì sao |
|---|---|---|
| `.pdf` | **trang** | block mang `page` là số trang |
| `.pptx` | **slide** | block mang `page` là SỐ SLIDE (từ 1) |
| `.xlsx`/`.xlsm`/`.xltx` | **sheet** | `parse_xlsx` trả `sheets`, không có `page`; `metadata` mang `sheet` thay `page` |
| `.docx` | **cả tệp, một `Document`** | `parse_docx` đặt `page: None` cho MỌI block — .docx không có khái niệm trang, và bịa ra một cách chia là bịa cấu trúc |

## 5. Luồng bên trong

1. Kiểm token bằng `_kiem_token` **có sẵn** — không dựng cơ chế xác thực thứ hai
2. Lấy đuôi tệp từ `X-Filename`; không nhận dạng được thì từ chối, không đoán
3. Ghi bytes ra tệp tạm — **bắt buộc**: cả bốn parser nhận `path`, không nhận bytes
4. Gọi parser sẵn có theo đuôi: `parse_pdf` / `parse_docx` / `parse_xlsx` / `parse_pptx`
5. Gom theo `page` (hoặc `sheet`) thành một `Document` mỗi đơn vị
6. `finally`: xoá tệp tạm, **kể cả khi parser ném**

**Định dạng lát 1**: đúng `_EXT` của `ingest.py` — `.pdf`, `.docx`, `.xlsx`,
`.xlsm`, `.xltx`, `.pptx`. `.doc` và `.xls` cần LibreOffice chuyển đổi
(`convert.py`), là một tiến trình con chậm — để lát sau, và trả **415** kèm lý
do đọc được chứ không im lặng bỏ qua.

## 6. Xử lý lỗi — phần quan trọng nhất của thiết kế này

Chính lỗi đang đi vá là *hỏng mà trông như đã trả lời*. Endpoint này không được
phép lặp lại nó:

| tình huống | phản hồi |
|---|---|
| trích ra **rỗng** | **422** kèm lý do đọc được — **KHÔNG** trả 200 với chuỗi rỗng |
| trích ra **toàn khoảng trắng** | **422** như trên — xem định nghĩa ngay dưới |
| đuôi tệp không hỗ trợ | 415, nêu rõ những đuôi được hỗ trợ |
| thiếu `X-Filename` | 400 — không đoán định dạng từ nội dung |
| Tesseract thiếu | 503 nêu đúng tên thứ còn thiếu (`TesseractMissing` đã có) |
| parser sinh cảnh báo | vào `metadata.warnings`, **không nuốt** |

**"Rỗng" nghĩa là gì, nói chính xác**: không còn block nào có text khác rỗng
sau `strip()`. KHÔNG phải "độ dài bằng 0" — Open WebUI trả về **15 ký tự toàn
dấu cách** cho `DVT_2022.pdf` và coi đó là nội dung, rồi người dùng nghe "không
tìm thấy tài liệu liên quan". Kiểm theo độ dài là xây lại đúng lỗi đang đi vá.

Cùng định nghĩa mà `parse_pdf` đã dùng để quyết định có gọi OCR hay không
(`if not text_toan_trang`, tức không còn dòng nào sau `strip`) — dùng lại,
không định nghĩa lần thứ hai.

Nguyên tắc đã có sẵn trong dự án: **to tiếng nhưng đọc được**, và một lượt xử
lý bỏ sót nội dung KHÔNG phải là một lượt xử lý thành công.

## 7. Đã cân nhắc rồi bác bỏ

- **Lớp adapter riêng cho Open WebUI.** Không cần: `page_content` + `metadata`
  đã đủ tổng quát để làm hợp đồng của chính ta.
- **Dựng bảng thành Markdown.** `parse_pdf` đã trả text có nhãn cột; thêm bộ
  dựng Markdown là công cho lợi ích chưa đo được.
- **Bất đồng bộ kèm bảng job.** Open WebUI không đặt timeout nên áp lực nhẹ;
  bảng job kéo theo trạng thái, vòng đời, dọn rác — chưa đáng.
- **Chặn số trang.** Chủ dự án chốt: không chặn. Cảnh báo thời gian thuộc lát 2.

## 8. Giới hạn còn lại, nói thẳng

- **Không báo trước được thời gian.** `PUT /process` chạy lúc người dùng ĐÍNH
  KÈM, trước khi họ gửi câu hỏi — không có kênh nào hỏi có/không ở đó. OCR
  khoảng 4 giây mỗi trang: DVT 16 trang ~1 phút, SCID 63 trang ~4 phút. Gửi lại
  cùng tệp thì tức thì vì đệm OCR khoá theo băm nội dung. Đa số tệp (PDF số,
  .docx, .xlsx) trả về dưới một giây. Lát 2 giải quyết phần này.
- **Chỉ Open WebUI gọi.** Chừng nào chưa có frontend riêng, đó là khách hàng
  duy nhất — nhưng hợp đồng không khoá vào họ.
- **39% hàng bảng trong tài liệu scan vẫn mang tên cột vô nghĩa** (đo
  2026-09-08). Endpoint này không sửa điều đó; nó chỉ đưa được kết quả OCR ra
  tới người dùng, việc trước nay chưa từng xảy ra.

## 9. Nghiệm thu

- Test đơn: chọn parser theo đuôi; **dọn tệp tạm kể cả khi parser ném**; trích
  rỗng thì KHÔNG trả 200 — thiếu test cuối là xây lại đúng lỗi đang đi vá.
- Test đầu-cuối trên **tệp thật có sẵn trong repo**: một PDF số, một `.docx`, và
  **`DVT_2022.pdf`** — tệp mà Open WebUI trả 15 dấu cách. Đó là phép nghiệm thu
  thật: cùng tệp, khác kết quả.
- Nghiệm thu sống: cắm URL vào `external_document_loader_url` của Open WebUI,
  đính kèm lại `DVT_2022.pdf`, xác nhận trợ lý trả lời được từ nội dung.
