# OCR bậc 3 — VLM đọc trang bảng Tesseract hỏng hẳn, số được KIỂM bằng số học

## Context

Người dùng đính kèm `DVT_2022.pdf` (báo cáo tài chính công lập scan, TT 107/2017, 16
trang) qua Open WebUI, hỏi *"tổng tài sản đầu năm là bao nhiêu"*. Endpoint trích tài liệu
chạy đúng (40.953 ký tự). Trả lời: "không có thông tin", dẫn nguồn tài liệu khác.

Đã đo: trang 7 (bảng TÀI SẢN) dưới Tesseract PSM 6 mất **cả nhãn lẫn số**. Nhãn:
`'Pap s'`, `'F káananyee'`. Số: chỉ **1/8** token dài đúng (`83316921` cho `8.331.692.341`,
`4555344000` cho `3.555.344.000`). Chỉ 4/38 hàng có ≥2 số. `TỔNG CỘNG TÀI SẢN` không tồn
tại trong bản trích.

Đã thử và **bị bác bỏ bằng số đo** (merge `bb0e845`): đổi PSM toàn cục (3 cổng đỏ), PSM
thích ứng theo conf (`T=85` là lưỡi dao), và `mean_conf` không phải thước chất lượng đọc.
Phép "VLM chỉ đọc nhãn, ghép theo số Tesseract" bị bác trong lượt thiết kế này: sản lượng
**nghịch với nhu cầu** — 16–17 hàng ở trang đã tốt, **4 ở trang 7, 0 ở trang 12**.

**Quyết định chủ dự án (2026-09-11)**: nới Ràng buộc 1 ("LLM không viết chữ số") **CHỈ**
cho trang Tesseract hỏng, với điều kiện số **được kiểm bằng số học** trước khi lưu. Thiết
kế 2026-09-04 §9 đã gọi cổng số học là *"cơ chế DUY NHẤT có thể cho phép sửa một chữ số
an toàn"* — đây là dùng đúng cái đó. Cả ba vai VLM (đọc dự phòng / mô tả hình / làm giàu
token) đều muốn; **spec này = nền + vai đọc dự phòng**. Khoá Gemini có rỗi để dành riêng.

## Bốn dữ kiện đo được đã đổi thiết kế

| | dữ kiện | hệ quả |
|---|---|---|
| F1 | Trên trang kích hoạt, số Tesseract đọc **1/8 đúng** — con số 35/37 đo trên trang Tesseract *đọc được* | Tesseract **không được** làm phủ quyết; chỉ làm chứng thực + kiểm hướng cột |
| F2 | **Mẫu TT 107 in công thức trong nhãn**: `(50=01+05+10+20+25+30+40+45)`, `(09=01-05)`, có dấu âm. Mẫu TT 99 chính thức cũng in `(280 = 100 + 200)`, `(50 = 20+30+40)`. Đã kiểm tay: **mọi tổng in trên DVT tr7/8/9 khớp tới đồng** | Tầng ràng buộc mạnh nhất là **công thức in sẵn** — trên giấy, không phải bảng ta nuôi, không phải LLM đoán |
| F3 | SCID là **TT 99/2025**, không phải TT 200 (mã 280). `tmp-docs/b01-dn.docx`, `b03-dn-*.docx` là mẫu chính thức TT 99, đọc máy được | Bảng mã số theo thông tư **suy ra từ mẫu chính thức**, không gõ tay; corpus có ≥3 thông tư |
| F4 | DVT trang 12 (0/115) là **trang xoay ngang** | Lỗi xoay ≠ lỗi in. `pytesseract.image_to_osd` (tất định, miễn phí) trước VLM; tín hiệu dấu tiếng Việt đang **gộp hai lớp lỗi** khác giá |

