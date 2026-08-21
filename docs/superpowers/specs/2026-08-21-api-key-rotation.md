# Xoay khoá API bên trong một mắt xích

**Ngày**: 2026-08-21 · Đóng **mục 7** trên `docs/trang-thai-chung.md`.

## 1. Vấn đề

`providers.ENV_KEYS` ánh xạ **một upstream ↔ một biến môi trường**
(`google → GOOGLE_API_KEY`). Hạn mức free tier của Google tính theo
**project/model/ngày**, nên hai khoá của hai project là **hai ví riêng** —
nhưng hệ không biết điều đó, và cạn một khoá là cạn cho cả bảy vai.

Ngày 2026-08-21 chuyện này chặn công việc **hai lần**: một lần khi hỏi tồn kho
(`ChainExhausted` vai `read`), một lần khi chạy job e2e (3/14 kịch bản không
nghiệm thu được). Xem `2026-08-21-e2e-jobs-port.md` §5.2.

## 2. Thiết kế: xoay BÊN TRONG một mắt xích

    read, prefer=3.1:  [3.1-flash-lite] → [3.5-flash-lite] → [groq-llama] → [or-nemotron]
                        ↑ k1→k2→k3        ↑ k1→k2→k3

Khoá xoay *trong* một mắt xích, **không thành mắt xích mới**. Đây là điều kiện
để không phá **bất biến #1** (không hai mắt xích chung upstream): bất biến đó
tồn tại để tránh rơi từ một miền lỗi vào lại chính nó, mà ba khoá là **cùng
miền nhưng khác ví** — chuyện nó không nói tới.

### 2.1 Ba quyết định

**Chỉ xoay khi 429.** `or-nemotron` trả 404 "Provider returned error / Nvidia"
**16/16 lượt** (mục 10 bảng chung); xoay khoá ở đó chỉ đốt thêm lượt gọi cho
một provider đang hỏng. Điều kiện dùng đúng `_is_rate_limit` sẵn có.

**Chỉ cooldown model sau khi CẢ BA khoá đều 429.** `_cooldown_for` khoá theo
`spec.alias`, nên trước bản này cạn một khoá là chặn model đó cho *mọi* khoá.
Không sửa chỗ này thì thêm khoá cũng vô ích.

**Không đụng sổ ngân sách.** `llm_usage` đếm theo alias, không phân biệt khoá.
Xoay khoá dựa **hoàn toàn vào 429 thật**, đúng luật vận hành đã ghi
(*"`llm_usage` KHÔNG dùng để chẩn đoán hạn mức"*). Nói thẳng hệ quả: sau bản
này sổ càng kém phản ánh hạn mức thật hơn nữa. Sửa nó thành (alias, khoá) là
một đợt riêng.

### 2.2 Hết khoá thì ĐẶT LẠI về khoá đầu

Không giữ ở khoá cuối. Hạn mức ngày của Google là **cửa sổ TRƯỢT 24h** — đo
2026-08-21: model vừa báo `PerDayPerProjectPerModel` trả 200 lại sau vài phút.
Giữ nguyên ở khoá cuối là tự khoá mình vào cái ví cạn gần nhất.

Chỉ số khoá sống trong **bộ nhớ tiến trình** (giống cooldown), không lưu bền:
một lượt 429 dạy lại ngay, còn lưu bền thì một lần cạn tạm thời sẽ đóng đinh
khoá đó là "hỏng" mãi mãi.

### 2.3 `keys_for` — hai chi tiết chống lỗi im lặng

**Quét trọn dải hậu tố** (`_2`…`_9`) thay vì dừng ở chỗ trống đầu tiên: xoá một
khoá hỏng rồi để trống `_2` là chuyện thường, và dừng sớm sẽ **im lặng vứt**
khoá `_4`.

**Khử trùng giữ thứ tự**: dán nhầm cùng một khoá vào hai biến là lỗi sao chép
rất dễ xảy ra; không khử thì mỗi lượt 429 trả giá hai lần cho cùng một ví.

## 3. Ba chỗ phát sinh ngoài dự kiến

### 3.1 Hợp đồng `client_factory` phải đổi

Thành `(spec, api_key=None)` — 24 chỗ trong test. Cân nhắc phương án giữ nguyên
(router gọi 1 tham số khi không xoay, 2 tham số khi xoay) và **bác**: một hợp
đồng lúc thế này lúc thế kia là cái bẫy nằm chờ. Nhất quán còn hơn chạy được
nhờ may.

