# B3 — Word suy phân cấp từ chữ — thiết kế

**Ngày**: 2026-09-04. **Nhánh**: `worktree-tang-nap-tai-lieu-1`. **Trạng thái**: thiết kế đã
duyệt, chưa viết code.

Mở rộng `2026-08-29-tang-nap-tai-lieu.md` mục 5.3 (lỗi 3 trong bảng bốn lỗi).

## 1. Đề bài, đo được

`parse_docx` chỉ nhận tiêu đề qua **style Heading của Word**. Tài liệu không dùng style thì không
có tiêu đề nào, và hậu quả không dừng ở việc mất breadcrumb.

**Đo 2026-09-04 trên 12 tệp `.docx`/`.doc` thật trong `tmp-docs/`:**

| tệp | dòng có chữ | dùng Heading style | mẫu chữ bắt được |
|---|---|---|---|
| `B01a-DN`, `B02a-DN`, `b01-dn`, `b02-dn` | 9 mỗi tệp | **0** | 1 (chỉ tiêu đề tài liệu) |
| `B03a-DN-*`, `b03-dn-*` | 5-7 | **0** | 1 (chỉ tiêu đề tài liệu) |
| **`B09a-DN`** | 28 | **0** | **0** |
| `b09-dn` | 322 | **0** | 5 |
| `quyche_ogop` | 2 | 1 | 1 |

**0/10 biểu mẫu BCTC dùng style Heading.** `B09a-DN.docx` là ca xấu nhất: 28 dòng, không dòng nào
được nhận là tiêu đề bằng bất kỳ cách nào.

Và bộ dò chữ **đã có sẵn** (`heading_level()`, đang phục vụ `parse_pdf`) chỉ vớt được tiêu đề tài
liệu (nhánh dòng IN HOA) — vì nó được hiệu chỉnh cho **văn bản luật**, nơi số đánh một cấp (`1.`)
là *khoản* chứ không phải tiêu đề.

## 2. Cơ chế lỗi, đã truy tới dòng

Trước bản sửa, `b09-dn.docx` có **377/377 block `heading_level=None`** và **74/74 chunk mang
`section_path` bằng ĐƯỜNG DẪN TỆP**:

```
chunking.py:52   doc_title = next((b["text"] for b in blocks if b["heading_level"]), source_file)
chunking.py:61   crumb     = " › ".join(t for _, t in path_stack) or doc_title
```

Không block nào có heading → `doc_title` lùi về `source_file` → `path_stack` rỗng nên `crumb` lùi
về `doc_title` → `index_text()` nối nó vào text đem đi embed. **Đường dẫn Windows được nhúng vào
vector của MỌI chunk trong tài liệu, giống hệt nhau** — vừa vô nghĩa vừa **làm giảm khả năng phân
biệt giữa chính các chunk đó**, và vô hiệu hoá luôn P3b (phân cấp).

Đây là lỗi **CHUNG cho mọi định dạng**, không riêng docx: bất kỳ tài liệu văn xuôi thuần nào của
bất kỳ format nào rơi vào ca "không có heading" đều dính. Docx chỉ là nơi nó phổ biến nhất.

## 3. Bốn phương án đã cân nhắc

