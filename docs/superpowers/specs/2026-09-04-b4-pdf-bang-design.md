# B4 — PDF bóc bảng: Thiết kế

**Spec gốc:** `docs/superpowers/specs/2026-08-29-tang-nap-tai-lieu.md` §5.4 (mục 4 trong bảng lỗi
đầu spec: "PDF gắn số sang hàng bên cạnh", **70/195 mã** bảng thuế có mức sai nằm kề, 3/198 mã
không có đáp án đúng trong chunk — ~36% câu hỏi tra bảng bị gài bẫy số liệu).

**Bối cảnh:** Kế hoạch 1 (to tiếng + phủ định dạng), Kế hoạch 2 (Excel dò hàng tiêu đề), B3 (Word
suy phân cấp) đã xong sạch trên worktree `worktree-tang-nap-tai-lieu-1`, chưa merge. Thứ tự roadmap
đã định: A → B2 → B3 → **B4** → tầng OCR (B5, đã thiết kế riêng, xem
`2026-09-04-tang-ocr-dung-chung-design.md`).

## 1. Khảo sát — vì sao lỗi 4 xảy ra

`parse_pdf` hiện tại (`backend/src/rag/parse.py:406-435`) dùng `pypdf` đọc **thô theo dòng trực
quan**: mỗi trang, mỗi dòng `page.extract_text()` trả về thành một block riêng, chạy qua
`heading_level()` để đoán tiêu đề, không có khái niệm "bảng". Khi một trang có bảng nhiều cột,
`pypdf` linearize theo vị trí trực quan trên trang — dễ đọc lệch cột (giá trị của hàng này in ra
cạnh mã của hàng khác) vì không biết ranh giới ô/hàng thật của bảng. Đây là gốc lỗi 4.

`pdfplumber` (đã CÀI trong `.venv` — 0.11.10 — nhưng **chưa khai** trong `requirements.txt`, một
món nợ cần vá) có `page.find_tables()`/`extract_tables()` dò bảng thật qua đường kẻ/khoảng cách
văn bản, cho cấu trúc hàng-cột đúng. Đo 2026-08-29 (spike, xem spec gốc §5.4):

| chế độ | hàng lấy được | mô tả |
|---|---|---|
| mặc định | 194/210 — mất 14 hàng vắt qua ngắt trang | ô ĐẦY ĐỦ |
| `horizontal_strategy="text"` | 210/210 | **55 hàng rỗng mô tả** |

Không chế độ nào đủ một mình.

**Phát hiện thêm khi khảo sát lại 2026-09-04** (đường đi tiếp theo của dữ liệu, không có trong
spec gốc): `.docx`/`.pptx` hiện gộp **CẢ BẢNG thành MỘT block** (`_bang_thanh_text`,
`parse.py:323-337` — các hàng nối `"\n"`, cột nối `"|"`). Trong `chunking.py:51-120`,
`_flush()` nối mọi block trong một mục (kể cả block-bảng) bằng `" ".join(body)` rồi đưa qua
`_split_section_text` — hàm này tách "câu" bằng `_SENT_RE = r"(?<=[.!?…])\s+"`. Một bảng không có
dấu chấm câu cuối hàng bị coi là **MỘT "câu" duy nhất, không có điểm cắt bên trong**: không bao
giờ bị cắt giữa hai hàng (an toàn), nhưng nếu bảng lớn — `bieumau_bctc_hopnhat.pdf` có bảng tới
759 hàng — **CẢ BẢNG dồn vào một chunk vượt xa `CHUNK_SIZE_TOKENS=400`**, pha loãng embedding.
Nhiều khả năng đây là **CƠ CHẾ THẬT** đằng sau tỉ lệ 36%: chunk chứa đúng hàng cần tìm nhưng bị
chôn trong hàng trăm hàng khác nên vector không còn khớp câu hỏi cụ thể. B4 phải sửa CẢ HAI: (a)
trích đúng cấu trúc hàng-cột tại nguồn, (b) đảm bảo ranh giới chunk không xoá cấu trúc đó.

## 2. Corpus thật dùng để nghiệm thu

Tại `d:/Youdoo/tmp-docs`:

- **100 `invoice_*.pdf`** — tự kiểm số học (số lượng × đơn giá = thành tiền; thành tiền + thuế =
  tổng; tổng các dòng = SUMMARY), đúng khuôn Tầng C của spec gốc §6.
