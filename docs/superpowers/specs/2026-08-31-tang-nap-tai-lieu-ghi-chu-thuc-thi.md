# Tầng nạp tài liệu — ghi chú thực thi kế hoạch 1

**Ngày**: 2026-08-31. **Nhánh**: `worktree-tang-nap-tai-lieu-1`.
**Spec**: `2026-08-29-tang-nap-tai-lieu.md` · **Kế hoạch**: `plans/2026-08-30-tang-nap-tai-lieu-1-to-tieng.md`

Ghi lại khó khăn, hướng đã chọn, và giới hạn còn lại — kể cả những giả thuyết đã bị số đo bác bỏ.

## 1. Kết quả

| | trước | sau |
|---|---|---|
| test suite mặc định | 2215 | **2256** |
| nghiệm thu kho thật 117 tệp | `.doc`/`.xlsm` biến mất im lặng | **117/117 nạp được, 0 im lặng** |
| định dạng nạp được | pdf, docx, xlsx | + **xlsm, xltx, pptx**, + doc/xls/ppt/rtf/odt/ods/odp qua LibreOffice |

## 2. Khó khăn đã gặp

### 2.1 Worktree thiếu hai thứ không theo git

Baseline đầu tiên trong worktree cho **21 failed + 65 errors**. Không phải code hỏng:

| thiếu | triệu chứng | cách xử |
|---|---|---|
| `backend/.venv` | không chạy được test | dùng interpreter của cây chính với cwd trong worktree; **đã chứng minh** nó nạp đúng mã worktree bằng `module.__file__` |
| `.env` (gitignore) | `KeyError: 'ODOO_URL'` | chép `.env` và `backend/.env` sang; cả hai vẫn gitignore ở đích |

Ký ức dự án ghi lần merge trước **thất bại đúng vì "test xanh giả do worktree không có .venv"**. Lần này baseline đỏ trước, truy nguyên nhân, rồi mới tuyên bố sạch.

### 2.2 Ba mã thoát nói dối trong một đợt cài phụ thuộc

Cài LibreOffice hỏng ba lần trước khi được:

| lần | cách | kết quả |
|---|---|---|
| 1 | `winget` | treo 27 phút chờ UAC, **1,0 giây CPU** — không tải gì; tiến trình nền vẫn báo "hoàn tất mã 0" |
| 2 | `scoop` | tải 33/357 MB rồi đứt, **thoát mã 0** |
| 3 | `curl` từ mirror chính thức | 116/357 MB ở **~16 KB/s**, băm không khớp |
| 4 | `curl` từ `ftp.acc.umu.se` | **25,9 MB/s**, xong ~10 giây, băm khớp |

Rồi bung MSI báo `Failed to extract files`, mã **1603**, log rỗng, `scoop list` ghi "Install failed" — **nhưng đã bung đủ 19.417 tệp, 1,6 GB, và `soffice.exe` chạy được**. Mã thoát nói dối theo **cả hai chiều** trong cùng một đợt.

`download.documentfoundation.org` đo được **13 KB/s**, mirror Thuỵ Điển **1675 KB/s** ở phép thử — chênh hơn hai bậc độ lớn. Ai cài lại nên trỏ thẳng mirror.

Bài học này đi thẳng vào thiết kế: `_run_soffice` **cố ý không đọc mã thoát**, chỉ kiểm sự tồn tại của tệp đầu ra.

### 2.3 Sổ ghi tiến trình bị chia đôi

Mục Task 1–2 ghi nhầm vào `backend/.superpowers/...` vì lúc đó cwd là `backend/` và dùng đường dẫn tương đối. Sổ chính thiếu hẳn hai task đầu — đúng thứ sổ sinh ra để chống. Đã gộp và xoá bản lạc. **Đường dẫn sổ phải tuyệt đối.**

## 3. Giả thuyết bị số đo bác bỏ