| | cách | phán quyết |
|---|---|---|
| A | Dùng `heading_level()` nguyên xi làm dự phòng cho docx | **Không đủ** — đo ra `B09a-DN` vẫn 0/28, biểu mẫu BCTC chỉ vớt được dòng tiêu đề. Rẻ nhưng không giải quyết đề bài. |
| B | Sửa chính `heading_level()` để nhận thêm mẫu hành chính | **Loại** — nó đang phục vụ corpus luật đã hiệu chỉnh kỹ (mẫu `Điều` từng bị siết vì sinh 15 mục là mảnh câu). Nới nó ra là rủi ro hồi quy trên đường đang chạy tốt, để chữa một đường khác. |
| C | **Lớp mẫu RIÊNG cho docx, gọi `heading_level()` trước rồi mới thử mẫu mở rộng** | **Chọn** — đường luật không đổi một bit, phần dùng chung vẫn dùng chung. |
| D | Thêm tín hiệu định dạng (đậm, in hoa, căn giữa) từ python-docx | **Hoãn** — quyết định của chủ dự án 2026-09-04: đo trước với mẫu chữ, chỉ thêm nếu số đo cho thấy còn thiếu. Lý do: `xlsx_header.py` vừa bị review toàn nhánh gắn cờ vì tích luỹ cơ chế; không lặp lại bằng cách bắt đầu từ nhiều cơ chế. |

## 4. Thang cấp

`parse_docx` và `parse_pdf` không bao giờ trộn trong cùng một tài liệu, nên nhánh docx dùng
**thang riêng, rộng hơn**: ánh xạ 1-5 của `heading_level()` sang bội số 10 rồi chèn tầng mới vào
khoảng trống.

| tầng | cấp | nguồn |
|---|---|---|
| PHẦN | 5 | mới |
| Chương | 10 | `heading_level()`=1 |
| dòng IN HOA | 20 | =2 |
| Mục | 30 | =3 |
| `I.`, `II.` | 35 | mới |
| `A.`, `B.` | 38 | mới |
| Điều N. | 40 | =4 |
| `1.`, `12.` | 45 | mới |
| `1.1`, `12.1` | 50 | =5 |

`chunk_text_blocks` chỉ so cấp bằng `>=` nên thang không cần liền mạch — thang rộng làm quan hệ
giữa các tầng thành tường minh và chỉnh được mà không đụng hàm dùng chung.

**Các con số này là ĐỀ XUẤT KHỞI ĐIỂM, không phải chốt.** Phải hiệu chỉnh trên 12 tệp thật kèm
bảng đo, đúng cách `SCAN_LIMIT`/`MIN_SCORE` của kế hoạch 2 đã làm. Chỗ biết trước là đáng ngờ:
`I.` đặt TRÊN `Điều` khớp văn bản hành chính (I./II. là mục lớn), nhưng sai nếu tài liệu nào đó
dùng `I.` làm mục con của một Điều.

## 5. Quy tắc cốt lõi: đánh số trần phải TỰ CHỨNG MINH

Chia hai loại mẫu:

**Từ khoá** (`PHẦN`, và `Chương`/`Mục` sẵn có): nhận thẳng — chúng gần như không bao giờ là văn
xuôi.

**Đánh số trần** (`I.`, `A.`, `1.`): chỉ tính là tiêu đề khi **chính tài liệu đưa ra bằng chứng** —
một trong hai:
- có **ít nhất hai** mục KẾ TIẾP NHAU TRONG DÃY cùng họ (`I.` rồi `II.`), hoặc
- có **con mang cùng tiền tố** (`12.` là tiêu đề vì `12.1` tồn tại)

"Kế tiếp trong dãy" nói về **thứ tự đánh số**, KHÔNG phải về khoảng cách dòng: `I.` ở dòng 5 và
`II.` ở dòng 40 vẫn là bằng chứng hợp lệ — đó chính là hình dạng bình thường của một tài liệu có
cấu trúc. Nói rõ vì đọc lướt rất dễ hiểu thành "hai dòng liền nhau", và hiểu vậy thì quy tắc gần
như không bao giờ kích hoạt.

**Vì sao quy tắc này đáng giá hơn đoán theo thể loại.** Số trần một cấp là thứ văn bản luật **cố
tình loại** vì đó là *khoản* — nhận bừa thì một `Điều 5` có 4 khoản vỡ thành 4 mảnh thay vì một
chunk trọn. Nhưng trong `b09-dn.docx` thì `12.` là mục thật, và bằng chứng nằm ngay trong tài
liệu: `12.1` và `12.2` **đã được nhận là tiêu đề rồi**. Tức hiện tại **con là tiêu đề còn cha thì
không** — một sự bất nhất còn tệ hơn cả hai thái cực.

