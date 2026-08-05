# Báo cáo — Task 1: sửa ca `bang_gia_chiet_khau` trong `GATHER_CASES` + đo thật

Plan: `docs/superpowers/plans/2026-08-04-gather-cases-product-price-fix.md`
Spec: `docs/superpowers/specs/2026-08-04-gather-cases-product-price-fix-design.md`

## 1. Tóm tắt thay đổi

`backend/evals/cases.py`, ca `bang_gia_chiet_khau` trong `GATHER_CASES`
(~dòng 706-728, sau khi sửa thành 706-730):

- **Câu hỏi**: đổi từ "Azure Interior đặt 50 Large Cabinet được chiết khấu
  bao nhiêu?" sang "Azure Interior đặt 50 Large Cabinet, giá niêm yết là
  bao nhiêu?" — không còn đòi hỏi thông tin (% chiết khấu) mà không tool
  ERP nào trong hệ thống có thể trả về.
- **`required_facts`**: đổi từ `("12%",)` sang `("2.400.000",)` — giá trị
  này THẬT sự xuất hiện trong output `get_product_price`, không phải giá
  trị bịa.
- **`required_tools`**: **giữ nguyên hoàn toàn** —
  `("find_customer", "find_product", "get_product_price")`, không đổi một
  ký tự.
- **Fixture text `get_product_price`**: đổi từ
  `"Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): 2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"`
  sang `"Giá Large Cabinet: 2.400.000 (SL 50)."` — nguyên văn byte-for-byte
  giống ca song sinh đã kiểm chứng trong `MULTI_SOURCE_GATHER_CASES`
  (dòng 570 trong file sau khi sửa).
- **Comment**: thay toàn bộ khối `CẢNH BÁO CHƯA SỬA` (giải thích tại sao
  defect này CỐ Ý chưa sửa) bằng comment xác nhận đã sửa — giải thích
  quyết định đổi câu hỏi thay vì sửa fixture, lý do khác lớp lỗi với
  `get_overdue_invoices`, và ghi chú topic name lệch nội dung có chủ đích
  (ngoài phạm vi plan này).

Diff đầy đủ:

```diff
--- a/backend/evals/cases.py
+++ b/backend/evals/cases.py
@@ -707,22 +707,24 @@ GATHER_CASES = [
     # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
     # một lượt gọi đơn.
     #
-    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
-    # 2026-08-04-multi-source-gather-eval-design.md §7): fixture
-    # get_product_price dưới đây khẳng định "đã áp chiết khấu số lượng 12%",
-    # nhưng sales.get_product_price (sales.py:73-90) chỉ đọc list_price và
-    # docstring nói rõ nó KHÔNG áp pricelist/chiết khấu — pricelist cần ORM
-    # method mà gateway read-only không cho phép. Đây là đúng "hạng lỗi thứ
-    # ba" (fixture khẳng định năng lực tool không có), ở một tool contract
-    # test chưa phủ (nhãn hiện chỉ về ngày/trạng thái, không về giá).
-    # CỐ Ý chưa sửa: required_facts của ca này là ("12%",), sửa sẽ đổi số đo
-    # của set `gather` và cần một lượt đo riêng để quy trách nhiệm.
-    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
+    # Câu hỏi đã sửa từ "được chiết khấu bao nhiêu?" sang tra giá niêm yết
+    # (plan 2026-08-04-gather-cases-product-price-fix): sales.get_product_price
+    # (sales.py:73-90) chỉ đọc list_price, KHÔNG áp pricelist/chiết khấu —
+    # pricelist cần ORM method mà gateway read-only không cho phép. Không
+    # tool ERP nào trong hệ thống trả về được % chiết khấu, nên câu hỏi cũ
+    # đòi required_facts=("12%",) — một giá trị KHÔNG thể đến từ ERP thật,
+    # không phải field bị bỏ sót (khác lớp "hạng lỗi thứ ba" đã sửa ở
+    # get_overdue_invoices). Fixture get_product_price dưới đây nguyên văn
+    # đã kiểm chứng ở ca song sinh trong MULTI_SOURCE_GATHER_CASES.
+    #
+    # Topic vẫn tên "bang_gia_chiet_khau" (dùng chung ở set khác qua
+    # fixtures.load_chunks()) dù ca CỤ THỂ này trong GATHER_CASES giờ đo
+    # tra giá, không phải tra chiết khấu — lệch tên/nội dung có chủ đích,
+    # đổi tên topic ngoài phạm vi plan này.
+    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet, giá niêm yết là bao nhiêu?",
      ("find_customer", "find_product", "get_product_price"),
-     ("12%",),
+     ("2.400.000",),
      {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
       "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
-      "get_product_price":
-      "Giá bán Large Cabinet cho khách Azure Interior (số lượng 50): "
-      "2.400.000đ/sp (đã áp chiết khấu số lượng 12%)"}),
+      "get_product_price": "Giá Large Cabinet: 2.400.000 (SL 50)."}),
 ]
```