- **"OCR sẽ chữa được lỗi bảng"** — sai. 683/683 trang PDF luật và 100/100 hoá đơn **đều có lớp text**. Bệnh là cấu trúc bảng, không phải nhận dạng chữ.
- **"Cần Docling"** — không cần. `pdfplumber` (2 MB, không model, không GPU) giải đúng 8/8 mã đối chiếu. Docling chưa từng được thử; nó **không** bị kết luận là kém, chỉ là không còn gì phải chứng minh cho tài liệu hiện có.
- **"Đáp án đúng chưa bao giờ có trong ngữ cảnh"** — sai, tôi khái quát từ 3 mẫu. Đo đủ 198 mã: chỉ **3/198 (1,5%)** vắng mặt hoàn toàn. Bệnh thật là **gắn sai** (70/195).
- **"EasyOCR là lựa chọn hiển nhiên vì đã có torch+CUDA"** — sai. `--dry-run` cho thấy nó **đè `torch 2.11.0+cu128` thành `2.13.0`**, gần như chắc giết reranker GPU. Chuyển sang Tesseract + `pytesseract`: đúng một gói pip, không đụng cây phụ thuộc.
- **"`source_file` chỉ dùng để hiển thị nhãn nên trỏ vào bản đã chuyển cũng được"** — **sai, và đây là sai lầm đắt nhất của đợt.** Nó chảy `source_file` → `doc_title` → `section_path` → `index_text()` → **thẳng vào vector embedding**. Tôi lập luận mà không truy dòng dữ liệu. Chỉ review toàn nhánh mới bắt được.

## 4. Lớp lỗi tái phát: "cổng trông như đang gác nhưng không đo gì"

Xuất hiện **tám lần** trong một đợt. Tất cả đều bị bắt, và mỗi lần đều bằng **đột biến** chứ không bằng đọc code:

| # | chỗ | bằng chứng |
|---|---|---|
| 1 | phép thử phá Task 3 do kế hoạch quy định | test monkeypatch trọn `_run_soffice` nên đột biến trong thân hàm không thể làm nó đỏ |
| 2 | đường chuyển đổi **thành công** | đổi `doc_id_source=path` → `=converted`, 86 test vẫn xanh |
| 3 | bảng trong group shape | reviewer dựng slide thật: group có `has_table=False`, `has_text_frame=False` → mất im lặng |
| 4 | `pytest.importorskip("pptx")` | gỡ `python-pptx` → tính năng chết trọn, suite **vẫn xanh, mã thoát 0** |
| 5 | `set(_EXT) <= DOCUMENT_EXT` | tautological (`DOCUMENT_EXT = frozenset(_EXT) \| {...}`); thêm `.epub` vào `_EXT` → vẫn xanh |
| 6 | `target in _EXT or in DOCUMENT_EXT` | vế `or` nuốt vế đầu; đổi đích `.rtf` sang `odt` → vẫn xanh |
| 7 | cạnh gác chống trùng tiêu đề slide | `s.shapes.title is s.shapes.title` → **False**; `shape is title_shape` không bao giờ đúng |
| 8 | `_pptx_xml_text` | thay thân hàm bằng `""` → suite xanh hoàn toàn |

**Kết luận rút ra:** một cổng chỉ đáng tin sau khi đã thấy nó **đỏ**. Đọc code không thay thế được đột biến. Bốn trong tám lần nằm trong văn bản kế hoạch do controller viết, không phải trong việc thực thi.

## 5. Hướng đã chọn, và vì sao