Và một lỗ hổng trong mã hiện tại phải đóng cùng lượt: **không gì phía sau đọc
`source_kind`**. `src/rag/retrieve.py::_COLS` không chọn nó, `Chunk` không mang nó,
`src/rag/extract.py:68` gộp thành `"ocr" if any(...=="ocr") else "text"` → trang toàn VLM
chưa kiểm sẽ mang nhãn **`text`**, bậc tin cậy cao nhất. "To tiếng" hôm nay dừng ở log.

## Kiến trúc — giữ hợp đồng 2026-09-04, thêm một module lá

| tầng | tệp | việc |
|---|---|---|
| 0 — máy đọc | `src/ocr/engine.py` · **`src/ocr/vision.py` (mới)** | `read_table(png) -> VisionTable`; không biết PDF/trang/DB |
| 0 — kiểm | **`src/ocr/so_hoc.py` (mới)** | parse hàng, công thức in sẵn, bất biến cấu trúc, phân cấp, bảng thông tư, đánh giá, trạng thái hàng. **Lõi đánh giá chuyển từ `tests/fixtures/ocr_bang_that/kiem_so_hoc.py` vào đây, CLI uỷ quyền lại** — một thước duy nhất, để test 85/85 hiện có canh chính bộ đánh giá production |
| 1 — tài liệu | `src/ocr/document.py` | định tuyến: OSD xoay → grid Tesseract → **kiểm số học trên grid Tesseract** → nếu không vouch được → VLM → kiểm → `Region` |
| 2 — consumer | `src/rag/parse.py`, `src/rag/extract.py` | `parse.py` gắn `source_kind` từ Region; `extract.py:68` sửa gộp theo **bậc xấu nhất** |

## Xác minh số học — bốn tầng, thứ tự ưu tiên rõ

| tầng | bắt được | mù với | ưu tiên |
|---|---|---|---|
| **(e1) công thức in sẵn** trong nhãn — parse tất định `(\d+[a-z]?)\s*=\s*([^)]+)`, hạng tử `±\d+[a-z]?`, cho ngoặc lồng | mọi ô đọc sai trong hàng được tham chiếu, cả hai cột; hàng thành phần ≠0 bị rơi; đảo cột một hàng | hàng không được công thức nào tham chiếu; hai lỗi triệt tiêu cùng cột (rất hiếm); **giải ngược** (VLM tính thành phần cuối = tổng − còn lại); **đảo cột toàn trang** (mọi tổng vẫn khớp) | **cao nhất** — là phát biểu của chính tài liệu |
| **(e2) bất biến cấu trúc** — mã số tăng dần trong trang (`411a/411b` so (int, hậu tố)); `len(so_tien)` = số cột khai báo; mỗi `so_tien` khớp `^\(?\d{1,3}(\.\d{3})*\)?$` hoặc `-`; không trùng mã số | hàng gộp, hàng lặp, `13`→`18`, thừa/thiếu cột, rác trong ô tiền | đọc sai giữ thứ tự (`14`→`15`) | cổng, không phải ràng buộc — chạy trước số học |
| **(c) bảng thông tư** — `src/ocr/ma_so/tt99.json`, `tt107.json`; **suy từ mẫu docx chính thức** (mức đánh dấu + mã số → cha/con), chọn theo số thông tư Tesseract đọc ở header (`107/2017/TT-BTC` đọc đúng nguyên văn trên tr7 dù thân trang rác) | cùng lớp với (e1) trên mọi quan hệ chuẩn nơi không in công thức (`110=111+112`) | hàng ngoài chuẩn; trang thuyết minh; chọn nhầm bảng mà tình cờ qua (đo Q4) | (e1) thắng khi cùng tổng khác thành phần → cảnh báo nêu cả hai |
| **(b) phân cấp đánh dấu** — `I.` = Σ `1.`,`2.`… tới `I.` kế; hàng không đánh dấu ngay dưới hàng số là thành phần của nó; `A/B` = Σ la-mã. **CHỈ trang B01** | sai cha/con trên thông tư chưa có bảng | **sai trên B02/B03** (SCID tr16 phẳng `1.`…`23.` có dấu; tr17 thành phần đứng trước tổng) | thấp nhất, chỉ điền chỗ (e1)/(c) chưa phủ |
| **(a) Tesseract đồng ý** | VLM bịa số mà Tesseract đọc đúng — nhưng tập đó ~1/8 trên trang kích hoạt (F1) | gần hết | **không bao giờ phủ quyết**. Việc thật: token Tesseract có toạ độ x → kiểm cột 0 của VLM có phải cột tiền trái không — phòng thủ rẻ duy nhất cho điểm mù "đảo cột toàn trang". Ghi `|T|`, `|T∩V|` mỗi trang |