- **`ssc_bieumau.pdf`** (8 trang, 53 hàng, 6 cột) — cột `TT` đếm liên tục 1..N, **checksum được**.
- **`bieumau_bctc_hopnhat.pdf`** (55 trang, 45 trang bảng, 759 hàng) — header trải NHIỀU DÒNG thật
  (xem phân tích chi tiết ở §3.4), KHÔNG có cột đếm liên tục toàn bảng (không checksum được bằng
  STT, chỉ tự kiểm được ở mức khác nếu cần).

**Không tìm thấy** file "bảng thuế XNK, STT 1..210" mà spec gốc đo (`/d/Documents/luat-
thuexuatnhapkhau.pdf` chỉ là văn bản luật 25 trang, không phải bảng biểu thuế suất) — file gốc
dùng cho phép đo đó không còn trong kho truy cập được. Cổng checksum-STT của B4 nghiệm thu trên
`ssc_bieumau.pdf` thay thế, và số liệu "70/195 mã sai nằm kề" của spec gốc coi là **đường cơ sở
lịch sử tham khảo**, không phải mục tiêu đo lại chính xác (không còn file để đo lại chính xác).

## 3. Kiến trúc trích xuất

### 3.1 Nguyên tắc "chỉ chạm trang có bảng"

`parse_pdf` giữ NGUYÊN đường `pypdf` hiện tại làm mặc định cho MỌI trang. Với từng trang, chạy
THÊM `page.find_tables()` (chế độ mặc định) của `pdfplumber` để hỏi "trang này có bảng không".

- **Trang KHÔNG có bảng**: không đổi gì — dòng, furniture-detection, `heading_level()` chạy y hệt
  hôm nay. Đây là gate an toàn quan trọng nhất của B4: **683/683 trang PDF luật hiện có (đã xác
  nhận 0 bảng trong KH1) phải cho output BYTE-IDENTICAL với trước B4** — vì không văn bản luật nào
  hiện có trong corpus chứa bảng, phép thử này chứng minh B4 không đụng vào đường xử lý văn bản
  luật đang chạy tốt.
- **Trang CÓ ≥1 bảng**: thay `pypdf.extract_text()` của riêng trang đó bằng đường xử lý mới ở
  §3.2. Trang khác trong cùng tài liệu không bị ảnh hưởng.

### 3.2 Xử lý một trang có bảng — chia dải theo chiều dọc

Với N bảng trên trang (sắp theo toạ độ `top` tăng dần), chia trang thành N+1 "dải" theo chiều dọc:
dải trước bảng 1, dải giữa bảng i và i+1, dải sau bảng N. Mỗi dải cắt bằng `page.crop((0, y0, page
width, y1))` rồi `.extract_text()` — text của dải này chạy qua ĐÚNG pipeline dòng/furniture/
`heading_level()` hiện tại (không viết lại logic đó). Ghép theo thứ tự: dải 0 → hàng bảng 1
(§3.3) → dải 1 → hàng bảng 2 → ... → dải N. Đây là cách bảo toàn "văn xuôi trước/sau bảng vẫn đúng
thứ tự đọc" mà không cần suy luận layout phức tạp hơn.

Furniture-detection (`detect_page_furniture`, chạy trên TOÀN TÀI LIỆU trước khi dựng block) nhận
đầu vào là dòng của TỪNG DẢI trên trang có bảng (không phải dòng thô `pypdf` của cả trang) — để
header/footer lặp lại trên nhiều trang bảng vẫn bị nhận diện như hôm nay.

### 3.3 Gộp hai chế độ `pdfplumber` cho một bảng

Với một bảng, trích bằng CẢ HAI chế độ (mặc định + `horizontal_strategy="text"`), đối chiếu theo
**số thứ tự hàng thấy được, có neo bằng nội dung cột đầu không rỗng** (không đối chiếu bằng chỉ số
vị trí thuần vì chế độ mặc định có thể thiếu hàng ở giữa danh sách, làm lệch chỉ số):

- Hàng có mặt ở **cả hai** chế độ → dùng nội dung từ chế độ **mặc định** (ô đầy đủ hơn — đo được
  đây là chế độ ít ô rỗng hơn khi cả hai cùng thấy hàng).
- Hàng **chỉ chế độ `text` thấy** (hàng vắt qua ngắt trang mà mặc định làm mất) → dùng nội dung từ
  `text`, dù có thể thiếu ô mô tả. Còn hơn mất cả hàng — "hỏng lớn tiếng còn hơn thiếu âm thầm".
  Hàng này được đánh dấu nội bộ `nguon="text_fallback"` để phục vụ chẩn đoán khi cần, không lộ ra
  ngoài schema DB (không có cột mới).
- Hàng chỉ chế độ mặc định thấy (chế độ `text` bỏ sót) → hiếm nhưng xử lý đối xứng: vẫn giữ, dùng
  nội dung mặc định.