| quyết định | vì sao |
|---|---|
| Tách `DOCUMENT_EXT` khỏi `_EXT` | `.doc` và `.gitkeep` trước đây chung một rọ. Một cái là rác thư mục, cái kia là quy chế công ty biến mất. |
| Bỏ chữ `skipped`, dùng `unchanged` | `skipped` mang hai nghĩa ("không đổi nên bỏ" và "không hiểu nên bỏ"); chính sự mơ hồ đó là chỗ lỗi nấp. |
| `_run_soffice` không đọc mã thoát | Ba mã thoát nói dối trong một đợt cài, xem 2.2. |
| Ghi tạm rồi đổi tên nguyên tử vào cache | Tệp cụt do timeout ở lại thì **bẩn vĩnh viễn** — khoá cache là hash tệp gốc nên không bao giờ tự lành. |
| Lá chắn quanh vòng lặp nạp, **trừ** `EmbeddingError` | Nuốt nó sẽ biến "Ollama không chạy" thành "117 tài liệu bị từ chối" — đổ lỗi cho tài liệu người dùng. |
| Không đưa `pdfplumber`/`pytesseract` vào requirements | Chưa dòng code nào dùng. Khai phụ thuộc chưa ai dùng là lớp lỗi "danh sách lệch khỏi sự thật" theo chiều ngược. |

## 6. Giới hạn còn lại

### Đã biết vị trí và cách sửa, chưa làm

| # | chỗ | mức |
|---|---|---|
| 1 | `parse.py` — tiêu đề slide vào corpus **hai lần**; sửa bằng so `_element` thay vì `is`. Tác động hôm nay = 0 vì kho thật chưa có `.pptx` nào | Important |
| 2 | `tests/mcp/test_khong_ro_loi_exception.py` — chú thích miễn trừ khẳng định "không module runtime nào import ingest", **sai**: `retrieve.py` import `segment_vi`. Kết luận vẫn đúng, câu chữ sai | Important |
| 3 | Lá chắn nuốt **lỗi DB**: Postgres chết giữa lượt nay thành 117 dòng `rejected` với lý do giả, thay vì một tiếng nổ | Important |
| 4 | Ranh giới `EmbeddingError` chỉ đúng với Ollama; `GeminiEmbedder` **cố ý** không bọc lỗi nên bật Gemini là lá chắn rò trọn | Important tiềm ẩn |
| 5 | `_pptx_xml_text` không test nào chạy qua thân hàm | nhẹ |

### Chưa chạm tới (thuộc kế hoạch sau)

- **Excel dò hàng tiêu đề** — 0/81 sheet đúng trên sổ kế toán thật
- **Word suy phân cấp từ chữ** — 377/377 block `heading_level=None`, `section_path` thành đường dẫn tệp
- **PDF bóc bảng** — 70/195 mã thuế có mức sai nằm kề
- **OCR** — Tesseract + `vie` đã cài và đo (recall 0,865 @ PSM 6, 200 DPI) nhưng chưa nối vào đường nạp

### Nợ triển khai

`TESSDATA_PREFIX` (`C:\Users\ADMIN\.tessdata`, vì `Program Files` cần admin) và đường dẫn `soffice.exe` đều là **đường dẫn máy cá nhân**. `convert.soffice_path()` đọc env → PATH → vài vị trí quen thuộc, nên máy khác vẫn chạy được, nhưng **kho `tmp-docs/` và cả hai binary đều không có sẵn ở nơi khác**.

### Nội dung vẫn chưa lấy được

- SmartArt trong slide: chỉ sinh **dấu vết**, nội dung chưa vào corpus. Có chủ ý — python-pptx không dựng được SmartArt nên không có fixture tầng 1, và viết bộ đọc `dgm:relIds` mà không ai chạy qua chính là lớp lỗi mục 4.
- Bảng trong slide dưới dạng **ảnh**: đó là ca OCR, không phải ca bóc bảng.

---

# Tầng nạp tài liệu — ghi chú thực thi kế hoạch 2

**Ngày**: 2026-09-03. **Nhánh**: `worktree-tang-nap-tai-lieu-1`.
**Spec**: `2026-08-29-tang-nap-tai-lieu.md` mục 4 + 5.2 · **Kế hoạch**: `plans/2026-08-31-tang-nap-tai-lieu-2-excel-header.md`
**Ledger**: `.superpowers/sdd/2026-08-31-tang-nap-tai-lieu-2-excel-header/progress.md`

