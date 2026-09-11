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

## Nạp lại corpus sản xuất — 2026-09-06, đóng mục cuối của spec 2026-08-29 §10

Toàn bộ `A → B2 → B3 → B4 → B5(OCR bậc 1)` đã qua cổng, nên mục **"nạp lại toàn bộ corpus"** —
nằm TRONG phạm vi ngay từ spec `2026-08-29-tang-nap-tai-lieu.md` §10 và cố ý xếp cuối — được thi
hành. Nhánh `worktree-tang-nap-tai-lieu-1` merge vào `main` (`caebc7b`, 58 commit, không xung đột).

### Vì sao nó không phải việc dọn dẹp

Trước khi merge, chạy parser của nhánh trên đúng 17 tài liệu seed và so **từng chunk** với DB sản
xuất (do mã ngày 19/08 sinh ra). Kết quả:

| tệp | DB cũ | nhánh | Δ chunk | Δ ký tự |
|---|---:|---:|---:|---:|
| `luat-dautu.pdf` | 207 | 747 | **+540** | +15.433 |
| `luat-thuexuatnhapkhau.pdf` | 91 | 292 | **+201** | +11.679 |
| `luat-doanhnghiep.pdf` | 523 | 530 | +7 | −612 |
| `luat-baohiemxahoi.pdf` | 331 | 334 | +3 | +29 |
| 13 tệp còn lại | — | — | **0** | **0** |
| **TỔNG** | **3.151** | **3.902** | **+751 (+23,8%)** | |

13/17 tệp **byte-identical cả `chunk_text` LẪN `section_path`** — `section_path` được so riêng vì
nó chảy vào embedding qua `index_text()`, nên "chunk_text giống" chưa đủ để kết luận vector không
trôi. Cả 7 tệp `.docx` giống hệt: B3 không làm trôi vector của chúng.

741/751 chunk tăng thêm đến từ đúng 2 tệp phụ lục dạng bảng, khớp số đã đo ở §2.3 (898 và 621 ô
bảng thật). Nói thẳng: **~24% corpus đang thiếu, và giá trị của 58 commit với người dùng là 0 cho
tới khi nạp lại.**

### Nghiệm thu

- Live-verify TRƯỚC merge (theo lệ `feedback_test_before_merge`): chạy đúng CLI `python -m
  src.rag.ingest` của nhánh vào schema nháp `rag_nghiem_thu` — 3.902 chunk / 17 tài liệu, khớp đúng
  dự đoán đo ngoại tuyến. Đây cũng là lần đầu **đường cài MỚI** được chạy thật: schema dựng từ
  `schema.sql` (không qua migration), cột `source_kind`/`ocr_conf` có sẵn, 3.902/3.902 = `'text'`.
- Suite trên nhánh: 2387 passed. Suite trên **kết quả đã merge**: **2409 passed, 1 skipped**.
- Migration `007` chạy trên schema `public`: hai `ALTER TABLE IF EXISTS` thành công.
- Nạp lại sản xuất: `đã nạp 17 · không đổi 0 · chunk 3902 · từ chối 0 · cảnh báo 34`. Kiểm sau:
  rác `about:blank` = 0, mục-là-mảnh-câu = 0, `embedding` NULL = 0, `ts_vector` NULL = 0.
- Hợp đồng nhãn eval (`pytest tests/evals/ -m integration`): **6 passed** — mọi nhãn viết tay vẫn
  trỏ vào cặp `(tệp, section_path)` có thật sau khi corpus tăng 751 chunk. Đây đúng là thứ P0 dựng
  ra để bắt, và nó trả cổ tức lần thứ hai.
- Retrieval eval so baseline `bge-m3`: `recall@20` **1.0 → 1.0**, `recall@6` **0,9688 → 0,9688**,
  `MRR` 0,8646 → **0,8645** (−0,0001, nhiễu), `chunk_span` 2,55 → 2,56, 0 fail / 0 error.
  **Thêm 751 chunk mà không pha loãng truy xuất.**
- Bản lưu corpus cũ nằm ở schema `rag_luu_20260906` (3.151 chunk / 17 tài liệu), phòng khi cần đối
  chứng. Xoá được khi không còn cần.

### Bẫy đã bịt

`_ingest_file` bỏ qua tệp khi `content_hash` khớp, mà hash đó **chỉ của tệp nguồn, không mang dấu
vân tay phiên bản parser**. Tệp không đổi + mã đổi ⇒ báo `không đổi 17` và không làm gì, trong khi
trông như đã chạy xong. Đúng lớp lỗi khoá-đệm-thiếu-vân-tay-cấu-hình mà tầng OCR đã cố ý tránh khi
thiết kế `config_fingerprint()`.

Bẫy này ĐÃ được ghi trong plan `2026-08-19-ingest-hygiene.md:527` kèm cách vòng qua, nhưng nằm
trong một plan cũ **không ai đọc lại**, không có cờ trong mã, và `docs/getting-started.md` còn nói
ngược lại: *"re-running later is fast and safe"*. Đã sửa `getting-started.md` thành lời cảnh báo
tường minh kèm lệnh `DELETE FROM rag_documents;` và bước chạy hợp đồng nhãn eval sau đó.

**Chưa đóng**: vẫn không có cờ `--reindex` trong `src/rag/ingest.py`. Cách chữa đúng là đưa dấu vân
tay phiên bản parser vào khoá bỏ-qua (như `config_fingerprint()` của tầng OCR đã làm), để việc nạp
lại tự đúng thay vì phụ thuộc người vận hành nhớ một câu SQL. Chưa làm — ghi ra đây để lần sau
chạm vào `ingest.py` thì làm luôn.

### Giới hạn phát hiện khi nạp lại, KHÔNG phải hồi quy

`page` của chunk là **trang nơi MỤC bắt đầu**, không phải trang chứa chunk đó
(`chunking.py`: `cur_page` chỉ gán khi đang `None`, và reset ở mỗi heading). Với văn xuôi thì hợp
lý; với phụ lục bảng dài thì sai đáng kể — `luat-thuexuatnhapkhau.pdf` có **245 chunk cùng gắn
`page 12`** trong khi nội dung nằm rải trang 13–25, và chính parser đã in cảnh báo bảng ở đúng các
trang đó.

Đã đối chiếu `git show main:backend/src/rag/chunking.py`: **logic y hệt trước đợt này** — không
phải hồi quy do B4. Nhưng đợt này làm nó ĐÁNG KỂ hơn: trước đây các trang bảng gần như không sinh
chunk nào (nội dung mất), nên không có trích dẫn sai; giờ nội dung đã cứu được, kèm trích dẫn trang
lệch. Đổi mất-nội-dung-âm-thầm lấy có-nội-dung-trích-dẫn-thô — vẫn là lãi, nhưng phải nói ra.
`chunk_span` trong retrieval eval không bắt được lỗi này vì nó đo khoảng chunk, không đo đúng trang.

## OCR bậc 2 — dựng bảng từ toạ độ

**Ngày**: 2026-09-06/07. **Nhánh**: `worktree-ocr-bac-2`, base `372b1fe`.
**Spec**: `2026-09-06-b5b-ocr-bac-2-dung-bang-design.md` · **Kế hoạch**: `plans/2026-09-06-ocr-bac-2-dung-bang.md`
**Ledger**: `.superpowers/sdd/2026-09-06-ocr-bac-2-dung-bang/progress.md` (16 ruling P1–P16, kèm giá-nếu-sai từng cái).

Bậc 2 là một hàm thuần `backend/src/ocr/table.py::build_grid` — nhận `list[OcrWord]`
(toạ độ chữ Tesseract đã trả sẵn từ bậc 1), trả `list[list[str]]`. Không sửa chữ
trong ô, không dò bảng, không đọc tệp. Đây là mục ghi lại: thuật toán chốt là gì,
bốn cách khác đã thử rồi bị số đo bác bỏ, bốn lần chính cây thước đo tự nó hỏng,
và giới hạn còn mở.

### 1. Kết quả

Hai cổng nghiệm thu, ngưỡng suy từ số đo thật (không nhận số từ trên trời — cách
suy giữ nguyên từ bậc 1: làm tròn xuống hai chữ số của điểm thấp nhất quan sát
được trừ 0,05):

| cổng | tệp test | điểm 6/7 ca | thấp nhất | ngưỡng |
|---|---|---|---|---|
| A — tự nuôi, đa định dạng (vector rasterise) | `test_table_gate_vector.py` | phụ lục luật 1,0000 · biểu thuế 0,9714 · biểu mẫu BCTC 0,7179 · biểu mẫu SSC 0,8571 · hoá đơn (dòng) 0,9643 · hoá đơn (VAT) 0,9091 | 0,7179 (biểu mẫu BCTC) | `MATCH_THRESHOLD = 0,66` |
| B — scan thật (BCTC SCID, 7 trang) | `test_table_gate_scan.py` | tr12 0,8824 · tr13 0,8571 · tr14 1,0000 · tr15 0,8333 · tr16 0,8000 · tr17 0,7647 · tr18 0,8000 | 0,7647 (tr17) | `SAME_ROW_THRESHOLD = 0,71` |

Mỗi cổng có một phép **thử phá bắt buộc**: ép `GAP_FACTOR = 1000.0` (không khe
nào đủ lớn để thành ranh giới, mọi bảng suy biến về MỘT cột). Cổng B đo được cụ
thể ngay trước khi giao (P15): thước mới cho **0,847** ở tham số mặc định và
**0,000** ở cấu hình suy biến — rớt hẳn xuống dưới ngưỡng 0,71. Cả hai cổng đều
có test `test_break_check_...` khẳng định điểm suy biến phải thấp hơn điểm mặc
định trên cùng dữ liệu; cổng nào không đỏ ở đây thì coi như không đo gì (P6, P15).

Suite cuối (nạp toàn bộ `.env`, không phải bốn biến brief liệt kê — thiếu
`ODOO_URL` từng làm 65 test `tests/mcp/` chết oan, xem mục 6): **2438 passed, 1
skipped, 83 deselected**. So với nền `f84f3a6` (đã có Task 1–4, chưa có Task 5)
chạy cùng lệnh: **2435 passed** — chênh đúng **+3**, bằng đúng số test mới ở
Task 5. 0 failed cả hai lượt.

**Byte-identical** trên 4 tài liệu luật (`luat-dautu.pdf` 1583 block, `luat-
thuexuatnhapkhau.pdf` 565 block, `boluat-danssu.pdf` 4164 block, `luat-
thuegtgt.pdf` 437 block — băm SHA giống hệt cả 4 tệp, đối chiếu trước/sau Task
5). Phép kiểm chạy **hai lần, ở hai điểm so sánh khác nhau**:

- người thi hành Task 5 so với `f84f3a6` (đầu nhánh ngay trước Task 5) — đủ để
  chứng minh riêng Task 5 không làm trôi bit nào;
- điều phối viên so lại với **`372b1fe`, gốc của cả nhánh** — mạnh hơn, vì nó
  phủ luôn khả năng Task 1–4 vô tình chạm đường nạp. Cả 4 tệp khớp băm SHA.

Con số thứ hai mới là bất biến an toàn thật, và nó đạt. Ghi cả hai vì chúng trả
lời hai câu khác nhau, và vì bản báo cáo của Task 5 chỉ có con số thứ nhất.

Corpus sản xuất hiện có **0 tài liệu cần đọc bằng ảnh** (xác nhận lại ở Task 5),
nên bất biến này hiện chưa bị dữ liệu thật chạm tới — nó gác cho tương lai.

### 2. Thuật toán chốt, và bốn hướng đã thử rồi bị bác bỏ

**Thuật toán cuối** (`find_column_bounds` trong `table.py`): với mỗi dòng
(`line_id` Tesseract, không tự gom lại theo y), khe giữa hai từ liền nhau rộng
hơn `GAP_FACTOR × bề_rộng_ký_tự_trung_vị` là ứng viên ranh giới; vị trí ranh
giới lấy từ **mép** của từ cạnh khe (mép trái của từ sau khe, mép phải của từ
trước khe — không phải điểm giữa khe); các ứng viên cụm lại qua nhiều dòng
(ngưỡng ủng hộ = `SUPPORT_RATIO × số dòng`); cuối cùng bỏ ranh giới nào sinh cột
rỗng ở mọi hàng. Không có ranh giới nào ⇒ một cột ⇒ mỗi dòng một ô — đúng hệt
hành vi hôm nay, không có bộ dò bảng riêng để bắn nhầm.

Bốn cách khác đã thử và bị số đo bác bỏ, ghi lại để không đi lại:

**(a) Khe trắng chạy dọc suốt trang.** Đo trên BCTC scan thật (spec §2.1): trang
12/13/16/17 đều có 5 cột thật, nhưng khe trắng suốt trang chỉ tìm ra 3/3/1/1 —
một dòng tiêu đề hay chân trang chạy hết bề ngang là đủ bịt mọi khe.

**(b) Loại dòng "chạy suốt" trước rồi mới tính khe** — bản vá hiển nhiên cho (a).
Cũng hỏng: **0/4 trang loại được dòng nào**, vì dòng văn xuôi bình thường cũng
có khe giữa các từ vượt ngưỡng, không phân biệt được với dòng tiêu đề.

**(c) Cụm mép trái/phải làm cơ chế sơ cấp** (thiết kế gốc của Task 1, trước ruling
P1). Truy tay bằng chính test của Task 1: ba từ nhãn `"Tien"/"Hang"/"Khac"` cùng
`left=100, width=40` cho cụm mép trái tại 100 (3 từ) **và** cụm mép phải tại 140
(3 từ), cả hai đều vượt ngưỡng tối thiểu — ra 4 mốc trong khi test đòi 3. Sâu
hơn: mốc-mép không có khái niệm "nhiều từ trong cùng một ô" — khe giữa `"Tai"`
và `"san"` (cùng ô, 10px = 1 bề rộng ký tự) và khe sang cột số (300px) đều chỉ là
khoảng cách giữa hai mép, không thứ gì phân biệt được hai loại khe đó. Ruling:
đổi cơ chế sơ cấp sang **cụm KHE giữa các từ** (P1).

**(d) Cụm điểm giữa khe** (bản đầu của cơ chế cụm-khe, chạy tốt trên corpus
vector, dùng suốt Task 2–4 ban đầu). Hỏng trên scan thật (P11): nhãn chỉ tiêu
trên BCTC SCID kết thúc ở x khác nhau mỗi hàng, nên điểm giữa khe tản mát,
không bao giờ cụm. Đo được bằng thuật toán điểm-giữa cũ: trang 12 ra `[234]`,
trang 13 ra `[228]` (cả hai chỉ là rãnh sau số thứ tự, không phải cột thật);
**trang 17 ra `[]` — một cột, không tìm được ranh giới nào**. Đổi sang mép cạnh
khe (thuật toán cuối ở trên) ra đúng `930/965` (cột `Mã số`), `1300` và `1549`
— khớp chính xác số đo spec §2.2 (tiền căn phải ở x≈1290–1305 và x≈1545–1560).

