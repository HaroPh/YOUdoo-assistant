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
`.superpowers/sdd/2026-08-01-gather-erp-tool-selection-fix/task-2-report.md`
(gitignored).

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
(gitignored) (mục "Bước 2b").

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
lại flake timing của Bước 2b). Chạy `git checkout --` cho 2 file fixture
nhị phân `tests/rag/` theo thói quen phòng ngừa sau khi chạy test (không
có `git status` ghi lại tại thời điểm đó xác nhận 2 file này có thực sự bị
đổi hay không — đây là lượt chạy test KHÁC với lượt ở mục "Xác minh test"
phía dưới, nơi `git status` được ghi lại tường minh và cho kết quả sạch;
hai kết quả không mâu thuẫn nhau, chỉ là hai lần chạy khác nhau, xem chú
thích ở đó).

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
(gitignored) (mục "Bước 2c").

## Bước 3 — `multi_source` thật (thước đo cuối cùng)

Chạy đúng lệnh brief Task 3 Step 1
(`cd backend && set -a && source ../.env && set +a && PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -m jobs run eval-gate --set multi_source`), model
`gemini-3.1-flash-lite` (không truyền `--model`), **KHÔNG sửa code gì thêm**
(`cases.py`, `prompts.py` giữ nguyên trạng thái đã commit ở Bước 1/2c).

- verdict: **`PASS`** — nhưng gate `multi_source` là điều kiện SÀN, không
  phải "phải tăng": `jobs/eval_gate.py:82`,
  `result["both_source_coverage"] >= base["both_source_coverage"]`. `0.75 >=
  0.75` → PASS. PASS ở đây nghĩa là "không tệ đi", KHÔNG có nghĩa là "đã sửa
  xong 2 ca mục tiêu".
- `both_source_coverage`: **`0.75`** (TRƯỚC, SP-2b report: `0.75`) — **KHÔNG
  đổi, dù đã cộng thêm 4/4 case `gather` PASS ở Bước 2c**.
- `citation_validity`: `1.0`
- `fabricated_number`: `0`
- `lat_p50` / `lat_p95`: `989` / `1454` ms
- log gốc: `logs/jobs/eval-gate-20260801T235708.json`
- 2 ca fail hiện tại (nguyên văn từ log):
  1. `sla_giao_hang` / "Đơn S00042 có đáp ứng SLA giao hàng không?" —
     `both: false`, `citation_ok: true`, `fabricated: []`. Response: "...dữ
     liệu này không cung cấp thông tin về ngày xác nhận đơn hàng, ngày giao
     hàng thực tế hoặc loại đơn hàng... để đối chiếu với quy định về thời
     gian giao hàng."
  2. `chinh_sach_hoan_hang` / "Hóa đơn INV/2026/00017 có được hoàn tiền
     không?" — `both: false`, `citation_ok: true`, `fabricated: []`.
     Response: "...tôi chưa thể khẳng định hóa đơn INV/2026/00017 có được
     hoàn tiền hay không..."

### Vì sao KHÔNG đổi — bằng chứng mã nguồn, không suy đoán

Hai phát hiện độc lập, cả hai đều xác minh được từ mã nguồn (không phải
suy luận):

**(A) `eval_multi_source()` không hề gọi `gather_erp`/`GATHER_ERP_PROMPT`.**
Đọc `backend/evals/run_eval.py:590-657`: hàm `call()` bên trong lấy
`erp_block` — trường **viết tay, cố định** của mỗi case trong
`MULTI_SOURCE_CASES` — rồi truyền THẲNG làm `erp_facts` cho
`render_fuse_input()` (dòng 605-609), gọi `FUSE_PROMPT` một lượt duy nhất.
Không có `make_gather_erp_node`, không `bind_tools`, không vòng lặp
ReAct nào được thực thi. Đây không phải khoảng trống mới phát hiện — chính
`eval_gather()` (hàm được sửa ở Task 1) tự ghi rõ trong docstring của nó
(`run_eval.py:230-233`):