Hai thứ số học **không kiểm được**, phải nói ra trong artifact và báo cáo:
- **Nhãn.** `10 = 11 + 14` không nói `Các khoản phải thu` hay `phải trả`. Mà nhãn là thứ người
  dùng tìm. Giảm nhẹ ở lát 5: bảng (c) mang nhãn chuẩn theo mã số, so `fold_vi(nhan)`
  bằng chồng lấp token → lệch thì **cảnh báo**, không bao giờ loại (đơn vị tuỳ biến nhãn).
- **Giải ngược.** VLM đọc đúng tổng và n−1 thành phần rồi *tính* cái cuối → qua. Hàng
  trong đúng một ràng buộc, không có Tesseract chứng thực, mang dư số này. Q7 đo trực tiếp.

## Quy tắc theo hàng — tất định, không bao giờ lưu hàng thất bại

Parse: mỗi `so_tien[k]` → `int` | `DASH` | `BAD` (`(x)` = âm). Hàng khoá theo `ma_so`.
Hàng `ma_so == null` (tiêu đề mục như `TÀI SẢN`) không có ô số, lưu là block nhãn thuần.
Tập ràng buộc C = khử-trùng-theo-tổng( (e1) ∪ (c) ∪ (b)-điền-chỗ ).

Đánh giá ràng buộc c ở cột k: **`NA`** nếu hàng tổng vắng, hoặc hàng tham chiếu nào có
`BAD` ở k, hoặc mã số tham chiếu trùng, hoặc (lượt này) tham chiếu ngoài trang. Mã số
**thành phần** vắng = 0 **chỉ để tính**, và **đếm số thành phần vắng** vào kết quả — đây
KHÔNG phải bẫy `null` README ghi (đó là hàng tiêu đề bị cộng thành 0); ở đây là vắng-khỏi-
trang, được đếm và báo. Còn lại **`PASS`** iff Σ hệ_số·giá_trị == tổng chính xác, else
**`FAIL`** kèm độ lệch.

Trạng thái hàng, xét theo thứ tự, khớp đầu tiên thắng:

1. **REJECTED** (không lưu; `Warning` nêu tệp, trang, mã số, lý do): có `so_tien[k]` là
   `BAD`; hoặc `len(so_tien) != K`; hoặc hàng được **bất kỳ** ràng buộc `FAIL` nào tham
   chiếu ở **bất kỳ** cột (tổng hay thành phần — cả cụm hàng của ràng buộc đó đi, cảnh báo
   nêu phạm vi: *"loại 9 hàng vì 50=… lệch 1.000.000 ở cột 0"*); hoặc trùng mã số.
2. **`vision_verified`**: không bị loại, có ≥1 ô số, và với **mọi** cột k hàng có số, ≥1
   ràng buộc tham chiếu hàng có `PASS` ở k.
3. **`vision_unverified`**: còn lại — 0 ràng buộc phủ, hoặc toàn `NA`, hoặc toàn `-`, hoặc
   trang có mã số **không đơn điệu** (cả trang bị trần ở `unverified` — không biết hàng nào
   lệch, hàng gộp là nguyên nhân dễ nhất).

Cổng trang trước khi xét hàng: VLM trả < 2 hàng có mã số, hoặc `trang.thong_tu` lệch với
header Tesseract → trần `unverified` + cảnh báo. Không ngưỡng nào ngoài "≥2".

