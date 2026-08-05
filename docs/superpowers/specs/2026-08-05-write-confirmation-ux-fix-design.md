# Cải thiện UX luồng xác nhận ghi ERP (write-confirmation)

**Ngày:** 2026-08-05
**Trạng thái:** design đã duyệt, chờ plan
**Tính chất quyết định:** TẠM THỜI, có cổng đánh giá thật (xem §7). Người dùng
đã nêu rõ: "chưa chắc với quyết định này, nhưng nếu cài đặt và test có tín hiệu
tốt thì giữ." Nghĩa là thiết kế §2.1 KHÔNG mặc định được giữ — nó phải qua
được §7 mới ở lại.

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
   (không tra cứu trước — xem §1.2).
4. User hỏi "có các nhà cung cấp nào..." → nhánh đọc tra được, gợi ý luôn
   "Acme Corporation", hỏi thêm bằng **văn bản tự nhiên**: "Bạn có muốn tôi
   tiến hành tạo đơn mua 20 cái sản phẩm này từ nhà cung cấp Acme
   Corporation không?"
5. User trả lời "okay" — **KHÔNG được hiểu là xác nhận.** Agent trả lời
   chitchat chung chung ("Bạn đang cần giúp gì ạ?"), mất hẳn ngữ cảnh đề
   xuất vừa đưa ra. User phải gõ lại toàn bộ yêu cầu.

**Gốc rễ (xác nhận qua đọc `backend/src/agents/confirmation.py` +
`erp_agent.py:159-213`):** `classify_confirmation`/cơ chế resume CHỈ được gọi
khi graph đang ở trạng thái **parked thật** — tức đã có một lệnh gọi
`_interrupt()` thật từ `erp_write_planner` (`nodes.py:248`). Câu đề xuất ở
bước 4 chỉ là văn bản do LLM `fuse_answer` sinh ra trong lượt trả lời READ,
KHÔNG đi qua `_interrupt()` — nên không có gì để "resume" khi user trả lời
ngắn gọn ở bước 5. `ERPAgent.chat` chỉ kiểm tra `_is_parked(snapshot)` để
quyết định có gọi `classify_confirmation` hay không; không có nhánh nào xử lý
"câu trả lời ngắn cho một đề xuất bằng lời (không parked)".

### 1.2. Thiếu: không tự tra cứu khi thiếu đúng 1 thông tin bắt buộc

Ở bước 3 trên, agent hỏi thẳng "nhà cung cấp nào" mà KHÔNG tra cứu trước —
dù cùng công cụ đó, khi được hỏi trực tiếp ở bước 4, nó tra ra ngay và chỉ
có ĐÚNG 1 nhà cung cấp (Acme Corporation). Bắt user tự hỏi lại thay vì agent
chủ động tra là một vòng hỏi-đáp thừa.

### 1.3. Không có cơ chế chung — mỗi task một câu gợi ý riêng sẽ không nhất quán

