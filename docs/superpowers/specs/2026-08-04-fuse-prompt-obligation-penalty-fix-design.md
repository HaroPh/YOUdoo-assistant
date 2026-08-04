# Sửa `FUSE_PROMPT` — đối chiếu đủ cặp "nghĩa vụ + hậu quả/mức phạt"

**Ngày:** 2026-08-04
**Trạng thái:** design đã duyệt (kèm thực nghiệm đo thật), chờ plan

## 1. Vấn đề

Set eval `multi_source_gather` (xem
`docs/superpowers/plans/2026-08-04-multi-source-gather-eval-design.md`) đo
được 2 ca fail ở topic `sla_giao_hang`, cả hai đều là "tổng hợp kém"
(`fuse_answer` chọn sai/thiếu đoạn tài liệu), KHÔNG phải "chọn sai tool".

Kiểm tra lặp lại 8 lần (n=8, cùng seed dữ liệu qua production path thật —
`make_gather_erp_node` + `render_fuse_input` + `FUSE_PROMPT`) cho ca
`WH/OUT/00001` ("Phiếu WH/OUT/00001 có vi phạm SLA không?"): **8/8 lần fail
giống hệt nhau** — không phải may rủi n=1 như phát hiện gốc, mà là lỗi hệ
thống 100% lặp lại (khả năng do temperature thấp + `/no_think` trong
`FUSE_PROMPT`).

Đối chiếu điểm rerank thật của 4 chunk cố định cho topic này
(`evals/fixtures/chunks.json`, đóng băng từ `retrieve()` thật):

```
[1] Điều 5 — Phạt chậm trễ giao hàng   rerank_score = 1.72   (đoạn NGHĨA VỤ + HẬU QUẢ)
[2] Điều 3 — Thời gian giao hàng       rerank_score = -1.92
[3] Điều 550 (luật dân sự, gia công)   rerank_score = -4.35  (không liên quan)
[4] Điều 560 (luật dân sự, gửi giữ)    rerank_score = -4.55  (không liên quan)
```

Retrieval/rerank ĐÚNG — chunk đúng xếp hạng 1 với khoảng cách điểm rất lớn.
Đây không phải lỗi retrieval.

**Gốc rễ thật (đọc kỹ cả 2 ca fail cùng topic, không chỉ 1 ca):**
`sla_giao_hang` có 2 chunk mô tả 2 khái niệm liên đới nhưng khác nhau —
Điều 3 (NGHĨA VỤ/thời hạn giao hàng) và Điều 5 (HẬU QUẢ/mức phạt khi vi
phạm). Model không nhất quán ưu tiên chunk nào:

- Ca `S00042` ("có đáp ứng SLA giao hàng không?", đáp án mong đợi "3 ngày"
  từ Điều 3): model lại lý luận theo Điều 5 ("trễ 1 ngày → phạt 0,5%"),
  bỏ qua điều khoản 3-ngày khẩn cấp.
- Ca `WH/OUT/00001` ("có vi phạm SLA không?", đáp án mong đợi "0,5%" từ
  Điều 5): model lý luận theo Điều 3 (nghĩa vụ giao hàng + báo trước 48
  giờ), không bao giờ nêu tiếp mức phạt.

Cả hai không phải "chọn nhầm chunk" mà là **dừng lại ở MỘT trong hai khái
niệm liên đới, không tổng hợp cả hai** — `FUSE_PROMPT` hiện tại không có
quy tắc nào yêu cầu đối chiếu đủ khi tài liệu có cặp "nghĩa vụ + hậu quả".

## 2. Thực nghiệm: 2 biến thể prompt, đo thật cả 8 ca `MULTI_SOURCE_GATHER_CASES`

Baseline (`FUSE_PROMPT` hiện tại): **6/8 PASS** — fail đúng 2 ca
`sla_giao_hang` (S00042, WH/OUT/00001).