### 3. Bốn lần thước đo tự nó hỏng

Bài học đắt nhất của đợt: bốn lần liền, con số thấp không phải vì thuật toán sai
mà vì cây thước đo tự nó không đo đúng thứ cần đo.

1. **Cổng A, lượt 1 (P4)** — thước so nguyên văn ở đúng chỉ số (hàng, cột) ra
   điểm cao nhất chỉ **0,1092**, dưới hẳn sàn 0,5. Đo lại bằng thước
   chỉ-cấu-trúc (bỏ ô tầng đọc không đọc nổi khỏi mẫu số, không đòi trùng chỉ
   số) cho **1/1 = 1,000** (`luat-dautu.pdf` tr.38) và **33/34 = 0,971**
   (`luat-thuexuatnhapkhau.pdf` tr.14) — thuật toán đúng ~97% trên phần đọc
   được; thước cũ gộp nhầm lỗi-đọc-chữ với lỗi-dựng-cột.
2. **Cổng A, lượt 2 (P6)** — thước sửa ở (1) chỉ đo MỘT vế ("không tách nhầm"),
   nên một lưới suy biến về một cột ăn điểm miễn phí: trên
   `luat-thuexuatnhapkhau.pdf` tr.14, `boi_khe=2.0`, `5.0`, và **1000,0** (thử
   phá) đều cho ra **cùng 0,9706** — thước không phân biệt được "đúng cột" với
   "không có cột nào". Sửa: thêm vế đối xứng "không gộp nhầm", điểm cuối lấy
   MIN của hai vế.
3. **Cổng B (P11a, xác nhận lại P15)** — thước nối cả hàng lưới thành một chuỗi
   rồi hỏi giá trị có nằm trong đó không. `GAP_FACTOR=3.0` và `GAP_FACTOR=1000`
   đều ra **95/98 = 0,969** — đúng ví dụ "cùng một điểm ở hai cấu hình cực đoan
   khác nhau" chứng minh thước vô hiệu. Thước sửa (đòi thêm mỗi giá trị ở một Ô
   KHÁC NHAU) phân biệt dứt khoát: mặc định **0,847**, suy biến **0,000**.
4. **Cổng A, lượt 3 (P9)** — thước phạt cả những ô có nội dung xuống dòng, dù
   spec §10 đã tuyên bố loại đó ngoài phạm vi bậc 2. `ssc_bieumau.pdf` tr.4 đi
   từ **0,3750** lên **0,8333** khi loại ô xuống dòng khỏi vế "giữ"; ba định
   dạng không có ô xuống dòng (`bieumau_bctc_hopnhat` tr.3, `luat-dautu` tr.42,
   `luat-thuexuatnhapkhau` tr.17) **không đổi một chút nào** — xác nhận đây là
   sửa đúng một giới hạn đã tuyên bố, không phải nới lỏng thước cho xanh.

**Nguyên tắc rút ra**: một thước đo chỉ đáng tin sau khi đã **thử phá** nó — ép
tham số về giá trị suy biến rõ ràng (ở đây luôn là "khe khổng lồ ⇒ một cột") và
xem thước có đỏ không. Thước còn phải **đối xứng**: đo cả hai hướng suy biến
(tách vụn lẫn gộp hết), vì chỉ đo một vế luôn có một hướng suy biến ăn điểm
miễn phí. Cả bốn lần trên đều bị đúng một lớp lỗi khác nhau của chính nguyên
tắc này.

### 4. Hai cổng đòi tham số khác nhau — vì sao bản scan thật thắng

Trên 234 trang bảng vector (107 tệp, quét lưới 6×5 `gap_factor`/`support_ratio`),
cấu hình MIN cao nhất là `GAP_FACTOR=3.0, SUPPORT_RATIO=0.6` (min 0,8746). Nhưng
đo thẳng số cột dựng ra trên 7 trang BCTC scan thật (tr12–18):

| `support_ratio` | số cột từng trang (12…18) |
|---|---|
| 0,6 | `[6, 6, 6, 1, 1, 1, 1]` — **4/7 trang sập về một cột** |
| 0,45 | `[6, 8, 6, 2, 5, 6, 1]` — 2/7 trang sập |
| **0,3** | `[9, 12, 8, 6, 8, 8, 5]` — **chạy trên mọi trang** |

(`gap_factor` gần như không ảnh hưởng trên scan — 1.0/2.0/3.0 cho kết quả gần
hệt nhau.) Đã chốt `GAP_FACTOR=3.0, SUPPORT_RATIO=0.3` — MIN trên corpus vector
tụt còn 0,8674 (≈0,007), đổi lấy việc bậc 2 chạy được trên 7/7 trang scan thay
vì chết trên 4/7. Bản scan thắng vì bảng **vector** đã đi qua `pdfplumber` ở B4
và không cần bậc 2 — bậc 2 sinh ra để xử lý đúng thứ `pdfplumber` không đọc
được, tức là scan; cổng vector chỉ là cổng còn-sống trên một proxy dễ hơn.

### 5. Giới hạn còn mở, nói thẳng

- **Tách hơi vụn trang 12–13 của BCTC scan**: ở `SUPPORT_RATIO=0.3`, hai trang
  này ra 9 và 12 cột trong khi thật sự chỉ có 5 — rãnh nội bộ trong ô đôi khi
  bị bắt nhầm thành ranh giới. Chấp nhận vì hỏng-vụn vẫn giữ được dữ liệu, khác
  hẳn hỏng-sập-về-một-cột là mất trắng cấu trúc.
- **25% ô của tầng đọc không đọc nổi** trên corpus vector (2.485/9.941 ô, chủ
  yếu bảng danh mục hoá chất trong phụ lục luật) — giới hạn của tầng đọc
  (Tesseract), không phải của bậc 2; bị loại khỏi mẫu số khi chấm điểm, đếm
  riêng chứ không lặng lẽ bỏ.
- **Cổng A không phủ tài liệu tiếng Anh thuần.** Đã tìm khắp kho (`tmp-docs` +
  `src/rag/seed/law` + `D:/Documents` + `backend/tests/rag/fixtures/*.pdf`): tài
  liệu tiếng Anh thuần duy nhất tìm được, `USA_Employee_Handbook`, có cả 34/34
  trang mà `pdfplumber` báo "có bảng" đều là dương tính giả (văn xuôi/mục lục bị
  nhầm thành bảng); `BOM.pdf` (114 trang) và fixture SOP (9 trang) không có
  trang nào pdfplumber thấy bảng. Định dạng thứ 6 trong cổng A vì vậy dùng bảng
  thứ hai (khối tổng hợp VAT) trên CHÍNH tệp hoá đơn đã dùng ở định dạng thứ 5
  — nội dung tiếng Anh thật, nhưng cùng nguồn tệp, không phải một tài liệu tiếng
  Anh độc lập. Ai cần phủ tiếng Anh độc lập phải bổ sung tệp mới vào kho.
- **Cổng A dùng ảnh rasterise sạch hơn scan đời thật** — giống hệt giới hạn của
  cổng tự nuôi bậc 1: chứng minh "còn sống và đại khái đúng trên nhiều định
  dạng", không chứng minh "chịu được scan đời thật".
- **Cổng B chỉ có MỘT tài liệu** (BCTC SCID), phẳng và sạch — chưa có tài liệu
  nghiêng, nhiễu, hay photo nhiều đời trong cả hai cổng.
- **Ô có nội dung xuống dòng ngoài phạm vi bậc 2** (spec §10): bậc 2 gom hàng
  theo `line_id`, nên một ô vắt qua nhiều dòng vật lý luôn nằm ở các hàng lưới
  khác nhau, kể cả khi cột tách hoàn toàn đúng. Cả hai cổng loại lớp ô này khỏi
  vế "kept"/"intact" và đếm riêng (`wrapped`/tương đương) thay vì lặng lẽ bỏ.

### 6. Hai lần suite đỏ mà KHÔNG phải hồi quy (P16)

Ghi lại để người sau khỏi hoảng khi gặp lại:

1. **21 failed + 65 errors** — do lệnh nạp biến môi trường chỉ lấy 4 biến
   (`DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED`), thiếu
   `ODOO_URL` mà test MCP cần → `KeyError: 'ODOO_URL'`. Nạp trọn `.env` là hết.
   Lỗi của lệnh đo, không phải của nhánh; tái lập được khi chạy một mình nên
   **không phải** lỗi giả do hai lượt pytest tranh schema.
2. **1 failed `test_cli_utf8.py::test_jobs_list_song_duoc`**
   (`AssertionError: b''`) — chạy riêng thì xanh trên cả gốc nhánh lẫn nhánh
   hiện tại; chạy lại suite đầy đủ cũng xanh. Test chập chờn dưới tải (output
   tiến trình con rỗng), không phải hồi quy.

### 7. Review toàn nhánh tìm ra HAI lỗi chặn merge — và một nửa mục tiêu vẫn chưa đạt

Mọi số ở các mục trên là **trước** review toàn nhánh. Review đó (chạy thật, không
đọc diff) tìm ra 2 Critical, 7 Important, 6 Minor. Phần này ghi trạng thái CUỐI.

**C1 — mục tiêu §1 không đạt trên chính tài liệu đích.** Bậc 1 luôn nhả đúng MỘT
`Region` phủ CẢ TRANG, nên `build_grid` chạy trên cả letterhead. Đo trên SCID
tr12: `column_names()` lấy ba dòng letterhead làm tên cột → **tên cột dài 136 ký
tự lặp trong MỌI block**; hàng header thật rơi xuống body; hai cột tiền thành
`Cột 6`/`Cột 8`. Kết quả **xấu hơn** hành vi trước đó. Test của Task 5 không thấy
vì nó nạp một lưới **dựng tay** đã lý tưởng — thứ `build_grid` không bao giờ sinh
ra trên trang thật.

**C2 — cổng B: 13/15 lần đỏ là ẢO.** `v in c` so **chuỗi con**: `'160'` nằm
trong `'15.618.160.768'`, `'05'` trong `'(38.320.042.505)'`. Độ đúng cấu trúc
thật ≈ 105/107 = 0,981 chứ không phải 0,847, và ngưỡng 0,71 suy từ trang 17 mà
**cả 4 lần trượt của trang đó đều ảo**.

Đợt sửa (một đợt duy nhất, 5 commit) đóng cả hai, cộng năm Important nữa:

| | trước | sau |
|---|---|---|
| letterhead thành tên cột | 136 ký tự rác/block | không còn; letterhead ra block văn xuôi 39–70 ký tự |
| cổng A ở cấu hình suy biến | 5/6 ca đỏ (`ssc_bieumau` tr4 XANH miễn phí 0,8333) | **6/6 đỏ**, ca đó về 0,0000 |
| ngưỡng cổng B | 0,71 (suy từ nhiễu) | **0,78** (min 5/6 = 0,8333 tại tr15) |
| hằng số bậc 2 trong vân tay đệm | không có | có, đổi hằng số là đổi vân tay |
| thước chấm điểm | nhân đôi, **hai bản đã lệch nhau** | gộp về `src/ocr/table_score.py` |
| trang lai | bảng vector bị bỏ ÂM THẦM, cảnh báo nói sai | pop cả hai, cảnh báo đúng sự thật |
| cổng B chạy sai cwd | sinh 0 test, không kêu | đường dẫn tuyệt đối + `assert` |

Suite cuối **2447 passed, 1 skipped, 0 failed**; byte-identical so với gốc nhánh
vẫn khớp trên cả 4 tài liệu luật.

**Nhưng mục tiêu §1 mới đạt MỘT NỬA — nói thẳng.** Trên scan thật, cột đã tách
đúng (`Cột 3` = chỉ tiêu, `Cột 4` = Mã số, `Cột 6`/`Cột 8` = hai cột tiền) nhưng
**tên cột vẫn là `Cột 1..N`**, không phải `CHỈ TIÊU`/`Mã số`/`Số cuối kỳ`/
`Số đầu năm`, kèm cột rỗng thừa và rác dấu mộc (`Cột 9: Sa`, `>>`, `ww`).
Nguyên nhân: dải hàng-trông-như-bảng bị hàng rác cắt khỏi hàng header thật, nên
`column_names()` không lấy được tên thật.

Nghĩa là câu mở đầu §1 — *"không biết số nào là cuối kỳ số nào là đầu năm"* —
**chưa được trả lời trọn**. Có ranh giới ô là hơn dòng phẳng, nhưng chưa phải
thứ spec hứa. Đây là việc còn lại, không phải việc đã xong.

**Gốc của nó là một lỗ trong chính bộ nghiệm thu**: cả hai cổng dừng ở
`build_grid`, **không cổng nào chạm** `split_header_body → column_names →
row_to_text` trên dữ liệu thật. Không ruling nào trong 18 ruling của đợt này hỏi
*"cuối cùng thì chuỗi text NÀO đi vào index?"*. Ai làm tiếp nên đóng lỗ đó trước.

Thêm hai giới hạn còn mở đáng biết:
- **tách vụn vô hình với cả hai cổng** ở ô một token: cổng B chỉ đòi các giá trị
  ở ô khác nhau nên tách bao nhiêu cột cũng đạt; cổng A vế "tách" cũng không
  phạt. Khẳng định cũ rằng "`pdf_table.py` hấp thụ được ô thừa" là **giả định
  chưa đo, và đo ra là sai**;
- `min_support` tính theo số dòng **CẢ TRANG**, nên một bảng nhỏ nằm trong trang
  dài không bao giờ đủ ủng hộ — bậc 2 hiện chỉ chạy trên trang *chủ yếu là bảng*.

### 8. Đo lại trên SÁU tài liệu scan: cổng B chưa bao giờ mô tả tài liệu, nó mô tả 7 trang tôi tự chọn

Sau khi nhánh đóng, kéo về **5 báo cáo tài chính scan thật** (vietstock/FPTS,
xem `tmp-docs/ocr-scan-that/README.md`) và đo lại cùng SCID. Phép đo **không
cần nhãn**: BCTC luôn có hai cột tiền, nên mỗi DÒNG chứa ≥2 chuỗi tiền phân
biệt là một hàng bảng, và câu hỏi §1 tương đương với "hai chuỗi đó có nằm ở hai
Ô KHÁC NHAU không". Đáp án đến từ chính tầng đọc chữ. So sánh dùng **token
chính xác** (bài học C2).