Ghi lại khó khăn, hướng đã chọn, và giới hạn còn lại của đợt B2 (Excel dò hàng tiêu đề) — kể cả những giả thuyết đã bị số đo bác bỏ. Nối tiếp phần Kế hoạch 1 ở trên.

## 1. Kết quả

| | trước | sau |
|---|---|---|
| test suite mặc định | 2257 passed, 1 skipped | **2283 passed, 1 skipped, 74 deselected** |
| hàng tiêu đề đúng trên sổ kế toán thật | **0/81** sheet đúng (thước đo cũ: hàng đầu tiên có chữ) | **17 đúng / 0 sai / 6 cảnh báo an toàn** trên 23 sheet có đáp án thật |
| cảnh báo có tên trên 81 sheet thật | không phân biệt (đoán bừa, không cảnh báo) | 21/81 sheet sinh cảnh báo "không dò được" thay vì đoán bừa |

Cổng nghiệm thu chính là `sai == 0` trên 23 sheet có đáp án — ĐẠT, xác nhận độc lập ba lần: review Task 3, re-review Task 3, và review toàn nhánh (reviewer tự chạy lại, tự đo ra đúng 17/0/6, không chỉ tin báo cáo).

## 2. Khó khăn đã gặp

### 2.1 Bảng hiệu chỉnh SCAN_LIMIT × MIN_SCORE (định ở Task 2 Step 3, thực đo ở Task 3 Step 5)

Kế hoạch định hiệu chỉnh hai hằng số này ngay ở Task 2 Step 3, nhưng phép đo cần dữ liệu ĐÃ TRẢI Ô GỘP — việc trải nằm ở Task 3. Đo trên lưới chưa trải là đo trên dữ liệu sai hình dạng (hàng header cha trông thưa hơn thực tế, lệch điểm `contiguity`). Phát hiện khi rà kế hoạch, sửa TRƯỚC khi chạy: hiệu chỉnh dời xuống Task 3 Step 5, dùng đúng `_spread_merged` mà sản phẩm dùng.

Lưới thô đầu tiên (giá trị tạm Task 2: `SCAN_LIMIT=15, MIN_SCORE=0.5`, công thức gốc + cổng `label_ratio==0`) đo trên 23 sheet có đáp án:

| scan_limit | min_score (0.3–0.8, mọi giá trị) | đúng | sai | None |
|---|---|---|---|---|
| 15 | bất kỳ | 4 | 19 | 0 |
| 20 | bất kỳ | 4 | 19 | 0 |
| 10 | 0.3–0.7 | 3 | 20 | 0 |
| 25/30/35/40 | bất kỳ | 2 | 21 | 0 |

`SCAN_LIMIT` gần như không đổi kết quả — 17/19 ca sai là "bị đánh bại trong cửa sổ quét" (hàng đúng NẰM TRONG phạm vi quét nhưng một hàng khác, thường là hàng đánh số cột `(1)/(2)/(3)`, đạt điểm bằng hoặc cao hơn). Quét mịn `MIN_SCORE` ở `scan_limit=15`:

| min_score | đúng | sai | None |
|---|---|---|---|
| 0.5 – 0.85 | 4 | 19 | 0 |
| 0.9 | 4 | 15 | 4 |
| 0.92 | 4 | 12 | 7 |
| 0.95 | 4 | 11 | 8 |
| 0.96 – 0.964 | 4 | 11 | 8 |
| 0.965 – 1.0 | 3 | 11 | 9 |

Chốt lần đầu: `SCAN_LIMIT=15, MIN_SCORE=0.95` → đúng=4 sai=11 None=8 — sai giảm 42% (19→11) mà không mất ca đúng nào, nhưng CHƯA đạt mục tiêu 20/23. Hai hằng số một mình không đủ; công thức `_score_row` cần sửa — mở đường cho hai vòng sửa ở mục 2.2.

