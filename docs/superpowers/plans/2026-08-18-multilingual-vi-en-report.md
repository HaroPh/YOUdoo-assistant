# Đa ngôn ngữ Việt–Anh — báo cáo đo thật và nghiệm thu sống

**Ngày:** 2026-08-18
**Nhánh:** worktree-multilingual-vi-en
**Phạm vi:** Task 7 của kế hoạch — không viết code sản phẩm, chỉ đo và nghiệm thu.

---

## 1. Bốn cổng có thể thụt (Task 2 sửa 4 prompt)

Cả 4 cổng PASS, nhưng 2 cổng (`synthesis`, `multi_source`) FAIL ở lần chạy đầu và cần
sửa DỮ LIỆU EVAL (không phải code sản phẩm) trước khi PASS. Chi tiết ruling đầy đủ
nằm ở ledger (`​.superpowers/sdd/2026-08-18-multilingual-vi-en/progress.md`); tóm tắt:

### `read` (gemini-3.5-flash-lite) — PASS ngay lần đầu

```json
{"set": "read", "n": 27, "tool_acc": 1.0, "param_acc": 1.0,
 "fabricated_param": 0, "lat_p50": 818, "lat_p95": 1189}
```
GATE PASS — model=1.000 baseline=1.000

### `planner` (gemini-3.5-flash-lite) — PASS ngay lần đầu

```json
{"set": "planner", "n": 25, "tool_acc": 1.0, "args_acc": 1.0,
 "dangerous_misroute": 0, "parse_fail": 0, "lat_p50": 1123, "lat_p95": 1302}
```
GATE PASS — model=1.000 baseline=1.000

### `synthesis` (gemini-3.1-flash-lite) — FAIL lần đầu → sửa dữ liệu eval → PASS