Đây là đúng nguyên văn khối thay thế trong task brief (Step 2) —
không có sai khác nào so với những gì brief yêu cầu.

## 2. Test — trước và sau sửa

**Bước xác nhận trước khi sửa**: đối chiếu nội dung hiện tại của
`backend/evals/cases.py:706-728` với khối brief trích dẫn — khớp
100%, không có drift.

**Step 1 (baseline, TRƯỚC khi sửa)**:

```
$ cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && \
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -q
.............................                                            [100%]
29 passed in 3.75s
```

**Step 3 (SAU khi sửa)** — cùng lệnh:

```
$ PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -q
.............................                                            [100%]
29 passed in 3.63s
```

29 passed → 29 passed, **không đổi số lượng**. Sửa case không làm gãy
assertion nào có sẵn.

**Suite unit-only đầy đủ** (SAU khi sửa):

```
$ PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
1122 passed, 4 skipped, 43 deselected in 18.83s
```

Khớp đúng baseline đã biết trước khi bắt đầu task (`1122 passed, 4
skipped, 43 deselected`), 0 failures.

**Ghi chú môi trường (đã biết trước, không phải bug)**: sau khi chạy suite
đầy đủ, `git status` báo `backend/tests/rag/fixtures/bang_gia.xlsx` và
`policy.docx` bị modified (quirk không xác định của `tests/rag/`). Đã
`git checkout --` phục hồi 2 file đó trước khi commit — `git status` sau
đó chỉ còn `backend/evals/cases.py` thay đổi.

## 3. Đo thật `--set gather`

Xác nhận trước khi đo:
- Postgres: container `youdoo-postgres`, `Up 31 minutes (healthy)`,
  cổng `0.0.0.0:5434->5432/tcp`.
- Odoo: `http://localhost:8069` → HTTP 303 (redirect trang login),
  phản hồi bình thường.

```
$ cd D:/Youdoo/.claude/worktrees/gather-cases-product-price-fix/backend && \
  set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather

[gather] model=gemini-3.1-flash-lite pace=4.8s tool_recall=1.0 fact_coverage=1.0 → PASS
== PASS == exit 0 → D:\Youdoo\.claude\worktrees\gather-cases-product-price-fix\logs\jobs\eval-gate-20260805T113806.json
```

Log JSON đầy đủ
(`logs/jobs/eval-gate-20260805T113806.json`, trong worktree):

```json
{
  "job": "eval-gate",
  "exit_code": 0,
  "verdict": "PASS",
  "detail": {
    "gather": {
      "model": "gemini-3.1-flash-lite",
      "pace": 4.8,
      "gate": "PASS",
      "fails": [],
      "tool_recall": 1.0,
      "fact_coverage": 1.0,
      "branch": "base",
      "lat_p50": 2803,
      "lat_p95": 36994
    }
  },
  "started_at": "2026-08-05T11:37:04",
  "duration_s": 61.9
}
```

`tool_recall=1.000 fact_coverage=1.000`, `fails: []` — **cả 4 ca `--set
gather` PASS**, bao gồm ca `bang_gia_chiet_khau` vừa sửa. Job `eval-gate
--set gather` chỉ ghi số đo tổng hợp (aggregate) trong log JSON, không
tách kết quả theo từng ca riêng lẻ trong output; `fails: []` rỗng là bằng
chứng không ca nào trong 4 ca (`sla_giao_hang`, `chinh_sach_hoan_hang`,
`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`) fail — nếu bất kỳ ca nào
fail, `fails` sẽ liệt kê tên ca đó (theo cách job này report, đã quan sát
nhất quán qua các lượt đo trước, ví dụ report Task 1 của plan
`gather-cases-overdue-invoices-fix` §3).

**So sánh 3 ca không đổi** (`sla_giao_hang`, `chinh_sach_hoan_hang`,
`chinh_sach_thanh_toan`) với lượt đo trước — Task 1 Step 5 của plan
`gather-cases-overdue-invoices-fix`
(`docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix-report.md`,
log `eval-gate-20260804T172153.json`):
`tool_recall=1.000 fact_coverage=1.000 fails=[]`. Kết quả lượt đo này
(`tool_recall=1.000 fact_coverage=1.000 fails=[]`) **khớp tuyệt đối** —
không hồi quy ở 3 ca kia. Fixture/question/required_facts của 3 ca đó
không bị chạm trong task này (chỉ ca `bang_gia_chiet_khau` bị sửa), nên
kết quả không đổi là đúng như kỳ vọng.