**Variant A** (quy tắc CHUNG: "nếu nhiều đoạn cùng liên quan, đối chiếu
TẤT CẢ trước khi trả lời") — **6/8 PASS, đổi thành phần fail**:
- WH/OUT/00001: FIXED (PASS).
- S00042: vẫn FAIL (hết bịa số "01", nhưng vẫn thiếu "3 ngày" — xem §5).
- `chinh_sach_thanh_toan`/INV/2026/00020: **HỒI QUY** (PASS → FAIL) — quy
  tắc quá rộng khiến model tự suy luận thêm (tính ra ngày cụ thể "quá hạn
  từ 01/08/2026" thay vì nói thẳng "30 ngày" như tài liệu nêu), trượt khỏi
  câu trả lời literal-match mà eval mong đợi.

Kết luận: quy tắc CHUNG quá rộng, có hồi quy THẬT (đo được, không phải suy
đoán) — không dùng.

**Variant B** (quy tắc HẸP: chỉ kích hoạt cho câu hỏi TUÂN THỦ/VI PHẠM một
điều khoản, VÀ chỉ khi tài liệu có cặp đoạn nghĩa vụ + hậu quả/mức phạt) —
**7/8 PASS, KHÔNG hồi quy**:
- WH/OUT/00001: FIXED (PASS).
- INV/2026/00020: giữ nguyên PASS (không đụng).
- 5 ca còn lại: giữ nguyên PASS.
- S00042: vẫn FAIL — nguyên nhân khác hẳn, xem §5.

Variant B là lựa chọn của plan này.

## 3. Nội dung sửa — thêm 1 dòng quy tắc vào `FUSE_PROMPT`

File: `backend/src/agents/prompts.py`, hằng số `FUSE_PROMPT`
(`prompts.py:158-168`).

Chèn NGAY TRƯỚC dòng cuối `"- Trả lời tự nhiên, thân thiện, ngắn gọn bằng
tiếng Việt."`:

```
- Với câu hỏi về việc có TUÂN THỦ/VI PHẠM một điều khoản hay không (SLA,
  thời hạn, chính sách): nếu TÀI LIỆU có một đoạn nêu NGHĨA VỤ/THỜI HẠN và
  một đoạn KHÁC nêu HẬU QUẢ/MỨC PHẠT khi vi phạm, hãy dùng CẢ HAI — xác
  định trước có vi phạm nghĩa vụ hay không, rồi nêu hậu quả/mức phạt
  tương ứng nếu có vi phạm.
```

Đây là đoạn văn bản ĐÃ ĐƯỢC ĐO THẬT nguyên văn ở §2 (Variant B) — không
phải diễn giải lại, plan chỉ cần chép đúng.

**Đây là prompt SẢN XUẤT thật** (`make_fuse_answer_node` dùng
`FUSE_PROMPT` cho MỌI câu hỏi nhánh `mixed` trong production, không chỉ
eval) — khác các plan trước chỉ sửa fixture/test. Rủi ro cao hơn, cần đo
kỹ cả set đang GÁC (`multi_source`) lẫn set ghi nhận (`multi_source_gather`).

## 4. Ràng buộc cứng: `multi_source` KHÔNG được lùi

`multi_source` là 1 trong 6 set đang GÁC thật (`_gate()` yêu cầu
`citation_validity == 1.0`, `fabricated_number == 0`,
`both_source_coverage >= baseline` — hiện `baseline-qwen3-8b-multi_source.json`).
`FUSE_PROMPT` dùng CHUNG cho cả `multi_source` (erp_block viết tay) và
`multi_source_gather` (gather_erp thật) — sửa prompt ảnh hưởng CẢ HAI set.
Task đo thật phải chạy `--set multi_source` SAU khi sửa và xác nhận không
lùi dưới baseline, không chỉ đo `multi_source_gather`.

## 5. S00042 — CỐ Ý KHÔNG sửa trong plan này

Ca `S00042` ("Đơn S00042 có đáp ứng SLA giao hàng không?", đáp án mong đợi
"3 ngày") vẫn FAIL với cả 2 biến thể đã thử. Đọc kỹ `erp_facts` model nhận
được (từ `get_sale_order_detail` qua `gather_erp` thật): dữ liệu ERP
**không có trường nào báo đơn này là "khẩn cấp"** — model không có căn cứ
để biết phải áp điều khoản "đơn hàng khẩn cấp xử lý trong 3 ngày" (Điều 3)
thay vì hạn 7-ngày mặc định. Đây là **lỗ hổng dữ liệu ERP** (cùng lớp với
các plan `sale-order-detail-dates`/`sale-order-effective-dates` trước —
thiếu field, không phải lỗi tổng hợp), không phải thứ `FUSE_PROMPT` sửa
được.

**Cố ý không mở rộng phạm vi plan này để giải quyết S00042**: đây là 2
nguyên nhân khác nhau hoàn toàn (thiếu dữ liệu ERP vs. tổng hợp thiếu
sót) — trộn vào cùng 1 lần đo sẽ không quy được trách nhiệm rõ ràng, đúng
kỷ luật dự án đã áp dụng nhiều lần (`get_product_price`/"12%",
`get_overdue_invoices`/"quá hạn N ngày"). Nếu muốn đóng gap này, cần plan
riêng kiểm tra xem `sale.order` có field nào biểu thị "khẩn cấp"
(`priority`? ghi chú nội bộ?) hay hoàn toàn không lưu — có thể là gap
không đóng được nếu Odoo demo data không có khái niệm đó.

## 6. Kiểm chứng thêm: fix có LẶP LẠI được không (không chỉ 1 lần PASS)

Bug gốc đã xác nhận lặp lại 100% (8/8, §1). Fix phải được kiểm tra tương
tự — 1 lần PASS ở §2 chưa đủ để kết luận fix ổn định. Plan cần chạy lại
CA `WH/OUT/00001` với `FUSE_PROMPT` mới N lần (khuyến nghị N=5) để xác
nhận PASS ổn định, không phải lần đo may mắn.

## 7. File bị chạm

| File | Việc |
|---|---|
| `backend/src/agents/prompts.py` | Thêm 1 dòng quy tắc vào `FUSE_PROMPT` (§3) |
| `backend/tests/agents/test_prompts.py` | Thêm test chốt substring quy tắc mới có trong `FUSE_PROMPT`, cùng khuôn với test hiện có tại dòng 113/121 (`assert "..." in FUSE_PROMPT`) |
| `backend/tests/agents/test_fanout.py` | Test hiện có `FUSE_PROMPT.rstrip().endswith("/no_think")` (dòng 57) và test khớp `captured["system"] == FUSE_PROMPT` (dòng 393) — chạy lại để xác nhận KHÔNG vỡ, không cần sửa nội dung |
| `docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md` (mới) | Report: đo lặp lại N=5 ca WH/OUT/00001, đo thật `--set multi_source` (không lùi baseline) + `--set multi_source_gather` (kỳ vọng 7/8, ghi rõ S00042 vẫn fail vì lý do khác) |

## 8. Tiêu chí hoàn thành

1. `FUSE_PROMPT` có đúng 1 dòng quy tắc mới, nội dung khớp §3 nguyên văn.
2. `pytest` unit-only xanh toàn bộ.
3. Chạy thật `--set multi_source`: `both_source_coverage` KHÔNG thấp hơn
   baseline hiện có, `citation_validity == 1.0`, `fabricated_number == 0`
   — gate PASS. Nếu lùi, DỪNG và báo cáo (đây là ràng buộc cứng §4).
4. Chạy thật `--set multi_source_gather`: kỳ vọng `both_source_coverage`
   tăng từ 0.750 lên 0.875 (7/8) — ca `WH/OUT/00001` PASS,
   `S00042` vẫn FAIL (lý do khác, đã ghi ở §5, không phải hồi quy của
   plan này).
5. Chạy lại riêng ca `WH/OUT/00001` N=5 lần (§6): tất cả PASS, xác nhận
   fix ổn định chứ không phải may mắn 1 lần.