### 2.2 Hai vòng sửa của Task 3: đúng 4→6→17, sai 19→11→0

**Vòng sửa 1 (2026-08-31):** chủ dự án tự đo lại, xác nhận chẩn đoán "hàng đánh số cột" đúng, và tìm thêm nguyên nhân thứ hai: **biểu mẫu trống bị `data_ratio=0` phạt oan**. `DM KH`/`DM NCC`/`DMHH` có hàng tiêu đề HOÀN HẢO nhưng mọi hàng dưới đều rỗng → `data_ratio=0` → điểm sụp — trong khi biểu mẫu trống là dạng phổ biến NHẤT của kế toán VN. Ruling: sửa CÔNG THỨC, không chỉ nới ngưỡng. Ba cơ chế: (a) nhận diện + loại hẳn hàng đánh số cột (`is_column_index_row`), (b) hàng đánh số cột NGAY DƯỚI làm bằng chứng dương (`_COLUMN_INDEX_BONUS`), (c) `data_ratio` TRUNG TÍNH khi mọi hàng dưới đều rỗng (bỏ hẳn thành phần, chuẩn hoá lại hai trọng số còn lại) thay vì nhân 0. Kết quả: đúng=6, sai=11, None=6 (`MIN_SCORE` nâng lên 0.99). Vẫn dưới mục tiêu — implementer DỪNG đúng chỉ đạo thay vì tinh chỉnh tiếp.

Ngay sau đó, chủ dự án tự đo lại và phát hiện **chính đáp án 23-sheet SAI** — xem mục 3. Con số thật của baseline trước vòng sửa 2 là 10 đúng/7 sai/6 None, không phải 6/11/6.

**Vòng sửa 2 (2026-09-03):** bốn cơ chế mới, xử lý 3 nhóm nguyên nhân còn lại (hàng đánh số cột LẪN nhãn tháng thật với tỉ lệ dưới 50%; mục La Mã/chữ đơn ngắn tự tin đạt điểm tuyệt đối; header lặp lại/đa bảng):
- `_index_symbol_run` — chuỗi ≥3 ô LIỀN KỀ, PHÂN BIỆT, đều là ký hiệu cột thì cả hàng bị loại, BẤT KỂ tỉ lệ toàn hàng.
- đếm GIÁ TRỊ PHÂN BIỆT thay vì đếm Ô trong `is_column_index_row` — tránh hàng dữ liệu đầy số lặp (`0|0|0`) bị nhận nhầm.
- `_column_alignment` — cổng KHỚP CỘT giữa hàng ứng viên và thân bảng dưới nó (tín hiệu kết cấu mà `label_ratio`/`contiguity` không có).
- `_distinct_groups(row) < 2` áp cho cả `_score_row` (không chỉ `is_parent_header` như Task 3 gốc) — loại dòng tiêu đề/chú thích tài liệu (một ô gộp phủ hết bề rộng).
- `_has_wider_rival_table` — sheet `DV` xếp chồng nhiều bảng; cổng đòi bảng đối thủ RỘNG GẤP `_RIVAL_WIDTH_FACTOR` lần mới trả None, tránh giết oan 5 sheet có header lặp lại hợp lệ (in nhiều trang).

Một bản nháp uncommitted từ phiên trước được tìm thấy giữa chừng, xử lý theo ruling "giả thuyết chưa kiểm chứng, không phải bản đã duyệt" (chi tiết mục 3). Kết quả vòng sửa 2: **đúng=17, sai=0, None=6** — cổng chính ĐẠT. Suite 2275→2280.

Review độc lập tìm thêm 2 Important: đính chính báo cáo + một hồi quy thật (`BHBB`, `Data2` — xem mục 3), và một lớp lỗi mới trong `_index_symbol_run` (nhánh lỏng `isinstance` khiến nhãn năm dạng số bị chấm 0 điểm oan — xem mục 5). Fix round riêng (2026-09-03) đóng cả hai, không đổi con số 17/0/6 trên 23 sheet. Suite 2280→2281.