Kết quả ở cấu hình đang ship (`GAP_FACTOR=3.0, SUPPORT_RATIO=0.3`), 118 trang
bảng / **1.357 hàng** — so với 7 trang / ~107 hàng mà cả nhánh được gác trên đó:

| tài liệu | trang bảng | cột | TÁCH |
|---|---|---|---|
| PGI_2024 (HOSE) | 27 | 2–7 | 0,944 |
| DVT_2022 (UPCOM) | 6 | 4–8 | 0,889 |
| NTC_2025 | 18 | 2–10 | 0,839 |
| TDC_2022 (HOSE) | 22 | 1–9 | 0,682 |
| **SCID (tài liệu đã hiệu chỉnh trên đó)** | 28 | 1–12 | **0,668** |
| RBC_2024 (UPCOM) | 17 | 1–9 | **0,434** |
| **TỔNG** | 118 | | **0,774** |

**Phát hiện chính, và nó nói về bộ đo chứ không về thuật toán.** Tách SCID ra:

- 7 trang dùng làm đáp án (tr12–18): TÁCH **91/91 = 1,000**
- 21 trang bảng còn lại của **cùng tài liệu đó** (thuyết minh, tr33+):
  **124/231 = 0,537**, trong đó **9 trang sập hẳn về 1 cột**

Bảy trang ấy do chính tôi chọn hồi dựng đáp án, vì chúng là bốn bảng chính.
Chúng không chỉ dễ hơn — chúng là phần **duy nhất** chạy đúng. Cổng B chưa bao
giờ đo tài liệu; nó đo mẫu tôi đã chọn. Đây là lỗi chọn mẫu của tôi, không phải
lỗi người thi hành nào.

**Nguyên nhân, đã chứng minh:** `min_support = max(2, int(len(dong) *
support_ratio))` trong `find_column_bounds` lấy mẫu số là số dòng **CẢ TRANG**.
Trang thuyết minh có bảng nhỏ (6–12 hàng) nằm trong trang dài (40–52 dòng), nên
một ranh giới được 12/12 hàng bảng ủng hộ vẫn chỉ đạt 23% của trang → bị loại.
Đây đúng là Minor tôi đã **park nhầm** ở ruling R3; nó không nhỏ.

Quét lại `SUPPORT_RATIO` trên cả 6 tài liệu (OCR lấy từ đệm):

| support | TÁCH | trang sập | cột tối đa | ô đầy/hàng |
|---|---|---|---|---|
| **0,30 (đang ship)** | 0,774 | **12** | 12 | 2,46 |
| 0,20 | 0,905 | 3 | 14 | 3,03 |
| **0,15** | 0,965 | 1 | 18 | 3,55 |
| **0,12** | 0,976 | **0** | 18 | 3,81 |
| 0,10 | 0,981 | 0 | **24** | 4,21 |
| 0,08 | 0,987 | 0 | **30** | 4,73 |

Thước TÁCH **mù chiều tách vụn** (hai token ở ô khác nhau thì tách bao nhiêu cột
cũng đạt — đúng giới hạn R2), nên cột `ô đầy/hàng` là chiều ngược: một hàng BCTC
thật có ~4–5 ô (chỉ tiêu | mã số | thuyết minh | cuối kỳ | đầu năm). Ở 0,30 chỉ
đạt 2,46 → đang **gộp thiếu**. Từ 0,10 xuống, cột tối đa bật lên 24→30 → bắt đầu
**vụn**. Vùng lành là **0,12–0,15**.

Cổng A (corpus vector, 6 định dạng) **không bị phá** khi hạ: MIN còn tăng
0,6667 → 0,7143 (biểu mẫu SSC khá lên vì bảng nó nhỏ, đúng bệnh trên), chỉ phụ
lục luật tụt 1,0000 → 0,8750. Tất cả vẫn trên `MATCH_THRESHOLD=0.61`.

**Hai lời giải "hiển nhiên" đã nguyên mẫu hoá và BỊ BÁC BỎ** — ghi lại để không
ai thử lại:

1. *Hai lượt: dựng lưới thô → giới hạn ủng hộ vào dải hàng bảng.* Không sửa
   được DVT tr9 (dải vẫn 31/52 dòng vì hàng rác cũng có ≥2 ô đầy), lại đội số
   cột ở SCID tr12 (9→13), tr14 (8→12), tr18 (5→9) mà TÁCH không tăng.
2. *Ủng hộ = dải dòng LIÊN TIẾP dài nhất, thay cho % cả trang.* DVT tr9 sập về
   1 cột ở mọi ngưỡng k∈{4,5,6,8}; SCID tr18 và DVT tr15 hỏng theo.

**Trả lời cho câu "có nên làm adaptive không" (spec §6).** Phương sai **trong
một tài liệu** (1,000 vs 0,537) lớn ngang phương sai **giữa các tài liệu**
(0,434–0,944). Nên câu hỏi không phải "mỗi tài liệu một tham số" — mà là một
hằng số **tính theo tỉ lệ trang** vốn sai hình dạng cho bảng nhỏ trong trang
dài. Và một hằng số tốt hơn đóng được phần lớn khoảng cách (0,774 → 0,976).
Vậy §6 **vẫn đứng**: chưa cần adaptive. Nhưng lần này là kết luận có số đo,
trước đó chỉ là khẳng định.

**Giới hạn của chính phép đo này, nói thẳng:** (a) chỉ chấm hàng có ≥2 chuỗi
tiền — không nói gì về ô nhãn, và **không nói gì về TÊN cột**, tức lỗ hổng
`row_to_text` ở mục 7 vẫn nguyên; (b) cả 6 tài liệu đều là BCTC tiếng Việt —
"khác định dạng" ở đây nghĩa là khác công ty/kiểm toán viên/máy quét, không
phải khác thể loại tài liệu.

### 9. Hiệu chỉnh lại có HAI chân, và cổng B nay đo cả corpus

Sửa hai thứ mục 8 chỉ ra, theo đúng thứ tự đó.

**Bộ hiệu chỉnh nay có hai chân.** `calibrate_table.py` trước đây chỉ chạy trên
corpus vector; hằng số ra từ đó rồi bị tôi đè bằng mắt sau khi nhìn một tài
liệu scan (ruling P13). Nay chân scan nằm trong chính công cụ:

- chân **vector** có đáp án thật từ pdfplumber nên phạt được **tách vụn**;
- chân **scan** chạy trên ảnh thoái hoá thật nên phạt được **gộp nhầm**;
- điểm chốt = `min(hai chân)`. Không hệ số cân bằng nào bị bịa ra.

Lưới tham số nới xuống 0,05–0,12 vì vòng trước chốt đúng `ty_le=0.15` — **giá
trị thấp nhất từng thử**, tức lại là rìa lưới, đúng bệnh FIX ROUND 3 đã bắt ở
đầu kia.

| gap | ty_le | vector min | scan tách | sập | cột_max | GỘP |
|---|---|---|---|---|---|---|
| **3.0** | **0.15** | 0,9059 | 0,9648 | 1 | 18 | **0,9059** ← chốt |
| 3.0 | 0.12 | 0,9023 | 0,9757 | 0 | 18 | 0,9023 |
| 3.0 | 0.30 | **0,9156** | 0,7736 | **12** | 12 | 0,7736 ← đang ship |
| 2.0 | 0.60 | **0,9227** | 0,2303 | **82** | 6 | 0,2303 |
| thử phá | | 0,0365 | 0,0000 | — | — | 0,0000 |

Hai dòng in đậm là toàn bộ lý lẽ cho chân scan: `2.0/0.6` có **chân vector cao
nhất cả bảng** mà làm sập 82 trang scan. Và `3.0/0.3` đang ship cũng có chân
vector **cao hơn** cấu hình được chọn — nhìn riêng corpus vector thì thay đổi
này trông như đi lùi. Nó không lùi: scan mới là đầu vào thật của bậc 2, bảng
vector đã có pdfplumber lo.

**Cổng A**: min 0,6667 → 0,7143, `MATCH_THRESHOLD` 0,61 → 0,66. Biểu mẫu SSC
khá lên (bảng nó nhỏ — đúng bệnh vừa sửa), nhưng **phụ lục luật tụt 1,0000 →
0,8750**: một ô đáp án bị xé làm đôi. Đó là cái giá phải trả, ghi ra chứ không
giấu; nếu về sau nó tụt thêm thì là dấu hiệu đã hạ quá tay.

**Cổng B, 7 trang đáp án: KHÔNG ĐỔI MỘT CHÚT NÀO** — vẫn 93/94, ngưỡng vẫn
0,78. Nó không nhúc nhích giữa cấu hình sập 12 trang và cấu hình sập 1 trang.
Đó là bằng chứng cuối cùng rằng bảy trang ấy không đo được thứ cần đo.

**Chân thứ hai của cổng B: cả corpus scan, không đáp án.**
`table_score.score_unlabelled` + chọn trang bằng **bước nhảy cố định
`STRIDE=3`, không chọn tay** — chọn tay chính là cơ chế đã hỏng. Đo được:
tách 470/481 = 0,9771, 0/37 trang sập, mật độ ô 0,391; thử phá cho 0,0000 với
39/39 trang sập. Ngưỡng đặt 0,92 / ≤2 trang sập / mật độ ≥0,34 — hằng số **cũ**
cho 0,7137 và 6 trang sập, tức cổng này bắt được đúng lỗi nó sinh ra để bắt.

Thước đó trả về **bốn** số chứ không một tỉ lệ, có chủ ý: vế `separated` mù với
tách vụn (giới hạn R2), vế `filled/total` là vế ngược. Test
`test_shredded_grid_still_scores_full_on_separation_but_density_collapses` ghi
lại đúng điều đó để không ai rút gọn còn một vế.

**Một lo ngại tự đặt ra rồi tự bác bỏ, ghi lại vì kết quả ngược trực giác.**
`MIN_TABLE_ROW_CELLS=4` được hiệu chỉnh khi mỗi hàng có ~2,46 ô đầy; hằng số
mới nâng lên ~3,55 nên nhiều hàng hơn qua được `is_table_like_row`, có nguy cơ
kéo văn xuôi vào đường lưới và làm **hồi quy bản sửa C1**. Đo trên scan thật:

| support | min_cells | hàng bảng THẬT vào đường lưới | văn xuôi bị kéo vào | tỉ lệ |
|---|---|---|---|---|
| 0,3 (cũ) | 4 | 85 | 121 | 0,70 |
| **0,15** | **4** | **191** | 232 | **0,82** |
| 0,15 | 6 | 69 | 74 | 0,93 |

Hằng số mới đưa **gấp đôi** hàng bảng thật vào đường lưới và tỉ lệ cũng tốt
lên. Nâng `min_cells` lên 6 làm tỉ lệ đẹp hơn nhưng vứt mất 2/3 hàng bảng
thật. **Giữ `min_cells=4`.** Văn xuôi bị xé thành cột là bệnh có sẵn ở CẢ HAI
cấu hình (121 hàng ở cũ, 232 ở mới) — nó thuộc về lỗ `row_to_text`, không phải
về hai hằng số này.

**Chỗ cả hai chân hiệu chỉnh đều MÙ, nói thẳng:** không chân nào đo việc văn
xuôi bị đối xử như bảng. Chân scan chỉ chấm hàng có ≥2 chuỗi tiền (văn xuôi
không có); chân vector chỉ chấm bên trong khung bảng pdfplumber. Bảng đo ngay
trên là thứ duy nhất hiện chạm tới, và nó là script rời chứ chưa phải cổng.

Suite **2456 passed, 1 skipped, 0 failed**. Byte-identical so với gốc nhánh
`372b1fe`: 4/4 tài liệu luật khớp băm.

### 10. Đóng lỗ `row_to_text`: tên cột 0,301 → 0,611, và cổng đầu tiên chạm chuỗi text

Mục 7 nêu lỗ hổng sâu nhất của nhánh: **không cổng nào chạm chuỗi text thật sự
đi vào index**. Cả hai cổng dừng ở `build_grid` — chứng minh các *ô* đã tách
đúng, không chứng minh cái gì **dán nhãn** cho chúng.

Đo lần đầu, thước không cần đáp án (hàng có ≥2 chuỗi tiền phân biệt; hỏi
`row_to_text` gán cho chúng nhãn gì; đạt khi cả hai nhãn không phải `Cột N`
**và** khác nhau): **98/326 = 0,301** trên 95 trang / 6 tài liệu. Bảy mươi phần
trăm hàng bảng đi vào index dưới dạng `Cột 9: 566.695.646.268 | ... | Cột 12:
534.044.474.982`. Đó đúng là câu mở đầu spec §1.

**Hai nguyên nhân, đo được đến từng hàng:**

1. *Một ký tự rác cắt lìa header khỏi thân.* SCID tr12 hàng 11 **là** header
   thật (`CHỈ TIÊU | số | minh | Số cuối kỳ | Số đầu năm`, 6 ô đầy); hàng 12
   chứa **đúng một** ký tự `C` — vệt dấu mộc. Hàng 11 thành dải dài 1 <
   `MIN_TABLE_RUN_ROWS` nên bị vứt, thân bắt đầu lại ở hàng 13 với 0 hàng
   header, `column_names([])` trả rỗng, mọi cột thành `Cột N`.
2. *Một token số lạc biến letterhead thành tên cột.* `split_header_body` coi
   MỌI hàng trước hàng-có-số-thuần đầu tiên là header. SCID tr13 có số lạc
   trong letterhead → nó tuyên bố thân đã bắt đầu → header thật rơi vào thân,
   tên cột thành `'TY CỔ PHẦN ĐẦU Số 199-205 Nguyễn Thái TÀI CHÍNH HỢP'`. Đây
   là **họ hàng gần của C1**, thu nhỏ từ cả trang xuống một dải.

**Sửa**: `table_row_runs` bắc cầu qua tối đa `MAX_RUN_GAP_ROWS=1` hàng, và
`find_header_rows()` tìm header theo **nội dung** (≥3 ô đầy, **không** chứa
chuỗi tiền, trong cửa sổ `HEADER_SEARCH_ROWS=3` phía trên thân).

| bắc cầu | cửa sổ header | tên cột có nghĩa |
|---|---|---|
| — | — | 98/326 = 0,301 |
| 1 | — | 165/383 = 0,431 |
| — | 3 | 153/326 = 0,469 |
| **1** | **3** | **234/383 = 0,611** |
| 1 | 6 | 235/383 = 0,614 |
| 2 | 3 | 222/404 = 0,550 |