Quy tắc này cũng giết luôn ca dương tính giả rẻ tiền: một `A.` lạc giữa văn xuôi, một `I.` đứng
một mình.

## 6. Giao diện: nhận CẢ TÀI LIỆU, trả CẢ MẢNG

Vì bằng chứng ở mục 5 nằm ở phạm vi cả tài liệu, hàm không thể chấm từng dòng độc lập:

```
docx_heading_levels(texts: list[str]) -> list[int | None]
```

Cùng khuôn `find_header(rows)` của `xlsx_header.py`. Quan trọng: **nhận `list[str]`, KHÔNG nhận
đối tượng docx** — module vẫn là lá thuần, và phần lớn test tầng 1 không cần tệp `.docx` nào.

Đặt cạnh `heading_level()` trong `parse.py`, **không tách module riêng**: quy mô nhỏ (bốn mẫu +
một quy tắc bằng chứng), chưa đáng một module lá như `xlsx_header.py`.

## 7. Nối vào `parse_docx`: hai lượt

Hệ quả của mục 6: `parse_docx` thành hai lượt — cùng khuôn `parse_pdf` đã chạy hai lượt, không
phải kiểu mới.

1. lượt một: duyệt `doc.element.body` như hiện tại, gom text của mọi đoạn (và bảng), ghi lại đoạn
   nào **có style Heading** cùng cấp của nó
2. gọi `docx_heading_levels()` trên danh sách text
3. lượt hai: dựng block — đoạn có style Heading **ưu tiên style** (không đổi hành vi khi Word đã
   khai báo sẵn); đoạn không có style thì lấy cấp từ bước 2

**Cấp từ style phải ÁNH XẠ sang cùng thang, không dùng thô.** Word cho `Heading 1..9` tức cấp
1-9, còn thang mục 4 chạy 5-50 — dùng thô thì một `Heading 2` thành cấp 2, **cao hơn cả PHẦN (5)
lẫn Chương (10)**, và hất sạch mọi thứ phía trên nó. Ánh xạ: `Heading N` → `N × 10`, khớp tự
nhiên với các tầng đã có (Heading 1 ↔ Chương 10, Heading 2 ↔ dòng IN HOA 20, Heading 3 ↔ Mục 30).
Lỗi này tìm được khi tự soát spec, không phải khi chạy — ghi lại vì nó là loại lỗi "hai thang số
gặp nhau ở một chỗ không ai nhìn".

`quyche_ogop.docx` là bằng chứng ca **trộn** có thật (1 đoạn dùng style + 1 đoạn chỉ mẫu chữ bắt
được), nên đây không phải "hoặc style hoặc mẫu chữ cho cả tài liệu" mà là **quyết định theo từng
đoạn**.

Bảng vẫn `heading_level=None` như hiện tại — bảng là THÂN, không bao giờ là tiêu đề.

## 8. Sửa `chunking.py`

`doc_title` khi không có heading nào phải là **rỗng**, tuyệt đối không phải `source_file`.

Đây là bản sửa **chung cho mọi định dạng** (mục 2), nằm trong B3 vì đây là nơi nó lộ ra và đo
được. Hệ quả có chủ ý: tài liệu thật sự không có phân cấp sẽ có `section_path` rỗng — đúng, vì
"không biết" phải trông như không biết, không phải như một đường dẫn Windows.

## 9. Thử nghiệm

**Hai tầng, đúng khuôn spec 2026-08-29 mục 6.1:**

- **Tầng 1 — fixture trong repo, đáp án chắc 100%**: mỗi mẫu mới một test; và quan trọng nhất là
  test cho *quy tắc bằng chứng* — `I.` đứng một mình (không có `II.`) thì **không** phải tiêu đề;
  `12.` thành tiêu đề **vì** `12.1` tồn tại. Phần lớn chỉ cần `list[str]`, không cần tệp thật.