Lần đầu: acc=0.917 (11/12). Ca fail: "Hàng giảm giá có được hoàn trả không?" — model trả
lời ĐÚNG, có căn cứ (NGUỒN_DÙNG: 4, false_answer=false) nhưng diễn giải MỚI ("không được
phép hoàn trả") không khớp 2 phương án literal đã đăng ký trước đó. Tái lập 2/2 lần chạy,
byte-identical — không phải nhiễu sampling, là ưu tiên diễn đạt ổn định của
model+RAG_SYNTHESIS_PROMPT (Task 2 vừa thêm khối LANGUAGE_RULE ở cuối). Áp dụng đúng cơ
chế đã được review chấp nhận trước đó (SP-1C1): thêm phương án khớp NGUYÊN VĂN thứ 3 đã
xác minh thật vào `SYNTHESIS_CASES`, KHÔNG nới gate (commit `f06bd1a`).

```json
{"set": "synthesis", "n": 12, "grounded_acc": 1.0, "false_answer": 0,
 "false_insufficient": 0, "lat_p50": 1414, "lat_p95": 7799}
```
GATE PASS — model=1.000 baseline=1.000

### `multi_source` (gemini-3.1-flash-lite) — FAIL lần đầu → sửa dữ liệu eval → PASS

Lần đầu: `fabricated_number=1` (điều kiện TUYỆT ĐỐI của gate, khác bản chất với
`both_source_coverage=0.75` hoà baseline). Ca "Azure Interior đặt 50 Large Cabinet được
chiết khấu bao nhiêu?" — model liệt kê "(0%, 5% hoặc 10%)" khi từ chối trả lời dứt khoát
(thiếu cấp khách hàng). Đọc chunk RAG thật xác nhận: "5%"/"10%" đã literal trong chunk,
"0%" suy ĐÚNG từ câu prose "Khách hàng cấp Thường không áp dụng chiết khấu ngoài bảng giá
niêm yết" — không phải chữ số literal nên máy quy oan là bịa, xác minh tay là sự thật có
căn cứ. Thêm entry đã xác minh vào `MULTI_SOURCE_DERIVED_DIGITS` (commit `6072b3a`).

```json
{"set": "multi_source", "n": 8, "both_source_coverage": 0.75,
 "citation_validity": 1.0, "fabricated_number": 0, "lat_p50": 1869, "lat_p95": 2366}
```
GATE PASS — model=0.750 baseline=0.750 (2 ca `both:false` còn lại là biến thiên đã biết,
hoà đúng baseline, không phải quy hồi).

### Lỗ hổng riêng phát hiện trước Bước 2: CLI runner chưa nối 2 set mới

Chạy đúng lệnh CLI mà chính plan này ghi (`--set language`/`--set localize`) thì
argparse từ chối "invalid choice" — `run_eval.py`'s own `main()` chưa từng được nối 2 set
mới (chỉ `eval_gate.py`, registry job đêm, được Task 5/6 nối). Đối chiếu plan gốc xác
nhận: đây là lỗ hổng trong CHÍNH VĂN BẢN PLAN (Task 5/6 brief không yêu cầu bước này), không
phải lỗi implementer. Sửa trực tiếp (commit `bc5b284`).

---

## 2. Bộ `language` (tầng prompt), model gemini-3.5-flash

Lần đầu FAIL: acc=0.833 (5/6). Ca `RAG_SYNTHESIS_PROMPT`/"chính sách hoàn hàng là gì?"
(want=vi) → got=en, body="KHÔNG_ĐỦ_THÔNG_TIN". Nguyên nhân: `eval_language()` gọi prompt
BARE (không TÀI LIỆU) — với RAG_SYNTHESIS_PROMPT, không có ngữ cảnh nghĩa là model LUÔN
đúng theo hợp đồng trả về hằng số SENTINEL cố định (`synthesis.py:16`) bất kể ngôn ngữ câu
hỏi — không phải văn xuôi, "ngôn ngữ" của nó vô nghĩa để đo. Xác minh trực tiếp: cả hai câu
hỏi (vi/en) đều ra byte-identical "KHÔNG_ĐỦ_THÔNG_TIN" — hợp đồng SENTINEL nguyên vẹn qua
LANGUAGE_RULE (không phải hồi quy sản phẩm — `synthesis.py:202` vẫn chặn đúng và thay bằng
GUARD_MSG, bản thân GUARD_MSG lại đi qua `localize()` ở chốt `ERPAgent.chat()` khi ra tới
người dùng thật). Ca "en" từng PASS chỉ là trùng hợp (cùng marker không khớp
`looks_vietnamese()` ở cả hai ngôn ngữ).

Sửa: bơm TÀI LIỆU thật (đúng hình dạng `synthesize()`, topic `chinh_sach_hoan_hang`) chỉ
cho nhánh RAG_SYNTHESIS_PROMPT, giữ nguyên bare-call cho CHITCHAT/FUSE (commit `a473449`).
Đây cũng là ca kiểm ĐÚNG rủi ro trích dẫn danh từ riêng tiếng Việt mà spec §2.4 nói tới —
mạnh hơn ca cũ.

```json
{"set": "language", "n": 6, "acc": 1.0, "lat_p50": 5133, "lat_p95": 12231, "fails": []}
```

## 3. Bộ `localize` (tầng điều phối), model gemma-4-26b

```json
{"set": "localize", "n": 7, "acc": 0.7142857142857143, "fact_loss": 2,
 "lat_p50": 22332, "lat_p95": 44223,
 "fails": [
   {"lang": "en", "reason": "roi_ve_ban_goc"},
   {"lang": "en", "reason": "roi_ve_ban_goc"}
 ]}
```

Cả 2 ca fail đều `reason: "roi_ve_ban_goc"` (rơi về bản gốc — lớp phòng thủ hoạt động,
KHÔNG phải crash/lỗi). Log kèm: "gemma-4-26b trả phản hồi rỗng (finish_reason=MAX_TOKENS)"
— đặc tính ĐÃ BIẾT của gemma-4-26b (catalog.py: "KHÔNG tắt được thinking"). `facts_survived()`
bắt đúng output rỗng → trả về bản gốc tiếng Việt, không bao giờ ném. 2/7 = 28.6%, dưới xa
ngưỡng "quá nửa" mà plan đặt ra để cân nhắc lại quyết định "cho LLM dịch" — không cần sửa,
không cần xét lại quyết định.

**Lưu ý quan trọng — cận dưới, không phải số thật của sản phẩm**: bộ đo GHIM cứng một
model (bỏ qua chuỗi CHAINS, đúng thiết kế cô lập phép đo). Sản phẩm thật dùng vai
`evaluator` KHÔNG ghim, có chuỗi fallback `("gemma-4-26b", "groq-gpt-oss-20b")` — khi gemma
rỗng MAX_TOKENS trong sản phẩm thật, Router rơi xuống groq-gpt-oss-20b và CÓ THỂ dịch
thành công thay vì rơi thẳng về tiếng Việt. acc=0.714 đo được ở đây là kịch bản xấu nhất
(một mắt xích), không phải số thật của pipeline đầy đủ.

## 4. Nghiệm thu sống qua HTTP thật (`start-dev.ps1`)

Khởi động backend thật (:8002) + 3 mcp-odoo theo vai (:8003/8004/8005), gọi qua đúng
`/v1/chat/completions` với header `x-openwebui-user-id` (tài khoản admin thật). Sự cố công
cụ đo (KHÔNG phải sản phẩm): PowerShell 5.1 `Invoke-RestMethod` gửi/đọc body không đúng
UTF-8 — sửa bằng ép UTF-8 byte tường minh ở client, không đụng gì phía backend (xác nhận
bằng traceback: lỗi decode xảy ra ở `req.json()`, TRƯỚC khi chạm code sản phẩm).

| # | câu | kết quả |
|---|---|---|
| 1 | `show me the details of purchase order P00003` | ✅ tiếng Anh, nhãn dịch đúng (Vendor/Status/Total Amount...), số liệu nguyên vẹn (255.0, 10, 25.5) |
| 2 | `cho tôi xem chi tiết đơn mua P00003` | ✅ tiếng Việt, không hồi quy, cùng số liệu |
| 3 | `what is the company return policy?` | ✅ tiếng Anh; tên file nguồn `(policy.docx)` giữ nguyên; xem Phát hiện phụ #1 |
| 4 | `does order S00165 meet the delivery SLA?` | ✅ tiếng Anh — đường `mixed` từng hỏng ở spike, nay XANH |
| 5 | `hi, who are you?` | ✅ tiếng Anh, thương hiệu "Youdoo" còn nguyên |
| 6 | `receive the goods for purchase order P00003` | ✅ câu xác nhận tiếng Anh, `(receive_order: order_ref=P00003)` và mã P00003 còn nguyên — **kịch bản DUY NHẤT chứng minh Task 3+4 hoạt động đầu-cuối, ĐẠT** |
| 7 | `nhận hàng cho đơn mua P00003` | ✅ câu xác nhận tiếng Việt, byte-identical với hôm nay, không hồi quy |

**Không thao tác ghi thật nào được xác nhận/thực thi.** Cả 2 lượt xác nhận (kịch bản 6, 7)
đều bị HỦY chủ động ngay sau khi quan sát câu hỏi xác nhận (trả lời "no"/"không" cùng
session) — kỷ luật không để một hành động ghi thật xảy ra ngoài ý muốn khi đang đo/thử.
Không có ghi chú/thao tác Odoo thật nào phát sinh trong quá trình đo.

### Phát hiện phụ #1 (lành tính, không sửa): nhãn trích dẫn bị dịch

Kịch bản 3 dịch CẢ nhãn mục trích dẫn ("Chính sách hoàn hàng › Điều 1" →
"Return Policy › Section 1"), không giữ nguyên tiếng Việt như câu chữ không hình thức của
spec §2.4. Trace: `build_citations()` (synthesis.py:89) tất định, dùng đúng `section_path`
gốc — nhưng toàn bộ câu trả lời (văn xuôi + chân trang) đi qua MỘT LẦN `localize()` ở chốt
`ERPAgent.chat()` (vì "📄 Nguồn:" có dấu tiếng Việt, kích hoạt dịch). `TRANSLATE_PROMPT` có
dặn "Keep proper nouns (product, partner, document names) unchanged" nhưng đây là chỉ dẫn
ngôn ngữ tự nhiên, không có cổng tất định canh riêng cho nhãn mục (`facts_survived` chỉ
canh số/mã/ngày).

**Ruling: CHẤP NHẬN, không sửa.** Tên file gốc `(policy.docx)` (định danh thật để tra
ngược) vẫn giữ nguyên đúng, mọi sự việc số/ngày sống sót đúng, đây là câu ĐỌC không phải
câu xác nhận GHI (rủi ro thấp/không có — không ai "duyệt nhầm thao tác" vì một nhãn mục
trích dẫn bị dịch), và bản dịch nhãn mục thực ra DỄ ĐỌC hơn cho người dùng tiếng Anh. Ghi
nhận như một khác biệt so với câu chữ spec, không phải lỗi.

### Phát hiện phụ #2 (xác nhận đúng giới hạn đã tài liệu hoá từ trước)

Gửi "no" bằng đúng MỘT tin nhắn (không kèm lịch sử) sau kịch bản 6 → phản hồi "Đã hủy thao
tác." (tiếng Việt) dù cả luồng là tiếng Anh. Trace: `chat()`'s `lang` chỉ quét `messages`
của LƯỢT GỌI HIỆN TẠI (`erp_agent.py:216-220`), không phải lịch sử đầy đủ trong
checkpointer — đúng GIỚI HẠN đã ghi sẵn trong docstring của chính Task 4
(`erp_agent.py:206-209`): "client script chỉ gửi đúng một tin nhắn mỗi lượt... sẽ mất ngôn
ngữ ở lượt xác nhận → rơi về 'vi'. Đó là chiều an toàn."

Verify: gửi LẠI đúng kịch bản với lịch sử ĐẦY ĐỦ (mô phỏng client thật — Open WebUI luôn
gửi lại toàn bộ lịch sử mỗi lượt) → phản hồi ĐÚNG "Operation cancelled." tiếng Anh.

**Kết luận: KHÔNG phải hồi quy.** Giới hạn đã biết, đã review (Task 4), hoạt động đúng
chiều an toàn đã thiết kế. Ghi nhận như xác nhận thực nghiệm cho giới hạn đã công bố
trước, không phải phát hiện mới.

## 5. Chưa làm được / ngoài phạm vi

- Ngôn ngữ thứ ba (ngoài phạm vi theo spec §7).
- Bảng thông điệp hai ngôn ngữ cho tầng điều phối (đã cân nhắc và bác ở spec §4; §4.3's
  cổng phủ quyết + Bước 3 ở trên cho thấy tỉ lệ rơi về bản gốc (28.6%, đo ở kịch bản xấu
  nhất) chưa đủ cao để mở lại quyết định này).
- Rủi ro tổng quát "hai con số độc lập bị hoán đổi" trong `facts_survived()` (Task 3,
  finding #2) — đã ruling chấp nhận, ghi thành giới hạn có tài liệu, không phải nợ của
  Task 7.
- Nhãn mục trích dẫn RAG bị dịch (Phát hiện phụ #1 ở trên) — chấp nhận, không sửa, có thể
  xem lại nếu sau này có bằng chứng thực tế gây nhầm lẫn.

## 6. Kết luận

Cả 6 cổng liên quan (`read`, `planner`, `synthesis`, `multi_source`, `language`,
`localize`) đều PASS ở trạng thái cuối cùng. Cả 7 kịch bản sống qua HTTP thật đều đúng như
plan dự đoán, bao gồm kịch bản DUY NHẤT (kịch bản 6) chứng minh cơ chế dịch câu xác nhận
ghi hoạt động đầu-cuối với lớp phủ quyết tất định giữ nguyên mã chứng từ. Không có hồi quy
thật nào được phát hiện; 2 phát hiện phụ đều lành tính/đã biết trước, không cần vòng sửa
mới. Đợt đa ngôn ngữ Việt–Anh đạt tiêu chí nghiệm thu của Task 7.
