# Người dùng chọn model, kèm báo khi tụt mắt xích

Ngày: 2026-08-21. Trạng thái: đã cài, 1902 test default + 52 integration xanh.

## 1. Vấn đề

Bảy vai, bảy chuỗi khác nhau, bốn mắt xích đầu khác nhau. Chủ dự án thấy việc
chia model theo "độ quan trọng của task" là rườm rà và làm hệ rời rạc, và muốn
**một model cho cả luồng, người dùng tự chọn** — giống chọn Opus/Sonnet.

Rà lại thì bảng gán cũ **phân bổ gần như ngược với lưu lượng**:

| model | rpd | vai |
|---|---|---|
| `gemini-3.5-flash` | **20** | `chitchat` |
| `gemini-3.1-flash-lite` | 500 | `router`, `synthesis`, `fusion` |
| `gemini-3.5-flash-lite` | 500 | `planner`, `read` |
| `gemma-4-26b` | **14 400** | `evaluator` |

Tán gẫu ăn model mạnh nhất **nhưng chỉ 20 lượt/ngày** — tức từ tin nhắn thứ 21
trở đi Groq trả lời, và **không ai từng biết** vì không có dòng báo nào. Còn
model dung lượng lớn nhất thì đậu trên vai chạy ít nhất.

## 2. Cài đặt — ba mảnh, cả ba đã có sẵn đường

**Chọn model**: `/v1/models` trước đây trả đúng MỘT mục và trường `model` trong
request **chưa ai đọc**. Liệt kê lựa chọn thật ở đó là toàn bộ phần giao diện —
**dropdown của Open WebUI đã có sẵn**, không dựng UI mới. Tên hiển thị là TÊN
MODEL THẬT, không phải nhãn "Nhanh / Chính xác": nhãn kiểu đó là lời hứa về kết
quả mà chưa ai đo, còn mục đích của việc cho chọn chính là để biết model nào
đang trả lời.

**`prefer`, KHÔNG phải `pin`**: Router đã có `pin` nhưng nó **bỏ qua toàn bộ
chuỗi**, thử một lần, không fallback (eval dùng để quy kết quả). `prefer` chỉ
ĐỔI THỨ TỰ — mắt xích đầu cũ **tụt xuống làm dự phòng**. Nhầm hai thứ này là mất
fallback mà không có gì báo. Có test khoá.

**Báo fallback**: `fallback_depth` trước đây chỉ đi vào Langfuse, chưa từng tới
người dùng.

## 3. Cái bẫy làm hỏng kế hoạch đầu, và cách vòng qua

Kế hoạch đầu là đọc `_QUYET_DINH` (ContextVar sẵn có) ở lớp bọc `erp_agent` sau
mỗi lượt. **Hỏng.** Chú thích trong `router.py` đã cảnh báo, và đo lại bằng
graph thật thì đúng: **giá trị `set()` bên trong một asyncio.Task KHÔNG lan
ngược về cha**. Node LangGraph chạy trong task con; cha đọc thấy `{}`.

Cách dùng được — cũng đã đo bằng graph thật: cha đặt sẵn một dict **khả biến**,
node **sửa tại chỗ**. Chiều xuôi thì ContextVar lan bình thường.

Mặc định của thùng là **None chứ không phải `{}`**: một dict mặc định dùng chung
mọi ngữ cảnh, sửa tại chỗ trên nó là rò rỉ giữa các request — đúng thứ chú thích
của `_QUYET_DINH` đang tránh.

Ghi tại `RoutedChatModel` — **chỗ nghẽn duy nhất** mọi lượt gọi LLM đi qua —
thay vì sửa từng node. Sửa từng node chính là lỗi "năm chỗ ghép, đếm nhầm thành
bốn" vừa xảy ra ở tính năng ký ức.

Dòng thông báo gắn **sau** `_apply_memory_markers` và **trước** `localize`: sau,
vì nó là văn bản cuối câu trả lời — đúng vùng `NGUỒN_DÙNG:` và `ĐỀ_XUẤT_GHI`
sống; trước, để người dùng tiếng Anh nhận nó bằng tiếng Anh.

## 4. Chọn model mặc định — và tôi đã đổi ý sau lượt lặp

Đo `read` / `planner` / `intent`, mỗi bộ 2 lượt:

| | intent acc | intent p95 | read | planner |
|---|---|---|---|---|
| `3.1-flash-lite` | **0,9444 · 0,9444** | 11 220 · 7 900ms | 1,0 | 1,0 |
| `3.5-flash-lite` | 0,9074 · 0,8889 | **1 058 · 1 073ms** | 1,0 | 1,0 |

