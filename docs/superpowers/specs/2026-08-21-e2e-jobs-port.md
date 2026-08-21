# Port 4 job `e2e_*` — đóng nợ SP-1C1 Bước 8

**Ngày**: 2026-08-21 · **Mục** #2 trên `docs/trang-thai-chung.md`, nợ **cũ nhất**
trên bảng.

## 1. Đề bài thật khác hẳn dòng trên bảng

Bảng ghi "4 job `e2e_*` chưa port". Đọc kỹ thì bốn tệp job chỉ ~65 dòng mỗi cái;
thứ chúng bọc — **4 script live-verify, ~717 dòng** — mới là phần chưa có. Dòng
mô tả ngầm hiểu đây là việc chép tệp, thực tế là port cả tầng dưới.

Và trong lúc khảo sát tìm ra **một lỗi tiềm ẩn có thật**: `live_verify_common.py`
đã được port sang Youdoo từ SP-1B, nhưng

- nó **mồ côi** — người dùng duy nhất là test đơn vị của chính nó, trong khi
  docstring khai nó phục vụ ba script skill không tồn tại ở đây;
- `chat()` **không gửi header vai**, mà backend Youdoo suy vai từ
  `x-openwebui-user-id` và **từ chối** khi thiếu (`main._role_from_headers` trả
  None ⇒ "Không xác định được quyền truy cập của bạn").

Tức helper này **chưa từng chạy được** ở Youdoo. Lỗi nằm im vì không ai gọi nó.
Đây là lớp lỗi "code đã port nhưng chưa ai chạy" — họ hàng gần với
"danh sách khai báo mà không ai gác".

## 2. Những gì đã làm

| tệp | việc |
|---|---|
| `tests/live_verify_common.py` | thêm `role_user_id()` + `chat()` gửi header vai |
| `tests/live_verify_auto_chain.py` | **viết lại** (không chép) |
| `tests/live_verify_skill_{discount,delivery,warehouse}.py` | port, sửa đường import |
| `jobs/e2e_common.py` | **mới** — khung chung cho cả bốn job |
| `jobs/e2e_{smoke,skill_discount,skill_delivery,skill_warehouse}.py` | mỗi tệp ~8 dòng khai báo |
| `jobs/__main__.py` | đăng ký bốn job |
| `tests/jobs/test_cli.py` | **bỏ `@pytest.mark.skip`** |
| `tests/jobs/test_e2e_jobs.py` | **mới** — 12 test gác tầng khai báo |

### 2.1 Vì sao `e2e_common.py` chứ không phải bốn bản sao

Bản gốc lặp `_preflight` gần như từng chữ trong **bốn** tệp và
`_extract_result_json` trong **ba**. Chúng không bất biến theo thời gian: cổng
backend đã đổi 8000→8002 một lần rồi (spec `2026-08-05-cross-project-port-collision-fix`),
và mỗi lần đổi là bốn chỗ phải nhớ sửa. Gom lại là **sửa gốc**, không phải dọn
thẩm mỹ.

`preflight()` đọc `BACKEND_PORT`/`MCP_ODOO_PORT` từ môi trường thay vì ghim
cứng — vì `live_verify_common` đã đọc `BACKEND_PORT`, nên job ghim một cổng khác
sẽ báo *"backend không chạy"* trong khi script con lại gọi đúng chỗ. **Một chẩn
đoán sai còn tệ hơn không có chẩn đoán.**

### 2.2 Vì sao `live_verify_auto_chain.py` được VIẾT LẠI

Bản gốc là mã nháp, và ba chỗ của nó không dùng lại được:

1. Tự chế `chat()`, ghim cứng `:8000`, không gửi header vai.
2. Tự đặt `sys.stdout = io.TextIOWrapper(...)` — Youdoo đã có
   `src.cli_console.use_utf8_streams()` làm đúng việc đó cho cả bảy cửa vào CLI;
   dựng thêm bản riêng là dựng lại đúng thứ vừa được gom.
3. **Không phát `RESULT_JSON`**, nên job bọc nó chỉ đọc được `returncode` trong
   khi ba job kia đọc được từng kịch bản. Nay cả bốn cùng một khuôn.

