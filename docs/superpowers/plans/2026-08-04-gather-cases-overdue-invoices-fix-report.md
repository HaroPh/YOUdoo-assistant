# Báo cáo — Task 1: sửa fixture `get_overdue_invoices` trong `GATHER_CASES` + dọn comment + đo thật

Plan: `docs/superpowers/plans/2026-08-04-gather-cases-overdue-invoices-fix.md`
Spec: `docs/superpowers/specs/2026-08-04-gather-cases-overdue-invoices-fix-design.md`

## 1. Tóm tắt thay đổi

`backend/evals/cases.py`, 2 vị trí:

1. **`MULTI_SOURCE_GATHER_CASES`** (comment cross-reference, ngay trước ca
   `chinh_sach_thanh_toan`/`get_overdue_invoices` thứ hai, ~dòng 518-528):
   đổi 3 câu cuối từ thì "hiện tại còn tồn tại lỗi ở GATHER_CASES" sang thì
   "đã sửa ở plan này — cả hai fixture nay khớp nhau".
2. **`GATHER_CASES`**, ca `chinh_sach_thanh_toan` (~dòng 665-695):
   - Xoá 2 đoạn `"quá hạn 32 ngày | "` và `"quá hạn 20 ngày | "` khỏi
     fixture text của `get_overdue_invoices`.
   - Thay comment `CẢNH BÁO CHƯA SỬA` bằng comment xác nhận đã sửa + tham
     chiếu tới lượt đo thật xác nhận không hồi quy.
   - `question`, `required_tools`, `required_facts` — **giữ nguyên hoàn
     toàn**, không đổi một ký tự nào.

Diff đầy đủ:

```diff
--- a/backend/evals/cases.py
+++ b/backend/evals/cases.py
@@ -516,16 +516,15 @@ MULTI_SOURCE_GATHER_CASES = [
      "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì quá hạn thanh toán?",
      "30 ngày", "INV/2026/00020"),
     # Fixture ĐIỀU CHỈNH từ GATHER_CASES (cùng câu hỏi, cùng tool), KHÔNG
-    # chép nguyên văn: bản ở GATHER_CASES khẳng định "quá hạn N ngày", nhưng
-    # get_overdue_invoices (accounting.py:35-51) chỉ đọc/trả về _FIELDS —
-    # name, partner_id, invoice_date, invoice_date_due, amount_total,
-    # amount_residual, payment_state — KHÔNG có field số-ngày-quá-hạn nào;
-    # display thật là "{name} | {partner} | đến hạn {invoice_date_due} |
-    # còn {amount_residual}". Đây đúng "hạng lỗi thứ ba" đã nêu ở đầu file
-    # (fixture khẳng định năng lực tool không có). Lỗi tương tự VẪN CÒN
-    # nguyên trong GATHER_CASES — CỐ Ý chưa sửa ở đó, cùng lý do với ca
-    # get_product_price/"12%" đã ghi chú ở cuối GATHER_CASES: sửa sẽ đổi số
-    # đo của set `gather` và cần một lượt đo riêng để quy trách nhiệm.
+    # chép nguyên văn: get_overdue_invoices (accounting.py:35-51) chỉ
+    # đọc/trả về _FIELDS — name, partner_id, invoice_date, invoice_date_due,
+    # amount_total, amount_residual, payment_state — KHÔNG có field
+    # số-ngày-quá-hạn nào; display thật là "{name} | {partner} | đến hạn
+    # {invoice_date_due} | còn {amount_residual}". Đây đúng "hạng lỗi thứ
+    # ba" đã nêu ở đầu file (fixture khẳng định năng lực tool không có).
+    # Lỗi tương tự trong GATHER_CASES (từng CỐ Ý chưa sửa) đã được sửa ở
+    # plan 2026-08-04-gather-cases-overdue-invoices-fix — cả hai fixture
+    # nay khớp nhau và khớp format thật.
     # erp_fact là tuple 2 phương án, thừa kế nguyên do từ MULTI_SOURCE_CASES
     # (model trả lời đúng nhưng gọi khách hàng bằng TÊN thay vì lặp mã đơn).
     # Lưu ý: "S00050" KHÔNG có trong fixture — get_overdue_invoices trả hóa
@@ -669,19 +668,14 @@ GATHER_CASES = [
     # đơn CHỈ xuất hiện trong dữ liệu tool, đòi model phải đọc và đối chiếu
     # đúng dòng giữa nhiều dòng dữ liệu khác.
     #
-    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
-    # 2026-08-04-multi-source-gather-eval-design.md §7): fixture dưới đây
-    # khẳng định "quá hạn 32 ngày" / "quá hạn 20 ngày" (số ngày quá hạn),
-    # nhưng accounting.get_overdue_invoices (accounting.py:35-51) chỉ
-    # đọc/trả về _FIELDS (accounting.py:7-8) — name, partner_id,
-    # invoice_date, invoice_date_due, amount_total, amount_residual,
-    # payment_state — KHÔNG có field số-ngày-quá-hạn nào. Đúng "hạng lỗi thứ
-    # ba" (fixture khẳng định năng lực tool không có); defect y hệt đã được
-    # SỬA ở fixture tương ứng của MULTI_SOURCE_GATHER_CASES (xem comment ở
-    # cases.py:518-528). CỐ Ý chưa sửa ở đây: required_facts của ca này là
-    # ("INV/2026/00030",) — không chạm field "quá hạn N ngày" — sửa sẽ đổi
-    # số đo của set `gather` và cần một lượt đo riêng để quy trách nhiệm,
-    # cùng lý do với ca get_product_price/"12%" bên dưới.
+    # Fixture dưới đây đã được sửa khớp format thật của
+    # accounting.get_overdue_invoices (accounting.py:35-51, chỉ trả _FIELDS
+    # — accounting.py:7-8 — không có field số-ngày-quá-hạn nào). Trước đó
+    # fixture khẳng định "quá hạn N ngày" (hạng lỗi thứ ba, phát hiện ở
+    # spec 2026-08-04-multi-source-gather-eval-design.md §7) — đã sửa ở
+    # plan 2026-08-04-gather-cases-overdue-invoices-fix, đo thật xác nhận
+    # tool_recall/fact_coverage không đổi (required_facts của ca này chưa
+    # từng chạm field đó).
     ("chinh_sach_thanh_toan",
      "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
      "bị tạm dừng xử lý không?",
@@ -690,9 +684,9 @@ GATHER_CASES = [
      {"get_overdue_invoices":
       "2 hóa đơn quá hạn:\n"
       "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
-      "quá hạn 32 ngày | còn 4.200.000\n"
+      "còn 4.200.000\n"
       "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
-      "quá hạn 20 ngày | còn 1.000.000"}),
+      "còn 1.000.000"}),
     # bang_gia_chiet_khau — ca 3 tool nối chuỗi (find_customer → find_product
     # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
     # một lượt gọi đơn.
```