Không đối chiếu chéo giữa các bảng khác nhau hoặc khác trang.

### 3.4 Dò khối header nhiều dòng — TÁI DÙNG `is_column_index_row`, không viết lại

Khảo sát thêm 2026-09-04 (4 bảng thật, `bieumau_bctc_hopnhat.pdf` trang 1/21 + `invoice_*.pdf`)
cho thấy header bảng PDF **không phải luôn 1 dòng**:

```
['', '', 'Thuyết', 'Số cuối', 'Số đầu']        ← dòng nhãn phụ (Thuyết minh/Số cuối/Số đầu)
['TÀI SẢN', 'Mã số', None, None, None]         ← dòng nhãn chính
[None, None, 'minh', 'năm (3)', 'năm (3)']     ← tiếp dòng nhãn phụ (Word/PDF ngắt dòng giữa chữ)
['', '', None, None, None]                     ← dòng đệm rỗng
['1', '2', '3', '4', '5']                      ← HÀNG ĐÁNH SỐ CỘT — bẫy giống hệt KH2
```

Hàng cuối (`['1','2','3','4','5']`) là đúng lớp lỗi `xlsx_header.py` đã đóng ở Kế hoạch 2: một hàng
CHỈ đánh số thứ tự cột, trông "đủ ô" như hàng dữ liệu thật nhưng KHÔNG BAO GIỜ là dữ liệu. **Không
viết lại predicate này** — tái dùng thẳng `is_column_index_row(row: list)` từ
`backend/src/rag/xlsx_header.py` (chữ ký nhận `list` giá trị ô bất kỳ, không ràng buộc kiểu
openpyxl; đã tự chứng minh đúng trên 81 sheet thật ở KH2). Viết lại một bản riêng cho PDF sẽ tái
lặp đúng cặp lỗi "hai predicate gần giống hệt" đã gây hồi quy thật ở KH2 vòng sửa 2 — nguyên tắc đã
nêu trong thiết kế OCR: không đóng băng một phỏng đoán cấu trúc thành logic riêng lặp lại.

**Quy tắc khối header** — duyệt hàng từ trên xuống, mỗi hàng kiểm theo THỨ TỰ ưu tiên (rơi vào
nhánh nào dừng ở đó, không kiểm nhánh sau):

1. Khớp `is_column_index_row(row)` → **header** (bỏ qua, không phát block). Kiểm TRƯỚC nhánh 3 —
   hàng `['1','2','3','4','5']` cũng có ô số thuần nhưng phải dừng ở đây, không rơi xuống nhánh 3.
2. Số ô rỗng/`None` chiếm đa số (>50%) → **header** (dòng đệm/nhãn phụ thưa).
3. Có ô không rỗng khớp mẫu **số liệu thuần** (`^[\d][\d.,]*[\d]$|^\d$` — toàn chữ số và dấu phân
   cách nghìn/thập phân, KHÔNG lẫn chữ, phân biệt với nhãn kiểu `"năm (3)"` có chữ) → **THÂN bảng
   bắt đầu từ đây** — dừng gom header, dòng này và mọi dòng sau (kể cả dòng không khớp nhánh nào)
   đều là dữ liệu.
4. Không khớp nhánh nào ở trên (toàn chữ, không rỗng đa số, không phải index-row — vd
   `['', '', 'Thuyết', 'Số cuối', 'Số đầu']`, 2/5 rỗng nên không qua nhánh 2, không có ô số nên
   không qua nhánh 3) → **VẪN header** — nhãn cột chưa chắc bắt đầu dữ liệu, không có tín hiệu nào
   nói đây là dữ liệu thì mặc định coi là nhãn còn hơn phát một hàng dữ liệu rỗng-toàn-nhãn giả.

Nhánh 4 là điểm dễ đọc sai nhất: đừng hiểu "không khớp quy tắc nào" thành "vậy là THÂN" — chỉ
NHÁNH 3 (có tín hiệu số liệu thật) mới chuyển sang THÂN; mọi hàng khác mặc định vẫn là header cho
tới khi gặp nhánh 3.

**Chốt an toàn bắt buộc**: nếu duyệt hết bảng mà KHÔNG hàng nào từng khớp nhánh 3 (toàn bộ hàng bị
gom vào header, 0 hàng thân) — bảng toàn chữ, không có ô số liệu thuần nào để làm tín hiệu — đây là
dấu hiệu quy tắc trên KHÔNG áp dụng được cho bảng này, KHÔNG ĐƯỢC để bảng biến mất khỏi corpus. Xử
lý dự phòng: coi CHỈ dòng đầu tiên là header, mọi dòng còn lại là thân (dù không có tín hiệu số),
và sinh một `Warning` (§3.6) `"bảng không có tín hiệu số liệu — dùng dòng đầu làm header theo mặc
định"`. Mất nhãn cột chính xác còn hơn mất cả bảng.