Nếu sửa bằng cách thêm "câu gợi ý" thủ công cho từng loại task (mua hàng,
tra đơn, v.v.), sẽ (a) không đồng đều giữa các task, (b) nhân bản đúng bug ở
§1.1 ra nhiều chỗ hơn (càng nhiều nơi gợi ý bằng lời không có state thật
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

### 2.1. Sửa bug xác nhận (§1.1, §1.3) — marker + metadata trên message, KHÔNG ép format văn bản

**Phương án đã cân nhắc và LOẠI BỎ** (ghi lại để đời sau không làm lại):

- *Trộn logic write vào nhánh đọc* (`fuse_answer` tự gọi plan + `_interrupt()`):
  phá tách bạch read/write đã document kỹ trong `routing.py` (lịch sử hijack
  2026-07-16 khi router LLM lẫn lộn 2 nhánh). Loại.
- *`decide_route` match VĂN BẢN câu hỏi có/không*: mâu thuẫn không giải được.
  Câu gây bug thật ("...từ nhà cung cấp Acme Corporation **không?**") KHÔNG có
  format "(có / không)" tường minh; nếu marker chặt thì không bắt được chính
  bug đang sửa, còn nếu marker lỏng (mọi câu kết thúc "...không?") thì MỌI câu
  hỏi chitchat/RAG bình thường ("Bạn có muốn tôi giải thích thêm không?") theo
  sau bởi "ok" đều bị ép sai sang `erp_write_planner` — hồi quy diện rộng, khả
  năng gặp cao hơn hẳn ca gốc. Loại.
- *Ép `fuse_answer` luôn kết thúc bằng đúng format "(có / không)"*: giải được
  mâu thuẫn trên nhưng làm câu trả lời đọc/tra cứu nghe máy móc, lệch tông
  "tự nhiên, ấm áp" đang có. Loại.

**Phương án chọn — marker trailer + `additional_kwargs`, đi theo pattern
`NGUỒN_DÙNG` đã có sẵn trong chính codebase này:**

1. `FUSE_PROMPT` được thêm chỉ dẫn: khi câu trả lời ĐANG đề xuất một hành
   động ghi cụ thể, thêm một dòng CUỐI CÙNG dạng `ĐỀ_XUẤT_GHI: có`. Phần văn
   bản user đọc **giữ nguyên tự do, tự nhiên** — không bị ép khuôn gì cả.
   Marker cố ý là **cờ boolean, KHÔNG kèm tên tool**: `fuse_answer` không có
   danh sách 29 tool ghi trong prompt của nó (đó là của
   `WRITE_PLANNER_PROMPT`), bắt nó đoán tên tool chính xác là mời thêm một
   nguồn sai. Việc xác định tool thật vẫn thuộc về `_plan_json` của
   `erp_write_planner` — nơi CÓ danh sách tool đầy đủ.
2. `fuse_answer` parse dòng marker đó rồi **CẮT BỎ trước khi hiển thị** —
   đúng cơ chế `extract_used_citations()` (`synthesis.py:52-65`) đang làm với
   `NGUỒN_DÙNG`. User không bao giờ thấy marker. Tín hiệu được gắn vào chính
   `AIMessage` qua `additional_kwargs={"suggested_write": True}`.
3. `decide_route` (routing.py, Lớp 2 tất định) thêm điều kiện: tin nhắn AI
   **cuối cùng** trong `state["messages"]` có
   `additional_kwargs["suggested_write"]`, **VÀ** tin nhắn user mới là khẳng
   định ngắn gọn (tái dùng `_CONFIRM_WORDS`/`_match_any` đã có sẵn trong
   `confirmation.py` qua import — KHÔNG viết lại logic đoán từ) → ép trả về
   `"erp_write"`.
4. `erp_write_planner` gọi `_plan_json(llm, system, state["messages"])` — đọc
   **TOÀN BỘ** lịch sử hội thoại, nên mọi thông tin cần (sản phẩm, số lượng,
   nhà cung cấp) đã có sẵn → tái dựng đúng plan → phát `_interrupt()` **thật**,
   đúng luồng xác nhận đã có. **Không cần cơ chế xác nhận mới nào.**

**Vì sao gắn vào MESSAGE chứ không phải một state key riêng** (đây là điểm
kỹ thuật quan trọng, không phải tuỳ ý): `intent_router` chạy TRƯỚC
`decide_route`. Nếu cờ nằm ở state key riêng thì hoặc `intent_router` xoá nó
(theo pattern `sop`) và `decide_route` không bao giờ đọc được, hoặc không ai
xoá và cờ sống dai sang các lượt sau gây kích hoạt sai. Gắn vào chính
`AIMessage` làm tín hiệu **tự giới hạn phạm vi**: nó thuộc về đúng message
đó, `decide_route` luôn đọc AI message MỚI NHẤT nên một câu trả lời mới không
mang cờ tự động vô hiệu hoá cờ cũ — không cần kỷ luật dọn dẹp trải khắp các
node (đúng thứ mà `state.py` cảnh báo là mong manh).

**Đã kiểm chứng THẬT (không suy đoán):** `state.py` ghi rõ bài học SP-1C2 —
có loại lỗi CHỈ hỏng khi checkpointer Postgres thật chạy, unit test mock bỏ
lọt hoàn toàn. Nên đã chạy probe thật (graph tối giản + `AsyncPostgresSaver`
+ Postgres thật ở cổng 5434, ghi rồi ĐỌC LẠI qua `aget_state`):
`additional_kwargs` **sống sót nguyên vẹn** qua vòng lưu/đọc checkpoint (probe
dùng payload chuỗi; giá trị thật `True` là boolean — cùng loại JSON thuần, an
toàn tương đương). Dù vậy plan VẪN phải có integration test (`-m integration`)
chốt lại điều này trong repo bằng ĐÚNG payload thật — probe là bằng chứng cho
quyết định thiết kế, test là lưới chống hồi quy.

**Vì sao cách này không dính rủi ro của phương án match-văn-bản:** chitchat và
RAG **không bao giờ** phát marker `ĐỀ_XUẤT_GHI` (chỉ `FUSE_PROMPT`/
`SYSTEM_PROMPT` được thêm chỉ dẫn này, và chỉ khi thật sự đề xuất hành động
ghi) → câu hỏi thường ngày kiểu "Bạn có muốn tôi giải thích thêm không?" +
"ok" KHÔNG kích hoạt ép route.

**Rủi ro còn lại đã cân nhắc:** nếu LLM phát marker sai (đề xuất ghi nhưng
thật ra không có hành động ghi khả thi), `_plan_json` không tìm được plan hợp
lệ → rơi về nhánh có sẵn "Không thể xác định thao tác cần thực hiện. Vui lòng
mô tả rõ hơn." (`nodes.py:218-220`). Không nguy hiểm (không tạo nhầm hành
động, không hallucinate số liệu), chỉ lệch UX ở ca hiếm.

