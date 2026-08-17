# Báo cáo: đo thật + nghiệm thu sống — tách miền nghiệp vụ khỏi độ sâu ở tầng định tuyến SOP

Đo ngày 2026-08-17, sau khi Task 1-6 đã commit và review sạch (worktree
`sop-domain-depth-split`, HEAD `11928dd`). Model: `gemini-3.1-flash-lite`
(đầu chuỗi vai `router` production).

## ⚠️ KẾT LUẬN NGAY: `sop_select` CHƯA XANH

Mục tiêu Task 7 là đưa cổng `sop_select` về xanh lần đầu kể từ 2026-07-31.
**Không đạt.** `acc = 0.833` (20/24), `depth_acc = 0.833`, `hijack = 0`,
`errors = []`. Đo 2 lần độc lập (cách nhau ~5 phút, cùng 24 ca, cùng
model) ra **kết quả giống hệt nhau byte-for-byte** — đây không phải nhiễu
mô hình ngẫu nhiên, mà là một khoảng lệch ổn định, tái lập được.

4 ca trượt (cả 2 lần đo):

| # | Câu | Kỳ vọng (route/depth) | Đo được (route/depth) | raw_intent / raw_sop |
|---|---|---|---|---|
| 1 | "quy trình nhập kho cho đơn mua P00021" | nhap-kho / full_sop | rag / none | rag / null |
| 2 | "đơn mua P00021 vừa giao tới, làm nốt phần còn lại nhé" | nhap-kho / full_sop | erp_write / one_step | erp_write / nhap-kho |
| 3 | "báo giá kèm chiết khấu theo cấp khách cho Wood Corner, 10 Desk Pad" | bao-gia-chiet-khau / full_sop | erp_write / one_step | erp_write / bao-gia-chiet-khau |
| 4 | "Wood Corner mua 10 Desk Pad, tính giá cho khách này giúp tôi" | clarify_depth / unsure | erp_write / one_step | erp_read / bao-gia-chiet-khau |

**Ca #1 là ca hồi quy 2026-07-16 nổi tiếng nhất repo — nó đã QUAY LẠI.**
Spec/plan (commit `a688d1c`) tuyên bố spike vòng 3 đo được ca này "TỰ KHỎI
dù không nhắm tới nó". Đo thật ở Task 7 với đúng prompt (Task 2) và đúng
mô tả skill (Task 3) đã commit thì KHÔNG tự khỏi — router vẫn phân loại
"quy trình nhập kho cho đơn mua P00021" là câu hỏi VỀ quy trình (rag),
dù có mã đơn mua cụ thể P00021. Không rõ nguyên nhân lệch giữa phép đo
spike (script cô lập, không qua `evals/cases.py` đầy đủ) và phép đo Task 7
(qua đúng harness `eval_sop_select` với 24 ca cùng lúc) — cần một phiên
điều tra riêng, KHÔNG thử sửa trong task này (Task 7 không viết code
sản phẩm).

Ca #4 cũng đáng chú ý — nhưng **sửa lại một trích dẫn sai ở bản nháp
trước của báo cáo này**: comment "MƠ HỒ THẬT — đo 2026-08-16 tất định 3/3
lượt" trong `cases.py:665` gắn vào ca SONG SINH của nó
(`"kho báo hàng P00021 đã tới, cần làm gì tiếp"`, dòng 666), KHÔNG PHẢI
vào chính ca #4 — ca #4 (`cases.py:678`) mang comment riêng "NGỮ NGHĨA —
không chữ 'chiết khấu'" (dòng 676-677). Cả hai ca cùng thuộc nhóm
depth="unsure" mà đặc tả `2026-08-16-sop-domain-depth-split-design.md`
(dòng 129, 290) mô tả chung là "2/18 ca (11%) mơ hồ thật... tất định 3/3
lượt" ở mức SPIKE, không phải một comment riêng cho từng ca trong
`cases.py`. Kết luận thực chất không đổi: Task 7 đo lại thì ca song sinh
("kho báo hàng...") vẫn đúng `clarify_depth/unsure` ở cả JSON eval lẫn
kịch bản sống #3 dưới đây, còn ca #4 rơi thẳng về `erp_write/one_step`
(bỏ qua hỏi lại) cả 2 lần đo — trong 2 ca thuộc nhóm "mơ hồ thật" của
spike, chỉ 1 còn đúng ở Task 7.

3 ca có ghi chú "kỳ vọng theo số đo spike, không theo mong muốn" trong
`cases.py` (`"đơn S00012 đóng gói xong rồi..."`, `"khách giục..."`,
`"hàng của đơn mua P00021 về rồi..."`) **ĐỀU ĐÚNG** — không nằm trong danh
sách trượt. Ca #2 ở trên (`"đơn mua P00021 vừa giao tới..."`) KHÔNG nằm
trong 3 ca được cảnh báo trước đó — đây là một gap mới, không được dự
đoán trước.

