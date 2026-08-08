# Báo cáo kết thúc: 2026-08-07-order-confirmation-email

**Trạng thái:** HOÀN THÀNH — merge vào `main`, §Cổng đánh giá live-verify ĐẠT
cả 3 tiêu chí, đo **TRƯỚC khi merge** (thay đổi quy trình theo yêu cầu
người dùng — xem mục cuối), bắt được 1 lỗi thật trong quá trình đó.

**Nhánh:** `order-confirmation-email` (worktree, đã xoá sau merge)

**Ngày hoàn thành:** 2026-08-08

**Spec:** `docs/superpowers/specs/2026-08-07-order-confirmation-email-design.md`
**Plan:** `docs/superpowers/plans/2026-08-07-order-confirmation-email.md`

---

## Tóm tắt

Agent nay gửi được **mail thật** (không phải giả lập) — mail xác nhận đơn
hàng cho khách, dùng template Odoo có sẵn "Sales: Order Confirmation", qua
đúng cổng xác nhận trước khi gửi. Đây là điểm nối đầu tiên trong số nhiều
điểm nối gửi mail dự kiến (RFQ, báo giá, hóa đơn...) — cố ý thu hẹp phạm
vi để chứng minh **cơ chế lõi** hoạt động đầu-cuối thật trước khi nhân
rộng ở các plan sau.

## Task 1: Whitelist bảo mật cho `send_mail`/`send`

**Commit:** `34d0868`. Review: spec ✅, quality Approved, 0 finding.

## Task 2: 2 tool MCP dùng chung

**Commit:** `c3e1ce7`. Review: spec ✅, quality Approved. 1 finding Important
gắn nhãn plan-mandated (2 tool không có try/except, khớp
`confirm_sale_order`/`create_quotation` — không sửa ở Task 2, xử lý ở tầng
coordinator Task 3).

## Task 3: Coordinator — **thiết kế lại hoàn toàn giữa chừng**

Đây là task phức tạp nhất dự án này từng gặp: **1 lần redesign kiến trúc +
3 vòng fix**, mỗi vòng đều verify bằng probe thật (không chỉ đọc code).

### Review lần 1 (opus) — phát hiện Critical bằng probe thật

Thiết kế gốc (1 node, khuôn giống mọi coordinator khác) gọi
`preview_template_email` (1 write thật — tạo `mail.mail` nháp) TRƯỚC
`_interrupt()` trong CÙNG node. Reviewer đo bằng probe: LangGraph **replay
toàn bộ node** khi resume sau interrupt → preview bị gọi LẦN THỨ HAI → mail
**thật sự gửi đi KHÔNG PHẢI bản người dùng đã duyệt**. Đồng thời phát hiện
Odoo có cron "Mail: Email Queue Manager" đang bật, tự gửi mọi `mail.mail`
ở trạng thái `outgoing` mỗi giờ — đảo ngược quyết định §4.1 gốc của spec
("không dọn bản nháp khi từ chối").

**Redesign** (commit `f5e9bf1`): tách 2 node LangGraph (Node 1 soạn mail 1
lần, lưu vào state; Node 2 đọc từ state, xác nhận, gửi) + tool mới
`discard_prepared_email` (hủy chủ động khi từ chối) + đăng ký
`WRITE_PLANNER_PROMPT` (phát hiện thêm: coordinator chưa từng được đăng ký,
không LLM nào chọn được tool từ 1 lượt chat thật — đúng lớp lỗi
`write-confirmation-ux-fix`).

### Review lần 2 (opus) — xác nhận bug Critical đã sửa thật (negative control), +3 Important mới

Reviewer tự dựng probe qua `build_graph()` thật, **negative control tái
tạo đúng bug cũ** (chứng minh probe có độ nhạy thật), rồi xác nhận thiết
kế mới: preview chỉ gọi 1 lần, mail gửi đúng bản đã duyệt. Nhưng phát hiện
3 Important mới: (1) Node 2 không re-check `write_actions_enabled()` — tắt
kill-switch giữa lúc chờ xác nhận vẫn gửi được; (2) không test nào pin
đăng ký `WRITE_PLANNER_PROMPT`; (3) helper test `_write_graph()` lại drift
(đúng lỗi đã sửa 1 lần ở plan `invoice-confirm-summary`, tái diễn).