`read`/`planner` **bão hoà** (cả hai 1,0) nên không phân biệt được — chỉ `intent`
còn dư địa.

**Lượt đầu tôi nghiêng 3.5** vì chênh acc trông như nhiễu. Lượt lặp cho thấy nó
ổn định: 3.1 giữ đúng 0,9444 cả hai lần, 3.5 dao động 0,89–0,91. Chênh 4-6 điểm
phần trăm, có thật.

**Chọn 3.1 dù CHẬM HƠN 7-10 lần ở đuôi**, vì hai kiểu hỏng không cùng hạng:
chậm là hỏng **lớn tiếng** (người dùng thấy, không nhận thông tin sai); định
tuyến nhầm là hỏng **im lặng** — câu `mixed` bị phân thành nguồn đơn nên thiếu
hẳn nửa tài liệu mà người dùng không biết là thiếu. Mặc định phục vụ người không
bao giờ đổi lựa chọn; với họ, thiếu âm thầm tệ hơn chậm.

Ai ưu tiên tốc độ thì đổi ở dropdown — **đó chính là lý do tính năng này tồn
tại**, và nó biến một đánh đổi bắt buộc thành một lựa chọn.

## 5. Giới hạn còn lại

- **Gộp về một model nghĩa là bảy vai chia CHUNG một ví 500 lượt/ngày**, thay vì
  ba ví như trước. Đổi lại chuỗi dự phòng nay giàu hơn (mắt xích đầu cũ tụt
  xuống làm dự phòng) nên suy giảm êm, và dòng báo cho người dùng biết.
- `gemma-4-26b` (rpd 14 400) là model DUY NHẤT đủ sức gánh cả hệ một mình.
  **Chưa đo** trên các vai này nên chưa cho chọn. Nếu hạn mức thành nút thắt,
  đây là ứng viên đáng đo trước tiên.
- `gemini-3.5-flash` (rpd 20) **cố ý không cho chọn** — làm dự phòng thì được.
- Chưa đo chuỗi thật sự tụt trên production (cần một model cạn hạn mức thật).

## 6. Bổ sung: chênh lệch acc giữa hai model phần lớn là do PROMPT, không do model

Ngày 2026-08-21, sau §4.

§4 chọn 3.1 làm mặc định vì nó hơn 3.5 khoảng 4-6 điểm phần trăm ở `intent`. Soi
ca trượt thì **mọi ca đều cùng một khuôn**: *"đối chiếu một bản ghi ERP với một
quy tắc trong tài liệu"* — trễ SLA chưa, có vi phạm SLA không, có khớp bảng giá
không, có dưới ngưỡng trong SOP không.

Prompt tả `mixed` bằng **đúng một ví dụ**, và nó là dạng **nêu chính sách ra
trước**: *"theo chính sách hoàn hàng, đơn của khách X có được hoàn không?"*.
Toàn bộ ca trượt là dạng **nhúng** — tên tài liệu nằm lẫn trong câu như một
thuộc tính. **Prompt dạy một hình thái, thực tế hỏng ở hình thái khác.**

**Bản vá**: thêm một quy tắc chung (không phải chép ca trượt vào làm ví dụ — làm
thế thì acc lên là đương nhiên và chứng minh được gì). Ví dụ dùng trong prompt
là một câu KHÁC cùng khuôn.

| bộ | model | trước | sau |
|---|---|---|---|
| `intent` | 3.1 | 0,9444 · 0,9444 | **0,9630 · 0,9630** |
| `intent` | 3.5 | 0,9074 · 0,8889 | **0,9630 · 0,9815** |
| `sop_select` | 3.1 | 0,9259 | **0,9630** |
| `sop_select` | 3.5 | 0,8889 | 0,8889 |
| `hijack` | cả hai | 0 | **0** |

Prompt dùng chung cho vai `intent` VÀ `sop_select` nên phải đo cả hai; `hijack`
là bất biến an toàn của router và nó giữ 0 ở cả bốn lượt.

Diacritics đã kiểm riêng: bản không dấu và bản có dấu cho cùng 0,9630 — bản đo
đầu dùng tiếng Việt không dấu do vướng heredoc, nên phải đo lại bản có dấu trước
khi áp, vì áp một văn bản khác bản đã đo là không đo gì cả.