Hai hằng số chốt trên **cả corpus**, không trên 7 trang đáp án — đúng lỗi vừa
mất cả ngày để chẩn đoán ở mục 8. Số corpus (0,301 → 0,611) còn **nhỉnh hơn**
số trên 7 trang (0,273 → 0,574): lần này không có hiệu ứng chọn mẫu.

**Cổng thứ ba** (`test_money_columns_get_meaningful_names_in_final_text`) là
cổng đầu tiên trong cả nhánh chạm `split_header_body → column_names →
row_to_text`. Ngưỡng 0,56; thử phá tắt **cả hai** cơ chế thì rơi về 0,301,
dưới ngưỡng.

**Hai test cũ về `table_row_runs` phải viết lại, và lý do đáng ghi.** Chúng mã
hoá hành vi không-bắc-cầu. Một cái giờ dùng khe 2 hàng để vẫn đo đúng điều nó
định đo; cái kia giữ bất biến **"hai bảng rời nhau không được gộp"** — đó là
rủi ro **có thật** mà bắc cầu tạo ra (hai bảng cách nhau đúng một dòng sẽ gộp,
bảng sau mượn tên cột của bảng trước). Thêm một test mới ghi rõ việc bắc cầu
là **cố ý**, kèm ca SCID tr12.

**Ca xấu nhất, mổ ra chứ không làm tròn.** Từng tài liệu: NTC 0,869 | DVT
0,680 | TDC 0,673 | SID 0,591 | PGI 0,585 | **RBC 0,091**. RBC tr13 hàng 8–9
*là* header đọc được (`m Chỉ tiêu | ... | Năm trước`, rồi `số | minh`), nhưng
vệt dấu mộc chèn một hàng rác giữa **gần như mọi** hàng thân (hàng 12, 13 chỉ
2 ô đầy), nên `max_gap=1` không đủ và dải vỡ vụn; dải sống sót `(14,32)` bắt
đầu *dưới* header. `max_gap=2` cứu RBC nhưng kéo tổng corpus xuống 0,550 —
đánh đổi thật, để số corpus phân xử chứ không chọn theo ca yêu thích.

**Còn lại chưa đóng:** 39% hàng bảng vẫn mang tên cột vô nghĩa; và văn xuôi
vẫn bị xé thành cột (`Cột 2: Bảo cáo | Cột 3: này phải được doc cùng | ...`) —
bệnh có sẵn từ trước, không chân hiệu chỉnh nào đo được nó (mục 9).

Kiểm C1: block dài nhất **818 → 326**, thấp hơn cả mức trước khi đổi
`SUPPORT_RATIO` (348). Suite **2464 passed, 1 skipped, 0 failed**.
Byte-identical so với `372b1fe`: 4/4.

### 11. Văn xuôi bị xé thành cột — chỗ mù cuối cùng, và nó là lỗi định tuyến

Mục 9 và 10 đều kết thúc bằng cùng một câu: **không chân hiệu chỉnh nào đo
được việc văn xuôi bị đối xử như bảng.** Chân scan chỉ chấm hàng có ≥2 chuỗi
tiền (văn xuôi không có); chân vector chỉ chấm bên trong khung bảng pdfplumber.

Thước cho nó, vẫn không cần nhãn: **hàng thân đi qua đường lưới mà không chứa
chữ số nào**. Hàng bảng tài chính thật gần như luôn mang mã số hoặc tiền; hàng
sạch chữ số gần như chắc là văn xuôi lọt vào dải.

Đo được: **633/1980 = 32,0%**. Chuỗi thật đi vào index:

```
Cột 1: a | Cột 2: Il. | CHỈ TIÊU: Lưu chuyển tiền từ hoạt | Cột 4: động đầu tư
':  | Cột 2: Báo | VÕ THỊ KIM LANG: cáo này phải được doc cing với Bản
| |} I ) \:  | TRUNG Thuyết Dia Cho:  | TAM ĐÀO TẠO NGHIỆP VỤ GIAO THONG minh
```

Dòng thứ hai là câu *"Báo cáo này phải được đọc cùng với Bản thuyết minh..."* bị
băm làm đôi và **dán nhãn bằng tên người** (kế toán trưởng, đọc lệch cột).

**Đây không phải bài toán hiệu chỉnh mà là lỗi định tuyến.** Không có đường
cong đánh đổi để dò: hàng không mang dữ liệu số thì không nên bị xé thành cột,
chấm hết. Sửa: `table.has_numeric_data(row)` và trong `_khoi_tu_luoi_anh`, hàng
thân không có số đi **đúng đường dòng-phẳng** như hàng ngoài dải — qua
`heading_level()` và qua bộ lọc furniture. Đường phẳng đó tách thành
`_flat_line_block()` vì nay có hai chỗ gọi.

| | trước | sau |
|---|---|---|
| block văn xuôi bị xé (≥2 nhãn cột, 0 chữ số) | 633 hàng | **0 / 4.722 block** |
| tên cột có nghĩa | 0,6110 | **0,6110** (không đổi) |
| tách hai cột tiền | trên lưới | không đụng lưới, không thể hồi quy |

**Cổng thứ tư** khẳng định bất biến đó (không ngưỡng), kèm thử phá: ép
`has_numeric_data` luôn trả `True` thì block xé văn xuôi quay lại — nếu không
quay lại thì cổng không đo gì.

Suite **2469 passed, 1 skipped, 0 failed**. Byte-identical `372b1fe`: 4/4.

**Trạng thái bậc 2 sau bốn mục 8–11**, tất cả đo trên 95 trang / 6 tài liệu:

| số đo | trước 2026-09-07 | nay |
|---|---|---|
| tách hai cột tiền | 0,774 | **0,977** |
| trang sập về 1 cột | 12 | **0** |
| tên cột có nghĩa | 0,301 | **0,611** |
| văn xuôi bị xé thành cột | 633 hàng | **0** |

Còn mở, không giấu: **39% hàng bảng vẫn mang tên cột vô nghĩa**, xấu nhất là
RBC_2024 (0,091 — vệt dấu mộc chèn hàng rác giữa gần như mọi hàng thân, xem
mục 10). Và cả bốn số trên đều đo trên **báo cáo tài chính tiếng Việt**; "khác
định dạng" ở đây nghĩa là khác công ty/kiểm toán viên/máy quét, chưa phải khác
thể loại tài liệu.

### 12. Nạp thật lần đầu, và cái mà chỉ sản xuất mới chỉ ra được

Sau khi merge bậc 2, nạp bản scan SCID vào corpus sản xuất: **968 chunk OCR**,
0 từ chối, 0 cảnh báo, `ocr_conf` trung bình 82,0. Đây là lần đầu tiên corpus
có chunk `source_kind='ocr'` — trước đó **3902/3902 là `text`**, tức cả tầng
OCR chưa từng chạy thật một lần nào. Dự án này đã trả giá bốn lần cho đúng lớp
lỗi đó (reranker chết 6 tuần, chân sparse chết từ ngày đầu, mail tool chết với
mọi vai không phải admin, cơ chế xác nhận ghi chết hẳn trong prod).

Ba câu hỏi vào retriever thật, so với giá trị trong đáp án đã duyệt:

| câu hỏi | trước | sau |
|---|---|---|
| tiền và tương đương tiền **cuối kỳ** năm nay | hạng 1 | hạng 1 |
| tiền và tương đương tiền **đầu năm** | hạng 1 | hạng 1 |
| **tài sản ngắn hạn cuối kỳ** | KHÔNG có trong ứng viên, kể cả k=50 | **hạng 4** |

Chunk trả về tự mang câu trả lời và phân biệt được hai kỳ:

```
CHỈ TIÊU: Tiền và tương đương tiền cuối kỳ | số: 70 | Nam nay: 148.058.124.948
```

**Câu trượt chỉ ra một thứ không cổng nào bắt được**: nó trượt vì *recall*, hàng
đúng không vào nổi tập ứng viên. Hai nguyên nhân chồng nhau — tầng đọc rụng dấu
(`TÀI SẢN NGẮN **HAN**`), và **37,7% số ô** trong chunk bảng là ô rỗng mang nhãn
`Cột N`, chiếm **20,6% độ dài chunk**. Đó không phải rác vô hại: nó đi thẳng vào
vector nhúng và pha loãng tín hiệu. Một phần năm mỗi chunk là `Cột 5: | Cột 7: |
Cột 10: |`.

Không cổng nào của bậc 2 thấy được chuyện này, và không thể thấy: cả bốn chân
đều dừng ở *cấu trúc lưới* và *chuỗi text*, không chân nào đo **truy xuất**.
Chỉ nạp thật mới lộ ra.

**Sửa**: `row_to_text(..., compact=True)` bỏ đúng hai thứ không mang thông tin —
ô rỗng, và nhãn `Cột N` khi ô có giá trị (giữ giá trị, bỏ nhãn). Cắt 39,2% độ
dài. Sau khi nạp lại: **0 chunk còn nhãn `Cột N:`**.

Ba lựa chọn thi hành đáng ghi:
- **Tham số trên chính `row_to_text`, không phải bản dựng text thứ hai trong
  `parse.py`** — hai bản chép tay sẽ lệch nhau, đúng phát hiện I6.
- **Mặc định TẮT** nên đường bảng vector và .docx không đổi một byte; bất biến
  byte-identical so với `372b1fe` vẫn 4/4.
- **Cổng đặt tên phải sửa theo.** Nó đang gọi bản không-`compact`, tức đo một
  chuỗi KHÁC chuỗi đi vào index. Tệ hơn: với `compact`, giá trị mang nhãn chung
  xuất hiện **trần không nhãn**, mà bộ phân tích cũ lại tính đoạn không có
  `': '` thành "có nhãn có nghĩa" — cổng sẽ tự xanh lên mà không ai sửa gì. Đã
  sửa để đoạn không nhãn tính là vô nghĩa; số đo giữ nguyên 234/383 = 0,6110.

Suite **2474 passed, 1 skipped, 0 failed**.

**Còn lại**: nguyên nhân thứ nhất của câu trượt — dấu tiếng Việt rụng khi scan —
vẫn nguyên. Cổng tự nuôi bậc 1 chỉ chạy trên **ảnh rasterise sạch** và tự khai
điều đó trong docstring; giờ đã có bằng chứng nó làm hỏng truy xuất thật.

### 13. Spike: lexicon khớp mờ vs LLM sửa nhãn — đo cả hai, cả hai chiều

Câu hỏi: có nên cho LLM làm giàu/sửa nhãn chỉ tiêu đọc từ scan không.

**Tập thử**: 78 cặp `(nhãn OCR, nhãn đúng)` từ 7 trang SCID có đáp án đã duyệt,
ghép qua **mã số** (duy nhất mỗi hàng) chứ không qua giá trị tiền — bản ghép
đầu tiên dùng tiền và sai nhiều, vì trong BCTC một dòng tổng và dòng thành phần
duy nhất thường **bằng nhau**, nên nhiều cặp bị ghép nhầm và mọi cách đều bị
chấm oan. 51 nhãn OCR đọc đúng sẵn, 27 sai.

**Thước đối xứng, bắt buộc**: sửa đúng bao nhiêu trên 27 nhãn sai, **và** làm
hỏng bao nhiêu trên 51 nhãn đang đúng. Một bộ sửa được 19 mà phá 27 là lỗ.

| cách | sửa đúng | làm hỏng | chi phí |
|---|---|---|---|
| A1 — lexicon 174 nhãn, khớp mờ | 19/27 = 70,4% | **0/51** | 0, tất định |
| A2 — lexicon **thiếu** nhãn thật | 0/27 | **27/51** | 0 |
| B1 — LLM, không lexicon | 22/27 = 81,5% | **0/51** | ~5k token/tài liệu |
| **B2 — LLM + lexicon trong prompt** | **24/27 = 88,9%** | **0/51** | ~30k token/tài liệu |

**Điểm mấu chốt không phải độ chính xác mà là độ bền.** A1 hơn kém B1 có 3 ca,
nhưng A **sụp hoàn toàn** khi nhãn không có trong lexicon: không sửa được gì
*và* kéo 27/51 nhãn đang đúng về mục sai. B1 không cần lexicon nào. Với tài liệu
ngoài BCTC — nơi không có từ vựng đóng — A không dùng được, B vẫn chạy.

Cả ba chế độ LLM **không làm hỏng nhãn nào** (0/51): chỉ dẫn "nếu đã đúng thì
trả nguyên văn" giữ được.

**Trần của việc sửa chữ là 24/27, và 3 ca còn lại nói lên vấn đề thật.** Cả ba
là ô lưới chỉ chứa **mảnh đuôi** của nhãn xuống dòng — `đơn vị khác` là phần
cuối của *"Tiền chi cho vay, mua các công cụ nợ của đơn vị khác"*. Thông tin
không có trong đầu vào; không cách nào khôi phục. Và ở hai ca đó LLM sinh nhãn
**sai nhưng nghe thuyết phục** (`Dự phòng tổn thất đầu tư vào đơn vị khác dài
hạn`). Trong một chunk, nhãn sai-mà-nghe-đúng hại hơn nhãn bị cắt.

**Phân loại 27 ca sai — đây mới là thứ đổi thứ tự việc:**

| loại | số ca |
|---|---|
| **nhãn bị CẮT vì xuống dòng** | **18** |
| đọc nhầm ký tự | 8 |
| khác | 1 |

Hai phần ba là **cấu trúc**, không phải tầng đọc. Cả A lẫn B chỉ *đoán bù* phần
bị cắt; một bản sửa ô-xuống-dòng (gộp dòng gãy vào một hàng lưới) sẽ đóng trọn
18 ca **mà không phải đoán**, đồng thời xoá luôn rủi ro bịa nhãn ở đó.

**Đính chính hai điều tôi đã nói sai trong phiên này:**
1. "Dấu tiếng Việt rụng là việc OCR tiếp theo rõ nhất" — dựa trên **một từ**.
   Đo tử tế: 91,7% nhãn đọc đúng ở mức text phẳng.
2. "Nên làm lexicon trước, LLM chưa đáng" — số đo nói **ngược lại**: LLM hơn cả
   về độ chính xác lẫn độ bền, và không có chế độ hỏng thảm hoạ như A2.

**Chi phí thật nếu bật LLM**: 16 lượt gọi/tài liệu (12 nhãn/lô). Hạn mức free
RPD 500/khoá ⇒ ~31 tài liệu/ngày/khoá, **dùng chung hồ với chatbot**. B2 tốn
gấp 6 lần token của B1 để đổi 2 ca — B1 gần như chắc chắn đáng giá hơn.