Đây là **giả thuyết đầu, chưa đo trên toàn corpus** — đúng tinh thần "phép đo dẫn tới ruling có hệ
quả sản xuất phải chỉ định sẵn độ chi tiết cần thiết ngay trong bước đo" (bài học B3): kế hoạch thi
hành PHẢI có bước đo thật quy tắc này trên `bieumau_bctc_hopnhat.pdf` (45 trang bảng, nhiều biến
thể header) trước khi coi là xong, tương tự cách KH2 đo `xlsx_header.py` qua 2 vòng thay vì tin
trực giác ban đầu.

Tên cột cuối cùng: nối các ô KHÔNG rỗng của mọi dòng header (theo cột, theo thứ tự dòng) bằng
khoảng trắng — ví dụ cột 1 của bảng trên: `"TÀI SẢN"` (chỉ dòng 2 có chữ ở cột này); cột 3:
`"Thuyết minh"` (ghép dòng 1 + dòng 3). Cột không có ô nào không rỗng trong toàn khối header dùng
tên vị trí (`"Cột 3"`).

**Giới hạn đã biết, chấp nhận cho vòng 1**: bảng vỡ ngang trang (`pdfplumber` không nối bảng qua
trang — trang 21 của `bieumau_bctc_hopnhat.pdf` có một "bảng" chỉ 1 dòng `['Cộng', ...]`, rõ ràng
là phần tiếp của bảng trang trước) sẽ không có khối header nào để dò (không dòng nào khớp quy tắc
header ở trên vì bảng bắt đầu thẳng bằng dữ liệu) → toàn bộ dòng của "bảng" đó bị coi là THÂN,
dùng tên cột vị trí (`"Cột 1"`, `"Cột 2"`...) thay vì tên cột thật. Không sai dữ liệu (giá trị vẫn
đúng, tự đủ nghĩa vẫn giữ), chỉ mất tên cột — trạng thái AN TOÀN CÓ SUY GIẢM, không phải lỗi im
lặng. Ghép bảng vỡ trang triệt để là việc round sau nếu đo thấy cần.

Header cột đã dò được giữ làm danh sách tên cột. Mỗi hàng THÂN bảng thành MỘT block văn bản dạng:

```
"<Tên cột 1>: <giá trị 1> | <Tên cột 2>: <giá trị 2> | ..."
```

(khác `_bang_thanh_text` của `.docx` — nối `"|"` KHÔNG nhắc tên cột, vì đó là 1 block/CẢ bảng nên
header đứng riêng dòng đầu đã đủ ngữ cảnh cho người đọc cả khối; PDF giờ là 1 block/HÀNG nên mỗi
hàng phải tự mang tên cột để tự đủ nghĩa khi đứng riêng.) Cột có tên rỗng (ô header gộp không đọc
được) dùng chỉ số cột (`"Cột 3: ..."`) — không bỏ ô, không đoán tên.

Mỗi block này có `heading_level=None`, `page=<số trang>`, và cờ `atomic=True` (xem §3.5).

### 3.5 `chunking.py` — chunk nguyên tử, không gộp lẫn văn xuôi

`chunk_text_blocks` (dùng chung bởi `.docx`/`.pptx`/`.pdf`) hiện gom mọi block cùng mục vào
`cur_body: list[str]` rồi `_flush()` nối phẳng bằng `" ".join(body)` trước khi cắt cửa sổ theo câu
— đúng chỗ làm phẳng cấu trúc hàng đã nêu ở §1. Thêm khoá `atomic: bool = False` (mặc định) vào
block dict; `.docx`/`.pptx` KHÔNG đặt khoá này (giữ nguyên hành vi hôm nay — một bảng vẫn một
block, vẫn qua `" ".join` + cắt câu như cũ, KHÔNG đổi gì cho hai định dạng đó).

Khi build `sections` (vòng lặp `for b in blocks` hiện có), thay vì gom TẤT CẢ body-block của một
mục vào một `list[str]` phẳng, tách thành các **run**: một run văn xuôi liên tục (block không
`atomic`) hoặc một block `atomic` đứng riêng. Khi phát chunk (vòng lặp `for section_path, page,
body in sections`), xử lý theo run:

- Run văn xuôi → giữ nguyên logic hiện tại (`" ".join` + `_split_section_text` nếu vượt
  `MIN_CHUNK_TOKENS`).