### 6.1 Hệ quả: nên xét lại model mặc định

**Hai model nay HỘI TỤ** (3.1: 0,9630 · 0,9630; 3.5: 0,9630 · 0,9815). Khoảng
cách 4-6 điểm — căn cứ DUY NHẤT để §4 chọn 3.1 — **đã đóng**, và ở lượt thứ hai
3.5 còn nhỉnh hơn.

Nếu acc ngang nhau thì tiêu chí còn lại là độ trễ, và ở đó 3.5 nhanh hơn ~2 lần
ở trung vị (951ms vs 2000ms, đo bằng prompt router thật). Tức lập luận của §4
nay nghiêng về 3.5.

**CHƯA đổi mặc định.** Số của 3.5 sau vá là 0,9630 và 0,9815 — hai lượt chênh
nhau một ca, nên chưa chốt được nó ngang hay hơn. Cần thêm lượt lặp, và hạn mức
ngày của 3.5 đã cạn lúc đo (phải mượn khoá dự phòng). Đây là việc đáng làm khi
hạn mức reset.

### 6.1.1 CHỐT 2026-08-21: giữ 3.1

Chủ dự án quyết **giữ `gemini-3.1-flash-lite` làm mặc định**. Không cần đổi code
— hằng số `MODEL_MAC_DINH` đã là giá trị đó.

Ghi lại cho rõ, vì quyết định này đi **ngược chiều** số đo mới nhất và người đọc
sau sẽ vấp vào §6.1 rồi tưởng đây là nợ chưa đóng:

- Số sau vá cho thấy 3.5 **ngang**, không cho thấy nó **hơn**. Đổi mặc định cần
  bằng chứng nó hơn, không phải bằng chứng nó không kém — mặc định đang chạy có
  quyền được giữ khi hoà.
- Lập luận bất đối xứng của §4 **vẫn còn nguyên**: chậm là hỏng lớn tiếng, định
  tuyến nhầm là hỏng im lặng. Nó không phụ thuộc vào chênh lệch 4-6 điểm đã
  đóng, nên vá prompt không xoá được nó.
- Tốc độ nay là **lựa chọn chứ không phải đánh đổi bắt buộc** — ai cần thì đổi ở
  dropdown. Đó chính là thứ tính năng này sinh ra để giải quyết.

**Điều kiện mở lại**: có số cho thấy 3.5 acc **hơn** 3.1 ổn định qua nhiều lượt.
"Cần thêm lượt lặp" ở §6.1 **không còn là việc đang treo** — nó là điều kiện mở
lại, không phải hàng đợi.

### 6.2 Ca CHƯA chữa được

*"lệnh sản xuất mới có cần kiểm tra chất lượng theo SOP trước khi hoàn tất
không?"* → `rag` thay vì `mixed`, trượt ở **mọi model, mọi phiên bản prompt**.
Nó khác các ca kia: "lệnh sản xuất mới" chưa phải một bản ghi cụ thể, nên câu
này thật sự nằm ở ranh giới.

Và bản vá tạo ra **một ca trượt ngược chiều**: *"phiếu giao hàng nào đang trễ
hạn?"* → `mixed` trong khi kỳ vọng `erp_read`. Ròng vẫn dương, nhưng nó cho thấy
ranh giới `mixed`/`erp_read` mảnh — đừng siết thêm quy tắc mà không đo.

## 7. Nghiệm thu sống 2026-08-21 — dòng báo fallback ĐÃ chạy thật

Giới hạn cuối của §5 ("chưa đo chuỗi thật sự tụt trên production") **đã đóng**,
và đóng ngoài ý muốn: chủ dự án chọn `3.5-flash-lite`, hỏi *"xin chào bạn có thể
làm gì"*, và nhận đúng dòng:

    Lượt này do gemini-3.1-flash-lite, gemini-3.5-flash trả lời
    (model bạn chọn đang quá tải).

**Hai tên chứ không phải một, và đó là đúng.** Một lượt chat gọi LLM nhiều lần,
`THUNG_FALLBACK` gom theo LƯỢT chứ không theo lời gọi:

| vai | chuỗi khi `prefer=3.5-flash-lite` | ai thật sự trả lời |
|---|---|---|
| `router` | 3.5-flash-lite → **3.1-flash-lite** → groq → or-ling | 3.1-flash-lite |
| `chitchat` | 3.5-flash-lite → **3.5-flash** → groq | 3.5-flash |

