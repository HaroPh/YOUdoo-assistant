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

---

# Tầng nạp tài liệu — ghi chú thực thi kế hoạch 3

**Ngày**: 2026-09-04. **Nhánh**: `worktree-tang-nap-tai-lieu-1`.
**Spec**: `2026-09-04-b3-word-phan-cap-design.md` · **Kế hoạch**: `plans/2026-09-04-b3-word-phan-cap.md`
**Ledger**: `.superpowers/sdd/2026-09-04-b3-word-phan-cap/progress.md`

Ghi lại khó khăn, hướng đã chọn, và giới hạn còn lại của đợt B3 (Word suy phân cấp từ chữ) — kể cả
giả thuyết bị số đo bác bỏ. Nối tiếp phần Kế hoạch 1-2 ở trên. Sửa lỗi 3 trong bảng bốn lỗi của
`2026-08-29-tang-nap-tai-lieu.md` mục 5.3: `parse_docx` chỉ nhận tiêu đề qua style Word nên tài
liệu không dùng style (0/10 biểu mẫu BCTC thật) mất sạch breadcrumb, và tệ hơn — breadcrumb rỗng đó
từng lùi về ĐƯỜNG DẪN TỆP, nhúng thẳng vào vector embedding của mọi chunk.

## 1. Kết quả

| | trước | sau |
|---|---|---|
| test suite mặc định | 2283 passed, 1 skipped, 74 deselected | **2304 passed, 1 skipped, 76 deselected** |
| `b09-dn.docx` — chunk dính đường dẫn tệp làm breadcrumb | **74/74** | **0/109** |
| `b09-dn.docx` — chunk có breadcrumb thật | 0 (mọi breadcrumb đều là đường dẫn) | **108/109** |
| nghiệm thu 12 tệp Word thật (`.docx` + `.doc`) | chưa có | cổng cứng ĐẠT — 0/191 chunk toàn corpus dính đường dẫn |

## 2. Khó khăn đã gặp

### 2.1 Chỉ dẫn phép thử phá của controller đủ mơ hồ để một cách đọc hợp lý không đỏ (Task 1)

Reviewer dựng lại đột biến Step 6 theo ba cách đọc hợp lý khác nhau của cùng một câu chỉ dẫn: một
cách **không đỏ** (đặt khối enum trước `if shared is None`), một cách đỏ nhưng **sai lý do** (đặt
sau `return None`, đỏ vì return sớm chứ không vì thứ tự kiểm), và một cách đỏ **đúng lý do** (đột
biến "tự nhiên" — `heading_level` thắng, enum là dự phòng — ra `[35, 20]` khớp đúng docstring). Số
báo cáo ban đầu của implementer không tái lập được bằng bất kỳ cách đọc nào — nghi là chép sai báo
cáo, không phải bịa. Ruling: KHÔNG mở fix round — tính chất cần chứng minh (thứ tự kiểm là cần
thiết) đã được một nguồn nghiêm ngặt hơn (reviewer tự dựng) xác nhận bằng số cụ thể khớp docstring;
chạy lại qua implementer không thêm thông tin. Sửa CHỈ DẪN trong plan cho hết mơ hồ thay vì chạy
lại người.

### 2.2 Đáp án nền cho Task 4 phải đo trước khi giao việc, không suy từ spec

Controller tự đo cổng cứng số 1 trên `b09-dn.docx` thật (không chỉ tin diff) trước khi dispatch
Task 4, cấp sẵn con số `109 chunk / 0 dính đường dẫn / 108 có breadcrumb` cho implementer đối chiếu
thay vì để họ đo lại từ đầu — tránh lãng phí một lượt đo trùng và cho một điểm neo độc lập để phát
hiện lệch ngay nếu môi trường implementer khác đi.

### 2.3 Brief Task 4 tự mâu thuẫn với chính tiêu đề của nó: "12 tệp" nhưng code mẫu chỉ lọc `.docx`