**Riêng biệt, "Ghi chú cho người thực thi" cuối brief Task 7 còn nêu
tường minh MỘT bộ ba khác** — `"giao hàng cho đơn S00040 luôn nhé"`,
`"nhận hàng cho đơn mua P00003"`, `"tạo báo giá cho Azure Interior, 2
Large Cabinet"` (`cases.py:650,669,683`) — làm bằng chứng cho tuyên bố
"đợt này gần như thuần THÊM khả năng": router nay điền `sop` cho cả ba
nhưng `decide_route` đưa `(sop, one_step)` về `erp_write` nên hành vi cuối
không đổi so với trước đợt này. Cả ba đều **KHÔNG** nằm trong `fails` của
cả hai lần đo `sop_select`. Ca thứ hai của bộ ba này (P00003) còn được
xác nhận sống qua HTTP thật ở kịch bản 2 (Step 4 dưới đây): router trả
`erp_write/one_step`, hỏi xác nhận một bước `receive_order`, đúng đường
`erp_write` cũ — không lệch sang SOP. Vậy tuyên bố "thuần THÊM khả năng"
của brief đứng vững cho cả 3 ca này.

Raw JSON (2 lần đo, giống hệt nhau ngoại trừ latency):

```json
{
  "set": "sop_select",
  "n": 24,
  "acc": 0.8333333333333334,
  "depth_acc": 0.8333333333333334,
  "hijack": 0,
  "fails": [
    {"text": "quy trình nhập kho cho đơn mua P00021", "expected": "nhap-kho", "got": "rag", "expected_depth": "full_sop", "got_depth": "none", "depth_ok": false, "raw_intent": "rag", "raw_sop": null, "hijack": false},
    {"text": "đơn mua P00021 vừa giao tới, làm nốt phần còn lại nhé", "expected": "nhap-kho", "got": "erp_write", "expected_depth": "full_sop", "got_depth": "one_step", "depth_ok": false, "raw_intent": "erp_write", "raw_sop": "nhap-kho", "hijack": false},
    {"text": "báo giá kèm chiết khấu theo cấp khách cho Wood Corner, 10 Desk Pad", "expected": "bao-gia-chiet-khau", "got": "erp_write", "expected_depth": "full_sop", "got_depth": "one_step", "depth_ok": false, "raw_intent": "erp_write", "raw_sop": "bao-gia-chiet-khau", "hijack": false},
    {"text": "Wood Corner mua 10 Desk Pad, tính giá cho khách này giúp tôi", "expected": "clarify_depth", "got": "erp_write", "expected_depth": "unsure", "got_depth": "one_step", "depth_ok": false, "raw_intent": "erp_read", "raw_sop": "bao-gia-chiet-khau", "hijack": false}
  ],
  "errors": []
}
```

Đo lần 2 (byte-for-byte giống hệt, chỉ khác `lat_p50`/`lat_p95`): `1136ms`/`1598ms` so với lần 1 `1874ms`/`7859ms`.

## Step 2: cổng `intent` (vai admin) — chứng minh không thụt

```json
{
  "set": "intent",
  "n": 54,
  "acc": 0.9444444444444444,
  "lat_p50": 1379,
  "lat_p95": 4233,
  "fails": [
    {"text": "đơn của Azure Interior trễ SLA chưa?", "expected": "mixed", "got": "erp_read"},
    {"text": "đơn nào đang vi phạm SLA giao hàng?", "expected": "mixed", "got": "erp_read"},
    {"text": "lệnh sản xuất mới có cần kiểm tra chất lượng theo SOP trước khi hoàn tất không?", "expected": "mixed", "got": "rag"}
  ],
  "errors": []
}
```

**GATE PASS — model=0.944 baseline=0.870.** Hợp đồng router đổi từ 2 dòng
sang 3 dòng (Task 2) KHÔNG làm thụt việc phân loại ý định tầng 1. 3 ca
trượt là các ca `mixed` đã trượt từ trước đợt này (không liên quan tới
đợt này — không có ca nào MỚI trượt so với baseline).

## Step 3: vai kế toán (worker block RỖNG) — không tái phát lỗi cũ

Cấu hình vai kế toán (0 skill ⇒ `sop` luôn rỗng, `depth` luôn `"none"`)
từng làm router phân loại lệnh ghi thành `unknown` 3/3 ở một đợt trước —
chỉ nghiệm thu sống mới bắt được, không test nội bộ nào thấy.

