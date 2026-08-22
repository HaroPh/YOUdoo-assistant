# Gom catalog: 9 model → 4, một hình dạng chuỗi cho mọi vai

**Ngày**: 2026-08-21 · Đóng **mục 6, 8, 10** trên `docs/trang-thai-chung.md`.

## 1. Vì sao đợt này tồn tại

Ba mục riêng lẻ hoá ra là **một** vấn đề. Rà mục 10 thì phát hiện bảng model đã
**mục ruỗng**:

| model | trạng thái đo được 2026-08-21 |
|---|---|
| `groq-llama-3.3-70b` | **CHẾT** — Groq trả *"model does not exist"* |
| `or-ling` | **CHẾT** — OpenRouter gỡ slug `:free`, chỉ còn bản trả tiền |
| `or-nemotron` | sống (mục 10 của tôi ghi SAI, xem §5) |

Hai model chết đó là mắt xích của 4/7 vai. Bức tranh thật:

    router     2/3      fusion     1/2   *** CÒN MỘT MẮT XÍCH ***
    read       2/3      synthesis  2/3

`fusion` — vai hợp nhất câu trả lời nhánh `mixed` — **chỉ còn một model**. Cạn
nó là hỏng hẳn. Tình trạng này **có sẵn từ trước**, không do đợt nào hôm nay.

## 2. Quyết định của chủ dự án

Sau khi có xoay khoá (3 khoá = 3 ví), chủ dự án chốt: **dồn về Gemini**, giữ
**một** model Groq làm đường thoát khỏi Google, và **dùng một model cho mọi
task** như đã làm với dropdown — để dễ đo.

Lý do quan trọng nhất được nêu và **đo được**: hạn mức cạn hôm nay là do **tôi
chạy nghiệm thu**, không phải do tải thật (~40 lượt/ngày thật, một job e2e bắn
vài chục lượt).

### 2.1 Chỗ tôi không đồng ý, và đã nói một lần

Ba khoá chữa **hạn mức**, không chữa **sự cố nhà cung cấp** — chúng là ba ví
trên cùng một hệ thống Google. Bất biến #1 sinh ra cho kiểu hỏng thứ hai. Vì
vậy giữ lại đúng một model Groq, thay vì thuần Gemini.

Ngược lại, hai bằng chứng ủng hộ việc rút gọn: Groq và OpenRouter **mỗi bên âm
thầm khai tử một model**, chỉ lộ ra vì tình cờ chạy một test `live`; và
OpenRouter free là **~50 lượt/ngày dùng chung cho mọi model** — chưa bao giờ là
dung lượng thật.

## 3. Hình dạng mới

    mọi vai:  [model người dùng chọn] → [Gemini còn lại] → groq-gpt-oss-120b