Fixture text sau khi sửa khớp cấu trúc field/nhãn với format thật tạo ra bởi
`accounting.get_overdue_invoices` (accounting.py:47-49) — KHÔNG phải khớp
byte-for-byte: formatter thật dùng `{:,.0f}` (dấu phẩy ngăn nghìn, ví dụ
"4,200,000") và `invoice_date_due` thô từ Odoo là ISO (ví dụ "2026-06-30"),
trong khi fixture (đúng quy ước hiển thị đã dùng xuyên suốt file này) viết
dấu chấm ngăn nghìn ("4.200.000") và ngày dd/mm/yyyy ("30/06/2026"). Khác
biệt rendering này là chủ ý của file, không phải sai lệch so với tool thật —
cái khớp là CẤU TRÚC field/nhãn, đúng thứ mà "hạng lỗi thứ ba" quan tâm:

```python
body = "\n".join(f"  {r['name']} | {(r['partner_id'] or [0, 'N/A'])[1]} "
                 f"| đến hạn {r.get('invoice_date_due') or 'N/A'} "
                 f"| còn {r['amount_residual']:,.0f}" for r in rows)
return ok({"rows": rows, "count": len(rows)},
          f"{len(rows)} hóa đơn quá hạn:\n{body}")
```

→ `"{name} | {partner} | đến hạn {invoice_date_due} | còn {amount_residual}"`
— đúng pattern mà fixture đã sửa dùng.

## 2. Test — trước và sau sửa

**Step 1 (baseline, TRƯỚC khi sửa)** — chạy từ worktree
(`D:/Youdoo/.claude/worktrees/gather-cases-overdue-invoices-fix/backend`,
`.venv` cục bộ trong worktree, không phải `D:/Youdoo/backend`):

```
$ PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest \
    tests/jobs/test_eval_gather.py tests/jobs/test_eval_multi_source_gather.py -q
........................................                                 [100%]
40 passed in 5.67s
```

**Step 4 (SAU khi sửa)** — cùng lệnh:

```
$ PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest \
    tests/jobs/test_eval_gather.py tests/jobs/test_eval_multi_source_gather.py -q
........................................                                 [100%]
40 passed in 3.85s
```