**Khuyến nghị theo thứ tự**: sửa ô-xuống-dòng trước (đóng 18/27, tất định,
không hạn mức), rồi đo lại xem 8 ca đọc nhầm còn lại có đáng gọi LLM không.

#### 13b. Đính chính mục 13 — tập thử của tôi sai, và số đổi trọng yếu

Mục 13 trích nhãn OCR bằng **ô dài nhất** trong hàng lưới. Sai: nhãn xuống dòng
nằm rải sang **ô kế bên cùng hàng**, và `row_to_text` phát ra hết, nên chunk
production **đã có đủ nhãn**. Ví dụ mã 110 — chunk thật là
`Cột 3: Tiền và các khoản tương | CHỈ TIÊU: đương tiền`, đủ cả.

Đo lại với nhãn = **nối mọi ô không-phải-số** (đúng thứ vào chunk) và tiêu chí
**chứa** thay vì bằng:

| | mục 13 (sai) | đo lại |
|---|---|---|
| nhãn thiếu/sai | 27/78 = 35% | **14/78 = 18%** |
| trong đó: bị cắt | 18 | **5** |
| trong đó: đọc nhầm ký tự | 8 | **9** |

Tỉ lệ **đảo ngược**: đọc nhầm mới là phần chính, không phải cắt. Kéo theo đó,
khuyến nghị "sửa ô-xuống-dòng trước" ở mục 13 **không còn đứng vững** — nó chỉ
chạm 5 ca, và 3 trong số đó là mảnh đuôi mà phần đầu nằm ở hàng lưới khác.

Bảng so sánh chấm lại theo tiêu chí chứa:

| cách | sửa đúng | làm hỏng | ròng |
|---|---|---|---|
| A1 — lexicon đủ (ngưỡng 0,70) | 8/14 | **5/64** | +3 |
| A2 — lexicon thiếu nhãn | 0/14 | **38/64** | −38 |
| **B1 — LLM, không lexicon** | **10/14** | **0/64** | **+10** |
| **B2 — LLM + lexicon** | **11/14** | **0/64** | **+11** |

Lexicon tụt hẳn khi chấm trung thực: nó **thay** cả nhãn đang đúng bằng mục
gần giống, nên vừa sửa 8 vừa phá 5. LLM không phá ca nào ở cả hai chế độ.

**Kết luận sau khi sửa phép đo**: LLM thắng rõ, và B1 lấy được 10/11 phần
thưởng với **1/6 chi phí token** của B2. Phần được: ~18% nhãn hàng bảng đang
thiếu, LLM đóng được ~14%. Ba ca còn lại là mảnh đuôi — không cách nào khôi
phục từ đầu vào, cần gộp hàng lưới trước.

**Bài học của chính mục này**: hai lần liên tiếp tập thử của tôi tạo ra kết
luận sai — lần đầu ghép hàng qua giá trị tiền (dòng tổng và dòng thành phần
duy nhất bằng nhau), lần hai trích nhãn bằng ô dài nhất. Cả hai đều làm phép đo
BI QUAN hơn thực tế và suýt dẫn tới xây nhầm thứ. Cùng lớp lỗi "thước không đo
thứ mình tưởng" đã đếm được năm lần trong nhánh bậc 2.

### 14. Đo bộ vàng cho nội dung OCR — và một lỗ hổng LỚN HƠN lộ ra

**Việc định làm**: thêm ca vào bộ vàng truy xuất cho tài liệu scan, vì cả 64 ca
hiện có đều hỏi về corpus cũ, **không ca nào chạm nội dung OCR**.

**Chặn kỹ thuật đầu tiên**: `label_of()` neo nhãn theo `(tên tệp, section_path)`,
mà `section_path` của chunk OCR là **rác** — 100 giá trị riêng biệt gồm `Z`,
`Chương trình › HRT HE.`, `| : THẾ`, cùng các biến thể chỉ khác nhau ở lỗi dấu
(`HỢP NHAT` / `HỢP NHÁT` / `HỢP NHẮT`). Neo vào đó sẽ gãy ngay khi đổi tham số
OCR. Ca cho nội dung OCR phải chấm bằng **giá trị chính xác từ đáp án đã
duyệt**, không phải bằng `section_path`.

14 ca sinh bằng **quy tắc** (mỗi trang lấy 2 hàng có nhãn dài nhất), không chọn
tay. Đo trên corpus thật:

| dạng truy vấn | top-5 | top-20 |
|---|---|---|
| có dấu | 9/14 | 11/13 |
| **không dấu** | **2/14** | **3/14** |

**Chênh lệch đó không phải chuyện của OCR.** Đo lại trên **bộ vàng 64 ca hiện
có**, dùng đúng `score_one` + `label_matches` của eval chính thức (bản có dấu
tái lập chính xác 1,0000 / 0,9688 nên harness đã được kiểm chứng):

| | recall@20 | recall@6 |
|---|---|---|
| có dấu (đối chứng) | 64/64 = **1,0000** | 62/64 = 0,9688 |
| **không dấu** | 1/64 = **0,0156** | **0/64 = 0,0000** |

**Toàn bộ tầng truy xuất sập khi người dùng gõ tiếng Việt không dấu.** Không
phải trả về rỗng mà trả về **sai hẳn**: câu *"chinh sach doi tra hang nhu the
nao?"* trả về ba chunk báo cáo tài chính SCID.

Truy nguyên xem OCR có gây ra không — **không**:

| | chunk SCID chiếm top-20 | bỏ SCID ra thì recall@20 |
|---|---|---|
| có dấu | 2,5% | 1,0000 |
| không dấu | **80,4%** | **0,0156** |

Bỏ hẳn SCID vẫn 1/64. Lỗi có sẵn từ trước; tài liệu OCR chỉ **lấp đầy chỗ** vì
text méo của nó gần với truy vấn méo hơn là tài liệu sạch. Nói cách khác OCR
làm lỗi này *dễ thấy hơn*, không làm nó *nặng hơn*.

**Vì sao chưa ai thấy**: bộ vàng 64 ca **100% có dấu**. Không ca nào đo dạng
gõ không dấu. Chân sparse (FTS) — thứ lẽ ra bắt được khớp mặt chữ — đã chết từ
đầu (0/64 truy vấn có kết quả) và hồi sinh nó từng đo được là CÓ HẠI, nên hệ
chạy **dense-only**; không có tầng nào bắt chữ khi nhúng trượt.

**Chưa biết, phải hỏi chủ dự án**: người dùng thật của Youdoo có gõ không dấu
không. Nếu có thì đây là lỗi nghiêm trọng nhất đang mở, trên mọi mục trong lộ
trình. Nếu không thì nó vẫn cho thấy truy xuất **giòn** trước sai sót dấu.

Bộ 14 ca OCR đã sinh và đo xong, **chưa đưa vào `evals/`** vì còn phụ thuộc một
quyết định: tài liệu scan hiện nạp từ `D:/downloads`, không nằm trong `seed/`,
nên một lượt nạp lại toàn bộ sẽ âm thầm làm mất nó và mọi ca đó thành skip.

#### 14b. Đo bốn cách chữa — chân từ vựng BỎ DẤU thắng, nhúng bỏ dấu bị bác bỏ

Chủ dự án xác nhận **người dùng thật có gõ không dấu**, nên đây là lỗi nghiêm
trọng nhất đang mở. Đo bốn hướng, trên bộ vàng 64 ca, ba dạng truy vấn (có
dấu / nửa dấu — bỏ dấu mỗi từ thứ hai / không dấu hoàn toàn):

| cách | có dấu | nửa dấu | không dấu |
|---|---|---|---|
| **dense (hiện tại)** | 1,0000 | 0,8594 | **0,0156** |
| chỉ BM25 bỏ dấu | 0,7188 | 0,7188 | 0,7188 |
| **RRF dense + BM25 bỏ dấu** | **0,9844** | **0,9219** | **0,6406** |
| định tuyến theo dấu | 1,0000 | 0,8594 | 0,7188 |
| nhúng chính text BỎ DẤU | 0,4531 | 0,4531 | 0,4531 |

**Bỏ dấu làm truy xuất bất biến với dấu** — BM25 bỏ dấu cho đúng 0,7188 ở cả
ba dạng. Đó là tính chất cần.

**Nhúng text bỏ dấu BỊ BÁC BỎ**: 0,4531, tệ hơn cả BM25. Dấu tiếng Việt mang
nghĩa thật và BGE-M3 dựa vào nó; bỏ dấu ở phía index phá mất tín hiệu ngữ
nghĩa. Tốn 254 giây nhúng lại để biết điều này — rẻ hơn nhiều so với xây rồi
mới phát hiện.

**Định tuyến theo dấu thắng hai đầu nhưng thua ở giữa** (0,8594 vs 0,9219),
mà nửa dấu mới là dạng gõ thực tế nhất. Nó cũng cần một heuristic có thể sai.

**Chốt: RRF dense + BM25 bỏ dấu, trọng số bằng nhau.** Quét trọng số cho thấy
1,0 là điểm duy nhất hoạt động — dưới 0,7 chân từ vựng không bao giờ chen nổi
vào top-20, từ 1,5 trở lên nó nuốt cả chân dense (cả ba dạng tụt về 0,7188).

Cái giá: **1 ca** trên truy vấn có dấu (64/64 → 63/64). Cái được: **+40 ca**
trên không dấu và **+4 ca** trên nửa dấu.

**Lưu ý về "chân sparse đã chết"**: ghi chú cũ đo được rằng hồi sinh chân sparse
là CÓ HẠI (recall 1,0 → 0,9766). Điều đó vẫn đúng — nhưng nó đo chân FTS **có
dấu** trên truy vấn **có dấu**. Chân đề xuất ở đây khác hẳn: nó bỏ dấu cả hai
phía, và giá trị của nó nằm ở dạng truy vấn mà bộ vàng cũ **chưa từng đo**.

### 15. Thi hành chân BỎ DẤU — và hai lỗi tự gây, cả hai chỉ số đo mới thấy

Migration 008 (`chunk_text_fold` + `ts_vector_fold` GENERATED + GIN),
`chunking.fold_vi()`, `retrieve._lexical_fold()` làm chân RRF ngang quyền, có
công tắc lùi `RAG_FOLD_ENABLED=0`.

**Lỗi tự gây thứ nhất: tôi tái tạo đúng lỗi đã giết chân sparse cũ.** Bản đầu
dùng `plainto_tsquery`, mà hàm đó nối các từ bằng **AND** — câu dài đòi chunk
chứa MỌI từ. Đo trên corpus 4.870 chunk: **0 chunk khớp**; đổi sang OR: 3.409.
Đây đúng nguyên nhân `test_sparse_van_chet.py` ghi lại (0/64 truy vấn có kết
quả sparse), và tôi vẫn giẫm lại. Bản mô phỏng trước đó dùng BM25 (OR có chấm
điểm) nên không lộ. **Chỉ phép đo đầu-cuối mới bắt được**: recall không dấu
nhích 0,0156 → 0,0312 thay vì lên 0,6406 như mô phỏng hứa.

**Lỗi tự gây thứ hai: `segment_vi` trong chân bỏ dấu.** pyvi tạo token GHÉP
(`chinh_sach`) đòi khớp y hệt hai phía, mà phía truy vấn người dùng gõ tự do.
Mô phỏng đạt 0,7188 với tách từ THUẦN; bỏ `segment_vi` khỏi chân này rồi mới
khớp lại được số đã đo.

**Kết quả cuối, bộ eval CHÍNH THỨC, cùng thước cho cả hai chân:**

| dạng gõ | | TẮT | BẬT |
|---|---|---|---|
| có dấu | recall@20 | 1,0000 | 0,9766 |
| | **recall@6** | 0,9688 | **0,9688** |
| | mrr | 0,8619 | 0,8091 |
| nửa dấu | recall@20 | 0,8411 | 0,8359 |
| | **recall@6** | 0,7682 | **0,8203** |
| | mrr | 0,6360 | 0,6473 |
| không dấu | recall@20 | 0,0156 | **0,6042** |
| | **recall@6** | 0,0000 | **0,5208** |
| | mrr | 0,0017 | 0,3569 |

**`recall@6` trên truy vấn có dấu KHÔNG ĐỔI** (0,9688). Đó là con số đáng giá
nhất ở đây: `recall@20` là kích thước pool cho reranker, còn `recall@6` mới là
thứ LLM thật sự nhìn thấy. Giá phải trả nằm ở **thứ hạng trong pool** (mrr
−0,053), không ở nội dung đến tay LLM. Độ trễ p50 473 → 549 ms (+16%).

**Bộ vàng nay đo cả ba dạng gõ**: `--dang-go co_dau|nua_dau|khong_dau`. Cùng
câu hỏi, cùng nhãn mong đợi, chỉ đổi cách gõ. Không có nó thì lỗi này lại vô
hình đúng như suốt 64 ca trước đây.

**Một nhãn nói dối, tự bắt được khi test cũ đỏ.** `method` bản đầu của tôi báo
`dense+fold-rrf` khi chân bỏ dấu **được bật**, kể cả lúc nó trả về rỗng — đúng
kiểu nói dối mà `test_sparse_van_chet.py` sinh ra để chặn (`hybrid` trong khi
sparse luôn rỗng). Sửa: nhãn phản ánh **đóng góp thật**, và `method_label()`
tách thành hàm riêng để test kiểm từng tổ hợp không cần DB. Sau khi sửa, ba
test rerank cũ pass lại **mà không phải đụng vào chúng** — dấu hiệu nhãn nay
đúng.

Test cũ đó cũng phải sửa cơ chế: nó grep MÃ NGUỒN tìm chuỗi `"hybrid-rrf"` và
bắt nhầm một **chú thích** trích lại nhãn cũ. Grep không phân biệt chú thích
với nhãn phát ra.

Suite **2481 passed, 1 skipped, 0 failed**; 30/30 test integration của `rag`.

**Còn nợ**: `chunk_text_fold` được ghi lúc ingest, nên corpus có sẵn phải nạp
lại (hoặc backfill) sau migration — đã ghi vào `getting-started.md`.

## Endpoint trích tài liệu cho Open WebUI

**Ngày**: 2026-09-09. **Nhánh**: `worktree-trich-tai-lieu`, base `e4d242a`.
**Spec**: `2026-09-09-endpoint-trich-tai-lieu-design.md` · **Kế hoạch**: `plans/2026-09-09-endpoint-trich-tai-lieu.md`
**Ledger**: `.superpowers/sdd/2026-09-09-endpoint-trich-tai-lieu/progress.md`