Catalog **9 → 4**: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`,
`groq-gpt-oss-120b`, và `gemini-3.5-flash` (giữ để `--model` ghim đo, không vào
chuỗi nào — bất biến #5 chặn nó quay lại).

Bị xoá: `gemma-4-26b`, `groq-gpt-oss-20b`, `groq-llama-3.3-70b`, `or-ling`,
`or-nemotron`.

### 3.1 Mắt xích thứ hai đến từ đâu (mục 8)

`chain_for(prefer=…)` trước đây **chỉ chèn lên đầu**, nên model vốn đứng đầu thì
không thêm gì — người chọn 3.5 có chuỗi **ngắn hơn** người chọn 3.1. Nay nó bảo
đảm **mọi model trong `MODEL_CHON_DUOC` đều có mặt** ngay sau mắt xích đầu. Đây
chính là thứ đưa `fusion` từ 1 mắt xích lên 2 (× 3 khoá = 6 ví).

## 4. Số đo quyết định việc bỏ `gemma-4-26b`

Gemma ở chuỗi vì **một** phép đo 2026-08-13 trên bộ `confirm` (cổng xác nhận
ghi). Đo lại đối đầu, **cùng phiên, cùng prompt**, mỗi model 2 lượt:

| model | acc (2 lượt) | false_confirm | p50 |
|---|---|---|---|
| `gemma-4-26b` | 0,7917 · 0,7917 | 0 | 6 062 ms |
| `groq-gpt-oss-120b` | **0,8333 · 0,8333** | 0 | **611 ms** |

Cả hai **tất định** qua các lượt lặp; gemma trùng khít số 2026-08-13, nên
baseline cũ **không** lỗi thời.

**Nói cho chính xác**: chênh lệch acc là **đúng một ca** (20/24 vs 19/24) — trên
n=24 tôi KHÔNG kết luận 120b đúng hơn, chỉ kết luận nó **không kém**. Thứ dứt
khoát là **độ trễ nhanh gấp 10**.

Hai lý do phụ, đều là dằm vận hành của gemma mà 120b không có: nó nhả thẻ
`<thought>` vào content, và có bề mặt *"cạn ngân sách token suy luận"* — chính
cái đã khiến nó **trả rỗng thật** và buộc đợt `router-empty-response` dựng cả
một lưới đỡ.

Lý lẽ "ví lớn" (rpd 14 400) không cứu được nó: chú thích trong chính catalog ghi
rằng đường LLM của cổng này **hiếm khi chạy**. Ví lớn đặt đúng chỗ ít dùng nhất.

⇒ **Mục 6 đóng bằng số đo**, không phải bằng cách treo tiếp.

## 5. Mục 10 tôi ghi SAI — đính chính

Tôi ghi *"`or-nemotron` chết, 16 lần gọi 0 thành công"*. Sai hai lớp:

- **16** là số dòng **nhắc tên** nó trong log, gồm cả dòng `ChainExhausted` liệt
  kê `or-nemotron=cooldown`. Số lần hỏng thật là **4**.
- **"0 thành công"** đọc từ `llm_usage` — cái sổ vừa bị bộ test tích hợp xoá
  sạch (mục 9). Probe trực tiếp: `or-nemotron` **trả lời bình thường**.

Model chết thật là `or-ling` và `groq-llama-3.3-70b`, và cả hai được tìm ra bởi
`test_moi_model_id_trong_catalog_van_con_ton_tai` — rào **đã có sẵn**, đánh dấu
`live` nên không chạy ở chế độ mặc định.

Log gốc nay **không tra lại được**: tôi đã ghi đè nó khi khởi động lại backend
(`-RedirectStandardError` cắt tệp). Đó là bài học riêng — **đừng phá bằng chứng
trước khi kết luận xong**.

## 6. Hạ `HEAVY_TPM_FLOOR` 12 000 → 8 000

`groq-gpt-oss-120b` có tpm 8 000, nên giữ ngưỡng thì ba vai nặng **không có**
mắt xích Groq — ngược hẳn lý do giữ sợi Groq.

Ngưỡng 12 000 được đặt **theo cái `llama-3.3-70b` sẵn có**, không theo nhu cầu:
chú thích gốc ghi *"một lượt synthesis có RAG tốn ~3–4K token input, và 12K là
mức của llama-3.3-70b — mắt xích Groq duy nhất gánh nổi vai nặng"*. Model đó
biến mất thì ngưỡng không còn bảo vệ gì, chỉ còn **cấm mọi ứng viên tồn tại**.

Ngưỡng bảo vệ **thông lượng**, không bảo vệ **tính đúng**: ở 8 000 tpm một lượt
nặng ~3–4K vẫn chạy lọt, chỉ còn ~2 lượt/phút thay vì ~3 — cho một mắt xích
**chỉ chạy khi cả hai Gemini đã ngã**.

## 7. Một giả thuyết tôi dựng rồi tự bác

Lượt đo 120b đầu tiên chết vì 429 với `Requested 4366`/lượt, rất gần
`max_output_tokens=4096`. Tôi dựng giả thuyết *"Groq tính cả `max_tokens` dự trữ
vào TPM"* — nếu đúng thì chính ưu điểm tôi vừa khen (đầu ra gấp đôi 20b) lại là
nhược điểm chí mạng.

**Đo thì bác**: 6 lượt liên tiếp `max_tokens=16` mỗi lượt tốn ~200 token, và một
lượt `max_tokens=4096` cũng chỉ tốn ~196. Không có dự trữ.

Con số `Requested 4363` **vẫn chưa giải thích được**. Nghi ngờ hợp lý nhất: bộ
eval bắn 24 ca **đồng thời** và bộ đếm của Groq cộng dồn lượt đang bay — nhưng
đó là **phỏng đoán chưa đo**, ghi lại đúng như vậy. Chạy với `--pace 1.0` thì
sạch hoàn toàn.

Điều đáng giữ: một lượt `confirm` thật tốn **~200–280 token**, tức 8 000 tpm cho
~28–40 lượt/phút. Lo ngại *"8 000 tpm quá chật"* mà tôi nêu lúc đầu **không có
cơ sở ở vai nhẹ**.

## 8. Nghiệm thu

**Test**: 1944 mặc định + 52 tích hợp xanh. Rào sống
`test_moi_model_id_trong_catalog_van_con_ton_tai` xanh cả ba provider — mọi
model còn lại đều TỒN TẠI THẬT (chính rào này bắt ra hai model chết).

**Sống**, backend chạy catalog mới, cả ba nhánh định tuyến:

| chọn | hỏi | model trả về | dòng báo tụt |
|---|---|---|---|
| 3.1 | "xin chào" (`chitchat`) | `gemini-3.1-flash-lite` | không |
| 3.5 | tồn kho (`erp_read`) | `gemini-3.5-flash-lite` | không |
| 3.1 | quy trình nhập kho (`rag`) | `gemini-3.1-flash-lite` | không |

Câu tồn kho trả đúng số Odoo thật (73 tại WH/Tồn kho).

### 8.1 Cái giá phải trả: 18 tệp test, và BA test mất sức phân biệt

Gom catalog làm **56 test đỏ**. Phần lớn cơ học, nhưng ba ca đáng ghi vì chúng
đều thuộc lớp *"test vẫn xanh nhưng không còn đo gì"*:

1. `test_last_decision_khong_ro_ri_giua_hai_vai` — dùng hai vai để chứng minh
   `last_decision` không rò rỉ. Mọi vai nay chung một chuỗi ⇒ hai vai ra CÙNG
   model. **Rào tự dựng sáng cùng ngày đã bắt được**: khẳng định
   `alias != alias` đỏ ngay. Sửa bằng cách `pin` một vai. Rào đó **đã đỏ thật
   hai lần trong một ngày** — lần đầu khi chuỗi `chitchat` đổi, lần này khi gom.
2. `test_nhip_tu_dong_suy_tu_rpm_catalog` — hai dòng vốn dùng hai `rpm` khác
   nhau, nay bằng nhau. Sửa bằng cách **suy kỳ vọng từ catalog** thay vì ghim
   hằng số, để nó đo CÔNG THỨC chứ không đo một con số.
3. `test_client_google_dung_model_id_goc` — cả 4 model còn lại đều có
   `model_id == alias`, nên test "phải gửi model_id GỐC" không phân biệt được
   gì. Sửa bằng **spec tổng hợp** có `model_id ≠ alias`.

Cùng lý do, hai chỗ khác dùng spec tổng hợp thay vì lấy từ catalog:
`quota_scope="account"` (không model nào còn dùng) và provider `openrouter`
(nhánh code vẫn còn và vẫn phải đúng).

### 8.2 Hai bất biến nay RỖNG CHỦ THỂ

`test_khong_co_model_openrouter_nao_co_upstream_google` và
`test_openrouter_dung_quota_scope_account` lặp trên **tập rỗng** — xanh vì
không có gì để kiểm. Thêm `test_ba_bat_bien_duoi_day_HIEN_RONG_CHU_THE` để
không ai đọc nhầm màu xanh của chúng; nó **tự hết hạn**: đỏ ngay khi có model
OpenRouter hoặc model nhả `<thought>` quay lại.

## 9. Khó khăn / giới hạn còn lại

**Khó khăn thật sự gặp**

- Đề bài phình từ "sửa mục 10" thành "gom cả catalog" vì phép đo đầu tiên
  **bác luôn mục 10** như tôi đã ghi nó.
- 18 tệp test phải sửa; ba trong số đó nếu sửa cẩu thả sẽ **xanh mà không đo
  gì** — xem §8.1.
- Giữa đợt máy khởi động lại: ba tiến trình MCP (:8003/:8004/:8005) là tiến
  trình HOST nên không tự dậy cùng Docker, phải bật tay trước khi backend lên.

**Hướng đã chọn**

- Suy kỳ vọng **từ catalog** thay vì ghim hằng số, ở mọi chỗ sửa được.
- Dùng **spec tổng hợp** cho các nhánh code còn sống nhưng không còn chủ thể
  trong catalog, thay vì xoá test.

**Giới hạn còn lại**

- `groq-gpt-oss-120b` **chưa được đo trên vai nào ngoài `confirm`**. Nó vào
  chuỗi với tư cách mắt xích CUỐI nên rủi ro thấp, nhưng đừng nói nó "đã đo".
- Ba vai nặng nay chỉ có **một** mắt xích ngoài Google, và nó ở tpm 8 000.
- `emits_thought_tags` + `strip_thought` là **cấu hình không còn chủ thể**;
  giữ lại có chủ đích, có test spec-tổng-hợp phủ.
- Sổ `llm_usage` vẫn mù với khoá (mục 9 bảng chung) — càng lệch hơn sau khi có
  xoay khoá.