### 2.3 Sự cố sổ ghi lặp lại (lần 2)

Đúng bài học đã ghi ở ghi chú Kế hoạch 1 (mục 2.3 ở trên) — và chính người ghi ký ức đó lại không áp dụng nó lần này: cwd bị đổi sang `backend/` giữa phiên (subagent), ghi sổ bằng đường dẫn TƯƠNG ĐỐI khiến một đoạn ghi hụt lần thứ hai. Từ đó dùng đường dẫn TUYỆT ĐỐI cho mọi thao tác sổ trong suốt phần còn lại của B2.

### 2.4 Test nghiệm thu của chính Task 5 có lỗ hổng phân loại

Task 5 (nghiệm thu trên 81 sheet thật) đo ra `dung=17, sai=6, canh_bao=21` — BLOCKED. Điều tra READ-ONLY (không sửa `xlsx_header.py`/ngưỡng/logic test) xác định: 6 sheet "sai" trùng TUYỆT ĐỐI với 6 sheet Task 3 đã báo `None`-an-toàn-có-cảnh-báo. Không phải hồi quy — code cho kết quả giống hệt Task 3. Lỗ hổng nằm ở CHÍNH code mẫu của brief: nó suy "sai" gián tiếp qua `co_stt_o_body` (còn ô STT gốc trong `rows` vì `parse_xlsx` không cắt `body` khi `find_header` trả None), không đọc trực tiếp `find_header`/`canh_bao`. Ruling A (mục 4) sửa logic phân loại của TEST, không đụng mã sản phẩm — đo lại: `dung=17, sai=0, canh_bao=21`, khớp CHÍNH XÁC dự đoán.

## 3. Giả thuyết bị số đo bác bỏ

- **"Đáp án 23-sheet 6/11/6 (hàng ĐẦU TIÊN chứa STT) đúng"** — SAI. Ô `STT` bị GỘP DỌC qua 2-3 hàng ở 8 sheet; sau khi trải ô gộp, MỌI hàng trong vùng gộp mang "STT". Đáp án đúng là hàng CUỐI vùng gộp (tầng lá). Con số thật: **10 đúng / 7 sai / 6 None**, không phải 6/11/6 — bộ dò vốn ĐÚNG HƠN thước đo ở 4 ca. Suýt bắt subagent chạy thêm nhiều vòng đuổi theo một oracle hỏng; dự án đã có tiền lệ đúng dạng này (regression truy về scoring artifact, không phải bug thật).
- **"Siết `MIN_SCORE` 0.92→0.96 đóng được `BHBB`/`Data2` mà không mất gì"** — SAI. Ở đúng điểm 0.9500000000 có CẢ hàng sai của `BHBB` LẪN hai hàng tiêu đề ĐÚNG (`SỔ CT VT-HH`, `PB CPMH`) — bằng điểm nhau tuyệt đối, không ngưỡng nào tách nổi. Đã THỬ THẬT (không chỉ suy luận), đo trên đủ 81 sheet chứ không chỉ 23 có đáp án: nâng lên 0.96 loại 2 ca sai nhưng giết 3 ca đúng, cảnh báo bật 21→27 — đổi 3 lấy 2, LỖ. RÚT LẠI, giữ 0.92.
- **"Bản nháp uncommitted của phiên trước dùng được nguyên"** — bác bỏ một phần: `SCAN_LIMIT=7/MIN_SCORE=0.96/MARGIN=0.0` đo ra CÓ HẠI (`MARGIN=0.0` là lệnh chết; `SCAN_LIMIT=7` không sửa gì, chỉ "bịt mắt" bộ dò — 4 sheet có header ở chỉ số 11-17 vĩnh viễn không dò được ở bất kỳ ngưỡng nào); chuỗi hoá số toàn cục đo ra VÔ TÁC DỤNG (kết quả giống hệt bật/tắt trên dải MIN_SCORE 0.88–0.96, bỏ theo YAGNI). Chỉ ý tưởng lõi (chuỗi ký hiệu liền kề) được giữ, và phải thêm ràng buộc PHÂN BIỆT mới đúng.
- **"Chuỗi hoá toàn cục cho mọi so khớp ký hiệu cột (không riêng `_index_symbol_run`)"** — bác bỏ bởi review độc lập: đo ra 2 sheet thật (`CĐTK`, `Thẻ giá thành DV`) RỜI KHỎI hàng tiêu đề đúng (4→3) — một hồi quy KHÁC. Phải tách `_looks_like_index_symbol` (bản chặt, chỉ dùng trong `_index_symbol_run`) khỏi `_looks_like_column_index` (giữ nguyên nhánh lỏng).
- **"Đối thủ nào đạt điểm tối đa cũng đủ để trả None (đa bảng)"** — bác bỏ: đo ra đúng 17→12, sai 1→0 — đổi 5 sheet đang đúng lấy đúng 1 ca, giá tồi (rất nhiều sheet lặp lại chính hàng tiêu đề của nó ở giữa thân — biểu mẫu in nhiều trang). Phải thêm điều kiện BỀ RỘNG (`_RIVAL_WIDTH_FACTOR`) để cổng chỉ kích hoạt đúng ca `DV`.
- **"`BẢNG SƠ ĐỒ`/`NHẬT KÝ CHUNG` là hồi quy MỚI của vòng sửa 2"** — SAI, tự nhận nhầm trong báo cáo đầu. Đo base↔head xác nhận CẢ HAI KHÔNG ĐỔI qua vòng sửa 2 — là nợ có sẵn TỪ TRƯỚC, đã đính chính ở fix round.