Route `PUT /v1/documents/process` (`backend/src/main.py`) đưa `extract_documents()`
— OCR bậc 1 đã có từ trước — ra khỏi nội bộ backend, cắm thẳng vào khe
`external_document_loader` của Open WebUI. Năng lực OCR đã có sẵn trong repo
nhưng không route nào nhận tệp, nên chưa từng tới tay người dùng qua đường đính
kèm cho tới bản này.

### Số đo thật, đặt cạnh số của Open WebUI

Đo trên `DVT_2022.pdf` — báo cáo tài chính scan, 16 trang, 5,1 MB — qua cổng
nghiệm thu chạy trên tệp thật (`backend/tests/rag/test_extract_real_files.py`):

| | Open WebUI, bộ đọc mặc định (đo 2026-09-09) | Endpoint mới (đo 2026-09-09) |
|---|---|---|
| tổng số ký tự trích được | **15**, toàn dấu cách | **40.939** |
| số tài liệu trả về | — (`status=failed`) | **16** (đúng 1 tài liệu/trang) |
| người dùng nghe | *"Không tìm thấy tài liệu liên quan đến câu hỏi này."* | trả lời được từ nội dung thật |

Cả **16/16** trang mang `source_kind="ocr"`; cả **16/16** trang có giá trị
`ocr_conf`, khoảng tin cậy **43,4–92,5**, trung bình **80,1**.

40.939 không phải con số đếm suông: trang 6 là văn xuôi tiếng Việt sạch, đủ dấu
— "Báo cáo tài chính cho năm tài chính kết thúc tại ngày 31 tháng 12 năm 2021
chưa được kiểm toán bởi Công ty kiểm toán độc lập". Trang 2 (mục lục) có nhiễu
OCR thật — dấu chấm dẫn dòng và đường kẻ lẫn vào tiêu đề. Chỉ đếm ký tự sẽ
không biết được điều này; đã đọc trực tiếp cả hai trang trước khi ghi số này
vào đây.

Hai tệp còn lại của cổng nghiệm thu cũng qua: `src/rag/seed/law/luat-thuegtgt.pdf`
(PDF số) và `src/rag/seed/policy.docx` — `.docx` ra đúng MỘT tài liệu, vì
`parse_docx` không có khái niệm trang.

Thời gian chạy cổng: khoảng **1 phút** trên máy nguội, **2 giây** khi đã ấm, vì
kết quả OCR được đệm theo băm nội dung tệp. Ghi cả hai số để người chạy lại sau
không tưởng nhầm lượt nhanh là cổng đã hỏng (bỏ qua OCR thật).

### Nghiệm thu sống — chạy thật, không phải đọc mã (2026-09-09, sau khi bộ test đã xanh)

Tất cả số phía trên đến từ cổng nghiệm thu chạy qua pytest. Sau khi cổng đó
xanh, controller còn tự tay đo thêm một lượt qua socket thật, để tách "mã
chạy đúng trong test" khỏi "mã chạy đúng khi có ai đó thật sự gọi tới nó".

**Backend chạy ở đâu.** Từ worktree này, trên cổng **8012**, không phải 8002.
Cổng 8002 khi đó đang phục vụ backend của cây chính (tiến trình PID 12564) —
và đây không phải giả định: `PUT /v1/documents/process` gọi vào cổng 8002 trả
về **404** trong khi `/health` vẫn trả 200, tức đúng là code cũ, thiếu route
mới. Tiến trình đó được để nguyên, không đụng vào — dừng một tiến trình ngoài
worktree không nằm trong lựa chọn. Backend nghiệm thu chạy với
`RAG_RERANK_ENABLED=0`, để không có hai reranker cùng tranh 8 GB GPU với cái
đã nạp sẵn.

**Gọi trực tiếp qua socket thật.** `curl -X PUT
http://127.0.0.1:8012/v1/documents/process` với đúng tệp `DVT_2022.pdf` nặng
**5.124.652 byte**:

- HTTP **200** sau **0,50 giây** (bộ đệm OCR đã ấm), thân JSON **50.895 byte**
- **16** tài liệu, **40.939 ký tự**, **16/16** trang mang `source_kind="ocr"`,
  `metadata.source = "DVT_2022.pdf"`
- trang 6 đọc lại là tiếng Việt sạch, đủ dấu — khớp với quan sát đã ghi ở mục
  trên qua đường gate

Thêm hai phép thử phá không có trong kế hoạch, chạy vì một kết quả đúng một
mình không cho thấy các cổng chặn vẫn còn chặn:

- đổi đuôi tệp thành `.doc` → HTTP **415**, không phải 200
- bỏ header `Authorization` → HTTP **401**

**Client thật của Open WebUI, chạy nguyên văn — phần quan trọng nhất.** Thay
vì đọc mã nguồn `ExternalDocumentLoader` của Open WebUI rồi suy luận nó sẽ làm
gì, class đó được chạy THẬT bên trong container của chính Open WebUI, gọi
thẳng vào endpoint. Chỉ một chỗ bị giả (stub): `open_webui.utils.headers` —
và chỉ sau khi chứng minh cả hai hàm trong đó là no-op với lượt gọi này
(`headers.py:43-44` trả nguyên header khi `user is None`; `headers.py:95-96`
trả `{}` khi `custom_headers` rỗng). Client của họ, mã của họ, gọi qua
`host.docker.internal:8012`, trả về:

- **16** đối tượng `Document` của langchain, **40.939 ký tự**, **16/16** gắn
  nhãn OCR, `source="DVT_2022.pdf"`

Tức là nửa hợp đồng thuộc về Open WebUI được xác nhận **bằng cách chạy**, chứ
không phải bằng cách đọc mã của họ rồi tin.

### Nửa còn lại: KHÔNG chạy, nói thẳng để không ai hiểu nhầm là xong xuôi

Hai việc bị cố ý bỏ qua trong lượt đo trên, và phải ghi rõ ở đây kẻo sáu tháng
sau ai đó đọc lại tưởng nhầm đây là nghiệm thu đầu-cuối trọn vẹn:

1. **Open WebUI KHÔNG được cấu hình lại.** Bật
   `rag.content_extraction_engine` sang External, cộng URL bộ nạp và API key,
   nghĩa là ghi vào `webui.db` của một instance đang chạy sống — cả ba khoá
   đó hiện chưa tồn tại trong đó, đã xác nhận bằng một truy vấn chỉ-đọc. Ghi
   vào database cấu hình của một app đang chạy có rủi ro app đó ghi đè lại
   bằng bản trong bộ nhớ của nó; hơn nữa backend nghiệm thu ở cổng 8012 mà
   được trỏ tới rồi tắt đi sẽ để lại một cấu hình trỏ vào cổng chết. Vì vậy
   việc này để lại cho người vận hành.
2. ~~Do đó đường nạp tài liệu THẬT của Open WebUI vẫn chưa được xác nhận.~~
   **ĐÃ ĐÓNG 2026-09-10 — xem ngay dưới.**

### Nghiệm thu qua Open WebUI THẬT — đóng mục 2 ở trên (2026-09-10)

Chủ dự án tự cắm dây qua giao diện, rồi đính kèm lại `DVT_2022.pdf`. Trợ lý trả
lời được **từ nội dung tài liệu** — nêu đúng đơn vị sự nghiệp, TSCĐ, Bản thuyết
minh, và tên người ký (Kế toán trưởng, Thủ trưởng đơn vị) — kèm dẫn nguồn
`DVT_2022.pdf`. Trước bản vá, câu trả lời là *"Không tìm thấy tài liệu liên quan
đến câu hỏi này."*

Số đo trong DB của chính Open WebUI, và cái đáng giá là **before/after nằm cùng
một bảng `file`**:

| lần tải lên | `status` | độ dài `content` |
|---|---|---|
| sau khi cắm dây | **`completed`** | **40.953 ký tự** |
| ba lần trước đó | `failed` | 15 ký tự |

40.953 lệch 14 ký tự so với 40.939 mà endpoint trả về: Open WebUI nối 16 trang
lại bằng ký tự phân cách của nó. Không phải lệch nội dung.

Hai điều được xác nhận kèm theo, cả hai trước đó chỉ là suy luận từ đọc mã:

- **Nhãn giao diện trong `getting-started.md` khớp bản thật** (Open WebUI
  0.11.0): "Content Extraction Engine" → **External**, rồi "External Document
  Loader" và "External Document Loader API Key". Dropdown có 8 lựa chọn; giá trị
  nội bộ cần là `external`.
- **URL không kèm `/process`** — Open WebUI tự nối. Cấu hình chạy được là
  `http://host.docker.internal:8002/v1/documents`.

Một cái bẫy đã trả giá ba lần: Open WebUI trích text lúc **tải lên**, không phải
lúc gửi câu hỏi. Ba bản đính kèm cũ đã bị đóng dấu `failed` vĩnh viễn trong DB
của nó, nên sau khi đổi cấu hình phải đính kèm **tệp mới**, dùng lại bản cũ sẽ
vẫn thấy hỏng.

### Cổng nghiệm thu KHÔNG chạy trong bộ test mặc định

Ba test trên đều đánh dấu `@pytest.mark.integration`, nên lệnh mặc định của dự
án — `-m "not integration and not live"` — loại cả ba. Phải gọi tường minh
`-m "integration and not live"` mới chạy thật. Đây là đánh đổi hợp lý (một
phút OCR, cần cài Tesseract, cần tệp không nằm trong git) — nhưng phải nói
thẳng: một cổng không ai chạy là cách dự án này để mất một đảm bảo nhiều lần
nhất.

### Chưa làm trong lát này

- Không lưu **tệp gốc** ở đâu lâu dài — ghi ra tệp tạm trong một lượt
  `to_thread` rồi xoá ngay, kể cả khi parser ném lỗi. Điều này KHÔNG đúng cho
  văn bản đã OCR ra từ tệp đó — xem đoạn "Bộ đệm OCR" ngay dưới đây, kẻo đọc
  hai gạch đầu dòng này cạnh nhau lại tưởng nhầm endpoint hoàn toàn vô trạng
  thái.
- Không ghi gì vào database.
- `.doc` và `.xls` trả **415** — cần LibreOffice chuyển đổi, ngoài phạm vi
  lát này.
- Không báo trước thời gian dự kiến cho tệp lớn — cố ý để dành cho lát 2, khi
  đã có số đo thật về kích thước/thời gian trên nhiều tệp hơn để thiết kế
  đúng, thay vì đoán trước khi có dữ liệu.
- `asyncio.to_thread` dùng **executor mặc định** của event loop — cùng
  executor mà đường chat dùng cho `retrieve()` — nên một lượt OCR dài (hàng
  phút) chiếm một worker, và đủ nhiều lượt tải lên đồng thời sẽ xếp hàng cả
  những lượt truy xuất RAG phía sau; tách executor riêng cho OCR là việc của
  lát sau.

### Đóng nợ: bộ lọc tên tệp chặn ĐỦ ký tự tách dòng (2026-09-10)

Bản vá đầu chặn tên tệp bằng `ord(c) >= 0x20`, tức chỉ khối điều khiển C0. Đo
lại thì thiếu: `%C2%85` (NEL U+0085), `%E2%80%A8` (U+2028) và `%E2%80%A9`
(U+2029) đều nằm ngoài C0 mà `splitlines()` của Python **vẫn tách dòng** ở
chúng — nên một caller đã xác thực vẫn giả mạo được dòng log, dù ca `%0A` mà
review nêu đã bị bịt.

Tập ký tự không lấy bằng suy luận: quét toàn miền Unicode tìm mọi `c` mà
`('a'+c+'b').splitlines()` dài hơn 1 — được **đúng 10 ký tự**, và category của
chúng chỉ gồm `Cc`, `Zl`, `Zp`. Ba nhóm đó vừa **đủ** vừa **cần**, nên bộ lọc
chuyển sang loại theo category (`_BAD_FILENAME_CATEGORIES` trong `main.py`)
thay vì so `ord`. Loại kèm `Cf`/`Cs`/`Co`/`Cn` — ký tự vô hình như BOM hay đảo
chiều RTL không việc gì nằm trong tên tệp rồi đi vào log. **Không** loại `Zs`:
khoảng trắng nằm trong tên tệp thật.

Số đo sau khi vá: 0/10 ký tự tách dòng lọt qua (trước là 3/10), và các tên
thật như `Bảng cân đối kế toán 2022.xlsx` hay `Hợp đồng số 12/2022 (bản ký).docx`
giữ nguyên từng ký tự — chốt chống lọc quá tay có test riêng, vì một bộ lọc
hăng quá sẽ làm hỏng đúng thứ nó phải bảo vệ.

### Bộ đệm OCR: "không lưu tệp" không có nghĩa là vô trạng thái

Hai gạch đầu dòng ở trên — không lưu tệp lâu dài, không ghi gì vào database —
đều ĐÚNG từng câu một, nhưng đặt cạnh nhau dễ để lại cảm giác sai rằng
endpoint này hoàn toàn vô trạng thái. Không phải vậy: `src/ocr/document.py`
ghi một tệp JSON cho MỖI TRANG đã OCR vào `%TEMP%\youdoo_ocr` (đổi được qua
biến môi trường `YOUDOO_OCR_CACHE`), khoá theo băm nội dung tệp, chứa trọn
văn bản nhận dạng được cộng toạ độ từng từ và độ tin cậy trung bình. Không có
TTL, không có cơ chế dọn ở bất kỳ đâu trong `src/ocr/` — đo trên máy này lúc
viết đoạn này: **474 tệp, 22,6 MB**.

Trước nhánh này, bộ đệm chỉ được nạp bởi kho tài liệu của chính người vận
hành. Từ nhánh này, bất kỳ người dùng đã xác thực nào đính kèm một phiếu
lương, hợp đồng hay sao kê ngân hàng dạng scan sẽ để lại TRỌN văn bản của nó
dưới dạng chữ thường (plaintext) trên đĩa máy chủ, vô thời hạn, ngoài
database và ngoài mọi lớp kiểm quyền vai. Nói rõ để không ai hiểu lầm: đây
KHÔNG phải lỗ hổng ở phía ĐỌC — khoá đệm là băm nội dung tệp, nên không lấy
lại được một mục nếu chưa sẵn có chính tệp đó trong tay. Đây là vấn đề LƯU
GIỮ, BẢO MẬT của nơi lưu trữ, và TĂNG TRƯỞNG KHÔNG GIỚI HẠN. Dọn bộ đệm
(TTL/eviction) là việc của lát sau; `YOUDOO_OCR_CACHE` đã có sẵn ngay từ bây
giờ để trỏ nó sang một vị trí có quản lý thay vì thư mục tạm mặc định của hệ
điều hành.