**Tổng quát hoá (§1.3):** cơ chế nằm ở tầng routing chung nên áp dụng cho MỌI
node biết phát marker. Plan này nối dây vào **`fuse_answer`** (nơi bug thật
đã quan sát được) và **`erp_read`** (node trả lời user-facing còn lại trên
đường đọc), dùng CHUNG một helper parse/gắn cờ — không phải hai bản sao. Thêm
node khác về sau là đổi một dòng.

### 2.2. Auto-tra cứu khi thiếu đúng 1 lựa chọn (§1.2)

`erp_write_planner`/`_plan_json` là lệnh gọi LLM đơn thuần, KHÔNG có tool —
không thể tự tra cứu. Việc tra cứu chỉ có thể xảy ra ở nhánh CÓ tool thật —
`gather_erp`. Thêm hướng dẫn vào `GATHER_ERP_PROMPT`: khi câu hỏi user ngụ ý
một hành động ghi còn thiếu thông tin bắt buộc VÀ có tool tra cứu được thông
tin đó — chủ động gọi tool tra TRƯỚC khi hỏi lại. `FUSE_PROMPT` được hướng
dẫn: nếu dữ kiện cho thấy ĐÚNG 1 lựa chọn khả dĩ, nêu thẳng lựa chọn đó và đề
nghị tiến hành (kèm marker `ĐỀ_XUẤT_GHI` ở §2.1); nếu NHIỀU lựa chọn, liệt kê
để user chọn (giữ hành vi hỏi lại, nhưng có DỮ LIỆU THẬT thay vì hỏi suông).
Hướng dẫn viết **chung chung** (không riêng "nhà cung cấp").

**Rủi ro đã biết:** đây đúng vùng `gather_erp` tool-selection đã gây bug thật
ở nhiều plan trước (chọn sai tool, chọn đúng tool nhưng sai tham số — xem
`youdoo-gather-erp-tool-fix-status`, `youdoo-gather-cases-product-price-fix-status`
trong bộ nhớ dự án). Mở rộng phán đoán của cơ chế này cần live-test thật
nhiều ca, không chỉ unit test — đã đưa vào §7.

### 2.3. Câu xác nhận tự nhiên hơn, template tĩnh (§1.4)

**Đính chính bản spec đầu (phát hiện khi viết plan, bằng grep toàn repo):**
ví dụ người dùng phàn nàn ("Đơn mua từ Acme Corporation: … Xác nhận? (có /
không)") KHÔNG đến từ `nodes.py` mà từ `create_order.py:48` — một
COORDINATED write. Chuỗi `"Xác nhận? (có / không)"` đang bị **lặp nguyên văn
ở 13 chỗ**: `create_order.py` (×2), `bom_write.py` (×2), `crm_write.py` (×3),
`inventory_write.py` (×3), `mrp_write.py`, `purchase_write.py` (×3),
`returns_write.py` (×2), `edit_order.py`, `nodes.py`, và
`skills/bao-gia-chiet-khau/logic.py`. Chỉ sửa `nodes.py` sẽ KHÔNG sửa được ví
dụ người dùng nêu, và còn làm câu xác nhận **không nhất quán** giữa đường
single-step và đường coordinated.

Cách làm:
- **Gom chuỗi lặp về MỘT hằng số** trong `prompts.py`
  (`WRITE_CONFIRM_SUFFIX`), thay literal ở cả 13 chỗ. Đây là cải thiện thật:
  một chuỗi an toàn hiển thị cho người dùng không nên tồn tại 13 bản sao —
  sau này đổi câu chữ là sửa MỘT dòng.