## 4. Hướng đã chọn, và vì sao

| quyết định | vì sao |
|---|---|
| `sai == 0` là cổng CHÍNH thay vì `đúng >= 20` | một tiêu đề SAI làm bẩn mọi chunk của sheet đó một cách ÂM THẦM; một `None` sinh cảnh báo CÓ TÊN mà người vận hành xử lý được. 81 sheet kế toán làm tay quá đa dạng (hoá đơn, chấm công, tờ khai thuế, sổ cái) để đòi một heuristic tổng quát đạt 87%. |
| Tách predicate lỏng/chặt (`_looks_like_column_index` / `_looks_like_index_symbol`) cho ký hiệu cột, thay vì chuỗi hoá toàn cục | đã ĐO chuỗi hoá toàn cục gây hồi quy khác (mục 3) — tách phạm vi giữ đúng tác dụng mong muốn (chuỗi liền kề) mà không lan tác dụng phụ sang nhánh cũ đã hiệu chỉnh cùng `_COLUMN_INDEX_BONUS`. |
| Chấp nhận `BHBB`/`Data2` tự tin sai, không siết `MIN_SCORE` thêm | ĐÃ THỬ 0.96 và đo ra LỖ trên đủ 81 sheet (mục 3) — đóng đúng cần CƠ CHẾ nhận diện văn xuôi (câu có dấu chấm cuối, nhiều từ), không phải một con số ngưỡng; để lại cho việc tương lai có đo đàng hoàng. |
| Test Task 5 dùng `canh_bao` để loại `None`-an-toàn khỏi bucket "sai" (Ruling A) | CHÍNH LÀ phương pháp Task 3 đã dùng để đóng cổng 17/0/6 qua 2 lượt review độc lập — dùng lại phép đo đã xác nhận, không phát minh cách đo mới giữa Task 5; bền hơn liệt kê tên sheet cứng (không vỡ khi corpus/ngưỡng đổi sau). |
| `SCAN_LIMIT` giữ 15 dù 18 cho đúng=18/sai=0 (tốt hơn) | 18 là một MŨI NHỌN đúng một điểm (19 sinh ca sai lại), chỉ vớt thêm ĐÚNG MỘT sheet đứng ngay cạnh vách đá; 15 nằm giữa cao nguyên phẳng 13-17 — ưu tiên độ bền hơn điểm số cao nhất đo được. |
| Dựng `compare_all.py` so TỪNG SHEET base↔head trên CẢ 81 sheet (không chỉ 23 có đáp án) | vòng sửa 2 ban đầu chỉ nhìn 23 sheet có đáp án — cách đó KHÔNG BAO GIỜ thấy được một sheet lặng lẽ đi từ `None` (an toàn) sang câu trả lời tự tin SAI; công cụ này bắt được cả hồi quy `BHBB` lẫn sai lầm 0.96 tự thử của chính implementer. |