### Giới hạn cần biết: Open WebUI không đặt timeout

Client `external_document_loader` của Open WebUI gọi bằng `requests.put`
không đặt timeout, nên một lượt OCR chậm vài phút không bị họ ngắt ngang —
tiện cho lát này, vì không cần dựng bảng job hay trạng thái riêng. Nhưng đó là
hành vi đọc được từ mã nguồn Open WebUI HÔM NAY, không phải một cam kết trong
hợp đồng giữa hai bên — không có gì đảm bảo một bản Open WebUI sau này vẫn giữ
nguyên như vậy.

### Khó khăn gặp phải khi thi hành

- **Kiểm rỗng ban đầu hẹp hơn bất biến nó phải giữ (Task 1).** Bản đầu
  `.strip()` chuỗi các ô ĐÃ NỐI lại, nên một ô `.xlsx` chỉ chứa ký tự tab
  sống sót thành `"\t"` sau `.strip(" |")` — khác rỗng, "trích thành công"
  nội dung rác. Đúng lớp lỗi module này sinh ra để chặn, chỉ đi vào bằng cửa
  `.xlsx` thay vì cửa PDF scan. Sửa: lọc rỗng theo TỪNG Ô trước khi nối.
- **Thiếu `.env` trong worktree (Task 2).** `tests/mcp/` và `tests/jobs/` lỗi
  ngay từ bước import vì thiếu biến môi trường Odoo, dù hai thư mục đó không
  liên quan gì tới tài liệu. Copy `.env` từ cây chính vào worktree là đủ; tệp
  đã nằm trong `.gitignore`, không lọt vào git.
- **Ba biến định danh tiếng Việt lọt vào mã** (`_moi_truong` ở Task 2,
  `tong`/`het` ở Task 3) — cùng một lớp lỗi lặp lại lần thứ ba trong một kế
  hoạch, cả ba đều bị copy nguyên văn từ code block trong brief. Đã đổi tên
  cả ba.
- **Mức log lẫn lộn giữa lỗi-thường-gặp và lỗi-hạ-tầng (Task 2).** Bản đầu
  ghi `logger.exception` (ERROR + stack trace) cho cả `EmptyExtraction`/
  `UnsupportedFormat` (422/415 — kết quả THƯỜNG gặp khi quét hỏng) lẫn
  `TesseractMissing` (503 — lỗi hạ tầng thật). Theo dõi log ở mức ERROR sẽ
  không phân biệt được "tài liệu này quét hỏng" với "máy chủ thiếu
  Tesseract". Sửa: `warning` cho hai nhánh trước, giữ `exception` cho nhánh
  sau.
- **Hai khẳng định `any(...)` quá lỏng ở cổng nghiệm thu (Task 3).** Bản đầu
  chỉ đòi MỘT trong 16 trang mang `source_kind="ocr"` / có `ocr_conf` — một
  hồi quy khiến phần lớn trang trượt khỏi đường OCR vẫn lọt qua cổng nếu tổng
  ký tự còn trên ngưỡng. Siết thành `all(...)`.

## Đổi PSM cho OCR — ĐÃ THỬ VÀ BỊ BÁC BỎ (2026-09-10/11)

**Ngày**: 2026-09-10 → 2026-09-11. **Nhánh**: `worktree-ocr-psm`, base `35fc75d`.
**Kết luận**: cả hai phương án đổi PSM đều **bị số đo bác bỏ**. Không thay đổi
production nào. Giữ `OCR_PSM = 6`.

### Vì sao thử: một câu hỏi số liệu không trả lời được

Người dùng đính kèm `DVT_2022.pdf` qua Open WebUI (endpoint trích tài liệu chạy
đúng, 40.953 ký tự) rồi hỏi *"tổng tài sản đầu năm là bao nhiêu"*. Trả lời:
"không có thông tin", kèm dẫn nguồn một tài liệu KHÁC trong corpus.

Con số **có** trong tệp; nhãn để tìm nó thì **không**. Cột nhãn trang 7 (trang
TÀI SẢN của bảng cân đối) đọc ra: `'Pap s'`, `'2 mmeeomeih'`, `'[xamasu'`,
`'F káananyee'`, `'H999'`. `TỔNG CỘNG TÀI SẢN` không xuất hiện ở đâu.

### Hai giả thuyết bị bác bỏ trước khi thử PSM

- **DPI không phải nguyên nhân**: 200 → 300 → 400 cho conf 63,3 → 60,0 → 60,2
  trên trang 7, và không nhãn nào nhận ra được ở bất kỳ DPI nào. Đừng thử lại.
- **PSM 11 (chữ thưa) phải loại** dù conf cao nhất (90,0): `build_grid` gom hàng
  theo `line_id` của Tesseract, chế độ chữ thưa không sinh cấu trúc dòng, nên
  grid ra **135 hàng × 1 cột** và `table_row_runs` ra **0 run**. Bảng biến mất.

### `mean_conf` KHÔNG phải thước đo chất lượng đọc

Đây là bài học đắt nhất của lượt này. Bảng "PSM 6 tệ nhất ở 16/16 trang" (conf
trung bình 80,1 so với 89,5 của PSM 4) **đã dẫn tới một khuyến nghị sai**.

Bằng chứng trực tiếp, `luat-thuexuatnhapkhau.pdf` tr.13: conf **tăng** 93,7 →
95,3 trong khi recall theo TỪ **giảm** 0,9473 → 0,9308. Conf là mức tự tin của
Tesseract về những gì nó đã đọc, không phải về những gì nó bỏ sót.

### Phương án 1 — PSM 4 toàn cục: BỊ BÁC BỎ, 3 cổng đỏ

| thước | PSM 6 | PSM 4 toàn cục |
|---|---|---|
| tự-nuôi bậc 1 (min) | 0,9473 | **0,8725** ✗ dưới 0,89 |
| lát 3 tên cột | 234/383 = 0,6110 | **101/251 = 0,4024** ✗ dưới 0,56 |
| Cổng A mẫu SSC | 0,7143 | **0,6364** ✗ dưới 0,66 |
| lát 2 sụp về 1 cột | 0 trang | 1 trang |
| lát 2 mật độ ô | 0,3911 | 0,4488 (tốt hơn) |

Hồi quy tự-nuôi tr.20 **tất định**: 0,8725 hai lượt riêng, 0,9508 dưới PSM 6.
Lưu ý lát 3 đếm được **251 hàng bảng thay vì 383** — PSM 4 làm ít hàng được
nhận là hàng bảng hơn: nó đọc chữ khác đi nhưng phá cấu trúc bảng.

### Phương án 2 — PSM thích ứng theo conf: BỊ BÁC BỎ, hằng số ăn may

Quy tắc: đọc PSM 6 trước, `mean_conf < T` thì đọc lại bằng PSM 4. Quét 13 giá
trị T trong MỘT tiến trình, OCR mỗi trang đúng một lần mỗi PSM rồi ghi nhớ —
cùng lối `calibrate_table.py` dùng cho lưới gap/support.

T=0 nghĩa là không bao giờ đổi (= PSM 6 thuần) và T=101 là luôn đổi (= PSM 4
thuần), nên **phép quét bao trùm cả hai đầu**, và cả ba giá trị 0/85/101 **tái
tạo khít** ba phép đo độc lập trước đó — đó là bước tự kiểm thước.

| T | tự-nuôi min | lát 3 tên cột | lát 2 tách | sụp | mật độ | đổi PSM4 |
|---|---|---|---|---|---|---|
| 0 | 0,9473 | 234/383 = 0,6110 | 0,9771 | 0 | 0,3911 | 0/101 |
| 55 | 0,9473 | 234/383 = 0,6110 | 0,9771 | 0 | 0,3911 | 8/101 |
| 65 | 0,9473 | 234/392 = **0,5969** | 0,9776 | 0 | 0,3896 | 10/101 |
| 70 | 0,9473 | 234/392 = **0,5969** | 0,9776 | 0 | 0,3896 | 11/101 |
| 75 | 0,9473 | 234/392 = **0,5969** | 0,9776 | 0 | 0,3896 | 14/101 |
| 80 | 0,9473 | 234/392 = **0,5969** | 0,9776 | 0 | 0,3896 | 16/101 |
| **85** | 0,9473 | **247/394 = 0,6269** | 0,9797 | 0 | 0,3955 | 25/101 |
| 88 | 0,9473 | 160/309 = **0,5178** | 0,9775 | 0 | 0,4125 | 42/101 |
| 90 | 0,9473 | 117/283 = 0,4134 | 0,9769 | 1 | 0,4358 | 55/101 |
| 92 | 0,9473 | 106/270 = 0,3926 | 0,9727 | 1 | 0,4387 | 67/101 |
| 95 | **0,8725** | 101/251 = 0,4024 | 0,9749 | 1 | 0,4488 | 96/101 |
| 98 · 101 | **0,8725** | 101/251 = 0,4024 | 0,9749 | 1 | 0,4488 | 101/101 |

**T=85 là một LƯỠI DAO, không phải cao nguyên.** Nó là giá trị duy nhất trong
13 giá trị vượt được nền, và **hai bên nó đều tệ hơn việc không làm gì**: T=80
cho 0,5969 và T=88 cho 0,5178, so với nền 0,6110. Từ 85 sang 88, số trang đổi
PSM tăng 25 lên 42 và lát 3 sụp 0,6269 xuống 0,5178 — độ nhạy đó nghĩa là kết
quả chỉ phụ thuộc việc trang nào tình cờ rơi bên nào của ngưỡng trong đúng
corpus này.

Đó đúng lớp "chốt đúng rìa lưới" mà `calibrate_table.py:68-74` ghi là đã bị bắt
hai lần. Cơ chế thật phải bền quanh điểm chốt.

### Cái vẫn đúng

Dưới PSM 4, trang 7 của DVT **thật sự** đọc được. Trước:

    I |: h | Báo cáo tình hình tài chính Địa chỉ: 361 Tây Sơn, P. Quang:
    ~m.|cáckhoinphittu | Bình Định.: 19 | || | (Ban hành theo ngày: 19078257365)

Sau:

    STT Chỉ tiêu Mã số minh Số cuối năm Số đầu năm
    TÀI SẢN
    IIL | Các khoản phải thu        | 10 | 19.078.257.265 | 8.331.692.341
    1.  | Phải thu khách hàng       | 11 | 8.812.478.000  | 4.773.193.000
    Lu  | Đầu tư tài chính ngắn hạn | 05 | -              | -

Nhãn thật, mã số thật, hai cột năm, có dấu phân cách nghìn. **Khả năng đọc tồn
tại** — chỉ là không lấy được nó qua công tắc PSM mà không phá chỗ khác. Và ngay
cả khi lấy được: `TỔNG CỘNG TÀI SẢN` vẫn 0 trang, vì nhãn hàng tổng vẫn mất.

### Hướng KHÔNG nên thử tiếp

Biến thể thứ ba của cùng một ý — chọn PSM theo tín hiệu cấu trúc thay vì conf —
**không nên làm ngay**. Hai lần thất bại cùng một cần điều khiển là lúc hỏi lại
cần điều khiển, không phải thử biến thể thứ ba. Hai cần còn lại:

- **Dò hàng tiêu đề**: tất định, không hạ tầng mới. `table.find_header_rows`
  chỉ có hai vị từ (>=3 ô không rỗng; không ô nào khớp `MONEY`), trong khi đường
  xlsx đã có `xlsx_header.find_header` với `_looks_like_label`
  (`_LABEL_MAX_LEN=40`), `MIN_SCORE=0.92` và hợp đồng "thà trả None chứ không
  đoán bừa" — mà None ở đây TỐT HƠN văn xuôi, vì `compact=True` sẽ phát giá trị
  trần thay vì `(Ban hành theo: 19.078.257.365`.
- **VLM bậc 3**: theo `reference_youdoo_compute_and_model_capability` (đo
  2026-09-04), Gemini flash-lite đọc ảnh tốt (30/30 số hoá đơn) nhưng hạn mức là
  hồ CHUNG với chatbot.

### Hai thứ giữ lại từ lượt này

Không phải thay đổi hành vi, có giá trị độc lập với PSM:

- `c664786` — bốn cổng OCR (lát 2, lát 3, lát 4, tự-nuôi) trước đây **không in
  số nào**, nên một cổng xanh ở 0,57 trông y hệt một cổng xanh ở 0,99. Giờ chúng
  in. Không đổi một assert nào. Chính nhờ commit này mới dựng được bảng trên.
- `2f41343` — `kiem_so_hoc.py` chạy được như CLI từ 2026-09-06 nhưng **chưa test
  nào gọi**, nên chưa bao giờ chặn được gì. Đã nối vào suite (85/85, 0,04s,
  không cần tesseract nên THỰC SỰ chạy ở CI). Đã thử phá: đổi một chữ số ở chỉ
  tiêu 100 làm cổng đỏ.

## OCR bậc 3 — lát 0: bộ kiểm số học ĐI TRƯỚC ống dẫn VLM (2026-09-11)

Spec: `2026-09-11-ocr-bac-3-vlm-kiem-so-hoc-design.md`. Lát 0 không gọi API nào.
Nó dựng cái thước để lượt gọi VLM đầu tiên (lát 2) đã có thứ bác được nó. Mọi số
dưới đây đo trên **10 trang đáp án tay** (`tests/fixtures/ocr_bang_that/*.json`:
7 trang SCID TT 99/2025, 3 trang DVT TT 107/2017 viết mới từ ảnh 200 DPI trước
khi nhìn output VLM nào), chạy trong CI vì không cần tesseract.

### Cái ship: `src/ocr/so_hoc.py`, module lá