**Fix round 2** (commit `5278500`): cả 3 đã sửa, verify bằng probe thật
(kể cả trường hợp gate tắt giữa chừng → discard đúng mail_id, không
double-discard).

## Final whole-branch review (opus) — 5 Important, 1 fix wave

Reviewer phát hiện thêm 1 mâu thuẫn logic sâu: fix round 2 vừa thêm
"gate tắt thì hủy nháp" — nhưng chính lệnh hủy (`unlink`) CŨNG bị chặn bởi
đúng gate đó, nên trong tình huống cần dọn nhất, hủy gần như chắc chắn thất
bại âm thầm. Cộng thêm: cổng xác nhận chỉ hiện SỐ LƯỢNG người nhận (không
hiện AI), và không test nào bảo vệ đoạn loại trừ 2-node trong `graph.py`
khỏi bị gỡ nhầm (sẽ gây vòng lặp vô hạn tạo mail.mail).

**Quyết định người dùng:** sửa code ngay 2 finding (hiện người nhận thật;
test bảo vệ wiring), 2 finding còn lại (gate-off cleanup + hội thoại bỏ
dở) chỉ sửa thông báo cho trung thực + ghi chú giới hạn đã biết, để dành
redesign "bản nháp trơ tính" cho plan sau — không mở rộng phạm vi.

**Fix wave** (commit `3dccb30`): cả 4 đã sửa, verify bằng probe thật (kể
cả tự dựng lại bug graph để chứng minh test không vacuous). Không breakage
mới.

## Kết quả test toàn bộ

```
cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"
```
```
1212 passed, 4 skipped, 46 deselected
```

**Baseline trước plan:** 1197 passed. **Tổng cộng:** +15 test mới.

---

## Thay đổi quy trình: live-verify TRƯỚC merge, không phải sau

Hai plan trước (`invoice-confirm-summary`, `customer-contact-detail`) đều
live-verify SAU khi merge vào main, theo đúng tiền lệ `write-confirmation-ux-fix`.
Người dùng yêu cầu đảo lại cho plan này: **luôn thử qua API/UI thật TRƯỚC
khi merge** — hợp lý hơn hẳn cho một tính năng gửi mail thật ra ngoài,
rủi ro cao hơn các plan trước.

**Cách thực hiện:** khởi động backend + mcp-odoo trỏ thẳng vào code
WORKTREE (chưa merge), dùng interpreter của repo chính với cwd đặt ở
worktree — cùng kỹ thuật đã dùng để chạy test, áp dụng cho chạy server
thật.

### Chuẩn bị hạ tầng cho live-verify thật

- Người dùng tự cấu hình SMTP Gmail thật (`smtp.gmail.com:587`, STARTTLS
  strict) — trước đó `ir.mail_server` rỗng suốt các phiên trước.
- Đổi email "Acme Corporation" (demo data, `info@agrolait.com` — domain
  demo chuẩn của Odoo) thành email thật của người dùng, để tự kiểm tra
  nhận mail mà không gửi nhầm ra domain không kiểm soát được.
- Sự cố giữa chừng (đã điều tra, không phải lỗi code): Odoo tự reload do
  cơ chế bảo vệ `limit_time_real` (1 thread HTTP treo >120s từ kết nối
  trình duyệt cũ) → backend/mcp-odoo (tiến trình thủ công, không auto-
  restart) chết theo → khởi động lại cả hai, xác nhận qua log Odoo.

### Tiêu chí 1+2 — ĐẠT ngay (không cần SMTP)

