# Cải thiện UX luồng xác nhận ghi ERP (write-confirmation)

**Ngày:** 2026-08-05
**Trạng thái:** design đã duyệt, chờ plan

## 1. Vấn đề

Phát hiện qua live-test thật (đoạn chat "individual workplace" — export JSON
Open WebUI, xác nhận qua đọc code + trace Langfuse): luồng đề xuất-rồi-xác
nhận hành động ghi (write) có 3 khoảng trống UX/độ tin cậy thật, cộng thêm 1
mong muốn cải thiện văn phong. Cả 4 quy về CÙNG một chủ đề — luồng xác nhận
ghi — nên gộp vào một plan.

### 1.1. Bug thật: câu trả lời ngắn gọn ("okay") không được hiểu là xác nhận

Kịch bản thật đã xảy ra:
1. User: "có 1 khách hàng sắp đặt 30 cái individual workplace, nhưng kho chỉ
   còn 16 cái, tôi muốn nhập 20 cái individual workplace" — có cả ngữ cảnh
   (đơn khách, tồn kho) LẪN ý định hành động.
2. `intent_router` phân loại câu này là `mixed` (xác nhận qua trace Langfuse
   thật: cùng ý định "muốn nhập" nhưng viết THUẦN không kèm ngữ cảnh → route
   đúng `erp_write` ngay; viết KÈM ngữ cảnh như trên → route `mixed`) — đi
   vào nhánh đọc (`gather_erp` → `fuse_answer`), không phải
   `erp_write_planner`.
3. Nhánh đọc hỏi lại "Bạn cần cho biết nhà cung cấp nào để mình tạo đơn."
   (không tra cứu trước — xem mục 1.2).
4. User hỏi "có các nhà cung cấp nào..." → nhánh đọc tra được, gợi ý luôn
   "Acme Corporation", hỏi thêm bằng **văn bản tự nhiên**: "Bạn có muốn tôi
   tiến hành tạo đơn mua 20 cái sản phẩm này từ nhà cung cấp Acme
   Corporation không?"
5. User trả lời "okay" — **KHÔNG được hiểu là xác nhận.** Agent trả lời
   chitchat chung chung ("Bạn đang cần giúp gì ạ?"), mất hẳn ngữ cảnh đề
   xuất vừa đưa ra. User phải gõ lại toàn bộ yêu cầu.

**Gốc rễ (xác nhận qua đọc `backend/src/agents/confirmation.py` +
`nodes.py:159-182`):** `classify_confirmation`/cơ chế resume CHỈ được gọi
khi graph đang ở trạng thái **parked thật** — tức đã có một lệnh gọi
`_interrupt()` thật từ `erp_write_planner` (`nodes.py:248`). Câu đề xuất ở
bước 4 chỉ là văn bản do LLM synthesis sinh ra trong lượt trả lời READ,
KHÔNG đi qua `_interrupt()` — nên không có gì để "resume" khi user trả lời
ngắn gọn ở bước 5. `ERPAgent.chat` (`erp_agent.py:159-213`) chỉ kiểm tra
`_is_parked(snapshot)` để quyết định có gọi `classify_confirmation` hay
không; không có nhánh nào xử lý "câu trả lời ngắn cho một đề xuất bằng lời
(không parked)".

### 1.2. Thiếu: không tự tra cứu khi thiếu đúng 1 thông tin bắt buộc

Ở bước 3 trên, agent hỏi thẳng "nhà cung cấp nào" mà KHÔNG tra cứu trước —
dù cùng công cụ đó, khi được hỏi trực tiếp ở bước 4, nó tra ra ngay và chỉ
có ĐÚNG 1 nhà cung cấp (Acme Corporation). Bắt user tự hỏi lại thay vì agent
chủ động tra là một vòng hỏi-đáp thừa.

### 1.3. Không có cơ chế chung — mỗi task một câu gợi ý riêng sẽ không nhất quán

Nếu sửa bằng cách thêm "câu gợi ý" thủ công cho từng loại task (mua hàng,
tra đơn, v.v.), sẽ (a) không đồng đều giữa các task, (b) nhân bản đúng bug ở
mục 1.1 ra nhiều chỗ hơn (càng nhiều nơi gợi ý bằng lời không có state thật
đứng sau, càng nhiều chỗ "okay" bị hiểu sai).

### 1.4. Câu xác nhận ghi còn thô, muốn tự nhiên hơn nhưng không được đổi số liệu