- **Số liệu tất định** (`summary`, `plan.get('tool')`, `args_line`,
  `chain_note`, và các dòng hàng hoá của coordinated writes): GIỮ NGUYÊN Y
  HỆT — không đổi cách tính, không đổi thứ tự, không bỏ bớt. Invariant C tầng
  3 phải còn nguyên vẹn, có test canh.
- **Khung câu chữ bao quanh**: đổi sang **template tĩnh viết sẵn trong code**,
  tự nhiên hơn, render bằng f-string thường. **KHÔNG thêm lệnh gọi LLM nào**
  cho việc này — đó là toàn bộ lý do chọn template tĩnh thay vì "qua 1 lớp
  LLM cho tự nhiên".
- **Ràng buộc bắt buộc:** câu mới VẪN phải chứa cụm "xác nhận" VÀ dấu "?" —
  `live_verify_common.py:58-68` (`_looks_like_confirm_gate`) dò cổng xác nhận
  bằng đúng hai dấu hiệu này; mất một trong hai là làm hỏng 3 script
  live-verify skill agentic.

## 3. File bị chạm

| File | Thay đổi |
|---|---|
| `backend/src/agents/routing.py` | Thêm điều kiện tất định mới vào `decide_route` (§2.1 bước 3); import `_CONFIRM_WORDS`/`_match_any` từ `confirmation.py` |
| `backend/src/agents/prompts.py` | `FUSE_PROMPT` + `SYSTEM_PROMPT`: chỉ dẫn phát marker `ĐỀ_XUẤT_GHI` (§2.1 bước 1); `GATHER_ERP_PROMPT` + `FUSE_PROMPT`: chỉ dẫn auto-tra cứu (§2.2); `WRITE_CONFIRM_PREFIX`/template câu xác nhận: đổi khung câu chữ (§2.3) |
| `backend/src/agents/fanout.py` | `fuse_answer`: parse + cắt marker, gắn `additional_kwargs` (§2.1 bước 2) |
| `backend/src/agents/nodes.py` | `erp_read`: dùng chung helper parse/gắn cờ (§2.1 tổng quát hoá); `erp_write_planner`: đổi cách build `question`, số liệu tất định giữ nguyên (§2.3) |
| `backend/src/agents/{create_order,bom_write,crm_write,inventory_write,mrp_write,purchase_write,returns_write,edit_order}.py` + `backend/skills/bao-gia-chiet-khau/logic.py` | Thay literal `"Xác nhận? (có / không)"` (13 chỗ) bằng hằng `WRITE_CONFIRM_SUFFIX` từ `prompts.py` (§2.3) |
| `backend/tests/agents/test_auto_chain.py` | 4 assert đang bám literal `"Xác nhận? (có / không)"` — đổi sang tham chiếu hằng số (§2.3) |
| `backend/src/agents/synthesis.py` | Helper parse + cắt marker `ĐỀ_XUẤT_GHI`, dùng chung bởi `fuse_answer` và `erp_read` — MỘT bản, không copy. Đặt ở đây (không phải module mới) vì: `extract_used_citations`/`USED_MARKER` — helper marker anh em — đã sống ở đây, và CẢ `fanout.py` LẪN `nodes.py` đều đã import từ module này sẵn, không tạo import vòng |
| `backend/tests/agents/test_routing.py` | Test điều kiện route mới: ca DƯƠNG (có cờ + "ok" → `erp_write`) và ca ÂM (không cờ + "ok" → KHÔNG ép route) |
| `backend/tests/agents/test_fanout.py` | Test marker được cắt khỏi văn bản hiển thị và gắn đúng vào `additional_kwargs` |
| `backend/tests/agents/test_prompts.py` | Test số liệu tất định (`args_line`, tool name) vẫn xuất hiện y hệt trong câu xác nhận mới |
| `backend/tests/` (integration, `-m integration`) | Test `additional_kwargs` sống sót qua checkpointer Postgres THẬT (bài học SP-1C2 — mock bỏ lọt loại lỗi này) |

## 4. Không thuộc phạm vi (out of scope)

- Bug "nhập" bị hiểu nhầm thành `inventory_adjustment` thay vì
  `create_rfq`/mua hàng khi không có ngữ cảnh — phát hiện phụ trong lúc
  live-test §2.1, KHÔNG sửa ở plan này (không liên quan luồng xác nhận, cần
  điều tra riêng).
- Bất khớp tên sản phẩm tiếng Việt/tiếng Anh (vd "bàn làm việc cá nhân" vs
  "Individual Workplace") khi tra cứu — phát hiện phụ khác, không thuộc phạm
  vi write-confirmation UX.