Tesseract đồng ý **không nâng bậc** — ghi `tess_khop` từng ô trong artifact, đếm vào cảnh
báo trang, nhưng không đổi hạng (F1: quá thưa trên trang kích hoạt để có nghĩa).

## Xuất xứ — ba kênh, đều bắt buộc

1. **Bậc**: mở rộng `src/rag/chunking.py::_XUAT_XU_RANK` (dòng 13) thành
   `text 0 < ocr 1 < ocr_repaired 2 < vision_verified 3 < vision_unverified 4 < vision_description 5`.
   `vision_verified` **dưới** mọi bậc Tesseract-thuần (vẫn là LLM viết chữ số — thật về xuất
   xứ) nhưng trên `vision_description` (đã kiểm ngoài). Đây là **lựa chọn chính sách, chủ dự
   án xác nhận**. Sửa `extract.py:68` lấy bậc **xấu nhất**. Quy tắc gộp `max(rank)` không
   đổi — vì thế một block mỗi hàng (`atomic: True`, `_khoi_tu_luoi_anh` đã làm) mới quan
   trọng: nếu không, một hàng `unverified` kéo cả chunk `verified` xuống.
2. **Người vận hành**: mỗi trang VLM phát **đúng một** `Warning(path, "trang N (VLM)", …)`
   với đếm `xác minh a/b hàng tiền · chưa xác minh c · loại d · ràng buộc p/q thoả ·
   Tesseract đồng ý t/u ô` — **luôn phát**, không chỉ khi lỗi, để lượt xác minh 0 hàng nhìn
   khác lượt xác minh 12 hàng.
3. **Prompt tổng hợp**: thêm `source_kind` vào `retrieve._COLS` và `Chunk`; render tag mỗi
   chunk khi `source_kind != "text"` — với `vision_unverified`: *"số liệu do mô hình đọc
   ảnh, CHƯA kiểm được bằng số học — không trích như số chính xác"*. **Không** nhét marker
   vào `chunk_text` (bẩn BM25/embedding). Không có kênh này thì "to tiếng" dừng ở log.

## Kích hoạt — số học vouch trước, dấu tiếng Việt chỉ là lọc thô

Cho trang bị tín hiệu dấu-tiếng-Việt gắn cờ:
1. **OSD xoay** (`image_to_osd`, tất định): góc ≠ 0 → xoay, OCR lại **dưới dấu tay có góc
   xoay**. Trang 12 có thể **không cần VLM** (F4). Đo Q6 xem bao nhiêu trang cờ là xoay.
2. Dựng hàng từ **grid Tesseract** (`table_row_runs` + `find_header_rows`/`column_names`
   đã đặt tên `Mã số`/`Số cuối năm` trên 0,611 hàng scan), chạy **cùng bộ kiểm**.
   ≥1 `PASS` và 0 `FAIL` → **không gọi VLM**, lưu hàng Tesseract là `ocr` — số học vouch
   cho số, nhãn vẫn của Tesseract, cảnh báo trang nói rõ. Tín hiệu kích hoạt thật là *"số
   học không vouch được cho Tesseract"*; dấu tiếng Việt chỉ giữ số lượt VLM có giới hạn.
3. Còn lại → gọi VLM.

Răng của bảo vệ này **chưa biết**: Tesseract đọc sai mã số ngắn 21%, nên nhiều ràng buộc
trên grid Tesseract sẽ `NA` (mất khoá). Trên SCID tr17 với 3/14 mã số sai, `08=01+…+07`
mất khoá → có thể 0 ràng buộc đánh giá được → **không bảo vệ đúng trang tốt**. Q2 đo;
nếu ~0 thì quy tắc hạ thành "bất kỳ PASS nào bảo vệ" và ngưỡng dấu tiếng Việt gánh chính.