40 passed → 40 passed, **không đổi số lượng**. Sửa fixture text không làm
gãy assertion nào có sẵn.

**Suite unit-only đầy đủ** (đối chiếu không có test nào xa phụ thuộc chuỗi
"quá hạn" đã xoá):

```
$ PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
1120 passed, 4 skipped, 43 deselected in 27.84s
```

Khớp đúng baseline đã biết trước khi bắt đầu task (`1120 passed, 4 skipped,
43 deselected`), 0 failures.

**Ghi chú môi trường (đã biết trước, không phải bug)**: chạy suite đầy đủ
làm 2 file fixture nhị phân `backend/tests/rag/fixtures/bang_gia.xlsx` và
`policy.docx` bị `git status` báo modified (quirk không xác định của
`tests/rag/`). Đã `git checkout --` phục hồi 2 file đó trước khi commit —
`git status` sau đó chỉ còn `backend/evals/cases.py` thay đổi.

## 3. Đo thật `--set gather`

Postgres (`youdoo-postgres`, container `pgvector/pgvector:pg16`, healthy)
và Odoo (`http://localhost:8069`, HTTP 303 — trang login, phản hồi bình
thường) đều đang chạy, xác nhận trước khi đo.

```
$ cd D:/Youdoo/.claude/worktrees/gather-cases-overdue-invoices-fix/backend && \
  set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather

[gather] model=gemini-3.1-flash-lite pace=4.8s tool_recall=1.0 fact_coverage=1.0 → PASS
== PASS == exit 0 → D:\Youdoo\.claude\worktrees\gather-cases-overdue-invoices-fix\logs\jobs\eval-gate-20260804T172153.json
```