Ca `bang_gia_chiet_khau` trước đây (`required_facts=("12%",)`) đã PASS
trong các lượt đo trước đó (vì `verify_erp_grounding`/LLM judge từng cho
qua bất chấp "12%" không có căn cứ tool thật — đây chính là lý do plan
này tồn tại: PASS giả không có nghĩa đo đúng năng lực tool). Sau khi sửa,
ca này PASS với `required_facts=("2.400.000",)` — giá trị **thật sự** có
trong output `get_product_price`, nên lần PASS này có ý nghĩa đo lường
thật, không phải PASS nhờ model tự bịa số khớp fixture cũ.

## 4. Xác nhận không còn comment claim defect này chưa sửa

```
$ grep -n "CẢNH BÁO CHƯA SỬA" backend/evals/cases.py
(không có kết quả)
```

Không còn dòng nào trong file. Grep mở rộng thêm các biến thể liên quan:

```
$ grep -n "chưa sửa\|CHƯA SỬA\|12%" backend/evals/cases.py
541:    # Lỗi tương tự trong GATHER_CASES (từng CỐ Ý chưa sửa) đã được sửa ở
715:    # đòi required_facts=("12%",) — một giá trị KHÔNG thể đến từ ERP thật,
```

- Dòng 541: thuộc comment của ca `chinh_sach_thanh_toan`/
  `get_overdue_invoices` trong `MULTI_SOURCE_GATHER_CASES`, viết ở plan
  TRƯỚC (`gather-cases-overdue-invoices-fix`) — nói ở **thì quá khứ**
  ("từng CỐ Ý chưa sửa) đã được sửa ở plan ...") rằng defect ĐÓ (khác
  defect này) đã được sửa. Không claim gì đang unfixed.
- Dòng 715: thuộc comment MỚI viết trong task này, mô tả **câu hỏi cũ**
  (`"required_facts của ca này là ("12%",)"`) ở thì quá khứ, giải thích
  tại sao nó sai — không claim defect hiện tại chưa sửa.

Không còn comment nào tuyên bố `bang_gia_chiet_khau`/`get_product_price`
là defect còn tồn tại chưa sửa.

## 5. Kết luận theo tiêu chí hoàn thành

| Tiêu chí | Kết quả |
|---|---|
| Câu hỏi + `required_facts` + fixture text đổi theo đúng khối brief Step 2 | ĐẠT — diff §1 khớp nguyên văn brief |
| `required_tools` không đổi | ĐẠT — vẫn `("find_customer", "find_product", "get_product_price")` |
| Fixture text khớp byte-for-byte ca song sinh `MULTI_SOURCE_GATHER_CASES` | ĐẠT — `"Giá Large Cabinet: 2.400.000 (SL 50)."` xuất hiện ở cả dòng 570 và 729 |
| Test `test_eval_gather.py` PASS, cùng số lượng trước/sau | ĐẠT — 29 passed cả hai lượt |
| Suite unit-only đầy đủ PASS, khớp baseline | ĐẠT — 1122 passed, 4 skipped, 43 deselected |
| `--set gather` đo thật, 4/4 ca PASS bao gồm `bang_gia_chiet_khau` | ĐẠT — `tool_recall=1.000 fact_coverage=1.000 fails=[]` |
| 3 ca còn lại không đổi so với lượt đo trước | ĐẠT — khớp tuyệt đối với `eval-gate-20260804T172153.json` |
| Không còn comment claim defect này chưa sửa | ĐẠT — grep xác nhận (§4) |

Không có gì bất thường hay lệch so với dự đoán của brief/spec. Không cần
điều tra thêm.

## 6. Concerns

Không có concern chặn (blocking) nào. Một lưu ý minh bạch:

- Log JSON của job `eval-gate --set gather` chỉ ghi số đo **tổng hợp**
  (aggregate `tool_recall`/`fact_coverage` trên cả 4 ca, cộng danh sách
  `fails`), không ghi chi tiết `erp_facts`/`called` riêng cho từng ca
  trong file log. Bằng chứng "ca `bang_gia_chiet_khau` PASS" dựa trên
  `fails: []` (rỗng — không ca nào trong 4 ca fail) kết hợp
  `fact_coverage=1.0` (nếu ca này fail, coverage sẽ < 1.0 vì đây là 1
  trong 4 ca duy nhất đóng góp vào mẫu số) — không phải một dòng log
  tường minh ghi tên "bang_gia_chiet_khau: PASS". Đây là cách job này
  report nhất quán qua tất cả các lượt đo trước (xem báo cáo plan
  `gather-cases-overdue-invoices-fix`, cùng định dạng), không phải hạn
  chế riêng của lượt đo này.
- `n=1` cho lượt đo `--set gather` — cùng rủi ro stochastic đã ghi nhận ở
  report của plan trước (LLM judge `verify_erp_grounding` trong vòng lặp
  chống-bịa có thể phán khác nhau giữa các lượt chạy). Lượt đo lần này
  cho kết quả sạch (`fails: []`), nhưng không phải bảo đảm tuyệt đối
  chống fail gián đoạn trong tương lai.
