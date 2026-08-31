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