### 3.2 Test đang đọc `.env` THẬT — số khoá phụ thuộc máy chạy

`tests/conftest.py` gọi `load_dotenv` trên `.env` ở gốc repo. Máy này có ba
khoá, nên ngay lượt chạy đầu sau khi thêm cơ chế, `test_sau_429_mat_xich_do_bi_
cooldown_o_luot_sau` thấy **3 lượt gọi thay vì 1** — cùng một test cho kết quả
khác nhau trên máy có 1 khoá và máy có 3.

Bịt ở gốc: fixture autouse trong `tests/llm/conftest.py` đặt đúng **một** khoá
giả mỗi provider và xoá sạch hậu tố. Test nào ĐO xoay khoá thì tự khai số khoá
nó cần ⇒ số khoá là **dữ liệu của test**, không phải của môi trường.

### 3.3 Một thay đổi hành vi, đã ghim bằng test

Thiếu khoá **chính** nhưng còn `_2` thì nay **vẫn chạy** (trước: chết ngay bất
kể có gì khác). Giữ hướng này — `keys_for` nghĩa là "mọi khoá dùng được" —
nhưng ghim bằng `test_thieu_khoa_CHINH_nhung_con_du_phong_thi_van_chay` để
không ai sửa ngược mà không biết. "Fail loud" cũ giữ nguyên cho ca **không khoá
nào**, kèm tên biến CHÍNH trong thông báo (thứ người ta đi đặt).

## 4. Nghiệm thu

**Test**: 1946 xanh (+13). Phép thử phá — tắt `_nen_xoay` ⇒ **4/7** test xoay
khoá đỏ; ba test còn lại xanh **đúng vai trò** (chúng khẳng định *không* xoay).

Một test riêng chứng minh khoá **thật sự đi xuống client**
(`google_api_key`/`openai_api_key`, hai tên trường khác nhau, đều `SecretStr`) —
không có nó thì mọi test xoay khoá đo bằng client giả đều có thể xanh giả.

**Sống, bằng ca THẬT chứ không dựng**: khoá cũ đã cạn ngày cho *cả hai* model
(probe trực tiếp: 429 `PerDay`). Dựng backend với **khoá cạn đặt ở vị trí #1**
và khoá còn hạn mức ở #2:

| quan sát | kết quả |
|---|---|
| model trả lời | `gemini-3.1-flash-lite` — **mắt xích ĐẦU**, không tụt |
| dòng báo tụt | **không có** (đúng: không có fallback chuỗi nào) |
| log | đúng **một** dòng `khoá #1 cạn hạn mức — xoay sang khoá #2` |
| hai lượt tiếp | vẫn `3.1-flash-lite`, **không** phát sinh dòng xoay mới |

Dòng cuối là phần chứng minh "nhớ khoá": không có nó thì mỗi lượt đều phải trả
giá một cú 429 cho cái ví đã biết là cạn.

## 5. Khó khăn / giới hạn còn lại

**Khó khăn**: ba phát sinh ở §3, trong đó §3.2 (test đọc `.env` thật) là thứ
duy nhất có thể làm cả nhóm test này thành trang trí trên máy khác.

**Giới hạn còn lại, chưa làm**

- **Sổ ngân sách vẫn mù với khoá** (§2.1). Sau bản này nó càng lệch xa hạn mức
  thật hơn. Chỉ nên sửa cùng lúc với việc quyết định `llm_usage` dùng để làm gì.
- **Mỗi lần chỉ số khoá đặt lại về 0, lượt kế phải trả một cú 429** cho khoá
  đầu nếu nó vẫn cạn (~0,4s với `MAX_RETRIES=0`). Chấp nhận: đó là cái giá để
  phát hiện cửa sổ trượt đã mở.
- **Chưa đo hành vi khi khoá SAI (401) chứ không phải cạn (429)**: hiện 401
  không xoay (đúng thiết kế — sai khoá thì khoá kế cũng chẳng liên quan), nhưng
  nó sẽ làm mắt xích đó cooldown như một lỗi thường. Chưa có ca thật để đo.
- Chỉ `google` có nhiều hơn một khoá. Cơ chế generic: thêm `GROQ_API_KEY_2` là
  chạy, không cần sửa code — nhưng **chưa ai thử**.