```json
{
  "set": "intent",
  "n": 54,
  "acc": 0.9444444444444444,
  "lat_p50": 1132,
  "lat_p95": 2360,
  "fails": [
    {"text": "đơn của Azure Interior trễ SLA chưa?", "expected": "mixed", "got": "erp_read"},
    {"text": "đơn nào đang vi phạm SLA giao hàng?", "expected": "mixed", "got": "erp_read"},
    {"text": "lệnh sản xuất mới có cần kiểm tra chất lượng theo SOP trước khi hoàn tất không?", "expected": "mixed", "got": "rag"}
  ],
  "errors": []
}
```

`errors = []`, `acc = 0.944` — **giống hệt vai admin, cùng 3 ca trượt, 0
ca trượt thêm.** Không tái phát lỗi "worker rỗng → unknown 3/3". Cấu hình
worker rỗng không gây suy giảm định tuyến ý định trong đợt này.

## Step 4: nghiệm thu sống qua HTTP THẬT

Backend + mcp-odoo × 3 vai khởi động từ CHÍNH worktree này (`start-dev.ps1`,
không phải checkout main) qua `:8002`/`:8003-8005`. Role suy từ header
`x-openwebui-user-id` (tài khoản admin thật trong `YOUDOO_ROLE_MAP`), mỗi
kịch bản một `session_id` riêng, KHÔNG gọi graph trực tiếp.

| # | Câu | Kỳ vọng | Đo được | Kết quả |
|---|---|---|---|---|
| 1 | "làm quy trình nhập kho cho đơn mua P00021" | vào SOP nhap-kho, hỏi kiểm đếm | "Bạn đã kiểm đếm hàng cho đơn mua P00021 chưa? Tổng số lượng thực nhận (tất cả các mặt hàng) là bao nhiêu?" | ✅ ĐÚNG |
| 2 | "nhận hàng cho đơn mua P00003" | đi write planner, hỏi xác nhận một bước | "Mình sẽ thực hiện thao tác sau giúp bạn: **Nhận hàng cho đơn mua P00003** (receive_order: order_ref=P00003). Bạn xác nhận giúp mình nhé? (trả lời \"có\" để thực hiện, \"không\" để hủy)" | ✅ ĐÚNG |
| 3a | "kho báo hàng P00021 đã tới, cần làm gì tiếp" | hỏi lại 2 lựa chọn | "Bạn muốn chạy đủ quy trình (có các bước kiểm tra) hay làm nhanh một bước?" | ✅ ĐÚNG |
| 3b | (cùng session, gửi tiếp) "1" | chạy đủ quy trình | "Bạn đã kiểm đếm hàng cho đơn P00021 chưa? Tổng số lượng thực nhận (tất cả các mặt hàng) là bao nhiêu?" | ✅ ĐÚNG — giống hệt hành vi kịch bản 1 |
| 4 | "quy trình nhập kho là gì?" | trả lời tài liệu, KHÔNG vào SOP | Trả lời 4 bước quy trình nhập kho kèm nguồn trích dẫn `sop.docx`, không hỏi kiểm đếm/xác nhận gì | ✅ ĐÚNG |

**Kịch bản 3 là bằng chứng quan trọng nhất:** hai lượt HTTP tách rời, cùng
`session_id`, chứng minh cơ chế `interrupt(kind="disambiguation")` +
`Command(resume=...)` sống được qua checkpointer Postgres và ĐI ĐÚNG
đường (`clarify_depth` → chọn `full_sop` → node SOP `nhap-kho`) qua đúng
entry point HTTP mà client thật (Open WebUI) dùng — không phải gọi graph
trực tiếp trong test nội bộ. Đây chính là lớp lỗi Task 5 cảnh báo (cơ chế
write-confirmation bản đầu chết hoàn toàn trong production vì gắn tín
hiệu lên `AIMessage.additional_kwargs`, 6 vòng review không ai thấy) —
lần này KHÔNG tái phát.

## Lệch so với dự đoán của spike

1. **Ca hồi quy 2026-07-16 quay lại** (xem "KẾT LUẬN NGAY" ở trên) — spike
   round 3 tuyên bố tự khỏi, đo Task 7 với đúng code đã commit thì không.
2. **1/2 ca "mơ hồ thật" hết tất định** — case #4 ở trên, spike đo "tất
   định 3/3 lượt" về `clarify_depth`, Task 7 đo 2/2 lần đều lệch sang
   `erp_write/one_step`.
3. **1 ca mới, không được spike dự đoán trước** — case #2 ở trên
   ("đơn mua P00021 vừa giao tới..."), không nằm trong danh sách 3 ca
   "kỳ vọng theo số đo spike" mà `cases.py` đã cảnh báo trước.