`"Gửi mail xác nhận đơn S00171 cho khách"` → hiện đúng
`Tới: Acme Corporation <email thật>` (không phải số lượng — xác nhận trực
tiếp fix Finding 4 của final review hoạt động thật). Trả lời "không" →
xác nhận qua Odoo thật: bản `mail.mail` **biến mất hoàn toàn** (discard/
unlink thành công).

### Tiêu chí 3 — phát hiện + sửa 1 lỗi thật ngay tại chỗ

Lần gửi thật đầu tiên: **crash** — `"Error executing tool
send_prepared_email: list index out of range"`. Điều tra: template "Sales:
Order Confirmation" có `auto_delete=True` — **Odoo tự xóa bản ghi
`mail.mail` ngay sau khi gửi THÀNH CÔNG** (hành vi mặc định của Odoo, đo
thật lần đầu tiên chạm code path này với SMTP thật). Code cũ giả định bản
ghi luôn còn để đọc lại `state`, đọc list rỗng → `IndexError`.

**Đây chính xác là giá trị của yêu cầu "test trước khi merge":** lỗi này
không thể bị bắt bởi bất kỳ unit test giả lập nào (mọi test đều mock phản
hồi cố định), và cũng không xuất hiện ở tiêu chí 1+2 (không chạm SMTP
thật). Nếu merge trước rồi mới test, lỗi này sẽ nằm im trong production
tới khi ai đó thật sự bấm gửi mail — đúng loại sự cố dự án này luôn cố
gắng ngăn bằng live-verify.

**Sửa ngay** (commit `3237696`, trên worktree, trước merge): `rows` rỗng
sau `send()` = dấu hiệu gửi THÀNH CÔNG (không phải lỗi) — `auto_delete`
chỉ áp dụng nhánh thành công, gửi thất bại Odoo vẫn giữ record ở
`state='exception'` (đã kiểm chứng thật trước đó khi chưa có SMTP). Restart
mcp-odoo + backend, chạy lại → `"Đã gửi mail."`.

**Xác nhận cuối cùng — bằng chứng mạnh nhất có thể:** người dùng tự kiểm
tra hộp thư Gmail thật và xác nhận **đã nhận được mail** đúng tiêu đề
"My Company (San Francisco) Đơn hàng (Mã S00171)".

### Kết luận cổng đánh giá

**Cả 3 tiêu chí ĐẠT, đo TRƯỚC khi merge, có bằng chứng thật ở mức cao nhất
(con người tự kiểm tra hộp thư nhận mail thật) — bắt và sửa 1 lỗi thật
ngay tại chỗ, không để lọt vào production.**

---

## Nhận xét cuối

- ✅ 3 task code (Task 3 qua 1 redesign + 3 vòng fix, mỗi vòng verify bằng
  probe thật) + final whole-branch review (1 fix wave) + merge fast-forward
- ✅ Test suite 1212 passed (không regression thật — 1 test timing flaky
  không liên quan, tự xác nhận không tái diễn)
- ✅ Tổng 9 finding Important qua toàn bộ review loop (Task 3: 1 Critical
  + 3 + 3, final review: 5) đều được xác nhận + sửa/ruling, phần lớn verify
  bằng probe thật thay vì chỉ đọc code — kể cả negative control để chứng
  minh probe có độ nhạy thật
- ✅ **Live-verify TRƯỚC merge (thay đổi quy trình theo yêu cầu người dùng)
  bắt được 1 lỗi thật (`auto_delete` crash) mà không unit test nào phát
  hiện được — xác nhận giá trị thật của thay đổi quy trình này**
- ✅ Bằng chứng cuối: mail thật đã tới hộp thư Gmail thật của người dùng
- ⏳ Minor deferred (nhiều mục qua các vòng review, liệt kê trong ledger
  SDD của plan — không chặn merge): redesign "bản nháp trơ tính" (tạo mail
  ở trạng thái cron bỏ qua, chỉ chuyển sang outgoing lúc gửi thật) — để
  dành cho plan mở rộng các điểm nối gửi mail khác