Hai tên trong dòng báo khớp **chính xác** hai mắt xích này, nên nó vừa chứng
minh cơ chế chạy vừa chứng minh nó gom đúng phạm vi. Không cần dựng lại hạn mức
giả để đo.

### 7.1 Nhưng nó phơi ra một hố: `prefer` mở lại cái bẫy rpd=20

Comment ở `main.py` khoe rằng mặc định mới "tiện thể chữa luôn việc
`gemini-3.5-flash` (rpd=20) từng là mắt xích ĐẦU của chitchat". Đúng — **nhưng
chỉ với mặc định**. Chọn `3.5-flash-lite` thì chuỗi chitchat thành
`3.5-flash-lite → 3.5-flash → groq`, nên khi mắt xích đầu cạn ngày, tán gẫu rơi
thẳng vào đúng model rpd=20 mà §4 đã CỐ Ý không cho chọn. Nó chết sau ~20 lượt
rồi mới xuống Groq.

Không phải lỗi của `prefer` — `prefer` đúng thiết kế là chỉ đảo thứ tự. Lỗi là
chuỗi `chitchat` gốc vẫn còn `gemini-3.5-flash` ở vị trí mà mọi lựa chọn của
người dùng đều đẩy nó lên hàng hai.

### 7.2 Ba ô dropdown, hai hành vi

`erp-assistant` là `MODEL_ID`, không nằm trong `MODEL_CHON_DUOC`, nên rơi vào
nhánh `else MODEL_MAC_DINH` — tức **y hệt** chọn `gemini-3.1-flash-lite`, không
khác một mắt xích nào ở cả bảy vai. Ba ô nhưng chỉ hai hành vi.

### 7.3 Vì sao KHÔNG có dự phòng theo khoá API

`providers.ENV_KEYS` là ánh xạ **một upstream ↔ một biến môi trường**
(`google → GOOGLE_API_KEY`). Không có vòng xoay khoá ở bất kỳ tầng nào. Hạn mức
Gemini free tier tính **theo project**, nên một khoá project khác là một ví
KHÁC — nhưng hệ hiện không biết điều đó, và cạn ngày của một khoá là cạn cho cả
bảy vai.

Đây là **nợ có thật, chưa mở phạm vi** — xem `docs/trang-thai-chung.md` mục 7.
Lưu ý khi thiết kế: thêm khoá thứ hai KHÔNG được làm thành mắt xích thứ hai của
chuỗi, vì bất biến #1 của router (không hai mắt xích cùng upstream) tồn tại để
chặn đúng chuyện rơi từ miền lỗi này sang lại chính nó. Chỗ đúng là **xoay khoá
bên trong một mắt xích**, trước khi tụt xuống mắt xích sau.

## 8. Bản sửa 2026-08-21 (đợt hai): đóng hố rpd=20 và bỏ ô dropdown giả

### 8.1 Chuỗi `chitchat` — `gemini-3.5-flash` → `gemini-3.5-flash-lite`

Đóng §7.1. Số đo bộ `chitchat` 2026-08-13 giữ nguyên giá trị tham khảo, không
lượt nào bị bác — thứ SAI là **lập luận**, không phải số: "rpd=20 chấp nhận được
ở đây vì chitchat rất thưa" chết kể từ khi `prefer` ra đời, mà không ai sửa lại.

`gemini-3.5-flash-lite` KHÔNG cần đo lại trên bộ này: nó đã chạy vai `chitchat`
ở **vị trí 1** mỗi lượt người dùng chọn nó ở dropdown. Đưa xuống vị trí 2 là
phơi nhiễm nghiêm ngặt ÍT hơn thứ production đang làm.

Entry `gemini-3.5-flash` **giữ lại** trong `CATALOG` (khác `gemma-4-31b` bị xoá
hẳn): nó vẫn cần cho `--model gemini-3.5-flash` lúc ghim đo, và bất biến #5 làm
việc giữ nó thành an toàn.

### 8.2 Bất biến #5 — hai mắt xích đầu phải đủ gánh một ngày

`RPD_SAN_PHUC_VU = 500`. Kiểm với `prefer=None` LẪN từng model trong dropdown,
vì chỉ kiểm bảng `CHAINS` tĩnh là mù đúng với đường người dùng thật đi. Mắt xích
cuối (`or-ling`/`or-nemotron`, rpd 50) được miễn — lưới đỡ khẩn cấp, cố ý mỏng.