- Block `atomic` → LUÔN phát thành đúng MỘT chunk riêng, KHÔNG qua `_split_section_text`, KHÔNG
  gộp với run liền kề dù cộng dồn token vẫn dưới `CHUNK_SIZE_TOKENS`. Nếu bản thân một hàng vượt
  `CHUNK_SIZE_TOKENS` (hiếm — hàng có ô văn bản dài) vẫn phát nguyên hàng thành 1 chunk, không cắt
  giữa hàng — ranh giới chunk không được phép tách số khỏi mã của nó (yêu cầu cứng của spec gốc
  §5.4), chấp nhận vượt ngân sách token trong ca hiếm này, GHI CHÚ lại trong ghi chú thực thi,
  không âm thầm.

### 3.6 Checksum cột đếm liên tục + báo cáo qua Tầng A

Sau khi gộp một bảng (§3.3), nếu cột đầu tiên toàn số nguyên tăng dần đều (cho phép mốc bắt đầu
khác 1), kiểm tra dãy có đứt đoạn. Đứt đoạn → sinh cảnh báo theo ĐÚNG khuôn đã lập ở Kế hoạch 2
(`parse_xlsx` trả `(sheets, sheet_warnings)`, `sheet_warnings: list[tuple[str, str]]`):
đổi chữ ký `parse_pdf` thành trả `(blocks, warnings)`. `_chunks_for` (`ingest.py:78-106`) hiện
hard-code `return (..., [])` cho nhánh `.pdf` — sửa để `unpack` cặp `(blocks, pdf_warnings)` từ
`parse_pdf` giống hệt nhánh `xlsx` đã làm, để `pdf_warnings` chảy tiếp vào `report.warnings` qua
`Warning(origin, where, reason)` đã có sẵn ở `ingest.py:191-193`. `where` mang dạng
`"trang <n>, bảng <k>"`. KHÔNG phát minh cơ chế báo cáo mới.

Bảng không có cột đếm liên tục nhận diện được (đa số — `bieumau_bctc_hopnhat.pdf` không có) thì
không sinh cảnh báo checksum — im lặng ĐÚNG, không phải lỗ hổng (không có gì để kiểm).

## 4. Phụ thuộc

Khai `pdfplumber` vào `requirements.txt` (đã cài "chui" trong `.venv`, phiên bản đo được
`0.11.10` — ghim đúng số này, `pypdfium2` đã đi kèm sẵn như một dependency của `pdfplumber`).

## 5. Phạm vi KHÔNG làm

- PDF không có lớp text (scan) — thuộc tầng OCR (B5), đã thiết kế riêng, gọi TỰ ĐỘNG trước khi
  `parse_pdf` nhận thấy trang rỗng, không phải việc của B4.
- Không đụng `heading_level()`, không đụng furniture-detection logic, không đụng đường xử lý
  `.docx`/`.pptx`/`.xlsx` (`chunk_text_blocks` chỉ thêm một khoá tuỳ chọn mặc định tắt, hành vi cũ
  giữ nguyên cho mọi caller không đặt `atomic=True`).
- Không dựng lại "bảng thuế XNK 210 hàng" của spec gốc (file không còn) — dùng `ssc_bieumau.pdf`
  thay thế cho cổng checksum.

## 6. Nghiệm thu (Tầng C)

| bộ | đáp án lấy từ đâu | quy mô |
|---|---|---|
| 100 `invoice_*.pdf` | tự kiểm số học (SL×đơn giá=thành tiền; +thuế=tổng; Σdòng=SUMMARY) | 855 hàng dự kiến, 0 ô gán tay |
| `ssc_bieumau.pdf` | cột `TT` liên tục 1..N — đứt đoạn phải sinh `Warning` | 53 hàng, 8 trang |
| `bieumau_bctc_hopnhat.pdf` | không có checksum số — nghiệm thu bằng **không chunk nào lẫn số của hàng khác** (mỗi chunk-hàng chỉ chứa đúng 1 mã số cột đầu, kiểm bằng regex trên `chunk_text`) | 759 hàng dự kiến, một phần mang tên cột vị trí do bảng vỡ trang (§3.4, chấp nhận) |
| 683 trang PDF luật hiện có | **byte-identical** blocks trước/sau B4 (không trang nào có bảng) | phép thử phá bắt buộc: gỡ gate "chỉ chạm trang có bảng" ra, test phải đỏ |

Mỗi cổng kèm phép thử phá: gỡ bản sửa ra thì cổng phải đỏ — nguyên tắc lặp lại xuyên suốt dự án
này.