Về **nội dung kiểm**, bản gốc so khớp nguyên văn `"Sau đó tự động: Xác nhận báo
giá"` và `"Xác nhận? (có / không)"`. Chuỗi thứ hai **không tồn tại** trong mã
Youdoo; chuỗi thứ nhất ghép từ nhãn trong `write_registry.NEXT_STEPS`. Nên nhãn
nay được **suy từ chính bảng đó** — đổi nhãn trong registry thì script đi theo,
thay vì đỏ vì một lý do không liên quan. Vị trí chain_note neo vào dấu `?` cuối
cùng thay vì một câu hỏi nguyên văn.

### 2.3 Hai giả định ghim cứng của bản gốc — đã KIỂM, không đoán

`live_verify_skill_discount.py` ghim `PARTNER_ID=15`, `PRODUCT_ID=20`,
`UNIT_PRICE=320.0`, verify trên Odoo của `D:\Project`. Youdoo dùng **database
khác**, nên đã đọc trực tiếp qua XML-RPC trước khi chạy:

    partner 15 → Azure Interior (customer_rank=13)          ✓
    product 20 → [E-COM07] Large Cabinet, list_price 320.0  ✓
    "Kìm điện cách điện" (kịch bản no_po) → id 112          ✓

Trùng khớp vì hai Odoo cùng gốc dữ liệu demo. **May, nhưng đã kiểm** — nếu lệch
thì ba kịch bản discount sẽ đỏ vì lý do không liên quan tới skill.

## 3. Test bị skip có sẵn MỘT LỖI TRONG CHÍNH NÓ

`test_cli_survives_redirected_cp1252_stdout` chạy `python -m jobs …` với
`cwd=REPO_ROOT`. Ở Youdoo gói `jobs` nằm dưới `backend/`, nên lệnh trả
*"No module named jobs"*. Test skip cứng **từ lúc được viết cho tới hôm nay**,
nên chưa ai từng chạy nó, nên chưa ai thấy lỗi này.

Đáng ghi lại vì nó là hệ quả trực tiếp của việc *ghi bài học thành test rồi tắt
đi*: lớp lỗi cp1252 sau đó cắn **lần thứ hai** ở `evals/run_eval.py` (2026-08-21)
mà cổng chặn dành riêng cho nó đang tắt — và bản thân cổng đó cũng hỏng.

## 4. Rào mới, và một rào cũ đã bắt được tôi

`tests/jobs/test_e2e_jobs.py` gác tầng khai báo: bốn job đăng ký đủ, **không job
nào `schedulable=True`**, bảng `E2E_MODULES` khớp **hai chiều** với `JOBS`
(không so với danh sách cứng — thêm job thứ năm mà quên sẽ bị bắt), mọi module
được trỏ tới đều import được và có `main()`.

Một quyết định dễ bị "sửa" nhầm, nên có test riêng: **không suy `PASS` từ
`returncode == 0` khi thiếu `RESULT_JSON`**. Script chết trước lúc chấm điểm vẫn
có thể thoát 0; suy PASS từ đó là biến một job hỏng thành một job xanh — đúng
kiểu hỏng im lặng mà bốn job này sinh ra để bắt.

**Rào cũ bắt được tôi**: `test_khong_ro_loi_exception` chặn `e2e_common.py` vì
`preflight()` nhúng nguyên văn lỗi socket. Đã khai miễn trừ **kèm lý do và kèm
số đếm** (3 regex / 3 AST — thêm chỗ rò mới vẫn bị bắt), theo đúng tiền lệ đã có
cho `jobs/resilience.py` và `evals/run_eval.py`: đây là console của người vận
hành và `logs/jobs/*.json`, không bao giờ vào hội thoại, và nguyên văn lỗi socket
**chính là** chẩn đoán cần đọc.

## 5. Nghiệm thu sống

Chạy thật trên stack sống (backend :8002, MCP :8003, write-toggle Odoo bật).
Mọi lượt đều tạo bản ghi THẬT trong Odoo.

| job | kết quả | ghi chú |
|---|---|---|
| `e2e-smoke` | **PASS 3/3** (148s) | chain_note đúng chỗ, tự chạy tới bước `Giao hàng`, ca một-bước không sinh chain_note |
| `e2e-skill-discount` | **PASS 3/3** (111s) | `price_unit` 304,0 (−5%) và 288,0 (−10%); ca từ chối không tạo quotation |
| `e2e-skill-delivery` | **PASS 3/3** (135s) | sau khi sửa câu mở đầu (§5.1) và đổi khoá (§5.2) |
| `e2e-skill-warehouse` | **PASS 5/5** (296s) | gồm `no_po_tool_leak` và `refusal`, cả hai từng đỏ |