| tầng | hàm | đo trên đáp án |
|---|---|---|
| ô tiền | `parse_money` | `"(58.099.826.029)"` → âm; `"19078257365"` (không phân cách) → BAD; chữ O → BAD |
| (e1) công thức in | `parse_printed_formula` — đếm ngoặc, dấu âm, ngoặc lồng | 0 FAIL trên 10 trang; phủ 15/15 ràng buộc nội trang của DVT (TT 107 in công thức ở MỌI hàng tổng) |
| (e2) cấu trúc | `check_structure` — width / bad_money / dup_ma_so / bad_ma_so / non_monotonic | 0 vi phạm trên 10 trang đáp án |
| (b) phân cấp | `derive_hierarchy` — 5 mức `A-` > `I.` > `1.` > `a)` > `-`/không | B01: suy lại 32/35 ràng buộc tay, **0 sai**; B02/B03: sai 5 lần → lý do giới hạn vào B01, ghi thành test "phải đỏ" |
| (c) bảng thông tư | `form_table("99/2025/TT-BTC", "B01-DN")` đọc `src/ocr/ma_so/tt99.json` | riêng (c) trên SCID: 33/40, 0 FAIL |
| gộp | `merge_constraints` — (e1) > (c) > (b) theo tổng; cùng tầng giữ cả hai | (e1)∪(c)∪(b): **48/55** ràng buộc tay nội trang |
| hàng | `classify_rows` → `PageReport` | chế độ VLM (`strict_absent=False`): **131/136 hàng có số `vision_verified`, 0 hàng đúng bị loại** |

5 hàng có số không xác minh được: 52 (DVT tr9, phân phối kết quả — không có
ràng buộc nào), 70/71 (SCID tr16, lãi trên cổ phiếu), 280/440/B03:50 (tổng xuyên
trang — thành phần ở trang trước). Tất cả ở `vision_unverified`, không mất.

### Bảng (c) suy từ mẫu chính thức, và chỗ phải gõ tay

`tools/derive_form_table.py` đọc `tmp-docs/b01-dn.docx`, `b03-dn-truc-tiep.docx`,
`b03-dn-pp-gian-tiep.docx` (sha256 ghi vào JSON), chạy CHÍNH `derive_hierarchy`
production lên mẫu sạch cho B01 (28 ràng buộc, 2 in sẵn), quy tắc thành-phần-
trước-tổng cho B03 (gián tiếp có tổng phụ chạy `08 = 01 + 02..07`,
`20 = 08 + 09..17`). **B02-DN gõ tay**: tmp-docs không có mẫu KQKD (`b02-dn.docx`
là B01 dán nhầm — sha256 trùng; `B02a-DN.docx` là B01-DNKLT), và quan hệ có dấu
`10 = 01 − 02` không nằm trong bố cục mẫu mà trong văn bản hướng dẫn. JSON ghi
`"nguon": "tay — ..."` để không ai tưởng nó suy từ mẫu. TT 107 **không có bảng**:
(e1) đã phủ 15/15 trên DVT, bảng sẽ không đo được gì — thêm khi có trang TT 107
kích hoạt mà (e1) không phủ.

Hai lỗi của chính bộ suy lộ ra **khi sinh bảng từ mẫu**, không phải khi chạy
trên đáp án: (1) mẫu B01 có mức `a)`/`b)` (231 = 232 + 233, 233 = 234 + 235) mà
bộ suy 4 mức bỏ qua → dashes gắn nhầm lên `1.`; (2) hàng "TỔNG CỘNG NGUỒN VỐN
(440 = 300 + 400)" không STT gắn làm con của `10.` (420) → `420 = 420a + 420b +
440`. Sửa: hàng mang công thức in của chính nó không là con của ai. Cả hai lỗi
**không đỏ** trên 10 trang đáp án vì các hàng liên quan đều "-" — một lần nữa
đáp án chỉ bắt được sai ở chỗ có số.

### Q4 — áp bảng SAI: 0 PASS khác 0 trên 6 cặp

TT 99 B01 lên DVT tr7/tr8 (TT 107): toàn NA (mã số khác hệ). TT 99 B02 lên DVT
tr9, B03 lên SCID tr16, B02 lên SCID tr17, B03 lên SCID tr12: **FAIL 6–8, PASS
0**. Chọn sai thông tư **không** sinh `vision_verified` giả; nó loại hàng đúng —
chi phí phạm vi, không phải chi phí đúng-sai. Vì thế cổng chọn thông tư ở lát 3
không cần "cứng": sai thì mất phủ và cảnh báo nói ra, không có gì lọt.

### Q5 — 11 ca phá, đỏ đúng chỗ, và hai điểm mù ghi thành test

Đổi một chữ số ở 11 → loại đúng cụm `10 = 11 + 12 + 13 + 14` (5 hàng), nêu công
thức và độ lệch −1 ở đúng cột, **và 50 vẫn xác minh** vì ô của 10 không đổi (tôi
viết test kỳ vọng 01 bị loại — sai, bộ kiểm chính xác hơn tôi). Đổi tổng 31 →
cụm 31 và cụm 30 (vì 31 là thành phần của 30) đi. Đảo cột một hàng → FAIL cả hai
cột. Ô rác → loại riêng hàng, ràng buộc chứa nó thành NA (không kết luận sai về
hàng khác). Hàng lặp → loại bản lặp, giữ bản gốc, **không** trần trang (lúc đầu
"14 sau 14" kích `non_monotonic` — sửa). Hai điểm mù:

- **Đảo cột MỌI hàng → số học QUA.** Không phải việc của số học; lát 2 dùng
  x-toạ-độ token Tesseract. Test tồn tại để không ai kỳ vọng nhầm.
- **(b) mù với hàng bị rơi**: suy từ hàng có mặt, nên rơi hàng 14 thì ràng buộc
  thành `10 = 11 + 12 + 13`, FAIL vì lệch nhưng `absent` rỗng. Chỉ (e1)/(c) —
  tham chiếu cố định — mới báo được vắng cái gì.

### Một quyết định lệch spec, có số đo: lệch + vắng → NA, không FAIL

Spec viết: thành phần vắng tính 0, tổng lệch → FAIL. Đo ở chế độ VLM trên SCID:
`280 = 100 + 200` (100 ở tr12), `440 = 300 + 400` (300 ở tr14), B03 `50 = 20 + 30
+ 40` (20/30 ở tr17) → **6 hàng tổng ĐÚNG bị loại**, và đó là chính hàng người
dùng hỏi ("tổng tài sản"). Không phân biệt được "VLM rơi một hàng khác 0" với
"hàng ở trang trước" bằng số học nội trang. Đổi: lệch mà có hàng vắng → **NA**,
lý do nêu cả độ lệch lẫn mã số vắng. Hậu quả với hàng rơi thật: cụm mất phủ →
`unverified` (không kết luận), tổng vẫn xác minh được qua ràng buộc cha nếu ô
nó đúng. **Không cách nào xác minh sai hơn cách nào**; khác nhau ở chi phí phạm
vi, và cách mới trả chi phí đó cho đúng hàng.

### Điều chưa chắc sau lát 0

- SCID là báo cáo **hợp nhất**, có hàng ngoài mẫu DN (279, 429). Trên trang này
  chúng "-" nên (c) B01-DN không FAIL; một báo cáo hợp nhất có 279 ≠ 0 sẽ làm
  (c) loại đúng cụm 270. `tmp-docs/bieumau_bctc_hopnhat.pdf` có thể cho bảng
  B01-DN/HN — chưa đọc.
- Xung đột (c) vs (b) trên SCID = 6, đều do SCID **bỏ hàng "-"** (mẫu ghi chú
  (1): chỉ tiêu không có số liệu được miễn trình bày). Lenient coi vắng = 0 nên
  (c) vẫn PASS. Đúng cho hàng "-"; chưa có ca hàng vắng ≠ 0 thật để đo.
- `rows_from_vision` chưa gặp output VLM thật nào — hình dạng theo hợp đồng spec,
  lát 2 sẽ là lần đầu nó chạm dữ liệu sống.

## OCR bậc 3 — lát 1–4: kích hoạt, xoay, ống dẫn VLM, xuất xứ (2026-09-11)

Tất cả đo/kiểm KHÔNG gọi API nào. Lượt VLM thật đầu tiên (Q7/Q8, fixture
`vlm_raw/`) và nghiệm thu sống qua Open WebUI **chưa chạy**: cần
`YOUDOO_VLM_API_KEY` trong `.env` — khoá riêng, chủ dự án cấp.

### Lát 1 — `tools/calibrate_vlm_trigger.py` trên 281 trang ảnh, 6 báo cáo

Kết quả đầy đủ: `tools/calibrate_vlm_trigger_result.txt`. Bốn phép đo, hai bác bỏ:

- **Q9 — tỉ lệ dấu tiếng Việt BỊ BÁC.** Trang Tesseract được số học bảo lãnh
  p50 = 0,78; trang không được bảo lãnh p50 = 0,78; đối chứng vector rasterise
  0,84. Hai phân bố chồng nhau ngay chỗ trang cờ nằm — spec đề xuất tín hiệu
  này làm lọc thô, và nó không lọc được gì. Không có ngưỡng nào để chốt.
- **Q2 — số học vouch cho Tesseract có răng, nhưng hẹp.** 52/281 trang dựng
  được cột mã số; 21 trong đó ≥ 1 PASS và 0 FAIL (giữ hàng Tesseract, không gọi
  VLM); 30 trang có cột mã số nhưng 0 ràng buộc đánh giá được (mã số đọc sai
  làm mất khoá). Đúng lo ngại của spec — vì thế quy tắc kích hoạt KHÔNG dựa
  vào "không vouch" một mình (260/281 trang không vouch, đa số là thuyết minh
  và văn xuôi).
- **Tín hiệu TIÊU ĐỀ báo cáo chính** (không có trong spec, tìm ra khi đọc text
  Tesseract của DVT tr7: dòng "Báo cáo tình hình tài chính" đọc ĐÚNG dù thân
  trang 1/8 số đúng): 1/3 đầu trang, bỏ dấu, khớp "bảng cân đối kế toán / báo
  cáo tình hình tài chính / kết quả hoạt động / lưu chuyển tiền", loại "bản
  thuyết minh". Bắt 50/281 trang, **đúng mọi trang báo cáo chính của cả 6 tài
  liệu**; 8 trang khớp ≥ 2 loại là mục lục/ý kiến kiểm toán → loại. Quy tắc
  chốt: **gọi VLM ⇔ tiêu đề đúng một loại VÀ số học không vouch**. Trên corpus:
  43 trang tiêu đề một loại − 19 vouched = **24 lượt VLM / 6 tài liệu** (DVT 4,
  NTC 3, PGI 5, RBC 6, TDC 3, SCID 3), gồm DVT tr7/8/9. Hai trang tốt không có
  tiêu đề (PGI tr9, SCID tr56) không sao — chúng đi Tesseract như cũ.
- **Q3 — Tesseract làm oracle: bác dứt điểm.** Ô tiền đáp án có mặt nguyên văn
  trong token Tesseract: tr7 **0/23**, tr8 3/12, tr9 13/17; mã số 2/19, 2/15,
  5/23. (a) không bao giờ được phủ quyết — con số này biến khẳng định thành số.
- **Q6 — xoay.** OSD báo 27 trang; đọc thêm hướng xoay và giữ hướng conf cao
  hơn: **20 xoay thật** (conf 43→86, số tiền đọc được 0→20..57 mỗi trang), 7
  báo sai (độ tin OSD 0–3, conf 92→47 nếu tin) không bị xoay. Cả 20 là trang
  thuyết minh ngang — VLM không kích hoạt trên chúng, nhưng Tesseract đọc
  được chữ thay vì rác: cải thiện bậc 1 độc lập với VLM. `ARTIFACT_VERSION` 3
  → 4, đệm cũ tự lạc khoá (không xoá).

### Lát 2–4 — cái ship

- `providers.KeyRing` + `keys_for_env` tách từ `Router._xoay_khoa`; Router uỷ
  quyền, 50 test cũ không đổi. `vision.py`: khoá riêng `YOUDOO_VLM_API_KEY*`
  (không có → tắt, log một lần), xoay chỉ khi 429, trần 200/lượt nạp (SUY
  LUẬN, ghi rõ), ghi sổ `vlm-ocr`, prompt v1 "chép, không diễn giải", JSON hỏng
  → lỗi mang độ dài không mang nội dung.
- `trigger.decide` + `parse._khoi_tu_vlm`: mỗi hàng một block atomic mang
  `source_kind` theo trạng thái; REJECTED không lưu, cảnh báo nêu mã số; một
  xuất xứ mỗi trang; hết khoá → dừng phần còn lại lượt nạp.
- `_XUAT_XU_RANK` 6 bậc; `extract.py` gộp bậc xấu nhất (trước đó trang toàn
  VLM chưa kiểm mang nhãn "text"); `Chunk.source_kind` từ `rag_chunks` tới
  `_format_context` với tag "CHƯA kiểm được bằng số học — không trích như số
  chính xác". `conftest` xoá khoá VLM trong mọi test không `live`.

### Ba ruling lệch/ngoài spec

1. **(b) chỉ khi không có bảng (c).** Trên lưới Tesseract thật, đánh dấu STT đọc
   sai ("L", "2;") làm (b) sinh `238 = 240 + 241 + 242` → FAIL giả → gọi VLM
   thừa; trên hàng VLM cũng có thể loại oan. (c) riêng đã phủ 33/40 trên TT 99.
2. **Chọn bảng bằng số học**, không đọc header: thử mọi bảng, giữ bảng (PASS
   nhiều, FAIL ít, NA ít). Q4 bảo đảm bảng sai không PASS khác 0 nên không cần
   ngưỡng. Hoà không phân được (B03 trang 2 giống nhau ở hai phương pháp) → chỉ
   đòi đúng họ mẫu.
3. **Trần VLM tính theo lượt `parse_pdf`** (một tài liệu), không theo lượt nạp
   corpus — vì `parse_pdf` không biết nó nằm trong lượt nạp nào. 100 tài liệu ×
   ~4 trang = 400 > 500 rpd một khoá → 429 → xoay → hết vòng thì dừng có tên.

### Chưa làm, nói thẳng

- **Chưa một lượt VLM thật nào.** Prompt v1, `rows_from_vision`, và giả định
  "VLM đọc đánh dấu STT tốt hơn Tesseract" đều chưa chạm dữ liệu sống. Q7 (giải
  ngược) và Q8 (0 ô sai vào `vision_verified`) chạy bằng `test_vision_live.py`
  khi có khoá; phản hồi thô lưu làm fixture cho `test_vision_replay.py`.
- Nghiệm thu sống (đính `DVT_2022.pdf`, hỏi "tổng tài sản đầu năm") chưa chạy;
  đáp án chờ sẵn: **69.862.687.223** (mã 50, Số đầu năm, tr7), phải là block
  `vision_verified`.
- Tesseract đồng ý ((a) kiểm hướng cột bằng x-toạ-độ) CHƯA nối — điểm mù "đảo
  cột toàn trang" còn nguyên, ghi thành test.
- Trang thuyết minh (221/281 trang không có cột mã số) hoàn toàn ngoài phạm vi
  bậc 3 lượt này.