Lượt này **không trộn** hàng Tesseract-đã-kiểm với hàng VLM cùng trang — một xuất xứ mỗi
trang. Ghi là tinh chỉnh sau.

## Hợp đồng VLM — mù với Tesseract, chuỗi nguyên văn

```json
{"trang": {"mau": "B01/BCTC", "thong_tu": "107/2017/TT-BTC",
           "cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
 "hang": [{"muc": "III.", "nhan": "Các khoản phải thu", "ma_so": "10",
           "thuyet_minh": null, "so_tien": ["19.078.257.265", "8.331.692.341"]},
          {"muc": null, "nhan": "TỔNG CỘNG TÀI SẢN (50=01+05+10+20+25+30+40+45)",
           "ma_so": "50", "thuyet_minh": null, "so_tien": ["79.611.117.804", "69.862.687.223"]}]}
```

- `so_tien` là **chuỗi nguyên văn** có dấu phân cách và ngoặc; parse trong mã. Mẫu nhóm-3
  là tự kiểm trên chính output VLM.
- `thuyet_minh` tách riêng để `III.2` không lọt vào `so_tien`.
- `nhan` nguyên văn **kể cả công thức in** — công thức parse trong mã, **không** hỏi model
  trích ra (hỏi trích là hỏi diễn giải; ta muốn chép).
- `cot_gia_tri` khai số cột để (e2) ép độ rộng hàng.
- `trang.thong_tu` là kiểm chéo với header Tesseract, **không** là nguồn chọn bảng.
- VLM **không xem** Tesseract: nếu xem, nó lặp số Tesseract và mọi kiểm chéo mất độc lập.
- JSON hỏng → trang không nhận gì, log **độ dài** phản hồi, đếm lượt thất bại. Prompt có
  phiên bản.

## Nền (lát 2) — bốn thứ phải xong trước lượt gọi VLM đầu tiên (§18)

1. **Khoá riêng** `YOUDOO_VLM_API_KEY[_2.._9]`. Không có → VLM tắt hẳn, log có tên lần đầu.
   Không cấu hình = không tiêu một lượt hạn mức chat nào.
2. **`KeyRing`** tách từ `router.py::_xoay_khoa` (dòng 236) vào `providers.py` cạnh
   `keys_for`: chỉ xoay khi 429; hết khoá về 0 (cửa sổ trượt 24h); quét trọn dải hậu tố,
   khử trùng. `Router` uỷ quyền; `vision.py` dùng cùng lớp với tiền tố khác. **Chỗ duy
   nhất chạm mã đường chat** — chốt: test xoay khoá hiện có qua không đổi một byte hành vi.
3. **Trần cứng** `VLM_MAX_CALLS_PER_INGEST` (suy luận từ §10: 500 rpd/khoá, để ≥60% ⇒ 200;
   ghi rõ là suy luận). Vượt → dừng VLM, tiếp bằng Tesseract, cảnh báo có tên `IngestReport`.
4. **Đếm** `store.record(alias="vlm-ocr", provider="google", …)` vào `llm_usage`.
5. **Dấu tay** `config_fingerprint()` thêm model VLM + phiên bản prompt + **góc xoay OSD**.
   Không bump `ARTIFACT_VERSION`.

`vision.py` tái dùng `client_for(spec, api_key=…)` (đã có `MAX_RETRIES`). Bẫy đã trả giá
hai lần: `.invoke().content` là **list block** — bóc đúng, test riêng.

## Chín phép đo TRƯỚC khi chọn hằng số nào (1–6 không cần API)