**14/14 kịch bản đạt.**

Cả bốn job từ chối `--scheduled` với exit 2, không chạm mạng.

### 5.1 Nghiệm thu bắt được MỘT LỖI TRONG CHÍNH BẢN PORT

`e2e-skill-delivery` lượt đầu đỏ ở `draft_order_refused` với *"lộ tool name:
['deliver_order']"*. Chuỗi đường dẫn tới kết luận đúng mất bốn bước, và **hai
bước giữa tôi kết luận sai**:

1. Cơ chế chống lộ (`tool_leak_guard`) có thật và có chạy — nhưng docstring của
   `agentic_context_sync` khai sẵn một khoảng hở **cố ý không vá**: câu hỏi đang
   treo ở `interrupt` không đi qua node scrub. Có vẻ khớp.
2. Lấy văn bản thật ra thì dòng lộ là `(deliver_order: order_ref=S00180)` —
   **khuôn máy sinh**, không phải model lỡ miệng. Nguồn: `nodes.py:475-479`,
   kèm chú thích *"Invariant C tầng 3: hiện tool+args TẤT ĐỊNH — user luôn thấy
   ref thật trước khi 'có'"*. Tức **hai bất biến cố ý mâu thuẫn nhau**.
3. Tôi kết luận skill `giao-hang` không được chọn, và gọi đó là lỗi định tuyến.
   **SAI.** Bộ eval `sop_select` của chính repo bác:

       "làm quy trình giao hàng cho đơn bán S00012" → giao-hang,  full_sop
       "giao hàng cho đơn S00040 luôn nhé"          → erp_write,  one_step

   Youdoo tách **miền** khỏi **độ sâu**; câu trần là one-step tầng 1 theo đúng
   thiết kế. Tôi đọc mô tả *miền* trong `SKILL.md` rồi phát biểu về *độ sâu* —
   đúng cái nhầm mà bản tách đó sinh ra để chống.
4. Lỗi thật: **câu mở đầu trong bản port của tôi**. Bản gốc ở `D:\Project` chưa
   có tách độ sâu nên câu trần vào skill; ở đây nó vào tầng 1, và job mang tên
   *"E2E skill agentic: giao-hang"* thực ra đo tầng 1. Hai kịch bản PASS cũng
   pass **vì lý do sai** — chúng chỉ khẳng định trạng thái Odoo, thứ tầng 1 cũng
   làm được.

Sửa câu mở đầu về dạng `full_sop` ⇒ `draft_order_refused` **PASS**. Đối chiếu
lại cả ba script: `warehouse` vốn đã dùng đúng câu; `discount` chứng minh bằng
kết quả (chiết khấu theo cấp khách chỉ skill mới tính được).

**Bất biến C vs chống-lộ-tool vẫn là mâu thuẫn chưa giải** — nó chỉ không còn
lộ ra ở đây vì đường skill dùng mẫu xác nhận riêng. Dòng y hệt tồn tại ở
`D:\Project`, nên đây không phải hồi quy của Youdoo.

### 5.2 Ba kịch bản còn lại: CẠN HẠN MỨC, và nó suy giảm CHẤT LƯỢNG chứ không chỉ gây lỗi

Lượt đầu, `refusal` (cả hai job) trả `ERROR_MSG`; log backend cho `ChainExhausted`
vai `planner`, cả bốn mắt xích cooldown, 429 ghi `PerDayPerProjectPerModel`.

**Hạn mức ngày của Google là cửa sổ TRƯỢT 24h, không phải mốc nửa đêm.** Probe
trực tiếp bằng API trần trên chính khoá đã báo cạn: `gemini-3.1-flash-lite` trả
**200**, còn `gemini-3.5-flash-lite` vẫn 429 `PerDay`. Tức chỗ trống nhỏ giọt
quay lại khi lượt cũ rơi khỏi cửa sổ — "cạn ngày" KHÔNG có nghĩa phải chờ tới
sáng, nhưng cũng KHÔNG đủ để chạy một job 5 kịch bản.

Chủ dự án cấp ba khoá (ba project ⇒ **ba ví riêng**). Đổi khoá chính sang khoá
còn nguyên rồi chạy lại: **cả hai job PASS trọn**.