Ví dụ thật:
```
Đơn mua từ Acme Corporation:
  - [FURN_0789] Individual Workplace × 20
Xác nhận? (có / không)
```
Muốn câu chữ tự nhiên hơn, nhưng **số liệu ghi ERP (sản phẩm, số lượng, nhà
cung cấp, tool+args) tuyệt đối không được để LLM diễn giải lại** — đây là
tin nhắn an toàn (safety-critical): nếu LLM viết lại và lỡ đổi "20" thành
"khoảng 20" hay nhầm tên, user có thể xác nhận dựa trên bản xem trước SAI mà
không biết. Đây chính là bất biến "Invariant C tầng 3" đã ghi rõ trong
`nodes.py:240-241` — thiết kế mới phải giữ nguyên, không phải nới lỏng.

## 2. Quyết định kiến trúc

### 2.1. Sửa bug xác nhận (mục 1.1, 1.3) — tầng routing, KHÔNG trộn logic write vào read

Thêm một điều kiện tất định **mới** vào Lớp 2 (`decide_route`,
`routing.py:156-185`) — cùng tinh thần với điều kiện phủ quyết hiện có
(`looks_like_question`), độc lập với phân loại của LLM:

- **Điều kiện:** tin nhắn AI **ngay trước đó** (tìm bằng `m.type == "ai"`
  cuối cùng trong `state["messages"]`) kết thúc bằng mẫu câu hỏi có/không
  dạng xác nhận (marker mới, style giống `WRITE_CONFIRM_PREFIX`/"Xác nhận?
  (có / không)" đã dùng — KHÔNG trùng `_QUESTION_MARKERS` hiện có, vì đó là
  marker CÂU HỎI THÔNG THƯỜNG, còn marker mới đây là marker ĐỀ XUẤT HÀNH
  ĐỘNG cụ thể chờ có/không), **VÀ** tin nhắn user mới là một khẳng định
  ngắn gọn (tái dùng `_CONFIRM_WORDS`/`_match_any` đã có sẵn trong
  `confirmation.py` qua import — KHÔNG viết lại logic đoán từ).
- **Kết quả:** ép `decide_route` trả về `"erp_write"` bất kể
  `intent_router` đề xuất gì.
- **Vì sao an toàn:** `erp_write_planner` gọi `_plan_json(llm, system,
  state["messages"])` — đọc **TOÀN BỘ** lịch sử hội thoại, không chỉ tin
  nhắn cuối. Khi route tới đây, mọi thông tin cần (sản phẩm, số lượng, nhà
  cung cấp) đã có sẵn trong lịch sử → `_plan_json` tái dựng đúng plan → phát
  `_interrupt()` **thật**, đúng luồng xác nhận đã có, không cần cơ chế mới
  nào khác.
- **Rủi ro đã cân nhắc:** nếu câu hỏi có/không trước đó KHÔNG liên quan
  hành động ghi (vd RAG hỏi "bạn có muốn tôi tìm thêm tài liệu không?"), ép
  route sẽ khiến `_plan_json` không tìm được plan hợp lệ → rơi về nhánh có
  sẵn "Không thể xác định thao tác cần thực hiện. Vui lòng mô tả rõ hơn."
  (`nodes.py:218-220`). Không nguy hiểm (không tạo nhầm hành động, không
  hallucinate), chỉ hơi lệch UX ở ca hiếm gặp — chấp nhận được.
- **Vì sao tầng routing, không phải trộn write-plan vào nhánh đọc (đã cân
  nhắc và loại bỏ):** giữ tách bạch read/write đã được document kỹ trong
  `routing.py` (lịch sử hijack 2026-07-16 khi router LLM lẫn lộn 2 nhánh).
  Cách này KHÔNG đụng `gather_erp`/`fuse_answer` — chỉ thêm điều kiện tất
  định ở đúng nơi các điều kiện tất định khác đang sống.
- **Tự động tổng quát (mục 1.3):** vì nằm ở tầng routing chung, áp dụng cho
  MỌI task có `erp_write_planner` xử lý được — không cần sửa riêng từng
  prompt.

### 2.2. Auto-tra cứu khi thiếu đúng 1 lựa chọn (mục 1.2)

`erp_write_planner`/`_plan_json` là lệnh gọi LLM đơn thuần, KHÔNG có tool —
không thể tự tra cứu. Việc tra cứu chỉ có thể xảy ra ở nhánh CÓ tool thật —
`gather_erp`. Sửa bằng cách thêm hướng dẫn vào `GATHER_ERP_PROMPT`/
`FUSE_PROMPT` (prompts.py): khi câu hỏi user ngụ ý một hành động ghi còn
thiếu thông tin bắt buộc (vd nhà cung cấp) VÀ gather có tool tra cứu thông
tin đó — chủ động gọi tool tra trước khi hỏi lại; nếu tra ra ĐÚNG 1 kết quả,
nêu thẳng kết quả đó và đề nghị tiến hành (đây chính là câu đề xuất bằng
lời mà mục 2.1 sẽ bắt được nếu user trả lời ngắn gọn); nếu nhiều kết quả,
liệt kê để user chọn — có DỮ LIỆU THẬT thay vì hỏi suông. Hướng dẫn viết
**chung chung** (không riêng "nhà cung cấp"), tự nhiên phục vụ luôn mục
1.3.