**Đã thử phá bằng cách khôi phục đúng cấu hình cũ**: 2 test đỏ, khôi phục thì
xanh. Một test tự-mô-phỏng tôi viết lúc đầu đã **bị gỡ** — nó tự dựng lấy cấu
hình hỏng nên xanh ở cả hai lượt, tức không chạm vào luật thật.

### 8.3 Dropdown còn hai ô; trường `model` mang tên model THẬT

`/v1/models` không còn quảng cáo `MODEL_ID`. Client cũ không gãy: nhánh "tên lạ
→ `MODEL_MAC_DINH`" vẫn nhận `erp-assistant` (harness `live_verify_common.py`
gửi đúng tên đó). Đọc mã Open WebUI đang chạy trong container để xác nhận chứ
không đoán: `utils/models.py:158`, model tuỳ biến có `base_model_id=None` được
tra ngược lên danh sách backend; không thấy thì **bỏ qua hoàn toàn**.

`THUNG_MODEL` (thùng thứ hai, cạnh `THUNG_FALLBACK`) ghi **mọi** lượt chứ không
chỉ lúc tụt — nếu nó cũng lọc theo `fallback_depth` thì trường `model` sẽ đúng
ĐÚNG lúc có sự cố và sai mọi lúc bình thường. `catalog.VAI_TRA_LOI` chọn vai
SINH câu trả lời theo ưu tiên (`fusion > synthesis > read > chitchat`), không
lấy "lời gọi LLM cuối cùng" — lấy thế sẽ trúng `evaluator` (localize), thứ chỉ
dịch lại văn bản đã có.

**Cả hai chỗ này trước đó KHÔNG có test nào gác**: sửa xong toàn bộ 1902 test
vẫn xanh. Đã bổ sung 4 test ở `tests/test_main.py`, tất cả đã chứng minh đỏ khi
quay về hành vi cũ.

### 8.4 Nghiệm thu sống

Backend phụ cổng 8012 (không đụng 8002) rồi khởi động lại 8002 bằng code mới.

| lượt | model trả về | dòng báo tụt |
|---|---|---|
| chọn 3.1, câu chào | `gemini-3.1-flash-lite` | không |
| chọn `erp-assistant` (tên cũ) | `gemini-3.1-flash-lite` | không |
| chọn 3.5 (đã cạn ngày), câu chào | `groq-gpt-oss-20b` | 3.1-flash-lite, groq |
| chọn 3.1, hỏi tồn kho | `gemini-3.1-flash-lite` | không |

Lượt thứ ba là bằng chứng hố rpd=20 đã đóng trên đường thật: trước bản sửa nó
rơi vào `gemini-3.5-flash`, nay đi thẳng xuống Groq.

### 8.5 Khó khăn / giới hạn còn lại

- **Bẫy công cụ**: ghi đè `MCP_ODOO_URL` thành `/mcp` (đúng là `/sse`) làm
  backend phụ chết lúc startup; và `stdout` cp1252 nuốt chẩn đoán cho tới khi
  đặt `PYTHONIOENCODING=utf-8`. Cùng hai bẫy đã ghi ở các đợt trước.
- **`start-dev.ps1` KHÔNG dùng được để khởi động lại từ agent**: nó chạy vòng
  canh vô hạn và `finally` của nó **giết chính backend vừa khởi động**. Phải
  lặp lại khối backend bằng tay.
- ⚠️ **GIỚI HẠN MỚI, CHƯA SỬA — chọn 3.5 cho chuỗi NGẮN HƠN chọn 3.1.**
  `prefer` chỉ CHÈN LÊN ĐẦU, nên khi model được chọn vốn đã là mắt xích 1 thì
  nó không thêm gì:

      read, prefer=3.1 → 3.1-lite, 3.5-lite, groq-llama, or-nemotron   (4)
      read, prefer=3.5 → 3.5-lite, groq-llama, or-nemotron             (3)

  Người chọn 3.5 **không có** mắt xích Gemini thứ hai. Gặp thật trong nghiệm
  thu: hỏi tồn kho khi chọn 3.5 → `ChainExhausted` (3.5-lite cạn ngày,
  groq-llama và or-nemotron hỏng tại chỗ) trong khi 3.1-lite vẫn còn hạn mức
  nhưng **không nằm trong chuỗi**. Cùng câu hỏi với 3.1 trả lời đúng.
  Hướng khả dĩ: `chain_for` bảo đảm MỌI model trong `MODEL_CHON_DUOC` đều có
  mặt sau mắt xích đầu. Chưa làm — thuộc phạm vi mới.