⚠️ **PHÁT HIỆN QUAN TRỌNG NHẤT CỦA ĐỢT NÀY — và nó bác một dự đoán của tôi.**
Tôi lập luận rằng đổi khoá sẽ chữa `refusal` (đỏ vì `ERROR_MSG`) nhưng **không**
chữa `no_po_tool_leak`, vì kịch bản đó chạy đủ 3 lượt, không lỗi, chỉ thiếu câu
bridge mà SOP dặn — nghe như lỗi hành vi. **Đổi khoá xong nó PASS.**

Cơ chế: cạn hạn mức không làm lượt gọi chết, nó làm lượt gọi **TỤT xuống mắt
xích yếu hơn**. Model yếu vẫn trả lời trôi chảy nhưng bỏ qua một chỉ dẫn trong
SOP. Nhìn từ ngoài, thứ đó **không phân biệt được với một lỗi hành vi thật**.

⇒ **Mọi kết quả eval/nghiệm thu chạy trong lúc hạn mức suy giảm đều không đáng
tin — kể cả những lượt đỏ trông như lỗi chất lượng, không chỉ những lượt đỏ vì
lỗi.**

### 5.3 Hệ quả đã cài đặt: RESULT_JSON mang theo model đã phục vụ

`live_verify_common.chat()` nay gom trường `model` của phản hồi (thứ mới có từ
đợt model-picker sáng cùng ngày) vào `MODELS_DA_PHUC_VU`, và `print_result` phát
nó ra `RESULT_JSON["models"]`. Nhờ vậy một lượt đỏ **tự nó nói được** "đỏ vì suy
giảm" hay "đỏ vì hành vi", thay vì bắt người đọc đoán như tôi vừa phải làm.

Thông tin này trước đó **có sẵn mà bị vứt đi** — script chỉ đọc `content`.

## 6. Khó khăn / giới hạn còn lại

**Khó khăn thật sự gặp**

- Đề bài trên bảng nhỏ hơn thực tế 10 lần (4 tệp job → 4 script + 1 khung chung
  + sửa helper + sửa test).
- `live_verify_common.py` đã port từ SP-1B nhưng **chưa từng chạy được** ở đây
  (thiếu header vai). Code đã port mà chưa ai chạy = code chưa tồn tại.
- Test bị skip có sẵn lỗi trong chính nó (`cwd=REPO_ROOT`).
- **Bốn** lần suýt kết luận sai trong một phiên: khoảng hở scrub, "lỗi định
  tuyến", "306 lượt" (số đọc từ một sổ vừa bị chính bộ test tích hợp xoá), và
  "đổi khoá không chữa được `no_po_tool_leak`" (§5.2). Ba trong bốn cái đều do
  **suy từ dấu hiệu gián tiếp thay vì lấy dữ liệu thật ra xem**.
- Bẫy `cwd`: `python -m jobs` phải chạy từ `backend/`. Cắn ba lần trong một
  ngày (test bị skip, và hai lần ở chính tôi) vì thông điệp "No module named
  jobs" trông giống "chưa cài" chứ không giống "đứng sai chỗ". Đã ghi vào
  `e2e_common.py`.

**Hướng đã chọn**

- Gom `preflight`/`extract_result_json` về `e2e_common` thay vì bốn bản sao.
- Suy nhãn/câu kích hoạt **từ nguồn sự thật trong repo** (`write_registry.NEXT_STEPS`,
  `SOP_SELECT_CASES`) thay vì ghim chuỗi của repo nguồn.
- Không suy `PASS` từ `returncode == 0` khi thiếu `RESULT_JSON`.

**Giới hạn còn lại**

- ~~3/14 kịch bản chưa nghiệm thu~~ → **ĐÃ ĐÓNG**, 14/14 đạt sau khi đổi khoá.
- Mâu thuẫn Invariant C ↔ chống-lộ-tool: **chưa giải**, chỉ chưa lộ ra.
- `or-nemotron` **chết** (bảng chung mục 10): 16 lần gọi, 0 thành công.
- Bộ test tích hợp **xoá sổ ngân sách** (bảng chung mục 9).
- `discount` vẫn ghim `PARTNER_ID`/`PRODUCT_ID`; đã kiểm đúng trên Odoo của
  Youdoo hôm nay, nhưng một lần reset dữ liệu demo là hỏng.