### 2.3. Câu xác nhận tự nhiên hơn, template tĩnh (mục 1.4)

Sửa phần build `question` trong `erp_write_planner`
(`nodes.py:239-246`) — tách 2 phần:
- **Số liệu tất định** (`summary`, `plan.get('tool')`, `args_line`,
  `chain_note`) — GIỮ NGUYÊN Y HỆT, không đổi cách tính, không đổi vị trí
  trong câu (Invariant C tầng 3 phải còn nguyên vẹn, có test canh).
- **Khung câu chữ bao quanh** (`WRITE_CONFIRM_PREFIX` + format hiện tại) —
  đổi sang **template tĩnh viết sẵn trong code**, tự nhiên hơn, nhưng vẫn
  render qua f-string thường (không qua LLM). Không thêm lệnh gọi LLM mới
  nào cho việc này.

## 3. File bị chạm

| File | Thay đổi |
|---|---|
| `backend/src/agents/routing.py` | Thêm điều kiện tất định mới vào `decide_route` (mục 2.1); có thể cần thêm 1 marker set mới (câu hỏi xác nhận hành động) và import `_CONFIRM_WORDS`/`_match_any` từ `confirmation.py` |
| `backend/src/agents/prompts.py` | `GATHER_ERP_PROMPT`/`FUSE_PROMPT`: thêm hướng dẫn auto-tra cứu khi thiếu đúng 1 lựa chọn (mục 2.2); `WRITE_CONFIRM_PREFIX`/template câu hỏi xác nhận: đổi khung câu chữ (mục 2.3) |
| `backend/src/agents/nodes.py` | `erp_write_planner`: đổi cách build `question` (dùng template mới từ prompts.py), số liệu tất định giữ nguyên (mục 2.3) |
| `backend/tests/agents/test_routing.py` (hoặc file test routing hiện có) | Test mới cho điều kiện veto mới ở `decide_route` |
| `backend/tests/agents/test_prompts.py` | Test mới xác nhận `WRITE_CONFIRM_PREFIX`/template vẫn chứa placeholder cho số liệu tất định, không bị format cứng nhắc mất |

## 4. Không thuộc phạm vi (out of scope)

- Bug "nhập" bị hiểu nhầm thành `inventory_adjustment` thay vì
  `create_rfq`/mua hàng khi không có ngữ cảnh — phát hiện phụ trong lúc
  live-test mục 2.1's trace, KHÔNG sửa ở plan này (không liên quan luồng
  xác nhận, cần điều tra riêng).
- Bất khớp tên sản phẩm tiếng Việt/tiếng Anh (vd "bàn làm việc cá nhân" vs
  "Individual Workplace") khi tra cứu — phát hiện phụ khác, không thuộc
  phạm vi write-confirmation UX.
- 2 lớp xác nhận (xác nhận Ý ĐỊNH rồi xác nhận lại DÒNG ĐƠN cụ thể) — ĐÃ
  đánh giá là đúng mô hình 2 giai đoạn Odoo thật (RFQ nháp → Purchase Order
  xác nhận), không phải lỗi, không sửa.

## 5. Kiểm chứng

1. Unit test mới cho `decide_route`'s điều kiện veto mới (mock state với AI
   message kết thúc bằng câu hỏi xác nhận + human message ngắn gọn khẳng
   định → assert route = `erp_write`).
2. Unit test cho `WRITE_CONFIRM_PREFIX`/template: số liệu tất định
   (`args_line`, tool name) vẫn xuất hiện y hệt trong câu hỏi cuối.
3. `pytest -m "not integration and not live"` toàn bộ xanh, không hồi quy.
4. Live-verify thật (đã có Langfuse tracing — dùng để xác nhận đúng
   node/route mà không cần suy đoán): tái hiện đúng kịch bản gốc (câu hỏi
   kèm ngữ cảnh → mixed → gợi ý nhà cung cấp → "okay") và xác nhận lần này
   route đúng vào `erp_write_planner`, phát `_interrupt()` thật.

## 6. Tiêu chí hoàn thành

1. Cả 3 file (`routing.py`, `prompts.py`, `nodes.py`) đã sửa đúng theo mục
   2.1-2.3.
2. `pytest` unit-only xanh toàn bộ, không hồi quy.
3. Live-verify thật xác nhận kịch bản gốc ("okay" sau đề xuất bằng lời) giờ
   route đúng vào `erp_write_planner` và phát `_interrupt()` thật (dùng
   Langfuse trace làm bằng chứng, không suy đoán).
4. Câu hỏi xác nhận ghi vẫn giữ nguyên số liệu tất định (test canh +
   review thủ công), chỉ đổi khung câu chữ.