4. Ngược lại, **3 ca ĐƯỢC cảnh báo trước đều đúng** — cho thấy phần lớn
   dự đoán của spike vẫn đứng vững, lệch chỉ tập trung ở các ca liên quan
   tới cụm "quy trình" xuất hiện CÙNG một mã đơn cụ thể (ca #1, #2) và một
   nhánh của cặp "mơ hồ thật" (ca #4).
5. **Điểm nhấn mạnh thêm sau final review:** ca #2 ("đơn mua P00021 vừa
   giao tới...") không chỉ là "một gap mới" — spec §1.2 (design doc, dòng
   41) đo PRE-PLAN câu này đã đúng `nhap-kho` (✅). `cases.py:667-668` vẫn
   giữ nguyên kỳ vọng đó (không đổi so với pre-plan), nhưng Task 7 đo được
   giờ FAIL (`erp_write/one_step`). Đây là một HỒI QUY thật so với hành vi
   đã đúng trước đợt này, không chỉ là "chưa lấp được". Ca #1 ở
   `cases.py:666` là một tình huống liên quan nhưng khác: pre-plan
   cũng đã đúng `nhap-kho` (spec §1.2 dòng 40), nhưng lần này plan CHỦ
   ĐÍCH đổi kỳ vọng sang `erp_write/one_step` (xem comment tại
   `cases.py:661-665`) — một đánh đổi có ghi nhận, không phải một hồi quy bị
   che giấu. Vậy trong 6 câu đời thật của spec §1.2: 1 cải thiện đã xác
   nhận (kho báo hàng → `clarify_depth`), 2 ca trước đó ❌ nay ĐÚNG theo mô
   hình depth mới (đơn S00012, khách giục — coi one_step→erp_write là hành
   vi đúng THEO THIẾT KẾ), 1 ca đổi kỳ vọng có chủ đích (ca #1), 1 ca hồi
   quy thật (ca #2), 1 ca "mơ hồ thật" mất tính tất định (ca #4, xem ở
   trên).

## Lỗi phát hiện trong chính công cụ đo (Task 7), đã sửa tại chỗ

Script mẫu `backend/run_eval_env.py` cho ở Step 1 của brief Task 7 viết
`sys.path.insert(0, r"D:\Youdoo\backend")` — trỏ vào **main checkout**,
không phải worktree. Chạy nguyên văn trong worktree này nạp NHẦM code cũ
của main (`SOP_SELECT_CASES` 17 ca dạng 2-tuple, không có `depth_acc`) —
lần đo đầu tiên cho `n=17`, không phát hiện ngay là sai vì `acc=0.941`
trông hợp lý. Phát hiện được vì thiếu hẳn khoá `depth_acc` trong output
JSON (Task 6 phải thêm khoá đó). Sửa bằng cách trỏ `sys.path` vào đường
dẫn tuyệt đối của CHÍNH worktree này thay vì `D:\Youdoo\backend`. Đây là
lỗi trong brief (giả định luôn chạy từ main checkout), không phải lỗi
code sản phẩm — không có gì trong `backend/src` hay `backend/evals` bị
ảnh hưởng. File `run_eval_env.py` (đã sửa) bị xoá sau khi đo xong, không
commit, đúng chỉ dẫn của brief.

## Những gì CHƯA làm được

- **`sop_select` chưa xanh** — 4/24 ca trượt, ổn định qua 2 lần đo. Đây là
  gap còn lại lớn nhất của đợt này. Nguyên nhân gốc (tại sao spike và eval
  đầy đủ lệch nhau) CHƯA được điều tra — nằm ngoài phạm vi Task 7 (không
  viết code sản phẩm). Cần một phiên riêng, có thể là spike-lại có kiểm
  soát biến số tốt hơn (số ca cùng lúc trong prompt, thứ tự ca, v.v.).
- Không đo lại độ ổn định của 20 ca ĐÚNG (chỉ đo 2 lần cho toàn bộ set,
  không lặp riêng từng ca như spike vòng 4 làm với 10 ca). Không rõ liệu
  một vài trong 20 ca đúng có tự flaky ở lần đo thứ 3 hay không.
- 3 ca `mixed` trượt ở cổng `intent` (Step 2, Step 3) là nợ có từ trước,
  không thuộc phạm vi đợt này — không điều tra thêm.

---

**Đo bởi:** phiên tiếp tục (2026-08-17), trực tiếp bởi controller (không
qua subagent) — khởi động/dừng tiến trình hạ tầng sống nằm ngoài phạm vi
nên giao cho subagent theo bài học từ sự cố subagent-permission-bypass
trước đó.