- 2 lớp xác nhận (xác nhận Ý ĐỊNH rồi xác nhận lại DÒNG ĐƠN cụ thể) — ĐÃ
  đánh giá là đúng mô hình 2 giai đoạn Odoo thật (RFQ nháp → Purchase Order
  xác nhận), không phải lỗi, không sửa.
- Đường RAG thuần (`synthesize`) KHÔNG phát marker `ĐỀ_XUẤT_GHI` ở plan này:
  câu hỏi tài liệu thuần rất ít khi đề xuất hành động ghi; nối dây thêm là
  một dòng, để dành khi có bằng chứng cần.

## 5. Bất biến an toàn KHÔNG được đổi

Ghi riêng thành mục để reviewer chốt được nhanh:

1. **Không hành động ghi nào được thực thi mà chưa qua `_interrupt()` xác
   nhận thật.** Toàn bộ thay đổi ở đây chỉ ảnh hưởng ĐỊNH TUYẾN (đi tới node
   nào) và VĂN PHONG câu hỏi — không đụng `erp_write_executor`, không đụng
   điều kiện `state.get("confirmed")`, không đụng `write_gate`.
2. **Invariant C tầng 3 nguyên vẹn:** tool + args thật luôn hiện tất định
   trong câu xác nhận, không do LLM sinh lại.
3. **Không thêm lệnh gọi LLM mới** cho việc làm đẹp câu chữ (§2.3).
4. **Cổng xác nhận vẫn dò được:** câu xác nhận mới giữ cả cụm "xác nhận" lẫn
   dấu "?" (`live_verify_common.py:58-68` dựa vào đúng hai dấu hiệu này).

## 6. Kiểm chứng

1. Unit test `decide_route`: ca DƯƠNG (AI message cuối có
   `additional_kwargs["suggested_write"]` + human "ok" → `erp_write`) VÀ ca
   ÂM (AI message cuối KHÔNG có cờ + human "ok" → route bình thường, không ép).
2. Unit test `fuse_answer`: marker `ĐỀ_XUẤT_GHI` bị cắt khỏi văn bản hiển
   thị, và gắn đúng vào `additional_kwargs`.
3. Unit test câu xác nhận: số liệu tất định (`args_line`, tool name) vẫn
   xuất hiện y hệt.
4. Integration test (`-m integration`, Postgres thật): `additional_kwargs`
   sống sót vòng lưu/đọc checkpoint.
5. `pytest -m "not integration and not live"` xanh toàn bộ, không hồi quy.
6. `eval_chitchat` không hồi quy (`violations == 0`) — bảo đảm thay đổi
   prompt không phá sàn an toàn hiện có.

## 7. Cổng đánh giá — quyết định §2.1 chỉ được GIỮ nếu qua

Người dùng đã nêu rõ đây là quyết định tạm, giữ hay bỏ tuỳ tín hiệu đo được.
Live-verify thật (đã có Langfuse tracing để xác nhận đúng node/route, không
suy đoán) phải cho thấy:

1. **Ca gốc chạy đúng:** tái hiện đúng kịch bản §1.1 (câu hỏi kèm ngữ cảnh →
   `mixed` → gợi ý nhà cung cấp → "okay") và "okay" lần này route đúng vào
   `erp_write_planner`, phát `_interrupt()` thật. Bằng chứng: trace Langfuse.
2. **Không hồi quy hội thoại thường:** ít nhất 3 ca chitchat/RAG có câu hỏi
   dạng "...không?" theo sau bởi "ok"/"có" — KHÔNG ca nào bị ép sai sang
   `erp_write_planner`. Bằng chứng: trace Langfuse.
3. **§2.2 không làm hỏng tool-selection:** ít nhất 3 ca `gather_erp` thật
   (bao gồm ca 1-lựa-chọn và ca nhiều-lựa-chọn) cho kết quả đúng, không chọn
   sai tool/sai tham số — vùng này có tiền sử lỗi lặp lại.

**Nếu tiêu chí 2 hoặc 3 thất bại:** KHÔNG merge phần tương ứng. Ghi lại số đo
thật vào report và trình bày lại cho người dùng quyết định, thay vì tự nới
tiêu chí.

## 8. Tiêu chí hoàn thành

1. §2.1, §2.2, §2.3 đã cài đặt đúng, các bất biến §5 còn nguyên (review chốt
   từng mục).
2. Toàn bộ test ở §6 xanh.
3. Cổng §7 đạt cả 3 tiêu chí, có bằng chứng trace Langfuse thật đính kèm
   report — hoặc phần không đạt đã được tách ra khỏi merge và báo lại người
   dùng.