| # | đo gì, trên gì | kết quả BÁC BỎ thiết kế |
|---|---|---|
| 1 | (e1)+(c-suy-từ-docx)+(b) trên 7 đáp án SCID **đã bỏ `rang_buoc_so_hoc`**, theo hình dạng hàng VLM | ràng buộc tay nào không suy ra được (thiếu); hoặc **ràng buộc suy ra nào FAIL trên đáp án đã duyệt** (đáp án là chân lý → ràng buộc sai). Thước hỏng được **cả hai chiều**. Kỳ vọng: (b) một mình FAIL trên tr16/tr17 — đó là số đo biện minh cho việc giới hạn (b) vào B01 |
| 2 | bộ kiểm trên grid Tesseract đệm sẵn của 95 trang scan (`tools/calibrate_vlm_trigger.py`, cùng khuôn `calibrate_table.py`): tỉ lệ dấu, `|T|`, ràng buộc đánh giá được/PASS/FAIL, góc OSD | trang tốt (SCID 12–18) có ~0 ràng buộc đánh giá được → bảo vệ Q4 không răng; hoặc trang **đã duyệt** nào FAIL → ánh xạ grid→hàng sai, không phải trang sai |
| 3 | chất lượng Tesseract làm oracle trên DVT tr7/8/9 với đáp án tay mới | (a)-làm-phủ-quyết bị bác nếu < ~0,9 — tr7 đã 1/8, đây chỉ biến khẳng định thành số ghi |
| 4 | tỉ lệ **qua nhầm bảng**: áp TT 107 lên SCID, TT 99 lên DVT | ràng buộc không tầm thường nào PASS dưới bảng sai → `PASS` ít nghĩa hơn enum hàm ý, chọn thông tư phải là cổng cứng |
| 5 | **break-test** dạng pytest theo 4 bẫy README: đổi 1 chữ số thành phần → loại + nêu mã số; đổi tổng → cả cụm loại; xoá hàng thành phần ≠0 → FAIL; xoá hàng `-` → vẫn PASS với `vắng=1`; `1.`→`I.` trong nhóm (b) → FAIL; đảo cột một hàng → FAIL; **đảo cột mọi hàng → số học QUA và kiểm x-toạ-độ (a) phải là thứ bắt** (test ghi lại điểm mù và chứng minh kiểm phụ còn sống); `"8.812.478.00O"` → BAD → loại | bất kỳ ca nào không đỏ đúng chỗ |
| 6 | OSD trên 95 trang: bao nhiêu trang cờ-dấu là **xoay** | đa số là xoay → "VLM là thuốc cho trang rác" bị bác, thuốc là xoay |
| 7 | **thăm dò giải ngược** (sống, ~6 lượt): gửi ảnh tr7 với **một ô thành phần bôi đen** (PIL, tất định); VLM trả số = tổng − còn lại thay vì null → số học có lỗ đã chứng minh; hàng trong đúng một ràng buộc phải mang dư số có tên hoặc cần (a) chứng thực mới `verified`. Lặp cho ô tổng và ô `-` | VLM giải ngược |
| 8 | **độ chính xác sống vs đáp án** (~14 lượt, chạy 2 lần cho tất định): VLM trên SCID 12–18 (ép kích hoạt) + DVT 7–9, so từng ô | **bất kỳ ô sai nào được lưu `vision_verified`** (số 0 cứng). Ghi thêm: hàng đúng bị loại (chi phí phạm vi), độ phủ, đồng ý giữa 2 lượt, `trang.thong_tu` khớp header. **Lưu JSON thô làm fixture** để mọi thay đổi bộ kiểm sau chạy offline |
| 9 | ngưỡng dấu tiếng Việt — **chỉ sau** 2 và 6: phân bố tỉ lệ trên 95 trang scan **và** trên trang vector rasterise (đối chứng biết-tốt, ý §13) | hai phân bố chồng lấp ở chỗ trang cờ nằm → thước không tách, ngưỡng sẽ là lưỡi dao `T=85` thứ hai |

## Chia lát — bộ kiểm ĐI TRƯỚC ống dẫn, để lượt gọi VLM đầu tiên đã có thứ bác được nó

