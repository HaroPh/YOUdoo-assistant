# Báo cáo — sửa hướng dẫn chọn tool của gather_erp

Plan: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix.md`
Spec: `docs/superpowers/specs/2026-08-01-gather-erp-tool-selection-design.md`

## Bước 1 — xác nhận case sửa tái hiện đúng bug (TRƯỚC khi sửa prompt)

Chạy `jobs run eval-gate --set gather`, model: `gemini-3.1-flash-lite`, TRƯỚC khi
sửa `GATHER_ERP_PROMPT`.

- verdict: `PASS` (gate `gather` trả True vô điều kiện — verdict này
  không phản ánh việc 2 case có FAIL đúng kỳ vọng hay không, xem chi tiết
  case dưới đây)
- `tool_recall`: `0.75` (3/4 case đạt — 1 case fail là `chinh_sach_hoan_hang`)
- `fact_coverage`: `0.75` (cùng 1 case fail cả hai tiêu chí)
- log gốc: `logs/jobs/eval-gate-20260801T230841.json`
- Case `sla_giao_hang`: **PASS ngoài dự kiến** — case này KHÔNG xuất hiện
  trong mảng `fails` của log. Vì hàm `call()` trong `evals/run_eval.py::eval_gather`
  chỉ trả `None` (= pass, không ghi vào `fails`) khi CẢ HAI `tool_recall_ok`
  và `fact_coverage_ok` đều `True`, việc case này vắng mặt trong `fails`
  nghĩa là model đã tự gọi đúng `list_sale_orders` (tool mới, đúng
  `required_tools` đã sửa ở Task 1) VÀ lấy đủ cả hai fact ngày
  (`18/07/2026`, `20/07/2026`) cho câu hỏi
  "Đơn S00042 có đáp ứng SLA giao hàng không?" — dù `GATHER_ERP_PROMPT`
  CHƯA được sửa. Log chỉ ghi chi tiết (`called`, `erp_facts`) cho case
  trong `fails`; vì case pass, KHÔNG có `called`/`erp_facts` nào được ghi
  lại trong log cho case này (checkpoint trung gian cũng đã bị xoá sau khi
  chạy xong sạch — `jobs/resilience.py:88`, `checkpoint_path.unlink(missing_ok=True)`
  khi chạy hết không lỗi). Không có bằng chứng thô nào khác về việc model
  gọi tool nào cho case này ngoài kết luận suy ra được từ việc nó KHÔNG
  nằm trong `fails`.
- Case `chinh_sach_hoan_hang`: **FAIL đúng kỳ vọng** — `called`:
  `["get_sale_order_detail"]` (đúng như giả thuyết gốc: model gọi tool cũ,
  không thoả `required_tools = ("list_sale_orders",)`). Chi tiết đầy đủ từ
  log:
  ```json
  {
    "topic": "chinh_sach_hoan_hang",
    "question": "Đơn S00042 còn được hoàn hàng theo chính sách không?",
    "called": ["get_sale_order_detail"],
    "required_tools": ["list_sale_orders"],
    "erp_facts": "Dữ kiện liên quan đến đơn S00042:\n*   Khách hàng: Azure Interior\n*   Trạng thái: done (đã giao)",
    "tool_recall_ok": false,
    "fact_coverage_ok": false
  }
  ```

**Kết luận bước này:** **BLOCKED** — chỉ 1/2 case (`chinh_sach_hoan_hang`)
FAIL đúng kỳ vọng với `tool_recall_ok: false`. Case `sla_giao_hang` PASS
ngoài dự kiến (không nằm trong `fails`), nghĩa là với đúng câu hỏi và
fixture đã sửa ở Task 1, model gọi đúng `list_sale_orders` mà KHÔNG cần
sửa `GATHER_ERP_PROMPT`. Điều này mâu thuẫn với giả thuyết gốc của plan
("gather_erp hiện tại luôn gọi sai tool `get_sale_order_detail` khi cần
ngày/trạng thái giao hàng" — áp dụng cho cả hai câu hỏi cùng hình dạng).
Không tự đoán nguyên nhân (có thể: câu hỏi `sla_giao_hang` có từ khoá "SLA
giao hàng" đủ mạnh để model tự chọn đúng tool ngay cả với prompt cũ, trong
khi câu hỏi `chinh_sach_hoan_hang` không có tín hiệu từ khoá tương đương;
hoặc đơn thuần là nhiễu non-determinism của 1 lần gọi LLM thật) — cần
controller quyết định bước tiếp theo trước khi động vào `GATHER_ERP_PROMPT`
(Task 2).

## Điều tra thêm của controller — quyết định về BLOCKED

Trước khi hỏi người dùng, controller tự làm 2 việc để loại trừ khả năng
"chỉ là nhiễu":

1. **Chạy lại `--set gather` lần 2** (log
   `logs/jobs/eval-gate-20260801T231348.json`): kết quả giống hệt lần 1 —
   `tool_recall=0.75`, `fact_coverage=0.75`, `fails` chỉ chứa
   `chinh_sach_hoan_hang` (`called: ["get_sale_order_detail"]`).
   `sla_giao_hang` PASS lại. → không phải nhiễu ngẫu nhiên của 1 lần gọi,
   đây là hành vi tái lập được.

2. **Diagnostic riêng cho `sla_giao_hang`** (script tạm, không commit, gọi
   trực tiếp `make_gather_erp_node` thật với đúng câu hỏi + fixture của
   case này, in ra TOÀN BỘ `called` bất kể pass/fail — log không ghi lại
   chi tiết này cho case pass):

   ```
   QUESTION: Đơn S00042 có đáp ứng SLA giao hàng không?
   CALLED: ['get_sale_order_detail', 'list_sale_orders', 'list_late_deliveries']
   ```

   Kết quả: model VẪN gọi `get_sale_order_detail` ĐẦU TIÊN (khớp với chẩn
   đoán trực tiếp qua Odoo thật ở phiên trước khi viết plan này — xu hướng
   mặc định gọi tool này trước là có thật và nhất quán). Nhưng sau đó, cho
   riêng câu hỏi này, model TỰ gọi thêm `list_sale_orders` (lấy được cả 2
   ngày) và `list_late_deliveries` (không có trong `tool_fixtures`, stub
   trả "Không có dữ liệu liên quan." — model diễn giải đúng thành "không có
   đơn trong danh sách trễ hạn"). Việc gọi thêm `list_sale_orders` khiến
   `tool_recall_ok` đạt (kiểm tra tập con: `required_tools ⊆ called`, xem
   `evals/run_eval.py::_score_gather` dòng ~205).

   Với câu hỏi `chinh_sach_hoan_hang`, model KHÔNG tự gọi thêm tool nào sau
   `get_sale_order_detail` — có thể vì câu trả lời "trạng thái: done (đã
   giao)" của fixture (cố ý viết cụt, không có ngày) "trông đủ" để dừng
   vòng lặp ReAct, trong khi câu hỏi `sla_giao_hang` ("có đáp ứng SLA
   không?") tự nó gợi ý cần xác minh thêm (ngày, phiếu giao trễ) nên model
   chủ động tra cứu tiếp.

**Kết luận của điều tra:** cơ chế gốc (mặc định gọi `get_sale_order_detail`
trước, KHÔNG có quy tắc nào dẫn dắt dùng `list_sale_orders`) là CÓ THẬT và
nhất quán ở cả hai case — khớp với chẩn đoán Odoo thật trước đó. Điều khác
biệt là liệu model có TỰ ý gọi thêm tool thứ hai hay không, và điều đó phụ
thuộc vào cách đặt câu hỏi — không ổn định, không phải điều plan có thể
kiểm soát bằng cách viết fixture. Đây chính là lý do Task 2 (thêm quy tắc
tường minh vào prompt) vẫn có giá trị: mục tiêu không phải "làm case FAIL
2/2 cho đẹp" mà là loại bỏ sự phụ thuộc vào việc model có "tự suy luận
thêm" hay không.

**Quyết định (do người dùng chọn qua AskUserQuestion, không phải controller
tự quyết):** **Tiếp tục Task 2**, không dừng ở BLOCKED. Ghi nhận trung thực:
Task 1 chỉ tái hiện được lỗi tất định 1/2 case
(`chinh_sach_hoan_hang`); case còn lại (`sla_giao_hang`) đã tự vượt qua
nhờ hành vi gọi tool phụ không ổn định của model, KHÔNG phải nhờ
`GATHER_ERP_PROMPT` đã được sửa. Task 2 vẫn tiến hành như kế hoạch: thêm
quy tắc chọn tool vào prompt, đo lại `--set gather` để xác nhận CẢ HAI case
đều PASS sau khi sửa (không chỉ dựa vào diễn biến may rủi của
`sla_giao_hang` như ở bước này).

## Ghi chú vận hành (ngoài phạm vi bug đang đo)

`python -m jobs run eval-gate --set gather` gọi thẳng ban đầu (không export
biến môi trường thủ công) bị lỗi hạ tầng `INFRA_ERROR` (`exit_code: 2`,
`error: "'DATABASE_URL'"`) — log `logs/jobs/eval-gate-20260801T230422.json`.
Nguyên nhân: `backend/jobs/__main__.py` KHÔNG gọi `load_dotenv()` (khác với
`backend/tests/conftest.py:26`, nơi có `load_dotenv(...)` cho pytest) — CLI
`jobs` không tự đọc `.env` như mô tả trong hướng dẫn bổ sung của controller.
Đã xác minh `.env` ở root worktree có `DATABASE_URL` hợp lệ và đúng định
dạng `KEY=VALUE` đơn giản (không ký tự đặc biệt cần escape). Khắc phục tạm
thời để chạy được Step 4 thật: export toàn bộ `.env` vào shell trước khi
gọi job (`set -a && source ../.env && set +a`) — KHÔNG sửa bất kỳ file
source nào trong repo. Đây là vấn đề hạ tầng độc lập với bug đang sửa,
ghi lại ở đây để controller biết (không nằm trong phạm vi sửa của Task 1).

## Bước 2 — xác nhận đã sửa (SAU khi sửa prompt)

Sửa `GATHER_ERP_PROMPT` (`backend/src/agents/prompts.py:152`), thêm ĐÚNG
một gạch đầu dòng mới theo văn bản Step 2 của brief Task 2 (không đổi gì
khác trong file):

```
- Câu hỏi cần NGÀY (xác nhận, đặt hàng, giao hàng) hoặc TRẠNG THÁI GIAO của MỘT đơn bán cụ thể: dùng `list_sale_orders` (lọc theo tên khách hàng hoặc điều kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG có ngày hay trạng thái giao).
```

Full unit test (`-m "not integration and not live"`): `1095 passed, 4
skipped, 43 deselected` — không hồi quy, không test nào assert nguyên văn
prompt cũ.

Chạy `jobs run eval-gate --set gather`, cùng model
(`gemini-3.1-flash-lite`), SAU khi sửa `GATHER_ERP_PROMPT`. Chạy 2 lần độc
lập để loại trừ nhiễu non-determinism (theo đúng kỷ luật đã dùng ở Bước 1
khi gặp kết quả bất ngờ):

- `tool_recall`: `0.75` (Bước 1: `0.75`) — KHÔNG đổi
- `fact_coverage`: `0.75` (Bước 1: `0.75`) — KHÔNG đổi
- log gốc lần 1: `logs/jobs/eval-gate-20260801T232648.json`
- log gốc lần 2 (lặp lại để kiểm tra nhiễu): `logs/jobs/eval-gate-20260801T232742.json`
  — kết quả GIỐNG HỆT lần 1 (cùng `called`, cùng `erp_facts` nguyên văn) →
  không phải nhiễu ngẫu nhiên, là hành vi tái lập được.
- Case `sla_giao_hang`: **PASS** ở cả 2 lần — nhưng đây là hành vi ĐÃ CÓ
  TỪ TRƯỚC khi sửa prompt (xem Bước 1, mục "Điều tra thêm của
  controller": model tự gọi thêm `list_sale_orders` +
  `list_late_deliveries` không cần quy tắc prompt nào). Không có bằng
  chứng nào cho thấy quy tắc prompt mới là NGUYÊN NHÂN case này pass —
  case này pass độc lập với việc sửa prompt, KHÔNG phải bằng chứng cho
  việc sửa có tác dụng.
- Case `chinh_sach_hoan_hang`: **VẪN FAIL** — `called`:
  `["get_sale_order_detail"]`, giống hệt tín hiệu FAIL ở Bước 1 (trước khi
  sửa prompt). Chi tiết đầy đủ (giống hệt cả 2 lần chạy):
  ```json
  {
    "topic": "chinh_sach_hoan_hang",
    "question": "Đơn S00042 còn được hoàn hàng theo chính sách không?",
    "called": ["get_sale_order_detail"],
    "required_tools": ["list_sale_orders"],
    "erp_facts": "Dữ kiện về đơn hàng S00042:\n*   Khách hàng: Azure Interior\n*   Trạng thái: done (đã giao)",
    "tool_recall_ok": false,
    "fact_coverage_ok": false
  }
  ```

### Chẩn đoán — vì sao quy tắc prompt mới không đổi được hành vi cho case này

Đối chiếu với fixture (`backend/evals/cases.py:524-530`): câu hỏi "Đơn
S00042 còn được hoàn hàng theo chính sách không?" KHÔNG nhắc từ khoá
"ngày" hay "trạng thái giao" trong bề mặt câu chữ — nó hỏi về TÍNH ĐỦ
ĐIỀU KIỆN hoàn hàng (return eligibility). Quy tắc mới thêm vào
`GATHER_ERP_PROMPT` được viết bám theo bề mặt câu hỏi ("Câu hỏi cần
NGÀY... hoặc TRẠNG THÁI GIAO") — câu hỏi này không khớp mẫu đó theo nghĩa
đen, dù về bản chất việc trả lời đúng phụ thuộc vào ngày giao (chính sách
hoàn hàng luôn có mốc thời gian, đây là suy luận thuộc về bước FUSE, gather_erp
không được yêu cầu tự suy luận vậy). Thêm vào đó, fixture
`get_sale_order_detail` trả sẵn "trạng thái: done (đã giao)" — bề ngoài
có vẻ đã trả lời được "trạng thái giao", nên model dừng vòng lặp ReAct
sớm mà không tra cứu thêm. So sánh: `sla_giao_hang` ("có đáp ứng SLA giao
hàng không?") tự thân câu hỏi gợi ý cần xác minh thêm (khớp quan sát của
Bước 1 — model chủ động gọi thêm tool ngay cả khi KHÔNG có quy tắc
prompt), còn `chinh_sach_hoan_hang` thì không.

**Kết luận Bước 2: BLOCKED.** Quy tắc prompt mới (đúng nguyên văn Step 2
của brief) KHÔNG đủ để đổi hành vi chọn tool của case
`chinh_sach_hoan_hang` — tái lập 2/2 lần chạy độc lập, không phải nhiễu.
Đây KHÔNG phải vấn đề tầng `verify_erp_grounding` (tool đúng nhưng
`fact_coverage_ok` sai) — tool bị chọn SAI ngay từ đầu
(`get_sale_order_detail` thay vì `list_sale_orders`), giống hệt tín hiệu
FAIL ở Bước 1. Theo đúng phạm vi brief, KHÔNG tự ý viết thêm quy tắc mở
rộng ngoài văn bản Step 2 đã cho — cần quyết định riêng của
controller/người dùng (ví dụ: mở rộng quy tắc để bắt cả các câu hỏi dạng
"hoàn hàng/đổi trả/bảo hành" ngụ ý cần ngày dù không nói thẳng, hay hướng
khác).

Thay đổi `prompts.py` VẪN được giữ lại và commit (không revert): đây là
thay đổi đúng về mặt kỹ thuật theo văn bản Step 2, đã qua đầy đủ unit
test, không gây hồi quy, không làm case nào khác (kể cả `sla_giao_hang`)
tệ đi. Nó chỉ đơn giản là CHƯA ĐỦ RỘNG để bắt case `chinh_sach_hoan_hang`
— giữ lại làm nền cho quyết định mở rộng tiếp theo, thay vì bỏ đi và phải
làm lại từ đầu. Chi tiết vận hành đầy đủ (lệnh, log, đối chiếu số liệu
Bước 1 vs Bước 2):
`.superpowers/sdd/2026-08-01-gather-erp-tool-selection-fix/task-2-report.md`.

## Bước 2b — mở rộng quy tắc sau BLOCKED, đo lại — kết quả: BLOCKED (regression ngoài phạm vi)

**Lý do mở rộng:** quy tắc hẹp ở Bước 2 (bám sát bề mặt câu hỏi — "cần
NGÀY... hoặc TRẠNG THÁI GIAO") không bắt được câu hỏi ngụ ý — câu hỏi
`chinh_sach_hoan_hang` ("Đơn S00042 còn được hoàn hàng theo chính sách
không?") không nói thẳng chữ "ngày"/"trạng thái giao", dù về bản chất cần
ngày giao để tính hạn hoàn hàng. Người dùng thật đã xem finding BLOCKED
này và CHỌN mở rộng quy tắc thay vì dừng lại hoặc chấp nhận giới hạn —
lệch khỏi văn bản Step 2 gốc của brief Task 2, được người dùng thật duyệt
tường minh (không phải controller/tôi tự quyết). Controller đã tự kiểm
chứng bản mở rộng bằng script tạm (không commit) trước khi giao lại: PASS
sạch 2/2 lần cho riêng case `chinh_sach_hoan_hang`.

**Quy tắc mở rộng** (`backend/src/agents/prompts.py:152`, thay 1 dòng):

```
- Câu hỏi cần NGÀY (xác nhận, đặt hàng, giao hàng) hoặc TRẠNG THÁI GIAO của MỘT đơn bán cụ thể — kể cả khi câu hỏi không nói thẳng chữ "ngày"/"trạng thái giao" mà hỏi về SLA, chính sách hoàn hàng, bảo hành, đổi trả trên một đơn cụ thể (những câu hỏi này CẦN ngày giao thực tế để tính hạn) — dùng `list_sale_orders` (lọc theo tên khách hàng hoặc điều kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG có ngày hay trạng thái giao).
```

Full unit test: 1 lần đầu `1 failed` — flake timing hệ thống không liên
quan (`tests/jobs/test_eval_latency.py`, `assert 9.8745 >= 10.0`, chạy
riêng file đó `8 passed`, xác nhận flake). Chạy lại toàn bộ: `1095
passed, 4 skipped` — sạch.

Đo thật `--set gather`, TOÀN BỘ 4 case (không chỉ 2 case mục tiêu), 2 lần
độc lập:

| | Bước 2 (quy tắc hẹp) | Bước 2b lần 1 (mở rộng) | Bước 2b lần 2 (kiểm tra lại) |
|---|---|---|---|
| `tool_recall` | 0.75 | 1.0 | 1.0 |
| `fact_coverage` | 0.75 | 0.75 | 0.75 |
| `sla_giao_hang` | PASS | PASS | PASS |
| `chinh_sach_hoan_hang` | FAIL | **PASS** | **PASS** |
| `chinh_sach_thanh_toan` | PASS | **FAIL** (mới) | **FAIL** (mới) |
| `bang_gia_chiet_khau` | PASS | PASS | PASS |
| log | `eval-gate-20260801T232742.json` | `eval-gate-20260801T233859.json` | `eval-gate-20260801T234007.json` |

**Tin tốt:** cả 2 case mục tiêu của toàn bộ plan (`sla_giao_hang`,
`chinh_sach_hoan_hang`) đều PASS ở cả 2 lần chạy — đúng như controller đã
kiểm chứng bằng script tạm.

**Tin xấu — regression ngoài phạm vi:** `chinh_sach_thanh_toan` (KHÔNG bị
đụng ở Task 1, vẫn PASS bình thường ở Bước 2) bắt đầu FAIL sau khi mở
rộng quy tắc, tái lập giống hệt 2/2 lần (`called`, `erp_facts` nguyên văn
giống nhau):

```json
{
  "topic": "chinh_sach_thanh_toan",
  "question": "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có bị tạm dừng xử lý không?",
  "called": ["get_overdue_invoices", "list_sale_orders", "list_sale_orders", "find_customer"],
  "required_tools": ["get_overdue_invoices"],
  "erp_facts": "Xin lỗi, tôi không chắc chắn về độ chính xác của câu trả lời này. Vui lòng kiểm tra lại trực tiếp trên hệ thống hoặc hỏi lại cụ thể hơn.",
  "tool_recall_ok": true,
  "fact_coverage_ok": false
}
```

**Chẩn đoán (căn cứ mã nguồn, không suy đoán):** câu hỏi có cụm "đơn hàng
mới... tạm dừng xử lý" — đủ giống mẫu "TRẠNG THÁI... của một đơn bán cụ
thể" trong quy tắc mở rộng khiến model tự gọi thêm `list_sale_orders` +
`find_customer` ngoài `get_overdue_invoices` (required). `tool_recall_ok`
vẫn `true` (tập required vẫn là tập con của called) — vấn đề nằm ở
`fact_coverage_ok: false`: `erp_facts` là nguyên văn
`ERP_GROUNDING_FALLBACK_MSG` (`backend/src/agents/erp_grounding.py:19-22`)
— message thay thế TOÀN BỘ câu trả lời khi bước `verify_erp_grounding`
(LLM-judge riêng, so khớp câu trả lời nháp với tool outputs thô) phán
quyết phát hiện mâu thuẫn. Với 4 lượt gọi tool thay vì 1, khả năng tổng
hợp sai lệch dữ liệu giữa nhiều nguồn tăng, kích hoạt fallback. Đây đúng
là lớp vấn đề `verify_erp_grounding` mà brief Task 2 gốc đã lường trước
("...ghi nhận đây là một lớp vấn đề KHÁC... KHÔNG tự ý sửa thêm") — chỉ
khác là xuất hiện ở case NGOÀI phạm vi mục tiêu, do side effect của việc
mở rộng quy tắc.

**Kết luận Bước 2b: BLOCKED.** Không đạt 4/4 case PASS — quy tắc mở rộng
giải quyết đúng 2 case mục tiêu nhưng đổi lấy 1 regression mới. Theo đúng
chỉ dẫn của coordinator cho nhánh "không đủ 4/4": DỪNG LẠI, không tự ý
mở rộng/thu hẹp quy tắc thêm nữa, báo cáo lại để quyết định. **KHÔNG
commit** thay đổi lần này (khác Bước 2 — nơi vẫn commit vì không có
regression mới). `backend/src/agents/prompts.py` hiện đang ở trạng thái
ĐÃ SỬA (bản mở rộng) nhưng CHƯA COMMIT trong worktree, chờ quyết định
tiếp theo. Chi tiết đầy đủ:
`.superpowers/sdd/2026-08-01-gather-erp-tool-selection-fix/task-2-report.md`
(mục "Bước 2b").

## Bước 2c — thu hẹp lại quy tắc sau khi bản mở rộng làm hỏng `chinh_sach_thanh_toan`, đo lại 4/4 x 2 lần — DONE

**Lý do thu hẹp:** bản mở rộng ở Bước 2b dùng cụm khái quát "TRẠNG THÁI
GIAO của MỘT đơn bán cụ thể" — cụm này đủ tổng quát để model tự suy rộng
sang câu hỏi thanh toán ("đơn hàng mới... tạm dừng xử lý" đọc giống
"trạng thái của một đơn"), khiến nó tự gọi thêm `list_sale_orders` +
`find_customer` ngoài `get_overdue_invoices` (required), kích hoạt
fallback của `verify_erp_grounding`. Controller đã thu hẹp lại: (1) bỏ
cụm khái quát "trạng thái của đơn", thay bằng liệt kê ĐÍCH DANH 4 chủ đề
(SLA giao hàng / chính sách hoàn hàng / bảo hành / đổi trả); (2) thêm câu
loại trừ tường minh cuối dòng cho thanh toán/hoá đơn/chiết khấu, chỉ định
rõ dùng đúng tool tương ứng, không tự ý gọi thêm `list_sale_orders`. Đã
kiểm chứng bằng script tạm (không commit) chạy đủ 4 case, 2 lần độc lập —
4/4 PASS cả 2 lần — trước khi giao lại để áp dụng vào file thật. Đây là
vòng chỉnh sửa thứ 3, mỗi vòng đều được đo bằng LLM thật (không mock) và
được người dùng thật + controller duyệt qua AskUserQuestion trước khi áp
dụng.

**Quy tắc cuối cùng** (`backend/src/agents/prompts.py:152`, thay 1 dòng,
không đổi gì khác):

```
- Câu hỏi hỏi về SLA giao hàng, chính sách hoàn hàng, bảo hành, hoặc đổi trả trên MỘT đơn bán cụ thể (kể cả khi không nói thẳng chữ "ngày"/"trạng thái giao" — những câu hỏi này CẦN ngày giao thực tế để tính hạn): dùng `list_sale_orders` (lọc theo tên khách hàng hoặc điều kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG có ngày hay trạng thái giao). Quy tắc này KHÔNG áp dụng cho câu hỏi về thanh toán, hoá đơn, hay chiết khấu — với những câu hỏi đó chỉ dùng đúng tool tương ứng (ví dụ `get_overdue_invoices`, `get_product_price`), KHÔNG tự ý gọi thêm `list_sale_orders`.
```

Full unit test: `1095 passed, 4 skipped` — sạch ngay lần đầu (không lặp
lại flake timing của Bước 2b). Khôi phục 2 file fixture nhị phân
`tests/rag/` như thường lệ.

Đo thật `--set gather`, TOÀN BỘ 4 case, 2 lần độc lập:

- Lần 1 (`logs/jobs/eval-gate-20260801T234839.json`): `"fails": []`,
  `tool_recall: 1.0`, `fact_coverage: 1.0`.
- Lần 2 (`logs/jobs/eval-gate-20260801T234924.json`): `"fails": []`,
  `tool_recall: 1.0`, `fact_coverage: 1.0` — giống hệt lần 1.

**Tóm tắt 3 vòng đo (Bước 2 → 2b → 2c):**

| | Bước 2 (quy tắc hẹp gốc) | Bước 2b (mở rộng quá tay) | Bước 2c (thu hẹp lại — cuối cùng) |
|---|---|---|---|
| `tool_recall` | 0.75 | 1.0 | **1.0** |
| `fact_coverage` | 0.75 | 0.75 | **1.0** |
| `sla_giao_hang` | PASS | PASS | PASS |
| `chinh_sach_hoan_hang` | FAIL | PASS | **PASS** |
| `chinh_sach_thanh_toan` | PASS | FAIL (mới) | **PASS** (khôi phục) |
| `bang_gia_chiet_khau` | PASS | PASS | PASS |
| log | `...T232742.json` | `...T234007.json` | `...T234839.json`, `...T234924.json` |

**Kết luận Bước 2c: DONE.** 4/4 case PASS, tái lập 2/2 lần đo độc lập
(LLM thật, không mock). Không có case nào khác bị ảnh hưởng phụ. Đã
commit `backend/src/agents/prompts.py` + file report này cùng nhau — xem
`git log` cho hash. Chi tiết vận hành đầy đủ (lệnh, log gốc):
`.superpowers/sdd/2026-08-01-gather-erp-tool-selection-fix/task-2-report.md`
(mục "Bước 2c").