> "Đo bước THU THẬP của gather_erp — multi_source đo bước TỔNG HỢP trên
> erp_block viết tay, KHÔNG đo được liệu gather_erp thật có lấy đủ field
> hay không (spec 2026-08-01-sp2c)."

Nói cách khác: **quy tắc mới thêm vào `GATHER_ERP_PROMPT` ở Task 2 không
có đường dẫn cơ học nào để ảnh hưởng tới điểm `both_source_coverage`** —
eval này được thiết kế (từ SP-2c, trước plan này) để đo bước FUSE trên dữ
liệu ERP đã đóng băng, tách biệt hoàn toàn khỏi việc `gather_erp` chọn tool
nào. Đối chiếu git diff `b9fef00` (Task 1): chỉ `GATHER_CASES` bị sửa,
`MULTI_SOURCE_CASES` — bao gồm đúng `erp_block` của 2 case đang fail ở
trên — **0 dòng thay đổi** trong suốt cả plan này.

**(B) Ca mục tiêu thứ hai của plan (`chinh_sach_hoan_hang`) không khớp với
ca đang fail thật trong `multi_source`.** Đối chiếu `MULTI_SOURCE_CASES`
(`backend/evals/cases.py:409-414`), topic `chinh_sach_hoan_hang` có 2 case:
`"Đơn S00042 còn được hoàn hàng theo chính sách không?"` (đơn S00042) và
`"Hóa đơn INV/2026/00017 có được hoàn tiền không?"` (hoá đơn, KHÔNG phải
đơn S00042). Case đơn S00042 **KHÔNG nằm trong `fails`** — nó PASS, cả ở
lần đo này lẫn ở báo cáo SP-2b gốc
(`docs/superpowers/plans/2026-08-01-sp2b-read-fanout-report.md:286-292`,
nơi 2 ca fail baseline `0.75` được liệt kê tường minh là
`sla_giao_hang`/"Đơn S00042 có đáp ứng SLA giao hàng không?" và
`chinh_sach_hoan_hang`/"Hóa đơn INV/2026/00017 có được hoàn tiền không?").
Case `chinh_sach_hoan_hang` mà `GATHER_CASES` (Task 1) sửa lại dùng câu hỏi
**"Đơn S00042 còn được hoàn hàng theo chính sách không?"** — đúng chữ,
đúng topic, nhưng là case KHÔNG fail trong `multi_source` (cả trước và sau
plan này). Ca thật đang fail (hoá đơn INV/2026/00017) chưa từng được
`GATHER_CASES` hay bất kỳ phần nào của plan này chạm tới.

