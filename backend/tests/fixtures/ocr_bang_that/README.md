# Đáp án bảng tài chính từ scan thật — dữ liệu hiệu chỉnh cho OCR bậc 2

Tập này tồn tại để **hiệu chỉnh và gác** tầng dựng bảng từ toạ độ (OCR bậc 2,
spec `docs/superpowers/specs/2026-09-04-tang-ocr-dung-chung-design.md` §14).
Trước 2026-09-06 dự án **không có một tài liệu scan nào** — mọi số đo OCR đều
lấy trên ảnh rasterise từ PDF số, tức là ảnh sạch hơn đời thật.

## Tài liệu nguồn

Báo cáo tài chính hợp nhất bán niên đã soát xét của **Công ty CP Đầu tư Phát
triển Sài Gòn Co.op**, công bố thông tin bắt buộc theo Luật Chứng khoán.

| thuộc tính | giá trị (đo được, không phải mô tả) |
|---|---|
| Số trang | 63 |
| Lớp text | **0 ký tự trên cả 63 trang** — scan thuần |
| Máy scan có chèn OCR không | **không** (0 `chars`, 0 `lines`, 0 `rects`, đúng 1 ảnh/trang) |
| Độ phân giải thật | **150 DPI** (ảnh nhúng 1240×1752 px trên trang A4) |
| Trang có bảng | 12–18 |

Tệp PDF **không** nằm trong repo (22 MB, và `tmp-docs/` đã gitignore). Đường dẫn
gốc ghi trong trường `tep_nguon` của từng tệp đáp án.

## Vì sao đáp án lại do một mô hình đọc

Bản scan **không có lớp text**, nên không có gì để so — khác hẳn cổng tự nuôi
của bậc 1, nơi corpus tự sinh đáp án. Đáp án ở đây phải do người hoặc máy đọc
ảnh tạo ra.

Cách làm: Claude đọc ảnh 200 DPI và ghi đáp án, **trước khi xem Tesseract đọc ra
gì** (nhìn trước là neo, và "dò bất đồng" sẽ thành diễn kịch). Sau đó **hai cơ
chế độc lập** kiểm lại bản đọc đó:

1. **`kiem_so_hoc.py`** — số học nội tại của chính báo cáo. Tất định, không LLM,
   không nguồn ngoài, chạy trong CI được.
2. **`doi_chieu_tesseract.py`** — so với Tesseract, sinh hàng đợi bất đồng để
   người duyệt.

Mọi tệp mang `"trang_thai"` nói đúng nguồn gốc của nó. Đây là dữ liệu **máy
đọc**, và nhãn phải nói đúng điều đó.

**Đã duyệt 2026-09-06** (`"trang_thai": "DA_DUYET"`). Chủ dự án soát ba thứ mà
hai cơ chế tự động không với tới — đếm hàng từng trang, toàn bộ cột `Thuyết
minh` (55 mục), và 10 nhãn gộp nhiều dòng — và xác nhận đúng hết. Số hàng có
`Mã số` khớp chính xác trên cả ba trang được đếm độc lập (15 → 17, 17 → 26,
18 → 11).

## Cổng số học: vì sao nó kiểm được CẤU TRÚC

Một báo cáo tài chính tự mang đáp án: dòng tổng phải bằng tổng có dấu các dòng
thành phần. Muốn cộng được thì phải biết **ô nào thuộc cột nào** và **hàng nào
thuộc mục nào** — nên một bảng dựng lại **sai cột** sẽ làm gãy chuỗi ràng buộc.
Đó là lý do nó là cổng cho bậc 2, không chỉ cho việc đọc chữ.

Ba tầng ràng buộc, mạnh dần:

- **trong trang**: `110 = 111 + 112`
- **bắc qua trang** (`nhom` chung): `280 = 100 + 200`, và **đẳng thức kế toán cơ
  bản** `440 = 280` — tổng nguồn vốn bằng tổng tài sản, bắc qua 4 trang
- **bắc qua báo cáo** (`rang_buoc_lien_bao_cao`): tiền cuối kỳ trên lưu chuyển
  tiền tệ bằng chỉ tiêu 110 trên bảng cân đối

## Quy ước ô — đọc kỹ, nó không phải chi tiết vặt

| giá trị | nghĩa |
|---|---|
| số | giá trị thật; âm = in trong ngoặc đơn trên giấy |
| `"-"` | **có** ô, **không** có số (bằng không về nghiệp vụ) |
| `null` | **không áp dụng**: hàng tiêu đề/nhóm, ô này không tồn tại |

Phân biệt `"-"` với `null` không phải để cho đẹp. Bản đầu dùng `x or 0`, nên một
ô **đọc sót** (`null`) được lặng lẽ cộng như 0 và tổng vẫn xanh trong khi dữ
liệu sai — đúng lớp lỗi "cổng không đo gì" mà dự án này đã mất thời gian vì nó
nhiều lần. Giờ cổng **từ chối cộng** ô `null` và báo lỗi có tên.

## Chạy

```bash
cd backend/tests/fixtures/ocr_bang_that
python kiem_so_hoc.py SCID_2026H1_tr1{2,3,4,5,6,7,8}.json
```

Phải truyền **cùng lúc** mọi tệp mà ràng buộc bắc qua, nếu không tham chiếu chéo
sẽ báo không tìm thấy. Thoát khác 0 khi có ràng buộc không thoả.

```bash
python doi_chieu_tesseract.py SCID_2026H1_tr17.json <duong_dan_pdf>
```

## Kết quả đo 2026-09-06

| | |
|---|---|
| Ràng buộc số học | **85/85 thoả** (7 trang, gồm 3 ràng buộc liên báo cáo) |
| Ô đối chiếu được với Tesseract | 208 |
| — khớp nguyên văn | **204** |
| — đúng chữ số, sai dấu phân cách | 4 |
| — **cần người duyệt** | **0** |
| Ô bỏ qua vì quá nhỏ để đối chiếu tin cậy | 4 (mã 70/71, lãi trên cổ phiếu) |

Cổng đã được **thử phá** và đỏ đúng chỗ ở bốn kiểu hỏng: sai một chữ số; ô
`null` lọt vào ràng buộc; sai một chữ số ở bảng có hệ số âm; và sai một chữ số
làm gãy ràng buộc liên báo cáo. Mã thoát 1 ở cả bốn.

## Điều tập này KHÔNG chứng minh

- **Không** chứng minh Tesseract đọc đúng. Nó chứng minh Claude và Tesseract
  **đồng ý** ở 204/208 ô, và bản đọc của Claude **thoả số học của chính tài
  liệu**. Hai bằng chứng độc lập, nhưng vẫn không phải bản gốc do kế toán lập.
- **Không** phủ trang thuyết minh (19–63), nơi bảng có hình dạng khác.
- **Không** phủ tài liệu nghiêng, nhiễu, hay photo nhiều đời. Bản này scan
  phẳng, sạch, 150 DPI.
- Cột `Mã số` — khoá ghép của mọi ràng buộc — **Tesseract đọc sai 3/14 trên
  trang 17** (`01`→`0`, `02`→`022`, `11`→`1`). Số tiền dài thì gần như hoàn hảo,
  số ngắn thì hỏng. Đây là phát hiện quan trọng nhất cho thiết kế bậc 2: token
  dài có khuôn nhóm-3 tự ràng buộc nó, token ngắn thì không có gì để tự sửa.