Log JSON đầy đủ
(`logs/jobs/eval-gate-20260804T172153.json`, trong worktree):

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
      "lat_p50": 3877,
      "lat_p95": 69136
    }
  },
  "started_at": "2026-08-04T17:20:18",
  "duration_s": 94.7
}
```

**So sánh với baseline gần nhất và sạch nhất** — `docs/superpowers/plans/2026-08-02-sale-order-effective-dates-report.md`
(§"Task 3 Bước 5", `tool_recall=1.0 fact_coverage=1.0 fails=[]`, log
`eval-gate-20260802T171038.json`): **khớp tuyệt đối, không hồi quy**. Đây là
baseline chính dùng để so sánh — đo cùng điều kiện (cùng 4 ca `--set
gather`, cùng job `eval-gate`), gần đây hơn (2026-08-02) và không bị bất kỳ
đính chính/disclaim nào.

Baseline SP-2c gốc (`docs/superpowers/specs/2026-08-01-sp2c-gather-eval-design.md`,
4 ca, `tool_recall=1.000 fact_coverage=1.000`, log
`eval-gate-20260801T163040.json`) cho cùng con số nhưng chỉ giữ để tham
khảo lịch sử — báo cáo của chính lượt đo đó
(`docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`, dòng
23-41 và 81-96) đã tự đính chính 2 vấn đề: (1) `required_fact` gốc của ca
`chinh_sach_thanh_toan` khi đó là "32 ngày" — rò rỉ nguyên văn từ câu hỏi,
sau mới đổi thành `INV/2026/00030`; (2) 2/4 fixture (`sla_giao_hang`,
`chinh_sach_hoan_hang`) chạy trên field ngày gán sai cho
`get_sale_order_detail`, sửa ở plan sau. Lượt đo đó chưa từng chạy lại sau
2 đính chính này, nên dùng nó làm baseline chính cho phép so sánh
"không hồi quy" ở đây là chưa đủ chắc — baseline 2026-08-02 ở trên sạch hơn
và gần điều kiện đo hiện tại hơn.

Cả hai baseline đều cho `tool_recall=1.0`/`fact_coverage=1.0` giống lượt đo
sau khi sửa ở đây, nên kết luận "không hồi quy" không đổi dù dùng baseline
nào — chỉ khác độ tin cậy của điểm so sánh. `fails: []` — không có ca nào
fail, bao gồm cả ca `chinh_sach_thanh_toan` vừa sửa fixture. Đúng như lập
luận trước ở spec §2/§5: `required_facts` của ca đó là `("INV/2026/00030",)`
— chưa từng chạm chuỗi `"quá hạn N ngày"` bị xoá, nên xoá chuỗi đó khỏi
fixture text không ảnh hưởng tới điểm số.

**Rủi ro stochastic chưa loại trừ (ghi nhận, không phải bug ở lượt đo
này):** trước khi sửa, câu hỏi của ca `chinh_sach_thanh_toan`/
`get_overdue_invoices` đã có sẵn nguyên văn "quá hạn thanh toán 32 ngày",
và TRƯỚC bản sửa của plan này, cùng chuỗi "32 ngày" đó cũng có mặt trong
fixture tool — nếu model lặp lại cụm này, bước chống-bịa
`verify_erp_grounding` (gọi từ `make_gather_erp_node`,
`backend/src/agents/fanout.py:139`) sẽ thấy nó "có căn cứ" trong tool
output. Sau khi sửa ở đây, chuỗi "32 ngày" CHỈ còn trong câu hỏi, không còn
trong tool output. Nếu một câu trả lời của model gán cụm "32 ngày" cho dữ
liệu tool (thay vì chỉ lặp lại câu hỏi), LLM judge trong
`verify_erp_grounding` có thể phán câu trả lời đó KHÔNG có căn cứ và thay
TOÀN BỘ chuỗi `erp_facts` bằng thông điệp fallback — xoá luôn required
fact `INV/2026/00030`, khiến `fact_coverage` fail cho ca này. Đây không
phải suy đoán: `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`
(dòng 55-72) ghi lại đúng cơ chế này gây fail thật ở nhánh `policy`. Lượt
đo `--set gather` ở trên (§3) ra `fails: []` sạch — bằng chứng thật, nhưng
là **n=1** trên một pipeline có LLM judge trong vòng lặp, không phải bảo
đảm chống fail gián đoạn trong tương lai. Nếu ca
`chinh_sach_thanh_toan`/`get_overdue_invoices` bắt đầu fail không ổn định ở
các lượt `--set gather` sau này, nên kiểm tra tương tác verify-chống-bịa
này trước khi kết luận đó là hồi quy chất lượng model.

## 4. Xác nhận không còn comment `CẢNH BÁO CHƯA SỬA` nào trỏ tới defect này

```
$ grep -n "CẢNH BÁO CHƯA SỬA" backend/evals/cases.py
694:    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
```

Chỉ còn **đúng 1 chỗ** (dòng 694), thuộc ca `bang_gia_chiet_khau` /
`get_product_price` / `"12%"` — đây là defect **KHÁC**
(`sales.get_product_price` không áp chiết khấu số lượng), cố ý vẫn chưa
sửa, **ngoài phạm vi plan này** (đã ghi rõ trong spec §7 và trong report
Task 4 của plan `2026-08-04-multi-source-gather-eval`, mục "Những gì CỐ Ý
không sửa"). Comment `CẢNH BÁO CHƯA SỬA` trỏ tới defect
`get_overdue_invoices` trong `GATHER_CASES` đã được thay bằng comment xác
nhận đã sửa (§1 ở trên) — không còn tồn tại.

## 5. Kết luận theo tiêu chí hoàn thành

| Tiêu chí | Kết quả |
|---|---|
| Fixture text khớp cấu trúc field/nhãn của format thật `get_overdue_invoices` | ĐẠT — xem §1 |
| `required_facts`/`required_tools`/`question` không đổi | ĐẠT — diff §1 chỉ chạm fixture text + comment |
| Test `test_eval_gather.py` + `test_eval_multi_source_gather.py` PASS, cùng số lượng trước/sau | ĐẠT — 40 passed cả hai lượt |
| Suite unit-only đầy đủ PASS, khớp baseline | ĐẠT — 1120 passed, 4 skipped, 43 deselected |
| `--set gather` đo thật, không hồi quy so với baseline SP-2c | ĐẠT — `tool_recall=1.000 fact_coverage=1.000`, `fails: []` |
| Chỉ còn đúng 1 comment `CẢNH BÁO CHƯA SỬA` (ca `get_product_price`/"12%") | ĐẠT — grep xác nhận |

Không có gì bất thường hay lệch so với dự đoán của spec. Không cần điều
tra thêm.

## 6. Concerns

Không có concern nào phát sinh trong quá trình thực hiện. Một lưu ý vận
hành (không phải bug): brief Step 1/4/5 viết lệnh với `cd D:/Youdoo/backend`
— đây là repo chính, KHÔNG phải worktree đang làm việc
(`D:/Youdoo/.claude/worktrees/gather-cases-overdue-invoices-fix/backend`).
Đã chạy đúng trong worktree (nơi `.venv`/`.env` được copy sẵn theo mô tả
task) thay vì theo đúng nguyên văn đường dẫn trong brief; kết quả không đổi
vì cả 2 nơi cùng baseline test, chỉ khác đường dẫn tới đúng workspace đang
sửa.