**Tóm lại:** trong 2 ca fail hiện tại của `multi_source`, đúng 1 ca
(`sla_giao_hang`) khớp câu hỏi với case mục tiêu gốc của plan — nhưng ngay
cả case này cũng không thể đổi kết quả vì lý do (A). Ca còn lại
(`chinh_sach_hoan_hang`/hoá đơn) chưa từng là mục tiêu sửa của
`GATHER_CASES` — chữ "2 ca mục tiêu" trong khung đo Bước 3 của brief, khi
đối chiếu ngược với chính log gốc SP-2b, hoá ra chỉ khớp câu hỏi 1/2 với
plan này. Văn bản `response` của ca `sla_giao_hang` ở log lần này gần như
nguyên văn với mô tả hồi quy gốc bị xoá khỏi comment `cases.py` ở Task 1
(git diff `b9fef00`: "...nói 'không cung cấp thông tin về ngày xác nhận
đơn hàng, ngày giao hàng thực tế' rồi từ chối kết luận") — nhất quán với
việc `erp_block` của case này chưa từng bị đổi.

## Xác minh test

- Unit-only (`pytest -m "not integration and not live"`): **`1095 passed,
  4 skipped, 43 deselected`**.
- Integration (`pytest -m integration`): **`27 passed, 1115 deselected`**.
- 2 file fixture nhị phân (`tests/rag/fixtures/bang_gia.xlsx`,
  `policy.docx`): `git status` sau cả 2 lượt chạy (unit-only, integration)
  ở Bước 3 này — sạch, không bị đổi, không cần `git checkout --`. (Đây là
  lượt chạy test KHÁC với lượt ở Bước 2c phía trên, nơi `git checkout --`
  được chạy theo thói quen phòng ngừa mà không có `git status` ghi lại —
  hai đoạn không mâu thuẫn, chỉ phản ánh 2 lần chạy test riêng biệt, có
  thể cho kết quả khác nhau.)
- Đối chiếu `git diff main..HEAD --stat` (toàn bộ 6 commit của plan): chỉ
  `backend/evals/cases.py`, `backend/src/agents/prompts.py`, và file report
  này bị đổi. `graph.py`, `fanout.py`, `state.py`, mô tả 25 tool dùng chung
  (`erp_query/tools.py`) — **0 dòng thay đổi**.

## Kết luận

> **Đính chính (2026-08-02):** lỗ hổng mô tả trong cảnh báo dưới đây ĐÃ
> được vá — xem
> `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`.
> `get_sale_order_detail` giờ đọc thêm `date_order`/`delivery_status`, và
> quy tắc `GATHER_ERP_PROMPT` mô tả bên dưới (khiến model tránh dùng
> `get_sale_order_detail` cho câu hỏi cần ngày) đã bị BỎ HẲN — không còn
> đúng ở prompt hiện tại. Đoạn dưới đây giữ nguyên làm hồ sơ lịch sử của
> phát hiện gốc.

**CẢNH BÁO QUAN TRỌNG — đọc trước khi xem 6 điều dưới đây:** bằng chứng đã
đo được trong chính report này (mục "Điều tra thêm của controller — chẩn
đoán trực tiếp qua Odoo thật (sau Task 3)" ở dưới) cho thấy bản sửa này CÓ
THỂ làm production TỆ HƠN — không chỉ "chưa đủ tốt" — cho đúng lớp câu hỏi
plan này nhắm sửa: câu hỏi hỏi về một đơn bán CỤ THỂ bằng MÃ ĐƠN (ví dụ
"S00042"), không kèm tên khách hàng. Nối lại 4 sự kiện đã có sẵn nhưng rời
rạc trong report:

(a) Người dùng gọi đơn bán bằng MÃ ĐƠN (ví dụ "S00042"), không phải tên
khách hàng — đây chính là hình dạng của cả 2 case mục tiêu gốc của plan.
(b) `list_sale_orders` (`backend/src/erp_query/sales.py:24-46`) KHÔNG có
tham số tìm theo mã đơn — chỉ lọc theo `state`/`customer`/`date_from`/
`date_to`.
(c) `backend/src/erp_query/tools.py` có `_reject_ref_shaped_partner_names`
(khoảng dòng 16-24, áp dụng cho mọi tool qua `build_erp_query_tools()`
dòng ~222) — CHẶN CỨNG (raise lỗi validation) khi model gọi
`list_sale_orders(customer="S00042")`, vì giá trị đó CÓ HÌNH DẠNG mã đơn,
bị coi là model gán nhầm mã tham chiếu vào tham số tên.
(d) `get_sale_order_detail` là con đường DUY NHẤT tra được mã đơn → tên
khách hàng (`sales.py:49-68`, tìm theo `name = ref`), nhưng quy tắc prompt
mới ("KHÔNG dùng `get_sale_order_detail` cho việc này") lại bị model đọc
theo nghĩa đen là cấm hoàn toàn dùng tool đó cho câu hỏi này — nên model bỏ
qua bước tra tên khách hàng cần thiết.

Kết quả quan sát được (đã ghi nguyên văn ở mục điều tra bên dưới): với câu
hỏi S00042/SLA giao hàng, kết quả cuối là `ERP_GROUNDING_FALLBACK_MSG` —
TOÀN BỘ câu trả lời bị thay bằng "Xin lỗi, tôi không chắc chắn...". TRƯỚC
khi có bản sửa này, `gather_erp` (dù chọn sai tool `get_sale_order_detail`)
ít nhất còn trả về được tên khách hàng/trạng thái/tổng tiền — CÓ dữ kiện,
dù thiếu ngày. SAU khi sửa: KHÔNG CÒN dữ kiện nào cả (fallback trắng). Đây
là dấu hiệu REGRESSION THẬT trên đúng lớp câu hỏi plan nhắm sửa, không chỉ
đơn thuần "chưa đủ để giải quyết" như điều 4 dưới đây diễn đạt.

`gather` (bộ đo eval, báo 4/4 PASS) KHÔNG phát hiện được vì `_stub_erp_tools`
(`backend/evals/run_eval.py`) trả cố định fixture text BẤT KỂ tham số gọi
tool là gì — kể cả gọi `list_sale_orders(customer="S00042")` (dạng lẽ ra bị
`_reject_ref_shaped_partner_names` chặn khi dùng tool thật), stub vẫn trả
đúng dòng S00042 như không có chuyện gì. Bộ đo `gather` vì vậy chỉ đo được
"model có gọi đúng TÊN tool hay không", KHÔNG đo được "tham số gọi tool có
hợp lệ/tìm ra đúng bản ghi với dữ liệu Odoo thật hay không" — đây chính là
lỗ hổng khiến 4/4 xanh trong khi production thật có thể tệ hơn trước bản
sửa.

Ghi nhận đúng mức độ nghiêm trọng ở đây — KHÔNG tự ý sửa thêm
`GATHER_ERP_PROMPT`: người dùng thật đã xem xét và quyết định chốt plan
như hiện tại, để lỗ hổng này cho phase sau xử lý (xem thêm khoảng trống
phủ kiểm thử đã nêu ở điều 4 dưới đây).

Đối chiếu từng điều của §5 "Xong nghĩa là"
(`docs/superpowers/specs/2026-08-01-gather-erp-tool-selection-design.md`):

1. **`GATHER_ERP_PROMPT` có quy tắc chọn tool mới (§2). ĐẠT.**
   `backend/src/agents/prompts.py:152` có quy tắc cuối cùng (bản thu hẹp,
   Bước 2c) — xem `git log` commit `54accc5`.
2. **2 case `GATHER_CASES` phản ánh đúng khả năng thật của tool, test
   tự-nhất-quán vẫn PASS. ĐẠT.** Commit `b9fef00`; test suite lần này (mục
   "Xác minh test" ở trên) chạy sạch `1095 passed`, bao gồm
   `test_gather_cases_required_facts_exist_in_fixtures` và
   `test_gather_cases_required_tools_are_real_erp_tool_names`.
3. **Số đo TRƯỚC (FAIL) và SAU (PASS) của `gather` đều ghi vào báo cáo,
   TRƯỚC bắt buộc phải FAIL. ĐẠT.** Bước 1 (TRƯỚC: `tool_recall=0.75`,
   `chinh_sach_hoan_hang` FAIL đúng kỳ vọng) → Bước 2/2b/2c (SAU cuối cùng:
   `tool_recall=1.0`, `fact_coverage=1.0`, `"fails": []`, 2 lần đo độc
   lập).
4. **`multi_source` đo lại thật, `both_source_coverage` không tệ hơn 0.75
   và lý tưởng tăng lên. ĐẠT PHẦN SÀN, KHÔNG ĐẠT PHẦN LÝ TƯỞNG — nói
   thẳng, không suy diễn thêm.** Số đo SAU = `0.75`, bằng hệt TRƯỚC —
   không tệ đi (đạt điều kiện gate), nhưng cũng không tăng. **2 ca mục
   tiêu gốc của toàn bộ plan (nêu ở Bối cảnh của spec, lấy từ SP-2b report)
   VẪN còn trong `fails`, KHÔNG hết** — đây là điểm khác với kịch bản brief
   dự trù ("dù 2 ca mục tiêu đã hết"): thực tế 2 ca mục tiêu CHƯA hết, và
   có bằng chứng mã nguồn (mục "Vì sao KHÔNG đổi" ở trên, phát hiện A) cho
   thấy chúng **không thể hết được bằng cách sửa `GATHER_ERP_PROMPT`**, vì
   `eval_multi_source()` không đi qua node đó — đây là giới hạn kiến trúc
   của chính bộ đo `multi_source`, không phải bug mới hay lỗi thực thi của
   plan này. Không suy diễn xa hơn: KHÔNG có bằng chứng nào trong phạm vi
   đo được của plan này (chỉ gồm `gather` và `multi_source`, không chạy
   graph thật end-to-end qua Odoo sống) để khẳng định hay phủ nhận việc
   sửa `GATHER_ERP_PROMPT` có cải thiện hành vi PRODUCTION thật (nơi
   `fuse_answer` nhận đầu vào thật từ `gather_erp`, không phải `erp_block`
   đóng băng) hay không — câu hỏi đó nằm ngoài những gì 2 bộ đo hiện có
   (`gather`, `multi_source`) có thể trả lời.
5. **2/2 chế độ pytest brief Task 3 Step 2 yêu cầu (unit-only,
   integration) — ĐẠT, sạch.** Unit-only: `1095 passed, 4 skipped`.
   Integration: `27 passed`. (Brief chỉ liệt kê đúng 2 lệnh pytest này.)

   Ngoài phạm vi brief, controller ĐÃ THỬ thêm chế độ `-m live` cho đúng
   test liên quan chủ đề nhất — `backend/tests/agents/test_dau_cuoi_fanout.py`
   (câu hỏi trong test: "Theo chính sách hoàn hàng, đơn S00042 còn hoàn
   được không?" — đúng lớp câu hỏi plan này sửa):
   `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest
   tests/agents/test_dau_cuoi_fanout.py -m live -v` (từ `backend/`, sau khi
   export `.env`) — **FAILED**: `httpx.ConnectError: All connection
   attempts failed`. Nguyên nhân: test này đi qua `ERPAgent` →
   `MultiServerMCPClient` → cần MCP Odoo server thật chạy ở
   `http://localhost:8001/sse` (`backend/src/agents/erp_agent.py:21,140`);
   service đó KHÔNG chạy trong worktree/môi trường này (đã xác nhận cổng
   8001 không nghe). Đây là THIẾU HẠ TẦNG cục bộ (không có server MCP),
   KHÔNG PHẢI lỗi của bản sửa — các chẩn đoán trực tiếp Task 1/2/3 trong
   plan này đều CỐ Ý bypass MCP, gọi thẳng `build_erp_query_tools()` qua
   XML-RPC thật (không cần MCP cho việc ĐỌC). Bằng chứng tương đương đã có:
   xem mục "Điều tra thêm của controller — chẩn đoán trực tiếp qua Odoo
   thật (sau Task 3)" bên dưới — vẫn phủ được cùng cơ chế thật (real
   `gather_erp` node, real Odoo), dù không đi qua đúng lớp MCP/audit mà
   test `-m live` này kiểm tra.
6. **`graph.py`, `fanout.py`, `state.py`, mô tả 25 tool dùng chung — 0 dòng
   thay đổi. ĐẠT.** Xác nhận bằng `git diff main..HEAD --stat` (mục "Xác
   minh test" ở trên).

**Tổng kết trung thực, không tô hồng:** plan này sửa đúng và sửa sạch một
lỗi thật ở tầng `gather_erp` (điều 1-3, 5, 6 đạt đầy đủ, đo bằng LLM thật,
tái lập nhiều lần, review sạch). Nhưng mục tiêu GỐC nêu ngay dòng đầu của
spec ("Sửa đúng nguyên nhân đã xác minh của 2 ca `multi_source` còn FAIL
từ trước SP-2b") **không đo được là đã đạt** — điều 4 chỉ đạt phần sàn.
Nguyên nhân không phải bản sửa sai, mà là **bộ đo `multi_source` được
thiết kế (từ trước plan này, ở SP-2c) theo cách tách rời khỏi chính node
mà plan này sửa**, nên không có cách nào để một thay đổi ở
`GATHER_ERP_PROMPT` phản ánh vào con số `both_source_coverage`, bất kể bản
sửa đó đúng hay sai. Đây là một khoảng trống phủ kiểm thử (test-coverage
gap) giữa `gather` và `multi_source` chưa từng được nêu ra trước — nằm
ngoài phạm vi brief Task 3 ("không sửa code thêm"), nên KHÔNG được đóng ở
đây, chỉ được đo và ghi nhận trung thực để controller/người dùng quyết
định bước tiếp theo (ví dụ: một task riêng nối `gather_erp` thật vào
`eval_multi_source()`, hoặc chấp nhận giới hạn đo hiện tại và xác minh
production bằng cách khác, ví dụ chẩn đoán trực tiếp qua Odoo thật như đã
làm ở §0 spec).

## Điều tra thêm của controller — chẩn đoán trực tiếp qua Odoo thật (sau Task 3)

Task 3 đã chỉ ra rằng `gather`/`multi_source` không thể trả lời câu hỏi
"bản sửa có cải thiện hành vi PRODUCTION thật hay không". Cách duy nhất
đo được điều đó — đúng như report đề xuất — là chẩn đoán trực tiếp qua
Odoo thật, giống hệt phương pháp đã dùng TRƯỚC khi viết plan này (script
tạm gọi thẳng `make_gather_erp_node` với tool thật, không stub, không
mock). Controller chạy lại đúng phương pháp đó, KHÔNG sửa code, KHÔNG
commit script, cho đúng 2 câu hỏi mà `multi_source` thật đang FAIL (nêu ở
mục "Vì sao KHÔNG đổi" phía trên):

**Câu hỏi 1 — `sla_giao_hang` / "Đơn S00042 có đáp ứng SLA giao hàng
không?"** (đây LÀ câu hỏi plan này nhắm sửa):

- `called` (tool thật, Odoo thật): `list_sale_orders` — ĐÚNG tool mới,
  quy tắc prompt CÓ ảnh hưởng thật tới hành vi production, không chỉ tới
  eval có stub.
- Nhưng kết quả cuối: `erp_facts` = thông báo fallback của
  `verify_erp_grounding` ("Xin lỗi, tôi không chắc chắn về độ chính xác
  của câu trả lời này..."). Vết đầy đủ (đọc trực tiếp từ
  `AIMessage`/`ToolMessage` thật, không suy đoán):
  1. `list_sale_orders(state="", customer="", date_from="", date_to="")`
     → trả về trang mặc định (đơn GẦN NHẤT: S00165, S00164, S00163...) —
     **KHÔNG có S00042** (đơn này cũ hơn nhiều so với trang mặc định).
  2. Model thử `list_sale_orders(customer="S00042")` — SAI cách dùng (đưa
     mã ĐƠN vào tham số dành cho tên KHÁCH HÀNG) → lỗi tool.
  3. Model gọi lại `list_sale_orders()` với bộ lọc rỗng lần nữa — cùng
     kết quả trang mặc định, vẫn không có S00042.
  4. Model bỏ cuộc: "Không tìm được dữ kiện ERP liên quan đến đơn hàng
     S00042" — câu này đúng theo quy tắc "nếu không lấy được dữ kiện,
     trả lời đúng một câu..." của `GATHER_ERP_PROMPT`, nhưng sau đó lại
     bị `verify_erp_grounding` thay bằng thông báo fallback khác.

  **Nguyên nhân gốc (bằng chứng, không suy đoán):** `list_sale_orders`
  (`backend/src/erp_query/sales.py:24-46`) CHỈ lọc theo `state`,
  `customer` (tên khách hàng), `date_from`, `date_to` — **KHÔNG có tham
  số tìm theo MÃ ĐƠN**. Chỉ `get_sale_order_detail(ref=...)`
  (`sales.py:49-68`) tìm được theo mã đơn, nhưng tool đó không có field
  ngày. Cách ĐÚNG để trả lời câu hỏi này là gọi `get_sale_order_detail`
  TRƯỚC để biết tên khách hàng (Azure Interior), RỒI gọi `list_sale_orders
  (customer="Azure Interior")` để tìm đúng dòng theo mã đơn trong kết quả
  — đây chính xác là cách `GATHER_CASES`' comment mô tả ("lọc theo tên
  khách hàng... tìm đúng dòng có mã đơn khớp"). Nhưng câu chữ hiện tại
  của quy tắc mới ("KHÔNG dùng `get_sale_order_detail` cho việc này")
  nhiều khả năng bị model (flash-lite, dễ đọc quy tắc theo nghĩa đen)
  hiểu thành "không dùng tool đó cho câu hỏi này" (cấm hoàn toàn), thay
  vì nghĩa dự định "không dùng tool đó LÀM NGUỒN LẤY NGÀY" — nên model bỏ
  qua bước tra cứu tên khách hàng cần thiết, mò mẫm với
  `list_sale_orders` không có bộ lọc và thất bại.

  **Vì sao `gather` (stub) đo được 4/4 PASS nhưng production thật vẫn
  thất bại ở câu hỏi này:** `_stub_erp_tools` (`evals/run_eval.py`) trả
  cố định đúng fixture text bất kể tham số gọi tool là gì — kể cả gọi
  `list_sale_orders()` KHÔNG lọc gì, stub vẫn trả đúng dòng S00042. Bộ đo
  `gather` vì vậy đo được "model có gọi đúng TÊN tool hay không"
  (`tool_recall`), nhưng KHÔNG đo được "model có tự xây được đúng THAM SỐ
  tìm kiếm để tìm ra đúng bản ghi hay không" — với dữ liệu Odoo thật (có
  hàng trăm đơn, phân trang, không tìm theo mã đơn được), đây lại chính
  là bước quyết định thành-bại.

**Câu hỏi 2 — `chinh_sach_hoan_hang` / "Hóa đơn INV/2026/00017 có được
hoàn tiền không?"** (đây KHÔNG phải câu hỏi plan này nhắm sửa — đã nêu ở
Finding B phía trên):

- `called`: `list_invoices` — đúng tool, KHÔNG liên quan gì đến quy tắc
  mới của Task 2 (câu hỏi về hoá đơn, không phải đơn bán).
- `erp_facts` trả về ĐẦY ĐỦ, đúng định dạng: mã hoá đơn, khách hàng, ngày
  hoá đơn (2026-07-18), tổng tiền, trạng thái thanh toán (paid). Bước
  `gather_erp` cho câu hỏi này **hoạt động đúng, không có vấn đề** —
  khớp với Finding B (case này chưa từng là mục tiêu sửa của plan, và quả
  thật không có gì để sửa ở tầng `gather_erp`). Nếu `multi_source` vẫn
  FAIL case này, nguyên nhân nằm ở bước KHÁC (tổng hợp `fuse_answer`, hoặc
  chính sách hoàn tiền trong tài liệu không đủ rõ) — ngoài phạm vi đo
  được của cả plan này.

**Kết luận của điều tra:** quy tắc prompt Task 2 **CÓ** thay đổi hành vi
chọn tool thật trong production (không chỉ trong eval có stub) — đây là
bằng chứng độc lập, mạnh hơn con số `gather` 4/4, rằng bản sửa chạm đúng
vào cơ chế thật. Nhưng bản sửa **CHƯA ĐỦ** để tự nó giải quyết câu hỏi
`sla_giao_hang`/S00042 trong production thật — model chọn đúng tool
nhưng không biết cách TRA CỨU đúng cách (thiếu bước trung gian lấy tên
khách hàng) khi Odoo có nhiều dữ liệu thật và tool không tìm được theo mã
đơn. Đây là một lỗi THẬT, cụ thể hơn phát hiện A/B của Task 3 (không phải
"bộ đo tách rời node" nữa, mà là "quy tắc prompt chưa hướng dẫn đủ bước
tra cứu trung gian"), phát hiện được NHỜ đo qua Odoo thật thay vì chỉ qua
stub. Theo đúng kỷ luật của cả plan này (Task 2 Step 4: phát hiện vấn đề
tầng `verify_erp_grounding`/liên quan thì CHỈ ghi nhận, KHÔNG tự sửa
thêm — đây đã là vòng sửa thứ 3 của Task 2, thêm một vòng nữa vượt phạm
vi Task 3 "không sửa code thêm"), controller KHÔNG tự sửa tiếp ở đây —
ghi nhận trung thực, để người dùng quyết định bước tiếp theo.