| lát | nội dung | tệp | ship gì |
|---|---|---|---|
| **0** | **Bộ kiểm là module lá, không API.** Parse hàng, (e1), (e2), (b), loader (c) từ `src/ocr/ma_so/*.json`, đánh giá, trạng thái hàng, dataclass báo cáo trang. **Chuyển lõi `kiem_so_hoc.py` vào, CLI uỷ quyền.** Fixture: SCID bỏ ràng buộc; **đáp án mới `DVT_2022_tr7/8/9.json` viết từ ảnh TRƯỚC khi nhìn output VLM** (giao thức README), schema thêm `thong_tu`, `mau`. Test Q1, Q4, Q5 | `src/ocr/so_hoc.py`, `src/ocr/ma_so/tt99.json`, `tt107.json`, `tests/fixtures/ocr_bang_that/kiem_so_hoc.py` (uỷ quyền), 3 fixture DVT, `tests/ocr/test_so_hoc.py` | **một con số**: độ phủ ràng buộc suy ra trên 10 trang, 2 thông tư |
| **1** | **Công cụ đo, không API.** Q2, Q3, Q6, Q9. Xử lý xoay vào đây nếu Q6 nói đáng | `tools/calibrate_vlm_trigger.py` + `_result.txt`; có thể `document.py` (OSD) | bảng chọn quy tắc kích hoạt và ngưỡng (nếu có) |
| **2** | **Ống dẫn VLM** (nền ở trên) + **bắt fixture**. Test `live` gọi DVT tr7 **một lần**, ghi phản hồi thô vào `tests/fixtures/ocr_bang_that/vlm_raw/`, rồi chạy bộ kiểm lát 0 offline. Q7, Q8 chạy ở đây **một lần**, giữ phản hồi thô | `src/ocr/vision.py`, `providers.py` (`KeyRing`), `router.py` (uỷ quyền), `document.py` (dấu tay), `store.py` alias | fixture thô + số Q7/Q8 |
| **3** | **Nối vào `parse_pdf`.** Trong `_doc_trang_bang_anh`/`_khoi_tu_luoi_anh`: kích hoạt → (kiểm grid Tesseract → có thể bỏ) → VLM → kiểm → block `source_kind ∈ {vision_verified, vision_unverified}`, hàng loại log theo mã số. Mở `_XUAT_XU_RANK`, sửa `extract.py:68`, ghi enum vào `schema.sql`. Test với client giả (như `Router(client_factory=…)`) trả fixture đã bắt **với một chữ số bị đổi** → block vắng, cảnh báo có | `src/rag/parse.py`, `src/rag/chunking.py`, `src/rag/extract.py`, `src/rag/schema.sql`, `src/ocr/document.py` | đường production chạy được |
| **4** | **Xuất xứ tới prompt tổng hợp.** `retrieve._COLS` + `Chunk.source_kind` + tag prompt. Nhỏ; **không có nó thì lát 0–3 chỉ to tiếng với người vận hành** | `src/rag/retrieve.py`, `src/rag/types.py`, prompt tổng hợp | cờ tới người dùng |
| **5** | sau: so nhãn chuẩn từ (c); lượt cấp tài liệu cho đồng nhất xuyên trang/xuyên báo cáo (`50=80`, `280=100+200`, `B02:50=B01:72`) tái dùng `nhom:ma` của `kiem_so_hoc.py`; tầng tổng-ma-trận cho trang thuyết minh; bảng TT 200/2014 khi có trang TT 200 kích hoạt thật | — | — |

## Xử lý lỗi — to tiếng, qua `IngestReport` sẵn có

| tình huống | hành vi |
|---|---|
| không có khoá VLM | tắt hẳn, log có tên lần đầu; trạng thái cấu hình, không phải lỗi |
| 429 hết cả tập khoá VLM | dừng VLM phần còn lại lượt nạp, tiếp bằng Tesseract, cảnh báo + số trang bỏ |
| chạm trần | y hệt, lý do khác tên |
| timeout / không tới | bỏ trang, log, đếm; không thử lại ngoài `MAX_RETRIES` |
| JSON hỏng | bỏ trang, log độ dài, đếm |
| hàng FAIL ràng buộc | **không lưu cả cụm**, cảnh báo nêu công thức, độ lệch, phạm vi |
| trang mã số không đơn điệu | cả trang trần `unverified`, cảnh báo |