Mẫu code trong brief (`_tep_docx()`) lọc đúng đuôi `.docx`, nhưng kho `tmp-docs/` có 11 tệp `.docx`
+ 1 tệp `.doc` (`quyche_taichinh.doc`) — dùng nguyên mẫu chỉ nghiệm thu được 11/12 tệp, và bỏ lọt
đúng ca kiểm cầu chuyển đổi LibreOffice mà spec mục 12 nêu tên minh thị ("`quyche_taichinh.doc` đi
qua cầu LibreOffice trước khi tới `parse_docx`, nên nó cũng gián tiếp kiểm đường chuyển đổi của kế
hoạch 1"). Implementer Task 4 tự phát hiện khi đối chiếu số tệp trong thư mục với con số "12" ở
tiêu đề task, sửa test để gồm cả `.doc` (chuyển qua `convert.convert_file` trước `parse_docx`,
đúng khuôn `read_path`/`source_file` tách rời của `ingest._chunks_for`/`_ingest_convertible`).
Không cần sửa gì ở `convert.py`/`ingest.py` — chỉ test tự lo phần chuyển đổi bằng cách gọi lại đúng
hàm production đã có sẵn.

### 2.4 BỐN lỗi trong kế hoạch

Review toàn nhánh gọi tên bốn lỗi cùng lớp (chỉ dẫn / phép đo TRÔNG như đủ để kết luận nhưng không
đủ), ba cái từ việc thực thi, một cái từ chính brief của Task 4:

(1) Chỉ dẫn phép thử phá ở Task 1 Step 6 đủ mơ hồ để ba cách đọc hợp lý khác nhau, một cách không
    kích hoạt đột biến. Sửa chỉ dẫn trong plan cho hết mơ hồ thay vì chạy lại người (mục 2.1).

(2) Brief Task 4 có code mẫu chỉ lọc `.docx` trong khi tiêu đề task nói "12 tệp", bỏ lọt đúng tệp
    kiểm cầu chuyển đổi LibreOffice mà spec đặt tên riêng. Chỉ dẫn phải tuyệt đối rõ ràng (mục 2.3).

(3) Task 4 Step 3 yêu cầu thử ba biến thể `roman`/`letter` ở ba vị trí khác nhau, nhưng không đặt
    rõ nên implementer không biết nên thử các vị trí nào là chính (không quy định chi tiết → không
    xác minh được hiệu chỉnh).

(4) Task 4 Step 4 tự nhận "ba dòng số này trả lời đúng câu hỏi spec mục 5 đặt ra" — SAI: ba con số
    TỔNG trên cả 12 tệp không trả lời được câu hỏi thật (mẫu số trần `arabic_ok` gây hại ở THỂ
    LOẠI tài liệu nào), phải có phép phân định theo TỪNG TỆP mới ra được ruling có trách nhiệm —
    và phép đó KHÔNG có trong plan, controller phải tự viết thêm giữa chừng. Cùng lớp lỗi với ba
    lỗi trên (chỉ dẫn/phép đo TRÔNG như đủ để kết luận nhưng không đủ).

**Quy tắc rút ra**: bất kỳ phép đo nào trong một plan sẽ dẫn tới một RULING có hệ quả sản xuất
(đặc biệt hệ quả tới retrieval) phải chỉ định SẴN độ chi tiết cần thiết (theo tệp / theo thể loại
tài liệu, không chỉ số tổng) ngay trong bước đo của plan — không được để lại cho controller ứng biến
sau khi thấy một con số tổng mơ hồ.

## 3. Giả thuyết bị số đo bác bỏ

- **"Hàm dò chữ có sẵn (`heading_level()`) là đủ, chỉ cần nối vào docx"** — SAI, đo ra `B09a-DN`
  vẫn 0/28 tiêu đề dò được (spec mục 1). Giả thuyết đầu tiên của thiết kế, bị chính số đo bác trước
  khi viết code.
- **"Ba biến thể roman/letter khác nhau sẽ tách bạch được thang cấp đúng"** (Task 4 Step 3) — không
  hẳn SAI nhưng **không xác nhận được**: đo cả 12 tệp thật với `roman/letter` đặt ở ba vị trí khác
  nhau trong thang (35/38 hiện tại, 22/25 sát `upper`, 42/43 dưới `Điều`) cho **CHÍNH XÁC cùng một
  con số** (191 chunk, 182 breadcrumb) ở cả ba biến thể. Truy nguyên: họ `letter` (`A.`/`B.`)
  **không xuất hiện lần nào** trong 12 tệp thật, và họ `roman` chỉ xuất hiện ở 2 tệp mà cả hai đều
  không đồng thời có tiêu đề cấp `Điều` — nên không tài liệu nào từng tạo ra một cặp cha-con thật
  để thang cấp phải phân xử. Dải phẳng đúng cách kế hoạch 2 đã chốt `SCAN_LIMIT`: **giữ nguyên đề
  xuất** (`roman=35, letter=38`), không đổi `parse.py`.
- **Ngầm định "mẫu số trần (`arabic_ok`) không có tác dụng phụ đáng kể"** — số đo phân bố chunk
  (Task 4 Step 4) cho tín hiệu ngược: bật đầy đủ suy phân cấp làm chunk tăng từ 146 lên 191
  (+31%), nhưng tắt riêng nhánh `arabic_ok` (chỉ giữ bằng chứng cha-con `n in parents`) thì chỉ còn
  156 (+7% so với trước B3, kích thước trung vị 710 ký tự — gần khớp 726 của "trước").

  **Phương pháp**: cả hai script đo của Task 4 Step 3/4 đã được sửa để gồm CẢ `.doc` qua
  `convert.convert_file` (cùng lý do như tệp test — xem §0), không chỉ `.docx` như mẫu code trong
  kế hoạch. Ai chạy đúng mẫu code trong kế hoạch (chỉ lọc `.docx`, 11 tệp) sẽ ra `132/174/139` chứ
  không phải `146/191/156` — hai bộ số đều đúng, chỉ khác phạm vi tệp.

  **RULING của controller (2026-09-04): GIỮ nhánh `arabic_ok`, KHÔNG áp phương án lùi.** Ban đầu
  tôi ghi ở đây rằng mẫu số trần "đang cắt `Điều`/mục thành khoản nhỏ hơn" — **câu đó SAI, đã sửa
  lại**. Phép đo phân định (controller tự chạy, tách chênh lệch theo TỪNG TỆP) cho thấy:

  | tệp | đầy đủ | bỏ `arabic_ok` | chênh |
  |---|---|---|---|
  | `b09-dn.docx` (thuyết minh BCTC) | 109 | 77 | **+32** |
  | `B09a-DN.docx` (thuyết minh BCTC) | 11 | 8 | **+3** |
  | `quyche_ogop.docx` | 1 | 1 | **+0** |
  | `quyche_taichinh.doc` | 17 | 17 | **+0** |
  | 8 biểu mẫu BCTC ngắn còn lại | — | — | **+0** |

  Toàn bộ mức tăng nằm ở hai tệp *thuyết minh báo cáo tài chính*, đúng thể loại mà `1.`/`12.` LÀ
  mục thật — breadcrumb sinh ra là `… › I. Đặc điểm hoạt động của doanh nghiệp › 1. Hình thức sở
  hữu vốn.`, đúng cấu trúc tài liệu. **Cả hai tệp quy chế — thể loại mà rủi ro "khoản của Điều bị
  vỡ" thực sự nằm — đều +0.** Rủi ro spec mục 5 lường trước đã được ĐO và nó không xảy ra trên
  corpus này. "Cắt vụn" ở đây cũng không mất nội dung hay ngữ cảnh: mỗi chunk nhỏ hơn vẫn mang trọn
  breadcrumb cha, đúng thứ B3 dựng ra để cấp.

  **Giá nếu ruling sai**: nếu corpus sau này có nhiều văn bản kiểu luật (khoản đánh số dưới Điều),
  `arabic_ok` sẽ cắt vụn chúng — sửa là lật một cờ boolean, phương án lùi đã ghi sẵn ở spec mục 5.
  **Điều CHƯA đo, nói rõ**: chưa có phép đo RETRIEVAL nào cho corpus docx (12 tệp này là fixture
  trong `tmp-docs`, chưa index vào production). Ruling dựa trên cấu trúc tài liệu, KHÔNG dựa trên
  recall. Mở lại khi corpus docx được index thật và có eval phủ nó.

## 4. Hướng đã chọn, và vì sao

| quyết định | vì sao |
|---|---|
| Lớp mẫu RIÊNG cho docx (`docx_heading_levels`), gọi `heading_level()` trước rồi mới thử mẫu mở rộng, KHÔNG nới `heading_level()` gốc | `heading_level()` đang phục vụ corpus luật đã hiệu chỉnh kỹ (nhánh `Điều` từng bị siết vì sinh mảnh câu) — nới nó ra là rủi ro hồi quy trên đường đang chạy tốt để chữa một đường khác. Đường luật không đổi một bit; cổng cứng số 2 của spec mục 10 xác nhận suite PDF giữ nguyên số. |
| Đánh số trần (`I.`, `A.`, `1.`) chỉ tính là tiêu đề khi CHÍNH tài liệu đưa bằng chứng (hai mục kế tiếp cùng họ, hoặc có con mang cùng tiền tố) | Số trần một cấp là thứ văn bản luật cố tình loại vì đó là khoản — nhận bừa vỡ một `Điều` có 4 khoản thành 4 mảnh. Nhưng số đo Task 4 (mục 3 ở trên) cho thấy chính quy tắc bằng chứng này KHÔNG hoàn hảo — nhánh `arabic_ok` (bằng chứng yếu hơn: chỉ cần hai số trần kế tiếp, không cần con) vẫn để lọt một phần "cắt vụn" — ghi lại làm giới hạn đã biết, không phải khiếm khuyết mới phát sinh. |
| Ánh xạ style Word `Heading N` → `N × STYLE_SCALE(10)`, không dùng cấp thô | Dùng thô thì `Heading 2` (cấp 2) cao hơn cả `PHẦN`(5) lẫn `Chương`(10), hất sạch mọi thứ phía trên nó — lỗi tìm được khi tự soát spec, không phải khi chạy, thuộc loại "hai thang số gặp nhau ở một chỗ không ai nhìn". |
| `crumb` không lùi về `doc_title` khi rỗng; `doc_title` (cột riêng cho hiển thị/trích dẫn) lùi về BASENAME chứ không phải rỗng — LỆCH có chủ ý so với spec mục 8 (spec viết "phải rỗng") | Đọc code trước khi thực thi: `doc_title` là cột schema.sql riêng, `retrieve.py` SELECT ra để hiển thị, KHÔNG đi vào `index_text()`/`ts_vector` — tác hại nằm TRỌN ở `crumb`. Tách đôi giữ được nhãn trích dẫn đọc được (basename) mà vẫn đóng đúng lỗ hổng embedding (crumb rỗng thật). Đã nêu với chủ dự án trước khi bắt đầu, không phản đối. |
| Task 4: mở rộng nghiệm thu sang cả `.doc` qua cầu LibreOffice, dù brief mẫu chỉ lọc `.docx` | Tiêu đề task và spec mục 12 đều nói "12 tệp" — kho thật có đúng 12 tệp Word (11 `.docx` + 1 `.doc`); dùng nguyên mẫu bỏ sót đúng ca kiểm cầu chuyển đổi mà spec đặt tên riêng. |
| Task 4 Step 3: giữ nguyên `DOCX_LEVEL`, không đổi số dù đã thử 2 biến thể khác vị trí | Số đo ra dải phẳng tuyệt đối (3 biến thể, cùng 191/182 y hệt) — đổi số mà không có bằng chứng phân biệt là "chỉnh cho đẹp", đúng điều dự án đã tự cấm sau khi bỏ ngưỡng `đúng >= 20` ở kế hoạch 2. |
| Task 4 Step 4: chỉ đo, không tự áp phương án lùi (bỏ nhánh `arabic_ok`) dù số đo có tín hiệu rõ | Đánh đổi có hệ quả tới retrieval (hình dạng chunk đem đi embed), không phải một cấu hình cục bộ — chỉ thị cứng của brief, và đúng tinh thần "đo trước, quyết sau" đã xuyên suốt cả ba kế hoạch. |

## 5. Giới hạn còn lại

### Đã biết, cần controller quyết định (không phải bỏ sót)

- **Cổng cứng "0 chunk mang đường dẫn tệp" trên 12 tệp Word thật KHÔNG nhạy riêng với Task 3** —
  Đo lại bằng cách dựng lại logic `chunking.py` TRƯỚC Task 3 (doc_title lùi về source_file, crumb
  lùi về doc_title) nhưng GIỮ NGUYÊN bộ dò Task 1+2, vẫn ra 0/12 tệp dính đường dẫn. Lý do: Task
  1+2 đã khiến MỌI tệp trong 12 tệp có ít nhất một heading (kể cả chỉ nhờ dòng IN HOA tiêu đề tài
  liệu), nên kịch bản Task 3 sửa ("tài liệu KHÔNG có heading nào") không còn xảy ra trên corpus này.
  Bảo vệ hồi quy THẬT của Task 3 nằm trọn trong fixture tổng hợp `test_chunking_khong_duong_dan.py`
  (đã xác nhận đỏ được bằng phép thử phá). Nếu sau này có tệp thật hoàn toàn không phân cấp được (0
  heading dù đã qua Task 1+2), chỉ fixture tổng hợp mới bắt được hồi quy ở đó — cổng trên corpus
  thật sẽ không thấy.
- **Nhánh `arabic_ok` có dấu hiệu cắt vụn `Điều` thành khoản** — số đo ba dòng ở mục 3 trên. Phương
  án lùi (bỏ `arabic_ok`, chỉ giữ bằng chứng `n in parents`) đã có sẵn trong spec nhưng KHÔNG được
  tự áp dụng ở Task 4. Cần một quyết định rõ ràng + (nếu áp) một lượt đo lại 12 tệp thật để xác
  nhận không mất ca đúng nào.
- **Thang cấp `roman`(35)/`letter`(38) chưa từng được số đo THẬT xác nhận đúng vị trí** — dải phẳng
  nghĩa là "chưa có bằng chứng SAI", không phải "đã có bằng chứng ĐÚNG". Riêng `letter` (`A.`/`B.`)
  chưa xuất hiện lần nào trong 12 tệp thật hiện có; hiệu chỉnh này cần chờ kho mở rộng.

### Chưa chạm tới / ngoài phạm vi (theo spec mục 11)

- **Tín hiệu định dạng** (đậm, in hoa, căn giữa) từ python-docx — hoãn có chủ ý (phương án D, spec
  mục 3). Mở lại chỉ nếu số đo sau khi mở rộng mẫu chữ cho thấy còn thiếu thật; 12 tệp thật hiện
  tại chưa cho bằng chứng cần nó.
- **Bảng trong `.docx` vẫn là THÂN, không bao giờ là tiêu đề** — B4 (PDF bóc bảng) không chạm tới
  ca này; bảng docx là một khoảng trống thiết kế riêng, chưa có kế hoạch.
- **Tách module riêng cho bộ dò docx** — quy mô hiện tại (4 mẫu + 1 quy tắc bằng chứng) chưa đáng
  một module lá như `xlsx_header.py`. Nếu nó phình lên (ví dụ khi thêm tín hiệu định dạng) thì tách
  sau.

### Đại diện của kho thật

- **12 tệp thật đều là biểu mẫu BCTC/quy chế** — không có tài liệu Word văn xuôi dài (hợp đồng, báo
  cáo dài) trong kho. Mẫu hành chính có thể không đại diện cho loại đó; 8/12 tệp trong nghiệm thu
  Task 4 thực chất chỉ có ĐÚNG MỘT tiêu đề (dòng tiêu đề tài liệu), tức không có phân cấp đa tầng
  thật — "12/12 tài liệu có phân cấp" ở báo cáo Task 4 chỉ đúng theo định nghĩa "≥1 tiêu đề", dễ
  đọc nhầm thành phân cấp sâu nếu không xem cột "tiêu đề" trong bảng chi tiết.

# Tầng nạp tài liệu — ghi chú thực thi B4

**Ngày**: 2026-09-04. **Nhánh**: `worktree-tang-nap-tai-lieu-1`.
**Spec**: `2026-09-04-b4-pdf-bang-design.md` · **Kế hoạch**: `plans/2026-09-04-b4-pdf-bang.md`
**Ledger**: `.superpowers/sdd/2026-09-04-b4-pdf-bang/progress.md`

Nghiệm thu B4 (PDF bóc bảng, Task 1-4 đã xong, review sạch tại `b9703c3`) trên corpus PDF THẬT tại
`d:/Youdoo/tmp-docs` + `d:/Documents/luat-*.pdf`. Task 5 KHÔNG sản xuất API mới — khoá kết quả bằng
test tự kiểm trên tài liệu thật, đúng tinh thần "kiểm bằng sản phẩm không kiểm bằng mã thoát". Một
trong bốn test KHÔNG pass ngay lần đầu — mục 2.2 dưới đây ghi lại đầy đủ, không giấu.

## 1. Kết quả

| phép đo | kết quả thật |
|---|---|
| 100 `invoice_*.pdf` — tự kiểm SL × đơn giá = thành tiền | **0/455 hàng tự kiểm sai** (1652 chunk tổng, 455 hàng đủ 3 trường để tự kiểm được) |
| `ssc_bieumau.pdf` — checksum đứt đoạn | **0 đứt đoạn** |
| `ssc_bieumau.pdf` — hàng bảng LẶP qua ranh giới trang | **4 hàng trùng lặp** (đo, không phải 0 giả định — xem 2.1) |
| `bieumau_bctc_hopnhat.pdf` — không chunk lẫn mã cột đầu hàng khác | **BUG THẬT, 2 hàng lẫn → ĐÃ VÁ 2026-09-04**, còn 2 hàng đỏ vì lý do KHÁC (`xfail(strict=True)` vẫn giữ — xem 2.2 mục "Vá sau nghiệm thu") |
| 6 tệp PDF luật thật (`d:/Documents/luat-*.pdf`, 372 trang) — byte-identical trên trang KHÔNG bảng | **6/6 tệp khớp 100%** đối chiếu trực tiếp với `parse_pdf` bản TRƯỚC B4 (xem 2.3) |
| tiền đề "683/683 trang PDF luật không bảng" trên corpus HIỆN CÓ | **KHÔNG khớp** — 4/6 tệp luật thật có bảng thật (phụ lục danh mục); xem 2.3 |
| test suite mặc định | 2327 passed, 1 skipped, 77 deselected → **2327 passed, 1 skipped, 81 deselected** (không đổi — 4 test mới đều `-m live`, không vào suite nhanh) |

## 2. Khó khăn đã gặp

### 2.1 `ssc_bieumau.pdf` — giới hạn "vỡ trang" biến thể LẶP, đúng như dự đoán khi khảo sát kế hoạch

Brief đã cảnh báo trước: bảng đánh số phân cấp trải trang 3→8 có thể để hàng cuối trang N trùng
hàng đầu trang N+1, vì `pdfplumber.find_tables()` dò bảng RIÊNG trên TỪNG TRANG. Đo thật ra
**4 hàng trùng lặp** (ví dụ: `"Cột 1: | Cột 2: | yết, công ty đại chúng\nquy mô lớn): Công ty đại
chúng | kiểm toán nhưng không được vượt\nquá 120 ngày..."`), không phải hàng `"2.2"` cụ thể mà khảo
sát ban đầu nêu làm ví dụ — số liệu thật khác chi tiết minh hoạ trong brief nhưng đúng LỚP hiện
tượng đã dự đoán. Giữ nguyên phán quyết đã ghi trước: giới hạn CHẤP NHẬN của B4 (biến thể của "vỡ
trang" mất-hàng đã chấp nhận ở `bieumau_bctc_hopnhat.pdf` trang 21), không vá — `pdf_table.py` xử
lý mỗi bảng độc lập theo trang, ĐÚNG THIẾT KẾ.

Một lưu ý môi trường phụ: đo bằng `capsys`/`print` unicode qua `pytest -s` trên console Windows văn
bản mặc định (cp1252) NÉM `UnicodeEncodeError` khi in tiếng Việt có dấu — không phải lỗi code, lỗi
mã hoá console. Không chạy `-s` (dùng capture mặc định của pytest) hoặc đặt `PYTHONIOENCODING=utf-8`
thì đọc được số liệu bình thường.

### 2.2 `bieumau_bctc_hopnhat.pdf` — BUG THẬT trong `split_header_body`, tìm ra nhờ chính test nghiệm thu

Step 4 KHÔNG pass ngay lần đầu — 5 chunk bị gắn cờ "nghi lẫn số hàng khác". Điều tra tay từng ca
(đọc lại `warnings`, dựng lại `_khoi_bang`/`merge_table_rows`/`split_header_body` trực tiếp trên
bảng thật của trang có lỗi) tách ra **hai lớp khác nhau**, đúng cảnh báo brief đưa ra trước ("có thể
là bug thật, có thể là thước đo sai — đừng nới lỏng phép so sánh"):

- **3/5 ca là LỖI THƯỚC ĐO của chính test**: mẫu code trong brief chọn "hàng bảng" bằng
  `any(k in text for k in (" | ", ": "))` — điều kiện `": "` quá lỏng, bắt luôn văn xuôi thường có
  dấu hai chấm (đoạn "Ghi chú: (1) Những chỉ tiêu...", đoạn liệt kê "Nguyên tắc kế toán..."), không
  phải hàng bảng thật. `row_to_text` (`pdf_table.py`) LUÔN nối cột bằng `" | "` — sửa điều kiện
  thành CHỈ `" | "` (khớp đúng hợp đồng thật của hàm sản xuất), 3 ca này biến mất.
- **2/5 ca còn lại là BUG THẬT**, xác nhận bằng cách dựng lại pipeline tay từng bước (dump bảng thô
  từ `pdfplumber` → qua `merge_table_rows` → qua `split_header_body` → qua `column_names`): bảng
  thô ĐÚNG (mỗi dòng cân đối tài sản có mã số riêng: `251, 252, 260...`), `merge_table_rows` ĐÚNG
  (79 hàng tách bạch). Lỗi nằm ở `split_header_body`: nhánh 2 ("đa số ô rỗng → header") được kiểm
  TRƯỚC nhánh 3 ("có ô số liệu thuần → thân"). `bieumau_bctc_hopnhat.pdf` là biểu mẫu (form) CHƯA
  điền — mọi hàng dữ liệu thật chỉ có 2/5 ô khác rỗng (nhãn + mã số, ba cột "số cuối kỳ/số đầu kỳ"
  để trống), nên MỌI hàng thân thật đều rơi vào nhánh 2 và bị nuốt vào HEADER liên tục, cho tới khi
  gặp ĐÚNG một hàng có ≥3/5 ô khác rỗng để kích nhánh 3. `column_names()` sau đó nối TẤT CẢ nhãn của
  các "hàng-header-giả" (thật ra là nhiều dòng dữ liệu KHÔNG LIÊN QUAN nhau) thành MỘT tên cột rác
  dài, và tên rác đó bị đắp vào MỌI hàng thân phía sau qua `row_to_text`. Đo được nguyên văn:
  `'... TỔNG CỘNG TÀI SẢN (280 = 100 + 200) | 251 252 260 261 262 263: 280 | Cột 3: | Cột 4: | Cột
  5: '` — 6 mã số (`251,252,260,261,262,263`) của 6 hàng cân đối tài sản khác nhau dồn vào MỘT ô.
  **Phạm vi đo trên toàn tài liệu** (55 trang): 12/55 trang có bảng, 1106 hàng bảng tổng; ≥3/12
  trang mang dấu hiệu rõ (một tiền tố cột-1 dài >60 ký tự lặp lại >5 lần trong cùng trang), ước
  lượng ~79/1106 hàng bảng bị ảnh hưởng — tức KHÔNG phải ca hiếm, mà là hệ quả CÓ HỆ THỐNG của cấu
  trúc "biểu mẫu chưa điền" xuất hiện lặp lại trên nhiều phần của cùng tài liệu.

  **Đây đúng lớp rủi ro Task 1 review đã tự dự đoán** (Minor #2, deferred): *"`column_names` lấy
  `n_cols` từ ĐỘ DÀI HÀNG ĐẦU của `label_rows`... Corpus thật `bieumau_bctc_hopnhat.pdf` có khả
  năng gặp ca này — Task 2/5 cần để ý khi đo thật."* — đúng như dự đoán, nhưng cơ chế cụ thể (thứ
  tự nhánh 2/3 trên bảng THƯA) tinh vi hơn dự đoán ban đầu (không phải "cắt cột", mà "nuốt cả hàng
  thân vào header").

  **Quyết định cho Task 5 (KHÔNG vá `pdf_table.py`)**: đổi thứ tự hai nhánh trong `split_header_body`
  là sửa THUẬT TOÁN LÕI đã qua review Task 1 (16/16 test, Approved) — ngoài phạm vi khai báo của
  Task 5 ("Produces: không có API mới — đây là task NGHIỆM THU"), và một thay đổi thứ tự nhánh cần
  một lượt review/test riêng để chứng minh không hồi quy trên 16 ca của Task 1 + 25 ca của Task 2.
  Test giữ NGUYÊN phép so sánh cứng của brief (`assert lan == []`, không nới lỏng), nhưng đánh dấu
  `@pytest.mark.xfail(strict=True, reason=...)` ghi đầy đủ nguyên nhân gốc + số liệu phạm vi ngay
  trong lý do — chọn `xfail` thay vì im lặng để test đỏ (dễ bị bỏ qua) hay hạ xuống chỉ-in-số như ca
  ssc (che mất một bug CHƯA từng được chấp nhận là giới hạn, khác ssc đã có tiền lệ chấp nhận).
  `strict=True` nghĩa là nếu bug được sửa mà quên gỡ `xfail`, suite sẽ ĐỎ (XPASS), ép phải xử lý —
  đúng "hỏng lớn tiếng còn hơn thiếu âm thầm". **Cần một fix round riêng** (đổi thứ tự nhánh 2/3
  hoặc thêm điều kiện "đã có mã số/số liệu thuần ở CHÍNH hàng này thì ưu tiên nhánh 3 dù ô khác đa
  số rỗng") trước khi merge nếu chủ dự án muốn đóng B4 mà không mang theo bug này — quyết định của
  controller, không tự vá đơn phương trong task nghiệm thu.

#### Vá sau nghiệm thu (2026-09-04, fix round riêng — vẫn còn xfail, CHƯA đóng hoàn toàn)

Fix round đã đổi đúng thứ tự nhánh như dự đoán ở trên: `split_header_body` giờ kiểm "có ô số liệu
thuần → thân" TRƯỚC "đa số ô rỗng → header" (nhánh đánh số cột `is_column_index_row` vẫn kiểm đầu
tiên, không đổi). Viết test đơn vị mới (`test_split_header_body_bang_thua_hang_than_nhieu_o_rong_van_vao_than`
trong `test_pdf_table.py`) mô phỏng đúng ca bảng thưa 5 cột (2/5 ô có giá trị) — xác nhận FAIL trên
code cũ trước khi sửa, PASS sau khi sửa. Toàn bộ 16 test gốc của Task 1 vẫn PASS (đúng dự đoán ở
trên: không ca nào trong fixture cũ vừa có ô số liệu thuần vừa đa số ô rỗng cùng lúc).

**Đo lại trên chính `bieumau_bctc_hopnhat.pdf`, đối chiếu TRƯỚC/SAU cùng file** (đổi code qua lại,
không đổi gì khác):

| phép đo | TRƯỚC vá | SAU vá |
|---|---|---|
| Tổng số chunk | 1678 | 1719 (+41) |
| Tổng số hàng bảng (`" \| "` trong chunk_text) | 1106 | 1147 (+41 — hàng thân thật trước đây bị nuốt vào header giờ tách ra đúng thành hàng riêng) |
| Prefix cột dài >60 ký tự lặp lại >5 lần trong TOÀN tài liệu (proxy gần đúng cho "tên cột rác dồn nhiều nhãn") | 15 mẫu, tổng 473 lượt | 12 mẫu, tổng 310 lượt |
| Trong đó: mẫu MANG DẤU HIỆU RÕ của bug gốc (nhãn của NHIỀU dòng dữ liệu không liên quan dồn thành một prefix, ví dụ `"TÀI SẢN A – TÀI SẢN NGẮN HẠN I. Tiền và các khoản tương đươn"` 37 lượt, `"1. Chi phí sản xuất, kinh doanh dở dang dài hạn 2. Chi phí x"` 67 lượt, `"CHỈ TIÊU I. Lưu chuyển tiền từ hoạt động kinh doanh 1. Tiền"` 53 lượt, + 2 mẫu khác) | **5 mẫu, 260 lượt** | **0 mẫu — biến mất hoàn toàn** |
| Test tự kiểm `test_bctc_khong_chunk_nao_lan_ma_cot_dau_hang_khac` (assert `lan == []`) | 2 chunk lẫn: cột 2 chứa `"251 252 260 261 262 263: 280"` — 6 mã số của 6 hàng cân đối tài sản KHÁC NHAU dồn vào MỘT ô | vẫn 2 chunk đỏ, nhưng cột 2 giờ ĐÚNG (chỉ `"280"`, `"440"` — một giá trị) — 2 chunk còn lại là hàng TỔNG CỘNG có NHÃN (cột 1) chứa công thức tham chiếu hợp lệ `"(280 = 100 + 200)"`/`"(440 = 300 + 400)"`, không phải lẫn hàng |

Kết luận đo được: **cơ chế bug gốc đã đóng** — không còn chunk nào có nhiều mã số của nhiều hàng
khác nhau dồn vào một cột, 5/5 mẫu prefix rác đặc trưng cho garbage-header-merge đã biến mất. Nhưng
test tự kiểm ban đầu (viết ở Task 5, phép so sánh cứng `assert lan == []`) vẫn đỏ vì MỘT nguyên nhân
KHÁC, hẹp hơn nhiều: quy tắc đếm "cột đầu có >1 số liệu là nghi lẫn hàng" không phân biệt được "công
thức tham chiếu hợp lệ trong ngoặc ở nhãn hàng TỔNG CỘNG" với "mã số lẫn từ hàng khác" — CHƯA xác
định chắc chắn đây là lỗi thước đo (giống lớp lỗi `": "` đã sửa ở Step 4) hay dấu hiệu của một bug
CÒN LẠI khác (ví dụ cột bị lệch 1 vị trí đúng tại hàng TỔNG CỘNG). Theo đúng chỉ dẫn của fix round
này: **KHÔNG gỡ `xfail`, KHÔNG tự ý sửa thước đo lần nữa** — giữ nguyên `xfail(strict=True)` với lý
do cập nhật đầy đủ số liệu trên, để controller quyết định bước tiếp theo (sửa test hay điều tra thêm
`split_header_body`/`column_names` cho đúng ca hàng TỔNG CỘNG).

Không hồi quy: `pytest tests/rag/test_pdf_table.py -v` → 17 passed (16 gốc + 1 mới); `pytest
tests/rag/test_pdf_kho_that.py -v -m live` → 3 passed, 1 xfailed (3 test còn lại — 100 hoá đơn, ssc
checksum, ssc trùng lặp — không đổi); `pytest -m "not integration and not live" -q` → 2328 passed
(tăng đúng 1 so với 2327 trước đó — test đơn vị mới không phải `-m live`), 1 skipped, 81 deselected.

#### Sửa lỗi thước đo (2026-09-04, sau khi controller xác nhận chắc chắn)

Kiểm tra lại xác nhận từ controller: **2/5 chunk còn lại LÀ lỗi thước đo, KHÔNG phải bug sản phẩm**.
Nguyên nhân chính xác: quy tắc `re.findall(r"\d[\d.,]{2,}", ...)` đếm mọi số liệu >3 chữ số trong
**cột nhãn** (cột đầu tiên của hàng bảng), mà không loại trừ nội dung trong ngoặc `(...)` — hai hàng
TỔNG CỘNG `"TỔNG CỘNG TÀI SẢN (280 = 100 + 200)"` và `"TỔNG CỘNG NGUỒN VỐN (440 = 300 + 400)"` là
cấu trúc kế toán hợp lệ (công thức tham chiếu trong ngoặc ghi mã dòng con số), KHÔNG phải hiện tượng
"lẫn hàng khác". Sửa phép đo: loại bỏ **nội dung trong ngoặc TRƯỚC khi đếm**, sử dụng
`re.sub(r"\([^)]*\)", "", ...)` để xoá tất cả `(...)`, rồi mới đếm số liệu. Loại bỏ `xfail` marker.

Kết quả sau sửa:
- `test_bctc_khong_chunk_nao_lan_ma_cot_dau_hang_khac` — **PASS** (0/1147 hàng bảng nghi lẫn)
- 3 test B4 còn lại (100 hoá đơn, ssc checksum, ssc trùng lặp) — vẫn PASS (không hồi quy)
- Suite toàn bộ `-m "not integration and not live"` — **2328 passed** (không đổi số lượng)
- Commit: đồng thời cập nhật test + ghi chú thực thi

### 2.3 Tiền đề "683/683 trang PDF luật không bảng" KHÔNG khớp corpus hiện có — nhưng bất biến an toàn thật vẫn đứng vững

`d:/Youdoo/tmp-docs` hiện KHÔNG còn tệp `.pdf` nào tên "luật" (thư mục gitignore, nội dung đổi theo
thời gian — con số 683 trong spec `2026-08-29-tang-nap-tai-lieu.md`/`2026-09-04-b4-pdf-bang-design.md`
được đo ở một thời điểm/corpus khác, không tái lập được ở đây). Kho luật thật gần nhất hiện có là
`d:/Documents/luat-*.pdf` (6 tệp, **372 trang**, không phải 683). Chạy `parse_pdf` qua cả 6 tệp cho
kết quả **KHÔNG khớp tiền đề "0 bảng"**:

| tệp | trang | atomic (bảng) | trang có bảng |
|---|---|---|---|
| `luat-baohiemxahoi.pdf` | 71 | 2 | 1 |
| `luat-dautu.pdf` | 62 | 898 | 25 |
| `luat-doanhnghiep.pdf` | 121 | 7 | 7 |
| `luat-quanlythue.pdf` | 77 | 0 | 0 |
| `luat-thuegtgt.pdf` | 16 | 0 | 0 |
| `luat-thuexuatnhapkhau.pdf` | 25 | 621 | 14 |

Chỉ 2/6 tệp khớp đúng "0 bảng". Đọc mẫu nội dung `atomic` của `luat-dautu.pdf` (trang 37-61) xác
nhận đây là **bảng THẬT** — phụ lục danh mục hoá chất/chất cấm dạng `STT | tên chất | tên khoa học`
(Luật Đầu tư có phụ lục ngành nghề cấm kinh doanh liệt kê dạng bảng) — KHÔNG phải `pdfplumber`
báo nhầm trên văn xuôi thường. Tương tự khả năng cao cho `luat-thuexuatnhapkhau.pdf` (biểu thuế
suất, bản chất vốn dĩ là bảng).

**Điều thật sự cần bảo vệ** (bất biến an toàn — trang KHÔNG bảng phải byte-identical với đường cũ)
**vẫn đo được trên chính corpus này**, không cần đúng số 683: dựng lại `parse_pdf` bản NGAY TRƯỚC
B4 (commit `3b74520`, trước Task 2) và so từng block trên các trang KHÔNG có bảng của cả 6 tệp —
**khớp 100% cả 6/6 tệp** (số block bằng nhau, nội dung từng block bằng nhau). Tức: tiền đề bề mặt
("không trang nào có bảng") sai với corpus hiện tại, nhưng THUỘC TÍNH mà tiền đề đó được viết ra để
bảo vệ (đường pypdf không đổi trên trang không chạm tới) vẫn đứng vững — xác nhận bằng đối chiếu
trực tiếp, không chỉ suy luận từ số 0 bảng.

## 3. Giả thuyết bị số đo bác bỏ

- **"PDF luật hiện có không trang nào có bảng"** (tiền đề nêu trong spec gốc + design B4 §3.2, dựa
  trên số đo 683/683 ở một thời điểm khác) — SAI trên corpus `d:/Documents/luat-*.pdf` hiện tại:
  4/6 tệp có bảng thật (phụ lục danh mục/biểu thuế). Không phải giả thuyết B4 tự đặt ra, mà là một
  tiền đề kế thừa từ kế hoạch trước đó, lần đầu bị đối chiếu với corpus THẬT ở Task 5. Không ảnh
  hưởng ruling nào của B4 vì bất biến thật sự cần (byte-identical trên trang không bảng) đã đo lại
  và vẫn đúng (mục 2.3).
- **Ngầm định "test nghiệm thu Task 5, viết sẵn trong brief, đo đúng ngay lần đầu"** — sai cho Step
  4: 3/5 ca đầu là lỗi thước đo của chính test (điều kiện `": "` quá lỏng), 2/5 ca còn lại là bug
  thật trong `split_header_body` (mục 2.2). Đúng tinh thần "task ĐO THẬT, không phải task có sẵn
  đáp án đúng" mà chỉ dẫn Task 5 đã nêu trước.

## 4. Hướng đã chọn, và vì sao

| quyết định | vì sao |
|---|---|
| Test `ssc_bieumau` hàng trùng lặp: chỉ ĐO (`print`), không gate cứng | Đã có tiền lệ CHẤP NHẬN rõ ràng từ lúc khảo sát kế hoạch (biến thể của giới hạn "vỡ trang" đã chấp nhận cho ca mất-hàng) — không phải bug mới, không cần fix round. |
| Test `bctc` sửa điều kiện lọc "hàng bảng" từ `(" | ", ": ")` OR xuống chỉ `" | "` | `row_to_text` LUÔN dùng `" | "` làm dấu phân cách cột thật — điều kiện `": "` là lỗi thước đo (bắt cả văn xuôi có dấu hai chấm), sửa THƯỚC ĐO đúng như chỉ dẫn Task 5 cho phép, KHÔNG đụng tới phép so sánh số học (`assert lan == []` giữ nguyên). |
| Test `bctc` giữ nguyên `assert lan == []`, đánh dấu `xfail(strict=True)` thay vì sửa `pdf_table.py` hoặc hạ gate | Bug thật nằm trong thuật toán lõi đã qua review (Task 1), ngoài phạm vi "không có API mới" của Task 5; vá đơn phương không qua review là rủi ro hồi quy trên 16+25 test đã xanh của Task 1/2. `xfail(strict=True)` giữ tín hiệu ĐỎ LỚN TIẾNG (không giấu trong suite xanh, không im lặng bằng cách xoá assert) mà không chặn Step 8 (test `-m live`, không vào suite nhanh) — đúng "hỏng lớn tiếng còn hơn thiếu âm thầm", để lại quyết định fix round cho controller. |
| Step 7: không dừng lại ở con số "0 bảng" khi tiền đề đó sai, tự đối chiếu byte-identical bằng `parse_pdf` bản trước B4 | Con số bề mặt ("0 bảng") không phải điều spec THẬT SỰ cần bảo vệ — thuộc tính cần bảo vệ là byte-identical trên trang không chạm. Đo bề mặt sai mà dừng lại sẽ để lại một câu hỏi treo ("vậy bất biến an toàn còn đúng không?") đúng lúc corpus vừa cho thấy tiền đề bề mặt không còn khớp — đo thẳng vào thuộc tính thật rẻ hơn và trả lời dứt điểm. |

## 5. Giới hạn còn lại

### Đã biết, cần controller quyết định (không phải bỏ sót)

- **`split_header_body` nuốt hàng thân vào header trên bảng biểu mẫu THƯA** (mục 2.2) — bug thật,
  **ĐÃ VÁ 2026-09-04** (đổi thứ tự nhánh 2/3, xem "Vá sau nghiệm thu" ở mục 2.2): cơ chế gốc (nhiều
  mã số của nhiều hàng khác nhau dồn vào một cột) đã biến mất, 5 mẫu prefix rác đặc trưng cho bug
  này (473 lượt) không còn xuất hiện. **Còn lại, CHƯA đóng hoàn toàn**: `xfail(strict=True)` vẫn giữ
  vì test tự kiểm gốc còn 2 chunk đỏ do MỘT nguyên nhân KHÁC — nhãn hàng TỔNG CỘNG chứa công thức
  tham chiếu hợp lệ (`"(280 = 100 + 200)"`) khiến quy tắc đếm "cột đầu >1 số liệu = nghi lẫn" báo
  sai; chưa xác định đây là lỗi thước đo hay bug thật khác — để controller quyết định bước tiếp
  theo. Chưa đo trên tài liệu khác có cùng đặc điểm "biểu mẫu chưa điền" (nếu corpus mở rộng có thêm
  loại này, cần đo lại).
- **`ssc_bieumau.pdf` — 4 hàng bảng lặp qua ranh giới trang** (mục 2.1) — giới hạn CHẤP NHẬN, không
  cần vá, chỉ đo (đã có tiền lệ chấp nhận biến thể mất-hàng ở B3/B4).
- **Tiền đề "683 trang PDF luật" trong 2 spec cũ (`2026-08-29-tang-nap-tai-lieu.md`,
  `2026-09-04-b4-pdf-bang-design.md`) không còn tái lập được với corpus hiện có** — không sửa các
  spec cũ đó ở Task 5 (ngoài phạm vi commit này); ghi lại ở đây làm điểm neo cho lần sau ai đọc lại
  hai spec đó không hiểu nhầm "683" là con số còn kiểm chứng được hôm nay.

### Chưa chạm tới / ngoài phạm vi

- **Không đo chunk-lẫn-số trên bảng phụ lục thật của `luat-dautu.pdf`/`luat-thuexuatnhapkhau.pdf`**
  (mục 2.3) — Task 5 chỉ đo "có bảng hay không" cho gate byte-identical, chưa chạy phép tự kiểm kiểu
  Step 4 trên các bảng phụ lục luật này. Nếu corpus luật với bảng phụ lục được đưa vào production
  thật, nên đo thêm — ngoài phạm vi brief hiện tại.
- **Nghiệm thu Task 5 không có eval RETRIEVAL nào** — toàn bộ số liệu ở đây là cấu trúc dữ liệu
  (đúng/sai số học, checksum, byte-identical), không phải chất lượng truy hồi. Giống ranh giới đã
  ghi ở B3 mục 3: ruling dựa trên cấu trúc, chưa dựa trên recall.

---

## 6. Fix wave sau review toàn nhánh (2026-09-04)

Review toàn nhánh cuối cùng (đọc diff + TỰ ĐO trên corpus THẬT, ngoài 3 tệp mà Task 5 dùng nghiệm
thu) báo 2 lỗi Critical + 1 Important. Cả ba đều là **B4 làm mất/làm hỏng nội dung trên tài liệu
sản xuất thật** — đúng lớp lỗi B4 sinh ra để đóng nhưng tái xuất hiện ở tầng khác. Dưới đây là số
đo trước/sau của từng phần.

### 6.1 Thước đo dùng chung: PHỦ TỪ VỰNG (token) so với `pypdf` thô

Đường `pypdf` toàn trang là **hành vi TRƯỚC B4** — mốc so sánh đúng nghĩa "B4 có làm mất gì
không". Đếm multiset các token `[0-9\w]+` của từng trang theo `pypdf`, trừ đi multiset token của
mọi block `parse_pdf` phát ra cho trang đó; phần dư là **token biến mất**.

| tệp | phủ token TRƯỚC fix (c0d6627) | phủ token SAU fix |
|---|---|---|
| `USA_Employee_Handbook-Freely_Available.pdf` (34 tr.) | **18.6%** | **99.7%** |
| `ssc_bieumau.pdf` (8 tr.) | **39.5%** | **78.6%** (xem ghi chú) |
| `bieumau_bctc_hopnhat.pdf` (53 tr.) | **72.9%** | **92.5%** |
| `luat-thuexuatnhapkhau.pdf` (25 tr.) | **89.6%** | **97.7%** |
| `luat-dautu.pdf` (61 tr.) | **93.4%** | **97.5%** |
| `invoice_51109301.pdf` | 100.0% | 100.0% |

Ghi chú `ssc`: phần "thiếu" còn lại KHÔNG phải mất nội dung mà là **khác cách tách từ** — `pypdf`
trả ra chữ vỡ (`"Trong th ời hạn 10 ng ày"`), `pdfplumber` trả đúng (`"Trong thời hạn 10 ngày"`),
nên token `"th"`/`"ời"` của `pypdf` không khớp token `"thời"`. Con số 78.6% là **cận DƯỚI**, chất
lượng chữ thực tế tốt hơn mốc so sánh. Cùng hiệu ứng có mặt ở mọi tệp tiếng Việt.

### 6.2 Critical #1 — mất CẢ MỘT CỘT của bảng biểu thuế suất

**Triệu chứng đo được**: số dòng mang mức thuế suất (regex `\b\d{1,3}\s*-\s*\d{1,3}\b`, kiểu
"0-10"/"15-25") trên trang 12-25 của `luat-thuexuatnhapkhau.pdf`:

| | số dòng |
|---|---|
| `pypdf` thô (trước B4) | **247** |
| B4 tại c0d6627 | **14** (5.7%) |
| sau fix | **240** (97.2%) |

**Nguyên nhân THẬT — khác với chẩn đoán ban đầu của review.** Review cho rằng `merge_table_rows`
gộp nhầm hai lưới 23x4 (mặc định) và 53x2 (`text`). Đo lại từng bước cho thấy nguyên nhân nằm
SỚM HƠN một bậc, trong `_trich_mot_bang`: nó **dò lại bảng bằng `find_tables()` bên trong chính
bbox của bảng** (`page.within_bbox(bbox).find_tables()`). Cắt trang theo đúng bbox làm **mất các
đường kẻ nằm ĐÚNG TRÊN biên cắt**, nên lần dò lại ra lưới **nghèo hơn hẳn**:

| trang | `bang.extract()` (dò trên TOÀN trang) | dò lại trong bbox |
|---|---|---|
| 13 | 15 hàng × **4 cột** (STT / Nhóm hàng / Mô tả / **Khung thuế suất**) | 13 hàng × **2 cột** |
| 16 | 25 hàng × **4 cột** | 23 hàng × **2 cột** |

Cột "Khung thuế suất" rơi khỏi lưới, **và vì nó nằm TRONG bbox nên `parse_pdf` cũng cắt nó khỏi
dải văn xuôi** → mất hẳn, không còn đường nào phát ra. Nhánh dự phòng `if not hang_mac_dinh:
hang_mac_dinh = bang.extract()` chỉ chạy khi dò lại trả về RỖNG, không cứu được ca "dò lại ra
lưới nghèo hơn nhưng không rỗng". Chẩn đoán "23x4 vs 53x2" của review chính là **so lưới đúng
(`bang.extract()`) với lưới `text`** — đúng con số, nhưng mã tại c0d6627 chưa bao giờ nhìn thấy
lưới 4 cột đó.

**Đã sửa, hai lớp:**

1. `_trich_mot_bang` nhận thẳng đối tượng `bang` và trả `bang.extract()` làm lưới chế độ mặc định
   — KHÔNG dò lại chế độ mặc định trong bbox nữa. Chế độ `text` vẫn phải dò trong `within_bbox`
   (không có đường nào khác giới hạn `horizontal_strategy="text"` vào một bảng).
2. Cổng `bat_dong_so_cot()` (mới, trong `pdf_table.py` — module thuật toán thuần): nếu số cột đại
   diện của hai lưới LỆCH nhau thì **bỏ hẳn chế độ `text`**, để `merge_table_rows(..., [])` rơi vào
   đúng đường dự phòng sẵn có. Kèm cảnh báo mới `("trang N, bảng", "hai chế độ trích xuất bất đồng
   số cột (n1 vs n2) — dùng riêng chế độ mặc định")` — bỏ chế độ `text` là một quyết định mất dữ
   liệu tiềm tàng (hàng vắt trang chỉ chế độ `text` thấy), phải LỚN TIẾNG.

**Hệ quả cần biết**: sau lớp (1), lưới mặc định gần như luôn NHIỀU CỘT HƠN lưới `text` (lưới `text`
chịu đúng thiệt hại cắt-bbox nói trên), nên cổng (2) kích hoạt trên hầu hết bảng thật: 13 cảnh báo
trên `luat-thuexuatnhapkhau.pdf`, 78 trên `bctc`, 3 trên `ssc`, 2 trên `invoice_51109301`. Nghĩa là
**cơ chế gộp hai chế độ của spec §3.3 nay hiếm khi có tác dụng** — đổi lại phủ token tăng ở TẤT CẢ
tệp đo được (bảng 6.1) và test tự kiểm số học 100 hoá đơn vẫn xanh. Nếu sau này muốn khôi phục lợi
ích của chế độ `text` (hàng vắt trang), hướng cần thử là dò chế độ `text` trên bbox NỚI RỘNG chút
để không mất đường kẻ biên — chưa làm, chưa đo.

**Test**: `test_bat_dong_so_cot_*`, `test_lech_so_cot_thi_ket_qua_chi_dung_che_do_mac_dinh`,
`test_doi_chung_gop_thang_hai_luoi_lech_cot_lam_mat_cot_cuoi` (ca ĐỐI CHỨNG, ghi lại chính lỗi),
`test_khoi_bang_lech_so_cot_thi_bo_che_do_text_va_canh_bao`,
`test_khoi_bang_khop_so_cot_thi_van_gop_hai_che_do` (phép thử phá: cổng không được chặn luôn chế độ
`text` khi số cột KHỚP), và 2 test live `test_luat_thue_*` trên corpus thật.

### 6.3 Critical #2 — cổng "đây có THẬT là bảng không": KHÔNG tìm được ngưỡng, CHƯA làm

**Triệu chứng review báo**: `find_tables()` báo dương tính giả trên **34/34 trang** văn xuôi của
`USA_Employee_Handbook-Freely_Available.pdf` (đã xác nhận lại: đúng 34/34), và 78% token biến mất.

**Số đo lại sau fix 6.2**: mất token trên tệp này giảm **7624/9364 (81.4%) → 24/9364 (0.3%)**. Nói
cách khác **phần MẤT NỘI DUNG của Critical #2 có chung nguyên nhân gốc với Critical #1** (lưới
nghèo do cắt bbox → `split_header_body` nuốt hàng vào header) và đã đóng theo.

**Phần CÒN LẠI vẫn thật, nhưng là lỗi CHẤT LƯỢNG, không phải mất nội dung**: trang văn xuôi vẫn bị
xử lý như bảng, nên câu văn được phát ra dưới dạng hàng-bảng giả với khung tên cột rác — trang 5
cho **0 block văn xuôi + 29 block atomic**, toàn tài liệu **10 block văn xuôi + 928 block atomic**,
mỗi block dạng:

```
Cột 1:  | x.: xi. | Cột 3:  | Screen and interview candidates.: Run background checks... | Cột 5:  | ... | Cột 12:
```

Mỗi câu thành một chunk atomic riêng (không gộp đoạn, không có `heading_level`), index đầy chuỗi
`"Cột 5: | Cột 6:"`. Xấu cho truy hồi — nhưng KHÔNG mất chữ.

**Vì sao cổng theo tỉ lệ nội dung KHÔNG dùng được — số đo, không phải phỏng đoán.** Đo tỉ lệ
`độ_dài(nội dung đường bảng) / độ_dài(nội dung pypdf toàn trang)` (đếm ký tự không-khoảng-trắng;
"nội dung đường bảng" = dải văn xuôi ngoài bbox + giá trị ô của các hàng THÂN thực sự được phát,
tức đúng thứ sống sót tới output) trên 93 trang bảng THẬT và 34 trang dương-tính-giả:

| nhóm | n trang | tỉ lệ min | tỉ lệ max |
|---|---|---|---|
| bảng THẬT (`ssc`, `bctc`, `thue`, `dautu`, hoá đơn) | 93 | **0.682** | 1.000 |
| dương tính GIẢ (`handbook`) | 34 | 0.766 | **1.000** |

**Hai nhóm chồng lấn hoàn toàn** — không có ngưỡng nào tách được. Nguyên nhân: sau fix 6.2, đường
bảng trên trang văn xuôi trích được gần như TOÀN BỘ chữ (~0.95 trung bình), cao hơn nhiều trang
bảng thật thưa ô (`thue` tr.25 = 0.682; `bctc` tr.24 = 0.743). Đo thêm 3 đặc trưng thay thế ở mức
từng bảng (127 bảng thật / 49 bảng giả) cũng đều chồng lấn:

| đặc trưng | bảng THẬT | dương tính GIẢ | tách được? |
|---|---|---|---|
| tỉ lệ ô có nội dung | 0.143 – 1.000 | 0.044 – 0.500 | KHÔNG (biểu mẫu `bctc` thưa tới 0.143) |
| trung bình ô đầy / hàng | 1.00 – 8.00 | 0.54 – 2.00 | KHÔNG |
| tỉ lệ cột rỗng hoàn toàn | 0.000 – 0.857 | 0.000 – 0.944 | KHÔNG |
| số cột | 2 – 10 | 2 – 27 | KHÔNG |

Theo đúng chỉ dẫn của brief ("nếu KHÔNG tìm được ranh giới sạch, đừng chọn liều một con số"),
**cổng khả tín KHÔNG được thêm vào mã**. Việc này trả lại controller quyết định hướng khác. Ứng
viên đáng thử tiếp (chưa đo): dựa vào **chứng cứ hình học** thay vì tỉ lệ nội dung — số đường kẻ
(`page.lines`/`rects`) thật sự bao quanh bbox, hoặc dùng `table_settings` chặt hơn
(`vertical_strategy="lines_strict"`) để `find_tables()` bớt dương tính giả ngay từ đầu.

### 6.4 Important #3 — hàng atomic RỖNG HOÀN TOÀN

`row_to_text` phát block cho mọi hàng thân, kể cả hàng mà MỌI ô đều rỗng (chỉ còn khung
`"Cột 1: | Cột 2: "`), làm loãng index.

| `bieumau_bctc_hopnhat.pdf` | trước | sau |
|---|---|---|
| tổng block | 2309 | 1335 |
| block atomic | 1625 | 651 |
| **atomic không mang giá trị nào** | **951 (58.5%)** | **0** |

Sửa: `hang_khong_gia_tri()` (thuần, trong `pdf_table.py`) + điều kiện lọc ngay trước
`blocks.append` trong `_khoi_bang`. Không cảnh báo — ô đệm rỗng của biểu mẫu không phải nội dung
bị mất, im lặng ở đây là đúng. (Lưu ý khi đọc bảng số: phần giảm 1625 → 651 gồm CẢ tác động của
fix 6.2, hai thay đổi cùng chạm lưới hàng nên không tách rời tuyệt đối được.)

### 6.5 Test cũ ĐỔI KẾT QUẢ — một, và có lý do

`test_parse_pdf_bang_that_moi_hang_la_mot_block_atomic` (live) khẳng định `warnings == []` cho
`ssc_bieumau.pdf`. Nay tệp này sinh 3 cảnh báo LOẠI MỚI "bất đồng số cột" (6 vs 4, trang 1-3) —
cảnh báo CỐ Ý của 6.2, không phải hồi quy. Chính chú thích của test đã dặn "nếu implementer đo ra
khác, SỬA assertion theo số thật, đừng ép về [] cho khớp dòng này". Ý định gốc của dòng đó là
"không có cảnh báo CHECKSUM", nên assertion được **thu hẹp đúng vào ý định** (`"đứt đoạn"`), kèm
một assertion mới chốt rằng mọi cảnh báo còn lại đều thuộc loại đã biết — chặt hơn, không nới lỏng.

### 6.6 Kết quả test

- `tests/rag/test_pdf_table.py` + `tests/rag/test_parse_pdf.py`: **51 passed** (kể cả live).
- `tests/rag/test_pdf_kho_that.py -m live`: **6 passed** — 4 bất biến có sẵn (100 hoá đơn, ssc
  checksum, ssc trùng lặp, bctc công thức) đều còn xanh, cộng 2 test mới của 6.2.
- `pytest -m "not integration and not live" -q`: **2337 passed, 1 skipped**.

---

# Tầng nạp tài liệu — ghi chú thực thi Tầng OCR bậc 1

**Ngày**: 2026-09-05. **Nhánh**: `worktree-tang-nap-tai-lieu-1`.
**Spec**: `2026-09-04-tang-ocr-bac-1.md` (implicit — plan `2026-09-05-tang-ocr-bac-1`, Task 5 NGHIỆM
THU: cổng tự nuôi + nghiệm thu corpus thật + ghi chú thực thi).

Task 5 là task ĐO THẬT — mọi con số dưới đây được CHẠY để biết, không suy đoán theo brief.

## 1. Kết quả

| | trước Task 5 | sau Task 5 |
|---|---|---|
| test suite mặc định | 2374 | **2380** (+6, đúng bằng 6 tham số hoá của cổng tự nuôi) |
| cổng tự nuôi trên PDF luật thật | không tồn tại | **6/6 PASSED**, ngưỡng đo thật `0,89` (không kế thừa số cũ `0,865`) |
| phép thử phá (PSM 3) | chưa từng chạy | cổng **BIẾT ĐỎ** — trang 20 tụt `0,9508 → 0,5902`, dưới ngưỡng |
| block OCR trên corpus thật (109 tệp) | — | **0** (đúng kỳ vọng — corpus 100% có lớp text) |
| byte-identical với bản trước OCR (commit `8085815`) | — | **khớp 100%** trên 3 tệp đại diện (1335+60+565 block) |

## 2. Khó khăn đã gặp

### 2.1 Ngưỡng cũ (0,865) đo trên tập trang KHÁC — không kế thừa được

Spec §4.1 ghi recall TB `0,865` nhưng đó là 3 trang bảng của MỘT tài liệu. Đo lại trên đúng 6 trang
brief chỉ định (2 tài liệu, có trang bảng khó) cho kết quả cao hơn hẳn:

| tệp | trang | recall theo từ | n từ gốc |
|---|---|---|---|
| `luat-thuegtgt.pdf` | 1 | **0,9905** | 317 |
| `luat-thuegtgt.pdf` | 5 | **0,9894** | 567 |
| `luat-thuexuatnhapkhau.pdf` | 3 | **0,9893** | 652 |
| `luat-thuexuatnhapkhau.pdf` | 6 | **0,9915** | 469 |
| `luat-thuexuatnhapkhau.pdf` | 13 (trang BẢNG) | **0,9473** | 607 |
| `luat-thuexuatnhapkhau.pdf` | 20 | **0,9508** | 549 |

min = `0,9473`, không có trang nào dưới `0,80` (không cần báo `NEEDS_CONTEXT`). Ngưỡng chốt theo đúng
công thức brief: `NGUONG = floor2(min − 0,05) = floor2(0,9473 − 0,05) = floor2(0,8973) = 0,89`. Biên
`0,05` là chỗ cho biến động máy/phiên bản tesseract — hai con số (`0,865` cũ và `0,976` mới) không
mâu thuẫn, chúng đo hai tập trang khác nhau.

### 2.2 Cảnh báo đã đo sẵn của controller ĐÚNG một phần — trang 13 chênh yếu, nhưng trang 20 chênh mạnh

Controller cảnh báo trước: đo trên máy này trang 13 cho PSM 6 = `0,947`, PSM 3 = `0,901` — chênh chỉ
`0,046`, yếu hơn spec cũ gợi ý (spec ghi TB `0,569`, có trang xuống `0,256`). Nếu chỉ nhìn trang 13,
đúng là ngưỡng `0,89` sẽ KHÔNG bắt được đột biến này (`0,901 > 0,89`) và phép thử phá sẽ không đỏ.

Đo đủ cả 6 trang với `engine.OCR_PSM = 3` (dùng `YOUDOO_OCR_CACHE` riêng để không lẫn đệm PSM 6):

| tệp | trang | recall PSM 6 | recall PSM 3 | chênh |
|---|---|---|---|---|
| `luat-thuegtgt.pdf` | 1 | 0,9905 | 0,9905 | 0,0000 |
| `luat-thuegtgt.pdf` | 5 | 0,9894 | 0,9912 | +0,0018 |
| `luat-thuexuatnhapkhau.pdf` | 3 | 0,9893 | 0,9923 | +0,0030 |
| `luat-thuexuatnhapkhau.pdf` | 6 | 0,9915 | 0,9915 | 0,0000 |
| `luat-thuexuatnhapkhau.pdf` | 13 | 0,9473 | 0,9012 | −0,0461 |
| `luat-thuexuatnhapkhau.pdf` | 20 | 0,9508 | **0,5902** | **−0,3606** |

Trang 13 khớp đúng số controller đã đo (chênh yếu, `0,901 > 0,89`, KHÔNG đỏ một mình). Nhưng trang 20
— không nằm trong cảnh báo trước — tụt từ `0,9508` xuống `0,5902`, cách ngưỡng `0,89` rất xa. Cổng
VẪN đỏ (test trang 20 FAIL với `NGUONG_RECALL = 0.89`), chỉ là bằng chứng đến từ trang khác với
trang controller đã soi. Không cần đổi sang đột biến mạnh hơn (`lang="eng"` hoặc DPI thấp) — PSM 3
đã đủ căn cứ chứng minh cổng biết đỏ, chỉ là bằng chứng nằm ở một trang khác dự đoán ban đầu. Đã khôi
phục `engine.OCR_PSM = 6` sau đo (đột biến chỉ chạy trong tiến trình python tạm, không sửa file
`engine.py`).

## 3. Giả thuyết bị số đo bác bỏ

- **"Nếu trang 13 (trang controller đã soi) không chênh đủ dưới ngưỡng, phép thử phá sẽ không đỏ và
  phải đổi đột biến mạnh hơn"** — sai một phần: trang 13 đúng là không đỏ một mình (`0,901 > 0,89`),
  nhưng trang 20 (nằm sẵn trong `TAP_TRANG`, không cần thêm trang mới) tụt mạnh (`0,5902`), đủ để cổng
  đỏ mà KHÔNG cần đổi sang đột biến khác. Cảnh báo của controller đúng ở dữ kiện (trang 13 chênh yếu)
  nhưng kết luận suy ra ("ngưỡng có thể không phân biệt được gì") không đúng cho TOÀN BỘ tập 6 trang.
- **"PSM 3 hỏng ĐỀU trên mọi trang"** — sai, đúng như engine.py đã ghi chú (spec §4.1): PSM 3 hỏng
  KHÔNG ĐỀU — 4/6 trang ở đây gần như không đổi (thậm chí một số nhích lên), chỉ 2/6 trang (bảng)
  tụt, và mức tụt giữa hai trang bảng đó lệch nhau gần 8 lần (`0,046` so với `0,361`). Đây chính là
  "cái đáng sợ" mà engine.py cảnh báo: PSM 3 không kém đều, nó kém KHÔNG BÁO TRƯỚC được trang nào.

## 4. Hướng đã chọn, và vì sao

| quyết định | vì sao |
|---|---|
| Ngưỡng `0,89` (đo thật), không giữ `0,865` (spec cũ) | Hai số đo hai tập trang khác nhau; giữ số cũ là kế thừa một phép đo không tái lập được trên tập trang cổng thật sự chạy. |
| Không đổi đột biến Step 4 sang `lang="eng"`/DPI thấp dù trang 13 chênh yếu | Trang 20 (đã có sẵn trong `TAP_TRANG`, không cần thêm ca) chênh `0,361`, đủ để cổng đỏ thật — đổi đột biến khi bằng chứng đã đủ là làm phức tạp thêm không cần thiết. |
| Giữ nguyên `TAP_TRANG` 6 trang của brief, không bớt trang 13 dù nó không tự đỏ | Trang 13 vẫn là ca khó thật (trang bảng, đường kẻ bị đọc thành ký tự) — bỏ nó khỏi tập cổng chỉ vì nó không tự đỏ ở một đột biến cụ thể là làm yếu cổng để "cho gọn", đúng lớp lỗi cổng này sinh ra để chống. |
| Dùng `YOUDOO_OCR_CACHE` riêng cho mỗi lượt đo (Step 1, Step 4) | Tránh đệm PSM 6 trả nhầm kết quả khi đo PSM 3 — đã xác nhận bằng số đo thật (Step 4 cho số KHÁC Step 1 trên cùng cặp tệp/trang, không phải số lặp lại từ đệm cũ). |

## 5. Giới hạn còn lại

### `mean_conf` quan sát được (tham chiếu chéo Task 2 + Task 4)

| nguồn | `mean_conf` |
|---|---|
| PDF luật THẬT (`luat-thuegtgt.pdf` tr.1, Task 2 Step 10) | **92,56** |
| PDF ảnh tự dựng bằng Pillow (Task 4 Step 9, font hệ thống, nền sạch) | **94,52** |

Hai số gần nhau nhưng đo hai thứ khác hẳn về độ khó — ảnh Pillow SẠCH HƠN cả PDF luật thật (chưa nói
tới scan đời thật), nên không suy luận "corpus scan thật cũng sẽ ~93-95" từ hai số này.

### Còn nguyên, nói thẳng

- **Chưa đo trên scan đời thật** (nhiễu, nghiêng, dấu mộc, mất góc). Cổng tự nuôi (Step 2) và phép thử
  phá (Step 4) đều dùng trang PDF ĐÃ CÓ lớp text rồi rasterise lại — ảnh sinh ra sạch hơn scan thật.
  Cổng này chứng minh "còn sống và đại khái đúng", KHÔNG chứng minh "chịu được scan đời thật".
- **Ngưỡng confidence để TỪ CHỐI một trang vẫn CHƯA CHỐT.** Bậc 1 (tầng đang có) chỉ từ chối khi text
  đọc ra RỖNG HẲN (không có ngưỡng `mean_conf` tối thiểu nào được áp dụng để loại trang đọc kém).
  Mọi ngưỡng conf khác (ví dụ "dưới X thì coi là đọc hỏng, cảnh báo thay vì âm thầm dùng") cần tài
  liệu scan thật để hiệu chỉnh — corpus hiện tại không có ca nào để đo.
- **Bậc 2 (dựng lại bảng từ toạ độ chữ) và bậc 3 (mô tả hình bằng VLM) chưa làm.** `Region`/`OcrWord`
  đã giữ toạ độ (`bbox`, `left/top/width/height`) đúng như spec §6 yêu cầu để hai bậc sau không phải
  đổi hình dạng artifact đệm, nhưng chưa có tài liệu scan thật (bảng/hình) để hiệu chỉnh thuật toán.
- **`TESSDATA_PREFIX` và đường dẫn binary tesseract vẫn là đường dẫn máy cá nhân** (`tesseract_path()`/
  `tessdata_prefix()` có fallback env → PATH → vài vị trí quen thuộc, giống `convert.soffice_path()`),
  nhưng máy khác vẫn cần cài tesseract + gói `vie.traineddata` riêng — nợ triển khai đã ghi từ kế
  hoạch 1, chưa đóng.
- **Corpus hôm nay có 0 tài liệu cần đọc bằng ảnh** (xác nhận lại ở Task 5: `TONG block OCR = 0` trên
  109 tệp quét). Nghĩa là toàn bộ tầng OCR bậc 1, kể cả cổng tự nuôi vừa dựng, CHƯA từng được thực thi
  bởi một tài liệu sản xuất thật — chỉ được chứng minh sống bằng dữ liệu TỰ SINH (rasterise-lại). Nếu
  một tài liệu scan thật xuất hiện trong corpus, đây là lần đầu tầng này chạy ngoài phòng thí nghiệm.