## 5. Giới hạn còn lại

- **`BHBB`/`Data2` vẫn tự tin sai** — biết, đo, chấp nhận có lý do định lượng (mục 3), không phải phát hiện mới. Đóng đúng cần cơ chế nhận diện văn xuôi, chưa làm.
- **58/81 sheet thật chưa có đáp án đo được** (không có ô `STT`) — mọi con số `sai==0` chỉ có ý nghĩa trong phạm vi 23 sheet có đáp án.
- **Khe `MIN_SCORE` chỉ rộng 0,0115** (0,9135 – 0,9250) — điểm mỏng nhất của bộ hằng số hiện tại; bất kỳ thay đổi nào chạm `_score_row` sau này đều phải đo lại khe này.
- **`_RIVAL_WIDTH_FACTOR` hiệu chỉnh trên N=1** — chỉ sheet `DV` trong 23 sheet kích hoạt cổng đa bảng; dải phẳng [1,5–3,0] rộng nhưng vẫn là một mẫu duy nhất.
- **`DV` vẫn KHÔNG dò đúng**, chỉ lùi về `None` an toàn — khái niệm "nhiều bảng trong một sheet" chưa có thiết kế, cổng hiện tại chỉ là lời nhận-không-biết.
- **Nợ `isinstance(v, (int, float)) → True`** trong `_looks_like_column_index` (nhánh lỏng) — một hàng dữ liệu toàn số PHÂN BIỆT vẫn có thể bị tiêu chí tỉ lệ nhận nhầm là hàng đánh số cột; giữ có chủ đích (bỏ toàn cục làm 2 sheet thật rời hàng tiêu đề đúng), đã khoá bằng assert.
- **Khuyến nghị tái cấu trúc `_score_row` / gộp hai predicate `_looks_like_column_index`/`_looks_like_index_symbol`** — final review toàn nhánh tự đặt câu hỏi kiến trúc và tìm bằng chứng CỤ THỂ của "vá chồng vá": hai predicate gần giống hệt, khác biệt CHỈ nằm trong docstring chứ không nằm ở tên/chữ ký, và chính sự nhầm lẫn này đã gây MỘT hồi quy thật (nhãn năm dạng số bị chấm 0 điểm dứt khoát ở vòng sửa 2, đã fix ở fix round kế tiếp — mục 2.2). `_score_row` tích luỹ 5 cổng loại trừ tuần tự qua các vòng, if-chain đang phình. **ĐÃ PARK có chủ ý** ở fix wave này (không phải bỏ sót) — controller ruling: đây là quy trình CHỈ MỘT fix wave, một tái cấu trúc thật (không phải dòng an toàn) mà chỉ được đúng một lượt re-review scoped để bắt hồi quy là rủi ro không tương xứng, nhất là khi tệp này đã có tiền lệ hồi quy tinh vi từ refactor tưởng an toàn. Ghi lại làm khuyến nghị sẵn sàng thực thi khi có vòng sửa 3 (đo 58 sheet còn lại) hoặc lý do thật khác để chạm lại file — đây chính là điều mục "Sau khi xong kế hoạch này" của kế hoạch cần người thực thi việc tương lai biết trước khi bắt đầu.