- **Tầng 2 — 12 tệp thật ở `tmp-docs/`**, mốc `live`, skip sạch khi thiếu.

**Hai chân đối chứng bắt buộc** (dự án có tiền sử cổng không gác gì):
- Tài liệu **thật sự không có phân cấp** phải ra breadcrumb **rỗng**, không phải một cấp bịa ra —
  chứng minh ta không dán nhãn tiêu đề cho mọi thứ.
- Gỡ bản sửa `chunking.py` → test "không chunk nào chứa đường dẫn tệp" phải **ĐỎ**.

**Phép thử phá riêng cho từng mẫu mới**: gỡ mẫu → test khoá của nó đỏ. Đúng lệ đã có.

## 10. Cổng nghiệm thu

Cố ý dùng lại đúng hình dạng ruling đã chứng minh là đúng ở kế hoạch 2 (`sai == 0` cứng, phần
còn lại báo cáo trung thực):

| | loại | nội dung |
|---|---|---|
| 1 | **cứng** | **0 chunk** mang đường dẫn tệp làm `section_path`, trên toàn corpus thật. Hôm nay `b09-dn.docx` là 74/74 — phải về 0. |
| 2 | **cứng** | Đường PDF **không đổi một bit**. `heading_level()` không bị đụng, nên bằng chứng là suite PDF hiện có giữ nguyên số. |
| 3 | báo cáo | Bao nhiêu tài liệu docx có phân cấp thật (hôm nay: gần như 0). **Không đặt ngưỡng cứng** — cùng lý do kế hoạch 2 đã bỏ `đúng >= 20`. |
| 4 | báo cáo | Phân bố **số chunk và kích thước chunk** trước/sau — nghĩa vụ đo cho mẫu số trần (mục 5). |

Cổng 1 mạnh vì **không cần gán tay đáp án nào**: "breadcrumb là đường dẫn tệp" là thứ máy tự kiểm
được, đúng tinh thần đáp án tự sinh mà kế hoạch 2 đã dùng.

## 11. Ngoài phạm vi

- **Tín hiệu định dạng** (đậm, in hoa, căn giữa) — phương án D mục 3, hoãn có chủ ý. Mở lại nếu
  số đo sau khi mở rộng mẫu chữ cho thấy còn thiếu thật.
- **Sửa `heading_level()`** — phương án B, loại.
- **Bảng trong docx** — B4 lo phần bóc bảng; ở đây bảng vẫn là thân.
- **Tách module riêng cho bộ dò docx** — chưa đáng, xem mục 6. Nếu nó phình lên thì tách sau.

## 12. Giới hạn đã biết và giả thuyết đã bị bác bỏ

- **"Hàm dò chữ có sẵn là đủ, chỉ cần nối vào docx"** — SAI, đo ra `B09a-DN` vẫn 0/28 (mục 1).
  Đây là giả thuyết đầu tiên của tôi và số đo bác nó.
- **Thang cấp mục 4 chưa được hiệu chỉnh** — là đề xuất, không phải kết quả đo.
- **Mẫu số trần có hệ quả tới retrieval, không chỉ breadcrumb** — chia nhỏ chunk là đổi hình dạng
  thứ đem đi embed; phải đo phân bố chunk (cổng 4), không được suy.
- **12 tệp thật đều là biểu mẫu/quy chế** — không có tài liệu Word văn xuôi dài (hợp đồng, báo
  cáo dài) trong kho. Mẫu hành chính có thể không đại diện cho loại đó.
- **`quyche_taichinh.doc` đi qua cầu LibreOffice** trước khi tới `parse_docx`, nên nó cũng gián
  tiếp kiểm đường chuyển đổi của kế hoạch 1.