## Nghiệm thu

1. Test đơn vị lát 0 xanh, **và** `tests/ocr/test_dap_an_so_hoc.py` **vẫn 85/85** sau khi lõi
   chuyển sang `so_hoc.py` — đó là bằng chứng bộ đánh giá production và thước cũ là một.
2. Bảng Q1–Q6 tồn tại trong `tools/calibrate_vlm_trigger_result.txt` và ghi chú thi hành,
   **trước** khi lát 2 gọi API lần đầu.
3. Q8: **0 ô sai được lưu `vision_verified`** trên 10 trang có đáp án. Số cứng.
4. Break-test Q5 đỏ đúng chỗ, kể cả ca đảo-cột-toàn-trang được kiểm phụ bắt.
5. Suite đầy đủ xanh (`-m "not integration and not live"`, nền 2509 passed / 1 skipped);
   tự-nuôi **giữ 0,9473** (VLM không kích hoạt trang văn xuôi); lát 3 tên cột toàn corpus
   ≥0,56.
6. **Sống**: đính kèm lại `DVT_2022.pdf` qua Open WebUI, hỏi *"tổng tài sản đầu năm là bao
   nhiêu"*. Trước: "không có thông tin" + dẫn nguồn sai. Sau: trả lời **đúng giá trị hàng
   mã số 50, cột "Số đầu năm", trong đáp án tay `DVT_2022_tr7.json`** — đáp án đó được
   viết ở lát 0 **từ ảnh, trước khi nhìn bất kỳ output VLM nào** (giao thức README). Block
   đó phải là `vision_verified`. Nếu ra `unverified` → tag prompt phải hiện ra trong câu
   trả lời.

   Ghi chú trung thực: Plan agent đọc ảnh tr7 ra `79.611.117.804 / 69.862.687.223` cho mã
   số 50 và nói đã kiểm tay công thức `50=01+05+…+45` khớp tới đồng. **Tôi chưa tự kiểm
   con số đó**, và nó không khớp dòng `750.005.854 40.565.652.481` tôi thấy dưới PSM 4
   (nhiều khả năng là hàng `Tiền`, mã 01 — nhưng chưa xác minh). Lát 0 chốt bằng đáp án
   tay; **không** hardcode con số vào test trước khi đáp án được viết và đối chiếu.

## Điều chưa chắc, nói thẳng

- Thông tư của SCID là **suy** (TT 99/2025) từ mã 280 và mẫu docx, chưa đọc header ảnh
  SCID tr12. Đọc trước khi đặt tên tệp bảng.
- TT 99 B02-DN có in công thức tổng phụ không: **tin, chưa đo** (`b02-dn.docx` trong
  tmp-docs là bản B01 dán nhầm). Đọc ảnh SCID tr16 trước khi cho (e1) phủ báo cáo KQKD.
- Vị trí bậc `vision_verified` so với `ocr` là **chính sách** — chủ dự án xác nhận.
- Bảo vệ kích hoạt bằng grid Tesseract (Q4) có ràng buộc đánh giá được hay không: Q2.
- Tần suất giải ngược của flash-lite: Q7. Có → `vision_verified` cho hàng trong đúng một
  ràng buộc cần định nghĩa chặt hơn.
- Độ phủ TT 107 dựa trên **3 trang của 1 tài liệu**; TT 99 trên 7 trang của 1 tài liệu.
- Trang thuyết minh ~0% dưới (e1)/(b)/(c). SCID: 4/63 trang là báo cáo chính; DVT: 4/16.
  Độ phủ **cấp tài liệu** sẽ thấp nếu trang thuyết minh kích hoạt — đo bằng cách đếm token
  `MONEY` theo trang có/không có cột mã số trên 95 trang, từ grid đệm sẵn.
